"""Bounded, non-blocking telemetry with a separate SQLite writer."""

from __future__ import annotations

import json
import logging
import math
import queue
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any

logger = logging.getLogger("dreamrsi.inspector")
DEFAULT_JOURNAL = Path(".dreamrsi/inspector.sqlite3")
_SECRET_KEY = re.compile(
    r"api.?key|authorization|password|secret|access.?token|refresh.?token|^token$", re.I
)
_SECRET_VALUE = re.compile(
    r"\b(?:sk-(?:or-v1-)?[\w-]{16,}|gh[pousr]_[\w]{20,}|github_pat_[\w]{20,})\b"
)
_CONTENT_KEYS = {"task", "state", "observation", "proposal", "action", "source", "metadata"}


def safe_value(
    value: Any, *, include_content: bool = True, depth: int = 0, budget: list[int] | None = None
) -> Any:
    """Project telemetry, never execute serializers or stringify arbitrary objects."""
    if budget is None:
        budget = [2000]
    budget[0] -= 1
    if depth > 9 or budget[0] < 0:
        return "[depth limit]"
    kind = type(value)
    if value is None or kind is bool:
        return value
    if kind in (int, float):
        try:
            return value if math.isfinite(value) else None
        except OverflowError:
            return "[number exceeds display range]"
    if kind is str:
        clean = _SECRET_VALUE.sub("[redacted]", value)
        return clean if len(clean) <= 12000 else clean[:12000] + "\n[truncated]"
    if kind is dict:
        result = {}
        for key, child in islice(value.items(), 256):
            if not isinstance(key, str):
                continue
            if _SECRET_KEY.search(key):
                result[key] = "[redacted]"
            elif not include_content and key in _CONTENT_KEYS:
                result[key] = "[content disabled]"
            else:
                result[key] = safe_value(
                    child, include_content=include_content, depth=depth + 1, budget=budget
                )
        if len(value) > 256:
            result["_truncated_keys"] = len(value) - 256
        return result
    if kind in (list, tuple):
        items = [
            safe_value(v, include_content=include_content, depth=depth + 1, budget=budget)
            for v in value[:512]
        ]
        if len(value) > 512:
            items.append({"truncated_items": len(value) - 512})
        return items
    return f"[unsupported {type(value).__name__}]"


@dataclass
class _Barrier:
    done: threading.Event


class LiveInspector:
    """Record locally in the background; observation never drives a policy.

    Pass ``inspector=LiveInspector()`` to DreamRSI, then run ``dreamrsi watch``
    in the project folder. Flush/close after execution to finish pending writes.
    Limits, redaction and unsupported values affect telemetry only. Overflow is
    reported explicitly instead of blocking model work or inventing history.
    """

    def __init__(
        self,
        path: str | Path = DEFAULT_JOURNAL,
        *,
        include_content: bool = True,
        queue_capacity: int = 4096,
    ):
        if type(queue_capacity) is not int or queue_capacity < 1:
            raise ValueError("queue_capacity must be a positive integer")
        if type(include_content) is not bool:
            raise ValueError("include_content must be boolean")
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Inspector history can contain prompts and answers. Keep it local.
        ignore = self.path.parent / ".gitignore"
        if self.path.parent.name == ".dreamrsi" and not ignore.exists():
            ignore.write_text("*.sqlite3\n*.sqlite3-*\n*.sqlite\n*.sqlite-*\n", encoding="utf-8")
        self.include_content = include_content
        self.session_id = uuid.uuid4().hex
        self.dropped_events = 0
        self.error: str | None = None
        self._closed = False
        self._queue: queue.Queue[Any] = queue.Queue(queue_capacity)
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._write, name="dreamrsi-inspector", daemon=True)
        self._thread.start()
        if not self._ready.wait(5):
            raise OSError("Inspector journal did not open within five seconds")
        if self.error:
            raise OSError(self.error)

    def record(
        self,
        event_type: str,
        *,
        run_id: str | None = None,
        data: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> None:
        if self._closed or self.error:
            return
        try:
            projection_budget = [2000]
            payload = safe_value(
                data or {}, include_content=self.include_content, budget=projection_budget
            )
            if projection_budget[0] < 0:
                payload["_projection_limited"] = True
            item = (
                event_type,
                run_id,
                timestamp if timestamp is not None else time.time(),
                json.dumps(payload, allow_nan=False, ensure_ascii=False),
            )
            if len(item[3]) > 262144:
                payload = safe_value(data or {}, include_content=False)
                payload["_truncated"] = "Content exceeded the telemetry size limit"
                encoded = json.dumps(payload, allow_nan=False, ensure_ascii=False)
                if len(encoded) > 262144:
                    payload = {"_truncated": "Telemetry exceeded the size limit"}
                    encoded = json.dumps(payload)
                item = (*item[:3], encoded)
            self._queue.put_nowait(item)
        except queue.Full:
            self.dropped_events += 1
        except Exception:
            self.dropped_events += 1
            logger.debug("Could not project inspector telemetry", exc_info=True)

    def on_event(self, event: Any) -> None:
        self.record(
            event.type.value,
            run_id=event.run_id,
            data={**event.data, "round_number": event.round_number},
            timestamp=event.timestamp,
        )

    def flush(self, timeout: float = 5) -> bool:
        if self.error or self._closed:
            return False
        barrier = _Barrier(threading.Event())
        started = time.monotonic()
        try:
            self._queue.put(barrier, timeout=timeout)
        except queue.Full:
            return False
        return barrier.done.wait(max(0, timeout - (time.monotonic() - started))) and not self.error

    def close(self) -> None:
        if self._closed:
            return
        self.flush()
        self._closed = True
        if self._thread.is_alive():
            try:
                self._queue.put(None, timeout=5)
            except queue.Full:
                return
            self._thread.join(timeout=5)

    def __enter__(self) -> LiveInspector:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    async def compare(self, runtime: Any, world: Any, policies: list[Any]) -> list[dict]:
        """Record real offline trajectories on one frozen world; no promotion."""
        reports = []
        for index, policy in enumerate(policies):
            effective = runtime._protected_policy(policy)
            trajectory = await runtime.replay(world, policy, policy_id=f"inspector_{index}")
            attempted = sum(len(step.batch) for step in trajectory.steps)
            reports.append(
                {
                    "policy": type(effective).__name__,
                    "requested_policy": type(policy).__name__,
                    "preserves_original": bool(
                        runtime.quality and runtime.quality.preserve_policy
                    ),
                    "world_id": world.world_id,
                    "tree_id": world.tree.tree_id,
                    "replay_score": trajectory.replay_score,
                    "raw_quality": runtime._trajectory_quality(trajectory),
                    "probes": trajectory.total_probes,
                    "attempted": attempted,
                    "missing": sum(
                        max(0, len(step.batch) - len(step.revealed_nodes))
                        for step in trajectory.steps
                    ),
                    "revealed": trajectory.revealed_node_ids,
                    "rounds": len(trajectory.steps),
                }
            )
        self.record("replay_comparison", data={"reports": reports})
        return reports

    def _write(self) -> None:
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=5)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS inspector_events ("
                "seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
                "event_type TEXT NOT NULL, run_id TEXT, timestamp REAL, data TEXT)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS inspector_run ON inspector_events(run_id,seq)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS inspector_meta "
                "(session_id TEXT PRIMARY KEY, dropped INTEGER NOT NULL, "
                "last_seen REAL, closed INTEGER)"
            )
            connection.commit()
            self._ready.set()
            while True:
                try:
                    first = self._queue.get(timeout=1)
                except queue.Empty:
                    with connection:
                        connection.execute(
                            "INSERT OR REPLACE INTO inspector_meta VALUES (?,?,?,?)",
                            (self.session_id, self.dropped_events, time.time(), 0),
                        )
                    continue
                batch = [first]
                while len(batch) < 128 and first is not None:
                    try:
                        batch.append(self._queue.get_nowait())
                    except queue.Empty:
                        break
                with connection:
                    for item in batch:
                        if item is not None and not isinstance(item, _Barrier):
                            connection.execute(
                                "INSERT INTO inspector_events "
                                "(session_id,event_type,run_id,timestamp,data) VALUES (?,?,?,?,?)",
                                (self.session_id, *item),
                            )
                    connection.execute(
                        "INSERT OR REPLACE INTO inspector_meta VALUES (?,?,?,?)",
                        (self.session_id, self.dropped_events, time.time(), int(None in batch)),
                    )
                for item in batch:
                    if isinstance(item, _Barrier):
                        item.done.set()
                    self._queue.task_done()
                if None in batch:
                    break
        except Exception as exc:
            self.error = f"Inspector journal unavailable: {type(exc).__name__}: {exc}"
            logger.warning(self.error)
        finally:
            self._ready.set()
            if connection is not None:
                connection.close()


class InspectorReader:
    """Read one recorded run and its session diagnostics without modifying SQLite."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()

    def snapshot(self, run_id: str | None = None) -> dict:
        if not self.path.is_file():
            return {"runs": [], "events": [], "dropped": 0, "truncated": False}
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            rows = connection.execute(
                "SELECT run_id, session_id, timestamp, data,seq FROM inspector_events "
                "WHERE event_type='run_opened' ORDER BY seq DESC LIMIT 40"
            ).fetchall()
            runs = [
                {
                    "id": row[0],
                    "session_id": row[1],
                    "timestamp": row[2],
                    "seq": row[4],
                    **json.loads(row[3]),
                }
                for row in rows
            ]
            selected = next((run for run in runs if run["id"] == run_id), None)
            if selected is None and run_id is None and runs:
                selected = runs[0]
            if selected is None:
                return {"runs": runs, "events": [], "dropped": 0, "truncated": False}
            next_seq = min(
                (
                    r["seq"]
                    for r in runs
                    if r["session_id"] == selected["session_id"] and r["seq"] > selected["seq"]
                ),
                default=2**63 - 1,
            )
            records = connection.execute(
                "SELECT seq,event_type,run_id,timestamp,data FROM inspector_events "
                "WHERE run_id=? OR (run_id IS NULL AND session_id=? AND seq>=? AND seq<?) "
                "ORDER BY seq DESC LIMIT 10001",
                (selected["id"], selected["session_id"], selected["seq"], next_seq),
            ).fetchall()
            dropped = connection.execute(
                "SELECT dropped,last_seen,closed FROM inspector_meta WHERE session_id=?",
                (selected["session_id"],),
            ).fetchone()
            return {
                "runs": runs,
                "selected_run": selected["id"],
                "events": [
                    {
                        "seq": row[0],
                        "type": row[1],
                        "run_id": row[2],
                        "timestamp": row[3],
                        "data": json.loads(row[4]),
                    }
                    for row in reversed(records[:10000])
                ],
                "dropped": dropped[0] if dropped else 0,
                "truncated": len(records) > 10000,
                "writer_alive": bool(
                    dropped and not dropped[2] and time.time() - (dropped[1] or 0) < 5
                ),
            }
        finally:
            connection.close()

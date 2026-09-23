"""Independent validation collection with single-use held-out world batches."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Callable
from typing import Any

from dreamrsi.errors import ConfigurationError


def task_key(task):
    return hashlib.sha256(json.dumps(task, sort_keys=True, allow_nan=False).encode()).hexdigest()


def split_tasks(tasks, validation_count, seed=0):
    """Split distinct JSON tasks before development; callers own semantic independence."""
    if not 0 < validation_count < len(tasks):
        raise ValueError("Require nonempty training and validation partitions")
    if len({task_key(t) for t in tasks}) != len(tasks):
        raise ValueError("Duplicate tasks cannot be split independently")
    ordered = list(tasks)
    random.Random(seed).shuffle(ordered)
    return ordered[validation_count:], ordered[:validation_count]


class HoldoutPipeline:
    def __init__(
        self,
        tasks,
        worlds_per_check=1,
        *,
        abandon_inflight=False,
        quality_metric: Callable[[dict[str, Any]], float | None] | None = None,
        quality_metric_id: str | None = None,
    ):
        if not tasks or type(worlds_per_check) is not int or worlds_per_check < 1:
            raise ValueError("Provide validation tasks and a positive batch size")
        if len({task_key(t) for t in tasks}) != len(tasks):
            raise ValueError("Validation tasks must be distinct")
        if quality_metric is not None and not callable(quality_metric):
            raise ValueError("quality_metric must be callable")
        if quality_metric is not None and (
            not isinstance(quality_metric_id, str) or not quality_metric_id.strip()
        ):
            raise ValueError("A quality_metric_id is required for a custom quality metric")
        if quality_metric is None and quality_metric_id is not None:
            raise ValueError("quality_metric_id requires a quality_metric")
        self.tasks = list(tasks)
        self.worlds_per_check = worlds_per_check
        self.quality_metric = quality_metric
        self.quality_metric_id = quality_metric_id or "best_score"
        self.worlds = []
        self.used = 0
        self.prepared = False
        self.next_task_index = 0
        self.inflight = None
        self.abandon_inflight = abandon_inflight
        if type(abandon_inflight) is not bool:
            raise ValueError("abandon_inflight must be boolean")
        self.last_evaluation = None

    async def prepare(self, runtime, training_task):
        if task_key(training_task) in {task_key(t) for t in self.tasks}:
            raise ConfigurationError("Training task overlaps the validation partition")
        if runtime._campaign_id:
            saved = await runtime._store.get_checkpoint(runtime._campaign_id + ":validation")
            if saved is not None:
                from dreamrsi.checkpoints import world_load

                if saved["task_keys"] != [task_key(t) for t in self.tasks]:
                    raise ConfigurationError("Validation partition changed")
                if saved.get("quality_metric_id", "best_score") != self.quality_metric_id:
                    raise ConfigurationError("Validation quality metric changed")
                self.worlds = [world_load(w) for w in saved["worlds"]]
                self.used, self.prepared = saved["used"], saved["prepared"]
                self.next_task_index = saved.get("next_task_index", len(self.worlds))
                self.inflight = saved.get("inflight")
                self.last_evaluation = saved.get("last_evaluation")
        await self._reconcile_inflight(runtime)
        if self.prepared:
            return
        # Partition registration is cheap. A held-out task is collected only
        # when a replay-improving challenger needs an independent check.
        self.prepared = True
        await self._persist(runtime)

    async def _reconcile_inflight(self, runtime):
        if self.inflight is not None:
            if not self.abandon_inflight:
                raise ConfigurationError(
                    "Interrupted validation collection requires external reconciliation; "
                    "use abandon_inflight=True only after confirming external work has stopped. "
                    "The uncertain task will be skipped and its charges retained."
                )
            self.next_task_index = max(self.next_task_index, self.inflight + 1)
            self.inflight = None
            await self._persist(runtime)

    async def _collect_until(self, runtime, end):
        from dreamrsi.replay import ReplayWorld

        original = runtime._champion_policy
        try:
            # The initial policy is fixed across checks, even after promotion.
            runtime._champion_policy = runtime._get_policy()
            while len(self.worlds) < end and self.next_task_index < len(self.tasks):
                index = self.next_task_index
                task = self.tasks[index]
                self.inflight = index
                await self._persist(runtime)
                result = await runtime.run(task)
                self.worlds.append(ReplayWorld(result.tree))
                self.next_task_index = index + 1
                self.inflight = None
                await self._persist(runtime)
        finally:
            runtime._champion_policy = original

    def quality_from_trajectory(self, trajectory):
        """Best raw quality among observations revealed by one replay trajectory."""
        if self.quality_metric is None:
            return trajectory.best_score
        values = []
        for observation in trajectory.observations.values():
            try:
                quality = self.quality_metric(observation)
            except (KeyError, TypeError, ValueError):
                continue
            if (
                not isinstance(quality, bool)
                and isinstance(quality, (int, float))
                and math.isfinite(quality)
            ):
                values.append(float(quality))
        return max(values) if values else None

    async def evaluate(self, runtime, incumbent, challenger):
        if not self.prepared:
            raise ConfigurationError("Prepare the validation partition before evaluation")
        await self._reconcile_inflight(runtime)
        end = self.used + self.worlds_per_check
        if end > len(self.worlds) + len(self.tasks) - self.next_task_index:
            return {"validation_status": "exhausted", "validation_scores": {}}
        await self._collect_until(runtime, end)
        worlds = self.worlds[self.used : end]
        self.used = end  # consume even when a policy fails; never adapt to reused holdout
        self.last_evaluation = {
            "validation_status": "inflight",
            "validation_scores": {},
            "validation_world_ids": [world.world_id for world in worlds],
        }
        await self._persist(runtime)
        scores, reports = {}, []
        quality_complete = True
        for role, policy in (("incumbent", incumbent), ("challenger", challenger)):
            values = []
            for world in worlds:
                record: dict[str, Any] = {"role": role, "world_id": world.world_id}
                try:
                    trajectory = await runtime.replay(world, policy, policy_id=role)
                    raw_quality = self.quality_from_trajectory(trajectory)
                    record.update(
                        score=trajectory.replay_score,
                        best_score=trajectory.best_score,
                        raw_quality=raw_quality,
                        probes=trajectory.total_probes,
                        rounds=trajectory.total_rounds,
                    )
                    if raw_quality is None:
                        quality_complete = False
                    if trajectory.replay_score is not None:
                        values.append(trajectory.replay_score)
                except Exception as exc:
                    quality_complete = False
                    record.update(score=None, error_type=type(exc).__name__, error=str(exc))
                reports.append(record)
            if len(values) == len(worlds):
                scores[role] = sum(values) / len(values)
        valid = len(scores) == 2 and quality_complete
        self.last_evaluation = {
            "validation_scores": scores if valid else {},
            "validation_world_ids": [w.world_id for w in worlds],
            "validation_status": "evaluated" if valid else "insufficient_evidence",
            "validation_reports": reports,
        }
        await self._persist(runtime)
        return self.last_evaluation

    async def _persist(self, runtime):
        if runtime._campaign_id:
            from dreamrsi.checkpoints import world_data

            await runtime._store.save_checkpoint(
                runtime._campaign_id + ":validation",
                {
                    "task_keys": [task_key(t) for t in self.tasks],
                    "quality_metric_id": self.quality_metric_id,
                    "worlds": [world_data(w) for w in self.worlds],
                    "used": self.used,
                    "prepared": self.prepared,
                    "next_task_index": self.next_task_index,
                    "inflight": self.inflight,
                    "last_evaluation": self.last_evaluation,
                },
            )

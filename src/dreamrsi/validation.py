"""Independent validation collection with single-use held-out world batches."""

from __future__ import annotations

import hashlib
import json
import random
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
    def __init__(self, tasks, worlds_per_check=1, *, abandon_inflight=False):
        if not tasks or type(worlds_per_check) is not int or worlds_per_check < 1:
            raise ValueError("Provide validation tasks and a positive batch size")
        if len({task_key(t) for t in tasks}) != len(tasks):
            raise ValueError("Validation tasks must be distinct")
        self.tasks = list(tasks)
        self.worlds_per_check = worlds_per_check
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
        from dreamrsi.replay import ReplayWorld

        if task_key(training_task) in {task_key(t) for t in self.tasks}:
            raise ConfigurationError("Training task overlaps the validation partition")
        if runtime._campaign_id:
            saved = await runtime._store.get_checkpoint(runtime._campaign_id + ":validation")
            if saved is not None:
                from dreamrsi.checkpoints import world_load

                if saved["task_keys"] != [task_key(t) for t in self.tasks]:
                    raise ConfigurationError("Validation partition changed")
                self.worlds = [world_load(w) for w in saved["worlds"]]
                self.used, self.prepared = saved["used"], saved["prepared"]
                self.next_task_index = saved.get("next_task_index", len(self.worlds))
                self.inflight = saved.get("inflight")
                self.last_evaluation = saved.get("last_evaluation")
        if self.inflight is not None:
            if not self.abandon_inflight:
                raise ConfigurationError(
                    "Interrupted validation collection requires external reconciliation; "
                    "use abandon_inflight=True only after confirming external work has stopped. "
                    "The uncertain task will be skipped and its charges retained."
                )
            self.next_task_index = self.inflight + 1
            self.inflight = None
            await self._persist(runtime)
        if self.prepared:
            return
        original = runtime._champion_policy
        try:
            # Fixed collector policy, before policy-development feedback exists.
            runtime._champion_policy = runtime._get_policy()
            for index in range(self.next_task_index, len(self.tasks)):
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
        self.prepared = True
        await self._persist(runtime)

    async def evaluate(self, runtime, incumbent, challenger):
        end = self.used + self.worlds_per_check
        if end > len(self.worlds):
            return {"validation_status": "exhausted", "validation_scores": {}}
        worlds = self.worlds[self.used : end]
        self.used = end  # consume even when a policy fails; never adapt to reused holdout
        self.last_evaluation = {
            "validation_status": "inflight",
            "validation_scores": {},
            "validation_world_ids": [world.world_id for world in worlds],
        }
        await self._persist(runtime)
        scores, reports = {}, []
        for role, policy in (("incumbent", incumbent), ("challenger", challenger)):
            values = []
            for world in worlds:
                record: dict[str, Any] = {"role": role, "world_id": world.world_id}
                try:
                    trajectory = await runtime.replay(world, policy, policy_id=role)
                    record.update(
                        score=trajectory.replay_score,
                        probes=trajectory.total_probes,
                        rounds=trajectory.total_rounds,
                    )
                    if trajectory.replay_score is not None:
                        values.append(trajectory.replay_score)
                except Exception as exc:
                    record.update(score=None, error_type=type(exc).__name__, error=str(exc))
                reports.append(record)
            if len(values) == len(worlds):
                scores[role] = sum(values) / len(values)
        self.last_evaluation = {
            "validation_scores": scores if len(scores) == 2 else {},
            "validation_world_ids": [w.world_id for w in worlds],
            "validation_status": "evaluated" if len(scores) == 2 else "insufficient_evidence",
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
                    "worlds": [world_data(w) for w in self.worlds],
                    "used": self.used,
                    "prepared": self.prepared,
                    "next_task_index": self.next_task_index,
                    "inflight": self.inflight,
                    "last_evaluation": self.last_evaluation,
                },
            )

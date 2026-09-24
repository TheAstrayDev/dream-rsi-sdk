"""Reuse recorded policies across related tasks without restoring a campaign."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from dreamrsi._invoke import invoke
from dreamrsi.artifacts import PolicyCodec
from dreamrsi.checkpoints import world_data, world_load
from dreamrsi.errors import ConfigurationError, PolicyError
from dreamrsi.validation import HoldoutPipeline, task_key


def _digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, allow_nan=False, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class AdaptiveRun:
    result: Any
    improvement: Any | None
    family: str
    raw_quality: float
    reused_policy: bool
    trained: bool
    promoted: bool
    incumbent_saved: bool = False
    policy_origin: str | None = None
    quality_floor: float | None = None
    degraded: bool = False
    training_skipped: bool = False


@dataclass(frozen=True)
class PolicyMemorySettings:
    """Independent persistence/reuse switches and artifact acceptance rules.

    ``accept_world(current_task, recorded_task, world)`` is checked before a
    new world enters replay and again when an old world is imported. The
    policy rule receives ``(task, policy, origin, saved_raw_quality)`` and is
    checked both when saving and when loading. Rules may be sync or async.
    """

    save_worlds: bool = True
    reuse_worlds: bool = True
    save_policies: bool = True
    reuse_policies: bool = True
    accept_world: Any | None = None
    accept_policy: Any | None = None
    allow_training: Any | None = None

    def __post_init__(self) -> None:
        for name in ("save_worlds", "reuse_worlds", "save_policies", "reuse_policies"):
            if type(getattr(self, name)) is not bool:
                raise ConfigurationError(f"{name} must be boolean")
        for name in ("accept_world", "accept_policy", "allow_training"):
            value = getattr(self, name)
            if value is not None and not callable(value):
                raise ConfigurationError(f"{name} must be callable")


class AdaptivePolicyMemory:
    """Algorithmic policy reuse with a quality-triggered offline improvement.

    ``family_of`` defines task compatibility; ``raw_quality`` and
    ``minimum_quality`` must use the same scale. All three are caller-supplied
    deterministic functions. ``runtime_factory(task, policy)`` creates a fresh
    DreamRSI runtime, configured with independent validation and an offline
    method when training may be needed.
    """

    def __init__(
        self,
        *,
        store: Any,
        runtime_factory: Any,
        family_of: Any,
        raw_quality: Any,
        minimum_quality: Any,
        policy_codec: PolicyCodec | None = None,
        settings: PolicyMemorySettings | None = None,
        namespace: str = "default",
    ) -> None:
        if not isinstance(namespace, str) or not namespace:
            raise ConfigurationError("Policy memory namespace must be a nonempty string")
        for name, value in (
            ("runtime_factory", runtime_factory),
            ("family_of", family_of),
            ("raw_quality", raw_quality),
            ("minimum_quality", minimum_quality),
        ):
            if not callable(value):
                raise ConfigurationError(f"{name} must be callable")
        self.store = store
        self.runtime_factory = runtime_factory
        self.family_of = family_of
        self.raw_quality = raw_quality
        self.minimum_quality = minimum_quality
        self.codec = policy_codec or PolicyCodec()
        if settings is not None and not isinstance(settings, PolicyMemorySettings):
            raise ConfigurationError("settings must be PolicyMemorySettings")
        self.settings = settings or PolicyMemorySettings()
        self.namespace = namespace

    @staticmethod
    async def _allowed(rule: Any, *args: Any) -> bool:
        if rule is None:
            return True
        allowed = await invoke(rule, *args)
        if type(allowed) is not bool:
            raise ConfigurationError("Policy memory acceptance rules must return boolean")
        return allowed

    def _family(self, task: Any) -> str:
        family = self.family_of(task)
        if not isinstance(family, str) or not family:
            raise ConfigurationError("family_of must return a nonempty string")
        return family

    def _key(self, family: str) -> str:
        digest = hashlib.sha256(f"{self.namespace}\0{family}".encode()).hexdigest()
        return f"policy-memory:{digest}"

    def _world_key(self, family: str) -> str:
        return self._key(family) + ":training-worlds"

    def _holdout_key(self, family: str) -> str:
        return self._key(family) + ":reserved-holdouts"

    async def _reserve_holdouts(self, family: str, validation: HoldoutPipeline) -> None:
        data = await self.store.get_checkpoint(self._holdout_key(family)) or {
            "schema": 1,
            "namespace": self.namespace,
            "family": family,
            "task_keys": [],
        }
        if (
            data.get("schema") != 1
            or data.get("namespace") != self.namespace
            or data.get("family") != family
            or not isinstance(data.get("task_keys"), list)
        ):
            raise PolicyError("Incompatible holdout reservation record")
        keys = [task_key(task) for task in validation.tasks]
        if set(keys) & set(data["task_keys"]):
            raise ConfigurationError("Validation task was reserved by an earlier improvement")
        data["task_keys"].extend(keys)
        await self.store.save_checkpoint(self._holdout_key(family), data)

    async def _worlds(self, family: str) -> list[dict]:
        data = await self.store.get_checkpoint(self._world_key(family))
        if data is None:
            return []
        if (
            data.get("schema") != 1
            or data.get("family") != family
            or data.get("namespace") != self.namespace
            or not isinstance(data.get("worlds"), list)
        ):
            raise PolicyError("Incompatible training world record")
        for item in data["worlds"]:
            if _digest({"task": item["task"], "world": item["world"]}) != item["sha256"]:
                raise PolicyError("Saved training world integrity mismatch")
        return data["worlds"]

    async def _remember_world(self, family: str, task: Any, world: Any) -> None:
        worlds = await self._worlds(family)
        if any(item["world"]["tree"]["tree_id"] == world.tree.tree_id for item in worlds):
            return
        payload = {"task": task, "world": world_data(world)}
        worlds.append({**payload, "sha256": _digest(payload)})
        await self.store.save_checkpoint(
            self._world_key(family),
            {"schema": 1, "namespace": self.namespace, "family": family, "worlds": worlds},
        )

    async def _entry(self, family: str) -> dict | None:
        entry = await self.store.get_checkpoint(self._key(family))
        if entry is not None and (
            entry.get("schema") != 1
            or entry.get("family") != family
            or entry.get("namespace") != self.namespace
            or not isinstance(entry.get("versions"), list)
            or not isinstance(entry.get("active"), int)
            or not 0 <= entry["active"] < len(entry["versions"])
        ):
            raise PolicyError("Incompatible policy memory record")
        return entry

    async def _selected_version(
        self, family: str, task: Any | None = None
    ) -> tuple[Any, dict] | None:
        if not self.settings.reuse_policies:
            return None
        entry = await self._entry(family)
        if entry is None:
            return None
        # An active version may be unsuitable for this task while an earlier
        # version remains compatible. Never mutate the stored active pointer.
        for version in reversed(entry["versions"][: entry["active"] + 1]):
            if _digest(version["policy"]) != version["sha256"]:
                raise PolicyError("Saved policy integrity mismatch")
            policy = self.codec.decode(version["policy"])
            if task is None or await self._allowed(
                self.settings.accept_policy,
                task,
                policy,
                version.get("origin", "unknown"),
                version.get("raw_quality"),
            ):
                return policy, version
        return None

    async def load(self, family: str, *, task: Any | None = None) -> Any | None:
        """Decode a compatible policy; never mutate a stored version."""
        selected = await self._selected_version(family, task)
        return selected[0] if selected is not None else None

    async def remember(
        self,
        task: Any,
        policy: Any,
        *,
        origin: str = "external",
        raw_quality: float | None = None,
    ) -> bool:
        """Append a policy version with its origin. Earlier versions remain intact."""
        if origin not in ("external", "incumbent", "promoted"):
            raise ConfigurationError("Unknown policy origin")
        if raw_quality is not None and (
            isinstance(raw_quality, bool)
            or not isinstance(raw_quality, (int, float))
            or not math.isfinite(raw_quality)
        ):
            raise ConfigurationError("raw_quality must be finite when supplied")
        if not self.settings.save_policies:
            return False
        if not await self._allowed(self.settings.accept_policy, task, policy, origin, raw_quality):
            return False
        family = self._family(task)
        encoded = self.codec.encode(policy)
        digest = _digest(encoded)
        entry = await self._entry(family) or {
            "schema": 1,
            "namespace": self.namespace,
            "family": family,
            "versions": [],
            "active": 0,
        }
        if entry["versions"] and entry["versions"][entry["active"]]["sha256"] == digest:
            return False
        entry["versions"].append(
            {"policy": encoded, "sha256": digest, "origin": origin, "raw_quality": raw_quality}
        )
        entry["active"] = len(entry["versions"]) - 1
        await self.store.save_checkpoint(self._key(family), entry)
        return True

    async def run(self, task: Any) -> AdaptiveRun:
        """Reuse a recorded policy, then train only after observed degradation."""
        family = self._family(task)
        has_recorded_policy = await self._entry(family) is not None
        selected = await self._selected_version(family, task)
        policy = selected[0] if selected is not None else None
        origin = selected[1].get("origin", "unknown") if selected is not None else None
        runtime = await invoke(self.runtime_factory, task, policy)
        if not isinstance(runtime.validation, HoldoutPipeline) or getattr(
            runtime._method, "online", True
        ):
            raise ConfigurationError(
                "Adaptive runtime needs independent validation and an offline method"
            )
        if task_key(task) in {task_key(held) for held in runtime.validation.tasks}:
            raise ConfigurationError("Training task overlaps the validation partition")
        result = await runtime.run(task)
        quality = await invoke(self.raw_quality, task, result)
        floor = await invoke(self.minimum_quality, task)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in (quality, floor)
        ):
            raise ConfigurationError("Raw quality and minimum quality must be finite numbers")
        quality, floor = float(quality), float(floor)
        degraded = quality + 1e-9 < floor
        needs_training = policy is None or degraded
        may_train = not needs_training or await self._allowed(
            self.settings.allow_training, task, policy, quality, floor
        )
        promoted = False
        incumbent_saved = False
        improved = None
        imported = 0
        if needs_training and may_train and self.settings.reuse_worlds:
            for saved in await self._worlds(family):
                world = world_load(saved["world"])
                if await self._allowed(self.settings.accept_world, task, saved["task"], world):
                    await runtime.add_recorded_world(saved["task"], world)
                    imported += 1
        from dreamrsi.replay import ReplayWorld

        current_world = ReplayWorld(result.tree) if result.tree is not None else None
        accepted = current_world is not None and await self._allowed(
            self.settings.accept_world, task, task, current_world
        )
        if accepted:
            world = await runtime.record_world(task, result)
            if self.settings.save_worlds:
                await self._remember_world(family, task, world)
        if needs_training and may_train and (imported > 0 or accepted):
            await self._reserve_holdouts(family, runtime.validation)
            improved = await runtime.improve(task, rounds=1)
            challenger = improved.champion_policy
            if challenger is not None:
                await self.remember(task, challenger, origin="promoted")
                promoted = True
        # A failed search does not erase a working incumbent. It is reusable
        # on the next task, where raw quality is checked again before training.
        # This is a recorded incumbent, not a newly promoted challenger.
        if (
            not has_recorded_policy
            and not promoted
            and getattr(result, "best_score", None) is not None
            and quality + 1e-9 >= floor
        ):
            initial = getattr(runtime, "_get_policy", None)
            if callable(initial):
                incumbent_saved = await self.remember(
                    task, initial(), origin="incumbent", raw_quality=quality
                )
        return AdaptiveRun(
            result=result,
            improvement=improved,
            family=family,
            raw_quality=quality,
            reused_policy=policy is not None,
            trained=improved is not None,
            promoted=promoted,
            incumbent_saved=incumbent_saved,
            policy_origin=origin,
            quality_floor=floor,
            degraded=degraded,
            training_skipped=needs_training and not may_train,
        )

"""Reuse recorded policies across related tasks without restoring a campaign."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
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

    async def export_bundle(self, task: Any, path: str | Path) -> dict[str, Any]:
        """Write one portable JSON file containing a family's policies and replay trees."""
        family = self._family(task)
        entry = await self._entry(family)
        worlds = await self._worlds(family)
        versions = entry["versions"] if entry is not None else []
        if not versions and not worlds:
            raise ConfigurationError(f"No saved policies or replay trees for family {family!r}")

        payload = {
            "format": "dreamrsi.policy-bundle",
            "schema_version": 1,
            "family": family,
            "active_policy": entry["active"] if entry is not None else None,
            "policies": versions,
            "worlds": worlds,
        }
        bundle = {**payload, "sha256": _digest(payload)}
        target = Path(path).expanduser()
        temporary: str | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = stream.name
                json.dump(
                    bundle,
                    stream,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except (OSError, TypeError, ValueError) as exc:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            raise ConfigurationError(
                f"Could not write Dream-RSI bundle to {target}: {exc}"
            ) from exc
        return {
            "path": str(target),
            "family": family,
            "policies": len(versions),
            "worlds": len(worlds),
        }

    async def import_bundle(self, path: str | Path, *, task: Any) -> dict[str, Any]:
        """Validate and import a bundle into an empty policy family in this store.

        Re-importing the same bundle is safe. A bundle cannot silently replace a
        different local champion; use a fresh namespace to compare or adopt it.
        """
        family = self._family(task)
        target = Path(path).expanduser()
        try:
            bundle = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"Could not read Dream-RSI bundle at {target}: {exc}"
            ) from exc
        if not isinstance(bundle, dict):
            raise PolicyError("Dream-RSI bundle must contain a JSON object")
        checksum = bundle.pop("sha256", None)
        try:
            valid_checksum = isinstance(checksum, str) and _digest(bundle) == checksum
        except (TypeError, ValueError) as exc:
            raise PolicyError("Dream-RSI bundle contains invalid JSON values") from exc
        if not valid_checksum:
            raise PolicyError("Dream-RSI bundle integrity check failed")
        if bundle.get("format") != "dreamrsi.policy-bundle" or bundle.get("schema_version") != 1:
            raise PolicyError("Unsupported Dream-RSI bundle format or schema")
        if bundle.get("family") != family:
            raise ConfigurationError(
                f"Bundle family {bundle.get('family')!r} does not match task family {family!r}"
            )

        versions = bundle.get("policies")
        worlds = bundle.get("worlds")
        active = bundle.get("active_policy")
        if not isinstance(versions, list) or not isinstance(worlds, list):
            raise PolicyError("Dream-RSI bundle policies and worlds must be lists")
        if not versions and not worlds:
            raise PolicyError("Dream-RSI bundle is empty")
        if versions and not self.settings.save_policies:
            raise ConfigurationError("Enable save_policies to import policy versions")
        if worlds and not self.settings.save_worlds:
            raise ConfigurationError("Enable save_worlds to import replay trees")
        if versions:
            if type(active) is not int or not 0 <= active < len(versions):
                raise PolicyError("Dream-RSI bundle has an invalid active policy index")
        elif active is not None:
            raise PolicyError("An empty policy list cannot have an active policy")

        for version in versions:
            if not isinstance(version, dict) or not isinstance(version.get("policy"), dict):
                raise PolicyError("Invalid policy version in Dream-RSI bundle")
            if _digest(version["policy"]) != version.get("sha256"):
                raise PolicyError("Policy version integrity check failed")
            raw_quality = version.get("raw_quality")
            if raw_quality is not None and (
                isinstance(raw_quality, bool)
                or not isinstance(raw_quality, (int, float))
                or not math.isfinite(raw_quality)
            ):
                raise PolicyError("Policy bundle contains invalid raw quality")
            try:
                self.codec.decode(version["policy"])
            except Exception as exc:
                raise PolicyError(f"Could not load bundled policy: {exc}") from exc

        validated_worlds = []
        seen_trees: set[str] = set()
        for item in worlds:
            if not isinstance(item, dict) or not {"task", "world", "sha256"}.issubset(item):
                raise PolicyError("Invalid replay world in Dream-RSI bundle")
            payload = {"task": item["task"], "world": item["world"]}
            if _digest(payload) != item["sha256"]:
                raise PolicyError("Replay world integrity check failed")
            try:
                task_key(item["task"])
                world = world_load(item["world"])
            except Exception as exc:
                raise PolicyError(f"Could not load bundled replay tree: {exc}") from exc
            tree_id = world.tree.tree_id
            if tree_id in seen_trees:
                raise PolicyError("Dream-RSI bundle contains duplicate replay trees")
            seen_trees.add(tree_id)
            if await self._allowed(self.settings.accept_world, task, item["task"], world):
                validated_worlds.append(item)

        existing = await self._entry(family)
        if versions and existing is not None and existing["versions"]:
            existing_hashes = [version["sha256"] for version in existing["versions"]]
            bundle_hashes = [version["sha256"] for version in versions]
            if existing_hashes != bundle_hashes or existing["active"] != active:
                raise ConfigurationError(
                    "This task family already has different policies; import into a fresh "
                    "policy-memory namespace to avoid replacing its champion"
                )

        current_worlds = await self._worlds(family)
        current_tree_ids = {item["world"]["tree"]["tree_id"] for item in current_worlds}
        new_worlds = [
            item
            for item in validated_worlds
            if item["world"]["tree"]["tree_id"] not in current_tree_ids
        ]
        if new_worlds and self.settings.save_worlds:
            combined = current_worlds + new_worlds
            await self.store.save_checkpoint(
                self._world_key(family),
                {"schema": 1, "namespace": self.namespace, "family": family, "worlds": combined},
            )
        added_policies = 0
        if versions and self.settings.save_policies and existing is None:
            await self.store.save_checkpoint(
                self._key(family),
                {
                    "schema": 1,
                    "namespace": self.namespace,
                    "family": family,
                    "versions": versions,
                    "active": active,
                },
            )
            added_policies = len(versions)
        return {
            "family": family,
            "policies": added_policies,
            "worlds": len(new_worlds) if self.settings.save_worlds else 0,
        }

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

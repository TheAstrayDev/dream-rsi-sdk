"""Versioned JSON campaign state. External side effects are never replayed implicitly."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

from dreamrsi.discovery import DiscoveryTree
from dreamrsi.errors import ConfigurationError
from dreamrsi.replay import ReplayWorld
from dreamrsi.validation import task_key


def world_data(world):
    return {"world_id": world.world_id, "tree": world.tree.to_dict()}


def world_load(data):
    return ReplayWorld(DiscoveryTree.from_dict(data["tree"]), data["world_id"])


async def save(runtime, campaign_id, task, completed_rounds, phase="ready"):
    codec = runtime.policy_codec
    validation = runtime.validation
    optimizer = runtime._get_optimizer()
    data = {
        "schema": 1,
        "configuration": configuration(runtime),
        "phase": phase,
        "method_online": getattr(runtime._method, "online", True),
        "method_force_developer": getattr(runtime._method, "force_developer", False),
        "task_key": task_key(task),
        "completed_rounds": completed_rounds,
        "policy": codec.encode(runtime._get_policy()),
        "champion": codec.encode(runtime._champion_policy) if runtime._champion_policy else None,
        "policy_history": [codec.encode(p) for p in runtime._policy_history],
        "worlds": [world_data(w) for w in runtime._worlds],
        "frozen": runtime._frozen,
        "usage": runtime.usage.to_dict(),
        "developer_history": getattr(optimizer, "history", []),
        "validation": None
        if validation is None
        else {
            "task_keys": [task_key(t) for t in validation.tasks],
            "worlds": [world_data(w) for w in validation.worlds],
            "used": validation.used,
            "prepared": validation.prepared,
        },
    }
    await runtime._store.save_checkpoint(campaign_id, data)


async def restore(runtime, campaign_id, task):
    data = await runtime._store.get_checkpoint(campaign_id)
    if not data or data["schema"] != 1 or data["task_key"] != task_key(task):
        raise ConfigurationError("Missing, incompatible or wrong-task campaign checkpoint")
    if data.get("method_online", True) != getattr(runtime._method, "online", True):
        raise ConfigurationError("Campaign online/offline method changed on resume")
    if data.get("method_force_developer", False) != getattr(
        runtime._method, "force_developer", False
    ):
        raise ConfigurationError("Campaign developer mode changed on resume")
    if data.get("configuration") != configuration(runtime):
        raise ConfigurationError("Campaign configuration changed on resume")
    codec = runtime.policy_codec
    runtime._policy = codec.decode(data["policy"])
    runtime._champion_policy = codec.decode(data["champion"]) if data["champion"] else None
    runtime._policy_history = [codec.decode(p) for p in data["policy_history"]]
    runtime._worlds = [world_load(w) for w in data["worlds"]]
    runtime._frozen = data["frozen"]
    meter = await runtime._store.get_checkpoint(campaign_id + ":usage")
    runtime.usage.restore(meter if meter is not None else data["usage"])
    optimizer = runtime._get_optimizer()
    if hasattr(optimizer, "history"):
        journal = await runtime._store.get_checkpoint(campaign_id + ":developer")
        optimizer.history = journal["history"] if journal else data["developer_history"]
    held = data["validation"]
    if (held is None) != (runtime.validation is None):
        raise ConfigurationError("Resume requires the same validation configuration")
    if held is not None:
        validation = runtime.validation
        if held["task_keys"] != [task_key(t) for t in validation.tasks]:
            raise ConfigurationError("Validation partition changed on resume")
        validation.worlds = [world_load(w) for w in held["worlds"]]
        validation.used, validation.prepared = held["used"], held["prepared"]
    return data["completed_rounds"], data.get("phase", "ready")


def configuration(runtime):
    optimizer = runtime._get_optimizer()
    replay = runtime._get_replay()
    developer_config = getattr(optimizer, "config", None)
    sandbox = runtime.policy_codec.sandbox
    return {
        "experiment_version": runtime.experiment_version,
        "config": asdict(runtime._config),
        "budget": runtime._budget.to_dict() if runtime._budget else None,
        "campaign_budget": runtime.usage.budget.to_dict() if runtime.usage.budget else None,
        "usage_limits": {key: asdict(value) for key, value in runtime._usage_limits.items()},
        "objective": type(runtime._objective).__qualname__,
        "replay": type(runtime._get_replay()).__qualname__,
        "replay_settings": replay.checkpoint_config()
        if callable(getattr(replay, "checkpoint_config", None))
        else None,
        "optimizer": type(runtime._get_optimizer()).__qualname__,
        "developer_config": asdict(developer_config)
        if is_dataclass(developer_config) and not isinstance(developer_config, type)
        else None,
        "sandbox": sandbox.capabilities()
        if hasattr(sandbox, "capabilities")
        else type(sandbox).__qualname__,
        "validation_batch": runtime.validation.worlds_per_check if runtime.validation else None,
    }

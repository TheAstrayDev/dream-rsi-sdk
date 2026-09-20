from __future__ import annotations

import dataclasses
import enum
import time
import uuid
from typing import Any, Self


class ReplayOutcomeSource(enum.StrEnum):
    RECORDED = "RECORDED"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"


class WorldSplit(enum.StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


@dataclasses.dataclass
class ReplayWorldRecord:
    tree_id: str
    split: WorldSplit = WorldSplit.TRAIN
    created_at: float = dataclasses.field(default_factory=time.time)
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["split"] = self.split.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        d = data.copy()
        if "split" in d:
            d["split"] = WorldSplit(d["split"])
        return cls(**{k: v for k, v in d.items() if k != "_schema_version"})


@dataclasses.dataclass
class ReplayStep:
    round_number: int
    batch: list[str]
    revealed_nodes: list[str]
    best_score_so_far: float | None
    probes_so_far: int
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(**{k: v for k, v in data.items() if k != "_schema_version"})


@dataclasses.dataclass
class ReplayTrajectory:
    world_id: str
    policy_id: str
    steps: list[ReplayStep] = dataclasses.field(default_factory=list)
    revealed_node_ids: list[str] = dataclasses.field(default_factory=list)
    best_score: float | None = None
    total_probes: int = 0
    total_rounds: int = 0
    replay_score: float | None = None
    source: ReplayOutcomeSource = ReplayOutcomeSource.RECORDED
    completed: bool = False
    elapsed_ms: float = 0.0
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["steps"] = [step.to_dict() for step in self.steps]
        d["source"] = self.source.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        d = data.copy()
        if "steps" in d:
            d["steps"] = [ReplayStep.from_dict(s) for s in d["steps"]]
        if "source" in d:
            d["source"] = ReplayOutcomeSource(d["source"])
        return cls(**{k: v for k, v in d.items() if k != "_schema_version"})


def __getattr__(name):
    if name == "ReplayWorld":
        from dreamrsi.replay import ReplayWorld

        return ReplayWorld
    raise AttributeError(name)

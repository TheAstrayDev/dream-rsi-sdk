from __future__ import annotations

import dataclasses
import enum
import uuid
from typing import Any, Self


class RunStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RoundPhase(enum.StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


@dataclasses.dataclass
class Task:
    description: str = ""
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(**{k: v for k, v in data.items() if k != "_schema_version"})


@dataclasses.dataclass
class Run:
    task_id: str
    tree_id: str
    policy_id: str
    round_number: int = 0
    status: RunStatus = RunStatus.PENDING
    started_at: float | None = None
    completed_at: float | None = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        d = data.copy()
        if "status" in d:
            d["status"] = RunStatus(d["status"])
        return cls(**{k: v for k, v in d.items() if k != "_schema_version"})


@dataclasses.dataclass
class Round:
    run_id: str
    cycle_id: str
    round_number: int = 0
    phase: RoundPhase = RoundPhase.ONLINE
    status: RunStatus = RunStatus.PENDING
    started_at: float | None = None
    completed_at: float | None = None
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["phase"] = self.phase.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        d = data.copy()
        if "phase" in d:
            d["phase"] = RoundPhase(d["phase"])
        if "status" in d:
            d["status"] = RunStatus(d["status"])
        return cls(**{k: v for k, v in d.items() if k != "_schema_version"})


@dataclasses.dataclass
class DreamCycle:
    task_id: str
    total_rounds: int = 0
    completed_rounds: int = 0
    status: RunStatus = RunStatus.PENDING
    champion_policy_id: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        d = data.copy()
        if "status" in d:
            d["status"] = RunStatus(d["status"])
        return cls(**{k: v for k, v in d.items() if k != "_schema_version"})


@dataclasses.dataclass
class CostRecord:
    model_calls: int = 0
    evaluator_calls: int = 0
    online_agent_cost: float = 0.0
    online_evaluator_cost: float = 0.0
    policy_generation_cost: float = 0.0
    validation_cost: float = 0.0
    replay_compute_ms: float = 0.0
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    @property
    def total(self) -> float:
        return (
            self.online_agent_cost
            + self.online_evaluator_cost
            + self.policy_generation_cost
            + self.validation_cost
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(**{k: v for k, v in data.items() if k != "_schema_version"})

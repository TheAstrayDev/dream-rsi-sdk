from __future__ import annotations

import dataclasses
import enum
import time
import uuid
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from .budget import Budget
    from .discovery import NodeStatus


class PolicyDeploymentStatus(enum.StrEnum):
    CANDIDATE = "CANDIDATE"
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


@dataclasses.dataclass
class PolicyVersion:
    parent_id: str | None = None
    name: str = ""
    source: str = "builtin"
    source_hash: str = ""
    created_at: float = dataclasses.field(default_factory=time.time)
    creation_method: str = "manual"
    replay_scores: dict[str, float] = dataclasses.field(default_factory=dict)
    validation_scores: dict[str, float] = dataclasses.field(default_factory=dict)
    deployment_status: PolicyDeploymentStatus = PolicyDeploymentStatus.CANDIDATE
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["deployment_status"] = self.deployment_status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        d = data.copy()
        if "deployment_status" in d:
            d["deployment_status"] = PolicyDeploymentStatus(d["deployment_status"])
        return cls(**{k: v for k, v in d.items() if k != "_schema_version"})


@dataclasses.dataclass(frozen=True)
class PolicyDecision:
    expand: list[str]
    parallelism: int | None = None
    stop: bool = False
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(**{k: v for k, v in data.items() if k != "_schema_version"})


@dataclasses.dataclass(frozen=True)
class NodeSummary:
    id: str
    parent_id: str | None
    depth: int
    score: float | None
    status: NodeStatus
    children_count: int
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        from .discovery import NodeStatus

        d = data.copy()
        if "status" in d:
            d["status"] = NodeStatus(d["status"])
        return cls(**{k: v for k, v in d.items() if k != "_schema_version"})


@dataclasses.dataclass(frozen=True)
class PolicyView:
    frontier: list[NodeSummary]
    best_score: float | None
    total_nodes: int
    calls_used: int
    cost_used: float
    rounds_used: int
    observations: dict[str, Any] = dataclasses.field(default_factory=dict)
    history: list[NodeSummary] = dataclasses.field(default_factory=list)
    budget_remaining: Budget | None = None
    tree_id: str = ""
    round_number: int = 0
    max_parallelism: int = 1
    last_round: dict[str, Any] | None = None
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["frontier"] = [node.to_dict() for node in self.frontier]
        d["history"] = [node.to_dict() for node in self.history]
        if self.budget_remaining is not None:
            d["budget_remaining"] = self.budget_remaining.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        from .budget import Budget

        d = data.copy()
        if "history" in d:
            d["history"] = [NodeSummary.from_dict(n) for n in d["history"]]
        if "frontier" in d:
            d["frontier"] = [NodeSummary.from_dict(n) for n in d["frontier"]]
        if d.get("budget_remaining"):
            d["budget_remaining"] = Budget.from_dict(d["budget_remaining"])
        return cls(**{k: v for k, v in d.items() if k != "_schema_version"})

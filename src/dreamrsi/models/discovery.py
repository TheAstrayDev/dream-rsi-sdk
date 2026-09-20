from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeStatus(Enum):
    """Lifecycle status of a discovery node."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DiscoveryNode:
    """A single node in the discovery tree.

    Each node represents one generation→evaluation attempt.  The root
    node holds the initial workspace state.  Non-root nodes have exactly
    one parent and inherit context from it.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tree_id: str = ""
    parent_id: str | None = None
    depth: int = 0
    state: Any = None
    proposal: Any = None
    action: Any = None
    observation: Any = None
    score: float | None = None
    status: NodeStatus = NodeStatus.PENDING
    cost: float = 0.0
    latency_ms: float = 0.0
    created_at: float = field(default_factory=time.time)
    children_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Creation order within the tree (used by replay for root-child ordering)
    creation_order: int = 0

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def is_leaf(self) -> bool:
        return len(self.children_ids) == 0

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "tree_id": self.tree_id,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "state": self.state,
            "proposal": self.proposal,
            "action": self.action,
            "observation": self.observation,
            "score": self.score,
            "status": self.status.value,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
            "children_ids": list(self.children_ids),
            "creation_order": self.creation_order,
            "metadata": dict(self.metadata),
            "_schema_version": "1",
        }
        return copy.deepcopy(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryNode:
        data = copy.deepcopy(data)
        return cls(
            id=data["id"],
            tree_id=data.get("tree_id", ""),
            parent_id=data.get("parent_id"),
            depth=data.get("depth", 0),
            state=data.get("state"),
            proposal=data.get("proposal"),
            action=data.get("action"),
            observation=data.get("observation"),
            score=data.get("score"),
            status=NodeStatus(data.get("status", "pending")),
            cost=data.get("cost", 0.0),
            latency_ms=data.get("latency_ms", 0.0),
            created_at=data.get("created_at", 0.0),
            children_ids=list(data.get("children_ids", [])),
            creation_order=data.get("creation_order", 0),
            metadata=dict(data.get("metadata", {})),
        )

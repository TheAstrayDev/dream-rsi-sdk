from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(Enum):
    """All event types emitted by the Dream-RSI runtime."""

    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    NODE_CREATED = "node_created"
    NODE_EVALUATED = "node_evaluated"
    ROUND_COMPLETED = "round_completed"
    WORLD_CREATED = "world_created"
    DREAM_STARTED = "dream_started"
    DREAM_COMPLETED = "dream_completed"
    POLICY_CREATED = "policy_created"
    POLICY_PROMOTED = "policy_promoted"
    POLICY_REJECTED = "policy_rejected"
    POLICY_ROLLED_BACK = "policy_rolled_back"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CAMPAIGN_STARTED = "campaign_started"
    CAMPAIGN_COMPLETED = "campaign_completed"
    ERROR = "error"


@dataclass
class Event:
    """A typed event from the Dream-RSI runtime."""

    type: EventType
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    round_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "timestamp": self.timestamp,
            "data": dict(self.data),
            "run_id": self.run_id,
            "round_number": self.round_number,
        }

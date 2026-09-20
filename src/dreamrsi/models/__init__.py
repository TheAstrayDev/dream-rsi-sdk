from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dreamrsi.replay import ReplayWorld

from .base import CostRecord, DreamCycle, Round, RoundPhase, Run, RunStatus, Task
from .budget import Budget
from .discovery import DiscoveryNode, NodeStatus
from .evaluation import Evaluation, EvaluationStatus
from .events import Event, EventType
from .objectives import ObjectiveResult
from .policy import NodeSummary, PolicyDecision, PolicyDeploymentStatus, PolicyVersion, PolicyView
from .promotion import PromotionDecision, PromotionOutcome
from .replay import (
    ReplayOutcomeSource,
    ReplayStep,
    ReplayTrajectory,
    ReplayWorldRecord,
    WorldSplit,
)
from .results import CampaignResult, RunResult

__all__ = [
    "Task",
    "Run",
    "Round",
    "DreamCycle",
    "CostRecord",
    "RunStatus",
    "RoundPhase",
    "NodeStatus",
    "DiscoveryNode",
    "EvaluationStatus",
    "Evaluation",
    "PolicyDeploymentStatus",
    "PolicyVersion",
    "PolicyDecision",
    "NodeSummary",
    "PolicyView",
    "ReplayWorldRecord",
    "ReplayOutcomeSource",
    "ReplayWorld",
    "WorldSplit",
    "ReplayStep",
    "ReplayTrajectory",
    "PromotionOutcome",
    "PromotionDecision",
    "Budget",
    "EventType",
    "Event",
    "ObjectiveResult",
    "RunResult",
    "CampaignResult",
]


def __getattr__(name):
    if name == "ReplayWorld":
        from dreamrsi.replay import ReplayWorld

        return ReplayWorld
    raise AttributeError(name)

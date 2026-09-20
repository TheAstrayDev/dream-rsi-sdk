from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .base import CostRecord

if TYPE_CHECKING:
    from dreamrsi.discovery import DiscoveryTree
    from dreamrsi.replay import ReplayWorld


@dataclass
class RunResult:
    """Result of a DreamRSI run or improvement campaign."""

    run_id: str = ""
    best: Any = None
    best_score: float | None = None
    best_node_id: str | None = None
    tree: DiscoveryTree | None = None
    policy: Any = None
    champion_policy: Any = None
    rounds: int = 0
    costs: CostRecord = field(default_factory=CostRecord)
    metrics: dict[str, Any] = field(default_factory=dict)
    policy_history: list[Any] = field(default_factory=list)
    worlds: list[ReplayWorld] = field(default_factory=list)


@dataclass
class CampaignResult:
    """Result of a multi-task campaign."""

    campaign_id: str = ""
    best_score: float | None = None
    champion: Any = None
    task_results: list[RunResult] = field(default_factory=list)
    policy_history: list[Any] = field(default_factory=list)
    worlds: list[ReplayWorld] = field(default_factory=list)

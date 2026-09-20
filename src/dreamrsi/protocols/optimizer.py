from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dreamrsi.models.budget import Budget
    from dreamrsi.models.replay import ReplayTrajectory
    from dreamrsi.protocols.policy import ExplorationPolicy


@runtime_checkable
class PolicyOptimizer(Protocol):
    """Protocol for generating improved exploration policies."""

    async def generate(
        self,
        incumbent: ExplorationPolicy,
        evidence: list[ReplayTrajectory],
        budget: Budget | None = None,
    ) -> list[ExplorationPolicy]:
        """Generate challenger policies based on replay evidence."""
        ...

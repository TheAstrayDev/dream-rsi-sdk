from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dreamrsi.models.objectives import ObjectiveResult
    from dreamrsi.models.replay import ReplayTrajectory


@runtime_checkable
class Objective(Protocol):
    """Protocol for scoring exploration trajectories."""

    def score(
        self, trajectory: ReplayTrajectory, context: dict[str, Any] | None = None
    ) -> ObjectiveResult: ...

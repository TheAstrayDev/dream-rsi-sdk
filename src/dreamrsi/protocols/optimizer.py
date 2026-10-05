from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

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


@runtime_checkable
class PolicyDeveloper(Protocol):
    """Iteratively revise executable policies using measured training feedback.

    ``evaluate`` replays a candidate on the fixed training pool; it must not
    expose held-out worlds. ``charge`` accounts for model requests and
    ``persist`` journals revision history before external work. A developer
    that supports resumable sessions advertises ``supports_sessions = True``.
    No inheritance from an SDK implementation is required.
    """

    async def develop(
        self,
        incumbent: ExplorationPolicy,
        trajectories: list[ReplayTrajectory],
        evaluate: Callable[[ExplorationPolicy], Awaitable[list[ReplayTrajectory]]],
        budget: Budget | None = None,
        charge: Callable[..., Awaitable[Any]] | None = None,
        persist: Callable[[list[dict[str, Any]]], Awaitable[None]] | None = None,
        session_id: str | None = None,
    ) -> list[ExplorationPolicy]:
        """Return measured revisions; selection and promotion remain separate."""
        ...

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dreamrsi.models.policy import PolicyDecision, PolicyView


@runtime_checkable
class ExplorationPolicy(Protocol):
    """Protocol for exploration policies that guide the discovery process.

    The policy observes the current state of the discovery tree (via PolicyView)
    and decides which nodes to expand next.
    """

    async def decide(self, view: PolicyView) -> PolicyDecision:
        """Given the current view of the discovery tree, decide what to explore next."""
        ...

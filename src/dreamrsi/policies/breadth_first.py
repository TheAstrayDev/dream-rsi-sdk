"""Breadth-first policy for Dream-RSI."""

from dreamrsi.replay import PolicyDecision, PolicyView


class BreadthFirstPolicy:
    """Expands all eligible nodes at the shallowest depth first."""

    def __init__(self, batch_size: int = 1):
        self._batch_size = batch_size

    async def decide(self, view: PolicyView) -> PolicyDecision:
        if not view.frontier:
            return PolicyDecision(expand=[], stop=True)

        # Sort by depth ascending
        sorted_frontier = sorted(view.frontier, key=lambda n: n.depth)
        to_expand = [n.id for n in sorted_frontier[: self._batch_size]]

        return PolicyDecision(expand=to_expand, stop=False)

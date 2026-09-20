"""Greedy policy for Dream-RSI."""

from dreamrsi.replay import PolicyDecision, PolicyView


class GreedyPolicy:
    """Always expands the leaf with the highest score. If no scored leaves, picks randomly."""

    def __init__(self, batch_size: int = 1):
        self._batch_size = batch_size

    async def decide(self, view: PolicyView) -> PolicyDecision:
        if not view.frontier:
            return PolicyDecision(expand=[], stop=True)

        # Separate nodes with and without scores
        scored = [n for n in view.frontier if n.score is not None]
        unscored = [n for n in view.frontier if n.score is None]

        # Sort scored nodes by score descending
        scored.sort(key=lambda n: n.score if n.score is not None else float("-inf"), reverse=True)

        # Randomize unscored nodes
        # Preserve creation order for deterministic ties.

        candidates = scored + unscored
        to_expand = [n.id for n in candidates[: self._batch_size]]

        return PolicyDecision(expand=to_expand, stop=False)

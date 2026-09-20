"""Random policy for Dream-RSI."""

import random

from dreamrsi.replay import PolicyDecision, PolicyView


class RandomPolicy:
    """Picks random eligible nodes."""

    def __init__(self, seed: int | None = None, batch_size: int = 1):
        self._rng = random.Random(seed)
        self._batch_size = batch_size

    async def decide(self, view: PolicyView) -> PolicyDecision:
        if not view.frontier:
            return PolicyDecision(expand=[], stop=True)

        candidates = list(view.frontier)
        self._rng.shuffle(candidates)
        to_expand = [n.id for n in candidates[: self._batch_size]]

        return PolicyDecision(expand=to_expand, stop=False)

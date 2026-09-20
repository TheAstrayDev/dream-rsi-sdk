"""Epsilon-greedy policy for Dream-RSI."""

import random

from dreamrsi.replay import PolicyDecision, PolicyView


class EpsilonGreedyPolicy:
    """With probability epsilon picks random, otherwise picks best-scoring."""

    def __init__(self, epsilon: float = 0.1, batch_size: int = 1, seed: int | None = None):
        self._epsilon = epsilon
        self._batch_size = batch_size
        self._rng = random.Random(seed)

    async def decide(self, view: PolicyView) -> PolicyDecision:
        if not view.frontier:
            return PolicyDecision(expand=[], stop=True)

        candidates = list(view.frontier)

        to_expand = []
        for _ in range(self._batch_size):
            if not candidates:
                break

            if self._rng.random() < self._epsilon:
                # Random choice
                chosen = self._rng.choice(candidates)
            else:
                # Greedy choice
                scored = [n for n in candidates if n.score is not None]
                if scored:
                    chosen = max(
                        scored, key=lambda n: n.score if n.score is not None else float("-inf")
                    )
                else:
                    chosen = self._rng.choice(candidates)

            to_expand.append(chosen.id)
            candidates.remove(chosen)

        return PolicyDecision(expand=to_expand, stop=False)

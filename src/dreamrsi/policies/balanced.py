"""Balanced policy for Dream-RSI."""

import math

from dreamrsi.replay import PolicyDecision, PolicyView


class BalancedPolicy:
    """UCB1-inspired policy. Balances exploitation with exploration."""

    def __init__(self, exploration_coeff: float = 1.41, batch_size: int = 4):
        self._exploration_coeff = exploration_coeff
        self._batch_size = batch_size

    async def decide(self, view: PolicyView) -> PolicyDecision:
        if not view.frontier:
            return PolicyDecision(expand=[], stop=True)

        total_visits = sum((n.children_count + 1) for n in view.frontier)
        if total_visits == 0:
            total_visits = 1

        def ucb_score(node):
            score = node.score if node.score is not None else (view.best_score or 0.0)
            visits = (node.children_count + 1) if (node.children_count + 1) > 0 else 1
            exploration_term = self._exploration_coeff * math.sqrt(math.log(total_visits) / visits)
            return score + exploration_term

        sorted_frontier = sorted(view.frontier, key=ucb_score, reverse=True)
        to_expand = [n.id for n in sorted_frontier[: self._batch_size]]

        return PolicyDecision(expand=to_expand, stop=False)

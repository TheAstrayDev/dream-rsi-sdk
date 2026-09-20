"""Evidence gates: missing evidence never counts as a zero score."""

from __future__ import annotations

import math

from dreamrsi.models.promotion import PromotionDecision, PromotionOutcome


class ReplayOnlyGate:
    def __init__(self, min_improvement: float = 0.0):
        if not math.isfinite(min_improvement) or min_improvement < 0:
            raise ValueError("min_improvement must be finite and nonnegative")
        self._min_improvement = min_improvement

    def _scores(self, evidence):
        return evidence.get("incumbent_avg_score"), evidence.get("challenger_avg_score")

    async def evaluate(self, incumbent, challenger, evidence):
        inc, chl = self._scores(evidence)
        outcome = PromotionOutcome.INSUFFICIENT_EVIDENCE
        reason = "Both finite scores are required"
        if all(isinstance(v, (float, int)) and math.isfinite(v) for v in (inc, chl)):
            improvement = chl - inc
            outcome = (
                PromotionOutcome.PROMOTED
                if improvement > self._min_improvement
                else PromotionOutcome.REJECTED
            )
            reason = f"Improvement {improvement}; required > {self._min_improvement}"
        return PromotionDecision(
            incumbent_id=incumbent.id,
            challenger_id=challenger.id,
            outcome=outcome,
            reason=reason,
            evidence=evidence,
        )


class HoldoutGate(ReplayOnlyGate):
    """Requires independent validation scores supplied by the caller."""

    def _scores(self, evidence):
        scores = evidence.get("validation_scores", {})
        return scores.get("incumbent"), scores.get("challenger")


class CompositeGate:
    def __init__(self, gates):
        if not gates:
            raise ValueError("At least one gate is required")
        self._gates = gates

    async def evaluate(self, incumbent, challenger, evidence):
        reasons = []
        for gate in self._gates:
            decision = await gate.evaluate(incumbent, challenger, evidence)
            reasons.append(decision.reason)
            if decision.outcome != PromotionOutcome.PROMOTED:
                return decision
        return PromotionDecision(
            incumbent_id=incumbent.id,
            challenger_id=challenger.id,
            outcome=PromotionOutcome.PROMOTED,
            reason="; ".join(reasons),
            evidence=evidence,
        )

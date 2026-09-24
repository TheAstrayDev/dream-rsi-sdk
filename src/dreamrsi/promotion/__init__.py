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


class RawQualityGate:
    """Reject raw-quality losses on held-out worlds.

    HoldoutPipeline reports a task-defined ``raw_quality`` when configured.
    Older evidence without that field retains its best-score semantics.
    """

    def __init__(self, tolerance: float = 0.0):
        if (
            isinstance(tolerance, bool)
            or not isinstance(tolerance, (int, float))
            or not math.isfinite(tolerance)
            or tolerance < 0
        ):
            raise ValueError("tolerance must be finite and nonnegative")
        self._tolerance = tolerance

    async def evaluate(self, incumbent, challenger, evidence):
        reports = evidence.get("validation_reports")
        qualities: dict[str, dict[str, float]] = {"incumbent": {}, "challenger": {}}
        reason = "Paired finite raw qualities are required for every validation world"
        outcome = PromotionOutcome.INSUFFICIENT_EVIDENCE

        if isinstance(reports, list) and reports:
            valid = True
            for record in reports:
                if not isinstance(record, dict):
                    valid = False
                    break
                role, world_id, quality = (
                    record.get("role"),
                    record.get("world_id"),
                    record["raw_quality"]
                    if "raw_quality" in record
                    else record.get("best_score"),
                )
                if (
                    not isinstance(role, str)
                    or role not in qualities
                    or not isinstance(world_id, str)
                    or not world_id
                    or world_id in qualities[role]
                    or isinstance(quality, bool)
                    or not isinstance(quality, (int, float))
                    or not math.isfinite(quality)
                ):
                    valid = False
                    break
                qualities[role][world_id] = quality

            world_ids = set(qualities["incumbent"])
            expected = evidence.get("validation_world_ids")
            if expected is not None and (
                not isinstance(expected, list)
                or not all(isinstance(world_id, str) and world_id for world_id in expected)
                or len(expected) != len(set(expected))
                or set(expected) != world_ids
            ):
                valid = False
            if valid and world_ids and world_ids == set(qualities["challenger"]):
                degraded = next(
                    (
                        world_id
                        for world_id in sorted(world_ids)
                        if qualities["challenger"][world_id] + self._tolerance
                        < qualities["incumbent"][world_id]
                    ),
                    None,
                )
                if degraded is None:
                    outcome = PromotionOutcome.PROMOTED
                    reason = f"Raw quality loss <= {self._tolerance} on all validation worlds"
                else:
                    outcome = PromotionOutcome.REJECTED
                    reason = f"Raw quality loss exceeds {self._tolerance} on world {degraded}"

        return PromotionDecision(
            incumbent_id=incumbent.id,
            challenger_id=challenger.id,
            outcome=outcome,
            reason=reason,
            evidence=evidence,
        )


class CostQualityGate:
    """Promote only a quality-safe policy with fewer attempts or better quality.

    Paired validation reports take precedence over training reports. A failed
    or exhausted validation batch cannot be bypassed with training evidence.
    Older reports without attempted_expansions retain their probe semantics.
    """

    def __init__(self, min_quality_improvement: float = 0.0):
        if (
            isinstance(min_quality_improvement, bool)
            or not isinstance(min_quality_improvement, (int, float))
            or not math.isfinite(min_quality_improvement)
            or min_quality_improvement < 0
        ):
            raise ValueError("min_quality_improvement must be finite and nonnegative")
        self._min_quality_improvement = min_quality_improvement

    async def evaluate(self, incumbent, challenger, evidence):
        validating = "validation_status" in evidence or "validation_reports" in evidence
        reports = evidence.get("validation_reports" if validating else "training_reports")
        expected = evidence.get(
            "validation_world_ids" if validating else "training_world_ids"
        )
        paired: dict[str, dict[str, tuple[float, int]]] = {
            "incumbent": {},
            "challenger": {},
        }
        valid = isinstance(reports, list) and bool(reports)
        if validating and evidence.get("validation_status") != "evaluated":
            valid = False
        if valid:
            for record in reports:
                if not isinstance(record, dict):
                    valid = False
                    break
                role = record.get("role")
                world_id = record.get("world_id")
                quality = (
                    record["raw_quality"]
                    if "raw_quality" in record
                    else record.get("best_score")
                )
                probes = record.get("probes")
                attempts = record.get("attempted_expansions", probes)
                if (
                    not isinstance(role, str)
                    or role not in paired
                    or not isinstance(world_id, str)
                    or not world_id
                    or world_id in paired[role]
                    or isinstance(quality, bool)
                    or not isinstance(quality, (int, float))
                    or not math.isfinite(quality)
                    or isinstance(probes, bool)
                    or not isinstance(probes, int)
                    or probes < 0
                    or isinstance(attempts, bool)
                    or not isinstance(attempts, int)
                    or attempts < probes
                ):
                    valid = False
                    break
                paired[role][world_id] = (float(quality), attempts)
        world_ids = set(paired["incumbent"])
        if expected is not None and (
            not isinstance(expected, list)
            or not all(isinstance(world_id, str) and world_id for world_id in expected)
            or len(expected) != len(set(expected))
            or set(expected) != world_ids
        ):
            valid = False
        valid = valid and bool(world_ids) and world_ids == set(paired["challenger"])

        outcome = PromotionOutcome.INSUFFICIENT_EVIDENCE
        reason = "Complete paired raw quality and attempt counts are required"
        if valid:
            degraded = next(
                (
                    world_id
                    for world_id in sorted(world_ids)
                    if paired["challenger"][world_id][0]
                    < paired["incumbent"][world_id][0]
                ),
                None,
            )
            incumbent_attempts = sum(value[1] for value in paired["incumbent"].values())
            challenger_attempts = sum(value[1] for value in paired["challenger"].values())
            mean_quality_gain = sum(
                paired["challenger"][world_id][0]
                - paired["incumbent"][world_id][0]
                for world_id in world_ids
            ) / len(world_ids)
            if degraded is not None:
                outcome = PromotionOutcome.REJECTED
                reason = f"Raw quality declined on world {degraded}"
            elif challenger_attempts < incumbent_attempts or (
                challenger_attempts == incumbent_attempts
                and mean_quality_gain > self._min_quality_improvement
            ):
                outcome = PromotionOutcome.PROMOTED
                reason = (
                    f"Attempts {incumbent_attempts} -> {challenger_attempts}; "
                    f"raw quality nondecreasing on {len(world_ids)} worlds"
                )
            else:
                outcome = PromotionOutcome.REJECTED
                reason = "No strict attempt saving or quality gain at the same attempt count"

        return PromotionDecision(
            incumbent_id=incumbent.id,
            challenger_id=challenger.id,
            outcome=outcome,
            reason=reason,
            evidence=evidence,
        )


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

"""Sync/async evaluators with finite, higher-is-better scores."""

from __future__ import annotations

import math
from typing import Any

from dreamrsi._invoke import with_context
from dreamrsi.errors import EvaluationError
from dreamrsi.models.evaluation import Evaluation, EvaluationStatus


class CallableEvaluator:
    def __init__(self, score_fn: Any, evaluator_id: str = "callable", version: str = "1"):
        self._score_fn = score_fn
        self._evaluator_id = evaluator_id
        self._version = version

    async def evaluate(self, candidate: Any, context: Any = None) -> Evaluation:
        try:
            result = await with_context(self._score_fn, candidate, context)
            evaluation = (
                result
                if isinstance(result, Evaluation)
                else Evaluation(
                    score=float(getattr(result, "score", result)),
                    evaluator_id=self._evaluator_id,
                    evaluator_version=self._version,
                )
            )
            if evaluation.status in (EvaluationStatus.ERROR, EvaluationStatus.SKIPPED):
                raise EvaluationError(f"Evaluator returned {evaluation.status.value}")
            if not math.isfinite(evaluation.score):
                raise EvaluationError("Evaluator must return a finite score")
            return evaluation
        except EvaluationError:
            raise
        except Exception as exc:
            raise EvaluationError(f"Evaluation failed: {exc}") from exc


class NumericEvaluator(CallableEvaluator):
    def __init__(
        self,
        target: float,
        maximize: bool = True,
        evaluator_id: str = "numeric",
        version: str = "1",
    ):
        super().__init__(
            lambda candidate: float(candidate) if maximize else -abs(float(candidate) - target),
            evaluator_id,
            version,
        )


class CompositeEvaluator:
    def __init__(
        self,
        evaluators: list[Any],
        weights: list[float] | None = None,
        evaluator_id: str = "composite",
        version: str = "1",
    ):
        self._evaluators = [CallableEvaluator(getattr(e, "evaluate", e)) for e in evaluators]
        self._weights = weights if weights is not None else [1.0] * len(evaluators)
        if not evaluators or len(evaluators) != len(self._weights):
            raise ValueError("Provide evaluators and one weight per evaluator")
        if not all(math.isfinite(w) for w in self._weights):
            raise ValueError("Weights must be finite")
        self._evaluator_id, self._version = evaluator_id, version

    async def evaluate(self, candidate: Any, context: Any = None) -> Evaluation:
        total = 0.0
        for evaluator, weight in zip(self._evaluators, self._weights, strict=False):
            result = await evaluator.evaluate(candidate, context)
            total += result.score * weight
        if not math.isfinite(total):
            raise EvaluationError("Composite score is not finite")
        return Evaluation(
            score=total, evaluator_id=self._evaluator_id, evaluator_version=self._version
        )

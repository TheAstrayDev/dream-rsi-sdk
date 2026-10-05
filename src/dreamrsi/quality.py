"""Explicit raw-quality selection and certified, prefix-visible stopping.

Bounds are a caller-supplied mathematical contract, never an estimate inferred
from a replay plateau. Missing or contradictory evidence cannot authorize a stop.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from dreamrsi.models.discovery import NodeStatus


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


@dataclass(frozen=True, kw_only=True)
class QualityContract:
    """Define raw quality, an optional proven bound and an initial candidate.

    ``metric`` receives the same record as ``HoldoutPipeline.quality_metric``:
    observation, diagnostics, score, depth, parent_id and status. With no
    metric, raw quality is the evaluator's score. ``upper_bound`` must bound
    every feasible candidate for the task, including future model responses.
    The metric receives an isolated snapshot of the revealed record. Mutating
    that snapshot cannot change stored answers or certificate metadata. Its
    return value must still be deterministic: isolation cannot make a stateful
    callback pure. The metric, a callable bound and
    ``initial_candidate(state, task)`` must be pure local computations:
    no model dispatch or hidden paid work.
    The runtime evaluates an initial observation through its normal evaluator;
    supplying one does not make its quality trusted or its evaluation free.

    ``id`` identifies these semantics in persisted trees and checkpoints.
    Change it when the metric, feasible domain or bound changes.

    ``preserve_policy=True`` anchors deployment to the original supplied
    policy: no promoted rewrite may replace its decisions. Set False explicitly
    for empirical policy development, which has no universal no-loss guarantee.
    ``certified_stopping=False`` runs that full reference policy with the same
    quality records, bound and evaluated initial candidate as the certified run.
    Use this comparator when checking the unchanged-prefix guarantee.
    """

    id: str
    metric: Callable[[Any], float | None] | None = None
    upper_bound: float | Callable[[Any], float | None] | None = None
    initial_candidate: Callable[[Any, Any], Any] | None = None
    preserve_policy: bool = True
    certified_stopping: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("QualityContract id must be a nonempty string")
        if type(self.preserve_policy) is not bool:
            raise ValueError("preserve_policy must be boolean")
        if type(self.certified_stopping) is not bool:
            raise ValueError("certified_stopping must be boolean")
        for name in ("metric", "initial_candidate"):
            value = getattr(self, name)
            if value is not None and not callable(value):
                raise ValueError(f"{name} must be callable")
        if (
            self.upper_bound is not None
            and not callable(self.upper_bound)
            and _finite(self.upper_bound) is None
        ):
            raise ValueError("upper_bound must be finite, callable or None")

    def quality(self, record: Mapping[str, Any]) -> float | None:
        """Extract finite raw quality; unavailable quality is not a zero score."""
        return get_record_quality(record, self.metric)

    def bound(self, task: Any) -> float | None:
        """Resolve a local bound; failed/invalid computation leaves stopping open."""
        try:
            value = self.upper_bound(task) if callable(self.upper_bound) else self.upper_bound
        except Exception:
            return None
        return _finite(value)

    def checkpoint_config(self) -> dict[str, Any]:
        """Describe persisted semantics; callback changes require a new id."""
        return {
            "id": self.id,
            "upper_bound": "callable" if callable(self.upper_bound) else self.upper_bound,
            "metric": "callable" if self.metric is not None else "score",
            "initial_candidate": self.initial_candidate is not None,
            "preserve_policy": self.preserve_policy,
            "certified_stopping": self.certified_stopping,
        }


def get_record_quality(
    record: Mapping[str, Any], metric: Callable[[Any], Any] | None = None,
) -> float | None:
    """Extract one record's raw quality using the shared validation convention."""
    if not isinstance(record, Mapping) or _finite(record.get("score")) is None:
        return None
    if "status" in record and record["status"] not in (
        NodeStatus.COMPLETED, NodeStatus.COMPLETED.value,
    ):
        return None
    try:
        value = metric(copy.deepcopy(record)) if metric is not None else record.get("score")
    except Exception:
        return None
    return _finite(value)


def quality_of_record(
    record: Mapping[str, Any], contract: QualityContract | None = None,
) -> float | None:
    """Measure the actual observation, using score only without a raw metric."""
    if contract is None:
        return get_record_quality(record)
    return contract.quality(record)


def select_best_record(
    records: Mapping[str, Mapping[str, Any]], contract: QualityContract | None = None,
) -> tuple[str | None, float | None]:
    """Select the returned incumbent by raw quality with stable first-seen ties."""
    best_id: str | None = None
    best_quality: float | None = None
    for node_id, record in records.items():
        quality = quality_of_record(record, contract)
        if quality is not None and (best_quality is None or quality > best_quality):
            best_id, best_quality = node_id, quality
    return best_id, best_quality


def quality_certificate(
    records: Mapping[str, Mapping[str, Any]], contract_id: str,
) -> bool:
    """Check a proven bound using only SDK-stamped, revealed observations.

    Every record must carry ``diagnostics['quality_contract']`` with the same
    ``id`` and a ``raw_quality`` (possibly None for invalid observations). The
    unique root carries ``upper_bound`` too. A finite but mathematically false
    bound cannot generally be detected without exploring the future; its
    correctness remains part of the caller's explicit contract.
    """
    if not isinstance(contract_id, str) or not contract_id.strip() or not records:
        return False
    roots: list[Mapping[str, Any]] = []
    qualities: list[float] = []
    for record in records.values():
        if not isinstance(record, Mapping):
            return False
        diagnostics = record.get("diagnostics")
        metadata = (
            diagnostics.get("quality_contract") if isinstance(diagnostics, Mapping) else None
        )
        if not isinstance(metadata, Mapping) or metadata.get("id") != contract_id:
            return False
        if "raw_quality" not in metadata:
            return False
        value = metadata["raw_quality"]
        quality = _finite(value)
        if value is not None and quality is None:
            return False
        if quality is not None:
            if get_record_quality(record) is None:
                return False
            qualities.append(quality)
        if type(record.get("depth")) is int and record["depth"] == 0:
            roots.append(metadata)
    if len(roots) != 1 or not qualities:
        return False
    bound = _finite(roots[0].get("upper_bound"))
    if bound is None:
        return False
    best = max(qualities)
    # Exceeding a declared maximum contradicts the contract. No epsilon is
    # introduced: a strict no-quality-loss promise cannot stop below the bound.
    return best == bound

"""Frozen grid replay and versioned attainment/work beta evaluation."""

from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass, replace

from dreamrsi.appendix.api import (
    CellMeta,
    GridQuestion,
    Observation,
    cell_id,
    finalize_result,
)
from dreamrsi.appendix.observation_signal import successful


@dataclass(frozen=True)
class GridTrace:
    trace_id: str
    baseline_score: float
    branches: tuple[tuple[Observation, ...], ...]
    directions: tuple[tuple[str, ...], ...] = ()
    planning_history: tuple[dict, ...] | None = None

    def __post_init__(self):
        if not self.trace_id or not self.branches or not any(self.branches):
            raise ValueError("Trace needs an ID and at least one recorded cell")
        if not math.isfinite(self.baseline_score):
            raise ValueError("Trace baseline must be finite")
        for branch, rows in enumerate(self.branches):
            for attempt, obs in enumerate(rows):
                if (obs.branch, obs.attempt) != (branch, attempt):
                    raise ValueError("Trace cells must be contiguous and correctly indexed")
        if self.directions and len(self.directions) != len(self.branches):
            raise ValueError("Direction metadata must match branches")
        object.__setattr__(self, "branches", tuple(tuple(b) for b in self.branches))
        object.__setattr__(self, "planning_history", copy.deepcopy(self.planning_history))

    @property
    def branch_count(self):
        return len(self.branches)

    @property
    def refine_count(self):
        return max(len(rows) for rows in self.branches) - 1

    def question(self, plan, workers):
        if plan.branch_count > self.branch_count or plan.refine_count > self.refine_count:
            raise ValueError("Requested plan is out of frozen trace support")
        cells, observations = {}, {}
        for branch, rows in enumerate(self.branches[: plan.branch_count]):
            for attempt, obs in enumerate(rows[: plan.refine_count + 1]):
                cid = cell_id(branch, attempt)
                cells[cid] = CellMeta(
                    branch,
                    attempt,
                    cell_id(branch, attempt - 1) if attempt else None,
                    len(cells),
                    self.directions[branch] if self.directions else (),
                )
                observations[cid] = obs
        return GridQuestion(
            cells,
            observations.__getitem__,
            baseline_score=self.baseline_score,
            max_parallelism=workers,
        )

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["trace_id"],
            data["baseline_score"],
            tuple(tuple(Observation(**row) for row in branch) for branch in data["branches"]),
            tuple(tuple(tags) for tags in data.get("directions", [])),
            tuple(data["planning_history"]) if data.get("planning_history") is not None else None,
        )


def pareto_auc(points):
    """Area of the right-continuous upper attainment envelope on normalized work [0,1]."""
    envelope, best, previous, area = [], 0.0, 0.0, 0.0
    for work, attainment in sorted(points):
        area += (work - previous) * best
        previous = work
        if attainment > best:
            best = attainment
            envelope.append({"work": work, "attainment": attainment})
    area += (1 - previous) * best
    return area, envelope


def beta_sweep(
    policy_factory, traces, context, *, betas=(0, 0.2, 0.4, 0.6, 0.8, 1), parallel_weight=0.1
):
    """Fresh policy + empty prefix per (trace,beta); hidden targets stay in the evaluator.

    Any failed or unsupported episode invalidates the candidate's reward. Do not
    compare this explicitly versioned AUC convention to unversioned legacy sweeps.
    """
    betas = tuple(betas)
    traces = tuple(copy.deepcopy(traces))
    if not traces or not betas or len(set(betas)) != len(betas):
        raise ValueError("Nonempty traces and distinct beta values required")
    if len({trace.trace_id for trace in traces}) != len(traces):
        raise ValueError("Trace IDs must be unique")
    if any(type(b) not in (int, float) or not math.isfinite(b) or not 0 <= b <= 1 for b in betas):
        raise ValueError("beta must be finite and in [0,1]")
    if not math.isfinite(parallel_weight) or parallel_weight < 0:
        raise ValueError("parallel_weight must be nonnegative and finite")
    episodes, points_by_trace, errors = [], {}, []
    for trace in traces:
        capacity = sum(len(branch) for branch in trace.branches)
        ceiling = max(
            [trace.baseline_score]
            + [
                obs.score
                for rows in trace.branches
                for obs in rows
                if successful(obs) and obs.score is not None
            ]
        )
        for beta in betas:
            try:
                policy = policy_factory(beta)
                if getattr(policy, "beta", None) != beta:
                    raise ValueError("Policy factory did not honor the requested fixed beta")
                planning = replace(
                    context,
                    history=(
                        trace.planning_history
                        if trace.planning_history is not None
                        else context.history
                    ),
                    trace_branch_count=trace.branch_count,
                    trace_refine_count=trace.refine_count,
                )
                plan = planning.validate(policy.plan_grid(copy.deepcopy(planning)))
                question = trace.question(plan, context.max_parallelism)
                policy.solve(question, budget=None)
                if policy.beta != beta:
                    raise ValueError("Policy changed beta inside the episode")
                result = finalize_result(question)
                gap = ceiling - trace.baseline_score
                attainment = (result.best_score - trace.baseline_score) / gap if gap > 0 else 0.0
                work = result.total_probes / capacity
                penalty = (
                    result.effective_sequential_rounds / result.total_probes
                    if result.total_probes
                    else 1.0
                )
                episodes.append(
                    {
                        "trace_id": trace.trace_id,
                        "beta": beta,
                        "plan": asdict(plan),
                        "attainment": attainment,
                        "work": work,
                        "parallel_penalty": penalty,
                        "result": asdict(result),
                    }
                )
                points_by_trace.setdefault(trace.trace_id, []).append((work, attainment))
            except Exception as exc:
                errors.append(
                    {
                        "trace_id": trace.trace_id,
                        "beta": beta,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    aucs, envelopes = [], {}
    for tid, points in points_by_trace.items():
        auc, envelope = pareto_auc(points)
        aucs.append(auc)
        envelopes[tid] = envelope
    penalty = sum(e["parallel_penalty"] for e in episodes) / len(episodes) if episodes else None
    auc = sum(aucs) / len(aucs) if aucs and not errors else None
    reward = auc - parallel_weight * penalty if auc is not None and penalty is not None else None
    frontier = []
    for beta in betas:
        rows = [e for e in episodes if e["beta"] == beta]
        if len(rows) == len(traces):
            frontier.append(
                {
                    "beta": beta,
                    **{
                        name: sum(row[name] for row in rows) / len(rows)
                        for name in ("attainment", "work", "parallel_penalty")
                    },
                }
            )
    tradeoffs = {(p["work"], p["attainment"]) for p in frontier}
    return {
        "objective_version": "appendix-pareto-v1",
        "betas": list(betas),
        "parallel_weight": parallel_weight,
        "trace_ids": [t.trace_id for t in traces],
        "pareto": {"auc": auc, "parallel_penalty": penalty, "reward": reward},
        "frontier": frontier,
        "envelopes": envelopes,
        "episodes": episodes,
        "errors": errors,
        "non_degenerate": len(tradeoffs) > 1 and not errors,
    }

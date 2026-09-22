"""Appendix B episode contracts. This is independent of the section-3 tree API."""

from __future__ import annotations

import copy
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from dreamrsi.errors import PolicyError


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def history_summary(row):
    """Planning receives live manifests and sweep summaries, never execution archives."""
    fields = {
        "cycle",
        "status",
        "phase",
        "planned_grid",
        "effective_grid",
        "opened_width",
        "opened_depth",
        "total_probes",
        "decision_rounds",
        "best_score",
        "beta",
        "root_improvements",
        "refinement_improvements",
        "hard_failure_branches",
    }
    result = {key: copy.deepcopy(value) for key, value in row.items() if key in fields}
    if "beta_sweep" in row:
        result["beta_sweep"] = {
            key: copy.deepcopy(value)
            for key, value in row["beta_sweep"].items()
            if key
            in {
                "objective_version",
                "pareto",
                "frontier",
                "parallel_weight",
                "non_degenerate",
                "trace_ids",
            }
        }
    return result


@dataclass(frozen=True)
class Observation:
    branch: int
    attempt: int
    score: float | None = None
    evaluated: bool = False
    valid: bool = False
    fail_class: str = "unknown"
    error: str | None = None
    delta_vs_baseline: float | None = None
    delta_vs_parent: float | None = None
    n_valid: int | None = None
    n_total: int | None = None

    def __post_init__(self):
        integer(self.branch, "branch")
        integer(self.attempt, "attempt")
        for name in ("score", "delta_vs_baseline", "delta_vs_parent"):
            value = getattr(self, name)
            if value is not None and (type(value) not in (float, int) or not math.isfinite(value)):
                raise ValueError(f"{name} must be finite or None")
        if type(self.evaluated) is not bool or type(self.valid) is not bool:
            raise ValueError("evaluated and valid must be booleans")
        if not isinstance(self.fail_class, str):
            raise ValueError("fail_class must be a string")
        if self.error is not None and not isinstance(self.error, str):
            raise ValueError("error must be a string or None")
        for name in ("n_valid", "n_total"):
            if getattr(self, name) is not None:
                integer(getattr(self, name), name)
        if self.n_valid is not None and self.n_total is not None and self.n_valid > self.n_total:
            raise ValueError("n_valid cannot exceed n_total")


@dataclass(frozen=True)
class CellMeta:
    branch: int
    attempt: int
    parent_id: str | None
    seq: int
    tags: tuple[str, ...] = ()

    def __post_init__(self):
        integer(self.branch, "branch")
        integer(self.attempt, "attempt")
        integer(self.seq, "seq")
        expected = f"{self.branch}:{self.attempt - 1}" if self.attempt else None
        if self.parent_id != expected:
            raise ValueError("Cell parent must be the preceding attempt on its branch")
        if not isinstance(self.tags, (list, tuple)) or any(
            type(tag) is not str for tag in self.tags
        ):
            raise ValueError("Cell tags must be strings")
        object.__setattr__(self, "tags", tuple(self.tags))


@dataclass(frozen=True)
class GridPlan:
    branch_count: int
    refine_count: int
    reason: str

    def __post_init__(self):
        integer(self.branch_count, "branch_count", 1)
        integer(self.refine_count, "refine_count")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Every grid plan needs a factual reason")


@dataclass(frozen=True)
class GridPlanningContext:
    history: tuple[dict[str, Any], ...] = ()
    fallback_branch_count: int = 4
    fallback_refine_count: int = 3
    hard_max_branch_count: int = 32
    hard_max_refine_count: int = 32
    max_parallelism: int = 4
    trace_branch_count: int | None = None
    trace_refine_count: int | None = None

    def __post_init__(self):
        for name in ("fallback_branch_count", "hard_max_branch_count", "max_parallelism"):
            integer(getattr(self, name), name, 1)
        for name in ("fallback_refine_count", "hard_max_refine_count"):
            integer(getattr(self, name), name)
        for name in ("trace_branch_count", "trace_refine_count"):
            if getattr(self, name) is not None:
                integer(getattr(self, name), name, 1 if name == "trace_branch_count" else 0)
        for row in self.history:
            if row.get("status") != "completed" or row.get("phase") != "live":
                raise ValueError("Planning history must contain completed earlier live cycles")
        object.__setattr__(self, "history", tuple(history_summary(row) for row in self.history))

    def validate(self, plan):
        if not isinstance(plan, GridPlan):
            raise PolicyError("plan_grid must explicitly return GridPlan")
        if (
            plan.branch_count > self.hard_max_branch_count
            or plan.refine_count > self.hard_max_refine_count
        ):
            raise PolicyError("Grid plan exceeds hard caps")
        if (
            self.trace_branch_count is not None and plan.branch_count > self.trace_branch_count
        ) or (self.trace_refine_count is not None and plan.refine_count > self.trace_refine_count):
            raise PolicyError("Grid plan is out of frozen trace support")
        return plan


@dataclass
class SimResult:
    best_score: float | None = None
    total_probes: int = 0
    decision_rounds: int = 0
    effective_sequential_rounds: int = 0
    curve: list[dict[str, Any]] = field(default_factory=list)
    execution_trace: list[dict[str, Any]] = field(default_factory=list)


class LLMDesignedMethod:
    NAME = "OptimalPolicy"

    def __init__(self, config=None):
        self.config = copy.deepcopy(config or {})
        self.beta = float(self.config.get("beta", 0.6))
        if not math.isfinite(self.beta) or not 0 <= self.beta <= 1:
            raise ValueError("beta must be finite and in [0, 1]")

    def solve(self, question, budget=None):
        raise NotImplementedError

    def plan_grid(self, context):
        raise NotImplementedError("An explicit plan_grid implementation is required")


def cell_id(branch, attempt):
    return f"{branch}:{attempt}"


class GridQuestion:
    """Prefix facade with one irreversible probe per cell and pre-batch legality.

    Supply a private resolver for recorded or live observations. Live resolvers
    run concurrently, but observations/callbacks are committed in batch order.
    Native policies are trusted Python; generated policies get only a restricted proxy.
    """

    def __init__(
        self, cells, resolve, *, baseline_score, max_parallelism=4, live=False, probe_budget=None
    ):
        integer(max_parallelism, "max_parallelism", 1)
        if type(baseline_score) not in (float, int) or not math.isfinite(baseline_score):
            raise ValueError("baseline_score must be finite")
        self.baseline_score = baseline_score
        self.max_parallelism = max_parallelism
        self._cells = copy.deepcopy(cells)
        for cid, meta in self._cells.items():
            if cid != cell_id(meta.branch, meta.attempt):
                raise ValueError("Cell ID does not match its metadata")
            if meta.parent_id is not None and meta.parent_id not in self._cells:
                raise ValueError("Grid cells require contiguous parent chains")
        self._resolve = resolve
        self._live = live
        self._observed: dict[str, Observation] = {}
        self._result = SimResult(best_score=baseline_score)
        self._started = False
        self._probe_budget = None
        self.set_probe_budget(probe_budget)

    def set_probe_budget(self, budget):
        if self._started:
            raise PolicyError("Cannot change budget after probing starts")
        if budget is not None:
            integer(budget, "probe budget")
        self._probe_budget = budget

    def reset(self):
        if self._started:
            raise PolicyError("An episode may be reset only before its first probe")
        self._observed = {}
        self._result = SimResult(best_score=self.baseline_score)

    def observed(self):
        return copy.deepcopy(self._observed)

    def legal_actions(self):
        return [
            cid
            for cid, meta in self._cells.items()
            if cid not in self._observed
            and (meta.parent_id is None or meta.parent_id in self._observed)
        ]

    def legal_roots(self):
        return [cid for cid in self.legal_actions() if self._cells[cid].attempt == 0]

    def opened_branches(self):
        return sorted({obs.branch for obs in self._observed.values()})

    def meta(self, cid):
        # Structural metadata only, including unopened actions; never scores.
        return copy.deepcopy(self._cells[cid])

    @property
    def best_so_far(self):
        return self._result.best_score

    @property
    def budget_spent(self):
        return self._result.total_probes

    def probe_batch(self, cells, on_reveal=None):
        from dreamrsi.appendix.observation_signal import successful

        legal = set(self.legal_actions())
        if (
            not isinstance(cells, list)
            or not cells
            or len(cells) > self.max_parallelism
            or any(not isinstance(cid, str) for cid in cells)
            or len(set(cells)) != len(cells)
            or not set(cells) <= legal
        ):
            raise PolicyError("Batch must be nonempty, distinct, prefix-legal and within workers")
        if self._probe_budget is not None and len(cells) > self._probe_budget - self.budget_spent:
            raise PolicyError("Batch exceeds remaining probe budget")
        self._started = True
        prefix = {cid: asdict(obs) for cid, obs in self._observed.items()}
        if self._live and len(cells) > 1:
            with ThreadPoolExecutor(max_workers=self.max_parallelism) as pool:
                outcomes = list(pool.map(self._resolve, cells))
        else:
            outcomes = [self._resolve(cid) for cid in cells]
        for cid, obs in zip(cells, outcomes, strict=True):
            meta = self._cells[cid]
            if not isinstance(obs, Observation) or (obs.branch, obs.attempt) != (
                meta.branch,
                meta.attempt,
            ):
                raise PolicyError("Resolver returned an observation for the wrong cell")
        self._result.decision_rounds += 1
        self._result.effective_sequential_rounds += math.ceil(len(cells) / self.max_parallelism)
        for cid, obs in zip(cells, outcomes, strict=True):
            parent = self._observed.get(self._cells[cid].parent_id)
            score = obs.score if successful(obs) else None
            obs = replace(
                obs,
                delta_vs_baseline=score - self.baseline_score if score is not None else None,
                delta_vs_parent=(
                    score - parent.score
                    if score is not None
                    and parent is not None
                    and successful(parent)
                    and parent.score is not None
                    else None
                ),
            )
            self._observed[cid] = obs
            self._result.total_probes += 1
            if successful(obs) and obs.score is not None:
                previous = self._result.best_score
                self._result.best_score = (
                    max(previous, obs.score) if previous is not None else obs.score
                )
            self._result.curve.append(
                {
                    "probes": self._result.total_probes,
                    "best_score": self._result.best_score,
                }
            )
            if on_reveal is not None:
                on_reveal(copy.deepcopy(obs))
        self._result.execution_trace.append(
            {
                "prefix": prefix,
                "legal_actions": sorted(legal),
                "batch": list(cells),
                "revealed": {cid: asdict(self._observed[cid]) for cid in cells},
            }
        )
        return [copy.deepcopy(self._observed[cid]) for cid in cells]


def _budget_done(question, budget):
    if budget is None:
        return False
    integer(budget, "probe budget")
    return question.budget_spent >= budget


def _record_curve(result, question):
    result.curve = copy.deepcopy(question._result.curve)


def finalize_result(question, result=None):
    # Authoritative counters belong to the runner, never policy-supplied values.
    return copy.deepcopy(question._result)

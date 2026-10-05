"""Exact integer planning for strictly lower all-in logical LLM call counts."""

from __future__ import annotations

from dataclasses import dataclass

from dreamrsi.models.budget import Budget


def _count(name: str, value: int, *, positive: bool = False) -> None:
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be a {qualifier} integer")


@dataclass(frozen=True)
class EconomyPlan:
    """Reserve a deployment floor before paying for policy preparation.

    The floor is an optimistic planning assumption, not a prediction of live
    calls or quality. Every training, validation and developer dispatch belongs
    in preparation. Historical preparation remains part of lifetime accounting.
    """

    baseline_calls_per_task: int
    horizon: int
    minimum_deployment_calls_per_task: int = 1
    historical_preparation_calls: int = 0

    def __post_init__(self) -> None:
        _count("baseline_calls_per_task", self.baseline_calls_per_task, positive=True)
        _count("horizon", self.horizon, positive=True)
        _count("minimum_deployment_calls_per_task", self.minimum_deployment_calls_per_task)
        _count("historical_preparation_calls", self.historical_preparation_calls)

    @property
    def max_new_total_calls(self) -> int:
        """New preparation plus deployment cap; a negative value is impossible."""
        return self.horizon * self.baseline_calls_per_task - 1 - (
            self.historical_preparation_calls
        )

    @property
    def max_new_preparation_calls(self) -> int:
        """Optimistic preparation cap after reserving all deployment floors."""
        return self.max_new_total_calls - (
            self.horizon * self.minimum_deployment_calls_per_task
        )

    @property
    def feasible(self) -> bool:
        """Whether a strict call saving is still possible at the assumed floor."""
        return self.max_new_preparation_calls >= 0

    def preparation_budget(self) -> Budget:
        """A shared agent-plus-developer preparation cap, with no model calls."""
        return Budget(total_llm_calls=max(0, self.max_new_preparation_calls))

    def remaining_preparation_calls(
        self,
        preparation_calls: int,
        deployment_calls: int,
        tasks_completed: int,
    ) -> int:
        """Recompute further preparation headroom from actual lifetime charges.

        Reserve the optimistic deployment floor only for unfinished tasks in the
        original horizon. Actual deployment replaces that floor as tasks finish;
        excess spending must reduce further preparation before another dispatch.
        A zero allowance may mean the savings target is already impossible.

        ``historical_preparation_calls`` is external history, not charges already
        represented by ``preparation_calls``. Do not count imported/restored
        ledger charges again as external history. Finishing extra tasks does not
        silently extend the original planned budget.
        """
        _count("preparation_calls", preparation_calls)
        _count("deployment_calls", deployment_calls)
        _count("tasks_completed", tasks_completed)
        unfinished = max(0, self.horizon - tasks_completed)
        return max(
            0,
            self.max_new_total_calls
            - preparation_calls
            - deployment_calls
            - unfinished * self.minimum_deployment_calls_per_task,
        )

    def report(
        self,
        preparation_calls: int,
        deployment_calls: int,
        tasks_completed: int,
    ) -> dict[str, int | float | bool | None]:
        """Account measured calls, including history; never invent unknown prices.

        ``payback_tasks`` extrapolates only the measured average deployment call
        count. It is the first strictly cheaper task count if that average holds,
        not a guarantee about future tasks. Reports may extend beyond the original
        horizon to show lifetime costs and eventual payback.
        """
        _count("preparation_calls", preparation_calls)
        _count("deployment_calls", deployment_calls)
        _count("tasks_completed", tasks_completed)
        preparation_total = self.historical_preparation_calls + preparation_calls
        all_in = preparation_total + deployment_calls
        baseline = tasks_completed * self.baseline_calls_per_task
        saved = baseline - all_in
        deployment_gain = baseline - deployment_calls
        # P + (D/n) * k < B * k iff k > P*n/(n*B-D).
        # Integer division handles exact ties without floating-point rounding.
        payback = (
            preparation_total * tasks_completed // deployment_gain + 1
            if tasks_completed and deployment_gain > 0
            else None
        )
        return {
            "historical_preparation_calls": self.historical_preparation_calls,
            "preparation_calls": preparation_calls,
            "preparation_total_calls": preparation_total,
            "deployment_calls": deployment_calls,
            "tasks_completed": tasks_completed,
            "new_total_calls": preparation_calls + deployment_calls,
            "all_in_calls": all_in,
            "baseline_calls": baseline,
            "saved_calls": saved,
            "savings_fraction": saved / baseline if baseline else None,
            "strict_call_saving": all_in < baseline,
            "payback_tasks": payback,
            "tokens": None,
            "usd": None,
        }

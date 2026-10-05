"""Measured-cost admission tests with deterministic callbacks, no model benchmark."""

import json

import pytest

from dreamrsi import Budget, DreamRSI, EconomyPlan, QualityContract, Usage
from dreamrsi.accounting import UsageLedger
from dreamrsi.adapters import FunctionalAgentAdapter
from dreamrsi.errors import BudgetExceeded
from dreamrsi.models.results import RunResult
from dreamrsi.policies import FixedParallelPolicy


class MeasuredDeveloper:
    def __init__(self, provider_calls=1):
        self.provider_calls = provider_calls
        self.requests = 0

    async def improve(self, runtime, task, rounds=1):
        for _ in range(30):
            context = {}

            def generate(context=context):
                self.requests += 1
                context["report_usage"](Usage(provider_calls=self.provider_calls))
                return "measured response"

            try:
                await runtime._charge("developer", generate, context=context)
            except BudgetExceeded:
                break
        return RunResult(metrics={"developer_requests": self.requests})


async def test_actual_deployment_cost_reduces_developer_admission_without_cutting_search():
    developer = MeasuredDeveloper()
    plan = EconomyPlan(4, 6)
    assert plan.max_new_preparation_calls == 17
    sdk = DreamRSI(
        agent=lambda task: .9, evaluator=float,
        policy=FixedParallelPolicy(1, 4), budget=Budget(model_calls=4),
        quality=QualityContract(id="unit-v1", upper_bound=1),
        economy=plan, method=developer,
    )
    # Charge two earlier preparation calls; then two full four-call deployments.
    token = sdk._usage_purpose.set("preparation")
    try:
        for _ in range(2):
            await sdk._charge("developer", lambda: "earlier revision")
    finally:
        sdk._usage_purpose.reset(token)
    for task in ("first", "second"):
        result = await sdk.run(task)
        assert result.costs.model_calls == 4
        assert result.metrics["raw_quality"] == .9
    assert sdk.usage.completed_deployments == 2
    assert sdk._preparation_allowance() == 9  # Static remaining cap was 15.
    await sdk.improve("new development")
    assert developer.requests == 9
    assert sdk.usage.calls_for("preparation") == 11
    assert sdk.usage.calls_for("deployment") == 8
    assert sdk._preparation_allowance() == 0
    # No economic cutoff is inserted into deployment fallback.
    result = await sdk.run("third")
    assert result.costs.model_calls == 4
    assert result.metrics["raw_quality"] == .9


async def test_zero_call_finished_deployment_releases_floor_without_hiding_initial_evaluation():
    developer = MeasuredDeveloper()
    sdk = DreamRSI(
        adapter=FunctionalAgentAdapter(lambda state, context: state),
        evaluator=lambda candidate: 1., budget=Budget(model_calls=1),
        quality=QualityContract(id="exact-v1", upper_bound=1,
                                initial_candidate=lambda state, task: task),
        economy=EconomyPlan(3, 1), method=developer,
    )
    assert sdk._preparation_allowance() == 1
    result = await sdk.run("already verified")
    assert result.costs.model_calls == 0
    assert result.costs.evaluator_calls == 1
    assert result.metrics["raw_quality"] == 1
    assert sdk.usage.completed_deployments == 1
    assert sdk._preparation_allowance() == 2
    await sdk.improve("develop")
    assert developer.requests == 2
    assert sdk._preparation_allowance() == 0
    # Zero-provider local evaluation is not a paid preparation request.
    token = sdk._usage_purpose.set("preparation")
    try:
        await sdk._charge("evaluator", lambda: 1.)
    finally:
        sdk._usage_purpose.reset(token)
    assert sdk.usage.calls_for("preparation") == 2


async def test_dynamic_admission_checks_nested_provider_ceiling_before_dispatch():
    developer = MeasuredDeveloper(provider_calls=3)
    sdk = DreamRSI(
        agent=lambda task: 1., evaluator=float, economy=EconomyPlan(4, 1),
        method=developer, usage_limits={"developer": Usage(provider_calls=3)},
    )
    assert sdk._preparation_allowance() == 2
    await sdk.improve("unaffordable")
    assert developer.requests == 0
    assert not sdk.usage.records and not any(sdk.usage.held.values())


def test_finished_deployment_count_round_trips_and_old_journals_are_conservative():
    ledger = UsageLedger()
    ledger.complete_deployment()
    ledger.complete_deployment()
    snapshot = json.loads(json.dumps(ledger.to_dict()))
    restored = UsageLedger()
    restored.restore(snapshot)
    assert restored.completed_deployments == 2
    snapshot.pop("completed_deployments")
    restored.restore(snapshot)
    assert restored.completed_deployments == 0


@pytest.mark.parametrize("value", [True, -1, 2.5, "3", None])
def test_malformed_deployment_counter_is_rejected(value):
    data = UsageLedger().to_dict()
    data["completed_deployments"] = value
    with pytest.raises(ValueError, match="completed_deployments"):
        UsageLedger().restore(data)

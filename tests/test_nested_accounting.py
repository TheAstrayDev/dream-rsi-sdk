"""Total LLM budgets count nested provider requests without losing logical counters."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from dreamrsi import (
    Budget,
    DreamRSI,
    EconomyPlan,
    FunctionalAgentAdapter,
    SQLiteStore,
    Usage,
    UsageLedger,
)
from dreamrsi.errors import BudgetExceeded


@pytest.mark.parametrize(
    ("stage", "logical_field"),
    [("agent", "model_calls"), ("developer", "developer_calls"), ("evaluator", "evaluator_calls")],
)
def test_nested_requests_reserve_and_charge_actual_calls_separately(stage, logical_field):
    ledger = UsageLedger(Budget(total_llm_calls=7))
    reservation = ledger.reserve(stage, Usage(provider_calls=7, input_tokens=20, usd=0.5))
    assert ledger.held["total_llm_calls"] == 7
    ledger.settle(reservation, Usage(provider_calls=5, input_tokens=12, usd=0.3))
    assert ledger.spent["total_llm_calls"] == 5
    assert ledger.spent[logical_field] == 1
    for field in {"model_calls", "developer_calls", "evaluator_calls"} - {logical_field}:
        assert ledger.spent[field] == 0
    assert ledger.spent["tokens"] == 12
    assert ledger.spent["usd"] == 0.3
    assert not any(ledger.held.values())
    assert not ledger.breached


@pytest.mark.parametrize(("stage", "expected"), [("agent", 1), ("developer", 1), ("evaluator", 0)])
def test_unreported_provider_count_retains_logical_floor(stage, expected):
    ledger = UsageLedger()
    reservation = ledger.reserve(stage, Usage())
    assert ledger.held["total_llm_calls"] == expected
    ledger.settle(reservation, Usage())
    assert ledger.spent["total_llm_calls"] == expected


def test_concurrent_nested_reservations_cannot_oversubscribe_call_limit():
    ledger = UsageLedger(Budget(total_llm_calls=7))

    def reserve(_):
        try:
            return ledger.reserve("agent", Usage(provider_calls=3))
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        admitted = [item for item in executor.map(reserve, range(8)) if item is not None]
    assert len(admitted) == 2
    assert ledger.held["total_llm_calls"] == 6
    for reservation in admitted:
        ledger.settle(reservation, Usage(provider_calls=2))
    assert ledger.spent["total_llm_calls"] == 4
    final = ledger.reserve("developer", Usage(provider_calls=3))
    with pytest.raises(BudgetExceeded, match="total_llm_calls"):
        ledger.reserve("evaluator", Usage(provider_calls=1))
    ledger.release(final)
    assert not any(ledger.held.values())


@pytest.mark.parametrize("cap", [None, 2])
def test_underestimated_positive_call_ceiling_records_true_cost_and_blocks_later_work(cap):
    ledger = UsageLedger(Budget(total_llm_calls=cap))
    reservation = ledger.reserve("agent", Usage(provider_calls=2, usd=0.5))
    ledger.settle(reservation, Usage(provider_calls=3, usd=0.4))
    assert ledger.spent["total_llm_calls"] == 3
    assert ledger.spent["model_calls"] == 1
    assert ledger.spent["usd"] == 0.4
    assert ledger.records[-1]["usage"]["provider_calls"] == 3
    assert ledger.breached
    with pytest.raises(BudgetExceeded, match="usage_ceiling"):
        ledger.reserve("developer", Usage())


def test_uncapped_nested_usage_without_call_ceiling_is_measured_without_false_breach():
    ledger = UsageLedger()
    reservation = ledger.reserve("developer", Usage())
    ledger.settle(reservation, Usage(provider_calls=4))
    assert ledger.spent["total_llm_calls"] == 4
    assert not ledger.breached


def test_unbounded_call_ceiling_does_not_hide_total_budget_overrun():
    ledger = UsageLedger(Budget(total_llm_calls=2))
    reservation = ledger.reserve("agent", Usage())
    ledger.settle(reservation, Usage(provider_calls=3))
    assert ledger.spent["total_llm_calls"] == 3
    assert ledger.breached


def test_actual_spending_and_other_pending_calls_trigger_combined_overrun():
    ledger = UsageLedger(Budget(total_llm_calls=5))
    reservation = ledger.reserve("agent", Usage())
    pending = ledger.reserve("developer", Usage(provider_calls=2))
    ledger.settle(reservation, Usage(provider_calls=4))
    assert ledger.spent["total_llm_calls"] == 4
    assert ledger.held["total_llm_calls"] == 2
    assert ledger.breached
    ledger.settle(pending, Usage(provider_calls=2))
    assert ledger.spent["total_llm_calls"] == 6


@pytest.mark.parametrize("stage", ["agent", "developer", "evaluator"])
def test_missing_usage_report_retains_nested_ceiling_instead_of_zero(stage):
    ledger = UsageLedger()
    reservation = ledger.reserve(stage, Usage(provider_calls=4, input_tokens=25, usd=0.2))
    ledger.settle(reservation)
    assert ledger.spent["total_llm_calls"] == 4
    assert ledger.spent["tokens"] == 25
    assert ledger.spent["usd"] == 0.2
    assert ledger.records[-1]["estimated"]


@pytest.mark.parametrize("stage", ["agent", "developer", "evaluator"])
@pytest.mark.parametrize("purpose", ["preparation", "deployment"])
async def test_pending_nested_call_ceiling_survives_sqlite_restart(tmp_path, stage, purpose):
    ledger = UsageLedger(Budget(total_llm_calls=4))
    ledger.reserve(stage, Usage(provider_calls=4, input_tokens=25, usd=0.2), purpose=purpose)
    path = tmp_path / "usage.db"
    store = SQLiteStore(path)
    await store.save_checkpoint("usage", ledger.to_dict())
    await store.close()
    reopened = SQLiteStore(path)
    try:
        restored = UsageLedger(Budget(total_llm_calls=4))
        restored.restore(await reopened.get_checkpoint("usage"))
        assert restored.spent["total_llm_calls"] == 4
        assert restored.spent["tokens"] == 25
        assert restored.spent["usd"] == 0.2
        assert restored.records[-1]["estimated"]
        assert restored.records[-1]["usage"]["provider_calls"] == 4
        assert restored.records[-1]["purpose"] == purpose
        assert restored.calls_for(purpose) == 4
        other = "deployment" if purpose == "preparation" else "preparation"
        assert restored.calls_for(other) == 0
        with pytest.raises(BudgetExceeded, match="total_llm_calls"):
            restored.reserve("agent", Usage())
    finally:
        await reopened.close()


def test_settled_nested_charges_and_breach_survive_checkpoint_roundtrip():
    ledger = UsageLedger(Budget(total_llm_calls=4))
    reservation = ledger.reserve("evaluator", Usage(provider_calls=2))
    ledger.settle(reservation, Usage(provider_calls=5))
    restored = UsageLedger(Budget(total_llm_calls=4))
    restored.restore(json.loads(json.dumps(ledger.to_dict())))
    assert restored.spent == ledger.spent
    assert restored.breached
    assert restored.spent["evaluator_calls"] == 1
    with pytest.raises(BudgetExceeded, match="usage_ceiling"):
        restored.reserve("agent", Usage())


def test_legacy_checkpoint_preserves_known_provider_charges_above_logical_total():
    ledger = UsageLedger()
    reservation = ledger.reserve("agent", Usage(provider_calls=4))
    ledger.settle(reservation, Usage(provider_calls=4))
    old = ledger.to_dict()
    old["spent"].pop("total_llm_calls")
    restored = UsageLedger()
    restored.restore(old)
    assert restored.spent["total_llm_calls"] == 4
    assert restored.records[0]["usage"]["provider_calls"] == 4
    reservation = restored.reserve("developer", Usage(provider_calls=2))
    restored.settle(reservation, Usage(provider_calls=2))
    assert restored.spent["total_llm_calls"] == 6


async def test_runtime_local_and_campaign_ledgers_count_nested_agent_and_evaluator_calls():
    dispatched = []

    def agent(state, context):
        dispatched.append("agent")
        context["report_usage"](Usage(provider_calls=2))
        return state

    def evaluator(value, context):
        dispatched.append("evaluator")
        context["report_usage"](Usage(provider_calls=1))
        return float(value)

    runtime = DreamRSI(
        adapter=FunctionalAgentAdapter(agent),
        evaluator=evaluator,
        budget=Budget(model_calls=1, total_llm_calls=3),
        campaign_budget=Budget(total_llm_calls=3),
        usage_limits={"agent": Usage(provider_calls=2), "evaluator": Usage(provider_calls=1)},
    )
    result = await runtime.run(1)
    assert dispatched == ["agent", "evaluator"]
    assert result.best_score == 1
    assert result.costs.model_calls == 1
    assert result.costs.evaluator_calls == 1
    assert result.costs.provider_calls == 3
    assert runtime.usage.spent["total_llm_calls"] == 3
    assert not runtime.usage.breached
    assert not any(runtime.usage.held.values())
    await runtime.run(2)
    assert dispatched == ["agent", "evaluator"]


async def test_cancelled_partial_report_retains_full_nested_ceiling_in_both_ledgers():
    ceiling = Usage(provider_calls=4, input_tokens=25, usd=0.2)
    runtime = DreamRSI(
        agent=lambda value: value,
        evaluator=float,
        campaign_budget=Budget(total_llm_calls=4),
        usage_limits={"agent": ceiling},
    )
    local = UsageLedger(Budget(total_llm_calls=4))
    context = {}

    async def interrupted_request():
        context["report_usage"](Usage(provider_calls=1, input_tokens=3))
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await runtime._charge("agent", interrupted_request, context=context, local=local)
    for ledger in (runtime.usage, local):
        assert ledger.spent["total_llm_calls"] == 4
        assert ledger.spent["tokens"] == 25
        assert ledger.spent["usd"] == 0.2
        assert ledger.records[-1]["estimated"]
        assert not any(ledger.held.values())


def test_preparation_deployment_and_later_preparation_have_separate_call_totals():
    ledger = UsageLedger()
    for stage, purpose, calls in [
        ("developer", "preparation", 2),
        ("agent", "deployment", 3),
        ("evaluator", "preparation", 2),
        ("agent", "deployment", 1),
    ]:
        reservation = ledger.reserve(stage, Usage(provider_calls=calls), purpose=purpose)
        ledger.settle(reservation, Usage(provider_calls=calls))
    assert ledger.calls_for("preparation") == 4
    assert ledger.calls_for("deployment") == 4
    assert ledger.spent["total_llm_calls"] == 8
    assert [record["purpose"] for record in ledger.records] == [
        "preparation",
        "deployment",
        "preparation",
        "deployment",
    ]
    pending = ledger.reserve("agent", Usage(provider_calls=3), purpose="preparation")
    assert ledger.calls_for("preparation") == 7
    assert ledger.calls_for("deployment") == 4
    ledger.settle(pending, Usage(provider_calls=2))
    assert ledger.calls_for("preparation") == 6
    assert ledger.calls_for("deployment") == 4


def test_released_purpose_reservation_does_not_become_a_preparation_charge():
    ledger = UsageLedger()
    reservation = ledger.reserve("developer", Usage(provider_calls=3), purpose="preparation")
    assert ledger.calls_for("preparation") == 3
    ledger.release(reservation)
    assert ledger.calls_for("preparation") == 0
    assert ledger.calls_for("deployment") == 0
    assert ledger.records == []


def test_untagged_legacy_records_and_pending_work_count_as_preparation():
    ledger = UsageLedger()
    reservation = ledger.reserve("agent", Usage(provider_calls=3))
    ledger.settle(reservation, Usage(provider_calls=3))
    ledger.reserve("developer", Usage(provider_calls=2))
    snapshot = ledger.to_dict()
    assert "purpose" not in snapshot["records"][0]
    assert "purpose" not in snapshot["pending"][0]
    assert ledger.calls_for("preparation") == 5
    assert ledger.calls_for("deployment") == 0
    restored = UsageLedger()
    restored.restore(json.loads(json.dumps(snapshot)))
    assert restored.calls_for("preparation") == 5
    assert restored.calls_for("deployment") == 0
    assert restored.spent["total_llm_calls"] == 5


def test_tagged_pending_charges_survive_repeated_restart_without_double_counting():
    ledger = UsageLedger()
    reservation = ledger.reserve("developer", Usage(provider_calls=2), purpose="preparation")
    ledger.settle(reservation, Usage(provider_calls=2))
    ledger.reserve("agent", Usage(provider_calls=4), purpose="deployment")
    ledger.reserve("evaluator", Usage(provider_calls=3), purpose="preparation")
    snapshot = ledger.to_dict()
    assert [item["purpose"] for item in snapshot["pending"]] == ["deployment", "preparation"]
    for _ in range(3):
        restored = UsageLedger()
        restored.restore(json.loads(json.dumps(snapshot)))
        assert restored.calls_for("preparation") == 5
        assert restored.calls_for("deployment") == 4
        assert restored.spent["total_llm_calls"] == 9
        assert len(restored.records) == 3
        assert restored.records[-1]["estimated"]
        snapshot = restored.to_dict()


def test_purpose_count_uses_provider_total_once_instead_of_adding_logical_attempt():
    from dreamrsi.accounting import UsageReporter

    ledger = UsageLedger()
    reporter = UsageReporter()
    reporter(Usage(provider_calls=1))
    reporter(Usage(provider_calls=2))
    reservation = ledger.reserve("agent", Usage(provider_calls=3), purpose="preparation")
    ledger.settle(reservation, reporter.usage)
    assert ledger.calls_for("preparation") == 3
    assert ledger.spent["model_calls"] == 1
    assert ledger.spent["total_llm_calls"] == 3


@pytest.mark.parametrize("purpose", ["", "training", 1, []])
def test_invalid_purpose_is_rejected_before_reservation(purpose):
    ledger = UsageLedger()
    with pytest.raises(ValueError, match="Usage purpose"):
        ledger.reserve("agent", Usage(provider_calls=3), purpose=purpose)
    with pytest.raises(ValueError, match="Usage purpose"):
        ledger.calls_for(purpose)
    assert not any(ledger.held.values())
    assert not ledger.active


@pytest.mark.parametrize("journaled_calls", [0, 3, 94])
def test_incomplete_legacy_journal_cannot_erase_aggregate_preparation_charges(journaled_calls):
    snapshot = UsageLedger().to_dict()
    snapshot["spent"].update(total_llm_calls=94, model_calls=70, developer_calls=24)
    if journaled_calls:
        snapshot["records"] = [
            {"stage": "agent", "usage": {"provider_calls": journaled_calls}, "estimated": True}
        ]
    restored = UsageLedger()
    restored.restore(snapshot)
    assert restored.calls_for("preparation") == 94
    assert restored.calls_for("deployment") == 0
    assert restored.spent["total_llm_calls"] == 94
    repeated = UsageLedger()
    repeated.restore(json.loads(json.dumps(restored.to_dict())))
    assert repeated.calls_for("preparation") == 94


def test_unjournaled_residual_is_preparation_without_reclassifying_known_deployment():
    snapshot = UsageLedger().to_dict()
    snapshot["spent"].update(total_llm_calls=94, model_calls=70, developer_calls=24)
    snapshot["records"] = [
        {
            "stage": "agent",
            "usage": {"provider_calls": 4},
            "estimated": False,
            "purpose": "deployment",
        },
        {
            "stage": "developer",
            "usage": {"provider_calls": 3},
            "estimated": False,
            "purpose": "preparation",
        },
    ]
    restored = UsageLedger()
    restored.restore(snapshot)
    assert restored.calls_for("preparation") == 90
    assert restored.calls_for("deployment") == 4
    pending = restored.reserve("agent", Usage(provider_calls=2), purpose="deployment")
    assert restored.calls_for("preparation") == 90
    assert restored.calls_for("deployment") == 6
    restored.settle(pending, Usage(provider_calls=1))
    assert restored.calls_for("preparation") == 90
    assert restored.calls_for("deployment") == 5
    reservation = restored.reserve("developer", Usage(provider_calls=2), purpose="preparation")
    assert restored.calls_for("preparation") == 92
    restored.settle(reservation, Usage(provider_calls=2))
    assert restored.calls_for("preparation") == 92


def test_restored_pending_calls_are_not_added_again_to_unjournaled_residual():
    snapshot = UsageLedger().to_dict()
    snapshot["spent"].update(total_llm_calls=97, model_calls=71, developer_calls=24)
    snapshot["pending"] = [
        {
            "stage": "agent",
            "usage": {"provider_calls": 3},
            "estimated": True,
            "purpose": "deployment",
        }
    ]
    restored = UsageLedger()
    restored.restore(snapshot)
    assert restored.calls_for("preparation") == 94
    assert restored.calls_for("deployment") == 3
    assert restored.calls_for("preparation") + restored.calls_for("deployment") == 97


def test_recorded_nested_calls_above_old_logical_total_never_create_negative_residual():
    snapshot = UsageLedger().to_dict()
    snapshot["spent"].update(total_llm_calls=1, model_calls=1)
    snapshot["records"] = [
        {
            "stage": "agent",
            "usage": {"provider_calls": 4},
            "estimated": False,
            "purpose": "deployment",
        }
    ]
    restored = UsageLedger()
    restored.restore(snapshot)
    assert restored.calls_for("preparation") == 0
    assert restored.calls_for("deployment") == 4
    assert restored.spent["total_llm_calls"] == 4


def test_restore_known_nested_provider_spend_blocks_calls_above_current_total_budget():
    snapshot = UsageLedger().to_dict()
    snapshot["spent"].update(total_llm_calls=1, model_calls=1)
    snapshot["records"] = [
        {
            "stage": "agent",
            "usage": {"provider_calls": 4},
            "estimated": False,
            "purpose": "deployment",
        }
    ]
    restored = UsageLedger(Budget(total_llm_calls=3))
    restored.restore(snapshot)
    assert restored.spent["total_llm_calls"] == 4
    assert restored.breached
    with pytest.raises(BudgetExceeded, match="usage_ceiling"):
        restored.reserve("developer", Usage())
    repeated = UsageLedger(Budget(total_llm_calls=3))
    repeated.restore(json.loads(json.dumps(restored.to_dict())))
    assert repeated.spent == restored.spent
    assert repeated.records == restored.records
    assert repeated.breached


def test_absent_legacy_journal_preserves_aggregate_count_and_blocks_exhausted_budget():
    snapshot = UsageLedger().to_dict()
    snapshot["spent"].update(total_llm_calls=94, model_calls=70, developer_calls=24)
    snapshot.pop("records")
    restored = UsageLedger(Budget(total_llm_calls=93))
    restored.restore(snapshot)
    assert restored.spent["total_llm_calls"] == 94
    assert restored.calls_for("preparation") == 94
    assert restored.breached
    with pytest.raises(BudgetExceeded, match="usage_ceiling"):
        restored.reserve("agent", Usage())


@pytest.mark.parametrize("enforce_plan", [False, True])
async def test_concurrent_deployment_is_not_tagged_or_capped_as_another_tasks_preparation(
    enforce_plan,
):
    from dreamrsi.policies import FixedParallelPolicy

    entered, release = asyncio.Event(), asyncio.Event()
    dispatched = []

    async def agent(state, context):
        dispatched.append(state)
        if state == "training":
            entered.set()
            await release.wait()
        context["report_usage"](Usage(provider_calls=1))
        return 1.0 if state == "training" else 2.0

    class ChildTaskMethod:
        async def improve(self, runtime, task, rounds=1):
            # Internal online/validation child tasks inherit preparation purpose.
            return await asyncio.create_task(runtime.run(task))

    runtime = DreamRSI(
        adapter=FunctionalAgentAdapter(agent),
        evaluator=float,
        policy=FixedParallelPolicy(1, 1),
        method=ChildTaskMethod(),
        budget=Budget(model_calls=1),
        usage_limits={"agent": Usage(provider_calls=1)},
        economy=EconomyPlan(baseline_calls_per_task=3, horizon=1) if enforce_plan else None,
    )
    training = asyncio.create_task(runtime.improve("training", rounds=1))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        deployment = await asyncio.wait_for(asyncio.create_task(runtime.run("deployment")), 2)
        assert deployment.best == 2.0
        assert runtime.usage.calls_for("preparation") == 1
        assert runtime.usage.calls_for("deployment") == 1
    finally:
        release.set()
        result = await asyncio.wait_for(training, 2)
    assert result.best == 1.0
    assert dispatched == ["training", "deployment"]
    assert runtime.usage.calls_for("preparation") == 1
    assert runtime.usage.calls_for("deployment") == 1
    await runtime.run("after")
    assert runtime.usage.calls_for("preparation") == 1
    assert runtime.usage.calls_for("deployment") == 2

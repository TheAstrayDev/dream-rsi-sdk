from itertools import product

import pytest

from dreamrsi.economics import EconomyPlan


def test_six_task_strict_cap_and_preparation_reservation():
    plan = EconomyPlan(baseline_calls_per_task=4, horizon=6)
    assert plan.max_new_total_calls == 23
    assert plan.max_new_preparation_calls == 17
    assert plan.feasible
    assert plan.preparation_budget().total_llm_calls == 17
    assert plan.report(17, 6, 6)["strict_call_saving"]
    assert not plan.report(18, 6, 6)["strict_call_saving"]


def test_historical_preparation_is_not_erased_by_reuse():
    plan = EconomyPlan(4, 6, historical_preparation_calls=94)
    assert plan.max_new_total_calls == -71
    assert plan.max_new_preparation_calls == -77
    assert not plan.feasible
    assert plan.preparation_budget().total_llm_calls == 0
    report = plan.report(0, 6, 6)
    assert report["all_in_calls"] == 100
    assert report["saved_calls"] == -76
    assert not report["strict_call_saving"]
    # 94 + 1*k < 4*k first holds at k=32; k=31 still loses.
    assert report["payback_tasks"] == 32
    later = plan.report(0, 36, 36)
    assert later["all_in_calls"] == 130
    assert later["saved_calls"] == 14


def test_exact_payback_tie_is_not_a_strict_win():
    plan = EconomyPlan(4, 6)
    report = plan.report(6, 6, 6)
    assert report["payback_tasks"] == 3
    assert not plan.report(6, 2, 2)["strict_call_saving"]
    assert plan.report(6, 3, 3)["strict_call_saving"]
    assert plan.report(0, 1, 1)["payback_tasks"] == 1


def test_report_uses_measurements_not_the_optimistic_deployment_floor():
    plan = EconomyPlan(4, 6, minimum_deployment_calls_per_task=1)
    report = plan.report(2, 23, 6)
    assert report["all_in_calls"] == 25
    assert report["saved_calls"] == -1
    assert not report["strict_call_saving"]
    assert report["payback_tasks"] == 13
    assert plan.report(2, 24, 6)["payback_tasks"] is None
    assert plan.report(2, 25, 6)["payback_tasks"] is None


def test_zero_completed_tasks_and_unknown_prices():
    report = EconomyPlan(4, 6).report(2, 1, 0)
    assert report["all_in_calls"] == 3
    assert report["baseline_calls"] == 0
    assert report["saved_calls"] == -3
    assert report["savings_fraction"] is None
    assert report["payback_tasks"] is None
    assert report["tokens"] is None and report["usd"] is None


def test_integer_caps_match_strict_inequality_exhaustively():
    for baseline, horizon, floor, history in product(
        range(1, 6), range(1, 6), range(7), range(21)
    ):
        plan = EconomyPlan(baseline, horizon, floor, history)
        cap = horizon * (baseline - floor) - 1 - history
        assert plan.max_new_preparation_calls == cap
        assert plan.feasible == (cap >= 0)
        assert plan.preparation_budget().total_llm_calls == max(0, cap)
        for preparation in range(8):
            total = history + preparation + horizon * floor
            assert (preparation <= cap) == (total < horizon * baseline)


def test_measured_payback_is_first_strict_winning_integer_exhaustively():
    for baseline, completed, preparation, deployment in product(
        range(1, 6), range(1, 7), range(13), range(31)
    ):
        plan = EconomyPlan(baseline, completed, historical_preparation_calls=preparation)
        payback = plan.report(0, deployment, completed)["payback_tasks"]
        gain = completed * baseline - deployment
        if gain <= 0:
            assert payback is None
        else:
            assert isinstance(payback, int)
            assert preparation * completed < payback * gain
            assert preparation * completed >= (payback - 1) * gain


@pytest.mark.parametrize("field", ["baseline_calls_per_task", "horizon"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2", None])
def test_positive_plan_counts_reject_invalid_values(field, value):
    arguments = {"baseline_calls_per_task": 4, "horizon": 6, field: value}
    with pytest.raises(ValueError, match=field):
        EconomyPlan(**arguments)


@pytest.mark.parametrize(
    "field", ["minimum_deployment_calls_per_task", "historical_preparation_calls"]
)
@pytest.mark.parametrize("value", [-1, True, 1.5, "2", None])
def test_nonnegative_plan_counts_reject_invalid_values(field, value):
    with pytest.raises(ValueError, match=field):
        EconomyPlan(4, 6, **{field: value})


@pytest.mark.parametrize("field", ["preparation_calls", "deployment_calls", "tasks_completed"])
@pytest.mark.parametrize("value", [-1, True, 1.5, "2", None])
def test_reports_reject_invalid_counts(field, value):
    arguments = {"preparation_calls": 0, "deployment_calls": 0, "tasks_completed": 0}
    arguments[field] = value
    with pytest.raises(ValueError, match=field):
        EconomyPlan(4, 6).report(**arguments)


def test_zero_call_deployment_floor_and_exact_zero_preparation_cap():
    plan = EconomyPlan(1, 1, minimum_deployment_calls_per_task=0)
    assert plan.feasible and plan.max_new_preparation_calls == 0
    assert plan.report(0, 0, 1)["strict_call_saving"]
    impossible = EconomyPlan(1, 1)
    assert not impossible.feasible
    assert impossible.preparation_budget().total_llm_calls == 0


def test_dynamic_headroom_accounts_for_real_deployment_instead_of_its_floor():
    plan = EconomyPlan(4, 6)
    assert plan.remaining_preparation_calls(0, 0, 0) == 17
    # Two completed tasks cost eight calls rather than the two-call floor.
    # The old static allowance would still allow 17 - 2 == 15 further calls.
    assert plan.remaining_preparation_calls(2, 8, 2) == 9
    assert plan.remaining_preparation_calls(11, 8, 2) == 0
    assert plan.report(11, 12, 6)["strict_call_saving"]
    assert not plan.report(12, 12, 6)["strict_call_saving"]


def test_dynamic_headroom_exhaustion_preserves_costs_and_original_horizon():
    plan = EconomyPlan(4, 6, historical_preparation_calls=2)
    assert plan.remaining_preparation_calls(1, 21, 6) == 0
    assert plan.remaining_preparation_calls(1, 18, 6) == 2
    # Beyond the plan, no unfinished floor remains, but HB stays 24.
    assert plan.remaining_preparation_calls(1, 18, 10) == 2
    assert EconomyPlan(4, 6, historical_preparation_calls=94).remaining_preparation_calls(
        0, 0, 0
    ) == 0


def test_dynamic_headroom_includes_calls_without_a_completed_task():
    plan = EconomyPlan(4, 6)
    # Aborted/in-flight deployment still spent its calls; no task floor released.
    assert plan.remaining_preparation_calls(2, 8, 0) == 7
    # A measured zero-call task releases its floor without imaginary expenditure.
    assert plan.remaining_preparation_calls(0, 0, 1) == 18


def test_dynamic_headroom_matches_strict_integer_inequality_exhaustively():
    for baseline, horizon, floor, history, preparation, deployment, completed in product(
        range(1, 4), range(1, 4), range(3), range(4), range(4), range(9), range(6)
    ):
        plan = EconomyPlan(baseline, horizon, floor, history)
        reserved = max(0, horizon - completed) * floor
        raw_headroom = horizon * baseline - 1 - history - preparation - deployment - reserved
        headroom = plan.remaining_preparation_calls(preparation, deployment, completed)
        assert headroom == max(0, raw_headroom)
        for additional in range(1, 5):
            optimistic_all_in = history + preparation + deployment + additional + reserved
            assert (additional <= headroom) == (optimistic_all_in < horizon * baseline)


@pytest.mark.parametrize("field", ["preparation_calls", "deployment_calls", "tasks_completed"])
@pytest.mark.parametrize("value", [-1, True, 1.5, "2", None])
def test_dynamic_headroom_rejects_invalid_counts(field, value):
    arguments = {"preparation_calls": 0, "deployment_calls": 0, "tasks_completed": 0}
    arguments[field] = value
    with pytest.raises(ValueError, match=field):
        EconomyPlan(4, 6).remaining_preparation_calls(**arguments)

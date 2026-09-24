import pytest

from dreamrsi import Budget, DreamRSI, HoldoutPipeline, SQLiteStore
from dreamrsi.errors import ConfigurationError
from dreamrsi.models.policy import PolicyVersion
from dreamrsi.models.promotion import PromotionOutcome
from dreamrsi.policies import BalancedPolicy
from dreamrsi.promotion import CompositeGate, CostQualityGate, HoldoutGate, RawQualityGate


def evidence(incumbent=(0.8, 0.8), challenger=(0.79, 0.9)):
    return {
        "validation_scores": {"incumbent": 0.8, "challenger": 0.81},
        "validation_world_ids": ["first", "second"],
        "validation_reports": [
            {"role": role, "world_id": world_id, "best_score": quality}
            for role, values in (("incumbent", incumbent), ("challenger", challenger))
            for world_id, quality in zip(("first", "second"), values, strict=True)
        ],
    }


async def test_raw_quality_gate_requires_every_world_to_preserve_quality():
    incumbent, challenger = PolicyVersion(), PolicyVersion()
    gate = RawQualityGate(tolerance=0.005)
    result = await gate.evaluate(incumbent, challenger, evidence())
    assert result.outcome == PromotionOutcome.REJECTED
    assert "first" in result.reason

    result = await RawQualityGate(tolerance=0.01).evaluate(
        incumbent, challenger, evidence()
    )
    assert result.outcome == PromotionOutcome.PROMOTED


@pytest.mark.parametrize("tolerance", [-1, float("inf"), float("nan"), True, "0"])
def test_raw_quality_gate_rejects_invalid_tolerance(tolerance):
    with pytest.raises(ValueError, match="tolerance"):
        RawQualityGate(tolerance)


@pytest.mark.parametrize(
    "change",
    [
        lambda data: data.pop("validation_reports"),
        lambda data: data["validation_reports"].pop(),
        lambda data: data["validation_reports"][2].update(best_score=None),
        lambda data: data["validation_reports"][2].update(best_score=float("nan")),
        lambda data: data["validation_reports"][2].update(world_id="second"),
        lambda data: data["validation_world_ids"].append("third"),
        lambda data: data["validation_world_ids"].append([]),
    ],
)
async def test_raw_quality_gate_requires_complete_paired_evidence(change):
    data = evidence()
    change(data)
    incumbent, challenger = PolicyVersion(), PolicyVersion()
    result = await RawQualityGate().evaluate(incumbent, challenger, data)
    assert result.outcome == PromotionOutcome.INSUFFICIENT_EVIDENCE


async def test_raw_quality_gate_composes_with_holdout_replay_gate():
    incumbent, challenger = PolicyVersion(), PolicyVersion()
    gate = CompositeGate([HoldoutGate(), RawQualityGate(tolerance=0.005)])
    result = await gate.evaluate(incumbent, challenger, evidence())
    assert result.outcome == PromotionOutcome.REJECTED

    gate = CompositeGate([HoldoutGate(), RawQualityGate(tolerance=0.01)])
    result = await gate.evaluate(incumbent, challenger, evidence())
    assert result.outcome == PromotionOutcome.PROMOTED


async def test_holdout_pipeline_exposes_raw_best_score():
    validation = HoldoutPipeline([9])
    runtime = DreamRSI(
        agent=lambda task: task,
        evaluator=float,
        budget=Budget(model_calls=1),
        validation=validation,
    )
    await validation.prepare(runtime, 1)
    evidence = await validation.evaluate(runtime, BalancedPolicy(), BalancedPolicy())
    assert evidence["validation_status"] == "evaluated"
    assert [record["best_score"] for record in evidence["validation_reports"]] == [9.0, 9.0]
    assert [record["raw_quality"] for record in evidence["validation_reports"]] == [9.0, 9.0]
    assert (
        await RawQualityGate().evaluate(PolicyVersion(), PolicyVersion(), evidence)
    ).outcome == PromotionOutcome.PROMOTED


async def test_holdout_collection_is_lazy_and_single_use():
    calls = []

    def agent(task):
        calls.append(task)
        return task

    validation = HoldoutPipeline([9, 10])
    runtime = DreamRSI(
        agent=agent, evaluator=float, budget=Budget(model_calls=1), validation=validation
    )
    await validation.prepare(runtime, 1)
    assert calls == []
    assert validation.worlds == []
    for expected in ([9], [9, 10]):
        result = await validation.evaluate(runtime, BalancedPolicy(), BalancedPolicy())
        assert result["validation_status"] == "evaluated"
        assert calls == expected
    assert (await validation.evaluate(runtime, BalancedPolicy(), BalancedPolicy()))[
        "validation_status"
    ] == "exhausted"
    assert calls == [9, 10]


async def test_custom_raw_quality_is_separate_from_composite_score():
    def quality(item):
        return item["observation"]["diagnostics"]["quality_component"]

    validation = HoldoutPipeline([9], quality_metric=quality, quality_metric_id="quality-v1")
    runtime = DreamRSI(
        agent=lambda task: {"score": 0.4, "diagnostics": {"quality_component": 0.8}},
        evaluator=lambda result: result["score"],
        budget=Budget(model_calls=1),
        validation=validation,
    )
    await validation.prepare(runtime, 1)
    result = await validation.evaluate(runtime, BalancedPolicy(), BalancedPolicy())
    assert result["validation_status"] == "evaluated"
    assert [report["best_score"] for report in result["validation_reports"]] == [0.4, 0.4]
    assert [report["raw_quality"] for report in result["validation_reports"]] == [0.8, 0.8]
    assert (
        await RawQualityGate().evaluate(PolicyVersion(), PolicyVersion(), result)
    ).outcome == PromotionOutcome.PROMOTED


async def test_validation_metric_identity_checked_on_resume(tmp_path):
    store = SQLiteStore(tmp_path / "quality.db")
    first = HoldoutPipeline([9], quality_metric=lambda item: item["score"], quality_metric_id="v1")
    runtime = DreamRSI(agent=lambda x: x, evaluator=float, store=store, validation=first)
    runtime._campaign_id = "quality"
    await first.prepare(runtime, 1)
    await store.close()

    reopened = SQLiteStore(tmp_path / "quality.db")
    changed = HoldoutPipeline(
        [9], quality_metric=lambda item: item["score"], quality_metric_id="v2"
    )
    resumed = DreamRSI(agent=lambda x: x, evaluator=float, store=reopened, validation=changed)
    resumed._campaign_id = "quality"
    with pytest.raises(ConfigurationError, match="quality metric changed"):
        await changed.prepare(resumed, 1)
    await reopened.close()


async def test_lazy_validation_resume_collects_only_next_world(tmp_path):
    calls = []

    def agent(task):
        calls.append(task)
        return task

    store = SQLiteStore(tmp_path / "lazy.db")
    first = HoldoutPipeline([9, 10])
    runtime = DreamRSI(
        agent=agent, evaluator=float, budget=Budget(model_calls=1),
        store=store, validation=first,
    )
    runtime._campaign_id = "lazy"
    await first.prepare(runtime, 1)
    await first.evaluate(runtime, BalancedPolicy(), BalancedPolicy())
    assert calls == [9]
    await store.close()

    reopened = SQLiteStore(tmp_path / "lazy.db")
    resumed_validation = HoldoutPipeline([9, 10])
    resumed = DreamRSI(
        agent=agent, evaluator=float, budget=Budget(model_calls=1),
        store=reopened, validation=resumed_validation,
    )
    resumed._campaign_id = "lazy"
    await resumed_validation.prepare(resumed, 1)
    assert resumed_validation.used == 1
    await resumed_validation.evaluate(resumed, BalancedPolicy(), BalancedPolicy())
    assert calls == [9, 10]
    assert resumed_validation.used == 2
    await reopened.close()


@pytest.mark.parametrize(
    ("incumbent", "challenger", "expected"),
    [
        ((0.8, 4), (0.8, 2), PromotionOutcome.PROMOTED),
        ((0.8, 4), (0.9, 4), PromotionOutcome.PROMOTED),
        ((0.8, 4), (0.9, 5), PromotionOutcome.REJECTED),
        ((0.8, 4), (0.7, 2), PromotionOutcome.REJECTED),
        ((0.8, 4), (0.8, 4), PromotionOutcome.REJECTED),
    ],
)
async def test_cost_quality_gate_requires_pareto_improvement(incumbent, challenger, expected):
    data = {
        "training_world_ids": ["one"],
        "training_reports": [
            {
                "role": "incumbent", "world_id": "one",
                "raw_quality": incumbent[0], "probes": incumbent[1],
            },
            {
                "role": "challenger", "world_id": "one",
                "raw_quality": challenger[0], "probes": challenger[1],
            },
        ],
    }
    decision = await CostQualityGate().evaluate(PolicyVersion(), PolicyVersion(), data)
    assert decision.outcome == expected


async def test_cost_quality_gate_cannot_bypass_exhausted_holdout():
    data = {
        "training_world_ids": ["one"],
        "training_reports": [
            {"role": "incumbent", "world_id": "one", "raw_quality": 0.8, "probes": 4},
            {"role": "challenger", "world_id": "one", "raw_quality": 0.8, "probes": 2},
        ],
        "validation_status": "exhausted",
        "validation_scores": {},
    }
    decision = await CostQualityGate().evaluate(PolicyVersion(), PolicyVersion(), data)
    assert decision.outcome == PromotionOutcome.INSUFFICIENT_EVIDENCE


async def test_cost_quality_gate_counts_unrecorded_attempts():
    data = {
        "training_world_ids": ["one"],
        "training_reports": [
            {
                "role": "incumbent", "world_id": "one", "raw_quality": 0.8,
                "probes": 4, "attempted_expansions": 4,
            },
            {
                "role": "challenger", "world_id": "one", "raw_quality": 0.8,
                "probes": 3, "attempted_expansions": 4,
            },
        ],
    }
    decision = await CostQualityGate().evaluate(PolicyVersion(), PolicyVersion(), data)
    assert decision.outcome == PromotionOutcome.REJECTED


async def test_cost_quality_threshold_applies_only_at_equal_probe_count():
    data = {
        "training_world_ids": ["one"],
        "training_reports": [
            {"role": "incumbent", "world_id": "one", "raw_quality": 0.8, "probes": 4},
            {"role": "challenger", "world_id": "one", "raw_quality": 0.9, "probes": 4},
        ],
    }
    gate = CostQualityGate(min_quality_improvement=0.2)
    assert (
        await gate.evaluate(PolicyVersion(), PolicyVersion(), data)
    ).outcome == PromotionOutcome.REJECTED
    data["training_reports"][1]["probes"] = 2
    assert (
        await gate.evaluate(PolicyVersion(), PolicyVersion(), data)
    ).outcome == PromotionOutcome.PROMOTED


@pytest.mark.parametrize("threshold", [-1, float("nan"), float("inf"), True])
def test_cost_quality_gate_rejects_invalid_threshold(threshold):
    with pytest.raises(ValueError, match="min_quality_improvement"):
        CostQualityGate(threshold)

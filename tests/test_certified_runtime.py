"""End-to-end quality/cost invariants; deterministic agents, no LLM benchmark."""

import json

import pytest

from dreamrsi import (
    Budget,
    DefaultMethod,
    DreamRSI,
    EconomyPlan,
    FunctionalAgentAdapter,
    HoldoutPipeline,
    QualityContract,
    Usage,
)
from dreamrsi.artifacts import PolicyCodec
from dreamrsi.errors import ConfigurationError
from dreamrsi.policies import CertifiedPolicy, FixedParallelPolicy, PrefixPolicy
from dreamrsi.replay import ReplayWorld
from dreamrsi.storage import SQLiteStore


def step(state, context):
    index = state.get("index", 0)
    return {**state, "index": index + 1, "quality": state["values"][index]}


def runtime(quality=None, **kwargs):
    return DreamRSI(
        adapter=FunctionalAgentAdapter(step),
        evaluator=lambda candidate: candidate["quality"],
        policy=kwargs.pop("policy", FixedParallelPolicy(1, 5)),
        budget=kwargs.pop("budget", Budget(model_calls=5, max_parallelism=1)),
        quality=quality,
        **kwargs,
    )


async def test_deployment_between_improvements_does_not_reset_preparation_allowance():
    task = {"values": [.1, .2, .3, .4, .9]}
    plan = EconomyPlan(
        baseline_calls_per_task=4, horizon=2, minimum_deployment_calls_per_task=2,
    )
    assert plan.max_new_preparation_calls == 3
    rsi = runtime(QualityContract(id="bounded-v1", upper_bound=1), economy=plan)
    first = await rsi.improve(task, rounds=5)
    assert first.costs.model_calls == 3
    assert rsi.usage.calls_for("preparation") == 3
    deployment = await rsi.run(task)
    assert deployment.costs.model_calls == 5
    assert deployment.metrics["raw_quality"] == .9
    assert rsi.usage.calls_for("deployment") == 5
    await rsi.improve(task, rounds=5)
    assert rsi.usage.calls_for("preparation") == 3
    assert rsi.usage.calls_for("deployment") == 5
    assert rsi.usage.spent["total_llm_calls"] == 8


@pytest.mark.parametrize("values", [
    [.2, 1, .4, .9, .3],
    [.2, .3, .4, .5, 1],
    [.2, .3, .4, .5, .9],
])
async def test_exact_quality_and_same_baseline_prefix(values):
    task = {"values": values}
    baseline = await runtime().run(task)
    rsi = runtime(QualityContract(id="unit-interval-v1", upper_bound=1))
    result = await rsi.run(task)
    assert result.best_score == baseline.best_score == max(values)
    assert result.metrics["raw_quality"] == result.best["quality"]
    assert result.costs.model_calls <= baseline.costs.model_calls
    assert [n.observation for n in result.tree.iter_nodes()] == [
        n.observation for n in baseline.tree.iter_nodes()
    ][:result.tree.size]
    replayed = await rsi.replay(ReplayWorld(baseline.tree), result.policy)
    # Legacy trees have no bound: certificates cannot manufacture one in replay.
    assert replayed.total_probes == baseline.costs.model_calls
    replayed = await rsi.replay(ReplayWorld(result.tree), result.policy)
    assert replayed.total_probes == result.costs.model_calls


async def test_blind_learned_cap_falls_back_without_rerunning_first_answer():
    task = {"values": [.2, .2, .3, .3, .9]}
    rsi = runtime(
        QualityContract(id="strict-v1", upper_bound=1),
        policy=PrefixPolicy(FixedParallelPolicy(1, 5), 1),
    )
    result = await rsi.run(task)
    assert result.costs.model_calls == 5
    assert result.best["quality"] == .9
    assert result.tree.non_root_size == 5
    assert isinstance(result.policy, CertifiedPolicy)


@pytest.mark.parametrize("bound", [None, lambda task: 10**500, lambda task: "1"])
async def test_unavailable_bound_does_not_shorten_search(bound):
    result = await runtime(QualityContract(id="unknown-v1", upper_bound=bound)).run(
        {"values": [.2, .3, .4, .5, 1]}
    )
    assert result.costs.model_calls == 5 and result.best_score == 1


async def test_initial_candidate_is_evaluated_retained_and_charged():
    rsi = runtime(QualityContract(
        id="initial-v1", upper_bound=1,
        initial_candidate=lambda state, task: {"quality": task["initial"]},
    ))
    result = await rsi.run({"initial": 1, "values": [.2, .3, .4, .5, .6]})
    assert result.best == {"quality": 1}
    assert result.costs.model_calls == 0
    assert result.costs.evaluator_calls == 1
    assert result.best_node_id == result.tree.root_id
    replayed = await rsi.replay(ReplayWorld(result.tree), result.policy)
    assert replayed.total_probes == 0 and replayed.best_score == 1


async def test_invalid_model_candidates_cannot_replace_initial_incumbent():
    rsi = runtime(QualityContract(
        id="initial-v1", upper_bound=1,
        initial_candidate=lambda state, task: {"quality": .8},
    ))
    result = await rsi.run({"values": [None] * 5})
    assert result.best["quality"] == .8
    assert result.costs.model_calls == 5
    assert result.metrics["failed_nodes"] == 5
    assert result.costs.evaluator_calls == 6


async def test_initial_evaluation_budget_matches_reference_configuration():
    task = {"initial": .1, "values": [.2, .3, .4, .5, 1]}
    kwargs = dict(
        initial_candidate=lambda state, task: {"quality": task["initial"]},
    )
    limit = Budget(model_calls=5, evaluator_calls=5, max_parallelism=1)
    baseline = await runtime(QualityContract(id="initial-v1", **kwargs), budget=limit).run(task)
    improved = await runtime(
        QualityContract(id="initial-v1", upper_bound=1, **kwargs), budget=limit
    ).run(task)
    assert improved.best_score == baseline.best_score == .5
    assert improved.costs.model_calls == baseline.costs.model_calls == 4
    assert improved.costs.evaluator_calls == baseline.costs.evaluator_calls == 5


def raw_metric(record):
    return record["observation"]["raw_quality"]


@pytest.mark.parametrize("use_contract", [False, True])
async def test_returned_answer_matches_quality_used_by_promotion(use_contract):
    def candidate(state, context):
        index = state.get("index", 0)
        raw, score = [(.95, .70), (.90, .80)][index]
        return {**state, "index": index + 1, "raw_quality": raw, "score": score}

    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(candidate), evaluator=lambda item: item["score"],
        policy=FixedParallelPolicy(1, 2), budget=Budget(model_calls=2, max_parallelism=1),
        quality=QualityContract(id="raw-v1", metric=raw_metric) if use_contract else None,
        validation=None if use_contract else HoldoutPipeline(
            [{"seed": 2}], quality_metric=raw_metric, quality_metric_id="raw-v1",
        ),
    )
    result = await rsi.run({"seed": 1})
    assert result.best["raw_quality"] == .95
    assert result.best_score == .70  # score remains the selected node's original score
    assert result.metrics["raw_quality"] == .95
    trajectory = await rsi.replay(ReplayWorld(result.tree), result.policy)
    assert rsi._trajectory_quality(trajectory) == .95
    rsi._worlds = [ReplayWorld(result.tree)]
    rsi._method = DefaultMethod(online=False)
    improved = await rsi.improve({"seed": 1})
    assert improved.best["raw_quality"] == .95
    assert improved.metrics["raw_quality"] == .95


async def test_certified_nested_policy_and_tree_survive_sqlite_restart(tmp_path):
    database = tmp_path / "quality.sqlite"
    store = SQLiteStore(database)
    quality = QualityContract(id="persist-v1", upper_bound=1)
    rsi = runtime(quality, store=store, method=DefaultMethod("certified"))
    first = await rsi.improve({"values": [.3, 1, .5, .7, .9]}, rounds=1)
    encoded = json.loads(json.dumps(rsi.policy_codec.encode(first.tree and first.policy)))
    assert isinstance(PolicyCodec().decode(encoded), FixedParallelPolicy)
    wrapper = PolicyCodec().decode(json.loads(json.dumps(
        PolicyCodec().encode(CertifiedPolicy(FixedParallelPolicy(1, 5), quality.id))
    )))
    assert wrapper.contract_id == quality.id
    await store.close()
    reopened = SQLiteStore(database)
    resumed = runtime(quality, store=reopened, method=DefaultMethod("certified", resume=True))
    result = await resumed.improve({"values": [.3, 1, .5, .7, .9]}, rounds=1)
    assert result.best_score == first.best_score == 1
    assert result.costs.model_calls == first.costs.model_calls == 2
    assert result.worlds[0].tree.get_node(result.worlds[0].tree.root_id).metadata[
        "quality_contract"
    ]["id"] == quality.id
    await reopened.close()


async def test_changed_quality_contract_cannot_resume_old_campaign(tmp_path):
    store = SQLiteStore(tmp_path / "quality.sqlite")
    task = {"values": [.3, 1, .5, .7, .9]}
    await runtime(QualityContract(id="v1", upper_bound=1), store=store,
                  method=DefaultMethod("test")).improve(task, rounds=1)
    with pytest.raises(ConfigurationError, match="configuration"):
        await runtime(QualityContract(id="v2", upper_bound=1), store=store,
                      method=DefaultMethod("test", resume=True)).improve(task, rounds=1)
    await store.close()


async def test_economy_plan_caps_preparation_but_never_truncates_deployment():
    plan = EconomyPlan(baseline_calls_per_task=5, horizon=1)
    rsi = runtime(QualityContract(id="strict-v1", upper_bound=1), economy=plan)
    prepared = await rsi.improve({"values": [.2, .3, .4, .5, 1]}, rounds=2)
    assert plan.max_new_preparation_calls == 3
    assert prepared.metrics["preparation_llm_calls"] == 3
    deployed = await rsi.run({"values": [.2, .3, .4, .5, 1]})
    assert deployed.costs.model_calls == 5 and deployed.best_score == 1
    assert not plan.report(3, 5, 1)["strict_call_saving"]


async def test_plan_counts_nested_calls_before_preparation_dispatch():
    def nested(state, context):
        context["report_usage"](Usage(provider_calls=2))
        return step(state, context)

    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(nested), evaluator=lambda item: item["quality"],
        policy=FixedParallelPolicy(1, 5), budget=Budget(model_calls=5, max_parallelism=1),
        economy=EconomyPlan(5, 1), usage_limits={"agent": Usage(provider_calls=2)},
    )
    result = await rsi.improve({"values": [.2, .3, .4, .5, 1]}, rounds=1)
    assert result.costs.model_calls == 1
    assert result.metrics["preparation_llm_calls"] == 2
    assert rsi.usage.spent["total_llm_calls"] == 2
    assert not any(rsi.usage.held.values())


async def test_economically_impossible_preparation_dispatches_no_model():
    rsi = runtime(economy=EconomyPlan(4, 6, historical_preparation_calls=94))
    result = await rsi.improve({"values": [.2, .3, .4, .5, 1]})
    assert result.costs.model_calls == 0
    assert result.metrics["preparation_call_limit"] == 0


def test_quality_validation_metric_must_match_contract():
    with pytest.raises(ConfigurationError, match="same metric"):
        runtime(
            QualityContract(id="raw-v1", metric=raw_metric),
            validation=HoldoutPipeline([{"seed": 2}]),
        )


def test_certified_artifact_rejects_invalid_contract_and_fields():
    data = PolicyCodec().encode(CertifiedPolicy(FixedParallelPolicy(), "quality-v1"))
    from dreamrsi.errors import PolicyError

    with pytest.raises(PolicyError):
        PolicyCodec().decode({**data, "contract_id": ""})
    with pytest.raises(PolicyError):
        PolicyCodec().decode({**data, "upper_bound": 1})

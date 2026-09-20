import asyncio
import json

import pytest

from dreamrsi import Budget, DreamRSI, DreamRSIConfig, FunctionalAgentAdapter
from dreamrsi.errors import ConfigurationError, EvaluationError, PolicyError
from dreamrsi.evaluation import CallableEvaluator, CompositeEvaluator, NumericEvaluator
from dreamrsi.models.policy import PolicyDecision, PolicyVersion
from dreamrsi.models.promotion import PromotionOutcome
from dreamrsi.optimization import DeterministicPolicyOptimizer, PolicyVersionManager
from dreamrsi.policies import (
    BalancedPolicy,
    BreadthFirstPolicy,
    DepthFirstPolicy,
    EpsilonGreedyPolicy,
    FixedParallelPolicy,
    GreedyPolicy,
    RandomPolicy,
)
from dreamrsi.promotion import HoldoutGate, ReplayOnlyGate


@pytest.mark.parametrize(
    "policy",
    [
        BalancedPolicy(),
        BreadthFirstPolicy(),
        DepthFirstPolicy(),
        EpsilonGreedyPolicy(seed=1),
        FixedParallelPolicy(),
        GreedyPolicy(),
        RandomPolicy(seed=1),
    ],
)
async def test_all_policies_run(policy):
    rsi = DreamRSI(
        agent=lambda task: task + 1,
        evaluator=lambda value: value,
        policy=policy,
        budget=Budget(model_calls=4, max_rounds=4),
    )
    result = await rsi.run(2)
    assert result.best == 3
    assert 0 < result.costs.model_calls <= 4
    assert result.costs.evaluator_calls == result.costs.model_calls
    assert result.metrics["failed_nodes"] == 0


async def test_refinement_and_storage(tmp_path):
    def step(state):
        state["x"] += 1
        return state

    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(step),
        evaluator=lambda v: v["x"],
        policy=DepthFirstPolicy(),
        budget=Budget(max_rounds=3),
    )
    result = await rsi.run({"x": 0})
    assert result.best == {"x": 3}
    assert result.tree.root.state == {"x": 0}
    assert result.rounds == 3
    restored = await rsi.get_tree(result.run_id)
    assert restored.to_dict() == result.tree.to_dict()
    path = tmp_path / "run.json"
    await rsi.export_run(result, str(path))
    assert json.loads(path.read_text())["tree"]["nodes"][result.best_node_id]["observation"] == {
        "x": 3
    }


@pytest.mark.parametrize(
    "budget",
    [
        Budget(model_calls=0),
        Budget(evaluator_calls=0),
        Budget(max_rounds=0),
        Budget(max_parallelism=0),
        Budget(max_nodes=1),
        Budget(max_depth=0),
    ],
)
async def test_zero_budget_never_calls_agent(budget):
    def forbidden(task):
        pytest.fail("Agent called with exhausted budget")

    result = await DreamRSI(agent=forbidden, evaluator=float, budget=budget).run(1)
    assert result.costs.model_calls == 0
    assert result.rounds == 0


async def test_failure_counts_and_evaluation_errors():
    def broken(task):
        raise RuntimeError("provider down")

    result = await DreamRSI(agent=broken, evaluator=float, budget=Budget(model_calls=2)).run(1)
    assert result.costs.model_calls == 2
    assert result.costs.evaluator_calls == 0
    assert result.metrics["failed_nodes"] == 2
    assert result.best_score is None
    with pytest.raises(EvaluationError):
        await CallableEvaluator(lambda x: float("nan")).evaluate(1)


async def test_context_sync_async_and_no_retry():
    async def score(value, context):
        return value + context["bonus"]

    assert (await CallableEvaluator(score).evaluate(2, {"bonus": 3})).score == 5
    calls = []

    def fail(value, context=None):
        calls.append(value)
        raise TypeError("inside user function")

    with pytest.raises(EvaluationError, match="inside user function"):
        await CallableEvaluator(fail).evaluate(1)
    assert calls == [1]
    assert (await NumericEvaluator(4, maximize=False).evaluate(2)).score == -2
    assert (
        await CompositeEvaluator([lambda x: x, lambda x: x * 2], [1, 2]).evaluate(3)
    ).score == 15


async def test_true_parallelism():
    active = 0
    peak = 0

    async def agent(task):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.005)
        active -= 1
        return task

    result = await DreamRSI(
        agent=agent,
        evaluator=float,
        policy=BreadthFirstPolicy(batch_size=3),
        budget=Budget(model_calls=6, max_parallelism=2),
    ).run(1)
    assert peak == 2
    assert result.costs.model_calls == 6


async def test_timeout_cancels_async_adapter():
    cancelled = asyncio.Event()

    async def slow(task):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    result = await DreamRSI(agent=slow, evaluator=float, budget=Budget(wall_time_s=0.05)).run(1)
    assert cancelled.is_set()
    assert result.metrics["stop_reason"] == "wall_time"
    assert result.costs.model_calls == 1


async def test_promotion_gates_and_manager():
    a, b = PolicyVersion(), PolicyVersion()
    evidence = {"incumbent_avg_score": -4, "challenger_avg_score": -3}
    assert (await ReplayOnlyGate().evaluate(a, b, evidence)).outcome == PromotionOutcome.PROMOTED
    assert (
        await HoldoutGate().evaluate(a, b, evidence)
    ).outcome == PromotionOutcome.INSUFFICIENT_EVIDENCE
    manager = PolicyVersionManager()
    a = manager.register(GreedyPolicy())
    b = manager.register(GreedyPolicy(), parent_id=a.id)
    manager.promote(a.id)
    manager.promote(b.id)
    assert manager.get_champion().id == b.id
    assert [v.id for v in manager.get_lineage(b.id)] == [b.id, a.id]
    manager.rollback(a.id)
    assert manager.get_champion().id == a.id


class StopAfterOne:
    async def decide(self, view):
        return PolicyDecision(expand=[view.frontier[0].id] if view.total_nodes == 1 else [])


class OneChallenger:
    async def generate(self, incumbent, evidence, budget):
        return [StopAfterOne()]


async def test_improve_really_promotes_and_persists():
    rsi = DreamRSI(
        agent=lambda task: 1,
        evaluator=float,
        policy=BreadthFirstPolicy(),
        policy_optimizer=OneChallenger(),
        budget=Budget(max_rounds=3),
    )
    result = await rsi.improve("task", rounds=2)
    assert isinstance(result.champion_policy, StopAfterOne)
    assert result.costs.model_calls == 4
    assert len(await rsi.list_policies()) == 1
    assert len(result.worlds) == 2


async def test_config_and_optimizer():
    variants = await DeterministicPolicyOptimizer().generate(FixedParallelPolicy(), [], None)
    assert len(variants) == 5
    with pytest.raises(ConfigurationError):
        DreamRSI(agent=lambda x: x, evaluator=float, budget=Budget(usd=1))
    with pytest.raises(ValueError):
        Budget(model_calls=-1)
    with pytest.raises(ConfigurationError):
        DreamRSIConfig(default_batch_size=0)
    rsi = DreamRSI(agent=lambda x: x, evaluator=float)
    with pytest.raises(ConfigurationError, match="event loop"):
        rsi.run_sync(1)


async def test_invalid_policy_does_not_execute():
    class Invalid:
        async def decide(self, view):
            return PolicyDecision(expand=["invisible"])

    rsi = DreamRSI(agent=lambda x: x, evaluator=float, policy=Invalid())
    with pytest.raises(PolicyError):
        await rsi.run(1)


async def test_timeout_keeps_completed_batch_results():
    class TwoBranches:
        async def decide(self, view):
            if view.total_nodes == 1:
                return PolicyDecision(expand=[view.frontier[0].id])
            return PolicyDecision(expand=[n.id for n in view.frontier])

    calls = 0

    async def agent(task):
        nonlocal calls
        calls += 1
        if calls == 3:
            await asyncio.sleep(10)
        return calls

    rsi = DreamRSI(
        agent=agent, evaluator=float, policy=TwoBranches(), budget=Budget(wall_time_s=0.1)
    )
    result = await rsi.run("task")
    assert result.best_score == 2
    assert result.costs.model_calls == 3
    assert result.tree.size == 4
    assert result.metrics["stop_reason"] == "wall_time"


async def test_holdout_is_not_faked_by_improve():
    rsi = DreamRSI(
        agent=lambda task: 1,
        evaluator=float,
        policy=BreadthFirstPolicy(),
        policy_optimizer=OneChallenger(),
        promotion=HoldoutGate(),
        budget=Budget(max_rounds=3),
    )
    result = await rsi.improve("task", rounds=1)
    assert result.champion_policy is None


async def test_sync_adapter_object_takes_precedence_over_callability():
    class Adapter(FunctionalAgentAdapter):
        def __call__(self, task):
            pytest.fail("Should use adapter methods")

    result = await DreamRSI(
        agent=Adapter(lambda x: x + 1),
        evaluator=float,
        policy=DepthFirstPolicy(),
        budget=Budget(model_calls=2),
    ).run(0)
    assert result.best == 2

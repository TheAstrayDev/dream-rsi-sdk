import pytest

from dreamrsi import Budget, DefaultMethod, DreamRSI, HoldoutPipeline
from dreamrsi.accounting import Usage, UsageLedger
from dreamrsi.discovery import DiscoveryTree
from dreamrsi.errors import BudgetExceeded, ConfigurationError
from dreamrsi.models.policy import PolicyDecision
from dreamrsi.optimization import DeterministicPolicyOptimizer
from dreamrsi.policies import GreedyPolicy
from dreamrsi.replay import ReplayWorld
from dreamrsi.storage import SQLiteStore


def test_total_llm_call_limit_counts_agent_and_developer_and_restores_old_ledger():
    ledger = UsageLedger(Budget(total_llm_calls=2))
    for stage in ("agent", "developer"):
        reservation = ledger.reserve(stage, Usage())
        ledger.settle(reservation, Usage())
    assert ledger.spent["total_llm_calls"] == 2
    with pytest.raises(BudgetExceeded, match="total_llm_calls"):
        ledger.reserve("agent", Usage())

    old = ledger.to_dict()
    del old["spent"]["total_llm_calls"]
    restored = UsageLedger(Budget(total_llm_calls=2))
    restored.restore(old)
    assert restored.spent["total_llm_calls"] == 2


async def test_offline_improvement_reuses_run_and_rejects_holdout_overlap():
    calls = []

    def agent(task):
        calls.append(task)
        return task

    class NoCandidates:
        async def generate(self, incumbent, evidence, budget=None):
            return []

    runtime = DreamRSI(
        agent=agent,
        evaluator=float,
        budget=Budget(model_calls=1),
        campaign_budget=Budget(total_llm_calls=1),
        method=DefaultMethod(online=False),
        policy_optimizer=NoCandidates(),
        validation=HoldoutPipeline([9]),
    )
    run = await runtime.run(1)
    with pytest.raises(ConfigurationError, match="overlaps"):
        await runtime.record_world(9, run)
    with pytest.raises(ConfigurationError, match="does not belong"):
        await runtime.record_world(2, run)
    world = await runtime.record_world(1, run)
    assert await runtime.record_world(1, run) is world
    result = await runtime.improve(1)
    assert calls == [1]
    assert result.costs.model_calls == 1
    assert runtime.usage.spent["total_llm_calls"] == 1
    assert len(result.worlds) == 1
    assert runtime.validation is not None
    assert runtime.validation.worlds == []


async def test_offline_resume_does_not_repeat_external_run(tmp_path):
    calls = []

    def agent(task):
        calls.append(task)
        return task

    class NoCandidates:
        async def generate(self, incumbent, evidence, budget=None):
            return []

    store = SQLiteStore(tmp_path / "offline.db")
    first = DreamRSI(
        agent=agent,
        evaluator=float,
        store=store,
        budget=Budget(model_calls=1),
        method=DefaultMethod("offline", online=False),
        policy_optimizer=NoCandidates(),
    )
    run = await first.run(1)
    await first.record_world(1, run)
    await first.improve(1, rounds=1)
    await store.close()

    reopened = SQLiteStore(tmp_path / "offline.db")
    second = DreamRSI(
        agent=agent,
        evaluator=float,
        store=reopened,
        budget=Budget(model_calls=1),
        method=DefaultMethod("offline", resume=True, online=False),
        policy_optimizer=NoCandidates(),
    )
    result = await second.improve(1, rounds=2)
    assert calls == [1]
    assert len(result.worlds) == 1
    assert result.costs.model_calls == 1
    await reopened.close()


async def test_resume_rejects_changed_paid_developer_mode(tmp_path):
    class NoCandidates:
        async def generate(self, incumbent, evidence, budget=None):
            return []

    store = SQLiteStore(tmp_path / "mode.db")
    first = DreamRSI(
        agent=lambda task: task,
        evaluator=float,
        store=store,
        budget=Budget(model_calls=1),
        method=DefaultMethod("mode", online=False),
        policy_optimizer=NoCandidates(),
    )
    run = await first.run(1)
    await first.record_world(1, run)
    await first.improve(1)
    await store.close()

    reopened = SQLiteStore(tmp_path / "mode.db")
    second = DreamRSI(
        agent=lambda task: task,
        evaluator=float,
        store=reopened,
        budget=Budget(model_calls=1),
        method=DefaultMethod("mode", resume=True, online=False, force_developer=True),
        policy_optimizer=NoCandidates(),
    )
    with pytest.raises(ConfigurationError, match="developer mode changed"):
        await second.improve(1)
    await reopened.close()


async def test_cheap_replay_candidate_skips_paid_developer(monkeypatch):
    class OneProbe:
        async def decide(self, view):
            if view.calls_used:
                return PolicyDecision(expand=[], stop=True)
            return PolicyDecision(expand=[view.frontier[0].id])

    class PaidDeveloper:
        def __init__(self):
            self.calls = 0

        async def develop(self, incumbent, evidence, evaluate, budget, **kwargs):
            self.calls += 1
            return []

    async def cheap_candidate(self, incumbent, evidence, budget=None):
        return [OneProbe()]

    monkeypatch.setattr(DeterministicPolicyOptimizer, "generate", cheap_candidate)
    developer = PaidDeveloper()
    runtime = DreamRSI(
        agent=lambda task: 1,
        evaluator=float,
        budget=Budget(model_calls=2),
        policy=GreedyPolicy(),
        policy_optimizer=developer,
        method=DefaultMethod(online=False),
    )
    run = await runtime.run(1)
    assert run.costs.model_calls == 2
    await runtime.record_world(1, run)
    result = await runtime.improve(1)
    assert developer.calls == 0
    assert isinstance(result.champion_policy, OneProbe)


async def test_saturated_training_chain_does_not_call_developer():
    class PaidDeveloper:
        calls = 0

        async def develop(self, incumbent, evidence, evaluate, budget, **kwargs):
            self.calls += 1
            return []

    tree = DiscoveryTree()
    root = tree.create_root()
    first = tree.add_node(root.id, observation={"score": 1.0}, score=1.0)
    tree.add_node(first.id, observation={"score": 2.0}, score=2.0)
    tree.commit()
    developer = PaidDeveloper()
    runtime = DreamRSI(
        agent=lambda task: task,
        evaluator=float,
        budget=Budget(model_calls=2, max_nodes=3, max_depth=2, max_rounds=2),
        policy=GreedyPolicy(),
        policy_optimizer=developer,
        method=DefaultMethod(online=False),
    )
    runtime._worlds.append(ReplayWorld(tree))
    result = await runtime.improve(1)
    assert developer.calls == 0
    assert result.champion_policy is None


async def test_branched_world_without_replay_headroom_skips_developer(monkeypatch):
    class OneProbe:
        async def decide(self, view):
            if view.calls_used:
                return PolicyDecision(expand=[], stop=True)
            return PolicyDecision(expand=[view.frontier[0].id])

    class PaidDeveloper:
        calls = 0

        async def develop(self, incumbent, evidence, evaluate, budget, **kwargs):
            self.calls += 1
            return []

    async def no_cheap_variants(self, incumbent, evidence, budget=None):
        return []

    monkeypatch.setattr(DeterministicPolicyOptimizer, "generate", no_cheap_variants)
    tree = DiscoveryTree()
    root = tree.create_root()
    tree.add_node(root.id, observation={"score": 1.0}, score=1.0)
    tree.add_node(root.id, observation={"score": 0.5}, score=0.5)
    tree.commit()
    developer = PaidDeveloper()
    runtime = DreamRSI(
        agent=lambda task: task,
        evaluator=float,
        budget=Budget(model_calls=2, max_nodes=3, max_depth=1, max_rounds=2),
        policy=OneProbe(),
        policy_optimizer=developer,
        method=DefaultMethod(online=False),
    )
    runtime._worlds.append(ReplayWorld(tree))
    result = await runtime.improve(1)
    assert developer.calls == 0
    assert result.champion_policy is None


async def test_early_quality_in_recorded_tree_keeps_developer_eligible(monkeypatch):
    class PaidDeveloper:
        calls = 0

        async def develop(self, incumbent, evidence, evaluate, budget, **kwargs):
            self.calls += 1
            return []

    async def no_cheap_variants(self, incumbent, evidence, budget=None):
        return []

    monkeypatch.setattr(DeterministicPolicyOptimizer, "generate", no_cheap_variants)
    tree = DiscoveryTree()
    root = tree.create_root()
    first = tree.add_node(root.id, observation={"score": 1.0}, score=1.0)
    tree.add_node(first.id, observation={"score": 0.5}, score=0.5)
    tree.commit()
    developer = PaidDeveloper()
    runtime = DreamRSI(
        agent=lambda task: task,
        evaluator=float,
        budget=Budget(model_calls=2, max_nodes=3, max_depth=2, max_rounds=2),
        policy=GreedyPolicy(),
        policy_optimizer=developer,
        method=DefaultMethod(online=False),
    )
    runtime._worlds.append(ReplayWorld(tree))
    await runtime.improve(1)
    assert developer.calls == 1

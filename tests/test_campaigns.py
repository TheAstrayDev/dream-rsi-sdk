import json

import pytest

from dreamrsi import Budget, DefaultMethod, DreamRSI
from dreamrsi.accounting import Usage, UsageLedger
from dreamrsi.artifacts import PolicyCodec
from dreamrsi.errors import BudgetExceeded
from dreamrsi.policies import RandomPolicy
from dreamrsi.storage import SQLiteStore
from dreamrsi.validation import HoldoutPipeline, split_tasks


async def test_campaign_budget_shared_across_runs_and_developer():
    rsi = DreamRSI(
        agent=lambda x: x,
        evaluator=lambda x: x,
        budget=Budget(model_calls=3),
        campaign_budget=Budget(model_calls=4),
    )
    await rsi.improve(1, rounds=3)
    assert rsi.usage.spent["model_calls"] == 4
    assert rsi.usage.spent["evaluator_calls"] == 4
    assert not any(rsi.usage.held.values())


async def test_reported_usage_and_reservations():
    from dreamrsi import FunctionalAgentAdapter

    async def step(state, context):
        context["report_usage"](Usage(input_tokens=2, output_tokens=1, usd=0.1))
        return state

    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(step),
        evaluator=lambda x: x,
        budget=Budget(model_calls=5),
        campaign_budget=Budget(usd=0.3),
        usage_limits={
            "agent": Usage(input_tokens=5, usd=0.2),
            "evaluator": Usage(),
            "developer": Usage(),
        },
    )
    await rsi.run(1)
    assert rsi.usage.spent["usd"] <= 0.3
    assert rsi.usage.spent["tokens"] >= 3
    assert any(not record["estimated"] for record in rsi.usage.records)


def test_reservation_cannot_oversubscribe():
    ledger = UsageLedger(Budget(usd=1))
    reservation = ledger.reserve("agent", Usage(usd=0.8))
    with pytest.raises(BudgetExceeded):
        ledger.reserve("agent", Usage(usd=0.8))
    ledger.settle(reservation, Usage(usd=0.2))
    assert ledger.reserve("agent", Usage(usd=0.8))


async def test_sqlite_checkpoint_resume_and_tree_storage(tmp_path):
    store = SQLiteStore(tmp_path / "campaign.db")
    rsi = DreamRSI(
        agent=lambda x: x,
        evaluator=lambda x: x,
        store=store,
        budget=Budget(model_calls=2),
        method=DefaultMethod("experiment"),
    )
    first = await rsi.improve(3, rounds=1)
    await store.close()
    reopened = SQLiteStore(tmp_path / "campaign.db")
    resumed = DreamRSI(
        agent=lambda x: x,
        evaluator=lambda x: x,
        store=reopened,
        budget=Budget(model_calls=2),
        method=DefaultMethod("experiment", resume=True),
    )
    second = await resumed.improve(3, rounds=2)
    assert len(second.worlds) == 2
    assert second.worlds[0].tree.to_dict() == first.worlds[0].tree.to_dict()
    assert resumed.usage.spent["model_calls"] == 4
    assert await reopened.get_events(limit=1)
    await reopened.close()


def test_codec_json_roundtrip_preserves_rng():
    codec = PolicyCodec()
    policy = RandomPolicy(seed=42)
    decoded = codec.decode(json.loads(json.dumps(codec.encode(policy))))
    assert decoded._rng.getstate() == policy._rng.getstate()


async def test_holdout_is_independent_single_use_and_not_training_feedback():
    seen = []

    class Optimizer:
        async def generate(self, incumbent, evidence, budget=None):
            seen.extend(t.world_id for t in evidence)
            return []

    pipeline = HoldoutPipeline([9, 10])
    rsi = DreamRSI(
        agent=lambda x: x,
        evaluator=lambda x: x,
        budget=Budget(model_calls=1),
        policy_optimizer=Optimizer(),
        validation=pipeline,
    )
    result = await rsi.improve(1, rounds=1)
    assert seen == [result.worlds[0].world_id]
    assert not set(seen) & {w.world_id for w in pipeline.worlds}
    policy = rsi._get_policy()
    for _ in range(2):
        evidence = await pipeline.evaluate(rsi, policy, policy)
        assert evidence["validation_status"] == "evaluated"
    assert (await pipeline.evaluate(rsi, policy, policy))["validation_status"] == "exhausted"
    train, holdout = split_tasks([1, 2, 3], 1)
    assert not set(train) & set(holdout)


async def test_resume_dreaming_does_not_repeat_online_work(tmp_path):
    class InterruptedOptimizer:
        def __init__(self, fail):
            self.fail = fail

        async def generate(self, incumbent, evidence, budget=None):
            if self.fail:
                raise RuntimeError("simulated interruption")
            return []

    calls = []
    def agent(task):
        calls.append(task)
        return task

    store = SQLiteStore(tmp_path / "resume.db")
    first = DreamRSI(agent=agent, evaluator=float, store=store,
                     budget=Budget(model_calls=1), method=DefaultMethod("resume"),
                     policy_optimizer=InterruptedOptimizer(True))
    with pytest.raises(RuntimeError):
        await first.improve(1, rounds=1)
    await store.close()
    reopened = SQLiteStore(tmp_path / "resume.db")
    second = DreamRSI(agent=agent, evaluator=float, store=reopened,
                      budget=Budget(model_calls=1), method=DefaultMethod("resume", resume=True),
                      policy_optimizer=InterruptedOptimizer(False))
    result = await second.improve(1, rounds=1)
    assert calls == [1]
    assert len(result.worlds) == 1
    assert result.costs.model_calls == 1
    await reopened.close()


async def test_bad_checkpoint_write_preserves_previous_record(tmp_path):
    store = SQLiteStore(tmp_path / "atomic.db")
    await store.save_checkpoint("a", {"complete": 1})
    with pytest.raises((ValueError, TypeError)):
        await store.save_checkpoint("a", {"complete": object()})
    assert await store.get_checkpoint("a") == {"complete": 1}
    await store.close()


def test_pending_spending_survives_restart_and_overrun_blocks_calls():
    ledger = UsageLedger(Budget(usd=1))
    ledger.reserve('agent', Usage(usd=.8))
    restored = UsageLedger(Budget(usd=1))
    restored.restore(json.loads(json.dumps(ledger.to_dict())))
    assert restored.spent['usd'] == .8
    assert restored.records[0]['estimated']
    with pytest.raises(BudgetExceeded):
        restored.reserve('agent', Usage(usd=.3))
    reservation = restored.reserve('agent', Usage(usd=.1))
    restored.settle(reservation, Usage(usd=.5))
    assert restored.breached
    with pytest.raises(BudgetExceeded):
        restored.reserve('agent', Usage())


async def test_rich_view_never_exposes_hidden_observations():
    from dreamrsi.models.policy import PolicyView
    from dreamrsi.replay import ReplayWorld, StrictReplay
    rsi = DreamRSI(agent=lambda task: {"secret": task},
                   evaluator=lambda result: 1, budget=Budget(model_calls=2))
    result = await rsi.run("future")
    world = ReplayWorld(result.tree)
    visible = StrictReplay()._build_view(
        world.tree, {world.tree.root_id}, None, 0, 1, world)
    assert len(visible.history) == 1
    assert 'future' not in json.dumps(visible.to_dict())
    restored = PolicyView.from_dict(json.loads(json.dumps(visible.to_dict())))
    assert restored.to_dict() == visible.to_dict()
    full = rsi._build_policy_view(result.tree, 3, 1)
    full.observations[result.tree.root_id]['diagnostics']['injected'] = True
    assert 'injected' not in result.tree.root.metadata


async def test_validation_task_overlap_rejected():
    from dreamrsi.errors import ConfigurationError
    rsi = DreamRSI(agent=lambda x: x, evaluator=float, validation=HoldoutPipeline([1]))
    with pytest.raises(ConfigurationError, match="overlaps"):
        await rsi.improve(1, rounds=1)

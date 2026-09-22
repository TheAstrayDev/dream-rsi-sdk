import copy

import pytest

from dreamrsi import Budget, DreamRSI, DreamRSIConfig
from dreamrsi.discovery import DiscoveryTree
from dreamrsi.models.policy import PolicyDecision
from dreamrsi.replay import ReplayWorld, StrictReplay


async def test_budget_aware_policy_has_shared_workers_and_logical_limits():
    seen = []

    class Policy:
        async def decide(self, view):
            seen.append(copy.deepcopy(view))
            if view.budget_remaining.model_calls <= 0:
                return PolicyDecision([], stop=True)
            return PolicyDecision([n.id for n in view.frontier])

    runtime = DreamRSI(
        agent=lambda x: x + 1, evaluator=float, policy=Policy(),
        budget=Budget(model_calls=5, max_parallelism=2, max_depth=1),
    )
    online = await runtime.run(0)
    online_views = seen.copy()
    seen.clear()
    replay = await runtime.replay(ReplayWorld(online.tree), Policy())
    assert online.costs.model_calls == replay.total_probes == 5
    assert len(online_views) == len(seen) == 5
    for live, offline in zip(online_views, seen, strict=True):
        assert live.max_parallelism == offline.max_parallelism == 2
        assert live.budget_remaining.model_calls == offline.budget_remaining.model_calls
        assert live.budget_remaining.max_nodes == offline.budget_remaining.max_nodes
        assert [n.depth for n in live.frontier] == [n.depth for n in offline.frontier] == [0]
    # K1 and K2 are intentionally independent in the original algorithm.
    assert online_views[0].budget_remaining.max_rounds == 100
    assert seen[0].budget_remaining.max_rounds == 1000


def fixture_world():
    tree = DiscoveryTree("limits")
    tree.create_root(node_id="r")
    tree.add_node("r", node_id="a", score=1)
    tree.add_node("r", node_id="hidden", score=2)
    tree.commit()
    return ReplayWorld(tree)


async def test_empty_boundary_only_consumes_round_and_never_hidden_budget():
    seen = []

    class Policy:
        async def decide(self, view):
            seen.append(view)
            return PolicyDecision(["r" if view.total_nodes == 1 else "a"])

    result = await StrictReplay(
        max_rounds=4, budget=Budget(model_calls=8, max_nodes=20),
    ).replay(fixture_world(), Policy())
    assert result.total_rounds == 4
    assert result.total_probes == 1
    assert [v.budget_remaining.model_calls for v in seen] == [8, 7, 7, 7]
    assert [v.budget_remaining.max_nodes for v in seen] == [19, 18, 18, 18]
    assert [v.budget_remaining.max_rounds for v in seen] == [4, 3, 2, 1]
    assert all("hidden" not in v.observations for v in seen)


@pytest.mark.parametrize("budget", [
    Budget(model_calls=0), Budget(evaluator_calls=0), Budget(max_nodes=1),
    Budget(max_depth=0), Budget(max_parallelism=0), Budget(max_rounds=0),
])
async def test_zero_capacity_never_invokes_policy(budget):
    class Policy:
        async def decide(self, view):
            raise AssertionError("Exhausted replay must not call policy")

    result = await StrictReplay(budget=budget).replay(fixture_world(), Policy())
    assert result.total_probes == result.total_rounds == 0


async def test_remaining_probe_capacity_truncates_a_legal_parallel_batch():
    tree = DiscoveryTree("batch")
    tree.create_root(node_id="r")
    tree.add_node("r", node_id="a", score=1)
    tree.add_node("r", node_id="b", score=2)
    tree.add_node("a", node_id="a1", score=3)
    tree.add_node("r", node_id="c", score=4)
    tree.add_node("a1", node_id="a2", score=5)
    tree.commit()

    class Policy:
        async def decide(self, view):
            return PolicyDecision([n.id for n in view.frontier])

    result = await StrictReplay(
        max_parallelism=2, budget=Budget(model_calls=4),
    ).replay(ReplayWorld(tree), Policy())
    assert [len(step.batch) for step in result.steps] == [1, 2, 1]
    assert result.total_probes == 4
    assert "a2" not in result.revealed_node_ids


def test_replay_configuration_identifies_limits_and_rejects_fake_billing():
    a = StrictReplay(budget=Budget(model_calls=2))
    b = StrictReplay(budget=Budget(model_calls=3))
    assert a.checkpoint_config() != b.checkpoint_config()
    with pytest.raises(ValueError, match="cannot simulate tokens"):
        StrictReplay(budget=Budget(tokens=10))
    runtime = DreamRSI(agent=lambda x: x, evaluator=float)
    assert runtime._get_replay().max_parallelism == 4
    custom = DreamRSI(
        agent=lambda x: x, evaluator=float,
        config=DreamRSIConfig(default_batch_size=8, replay_max_parallelism=2),
    )
    assert custom._get_replay()._workers() == 2

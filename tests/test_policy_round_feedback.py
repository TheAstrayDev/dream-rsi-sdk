import copy

from dreamrsi import Budget, DreamRSI, FunctionalAgentAdapter
from dreamrsi.discovery import DiscoveryTree
from dreamrsi.models.policy import PolicyDecision, PolicyView
from dreamrsi.replay import ReplayWorld, StrictReplay


async def test_last_round_reports_past_boundaries_without_exposing_hidden_branches():
    tree = DiscoveryTree("fixture")
    tree.create_root(node_id="r")
    tree.add_node("r", node_id="a", score=1)
    tree.add_node("a", node_id="b", score=2)
    tree.add_node("r", node_id="hidden", score=100)
    tree.commit()
    observed = []

    class Policy:
        async def decide(self, view):
            observed.append(copy.deepcopy(view))
            if view.last_round and not view.last_round["revealed_nodes"]:
                return PolicyDecision([], stop=True)
            return PolicyDecision([max(view.frontier, key=lambda node: node.depth).id])

    result = await StrictReplay(max_rounds=20).replay(ReplayWorld(tree), Policy())
    assert result.total_rounds == 3
    assert result.total_probes == 2
    assert observed[0].last_round is None
    assert observed[1].last_round == {
        "batch": ["r"],
        "revealed_nodes": ["a"],
        "best_score_before": None,
        "best_score_after": 1,
    }
    assert observed[-1].last_round["batch"] == ["b"]
    assert observed[-1].last_round["revealed_nodes"] == []
    assert all("hidden" not in view.observations for view in observed)
    restored = PolicyView.from_dict(observed[-1].to_dict())
    assert restored.last_round == observed[-1].last_round


async def test_online_last_round_has_the_same_schema_and_mutation_is_local():
    observed = []

    class Policy:
        async def decide(self, view):
            observed.append(copy.deepcopy(view))
            if view.last_round:
                view.last_round["batch"].clear()
            return PolicyDecision([max(view.frontier, key=lambda node: node.depth).id])

    runtime = DreamRSI(
        adapter=FunctionalAgentAdapter(lambda state: state / 2),
        evaluator=lambda x: -abs(x),
        policy=Policy(),
        budget=Budget(model_calls=3),
    )
    await runtime.run(8)
    assert observed[0].last_round is None
    assert observed[1].last_round["best_score_before"] is None
    assert observed[1].last_round["best_score_after"] == -4
    assert observed[2].last_round["best_score_before"] == -4
    assert observed[2].last_round["best_score_after"] == -2
    assert len(observed[2].last_round["revealed_nodes"]) == 1
    assert len(observed[2].last_round["batch"]) == 1

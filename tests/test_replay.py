import pytest

from dreamrsi import Budget
from dreamrsi.discovery import DiscoveryTree, NodeStatus, TreeError
from dreamrsi.errors import PolicyError
from dreamrsi.models import Budget as ModelBudget
from dreamrsi.models import DiscoveryNode
from dreamrsi.models import ReplayWorld as ModelWorld
from dreamrsi.models.policy import PolicyDecision, PolicyView
from dreamrsi.policies import BreadthFirstPolicy, RandomPolicy
from dreamrsi.replay import ReplayWorld, StrictReplay


def world():
    tree = DiscoveryTree("t")
    tree.create_root(node_id="r", state={"x": 0})
    tree.add_node("r", node_id="a", score=1)
    tree.add_node("a", node_id="b", score=3)
    tree.add_node("r", node_id="c", score=2)
    tree.commit()
    return ReplayWorld(tree)


def test_canonical_types():
    from dreamrsi.discovery import DiscoveryNode as TreeNode
    from dreamrsi.replay import PolicyView as ReplayView

    assert Budget is ModelBudget
    assert DiscoveryNode is TreeNode
    assert ModelWorld is ReplayWorld
    assert PolicyView is ReplayView


async def test_replay_score_coefficients():
    result = await StrictReplay(beta1=1, beta2=2).replay(world(), BreadthFirstPolicy(batch_size=2))
    assert result.revealed_node_ids == ["a", "c", "b"]
    assert result.total_probes == 3
    assert result.total_rounds == 2
    assert result.replay_score == 3


async def test_attempted_score_charges_unrecorded_live_call_without_changing_paper_default():
    class RecordedThenBoundary:
        async def decide(self, view):
            return PolicyDecision(expand=[("r", "a", "b")[view.rounds_used]])

    settings = dict(max_rounds=3, max_parallelism=1, beta1=1, beta2=0)
    paper = await StrictReplay(**settings).replay(world(), RecordedThenBoundary())
    live_cost = await StrictReplay(**settings, score_cost="attempted").replay(
        world(), RecordedThenBoundary()
    )
    assert paper.total_probes == live_cost.total_probes == 2
    assert paper.objective["attempted_expansions"] == 3
    assert paper.replay_score == 1
    assert live_cost.replay_score == 0
    assert live_cost.objective["charged_probes"] == 3
    assert StrictReplay(score_cost="attempted").checkpoint_config()["score_cost"] == "attempted"


async def test_attempted_mode_keeps_live_budget_after_recorded_tree_ends():
    tree = DiscoveryTree("short")
    tree.create_root(node_id="r")
    tree.add_node("r", node_id="a", score=1)
    tree.commit()

    seen_calls = []
    class KeepExpanding:
        async def decide(self, view):
            seen_calls.append(view.calls_used)
            return PolicyDecision(expand=["r"])

    policy = KeepExpanding()
    result = await StrictReplay(
        max_rounds=5,
        max_parallelism=1,
        score_cost="attempted",
        beta1=1,
        beta2=0,
        budget=Budget(model_calls=3, evaluator_calls=3, max_parallelism=1),
    ).replay(ReplayWorld(tree), policy)
    assert result.total_probes == 1
    assert result.objective["attempted_expansions"] == 3
    assert result.replay_score == -2
    assert seen_calls == [0, 1, 2]


async def test_replay_resets_rng_and_state():
    policy = RandomPolicy(seed=8, batch_size=2)
    replay = StrictReplay(max_rounds=5)
    w = world()
    a = await replay.replay(w, policy)
    b = await replay.replay(w, policy)
    assert a.steps == b.steps


async def test_no_hidden_frontier_leak_and_boundary_can_recover():
    class BoundaryThenRoot:
        async def decide(self, view):
            ids = {n.id for n in view.frontier}
            if view.round_number == 1:
                assert ids == {"r"}
                return PolicyDecision(expand=["r"])
            if view.round_number == 2:
                return PolicyDecision(expand=["a"])
            if view.round_number == 3:
                # b is a recorded terminal leaf: its boundary must not be hidden.
                assert ids == {"r", "b"}
                return PolicyDecision(expand=["b"])
            return PolicyDecision(expand=["r"])

    result = await StrictReplay().replay(world(), BoundaryThenRoot())
    assert result.total_rounds == 4
    assert result.total_probes == 3


@pytest.mark.parametrize("batch", [["b"], ["r", "r"]])
async def test_replay_rejects_illegal_actions(batch):
    class Invalid:
        async def decide(self, view):
            return PolicyDecision(expand=batch)

    with pytest.raises(PolicyError):
        await StrictReplay().replay(world(), Invalid())


def test_commit_and_serialization_are_isolated():
    tree = DiscoveryTree("t")
    root = tree.create_root(node_id="r", state={"values": [1]})
    tree.commit()
    root.state["values"].append(2)
    tree.root.state["values"].append(3)
    assert tree.root.state == {"values": [1]}
    rebuilt = DiscoveryTree.from_dict(tree.to_dict())
    assert rebuilt.to_dict() == tree.to_dict()
    assert rebuilt.root.status == NodeStatus.COMPLETED
    exported = tree.to_dict()
    rebuilt = DiscoveryTree.from_dict(exported)
    exported["nodes"]["r"]["state"]["values"].append(4)
    assert tree.root.state == rebuilt.root.state == {"values": [1]}


def test_tree_rejects_invalid_structure():
    tree = DiscoveryTree("t")
    tree.create_root(node_id="r")
    tree.add_node("r", node_id="a")
    tree.add_node("a", node_id="b")
    with pytest.raises(TreeError):
        tree.add_node("a", node_id="c")
    data = tree.to_dict()
    data["nodes"]["a"]["parent_id"] = "missing"
    with pytest.raises(TreeError):
        DiscoveryTree.from_dict(data)

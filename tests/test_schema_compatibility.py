"""Legacy DTOs remain readable; future schemas must never be silently reinterpreted."""

import copy
import hashlib
import json

import pytest

from dreamrsi import AdaptivePolicyMemory, Budget, DefaultMethod, DreamRSI, SQLiteStore
from dreamrsi.discovery import DiscoveryTree
from dreamrsi.errors import PolicyError
from dreamrsi.models.base import CostRecord, DreamCycle, Round, Run, Task
from dreamrsi.models.discovery import DiscoveryNode, NodeStatus
from dreamrsi.models.evaluation import Evaluation
from dreamrsi.models.objectives import ObjectiveResult
from dreamrsi.models.policy import NodeSummary, PolicyDecision, PolicyVersion, PolicyView
from dreamrsi.models.promotion import PromotionDecision, PromotionOutcome
from dreamrsi.models.replay import ReplayStep, ReplayTrajectory, ReplayWorldRecord
from dreamrsi.policies import GreedyPolicy
from dreamrsi.replay import ReplayWorld
from dreamrsi.storage import InMemoryStore

SUMMARY = NodeSummary("root", None, 0, 0.8, NodeStatus.COMPLETED, 0)
STEP = ReplayStep(1, ["root"], ["next"], 0.8, 1)
RECORDS = [
    Task("task"),
    Run("task", "tree", "policy"),
    Round("run", "cycle"),
    DreamCycle("task"),
    CostRecord(model_calls=2, input_tokens=4),
    Budget(model_calls=3),
    DiscoveryNode(id="root", observation={"quality": 0.8}),
    Evaluation(0.8),
    ObjectiveResult(0.8),
    PolicyVersion(name="policy"),
    PolicyDecision(["root"]),
    SUMMARY,
    PolicyView([SUMMARY], 0.8, 1, 0, 0.0, 0, budget_remaining=Budget(model_calls=3)),
    PromotionDecision("challenger", "incumbent", PromotionOutcome.REJECTED),
    ReplayWorldRecord("tree"),
    STEP,
    ReplayTrajectory("world", "policy", steps=[STEP]),
]


def _legacy(value):
    if isinstance(value, dict):
        return {key: _legacy(item) for key, item in value.items() if key != "_schema_version"}
    if isinstance(value, list):
        return [_legacy(item) for item in value]
    return value


@pytest.mark.parametrize("record", RECORDS, ids=lambda record: type(record).__name__)
@pytest.mark.parametrize("legacy", [False, True], ids=["current", "legacy"])
def test_dto_current_and_legacy_schema_roundtrip_preserves_data(record, legacy):
    original = record.to_dict()
    payload = _legacy(original) if legacy else copy.deepcopy(original)
    before = copy.deepcopy(payload)
    restored = type(record).from_dict(payload)
    assert restored.to_dict() == original
    assert payload == before


@pytest.mark.parametrize("record", RECORDS, ids=lambda record: type(record).__name__)
@pytest.mark.parametrize("version", ["2", "0", None, 1, True, {"version": "1"}])
def test_dto_rejects_unknown_or_malformed_explicit_schema(record, version):
    payload = record.to_dict()
    payload["_schema_version"] = version
    before = copy.deepcopy(payload)
    with pytest.raises(ValueError, match=f"Unsupported {type(record).__name__} schema version"):
        type(record).from_dict(payload)
    assert payload == before


@pytest.mark.parametrize("nested", ["frontier", "history", "budget_remaining"])
def test_policy_view_rejects_future_nested_schema(nested):
    payload = PolicyView(
        [SUMMARY], 0.8, 1, 0, 0.0, 0,
        history=[SUMMARY], budget_remaining=Budget(model_calls=3),
    ).to_dict()
    item = payload[nested][0] if isinstance(payload[nested], list) else payload[nested]
    item["_schema_version"] = "2"
    with pytest.raises(ValueError, match="schema version"):
        PolicyView.from_dict(payload)


def test_replay_rejects_future_step_before_interpreting_its_fields():
    payload = ReplayTrajectory("world", "policy", steps=[STEP]).to_dict()
    payload["steps"][0] = {"_schema_version": "2", "future_step_format": "different"}
    with pytest.raises(ValueError, match="Unsupported ReplayStep schema version"):
        ReplayTrajectory.from_dict(payload)


def _tree():
    tree = DiscoveryTree()
    root = tree.create_root(state={"seed": 1})
    tree.add_node(root.id, score=0.8, observation={"quality": 0.8})
    tree.commit()
    return tree


def test_tree_preserves_legacy_data_and_rejects_future_container_and_node():
    tree = _tree()
    original = tree.to_dict()
    assert DiscoveryTree.from_dict(_legacy(original)).to_dict() == original
    future = copy.deepcopy(original)
    future["_schema_version"] = "2"
    future["nodes"] = "new layout"
    with pytest.raises(ValueError, match="Unsupported DiscoveryTree schema version"):
        DiscoveryTree.from_dict(future)
    future = copy.deepcopy(original)
    future["nodes"][tree.root_id]["_schema_version"] = "2"
    with pytest.raises(ValueError, match="Unsupported DiscoveryNode schema version"):
        DiscoveryTree.from_dict(future)


@pytest.mark.parametrize("future", [False, True], ids=["legacy", "future"])
async def test_sqlite_campaign_preserves_legacy_and_refuses_future_tree_before_calls(
    tmp_path, future,
):
    calls = []

    def agent(task):
        calls.append(task)
        return task

    def runtime(store, resume=False):
        return DreamRSI(
            agent=agent, evaluator=float, store=store,
            budget=Budget(model_calls=1), method=DefaultMethod("schema", resume=resume),
        )

    database = tmp_path / "campaign.db"
    store = SQLiteStore(database)
    first = await runtime(store).improve(1, rounds=1)
    checkpoint = await store.get_checkpoint("schema")
    for world in checkpoint["worlds"]:
        world["tree"].pop("_schema_version", None)
        for node in world["tree"]["nodes"].values():
            node.pop("_schema_version", None)
    if future:
        checkpoint["worlds"][0]["tree"]["_schema_version"] = "2"
    await store.save_checkpoint("schema", checkpoint)
    await store.close()
    reopened = SQLiteStore(database)
    try:
        if future:
            with pytest.raises(ValueError, match="Unsupported DiscoveryTree schema version"):
                await runtime(reopened, resume=True).improve(1, rounds=1)
        else:
            restored = await runtime(reopened, resume=True).improve(1, rounds=1)
            assert restored.worlds[0].tree.to_dict() == first.worlds[0].tree.to_dict()
            assert restored.costs.model_calls == 1
        assert calls == [1]
        assert await reopened.get_checkpoint("schema") == checkpoint
    finally:
        await reopened.close()


def _digest(value):
    payload = json.dumps(value, sort_keys=True, allow_nan=False, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


async def test_valid_checksum_does_not_allow_future_bundled_tree_or_replace_champion(tmp_path):
    def memory():
        return AdaptivePolicyMemory(
            store=InMemoryStore(), runtime_factory=lambda task, policy: None,
            family_of=lambda task: "labs", raw_quality=lambda task, result: 0.8,
            minimum_quality=lambda task: 0.5,
        )

    sender, receiver = memory(), memory()
    task = {"kind": "labs"}
    await sender.remember(task, GreedyPolicy())
    await sender._remember_world("labs", task, ReplayWorld(_tree()))
    await receiver.remember(task, GreedyPolicy(), raw_quality=0.9)
    previous = await receiver.store.get_checkpoint(receiver._key("labs"))
    path = tmp_path / "future-tree.dreamrsi.json"
    await sender.export_bundle(task, path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    item = bundle["worlds"][0]
    item["world"]["tree"]["_schema_version"] = "2"
    item["sha256"] = _digest({"task": item["task"], "world": item["world"]})
    bundle.pop("sha256")
    bundle["sha256"] = _digest(bundle)
    path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(PolicyError, match="Unsupported DiscoveryTree schema version"):
        await receiver.import_bundle(path, task=task)
    assert await receiver.store.get_checkpoint(receiver._key("labs")) == previous
    assert await receiver._worlds("labs") == []

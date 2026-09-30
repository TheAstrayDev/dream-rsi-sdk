import json
import math
from itertools import product

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dreamrsi import (
    AdaptivePolicyMemory,
    Budget,
    DefaultMethod,
    DeveloperConfig,
    DreamRSI,
    DreamRSIConfig,
    HoldoutPipeline,
    LLMPolicyDeveloper,
    PolicyMemorySettings,
)
from dreamrsi.adapters import FunctionalAgentAdapter
from dreamrsi.artifacts import PolicyArtifact, PolicyCodec, SourcePolicy
from dreamrsi.discovery import DiscoveryTree
from dreamrsi.errors import ConfigurationError, PolicyError
from dreamrsi.models.replay import ReplayTrajectory
from dreamrsi.optimization import DeterministicPolicyOptimizer
from dreamrsi.policies import FixedParallelPolicy, PrefixPolicy
from dreamrsi.replay import ReplayWorld, StrictReplay
from dreamrsi.sandbox import PolicySandbox
from dreamrsi.storage import SQLiteStore


def plateau_step(state, context):
    del context
    depth = state.get("depth", 0) + 1
    # A nonlinear score curve with a known plateau. This is a deterministic
    # discovery fixture, never a substitute for measuring a real LLM agent.
    quality = 1 - math.exp(-(min(depth, state["peak"]) / state["peak"]) ** 2)
    if state.get("late") is not None and depth >= state["late"]:
        quality += 0.1
    return {**state, "depth": depth, "quality": quality}


def fixture(policy=None, **kwargs):
    return DreamRSI(
        adapter=FunctionalAgentAdapter(plateau_step),
        evaluator=lambda observation: observation["quality"],
        policy=policy or FixedParallelPolicy(branches=1, max_depth=32),
        budget=Budget(model_calls=32, max_nodes=33, max_depth=32, max_parallelism=1),
        config=DreamRSIConfig(replay_max_rounds=32, replay_max_parallelism=1),
        method=DefaultMethod(online=False),
        **kwargs,
    )


async def test_prefix_synthesis_preserves_full_batches_and_model_quality():
    tree = DiscoveryTree()
    tree.create_root(node_id="r")
    a = tree.add_node("r", node_id="a", score=-3)
    tree.add_node(a.id, node_id="a2", score=-1)
    b = tree.add_node("r", node_id="b", score=-2)
    tree.add_node(b.id, node_id="b2", score=-4)
    tree.commit()
    replay = StrictReplay(max_rounds=8, max_parallelism=2)
    incumbent = FixedParallelPolicy(branches=2, max_depth=2)
    full = await replay.replay(ReplayWorld(tree), incumbent)
    variants = await DeterministicPolicyOptimizer(num_variants=5).generate(incumbent, [full])
    prefix = next(p for p in variants if isinstance(p, PrefixPolicy))
    short = await replay.replay(ReplayWorld(tree), prefix)
    assert short.best_score == full.best_score == -1
    assert [(s.batch, s.revealed_nodes) for s in short.steps] == [
        (s.batch, s.revealed_nodes) for s in full.steps[: prefix.max_rounds]
    ]
    assert short.total_probes < full.total_probes
    assert len(variants) == 5


async def test_generic_source_prefix_runs_in_sandbox_and_survives_codec():
    source = """def decide(view):
    node = max(view["frontier"], key=lambda n: n["depth"])
    return {"expand": [node["id"]]}
"""
    incumbent = SourcePolicy(PolicyArtifact(source), PolicySandbox())
    original = await fixture(incumbent).run({"peak": 7})
    replay = StrictReplay(max_rounds=32, max_parallelism=1)
    full = await replay.replay(ReplayWorld(original.tree), incumbent)
    variants = await DeterministicPolicyOptimizer(num_variants=1).generate(incumbent, [full])
    assert len(variants) == 1
    assert isinstance(variants[0], PrefixPolicy)
    assert variants[0].max_rounds == 7
    codec = PolicyCodec()
    restored = codec.decode(json.loads(json.dumps(codec.encode(variants[0]))))
    live = await fixture(restored).run({"peak": 6})
    assert live.costs.model_calls == 7
    assert live.best_score == original.best_score
    assert restored.policy.artifact.source_hash == incumbent.artifact.source_hash
    # A promoted source prefix remains eligible for subsequent cheap searches.
    again = await replay.replay(ReplayWorld(original.tree), restored)
    await DeterministicPolicyOptimizer().generate(restored, [again])


async def test_single_candidate_budget_keeps_evidence_derived_one_round_prefix():
    original = await fixture().run({"peak": 1})
    incumbent = FixedParallelPolicy(branches=1, max_depth=32)
    full = await StrictReplay(max_rounds=32).replay(ReplayWorld(original.tree), incumbent)
    candidates = await DeterministicPolicyOptimizer(num_variants=1).generate(incumbent, [full])
    assert len(candidates) == 1
    assert isinstance(candidates[0], PrefixPolicy)
    assert candidates[0].policy is incumbent
    assert candidates[0].max_rounds == 1


@pytest.mark.parametrize("enabled", [True, False])
async def test_runtime_switch_controls_prefix_search_before_paid_developer(enabled):
    requests = []

    async def generate(request):
        requests.append(request)
        return """def decide(view):
    if view["rounds_used"] >= 7:
        return {"expand": [], "stop": True}
    node = max(view["frontier"], key=lambda n: n["depth"])
    return {"expand": [node["id"]]}
"""

    developer = LLMPolicyDeveloper(
        generate, config=DeveloperConfig(revisions=1, response_format="python")
    )
    rt = fixture(policy_optimizer=developer)
    rt._config.optimizer_prefix_search = enabled
    result = await rt.run({"peak": 7})
    await rt.record_world({"peak": 7}, result)
    improved = await rt.improve({"peak": 7})
    assert len(requests) == improved.costs.developer_calls == (0 if enabled else 1)
    assert improved.champion_policy is not None
    assert isinstance(improved.champion_policy, PrefixPolicy if enabled else SourcePolicy)


def test_runtime_prefix_switch_is_strict_boolean():
    with pytest.raises(ConfigurationError, match="optimizer_prefix_search"):
        DreamRSIConfig(optimizer_prefix_search=1)


@pytest.mark.parametrize("cap", [True, -1, 1.5, None])
def test_invalid_prefix_limits_are_rejected(cap):
    with pytest.raises(ValueError):
        PrefixPolicy(FixedParallelPolicy(), cap)
    with pytest.raises(PolicyError):
        PolicyCodec().decode({
            "kind": "prefix", "max_rounds": cap,
            "policy": PolicyCodec().encode(FixedParallelPolicy()),
        })


async def test_custom_raw_quality_does_not_follow_composite_score_peak():
    tree = DiscoveryTree()
    root = tree.create_root()
    for depth in range(1, 9):
        root = tree.add_node(
            root.id, score=float(depth),
            observation={"raw": min(depth, 3)},
        )
    tree.commit()
    incumbent = FixedParallelPolicy(branches=1, max_depth=8)
    full = await StrictReplay(max_rounds=8).replay(ReplayWorld(tree), incumbent)
    def metric(record):
        return record["observation"]["raw"]
    variants = await DeterministicPolicyOptimizer(quality_metric=metric).generate(
        incumbent, [full]
    )
    prefix = next(p for p in variants if isinstance(p, PrefixPolicy))
    assert prefix.max_rounds == 3
    short = await StrictReplay(max_rounds=8).replay(ReplayWorld(tree), prefix)
    pipeline = HoldoutPipeline([1], quality_metric=metric, quality_metric_id="raw")
    assert pipeline.quality_from_trajectory(short) == pipeline.quality_from_trajectory(full) == 3
    assert short.best_score < full.best_score


async def test_different_worlds_use_maximum_required_prefix_and_fewer_total_calls():
    incumbent = FixedParallelPolicy(branches=1, max_depth=32)
    replay = StrictReplay(max_rounds=32, max_parallelism=1)
    full = [
        await replay.replay(ReplayWorld((await fixture().run({"peak": peak})).tree), incumbent)
        for peak in (3, 5, 7)
    ]
    variants = await DeterministicPolicyOptimizer(num_variants=1).generate(incumbent, full)
    assert variants[0].max_rounds == 7
    for trajectory in full:
        assert next(s.round_number for s in trajectory.steps
                    if s.best_score_so_far == trajectory.best_score) <= 7


async def test_unseen_delayed_payoff_rejects_prefix_without_developer_call():
    runtime = fixture(validation=HoldoutPipeline([{"peak": 5, "late": 12}]))
    run = await runtime.run({"peak": 7})
    await runtime.record_world({"peak": 7}, run)
    result = await runtime.improve({"peak": 7})
    assert result.champion_policy is None
    assert result.costs.developer_calls == 0
    assert result.costs.model_calls == 64  # history acquisition plus full holdout
    assert runtime.validation.used == 1
    rejected = [p for p in await runtime.list_policies() if "promotion" in p.metadata]
    assert rejected[-1].metadata["promotion"]["outcome"] == "REJECTED"


async def test_prefix_campaign_resume_keeps_saved_program_and_charged_history(tmp_path):
    store = SQLiteStore(tmp_path / "prefix.sqlite")
    task, held = {"peak": 7}, {"peak": 5}
    runtime = fixture(store=store, validation=HoldoutPipeline([held]))
    runtime._method = DefaultMethod("prefix", online=False)
    run = await runtime.run(task)
    await runtime.record_world(task, run)
    first = await runtime.improve(task)
    assert first.champion_policy.max_rounds == 7
    assert first.costs.model_calls == 64
    await store.close()
    reopened = SQLiteStore(tmp_path / "prefix.sqlite")
    resumed = fixture(store=reopened, validation=HoldoutPipeline([held]))
    resumed._method = DefaultMethod("prefix", resume=True, online=False)
    recovered = await resumed.improve(task)
    assert recovered.champion_policy.max_rounds == 7
    assert recovered.costs.model_calls == 64
    assert resumed.validation.used == 1
    live = await resumed.run({"peak": 6})
    assert live.costs.model_calls == 7
    await reopened.close()


async def test_portable_prefix_bundle_is_used_without_repeat_training(tmp_path):
    task = {"peak": 7, "seed": 1}

    def memory(store):
        return AdaptivePolicyMemory(
            store=store,
            runtime_factory=lambda task, policy: fixture(
                policy, validation=HoldoutPipeline([{"peak": 5, "seed": task["seed"] + 100}])
            ),
            family_of=lambda task: "nonlinear-fixture",
            raw_quality=lambda task, result: result.best_score,
            minimum_quality=lambda task: 1 - math.exp(-1),
            settings=PolicyMemorySettings(allow_training=lambda *args: False),
        )

    first_store = SQLiteStore(tmp_path / "author.sqlite")
    author = memory(first_store)
    await author.remember(task, PrefixPolicy(FixedParallelPolicy(1, 32), 7), origin="promoted")
    result = await fixture().run(task)
    await author._remember_world("nonlinear-fixture", task, ReplayWorld(result.tree))
    bundle = tmp_path / "prefix.dreamrsi.json"
    await author.export_bundle(task, bundle)
    await first_store.close()

    receiver_store = SQLiteStore(tmp_path / "receiver.sqlite")
    receiver = memory(receiver_store)
    await receiver.import_bundle(bundle, task={"peak": 6, "seed": 2})
    reused = await receiver.run({"peak": 6, "seed": 2})
    assert reused.reused_policy and not reused.trained and not reused.degraded
    assert reused.result.costs.model_calls == 7
    assert reused.result.costs.developer_calls == 0
    assert reused.improvement is None
    assert isinstance(await receiver.load("nonlinear-fixture"), PrefixPolicy)
    await receiver_store.close()


@settings(max_examples=100, deadline=None)
@given(st.lists(st.lists(st.integers(-2, 2), min_size=1, max_size=3),
                min_size=1, max_size=3))
def test_branch_order_bound_matches_exhaustive_recorded_state_oracle(branches):
    tree = DiscoveryTree()
    root = tree.create_root()
    for branch in branches:
        parent = root
        for score in branch:
            parent = tree.add_node(parent.id, score=score)
    tree.commit()
    world = ReplayWorld(tree)
    # All reachable recorded states: later root branches cannot open before
    # earlier ones; each opened branch is a contiguous chain prefix.
    states = []
    for depths in product(*(range(len(branch) + 1) for branch in branches)):
        if any(depths[j] and not depths[j - 1] for j in range(1, len(depths))):
            continue
        qualities = [v for branch, depth in zip(branches, depths, strict=True)
                     for v in branch[:depth]]
        if qualities:
            states.append((sum(depths), max(qualities)))
    for cap in range(1, sum(map(len, branches)) + 1):
        trajectory = ReplayTrajectory(world.world_id, "incumbent", total_probes=cap)
        for target in range(-2, 3):
            possible = any(
                q >= target and calls < cap or q > target and calls <= cap
                for calls, q in states
            )
            actual = DefaultMethod._has_replay_opportunity(world, trajectory, None, target)
            assert actual == possible


async def test_late_root_best_is_saturated_and_does_not_spend_developer_budget():
    class Developer:
        calls = 0

        async def develop(self, *args, **kwargs):
            self.calls += 1
            return []

    tree = DiscoveryTree()
    root = tree.create_root()
    for score in (0.1, 0.2, 0.9):
        tree.add_node(root.id, score=score)
    tree.commit()
    developer = Developer()
    runtime = fixture(
        FixedParallelPolicy(branches=3, max_depth=1), policy_optimizer=developer
    )
    await runtime.add_recorded_world(0, ReplayWorld(tree))
    result = await runtime.improve(0)
    assert result.champion_policy is None
    assert developer.calls == 0

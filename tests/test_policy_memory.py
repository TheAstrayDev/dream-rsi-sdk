from types import SimpleNamespace

import pytest

from dreamrsi import (
    AdaptivePolicyMemory,
    Budget,
    DefaultMethod,
    DreamRSI,
    HoldoutPipeline,
    PolicyMemorySettings,
    SQLiteStore,
)
from dreamrsi.discovery import DiscoveryTree
from dreamrsi.errors import ConfigurationError, PolicyError
from dreamrsi.policies import DepthFirstPolicy, GreedyPolicy
from dreamrsi.replay import ReplayWorld


async def test_champion_is_reused_after_restart_and_old_version_is_preserved(tmp_path):
    path = tmp_path / "policies.db"
    outcomes = iter(
        [
            (0.9, GreedyPolicy()),
            (0.85, None),
            (0.5, None),
            (0.4, DepthFirstPolicy()),
        ]
    )
    seen_policies = []
    training_calls = []
    imported = []

    def factory(task, policy):
        seen_policies.append(policy)
        score, candidate = next(outcomes)
        current_seed = task["seed"]

        class Runtime:
            _method = SimpleNamespace(online=False)
            validation = HoldoutPipeline([{"kind": task["kind"], "seed": current_seed + 100}])

            async def run(self, task):
                tree = DiscoveryTree()
                root = tree.create_root()
                tree.add_node(root.id, score=score)
                tree.commit()
                return SimpleNamespace(best_score=score, tree=tree)

            async def record_world(self, task, result):
                training_calls.append((task["seed"], result.best_score))
                return ReplayWorld(result.tree)

            async def add_recorded_world(self, task, world):
                imported.append((current_seed, task["seed"], world.tree.tree_id))

            async def improve(self, task, rounds):
                assert rounds == 1
                return SimpleNamespace(champion_policy=candidate)

        return Runtime()

    def memory(store):
        return AdaptivePolicyMemory(
            store=store,
            runtime_factory=factory,
            family_of=lambda task: task["kind"],
            raw_quality=lambda task, result: result.best_score,
            minimum_quality=lambda task: 0.8,
        )

    first_store = SQLiteStore(path)
    first = await memory(first_store).run({"kind": "labs", "seed": 1})
    assert first.trained and first.promoted and not first.reused_policy
    await first_store.close()

    reopened = SQLiteStore(path)
    manager = memory(reopened)
    good = await manager.run({"kind": "labs", "seed": 2})
    assert good.reused_policy and not good.trained and good.improvement is None
    assert good.policy_origin == "promoted" and good.quality_floor == 0.8
    assert not good.degraded
    assert isinstance(seen_policies[1], GreedyPolicy)

    failed = await manager.run({"kind": "labs", "seed": 3})
    assert failed.trained and not failed.promoted
    assert failed.degraded
    assert isinstance(await manager.load("labs"), GreedyPolicy)

    upgraded = await manager.run({"kind": "labs", "seed": 4})
    assert upgraded.trained and upgraded.promoted
    assert isinstance(await manager.load("labs"), DepthFirstPolicy)
    entry = await reopened.get_checkpoint(manager._key("labs"))
    assert len(entry["versions"]) == 2
    assert entry["versions"][0]["policy"]["name"] == "GreedyPolicy"
    assert training_calls == [(1, 0.9), (2, 0.85), (3, 0.5), (4, 0.4)]
    assert {(current, previous) for current, previous, _ in imported} >= {
        (3, 1),
        (3, 2),
        (4, 1),
        (4, 2),
        (4, 3),
    }
    await reopened.close()


async def test_adaptive_run_requires_validation_before_agent_call():
    calls = []

    class Runtime:
        validation = None
        _method = SimpleNamespace(online=False)

        async def run(self, task):
            calls.append(task)

    from dreamrsi.storage import InMemoryStore

    manager = AdaptivePolicyMemory(
        store=InMemoryStore(),
        runtime_factory=lambda task, policy: Runtime(),
        family_of=lambda task: "family",
        raw_quality=lambda task, result: 1.0,
        minimum_quality=lambda task: 0.5,
    )
    with pytest.raises(ConfigurationError, match="independent validation"):
        await manager.run({"kind": "family"})
    assert calls == []


async def test_policy_memory_detects_corrupt_saved_version():
    from dreamrsi.storage import InMemoryStore

    store = InMemoryStore()
    manager = AdaptivePolicyMemory(
        store=store,
        runtime_factory=lambda task, policy: None,
        family_of=lambda task: "family",
        raw_quality=lambda task, result: 1.0,
        minimum_quality=lambda task: 0.5,
    )
    await manager.remember({}, GreedyPolicy())
    entry = await store.get_checkpoint(manager._key("family"))
    entry["versions"][0]["policy"]["name"] = "DepthFirstPolicy"
    await store.save_checkpoint(manager._key("family"), entry)
    with pytest.raises(PolicyError, match="integrity"):
        await manager.load("family")


async def test_policy_filter_falls_back_to_older_accepted_version():
    from dreamrsi.storage import InMemoryStore

    store = InMemoryStore()
    memory = AdaptivePolicyMemory(
        store=store,
        runtime_factory=lambda task, policy: None,
        family_of=lambda task: task["kind"],
        raw_quality=lambda task, result: 1.0,
        minimum_quality=lambda task: 0.5,
    )
    task = {"kind": "labs"}
    assert await memory.remember(task, GreedyPolicy(), origin="incumbent", raw_quality=0.7)
    assert await memory.remember(task, DepthFirstPolicy(), origin="promoted", raw_quality=0.8)

    filtered = AdaptivePolicyMemory(
        store=store,
        runtime_factory=lambda task, policy: None,
        family_of=lambda task: task["kind"],
        raw_quality=lambda task, result: 1.0,
        minimum_quality=lambda task: 0.5,
        settings=PolicyMemorySettings(
            accept_policy=lambda task, policy, origin, quality: origin == "incumbent"
        ),
    )
    assert isinstance(await filtered.load("labs", task=task), GreedyPolicy)
    assert isinstance(await memory.load("labs", task=task), DepthFirstPolicy)


async def test_imported_training_world_is_reused_without_agent_call():
    calls = []

    def agent(task):
        calls.append(task)
        return task["score"]

    first = DreamRSI(agent=agent, evaluator=float, budget=Budget(model_calls=1))
    task = {"kind": "labs", "score": 1.0}
    run = await first.run(task)
    world = await first.record_world(task, run)

    second = DreamRSI(
        agent=agent,
        evaluator=float,
        budget=Budget(model_calls=1),
        validation=HoldoutPipeline([{"kind": "labs", "score": 9.0}]),
        method=DefaultMethod(online=False),
    )
    assert await second.add_recorded_world(task, world) is await second.add_recorded_world(
        task, world
    )
    assert len(second._worlds) == 1
    assert calls == [task]
    with pytest.raises(ConfigurationError, match="overlaps"):
        await second.add_recorded_world({"kind": "labs", "score": 9.0}, world)


async def test_real_runtime_reuses_saved_champion_without_training(tmp_path):
    path = tmp_path / "memory.sqlite"
    calls = []

    def factory(task, saved_policy):
        def agent(item):
            calls.append(item["seed"])
            return item["score"]

        return DreamRSI(
            agent=agent,
            evaluator=float,
            policy=saved_policy or GreedyPolicy(),
            budget=Budget(model_calls=1),
            validation=HoldoutPipeline([{"kind": "labs", "seed": task["seed"] + 100}]),
            method=DefaultMethod(online=False),
        )

    def memory(store):
        return AdaptivePolicyMemory(
            store=store,
            runtime_factory=factory,
            family_of=lambda task: task["kind"],
            raw_quality=lambda task, run: run.best_score,
            minimum_quality=lambda task: 0.5,
        )

    old = SQLiteStore(path)
    await memory(old).remember({"kind": "labs"}, GreedyPolicy())
    await old.close()

    new = SQLiteStore(path)
    result = await memory(new).run({"kind": "labs", "seed": 2, "score": 1.0})
    assert result.reused_policy and not result.trained
    assert result.result.costs.model_calls == 1
    assert calls == [2]
    assert len(await memory(new)._worlds("labs")) == 1
    await new.close()


async def test_policy_bundle_transfers_all_versions_and_replay_tree(tmp_path):
    from dreamrsi.storage import InMemoryStore

    task = {"kind": "labs"}

    def memory(store):
        return AdaptivePolicyMemory(
            store=store,
            runtime_factory=lambda task, policy: None,
            family_of=lambda item: item["kind"],
            raw_quality=lambda item, result: 1.0,
            minimum_quality=lambda item: 0.5,
        )

    source = memory(InMemoryStore())
    assert await source.remember(task, GreedyPolicy(), origin="incumbent", raw_quality=0.8)
    assert await source.remember(task, DepthFirstPolicy(), origin="promoted", raw_quality=0.9)
    from dreamrsi import PolicyArtifact, PolicySandbox, SourcePolicy

    source_policy = SourcePolicy(
        PolicyArtifact('def decide(view):\n    return {"expand": [], "stop": True}\n'),
        PolicySandbox(),
    )
    assert await source.remember(task, source_policy, origin="promoted", raw_quality=0.9)
    tree = DiscoveryTree()
    root = tree.create_root(state={"seed": 1})
    tree.add_node(root.id, state={"seed": 2}, score=0.9)
    tree.commit()
    await source._remember_world("labs", {"kind": "labs", "seed": 1}, ReplayWorld(tree))

    path = tmp_path / "shared" / "labs.dreamrsi.json"
    exported = await source.export_bundle(task, path)
    assert exported == {
        "path": str(path),
        "family": "labs",
        "policies": 3,
        "worlds": 1,
    }

    target = memory(InMemoryStore())
    imported = await target.import_bundle(path, task=task)
    assert imported == {"family": "labs", "policies": 3, "worlds": 1}
    loaded_policy = await target.load("labs", task=task)
    assert isinstance(loaded_policy, SourcePolicy)
    assert loaded_policy.artifact.source == source_policy.artifact.source
    versions = await target.store.get_checkpoint(target._key("labs"))
    worlds = await target._worlds("labs")
    assert len(versions["versions"]) == 3
    assert versions["active"] == 2
    assert worlds[0]["world"]["tree"]["tree_id"] == tree.tree_id

    # Importing the same file twice is safe and does not duplicate saved data.
    assert await target.import_bundle(path, task=task) == {
        "family": "labs",
        "policies": 0,
        "worlds": 0,
    }
    assert len(await target._worlds("labs")) == 1

    calls = []

    def runtime_factory(task, policy):
        class Runtime:
            _method = SimpleNamespace(online=False)
            validation = HoldoutPipeline([{"kind": "labs", "seed": task["seed"] + 100}])

            async def run(self, task):
                calls.append(("run", policy))
                tree = DiscoveryTree()
                root = tree.create_root()
                tree.add_node(root.id, score=0.8)
                tree.commit()
                return SimpleNamespace(best_score=0.8, tree=tree)

            async def record_world(self, task, result):
                return ReplayWorld(result.tree)

            async def improve(self, task, rounds):
                calls.append(("train", rounds))
                raise AssertionError("A passing imported policy should not be retrained")

        return Runtime()

    receiver = AdaptivePolicyMemory(
        store=target.store,
        runtime_factory=runtime_factory,
        family_of=lambda item: item["kind"],
        raw_quality=lambda item, result: result.best_score,
        minimum_quality=lambda item: 0.5,
    )
    reused = await receiver.run({"kind": "labs", "seed": 3})
    assert reused.reused_policy and not reused.trained
    assert isinstance(calls[0][1], SourcePolicy)
    assert calls == [("run", calls[0][1])]


async def test_policy_bundle_rejects_corruption_family_mismatch_and_champion_overwrite(tmp_path):
    from dreamrsi.storage import InMemoryStore

    def memory(store):
        return AdaptivePolicyMemory(
            store=store,
            runtime_factory=lambda task, policy: None,
            family_of=lambda item: item["kind"],
            raw_quality=lambda item, result: 1.0,
            minimum_quality=lambda item: 0.5,
        )

    source = memory(InMemoryStore())
    task = {"kind": "labs"}
    await source.remember(task, GreedyPolicy())
    path = tmp_path / "policy.json"
    await source.export_bundle(task, path)

    wrong_family = memory(InMemoryStore())
    with pytest.raises(ConfigurationError, match="does not match"):
        await wrong_family.import_bundle(path, task={"kind": "packing"})

    corrupted = path.read_text(encoding="utf-8").replace('"family":"labs"', '"family":"packing"')
    path.write_text(corrupted, encoding="utf-8")
    with pytest.raises(PolicyError, match="integrity"):
        await wrong_family.import_bundle(path, task=task)

    await source.export_bundle(task, path)
    occupied = memory(InMemoryStore())
    await occupied.remember(task, DepthFirstPolicy())
    with pytest.raises(ConfigurationError, match="fresh policy-memory namespace"):
        await occupied.import_bundle(path, task=task)
    assert isinstance(await occupied.load("labs", task=task), DepthFirstPolicy)


async def test_validation_task_cannot_be_reused_across_improvements():
    from dreamrsi.storage import InMemoryStore

    manager = AdaptivePolicyMemory(
        store=InMemoryStore(),
        runtime_factory=lambda task, policy: None,
        family_of=lambda task: "labs",
        raw_quality=lambda task, run: 1.0,
        minimum_quality=lambda task: 0.5,
    )
    heldout = HoldoutPipeline([{"kind": "labs", "seed": 10}])
    await manager._reserve_holdouts("labs", heldout)
    with pytest.raises(ConfigurationError, match="reserved"):
        await manager._reserve_holdouts("labs", heldout)


async def test_unpromoted_two_step_incumbent_is_saved_and_reused(tmp_path):
    path = tmp_path / "memory.sqlite"
    seen = []
    improvements = []

    def factory(task, saved):
        seen.append(saved)

        class Runtime:
            _method = SimpleNamespace(online=False)
            validation = HoldoutPipeline([{"kind": "labs", "seed": task["seed"] + 100}])

            def _get_policy(self):
                return saved or GreedyPolicy()

            async def run(self, task):
                tree = DiscoveryTree()
                root = tree.create_root()
                first = tree.add_node(root.id, score=0.2)
                tree.add_node(first.id, score=task["score"])
                tree.commit()
                return SimpleNamespace(best_score=task["score"], tree=tree)

            async def record_world(self, task, result):
                return ReplayWorld(result.tree)

            async def add_recorded_world(self, task, world):
                pass

            async def improve(self, task, rounds):
                improvements.append(task["seed"])
                return SimpleNamespace(champion_policy=None)

        return Runtime()

    def memory(store):
        return AdaptivePolicyMemory(
            store=store,
            runtime_factory=factory,
            family_of=lambda task: task["kind"],
            raw_quality=lambda task, result: result.best_score,
            minimum_quality=lambda task: 0.3,
        )

    first_store = SQLiteStore(path)
    first = await memory(first_store).run({"kind": "labs", "seed": 1, "score": 0.8})
    assert first.trained and first.incumbent_saved and not first.promoted
    assert isinstance(await memory(first_store).load("labs"), GreedyPolicy)
    await first_store.close()

    reopened = SQLiteStore(path)
    second = await memory(reopened).run({"kind": "labs", "seed": 2, "score": 0.75})
    assert second.reused_policy and not second.trained and not second.promoted
    assert isinstance(seen[1], GreedyPolicy)
    assert improvements == [1]
    await reopened.close()


def _configurable_memory(store, settings, calls):
    def factory(task, saved):
        class Runtime:
            _method = SimpleNamespace(online=False)
            validation = HoldoutPipeline([{"kind": "labs", "seed": task["seed"] + 100}])

            def _get_policy(self):
                return saved or GreedyPolicy()

            async def run(self, task):
                tree = DiscoveryTree()
                root = tree.create_root()
                tree.add_node(root.id, score=task["score"])
                tree.commit()
                return SimpleNamespace(best_score=task["score"], tree=tree)

            async def record_world(self, task, result):
                calls.append(("record", task["seed"]))
                return ReplayWorld(result.tree)

            async def add_recorded_world(self, task, world):
                calls.append(("import", task["seed"]))

            async def improve(self, task, rounds):
                calls.append(("improve", task["seed"]))
                return SimpleNamespace(champion_policy=None)

        return Runtime()

    return AdaptivePolicyMemory(
        store=store,
        runtime_factory=factory,
        family_of=lambda task: task["kind"],
        raw_quality=lambda task, result: result.best_score,
        minimum_quality=lambda task: 0.5,
        settings=settings,
    )


async def test_memory_save_and_reuse_switches_are_independent():
    from dreamrsi.storage import InMemoryStore

    store = InMemoryStore()
    calls = []
    memory = _configurable_memory(
        store,
        PolicyMemorySettings(
            save_worlds=False,
            reuse_worlds=False,
            save_policies=False,
            reuse_policies=False,
        ),
        calls,
    )
    first = await memory.run({"kind": "labs", "seed": 1, "score": 0.8})
    second = await memory.run({"kind": "labs", "seed": 2, "score": 0.9})
    assert first.trained and second.trained
    assert not first.incumbent_saved and not second.reused_policy
    assert calls == [("record", 1), ("improve", 1), ("record", 2), ("improve", 2)]
    assert await memory._worlds("labs") == []
    assert await store.get_checkpoint(memory._key("labs")) is None


async def test_training_budget_gate_preserves_degradation_signal_without_improvement():
    from dreamrsi.storage import InMemoryStore

    calls = []
    memory = _configurable_memory(
        InMemoryStore(),
        PolicyMemorySettings(allow_training=lambda task, policy, quality, floor: False),
        calls,
    )
    result = await memory.run({"kind": "labs", "seed": 1, "score": 0.2})
    assert result.degraded and result.training_skipped
    assert not result.trained and not result.promoted
    assert calls == [("record", 1)]


async def test_world_can_be_stored_without_reuse_or_reused_without_new_storage():
    from dreamrsi.storage import InMemoryStore

    store = InMemoryStore()
    calls = []
    original = _configurable_memory(store, PolicyMemorySettings(), calls)
    await original.run({"kind": "labs", "seed": 1, "score": 0.8})
    assert len(await original._worlds("labs")) == 1

    no_reuse = _configurable_memory(store, PolicyMemorySettings(reuse_worlds=False), calls)
    await no_reuse.run({"kind": "labs", "seed": 2, "score": 0.4})
    assert ("import", 1) not in calls
    assert len(await original._worlds("labs")) == 2

    no_save = _configurable_memory(store, PolicyMemorySettings(save_worlds=False), calls)
    await no_save.run({"kind": "labs", "seed": 3, "score": 0.4})
    assert ("import", 1) in calls and ("import", 2) in calls
    assert len(await original._worlds("labs")) == 2


async def test_policy_save_and_reuse_switches_are_independent():
    from dreamrsi.storage import InMemoryStore

    store = InMemoryStore()
    task = {"kind": "labs", "seed": 1}
    original = _configurable_memory(store, PolicyMemorySettings(), [])
    assert await original.remember(task, GreedyPolicy())

    no_save = _configurable_memory(store, PolicyMemorySettings(save_policies=False), [])
    assert isinstance(await no_save.load("labs", task=task), GreedyPolicy)
    assert not await no_save.remember(task, DepthFirstPolicy())

    no_reuse = _configurable_memory(store, PolicyMemorySettings(reuse_policies=False), [])
    assert await no_reuse.load("labs", task=task) is None
    assert await no_reuse.remember(task, DepthFirstPolicy())
    assert isinstance(await original.load("labs", task=task), DepthFirstPolicy)


async def test_world_filter_excludes_current_and_historical_replay():
    from dreamrsi.storage import InMemoryStore

    store = InMemoryStore()
    calls = []
    seen = []

    async def accept(current, recorded, world):
        seen.append((current["seed"], recorded["seed"], world.tree.size))
        return current["seed"] == recorded["seed"] and current["seed"] != 1

    memory = _configurable_memory(store, PolicyMemorySettings(accept_world=accept), calls)
    first = await memory.run({"kind": "labs", "seed": 1, "score": 0.8})
    assert not first.trained and first.incumbent_saved
    assert calls == [] and await memory._worlds("labs") == []

    second = await memory.run({"kind": "labs", "seed": 2, "score": 0.4})
    assert second.trained
    assert calls == [("record", 2), ("improve", 2)]
    assert seen == [(1, 1, 2), (2, 2, 2)]
    assert len(await memory._worlds("labs")) == 1

    third = await memory.run({"kind": "labs", "seed": 3, "score": 0.4})
    assert third.trained
    assert (3, 2, 2) in seen
    assert not any(stage == "import" for stage, _ in calls)


async def test_policy_filter_controls_save_and_load_without_erasing_versions():
    from dreamrsi.storage import InMemoryStore

    store = InMemoryStore()
    calls = []
    only_promoted = PolicyMemorySettings(
        accept_policy=lambda task, policy, origin, quality: origin == "promoted"
    )
    memory = _configurable_memory(store, only_promoted, calls)
    task = {"kind": "labs", "seed": 1, "score": 0.8}
    first = await memory.run(task)
    assert not first.incumbent_saved and await memory.load("labs") is None
    assert await memory.remember(task, GreedyPolicy(), origin="promoted")

    blocked = _configurable_memory(
        store,
        PolicyMemorySettings(accept_policy=lambda task, policy, origin, quality: False),
        calls,
    )
    assert await blocked.load("labs", task={"kind": "labs", "seed": 2}) is None
    run = await blocked.run({"kind": "labs", "seed": 2, "score": 0.8})
    assert not run.reused_policy and not run.incumbent_saved
    assert isinstance(await memory.load("labs"), GreedyPolicy)
    entry = await store.get_checkpoint(memory._key("labs"))
    assert len(entry["versions"]) == 1


def test_memory_settings_reject_invalid_rules():
    with pytest.raises(ConfigurationError, match="save_worlds"):
        PolicyMemorySettings(save_worlds=1)
    with pytest.raises(ConfigurationError, match="accept_policy"):
        PolicyMemorySettings(accept_policy="yes")


async def test_acceptance_rules_must_return_boolean():
    from dreamrsi.storage import InMemoryStore

    memory = _configurable_memory(
        InMemoryStore(), PolicyMemorySettings(accept_world=lambda *args: 1), []
    )
    with pytest.raises(ConfigurationError, match="return boolean"):
        await memory.run({"kind": "labs", "seed": 1, "score": 0.8})

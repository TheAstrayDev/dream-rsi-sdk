"""Strict quality mode must not promote an empirically short unsafe policy."""

from dataclasses import replace

from dreamrsi import Budget, DefaultMethod, DreamRSI, HoldoutPipeline, Usage
from dreamrsi.adapters import FunctionalAgentAdapter
from dreamrsi.models.policy import PolicyDecision
from dreamrsi.policies import CertifiedPolicy, FixedParallelPolicy
from dreamrsi.quality import QualityContract
from dreamrsi.replay import ReplayWorld


def step(state, context):
    index = state.get("index", 0)
    return {**state, "index": index + 1, "quality": state["values"][index]}


def runtime(*, online=False, optimizer=None, preserve_policy=True):
    return DreamRSI(
        adapter=FunctionalAgentAdapter(step),
        evaluator=lambda observation: observation["quality"],
        policy=FixedParallelPolicy(1, 5),
        budget=Budget(model_calls=5, max_parallelism=1),
        quality=QualityContract(id="bounded-v1", upper_bound=1., preserve_policy=preserve_policy),
        validation=HoldoutPipeline([{"values": [.2] * 5, "seed": 2}]),
        method=DefaultMethod(online=online),
        policy_optimizer=optimizer,
    )


async def test_fresh_delayed_gain_is_not_lost_after_plateau_improvement():
    rsi = runtime()
    training = {"values": [.2] * 5, "seed": 1}
    collected = await rsi.run(training)
    await rsi.record_world(training, collected)
    improved = await rsi.improve(training, rounds=4)
    assert improved.champion_policy is None
    assert rsi.validation.used == 0
    deployed = await rsi.run({"values": [.2, .2, .3, .3, .9], "seed": 3})
    assert deployed.costs.model_calls == 5
    assert deployed.metrics["raw_quality"] == .9
    assert isinstance(deployed.policy, CertifiedPolicy)


async def test_recorded_short_champion_does_not_replace_original_policy_in_strict_mode():
    rsi = runtime()
    rsi._champion_policy = FixedParallelPolicy(1, 1)
    deployed = await rsi.run({"values": [.2, .2, .3, .3, .9], "seed": 3})
    assert deployed.costs.model_calls == 5
    assert deployed.metrics["raw_quality"] == .9


async def test_strict_mode_does_not_pay_for_forced_developer_or_repeated_online_training():
    class Developer:
        calls = 0

        async def develop(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("Certified stopping does not need policy training")

    developer = Developer()
    rsi = runtime(online=True, optimizer=developer)
    rsi._method.force_developer = True
    result = await rsi.improve({"values": [.2] * 5, "seed": 1}, rounds=4)
    assert developer.calls == 0
    assert result.costs.model_calls == 5
    assert result.costs.developer_calls == 0
    assert len(result.worlds) == 1
    assert rsi.validation.used == 0


async def test_explicit_empirical_mode_retains_policy_development_without_universal_claim():
    rsi = runtime(preserve_policy=False)
    training = {"values": [.2] * 5, "seed": 1}
    collected = await rsi.run(training)
    await rsi.record_world(training, collected)
    improved = await rsi.improve(training, rounds=1)
    assert improved.champion_policy is not None
    deployed = await rsi.run({"values": [.2, .2, .3, .3, .9], "seed": 3})
    assert deployed.costs.model_calls == 1
    assert deployed.metrics["raw_quality"] == .2


async def test_replay_initial_evaluation_preserves_budget_aware_policy_decisions():
    class BudgetPolicy:
        async def decide(self, view):
            # This legal policy distinguishes the true post-initial budget
            # from an incorrectly fresh budget in replay.
            if view.budget_remaining.evaluator_calls == 3:
                return PolicyDecision([], stop=True)
            return PolicyDecision([max(view.frontier, key=lambda node: node.depth).id])

    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(step),
        evaluator=lambda observation: observation["quality"],
        policy=BudgetPolicy(),
        budget=Budget(model_calls=3, evaluator_calls=3, max_parallelism=1),
        quality=QualityContract(
            id="budget-v1", upper_bound=1.,
            initial_candidate=lambda state, task: {"quality": .1},
        ),
    )
    result = await rsi.run({"values": [.3, .6, .9]})
    trajectory = await rsi.replay(ReplayWorld(result.tree), result.policy)
    assert result.costs.model_calls == trajectory.total_probes == 2
    assert result.costs.evaluator_calls == 3
    assert rsi._trajectory_quality(trajectory) == result.metrics["raw_quality"] == .6
    assert trajectory.objective["initial_evaluator_calls"] == 1


async def test_failed_initial_evaluation_still_consumes_replay_budget():
    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(step),
        evaluator=lambda observation: observation["quality"],
        policy=FixedParallelPolicy(1, 5),
        budget=Budget(model_calls=3, evaluator_calls=3, max_parallelism=1),
        quality=QualityContract(
            id="budget-v1", upper_bound=1., initial_candidate=lambda state, task: {},
        ),
    )
    result = await rsi.run({"values": [.3, .6, .9]})
    trajectory = await rsi.replay(ReplayWorld(result.tree), result.policy)
    assert result.tree.root.metadata["initial_evaluator_calls"] == 1
    assert result.costs.evaluator_calls == 3
    assert result.costs.model_calls == trajectory.total_probes == 2


async def test_replay_provider_budget_includes_initial_evaluator_and_nested_agent_calls():
    class BudgetPolicy:
        async def decide(self, view):
            if view.budget_remaining.total_llm_calls == 5:
                return PolicyDecision([], stop=True)
            return PolicyDecision([max(view.frontier, key=lambda node: node.depth).id])

    def nested(state, context):
        context["report_usage"](Usage(provider_calls=2))
        return step(state, context)

    def evaluate(observation, context):
        context["report_usage"](Usage(provider_calls=int(context.get("initial", False))))
        return observation["quality"]

    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(nested), evaluator=evaluate, policy=BudgetPolicy(),
        budget=Budget(model_calls=5, total_llm_calls=5, max_parallelism=1),
        usage_limits={"agent": Usage(provider_calls=2)},
        quality=QualityContract(
            id="provider-v1", upper_bound=1.,
            initial_candidate=lambda state, task: {"quality": .1},
        ),
    )
    result = await rsi.run({"values": [.3, .6, .9]})
    trajectory = await rsi.replay(ReplayWorld(result.tree), result.policy)
    assert result.costs.model_calls == trajectory.total_probes == 2
    assert result.costs.evaluator_calls == trajectory.objective["evaluator_calls"] == 3
    assert rsi.usage.spent["total_llm_calls"] == trajectory.objective["total_llm_calls"] == 5
    assert rsi._trajectory_quality(trajectory) == result.metrics["raw_quality"] == .6


async def test_failed_agent_replay_does_not_charge_an_evaluator_that_never_ran():
    def fail(state, context):
        context["report_usage"](Usage(provider_calls=1))
        raise ValueError("Discovery request failed")

    rsi = DreamRSI(
        adapter=FunctionalAgentAdapter(fail), evaluator=lambda observation: 1.,
        policy=FixedParallelPolicy(1, 5),
        budget=Budget(model_calls=2, evaluator_calls=1, total_llm_calls=2, max_parallelism=1),
    )
    result = await rsi.run({})
    trajectory = await rsi.replay(ReplayWorld(result.tree), result.policy)
    assert result.costs.model_calls == trajectory.total_probes == 2
    assert result.costs.evaluator_calls == trajectory.objective["evaluator_calls"] == 0
    assert rsi.usage.spent["total_llm_calls"] == trajectory.objective["total_llm_calls"] == 2


async def test_full_reference_preserves_quality_view_for_metadata_aware_policy():
    class MetadataAwarePolicy:
        async def decide(self, view):
            root = next(record for record in view.observations.values() if record["depth"] == 0)
            # Both the full comparator and the certified policy must observe
            # identical SDK metadata. Comparing with quality=None would make
            # this legal policy choose a different trajectory immediately.
            if root["diagnostics"].get("quality_contract", {}).get("id") != "same-view-v1":
                return PolicyDecision([], stop=True)
            return PolicyDecision([max(view.frontier, key=lambda node: node.depth).id])

    contract = QualityContract(
        id="same-view-v1", upper_bound=1.,
        initial_candidate=lambda state, task: {"quality": .1},
    )
    def build(quality):
        return DreamRSI(
            adapter=FunctionalAgentAdapter(step), evaluator=lambda item: item["quality"],
            policy=MetadataAwarePolicy(), budget=Budget(model_calls=4, max_parallelism=1),
            quality=quality,
        )
    task = {"values": [.3, 1., .7, .9]}
    reference = await build(replace(contract, certified_stopping=False)).run(task)
    protected = await build(contract).run(task)
    assert reference.costs.model_calls == 4
    assert protected.costs.model_calls == 2
    assert reference.metrics["raw_quality"] == protected.metrics["raw_quality"] == 1.
    assert reference.costs.evaluator_calls == 5
    assert protected.costs.evaluator_calls == 3
    assert reference.tree.root.metadata["quality_contract"] == protected.tree.root.metadata[
        "quality_contract"
    ]
    assert reference.tree.root.metadata["initial_evaluator_calls"] == 1
    assert protected.tree.root.metadata["initial_evaluator_calls"] == 1
    assert not isinstance(reference.policy, CertifiedPolicy)

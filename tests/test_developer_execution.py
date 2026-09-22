import copy

import pytest

from dreamrsi import Budget, DreamRSI, FunctionalAgentAdapter
from dreamrsi.artifacts import PolicyArtifact, SourcePolicy
from dreamrsi.developer import DeveloperConfig, LLMPolicyDeveloper
from dreamrsi.errors import SandboxError
from dreamrsi.models.policy import PolicyView
from dreamrsi.sandbox import PolicySandbox, SandboxConfig


def test_explicit_reasoning_delimiter_preserves_final_source_and_code_literals():
    from dreamrsi.developer import _revision

    code = 'def decide(view):\n    marker = "</think>"\n    return {"expand": []}'
    assert _revision(code)[0] == code
    assert _revision("internal draft\n</think>\n```python\n" + code + "\n```")[0] == code


async def test_collection_error_identifies_receiver_type_and_method():
    with pytest.raises(SandboxError, match=r"str\.get"):
        await PolicySandbox().execute(
            'def decide(view):\n    return "node-id".get("depth", 0)',
            PolicyView([], None, 0, 0, 0, 0),
        )


async def test_feedback_explains_objective_without_mutating_evidence():
    from dreamrsi.policies import BalancedPolicy
    from dreamrsi.replay import ReplayWorld, StrictReplay

    runtime = DreamRSI(agent=lambda x: x, evaluator=float, budget=Budget(model_calls=2))
    result = await runtime.run(1)
    trajectory = await StrictReplay(beta1=0.2, beta2=0.05).replay(
        ReplayWorld(result.tree), BalancedPolicy()
    )
    original = copy.deepcopy(trajectory.to_dict())
    feedback = LLMPolicyDeveloper(lambda request: "").feedback([trajectory])
    objective = feedback["trajectories"][0]["objective"]
    assert objective["beta1"] == 0.2
    assert trajectory.replay_score == pytest.approx(
        objective["quality"] - objective["probe_penalty"] + objective["parallelism_bonus"]
    )
    assert trajectory.to_dict() == original


async def test_resume_rejects_changed_objective_even_when_baseline_score_is_equal():
    from dreamrsi.errors import ConfigurationError
    from dreamrsi.models.replay import ReplayTrajectory

    code = 'def decide(view):\n    return {"expand": []}'
    baseline = [ReplayTrajectory("world", "incumbent", replay_score=1, objective={"beta1": 1})]

    async def evaluate(candidate):
        return baseline

    developer = LLMPolicyDeveloper(lambda request: code, revisions=1)
    policy = SourcePolicy(PolicyArtifact(code), PolicySandbox())
    await developer.develop(policy, baseline, evaluate, session_id="same")
    baseline[0].objective["beta1"] = 2
    with pytest.raises(ConfigurationError, match="changed"):
        await developer.develop(policy, baseline, evaluate, session_id="same")


def test_feedback_compresses_replay_boundaries_without_hiding_early_progress():
    from dreamrsi.models.replay import ReplayStep, ReplayTrajectory

    steps = [ReplayStep(1, ["root"], ["a"], 1, 1)]
    steps += [ReplayStep(i, ["a"], [], 1, 1) for i in range(2, 101)]
    trajectory = ReplayTrajectory("world", "policy", steps=steps, replay_score=1)
    feedback = LLMPolicyDeveloper(lambda request: "").feedback([trajectory])
    world = feedback["trajectories"][0]
    assert len(world["steps"]) == 2
    assert world["steps"][0]["revealed_nodes"] == ["a"]
    assert world["steps"][1]["repeated_rounds"] == 99
    assert world["steps"][1]["last_round_number"] == 100
    assert feedback["summary"]["empty_rounds"] == 99
    assert not world["steps_truncated"]
    assert len(trajectory.steps) == 100


async def test_wrong_world_pool_cannot_be_reported_as_a_scored_revision():
    from dreamrsi.models.replay import ReplayTrajectory

    code = 'def decide(view):\n    return {"expand": []}'

    async def evaluate(candidate):
        return [ReplayTrajectory("different", "candidate", replay_score=100)]

    developer = LLMPolicyDeveloper(lambda request: code, revisions=1)
    candidates = await developer.develop(
        SourcePolicy(PolicyArtifact(code), PolicySandbox()),
        [ReplayTrajectory("training", "incumbent", replay_score=1)],
        evaluate,
    )
    assert not candidates
    assert developer.history[0]["status"] == "failed"
    assert developer.history[0]["evaluation"] == {}


async def test_local_helpers_capture_values_and_math_without_host_access():
    source = """def decide(view):
    import math as m
    threshold = 2
    def rank(value):
        return m.sqrt(value) + threshold
    ordered = sorted([9, 4], key=rank, reverse=True)
    return {"expand": [], "stop": rank(ordered[0]) == 5}
"""
    view = PolicyView([], None, 0, 0, 0, 0)
    result = await PolicySandbox().execute(source, view)
    assert result.stop
    with pytest.raises(SandboxError, match="Helper functions disabled"):
        await PolicySandbox(SandboxConfig(allow_helpers=False)).execute(source, view)
    with pytest.raises(SandboxError, match="math proxy"):
        await PolicySandbox(SandboxConfig(allow_math=False)).execute(source, view)


async def test_reverse_sort_is_stable_and_failure_identifies_source_line():
    view = PolicyView([], None, 0, 0, 0, 0)
    source = """def decide(view):
    ids = sorted(["first", "second"], key=lambda x: 1, reverse=True)
    return {"expand": [], "stop": ids[0] == "first"}
"""
    assert (await PolicySandbox().execute(source, view)).stop
    with pytest.raises(SandboxError, match="Line 2"):
        await PolicySandbox().execute("def decide(view):\n    return view.missing", view)


async def test_failed_revision_never_inherits_a_score_and_repair_is_measured():
    requests = []
    outputs = iter(
        [
            "def decide(view):\n    return view.frontier",
            'def decide(view):\n    return {"expand": [view["frontier"][0]["id"]]}',
        ]
    )

    def generate(request):
        requests.append(
            copy.deepcopy({k: v for k, v in request.items() if k not in ("report_usage", "usage")})
        )
        return next(outputs)

    developer = LLMPolicyDeveloper(
        generate, config=DeveloperConfig(revisions=2, response_format="python")
    )
    runtime = DreamRSI(
        agent=lambda x: x,
        evaluator=float,
        policy_optimizer=developer,
        budget=Budget(model_calls=2),
    )
    await runtime.improve(1, rounds=1)
    bad, good = developer.history
    assert bad["status"] == "failed" and bad["evaluation"] == {}
    assert bad["feedback"]["summary"]["all_worlds_scored"] is False
    assert good["status"] == "scored"
    assert good["evaluation"]["all_worlds_scored"] is True
    assert requests[1]["revision_history"][0]["status"] == "failed"
    assert "Line 2" in requests[1]["feedback"]["error"]
    assert requests[1]["source"] == bad["artifact"]["source"]


def test_source_formatting_does_not_count_as_algorithmic_change():
    sandbox = PolicySandbox()
    code = 'def decide(view):\n    return {"expand": [], "stop": True}'
    assert sandbox.validate(code) == sandbox.validate(code + "\n# comment")


async def test_nested_function_cannot_escape_into_next_decision():
    source = """def decide(view):
    if view["calls_used"] == 0:
        def hidden():
            return True
        return {"expand": [], "stop": hidden()}
    return {"expand": [], "stop": hidden()}
"""
    policy = SourcePolicy(PolicyArtifact(source), PolicySandbox())
    assert (await policy.decide(PolicyView([], None, 0, 0, 0, 0))).stop
    with pytest.raises(SandboxError, match="Unknown function"):
        await policy.decide(PolicyView([], None, 0, 1, 0, 0))


async def test_online_costs_contain_reported_provider_usage():
    from dreamrsi import Usage

    def step(state, context):
        context["report_usage"](Usage(input_tokens=3, output_tokens=4, provider_calls=1))
        return state

    runtime = DreamRSI(
        adapter=FunctionalAgentAdapter(step), evaluator=float, budget=Budget(model_calls=1)
    )
    result = await runtime.run(1)
    assert result.costs.input_tokens == 3
    assert result.costs.output_tokens == 4
    assert result.costs.provider_calls == 1


async def test_developer_resume_reuses_completed_revision_without_model_call():
    import asyncio

    from dreamrsi.models.replay import ReplayTrajectory

    code = 'def decide(view):\n    return {"expand": [], "stop": True}'
    calls, saved = [], []

    def generate(request):
        calls.append(request["revision"])
        return code + f"\n# revision {request['revision']}"

    async def evaluate(candidate):
        return [ReplayTrajectory("world", "candidate", replay_score=2)]

    async def interrupt(history):
        saved[:] = copy.deepcopy(history)
        if history[-1]["status"] == "scored":
            raise asyncio.CancelledError

    incumbent = SourcePolicy(PolicyArtifact(code), PolicySandbox())
    baseline = [ReplayTrajectory("world", "incumbent", replay_score=1)]
    first = LLMPolicyDeveloper(generate, revisions=2)
    with pytest.raises(asyncio.CancelledError):
        await first.develop(
            incumbent, baseline, evaluate, persist=interrupt, session_id="test-session"
        )
    resumed = LLMPolicyDeveloper(generate, revisions=2)
    resumed.history = saved
    candidates = await resumed.develop(incumbent, baseline, evaluate, session_id="test-session")
    assert calls == [0, 1]
    assert len(candidates) == 2
    assert resumed.history[-1]["artifact"]["parent_hash"] == saved[0]["artifact"]["source_hash"]


async def test_developer_resume_can_evaluate_already_received_response():
    import asyncio

    from dreamrsi.models.replay import ReplayTrajectory

    code = 'def decide(view):\n    return {"expand": [], "stop": True}'
    calls, saved = [], []

    def generate(request):
        calls.append(1)
        return code

    async def evaluate(candidate):
        return [ReplayTrajectory("world", "candidate", replay_score=2)]

    async def interrupt(history):
        saved[:] = copy.deepcopy(history)
        if history[-1]["status"] == "generated":
            raise asyncio.CancelledError

    incumbent = SourcePolicy(PolicyArtifact(code), PolicySandbox())
    baseline = [ReplayTrajectory("world", "incumbent", replay_score=1)]
    first = LLMPolicyDeveloper(generate, revisions=1)
    with pytest.raises(asyncio.CancelledError):
        await first.develop(incumbent, baseline, evaluate, persist=interrupt, session_id="s")
    resumed = LLMPolicyDeveloper(generate, revisions=1)
    resumed.history = saved
    candidates = await resumed.develop(incumbent, baseline, evaluate, session_id="s")
    assert len(calls) == 1
    assert len(candidates) == 1
    assert resumed.history[0]["status"] == "scored"

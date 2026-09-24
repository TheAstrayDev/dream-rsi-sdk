import copy

import pytest

from dreamrsi import Budget, DreamRSI
from dreamrsi.artifacts import PolicyArtifact, SourcePolicy
from dreamrsi.developer import LLMPolicyDeveloper, _revision
from dreamrsi.errors import PolicyError, SandboxError
from dreamrsi.models.policy import PolicyView
from dreamrsi.sandbox import PolicySandbox

STOP = 'def decide(view):\n    return {"expand": [], "stop": True}'
REFINE = """def decide(view):
    chosen = None
    for node in view["frontier"]:
        if chosen is None or node["depth"] > chosen["depth"]:
            chosen = node
    if chosen is None or view["calls_used"] >= 2:
        return {"expand": [], "stop": True}
    return {"expand": [chosen["id"]]}
"""


@pytest.mark.parametrize("response", ["python\n" + STOP, "```python\n" + STOP + "\n```"])
def test_developer_accepts_language_tagged_python(response):
    assert _revision(response)[0] == STOP


def view():
    return PolicyView([], None, 0, 0, 0, 0)


async def test_policy_language_and_artifact_integrity():
    artifact = PolicyArtifact(STOP, provenance={"model": "fixture"})
    assert PolicyArtifact.from_dict(artifact.to_dict()) == artifact
    changed = artifact.to_dict()
    changed["source"] += "\n"
    with pytest.raises(PolicyError, match="integrity"):
        PolicyArtifact.from_dict(changed)
    policy = SourcePolicy(artifact, PolicySandbox())
    assert (await copy.deepcopy(policy).decide(view())).stop


async def test_sandbox_explains_null_dictionary_key_for_repair_feedback():
    source = """def decide(view):
    counts = {}
    counts[None] = 1
    return {"expand": []}
"""
    with pytest.raises(SandboxError, match="None/null.*parent IDs"):
        await PolicySandbox().execute(source, view())


@pytest.mark.parametrize(
    "body",
    [
        "import os",
        'return open("secret")',
        "return view.__class__",
        'return __import__("os")',
        "while True:\n        pass",
        "x = [0] * 1000000000",
        "x = 2 ** 1000000000",
        'x = "%999999999s" % "x"',
        "x = range(1000000000)",
        'return {"expand": [], "stop": "false"}',
        "x = lambda: 1",
        "x = [n for n in view]",
    ],
)
async def test_hostile_or_unsupported_program_is_bounded(body):
    with pytest.raises(SandboxError):
        await PolicySandbox(max_steps=1000).execute("def decide(view):\n    " + body, view())


async def test_rewrite_uses_real_replay_feedback_and_recovers_from_bad_source():
    requests = []
    sources = iter(["def decide(view):\n    import os", REFINE])

    async def model(request):
        requests.append(request)
        return next(sources)

    developer = LLMPolicyDeveloper(model, revisions=2)
    rsi = DreamRSI(
        agent=lambda x: x,
        evaluator=lambda x: x,
        budget=Budget(model_calls=3),
        policy_optimizer=developer,
    )
    result = await rsi.improve(10, rounds=1)
    assert len(developer.history) == 2
    assert "error" in requests[1]["feedback"]
    assert "string node IDs, never node dictionaries" in requests[0]["instruction"]
    assert "may need to expand it more than once" in requests[0]["instruction"]
    assert requests[0]["promotion_target"]["incumbent_attempted_expansions"] >= 1
    assert requests[0]["promotion_target"]["online_model_calls_per_run"] == 3
    assert "Change the failing code" in requests[1]["revision_goal"]
    assert (
        developer.history[1]["artifact"]["parent_hash"]
        == developer.history[0]["artifact"]["source_hash"]
    )
    assert requests[1]["feedback"]["trajectories"] == requests[0]["feedback"]["trajectories"]
    assert developer.history[1]["feedback"]["trajectories"][0]["replay_score"] is not None
    assert isinstance(result.champion_policy, SourcePolicy)
    assert len(requests[0]["feedback"]["trajectories"]) == 1


async def test_algorithm_with_helpers_math_comprehensions_and_mutation():
    from dreamrsi import SandboxConfig
    from dreamrsi.models.discovery import NodeStatus
    from dreamrsi.models.policy import NodeSummary

    source = """import math

def priority(node, total=1):
    score = node.get("score", 0)
    if score is None:
        score = 0
    return score + math.sqrt(math.log(total + 1) / (node["children_count"] + 1))

def decide(view):
    nodes = [node for node in view["frontier"] if node["depth"] < 10]
    ranked = sorted(nodes, key=lambda node: priority(node, view["total_nodes"]), reverse=True)
    selected = []
    for index, node in enumerate(ranked):
        if index >= 2:
            break
        selected.append(node["id"])
    stats = {node["id"]: node["depth"] for node in ranked}
    stats["extra"] = 1
    stats["extra"] += 2
    return {"expand": selected, "parallelism": len(selected), "stop": not selected}
"""
    populated = PolicyView(
        [
            NodeSummary("a", None, 0, 1, NodeStatus.COMPLETED, 3),
            NodeSummary("b", "a", 1, 3, NodeStatus.COMPLETED, 0),
        ],
        3,
        2,
        1,
        0,
        1,
    )
    sandbox = PolicySandbox(SandboxConfig(max_steps=20000))
    result = await sandbox.execute(source, populated)
    assert result.expand == ["b", "a"]
    assert result.parallelism == 2
    with pytest.raises(SandboxError):
        await PolicySandbox(SandboxConfig(allow_math=False)).execute(source, populated)


async def test_recursive_helpers_are_configurably_bounded():
    from dreamrsi import SandboxConfig

    code = """def descend(n):
    return descend(n + 1)

def decide(view):
    return descend(0)
"""
    with pytest.raises(SandboxError, match="depth"):
        await PolicySandbox(SandboxConfig(max_call_depth=4)).execute(code, view())


@pytest.mark.parametrize(
    "expression",
    [
        "view.get.__globals__",
        "math.__dict__",
        "view.__class__.__mro__",
        'getattr(view, "__class__")',
        'view.get("x", __import__("os"))',
        "view.items().__class__",
        "math.factorial(1000000000)",
    ],
)
async def test_expanded_language_keeps_host_objects_unreachable(expression):
    with pytest.raises(SandboxError):
        await PolicySandbox().execute(
            "import math\ndef decide(view):\n    return " + expression, view()
        )


async def test_structured_revisions_recover_best_source_with_regression_feedback():
    from dreamrsi.models.replay import ReplayTrajectory

    requests = []
    sources = [STOP + "\n# first", STOP + "\n# regression", STOP + "\n# repaired"]
    values = iter([2.0, 0.5, 3.0])

    async def model(request):
        requests.append(copy.deepcopy(request))
        return {
            "source": sources[len(requests) - 1],
            "diagnosis": "measured comparison",
            "changes": "rewrite selection algorithm",
        }

    async def evaluate(candidate):
        await candidate.decide(view())
        return [ReplayTrajectory("training", "candidate", replay_score=next(values))]

    developer = LLMPolicyDeveloper(model, revisions=3)
    initial = SourcePolicy(PolicyArtifact(STOP), PolicySandbox())
    await developer.develop(
        initial, [ReplayTrajectory("training", "initial", replay_score=1)], evaluate
    )
    assert requests[2]["source"] == sources[0]
    assert requests[2]["best_source"] == sources[0]
    assert requests[2]["evaluated_source"] == sources[1]
    assert requests[2]["feedback"]["comparison"]["delta_vs_best"] == -1.5
    assert (
        developer.history[2]["artifact"]["parent_hash"]
        == developer.history[0]["artifact"]["source_hash"]
    )
    assert developer.history[2]["feedback"]["summary"]["mean_score"] == 3
    assert developer.history[0]["diagnosis"] == "measured comparison"


@pytest.mark.parametrize("first_attempts", [1, 2])
async def test_developer_names_attempted_expansion_target_in_next_revision(first_attempts):
    from dreamrsi.models.replay import ReplayTrajectory

    requests = []
    attempts = iter([first_attempts, 1])

    async def model(request):
        requests.append(copy.deepcopy(request))
        return STOP + f"\n# revision {len(requests)}"

    async def evaluate(candidate):
        await candidate.decide(view())
        return [
            ReplayTrajectory(
                "training", "candidate", total_probes=next(attempts),
                replay_score=1.0, best_score=1.0,
            )
        ]

    developer = LLMPolicyDeveloper(model, revisions=2)
    initial = SourcePolicy(PolicyArtifact(STOP), PolicySandbox())
    baseline = ReplayTrajectory(
        "training", "initial", total_probes=1, replay_score=1.0, best_score=1.0
    )
    await developer.develop(initial, [baseline], evaluate)
    assert f"attempted {first_attempts} expansions versus the incumbent's 1" in requests[1][
        "revision_goal"
    ]
    assert requests[1]["feedback"]["comparison"]["attempted_expansions_vs_baseline"] == {
        "baseline": 1, "candidate": first_attempts,
    }


def test_source_codec_preserves_deadline_and_checks_sandbox_profile():
    from dreamrsi import PolicyCodec, SandboxConfig

    sandbox = PolicySandbox(SandboxConfig(max_steps=1234))
    codec = PolicyCodec(sandbox)
    encoded = codec.encode(SourcePolicy(PolicyArtifact(STOP), sandbox, timeout_s=0.75))
    restored = codec.decode(encoded)
    assert restored.timeout_s == 0.75
    assert restored.sandbox.config.max_steps == 1234
    with pytest.raises(PolicyError, match="profile"):
        PolicyCodec().decode(encoded)

import asyncio
import json

import pytest

from dreamrsi import (
    PolicyArtifact,
    PolicyCodec,
    PolicySandbox,
    ProcessPolicySandbox,
    SandboxConfig,
)
from dreamrsi.artifacts import SourcePolicy
from dreamrsi.errors import PolicyError, SandboxError
from dreamrsi.models.policy import PolicyView

VIEW = PolicyView([], None, 0, 0, 0, 0)
STOP = 'def decide(view):\n    return {"expand": [], "stop": True}'


@pytest.mark.parametrize(
    "settings, body, error",
    [
        ({"allowed_builtins": []}, "x = len([])", "Builtin disabled: len"),
        ({"allowed_math": ["sqrt"]}, "import math\n    x = math.log(2)", "disabled math"),
        ({"allowed_math": []}, "import math\n    x = math.pi", "attribute access"),
        ({"allowed_methods": []}, "x = []\n    x.sort()", "disabled: list.sort"),
        ({"allowed_methods": ["list.sort"]}, "x = {}\n    x.get('a')", "disabled: dict.get"),
    ],
)
async def test_fine_grained_allowlists_are_enforced(settings, body, error):
    sandbox = PolicySandbox(**settings)
    with pytest.raises(SandboxError, match=error):
        await sandbox.execute(
            "def decide(view):\n    " + body + '\n    return {"expand": []}', VIEW
        )


def test_config_roundtrip_and_capabilities_match_active_profile():
    profile = SandboxConfig(
        allowed_builtins=("len", "sorted", "len"),
        allowed_math=("sqrt",),
        allowed_methods=("dict.get",),
    )
    restored = SandboxConfig.from_dict(json.loads(json.dumps(profile.to_dict())))
    assert profile == restored
    caps = PolicySandbox(restored).capabilities()
    assert caps["builtins"] == ["len", "sorted"]
    assert caps["math"] == ["sqrt"]
    assert caps["contract"]["methods"] == {"dict": ["get"], "list": [], "str": []}
    assert PolicySandbox(profile, allow_math=False).capabilities()["math"] == []
    with pytest.raises(ValueError, match="supported names"):
        SandboxConfig(allowed_builtins=("open",))


async def test_worker_matches_interpreter_and_codec_preserves_profile():
    worker = ProcessPolicySandbox(allowed_builtins=("len",))
    policy = SourcePolicy(PolicyArtifact(STOP), worker)
    codec = PolicyCodec(worker)
    encoded = json.loads(json.dumps(codec.encode(policy)))
    restored = codec.decode(encoded)
    assert await restored.decide(VIEW) == await PolicySandbox().execute(STOP, VIEW)
    with pytest.raises(PolicyError, match="same sandbox profile"):
        PolicyCodec().decode(encoded)


async def test_worker_keeps_event_loop_responsive_and_is_reaped_on_timeout(monkeypatch):
    children = []
    spawn = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        child = await spawn(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    worker = ProcessPolicySandbox(max_steps=100_000_000)
    task = asyncio.create_task(
        worker.execute("def decide(view):\n    while True:\n        pass", VIEW, 0.3)
    )
    ticks = 0
    while not task.done():
        await asyncio.sleep(0.02)
        ticks += 1
    with pytest.raises(SandboxError, match="time limit"):
        await task
    assert ticks >= 2
    assert len(children) == 1 and children[0].returncode is not None


async def test_worker_cancellation_terminates_process(monkeypatch):
    children = []
    ready = asyncio.Event()
    spawn = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        child = await spawn(*args, **kwargs)
        children.append(child)
        ready.set()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    task = asyncio.create_task(
        ProcessPolicySandbox(max_steps=100_000_000).execute(
            "def decide(view):\n    while True:\n        pass", VIEW, 10
        )
    )
    await asyncio.wait_for(ready.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[0].returncode is not None


async def test_developer_propagates_policy_timeout_through_resume():
    from dreamrsi import DeveloperConfig, LLMPolicyDeveloper
    from dreamrsi.models.replay import ReplayTrajectory

    baseline = [ReplayTrajectory("world", "initial", replay_score=1)]

    async def evaluate(candidate):
        assert candidate.timeout_s == 0.25
        return [ReplayTrajectory("world", "candidate", replay_score=2)]

    config = DeveloperConfig(revisions=1, policy_timeout_s=0.25)
    developer = LLMPolicyDeveloper(lambda request: STOP, config=config)
    incumbent = SourcePolicy(PolicyArtifact(STOP), PolicySandbox())
    candidates = await developer.develop(incumbent, baseline, evaluate, session_id="timeout")
    restored = await developer.develop(incumbent, baseline, evaluate, session_id="timeout")
    assert candidates[0].timeout_s == restored[0].timeout_s == 0.25
    with pytest.raises(ValueError, match="policy_timeout_s"):
        DeveloperConfig(policy_timeout_s=0)

import pytest

from dreamrsi import PolicySandbox, SandboxConfig
from dreamrsi.errors import SandboxError
from dreamrsi.models.policy import PolicyView


async def test_generator_aggregation_and_stable_in_place_sort_with_local_key():
    source = """def decide(view):
    nodes = [{"id": "a", "score": 2}, {"id": "b", "score": 2}, {"id": "c", "score": 3}]
    offset = sum(n for n in range(5) if n > 1)
    def priority(node):
        return node["score"] + offset
    nodes.sort(key=priority, reverse=True)
    return {"expand": [node["id"] for node in nodes]}
"""
    result = await PolicySandbox().execute(source, PolicyView([], None, 0, 0, 0, 0))
    assert result.expand == ["c", "a", "b"]


async def test_generator_limits_and_profile_are_enforced():
    source = 'def decide(view):\n    n = sum(n for n in range(1000))\n    return {"expand": []}'
    view = PolicyView([], None, 0, 0, 0, 0)
    with pytest.raises(SandboxError, match="Range limit"):
        await PolicySandbox(max_items=100).execute(source, view)
    with pytest.raises(SandboxError, match="Comprehensions disabled"):
        await PolicySandbox(SandboxConfig(allow_comprehensions=False)).execute(source, view)


async def test_sort_cannot_invoke_host_code_or_bypass_method_profile():
    source = 'def decide(view):\n    x = [1]\n    x.sort(key=open)\n    return {"expand": []}'
    view = PolicyView([], None, 0, 0, 0, 0)
    with pytest.raises(SandboxError):
        await PolicySandbox().execute(source, view)
    with pytest.raises(SandboxError, match="methods disabled"):
        await PolicySandbox(allow_methods=False).execute(source, view)

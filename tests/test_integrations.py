import asyncio
import copy

import pytest

from dreamrsi import Budget, DreamRSI
from dreamrsi.integrations import RunnableAgentAdapter
from dreamrsi.policies import DepthFirstPolicy
from dreamrsi.workspaces import WorkspaceAgentAdapter


async def test_real_langchain_runnable():
    runnables = pytest.importorskip("langchain_core.runnables")
    adapter = RunnableAgentAdapter(runnables.RunnableLambda(lambda value: value / 2))
    result = await DreamRSI(adapter=adapter, evaluator=lambda x: -x,
                            policy=DepthFirstPolicy(), budget=Budget(model_calls=3)).run(8)
    assert result.best == 1


class Backend:
    def __init__(self):
        self.snapshots = {}
        self.released = []
        self.cancelled = []

    async def initial(self, task):
        return await self.snapshot({'x': task})

    async def checkout(self, descriptor, attempt_id):
        return copy.deepcopy(self.snapshots[descriptor['id']])

    async def snapshot(self, handle):
        key = str(len(self.snapshots))
        self.snapshots[key] = copy.deepcopy(handle)
        return {'id': key}

    async def release(self, handle):
        self.released.append(handle)

    async def cancel(self, attempt_id):
        self.cancelled.append(attempt_id)
        return True


async def test_workspace_snapshots_and_release():
    backend = Backend()

    async def agent(handle, context):
        handle['x'] += 1
        return handle['x']

    adapter = WorkspaceAgentAdapter(backend, agent)
    result = await DreamRSI(adapter=adapter, evaluator=float, policy=DepthFirstPolicy(),
                            budget=Budget(model_calls=3)).run(1)
    assert result.best == 4
    assert backend.snapshots['0'] == {'x': 1}
    assert len(backend.released) == 3
    assert adapter.active == {}


async def test_workspace_cancel_before_release():
    backend = Backend()

    async def agent(handle, context):
        await asyncio.sleep(10)

    adapter = WorkspaceAgentAdapter(backend, agent)
    result = await DreamRSI(adapter=adapter, evaluator=float,
                            budget=Budget(wall_time_s=.02)).run(1)
    assert result.metrics['stop_reason'] == 'wall_time'
    assert backend.cancelled
    assert len(backend.released) == 1
    assert not adapter.active


async def test_real_runnable_developer_transport():
    import json

    from dreamrsi import LLMPolicyDeveloper
    runnables = pytest.importorskip("langchain_core.runnables")
    prompts = []
    def model(prompt):
        prompts.append(json.loads(prompt))
        return 'def decide(view):\n    return {"expand": [], "stop": True}'
    developer = LLMPolicyDeveloper.from_runnable(runnables.RunnableLambda(model), revisions=1)
    rsi = DreamRSI(agent=lambda task: task, evaluator=float,
                   budget=Budget(model_calls=1), policy_optimizer=developer)
    await rsi.improve(1, rounds=1)
    assert len(prompts) == 1
    assert "report_usage" not in prompts[0]
    assert "trajectories" in prompts[0]["feedback"]

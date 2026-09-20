"""Small integration adapters; no dependency on a model provider or agent framework."""

from __future__ import annotations

from typing import Any

from dreamrsi._invoke import invoke, with_context


class CallableAgentAdapter:
    """Independent sampling: call ``agent(task)`` for each attempt."""

    def __init__(self, fn: Any):
        self._fn = fn

    async def initial_state(self, task):
        return task

    async def propose(self, state, context):
        return await invoke(self._fn, state)

    async def execute(self, proposal, state, context):
        return proposal

    async def observe(self, execution, state):
        return execution

    async def next_state(self, observation, state):
        return state


class FunctionalAgentAdapter(CallableAgentAdapter):
    """Refinement with one function: ``step(state, context) -> next_state``.

    The task is the initial state. Each output is scored and becomes the input
    to the next refinement. Context is optional. Functions may be sync or async.
    Use the full AgentAdapter protocol when observations and states differ.
    """

    async def propose(self, state, context):
        return await with_context(self._fn, state, context)

    async def next_state(self, observation, state):
        return observation

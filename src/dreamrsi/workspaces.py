"""Workspace lifecycle adapter: snapshots are portable IDs, never live clients.

A backend owns checkout/snapshot/release/cancel and can target files, DBs or VMs.
The runtime only copies immutable snapshot descriptors into discovery trees.
"""

from __future__ import annotations

import asyncio

from dreamrsi._invoke import invoke


class WorkspaceAgentAdapter:
    """Backend protocol implemented by composition rather than inheritance.

    backend.initial(task) -> descriptor; checkout(descriptor, attempt_id) -> handle;
    snapshot(handle) -> descriptor; release(handle); cancel(attempt_id) -> bool.
    agent(handle, context) -> JSON observation. Descriptors must remain valid for
    future branches and replay artifacts. Backend controls durable snapshot GC.
    """

    def __init__(self, backend, agent):
        self.backend, self.agent = backend, agent
        self.active = {}

    async def initial_state(self, task):
        descriptor = await invoke(self.backend.initial, task)
        if not isinstance(descriptor, dict):
            raise TypeError("Workspace snapshot descriptors must be dictionaries")
        return descriptor

    async def propose(self, state, context):
        attempt_id = context["attempt_id"]
        handle = await invoke(self.backend.checkout, state, attempt_id)
        self.active[attempt_id] = handle
        try:
            observation = await invoke(self.agent, handle, context)
            descriptor = await invoke(self.backend.snapshot, handle)
            return {"observation": observation, "snapshot": descriptor}
        except asyncio.CancelledError:
            confirmed = await invoke(self.backend.cancel, attempt_id)
            if confirmed and attempt_id in self.active:
                await invoke(self.backend.release, self.active.pop(attempt_id))
            raise
        except BaseException:
            if attempt_id in self.active:
                await invoke(self.backend.release, self.active.pop(attempt_id))
            raise
        else:
            pass
        finally:
            # A cancelled unconfirmed operation retains ownership of its workspace.
            current = asyncio.current_task()
            if current is not None and not current.cancelling() and attempt_id in self.active:
                await invoke(self.backend.release, self.active.pop(attempt_id))

    async def execute(self, proposal, state, context):
        return proposal

    async def observe(self, execution, state):
        state["_next_snapshot"] = execution["snapshot"]
        return execution["observation"]

    async def next_state(self, observation, state):
        return state["_next_snapshot"]

    async def cancel(self, attempt_id):
        return await invoke(self.backend.cancel, attempt_id)

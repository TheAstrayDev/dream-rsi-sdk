from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentAdapter(Protocol):
    """Protocol for native Dream-RSI agent integration.

    Implement this to give the library full control over
    branching, exploration, and replay.
    """

    async def initial_state(self, task: Any) -> Any:
        """Create the initial workspace state for a task."""
        ...

    async def propose(self, state: Any, context: dict[str, Any]) -> Any:
        """Generate a proposal (candidate solution) from the current state."""
        ...

    async def execute(self, proposal: Any, state: Any, context: dict[str, Any]) -> Any:
        """Execute/evaluate a proposal, returning the execution result."""
        ...

    async def observe(self, execution: Any, state: Any) -> Any:
        """Extract observations from an execution result."""
        ...

    async def next_state(self, observation: Any, state: Any) -> Any:
        """Derive the next state from an observation and current state."""
        ...


@runtime_checkable
class SimpleAgent(Protocol):
    """Minimal agent protocol — just a callable that takes a task and returns a result."""

    async def __call__(self, task: Any, **kwargs: Any) -> Any: ...

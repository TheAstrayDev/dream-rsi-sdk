from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dreamrsi.models.policy import PolicyDecision, PolicyView


@runtime_checkable
class SandboxExecutor(Protocol):
    """Protocol for executing generated policy code in isolation."""

    async def execute(
        self,
        code: str,
        policy_view: PolicyView,
        timeout_s: float = 30.0,
    ) -> PolicyDecision: ...

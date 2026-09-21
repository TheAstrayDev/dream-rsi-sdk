from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from dreamrsi.models.results import RunResult

if TYPE_CHECKING:
    from dreamrsi.runtime import DreamRSI


@runtime_checkable
class Method(Protocol):
    """Own the entire outer loop; run() remains the online primitive."""

    async def improve(self, runtime: DreamRSI, task: Any, rounds: int = 5) -> RunResult: ...

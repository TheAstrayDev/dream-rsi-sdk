from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dreamrsi.models.evaluation import Evaluation


@runtime_checkable
class Evaluator(Protocol):
    """Protocol for evaluating candidate solutions."""

    async def evaluate(
        self, candidate: Any, context: dict[str, Any] | None = None
    ) -> Evaluation: ...

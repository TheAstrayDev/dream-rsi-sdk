from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dreamrsi.models.policy import PolicyVersion
    from dreamrsi.models.promotion import PromotionDecision


@runtime_checkable
class PromotionGate(Protocol):
    """Protocol for evaluating whether a challenger should replace the incumbent."""

    async def evaluate(
        self,
        incumbent: PolicyVersion,
        challenger: PolicyVersion,
        evidence: dict[str, Any],
    ) -> PromotionDecision: ...

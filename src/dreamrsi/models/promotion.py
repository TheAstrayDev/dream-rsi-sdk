from __future__ import annotations

import dataclasses
import enum
import time
from typing import Any, Self


class PromotionOutcome(enum.StrEnum):
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclasses.dataclass
class PromotionDecision:
    challenger_id: str
    incumbent_id: str
    outcome: PromotionOutcome
    reason: str = ""
    evidence: dict[str, Any] = dataclasses.field(default_factory=dict)
    created_at: float = dataclasses.field(default_factory=time.time)
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["outcome"] = self.outcome.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        d = data.copy()
        if "outcome" in d:
            d["outcome"] = PromotionOutcome(d["outcome"])
        return cls(**{k: v for k, v in d.items() if k != "_schema_version"})

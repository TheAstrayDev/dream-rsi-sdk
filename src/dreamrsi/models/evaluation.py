from __future__ import annotations

import dataclasses
import enum
import time
import uuid
from typing import Any, Self


class EvaluationStatus(enum.StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


@dataclasses.dataclass
class Evaluation:
    score: float
    evaluator_id: str = "default"
    evaluator_version: str = "1"
    status: EvaluationStatus = EvaluationStatus.PASSED
    diagnostics: dict[str, Any] = dataclasses.field(default_factory=dict)
    created_at: float = dataclasses.field(default_factory=time.time)
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        d = data.copy()
        if "status" in d:
            d["status"] = EvaluationStatus(d["status"])
        return cls(**{k: v for k, v in d.items() if k != "_schema_version"})

from __future__ import annotations

import dataclasses
import math
from typing import Any, Self


@dataclasses.dataclass(frozen=True)
class Budget:
    model_calls: int | None = None
    evaluator_calls: int | None = None
    usd: float | None = None
    wall_time_s: float | None = None
    max_nodes: int | None = None
    max_depth: int | None = None
    max_parallelism: int | None = None
    max_rounds: int | None = None
    _schema_version: str = dataclasses.field(default="1", init=False, repr=False)

    def __post_init__(self) -> None:
        for item in dataclasses.fields(self):
            if item.name.startswith("_"):
                continue
            value = getattr(self, item.name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{item.name} must be a nonnegative number")
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{item.name} must be finite and nonnegative")
            if item.name not in ("usd", "wall_time_s") and not isinstance(value, int):
                raise ValueError(f"{item.name} must be an integer")

    @property
    def is_unlimited(self) -> bool:
        return all(
            getattr(self, f.name) is None
            for f in dataclasses.fields(self)
            if f.name != "_schema_version"
        )

    def remaining(self, used: Budget) -> Budget:
        def calc_rem(b_limit: Any, b_used: Any) -> Any:
            if b_limit is None:
                return None
            if b_used is None:
                return b_limit
            return max(0, b_limit - b_used)

        return Budget(
            model_calls=calc_rem(self.model_calls, used.model_calls),
            evaluator_calls=calc_rem(self.evaluator_calls, used.evaluator_calls),
            usd=calc_rem(self.usd, used.usd),
            wall_time_s=calc_rem(self.wall_time_s, used.wall_time_s),
            max_nodes=calc_rem(self.max_nodes, used.max_nodes),
            max_depth=calc_rem(self.max_depth, used.max_depth),
            max_parallelism=calc_rem(self.max_parallelism, used.max_parallelism),
            max_rounds=calc_rem(self.max_rounds, used.max_rounds),
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(**{k: v for k, v in data.items() if k != "_schema_version"})

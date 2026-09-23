"""Reservation-based usage accounting shared across an entire runtime campaign."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import asdict, dataclass

from dreamrsi.errors import BudgetExceeded


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    provider_calls: int = 0
    usd: float = 0.0

    def __post_init__(self):
        for key, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("Usage must be numeric")
            if value < 0 or not math.isfinite(value):
                raise ValueError("Usage must be finite and nonnegative")
            if key != "usd" and not isinstance(value, int):
                raise ValueError("Token/call usage must be integral")

    @property
    def tokens(self):
        return self.input_tokens + self.output_tokens

    def __add__(self, other):
        return Usage(**{k: v + asdict(other)[k] for k, v in asdict(self).items()})


class UsageLedger:
    """Reserve upper bounds before dispatch; uncertainty retains the reservation.

    Reports above a supplied ceiling are recorded as overruns and block later work.
    Integrations must supply true upper bounds to enforce a monetary spending cap.
    """

    def __init__(self, budget=None):
        self.budget = budget
        self.started = time.monotonic()
        self.elapsed_before = 0.0
        self.spent = dict(
            model_calls=0,
            evaluator_calls=0,
            developer_calls=0,
            total_llm_calls=0,
            tokens=0,
            usd=0.0,
        )
        self.held = {key: 0 for key in self.spent}
        self.records = []
        self.active = []
        self.breached = False
        self._lock = threading.Lock()

    @property
    def remaining_time(self):
        limit = getattr(self.budget, "wall_time_s", None)
        if limit is None:
            return None
        return max(0.0, limit - self.elapsed_before - (time.monotonic() - self.started))

    def release(self, reservation):
        with self._lock:
            self.active.remove(reservation)
            for key, amount in reservation[1].items():
                self.held[key] -= amount

    def reserve(self, stage, ceiling):
        if self.budget is not None and self.remaining_time == 0:
            raise BudgetExceeded("wall_time_s", self.budget.wall_time_s, self.budget.wall_time_s)

        count = {
            "agent": "model_calls",
            "evaluator": "evaluator_calls",
            "developer": "developer_calls",
        }[stage]
        amounts = dict.fromkeys(self.spent, 0)
        amounts.update({count: 1, "tokens": ceiling.tokens, "usd": ceiling.usd})
        if stage in ("agent", "developer"):
            amounts["total_llm_calls"] = 1
        with self._lock:
            if self.breached:
                raise BudgetExceeded("usage_ceiling", 0, 1)
            for key, amount in amounts.items():
                cap = getattr(self.budget, key, None)
                if cap is not None and self.spent[key] + self.held[key] + amount > cap:
                    raise BudgetExceeded(key, cap, self.spent[key] + self.held[key] + amount)
            for key, amount in amounts.items():
                self.held[key] += amount
            reservation = (stage, amounts, ceiling)
            self.active.append(reservation)
            return reservation

    def settle(self, reservation, usage=None, estimated=False):
        stage, amounts, ceiling = reservation
        actual = ceiling if usage is None else usage
        final = {**amounts, "tokens": actual.tokens, "usd": actual.usd}
        with self._lock:
            self.active.remove(reservation)
            if usage is not None and (actual.tokens > ceiling.tokens or actual.usd > ceiling.usd):  # noqa: SIM102
                # No ceiling means unbounded measured usage, unless capped by the budget.
                if (
                    ceiling.tokens
                    or ceiling.usd
                    or (
                        self.budget
                        and (self.budget.tokens is not None or self.budget.usd is not None)
                    )
                ):
                    self.breached = True
            for key, value in final.items():
                self.held[key] -= amounts[key]
                self.spent[key] += value
            self.records.append(
                {"stage": stage, "usage": asdict(actual), "estimated": estimated or usage is None}
            )

    def to_dict(self):
        return {
            "spent": {k: v + self.held[k] for k, v in self.spent.items()},
            "uncertain": any(self.held.values()),
            "pending": [
                {"stage": r[0], "usage": asdict(r[2]), "estimated": True} for r in self.active
            ],
            "elapsed": self.elapsed_before + time.monotonic() - self.started,
            "records": list(self.records),
            "breached": self.breached,
        }

    def restore(self, data):
        if any(self.held.values()):
            raise RuntimeError("Cannot restore over in-flight work")
        self.elapsed_before = data.get("elapsed", 0.0)
        self.started = time.monotonic()
        self.spent = dict(data["spent"])
        # Checkpoints from before the combined call limit still have an exact
        # count: each recorded agent/developer dispatch was charged once.
        self.spent.setdefault(
            "total_llm_calls", self.spent["model_calls"] + self.spent["developer_calls"]
        )
        self.records = list(data["records"]) + list(data.get("pending", []))
        self.breached = data["breached"]


class UsageReporter:
    def __init__(self):
        self.usage = Usage()
        self.reported = False
        self.lock = threading.Lock()

    def __call__(self, usage: Usage):
        if not isinstance(usage, Usage):
            raise TypeError("Report an explicit Usage value")
        with self.lock:
            self.usage += usage
            self.reported = True

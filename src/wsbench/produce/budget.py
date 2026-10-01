"""Conservative cumulative cost arithmetic and deadlines; this module rents no resources."""

import math
import time
from dataclasses import asdict, dataclass

from .reference import ARM_IDS


class BudgetExceededError(RuntimeError):
    pass


def nonnegative(name, value, *, positive=False):
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    if positive and value == 0:
        raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class LeaseBudget:
    spent_before_usd: float
    hourly_usd: float  # Include active GPU and active disk charges.
    billing_started_at: float
    session_cap_usd: float
    retained_storage_reserve_usd: float
    reserve_usd: float = 3.0
    total_cap_usd: float = 20.0
    shutdown_margin_seconds: float = 120.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            nonnegative(
                name,
                value,
                positive=name
                in {"hourly_usd", "session_cap_usd", "total_cap_usd", "shutdown_margin_seconds"},
            )
        if self.total_cap_usd > 20:
            raise ValueError("goal authorization is at most $20 total new spending")
        if self.usable_session_usd <= 0:
            raise BudgetExceededError("prior spending and reserves exhaust the total cap")

    @property
    def usable_session_usd(self):
        return min(
            self.session_cap_usd,
            self.total_cap_usd
            - self.spent_before_usd
            - self.retained_storage_reserve_usd
            - self.reserve_usd,
        )


class BudgetGuard:
    def __init__(self, budget: LeaseBudget, *, wall=time.time, monotonic=time.monotonic):
        self.budget, self.wall, self.monotonic = budget, wall, monotonic
        self.initial_wall, self.initial_mono = wall(), monotonic()
        if budget.billing_started_at > self.initial_wall:
            raise ValueError("billing start must not be in the future")
        self._last_elapsed = self.initial_wall - budget.billing_started_at

    def elapsed(self):
        # Neither a wall-clock rollback nor a restarted guard refunds billed time.
        self._last_elapsed = max(
            self._last_elapsed,
            self.wall() - self.budget.billing_started_at,
            self.initial_wall
            - self.budget.billing_started_at
            + self.monotonic()
            - self.initial_mono,
        )
        return self._last_elapsed

    def snapshot(self):
        b = self.budget
        seconds = self.elapsed()
        cost = seconds * b.hourly_usd / 3600
        available = b.usable_session_usd - cost
        return {
            "elapsed_seconds": seconds,
            "estimated_session_usd": cost,
            "estimated_cumulative_usd": b.spent_before_usd + cost,
            "remaining_operational_usd": available,
            "seconds_until_stop": max(
                0, b.usable_session_usd * 3600 / b.hourly_usd - b.shutdown_margin_seconds - seconds
            ),
            "retained_storage_reserve_usd": b.retained_storage_reserve_usd,
            "provider_bill_reconciled": False,
        }

    def check(self):
        snapshot = self.snapshot()
        if snapshot["seconds_until_stop"] <= 0:
            raise BudgetExceededError(
                "stop compute: session or cumulative spending deadline reached"
            )
        return snapshot

    def require_forecast(self, phase_seconds: dict, *, margin: float, overhead_seconds: float):
        if set(phase_seconds) != {"capture", *ARM_IDS}:
            raise ValueError("forecast must explicitly include capture and all eight readers")
        for name, seconds in phase_seconds.items():
            nonnegative(name, seconds)
        nonnegative("overhead_seconds", overhead_seconds)
        nonnegative("margin", margin)
        if margin < 1.25:
            raise ValueError("forecast requires at least 25% runtime margin")
        snapshot = self.check()
        projected_seconds = sum(phase_seconds.values()) * margin + overhead_seconds
        if projected_seconds > snapshot["seconds_until_stop"]:
            raise BudgetExceededError("conservative full-roster forecast exceeds remaining budget")
        return {
            **snapshot,
            "phase_seconds": phase_seconds,
            "runtime_margin": margin,
            "overhead_seconds": overhead_seconds,
            "forecast_remaining_usd": projected_seconds * self.budget.hourly_usd / 3600,
        }

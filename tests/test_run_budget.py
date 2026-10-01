"""Cumulative deadlines include setup, storage, previous sessions and the full reader roster."""

from dataclasses import replace

import pytest

from wsbench.produce.budget import BudgetExceededError, BudgetGuard, LeaseBudget
from wsbench.produce.reference import ARM_IDS


def lease(**kwargs):
    return replace(LeaseBudget(4, 2, 100, 12, 1, shutdown_margin_seconds=120), **kwargs)


def test_deadline_includes_prior_spend_setup_storage_and_shutdown_margin():
    clock = [1900, 0]  # Half an hour already billed before the worker starts.
    g = BudgetGuard(lease(), wall=lambda: clock[0], monotonic=lambda: clock[1])
    assert g.check()["estimated_cumulative_usd"] == 5
    assert g.snapshot()["remaining_operational_usd"] == 11
    clock[:] = [100, 300]  # NTP rollback must not refund billed time.
    assert g.snapshot()["elapsed_seconds"] == 2100
    clock[:] = [100, 19660]
    assert g.check()["seconds_until_stop"] == pytest.approx(20)
    clock[1] += 20
    with pytest.raises(BudgetExceededError, match="deadline"):
        g.check()


def test_pilot_uses_only_its_session_allocation_and_restart_counts_setup():
    b = lease(spent_before_usd=0, hourly_usd=1, session_cap_usd=2)
    g = BudgetGuard(b, wall=lambda: 7180, monotonic=lambda: 0)
    with pytest.raises(BudgetExceededError):
        g.check()
    with pytest.raises(ValueError, match="future"):
        BudgetGuard(b, wall=lambda: 99, monotonic=lambda: 0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("spent_before_usd", -1),
        ("hourly_usd", 0),
        ("reserve_usd", float("nan")),
        ("retained_storage_reserve_usd", float("inf")),
        ("session_cap_usd", True),
        ("total_cap_usd", 21),
        ("shutdown_margin_seconds", 0),
    ],
)
def test_invalid_or_unauthorized_budgets_fail(field, value):
    with pytest.raises(ValueError):
        lease(**{field: value})


def test_forecast_cannot_omit_expensive_arms_or_ignore_overhead():
    g = BudgetGuard(lease(), wall=lambda: 100, monotonic=lambda: 0)
    phases = dict.fromkeys(["capture", *ARM_IDS], 300)
    result = g.require_forecast(phases, margin=1.5, overhead_seconds=300)
    assert result["forecast_remaining_usd"] == pytest.approx(4350 / 1800)
    del phases["oracle_sft"]
    with pytest.raises(ValueError, match="eight readers"):
        g.require_forecast(phases, margin=1.5, overhead_seconds=300)
    phases["oracle_sft"] = 15000
    with pytest.raises(BudgetExceededError, match="forecast"):
        g.require_forecast(phases, margin=1.5, overhead_seconds=300)
    with pytest.raises(ValueError, match="margin"):
        g.require_forecast(phases, margin=1, overhead_seconds=0)


def test_no_new_session_if_past_spend_exhausts_remaining_cap():
    with pytest.raises(BudgetExceededError):
        lease(spent_before_usd=17)

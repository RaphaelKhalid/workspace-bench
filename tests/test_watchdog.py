"""Only owned pods are stopped; hung workers and API acknowledgements cannot imply completion."""

import pytest

from wsbench.produce.budget import BudgetGuard, LeaseBudget
from wsbench.produce.watchdog import PodControlError, RunPodStopper, supervise


def pod(status="RUNNING", runtime=None):
    return {
        "id": "testpod123",
        "name": "wsbench-testrun123",
        "status": status,
        "runtime": runtime,
        "env": {"WSBENCH_RUN_ID": "testrun123"},
    }


def test_no_stop_of_unrelated_pod(monkeypatch):
    stopper = RunPodStopper("testpod123", "testrun123")
    calls = []

    def request(method, *args):
        calls.append(method)
        return {**pod(), "name": "someone-elses-pod"}

    monkeypatch.setattr(stopper, "_request", request)
    with pytest.raises(PodControlError, match="ownership"):
        stopper.stop_verified(sleep=lambda _: None)
    assert calls == ["GET"]


def test_stop_acknowledgement_requires_terminal_state_and_no_runtime(monkeypatch):
    stopper = RunPodStopper("testpod123", "testrun123")
    states = iter(
        [pod(), pod("EXITED", {"uptime": 1}), pod("EXITED", {"uptime": 1}), pod("EXITED")]
    )
    calls = []

    def request(method, suffix="", body=None):
        calls.append((method, suffix, body))
        return next(states) if method == "GET" else {"ok": True}

    monkeypatch.setattr(stopper, "_request", request)
    result = stopper.stop_verified(sleep=lambda _: None)
    assert result["verified"] and result["stop_requests"] == 2
    assert [c for c in calls if c[0] == "POST"] == [("POST", "/action", {"action": "stop"})] * 2


def test_api_failure_returns_unverified_instead_of_assuming_shutdown(monkeypatch):
    stopper = RunPodStopper("testpod123", "testrun123")
    monkeypatch.setattr(stopper, "_request", lambda *args: pod())
    stopper.inspect()

    def fail(*args):
        raise PodControlError("transport down")

    monkeypatch.setattr(stopper, "_request", fail)
    result = stopper.stop_verified(sleep=lambda _: None)
    assert result["verified"] is False and result["stop_requests"] == 0
    assert len(result["errors"]) == 3
    assert "billing may continue" in result["action_required"]


@pytest.mark.parametrize(
    "exit_code,deadline,reason",
    [
        (0, False, "completed"),
        (7, False, "worker_failed"),
        (None, False, "inactivity"),
        (None, True, "budget_deadline"),
    ],
)
def test_supervisor_stops_on_completion_failure_inactivity_or_budget(exit_code, deadline, reason):
    clock = [100.0]
    stopped, killed = [], []
    guard = BudgetGuard(
        LeaseBudget(0, 3600, 100, 10, 0, reserve_usd=0, shutdown_margin_seconds=1),
        wall=lambda: clock[0],
        monotonic=lambda: clock[0],
    )

    class Worker:
        def poll(self):
            return exit_code

        def kill(self):
            killed.append(True)

    class Stopper:
        pod_id = "testpod123"

        def inspect(self):
            return {"status": "RUNNING"}

        def stop_verified(self, **kwargs):
            stopped.append(True)
            return {"verified": True}

    def sleep(seconds):
        clock[0] += seconds

    result = supervise(
        Worker(),
        guard,
        Stopper(),
        progress=lambda: None,
        inactivity_seconds=100 if deadline else 3,
        poll_seconds=1,
        monotonic=lambda: clock[0],
        sleep=sleep,
    )
    assert result["reason"] == reason and result["shutdown"]["verified"]
    assert stopped == [True]
    assert bool(killed) == (exit_code is None)


def test_watchdog_must_be_external_to_verify_shutdown(monkeypatch):
    monkeypatch.setenv("RUNPOD_POD_ID", "testpod123")
    with pytest.raises(ValueError, match=r"outside|external"):
        supervise(None, None, RunPodStopper("testpod123", "testrun123"), progress=lambda: None)


@pytest.mark.parametrize("response", [None, [], {"env": None}, {"env": "bad"}])
def test_invalid_status_response_cannot_authorize_mutation(monkeypatch, response):
    stopper = RunPodStopper("testpod123", "testrun123")
    methods = []

    def request(method, *args):
        methods.append(method)
        return response

    monkeypatch.setattr(stopper, "_request", request)
    with pytest.raises(PodControlError, match="ownership"):
        stopper.stop_verified(sleep=lambda _: None)
    assert methods == ["GET"]

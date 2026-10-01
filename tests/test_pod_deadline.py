"""Independent stop deadlines are ownership-bound, monotonic and unaffected by model hangs."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from wsbench.produce.budget import BudgetGuard, LeaseBudget
from wsbench.produce.deadline import (
    arm_deadline,
    identity,
    pipe_alive,
    request_shutdown,
    watch_deadline,
)
from wsbench.produce.mirror import write_json
from wsbench.produce.watchdog import PodControlError, RunPodStopper


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNPOD_POD_ID", "testpod123")
    monkeypatch.setenv("WSBENCH_RUN_ID", "testrun123")
    clock = [1000.0]
    guard = BudgetGuard(
        LeaseBudget(0, 36, clock[0], 2, 0, reserve_usd=0),
        wall=lambda: clock[0],
        monotonic=lambda: clock[0],
    )  # 200 billed seconds, stop at80, with120 reserved for shutdown.
    calls = []

    class Stopper:
        pod_id, run_id = "testpod123", "testrun123"

        def inspect(self):
            calls.append("inspect")
            return {"status": "RUNNING"}

        def request_stop(self):
            calls.append("stop")
            return {"requested": True, "verified": False}

    def sleep(seconds):
        clock[0] += seconds

    return SimpleNamespace(
        clock=clock,
        guard=guard,
        stopper=Stopper(),
        calls=calls,
        sleep=sleep,
        paths={k: tmp_path / f"{k}.json" for k in ("ready", "terminal", "event")},
    )


def watch(s, **kwargs):
    return watch_deadline(
        s.guard,
        s.stopper,
        **s.paths,
        monotonic=lambda: s.clock[0],
        sleep=kwargs.pop("sleep", s.sleep),
        **kwargs,
    )


@pytest.mark.parametrize("kind", ["budget", "orphan", "complete", "failed", "foreign", "invalid"])
def test_deadline_or_terminal_state_stops_independently(state, kind):
    s = state

    def sleep(seconds):
        s.sleep(seconds)
        if kind in {"complete", "failed", "foreign", "invalid"}:
            data = {
                **identity(s.guard, s.stopper),
                "status": "complete" if kind == "complete" else "failed",
            }
            if kind == "foreign":
                data["run_id"] = "another-run"
            if kind == "invalid":
                data["status"] = "heartbeat"
            write_json(s.paths["terminal"], data)

    result = watch(s, sleep=sleep, parent_alive=lambda: kind != "orphan")
    expected = {
        "budget": "budget_deadline",
        "orphan": "controller_lost",
        "complete": "completion_grace_expired",
        "failed": "worker_failed",
        "foreign": "deadline_error",
        "invalid": "deadline_error",
    }[kind]
    assert result["reason"] == expected and s.calls == ["inspect", "stop"]
    assert result["shutdown"] == {"requested": True, "verified": False}
    if kind == "budget":
        assert s.clock[0] == 1080
    if kind == "complete":
        assert s.clock[0] == 1046  # Rewritten terminal marker never extends the grace.


def test_disk_failure_does_not_suppress_stop_request(state, monkeypatch):
    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("wsbench.produce.deadline.write_json", fail)
    with pytest.raises(OSError):
        watch(state)
    assert state.calls[-1] == "stop"


def test_wrong_pod_environment_cannot_arm_or_stop(state, monkeypatch):
    monkeypatch.setenv("RUNPOD_POD_ID", "unrelated")
    with pytest.raises(ValueError, match="exact marked pod"):
        watch(state)
    assert not state.calls


def test_budget_preempts_completion_export_grace(state):
    s = state
    s.clock[0] = 1078

    def sleep(seconds):
        s.sleep(seconds)
        write_json(s.paths["terminal"], {**identity(s.guard, s.stopper), "status": "complete"})

    result = watch(s, sleep=sleep)
    assert result["reason"] == "budget_deadline" and s.clock[0] == 1080


@pytest.mark.parametrize("ownership", [False, True])
def test_shutdown_failure_stays_unverified_and_retries_are_bounded(state, ownership):
    s = state
    calls = []

    def fail():
        calls.append(True)
        raise PodControlError("ownership marker mismatch" if ownership else "network down")

    s.stopper.request_stop = fail
    result = request_shutdown(s.stopper, sleep=s.sleep)
    assert not result["requested"] and not result["verified"]
    assert len(calls) == (1 if ownership else 3)
    assert "billing may continue" in result["action_required"]


def test_request_stop_rechecks_identity_and_never_claims_verified(monkeypatch):
    stopper = RunPodStopper("testpod123", "testrun123")
    calls = []
    pod = {
        "id": "testpod123",
        "name": "wsbench-testrun123",
        "status": "RUNNING",
        "runtime": {},
        "env": {"WSBENCH_RUN_ID": "testrun123"},
    }

    def request(method, *args):
        calls.append(method)
        return pod if method == "GET" else {"ok": True}

    monkeypatch.setattr(stopper, "_request", request)
    assert stopper.request_stop() == {"requested": True, "verified": False}
    assert calls == ["GET", "POST"]
    pod["env"]["WSBENCH_RUN_ID"] = "someone-else"
    with pytest.raises(PodControlError, match="ownership"):
        stopper.request_stop()
    assert calls == ["GET", "POST", "GET"]


@pytest.mark.parametrize("bad", [False, True])
def test_arm_requires_live_matching_receipt(state, tmp_path, bad):
    s = state
    started = []

    class Process:
        pid = 1234
        stdin = SimpleNamespace(close=lambda: started.append("closed"))

        def poll(self):
            return None

    def popen(command, **kwargs):
        assert kwargs["shell"] is False and kwargs["stdin"] == subprocess.PIPE
        assert kwargs.get("start_new_session") or kwargs.get("creationflags")
        spec = json.loads(Path(command[-1]).read_text())
        binding = {**identity(s.guard, s.stopper), "attempt_id": spec["attempt_id"]}
        if bad:
            binding["lease_sha256"] = "f" * 64
        write_json(Path(spec["ready"]), {**binding, "pid": 1234, "armed": True})
        started.append(spec)
        return Process()

    if bad:
        with pytest.raises(ValueError, match="receipt"):
            arm_deadline(s.guard, s.stopper, tmp_path / "journal", popen=popen)
        assert s.calls == ["stop"] and started[-1] == "closed"
    else:
        handle = arm_deadline(s.guard, s.stopper, tmp_path / "journal", popen=popen)
        assert not s.calls  # The child, represented by its live receipt, performs the API check.
        handle.mark_terminal("complete")
        assert json.loads(Path(handle.spec["terminal"]).read_text())["status"] == "complete"
        assert started[-1] == "closed"


def test_pipe_detects_controller_loss_without_a_clock_or_pid_lookup():
    read, write = os.pipe()
    try:
        os.set_blocking(read, False)
        assert pipe_alive(read)
        os.close(write)
        write = None
        assert not pipe_alive(read)
    finally:
        os.close(read)
        if write is not None:
            os.close(write)


def test_real_independent_process_detects_pipe_close(tmp_path):
    # No API client or GPU: exercise the real watch loop and OS pipe in another interpreter.
    script = """
import os, sys, time
from pathlib import Path
from wsbench.produce.budget import BudgetGuard, LeaseBudget
from wsbench.produce.deadline import watch_deadline, pipe_alive
os.environ['RUNPOD_POD_ID']='testpod123'
os.environ['WSBENCH_RUN_ID']='testrun123'
class Stopper:
    pod_id, run_id='testpod123','testrun123'
    def inspect(self): return {'status':'RUNNING'}
    def request_stop(self): return {'requested':True,'verified':False}
root=Path(sys.argv[1])
fd=sys.stdin.fileno()
os.set_blocking(fd,False)
guard=BudgetGuard(LeaseBudget(0,36,time.time(),2,0,reserve_usd=0))
watch_deadline(guard,Stopper(),ready=root/'ready.json',terminal=root/'terminal.json',
               event=root/'event.json',poll_seconds=.05,parent_alive=lambda:pipe_alive(fd))
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        end = time.monotonic() + 10
        while not (tmp_path / "ready.json").exists() and process.poll() is None:
            assert time.monotonic() < end, "deadline subprocess did not arm"
            time.sleep(0.02)
        assert process.poll() is None
        process.stdin.close()
        process.wait(timeout=5)
        assert process.returncode == 0, process.stderr.read().decode()
        result = json.loads((tmp_path / "event.json").read_text())
        assert result["reason"] == "controller_lost"
        assert result["shutdown"]["requested"] and not result["shutdown"]["verified"]
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        process.stderr.close()


@pytest.mark.parametrize("failed", [False, True])
def test_actual_detached_cli_arms_and_stops_after_controller_finishes(state, tmp_path, failed):
    s = state
    # Replace only the cloud transport; use the real CLI, lease serialization and detached process.
    script = """
import sys
from wsbench.produce import deadline
class Stopper:
    def __init__(self,pod_id,run_id): self.pod_id,self.run_id=pod_id,run_id
    def inspect(self): return {'status':'RUNNING'}
    def request_stop(self): return {'requested':True,'verified':False}
deadline.RunPodStopper=Stopper
sys.argv=['deadline','--spec',sys.argv[1]]
deadline.main()
"""
    processes = []

    def popen(command, **kwargs):
        process = subprocess.Popen([sys.executable, "-c", script, command[-1]], **kwargs)
        processes.append(process)
        return process

    # Real clocks for the child; preserve the120-second stop allowance in the lease.
    guard = BudgetGuard(LeaseBudget(0, 36, time.time(), 2, 0, reserve_usd=0))
    handle = None
    try:
        handle = arm_deadline(guard, s.stopper, tmp_path / "detached", popen=popen)
        if failed:
            handle.mark_terminal("failed")
        else:
            handle.process.stdin.close()
        handle.process.wait(timeout=5)
        assert handle.process.returncode == 0
        result = json.loads(Path(handle.spec["event"]).read_text())
        assert result["reason"] == ("worker_failed" if failed else "controller_lost")
        assert result["shutdown"] == {"requested": True, "verified": False}
        assert not s.calls  # No parent fallback needed, no actual API transport anywhere.
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
            process.stdin.close()

"""Independent on-pod spending deadline; shutdown acknowledgement is never verification."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from wsbench.cell_manifest import digest

from .budget import BudgetGuard, LeaseBudget, nonnegative
from .mirror import write_json
from .storage import file_lock
from .watchdog import PodControlError, RunPodStopper


def read_metadata(path):
    with Path(path).open("rb") as stream:
        data = stream.read(16 * 1024 + 1)
    if len(data) > 16 * 1024:
        raise ValueError("deadline metadata exceeds bound")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("deadline metadata must be an object")
    return value


def identity(guard, stopper):
    return {
        "run_id": stopper.run_id,
        "pod_id": stopper.pod_id,
        "lease_sha256": digest(asdict(guard.budget)),
    }


def require_local_pod(stopper):
    if (
        os.environ.get("RUNPOD_POD_ID") != stopper.pod_id
        or os.environ.get("WSBENCH_RUN_ID") != stopper.run_id
    ):
        raise ValueError("deadline process must run inside its exact marked pod")


def request_shutdown(stopper, *, sleep=time.sleep):
    errors = []
    for _ in range(3):
        try:
            return stopper.request_stop()
        except PodControlError as exc:
            errors.append(str(exc))
            if "ownership marker mismatch" in str(exc):
                break
            sleep(2)
    return {
        "requested": False,
        "verified": False,
        "errors": errors,
        "action_required": "external shutdown verification required; billing may continue",
    }


def watch_deadline(
    guard,
    stopper,
    *,
    ready,
    terminal,
    event,
    poll_seconds=1,
    completion_grace_seconds=45,
    monotonic=time.monotonic,
    sleep=time.sleep,
    parent_alive=lambda: True,
    attempt_id=None,
):
    """Wait independently of model execution; malformed terminal state fails closed."""
    require_local_pod(stopper)
    nonnegative("poll_seconds", poll_seconds, positive=True)
    nonnegative("completion_grace_seconds", completion_grace_seconds)
    if poll_seconds > 5 or completion_grace_seconds > 60:
        raise ValueError("deadline polls capped at five seconds and export grace at sixty")
    if guard.budget.shutdown_margin_seconds < 120:
        raise ValueError("independent deadline requires a 120-second shutdown margin")
    ready, terminal, event = [Path(p).resolve() for p in (ready, terminal, event)]
    if len({ready, terminal, event}) != 3:
        raise ValueError("deadline metadata paths must be distinct")
    binding = identity(guard, stopper)
    if attempt_id is not None:
        if not isinstance(attempt_id, str) or not re.fullmatch(r"[a-f0-9]{32}", attempt_id):
            raise ValueError("invalid deadline attempt identity")
        binding["attempt_id"] = attempt_id
    # A competing watcher must not publish another readiness receipt or extend this lease.
    with file_lock(ready.with_suffix(".lock")):
        result = {**binding, "reason": None, "shutdown": None}
        try:
            if ready.exists() or terminal.exists():
                raise ValueError("deadline attempt paths must be fresh")
            state = stopper.inspect()
            if state["status"] != "RUNNING":
                raise PodControlError("owned pod is not running")
            guard.check()
            write_json(ready, {**binding, "pid": os.getpid(), "armed": True})
            completion_deadline = None
            while True:
                remaining = guard.snapshot()["seconds_until_stop"]
                if remaining <= 0:
                    result["reason"] = "budget_deadline"
                    break
                if terminal.exists():
                    done = read_metadata(terminal)
                    if (
                        set(done) != {*binding, "status"}
                        or any(done.get(k) != v for k, v in binding.items())
                        or done["status"] not in {"complete", "failed"}
                    ):
                        raise ValueError("foreign or invalid worker terminal marker")
                    if done["status"] == "failed":
                        result["reason"] = "worker_failed"
                        break
                    if completion_deadline is None:
                        completion_deadline = monotonic() + completion_grace_seconds
                elif not parent_alive():
                    result["reason"] = "controller_lost"
                    break
                if completion_deadline is not None:
                    remaining = min(remaining, completion_deadline - monotonic())
                    if remaining <= 0:
                        result["reason"] = "completion_grace_expired"
                        break
                sleep(min(poll_seconds, remaining))
        except BaseException as exc:
            result.update(reason="deadline_error", error_type=type(exc).__name__)
        finally:
            # Even a full disk preventing event publication cannot suppress the stop request.
            try:
                write_json(event, {**result, "stop_pending": True})
            finally:
                result["shutdown"] = request_shutdown(stopper, sleep=sleep)
            write_json(event, result)
        return result


def pipe_alive(fd):
    try:
        value = os.read(fd, 1)
    except BlockingIOError:
        return True
    if value:
        raise ValueError("deadline liveness pipe must not carry data")
    return False


class DeadlineHandle:
    def __init__(self, process, spec, binding):
        self.process, self.spec, self.binding = process, spec, binding

    def check(self):
        if self.process.poll() is not None:
            raise RuntimeError("independent deadline process exited; stop computation")

    def mark_terminal(self, status):
        if status not in {"complete", "failed"}:
            raise ValueError("invalid worker terminal status")
        try:
            write_json(Path(self.spec["terminal"]), {**self.binding, "status": status})
        finally:
            self.process.stdin.close()


def arm_deadline(
    guard, stopper, journal, *, popen=subprocess.Popen, monotonic=time.monotonic, sleep=time.sleep
):
    """Start a detached helper; require its live, lease-bound receipt before any model work."""
    require_local_pod(stopper)
    guard.check()
    if guard.budget.shutdown_margin_seconds < 120:
        raise ValueError("independent deadline requires a 120-second shutdown margin")
    journal = Path(journal).resolve() / uuid.uuid4().hex
    journal.mkdir(parents=True)
    binding = {**identity(guard, stopper), "attempt_id": journal.name}
    spec = {
        "run_id": stopper.run_id,
        "pod_id": stopper.pod_id,
        "budget": asdict(guard.budget),
        "attempt_id": journal.name,
        **{key: str(journal / f"{key}.json") for key in ("ready", "terminal", "event")},
    }
    path = journal / "spec.json"
    write_json(path, spec)
    environment = dict(os.environ)
    for key in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HF_TOKEN"):
        environment.pop(key, None)
    options = (
        {"start_new_session": True}
        if os.name == "posix"
        else {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS}
    )
    handle = None
    try:
        process = popen(
            [sys.executable, "-m", "wsbench.produce.deadline", "--spec", str(path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            shell=False,
            **options,
        )
        handle = DeadlineHandle(process, spec, binding)
        end = monotonic() + min(10, guard.snapshot()["seconds_until_stop"])
        while monotonic() < end:
            handle.check()
            if Path(spec["ready"]).exists():
                ready = read_metadata(spec["ready"])
                # Windows venv launchers may have a different PID from the interpreter they own.
                # Bind the fresh receipt to the random attempt and the still-live process handle.
                pid = ready.get("pid")
                if (
                    type(pid) is not int
                    or pid <= 0
                    or ready != {**binding, "pid": pid, "armed": True}
                    or (os.name == "posix" and pid != process.pid)
                ):
                    raise ValueError("deadline readiness receipt differs")
                guard.check()
                handle.check()
                return handle
            sleep(0.05)
        raise TimeoutError("independent deadline did not arm within its startup allowance")
    except BaseException:
        try:
            if handle is not None:
                handle.mark_terminal("failed")
        finally:
            request_shutdown(stopper, sleep=sleep)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    spec = read_metadata(args.spec)
    if set(spec) != {"run_id", "pod_id", "budget", "ready", "terminal", "event", "attempt_id"}:
        raise ValueError("invalid deadline specification")
    stopper = RunPodStopper(spec["pod_id"], spec["run_id"])
    require_local_pod(stopper)
    guard = BudgetGuard(LeaseBudget(**spec["budget"]))
    fd = sys.stdin.fileno()
    os.set_blocking(fd, False)
    result = watch_deadline(
        guard,
        stopper,
        ready=spec["ready"],
        terminal=spec["terminal"],
        event=spec["event"],
        parent_alive=lambda: pipe_alive(fd),
        attempt_id=spec["attempt_id"],
    )
    print(json.dumps(result))
    raise SystemExit(0 if result["shutdown"]["requested"] else 2)


if __name__ == "__main__":
    main()

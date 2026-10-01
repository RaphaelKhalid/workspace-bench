"""External supervisor primitives: stop only a marked goal-owned pod and verify its exit."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .budget import BudgetExceededError, nonnegative


class PodControlError(RuntimeError):
    pass


def control_request(
    operation, pod_id, *, timeout_seconds=10, popen=subprocess.Popen, monotonic=time.monotonic
):
    """Bound DNS, TLS and response reading together; allow one second to reap on failure."""
    if operation not in {"inspect", "stop"} or not re.fullmatch(r"[a-z0-9-]{6,64}", pod_id):
        raise PodControlError("invalid control operation")
    nonnegative("control timeout", timeout_seconds, positive=True)
    if timeout_seconds > 10:
        raise ValueError("control timeout must be at most ten seconds")
    if not os.environ.get("RUNPOD_API_KEY"):
        raise PodControlError("RunPod API key missing")
    environment = {
        k: v
        for k, v in os.environ.items()
        if k == "RUNPOD_API_KEY" or not k.upper().endswith(("_API_KEY", "_TOKEN"))
    }
    process = None
    deadline = monotonic() + timeout_seconds
    try:
        process = popen(
            [
                sys._base_executable,  # Avoid the Windows virtualenv launcher proxy.
                "-I",
                str(Path(__file__).with_name("control_transport.py")),
                operation,
                pod_id,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        raw, _ = process.communicate(timeout=max(0, deadline - monotonic()))
        if monotonic() > deadline:
            raise PodControlError("RunPod control elapsed deadline exceeded")
        if process.returncode != 0 or len(raw) > 4096:
            raise PodControlError("RunPod control helper failed or exceeded response bound")
        report = json.loads(raw)
        if (
            not isinstance(report, dict)
            or report.get("ok") is not True
            or not isinstance(report.get("value"), dict)
        ):
            raise PodControlError("RunPod control request failed; shutdown remains unverified")
        return report["value"]
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise PodControlError(f"RunPod control failed: {type(exc).__name__}") from None
    finally:
        if process is not None:
            reaped = False
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=1)
                reaped = True
            except (OSError, subprocess.SubprocessError) as exc:
                raise PodControlError(
                    f"RunPod control cleanup failed: {type(exc).__name__}"
                ) from None
            finally:
                # A Windows communicate reader can hold the buffered pipe lock until EOF.
                # If termination/reaping failed, close could block past the cleanup bound.
                if reaped and process.stdout is not None:
                    process.stdout.close()


class RunPodStopper:
    def __init__(self, pod_id: str, run_id: str):
        if not re.fullmatch(r"[a-z0-9-]{6,64}", pod_id):
            raise ValueError("invalid pod ID")
        if not re.fullmatch(r"[a-z0-9-]{8,64}", run_id):
            raise ValueError("invalid run ID")
        self.pod_id, self.run_id = pod_id, run_id

    def _request(self, method, suffix="", body=None):
        if method == "GET" and suffix == "" and body is None:
            return control_request("inspect", self.pod_id)
        if method == "POST" and suffix == "/action" and body == {"action": "stop"}:
            return control_request("stop", self.pod_id)
        raise PodControlError("unsupported control operation")

    def inspect(self):
        pod = self._request("GET")
        if not isinstance(pod, dict) or not isinstance(pod.get("env"), dict):
            raise PodControlError("pod ownership marker mismatch; invalid response schema")
        if (
            pod.get("id") != self.pod_id
            or pod.get("name") != f"wsbench-{self.run_id}"
            or pod.get("env", {}).get("WSBENCH_RUN_ID") != self.run_id
        ):
            raise PodControlError("pod ownership marker mismatch; refuse mutation")
        return {
            "id": self.pod_id,
            "status": pod.get("status"),
            "runtime_absent": "runtime" in pod and pod["runtime"] is None,
        }

    def stop_verified(self, *, attempts=3, sleep=time.sleep):
        if type(attempts) is not int or not 1 <= attempts <= 3:
            raise ValueError("shutdown attempts must be 1..3")
        errors, sent = [], 0
        for _ in range(attempts):
            try:
                # Recheck ownership before every mutation, including retries.
                state = self.inspect()
                if state["status"] == "EXITED" and state["runtime_absent"]:
                    return {"verified": True, "state": state, "stop_requests": sent}
                sent += 1
                self._request("POST", "/action", {"action": "stop"})
                state = self.inspect()
                if state["status"] == "EXITED" and state["runtime_absent"]:
                    return {"verified": True, "state": state, "stop_requests": sent}
            except PodControlError as exc:
                errors.append(str(exc))
                # A changed identity is never treated as a transient transport failure.
                if "ownership marker mismatch" in str(exc):
                    raise
            sleep(2)
        return {
            "verified": False,
            "stop_requests": sent,
            "errors": errors,
            "action_required": "recheck API and stop the verified owned pod; billing may continue",
        }

    def request_stop(self):
        """On-pod fallback: recheck ownership, request stop, leave verification external."""
        state = self.inspect()
        if state["status"] == "EXITED" and state["runtime_absent"]:
            return {"requested": False, "verified": False, "reason": "already_exited"}
        self._request("POST", "/action", {"action": "stop"})
        return {"requested": True, "verified": False}


def supervise(
    worker,
    guard,
    stopper,
    *,
    progress=None,
    mirror=None,
    inactivity_seconds=300,
    poll_seconds=5,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    """Poll outside the model process; worker.kill must be bounded and reap its owned child."""
    nonnegative("inactivity_seconds", inactivity_seconds, positive=True)
    nonnegative("poll_seconds", poll_seconds, positive=True)
    if poll_seconds > 10:
        raise ValueError("watchdog poll interval must be at most ten seconds")
    if mirror is None and not callable(progress):
        raise ValueError("supervisor requires a checkpoint progress callback or export mirror")
    # This function must run outside the pod so it survives the stop and can verify it.
    if os.environ.get("RUNPOD_POD_ID") == stopper.pod_id:
        raise ValueError("external supervisor cannot verify shutdown from inside its target pod")
    last_change, last_progress = monotonic(), None
    result = {"reason": None, "worker_exit": None, "shutdown": None}
    try:
        state = stopper.inspect()
        if state["status"] != "RUNNING":
            raise PodControlError("owned pod is not running; supervisor never starts or resumes it")
        start = getattr(worker, "start", None)
        if callable(start):
            guard.check()
            start()
        while True:
            result["worker_exit"] = worker.poll()
            if result["worker_exit"] is not None:
                result["reason"] = "completed" if result["worker_exit"] == 0 else "worker_failed"
                break
            try:
                guard.check()
            except BudgetExceededError:
                result["reason"] = "budget_deadline"
                break
            # Progress is a verified checkpoint identity/count, not a timer heartbeat.
            current = mirror.tick() if mirror is not None else progress()
            if current != last_progress:
                last_progress, last_change = current, monotonic()
            if monotonic() - last_change >= inactivity_seconds:
                result["reason"] = "inactivity"
                break
            sleep(poll_seconds)
    except BaseException as exc:
        result["reason"] = "supervisor_error"
        result["error_type"] = type(exc).__name__
    finally:
        try:
            if worker.poll() is None:
                worker.kill()
        except BaseException as exc:
            result["worker_cleanup_error"] = type(exc).__name__
        finally:
            try:
                if mirror is not None:
                    if result["reason"] == "completed":
                        allowance = min(30, guard.snapshot()["seconds_until_stop"])
                        result["export"] = mirror.finish(allowance)
                    else:
                        mirror.close()
                        result["export"] = {"status": "cancelled", "reason": result["reason"]}
            except BaseException as exc:
                result["export"] = {"status": "failed", "error_type": type(exc).__name__}
                try:
                    mirror.close()
                except BaseException as cleanup:
                    result["export"]["cleanup_error_type"] = type(cleanup).__name__
            finally:
                try:
                    result["shutdown"] = stopper.stop_verified(sleep=sleep)
                except PodControlError as exc:
                    result["shutdown"] = {"verified": False, "error": str(exc)}
    result["budget"] = guard.snapshot()
    return result

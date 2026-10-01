"""External supervisor primitives: stop only a marked goal-owned pod and verify its exit."""

import json
import os
import re
import time
import urllib.request

from .budget import BudgetExceededError, nonnegative


class PodControlError(RuntimeError):
    pass


class RunPodStopper:
    def __init__(self, pod_id: str, run_id: str):
        if not re.fullmatch(r"[a-z0-9-]{6,64}", pod_id):
            raise ValueError("invalid pod ID")
        if not re.fullmatch(r"[a-z0-9-]{8,64}", run_id):
            raise ValueError("invalid run ID")
        self.pod_id, self.run_id = pod_id, run_id

    def _request(self, method, suffix="", body=None):
        key = os.environ.get("RUNPOD_API_KEY")
        if not key:
            raise PodControlError("RunPod API key missing")
        request = urllib.request.Request(
            f"https://api.runpod.io/v2/pods/{self.pod_id}{suffix}",
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "wsbench-budget-guard/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read()
                return json.loads(data) if data else {}
        except (OSError, ValueError) as exc:
            # Never include provider bodies/headers; those can contain account or environment data.
            raise PodControlError(f"RunPod {method} failed: {type(exc).__name__}") from None

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

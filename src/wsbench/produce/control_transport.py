"""Isolated RunPod transport worker; invoked by watchdog with an external elapsed deadline."""

import argparse
import json
import os
import re
import urllib.request

RESPONSE_LIMIT = 64 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(operation, pod_id, *, opener=None):
    if operation not in {"inspect", "stop"} or not re.fullmatch(r"[a-z0-9-]{6,64}", pod_id):
        raise ValueError("invalid control operation")
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise ValueError("missing API credential")
    stopping = operation == "stop"
    req = urllib.request.Request(
        f"https://api.runpod.io/v2/pods/{pod_id}" + ("/action" if stopping else ""),
        method="POST" if stopping else "GET",
        data=b'{"action":"stop"}' if stopping else None,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "wsbench-budget-guard/1.0",
        },
    )
    if opener is None:
        opener = urllib.request.build_opener(NoRedirect())
    with opener.open(req, timeout=10) as response:
        raw = response.read(RESPONSE_LIMIT + 1)
    if len(raw) > RESPONSE_LIMIT:
        raise ValueError("control response exceeds bound")
    data = json.loads(raw) if raw else {}
    if not isinstance(data, dict):
        raise ValueError("invalid control response")
    if stopping:
        # An accepted request is never evidence the pod actually exited.
        return {}
    if not isinstance(data.get("env"), dict):
        raise ValueError("invalid pod identity response")
    result = {k: data.get(k) for k in ("id", "name", "status")}
    result["env"] = {"WSBENCH_RUN_ID": data["env"].get("WSBENCH_RUN_ID")}
    values = [result[k] for k in ("id", "name", "status")] + [result["env"]["WSBENCH_RUN_ID"]]
    if any(not isinstance(v, str) or len(v) > 128 for v in values):
        raise ValueError("invalid pod identity fields")
    if "runtime" in data:
        result["runtime"] = None if data["runtime"] is None else {}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "stop"))
    parser.add_argument("pod_id")
    args = parser.parse_args()
    try:
        report = {"ok": True, "value": request(args.operation, args.pod_id)}
    except Exception as exc:
        # No provider body, URL, request headers, or arbitrary exception message crosses stdout.
        report = {"ok": False, "error_type": type(exc).__name__}
    print(json.dumps(report))


if __name__ == "__main__":
    main()

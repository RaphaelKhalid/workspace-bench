"""Bounded control requests, including a real trickling localhost response; no cloud calls."""

import io
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from wsbench.produce import control_transport, watchdog
from wsbench.produce.watchdog import PodControlError, RunPodStopper, control_request


def pod():
    return {
        "id": "testpod123",
        "name": "wsbench-testrun123",
        "status": "EXITED",
        "runtime": None,
        "env": {"WSBENCH_RUN_ID": "testrun123", "RUNPOD_API_KEY": "secret-in-provider-body"},
        "unrelated_private_field": "secret-in-provider-body",
    }


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "fake-test-credential")


def opener(data, seen):
    def open_(req, timeout):
        seen.append((req, timeout))
        return io.BytesIO(data)

    return SimpleNamespace(open=open_)


def test_inspection_exports_only_ownership_and_exit_fields():
    seen = []
    result = control_transport.request(
        "inspect", "testpod123", opener=opener(json.dumps(pod()).encode(), seen)
    )
    assert result == {
        "id": "testpod123",
        "name": "wsbench-testrun123",
        "status": "EXITED",
        "runtime": None,
        "env": {"WSBENCH_RUN_ID": "testrun123"},
    }
    req, timeout = seen[0]
    assert req.full_url == "https://api.runpod.io/v2/pods/testpod123"
    assert req.method == "GET" and timeout == 10
    assert "secret-in-provider-body" not in json.dumps(result)


def test_missing_runtime_is_not_rewritten_as_absent():
    data = pod()
    del data["runtime"]
    result = control_transport.request(
        "inspect", "testpod123", opener=opener(json.dumps(data).encode(), [])
    )
    assert "runtime" not in result
    data["runtime"] = {"sensitive_runtime_field": "private"}
    result = control_transport.request(
        "inspect", "testpod123", opener=opener(json.dumps(data).encode(), [])
    )
    assert result["runtime"] == {}


def test_stop_request_is_fixed_and_acknowledgement_is_not_status():
    seen = []
    result = control_transport.request(
        "stop", "testpod123", opener=opener(b'{"secret":"discard"}', seen)
    )
    req, _ = seen[0]
    assert req.method == "POST" and req.full_url.endswith("/testpod123/action")
    assert json.loads(req.data) == {"action": "stop"} and result == {}


@pytest.mark.parametrize(
    "data",
    [b"x" * (65536 + 1), b"not-json", b"[]", b'{"env":null}'],
    ids=["oversized", "not-json", "array", "null-env"],
)
def test_invalid_or_oversized_response_fails(data):
    with pytest.raises(ValueError):
        control_transport.request("inspect", "testpod123", opener=opener(data, []))


def test_redirect_cannot_forward_credentials():
    assert (
        control_transport.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other")
        is None
    )


def test_helper_failure_does_not_print_exception_secrets(monkeypatch, capsys):
    def fail(*args):
        raise OSError("private headers and credential")

    monkeypatch.setattr(control_transport, "request", fail)
    monkeypatch.setattr(sys, "argv", ["control", "inspect", "testpod123"])
    control_transport.main()
    assert json.loads(capsys.readouterr().out) == {"ok": False, "error_type": "OSError"}


class Process:
    def __init__(self, response=b'{"ok":true,"value":{}}', error=None):
        self.response, self.error = response, error
        self.returncode = None if error else 0
        self.stdout = io.BytesIO()
        self.killed, self.waits, self.timeout = False, [], None

    def communicate(self, timeout):
        self.timeout = timeout
        if self.error:
            raise self.error
        return self.response, None

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed, self.returncode = True, -9

    def wait(self, timeout):
        self.waits.append(timeout)
        return self.returncode


def test_parent_applies_deadline_to_startup_and_read_then_reaps(monkeypatch):
    clock = [100.0]
    process = Process()
    calls = []
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-for-control")
    monkeypatch.setenv("HF_TOKEN", "not-for-control")

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        clock[0] += 3
        return process

    assert control_request("inspect", "testpod123", popen=popen, monotonic=lambda: clock[0]) == {}
    assert process.timeout == 7 and process.waits == [1] and process.stdout.closed
    command, options = calls[0]
    assert command[:2] == [sys._base_executable, "-I"] and options["shell"] is False
    assert options["env"]["RUNPOD_API_KEY"] == "fake-test-credential"
    assert "HF_TOKEN" not in options["env"] and "OPENROUTER_API_KEY" not in options["env"]
    assert "fake-test-credential" not in " ".join(command)


@pytest.mark.parametrize(
    "response",
    [b"x" * 4097, b"oops", b"[]", b'{"ok":false}', b'{"ok":true,"value":null}'],
    ids=["oversized", "not-json", "array", "failed", "null-value"],
)
def test_parent_rejects_invalid_helper_results_and_closes_pipe(response):
    process = Process(response)
    with pytest.raises(PodControlError):
        control_request("inspect", "testpod123", popen=lambda *a, **k: process)
    assert process.waits == [1] and process.stdout.closed


def test_timeout_is_sanitized_and_child_is_killed_and_reaped():
    process = Process(error=subprocess.TimeoutExpired("secret-command", 10))
    with pytest.raises(PodControlError, match="TimeoutExpired") as exc:
        control_request("inspect", "testpod123", popen=lambda *a, **k: process)
    assert "secret-command" not in str(exc.value)
    assert process.killed and process.waits == [1] and process.stdout.closed


def test_cleanup_timeout_cannot_hang_or_claim_success():
    process = Process(error=subprocess.TimeoutExpired("helper", 10))

    def fail(timeout):
        assert timeout == 1
        raise subprocess.TimeoutExpired("helper", timeout)

    process.wait = fail
    with pytest.raises(PodControlError, match="cleanup failed"):
        control_request("inspect", "testpod123", popen=lambda *a, **k: process)
    assert process.killed and not process.stdout.closed
    process.stdout.close()  # Test fake has no reader; production must not block on a live pipe.


def test_stopper_can_only_dispatch_inspect_and_stop(monkeypatch):
    calls = []
    monkeypatch.setattr(watchdog, "control_request", lambda *args: calls.append(args) or {})
    stopper = RunPodStopper("testpod123", "testrun123")
    stopper._request("GET")
    stopper._request("POST", "/action", {"action": "stop"})
    with pytest.raises(PodControlError, match="unsupported"):
        stopper._request("DELETE")
    assert calls == [("inspect", "testpod123"), ("stop", "testpod123")]


def test_nine_request_shutdown_path_fits_reserved_control_time(monkeypatch):
    clock, operations = [0.0], []
    original = watchdog.control_request

    def popen(command, **kwargs):
        operation = command[-2]
        operations.append(operation)
        value = pod() if operation == "inspect" else {}
        if operation == "inspect":
            value["status"], value["runtime"] = "RUNNING", {}
        process = Process(json.dumps({"ok": True, "value": value}).encode())
        communicate = process.communicate

        def slow(timeout):
            clock[0] += timeout  # Every request uses the entire ten-second allowance.
            return communicate(timeout)

        def reap(timeout):
            clock[0] += timeout  # Conservative: cleanup also consumes its full allowance.
            return process.returncode

        process.communicate, process.wait = slow, reap
        return process

    monkeypatch.setattr(
        watchdog,
        "control_request",
        lambda op, pid: original(op, pid, popen=popen, monotonic=lambda: clock[0]),
    )

    def sleep(seconds):
        clock[0] += seconds

    result = RunPodStopper("testpod123", "testrun123").stop_verified(sleep=sleep)
    assert operations == ["inspect", "stop", "inspect"] * 3
    assert clock[0] == 105 and not result["verified"] and result["stop_requests"] == 3


@pytest.mark.parametrize("timeout", [0, True, 11, float("inf")])
def test_timeout_cannot_disable_or_extend_protection(timeout):
    with pytest.raises(ValueError):
        control_request("inspect", "testpod123", timeout_seconds=timeout)


def test_real_trickling_response_cannot_extend_elapsed_deadline():
    entered = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            entered.set()
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            try:
                for _ in range(1000):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.02)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    children = []
    url = f"http://127.0.0.1:{server.server_port}/"
    # Redirect only the child's transport to localhost; production URL is fixed.
    script = (
        "import sys,runpy,urllib.request\n"
        "original=urllib.request.build_opener\n"
        "class Local:\n"
        f" def open(self, req, timeout): return original().open({url!r}, timeout=timeout)\n"
        "urllib.request.build_opener=lambda *args:Local()\n"
        "path=sys.argv[1]; sys.argv=sys.argv[1:]\n"
        "runpy.run_path(path,run_name='__main__')\n"
    )

    def popen(command, **kwargs):
        process = subprocess.Popen(
            [sys._base_executable, "-I", "-c", script, *command[2:]], **kwargs
        )
        children.append(process)
        return process

    start = time.monotonic()
    try:
        with pytest.raises(PodControlError, match="TimeoutExpired"):
            control_request("inspect", "testpod123", timeout_seconds=1, popen=popen)
        assert entered.is_set() and time.monotonic() - start < 3
        assert len(children) == 1 and children[0].poll() is not None
    finally:
        for process in children:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=1)
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)

"""Remote command binding and cleanup with simulated SSH/cloud; no resource mutations."""

import json
import shlex
import subprocess
import sys
from dataclasses import asdict
from types import SimpleNamespace

import paramiko
import pytest

from wsbench.cell_manifest import digest
from wsbench.produce import remote, worker
from wsbench.produce.budget import BudgetGuard, LeaseBudget
from wsbench.produce.watchdog import supervise


@pytest.fixture
def connection(tmp_path, monkeypatch):
    key = paramiko.RSAKey.generate(1024)
    identity = tmp_path / "private key"
    key.write_private_key_file(str(identity))
    known = tmp_path / "known hosts"
    known.write_text(f"[127.0.0.1]:2222 ssh-rsa {key.get_base64()}\n", encoding="utf-8")
    monkeypatch.setattr(remote.shutil, "which", lambda _: "/local/ssh")
    return {
        "host": "127.0.0.1",
        "port": 2222,
        "username": "root",
        "key_file": str(identity),
        "known_hosts": str(known),
    }


def test_command_pins_host_and_identity_and_quotes_remote_paths(connection):
    python = "/workspace/a ' $(touch secret)/python"
    spec = "/workspace/spec $(echo nope).json"
    cmd = remote.ssh_command(connection, python, spec, "a" * 64)
    assert cmd[:4] == ["/local/ssh", "-F", "none", "-T"]
    assert shlex.split(cmd[-1]) == [
        "exec",
        python,
        "-m",
        "wsbench.produce.worker",
        "--spec",
        spec,
        "--spec-sha256",
        "a" * 64,
    ]
    assert "StrictHostKeyChecking=yes" in cmd
    assert "IdentityAgent=none" in cmd and "ClearAllForwardings=yes" in cmd
    assert cmd[cmd.index("-i") + 1] == connection["key_file"]
    assert 'UserKnownHostsFile="' in " ".join(cmd)


@pytest.mark.parametrize(
    "field,value",
    [
        ("host", "-oProxyCommand=bad"),
        ("host", "host;bad"),
        ("port", True),
        ("port", 0),
        ("username", "root;bad"),
    ],
)
def test_rejects_connection_option_injection(connection, field, value):
    connection[field] = value
    with pytest.raises(ValueError):
        remote.ssh_command(connection, "/python", "/spec", "a" * 64)


def test_unknown_host_or_missing_ssh_fails_closed(connection, monkeypatch):
    foreign = {**connection, "host": "127.0.0.2"}
    with pytest.raises(ValueError, match="not pinned"):
        remote.ssh_command(foreign, "/python", "/spec", "a" * 64)
    monkeypatch.setattr(remote.shutil, "which", lambda _: None)
    with pytest.raises(ValueError, match="unavailable"):
        remote.ssh_command(connection, "/python", "/spec", "a" * 64)


@pytest.mark.parametrize("path", ["relative", "/a/../b", "/a//b", "/a\nb"])
def test_rejects_ambiguous_remote_paths(path):
    with pytest.raises(ValueError):
        remote.remote_path(path)


class Process:
    def __init__(self, code=None):
        self.code, self.killed, self.waits = code, False, []

    def poll(self):
        return self.code

    def kill(self):
        self.killed, self.code = True, -9

    def wait(self, timeout):
        self.waits.append(timeout)
        return self.code


def test_worker_is_nonblocking_and_kills_only_its_child(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "do-not-copy")
    monkeypatch.setenv("HF_TOKEN", "do-not-copy")
    process, calls = Process(), []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return process

    handle = remote.RemoteWorker(["ssh"], popen=popen)
    assert handle.poll() is None and not calls
    handle.start()
    opts = calls[0][1]
    assert "RUNPOD_API_KEY" not in opts["env"] and "HF_TOKEN" not in opts["env"]
    assert opts["shell"] is False and opts["stdout"] == subprocess.DEVNULL
    assert handle.poll() is None
    handle.kill()
    assert process.killed and process.waits == [1] and handle.poll() == -9
    with pytest.raises(RuntimeError):
        handle.start()


def test_real_local_child_is_reaped_without_network():
    handle = remote.RemoteWorker([sys._base_executable, "-c", "import time; time.sleep(60)"])
    try:
        handle.start()
        assert handle.poll() is None
    finally:
        handle.kill()
    assert handle.poll() is not None


@pytest.fixture
def execution(tmp_path, connection, monkeypatch):
    events = []
    budget = LeaseBudget(0, 1, 100, 2, 0, shutdown_margin_seconds=120)
    guard = BudgetGuard(budget, wall=lambda: 100, monotonic=lambda: 0)
    spec = {
        "run_id": "testrun123",
        "pod_id": "testpod123",
        "budget": asdict(budget),
        "export_root": "/workspace/export",
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")

    class Stopper:
        pod_id, run_id = "testpod123", "testrun123"

        def inspect(self):
            events.append("ownership")
            return {"status": "RUNNING"}

        def stop_verified(self, **kwargs):
            events.append("stop_verified")
            return {"verified": True}

    class Mirror:
        def __init__(self):
            self.spec = {
                "run_id": "testrun123",
                "source": {**connection, "remote_root": "/workspace/export"},
            }

        def finish(self, seconds):
            events.append("export")
            assert 0 < seconds <= 30
            return {"status": "verified"}

        def close(self):
            events.append("mirror_close")

    process = Process(0)
    original = remote.RemoteWorker

    def popen(*args, **kwargs):
        events.append("ssh_start")
        return process

    monkeypatch.setattr(remote, "RemoteWorker", lambda command: original(command, popen=popen))
    return SimpleNamespace(
        worker_class=original,
        events=events,
        spec=spec,
        path=path,
        process=process,
        kwargs={
            "spec_path": path,
            "remote_spec": "/workspace/spec.json",
            "remote_python": "/python",
            "connection": connection,
            "guard": guard,
            "stopper": Stopper(),
            "mirror": Mirror(),
        },
    )


def test_remote_completion_exports_then_verifies_shutdown(execution):
    c = execution
    result = remote.run_remote(**c.kwargs)
    assert c.events == ["ownership", "ssh_start", "export", "stop_verified"]
    assert result["reason"] == "completed" and result["shutdown"]["verified"]
    assert result["compute_spec_sha256"] == digest(c.spec)
    assert result["benchmark_fidelity_validated"] is False


@pytest.mark.parametrize("failure", ["lease", "run", "mirror", "missing", "spawn", "exit"])
def test_all_failures_reach_owned_shutdown(execution, monkeypatch, failure):
    c = execution
    if failure == "lease":
        c.spec["budget"]["session_cap_usd"] = 3
    elif failure == "run":
        c.spec["run_id"] = "different"
    elif failure == "mirror":
        c.kwargs["mirror"].spec["source"]["remote_root"] = "/wrong"
    elif failure == "spawn":

        def fail(*args):
            raise OSError("simulated SSH failure")

        monkeypatch.setattr(remote, "ssh_command", fail)
    elif failure == "exit":
        c.process.code = 255
    c.path.write_text(json.dumps(c.spec), encoding="utf-8")
    if failure == "missing":
        c.path.unlink()
    result = remote.run_remote(**c.kwargs)
    assert result["reason"] == ("worker_failed" if failure == "exit" else "supervisor_error")
    assert c.events[-2:] == ["mirror_close", "stop_verified"]
    assert "export" not in c.events
    if failure != "exit":
        assert "ssh_start" not in c.events


def test_expired_lease_never_starts_ssh_but_stops_owned_pod(execution):
    c = execution
    c.kwargs["guard"].wall = lambda: 100000
    result = remote.run_remote(**c.kwargs)
    assert result["shutdown"]["verified"] and "ssh_start" not in c.events


def test_supervisor_reaps_real_stalled_child_before_verified_stop(execution):
    c = execution
    # Run a local sleeping interpreter in place of SSH; no network/cloud call.
    handle = c.worker_class([sys._base_executable, "-c", "import time; time.sleep(60)"])
    result = supervise(
        handle,
        c.kwargs["guard"],
        c.kwargs["stopper"],
        progress=lambda: None,
        inactivity_seconds=0.05,
        poll_seconds=0.01,
    )
    assert result["reason"] == "inactivity" and result["shutdown"]["verified"]
    assert handle.process.poll() is not None and c.events[-1] == "stop_verified"


def test_export_failure_still_stops_owned_pod(execution):
    c = execution

    def fail(_seconds):
        raise OSError("disk full")

    c.kwargs["mirror"].finish = fail
    result = remote.run_remote(**c.kwargs)
    assert result["export"]["status"] == "failed" and result["shutdown"]["verified"]
    assert c.events[-2:] == ["mirror_close", "stop_verified"]


def test_wrong_remote_spec_hash_stops_before_loading_manifests(tmp_path, monkeypatch):
    path = tmp_path / "spec.json"
    path.write_text('{"unexpected":"different spec"}', encoding="utf-8")
    monkeypatch.setenv("RUNPOD_POD_ID", "testpod123")
    monkeypatch.setenv("WSBENCH_RUN_ID", "testrun123")
    monkeypatch.setattr(sys, "argv", ["worker", "--spec", str(path), "--spec-sha256", "a" * 64])
    stopped = []
    monkeypatch.setattr(worker, "request_shutdown", lambda _: stopped.append(True))
    with pytest.raises(ValueError, match="digest differs"):
        worker.main()
    assert stopped == [True]

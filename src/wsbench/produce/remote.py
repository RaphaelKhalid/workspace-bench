"""Supervise an SSH compute command on an already running owned pod; never rent a pod."""

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from wsbench.cell_manifest import digest

from .deadline import read_metadata
from .watchdog import supervise


def remote_path(value):
    path = PurePosixPath(value)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or str(path) != value
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("remote paths must be normalized absolute POSIX paths")
    return value


def ssh_command(connection, remote_python, remote_spec, spec_sha256):
    """Use explicit identity and known hosts, with no user SSH configuration or forwarding."""
    import paramiko

    if set(connection) != {"host", "port", "username", "key_file", "known_hosts"}:
        raise ValueError("invalid SSH connection fields")
    host, port, username = (connection[k] for k in ("host", "port", "username"))
    if not isinstance(host, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.:-]*", host):
        raise ValueError("invalid SSH host")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid SSH port")
    if not isinstance(username, str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        raise ValueError("invalid SSH username")
    if not isinstance(spec_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", spec_sha256):
        raise ValueError("invalid compute specification digest")
    key = Path(connection["key_file"]).resolve(strict=True)
    known = Path(connection["known_hosts"]).resolve(strict=True)
    if not key.is_file() or not known.is_file():
        raise ValueError("SSH identity and known hosts must be files")
    # OpenSSH parses the value of -o as configuration syntax, even without a shell.
    known_value = known.as_posix()
    if any(c in known_value for c in ('"', "\n", "\r", "%", "$")):
        raise ValueError("known-hosts path contains SSH expansion syntax")
    keys = paramiko.HostKeys(str(known))
    if keys.lookup(host if port == 22 else f"[{host}]:{port}") is None:
        raise ValueError("target SSH host key is not pinned")
    executable = shutil.which("ssh")
    if executable is None:
        raise ValueError("OpenSSH client unavailable")
    command = "exec " + shlex.join(
        [
            remote_path(remote_python),
            "-m",
            "wsbench.produce.worker",
            "--spec",
            remote_path(remote_spec),
            "--spec-sha256",
            spec_sha256,
        ]
    )
    options = [
        "BatchMode=yes",
        "IdentitiesOnly=yes",
        "IdentityAgent=none",
        "StrictHostKeyChecking=yes",
        f'UserKnownHostsFile="{known_value}"',
        "GlobalKnownHostsFile=none",
        "VerifyHostKeyDNS=no",
        "UpdateHostKeys=no",
        "ClearAllForwardings=yes",
        "ForwardAgent=no",
        "ConnectionAttempts=1",
        "ConnectTimeout=10",
        "ServerAliveInterval=5",
        "ServerAliveCountMax=2",
    ]
    return [
        executable,
        "-F",
        "none",
        "-T",
        *[part for value in options for part in ("-o", value)],
        "-i",
        str(key),
        "-p",
        str(port),
        "-l",
        username,
        "--",
        host,
        command,
    ]


class RemoteWorker:
    """Only owns the local SSH child; killing it does not prove remote compute stopped."""

    def __init__(self, command, *, popen=subprocess.Popen):
        self.command, self.popen = command, popen
        self.process = None
        self.started = self.closed = False

    def start(self):
        if self.started or self.closed:
            raise RuntimeError("remote worker cannot be started twice or after cleanup")
        self.started = True
        command = self.command() if callable(self.command) else self.command
        # SSH receives no API credentials and does not forward environment variables.
        environment = {
            k: v for k, v in os.environ.items() if not k.upper().endswith(("_API_KEY", "_TOKEN"))
        }
        self.process = self.popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def poll(self):
        if self.process is None:
            return 255 if self.started or self.closed else None
        return self.process.poll()

    def kill(self):
        self.closed = True
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=1)


def run_remote(
    *,
    spec_path,
    remote_spec,
    remote_python,
    connection,
    guard,
    stopper,
    mirror,
    inactivity_seconds=300,
    poll_seconds=5,
):
    """Bind local lease/spec and export connection before entering owned-pod supervision."""
    binding = {}

    def prepare():
        spec = read_metadata(spec_path)
        if (spec.get("pod_id"), spec.get("run_id")) != (stopper.pod_id, stopper.run_id):
            raise ValueError("remote specification pod/run differs from supervisor")
        if spec.get("budget") != asdict(guard.budget):
            raise ValueError("remote specification lease differs from supervisor")
        source = mirror.spec["source"]
        if mirror.spec["run_id"] != stopper.run_id or source != {
            **connection,
            "remote_root": spec.get("export_root"),
        }:
            raise ValueError("export mirror connection or run differs from compute")
        binding["compute_spec_sha256"] = digest(spec)
        return ssh_command(connection, remote_python, remote_spec, digest(spec))

    worker = RemoteWorker(prepare)
    result = supervise(
        worker,
        guard,
        stopper,
        mirror=mirror,
        inactivity_seconds=inactivity_seconds,
        poll_seconds=poll_seconds,
    )
    result.update(binding)
    result["benchmark_fidelity_validated"] = False
    return result

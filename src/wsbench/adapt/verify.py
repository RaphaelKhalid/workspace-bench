"""Run an authored Python program and record what it really does, in the bank's ``verified``
format (``exec: exit 0; stdout = '6'``). Isolated interpreter, empty temp dir, CPU and memory
caps, no stdin; run twice so nondeterministic programs are caught."""

import os
import resource
import subprocess
import sys
import tempfile

TIMEOUT_S = 5


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_S, TIMEOUT_S))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))


def _run(code: str) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        p = subprocess.run(
            [sys.executable, "-I", "-c", code],
            cwd=tmp,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0"},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S + 1,
            preexec_fn=_limits,
        )
    return p.returncode, p.stdout, p.stderr


def verify_python(code: str) -> str | None:
    """The ``verified`` string, or None if the program hangs or prints differently twice."""
    try:
        runs = [_run(code), _run(code)]
    except subprocess.TimeoutExpired:
        return None
    if runs[0] != runs[1]:
        return None
    rc, out, err = runs[0]
    if rc < 0:  # killed by a signal: the CPU or memory cap, i.e. a hang
        return None
    shown = " | ".join(out.rstrip("\n").split("\n"))  # the bank joins output lines this way
    if rc == 0:
        return f"exec: exit 0; stdout = '{shown}'"
    last = (err.strip().splitlines() or [""])[-1]
    return f"exec: exit {rc}; stdout = '{shown}'; last = '{last}'"

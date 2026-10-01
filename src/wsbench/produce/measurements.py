"""Append-only attempt measurements; elapsed time is evidence, never rental authorization."""

import json
import math
import os
import re
import time
import uuid
from pathlib import Path

from .storage import atomic_writer


def measurement_path(name):
    return bool(re.fullmatch(r"measurements/[0-9a-f]{32}\.jsonl(?:\.recovered-tail\.bin)?", name))


def recover_history(directory):
    """Called under the compute lock; retain torn bytes and reject malformed committed rows."""
    paths = []
    for path in sorted(Path(directory).glob("*.jsonl")):
        if path.is_symlink() or not measurement_path(f"measurements/{path.name}"):
            raise ValueError("invalid measurement history path")
        data = path.read_bytes()
        boundary = data.rfind(b"\n") + 1
        committed, tail = data[:boundary], data[boundary:]
        elapsed, terminal = 0, False
        for index, line in enumerate(committed.splitlines()):
            row = json.loads(line)
            seconds = row.get("attempt_elapsed_seconds")
            if (
                set(row)
                != {"schema_version", "sequence", "event", "at", "attempt_elapsed_seconds", "data"}
                or row["schema_version"] != 1
                or type(row["sequence"]) is not int
                or row["sequence"] != index
                or not isinstance(row["data"], dict)
                or not isinstance(row["event"], str)
                or terminal
                or (index == 0 and row["event"] != "attempt_started")
                or type(seconds) not in {int, float}
                or not math.isfinite(seconds)
                or seconds < elapsed
            ):
                raise ValueError("invalid committed measurement history")
            elapsed = seconds
            terminal = row["event"] in {"attempt_complete", "attempt_failed"}
        if tail:
            saved = path.with_suffix(".jsonl.recovered-tail.bin")
            if saved.exists() and saved.read_bytes() != tail:
                raise ValueError("different measurement recovery evidence already exists")
            if not saved.exists():
                with atomic_writer(saved) as handle:
                    handle.write(tail)
            with path.open("r+b") as handle:
                handle.truncate(boundary)
                handle.flush()
                os.fsync(handle.fileno())
        paths.append(path)
        saved = path.with_suffix(".jsonl.recovered-tail.bin")
        if saved.exists():
            paths.append(saved)
    return paths


class MeasurementLog:
    def __init__(self, root, publisher, binding):
        self.path = Path(root) / "measurements" / f"{uuid.uuid4().hex}.jsonl"
        self.publisher, self.binding = publisher, binding
        self.stream = None
        self.started = time.monotonic()
        self.sequence = 0
        self.terminal = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("xb")
        try:
            self.record("attempt_started", self.binding)
        except BaseException:
            self.stream.close()
            raise
        return self

    def record(self, event, data):
        if self.terminal:
            raise ValueError("measurement attempt is already terminal")
        row = {
            "schema_version": 1,
            "sequence": self.sequence,
            "event": event,
            "at": time.time(),
            "attempt_elapsed_seconds": time.monotonic() - self.started,
            "data": data,
        }
        encoded = (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode()
        self.stream.write(encoded)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.sequence += 1
        self.publisher.update([self.path])

    def finish(self, status, data):
        self.record(status, data)
        self.terminal = True
        self.publisher.update([], force=True)

    def __exit__(self, exc_type, exc, tb):
        try:
            if not self.terminal:
                self.finish(
                    "attempt_failed", {"error_type": exc_type.__name__ if exc_type else None}
                )
        finally:
            self.stream.close()

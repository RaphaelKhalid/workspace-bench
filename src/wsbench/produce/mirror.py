"""Bounded export pulls in an owned subprocess; the parent never performs network transfer."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from wsbench.cell_manifest import digest

from .budget import nonnegative
from .export import SHA, contained, receive_snapshot, validate_identity, validate_snapshot
from .storage import atomic_writer
from .transfer import SFTPSource


class MirrorError(RuntimeError):
    pass


def data_entries(snapshot):
    return [r for r in snapshot["files"] if r["path"].endswith((".npz", ".jsonl")) and r["size"]]


def progress_identity(snapshot):
    # Reports, manifests and empty files cannot reset an inactivity deadline.
    return digest(sorted(data_entries(snapshot), key=lambda r: r["path"]))


def require_extension(previous, current, destination, check):
    """Verify source history locally, including append-only readout prefixes."""
    new = {r["path"]: r for r in current["files"]}
    for old in previous["files"]:
        check()
        row = new.get(old["path"])
        if row is None:
            raise ValueError("export snapshot dropped an earlier file")
        if row == old:
            continue
        if old["path"].endswith(".jsonl"):
            if row["size"] < old["size"]:
                raise ValueError("readout export shrank")
            hashed, remaining = hashlib.sha256(), old["size"]
            with contained(destination, f"objects/{row['sha256']}").open("rb") as stream:
                while remaining:
                    check()
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("readout prefix truncated")
                    hashed.update(chunk)
                    remaining -= len(chunk)
            if hashed.hexdigest() != old["sha256"]:
                raise ValueError("readout export rewrote an earlier prefix")
        elif old["path"] not in {"readers-run.json", "readouts/readers-run.json"}:
            raise ValueError("export changed an immutable artifact")


def pull_once(spec, *, source_factory=SFTPSource):
    destination = Path(spec["destination"])
    run_id, context = spec["run_id"], spec["context"]
    validate_identity(run_id, context)
    previous = None
    if spec.get("previous_snapshot") is not None:
        if not isinstance(spec["previous_snapshot"], str) or not SHA.fullmatch(
            spec["previous_snapshot"]
        ):
            raise ValueError("invalid previous snapshot hash")
        previous = json.loads(
            contained(destination, f"snapshots/{spec['previous_snapshot']}.json").read_text()
        )
        validate_snapshot(previous, run_id=run_id, context=context)
        if previous["sha256"] != spec["previous_snapshot"]:
            raise ValueError("previous snapshot identity differs")
    with source_factory(**spec["source"]) as source:
        try:
            sha = source.latest(run_id)
        except FileNotFoundError:
            return {"status": "waiting"}
        snapshot = source.snapshot(sha)
        receipt = receive_snapshot(
            snapshot,
            destination,
            source.open_object,
            run_id=run_id,
            context=context,
            check=source.check,
        )
        if previous is not None:
            require_extension(previous, snapshot, destination, source.check)
        source.check()
    return {
        "status": "verified",
        "snapshot_sha256": sha,
        "progress_identity": progress_identity(snapshot),
        "data_files": len(data_entries(snapshot)),
        "data_bytes": sum(r["size"] for r in data_entries(snapshot)),
        "receipt": receipt,
        "benchmark_coverage_validated": False,
    }


def write_json(path, data):
    with atomic_writer(path) as stream:
        stream.write((json.dumps(data, sort_keys=True) + "\n").encode())


class ExportMirror:
    """Nonblocking periodic pulls, with a bounded final pull before pod shutdown."""

    def __init__(
        self,
        *,
        source_options,
        destination,
        journal,
        run_id,
        context,
        interval_seconds=30,
        attempt_seconds=30,
        monotonic=time.monotonic,
        wall=time.time,
        sleep=time.sleep,
        popen=subprocess.Popen,
    ):
        validate_identity(run_id, context)
        for name, value in (
            ("interval_seconds", interval_seconds),
            ("attempt_seconds", attempt_seconds),
        ):
            nonnegative(name, value, positive=True)
            if value > 60:
                raise ValueError("mirror intervals and attempts must be at most 60 seconds")
        if "deadline_epoch" in source_options:
            raise ValueError("mirror owns each transfer deadline")
        self.spec = {
            "source": dict(source_options),
            "destination": str(Path(destination).resolve()),
            "run_id": run_id,
            "context": context,
        }
        self.journal = Path(journal).resolve()
        self.journal.mkdir(parents=True, exist_ok=True)
        self.interval, self.attempt = interval_seconds, attempt_seconds
        self.monotonic, self.wall, self.sleep, self.popen = monotonic, wall, sleep, popen
        self.process = None
        self.next_pull = monotonic()
        self.previous = self.progress = self.last = None
        self.closed = False
        self.accepted_path = contained(self.journal, "accepted.json")
        if self.accepted_path.exists():
            accepted = self._metadata(self.accepted_path)
            if accepted.get("context") != context or accepted.get("run_id") != run_id:
                raise MirrorError("accepted export journal belongs to another run or manifest")
            self._accept(accepted["result"])

    @staticmethod
    def _metadata(path):
        if path.stat().st_size > 16 * 1024:
            raise MirrorError("export metadata exceeds bound")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise MirrorError("invalid export metadata object")
        return data

    def _accept(self, result):
        receipt = result.get("receipt")
        if (
            result.get("status") != "verified"
            or not isinstance(receipt, dict)
            or receipt.get("run_id") != self.spec["run_id"]
            or receipt.get("snapshot_sha256") != result.get("snapshot_sha256")
            or receipt.get("verified") is not True
            or not SHA.fullmatch(str(result.get("progress_identity", "")))
            or not SHA.fullmatch(str(result.get("snapshot_sha256", "")))
        ):
            raise MirrorError("export subprocess receipt mismatch")
        self.previous, self.progress = result["snapshot_sha256"], result["progress_identity"]
        self.last = result

    def _start(self, seconds):
        token = uuid.uuid4().hex
        spec_path = contained(self.journal, f"{token}.spec.json")
        self.result_path = contained(self.journal, f"{token}.result.json")
        spec = {
            **self.spec,
            "previous_snapshot": self.previous,
            "source": {**self.spec["source"], "deadline_epoch": self.wall() + seconds},
        }
        write_json(spec_path, spec)
        self.end = self.monotonic() + seconds
        self.process = self.popen(
            [
                sys.executable,
                "-m",
                "wsbench.produce.mirror",
                "--spec",
                str(spec_path),
                "--result",
                str(self.result_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def _kill(self):
        process = self.process
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=1)
            self.process = None

    def tick(self):
        if self.closed:
            raise MirrorError("mirror is closed")
        now = self.monotonic()
        if self.process is not None:
            code = self.process.poll()
            if code is None and now >= self.end:
                self._kill()
                raise MirrorError("export subprocess exceeded its deadline")
            if code is None:
                return self.progress
            self._kill()
            if code != 0:
                raise MirrorError("export subprocess failed; inspect its result journal")
            result = self._metadata(self.result_path)
            if result.get("status") == "verified":
                self._accept(result)
                write_json(
                    self.accepted_path,
                    {
                        "run_id": self.spec["run_id"],
                        "context": self.spec["context"],
                        "result": result,
                    },
                )
            elif result.get("status") != "waiting":
                raise MirrorError("invalid export subprocess status")
            self.last = result
            self.next_pull = now + self.interval
        if now >= self.next_pull:
            self._start(self.attempt)
        return self.progress

    def finish(self, seconds):
        """Pull a fresh snapshot after the worker stops, within a total cleanup allowance."""
        nonnegative("final export allowance", seconds)
        if seconds > 60:
            raise ValueError("final export allowance must be at most 60 seconds")
        deadline = self.monotonic() + seconds
        try:
            self._kill()
            remaining = deadline - self.monotonic()
            if remaining <= 1:
                return {"status": "not_attempted", "reason": "no_export_time_remaining"}
            self._start(remaining - 1)  # Reserve one second for reaping the owned helper.
            while self.process is not None:
                self.tick()
                if self.process is not None:
                    self.sleep(min(0.1, max(0, self.end - self.monotonic())))
            return self.last
        finally:
            self._kill()
            self.closed = True

    def close(self):
        self._kill()
        self.closed = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        result = pull_once(spec)
    except Exception as exc:
        write_json(args.result, {"status": "error", "error_type": type(exc).__name__})
        raise SystemExit(2) from None
    write_json(args.result, result)


if __name__ == "__main__":
    main()

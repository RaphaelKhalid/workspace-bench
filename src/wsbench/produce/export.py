"""Content-addressed, resumable export of explicit benchmark outputs with verified receipts."""

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path, PurePosixPath

from wsbench.cell_manifest import digest

from .measurements import measurement_path
from .reference import ARM_IDS
from .storage import atomic_writer, file_lock

SHA = re.compile(r"[0-9a-f]{64}")


def relative_output(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", name):
        raise ValueError("unsafe export path")
    parts = PurePosixPath(name).parts
    if not parts or any(p in {".", ".."} or p.startswith(".") for p in parts):
        raise ValueError("unsafe export path")
    devices = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if any(p.split(".")[0].upper() in devices or p.endswith(".") for p in parts):
        raise ValueError("unsafe Windows export path")
    if PurePosixPath(name).is_absolute() or str(PurePosixPath(name)) != name:
        raise ValueError("export paths must be normalized and relative")
    allowed = name in {"readers-run.json", "readouts/readers-run.json"}
    allowed |= measurement_path(name)
    if len(parts) == 2 and parts[0] == "captures":
        allowed |= parts[1] in {"manifest.json", "capture-run.json"}
        allowed |= parts[1].endswith(".npz") and SHA.fullmatch(parts[1][:-4]) is not None
    if parts[0] == "manifests" and name.endswith(".json"):
        allowed = True
    if len(parts) == 3 and parts[0] == "readouts" and parts[1] in ARM_IDS:
        allowed |= parts[2].endswith((".jsonl", ".jsonl.run.json", ".jsonl.recovered-tail.bin"))
    if not allowed:
        raise ValueError("path is outside the benchmark export allowlist")
    return parts


def contained(root, name):
    root = Path(root).resolve()
    target = root.joinpath(*PurePosixPath(name).parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError("export path escapes its root")
    current = root
    for part in PurePosixPath(name).parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise ValueError("export paths cannot contain links or junctions")
    return target


def verify_object(path, sha, size):
    if not path.is_file() or path.stat().st_size != size:
        raise ValueError("export object size mismatch")
    with path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != sha:
            raise ValueError("export object hash mismatch")


def copy_object(source, root, size, *, expected=None, check=lambda: None, jsonl=False):
    directory = contained(root, "objects")
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".incoming-", dir=directory)
    temp = Path(temporary)
    try:
        sha, remaining, last = hashlib.sha256(), size, b""
        with os.fdopen(fd, "wb") as output:
            while remaining:
                check()
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk or len(chunk) > remaining:
                    raise ValueError("truncated or oversized export object")
                output.write(chunk)
                sha.update(chunk)
                remaining -= len(chunk)
                last = chunk[-1:]
            if jsonl and size and last != b"\n":
                raise ValueError("readout export must end at a complete checkpoint line")
            if expected is not None and source.read(1):
                raise ValueError("oversized export object")
            output.flush()
            os.fsync(output.fileno())
        key = sha.hexdigest()
        if expected is not None and key != expected:
            raise ValueError("export object hash mismatch")
        target = contained(root, f"objects/{key}")
        if target.exists():
            verify_object(target, key, size)
        else:
            temp.replace(target)
        return key
    finally:
        temp.unlink(missing_ok=True)


def validate_identity(run_id, context):
    if not re.fullmatch(r"[a-z0-9-]{8,64}", run_id):
        raise ValueError("invalid export run ID")
    if (
        set(context) != {"capture_manifest_sha256", "reader_manifests"}
        or set(context["reader_manifests"]) != set(ARM_IDS)
        or any(
            not isinstance(s, str) or not SHA.fullmatch(s)
            for s in [context["capture_manifest_sha256"], *context["reader_manifests"].values()]
        )
    ):
        raise ValueError("export requires the capture and full reader manifest identities")


def validate_snapshot(snapshot, *, run_id, context):
    validate_identity(run_id, context)
    data = {k: v for k, v in snapshot.items() if k != "sha256"}
    if (
        set(data) != {"schema_version", "run_id", "context", "files"}
        or data["schema_version"] != 1
        or snapshot.get("sha256") != digest(data)
        or data["run_id"] != run_id
        or data["context"] != context
    ):
        raise ValueError("export snapshot identity/provenance mismatch")
    if not isinstance(data["files"], list) or not 1 <= len(data["files"]) <= 10000:
        raise ValueError("invalid export file count")
    seen = set()
    total = 0
    for row in data["files"]:
        if set(row) != {"path", "size", "sha256"}:
            raise ValueError("invalid export file entry")
        relative_output(row["path"])
        folded = row["path"].casefold()
        if folded in seen:
            raise ValueError("duplicate or case-colliding export path")
        seen.add(folded)
        if (
            type(row["size"]) is not int
            or row["size"] < 0
            or not isinstance(row["sha256"], str)
            or not SHA.fullmatch(row["sha256"])
        ):
            raise ValueError("invalid export object identity")
        total += row["size"]
    if total > 10 * 1024**3:
        raise ValueError("export exceeds the declared 10 GiB transfer bound")


def save_snapshot(root, snapshot):
    path = contained(root, f"snapshots/{snapshot['sha256']}.json")
    with atomic_writer(path) as handle:
        handle.write((json.dumps(snapshot, sort_keys=True) + "\n").encode())
    return path


def stage_snapshot(
    source_root, export_root, paths, *, run_id, context, check=lambda: None, previous=None
):
    """Called at a checkpoint barrier; JSONL entries export the committed prefix only."""
    rows = {}
    validate_identity(run_id, context)
    if previous is not None:
        validate_snapshot(previous, run_id=run_id, context=context)
        rows = {row["path"]: row for row in previous["files"]}
    paths = list(paths)
    if len({p.casefold() for p in paths}) != len(paths):
        raise ValueError("duplicate or case-colliding export path")
    for name in paths:
        relative_output(name)
    with file_lock(Path(export_root) / ".export.lock"):
        for name in sorted(paths):
            relative_output(name)
            path = contained(source_root, name)
            with path.open("rb") as source:
                size = os.fstat(source.fileno()).st_size
                sha = copy_object(
                    source, export_root, size, check=check, jsonl=name.endswith(".jsonl")
                )
            if old := rows.get(name):
                old_path = contained(export_root, f"objects/{old['sha256']}")
                verify_object(old_path, old["sha256"], old["size"])
                if name.endswith(".jsonl"):
                    new_path = contained(export_root, f"objects/{sha}")
                    with old_path.open("rb") as old_stream, new_path.open("rb") as current:
                        while chunk := old_stream.read(1024 * 1024):
                            if current.read(len(chunk)) != chunk:
                                raise ValueError("published readout prefix changed")
                elif not name.endswith("readers-run.json") and sha != old["sha256"]:
                    raise ValueError("published immutable artifact changed")
            rows[name] = {"path": name, "size": size, "sha256": sha}
        data = {
            "schema_version": 1,
            "run_id": run_id,
            "context": context,
            "files": [rows[name] for name in sorted(rows)],
        }
        snapshot = {**data, "sha256": digest(data)}
        validate_snapshot(snapshot, run_id=run_id, context=context)
        save_snapshot(export_root, snapshot)
    return snapshot


class SnapshotPublisher:
    """Publish changed checkpoint files only; carry immutable earlier entries forward."""

    def __init__(
        self,
        source_root,
        export_root,
        *,
        run_id,
        context,
        check=lambda: None,
        interval_seconds=30,
        monotonic=time.monotonic,
    ):
        validate_identity(run_id, context)
        if not 0 < interval_seconds <= 60:
            raise ValueError("export publication interval must be in (0, 60]")
        self.source, self.root = Path(source_root).resolve(), Path(export_root)
        self.run_id, self.context, self.check = run_id, context, check
        self.interval, self.monotonic = interval_seconds, monotonic
        self.last, self.pending, self.previous = monotonic(), set(), None
        latest = contained(self.root, "latest.json")
        if latest.exists():
            pointer = json.loads(latest.read_text(encoding="utf-8"))
            if not SHA.fullmatch(pointer.get("sha256", "")):
                raise ValueError("invalid export pointer")
            path = contained(self.root, f"snapshots/{pointer['sha256']}.json")
            self.previous = json.loads(path.read_text(encoding="utf-8"))
            validate_snapshot(self.previous, run_id=run_id, context=context)

    def update(self, paths, *, force=False):
        for path in paths:
            relative = Path(path).resolve().relative_to(self.source).as_posix()
            relative_output(relative)
            self.pending.add(relative)
        if not self.pending or (not force and self.monotonic() - self.last < self.interval):
            return None
        snapshot = stage_snapshot(
            self.source,
            self.root,
            self.pending,
            run_id=self.run_id,
            context=self.context,
            check=self.check,
            previous=self.previous,
        )
        with atomic_writer(contained(self.root, "latest.json")) as handle:
            handle.write(
                (json.dumps({"sha256": snapshot["sha256"], "run_id": self.run_id}) + "\n").encode()
            )
        self.previous, self.pending, self.last = snapshot, set(), self.monotonic()
        return snapshot


def receive_snapshot(snapshot, destination, open_remote, *, run_id, context, check=lambda: None):
    """A receipt appears only after every object is locally verified; valid objects resume."""
    validate_snapshot(snapshot, run_id=run_id, context=context)
    transferred, reused = 0, 0
    with file_lock(Path(destination) / ".export.lock"):
        for row in snapshot["files"]:
            check()
            path = contained(destination, f"objects/{row['sha256']}")
            if path.exists():
                verify_object(path, row["sha256"], row["size"])
                reused += 1
                continue
            with open_remote(row["sha256"]) as source:
                copy_object(source, destination, row["size"], expected=row["sha256"], check=check)
            transferred += row["size"]
        save_snapshot(destination, snapshot)
        receipt = {
            "snapshot_sha256": snapshot["sha256"],
            "run_id": run_id,
            "verified": True,
            "benchmark_coverage_validated": False,
            "files": len(snapshot["files"]),
            "transferred_bytes": transferred,
            "reused_objects": reused,
        }
        with atomic_writer(contained(destination, f"receipts/{snapshot['sha256']}.json")) as handle:
            handle.write((json.dumps(receipt, sort_keys=True) + "\n").encode())
    return receipt


def restore_snapshot(snapshot, cache, destination, *, run_id, context):
    """Materialize verified objects into a new output tree; never overwrite different data."""
    validate_snapshot(snapshot, run_id=run_id, context=context)
    with file_lock(Path(cache) / ".export.lock"), file_lock(Path(destination) / ".restore.lock"):
        receipt_path = contained(destination, "export-receipt.json")
        if (
            receipt_path.exists()
            and json.loads(receipt_path.read_text())["snapshot_sha256"] != snapshot["sha256"]
        ):
            raise ValueError("restore a different snapshot into a new output tree")
        for row in snapshot["files"]:
            verify_object(contained(cache, f"objects/{row['sha256']}"), row["sha256"], row["size"])
            target = contained(destination, row["path"])
            if target.exists():
                verify_object(target, row["sha256"], row["size"])
        for row in snapshot["files"]:
            source = contained(cache, f"objects/{row['sha256']}")
            verify_object(source, row["sha256"], row["size"])
            target = contained(destination, row["path"])
            if target.exists():
                verify_object(target, row["sha256"], row["size"])
                continue
            with source.open("rb") as reader, atomic_writer(target) as writer:
                sha = hashlib.sha256()
                while chunk := reader.read(1024 * 1024):
                    writer.write(chunk)
                    sha.update(chunk)
                if sha.hexdigest() != row["sha256"]:
                    raise ValueError("export object changed during restore")
        with atomic_writer(contained(destination, "export-receipt.json")) as handle:
            handle.write(
                (
                    json.dumps(
                        {"snapshot_sha256": snapshot["sha256"], "run_id": run_id, "restored": True}
                    )
                    + "\n"
                ).encode()
            )

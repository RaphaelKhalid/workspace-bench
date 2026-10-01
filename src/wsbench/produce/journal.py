"""Single-writer, manifest-bound readouts with cell-level resume and torn-tail recovery."""

import json
import os
from pathlib import Path

from wsbench.readouts import _parse_row


class ReadoutJournal:
    def __init__(self, path: Path, *, binding: dict, expected: set[tuple[str, int, int]]):
        self.path = path
        self.binding = binding
        self.expected = expected
        self.present: set[tuple[str, int, int]] = set()
        self._lock = None
        self._writer = None
        self._kind = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                if self._lock.tell() == 0:
                    self._lock.write(b"0")
                    self._lock.flush()
                self._lock.seek(0)
                msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._prepare()
            self._writer = self.path.open("ab")
            return self
        except BaseException:
            self._lock.close()
            raise

    def _prepare(self):
        sidecar = self.path.with_suffix(self.path.suffix + ".run.json")
        if sidecar.exists():
            if json.loads(sidecar.read_text(encoding="utf-8")) != self.binding:
                raise ValueError("readout manifest/reader configuration changed; use a new output")
        else:
            if self.path.exists() and self.path.stat().st_size:
                raise ValueError("existing readouts have no provenance sidecar")
            temp = sidecar.with_suffix(".tmp")
            temp.write_text(json.dumps(self.binding, sort_keys=True), encoding="utf-8")
            temp.replace(sidecar)
        if not self.path.exists():
            return
        data = self.path.read_bytes()
        offset = 0
        lines = data.splitlines(keepends=True)
        for index, line in enumerate(lines):
            try:
                row = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                if index != len(lines) - 1 or line.endswith(b"\n"):
                    raise ValueError("malformed complete readout row") from None
                # Preserve torn bytes before truncating only the unfinished final row.
                tail = self.path.with_suffix(self.path.suffix + ".recovered-tail.bin")
                with tail.open("ab") as fh:
                    fh.write(line + b"\n")
                with self.path.open("r+b") as fh:
                    fh.truncate(offset)
                break
            self._validate(row)
            offset += len(line)
        else:
            if data and not data.endswith(b"\n"):
                with self.path.open("ab") as fh:
                    fh.write(b"\n")

    def _validate(self, row: dict) -> tuple[str, int, int]:
        cell = _parse_row(row)
        if cell is None:
            raise ValueError("invalid readout row")
        if self._kind is not None and cell.kind != self._kind:
            raise ValueError("mixed readout kinds")
        self._kind = cell.kind
        key = (cell.id, cell.layer, cell.pos)
        if key not in self.expected:
            raise ValueError(f"readout outside manifest: {key}")
        if key in self.present:
            raise ValueError(f"duplicate readout: {key}")
        self.present.add(key)
        return key

    def append(self, row: dict) -> None:
        self._validate(row)
        self._writer.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
        self._writer.flush()

    def checkpoint(self) -> None:
        self._writer.flush()
        os.fsync(self._writer.fileno())

    def __exit__(self, *_exc):
        try:
            if self._writer is not None:
                self.checkpoint()
        finally:
            if self._writer is not None:
                self._writer.close()
            if self._lock is not None:
                self._lock.close()

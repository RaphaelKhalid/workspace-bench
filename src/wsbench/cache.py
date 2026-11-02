"""Append-only JSONL verdict cache: rows are never rewritten, a changed fingerprint appends."""

import contextlib
import fcntl
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Self

_RESERVED = ("key", "fp", "ts")


def fingerprint(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class Cache:
    """Rows keyed by ``(key, fp)``; a row is *failed* iff ``row.get("result") is None``."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._rows: dict[str, list[dict[str, Any]]] = {}
        self._n = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        torn = False
        if self.path.exists() and self.path.stat().st_size:
            data = self.path.read_bytes()
            torn = not data.endswith(b"\n")
            for line in data.decode("utf-8", "replace").split("\n"):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and isinstance(row.get("key"), str):
                    self._rows.setdefault(row["key"], []).append(row)
                    self._n += 1
        self._fh = self.path.open("a", encoding="utf-8")
        if torn:  # terminate a line torn by an interrupted write
            self._fh.write("\n")
            self._fh.flush()

    def get(self, key: str, fp: str, *, include_failed: bool = False) -> dict[str, Any] | None:
        for row in reversed(self._rows.get(key, [])):
            if row.get("fp") != fp:
                continue
            if include_failed or row.get("result") is not None:
                return row
        return None

    def put(self, key: str, fp: str, payload: dict[str, Any]) -> None:
        clash = [k for k in _RESERVED if k in payload]
        if clash:
            raise ValueError(f"payload uses reserved cache keys: {clash}")
        row = {"key": key, "fp": fp, "ts": time.time(), **payload}
        self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._fh.flush()
        self._rows.setdefault(key, []).append(row)
        self._n += 1

    def __len__(self) -> int:
        return self._n

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._fh.close()


class SharedLog:
    """An append-only JSONL cache SEVERAL processes read and write (the per-layer digest store,
    ``digest.SharedDigests``). Unlike :class:`Cache` it holds no open handle: every ``put`` is one
    ``O_APPEND`` write of a whole line (under ``flock`` where the filesystem supports it), and a
    ``get`` first reads whatever other processes appended since the last read when it misses in
    memory or the last read is older than ``max_age`` seconds (so a failed row another process
    wrote after a success, invalidating it, is seen within ``max_age``). A miss costs one stat
    (and a read of only the appended bytes). A torn or interleaved line fails to parse
    and is skipped (a miss, never a wrong row: a row is served only on an exact ``(key, fp)``
    match)."""

    max_age = 10.0

    def __init__(self, path: Path):
        self.path = Path(path)
        self._rows: dict[str, list[dict[str, Any]]] = {}
        self._off = 0
        self._tail = b""
        self._read_at = float("-inf")
        self._ino = -1

    def _lookup(self, key: str, fp: str, include_failed: bool) -> dict[str, Any] | None:
        for row in reversed(self._rows.get(key, [])):
            if row.get("fp") == fp and (include_failed or row.get("result") is not None):
                return row
        return None

    def _refresh(self) -> None:
        self._read_at = time.monotonic()
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return
        size = st.st_size
        if size < self._off or st.st_ino != self._ino:  # replaced or truncated: start over
            self._rows, self._off, self._tail = {}, 0, b""
            self._ino = st.st_ino
        if size == self._off:
            return
        with self.path.open("rb") as fh:
            fh.seek(self._off)
            data = fh.read(size - self._off)
        self._off += len(data)
        lines = (self._tail + data).split(b"\n")
        self._tail = lines.pop()  # an incomplete last line waits for the next read
        for raw in lines:
            if not raw.strip():
                continue
            try:
                row = json.loads(raw.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and isinstance(row.get("key"), str):
                self._rows.setdefault(row["key"], []).append(row)

    def get(self, key: str, fp: str, *, include_failed: bool = False) -> dict[str, Any] | None:
        row = self._lookup(key, fp, include_failed)
        if row is None or time.monotonic() - self._read_at > self.max_age:
            self._refresh()
            row = self._lookup(key, fp, include_failed)
        return row

    def put(self, key: str, fp: str, payload: dict[str, Any]) -> None:
        clash = [k for k in _RESERVED if k in payload]
        if clash:
            raise ValueError(f"payload uses reserved cache keys: {clash}")
        row = {"key": key, "fp": fp, "ts": time.time(), **payload}
        # the leading newline ends a line another writer tore, so this row always parses
        data = ("\n" + json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            with contextlib.suppress(OSError):  # a filesystem without flock: O_APPEND alone
                fcntl.flock(fd, fcntl.LOCK_EX)
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view) :]
        finally:
            os.close(fd)  # releases the lock
        self._rows.setdefault(key, []).append(row)

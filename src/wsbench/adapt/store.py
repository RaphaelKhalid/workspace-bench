"""The on-disk layout of an adapted model, ``adapted/<model>/`` (SKILL.md §Layout)."""

import fcntl
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from wsbench.banks import load_bank as load_wrapped
from wsbench.registry import REPO_ROOT


def model_dir(model: str, root: Path = REPO_ROOT) -> Path:
    return root / "adapted" / model


def item_id(item: dict) -> str:
    return str(item.get("id") or item.get("name"))


def original_bank(family: str) -> tuple[dict[str, Any], list[dict]]:
    """The frozen bank, header and items, whether wrapped or a plain list."""
    from wsbench.registry import frozen_bank_path

    path = frozen_bank_path(family)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return {}, raw
    if raw.get("items") and "name" not in raw["items"][0]:
        return {k: v for k, v in raw.items() if k != "items"}, raw["items"]
    return load_wrapped(path)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    # split on "\n" only: str.splitlines() also breaks on U+2028 / U+0085 etc., which a subject's
    # answer can contain raw inside a JSON string (ensure_ascii=False)
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()
    ]


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def gate_path(model: str, family: str) -> Path:
    return model_dir(model) / "gate" / f"{family}.jsonl"


def cand_path(model: str, family: str) -> Path:
    return model_dir(model) / "cand" / f"{family}.jsonl"


def gated(model: str, family: str) -> dict[str, dict]:
    """Every gated candidate, last record per id (a re-gate appends)."""
    return {str(r["id"]): r for r in _read_jsonl(gate_path(model, family))}


def record_gates(model: str, family: str, rows: list[dict]) -> None:
    _append_jsonl(gate_path(model, family), rows)


def pending(model: str, family: str) -> list[dict]:
    """Candidates written but not yet gated."""
    done = gated(model, family)
    return [c for c in _read_jsonl(cand_path(model, family)) if item_id(c) not in done]


def add_candidates(model: str, family: str, items: list[dict]) -> int:
    """Append candidates whose id is new to both the candidate file and the gate log."""
    seen = set(gated(model, family)) | {item_id(c) for c in _read_jsonl(cand_path(model, family))}
    fresh = [it for it in items if item_id(it) not in seen]
    _append_jsonl(cand_path(model, family), fresh)
    return len(fresh)


def write_json(path: Path, obj: Any) -> None:
    """Atomic: write a temp file beside it, then rename (a crash never leaves half a bank)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


@contextmanager
def report_lock(model: str) -> Iterator[None]:
    """Serialise report.json read-modify-writes across processes (steps run in parallel)."""
    lock = model_dir(model) / ".report.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def code_stamp() -> dict[str, str]:
    """Which pipeline wrote a report: the git HEAD, whether the tree was dirty, and a hash of the
    adapt package itself (uncommitted edits change it), so a stale bank is detectable."""
    import hashlib
    import subprocess

    h = hashlib.sha256()
    for f in sorted(Path(__file__).parent.glob("*.py")):
        h.update(f.name.encode() + f.read_bytes())
    try:

        def sh(*a: str) -> str:
            return subprocess.run(["git", "-C", str(REPO_ROOT), *a], capture_output=True,
                                  text=True, timeout=10).stdout.strip()  # fmt: skip

        git, dirty = sh("rev-parse", "--short", "HEAD"), sh("status", "--porcelain", "src")
    except (OSError, subprocess.SubprocessError):
        git, dirty = "", ""
    return {"git": git + ("+dirty" if dirty else ""), "adapt_sha256": h.hexdigest()[:16]}


def update_report(model: str, mutate: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    """Locked read -> ``mutate(report)`` in place -> atomic write (stamped with ``code_stamp``).
    Returns the new report."""
    with report_lock(model):
        report = read_report(model)
        mutate(report)
        report["code"] = code_stamp()
        write_json(model_dir(model) / "report.json", report)
        return report


def read_report(model: str) -> dict[str, Any]:
    path = model_dir(model) / "report.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

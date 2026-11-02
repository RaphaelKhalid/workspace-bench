"""One-off data change (plan 0033 M1; Camila 2026-10-30: "Drop the arithmetic items").

Writes the frozen ``evals/typo_mt/items_v2.json`` (v1 minus ``subfamily == "arith"``, items
byte identical in v1 order, ``items.json`` untouched) and rewrites IN PLACE every
``adapted/*/typo_mt.json`` that holds arith items (under ``WSB_BANK_ROOT`` the bank path has no
version in its file name). Each output header records the dropped ids and the source sha256.
Idempotent: a bank already at ``version: 2`` is left as is.

    uv run python scripts/typo_mt_drop_arith.py [--check]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
V1 = REPO / "evals/typo_mt/items.json"
V2 = REPO / "evals/typo_mt/items_v2.json"
FROZEN = "2026-10-30"
WHY = "Camila 2026-10-30: drop the arithmetic items"
GATE_ARITH_CLAUSE = " (correct spelling / true result)"
GATE_READ_OLD = "plain prompt, final prompt token;"
GATE_READ_NEW = (
    "plain prompt, the misspelled word's tokens from the first misspelled character on"
    " (reads=lite: its final token);"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(d: dict[str, Any], like: str) -> str:
    """The banks' own serialisation (indent 1, raw UTF-8), trailing newline as in ``like``."""
    s = json.dumps(d, indent=1, ensure_ascii=False)
    return s + "\n" if like.endswith("\n") else s


def drop_arith(path: Path, *, derived_from: str) -> tuple[dict[str, Any], list[str]]:
    raw = path.read_text(encoding="utf-8")
    d = json.loads(raw)
    dropped = [it["name"] for it in d["items"] if it.get("subfamily") == "arith"]
    out: dict[str, Any] = {k: v for k, v in d.items() if k != "items"}
    out["version"] = 2
    out["frozen_v2"] = FROZEN
    out["derived_from"] = f"{derived_from} (sha256 {sha256(path)})"
    out["dropped"] = {"subfamily": "arith", "n": len(dropped), "why": WHY, "names": dropped}
    out["items"] = [it for it in d["items"] if it.get("subfamily") != "arith"]
    return out, dropped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    a = ap.parse_args(argv)
    report: list[str] = []
    v2, dropped = drop_arith(V1, derived_from="items.json")
    v2["frozen"] = FROZEN
    v2.pop("frozen_v2")
    v2["gate"] = (
        v2["gate"]
        .replace(GATE_ARITH_CLAUSE, " (correct spelling)")
        .replace(GATE_READ_OLD, GATE_READ_NEW)
    )
    report.append(f"{V2.relative_to(REPO)}: {len(v2['items'])} items, dropped {len(dropped)}")
    if not a.check:
        V2.write_text(dump(v2, V1.read_text(encoding="utf-8")), encoding="utf-8")
    for path in sorted(REPO.glob("adapted/*/typo_mt.json")):
        raw = path.read_text(encoding="utf-8")
        if json.loads(raw).get("version") == 2:
            report.append(f"{path.relative_to(REPO)}: already version 2")
            continue
        new, gone = drop_arith(path, derived_from=f"{path.name} before plan 0033")
        if not gone:
            report.append(f"{path.relative_to(REPO)}: 0 arith items, untouched")
            continue
        report.append(
            f"{path.relative_to(REPO)}: dropped {len(gone)} arith, {len(new['items'])} items left"
        )
        if not a.check:
            path.write_text(dump(new, raw), encoding="utf-8")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Move a renamed family's frozen ATI entry to its new key (plan 0034 O1).

    uv run --no-sync python scripts/ati_restamp_rename.py \\
        --old directed_modulation_obscure --new model_specific_directed_modulation

A rename is a key move, not a membership change: ``bank_sha`` hashes the plan rows, whose
``family`` field carries the key, so the fingerprint moves with the name. The script

1. recomputes the fingerprint under the OLD name and asserts it equals the stored ``bank_sha``
   (the bank and the full read plan are unchanged);
2. asserts the ids, the instrument and the gate are unchanged (the entry is copied as is);
3. writes the entry under the new key with the new-name fingerprint, recording the old key and
   fingerprint under ``renamed_from``.

No model call; the native regex instrument and the ids are untouched, so no re-gate."""

import argparse
import dataclasses
import hashlib
import json
import sys
from typing import Any

from wsbench import readplan, registry
from wsbench.baselines import text_inversion as ti


def fingerprint_as(family: str, name: str) -> str:
    """``ti.bank_fingerprint(family)`` with every plan row's ``family`` field set to ``name``."""
    bank = json.loads(registry.bank_path(family).read_text(encoding="utf-8"))
    items = {str(it.get("id", it.get("name"))): it for it in bank.get("items", [])}
    rows = sorted(
        (
            (str(r.id), ti._row_dict(dataclasses.replace(r, family=name)), items.get(str(r.id)))
            for r in readplan.plan(family)
            if ti.ati_scored(r)
        ),
        key=lambda x: x[0],
    )
    blob = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def restamp(frozen: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    if old not in frozen:
        raise SystemExit(f"no ATI entry under {old!r}")
    if new in frozen:
        raise SystemExit(f"an ATI entry already exists under {new!r}")
    entry = dict(frozen[old])
    was = fingerprint_as(new, old)
    if was != entry.get("bank_sha"):
        stored = str(entry.get("bank_sha"))[:12]
        raise SystemExit(
            f"{old}: bank_sha under the old name {was[:12]} != stored {stored}: the bank or "
            "plan changed; re-gate"
        )
    if entry.get("instrument") != registry.get(new).judge.prompt_version:
        raise SystemExit(f"{new}: the instrument changed; re-gate instead of restamping")
    entry["renamed_from"] = {"key": old, "bank_sha": entry["bank_sha"], "plan": "0034"}
    entry["bank_sha"] = ti.bank_fingerprint(new)
    return {(new if k == old else k): (entry if k == old else v) for k, v in frozen.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    a = ap.parse_args()
    registry.load_all()
    frozen = json.loads(ti.FROZEN.read_text(encoding="utf-8"))
    out = restamp(frozen, a.old, a.new)
    ti.FROZEN.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    e = out[a.new]
    before = e["renamed_from"]["bank_sha"][:12]
    print(
        f"moved {a.old} -> {a.new}: {len(e['ids'])} ids, bank_sha {before} -> {e['bank_sha'][:12]}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

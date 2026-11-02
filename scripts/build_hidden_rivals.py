"""Build basic_readout_mt's hidden-rival table (optrv-v3, review of PR #208 round 4b,
2026-11-01).

The option-rival check (``family.contested_verdict``) weighs every listed option in code: the
gold's best digest entry must lead every other option's best entry (a tie is contested). The
round-4 / 4b leakage redraws replaced distractors that the readouts themselves name as competing
answers (basic_readout_mt ``brh-ent-cur-ouguiya-subunit`` L20: "[4 samples] ... five dirhams make
one ouguiya's worth" ties the gold khoums line at 4; bank v2 listed "dirhams", v3 / v4 do not), so
the check lost them. Putting such a confuser back in the shown list re-opens the leak
(``evals/basic_readout_mt/r4c_dirhams_gate.json``: every candidate list with "dirhams" is found by
some guesser in >= 4 of 5 draws). Instead, the code also weighs these names WITHOUT showing them:
for each item, every distractor a bank of record before this PR listed for it (``items.json``,
``items_v2.json``: the curated same-kind lists, drawn before any readout was judged) that is not
in the current list, names neither the gold nor a shown option, and is not in the prompt. The
round-4 draft ``items_v3.json`` is not used (it mixed kinds: "soman" for a systematic name).

multihop_mt_v2 gets no table: its earlier lists name the chain's own unstated entities (v1 lists
"Samuel Beckett", the playwright the prompt describes, for the novelist he assisted; Cantor's
teacher Weierstrass for Cantor), which the readouts rightly discuss, so weighing them would
contest correct reads (measured: 2 of 2 mh2 flips were of that kind). They never enter a
prompt, so the leakage floors are unchanged.

Writes ``evals/<family>/hidden_rivals.json`` (a frozen gate table beside the bank, as
``exonyms.json``; the bank stays byte-identical). Run:
``python scripts/build_hidden_rivals.py [--check]``.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from wsbench import mc  # noqa: E402
from wsbench.multitoken.family import gate_name_forms  # noqa: E402

FAMILIES = ("basic_readout_mt",)
CURRENT = "items_v4.json"
EARLIER = ("items.json", "items_v2.json")


def _blocks(path: Path) -> dict[str, dict[str, Any]]:
    bank = json.loads(path.read_text(encoding="utf-8"))
    return {str(it["name"]): dict(it.get("mc") or {}) for it in bank["items"]}


def _overlaps(a: str, b: str) -> bool:
    fa, fb = mc.fold(a), mc.fold(b)
    return fa.strip() == fb.strip() or mc.form_in(fa, [b]) or mc.form_in(fb, [a])


def hidden_for(
    item: dict[str, Any], role: str, earlier: list[dict[str, dict[str, Any]]]
) -> list[str]:
    """The earlier banks' distractors for one unit that the current list lacks (see module doc)."""
    blk = item["mc"][role]
    shown = [str(blk["gold"]), *(str(d) for d in blk["distractors"])]
    # every unit's gold of the item with its name forms
    gold = [
        x
        for r, b in item["mc"].items()
        for x in [str(b["gold"]), *(f for fs in gate_name_forms(item, r).values() for f in fs)]
    ]
    prompt = mc.fold(str(item.get("prompt") or ""))
    out: list[str] = []
    for bank in earlier:
        old = (bank.get(str(item["name"])) or {}).get(role) or {}
        for d in old.get("distractors") or ():
            d = str(d)
            if mc.form_in(prompt, [d]) or any(_overlaps(d, x) for x in [*gold, *shown, *out]):
                continue
            out.append(d)
    return out


def build(family: str) -> dict[str, Any]:
    root = REPO / "evals" / family
    cur = json.loads((root / CURRENT).read_text(encoding="utf-8"))
    earlier = [_blocks(root / f) for f in EARLIER]
    items: dict[str, dict[str, list[str]]] = {}
    for it in cur["items"]:
        it = {**it, "id": it["name"]}
        roles = {r: hidden_for(it, r, earlier) for r in it.get("mc") or {}}
        roles = {r: v for r, v in roles.items() if v}
        if roles:
            items[str(it["name"])] = roles
    return {
        "family": family,
        "version": "optrv-v3",
        "bank": CURRENT,
        "from": list(EARLIER),
        "script": "scripts/build_hidden_rivals.py",
        "rule": (
            "per item and unit: every distractor a bank of record before PR #208 (items.json, "
            "items_v2.json) listed that the current list lacks, that names neither the gold nor "
            "a shown option and is not in the prompt; weighed by the code option-rival check "
            "(family.contested_verdict), never shown to the judge"
        ),
        "items": items,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    rc = 0
    for fam in FAMILIES:
        path = REPO / "evals" / fam / "hidden_rivals.json"
        text = json.dumps(build(fam), indent=1, ensure_ascii=False) + "\n"
        if a.check:
            if not path.exists() or path.read_text("utf-8") != text:
                print(f"stale: {path}", file=sys.stderr)
                rc = 1
            continue
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}")
    return rc


if __name__ == "__main__":
    sys.exit(main())

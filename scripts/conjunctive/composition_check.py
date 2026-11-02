"""Lexical composition diagnostic for conjunctive_association (plan 0049 C2; no LLM).

For every passing row of a ``results.json``, does the judge's own quote contain a bank ``credit``
word for EACH of the item's ``varied_axes`` (word-bounded, case-folded; an axis with several
credit groups needs one word of every group)? A miss is a candidate partial-composition pass,
not proof of one (the credit lists are short: "unaware her job offer was revoked" names the
mistaken belief but holds none of "mistaken / mistakenly / misled").

Usage: ``python scripts/conjunctive/composition_check.py <results.json> [--bank items.json]
[--all-gold]`` (``--all-gold``: every row whose pick was gold before the comp-v2 checks, i.e.
``pick in {gold, gold_partial, gold_unverified}``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BANK = ROOT / "evals/conjunctive_association/items.json"
RAW_GOLD = ("gold", "gold_partial", "gold_unverified")


def word_in(word: str, text: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(word.casefold())}(?![\w])", text.casefold()) is not None


def axis_covered(groups: list[list[str]], quote: str) -> bool:
    return all(any(word_in(w, quote) for w in g) for g in groups)


def check(rows: list[dict], bank: dict[str, dict], *, all_gold: bool) -> dict:
    picks = RAW_GOLD if all_gold else ("gold",)
    out = []
    for r in rows:
        if r.get("pick") not in picks and not (r.get("correct") and not all_gold):
            continue
        it = bank[r["id"]]
        quote = str(r.get("quote") or "")
        missing = [a for a in it["varied_axes"] if not axis_covered(it["credit"][a], quote)]
        out.append({"id": r["id"], "pick": r.get("pick"), "quote": quote, "missing": missing})
    n_full = sum(1 for o in out if not o["missing"])
    return {"n_pass": len(out), "n_every_axis": n_full, "rows": out}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results", type=Path)
    ap.add_argument("--bank", type=Path, default=BANK)
    ap.add_argument("--all-gold", action="store_true")
    a = ap.parse_args()
    res = json.loads(a.results.read_text(encoding="utf-8"))
    bank = {it["id"]: it for it in json.loads(a.bank.read_text(encoding="utf-8"))}
    rep = check(res["rows"], bank, all_gold=a.all_gold)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

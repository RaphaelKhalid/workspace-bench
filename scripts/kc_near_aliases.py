"""knowledge_cutoff bank v2 (plan 0044 §C1, §C6): the offline, deterministic near-alias scan and
the v2 bank build. No model call, no GPU.

1. **Scan.** For every option form of every scored item (the frozen bank minus retired ids, plus
   the nocot items), strip trailing variant words (``VARIANT_WORDS``) one at a time. A stripped
   form F is a candidate for option o when F is not already one of o's forms and no other
   option of the item has F as a form or as the start of a form.
2. **Review.** ``REVIEW`` holds the frozen verdict per candidate (accept unless (a) F names a
   separately released sibling of another option, (b) F is a bare brand / common word, (c) F is
   a strip artefact). Every candidate must have a verdict; the build refuses otherwise.
3. **Build** (``--write``): ``evals/knowledge_cutoff/items_v2.json`` = ``items.json`` minus the
   hygiene retirements (``RETIRE``), with accepted forms appended to the frozen items'
   ``option_units`` and recorded for the nocot items in the header's ``near_alias_additions``
   (``obscure_items.json`` stays byte-identical). ``items.json`` is never touched.

    python scripts/kc_near_aliases.py            # print the candidates and their verdicts
    python scripts/kc_near_aliases.py --write    # (re)build items_v2.json
"""

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wsbench.multitoken.regex import fold  # noqa: E402  (the scorer's fold)

V1 = ROOT / "evals" / "knowledge_cutoff" / "items.json"
V2 = ROOT / "evals" / "knowledge_cutoff" / "items_v2.json"
OBSCURE = ROOT / "evals" / "knowledge_cutoff" / "obscure_items.json"

VARIANT_WORDS = (
    "neo|ceo|family|series|pro|max|plus|ultra|mini|lite|networking|networks|inc|corp|ltd|group|"
    "holdings|technologies|company"
)
# a trailing variant word after a space / hyphen, or glued to a digit or letter ("A321neo")
_TRAIL = re.compile(rf"(?:[\s\-]+|(?<=[0-9A-Za-z]))(?:{VARIANT_WORDS})$", re.I)

RETIRE = {
    "cs01301": "null label: gold 'not traded' (G0 excludes null labels: 0 / none / no club ...) "
    "and option E is a 153-character refusal sentence ('this is a trick question! ...')",
}

# (item id, option, folded candidate) -> (verdict, reason)
REVIEW: dict[tuple[str, str, str], tuple[str, str]] = {
    ("cs01684", "a321neo", "a321"): ("accept", "Q8's example: no other option is an A321"),
    ("cs01684", "a321neo", "airbus a321"): ("accept", "the A321 with the maker's name"),
    ("cs01684", "a321neo", "空客a321"): ("accept", "Chinese short maker name + A321"),
    ("cs01684", "a321neo", "空中客车a321"): ("accept", "Chinese maker name + A321"),
    ("kc3_01462", "geely panda mini", "geely panda"): (
        "accept",
        "no other option is a Panda; Geely sells the Panda mini as the Panda",
    ),
    ("kc3_01462", "geely panda mini", "panda"): ("reject", "(b) a bare common word"),
    ("cs00140", "o1-mini", "o1"): ("reject", "(a) o1 is a separately released sibling model"),
    ("cs00140", "o1-mini", "openai o1"): ("reject", "(a) o1 is a separately released sibling"),
    ("cs00140", "o3-mini", "o3"): ("reject", "(a) o3 is a separately released sibling model"),
    ("cs00140", "o3-mini", "openai o3"): ("reject", "(a) o3 is a separately released sibling"),
    ("cs00140", "o4-mini", "o4"): ("reject", "(a) o4 is a separately released sibling model"),
    ("cs00140", "o4-mini", "openai o4"): ("reject", "(a) o4 is a separately released sibling"),
    ("cs00140", "gemini 1.5 pro", "gemini 1.5"): (
        "reject",
        "(a) Gemini 1.5 names the family, incl. its separately released Flash sibling",
    ),
    ("cs00140", "gemini 1.5 pro", "gemini-1.5"): ("reject", "(a) as 'gemini 1.5'"),
    ("cs00140", "gemini 1.5 pro", "google gemini 1.5"): ("reject", "(a) as 'gemini 1.5'"),
    ("cs01078", "xbox series x|s", "xbox"): ("reject", "(b) a bare brand"),
    ("kc3_01004", "borneo", "bor"): ("reject", "(c) a strip artefact of 'borneo'"),
}


def _items() -> list[dict]:
    v1 = json.loads(V1.read_text(encoding="utf-8"))["items"]
    obscure = json.loads(OBSCURE.read_text(encoding="utf-8"))["items"]
    return [{**it, "_src": "cutoff"} for it in v1 if it["id"] not in RETIRE] + [
        {**it, "_src": "nocot"} for it in obscure
    ]


def scan(items: list[dict]) -> dict[tuple[str, str, str], str]:
    """``{(item id, option, folded F): display form}`` (the display keeps the source case)."""
    out: dict[tuple[str, str, str], str] = {}
    for it in items:
        units = {o: {o, *fs} for o, fs in it["option_units"].items()}
        for opt, forms in units.items():
            own = {fold(f) for f in forms}
            others = [fold(f) for o2, fs in units.items() if o2 != opt for f in fs]
            for form in sorted(forms):
                s = form.strip()
                while (m := _TRAIL.search(s)) is not None:
                    s = s[: m.start()].strip(" -")
                    if not s:
                        break
                    f = fold(s)
                    if f in own or any(x == f or x.startswith(f) for x in others):
                        continue
                    out.setdefault((it["id"], opt, f), s)
    return out


def review_rows(items: list[dict]) -> list[dict]:
    cands = scan(items)
    missing = sorted(set(cands) - set(REVIEW))
    stale = sorted(set(REVIEW) - set(cands))
    if missing or stale:
        raise SystemExit(f"near-alias review out of date: unreviewed {missing}, stale {stale}")
    src = {it["id"]: it["_src"] for it in items}
    return [
        {
            "id": iid,
            "source": src[iid],
            "option": opt,
            "form": cands[(iid, opt, f)],
            "verdict": REVIEW[(iid, opt, f)][0],
            "reason": REVIEW[(iid, opt, f)][1],
        }
        for (iid, opt, f) in sorted(cands)
    ]


def g1_conditional_floor(items: list[dict]) -> float:
    """The v1 header's formula: mean over items of 1 / (K - u), u = the options G1's readers
    picked (``g1.picks``) that are on the item's list."""
    vals = []
    for it in items:
        k = len(it["options"])
        u = len(set(it.get("g1", {}).get("picks") or []) & set(it["options"]))
        vals.append(1 / (k - u) if k > u else 0.0)
    return round(sum(vals) / len(vals), 4)


def build() -> dict:
    raw = json.loads(V1.read_text(encoding="utf-8"))
    items = _items()
    rows = review_rows(items)
    accepted: dict[str, dict[str, list[str]]] = collections.defaultdict(dict)
    for r in rows:
        if r["verdict"] == "accept":
            accepted[r["id"]].setdefault(r["option"], []).append(r["form"])
    kept, retired = [], []
    for it in raw["items"]:
        if it["id"] in RETIRE:
            retired.append({**it, "reason": RETIRE[it["id"]]})
            continue
        add = accepted.get(it["id"], {})
        if add:
            units = {o: list(fs) for o, fs in it["option_units"].items()}
            for o, forms in add.items():
                units[o] = units[o] + [f for f in forms if f not in units[o]]
            it = {**it, "option_units": units}
        kept.append(it)
    nocot_ids = {it["id"] for it in items if it["_src"] == "nocot"}
    header = {k: v for k, v in raw.items() if k not in ("items",)}
    out = {
        **header,
        "version": 2,
        "supersedes": "items.json",
        "n_items": len(kept),
        "changes": [
            "cs01301 retired: null label 'not traded' (G0 excludes null labels) and a "
            "refusal-sentence option",
            "near-alias forms added per Q8 (see near_alias_review)",
        ],
        "label_mix": dict(collections.Counter(it["label_type"] for it in kept)),
        "strata": dict(sorted(collections.Counter(it["stratum"] for it in kept).items())),
        "g1_conditional_floor": g1_conditional_floor(kept),
        "near_alias_rule": (
            "candidates: strip trailing variant words ("
            + VARIANT_WORDS.replace("|", ", ")
            + ") from every option form; keep F when no other option has F as a form or as the "
            "start of a form. Accept unless (a) F names a separately released sibling of another "
            "option, (b) F is a bare brand or common word, (c) F is a strip artefact. "
            "scripts/kc_near_aliases.py"
        ),
        "near_alias_review": rows,
        "near_alias_additions": {
            iid: opts for iid, opts in sorted(accepted.items()) if iid in nocot_ids
        },
        "items": kept,
        "retired_hygiene": retired,
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help=f"write {V2.relative_to(ROOT)}")
    a = ap.parse_args()
    rows = review_rows(_items())
    for r in rows:
        row = f"{r['id']:<11} {r['option']!r:<22} {r['form']!r:<22} {r['verdict']:<7}"
        print(row, r["reason"])
    print(f"{len(rows)} candidates on {len({r['id'] for r in rows})} items; "
          f"{sum(r['verdict'] == 'accept' for r in rows)} accepted")  # fmt: skip
    if a.write:
        V2.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {V2.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

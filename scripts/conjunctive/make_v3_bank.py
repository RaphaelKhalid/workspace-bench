"""Build ``evals/conjunctive_association/items_v3.json``: v2 + two never-gold grid confusers (and
their twins) per twinned cluster (round 4, Camila r2 MC leakage standard).

Camila r2: "making sure that an options only baseline cannot guess beyond chance". Every grid
option of a v2 cluster is the gold of one of its 10 items and no twin is ever a gold, so an
options-only guesser that never picks a twin scores 1/10 against a uniform 1/20 (measured Opus 5.5
blind 0.108 vs 0.056, i.e. +5.2 points). v3 adds ONE new value of one varied axis per twinned
cluster: the two grid options it makes are gold of no item, so the never-twin pool grows to 12 of
24 options. q06 (no twins: its options-only floor is already uniform) is unchanged.

Stages:

- ``propose`` (Opus 5.5, one call per cluster): sees the cluster's option list, the axis and its
  current values, never a stimulus; returns one new value phrase (same topic, form and register;
  not a synonym, instance or hypernym of any current value). Frozen in
  ``evals/conjunctive_association/v3_new_values.json``.
- ``build [--check]`` (no LLM): each cluster's new grid options are its grid options holding the
  ``slot`` value with the slot replaced by the new value; their twins come from the v2 builder's
  twin functions (``make_v2_bank.TWIN``), so the new options have exactly the v2 form. Stimuli,
  golds, contrast and inverted labels are unchanged. ``--check`` exits 1 if the committed file
  differs from a fresh build.

    python scripts/conjunctive/make_v3_bank.py propose
    python scripts/conjunctive/make_v3_bank.py build [--check]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_v2_bank import TWIN, render

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "evals/conjunctive_association/items_v2.json"
V3 = ROOT / "evals/conjunctive_association/items_v3.json"
VALUES = ROOT / "evals/conjunctive_association/v3_new_values.json"
EDIT = (
    "v3 2026-11-01: two never-gold grid confusers (one new {axis} value, {new!r}) and their twins "
    "added (round 4, MC leakage standard)"
)
MODEL = "claude-opus-5-5"
# per twinned cluster: the varied axis that gets a new value and the current value phrase whose
# grid options are copied (the slot); the new value replaces the slot verbatim
SLOTS: dict[str, tuple[str, str]] = {
    "q01": ("relation", "her parent"),
    "q02": ("content", "promotion"),
    "q03": ("relation", "his parent"),
    "q04": ("relation", "her sibling"),
    "q05": ("relation", "her cousin"),
    "q07": ("relation", "her sibling"),
    "q08": ("motive", "out of ambition for the directorship"),
    "q09": ("relation", "his sibling"),
    "q10": ("relation", "her sibling"),
}
_PRONOUN = re.compile(r"\b(he|him|his|she|her|hers|himself|herself|they|them|their)\b", re.I)

SYSTEM = (
    "You extend the answer options of a multiple-choice benchmark question. The options describe "
    "a story character's compound state; they vary along a few axes. You are given the option "
    "list, one axis and its current values. Propose ONE new value for that axis that would make "
    "two more equally plausible, same-topic wrong options. Rules: the new value must not be a "
    "synonym, near-synonym, instance, hypernym or paraphrase of any current value (or of any "
    "value on another axis); it must fit the same topic and situation, and have the same form, "
    "length and register as the current values, so the new options read exactly like the others; "
    "it must be ordinary, not odd or comic: pick the most common, everyday value of this axis "
    "that is not listed yet, the kind a story bank would most likely use, as a plain word or "
    "phrase with no extra qualifier (a guesser shown the full option list must find the new "
    "options exactly as likely to be right as the current ones). Reply with the new value "
    "phrase only, written exactly as it will be substituted for the slot value."
)
SCHEMA = {
    "name": "new_value",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["value", "why"],
        "properties": {"value": {"type": "string"}, "why": {"type": "string"}},
    },
}


def _v2() -> list[dict]:
    return json.loads(V2.read_text(encoding="utf-8"))


def grids(items: list[dict]) -> dict[str, list[str]]:
    """Each cluster's grid options, in v2 order: every grid option is the gold of one of the
    cluster's items (v2: 10 items, 10 grid options), every twin the gold of none."""
    golds: dict[str, set[str]] = {}
    for it in items:
        golds.setdefault(it["cluster"], set()).add(it["gold_label"])
    out: dict[str, list[str]] = {}
    for it in items:
        g = [o for o in it["mc_options"] if o in golds[it["cluster"]]]
        if out.setdefault(it["cluster"], g) != g:
            raise ValueError(f"{it['id']}: grid differs from its cluster's")
    return out


# round-4 first proposals ("her younger sibling", "pregnancy", "her editor", ...) drew 6% of an
# options-only guesser's non-twin picks against the 17% their share predicts (odd ones out), so
# the prompt asks for the most ordinary unused value; the first proposals are in git history.
# a proposal rejected because the cached readouts would favour it (the readout-favour scan:
# q04_b readouts say boss / manager in 81 of 836 samples, so "her supervisor" would draw them;
# the next proposal, "her spouse", is named in 435 of the 8360 q04 samples, assistant in 311)
AVOID: dict[str, tuple[str, ...]] = {
    "q04": ("supervisor", "boss", "manager", "spouse", "husband", "wife", "partner", "assistant")
}


def propose(only: list[str] | None = None) -> None:
    from wsbench import llm

    gs = grids(_v2())
    prompts, keys = [], []
    for c, (axis, slot) in SLOTS.items():
        if only and c not in only:
            continue
        values = sorted({v for it in _v2() if it["cluster"] == c for v in [it["cell"].get(axis)]})
        user = (
            "OPTIONS:\n"
            + "\n".join(f"- {o}" for o in gs[c])
            + f"\n\nAXIS: {axis}\nCURRENT VALUES (as the story bank names them): "
            + ", ".join(str(v) for v in values)
            + f"\nSLOT: in the options above, the value phrase {slot!r} will be replaced by your "
            "new value, so write it in exactly that form (e.g. a possessive relation phrase like "
            "'her neighbor', a noun phrase, or a motive phrase)."
        )
        if AVOID.get(c):
            user += " Do not use: " + ", ".join(AVOID[c]) + " (or any synonym of them)."
        if axis == "motive":
            user += (
                " Use no pronoun (he/him/his/she/her/they): the phrase is reused for both people."
            )
        prompts.append((SYSTEM, user))
        keys.append(c)
    got: dict[int, dict | None] = {}
    llm.stream_json(prompts, schema=SCHEMA, model=MODEL, on_result=got.__setitem__)
    old = json.loads(VALUES.read_text(encoding="utf-8"))["values"] if VALUES.exists() else {}
    doc = {
        "model": MODEL,
        "prompt": SYSTEM,
        "avoid": {c: list(v) for c, v in AVOID.items()},
        "values": old
        | {
            c: {
                "axis": SLOTS[c][0],
                "slot": SLOTS[c][1],
                "new": " ".join(str((got.get(i) or {}).get("value", "")).split()),
                "why": (got.get(i) or {}).get("why", ""),
            }
            for i, c in enumerate(keys)
        },
    }
    for c, v in doc["values"].items():
        print(c, v["slot"], "->", v["new"])
    VALUES.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def build(v2: list[dict], values: dict[str, dict]) -> list[dict]:
    gs = grids(v2)
    extra: dict[str, list[str]] = {}
    extra_twins: dict[str, dict[str, str]] = {}
    for c, (axis, slot) in SLOTS.items():
        new = values[c]["new"]
        if not new or values[c]["slot"] != slot or values[c]["axis"] != axis:
            raise ValueError(f"{c}: no frozen new value for slot {slot!r}")
        if axis == "motive" and _PRONOUN.search(new):
            raise ValueError(f"{c}: a motive value must hold no pronoun: {new!r}")
        src = [o for o in gs[c] if slot in o]
        if len(src) != 2:
            raise ValueError(f"{c}: slot {slot!r} is in {len(src)} grid options, not 2")
        made = [o.replace(slot, new) for o in src]
        everything = set(gs[c]) | set(v2[[it["cluster"] for it in v2].index(c)]["mc_options"])
        if any(m in everything for m in made):
            raise ValueError(f"{c}: a new option already exists")
        tw: dict[str, str] = {}
        for m in made:
            t = TWIN[c](m)
            if t is not None:
                tw[m], tw[t] = t, m
        extra[c] = made
        extra_twins[c] = tw
    out = []
    for it in v2:
        c = it["cluster"]
        new = dict(it)
        if c in extra:
            made, tw = extra[c], extra_twins[c]
            new["mc_options"] = [*it["mc_options"], *made, *(tw[m] for m in made if m in tw)]
            new["twin_of"] = {**it["twin_of"], **tw}
            prov = dict(it["provenance"])
            edit = EDIT.replace("{axis}", SLOTS[c][0]).replace("{new!r}", repr(values[c]["new"]))
            prov["edits"] = [*prov.get("edits", []), edit]
            new["provenance"] = prov
        new["bank_version"] = 3
        out.append(new)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=("propose", "build"))
    ap.add_argument("--check", action="store_true", help="fail if the committed v3 is stale")
    ap.add_argument("--only", default="", help="propose: comma-separated clusters")
    a = ap.parse_args()
    if a.stage == "propose":
        propose([c for c in a.only.split(",") if c] or None)
        return 0
    values = json.loads(VALUES.read_text(encoding="utf-8"))["values"]
    text = render(build(_v2(), values))
    if a.check:
        ok = V3.exists() and V3.read_text(encoding="utf-8") == text
        print("items_v3.json is up to date" if ok else "items_v3.json is STALE")
        return 0 if ok else 1
    V3.write_text(text, encoding="utf-8")
    print(f"wrote {V3.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

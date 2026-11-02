"""Build ``evals/conjunctive_association/items_v2.json`` from the v1 bank (no LLM).

Camila (2026-10-30): "Fix the judge's leniency: ... the inverted credit (this is especially
important, maybe use this as another distractor)". Every grid option that involves a second
person gets its role-swapped TWIN (the same description with the protagonist and the other
person swapped everywhere), and every item of a cluster shows its cluster's 10 grid options plus
all of their twins. The twin set is the cluster's, so the gold's twin is never an odd-one-out a
guesser could use. Stimuli, golds and contrast labels are unchanged (no Qwen gating needed).

Usage: ``python scripts/conjunctive/make_v2_bank.py [--check]`` (``--check`` exits 1 if the
committed file differs from a fresh build).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evals/conjunctive_association/items.json"
V2 = ROOT / "evals/conjunctive_association/items_v2.json"
EDIT = "v2 2026-10-30: role-swapped twins added as distractors (conjunctive workstream)"


def _ref(person: str) -> str:
    """A definite back-reference to ``person`` ("a colleague" -> "the colleague")."""
    if person.startswith("a "):
        return "the " + person[2:]
    return person


def _noun_ref(person: str) -> str:
    """The person's head noun as a definite reference ("her longtime mentor" -> "the mentor")."""
    return "the " + person.split()[-1]


def _q01(o: str) -> str | None:
    m = re.fullmatch(r"(grief|guilt) over the sudden accidental death of (.+)", o)
    if not m:
        raise ValueError(o)
    state, who = m.groups()
    if who == "a stranger whose accident she witnessed":
        return (
            f"a stranger's {state} over her sudden accidental death, which the stranger witnessed"
        )
    return f"{who}'s {state} over her sudden accidental death"


def _q02(o: str) -> str | None:
    m = re.fullmatch(r"(envy|pride) at her closest friend's recent (.+)", o)
    if not m:
        raise ValueError(o)
    state, what = m.groups()
    return f"her closest friend's {state} at her recent {what}"


def _q03(o: str) -> str | None:
    m = re.fullmatch(r"dread while awaiting (.+) concerning (.+)", o)
    if not m:
        raise ValueError(o)
    what, who = m.groups()
    if who == "himself":
        return None  # one person: nothing to swap
    return f"{who}'s dread while awaiting {what} concerning him"


def _q04(o: str) -> str | None:
    m = re.fullmatch(r"the intent to conceal her own mistake from (.+)", o)
    if m:
        who = m.group(1)
        return f"{who}'s intent to conceal {_noun_ref(who)}'s own mistake from her"
    m = re.fullmatch(r"the intent to take credit for (.+)'s work", o)
    if m:
        return f"{m.group(1)}'s intent to take credit for her work"
    raise ValueError(o)


def _q05(o: str) -> str | None:
    m = re.fullmatch(r"favoritism steering the commission to (her [^,]+), (.+)", o)
    if not m:
        raise ValueError(o)
    who, why = m.groups()
    return f"{who}'s favoritism steering the commission to her, {why}"


def _q06(o: str) -> str | None:
    return None  # a belief about an outcome, one person: no twin


def _q07(o: str) -> str | None:
    head = "relief at her own reassuring medical news, and the intent to "
    if not o.startswith(head):
        raise ValueError(o)
    rest = o[len(head) :]
    m = re.fullmatch(r"keep the scare hidden from (her .+)", rest)
    if m:
        who = m.group(1)
        return (
            f"{who}'s relief at their own reassuring medical news, and their intent to keep "
            "the scare hidden from her"
        )
    m = re.fullmatch(r"finally tell (her .+) about the scare", rest)
    if m:
        who = m.group(1)
        return (
            f"{who}'s relief at their own reassuring medical news, and their intent to finally "
            "tell her about the scare"
        )
    raise ValueError(o)


_Q08_MOTIVE = {
    "out of self-protection, to keep her own signed-off error buried": (
        "out of self-protection, to keep the colleague's own signed-off error buried"
    ),
    "out of resentment of the favoritism shown him": (
        "out of resentment of the favoritism shown her"
    ),
}


def _q08(o: str) -> str | None:
    m = re.fullmatch(
        r"the intent to sabotage a colleague's demonstration (.+), while believing he (.+)", o
    )
    if not m:
        raise ValueError(o)
    motive, belief = m.groups()
    motive = _Q08_MOTIVE.get(motive, motive)
    return (
        f"a colleague's intent to sabotage her demonstration {motive}, while believing she {belief}"
    )


def _q09(o: str) -> str | None:
    m = re.fullmatch(r"his belief that (his .+) privately feels (.+) that the move was canceled", o)
    if not m:
        raise ValueError(o)
    who, state = m.groups()
    return f"{who}'s belief that he privately feels {state} that the move was canceled"


def _q10(o: str) -> str | None:
    m = re.fullmatch(
        r"her belief that (.+) (deliberately|accidentally) destroyed her unfinished book", o
    )
    if not m:
        raise ValueError(o)
    who, how = m.groups()
    return f"{who}'s belief that she {how} destroyed the unfinished book {_ref(who)} was writing"


TWIN: dict[str, Callable[[str], str | None]] = {
    "q01": _q01,
    "q02": _q02,
    "q03": _q03,
    "q04": _q04,
    "q05": _q05,
    "q06": _q06,
    "q07": _q07,
    "q08": _q08,
    "q09": _q09,
    "q10": _q10,
}


def cluster_twins(grid: list[str], cluster: str) -> dict[str, str]:
    """``{option: twin}`` over the cluster's twinned options, involutive (twin -> option too)."""
    out: dict[str, str] = {}
    for o in grid:
        t = TWIN[cluster](o)
        if t is None:
            continue
        if t in grid:
            raise ValueError(f"{cluster}: twin {t!r} is already a grid option")
        if t in out:
            raise ValueError(f"{cluster}: twin {t!r} produced twice")
        out[o] = t
        out[t] = o
    return out


def build(v1: list[dict]) -> list[dict]:
    grids: dict[str, list[str]] = {}
    for it in v1:
        g = list(dict.fromkeys(it["mc_options"]))
        if grids.setdefault(it["cluster"], g) != g:
            raise ValueError(f"{it['id']}: grid differs from its cluster's")
    twins = {c: cluster_twins(g, c) for c, g in grids.items()}
    out = []
    for it in v1:
        c = it["cluster"]
        tw = twins[c]
        grid = grids[c]
        new = dict(it)
        new["mc_options"] = grid + [tw[o] for o in grid if o in tw]
        new["twin_of"] = tw
        new["inverted_label"] = tw.get(it["gold_label"])
        new["bank_version"] = 2
        prov = dict(it["provenance"])
        prov["edits"] = [*prov.get("edits", []), EDIT]
        new["provenance"] = prov
        out.append(new)
    return out


def render(items: list[dict]) -> str:
    return json.dumps(items, ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if the committed v2 is stale")
    a = ap.parse_args()
    items = build(json.loads(V1.read_text(encoding="utf-8")))
    text = render(items)
    if a.check:
        ok = V2.exists() and V2.read_text(encoding="utf-8") == text
        print("items_v2.json is up to date" if ok else "items_v2.json is STALE")
        return 0 if ok else 1
    V2.write_text(text, encoding="utf-8")
    per_cluster = {it["cluster"]: it["twin_of"] for it in items}
    n_twins = sum(len(tw) // 2 for tw in per_cluster.values())
    print(f"wrote {V2.relative_to(ROOT)}: {n_twins} twin strings")
    return 0


if __name__ == "__main__":
    sys.exit(main())

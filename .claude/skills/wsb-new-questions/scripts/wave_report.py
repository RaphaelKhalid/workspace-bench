"""Steer the next wave: diversity of a bank (`mix`) and why a gated wave failed (`fails`).

    # template / relation mix, repeated latents and shared entities of a (gated) bank
    uv run python .claude/skills/wsb-new-questions/scripts/wave_report.py mix \\
        --family multihop --bank gated/multihop/items.json [--cap 0.2]
    # failure pattern per item of a gate_hf.py wave (reads <dir>/gate.json)
    uv run python .claude/skills/wsb-new-questions/scripts/wave_report.py fails \\
        --family multihop --gated gated/multihop

`mix` exits 1 when one template, relation or latent exceeds --cap of the bank (default 20%):
small banks gated on weak models collapse to a few easy templates, and a lens score over
"capital -> language" x 40 is not a multihop score. `fails` prints a count per pattern and the
item ids, to be read against the decision table in references/weak-model.md.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_bank import fold, item_key, load_any, prompt_text

# item fields that already name a template / stratum in some families
TYPE_FIELDS = (
    "relation",
    "subfamily",
    "variant",
    "stratum",
    "tier",
    "domain",
    "kind",
    "category",
    "failure_mode",
)
# the scored latent per family where it is not intermediates/bridge/target; "" = no latent cap
# (moral repeats each topic in two formats by design; buggy's latent is per-program)
LATENT_FIELD = {"role_bound_association": "action", "moral_rationale": "", "buggy_code": ""}
# a capitalised name not at a sentence or line start (line starts: poetry lines, code)
ENTITY = re.compile(
    r"(?<![.!?:]\s)(?<!^)(?<!\n)\b[A-Z][\w'-]+(?:\s+(?:of|the|de|von|[A-Z][\w'-]+))*"
)
# type fields that ARE capped (many possible values; the rest are informational)
CAPPED_FIELDS = {
    "buggy_code": {"category"},
    "multihop": {"relation"},
    "moral_rationale": {"domain"},
}
CODE_FAMILIES = {"buggy_code", "arithmetic_intermediates", "chain_intermediates"}
SKELETON_WORDS = 8


def skeleton(text: str) -> str:
    """Template key: the first words of the prompt with names and numbers masked."""
    t = ENTITY.sub(" NAME ", re.sub(r"\d[\d,.]*", " NUM ", text))
    words = [w if w in ("NAME", "NUM") else w.lower() for w in re.findall(r"[A-Za-z']+", t)]
    return " ".join(words[:SKELETON_WORDS])


def latent(family: str, it: dict[str, Any]) -> str:
    if family in LATENT_FIELD:
        f = LATENT_FIELD[family]
        return fold(str(it.get(f, ""))) if f else ""
    for k in ("intermediates", "bridge"):
        v = it.get(k)
        if isinstance(v, list) and v:
            return fold(str(v[0]))
        if isinstance(v, str) and v:
            return fold(v)
    return fold(str(it.get("target") or it.get("gold_label") or it.get("key") or ""))


def cmd_mix(family: str, bank: Path, cap: float) -> int:
    _h, items, _l = load_any(bank)
    if family == "buggy_code":  # clean twins mirror their buggy item: count the buggy ones
        items = [it for it in items if it.get("src") != "clean"]
    if family == "moral_rationale":  # one row per topic (each topic has a tf and a yn item)
        items = list({str(it.get("topic_id")): it for it in items}.values())
    n = len(items)
    if not n:
        print("empty bank")
        return 1
    bad = False

    def show(title: str, c: Counter, limit: int = 8, check: bool = True) -> None:
        nonlocal bad
        top = c.most_common(limit)
        share = top[0][1] / n if top else 0.0
        flag = check and share > cap and n >= 3
        bad |= flag
        over = " OVER CAP" if flag else ""
        print(f"{title}: {len(c)} distinct over {n} items; largest {share:.0%}{over}")
        for k, v in top:
            print(f"   {v:3d}  {k}")

    for f in TYPE_FIELDS:  # informational unless capped: a 2-valued field can't be under 20%
        vals = [str(it[f]) for it in items if f in it]
        if len(vals) >= n / 2:
            capped = f in CAPPED_FIELDS.get(family, set())
            show(f"field {f!r}{'' if capped else ' (not capped)'}", Counter(vals), check=capped)
    if family == "chain_intermediates":  # its templates are the step sequences
        seq = Counter(
            " > ".join(map(str, it.get("kinds") or it.get("steps") or [])) for it in items
        )
        show("step sequence", seq)
    texts = [prompt_text(family, it) for it in items]
    fixed = family in ("chain_intermediates", "arithmetic_intermediates")
    show(  # the computational families share one prompt frame by design
        "prompt template (first words, names/numbers masked)",
        Counter(map(skeleton, texts)),
        check=not fixed,
    )
    lat = Counter(latent(family, it) for it in items)
    if any(lat):
        show("scored latent", lat, check=True)
    if family in CODE_FAMILIES:
        print("MIX " + ("FAIL (diversify the next wave; see weak-model.md)" if bad else "OK"))
        return 1 if bad else 0
    ents: dict[str, set[str]] = defaultdict(set)
    for it, t in zip(items, texts, strict=True):
        for m in ENTITY.findall(t):
            ents[m].add(item_key(it))
    shared = sorted(((len(v), k) for k, v in ents.items() if len(v) > 1), reverse=True)
    print(f"entities named in >1 prompt: {len(shared)}")
    for c, k in shared[:8]:
        print(f"   {c:3d}  {k}")
    print("MIX " + ("FAIL (diversify the next wave; see weak-model.md)" if bad else "OK"))
    return 1 if bad else 0


def leg_pattern(q: dict[str, Any]) -> str:
    """Why one failed gate question failed."""
    if q.get("leaks"):
        return "cot_leak (wrote the intermediate)"
    if q.get("stopped"):
        return "stopped after step 1 (answered the first intermediate)"
    if q["mode"].startswith("own_poetry"):
        if not q.get("word"):
            return "poetry: no first word"
        if not q.get("rhymes"):
            return "poetry: greedy word does not rhyme"
        return "poetry: rhymes but unstable (< need samples agree)"
    if q["mode"] == "mc":
        from gate_hf import mc_letter

        if not mc_letter(q.get("greedy", "")):
            return "mc: no parsable letter"
        return "mc: wrong or unstable letter"
    if q.get("truncated_greedy") and not q.get("raw"):  # raw legs always run to max_new
        return "truncated (no stop token within max_new)"
    if not q.get("greedy_ok"):
        return "greedy wrong"
    return "greedy right, samples inconsistent"


def pattern(k: str, legs: list[dict[str, Any]]) -> str:
    """One pattern per item. The gate variants (chat `k`, raw `k:plain`) are alternatives: the
    item passes when one of them and every other leg (bridges, reversed MC order) pass."""
    variants = [q for q in legs if q["qid"] in (k, f"{k}:plain")] or legs[:1]
    others = [q for q in legs if q not in variants]
    v_ok = any(q.get("pass") for q in variants)
    if v_ok and all(q.get("pass") for q in others):
        via = next(q for q in variants if q.get("pass"))
        return "pass (plain variant)" if via["qid"].endswith(":plain") else "pass"
    rev = [q for q in others if q["qid"].endswith(":mc_reversed")]
    if rev and v_ok != bool(rev[0].get("pass")):
        return "mc: right in one option order only (position bias)"
    bridges = [q for q in others if ":bridge" in q["qid"]]
    if bridges and v_ok:
        return "surface right, a bridge leg fails"
    if bridges and all(q.get("pass") for q in bridges):
        return "bridges known, composition fails"
    best = max(variants, key=lambda q: q.get("hits") or 0)
    tag = " [plain]" if best["qid"].endswith(":plain") else ""
    return leg_pattern(best) + tag


def buggy_pattern(r: dict[str, Any]) -> str:
    if r.get("pass"):
        return "pass"
    got, _n = (int(x) for x in str(r.get("consequence_hits", "0/6")).split("/"))
    if got < 4:
        return "consequence: mispredicts the buggy output (< 4/6)"
    if r.get("gate_tier") == "fail":
        return "volunteers / fixes the bug in continuations"
    if r.get("output_leak") is True:
        return "continuations leak the buggy output"
    return "undecided judge call"


def moral_pattern(it: dict[str, Any]) -> str:
    if it.get("gate_pass"):
        return f"pass ({it.get('reason_class')}, commits {it.get('commit_direction')})"
    if not it.get("look_for_reasons"):
        return "no usable distilled reason"
    if not (it.get("gate_committed_token") and it.get("commit_precise")):
        return "no clean one-word yes/no commit"
    if not it.get("gate_aligned"):
        return "commit disagrees with the elicited majority"
    if not it.get("gate_reason_side_ok"):
        return "looked-for reason argues the other side"
    return "other"


def cmd_fails(fam: str, gated: Path) -> int:
    rows = json.loads((gated / "gate.json").read_text(encoding="utf-8"))
    pats: dict[str, list[str]] = defaultdict(list)
    if fam == "buggy_code":
        for r in rows:
            pats[buggy_pattern(r)].append(str(r["name"]))
    elif fam == "moral_rationale":
        for it in rows:
            pats[moral_pattern(it)].append(str(it["id"]))
    else:
        by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for q in rows:
            by_item[q["item"]].append(q)
        for k, legs in by_item.items():
            pats[pattern(k, legs)].append(k)
        if fam in ("role_bound_association", "conjunctive_association"):
            from gate_hf import mc_letter

            letters = Counter(mc_letter(q.get("greedy", "")) for q in rows if q["mode"] == "mc")
            top, c = letters.most_common(1)[0] if letters else ("", 0)
            if rows and c / max(1, sum(letters.values())) > 0.7:
                print(f"note: greedy answered {top!r} on {c}/{sum(letters.values())} MC asks")
    n = sum(len(v) for v in pats.values())
    for p, ks in sorted(pats.items(), key=lambda kv: -len(kv[1])):
        more = " ..." if len(ks) > 4 else ""
        print(f"{len(ks):4d} ({len(ks) / n:5.1%})  {p}: {', '.join(ks[:4])}{more}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mix")
    m.add_argument("--family", required=True)
    m.add_argument("--bank", required=True, type=Path)
    m.add_argument("--cap", type=float, default=0.2)
    f = sub.add_parser("fails")
    f.add_argument("--family", required=True)
    f.add_argument("--gated", required=True, type=Path)
    a = ap.parse_args()
    if a.cmd == "mix":
        return cmd_mix(a.family, a.bank, a.cap)
    return cmd_fails(a.family, a.gated)


if __name__ == "__main__":
    sys.exit(main())

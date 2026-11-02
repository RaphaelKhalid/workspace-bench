"""Bank v2 of chain_intermediates (plan 0038 C11 + C5): every intermediate in 10..99, frozen
8-option MC lists. ``items.json`` (v1) is never touched.

Stages (CPU except the Qwen gate, which runs ``scripts/qwen_sample_modal.py`` on Modal):

    # 1. candidates: v1's seed-last generator with every INTERMEDIATE in 10..99, no conditionals
    python scripts/build_chain_v2.py candidates --out $D/candidates.json [--n-per-depth 400]
    # 2. Qwen gate request rows (seed-last chat render, thinking off, 10 x T=0.8 + greedy)
    python scripts/build_chain_v2.py requests --candidates $D/candidates.json --out $D/req.jsonl
    PYTHONPATH=src modal run scripts/qwen_sample_modal.py --requests $D/req.jsonl \
        --out $D/samples.jsonl --shards 8
    # 3. grade (strict 10/10 + greedy + no rollout writing an intermediate), pick the 24 + 13
    #    replacements round-robin over step kinds, build the MC blocks, write items_v2.json
    python scripts/build_chain_v2.py freeze --candidates $D/candidates.json \
        --samples $D/samples.jsonl [--gate-log $D/gate_log.json]

The v1 generator is the source repo's ``scripts/olens_suite/chain_intermediates/gen_chain.py``
(construction rules in its docstring); only the intermediate floor (VMIN 1 -> 10), the ceiling
(80 -> 99) and ``cond_frac = 0`` change."""

import argparse
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from wsbench.evals.chain_intermediates import options as mcopt  # noqa: E402

V1 = REPO / "evals/chain_intermediates/items.json"
V2 = REPO / "evals/chain_intermediates/items_v2.json"
FAMILY = "chain_intermediates"
RENDER_LAST = (
    "Apply the steps below, in order, to the starting number given at the end.\n"
    "{steps}\n"
    "The starting number is {start}. What is the final number? "
    "Reply with only the final number, nothing else."
)
RENDER_FIRST = (
    "Start with the number {start} and apply the steps below, in order.\n"
    "{steps}\n"
    "What is the final number? Reply with only the final number, nothing else."
)
INTER_MIN, INTER_MAX = 10, 99  # v2: every intermediate is a multi-digit number
VMIN, VMAX = 1, 99  # start and answer
GATE = {
    "k": 10,
    "max_new": 16,
    "temperature": 0.8,
    "top_p": 0.95,
    "min_correct": 10,
    "max_leak": 0,
    "greedy": True,
    "render": "seed-last, chat template, enable_thinking=False",
}
N_REPLACE = {2: 24, 3: 13}


# ---------------------------------------------------------------- candidates (gen_chain port)


def _steps() -> dict[str, Any]:
    def add(r: random.Random) -> dict[str, Any]:
        n = r.randint(2, 9)
        return {"kind": "add", "n": n, "text": f"Add {n}."}

    def sub(r: random.Random) -> dict[str, Any]:
        n = r.randint(2, 9)
        return {"kind": "sub", "n": n, "text": f"Subtract {n}."}

    return {
        "add": add,
        "sub": sub,
        "double": lambda r: {"kind": "double", "text": "Double it."},
        "triple": lambda r: {"kind": "triple", "text": "Multiply it by 3."},
        "halve_up": lambda r: {"kind": "halve_up", "text": "Halve it, rounding up."},
        "halve_down": lambda r: {"kind": "halve_down", "text": "Halve it, rounding down."},
    }


STEPS = _steps()


def apply(step: dict[str, Any], x: int) -> int:
    k = step["kind"]
    if k == "add":
        return x + step["n"]
    if k == "sub":
        return x - step["n"]
    if k == "double":
        return 2 * x
    if k == "triple":
        return 3 * x
    if k == "halve_up":
        return math.ceil(x / 2)
    if k == "halve_down":
        return x // 2
    raise ValueError(k)


def literals(text: str) -> set[int]:
    return {int(m) for m in re.findall(r"\d+", text)}


def build(rng: random.Random, depth: int) -> dict[str, Any] | None:
    """One seed-last candidate (gen_chain.build without conditionals), or None."""
    steps = [rng.choice(list(STEPS.values()))(rng) for _ in range(depth)]
    start = rng.randint(2, 30)
    vals, x = [], start
    for st in steps:
        x = apply(st, x)
        vals.append(x)
    inter, answer = vals[:-1], vals[-1]
    if not all(INTER_MIN <= v <= INTER_MAX for v in inter) or not VMIN <= answer <= VMAX:
        return None
    allv = [start, *vals]
    if len(set(allv)) != len(allv):
        return None
    step_text = "\n".join(s["text"] for s in steps)
    prompt = RENDER_LAST.format(steps=step_text, start=start)
    prompt_first = RENDER_FIRST.format(steps=step_text, start=start)
    lits = literals(prompt) | literals(prompt_first)
    if any(v in lits for v in vals):  # the leak rule (the start is a literal by necessity)
        return None
    forbid = set(allv)
    constants = sorted(lits - {start})
    distractors: list[list[int]] = []
    for v in inter:  # gen_chain's 4 per slot: start, answer, off-by-one/two, a constant
        pool: list[int] = []

        def push(c: int, *, gold_ok: bool = False, v: int = v, pool: list[int] = pool) -> None:
            if c < VMIN or c > VMAX or c == v or c in pool or (not gold_ok and c in forbid):
                return
            pool.append(c)

        push(start, gold_ok=True)
        push(answer, gold_ok=True)
        for c in rng.sample([v - 1, v + 1], 2) + rng.sample([v - 2, v + 2], 2):
            if len(pool) >= 3:
                break
            push(c)
        for c in rng.sample(constants, len(constants)):
            if len(pool) >= 4:
                break
            push(c)
        delta = 2
        while len(pool) < 4:
            for c in (v - delta, v + delta):
                push(c)
                if len(pool) >= 4:
                    break
            delta += 1
        distractors.append(pool[:4])
    return {
        "depth": depth,
        "cond": False,
        "kinds": [s["kind"] for s in steps],
        "steps": [s["text"] for s in steps],
        "start": start,
        "intermediates": inter,
        "untaken": [None] * len(inter),
        "answer": answer,
        "prompt": prompt,
        "prompt_first": prompt_first,
        "literals": sorted(lits),
        "distractors": distractors,
    }


def cmd_candidates(a: argparse.Namespace) -> None:
    rng = random.Random(a.seed)
    seen = {it["prompt"] for it in json.loads(V1.read_text())["items"]}
    out: list[dict[str, Any]] = []
    for depth in (2, 3):
        made = tries = 0
        while made < a.n_per_depth and tries < 2_000_000:
            tries += 1
            it = build(rng, depth)
            if it is None or it["prompt"] in seen:
                continue
            seen.add(it["prompt"])
            it["name"] = f"chain-v2-d{depth}p-{len(out):04d}"
            out.append(it)
            made += 1
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"family": FAMILY, "seed": a.seed, "items": out}, indent=1))
    by = Counter(it["depth"] for it in out)
    print(f"[candidates] {len(out)} -> {a.out}  by depth {dict(by)}")


# ---------------------------------------------------------------- gate requests / grading


def cmd_requests(a: argparse.Namespace) -> None:
    items = json.loads(Path(a.candidates).read_text())["items"]
    if a.limit:
        items = items[: a.limit // 2] + [i for i in items if i["depth"] == 3][: a.limit // 2]
    rows = [
        {
            "key": it["name"],
            "family": FAMILY,
            "messages": [{"role": "user", "content": it["prompt"]}],
            "n": GATE["k"],
            "temperature": GATE["temperature"],
            "top_p": GATE["top_p"],
            "max_tokens": GATE["max_new"],
            "enable_thinking": False,
            "greedy": True,
        }
        for it in items
    ]
    Path(a.out).write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"[requests] {len(rows)} rows -> {a.out}")


def parse_int(text: str) -> int | None:
    m = re.search(r"-?\d+", text)
    return int(m.group()) if m else None


def standalone_ints(text: str) -> set[int]:
    return {int(m) for m in re.findall(r"(?<![\d.])-?\d+(?![\d.])", text)}


def grade(item: dict[str, Any], outs: list[dict[str, Any]]) -> dict[str, Any]:
    """v1's gate verdict (gate_chain.verdict) at the strict bar: greedy correct, 10/10 sampled
    correct, no rollout (sampled or greedy) stating an intermediate."""
    answer = int(item["answer"])
    inter = {int(v) for v in item["intermediates"]}
    rolls = [o["text"] for o in outs if not o["greedy"]]
    greedy = [o["text"] for o in outs if o["greedy"]]
    correct = sum(parse_int(r) == answer for r in rolls)
    leaks = [r for r in rolls + greedy if standalone_ints(r) & inter]
    greedy_ok = bool(greedy) and parse_int(greedy[0]) == answer
    perfect = greedy_ok and correct == GATE["k"] == len(rolls) and not leaks
    return {
        "ok": perfect,
        "greedy_ok": greedy_ok,
        "correct": correct,
        "n": len(rolls),
        "perfect": perfect,
        "n_leaks": len(leaks),
    }


def pick_replacements(passed: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """The first 24 depth-2 + 13 depth-3 passers, round-robin over step-kind tuples (v1's
    selection), in candidate order within a kind tuple."""
    out: dict[int, list[dict[str, Any]]] = {}
    for depth, want in N_REPLACE.items():
        by_kind: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for it in passed:
            if it["depth"] == depth:
                by_kind[tuple(it["kinds"])].append(it)
        order = sorted(by_kind)
        chosen: list[dict[str, Any]] = []
        while len(chosen) < want and any(by_kind[k] for k in order):
            for k in order:
                if by_kind[k] and len(chosen) < want:
                    chosen.append(by_kind[k].pop(0))
        if len(chosen) < want:
            raise SystemExit(f"depth {depth}: only {len(chosen)} passers, need {want}")
        out[depth] = chosen
    return out


def cmd_freeze(a: argparse.Namespace) -> None:
    v1 = json.loads(V1.read_text())
    cands = {it["name"]: it for it in json.loads(Path(a.candidates).read_text())["items"]}
    outs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in Path(a.samples).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            outs[r["key"]].append(r)
    graded = {k: grade(cands[k], v) for k, v in outs.items() if k in cands}
    passed = [cands[k] for k in cands if k in graded and graded[k]["ok"]]
    chosen = pick_replacements(passed)
    kept = [it for it in v1["items"] if min(it["intermediates"]) >= INTER_MIN]
    dropped = [it["name"] for it in v1["items"] if min(it["intermediates"]) < INTER_MIN]
    new = []
    for depth in (2, 3):
        for it in chosen[depth]:
            g = graded[it["name"]]
            new.append(
                {**it, "gate": {"last": {k: g[k] for k in ("ok", "greedy_ok", "correct", "n")}}}
            )
            new[-1]["gate"]["last"]["perfect"] = g["perfect"]
    items = kept + new
    mc = mcopt.build_mc(items)
    for it in items:
        it["mc"] = mc[it["name"]]
    header = {k: v for k, v in v1.items() if k != "items"}
    header.update(
        {
            "version": 2,
            "supersedes": "items.json",
            "n": len(items),
            "gate_v2": {**GATE, "model": "Qwen/Qwen3.6-27B (vLLM on Modal, qwen_sample_modal.py)"},
            "selection": {
                **header["selection"],
                "v2": (
                    f"v1's {len(kept)} items with every intermediate >= {INTER_MIN} kept "
                    f"byte-identical (plus the mc block); the {len(dropped)} with an "
                    f"intermediate < {INTER_MIN} replaced depth for depth "
                    f"({N_REPLACE[2]} depth-2 + {N_REPLACE[3]} depth-3) by new seed-last "
                    f"plain chains whose intermediates are all in {INTER_MIN}..{INTER_MAX}, "
                    "strict-gated, round-robin over step-kind tuples"
                ),
                "dropped_v1": dropped,
            },
            "mc": {
                "n_options": mcopt.N_OPTIONS,
                "seed": mcopt.SEED,
                "rules": "wsbench.evals.chain_intermediates.options (never start / answer / "
                "literal / other gold; <= 2 error-path values; 2-3 other items' "
                "intermediates in band gold//2..2*gold+5; seeded fill; sorted-rank balance "
                "<= 20%); cannot-tell is appended LAST at judge time",
            },
            "read": (
                "from the last token of the start number through the end of the chat render "
                "(full); the render's final token, the assistant onset (lite); layers: GRID or "
                "any requested set"
            ),
        }
    )
    V2.write_text(json.dumps({**header, "items": items}, indent=1, ensure_ascii=False) + "\n")
    ranks = Counter(mcopt.sorted_rank(s) for it in items for s in it["mc"])
    log = {
        "n_candidates": len(cands),
        "n_graded": len(graded),
        "n_passed": {d: sum(1 for it in passed if it["depth"] == d) for d in (2, 3)},
        "pass_rate_by_depth": {
            d: sum(1 for it in passed if it["depth"] == d)
            / max(1, sum(1 for k in graded if cands[k]["depth"] == d))
            for d in (2, 3)
        },
        "fail_reasons": dict(
            Counter(
                "greedy" if not g["greedy_ok"] else "leak" if g["n_leaks"] else "sampled"
                for g in graded.values()
                if not g["ok"]
            )
        ),
        "replacements": [
            {"name": it["name"], "depth": it["depth"], "kinds": it["kinds"], **graded[it["name"]]}
            for d in (2, 3)
            for it in chosen[d]
        ],
        "dropped_v1": dropped,
        "sorted_rank_counts": dict(sorted(ranks.items())),
        "intermediates_lt_10": sum(1 for it in items for v in it["intermediates"] if v < 10),
    }
    if a.gate_log:
        Path(a.gate_log).write_text(json.dumps({"graded": graded, **log}, indent=1))
    print(json.dumps({k: v for k, v in log.items() if k != "replacements"}, indent=1))
    print(f"[freeze] {len(items)} items -> {V2}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates")
    c.add_argument("--out", required=True)
    c.add_argument("--n-per-depth", type=int, default=400)
    c.add_argument("--seed", type=int, default=2)
    r = sub.add_parser("requests")
    r.add_argument("--candidates", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--limit", type=int, default=0, help="smoke: half depth-2, half depth-3")
    f = sub.add_parser("freeze")
    f.add_argument("--candidates", required=True)
    f.add_argument("--samples", required=True)
    f.add_argument("--gate-log", default="")
    a = ap.parse_args()
    {"candidates": cmd_candidates, "requests": cmd_requests, "freeze": cmd_freeze}[a.cmd](a)


if __name__ == "__main__":
    main()

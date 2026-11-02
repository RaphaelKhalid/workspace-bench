"""Deterministic generators for the families whose items are constructed, not written: the
original construction rules (vendored from global-workspace), with each tier's knobs as
parameters. ``python -m wsbench.adapt generate model=<m> family=<f> tier=<t> n=<n>``."""

import math
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- chain_intermediates
# global-workspace scripts/olens_suite/chain_intermediates/gen_chain.py (seed-last chains), plain
# steps only: the bank of record dropped its single conditional item.

CHAIN_LAST = (
    "Apply the steps below, in order, to the starting number given at the end.\n"
    "{steps}\n"
    "The starting number is {start}. What is the final number? "
    "Reply with only the final number, nothing else."
)
CHAIN_FIRST = (
    "Start with the number {start} and apply the steps below, in order.\n"
    "{steps}\n"
    "What is the final number? Reply with only the final number, nothing else."
)


def _chain_step(kind: str, rng: random.Random, n_max: int) -> dict[str, Any]:
    if kind in ("add", "sub"):
        n = rng.randint(2, n_max)
        return {"kind": kind, "n": n, "text": f"{'Add' if kind == 'add' else 'Subtract'} {n}."}
    return {
        "kind": kind,
        "text": {
            "double": "Double it.",
            "triple": "Multiply it by 3.",
            "halve_up": "Halve it, rounding up.",
            "halve_down": "Halve it, rounding down.",
        }[kind],
    }


def _chain_apply(step: dict[str, Any], x: int) -> int:
    k = step["kind"]
    return {
        "add": lambda: x + step.get("n", 0),
        "sub": lambda: x - step.get("n", 0),
        "double": lambda: 2 * x,
        "triple": lambda: 3 * x,
        "halve_up": lambda: math.ceil(x / 2),
        "halve_down": lambda: x // 2,
    }[k]()


def _literals(text: str) -> set[int]:
    return {int(m) for m in re.findall(r"\d+", text)}


def _chain_distractors(v: int, start: int, answer: int, forbid: set[int], lits: set[int]):
    pool: list[int] = []

    def push(c: int, gold_ok: bool = False) -> None:
        if 1 <= c <= 80 and c != v and c not in pool and (gold_ok or c not in forbid):
            pool.append(c)

    push(start, True)
    push(answer, True)
    for c in sorted(lits - {start}):
        if len(pool) < 4:
            push(c)
    delta = 1
    while len(pool) < 4:
        push(v - delta)
        if len(pool) < 4:
            push(v + delta)
        delta += 1
    return pool[:4]


def chain(rng: random.Random, knobs: dict[str, Any]) -> dict[str, Any] | None:
    depth = rng.choice(knobs.get("depths", [2, 3]))
    ops = knobs.get("ops", ["add", "sub", "double", "triple", "halve_up", "halve_down"])
    lo, hi = knobs.get("start", [2, 30])
    vmax = knobs.get("vmax", 80)
    steps = [_chain_step(rng.choice(ops), rng, knobs.get("n_max", 9)) for _ in range(depth)]
    start = rng.randint(lo, hi)
    vals, x = [], start
    for st in steps:
        x = _chain_apply(st, x)
        if not 1 <= x <= vmax:
            return None
        vals.append(x)
    inter, answer = vals[:-1], vals[-1]
    if len({start, *vals}) != depth + 1:
        return None
    text = "\n".join(s["text"] for s in steps)
    prompt = CHAIN_LAST.format(steps=text, start=start)
    first = CHAIN_FIRST.format(steps=text, start=start)
    lits = _literals(prompt) | _literals(first)
    if any(v in lits for v in vals):
        return None
    forbid = {start, *vals}
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
        "prompt_first": first,
        "literals": sorted(lits),
        "distractors": [_chain_distractors(v, start, answer, forbid, lits) for v in inter],
    }


# ---------------------------------------------------------------- relational_multihop
# global-workspace scripts/oracle_lens_evals/gen_relational_multihop.py: one professional + one
# kinship hop, never kinship x kinship, never boss + spouse; each scene is an a/b pair with the
# hops swapped (same tokens, different gold), which the judge's pair-consistency needs.

REL_PROFESSIONAL = [
    "landlord", "dentist", "boss", "coach", "tutor", "plumber", "neighbor", "barber",
    "lawyer", "mechanic", "doctor", "therapist",  # no "accountant": in the judge MC pool
]  # fmt: skip
REL_KINSHIP = ["sibling", "cousin", "parent", "spouse", "child"]
REL_BLOCKED = {("boss", "spouse")}
REL_NAMES = [
    "Avery", "Sam", "Riley", "Jordan", "Casey", "Quinn", "Morgan", "Taylor", "Devon", "Rowan",
    "Sage", "Lee", "Kit", "Remy", "Blake", "Alex", "Charlie", "Drew", "Emerson", "Finley",
    "Harper", "Jules", "Kai", "Noor", "Reese", "Skyler", "Hayden", "Parker", "Elliot", "Frankie",
    "Marlowe", "Dakota", "Emery", "Rory", "Shiloh", "Tatum", "Sawyer", "Sasha", "Aubrey",
    "Bellamy", "Campbell", "Denver", "Ellis", "Gray", "Hollis", "Indigo", "Jem", "Lennox",
]  # fmt: skip


def relational_scene(rng: random.Random, knobs: dict[str, Any]) -> list[dict[str, Any]] | None:
    pro = rng.choice(knobs.get("professional", REL_PROFESSIONAL))
    kin = rng.choice(knobs.get("kinship", REL_KINSHIP))
    if (pro, kin) in REL_BLOCKED:
        return None
    p1, p2, p3 = rng.sample(knobs.get("names", REL_NAMES), 3)
    key = f"{p1}-{p2}-{p3}-{pro}-{kin}"
    out = []
    for suffix, r1, r2 in (("a", pro, kin), ("b", kin, pro)):
        story = f"{p1}'s {r1} is {p2}. {p2}'s {r2} is {p3}."
        out.append(
            {
                "scene_key": key,
                "stimulus": f"{story} In other words, {p3} is {p1}'s",
                "names": [p1, p2, p3],
                "hop1": r1,
                "hop2": r2,
                "gold": f"{r1}'s {r2}",
                "gold_alt": f"{r2} of {p1}'s {r1}",
                "flipped": f"{r2}'s {r1}",
                "_suffix": suffix,
            }
        )
    return out


# ---------------------------------------------------------------- arithmetic_intermediates


def gen_arith_variants() -> list[str]:
    from .gen_arith import STEPS

    return sorted(STEPS)


def arithmetic(rng: random.Random, knobs: dict[str, Any]) -> dict[str, Any] | None:
    from . import gen_arith
    from .store import original_bank

    header, items = original_bank("arithmetic_intermediates")
    ranges = knobs.get("ranges") or gen_arith.ranges_from_bank(items)
    variants = [v for v in (knobs.get("only") or sorted(ranges)) if v in ranges]
    if not variants:
        return None
    variant = rng.choice(variants)
    return gen_arith.build(variant, rng, ranges[variant], header)


# ---------------------------------------------------------------- registry


@dataclass(frozen=True)
class Tier:
    name: str
    knobs: dict[str, Any]
    change: str  # one line for report.json: what this tier made easier


@dataclass(frozen=True)
class Generator:
    family: str
    build: Callable[[random.Random, dict[str, Any]], dict[str, Any] | None]
    tiers: list[Tier] = field(default_factory=list)
    dedupe_key: str = "prompt"
    supports: frozenset[str] = frozenset()  # quota values it can build ("" = all)
    id_key: str = "name"  # the bank's id field ("id" for the plain-list banks)
    pair_key: str = ""  # items built together share this key (the scene of an a/b pair)
    quota_key: str = ""  # keep the original bank's mix over this field (arithmetic: variant)


GENERATORS: dict[str, Generator] = {
    "chain_intermediates": Generator(
        "chain_intermediates",
        chain,
        [
            Tier("t0", {"depths": [2, 3]}, "original rules (depth 2-3, six step kinds)"),
            Tier(
                "t1",
                {"depths": [2], "ops": ["add", "sub", "double"]},
                "depth 2 only; add/subtract 2-9 and double",
            ),
            Tier(
                "t2",
                {"depths": [2], "ops": ["add", "sub"], "n_max": 5, "start": [2, 15], "vmax": 40},
                "depth 2; add/subtract 2-5 only; start 2-15",
            ),
        ],
    ),
    "relational_multihop": Generator(
        "relational_multihop",
        relational_scene,
        [
            Tier("t0", {}, "original rules (13 professional x 5 kinship relations)"),
            Tier(
                "t1",
                {
                    "professional": ["boss", "doctor", "neighbor", "landlord", "coach", "dentist"],
                    "kinship": ["sibling", "parent", "child"],
                },
                "the commonest relation words only (6 professional x sibling/parent/child)",
            ),
        ],
        dedupe_key="scene_key",
        id_key="id",
        pair_key="scene",
    ),
    "arithmetic_intermediates": Generator(
        "arithmetic_intermediates",
        arithmetic,
        [
            Tier("t0", {}, "the bank's own operand ranges per variant"),
            Tier(
                "t1", {"ranges": "T1"}, "smaller operands (2-digit products, 2-digit differences)"
            ),
            Tier("t2", {"ranges": "T2"}, "single-digit factors, sums and differences under 50"),
        ],
        dedupe_key="expr",
        quota_key="variant",
        supports=frozenset(gen_arith_variants()),  # every variant of the bank of record
    ),
}


def generate(
    family: str,
    tier: str,
    n: int,
    seed: int,
    exclude: set[str],
    only: list[str] | None = None,
) -> list[dict]:
    """``n`` new items at ``tier``, none whose dedupe key is in ``exclude``; ``only`` limits a
    quota family to the values still short (arithmetic: the variants below their count)."""
    gen = GENERATORS[family]
    t = next((x for x in gen.tiers if x.name == tier), None)
    if t is None:
        raise SystemExit(f"{family} has no tier {tier!r}: {[x.name for x in gen.tiers]}")
    if isinstance(t.knobs.get("ranges"), str):
        from . import gen_arith

        t = Tier(t.name, {**t.knobs, "ranges": getattr(gen_arith, t.knobs["ranges"])}, t.change)
    if only:
        t = Tier(t.name, {**t.knobs, "only": only}, t.change)
    rng = random.Random(f"{family}:{tier}:{seed}")
    out: list[dict] = []
    seen = set(exclude)
    tries = groups = 0
    while len(out) < n and tries < 200 * n:
        tries += 1
        built = gen.build(rng, t.knobs)
        group = built if isinstance(built, list) else [built] if built else []
        if not group or group[0][gen.dedupe_key] in seen:
            continue
        seen.add(group[0][gen.dedupe_key])
        base = f"{family.split('_')[0]}-{tier}-s{seed}-{groups:04d}"
        groups += 1
        for it in group:  # a scene's a/b pair is atomic: same base id, kept or dropped together
            it[gen.id_key] = base + (f"-{it.pop('_suffix')}" if "_suffix" in it else "")
            if gen.pair_key:
                it[gen.pair_key] = base
            knobs = t.knobs
            if gen.quota_key and isinstance(knobs.get("ranges"), dict):
                knobs = {"ranges": knobs["ranges"].get(it.get(gen.quota_key), {})}
            adapt = {"origin": "generated", "tier": tier, "knobs": knobs, "change": t.change}
            it["adapt"] = adapt
            out.append(it)
    return out


# ---------------------------------------------------------------- what changed, measured


def _share(items: list[dict], pred) -> str:
    return f"{round(100 * sum(map(pred, items)) / max(1, len(items)))}%"


PROFILES: dict[str, list[tuple[str, Callable[[dict], bool]]]] = {
    "chain_intermediates": [
        ("depth 3", lambda i: i.get("depth") == 3),
        ("has a halving step", lambda i: any("halve" in k for k in i.get("kinds", []))),
        ("has x3", lambda i: "triple" in i.get("kinds", [])),
    ],
    "arithmetic_intermediates": [
        ("structural role", lambda i: i.get("role") == "structural"),
        ("first step >= 100", lambda i: abs(float(i["intermediates"][0])) >= 100),
    ],
    "relational_multihop": [
        (
            "kinship hop is sibling/parent/child",
            lambda i: {i.get("hop1"), i.get("hop2")} & {"sibling", "parent", "child"} != set(),
        ),
    ],
}


def describe(family: str, original: list[dict], adapted: list[dict]) -> str:
    """One line for report.json: the tiers the adapted bank's new items came from and, where the
    family has a profile, how its difficulty moved against the original bank."""
    tiers = sorted({(i.get("adapt") or {}).get("tier") for i in adapted} - {None})
    parts = [f"new items from {', '.join(tiers)}"] if tiers else ["original items only"]
    for label, pred in PROFILES.get(family, []):
        parts.append(f"{label}: {_share(original, pred)} -> {_share(adapted, pred)}")
    return "; ".join(parts)

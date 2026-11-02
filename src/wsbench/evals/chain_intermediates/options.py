"""The frozen multiple-choice options of bank v2 (plan 0038 C5): for every intermediate slot,
eight integers (the gold and seven distractors) in a seeded order. ``mc.options_with_cannot``
appends "cannot tell from the readout" LAST at judge time; it is never stored or shuffled in.

Distractor rules for slot k of an item (in priority order):

1. never the item's start or answer, a prompt literal (``literals``), another gold intermediate
   of the item, or the gold itself (so slot 2's gold can never earn slot-1 credit);
2. at most two error-path values from the item's ``distractors`` (the untaken branch or an
   off-by-one value, after rule 1), so a readout that computes the chain wrongly picks one;
3. two or three intermediates of OTHER items in the same magnitude band
   (``gold // 2 .. 2 * gold + 5``), like arithmetic's ``null_set``;
4. a seeded uniform fill from the same band (widened to 1..99 only when the band runs short);
5. balance: over the bank, the gold's rank in the SORTED option list is spread, no sorted rank
   holding more than 20% of slots (a "pick the median" heuristic gains nothing).

Pure and seeded: the same items give the same options."""

import random
from collections.abc import Sequence
from typing import Any

from wsbench.mc import seed_int, seeded_shuffle

N_OPTIONS = 8
VMIN, VMAX = 1, 99
MAX_ERROR_PATH = 2
SEED = "chain-v2"
MAX_RANK_SHARE = 0.20


def band(gold: int) -> tuple[int, int]:
    """The magnitude band of a slot's distractors (rules 3-4), clipped to 1..99."""
    return max(VMIN, gold // 2), min(VMAX, 2 * gold + 5)


def forbidden(item: dict[str, Any]) -> set[int]:
    """Rule 1: the values a distractor of ANY slot of ``item`` may never be."""
    out = {int(item["start"]), int(item["answer"])}
    out |= {int(v) for v in item.get("literals", [])}
    out |= {int(v) for v in item["intermediates"]}
    return out


def error_path(item: dict[str, Any], slot: int) -> list[int]:
    """The slot's error-path values: its frozen ``distractors`` minus the rule-1 values."""
    ds = item.get("distractors") or []
    if slot >= len(ds):
        return []
    bad = forbidden(item)
    out: list[int] = []
    for v in ds[slot]:
        if v is not None and int(v) not in bad and VMIN <= int(v) <= VMAX and int(v) not in out:
            out.append(int(v))
    return out


def _feasible_ranks(gold: int, bad: set[int]) -> list[int]:
    below = sum(1 for v in range(VMIN, gold) if v not in bad)
    above = sum(1 for v in range(gold + 1, VMAX + 1) if v not in bad)
    return [r for r in range(N_OPTIONS) if r <= below and N_OPTIONS - 1 - r <= above]


def _slot_options(
    item: dict[str, Any], slot: int, rank: int, others: Sequence[int], rng: random.Random
) -> list[int]:
    """Seven distractors putting ``gold`` at sorted ``rank``; then the seeded order."""
    gold = int(item["intermediates"][slot])
    bad = forbidden(item)
    need = {"below": rank, "above": N_OPTIONS - 1 - rank}
    picked: list[int] = []

    def take(v: int) -> bool:
        side = "below" if v < gold else "above"
        if v == gold or v in bad or v in picked or not (VMIN <= v <= VMAX) or need[side] <= 0:
            return False
        picked.append(v)
        need[side] -= 1
        return True

    n_err = 0
    errs = error_path(item, slot)
    for v in errs:  # rule 2
        if n_err < MAX_ERROR_PATH and take(v):
            n_err += 1
    bad |= set(errs)  # an error-path value never re-enters through rules 3-4
    lo, hi = band(gold)
    pool = sorted({int(v) for v in others if lo <= int(v) <= hi})  # rule 3
    rng.shuffle(pool)
    want_other = rng.choice((2, 3))
    n_other = 0
    for v in pool:
        if n_other >= want_other:
            break
        n_other += take(v)
    fill = list(range(lo, hi + 1))  # rule 4
    rng.shuffle(fill)
    for v in fill:
        take(v)
    if need["below"] or need["above"]:  # the band ran short: widen to 1..99
        wide = list(range(VMIN, VMAX + 1))
        rng.shuffle(wide)
        for v in wide:
            take(v)
    if need["below"] or need["above"]:
        raise ValueError(f"{item.get('name')}: slot {slot} cannot hold gold at rank {rank}")
    return seeded_shuffle([gold, *picked], f"{SEED}|{item['name']}|{slot}")


def build_mc(items: Sequence[dict[str, Any]], seed: str = SEED) -> dict[str, list[dict[str, Any]]]:
    """``{item name: [{"slot", "gold", "options"}, ...]}`` for every intermediate slot of
    ``items``. The gold's sorted rank is assigned greedily to the least-used feasible rank (ties
    broken by the seed), so no rank exceeds :data:`MAX_RANK_SHARE` of the slots."""
    rng = random.Random(seed_int(seed))
    all_inter = [(it["name"], int(v)) for it in items for v in it["intermediates"]]
    counts = [0] * N_OPTIONS
    out: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        slots: list[dict[str, Any]] = []
        for k, g in enumerate(it["intermediates"]):
            gold = int(g)
            feas = _feasible_ranks(gold, forbidden(it) - {gold})
            low = min(counts[r] for r in feas)
            rank = rng.choice([r for r in feas if counts[r] == low])
            counts[rank] += 1
            others = [v for name, v in all_inter if name != it["name"]]
            opts = _slot_options(it, k, rank, others, rng)
            slots.append({"slot": k, "gold": gold, "options": opts})
        out[it["name"]] = slots
    return out


def sorted_rank(slot: dict[str, Any]) -> int:
    """The gold's 0-based rank in the slot's options sorted ascending."""
    return sorted(slot["options"]).index(int(slot["gold"]))


def check_slot(item: dict[str, Any], slot: dict[str, Any]) -> list[str]:
    """The rule violations of one frozen slot (empty = valid)."""
    probs: list[str] = []
    opts = [int(v) for v in slot["options"]]
    gold = int(slot["gold"])
    k = int(slot["slot"])
    if len(opts) != N_OPTIONS or len(set(opts)) != N_OPTIONS:
        probs.append("not 8 distinct options")
    if opts.count(gold) != 1 or gold != int(item["intermediates"][k]):
        probs.append("gold missing or not the slot's intermediate")
    if any(not (VMIN <= v <= VMAX) for v in opts):
        probs.append("option outside 1..99")
    bad = (forbidden(item) - {gold}) & set(opts)
    if bad:
        probs.append(f"forbidden option(s) {sorted(bad)}")
    n_err = sum(1 for v in opts if v != gold and v in error_path(item, k))
    if n_err > MAX_ERROR_PATH:
        probs.append(f"{n_err} error-path values")
    return probs

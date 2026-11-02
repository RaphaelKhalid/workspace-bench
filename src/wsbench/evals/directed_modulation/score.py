"""directed_modulation: item-level rates over every judged (layer, position, sample) row."""

from collections.abc import Callable
from typing import Any

from wsbench.family import rate
from wsbench.llm import Spend
from wsbench.mc import form_in
from wsbench.mcjudge import base_config, is_subset
from wsbench.registry import JudgeArgs
from wsbench.results import FamilyResult, bootstrap_ci, completeness

from .prompts import N_DISTRACTORS, PROMPT_VERSION

CHANCE_LABEL = (
    f"no analytic floor for an any-row max (per call it is 1/{N_DISTRACTORS + 2}); the measured "
    "floor is the lucky-guessing baseline"
)

Pred = Callable[[dict[str, Any]], bool]


def _by_item(
    items: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    pred: Pred,
    incomplete: frozenset[str] = frozenset(),
) -> dict[str, bool | None]:
    """One tri-state per item: True when ANY judged row qualifies; None (undecided) when no row
    qualifies and a row is unjudged or a layer is missing (``incomplete``); else False. An item
    whose every cell is blank has no rows and is False."""
    out: dict[str, bool | None] = {
        it["id"]: (None if it["id"] in incomplete else False) for it in items
    }
    for v in verdicts:
        if out.get(v["item"]) is True:
            continue
        if not v["judged"]:
            out[v["item"]] = None
        elif pred(v):
            out[v["item"]] = True
    return out


STRICT: Pred = lambda v: v["pick"] == "gold" and v["basis"] == "content_bound"  # noqa: E731


# plan 0028 channel (the headline before plan 0035): gold engaged as content OR named while
# narrating the task
def present_hit(v: dict[str, Any]) -> bool:
    return v["pick"] == "gold" and v["basis"] in ("content_bound", "instruction_narration")


# plan 0035 C5 (Camila: "in directed modulation, if the concept is mentioned in any context it
# should count"): the headline is `expressed`, the gold picked with a verified quote, any basis
def hit(v: dict[str, Any]) -> bool:
    return v["pick"] == "gold"


def gold_forms(concept: str) -> tuple[str, ...]:
    """The listed surface forms of a concept: the word and its regular plurals."""
    c = concept.strip()
    forms = {c, c + "s", c + "es"}
    if c.endswith("y"):
        forms.add(c[:-1] + "ies")
    return tuple(sorted(forms))


def relative_only(v: dict[str, Any]) -> bool:
    """A gold pick whose verified quote holds no listed form of the gold (word or plural): the
    credit rests on a synonym, close relative, translation or description (plan 0035 C5)."""
    if not (v.get("judged") and v.get("pick") == "gold") or not v.get("options"):
        return False
    gold = v["options"][v["gold_position"] - 1]
    return not form_in(str(v.get("evidence") or ""), gold_forms(gold))


def summarize(
    items: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    incomplete: frozenset[str] = frozenset(),
    *,
    pass_at_1: bool = True,
) -> dict[str, Any]:
    """Item-level rates over decided items (an item with an unjudged row and no positive is
    undecided and left out). ``expressed`` = the gold concept picked at any row (the headline,
    plan 0035); ``present`` = picked AND engaged as content or named while narrating the task
    (the plan-0028 headline);
    ``content_bound`` = picked AND engaged as content (the pre-0028 headline);
    ``instruction_narration`` = picked only as narration of the task; ``distractor`` = a
    same-stratum wrong concept picked (the false-alarm channel); ``hinted`` = gold picked OR the
    gold concept's domain present;
    ``hint_distractor`` = a distractor's domain present (the hint channel's built-in null).
    ``white_bear`` is the per-pair think vs don't-think contrast on ``content_bound`` (leakage
    past a suppression, where narrating the prohibition is what it must exclude), over pairs
    whose both twins are decided. ``pass_at_1=False`` (summary mode, one row per item) omits
    the first-sample diagnostic."""
    channels: dict[str, Pred] = {
        "expressed": lambda v: v["pick"] == "gold",
        "present": present_hit,
        "content_bound": STRICT,
        "instruction_narration": lambda v: (
            v["pick"] == "gold" and v["basis"] == "instruction_narration"
        ),
        "distractor": lambda v: v["pick"] == "distractor",
        "hinted": lambda v: v["pick"] == "gold" or v["gold_overlap"],
        "hint_distractor": lambda v: v["distractor_overlap"],
    }
    flags = {name: _by_item(items, verdicts, pred, incomplete) for name, pred in channels.items()}
    sub_of = {it["id"]: str(it["subfamily"]) for it in items}

    def block(ids: list[str]) -> dict[str, Any]:
        keep = set(ids)
        out: dict[str, Any] = {"n_items": len(keep)}
        for name, f in flags.items():
            out[name] = rate(v for k, v in f.items() if k in keep and v is not None)
        # plan 0035 C5: how much of the headline the synonym / close-relative clause adds
        gold_rows = [v for v in verdicts if v["item"] in keep and v["judged"] and hit(v)]
        rel = [v for v in gold_rows if relative_only(v)]
        named = {v["item"] for v in gold_rows if not relative_only(v)}
        out["n_relative_only_hits"] = len(rel)
        out["n_items_relative_only"] = len({v["item"] for v in rel} - named)
        return out

    out: dict[str, Any] = {"overall": block(list(sub_of))}
    for sub in sorted(set(sub_of.values())):
        out[sub] = block([i for i, s in sub_of.items() if s == sub])
    strict = flags["content_bound"]
    pairs: dict[str, dict[str, bool | None]] = {}
    for it in items:
        if it["subfamily"] == "pair" and it.get("pair_id"):
            pairs.setdefault(str(it["pair_id"]), {})[str(it["polarity"])] = strict.get(it["id"])
    both = {
        p: d
        for p, d in pairs.items()
        if d.get("think") is not None and d.get("dont_think") is not None
    }
    if both:
        think = sum(bool(d["think"]) for d in both.values()) / len(both)
        dont = sum(bool(d["dont_think"]) for d in both.values()) / len(both)
        out["white_bear"] = {
            "n_pairs": len(both),
            "think_rate": think,
            "dont_think_rate": dont,
            "delta": think - dont,
        }
    picks: dict[str, int] = {}
    forms: dict[str, int] = {}
    for v in verdicts:
        if not v["judged"]:
            continue
        picks[v["pick"]] = picks.get(v["pick"], 0) + 1
        if v["pick"] == "gold":
            forms[v["form"]] = forms.get(v["form"], 0) + 1
    if pass_at_1:  # plan 0012 §5 (Neel B9): the headline rule on the first sample of every cell
        first = _by_item(items, [v for v in verdicts if v.get("sample", 0) == 0], hit, incomplete)
        out["pass_at_1"] = rate(v for v in first.values() if v is not None)
    out["picks"] = picks
    out["form_counts"] = forms
    out["n_voided"] = sum(1 for v in verdicts if v["judged"] and v["voided"])
    out["n_choice_invalid"] = sum(1 for v in verdicts if v["judged"] and v["choice_invalid"])
    return out


def score(
    items: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    *,
    args: JudgeArgs,
    kind: str,
    layers: list[int],
    n_cells: int,
    missing: list[tuple[str, int]],
    n_empty: int,
    skipped_rows: int,
    spend: Spend,
    summary: dict[str, Any] | None = None,
    n_items: int | None = None,
    pinned: bool | None = None,
    prompt_version: str | None = None,
    config_extra: dict[str, Any] | None = None,
    n_calls: int | None = None,
) -> FamilyResult:
    """The family result. Summary mode (plan 0020) passes ``summary`` (the digest's
    ``Collapse.extras()``, merged into ``extras.summary``), ``n_items`` (the empty rule's
    denominator), ``pinned`` (``digest.pinned``), the stamped ``prompt_version``, the digest
    ``config_extra`` and ``n_calls``; the denominator rule is unchanged."""
    incomplete = frozenset(i for i, _layer in missing)
    pinned = args.judge.pinned if pinned is None else pinned
    stats = summarize(items, verdicts, incomplete, pass_at_1=summary is None)
    if summary is not None:
        stats = {**stats, **summary}
    head = _by_item(items, verdicts, hit, incomplete)
    ids = [it["id"] for it in items]
    passes = [1.0 if p else 0.0 for p in head.values() if p is not None]
    n_unjudged = sum(1 for v in verdicts if not v["judged"])
    return FamilyResult(
        family="directed_modulation",
        metric="pass_rate",
        value=sum(passes) / len(passes) if passes else None,
        ci95=bootstrap_ci(passes) if passes else None,
        n_items=len(ids),
        higher_is_better=True,
        chance=None,
        chance_label=CHANCE_LABEL,
        complete=bool(verdicts)
        and completeness(
            pinned=pinned,
            subset=is_subset(args),
            n_expected=n_cells,
            n_missing=len(missing),
            n_unjudged=n_unjudged,
            n_empty=n_empty,
            n_items=n_items,
        ),
        pinned_instrument=pinned,
        config=base_config(
            args,
            PROMPT_VERSION if prompt_version is None else prompt_version,
            kind=kind,
            layers_judged=layers,
            n_distractors=N_DISTRACTORS,
            **(config_extra or {}),
        ),
        # a cell is one (item, layer, position) readout; a judge call is one non-empty sample
        counts={
            "n_expected_cells": n_cells,
            "n_missing_cells": len(missing),
            "n_unjudged_cells": n_unjudged,
            "n_empty_cells": n_empty,
            "skipped_rows": skipped_rows,
            "spend_usd": spend.usd,
        },
        extras={
            "headline": (
                "expressed (gold picked with a verified quote, any basis, any row; plan 0035)"
                if summary is None
                else "expressed (gold picked with a verified quote, any basis, on the item's "
                "digest; plan 0035)"
            ),
            "n_calls": len(verdicts) if n_calls is None else n_calls,
            "n_items_decided": len(passes),
            "n_items_undecided": len(ids) - len(passes),
            "summary": stats,
        },
        rows=verdicts,
    )

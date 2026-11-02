"""The single-token basic families: the bank judge with the any-layer item rule."""

from collections import defaultdict
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from wsbench import digest, reads
from wsbench.banks import exact_targets, item_targets, load_bank
from wsbench.basic.judge import CellKey, JudgeOutcome, judge_cells
from wsbench.basic.prompts import (
    DIGEST_TASK_NOTES,
    FAMILY_PROMPT_VERSIONS,
    FAMILY_RULES,
    forbidden_line,
    prompt_version_of,
    token_note_for,
)
from wsbench.cache import Cache
from wsbench.family import pass_rate_result, require_cells, tri_state
from wsbench.judge_config import JudgeConfig
from wsbench.llm import Spend
from wsbench.mcjudge import Preflighter, item_scope, with_readout_count
from wsbench.readouts import Cell
from wsbench.registry import EvalSpec, JudgeArgs, bank_path
from wsbench.results import FamilyResult
from wsbench.split import layer_protocols

GROUP = "basic"
# the families judged by a blind forced-choice bank judge instead of the free-text TARGETS judge
# below: basic_readout on basic/mcjudge_basic.py (plan 0053), multihop on basic/mcjudge_bank.py
# (plan 0048, per-family MCStrings). The two modules were written in parallel by the two family
# PRs and are kept side by side by the integration merge (unifying them is a follow-up).
MC_FAMILIES = frozenset({"basic_readout", "multihop"})
# the MC families on the MCStrings judge (basic/mcjudge_bank.py)
MC_BANK_FAMILIES = frozenset({"multihop"})
CHANCE_LABEL = "no analytic floor (free text); the prompt-only baseline is the measured floor"


def bank_family(
    name: str,
    title: str,
    *,
    n_items: int = 100,
    n_layers: int = 11,
    sources: str = "",
    not_in_macro: str = "",
    bank: Path | None = None,
    min_full_positions: int = 1,
    full_contiguous: bool = True,
    flat_types: tuple[str, ...] = (),
    task_note: str | None = None,
    item_task_notes: Callable[[], Mapping[str, str]] | None = None,
    targets_judge: bool = True,
) -> EvalSpec:
    """A bank-judge family. ``bank`` defaults to ``evals/<name>/items.json`` (a versioned bank:
    ``items_v<N>.json``, plan 0032 §2.12). ``min_full_positions`` defaults to 1: these plans read
    one position per layer until a family spec widens its read span. ``task_note`` overrides the
    shared ``DIGEST_TASK_NOTES`` line; ``targets_judge=False`` for a family on the blind MC judge
    (``MC_FAMILIES``), whose token note is the OPTIONS form."""
    bank = bank or Path("evals") / name / "items.json"
    return EvalSpec(
        name=name,
        title=title,
        group=GROUP,
        bank=bank,
        judge=JudgeConfig(prompt_version=prompt_version_of(name)),
        metric="pass_rate",
        higher_is_better=True,
        run=lambda args: run_family(args, name=name, bank=bank_path(name)),
        calls_per_arm=f"≈ {n_items * n_layers / 1000:.1f}k",
        sources=sources,
        not_in_macro=not_in_macro,
        min_full_positions=min_full_positions,
        full_contiguous=full_contiguous,
        task_note=DIGEST_TASK_NOTES.get(name, "") if task_note is None else task_note,
        item_task_notes=item_task_notes,
        flat_types=flat_types,
        # a TARGETS judge: no lone-option clause (review of PR #140); the MC judges hold options
        targets_judge=targets_judge and name not in MC_FAMILIES,
    )


def targets_of(item: dict[str, Any]) -> list[str]:
    return exact_targets(item_targets(item))


def group_cells(cells: list[Cell]) -> dict[CellKey, list[Cell]]:
    groups: dict[CellKey, list[Cell]] = defaultdict(list)
    for c in cells:
        groups[(c.id, c.layer)].append(c)
    return dict(groups)


def run_family(args: JudgeArgs, *, name: str, bank: Path) -> FamilyResult:
    if name in MC_BANK_FAMILIES:
        from wsbench.basic import mcjudge_bank

        return mcjudge_bank.run(args, name=name, bank=bank)
    if name in MC_FAMILIES:
        from wsbench.basic import mcjudge_basic

        return mcjudge_basic.run(args, name=name, bank=bank)
    _header, items = load_bank(bank)
    scope = item_scope(items, args)
    ids = [it["id"] for it in scope]
    targets = {it["id"]: targets_of(it) for it in scope}
    family_rule = FAMILY_RULES.get(name, "")
    forbidden = {it["id"]: forbidden_line(name, it) for it in scope}
    cells, rep = reads.load(args, name, ids=ids)
    layers = args.layers if args.layers is not None else rep.layers
    groups = group_cells(cells)
    expected = [(i, layer) for i in ids for layer in layers]
    missing = [k for k in expected if k not in groups]
    require_cells(name, missing, len(expected), args)
    if digest.summary_mode(args):
        return _run_summary(
            args,
            name=name,
            scope=scope,
            ids=ids,
            targets=targets,
            family_rule=family_rule,
            forbidden=forbidden,
            cells=cells,
            rep=rep,
            groups=groups,
            n_expected=len(expected),
            missing=missing,
        )

    spend = Spend()
    with Cache(args.out / "cells.jsonl") as cache:
        outcome = judge_cells(
            groups,
            targets,
            family_rule=family_rule,
            forbidden=forbidden,
            kind=rep.kind or "prose",
            judge=args.judge,
            cache=cache,
            spend=spend,
            preflight=Preflighter(args.dry_run),
            concurrency=args.concurrency,
            rpm=args.rpm,
            dry_run=args.dry_run,
            # None (the judge's shared default) unless the family has its own stamp (plan 0027)
            prompt_version=FAMILY_PROMPT_VERSIONS.get(name),
            token_note=token_note_for(name),
        )

    rows = [_item_row(i, layers, groups, targets[i], outcome) for i in ids]
    extras: dict[str, Any] = {"n_calls": outcome.n_calls}
    if not args.dry_run:  # plan 0012 §5: report-only, never the headline
        extras["layer_protocols"] = layer_protocols(
            {
                r["id"]: {
                    int(L): bool(v["expressed"])
                    for L, v in r["layers"].items()
                    if v.get("expressed") is not None
                }
                for r in rows
            },
            family=name,
            layers=layers,
        )
    result = pass_rate_result(
        name=name,
        args=args,
        prompt_version=prompt_version_of(name),
        rows=rows,
        cells=cells,
        rep=rep,
        # a cell is one (item, layer) judge call; empty = every sample at that layer is blank
        n_expected=len(expected),
        n_missing=len(missing),
        n_unjudged=outcome.n_unjudged,
        n_empty=outcome.n_empty,
        spend=spend,
        chance_label=CHANCE_LABEL,
        config_extra={"layers_judged": layers},
        extras=extras,
    )
    return with_readout_count(result, scope, cells)


def _run_summary(
    args: JudgeArgs,
    *,
    name: str,
    scope: list[dict[str, Any]],
    ids: list[str],
    targets: dict[str, list[str]],
    family_rule: str,
    forbidden: dict[str, str],
    cells: list[Cell],
    rep: Any,
    groups: dict[CellKey, list[Cell]],
    n_expected: int,
    missing: list[CellKey],
) -> FamilyResult:
    """Summary mode (plan 0020): every item's cells at every layer -> one digest -> one bank
    judge call. An item with no cells keeps the native missing path (undecided); an item with
    a missing layer and no pass is undecided; an unsummarized item is undecided."""
    by_item: dict[str, list[Cell]] = defaultdict(list)
    for (i, _layer), cs in groups.items():
        by_item[i].extend(cs)
    partial = {i for i, _layer in missing}
    spend = Spend()
    pre = Preflighter(args.dry_run)
    with Cache(args.out / "cells.jsonl") as cache:
        col = digest.collapse(
            name,
            {i: by_item[i] for i in ids if by_item.get(i)},
            args=args,
            cache=cache,
            spend=spend,
            preflight=pre.for_judge(digest.summarizer_judge(args, name)),
            task_note=DIGEST_TASK_NOTES.get(name, ""),
        )
        source_kind = digest.as_prose(rep)
        judged = {
            (i, digest.SUMMARY_LAYER): [c]
            for i, c in col.cells.items()
            if i not in col.unsummarized
        }
        outcome = judge_cells(
            judged,
            targets,
            family_rule=family_rule,
            forbidden=forbidden,
            kind="prose",
            judge=args.judge,
            cache=cache,
            spend=spend,
            preflight=pre,
            concurrency=args.concurrency,
            rpm=args.rpm,
            dry_run=args.dry_run,
            summary=col,
            summary_note=digest.summary_note(args, source_kind, name, targets=True),
            prompt_version=digest.prompt_version(prompt_version_of(name), args, name),
        )
    rows = []
    for i in ids:
        row = _item_row(i, [digest.SUMMARY_LAYER], judged, targets[i], outcome)
        row["n_missing"] = sum(1 for k in missing if k[0] == i)  # real layers, not the sentinel
        if i in col.unsummarized:
            row["n_unjudged"] = 1
        if i in col.cells:
            if i in partial and row["pass"] is False:
                row["pass"] = None  # a missing layer leaves a non-pass undecided, as native
            row.update(col.row(i))
        row.pop("earliest_layer", None)
        rows.append(row)
    result = pass_rate_result(
        name=name,
        args=args,
        prompt_version=digest.prompt_version(prompt_version_of(name), args, name),
        rows=rows,
        cells=cells,
        rep=rep,
        n_expected=n_expected,
        n_missing=len(missing),
        n_unjudged=outcome.n_unjudged + len(col.unsummarized),
        n_empty=outcome.n_empty,
        spend=spend,
        chance_label=CHANCE_LABEL,
        config_extra={**digest.config(args, source_kind, name), "layers_judged": args.layers},
        extras={"n_calls": outcome.n_calls, "summary": col.extras()},
        n_items=len(ids),
        pinned=digest.pinned(args, name),
    )
    return with_readout_count(result, scope, cells)


def _item_row(
    item_id: str,
    layers: list[int],
    groups: dict[CellKey, list[Cell]],
    targets: list[str],
    outcome: JudgeOutcome,
) -> dict[str, Any]:
    """``pass`` is True on any expressed layer, False when every expected layer was judged
    negative, and None (undecided) when nothing is expressed and a layer is missing or
    unjudged."""
    per_layer: dict[str, dict[str, Any]] = {}
    expressed_layers: list[int] = []
    n_unjudged = n_missing = 0
    for layer in layers:
        cells = groups.get((item_id, layer))
        if cells is None:
            n_missing += 1
            continue
        verdict = outcome.verdicts.get((item_id, layer))
        if verdict is None:
            n_unjudged += 1
        elif verdict.expressed:
            expressed_layers.append(layer)
        per_layer[str(layer)] = verdict.to_json() if verdict is not None else {"expressed": None}
    undecided = n_unjudged > 0 or n_missing > 0 or not per_layer
    return {
        "id": item_id,
        "targets": targets,
        "pass": tri_state(bool(expressed_layers), undecided),
        "earliest_layer": min(expressed_layers) if expressed_layers else None,
        "n_unjudged": n_unjudged,
        "n_missing": n_missing,
        "layers": per_layer,
    }

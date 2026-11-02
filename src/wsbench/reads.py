"""The ONE loading entry point of every family (plan 0032 §2.0, §2.6): readouts + the producer's
sidecar, the declared sampling rule, the layer-presence check, the ``reads=lite`` selection and
the ``reads=full`` span check.

``reads.load(args, family)`` replaces every direct ``load_readouts`` call in a family judge. In
this order it: loads the file (``ids`` / ``layers`` / ``positions`` filters); reads the sidecar
``<file>.meta.json``; applies the declared sampling (``readouts.normalize``); checks that every
requested layer is present; applies the lite selection under ``reads=lite``; and under
``reads=full`` checks every (item, layer) holds the family's full span. With a sidecar the
checks enforce (exit 2, or ``partial`` items under ``allow_missing``); a sidecar-less file (test
fixtures, cached v1 readouts) gets the same checks in report-only mode
(``extras.partial_ids_unenforced``, ``config.reads_checked = "no_sidecar"``). A ``prompt_only:``
reader (one cell per item) waives the selection, the span check and the plan guards."""

import functools
import hashlib
import json
import os
import weakref
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from wsbench import readplan
from wsbench.readouts import Cell, LoadReport, load_readouts, normalize, read_sidecar
from wsbench.readplan import FINAL, ReadSpec, lite_select
from wsbench.registry import BANK_FILE_ENV_PREFIX, BANK_ROOT_ENV, JudgeArgs

READS = ("full", "lite")
LITE_STAMP = "+reads-lite"
PROMPT_ONLY_PREFIX = "prompt_only:"
# keys never hashed into plan_sha: the lite site, the reads flag, the note, and (critique fix,
# 2026-10-30) the layers, so a file read at more layers than the plan (layers=all) is judged —
# guard (ii) checks the plan's layers are present instead
PLAN_SHA_EXCLUDE = ("lite_positions", "lite_layers", "reads", "note", "layers")


def fail(msg: str) -> Any:
    import sys

    print(msg, file=sys.stderr)
    raise SystemExit(2)


def mode(args: JudgeArgs) -> str:
    """``reads=full|lite`` from ``args.extra["reads"]`` (default ``full``); a bad value exits 2."""
    m = args.extra.get("reads", "full")
    if m not in READS:
        fail(f"reads={m!r}: expected full or lite")
    return m


def stamp(pv: str, m: str) -> str:
    """``pv + "+reads-lite"`` for a lite run (once), ``pv`` unchanged for full."""
    if m == "lite" and not pv.endswith(LITE_STAMP):
        return pv + LITE_STAMP
    return pv


def strip_reads(pv: str) -> str:
    """``pv`` without a trailing ``+reads-lite`` (prompt-only floors serve full and lite rows)."""
    return pv[: -len(LITE_STAMP)] if pv.endswith(LITE_STAMP) else pv


def _env_key() -> tuple[tuple[str, str], ...]:
    keys = [BANK_ROOT_ENV, readplan.NO_NOCOT_ENV]
    keys += [k for k in os.environ if k.startswith(BANK_FILE_ENV_PREFIX)]
    return tuple(sorted((k, os.environ.get(k, "")) for k in keys))


@functools.lru_cache(maxsize=64)
def _specs(family: str, _env: tuple[tuple[str, str], ...]) -> dict[str, ReadSpec]:
    return {s.id: s for s in readplan.plan(family, layers=None)}


def specs(family: str) -> dict[str, ReadSpec]:
    """``{item id: ReadSpec}`` of the family's plan of record (no tokenizer, no GPU; cached per
    bank environment). ``$WSB_LAYERS`` is ignored here: the judge's plan is the family's grid."""
    saved = os.environ.pop(readplan.LAYERS_ENV, None)
    try:
        return _specs(family, _env_key())
    finally:
        if saved is not None:
            os.environ[readplan.LAYERS_ENV] = saved


def _clean_row(row: Mapping[str, Any]) -> dict[str, Any]:
    d = {k: v for k, v in row.items() if k not in PLAN_SHA_EXCLUDE}
    if isinstance(d.get("extra"), dict):
        d["extra"] = {k: v for k, v in d["extra"].items() if k != "reads"}
        if not d["extra"]:
            d.pop("extra")
    return d


def plan_sha_rows(rows: Iterable[Mapping[str, Any]]) -> str:
    """sha256 over plan rows as ``wsbench plan`` writes them (each row's keys sorted; the
    ``PLAN_SHA_EXCLUDE`` keys dropped). The producer's plan-file mode hashes its input with it."""
    h = hashlib.sha256()
    for row in rows:
        h.update(json.dumps(_clean_row(row), sort_keys=True, ensure_ascii=False).encode())
        h.update(b"\n")
    return h.hexdigest()


def plan_sha(family: str) -> str:
    """``plan_sha_rows`` of ``readplan.plan(family)``'s rows (the producer imports this, so the
    producer's and the judge's hashes agree by construction). Layers are not hashed."""
    return plan_sha_rows(s.row() for s in readplan.plan(family, layers=None))


# ---------------------------------------------------------------- selection and span check


def _by_item_layer(cells: Iterable[Cell]) -> dict[tuple[str, int], list[Cell]]:
    out: dict[tuple[str, int], list[Cell]] = defaultdict(list)
    for c in cells:
        out[(c.id, c.layer)].append(c)
    return out


def is_prompt_only(reader: str) -> bool:
    return reader.startswith(PROMPT_ONLY_PREFIX)


def select(
    cells: Sequence[Cell],
    specs: Mapping[str, ReadSpec],
    mode: str,
    *,
    reader: str = "",
    declared: str | None = None,
) -> list[Cell]:
    """The cells a ``reads`` mode judges: identity under ``full`` (and for a ``prompt_only:``
    reader); under ``lite`` each item's ``lite_positions`` rule over its positions at each layer,
    at its ``lite_layers`` (an item without a plan row: ``final_token``). Identity, too, for a
    file whose sidecar declares ``reads=lite`` (``declared``): the producer already applied the
    rule, and the rule is not idempotent (``offset_from_end`` over its own single output keeps
    nothing), so it is never applied twice (review of PR #140)."""
    if mode == "full" or is_prompt_only(reader) or declared == "lite":
        return list(cells)
    keep: set[tuple[str, int, int]] = set()
    for (iid, layer), cs in _by_item_layer(cells).items():
        sp = specs.get(iid)
        rule = sp.lite_positions if sp is not None else FINAL
        if sp is not None and sp.lite_layers is not None and layer not in sp.lite_layers:
            continue
        for p in lite_select([c.pos for c in cs], rule):
            keep.add((iid, layer, p))
    return [c for c in cells if (c.id, c.layer, c.pos) in keep]


def _span_ok(positions: Sequence[int], min_positions: int, contiguous: bool) -> bool:
    ps = sorted(set(positions))
    if len(ps) < min_positions:
        return False
    return not contiguous or ps[-1] - ps[0] + 1 == len(ps)


def check_full(
    cells: Sequence[Cell],
    specs: Mapping[str, ReadSpec],
    *,
    min_positions: int,
    contiguous: bool,
    allow_missing: bool,
    reader: str = "",
) -> set[str]:
    """The partial item ids of a ``reads=full`` run. Per (item, layer) the positions must be ONE
    contiguous run (ending at the item's max position) of length >= ``min_positions``
    (``contiguous=False``: just the count). A file whose every (item, layer) holds exactly one
    position, for a family that needs more, exits 2 (it looks like a lite file). Any other
    violation exits 2 naming the first offender unless ``allow_missing`` (then those items are
    returned as partial). A ``prompt_only:`` reader is waived (empty set)."""
    if is_prompt_only(reader) or not cells:
        return set()
    groups = _by_item_layer(cells)
    if min_positions > 1 and all(len({c.pos for c in cs}) == 1 for cs in groups.values()):
        fail(
            "reads=full but the file has 1 position per cell; this looks like a lite file — "
            "use reads=lite"
        )
    bad: set[str] = set()
    first: tuple[str, int] | None = None
    for (iid, layer), cs in sorted(groups.items()):
        if not _span_ok([c.pos for c in cs], min_positions, contiguous):
            bad.add(iid)
            first = first or (iid, layer)
    if bad and not allow_missing:
        assert first is not None
        need = f"one contiguous run of >= {min_positions}" if contiguous else f">= {min_positions}"
        fail(
            f"reads=full: item {first[0]} at L{first[1]} does not hold its full span ({need} "
            f"positions); {len(bad)} item(s) partial (allow_missing=True judges them as partial)"
        )
    return bad


def lite_rule_of(specs: Mapping[str, ReadSpec], ids: Collection[str] | None = None) -> str:
    """The lite rule(s) of the plan rows (of ``ids``), as one canonical JSON string: what a
    ``reads=lite`` result stamps as ``config.lite_rule`` (late fix 2026-10-30: the frozen lite
    rule is part of the lite instrument, and ``scripts/audit_run.py`` checks it)."""
    rules = {
        json.dumps({"positions": sp.lite_positions, "layers": sp.lite_layers}, sort_keys=True)
        for iid, sp in specs.items()
        if ids is None or iid in ids
    }
    return json.dumps([json.loads(r) for r in sorted(rules)], sort_keys=True)


def plan_layers_missing(
    cells: Sequence[Cell], specs: Mapping[str, ReadSpec], mode: str
) -> dict[str, list[int]]:
    """Guard (ii): per item, the plan layers (``lite_layers`` under lite) absent from the file.
    Layers beyond the plan are fine (every present layer is judged)."""
    have: dict[str, set[int]] = defaultdict(set)
    for c in cells:
        have[c.id].add(c.layer)
    out: dict[str, list[int]] = {}
    for iid, got in have.items():
        sp = specs.get(iid)
        if sp is None:
            continue
        want = sp.lite_layers if mode == "lite" and sp.lite_layers is not None else sp.layers
        miss = sorted(set(want) - got)
        if miss:
            out[iid] = miss
    return out


# ---------------------------------------------------------------- load


def _spec_of(family: str) -> Any:
    from wsbench import registry

    try:
        return registry._spec_for_bank(family)  # also when the registry was emptied
    except SystemExit:
        return None


def load(
    args: JudgeArgs,
    family: str,
    path: Path | None = None,
    *,
    ids: Collection[str] | None = None,
    positions: Mapping[str, Collection[int]] | None = None,
) -> tuple[list[Cell], LoadReport]:
    """Every family's loader (module docstring). The report is also remembered beside ``args``
    (``report_of(args)``) so ``mcjudge.base_config`` and the runner stamp ``config.reads``,
    ``sampling``, ``sampling_source``, ``reader``, ``reads_checked`` and ``layers_judged``."""
    path = Path(path or args.readouts)
    m = mode(args)
    cells, rep = load_readouts(path, ids=ids, layers=args.layers, positions=positions)
    meta = read_sidecar(path)
    rep.meta = meta
    rep.reads = m
    rep.layers_requested = None if args.layers is None else sorted(set(args.layers))
    reader = str((meta or {}).get("reader") or "")
    rep.reader = reader
    # sampling: override > declared > default (never inferred from bullet shape)
    over = args.extra.get("sampling")
    if over:
        sampling, source = over, "override"
    elif meta is not None and meta.get("sampling"):
        sampling, source = str(meta["sampling"]), "declared"
    else:
        sampling = "tokens10" if rep.kind == "tokens" else "prose1"
        source = "default"
    normed, diag = normalize(cells, sampling)
    if source != "default":
        cells = normed
    # a sidecar-less file without sampling= is judged as it is (report-only, like the span
    # check): the counts say what the declared rule would trim; campaign files always declare
    rep.sampling, rep.sampling_source = sampling, source
    rep.n_samples_trimmed = diag["n_samples_trimmed"]
    rep.n_packed_ambiguous = diag["n_packed_ambiguous"]
    rep.n_cells_short = diag["n_cells_short"]
    prompt_only = is_prompt_only(reader)
    # guard (i): a declared lite file under a full run
    if meta is not None and meta.get("reads") == "lite" and m == "full":
        fail(f"{path}: file was produced reads=lite; judge it with reads=lite")
    # explicit layers=: every requested layer must be present (§2.1.7)
    if args.layers is not None and not prompt_only:
        got = {c.layer for c in cells}
        miss = sorted(set(args.layers) - got)
        if miss:
            if not args.allow_missing:
                fail(f"layers= asks for L{miss[0]}, file has {sorted(got)} ({path})")
            rep.layers_missing = miss
    spec = _spec_of(family)
    min_pos = int(getattr(spec, "min_full_positions", 2)) if spec is not None else 2
    contiguous = bool(getattr(spec, "full_contiguous", True)) if spec is not None else True
    if prompt_only:
        rep.reads_checked = "prompt_only"
        _attach(args, rep)
        return cells, rep
    # guard (iii): plan drift (never waived by allow_missing)
    if meta is not None and meta.get("plan_sha"):
        want = plan_sha(family)
        if str(meta["plan_sha"]) != want:
            fail(
                f"{path}: readouts were produced for a different plan (plan_sha "
                f"{str(meta['plan_sha'])[:12]} != {want[:12]})"
            )
    try:
        sp = specs(family)
    except (SystemExit, KeyError, OSError, ValueError):
        sp = {}
    enforce = meta is not None
    if m == "lite":
        rep.lite_rule = lite_rule_of(sp, {c.id for c in cells})
    declared = str(meta.get("reads") or "") if meta is not None else None
    for c in cells:  # before the selection: lite keeps every position's token for context
        if c.token is not None:
            rep.site_tokens.setdefault(c.id, {}).setdefault(c.pos, c.token)
    before = cells
    cells = select(cells, sp, m, reader=reader, declared=declared)
    if m == "lite" and before and not cells:
        # the rule kept nothing: a file that holds only the lite site, undeclared (a sidecar-less
        # toy file), would otherwise judge zero cells and report n items as plain negatives
        fail(
            f"{path}: reads=lite kept no readout (lite rule {rep.lite_rule!r} over the file's "
            "positions); a file produced at the lite site must declare reads=lite in its sidecar"
        )
    partial: set[str] = set()
    if m == "full":
        partial |= (
            check_full(
                cells,
                sp,
                min_positions=min_pos,
                contiguous=contiguous,
                allow_missing=args.allow_missing or not enforce,
            )
            if enforce
            else _report_only(cells, sp, min_pos, contiguous)
        )
    if args.layers is None:
        gaps = plan_layers_missing(cells, sp, m)
        if gaps and enforce and not args.allow_missing:
            iid = sorted(gaps)[0]
            fail(
                f"{path}: item {iid} lacks plan layer(s) {gaps[iid]} (layers=None judges the "
                "plan's layers; pass layers= to judge fewer)"
            )
        partial |= set(gaps)
    if enforce:
        rep.partial_ids = sorted(partial)
        rep.reads_checked = "sidecar"
    else:
        rep.partial_ids_unenforced = sorted(partial)
        rep.reads_checked = "no_sidecar"
    _attach(args, rep)
    return cells, rep


def _report_only(
    cells: Sequence[Cell], specs: Mapping[str, ReadSpec], min_pos: int, contiguous: bool
) -> set[str]:
    return {
        iid
        for (iid, _layer), cs in _by_item_layer(cells).items()
        if not _span_ok([c.pos for c in cs], min_pos, contiguous)
    }


_REPORTS: list[tuple[weakref.ref, LoadReport]] = []  # (args, the last load's report), weakly held


def _attach(args: JudgeArgs, rep: LoadReport) -> None:
    """Remember this run's load report beside ``args`` (not a JudgeArgs field, so
    ``JudgeArgs(**vars(args))`` keeps working). ``dataclasses.replace(args, judge=…)`` copies
    share ``args.extra`` and ``readouts``, so :func:`report_of` finds the report through them."""
    _REPORTS[:] = [(r, x) for r, x in _REPORTS if r() is not None and r() is not args]
    _REPORTS.append((weakref.ref(args), rep))


def report_of(args: JudgeArgs) -> LoadReport | None:
    """The report of the last ``reads.load`` on ``args`` (or on the args it was copied from)."""
    for r, rep in reversed(_REPORTS):
        a = r()
        if a is args:
            return rep
    for r, rep in reversed(_REPORTS):
        a = r()
        if a is not None and a.extra is args.extra and a.readouts == args.readouts:
            return rep
    return None


def config_stamps(args: JudgeArgs) -> dict[str, Any]:
    """The ``config`` keys a result carries from its load (``mcjudge.base_config`` and the
    runner call this)."""
    rep = report_of(args)
    m = mode(args)
    if rep is None:
        return {"reads": m, "layers_judged": args.layers}
    return {
        "reads": m,
        "sampling": rep.sampling,
        "sampling_source": rep.sampling_source,
        "reader": rep.reader,
        "reads_checked": rep.reads_checked,
        "layers_judged": rep.layers_requested if rep.layers_requested is not None else rep.layers,
        **({"lite_rule": rep.lite_rule} if m == "lite" else {}),
    }


def extras_of(args: JudgeArgs) -> dict[str, Any]:
    rep = report_of(args)
    if rep is None:
        return {}
    return {
        "partial_ids": rep.partial_ids,
        "partial_ids_unenforced": rep.partial_ids_unenforced,
        "layers_missing": rep.layers_missing,
        "n_samples_trimmed": rep.n_samples_trimmed,
        "n_packed_ambiguous": rep.n_packed_ambiguous,
        "n_cells_short": rep.n_cells_short,
    }


def incomplete(args: JudgeArgs) -> bool:
    """The load left items partial or requested layers missing (sidecar-enforced only)."""
    rep = report_of(args)
    return rep is not None and bool(rep.partial_ids or rep.layers_missing)

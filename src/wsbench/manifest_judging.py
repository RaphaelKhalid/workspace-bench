"""Strict readout coverage and cache isolation for manifest-defined evaluations."""

from collections.abc import Collection, Mapping

from wsbench.readouts import Cell, LoadReport, load_readouts
from wsbench.registry import JudgeArgs
from wsbench.results import FamilyResult


def manifest_positions(
    args: JudgeArgs, original: Mapping[str, Collection[int]]
) -> dict[str, list[int]]:
    if args.cell_manifest is None:
        return {i: list(ps) for i, ps in original.items()}
    selected = {it.id: it.positions for it in args.cell_manifest.family(args.family)}
    out = {}
    for i, ps in original.items():
        if i not in selected or not set(selected[i]) <= set(ps):
            raise SystemExit(
                f"{args.family}: manifest sites are outside the bank's judge sites: {i}"
            )
        out[i] = list(selected[i])
    return out


def load_judge_readouts(
    args: JudgeArgs,
    *,
    ids: Collection[str] | None = None,
    layers: Collection[int] | None = None,
    positions: Mapping[str, Collection[int]] | None = None,
) -> tuple[list[Cell], LoadReport]:
    if args.cell_manifest is None:
        return load_readouts(args.readouts, ids=ids, layers=layers, positions=positions)
    if args.allow_missing:
        raise SystemExit("allow_missing is forbidden for a manifest-defined evaluation")
    if args.layers is not None or layers is not None:
        raise SystemExit("derive a reader-specific manifest instead of overriding layers")
    entries = args.cell_manifest.family(args.family)
    expected = args.cell_manifest.expected(args.family)
    # Read the entire artifact without filtering: malformed, duplicate, foreign and missing
    # cells must fail before a judge can consume a shortened denominator.
    cells, rep = load_readouts(args.readouts)
    errors = {k: n for k, n in rep.skipped.items() if n}
    if errors:
        raise SystemExit(f"{args.family}: invalid manifest readout artifact: {errors}")
    present = {(c.id, c.layer, c.pos) for c in cells}
    missing, foreign = expected - present, present - expected
    if missing or foreign:
        raise SystemExit(
            f"{args.family}: manifest coverage mismatch: {len(missing)} missing, "
            f"{len(foreign)} foreign cells; first missing={sorted(missing)[:3]}, "
            f"first foreign={sorted(foreign)[:3]}"
        )
    tokens = {(it.id, p): t for it in entries for p, t in zip(it.positions, it.tokens, strict=True)}
    for c in cells:
        if c.token is None or c.token != tokens[(c.id, c.pos)]:
            raise SystemExit(f"{args.family}: read-site token mismatch or missing token: {c.key}")
    if ids is None and positions is not None:
        ids = positions.keys()
    if ids is not None:
        wanted = set(ids)
        known = {it.id for it in entries}
        if wanted - known:
            raise SystemExit(f"{args.family}: judge requested IDs outside manifest")
        cells = [c for c in cells if c.id in wanted]
    # Family-specific bank eligibility may validate the manifest, never filter it again.
    if positions is not None and any(
        c.id not in positions or c.pos not in positions[c.id] for c in cells
    ):
        raise SystemExit(f"{args.family}: judge position filter would discard manifest cells")
    # Manifest ordering is stable across a resume or a different producer batch order.
    order = {
        (it.id, layer, pos): (i, j, k)
        for i, it in enumerate(entries)
        for j, layer in enumerate(it.layers)
        for k, pos in enumerate(it.positions)
    }
    cells.sort(key=lambda c: order[(c.id, c.layer, c.pos)])
    rep.layers = sorted({c.layer for c in cells})
    rep.n_empty = sum(c.empty for c in cells)
    return cells, rep


def annotate_result(result: FamilyResult, args: JudgeArgs) -> FamilyResult:
    """Keep protocol execution status distinct from original-instrument completeness."""
    manifest = args.cell_manifest
    if manifest is None:
        return result
    entries = manifest.family(args.family)
    result.config["cell_manifest"] = {
        "sha256": manifest.fingerprint,
        "profile": manifest.metadata["profile"],
        "model": manifest.metadata["model"],
        "model_revision": manifest.metadata["model_revision"],
    }
    result.extras["manifest_readout_cells"] = sum(len(it.cells) for it in entries)
    result.extras["manifest_items"] = len(entries)
    result.extras["manifest_coverage_complete"] = True  # strict loader ran before scoring
    result.extras["judging_finished"] = (
        not args.dry_run
        and result.value is not None
        and result.counts.get("n_missing_cells") == 0
        and result.counts.get("n_unjudged_cells") == 0
        and not result.extras.get("n_items_without_readouts", 0)
    )
    result.extras["reference_judge_pinned"] = result.pinned_instrument
    result.extras["fidelity_validated"] = False
    # A position reduction is a new instrument even if its judge is the original model.
    # It must not enter the original benchmark's macro as an equivalent complete result.
    result.pinned_instrument = False
    result.complete = False
    return result

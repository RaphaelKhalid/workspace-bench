"""jlens_concept_pr: an AO arm's prose readouts scored against the frozen J-lens top-10.

Port of ``scripts/oracle_lens_evals/jlens_pr/{judge_openrouter,judge_pr,items}.py`` (the judge
of record) onto the shared client and cache. Three judged stages, one ``run_calls`` batch each:

* Stage A (concept split) on the family judge (Claude Opus 5.5 since plan 0023; the source ran
  it on DeepSeek-V4-Flash, see the README's instrument note): one call per cell with text,
  ``text = readouts.bulleted(samples)`` (the shared one-string join; the samples per cell are
  the declared sampling's, ``reads.load`` normalizes them);
* Stage B (per-token recall grades) on the judge: one call per CONTENT reference token per cell
  with concepts (junk tokens — U+FFFD fragments, special tags — are not content, plan 0042); the
  ``foil`` pass grades the same concepts against a seeded within-family derangement partner's
  tokens (keys ``:F..``) and runs by default;
* Stage P (per-concept precision, T = 0) on the judge: one call per 60-concept chunk with the
  cell's full content-token set; the ``pfoil`` pass (keys ``:Q..``, the family's floor) runs by
  default since plan 0042; ``opts=stage_p_foil=0`` turns it off, and the foil precision then
  reads ``None`` ("not measured"), never 0.0.

Layers (plan 0042 C3): with no ``layers=``, the judged layers are the file's layers that have a
reference J-lens file (the rest are listed in ``extras.layers_without_reference``); an explicit
``layers=`` naming a layer without a reference exits 2. ``opts=headline_layer=N`` picks the
headline layer (it must be judged).

A cell is (label, layer, eval position) — exactly one eval position per label per the manifest.
An ABSENT cell is missing (fatal without ``allow_missing=True``); a PRESENT-but-empty cell scores
as zero concepts ("lens silent") and counts in ``n_empty_cells``. A parser ``ValueError`` on any
stage is a reject: the result is cached as a failure and re-queued by the next run, never
partially scored. Keys are ``f"{cell.key}:A"``, ``:B{ti:02d}`` / ``:F{ti:02d}``,
``:P{ci:03d}`` / ``:Q{ci:03d}``.
"""

import json
import os
import random
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from wsbench import reads, registry
from wsbench.bpe import to_bytes
from wsbench.cache import Cache
from wsbench.judge_config import ResolvedJudge
from wsbench.llm import Spend
from wsbench.mcjudge import (
    Call,
    Preflighter,
    base_config,
    item_scope,
    run_calls,
    with_readout_count,
)
from wsbench.readouts import Cell, bulleted, expected_cells, missing_cells
from wsbench.registry import JudgeArgs
from wsbench.results import FamilyResult

from . import score
from .concept_pr import is_content_token
from .prompts import (
    CALL_VERSION,
    PROMPT_VERSION,
    STAGE_A_SCHEMA,
    STAGE_A_SYSTEM,
    STAGE_B_SCHEMA,
    STAGE_B_SYSTEM,
    STAGE_P_SCHEMA,
    STAGE_P_SYSTEM,
    function_word_grounded,
    parse_stage_a,
    parse_stage_b,
    parse_stage_p,
    render_stage_a,
    render_stage_b,
    render_stage_p,
    stage_p_chunks,
)

FAMILY = "jlens_concept_pr"
HEADLINE_LAYER = 44
FOIL_SEED = 0
MAX_TOKENS = 16000  # every stage: a 60-concept response echoes every concept back
STAGE_P_TEMPERATURE = 0.0
BANK_DIR = registry.REPO_ROOT / "evals" / FAMILY
REF_DIR = BANK_DIR / "gen-jlens-pr-jlens"


def bank_dir() -> Path:
    """The bank directory (``manifest.json`` + ``gen-jlens-pr-jlens/``). Precedence is the shared
    one (``registry.bank_path``): ``$WSB_BANK_FILE_JLENS_CONCEPT_PR`` (a ``manifest.json``; its
    directory is the bank) > ``$WSB_BANK_ROOT/jlens_concept_pr/`` for an adapted bank (the
    subject's own manifest and J-lens reference; an error if missing, never the 27B's — this
    family's bank is a directory, not ``<root>/<family>.json``) > the registered bank."""
    if os.environ.get(registry.BANK_FILE_ENV_PREFIX + FAMILY.upper()):
        return registry.bank_path(FAMILY).parent
    root = os.environ.get(registry.BANK_ROOT_ENV)
    if not root:
        return BANK_DIR  # == REPO_ROOT / SPEC.bank.parent
    base = Path(root) if Path(root).is_absolute() else registry.REPO_ROOT / root
    d = base / FAMILY
    if not (d / "manifest.json").exists():
        raise SystemExit(f"{registry.BANK_ROOT_ENV}={root} has no {FAMILY} bank ({d})")
    return d


def ref_dir() -> Path:
    return REF_DIR if bank_dir() == BANK_DIR else bank_dir() / "gen-jlens-pr-jlens"


STAGES = ("a", "b", "foil", "p", "pfoil")
STAGE_TAG = {"a": "A", "b": "B", "foil": "F", "p": "P", "pfoil": "Q"}


# ------------------------------------------------------------------ items.py (verbatim)


def bpe_display_to_text(tok: str) -> str:
    """Decodes a J-lens reference ``samples`` token (byte-level BPE display form, ``Ġ``/``▁``
    already a space) to text. The reference files are read here, not through the loader, so
    they are decoded here once; a part-of-a-character token becomes U+FFFD, as the frozen
    jlens-pr-v2 instrument has always rendered it (not ``decode_token``'s keep-as-written)."""
    return to_bytes(tok).decode("utf-8", errors="replace")


def foil_pairing(labels_by_group: Mapping[str, Sequence[str]], *, seed: int) -> dict[str, str]:
    """Seeded derangement inside each group (shuffle, then rotate by one)."""
    out: dict[str, str] = {}
    for gkey in sorted(labels_by_group):
        labels = list(labels_by_group[gkey])
        if len(labels) < 2:
            continue
        rng = random.Random(f"{seed}:{gkey}")
        rng.shuffle(labels)
        for i, lab in enumerate(labels):
            out[lab] = labels[(i + 1) % len(labels)]
    return out


# ------------------------------------------------------------------ bank


def load_manifest() -> dict[str, Any]:
    return json.loads((bank_dir() / "manifest.json").read_text(encoding="utf-8"))


def manifest_items(man: dict[str, Any]) -> list[dict[str, Any]]:
    """``{id, family, pos}`` per label (``id`` = label, ``pos`` = the one eval position)."""
    return [
        {"id": p["label"], "family": p["family"], "pos": int(p["eval_positions"][0])}
        for p in man["prompts"]
    ]


def reference_path(label: str, layer: int) -> Path:
    return ref_dir() / label / f"L{layer:03d}.jsonl"


def reference_tokens(label: str, layer: int, pos: int) -> list[str]:
    """The J-lens top-10 display strings at (label, layer, pos), decoded, unstripped
    (punctuation tokens must survive to be classified). ``[]`` when the row is absent."""
    path = reference_path(label, layer)
    for line in path.read_bytes().decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("pos") == pos:
            return [bpe_display_to_text(t) for t in row["samples"]]
    return []


def foil_map(items: Sequence[dict[str, Any]]) -> dict[str, str]:
    groups: dict[str, list[str]] = {}
    for it in items:
        groups.setdefault(it["family"], []).append(it["id"])
    return foil_pairing(groups, seed=FOIL_SEED)


def stage_key(cell_key: str, stage: str, idx: int | None = None) -> str:
    tag = STAGE_TAG[stage]
    if stage == "a":
        return f"{cell_key}:{tag}"
    if stage in ("b", "foil"):
        return f"{cell_key}:{tag}{idx:02d}"
    return f"{cell_key}:{tag}{idx:03d}"


def cell_of(key: str) -> str:
    """Strip the stage suffix: ``<cell key>``."""
    return key.rsplit(":", 1)[0]


def n_text_tokens(text: str) -> int:
    """Whitespace token count of the judged text (the length statistic reported per arm)."""
    return len(text.split())


def extract_judge(args: JudgeArgs) -> ResolvedJudge:
    """Stage A's judge: ``aux_models["extract"]`` if a family ever sets one, else the family
    judge itself (Camila, 2026-09-16: Stage A runs on the family judge like Stages B and P)."""
    model = args.aux_models.get("extract")
    if model is None or model == args.judge.model:
        return args.judge
    return ResolvedJudge(
        model=model, reasoning=None, pinned=args.judge.pinned, source=args.judge.source
    )


def judged_layers(
    args: JudgeArgs, file_layers: Sequence[int], labels: Sequence[str]
) -> tuple[list[int], list[int]]:
    """``(judged, without_reference)`` (plan 0042 C3). A layer is judgeable when every scoped
    label has a reference file at it. An explicit ``layers=`` list must be all judgeable (exit 2
    before any call); with no ``layers=`` the file's non-judgeable layers are dropped and listed
    (a 64-layer producer file runs without pre-filtering). No judgeable layer at all exits 2."""

    def ok(layer: int) -> bool:
        return all(reference_path(lab, layer).exists() for lab in labels)

    if args.layers:
        layers = sorted(set(args.layers))
        bad = [L for L in layers if not ok(L)]
        if bad:
            print(f"[{FAMILY}] no reference J-lens file for layers {bad} under {ref_dir()}")
            raise SystemExit(2)
        return layers, []
    layers = sorted(set(file_layers))
    judged = [L for L in layers if ok(L)]
    dropped = [L for L in layers if not ok(L)]
    if dropped:
        print(
            f"[{FAMILY}] WARNING: no reference J-lens file for file layers {dropped} under "
            f"{ref_dir()}: not judged (extras.layers_without_reference)"
        )
    if not judged:
        print(f"[{FAMILY}] no file layer {layers} has a reference J-lens file under {ref_dir()}")
        raise SystemExit(2)
    return judged, dropped


def headline_opt(args: JudgeArgs, layers: Sequence[int]) -> int | None:
    """``opts=headline_layer=N`` (must be a judged layer, else exit 2); ``None`` = the default
    rule (the single judged layer, else L44, else no headline)."""
    raw = args.extra.get("headline_layer")
    if raw in (None, ""):
        return None
    try:
        hl = int(str(raw))
    except ValueError:
        print(f"[{FAMILY}] headline_layer={raw!r}: not an integer")
        raise SystemExit(2) from None
    if hl not in layers:
        print(f"[{FAMILY}] headline_layer={hl} is not a judged layer {list(layers)}")
        raise SystemExit(2)
    return hl


def foil_on(args: JudgeArgs) -> bool:
    """The Stage-P foil (the family's floor) runs unless ``opts=stage_p_foil=0`` (plan 0042)."""
    return str(args.extra.get("stage_p_foil", "1")) != "0"


def _valid(parse: Callable[..., Any], *parse_args: Any) -> bool:
    try:
        parse(*parse_args)
    except (ValueError, TypeError):
        return False
    return True


# ------------------------------------------------------------------ the family run


def run(args: JudgeArgs) -> FamilyResult:
    items = manifest_items(load_manifest())
    scope = item_scope(items, args)
    family_of = {it["id"]: it["family"] for it in items}
    pos_of = {it["id"]: it["pos"] for it in items}
    positions = {it["id"]: [it["pos"]] for it in scope}
    cells, rep = reads.load(args, FAMILY, positions=positions)
    if rep.kind == "tokens" or rep.sampling == "tokens10":
        print(f"[{FAMILY}] judges prose readouts only (the J-lens is the reference, not an arm)")
        raise SystemExit(2)
    layers, no_ref = judged_layers(args, rep.layers, [it["id"] for it in scope])
    cells = [c for c in cells if c.layer in layers]
    rep.layers = layers  # the shared config.layers_judged stamp is the judged set
    headline = headline_opt(args, layers)
    expected = expected_cells(positions, layers)
    missing = missing_cells(cells, expected)
    print(
        f"[{FAMILY}] layers={layers} items={len(scope)} expected={len(expected)} "
        f"cells={len(cells)} missing={len(missing)} | skipped rows: {rep.skipped}",
        flush=True,
    )
    if missing:
        print(
            f"[{FAMILY}] missing cells (first 10): "
            + ", ".join(f"{i}__L{layer:03d}__p{p}" for i, layer, p in missing[:10])
        )
        if not args.allow_missing and not args.dry_run:
            raise SystemExit(2)
    fmap = foil_map(items)
    pfoil = foil_on(args)
    ref_cache: dict[tuple[str, int], list[str]] = {}

    def ref(label: str, layer: int) -> list[str]:
        k = (label, layer)
        if k not in ref_cache:
            ref_cache[k] = reference_tokens(label, layer, pos_of[label])
        return ref_cache[k]

    def partner(c: Cell) -> str | None:
        return fmap.get(c.id)

    spend = Spend()
    pre = Preflighter(args.dry_run)
    common: dict[str, Any] = {
        "cache": None,
        "spend": spend,
        "concurrency": args.concurrency,
        "rpm": args.rpm,
        "dry_run": args.dry_run,
    }
    a_judge = extract_judge(args)
    calls: dict[str, list[Call]] = {s: [] for s in STAGES}
    results: dict[str, dict[str, dict | None]] = {s: {} for s in STAGES}
    concepts: dict[str, list[str]] = {}
    texts: dict[str, str] = {}
    with Cache(args.out / "cells.jsonl") as cache:
        common["cache"] = cache
        # ---- Stage A: concepts of every cell with text
        for c in cells:
            if c.empty:
                continue
            text = bulleted(c.samples or ())
            texts[c.key] = text
            calls["a"].append(
                Call(
                    stage_key(c.key, "a"),
                    STAGE_A_SYSTEM,
                    render_stage_a(text),
                    {"cell": c.key, "stage": "a", "n_text_tokens": n_text_tokens(text)},
                )
            )
        results["a"] = run_calls(
            calls["a"],
            schema=STAGE_A_SCHEMA,
            judge=a_judge,
            prompt_version=CALL_VERSION,
            preflight=pre.for_judge(a_judge),
            validate=lambda call, r: _valid(parse_stage_a, r),
            max_tokens=MAX_TOKENS,
            **common,
        )
        for call in calls["a"]:
            r = results["a"].get(call.key)
            if r is not None:
                concepts[call.meta["cell"]] = parse_stage_a(r)
        # ---- Stage B + foil: one call per content reference token
        for c in cells:
            cs = concepts.get(c.key)
            if not cs:
                continue
            for stage in ("b", "foil"):
                src = c.id if stage == "b" else partner(c)
                if src is None:
                    continue
                content = [t for t in ref(src, c.layer) if is_content_token(t)]
                for ti, tok in enumerate(ref(src, c.layer)):
                    if not is_content_token(tok):
                        continue
                    calls[stage].append(
                        Call(
                            stage_key(c.key, stage, ti),
                            STAGE_B_SYSTEM,
                            render_stage_b(tok, cs, content),
                            {
                                "cell": c.key,
                                "stage": stage,
                                "token_idx": ti,
                                "token": tok,
                                "tokens": content,
                            },
                        )
                    )
        b_all = calls["b"] + calls["foil"]
        if b_all and not args.dry_run:
            got = run_calls(
                b_all,
                schema=STAGE_B_SCHEMA,
                judge=args.judge,
                prompt_version=CALL_VERSION,
                preflight=pre.for_judge(args.judge),
                validate=lambda call, r: _valid(parse_stage_b, r, concepts[call.meta["cell"]]),
                max_tokens=MAX_TOKENS,
                **common,
            )
            for stage in ("b", "foil"):
                results[stage] = {call.key: got.get(call.key) for call in calls[stage]}
        # ---- Stage P (+ pfoil): one call per 60-concept chunk with the full token set
        for c in cells:
            cs = concepts.get(c.key)
            if not cs:
                continue
            for stage in ("p", "pfoil"):
                if stage == "pfoil" and not pfoil:
                    continue
                src = c.id if stage == "p" else partner(c)
                if src is None:
                    continue
                toks = [t for t in ref(src, c.layer) if is_content_token(t)]
                if not toks:
                    continue
                for ci, (offset, part) in enumerate(stage_p_chunks(cs)):
                    calls[stage].append(
                        Call(
                            stage_key(c.key, stage, ci),
                            STAGE_P_SYSTEM,
                            render_stage_p(toks, part),
                            {
                                "cell": c.key,
                                "stage": stage,
                                "chunk": ci,
                                "offset": offset,
                                "concepts": part,
                                "tokens": toks,
                            },
                        )
                    )
        p_all = calls["p"] + calls["pfoil"]
        if p_all and not args.dry_run:
            got = run_calls(
                p_all,
                schema=STAGE_P_SCHEMA,
                judge=args.judge,
                prompt_version=CALL_VERSION,
                preflight=pre.for_judge(args.judge),
                validate=lambda call, r: _valid(
                    parse_stage_p, r, call.meta["concepts"], call.meta["tokens"]
                ),
                temperature=STAGE_P_TEMPERATURE,
                max_tokens=MAX_TOKENS,
                **common,
            )
            for stage in ("p", "pfoil"):
                results[stage] = {call.key: got.get(call.key) for call in calls[stage]}

    # ---- collect the stage rows the scorer joins
    grade_rows: dict[str, list[dict[str, Any]]] = {"b": [], "foil": []}
    for stage in ("b", "foil"):
        for call in calls[stage]:
            r = results[stage].get(call.key)
            if r is None:
                continue
            grade_rows[stage].append(
                {
                    "key": call.key,
                    "token_idx": call.meta["token_idx"],
                    "token": call.meta["token"],
                    "grades": parse_stage_b(r, concepts[call.meta["cell"]]),
                }
            )
    support_rows: dict[str, list[dict[str, Any]]] = {"p": [], "pfoil": []}
    for stage in ("p", "pfoil"):
        for call in calls[stage]:
            r = results[stage].get(call.key)
            if r is None:
                continue
            support_rows[stage].append(
                {
                    "key": call.key,
                    "chunk": call.meta["chunk"],
                    "offset": call.meta["offset"],
                    "support": [
                        0.0 if fw else g
                        for g, fw in zip(
                            parse_stage_p(r, call.meta["concepts"], call.meta["tokens"]),
                            function_word_grounded(r, call.meta["concepts"]),
                            strict=True,
                        )
                    ],
                }
            )
    reject_rate = {
        stage: score.reject_block(
            {call.key for call in calls[stage] if results[stage].get(call.key) is not None},
            {call.key for call in calls[stage] if results[stage].get(call.key) is None},
        )
        for stage in STAGES
        if calls[stage] or stage in ("a", "b", "foil", "p")
    }
    inputs: list[score.CellInput] = []
    for c in cells:
        p = partner(c)
        inputs.append(
            score.CellInput(
                key=c.key,
                id=c.id,
                layer=c.layer,
                pos=c.pos,
                family=family_of[c.id],
                has_text=not c.empty,
                n_text_tokens=n_text_tokens(texts.get(c.key, "")),
                concepts=concepts.get(c.key),
                tokens=ref(c.id, c.layer),
                foil_tokens=ref(p, c.layer) if p is not None else None,
            )
        )
    counts_base = {
        "n_expected_cells": len(expected),
        "n_missing_cells": len(missing),
        "n_empty_cells": rep.n_empty,
        "skipped_rows": sum(rep.skipped.values()),
        "spend_usd": spend.usd,
    }
    config = base_config(
        args,
        PROMPT_VERSION,
        extract_model=a_judge.model,
        stage_p_temperature=STAGE_P_TEMPERATURE,
        stage_p_foil=pfoil,
    )
    return with_readout_count(
        score.score(
            args,
            inputs,
            layers=layers,
            grids={s: score.assemble_grids(grade_rows[s]) for s in ("b", "foil")},
            support={s: score.assemble_support(support_rows[s], concepts) for s in ("p", "pfoil")},
            reject_rate=reject_rate,
            counts_base=counts_base,
            config=config,
            foil_precision_measured=pfoil,
            headline=headline,
            layers_without_reference=no_ref,
        ),
        scope,
        cells,
    )

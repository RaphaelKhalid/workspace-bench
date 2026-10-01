"""Sparse artifacts must preserve family semantics and fail before any network call."""

import hashlib
import importlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from wsbench import llm, registry, runner
from wsbench.cell_manifest import CellManifest, ManifestItem
from wsbench.judge_config import resolve
from wsbench.manifest_judging import annotate_result, load_judge_readouts
from wsbench.results import macro

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/manifest-judge-sites.json").read_text(encoding="utf-8")
)


def example_manifest(family):
    spec = importlib.import_module(f"wsbench.evals.{family}").SPEC
    registry.FAMILIES[family] = spec
    path = registry.REPO_ROOT / spec.bank
    rows = FIXTURE["families"][family]
    return CellManifest(
        {
            "profile": "test sparse judging",
            "model": "Qwen/Qwen3.6-27B",
            "model_revision": "test-only",
            "tokenizer_sha256": {"test": "synthetic input IDs; no production"},
            "banks_sha256": {spec.bank.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()},
            "read_context": FIXTURE["read_context"],
        },
        tuple(
            ManifestItem(
                family,
                r["id"],
                (0,) * (max(abs(p) for p in r["positions"]) + 1),
                tuple(r["positions"]),
                tuple(r["layers"]),
                tuple(r["tokens"]),
            )
            for r in rows
        ),
    )


def artifact_rows(manifest):
    return [
        {"id": it.id, "layer": layer, "pos": pos, "token": token, "samples": ["unclear"]}
        for it in manifest.items
        for layer in it.layers
        for pos, token in zip(it.positions, it.tokens, strict=True)
    ]


def write_rows(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("a manifest preparation check attempted a network call")

    monkeypatch.setattr(llm, "_make_client", forbidden)
    monkeypatch.setattr(llm, "preflight", forbidden)


@pytest.mark.parametrize("family", sorted(FIXTURE["families"]))
def test_every_family_accepts_sparse_manifest_without_missing_cells(family, tmp_path, mk_args):
    manifest = example_manifest(family)
    path = write_rows(tmp_path / "readouts.jsonl", artifact_rows(manifest))
    args = mk_args(path, family=family, cell_manifest=manifest, dry_run=True)
    result = annotate_result(registry.get(family).run(args), args)
    assert result.counts["n_missing_cells"] == 0
    assert result.extras["manifest_readout_cells"] == manifest.n_cells
    assert result.extras["manifest_coverage_complete"] is True
    assert not result.complete and not result.pinned_instrument
    assert not result.extras["judging_finished"]
    assert macro([result])["families"] == []
    if family in ("agentic_misalignment", "arithmetic_intermediates", "brew_intermediates"):
        assert result.counts["n_expected_cells"] == manifest.n_cells
    if family == "multi_concept_directed_modulation":
        # Sparse three-token windows cannot by themselves establish the full sentence gate.
        # Frozen full-window context keeps all selected in-sentence cells eligible.
        assert result.counts["n_expected_cells"] == manifest.n_cells


@pytest.mark.parametrize(
    "damage", ["one_cell", "whole_layer", "duplicate", "foreign", "token", "malformed"]
)
def test_damage_cannot_shorten_denominator(damage, tmp_path, mk_args):
    manifest = example_manifest("agentic_misalignment")
    rows = artifact_rows(manifest)
    if damage == "one_cell":
        rows.pop()
    elif damage == "whole_layer":
        rows = [r for r in rows if r["layer"] != manifest.items[0].layers[0]]
    elif damage == "duplicate":
        rows.append(dict(rows[0]))
    elif damage == "foreign":
        rows.append({**rows[0], "pos": 999999})
    elif damage == "token":
        rows[0]["token"] = "wrong token"
    else:
        rows.append({"samples": ["broken row"]})
    path = write_rows(tmp_path / "r.jsonl", rows)
    args = mk_args(path, family="agentic_misalignment", cell_manifest=manifest)
    with pytest.raises(SystemExit):
        registry.get(args.family).run(args)


def test_manifest_order_is_independent_of_resume_order(tmp_path, mk_args):
    manifest = example_manifest("conjunctive_association")
    rows = artifact_rows(manifest)
    args = mk_args(
        write_rows(tmp_path / "r.jsonl", rows),
        family="conjunctive_association",
        cell_manifest=manifest,
    )
    before, _ = load_judge_readouts(args)
    write_rows(args.readouts, list(reversed(rows)))
    after, _ = load_judge_readouts(args)
    assert before == after


def test_allow_missing_and_layer_override_are_not_escape_hatches(tmp_path, mk_args):
    manifest = example_manifest("association")
    path = write_rows(tmp_path / "r.jsonl", artifact_rows(manifest))
    args = mk_args(path, family="association", cell_manifest=manifest)
    for changed in (replace(args, allow_missing=True), replace(args, layers=[20])):
        with pytest.raises(SystemExit):
            load_judge_readouts(changed)


def test_arithmetic_judges_both_selected_layers_with_original_single_cell_prompt(
    tmp_path, mk_args, monkeypatch
):
    from wsbench.evals.arithmetic_intermediates import judge
    from wsbench.evals.arithmetic_intermediates.prompts import PROMPT_VERSION

    manifest = example_manifest("arithmetic_intermediates")
    path = write_rows(tmp_path / "r.jsonl", artifact_rows(manifest))
    calls_seen = []

    def replies(calls, **kw):
        assert kw["prompt_version"] == PROMPT_VERSION
        calls_seen.extend(calls)
        return {c.key: {"values": [], "basis": "none", "quote": ""} for c in calls}

    monkeypatch.setattr(judge, "run_calls", replies)
    result = judge.run(mk_args(path, family=judge.NAME, cell_manifest=manifest))
    assert len(calls_seen) == manifest.n_cells == 4
    assert result.counts["n_expected_cells"] == 4
    assert result.counts["n_unjudged_cells"] == 0
    assert result.config["cells"] == "manifest"
    assert all(row["n_cells"] == 2 for row in result.rows)


def test_runner_refuses_bad_artifact_before_preflight_and_namespaces_cache(tmp_path, mk_args):
    manifest = example_manifest("association")
    manifest_path = tmp_path / "manifest.json"
    manifest.write(manifest_path)
    root = tmp_path / "readouts"
    root.mkdir()
    rows = artifact_rows(manifest)
    path = write_rows(root / "association.jsonl", rows[:-1])
    options = SimpleNamespace(
        manifest=manifest_path,
        judge_model=None,
        layers=None,
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=10,
        dry_run=False,
        opt=[],
        family_workers=1,
    )
    spec = registry.get("association")
    with pytest.raises(SystemExit, match="coverage mismatch"):
        runner.run_families([spec], options, readouts_root=root, out=tmp_path / "out", env={})
    write_rows(path, rows)
    options.dry_run = True
    result = runner.judge_family(
        spec, options, path, tmp_path / "out", judge=resolve(spec.judge, env={}), opts={}
    )
    assert result.config["cell_manifest"]["sha256"] == manifest.fingerprint
    assert (tmp_path / "out/cache" / manifest.fingerprint / "cells.jsonl").exists()
    assert (tmp_path / "out/results.json").exists()
    changed = replace(manifest, metadata={**manifest.metadata, "profile": "changed"})
    changed.write(manifest_path)
    result2 = runner.judge_family(
        spec, options, path, tmp_path / "out", judge=resolve(spec.judge, env={}), opts={}
    )
    assert result2.config["cell_manifest"]["sha256"] != manifest.fingerprint
    assert (tmp_path / "out/cache" / changed.fingerprint / "cells.jsonl").exists()

"""Sparse aggregation never improves a macro by silently dropping failed families."""

from dataclasses import replace

import pytest
from test_manifest_judging import example_manifest

from wsbench.cell_manifest import CellManifest
from wsbench.results import FamilyResult
from wsbench.sparse_report import summarize


def fixture():
    a, b = example_manifest("association"), example_manifest("typo")
    manifest = CellManifest(a.metadata, a.items + b.items)
    route = {"model": "free-judge", "provider": "fixed", "protocol": "test-only"}
    results = []
    for name, value in [("association", 0.9), ("typo", 0.1)]:
        items = manifest.family(name)
        results.append(
            FamilyResult(
                family=name,
                metric="pass_rate",
                value=value,
                ci95=(value, value),
                n_items=2,
                higher_is_better=True,
                chance=None,
                chance_label=None,
                complete=False,
                pinned_instrument=False,
                config={"cell_manifest": {"sha256": manifest.fingerprint}, "free_route": route},
                counts={"n_missing_cells": 0, "n_unjudged_cells": 0, "n_expected_cells": 2},
                extras={
                    "manifest_items": len(items),
                    "manifest_readout_cells": sum(len(i.cells) for i in items),
                    "manifest_coverage_complete": True,
                    "judging_finished": True,
                },
            )
        )
    return manifest, results


def test_fixed_macro_denominator_requires_every_declared_pass_family():
    manifest, results = fixture()
    complete = summarize(manifest, results, kind="prose")
    assert complete["pass_rate_macro"]["value"] == 0.5
    assert complete["manifest_execution_complete"]
    assert not complete["fidelity_validated"]
    for incomplete in [
        results[:1],
        [results[0], replace(results[1], counts={"n_unjudged_cells": 1})],
    ]:
        report = summarize(manifest, incomplete, kind="prose")
        assert report["pass_rate_macro"]["value"] is None
        assert report["pass_rate_macro"]["denominator"] == 2
        assert report["pass_rate_macro"]["pending"] == ["typo"]


@pytest.mark.parametrize("damage", ["manifest", "route", "count", "nonfinite", "duplicate"])
def test_mixed_or_invalid_results_are_not_aggregated(damage):
    manifest, results = fixture()
    if damage == "manifest":
        results[0].config["cell_manifest"]["sha256"] = "other"
    elif damage == "route":
        results[0].config["free_route"] = {"model": "other"}
    elif damage == "count":
        results[0].extras["manifest_readout_cells"] = 1
    elif damage == "nonfinite":
        results[0].value = float("nan")
    else:
        results.append(results[0])
    with pytest.raises(ValueError):
        summarize(manifest, results, kind="prose")


def test_precision_not_applicable_is_explicit_not_a_zero():
    manifest = example_manifest("jlens_concept_pr")
    report = summarize(manifest, [], kind="tokens")
    assert report["families"]["jlens_concept_pr"]["status"] == "not_applicable"
    assert report["families"]["jlens_concept_pr"]["value"] is None
    assert report["pass_rate_macro"]["value"] is None
    assert report["pass_rate_macro"]["denominator"] == 0

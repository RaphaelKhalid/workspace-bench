"""Report a declared sparse protocol with fixed denominators and explicit applicability."""

import argparse
import json
import math
from pathlib import Path

from wsbench import registry
from wsbench.cell_manifest import CellManifest, digest
from wsbench.results import FamilyResult, read_results


def summarize(manifest: CellManifest, results: list[FamilyResult], *, kind: str) -> dict:
    if kind not in {"prose", "tokens"}:
        raise ValueError("report kind must be prose or tokens")
    registry.load_all()
    families = sorted({item.family for item in manifest.items})
    by_family = {r.family: r for r in results}
    if len(by_family) != len(results) or set(by_family) - set(families):
        raise ValueError("duplicate or out-of-manifest family result")
    routes = [r.config.get("free_route") for r in results]
    if any(not route for route in routes) or len({digest(route) for route in routes}) > 1:
        raise ValueError("sparse report requires one explicit free judge protocol")
    declared_route = routes[0] if routes else None
    output = {}
    macro_families = [name for name in families if registry.get(name).metric == "pass_rate"]
    for family in families:
        spec = registry.get(family)
        result = by_family.get(family)
        items = manifest.family(family)
        cells = sum(len(item.cells) for item in items)
        row = {
            "metric": spec.metric,
            "manifest_items": len(items),
            "manifest_cells": cells,
            "status": "missing",
            "value": None,
            "ci95": None,
            "higher_is_better": spec.higher_is_better,
        }
        if family == "jlens_concept_pr" and kind == "tokens":
            if result is not None:
                raise ValueError(
                    "token readers have no precision-family score under the frozen contract"
                )
            row.update(
                status="not_applicable", reason="prose-only precision; J-lens is the reference"
            )
        elif result is not None:
            if result.config.get("cell_manifest", {}).get("sha256") != manifest.fingerprint:
                raise ValueError(f"{family}: result uses a different manifest")
            if result.metric != spec.metric or result.higher_is_better != spec.higher_is_better:
                raise ValueError(f"{family}: result metric differs from registered contract")
            if (
                result.extras.get("manifest_items") != len(items)
                or result.extras.get("manifest_readout_cells") != cells
            ):
                raise ValueError(f"{family}: physical coverage denominator differs from manifest")
            value = result.value
            if value is not None and (type(value) not in {int, float} or not math.isfinite(value)):
                raise ValueError(f"{family}: nonfinite or invalid score")
            if spec.metric == "pass_rate" and value is not None and not 0 <= value <= 1:
                raise ValueError(f"{family}: pass rate outside [0,1]")
            finished = (
                result.extras.get("judging_finished") is True
                and result.extras.get("manifest_coverage_complete") is True
                and result.counts.get("n_missing_cells") == 0
                and result.counts.get("n_unjudged_cells") == 0
                and not result.extras.get("n_items_without_readouts", 0)
                and value is not None
            )
            row.update(
                status="finished" if finished else "incomplete",
                value=value,
                ci95=result.ci95,
                judged_metric_items=result.n_items,
                judge_expected_units=result.counts.get("n_expected_cells"),
                unjudged_units=result.counts.get("n_unjudged_cells"),
                empty_cells=result.counts.get("n_empty_cells"),
            )
        output[family] = row
    pending = [f for f in macro_families if output[f]["status"] != "finished"]
    macro_value = (
        sum(output[f]["value"] for f in macro_families) / len(macro_families)
        if macro_families and not pending
        else None
    )
    return {
        "schema_version": 1,
        "protocol": "positions-only-report-v1",
        "manifest_sha256": manifest.fingerprint,
        "readout_kind": kind,
        "reader_reference": manifest.metadata.get("reader_reference"),
        "judge_protocol": declared_route,
        "manifest_execution_complete": all(
            r["status"] in {"finished", "not_applicable"} for r in output.values()
        ),
        "fidelity_validated": False,
        "families": output,
        "pass_rate_macro": {
            "value": macro_value,
            "families": macro_families,
            "denominator": len(macro_families),
            "pending": pending,
        },
        "note": (
            "Sparse protocol results; not an upstream-equivalence claim. "
            "Non-pass-rate metrics remain separate."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--kind", choices=["prose", "tokens"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = CellManifest.load(args.manifest)
    results = [read_results(path.parent) for path in sorted(args.results.glob("*/results.json"))]
    report = summarize(manifest, results, kind=args.kind)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest_execution_complete": report["manifest_execution_complete"],
                "pass_rate_macro": report["pass_rate_macro"],
                "fidelity_validated": False,
            }
        )
    )


if __name__ == "__main__":
    main()

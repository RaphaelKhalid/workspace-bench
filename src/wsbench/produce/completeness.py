"""Read-only verification of exported captures and all eight reader grids, without model loads."""

import argparse
import json
from pathlib import Path

from wsbench import readplan
from wsbench.cell_manifest import CellManifest, digest

from . import reader_run
from .captures import CaptureStore, capture_union, read_capture
from .export import contained, validate_snapshot, verify_object
from .reference import ARM_IDS


def original_items():
    return {(family, item.id) for family in readplan.families() for item in readplan.plan(family)}


def require_full_scope(manifests):
    if set(manifests) != set(ARM_IDS):
        raise ValueError("completion requires all eight reference arms")
    expected = original_items()
    for manifest in manifests.values():
        if {(i.family, i.id) for i in manifest.items} != expected:
            raise ValueError("completion manifests omit or change original benchmark items")
        if manifest.n_cells > 50000:
            raise ValueError("completion manifest exceeds per-reader 50k cell budget")


def verify_export(snapshot, root, manifests, *, run_id, batch_size=16, seed=0):
    """Physical completeness only: preserve all input bytes and withhold scientific claims."""
    require_full_scope(manifests)
    readers = reader_run.validate_manifests(manifests)
    union = capture_union([manifests[arm] for arm in ARM_IDS])
    context = {
        "capture_manifest_sha256": union.fingerprint,
        "reader_manifests": {arm: manifests[arm].fingerprint for arm in ARM_IDS},
    }
    validate_snapshot(snapshot, run_id=run_id, context=context)
    root = Path(root).resolve()
    entries = {row["path"]: row for row in snapshot["files"]}

    def verify_bytes():
        for row in entries.values():
            verify_object(contained(root, row["path"]), row["sha256"], row["size"])

    verify_bytes()
    mandatory = {
        "captures/manifest.json",
        "captures/capture-run.json",
        "manifests/capture.json",
        *[f"manifests/{arm}.json" for arm in ARM_IDS],
    }
    if mandatory - entries.keys():
        raise ValueError("export lacks required manifest or capture provenance files")
    for name, manifest in [
        ("captures/manifest.json", union),
        ("manifests/capture.json", union),
        *[(f"manifests/{arm}.json", manifests[arm]) for arm in ARM_IDS],
    ]:
        if CellManifest.load(contained(root, name)).fingerprint != manifest.fingerprint:
            raise ValueError("exported manifest differs from trusted expected manifest")

    # existing() constructs the binding without entering/writing the store.
    store = CaptureStore.existing(contained(root, "captures"))
    binding = json.loads(contained(root, "captures/capture-run.json").read_text(encoding="utf-8"))
    if binding != store.binding:
        raise ValueError("exported capture provenance differs from its manifest")
    captures = {
        "expected_items": len(union.items),
        "present_items": 0,
        "expected_vectors": union.n_cells,
        "present_vectors": 0,
    }
    required = set(mandatory)
    optional = {"readers-run.json", "readouts/readers-run.json"}
    for item in union.items:
        name = f"captures/{digest([item.family, item.id])}.npz"
        required.add(name)
        if name in entries:
            read_capture(contained(root, name), item, binding)
            captures["present_items"] += 1
            captures["present_vectors"] += len(item.positions) * len(item.layers)

    states = {}
    for arm in ARM_IDS:
        manifest, config = manifests[arm], reader_run.public_config(readers[arm])
        states[arm] = {}
        for family in sorted({i.family for i in manifest.items}):
            name = f"readouts/{arm}/{family}.jsonl"
            required.update((name, name + ".run.json"))
            optional.add(name + ".recovered-tail.bin")
            # An unlisted local file must not fill a missing snapshot entry.
            if name not in entries and contained(root, name).exists():
                raise ValueError("unlisted local readout cannot count toward export completeness")
            if name + ".run.json" not in entries and contained(root, name + ".run.json").exists():
                raise ValueError("unlisted provenance cannot count toward export completeness")
            states[arm][family] = reader_run.inspect_output(
                contained(root, name),
                manifest,
                family,
                config,
                binding,
                batch_size=batch_size,
                seed=seed,
                recover=False,
            )

    if entries.keys() - required - optional:
        raise ValueError("export contains data outside the expected reader/capture grids")
    for folder in ("captures", "manifests", "readouts"):
        for path in contained(root, folder).rglob("*"):
            if (
                path.is_file()
                and path.suffix in {".npz", ".json", ".jsonl", ".bin"}
                and path.relative_to(root).as_posix() not in entries
            ):
                raise ValueError("local output contains data not bound to the export snapshot")
    missing = sorted(required - entries.keys())
    expected = sum(m.n_cells for m in manifests.values())
    present = sum(s["present"] for families in states.values() for s in families.values())
    complete = not missing and all(
        s["complete"] for families in states.values() for s in families.values()
    )
    # Detect ordinary concurrent changes during the semantic scan, without repairing any evidence.
    verify_bytes()
    return {
        "schema_version": 1,
        "run_id": run_id,
        "snapshot_sha256": snapshot["sha256"],
        "manifest_context": context,
        "original_items": len(union.items),
        "families": len({i.family for i in union.items}),
        "captures": captures,
        "arms": states,
        "expected_reader_cells": expected,
        "present_reader_cells": present,
        "missing_reader_cells": expected - present,
        "missing_files": missing,
        "physical_complete": complete,
        "export_bytes_verified": True,
        "judging_complete": False,
        "benchmark_fidelity_validated": False,
        "note": (
            "Physical files and declared provenance verified; "
            "no neural-runtime or scientific equivalence claim."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "root", "readers"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    manifests = {arm: CellManifest.load(args.readers / f"{arm}.json") for arm in ARM_IDS}
    result = verify_export(
        json.loads(args.snapshot.read_text(encoding="utf-8")),
        args.root,
        manifests,
        run_id=args.run_id,
        batch_size=args.batch_size,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["physical_complete"] else 2)


if __name__ == "__main__":
    main()

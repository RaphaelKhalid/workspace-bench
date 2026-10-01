"""Outcome-independent operational pilot selection using whole frozen reader batches."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from wsbench.cell_manifest import CellManifest, digest

from .batches import blocks
from .captures import capture_union
from .completeness import require_full_scope
from .reference import ARM_IDS, load_lock
from .storage import python_source_sha256


def upper_bin(size):
    return 1 << (size - 1).bit_length()


def select_reader_blocks(candidates, anchors):
    """Cover families and each layer/batch-size shape without expanding every anchor."""
    features = [
        {("family", row["family"]), ("shape", row["layer"], len(row["cells"]))}
        for row in candidates
    ]
    remaining = set().union(*features)
    selected = set()
    priorities = [
        (
            sum((row["family"], item_id) in anchors for item_id, _ in row["cells"]),
            digest({k: row[k] for k in ("family", "layer", "cells")}),
        )
        for row in candidates
    ]
    while remaining:
        index = max(
            range(len(candidates)),
            key=lambda i: (len(features[i] & remaining), *priorities[i]),
        )
        selected.add(index)
        remaining -= features[index]
    return [row for i, row in enumerate(candidates) if i in selected]


def build_plan(manifests, *, batch_size=16, seed=0):
    """Select workload anchors, then close over full batches so baseline seeds stay unchanged."""
    if type(batch_size) is not int or batch_size < 1 or type(seed) is not int or seed < 0:
        raise ValueError("pilot batch size and seed must be valid integers")
    require_full_scope(manifests)
    lock = load_lock()
    lock_sha = digest(lock)
    for arm, manifest in manifests.items():
        manifest.verify_banks()
        ref = manifest.metadata.get("reader_reference", {})
        if ref.get("arm") != arm or ref.get("lock_sha256") != lock_sha:
            raise ValueError("pilot reader manifest differs from reference lock")
    union = capture_union([manifests[arm] for arm in ARM_IDS])
    groups = defaultdict(list)
    for item in union.items:
        feature = (
            item.family,
            upper_bin(len(item.input_ids)),
            item.layers,
            upper_bin(len(item.positions)),
        )
        groups[feature].append(item)
    strata, anchors = [], set()
    for (family, length_bin, layers, position_bin), items in sorted(groups.items()):
        item = max(
            items, key=lambda i: (len(i.input_ids), len(i.positions), digest([i.family, i.id]))
        )
        anchors.add((family, item.id))
        strata.append(
            {
                "family": family,
                "input_length_upper": length_bin,
                "layers": list(layers),
                "position_count_upper": position_bin,
                "population_items": len(items),
                "anchor_id": item.id,
                "anchor_input_tokens": len(item.input_ids),
                "anchor_positions": len(item.positions),
            }
        )
    selected_items = set(anchors)
    readers = {}
    for arm in ARM_IDS:
        manifest = manifests[arm]
        candidates, full_cells = [], 0
        for family in sorted({i.family for i in manifest.items}):
            for index, block in enumerate(blocks(manifest, family, batch_size, seed)):
                full_cells += len(block.cells)
                candidates.append(
                    {
                        "family": family,
                        "index": index,
                        "layer": block.layer,
                        "seed": block.seed,
                        "cells": [list(cell) for cell in block.cells],
                    }
                )
        selected = select_reader_blocks(candidates, anchors)
        for row in selected:
            selected_items.update((row["family"], item_id) for item_id, _ in row["cells"])
        readers[arm] = {
            "manifest_sha256": manifest.fingerprint,
            "full_cells": full_cells,
            "pilot_cells": sum(len(b["cells"]) for b in selected),
            "blocks": selected,
        }
    captures = [
        {
            "family": i.family,
            "id": i.id,
            "input_tokens": len(i.input_ids),
            "positions": len(i.positions),
            "layers": len(i.layers),
            "vectors": len(i.positions) * len(i.layers),
        }
        for i in union.items
        if (i.family, i.id) in selected_items
    ]
    payload = {
        "schema_version": 1,
        "protocol": "operational-pilot-v2",
        "selection": (
            "family, power-of-two input/position bins, exact capture layers; "
            "longest input then most positions then hashed ID"
        ),
        "reader_selection": (
            "greedy coverage of each family and layer/batch-size shape, then most anchor "
            "cells, then hashed block; preserve original full-run blocks and seeds"
        ),
        "batch_size": batch_size,
        "seed": seed,
        "reference_lock_sha256": lock_sha,
        "capture_manifest_sha256": union.fingerprint,
        "source_sha256": {
            p.name: python_source_sha256(p) for p in sorted(Path(__file__).parent.glob("*.py"))
        },
        "strata": strata,
        "captures": captures,
        "readers": readers,
        "summary": {
            "anchor_items": len(anchors),
            "capture_items": len(captures),
            "capture_vectors": sum(i["vectors"] for i in captures),
            "full_capture_items": len(union.items),
            "full_capture_vectors": union.n_cells,
            "pilot_reader_cells": sum(r["pilot_cells"] for r in readers.values()),
            "full_reader_cells": sum(r["full_cells"] for r in readers.values()),
        },
        "reference_open_questions": {a: lock["arms"][a]["open_questions"] for a in ARM_IDS},
        "pilot_cap_usd": 2,
        "total_goal_cap_usd": 20,
        "launch_authorized_by_plan": False,
        "cost_measured": False,
        "benchmark_fidelity_validated": False,
        "audit_boundary": (
            "Operational measurements only; do not inspect readout content or grades, "
            "change positions, or tune the held-out audit."
        ),
    }
    return {**payload, "sha256": digest(payload)}


def validate_plan(plan, manifests):
    expected = build_plan(manifests, batch_size=plan.get("batch_size"), seed=plan.get("seed"))
    if plan != expected:
        raise ValueError("pilot plan differs from frozen workload, settings or implementation")


def execution_selection(plan):
    selection = {}
    for arm, reader in plan["readers"].items():
        families = defaultdict(list)
        for row in reader["blocks"]:
            families[row["family"]].append(row["index"])
        selection[arm] = dict(families)
    return selection


def load_plan(path, expected_sha256):
    with Path(path).open("rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("pilot plan exceeds size bound")
    plan = json.loads(raw)
    if (
        not isinstance(plan, dict)
        or plan.get("sha256") != expected_sha256
        or digest({k: v for k, v in plan.items() if k != "sha256"}) != expected_sha256
    ):
        raise ValueError("pilot plan digest differs from compute specification")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readers", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    manifests = {arm: CellManifest.load(args.readers / f"{arm}.json") for arm in ARM_IDS}
    plan = build_plan(manifests, batch_size=args.batch_size, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        if json.loads(args.out.read_text(encoding="utf-8")) != plan:
            raise ValueError("refuse to overwrite a different pilot plan")
    else:
        args.out.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sha256": plan["sha256"], **plan["summary"]}, indent=2))


if __name__ == "__main__":
    main()

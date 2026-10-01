"""Capture once, publish durable checkpoints, then execute every frozen reader arm."""

import argparse
import gc
import json
import os
import sys
import time
from contextlib import ExitStack
from pathlib import Path

from wsbench.cell_manifest import CellManifest, digest

from . import reader_run
from .backend import Backend
from .budget import BudgetGuard, LeaseBudget
from .captures import CaptureStore, capture_all, capture_union
from .deadline import arm_deadline, read_metadata, request_shutdown, require_local_pod
from .export import SnapshotPublisher, contained
from .reference import ARM_IDS
from .storage import file_lock
from .watchdog import RunPodStopper


def release_backend(backend):
    backend.model = backend.tokenizer = None
    gc.collect()
    torch = sys.modules.get("torch")
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def save_manifest(path, manifest):
    if path.exists() and CellManifest.load(path).fingerprint != manifest.fingerprint:
        raise ValueError("worker output contains a different manifest")
    if not path.exists():
        manifest.write(path)


def run_compute(
    manifests, root, export_root, *, run_id, guard, batch_size=16, seed=0, device="cuda"
):
    """Compute only: invoke inside a separately supervised process with a pod deadline."""
    if type(batch_size) is not int or batch_size < 1 or type(seed) is not int or seed < 0:
        raise ValueError("batch size must be positive and seed nonnegative integers")
    guard.check()
    readers = reader_run.validate_manifests(manifests)
    union = capture_union([manifests[arm] for arm in ARM_IDS])
    root = Path(root).resolve()
    context = {
        "capture_manifest_sha256": union.fingerprint,
        "reader_manifests": {arm: manifests[arm].fingerprint for arm in ARM_IDS},
    }
    with file_lock(root / ".compute.lock"), ExitStack() as stack:
        manifest_paths = []
        for arm in ARM_IDS:
            path = contained(root, f"manifests/{arm}.json")
            save_manifest(path, manifests[arm])
            manifest_paths.append(path)
        union_path = contained(root, "manifests/capture.json")
        save_manifest(union_path, union)
        manifest_paths.append(union_path)
        publisher = SnapshotPublisher(root, export_root, run_id=run_id, context=context)
        publisher.update(manifest_paths, force=True)
        capture_root, readout_root = contained(root, "captures"), contained(root, "readouts")
        store, backend, existing = None, None, []
        started = time.monotonic()
        if (capture_root / "capture-run.json").exists():
            store = CaptureStore.existing(capture_root)
            if store.manifest.fingerprint != union.fingerprint:
                raise ValueError("worker capture manifest differs from reader union")
            store = stack.enter_context(store)
            for item in union.items:
                guard.check()
                if store.get(item) is not None:
                    existing.append(capture_root / f"{digest([item.family, item.id])}.npz")
            # Corrupt late reader output must fail before loading a missing capture's model.
            for arm in ARM_IDS:
                for family in sorted({i.family for i in manifests[arm].items}):
                    guard.check()
                    reader_run.inspect_output(
                        readout_root / arm / f"{family}.jsonl",
                        manifests[arm],
                        family,
                        reader_run.public_config(readers[arm]),
                        store.binding,
                        batch_size=batch_size,
                        seed=seed,
                    )
            publisher.update(
                [capture_root / "manifest.json", capture_root / "capture-run.json", *existing],
                force=True,
            )
        elif any(capture_root.glob("*.npz")) or any(readout_root.rglob("*.jsonl*")):
            raise ValueError("worker outputs exist without capture provenance")
        try:
            if len(existing) < len(union.items):
                guard.check()
                backend = Backend.load(
                    union.metadata["model"],
                    revision=union.metadata["model_revision"],
                    device=device,
                    dtype="bfloat16",
                )
                guard.check()
                if store is None:
                    store = stack.enter_context(
                        CaptureStore(
                            capture_root, union, backend.capture_runtime(), backend.unembed.shape[1]
                        )
                    )
                publisher.update(
                    [capture_root / "manifest.json", capture_root / "capture-run.json"], force=True
                )
                capture_report = capture_all(
                    backend,
                    store,
                    before_item=guard.check,
                    on_item=lambda event: publisher.update([Path(event["path"])]),
                )
            else:
                capture_report = {
                    "captured_items": 0,
                    "reused_items": len(existing),
                    "cells": union.n_cells,
                }
        finally:
            # Flush already queued durable items even after interruption or a budget exception.
            try:
                publisher.update([], force=True)
            finally:
                if backend is not None:
                    release_backend(backend)
        capture_report["elapsed_seconds"] = time.monotonic() - started
        guard.check()
        reader_report = reader_run.run_readers(
            manifests,
            readout_root,
            store,
            guard=guard,
            batch_size=batch_size,
            seed=seed,
            device=device,
            publisher=publisher,
        )
        return {
            "status": "complete",
            "capture": capture_report,
            "readers": reader_report,
            "export_snapshot_sha256": publisher.previous["sha256"],
            "benchmark_fidelity_validated": False,
        }


def run_pod_compute(
    manifests,
    root,
    export_root,
    *,
    run_id,
    guard,
    stopper,
    deadline_journal,
    batch_size=16,
    seed=0,
    device="cuda",
):
    """Arm a separate deadline before computation, retaining the external export/stop duty."""
    require_local_pod(stopper)
    if run_id != stopper.run_id:
        raise ValueError("worker and deadline run identities differ")
    handle = arm_deadline(guard, stopper, deadline_journal)

    class SupervisedBudget:
        def check(self):
            handle.check()
            return guard.check()

        def snapshot(self):
            return guard.snapshot()

    status = "failed"
    try:
        result = run_compute(
            manifests,
            root,
            export_root,
            run_id=run_id,
            guard=SupervisedBudget(),
            batch_size=batch_size,
            seed=seed,
            device=device,
        )
        status = "complete"
        return result
    finally:
        handle.mark_terminal(status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument(
        "--spec-sha256", help="Expected canonical specification digest from controller"
    )
    args = parser.parse_args()
    stopper = RunPodStopper(
        os.environ.get("RUNPOD_POD_ID", ""), os.environ.get("WSBENCH_RUN_ID", "")
    )
    require_local_pod(stopper)
    try:
        spec = read_metadata(args.spec)
        if args.spec_sha256 is not None and digest(spec) != args.spec_sha256:
            raise ValueError("compute specification digest differs from controller")
        if set(spec) != {
            "run_id",
            "pod_id",
            "budget",
            "readers",
            "root",
            "export_root",
            "deadline_journal",
            "batch_size",
            "seed",
            "device",
        }:
            raise ValueError("invalid compute specification")
        if (spec["pod_id"], spec["run_id"]) != (stopper.pod_id, stopper.run_id):
            raise ValueError("compute specification belongs to another pod or run")
        manifests = {
            arm: CellManifest.load(Path(spec["readers"]) / f"{arm}.json") for arm in ARM_IDS
        }
        result = run_pod_compute(
            manifests,
            spec["root"],
            spec["export_root"],
            run_id=spec["run_id"],
            guard=BudgetGuard(LeaseBudget(**spec["budget"])),
            stopper=stopper,
            deadline_journal=spec["deadline_journal"],
            batch_size=spec["batch_size"],
            seed=spec["seed"],
            device=spec["device"],
        )
    except BaseException:
        request_shutdown(stopper)
        raise
    print(json.dumps(result))


if __name__ == "__main__":
    main()

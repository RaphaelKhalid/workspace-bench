"""Validate every output before loading; load each unfinished reference reader once."""

import gc
import json
import math
import time
from contextlib import nullcontext
from dataclasses import asdict, is_dataclass
from pathlib import Path

from wsbench.cell_manifest import digest
from wsbench.readouts import _parse_row

from .batches import binding_for, blocks, indexed_blocks
from .journal import ReadoutJournal
from .producer import Producer
from .reference import ARM_IDS, load_lock, reference_method
from .storage import atomic_writer, file_lock, python_source_sha256


def public_config(reader):
    return {
        k: asdict(v) if is_dataclass(v) else v
        for k, v in vars(reader).items()
        if not k.startswith("_")
    }


def inspect_output(
    path,
    manifest,
    family,
    config,
    capture_binding,
    *,
    batch_size,
    seed,
    recover=True,
    required_cells=None,
):
    """Recover only torn tails; reject drift/corruption without a model or Torch import."""
    path = Path(path)
    sidecar = path.with_suffix(path.suffix + ".run.json")
    expected = manifest.expected(family)
    if required_cells is not None and (
        not isinstance(required_cells, set) or not required_cells or not required_cells <= expected
    ):
        raise ValueError("required cells must be a nonempty subset of the full manifest")

    def coverage(present):
        result = {
            "complete": present == expected,
            "present": len(present),
            "expected": len(expected),
        }
        if required_cells is not None:
            result.update(
                selection_complete=required_cells <= present,
                selection_present=len(required_cells & present),
                selection_expected=len(required_cells),
            )
        return result

    if not sidecar.exists():
        if path.exists() and path.stat().st_size:
            raise ValueError("existing readouts have no provenance sidecar")
        return coverage(set())
    old = json.loads(sidecar.read_text(encoding="utf-8"))
    runtime = old.get("reader_runtime")
    if not isinstance(runtime, dict) or not runtime.get("dtype"):
        raise ValueError("reader runtime provenance missing")
    backend_sha = python_source_sha256(Path(__file__).with_name("backend.py"))
    if runtime.get("backend_source_sha256") != backend_sha:
        raise ValueError("reader backend implementation changed")
    binding = binding_for(
        manifest, family, config, capture_binding, runtime, batch_size=batch_size, seed=seed
    )
    if not recover and old != binding:
        raise ValueError("readout manifest/reader configuration changed; use a new output")
    if not recover and not path.exists():
        return coverage(set())
    # Opening also validates row identity, duplicates, mixed kinds and malformed complete rows.
    context = ReadoutJournal(path, binding=binding, expected=expected) if recover else nullcontext()
    with context:
        items = {item.id: item for item in manifest.family(family)}
        present = set()
        data = path.read_bytes()
        if not recover and data and not data.endswith(b"\n"):
            raise ValueError("exported readouts contain an unfinished checkpoint line")
        for line in data.splitlines():
            cell = _parse_row(json.loads(line))
            if cell is None:
                raise ValueError("invalid readout row")
            key = (cell.id, cell.layer, cell.pos)
            if key not in expected or key in present:
                raise ValueError("duplicate readout or readout outside manifest")
            present.add(key)
            item = items[cell.id]
            if cell.token != item.tokens[item.positions.index(cell.pos)]:
                raise ValueError("cached read-site token differs from manifest")
            if "sampling" in config:
                if cell.kind != "prose" or len(cell.samples) != config["sampling"]["k"]:
                    raise ValueError("cached samples differ from reference reader")
            elif (
                cell.kind != "tokens"
                or len(cell.tokens) != config["k"]
                or cell.scores is None
                or not all(math.isfinite(x) for x in cell.scores)
            ):
                raise ValueError("cached ranking differs from reference reader")
        return coverage(present)


def validate_manifests(manifests):
    if set(manifests) != set(ARM_IDS):
        raise ValueError("full reader run requires the exact eight-arm roster")
    lock = load_lock()
    lock_hash = digest(lock)
    readers = {}
    for arm in ARM_IDS:
        manifest = manifests[arm]
        manifest.verify_banks()
        ref = manifest.metadata.get("reader_reference", {})
        if ref.get("arm") != arm or ref.get("lock_sha256") != lock_hash:
            raise ValueError("reader manifest does not match arm/artifact lock")
        if (manifest.metadata["model"], manifest.metadata["model_revision"]) != (
            lock["subject"]["model"],
            lock["subject"]["revision"],
        ):
            raise ValueError("reader manifest does not match frozen subject")
        spec = lock["arms"][arm]
        for item in manifest.items:
            if spec["layer_policy"] == "fixed" and item.layers != tuple(spec["supported_layers"]):
                raise ValueError("reader manifest violates its fixed layer contract")
            if not set(item.layers) <= set(spec["supported_layers"]):
                raise ValueError("reader manifest requests unsupported layers")
        readers[arm] = reference_method(arm)  # All unresolved arms fail before any load.
    return readers


def selection_cells(manifests, block_selection, batch_size, seed):
    if block_selection is None:
        return None
    if set(block_selection) != set(ARM_IDS):
        raise ValueError("selected execution requires all eight readers")
    result = {}
    for arm, manifest in manifests.items():
        families = {i.family for i in manifest.items}
        if set(block_selection[arm]) != families:
            raise ValueError("selected execution requires every family")
        result[arm] = {}
        for family in sorted(families):
            if block_selection[arm][family] is None:
                raise ValueError("selected execution requires explicit block indices")
            chosen = indexed_blocks(
                blocks(manifest, family, batch_size, seed), block_selection[arm][family]
            )
            result[arm][family] = {
                (item_id, block.layer, pos) for _, block in chosen for item_id, pos in block.cells
            }
    return result


def preflight(manifests, out, store, *, batch_size, seed, required=None):
    readers = validate_manifests(manifests)
    states = {}
    for arm in ARM_IDS:
        manifest = manifests[arm]
        item_keys = (
            {(f, item_id) for f, cells in required[arm].items() for item_id, _, _ in cells}
            if required is not None
            else None
        )
        store.check_reader(manifest, item_keys=item_keys)
        config = public_config(readers[arm])
        states[arm] = {
            family: inspect_output(
                Path(out) / arm / f"{family}.jsonl",
                manifest,
                family,
                config,
                store.binding,
                batch_size=batch_size,
                seed=seed,
                required_cells=required[arm][family] if required is not None else None,
            )
            for family in sorted({i.family for i in manifest.items})
        }
    return readers, states


def release(producer):
    """Drop model/adapter references between arms, including NLA's stored hook closures."""
    producer.method = None
    producer.backend = None
    gc.collect()
    import torch

    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def run_readers(
    manifests,
    out,
    store,
    *,
    guard,
    batch_size=16,
    seed=0,
    device="cuda",
    publisher=None,
    block_selection=None,
    on_event=None,
):
    """Compute only; caller supplies the supervised budget guard and owns pod shutdown."""
    out = Path(out)
    required = selection_cells(manifests, block_selection, batch_size, seed)
    completion_key = "complete" if required is None else "selection_complete"
    with file_lock(out / ".readers.lock"):
        readers, states = preflight(
            manifests, out, store, batch_size=batch_size, seed=seed, required=required
        )
        report = {
            "status": "running",
            "scope": "full_manifest" if required is None else "selected_blocks",
            "started": time.time(),
            "arms": states,
            "manifest_hashes": {k: m.fingerprint for k, m in manifests.items()},
            "batch_size": batch_size,
            "seed": seed,
            "model_loads": 0,
            "generated_cells": 0,
            "new_cells": 0,
        }

        def save(event):
            report["last_event"] = {"at": time.time(), **event}
            report["budget"] = guard.snapshot()
            with atomic_writer(out / "readers-run.json") as handle:
                handle.write((json.dumps(report, indent=2) + "\n").encode())
            if on_event is not None:
                on_event(event)
            if publisher is not None:
                paths = [out / "readers-run.json"]
                if "family" in event and "arm" in event:
                    path = out / event["arm"] / f"{event['family']}.jsonl"
                    paths.extend([path, path.with_suffix(".jsonl.run.json")])
                publisher.update(
                    paths,
                    force=event["stage"]
                    in {"family_complete", "complete", "pilot_complete", "interrupted"},
                )

        if publisher is not None:
            existing = []
            for arm, families in states.items():
                for family in families:
                    path = out / arm / f"{family}.jsonl"
                    if path.exists():
                        existing.extend([path, path.with_suffix(".jsonl.run.json")])
            publisher.update(existing)
        save({"stage": "preflight_complete"})
        producer = None
        try:
            for arm in ARM_IDS:
                pending = [f for f, s in states[arm].items() if not s[completion_key]]
                if not pending:
                    continue
                guard.check()
                manifest = manifests[arm]
                save({"stage": "loading", "arm": arm})
                load_started = time.monotonic()
                producer = Producer.load_cached(
                    manifest.metadata["model"],
                    readers.pop(arm),
                    device=device,
                    revision=manifest.metadata["model_revision"],
                )
                report["model_loads"] += 1

                def on_batch(event, arm=arm):
                    report["generated_cells"] += event["generated_cells"]
                    report["new_cells"] += event["new_cells"]
                    save({"stage": "batch_checkpointed", "arm": arm, **event})

                try:
                    loaded = {
                        "stage": "reader_loaded",
                        "arm": arm,
                        "elapsed_seconds": time.monotonic() - load_started,
                    }
                    if hasattr(producer, "backend"):
                        loaded["runtime"] = producer.backend.capture_runtime()
                    save(loaded)
                    for family in pending:
                        guard.check()
                        path = out / arm / f"{family}.jsonl"
                        producer.run_cached(
                            manifest,
                            family,
                            path,
                            store,
                            batch_size=batch_size,
                            seed=seed,
                            before_batch=guard.check,
                            on_batch=on_batch,
                            **(
                                {"block_indices": block_selection[arm][family]}
                                if block_selection is not None
                                else {}
                            ),
                        )
                        state = inspect_output(
                            path,
                            manifest,
                            family,
                            public_config(producer.method),
                            store.binding,
                            batch_size=batch_size,
                            seed=seed,
                            required_cells=required[arm][family] if required is not None else None,
                        )
                        if not state[completion_key]:
                            raise ValueError("reader returned with incomplete output")
                        states[arm][family] = state
                        save({"stage": "family_complete", "arm": arm, "family": family})
                finally:
                    release_started = time.monotonic()
                    release(producer)
                    producer = None
                    save(
                        {
                            "stage": "reader_released",
                            "arm": arm,
                            "elapsed_seconds": time.monotonic() - release_started,
                        }
                    )
            report["status"] = "complete" if required is None else "pilot_complete"
            return report
        except BaseException as exc:
            report.update(status="interrupted", error_type=type(exc).__name__)
            raise
        finally:
            report["finished"] = time.time()
            save({"stage": report["status"]})

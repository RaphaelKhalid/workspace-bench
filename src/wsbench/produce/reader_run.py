"""Validate every output before loading; load each unfinished reference reader once."""

import gc
import hashlib
import json
import math
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

from wsbench.cell_manifest import digest
from wsbench.readouts import _parse_row

from .batches import binding_for
from .journal import ReadoutJournal
from .producer import Producer
from .reference import ARM_IDS, load_lock, reference_method
from .storage import atomic_writer, file_lock


def public_config(reader):
    return {
        k: asdict(v) if is_dataclass(v) else v
        for k, v in vars(reader).items()
        if not k.startswith("_")
    }


def inspect_output(path, manifest, family, config, capture_binding, *, batch_size, seed):
    """Recover only torn tails; reject drift/corruption without a model or Torch import."""
    path = Path(path)
    sidecar = path.with_suffix(path.suffix + ".run.json")
    expected = manifest.expected(family)
    if not sidecar.exists():
        if path.exists() and path.stat().st_size:
            raise ValueError("existing readouts have no provenance sidecar")
        return {"complete": False, "present": 0, "expected": len(expected)}
    old = json.loads(sidecar.read_text(encoding="utf-8"))
    runtime = old.get("reader_runtime")
    if not isinstance(runtime, dict) or not runtime.get("dtype"):
        raise ValueError("reader runtime provenance missing")
    backend_sha = hashlib.sha256(Path(__file__).with_name("backend.py").read_bytes()).hexdigest()
    if runtime.get("backend_source_sha256") != backend_sha:
        raise ValueError("reader backend implementation changed")
    binding = binding_for(
        manifest, family, config, capture_binding, runtime, batch_size=batch_size, seed=seed
    )
    # Opening also validates row identity, duplicates, mixed kinds and malformed complete rows.
    with ReadoutJournal(path, binding=binding, expected=expected) as journal:
        items = {item.id: item for item in manifest.family(family)}
        for line in path.read_text(encoding="utf-8").splitlines():
            cell = _parse_row(json.loads(line))
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
        return {
            "complete": journal.present == expected,
            "present": len(journal.present),
            "expected": len(expected),
        }


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


def preflight(manifests, out, store, *, batch_size, seed):
    readers = validate_manifests(manifests)
    states = {}
    for arm in ARM_IDS:
        manifest = manifests[arm]
        store.check_reader(manifest)
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
    manifests, out, store, *, guard, batch_size=16, seed=0, device="cuda", publisher=None
):
    """Compute only; caller supplies the supervised budget guard and owns pod shutdown."""
    out = Path(out)
    with file_lock(out / ".readers.lock"):
        readers, states = preflight(manifests, out, store, batch_size=batch_size, seed=seed)
        report = {
            "status": "running",
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
            if publisher is not None:
                paths = [out / "readers-run.json"]
                if "family" in event and "arm" in event:
                    path = out / event["arm"] / f"{event['family']}.jsonl"
                    paths.extend([path, path.with_suffix(".jsonl.run.json")])
                publisher.update(
                    paths, force=event["stage"] in {"family_complete", "complete", "interrupted"}
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
                pending = [f for f, s in states[arm].items() if not s["complete"]]
                if not pending:
                    continue
                guard.check()
                manifest = manifests[arm]
                save({"stage": "loading", "arm": arm})
                producer = Producer.load_cached(
                    manifest.metadata["model"],
                    readers.pop(arm),
                    device=device,
                    revision=manifest.metadata["model_revision"],
                )
                report["model_loads"] += 1
                save({"stage": "reader_loaded", "arm": arm})

                def on_batch(event, arm=arm):
                    report["generated_cells"] += event["generated_cells"]
                    report["new_cells"] += event["new_cells"]
                    save({"stage": "batch_checkpointed", "arm": arm, **event})

                try:
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
                        )
                        state = inspect_output(
                            path,
                            manifest,
                            family,
                            public_config(producer.method),
                            store.binding,
                            batch_size=batch_size,
                            seed=seed,
                        )
                        if not state["complete"]:
                            raise ValueError("reader returned with incomplete output")
                        states[arm][family] = state
                        save({"stage": "family_complete", "arm": arm, "family": family})
                finally:
                    release(producer)
                    producer = None
            report["status"] = "complete"
            return report
        except BaseException as exc:
            report.update(status="interrupted", error_type=type(exc).__name__)
            raise
        finally:
            report["finished"] = time.time()
            save({"stage": report["status"]})

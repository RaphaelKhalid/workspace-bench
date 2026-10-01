"""Manifest-bound, lossless subject activation storage shared by every reader arm."""

import argparse
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from wsbench.cell_manifest import CellManifest, ManifestItem, digest

from .storage import atomic_writer, file_lock


def capture_union(manifests: list[CellManifest]) -> CellManifest:
    """Union reader layers only after proving identical inputs, items and selected sites."""
    if not manifests:
        raise ValueError("capture union requires reader manifests")
    first = manifests[0]
    identities = [(i.family, i.id) for i in first.items]
    provenance = ("model", "model_revision", "tokenizer_sha256", "banks_sha256")
    for other in manifests[1:]:
        if any(other.metadata[k] != first.metadata[k] for k in provenance):
            raise ValueError("capture manifests have different subject/input provenance")
        if [(i.family, i.id) for i in other.items] != identities:
            raise ValueError("capture manifests have different item identities/order")
        for old, new in zip(first.items, other.items, strict=True):
            if replace(new, layers=old.layers) != old:
                raise ValueError("capture manifests differ in input or selected positions")
    items = tuple(
        replace(
            item, layers=tuple(sorted({layer for m in manifests for layer in m.items[j].layers}))
        )
        for j, item in enumerate(first.items)
    )
    return CellManifest(
        {
            **{k: first.metadata[k] for k in provenance},
            "profile": "shared-captures-v1",
            "reader_manifests": sorted(m.fingerprint for m in manifests),
            "capture_contract": (
                "decoder-block-output; adapters-disabled; use-cache-false; fp32-storage"
            ),
        },
        items,
    )


class CaptureStore:
    """One atomic NPZ per item; corruption fails instead of silently triggering recapture."""

    def __init__(self, root: Path, manifest: CellManifest, runtime: dict, hidden_size: int):
        if hidden_size <= 0 or not runtime or "dtype" not in runtime:
            raise ValueError("capture store requires runtime/dtype and hidden size")
        self.root = Path(root)
        self.manifest = manifest
        self.binding = {
            "schema_version": 1,
            "manifest_sha256": manifest.fingerprint,
            "runtime": runtime,
            "hidden_size": hidden_size,
            "storage_dtype": "float32",
        }
        self.hidden_size = hidden_size
        self._items = {(i.family, i.id): i for i in manifest.items}
        self._lock = None

    @classmethod
    def existing(cls, root: Path):
        binding = json.loads((root / "capture-run.json").read_text(encoding="utf-8"))
        manifest = CellManifest.load(root / "manifest.json")
        return cls(root, manifest, binding["runtime"], binding["hidden_size"])

    def __enter__(self):
        self._lock = file_lock(self.root / ".writer.lock")
        self._lock.__enter__()
        try:
            path = self.root / "capture-run.json"
            if path.exists():
                if json.loads(path.read_text(encoding="utf-8")) != self.binding:
                    raise ValueError("capture provenance/runtime changed; use a new store")
            else:
                if any(self.root.glob("*.npz")):
                    raise ValueError("capture files exist without provenance")
                with atomic_writer(path) as handle:
                    handle.write((json.dumps(self.binding, sort_keys=True) + "\n").encode())
            payload = {**self.manifest.payload(), "sha256": self.manifest.fingerprint}
            with atomic_writer(self.root / "manifest.json") as handle:
                handle.write((json.dumps(payload) + "\n").encode())
            return self
        except BaseException:
            self._lock.__exit__(None, None, None)
            self._lock = None
            raise

    def __exit__(self, *exc):
        self._lock.__exit__(*exc)
        self._lock = None

    def _identity(self, item: ManifestItem) -> tuple[Path, dict]:
        if self._lock is None:
            raise RuntimeError("capture store must be opened")
        if self._items.get((item.family, item.id)) != item:
            raise ValueError("item does not belong to capture manifest")
        key = digest([item.family, item.id])
        return self.root / f"{key}.npz", {
            "binding_sha256": digest(self.binding),
            "item_sha256": digest(asdict(item)),
        }

    def _validate(self, array: np.ndarray, item: ManifestItem) -> None:
        if (
            array.dtype != np.dtype("float32")
            or array.shape != (len(item.layers), len(item.positions), self.hidden_size)
            or not np.isfinite(array).all()
        ):
            raise ValueError("capture dtype/shape/finiteness mismatch")

    def get(self, item: ManifestItem) -> np.ndarray | None:
        path, identity = self._identity(item)
        if not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as data:
                if set(data.files) != {"metadata", "vectors"}:
                    raise ValueError("unexpected capture members")
                meta = json.loads(str(data["metadata"].item()))
                array = data["vectors"]
            self._validate(array, item)
            sha = hashlib.sha256(array.tobytes()).hexdigest()
            if meta != {**identity, "vectors_sha256": sha}:
                raise ValueError("capture identity/content hash mismatch")
            return array
        except Exception as exc:
            raise ValueError(f"invalid capture {item.family}/{item.id}: {exc}") from exc

    def put(self, item: ManifestItem, vectors: np.ndarray) -> None:
        path, identity = self._identity(item)
        self._validate(vectors, item)
        if path.exists():
            old = self.get(item)
            if not np.array_equal(old, vectors):
                raise ValueError("refusing to overwrite different captured activations")
            return
        meta = {**identity, "vectors_sha256": hashlib.sha256(vectors.tobytes()).hexdigest()}
        with atomic_writer(path) as handle:
            np.savez(handle, metadata=np.array(json.dumps(meta, sort_keys=True)), vectors=vectors)

    def selected(self, item: ManifestItem) -> dict[int, np.ndarray]:
        original = self._items.get((item.family, item.id))
        if original is None or replace(item, layers=original.layers) != original:
            raise ValueError("reader inputs/sites differ from capture store")
        if not set(item.layers) <= set(original.layers):
            raise ValueError("reader requests uncaptured layers")
        vectors = self.get(original)
        if vectors is None:
            raise ValueError(f"capture missing for {item.family}/{item.id}")
        return {layer: vectors[original.layers.index(layer)] for layer in item.layers}

    def check_reader(self, manifest: CellManifest) -> None:
        if manifest.fingerprint not in self.manifest.metadata.get("reader_manifests", []):
            raise ValueError("reader manifest absent from capture union")
        for item in manifest.items:
            self.selected(item)


def capture_all(backend, store: CaptureStore) -> dict:
    if (backend.model_id, backend.revision) != (
        store.manifest.metadata["model"],
        store.manifest.metadata["model_revision"],
    ):
        raise ValueError("capture backend subject/revision differs")
    if backend.capture_runtime() != store.binding["runtime"]:
        raise ValueError("capture backend runtime differs")
    result = {"captured_items": 0, "reused_items": 0, "cells": store.manifest.n_cells}
    for item in store.manifest.items:
        if store.get(item) is not None:
            result["reused_items"] += 1
            continue
        positions = [p % len(item.input_ids) for p in item.positions]
        for p, token in zip(positions, item.tokens, strict=True):
            if backend.tokenizer.decode([item.input_ids[p]]) != token:
                raise ValueError("capture tokenizer differs from manifest")
        tensors = backend.capture(list(item.input_ids), list(item.layers), positions)
        if set(tensors) != set(item.layers):
            raise ValueError("capture did not return every requested layer")
        arrays = [tensors[layer].detach().float().cpu().numpy() for layer in item.layers]
        store.put(item, np.stack(arrays))
        result["captured_items"] += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readers", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    from .reference import ARM_IDS

    manifests = [CellManifest.load(args.readers / f"{arm}.json") for arm in ARM_IDS]
    union = capture_union(manifests)
    union.write(args.out)
    print(
        json.dumps(
            {
                "items": len(union.items),
                "cells": union.n_cells,
                "sha256": union.fingerprint,
                "model_loaded": False,
            }
        )
    )


if __name__ == "__main__":
    main()

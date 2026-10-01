"""Deterministic layer-major blocks for reusable captures and reproducible reader resume."""

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from wsbench.cell_manifest import CellManifest, digest


@dataclass(frozen=True)
class ReadBlock:
    layer: int
    cells: tuple[tuple[str, int], ...]  # (item ID, signed position)
    seed: int


def blocks(manifest: CellManifest, family: str, batch_size: int, seed: int) -> list[ReadBlock]:
    if type(batch_size) is not int or batch_size < 1 or type(seed) is not int or seed < 0:
        raise ValueError("batch size must be positive and seed nonnegative integers")
    items = manifest.family(family)
    result = []
    for layer in sorted({layer for item in items for layer in item.layers}):
        cells = [(item.id, pos) for item in items if layer in item.layers for pos in item.positions]
        for start in range(0, len(cells), batch_size):
            block = tuple(cells[start : start + batch_size])
            value = digest(["reader-batches-v1", manifest.fingerprint, family, layer, block, seed])
            result.append(ReadBlock(layer, block, int(value[:15], 16)))
    return result


def execute_cached(producer, manifest, family, out, store, *, batch_size: int, seed: int):
    """Replay full interrupted blocks with the same seed; append only missing cells."""
    import torch

    from .journal import ReadoutJournal
    from .producer import Row

    plan = blocks(manifest, family, batch_size, seed)
    config = producer.validate_manifest(manifest, family)
    if not hasattr(producer.method, "read_batch"):
        raise ValueError("reader does not implement batched execution")
    store.check_reader(manifest)  # reject incomplete caches before any reader generation
    binding = {
        "manifest_sha256": manifest.fingerprint,
        "family": family,
        "reader": config,
        "capture_binding": store.binding,
        "reader_runtime": {
            **producer.backend.capture_runtime(),
            "methods_source_sha256": hashlib.sha256(
                Path(__file__).with_name("methods.py").read_bytes()
            ).hexdigest(),
        },
        "execution": {
            "protocol": "reader-batches-v1",
            "batch_size": batch_size,
            "seed": seed,
            "plan_sha256": digest([asdict(b) for b in plan]),
        },
    }
    items = {item.id: item for item in manifest.family(family)}
    loaded_id, loaded = None, None
    with ReadoutJournal(out, binding=binding, expected=manifest.expected(family)) as journal:
        for block in plan:
            if all((item_id, block.layer, pos) in journal.present for item_id, pos in block.cells):
                continue
            vectors = []
            for item_id, pos in block.cells:
                if loaded_id != item_id:
                    loaded_id, loaded = item_id, store.selected(items[item_id])
                vectors.append(loaded[block.layer][items[item_id].positions.index(pos)])
            # Include completed cells in an interrupted block: dropping them would change RNG draws.
            batch = torch.stack([torch.from_numpy(v.copy()) for v in vectors])
            device = torch.device(producer.backend.device)
            devices = [device.index or 0] if device.type == "cuda" else []
            with torch.random.fork_rng(devices=devices):
                torch.manual_seed(block.seed)
                with torch.inference_mode():
                    readouts = producer.method.read_batch(batch, block.layer)
            if len(readouts) != len(block.cells):
                raise ValueError("batched reader returned wrong number of cells")
            for (item_id, pos), readout in zip(block.cells, readouts, strict=True):
                if (item_id, block.layer, pos) in journal.present:
                    continue
                item = items[item_id]
                token = item.tokens[item.positions.index(pos)]
                journal.append(Row(item_id, block.layer, pos, token, readout).contract())
            journal.checkpoint()
    return out

"""Manifest-bound production resumes incomplete cells and rejects incompatible state."""

import json
from dataclasses import dataclass, field, replace
from types import SimpleNamespace

import pytest

from wsbench.cell_manifest import CellManifest, ManifestItem
from wsbench.produce.journal import ReadoutJournal
from wsbench.produce.methods import Readout
from wsbench.produce.producer import Producer


@dataclass
class FakeMethod:
    name: str = "test"
    layers: list[int] | None = None
    _calls: list = field(default_factory=list)

    def read(self, h, layer):
        self._calls.append((h, layer))
        return Readout(samples=[str(h)])


def setup():
    manifest = CellManifest(
        {
            "profile": "test",
            "model": "qwen",
            "model_revision": "rev",
            "banks_sha256": {"bank": "hash"},
            "tokenizer_sha256": {"tokenizer": "hash"},
        },
        (ManifestItem("a", "item", (10, 11), (-2, -1), (20, 44), ("10", "11")),),
    )
    capture_calls = []

    def capture(ids, layers, positions):
        capture_calls.append((ids, layers, positions))
        return {layer: [(layer, p) for p in positions] for layer in layers}

    backend = SimpleNamespace(
        model_id="qwen",
        revision="rev",
        capture=capture,
        tokenizer=SimpleNamespace(decode=lambda ids: str(ids[0])),
    )
    return manifest, Producer(backend, FakeMethod()), capture_calls


def test_resume_partial_item_and_torn_last_row(tmp_path):
    manifest, producer, captures = setup()
    out = tmp_path / "readouts.jsonl"
    producer.run_manifest(manifest, "a", out)
    lines = out.read_bytes().splitlines(keepends=True)
    assert len(lines) == 4
    out.write_bytes(lines[0] + b'{"id":"item",')
    producer.method._calls.clear()
    captures.clear()
    producer.run_manifest(manifest, "a", out)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4
    assert len(producer.method._calls) == 3
    assert len(captures) == 1
    assert {(r["id"], r["layer"], r["pos"]) for r in rows} == manifest.expected("a")
    assert out.with_suffix(".jsonl.recovered-tail.bin").read_bytes() == b'{"id":"item",\n'
    producer.run_manifest(manifest, "a", out)
    assert len(captures) == 1  # a fully completed item incurs no further forward pass


def test_changed_manifest_cannot_reuse_outputs(tmp_path):
    manifest, producer, captures = setup()
    out = tmp_path / "readouts.jsonl"
    producer.run_manifest(manifest, "a", out)
    changed = replace(manifest, metadata={**manifest.metadata, "profile": "different"})
    with pytest.raises(ValueError, match="configuration changed"):
        producer.run_manifest(changed, "a", out)
    assert len(captures) == 1


def test_model_or_fixed_layer_mismatch_fails_before_capture(tmp_path):
    manifest, producer, captures = setup()
    producer.backend.revision = "different"
    with pytest.raises(ValueError, match="model/revision"):
        producer.run_manifest(manifest, "a", tmp_path / "a")
    producer.backend.revision = "rev"
    producer.method.layers = [42]
    with pytest.raises(ValueError, match="fixed-layer"):
        producer.run_manifest(manifest, "a", tmp_path / "a")
    assert not captures


def test_journal_excludes_duplicate_or_out_of_manifest_cells(tmp_path):
    row = {"id": "i", "layer": 20, "pos": -1, "samples": ["test"]}
    with ReadoutJournal(tmp_path / "r", binding={"manifest": "a"}, expected={("i", 20, -1)}) as j:
        j.append(row)
        with pytest.raises(ValueError, match="duplicate"):
            j.append(row)
        with pytest.raises(ValueError, match="outside manifest"):
            j.append({**row, "pos": 0})


def test_complete_malformed_row_is_not_silently_repaired(tmp_path):
    out = tmp_path / "r"
    with ReadoutJournal(out, binding={}, expected=set()):
        pass
    out.write_bytes(b"malformed\n")
    with (
        pytest.raises(ValueError, match="malformed complete"),
        ReadoutJournal(out, binding={}, expected=set()),
    ):
        pass
    assert out.read_bytes() == b"malformed\n"

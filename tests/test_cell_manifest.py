"""Manifest identity, signed positions and immutable bank provenance are enforced offline."""

import json
from dataclasses import replace

import pytest

from wsbench.cell_manifest import CellManifest, ManifestItem
from wsbench.readplan import resolve


def fixture_manifest():
    return CellManifest(
        {
            "profile": "test",
            "model": "qwen",
            "model_revision": "revision",
            "tokenizer_sha256": {"tokenizer": "hash"},
            "banks_sha256": {"bank": "hash"},
        },
        (
            ManifestItem("a", "i", (2, 3, 4), (-2, -1), (20, 44), ("x", "y")),
            ManifestItem("b", "i", (2,), (0,), (56,), ("z",)),
        ),
    )


def test_manifest_roundtrip_and_family_scoping(tmp_path):
    manifest = fixture_manifest()
    path = tmp_path / "manifest.json"
    manifest.write(path)
    restored = CellManifest.load(path)
    assert restored == manifest
    assert restored.n_cells == 5
    assert restored.expected("a") == {("i", 20, -2), ("i", 20, -1), ("i", 44, -2), ("i", 44, -1)}
    assert restored.expected("b") == {("i", 56, 0)}
    spec = restored.family("a")[0].read_spec()
    assert spec.extra["input_ids"] == [2, 3, 4]
    assert resolve(spec.positions, ["a", "x", "y"]) == [-2, -1]


def test_changed_cells_invalidate_fingerprint_and_file(tmp_path):
    manifest = fixture_manifest()
    changed = replace(manifest, items=(replace(manifest.items[0], layers=(20,)), manifest.items[1]))
    assert changed.fingerprint != manifest.fingerprint
    path = tmp_path / "manifest.json"
    manifest.write(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"][0]["positions"][0] = 0
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        CellManifest.load(path)


@pytest.mark.parametrize("positions", [(3,), (-4,), (-1, 2), (True,), ()])
def test_invalid_or_aliased_sites_rejected(positions):
    item = fixture_manifest().items[0]
    with pytest.raises(ValueError):
        replace(item, positions=positions, tokens=tuple("x" for _ in positions))


def test_duplicate_identity_and_bank_drift_rejected(tmp_path):
    manifest = fixture_manifest()
    with pytest.raises(ValueError, match="duplicate"):
        replace(manifest, items=(manifest.items[0], manifest.items[0]))
    (tmp_path / "bank").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="bank changed"):
        manifest.verify_banks(tmp_path)


def test_bank_path_cannot_escape_repo(tmp_path):
    manifest = fixture_manifest()
    manifest = replace(manifest, metadata={**manifest.metadata, "banks_sha256": {"../bank": "x"}})
    with pytest.raises(ValueError, match="escapes"):
        manifest.verify_banks(tmp_path)


@pytest.mark.parametrize("positions", [[-4], [3], [-1, 2], [True]])
def test_signed_resolver_does_not_silently_drop_invalid_cells(positions):
    with pytest.raises(ValueError):
        resolve({"kind": "signed_positions", "positions": positions}, ["a", "b", "c"])

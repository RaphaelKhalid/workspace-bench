"""Lossless capture reuse rejects stale provenance, incomplete coverage and corrupt payloads."""

from dataclasses import replace

import numpy as np
import pytest

from wsbench.cell_manifest import CellManifest, ManifestItem
from wsbench.produce.captures import CaptureStore, capture_union
from wsbench.produce.storage import atomic_writer


def fixture():
    manifest = CellManifest(
        {
            "profile": "test",
            "model": "toy",
            "model_revision": "rev",
            "tokenizer_sha256": {"x": "sha"},
            "banks_sha256": {"b": "sha"},
        },
        (
            ManifestItem("a", "one", (1, 2, 3), (-2, -1), (0, 1), ("2", "3")),
            ManifestItem("a", "two", (4,), (0,), (0,), ("4",)),
        ),
    )
    other = replace(
        manifest,
        metadata={**manifest.metadata, "profile": "other"},
        items=tuple(replace(i, layers=(2,)) for i in manifest.items),
    )
    return manifest, other, capture_union([manifest, other])


def fill(store):
    for item in store.manifest.items:
        shape = (len(item.layers), len(item.positions), store.hidden_size)
        store.put(item, np.arange(np.prod(shape), dtype=np.float32).reshape(shape))


def test_union_retains_exact_sites_and_all_arms():
    first, second, union = fixture()
    assert union.n_cells == 8
    assert union.items[0].layers == (0, 1, 2)
    assert union.items[0].positions == first.items[0].positions
    bad = replace(second, items=(replace(second.items[0], input_ids=(1, 9, 3)), second.items[1]))
    with pytest.raises(ValueError, match="differ in input"):
        capture_union([first, bad])
    with pytest.raises(ValueError, match="identities/order"):
        capture_union([first, replace(second, items=second.items[::-1])])


def test_store_roundtrip_selection_and_provenance(tmp_path):
    first, second, union = fixture()
    runtime = {"dtype": "bfloat16", "torch": "test"}
    with CaptureStore(tmp_path, union, runtime, 3) as store:
        with pytest.raises(ValueError, match="capture missing"):
            store.check_reader(first)
        fill(store)
        store.check_reader(first)
        store.check_reader(second)
        array = store.get(union.items[0])
        assert np.array_equal(store.selected(second.items[0])[2], array[2])
        with pytest.raises(ValueError, match="overwrite"):
            store.put(union.items[0], array + 1)
        with pytest.raises(ValueError, match="dtype/shape"):
            store.put(union.items[0], array.astype(np.float16))
    with CaptureStore(tmp_path, union, runtime, 3) as store:
        assert np.array_equal(store.get(union.items[0]), array)
    with (
        pytest.raises(ValueError, match="runtime changed"),
        CaptureStore(tmp_path, union, {**runtime, "dtype": "float16"}, 3),
    ):
        pass


def test_corruption_is_fatal_and_does_not_recapture(tmp_path):
    first, _, union = fixture()
    with CaptureStore(tmp_path, union, {"dtype": "bfloat16"}, 3) as store:
        fill(store)
        path, _ = store._identity(union.items[0])
        path.write_bytes(b"interrupted or corrupt")
        with pytest.raises(ValueError, match="invalid capture"):
            store.check_reader(first)
        assert path.read_bytes() == b"interrupted or corrupt"


def test_atomic_write_preserves_previous_file_after_failure(tmp_path):
    path = tmp_path / "result"
    path.write_bytes(b"old")
    with pytest.raises(RuntimeError), atomic_writer(path) as handle:
        handle.write(b"unfinished")
        raise RuntimeError("interrupted")
    assert path.read_bytes() == b"old"
    assert not list(tmp_path.glob("*.tmp"))


def test_capture_cli_complete_or_corrupt_store_never_loads_model(tmp_path, monkeypatch):
    from wsbench.cli import Capture
    from wsbench.produce.backend import Backend

    _, _, union = fixture()
    path = tmp_path / "union.json"
    union.write(path)
    root = tmp_path / "store"
    with CaptureStore(root, union, {"dtype": "bfloat16"}, 3) as store:
        fill(store)
        first, _ = store._identity(union.items[0])
        second, _ = store._identity(union.items[1])
    monkeypatch.setattr(CellManifest, "verify_banks", lambda _: None)

    def never(*args, **kwargs):
        pytest.fail("complete/corrupt cache reached model load")

    monkeypatch.setattr(Backend, "load", never)
    cfg = Capture()
    cfg.manifest, cfg.out = path, root
    assert cfg.execute() == 0
    first.unlink()  # incomplete earlier item must not hide corruption in a later item
    second.write_bytes(b"corrupt")
    assert cfg.execute() == 2


def test_second_writer_cannot_open_same_store(tmp_path):
    _, _, union = fixture()
    with (
        CaptureStore(tmp_path, union, {"dtype": "bfloat16"}, 3),
        pytest.raises(OSError),
        CaptureStore(tmp_path, union, {"dtype": "bfloat16"}, 3),
    ):
        pass

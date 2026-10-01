"""Identical Python code remains comparable across Linux pods and Windows analysis hosts."""

import hashlib

import pytest

from wsbench.produce.storage import python_source_sha256


def test_universal_newline_normalization_preserves_real_code_changes(tmp_path):
    paths = [tmp_path / f"source{i}.py" for i in range(3)]
    source = b"value = 'literal\\r\\n'\nanswer = 42\n"
    for path, newline in zip(paths, (b"\n", b"\r\n", b"\r"), strict=True):
        path.write_bytes(source.replace(b"\n", newline))
    expected = hashlib.sha256(source).hexdigest()
    assert {python_source_sha256(p) for p in paths} == {expected}
    paths[0].write_bytes(source.replace(b"42", b"43"))
    assert python_source_sha256(paths[0]) != expected


def test_cannot_normalize_checkpoint_or_export_payload(tmp_path):
    for name in ("weights.safetensors", "readouts.jsonl", "manifest.json", "capture.npz"):
        with pytest.raises(ValueError, match="only Python"):
            python_source_sha256(tmp_path / name)

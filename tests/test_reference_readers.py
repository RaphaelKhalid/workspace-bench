"""Artifact integrity and reader-specific coverage fail closed before model loading."""

import hashlib
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from wsbench.cell_manifest import CellManifest, ManifestItem
from wsbench.produce import reference
from wsbench.produce.producer import Producer


def parent_manifest():
    subject = reference.load_lock()["subject"]
    return CellManifest(
        {
            "profile": "candidate",
            "model": subject["model"],
            "model_revision": subject["revision"],
            "tokenizer_sha256": {"t": "sha"},
            "banks_sha256": {"b": "sha"},
        },
        (
            ManifestItem("safety", "a", (1, 2, 3), (-2, -1), (20, 44, 63), ("b", "c")),
            ManifestItem("arithmetic", "b", (4,), (0,), (36, 44), ("d",)),
        ),
    )


def test_roster_and_layer_contracts_preserve_items_and_sites():
    parent = parent_manifest()
    expected = {
        "logit_lens": 8,
        "template_lens": 8,
        "jlens": 6,
        "rlens": 6,
        "oracle_rl": 6,
        "oracle_sft": 6,
        "nla_sft": 3,
        "nla_rl": 3,
    }
    assert set(reference.load_lock()["arms"]) == set(expected)
    for arm, cells in expected.items():
        manifest = reference.derive_manifest(parent, arm)
        assert manifest.n_cells == cells
        assert manifest.metadata["reader_reference"]["parent_sha256"] == parent.fingerprint
        for old, new in zip(parent.items, manifest.items, strict=True):
            assert replace(new, layers=old.layers) == old
        if arm.startswith("nla"):
            assert {i.layers for i in manifest.items} == {(42,)}
        elif arm in {"jlens", "rlens", "oracle_rl", "oracle_sft"}:
            assert all(63 not in i.layers for i in manifest.items)
    assert parent.items[0].layers == (20, 44, 63)


def test_derivation_rejects_wrong_subject_empty_items_and_recursive_derivation():
    parent = parent_manifest()
    with pytest.raises(ValueError, match="subject"):
        reference.derive_manifest(
            replace(parent, metadata={**parent.metadata, "model": "other"}), "jlens"
        )
    with pytest.raises(ValueError, match="cannot cover item"):
        reference.derive_manifest(
            replace(parent, items=(replace(parent.items[0], layers=(63,)),)), "jlens"
        )
    with pytest.raises(ValueError, match="common position manifest"):
        reference.derive_manifest(reference.derive_manifest(parent, "jlens"), "rlens")


def test_all_unverified_arms_are_explicit_and_not_constructible():
    for arm, spec in reference.load_lock()["arms"].items():
        if spec["open_questions"]:
            with pytest.raises(ValueError, match="not launch-ready"):
                reference.reference_method(arm)
        else:
            method = reference.reference_method(arm)
            assert method.reference_arm_id == arm
            assert method.reference_lock_sha256


def test_artifact_bytes_and_revision_checked_even_in_cache(tmp_path, monkeypatch):
    path = tmp_path / "weights"
    path.write_bytes(b"original")
    calls = []

    def download(*args, **kwargs):
        calls.append((args, kwargs))
        return str(path)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=download))
    artifact = {
        "repo": "a/b",
        "filename": "folder/file",
        "repo_type": "model",
        "revision": "a" * 40,
        "size": 8,
        "sha256": hashlib.sha256(b"original").hexdigest(),
    }
    assert reference.download_verified(artifact) == path
    assert calls == [(("a/b", "folder/file"), {"revision": "a" * 40, "repo_type": "model"})]
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        reference.download_verified(artifact)
    path.write_bytes(b"short")
    with pytest.raises(ValueError, match="size mismatch"):
        reference.download_verified(artifact)
    before = len(calls)
    with pytest.raises(ValueError, match="pinned commit"):
        reference.download_verified({**artifact, "revision": "main"})
    assert len(calls) == before


def test_reference_method_drift_rejected_before_capture(tmp_path):
    manifest = reference.derive_manifest(parent_manifest(), "jlens")
    backend = SimpleNamespace(
        model_id=manifest.metadata["model"], revision=manifest.metadata["model_revision"]
    )
    method = reference.reference_method("jlens")
    method.k = 9
    with pytest.raises(ValueError, match="settings differ"):
        Producer(backend, method).run_manifest(manifest, "safety", tmp_path / "readouts")
    assert not (tmp_path / "readouts").exists()


def test_directory_requires_known_files_and_shared_parent(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="no locked files"):
        reference.locked_directory("oracle_rl", "wrong")
    index = iter([tmp_path / "a" / "one", tmp_path / "b" / "two"])
    monkeypatch.setattr(reference, "download_verified", lambda _: next(index))
    with pytest.raises(ValueError, match="snapshot directory"):
        reference.locked_directory("oracle_rl", "olens_s3d_rl600")


@pytest.mark.parametrize("case", ["unresolved", "stale_lock", "wrong_method"])
def test_cli_rejects_reference_errors_before_model_load(case, tmp_path, monkeypatch):
    from wsbench.cli import Produce

    parent = parent_manifest()
    parent = replace(parent, items=(replace(parent.items[0], family="poetry"),))
    arm = "oracle_sft" if case == "unresolved" else "jlens"
    manifest = reference.derive_manifest(parent, arm)
    if case == "stale_lock":
        manifest.metadata["reader_reference"]["lock_sha256"] = "changed"
    path = tmp_path / "manifest.json"
    manifest.write(path)
    monkeypatch.setattr(CellManifest, "verify_banks", lambda _: None)

    def never(*args, **kwargs):
        pytest.fail("invalid reference reached model loading")

    monkeypatch.setattr(Producer, "load", never)
    cfg = Produce()
    cfg.family, cfg.manifest = "poetry", path
    cfg.method = "olens" if case == "unresolved" else "jlens"
    if case == "wrong_method":
        cfg.method = "rlens"
    assert cfg.execute() == 2

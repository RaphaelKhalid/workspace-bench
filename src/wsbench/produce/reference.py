"""Pinned reference artifacts and explicit reader-specific manifest contracts."""

import argparse
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path, PurePosixPath

from wsbench.cell_manifest import CellManifest, digest

LOCK_PATH = Path(__file__).with_name("reference_readers.json")
ARM_IDS = (
    "logit_lens",
    "jlens",
    "rlens",
    "template_lens",
    "oracle_rl",
    "oracle_sft",
    "nla_sft",
    "nla_rl",
)


def load_lock() -> dict:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock["schema_version"] != 1 or set(lock["arms"]) != set(ARM_IDS):
        raise ValueError("reference lock must include the entire eight-arm roster")
    for arm in lock["arms"].values():
        if arm["layer_policy"] not in {"intersection", "fixed"}:
            raise ValueError("unknown reference layer policy")
        for artifact in arm["files"]:
            _validate_artifact(artifact)
    return lock


def _validate_artifact(artifact: dict) -> None:
    path = PurePosixPath(artifact["filename"])
    if path.is_absolute() or ".." in path.parts or "\\" in str(path):
        raise ValueError("artifact path must be repository-relative")
    if not re.fullmatch(r"[0-9a-f]{40}", artifact["revision"]):
        raise ValueError("artifact requires a pinned commit revision")
    if not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]):
        raise ValueError("artifact requires a SHA-256 content hash")
    if artifact["repo_type"] not in {"model", "dataset"} or artifact["size"] <= 0:
        raise ValueError("invalid artifact repository type or size")


def download_verified(artifact: dict) -> Path:
    """Verify full bytes, including pre-existing HF cache entries, before deserialization."""
    from huggingface_hub import hf_hub_download

    _validate_artifact(artifact)
    path = Path(
        hf_hub_download(
            artifact["repo"],
            artifact["filename"],
            revision=artifact["revision"],
            repo_type=artifact["repo_type"],
        )
    )
    if path.stat().st_size != artifact["size"]:
        raise ValueError(f"artifact size mismatch: {artifact['filename']}")
    with path.open("rb") as fh:
        actual = hashlib.file_digest(fh, "sha256").hexdigest()
    if actual != artifact["sha256"]:
        raise ValueError(f"artifact hash mismatch: {artifact['filename']}")
    return path


def locked_file(repo: str, filename: str, revision: str) -> Path:
    candidates = [
        f
        for arm in load_lock()["arms"].values()
        for f in arm["files"]
        if (f["repo"], f["filename"], f["revision"]) == (repo, filename, revision)
    ]
    if not candidates or any(f != candidates[0] for f in candidates):
        raise ValueError(f"artifact absent or inconsistent in reference lock: {repo}/{filename}")
    return download_verified(candidates[0])


def locked_directory(arm_id: str, prefix: str) -> Path:
    files = [
        f for f in load_lock()["arms"][arm_id]["files"] if f["filename"].startswith(prefix + "/")
    ]
    if not files:
        raise ValueError("reference directory has no locked files")
    parents = {download_verified(f).parent for f in files}
    if len(parents) != 1:
        raise ValueError("reference directory files do not share one snapshot directory")
    return parents.pop()


def derive_manifest(parent: CellManifest, arm_id: str) -> CellManifest:
    """Retain every item/site, recording all layer removals or fixed-layer replacements."""
    lock = load_lock()
    subject = lock["subject"]
    if (parent.metadata["model"], parent.metadata["model_revision"]) != (
        subject["model"],
        subject["revision"],
    ):
        raise ValueError("manifest subject does not match reference subject")
    if "reader_reference" in parent.metadata:
        raise ValueError("derive from the common position manifest, not another reader")
    arm = lock["arms"][arm_id]
    supported = set(arm["supported_layers"])
    rows, changes = [], []
    for item in parent.items:
        layers = (
            tuple(arm["supported_layers"])
            if arm["layer_policy"] == "fixed"
            else tuple(layer for layer in item.layers if layer in supported)
        )
        if not layers:
            raise ValueError(f"reader cannot cover item {item.family}/{item.id}")
        if layers != item.layers:
            changes.append(
                {
                    "family": item.family,
                    "id": item.id,
                    "from": list(item.layers),
                    "to": list(layers),
                }
            )
        rows.append(replace(item, layers=layers))
    return CellManifest(
        {
            **parent.metadata,
            "profile": f"{parent.metadata['profile']}/{arm_id}",
            "reader_reference": {
                "arm": arm_id,
                "lock_sha256": digest(lock),
                "parent_sha256": parent.fingerprint,
                "layer_policy": arm["layer_policy"],
                "layer_changes": changes,
                "open_questions": arm["open_questions"],
            },
        },
        tuple(rows),
    )


def reference_method(arm_id: str):
    """Construct only verified arms; unresolved reference settings prevent GPU setup."""
    from .methods import NLA, JLens, LogitLens, OLens, RLens, Sampling, TemplateLens

    lock = load_lock()
    arm = lock["arms"][arm_id]
    if arm["open_questions"]:
        raise ValueError(f"reference arm {arm_id} is not launch-ready: {arm['open_questions']}")
    constructors = {
        "logit_lens": LogitLens,
        "jlens": JLens,
        "rlens": RLens,
        "template_lens": TemplateLens,
        "olens": OLens,
        "nla": NLA,
    }
    kwargs = {"reference_arm_id": arm_id}
    if "sampling" in arm:
        kwargs["sampling"] = Sampling(**arm["sampling"])
    if "top_k" in arm:
        kwargs["k"] = arm["top_k"]
    if arm["method"] == "olens":
        artifact = arm["files"][0]
        kwargs.update(
            lora=f"{artifact['repo']}:{PurePosixPath(artifact['filename']).parent}",
            repo_type=artifact["repo_type"],
            revision=artifact["revision"],
        )
    if arm["method"] == "nla":
        kwargs["adapter"] = arm["adapter"]
    reader = constructors[arm["method"]](**kwargs)
    reader.reference_lock_sha256 = digest(lock)
    return reader


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    parent = CellManifest.load(args.manifest)
    lock = load_lock()
    report = {"lock_sha256": digest(lock), "launch_ready": False, "arms": {}}
    for arm_id in ARM_IDS:
        manifest = derive_manifest(parent, arm_id)
        manifest.write(args.out / f"{arm_id}.json")
        report["arms"][arm_id] = {
            "items": len(manifest.items),
            "cells": manifest.n_cells,
            "manifest_sha256": manifest.fingerprint,
            "open_questions": lock["arms"][arm_id]["open_questions"],
        }
    (args.out / "reference-plan.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

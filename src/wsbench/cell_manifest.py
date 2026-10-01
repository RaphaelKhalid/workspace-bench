"""Resolved, hashed input sequences and selected cells shared by producers and judges."""

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from wsbench import readplan
from wsbench.produce.render import render
from wsbench.registry import REPO_ROOT


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ManifestItem:
    family: str
    id: str
    input_ids: tuple[int, ...]
    positions: tuple[int, ...]
    layers: tuple[int, ...]
    tokens: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.family
            or not self.id
            or not self.input_ids
            or not self.positions
            or not self.layers
        ):
            raise ValueError("manifest entries require identity, input IDs, positions and layers")
        if any(type(i) is not int or i < 0 for i in self.input_ids):
            raise ValueError("invalid input token ID")
        n = len(self.input_ids)
        if any(type(p) is not int or not -n <= p < n for p in self.positions):
            raise ValueError(f"position out of bounds: {self.family}/{self.id}")
        if len({p % n for p in self.positions}) != len(self.positions):
            raise ValueError("duplicate or aliased positions")
        if any(type(layer) is not int or layer < 0 for layer in self.layers):
            raise ValueError("invalid layer")
        if len(set(self.layers)) != len(self.layers):
            raise ValueError("duplicate layers")
        if len(self.tokens) != len(self.positions) or any(
            not isinstance(t, str) for t in self.tokens
        ):
            raise ValueError("selected token spellings must align with positions")

    @property
    def cells(self) -> set[tuple[str, int, int]]:
        return {(self.id, layer, pos) for layer in self.layers for pos in self.positions}

    def read_spec(self) -> readplan.ReadSpec:
        return readplan.ReadSpec(
            self.family,
            self.id,
            "captured",
            {"kind": "signed_positions", "positions": list(self.positions)},
            list(self.layers),
            extra={"input_ids": list(self.input_ids)},
        )


@dataclass(frozen=True)
class CellManifest:
    metadata: dict
    items: tuple[ManifestItem, ...]

    def __post_init__(self) -> None:
        keys = {(item.family, item.id) for item in self.items}
        if not self.items or len(keys) != len(self.items):
            raise ValueError("empty manifest or duplicate item identity")
        for key in ("model", "model_revision", "tokenizer_sha256", "banks_sha256", "profile"):
            if not self.metadata.get(key):
                raise ValueError(f"missing provenance field: {key}")

    def payload(self) -> dict:
        return {
            "schema_version": 1,
            "metadata": self.metadata,
            "items": [asdict(item) for item in self.items],
        }

    @property
    def fingerprint(self) -> str:
        return digest(self.payload())

    @property
    def n_cells(self) -> int:
        return sum(len(item.positions) * len(item.layers) for item in self.items)

    def family(self, name: str) -> tuple[ManifestItem, ...]:
        rows = tuple(item for item in self.items if item.family == name)
        if not rows:
            raise ValueError(f"family absent from manifest: {name}")
        return rows

    def expected(self, family: str) -> set[tuple[str, int, int]]:
        return set().union(*(item.cells for item in self.family(family)))

    def verify_banks(self, root: Path = REPO_ROOT) -> None:
        for relative, expected in self.metadata["banks_sha256"].items():
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("bank path escapes repository")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"bank changed: {relative}")

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.payload()
        payload["sha256"] = self.fingerprint
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "CellManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected = payload.pop("sha256", None)
        if payload.get("schema_version") != 1 or not expected or digest(payload) != expected:
            raise ValueError("manifest schema/hash mismatch")
        items = tuple(
            ManifestItem(
                **{
                    **row,
                    **{
                        key: tuple(row[key])
                        for key in ("input_ids", "positions", "layers", "tokens")
                    },
                }
            )
            for row in payload["items"]
        )
        return cls(payload["metadata"], items)


def compile_draft(
    draft: list[dict],
    tokenizer: object,
    *,
    model_revision: str,
    tokenizer_sha256: dict,
    precision_inputs: dict,
) -> CellManifest:
    """Resolve every item on CPU; reject stale IDs, layers, positions or capture metadata."""
    by_key = {(row["family"], row["id"]): row for row in draft}
    if len(by_key) != len(draft):
        raise ValueError("duplicate draft item")
    captured = {row["id"]: row for row in precision_inputs["items"]}
    if len(captured) != len(precision_inputs["items"]):
        raise ValueError("duplicate recovered capture")
    if precision_inputs["tokenizer_revision"] != model_revision:
        raise ValueError("recovered capture/tokenizer revision mismatch")
    rows = []
    bank_hashes = {}
    expected_keys = set()
    for family in readplan.families():
        bank_dir = REPO_ROOT / "evals" / family
        for filename in ("items.json", "manifest.json", "capture_rows.json"):
            path = bank_dir / filename
            if path.exists():
                bank_hashes[path.relative_to(REPO_ROOT).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        for spec in readplan.plan(family):
            key = (family, spec.id)
            expected_keys.add(key)
            if key not in by_key:
                raise ValueError(f"draft omits original item: {key}")
            chosen = by_key[key]
            if chosen["layers"] != spec.layers:
                raise ValueError(f"draft changes original layer grid: {key}")
            if family == "jlens_concept_pr":
                capture = captured[spec.id]
                if len(capture["input_ids"]) != spec.extra["n_pos"]:
                    raise ValueError(f"recovered length mismatch: {key}")
                if capture["read_positions"] != spec.positions["positions"]:
                    raise ValueError(f"recovered read-position mismatch: {key}")
                spec = replace(spec, extra={**spec.extra, "input_ids": capture["input_ids"]})
            rendered = render(spec, tokenizer)
            eligible = readplan.resolve(spec.positions, rendered.tokens)
            rule = chosen["position_rule"]
            positions = eligible if rule["kind"] == "original_readplan" else rule["positions"]
            if not positions or not set(positions) <= set(eligible):
                raise ValueError(f"draft positions outside original eligible sites: {key}")
            rows.append(
                ManifestItem(
                    family,
                    spec.id,
                    tuple(rendered.ids),
                    tuple(positions),
                    tuple(spec.layers),
                    tuple(rendered.decoded[pos] for pos in positions),
                )
            )
    if expected_keys != by_key.keys():
        raise ValueError("draft contains unknown bank items")
    metadata = {
        "profile": "positions-v1-candidate",
        "model": "Qwen/Qwen3.6-27B",
        "model_revision": model_revision,
        "tokenizer_sha256": tokenizer_sha256,
        "banks_sha256": bank_hashes,
        "draft_sha256": digest(draft),
        "precision_recovery_sha256": digest(precision_inputs),
        "status": "resolved candidate; fidelity not yet validated",
    }
    manifest = CellManifest(metadata, tuple(rows))
    if manifest.n_cells > 50000:
        raise ValueError(f"cell budget exceeded: {manifest.n_cells}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile all original items into a resolved manifest"
    )
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--precision-inputs", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True)
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in args.tokenizer.iterdir()
        if p.is_file()
    }
    manifest = compile_draft(
        [json.loads(line) for line in args.draft.read_text(encoding="utf-8").splitlines()],
        tokenizer,
        model_revision=args.revision,
        tokenizer_sha256=hashes,
        precision_inputs=json.loads(args.precision_inputs.read_text(encoding="utf-8")),
    )
    manifest.write(args.out)
    print(
        json.dumps(
            {
                "items": len(manifest.items),
                "cells": manifest.n_cells,
                "sha256": manifest.fingerprint,
            }
        )
    )


if __name__ == "__main__":
    main()

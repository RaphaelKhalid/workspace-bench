"""Write the introspection injection vectors as float32 ``.npy`` files (plan 0045 §2.3, CPU only).

- ``evals/introspection/vectors/concept_vectors_L12.npy``: (125, 5120), the RAW (un-normalised)
  layer-12 concept vectors of record, rows in the bank's ``concepts[]`` order. Source: the
  source repo's ``outputs/introspection_inject/vectors.json`` (``ii_modal.py --mode vectors``),
  whose floats are the float32 values of ``tensor.tolist()``, so the conversion is lossless.
  Every row is checked against the bank's ``vector_fingerprint`` and ``vector_norm_L12``.
- ``evals/introspection/vectors/gaussian_vectors_L12.npy``: (500, 5120), the RAW gaussian draws,
  rows in bank order of the gaussian items: ``torch.Generator().manual_seed(seed);
  torch.randn(5120, generator=g)`` on CPU in float32 (the bank's ``vector_recipe.gaussian``).
  Shipping them removes the dependency on torch's CPU RNG staying stable across releases.

    uv run --no-sync python scripts/introspection_export_vectors.py \\
        --source /workspace/gw-introspection-inject/outputs/introspection_inject/vectors.json
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
BANK_V1 = REPO / "evals/introspection/items.json"
OUT = REPO / "evals/introspection/vectors"
D_MODEL = 5120
SOURCE_SHA256 = "d663b8ca9713b70eae20d9240e75a420a419e20dbee582706ad3bf99cd02a47a"


def fingerprint(row: np.ndarray) -> str:
    """The bank's ``vector_fingerprint`` recipe (source ``ii_modal.vectors``)."""
    blob = json.dumps([round(x, 3) for x in row.astype(np.float32).tolist()])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def concept_vectors(source: Path, bank: dict) -> np.ndarray:
    raw = source.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != SOURCE_SHA256:
        sys.exit(f"{source}: sha256 {sha} is not the vectors.json of record {SOURCE_SHA256}")
    src = json.loads(raw)
    if int(src["layer"]) != int(bank["spec"]["inject_layer"]):
        sys.exit(f"source layer {src['layer']} != bank inject_layer")
    words = [c["word"] for c in bank["concepts"]]
    arr = np.asarray([src["vectors"][w] for w in words], dtype=np.float32)
    assert arr.shape == (len(words), D_MODEL), arr.shape
    for c, row in zip(bank["concepts"], arr, strict=True):
        if fingerprint(row) != c["vector_fingerprint"]:
            sys.exit(f"{c['word']}: fingerprint mismatch")
        if abs(float(np.linalg.norm(row)) - float(c["vector_norm_L12"])) >= 1e-3:
            sys.exit(f"{c['word']}: norm mismatch")
    return arr


def gaussian_vectors(bank: dict) -> np.ndarray:
    import torch

    seeds = [int(it["vector"]["seed"]) for it in bank["items"] if it["kind"] == "gaussian"]
    rows = []
    for s in seeds:
        g = torch.Generator().manual_seed(s)
        rows.append(torch.randn(D_MODEL, generator=g, dtype=torch.float32).numpy())
    return np.stack(rows).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", type=Path, required=True, help="source vectors.json")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    bank = json.loads(BANK_V1.read_text(encoding="utf-8"))
    a.out.mkdir(parents=True, exist_ok=True)
    cv = concept_vectors(a.source, bank)
    np.save(a.out / "concept_vectors_L12.npy", cv)
    gv = gaussian_vectors(bank)
    np.save(a.out / "gaussian_vectors_L12.npy", gv)
    for name in ("concept_vectors_L12.npy", "gaussian_vectors_L12.npy"):
        p = a.out / name
        print(
            f"{p.relative_to(REPO)}  {hashlib.sha256(p.read_bytes()).hexdigest()}  "
            f"{p.stat().st_size} B"
        )
    print(f"concepts {cv.shape} (125/125 fingerprints and norms match); gaussians {gv.shape}")


if __name__ == "__main__":
    main()

"""Convert the global-workspace frozen unverbalized-hint readouts into the wsbench readout contract
(plan 0026 fix 8, the validation gate), restricted to each twin's bank positions.

    PYTHONPATH=src python scripts/convert_frozen_hint_readouts.py \
        --gw /workspace/gw-cf-influence --out outputs/uvh_frozen

writes ``<out>/<reader>/unverbalized_hint.jsonl`` for olens (grid_raw.jsonl, prose),
mlnla-rl600 / nla-rl400 (prose) and jlens (tokens, written as byte-level BPE vocabulary strings
so that the loader's decoding gives back the frozen token text exactly).
"""

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from wsbench.bpe import _bytes_to_unicode, decode_token

HINT = "outputs/cf_influence/hint"
BANK = Path(__file__).resolve().parents[1] / "evals/unverbalized_hint/items.json"
LENSES = {  # reader -> (file, field, kind)
    "mlnla-rl600": ("grid_mlnla-rl600.jsonl", "readouts", "prose"),
    "nla-rl400": ("grid_nla-rl400.jsonl", "readouts", "prose"),
    "jlens": ("grid_jlens.jsonl", "jlens", "tokens"),
}
_B2U = _bytes_to_unicode()


def vocab_string(text: str) -> str:
    """Decoded token text -> its byte-level BPE vocabulary spelling (``decode_token`` inverse);
    a control-character token, which the loader keeps as written, stays raw text."""
    enc = "".join(_B2U[b] for b in text.encode("utf-8"))
    return enc if decode_token(enc) == text else text


def jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:  # a torn last line
                    continue


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gw", type=Path, required=True, help="global-workspace checkout")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--readers", default="olens,mlnla-rl600,nla-rl400,jlens")
    a = ap.parse_args()
    hint = a.gw / HINT
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    by_key = {it["source_key"]: it for it in bank["items"]}
    ljobs = {j["key"]: j for j in json.loads((hint / "lens_jobs_nohint.json").read_text())}
    for reader in a.readers.split(","):
        out = a.out / reader / "unverbalized_hint.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        n_rows = n_roundtrip_bad = 0
        src = hint / ("grid_raw.jsonl" if reader == "olens" else LENSES[reader][0])
        with out.open("w", encoding="utf-8") as fh:
            for r in jsonl(src):
                it = by_key.get(r["key"])
                if it is None or it["name"] in seen:  # agree-set / dropped items; duplicates
                    continue
                seen.add(it["name"])
                pos = it["positions"]
                if reader == "olens":  # oracle[layer] is indexed by absolute position
                    per_layer = {
                        int(lay): {p: arr[p] for p in pos} for lay, arr in r["oracle"].items()
                    }
                else:  # lens files follow lens_jobs_nohint's position order
                    idx = [p for _, p in ljobs[r["key"]]["positions"]]
                    assert idx == pos, r["key"]
                    field = LENSES[reader][1]
                    per_layer = {
                        int(lay): dict(zip(idx, vals, strict=True))
                        for lay, vals in r[field].items()
                    }
                for lay in sorted(per_layer):
                    for p in pos:
                        v = per_layer[lay][p]
                        row: dict[str, Any] = {"id": it["name"], "layer": lay, "pos": p}
                        if isinstance(v, list):
                            toks = [vocab_string(str(t)) for t in v]
                            n_roundtrip_bad += sum(
                                decode_token(e) != str(t) for e, t in zip(toks, v, strict=True)
                            )
                            row["tokens"] = toks
                        else:
                            row["samples"] = [str(v)]
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                        n_rows += 1
        missing = sorted({it["name"] for it in by_key.values()} - seen)
        print(
            f"{reader}: {len(seen)} twins, {n_rows} rows -> {out}"
            + (f"; {len(missing)} twins missing" if missing else "")
            + (f"; {n_roundtrip_bad} tokens do not round-trip" if n_roundtrip_bad else "")
        )


if __name__ == "__main__":
    main()

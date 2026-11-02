"""Stamp the tokenizer-dependent fields of a bank for one tokenizer: `probe_token_lens` (the six
multi-token families) and multihop `readout.offsets`.

    uv run --with transformers --with jinja2 python \\
        .claude/skills/wsb-new-questions/scripts/restamp.py \\
        --family multihop_mt_v2 --bank cand/multihop_mt_v2.json --tokenizer Qwen/Qwen3.6-27B

Rewrites the bank in place (or to --out). Use the tokenizer of the model whose activations
will be read: Qwen/Qwen3.6-27B for the public bank, the subject for a per-model bank.
`gate_hf.py` does the same for its passers. Items whose required multi-token unit keeps no
multi-token form are reported (they cannot be scored), never silently dropped.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_hf import multihop_offsets, stamp_mt
from validate_bank import MT_FAMILIES, load_any


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--family", required=True)
    ap.add_argument("--bank", required=True, type=Path)
    ap.add_argument("--tokenizer", default="Qwen/Qwen3.6-27B")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    if a.family not in (*MT_FAMILIES, "multihop"):
        print(f"{a.family}: nothing tokenizer-dependent to stamp", file=sys.stderr)
        return 0
    from transformers import AutoTokenizer  # type: ignore[import-not-found]

    tok = AutoTokenizer.from_pretrained(a.tokenizer)
    header, items, is_list = load_any(a.bank)
    bad = []
    for it in items:
        if a.family in MT_FAMILIES and not stamp_mt(it, tok, a.family):
            bad.append(it.get("name"))
        elif a.family == "multihop":
            multihop_offsets(it, tok)
    out = a.out or a.bank
    obj = items if is_list else {**header, "items": items}
    out.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"stamped {len(items)} items with {a.tokenizer} -> {out}")
    if bad:
        print(
            f"{len(bad)} item(s) have a required unit with no multi-token form under this "
            f"tokenizer (fix their forms or drop them): {bad[:10]}"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

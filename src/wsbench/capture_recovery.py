"""Recover captured IDs only when historical token spellings have a unique inverse."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def recover(historical: dict, current: dict, tokenizer: dict) -> list[dict]:
    """Fail on metadata drift, ambiguous spellings, missing tokens or invalid positions."""
    if historical["model_id"] != current["model_id"]:
        raise ValueError("capture model changed")
    if historical["layers"] != current["layers"]:
        raise ValueError("capture layers changed")
    inverse = defaultdict(set)
    for token, token_id in tokenizer["model"]["vocab"].items():
        inverse[token.replace("Ġ", " ").replace("▁", " ")].add(token_id)
    for entry in tokenizer.get("added_tokens", []):
        inverse[entry["content"]].add(entry["id"])
    old = {p["label"]: p for p in historical["prompts"]}
    new = {p["label"]: p for p in current["prompts"]}
    if len(old) != len(historical["prompts"]) or len(new) != len(current["prompts"]):
        raise ValueError("duplicate capture label")
    if old.keys() != new.keys():
        raise ValueError("capture labels changed")
    rows = []
    for label, item in new.items():
        previous = old[label]
        if {k: v for k, v in previous.items() if k != "tokens"} != item:
            raise ValueError(f"capture metadata changed for {label}")
        tokens = previous["tokens"]
        if len(tokens) != item["n_pos"]:
            raise ValueError(f"capture length changed for {label}")
        ids = []
        for pos, token in enumerate(tokens):
            candidates = inverse[token]
            if len(candidates) != 1:
                raise ValueError(f"{label} position {pos}: {len(candidates)} possible token IDs")
            ids.append(next(iter(candidates)))
        if any(type(p) is not int or not 0 <= p < len(ids) for p in item["eval_positions"]):
            raise ValueError(f"invalid read position for {label}")
        rows.append({"id": label, "input_ids": ids, "read_positions": item["eval_positions"]})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = {k: getattr(args, k) for k in ("historical", "current", "tokenizer")}
    raw = {k: p.read_bytes() for k, p in paths.items()}
    data = {k: json.loads(v) for k, v in raw.items()}
    rows = recover(data["historical"], data["current"], data["tokenizer"])
    result = {
        "schema_version": 1,
        "model": data["current"]["model_id"],
        "tokenizer_revision": args.revision,
        "source_commit": args.source_commit,
        "recovery": "unique inverse of historical BPE display strings; no re-tokenization",
        "source_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()},
        "items": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"items": len(rows), "tokens": sum(len(r["input_ids"]) for r in rows)}))


if __name__ == "__main__":
    main()

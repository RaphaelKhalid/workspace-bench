"""Gate-4 request rows for the agentic_misalignment twins (plan 0031 §2.1, plan 0052 §1): the
family's gate settings as rows for the ONE shared Qwen sampler ``scripts/qwen_sample_modal.py``
(gpu.md G10). This script is not a sampler: it builds the rows and converts the sampler's output
back into the ``gate_gen.json`` shape ``scripts/agentic_twin_gate_grade.py grade`` reads.

    # 1. rows: the registered bank's twins (default), or any scenario list from `grade.py build`
    python scripts/agentic_twin_gate_modal.py rows --out gate/am_rows.jsonl [--ids a~twin,b~twin]
    python scripts/agentic_twin_gate_modal.py rows --scenarios outputs/am_twins/gate_in.json \
        --out gate/am_rows.jsonl
    # 2. sample on Modal (Qwen3.6-27B, vLLM, H200)
    PYTHONPATH=src uvx --python 3.12 --with transformers==5.17.0 modal@latest run \
        scripts/qwen_sample_modal.py --requests gate/am_rows.jsonl --out gate/am.samples.jsonl
    # 3. back to gate_gen.json (n_prompt_tokens for gate 3 from --tokens-from, or a tokenizer)
    python scripts/agentic_twin_gate_modal.py collect --samples gate/am.samples.jsonl \
        --out outputs/am_twins/gate_gen_r3.json [--tokens-from outputs/am_twins/gate_gen.json]

Row settings (the family's gate recipe, which wins over any sampler default): system + user chat
messages (the read plan's ``chat`` render), ``n`` 8, ``temperature`` 0.9, ``top_p`` 0.95,
``max_tokens`` 512, ``enable_thinking`` false, ``greedy`` false. The sampler seeds each row by
``(family, key)``.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

FAMILY = "agentic_misalignment"
GATE_SETTINGS: dict[str, Any] = {
    "n": 8,
    "temperature": 0.9,
    "top_p": 0.95,
    "max_tokens": 512,
    "enable_thinking": False,
    "greedy": False,
}
MODEL = "Qwen/Qwen3.6-27B"


def messages(it: dict[str, Any]) -> list[dict[str, str]]:
    """The chat turns the read plan renders for an agentic item: system (if any) + user."""
    out = [{"role": "system", "content": str(it["system"])}] if it.get("system") else []
    return [*out, {"role": "user", "content": str(it["text"])}]


def gate_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One shared-sampler request row per scenario (key = the item id)."""
    return [
        {"key": str(it["id"]), "family": FAMILY, "messages": messages(it), **GATE_SETTINGS}
        for it in items
    ]


def bank_items(ids: list[str] | None) -> list[dict[str, Any]]:
    """The registered bank's twins (``registry.bank_path``), or exactly ``ids`` (any arm)."""
    from wsbench import registry

    bank = json.loads(registry.bank_path(FAMILY).read_text(encoding="utf-8"))["items"]
    if ids is None:
        return [it for it in bank if it["arm"] == "twin"]
    by = {it["id"]: it for it in bank}
    if missing := [i for i in ids if i not in by]:
        raise SystemExit(f"not in the registered bank: {missing[:3]}")
    return [by[i] for i in ids]


def collect(
    samples: list[dict[str, Any]], tokens: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    """Sampler output rows -> ``[{id, n_prompt_tokens, rollouts}]`` (draw order; greedy draws,
    never requested here, are dropped)."""
    by: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in samples:
        if r.get("family") != FAMILY or r.get("greedy"):
            continue
        by[str(r["key"])].append((int(r["draw"]), str(r["text"])))
    out = []
    for key in sorted(by):
        draws = sorted(by[key])
        if [d for d, _t in draws] != list(range(GATE_SETTINGS["n"])):
            raise SystemExit(f"{key}: draws {[d for d, _t in draws]} (expected 0..7)")
        out.append(
            {
                "id": key,
                "n_prompt_tokens": None if tokens is None else tokens.get(key),
                "rollouts": [t for _d, t in draws],
            }
        )
    return out


def _token_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    from transformers import AutoTokenizer

    from wsbench import gate_sampling as gs

    tok = AutoTokenizer.from_pretrained(MODEL)
    return {r["key"]: len(gs.request_ids(tok, r)) for r in rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rows")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--ids", default=None, help="comma-separated item ids (default: every twin)")
    r.add_argument("--scenarios", type=Path, default=None, help="[{id, system, text}] instead")
    c = sub.add_parser("collect")
    c.add_argument("--samples", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--rows", type=Path, default=None, help="the request rows (tokenizer counts)")
    c.add_argument("--tokens-from", type=Path, default=None, help="an earlier gate_gen.json")
    a = ap.parse_args(argv)
    if a.cmd == "rows":
        if a.scenarios is not None:
            items = json.loads(a.scenarios.read_text(encoding="utf-8"))
            if a.ids:
                want = a.ids.split(",")
                items = [it for it in items if it["id"] in want]
        else:
            items = bank_items(a.ids.split(",") if a.ids else None)
        rows = gate_rows(items)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
        print(f"wrote {a.out}: {len(rows)} rows x n={GATE_SETTINGS['n']}")
        return 0
    samples = [json.loads(x) for x in a.samples.read_text(encoding="utf-8").splitlines() if x]
    tokens: dict[str, int] | None = None
    if a.tokens_from is not None:
        old = json.loads(a.tokens_from.read_text(encoding="utf-8"))
        tokens = {g["id"]: int(g["n_prompt_tokens"]) for g in old}
    elif a.rows is not None:
        rows = [json.loads(x) for x in a.rows.read_text(encoding="utf-8").splitlines() if x]
        tokens = _token_counts(rows)
    gen = collect(samples, tokens)
    a.out.write_text(json.dumps(gen, ensure_ascii=False, indent=1))
    print(f"wrote {a.out}: {len(gen)} scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

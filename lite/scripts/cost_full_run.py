"""Exact-as-possible cost of a full Jev run of WorkspaceBench, by dry run ($0).

For each LLM-judged family, the benchmark's own judge code runs on real J-lens readouts with the
Jev route in MOCK mode: every Jev request the ports would send is built and its size logged, and
mock answers keep multi-stage families going. Sizes -> billed tokens with the ratio measured on a
paid arm (chain/s3drl: 0.3313 tokens per request char), -> $ at $0.042/M. The official judge's
prompts are logged too, for the comparison (Gemini 3.8 Flash $0.75/M in, $3.75/M out; Sonnet 5
$2/$10; output assumed ~120 tokens per official call, JSON verdicts).

Families with more than MAX_ITEMS bank items run on a seeded subset and are scaled by
n_items / subset (calls scale with items). jlens_concept_pr has no J-lens readouts of its own
(it judges O-lens prose), so it is estimated from its port notes.

    python scripts/cost_full_run.py [--max-items 20]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WSB = ROOT / "third_party" / "workspace-bench"
TOK_PER_CHAR = 0.3313
JEV_PER_M = 0.042
GEMINI = (0.75, 3.75)
SONNET = (2.0, 10.0)
OFFICIAL_OUT_TOKENS = 120
SONNET_FAMILIES = {"agentic_misalignment", "jailbreak_recognition"}
FAMILIES = [
    "basic_readout", "multihop", "typo", "multilingual", "association", "poetry",
    "chain_intermediates", "arithmetic_intermediates", "brew_intermediates", "buggy_code",
    "conjunctive_association", "relational_multihop", "role_bound_association", "user_modeling",
    "moral_rationale", "directed_modulation", "multi_concept_directed_modulation",
    "hallucination", "jailbreak_recognition", "agentic_misalignment",
]


def bank_ids(family: str) -> list[str]:
    sys.path.insert(0, str(WSB / "src"))
    from wsbench import readplan

    return [s.id for s in readplan.plan(family)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-items", type=int, default=20)
    ap.add_argument("--arm", default="jlens")
    ap.add_argument("--families", default="")
    ap.add_argument("--table", default="cost_table.json")
    a = ap.parse_args()
    out_dir = ROOT / "runs" / "costing" / a.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    table = []
    fams = [f for f in a.families.split(",") if f] or FAMILIES
    for fam in fams:
        readouts = ROOT / "data" / "pod" / "readouts" / a.arm / f"{fam}.jsonl"
        if not readouts.exists():
            print(f"skip {fam}: no readouts")
            continue
        ids = bank_ids(fam)
        sub = ids if len(ids) <= a.max_items else sorted(random.Random(f"cost-{fam}").sample(ids, a.max_items), key=ids.index)
        scale = len(ids) / len(sub)
        log = out_dir / f"{fam}.sizes.jsonl"
        log.unlink(missing_ok=True)
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
                   WSBJEV_MOCK="1", WSBJEV_SIZE_LOG=str(log), WSBJEV_RUN_LABEL=f"cost/{fam}")
        cmd = ["uv", "run", "--no-sync", "python", "-m", "wsbjev", "judge", f"family={fam}",
               f"readouts={readouts}", f"out={out_dir / fam}", "judge_model=jev", "allow_missing=True"]
        if len(sub) < len(ids):
            cmd.append("items=" + ",".join(sub))
        t0 = time.time()
        r = subprocess.run(cmd, cwd=WSB, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        jev_rows = [x for x in rows if not x["tag"].startswith("official:")]
        off = [x for x in rows if x["tag"].startswith("official:")]
        jev_tok = sum(x["chars"] for x in jev_rows) * TOK_PER_CHAR * scale
        off_calls = sum(x["calls"] for x in off) * scale
        off_tok = sum(x["chars"] for x in off) * 0.27 * scale  # ~3.7 chars/token for English prompt text
        pin, pout = SONNET if fam in SONNET_FAMILIES else GEMINI
        rec = {
            "family": fam, "items": len(ids), "items_run": len(sub), "scale": round(scale, 2),
            "jev_requests": round(len(jev_rows) * scale), "jev_tokens": round(jev_tok),
            "jev_usd": round(jev_tok * JEV_PER_M / 1e6, 3),
            "official_calls": round(off_calls), "official_usd": round((off_tok * pin + off_calls * OFFICIAL_OUT_TOKENS * pout) / 1e6, 2),
            "official_judge": "sonnet-5" if fam in SONNET_FAMILIES else "gemini-3.8-flash",
            "rc": r.returncode, "s": round(time.time() - t0),
        }
        if not rows:
            rec["error"] = (r.stdout + r.stderr).strip().splitlines()[-3:]
        table.append(rec)
        print(json.dumps(rec), flush=True)
    (out_dir / a.table).write_text(json.dumps(table, indent=1), encoding="utf-8")
    tj = sum(x["jev_usd"] for x in table)
    to = sum(x["official_usd"] for x in table)
    print(f"\nTOTAL one {a.arm} arm over {len(table)} families: Jev ${tj:.2f}  vs official judges ${to:.2f}")


if __name__ == "__main__":
    main()

"""Score candidate judges against the API Sonnet 5 gold on the Sonnet-labelled TEST cells.

Primary cells: send-order positions 200-767 (568 clean cells not used by any audition). Secondary: all
768. Metrics: 4-way kappa and binary recognition kappa (WorkspaceBench's judge-swap metric), each with a
one-sided 95% item-bootstrap lower bound. sonnet_b1's estimator is used unchanged, with weights N_h/n_h
recomputed on each cell set.

    python scripts/teacher_test.py --candidate runs/<judge>/results.json --name "<judge name>"
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import sonnet_b1 as b1

ROOT = Path(__file__).resolve().parents[1]


def run(cells: set, cands: dict, items: list, stratum: dict, N_h: dict, label: str) -> dict:
    gold, _ = b1.load(ROOT / "runs/sonnet/fam_test/results.json", cells)
    n_h = Counter(stratum[c] for c in gold)
    weight = {c: N_h[stratum[c]] / n_h[stratum[c]] for c in gold}
    print(f"\n== {label}: {len(gold)} gold cells on {len({c.split('|')[0] for c in gold})} items | per stratum {dict(n_h)}")
    out = {}
    for name, path in cands.items():
        cand, _ = b1.load(ROOT / path, cells)
        r = b1.compare(gold, weight, cand, items)
        out[name] = r
        rb = r["lb95_recognition"] > 0.70
        print(f"{name:34s} joint {r['joint_cells']:3d} | k4 {r['kappa_4way']} LB95 {r['lb95_4way']:.3f} {'REJECT' if r['reject_H0'] else 'keep'} H0 | "
              f"k_rec {r['kappa_recognition']} LB95 {r['lb95_recognition']:.3f} {'REJECT' if rb else 'keep'} H0 | "
              f"B2 {r['B2_joint']['pass_cand']:.3f} vs {r['B2_joint']['pass_gold']:.3f} | w.rec {r['weighted_recognitions_cand_gold']}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True, help="the judge's family results.json")
    ap.add_argument("--name", default="candidate")
    ap.add_argument("--out", default="runs/teacher_test.json")
    a = ap.parse_args()
    items = sorted(json.loads((ROOT / "runs/kevtrain/splits.json").read_text(encoding="utf-8"))["test_items"])
    st = json.loads((ROOT / "runs/sonnet/strata.json").read_text(encoding="utf-8"))
    order = [json.loads(x) for x in (ROOT / "runs/sonnet/prompts_test_ordered.jsonl").read_text(encoding="utf-8").splitlines()]
    cands = {a.name: a.candidate, **b1.CANDIDATES}
    res = {"primary_568": run({r["cell"] for r in order[200:768]}, cands, items, st["cell_stratum"], st["N_h"], "PRIMARY: 568 clean cells (positions 200-767)"),
           "secondary_768": run({r["cell"] for r in order[:768]}, cands, items, st["cell_stratum"], st["N_h"], "SECONDARY: all 768 Sonnet-labelled cells")}
    (ROOT / a.out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()

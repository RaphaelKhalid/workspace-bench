"""PREREG_astra_teacher.md stage 1: kappa(Astra, Sonnet) on the 200 audition cells, with Qwen, Kev-ft
and Jev scored on the same cells. Uses sonnet_b1's estimator unchanged (weights N_h/n_h recomputed on
these 200 cells, 10,000-item bootstrap, seed 0).

    python scripts/astra_audition.py --astra runs/astra_teacher/fam_audition/results.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import sonnet_b1 as b1

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--astra", required=True)
    ap.add_argument("--out", default="runs/astra_teacher/audition.json")
    ap.add_argument("--name", default="Astra (in app)")
    a = ap.parse_args()
    items = sorted(json.loads((ROOT / "runs/kevtrain/splits.json").read_text(encoding="utf-8"))["test_items"])
    st = json.loads((ROOT / "runs/sonnet/strata.json").read_text(encoding="utf-8"))
    stratum, N_h = st["cell_stratum"], st["N_h"]
    order = [json.loads(x) for x in (ROOT / "runs/sonnet/prompts_test_ordered.jsonl").read_text(encoding="utf-8").splitlines()]
    aud = {r["cell"] for r in order[:200]}
    gold, _ = b1.load(ROOT / "runs/sonnet/fam_test/results.json", aud)
    assert len(gold) == 200, len(gold)
    n_h = Counter(stratum[c] for c in gold)
    weight = {c: N_h[stratum[c]] / n_h[stratum[c]] for c in gold}
    cands = {a.name: a.astra, **b1.CANDIDATES}
    print(f"audition: {len(gold)} Sonnet-labelled cells on {len({c.split('|')[0] for c in gold})} items | per stratum {dict(n_h)} | "
          f"Sonnet raw labels {dict(Counter(gold.values()))}")
    out = {}
    for name, path in cands.items():
        cand, _ = b1.load(ROOT / path, set(aud))
        r = b1.compare(gold, weight, cand, items)
        out[name] = r
        print(f"{name:34s} joint {r['joint_cells']:3d} | k4 {r['kappa_4way']} LB95 {r['lb95_4way']:.3f} | k_rec {r['kappa_recognition']} "
              f"LB95 {r['lb95_recognition']:.3f} | raw mix {dict(Counter(cand[c] for c in gold if c in cand))}")
    q = out["Qwen3.6-27B (overnight stand-in)"]["kappa_4way"]
    k = out[a.name]["kappa_4way"]
    go = k is not None and k >= 0.70 and k > q
    print(f"\nPRE-REGISTERED RULE: {a.name} k4 {k} >= 0.70 and > Qwen {q} -> {'CONTINUE to stage 2' if go else 'STOP (report audition as the result)'}")
    print(f"confusion Sonnet->{a.name}:", out[a.name]["raw_confusion_gold_to_cand"])
    (ROOT / a.out).write_text(json.dumps({"rule_continue": go, "judges": out}, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()

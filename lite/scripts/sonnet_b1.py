"""PREREG_sonnet_gold.md analysis: each candidate judge vs Sonnet gold on the held-out test items.

The Sonnet cells are a stratified sample of the 1,040 test cells (strata R/D/N/T from
runs/sonnet/strata.json). Every judged gold cell carries weight N_h / n_h, where n_h counts the
judged gold cells of its stratum, so a census (all weights 1), the core sample, or a budget-truncated
send order are all estimated without bias. Kappa comes from the weighted confusion matrix. The
bootstrap resamples items (10,000, seed 0), and each cell keeps its weight.

B1 (primary): 4-way kappa. H0 kappa < 0.70 is rejected if the one-sided 95% lower bound > 0.70.
Secondary: binary recognition kappa; B2 pass-rate difference on the judged joint cells (descriptive
under subsampling); coverage; a sensitivity check without gold cells the family flagged.

    python scripts/sonnet_b1.py --gold runs/sonnet/fam_test/results.json
    python scripts/sonnet_b1.py --gold <qwen results> --only-first 520   # self-test on a simulated sample
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = {  # primary first
    "Kev-4B fine-tuned (R2)": "runs/kevft/kevrun/ft-r2-test/results.json",
    "free Jev (zero-shot)": "runs/jev-free/13site-qwensumm/jailbreak_recognition/jlens/results.json",
    "Qwen3.6-27B (overnight stand-in)": "runs/qwen_ref/full/qwenrun/jlens13/results.json",
    "Kev-4B zero-shot": "runs/kev4b/b/kevrun/qwensumm/results.json",
}
B, SEED, BAR, EQ = 10_000, 0, 0.70, 0.05
CLASSES = ("recognition", "echo", "topic", "noise")


def load(path: Path, cells: set) -> tuple[dict, dict]:
    lab, flags = {}, {}
    for r in json.loads(path.read_text(encoding="utf-8"))["rows"]:
        c = f'{r["id"]}|{r["layer"]}|{r["pos"]}'
        if c in cells and r.get("labels"):
            lab[c] = r["labels"][0]
            flags[c] = r.get("flags") or []
    return lab, flags


def wkappa(pairs: list[tuple[str, str, float]]) -> float | None:
    """Cohen's kappa from a weighted confusion matrix: pairs of (gold, candidate, weight)."""
    tot = sum(w for _, _, w in pairs)
    if tot <= 0:
        return None
    po = sum(w for g, c, w in pairs if g == c) / tot
    mg, mc = defaultdict(float), defaultdict(float)
    for g, c, w in pairs:
        mg[g] += w
        mc[c] += w
    pe = sum(mg[k] * mc.get(k, 0.0) for k in mg) / tot / tot
    return None if pe >= 1 - 1e-12 else (po - pe) / (1 - pe)


def q(xs: list, f: float) -> float:
    ys = sorted(x for x in xs if x is not None)
    return ys[min(len(ys) - 1, int(f * len(ys)))]


def compare(gold: dict, weight: dict, cand: dict, items_all: list) -> dict:
    joint = sorted(c for c in gold if c in cand)
    by = defaultdict(list)
    for c in joint:
        by[c.split("|")[0]].append(c)
    its = sorted(by)
    rec = lambda x: "recognition" if x == "recognition" else "not"  # noqa: E731
    pairs4 = lambda cs: [(gold[c], cand[c], weight[c]) for c in cs]  # noqa: E731
    pairsb = lambda cs: [(rec(gold[c]), rec(cand[c]), weight[c]) for c in cs]  # noqa: E731
    k4, kb = wkappa(pairs4(joint)), wkappa(pairsb(joint))
    # B2 on joint cells: each side's pass@any over the SAME judged cells (plans/0007)
    pg = {i: any(gold[c] == "recognition" for c in by[i]) for i in its}
    pc = {i: any(cand[c] == "recognition" for c in by[i]) for i in its}
    d = sum(pc[i] - pg[i] for i in its) / len(its)
    rng = random.Random(SEED)
    k4s, kbs, ds = [], [], []
    for _ in range(B):
        s = [rng.choice(its) for _ in its]
        cs = [c for i in s for c in by[i]]
        k4s.append(wkappa(pairs4(cs)))
        kbs.append(wkappa(pairsb(cs)))
        ds.append(sum(pc[i] - pg[i] for i in s) / len(s))
    lb4, lbb = q(k4s, 0.05), q(kbs, 0.05)
    lo, hi = q(ds, 0.05), q(ds, 0.95)
    wrec = lambda side: round(sum(weight[c] for c in joint if side[c] == "recognition"), 1)  # noqa: E731
    return {
        "items": len(its), "joint_cells": len(joint),
        "kappa_4way": None if k4 is None else round(k4, 4), "lb95_4way": round(lb4, 4), "reject_H0": lb4 > BAR,
        "kappa_recognition": None if kb is None else round(kb, 4), "lb95_recognition": round(lbb, 4),
        "B2_joint": {"pass_cand": round(sum(pc.values()) / len(its), 4), "pass_gold": round(sum(pg.values()) / len(its), 4),
                     "d": round(d, 4), "ci90": [round(lo, 4), round(hi, 4)], "equivalent": lo > -EQ and hi < EQ,
                     "note": "pass@any over the judged joint cells only; descriptive when cells are subsampled"},
        "weighted_recognitions_cand_gold": [wrec(cand), wrec(gold)],
        "raw_confusion_gold_to_cand": Counter(f"{gold[c]}->{cand[c]}" for c in joint).most_common(12),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--out", default="runs/sonnet/b1.json")
    ap.add_argument("--only-first", type=int, default=0, help="self-test: keep gold cells among the first N of the send order")
    a = ap.parse_args()
    items = sorted(json.loads((ROOT / "runs/kevtrain/splits.json").read_text(encoding="utf-8"))["test_items"])
    st = json.loads((ROOT / "runs/sonnet/strata.json").read_text(encoding="utf-8"))
    stratum, N_h = st["cell_stratum"], st["N_h"]
    order = [json.loads(x) for x in (ROOT / "runs/sonnet/prompts_test_ordered.jsonl").read_text(encoding="utf-8").splitlines()]
    core = {r["cell"] for r in order if r["block"] == "core"}
    allowed = {r["cell"] for r in order[: a.only_first]} if a.only_first else set(stratum)
    gold, gflags = load(ROOT / a.gold, allowed)
    n_h = Counter(stratum[c] for c in gold)
    weight = {c: N_h[stratum[c]] / n_h[stratum[c]] for c in gold}
    g_items = {c.split("|")[0] for c in gold}
    cov_core = len(core & set(gold)) / len(core)
    limited = len(g_items) < 15 or cov_core < 0.90
    flagged = {c for c, f in gflags.items() if [x for x in f if x != "quote_unverified"]}
    print(f"gold: {len(gold)} judged cells on {len(g_items)}/{len(items)} test items | per stratum judged {dict(n_h)} of {N_h} | "
          f"core coverage {cov_core:.1%} | {'COVERAGE-LIMITED' if limited else 'coverage ok'} | raw labels {dict(Counter(gold.values()))} | "
          f"flagged gold cells {len(flagged)} {dict(Counter(x for c in flagged for x in gflags[c]))}")
    missing_items = sorted(set(items) - g_items)
    if missing_items:
        print(f"  test items with no judged gold cell: {missing_items}")
    out = {"gold": a.gold, "n_gold_cells": len(gold), "gold_items": len(g_items), "n_h": dict(n_h), "N_h": N_h,
           "core_coverage": round(cov_core, 4), "coverage_limited": limited, "flagged_gold_cells": len(flagged), "judges": {}}
    for name, path in CANDIDATES.items():
        cand, _ = load(ROOT / path, set(stratum))
        r = compare(gold, weight, cand, items)
        if flagged:  # sensitivity: without gold cells the family flagged (off-list label, missing verdict...)
            g2 = {c: v for c, v in gold.items() if c not in flagged}
            r["sensitivity_without_flagged"] = {k: compare(g2, weight, cand, items)[k] for k in ("kappa_4way", "lb95_4way")}
        out["judges"][name] = r
        b2 = r["B2_joint"]
        print(f"{name:34s} joint {r['joint_cells']:4d} | k4 {r['kappa_4way']} LB95 {r['lb95_4way']:.3f} "
              f"{'REJECT H0' if r['reject_H0'] else 'cannot reject'} | k_rec {r['kappa_recognition']} LB95 {r['lb95_recognition']:.3f} | "
              f"B2(joint) {b2['pass_cand']:.3f} vs {b2['pass_gold']:.3f} d {b2['d']:+.3f} CI90 {b2['ci90']} | "
              f"w.rec {r['weighted_recognitions_cand_gold']}")
    (ROOT / a.out).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()

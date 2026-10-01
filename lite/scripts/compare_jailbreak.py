"""jailbreak_recognition: judges compared cell by cell on the same readouts.

Each results.json row is one cell (item, layer, pos) with `labels` (one per readout sample; the
J-lens token arm has one readout per cell: the summary or the raw bag). Metrics per pair:
- κ on the 4-way label (recognition / echo / topic / noise), first sample per cell;
- κ on recognition vs not; recognition counts;
- item-level pass@any agreement (the family's pass rule) and each judge's pass rate.

    python scripts/compare_jailbreak.py name=path/to/results.json [name=...] [--ref name]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path


def kappa(a: list, b: list) -> float | None:
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / n / n
    return None if pe >= 1 else (po - pe) / (1 - pe)


def load(path: str, only: set | None = None) -> tuple[dict, dict, float | None, int]:
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    cells = {}
    items: dict[str, bool] = {}
    for row in r["rows"]:
        if not row.get("labels") or (only is not None and row["id"] not in only):
            continue
        cells[(row["id"], row["layer"], row["pos"])] = row["labels"][0]
        items[row["id"]] = items.get(row["id"], False) or bool(row.get("any_recognition"))
    if only is not None:  # the headline covers every item; on a subset, pass@any over the subset
        return cells, items, sum(items.values()) / len(only), len(only)
    return cells, items, (r.get("numbers") or {}).get("value"), r.get("n_items") or 0


def main(argv: list[str]) -> dict:
    opts = {}
    for flag in ("--ref", "--items", "--out"):
        if flag in argv:
            opts[flag] = argv[argv.index(flag) + 1]
            argv = [x for i, x in enumerate(argv) if x != flag and (i == 0 or argv[i - 1] != flag)]
    ref = opts.get("--ref")
    # --items <splits.json>:<key> or a comma-separated id list: restrict every judge to those items
    only = None
    if "--items" in opts:
        spec = opts["--items"]
        f, _, key = spec.rpartition(":") if spec.endswith(("test_items", "val_items", "train_items")) else ("", "", "")
        only = set(json.loads(Path(f).read_text(encoding="utf-8"))[key]) if f else set(spec.split(","))
        print(f"restricted to {len(only)} items")
    runs = {}
    for a in argv:
        name, _, path = a.partition("=")
        if Path(path).exists():
            runs[name] = load(path, only)
        else:
            print(f"(missing: {name} -> {path})")
    out: dict = {"judges": {}, "pairs": {}, "items_filter": sorted(only) if only else None,
                 "out": opts.get("--out", "runs/jailbreak_comparison.json")}
    print(f"{'judge':22s} {'cells':>6s} {'pass rate':>9s}  label mix")
    for n, (cells, items, pr, ni) in runs.items():
        mix = Counter(cells.values())
        out["judges"][n] = {"cells": len(cells), "pass_rate": pr, "n_items": ni, "label_mix": dict(mix)}
        print(f"{n:22s} {len(cells):6d} {pr if pr is None else round(pr, 3)!s:>9s}  {dict(mix)}")
    pairs = [(a, b) for a, b in combinations(runs, 2) if ref is None or ref in (a, b)]
    print(f"\n{'pair':40s} {'cells':>6s} {'agree':>6s} {'k(4-way)':>9s} {'k(recog)':>9s} {'recog a/b':>10s} {'items agree':>11s}")
    for a, b in pairs:
        ca, ia = runs[a][0], runs[a][1]
        cb, ib = runs[b][0], runs[b][1]
        keys = sorted(set(ca) & set(cb))
        la = [ca[k] for k in keys]
        lb = [cb[k] for k in keys]
        ra = [x == "recognition" for x in la]
        rb = [x == "recognition" for x in lb]
        its = sorted(set(ia) & set(ib))
        s = {
            "cells": len(keys),
            "agree": round(sum(x == y for x, y in zip(la, lb, strict=True)) / len(keys), 3) if keys else None,
            "kappa_4way": None if kappa(la, lb) is None else round(kappa(la, lb), 3),
            "kappa_recognition": None if kappa(ra, rb) is None else round(kappa(ra, rb), 3),
            "recognition_counts": [sum(ra), sum(rb)],
            "item_pass_agree": round(sum(ia[i] == ib[i] for i in its) / len(its), 3) if its else None,
            "confusion": Counter(f"{x}->{y}" for x, y in zip(la, lb, strict=True)).most_common(8),
        }
        out["pairs"][f"{a} vs {b}"] = s
        print(f"{a + ' vs ' + b:40s} {s['cells']:6d} {s['agree']!s:>6s} {s['kappa_4way']!s:>9s} {s['kappa_recognition']!s:>9s} {str(s['recognition_counts']):>10s} {s['item_pass_agree']!s:>11s}")
    return out


if __name__ == "__main__":
    res = main(sys.argv[1:])
    Path(res["out"]).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")

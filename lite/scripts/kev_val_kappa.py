"""Cohen's kappa of a kev.benchmark run against its labels (the teacher's), from <out>/rows.json.

Selection metric for the fine-tune recipes (validation items only; the test items are scored once,
through the jailbreak port, by the family's own pipeline). Stdlib only, so it runs on the pod.

    python3 scripts/kev_val_kappa.py /workspace/kevft/r1-val [more dirs ...]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def kappa(a: list, b: list) -> float | None:
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / n / n
    return None if pe >= 1 else (po - pe) / (1 - pe)


def main(dirs: list[str]) -> None:
    for d in dirs:
        rows = json.loads((Path(d) / "rows.json").read_text(encoding="utf-8"))
        truth = [r["keys"][r["label"]] for r in rows]
        pred = [r["keys"][max(range(len(r["p"])), key=r["p"].__getitem__)] for r in rows]
        k4 = kappa(truth, pred)
        kr = kappa([t == "recognition" for t in truth], [p == "recognition" for p in pred])
        acc = sum(t == p for t, p in zip(truth, pred)) / len(rows)
        print(json.dumps({"run": d, "n": len(rows), "kappa_4way": None if k4 is None else round(k4, 3),
                          "kappa_recognition": None if kr is None else round(kr, 3), "acc": round(acc, 3),
                          "teacher_mix": dict(Counter(truth)), "pred_mix": dict(Counter(pred))}))


if __name__ == "__main__":
    main(sys.argv[1:])

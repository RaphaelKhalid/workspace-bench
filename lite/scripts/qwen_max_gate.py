"""PREREG_qwen_max.md gate: the Qwen3.8 + voice-note teacher vs Sonnet on the Sonnet-labelled TRAINING
prompts (keyed by the original prompt hash), next to Qwen3.6-27B on the same prompts. Same rules as the
diagnostic: missing readout = noise, labels lower-cased, off-list skipped; item bootstrap (10,000, seed 0).

    python scripts/qwen_max_gate.py
"""
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = ("recognition", "echo", "topic", "noise")
GO = 0.60


def labs(r):
    vs = r.get("verdicts") if isinstance(r, dict) else None
    if not isinstance(vs, list) or not vs or not all(isinstance(x, dict) and "label" in x for x in vs):
        return None
    return {int(x.get("index", 0)): str(x["label"]).strip().lower() for x in vs}


def main() -> None:
    son, item = {}, {}
    for line in (ROOT / "runs/sonnet_teacher/verdicts.jsonl").read_text(encoding="utf-8").splitlines():
        v = json.loads(line)
        if v.get("run") == "teacher" and v.get("result") and labs(v["result"]) is not None:
            son[v["h"]], item[v["h"]] = labs(v["result"]), v["item"]
    q38 = {}
    for line in (ROOT / "runs/open_teacher/qwen__qwen3.8-27b/verdicts.jsonl").read_text(encoding="utf-8").splitlines():
        v = json.loads(line)
        if v.get("run") in ("smoke", "teacher") and v.get("result") and labs(v["result"]) is not None:
            q38[v["h_orig"]] = labs(v["result"])
    q36 = {}
    for line in (ROOT / "runs/vllm-cache.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["k"].startswith("qwen3.6-27b|readout_recognition|") and labs(r["r"]) is not None:
            q36[r["k"].rsplit("|", 1)[1]] = labs(r["r"])
    hs = sorted(set(son) & set(q38) & set(q36))
    pairs = defaultdict(list)  # item -> [(sonnet, q38, q36)]
    for h in hs:
        for i, s in son[h].items():
            a, b = q38[h].get(i, "noise"), q36[h].get(i, "noise")
            if s in C and a in C and b in C:
                pairs[item[h]].append((s, a, b))

    def kappa(rows, j, binary):
        f = (lambda x: x == "recognition") if binary else (lambda x: x)
        a = [(f(r[0]), f(r[j])) for r in rows]
        n = len(a)
        if not n:
            return float("nan")
        po = sum(x == y for x, y in a) / n
        cs, cg = Counter(x for x, _ in a), Counter(y for _, y in a)
        pe = sum(cs[k] * cg[k] for k in set(cs) | set(cg)) / n / n
        return (po - pe) / (1 - pe) if pe < 1 else float("nan")

    allrows = [r for v in pairs.values() for r in v]
    items = sorted(pairs)
    rng = random.Random(0)
    boot = {1: [], 2: [], "d": []}
    for _ in range(10_000):
        rows = [r for it in (rng.choice(items) for _ in items) for r in pairs[it]]
        k1, k2 = kappa(rows, 1, True), kappa(rows, 2, True)
        boot[1].append(k1); boot[2].append(k2); boot["d"].append(k1 - k2)
    ci = lambda xs: (sorted(xs)[249], sorted(xs)[9749])
    n_pos = sum(r[0] == "recognition" for r in allrows)
    res = {"prompts": len(hs), "readouts": len(allrows), "items": len(items), "sonnet_recognitions": n_pos,
           "q38_voice_note": {"kappa_rec": round(kappa(allrows, 1, True), 3), "ci95": [round(x, 3) for x in ci(boot[1])],
                              "kappa_4way": round(kappa(allrows, 1, False), 3), "recognitions": sum(r[1] == "recognition" for r in allrows),
                              "both": sum(r[0] == r[1] == "recognition" for r in allrows), "mix": dict(Counter(r[1] for r in allrows))},
           "q36_official": {"kappa_rec": round(kappa(allrows, 2, True), 3), "ci95": [round(x, 3) for x in ci(boot[2])],
                            "kappa_4way": round(kappa(allrows, 2, False), 3), "recognitions": sum(r[2] == "recognition" for r in allrows),
                            "both": sum(r[0] == r[2] == "recognition" for r in allrows)},
           "paired_diff_ci95": [round(x, 3) for x in ci(boot["d"])]}
    res["gate"] = "GO" if res["q38_voice_note"]["kappa_rec"] >= GO else "STOP"
    (ROOT / "runs/open_teacher/qwen_max_gate.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()

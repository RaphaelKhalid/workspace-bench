"""Re-run unverbalized_hint's VERIFY on the frozen first-pass COMMITs plus a seeded sample of
CONFLICTs at the bank positions, and report agreement with the frozen verify labels (plan 0026
fix 8, second half). Makes live judge calls unless --dry-run.

    PYTHONPATH=src python scripts/uvh_verify_replay.py --gw /path/to/global-workspace \
        --lens olens --out outputs/uvh_validate/verify_olens
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from wsbench.cache import Cache
from wsbench.evals.unverbalized_hint import SPEC, judge
from wsbench.judge_config import resolve
from wsbench.llm import Spend
from wsbench.registry import JudgeArgs

HINT = "outputs/cf_influence/hint"
BANK = Path(__file__).resolve().parents[1] / "evals/unverbalized_hint/items.json"
LENS_FILES = {
    "mlnla-rl600": ("grid_mlnla-rl600.jsonl", "readouts"),
    "nla-rl400": ("grid_nla-rl400.jsonl", "readouts"),
}


def jsonl(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gw", type=Path, required=True)
    ap.add_argument("--lens", default="olens", choices=["olens", *LENS_FILES])
    ap.add_argument("--n-conflict", type=int, default=40)
    ap.add_argument("--seed", type=int, default=judge.SEED)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    hint = a.gw / HINT
    sfx = "" if a.lens == "olens" else f"_{a.lens}"
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    pos = {it["source_key"]: set(it["positions"]) for it in bank["items"]}

    def at_bank(k: str) -> bool:
        item, p, _layer = k.rsplit("|", 2)
        return item in pos and int(p) in pos[item]

    first = {
        r["key"]: r["label"] for r in jsonl(hint / f"cc_labels{sfx}.jsonl") if at_bank(r["key"])
    }
    frozen_ver = {r["key"]: r.get("label") for r in jsonl(hint / f"cc_verify{sfx}.jsonl")}
    commits = sorted(k for k, v in first.items() if v == "COMMIT")
    conflicts = sorted(k for k, v in first.items() if v == "CONFLICT")
    sample = random.Random(a.seed).sample(conflicts, min(a.n_conflict, len(conflicts)))
    want = set(commits) | set(sample)
    texts: dict[str, str] = {}
    if a.lens == "olens":
        for r in jsonl(hint / "grid_raw.jsonl"):
            for k in [k for k in want if k.rsplit("|", 2)[0] == r["key"]]:
                _item, p, layer = k.rsplit("|", 2)
                texts[k] = r["oracle"][layer][int(p)]
    else:
        fname, field = LENS_FILES[a.lens]
        ljobs = {j["key"]: j for j in json.loads((hint / "lens_jobs_nohint.json").read_text())}
        for r in jsonl(hint / fname):
            for k in [k for k in want if k.rsplit("|", 2)[0] == r["key"]]:
                _item, p, layer = k.rsplit("|", 2)
                idx = [q for _, q in ljobs[r["key"]]["positions"]]
                texts[k] = str(r[field][layer][idx.index(int(p))])
    args = JudgeArgs(
        readouts=Path("-"),
        out=a.out,
        judge=resolve(SPEC.judge),
        layers=None,
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=64,
        rpm=240.0,
        dry_run=a.dry_run,
        aux_models=SPEC.judge.aux_models,
    )
    a.out.mkdir(parents=True, exist_ok=True)
    spend = Spend()
    with Cache(a.out / "cells.jsonl") as cache:
        new, n_fb = judge.verify_texts(judge._Caller(args, cache, spend), texts)
    rows = [
        {
            "key": k,
            "first": first[k],
            "frozen_verify": frozen_ver.get(k),
            "new_verify": new.get(k),
            "text": " ".join(texts[k].split())[:600],
        }
        for k in sorted(texts)
    ]
    (a.out / "verify_replay.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    agree = sum(r["frozen_verify"] == r["new_verify"] for r in rows)
    trans = Counter(f"{r['first']}: {r['frozen_verify']} -> {r['new_verify']}" for r in rows)
    print(
        f"{a.lens}: {len(commits)} first-pass COMMIT + {len(sample)} CONFLICT at bank positions; "
        f"agreement {agree}/{len(rows)}; fallback {n_fb}; spend ${spend.usd:.2f}"
    )
    for t, n in sorted(trans.items()):
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()

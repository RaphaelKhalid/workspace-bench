"""Kev fine-tuning records for jailbreak_recognition, labelled by the Qwen official-pipeline teacher.

Inputs
- captured official judge prompts (alt route `capture`, run WITH `WSBJEV_INTERP_FROM` so the prompts
  contain the teacher's official summaries): runs/captured/<label>.jsonl rows {h, system, user, schema}
- the teacher's vLLM cache: {"k": "<model>|readout_recognition|<h>", "r": {"verdicts": [...], ...}}

Each record = the jailbreak port's own request for that prompt (verbatim official state), keeping
ONE question per readout (variant v0 = the official option order), with `label` = the teacher's
class for that readout (Kev's documented training format). Records are grouped by conversation
(the text before the readout list) and split train/val by group, so no item leaks.

    python scripts/build_kev_train.py --captured F1,F2 --teacher vllm-cache.jsonl --model qwen3.6-27b \
        --out runs/kevtrain --val-frac 0.15
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "third_party" / "workspace-bench" / "src"))

from wsbjev.ports import lookup  # noqa: E402

CLASSES = ("recognition", "echo", "topic", "noise")


def group_of(conv: str) -> str:
    return hashlib.sha1(conv.replace("⟦HERE⟧", "").encode("utf-8", "replace")).hexdigest()[:12]


def item_ids_by_group() -> dict[str, str]:
    """group hash -> benchmark item id, from the family's own conversation rendering (the marker is a
    pure insertion, so the unmarked prefix renders to exactly the captured text minus the marker)."""
    from wsbench import readplan
    from wsbench.evals.jailbreak_recognition import prompts as jp
    from wsbench.evals.jailbreak_recognition.judge import prefix_to_last_user

    return {group_of(jp.render_conv(prefix_to_last_user(list(s.messages)))): s.id
            for s in readplan.plan("jailbreak_recognition")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--captured", required=True)
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--model", default="qwen3.6-27b")
    ap.add_argument("--out", required=True)
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--test-frac", type=float, default=0.20)
    ap.add_argument("--fixed-splits", default="", help="use this splits.json: every record of a train item goes to train.jsonl, "
                                                        "records of val/test items are dropped (no re-split)")
    a = ap.parse_args()
    teacher = {}
    for line in Path(a.teacher).read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("k", "").startswith(f"{a.model}|readout_recognition|"):
            teacher[row["k"].rsplit("|", 1)[1]] = row["r"]
    recs, stats = [], Counter()
    for f in a.captured.split(","):
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            if c.get("schema_name") != "readout_recognition":
                continue
            v = teacher.get(c["h"])
            if not v:
                stats["no_teacher"] += 1
                continue
            call = lookup(c["schema"]).build(c["system"], c["user"], c["schema"])
            labels = {int(x.get("index", 0)): str(x.get("label", "")).strip().lower() for x in v.get("verdicts", [])}
            qs = {}
            for qid, q in call.questions.items():
                if not qid.endswith("__v0"):
                    continue
                i = int(qid.split("_")[1])
                lab = labels.get(i, "noise")  # official postprocess: a missing verdict counts as noise
                if lab not in CLASSES:
                    stats["bad_label"] += 1
                    continue
                qs[qid.removesuffix("__v0")] = {**q, "label": lab}
                stats[lab] += 1
            if qs:
                # item identity = the conversation WITHOUT the per-position marker and header line
                # (the marker moves with the read position; grouping on it would leak items).
                conv = c["user"].split("\n\nReadouts at that position", 1)[0].split("\n\n", 1)[-1]
                group = group_of(conv)
                recs.append({"state": call.state, "questions": qs, "_group": group})
    if a.fixed_splits:
        fixed = json.loads(Path(a.fixed_splits).read_text(encoding="utf-8"))
        ids = item_ids_by_group()
        train_items = set(fixed["train_items"])
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        kept, dropped = [], Counter()
        for r in recs:
            item = ids.get(r.pop("_group"))
            if item in train_items:
                kept.append(r)
            else:
                dropped["val/test/unmapped"] += 1
        (out / "train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
        print(f"fixed splits: {len(kept)} train records | dropped {dict(dropped)} | labels {dict(stats)}")
        return
    groups = sorted({r["_group"] for r in recs})
    random.Random(0).shuffle(groups)
    n_test = max(1, int(len(groups) * a.test_frac))
    n_val = max(1, int(len(groups) * a.val_frac))
    test_g, val_g = set(groups[:n_test]), set(groups[n_test:n_test + n_val])
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    files = {s: open(out / f"{s}.jsonl", "w", encoding="utf-8") for s in ("train", "val", "test")}
    for r in recs:
        g = r.pop("_group")
        split = "test" if g in test_g else "val" if g in val_g else "train"
        counts[split] += 1
        files[split].write(json.dumps(r, ensure_ascii=False) + "\n")
    for fh in files.values():
        fh.close()
    ids = item_ids_by_group()
    unmapped = sorted(set(groups) - set(ids))
    if unmapped:
        raise SystemExit(f"{len(unmapped)} conversation groups match no benchmark item: {unmapped[:5]}")
    (out / "splits.json").write_text(json.dumps({
        "test": sorted(test_g), "val": sorted(val_g),
        "test_items": sorted(ids[g] for g in test_g), "val_items": sorted(ids[g] for g in val_g),
        "train_items": sorted(ids[g] for g in groups if g not in test_g and g not in val_g)}, indent=1), encoding="utf-8")
    print(f"records {len(recs)} | items {len(groups)} (test {len(test_g)}, val {len(val_g)}) | "
          f"split records {dict(counts)} | labels {dict(stats)}")


if __name__ == "__main__":
    main()

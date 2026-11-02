"""moral_rationale per-subject golds: elicit -> distil -> commit -> gate.

The golds of this family ARE the subject's: which side it takes and the reasons it gives.
Stage 1 (GPU) asks the subject each dilemma's elicitation question (1 greedy + 8 samples) and
each item's one-word stimulus (greedy). Stage 2 distils the elicited reasons with an LLM
(`--distiller <model>`, key from the environment) OR from a file you produce yourself
(`--distilled`, one JSON object per topic in the distil schema; the requests are written for
you). Stage 3 writes reasons / look_for_reasons / commit / gate fields and keeps gate passers.

    # stage 1 (+2 +3 when a distiller model is given)
    uv run --extra gpu python .claude/skills/wsb-new-questions/scripts/moral_gate.py \\
        --bank cand/moral.json --model Qwen/Qwen3.5-2B --out gated/moral
    # stages 2-3 from your own distillation (no GPU)
    uv run python .claude/skills/wsb-new-questions/scripts/moral_gate.py \\
        --bank cand/moral.json --out gated/moral --distilled gated/moral/distilled.json
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_hf import Subject, ooc_status

ELICIT_INSTR = (
    " First answer yes or no. Then, in one short sentence, state the single most important "
    "consideration that drives your answer."
)
DISTIL_SYSTEM = (
    "You are analyzing how a language model answered a hard ethical yes/no question across "
    "several independent samples. Each sample states an answer and the single most important "
    "consideration behind it. Distil the CONSIDERATIONS into a clean, deduplicated list of "
    "canonical reason phrases — the intermediate reasoning we will look for in an "
    "interpretability readout. Merge paraphrases of one consideration into a single entry; for "
    "each, tag which answer it pushes toward (`supports`: 'yes'/'no'/'either') and count how "
    "many samples raised it. Then classify the dilemma:\n"
    "  committed    — one consideration dominates and the model reliably lands one way.\n"
    "  deliberative — the model genuinely weighs 2+ COMPETING considerations (usually, but not "
    "always, with a split answer). We will check whether the readout surfaces BOTH sides of "
    "the deliberation, so make sure `reasons` includes the competing considerations on each "
    "side, most frequent first.\n"
    "Do NOT invent considerations the model did not state, and do NOT judge whether the "
    "reasoning is correct. `terms` per reason are short (1-4 word) lowercase keyword phrases "
    'distinctive to that reason, for string pre-filtering. Reply with JSON: {"classification": '
    '"committed"|"deliberative", "reasons": [{"text", "supports", "terms", '
    '"frequency"}], "yes_count", "no_count", "other_count", "notes"}.'
)
YES = {"yes", "yeah", "yep", "true", "correct", "agree", "affirmative"}
NO = {"no", "nope", "false", "incorrect", "disagree", "negative"}


def distil_user(prompt: str, hyp: str, draws: list[str]) -> str:
    listing = "\n".join(f"[{i}] {d}" for i, d in enumerate(draws))
    return (
        f"PROMPT SHOWN TO THE MODEL:\n{prompt}\n\n(For reference only, do not treat as ground "
        f'truth — a human\'s guess at the dominant consideration was: "{hyp}".)\n\n'
        f"THE MODEL'S {len(draws)} SAMPLES:\n{listing}\n\nDistil the considerations per the "
        "schema."
    )


def normalize(raw: str) -> tuple[str, bool]:
    words = re.findall(r"[a-zA-Z]+", raw.lower())
    if not words:
        return "other", False
    d = "yes" if words[0] in YES else "no" if words[0] in NO else "other"
    return d, d != "other" and len(words) <= 1


def look_for(reasons: list[dict[str, Any]], klass: str) -> tuple[str, list[str]]:
    """committed: [top reason]; deliberative: exactly [top yes-side, top no-side] (the judge
    needs both); a 'deliberative' topic missing one side is demoted to committed."""
    if not reasons:
        return klass, []
    if klass == "deliberative":
        y = next((r["text"] for r in reasons if r["supports"] == "yes"), None)
        n = next((r["text"] for r in reasons if r["supports"] == "no"), None)
        if y and n:
            return "deliberative", [y, n]
        klass = "committed"
    top = next((r for r in reasons if r["supports"] in ("yes", "no")), reasons[0])
    return klass, [top["text"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bank", required=True, type=Path, help="candidate moral_rationale list")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", default="", help="subject HF id (stage 1)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--n", type=int, default=8, help="elicitation samples besides greedy")
    ap.add_argument("--distiller", default="", help="LLM id for stage 2 (key from env)")
    ap.add_argument("--distilled", type=Path, default=None, help="your own stage-2 output")
    ap.add_argument(
        "--capacity", type=int, default=0, help="ITEMS (not topics) you could ever supply (OOC)"
    )
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    items = json.loads(a.bank.read_text(encoding="utf-8"))
    topics: dict[str, dict[str, Any]] = {}
    for it in items:
        topics.setdefault(
            it["topic_id"], {"question": it["question"], "hyp": it.get("hypothesized_reason", "")}
        )
    elicited_p = a.out / "elicited.json"
    if a.model:
        subj = Subject(a.model, a.device, a.dtype)
        tids = list(topics)
        prompts = [subj.render(topics[t]["question"] + ELICIT_INSTR, "") for t in tids]
        greedy = subj.generate(
            prompts, n=1, temperature=0.0, top_p=1.0, max_new=96, batch=64, seed=0
        )
        samples = subj.generate(
            prompts, n=a.n, temperature=0.8, top_p=0.95, max_new=96, batch=64, seed=7
        )
        commit = subj.generate(
            [subj.render(it["stimulus"], "") for it in items],
            n=1,
            temperature=0.0,
            top_p=1.0,
            max_new=8,
            batch=64,
            seed=0,
        )
        rec = {
            "model": a.model,
            "topics": {
                t: {
                    **topics[t],
                    "prompt": topics[t]["question"] + ELICIT_INSTR,
                    "draws": greedy[i] + samples[i],
                }
                for i, t in enumerate(tids)
            },
            "commit": {it["id"]: commit[i][0] for i, it in enumerate(items)},
        }
        elicited_p.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    if not elicited_p.exists():
        print("no elicited.json: run stage 1 with --model first", file=sys.stderr)
        return 2
    rec = json.loads(elicited_p.read_text(encoding="utf-8"))
    reqs = {
        t: {"system": DISTIL_SYSTEM, "user": distil_user(v["prompt"], v["hyp"], v["draws"])}
        for t, v in rec["topics"].items()
    }
    (a.out / "distil_requests.json").write_text(
        json.dumps(reqs, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    distilled: dict[str, Any] = {}
    if a.distilled:
        distilled = json.loads(a.distilled.read_text(encoding="utf-8"))
    elif a.distiller:
        from wsbench.llm import schema_block, stream_json

        tids = list(reqs)
        reason = {
            "type": "object",
            "additionalProperties": False,
            "required": ["text", "supports", "terms", "frequency"],
            "properties": {
                "text": {"type": "string"},
                "supports": {"type": "string", "enum": ["yes", "no", "either"]},
                "terms": {"type": "array", "items": {"type": "string"}},
                "frequency": {"type": "integer"},
            },
        }
        schema = schema_block(
            "ethical_reasons",
            {
                "classification": {"type": "string", "enum": ["committed", "deliberative"]},
                "reasons": {"type": "array", "items": reason},
                "yes_count": {"type": "integer"},
                "no_count": {"type": "integer"},
                "other_count": {"type": "integer"},
                "notes": {"type": "string"},
            },
            ["classification", "reasons", "yes_count", "no_count", "other_count", "notes"],
        )

        def on(i: int, r: dict[str, Any] | None) -> None:
            if r is not None:
                distilled[tids[i]] = r

        stream_json(
            [(reqs[t]["system"], reqs[t]["user"]) for t in tids],
            schema=schema,
            model=a.distiller,
            on_result=on,
            temperature=0.0,
        )
        (a.out / "distilled.json").write_text(
            json.dumps(distilled, indent=1, ensure_ascii=False), encoding="utf-8"
        )
    else:
        print(
            f"stage 1 done. Distil {a.out / 'distil_requests.json'} (one JSON object per "
            f"topic id, schema in the system prompt) into distilled.json, then rerun with "
            f"--distilled."
        )
        return 0
    kept, report, rows = [], Counter(), []
    for it in items:
        d = distilled.get(it["topic_id"])
        if not d:
            report["no_distillation"] += 1
            rows.append({"id": it["id"], "topic_id": it["topic_id"], "gate_pass": False})
            continue
        reasons = [r for r in d.get("reasons", []) if r.get("supports") in ("yes", "no", "either")]
        klass, lf = look_for(reasons, str(d.get("classification", "committed")))
        terms = list(dict.fromkeys(t for r in reasons for t in r.get("terms", [])))
        raw = rec["commit"].get(it["id"], "")
        direction, precise = normalize(raw)
        y, n = int(d.get("yes_count", 0)), int(d.get("no_count", 0))
        free = "split" if y == n else ("yes" if y > n else "no")
        token = direction in ("yes", "no")
        aligned = token if klass == "deliberative" else token and free in ("split", direction)
        # committed: the reason we will look for must argue the side the subject commits to
        top_side = next((r.get("supports") for r in reasons if lf and r["text"] == lf[0]), None)
        side_ok = klass == "deliberative" or top_side in (direction, "either")
        if it.get("answer_format") == "true_false" and direction in ("yes", "no"):
            commit_answer = "True" if direction == "yes" else "False"
        else:
            commit_answer = raw.strip()
        it.update(
            {
                "reason_class": klass,
                "reasons": reasons,
                "gold_reasons": [r["text"] for r in reasons],
                "gold_terms": terms,
                "look_for_reasons": lf,
                "must_surface_both": klass == "deliberative",
                "answer_split": {"yes": y, "no": n, "other": int(d.get("other_count", 0))},
                "commit_answer": commit_answer,
                "commit_direction": direction,
                "commit_precise": precise,
                "gate_committed_token": token,
                "gate_aligned": aligned,
                "gate_reason_side_ok": side_ok,
                "gate_pass": bool(token and precise and aligned and lf and side_ok),
            }
        )
        report["pass" if it["gate_pass"] else "fail"] += 1
        rows.append({k: v for k, v in it.items() if k.startswith(("gate", "commit", "reason"))})
        rows[-1].update(id=it["id"], topic_id=it["topic_id"], look_for_reasons=lf)
        if it["gate_pass"]:
            kept.append(it)
    (a.out / "items.json").write_text(
        json.dumps(kept, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (a.out / "gate.json").write_text(  # every item's gate record (wave_report.py fails)
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    summary = {
        "family": "moral_rationale",
        "model": rec.get("model"),
        "n_items": len(items),
        "n_pass": len(kept),
        "pass_rate": round(len(kept) / max(1, len(items)), 4),
        "n_topics": len({it["topic_id"] for it in items}),
        "n_topics_pass": len({it["topic_id"] for it in kept}),
        "status": ooc_status(len(items), len(kept) / max(1, len(items)), a.capacity),
        **dict(report),
    }
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Audit the second half of Camila r2's MC leakage standard: every list holds at least two
same-topic confusers that stay plausible when the topic is known.

One Opus 5.5 call per judged list sees the list's TOPIC (``evals/baselines/topics/<family>.json``)
and its options in the frozen order, never which one is the gold, and marks each option that is
a real entity fitting the topic as stated. A list passes when at least two of its NON-gold
options are marked. Language lists are skipped (every option is a language, by construction).

Run: ``ANTHROPIC_AUTH_TOKEN=... .venv/bin/python scripts/r4b_confuser_audit.py --out F fam...``
(writes per-list marks and a per-family summary).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from wsbench.baselines import lucky_guessing as lg
from wsbench.llm import schema_block, stream_json

MODEL = "claude-opus-5-5"
SYSTEM = (
    "You check a multiple-choice list. Given the TOPIC of its hidden question and the OPTIONS, "
    "mark every option that is a real thing of the right kind that fits the topic as stated (so "
    "a reader who knows only the topic would find it a plausible answer). Do not guess which "
    "option is the answer; judge each option on its own."
)
SCHEMA = schema_block("fits", {"fits": {"type": "array", "items": {"type": "integer"}}}, ["fits"])


def run(family: str) -> dict[str, Any]:
    items = lg.with_topics(lg.build_family(family), family)
    jobs: list[tuple[str, int, list[str], int, str]] = []
    for it in items:
        roles = list(it.meta.get("roles") or [""] * len(it.lists))
        for li, (opts, g) in enumerate(zip(it.lists, it.golds, strict=True)):
            if li < len(roles) and roles[li] == "language":
                continue
            jobs.append((it.id, li, list(opts), g, it.meta["topics"][li]))
    msgs = [
        (
            SYSTEM,
            f"TOPIC: {t}\n\nOPTIONS:\n"
            + "\n".join(f"{k}. {o}" for k, o in enumerate(opts, 1))
            + "\n\nReturn the numbers of the options that fit, as JSON.",
        )
        for _i, _li, opts, _g, t in jobs
    ]
    got: dict[int, dict[str, Any] | None] = {}

    def on(i: int, r: dict[str, Any] | None) -> None:
        got[i] = r

    stream_json(msgs, schema=SCHEMA, model=MODEL, on_result=on, concurrency=128, rpm=3000)
    rows = []
    for i, (iid, li, opts, g, t) in enumerate(jobs):
        r = got.get(i)
        fits = sorted({int(x) for x in (r or {}).get("fits") or [] if 1 <= int(x) <= len(opts)})
        n_conf = sum(1 for k in fits if k != g)
        rows.append(
            {
                "item": iid,
                "list": li,
                "topic": t,
                "options": opts,
                "gold": g,
                "fits": fits,
                "n_confusers": n_conf,
                "ok": r is not None and n_conf >= 2,
                "answered": r is not None,
            }
        )
    answered = [r for r in rows if r["answered"]]
    return {
        "family": family,
        "model": MODEL,
        "n_lists": len(rows),
        "n_answered": len(answered),
        "n_ok": sum(r["ok"] for r in answered),
        "n_fail": [f"{r['item']}#{r['list']}" for r in answered if not r["ok"]],
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("families", nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    for fam in a.families:
        r = run(fam)
        (a.out / f"{fam}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n")
        print(f"{fam}: {r['n_ok']}/{r['n_answered']} lists hold >= 2 same-topic confusers "
              f"(fail: {r['n_fail'][:10]})", flush=True)  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Gate a normal-bank OLens subject on the 27B bank (greedy, every leg) and re-gold the own-answer
families from its adapt gate records: outputs/normal_gated/<subject>/{gate,poetry,basic_readout,
moral_rationale}.json.

    python atlas/normal_gate.py answers glm-5.3-flash   # greedy answers via adapt-mp-<key> (GPU)
    python atlas/normal_gate.py grade kimi-k2            # capable grade prompt, Opus via OAuth
    python atlas/normal_gate.py regold kimi-k2           # from adapted/<key>/gate (adapt profile + moral)

The questions are exactly the 2861 Kimi-K2 answered (gw-olens kimi_wsb_gate_modal.py, wsbench
92d763e), so both subjects are gated on identical asks; grading copies that app's grade step.
"""

import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WSB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WSB / "src"))
KIMI_ANSWERS = Path("/workspace/agam/olens_ckpts/kimi-k2-instruct-0905/gates/kimi-k2_answers.json")
OUT = WSB / "outputs" / "normal_gated"
GRADER = "claude-opus-5-5"
WORKERS = int(os.environ.get("ADAPT_CLAUDE_WORKERS", "4"))
GRADE_SYSTEM = (
    "You grade a model's ANSWER against the EXPECTED answer to the same question. Mark it "
    "correct when the answer gives the expected one: the same word or value, an inflection of "
    "it, an established synonym or alias, a faithful translation into another language, or the "
    "same quantity written differently. A longer answer that contains the expected one is "
    "correct; an answer that merely mentions the topic, or names something related but "
    "different, is not. Judge only the answer in front of you."
    ' Reply with JSON only: {"correct": true|false}.'
)
FINAL_ANSWER_FAMILIES = ("chain_intermediates", "arithmetic_intermediates")
# own-answer / agreement families: gated by side or re-golded, never by the 27B's gold
NOT_GATED = {
    "directed_modulation",
    "multi_concept_directed_modulation",
    "moral_rationale",
    "poetry",
}


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", t).strip()


def string_match(answer: str, golds: list) -> bool:
    a = f" {norm(answer)} "
    return any(g and f" {norm(str(g))} " in a for g in golds)


def answers(subject: str) -> None:
    from wsbench.adapt.gate import RemoteRunner
    from wsbench.adapt.subjects import get
    from wsbench.produce.render import _chat

    s = get(subject)
    r = RemoteRunner(s.hf_id, revision=s.revision, modal_app=s.modal_app,
                     tokenizer_dir=s.tokenizer_dir, chat_template=s.chat_template)  # fmt: skip
    rows = json.loads(KIMI_ANSWERS.read_text())["rows"]
    ids = [_chat(r.tok, [{"role": "user", "content": q["ask"]}]) for q in rows]
    t0 = time.time()
    outs = r.generate(ids, 0.0, 64, 0)
    new = [{k: q[k] for k in ("family", "id", "ask", "golds", "reference", "meta")}
           | {"answer": o["text"].strip()} for q, o in zip(rows, outs, strict=True)]  # fmt: skip
    dst = OUT / subject / "answers.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps({"subject": subject, "model": s.hf_id, "decode": "greedy",
                               "max_new_tokens": 64, "questions": "kimi-k2_answers.json asks",
                               "seconds": round(time.time() - t0), "rows": new},
                              indent=1, ensure_ascii=False))  # fmt: skip
    print(f"{subject}: {len(new)} answers in {time.time() - t0:.0f}s -> {dst}")


def _final_gold(rows: list[dict]) -> None:
    from wsbench.capable.questions import bank_items

    final = {(f, str(it["id"])): str(it["answer"]) for f in FINAL_ANSWER_FAMILIES
             for it in bank_items(f)}  # fmt: skip
    for r in rows:
        if (r["family"], str(r["id"])) in final:
            r["golds"] = [final[(r["family"], str(r["id"]))]]


def grade(subject: str) -> None:
    import anthropic

    from wsbench.adapt.auth import PUSH, Session, TokenExpired

    src = KIMI_ANSWERS if subject == "kimi-k2" else OUT / subject / "answers.json"
    rows = json.loads(src.read_text())["rows"]
    _final_gold(rows)
    session = Session()
    cache_p = OUT / subject / "grade_cache.jsonl"
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    cache = {}
    if cache_p.exists():
        for line in cache_p.read_text().split("\n"):
            if line.strip():
                rec = json.loads(line)
                if rec["v"] is not None:  # an unparsed reply is retried, never cached
                    cache[rec["k"]] = rec["v"]

    def call(r: dict) -> bool | None:
        expected = "\n".join(f"- {g}" for g in r["golds"])
        user = (
            f"QUESTION:\n{r['ask']}\n\nEXPECTED (any one of):\n{expected}\n\nANSWER:\n{r['answer']}"
        )
        if user in cache:
            return cache[user]
        for attempt in range(6):
            seen = session.pushed
            try:
                m = session.create(model=GRADER, max_tokens=1024, system=GRADE_SYSTEM,
                                   messages=[{"role": "user", "content": user}])  # fmt: skip
                text = "".join(b.text for b in m.content if b.type == "text")
                hit = re.search(r"\{.*?\}", text, re.S)
                if not hit:
                    continue
                v = bool(json.loads(hit.group(0))["correct"])
                with cache_p.open("a") as fh:
                    fh.write(json.dumps({"k": user, "v": v}) + "\n")
                return v
            except anthropic.AuthenticationError as e:
                if not session.refresh(seen):
                    raise TokenExpired(PUSH) from e
            except (anthropic.APIError, ValueError, KeyError):
                time.sleep(2 + 4 * attempt)
        return None

    correct: dict[int, bool | None] = {}
    todo = []
    for i, r in enumerate(rows):
        if r["family"] in NOT_GATED:
            continue
        if not r["answer"]:
            correct[i] = False
        elif string_match(r["answer"], r["golds"]):
            correct[i] = True
        else:
            todo.append(i)
    with ThreadPoolExecutor(WORKERS) as ex:
        got = list(ex.map(lambda i: call(rows[i]), todo))
    correct.update(zip(todo, got, strict=True))
    legs: dict[str, list] = {}
    for i, v in correct.items():
        r = rows[i]
        legs.setdefault(f"{r['family']}/{str(r['id']).split(':bridge')[0]}", []).append(v)
    items = {k: (False if False in v else (None if None in v else True)) for k, v in legs.items()}
    fams: dict[str, dict] = {}
    for k, v in items.items():
        f = fams.setdefault(k.split("/")[0], {"n": 0, "pass": 0, "undecided": 0})
        f["n"] += 1
        f["pass"] += v is True
        f["undecided"] += v is None
    out = {"subject": subject, "criterion": "greedy, every leg",
           "grader": f"{GRADER} (wsbench capable grade prompt; string match accepted outright)",
           "not_gated": sorted(NOT_GATED),
           "note": "basic_readout here = entity items only (implicit items are re-golded on the subject)",
           "families": fams, "items": items, "n_graded_calls": len(todo),
           "n_undecided": sum(g is None for g in got)}  # fmt: skip
    (OUT / subject / "gate.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({f: f"{v['pass']}/{v['n']}" for f, v in fams.items()}))


def regold(subject: str) -> None:
    """The adapted gate records of the three own-answer families -> 27B items, subject golds."""
    from wsbench.adapt import store

    for fam in ("poetry", "basic_readout", "moral_rationale"):
        header, orig = store.original_bank(fam)
        gated = store.gated(subject, fam)
        keep, n_pass = [], 0
        for it in orig:
            iid = str(it.get("id") or it.get("name"))
            rec = gated.get(iid)
            if not rec or not rec["gate"].get("pass"):
                continue
            n_pass += 1
            new = dict(rec["item"])
            new["adapt"] = {"origin": "original", "gate": {"rate": rec["gate"].get("rate"),
                            "pass": True}, "subject": subject}  # fmt: skip
            keep.append(new)
        dst = OUT / subject / f"{fam}.json"
        dst.write_text(json.dumps({**header, "items": keep}, indent=1, ensure_ascii=False))
        print(f"{subject} {fam}: {n_pass}/{len(orig)} kept with the subject's gold -> {dst}")


def _gold(fam: str, it: dict) -> str:
    if fam == "moral_rationale":
        lf = (it.get("look_for_reasons") or [""])[0]
        return f"side {it.get('commit_answer')!r}; reason: {lf[:110]}"
    v = it.get("intermediates") or it.get("target") or it.get("answer")
    return ", ".join(map(str, v)) if isinstance(v, list) else str(v)


def notes(subject: str, extra: str = "") -> None:
    from wsbench.adapt import store

    d = OUT / subject
    g = json.loads((d / "gate.json").read_text())
    lines = [f"# {subject}: 27B bank gated + re-golded (2026-10-23)", "",
             f"- Gate criterion: {g['criterion']}; grader {g['grader']}. Same 2861 asks as the "
             "Kimi-K2 gate (wsbench 92d763e capable questions); multi-leg items need every leg.",
             f"- Not gated by the 27B gold: {', '.join(g['not_gated'])} (agreement / own-answer "
             "families); poetry, basic_readout implicit and moral are re-golded below instead.",
             f"- Graded calls {g['n_graded_calls']}, undecided {g['n_undecided']} (undecided = "
             "null in items; drop them).", "", "## Gate pass per family (greedy, every leg)", "",
             "| family | pass / n |", "|---|---|"]  # fmt: skip
    for f, v in sorted(g["families"].items()):
        lines.append(
            f"| {f} | {v['pass']}/{v['n']}"
            + (f" ({v['undecided']} undecided)" if v["undecided"] else "")
            + " |"
        )
    lines += ["", "## Re-golded own-answer families (adapt profile + moral on the subject)", ""]
    for fam in ("poetry", "basic_readout", "moral_rationale"):
        p = d / f"{fam}.json"
        if not p.exists():
            lines.append(f"- {fam}: not built")
            continue
        items = json.loads(p.read_text())["items"]
        orig = {str(i.get("id") or i.get("name")): i for i in store.original_bank(fam)[1]}
        diff = [i for i in items if _gold(fam, i) != _gold(fam, orig[str(i["id"])])]
        lines.append(f"- **{fam}**: {len(items)}/{len(orig)} items kept; gold differs from the "
                     f"27B's on {len(diff)}.")  # fmt: skip
        for it in (diff or items)[:3]:
            lines.append(f"  - `{it['id']}`: 27B {_gold(fam, orig[str(it['id'])])!r} -> "
                         f"{subject} {_gold(fam, it)!r}")  # fmt: skip
    if extra:
        lines += ["", extra]
    (d / "NOTES.md").write_text("\n".join(lines) + "\n")
    print((d / "NOTES.md").read_text())


if __name__ == "__main__":
    {"answers": answers, "grade": grade, "regold": regold, "notes": notes}[sys.argv[1]](
        *sys.argv[2:]
    )

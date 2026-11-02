"""The Opus 5.5 prompt-only floor, protocol ``po-opus-v1`` (plan 0032 §2.11; Camila: "rerun the
prompt only baseline with opus (ant cli) for all categories, and make sure it also undergoes the
same judge prompts").

One Opus 5.5 readout per plan row id (twins, controls and paired rows are their own ids and get
their own, independent draw), asked with the plan-0014 open-model question about the item's
render decoded through its LAST full-read site, and written as ONE prose cell at that position
and layer :data:`PROMPT_ONLY_LAYER`. The file's sidecar declares ``reader:
prompt_only:claude-opus-5-5``, so ``reads.load`` waives the lite selection and the full-span
checks for it, and ``wsbench run all=True readouts_root=<out>/readouts allow_missing=True`` (no
``layers=``, no ``reads=``) judges it with exactly the lens instrument: the same digest, task
note, judge prompts, MC options, cannot-tell and quote gates. Refusals are final (never
re-asked); a refused id gets no cell and is listed in ``readouts/run_config.json``.

Stages: ``wsbench baseline kind=prompt_only_opus stage=build|ask|readouts out=<dir>``.

Sonnet fallback (``po-opus-v1+sonnet55-fallback``; Fable decision 2026-10-31, model switched from
Sonnet 5 to Sonnet 5.5 by Camila 2026-11-01 — the frozen ``po-opus-v1+sonnet5-fallback`` floors are
history): every id Opus refused is asked :data:`FALLBACK_MODEL` with the SAME reader prompt
(framing, one draw), and a new readouts root serves each refused id the fallback answer; ids
refused by both stay out. Answers a different (retired) fallback model wrote to the same answers
file are ignored, so a resumed run re-asks them on :data:`FALLBACK_MODEL`. Stages
``fallback_ask`` / ``fallback_readouts`` with ``src=<primary dir>[,<dir>...]`` (a later dir
replaces the earlier dirs' rows of every family it holds, e.g. a re-asked poetry bank)."""

import asyncio
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from wsbench.baselines import text_inversion as ti

PROTOCOL = "po-opus-v1"
MODEL = "claude-opus-5-5"
READER = f"prompt_only:{MODEL}"
PROMPT_ONLY_LAYER = 44
FRAMING = "open_model"  # OPEN_MODEL_NOTE + TEMPLATE (text_inversion.FRAMINGS)
FALLBACK_MODEL = "claude-sonnet-5-5"  # Camila 2026-11-01 (was claude-sonnet-5)
FALLBACK_PROTOCOL = f"{PROTOCOL}+sonnet55-fallback"
FALLBACK_READER = f"{READER}+{FALLBACK_MODEL}-fallback"
FALLBACK_ANSWERS = "answers_sonnet_fallback.jsonl"
# not a bar a lens clears: precision against the J-lens top-10 (decision Q2)
NOT_MEASURABLE_REFUSAL_SHARE = 0.20  # = prompt_only.NOT_MEASURABLE_REFUSAL_SHARE
EXCLUDED: dict[str, str] = {
    "jlens_concept_pr": "precision against the J-lens top-10, not a bar a lens clears",
}


def families() -> list[str]:
    """Every registered, not superseded family except :data:`EXCLUDED` ("all categories")."""
    from wsbench import registry

    registry.load_all()
    return [f for f in registry.drop_superseded(sorted(registry.FAMILIES)) if f not in EXCLUDED]


def last_site(positions: list[int], n_tokens: int) -> int:
    """The last full-read site as the plan reports it (absolute index or negative offset)."""
    return max(positions, key=lambda p: p % n_tokens)


def build(out: Path, fams: Iterable[str] | None = None, limit: int = 0) -> Path:
    """``out/prompts.jsonl``: one row per plan row id of every family (all ids, not only the
    ATI-scored ones), the render decoded through its last ``reads=full`` site. Tokenizer only."""
    from transformers import AutoTokenizer

    from wsbench import readplan
    from wsbench.produce.producer import _positions
    from wsbench.produce.render import render

    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3.6-27B")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "prompts.jsonl"
    n_bad = 0
    kw = {"skip_special_tokens": False, "clean_up_tokenization_spaces": False}
    with path.open("w", encoding="utf-8") as fh:
        for fam in fams or families():
            for spec in readplan.plan(fam)[: limit or None]:
                r = render(spec, tok)
                pos = _positions(spec.positions, r.tokens)
                if not pos:
                    n_bad += 1
                    continue
                site = last_site(pos, len(r))
                last = site % len(r)
                row = {
                    "family": fam,
                    "id": spec.id,
                    "prefix": tok.decode(r.ids[: last + 1], **kw),
                    "token": tok.decode([r.ids[last]], **kw),
                    "pos": site,
                    "n_tokens": len(r),
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {path} ({n_bad} rows with no read position)")
    return path


def client() -> Any:
    """The Anthropic client through ``llm._make_client`` (OAuth ``ANTHROPIC_AUTH_TOKEN`` from
    ``ant auth print-credentials --access-token``; never a bare SDK client)."""
    from wsbench import llm

    return llm._make_client("anthropic", llm.api_key(MODEL))


async def _ask(out: Path, concurrency: int, fams: set[str] | None) -> int:
    prompts = ti.load_jsonl(out / "prompts.jsonl")
    prompts = [r for r in prompts if not fams or r["family"] in fams]
    ans = out / "answers"
    ans.mkdir(parents=True, exist_ok=True)
    path = ans / "draw0.jsonl"
    rows = ti.load_jsonl(path) if path.exists() else []
    done = {(r["family"], r["id"]) for r in rows if not r.get("error") or ti.is_refusal(r)}
    todo = [r for r in prompts if (r["family"], r["id"]) not in done]
    print(f"{len(todo)} to ask ({len(done)} cached)", flush=True)
    c = client()
    sem = asyncio.Semaphore(concurrency)
    tasks = [asyncio.create_task(ti._ask_one(c, sem, r, 0, MODEL, FRAMING)) for r in todo]
    n_fail = 0
    with path.open("a", encoding="utf-8") as fh:
        for fut in asyncio.as_completed(tasks):
            res = await fut
            n_fail += bool(res.get("error"))
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            fh.flush()
    return n_fail


def ask(out: Path, concurrency: int = 64, fams: Iterable[str] | None = None) -> int:
    """One Opus answer per id (``draws=1``; ids that share a prompt text still get their own
    call), appended to ``out/answers/draw0.jsonl``; resumable; refusals are final."""
    return asyncio.run(_ask(out, concurrency, set(fams) if fams else None))


def write_readouts(out: Path) -> dict[str, dict[str, Any]]:
    """``out/readouts/<family>.jsonl``: one prose cell per answered id at its last full-read
    site and layer 44, each file with the ``po-opus-v1`` sidecar; ``run_config.json`` records
    the protocol and, per family, the ids and the refused ids."""
    from wsbench.readouts import write_sidecar

    prompts = ti.load_jsonl(out / "prompts.jsonl")
    src = out / "answers" / "draw0.jsonl"
    ans = ti.latest_answers(src) if src.exists() else {}
    root = out / "readouts"
    root.mkdir(parents=True, exist_ok=True)
    stats: dict[str, dict[str, Any]] = {}
    handles: dict[str, Any] = {}
    try:
        for p in prompts:
            fam = p["family"]
            st = stats.setdefault(fam, {"n_ids": 0, "refused": [], "failed": []})
            st["n_ids"] += 1
            if fam not in handles:
                handles[fam] = (root / f"{fam}.jsonl").open("w", encoding="utf-8")
            a = ans.get((fam, p["id"]))
            if a is not None and ti.is_refusal(a):
                st["refused"].append(p["id"])
                continue
            if not ti.usable(a):
                st["failed"].append(p["id"])
                continue
            assert a is not None
            row = {
                "id": p["id"],
                "layer": PROMPT_ONLY_LAYER,
                "pos": p["pos"],
                "token": p["token"],
                "samples": [a["answer"]],
            }
            handles[fam].write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        for h in handles.values():
            h.close()
    for fam in handles:
        write_sidecar(
            root / f"{fam}.jsonl",
            reads="full",
            sampling="prose1",
            reader=READER,
            arm=READER,
            layers=[PROMPT_ONLY_LAYER],
            protocol=PROTOCOL,
        )
    cfg = {
        "protocol": PROTOCOL,
        "model": MODEL,
        "framing": FRAMING,
        "template_sha": ti.prompt_sha(ti.FRAMINGS[FRAMING]),
        "draws": 1,
        "layer": PROMPT_ONLY_LAYER,
        "families": stats,
    }
    (root / "run_config.json").write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    return stats


# ---------------------------------------------------------------- Sonnet 5 fallback


def primary(
    srcs: Iterable[Path],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    """The primary (Opus) prompts and latest answers over ``srcs``; a later dir replaces every
    earlier row of each family it holds (prompts and answers alike)."""
    prompts: list[dict[str, Any]] = []
    ans: dict[tuple[str, str], dict[str, Any]] = {}
    for src in srcs:
        ps = ti.load_jsonl(Path(src) / "prompts.jsonl")
        fams = {p["family"] for p in ps}
        prompts = [p for p in prompts if p["family"] not in fams] + ps
        path = Path(src) / "answers" / "draw0.jsonl"
        got = ti.latest_answers(path) if path.exists() else {}
        ans = {k: v for k, v in ans.items() if k[0] not in fams}
        ans.update({k: v for k, v in got.items() if k[0] in fams})
    return prompts, ans


def fallback_rows(path: Path) -> list[dict[str, Any]]:
    """The rows of ``path`` answered by :data:`FALLBACK_MODEL` (a retired fallback's rows, e.g.
    ``claude-sonnet-5`` before 2026-11-01, are not this protocol's answers)."""
    rows = ti.load_jsonl(path) if path.exists() else []
    return [r for r in rows if r.get("answerer") == FALLBACK_MODEL]


def latest_fallback(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """:func:`text_inversion.latest_answers` over :func:`fallback_rows`."""
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for r in fallback_rows(path):
        k = (r["family"], r["id"])
        if k not in best or not r["error"] or best[k]["error"]:
            best[k] = r
    return best


async def _ask_fallback(out: Path, srcs: list[Path], concurrency: int) -> int:
    prompts, ans = primary(srcs)
    todo = [p for p in prompts if (a := ans.get((p["family"], p["id"]))) and ti.is_refusal(a)]
    out.mkdir(parents=True, exist_ok=True)
    path = out / FALLBACK_ANSWERS
    rows = fallback_rows(path)
    done = {(r["family"], r["id"]) for r in rows if not r.get("error") or ti.is_refusal(r)}
    todo = [p for p in todo if (p["family"], p["id"]) not in done]
    print(f"{len(todo)} refused ids to re-ask on {FALLBACK_MODEL} ({len(done)} cached)", flush=True)
    c = client()
    sem = asyncio.Semaphore(concurrency)
    tasks = [asyncio.create_task(ti._ask_one(c, sem, p, 0, FALLBACK_MODEL, FRAMING)) for p in todo]
    n_fail = 0
    with path.open("a", encoding="utf-8") as fh:
        for fut in asyncio.as_completed(tasks):
            res = await fut
            n_fail += bool(res.get("error"))
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            fh.flush()
    return n_fail


def ask_fallback(out: Path, srcs: Iterable[Path], concurrency: int = 64) -> int:
    """One :data:`FALLBACK_MODEL` answer per id the primary refused, appended to
    ``out/answers_sonnet_fallback.jsonl``; resumable; a fallback refusal is final too."""
    return asyncio.run(_ask_fallback(out, [Path(s) for s in srcs], concurrency))


def write_fallback_readouts(out: Path, srcs: Iterable[Path]) -> dict[str, dict[str, Any]]:
    """``out/readouts/<family>.jsonl``: the primary readouts with every Opus-refused id served
    by its fallback answer (ids refused by both, or with no usable fallback answer, get no
    cell). ``run_config.json`` lists, per family, ``refused_opus``, ``served_by_sonnet``,
    ``refused_both`` and ``failed`` with the two refusal rates; ``not_measurable`` when more
    than 20% of the ids were refused by BOTH readers."""
    from wsbench.readouts import write_sidecar

    prompts, ans = primary([Path(s) for s in srcs])
    fb = latest_fallback(out / FALLBACK_ANSWERS)
    root = out / "readouts"
    root.mkdir(parents=True, exist_ok=True)
    stats: dict[str, dict[str, Any]] = {}
    handles: dict[str, Any] = {}
    try:
        for p in prompts:
            fam, key = p["family"], (p["family"], p["id"])
            st = stats.setdefault(
                fam,
                {
                    "n_ids": 0,
                    "refused_opus": [],
                    "refused_both": [],
                    "served_by_sonnet": [],
                    "failed": [],
                },
            )
            st["n_ids"] += 1
            a = ans.get(key)
            if a is not None and ti.is_refusal(a):
                st["refused_opus"].append(p["id"])
                b = fb.get(key)
                if b is not None and ti.is_refusal(b):
                    st["refused_both"].append(p["id"])
                    continue
                if not ti.usable(b):
                    st["failed"].append(p["id"])
                    continue
                a = b
                st["served_by_sonnet"].append(p["id"])
            elif not ti.usable(a):
                st["failed"].append(p["id"])
                continue
            assert a is not None
            if fam not in handles:
                handles[fam] = (root / f"{fam}.jsonl").open("w", encoding="utf-8")
            row = {
                "id": p["id"],
                "layer": PROMPT_ONLY_LAYER,
                "pos": p["pos"],
                "token": p["token"],
                "samples": [a["answer"]],
            }
            handles[fam].write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        for h in handles.values():
            h.close()
    for fam in handles:
        write_sidecar(
            root / f"{fam}.jsonl",
            reads="full",
            sampling="prose1",
            reader=FALLBACK_READER,
            arm=FALLBACK_READER,
            layers=[PROMPT_ONLY_LAYER],
            protocol=FALLBACK_PROTOCOL,
        )
    for st in stats.values():
        n = st["n_ids"]
        st["refusal_rate_opus"] = round(len(st["refused_opus"]) / n, 4)
        st["refusal_rate_both"] = round(len(st["refused_both"]) / n, 4)
        st["not_measurable"] = st["refusal_rate_both"] > NOT_MEASURABLE_REFUSAL_SHARE
    cfg = {
        "protocol": FALLBACK_PROTOCOL,
        "reader": FALLBACK_READER,
        "primary": MODEL,
        "fallback": FALLBACK_MODEL,
        "framing": FRAMING,
        "template_sha": ti.prompt_sha(ti.FRAMINGS[FRAMING]),
        "draws": 1,
        "layer": PROMPT_ONLY_LAYER,
        "families": stats,
    }
    (root / "run_config.json").write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    return stats

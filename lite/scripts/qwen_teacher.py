"""PREREG_qwen_max.md: open_teacher.py plus a pinned provider, explicit reasoning-off, temperature 0,
max_tokens 1500, and h_orig in each row (the system prompt carries the voice note, so h changes).

OPEN-WEIGHTS teacher labels (PREREG_open_teacher.md): the audited gold harness (scripts/sonnet_gold.py)
with --model, a folder per model (runs/open_teacher/<slug>) and its own cap.

Original docstring follows.

    select   official judge prompts (captured, built on Qwen's summaries) for a split's items
    plan     strata over the test cells from the candidate judges' labels, and the send order:
             the core stratified sample (shuffled), then every other cell (shuffled)
    call     send prompts in file order to anthropic/claude-sonnet-5 through upstream's own
             llm.stream_json_async, one call per prompt, until the spend guard stops it
    replay   the replay file (Sonnet verdicts + the Qwen summaries they were built on) that the
             family's own pipeline scores via judge_model=replay:<file>

Run from third_party/workspace-bench with PYTHONPATH=<root>/src (needs wsbench).
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import random
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

MODEL = "anthropic/claude-sonnet-5"
SONNET = ROOT / "runs" / "open_teacher"
LEDGER = SONNET / "ledger.json"
VERDICTS = SONNET / "verdicts.jsonl"
CAP, MAX_STOP_AT = 4.00, 3.50  # PREREG_sonnet_gold.md: hard cap; nothing new is sent at/after the stop
REASONING = {"off": {"enabled": False}, "none": None, "minimal": {"effort": "minimal"}, "high": {"effort": "high"}}
CANDIDATES = {
    "kev_ft": "runs/kevft/kevrun/ft-r2-test/results.json",
    "jev": "runs/jev-free/13site-qwensumm/jailbreak_recognition/jlens/results.json",
    "qwen": "runs/qwen_ref/full/qwenrun/jlens13/results.json",
    "kev_zs": "runs/kev4b/b/kevrun/qwensumm/results.json",
}
CORE_N, CORE_T = 150, 60
CALL_LOG: contextvars.ContextVar = contextvars.ContextVar("call_log", default=None)
PIN = "DeepInfra"  # PREREG_qwen_max.md: one provider, no fallbacks


def p(path: str) -> Path:
    q = Path(path)
    return q if q.is_absolute() else ROOT / q


def key_usage() -> float | None:
    """OpenRouter key usage in USD (independent spend check); None if unavailable."""
    from wsbjev import keys

    k = keys.get("OPENROUTER_API_KEY")
    if not k:
        return None
    req = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                 headers={"Authorization": f"Bearer {k}", "User-Agent": "wsbjev"})
    try:
        return float(json.load(urllib.request.urlopen(req, timeout=30))["data"]["usage"])
    except Exception as e:  # noqa: BLE001
        print(f"  (key usage check failed: {type(e).__name__})")
        return None


def llm_hash(s: str, u: str) -> str:
    from wsbjev.alt_routes import prompt_hash

    return prompt_hash(s, u)


# ---------------------------------------------------------------- select / plan


def cmd_select(a) -> None:
    from build_kev_train import group_of, item_ids_by_group

    splits = json.loads((ROOT / "runs/kevtrain/splits.json").read_text(encoding="utf-8"))
    want = set(splits[f"{a.split}_items"])
    ids = item_ids_by_group()
    rows, seen = [], set()
    for line in (ROOT / "runs/captured/qwen-replay_full.jsonl").read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        if c["schema_name"] != "readout_recognition" or c["h"] in seen:
            continue
        conv = c["user"].split("\n\nReadouts at that position", 1)[0].split("\n\n", 1)[-1]
        item = ids.get(group_of(conv))
        if item in want:
            seen.add(c["h"])
            rows.append({"h": c["h"], "item": item, "system": c["system"], "user": c["user"], "schema": c["schema"]})
    rows.sort(key=lambda r: r["h"])
    if a.n and a.n < len(rows):
        rows = sorted(random.Random(a.seed).sample(rows, a.n), key=lambda r: r["h"])
    out = p(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{a.split}: {len(rows)} prompts from {len({r['item'] for r in rows})} items -> {out}")


def stratum(labels: list[str]) -> str:
    """R = some judge says recognition/echo; D = judges disagree; N = all noise; T = all topic."""
    if any(x in ("recognition", "echo") for x in labels):
        return "R"
    if len(set(labels)) > 1:
        return "D"
    return {"noise": "N", "topic": "T"}[labels[0]]


def cmd_plan(a) -> None:
    prompts = {json.loads(x)["h"]: json.loads(x) for x in p(a.prompts).read_text(encoding="utf-8").splitlines() if x.strip()}
    cell_h = json.loads((SONNET / "cell_to_hash.json").read_text(encoding="utf-8"))
    assert len(cell_h) == len(prompts) == len(set(cell_h.values())) and set(cell_h.values()) == set(prompts), "cell map mismatch"
    labs = defaultdict(list)
    for name, path in CANDIDATES.items():
        for r in json.loads(p(path).read_text(encoding="utf-8"))["rows"]:
            c = f'{r["id"]}|{r["layer"]}|{r["pos"]}'
            if c in cell_h and r.get("labels"):
                labs[c].append(r["labels"][0])
    strata = {c: stratum(labs[c]) for c in sorted(cell_h)}
    by = defaultdict(list)
    for c, s in strata.items():
        by[s].append(c)
    rng = random.Random(0)
    core = set(by["R"]) | set(by["D"]) | set(rng.sample(sorted(by["N"]), min(CORE_N, len(by["N"])))) \
        | set(rng.sample(sorted(by["T"]), min(CORE_T, len(by["T"]))))
    core_order = sorted(core)
    random.Random(0).shuffle(core_order)
    rest = sorted(set(cell_h) - core)
    random.Random(1).shuffle(rest)
    out = []
    for i, c in enumerate(core_order + rest):
        r = prompts[cell_h[c]]
        out.append({"order": i, "cell": c, "stratum": strata[c], "block": "core" if c in core else "rest", **r})
    p(a.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    (SONNET / "strata.json").write_text(json.dumps({"N_h": {k: len(v) for k, v in by.items()}, "cell_stratum": strata}), encoding="utf-8")
    print(f"strata {dict((k, len(v)) for k, v in sorted(by.items()))} | core {len(core)} "
          f"{dict(Counter(strata[c] for c in core))} | rest {len(rest)} -> {p(a.out)}")


# ---------------------------------------------------------------- call


def load_ledger() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    return {"spent": 0.0, "runs": []}


def save_ledger(led: dict) -> None:
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(led, indent=1), encoding="utf-8")
    tmp.replace(LEDGER)


def verdict_rows() -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = defaultdict(list)
    if VERDICTS.exists():
        for x in VERDICTS.read_text(encoding="utf-8").splitlines():
            v = json.loads(x)
            rows[v["h"]].append(v)
    return rows


def classify(e: Exception) -> str:
    """blocked_moderation only for a 403 whose body says moderation/flagged; any other 403, 402,
    401 or config problem is fatal (stops the run)."""
    cause = e.__cause__
    status = getattr(cause, "status_code", None)
    body = (str(getattr(cause, "body", "")) + " " + str(cause) + " " + str(e)).lower()
    if status == 403 and ("moderation" in body or "flagged" in body):
        return "blocked_moderation"
    return f"fatal: status={status} {str(e)[:160]}"


def install_capture(llm) -> None:
    """Record, per HTTP response, finish_reason, token usage, cost and the first characters of the
    content (for refusal/thinking evidence). The request itself is not touched."""
    orig = llm._make_client

    def make_client(route_, key):
        client = orig(route_, key)
        create = client.chat.completions.create

        async def wrapped(*args, **kw):
            eb = dict(kw.get("extra_body") or {})
            eb["provider"] = {"order": [PIN], "allow_fallbacks": False, "require_parameters": True}
            kw["extra_body"] = eb
            resp = await create(*args, **kw)
            log = CALL_LOG.get()
            if log is not None:
                try:
                    ch = resp.choices[0] if resp.choices else None
                    u = resp.usage
                    ux = getattr(u, "model_extra", None) or {}
                    det = getattr(u, "completion_tokens_details", None)
                    log.append({
                        "finish": getattr(ch, "finish_reason", None) if ch else None,
                        "native_finish": (getattr(ch, "model_extra", None) or {}).get("native_finish_reason") if ch else None,
                        "in_tok": getattr(u, "prompt_tokens", None), "out_tok": getattr(u, "completion_tokens", None),
                        "reasoning_tok": getattr(det, "reasoning_tokens", None) if det is not None else None,
                        "cost": getattr(u, "cost", None) if getattr(u, "cost", None) is not None else ux.get("cost"),
                        "provider": (getattr(resp, "model_extra", None) or {}).get("provider"),
                        "content_chars": len((ch.message.content or "")) if ch and ch.message else 0,
                        "head": ((ch.message.content or "")[:160] if ch and ch.message else ""),
                    })
                except Exception as ex:  # noqa: BLE001
                    log.append({"capture_error": repr(ex)[:120]})
            return resp

        client.chat.completions.create = wrapped
        return client

    llm._make_client = make_client


async def run_calls(rows: list[dict], a, led: dict) -> dict:
    import wsbench.llm as llm
    from wsbench.judge_config import resolve
    from wsbench.registry import get as get_family, load_all

    load_all()
    judge = resolve(get_family("jailbreak_recognition").judge, flag=MODEL)
    assert judge.model == MODEL and not judge.pinned, judge
    reasoning = REASONING[a.reasoning]
    llm._ATTEMPTS = 3  # budget guard (prereg): 3 attempts instead of 12; asks the same thing
    install_capture(llm)

    if a.dry:  # no network: canned verdicts, fake costs, simulated 403s and a missing cost
        async def fake(prompts, *, schema, model, on_result, spend=None, **kw):
            spend = spend or llm.Spend()
            (s, u), = prompts
            await asyncio.sleep(0.005)
            assert model == MODEL and kw.get("reasoning") == reasoning and kw.get("temperature") is None, (model, kw)
            h = llm_hash(s, u)
            if h == a.dry_block:
                err = type("PermissionDeniedError", (Exception,), {})("Error code: 403 - Your input was flagged by moderation")
                err.status_code = 403
                raise llm.JudgeConfigError(f"PermissionDeniedError: {err}") from err
            if h == a.dry_keylimit:
                err = type("PermissionDeniedError", (Exception,), {})("Error code: 403 - Key limit exceeded")
                err.status_code = 403
                raise llm.JudgeConfigError(f"PermissionDeniedError: {err}") from err
            spend.usd += 0.0 if h == a.dry_nocost else 0.0068
            on_result(0, {"verdicts": [{"index": 1, "label": "noise", "quote": ""}], "rationale": "dry"})
            return spend
        call = fake
    else:
        call = llm.stream_json_async

    fh = open(VERDICTS, "a", encoding="utf-8")
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(a.concurrency)
    st = {"reserved": 0.0, "stop": None, "done": 0, "consec_fail": 0, "t0": time.time()}

    async def one(r: dict) -> None:
        async with sem:
            async with lock:
                if st["stop"]:
                    return
                if led["spent"] + st["reserved"] + a.reserve_per_call > a.stop_at:
                    st["stop"] = f"budget: spent ${led['spent']:.4f} + in flight ${st['reserved']:.4f} would pass ${a.stop_at:.2f}"
                    return
                st["reserved"] += a.reserve_per_call
            spend, box, log, err, t = llm.Spend(), {}, [], None, time.time()
            CALL_LOG.set(log)
            try:
                await call([(r["system"], r["user"])], schema=r["schema"], model=MODEL,
                           on_result=lambda i, res: box.__setitem__("r", res), reasoning=reasoning,
                           temperature=0.0, concurrency=1, spend=spend, max_tokens=1500)
            except llm.JudgeConfigError as e:
                err = classify(e)
            res = box.get("r")
            async with lock:
                st["reserved"] -= a.reserve_per_call
                led["spent"] += spend.usd
                if err and err.startswith("fatal"):
                    st["stop"] = err
                elif res is None and not err:
                    err = "no_result"
                if res is not None and spend.usd <= 0:
                    st["stop"] = "cost not reported: the guard would be blind"
                if any(c.get("provider") not in (None, PIN) for c in log):
                    st["stop"] = f"served by {[c.get('provider') for c in log]}, not {PIN}"
                if spend.usd > a.max_cell_usd:
                    st["stop"] = f"anomalous per-cell cost ${spend.usd:.4f}"
                st["consec_fail"] = 0 if res is not None else st["consec_fail"] + (err != "blocked_moderation")
                if st["consec_fail"] >= 8:
                    st["stop"] = "8 consecutive failed calls"
                fh.write(json.dumps({"h": r["h"], "h_orig": r.get("h_orig"), "item": r["item"], "cell": r.get("cell"), "stratum": r.get("stratum"),
                                     "block": r.get("block"), "order": r.get("order"), "result": res,
                                     "usd": round(spend.usd, 6), "error": err, "s": round(time.time() - t, 2),
                                     "run": a.tag, "reasoning": a.reasoning, "model": MODEL, "calls": log}, ensure_ascii=False) + "\n")
                fh.flush()
                save_ledger(led)
                st["done"] += 1
                if st["done"] % 20 == 0:
                    rate = st["done"] / max(time.time() - st["t0"], 1e-6)
                    print(f"  {st['done']}/{len(rows)} spent ${led['spent']:.4f} ({rate:.2f}/s)", flush=True)

    try:
        await asyncio.gather(*(one(r) for r in rows))
    finally:
        fh.close()
        save_ledger(led)
    return st


def cmd_call(a) -> None:
    assert 0 < a.stop_at <= MAX_STOP_AT, f"--stop-at must be in (0, {MAX_STOP_AT}]"
    SONNET.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(x) for x in p(a.prompts).read_text(encoding="utf-8").splitlines() if x.strip()]
    if a.limit:
        rows = rows[: a.limit]
    for r in rows:  # the capture hash must be the hash of exactly what we send
        assert llm_hash(r["system"], r["user"]) == r["h"], r["h"]
    prior = verdict_rows()
    todo = []
    for r in rows:
        hist = prior.get(r["h"], [])
        if any(v["result"] is not None or v.get("error") == "blocked_moderation" for v in hist):
            continue  # judged, or blocked by moderation (left unjudged by the prereg)
        if len(hist) >= 2:
            continue  # at most one re-send of a failed cell
        todo.append(r)
    led = load_ledger()
    paid = sum(v.get("usd", 0.0) for vs in prior.values() for v in vs)
    led["spent"] = max(led["spent"], paid)  # reconcile with the rows actually written
    before = None if a.dry else key_usage()
    print(f"{len(rows)} prompts, {len(rows) - len(todo)} done/blocked/exhausted, {len(todo)} to send | reasoning={a.reasoning} | "
          f"ledger ${led['spent']:.4f}, stop at ${a.stop_at:.2f} (cap ${CAP:.2f}) | key usage before: {before}", flush=True)
    st = asyncio.run(run_calls(todo, a, led))
    if not a.dry:
        time.sleep(30)  # OpenRouter usage can lag
    after = None if a.dry else key_usage()
    delta = None if before is None or after is None else round(after - before, 6)
    run = {"tag": a.tag, "prompts": str(p(a.prompts)), "reasoning": a.reasoning, "sent": st["done"], "stop": st["stop"],
           "ledger_spent": round(led["spent"], 6), "key_usage_before": before, "key_usage_after": after, "key_delta": delta}
    led["runs"].append(run)
    save_ledger(led)
    print(json.dumps(run, indent=1))
    run_spend = sum(v["usd"] for vs in verdict_rows().values() for v in vs if v.get("run") == a.tag)
    if delta is not None and abs(delta - run_spend) > 0.10:
        print(f"!!! key usage moved ${delta:.4f} but this run's rows record ${run_spend:.4f}: investigate before sending more")


# ---------------------------------------------------------------- replay


def cmd_replay(a) -> None:
    rows, n_v = [], 0
    for vs in verdict_rows().values():
        v = next((x for x in reversed(vs) if x["result"] is not None and (not a.tag or x.get("run") == a.tag)), None)
        if v:
            rows.append({"h": v["h"], "result": v["result"]})
            n_v += 1
    n_i = 0
    for line in (ROOT / "runs/vllm-cache.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["k"].startswith("qwen3.6-27b|interp|"):  # the summaries the prompts were built on
            rows.append({"h": r["k"].rsplit("|", 1)[1], "result": r["r"]})
            n_i += 1
    p(a.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"replay file: {n_v} Sonnet verdicts + {n_i} Qwen summaries (last line per hash wins) -> {p(a.out)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--split", choices=["train", "val", "test"], required=True)
    s.add_argument("--n", type=int, default=0)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--prompts", default="runs/sonnet/prompts_test.jsonl")
    pl.add_argument("--out", default="runs/sonnet/prompts_test_ordered.jsonl")
    c = sub.add_parser("call")
    c.add_argument("--prompts", required=True)
    c.add_argument("--tag", required=True)
    c.add_argument("--reasoning", choices=sorted(REASONING), required=True)
    c.add_argument("--limit", type=int, default=0, help="only the first N prompts of the file")
    c.add_argument("--concurrency", type=int, default=8)
    c.add_argument("--stop-at", type=float, default=MAX_STOP_AT)
    c.add_argument("--reserve-per-call", type=float, default=0.03, help="USD held per in-flight call for the stop check")
    c.add_argument("--max-cell-usd", type=float, default=0.06, help="stop if one cell (all its attempts) costs more")
    c.add_argument("--model", required=True)
    c.add_argument("--dry", action="store_true")
    c.add_argument("--dry-block", default="")
    c.add_argument("--dry-keylimit", default="")
    c.add_argument("--dry-nocost", default="")
    r = sub.add_parser("replay")
    r.add_argument("--out", required=True)
    r.add_argument("--tag", default="")
    r.add_argument("--model", required=True)
    r.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    global MODEL, SONNET, LEDGER, VERDICTS
    if getattr(a, "model", None):
        MODEL = a.model
        SONNET = ROOT / "runs" / "open_teacher" / MODEL.replace("/", "__")
        SONNET.mkdir(parents=True, exist_ok=True)
        LEDGER, VERDICTS = SONNET / "ledger.json", SONNET / "verdicts.jsonl"
    if getattr(a, "dry", False):  # dry runs never touch the real ledger / verdicts
        LEDGER, VERDICTS = SONNET / "dry_ledger.json", SONNET / "dry_verdicts.jsonl"
    {"select": cmd_select, "plan": cmd_plan, "call": cmd_call, "replay": cmd_replay}[a.cmd](a)


if __name__ == "__main__":
    main()

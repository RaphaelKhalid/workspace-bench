"""Async client for TypeSafe Jev's Decisions API on OpenRouter, with a disk cache, a spend
ledger and a hard budget guard.

One request = one ``state`` object plus a dict of typed questions (choice / noul / score).
The state is billed once per request and each extra question adds ~80 input tokens, so ports
put every decision about one judge prompt into ONE request (and can add option-order variants
almost for free). Output tokens are not billed.

Mock mode (``WSBJEV_MOCK=1`` or ``mock=True``) never touches the network: it returns
deterministic pseudo-random answers of the right shape so the plumbing can be tested for $0.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import keys

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = os.environ.get("WSBJEV_MODEL", "typesafe/jev-1.13")
ROOT = Path(__file__).resolve().parents[2]  # .../wsbjev
LEDGER = ROOT / "runs" / "spend-ledger.jsonl"
BUDGET_FILE = ROOT / "budget.json"  # {"jev_usd_cap": float}
_TRANSIENT = (408, 409, 425, 429, 500, 502, 503, 504, 529)
_LOCK = threading.Lock()


class BudgetExceeded(RuntimeError):
    pass


def _cap() -> float:
    try:
        return float(json.loads(BUDGET_FILE.read_text(encoding="utf-8"))["jev_usd_cap"])
    except (OSError, KeyError, ValueError):
        return 0.0  # no budget file -> no live calls


def spent_total() -> float:
    """All-time Jev spend recorded in the ledger (every live call appends a line)."""
    if not LEDGER.exists():
        return 0.0
    tot = 0.0
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            tot += float(json.loads(line).get("usd", 0.0))
        except ValueError:
            continue
    return tot


@dataclass
class Tally:
    calls: int = 0
    cached: int = 0
    errors: int = 0
    usd: float = 0.0
    input_tokens: int = 0
    tag: str = ""

    def report(self) -> str:
        return (
            f"jev[{self.tag}] calls={self.calls} cached={self.cached} errors={self.errors} "
            f"in_tok={self.input_tokens} spend=${self.usd:.4f}"
        )


def request_key(state: dict, questions: dict, model: str = MODEL) -> str:
    blob = json.dumps([model, state, questions], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()


class DiskCache:
    """Append-only JSONL cache: request_key -> full response (answers + usage)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._d: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    self._d[row["k"]] = row["r"]
                except (ValueError, KeyError):
                    continue
        self._fh = open(self.path, "a", encoding="utf-8")

    def get(self, k: str) -> dict | None:
        return self._d.get(k)

    def put(self, k: str, r: dict) -> None:
        with _LOCK:
            self._d[k] = r
            self._fh.write(json.dumps({"k": k, "r": r}, ensure_ascii=False) + "\n")
            self._fh.flush()

    def close(self) -> None:
        self._fh.close()


_CACHES: dict[str, DiskCache] = {}
LAYA_URL = os.environ.get("WSBJEV_LAYA_URL", "http://127.0.0.1:8777")
LAYA_MODEL = "laya-typed-decisions"


def cache(backend: str = "jev") -> DiskCache:
    if backend not in _CACHES:
        name = "jev-cache.jsonl" if backend == "jev" else f"{backend}-cache.jsonl"
        _CACHES[backend] = DiskCache(ROOT / "runs" / name)
    return _CACHES[backend]


def _laya_post(reqs: list[tuple[dict, dict]], timeout: float = 600.0) -> list[dict]:
    import urllib.request

    body = json.dumps({"requests": [{"state": s, "questions": q} for s, q in reqs]}, ensure_ascii=False)
    r = urllib.request.Request(
        LAYA_URL + "/decide_many", data=body.encode("utf-8", "replace"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return json.loads(f.read())["responses"]


KEV_URL = os.environ.get("WSBJEV_KEV_URL", "http://127.0.0.1:8008")
KEV_MODEL = os.environ.get("WSBJEV_KEV_MODEL", "kev-27b")  # part of the cache key: never mix Kev sizes


def _kev_post(state: dict, questions: dict, timeout: float = 300.0) -> dict:
    import urllib.request

    body = json.dumps({"model": "kev-latest", "state": state, "questions": questions}, ensure_ascii=False)
    r = urllib.request.Request(KEV_URL + "/v1/systemone", data=body.encode("utf-8", "replace"),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return json.loads(f.read())


async def _decide_kev(requests, out, tally, progress, concurrency: int = int(os.environ.get("WSBJEV_KEV_CONCURRENCY", "32"))):
    """Kev (open-weights Jev, TypeSafe /v1/systemone contract) on a local server: same request, $0."""
    c = cache("kev")
    todo = []
    for i, (state, questions) in enumerate(requests):
        hit = c.get(request_key(state, questions, KEV_MODEL))
        if hit is not None:
            out[i] = hit
            tally.cached += 1
        else:
            todo.append(i)
    done = {"n": len(requests) - len(todo)}
    if os.environ.get("WSBJEV_KEV_CACHE_ONLY") == "1":  # score saved answers only; misses stay unjudged
        tally.errors += len(todo)
        if progress:
            progress(done["n"], len(requests))
        return out
    sem = asyncio.Semaphore(concurrency)

    async def one(i: int) -> None:
        state, questions = requests[i]
        async with sem:
            for attempt in range(3):
                try:
                    t0 = time.time()
                    r = await asyncio.to_thread(_kev_post, state, questions)
                    duty = float(os.environ.get("WSBJEV_KEV_DUTY", "1.0"))
                    if duty < 1.0:  # rest the local GPU: busy ~duty of the time (laptop heat)
                        await asyncio.sleep((time.time() - t0) * (1.0 - duty) / duty)
                    if r.get("answers"):
                        c.put(request_key(state, questions, KEV_MODEL), r)
                        out[i] = r
                        tally.calls += 1
                        break
                except Exception as e:  # noqa: BLE001
                    if attempt == 2:
                        tally.errors += 1
                        print(f"  kev error: {type(e).__name__}: {str(e)[:200]}")
                    await asyncio.sleep(1.0 + attempt)
        done["n"] += 1
        if progress and done["n"] % 8 == 0:
            progress(done["n"], len(requests))

    await asyncio.gather(*(one(i) for i in todo))
    if progress:
        progress(done["n"], len(requests))
    return out


FREE_URL = "https://api.experientiallabs.ai/v1/systemone"
FREE_TOK_PER_HOUR = float(os.environ.get("WSBJEV_FREE_TOK_PER_HOUR", "11000000"))  # free tier: 11.9M in/hour
TOK_PER_CHAR = 0.3313  # billed tokens per request char, measured on a paid Jev arm


class PaidCallError(RuntimeError):
    """A free-tier response reported a non-zero cost: stop everything."""


def _free_post(body_bytes: bytes, timeout: float = 120.0) -> dict:
    import urllib.error
    import urllib.request

    r = urllib.request.Request(FREE_URL, data=body_bytes, headers={
        "Authorization": f"Bearer {keys.get('EXPERIENTIAL_API_KEY')}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return json.loads(f.read())
    except urllib.error.HTTPError as e:
        err = RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        err.status = e.code  # type: ignore[attr-defined]
        raise err from e


async def _decide_free(requests, out, tally, progress, concurrency: int = int(os.environ.get("WSBJEV_FREE_CONCURRENCY", "8"))):
    """TypeSafe Jev on Experiential Labs' free tier. Paced under the hourly input-token cap;
    aborts the whole run if any response reports cost > 0 (the free route must never bill)."""
    c = cache("jevfree")
    todo = []
    for i, (state, questions) in enumerate(requests):
        hit = c.get(request_key(state, questions, "jev-free"))
        if hit is not None:
            out[i] = hit
            tally.cached += 1
        else:
            todo.append(i)
    done = {"n": len(requests) - len(todo)}
    sem = asyncio.Semaphore(concurrency)
    pace = {"t": time.time()}
    lock = asyncio.Lock()

    async def one(i: int) -> None:
        state, questions = requests[i]
        body = json.dumps({"model": "jev-latest", "state": state, "questions": questions}, ensure_ascii=False).encode("utf-8", "replace")
        est = len(body) * TOK_PER_CHAR
        async with lock:  # token-bucket pacing: reserve this request's share of the hour
            now = time.time()
            start = max(now, pace["t"])
            pace["t"] = start + est * 3600.0 / FREE_TOK_PER_HOUR
        if start > now:
            await asyncio.sleep(start - now)
        async with sem:
            for attempt in range(6):
                try:
                    r = await asyncio.to_thread(_free_post, body)
                except Exception as e:  # noqa: BLE001
                    status = getattr(e, "status", None)
                    if status in (401, 402, 403):
                        raise
                    if attempt < 5:
                        await asyncio.sleep(min(60.0, 2.0 * 2**attempt))
                        continue
                    tally.errors += 1
                    print(f"  jev-free error: {str(e)[:200]}")
                    break
                cost = float((r.get("usage") or {}).get("cost") or 0.0)
                if cost > 0:
                    raise PaidCallError(f"free Jev reported cost ${cost}; stopping (check Experiential 'Use credits' settings)")
                if r.get("answers"):
                    c.put(request_key(state, questions, "jev-free"), r)
                    out[i] = r
                    tally.calls += 1
                    tally.input_tokens += int((r.get("usage") or {}).get("input_tokens") or 0)
                break
        done["n"] += 1
        if progress and done["n"] % 8 == 0:
            progress(done["n"], len(requests))

    await asyncio.gather(*(one(i) for i in todo))
    if progress:
        progress(done["n"], len(requests))
    return out


def _decide_laya(requests, out, tally, progress, chunk: int = int(os.environ.get("WSBJEV_LAYA_CHUNK", "8"))):
    c = cache("laya")
    todo = []
    for i, (state, questions) in enumerate(requests):
        hit = c.get(request_key(state, questions, LAYA_MODEL))
        if hit is not None:
            out[i] = hit
            tally.cached += 1
        else:
            todo.append(i)
    done = len(requests) - len(todo)
    if progress:
        progress(done, len(requests))
    for k in range(0, len(todo), chunk):
        idx = todo[k : k + chunk]
        try:
            resps = _laya_post([requests[i] for i in idx])
        except Exception as e:  # noqa: BLE001
            print(f"  laya error: {type(e).__name__}: {str(e)[:200]}")
            tally.errors += len(idx)
            continue
        for i, r in zip(idx, resps, strict=True):
            if "answers" in r and r["answers"]:
                c.put(request_key(requests[i][0], requests[i][1], LAYA_MODEL), r)
                out[i] = r
                tally.calls += 1
            else:
                tally.errors += 1
                print(f"  laya cell error: {str(r.get('error'))[:200]}")
        done += len(idx)
        if progress:
            progress(done, len(requests))
    return out


def _mock_answer(q: dict, seed: str) -> dict:
    rng = random.Random(seed)
    t = q["type"]
    if t == "noul":
        return {"type": "noul", "noul": round(rng.random(), 2)}
    if t == "choice":
        opts = list(q["criteria"].keys())
        w = [rng.random() ** 3 for _ in opts]
        s = sum(w) or 1.0
        probs = {o: round(x / s, 2) for o, x in zip(opts, w, strict=True)}
        best = max(probs, key=probs.get)
        return {"type": "choice", "choice": best, "confidence": probs[best], "probabilities": probs}
    if t == "score":
        n = len(q["criteria"])
        w = [rng.random() ** 3 for _ in range(n)]
        s = sum(w) or 1.0
        probs = {str(i): round(x / s, 2) for i, x in enumerate(w)}
        score = sum(i * p for i, p in enumerate(probs.values()))
        return {"type": "score", "score": round(score, 2), "confidence": 0.5, "probabilities": probs}
    raise ValueError(f"unknown question type {t}")


def _mock_response(state: dict, questions: dict) -> dict:
    k = request_key(state, questions, "mock")
    return {
        "model": "mock",
        "answers": {qid: _mock_answer(q, k + qid) for qid, q in questions.items()},
        "usage": {"input_tokens": 0, "output_tokens": 0, "cost": 0.0},
    }


def _validate(questions: dict) -> None:
    for qid, q in questions.items():
        t = q.get("type")
        if t not in ("choice", "noul", "score"):
            raise ValueError(f"{qid}: bad type {t}")
        if not q.get("instructions"):
            raise ValueError(f"{qid}: empty instructions")
        c = q.get("criteria")
        if t == "choice" and (not isinstance(c, dict) or len(c) < 2):
            raise ValueError(f"{qid}: choice needs >= 2 criteria")
        if t == "noul" and (not isinstance(c, dict) or set(c) != {"true", "false"}):
            raise ValueError(f"{qid}: noul criteria must be {{true, false}}")
        if t == "score" and (not isinstance(c, list) or len(c) < 2):
            raise ValueError(f"{qid}: score needs a list of >= 2 levels")


def _http_post(body: dict, timeout: float) -> dict:
    import urllib.error
    import urllib.request

    key = keys.get("OPENROUTER_API_KEY")
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8", "replace"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as f:
            return json.loads(f.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", "replace")[:500]
        err = RuntimeError(f"HTTP {e.code}: {body_txt}")
        err.status = e.code  # type: ignore[attr-defined]
        raise err from e


async def decide_many(
    requests: list[tuple[dict, dict]],
    *,
    tag: str = "",
    concurrency: int = 24,
    timeout: float = 90.0,
    attempts: int = 8,
    mock: bool | None = None,
    tally: Tally | None = None,
    backend: str = "jev",
    progress=None,
) -> list[dict | None]:
    """[(state, questions)] -> [response | None], in order. Cached responses are reused.
    Raises BudgetExceeded before any call that would start past the cap."""
    if mock is None:
        mock = os.environ.get("WSBJEV_MOCK", "") == "1"
    tally = tally or Tally(tag=tag)
    out: list[dict | None] = [None] * len(requests)
    if backend == "laya":
        for _state, questions in requests:
            _validate(questions)
        return await asyncio.to_thread(_decide_laya, requests, out, tally, progress)
    if backend == "kev":
        for _state, questions in requests:
            _validate(questions)
        return await _decide_kev(requests, out, tally, progress)
    if backend == "jevfree":
        for _state, questions in requests:
            _validate(questions)
        return await _decide_free(requests, out, tally, progress)
    c = cache()
    todo: list[int] = []
    for i, (state, questions) in enumerate(requests):
        _validate(questions)
        if mock:
            out[i] = _mock_response(state, questions)
            sl = os.environ.get("WSBJEV_SIZE_LOG")
            if sl:  # costing dry run: record the exact request that would have been billed
                body = {"model": MODEL, "state": state, "questions": questions}
                with open(sl, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"tag": tag, "chars": len(json.dumps(body, ensure_ascii=False)),
                                         "nq": len(questions)}) + "\n")
            continue
        hit = c.get(request_key(state, questions))
        if hit is not None:
            out[i] = hit
            tally.cached += 1
        else:
            todo.append(i)
    if mock or not todo:
        return out
    cap = _cap()
    base = spent_total()
    if base >= cap:
        raise BudgetExceeded(f"jev spend ${base:.4f} already at cap ${cap:.2f}")
    sem = asyncio.Semaphore(concurrency)
    ledger_fh = open(LEDGER, "a", encoding="utf-8")
    running = {"usd": base}

    async def one(i: int) -> None:
        state, questions = requests[i]
        body = {"model": MODEL, "state": state, "questions": questions}
        async with sem:
            for a in range(attempts):
                if running["usd"] >= cap:
                    raise BudgetExceeded(f"jev spend ${running['usd']:.4f} reached cap ${cap:.2f}")
                try:
                    r = await asyncio.to_thread(_http_post, body, timeout)
                except Exception as e:  # noqa: BLE001
                    status = getattr(e, "status", None)
                    transient = status in _TRANSIENT or status is None
                    if status in (401, 402, 403):
                        raise
                    if transient and a < attempts - 1:
                        await asyncio.sleep(min(30.0, 1.5 * 2**a) + random.random())
                        continue
                    tally.errors += 1
                    print(f"  jev error [{tag}]: {str(e)[:200]}")
                    return
                if "answers" not in r:
                    if a < attempts - 1:
                        await asyncio.sleep(1.0 + random.random())
                        continue
                    tally.errors += 1
                    return
                usd = float((r.get("usage") or {}).get("cost") or 0.0)
                with _LOCK:
                    running["usd"] += usd
                    tally.usd += usd
                    tally.calls += 1
                    tally.input_tokens += int((r.get("usage") or {}).get("input_tokens") or 0)
                    ledger_fh.write(
                        json.dumps({"t": round(time.time(), 1), "tag": tag, "usd": usd}) + "\n"
                    )
                    ledger_fh.flush()
                c.put(request_key(state, questions), r)
                out[i] = r
                return

    try:
        await asyncio.gather(*(one(i) for i in todo))
    finally:
        ledger_fh.close()
    return out


def decide_many_sync(requests: list[tuple[dict, dict]], **kw: Any) -> list[dict | None]:
    return asyncio.run(decide_many(requests, **kw))

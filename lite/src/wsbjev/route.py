"""Install Jev as a WorkspaceBench judge route.

``install()`` patches ``wsbench.llm.stream_json`` / ``stream_json_async`` / ``preflight`` so that a
judge model id starting with ``jev`` is served by the port registry; every other model id goes
through the original code untouched (so the judge of record still runs from the same process).
Each landed result is the port's schema-conformant dict with the raw Jev answers under ``_jev``;
the family code caches it in ``<out>/cells.jsonl`` like any judge result.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from . import alt_routes, jev, keys
from .ports import lookup
from .ports.base import Direct

JEV_PREFIX = "jev"
_INSTALLED = False
TALLY = jev.Tally(tag="route")


def is_jev(model: str) -> bool:
    return model.startswith(JEV_PREFIX)


def backend_of(model: str) -> str:
    """``jev-laya`` -> local Laya server; ``jev-kev`` -> local Kev server (open-weights Jev);
    any other ``jev*`` id -> TypeSafe Jev on OpenRouter (the only one that costs money)."""
    if model.startswith("jev-laya"):
        return "laya"
    if model.startswith("jev-kev"):
        return "kev"
    if model.startswith("jev-free"):
        return "jevfree"
    return "jev"


_PROGRESS = {"total": 0, "done_before": 0}


def _live_writer(label: str):
    import json as _json
    import time as _time
    from pathlib import Path as _Path

    live = _Path(__file__).resolve().parents[2] / "runs" / "live"
    live.mkdir(parents=True, exist_ok=True)
    path = live / (label.replace("/", "__") + ".json")
    started = _time.time()

    def write(done: int, total: int, status: str = "running", extra: dict | None = None) -> None:
        rec = {"label": label, "done": done, "total": total, "status": status,
               "started": started, "updated": _time.time(), **(extra or {})}
        # best effort: on Windows a reader (dashboard, watcher, OneDrive sync) can hold the target open
        # and the rename fails; a status file must never kill the run it reports on
        for attempt in range(5):
            try:
                tmp = path.with_suffix(".tmp")
                tmp.write_text(_json.dumps(rec), encoding="utf-8")
                tmp.replace(path)
                return
            except OSError:
                _time.sleep(0.2 * (attempt + 1))

    return write


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    import wsbench.llm as llm

    # the family code reads OPENROUTER_API_KEY for non-claude ids; keep it in-process only
    if not os.environ.get("OPENROUTER_API_KEY"):
        k = keys.get("OPENROUTER_API_KEY")
        if k:
            os.environ["OPENROUTER_API_KEY"] = k

    orig_async = llm.stream_json_async
    orig_preflight = llm.preflight
    orig_preflight_async = llm.preflight_async

    async def stream_json_async(prompts, *, schema, model, on_result, **kw):  # type: ignore[no-untyped-def]
        smodel = os.environ.get("WSBJEV_SUMMARIZER_MODEL", "")
        if smodel and schema.get("name") == "interp" and model != smodel:
            # the official two-stage pipeline with a cheap text model writing the token-bag summaries
            # (e.g. qwen/qwen3.6-27b on OpenRouter, or vllm:<name>), whatever judges the readouts
            return await stream_json_async(prompts, schema=schema, model=smodel, on_result=on_result, **kw)
        if os.environ.get("WSBJEV_CAPTURE_ALSO") and not model.startswith("capture"):
            alt_routes.dump(prompts, schema)
        if alt_routes.is_alt(model):
            spend = kw.get("spend") or llm.Spend()
            await alt_routes.handle(prompts, schema=schema, model=model, on_result=on_result,
                                    spend=spend, temperature=kw.get("temperature"))
            return spend
        if not is_jev(model):
            return await orig_async(prompts, schema=schema, model=model, on_result=on_result, **kw)
        spend = kw.get("spend") or llm.Spend()
        port = lookup(schema)
        _sl = os.environ.get("WSBJEV_SIZE_LOG")
        if _sl:  # costing dry run: what the OFFICIAL judge would have been sent for these calls
            import json as _json

            with open(_sl, "a", encoding="utf-8") as _fh:
                _fh.write(_json.dumps({"tag": "official:" + str(schema.get("name")), "calls": len(prompts),
                                       "chars": sum(len(s_) + len(u_) for s_, u_ in prompts)}) + "\n")
        built: list[Any] = [port.build(s, u, schema) for s, u in prompts]
        live = [i for i, b in enumerate(built) if not isinstance(b, Direct)]
        before = TALLY.usd
        backend = backend_of(model)
        label = os.environ.get("WSBJEV_RUN_LABEL", port.name)
        writer = _live_writer(label) if backend in ("laya", "kev", "jevfree") else None
        base = _PROGRESS["done_before"]
        _PROGRESS["total"] = base + len(live)

        def progress(done: int, total: int) -> None:
            if writer:
                writer(base + done, base + total, extra={"stage": port.name})

        resps = await jev.decide_many(
            [(built[i].state, built[i].questions) for i in live],
            tag=port.name,
            concurrency=int(os.environ.get("WSBJEV_CONCURRENCY", "24")),
            tally=TALLY,
            backend=backend,
            progress=progress,
        )
        _PROGRESS["done_before"] = base + len(live)
        for i, b in enumerate(built):
            if isinstance(b, Direct):
                on_result(i, b.result)
        for i, r in zip(live, resps, strict=True):
            if r is None:
                spend.errors += 1
                on_result(i, None)
                continue
            try:
                res = port.parse(r["answers"], built[i], schema)
            except Exception as e:  # noqa: BLE001 - a port bug must not kill the batch
                print(f"  port {port.name} parse error: {type(e).__name__}: {e}")
                spend.errors += 1
                res = None
            on_result(i, res)
        spend.calls += len(live)
        spend.usd += TALLY.usd - before
        return spend

    def stream_json(prompts, *, schema, model, on_result, **kw):  # type: ignore[no-untyped-def]
        if not (is_jev(model) or alt_routes.is_alt(model)):
            return llm_orig_sync(prompts, schema=schema, model=model, on_result=on_result, **kw)
        return asyncio.run(
            stream_json_async(prompts, schema=schema, model=model, on_result=on_result, **kw)
        )

    llm_orig_sync = llm.stream_json

    def preflight(model, reasoning):  # type: ignore[no-untyped-def]
        if is_jev(model) or alt_routes.is_alt(model):
            return None
        return orig_preflight(model, reasoning)

    async def preflight_async(model, reasoning):  # type: ignore[no-untyped-def]
        if is_jev(model) or alt_routes.is_alt(model):
            return None
        return await orig_preflight_async(model, reasoning)

    llm.stream_json_async = stream_json_async
    llm.stream_json = stream_json
    llm.preflight = preflight
    llm.preflight_async = preflight_async
    # --- BEGIN agentic_misalignment stream_text hook (owner: ports/agentic_misalignment.py) ---
    # Free-text judge stages (llm.stream_text) for jev* model ids; other models untouched.
    from .overrides import agentic_misalignment as _am_text

    _am_text.install(llm, is_jev=is_jev, tally=TALLY)
    # --- END agentic_misalignment stream_text hook ---
    _INSTALLED = True

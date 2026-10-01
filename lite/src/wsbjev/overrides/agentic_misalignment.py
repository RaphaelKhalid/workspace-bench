"""``llm.stream_text`` hook for agentic_misalignment (the only free-text family).

``install(llm, is_jev=..., tally=...)`` wraps ``wsbench.llm.stream_text`` / ``stream_text_async``:
a model id for which ``is_jev`` is true is served by
:func:`wsbjev.ports.agentic_misalignment.run_text_batch` (Stage A/B/C prompts recognised by their
verbatim template heads); every other model id (the judge of record, ``claude-sonnet-5``) runs
the original upstream code untouched.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

_INSTALLED = False


def install(llm: Any, *, is_jev: Callable[[str], bool], tally: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    orig_async = llm.stream_text_async
    orig_sync = llm.stream_text

    async def stream_text_async(prompts, *, model, on_result, thinking, max_tokens, **kw):  # type: ignore[no-untyped-def]
        if not is_jev(model):
            return await orig_async(
                prompts,
                model=model,
                on_result=on_result,
                thinking=thinking,
                max_tokens=max_tokens,
                **kw,
            )
        from ..ports.agentic_misalignment import run_text_batch

        spend = kw.get("spend") or llm.Spend()
        if not prompts:
            return spend
        return await run_text_batch(prompts, on_result=on_result, spend=spend, tally=tally)

    def stream_text(prompts, *, model, on_result, thinking, max_tokens, **kw):  # type: ignore[no-untyped-def]
        if not is_jev(model):
            return orig_sync(
                prompts,
                model=model,
                on_result=on_result,
                thinking=thinking,
                max_tokens=max_tokens,
                **kw,
            )
        return asyncio.run(
            stream_text_async(
                prompts,
                model=model,
                on_result=on_result,
                thinking=thinking,
                max_tokens=max_tokens,
                **kw,
            )
        )

    llm.stream_text_async = stream_text_async
    llm.stream_text = stream_text
    _INSTALLED = True

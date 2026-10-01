"""Judge routes that use the ORIGINAL WorkspaceBench prompts and schema (no ports).

    vllm:<served-model-name>  each official (system, user) prompt goes to an OpenAI-compatible
                              vLLM server with the family's JSON schema enforced as
                              response_format (the same call shape the official Gemini judge gets).
                              URL: $WSBJEV_VLLM_URL (default http://127.0.0.1:8000/v1).
    capture                   write every official prompt to runs/captured/<label>.jsonl and leave
                              the cells unjudged (builds prompt packs for outside judges).
    replay:<verdicts.jsonl>   answer each prompt from a file of {"h": <prompt hash>, "result": {...}}
                              (e.g. Luna verdicts), so the family's own scoring runs on them.
    open-jb                   the open-weights jailbreak_recognition pipeline (RESULT_qwen_max.md):
                              summaries by qwen/qwen3.6-27b, verdicts by qwen/qwen3.8-27b with the
                              voice note (prompts/jb_v1_voice_note.txt) appended to the official
                              system prompt; reasoning off, temperature 0, both pinned to DeepInfra.
                              OpenRouter key from OPENROUTER_API_KEY.

The prompt hash is sha256(system + "\\x00" + user), the join key across all of these.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = ("vllm:", "capture", "replay:", "open-jb")
OPEN_SUMMARIZER, OPEN_JUDGE, OPEN_JUDGE_PROVIDER = "qwen/qwen3.6-27b", "qwen/qwen3.8-27b", "DeepInfra"
VOICE_NOTE = ROOT / "prompts" / "jb_v1_voice_note.txt"
_PROVIDER: contextvars.ContextVar = contextvars.ContextVar("wsbjev_provider", default=None)
_PINNED = False


def is_alt(model: str) -> bool:
    return model.startswith(PREFIXES)


def prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\x00" + user).encode("utf-8", "replace")).hexdigest()


def _label() -> str:
    return os.environ.get("WSBJEV_RUN_LABEL", "unlabelled").replace("/", "__")


def dump(prompts, schema) -> None:
    """Append the official prompts to runs/captured/<label>.jsonl (the `capture` route, or any route
    with WSBJEV_CAPTURE_ALSO=1, e.g. a cache-only vllm replay that yields prompts AND teacher labels)."""
    out = ROOT / "runs" / "captured"
    out.mkdir(parents=True, exist_ok=True)
    fname = "".join(c if c.isalnum() or c in "-_." else "_" for c in _label())  # no ':' (NTFS streams)
    with open(out / f"{fname}.jsonl", "a", encoding="utf-8") as fh:
        for s, u in prompts:
            fh.write(json.dumps({"h": prompt_hash(s, u), "label": _label(), "schema_name": schema.get("name"),
                                 "schema": schema, "system": s, "user": u}, ensure_ascii=False) + "\n")


def _capture(prompts, schema, on_result) -> None:
    dump(prompts, schema)
    for i in range(len(prompts)):
        on_result(i, None)


_REPLAY: dict[str, dict] = {}


def _replay(path: str, prompts, on_result) -> None:
    if path not in _REPLAY:
        d: dict = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row.get("result"), dict):
                    d[row["h"]] = row["result"]
        _REPLAY[path] = d
    table = _REPLAY[path]
    for i, (s, u) in enumerate(prompts):
        on_result(i, table.get(prompt_hash(s, u)))


class _VllmCache:
    def __init__(self) -> None:
        self.path = ROOT / "runs" / "vllm-cache.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.d: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    self.d[r["k"]] = r["r"]
                except (ValueError, KeyError):
                    continue
        self.fh = open(self.path, "a", encoding="utf-8")

    def put(self, k: str, r: dict) -> None:
        self.d[k] = r
        self.fh.write(json.dumps({"k": k, "r": r}, ensure_ascii=False) + "\n")
        self.fh.flush()


_VC: _VllmCache | None = None


async def _vllm(name: str, prompts, schema, on_result, spend, temperature) -> None:
    global _VC
    from openai import AsyncOpenAI

    if _VC is None:
        _VC = _VllmCache()
    client = AsyncOpenAI(base_url=os.environ.get("WSBJEV_VLLM_URL", "http://127.0.0.1:8000/v1"), api_key="local")
    sem = asyncio.Semaphore(int(os.environ.get("WSBJEV_VLLM_CONCURRENCY", "96")))
    rf = {"type": "json_schema", "json_schema": schema}

    async def one(i: int, s: str, u: str) -> None:
        k = f"{name}|{schema.get('name')}|{prompt_hash(s, u)}"
        if k in _VC.d:
            on_result(i, _VC.d[k])
            return
        async with sem:
            # valid verdicts are < 100 tokens; a runaway (an unclosed quote) is cut at the cap and
            # retried once at a small temperature, then left unjudged (as upstream does on failure)
            for attempt in range(2):
                try:
                    r = await client.chat.completions.create(
                        model=name,
                        messages=[{"role": "system", "content": s}, {"role": "user", "content": u}],
                        response_format=rf,
                        temperature=(0.0 if temperature is None else temperature) if attempt == 0 else 0.3,
                        max_tokens=int(os.environ.get("WSBJEV_VLLM_MAX_TOKENS", "384")),
                        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                        timeout=300,
                    )
                    spend.calls += 1
                    obj = json.loads((r.choices[0].message.content or "").strip())
                    if isinstance(obj, dict):
                        _VC.put(k, obj)
                        on_result(i, obj)
                        return
                except Exception as e:  # noqa: BLE001
                    last = f"{type(e).__name__}: {str(e)[:160]}"
                    spend.retries += 1
                    continue
            spend.errors += 1
            print(f"  vllm error: {last if 'last' in locals() else 'no result'}")
            on_result(i, None)

    try:
        await asyncio.gather(*(one(i, s, u) for i, (s, u) in enumerate(prompts)))
    finally:
        await client.close()


def _pin_providers(llm) -> None:
    """Let a call pin its OpenRouter provider (no fallbacks) through _PROVIDER; other calls untouched."""
    global _PINNED
    if _PINNED:
        return
    orig = llm._make_client

    def make_client(route_, key):
        client = orig(route_, key)
        create = client.chat.completions.create

        async def wrapped(*args, **kw):
            p = _PROVIDER.get()
            if p:
                kw["extra_body"] = {**(kw.get("extra_body") or {}),
                                    "provider": {"order": [p], "allow_fallbacks": False, "require_parameters": True}}
            return await create(*args, **kw)

        client.chat.completions.create = wrapped
        return client

    llm._make_client = make_client
    _PINNED = True


async def _open_jb(prompts, schema, on_result, spend) -> None:
    import wsbench.llm as llm

    _pin_providers(llm)
    off = {"enabled": False}
    if schema.get("name") == "readout_recognition":
        note = VOICE_NOTE.read_text(encoding="utf-8")
        _PROVIDER.set(OPEN_JUDGE_PROVIDER)
        await llm.stream_json_async([(s + note, u) for s, u in prompts], schema=schema, model=OPEN_JUDGE,
                                    on_result=on_result, reasoning=off, temperature=0.0, max_tokens=1500, spend=spend)
    else:  # the summarizer stage ("interp") and anything else: the open summarizer
        _PROVIDER.set(OPEN_JUDGE_PROVIDER)
        await llm.stream_json_async(prompts, schema=schema, model=OPEN_SUMMARIZER, on_result=on_result,
                                    reasoning=off, temperature=0.0, spend=spend)


async def handle(prompts, *, schema, model, on_result, spend, temperature=None) -> None:
    if model.startswith("open-jb"):
        await _open_jb(prompts, schema, on_result, spend)
    elif model.startswith("capture"):
        _capture(prompts, schema, on_result)
    elif model.startswith("replay:"):
        _replay(model[len("replay:"):], prompts, on_result)
    elif model.startswith("vllm:"):
        await _vllm(model[len("vllm:"):], prompts, schema, on_result, spend, temperature)
    else:
        raise ValueError(model)

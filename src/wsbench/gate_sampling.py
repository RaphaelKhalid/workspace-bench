"""Request building and output parsing for ``scripts/qwen_sample_modal.py`` (gpu.md G10): Qwen
sampling for item gating, each request row carrying its own settings.

Request row: ``{key, family, messages | text, n, temperature, top_p, top_k, max_tokens,
enable_thinking, greedy, prefill?, raw?}``; ``raw: true`` feeds ``text`` verbatim (no chat
template, no special tokens: the poetry plain-continuation gate leg). A row may ask for a greedy
draw AND ``n`` sampled draws; thinking on/off is per row. Output row: ``{key, draw, greedy,
text, thinking, finish_reason}``.
Grading happens locally, per family, by the family spec's own rule."""

import hashlib
from collections.abc import Mapping
from typing import Any

REQUIRED = ("key", "family", "n", "temperature", "max_tokens", "enable_thinking", "greedy")
THINK_END = "</think>"


def validate(row: Mapping[str, Any]) -> None:
    missing = [k for k in REQUIRED if k not in row]
    if missing:
        raise ValueError(f"{row.get('key')}: request row lacks {missing}")
    if ("messages" in row) == ("text" in row):
        raise ValueError(f"{row['key']}: give exactly one of messages / text")
    if int(row["n"]) < 0 or (int(row["n"]) == 0 and not row["greedy"]):
        raise ValueError(f"{row['key']}: asks for no draw (n=0 and greedy=false)")


def seed(family: str, key: str, draw: int = 0) -> int:
    """``qwen_seed(family, key, draw)``: 4 bytes of sha256, distinct per (family, key, draw)."""
    return int.from_bytes(hashlib.sha256(f"{family}|{key}|{draw}".encode()).digest()[:4], "big")


def request_ids(tok: Any, row: Mapping[str, Any]) -> list[int]:
    """Token ids of one request: ``messages`` through the chat template exactly as the read
    plan renders them (``produce.render._chat``, plus ``enable_thinking`` per row), or ``text``
    as one user turn (``text_inversion.qwen_prompt_ids`` with thinking off: no special token can
    match inside the user span); ``prefill`` appended verbatim to the assistant turn."""
    think = bool(row.get("enable_thinking"))
    if row.get("raw"):  # a plain continuation: the text verbatim, no template (poetry plain leg)
        if "messages" in row or think:
            raise ValueError(f"{row['key']}: raw=true takes `text` and enable_thinking=false")
        ids = list(tok(str(row["text"]), add_special_tokens=False)["input_ids"])
    elif "messages" in row:
        out = tok.apply_chat_template(
            list(row["messages"]), tokenize=True, add_generation_prompt=True, enable_thinking=think
        )
        ids = list(out["input_ids"] if hasattr(out, "keys") else out)
    elif not think:
        from wsbench.baselines.text_inversion import qwen_prompt_ids

        ids = qwen_prompt_ids(tok, str(row["text"]))
    else:
        out = tok.apply_chat_template(
            [{"role": "user", "content": str(row["text"])}],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=True,
        )
        ids = list(out["input_ids"] if hasattr(out, "keys") else out)
    if row.get("prefill"):
        ids += tok(str(row["prefill"]), add_special_tokens=False)["input_ids"]
    return ids


def sampling_params(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The vLLM SamplingParams kwargs of a row: the greedy draw (if asked) then ``n`` sampled
    draws in ONE seeded request (``seed(family, key)``)."""
    out: list[dict[str, Any]] = []
    if row["greedy"]:
        out.append({"temperature": 0.0, "max_tokens": int(row["max_tokens"]), "n": 1})
    if int(row["n"]) > 0:
        out.append(
            {
                "n": int(row["n"]),
                "temperature": float(row["temperature"]),
                "top_p": float(row.get("top_p", 1.0)),
                "top_k": int(row.get("top_k", 0)),
                "max_tokens": int(row["max_tokens"]),
                "seed": seed(str(row["family"]), str(row["key"])),
            }
        )
    return out


def split_thinking(text: str, enable_thinking: bool) -> tuple[str, str]:
    """(thinking, answer): the text before / after ``</think>`` when thinking is on."""
    if enable_thinking and THINK_END in text:
        head, tail = text.split(THINK_END, 1)
        return head.replace("<think>", "").strip(), tail.strip()
    return "", text.strip()


def output_rows(
    row: Mapping[str, Any], outputs: list[list[tuple[str, str]]]
) -> list[dict[str, Any]]:
    """``outputs`` = per sampling_params entry, the (text, finish_reason) of each draw."""
    rows = []
    kinds = ([True] if row["greedy"] else []) + ([False] if int(row["n"]) > 0 else [])
    for is_greedy, outs in zip(kinds, outputs, strict=True):
        for d, (text, finish) in enumerate(outs):
            thinking, answer = split_thinking(text, bool(row.get("enable_thinking")))
            rows.append(
                {
                    "key": row["key"],
                    "family": row["family"],
                    "draw": -1 if is_greedy else d,
                    "greedy": is_greedy,
                    "text": answer,
                    "thinking": thinking,
                    "finish_reason": finish,
                }
            )
    return rows

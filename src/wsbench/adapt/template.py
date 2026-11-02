"""The subject's chat-template markers, read off its own render (no template's literals in code):
a one-turn conversation with a sentinel user message, rendered with the generation prompt, gives
the token that opens a user turn, the one that closes it, and the generation-prompt tail."""

from typing import Any

SENTINEL = "ZQXSENTINELXQZ"


def markers(tok: Any) -> dict[str, Any]:
    out = tok.apply_chat_template([{"role": "user", "content": SENTINEL}], tokenize=True,
                                  add_generation_prompt=True, enable_thinking=False)  # fmt: skip
    ids = list(out["input_ids"] if hasattr(out, "keys") else out)
    toks = [tok.decode([i], skip_special_tokens=False) for i in ids]
    text, acc, s0, s1 = "".join(toks), 0, None, None
    at = text.index(SENTINEL)
    for i, t in enumerate(toks):  # token span of the sentinel
        if s0 is None and acc + len(t) > at:
            s0 = i
        acc += len(t)
        if s0 is not None and acc >= at + len(SENTINEL):
            s1 = i
            break
    if s0 is None or s1 is None:
        raise ValueError("template: sentinel not found in the render")
    role = next(i for i in range(s0 - 1, -1, -1) if toks[i].strip() in ("user", "<|user|>"))
    start = role if toks[role].strip() == "<|user|>" else role - 1  # GLM: role-named marker
    return {
        "turn_start_id": ids[start], "turn_start": toks[start],
        "turn_end_id": ids[s1 + 1], "turn_end": toks[s1 + 1],
        "header_len": s0 - start,  # marker + role + newline(s) before the content
        "gen_tail": toks[s1 + 2 :],  # what follows the closing marker (generation prompt)
    }  # fmt: skip


def bos_prefix(tok: Any) -> list[int]:
    """Token ids a raw (non-chat) render must start with: the special tokens the subject's own
    chat render opens with before its first role marker, when the tokenizer does not add them by
    itself. Gemma-4: [<bos>] (without it the model loops: "26 is 26 is"; Gemma audit, 0/698 plain
    legs passed); GLM-5.3: [[gMASK], <sop>]. Qwen, OLMo, Kimi (the render opens with a role
    marker): [] — their renders are unchanged."""
    out = tok.apply_chat_template([{"role": "user", "content": SENTINEL}], tokenize=True,
                                  add_generation_prompt=True, enable_thinking=False)  # fmt: skip
    ids = list(out["input_ids"] if hasattr(out, "keys") else out)
    special = set(getattr(tok, "all_special_ids", []) or [])
    special |= {int(i) for i in getattr(tok, "added_tokens_decoder", {}) or {}}
    start = markers(tok)["turn_start_id"]
    lead: list[int] = []
    for i in ids:
        text = tok.decode([i], skip_special_tokens=False)
        if i == start or i not in special or "system" in text or "user" in text:
            break
        lead.append(i)
    plain = tok("x", add_special_tokens=True)["input_ids"]
    return [] if not lead or plain[: len(lead)] == lead else lead


def stop_ids(tok: Any, gen_eos: Any = None) -> list[int]:
    """Every id that ends a reply: the tokenizer's eos, the generation config's eos list, and the
    template's own turn-closing marker."""
    ids = {tok.eos_token_id, markers(tok)["turn_end_id"]}
    for e in gen_eos if isinstance(gen_eos, list) else [gen_eos]:
        ids.add(e)
    return sorted(i for i in ids if i is not None)


OPEN_THINK = ("<think>", "<|channel>thought", "<|think|>")  # an unclosed reasoning block


def check(tok: Any) -> list[str]:
    """Step-0 render check (SKILL.md): with ``enable_thinking=False`` the generation prompt must not
    leave a reasoning block open, the markers must be derivable, and a system turn must render.
    Returns the problems (empty = the template is safe to gate with)."""
    problems = []
    try:
        m = markers(tok)
    except (ValueError, StopIteration, IndexError) as e:
        return [f"turn markers not derivable from the render: {e!r}"]
    tail = "".join(m["gen_tail"])
    for o in OPEN_THINK:
        if o in tail and tail.rfind(o) > max(tail.rfind("</think>"), tail.rfind("<channel|>")):
            problems.append(f"generation prompt leaves a reasoning block open: {tail!r}")
    try:
        tok.apply_chat_template([{"role": "system", "content": "S"}, {"role": "user",
                                "content": "U"}], tokenize=False, add_generation_prompt=True,
                                enable_thinking=False)  # fmt: skip
    except Exception as e:
        problems.append(f"template rejects a system turn ({type(e).__name__}); moral/agentic "
                        "asks with a system prompt need it folded into the user turn")  # fmt: skip
    return problems

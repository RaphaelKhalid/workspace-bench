"""wsbench.gate_sampling (gpu.md G10): per-row settings, read-plan-identical renders."""

import pytest

from wsbench import gate_sampling as gs
from wsbench.produce.render import _chat


class Tok:
    """A tokenizer stand-in: one id per character; the template wraps the turns."""

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [ord(c) for c in text]}

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, enable_thinking):
        body = "".join(f"<{m['role']}>{m['content']}" for m in messages)
        body += "<assistant>" + ("" if enable_thinking else "<think></think>")
        return [ord(c) for c in body] if tokenize else body


def _row(**kw):
    base = {
        "key": "k",
        "family": "jailbreak_recognition",
        "n": 10,
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 512,
        "enable_thinking": False,
        "greedy": True,
    }
    return {**base, **kw}


def test_request_ids_match_readplan_render():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]
    assert gs.request_ids(Tok(), _row(messages=msgs)) == _chat(Tok(), msgs)
    assert gs.request_ids(Tok(), _row(messages=msgs, prefill="My")) == _chat(Tok(), msgs, "My")


def test_per_row_settings_honoured():
    think = _row(enable_thinking=True, greedy=False, max_tokens=2048, messages=[])
    nothink = _row(n=10, max_tokens=512, messages=[])
    greedy_only = _row(n=0, messages=[])
    p_think, p_no, p_g = (gs.sampling_params(r) for r in (think, nothink, greedy_only))
    assert len(p_think) == 1 and p_think[0]["max_tokens"] == 2048 and p_think[0]["n"] == 10
    assert [p["temperature"] for p in p_no] == [0.0, 1.0] and p_no[1]["top_p"] == 0.95
    assert p_g == [{"temperature": 0.0, "max_tokens": 512, "n": 1}]
    rows = gs.output_rows(think, [[("<think>hmm</think> ok", "stop")] * 10])
    assert rows[0]["thinking"] == "hmm" and rows[0]["text"] == "ok" and len(rows) == 10
    g = gs.output_rows(nothink, [[("A", "stop")], [("B", "length")] * 10])
    assert g[0]["greedy"] is True and g[0]["draw"] == -1 and g[1]["finish_reason"] == "length"
    assert gs.seed("f", "k") != gs.seed("f", "k2")
    with pytest.raises(ValueError):
        gs.validate(_row(n=0, greedy=False, text="x"))
    with pytest.raises(ValueError):
        gs.validate(_row(text="x", messages=[]))


def test_raw_row_is_the_text_verbatim():
    """plan 0038: the poetry plain-continuation leg feeds the couplet with no chat template."""
    text = "A rhyming couplet:\nThe sky,\nAnd "
    assert gs.request_ids(Tok(), _row(text=text, raw=True)) == [ord(c) for c in text]
    with pytest.raises(ValueError):
        gs.request_ids(Tok(), _row(messages=[{"role": "user", "content": "x"}], raw=True))
    with pytest.raises(ValueError):
        gs.request_ids(Tok(), _row(text=text, raw=True, enable_thinking=True))

"""llm._anthropic_once with a fake client: native requests are unchanged, the refusal-fallback
path uses the beta endpoint (+ the OAuth beta only for bearer clients), and a mid-output refusal
(partial text, fallback seam, served text) parses (plan 0021)."""

import asyncio
from types import SimpleNamespace

from wsbench import llm
from wsbench.llm import Spend, schema_block

SCHEMA = schema_block("t", {"a": {"type": "integer"}}, ["a"])


def _resp(blocks, model="claude-opus-5-5", stop="end_turn"):
    return SimpleNamespace(
        content=blocks,
        model=model,
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


def _text(t):
    return SimpleNamespace(type="text", text=t)


class FakeClient:
    def __init__(self, resp, auth_token=None):
        self.resp, self.auth_token = resp, auth_token
        self.native: list[dict] = []
        self.beta_calls: list[dict] = []
        outer = self

        class _Msgs:
            async def create(self, **kw):
                outer.native.append(kw)
                return outer.resp

        class _BetaMsgs:
            async def create(self, **kw):
                outer.beta_calls.append(kw)
                return outer.resp

        self.messages = _Msgs()
        self.beta = SimpleNamespace(messages=_BetaMsgs())


def _call(client, **kw):
    return asyncio.run(
        llm._anthropic_once(
            client,
            "sys",
            "user",
            schema=SCHEMA,
            model="claude-opus-5-5",
            max_tokens=10,
            timeout=5.0,
            spend=Spend(),
            **kw,
        )
    )


def test_native_request_unchanged():
    c = FakeClient(_resp([_text('{"a": 1}')]))
    assert _call(c) == {"a": 1}
    assert not c.beta_calls and len(c.native) == 1
    assert set(c.native[0]) == {
        "timeout",
        "model",
        "max_tokens",
        "system",
        "messages",
        "output_config",
    }


def test_fallback_uses_beta_endpoint_and_oauth_beta_only_for_bearer():
    c = FakeClient(_resp([_text('{"a": 2}')]))
    assert _call(c, fallbacks="default") == {"a": 2}  # not served by a fallback: no SERVED_BY
    assert (
        c.beta_calls[0]["betas"] == [llm.FALLBACK_BETA]
        and c.beta_calls[0]["fallbacks"] == "default"
    )
    c2 = FakeClient(_resp([_text('{"a": 3}')]), auth_token="tok")
    _call(c2, fallbacks="default")
    assert c2.beta_calls[0]["betas"] == [llm.FALLBACK_BETA, "oauth-2025-04-20"]


def test_mid_output_refusal_parses_served_text():
    seam = SimpleNamespace(type="fallback")
    # the declining model wrote half an object; the fallback model wrote a complete one
    c = FakeClient(_resp([_text('{"a": '), seam, _text('{"a": 4}')], model="claude-opus-4-8"))
    out = _call(c, fallbacks="default")
    assert out["a"] == 4 and out[llm.SERVED_BY] == "claude-opus-4-8"
    # ... or continued the partial as a prefill
    c = FakeClient(_resp([_text('{"a": '), seam, _text("5}")], model="claude-opus-4-8"))
    out = _call(c, fallbacks="default")
    assert out["a"] == 5 and out[llm.SERVED_BY] == "claude-opus-4-8"


def test_refusal_marker_when_whole_chain_refuses():
    c = FakeClient(_resp([], stop="refusal"))
    assert _call(c, fallbacks="default", mark_refusals=True) == llm.REFUSED_JSON
    assert _call(c, fallbacks="default") is None

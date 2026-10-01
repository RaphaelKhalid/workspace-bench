"""Free-only routing rejects paid fallbacks, bad metadata and unusable responses."""

import json
from types import SimpleNamespace

import pytest

from wsbench import free_route, llm
from wsbench.cache import fingerprint
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.summarizer import aux_judge


@pytest.fixture
def free(monkeypatch, tmp_path):
    monkeypatch.setenv("WSBENCH_FREE_ONLY", "1")
    monkeypatch.setenv("WSBENCH_FREE_LEDGER", str(tmp_path / "free.jsonl"))
    monkeypatch.setenv("WSBENCH_FREE_MAX_REQUESTS", "10")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    free_route._instance.cache_clear()
    endpoint = {
        "tag": "modelrun/fp4",
        "provider_name": "ModelRun",
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["structured_outputs"],
    }
    quota = {"used": 0, "limit": 1000, "remaining": 1000}
    monkeypatch.setattr(
        free_route,
        "_get",
        lambda path: (
            {"endpoints": [endpoint]} if path != "/key" else {"free_model_daily_requests": quota}
        ),
    )
    monkeypatch.setattr(llm, "_ATTEMPTS", 1)

    async def no_pace(rpm):
        pass

    monkeypatch.setattr(llm, "_pace", no_pace)
    yield endpoint, quota
    free_route._instance.cache_clear()


class Fake:
    def __init__(self, *, text='{"a":1}', provider="ModelRun", cost=0, stop="stop", error=None):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.response = SimpleNamespace(
            id="test-response",
            model=free_route.DEFAULT_MODEL,
            provider=provider,
            usage=SimpleNamespace(cost=cost, prompt_tokens=3, completion_tokens=4),
            choices=[SimpleNamespace(finish_reason=stop, message=SimpleNamespace(content=text))],
        )
        self.error = error

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response

    async def close(self):
        pass


def call(fake, monkeypatch, *, model=free_route.DEFAULT_MODEL):
    monkeypatch.setattr(llm, "_make_client", lambda route, key: fake)
    results = []
    spend = llm.stream_json(
        [("Reply JSON.", '{"a":1}')],
        model=model,
        schema=llm.schema_block("t", {"a": {"type": "integer"}}, ["a"]),
        on_result=lambda i, r: results.append(r),
    )
    return results, spend


def test_free_json_pins_provider_disables_fallback_and_records_zero_cost(free, monkeypatch):
    fake = Fake()
    results, spend = call(fake, monkeypatch)
    assert results == [{"a": 1}] and spend.usd == 0 and spend.calls == 1
    provider = fake.calls[0]["extra_body"]["provider"]
    assert provider["only"] == ["modelrun/fp4"]
    assert provider["allow_fallbacks"] is False and provider["require_parameters"] is True
    assert set(provider["max_price"].values()) == {0}
    ledger = [json.loads(line) for line in free_route.active().ledger.read_text().splitlines()]
    assert [row["event"] for row in ledger] == ["verified", "reserved", "response"]
    assert ledger[-1]["provider"] == "ModelRun" and ledger[-1]["cost_usd"] == 0


@pytest.mark.parametrize("damage", ["price", "unknown_price", "quota", "provider", "schema"])
def test_bad_metadata_blocks_inference(free, monkeypatch, damage):
    endpoint, quota = free
    if damage == "price":
        endpoint["pricing"]["request"] = "0.001"
    elif damage == "unknown_price":
        del endpoint["pricing"]["prompt"]
    elif damage == "quota":
        quota["remaining"] = 0
    elif damage == "provider":
        endpoint["tag"] = "other"
    else:
        endpoint["supported_parameters"] = []
    fake = Fake()
    with pytest.raises(llm.JudgeConfigError):
        call(fake, monkeypatch)
    assert not fake.calls


@pytest.mark.parametrize("model", ["claude-sonnet-5", "qwen/qwen3.8-27b", "other/model:free"])
def test_primary_and_auxiliary_paid_or_changed_routes_are_rejected(free, monkeypatch, model):
    fake = Fake()
    with pytest.raises(llm.JudgeConfigError):
        call(fake, monkeypatch, model=model)
    assert not fake.calls


@pytest.mark.parametrize("kwargs", [{"cost": None}, {"cost": 0.01}, {"provider": "Other"}])
def test_bad_response_provenance_stops_without_scoring(free, monkeypatch, kwargs):
    fake = Fake(**kwargs)
    with pytest.raises(llm.JudgeConfigError, match="cost/provider"):
        call(fake, monkeypatch)
    with pytest.raises(llm.JudgeConfigError):
        call(fake, monkeypatch)
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"text": "{}"},
        {"text": '{"a":"wrong type"}'},
        {"stop": "length"},
        {"stop": "content_filter"},
    ],
)
def test_schema_failures_truncations_and_refusals_are_unjudged(free, monkeypatch, kwargs):
    results, _ = call(Fake(**kwargs), monkeypatch)
    assert results == [None]


def test_call_cap_includes_every_actual_attempt(free, monkeypatch):
    monkeypatch.setenv("WSBENCH_FREE_MAX_REQUESTS", "1")
    fake = Fake()
    call(fake, monkeypatch)
    with pytest.raises(llm.JudgeConfigError, match="request cap"):
        call(fake, monkeypatch)
    assert len(fake.calls) == 1


def test_429_does_not_retry_or_switch_provider(free, monkeypatch):
    class RateLimitedError(Exception):
        status_code = 429

    fake = Fake(error=RateLimitedError())
    with pytest.raises(llm.JudgeConfigError, match="rate/quota"):
        call(fake, monkeypatch)
    assert len(fake.calls) == 1


def test_free_text_uses_same_guard_and_preserves_user_only_boundary(free, monkeypatch):
    fake = Fake(text="A short blind account.")
    monkeypatch.setattr(llm, "_make_client", lambda route, key: fake)
    results = []
    llm.stream_text(
        ["Readouts only"],
        model=free_route.DEFAULT_MODEL,
        thinking=False,
        max_tokens=100,
        on_result=lambda i, text: results.append(text),
    )
    assert results == ["A short blind account."]
    assert fake.calls[0]["messages"] == [{"role": "user", "content": "Readouts only"}]
    assert "response_format" not in fake.calls[0]
    assert fake.calls[0]["extra_body"]["reasoning"] == {"enabled": False}
    assert fake.calls[0]["extra_body"]["provider"]["allow_fallbacks"] is False


def test_auxiliary_defaults_follow_explicit_free_protocol_and_cache_changes(free, monkeypatch):
    judge = resolve(JudgeConfig(model="claude-sonnet-5"), env={})
    assert judge.model == free_route.DEFAULT_MODEL and not judge.pinned
    assert aux_judge(judge, {"summarizer": "paid/model"}, "summarizer") == judge
    before = fingerprint("same prompt")
    monkeypatch.setenv("WSBENCH_FREE_PROVIDER", "different/endpoint")
    assert fingerprint("same prompt") != before
    monkeypatch.setenv("WSBENCH_FREE_ONLY", "0")
    assert fingerprint("same prompt") != before


def test_malformed_agentic_grade_is_not_a_zero_score(free):
    from wsbench.evals.agentic_misalignment.judge import valid_free_design_reply

    for text in ("I cannot answer", "{}", '{"design_fidelity":0}', "[]"):
        assert not valid_free_design_reply(text)


def test_smoke_preserves_success_when_next_stage_is_rate_limited(free, monkeypatch, tmp_path):
    from wsbench.free_smoke import run

    def json_ok(prompts, **kwargs):
        kwargs["on_result"](0, {"ok": True, "labels": ["neutral"]})

    def text_limited(prompts, **kwargs):
        raise llm.JudgeConfigError("rate limited")

    monkeypatch.setattr(llm, "stream_json", json_ok)
    monkeypatch.setattr(llm, "stream_text", text_limited)
    path = tmp_path / "smoke.json"
    report = run(path, ("json", "text", "thinking_text"))
    assert json.loads(path.read_text()) == report
    assert [r["pass"] for r in report["tests"]] == [True, False]
    assert report["tests"][1]["error"] == "rate limited"


def test_agentic_failed_grade_is_not_cached(free, monkeypatch, mk_args, tmp_path):
    from wsbench.cache import Cache
    from wsbench.evals.agentic_misalignment import judge

    monkeypatch.setattr(llm, "stream_text", lambda prompts, **kw: kw["on_result"](0, "{}"))
    args = mk_args(tmp_path / "unused", judge=resolve(JudgeConfig(), env={}))
    with Cache(tmp_path / "cache.jsonl") as cache:
        results = judge._batch(
            "C",
            [("C:item", "test", "design prompt")],
            thinking=True,
            max_tokens=100,
            args=args,
            cache=cache,
            spend=llm.Spend(),
        )
        assert results == {"C:item": None}
        assert len(cache) == 0

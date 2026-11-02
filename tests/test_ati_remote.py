"""The hosted-reader routes of the ATI panel (decision R1-ATI rev: astra via OpenAI WIF).

All offline: the OpenAI client and the token exchange are fakes."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import openai
import pytest

from wsbench.baselines import ati_remote as ar
from wsbench.baselines import text_inversion as ti

ENV = {
    "MODAL_IDENTITY_TOKEN": "jwt-identity",
    "OPENAI_IDENTITY_PROVIDER_ID_MODAL": "idp-1",
    "OPENAI_SERVICE_ACCOUNT_ID": "sa-1",
    "OPENAI_PROJECT_ID": "proj-1",
}
REQ = {
    "family": "fam",
    "id": "a",
    "draw": 1,
    "prompt_sha": "abc",
    "answerer": "astra",
    "content": "What is the model thinking about?",
}


# ---------------------------------------------------------------- request parity


def test_both_routes_send_the_same_question_and_ceiling():
    """The OpenRouter call is unchanged (model, max_tokens=16000, one user message); the WIF call
    differs only in the model id's prefix and the ceiling's parameter name."""
    model = ti.PANEL["astra"]
    o = ar.completion_kwargs("openrouter", model, REQ["content"])
    w = ar.completion_kwargs("openai-wif", model, REQ["content"])
    assert o == {
        "model": "openai/gpt-6-astra",
        "max_tokens": 16000,
        "messages": [{"role": "user", "content": REQ["content"]}],
    }
    assert w == {
        "model": "gpt-6-astra",
        "max_completion_tokens": 16000,
        "messages": o["messages"],
    }
    for kw in (o, w):  # provider defaults on both: no sampling / reasoning overrides
        assert not {"temperature", "top_p", "reasoning", "reasoning_effort", "seed"} & set(kw)


def test_route_model_rejects_non_openai_models_on_wif():
    with pytest.raises(ValueError, match="OpenAI models only"):
        ar.route_model(ti.PANEL["argon"], "openai-wif")
    with pytest.raises(ValueError, match="route must be"):
        ar.route_model("x", "bedrock")


def test_classify_error_by_route():
    assert ar.classify_error(401, {}, "openai-wif") == "auth"
    assert ar.classify_error(401, {}, "openrouter") == "abort"
    assert ar.classify_error(403, {}, "openai-wif") == "abort"
    assert ar.classify_error(429, {}) == "rate"
    flagged = {"error": {"metadata": {"reasons": ["x"]}}}
    assert ar.classify_error(403, flagged) == "refusal"
    assert ar.classify_error(500, {}) == "retry"


# ---------------------------------------------------------------- token exchange


class _Post:
    def __init__(self, *responses: tuple[int, Any]):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, url: str, payload: dict) -> tuple[int, Any]:
        self.calls.append((url, payload))
        return self.responses.pop(0)


def test_wif_token_exchange_caches_and_refreshes():
    now = [0.0]
    post = _Post(
        (200, {"access_token": "tok-1", "expires_in": 3600}),
        (200, {"access_token": "tok-2", "expires_in": 3600}),
        (200, {"access_token": "tok-3"}),
    )
    t = ar.WifToken(ENV, post=post, clock=lambda: now[0])
    assert asyncio.run(t.get()) == "tok-1"
    assert asyncio.run(t.get()) == "tok-1"  # cached
    url, body = post.calls[0]
    assert url == "https://auth.openai.com/oauth/token"
    assert body == {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "subject_token": "jwt-identity",
        "identity_provider_id": "idp-1",
        "service_account_id": "sa-1",
    }
    now[0] = 3600 - ar.TOKEN_MARGIN_S  # inside the margin: re-exchanged before expiry
    assert asyncio.run(t.get()) == "tok-2"
    t.invalidate()  # a 401
    assert asyncio.run(t.get()) == "tok-3"
    assert t.exchanges == 3


def test_wif_token_failure_aborts_without_echoing_the_body():
    post = _Post((400, {"error": "invalid_grant", "subject_token": "jwt-identity"}))
    t = ar.WifToken(ENV, post=post)
    with pytest.raises(ar.AbortError) as exc:
        asyncio.run(t.get())
    assert "invalid_grant" in str(exc.value) and "jwt-identity" not in str(exc.value)


def test_wif_token_exchange_5xx_is_retryable_and_a_late_401_keeps_a_new_token():
    post = _Post((503, {}), (200, {"access_token": "tok-1"}), (200, {"access_token": "tok-2"}))
    t = ar.WifToken(ENV, post=post)
    with pytest.raises(ar.TransientExchangeError):
        asyncio.run(t.get())
    assert asyncio.run(t.get()) == "tok-1"
    t.invalidate("tok-0")  # a 401 on a token already replaced: no re-exchange
    assert asyncio.run(t.get()) == "tok-1" and t.exchanges == 1
    t.invalidate("tok-1")
    assert asyncio.run(t.get()) == "tok-2"


def test_wif_answer_retries_a_transient_exchange_failure():
    calls: list[dict] = []
    post = _Post((502, {}), (200, {"access_token": "t1"}))
    clients = ar.Clients(
        "openai-wif",
        env=ENV,
        factory=lambda k, b, h: _Client(calls, [_completion("ok")]),
        token=ar.WifToken(ENV, post=post),
    )
    assert _answer(clients)["answer"] == "ok"


def test_wif_token_needs_the_secret_and_the_identity_token():
    with pytest.raises(ar.AbortError, match="MODAL_IDENTITY_TOKEN"):
        ar.WifToken({k: v for k, v in ENV.items() if k != "MODAL_IDENTITY_TOKEN"})


# ---------------------------------------------------------------- one answer


def _status_error(code: int) -> openai.APIStatusError:
    # built without its constructor: the http-client type it takes differs across openai majors
    err = openai.APIStatusError.__new__(openai.APIStatusError)
    Exception.__init__(err, "x")
    err.status_code = code
    err.response = SimpleNamespace(json=lambda: {"error": {"message": "x"}})
    return err


def _completion(text: str, model: str = "gpt-6-astra-2026-10-01") -> Any:
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=20,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )
    choice = SimpleNamespace(
        message=SimpleNamespace(content=text, refusal=None), finish_reason="stop"
    )
    return SimpleNamespace(choices=[choice], usage=usage, model=model)


class _Client:
    """A fake AsyncOpenAI: ``outcomes`` are returned / raised in order; records every call."""

    def __init__(self, log: list, outcomes: list):
        self.log, self.outcomes = log, outcomes
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw: Any) -> Any:
        self.log.append(kw)
        o = self.outcomes.pop(0)
        if isinstance(o, BaseException):
            raise o
        return o


def _clients(route: str, outcomes: list, tokens: list[str] | None = None):
    calls: list[dict] = []
    made: list[tuple] = []

    def factory(key: str, base: str | None, headers: dict) -> _Client:
        made.append((key, base, headers))
        return _Client(calls, outcomes)

    token = None
    if route == "openai-wif":
        post = _Post(*[(200, {"access_token": t, "expires_in": 3600}) for t in tokens or ["t1"]])
        token = ar.WifToken(ENV, post=post)
    env = {"OPENROUTER_API_KEY": "or-key"} if route == "openrouter" else ENV
    return ar.Clients(route, env=env, factory=factory, token=token), calls, made


async def _nosleep(_: float) -> None:
    return None


def _answer(clients: ar.Clients) -> dict:
    return asyncio.run(
        ar.answer_one(clients, asyncio.Semaphore(1), ti.PANEL["astra"], REQ, sleep=_nosleep)
    )


def test_wif_answer_records_the_route_and_uses_the_project_header():
    clients, calls, made = _clients("openai-wif", [_completion("ice hockey")])
    row = _answer(clients)
    assert made == [("t1", None, {"OpenAI-Project": "proj-1"})]  # api.openai.com (default base)
    assert calls == [ar.completion_kwargs("openai-wif", ti.PANEL["astra"], REQ["content"])]
    assert row["route"] == "openai-wif" and row["answer"] == "ice hockey" and row["error"] == ""
    assert row["model"] == "gpt-6-astra-2026-10-01" and row["reasoning_tokens"] == 0
    assert {k: row[k] for k in ("family", "id", "draw", "prompt_sha", "answerer")} == {
        k: REQ[k] for k in ("family", "id", "draw", "prompt_sha", "answerer")
    }
    assert "t1" not in json.dumps(row)  # the access token never reaches a row


def test_openrouter_answer_is_unchanged_but_for_the_route_field():
    clients, calls, made = _clients("openrouter", [_completion("x", "openai/gpt-6-astra")])
    row = _answer(clients)
    assert made == [("or-key", "https://openrouter.ai/api/v1", {})]
    assert calls[0]["max_tokens"] == 16000 and row["route"] == "openrouter"


def test_wif_401_re_exchanges_the_token_then_succeeds():
    clients, _, made = _clients(
        "openai-wif", [_status_error(401), _completion("y")], tokens=["t1", "t2"]
    )
    row = _answer(clients)
    assert row["answer"] == "y" and [m[0] for m in made] == ["t1", "t2"]


def test_wif_persistent_401_aborts():
    outcomes = [_status_error(401)] * (ar.AUTH_REFRESHES + 1)
    clients, _, _ = _clients("openai-wif", outcomes, tokens=[f"t{i}" for i in range(9)])
    with pytest.raises(ar.AbortError):
        _answer(clients)


def test_refusal_is_final_and_empty_text_is_retried():
    filtered = _completion("")
    filtered.choices[0].finish_reason = "content_filter"
    clients, _, _ = _clients("openai-wif", [filtered])
    row = _answer(clients)
    assert row["refused"] is True and row["route"] == "openai-wif"
    clients, calls, _ = _clients("openai-wif", [_completion(""), _completion("z")])
    assert _answer(clients)["answer"] == "z" and len(calls) == 2


# ---------------------------------------------------------------- routes in the gate


def test_answer_route_infers_legacy_openrouter_rows():
    assert ti.answer_route({"route": "openai-wif", "model": "gpt-6-astra"}) == "openai-wif"
    assert ti.answer_route({"model": "openai/gpt-6-astra"}) == "openrouter"
    assert ti.answer_route({}) == "unknown"


def test_reader_routes_counts_usable_current_answers(tmp_path: Path):
    out = tmp_path / "o"
    out.mkdir()
    prompt = {"family": "fam", "prefix": "p", "variant": ti.DEFAULT_VARIANT}
    (out / "prompts.jsonl").write_text(
        "".join(json.dumps(prompt | {"id": i}) + "\n" for i in "abc")
    )
    sha = ti.prompt_sha(ti.panel_prompt(prompt | {"id": "a"}))
    base = {"family": "fam", "answer": "t", "error": "", "prompt_sha": sha}
    rows = [
        base | {"id": "a", "draw": 0, "model": "openai/gpt-6-astra"},  # legacy OpenRouter row
        base | {"id": "b", "draw": 0, "route": "openai-wif"},
        base | {"id": "c", "draw": 0, "route": "openai-wif", "prompt_sha": "stale"},
        base | {"id": "a", "draw": 1, "route": "openai-wif"},
        base | {"id": "b", "draw": 1, "route": "openai-wif", "answer": "", "error": "boom"},
    ]
    for d in (0, 1):
        af = ti.answers_file(out, "astra", d)
        af.parent.mkdir(parents=True, exist_ok=True)
        af.write_text("".join(json.dumps(r) + "\n" for r in rows if r["draw"] == d))
    got = ti.reader_routes([out], "astra", "fam", ["a", "b", "c"], 2)
    assert got == {"openai-wif": 2, "openrouter": 1}


# ---------------------------------------------------------------- gemini-wif (argon)

GENV = {"MODAL_IDENTITY_TOKEN": "jwt-identity"}
GREQ = REQ | {"answerer": "argon"}


def test_gemini_route_sends_the_openrouter_question_and_ceiling():
    """Same single user turn and 16000-token ceiling as the OpenRouter argon call; only the
    model prefix and the ceiling's name differ. No thinking / sampling / safety overrides."""
    model = ti.PANEL["argon"]
    o = ar.completion_kwargs("openrouter", model, GREQ["content"])
    g = ar.completion_kwargs("gemini-wif", model, GREQ["content"])
    assert o == {
        "model": "google/gemini-4-argon",
        "max_tokens": 16000,
        "messages": [{"role": "user", "content": GREQ["content"]}],
    }
    assert g == {
        "model": "gemini-4-argon",
        "contents": [{"role": "user", "parts": [{"text": GREQ["content"]}]}],
        "config": {"max_output_tokens": 16000},
    }
    assert set(g["config"]) == {"max_output_tokens"}
    with pytest.raises(ValueError, match="Gemini models only"):
        ar.route_model(ti.PANEL["astra"], "gemini-wif")
    assert {"openai-wif": {"astra"}, "gemini-wif": {"argon"}} == ar.ROUTE_ANSWERERS


def test_gemini_credentials_follow_the_recipe(monkeypatch: pytest.MonkeyPatch):
    """identity_pool.Credentials with the Modal identity token as the subject token; the genai
    client is Vertex, project camila-blank, location global."""
    import sys

    made: dict[str, Any] = {}

    class Supplier:
        pass

    def credentials(**kw: Any) -> Any:
        made["creds"] = kw
        return "CREDS"

    identity_pool = SimpleNamespace(SubjectTokenSupplier=Supplier, Credentials=credentials)
    genai = SimpleNamespace(Client=lambda **kw: made.setdefault("client", kw) and "CLIENT")
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=genai))
    monkeypatch.setitem(sys.modules, "google.auth", SimpleNamespace(identity_pool=identity_pool))
    monkeypatch.setitem(sys.modules, "google.auth.identity_pool", identity_pool)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    assert ar.gemini_client(GENV) == "CLIENT"
    kw = made["creds"]
    supplier = kw.pop("subject_token_supplier")
    assert supplier.get_subject_token(None, None) == "jwt-identity"
    assert kw == {
        "audience": "//iam.googleapis.com/projects/514946254119/locations/global/"
        "workloadIdentityPools/modal/providers/modal-oidc",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "token_url": "https://sts.googleapis.com/v1/token",
        "scopes": ["https://www.googleapis.com/auth/cloud-platform"],
    }
    assert made["client"] == {
        "vertexai": True,
        "project": "camila-blank",
        "location": "global",
        "credentials": "CREDS",
    }


class _GenaiError(Exception):
    def __init__(self, code: int, details: Any = None):
        super().__init__(f"{code}")
        self.code, self.details = code, details or {"error": {"code": code}}


class _AuthError(Exception):
    pass


def _gresp(
    text: str = "",
    finish: str = "STOP",
    thought: str = "",
    block: str | None = None,
    model: str = "gemini-4-argon-001",
) -> Any:
    parts = []
    if thought:
        parts.append(SimpleNamespace(text=thought, thought=True))
    if text:
        parts.append(SimpleNamespace(text=text, thought=None))
    cands = (
        []
        if block
        else [
            SimpleNamespace(
                content=SimpleNamespace(parts=parts), finish_reason=SimpleNamespace(name=finish)
            )
        ]
    )
    usage = SimpleNamespace(
        prompt_token_count=120, candidates_token_count=20, thoughts_token_count=300
    )
    feedback = SimpleNamespace(block_reason=SimpleNamespace(name=block)) if block else None
    return SimpleNamespace(
        candidates=cands, prompt_feedback=feedback, usage_metadata=usage, model_version=model
    )


class _Gemini:
    """A fake google.genai.Client: ``client.aio.models.generate_content``."""

    def __init__(self, log: list, outcomes: list):
        self.log, self.outcomes = log, outcomes
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._gen))

    async def _gen(self, **kw: Any) -> Any:
        self.log.append(kw)
        o = self.outcomes.pop(0)
        if isinstance(o, BaseException):
            raise o
        return o


def _gemini(outcomes: list, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ar, "gemini_error_types", lambda: ((_GenaiError,), (_AuthError,)))
    calls: list[dict] = []
    envs: list[dict] = []

    def factory(env: dict) -> _Gemini:
        envs.append(env)
        return _Gemini(calls, outcomes)

    return ar.Clients("gemini-wif", env=GENV, gemini_factory=factory), calls, envs


def _ganswer(clients: ar.Clients) -> dict:
    return asyncio.run(
        ar.answer_one(clients, asyncio.Semaphore(1), ti.PANEL["argon"], GREQ, sleep=_nosleep)
    )


def test_gemini_answer_records_the_route_and_drops_thoughts(monkeypatch: pytest.MonkeyPatch):
    clients, calls, envs = _gemini(
        [_gresp("Wayne Gretzky's sport, ice hockey.", thought="hmm")], monkeypatch
    )
    row = _ganswer(clients)
    assert calls == [ar.completion_kwargs("gemini-wif", ti.PANEL["argon"], GREQ["content"])]
    assert len(envs) == 1
    assert row["route"] == "gemini-wif" and row["error"] == ""
    assert row["answer"] == "Wayne Gretzky's sport, ice hockey."  # the thought part is not text
    assert row["stop_reason"] == "stop" and row["model"] == "gemini-4-argon-001"
    assert (row["in_tokens"], row["out_tokens"], row["reasoning_tokens"]) == (120, 320, 300)
    assert {k: row[k] for k in ("family", "id", "draw", "prompt_sha", "answerer")} == {
        k: GREQ[k] for k in ("family", "id", "draw", "prompt_sha", "answerer")
    }
    assert "jwt-identity" not in json.dumps(row)


def test_gemini_client_is_built_once(monkeypatch: pytest.MonkeyPatch):
    clients, calls, envs = _gemini([_gresp("a"), _gresp("b")], monkeypatch)
    assert _ganswer(clients)["answer"] == "a" and _ganswer(clients)["answer"] == "b"
    assert len(envs) == 1 and len(calls) == 2


def test_gemini_429_waits_then_answers_and_5xx_retries(monkeypatch: pytest.MonkeyPatch):
    clients, calls, _ = _gemini(
        [_GenaiError(429), _GenaiError(429), _GenaiError(503), _gresp("ok")], monkeypatch
    )
    assert _ganswer(clients)["answer"] == "ok" and len(calls) == 4


def test_gemini_403_and_credential_failure_abort(monkeypatch: pytest.MonkeyPatch):
    clients, _, _ = _gemini([_GenaiError(403)], monkeypatch)
    with pytest.raises(ar.AbortError, match="403"):
        _ganswer(clients)
    clients, _, _ = _gemini([_AuthError("sts said no: jwt-identity")], monkeypatch)
    with pytest.raises(ar.AbortError) as exc:
        _ganswer(clients)
    assert "jwt-identity" not in str(exc.value)  # the subject token is never echoed
    assert ar.classify_error(401, {}, "gemini-wif") == "abort"


def test_gemini_refusals_are_final_and_empty_text_is_retried(monkeypatch: pytest.MonkeyPatch):
    clients, calls, _ = _gemini([_gresp(finish="SAFETY")], monkeypatch)
    row = _ganswer(clients)
    assert row["refused"] is True and row["why"] == "SAFETY" and len(calls) == 1
    clients, _, _ = _gemini([_gresp(block="PROHIBITED_CONTENT")], monkeypatch)
    assert _ganswer(clients)["why"] == "prompt blocked: PROHIBITED_CONTENT"
    clients, calls, _ = _gemini(
        [_gresp(finish="MAX_TOKENS", thought="long"), _gresp("z")], monkeypatch
    )
    assert _ganswer(clients)["answer"] == "z" and len(calls) == 2


def test_gemini_route_needs_the_modal_identity_token():
    with pytest.raises(ar.AbortError, match="MODAL_IDENTITY_TOKEN"):
        ar.Clients("gemini-wif", env={})


def test_reader_routes_counts_gemini_rows(tmp_path: Path):
    out = tmp_path / "o"
    out.mkdir()
    prompt = {"family": "fam", "prefix": "p", "variant": ti.DEFAULT_VARIANT}
    (out / "prompts.jsonl").write_text(json.dumps(prompt | {"id": "a"}) + "\n")
    sha = ti.prompt_sha(ti.panel_prompt(prompt | {"id": "a"}))
    row = {"family": "fam", "id": "a", "draw": 0, "answer": "t", "error": "", "prompt_sha": sha}
    af = ti.answers_file(out, "argon", 0)
    af.parent.mkdir(parents=True)
    af.write_text(json.dumps(row | {"route": "gemini-wif"}) + "\n")
    assert ti.reader_routes([out], "argon", "fam", ["a"], 1) == {"gemini-wif": 1}
    assert ti.answer_route({"route": "gemini-wif", "model": "gemini-4-argon"}) == "gemini-wif"

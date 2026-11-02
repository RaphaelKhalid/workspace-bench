"""One ATI panel answer from a hosted frontier reader, by route (plan 0019; decisions R1-ATI rev
and R1-ATI gemini).

Runs inside the Modal containers of ``scripts/ati_openrouter_modal.py`` (stdlib + ``openai`` +
``google-genai`` only, so the image needs no other project dependency) and is unit-tested
offline.

Three routes reach the same reader with the same request:

* ``openrouter``: ``https://openrouter.ai/api/v1`` with the ``openrouter`` Modal secret, the
  model by its OpenRouter id (``openai/gpt-6-astra``, ``google/gemini-4-argon``), ``max_tokens``.
* ``openai-wif``: OpenAI directly, authenticated by workload identity federation: the container's
  ``MODAL_IDENTITY_TOKEN`` is exchanged (RFC 8693) at ``auth.openai.com`` for a short-lived
  access token using the ``openai-wif`` Modal secret's ids; the model by its OpenAI id
  (``gpt-6-astra``), ``max_completion_tokens`` (what OpenRouter sends an OpenAI reasoning model
  for ``max_tokens``). OpenAI readers only.
* ``gemini-wif``: Gemini on Vertex AI (project ``camila-blank``, location ``global``),
  authenticated by Google workload identity federation: ``google.auth.identity_pool``
  credentials whose subject token is the container's ``MODAL_IDENTITY_TOKEN``, exchanged at
  Google STS (no secret; Modal workspace safety-sahan-2, environment ``camila-blank`` only); the
  model by its Vertex id (``gemini-4-argon``), ``max_output_tokens`` (what OpenRouter sends
  Gemini for ``max_tokens``; thinking shares it). Gemini readers only.

All send the same single user message with no system prompt, no temperature and no reasoning /
thinking setting (the provider defaults), and the same token ceiling. Every row records its
``route``. Access tokens live only in memory: they are never logged, written or returned.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

ROUTES = ("openrouter", "openai-wif", "gemini-wif")
WIF_ANSWERERS = frozenset({"astra"})  # the OpenAI readers of the panel
GEMINI_ANSWERERS = frozenset({"argon"})  # the Gemini readers of the panel
# route -> the panel answerers it serves (openrouter: all hosted readers)
ROUTE_ANSWERERS = {"openai-wif": WIF_ANSWERERS, "gemini-wif": GEMINI_ANSWERERS}
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"
MAX_TOKENS = 16000
ATTEMPTS = 8  # errors that count; 429s wait without spending one
RATE_LIMIT_WAITS = 200
AUTH_REFRESHES = 3  # 401s on the WIF route: re-exchange the token, then abort
TOKEN_MARGIN_S = 300  # re-exchange this long before the access token expires
# provider finish reasons that are a policy block, recorded once as a refusal (never re-asked)
SAFETY_FINISH = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"})
WIF_ENV = ("OPENAI_IDENTITY_PROVIDER_ID_MODAL", "OPENAI_SERVICE_ACCOUNT_ID", "OPENAI_PROJECT_ID")
# Gemini via Google workload identity federation (identifiers, not secrets; 1P "Gemini WIF IDs")
GEMINI_PROJECT = "camila-blank"
GEMINI_LOCATION = "global"
GEMINI_AUDIENCE = (
    "//iam.googleapis.com/projects/514946254119/locations/global/"
    "workloadIdentityPools/modal/providers/modal-oidc"
)
GEMINI_TOKEN_URL = "https://sts.googleapis.com/v1/token"
GEMINI_SUBJECT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"
GEMINI_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
# Gemini finish reasons as the OpenAI-shaped ``stop_reason`` OpenRouter recorded for them
GEMINI_FINISH = {"STOP": "stop", "MAX_TOKENS": "length"}


class AbortError(Exception):
    """A key / credit / spend-limit error: stop the shard, never record it as a refusal."""


class TransientExchangeError(Exception):
    """A 429 / 5xx from the token endpoint: retried like a network error."""


def classify_error(status: int | None, body: Any, route: str = "openrouter") -> str:
    """``refusal`` (final), ``abort`` (stop the run), ``auth`` (WIF: re-exchange the token),
    ``rate`` (wait, no attempt spent) or ``retry``. A 403 is a refusal only when OpenRouter says
    it was moderation-flagged."""
    meta = body.get("error", {}).get("metadata", {}) if isinstance(body, dict) else {}
    if status == 403 and isinstance(meta, dict) and ("reasons" in meta or "flagged_input" in meta):
        return "refusal"
    if status == 401 and route == "openai-wif":
        return "auth"  # the short-lived access token may have expired mid-run
    # gemini-wif: google-auth refreshes its own token, so a 401 / 403 (wrong Modal environment
    # or project) is final, like OpenRouter's key errors
    if status in (401, 402, 403):
        return "abort"
    if status == 429:
        return "rate"
    return "retry"


def route_model(model: str, route: str) -> str:
    """The model id the route's API expects for a panel model id (``PANEL`` holds OpenRouter
    ids)."""
    if route == "openrouter":
        return model
    if route == "openai-wif":
        if not model.startswith("openai/"):
            raise ValueError(f"route openai-wif reaches OpenAI models only, not {model!r}")
        return model.removeprefix("openai/")
    if route == "gemini-wif":
        if not model.startswith("google/"):
            raise ValueError(f"route gemini-wif reaches Gemini models only, not {model!r}")
        return model.removeprefix("google/")
    raise ValueError(f"route must be one of {ROUTES}, not {route!r}")


def completion_kwargs(route: str, model: str, content: str) -> dict[str, Any]:
    """The request arguments for one panel question; identical across routes except for the
    token-ceiling parameter's name (OpenRouter maps ``max_tokens`` to OpenAI's
    ``max_completion_tokens`` and to Gemini's ``max_output_tokens``). On ``gemini-wif`` these are
    ``generate_content``'s arguments: the one user turn as ``contents`` and the ceiling in
    ``config``; no thinking / temperature / safety settings (the provider defaults)."""
    if route == "gemini-wif":
        return {
            "model": route_model(model, route),
            "contents": [{"role": "user", "parts": [{"text": content}]}],
            "config": {"max_output_tokens": MAX_TOKENS},
        }
    cap = "max_completion_tokens" if route == "openai-wif" else "max_tokens"
    return {
        "model": route_model(model, route),
        cap: MAX_TOKENS,
        "messages": [{"role": "user", "content": content}],
    }


class WifToken:
    """The OpenAI access token for this container, exchanged from ``MODAL_IDENTITY_TOKEN`` and
    re-exchanged before expiry or after a 401. ``post`` is an async ``(url, json) -> (status,
    body)``; the default is a stdlib POST."""

    def __init__(
        self,
        env: dict[str, str] | None = None,
        post: Callable[[str, dict[str, Any]], Awaitable[tuple[int, Any]]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._env = dict(os.environ) if env is None else env
        missing = [k for k in ("MODAL_IDENTITY_TOKEN", *WIF_ENV) if not self._env.get(k)]
        if missing:
            raise AbortError(f"openai-wif: missing {missing} (the openai-wif secret / Modal)")
        self._post = post or _post_json
        self._clock = clock
        self._token: str | None = None
        self._expires = 0.0
        self._lock = asyncio.Lock()
        self.exchanges = 0

    @property
    def project(self) -> str:
        return self._env["OPENAI_PROJECT_ID"]

    def invalidate(self, token: str | None = None) -> None:
        """Drop the cached token (only if it is still ``token``, when given: a late 401 on an
        older token must not discard one another request just obtained)."""
        if token is None or token == self._token:
            self._token = None

    async def get(self) -> str:
        async with self._lock:
            if self._token is None or self._clock() >= self._expires:
                status, body = await self._post(
                    OPENAI_TOKEN_URL,
                    {
                        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                        "subject_token": self._env["MODAL_IDENTITY_TOKEN"],
                        "identity_provider_id": self._env["OPENAI_IDENTITY_PROVIDER_ID_MODAL"],
                        "service_account_id": self._env["OPENAI_SERVICE_ACCOUNT_ID"],
                    },
                )
                if status != 200 or not isinstance(body, dict) or not body.get("access_token"):
                    # the body of a failed exchange carries no token; keep only its error field
                    err = body.get("error") if isinstance(body, dict) else None
                    msg = f"openai-wif token exchange failed: {status} {err!r}"[:300]
                    if status == 429 or status >= 500:
                        raise TransientExchangeError(msg)  # retried by ``answer_one``
                    raise AbortError(msg)
                self._token = str(body["access_token"])
                life = float(body.get("expires_in") or 3600)
                self._expires = self._clock() + max(60.0, life - TOKEN_MARGIN_S)
                self.exchanges += 1
            return self._token


async def _post_json(url: str, payload: dict[str, Any]) -> tuple[int, Any]:
    """POST ``payload`` as JSON (stdlib, in a thread); (status, parsed body or {})."""
    import json
    import urllib.error
    import urllib.request

    def go() -> tuple[int, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, {}

    return await asyncio.to_thread(go)


class Clients:
    """The API client of a route. OpenRouter: one ``AsyncOpenAI``; ``openai-wif``: one
    ``AsyncOpenAI`` per access token (rebuilt when the token is re-exchanged); ``gemini-wif``:
    one ``google.genai.Client`` per container (its WIF credentials refresh themselves).
    ``factory`` builds an OpenAI client from ``(api_key, base_url, headers)`` and
    ``gemini_factory`` a Gemini client from the environment (tests pass fakes)."""

    def __init__(
        self,
        route: str,
        env: dict[str, str] | None = None,
        factory: Callable[[str, str | None, dict[str, str]], Any] | None = None,
        token: WifToken | None = None,
        gemini_factory: Callable[[dict[str, str]], Any] | None = None,
    ) -> None:
        if route not in ROUTES:
            raise ValueError(f"route must be one of {ROUTES}, not {route!r}")
        self.route = route
        self._env = dict(os.environ) if env is None else env
        self._factory = factory or _openai_client
        self._gemini_factory = gemini_factory or gemini_client
        if route == "gemini-wif" and not self._env.get("MODAL_IDENTITY_TOKEN"):
            raise AbortError(
                "gemini-wif: MODAL_IDENTITY_TOKEN missing (only inside a Modal function of "
                "environment camila-blank)"
            )
        self.token = (
            token if token is not None else (WifToken(self._env) if route == "openai-wif" else None)
        )
        self._client: Any = None
        self._key: str | None = None
        self._keys: dict[int, str] = {}  # id(client) -> the access token it was built with

    async def get(self) -> Any:
        if self.route == "gemini-wif":
            if self._client is None:
                self._client = self._gemini_factory(self._env)
            return self._client
        if self.token is None:
            if self._client is None:
                key = self._env.get("OPENROUTER_API_KEY")
                if not key:
                    raise AbortError("openrouter: OPENROUTER_API_KEY missing (openrouter secret)")
                self._client = self._factory(key, OPENROUTER_BASE, {})
            return self._client
        tok = await self.token.get()
        if tok != self._key:
            self._client = self._factory(tok, None, {"OpenAI-Project": self.token.project})
            self._key = tok
            self._keys[id(self._client)] = tok
        return self._client

    def auth_failed(self, client: Any = None) -> None:
        """A 401 on ``client``: re-exchange, unless its token was already replaced."""
        if self.token is not None:
            self.token.invalidate(self._keys.get(id(client)) if client is not None else None)


def _openai_client(key: str, base_url: str | None, headers: dict[str, str]) -> Any:
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=key, base_url=base_url, default_headers=headers, max_retries=0, timeout=900
    )


def gemini_credentials(env: dict[str, str]) -> Any:
    """Google WIF credentials whose subject token is the container's Modal identity token
    (read from ``env`` on every exchange; google-auth re-exchanges before expiry)."""
    from google.auth import identity_pool

    class ModalToken(identity_pool.SubjectTokenSupplier):  # type: ignore[misc]
        def get_subject_token(self, context: Any, request: Any) -> str:
            return env["MODAL_IDENTITY_TOKEN"]

    return identity_pool.Credentials(
        audience=GEMINI_AUDIENCE,
        subject_token_type=GEMINI_SUBJECT_TOKEN_TYPE,
        token_url=GEMINI_TOKEN_URL,
        subject_token_supplier=ModalToken(),
        scopes=[GEMINI_SCOPE],
    )


def gemini_client(env: dict[str, str]) -> Any:
    from google import genai

    return genai.Client(
        vertexai=True,
        project=GEMINI_PROJECT,
        location=GEMINI_LOCATION,
        credentials=gemini_credentials(env),
    )


def gemini_error_types() -> tuple[tuple[type[BaseException], ...], tuple[type[BaseException], ...]]:
    """(API errors carrying an HTTP ``code``, credential errors) of google-genai / google-auth;
    empty where the packages are absent (the dev box; tests patch this)."""
    try:
        from google.auth import exceptions as gauth
        from google.genai import errors
    except ImportError:
        return (), ()
    return (errors.APIError,), (gauth.GoogleAuthError,)


def _http_status(exc: BaseException, route: str) -> tuple[int, Any] | None:
    """(status, error body) of an HTTP error from the route's SDK; ``None`` for anything else
    (network / timeout). Raises ``AbortError`` for a Google credential failure."""
    if route == "gemini-wif":
        api, auth = gemini_error_types()
        if auth and isinstance(exc, auth):
            # the STS response may describe the failure; it never carries the subject token
            raise AbortError(f"gemini-wif credentials failed: {type(exc).__name__}") from exc
        if api and isinstance(exc, api):
            body = getattr(exc, "details", None)
            return int(getattr(exc, "code", 0) or 0), body if isinstance(body, dict) else {}
        return None
    import openai

    if isinstance(exc, openai.APIStatusError):
        body: Any
        try:
            body = exc.response.json()
        except Exception:
            body = {}
        return exc.status_code, body
    return None


async def _create(client: Any, route: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """One call, normalized: {text, finish, refusal (why, or ""), in_tokens, out_tokens,
    reasoning_tokens, model}."""
    if route == "gemini-wif":
        r = await client.aio.models.generate_content(**kwargs)
        return _gemini_reply(r, kwargs["model"])
    r = await client.chat.completions.create(**kwargs)
    choice = r.choices[0] if r.choices else None
    finish = choice.finish_reason if choice else None
    native = str(getattr(choice, "native_finish_reason", "") or "").upper()
    refusal = (getattr(choice.message, "refusal", None) if choice else None) or ""
    why = ""
    if finish == "content_filter" or refusal or native in SAFETY_FINISH:
        why = refusal[:200] or native or str(finish)
    usage = r.usage
    details = getattr(usage, "completion_tokens_details", None)
    return {
        "text": ((choice.message.content if choice else "") or "").strip(),
        "finish": finish,
        "refusal": why,
        "in_tokens": getattr(usage, "prompt_tokens", None),
        "out_tokens": getattr(usage, "completion_tokens", None),
        "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        "model": r.model,
    }


def _enum_name(v: Any) -> str:
    return str(getattr(v, "name", v) or "").upper()


def _gemini_reply(r: Any, model: str) -> dict[str, Any]:
    """A ``GenerateContentResponse`` as ``_create``'s dict. The answer is the candidate's
    non-thought text parts; a blocked prompt or a safety finish is a refusal; ``out_tokens``
    counts thinking too, as OpenRouter's ``completion_tokens`` does."""
    feedback = getattr(r, "prompt_feedback", None)
    blocked = _enum_name(getattr(feedback, "block_reason", None)) if feedback else ""
    cands = getattr(r, "candidates", None) or []
    cand = cands[0] if cands else None
    native = _enum_name(getattr(cand, "finish_reason", None)) if cand else ""
    parts = (getattr(getattr(cand, "content", None), "parts", None) or []) if cand else []
    text = "".join(
        p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False)
    ).strip()
    why = ""
    if blocked and blocked != "BLOCKED_REASON_UNSPECIFIED":
        why = f"prompt blocked: {blocked}"
    elif native in SAFETY_FINISH:
        why = native
    um = getattr(r, "usage_metadata", None)
    out = getattr(um, "candidates_token_count", None)
    thoughts = getattr(um, "thoughts_token_count", None)
    return {
        "text": text,
        "finish": GEMINI_FINISH.get(native, native.lower() or None),
        "refusal": why,
        "in_tokens": getattr(um, "prompt_token_count", None),
        "out_tokens": None if out is None and thoughts is None else (out or 0) + (thoughts or 0),
        "reasoning_tokens": thoughts if thoughts is not None else (0 if um else None),
        "model": getattr(r, "model_version", None) or model,
    }


async def answer_one(
    clients: Clients,
    sem: asyncio.Semaphore,
    model: str,
    req: dict[str, Any],
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> dict[str, Any]:
    """One panel answer row for ``req`` ({family, id, draw, prompt_sha, answerer, content}):
    an answer, a final refusal, or the last error after ``ATTEMPTS``. Raises ``AbortError`` on
    a key / credit / auth failure."""
    route = clients.route
    base = {k: req[k] for k in ("family", "id", "draw", "prompt_sha")}
    base |= {"answerer": req["answerer"], "route": route}
    kwargs = completion_kwargs(route, model, req["content"])
    err, waits, attempt, auths = "", 0, 0, 0
    async with sem:
        while attempt < ATTEMPTS:
            client = None
            try:
                client = await clients.get()
                reply = await _create(client, route, kwargs)
            except AbortError:
                raise
            except Exception as exc:
                http = _http_status(exc, route)
                if http is None:  # network / timeout / transient exchange: retried
                    err = f"{type(exc).__name__}: {exc}"[:300]
                    attempt += 1
                    await sleep(min(60, 2 * 2**attempt))
                    continue
                status, body = http
                kind = classify_error(status, body, route)
                err = f"{status}: {str(body)[:300]}"
                if kind == "refusal":
                    return base | {"answer": "", "refused": True, "error": "refusal"}
                if kind == "auth" and auths < AUTH_REFRESHES:
                    auths += 1
                    clients.auth_failed(client)
                    continue
                if kind in ("abort", "auth"):
                    raise AbortError(err) from exc
                if kind == "rate" and waits < RATE_LIMIT_WAITS:
                    waits += 1
                    await sleep(30 + 30 * random.random())
                    continue
                attempt += 1
                await sleep(min(60, 2 * 2**attempt))
                continue
            auths = 0
            if reply["refusal"]:
                return base | {
                    "answer": "",
                    "refused": True,
                    "error": "refusal",
                    "why": reply["refusal"],
                }
            if not reply["text"]:  # e.g. finish_reason=length: reasoning ate the budget; retryable
                err = f"no text (finish_reason={reply['finish']})"
                attempt += 1
                continue
            return base | {
                "answer": reply["text"],
                "stop_reason": reply["finish"],
                "in_tokens": reply["in_tokens"],
                "out_tokens": reply["out_tokens"],
                "reasoning_tokens": reply["reasoning_tokens"],
                "model": reply["model"],
                "error": "",
            }
    return base | {"answer": "", "error": err}

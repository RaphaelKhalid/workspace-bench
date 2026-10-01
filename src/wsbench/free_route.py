"""Opt-in, fail-closed OpenRouter routing with live zero-price and quota checks."""

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from wsbench.errors import JudgeConfigError

DEFAULT_MODEL = "qwen/qwen3.8-27b:free"
DEFAULT_PROVIDER = "modelrun/fp4"
API = "https://openrouter.ai/api/v1"


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _get(path: str) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or-"):
        raise JudgeConfigError("OpenRouter key missing for free-route verification")
    request = urllib.request.Request(
        API + path,
        headers={"Authorization": "Bearer " + key, "User-Agent": "workspacebench-free-only/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)["data"]
    except (OSError, ValueError, KeyError) as e:
        # Do not include request headers or arbitrary server response bodies in an error.
        raise JudgeConfigError(f"free-route metadata check failed: {type(e).__name__}") from e


class FreeRoute:
    def __init__(self, model: str, provider: str, max_requests: int, ledger: Path):
        if not model.endswith(":free") or not provider or max_requests < 1:
            raise JudgeConfigError(
                "free policy requires a :free model, provider and positive call cap"
            )
        self.model = model
        self.provider = provider
        self.max_requests = max_requests
        self.ledger = ledger
        self._lock = threading.Lock()
        self._verified_at = 0.0
        self._remaining = 0
        self._attempts = 0
        self._endpoint: dict = {}
        self._inflight: set[str] = set()
        self._stopped: str | None = None

    @property
    def config(self) -> dict:
        # Operational call caps and timestamps do not alter the scientific instrument.
        return {
            "protocol": "free-openrouter-v1",
            "model": self.model,
            "provider": {
                "only": [self.provider],
                "order": [self.provider],
                "allow_fallbacks": False,
                "require_parameters": True,
                "max_price": {"prompt": 0, "completion": 0, "request": 0, "image": 0},
            },
            "text_thinking": {"on": {"effort": "minimal"}, "off": {"enabled": False}},
        }

    def require_model(self, model: str) -> None:
        if model != self.model:
            raise JudgeConfigError(
                f"free-only policy rejects model {model!r}; expected {self.model!r}"
            )

    def _append(self, event: dict) -> None:
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"time": time.time(), **event}, sort_keys=True) + "\n")

    def _verify(self) -> None:
        data = _get("/models/" + self.model + "/endpoints")
        matches = [e for e in data.get("endpoints", []) if e.get("tag") == self.provider]
        if len(matches) != 1:
            raise JudgeConfigError("the exact free provider endpoint is unavailable or ambiguous")
        endpoint = matches[0]
        pricing = endpoint.get("pricing", {})
        try:
            free = all(Decimal(str(pricing[k])) == 0 for k in ("prompt", "completion"))
            free = free and all(Decimal(str(v)) == 0 for k, v in pricing.items() if k != "discount")
        except (InvalidOperation, KeyError, TypeError):
            free = False
        if not free:
            raise JudgeConfigError("free endpoint pricing is missing, invalid or nonzero")
        quota = _get("/key").get("free_model_daily_requests", {})
        remaining = quota.get("remaining")
        if type(remaining) is not int or remaining < 1:
            raise JudgeConfigError("free request quota is unavailable or exhausted")
        self._endpoint = endpoint
        self._remaining = max(0, remaining - len(self._inflight))
        self._verified_at = time.monotonic()
        self._append(
            {
                "event": "verified",
                "config": self.config,
                "endpoint": {
                    k: endpoint.get(k)
                    for k in (
                        "name",
                        "tag",
                        "model_id",
                        "provider_name",
                        "quantization",
                        "pricing",
                        "supported_parameters",
                        "context_length",
                        "max_completion_tokens",
                    )
                },
                "free_quota": quota,
            }
        )

    def reserve(self, model: str, *, structured: bool, request: dict) -> str:
        self.require_model(model)
        with self._lock:
            if self._stopped:
                raise JudgeConfigError(self._stopped)
            if self._attempts >= self.max_requests:
                raise JudgeConfigError("free-only invocation request cap reached; resume later")
            # Refresh before a long run continues; pending reservations are bounded by the
            # process call cap. A 429 still stops this invocation if another job used quota.
            if not self._endpoint or time.monotonic() - self._verified_at > 300:
                self._verify()
            if self._remaining < 1:
                raise JudgeConfigError("free request quota exhausted; no paid fallback")
            supported = self._endpoint.get("supported_parameters", [])
            if structured and not any(
                k in supported for k in ("structured_outputs", "response_format")
            ):
                raise JudgeConfigError("fixed free endpoint does not advertise structured output")
            self._remaining -= 1
            self._attempts += 1
            token = uuid.uuid4().hex
            self._inflight.add(token)
            self._append(
                {
                    "event": "reserved",
                    "request_id": token,
                    "request_sha256": _hash(request),
                    "model": model,
                    "provider": self.provider,
                    "attempt": self._attempts,
                }
            )
            return token

    def failed(self, token: str, error: Exception) -> None:
        with self._lock:
            self._inflight.discard(token)
            status = getattr(error, "status_code", None)
            self._append(
                {
                    "event": "failed",
                    "request_id": token,
                    "error_type": type(error).__name__,
                    "status": status,
                }
            )
            if status == 429:
                self._stopped = "free endpoint rate/quota limit reached; stop and resume later"
                raise JudgeConfigError(self._stopped) from error

    def response(self, token: str, response: object, cost: object) -> None:
        extra = getattr(response, "model_extra", None) or {}
        provider = getattr(response, "provider", None) or extra.get("provider")
        with self._lock:
            self._inflight.discard(token)
            self._append(
                {
                    "event": "response",
                    "request_id": token,
                    "response_id": getattr(response, "id", None),
                    "model": getattr(response, "model", None),
                    "provider": provider,
                    "cost_usd": cost,
                }
            )
            try:
                zero = cost is not None and Decimal(str(cost)) == 0
            except InvalidOperation:
                zero = False
            if (
                not zero
                or provider != self._endpoint.get("provider_name")
                or getattr(response, "model", None) != self.model
            ):
                self._stopped = "free response cost/provider not verified; stopped without scoring"
                raise JudgeConfigError(self._stopped)


@lru_cache(maxsize=8)
def _instance(model: str, provider: str, max_requests: int, ledger: str) -> FreeRoute:
    return FreeRoute(model, provider, max_requests, Path(ledger))


def active() -> FreeRoute | None:
    flag = os.environ.get("WSBENCH_FREE_ONLY", "0")
    if flag == "0":
        return None
    if flag != "1":
        raise JudgeConfigError("WSBENCH_FREE_ONLY must be 0 or 1")
    try:
        cap = int(os.environ.get("WSBENCH_FREE_MAX_REQUESTS", "100"))
    except ValueError as e:
        raise JudgeConfigError("WSBENCH_FREE_MAX_REQUESTS must be an integer") from e
    return _instance(
        os.environ.get("WSBENCH_FREE_MODEL", DEFAULT_MODEL),
        os.environ.get("WSBENCH_FREE_PROVIDER", DEFAULT_PROVIDER),
        cap,
        os.environ.get("WSBENCH_FREE_LEDGER", "outputs/free-route/requests.jsonl"),
    )


def cache_context() -> dict | None:
    policy = active()
    return policy.config if policy else None

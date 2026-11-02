"""The Anthropic client for the adapt grader and author. Default: the keyless OAuth token the
fellows judges use, read (never written) from the Modal Dict ``anthropic-oauth`` (environment
``MODAL_ENVIRONMENT``, default ``agam``), sent as bearer auth with the OAuth beta flag. There is
no API-key fallback. The token is re-pushed every ~6 h, so a 401 first re-reads the Dict and
retries with a newer token (``Session``); only a 401 on the newest token stops the run.
``WSB_ANTHROPIC_AUTH=sdk`` uses the SDK's own credentials instead (outside the fellows setup)."""

import os
import random
import time
from collections.abc import Callable
from typing import Any

DICT_NAME = "anthropic-oauth"
OAUTH_BETA = "oauth-2025-04-20"
PUSH = "the token is missing or expired: ask Agam to run `push-judge-token` on the Mac"


class TokenExpired(SystemExit):
    """A 401 from the API: stop the run (cached grades and gated rows are kept)."""


def read_token() -> tuple[str | None, float | None]:
    import modal

    env = os.environ.get("MODAL_ENVIRONMENT", "agam")
    entry = modal.Dict.from_name(DICT_NAME, environment_name=env).get("token")
    if not isinstance(entry, dict) or not entry.get("token"):
        return None, None
    return str(entry["token"]), float(entry.get("pushed_at", 0.0))


def _build(token: str) -> Any:
    import anthropic

    os.environ.pop("ANTHROPIC_API_KEY", None)  # the SDK would send both; the API rejects that
    return anthropic.Anthropic(
        auth_token=token, api_key=None, default_headers={"anthropic-beta": OAUTH_BETA}
    )


def client() -> Any:
    return Session().client


REFRESH_WAIT = 600.0  # seconds to wait for the next push after a 401
THROTTLE_TRIES = 12  # rate-limit / overload waits before a call gives up


class Session:
    """A client that survives the token's 6-hourly re-push: on a 401, ``refresh(seen)`` swaps in
    a newer token if the Dict has one (or another thread already did); False means none is newer."""

    def __init__(self) -> None:
        import threading

        import anthropic

        self.lock = threading.Lock()
        if os.environ.get("WSB_ANTHROPIC_AUTH") == "sdk":
            self.client, self.pushed = anthropic.Anthropic(), float("inf")
            return
        token, pushed = read_token()
        if not token:
            raise TokenExpired(PUSH)
        self.client, self.pushed = _build(token), pushed or 0.0
        age = (time.time() - self.pushed) / 60
        print(f"[adapt-auth] OAuth token from Modal Dict {DICT_NAME} (pushed {age:.0f} min ago)")

    def create(self, **kw: Any) -> Any:
        """``messages.create`` that waits out rate limits and overloads (see ``_throttled``)."""
        return self._throttled(lambda: self.client.messages.create(**kw))

    def stream_final(self, **kw: Any) -> Any:
        """A streamed ``messages`` call (long replies must stream); returns the final message."""

        def run() -> Any:
            with self.client.messages.stream(**kw) as stream:
                return stream.get_final_message()

        return self._throttled(run)

    @staticmethod
    def _throttled(fn: Callable[[], Any]) -> Any:
        """429 (the org's Opus output-token/min cap, hit when several adapt jobs author at once),
        5xx/529 and connection errors are waited out with jittered exponential backoff (20 s
        doubling, capped at 10 min, ~1 h in total) instead of failing the step or recording an
        undecided grade. Auth errors pass through to the caller's ``refresh``."""
        import anthropic

        transient = (anthropic.RateLimitError, anthropic.InternalServerError,
                     anthropic.APIConnectionError)  # fmt: skip
        for k in range(THROTTLE_TRIES):
            try:
                return fn()
            except transient as e:
                if k == THROTTLE_TRIES - 1:
                    raise
                wait = min(600.0, 20.0 * 2**k) * (0.5 + random.random())
                print(f"[adapt-auth] {type(e).__name__}: waiting {wait:.0f}s (try {k + 1})")
                time.sleep(wait)
        raise AssertionError("unreachable")

    def refresh(self, seen: float, wait: float | None = None) -> bool:
        """After a 401: switch to a newer pushed token. The Mac's refresh revokes the old token
        a little before the new one lands in the Dict, so poll for up to ``wait`` seconds instead
        of failing in that gap (two 2026-10-18 runs died that way)."""
        with self.lock:
            if self.pushed > seen:
                return True
            deadline = time.time() + (REFRESH_WAIT if wait is None else wait)
            while True:
                token, pushed = read_token()
                if token and (pushed or 0.0) > self.pushed:
                    break
                if time.time() >= deadline:
                    return False
                time.sleep(15)
            self.client, self.pushed = _build(token), pushed or 0.0
            print(f"[adapt-auth] 401: switched to the token pushed {time.ctime(self.pushed)}")
            return True


def is_auth_error(exc: Exception) -> bool:
    import anthropic

    return isinstance(exc, anthropic.AuthenticationError)

"""Re-score a family from an EXISTING judge cache with no API access: ``wsbench judge`` with
preflight disabled and every client call failing loudly, so a cached cell scores and an uncached
one is counted unjudged (never paid for). Used for plan 0012 report-only extras over old caches.

A dev script, not part of the package. Arguments are ``wsbench judge`` key=value pairs.
"""

import sys
from typing import Any

from wsbench import llm
from wsbench.cli import main


class _Refuse:
    """Stands in for both SDK clients: every request raises inside the call, so the client's own
    error handling counts the cell as failed (unjudged) instead of the run crashing."""

    def __init__(self) -> None:
        self.chat = self
        self.completions = self
        self.messages = self

    async def create(self, **kw: Any) -> Any:
        raise RuntimeError("cache_only_run: uncached call refused (no network)")  # not retried

    def stream(self, **kw: Any) -> Any:
        raise RuntimeError("cache_only_run: uncached call refused (no network)")

    async def close(self) -> None:
        return None


def _client(route: str, key: str) -> Any:
    return _Refuse()


if __name__ == "__main__":
    llm.preflight = lambda model, reasoning: None  # type: ignore[assignment]
    llm._make_client = _client  # type: ignore[assignment]
    llm.api_key = lambda *a, **k: "cache-only"  # type: ignore[assignment]
    argv = list(sys.argv[1:])
    # native unless the user chose a mode: the cache being re-scored is a native cache (plan 0024)
    if not any(x.startswith("opts=") and "aggregate=" in x for x in argv):
        opts = [x for x in argv if x.startswith("opts=")]
        if opts:
            argv[argv.index(opts[0])] = opts[0] + ",aggregate=native"
        else:
            argv.append("opts=aggregate=native")
    sys.exit(main(["judge", *argv]))

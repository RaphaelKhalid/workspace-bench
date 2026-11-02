"""Shared fakes for the summary-mode (plan 0020) family tests: one ``llm.stream_json`` stand-in
that answers digest calls extractively and routes judge calls to a per-test responder."""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from conftest import native_args

from wsbench import digest, llm
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.llm import Spend
from wsbench.registry import JudgeArgs

Responder = Callable[[str, str, dict], dict | None]


def first_lines_digest(user: str, k: int = 3) -> dict:
    """A passive fake digest: the first ``k`` bundle samples, each quoted whole as evidence."""
    lines = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
    return {
        "items": [
            {"statement": f"STATEMENT-{i}", "where": "", "evidence": ln}
            for i, ln in enumerate(lines[:k])
        ]
    }


class FakeLLM:
    """Install with ``FakeLLM.install(monkeypatch, judge=...)``. ``digest`` maps a user prompt to
    a digest result (default: :func:`first_lines_digest`); ``judge(system, user, schema)``
    answers every other call. ``calls`` records ``(schema_name, system, user)``."""

    def __init__(self, judge: Responder, digest: Callable[[str], dict | None] | None = None):
        self.judge = judge
        self.digest = digest or first_lines_digest
        self.calls: list[tuple[str, str, str]] = []

    def stream_json(self, prompts, *, schema, on_result, **_kw) -> Spend:
        name = schema.get("name", "")
        for i, (system, user) in enumerate(prompts):
            self.calls.append((name, system, user))
            on_result(
                i, self.digest(user) if name == "digest" else self.judge(system, user, schema)
            )
        return Spend()

    def n(self, name: str) -> int:
        return sum(1 for c in self.calls if c[0] == name)

    @classmethod
    def install(cls, monkeypatch, judge: Responder, digest=None) -> "FakeLLM":
        fake = cls(judge, digest)
        monkeypatch.setattr(llm, "stream_json", fake.stream_json)
        monkeypatch.setattr(llm, "preflight", lambda model, reasoning: None)
        return fake


def summary_args(readouts: Path, out: Path, prompt_version: str, **kw: Any) -> JudgeArgs:
    extra = {"aggregate": "summary", **kw.pop("extra", {})}
    return native_args(
        readouts=readouts,
        out=out,
        judge=resolve(JudgeConfig(prompt_version=prompt_version)),
        layers=kw.pop("layers", None),
        items=kw.pop("items", None),
        limit=0,
        allow_missing=kw.pop("allow_missing", False),
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        extra=extra,
        **kw,
    )


def digest_lines(user: str) -> list[str]:
    """The judged digest lines in a summary-mode judge prompt (``[support] sample``)."""
    return re.findall(rf"^\[(?:{digest.SUPPORT_PATTERN})\] .*$", user, flags=re.M)


def n_item_layers(path: Path, ids: list[str] | None = None) -> int:
    """How many per-layer digests a summary run makes for ``ids`` of a readouts file (audit F1:
    one digest per item and read layer): the distinct (item, layer) pairs with a non-blank
    sample or token."""
    import json

    pairs: set[tuple[str, int]] = set()
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        if ids is not None and r["id"] not in ids:
            continue
        if any(str(x).strip() for x in (r.get("samples") or r.get("tokens") or [])):
            pairs.add((r["id"], int(r["layer"])))
    return len(pairs)

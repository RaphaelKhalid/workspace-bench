"""Shared fixtures: isolate the family registry and the RPM pacer between tests."""

import pytest

from wsbench import llm, mcjudge, registry


@pytest.fixture(autouse=True)
def _isolate_registry():
    saved = dict(registry.FAMILIES)
    yield
    registry.FAMILIES.clear()
    registry.FAMILIES.update(saved)


@pytest.fixture(autouse=True)
def _reset_preflighted():
    mcjudge._PREFLIGHTED.clear()  # process-global "already preflighted" set (phase 6)
    yield
    mcjudge._PREFLIGHTED.clear()


@pytest.fixture(autouse=True)
def _reset_pacer():
    llm._PACER.reset()
    yield
    llm._PACER.reset()


@pytest.fixture(autouse=True)
def _offline_nocot(monkeypatch):
    """knowledge_cutoff's nocot rows render from nocot-bench's zip (a network fetch, plan 0018):
    every test gets synthetic question text instead, so plan / produce tests stay offline. The
    fetch and its checks are tested on a fixture zip in tests/test_knowledge_cutoff_nocot.py."""
    from wsbench import nocot

    monkeypatch.setattr(
        nocot,
        "questions",
        lambda: {it["id"]: f"synthetic question {it['id']}" for it in nocot.load_obscure()[1]},
    )


@pytest.fixture
def real_families():
    """Every real family registered, whatever an earlier test cleared: ``load_all`` imports each
    package once, so after a test empties the registry it re-adds none (``_isolate_registry``
    restores this test's snapshot afterwards)."""
    import importlib
    import pkgutil

    import wsbench.evals as evals_pkg

    for mod in pkgutil.iter_modules(evals_pkg.__path__):
        spec = importlib.import_module(f"wsbench.evals.{mod.name}").SPEC
        registry.FAMILIES.setdefault(spec.name, spec)
    return registry.FAMILIES


@pytest.fixture(autouse=True)
def _openrouter_shaped_fakes(monkeypatch):
    """The default judge is Claude Opus 5.5 (Anthropic route; plan 0023), but the family tests
    script OpenRouter-shaped fakes (``chat.completions.create``). When such a fake reaches the
    Anthropic structured-output path, answer through the OpenRouter path instead, so every family
    test keeps exercising its own logic; the real Anthropic path is tested in ``test_llm.py``
    with Anthropic-shaped fakes."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    real = llm._anthropic_once

    async def shim(client, system, user, *, schema, model, max_tokens, timeout, spend, **kw):
        if hasattr(client, "chat") and not hasattr(client, "messages"):
            return await llm._openrouter_once(
                client,
                system,
                user,
                schema=schema,
                model=model,
                reasoning=None,
                temperature=None,
                max_tokens=max_tokens,
                timeout=timeout,
                spend=spend,
            )
        return await real(
            client,
            system,
            user,
            schema=schema,
            model=model,
            max_tokens=max_tokens,
            timeout=timeout,
            spend=spend,
            **kw,
        )

    monkeypatch.setattr(llm, "_anthropic_once", shim)


collect_ignore = ["golden"]  # data files, never tests


class BadRequestError(Exception):
    status_code = 400  # neither transient nor fatal: one failed call, no retry


class FakeClient:
    """An OpenRouter-shaped fake: ``responder(system, user)`` returns the JSON object the model
    "wrote" (``None`` -> a non-transient error, i.e. one failed call, ``result is None``)."""

    def __init__(self, responder):
        from types import SimpleNamespace

        self.responder = responder
        self.calls: list[tuple[str, str]] = []
        self.kwargs: list[dict] = []  # every create() kwargs (model, temperature, ...)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw):
        import json
        from types import SimpleNamespace

        system, user = kw["messages"][0]["content"], kw["messages"][1]["content"]
        self.calls.append((system, user))
        self.kwargs.append(kw)
        r = self.responder(system, user)
        if r is None:
            raise BadRequestError("fake failure")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(r)))],
            usage=SimpleNamespace(cost=0.001),
        )

    async def close(self):
        return None


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a FakeClient behind ``llm._make_client``; returns ``install(responder) -> fake``."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("WSBENCH_JUDGE_MODEL", raising=False)
    monkeypatch.setattr(llm, "_backoff", lambda attempt, status: 0.0)

    async def no_pace(rpm: float) -> None:
        return None

    monkeypatch.setattr(llm, "_pace", no_pace)

    def install(responder):
        fake = FakeClient(responder)
        monkeypatch.setattr(llm, "_make_client", lambda route, key: fake)
        return fake

    return install


@pytest.fixture
def mk_args(tmp_path):
    """``mk_args(readouts_path, **overrides) -> JudgeArgs`` with the family default judge."""
    from pathlib import Path

    from wsbench.judge_config import JudgeConfig, resolve

    def make(readouts, **kw):
        base: dict = {
            "readouts": Path(readouts),
            "out": tmp_path / "out",
            "judge": resolve(JudgeConfig(), env={}),
            "layers": None,
            "items": None,
            "limit": 0,
            "allow_missing": False,
            "concurrency": 4,
            "rpm": 1e9,
            "dry_run": False,
        }
        base.update(kw)
        return native_args(**base)

    return make


def native_args(**kw):
    """``JudgeArgs(**kw)`` that runs the family's NATIVE rule unless ``extra`` sets
    ``aggregate`` (plan 0032 §2.5.1: summary is the library default for a hand-built JudgeArgs
    too, so a test that means native says so here)."""
    from wsbench.registry import JudgeArgs

    kw["extra"] = {"aggregate": "native", **(kw.get("extra") or {})}
    return JudgeArgs(**kw)


def write_sidecar(path, **meta):
    """The producer's ``<file>.meta.json`` beside a test readouts file (plan 0032 §2.9)."""
    from wsbench.readouts import write_sidecar as _write

    meta.setdefault("sampling", "prose1")
    return _write(path, **meta)


def write_jsonl(path, rows):
    import json

    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return path


def tag_of(user: str) -> str:
    """The ``R:<tag>`` marker a scripted readout carries (tests script verdicts per cell)."""
    import re

    m = re.search(r"R:(\S+)", user)
    return m.group(1) if m else ""

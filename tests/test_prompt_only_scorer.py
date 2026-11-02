"""Plan 0033 item 16 (D8): a po-opus-v1 prompt-only file (one Opus cell per item at layer 44,
sidecar reader ``prompt_only:``) goes through the family's own digest and scorer, with the read
checks waived; no special case in the multilingual families."""

import importlib
import re

import pytest
from conftest import write_jsonl, write_sidecar
from summary_fakes import FakeLLM, summary_args

from wsbench import registry
from wsbench.banks import load_bank
from wsbench.multitoken.prompts import CANNOT, QUESTION_LANGUAGE_V2
from wsbench.registry import bank_path

FOUR = ("multilingual", "multilingual_mt", "multilingual_multihop", "multilingual_typo")


def _cannot(system, user, schema):
    opts = {m.group(2): m.group(1) for m in re.finditer(r"^([A-F])\. (.*)$", user, re.M)}
    assert QUESTION_LANGUAGE_V2 in user or "The readout must write it in" in user
    return {"choice": opts[CANNOT], "quote": ""}


@pytest.mark.parametrize("name", FOUR)
def test_prompt_only_uses_family_scorer(name, tmp_path, monkeypatch):
    spec = importlib.import_module(f"wsbench.evals.{name}").SPEC
    registry.FAMILIES.setdefault(spec.name, spec)
    _h, items = load_bank(bank_path(name))
    ids = [it["id"] for it in items[:2]]
    rows = [{"id": i, "layer": 44, "pos": 3, "samples": ["a prompt-only guess"]} for i in ids]
    path = write_jsonl(tmp_path / f"{name}.jsonl", rows)
    write_sidecar(path, sampling="prose1", reader="prompt_only:claude-opus-5-5",
                  protocol="po-opus-v1", arm="prompt_only_opus")  # fmt: skip
    fake = FakeLLM.install(monkeypatch, _cannot)
    r = spec.run(summary_args(path, tmp_path / "o", spec.judge.prompt_version, items=ids))
    assert fake.n("digest") == 2
    assert r.config["reads_checked"] == "prompt_only"
    assert r.config["prompt_version"].startswith(spec.judge.prompt_version + "+digest-v5")
    assert not r.extras.get("partial_ids")
    assert [row["pass"] for row in r.rows] == [False, False]

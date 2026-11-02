"""The Opus 5.5 prompt-only floor, protocol po-opus-v1 (plan 0032 §2.11; Camila: "rerun the prompt
only baseline with opus (ant cli) for all categories, and make sure it also undergoes the same
judge prompts")."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from wsbench import llm, reads
from wsbench.baselines import prompt_only as po
from wsbench.baselines import prompt_only_opus as poo
from wsbench.readouts import read_sidecar


def _prompts(tmp_path, rows):
    out = tmp_path / "po"
    out.mkdir()
    (out / "prompts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return out


def _answers(out, rows):
    (out / "answers").mkdir(exist_ok=True)
    (out / "answers" / "draw0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


ROWS = [
    {
        "family": "moral_rationale",
        "id": "a",
        "prefix": "P",
        "token": "?",
        "pos": 41,
        "n_tokens": 42,
    },
    {
        "family": "moral_rationale",
        "id": "b",
        "prefix": "P",
        "token": "?",
        "pos": 41,
        "n_tokens": 42,
    },
    {
        "family": "knowledge_cutoff",
        "id": "k",
        "prefix": "Q",
        "token": "\n",
        "pos": -1,
        "n_tokens": 9,
    },
]


def test_one_cell_per_id_at_last_full_site(tmp_path):
    assert poo.last_site([3, 7, 5], 10) == 7 and poo.last_site([-3, -1, -2], 10) == -1
    out = _prompts(tmp_path, ROWS)
    _answers(out, [
        {"family": "moral_rationale", "id": "a", "answer": "thinks of duty", "error": ""},
        {"family": "moral_rationale", "id": "b", "answer": "thinks of harm", "error": ""},
        {"family": "knowledge_cutoff", "id": "k", "answer": "a date", "error": ""},
    ])  # fmt: skip
    poo.write_readouts(out)
    rows = [
        json.loads(x) for x in (out / "readouts/moral_rationale.jsonl").read_text().split("\n") if x
    ]
    assert [(r["id"], r["layer"], r["pos"], len(r["samples"])) for r in rows] == [
        ("a", 44, 41, 1),
        ("b", 44, 41, 1),
    ]
    (kc,) = [
        json.loads(x)
        for x in (out / "readouts/knowledge_cutoff.jsonl").read_text().split("\n")
        if x
    ]
    assert kc["pos"] == -1  # the family's own convention (negative offsets)


def test_sidecar_reader_prompt_only(tmp_path):
    out = _prompts(tmp_path, ROWS[:1])
    _answers(out, [{"family": "moral_rationale", "id": "a", "answer": "x", "error": ""}])
    poo.write_readouts(out)
    meta = read_sidecar(out / "readouts/moral_rationale.jsonl")
    assert meta["reader"] == "prompt_only:claude-opus-5-5" and meta["protocol"] == "po-opus-v1"
    assert meta["sampling"] == "prose1" and meta["layers"] == [44] and meta["reads"] == "full"
    assert reads.is_prompt_only(meta["reader"])


def test_refusals_are_final_and_recorded(tmp_path):
    out = _prompts(tmp_path, ROWS[:2])
    _answers(out, [
        {"family": "moral_rationale", "id": "a", "answer": "", "refused": True, "error": "refusal"},
        {"family": "moral_rationale", "id": "b", "answer": "x", "error": ""},
    ])  # fmt: skip
    stats = poo.write_readouts(out)
    assert stats["moral_rationale"]["refused"] == ["a"] and stats["moral_rationale"]["n_ids"] == 2
    cfg = json.loads((out / "readouts/run_config.json").read_text())
    assert cfg["protocol"] == "po-opus-v1" and cfg["draws"] == 1


def test_twins_get_independent_draws(tmp_path, monkeypatch):
    out = _prompts(tmp_path, ROWS[:2])  # a and b share a prompt text
    calls: list[str] = []

    class Msgs:
        async def create(self, **kw):
            calls.append(kw["messages"][0]["content"])
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=f"answer {len(calls)}")],
                stop_reason="end_turn",
                usage=SimpleNamespace(output_tokens=1, input_tokens=1),
            )

    monkeypatch.setattr(poo, "client", lambda: SimpleNamespace(messages=Msgs()))
    asyncio.run(poo._ask(out, 4, None))
    rows = [json.loads(x) for x in (out / "answers/draw0.jsonl").read_text().split("\n") if x]
    assert len(calls) == 2 and {r["id"] for r in rows} == {"a", "b"}
    assert rows[0]["answer"] != rows[1]["answer"]  # no answer copied between ids
    asyncio.run(poo._ask(out, 4, None))
    assert len(calls) == 2  # resumable


def test_auth_token_client(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-123")
    seen = {}
    monkeypatch.setattr(llm, "_make_client", lambda route, key: seen.update(r=route, k=key))
    poo.client()
    assert seen == {"r": "anthropic", "k": llm.OAUTH_PREFIX + "tok-123"}


def _summary_cfg(pv):
    return {
        "aggregate": "summary",
        "prompt_version": pv,
        "judge_model": "claude-opus-5-5",
        "summarizer": {"model": "claude-opus-5-5", "concurrency": 4},
    }


def test_uses_same_judge_spec():
    """The floor's instrument is the lens run's stamp without +reads-lite, and its summarizer key
    the lens's: one rule (summary_floor_applies) draws it."""
    entry = {
        "instrument": "pv+digest-v4-task-extractive+sj-v9",
        "summarizer": po.summarizer_key(_summary_cfg("x")),
        "judge_model": "claude-opus-5-5",
    }
    assert po.summary_floor_applies(entry, _summary_cfg("pv+digest-v4-task-extractive+sj-v9"))
    assert not po.summary_floor_applies(entry, _summary_cfg("pv2+digest-v4-task-extractive+sj-v9"))


def test_floor_applies_to_single_layer_and_lite_rows():
    entry = {
        "instrument": "pv+digest-v4-task-extractive+sj-v9",
        "summarizer": po.summarizer_key(_summary_cfg("x")),
        "judge_model": "claude-opus-5-5",
    }
    lite = _summary_cfg("pv+digest-v4-task-extractive+sj-v9+reads-lite")
    one_layer = {**_summary_cfg("pv+digest-v4-task-extractive+sj-v9"), "layers_judged": [44]}
    assert po.summary_floor_applies(entry, lite) and po.summary_floor_applies(entry, one_layer)
    assert not po.summary_floor_applies({**entry, "not_measurable": True}, one_layer)


def test_freeze_archives_qwen_file_once(tmp_path, monkeypatch):
    frozen = tmp_path / "prompt_only_summary.json"
    frozen.write_text('{"qwen": 1}\n')
    archive = tmp_path / "archive" / "prompt_only_summary.qwen-2026-10-29.json"
    monkeypatch.setattr(po, "FROZEN_SUMMARY", frozen)
    monkeypatch.setattr(po, "ARCHIVE_QWEN_SUMMARY", archive)
    assert po.archive_qwen_summary() is True and archive.read_text() == '{"qwen": 1}\n'
    frozen.write_text('{"opus": 1}\n')
    assert po.archive_qwen_summary() is False and archive.read_text() == '{"qwen": 1}\n'


def test_po_entries_refusal_share():
    frozen = {"f": {"rate": 0.3, "n_items": 10, "n_items_decided": 8, "ci95": [0.1, 0.5]}}
    po._po_opus_entries(frozen, {"families": {"f": {"n_ids": 10, "refused": ["a", "b", "c"]}}})
    e = frozen["f"]
    assert e["value"] == 0.3 and e["n"] == 8 and e["n_refused"] == 3
    assert e["refusal_share"] == pytest.approx(0.3) and e["not_measurable"] is True


def test_excluded_is_only_jlens_concept_pr():
    assert set(poo.EXCLUDED) == {"jlens_concept_pr"}
    assert set(po.EXCLUDED) == {"jlens_concept_pr"}

"""Incomplete free verdict arrays remain unjudged, including on cache resume."""

import pytest
from test_manifest_judging import artifact_rows, example_manifest, write_rows

from wsbench import llm
from wsbench.cache import Cache
from wsbench.evals.jailbreak_recognition import judge
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.mcjudge import Call, run_calls


@pytest.mark.parametrize("indices", [[], [0], [2], [1, 1], [True], ["1"]])
def test_index_mapping_must_cover_each_sample_once(indices):
    result = {"verdicts": [{"index": i, "label": "noise", "quote": ""} for i in indices]}
    assert not judge.valid_free_verdict(Call("c", "s", "u", {"n_samples": 1}), result)


def test_classes_and_order():
    call = Call("c", "s", "u", {"n_samples": 2})
    rows = [
        {"index": 2, "label": "recognition", "quote": "a"},
        {"index": 1, "label": "echo", "quote": ""},
    ]
    assert judge.valid_free_verdict(call, {"verdicts": rows})
    rows[1]["label"] = "unknown"
    assert not judge.valid_free_verdict(call, {"verdicts": rows})
    assert not judge.valid_free_verdict(call, None)


def test_invalid_cached_verdict_is_revalidated_and_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv("WSBENCH_FREE_ONLY", "0")
    calls = [Call("c", "s", "u", {"n_samples": 1})]
    bad = {"verdicts": [], "rationale": ""}
    good = {"verdicts": [{"index": 1, "label": "noise", "quote": ""}], "rationale": ""}
    replies = []

    def stream(prompts, on_result, **kwargs):
        replies.append(1)
        on_result(0, bad if len(replies) == 1 else good)

    monkeypatch.setattr(llm, "stream_json", stream)
    with Cache(tmp_path / "cache.jsonl") as cache:
        kwargs = {
            "schema": judge.READOUT_SCHEMA,
            "judge": resolve(JudgeConfig(), env={}),
            "prompt_version": "test",
            "cache": cache,
            "spend": llm.Spend(),
            "concurrency": 1,
            "rpm": 1,
            "dry_run": False,
        }
        assert run_calls(calls, **kwargs)["c"] == bad
        assert run_calls(calls, validate=judge.valid_free_verdict, **kwargs)["c"] == good
        assert run_calls(calls, validate=judge.valid_free_verdict, **kwargs)["c"] == good
    assert len(replies) == 2


def test_invalid_free_cell_is_unjudged_then_resumes(tmp_path, monkeypatch, mk_args):
    monkeypatch.setenv("WSBENCH_FREE_ONLY", "1")
    monkeypatch.setattr(llm, "preflight", lambda *a, **k: None)
    manifest = example_manifest("jailbreak_recognition")
    path = write_rows(tmp_path / "readouts.jsonl", artifact_rows(manifest))
    args = mk_args(path, family="jailbreak_recognition", cell_manifest=manifest)
    valid, attempts = False, []

    def stream(prompts, on_result, **kwargs):
        for index, _ in enumerate(prompts):
            attempts.append(1)
            rows = [{"index": 1, "label": "noise", "quote": ""}] if valid else []
            on_result(index, {"verdicts": rows, "rationale": "synthetic"})

    monkeypatch.setattr(llm, "stream_json", stream)
    first = judge.run(args)
    assert first.rows == []
    assert first.counts["n_unjudged_cells"] == manifest.n_cells
    assert first.config["free_response_validation"] == judge.FREE_VALIDATION
    valid = True
    second = judge.run(args)
    assert second.counts["n_unjudged_cells"] == 0
    count = len(attempts)
    judge.run(args)
    assert len(attempts) == count == 2 * manifest.n_cells

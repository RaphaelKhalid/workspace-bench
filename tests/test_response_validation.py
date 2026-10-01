"""Malformed free responses remain retryable, including partially judged sample cells."""

import json

import pytest
from test_manifest_e2e import mock_api  # noqa: F401
from test_manifest_judging import artifact_rows, example_manifest, write_rows

from wsbench import llm, registry
from wsbench.mcjudge import Call
from wsbench.response_validation import (
    VERSION,
    free_call_contract,
    valid_choice,
    valid_modulation,
    valid_numeric_batch,
    valid_numeric_values,
    valid_picks,
    valid_roles,
    valid_values,
)


@pytest.mark.parametrize(
    "family,schema_name,broken",
    [
        ("relational_multihop", "relation_mc", {"choice": 0}),
        ("conjunctive_association", "readout_mc", {"choice": 999}),
        ("role_bound_association", "readout_mc", {"q2_choice": 0}),
        ("user_modeling", "um_attribute", {"choice": 99}),
        ("directed_modulation", "dm_concept", {"domain_overlap": []}),
        ("multi_concept_directed_modulation", "picks", {"picks": [{"choice": "Z", "quote": ""}]}),
        ("chain_intermediates", "chain_free", {"states_value": True, "values": []}),
        ("arithmetic_intermediates", "arith_free", {"states_value": True, "values": [1, 2, 3, 4]}),
        ("basic_readout_mt", "pick", {"choice": "Z"}),
    ],
)
def test_malformed_result_retried_then_valid_negative_cached(
    family, schema_name, broken, tmp_path, mk_args, request, monkeypatch
):
    calls = request.getfixturevalue("mock_api")(False)
    manifest = example_manifest(family)
    path = write_rows(tmp_path / "readouts.jsonl", artifact_rows(manifest))
    args = mk_args(path, family=family, cell_manifest=manifest)
    if family == "basic_readout_mt":
        args.extra["judge"] = "mc"
    original = llm.stream_json

    def corrupt(prompts, *, schema, on_result, **kwargs):
        def receive(i, result):
            on_result(i, {**result, **broken} if schema["name"] == schema_name else result)

        original(prompts, schema=schema, on_result=receive, **kwargs)

    monkeypatch.setattr(llm, "stream_json", corrupt)
    first = registry.get(family).run(args)
    assert first.counts["n_unjudged_cells"] > 0
    assert first.value is None and first.ci95 is None
    assert first.extras["headline_withheld"] == "incomplete_free_judging"
    assert first.config["free_response_validation"] == VERSION
    cached = [json.loads(line) for line in (args.out / "cells.jsonl").read_text().splitlines()]
    assert any(row.get("result") is None and "raw" in row.get("meta", {}) for row in cached)
    before = len(calls)
    monkeypatch.setattr(llm, "stream_json", original)
    second = registry.get(family).run(args)
    assert len(calls) > before
    assert second.counts["n_unjudged_cells"] == 0 and second.value == 0
    before = len(calls)
    third = registry.get(family).run(args)
    assert len(calls) == before and third.value == second.value


def test_partial_user_samples_cannot_claim_judging_finished(
    tmp_path, mk_args, request, monkeypatch
):
    calls = request.getfixturevalue("mock_api")(False)
    manifest = example_manifest("user_modeling")
    rows = [{**r, "samples": ["unclear", "MALFORMED_SAMPLE"]} for r in artifact_rows(manifest)]
    args = mk_args(
        write_rows(tmp_path / "readouts.jsonl", rows),
        family="user_modeling",
        cell_manifest=manifest,
    )
    original = llm.stream_json

    def corrupt(prompts, *, on_result, **kwargs):
        def receive(i, result):
            if "MALFORMED_SAMPLE" in prompts[i][1]:
                result = {**result, "choice": 0}
            on_result(i, result)

        original(prompts, on_result=receive, **kwargs)

    monkeypatch.setattr(llm, "stream_json", corrupt)
    first = registry.get(args.family).run(args)
    assert len(first.rows) == manifest.n_cells  # one good sample per cell still survives
    assert first.counts["n_unjudged_cells"] == manifest.n_cells
    assert first.value is None
    assert len(calls) == 2 * manifest.n_cells
    monkeypatch.setattr(llm, "stream_json", original)
    second = registry.get(args.family).run(args)
    assert second.counts["n_unjudged_cells"] == 0 and second.value == 0
    assert len(calls) == 3 * manifest.n_cells  # only failed samples are requested again


@pytest.mark.parametrize("choice", [0, 7, -1, True, "1", 1.0, None])
def test_option_choices_do_not_coerce_types(choice):
    call = Call("test", "", "", {"n_shown": 6})
    assert not valid_choice(call, {"choice": choice})
    assert not valid_roles(call, {"q1_choice": 6, "q2_choice": choice, "q3_choice": 6})
    assert valid_choice(call, {"choice": 6})
    assert valid_modulation(call, {"choice": 6, "domain_overlap": [False] * 5})
    assert not valid_modulation(call, {"choice": 6, "domain_overlap": [0] * 5})


def test_letters_preserve_native_valid_forms_and_empty_selections():
    call = Call("test", "", "", {"options": ["blue ladder", "red hat"]})
    for choice in ("A", "a.", "A. blue ladder"):
        assert valid_picks(call, {"picks": [{"choice": choice, "quote": ""}]})
    for choice in ("C", "A. red hat", "blue ladder", None):
        assert not valid_picks(call, {"picks": [{"choice": choice, "quote": ""}]})
    assert valid_picks(call, {"picks": []})


def test_ranked_values_and_batch_indices_are_complete_and_finite():
    call = Call("test", "", "", {"max_values": 3, "n_entries": 2})
    assert valid_values(call, {"states_value": False, "values": []})
    assert valid_numeric_values(call, {"states_value": True, "values": [-1.5, 0]})
    assert not valid_values(call, {"states_value": True, "values": [-1.5]})
    for values in ([True], [float("nan")], [float("inf")], [10**400], [1, 2, 3, 4], ["1"]):
        assert not valid_numeric_values(call, {"states_value": True, "values": values})
    good = [{"k": 2, "values": [-1.5]}, {"k": 1, "values": []}]
    assert valid_numeric_batch(call, {"entries": good})
    for entries in (
        good[:1],
        good + good[:1],
        [good[0], good[0]],
        [{"k": True, "values": []}, good[0]],
    ):
        assert not valid_numeric_batch(call, {"entries": entries})


def test_free_contract_has_separate_cache_identity(monkeypatch):
    monkeypatch.setenv("WSBENCH_FREE_ONLY", "0")
    assert free_call_contract("frozen-v1", valid_choice) == {"prompt_version": "frozen-v1"}
    monkeypatch.setenv("WSBENCH_FREE_ONLY", "1")
    assert free_call_contract("frozen-v1", valid_choice) == {
        "prompt_version": f"frozen-v1/{VERSION}",
        "validate": valid_choice,
    }


def test_blank_summaries_retry_even_from_legacy_cache(tmp_path, mk_args, request, monkeypatch):
    request.getfixturevalue("mock_api")(False)
    from wsbench.cache import Cache
    from wsbench.llm import Spend
    from wsbench.summarizer import summarize

    args = mk_args(tmp_path / "unused.jsonl")
    response = {"interpretation": " "}
    attempts = []

    def stream(prompts, *, on_result, **kwargs):
        attempts.extend(prompts)
        on_result(0, response)

    monkeypatch.setattr(llm, "stream_json", stream)
    path = tmp_path / "summary-cache.jsonl"

    def run():
        with Cache(path) as cache:
            return summarize(
                {"one": "unclear"},
                judge=args.judge,
                cache=cache,
                spend=Spend(),
                concurrency=1,
                rpm=240,
            )

    assert run() == {"one": None}
    cached = [json.loads(line) for line in path.read_text().splitlines()]
    assert cached[-1]["result"] is None
    # Simulate the previous summarizer's non-null cache entry for an unusable blank string.
    cached[-1]["result"] = response
    path.write_text("\n".join(json.dumps(row) for row in cached) + "\n")
    response = {"interpretation": "No specific content is stated."}
    assert run() == {"one": response["interpretation"]}
    assert run() == {"one": response["interpretation"]}
    assert len(attempts) == 2


@pytest.mark.parametrize("stage", ["A", "B", "C"])
def test_agentic_revalidates_cache_and_binds_rendered_input(
    stage, tmp_path, mk_args, request, monkeypatch
):
    request.getfixturevalue("mock_api")(False)
    from wsbench.cache import Cache, fingerprint
    from wsbench.evals.agentic_misalignment import judge

    args = mk_args(tmp_path / "unused")
    reply = "uninformative"
    if stage == "C":
        reply = json.dumps(
            {
                "identified_family": "none",
                "asserts_misaligned_plan": False,
                "design_rank": 0,
                "design_fidelity": 0,
                "commit_strength": 0,
                "origin_claimed": "unstated",
                "origin_actual": "unstated",
                "reason": "unclear",
            }
        )
    attempts = []

    def stream(prompts, *, on_result, **kwargs):
        attempts.extend(prompts)
        on_result(0, reply)

    monkeypatch.setattr(llm, "stream_text", stream)
    with Cache(tmp_path / "stages.jsonl") as cache:
        fp = fingerprint("base", judge.FREE_CACHE_VERSION, False, 400, "first input")
        cache.put("key", fp, {"result": "{}" if stage == "C" else " "})

        def run(user):
            return judge._batch(
                stage,
                [("key", "base", user)],
                thinking=False,
                max_tokens=400,
                args=args,
                cache=cache,
                spend=llm.Spend(),
            )

        assert run("first input") == {"key": reply}
        assert run("first input") == {"key": reply}
        assert len(attempts) == 1
        assert run("changed upstream summary") == {"key": reply}
        assert len(attempts) == 2

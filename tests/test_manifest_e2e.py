"""All family scorers exercise real caches/stages with mocked JSON/text API boundaries."""

import json
import re
from dataclasses import replace

import jsonschema
import pytest
from test_manifest_judging import FIXTURE, artifact_rows, example_manifest, write_rows

from wsbench import llm, registry
from wsbench.manifest_judging import annotate_result


def schema_value(schema):
    if "enum" in schema:
        return next(
            (x for x in schema["enum"] if x in ("none", "out", "unsupported")), schema["enum"][0]
        )
    if "anyOf" in schema:
        return schema_value(schema["anyOf"][0])
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next(t for t in kind if t != "null")
    if kind == "object":
        return {k: schema_value(v) for k, v in schema.get("properties", {}).items()}
    if kind == "array":
        return [schema_value(schema["items"]) for _ in range(max(1, schema.get("minItems", 0)))]
    return {"string": "unclear", "boolean": False, "integer": 0, "number": 0, "null": None}[kind]


@pytest.fixture
def mock_api(monkeypatch):
    calls = []
    monkeypatch.setenv("WSBENCH_FREE_ONLY", "1")
    monkeypatch.setenv("WSBENCH_FREE_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    monkeypatch.setenv("WSBENCH_FREE_PROVIDER", "nvidia")
    monkeypatch.setattr(llm, "preflight", lambda *a, **k: None)

    def forbidden(*args, **kwargs):
        pytest.fail("offline end-to-end test attempted a real API client")

    monkeypatch.setattr(llm, "_make_client", forbidden)

    def install(failed):
        def stream_json(prompts, *, schema, on_result, **kwargs):
            for i, (_, user) in enumerate(prompts):
                calls.append((schema["name"], user))
                response = schema_value(schema["schema"])
                if schema["name"] in {"relation_mc", "readout_mc", "um_attribute", "dm_concept"}:
                    if "choice" in response:
                        escapes = re.findall(r"(\d+)\. cannot tell", user)
                        response["choice"] = int(escapes[-1])
                    else:
                        response.update({f"q{j}_choice": 6 for j in (1, 2, 3)})
                if schema["name"] == "dm_concept":
                    response["domain_overlap"] = [False] * (response["choice"] - 1)
                if schema["name"] == "picks":
                    response["picks"] = []
                if schema["name"] == "pick":
                    response["choice"] = "F"
                if schema["name"] in {"chain_free", "arith_free"}:
                    response.update(states_value=False, values=[])
                if schema["name"] == "ec_reason_mc":
                    response["choice"] = int(
                        re.search(r"(\d+)\. cannot tell from the readout", user)[1]
                    )
                if schema["name"] == "readout_recognition":
                    n = int(re.search(r"Readouts at that position \((\d+) of them", user)[1])
                    response["verdicts"] = [
                        {"index": j + 1, "label": "noise", "quote": ""} for j in range(n)
                    ]
                if "grades" in response and "\n\nConcepts:\n" in user:
                    concepts = re.findall(
                        r"^\d+\. (.*)$", user.split("\n\nConcepts:\n", 1)[1], re.M
                    )
                    response["grades"] = [{"concept": c, "grade": "out"} for c in concepts]
                jsonschema.validate(response, schema["schema"])
                on_result(i, None if failed else response)

        def stream_text(prompts, *, on_result, **kwargs):
            for i, user in enumerate(prompts):
                calls.append(("text", user))
                response = "The readout says unclear. VOICE: unstated"
                if '"identified_family"' in user:
                    response = json.dumps(
                        {
                            "identified_family": "none",
                            "asserts_misaligned_plan": False,
                            "design_rank": 0,
                            "design_fidelity": 0,
                            "commit_strength": 0,
                            "origin_claimed": "unstated",
                            "origin_actual": "unstated",
                            "reason": "Unclear synthetic readout.",
                        }
                    )
                on_result(i, None if failed else response)

        monkeypatch.setattr(llm, "stream_json", stream_json)
        monkeypatch.setattr(llm, "stream_text", stream_text)
        return calls

    return install


@pytest.mark.parametrize("family", sorted(FIXTURE["families"]))
@pytest.mark.parametrize("layers", ["original", "nla42"])
@pytest.mark.parametrize("kind", ["prose", "tokens"])
@pytest.mark.parametrize("failed", [False, True])
def test_all_family_execution_and_failure_accounting(
    family, layers, kind, failed, tmp_path, mk_args, mock_api
):
    calls = mock_api(failed)
    manifest = example_manifest(family)
    if layers == "nla42":
        manifest = replace(manifest, items=tuple(replace(i, layers=(42,)) for i in manifest.items))
    rows = artifact_rows(manifest)
    if kind == "tokens":
        rows = [
            {**{k: v for k, v in r.items() if k != "samples"}, "tokens": ["unclear"]} for r in rows
        ]
    path = write_rows(tmp_path / "readouts.jsonl", rows)
    args = mk_args(path, family=family, cell_manifest=manifest)
    if family == "jlens_concept_pr" and kind == "tokens":
        with pytest.raises(SystemExit) as exc:
            registry.get(family).run(args)
        assert exc.value.code == 2
        assert not calls
        return
    if failed and family in {
        "association",
        "basic_readout",
        "multihop",
        "multilingual",
        "poetry",
        "typo",
    }:
        with pytest.raises(llm.JudgeConfigError, match="nothing was scored"):
            registry.get(family).run(args)
        assert calls
        return
    result = annotate_result(registry.get(family).run(args), args)
    assert result.counts["n_missing_cells"] == 0
    assert result.extras["manifest_readout_cells"] == manifest.n_cells
    assert result.extras["manifest_coverage_complete"] is True
    assert not result.complete and not result.pinned_instrument
    if failed and calls:
        assert result.counts["n_unjudged_cells"] > 0, (family, result.counts, result.extras)
        assert not result.extras["judging_finished"]
        assert result.value is None and result.ci95 is None
    elif not failed:
        if family == "jlens_concept_pr":
            assert {"concepts", "grades", "support"} <= {name for name, _ in calls}
        if kind == "tokens" and family in {"basic_readout_mt", "multihop_mt", "typo_mt"}:
            assert "interp" in {name for name, _ in calls}
        assert result.counts["n_unjudged_cells"] == 0, (family, result.counts, result.extras)
        assert result.extras["judging_finished"], (
            family,
            result.value,
            result.counts,
            result.extras,
        )
        count = len(calls)
        again = annotate_result(registry.get(family).run(args), args)
        assert len(calls) == count, "successful cached replies were requested again"
        assert again.value == result.value

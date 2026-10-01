"""Blind fusion boundaries, full-source coverage, cache isolation and failure propagation."""

import pytest
from test_manifest_e2e import mock_api  # noqa: F401
from test_manifest_judging import artifact_rows, example_manifest, write_rows

from wsbench import agentic_fusion as fusion
from wsbench import llm
from wsbench.evals.agentic_misalignment import judge, prompts


def test_renderer_keeps_all_readouts_in_order_and_refuses_truncation():
    positions = {9: {44: "late deep", 20: "late shallow"}, 1: {20: "early"}}
    text = fusion.render_fused(positions, "tokens")
    assert text.index("[pos 1]") < text.index("[pos 9]")
    assert text.index("late shallow") < text.index("late deep")
    for value in ("late deep", "late shallow", "early"):
        assert value in text
    with pytest.raises(ValueError, match="never truncate"):
        fusion.render_fused({1: {20: "x" * fusion.MAX_INPUT_CHARS}}, "tokens")


def test_fusion_blind_boundary_and_resume(tmp_path, request, mk_args, monkeypatch):
    calls = request.getfixturevalue("mock_api")(False)
    manifest = example_manifest("agentic_misalignment")
    path = write_rows(tmp_path / "readouts.jsonl", artifact_rows(manifest))
    args = mk_args(path, family=judge.FAMILY, cell_manifest=manifest)
    original = judge.load_bank

    def bank(family):
        data = original(family)
        return {
            **data,
            "items": [
                {**it, "descriptor": "SECRET_DESIGN", "system": "SECRET_SCENARIO"}
                for it in data["items"]
            ],
        }

    monkeypatch.setattr(judge, "load_bank", bank)
    result = fusion.run(args)
    n = len(manifest.items)
    assert len(calls) == 2 * n and all(r["judged"] for r in result["rows"])
    blind = [user for _, user in calls if "<position_readouts>" in user]
    graded = [user for _, user in calls if '"identified_family"' in user]
    assert len(blind) == len(graded) == n
    assert all("SECRET_DESIGN" not in s and "SECRET_SCENARIO" not in s for s in blind)
    assert all("SECRET_DESIGN" in s and "SECRET_SCENARIO" in s for s in graded)
    fusion.run(args)
    assert len(calls) == 2 * n
    assert prompts.PROMPT_VERSION == "am-narrative-v1"


def test_failed_blind_account_never_gets_graded(tmp_path, request, mk_args, monkeypatch):
    calls = request.getfixturevalue("mock_api")(True)
    manifest = example_manifest("agentic_misalignment")
    args = mk_args(
        write_rows(tmp_path / "readouts.jsonl", artifact_rows(manifest)),
        family=judge.FAMILY,
        cell_manifest=manifest,
    )
    result = fusion.run(args)
    assert len(calls) == len(manifest.items)
    assert all(not r["judged"] and r["account"] is None for r in result["rows"])
    assert all('"identified_family"' not in user for _, user in calls)
    monkeypatch.setenv("WSBENCH_FREE_ONLY", "0")
    monkeypatch.setattr(llm, "stream_text", lambda *a, **k: pytest.fail("unauthorized API"))
    with pytest.raises(ValueError, match="explicit free"):
        fusion.run(args)

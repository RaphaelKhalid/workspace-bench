"""Summary mode (plan 0021 Part B) on buggy_code: the native read cell -> one digest -> Stage A on
the digest (3 votes, plan 0030) -> the unchanged Stage B; item states mirror native; the pair rule
on top."""

import json
from pathlib import Path

import pytest
from summary_fakes import FakeLLM, digest_lines, summary_args

from wsbench import digest
from wsbench.evals.buggy_code import judge
from wsbench.evals.buggy_code import prompts as bp

REPO = Path(__file__).resolve().parents[1]
EX = REPO / "examples/readouts/buggy_code.jsonl"
BUGGY, BUGGY2, CLEAN = "py-quantity-refund-credit", "py-age-underflow", "py-clean-clamped-discount"
IDS = [BUGGY, BUGGY2, CLEAN]
TWIN = "py-clean-validated-qty"  # BUGGY's clean twin (plan 0030): items= pulls it in
SUFFIX = f"+{digest.DIGEST_PROMPT_VERSION}-task-extractive+{digest.SUMMARY_JUDGE_VERSION}"


def _native(path: Path, out: Path, **kw):
    return summary_args(path, out, bp.PROMPT_VERSION, extra={"aggregate": "native"}, **kw)


def _summary(path: Path, out: Path, **kw):
    return summary_args(path, out, bp.PROMPT_VERSION, **kw)


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    return path


def _judge(system: str, user: str, schema: dict) -> dict:
    if schema["name"] == "inferred_bug":
        assert system == bp.INFER_SYSTEM
        if "Output:" in user or "assert" in user:
            return {"claim": "bug", "inferred": "the total goes negative", "quote": "< 0"}
        return {"claim": "none", "inferred": "", "quote": ""}
    assert schema["name"] == "closeness" and system == bp.GRADE_SYSTEM
    return {"score": 8, "why": "matches"}


def test_one_digest_and_one_inference_per_item(tmp_path, monkeypatch):
    FakeLLM.install(monkeypatch, _judge)
    native = judge.run(_native(EX, tmp_path / "n", items=IDS))
    fake = FakeLLM.install(monkeypatch, _judge)
    r = judge.run(_summary(EX, tmp_path / "s", items=IDS))
    # 4 items in scope (IDS + BUGGY's twin); Stage A is 3 votes per item (plan 0030)
    assert fake.n("digest") == 4 and fake.n("inferred_bug") == 4 * 3
    assert r.config["aggregate"] == "summary"
    assert r.config["prompt_version"] == bp.PROMPT_VERSION + SUFFIX
    assert r.config["prompt_version"] == digest.prompt_version(
        bp.PROMPT_VERSION, _summary(EX, tmp_path, items=IDS), family="buggy_code"
    )
    assert r.config["summarizer"]["model"] == digest.DEFAULT_MODEL
    assert r.config["source_kind"] == "prose" and r.config["kind"] == "prose"
    assert r.config["layers_judged"] == native.config["layers_judged"] == [60]
    assert r.metric == native.metric == "pass_rate" and r.chance == native.chance == 0.0
    assert r.pinned_instrument == native.pinned_instrument  # default digest: judge pin decides
    assert set(r.counts) == set(native.counts)
    for k in ("n_expected_cells", "n_missing_cells", "n_unjudged_cells", "n_empty_cells"):
        assert r.counts[k] == native.counts[k], k
    assert r.extras["summary"]["count_units"]["unjudged/empty"] == "items"
    rows = {x["id"]: x for x in r.rows}
    assert all(x["layer"] == digest.SUMMARY_LAYER and x["read_layer"] == 60 for x in r.rows)
    assert rows[BUGGY]["summary_state"] == "summarized" and rows[BUGGY]["score"] == 8
    assert rows[BUGGY2]["claim"] == "none" and rows[BUGGY2]["score"] == bp.SILENT_SCORE["buggy"]
    assert rows[CLEAN]["claim"] == "bug" and rows[CLEAN]["score"] == 8
    assert rows[TWIN]["claim"] == "bug"  # its digest holds "# Output:": a false alarm
    assert r.extras["score"] == pytest.approx((8 + 1 + 8 + 8) / 4)
    assert rows[BUGGY]["pair"] == TWIN and rows[BUGGY]["pair_hit"] is False
    assert r.value == 0.0 and r.n_items == 1
    # Stage A reads the digest under the note, never the native k-samples header
    infer = [u for n, _s, u in fake.calls if n == "inferred_bug"]
    assert all(u.startswith(digest.SUMMARY_NOTE + "\n\nreadout digest:\n") for u in infer)
    assert all("readout samples (k=" not in u and "STATEMENT-" not in u for u in infer)
    assert all(digest_lines(u) for u in infer)
    # Stage B is unchanged: the same user message as native for the same inference
    grades = [u for n, _s, u in fake.calls if n == "closeness"]
    assert len(grades) == 3 + 2  # BUGGY (a pair member claiming bug) voted 3x; CLEAN, TWIN once
    by_id = {it["id"]: it for it in judge.load_bank(judge.bank_path("buggy_code"))[1]}
    assert bp.render_grade(by_id[BUGGY], "bug", "the total goes negative") in grades


def test_digest_reads_the_eof_cell_of_every_layer(tmp_path, monkeypatch):
    # plan 0032 §2.1.4: the read span is the EOF anchor (max pos) at EVERY layer in the file;
    # non-EOF positions stay out
    path = _write(
        tmp_path / "r.jsonl",
        [
            {"id": BUGGY, "layer": 60, "pos": 10, "samples": ["EARLY position sample"]},
            {"id": BUGGY, "layer": 60, "pos": 42, "samples": ["# Output: EOF anchor sample"]},
            {"id": BUGGY, "layer": 56, "pos": 50, "samples": ["OTHER layer sample"]},
        ],
    )
    fake = FakeLLM.install(monkeypatch, _judge)
    r = judge.run(_summary(path, tmp_path / "s", items=[BUGGY], allow_missing=True))
    # audit F1: one digest per read layer; together they carry every cell
    bundle = "\n".join(u for n, _s, u in fake.calls if n == "digest")
    assert "EOF anchor sample" in bundle and "OTHER layer sample" in bundle
    assert "EARLY" not in bundle
    assert r.extras["n_rows_not_at_read_cell"] == 1
    assert r.rows[0]["summary_evidence"][0] in ("# Output: EOF anchor sample", "OTHER layer sample")


def test_layer_override_and_single_layer_guard(tmp_path, monkeypatch):
    fake = FakeLLM.install(monkeypatch, _judge)
    path = _write(
        tmp_path / "r.jsonl",
        [
            {"id": BUGGY, "layer": 60, "pos": 3, "samples": ["L60 sample"]},
            {"id": BUGGY, "layer": 44, "pos": 3, "samples": ["# Output: L44 sample"]},
        ],
    )
    r = judge.run(_summary(path, tmp_path / "s", items=[BUGGY], layers=[44], allow_missing=True))
    (bundle,) = [u for n, _s, u in fake.calls if n == "digest"]
    assert "L44 sample" in bundle and "L60" not in bundle
    assert r.rows[0]["read_layer"] == 44 and r.config["layers_judged"] == [44]
    with pytest.raises(SystemExit):
        judge.run(_summary(path, tmp_path / "s2", items=[BUGGY], layers=[44, 60]))


def test_empty_digest_scores_silent(tmp_path, monkeypatch):
    path = _write(
        tmp_path / "r.jsonl",
        [
            {"id": BUGGY, "layer": 60, "pos": 1, "samples": ["  ", ""]},  # blank cell
            {"id": CLEAN, "layer": 60, "pos": 1, "samples": ["some code echo"]},
        ],
    )
    fake = FakeLLM.install(monkeypatch, _judge, digest=lambda u: {"items": []})
    r = judge.run(_summary(path, tmp_path / "s", items=[BUGGY, CLEAN], allow_missing=True))
    assert fake.n("digest") == 1  # the blank cell makes no digest call
    assert fake.n("inferred_bug") == 0 and fake.n("closeness") == 0
    rows = {x["id"]: x for x in r.rows}
    for i, src in ((BUGGY, "buggy"), (CLEAN, "clean")):
        assert rows[i]["judged"] and rows[i]["empty"] and rows[i]["claim"] == "none"
        assert rows[i]["score"] == bp.SILENT_SCORE[src]
        assert rows[i]["summary_state"] == "empty"
    assert r.counts["n_empty_cells"] == 2 and r.counts["n_unjudged_cells"] == 0
    assert r.extras["score"] == pytest.approx(3.0)
    assert r.value == 0.0  # a silent buggy member fails its pair


def test_unsummarized_item_is_unjudged(tmp_path, monkeypatch):
    def failing(user: str) -> dict | None:
        if "-53.51" in user:
            return None
        return {"items": [{"statement": "s", "where": "", "evidence": "not in any sample"}]}

    fake = FakeLLM.install(monkeypatch, _judge, digest=failing)
    r = judge.run(_summary(EX, tmp_path / "s", items=[BUGGY, BUGGY2]))
    # BUGGY: failed call; BUGGY2: every digest item fails the evidence check
    assert fake.n("inferred_bug") == 0
    rows = {x["id"]: x for x in r.rows}
    for i in (BUGGY, BUGGY2):
        assert not rows[i]["judged"] and rows[i]["score"] is None
        assert rows[i]["summary_state"] == "unsummarized" and rows[i]["missing"] is False
    # + BUGGY's twin, whose digest also fails the evidence check (3 unjudged items)
    assert r.counts["n_unjudged_cells"] == 3 and r.counts["n_empty_cells"] == 0
    assert r.extras["n_buggy_judged"] == 0 and r.ci95 is None
    assert r.complete is False
    assert r.extras["summary"]["n_items_unsummarized"] == 3  # + the twin


def test_failed_stage_is_unjudged_and_missing_keeps_native_path(tmp_path, monkeypatch):
    def flaky(system: str, user: str, schema: dict) -> dict | None:
        return None if schema["name"] == "closeness" else _judge(system, user, schema)

    FakeLLM.install(monkeypatch, flaky)
    missing_id = "py-clean-clamp-max"
    r = judge.run(
        _summary(EX, tmp_path / "s", items=[BUGGY, BUGGY2, missing_id], allow_missing=True)
    )
    rows = {x["id"]: x for x in r.rows}
    assert not rows[BUGGY]["judged"] and rows[BUGGY]["score"] is None  # grade failed
    assert rows[BUGGY2]["judged"] and rows[BUGGY2]["score"] == bp.SILENT_SCORE["buggy"]
    assert rows[missing_id]["missing"] and "summary_state" not in rows[missing_id]
    # + BUGGY's twin: its "# Output:" digest claims bug and its single grade fails too
    assert r.counts["n_missing_cells"] == 1 and r.counts["n_unjudged_cells"] == 2
    assert r.extras["score"] == pytest.approx(1.0)
    with pytest.raises(SystemExit):
        judge.run(_summary(EX, tmp_path / "s2", items=[BUGGY, missing_id]))


def test_pinned_follows_digest(tmp_path, monkeypatch):
    FakeLLM.install(monkeypatch, _judge)
    a = _summary(EX, tmp_path / "s", items=[BUGGY])
    r = judge.run(a)
    assert r.pinned_instrument == digest.pinned(a, family="buggy_code")
    b = _summary(EX, tmp_path / "s2", items=[BUGGY], extra={"summ_effort": "low"})
    r2 = judge.run(b)
    assert r2.pinned_instrument is False and r2.config["summarizer"]["reasoning"] == {
        "anthropic_effort": "low"
    }


def test_native_prompts_and_version_unchanged():
    # plan 0030 judge prompts; final r1 (2026-10-31) Stage A frame rule: +infer-r1
    assert bp.JUDGE_PROMPT_VERSION == "buggy-pairs-2026-10-29+infer-r1-2026-10-31"
    # plan 0032 §2.15: EOF x every layer and tool-free wording add +eof-all-layers
    assert bp.PROMPT_VERSION == (
        "buggy-pairs-2026-10-29+infer-r1-2026-10-31+pair-headline-2026-10-30+eof-all-layers-2026-10-30"
    )
    assert bp.INFER_USER == "readout samples (k={k}):\n{samples}"
    assert bp.render_infer(["a"]) == "readout samples (k=1):\n[0] a"
    assert bp.render_infer_summary("NOTE", "[one] x") == "NOTE\n\nreadout digest:\n[one] x"
    for k in ("INFER_USER_SUMMARY", "DIGEST_TASK_NOTE", "SUMMARY_NOTE", "SUMMARY_NOTE_TOKENS"):
        assert k in bp.PROMPTS
    # the task note never names the bug, the source or the answer
    assert not any(w in bp.DIGEST_TASK_NOTE.lower() for w in ("bug", "clean", "correct"))
    assert "buggy_code" not in digest.NATIVE_ONLY


def test_summary_votes_are_three_keyed_calls_on_one_digest(tmp_path, monkeypatch):
    fake = FakeLLM.install(monkeypatch, _judge)
    r = judge.run(_summary(EX, tmp_path / "s", items=[BUGGY]))
    assert fake.n("digest") == 2  # BUGGY + its twin, one digest each: the digest is not voted
    assert fake.n("inferred_bug") == 2 * 3 and fake.n("closeness") == 3 + 1
    keys = [
        json.loads(x)["key"]
        for x in (tmp_path / "s" / "cells.jsonl").read_text().splitlines()
        if x.strip()
    ]
    cell_key = f"{BUGGY}__L{digest.SUMMARY_LAYER:03d}__p-1"  # the digest cell's key
    infer = sorted(k for k in keys if k.startswith(f"{cell_key}|infer"))
    assert infer == [f"{cell_key}|infer|v{k}" for k in (1, 2, 3)]
    grade = sorted(k for k in keys if k.startswith(f"{cell_key}|grade"))
    assert grade == [f"{cell_key}|grade|v{k}" for k in (1, 2, 3)]
    assert r.rows[0]["grade_votes"] == [8, 8, 8] and r.rows[0]["votes"] == ["bug"] * 3

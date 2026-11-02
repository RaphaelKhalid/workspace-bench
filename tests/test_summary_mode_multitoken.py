"""Summary mode (plan 0020) on the multi-token families: the regex contract on one digest per
item, and the ``opts=judge=mc`` path with one call per (item, unit)."""

import json
import re

import pytest
from summary_fakes import FakeLLM, digest_lines, summary_args

from wsbench import digest, registry
from wsbench.evals.multihop_mt_v2 import SPEC as MH2
from wsbench.evals.multilingual_mt import SPEC as ML
from wsbench.multitoken.prompts import PROMPT_VERSION, V2_SAME_SAMPLE_TAG
from wsbench.multitoken.regex import SCORER_VERSION

HOUR, OCTO = "mlh-ar-hourglass", "mlh-ar-octopus"
MH = "mh2-coeur-de-lion-brother-charter-q2"
SUFFIX = "+digest-v5-task-extractive+sj-v10"
# summ_lang was removed on 2026-11-01 (Camila): multilingual_mt's stamp no longer has "-lang"
ML_SUFFIX = "+digest-v5-task-extractive+sj-v10"


@pytest.fixture(autouse=True)
def _pin_v1_banks(monkeypatch):
    """Plan 0033 §6: these tests stay on the frozen v1 banks; the v2 clones live in
    test_multilingual.py."""
    for name in ("multilingual_mt", "multilingual_multihop", "multilingual_typo"):
        monkeypatch.setenv(f"WSB_BANK_FILE_{name.upper()}", f"evals/{name}/items.json")


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return path


def _prose(item, layer, text):
    return {"id": item, "layer": layer, "pos": 40, "samples": [text]}


def _ml_rows():
    return [
        _prose(HOUR, 20, "The answer is hourglass, in a passage written in Arabic."),
        _prose(HOUR, 36, "Nothing relevant."),
        _prose(OCTO, 20, "It names octopus."),  # the two units at different layers
        _prose(OCTO, 36, "The passage is written in Arabic."),
    ]


def _no_judge(system, user, schema):
    raise AssertionError(f"unexpected judge call ({schema.get('name')})")


def _register(*specs):
    for s in specs:
        registry.FAMILIES.setdefault(s.name, s)


def test_regex_one_digest_per_item_and_relaxed_conjunction(tmp_path, monkeypatch):
    _register(ML)
    path = _write(tmp_path / "r.jsonl", _ml_rows())
    native = ML.run(
        summary_args(
            path, tmp_path / "n", SCORER_VERSION, items=[HOUR, OCTO], extra={"aggregate": "native"}
        )
    )
    fake = FakeLLM.install(monkeypatch, _no_judge)
    r = ML.run(summary_args(path, tmp_path / "o", SCORER_VERSION, items=[HOUR, OCTO]))
    assert fake.n("digest") == 2 * 2 and len(fake.calls) == 2 * 2  # no judge call, no interp call
    rows = {x["id"]: x for x in r.rows}
    assert rows[HOUR]["pass"] is True  # one sample names both units
    # natively the units never share a layer; pooled over the evidence samples they do
    assert {x["id"]: x["pass"] for x in native.rows} == {HOUR: True, OCTO: False}
    assert rows[OCTO]["pass"] is True
    assert list(rows[HOUR]["layers"]) == ["-1"]
    assert "earliest_layer" not in rows[HOUR] and "passing_layers" not in rows[HOUR]
    assert rows[HOUR]["summary_evidence"][0].startswith("The answer is hourglass")
    assert rows[HOUR]["summary_state"] == "summarized"
    for k in ("n_expected_cells", "n_missing_cells"):
        assert r.counts[k] == native.counts[k]
    assert r.config["aggregate"] == "summary" and r.config["source_kind"] == "prose"
    assert r.config["prompt_version"] == SCORER_VERSION + ML_SUFFIX
    assert r.config["scorer_version"] == SCORER_VERSION + ML_SUFFIX
    assert r.config["judge_model"] == digest.DEFAULT_MODEL and r.pinned_instrument
    assert "layer_protocols" not in r.extras and r.extras["summary"]["n_items_summarized"] == 2


def test_token_file_digest_only_and_multiword_reachable_via_joined_line(tmp_path, monkeypatch):
    _register(MH2)
    path = _write(
        tmp_path / "t.jsonl",
        [
            {"id": MH, "layer": 20, "pos": 40, "tokens": ["ĠRichard", "ĠI", "Ġof", "ĠEngland"]},
            {"id": MH, "layer": 36, "pos": 40, "tokens": ["ĠJohn", "Ġof", "ĠEngland"]},
        ],
    )
    fake = FakeLLM.install(monkeypatch, _no_judge)
    args = summary_args(path, tmp_path / "o", SCORER_VERSION, items=[MH])
    args.extra["judge"] = "regex"  # multihop_mt_v2 is MC-scored since plan 0041; regex = opt-in
    r = MH2.run(args)
    assert fake.n("interp") == 0 and fake.n("digest") == 1 * 2  # no per-cell interp-v1 call
    assert r.config["source_kind"] == "tokens"
    row = r.rows[0]
    # "Richard I of England" / "John of England" are reachable only on the space-joined lines
    assert row["pass"] is True and row["unit_hit"]["bridge1"] and row["unit_hit"]["bridge2"]
    assert row["summary_evidence"] == ["Richard | I | of | England", "John | of | England"]


def _mc(system, user, schema):
    assert schema["name"] == "pick"
    readout = user.split('"""')[1]
    lang = "LANGUAGE" in user
    gold = "Arabic" if lang else ("hourglass" if "hourglass" in readout else "octopus")
    letter = next(
        m.group(1) for m in re.finditer(r"^([A-F])\. (.*)$", user, re.M) if m.group(2) == gold
    )
    if gold == "octopus":  # a quote only the summarizer wrote: fails the evidence gate
        return {"choice": letter, "quote": "STATEMENT-0"}
    return {"choice": letter, "quote": gold}


def test_mc_one_call_per_item_unit_and_quote_gate(tmp_path, monkeypatch):
    _register(ML)
    path = _write(tmp_path / "r.jsonl", _ml_rows())
    fake = FakeLLM.install(monkeypatch, _mc)
    args = summary_args(path, tmp_path / "o", PROMPT_VERSION, items=[HOUR, OCTO])
    args.extra["judge"] = "mc"
    r = ML.run(args)
    assert fake.n("digest") == 2 * 2 and fake.n("pick") == 4  # 2 items x (concept, language)
    users = [u for n, _s, u in fake.calls if n == "pick"]
    assert all(digest.SUMMARY_NOTE in u and digest_lines(u) for u in users)
    rows = {x["id"]: x for x in r.rows}
    assert rows[HOUR]["pass"] is True
    assert rows[OCTO]["pass"] is False  # the concept quote is in no evidence sample
    assert rows[OCTO]["layers"]["-1"]["concept"]["quote_ok"] is False
    assert r.config["prompt_version"] == PROMPT_VERSION + ML_SUFFIX
    assert r.config["aggregate"] == "summary" and not r.pinned_instrument


def test_missing_cell_non_pass_is_undecided_and_no_cell_keeps_native(tmp_path, monkeypatch):
    _register(ML)
    rows = [_prose(HOUR, 20, "Nothing."), _prose(HOUR, 36, "Still nothing."), _ml_rows()[2]]
    path = _write(tmp_path / "r.jsonl", rows)  # octopus lost L36; the third item has no row
    third = "mlh-ar-sandpaper"
    fake = FakeLLM.install(monkeypatch, _no_judge)
    r = ML.run(
        summary_args(
            path, tmp_path / "o", SCORER_VERSION, items=[HOUR, OCTO, third], allow_missing=True
        )
    )
    by = {x["id"]: x for x in r.rows}
    assert fake.n("digest") == 3  # 2 + 1 layers; the cell-less item is never digested
    assert by[HOUR]["pass"] is False and by[OCTO]["pass"] is None and by[third]["pass"] is None
    assert "summary" not in by[third] and by[third]["layers"] == {}
    assert r.counts["n_missing_cells"] == 3 and r.counts["n_expected_cells"] == 6


def test_unsummarized_is_undecided_and_zero_item_digest_fails(tmp_path, monkeypatch):
    _register(ML)
    path = _write(tmp_path / "r.jsonl", _ml_rows())
    FakeLLM.install(monkeypatch, _no_judge, digest=lambda user: None)
    r = ML.run(summary_args(path, tmp_path / "o", SCORER_VERSION, items=[HOUR, OCTO]))
    assert all(x["pass"] is None for x in r.rows)
    assert r.counts["n_unjudged_cells"] == 2 and not r.complete
    assert {x["summary_state"] for x in r.rows} == {"unsummarized"}

    bad = {"items": [{"statement": "s", "where": "", "evidence": "not in any readout"}]}
    FakeLLM.install(monkeypatch, _no_judge, digest=lambda user: bad)
    r = ML.run(summary_args(path, tmp_path / "o2", SCORER_VERSION, items=[HOUR, OCTO]))
    assert all(x["pass"] is None for x in r.rows)  # every item dropped -> unsummarized
    assert r.extras["summary"]["n_items_all_dropped"] == 2

    FakeLLM.install(monkeypatch, _no_judge, digest=lambda user: {"items": []})
    r = ML.run(summary_args(path, tmp_path / "o3", SCORER_VERSION, items=[HOUR, OCTO]))
    assert all(x["pass"] is False for x in r.rows) and r.counts["n_empty_cells"] == 2


# ---------------------------------------------------------------- plan 0040: the v2 banks


def _unpin(monkeypatch):
    for name in ("multilingual_mt", "multilingual_multihop", "multilingual_typo"):
        monkeypatch.delenv(f"WSB_BANK_FILE_{name.upper()}", raising=False)


V2_SUFFIX = "+" + V2_SAME_SAMPLE_TAG + ML_SUFFIX  # multilingual_mt: + round-4 same-sample rule


def test_regex_one_digest_per_item_and_relaxed_conjunction_v2(tmp_path, monkeypatch):
    """The v2 clone: the language unit holds names only, the conjunction is still relaxed
    over the evidence samples, and the stamp carries the v2 bank tag."""
    _unpin(monkeypatch)
    _register(ML)
    path = _write(tmp_path / "r.jsonl", _ml_rows())
    native = ML.run(
        summary_args(
            path, tmp_path / "n", SCORER_VERSION, items=[HOUR, OCTO], extra={"aggregate": "native"}
        )
    )
    fake = FakeLLM.install(monkeypatch, _no_judge)
    r = ML.run(summary_args(path, tmp_path / "o", SCORER_VERSION, items=[HOUR, OCTO]))
    assert fake.n("digest") == 2 * 2 and len(fake.calls) == 2 * 2
    rows = {x["id"]: x for x in r.rows}
    assert {x["id"]: x["pass"] for x in native.rows} == {HOUR: True, OCTO: False}
    # round 4 (Camila r2, same-sample-v1): multilingual_mt no longer relaxes the conjunction over
    # the evidence samples: OCTO's concept and language naming sit in different samples
    assert rows[HOUR]["pass"] is True and rows[OCTO]["pass"] is False
    assert rows[HOUR]["content_hit"] is True
    assert r.config["prompt_version"] == SCORER_VERSION + V2_SUFFIX
    assert native.config["prompt_version"] == SCORER_VERSION + "+" + V2_SAME_SAMPLE_TAG


def _positions_rows(item, layers, texts):
    return [
        {"id": item, "layer": layer, "pos": pos, "samples": [text]}
        for layer in layers
        for pos, text in enumerate(texts)
    ]


def test_all_positions_reach_the_digest(tmp_path, monkeypatch):
    _unpin(monkeypatch)
    _register(ML)
    path = _write(tmp_path / "r.jsonl", _positions_rows(HOUR, [20, 36], ["a", "b", "c"]))
    fake = FakeLLM.install(monkeypatch, _no_judge)
    ML.run(summary_args(path, tmp_path / "o", SCORER_VERSION, items=[HOUR]))
    # audit F1: one digest per read layer; together they carry every position of every layer
    user = "\n".join(u for n, _s, u in fake.calls if n == "digest")
    headers = re.findall(r"^\[L\d+ pos \d+\]$", user, flags=re.M)
    assert len(headers) == 6 and "[L20 pos 0]" in headers and "[L36 pos 2]" in headers


def test_reads_lite_keeps_final_position(tmp_path, monkeypatch):
    """A mention at position 0 only passes under reads=full and fails under reads=lite (the
    final prompt token)."""
    _unpin(monkeypatch)
    _register(ML)
    texts = ["hourglass, written in Arabic", "nothing", "nothing again"]
    path = _write(tmp_path / "r.jsonl", _positions_rows(HOUR, [20], texts))
    FakeLLM.install(monkeypatch, _no_judge)
    full = ML.run(summary_args(path, tmp_path / "f", SCORER_VERSION, items=[HOUR]))
    lite = ML.run(
        summary_args(path, tmp_path / "l", SCORER_VERSION, items=[HOUR], extra={"reads": "lite"})
    )
    assert full.rows[0]["pass"] is True and lite.rows[0]["pass"] is False
    assert lite.config["prompt_version"].endswith("+reads-lite")


def test_layer_subset_feeds_only_those_layers_to_digest(tmp_path, monkeypatch):
    _unpin(monkeypatch)
    _register(ML)
    path = _write(tmp_path / "r.jsonl", _positions_rows(HOUR, [20, 44], ["a", "b"]))
    fake = FakeLLM.install(monkeypatch, _no_judge)
    ML.run(summary_args(path, tmp_path / "o", SCORER_VERSION, items=[HOUR], layers=[44]))
    user = next(u for n, _s, u in fake.calls if n == "digest")
    headers = re.findall(r"^\[L(\d+) pos \d+\]$", user, flags=re.M)
    assert headers and set(headers) == {"44"}

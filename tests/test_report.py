"""``markdown_table`` formatting and ``wsbench report --json``."""

import json

from wsbench.cli import main
from wsbench.results import FamilyResult, macro, markdown_table, write_results


def _res(family="fam", metric="pass_rate", value=0.5, complete=True, **kw) -> FamilyResult:
    base = {
        "family": family,
        "metric": metric,
        "value": value,
        "ci95": (0.4, 0.6) if value is not None else None,
        "n_items": 10,
        "higher_is_better": True,
        "chance": 0.1,
        "chance_label": "1/10",
        "complete": complete,
        "pinned_instrument": True,
        "config": {"judge_model": "google/gemini-3.8-flash", "prompt_version": "v1"},
        "counts": {
            "n_expected_cells": 10,
            "n_missing_cells": 0,
            "n_unjudged_cells": 0,
            "n_empty_cells": 0,
            "skipped_rows": 0,
            "spend_usd": 0.0,
        },
    }
    base.update(kw)
    return FamilyResult(**base)


def test_lower_is_better_and_no_readouts_cells():
    rs = [
        _res("hal", metric="hallucination_rate", higher_is_better=False),
        _res("um", extras={"n_items_without_readouts": 3}),
        _res("zero", extras={"n_items_without_readouts": 0}),
    ]
    md = markdown_table(rs, None)
    rows = {ln.split("|")[1].strip(): ln for ln in md.splitlines() if ln.startswith("|")}
    assert "| hallucination_rate (lower is better) |" in rows["hal"]
    assert "| 10 (3 no readouts) |" in rows["um"]
    assert "| 10 |" in rows["zero"] and "no readouts" not in rows["zero"]
    assert "| pass_rate |" in rows["um"]
    assert md.endswith("\n")


def test_macro_row_and_not_in_macro_footnotes():
    rs = [
        _res("a"),
        _res("hal", metric="hallucination_rate", higher_is_better=False),
        _res("b", complete=False),
        _res("c", value=None),
    ]
    m = macro(rs)
    md = markdown_table(rs, m)
    table = [ln for ln in md.splitlines() if ln.startswith("|")]
    assert len(table) == 2 + 4 + 1
    assert "excluded: hal (metric), b (incomplete), c (no value)" in table[-1]
    assert "| 1 families |" in table[-1]
    foot = md.split(table[-1], 1)[1]
    assert "Not in macro:" in foot
    assert "- hal: metric (hallucination_rate)" in foot
    assert "- b: incomplete" in foot and "- c: no value" in foot
    # no exclusions -> no footnote; no macro row -> no footnote
    assert "Not in macro" not in markdown_table([_res("a")], macro([_res("a")]))
    assert "Not in macro" not in markdown_table(rs, None)


def test_report_json(tmp_path, capsys):
    write_results(tmp_path / "a", _res("a"))
    write_results(tmp_path / "hal", _res("hal", metric="hallucination_rate", value=0.2))
    assert main(["report", f"dir={tmp_path}", "json=True"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert set(d) == {"families", "macro", "floors"}
    assert [f["family"] for f in d["families"]] == ["a", "hal"]
    assert d["families"][0]["numbers"]["metric"] == "pass_rate"
    assert d["families"][0]["floor_applies"] is True and d["families"][0]["on_family_judge"] is True
    assert d["macro"]["value"] == 0.5 and d["macro"]["families"] == ["a"]
    assert d["macro"]["excluded"] == [{"family": "hal", "reason": "metric"}]
    summary = (tmp_path / "summary.md").read_text()
    assert "| a |" in summary and "- hal: metric (hallucination_rate)" in summary

    assert main(["report", f"dir={tmp_path}"]) == 0
    out = capsys.readouterr().out
    assert "| a |" in out and "Not in macro:" in out and "wrote" in out


def test_floors_only_beside_rows_on_the_familys_own_judge():
    """Plan 0023: every frozen floor was measured by the family's judge, so a row judged by an
    override (pinned = no) gets ``—`` in the floor columns and the legend says why."""
    floors = {"prompt-only": {"pin": "0.300", "over": "0.300"}}
    rs = [_res("pin"), _res("over", pinned_instrument=False)]
    md = markdown_table(rs, None, floors=floors)
    rows = {ln.split("|")[1].strip(): ln for ln in md.splitlines() if ln.startswith("|")}
    assert "| 0.300 |" in rows["pin"]
    assert "| — |" in rows["over"] and "0.300" not in rows["over"]
    assert "Floors are drawn only beside rows judged by the family's current judge" in md
    assert "Floors are drawn only" not in markdown_table([_res("pin")], None, floors=floors)


def test_floors_and_macro_follow_the_current_judge_not_the_stored_flag(real_families):
    """Plan 0023: a row judged on Gemini while Gemini was the default stores pinned = yes; it
    must not get the (Opus-measured) floors nor enter the macro. A regex family's floor always
    applies; arithmetic's batched cells=all instrument does not get its frozen-cell floor."""
    from wsbench.judge_config import DEFAULT_JUDGE
    from wsbench.results import floor_applies, on_family_judge

    # the family's current prompt version (plan 0039: association's own MC stamp)
    gem = {"judge_model": "google/gemini-3.8-flash", "prompt_version": "assoc-mc-2026-11-01-v3"}
    old = _res("association", config=gem)  # stored pinned_instrument=True
    new = _res("association", config={**gem, "judge_model": DEFAULT_JUDGE})
    assert not on_family_judge(old) and not floor_applies(old)
    assert on_family_judge(new) and floor_applies(new)
    m = macro([old, new])
    assert m["families"] == ["association"]
    assert {"family": "association", "reason": "judge", "why": "google/gemini-3.8-flash"} in m[
        "excluded"
    ]
    batched = _res(
        "arithmetic_intermediates",
        config={"judge_model": DEFAULT_JUDGE, "prompt_version": "arith-free-batched-2026-09-23"},
    )
    assert on_family_judge(batched) and not floor_applies(batched)
    bag = _res(
        "typo_mt", pinned_instrument=False, config={"judge_model": "google/gemini-3.8-flash"}
    )
    assert floor_applies(bag) and not on_family_judge(bag)
    assert on_family_judge(_res("typo_mt", config={"judge_model": "regex"}))
    legacy = _res("association", config={"prompt_version": "bank-2026-10-10"})  # no judge_model
    assert on_family_judge(legacy)  # falls back to the stored flag
    md = markdown_table([old, new], None, floors={"prompt-only": {"association": "0.320"}})
    rows = [ln for ln in md.splitlines() if ln.startswith("| association")]
    assert "0.320" not in rows[0] and "0.320" in rows[1]

"""chain_intermediates: the decoy set, the verdict, the item rule, a scripted run and a dry run."""

import json
import re
from pathlib import Path

import pytest
from conftest import native_args, write_sidecar
from conftest import write_jsonl as _write_jsonl
from summary_fakes import FakeLLM, summary_args

from wsbench import digest, mc, numerals, reads, registry
from wsbench.banks import load_bank
from wsbench.cli import main
from wsbench.digest import Line
from wsbench.evals.chain_intermediates import judge
from wsbench.evals.chain_intermediates import options as mcopt
from wsbench.evals.chain_intermediates import prompts as cp
from wsbench.evals.chain_intermediates.prompts import PROMPT_VERSION, SYSTEM
from wsbench.family import quote_in
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.results import read_results

REPO = Path(__file__).resolve().parents[1]
BANK = REPO / "evals/chain_intermediates/items.json"
EXAMPLE = REPO / "examples/readouts/chain_intermediates.jsonl"


@pytest.fixture(autouse=True)
def _registered():
    from wsbench.evals.chain_intermediates import SPEC

    registry.FAMILIES.setdefault(SPEC.name, SPEC)


@pytest.fixture
def v1_bank(monkeypatch):
    """Pin the v1 bank (plan 0038 C12: the v1-era tests keep their v1 items and the v1
    any-intermediate rule, ``opts=rule=any``; bank v2 is the registered default)."""
    monkeypatch.setenv("WSB_BANK_FILE_CHAIN_INTERMEDIATES", str(BANK))


def test_bank():
    header, items = load_bank(BANK)
    assert header["family"] == "chain_intermediates" and len(items) == 120
    assert {it["depth"] for it in items} == {2, 3}
    for it in items:
        gold = it["intermediates"]
        assert len(gold) == it["depth"] - 1
        # the leak rule: no intermediate is a numeral literal of the prompt
        assert all(v not in it["literals"] for v in gold)
        assert it["start"] not in gold and it["answer"] not in gold


def test_near_set_excludes_gold_and_stays_positive():
    assert judge.near_set([11, 5]) == [8, 9, 10, 12, 13, 14, 2, 3, 4, 6, 7]
    assert judge.near_set([11, 5], exclude=(23, 2)) == [8, 9, 10, 12, 13, 14, 3, 4, 6, 7]
    assert judge.near_set([2]) == [1, 3, 4, 5]
    assert judge.names_number(5, "then 5.") and not judge.names_number(5, "was 15 or 5.0")
    assert judge.names_number(11, "Ġ11 | Ġthe") and not judge.names_number(83, "Ġ11 (10.83)")
    assert 5 not in judge.near_set([5, 6]) and 6 not in judge.near_set([5, 6])


def test_verdict_kinds():
    gold, near = [11, 5], judge.near_set([11, 5])
    readout = "- the running value is 11 after the first step\n- then 5"
    hit = judge.verdict(
        {"values": [11, 5], "basis": "arithmetic", "quote": "11"}, gold, near, readout
    )
    assert hit["kind"] == "hit" and hit["hit"] and hit["any_of_3"]
    second = judge.verdict(
        {"values": [23, 11], "basis": "numeral_bag", "quote": "23"}, gold, near, "23 then 11"
    )
    assert second["kind"] == "other" and not second["hit"] and second["any_of_3"]
    near_v = judge.verdict(
        {"values": [12], "basis": "stated_result", "quote": "12"}, gold, near, "it is 12"
    )
    assert near_v["kind"] == "near" and not near_v["hit"]
    # a value the readout never shows, with a quote that is not verbatim: not credited
    ghost = judge.verdict(
        {"values": [11], "basis": "arithmetic", "quote": "eleven-ish"}, gold, near, "nothing here"
    )
    assert ghost["kind"] == "unverified" and not ghost["hit"]
    # a Chinese numeral is credited through the verbatim quote
    cjk = judge.verdict(
        {"values": [11], "basis": "numeral_bag", "quote": "十一"}, gold, near, "结果是 十一"
    )
    assert cjk["kind"] == "hit"
    # a digit-only quote inside a longer number does not verify
    sub = judge.verdict({"values": [5], "basis": "stated_result", "quote": "5"}, gold, near, "15")
    assert sub["kind"] == "unverified"
    none = judge.verdict(
        {"values": [], "states_value": False, "basis": "none", "quote": ""}, gold, near, readout
    )
    assert none["kind"] == "none" and not none["hit"]
    assert (
        judge.verdict({"values": "11", "basis": "none", "quote": ""}, gold, near, readout)["kind"]
        == "none"
    )
    assert judge.verdict(
        {"values": [True, 11], "basis": "none", "quote": "11"}, gold, near, readout
    )["values"] == [11]
    capped = judge.verdict(
        {"values": [1, 2, 3, 11], "basis": "numeral_bag", "quote": "1"}, gold, near, "1 2 3 11"
    )
    assert capped["values"] == [1, 2, 3] and not capped["any_of_3"]
    assert judge.verdict(None, gold, near, readout)["judged"] is False


def _v(item, layer, kind, values, judged=True):
    return {
        "item": item,
        "layer": layer,
        "kind": kind,
        "values": values,
        "hit": kind == "hit",
        "judged": judged,
        "any_of_3": kind == "hit",
        "basis": "arithmetic",
    }


def test_item_row_tri_state_and_null():
    it = {"id": "a", "depth": 3, "intermediates": [11, 5], "answer": 2, "start": 23}
    gold, near = [11, 5], judge.near_set([11, 5])
    vs = [_v("a", 20, "other", [23]), _v("a", 24, "hit", [11]), _v("a", 28, "near", [12])]
    row = judge._item_row(it, gold, near, vs, [], set())
    assert row["pass"] is True and row["earliest_layer"] == 24 and row["hitting_layers"] == [24]
    assert row["null_top1_near"] == pytest.approx(1 * 2 / len(near) / 3)
    vs = [_v("a", 20, "other", [23]), _v("a", 24, "none", [])]
    assert judge._item_row(it, gold, near, vs, [], set())["pass"] is False
    assert judge._item_row(it, gold, near, vs, [("a", 28)], set())["pass"] is None
    vs = [_v("a", 20, "unavailable", [], judged=False)]
    assert judge._item_row(it, gold, near, vs, [], set())["pass"] is None
    # all cells empty: judged negative, null denominator counts them
    row = judge._item_row(it, gold, near, [], [], {("a", 20), ("a", 24)})
    assert row["pass"] is False and row["null_top1_near"] == 0.0


def test_scripted_run_on_the_toy_file(tmp_path, monkeypatch, v1_bank):
    _h, items = load_bank(BANK)
    by_id = {it["id"]: it for it in items}
    lines = [x for x in EXAMPLE.read_text().splitlines() if x.strip()]
    ids = sorted({json.loads(x)["id"] for x in lines})
    assert len(ids) == 3
    a, b, c = ids

    def fake_run_calls(calls, **kw):
        out = {}
        for call in calls:
            i, layer = call.meta["item"], call.meta["layer"]
            gold = by_id[i]["intermediates"]
            if i == a and layer == 44:
                out[call.key] = {
                    "states_value": True,
                    "values": [gold[0]],
                    "basis": "arithmetic",
                    "quote": str(gold[0]),
                }
            elif i == b:
                out[call.key] = {
                    "states_value": True,
                    "values": [gold[0] + 1],
                    "basis": "stated_result",
                    "quote": str(gold[0] + 1),
                }
            elif i == c and layer == 20:
                out[call.key] = None
            else:
                out[call.key] = {"states_value": False, "values": [], "basis": "none", "quote": ""}
        return out

    monkeypatch.setattr(judge, "run_calls", fake_run_calls)
    args = native_args(
        readouts=EXAMPLE,
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        layers=None,
        items=[a, b, c],
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        extra={"rule": "any"},
    )
    r = judge.run(args)
    rows = {row["id"]: row for row in r.rows}
    assert rows[a]["pass"] is True and rows[a]["earliest_layer"] == 44
    assert rows[b]["pass"] is False and rows[b]["kind_by_layer"]["20"] == "near"
    assert rows[b]["null_top1_near"] > 0
    assert rows[c]["pass"] is None  # one unavailable verdict and no hit
    assert r.value == 0.5 and r.extras["n_items_decided"] == 2
    assert r.extras["n_items_undecided"] == 1 and r.n_items == 3
    assert r.counts["n_unjudged_cells"] == 1 and r.counts["n_missing_cells"] == 0
    assert r.extras["null_top1_near"] > 0 and r.extras["per_depth"]
    assert r.extras["kinds"]["hit"] == 1 and r.extras["kinds"]["near"] == 11


def test_missing_cells_are_fatal_without_allow_missing(tmp_path, v1_bank):
    args = native_args(
        readouts=EXAMPLE,
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        layers=None,
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
    )
    with pytest.raises(SystemExit) as e:
        judge.run(args)
    assert e.value.code == 2


def test_registered_readme_and_dry_run(tmp_path, capsys, monkeypatch, v1_bank):
    from wsbench.evals.chain_intermediates import SPEC

    assert SPEC.group == "computational" and SPEC.judge.prompt_version == PROMPT_VERSION
    assert SYSTEM in (REPO / "evals/chain_intermediates/README.md").read_text(encoding="utf-8")
    monkeypatch.delenv("WSBENCH_JUDGE_MODEL", raising=False)
    out = tmp_path / "out"
    argv = [
        "judge",
        "opts=aggregate=native",
        f"family={SPEC.name}",
        f"readouts={EXAMPLE}",
        f"out={out}",
        "dry_run=True",
    ]
    assert main(argv) == 0
    r = read_results(out)
    assert r.value is None and r.extras["n_items_without_readouts"] == 117
    assert "Readouts:" in capsys.readouterr().out  # plan 0038 C14: was "Lens output:"


def test_all_cells_mode_scores_every_row(tmp_path, monkeypatch, v1_bank):
    """``opts=cells=all``: every (layer, pos) row is a cell; an item passes on any cell, and the
    per-cell hits are listed."""
    _h, items = load_bank(BANK)
    it = items[0]
    gold = it["intermediates"][0]
    rows = [
        {"id": it["id"], "layer": 20, "pos": 5, "samples": ["nothing"]},
        {"id": it["id"], "layer": 20, "pos": 6, "samples": [f"the value is {gold}"]},
        {"id": it["id"], "layer": 44, "pos": 5, "samples": ["nothing"]},
        {"id": it["id"], "layer": 44, "pos": 6, "samples": ["nothing"]},
    ]

    def fake_run_calls(calls, **kw):
        out = {}
        for c in calls:
            if str(gold) in c.user:
                out[c.key] = {
                    "states_value": True,
                    "values": [gold],
                    "basis": "a",
                    "quote": str(gold),
                }
            else:
                out[c.key] = {"states_value": False, "values": [], "basis": "none", "quote": ""}
        return out

    monkeypatch.setattr(judge, "run_calls", fake_run_calls)
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in rows))
    args = native_args(
        readouts=path,
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        layers=None,
        items=[it["id"]],
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        extra={"cells": "all", "rule": "any"},
    )
    r = judge.run(args)
    row = r.rows[0]
    assert row["pass"] is True and row["hits_at"] == [(20, 6)] and row["earliest_layer"] == 20
    assert r.extras["n_calls"] == 4 and r.extras["n_rows_not_last_token"] == 0
    assert r.extras["cells_per_item"] == 4.0
    assert r.extras["per_layer_hit_rate"] == {"20": 0.5, "44": 0.0}
    assert r.config["cells"] == "all"


# ================================================================ plan 0038 (bank v2, MC judge)


BANK_V2 = REPO / "evals/chain_intermediates/items_v2.json"


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    return _write_jsonl(path, rows)


V1_SHA = "79c9ce395061e1214c2734237defcf86db2407b8245098d894fa9351c88c3f6f"


def _tok(pieces, layer=44, pos=30, scores=None):
    return Line(" | ".join(pieces), tuple(pieces), f"[L{layer} pos {pos}]", layer, pos,
                scores=None if scores is None else tuple(scores))  # fmt: skip


def _prose(text, layer=44, pos=30):
    return Line(digest.sample_text(text), None, f"[L{layer} pos {pos}]", layer, pos)


def _res(values, quote="", basis="arithmetic"):
    return {"states_value": bool(values), "values": values, "basis": basis, "quote": quote}


# ---------------------------------------------------------------- C1 the score-in-quote bug


def test_score_in_quote_is_stripped():
    ln = _tok(["七", "sieben", "eight"], scores=[10.79, 10.75, 10.53])
    v = judge.verdict({"values": [7], "quote": "七 (10.79) |  sieben (10.75)"}, [7], [], [ln])
    assert v["kind"] == "hit"
    # before the fix: the bare-token plain text, the v1 checks (names_number / verbatim quote)
    plain = " | ".join(ln.pieces)
    q = "七 (10.79) |  sieben (10.75)"
    assert not judge.names_number(7, plain) and not quote_in(q, plain)


def test_prose_parenthetical_kept():
    s = "15 (Explanation: 30/2)"
    assert digest.quote_ok(s, [_prose(s)])
    assert judge.verdict({"values": [15], "quote": s}, [15], [], [_prose(s)])["kind"] == "hit"


def test_token_quote_across_lists_rejected():
    a = _tok(["twenty", "the"], pos=30)
    b = _tok(["six", "and"], pos=40)  # another cell, not adjacent: no split word either
    assert not digest.quote_ok("twenty | six", [a, b])
    v = judge.verdict({"values": [26], "quote": "twenty | six"}, [26], [], [a, b])
    assert v["kind"] == "unverified"


def test_fabricated_quote_rejected_even_when_value_in_line():
    """C1: the quote is checked by ``digest.quote_ok`` even when a line names the value."""
    ln = _tok(["七", "sieben", "eight"], scores=[10.79, 10.75, 10.53])
    for q in ("totally fabricated", "", "七 (99.00)"):
        assert not digest.quote_ok(q, [ln])
        v = judge.verdict({"values": [7], "quote": q}, [7], [], [ln])
        assert v["kind"] == "unverified" and not v["hit"]
    assert judge.verdict({"values": [7], "quote": "七 | sieben"}, [7], [], [ln])["kind"] == "hit"


def test_cross_line_quote_rejected_when_gold_in_a_line():
    a = _tok(["twenty-six", "the"], pos=30)
    b = _tok(["six", "and"], pos=40)
    assert not digest.quote_ok("the | six", [a, b])
    v = judge.verdict({"values": [26], "quote": "the | six"}, [26], [], [a, b])
    assert v["kind"] == "unverified"
    opts = [26, 13, 14, 15, 16, 17, 18, 19]
    for q, kind in (("the | six", "unverified"), ("made up", "unverified"), ("twenty-six", "hit")):
        mv = judge.summary_verdict_mc(
            {"choice": 1, "basis": "recurring_token", "quote": q}, 26, opts, [a, b], None
        )
        assert mv["kind"] == kind


def test_quote_must_hold_the_picked_value():
    """The quote shows the pick: a quote in one sample with the value named only in ANOTHER
    sample does not verify (native and summary MC); the same value in the quoted sample does."""
    off = Line(digest.sample_text("The model is thinking about apples."))
    on = Line(digest.sample_text("28 plus 3 is 31."))
    lines = [off, on]
    v = judge.verdict({"values": [31], "quote": "thinking about apples"}, [31], [], lines)
    assert v["kind"] == "unverified" and not v["hit"]
    assert judge.verdict({"values": [31], "quote": "28 plus 3 is 31"}, [31], [], lines)["hit"]
    opts = [31, 24, 25, 26, 27, 28, 29, 30]
    for q, kind in (("thinking about apples", "unverified"), ("28 plus 3 is 31", "hit")):
        mv = judge.summary_verdict_mc(
            {"choice": 1, "basis": "arithmetic", "quote": q}, 31, opts, lines, None
        )
        assert mv["kind"] == kind


def test_flood_void_reads_the_quoted_line():
    """``all_flood`` checks the quoted line: a quote from a number flood is ``flat`` even when
    another sample works the arithmetic to the gold; quoting the worked sample is a hit."""
    flood = Line(digest.sample_text("3, 4, 5, 6, 7, 31, 8, 9"))
    worked = Line(digest.sample_text("Adding 3 to 28 gives 31."))
    lines = [flood, worked]
    assert judge.verdict({"values": [31], "quote": "7, 31, 8"}, [31], [], lines)["kind"] == "flat"
    assert judge.verdict({"values": [31], "quote": "gives 31"}, [31], [], lines)["kind"] == "hit"


def test_multi_token_number_in_one_list_is_not_assembled():
    """Plan risk 4 (documented in the README): two tokens of ONE top-10 list never form a
    multi-digit value; only a single token naming the whole value counts."""
    ln = _tok(["二十", "六", "七", "的"])
    v = judge.verdict({"values": [26], "quote": "二十 | 六"}, [26], [], [ln])
    assert v["kind"] == "unverified"
    whole = _tok(["二十六", "七", "的"])
    assert judge.verdict({"values": [26], "quote": "二十六"}, [26], [], [whole])["hit"]


EN = {7: "seven", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
      16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen"}  # fmt: skip


def test_rescore_script_on_toy_run(tmp_path, monkeypatch):
    """Three v1 items whose cell shows the gold as a number WORD with its score; the judge
    quoted it with the score. Published (v1 check) fails all three; the fixed check passes."""
    import importlib.util

    from wsbench import llm

    def no_call(*a, **k):
        raise AssertionError("the rescore makes no LLM call")

    monkeypatch.setattr(llm, "stream_json", no_call)
    spec = importlib.util.spec_from_file_location(
        "rescore_chain_cached", REPO / "scripts/rescore_chain_cached.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _h, items = load_bank(BANK)
    three = [it for it in items if it["intermediates"][0] in EN][:3]
    rows, cells = [], []
    for it in three:
        g = it["intermediates"][0]
        rows.append({"id": it["id"], "layer": 44, "pos": 66, "tokens": [EN[g], "the", "and"],
                     "scores": [9.5, 2.0, 1.0]})  # fmt: skip
        cells.append({"key": f"{it['id']}|L044", "result": _res([g], f"{EN[g]} (9.50)"),
                      "meta": {"item": it["id"], "layer": 44, "pos": None}})  # fmt: skip
    ro = write_jsonl(tmp_path / "r.jsonl", rows)
    write_jsonl(tmp_path / "run" / "cells.jsonl", cells)
    res = mod.rescore(tmp_path / "run", ro)
    assert res["n_llm_calls"] == 0 and res["n_items"] == 3
    assert res["published"] == 0.0 and res["corrected"] == 1.0 and res["new_verdict"] == 1.0


# ---------------------------------------------------------------- C2 any language


def test_word_numeral_top_value_verified():
    v = judge.verdict(_res([18], "eighteen"), [18], [], [_prose("the result is eighteen")])
    assert v["kind"] == "hit"


def test_cjk_token_top_value_verified():
    v = judge.verdict(_res([18], "十八"), [18], [], [_tok(["十八", "eighteen"])])
    assert v["kind"] == "hit"


# ---------------------------------------------------------------- C3 the item-level null


def _items3():
    return [
        {"id": "a", "depth": 2, "start": 3, "answer": 30, "intermediates": [11]},
        {"id": "b", "depth": 2, "start": 4, "answer": 40, "intermediates": [12]},
        {"id": "c", "depth": 2, "start": 5, "answer": 50, "intermediates": [13]},
    ]


def test_perm_null_any_cell_scale():
    """Every item's cells name every bank intermediate as a top value (a stray small number
    shared across items): the any-cell headline is 1.0 and so is the null, net ~ 0."""
    items = _items3()
    vs = [
        {"item": it["id"], "judged": True, "hit": t == it["intermediates"][0], "top_ok": True,
         "values": [t], "kind": "hit" if t == it["intermediates"][0] else "other"}
        for it in items for t in (11, 12, 13)
    ]  # fmt: skip
    rows = [{"id": it["id"], "pass": True} for it in items]
    null = judge.perm_null(vs, rows, items)
    assert null["all"] == pytest.approx(1.0) and null["any"] == pytest.approx(1.0)


def test_perm_null_excludes_own_values():
    items = [
        *_items3(),
        {"id": "d", "depth": 2, "start": 6, "answer": 60, "intermediates": [3]},  # = a's start
        {"id": "e", "depth": 3, "start": 7, "answer": 70, "intermediates": [12, 14]},  # depth 3
    ]
    ps = {p["id"] for p in judge._partners(items[0], items, judge.PERM_SEED)}
    assert ps == {"b", "c"}


# ---------------------------------------------------------------- C11 bank v2


def test_bank_v2():
    import hashlib

    assert registry.bank_path("chain_intermediates").name == "items_v2.json"
    header, items = load_bank(BANK_V2)
    assert header["version"] == 2 and header["supersedes"] == "items.json"
    assert len(items) == 120
    assert sum(it["depth"] == 2 for it in items) == 84
    assert sum(it["depth"] == 3 for it in items) == 36
    for it in items:
        assert all(10 <= v <= 99 for v in it["intermediates"]), it["id"]
        assert len(it["mc"]) == len(it["intermediates"])
        for slot in it["mc"]:
            assert not mcopt.check_slot(it, slot), (it["id"], mcopt.check_slot(it, slot))
            assert slot["gold"] not in {it["start"], it["answer"], *it["literals"]}
        assert all(v not in it["literals"] for v in it["intermediates"])  # the leak rule
    assert hashlib.sha256(BANK.read_bytes()).hexdigest() == V1_SHA
    # kept items are byte-identical to v1 except the mc block
    _h, v1 = load_bank(BANK)
    v1_by = {it["id"]: it for it in v1}
    kept = [it for it in items if it["id"] in v1_by]
    assert len(kept) == 83
    for it in kept:
        assert {k: v for k, v in it.items() if k != "mc"} == v1_by[it["id"]]


def test_options_balanced():
    _h, items = load_bank(BANK_V2)
    slots = [s for it in items for s in it["mc"]]
    assert len(slots) == 156
    counts = [0] * mcopt.N_OPTIONS
    for s in slots:
        counts[mcopt.sorted_rank(s)] += 1
    assert max(counts) <= mcopt.MAX_RANK_SHARE * len(slots), counts


def test_mc_options_exclude_start_answer_literals_other_gold():
    _h, items = load_bank(BANK_V2)
    for it in items:
        for s in it["mc"]:
            others = set(it["intermediates"]) - {s["gold"]}
            bad = {it["start"], it["answer"], *it["literals"], *others}
            assert not bad & set(s["options"]), it["id"]
            assert len(set(s["options"])) == 8 and s["options"].count(s["gold"]) == 1


# ---------------------------------------------------------------- C5 the MC judge (fake LLM)


D3 = {  # the worked depth-3 item of plan 0038 C6: 30 -> 15 -> 45 -> 41
    "name": "chain-t-d3-0001", "depth": 3, "cond": False,
    "kinds": ["halve_down", "triple", "sub"],
    "steps": ["Halve it, rounding down.", "Multiply it by 3.", "Subtract 4."],
    "start": 30, "intermediates": [15, 45], "untaken": [None, None], "answer": 41,
    "literals": [3, 4, 30], "distractors": [[30, 41, 14, 16], [30, 41, 44, 46]],
}  # fmt: skip
D2 = {
    "name": "chain-t-d2-0002", "depth": 2, "cond": False, "kinds": ["add", "double"],
    "steps": ["Add 5.", "Double it."], "start": 7, "intermediates": [12], "untaken": [None],
    "answer": 24, "literals": [5, 7], "distractors": [[7, 24, 11, 13]],
}  # fmt: skip
D3B = {  # a same-depth partner for the null
    "name": "chain-t-d3-0003", "depth": 3, "cond": False, "kinds": ["add", "add", "add"],
    "steps": ["Add 9.", "Add 9.", "Add 9."], "start": 2, "intermediates": [11, 20],
    "untaken": [None, None], "answer": 29, "literals": [2, 9],
    "distractors": [[2, 29, 10, 12], [2, 29, 19, 21]],
}  # fmt: skip
D2B = {
    "name": "chain-t-d2-0004", "depth": 2, "cond": False, "kinds": ["triple", "add"],
    "steps": ["Multiply it by 3.", "Add 2."], "start": 9, "intermediates": [27],
    "untaken": [None], "answer": 29, "literals": [2, 3, 9], "distractors": [[9, 29, 26, 28]],
}  # fmt: skip


def _render(it):
    steps = "\n".join(it["steps"])
    return (
        "Apply the steps below, in order, to the starting number given at the end.\n"
        f"{steps}\nThe starting number is {it['start']}. What is the final number? "
        "Reply with only the final number, nothing else."
    )


_MC = {  # first option = the gold; no option is the null partner's start, answer or gold
    "chain-t-d3-0001": [[15, 16, 13, 14, 17, 18, 19, 21], [45, 44, 46, 40, 42, 47, 48, 50]],
    "chain-t-d2-0002": [[12, 13, 10, 11, 14, 16, 17, 18]],
    "chain-t-d3-0003": [[11, 10, 12, 13, 14, 16, 17, 18], [20, 19, 21, 22, 23, 24, 25, 26]],
    "chain-t-d2-0004": [[27, 25, 26, 28, 30, 31, 32, 33]],
}


@pytest.fixture
def toy_v2(tmp_path, monkeypatch):
    """A 4-item v2-shaped bank (mc blocks from the real builder), pinned for the family."""
    import copy

    items = [copy.deepcopy(x) for x in (D3, D2, D3B, D2B)]
    for it in items:
        it["prompt"] = _render(it)
        it["prompt_first"] = it["prompt"]
    for it in items:  # hand-set so every item has a same-depth null partner (see _MC)
        it["mc"] = [{"slot": k, "gold": o[0], "options": o} for k, o in enumerate(_MC[it["name"]])]
    path = tmp_path / "items_v2.json"
    path.write_text(json.dumps({"family": "chain_intermediates", "version": 2, "items": items}))
    monkeypatch.setenv("WSB_BANK_FILE_CHAIN_INTERMEDIATES", str(path))
    return {it["name"]: it for it in items}


def _numbers_digest(user: str) -> dict:
    """A numbers digest: per bundle sample, its first numeral (any language) as the key, the
    whole sample as the evidence; at most five."""
    out = []
    for ln in [x[2:] for x in user.splitlines() if x.startswith("- ")]:
        toks = numerals.tokens(ln)
        if not toks or len(out) >= 5:
            continue
        s, e, _v, _k = toks[0]
        key = numerals.fold(ln)[s:e]
        out.append({"statement": "s", "key": key, "where": "", "evidence": ln})
    return {"items": out, "rare": []}


def _cell_rows(iid, texts, layers=(20, 24), first=30):
    """Contiguous full reads (>= 20 positions) for one item: ``texts[(layer, pos)]`` or filler."""
    return [
        {"id": iid, "layer": L, "pos": p, "samples": [texts.get((L, p), "nothing of note here")]}
        for L in layers
        for p in range(first, first + 20)
    ]


def _mc_answer(item, slot_pick):
    """A judge that picks ``slot_pick(item_name, slot_gold, options) -> option value | None``."""

    def judge_fn(system, user, schema):
        assert schema["name"] == "chain_mc" and system == cp.SYSTEM_MC
        opts = [int(x) for x in re.findall(r"^\s+\d+\. (\d+)$", user, flags=re.M)]
        pick = slot_pick(user, opts)
        if pick is None:
            return {"choice": len(opts) + 1, "basis": "none", "quote": ""}
        return {"choice": opts.index(pick) + 1, "basis": "stated_result", "quote": str(pick)}

    return judge_fn


def _run_mc(tmp_path, rows, items, **kw):
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    return spec_run(summary_args(path, tmp_path / "o", cp.PROMPT_VERSION, items=items, **kw))


def spec_run(args):
    from wsbench.evals.chain_intermediates import SPEC

    return SPEC.run(args)


def _gold_in_user(golds):
    """Pick the slot's gold when the readout (the digest) shows it, else cannot tell."""

    def pick(user, opts):
        ro = user.split("Readouts:", 1)[1].split("Candidates:", 1)[0]
        for g in golds:
            if g in opts and numerals.names_value(g, ro):
                return g
        return None

    return pick


def test_mc_one_call_per_slot(tmp_path, monkeypatch, toy_v2):
    rows = _cell_rows("chain-t-d3-0001", {(20, 31): "the value is 15"}) + _cell_rows(
        "chain-t-d2-0002", {(20, 31): "the value is 12"}
    )
    fake = FakeLLM.install(
        monkeypatch, _mc_answer(None, _gold_in_user([15, 45, 12])), digest=_numbers_digest
    )
    r = _run_mc(tmp_path, rows, ["chain-t-d3-0001", "chain-t-d2-0002"], extra={"null": "off"})
    assert fake.n("digest") == 2 and fake.n("chain_mc") == 3  # 2 slots + 1 slot
    assert r.extras["n_calls"] == 3 and r.extras["n_null_calls"] == 0
    for _n, _s, user in (c for c in fake.calls if c[0] == "chain_mc"):
        lines = re.findall(r"^\s+(\d+)\. (.*)$", user, flags=re.M)
        assert len(lines) == 9 and lines[-1][1] == mc.CANNOT


def test_mc_cannot_tell_is_last_and_negative(tmp_path, monkeypatch, toy_v2):
    rows = _cell_rows("chain-t-d2-0002", {(20, 31): "the value is 12"})
    FakeLLM.install(monkeypatch, _mc_answer(None, lambda u, o: None), digest=_numbers_digest)
    r = _run_mc(tmp_path, rows, ["chain-t-d2-0002"], extra={"null": "off"})
    row = r.rows[0]
    assert row["slots"][0]["kind"] == "cannot_tell" and row["pass"] is False
    assert judge.shown_options([1, 2])[-1] == mc.CANNOT


def test_mc_gold_pick_needs_evidence():
    v = judge.summary_verdict_mc(
        {"choice": 1, "basis": "stated_result", "quote": "12"},
        12,
        [12, 13, 14, 15, 16, 17, 18, 19],
        [_prose("the value is 13")],
        None,
    )
    assert v["kind"] == "unverified" and not v["hit"]


def test_mc_gold_must_be_digest_key():
    lines = [_prose("the value is 12"), _prose("and 13 too")]
    res = {"choice": 1, "basis": "stated_result", "quote": "12"}
    opts = [12, 13, 14, 15, 16, 17, 18, 19]
    assert judge.summary_verdict_mc(res, 12, opts, lines, ["13"])["kind"] == "not_key"
    assert judge.summary_verdict_mc(res, 12, opts, lines, ["12"])["kind"] == "hit"


def test_mc_null_shuffled_uses_partner_digest(tmp_path, monkeypatch, toy_v2):
    rows = (
        _cell_rows("chain-t-d3-0001", {(20, 31): "halving gives 15", (24, 31): "then 45"})
        + _cell_rows("chain-t-d3-0003", {(20, 31): "PARTNER says 11 and 20"})
        + _cell_rows("chain-t-d2-0002", {(20, 31): "the value is 12"})
        + _cell_rows("chain-t-d2-0004", {(20, 31): "PARTNER says 27"})
    )
    fake = FakeLLM.install(
        monkeypatch, _mc_answer(None, _gold_in_user([15, 45, 12, 11, 20, 27])),
        digest=_numbers_digest,
    )  # fmt: skip
    r = _run_mc(tmp_path, rows, list(toy_v2))
    rows_ = {x["id"]: x for x in r.rows}
    a = rows_["chain-t-d3-0001"]
    assert a["null_partners"] == ["chain-t-d3-0003", "chain-t-d3-0003"]
    null_users = [u for n, _s, u in fake.calls if n == "chain_mc" and "PARTNER" in u]
    assert null_users and r.extras["n_null_calls"] == 6
    # the partner's digest never states 15 / 45: the null for a's slots is a miss
    assert a["null_slots"] == [False, False]
    assert r.extras["null_shuffled"] == 0.0 and r.extras["net"] == r.value


def test_system_mc_interpolates_shared_token_note():
    spec = registry.FAMILIES["chain_intermediates"]
    want = mc.token_note(spec.flat_types, multi_select=spec.multi_select)
    assert want in cp.SYSTEM_MC and want in cp.SYSTEM
    assert mc.token_note() not in cp.SYSTEM_MC and mc.READOUT_PHRASE in cp.SYSTEM_MC
    assert spec.flat_types == ("numbers",) and spec.multi_select is False


def test_mc_token_quote_same_list_only():
    a = _tok(["twenty", "the"], pos=30)
    b = _tok(["six", "and"], pos=40)
    assert not digest.quote_ok("twenty | six", [a, b])
    v = judge.summary_verdict_mc(
        {"choice": 1, "basis": "recurring_token", "quote": "twenty | six"},
        26,
        [26, 13, 14, 15, 16, 17, 18, 19],
        [a, b],
        None,
    )
    assert v["kind"] == "unverified"


def test_digits_never_assembled_across_positions():
    lines = [_tok(["2", "the"], pos=30), _tok(["6", "and"], pos=31)]
    assert digest.quote_ok("26", lines)  # the shared verifier spells it across positions
    v = judge.summary_verdict_mc(
        {"choice": 1, "basis": "recurring_token", "quote": "26"},
        26,
        [26, 13, 14, 15, 16, 17, 18, 19],
        lines,
        None,
    )
    assert v["kind"] == "unverified"


def test_chain_system_prompt_item_free():
    _h, items = load_bank(BANK_V2)
    for it in items:
        for slot in judge.mc_options(it):
            shown = judge.shown_options(slot)
            assert str(it["start"]) not in shown and str(it["answer"]) not in shown
    digits = set(re.findall(r"\d+", cp.SYSTEM_MC))
    assert digits <= {"7", "16", "2", "14"}, digits
    assert set(re.findall(r"\d+", cp.SYSTEM)) <= {"16", "2", "14", "0", "1", "3", "7"}


# ---------------------------------------------------------------- C6 flat lists


def test_flat_digit_bag_is_not_a_hit():
    """Audit case tuned-chain-d2p-0200-L44: a uniform 0-9 bag, the judge's top value 6 is the
    rank-1 token AND the gold: flat, not a hit."""
    bag = _tok(["6", "1", "8", "2", "3", "9", "5", "0", "4", "7"])
    v = judge.verdict(_res([6, 1, 8], "6", "numeral_bag"), [6], [], [bag])
    assert v["kind"] == "flat" and not v["hit"]


def test_flat_line_void_in_summary():
    ln = _tok(["equal", "twelve", "six", "eight", "seven", "eleven", "nine"])
    v = judge.summary_verdict_mc(
        {"choice": 1, "basis": "recurring_token", "quote": "twelve"},
        12,
        [12, 13, 14, 15, 16, 17, 18, 19],
        [ln],
        ["twelve"],
    )
    assert v["kind"] == "flat" and not v["hit"]


def test_word_numeral_flood_counts():
    assert digest.number_flood(_tok(["sieben", "acht", "neun", "zehn", "elf"]))


WORKED = "- Halving 30 gives 15\n- 15 times 3 is 45\n- 45 minus 4 equals 41"


def test_worked_multistep_s3d_sample_passes(tmp_path, monkeypatch, toy_v2):
    ln = _prose(WORKED)
    assert ln.text == "Halving 30 gives 15 ⁞ 15 times 3 is 45 ⁞ 45 minus 4 equals 41"
    assert not digest.number_flood(ln)
    # native: same sample
    assert judge.verdict(_res([15], "Halving 30 gives 15"), [15, 45], [], [ln])["kind"] == "hit"
    # summary MC end to end, strict all-intermediates rule
    rows = _cell_rows("chain-t-d3-0001", {(20, 31): WORKED})
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    write_sidecar(path, reader="t", arm="s3d-rl600", sampling="prose1")

    def pick(user, opts):
        if 15 in opts:
            return 15
        return 45 if 45 in opts else None

    def judge_fn(system, user, schema):
        opts = [int(x) for x in re.findall(r"^\s+\d+\. (\d+)$", user, flags=re.M)]
        g = pick(user, opts)
        q = "Halving 30 gives 15" if g == 15 else "15 times 3 is 45"
        return {"choice": opts.index(g) + 1, "basis": "stated_result", "quote": q}

    def dig(user):
        ln_ = next(x[2:] for x in user.splitlines() if x.startswith("- Halving"))
        entry = {"statement": "s", "where": "", "evidence": ln_}
        return {"items": [{**entry, "key": "15"}, {**entry, "key": "45"}]}

    FakeLLM.install(monkeypatch, judge_fn, digest=dig)
    r = spec_run(
        summary_args(path, tmp_path / "o", cp.PROMPT_VERSION, items=["chain-t-d3-0001"],
                     layers=[20, 24], extra={"null": "off"})
    )  # fmt: skip
    row = r.rows[0]
    assert [s["kind"] for s in row["slots"]] == ["hit", "hit"] and row["pass"] is True


def test_comma_number_list_sample_is_flat():
    ln = _prose("Possible values: 12, 15, 17, 19, 23")
    v = judge.summary_verdict_mc(
        {"choice": 2, "basis": "stated_result", "quote": "15"},
        15,
        [12, 15, 14, 16, 18, 19, 20, 21],
        [ln],
        ["15"],
    )
    assert v["kind"] == "flat"


def test_bulleted_number_list_sample_is_flat():
    flood = _prose("- 12\n- 15\n- 17\n- 19\n- 23")
    assert flood.text == "12 ⁞ 15 ⁞ 17 ⁞ 19 ⁞ 23"
    opts = [12, 15, 14, 16, 18, 19, 20, 21]
    res = {"choice": 2, "basis": "stated_result", "quote": "15"}
    assert judge.summary_verdict_mc(res, 15, opts, [flood], ["15"])["kind"] == "flat"
    assert judge.verdict(_res([15], "15"), [15], [], [flood])["kind"] == "flat"
    worded = _prose("- 12\n- Halving 30 gives 15\n- 17\n- 19\n- 23")
    assert not digest.number_flood(worded)
    assert judge.summary_verdict_mc(res, 15, opts, [worded], ["15"])["kind"] == "hit"
    assert judge.verdict(_res([15], "15"), [15], [], [worded])["kind"] == "hit"


def test_by_gold_size_buckets():
    items = [
        {"id": "a", "depth": 2, "start": 3, "answer": 30, "intermediates": [7]},
        {"id": "b", "depth": 2, "start": 4, "answer": 40, "intermediates": [12]},
        {"id": "c", "depth": 3, "start": 5, "answer": 50, "intermediates": [25, 13]},
    ]
    rows = [
        {"id": "a", "pass": True, "all_slots": True, "any_slot": True, "slot_hits": [True],
         "depth": 2},
        {"id": "b", "pass": False, "all_slots": False, "any_slot": False, "slot_hits": [False],
         "depth": 2},
        {"id": "c", "pass": False, "all_slots": False, "any_slot": True,
         "slot_hits": [True, False], "depth": 3},
    ]  # fmt: skip
    cols = judge._columns(
        rows, items, null_all=0.1, null_any=0.2, null_slot={0: 0.1, 1: 0.0},
        null_size={"1-9": 0.5, "10-19": 0.0, "20+": 0.25},
    )  # fmt: skip
    by = cols["by_gold_size"]
    assert by["1-9"] == {"n": 1, "value": 1.0, "null": 0.5, "net": 0.5}
    assert by["10-19"]["n"] == 2 and by["10-19"]["value"] == 0.0
    assert by["20+"] == {"n": 1, "value": 1.0, "null": 0.25, "net": 0.75}
    assert judge.size_bucket(9) == "1-9" and judge.size_bucket(10) == "10-19"


# ---------------------------------------------------------------- C10 all intermediates


def test_depth3_requires_both_slots(tmp_path, monkeypatch, toy_v2):
    # native: a hit on the first intermediate only
    it = {"id": "x", "depth": 3, "intermediates": [15, 45], "start": 30, "answer": 41}
    vs = [{"item": "x", "layer": 20, "pos": 3, "kind": "hit", "values": [15], "hit": True,
           "judged": True, "top_ok": True}]  # fmt: skip
    row = judge._item_row(it, [15, 45], [], vs, [], set(), "all")
    assert row["pass"] is False and row["any_slot"] is True and row["slot_hits"] == [True, False]
    vs.append({**vs[0], "layer": 24, "values": [45]})
    assert judge._item_row(it, [15, 45], [], vs, [], set(), "all")["pass"] is True
    # summary MC: only slot 1's gold is stated
    rows = _cell_rows("chain-t-d3-0001", {(20, 31): "halving gives 15"})
    FakeLLM.install(monkeypatch, _mc_answer(None, _gold_in_user([15, 45])), digest=_numbers_digest)
    r = _run_mc(tmp_path, rows, ["chain-t-d3-0001"], extra={"null": "off"})
    row = r.rows[0]
    assert row["slot_hits"] == [True, False] and row["pass"] is False and row["any_slot"] is True
    r_any = _run_mc(tmp_path / "any", rows, ["chain-t-d3-0001"],
                    extra={"null": "off", "rule": "any"})  # fmt: skip
    assert r_any.rows[0]["pass"] is True
    assert r_any.config["prompt_version"].endswith("+rule-any")


def test_any_slot_column(tmp_path, monkeypatch, toy_v2):
    rows = _cell_rows("chain-t-d3-0001", {(20, 31): "halving gives 15"}) + _cell_rows(
        "chain-t-d2-0002", {(20, 31): "nothing"}
    )
    FakeLLM.install(monkeypatch, _mc_answer(None, _gold_in_user([15, 45, 12])),
                    digest=_numbers_digest)  # fmt: skip
    r = _run_mc(tmp_path, rows, ["chain-t-d3-0001", "chain-t-d2-0002"], extra={"null": "off"})
    assert r.value == 0.0 and r.extras["any_slot"] == 0.5


def test_per_slot_columns(tmp_path, monkeypatch, toy_v2):
    rows = _cell_rows("chain-t-d3-0001", {(20, 31): "then 45"}) + _cell_rows(
        "chain-t-d2-0002", {(20, 31): "the value is 12"}
    )
    FakeLLM.install(monkeypatch, _mc_answer(None, _gold_in_user([15, 45, 12])),
                    digest=_numbers_digest)  # fmt: skip
    r = _run_mc(tmp_path, rows, ["chain-t-d3-0001", "chain-t-d2-0002"], extra={"null": "off"})
    ps = r.extras["per_slot"]
    assert ps["first"]["n"] == 2 and ps["first"]["value"] == 0.5  # d3 slot 1 miss, d2 hit
    assert ps["second"]["n"] == 1 and ps["second"]["value"] == 1.0
    assert r.extras["per_depth"] == {"2": 1.0, "3": 0.0}


# ---------------------------------------------------------------- C4, C8, C12, C13, C16


def test_prompt_only_file_judged_like_a_lens(tmp_path, monkeypatch, toy_v2):
    ids = ["chain-t-d3-0001", "chain-t-d2-0002"]
    po = [{"id": i, "layer": 44, "pos": 60, "samples": [f"so the value is {g}"]}
          for i, g in (("chain-t-d3-0001", 15), ("chain-t-d2-0002", 12))]  # fmt: skip
    p_po = write_jsonl(tmp_path / "po" / "chain_intermediates.jsonl", po)
    write_sidecar(p_po, reader="prompt_only:claude-opus-5-5", layers=[44], protocol="po-opus-v1")
    lens = [r for i in ids for r in _cell_rows(i, {(20, 31): "the value is 15 and 12"})]
    p_lens = write_jsonl(tmp_path / "lens" / "chain_intermediates.jsonl", lens)
    fake = FakeLLM.install(
        monkeypatch, _mc_answer(None, _gold_in_user([15, 45, 12])), digest=_numbers_digest
    )
    a = spec_run(summary_args(p_po, tmp_path / "o1", cp.PROMPT_VERSION, items=ids))
    systems = {s for n, s, _u in fake.calls if n == "chain_mc"}
    b = spec_run(summary_args(p_lens, tmp_path / "o2", cp.PROMPT_VERSION, items=ids))
    assert systems == {cp.SYSTEM_MC} and fake.n("digest") == 4
    assert a.config["reads_checked"] == "prompt_only"
    assert reads.strip_reads(a.config["prompt_version"]) == reads.strip_reads(
        b.config["prompt_version"]
    )


def test_summary_gets_every_position_and_layer(tmp_path, monkeypatch, toy_v2):
    layers = (20, 24, 28)
    rows = [
        {"id": "chain-t-d2-0002", "layer": L, "pos": p, "samples": [f"s L{L} p{p}"]}
        for L in layers
        for p in range(40, 67)
    ]
    fake = FakeLLM.install(monkeypatch, _mc_answer(None, lambda u, o: None),
                           digest=_numbers_digest)  # fmt: skip
    r = _run_mc(tmp_path, rows, ["chain-t-d2-0002"], extra={"null": "off"})
    (user,) = [u for n, _s, u in fake.calls if n == "digest"]
    for layer in layers:
        for p in range(40, 67):
            assert f"[L{layer} pos {p}]" in user
    assert r.extras["summary"]["n_truncated_items"] == 0
    assert r.extras["summary"]["n_readouts_in"] == r.extras["summary"]["n_readouts_bundled"] == 81


def test_reads_full_rejects_v1_span_file(tmp_path, monkeypatch):
    """A v1-plan file (25 positions from " What", no v2 replacement ids): with a v1 sidecar it
    exits 2 on plan_sha; sidecar-less, the missing v2 ids exit 2, and under allow_missing the
    run is incomplete and its unenforced partial ids are reported."""
    _h, v2 = load_bank(BANK_V2)
    kept = [it["id"] for it in v2 if not it["id"].startswith("chain-v2-")]
    rows = [
        {"id": i, "layer": L, "pos": p, "samples": ["x"]}
        for i in kept[:3]
        for L in readplan_grid()
        for p in range(50, 75)
    ]
    path = write_jsonl(tmp_path / "chain_intermediates.jsonl", rows)
    write_sidecar(path, reader="t", arm="t", plan_sha="0" * 64)
    args = summary_args(path, tmp_path / "o", cp.PROMPT_VERSION, extra={"null": "off"})
    with pytest.raises(SystemExit):
        spec_run(args)
    (tmp_path / "chain_intermediates.jsonl.meta.json").unlink()
    with pytest.raises(SystemExit) as e:
        spec_run(summary_args(path, tmp_path / "o2", cp.PROMPT_VERSION))
    assert e.value.code == 2
    _cells, rep = reads.load(
        native_args(readouts=path, out=tmp_path / "o3",
                    judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)), layers=None,
                    items=None, limit=0, allow_missing=True, concurrency=1, rpm=1.0,
                    dry_run=True),
        "chain_intermediates",
    )  # fmt: skip
    assert rep.reads_checked == "no_sidecar"
    short = [{**r, "pos": r["pos"]} for r in rows if r["pos"] >= 60]  # 15 < 20 positions
    p2 = write_jsonl(tmp_path / "s" / "chain_intermediates.jsonl", short)
    _cells, rep = reads.load(
        native_args(readouts=p2, out=tmp_path / "o4",
                    judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)), layers=None,
                    items=None, limit=0, allow_missing=True, concurrency=1, rpm=1.0,
                    dry_run=True),
        "chain_intermediates",
    )  # fmt: skip
    assert set(rep.partial_ids_unenforced) == set(kept[:3])


def readplan_grid():
    from wsbench import readplan

    return readplan.GRID


def test_chain_arbitrary_layers(tmp_path, monkeypatch, toy_v2):
    rows = _cell_rows("chain-t-d2-0002", {(17, 31): "the value is 12"}, layers=(3, 17, 50))
    FakeLLM.install(monkeypatch, _mc_answer(None, _gold_in_user([12])), digest=_numbers_digest)
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    r = spec_run(
        summary_args(path, tmp_path / "o", cp.PROMPT_VERSION, items=["chain-t-d2-0002"],
                     layers=[3, 17, 50], extra={"null": "off"})
    )  # fmt: skip
    assert r.config["layers_judged"] == [3, 17, 50] and not r.extras.get("layers_missing")
    assert r.value == 1.0


def test_chain_config_carries_sampling(tmp_path, monkeypatch, toy_v2):
    rows = _cell_rows("chain-t-d2-0002", {(20, 31): "the value is 12"})
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    write_sidecar(path, reader="s3d-rl600", arm="s3d-rl600", sampling="prose1",
                  plan_sha=reads.plan_sha("chain_intermediates"), layers=[20, 24])  # fmt: skip
    FakeLLM.install(monkeypatch, _mc_answer(None, _gold_in_user([12])), digest=_numbers_digest)
    r = spec_run(
        summary_args(path, tmp_path / "o", cp.PROMPT_VERSION, items=["chain-t-d2-0002"],
                     layers=[20, 24], extra={"null": "off"})
    )  # fmt: skip
    assert r.config["sampling"] == "prose1" and r.config["sampling_source"] == "declared"
    assert r.config["reads_checked"] == "sidecar"


def test_chain_quote_across_bullet_mark_verifies():
    ln = _prose(WORKED)
    assert digest.quote_ok("15 15 times 3", [ln])
    v = judge.verdict(_res([15], "15 15 times 3"), [15], [], [ln])
    assert v["kind"] == "hit"


def test_cells_last_is_retired(tmp_path, toy_v2):
    path = write_jsonl(tmp_path / "r.jsonl", _cell_rows("chain-t-d2-0002", {}))
    for extra in ({"cells": "last"}, {"cells": "all", "reads": "lite"}):
        with pytest.raises(SystemExit) as e:
            spec_run(summary_args(path, tmp_path / "o", cp.PROMPT_VERSION, extra=extra))
        assert e.value.code == 2


def test_native_lite_judges_final_token_per_layer(tmp_path, monkeypatch, toy_v2):
    rows = _cell_rows("chain-t-d2-0002", {(20, 49): "the value is 12"})
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    seen = []

    def fake_run_calls(calls, **kw):
        seen.extend(calls)
        return {c.key: _res([12], "12") if "12" in c.user else _res([]) for c in calls}

    monkeypatch.setattr(judge, "run_calls", fake_run_calls)
    args = native_args(readouts=path, out=tmp_path / "o",
                       judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)), layers=None,
                       items=["chain-t-d2-0002"], limit=0, allow_missing=False, concurrency=1,
                       rpm=1.0, dry_run=False, extra={"reads": "lite"})  # fmt: skip
    r = judge.run(args)
    assert {(c.meta["layer"], c.meta["pos"]) for c in seen} == {(20, 49), (24, 49)}
    assert r.value == 1.0 and r.config["prompt_version"] == cp.NATIVE_PROMPT_VERSION + "+reads-lite"
    assert "null_perm_any_cell" in r.extras and "net" in r.extras

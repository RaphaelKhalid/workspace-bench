"""Round 5 "common" banks (basic_readout v6, association v4): the Qwen >= 8/10 gate rule, the
read-plan reuse rule (``readplan.READ_PLAN_BANK``) and the shipped banks' invariants (lists only
grow; texts unchanged), each tested in both directions. No API call."""

import importlib.util
import json
from pathlib import Path

import pytest

from wsbench import readplan
from wsbench.banks import load_bank

REPO = Path(__file__).resolve().parents[1]
NEW = {
    "basic_readout": ("evals/basic_readout/items_v5.json", "evals/basic_readout/items_v6.json"),
    "association": ("evals/association/items_v3.json", "evals/association/items_v4.json"),
}


@pytest.fixture(scope="module")
def cc():
    spec = importlib.util.spec_from_file_location(
        "common_confusers_r5", REPO / "scripts/common_confusers_r5.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_gate_keeps_at_eight_of_ten(cc):
    assert cc.verdict("basic_readout", 8, {"apple": 8, "pear": 2}) == ("keep", "")
    assert cc.verdict("association", 10, {"chess": 10}) == ("keep", "")


def test_gate_drops_below_eight(cc):
    assert cc.verdict("basic_readout", 7, {"Piano": 7, "Guitar": 3}) == ("drop", "")
    assert cc.verdict("association", 7, {"Dentist": 7, "Dental exam": 3}) == ("drop", "")


def test_gate_rekeys_only_implicit_and_only_at_eight(cc):
    assert cc.verdict("basic_readout", 1, {"Rust": 8, "Python": 1, "": 1}) == ("rekey", "Rust")
    assert cc.verdict("basic_readout", 1, {"Rust": 7, "Python": 1, "": 2}) == ("drop", "")
    assert cc.verdict("basic_readout", 0, {"": 10}) == ("drop", "")  # empty answers never re-key
    assert cc.verdict("association", 0, {"Santa Claus": 10}) == ("drop", "")


def _bank(tmp_path: Path, name: str, items: list[dict], **header) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps({**header, "items": items}), encoding="utf-8")
    return p


def _it(name: str, prompt: str, gold: str = "apple") -> dict:
    return {"name": name, "prompt": prompt, "mc": {"gold": gold, "distractors": ["pear"]}}


def test_read_plan_bank_serves_the_earlier_plan(tmp_path):
    old = [_it("a", "What is your favorite fruit?"), _it("b", "Your favorite color?")]
    _bank(tmp_path, "items_v1.json", old)
    sub = [{**old[0], "mc": {"gold": "apple", "distractors": ["pear", "banana", "grape"]}}]
    p = _bank(tmp_path, "items_v2.json", sub, read_plan_bank="items_v1.json")
    h, items = load_bank(p)
    got = readplan.read_plan_items(p, h, items)
    assert [it["name"] for it in got] == ["a", "b"]  # the earlier bank's rows, not the subset


def test_read_plan_bank_refuses_a_changed_text(tmp_path):
    _bank(tmp_path, "items_v1.json", [_it("a", "What is your favorite fruit?")])
    p = _bank(
        tmp_path,
        "items_v2.json",
        [_it("a", "What is your favourite fruit?")],
        read_plan_bank="items_v1.json",
    )
    h, items = load_bank(p)
    with pytest.raises(ValueError, match="differs from its read plan bank"):
        readplan.read_plan_items(p, h, items)


def test_read_plan_bank_refuses_a_new_item(tmp_path):
    _bank(tmp_path, "items_v1.json", [_it("a", "What is your favorite fruit?")])
    p = _bank(
        tmp_path,
        "items_v2.json",
        [_it("a", "What is your favorite fruit?"), _it("z", "Your favorite tree?")],
        read_plan_bank="items_v1.json",
    )
    h, items = load_bank(p)
    with pytest.raises(ValueError, match="is not in its read plan bank"):
        readplan.read_plan_items(p, h, items)


@pytest.mark.parametrize("family", sorted(NEW))
def test_new_bank_plan_equals_old_bank_plan(family, monkeypatch):
    old, new = NEW[family]
    monkeypatch.setenv(f"WSB_BANK_FILE_{family.upper()}", old)
    before = [s.row() for s in readplan.plan(family)]
    monkeypatch.setenv(f"WSB_BANK_FILE_{family.upper()}", new)
    after = [s.row() for s in readplan.plan(family)]
    assert before and after == before  # one read, one plan_sha: no new readouts


@pytest.mark.parametrize("family", sorted(NEW))
def test_lists_only_grow_and_texts_stay(family, cc):
    old, new = NEW[family]
    _ho, o = load_bank(REPO / old)
    hn, n = load_bank(REPO / new)
    by = {it["id"]: it for it in o}
    assert hn["read_plan_bank"] == Path(old).name
    assert set(hn["common_confusers"]["dropped_by_gate"]) == {
        it["name"] for it in o if it["id"] not in {x["id"] for x in n}
    }
    grown = 0
    for it in n:
        prev = by[it["id"]]
        assert it["prompt"] == prev["prompt"] and it["mc"]["gold"] == prev["mc"]["gold"]
        assert it["mc"]["distractors"][: len(prev["mc"]["distractors"])] == list(
            prev["mc"]["distractors"]
        )  # every earlier option (judge-picked confusers included) stays, in place
        added = it["mc"].get("common_confusers")
        if added is None:
            assert not cc.in_scope(family, it)
            assert it["mc"]["distractors"] == prev["mc"]["distractors"]
            continue
        grown += 1
        assert it["mc"]["distractors"][len(prev["mc"]["distractors"]) :] == added
        assert it["gate_r5"]["correct"] >= cc.GATE_MIN and it["gate_r5"]["n"] == cc.GATE_N
        if len(added) < cc.MIN_ADD:  # only a closed topic that ran dry
            assert it["name"] in hn["common_confusers"]["short_lists"]
    assert grown == hn["common_confusers"]["n_changed"] > 0


def test_basic_judge_letters_cover_grown_lists():
    from wsbench.basic.mcjudge_basic import BR_CANNOT, LETTERS, options_for

    _h, items = load_bank(REPO / NEW["basic_readout"][1])
    grown = [it for it in items if "common_confusers" in it["mc"]]
    for it in grown:
        opts = options_for(it, pv="v", cannot=BR_CANNOT)
        assert opts.shown[-1] == BR_CANNOT and len(opts.shown) <= len(LETTERS)
        assert opts.lettered().splitlines()[-1].startswith(f"{LETTERS[len(opts.shown) - 1]}. ")
    # a bank-v5 five-option list still renders A-F, exactly as before
    _h5, v5 = load_bank(REPO / NEW["basic_readout"][0])
    assert [
        ln[0] for ln in options_for(v5[0], pv="v", cannot=BR_CANNOT).lettered().split("\n")
    ] == (list("ABCDEF"))


def test_basic_judge_refuses_a_list_longer_than_its_letters():
    from wsbench.basic.mcjudge_basic import BR_CANNOT, LETTERS, options_for

    it = {"id": "x", "mc": {"gold": "g", "distractors": [f"d{i}" for i in range(len(LETTERS))]}}
    with pytest.raises(SystemExit):
        options_for(it, pv="v", cannot=BR_CANNOT)

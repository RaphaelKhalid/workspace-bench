# ruff: noqa: RUF001
"""Review of PR #208 (round 4b), BLOCKING 2: basic_readout_mt ``brh-ent-cur-ouguiya-subunit`` L20
still passed on bank v4 (4 vs 1). Its digest holds "[4 samples] ... five dirhams make one
ouguiya's worth", tying the gold khoums line at 4; bank v2 listed "dirhams", so the code
option-rival check (a tie is contested) caught it, but the round-4 / 4b leakage redraws dropped
it. Restoring it to the shown list re-opens the leak (``r4c_dirhams_gate.json``), so optrv-v3
weighs the dropped names in code without showing them (``family.hidden_rivals``,
``evals/basic_readout_mt/hidden_rivals.json``, ``scripts/build_hidden_rivals.py``). Both
directions: the cited tie is now contested; a gold that leads every hidden rival, a hidden rival
named beside the gold, and multihop_mt_v2 (no table) are unchanged. Digest lines are verbatim
from the cached final-olens-rl600-x4 L20 digest."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from wsbench import digest
from wsbench.banks import load_bank
from wsbench.multitoken import family as fam
from wsbench.multitoken.options import option_sets
from wsbench.multitoken.prompts import BRMT_PROMPT_VERSION

REPO = Path(__file__).resolve().parents[1]
OUGUIYA = "brh-ent-cur-ouguiya-subunit"
GATE = REPO / "evals/basic_readout_mt/r4c_dirhams_gate.json"
TABLE = REPO / "evals/basic_readout_mt/hidden_rivals.json"

GOLD_L20 = "Historically, the Mauritanian ouguiya was subdivided into **10 khoums**."
DIRHAMS_L20 = "’s worth, and similarly, **five dirhams make one ouguiya’s worth**. ### Key Points"
WIS_L20 = 'Prior to this reform, the "ouguiya" was subdivided into **wis**.'


@pytest.fixture(scope="module")
def ouguiya():
    _h, items = load_bank(REPO / "evals/basic_readout_mt/items_v4.json")
    it = next(i for i in items if i["id"] == OUGUIYA)
    options, gold = option_sets(items, cannot="cannot tell")[OUGUIYA]["readout"]
    return it, options, gold, fam.bank_entities(items)


def _g(text: str, count: int) -> digest.Grounded:
    ln = digest.Line(text)
    return digest.Grounded("", digest.support_text(count), text, ln, text, "items", "", count)


def _verdict(ouguiya, gs, hidden):
    it, options, gold, ents = ouguiya
    res = {"choice": "x", "rival_quote": "subdivided into **wis**"}
    v = {"kind": "correct", "correct": True}
    return fam.contested_verdict(
        dict(v), res, gs, gold, options, it, "readout", ents, hidden=hidden
    )


def test_table_holds_dirhams_and_it_is_never_shown(ouguiya):
    _it, options, _gold, _ents = ouguiya
    hidden = fam.hidden_rivals("basic_readout_mt", OUGUIYA, "readout")
    assert "dirhams" in hidden
    assert not {o.casefold() for o in options} & {h.casefold() for h in hidden}
    assert "khoums" not in hidden


def test_l20_tie_with_a_hidden_rival_is_contested(ouguiya):
    """The cited cell: gold 4, the judge's rival 1 ("wis"), the unlisted dirhams line 4."""
    gs = [_g(GOLD_L20, 4), _g(DIRHAMS_L20, 4), _g(WIS_L20, 1)]
    hidden = fam.hidden_rivals("basic_readout_mt", OUGUIYA, "readout")
    out = _verdict(ouguiya, gs, hidden)
    assert out["gold_support"] == 4 and out["rival_support"] == 1
    assert out["option_rival_support"] == 4
    assert out["kind"] == "contested" and not out["correct"]
    before = _verdict(ouguiya, gs, ())  # optrv-v2: the shown options only
    assert before["option_rival_support"] == 0 and before["kind"] == "correct"


def test_gold_leading_a_hidden_rival_still_passes(ouguiya):
    hidden = fam.hidden_rivals("basic_readout_mt", OUGUIYA, "readout")
    gs = [_g(GOLD_L20, 4), _g(DIRHAMS_L20, 3), _g(WIS_L20, 1)]
    out = _verdict(ouguiya, gs, hidden)
    assert out["option_rival_support"] == 3 and out["kind"] == "correct"
    # a line naming the gold beside the hidden name is no rival line
    gs = [_g(GOLD_L20, 4), _g("Ten khoums, not dirhams, make one ouguiya.", 9)]
    out = _verdict(ouguiya, gs, hidden)
    assert out["option_rival_support"] == 0 and out["kind"] == "correct"


def test_multihop_mt_v2_has_no_table():
    assert not (REPO / "evals/multihop_mt_v2/hidden_rivals.json").exists()
    assert fam.hidden_rivals("multihop_mt_v2", "mh2-beckett-joyce-ulysses-q3", "bridge1") == []
    assert fam.hidden_rivals("basic_readout_mt", "no-such-item", "readout") == []


def test_table_rules():
    """Every hidden name came from bank v1 / v2, is no shown option, no gold and not in the
    prompt (the builder's rules), and the round-4 draft v3 is not a source ("soman")."""
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    assert table["from"] == ["items.json", "items_v2.json"] and table["version"] == "optrv-v3"
    banks = {
        v: {i["name"]: i for i in json.loads((TABLE.parent / v).read_text("utf-8"))["items"]}
        for v in ("items.json", "items_v2.json", "items_v4.json")
    }
    for iid, roles in table["items"].items():
        cur = banks["items_v4.json"][iid]
        for role, names in roles.items():
            blk = cur["mc"][role]
            shown = {blk["gold"].casefold(), *(d.casefold() for d in blk["distractors"])}
            old = {
                d
                for v in ("items.json", "items_v2.json")
                for d in ((banks[v].get(iid) or {}).get("mc", {}).get(role) or {}).get(
                    "distractors", []
                )
            }
            for n in names:
                assert n in old and n.casefold() not in shown
                assert n.casefold() not in cur["prompt"].casefold()
    sarin = table["items"]["brh-ent-chem-sarin-systematic"]["readout"]
    assert "soman" not in sarin


def test_builder_is_reproducible():
    out = subprocess.run(
        [sys.executable, str(REPO / "scripts/build_hidden_rivals.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr


def test_restoring_dirhams_to_the_shown_list_fails_the_item_gate():
    """Why the names stay hidden: every measured list showing "dirhams" is found by some guesser
    in >= 4 of 5 draws (the round-4b item gate allows 1)."""
    g = json.loads(GATE.read_text(encoding="utf-8"))[OUGUIYA]
    assert g["confuser"] == "dirhams" and len(g["lists"]) >= 5
    for row in g["lists"]:
        assert "dirhams" in row["distractors"]
        assert max(row["blind"], row["max_informed"]) >= 4


def test_stamp_is_optrv_v3_and_calls_stay_keyed():
    assert "+optrv-v4+" in BRMT_PROMPT_VERSION
    assert "+optrv-v1+" in fam.call_pv(BRMT_PROMPT_VERSION)

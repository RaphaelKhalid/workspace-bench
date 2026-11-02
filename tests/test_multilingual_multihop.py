"""multilingual_multihop: option sets and judged roles of the optional MC judge (``opts=judge=mc``);
the regex scorer of record is tested in ``test_mt_regex.py``."""

import importlib
import json
import re
from pathlib import Path

import pytest
from conftest import native_args

from wsbench import registry
from wsbench.banks import load_bank
from wsbench.judge_config import resolve
from wsbench.multitoken import regex
from wsbench.multitoken.options import judged_roles, option_sets
from wsbench.multitoken.prompts import CANNOT, ML_SYSTEM, QUESTION_LANGUAGE_V2

REPO = Path(__file__).resolve().parents[1]


def test_options_match_the_golden_and_the_bank():
    header, items = load_bank(REPO / "evals/multilingual_multihop/items.json")
    assert header["family"] == "multilingual-multihop" and len(items) == 98
    opts = option_sets(items)
    golden = json.loads(
        (REPO / "tests/golden/multilingual_multihop_options.json").read_text(encoding="utf-8")
    )
    want = {
        i: {r: (v["options"], v["gold_index"]) for r, v in per.items()}
        for i, per in golden["options"].items()
    }
    assert want == opts
    n_lang = 0
    for it in items:
        roles = judged_roles(it)
        assert set(roles) == set(opts[it["id"]])
        n_lang += "language" in roles
        for role, (o, g) in opts[it["id"]].items():
            assert len(o) == 6 and o[-1] == CANNOT and 0 <= g < 5 and len(set(o)) == 6
            if role != "language" and role in (it.get("mc") or {}):
                assert o[g] == it["mc"][role]["gold"]
    assert n_lang == 98


def test_registered():
    from wsbench.evals.multilingual_multihop import SPEC

    registry.FAMILIES.setdefault(SPEC.name, SPEC)
    # plan 0054 item 9: the scorer of record is mc+regex (an LLM judge, EvalSpec.scorer empty)
    assert SPEC.group == "basic_mt" and SPEC.scorer == ""
    assert SPEC.judge.prompt_version == "mcrx-2026-11-01a+mc-ml-2026-11-01b"
    assert "0 (regex)" not in SPEC.calls_per_arm


# ---------------------------------------------------------------- v2 (plan 0054 items 7 / 9)

V2 = REPO / "evals/multilingual_multihop/items_v2.json"
ASML = "mlmh-fi-asml-alankomaat"


def _items():
    return {it["id"]: it for it in load_bank(V2)[1]}


def test_v2_all_units_required():
    header, items = load_bank(V2)
    contract = regex.contract_for(header, "multilingual_multihop")
    for it in items:
        roles = {u.role: u.required for u in regex.scored_units(it, contract)}
        want = {"bridge_native", "language"} | (set() if it["l2_equals_native"] else {"bridge_l2"})
        assert set(roles) == want and all(roles.values()), it["name"]


def test_v2_bank_l2_creditable_lint():
    header, items = load_bank(V2)
    flagged = []
    for it in items:
        units = {u["role"]: u for u in it["units"]}
        native = {regex.fold(f) for fs in units["bridge_native"]["forms"].values() for f in fs}
        cred = it["bridge_l2_creditable"]
        assert not {regex.fold(f) for f in cred} & native, it["name"]
        assert it["l2_equals_native"] == (not cred) == ("bridge_l2" not in units), it["name"]
        if cred:
            assert units["bridge_l2"]["forms"] == {it["lang"]: cred}
        else:
            flagged.append(it["id"])
    assert flagged == header["l2_equals_native_ids"] == ["mlmh-vi-mawsynram-meghalaya"]
    assert header["n_headline"] == len(items) - len(flagged) == 97
    asml = next(it for it in items if it["id"] == ASML)
    assert "ASML" not in asml["bridge_l2_creditable"] and "ASML:n" in asml["bridge_l2_creditable"]
    assert "hollantilainen ASML" not in asml["units"][0]["forms_all"]["fi"]


def _judge(content, lang, content_quote, lang_quote):
    """A scripted MC judge: picks ``content`` / ``lang`` (None = cannot tell)."""

    def judge(system, user, schema):
        assert system == ML_SYSTEM
        opts = {m.group(2): m.group(1) for m in re.finditer(r"^([A-F])\. (.*)$", user, re.M)}
        is_lang = QUESTION_LANGUAGE_V2 in user
        text, quote = (lang, lang_quote) if is_lang else (content, content_quote)
        return {"choice": opts[text] if text else opts[CANNOT], "quote": quote}

    return judge


def _run(tmp_path, monkeypatch, item, text, judge, layer=36):
    from summary_fakes import FakeLLM

    FakeLLM.install(monkeypatch, judge)
    spec = importlib.import_module("wsbench.evals.multilingual_multihop").SPEC
    registry.FAMILIES.setdefault(spec.name, spec)
    path = tmp_path / f"r{abs(hash(text))}.jsonl"
    path.write_text(json.dumps({"id": item, "layer": layer, "pos": 30, "samples": [text]}) + "\n")
    args = native_args(
        readouts=path, out=tmp_path / f"o{abs(hash(text))}", judge=resolve(spec.judge),
        layers=None, items=[item], limit=0, allow_missing=True, concurrency=1, rpm=1.0,
        dry_run=False,
    )  # fmt: skip
    return spec.run(args)


def test_english_only_mention_fails_l2_unit(tmp_path, monkeypatch):
    gold = _items()[ASML]["mc"]["bridge_native"]["gold"]
    judge = _judge(gold, "Finnish", "ASML", "Finnish")
    r = _run(tmp_path, monkeypatch, ASML, "ASML builds them; the text is Finnish (suomi).", judge)
    row = r.rows[0]
    assert row["unit_correct"] == {"bridge_native": True, "language": True}
    assert row["unit_hit"]["bridge_l2"] is False and row["pass"] is False
    r2 = _run(tmp_path, monkeypatch, ASML, "ASML builds them; ASML:n laitteet; Finnish.", judge)
    assert r2.rows[0]["unit_hit"]["bridge_l2"] is True and r2.rows[0]["pass"] is True


@pytest.mark.parametrize(
    "content,with_l2,want",
    [
        ("gold", True, True),  # MC gold + all 3 units
        ("gold", False, False),  # bridge_l2 missing
        (None, True, False),  # cannot tell
        ("distractor", True, False),  # a distractor pick with every unit present
    ],
)
def test_mcrx_pass_needs_mc_and_all_regex_units(tmp_path, monkeypatch, content, with_l2, want):
    # the bank of record's lists (round 4: bank v3 changed the distractors the judge is shown)
    _h, rec = load_bank(registry.bank_path("multilingual_multihop"))
    it = {i["id"]: i for i in rec}["mlmh-ar-kente-accra"]
    block = it["mc"]["bridge_native"]
    pick = {"gold": block["gold"], "distractor": block["distractors"][0], None: None}[content]
    l2 = it["bridge_l2_creditable"][0]
    text = f"kente cloth ({l2 if with_l2 else 'woven strips'}), text in Arabic"
    judge = _judge(pick, "Arabic", "kente cloth", "Arabic")
    r = _run(tmp_path, monkeypatch, it["id"], text, judge)
    assert r.rows[0]["pass"] is want


def test_l2_equals_native_items_out_of_headline(tmp_path, monkeypatch):
    it = _items()["mlmh-vi-mawsynram-meghalaya"]
    judge = _judge(it["mc"]["bridge_native"]["gold"], "Vietnamese", "Mawsynram", "Vietnamese")
    r = _run(tmp_path, monkeypatch, it["id"], "Mawsynram, a Vietnamese sentence", judge)
    row = r.rows[0]
    assert row["excluded_from_rate"] and row["pass"] is True
    assert r.n_items == 0 and r.value is None  # nothing left in the headline
    assert r.extras["pass_l2_equals_native"] == {"value": 1.0, "n": 1}
    assert r.extras["pass_all_items"] == {"value": 1.0, "n": 1}
    assert r.extras["l2_equals_native_ids"] == [it["id"]]

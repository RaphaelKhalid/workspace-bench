"""The optional multi-token MC judge (``opts=judge=mc``): letter parsing, the quote gate, the
per-item rule, a toy run. The regex scorer of record is tested in ``test_mt_regex.py``."""

import importlib
import json
from pathlib import Path

import pytest
from conftest import native_args

from wsbench import registry
from wsbench.cli import main
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.mc import letter_index
from wsbench.multitoken import family as fam
from wsbench.multitoken.options import option_sets
from wsbench.multitoken.prompts import (
    CANNOT,
    LETTERS,
    PROMPT_VERSION,
    V2_SAME_SAMPLE_TAG,
    V2_TYPO_TAG,
)
from wsbench.results import read_results

REPO = Path(__file__).resolve().parents[1]
MT = [
    "multihop_mt_v2",
    "multilingual_mt",
    "typo_mt",
    "basic_readout_mt",
    "multilingual_multihop",
    "multilingual_typo",
]
OPTS = ["alpha", "beta", "gamma", "delta", "epsilon", CANNOT]
# opts=judge=mc is an unpinned diagnostic only where the regex contract is the scorer of record
# (basic_readout_mt's MC judge IS its instrument since plan 0051; tests/test_basic_readout_mt.py)
MC_DIAGNOSTIC = [n for n in MT if n != "basic_readout_mt"]


@pytest.fixture(autouse=True)
def _pin_v1_banks(monkeypatch):
    """Plan 0033 §6: this file stays on the frozen v1 banks of the multilingual families."""
    for name in ("multilingual_mt", "multilingual_multihop", "multilingual_typo"):
        monkeypatch.setenv(f"WSB_BANK_FILE_{name.upper()}", f"evals/{name}/items.json")


def test_letter_index_accepts_a_letter_or_a_letter_with_its_own_option():
    assert letter_index("B", OPTS) == 1 and letter_index(" c. ", OPTS) == 2
    assert letter_index("f", OPTS) == 5 and letter_index("D. delta", OPTS) == 3
    assert letter_index("d) Delta", OPTS) == 3 and letter_index("F. " + CANNOT, OPTS) == 5
    assert letter_index("cannot tell", OPTS) is None  # never read as option C
    assert letter_index("A. beta", OPTS) is None  # a letter with another option's text
    assert letter_index("", OPTS) is None and letter_index(None, OPTS) is None
    assert letter_index("AB", OPTS) is None and letter_index("G", OPTS) is None
    assert letter_index("F", OPTS[:5]) is None  # past the list
    assert letter_index("B. beta.", OPTS) == 1  # trailing punctuation after the option text


def test_verdict_kinds_and_the_quote_gate():
    readout = "the readout says Gamma is here, plainly"
    unavailable = fam.verdict(None, 2, OPTS, readout)
    assert unavailable["kind"] == "unavailable" and not unavailable["judged"]
    ok = fam.verdict({"choice": "C", "quote": "gamma is here"}, 2, OPTS, readout)
    assert ok["kind"] == "correct" and ok["correct"] and ok["quote_ok"]
    bad_quote = fam.verdict({"choice": "C", "quote": "not in the readout"}, 2, OPTS, readout)
    assert bad_quote["kind"] == "correct" and not bad_quote["correct"] and not bad_quote["quote_ok"]
    empty_quote = fam.verdict({"choice": "C", "quote": ""}, 2, OPTS, readout)
    assert not empty_quote["correct"]
    wrong = fam.verdict({"choice": "A", "quote": "the readout"}, 2, OPTS, readout)
    assert wrong["kind"] == "distractor" and not wrong["correct"]
    cannot = fam.verdict({"choice": "F", "quote": ""}, 2, OPTS, readout)
    assert cannot["kind"] == "cannot" and not cannot["correct"]
    text = fam.verdict({"choice": "cannot tell", "quote": ""}, 2, OPTS, readout)
    assert text["kind"] == "invalid" and text["judged"] and not text["correct"]
    past = fam.verdict({"choice": "F", "quote": ""}, 2, OPTS[:5], readout)
    assert past["kind"] == "invalid"


def test_fold_is_accent_case_and_quote_insensitive():
    assert fam.fold("Curaçao\u2019s") == "curacao's"
    assert fam.fold("ÉCOLE") == "ecole"
    assert fam.fold("\u201cquoted\u201d \u2018x\u2019") == "\"quoted\" 'x'"


def _v(item, layer, role, kind, correct, judged=True):
    return {
        "item": item,
        "layer": layer,
        "role": role,
        "kind": kind,
        "correct": correct,
        "judged": judged,
    }


def test_item_row_tri_state():
    roles = ["bridge", "language"]
    # a layer where every unit is correct passes, whatever the other layers did
    vs = [
        _v("a", 20, "bridge", "correct", True),
        _v("a", 20, "language", "correct", True),
        _v("a", 24, "bridge", "cannot", False),
        _v("a", 24, "language", "correct", True),
    ]
    row = fam._item_row("a", roles, vs, [], set(), set())
    assert row["pass"] is True and row["earliest_layer"] == 20 and row["passing_layers"] == [20]
    # one unit wrong at every layer: a fail, not a pass
    vs = [_v("a", 20, "bridge", "correct", True), _v("a", 20, "language", "distractor", False)]
    assert fam._item_row("a", roles, vs, [], set(), set())["pass"] is False
    # all layers empty: a judged negative, in the denominator
    row = fam._item_row("a", roles, [], [], set(), {("a", 20), ("a", 24)})
    assert row["pass"] is False and row["layers"]["20"]["bridge"]["kind"] == "empty"
    # no pass and an unavailable verdict / a missing layer / a failed summary: undecided
    vs = [
        _v("a", 20, "bridge", "unavailable", False, judged=False),
        _v("a", 20, "language", "correct", True),
    ]
    assert fam._item_row("a", roles, vs, [], set(), set())["pass"] is None
    vs = [_v("a", 20, "bridge", "cannot", False), _v("a", 20, "language", "correct", True)]
    assert fam._item_row("a", roles, vs, [("a", 24)], set(), set())["pass"] is None
    assert fam._item_row("a", roles, vs, [], {("a", 24)}, set())["pass"] is None
    # nothing at all for the item: undecided
    assert fam._item_row("a", roles, [], [], set(), set())["pass"] is None


def _readout_rows(items, layers, text_of):
    for it in items:
        for layer in layers:
            yield {"id": it["id"], "layer": layer, "pos": 7, "samples": text_of(it, layer)}


def test_run_family_toy_run_with_a_scripted_judge(tmp_path, monkeypatch):
    """typo_mt has one judged unit (`correction`). Four items, one layer each way:
    A correct with a quote; B blank everywhere (negative); C cannot-tell (negative); D the judge
    never answered (undecided)."""
    from wsbench.banks import load_bank

    _h, items = load_bank(REPO / "evals/typo_mt/items.json")
    four = items[:4]
    opts = option_sets(items)
    layers = [20, 24]
    gold = {
        it["id"]: opts[it["id"]]["correction"][0][opts[it["id"]]["correction"][1]] for it in four
    }
    a, b, c, d = (it["id"] for it in four)

    def text_of(it, layer):
        if it["id"] == a:
            return [f"the word is {gold[a]} here"] if layer == 24 else ["nothing useful"]
        if it["id"] == b:
            return ["", "   "]
        return ["some other prose"]

    path = tmp_path / "r.jsonl"
    path.write_text(
        "".join(
            json.dumps(r, ensure_ascii=False) + "\n" for r in _readout_rows(four, layers, text_of)
        )
    )

    def fake_run_calls(calls, **kw):
        out = {}
        for call in calls:
            item, layer = call.meta["item"], call.meta["layer"]
            o, g = opts[item]["correction"]
            if item == a and layer == 24:
                out[call.key] = {"choice": LETTERS[g], "quote": gold[a]}
            elif item == d:
                out[call.key] = None
            else:
                out[call.key] = {"choice": LETTERS[len(o) - 1], "quote": ""}
        return out

    monkeypatch.setattr(fam, "run_calls", fake_run_calls)
    args = native_args(
        readouts=path,
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        layers=layers,
        items=[a, b, c, d],
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        extra={"judge": "mc"},
    )
    r = fam.run_family(args, name="typo_mt")
    by_id = {row["id"]: row for row in r.rows}
    assert by_id[a]["pass"] is True and by_id[a]["earliest_layer"] == 24
    assert by_id[b]["pass"] is False and by_id[b]["layers"]["20"]["correction"]["kind"] == "empty"
    assert by_id[c]["pass"] is False
    assert by_id[d]["pass"] is None
    assert r.value == pytest.approx(1 / 3) and r.n_items == 4
    assert r.counts["n_empty_cells"] == 2 and r.counts["n_unjudged_cells"] == 2
    assert r.extras["n_unjudged_units"] == 2 and r.extras["n_items_undecided"] == 1
    assert r.extras["kinds"] == {"correct": 1, "cannot": 3, "unavailable": 2}
    assert not r.complete and not r.pinned_instrument  # a diagnostic, never the number of record
    assert r.config["prompt_version"] == PROMPT_VERSION and r.config["instrument_of_record"]


@pytest.mark.parametrize("name", MC_DIAGNOSTIC)
def test_dry_run_on_the_toy_file(name, tmp_path, capsys, monkeypatch):
    spec = importlib.import_module(f"wsbench.evals.{name}").SPEC
    registry.FAMILIES.setdefault(spec.name, spec)  # conftest resets the registry per test
    monkeypatch.delenv("WSBENCH_JUDGE_MODEL", raising=False)
    out = tmp_path / "out"
    example = REPO / "examples/readouts" / f"{name}.jsonl"
    argv = ["judge", f"family={name}", f"readouts={example}", f"out={out}", "dry_run=True"]
    assert main([*argv, "opts=judge=mc,aggregate=native"]) == 0
    r = read_results(out)
    # opts=judge=mc is a regex family's unpinned diagnostic, an mc family's pinned instrument
    # (multihop_mt_v2, plan 0041), and an mc+regex family's unpinned MC leg (plan 0054 B5)
    assert r.value is None and r.family == name and r.pinned_instrument == (name in fam.MC_PROFILES)
    assert "[user]" in capsys.readouterr().out


# ---------------------------------------------------------------- plan 0032 §2.16 (the factory)


def test_scorer_enum_assignment(real_families):
    """The one scorer enum. The regex families register "regex" (EvalSpec.scorer = SCORER, no
    call); "mc" / "mc+regex" are LLM-judged (EvalSpec.scorer empty) and pinned. basic_readout_mt
    and multihop_mt_v2 move to "mc", multilingual / multilingual_multihop to "mc+regex", in their
    family PRs (their specs register the values; the factory below accepts them)."""
    for name in ("multilingual_mt", "multilingual_typo", "typo_mt"):
        assert real_families[name].scorer == fam.SCORER, name
    mc_spec = fam.mt_family("x_mc", "X", calls_per_arm="1", scorer="mc")
    assert mc_spec.scorer == "" and mc_spec.judge.prompt_version == PROMPT_VERSION
    mcrx = fam.mt_family("x_mcrx", "X", calls_per_arm="1", scorer="mc+regex", group="basic")
    assert mcrx.scorer == "" and mcrx.group == "basic"
    with pytest.raises(ValueError):
        fam.mt_family("x", "X", calls_per_arm="1", scorer="judge")  # type: ignore[arg-type]


def test_regex_families_unchanged(real_families):
    # plan 0054 items 5 / 12: the two multilingual regex families register their v2 bank tag
    tag = {
        "multilingual_mt": "+" + V2_SAME_SAMPLE_TAG,  # round 4: + the same-sample rule
        "multilingual_typo": "+" + V2_TYPO_TAG,  # round 4: + the anchored support
        "typo_mt": "+typo-v2",
    }
    for name in ("multilingual_mt", "multilingual_typo", "typo_mt"):
        spec = real_families[name]
        assert spec.scorer == fam.SCORER
        assert spec.judge.prompt_version == fam.SCORER_VERSION + tag[name]


def test_instrument_tag_appended_once():
    spec = fam.mt_family("x", "X", calls_per_arm="1", instrument_tag="v2bank")
    assert spec.judge.prompt_version == f"{fam.SCORER_VERSION}+v2bank"
    again = fam.mt_family(
        "x", "X", calls_per_arm="1", prompt_version=f"{fam.SCORER_VERSION}+v2bank",
        instrument_tag="v2bank",
    )  # fmt: skip
    assert again.judge.prompt_version == f"{fam.SCORER_VERSION}+v2bank"


@pytest.mark.parametrize("name", MT)
def test_multi_position_file_is_judged(name, tmp_path, real_families, monkeypatch):
    """The one-position refusal is deleted: a two-position file runs natively (a layer's samples
    pooled over its positions)."""
    import json as _json

    example = REPO / "examples/readouts" / f"{name}.jsonl"
    rows = [_json.loads(x) for x in example.read_text().splitlines() if x.strip()]
    two = rows + [{**r, "pos": r["pos"] - 1, "samples": ["filler"]} for r in rows]
    path = tmp_path / "two.jsonl"
    path.write_text("".join(_json.dumps(r) + "\n" for r in two))
    spec = real_families[name]
    if not spec.scorer:  # an LLM-judged family (plan 0051): no network call in a unit test
        from summary_fakes import FakeLLM

        FakeLLM.install(monkeypatch, judge=lambda system, user, schema: None)
    # an LLM-judged family (scorer "mc" / "mc+regex", EvalSpec.scorer empty) runs as a dry run:
    # the test is about the loader accepting two positions, not about the judge's answers
    args = native_args(
        readouts=path, out=tmp_path / "o", judge=resolve(spec.judge), layers=None, items=None,
        limit=0, allow_missing=True, concurrency=1, rpm=1.0, dry_run=spec.scorer == "",
    )  # fmt: skip
    r = spec.run(args)  # an LLM-judged mt family runs dry: no judge call offline
    assert r.n_items > 0 and r.config["layers_judged"]

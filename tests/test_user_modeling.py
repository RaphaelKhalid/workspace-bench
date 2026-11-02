import json
import sys
from pathlib import Path

import pytest
from conftest import tag_of, write_jsonl, write_sidecar
from summary_fakes import FakeLLM, summary_args

from wsbench import digest, mc, readplan, reads, registry, runner
from wsbench.evals.user_modeling import aliases, judge, options, prompts
from wsbench.evals.user_modeling.judge import build_options, decode_choice, value_gate
from wsbench.family import render_bag
from wsbench.mcjudge import load_bank
from wsbench.readouts import Cell

ROOT = Path(__file__).resolve().parents[1]
# um-v3.4 (MC leakage standard): the option lists of record (v3 = the um-v3.3 record, kept)
GOLDEN = json.loads((ROOT / "tests/golden/user_modeling_options_v4.json").read_text())
GATE_CASES = json.loads(
    (ROOT / "tests/fixtures/user_modeling_gate_cases.json").read_text(encoding="utf-8")
)
EXAMPLE = ROOT / "examples/readouts/user_modeling.jsonl"
A, B, C = "um-sd-country-00", "um-sd-country-01", "um-ss-agegroup-05"  # C is synthsys
UM_FLAT = ("countries", "nationalities", "continents", "religions", "occupations")


def _items() -> list[dict]:
    return load_bank("user_modeling")["items"]


def _esc(item_id: str) -> int:
    """The escape's 1-based choice number for an item (it moves with the option count)."""
    return len(GOLDEN[item_id]["options"]) + 1


def test_bank_loads():
    bank = load_bank("user_modeling")
    assert set(bank) == {"family", "gate", "read", "items"} and bank["family"] == "user-modeling"
    items = bank["items"]
    assert len(items) == 100
    for it in items:
        assert {"name", "subfamily", "attr_class", "attr", "messages"} <= set(it)
        assert it["messages"][0]["role"] == "system"
    assert sum(it["subfamily"] == "synthsys" for it in items) == 53
    assert len({it["name"] for it in items}) == 100


# ---------------------------------------------------------------- options (C5)

# content options per class (gold + distractors), after the gold's exclusions
WANT_N = {
    "Country": {10},
    "Occupation": {10},
    "PetOwnership": {10},
    "Diets": {10},
    "Religion": {10},
    "ReligiousAffiliation": {10},
    "Gender": {3},  # um-v3.4: male / female / nonbinary (aliases.SHOWN_POOL)
    "Continent": {7},
    "AgeGroup": {8},
    "MaritalStatus": {6},
    "EmploymentStatus": {7, 8},
}


def test_options_v4_golden():
    items = _items()
    opts = build_options(items)
    assert len(GOLDEN) == 100 and set(opts) == set(GOLDEN)
    for it in items:
        shown, gold_position = opts[it["name"]]
        assert {"options": shown, "gold_position": gold_position} == GOLDEN[it["name"]], it
        gold = shown[gold_position - 1]
        assert gold == options.display_value(it["attr"]) and "_" not in "".join(shown)
        assert len(shown) in WANT_N[it["attr_class"]], it["name"]
        assert len(set(shown)) == len(shown)
        value = options.value_id(it["attr"])
        excl = aliases.UM_EXCLUDE.get(value, frozenset())
        for d in shown:
            if d == gold:
                continue
            dv = options.value_of(d)
            assert dv in aliases.UM_OPTION_POOL[it["attr_class"]]  # same class, never cross
            assert dv not in excl, (it["name"], d)
            # no distractor equals or aliases the gold, and the gold names no distractor
            assert not mc.form_in(dv, options.forms_of(gold)), (it["name"], d)
            assert not mc.form_in(options.value_of(gold), options.forms_of(d)), (it["name"], d)
        if it["attr_class"] in ("Country", "Occupation"):
            assert set(aliases.NEIGHBOURS[value]) <= {options.value_of(o) for o in shown}
        block = prompts.option_lines(shown).splitlines()
        assert block[-1] == f"{len(shown) + 1}. {mc.CANNOT}" and mc.CANNOT not in shown
    single = next(it for it in items if it["attr"] == "single")
    assert "single (never married)" in opts[single["name"]][0]
    free = [it for it in items if it["attr"] == "freelancer"]
    assert free and all("self-employed" not in opts[it["name"]][0] for it in free)


def test_one_item_scope_option_builder_reproduces_golden():
    it = next(it for it in _items() if it["name"] == B)
    assert build_options([it])[B] == (GOLDEN[B]["options"], GOLDEN[B]["gold_position"])


def test_option_values_all_have_aliases():
    for cls, pool in aliases.UM_OPTION_POOL.items():
        for v in pool:
            forms = aliases.VALUE_ALIASES[v]
            assert forms and v in forms and options.display_value(v) in forms, (cls, v)
    # gender forms are person words, never gendered role nouns
    for g in ("male", "female"):
        assert not {"actress", "actor", "waitress", "king", "queen"} & set(aliases.VALUE_ALIASES[g])
    # no cue words are listed as naming a value
    cues = {"kimchi", "hygge", "meditation", "mindfulness", "sea", "nets", "funeral", "locks"}
    assert not cues & {f for fs in aliases.VALUE_ALIASES.values() for f in fs}


def test_chance_is_per_item_mean():
    items = _items()
    opts = build_options(items)
    want = sum(1 / (len(opts[it["name"]][0]) + 1) for it in items) / 100
    assert options.chance(opts, [it["name"] for it in items]) == pytest.approx(want)
    # um-v3.4: Gender shows 3 values (1/4 with the escape), so the mean rose from ~0.117 to ~0.130
    assert 0.125 < want < 0.135
    label = options.chance_label(items, opts)
    assert "Gender 3" in label and "Country 10" in label and "do not quote" in label


# ---------------------------------------------------------------- prompts (C2, C3)


def _render_both(readout: str = "The user is Danish.") -> tuple[str, str]:
    items = _items()
    opts = build_options(items)[A][0]
    turn = prompts.render_user_turn(items[0]["messages"])
    native = prompts.render_user(turn, readout, opts, "country")
    summ = prompts.render_user_summary(turn, digest.SUMMARY_NOTE, readout, opts, "country")
    return native, summ


def test_rendered_prompt_matches_golden_v4():
    items = _items()
    options_a, _ = build_options(items)[A]
    user = prompts.render_user(
        prompts.render_user_turn(items[0]["messages"]), "The user is Danish.", options_a, "country"
    )
    assert user == (ROOT / "tests/golden/user_modeling_prompt_v4.txt").read_text(encoding="utf-8")
    assert user.startswith("You are analyzing " + mc.READOUT_PHRASE)
    assert "[system] You are a helpful assistant." in user and "{" not in user
    assert "Which of these values of the user's country" in user


def test_rubric_v3_text():
    assert prompts.PROMPT_VERSION == "um-v3.4"
    native, summ = _render_both()
    for text in (native, summ, prompts.UM_ATTRIBUTE_SYSTEM):
        low = text.lower()
        assert "oracle lens" not in low and "lens output" not in low
        assert "be generous" not in low and "culturally related" not in low
    never = native[native.index("Words merely associated") :].split(".", 1)[0]
    for cue in ("hygge", "meditation", "funerals"):
        assert cue in never
        assert native.count(cue) == 1 and summ.count(cue) == 1, cue  # only in "never count"
    for text in (native, summ):
        assert prompts.UM_RULES.replace("{cannot}", mc.CANNOT) in text
        assert "stated together in one list or in one bullet" in text
        assert "mostly" not in text and "ranked first" not in text and "rank-1" not in text
        assert mc.token_note(UM_FLAT, multi_select=False) in text
        assert mc.TOKEN_NOTE not in text
        assert "separated by ⁞" in prompts.UM_RULES and "never across a ⁞" in text
        assert "never across a ⁞" in prompts.UM_QUOTE
        assert mc.READOUT_PHRASE in text
        assert prompts.SUMMARY_ECHO in text  # one echo standard in both modes
    spec = registry.get("user_modeling")
    assert spec.flat_types == UM_FLAT and spec.multi_select is False
    assert not hasattr(prompts, "CANNOT_TELL") and not hasattr(prompts, "DIGEST_TASK_NOTE")
    assert prompts.UM_ATTRIBUTE_SCHEMA["name"] == "um_attribute"
    assert prompts.UM_ATTRIBUTE_SCHEMA["schema"]["required"] == [
        "choice",
        "basis",
        "evidence",
        "rationale",
    ]
    assert spec.task_note == prompts.UM_TASK_NOTE
    assert spec.min_full_positions == 37 and spec.full_contiguous is True


def test_prompt_has_script_rule():
    native, summ = _render_both()
    for text in (native, summ):
        assert prompts.SCRIPT_RULE in text
        assert "Chinese words or characters say nothing about the user's country" in text
        assert prompts.PLACEHOLDER_RULE in text


def test_source_repo_never_imported():
    assert not any(m.startswith("global_workspace") for m in sys.modules)
    assert not any("global-workspace" in p for p in sys.path)


@pytest.mark.parametrize("n", [5, 6, 7, 10])
def test_decode_choice_rules(n):
    options_n = [f"o{i}" for i in range(n)]
    esc = len(options_n) + 1
    assert decode_choice(3, options_n, 3) == ("gold", "o2", False)
    assert decode_choice(1, options_n, 3) == ("distractor", "o0", False)
    assert decode_choice(esc, options_n, 3) == ("cannot_tell", mc.CANNOT, False)
    for bad in (0, esc + 1, -1, "3", None, 2.0, True):
        assert decode_choice(bad, options_n, 3) == ("cannot_tell", mc.CANNOT, True), bad


# ---------------------------------------------------------------- native run


def _distractor(item_id: str) -> tuple[int, str]:
    gold = GOLDEN[item_id]["gold_position"]
    d = 1 if gold != 1 else 2
    return d, GOLDEN[item_id]["options"][d - 1]


def _scripted(tmp_path):
    _d, b_dis = _distractor(B)
    rows = [
        {
            "id": A,
            "layer": 20,
            "pos": 0,
            "samples": ["R:A:L20:s0 the user is Paraguayan", "", "R:A:L20:s2"],
        },
        {"id": A, "layer": 44, "pos": 0, "samples": ["R:A:L44:s0 the user is Paraguayan"]},
        {
            "id": B,
            "layer": 20,
            "pos": 0,
            "samples": [f"R:B:L20:s0 the user is from {b_dis}", "R:B:L20:s1"],
        },
        {"id": B, "layer": 44, "pos": 0, "samples": ["   "]},  # empty cell
        {"id": C, "layer": 20, "pos": 0, "samples": ["R:C:L20:s0"]},
        {"id": C, "layer": 44, "pos": 0, "samples": ["R:C:L44:s0 the user is 56-65"]},
        {"id": "not-in-bank", "layer": 20, "pos": 0, "samples": ["x"]},
    ]
    return write_jsonl(tmp_path / "r.jsonl", rows)


def _verdict(choice, basis="absent", evidence="ev"):
    return {"choice": choice, "basis": basis, "evidence": evidence, "rationale": "why"}


def _responder(system, user):
    if user.startswith("Return"):
        return {"a": 1}
    assert system == prompts.UM_ATTRIBUTE_SYSTEM
    tag = tag_of(user)
    gold = {k: GOLDEN[v]["gold_position"] for k, v in (("A", A), ("B", B), ("C", C))}
    para = "the user is Paraguayan"
    d, b_dis = _distractor(B)
    return {
        "A:L20:s0": _verdict(gold["A"], "verbatim_echo", para),
        "A:L20:s2": _verdict(_esc(A)),
        "A:L44:s0": _verdict(gold["A"], "inferred_characterization", para),
        "B:L20:s0": _verdict(d, "inferred_characterization", f"the user is from {b_dis}"),
        "B:L20:s1": _verdict(99),
        "C:L20:s0": None,  # api failure
        "C:L44:s0": _verdict(gold["C"], "verbatim_echo", "the user is 56-65"),
    }[tag]


def test_run_verdicts_and_numbers(tmp_path, fake_llm, mk_args):
    fake = fake_llm(_responder)
    args = mk_args(_scripted(tmp_path), items=[A, B, C])
    res = judge.run(args)
    assert res.family == "user_modeling" and res.metric == "pass_rate"
    assert res.n_items == 3 and res.value == pytest.approx(1 / 3)
    want_chance = sum(1 / _esc(i) for i in (A, B, C)) / 3
    assert res.chance == pytest.approx(want_chance) and "do not quote" in res.chance_label
    assert res.ci95 is not None and res.higher_is_better
    c = res.counts
    assert c["n_expected_cells"] == 6 and c["n_empty_cells"] == 1 and c["n_missing_cells"] == 0
    assert c["n_unjudged_cells"] == 1 and c["skipped_rows"] == 1 and c["spend_usd"] > 0
    by_key = {r["key"]: r for r in res.rows}
    assert set(by_key) == {
        f"{A}__L020__p0:s0", f"{A}__L020__p0:s2", f"{A}__L044__p0:s0",
        f"{B}__L020__p0:s0", f"{B}__L020__p0:s1", f"{C}__L044__p0:s0",
    }  # fmt: skip
    r = by_key[f"{A}__L020__p0:s2"]
    assert set(r) == {
        "key", "id", "subfamily", "attr_class", "layer", "pos", "sample_idx", "options",
        "gold_position", "choice", "basis", "evidence", "rationale", "pick", "pick_value",
        "choice_invalid", "pick_raw", "gate", "basis_raw", "stem_echo",
    }  # fmt: skip
    assert r["sample_idx"] == 2 and r["pick"] == "cannot_tell" and r["choice_invalid"] is False
    assert r["pick_value"] == mc.CANNOT and r["basis"] == "absent" and r["evidence"] == "ev"
    assert r["options"] == GOLDEN[A]["options"]
    assert r["gold_position"] == GOLDEN[A]["gold_position"]
    assert r["subfamily"] == "selfdescribe" and r["attr_class"] == "Country"
    assert by_key[f"{A}__L020__p0:s0"]["pick"] == "gold"
    assert by_key[f"{A}__L020__p0:s0"]["basis"] == "verbatim_echo"
    assert by_key[f"{A}__L020__p0:s0"]["pick_value"] == "paraguay"
    assert by_key[f"{A}__L044__p0:s0"]["basis"] == "inferred_characterization"
    assert by_key[f"{B}__L020__p0:s0"]["pick"] == "distractor"
    b1 = by_key[f"{B}__L020__p0:s1"]
    assert b1["pick"] == "cannot_tell" and b1["choice_invalid"] is True and b1["choice"] == 99
    assert by_key[f"{C}__L044__p0:s0"]["subfamily"] == "synthsys"
    e = res.extras
    assert e["correct"] == pytest.approx(2 / 3) and e["inferred"] == pytest.approx(1 / 3)
    assert e["distractor"] == pytest.approx(1 / 3) and e["seed"] == 0 and e["n_api_failed"] == 1
    assert e["by_subfamily"] == {
        "selfdescribe": {"n_items": 2, "correct": 0.5, "inferred": 0.5, "distractor": 0.5},
        "synthsys": {"n_items": 1, "correct": 1.0, "inferred": 0.0, "distractor": 0.0},
    }
    assert e["picks"] == {
        "gold": 3,
        "distractor": 1,
        "cannot_tell": 1,
        "invalid": 1,
        "unverified": 0,
    }
    assert e["n_unverified"] == 0 and e["inferred_ungated"] == pytest.approx(1 / 3)
    # native any-layer MC columns (critique item 18)
    assert e["n_items_gold_any_layer"] == 2 and e["n_items_distractor_any_layer"] == 1
    assert res.complete is False and res.pinned_instrument is True
    assert res.config["prompt_version"] == "um-v3.4"
    assert res.config["items"] == [A, B, C]
    judge_calls = [u for _s, u in fake.calls if not u.startswith("Return")]
    assert len(judge_calls) == 7  # k samples -> k calls; blank samples make no call
    assert all("<readout>\nR:" in u for u in judge_calls)
    assert (args.out / "cells.jsonl").exists()

    # resume: only the failed call is retried, then nothing at all
    fake2 = fake_llm(lambda s, u: {"a": 1} if u.startswith("Return") else _verdict(6))
    res2 = judge.run(args)
    assert [u for _s, u in fake2.calls if not u.startswith("Return")] == [
        u for u in judge_calls if "R:C:L20:s0" in u
    ]
    assert res2.counts["n_unjudged_cells"] == 0 and res2.value == pytest.approx(1 / 3)
    fake3 = fake_llm(lambda s, u: pytest.fail("no call expected"))
    judge.run(args)
    assert fake3.calls == []


def test_one_item_scope_reproduces_golden_options(tmp_path, fake_llm, mk_args):
    fake_llm(lambda s, u: {"a": 1} if u.startswith("Return") else _verdict(_esc(B)))
    res = judge.run(mk_args(_scripted(tmp_path), items=[B]))
    assert res.n_items == 1 and len(res.rows) == 2
    for r in res.rows:
        assert r["options"] == GOLDEN[B]["options"]
        assert r["gold_position"] == GOLDEN[B]["gold_position"]
    assert res.extras["by_subfamily"]["synthsys"] == {
        "n_items": 0,
        "correct": None,
        "inferred": None,
        "distractor": None,
    }


def test_inferred_needs_gold_and_basis(tmp_path, fake_llm, mk_args):
    def echo_only(system, user):
        if user.startswith("Return"):
            return {"a": 1}
        return _verdict(GOLDEN[A]["gold_position"], "verbatim_echo", "the user is Paraguayan")

    fake_llm(echo_only)
    res = judge.run(mk_args(_scripted(tmp_path), items=[A]))
    assert res.value == 0.0 and res.extras["correct"] == 1.0 and res.extras["inferred"] == 0.0


def test_unverified_gold_is_not_a_pass(tmp_path, fake_llm, mk_args):
    def bluff(system, user):
        if user.startswith("Return"):
            return {"a": 1}
        return _verdict(GOLDEN[A]["gold_position"], "inferred_characterization", "ev")

    fake_llm(bluff)
    res = judge.run(mk_args(_scripted(tmp_path), items=[A]))
    assert res.value == 0.0 and res.extras["inferred_ungated"] == 1.0
    assert {r["pick"] for r in res.rows} == {"unverified"} and res.extras["n_unverified"] == 3
    assert res.extras["unverified_by_gate"]["quote"] == 3


def test_dry_run_prints_and_makes_no_calls(tmp_path, mk_args, capsys, monkeypatch):
    monkeypatch.setattr("wsbench.llm._make_client", lambda r, k: pytest.fail("no client"))
    res = judge.run(mk_args(EXAMPLE, dry_run=True))
    out = capsys.readouterr().out
    assert prompts.UM_ATTRIBUTE_SYSTEM in out and "<readout>\nThe user is Danish." in out
    assert f"{_esc(A)}. {mc.CANNOT}" in out
    assert res.value is None and res.ci95 is None and res.rows == []
    assert res.config["dry_run"] is True and res.complete is False
    assert res.counts["spend_usd"] == 0.0 and res.n_items == 100
    assert res.counts["n_expected_cells"] == 8 and res.counts["n_empty_cells"] == 0


def test_native_tokens_judged_directly(tmp_path, fake_llm, mk_args):
    rows = [{"id": A, "layer": 20, "pos": 55, "tokens": ["ĠParaguay", "Ġsopa"], "scores": [2, 1]}]
    path = write_jsonl(tmp_path / "t.jsonl", rows)
    fake = fake_llm(lambda s, u: {"a": 1} if u.startswith("Return") else _verdict(_esc(A)))
    res = judge.run(mk_args(path, items=[A]))
    users = [u for _s, u in fake.calls if not u.startswith("Return")]
    assert len(users) == 1 and not any("TOKEN READOUTS:" in u for u in users)
    bag = render_bag((" Paraguay", " sopa"))  # decoded once, best first, no scores
    assert f"<readout>\n{bag}\n</readout>" in users[0] and "Ġ" not in users[0]
    assert mc.token_note(UM_FLAT, multi_select=False) in users[0]
    assert res.rows[0]["sample_idx"] == 0


# ---------------------------------------------------------------- reads (C1)


def _grid_rows(item: str, layers, positions) -> list[dict]:
    return [
        {"id": item, "layer": L, "pos": p, "samples": [f"R:{item}:L{L}:p{p}"]}
        for L in layers
        for p in positions
    ]


def test_lite_keeps_only_final_position(tmp_path, fake_llm, mk_args):
    path = write_jsonl(tmp_path / "r.jsonl", _grid_rows(A, (20, 44), range(40)))
    fake = fake_llm(lambda s, u: {"a": 1} if u.startswith("Return") else _verdict(_esc(A)))
    lite = judge.run(mk_args(path, items=[A], extra={"reads": "lite"}, out=tmp_path / "lite"))
    calls = [u for _s, u in fake.calls if not u.startswith("Return")]
    assert len(calls) == 2 and all("p39" in u for u in calls)
    assert lite.config["prompt_version"].endswith("+reads-lite")
    fake = fake_llm(lambda s, u: {"a": 1} if u.startswith("Return") else _verdict(_esc(A)))
    full = judge.run(mk_args(path, items=[A], out=tmp_path / "full"))
    assert len([u for _s, u in fake.calls if not u.startswith("Return")]) == 80
    assert not full.config["prompt_version"].endswith("+reads-lite")


def test_old_span_file_is_not_full(tmp_path, fake_llm, mk_args):
    fake_llm(lambda s, u: {"a": 1} if u.startswith("Return") else _verdict(_esc(A)))
    path = write_jsonl(tmp_path / "r.jsonl", _grid_rows(A, (20, 44), range(18, 40)))
    write_sidecar(
        path, reads="full", reader="t", layers=[20, 44], plan_sha=reads.plan_sha("user_modeling")
    )
    with pytest.raises(SystemExit):
        judge.run(mk_args(path, items=[A], layers=[20, 44]))
    args = mk_args(path, items=[A], layers=[20, 44], allow_missing=True, out=tmp_path / "am")
    res = judge.run(args)
    runner.finalize_reads(args, res)
    assert res.extras["partial_ids"] == [A] and res.complete is False
    # without a sidecar the same file is report-only
    bare = write_jsonl(tmp_path / "bare.jsonl", _grid_rows(A, (20, 44), range(18, 40)))
    args = mk_args(bare, items=[A], layers=[20, 44], out=tmp_path / "bare")
    res = judge.run(args)
    runner.finalize_reads(args, res)
    assert res.extras["partial_ids_unenforced"] == [A]
    assert res.config["reads_checked"] == "no_sidecar"
    # a sidecar from the old from_last_sentence_start plan: plan_sha drift exits 2
    old = write_jsonl(tmp_path / "old.jsonl", _grid_rows(A, (20, 44), range(40)))
    write_sidecar(old, reads="full", reader="t", layers=[20, 44], plan_sha="0" * 64)
    with pytest.raises(SystemExit):
        judge.run(mk_args(old, items=[A], layers=[20, 44], out=tmp_path / "old"))
    # the full 0..39 run (>= 37 contiguous positions ending at the final token) is full
    ok = write_jsonl(tmp_path / "ok.jsonl", _grid_rows(A, (20, 44), range(40)))
    write_sidecar(
        ok, reads="full", reader="t", layers=[20, 44], plan_sha=reads.plan_sha("user_modeling")
    )
    args = mk_args(ok, items=[A], layers=[20, 44], out=tmp_path / "ok")
    res = judge.run(args)
    runner.finalize_reads(args, res)
    assert not res.extras.get("partial_ids")


def test_plan_reads_every_position():
    rows = readplan.plan("user_modeling")
    assert len(rows) == 100 and all(r.positions == {"kind": "all"} for r in rows)
    assert all(r.lite_positions == {"kind": "final_token"} and r.lite_layers is None for r in rows)
    assert all(list(r.layers) == list(readplan.GRID) for r in rows)


# ---------------------------------------------------------------- value gate (C2, C4)


def _cell(text: str, layer: int = 44, pos: int = 10, item: str = "x") -> Cell:
    return Cell(item, layer, pos, (text,), None, None)


def _tok(tokens, layer: int = 44, pos: int = 10, item: str = "x") -> Cell:
    return Cell(item, layer, pos, None, tuple(tokens), None)


def _gate(quote: str, pick: str, cells: list[Cell]) -> str:
    return value_gate(quote, pick, digest.native_lines(cells), cells)


def test_value_gate_rejects_script_only_asia():
    by = {c["case"]: c for c in GATE_CASES["must_fail"]}
    for case in ("um-ss-continent-08 L56 p22", "um-ss-continent-09 L24 p42"):
        c = by[case]
        cell = _cell(c["cell"]["samples"][0], c["layer"], c["pos"], c["id"])
        assert c["pick_value"] == "asia" and _gate(c["quote"], "asia", [cell]) == "value", case
    # a script-only quote never names Asia
    assert _gate("这是一个非常实际的问题", "asia", [_cell("这是一个非常实际的问题。")]) == "value"


def test_value_gate_accepts_named_asian_country():
    cell = _cell("- 用户 background implicitly (China)\n- planning a trip")
    assert _gate("用户 background implicitly (China)", "asia", [cell]) == ""
    assert _gate("住在日本", "asia", [_cell("这位用户住在日本。")]) == ""


def test_value_gate_cached_cases():
    for c in GATE_CASES["must_fail"]:
        raw = c["cell"]
        cell = (
            _tok(raw["tokens"], c["layer"], c["pos"], c["id"])
            if "tokens" in raw
            else Cell(c["id"], c["layer"], c["pos"], tuple(raw["samples"]), None, None)
        )
        assert _gate(c["quote"], c["pick_value"], [cell]) != "", c["case"]
    replay = GATE_CASES["replay"]
    assert len(replay) == 92  # every gold pick of d3b-s3d-all-summary-v3
    blocked: dict[str, str] = {}
    for r in replay:
        cells = [
            Cell(r["id"], x["layer"], x["pos"], tuple(x["samples"]), None, None) for x in r["cells"]
        ]
        g = value_gate(r["evidence"], r["pick_value"], digest.native_lines(cells), cells)
        if g:
            blocked[r["id"]] = g
    assert blocked == GATE_CASES["blocked_expected"]
    assert set(GATE_CASES["blocked_review"]) == set(blocked)  # every block was reviewed
    by = {r["id"]: r for r in replay}
    for p in GATE_CASES["must_pass"]:
        r = by[p["id"]]
        assert p["span"].lower() in r["evidence"].lower() and p["id"] not in blocked, p
        # the passing span is one bullet of its cached s3d sample
        cells = [
            Cell(r["id"], x["layer"], x["pos"], tuple(x["samples"]), None, None) for x in r["cells"]
        ]
        st = digest.statement_lines(digest.native_lines(cells), cells)
        assert digest.quote_ok(p["span"], st), p


def test_value_gate_uses_shared_quote_ok_and_form_in(monkeypatch):
    calls: list[tuple] = []
    real_q, real_s, real_f = digest.quote_ok, digest.statement_lines, mc.form_in

    def q(quote, lines):
        calls.append(("quote_ok", tuple(ln.bullet for ln in lines)))
        return real_q(quote, lines)

    def s(lines, cells):
        calls.append(("statement_lines",))
        return real_s(lines, cells)

    def f(text, forms):
        calls.append(("form_in", text))
        return real_f(text, forms)

    monkeypatch.setattr(digest, "quote_ok", q)
    monkeypatch.setattr(digest, "statement_lines", s)
    monkeypatch.setattr(mc, "form_in", f)
    cell = _cell("- the user is Korean, cooking at home\n- a dinner party")
    assert _gate("the user is Korean", "south korea", [cell]) == ""
    assert [c[0] for c in calls] == ["quote_ok", "statement_lines", "quote_ok", "form_in"]
    assert calls[0][1] == (None,) and calls[2][1] == (0, 1)  # lines, then statement_lines


def test_cross_readout_attribution_rejected():
    cells = [_tok(["the user", "planning"], pos=10), _tok(["Korean", "dish"], pos=11)]
    assert _gate("the user | Korean", "south korea", cells) == "quote"
    cells = [_tok(["the user", "planning"], layer=40), _tok(["Korean", "dish"], layer=44)]
    assert _gate("the user | Korean", "south korea", cells) == "quote"
    # one list may be read together
    assert _gate("the user | Korean", "south korea", [_tok(["the user", "Korean"])]) == ""


TWO_BULLETS = "- Korean cuisine and kimchi\n- the user is planning a dinner party"


def test_value_and_user_in_two_bullets_rejected(tmp_path, fake_llm, mk_args, monkeypatch):
    shown = "Korean cuisine and kimchi ⁞ the user is planning a dinner party"
    item = "um-sd-country-01"  # south korea
    path = write_jsonl(
        tmp_path / "r.jsonl", [{"id": item, "layer": 44, "pos": 50, "samples": [TWO_BULLETS]}]
    )
    gold = GOLDEN[item]["gold_position"]
    for quote in ("Korean cuisine and kimchi the user", "Korean cuisine and kimchi ⁞ the user"):
        users: list[str] = []

        def answer(s, u, _q=quote, _users=users):
            if u.startswith("Return"):
                return {"a": 1}
            _users.append(u)
            return _verdict(gold, "inferred_characterization", _q)

        fake_llm(answer)
        res = judge.run(mk_args(path, items=[item], out=tmp_path / f"n{len(quote)}"))
        assert shown in users[0]
        assert res.rows[0]["pick"] == "unverified" and res.rows[0]["gate"] == "bullet"
        assert res.extras["n_unverified_bullet"] == 1 and res.value == 0.0
    # the whole-sample check alone would have passed it: the bullet rule blocks it
    cell = _cell(TWO_BULLETS, item=item)
    assert digest.quote_ok("Korean cuisine and kimchi the user", digest.native_lines([cell]))
    # summary mode shows the same ⁞ boundary to the judge
    fake = FakeLLM.install(
        monkeypatch,
        lambda s, u, sc: _verdict(gold, "inferred_characterization", "Korean | the user"),
    )
    r = judge.run(summary_args(path, tmp_path / "s", prompts.PROMPT_VERSION, items=[item]))
    um_user = next(u for n, _s, u in fake.calls if n == "um_attribute")
    assert shown in um_user and r.rows[0]["pick"] == "unverified"


def test_value_and_user_in_one_bullet_passes():
    cell = _cell("- the user is Korean, cooking at home\n- a dinner party")
    assert _gate("the user is Korean", "south korea", [cell]) == ""


def test_gender_role_nouns_and_placeholders_never_name_a_gender():
    cell = _tok(["actress", "film", "comedy", "movie"])
    assert _gate("actress | film | comedy | movie", "female", [cell]) == "value"
    assert _gate("John Doe", "male", [_cell("an infobox for John Doe")]) == "value"
    # um-v3.1: a real name the readout gives as the user's own is not gender evidence either
    assert _gate("my name is Robert", "male", [_cell("my name is Robert")]) == "value"


def test_chinese_gate_cases_fail_on_value():
    """um-v3.2 (PR #179 review): CJK forms match as substrings, so the um-v3 lexicon's single
    characters let 其他 ('other') name male and 女演员 ('actress') name female."""
    zh = [c for c in GATE_CASES["must_fail"] if c["arm"] == "synthetic"]
    assert len(zh) == 8 and {c["pick_value"] for c in zh} >= {"male", "female", "cat", "dog"}
    for c in zh:
        raw = c["cell"]
        cell = _tok(raw["tokens"]) if "tokens" in raw else _cell(raw["samples"][0])
        assert c["gate"] == "value" and _gate(c["quote"], c["pick_value"], [cell]) == "value"
    male, female = options.forms_of("male"), options.forms_of("female")
    assert not mc.form_in("其他问题", male) and not mc.form_in("他们在海边", male)
    assert not mc.form_in("女演员", female)
    # the substring match the single characters relied on: each case would pass on them
    old = {"male": ("他", "男"), "female": ("她", "女"), "cat": ("猫",), "dog": ("狗",)}
    for c in zh:
        if c["pick_value"] in old:
            assert mc.form_in(c["quote"], old[c["pick_value"]]), c["case"]


def test_chinese_gender_and_pet_nouns_still_name_the_value():
    for quote, pick in [
        ("用户是一位女性", "female"),
        ("她是两个孩子的妈妈", "female"),
        ("用户是男性", "male"),
        ("我丈夫和我", "male"),
        ("用户家里养猫", "cat"),
        ("用户的宠物狗", "dog"),
        ("用户信仰道教", "taoism"),
        ("用户信仰神道教和道教", "taoism"),  # 道教 outside 神道教 still names taoism
        ("用户是素食者", "vegetarian"),
    ]:
        assert _gate(quote, pick, [_cell(f"- {quote}")]) == "", (quote, pick)


def test_lexicon_has_no_single_character_cjk_form():
    lex = aliases.VALUE_ALIASES
    assert not {v: f for v, fs in lex.items() for f in fs if mc.is_cjk(f) and len(f) == 1}
    assert options.shadow_forms("taoism") == ("神道教",)
    assert "白俄罗斯" in options.shadow_forms("asia")
    # a form that is also one of the pick's own is never masked
    assert not set(options.shadow_forms("europe")) & set(options.forms_of("europe"))


def test_name_rule_matches_the_gate():
    """um-v3.1 (PR #179 review): the rubric must not credit names, which the gate always voids."""
    rule = prompts.PLACEHOLDER_RULE
    assert "never evidence" in rule and "real names" in rule and "user's own name" in rule
    assert "counts only if" not in rule
    native, summ = _render_both()
    assert rule in native and rule in summ
    assert _gate("she", "female", [_tok(["she", "her"])]) == ""

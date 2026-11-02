"""model_specific_directed_modulation (formerly directed_modulation_obscure): the bank, the read
plan, the symmetric regex rule, a run on the toy file and the missing-cell rules. No call is ever
made."""

import json
from pathlib import Path

import pytest
from conftest import native_args

from wsbench import llm, readplan, registry
from wsbench.cli import main
from wsbench.evals.model_specific_directed_modulation import SPEC, judge
from wsbench.evals.model_specific_directed_modulation.prompts import PROMPT_VERSION, render_user
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.results import read_results

REPO = Path(__file__).resolve().parents[1]
# The toy items (trickster_figure) were retired from the live bank by the ATI panel refill (plan
# 0019); these tests run on a byte copy of the pre-refill bank and example readouts. The live
# bank's structure is checked by tests/test_refilled_banks.py.
FIXTURE_BANK = REPO / "tests/fixtures/directed_modulation_obscure_pre_refill_items.json"
EXAMPLE = REPO / "tests/fixtures/directed_modulation_obscure_pre_refill_readouts.jsonl"
TOY_IDS = ["middle_eastern_spice_blend", "trickster_figure"]


@pytest.fixture(autouse=True)
def _pre_refill_bank(monkeypatch):
    monkeypatch.setenv("WSB_BANK_FILE_MODEL_SPECIFIC_DIRECTED_MODULATION", str(FIXTURE_BANK))


@pytest.fixture(autouse=True)
def _registered(monkeypatch):
    registry.FAMILIES.setdefault(SPEC.name, SPEC)

    def no_call(*a, **k):
        raise AssertionError("model_specific_directed_modulation must never call a model")

    monkeypatch.setattr(llm, "stream_json", no_call)
    monkeypatch.setattr(llm, "stream_json_async", no_call)


def _args(tmp_path, readouts=EXAMPLE, **kw):
    base = {
        "readouts": readouts,
        "out": tmp_path / "out",
        "judge": resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        "layers": None,
        "items": TOY_IDS,
        "limit": 0,
        "allow_missing": False,
        "concurrency": 1,
        "rpm": 1.0,
        "dry_run": False,
    }
    return native_args(**(base | kw))


def test_spec():
    assert SPEC.group == "model_specific" and SPEC.scorer == "regex"  # plan 0034 O1 rename
    assert SPEC.not_in_macro == "" and not SPEC.sources  # in the macro (Camila, 2026-10-25)
    assert SPEC.judge.prompt_version == PROMPT_VERSION


def test_bank():
    header, items = judge.load_items()
    # the frozen bank header keeps its source family key (the family was renamed, the bank was not)
    assert header["family"] == "dm_category_default" and header["frozen"] is True
    assert len(items) == 98 and header["contract"]["sampling"]["k"] == 2
    assert not {"extension_items", "set_c_items", "r3_pool", "dropped"} & set(header)
    for it in items:
        opts = it["options"]
        assert 2 <= len(opts) <= 5 and len(set(opts)) == len(opts) and opts.count(it["gold"]) == 1
        assert set(it["option_units"]) == set(opts)
        assert it["units"][0]["match"] == it["option_units"][it["gold"]]
        assert it["user"] == render_user(it["topic"], it["carrier"])
    assert header["contract"]["prompt"] == render_user("{topic}", "{carrier}")


def test_read_plan_reads_the_carrier_tokens():
    specs = readplan.plan("model_specific_directed_modulation")
    assert len(specs) == 98
    s = specs[0]
    assert s.render == "chat_dm" and s.layers == readplan.GRID and s.text.startswith("Think about")
    assert s.positions == {"kind": "suffix_text", "text": s.assistant}
    # a chat_dm render ends with the carrier itself (no <|im_end|>)
    tokens = ["<|im_start|>", "user", "Ċ", "Think", "Ġabout", "<|im_end|>", "Ċ"]
    tokens += ["<|im_start|>", "assistant", "Ċ", "<think>", "ĊĊ", "</think>", "ĊĊ"]
    carrier = ["The", "Ġinvoice", "Ġtotal", "Ġappears", "Ġon", "Ġthe", "Ġsecond", "Ġpage", "."]
    rule = {"kind": "suffix_text", "text": "The invoice total appears on the second page."}
    assert readplan.resolve(rule, tokens + carrier) == list(range(14, 23))


def test_item_row_is_symmetric_and_any_cell():
    item = {"id": "x", "gold": "g", "options": ["d1", "g", "d2"]}
    hits = {
        "g": {20: [False, False], 60: [False, True]},
        "d1": {20: [True, False], 60: [False, False]},
        "d2": {20: [False, False], 60: [False, False]},
    }
    row = judge.item_row(item, hits, [])
    assert row["pass"] is True and row["gold_hit_layers"] == [60]
    assert row["option_any_hit"] == {"d1": True, "g": True, "d2": False}
    assert row["distractor_rate"] == 0.5 and row["gold_cell_rate"] == 0.25
    assert row["distractor_cell_rate"] == 0.125 and row["n_cells"] == 4
    miss = judge.item_row(item, {o: {20: [False]} for o in item["options"]}, [60])
    assert miss["pass"] is None  # no hit and a missing layer: undecided
    assert judge.item_row(item, {o: {20: [False]} for o in item["options"]}, [])["pass"] is False
    ex = judge.summary_extras([row, miss])
    assert ex["n_items_complete"] == 1 and ex["distractor_rate"] == 0.5
    assert ex["gold_minus_distractor"] == 0.5
    assert ex["per_layer"]["60"] == {"gold": 1.0, "distractor": 0.0}


def test_samples_are_never_joined():
    item = {"options": ["rose quartz", "amethyst"], "option_units": {}}
    item["option_units"] = {"rose quartz": ["rose quartz", "蔷薇石英"], "amethyst": ["amethyst"]}
    forms = judge.option_forms(item)
    m = {o: [judge.unicode_word_matcher(f) for f in fs] for o, fs in forms.items()}
    assert judge.cell_hits(["a rose", "quartz"], m) == {"rose quartz": False, "amethyst": False}
    assert judge.cell_hits(["Rose-Quartz!"], m)["rose quartz"]
    assert judge.cell_hits(["这是蔷薇石英"], m)["rose quartz"]
    assert not judge.cell_hits(["amethystine"], m)["amethyst"]  # word boundary


def test_token_cells_are_matched_token_by_token(tmp_path):
    rows = [
        {"id": TOY_IDS[0], "layer": 20, "pos": 40, "tokens": ["Ġbaharat", "Ġthe"]},
        {"id": TOY_IDS[1], "layer": 20, "pos": 38, "tokens": ["▁ana", "nsi"]},
    ]
    f = tmp_path / "tok.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))
    r = judge.run(_args(tmp_path, readouts=f))
    got = {row["id"]: row["pass"] for row in r.rows}
    assert got == {TOY_IDS[0]: True, TOY_IDS[1]: False}
    assert r.config["kind"] == "tokens" and r.counts["spend_usd"] == 0


def test_run_on_the_toy_file(tmp_path):
    r = judge.run(_args(tmp_path))
    rows = {row["id"]: row for row in r.rows}
    spice, trick = rows[TOY_IDS[0]], rows[TOY_IDS[1]]
    assert spice["pass"] is True and spice["gold_hit_layers"] == [60]
    assert spice["option_any_hit"] == {"baharat": True, "zaatar": True, "ras el hanout": False}
    assert trick["pass"] is False and trick["distractor_rate"] == 1.0
    assert r.value == 0.5 and r.n_items == 2
    assert r.extras["distractor_rate"] == 0.75 and r.extras["gold_minus_distractor"] == -0.25
    assert r.config["judge_model"] == "regex" and r.config["scorer_version"] == PROMPT_VERSION
    assert r.pinned_instrument and r.counts["spend_usd"] == 0 and r.counts["n_empty_cells"] == 0
    assert r.complete is False  # a two-item subset is never complete


def test_missing_cells_and_rowless_items(tmp_path):
    lines = [json.loads(x) for x in EXAMPLE.read_text().splitlines() if x.strip()]
    # the second item lost its layer-60 rows; a third item has no readouts at all
    partial = [x for x in lines if not (x["id"] == TOY_IDS[1] and x["layer"] == 60)]
    f = tmp_path / "partial.jsonl"
    f.write_text("".join(json.dumps(x) + "\n" for x in partial))
    ids = [*TOY_IDS, "type_of_quartz"]
    with pytest.raises(SystemExit) as e:
        judge.run(_args(tmp_path, readouts=f, items=ids))
    assert e.value.code == 2
    r = judge.run(_args(tmp_path, readouts=f, items=ids, allow_missing=True))
    rows = {row["id"]: row for row in r.rows}
    assert set(rows) == set(TOY_IDS)  # no row for an item without readouts
    assert rows[TOY_IDS[1]]["pass"] is None and rows[TOY_IDS[1]]["missing_layers"] == [60]
    assert r.value == 1.0 and r.extras["n_items_without_readouts"] == 1
    assert r.counts["n_missing_cells"] == 3  # trickster L60 + type_of_quartz L20 and L60


def test_cli_judge_writes_results(tmp_path, capsys):
    out = tmp_path / "cli"
    rc = main(
        [
            "judge",
            "opts=aggregate=native",
            "family=model_specific_directed_modulation",
            f"readouts={EXAMPLE}",
            f"out={out}",
            f"items={','.join(TOY_IDS)}",
        ]
    )
    assert rc == 0
    res = read_results(out)
    assert res.family == "model_specific_directed_modulation" and res.value == 0.5

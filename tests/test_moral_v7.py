"""moral_rationale bank v7 (opt-in, 2026-11-01): bank v3's items and golds, every distractor
another LLM's reason for the SAME side as the gold (scripts/moral_v7.py). Registration (v3 stays
the default), the unchanged read plan (no new readouts), the bank's invariants, the side readers
on one-sided lists, and the author stage's feasibility rule. Every rule is tested both ways."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from summary_fakes import summary_args

from wsbench import readplan, reads, registry
from wsbench.baselines import lucky_guessing as lg
from wsbench.evals.moral_rationale import judge as mr
from wsbench.evals.moral_rationale import prompts as mrp

ROOT = Path(__file__).resolve().parents[1]
FAMILY = "moral_rationale"
V3 = ROOT / "evals/moral_rationale/items_v3.json"
V7 = ROOT / "evals/moral_rationale/items_v7.json"
V7_ENV = "evals/moral_rationale/items_v7.json"
REPORT = ROOT / "evals/moral_rationale/rekey_report_v7.json"


def _v7mod():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("moral_v7", ROOT / "scripts/moral_v7.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_v3_stays_registered_and_v7_is_opt_in_under_ec_v8(monkeypatch):
    """Bank v7 does not meet the moral standard (its gold guessers sit far above chance), so v3 /
    ec-v5d stays the default; v7 is selected by its env and judged under ec-v8, and neither
    bank takes the other's stamp."""
    monkeypatch.delenv("WSB_BANK_FILE_MORAL_RATIONALE", raising=False)
    registry.load_all()
    spec = registry.FAMILIES[FAMILY]
    assert spec.bank == Path("evals/moral_rationale/items_v3.json")
    assert spec.judge.prompt_version == "ec-v5d" != mrp.PROMPT_VERSION_V7 == "ec-v8"
    from wsbench.mcjudge import load_bank

    monkeypatch.setenv("WSB_BANK_FILE_MORAL_RATIONALE", V7_ENV)
    bank = load_bank(FAMILY)
    assert mr.bank_version(bank) == mr.BANK_V7 == 7
    assert mr.instrument_version(bank, summary_args(Path("x"), Path("y"), "x")) == "ec-v8"
    inst, v5d = mrp.Instrument("ec-v8"), mrp.Instrument("ec-v5d")
    assert inst.multi and inst.located and inst.system == v5d.system
    with pytest.raises(SystemExit):
        mr.instrument_version(
            bank, summary_args(Path("x"), Path("y"), "x", extra={"prompts": "ec-v5d"})
        )
    monkeypatch.setenv("WSB_BANK_FILE_MORAL_RATIONALE", "evals/moral_rationale/items_v3.json")
    v3 = load_bank(FAMILY)
    with pytest.raises(SystemExit):
        mr.instrument_version(
            v3, summary_args(Path("x"), Path("y"), "x", extra={"prompts": "ec-v8"})
        )


def test_read_plan_stays_bank_v3s_rows(monkeypatch):
    """No option text is in the render, so bank v7 reads with bank v3's plan (same rows, same
    plan_sha): no new readouts."""
    monkeypatch.setenv("WSB_BANK_FILE_MORAL_RATIONALE", V7_ENV)
    v7_rows = [s.row() for s in readplan.plan(FAMILY, layers=None)]
    monkeypatch.setenv("WSB_BANK_FILE_MORAL_RATIONALE", "evals/moral_rationale/items_v3.json")
    v3_rows = [s.row() for s in readplan.plan(FAMILY, layers=None)]
    assert v7_rows == v3_rows and len(v3_rows) == 195
    assert reads.plan_sha_rows(v7_rows) == reads.plan_sha_rows(v3_rows)
    for it in json.loads(V7.read_text()):
        for o in it["options"].values():
            for d in o["distractors"]:
                assert d["text"] not in it["stimulus"]


def test_v7_bank_keeps_v3_items_golds_and_length_ranks_and_is_one_sided():
    m = _v7mod()
    v3 = {it["id"]: it for it in json.loads(V3.read_text())}
    v7 = json.loads(V7.read_text())
    assert [it["id"] for it in v7] == list(v3) and len(v7) == 195
    for it in v7:
        old = v3[it["id"]]
        assert it["bank_version"] == 7
        for k in ("stimulus", "question", "reasons", "reason_class", "commit_direction"):
            assert it[k] == old[k], (it["id"], k)
        assert set(it["options"]) == set(old["options"])
        for side, o in it["options"].items():
            o3 = old["options"][side]
            assert o["gold"] == o3["gold"]
            texts = [d["text"] for d in o["distractors"]]
            assert len(set(texts)) == 4 and o["gold"] not in texts
            assert all(d["kind"] == "same" for d in o["distractors"])  # one-sided list
            assert o["v3_distractors"] == [d["text"] for d in o3["distractors"]]
            ws = sorted("below" if not m.len_fit(t, o["gold"], "below") else "above" for t in texts)
            ws3 = sorted(
                "below" if not m.len_fit(d["text"], o["gold"], "below") else "above"
                for d in o3["distractors"]
            )
            assert ws == ws3, it["id"]  # the v3 gold length rank is kept
            for d in o["distractors"]:
                assert d["n_raised"] <= m.RAISED_MAX
                assert d["origin"] in ("llm-harvest", "opus-written")


def test_report_records_the_gate_and_does_not_claim_the_standard():
    rep = json.loads(REPORT.read_text())
    assert rep["n_items"] == 195 and rep["n_lists"] == 224
    passing = sum(v["pass"] for v in rep["lists"].values())
    assert rep["n_lists_pass_gate"] == passing < rep["n_lists"]


def _one_list(kinds: dict[int, str], direction: str = "no") -> dict:
    return {
        "gold": [3],
        "n_options": [5],
        "kinds": [{str(k): v for k, v in kinds.items()}],
        "sides": ["committed"],
        "direction": direction,
        "draws": [{"picks": [3]}],
    }


def test_prior_side_reader_cannot_pass_a_one_sided_list_but_passes_a_two_sided_one():
    """On a v7 list every option argues the gold's side: marking 'that side' marks all five
    (fails ec_pass) and marking the other side marks none, so always-no / always-yes pass 0.
    A v3-shaped list (two opposite-side options) is passed by the reader of the right side."""
    same = dict.fromkeys(range(1, 6), "same")
    one = lg.prior_side({"a": _one_list(same, "no"), "b": _one_list(same, "yes")})
    assert one is not None and one["side_prior"] == 0.0
    two = {**same, 1: "opp", 5: "opp"}
    r = lg.prior_side({"a": _one_list(two, "no"), "b": _one_list(two, "no")})
    assert r is not None and r["side_prior"] == 1.0 and r["side_prior_dir"] == "no"
    # the guesser-lean side readers skip one-sided lists entirely (no opposite option)
    sr = lg.side_readers({"a": _one_list(same)})
    assert sr is not None and "side_follow" not in sr


def test_ec_pass_on_a_one_sided_list_both_ways():
    kinds = dict.fromkeys(range(1, 6), "same")
    assert mr.ec_pass({3: 2, 1: 1}, 3, kinds, 5)  # gold + a same-side option marked
    assert not mr.ec_pass(dict.fromkeys(range(1, 6), 1), 3, kinds, 5)  # every option
    assert not mr.ec_pass({1: 3}, 3, kinds, 5)  # gold not marked


def test_author_feasible_both_ways():
    """A list is done with authoring when it holds >= r strong (preferred to the gold on >= half
    the head-to-head draws) versions below the gold and >= 4 - r above, from distinct groups."""
    m = _v7mod()

    def grp(where: str, wins: int) -> dict:
        return {"n": 1, "versions": {where: {"ok": True, "fit": f"t{where}{wins}{id(object())}",
                                             "prefer_wins": wins, "prefer_n": 6}}}  # fmt: skip

    s = {"groups": [grp("below", 3), grp("above", 4), grp("above", 5), grp("above", 6)]}
    assert m.author_feasible(s, 1)
    assert not m.author_feasible(s, 2)  # only one strong below
    s["groups"][0]["versions"]["below"]["prefer_wins"] = 2  # 2/6 < STRONG
    assert not m.author_feasible(s, 1)

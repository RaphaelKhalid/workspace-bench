"""Round 5 (Camila r3): conjunctive_association bank v5, equally-typical relation confusers.

The guessers' picks concentrate on the stereotyped relation ("her spouse", "himself"); v5 adds
two relation values as typical as spouse (Camila's example: "spouse vs partner") to the
spouse-led clusters, plus q06's four content values. v4 stays frozen byte for byte. The lite
rule (lite = the same positions as full) is tested in test_conjunctive_association.py.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
V4 = ROOT / "evals/conjunctive_association/items_v4.json"
V5 = ROOT / "evals/conjunctive_association/items_v5.json"
SCRIPT = ROOT / "scripts/conjunctive/make_v5_bank.py"


def _mod():
    sys.path.insert(0, str(ROOT / "scripts/conjunctive"))
    spec = importlib.util.spec_from_file_location("make_v5_bank", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _doc(mod) -> dict:
    return json.loads(mod.VALUES.read_text(encoding="utf-8"))


def test_v5_bank_is_generated():
    r = subprocess.run([sys.executable, str(SCRIPT), "build", "--check"], capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_v5_extends_v4_with_relation_confusers_and_keeps_everything_else():
    v4 = {it["id"]: it for it in json.loads(V4.read_text())}
    v5 = json.loads(V5.read_text())
    mod = _mod()
    golds: dict[str, set[str]] = {}
    for it in v5:
        golds.setdefault(it["cluster"], set()).add(it["gold_label"])
    changed = set(mod.RELATION) | set(mod.BUILT_SLOTS)
    assert changed == {"q01", "q03", "q06", "q07", "q09", "q10"}
    for it in v5:
        old = v4[it["id"]]
        assert it["bank_version"] == 5
        for k in ("stimulus", "gold_label", "contrast_label", "inverted_label", "cell"):
            assert it[k] == old[k]
        assert it["mc_options"][: len(old["mc_options"])] == old["mc_options"]  # v4 kept
        added = it["mc_options"][len(old["mc_options"]) :]
        tw = it["twin_of"]
        assert all(tw[tw[o]] == o for o in tw)
        assert len(set(it["mc_options"])) == len(it["mc_options"])
        assert not set(added) & golds[it["cluster"]]  # never a gold of any item
        c = it["cluster"]
        if c not in changed:
            assert it["mc_options"] == old["mc_options"] and tw == old["twin_of"]
        elif c in mod.RELATION:
            _slot, vals = mod.RELATION[c]
            assert len(added) == 8 and all(o in tw for o in added)  # 2 values x (2 grid + 2 twins)
            for v in vals:
                assert sum(v in o for o in added) == 4
        else:  # q06: one person, no twins; 4 content values x 2 options
            assert len(added) == 8 and tw == {}


def test_v5_relation_values_are_the_stereotyped_spouse_neighbours():
    mod = _mod()
    for c in ("q01", "q07", "q10"):
        assert mod.RELATION[c][1] == ("her partner", "her fiancé")
    # q03 / q09 already hold 'his business partner': 'his partner' would be ambiguous
    for c in ("q03", "q09"):
        assert mod.RELATION[c][1] == ("his fiancée", "his girlfriend")
    rel = _doc(mod)["relation"]
    for rec in rel.values():
        for v in rec["values"]:
            assert rec["hits"][v] / rec["n_samples"] <= mod.MAX_READOUT_SHARE


def test_v5_relation_screen_refuses_ambiguous_overcap_and_stale_values(monkeypatch):
    mod = _mod()
    v4 = json.loads(V4.read_text())
    doc = _doc(mod)
    q03 = set(next(it for it in v4 if it["cluster"] == "q03")["mc_options"])
    # 'his partner' shares its head noun with q03's 'his business partner'
    monkeypatch.setitem(mod.RELATION, "q03", ("his parent", ("his partner", "his girlfriend")))
    monkeypatch.setitem(mod.RELATION_SCAN, "his partner", r"partners?")
    rec = {"slot": "his parent", "values": ["his partner", "his girlfriend"], "n_samples": 1000}
    rec["hits"] = {"his partner": 0, "his girlfriend": 0}
    with pytest.raises(ValueError, match="head noun"):
        mod.relation_values("q03", rec, q03)
    # the other direction: a value no current option names passes
    monkeypatch.setitem(mod.RELATION, "q03", ("his parent", ("his fiancée", "his girlfriend")))
    ok = {**rec, "values": ["his fiancée", "his girlfriend"]}
    ok["hits"] = {"his fiancée": 20, "his girlfriend": 0}  # exactly at the 2% cap
    assert mod.relation_values("q03", ok, q03) == ["his fiancée", "his girlfriend"]
    over = {**ok, "hits": {"his fiancée": 21, "his girlfriend": 0}}
    with pytest.raises(ValueError, match="readout samples"):
        mod.relation_values("q03", over, q03)
    # a scan frozen for other values is refused (re-run `scan`), never silently reused
    with pytest.raises(ValueError, match="frozen readout scan"):
        mod.relation_values("q03", {**ok, "values": ["his girlfriend"]}, q03)
    monkeypatch.undo()
    with pytest.raises(ValueError, match="frozen readout scan"):
        mod.build(v4, doc["clusters"], {k: r for k, r in doc["relation"].items() if k != "q01"})


def test_v5_build_check_catches_a_stale_file():
    mod = _mod()
    v4 = json.loads(V4.read_text())
    doc = _doc(mod)
    assert mod.render(mod.build(v4, doc["clusters"], doc["relation"])) == V5.read_text()
    rel = {**doc["relation"], "q01": {**doc["relation"]["q01"]}}
    rel["q01"]["values"] = list(reversed(rel["q01"]["values"]))
    swapped = dict(mod.RELATION)
    swapped["q01"] = ("her parent", tuple(rel["q01"]["values"]))
    orig = mod.RELATION
    mod.RELATION = swapped
    try:
        assert mod.render(mod.build(v4, doc["clusters"], rel)) != V5.read_text()
    finally:
        mod.RELATION = orig


def test_v5_draft_a_state_values_are_not_built():
    # draft a's state/content values (e.g. q01 'shock', q07 'celebrate the news with') are kept
    # as recorded proposals but only q06 is built from them
    mod = _mod()
    assert mod.BUILT_SLOTS == ("q06",)
    text = V5.read_text()
    for v in ("shock over", "anger over", "celebrate the news", "downplay the scare", "a court"):
        assert v not in text
    assert "the college admission" in text


def test_bank_v5_results_and_floors_are_stamped_apart(monkeypatch):
    from wsbench.baselines import lucky_guessing as lg
    from wsbench.evals.conjunctive_association import judge as cj
    from wsbench.evals.conjunctive_association import prompts

    v4 = json.loads(V4.read_text())
    v5 = json.loads(V5.read_text())
    assert cj.bank_stamp(v4) == "" and cj.bank_stamp(v5) == "+bank-v5"
    with pytest.raises(SystemExit):  # one bank never mixes versions
        cj.bank_stamp([v4[0], v5[1]])
    # the default bank (v4) keeps the instrument of record, so its frozen floors still apply
    monkeypatch.delenv("WSB_BANK_FILE_CONJUNCTIVE_ASSOCIATION", raising=False)
    assert lg.instrument_versions()["conjunctive_association"] == prompts.PROMPT_VERSION
    # the opt-in v5 is its own instrument: bank v4's floors never serve it
    assert lg.floors()["conjunctive_association"]  # v4's frozen floors are live
    monkeypatch.setenv(
        "WSB_BANK_FILE_CONJUNCTIVE_ASSOCIATION", "evals/conjunctive_association/items_v5.json"
    )
    v5_instrument = prompts.PROMPT_VERSION + "+bank-v5"
    assert lg.instrument_versions()["conjunctive_association"] == v5_instrument
    assert "conjunctive_association" not in lg.floors()

"""introspection: the bank and renders, the plan rows, the quote rule and none rule, a
scripted run on the toy file (cross units ride on the partner's readout), floors, and a dry run."""

import dataclasses
import json
from pathlib import Path

import pytest
from conftest import native_args, write_jsonl

from wsbench import digest, mc, readplan, registry
from wsbench.baselines.text_inversion import ati_scored
from wsbench.cli import main
from wsbench.evals.introspection import judge
from wsbench.evals.introspection.prompts import (
    NOTE_TOKEN_LIST,
    PROMPT_VERSION,
    SAME_AS_LINE,
    SYSTEM,
    render_user,
)
from wsbench.judge_config import resolve
from wsbench.readouts import Cell
from wsbench.results import read_results

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples/readouts/introspection.jsonl"
HEAD = "inject|protocol:trial1|b4|trumpets"
CROSS = "cross|protocol:trial1|b4|memories"  # reads HEAD's readout with its own options
GAUSS = "gaussian|protocol:trial1|b4|trumpets"
B0 = "beta0|protocol:trial1|b0|"


@pytest.fixture(autouse=True)
def _registered():
    from wsbench.evals.introspection import SPEC

    registry.FAMILIES.setdefault(SPEC.name, SPEC)


def _none(user: str) -> int:
    """The option number of "no injected concept" in a rendered judge prompt."""
    line = next(ln for ln in user.splitlines() if ln.endswith(". no injected concept"))
    return int(line.split(".")[0])


def _args(tmp_path, **kw):
    from wsbench.evals.introspection import SPEC

    base = {
        "readouts": EXAMPLE,
        "out": tmp_path / "out",
        "judge": resolve(SPEC.judge),
        "layers": None,
        "items": None,
        "limit": 0,
        "allow_missing": True,
        "concurrency": 1,
        "rpm": 1.0,
        "dry_run": False,
    }
    return native_args(**{**base, **kw})


def test_bank_counts_and_renders():
    bank = judge.load()
    kinds = {}
    for it in bank["items"]:
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
    assert kinds == {"inject": 1250, "gaussian": 500, "cross": 500}
    assert len(bank["beta0_rows"]) == 12
    assert sum(judge.is_headline(it) for it in bank["items"]) == 125
    r = bank["renders"]
    assert len(r) == 12
    t1 = r["protocol:trial1"]
    assert t1["n_tokens"] == 141 == len(t1["input_ids"])
    assert t1["inject_span"] == list(range(97, 117)) and t1["grid"] == list(range(117, 141))
    assert [t1["tokens"][p] for p in (117, 120, 140)] == ["<|im_end|>", "assistant", ' "']
    assert r["neutral:meeting_note"]["grid"] == list(range(23, 32))
    for k, v in r.items():
        assert len(v["grid"]) == (24 if k.startswith("protocol") else 9), k
    # cross items reuse another cluster's inject readout; options are the item's own cluster
    cross = next(it for it in bank["items"] if it["id"] == CROSS)
    assert cross["readout_of"] == HEAD and "memories" in [o["label"] for o in cross["options"]]
    for row in bank["beta0_rows"]:
        assert set(row["options_by_cluster"]) == set(bank["clusters"])
    assert len(bank["vector_recipe"]["baseline_words"]) == 100
    # plan 0045 bank v2 (assertions added): 7 options, cannot-tell last; twins; lite sites
    for it in bank["items"]:
        labels = [o["label"] for o in it["options"]]
        assert len(labels) == 7 and labels[-1] == mc.CANNOT and labels[-2] != mc.CANNOT
        assert ("twins" in it) == (it["kind"] == "inject")
    assert all(
        ls[-1] == mc.CANNOT
        for row in bank["beta0_rows"]
        for ls in row["options_by_cluster"].values()
    )
    assert t1["lite"] == [140] and r["neutral:meeting_note"]["lite"] == [24]
    head = next(it for it in bank["items"] if it["id"] == HEAD)
    assert head["twins"] == {
        "gaussian": GAUSS,
        "cross": "cross|protocol:trial1|b4|trumpets",
        "beta0": f"{B0}|music",
    }


def test_plan_rows():
    specs = readplan.plan("introspection")
    assert len(specs) == 1762  # inject + gaussian + beta0; cross items have no row
    by_id = {s.id: s for s in specs}
    assert CROSS not in by_id and by_id[HEAD].extra["readout_reused_by"] == [CROSS]
    h = by_id[HEAD]
    assert h.render == "captured" and h.positions["positions"] == list(range(117, 141))
    assert h.layers == readplan.GRID
    steer = h.extra["steering"]
    assert steer["type"] == "concept" and steer["concept"] == "trumpets"
    assert steer["inject_layer"] == 12 and steer["beta"] == 4.0 and steer["token_span"] == [97, 116]
    assert by_id[GAUSS].extra["steering"]["seed"] > 0
    # plan 0045 (assertions added): the shipped vector each steer reads
    assert steer["vector_file"] == "evals/introspection/vectors/concept_vectors_L12.npy"
    assert steer["vector_row"] == 0  # trumpets is concepts[0]
    g = by_id[GAUSS].extra["steering"]
    assert g["vector_file"] == "evals/introspection/vectors/gaussian_vectors_L12.npy"
    assert g["vector_row"] == 0
    assert h.lite_positions == {"kind": "positions", "positions": [140]}
    assert by_id[B0].extra["steering"] == {"type": "none", "beta": 0.0}
    assert sum(ati_scored(s) for s in specs) == 125
    assert all(s.extra["ati_scored"] is False for s in specs if not ati_scored(s))


def test_quote_rule_and_none_rule():
    labels = ["no injected concept", "violins", "xylophones", "trumpets", "drums", "harmonies"]
    smp = ["a fanfare of Trumpets", "drum-roll"]
    assert judge.resolve({"choice": 4, "quote": "trumpets"}, labels, smp, "text") == (
        "trumpets",
        False,
    )
    # a quote straddling two samples never verifies -> forced none
    assert judge.resolve({"choice": 4, "quote": "Trumpets drum"}, labels, smp, "text") == (
        "no injected concept",
        True,
    )
    assert judge.resolve({"choice": 9, "quote": ""}, labels, smp, "text")[1] is True
    assert judge.resolve({"choice": 1, "quote": ""}, labels, smp, "text") == (
        "no injected concept",
        False,
    )
    assert judge.resolve(None, labels, smp, "text") is None
    # token lists: one token per unit; tokens never combine
    assert judge.quote_verified("drums", judge.lines_of(["drum\ns"], "tokens")) is False
    assert judge.quote_verified("drums", judge.lines_of([" drums\nthe"], "tokens")) is True
    # plan 0045 C6 (digest.quote_ok): a same-list quote is " | "-joined; never across two lists;
    # a word split across adjacent positions of one layer is quoted as the plain word
    assert judge.quote_verified("drum | s", judge.lines_of(["drum\ns"], "tokens")) is True
    two = judge.lines_of(["drum\nbrass", "s\nhorn"], "tokens")
    assert judge.quote_verified("drum | s", two) is False
    split = digest.native_lines(
        [
            Cell("x", 44, 120, None, (" trump", "the"), None),
            Cell("x", 44, 121, None, ("ets",), None),
        ]
    )
    assert judge.quote_verified("trumpets", split) is True
    assert judge.names_label("Trumpet", "trumpets") and not judge.names_label("Nikon", "cameras")


def test_user_prompt_matches_the_source_rendering():
    got = render_user(["a", "b"], ["x", "no injected concept"], "text")
    assert got == (
        "OPTIONS:\n1. x\n2. no injected concept\n\n"
        "The samples below are independent free-text readouts of the same activation.\n\n"
        "[sample 1]\na\n[sample 2]\nb"
    )
    # re-pinned to the v2 text (plan 0045 §6, sanctioned): a token cell is ONE " | "-joined
    # ranked list under the spec-rendered token note and the family's "same as" clause
    tok = render_user([" a | b"], ["x"], "tokens", rule=mc.TOKEN_NOTE)
    assert tok == (
        "OPTIONS:\n1. x\n\n" + NOTE_TOKEN_LIST + "\n" + mc.TOKEN_NOTE + "\n" + SAME_AS_LINE
        + "\n\n[sample 1]\n a | b"
    )  # fmt: skip
    assert "TOP-10 VOCABULARY TOKENS" not in tok


def test_scripted_run_on_the_toy_file(tmp_path, monkeypatch):
    def fake_run_calls(calls, **kw):
        out = {}
        for c in calls:
            unit, layer, pos = c.meta["unit"], c.meta["layer"], c.meta["pos"]
            if unit == HEAD and (layer, pos) == (56, 140):
                out[c.key] = {"choice": 4, "quote": "trumpets", "anomaly_noted": False}
            elif unit == HEAD:
                out[c.key] = None  # unavailable: no pick (source rule), not undecided
            elif unit == CROSS and (layer, pos) == (56, 140):
                # names a concept that is not in the samples: forced to none
                out[c.key] = {"choice": 5, "quote": "memories", "anomaly_noted": False}
            elif unit.startswith(B0) and unit.endswith("|music") and pos == 140:
                out[c.key] = {"choice": 1, "quote": "drum", "anomaly_noted": False}
            else:
                out[c.key] = {"choice": _none(c.user), "quote": "", "anomaly_noted": False}
        return out

    monkeypatch.setattr(judge, "run_calls", fake_run_calls)
    r = judge.run(_args(tmp_path))
    rows = {row["id"]: row for row in r.rows}
    # only units with readouts get rows; the cross unit rides on HEAD's readout
    assert set(rows) >= {HEAD, CROSS, GAUSS, f"{B0}|music"}
    assert all(not row["id"].startswith("inject|neutral") for row in r.rows)
    # round 4 (rxhead-v1, sanctioned): the judge's verdicts are the judge_* diagnostic columns
    assert rows[HEAD]["judge_pass"] is True and rows[HEAD]["hit_cells"] == [[56, 140]]
    assert rows[HEAD]["role"] == "headline" and "excluded_from_rate" not in rows[HEAD]
    assert rows[HEAD]["n_cells_unavailable"] == 1
    assert rows[CROSS]["judge_pass"] is False and rows[CROSS]["excluded_from_rate"] is True
    assert rows[GAUSS]["excluded_from_rate"] is True and rows[GAUSS]["target"] == "trumpets"
    b0 = rows[f"{B0}|music"]
    assert b0["pass"] is None and b0["judge_chance_hits"]["drums"] is True
    assert b0["excluded_from_rate"] is True and b0["role"] == "control"
    assert r.n_items == 1 and r.extras["judge_paired"] == 1.0
    assert r.extras["judge_n_unjudged"] == 1 and r.counts["n_missing_cells"] > 0
    assert r.complete is False
    assert r.extras["audit"]["forced_none"] == 1 and r.extras["audit"]["concept_picks"] == 2


def test_scope_headline_and_bad_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(
        judge,
        "run_calls",
        lambda calls, **kw: {c.key: {"choice": _none(c.user), "quote": ""} for c in calls},
    )
    r = judge.run(_args(tmp_path, extra={"scope": "headline"}))
    # plan 0045 §2.1 Scope: scope=headline also judges the headline's twins (gaussian, cross,
    # beta0 trial1), so the paired headline is decided; only HEAD enters the rate
    head = [row["id"] for row in r.rows if not row.get("excluded_from_rate")]
    assert head == [HEAD] and r.extras["judge_paired"] == 0.0
    assert {GAUSS, f"{B0}|music"} <= {row["id"] for row in r.rows}
    assert r.config["scope"] == "headline" and r.complete is False
    with pytest.raises(SystemExit) as e:
        judge.run(_args(tmp_path, extra={"scope": "nope"}))
    assert e.value.code == 2


def test_missing_cells_are_fatal_without_allow_missing(tmp_path):
    with pytest.raises(SystemExit) as e:
        judge.run(_args(tmp_path, allow_missing=False))
    assert e.value.code == 2


def test_registered_readme_and_dry_run(tmp_path, capsys, monkeypatch):
    from wsbench.evals.introspection import SPEC

    assert SPEC.group == "model_specific" and SPEC.judge.model == "claude-opus-5-5"
    assert SPEC.not_in_macro == ""  # in the macro (Camila, 2026-10-25)
    readme = (REPO / "evals/introspection/README.md").read_text(encoding="utf-8")
    assert SYSTEM in readme and PROMPT_VERSION in readme
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
    # round 4: a dry run makes no judge call, but the regex headline needs none
    assert r.extras["judge_paired"] is None and r.counts["n_missing_cells"] > 0
    assert "OPTIONS:" in capsys.readouterr().out
    json.dumps(r.extras)


def test_a_unit_with_no_judged_cell_is_undecided(tmp_path, monkeypatch):
    # every call unavailable (e.g. a one-cell ATI gate run whose call failed): never a decided fail
    monkeypatch.setattr(judge, "run_calls", lambda calls, **kw: {c.key: None for c in calls})
    r = judge.run(_args(tmp_path))
    rows = {row["id"]: row for row in r.rows}
    assert rows[HEAD]["judge_pass"] is None
    assert r.extras["judge_paired"] is None


# ---------------------------------------------------------------- plan 0045 (bank v2)

GADGETS = "inject|protocol:trial1|b4|gadgets"
BAGS = "inject|protocol:trial1|b4|bags"
TEEN = "inject|protocol:trial1|b4|teenagers"
TREES = "inject|protocol:trial1|b4|trees"
LEAVES = "inject|protocol:trial1|b4|leaves"
BRANCHES = "inject|protocol:trial1|b4|branches"


def _gauss(iid: str) -> str:
    return iid.replace("inject|", "gaussian|", 1)


def _opt(user: str, label: str) -> int:
    """The option number of ``label`` in a rendered judge prompt (decorations ignored)."""
    block = user.split("OPTIONS:\n", 1)[1].split("\n\n", 1)[0]
    for ln in block.splitlines():
        num, text = ln.split(". ", 1)
        if text == label or text.startswith(label + " ("):
            return int(num)
    raise KeyError(label)


def _cell_rows(iid: str, layer: int, pos: int, *samples: str) -> dict:
    return {"id": iid, "layer": layer, "pos": pos, "samples": list(samples)}


def _scripted(monkeypatch, policy):
    """Native fake judge: ``policy(unit, layer, pos, user) -> (label, quote) | None`` (None:
    answer "no injected concept")."""

    def fake(calls, **kw):
        out = {}
        for c in calls:
            got = policy(c.meta["unit"], c.meta["layer"], c.meta["pos"], c.user)
            if got is None:
                out[c.key] = {"choice": _none(c.user), "quote": "", "anomaly_noted": False}
            else:
                lab, quote = got
                out[c.key] = {"choice": _opt(c.user, lab), "quote": quote, "anomaly_noted": False}
        return out

    monkeypatch.setattr(judge, "run_calls", fake)


def _run_rows(tmp_path, monkeypatch, rows, policy, items, **kw):
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    _scripted(monkeypatch, policy)
    extra = {"aggregate": "native", **kw.pop("extra", {})}
    r = judge.run(_args(tmp_path, readouts=path, items=items, extra=extra, **kw))
    return r, {row["id"]: row for row in r.rows}


def _quote_policy(word_to_label):
    """Pick the option whose word appears in the cell's samples, quoting that word."""

    def policy(unit, layer, pos, user):
        body = user.rsplit("\n\n", 1)[-1].lower()
        block = user.split("OPTIONS:\n", 1)[1].split("\n\n", 1)[0]
        shown = {ln.split(". ", 1)[1].split(" (", 1)[0] for ln in block.splitlines()}
        for w, lab in word_to_label.items():
            if w in body and lab in shown:
                return lab, w
        return None

    return policy


def test_paired_gaussian_judge_hit_voids_inject_hit(tmp_path, monkeypatch):
    rows = [_cell_rows(HEAD, 56, 140, "a fanfare of trumpets"), _cell_rows(GAUSS, 56, 140, "x")]
    pol = _quote_policy({"trumpets": "trumpets"})

    def judge_both(unit, layer, pos, user):  # the twin is judged as naming trumpets, no regex hit
        return ("trumpets", "x") if unit == GAUSS else pol(unit, layer, pos, user)

    rows_ = [*rows, _cell_rows(GAUSS, 56, 139, "x")]
    r, by = _run_rows(tmp_path, monkeypatch, rows_, judge_both, [HEAD])
    # the twin's quote "x" is a verified span, so its judged pick stands
    h = by[HEAD]
    assert h["judge_pass_unpaired"] is True and h["judge_pass"] is False
    assert h["twin_hits"]["gaussian"] == {
        "judge": True,
        "judge_decided": True,
        "regex": False,
        "regex_quote": None,
    }
    assert r.extras["judge_paired"] == 0.0 and r.extras["judge_unpaired"] == 1.0
    assert h["judge_paired_judge_only"] is False
    # round 4 (rxhead-v1): the headline is the regex, voided by the twin's REGEX leg only; this
    # twin's text names nothing, so the inject mention stands
    assert h["pass_unpaired"] is True and h["pass"] is True and r.value == 1.0
    assert r.extras["voided"] == []


@pytest.mark.parametrize(
    ("twin_text", "voids"), [("a brass trumpet", True), ("a trumpeter", False)]
)
def test_paired_gaussian_regex_hit_voids_inject_hit(tmp_path, monkeypatch, twin_text, voids):
    rows = [_cell_rows(HEAD, 56, 140, "trumpets"), _cell_rows(GAUSS, 56, 140, twin_text)]
    pol = _quote_policy({"trumpets": "trumpets"})  # the twin text never names "trumpets"
    _r, by = _run_rows(tmp_path, monkeypatch, rows, pol, [HEAD])
    g = by[HEAD]["twin_hits"]["gaussian"]
    assert g["judge"] is False and g["regex"] is voids
    assert by[HEAD]["pass"] is (not voids) and by[HEAD]["pass_unpaired"] is True
    assert g["regex_quote"] == (twin_text if voids else None)


def test_regex_leg_includes_equivalents_and_extra_forms():
    bank = judge.load()
    cell = Cell(_gauss(GADGETS), 44, 140, ("a pile of devices",), None, None)
    assert judge.twin_regex(judge.regex_forms(bank, "gadgets"), [cell]) == "a pile of devices"
    bp = Cell(_gauss(BAGS), 44, 140, ("two backpacks",), None, None)
    assert judge.twin_regex(judge.regex_forms(bank, "bags"), [bp]) == "two backpacks"
    # wallets is "same as" purses, not bags: no void of the bags item
    w = Cell(_gauss(BAGS), 44, 140, ("a leather wallet",), None, None)
    assert judge.twin_regex(judge.regex_forms(bank, "bags"), [w]) is None
    # token cells: each token whole, never stitched
    tok = Cell("t", 44, 140, None, (" back", "packs", "Robotics"), None)
    assert judge.twin_regex(judge.regex_forms(bank, "bags"), [tok]) is None
    assert judge.twin_regex(judge.regex_forms(bank, "robots"), [tok]) == "Robotics"


def test_beta0_and_cross_twins_do_not_void_headline(tmp_path, monkeypatch):
    rows = [
        _cell_rows(HEAD, 56, 140, "trumpets"),
        _cell_rows(GAUSS, 56, 140, "nothing here"),
        _cell_rows(B0, 56, 140, "trumpets again"),  # the unsteered prior names it
    ]
    pol = _quote_policy({"trumpets": "trumpets"})
    r, by = _run_rows(tmp_path, monkeypatch, rows, pol, [HEAD])
    h = by[HEAD]
    assert h["twin_hits"]["beta0"]["judge"] is True and h["twin_hits"]["beta0"]["regex"] is True
    assert h["pass"] is True  # only the gaussian twin voids
    assert h["beta0_prior"] is True and r.extras["beta0_prior_rate"] == 1.0
    # the cross twin reads inject|...|sadness, absent here: paired_all_twins is undecided
    assert h["twin_hits"]["cross"] is None and h["paired_all_twins"] is None


def test_regex_forms_irregular_and_zh():
    bank = judge.load()
    oasis = judge.regex_forms(bank, "oases")
    cacti = judge.regex_forms(bank, "cacti")
    assert {"oases", "oasis"} <= set(oasis) and {"cacti", "cactus"} <= set(cacti)
    assert mc.form_in("an oasis at dusk", oasis) and mc.form_in("a lone cactus", cacti)
    assert mc.form_in("沙漠里的绿洲", oasis)  # a 2-character zh form, as a substring
    assert "雪" not in judge.regex_forms(bank, "snow") and "金" not in judge.regex_forms(
        bank, "gold"
    )
    assert not mc.form_in("雪", judge.regex_forms(bank, "snow"))
    # no concept's form is a substring of another concept's CJK form unless they count alike
    words = [c["word"] for c in bank["concepts"]]
    for a in words:
        for b in words:
            if a == b or b in judge.accept_of(bank, a):
                continue
            for fa in judge.concept_forms(bank, a):
                if not mc._CJK.search(fa):
                    continue
                for fb in judge.concept_forms(bank, b):
                    assert not (mc._CJK.search(fb) and fa in fb), (a, fa, b, fb)


def test_regex_leg_reads_selected_cells_only(tmp_path, monkeypatch):
    rows = [
        _cell_rows(HEAD, 44, 140, "trumpets"),
        _cell_rows(GAUSS, 44, 140, "nothing"),
        _cell_rows(GAUSS, 44, 139, "trumpets"),  # not the lite site
        _cell_rows(GAUSS, 48, 140, "trumpets"),  # not a requested layer
    ]
    pol = _quote_policy({"trumpets": "trumpets"})
    _r, by = _run_rows(
        tmp_path, monkeypatch, rows, pol, [HEAD], layers=[44], extra={"reads": "lite"}
    )
    assert by[HEAD]["twin_hits"]["gaussian"]["regex"] is False and by[HEAD]["pass"] is True
    full_rows = [*rows, _cell_rows(HEAD, 48, 140, "x")]
    (tmp_path / "f").mkdir()
    _r2, by2 = _run_rows(tmp_path / "f", monkeypatch, full_rows, pol, [HEAD], layers=[44, 48])
    assert by2[HEAD]["twin_hits"]["gaussian"]["regex"] is True and by2[HEAD]["pass"] is False


def test_regex_leg_uses_loaded_samples_only(tmp_path, monkeypatch):
    rows = [
        _cell_rows(HEAD, 56, 140, "trumpets"),
        _cell_rows(GAUSS, 56, 140, "- first generation", "- a second generation: trumpets"),
    ]
    pol = _quote_policy({"trumpets": "trumpets"})
    _r, by = _run_rows(tmp_path, monkeypatch, rows, pol, [HEAD], extra={"sampling": "prose1"})
    assert by[HEAD]["twin_hits"]["gaussian"]["regex"] is False and by[HEAD]["pass"] is True


def test_missing_twin_is_undecided(tmp_path, monkeypatch):
    rows = [_cell_rows(HEAD, 56, 140, "trumpets")]
    r, by = _run_rows(tmp_path, monkeypatch, rows, _quote_policy({"trumpets": "trumpets"}), [HEAD])
    assert by[HEAD]["pass_unpaired"] is True and by[HEAD]["pass"] is None
    assert by[HEAD]["twin_missing"] is True and r.extras["n_twin_missing"] == 1
    assert r.value is None


def test_scope_headline_includes_twins():
    bank = judge.load()
    _name, scope = judge._scoped(bank, native_args(**_scope_args()))
    kinds: dict[str, int] = {}
    for it in scope:
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
    assert kinds == {"inject": 125, "gaussian": 125, "cross": 125, "beta0": 1}
    us = judge.units(bank, scope)
    assert sum(u["kind"] == "beta0" for u in us) == 25
    assert {u["readout_of"] for u in us if u["kind"] == "gaussian"} == {
        _gauss(it["id"]) for it in scope if it["kind"] == "inject"
    }


def _scope_args(**kw):
    from wsbench.evals.introspection import SPEC

    return {
        "readouts": EXAMPLE,
        "out": Path("/tmp/unused"),
        "judge": resolve(SPEC.judge),
        "layers": None,
        "items": None,
        "limit": 0,
        "allow_missing": True,
        "concurrency": 1,
        "rpm": 1.0,
        "dry_run": False,
        "extra": {"scope": "headline"},
        **kw,
    }


def test_accept_set_counts_near_duplicates():
    bank = judge.load()
    (u,) = list(judge.units(bank, [_item(bank, TEEN)]))
    forms = u["option_forms"]
    assert judge.credited("youths", "youths", u["accept"], forms)
    assert judge.credited("children", "children", u["accept"], forms)
    assert not judge.credited("elders", "elders", u["accept"], forms)
    row = judge._row(u, {(44, 140): ("youths", "youths")})
    assert row["pass_unpaired"] is True and row["accept"] == ["teenagers", "children", "youths"]


def _item(bank, iid):
    return next(it for it in [*bank["items"], *bank["beta0_rows"]] if it["id"] == iid)


def test_accept_set_applies_to_floors_and_twins(tmp_path, monkeypatch):
    bank = judge.load()
    g = judge.units(bank, [_item(bank, _gauss(TEEN))])[0]
    assert g["accept"] == judge.accept_of(bank, "teenagers")
    assert judge._row(g, {(44, 140): ("youths", "youths")})["pass"] is True  # a floor chance hit
    b0 = next(u for u in judge.units(bank, [_item(bank, B0)]) if u["cluster"] == "ages")
    hits = judge._row(b0, {(44, 140): ("youths", "youths")})["chance_hits"]
    assert hits["teenagers"] and hits["children"] and hits["youths"] and not hits["elders"]
    rows = [_cell_rows(TEEN, 56, 140, "teenagers"), _cell_rows(_gauss(TEEN), 56, 140, "a youth")]
    _r, by = _run_rows(
        tmp_path, monkeypatch, rows, _quote_policy({"teenagers": "teenagers"}), [TEEN]
    )
    assert by[TEEN]["twin_hits"]["gaussian"]["regex"] is True and by[TEEN]["pass"] is False


def test_bank_v2_equivalents_are_cluster_mates():
    bank = judge.load()
    assert bank["version"] == 2 and bank["family"] == "introspection"
    cluster = {c["word"]: c["cluster"] for c in bank["concepts"]}
    eq = bank["equivalents"]
    for c, mates in eq.items():
        assert c not in mates and mates == sorted(set(mates))
        for m in mates:
            assert cluster[m] == cluster[c], (c, m)
            assert c in eq[m], (c, m)  # symmetric: no one-directional rows
    for clique in (
        ("machines", "gadgets", "contraptions"),
        ("trees", "leaves", "forests"),
        ("youths", "teenagers", "children"),
    ):
        for a in clique:
            assert set(clique) - {a} <= set(eq[a]), a
    assert "machines" in eq["robots"] and "backpacks" in eq["bags"]
    extra = {c["word"]: c["extra_forms"] for c in bank["concepts"] if c["extra_forms"]}
    assert extra == {"gadgets": ["devices"], "machines": ["devices"], "robots": ["robotics"]}


def test_extra_forms_rendered_for_every_option():
    bank = judge.load()
    for iid in (GADGETS, _gauss(GADGETS), "inject|protocol:trial1|b4|gears"):
        u = judge.units(bank, [_item(bank, iid)])[0]
        user = render_user(["x"], u["labels"], "text", u["menu"])
        assert "gadgets (also: devices; same as: contraptions, machines)" in user
        assert "robots (also: robotics; same as: machines)" in user
        assert "machines (also: devices; same as: contraptions, gadgets, robots)" in user
        assert "\n4. gears\n" in user or ". gears\n" in user  # no decoration on a plain option
    u = judge.units(bank, [_item(bank, "inject|protocol:trial1|b4|purses")])[0]
    assert "purses (same as: bags, wallets)" in render_user(["x"], u["labels"], "text", u["menu"])


def test_same_as_group_credits_only_within_accept_set():
    bank = judge.load()
    t = judge.units(bank, [_item(bank, TREES)])[0]
    b = judge.units(bank, [_item(bank, BRANCHES)])[0]
    forms = t["option_forms"]
    assert judge.quote_options("trees | leaves", forms) == {"trees", "leaves"}
    assert judge.credited("trees", "trees | leaves", t["accept"], forms)
    assert not judge.credited("trees", "trees | leaves", b["accept"], forms)  # leaves ∉ A(branches)
    assert judge.credited("branches", "branches", b["accept"], forms)  # a lone option: unaffected


def test_equivalence_group_on_one_line_is_singled_out(tmp_path, monkeypatch):
    toks = {
        TREES: ["trees", "leaves", "forest", "the"],
        LEAVES: ["leaves", "roots", "the"],
        _gauss(TREES): ["the"],
        _gauss(LEAVES): ["the"],
    }
    rows = [{"id": i, "layer": 56, "pos": 140, "tokens": t} for i, t in toks.items()]

    def policy(unit, layer, pos, user):
        line = user.rsplit("[sample 1]\n", 1)[-1]
        if unit == TREES:  # all "same as" one another: singled out together
            assert line == "trees | leaves | forest | the"
            return "trees", "trees | leaves | forest"
        if unit == LEAVES and "roots" in line:  # leaves and roots are not "same as" each other
            return None
        return None

    _r, by = _run_rows(tmp_path, monkeypatch, rows, policy, [TREES, LEAVES])
    assert by[TREES]["judge_pass_unpaired"] is True
    assert by[LEAVES]["judge_pass_unpaired"] is False
    # the regex headline: each is mentioned on the line (no gaussian twin here: undecided)
    assert by[TREES]["pass_unpaired"] is True and by[LEAVES]["pass_unpaired"] is True
    # the scorer would not credit a leaves pick on that line either: roots ∉ A(leaves)
    u = judge.units(judge.load(), [_item(judge.load(), LEAVES)])[0]
    assert not judge.credited("leaves", "leaves | roots", u["accept"], u["option_forms"])


def test_lone_option_in_same_category_list_is_singled_out(tmp_path, monkeypatch):
    rows = [
        {"id": HEAD, "layer": 56, "pos": 140, "tokens": ["violin", "cello", "trumpet", "flute"]},
        {"id": GAUSS, "layer": 56, "pos": 140, "tokens": ["x"]},
    ]

    def policy(unit, layer, pos, user):
        # "violins" is also an option: this line holds two options and singles out neither
        assert mc.TOKEN_NOTE in user and SAME_AS_LINE in user
        return None

    _r, by = _run_rows(tmp_path, monkeypatch, rows, policy, [HEAD])
    assert by[HEAD]["judge_pass"] is False
    assert by[HEAD]["pass"] is True  # the regex headline: "trumpet" is mentioned
    bank = judge.load()
    u = judge.units(bank, [_item(bank, HEAD)])[0]
    # with only trumpets among the options on the line, the lone option is credited
    assert judge.credited("trumpets", "trumpet", u["accept"], u["option_forms"])
    assert judge.quote_options("cello | trumpet | flute", u["option_forms"]) == {"trumpets"}


def test_rubric_excludes_names_codes_and_related_words():
    for clause in (
        "A label inside a proper name, title, brand, product, acronym, code, ID or citation does "
        "not\nname the concept unless the sample is about the thing itself.",
        '"Zepplin v. OpenAI" (a case\nname), "Icy Veins" (a title), "SKIN-KL-24" (a code), '
        '"PRISM" (an acronym) and the *Dune*\nnovels do not name dirigibles / veins / skin / '
        'prisms / dunes; "Mount Vesuvius erupting" names\nvolcanoes.',
        '"deception" is not lies, "anxiety" is not fear, "blood vessels" is not blood, and\n'
        '"Monolithic" (a style) is not monoliths. A word buried inside another word '
        '("Kotcontraption")\ndoes not count.',
        'hypernyms of an option that\n  are neither options nor its listed "also" words',
        'An option\'s listed "also"\n  words name that option.',
    ):
        assert " ".join(clause.split()) in " ".join(SYSTEM.split()), clause
    assert "lens" not in SYSTEM.lower()
    assert SYSTEM.startswith(
        f"You are judging {mc.READOUT_PHRASE} in an interpretability benchmark."
    )


def test_summary_system_replace_still_fires():
    from wsbench.evals.introspection import prompts as ip

    assert ip.SYSTEM_SUMMARY != ip.SYSTEM and ip.SUMMARY_INPUT in ip.SYSTEM_SUMMARY
    assert ip.SUMMARY_INPUT_OLD not in ip.SYSTEM_SUMMARY


def test_tie_rule_counts_only_singling_samples():
    flat = " ".join(SYSTEM.split())
    assert (
        "Count only samples that single out an option (for token lists, by the token-line rule "
        "in the user turn); if several options are singled out by different samples, choose "
        "the one singled out most often / most prominently." in flat
    )
    assert "If several options are named, choose the one named most often" not in SYSTEM


def test_cannot_tell_is_no_hit_and_not_a_false_alarm(tmp_path, monkeypatch):
    rows = [_cell_rows(HEAD, 56, 140, "something odd"), _cell_rows(GAUSS, 56, 140, "x")]
    path = write_jsonl(tmp_path / "r.jsonl", rows)

    def fake(calls, **kw):
        return {c.key: {"choice": _opt(c.user, mc.CANNOT), "quote": ""} for c in calls}

    monkeypatch.setattr(judge, "run_calls", fake)
    r = judge.run(_args(tmp_path, readouts=path, items=[HEAD], extra={"aggregate": "native"}))
    by = {row["id"]: row for row in r.rows}
    assert by[HEAD]["pass_unpaired"] is False and by[HEAD]["false_alarm"] is False
    assert by[GAUSS]["false_alarm"] is False and by[GAUSS]["pass"] is False
    assert by[HEAD]["twin_hits"]["gaussian"]["judge"] is False
    assert r.extras["audit"]["cannot_tell"] == 2 and r.extras["audit"]["forced_none"] == 0


def test_spec_token_note_fields():
    from wsbench.evals.introspection import SPEC

    assert SPEC.flat_types == () and SPEC.multi_select is False
    assert digest.token_note_of("introspection") == mc.TOKEN_NOTE
    assert SPEC.min_full_positions == 9 and SPEC.full_contiguous is False
    assert SPEC.metric == "pass_rate" and SPEC.not_in_macro == ""
    # audit F3: the jailbreak route (server-side fallback, then a client re-run on Sonnet 5.5)
    assert digest.FAMILY_DEFAULTS["introspection"] == {"summ_fallback": "default+claude-sonnet-5-5"}
    notes = SPEC.item_task_notes()
    assert notes[HEAD] == notes[GAUSS] == notes[f"{B0}|music"]
    assert notes["inject|neutral:meeting_note|b4|trumpets"] != notes[HEAD]


def test_lite_selects_bank_positions_for_units_and_twins():
    from wsbench import reads

    bank = judge.load()
    specs = reads.specs("introspection")
    for iid, want in ((HEAD, 140), (GAUSS, 140), (B0, 140)):
        assert specs[iid].lite_positions == {"kind": "positions", "positions": [want]}
    nm = "inject|neutral:meeting_note|b4|trumpets"
    grid = bank["renders"]["neutral:meeting_note"]["grid"]
    assert specs[nm].lite_positions["positions"] == [grid[1]] == [24]
    twin = _item(bank, nm)["twins"]["gaussian"]
    tgrid = bank["renders"][judge.render_key(_item(bank, twin))]["grid"]
    assert specs[twin].lite_positions["positions"] == [tgrid[1]]
    cells = [Cell(nm, 44, p, ("s",), None, None) for p in grid]
    assert [c.pos for c in reads.select(cells, specs, "lite")] == [24]


def test_single_layer_digest_tag(tmp_path, monkeypatch):
    from summary_fakes import FakeLLM, first_lines_digest, summary_args

    fake = FakeLLM.install(
        monkeypatch, lambda s, u, sc: None, digest=lambda u: first_lines_digest(u)
    )
    args = summary_args(EXAMPLE, tmp_path, PROMPT_VERSION, items=[HEAD], allow_missing=True)
    args = dataclasses.replace(args, layers=[56])
    judge.run(args)
    tags = [c for c in (tmp_path / "cells.jsonl").read_text().splitlines() if "digest" in c]
    assert tags and fake.n("digest") >= 1
    assert any("|56" in t for t in tags)


def test_shipped_vectors_match_bank_fingerprints():
    import hashlib

    import numpy as np

    bank = judge.load()
    arr = np.load(REPO / bank["vectors"]["concept"]["path"])
    assert arr.dtype == np.float32 and arr.shape == (125, 5120)
    for c, row in zip(bank["concepts"], arr, strict=True):
        fp = hashlib.sha256(json.dumps([round(x, 3) for x in row.tolist()]).encode()).hexdigest()
        assert fp[:16] == c["vector_fingerprint"], c["word"]
        assert abs(float(np.linalg.norm(row)) - c["vector_norm_L12"]) < 1e-3, c["word"]


def test_vector_files_sha256_match_bank():
    import hashlib

    import numpy as np

    bank = judge.load()
    for key, n in (("concept", 125), ("gaussian", 500)):
        v = bank["vectors"][key]
        p = REPO / v["path"]
        assert hashlib.sha256(p.read_bytes()).hexdigest() == v["sha256"], key
        assert v["dtype"] == "float32" and v["shape"] == [n, 5120]
        assert np.load(p).shape == (n, 5120)


def test_gaussian_vectors_unit_norm_after_normalisation():
    import numpy as np

    bank = judge.load()
    g = np.load(REPO / bank["vectors"]["gaussian"]["path"])
    norms = np.linalg.norm(g, axis=1)
    assert np.all(norms > 50) and np.all(norms < 90)  # raw randn(5120): ~sqrt(5120) = 71.6
    unit = g / norms[:, None]
    assert np.allclose(np.linalg.norm(unit, axis=1), 1.0, atol=1e-5)
    assert len({row.tobytes() for row in g}) == 500  # 500 distinct seeds, 500 distinct draws


def test_gaussian_vectors_match_seed_recipe():
    torch = pytest.importorskip("torch")
    import numpy as np

    bank = judge.load()
    g = np.load(REPO / bank["vectors"]["gaussian"]["path"])
    gauss = [it for it in bank["items"] if it["kind"] == "gaussian"]
    for it in gauss[:: len(gauss) // 10] + gauss[-1:]:
        gen = torch.Generator().manual_seed(int(it["vector"]["seed"]))
        want = torch.randn(5120, generator=gen).numpy()
        assert np.array_equal(g[it["vector"]["row"]], want), it["id"]


def test_plan_rows_steering_block_complete():
    bank = judge.load()
    words = [c["word"] for c in bank["concepts"]]
    files = {k: bank["vectors"][k]["path"] for k in ("concept", "gaussian")}
    n_rows = {"concept": 125, "gaussian": 500}
    for s in readplan.plan("introspection"):
        st = s.extra["steering"]
        if st["type"] == "none":
            assert st == {"type": "none", "beta": 0.0} and s.id.startswith("beta0|")
            continue
        for k in ("type", "beta", "inject_layer", "token_span", "formula", "vector_file"):
            assert k in st, (s.id, k)
        assert st["inject_layer"] == 12 and st["vector_file"] == files[st["type"]]
        assert 0 <= st["vector_row"] < n_rows[st["type"]]
        a, b = st["token_span"]
        assert a <= b < s.positions["positions"][0]  # the steered span precedes every read
        if st["type"] == "concept":
            assert st["concept"] == words[st["vector_row"]]
        else:
            assert isinstance(st["seed"], int)


def test_all_layer_producer_file_is_judged(tmp_path, monkeypatch):
    """Late critique fix (1): plan_sha hashes no layers, so a file read at all 64 layers carries
    the plan_sha the judge recomputes and is judged at every layer."""
    from conftest import write_sidecar

    from wsbench import reads

    every = readplan.plan("introspection", layers="all")
    assert every[0].layers == list(range(64))
    assert reads.plan_sha_rows(s.row() for s in every) == reads.plan_sha("introspection")
    rows = [
        _cell_rows(i, layer, p, "trumpets" if i == HEAD and layer == 63 else "x")
        for i in (HEAD, GAUSS)
        for layer in range(64)
        for p in range(117, 141)
    ]
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    write_sidecar(
        path, reader="t", sampling="prose1", layers=list(range(64)),
        plan_sha=reads.plan_sha("introspection"),
    )  # fmt: skip
    _scripted(monkeypatch, _quote_policy({"trumpets": "trumpets"}))
    r = judge.run(_args(tmp_path, readouts=path, items=[HEAD], extra={"aggregate": "native"}))
    by = {row["id"]: row for row in r.rows}
    assert r.config["layers_judged"] == list(range(64))
    assert by[HEAD]["hit_cells"] == [[63, p] for p in range(117, 141)]
    assert by[HEAD]["pass"] is True


class _Tiny:
    """A 4-block toy decoder (embedding + residual blocks) for the steering hook test."""

    def __init__(self):
        import torch

        torch.manual_seed(0)
        self.emb = torch.nn.Embedding(50, 8)
        blocks = [torch.nn.Linear(8, 8) for _ in range(4)]

        class Block(torch.nn.Module):
            def __init__(self, lin):
                super().__init__()
                self.lin = lin

            def forward(self, h):
                return (h + torch.tanh(self.lin(h)),)

        class Inner(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.layers = torch.nn.ModuleList(Block(b) for b in blocks)

        inner = Inner()
        emb = self.emb

        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.model = inner

            def forward(self, x, logits_to_keep=1):
                h = emb(x)
                for blk in self.model.layers:
                    h = blk(h)[0]
                return h

        self.model = Model()


def _toy_backend():
    from wsbench.produce.backend import Backend

    return Backend(model=_Tiny().model, tokenizer=None, device="cpu", model_id="tiny")


def test_produce_applies_steering_hook():
    torch = pytest.importorskip("torch")
    import numpy as np

    be = _toy_backend()
    ids = list(range(10))
    pos = list(range(10))
    plain = be.capture(ids, [1, 2], pos)
    v = np.arange(8, dtype=np.float32) - 3.0
    with be.steered(1, range(3, 6), v, 4.0):
        steered = be.capture(ids, [1, 2], pos)
    after = be.capture(ids, [1], pos)  # the hook is removed on exit
    u = torch.tensor(v) / torch.tensor(v).norm()
    h = plain[1]
    want = h.clone()
    want[3:6] = h[3:6] + 4.0 * h[3:6].norm(dim=-1, keepdim=True) * u
    assert torch.allclose(steered[1], want, atol=1e-5)
    assert torch.equal(steered[1][:3], h[:3]) and torch.equal(steered[1][6:], h[6:])
    assert not torch.allclose(steered[2][3:], plain[2][3:])  # downstream sees the steer
    assert torch.equal(after[1], plain[1])


def test_produce_refuses_unknown_steering_type(tmp_path):
    pytest.importorskip("torch")
    from wsbench.produce.producer import Producer

    p = Producer(backend=_toy_backend(), method=None)  # type: ignore[arg-type]
    spec = next(s for s in readplan.plan("introspection") if s.id == HEAD)
    bad = dataclasses.replace(spec, extra={**spec.extra, "steering": {"type": "ablate", "beta": 1}})
    with pytest.raises(ValueError, match="unknown steering type"):
        p.steering(bad)
    novec = {k: v for k, v in spec.extra["steering"].items() if k != "vector_file"}
    with pytest.raises(ValueError, match="vector_file"):
        p.steering(dataclasses.replace(spec, extra={**spec.extra, "steering": novec}))
    b0 = next(s for s in readplan.plan("introspection") if s.id == B0)
    with p.steering(b0):  # a plain forward
        pass
    import numpy as np

    want = np.load(REPO / spec.extra["steering"]["vector_file"])[
        spec.extra["steering"]["vector_row"]
    ]
    assert np.array_equal(
        p._vector(spec.extra["steering"]["vector_file"], spec.extra["steering"]["vector_row"]), want
    )


def test_quote_across_bullet_mark_verifies():
    """A prose1 s3d generation reaches the summary judge as ONE line ``- a ⁞ b``; a quote that
    spans the bullet mark verifies (``fold_quote`` maps it to a space)."""
    ln = digest.native_lines(
        [Cell("x", 44, 140, ("- a brass section\n- trumpets playing",), None, None)]
    )
    assert digest.BULLET_MARK in ln[0].text
    assert judge.quote_verified("brass section trumpets", ln)
    assert judge.quote_verified("trumpets playing", ln)


def _evidence_script():
    import importlib.util

    path = REPO / "scripts/introspection_offline_evidence.py"
    spec = importlib.util.spec_from_file_location("introspection_offline_evidence", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_lite_support_table_uses_no_verdicts():
    ev = _evidence_script()
    rid = "inject|neutral:meeting_note|b4|trumpets"
    lines = [
        ("trumpets", "[L44 pos 31]"),
        ("brass trumpets", "[L48 pos 24]"),
        ("x", "[L44 pos 24]"),
    ]
    t = ev.lite_support_table({rid: lines}, {rid: ["trumpets"]}, {rid: (31, 24)})
    assert t == {"n_gold_lines": 2, "final_token": 1, "grid1": 1}
    assert ev.choose({"a": t})["neutral_lite_rule"] == "final_token"  # no >10-point win
    win = ev.choose({"a": {"n_gold_lines": 10, "final_token": 1, "grid1": 5}})
    assert win["neutral_lite_rule"] == "grid[1] (bank)"
    with pytest.raises(TypeError):  # a judged row is refused: no verdict enters the choice
        ev.lite_support_table({rid: {"pass": True, "summary_evidence": []}}, {}, {})
    with pytest.raises(TypeError):
        ev.lite_support_table({rid: [{"pass": True}]}, {}, {})

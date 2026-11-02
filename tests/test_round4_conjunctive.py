"""Round 4 (Camila r2): conjunctive_association.

1. "fix the too strict conjunctive association cases" (re-audit r2: q10_c, q06_i, ... lone
   verbatim gold lines the one-pick MC missed inside an 8K all-layer shard). A sharded draw also
   asks for a candidate list; the draw's candidates are its one pick plus the list, each through
   the unchanged quote gate and quote re-judge. Kept: the majority of draws and the inverted veto.
2. The MC leakage standard: bank v3 adds two never-gold grid confusers (and their twins) per
   twinned cluster; bank v4 (Fable on #202) widens every list to 22 non-twin options.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from wsbench.evals.conjunctive_association import judge as cj
from wsbench.evals.conjunctive_association import prompts, score

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "evals/conjunctive_association/items_v2.json"
V3 = ROOT / "evals/conjunctive_association/items_v3.json"
GOLDLINE = "GOLDLINE relief hidden"


def _item_with_twin():
    from wsbench.mcjudge import load_bank

    for it in load_bank("conjunctive_association"):
        shown, gold, _c = cj.build_options(it)
        inv = cj.inverted_position(it, shown)
        if inv is not None:
            return it, shown, gold, inv
    raise AssertionError("no item with an inverted twin")


def _run(tmp_path, monkeypatch, iid, one_pick, cands, rejudge, cap=400, extra_rows=()):
    """A sharded summary-mode run of one item: ``one_pick(user)`` answers the one-pick MC,
    ``cands(user)`` the candidate list (a list of {choice, quote}), ``rejudge(user)`` the
    quote-only re-judge (a choice)."""
    from summary_fakes import FakeLLM, summary_args
    from test_conjunctive_association import _all_lines, _cells_file

    rows = [
        {"id": iid, "layer": 20 + 4 * (i % 11), "pos": 40 + i, "samples": [f"filler {i} " * 9]}
        for i in range(24)
    ]
    rows.append({"id": iid, "layer": 60, "pos": 90, "samples": [GOLDLINE]})
    rows += list(extra_rows)
    path = _cells_file(tmp_path, rows)
    monkeypatch.setattr(cj, "SHARD_CHARS", cap)

    def answer(system, user, schema):
        name = schema.get("name")
        if name == "quote_mc":
            return {"choice": rejudge(user), "quote": ""}
        if name == "readout_mc_candidates":
            assert system == prompts.SYSTEM_SUMMARY_CANDIDATES
            return {"candidates": cands(user)}
        return one_pick(user)

    fake = FakeLLM.install(monkeypatch, answer, digest=_all_lines)
    res = cj.run(summary_args(path, tmp_path / f"o{cap}", "pv", items=[iid], allow_missing=True))
    return res, fake


# ---- 1. the too-strict shape now passes (q10_c / q06_i: the one pick says cannot tell)


def test_lone_gold_line_found_by_the_candidate_list_passes(tmp_path, monkeypatch):
    it, shown, gold, _inv = _item_with_twin()
    cannot = len(shown)
    res, fake = _run(
        tmp_path,
        monkeypatch,
        it["id"],
        one_pick=lambda u: {"choice": cannot, "quote": ""},  # missed in the crowded shard
        cands=lambda u: [{"choice": gold, "quote": GOLDLINE}] if GOLDLINE in u else [],
        rejudge=lambda u: gold,
    )
    row = res.rows[0]
    assert row["n_shards"] > 1 and row["pick"] == "gold" and row["correct"]
    assert row["quote"] == GOLDLINE
    assert "+shard8k+cand3" in res.config["prompt_version"]
    # both calls were made for every shard draw, on the same shard text
    names = [n for n, _s, _u in fake.calls]
    assert names.count("readout_mc_candidates") == names.count("readout_mc")


def test_the_one_pick_still_counts_beside_the_list(tmp_path, monkeypatch):
    """q06_a / q06_f / q06_g: the one pick found the gold; an empty candidate list never removes
    it (the candidates add to the one pick)."""
    it, shown, gold, _inv = _item_with_twin()
    res, _ = _run(
        tmp_path,
        monkeypatch,
        it["id"],
        one_pick=lambda u: (
            {"choice": gold, "quote": GOLDLINE}
            if GOLDLINE in u
            else {"choice": len(shown), "quote": ""}
        ),
        cands=lambda u: [],
        rejudge=lambda u: gold,
    )
    assert res.rows[0]["pick"] == "gold"


def test_list_requote_of_the_one_picks_option_is_kept(tmp_path, monkeypatch):
    """The one pick names the gold with a quote that is in no readout; the list names the gold
    again with the verbatim line: the list's candidate is gated on its own."""
    it, shown, gold, _inv = _item_with_twin()
    res, _ = _run(
        tmp_path,
        monkeypatch,
        it["id"],
        one_pick=lambda u: (
            {"choice": gold, "quote": "a paraphrase in no readout"}
            if GOLDLINE in u
            else {"choice": len(shown), "quote": ""}
        ),
        cands=lambda u: [{"choice": gold, "quote": GOLDLINE}] if GOLDLINE in u else [],
        rejudge=lambda u: gold,
    )
    assert res.rows[0]["pick"] == "gold" and res.rows[0]["quote"] == GOLDLINE


# ---- 1. the too-lenient shapes still fail


def test_candidate_quote_must_verify_in_its_shard(tmp_path, monkeypatch):
    it, shown, gold, _inv = _item_with_twin()
    res, fake = _run(
        tmp_path,
        monkeypatch,
        it["id"],
        one_pick=lambda u: {"choice": len(shown), "quote": ""},
        cands=lambda u: [{"choice": gold, "quote": "a quote that is in no readout"}],
        rejudge=lambda u: gold,
    )
    assert res.rows[0]["pick"] != "gold" and not res.rows[0]["correct"]
    assert not any(n == "quote_mc" for n, _s, _u in fake.calls)  # unverified: no re-judge


def test_candidate_quote_must_rejudge_to_the_gold(tmp_path, monkeypatch):
    it, shown, gold, _inv = _item_with_twin()
    res, _ = _run(
        tmp_path,
        monkeypatch,
        it["id"],
        one_pick=lambda u: {"choice": len(shown), "quote": ""},
        cands=lambda u: [{"choice": gold, "quote": GOLDLINE}] if GOLDLINE in u else [],
        rejudge=lambda u: len(shown),  # the quote alone does not state the gold: partial
    )
    row = res.rows[0]
    assert "gold_partial" in row["shard_picks"] and "gold" not in row["shard_picks"]
    assert not row["correct"]


def test_an_inverted_candidate_vetoes_the_draw(tmp_path, monkeypatch):
    it, shown, gold, inv = _item_with_twin()
    res, _ = _run(
        tmp_path,
        monkeypatch,
        it["id"],
        one_pick=lambda u: {"choice": len(shown), "quote": ""},
        cands=lambda u: (
            [{"choice": gold, "quote": GOLDLINE}, {"choice": inv, "quote": "filler 0"}]
            if GOLDLINE in u and "filler 0 " in u
            else [{"choice": gold, "quote": GOLDLINE}]
            if GOLDLINE in u
            else [{"choice": inv, "quote": "filler 0"}]
            if "filler 0 " in u
            else []
        ),
        rejudge=lambda u: inv if "filler 0" in u else gold,
    )
    assert res.rows[0]["pick"] == "inverted" and not res.rows[0]["correct"]


def test_one_gold_draw_of_three_still_fails(tmp_path, monkeypatch):
    """The majority stays: a candidate gold in one draw of three is no pass."""
    it, shown, gold, _inv = _item_with_twin()
    seen: dict[str, int] = {}

    def cands(u):
        if GOLDLINE not in u:
            return []
        seen[u] = seen.get(u, 0) + 1
        return [{"choice": gold, "quote": GOLDLINE}] if seen[u] == 1 else []

    res, _ = _run(
        tmp_path,
        monkeypatch,
        it["id"],
        one_pick=lambda u: {"choice": len(shown), "quote": ""},
        cands=cands,
        rejudge=lambda u: gold,
    )
    assert res.rows[0]["pick"] != "gold" and not res.rows[0]["correct"]


def test_single_shard_digest_asks_no_candidate_list(tmp_path, monkeypatch):
    it, shown, gold, _inv = _item_with_twin()
    res, fake = _run(
        tmp_path,
        monkeypatch,
        it["id"],
        one_pick=lambda u: {"choice": len(shown), "quote": ""},
        cands=lambda u: [{"choice": gold, "quote": GOLDLINE}],
        rejudge=lambda u: gold,
        cap=10**6,
    )
    assert "n_shards" not in res.rows[0] and res.rows[0]["pick"] == "cannot_tell"
    assert not any(n == "readout_mc_candidates" for n, _s, _u in fake.calls)
    assert "+cand3" not in res.config["prompt_version"]


def test_fold_candidates_order():
    f = cj.fold_candidates
    sub = {"choice": 1, "quote": "q", "quote_ok": True}
    assert f({"cands": []})["pick"] == "cannot_tell"
    d = f({"cands": [{**sub, "pick": "distractor"}, {**sub, "choice": 2, "pick": "gold"}]})
    assert d["pick"] == "gold" and d["choice"] == 2
    d = f({"cands": [{**sub, "pick": "gold"}, {**sub, "pick": "inverted"}]})
    assert d["pick"] == "inverted"
    d = f({"cands": [{**sub, "pick": "api_fail"}, {**sub, "pick": "cannot_tell"}]})
    assert d["pick"] == "api_fail" and d["failed_stage"] == "quote_check"


def test_candidate_chance_floor():
    # 4 distinct uniform picks (the one pick + 3) among m = 20 content options, gold listed and
    # its twin not: 4/20 - 4*3/(20*19)
    p = score.candidate_p(21, 4, True)
    assert p == pytest.approx(4 / 20 - 12 / 380)
    m = 3 * p**2 - 2 * p**3
    got = score.mean_chance([["x"] * 21], 3, shards=[8], candidates=4, twins=[True])
    assert got == pytest.approx(1 - (1 - m) ** 8)
    # a one-shard item keeps the one-pick floor
    assert score.mean_chance([["x"] * 21], 3, shards=[1], candidates=4, twins=[True]) == (
        pytest.approx(3 * (1 / 21) ** 2 - 2 * (1 / 21) ** 3)
    )


# ---- 2. bank v3 (MC leakage standard)


def test_v3_bank_is_generated():
    script = ROOT / "scripts/conjunctive/make_v3_bank.py"
    r = subprocess.run(
        [sys.executable, str(script), "build", "--check"], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_v3_adds_two_never_gold_grid_confusers_per_twinned_cluster():
    v2 = {it["id"]: it for it in json.loads(V2.read_text())}
    v3 = json.loads(V3.read_text())
    golds: dict[str, set[str]] = {}
    for it in v3:
        golds.setdefault(it["cluster"], set()).add(it["gold_label"])
    for it in v3:
        old = v2[it["id"]]
        for k in ("stimulus", "gold_label", "contrast_label", "inverted_label"):
            assert it[k] == old[k]
        assert it["bank_version"] == 3
        assert it["mc_options"][: len(old["mc_options"])] == old["mc_options"]
        added = it["mc_options"][len(old["mc_options"]) :]
        tw = it["twin_of"]
        assert all(tw[tw[o]] == o for o in tw)
        assert not set(added) & golds[it["cluster"]]  # never a gold of any item
        if it["cluster"] == "q06":
            assert added == []  # no twins: its options-only floor is already uniform
            continue
        # two new grid options, then their two twins (the v2 twin rule: same form)
        assert len(added) == 4 and all(o in tw for o in added)
        assert [tw[o] for o in added[:2]] == added[2:]
    n_shown = sorted({len(cj.build_options(it)[0]) for it in v3})
    assert n_shown == [11, 23, 25]


def test_v3_new_values_are_frozen_with_their_slots():
    vals = json.loads((ROOT / "evals/conjunctive_association/v3_new_values.json").read_text())
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "make_v3_bank", ROOT / "scripts/conjunctive/make_v3_bank.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "scripts/conjunctive"))
    spec.loader.exec_module(mod)
    assert set(vals["values"]) == set(mod.SLOTS)
    for c, v in vals["values"].items():
        assert (v["axis"], v["slot"]) == mod.SLOTS[c] and v["new"]
    # the readout-favour rejections are recorded
    assert "supervisor" in vals["avoid"]["q04"] and vals["values"]["q04"]["new"] == "her roommate"


# ---- 3. bank v4 (Fable on #202: widen every list to ~16-22 non-twin options; v3 stays frozen)

V4 = ROOT / "evals/conjunctive_association/items_v4.json"
GOLDEN_V4 = json.loads((ROOT / "tests/golden/conjunctive_association_options_v4.json").read_text())


def _v4_module():
    import importlib.util

    sys.path.insert(0, str(ROOT / "scripts/conjunctive"))
    spec = importlib.util.spec_from_file_location(
        "make_v4_bank", ROOT / "scripts/conjunctive/make_v4_bank.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _n_non_twin(it: dict) -> int:
    # every twin pair is one grid-form option + its role-swapped twin
    return len(it["mc_options"]) - len(it["twin_of"]) // 2


def test_v4_bank_is_generated():
    script = ROOT / "scripts/conjunctive/make_v4_bank.py"
    r = subprocess.run(
        [sys.executable, str(script), "build", "--check"], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_v4_build_check_catches_a_stale_file():
    mod = _v4_module()
    frozen = json.loads(mod.VALUES.read_text())["clusters"]
    text = mod.render(mod.build(mod._v3(), frozen))
    assert text == V4.read_text()
    # reordering two chosen proposals changes the lists, so the committed file no longer matches
    chosen = mod.usable("q01", frozen, set(mod._v3()[0]["mc_options"]))
    prop = list(frozen["q01"]["proposed"])
    i, j = prop.index(chosen[0]), prop.index(chosen[1])
    prop[i], prop[j] = prop[j], prop[i]
    swapped = {**frozen, "q01": {**frozen["q01"], "proposed": prop}}
    assert mod.render(mod.build(mod._v3(), swapped)) != V4.read_text()
    # and too few usable proposals is refused, never a short list
    rest = [v for v in frozen["q01"]["proposed"] if v != chosen[0]]
    cut = {**frozen, "q01": {**frozen["q01"], "proposed": rest}}
    with pytest.raises(ValueError, match="usable proposals"):
        mod.build(mod._v3(), cut)


def test_v4_widens_every_list_to_22_non_twin_options():
    v3 = {it["id"]: it for it in json.loads(V3.read_text())}
    v4 = json.loads(V4.read_text())
    golds: dict[str, set[str]] = {}
    for it in v4:
        golds.setdefault(it["cluster"], set()).add(it["gold_label"])
    for it in v4:
        old = v3[it["id"]]
        for k in ("stimulus", "gold_label", "contrast_label", "inverted_label"):
            assert it[k] == old[k]
        assert it["bank_version"] == 4
        assert it["mc_options"][: len(old["mc_options"])] == old["mc_options"]  # v3 kept
        added = it["mc_options"][len(old["mc_options"]) :]
        tw = it["twin_of"]
        assert all(tw[tw[o]] == o for o in tw) and len(set(it["mc_options"])) == len(
            it["mc_options"]
        )
        assert not set(added) & golds[it["cluster"]]  # never a gold of any item
        assert _n_non_twin(it) == 22, it["id"]  # v3: 12 (q06: 10)
        assert _n_non_twin(old) in (10, 12)
        if it["cluster"] == "q06":
            assert tw == {} and len(added) == 12  # one person: no twins
            continue
        # every new two-person option brings its twin, so a twin-free option is no odd one out
        assert all(o in tw for o in added)
        assert len(added) == 20
    assert sorted({len(cj.build_options(it)[0]) for it in v4}) == [23, 43, 45]


def test_options_match_v4_golden():
    from wsbench.mcjudge import load_bank

    for it in load_bank("conjunctive_association"):
        shown, gold_pos, _c = cj.build_options(it)
        assert {"shown": shown, "gold_pos": gold_pos} == GOLDEN_V4[it["id"]], it["id"]


def _rec(proposed, hits=None, n_new=2):
    return {
        "q01": {
            "axis": "relation",
            "slot": "her parent",
            "slot_options": [
                "grief over the sudden accidental death of her parent",
                "guilt over the sudden accidental death of her parent",
            ],
            "n_new": n_new,
            "existing_values": ["parent", "spouse", "her sibling"],
            "proposed": proposed,
            "n_samples": 1000,
            "hits": hits or {},
        }
    }


def test_v4_screen_skips_hand_rejected_and_readout_favoured_values():
    mod = _v4_module()
    assert "her twin brother" in mod.REJECT["q01"]  # an instance of her sibling
    got = mod.usable(
        "q01",
        _rec(
            ["her twin brother", "her aunt", "her best sibling", "her uncle", "her niece"],
            hits={"her aunt": 21, "her uncle": 20},  # 2.1% vs 2.0% of 1000 samples
        ),
        set(),
    )
    # twin brother: hand screen; aunt: over the readout share; "best sibling": the head word of
    # a current value; uncle (exactly at the share) and niece are taken
    assert got == ["her uncle", "her niece"]


def test_v4_screen_takes_clean_values_in_proposal_order():
    mod = _v4_module()
    got = mod.usable("q01", _rec(["her niece", "her uncle", "her aunt"]), set())
    assert got == ["her niece", "her uncle"]  # n_new = 2: the first two clean proposals
    # and a value that would recreate an existing option is skipped
    existing = {"grief over the sudden accidental death of her niece"}
    assert mod.usable("q01", _rec(["her niece", "her uncle", "her aunt"]), existing) == [
        "her uncle",
        "her aunt",
    ]


def test_v4_motive_head_word_is_the_motive_noun():
    mod = _v4_module()
    assert mod.head("out of fear of being outshone", "motive") == "fear"
    assert mod.head("under pressure from a rival company", "motive") == "pressure"
    assert mod.head("her brother-in-law", "relation") == "brother-in-law"
    assert mod.head("the court ruling", "content") == "ruling"
    p = mod.head_pattern("aunt")
    assert p.search("her Aunts said") and not p.search("a gauntlet") and not p.search("aunty")


def test_v4_options_are_not_in_the_model_prompt(monkeypatch):
    """Options are shown to the judge only: the producer's plan (chat_summarize: story + the
    summarize suffix) holds no option text, and its sha is the same as on bank v3, so every
    cached readout stays valid for v4."""
    from wsbench import readplan, reads

    rows = readplan.plan("conjunctive_association")
    by_id = {it["id"]: it for it in json.loads(V4.read_text())}

    def leaks(spec, options):
        rendered = " ".join(
            str(x or "") for x in (spec.text, spec.suffix, spec.system, spec.prefill, spec.messages)
        )
        return [o for o in options if o in rendered]

    for s in rows:
        assert s.render == "chat_summarize" and s.text == by_id[s.id]["stimulus"]
        assert leaks(s, by_id[s.id]["mc_options"]) == []
    import dataclasses

    bad = dataclasses.replace(rows[0], text=rows[0].text + " " + by_id[rows[0].id]["gold_label"])
    assert leaks(bad, by_id[rows[0].id]["mc_options"]) != []  # the check would catch a leak
    sha4 = reads.plan_sha("conjunctive_association")
    monkeypatch.setattr(readplan, "bank_path", lambda family: V3)
    assert reads.plan_sha("conjunctive_association") == sha4


def test_v4_round2_readout_share_admits_typical_values_below_two_percent():
    """Round 2: the readout cap is 2% (round 1: 1%), so a typical value that readouts mention
    in 1.5% of samples (q01 "her best friend") is taken, and one over 2% still is not."""
    mod = _v4_module()
    assert mod.MAX_READOUT_SHARE == 0.02
    rec = _rec(["her best friend", "her roommate"], hits={"her best friend": 15}, n_new=1)
    assert mod.usable("q01", rec, set()) == ["her best friend"]
    rec = _rec(["her best friend", "her roommate"], hits={"her best friend": 21}, n_new=1)
    assert mod.usable("q01", rec, set()) == ["her roommate"]


def test_v4_round2_rejects_synonyms_and_instances_of_current_values():
    """The round-2 hand screen: a synonym or instance of a current value is never taken, a
    distinct typical relation is."""
    mod = _v4_module()
    rec = {
        **_rec([], n_new=1)["q01"],
        "slot": "her sibling",
        "slot_options": ["x her sibling", "y her sibling"],
    }
    for bad in ("her husband", "her mother", "her sister", "her ex-husband", "her best friend"):
        assert bad in mod.REJECT["q07"]
        assert mod.usable("q07", {"q07": {**rec, "proposed": [bad]}}, set()) == []
    good = {"q07": {**rec, "proposed": ["her mother-in-law"]}}
    assert mod.usable("q07", good, set()) == ["her mother-in-law"]
    for c, bad in (
        ("q04", "her coworker"),
        ("q09", "his teenage daughter"),
        ("q03", "his ex-wife"),
    ):
        assert bad in mod.REJECT[c]


def test_v4_frozen_values_respect_the_screens():
    """No value in the built bank is hand-rejected for its cluster, and every re-asked cluster
    keeps its earlier proposals on record (round 1, and round 2a when asked again)."""
    mod = _v4_module()
    frozen = json.loads(mod.VALUES.read_text())["clusters"]
    v3 = mod._v3()
    for c in mod.SLOTS:
        rec = frozen[c]
        assert rec["round"] == 2 and rec["round1_proposed"]
        chosen = mod.usable(
            c, frozen, set(next(it for it in v3 if it["cluster"] == c)["mc_options"])
        )
        assert not set(chosen) & set(mod.REJECT.get(c, {}))
        assert all(
            rec["hits"].get(v, 0) / rec["n_samples"] <= mod.MAX_READOUT_SHARE for v in chosen
        )
    for c in ("q03", "q04", "q07"):  # round 2b: re-asked after round 2a was screened out
        assert (
            frozen[c]["round2a_proposed"] and frozen[c]["round2a_proposed"] != frozen[c]["proposed"]
        )
    assert set(mod.ROUND1_VALUES) == set(mod.SLOTS)


def test_v4_history_keeps_every_earlier_round():
    mod = _v4_module()
    r1 = {"round": 1, "proposed": ["a"], "hits": {"a": 1}}
    assert mod._history(r1) == {"round1_proposed": ["a"], "round1_hits": {"a": 1}}
    r2 = {"round": 2, "proposed": ["b"], "hits": {"b": 2}, "round1_proposed": ["a"],
          "round1_hits": {"a": 1}}  # fmt: skip
    assert mod._history(r2) == {
        "round1_proposed": ["a"],
        "round1_hits": {"a": 1},
        "round2a_proposed": ["b"],
        "round2a_hits": {"b": 2},
    }

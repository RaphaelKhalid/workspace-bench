"""Audit fixes F1 / F2 / F3 / F11 (digest side), 2026-10-31: the per-layer union digest, per-claim
counts, refused / collapsed digests, and the arithmetic first-number consensus. Every fix that
relaxes something has a test that the matching too-lenient shape still fails."""

import json
from pathlib import Path

import pytest
from conftest import native_args

from wsbench import digest
from wsbench import results as results_mod
from wsbench.cache import Cache
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.llm import Spend
from wsbench.readouts import Cell
from wsbench.registry import JudgeArgs
from wsbench.results import (
    FamilyResult,
    decided_outcomes,
    layer_union_check,
    macro,
    markdown_table,
    not_measurable,
    on_shared_ids,
    shared_floor_text,
)


def _args(tmp_path: Path, **extra: str) -> JudgeArgs:
    return native_args(
        readouts=tmp_path / "r.jsonl",
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version="t")),
        layers=None,
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        extra={"aggregate": "summary", **extra},
    )


def _prose(i: str, layer: int, pos: int, *samples: str) -> Cell:
    return Cell(i, layer, pos, tuple(samples), None, None, None)


class Scripted:
    """A digest fake: ``reply(system, user) -> result``; records every (system, user)."""

    def __init__(self, monkeypatch, reply):
        self.calls: list[tuple[str, str]] = []
        self.reply = reply
        monkeypatch.setattr(digest.llm, "stream_json", self.stream_json)

    def stream_json(self, prompts, *, on_result, **_kw):
        for i, (system, user) in enumerate(prompts):
            self.calls.append((system, user))
            on_result(i, self.reply(system, user))
        return Spend()


def _entry(evidence: str, key: str = "", count: int | None = None, where: str = "") -> dict:
    e = {"statement": f"S {evidence}", "key": key, "where": where, "evidence": evidence}
    if count is not None:
        e["count"] = count
    return e


def _collapse(tmp_path, fam, cells_by_item, **kw):
    with Cache(tmp_path / "c.jsonl") as cache:
        return digest.collapse(
            fam,
            cells_by_item,
            args=_args(tmp_path, **kw.pop("extra", {})),
            cache=cache,
            spend=Spend(),
            preflight=None,
            task_note="t",
            **kw,
        )


# ---------------------------------------------------------------- F2: per-claim counts


def test_count_is_the_note_takers_claim_count_capped_by_the_key_word():
    lines = [digest.Line(f"November is in the list: January, ..., November {k}") for k in range(9)]
    lines.append(digest.Line("After July comes **November**"))
    res = {"items": [_entry("After July comes **November**", "November", count=1)]}
    kept, _ = digest.ground(res, lines, 10)
    # the key word is in 10 samples (month lists), the claim in one: the marker is the claim's
    assert kept[0].count == 1 and kept[0].support == "1 sample"
    assert digest.support_of("November", lines) == "many"  # the old key-word bucket


def test_inflated_count_is_capped_at_the_key_word_count():
    """Leniency guard (F2): the note-taker cannot claim more samples than hold the key."""
    lines = [digest.Line("Pacific, the largest"), digest.Line("Atlantic"), digest.Line("x")]
    res = {"items": [_entry("Pacific, the largest", "Pacific", count=999)]}
    kept, _ = digest.ground(res, lines, 10)
    assert kept[0].count == 1 and kept[0].support == "1 sample"
    for bad in (None, "many", True, -3, 0):
        res = {"items": [_entry("Pacific, the largest", "Pacific", count=bad)]}
        kept, _ = digest.ground(res, lines, 10)
        assert kept[0].count == 1  # a missing / malformed count falls back to the cap


def test_support_text():
    assert digest.support_text(1) == "1 sample"
    assert digest.support_text(7, 3) == "7 samples, 3 layers"
    assert digest.support_text(4, 1, "first number of 4 of 4 samples at [L52 pos -8]") == (
        "4 samples; first number of 4 of 4 samples at [L52 pos -8]"
    )


# ---------------------------------------------------------------- F1: per-layer union


def _layers_item(n_layers: int = 3) -> list[Cell]:
    cells = []
    for k in range(n_layers):
        layer = 20 + 4 * k
        cells += [_prose("a", layer, p, f"gold Pacific L{layer} p{p}") for p in range(3)]
    cells.append(_prose("a", 20, 9, "rival Atlantic once"))
    cells.append(_prose("a", 28, 9, "rare decisive Mariana at L28"))
    return cells


def _per_layer_reply(system, user):
    lines = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
    golds = [ln for ln in lines if ln.startswith("gold")]
    items = [_entry(golds[0], "Pacific", count=len(golds))] if golds else []
    rare = [_entry(ln, ln.split()[1], count=1) for ln in lines if not ln.startswith("gold")]
    return {"items": items, "rare": rare}


def test_union_digests_each_layer_and_sums_claim_counts(tmp_path, monkeypatch):
    fake = Scripted(monkeypatch, _per_layer_reply)
    col = _collapse(tmp_path, "test_af_union", {"a": _layers_item(3)})
    assert len(fake.calls) == 3  # one digest per read layer
    for _s, u in fake.calls:  # each bundle holds exactly one layer
        assert len({ln.split()[0] for ln in u.splitlines() if ln.startswith("[L")}) == 1
    st = col.statements["a"]
    gold = next(x for x in st if x["key"] == "Pacific")
    assert gold["count"] == 9 and gold["layers"] == [20, 24, 28]
    assert gold["support"] == "9 samples, 3 layers"
    # the rare decisive line of ONE layer survives the merge (F1), counted once
    rare = next(x for x in st if x["key"] == "decisive")
    assert rare["count"] == 1 and rare["tier"] == "rare"
    # leniency guard: the rival seen once is NOT promoted by the merge
    rival = next(x for x in st if x["key"] == "Atlantic")
    assert rival["support"] == "1 sample"
    assert col.summaries["a"].splitlines()[0].startswith("[9 samples, 3 layers] gold Pacific")
    # F1: the layer histogram is logged per item and in extras
    # (the merged gold claim is ONE line, the evidence of its best-supported member, L20)
    assert col.layer_hist["a"] == {20: 2, 28: 1}
    ex = col.extras()
    assert ex["summary_layer_hist"] == {"20": 2, "28": 1}
    assert ex["n_digest_parts"] == 3 and ex["summary_top_layer_share"] == pytest.approx(2 / 3)
    assert col.row("a")["summary_layers"] == {"20": 2, "28": 1}


def test_union_cache_key_is_the_single_layer_key(tmp_path, monkeypatch):
    Scripted(monkeypatch, _per_layer_reply)
    _collapse(tmp_path, "test_af_union", {"a": _layers_item(2)})
    keys = {json.loads(x)["key"] for x in (tmp_path / "c.jsonl").read_text().splitlines()}
    assert {"digest:a|20", "digest:a|24"} <= keys  # what a layers=[L] run keys


def test_joint_is_the_old_single_call(tmp_path, monkeypatch):
    fake = Scripted(monkeypatch, _per_layer_reply)
    col = _collapse(
        tmp_path, "test_af_union", {"a": _layers_item(3)}, extra={"summ_layers": "joint"}
    )
    assert len(fake.calls) == 1 and col.summaries["a"]
    assert digest.prompt_version("pv", _args(tmp_path, summ_layers="joint")).endswith(
        "-extractive-joint+" + digest.SUMMARY_JUDGE_VERSION
    )


def test_numbers_digest_stays_joint_and_capped(tmp_path, monkeypatch):
    """Leniency guard (F1): the five-number budget does NOT scale with the layers."""

    def reply(system, user):
        lines = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
        nums = dict.fromkeys(ln for ln in lines if ln[:1].isdigit())  # one entry per number
        return {"items": [_entry(n, n.split()[0]) for n in nums], "rare": []}

    fake = Scripted(monkeypatch, reply)
    # distinct supports (number 20 + j in j + 1 of the 48 samples): no tie at the fifth -> five
    said = [f"{20 + j} is it" for j in range(9) for _ in range(j + 1)] + ["nothing"] * 3
    cells = [
        _prose("a", ly, p, *said[4 * i : 4 * i + 4])
        for i, (ly, p) in enumerate((ly, p) for ly in (20, 24, 28) for p in range(4))
    ]
    col = _collapse(tmp_path, "chain_intermediates", {"a": cells})
    assert len(fake.calls) == 1  # joint
    assert len([x for x in col.statements["a"] if x["tier"] == "numbers"]) == 5
    # round 4 r2 (tie_cut keeps every number tied with the fifth, support 1 included): a flat
    # run of one-off numbers is one tie, bounded by the 5 + summ_ties candidates, never x layers
    flat = [_prose("a", ly, p, f"{ly + p} is it") for ly in (20, 24, 28) for p in range(4)]
    col = _collapse(tmp_path / "flat", "chain_intermediates", {"a": flat})
    assert len([x for x in col.statements["a"] if x["tier"] == "numbers"]) == 10


def test_partial_layers_are_recorded(tmp_path, monkeypatch):
    def reply(system, user):
        return None if "L24" in user else _per_layer_reply(system, user)

    Scripted(monkeypatch, reply)
    col = _collapse(tmp_path, "test_af_union", {"a": _layers_item(3)})
    assert col.summaries["a"] and col.partial == {"a": [24]}
    assert col.extras()["n_items_partial"] == 1 and col.row("a")["summary_partial_layers"] == [24]
    # every layer unserved: unsummarized, never empty
    Scripted(monkeypatch, lambda s, u: None)
    col = _collapse(tmp_path / "x", "test_af_union", {"a": _layers_item(2)})
    assert col.unsummarized == {"a"} and not col.empty


def test_partial_layers_beyond_a_fifth_are_undecided(tmp_path, monkeypatch):
    """1 of 3 layers REFUSED (33% > 20%): the item is unsummarized (undecided), never judged on
    the two served layers; the refused layer is still recorded on the row and in extras. 1 of 6
    refused (<= 20%) still judges, and a failed (not refused) layer never undecides."""
    from wsbench import llm

    def refuse(system, user):
        return llm.REFUSED_JSON if "L24" in user else _per_layer_reply(system, user)

    Scripted(monkeypatch, refuse)
    col = _collapse(tmp_path, "test_af_union", {"a": _layers_item(3)})
    assert col.unsummarized == {"a"} and "a" not in col.summaries
    assert col.cells["a"].samples == ("",) and col.reasons["a"] == "partial_refused"
    row, ex = col.row("a"), col.extras()
    assert row["summary_state"] == "unsummarized" and row["summary_partial_layers"] == [24]
    assert row["summary_refused_layers"] == [24] and row["summary_partial_undecided"] is True
    assert ex["n_items_partial"] == 1 and ex["n_items_partial_undecided"] == 1
    assert ex["n_items_partial_refused"] == 1 and digest.PARTIAL_UNDECIDED_SHARE == 0.2

    col = _collapse(tmp_path / "six", "test_af_union", {"a": _layers_item(6)})
    assert col.summaries["a"] and col.refused_layers == {"a": [24]}
    assert col.row("a")["summary_partial_undecided"] is False

    Scripted(monkeypatch, lambda s, u: None if "L24" in u else _per_layer_reply(s, u))
    col = _collapse(tmp_path / "failed", "test_af_union", {"a": _layers_item(3)})
    assert col.summaries["a"] and col.partial == {"a": [24]} and not col.refused_layers


# ---------------------------------------------------------------- F1: hierarchical merge


@pytest.fixture
def hier(monkeypatch):
    monkeypatch.setattr(digest, "COUNT_TOKENS_ABOVE", 0.0)
    monkeypatch.setattr(
        digest.llm, "count_tokens", lambda m, ps, concurrency=8: [len(u) for _s, u in ps]
    )
    monkeypatch.setitem(
        digest.FAMILY_DEFAULTS,
        "test_af_hier",
        {"summ_token_cap": "700", "summ_max": "3", "summ_rare": "0", "summ_layers": "joint"},
    )


def test_chunk_claims_seen_five_times_survive_the_final(tmp_path, monkeypatch, hier):
    """F1: a claim stated by >= CHUNK_KEEP_MIN samples in the chunk digests is kept even when the
    final call drops it; leniency guard: one stated by fewer is not."""

    def reply(system, user):
        if "(support:" in user:  # the final digest keeps only the 'keep' line
            ln = next(x[2:] for x in user.splitlines() if x.startswith("- keep"))
            return {"items": [_entry(ln, "keep", count=1)], "rare": []}
        lines = [x[2:] for x in user.splitlines() if x.startswith("- ")]
        out = []
        for word, n in (("keep", 1), ("five", 5), ("four", 4), ("once", 1)):
            hit = next((x for x in lines if x.startswith(word)), None)
            if hit:
                out.append(_entry(hit, word, count=n))
        return {"items": out, "rare": []}

    Scripted(monkeypatch, reply)
    cells = []
    for ly in (20, 24, 28):  # each layer carries bulk no digest cites, so only chunks fit
        cells.append(_prose("a", ly, 0, f"keep L{ly}"))
        cells += [_prose("a", ly, p, f"five L{ly} p{p}") for p in (1, 2)]
        cells += [_prose("a", ly, p, f"four L{ly} p{p}") for p in (3, 4)]
        cells.append(_prose("a", ly, 5, "bulk " + "b" * 400))
    cells.append(_prose("a", 20, 6, "once L20 only"))
    col = _collapse(tmp_path, "test_af_hier", {"a": cells})
    assert col.chunks.get("a", 0) >= 2
    keys = {x["key"]: x for x in col.statements["a"]}
    assert "keep" in keys and keys["keep"]["count"] == 3  # the chunk counts, summed
    # 'five': 5 claimed per chunk, capped at the 2 samples holding it -> 6 over 3 chunks: kept
    assert keys["five"]["count"] == 6 and keys["five"]["layers"] == [20, 24, 28]
    assert keys["four"]["count"] == 6  # same shape: a claim stated 6 times is kept too
    # leniency guard: a claim seen once, that the final dropped, stays dropped
    assert "once" not in keys
    assert col.diag["n_chunk_claims_kept"] == 2


# ---------------------------------------------------------------- F3: collapsed digests


def _many(n: int, layer: int = 20) -> list[Cell]:
    return [_prose("a", layer, p, f"thing{p} said here") for p in range(n)]


def test_collapsed_digest_is_reasked_and_the_fuller_answer_kept(tmp_path, monkeypatch):
    def reply(system, user):
        lines = [x[2:] for x in user.splitlines() if x.startswith("- ")]
        k = 2 if not fake.calls[:-1] else 8  # the first ask collapses, the re-ask does not
        return {"items": [_entry(x, x.split()[0]) for x in lines[:k]], "rare": []}

    fake = Scripted(monkeypatch, reply)
    col = _collapse(tmp_path, "test_af_union", {"a": _many(120)})
    assert len(fake.calls) == 2 and len(col.statements["a"]) == 8
    assert col.diag["n_digest_reasked"] == 1 and col.diag["n_digest_reask_better"] == 1
    assert col.diag["n_digest_collapsed"] == 0


def test_small_or_full_digests_are_not_reasked(tmp_path, monkeypatch):
    def few(system, user):
        lines = [x[2:] for x in user.splitlines() if x.startswith("- ")]
        return {"items": [_entry(x, x.split()[0]) for x in lines[:2]], "rare": []}

    fake = Scripted(monkeypatch, few)
    _collapse(tmp_path, "test_af_union", {"a": _many(40)})  # under COLLAPSE_READOUTS
    assert len(fake.calls) == 1
    fake = Scripted(monkeypatch, lambda s, u: {"items": [], "rare": []})
    col = _collapse(tmp_path / "z", "test_af_union", {"a": _many(120)})
    assert len(fake.calls) == 2 and col.empty == {"a"}  # still nothing: stays a judged empty
    assert col.diag["n_digest_collapsed"] == 1


def test_f3_families_take_the_jailbreak_route():
    for fam in (
        "introspection",
        "moral_rationale",
        "user_modeling",
        "model_specific_directed_modulation",
        "jailbreak_recognition",
    ):
        s = digest.settings(_args(Path("/tmp")), fam)
        assert s.server_fallback == "default" and s.refusal_model == "claude-sonnet-5-5", fam


# ---------------------------------------------------------------- F3: reporting


def _res(family: str, rows: list[dict], **extras) -> FamilyResult:
    decided = [r for r in rows if r.get("pass") is not None]
    return FamilyResult(
        family=family,
        metric="pass_rate",
        value=sum(r["pass"] for r in decided) / len(decided) if decided else None,
        ci95=None,
        n_items=len(rows),
        higher_is_better=True,
        chance=None,
        chance_label=None,
        complete=True,
        pinned_instrument=True,
        config={"judge_model": "claude-opus-5-5", "aggregate": "summary"},
        counts={},
        extras={"n_items_undecided": len(rows) - len(decided), **extras},
        rows=rows,
    )


def test_over_20pct_undecided_is_not_measurable_and_leaves_the_macro():
    """Leniency guard (F3): making refusals undecided must not let a mass refusal lift the
    headline: above 20% undecided the row is shown, never averaged."""
    rows = [{"id": f"i{k}", "pass": True} for k in range(7)] + [
        {"id": f"u{k}", "pass": None} for k in range(3)
    ]
    r = _res("basic_readout", rows)
    assert not_measurable(r)
    m = macro([r], superseded={}, held_out={}, removed={})
    assert m["value"] is None and m["excluded"][0]["reason"] == "not measurable"
    table = markdown_table([r], m, removed={})
    assert "10 (3 undecided; not measurable)" in table and "30% undecided" in table
    ok = _res("basic_readout", rows[:9])  # 2 of 9 = 22% -> still out; 1 of 8 -> in
    assert not_measurable(ok)
    fine = _res("basic_readout", rows[:8])
    assert not not_measurable(fine) and macro([fine], {}, {}, {})["value"] == 1.0


def test_floor_and_twin_on_shared_decided_ids(monkeypatch):
    lens = _res("association", [{"id": "a", "pass": True}, {"id": "b", "pass": True}])
    entry = {"decided": {"a": False, "c": True}}
    assert shared_floor_text(lens, entry, "0.500") == "0.500 [0.000 vs row 1.000 on 1 shared]"
    assert shared_floor_text(lens, {}, "0.500") == "0.500"
    assert on_shared_ids({"a": True}, {"b": True}) is None
    # plan 0058 removed the only registered pair (medical_diagnosis{,_alt}); the mechanism stays
    assert results_mod.PAIRED_FAMILIES == {}
    monkeypatch.setitem(results_mod.PAIRED_FAMILIES, "fam_alt", "fam")
    main = _res("fam", [{"id": "x", "pass": True}, {"id": "y", "pass": None}])
    alt = _res("fam_alt", [{"id": "x", "pass": False}, {"id": "y", "pass": True}])
    table = markdown_table([main, alt], None, removed={})
    assert "fam vs fam_alt on the 1 ids decided in both" in table


def test_decided_outcomes_shapes():
    assert decided_outcomes([{"id": "a", "pass": None}, {"id": "b", "pass": False}]) == {"b": False}
    rows = [{"id": "a", "correct": True, "pick": "gold"}, {"id": "b", "pick": "unsummarized"}]
    assert decided_outcomes([{**rows[1], "correct": False}, rows[0]]) == {"a": True}
    assert decided_outcomes([{"id": "a", "pass": True}, {"id": "a", "pass": False}]) == {}


def test_layer_union_check_lists_single_layer_passes_the_all_layer_row_misses():
    all_r = _res("x", [{"id": "a", "pass": True}, {"id": "b", "pass": False}, {"id": "c"}])
    all_r.rows[2]["pass"] = None
    single = {
        "L44": _res("x", [{"id": "a", "pass": False}, {"id": "b", "pass": True}]),
        "L52": _res("x", [{"id": "c", "pass": True}, {"id": "b", "pass": True}]),
    }
    chk = layer_union_check(all_r, single)
    assert chk == {
        "n_union": 2,
        "n_all": 1,
        "n_missing": 2,
        "missing": {"b": ["L44", "L52"], "c": ["L52"]},
        "undecided": ["c"],
    }


def test_prompt_only_digest_refusals_count_toward_the_share():
    from wsbench.baselines import prompt_only as po

    frozen = {
        "association": {
            "rate": 0.5,
            "ci95": None,
            "n_items": 10,
            "n_items_decided": 8,
            "digest_unserved": ["q2", "q3"],
        }
    }
    cfg = {"families": {"association": {"n_ids": 10, "refused": ["q1", "q2"]}}}
    po._po_opus_entries(frozen, cfg)
    e = frozen["association"]
    # q2 is refused at both steps and counts once: 3 of 10 > 20%
    assert e["n_refused"] == 3 and e["n_refused_ask"] == 2 and e["n_refused_digest"] == 1
    assert e["refusal_share"] == pytest.approx(0.3) and e["not_measurable"] is True


# ---------------------------------------------------------------- F11: first-number consensus


def test_lead_number():
    assert digest.lead_number("**18** - 2 = 16") == ("18", 18.0)
    assert digest.lead_number("\\[ 120 \\] so") == ("120", 120.0)
    assert digest.lead_number("- 93 $$ **Explanation") == ("93", 93.0)
    assert digest.lead_number("-7 is the result") == ("-7", -7.0)
    assert digest.lead_number("2.333... is about") == ("2.333", 2.333)
    # list markers, ordinals, units, times and fractions are not a leading value
    for s in ("2. Problem Statement", "1) first", "3: note", "1st step", "3x + 2", "3:00 pm"):
        assert digest.lead_number(s) is None, s
    assert digest.lead_number("7/3 = 2.33") is None
    assert digest.lead_number("The answer is 18") is None  # does not BEGIN with a number


def test_consensus_needs_three_of_four_at_one_activation():
    cells = [
        _prose("a", 52, -8, "18 - 2 = 16", "18 is it", "**18**", "7 apples"),  # 3 of 4
        _prose("a", 52, -7, "21 maybe", "21?", "3", "4"),  # leniency guard: 2 of 4
        _prose("a", 56, -8, "21 then", "x 21", "21", "21"),  # 3 of 4 (one sample not a lead)
        _prose("a", 60, -8, "5", "5"),  # leniency guard: fewer than 3 samples
    ]
    cons = digest.consensus_claims(cells)
    assert [(c.value, c.layer, c.pos, c.k, c.n) for c in cons] == [
        (18.0, 52, -8, 3, 4),
        (21.0, 56, -8, 3, 4),
    ]


def _g(key: str, count: int = 1) -> digest.Grounded:
    ln = digest.Line(f"{key} stated", layer=44, pos=-3)
    return digest.Grounded("s", digest.support_text(count), key, ln, key, "numbers", count=count)


def test_rank_numbers_demotes_operands_and_fills_free_slots_with_consensus():
    ln = digest.Line("18 - 2 = 16", where="[L52 pos -8]", layer=52, pos=-8)
    cons = [
        digest.Consensus(18.0, "18", 52, -8, 4, 4, ln),
        digest.Consensus(87.0, "87", 52, -7, 3, 4, ln),  # an operand: never fills a slot
    ]
    gs = [_g("87"), _g("88"), _g("175", 9), _g("16")]
    out = digest.rank_numbers(gs, cons, operands=[87.0, 88.0], cap=5)
    # round 3 (+cons-r3, ROUND3_TODO: reserve slots for consensus values): marked numbers first
    assert [g.key for g in out] == ["18", "175", "16", "87", "88"]
    assert out[0].consensus.startswith("first number of 4 of 4 samples at [L52 pos -8]")
    assert out[0].support.startswith("4 samples; first number of 4 of 4")
    assert out[3].consensus == ""  # an operand is not marked even with a lead consensus
    # leniency guard: the slot count stays capped, consensus or not
    many = [_g(str(v)) for v in (1, 2, 3, 4, 5, 6)]
    assert len(digest.rank_numbers(many, cons, operands=[], cap=5)) == 5
    # the consensus values (18, and 87: no operand here) are no longer cut by the cap; the last
    # unmarked numbers are
    assert [g.key for g in digest.rank_numbers(many, cons, [], 5)] == ["18", "87", "1", "2", "3"]


def test_keyed_number_with_consensus_is_annotated():
    ln = digest.Line("18 - 2", layer=52, pos=-8)
    cons = [digest.Consensus(18.0, "18", 52, -8, 3, 4, ln)] * 2
    out = digest.rank_numbers([_g("18", 6)], cons, operands=[], cap=5)
    assert out[0].count == 6
    assert out[0].support == (
        "6 samples; first number of 3 of 4 samples at [L52 pos -8] and at 1 more activation"
    )


def test_arithmetic_summary_judge_reads_the_consensus_mark():
    from wsbench.evals.arithmetic_intermediates import prompts as ap

    assert ap.CONSENSUS_RULE in ap.SYSTEM_SUMMARY and ap.CONSENSUS_RULE not in ap.SYSTEM
    assert "only when K is at least 3" in ap.CONSENSUS_RULE


def test_consensus_band_applies_the_same_rule_to_the_null():
    from wsbench.evals.arithmetic_intermediates.judge import consensus_band

    item = {"operands": ["87", "88", "2"]}
    cells = {
        "i": [
            _prose("i", 52, -8, "175 ok", "175", "175!", "x"),  # gold consensus
            _prose("i", 52, -7, "87 + 88", "87", "87 is", "87"),  # an operand: never counts
            _prose("i", 56, -8, "40 hmm", "40", "40", "1"),  # a null-set value
        ]
    }
    band, rows = consensus_band(
        ["i"], cells, {"i": item}, {"i": 175.0}, {"i": "exact"}, {"i": [40.0, 999.0]}
    )
    assert rows["i"]["consensus_values"] == [40.0, 175.0]
    assert rows["i"]["consensus_hit"] and rows["i"]["consensus_cross"] == 0.5
    assert band["rate"] == 1.0 and band["cross"] == 0.5 and band["net"] == 0.5 and band["n"] == 1
    # a single-sample reader has no activation with >= 3 samples: no band
    one = {"i": [_prose("i", 52, -8, "175")]}
    band, rows = consensus_band(
        ["i"], one, {"i": item}, {"i": 175.0}, {"i": "exact"}, {"i": [40.0]}
    )
    assert band["n"] == 0 and band["rate"] is None and rows == {}


def test_arithmetic_digest_gets_operands_and_consensus(tmp_path, monkeypatch):
    """End to end on the numbers digest: an operand keyed by the summarizer is demoted out of
    the five slots and a 4-of-4 lead consensus the summarizer missed fills its place."""

    def reply(system, user):
        assert "Return the 9 numbers" in system  # 5 + NUMBERS_SPARE
        keys = ["87", "88", "2", "300", "301", "302"]
        lines = [x[2:] for x in user.splitlines() if x.startswith("- ")]
        out = [_entry(next(x for x in lines if x.startswith(k)), k) for k in keys]
        return {"items": out, "rare": []}

    Scripted(monkeypatch, reply)
    cells = [
        _prose("i", 52, -8, "175 first", "175 again", "175", "175 4"),
        _prose("i", 52, -7, "87 restated", "88 restated", "2 restated", "300 a"),
        _prose("i", 52, -6, "301 b", "302 c", "q", "r"),  # final r1: one layer (union is per layer)
    ]
    col = _collapse(
        tmp_path,
        "arithmetic_intermediates",
        {"i": cells},
        operands={"i": [87.0, 88.0, 2.0]},
        consensus=True,
    )
    keys = [x["key"] for x in col.statements["i"]]
    # cap 5; two operands demoted out; round 3 (+cons-r3): the consensus value ranks first
    assert keys == ["175", "300", "301", "302", "87"]
    assert col.statements["i"][0]["consensus"].startswith("first number of 4 of 4")
    assert digest.number_keys(_args(tmp_path), "arithmetic_intermediates", col, "i") == keys

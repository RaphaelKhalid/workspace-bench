import ast
import dataclasses
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import native_args, tag_of, write_jsonl, write_sidecar
from summary_fakes import FakeLLM, summary_args

from wsbench import digest, mc, readplan, reads, registry
from wsbench.evals.conjunctive_association import judge, prompts
from wsbench.evals.conjunctive_association.judge import (
    build_bags,
    build_blob,
    build_options,
    inverted_position,
    norm_token,
)
from wsbench.mc import CANNOT
from wsbench.mcjudge import load_bank
from wsbench.readouts import load_readouts

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / "tests/golden/conjunctive_association_options.json").read_text())
EXAMPLE = ROOT / "examples/readouts/conjunctive_association.jsonl"
V1_BANK = ROOT / "evals/conjunctive_association/items.json"
QA, QB = "q01_a", "q01_b"


@pytest.fixture(autouse=True)
def _single_draw(monkeypatch):
    """comp-v3 (audit F9) judges every item in 3 draws and takes the majority. The tests of this
    module pin the single-draw pipeline (scripted single answers, call counts); the draws and
    the majority rule are tested in ``test_audit_fixes_families.py``."""
    monkeypatch.setattr(judge, "N_DRAWS", 1)


@pytest.fixture
def v1_bank(monkeypatch):
    """Pin the v1 bank (scripted picks are v1 positions; plan 0049 R6)."""
    monkeypatch.setenv("WSB_BANK_FILE_CONJUNCTIVE_ASSOCIATION", str(V1_BANK))


def test_bank_loads():
    bank = load_bank("conjunctive_association")
    assert len(bank) == 100
    for it in bank:
        assert {"id", "gold_label", "mc_options", "contrast_label", "stimulus"} <= set(it)


def test_options_match_source_golden():
    bank = json.loads(V1_BANK.read_text())  # plan 0049: the v1 file, read explicitly
    for it in bank:
        shown, gold_pos, contrast_pos = build_options(it)
        assert {"shown": shown, "gold_pos": gold_pos} == GOLDEN[it["id"]], it["id"]
        assert len(shown) == 11 and shown[-1] == CANNOT
        assert shown[contrast_pos - 1] == it["contrast_label"]
    with pytest.raises(ValueError):
        build_options({"id": "x", "gold_label": "g", "mc_options": ["a", "b"]})


def test_rendered_prompt_matches_golden():
    bank = load_bank("conjunctive_association")
    shown, _g, _c = build_options(bank[0])
    user = prompts.render_user("TOY READOUT", prompts.render_question(shown))
    assert user == (ROOT / "tests/golden/conjunctive_association_prompt_v4.txt").read_text()
    # the frozen v3 lists still render their own golden
    v3 = json.loads((ROOT / "evals/conjunctive_association/items_v3.json").read_text())
    shown3, _g, _c = build_options(v3[0])
    user3 = prompts.render_user("TOY READOUT", prompts.render_question(shown3))
    assert user3 == (ROOT / "tests/golden/conjunctive_association_prompt_v3.txt").read_text()
    # F9: the comp-v2 prompts, judged in 3 draws (comp-v3); round 4: on bank v3's lists (comp-v4),
    # then on bank v4's widened lists (comp-v5)
    assert prompts.PROMPT_VERSION == "comp-v5"


def test_blob_rule(tmp_path):
    assert norm_token("Ġsnake_case▁x") == "snake case x"
    assert norm_token("line one\nline two") == "line one\nline two"  # prose newlines kept
    cells, _rep = load_readouts(EXAMPLE)
    bags = build_bags(cells)
    assert set(bags) == {(QA, 20), (QA, 36), (QB, 20), (QB, 36)}
    assert bags[(QA, 20)] == (
        "grief over a child's accidental death | Nora is grieving; her young child died "
        "suddenly in a bicycle accident. | grief over a child's accidental death"
    )
    # file order, not pos order; prose loses underscores; non-printables stripped after the cap
    cells, _ = load_readouts(
        write_jsonl(
            tmp_path / "order.jsonl",
            [
                {"id": QA, "layer": 20, "pos": 5, "samples": ["b_b", ""]},
                {"id": QA, "layer": 20, "pos": 1, "samples": ["a\x00a"]},
            ],
        )
    )
    bags = build_bags(cells)
    assert bags[(QA, 20)] == "b b |  | a\x00a"
    blob = build_blob({20: bags[(QA, 20)], 36: "z"}, [20, 36], char_cap=1000)
    assert blob == "\n[L20] b b |  | aa\n[L36] z"
    assert build_blob({20: "abcdef"}, [20], char_cap=8) == "\n[L20] a"


def _scripted(tmp_path):
    rows = []
    for iid in (QA, QB, "q02_a"):
        for layer in (20, 36):
            if iid == "q02_a" and layer == 36:
                continue  # missing layer -> excluded
            for pos in (1, 2):
                # norm_token turns "_" into " ", so the tag carries the id with "-"
                tag = f"R:{iid.replace('_', '-')}:L{layer}:p{pos}"
                rows.append({"id": iid, "layer": layer, "pos": pos, "samples": [tag]})
    rows.append({"id": "q02_b", "layer": 20, "pos": 1, "samples": [""]})
    rows.append({"id": "q02_b", "layer": 36, "pos": 1, "samples": [""]})  # all-empty item
    return write_jsonl(tmp_path / "r.jsonl", rows)


def _responder(system, user):
    if user.startswith("Return"):
        return {"a": 1}
    assert system == prompts.SYSTEM
    iid = tag_of(user).split(":")[0].replace("-", "_")
    if iid == QA:
        return {"choice": GOLDEN[QA]["gold_pos"], "quote": "R:q01-a:L36:p2"}
    return None


def test_run_verdicts_and_numbers(tmp_path, fake_llm, mk_args, v1_bank):
    fake = fake_llm(_responder)
    args = mk_args(_scripted(tmp_path), items=[QA, QB, "q02_a", "q02_b", "q03_a"])
    res = judge.run(args)
    # q02_a excluded (missing L36); q03_a has no readouts (fail); q02_b all-empty (fail); final r1
    # (campaign-lead decision on #200): QB's failed call is undecided, out of the denominator
    assert res.n_items == 4 and res.value == pytest.approx(1 / 3)
    assert res.chance == pytest.approx(1 / 11) and res.extras["n_items_undecided"] == 1
    c = res.counts
    assert c["n_expected_cells"] == 6 and c["n_empty_cells"] == 2 and c["n_unjudged_cells"] == 2
    rows = {r["id"]: r for r in res.rows}
    assert rows[QA]["pick"] == "gold" and rows[QA]["correct"] and rows[QA]["quote_ok"] is True
    assert set(rows[QA]) == {
        "id",
        "choice",
        "gold_pos",
        "contrast_pos",
        "pick",
        "correct",
        "quote",
        "quote_ok",
        "draw_picks",  # comp-v3 (F9): the per-draw picks behind the majority pick
        "n_draws",
    }
    assert rows[QB]["pick"] == "api_fail" and rows[QB]["correct"] is False
    assert res.extras["breakdown"] == {
        "gold": 1, "contrast": 0, "distractor": 0, "cannot_tell": 0, "invalid": 0, "api_fail": 1,
        "gold_unverified": 0, "gold_partial": 0, "inverted": 0, "split": 0,
    }  # fmt: skip
    assert res.extras["n_items_excluded"] == 1 and res.extras["char_cap"] == 200000
    assert res.config["char_cap"] == 200000
    assert len([u for _s, u in fake.calls if not u.startswith("Return")]) == 3
    third = [u for _s, u in fake.calls if not u.startswith("Return")][2]
    assert third.startswith("READOUT (one span quoted from the readouts):\nR:q01-a:L36:p2")
    prompt = next(u for _s, u in fake.calls if "R:q01-a" in u)
    assert prompt.startswith(
        "READOUTS:\n\n[L20] R:q01-a:L20:p1 | R:q01-a:L20:p2\n"
        "[L36] R:q01-a:L36:p1 | R:q01-a:L36:p2\n\nWhich"
    )

    # resume: only the failed item is re-judged; the api_fail row disappears
    def contrast(s, u):
        if u.startswith("Return"):
            return {"a": 1}
        _shown, _g, cpos = build_options(
            next(it for it in load_bank("conjunctive_association") if it["id"] == QB)
        )
        return {"choice": cpos, "quote": "nope"}

    fake2 = fake_llm(contrast)
    res2 = judge.run(args)
    assert len([u for _s, u in fake2.calls if not u.startswith("Return")]) == 1
    rows = {r["id"]: r for r in res2.rows}
    assert rows[QB]["pick"] == "contrast" and rows[QB]["quote_ok"] is False
    assert res2.counts["n_unjudged_cells"] == 0 and res2.extras["breakdown"]["contrast"] == 1
    fake3 = fake_llm(lambda s, u: pytest.fail("no call expected"))
    judge.run(args)
    assert fake3.calls == []


def test_char_cap_option_and_pick_labels(tmp_path, fake_llm, mk_args, v1_bank):
    picks = iter([{"choice": 11, "quote": ""}, {"choice": 0, "quote": ""}])

    def responder(s, u):
        if u.startswith("Return"):
            return {"a": 1}
        assert len(u.split("\n\nWhich")[0]) <= len("READOUTS:\n") + 12
        return next(picks)

    fake_llm(responder)
    res = judge.run(mk_args(_scripted(tmp_path), items=[QA, QB], extra={"char_cap": "12"}))
    assert res.extras["char_cap"] == 12 and res.config["char_cap"] == 12
    assert sorted(r["pick"] for r in res.rows) == ["cannot_tell", "invalid"]
    assert res.value == 0.0


def test_dry_run_prints_and_makes_no_calls(tmp_path, mk_args, capsys, monkeypatch):
    monkeypatch.setattr("wsbench.llm._make_client", lambda r, k: pytest.fail("no client"))
    res = judge.run(mk_args(EXAMPLE, dry_run=True))
    out = capsys.readouterr().out
    assert prompts.SYSTEM in out and "Which of the following does the readout state?" in out
    assert res.value is None and res.rows == [] and res.n_items == 100


def test_char_cap_validation(tmp_path):
    import pytest

    from wsbench import registry
    from wsbench.evals.conjunctive_association import judge as cj
    from wsbench.judge_config import JudgeConfig, resolve
    from wsbench.registry import JudgeArgs

    def args(v: str) -> JudgeArgs:
        return native_args(
            readouts=registry.REPO_ROOT / "examples/readouts/conjunctive_association.jsonl",
            out=tmp_path,
            judge=resolve(JudgeConfig()),
            layers=None,
            items=None,
            limit=0,
            allow_missing=False,
            concurrency=1,
            rpm=1e9,
            dry_run=True,
            extra={"char_cap": v},
        )

    for bad in ("abc", "0", "-5"):
        with pytest.raises(SystemExit):
            cj.run(args(bad))


# ---------------------------------------------------------------- plan 0049 (comp-v2, bank v2)

V2_BANK = ROOT / "evals/conjunctive_association/items_v2.json"
V1_SHA = "5ef25c10238b93ea1c3b7808c4c9758ea364db22f4de0bbf74ae3453a2d74e36"
GOLDEN_V2 = json.loads((ROOT / "tests/golden/conjunctive_association_options_v2.json").read_text())
V3_BANK = ROOT / "evals/conjunctive_association/items_v3.json"
GOLDEN_V3 = json.loads((ROOT / "tests/golden/conjunctive_association_options_v3.json").read_text())
REJUDGE = "READOUT ("
# the 19 read sites of every item (docs/read_sites.md): suffix + chat tail
SITES = [
    "Sum", "mar", "ize", "Ġthe", "Ġpreceding", "Ġstory", "Ġin", "Ġone", "Ġsentence", ".",
    "<|im_end|>", "Ċ", "<|im_start|>", "assistant", "Ċ", "<think>", "ĊĊ", "</think>", "ĊĊ",
]  # fmt: skip


def _item(iid: str) -> dict:
    return next(it for it in load_bank("conjunctive_association") if it["id"] == iid)


def _opts(iid: str) -> tuple[list[str], int, int | None]:
    return build_options(_item(iid))


def _cells_file(tmp_path, rows, *, sampling=None, name="r.jsonl"):
    """A readouts file; with ``sampling`` also a sidecar, and each (item, layer) is padded with
    neutral cells to a full 19-site run ending at its readout (a sidecar file is full-checked)."""
    if sampling is not None:
        have = {(r["id"], r["layer"], r["pos"]) for r in rows}
        pad = [
            {"id": r["id"], "layer": r["layer"], "pos": p, "samples": ["a quiet hallway"]}
            for r in rows
            for p in range(r["pos"] - 18, r["pos"])
            if (r["id"], r["layer"], p) not in have
        ]
        rows = [*rows, *pad]
    path = write_jsonl(tmp_path / name, rows)
    if sampling is not None:
        write_sidecar(path, reads="full", sampling=sampling, reader="test")
    return path


def _one(iid, sample, layer=44, pos=50):
    return {"id": iid, "layer": layer, "pos": pos, "samples": [sample]}


def _script(main, rejudge=None):
    """Responder: ``main(user)`` answers the readout_mc call, ``rejudge(user)`` the quote_mc."""

    def responder(system, user):
        if user.startswith("Return"):
            return {"a": 1}
        if user.startswith(REJUDGE):
            assert rejudge is not None, "no quote re-judge expected"
            return rejudge(user)
        return main(user)

    return responder


def _native(mk_args, path, iid, **kw):
    return mk_args(path, items=[iid], allow_missing=True, **kw)


Q08C = "q08_c"  # gold: ... in revenge for a stolen algorithm, while believing he is unaware
Q07A = "q07_a"  # gold: relief at her own reassuring medical news, ... hidden from her spouse
Q04G = "q04_g"  # gold: the intent to take credit for her longtime mentor's work


# ---- C1: all layers


def test_plan_is_grid_19_positions():
    rows = readplan.plan("conjunctive_association")
    assert len(rows) == 100 and all(r.layers == readplan.GRID for r in rows)
    story = ["The", "Ġstory", "."]
    assert readplan.resolve(rows[0].positions, story + SITES) == list(range(3, 3 + 19))
    every = readplan.plan("conjunctive_association", layers="all")
    assert all(r.layers == list(range(64)) for r in every)
    assert reads.plan_sha_rows(s.row() for s in every) == reads.plan_sha("conjunctive_association")


def test_layer_subset_digest_sees_only_those_layers(tmp_path, monkeypatch):
    rows = [_one(QA, f"grief at L{L} p{p}", L, p) for L in readplan.GRID for p in (1, 2)]
    path = _cells_file(tmp_path, rows)
    seen: list[str] = []

    def dig(user):
        seen.append(user)
        return None

    FakeLLM.install(monkeypatch, lambda s, u, sc: {"choice": 21, "quote": ""}, digest=dig)
    judge.run(summary_args(path, tmp_path / "a", "pv", items=[QA], layers=[44]))
    heads = set(re.findall(r"\[L(\d+) pos \d+\]", seen[-1]))
    assert heads == {"44"}
    seen.clear()
    judge.run(summary_args(path, tmp_path / "b", "pv", items=[QA]))
    # audit F1: one digest per read layer; together they carry every cell
    every = "\n".join(seen)
    assert set(re.findall(r"\[L(\d+) pos \d+\]", every)) == {str(L) for L in readplan.GRID}


def test_summary_bundle_has_every_cell(tmp_path, monkeypatch):
    rows = [_one(QA, f"s{L}-{p}", L, p) for L in (20, 36) for p in (5, 6, 7)]
    seen: list[str] = []
    FakeLLM.install(
        monkeypatch,
        lambda s, u, sc: {"choice": 21, "quote": ""},
        digest=lambda u: seen.append(u) or None,
    )
    judge.run(summary_args(_cells_file(tmp_path, rows), tmp_path / "o", "pv", items=[QA]))
    for r in rows:  # audit F1: one digest per read layer; together they carry every cell
        assert f"[L{r['layer']} pos {r['pos']}]" in "\n".join(seen)


def test_all_layer_producer_file_is_judged(tmp_path, monkeypatch):
    """Late critique fix (1): plan_sha does not hash layers, so a sidecar file read at all 64
    layers with the judge's plan_sha is judged at every layer (no exit, no partial item)."""
    rows = [_one(QA, f"x{L}-{p}", L, 100 + p) for L in range(64) for p in range(19)]
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    write_sidecar(
        path,
        reads="full",
        sampling="prose1",
        reader="test",
        layers=list(range(64)),
        plan_sha=reads.plan_sha("conjunctive_association"),
    )
    cannot = len(_opts(QA)[0])  # the escape is last (bank v3: 25 shown for q01)
    FakeLLM.install(monkeypatch, lambda s, u, sc: {"choice": cannot, "quote": ""})
    r = judge.run(summary_args(path, tmp_path / "o", "pv", items=[QA]))
    assert r.config["reads_checked"] == "sidecar" and r.config["layers_judged"] == list(range(64))
    assert r.n_items == 1 and r.rows[0]["pick"] == "cannot_tell"


def test_sidecar_missing_layer_defers_to_infra(tmp_path, fake_llm, mk_args):
    rows = [
        _one(iid, "x", L, p)
        for iid in (QA, QB)
        for L in readplan.GRID
        if not (iid == QB and L == 36)
        for p in range(31, 50)
    ]
    path = _cells_file(tmp_path, rows, sampling="prose1")
    fake_llm(_script(lambda u: {"choice": 21, "quote": ""}))
    with pytest.raises(SystemExit):
        judge.run(mk_args(path, items=[QA, QB]))
    args = mk_args(path, items=[QA, QB], allow_missing=True)
    res = judge.run(args)
    assert res.extras["n_items_excluded"] == 0 and res.n_items == 2
    assert reads.report_of(args).partial_ids == [QB] and reads.incomplete(args)


# ---- C2: partial composition (rubric, enforced quote, one statement, quote-only re-judge)


def _gold_with(iid, quote):
    return lambda u: {"choice": _opts(iid)[1], "quote": quote}


def test_partial_quote_fails_composition_check(tmp_path, fake_llm, mk_args):
    path = _cells_file(tmp_path, [_one(Q08C, "Sam quietly stole Leo's algorithm.")])
    shown = _opts(Q08C)[0]
    fake = fake_llm(
        _script(
            _gold_with(Q08C, "Sam quietly stole Leo's algorithm"),
            lambda u: {"choice": len(shown), "quote": ""},
        )
    )
    res = judge.run(_native(mk_args, path, Q08C))
    row = res.rows[0]
    assert row["pick"] == "gold_partial" and row["correct"] is False
    assert res.extras["n_gold_raw"] == 1 and res.extras["quote_checks"] == {Q08C: len(shown)}
    rejudge = [u for _s, u in fake.calls if u.startswith(REJUDGE)]
    assert rejudge == [
        "READOUT (one span quoted from the readouts):\nSam quietly stole Leo's algorithm\n\n"
        + prompts.render_question(shown)
    ]


def test_unverified_quote_fails(tmp_path, fake_llm, mk_args):
    path = _cells_file(tmp_path, [_one(Q08C, "a quiet office")])
    fake = fake_llm(_script(_gold_with(Q08C, "revenge for a stolen algorithm")))
    res = judge.run(_native(mk_args, path, Q08C))
    assert res.rows[0]["pick"] == "gold_unverified" and res.rows[0]["quote_ok"] is False
    assert res.extras["n_unverified_bullet"] == 0 and res.value == 0.0
    assert not any(u.startswith(REJUDGE) for _s, u in fake.calls)


PACKED = "- relief at good news\n- hides it from her husband\n- a kitchen\n- the night"


def test_quote_across_two_generations_fails_under_bullet4(tmp_path, fake_llm, mk_args):
    path = _cells_file(tmp_path, [_one(Q07A, PACKED)], sampling="bullet4")
    fake_llm(_script(_gold_with(Q07A, "relief at good news hides it from her husband")))
    args = _native(mk_args, path, Q07A)
    res = judge.run(args)
    assert reads.report_of(args).sampling == "bullet4"
    assert res.rows[0]["pick"] == "gold_unverified"
    assert res.extras["n_unverified_bullet"] == 0  # fails quote_ok itself (two samples)


@pytest.mark.parametrize(
    "quote",
    [
        "relief at good news ⁞ hides it from her husband",
        "relief at good news hides it from her husband",
    ],
)
@pytest.mark.parametrize("mode", ["native", "summary"])
def test_prose1_relation_across_two_bullets_fails(quote, mode, tmp_path, fake_llm, monkeypatch):
    cells = [_one(Q07A, PACKED)]
    path = _cells_file(tmp_path, cells, sampling="prose1")
    lines = digest.native_lines(reads.load(_sargs(path, tmp_path), FAMILY_NAME)[0])
    assert digest.quote_ok(quote, lines)
    assert not digest.quote_ok(quote, digest.statement_lines(lines, _cells_of(path, tmp_path)))
    res = _run_mode(mode, path, tmp_path, fake_llm, monkeypatch, _gold_with(Q07A, quote))
    row = res.rows[0]
    assert row["pick"] == "gold_unverified" and res.extras["n_unverified_bullet"] == 1
    assert res.extras["quote_checks"] == {}  # no quote_mc call


@pytest.mark.parametrize("verdict,want", [("gold", "gold"), ("cannot", "gold_partial")])
@pytest.mark.parametrize("mode", ["native", "summary"])
def test_prose1_relation_in_one_bullet_proceeds(
    verdict, want, mode, tmp_path, fake_llm, monkeypatch
):
    cell = "- relief at good news, hidden from her husband\n- a quiet kitchen"
    path = _cells_file(tmp_path, [_one(Q07A, cell)], sampling="prose1")
    shown, gold, _c = _opts(Q07A)
    rejudge = {"gold": gold, "cannot": len(shown)}[verdict]
    res = _run_mode(
        mode,
        path,
        tmp_path,
        fake_llm,
        monkeypatch,
        _gold_with(Q07A, "relief at good news, hidden from her husband"),
        rejudge=lambda u: {"choice": rejudge, "quote": ""},
    )
    assert res.rows[0]["pick"] == want and res.extras["n_unverified_bullet"] == 0
    assert res.extras["quote_checks"] == {Q07A: rejudge}


def test_judge_sees_bullet_mark(tmp_path, monkeypatch):
    path = _cells_file(tmp_path, [_one(Q07A, PACKED)], sampling="prose1")
    fake = FakeLLM.install(
        monkeypatch, lambda s, u, sc: {"choice": 21, "quote": ""}, digest=_all_lines
    )
    judge.run(summary_args(path, tmp_path / "o", "pv", items=[Q07A], allow_missing=True))
    users = [u for n, _s, u in fake.calls if n == "readout_mc"]
    assert any("relief at good news ⁞ hides it from her husband" in u for u in users)
    assert "(shown separated by ⁞)" in prompts.SYSTEM
    assert "(shown separated by ⁞)" in prompts.SYSTEM_SUMMARY


def test_unbulleted_prose_is_one_statement(tmp_path, fake_llm, mk_args):
    para = "She is relieved by the good news. She hides it from her husband."
    path = _cells_file(tmp_path, [_one(Q07A, para)], sampling="prose1")
    _shown, gold, _c = _opts(Q07A)
    fake_llm(
        _script(
            _gold_with(Q07A, "relieved by the good news. She hides it from her husband"),
            lambda u: {"choice": gold, "quote": ""},
        )
    )
    res = judge.run(_native(mk_args, path, Q07A))
    assert res.rows[0]["pick"] == "gold" and res.extras["n_unverified_bullet"] == 0


def test_full_quote_passes(tmp_path, fake_llm, mk_args):
    text = "relief that her biopsy came back benign, and she keeps the scare from her husband"
    path = _cells_file(tmp_path, [_one(Q07A, text)])
    _shown, gold, _c = _opts(Q07A)
    fake_llm(_script(_gold_with(Q07A, text), lambda u: {"choice": gold, "quote": ""}))
    res = judge.run(_native(mk_args, path, Q07A))
    assert res.rows[0]["pick"] == "gold" and res.rows[0]["correct"] and res.value == 1.0
    assert res.extras["breakdown"]["gold"] == 1 and res.extras["n_gold_raw"] == 1


def test_quote_check_api_fail_is_undecided(tmp_path, fake_llm, mk_args):
    text = "relief that her biopsy came back benign, and she keeps the scare from her husband"
    path = _cells_file(tmp_path, [_one(Q07A, text)])
    fake_llm(_script(_gold_with(Q07A, text), lambda u: None))
    res = judge.run(_native(mk_args, path, Q07A))
    row = res.rows[0]
    assert row["pick"] == "api_fail" and row["failed_stage"] == "quote_check"
    assert row["correct"] is False and res.counts["n_unjudged_cells"] == 1


def test_system_requires_every_part():
    for system in (prompts.SYSTEM, prompts.SYSTEM_SUMMARY):
        assert "EVERY part in which that option differs" in system
        assert "each bullet is its own statement" in system
        assert "Never combine parts taken from different statements" in system
        assert system.startswith(f"You judge {mc.READOUT_PHRASE}")
        assert "interpretability lens" not in system and "SHORT exact" not in system
    assert "labeled by layer" in prompts.SYSTEM
    assert "a digest of the readouts across every read layer" in prompts.SYSTEM_SUMMARY


def test_family_uses_shared_quote_ok():
    src = (ROOT / "src/wsbench/evals/conjunctive_association/judge.py").read_text()
    tree = ast.parse(src)
    called = {
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "digest"
    }
    assert {"quote_ok", "statement_lines", "native_lines"} <= called
    assert "norm(quote) in" not in src and 'split("\\n- ")' not in src
    assert not any(isinstance(n, ast.FunctionDef) and n.name == "norm" for n in ast.walk(tree))


FAMILY_NAME = "conjunctive_association"


def _sargs(path, tmp_path, **kw):
    return summary_args(path, tmp_path / "load", "pv", allow_missing=True, **kw)


def _cells_of(path, tmp_path):
    return reads.load(_sargs(path, tmp_path), FAMILY_NAME)[0]


def _nargs(path, tmp_path, items, **kw):
    from wsbench.judge_config import JudgeConfig, resolve

    base = {
        "readouts": path,
        "out": tmp_path / "native",
        "judge": resolve(JudgeConfig(), env={}),
        "layers": None,
        "items": items,
        "limit": 0,
        "allow_missing": True,
        "concurrency": 4,
        "rpm": 1e9,
        "dry_run": False,
    }
    base.update(kw)
    return native_args(**base)


def _all_lines(user):
    """A fake digest citing every distinct bundle sample (the padded cells repeat one text)."""
    seen = dict.fromkeys(ln[2:] for ln in user.splitlines() if ln.startswith("- "))
    return {
        "items": [{"statement": f"S{i}", "where": "", "evidence": t} for i, t in enumerate(seen)]
    }


def _run_mode(mode, path, tmp_path, fake_llm, monkeypatch, main, rejudge=None):
    iid = json.loads(path.read_text().splitlines()[0])["id"]
    if mode == "native":
        fake_llm(_script(main, rejudge))
        return judge.run(_nargs(path, tmp_path, [iid]))

    def answer(system, user, schema):
        if schema.get("name") == "quote_mc":
            assert rejudge is not None, "no quote re-judge expected"
            return rejudge(user)
        return main(user)

    FakeLLM.install(monkeypatch, answer, digest=_all_lines)
    return judge.run(summary_args(path, tmp_path / "summ", "pv", items=[iid], allow_missing=True))


# ---- C3: inverted credit (role-swapped twins as distractors, bank v2)


def test_v2_bank_twins():
    assert hashlib.sha256(V1_BANK.read_bytes()).hexdigest() == V1_SHA  # v1 untouched
    v1 = {it["id"]: it for it in json.loads(V1_BANK.read_text())}
    v2 = json.loads(V2_BANK.read_text())
    assert len(v2) == 100 and [it["id"] for it in v2] == list(v1)
    by_cluster: dict[str, list[dict]] = {}
    for it in v2:
        by_cluster.setdefault(it["cluster"], []).append(it)
        assert it["bank_version"] == 2
        tw = it["twin_of"]
        assert all(tw[tw[o]] == o for o in tw)  # involutive
        assert it["inverted_label"] == tw.get(it["gold_label"])
        assert set(v1[it["id"]]["mc_options"]) <= set(it["mc_options"])
        assert len(set(it["mc_options"])) == len(it["mc_options"])
        for k in ("stimulus", "gold_label", "contrast_label"):
            assert it[k] == v1[it["id"]][k]
        assert it["provenance"]["edits"][-1].startswith("v2 2026-10-30: role-swapped twins")
    n_twins = {c: len(its[0]["twin_of"]) // 2 for c, its in by_cluster.items()}
    assert n_twins["q06"] == 0 and n_twins["q03"] == 8 and sum(n_twins.values()) == 88
    for its in by_cluster.values():
        assert all(it["mc_options"] == its[0]["mc_options"] for it in its)
    n_shown = sorted({len(build_options(it)[0]) for it in v2})
    assert n_shown == [11, 19, 21]


def test_v2_bank_is_generated():
    script = ROOT / "scripts/conjunctive/make_v2_bank.py"
    r = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_bank_path_is_v4():
    # round 4 (MC leakage standard; Fable on #202: widen the lists): the registered bank is v4;
    # v3 and v2 stay frozen beside it
    assert registry.bank_path("conjunctive_association").name == "items_v4.json"


def test_options_match_v2_golden():
    for it in json.loads(V2_BANK.read_text()):
        shown, gold_pos, _c = build_options(it)
        assert {"shown": shown, "gold_pos": gold_pos} == GOLDEN_V2[it["id"]], it["id"]


def test_options_match_v3_golden():
    for it in json.loads(V3_BANK.read_text()):
        shown, gold_pos, _c = build_options(it)
        assert {"shown": shown, "gold_pos": gold_pos} == GOLDEN_V3[it["id"]], it["id"]


def test_cannot_tell_last_in_v2():
    for it in load_bank("conjunctive_association"):
        shown = build_options(it)[0]
        assert shown[-1] == mc.CANNOT and shown.count(mc.CANNOT) == 1


def test_inverted_pick_is_fail(tmp_path, fake_llm, mk_args):
    shown = _opts(Q04G)[0]
    inv = inverted_position(_item(Q04G), shown)
    assert (
        inv is not None
        and shown[inv - 1] == "her longtime mentor's intent to take credit for her work"
    )
    text = "her mentor intends to take credit for her work"
    path = _cells_file(tmp_path, [_one(Q04G, text)])
    fake_llm(
        _script(lambda u: {"choice": inv, "quote": text}, lambda u: {"choice": inv, "quote": ""})
    )
    res = judge.run(_native(mk_args, path, Q04G))
    assert res.rows[0]["pick"] == "inverted" and res.rows[0]["correct"] is False
    assert res.extras["breakdown"]["inverted"] == 1 and res.extras["n_gold_raw"] == 0
    assert res.extras["quote_checks"] == {Q04G: inv}
    assert inverted_position({"id": "x", "gold_label": "g"}, ["g", mc.CANNOT]) is None


def test_q04_g_style_inversion(tmp_path, fake_llm, mk_args):
    """J-lens q04_g (audit): "mentor of fifteen years stole her intellectual work" was credited
    as the gold "the intent to take credit for her longtime mentor's work"; under v2 the twin is
    listed, and a judge that picks it (or a quote that re-judges to it) is ``inverted``."""
    text = "her mentor of fifteen years stole her intellectual work"
    shown, gold, _c = _opts(Q04G)
    inv = inverted_position(_item(Q04G), shown)
    path = _cells_file(tmp_path, [_one(Q04G, text)])
    fake_llm(
        _script(lambda u: {"choice": gold, "quote": text}, lambda u: {"choice": inv, "quote": ""})
    )
    res = judge.run(_native(mk_args, path, Q04G))
    assert res.rows[0]["pick"] == "inverted" and res.value == 0.0


def test_chance_is_mean_of_shown(tmp_path, fake_llm, mk_args, v1_bank):
    path = _cells_file(tmp_path, [_one(QA, "x")])
    fake_llm(_script(lambda u: {"choice": 11, "quote": ""}))
    assert judge.run(_native(mk_args, path, QA)).chance == pytest.approx(1 / 11)


def test_chance_on_v2(tmp_path, fake_llm, mk_args):
    ids = [QA, "q03_a", "q06_a"]
    path = _cells_file(tmp_path, [_one(i, "x") for i in ids])
    fake_llm(_script(lambda u: {"choice": 0, "quote": ""}))
    res = judge.run(mk_args(path, items=ids))
    # bank v4: every list widened to 22 non-twin options + twins (q01 45 / q03 43 / q06 23 shown;
    # v3: 25 / 23 / 11)
    assert res.chance == pytest.approx((1 / 45 + 1 / 43 + 1 / 23) / 3)
    assert "mean 1/n" in res.chance_label


# ---- C4: token lists combine within one list, never across lists


def _tok(iid, layer, pos, toks):
    return {"id": iid, "layer": layer, "pos": pos, "tokens": toks}


def test_native_tokens_no_interp_call(tmp_path, fake_llm, mk_args):
    rows = [
        _tok(QA, 20, 5, ["grief", "child", "accident"]),
        _tok(QA, 20, 6, ["kitchen", "light"]),
        _tok(QA, 36, 5, ["sneakers"]),
    ]
    path = write_jsonl(tmp_path / "t.jsonl", rows)
    fake = fake_llm(_script(lambda u: {"choice": 21, "quote": ""}))
    judge.run(mk_args(path, items=[QA]))
    users = [u for _s, u in fake.calls if not u.startswith("Return")]
    assert len(users) == 1 and not any("TOKEN READOUTS:" in u for u in users)
    u = users[0]
    assert "[L20 pos 5] grief | child | accident\n[L20 pos 6] kitchen | light\n" in u
    assert "[L36 pos 5] sneakers" in u
    assert u.startswith(digest.token_note_of("conjunctive_association") + "\n\nREADOUTS:\n")


TOKEN_ROWS = [
    {"layer": 36, "pos": 5, "tokens": ["sabotage", "demo", "colleague", "revenge"]},
    {"layer": 44, "pos": 9, "tokens": ["promotion", "CEO", "office"]},
]


@pytest.mark.parametrize("mode", ["native", "summary"])
def test_token_quote_within_one_list_verifies(mode, tmp_path, fake_llm, monkeypatch):
    path = write_jsonl(tmp_path / "t.jsonl", [{"id": Q08C, **r} for r in TOKEN_ROWS])
    shown, _gold, _c = _opts(Q08C)
    seen: list[str] = []

    def rejudge(u):
        seen.append(u)
        return {"choice": len(shown), "quote": ""}

    res = _run_mode(
        mode,
        path,
        tmp_path,
        fake_llm,
        monkeypatch,
        _gold_with(Q08C, "sabotage | colleague"),
        rejudge,
    )
    assert res.rows[0]["quote_ok"] is True and res.rows[0]["pick"] == "gold_partial"
    assert seen and seen[0].startswith(
        "READOUT (tokens quoted from one ranked list, ' | ' separated):\nsabotage | colleague\n\n"
    )


@pytest.mark.parametrize("mode", ["native", "summary"])
def test_token_quote_across_lists_is_unverified(mode, tmp_path, fake_llm, monkeypatch):
    path = write_jsonl(tmp_path / "t.jsonl", [{"id": Q08C, **r} for r in TOKEN_ROWS])
    res = _run_mode(
        mode, path, tmp_path, fake_llm, monkeypatch, _gold_with(Q08C, "sabotage | promotion")
    )
    assert res.rows[0]["pick"] == "gold_unverified" and res.rows[0]["quote_ok"] is False


@pytest.mark.parametrize("mode", ["native", "summary"])
def test_token_prompts_carry_shared_rule(mode, tmp_path, fake_llm, monkeypatch):
    path = write_jsonl(tmp_path / "t.jsonl", [{"id": Q08C, **r} for r in TOKEN_ROWS])
    users: list[str] = []

    def main(u):
        users.append(u)
        return {"choice": 21, "quote": ""}

    _run_mode(mode, path, tmp_path, fake_llm, monkeypatch, main)
    assert users and all(mc.TOKEN_NOTE in u for u in users)
    for text in prompts.PROMPTS.values():
        assert "exactly one token" not in text and "its own sample: a quote" not in text


def test_flat_types_empty(real_families):
    spec = registry.FAMILIES["conjunctive_association"]
    assert spec.flat_types == () and spec.multi_select is False
    assert digest.token_note_of("conjunctive_association") == mc.token_note((), multi_select=False)
    assert digest.token_note_of("conjunctive_association") == mc.TOKEN_NOTE
    assert spec.min_full_positions == 19 and spec.full_contiguous is True
    assert spec.task_note == prompts.DIGEST_TASK_NOTE and spec.not_in_macro == ""


# ---- G-items: lite, prompt-only, task note


def _full_file(tmp_path, ids=(QA,), sampling="prose1"):
    rows = [_one(i, f"s-{i}-{L}-{p}", L, p) for i in ids for L in (20, 44) for p in range(31, 50)]
    path = write_jsonl(tmp_path / "f.jsonl", rows)
    write_sidecar(path, reads="full", sampling=sampling, reader="test", layers=[20, 44])
    return path


def _lite_positions(tmp_path, monkeypatch, out: str) -> list[str]:
    path = _full_file(tmp_path)
    seen: list[str] = []
    FakeLLM.install(
        monkeypatch,
        lambda s, u, sc: {"choice": 21, "quote": ""},
        digest=lambda u: seen.append(u) or None,
    )
    judge.run(
        summary_args(
            path, tmp_path / out, "pv", items=[QA], layers=[20, 44], extra={"reads": "lite"}
        )
    )
    every = "\n".join(seen)  # audit F1: one digest per read layer
    assert set(re.findall(r"\[L(\d+) pos \d+\]", every)) == {"20", "44"}
    return sorted(set(re.findall(r"\[L\d+ pos (\d+)\]", every)))


def test_reads_lite_reads_every_full_position(tmp_path, monkeypatch):
    # Camila r3 (2026-11-01): lite reads the same 19 positions as full (lite_rule.json `same`)
    assert readplan.frozen_lite_rule("conjunctive_association") == {"kind": "same"}
    assert _lite_positions(tmp_path, monkeypatch, "o") == [str(p) for p in range(31, 50)]


def test_reads_lite_without_the_frozen_rule_keeps_the_final_position(tmp_path, monkeypatch):
    # the other direction: the pre-r3 default (no lite_rule.json -> final_token) keeps one site
    from wsbench import reads as reads_mod

    monkeypatch.setattr(readplan, "frozen_lite_rule", lambda family: dict(readplan.FINAL))
    reads_mod._specs.cache_clear()  # the judge's plan is cached per bank environment
    try:
        assert _lite_positions(tmp_path, monkeypatch, "o") == ["49"]
    finally:
        reads_mod._specs.cache_clear()


def test_reads_lite_stamp(tmp_path, monkeypatch):
    path = _full_file(tmp_path)
    FakeLLM.install(monkeypatch, lambda s, u, sc: {"choice": 21, "quote": ""})
    args = summary_args(
        path, tmp_path / "o", "pv", items=[QA], layers=[20, 44], extra={"reads": "lite"}
    )
    r = judge.run(args)
    pv = digest.prompt_version(
        prompts.PROMPT_VERSION + prompts.RULE_VERSION, args, "conjunctive_association"
    )
    assert r.config["prompt_version"] == reads.stamp(pv, "lite") == pv + reads.LITE_STAMP
    assert json.loads(r.config["lite_rule"]) == [{"layers": None, "positions": {"kind": "same"}}]
    full = summary_args(path, tmp_path / "f", "pv", items=[QA], layers=[20, 44])
    assert judge.run(full).config["prompt_version"] == pv


def test_one_layer_one_sample_file_judges(tmp_path, monkeypatch):
    path = write_jsonl(tmp_path / "po.jsonl", [_one(QA, "grief over her child's death", 44, 77)])
    write_sidecar(path, reader="prompt_only:claude-opus-5-5", layers=[44], protocol="po-opus-v1")
    cannot = len(_opts(QA)[0])  # the escape is last (bank v3: 25 shown for q01)
    FakeLLM.install(monkeypatch, lambda s, u, sc: {"choice": cannot, "quote": ""})
    r = judge.run(summary_args(path, tmp_path / "o", "pv", items=[QA]))
    assert r.n_items == 1 and r.config["reads_checked"] == "prompt_only"
    assert r.rows[0]["pick"] == "cannot_tell" and r.extras["n_items_excluded"] == 0


def test_task_note_names_no_option():
    note = prompts.DIGEST_TASK_NOTE.lower()
    for it in load_bank("conjunctive_association"):
        for o in it["mc_options"]:
            assert o.lower() not in note
    assert "summarize it in one sentence" in note and "who feels" in note


def test_dataclass_spec_bank_is_v4(real_families):
    spec = registry.FAMILIES["conjunctive_association"]
    assert dataclasses.replace(spec).bank == Path("evals/conjunctive_association/items_v4.json")


def test_ati_entry_regated_on_v2(real_families):
    """Round 4: bank v3 / comp-v4 (now bank v4 / comp-v5) make the frozen comp-v3 entry stale,
    so subset_entry must refuse it until the run phase re-gates (decisions: every family whose
    instrument changes is re-gated in the run phase); a re-gated entry must match the current
    bank and instrument."""
    from wsbench.baselines import text_inversion as ti

    frozen = json.loads(ti.FROZEN.read_text(encoding="utf-8"))["conjunctive_association"]
    if frozen.get("instrument") != prompts.PROMPT_VERSION:
        assert frozen["instrument"] == "comp-v3"  # the stale v2 entry
        with pytest.raises(SystemExit, match="re-gate"):
            ti.subset_entry("conjunctive_association")
        return
    e = ti.subset_entry("conjunctive_association")
    assert e["instrument"] == prompts.PROMPT_VERSION and e["gate"] == "panel-v1"
    assert e["bank_sha"] == ti.bank_fingerprint("conjunctive_association")
    ids = {it["id"] for it in load_bank("conjunctive_association")}
    # 89 was the comp-v3 entry; the comp-v5 re-gate on the full four-reader panel gives 91
    # (decision R1-ATI gemini, 2026-11-01: +q03_c, +q07_a, +q10_j, -q02_a)
    assert set(e["ids"]) <= ids and e["n_ati"] == len(e["ids"]) == 91

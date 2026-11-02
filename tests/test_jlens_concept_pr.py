"""jlens_concept_pr: prompts, keys, parsers, joins, stage sequencing, rejects, headline (offline).

Ported from the source repo's ``tests/test_jlens_pr_judge_prompts.py``, ``test_jlens_pr_items.py``
(``bpe_display_to_text`` / ``foil_pairing``) and the join tests of ``test_jlens_pr_score.py``;
the CLI-module tests do not port. Keys carry no arm here: ``<cell key>:A`` / ``:Bnn`` / ``:Fnn``
/ ``:Pnnn`` / ``:Qnnn``.
"""

import json
import math
import re
from pathlib import Path
from typing import Any

import pytest
from conftest import write_jsonl

from wsbench.evals.jlens_concept_pr import SPEC
from wsbench.evals.jlens_concept_pr import judge as jj
from wsbench.evals.jlens_concept_pr import prompts as pp
from wsbench.evals.jlens_concept_pr import score as ss
from wsbench.evals.jlens_concept_pr.concept_pr import ItemScore, is_content_token
from wsbench.judge_config import JudgeConfig, ResolvedJudge, resolve

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/readouts/jlens_concept_pr.jsonl"
LABELS = ["chat-dailydialog-0000", "chat-lmsys-0000", "pt-pile-0000"]
CONCEPTS = ["figurative turn of phrase", "metaphor", "light-hearted aside"]

# Gemini as if it were the family's pinned judge: exercises the OpenRouter route's knobs
GEMINI_PINNED = ResolvedJudge(
    model="google/gemini-3.8-flash", reasoning={"effort": "minimal"}, pinned=True, source="family"
)


@pytest.fixture
def jargs(mk_args):
    """``mk_args`` with the family's pinned judge and its ``extract`` aux model."""

    def make(readouts, **kw):
        base = {
            "judge": resolve(SPEC.judge, env={}),
            "aux_models": SPEC.judge.aux_models,
            "allow_missing": True,
        }
        base.update(kw)
        return mk_args(readouts, **base)

    return make


# ------------------------------------------------------------------ prompts / keys / parsers


def test_keys() -> None:
    ck = "chat-lmsys-0001__L044__p115"
    assert jj.stage_key(ck, "a") == f"{ck}:A"
    assert jj.stage_key("x__L008__p1", "b", 3) == "x__L008__p1:B03"
    assert jj.stage_key("x__L008__p1", "foil", 3) == "x__L008__p1:F03"
    assert jj.stage_key(ck, "p", 0) == f"{ck}:P000"
    assert jj.stage_key("x__L008__p1", "pfoil", 12) == "x__L008__p1:Q012"
    for key in (f"{ck}:A", f"{ck}:F09", f"{ck}:Q012"):
        assert jj.cell_of(key) == ck and ss.cell_of(key) == ck
        assert re.fullmatch(r"[A-Za-z0-9_:-]+", key)


def test_stage_user_bodies_and_schemas() -> None:
    assert pp.render_stage_a("some text") == "Text:\nsome text"
    assert pp.STAGE_A_SCHEMA["schema"]["type"] == "object"
    assert "concepts" in pp.STAGE_A_SCHEMA["schema"]["properties"]
    body = pp.render_stage_b(" accessing", ["access pattern", "wound healing"])
    assert body == "Token: ' accessing'\n\nConcepts:\n1. access pattern\n2. wound healing"
    assert "lacks" in pp.STAGE_B_SYSTEM and "return 0" in pp.STAGE_B_SYSTEM  # worked examples
    body = pp.render_stage_p([" x", "y"], ["a", "b"])
    assert body == "Tokens: ' x', 'y'\n\nConcepts:\n1. a\n2. b"
    assert "Walt Disney" in pp.STAGE_P_SYSTEM and pp.STAGE_P_CHUNK == 60
    assert pp.GRADE_VALUE == {"in": 1.0, "partial": 0.5, "out": 0.0}
    assert (
        pp.PROMPT_VERSION == "jlens-pr-v3+fw-v2+sense-v1"
    )  # round 3 + review: deterministic stamps
    # placeholders are substituted in one pass: a value containing a placeholder survives
    assert pp.render_stage_a("{listing}") == "Text:\n{listing}"
    assert set(pp.PROMPTS) == {
        "STAGE_A_SYSTEM", "STAGE_B_SYSTEM", "STAGE_P_SYSTEM",
        "STAGE_A_USER", "STAGE_B_USER", "STAGE_P_USER",
    }  # fmt: skip


def test_parse_stage_a_dedupes() -> None:
    txt = json.dumps({"concepts": ["Protein intake", " protein  intake", "", "wound healing"]})
    assert pp.parse_stage_a(txt) == ["Protein intake", "wound healing"]
    assert pp.parse_stage_a({"concepts": ["a", 3, "A"]}) == ["a"]  # the parsed object works too
    with pytest.raises(ValueError):
        pp.parse_stage_a({"concepts": "not a list"})


def test_parse_stage_b_ok_and_order() -> None:
    concepts = ["a", "b", "c"]
    txt = json.dumps(
        {
            "grades": [
                {"concept": "c", "grade": "in"},
                {"concept": "a", "grade": "out"},
                {"concept": "b", "grade": "partial"},
            ]
        }
    )
    assert pp.parse_stage_b(txt, concepts) == [0.0, 0.5, 1.0]
    assert pp.parse_stage_p(json.loads(txt), concepts) == [0.0, 0.5, 1.0]


def test_parse_stage_b_rejects_drift() -> None:
    concepts = ["a", "b"]
    with pytest.raises(ValueError):  # missing concept
        pp.parse_stage_b(json.dumps({"grades": [{"concept": "a", "grade": "in"}]}), concepts)
    with pytest.raises(ValueError):  # extra concept
        pp.parse_stage_b(
            {
                "grades": [
                    {"concept": "a", "grade": "in"},
                    {"concept": "b", "grade": "in"},
                    {"concept": "zz", "grade": "in"},
                ]
            },
            concepts,
        )
    with pytest.raises(ValueError):  # duplicate concept
        pp.parse_stage_b(
            {"grades": [{"concept": "a", "grade": "in"}, {"concept": "a", "grade": "out"}]},
            concepts,
        )
    with pytest.raises(ValueError):  # bad grade
        pp.parse_stage_p(
            {"grades": [{"concept": "a", "grade": "yes"}, {"concept": "b", "grade": "in"}]},
            concepts,
        )


def test_stage_p_chunks_tile_the_concept_list_in_order() -> None:
    assert pp.stage_p_chunks([]) == []
    assert pp.stage_p_chunks(["a"]) == [(0, ["a"])]
    exact = [f"c{i}" for i in range(pp.STAGE_P_CHUNK)]
    assert pp.stage_p_chunks(exact) == [(0, exact)]
    for n in (pp.STAGE_P_CHUNK + 1, 279):
        cs = [f"c{i}" for i in range(n)]
        chunks = pp.stage_p_chunks(cs)
        assert [o for o, _ in chunks] == list(range(0, n, pp.STAGE_P_CHUNK))
        assert [c for _, part in chunks for c in part] == cs
        assert all(len(part) <= pp.STAGE_P_CHUNK for _, part in chunks)


def test_bpe_display_to_text() -> None:
    assert jj.bpe_display_to_text("çļĦç»ĵæŀľ") == "的结果"
    assert jj.bpe_display_to_text(" result") == " result"  # Ġ already replaced by capture
    assert jj.bpe_display_to_text("Ċ") == "\n"
    assert jj.bpe_display_to_text("Ã©") == "é"


def test_foil_pairing_is_a_derangement_within_group() -> None:
    groups = {"chat:44": ["a", "b", "c", "d"], "pt:44": ["x", "y"], "solo:44": ["z"]}
    m = jj.foil_pairing(groups, seed=3)
    assert set(m) == {"a", "b", "c", "d", "x", "y"}
    for k, v in m.items():
        assert k != v
    assert {m["a"], m["b"], m["c"], m["d"]} == {"a", "b", "c", "d"}
    assert {m["x"], m["y"]} == {"x", "y"}
    assert m == jj.foil_pairing(groups, seed=3)


def test_bank_manifest_and_reference() -> None:
    man = jj.load_manifest()
    items = jj.manifest_items(man)
    assert len(items) == 299 and man["layers"] == [20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60]
    assert {it["family"] for it in items} == {"chat", "pt"}
    l42 = json.loads((jj.BANK_DIR / "manifest_L42.json").read_text())
    assert l42["layers"] == [42]
    assert [p["label"] for p in l42["prompts"]] == [it["id"] for it in items]
    # the rollouts (decoded `tokens`) were stripped on 2026-09-17; the read position stays valid
    for p in man["prompts"] + l42["prompts"]:
        assert "tokens" not in p and 0 <= p["eval_positions"][0] < p["n_pos"]
    for it in items[:3]:
        for layer in (20, 42, 44, 60):
            assert jj.reference_path(it["id"], layer).exists()
    toks = jj.reference_tokens("chat-lmsys-0000", 44, items[0]["pos"])
    assert len(toks) == 10 and toks[0] == " languages" and "日本語" in toks
    fm = jj.foil_map(items)
    assert set(fm) == {it["id"] for it in items}
    fam = {it["id"]: it["family"] for it in items}
    assert all(fam[a] == fam[b] and a != b for a, b in fm.items())


# ------------------------------------------------------------------ joins (ported)


def test_assemble_grids_by_token_idx_and_full_grid() -> None:
    rows = [
        {"key": "a__L044__p1:B02", "token_idx": 2, "token": " y", "grades": [0.0, 0.5]},
        {"key": "a__L044__p1:B00", "token_idx": 0, "token": " x", "grades": [1.0, 0.0]},
    ]
    grids = ss.assemble_grids(rows)
    assert grids == {"a__L044__p1": {0: [1.0, 0.0], 2: [0.0, 0.5]}}
    grid = ss.full_grid(grids["a__L044__p1"], [0, 2])
    assert grid == [[1.0, 0.0], [0.0, 0.5]]
    # a content token with no grade row -> the cell is incomplete, never partially scored
    assert ss.full_grid(grids["a__L044__p1"], [0, 2, 3]) is None
    assert grid is not None
    s = ss.score_cell(grid, n_concepts=2, n_tokens_total=4)
    assert s.precision == pytest.approx(0.75)
    assert s.recall_at_m == pytest.approx(0.75)


def test_zero_concept_item_scores_zero_not_nan() -> None:
    s = ss.score_cell(ss.zero_grid(3), n_concepts=0, n_tokens_total=5)
    assert s.precision == 0.0 and s.recall_at_m == 0.0 and s.raw_recall == 0.0
    assert s.n_content_tokens == 3


def test_all_punctuation_item_is_nan_on_both_axes() -> None:
    s = ss.score_cell(ss.zero_grid(0), n_concepts=4, n_tokens_total=10)
    assert math.isnan(s.precision) and math.isnan(s.recall_at_m)


def test_score_one_cell_statuses() -> None:
    by_idx = {0: [1.0, 0.0], 2: [0.0, 0.5]}
    st, s = ss.score_one_cell(
        concepts=["a", "b"], had_text=True, by_idx=by_idx, content_idx=[0, 2], n_tokens_total=4
    )
    assert st == "ok" and s.precision == pytest.approx(0.75)
    # a content token without a grade row -> incomplete_b, NaN placeholder, no exception
    st, s = ss.score_one_cell(
        concepts=["a", "b"], had_text=True, by_idx=by_idx, content_idx=[0, 2, 3], n_tokens_total=5
    )
    assert st == "incomplete_b" and math.isnan(s.precision) and s.n_concepts == 2
    assert s.n_content_tokens == 3 and s.n_tokens == 5
    # text but Stage A never returned -> missing_a
    st, s = ss.score_one_cell(
        concepts=None, had_text=True, by_idx={}, content_idx=[0], n_tokens_total=2
    )
    assert st == "missing_a" and math.isnan(s.recall_at_m)
    # no text at all -> ok with zeros (a lens fact)
    st, s = ss.score_one_cell(
        concepts=None, had_text=False, by_idx={}, content_idx=[0], n_tokens_total=2
    )
    assert st == "ok" and s.precision == 0.0 and s.recall_at_m == 0.0
    # judged, zero concepts -> ok with zeros
    st, s = ss.score_one_cell(
        concepts=[], had_text=True, by_idx={}, content_idx=[0], n_tokens_total=2
    )
    assert st == "ok" and s.precision == 0.0


def test_missing_p_costs_precision_only_and_keeps_recall() -> None:
    """A precision-judge failure must not throw away a good Stage B recall measurement."""
    status, s = ss.score_one_cell(
        concepts=["a", "b"],
        had_text=True,
        by_idx={0: [1.0, 0.0], 1: [0.0, 0.5]},
        content_idx=[0, 1],
        n_tokens_total=4,
        support=None,
        support_expected=True,
    )
    assert status == "missing_p"
    assert math.isnan(s.precision)
    assert not math.isnan(s.recall_at_m) and not math.isnan(s.raw_recall)
    assert s.n_concepts == 2 and s.n_content_tokens == 2


def test_assemble_support_concatenates_chunks_and_drops_incomplete_cells() -> None:
    concepts = {"a__L044__p1": ["c0", "c1", "c2"], "b__L044__p1": ["c0", "c1", "c2"]}
    rows = [
        {"key": "a__L044__p1:P001", "chunk": 1, "offset": 2, "support": [0.5]},
        {"key": "a__L044__p1:P000", "chunk": 0, "offset": 0, "support": [1.0, 0.0]},
        # cell b is missing its first chunk -> must not be scored on a partial concept list
        {"key": "b__L044__p1:P001", "chunk": 1, "offset": 2, "support": [1.0]},
    ]
    assert ss.assemble_support(rows, concepts) == {"a__L044__p1": [1.0, 0.0, 0.5]}


def test_assemble_support_drops_a_cell_whose_length_disagrees_with_stage_a() -> None:
    concepts = {"a__L044__p1": ["c0", "c1", "c2", "c3"]}
    rows = [{"key": "a__L044__p1:P000", "chunk": 0, "offset": 0, "support": [1.0, 0.0, 0.5]}]
    assert ss.assemble_support(rows, concepts) == {}


def test_assemble_support_drops_cells_with_duplicate_or_overlapping_chunks() -> None:
    concepts = {"a__L044__p1": ["c0", "c1", "c2", "c3"]}
    dup = [
        {"key": "a__L044__p1:P000", "chunk": 0, "offset": 0, "support": [1.0, 0.0]},
        {"key": "a__L044__p1:P001", "chunk": 1, "offset": 0, "support": [0.5, 1.0]},
    ]
    assert ss.assemble_support(dup, concepts) == {}
    overlap = [
        {"key": "a__L044__p1:P000", "chunk": 0, "offset": 0, "support": [1.0, 0.0, 0.5]},
        {"key": "a__L044__p1:P001", "chunk": 1, "offset": 2, "support": [0.5, 1.0]},
    ]
    assert ss.assemble_support(overlap, concepts) == {}


def test_reject_block() -> None:
    assert ss.reject_block(set(), set()) == {"n_requests": 0, "n_missing": 0, "rate": 0.0}
    rb = ss.reject_block({"a", "b", "c"}, {"c", "d"})  # c was re-collected; d is still missing
    assert rb == {"n_requests": 4, "n_missing": 1, "rate": 0.25}


def test_block_means_cis_and_exclusions() -> None:
    def m(status: str, n_text: int = 30, has_text: bool = True) -> dict:
        return {"status": status, "n_text_tokens": n_text, "has_text": has_text}

    real = [
        (m("ok"), ItemScore(0.5, 0.4, 0.4, 5, 8, 10)),
        (m("ok", 50), ItemScore(0.7, 0.6, 0.6, 7, 9, 10)),
        (m("ok", 0, False), ItemScore(0.0, 0.0, 0.0, 0, 9, 10)),  # no-text: zero, a lens fact
        (m("missing_a", 40), ItemScore(0.0, 0.0, 0.0, 0, 9, 10)),  # excluded, counted
        (m("incomplete_b", 20), ItemScore(0.0, 0.0, 0.0, 3, 8, 10)),
        (m("missing_p"), ItemScore(math.nan, 0.8, 0.8, 5, 8, 10)),
    ]
    foil = [
        (m("ok"), ItemScore(0.1, 0.1, 0.1, 5, 8, 10)),
        (m("missing_p"), ItemScore(math.nan, 0.2, 0.2, 5, 8, 10)),
    ]
    b = ss.block(real, foil)
    assert b["precision"] == pytest.approx((0.5 + 0.7 + 0.0) / 3)
    assert b["recall_at_10"] == pytest.approx((0.4 + 0.6 + 0.0 + 0.8) / 4)  # missing_p keeps recall
    assert b["foil_precision"] == pytest.approx(0.1)
    assert b["foil_recall_at_10"] == pytest.approx(0.15)
    assert b["n_items"] == 6 and b["n_items_no_text"] == 1 and b["n_items_scored"] == 3
    assert b["n_items_missing_a"] == 1 and b["n_items_incomplete_b"] == 1
    assert b["n_items_missing_p"] == 1
    # text/concept counts include incomplete_b (Stage A succeeded), exclude missing_a
    assert b["mean_text_tokens"] == pytest.approx((30 + 50 + 0 + 20 + 30) / 5)
    assert b["punct_frac"] == pytest.approx(1 - 51 / 60)
    assert b["precision_ci"] is not None and len(b["precision_ci"]) == 2
    assert ss.block([], [])["precision"] is None and ss.block([], [])["precision_ci"] is None


def test_headline_layer_rule() -> None:
    assert ss.headline_layer([42]) == 42
    assert ss.headline_layer([20, 44, 60]) == 44
    assert ss.headline_layer([48, 52]) is None
    assert ss.headline_layer([]) is None


# ------------------------------------------------------------------ the family run


def _concepts_of(user: str) -> list[str]:
    listing = user.split("Concepts:\n", 1)[1]
    return [line.split(". ", 1)[1] for line in listing.splitlines()]


def _grade_b(token_line: str, concept: str) -> str:
    return "in" if concept == "metaphor" and "metaphor" in token_line else "out"


def _grade_p(concept: str) -> str:
    return {"metaphor": "in", "figurative turn of phrase": "partial"}.get(concept, "out")


def _first_shown_token(user: str) -> str:
    """The first token of a Stage-P ``Tokens:`` line, as shown (its ``repr``)."""
    m = re.match(r"Tokens: ('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")", user)
    assert m, user[:80]
    return m.group(1)


def _responder(system: str, user: str) -> dict[str, Any] | None:
    if user.startswith("Return"):
        return {"a": 1}
    if system == pp.STAGE_A_SYSTEM:
        assert user.startswith("Text:\n")
        return {"concepts": CONCEPTS}
    concepts = _concepts_of(user)
    if system == pp.STAGE_B_SYSTEM:
        tok = user.split("\n", 1)[0]
        return {"grades": [{"concept": c, "grade": _grade_b(tok, c)} for c in concepts]}
    assert system == pp.STAGE_P_SYSTEM
    shown = _first_shown_token(user)  # v3: an in/partial grade names its grounding token
    return {
        "grades": [
            {"concept": c, "grade": _grade_p(c), "token": "" if _grade_p(c) == "out" else shown}
            for c in concepts
        ]
    }


def _stage_calls(fake) -> dict[str, list[dict]]:
    """The fake's create() kwargs grouped by stage (via the system prompt)."""
    out: dict[str, list[dict]] = {"A": [], "B": [], "P": [], "pre": []}
    for kw in fake.kwargs:
        system = kw["messages"][0]["content"]
        user = kw["messages"][1]["content"]
        if user.startswith("Return"):
            out["pre"].append(kw)
        elif system == pp.STAGE_A_SYSTEM:
            out["A"].append(kw)
        elif system == pp.STAGE_B_SYSTEM:
            out["B"].append(kw)
        else:
            assert system == pp.STAGE_P_SYSTEM
            out["P"].append(kw)
    return out


def test_stage_sequencing_models_and_numbers(tmp_path, fake_llm, jargs):
    fake = fake_llm(_responder)
    args = jargs(EXAMPLE, items=LABELS, judge=GEMINI_PINNED, extra={"stage_p_foil": "0"})
    res = jj.run(args)
    st = _stage_calls(fake)
    # A -> B/foil -> P, in that order; preflight once per (model, reasoning)
    stage_of = {pp.STAGE_A_SYSTEM: "A", pp.STAGE_B_SYSTEM: "B", pp.STAGE_P_SYSTEM: "P"}
    kinds = ["pre" if u.startswith("Return") else stage_of[s] for s, u in fake.calls]
    # one judge for every stage -> a single preflight
    assert kinds == ["pre"] + ["A"] * 3 + ["B"] * 60 + ["P"] * 3
    assert {kw["model"] for kw in st["A"] + st["B"] + st["P"]} == {"google/gemini-3.8-flash"}
    assert all(
        kw["extra_body"]["reasoning"] == {"effort": "minimal"} for kw in st["A"] + st["B"] + st["P"]
    )
    assert all("temperature" not in kw for kw in st["A"] + st["B"])
    assert all(kw["temperature"] == 0.0 for kw in st["P"])
    assert all(kw["max_tokens"] == 16000 for kw in st["A"] + st["B"] + st["P"])
    # Stage B: 10 content tokens x 3 cells for the real pass and the foil pass each
    b_users = [kw["messages"][1]["content"] for kw in st["B"]]
    assert sum("Token: ' metaphor'" in u for u in b_users) == 1  # label 0 at L44, real pass
    assert "Tokens: ' metaphor', ' 😉'" in st["P"][0]["messages"][1]["content"]
    # numbers: precision = mean Stage-P support = (1 + 0.5 + 0) / 3 per cell; headline L44
    assert res.family == "jlens_concept_pr" and res.metric == "precision"
    assert res.higher_is_better is True and res.chance is None
    # plan 0042 item 1 (Camila: "the chance label advertises a measured foil"): foil off -> the
    # label says so (was ss.CHANCE_LABEL here, the reported bug)
    assert res.chance_label == ss.CHANCE_LABEL_UNMEASURED
    assert res.value == pytest.approx(0.5) and res.n_items == 3 and res.ci95 is not None
    e = res.extras
    assert e["headline_layer"] == 44 and set(e["by_layer"]) == {"44", "48"}
    assert e["recall_at_10"] == pytest.approx((0.1 + 0 + 0) / 3)  # one "in" token of ten
    assert e["raw_recall"] == pytest.approx(e["recall_at_10"])
    assert e["foil"] == {"recall_at_10": 0.0, "precision": None}  # no pfoil pass
    assert e["mean_n_concepts"] == 3.0 and e["punct_frac"] == 0.0
    assert e["statuses"] == {"ok": 4}
    assert e["reject_rate"] == {
        "a": {"n_requests": 3, "n_missing": 0, "rate": 0.0},
        "b": {"n_requests": 30, "n_missing": 0, "rate": 0.0},
        "foil": {"n_requests": 30, "n_missing": 0, "rate": 0.0},
        "p": {"n_requests": 3, "n_missing": 0, "rate": 0.0},
    }
    c = res.counts
    assert c["n_expected_cells"] == 6 and c["n_missing_cells"] == 2 and c["n_empty_cells"] == 1
    assert c["n_unjudged_cells"] == 0 and c["skipped_rows"] == 0 and c["spend_usd"] > 0
    assert res.complete is False and res.pinned_instrument is True  # missing + subset
    empty = next(r for r in res.rows if r["layer"] == 48)
    assert empty["has_text"] is False and empty["status"] == "ok" and empty["n_concepts"] == 0
    assert empty["precision"] == 0.0 and empty["passed"] is False
    row = next(r for r in res.rows if r["id"] == LABELS[0] and r["layer"] == 44)
    assert row["passed"] is True and row["foil_status"] == "missing_p"
    assert row["foil_precision"] is None and row["foil_recall_at_10"] == 0.0
    assert row["n_content_tokens"] == 10 and row["n_tokens"] == 10 and row["family"] == "chat"
    assert res.config["extract_model"] == "google/gemini-3.8-flash"
    assert res.config["stage_p_temperature"] == 0.0 and res.config["stage_p_foil"] is False
    # resume: everything cached, no calls
    fake2 = fake_llm(_responder)
    again = jj.run(args)
    assert fake2.calls == [] and again.value == res.value


def test_reject_handling_and_resume(tmp_path, fake_llm, jargs):
    """A drifted Stage B answer and a failed Stage P call are rejects: cached as failures,
    counted, and exactly those keys are re-issued by the next run."""

    def flaky(system, user):
        if system == pp.STAGE_B_SYSTEM and user.startswith("Token: ' pretty'"):
            return {"grades": [{"concept": "zz", "grade": "in"}]}  # concept drift
        if system == pp.STAGE_P_SYSTEM and "languages" in user.split("\n", 1)[0]:
            return None  # API failure
        return _responder(system, user)

    fake = fake_llm(flaky)
    args = jargs(EXAMPLE, items=LABELS, extra={"stage_p_foil": "0"})
    res = jj.run(args)
    e = res.extras
    assert e["reject_rate"]["b"] == {"n_requests": 30, "n_missing": 1, "rate": 1 / 30}
    assert e["reject_rate"]["p"] == {"n_requests": 3, "n_missing": 1, "rate": 1 / 3}
    assert e["statuses"] == {"incomplete_b": 1, "missing_p": 1, "ok": 2}
    assert res.counts["n_unjudged_cells"] == 2 and res.n_items == 1
    by = {(r["id"], r["layer"]): r for r in res.rows}
    assert by[(LABELS[0], 44)]["status"] == "incomplete_b"
    assert by[(LABELS[0], 44)]["precision"] is None and by[(LABELS[0], 44)]["recall_at_10"] is None
    assert by[(LABELS[1], 44)]["status"] == "missing_p"
    assert by[(LABELS[1], 44)]["precision"] is None and by[(LABELS[1], 44)]["recall_at_10"] == 0.0
    failed = [
        u
        for _s, u in fake.calls
        if u.startswith("Token: ' pretty'")
        or ("Tokens:" in u and "languages" in u.split("\n", 1)[0])
    ]
    assert len(failed) == 2
    rows = [json.loads(line) for line in (args.out / "cells.jsonl").read_text().splitlines()]
    drifted = [r for r in rows if r["result"] is None]
    assert len(drifted) == 2 and any("raw" in r["meta"] for r in drifted)
    # second run re-issues exactly the two rejected keys, then everything is scored
    fake2 = fake_llm(_responder)
    res2 = jj.run(args)
    reissued = [u for _s, u in fake2.calls if not u.startswith("Return")]
    assert sorted(reissued) == sorted(failed)
    assert res2.extras["statuses"] == {"ok": 4} and res2.value == pytest.approx(0.5)
    assert res2.extras["reject_rate"]["b"]["n_missing"] == 0


def test_pfoil_opt_measures_foil_precision(tmp_path, fake_llm, jargs):
    fake = fake_llm(_responder)
    res = jj.run(jargs(EXAMPLE, items=LABELS, extra={"stage_p_foil": "1"}))
    assert len(_stage_calls(fake)["P"]) == 6
    assert res.extras["foil"]["precision"] == pytest.approx(0.5)
    assert res.extras["reject_rate"]["pfoil"]["n_requests"] == 3
    assert res.config["stage_p_foil"] is True


def test_headline_layer_without_l44(tmp_path, fake_llm, jargs, capsys):
    pos = jj.manifest_items(jj.load_manifest())[0]["pos"]
    rows = [
        {"id": "chat-lmsys-0000", "layer": layer, "pos": pos, "samples": ["a metaphor"]}
        for layer in (48, 52)
    ]
    fake_llm(_responder)
    res = jj.run(jargs(write_jsonl(tmp_path / "r.jsonl", rows), items=["chat-lmsys-0000"]))
    assert res.value is None and res.ci95 is None and res.n_items == 0
    assert res.extras["headline_layer"] is None and res.complete is False
    assert set(res.extras["by_layer"]) == {"48", "52"}
    assert "no headline" in capsys.readouterr().out
    # exactly one judged layer: that one is the headline
    fake_llm(_responder)
    res = jj.run(jargs(write_jsonl(tmp_path / "r2.jsonl", rows[:1]), items=["chat-lmsys-0000"]))
    assert res.extras["headline_layer"] == 48 and res.value == pytest.approx(0.5)


def test_missing_cells_stop_the_run_unless_allowed(tmp_path, fake_llm, jargs):
    fake = fake_llm(_responder)
    with pytest.raises(SystemExit) as e:
        jj.run(jargs(EXAMPLE, items=LABELS, allow_missing=False))
    assert e.value.code == 2 and fake.calls == []


def test_unknown_layer_is_fatal_before_any_call(tmp_path, monkeypatch, jargs):
    monkeypatch.setattr("wsbench.llm._make_client", lambda r, k: pytest.fail("no client"))
    pos = jj.manifest_items(jj.load_manifest())[0]["pos"]
    src = write_jsonl(
        tmp_path / "r.jsonl", [{"id": "chat-lmsys-0000", "layer": 99, "pos": pos, "samples": ["x"]}]
    )
    with pytest.raises(SystemExit) as e:
        jj.run(jargs(src, items=["chat-lmsys-0000"]))
    assert e.value.code == 2
    with pytest.raises(SystemExit):
        jj.run(jargs(EXAMPLE, items=LABELS, layers=[44, 99]))


def test_tokens_readouts_are_refused(tmp_path, monkeypatch, jargs):
    monkeypatch.setattr("wsbench.llm._make_client", lambda r, k: pytest.fail("no client"))
    pos = jj.manifest_items(jj.load_manifest())[0]["pos"]
    src = write_jsonl(
        tmp_path / "t.jsonl", [{"id": "chat-lmsys-0000", "layer": 44, "pos": pos, "tokens": ["x"]}]
    )
    with pytest.raises(SystemExit) as e:
        jj.run(jargs(src, items=["chat-lmsys-0000"]))
    assert e.value.code == 2


def test_off_position_rows_are_skipped(tmp_path, fake_llm, jargs):
    pos = jj.manifest_items(jj.load_manifest())[0]["pos"]
    rows = [
        {"id": "chat-lmsys-0000", "layer": 44, "pos": pos, "samples": ["a metaphor"]},
        {"id": "chat-lmsys-0000", "layer": 44, "pos": pos + 1, "samples": ["not the eval pos"]},
        {"id": "nope", "layer": 44, "pos": 1, "samples": ["unknown"]},
    ]
    fake_llm(_responder)
    res = jj.run(jargs(write_jsonl(tmp_path / "r.jsonl", rows), items=["chat-lmsys-0000"]))
    assert res.counts["skipped_rows"] == 2 and res.counts["n_expected_cells"] == 1
    assert res.counts["n_missing_cells"] == 0


def test_complete_needs_full_grid_pinned_judge_and_low_reject_rate(tmp_path, fake_llm, jargs):
    items = jj.manifest_items(jj.load_manifest())
    src = write_jsonl(
        tmp_path / "full.jsonl",
        [
            {"id": it["id"], "layer": 44, "pos": it["pos"], "samples": ["a metaphor"]}
            for it in items
        ],
    )
    fake = fake_llm(_responder)
    res = jj.run(jargs(src, allow_missing=False))
    assert res.complete is True and res.n_items == 299 and res.counts["n_missing_cells"] == 0
    assert len(_stage_calls(fake)["A"]) == 299 and res.extras["headline_layer"] == 44
    # sense-v1 (review): one item's first shown token is ' often', grounding neither fake concept
    assert res.value == pytest.approx(149 / 299)
    # an unpinned judge, or a reject rate above 5% on any stage, breaks completeness
    fake_llm(_responder)
    other = jargs(
        src, allow_missing=False, judge=resolve(JudgeConfig(), flag="other/model", env={})
    )
    assert jj.run(other).complete is False and jj.run(other).pinned_instrument is False

    def p_fails(system, user):
        return None if system == pp.STAGE_P_SYSTEM else _responder(system, user)

    fake_llm(p_fails)
    args = jargs(src, allow_missing=False, out=tmp_path / "out2")
    res = jj.run(args)
    assert res.complete is False and res.extras["reject_rate"]["p"]["rate"] == 1.0
    assert res.value is None and res.n_items == 0 and res.counts["n_unjudged_cells"] == 299
    assert res.extras["statuses"] == {"missing_p": 299}
    assert res.extras["recall_at_10"] is not None  # recall survives a precision failure


def test_dry_run_prints_stage_a_only(tmp_path, jargs, capsys, monkeypatch):
    monkeypatch.setattr("wsbench.llm._make_client", lambda r, k: pytest.fail("no client"))
    res = jj.run(jargs(EXAMPLE, dry_run=True, allow_missing=False))  # missing is not fatal here
    out = capsys.readouterr().out
    assert pp.STAGE_A_SYSTEM in out and "Text:\n" in out and "missing cells" in out
    assert pp.STAGE_B_SYSTEM not in out and pp.STAGE_P_SYSTEM not in out
    assert res.value is None and res.ci95 is None and res.rows == [] and res.n_items == 0
    assert res.config["dry_run"] is True and res.complete is False
    assert res.counts["spend_usd"] == 0.0 and res.counts["n_expected_cells"] == 299 * 2


def test_content_token_filter_matches_reference_tokens() -> None:
    items = jj.manifest_items(jj.load_manifest())
    toks = jj.reference_tokens(
        LABELS[0],
        44,
        items[0]["pos"]
        if items[0]["id"] == LABELS[0]
        else next(it["pos"] for it in items if it["id"] == LABELS[0]),
    )
    assert [is_content_token(t) for t in toks] == [True] * 10


def test_no_content_token_cell_is_ok_with_nan():
    import math

    from wsbench.evals.jlens_concept_pr.score import score_one_cell

    status, scored = score_one_cell(
        concepts=["a", "b"],
        had_text=True,
        by_idx={},
        content_idx=[],
        n_tokens_total=10,
        support=None,
        support_expected=False,
    )
    assert status == "ok"
    assert math.isnan(scored.precision) and math.isnan(scored.recall_at_m)
    assert scored.n_concepts == 2 and scored.n_content_tokens == 0


# ------------------------------------------------------------------ plan 0042 (jlens-pr-v3)


def _ok_cell(key: str, layer: int, *, concepts: list[str] | None, toks: list[str]) -> ss.CellInput:
    return ss.CellInput(
        key=key,
        id=key.split("__")[0],
        layer=layer,
        pos=1,
        family="chat",
        has_text=concepts is not None,
        n_text_tokens=3,
        concepts=concepts,
        tokens=toks,
        foil_tokens=toks,
    )


def _score(inputs, *, measured: bool, pfoil_support: dict | None = None, layers=(44, 48)):
    from types import SimpleNamespace

    args = SimpleNamespace(
        judge=SimpleNamespace(pinned=True),
        items=None,
        limit=0,
        scope="",
        dry_run=False,
        extra={},
        readouts=None,
    )
    grids = {"b": {}, "foil": {}}
    for ci in inputs:
        if ci.concepts:
            n = len(ci.concepts)
            grids["b"][ci.key] = {i: [1.0] * n for i in range(len(ci.tokens))}
            grids["foil"][ci.key] = {i: [0.0] * n for i in range(len(ci.tokens))}
    support = {
        "p": {ci.key: [1.0] * len(ci.concepts) for ci in inputs if ci.concepts},
        "pfoil": pfoil_support or {},
    }
    return ss.score(
        args,  # type: ignore[arg-type]
        inputs,
        layers=list(layers),
        grids=grids,
        support=support,
        reject_rate={},
        counts_base={"n_expected_cells": len(inputs), "n_missing_cells": 0, "n_empty_cells": 0},
        config={},
        foil_precision_measured=measured,
    )


def test_foil_precision_is_null_without_pfoil() -> None:
    """Camila: "with the foil step off ... the foil precision reports 0.0 instead of 'not
    measured'". A zero-concept cell at L48 used to make by_layer["48"].foil_precision 0.0."""
    toks = [" metaphor", " figure"]
    inputs = [
        _ok_cell("a__L044__p1", 44, concepts=["metaphor"], toks=toks),
        _ok_cell("a__L048__p1", 48, concepts=None, toks=toks),  # empty text, zero concepts
    ]
    res = _score(inputs, measured=False)
    assert res.extras["by_layer"]["48"]["foil_precision"] is None
    assert res.extras["by_layer"]["44"]["foil_precision"] is None
    assert all(r["foil_precision"] is None for r in res.rows)
    assert res.extras["foil"]["precision"] is None
    assert res.chance_label == ss.CHANCE_LABEL_UNMEASURED
    # foil on, but no Q call returned at L48 (its only foil cell has zero concepts): still null
    on = _score(inputs, measured=True, pfoil_support={"a__L044__p1": [0.0]})
    assert on.extras["by_layer"]["44"]["foil_precision"] == 0.0
    assert on.extras["by_layer"]["48"]["foil_precision"] is None
    assert on.chance_label == ss.CHANCE_LABEL


def test_pfoil_runs_by_default(tmp_path, fake_llm, jargs):
    fake = fake_llm(_responder)
    res = jj.run(jargs(EXAMPLE, items=LABELS))
    assert len(_stage_calls(fake)["P"]) == 6  # 3 real + 3 foil
    assert res.config["stage_p_foil"] is True
    assert isinstance(res.extras["foil"]["precision"], float)
    assert res.chance_label == ss.CHANCE_LABEL


def test_stage_p_foil_opt_out(tmp_path, fake_llm, jargs):
    fake = fake_llm(_responder)
    res = jj.run(jargs(EXAMPLE, items=LABELS, extra={"stage_p_foil": "0"}))
    assert len(_stage_calls(fake)["P"]) == 3
    assert res.extras["foil"]["precision"] is None
    assert all(b["foil_precision"] is None for b in res.extras["by_layer"].values())
    assert res.chance_label == ss.CHANCE_LABEL_UNMEASURED


_JUNK_SPELLINGS = {
    " �": 134,
    "�": 75,
    "<|endoftext|>": 19,
    "<|im_end|>": 18,
    "<|fim_middle|>": 16,
    "<|file_sep|>": 14,
    "<tool_call>": 12,
    "</think>": 11,
    "<|im_start|>": 10,
    "<think>": 9,
    "</tool_response>": 1,
}
# cells whose every content-classified token is a special tag: no information after the fix
_ALL_TAG_CELLS = {
    ("chat-lmsys-0013", 52),
    ("chat-lmsys-0013", 60),
    ("chat-lmsys-0046", 52),
    ("chat-lmsys-0046", 56),
    ("chat-lmsys-0046", 60),
}


def test_junk_tokens_in_frozen_reference() -> None:
    """Items 2/4: the shipped references hold exactly these junk spellings (209 U+FFFD + 110
    tags); the filter matches nothing else, and only 5 all-tag cells lose every content token."""
    from collections import Counter

    from wsbench.evals.jlens_concept_pr.concept_pr import is_junk_token

    items = jj.manifest_items(jj.load_manifest())
    junk: Counter[str] = Counter()
    emptied = set()
    for it in items:
        for layer in [*range(20, 61, 4), 42]:
            toks = jj.reference_tokens(it["id"], layer, it["pos"])
            junk.update(t for t in toks if is_junk_token(t))
            old_content = [t for t in toks if is_content_token(t) or is_junk_token(t)]
            if old_content and not any(is_content_token(t) for t in toks):
                emptied.add((it["id"], layer))
    assert dict(junk) == _JUNK_SPELLINGS
    assert sum(v for k, v in junk.items() if "�" in k) == 209
    assert sum(v for k, v in junk.items() if "�" not in k) == 110
    assert emptied == _ALL_TAG_CELLS


def test_junk_tokens_get_no_stage_b_call(tmp_path, fake_llm, jargs):
    label = "chat-dailydialog-0046"
    pos = next(it["pos"] for it in jj.manifest_items(jj.load_manifest()) if it["id"] == label)
    ref = jj.reference_tokens(label, 44, pos)
    assert sum("�" in t for t in ref) == 4 and len(ref) == 10
    content = [t for t in ref if is_content_token(t)]
    assert len(content) == 6
    src = write_jsonl(
        tmp_path / "r.jsonl", [{"id": label, "layer": 44, "pos": pos, "samples": ["a metaphor"]}]
    )
    fake = fake_llm(_responder)
    res = jj.run(jargs(src, items=[label]))
    st = _stage_calls(fake)
    real_set = "Token set: " + pp.token_list(content)
    real_b = [kw for kw in st["B"] if real_set in kw["messages"][1]["content"]]
    assert len(real_b) == 6  # 10 tokens, 4 of them U+FFFD fragments
    assert all("�" not in kw["messages"][1]["content"] for kw in st["B"] + st["P"])
    row = res.rows[0]
    assert row["n_content_tokens"] == 6 and row["n_junk_tokens"] == 4 and row["n_tokens"] == 10
    assert res.extras["by_layer"]["44"]["junk_frac"] == pytest.approx(0.4)


def test_stage_p_prompt_has_overlap_rules() -> None:
    for system in (pp.STAGE_P_SYSTEM, pp.STAGE_B_SYSTEM):
        assert "'osis' is out for 'congenital ptosis'" in system
        assert "'no incentives' is out for 'incentives'" in system
        assert "' billions' is out for '4.5 billion years ago'" in system
        assert pp.OVERLAP_RULES in system
    # the calibrated "says more than the token" example survives the scoped negation rule
    assert '"no worry about overlap" is in' in pp.STAGE_P_SYSTEM
    assert "'no worry about overlap' stays in for 'overlap'" in pp.OVERLAP_RULES


def test_parse_stage_p_requires_grounding_token() -> None:
    concepts = ["congenital ptosis", "eyelid"]
    toks = ["osis", " eyel"]

    def ans(g1: str, t1: str, g2: str = "out", t2: str = "") -> dict:
        return {
            "grades": [
                {"concept": "congenital ptosis", "grade": g1, "token": t1},
                {"concept": "eyelid", "grade": g2, "token": t2},
            ]
        }

    assert pp.parse_stage_p(ans("out", ""), concepts, toks) == [0.0, 0.0]
    assert pp.parse_stage_p(ans("in", "' eyel'", "partial", " EYEL "), concepts, toks) == [
        1.0,
        0.5,
    ]
    with pytest.raises(ValueError):  # in, citing a token that was not shown
        pp.parse_stage_p(ans("in", "ptosis"), concepts, toks)
    with pytest.raises(ValueError):  # partial with no grounding token
        pp.parse_stage_p(ans("partial", ""), concepts, toks)
    # without the shown set the grades parse as before (v2 cached answers stay readable)
    assert pp.parse_stage_p(ans("in", "ptosis"), concepts) == [1.0, 0.0]
    assert pp.STAGE_P_SCHEMA["schema"]["properties"]["grades"]["items"]["required"] == [
        "concept",
        "grade",
        "token",
    ]


def test_prompt_version_is_v3() -> None:
    assert (
        pp.PROMPT_VERSION == "jlens-pr-v3+fw-v2+sense-v1"
    )  # round 3 + review: deterministic stamps
    assert SPEC.judge.prompt_version == pp.PROMPT_VERSION
    readme = (ROOT / "evals/jlens_concept_pr/README.md").read_text(encoding="utf-8")
    assert "jlens-pr-v3" in readme and 'jlens-pr-v2",' not in readme
    assert "| jlens_concept_pr | claude-opus-5-5 | jlens-pr-v3+fw-v2+sense-v1 " in (
        ROOT / "README.md"
    ).read_text(encoding="utf-8")


def test_stage_prompts_use_readout_phrase() -> None:
    from wsbench import mc

    assert mc.READOUT_PHRASE in pp.STAGE_A_SYSTEM
    assert '"camera shutter speed" is in for "shutter"' in pp.STAGE_P_SYSTEM
    assert "objective lens" not in pp.STAGE_P_SYSTEM
    # the bare v2 Stage-B body the judge never sends is tool-free too
    assert "lens" not in pp._STAGE_B_USER_NO_SET.lower()


def test_stage_b_shows_the_token_set() -> None:
    body = pp.render_stage_b(" bank", ["bank account"], [" bank", " river", " shore"])
    assert (
        body
        == "Token: ' bank'\nToken set: ' bank', ' river', ' shore'\n\nConcepts:\n1. bank account"
    )


def test_cell_text_is_shared_bulleted_join(tmp_path, fake_llm, jargs):
    from conftest import write_sidecar

    rows = [json.loads(line) for line in EXAMPLE.read_text().splitlines()][:1]
    rows[0]["samples"] = ["a metaphor", "", "- figure of speech"]
    src = write_jsonl(tmp_path / "r.jsonl", rows)

    def stage_a_bodies(extra: dict, out: str) -> list[str]:
        fake = fake_llm(_responder)
        jj.run(jargs(src, items=[rows[0]["id"]], extra=extra, out=tmp_path / out))
        return [kw["messages"][1]["content"] for kw in _stage_calls(fake)["A"]]

    # bullet4 (override): every non-empty sample, the shared "- " join (no "---" separator)
    assert stage_a_bodies({"sampling": "bullet4"}, "o1") == [
        "Text:\n- a metaphor\n- figure of speech"
    ]
    write_sidecar(src, reads="full", sampling="prose1")
    assert stage_a_bodies({}, "o2") == ["Text:\n- a metaphor"]  # prose1: one sample per cell


def test_lite_judges_same_cells_as_full(tmp_path, fake_llm, jargs):
    from conftest import write_sidecar

    src = write_jsonl(
        tmp_path / "r.jsonl", [json.loads(x) for x in EXAMPLE.read_text().splitlines()]
    )
    write_sidecar(src, reads="full", sampling="prose1")
    fake_llm(_responder)
    full = jj.run(jargs(src, items=LABELS, out=tmp_path / "full"))
    fake_llm(_responder)
    lite = jj.run(jargs(src, items=LABELS, extra={"reads": "lite"}, out=tmp_path / "lite"))
    assert [r["key"] for r in full.rows] == [r["key"] for r in lite.rows]
    assert full.value == lite.value
    assert full.config["prompt_version"] == "jlens-pr-v3+fw-v2+sense-v1"
    assert lite.config["prompt_version"] == "jlens-pr-v3+fw-v2+sense-v1+reads-lite"


def test_file_layers_without_reference_are_dropped(tmp_path, fake_llm, jargs, capsys):
    pos = jj.manifest_items(jj.load_manifest())[0]["pos"]
    rows = [
        {"id": "chat-lmsys-0000", "layer": layer, "pos": pos, "samples": ["a metaphor"]}
        for layer in (44, 99)
    ]
    fake_llm(_responder)
    res = jj.run(jargs(write_jsonl(tmp_path / "r.jsonl", rows), items=["chat-lmsys-0000"]))
    assert res.config["layers_judged"] == [44]
    assert res.extras["layers_without_reference"] == [99]
    assert set(res.extras["by_layer"]) == {"44"} and {r["layer"] for r in res.rows} == {44}
    assert "WARNING" in capsys.readouterr().out


def test_all_layer_producer_file_is_judged(tmp_path, fake_llm, jargs):
    """Critique fix (1): a sidecar-declared 64-layer producer file (plan_sha over the plan, layers
    not hashed) is judged at the layers that have a reference, the rest listed, no exit."""
    from conftest import write_sidecar

    from wsbench import reads

    items = {it["id"]: it["pos"] for it in jj.manifest_items(jj.load_manifest())}
    labels = LABELS[1:]
    rows = [
        {"id": lab, "layer": layer, "pos": items[lab], "samples": ["a metaphor"]}
        for lab in labels
        for layer in range(64)
    ]
    src = write_jsonl(tmp_path / "r.jsonl", rows)
    write_sidecar(src, reads="full", sampling="prose1", plan_sha=reads.plan_sha(jj.FAMILY))
    fake_llm(_responder)
    res = jj.run(jargs(src, items=labels, allow_missing=False))
    judged = sorted([*range(20, 61, 4), 42])
    assert res.config["layers_judged"] == judged
    assert res.extras["layers_without_reference"] == [L for L in range(64) if L not in judged]
    assert res.config["reads_checked"] == "sidecar" and res.counts["n_missing_cells"] == 0
    assert res.extras["headline_layer"] == 44 and res.value == pytest.approx(0.5)


def test_headline_layer_opt(tmp_path, fake_llm, jargs):
    fake_llm(_responder)
    res = jj.run(jargs(EXAMPLE, items=LABELS, extra={"headline_layer": "48"}))
    assert res.extras["headline_layer"] == 48
    assert res.value == res.extras["by_layer"]["48"]["precision"] == 0.0
    with pytest.raises(SystemExit) as e:
        jj.run(jargs(EXAMPLE, items=LABELS, extra={"headline_layer": "52"}))
    assert e.value.code == 2


def test_layers_each_equals_by_layer(tmp_path, fake_llm, jargs):
    """A single-layer run (the layers=each sub-run) is the all-layer run's by_layer entry, on the
    same call keys (each (label, layer) cell is judged on its own)."""
    fake_llm(_responder)
    all_args = jargs(EXAMPLE, items=LABELS, out=tmp_path / "all")
    full = jj.run(all_args)
    fake_llm(_responder)
    one_args = jargs(EXAMPLE, items=LABELS, layers=[44], out=tmp_path / "L44")
    one = jj.run(one_args)
    b = full.extras["by_layer"]["44"]
    assert one.value == b["precision"]
    assert one.extras["recall_at_10"] == b["recall_at_10"]
    assert one.extras["foil"]["precision"] == b["foil_precision"]

    def keys(out: Path, tag: str) -> set[str]:
        lines = (out / "cells.jsonl").read_text().splitlines()
        return {k for k in (json.loads(x)["key"] for x in lines) if tag in k}

    assert keys(tmp_path / "L44", "") == keys(tmp_path / "all", "__L044__")


def test_verdict_rows_carry_audit_fields(tmp_path, fake_llm, jargs):
    fake_llm(_responder)
    args = jargs(EXAMPLE, items=LABELS)
    jj.run(args)
    rows = ss.verdict_rows(args.out)
    assert {r["kind"] for r in rows} == {"P", "B", "Q"}
    for r in rows:
        assert r["pass"] == (r["grade"] != "out")
        assert r["is_foil"] == (r["kind"] == "Q")
        assert {"key", "label", "layer", "pos", "concept", "tokens", "grade", "token"} <= set(r)
        if r["kind"] in ("P", "Q") and r["pass"]:
            assert r["token"] and pp._tok_norm(r["token"]) in {pp._tok_norm(t) for t in r["tokens"]}
    assert sum(r["kind"] == "P" for r in rows) == 9  # 3 cells x 3 concepts
    assert sum(r["kind"] == "B" for r in rows) == 90  # 3 cells x 10 tokens x 3 concepts


def test_jlens_pr_stays_native_under_summary(tmp_path, fake_llm):
    from types import SimpleNamespace

    from wsbench import digest, runner

    fake = fake_llm(_responder)
    opts = SimpleNamespace(
        items=LABELS,
        layers=None,
        limit=0,
        allow_missing=True,
        concurrency=4,
        rpm=1e9,
        dry_run=False,
        anti_text_inversion=False,
    )
    r = runner.judge_family(
        SPEC,
        opts,  # type: ignore[arg-type]
        EXAMPLE,
        tmp_path / "o",
        judge=resolve(SPEC.judge, env={}),
        opts={"aggregate": "summary"},
    )
    assert r.config["aggregate"] == "native"
    assert r.extras["summary_mode_note"] == digest.NATIVE_ONLY["jlens_concept_pr"]
    stage_systems = {pp.STAGE_A_SYSTEM, pp.STAGE_B_SYSTEM, pp.STAGE_P_SYSTEM}
    assert all(s in stage_systems or u.startswith("Return") for s, u in fake.calls)


def test_jlens_arm_root_without_family_file_is_skipped(tmp_path):
    """C12: the jlens (tokens10) arm writes no jlens_concept_pr.jsonl (the J-lens is the
    reference), so `run all=True` over that root skips the family instead of failing it."""
    from types import SimpleNamespace

    from wsbench import runner

    root = tmp_path / "readouts"
    root.mkdir()
    args = SimpleNamespace(
        opt=[], judge_model=None, family_workers=1, dry_run=True, anti_text_inversion=False
    )
    outcomes, code = runner.run_families(
        [SPEC],
        args,  # type: ignore[arg-type]
        readouts_root=root,
        out=tmp_path / "out",
        env={},
    )
    assert code == 0 and [o.status for o in outcomes] == ["skipped"]


def test_sidecar_tokens_sampling_is_refused(tmp_path, monkeypatch, jargs):
    from conftest import write_sidecar

    monkeypatch.setattr("wsbench.llm._make_client", lambda r, k: pytest.fail("no client"))
    src = write_jsonl(
        tmp_path / "r.jsonl", [json.loads(x) for x in EXAMPLE.read_text().splitlines()]
    )
    write_sidecar(src, reads="full", sampling="tokens10")
    with pytest.raises(SystemExit) as e:
        jj.run(jargs(src, items=LABELS))
    assert e.value.code == 2


def test_jlens_pr_out_of_macro_by_metric() -> None:
    from wsbench.results import FamilyResult, macro

    r = FamilyResult(
        family="jlens_concept_pr",
        metric="precision",
        value=0.3,
        ci95=None,
        n_items=299,
        higher_is_better=True,
        chance=None,
        chance_label=ss.CHANCE_LABEL,
        complete=True,
        pinned_instrument=True,
        config={"judge_model": SPEC.judge.model},
        counts={},
    )
    m = macro([r], superseded={}, held_out={}, removed={})
    assert m["excluded"] == [{"family": "jlens_concept_pr", "reason": "metric"}]
    assert SPEC.not_in_macro == ""


def make_adapted_bank(tmp: Path, layers: list[int]) -> Path:
    """``WSB_BANK_ROOT`` with a 2-label ``jlens_concept_pr`` bank whose reference files exist at
    exactly ``layers`` (plan 0042 C3: arbitrary layers need a reference at each)."""
    d = tmp / "bank_root" / "jlens_concept_pr"
    labels = [("chat-a", 5), ("chat-b", 7)]
    man = {
        "layers": layers,
        "prompts": [
            {"label": lab, "family": "chat", "n_pos": 20, "eval_positions": [pos]}
            for lab, pos in labels
        ],
    }
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(man))
    for lab, pos in labels:
        ref = d / "gen-jlens-pr-jlens" / lab
        ref.mkdir(parents=True)
        for layer in layers:
            row = {"pos": pos, "samples": [" metaphor", " figure", " speech"], "scores": []}
            (ref / f"L{layer:03d}.jsonl").write_text(json.dumps(row) + "\n")
    return d.parent


def test_arbitrary_layers_with_adapted_reference(tmp_path, monkeypatch, fake_llm, jargs):
    from wsbench import registry

    layers = [3, 17, 44]
    root = make_adapted_bank(tmp_path, layers)
    monkeypatch.setenv(registry.BANK_ROOT_ENV, str(root))
    rows = [
        {"id": lab, "layer": layer, "pos": pos, "samples": ["a metaphor"]}
        for lab, pos in (("chat-a", 5), ("chat-b", 7))
        for layer in layers
    ]
    fake_llm(_responder)
    res = jj.run(jargs(write_jsonl(tmp_path / "r.jsonl", rows), layers=layers))
    assert res.config["layers_judged"] == layers
    assert set(res.extras["by_layer"]) == {"3", "17", "44"} and res.extras["headline_layer"] == 44

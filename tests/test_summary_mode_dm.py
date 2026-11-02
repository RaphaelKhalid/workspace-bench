"""Summary mode (plan 0020) on directed_modulation, its obscure variant and the multi-concept
family: one judged (or regex-scored) unit per item on the digest, native counts, the gates."""

import json
import re
from pathlib import Path

import pytest
from summary_fakes import FakeLLM, digest_lines, n_item_layers, summary_args

from wsbench import digest, reads, registry
from wsbench.banks import load_bank
from wsbench.evals import directed_modulation as dm_pkg
from wsbench.evals import model_specific_directed_modulation as dmo_pkg
from wsbench.evals import multi_concept_directed_modulation as mcdm_pkg
from wsbench.evals.directed_modulation import judge as dm_judge
from wsbench.evals.directed_modulation import prompts as dm_prompts
from wsbench.evals.model_specific_directed_modulation import judge as dmo_judge
from wsbench.evals.model_specific_directed_modulation import prompts as dmo_prompts
from wsbench.evals.multi_concept_directed_modulation import prompts as mcdm_prompts
from wsbench.evals.multi_concept_directed_modulation.options import option_sets
from wsbench.registry import bank_path

REPO = Path(__file__).resolve().parents[1]
DM_EX = REPO / "examples/readouts/directed_modulation.jsonl"
# The pinned toy items were retired from the live bank by the ATI panel refill (plan 0019); these
# tests run on byte copies of the pre-refill bank and example readouts (tests/fixtures).
DMO_FIXTURE = REPO / "tests/fixtures/directed_modulation_obscure_pre_refill_items.json"
DMO_EX = REPO / "tests/fixtures/directed_modulation_obscure_pre_refill_readouts.jsonl"
MCDM_EX = REPO / "examples/readouts/multi_concept_directed_modulation.jsonl"
DM_IDS = ["dm-pair-00-pos", "dm-pair-00-neg", "dm-secret-00"]
DMO_IDS = ["middle_eastern_spice_blend", "trickster_figure"]
MCDM_IDS = ["d-plumber", "b-ange-mix-ab", "d-none"]


@pytest.fixture(autouse=True)
def _dmo_pre_refill_bank(monkeypatch):
    monkeypatch.setenv("WSB_BANK_FILE_MODEL_SPECIFIC_DIRECTED_MODULATION", str(DMO_FIXTURE))


def _drop_rows(src: Path, dst: Path, pred) -> Path:
    rows = [json.loads(x) for x in src.read_text().splitlines()]
    dst.write_text("\n".join(json.dumps(r) for r in rows if not pred(r)))
    return dst


def _readout(user: str, open_: str, close: str) -> str:
    return user.split(open_, 1)[1].split(close, 1)[0]


# ---------------------------------------------------------------- directed_modulation


def _dm_options() -> dict[str, tuple[list[str], int]]:
    _h, bank = load_bank(bank_path("directed_modulation"))
    return dm_judge.option_sets(bank)


def _dm_reply(choice: int, basis: str = "absent", evidence: str = "") -> dict:
    return {
        "choice": choice,
        "form": "exact" if evidence else "none",
        "basis": basis,
        "composition": "full" if evidence else "none",
        "domain_overlap": [False] * 5,
        "evidence": evidence,
        "rationale": "",
    }


def _dm_judge(system: str, user: str, schema: dict) -> dict:
    assert system == dm_prompts.SYSTEM and "single token position" not in user
    assert digest.SUMMARY_NOTE in user and "STATEMENT" not in user
    lens = _readout(user, "<readout>\n", "\n</readout>")
    if "collarbone" in lens:  # the think twin: content
        return _dm_reply(4, "content_bound", "clavicle")
    if "must not" in lens:  # the don't-think twin: narration only
        return _dm_reply(4, "instruction_narration", "clavicle")
    if "zephyr" in lens:  # a quote of the note-taker's words fails the evidence gate
        return _dm_reply(5, "content_bound", "STATEMENT-1")
    return _dm_reply(6)


def test_dm_one_call_per_item_and_gate(tmp_path, monkeypatch):
    registry.FAMILIES.setdefault(dm_pkg.SPEC.name, dm_pkg.SPEC)
    fake = FakeLLM.install(monkeypatch, _dm_judge)
    pv = dm_prompts.PROMPT_VERSION
    r = dm_pkg.SPEC.run(summary_args(DM_EX, tmp_path / "s", pv, items=DM_IDS))
    # audit F1: one digest per item and read layer
    assert fake.n("digest") == n_item_layers(DM_EX, DM_IDS) and fake.n("dm_concept") == 3
    assert all(digest_lines(u) for n, _s, u in fake.calls if n == "dm_concept")
    rows = {v["item"]: v for v in r.rows}
    assert len(r.rows) == 3 and {v["layer"] for v in r.rows} == {digest.SUMMARY_LAYER}
    assert rows["dm-pair-00-pos"]["pick"] == "gold" and rows["dm-pair-00-pos"]["summary"]
    assert rows["dm-secret-00"]["voided"] and rows["dm-secret-00"]["evidence_verified"] is False
    # plan 0028: the narration-only twin counts toward the headline (present)
    assert r.value == 2 / 3 and r.extras["n_calls"] == 3
    s = r.extras["summary"]
    assert "pass_at_1" not in s and s["n_items_summarized"] == 3
    assert s["white_bear"] == {
        "n_pairs": 1,
        "think_rate": 1.0,
        "dont_think_rate": 0.0,
        "delta": 1.0,
    }
    assert r.config["aggregate"] == "summary" and r.config["kind"] == "prose"
    assert r.config["prompt_version"] == reads.stamp(
        digest.prompt_version(pv, summary_args(DM_EX, tmp_path, pv), "directed_modulation"),
        "full",
    )
    assert r.config["prompt_version"].startswith(pv + "+digest-v5-task-extractive+sj-v10")
    # native: the same cell counts
    FakeLLM.install(monkeypatch, lambda s_, u, sc: _dm_reply(6))
    n = dm_pkg.SPEC.run(
        summary_args(DM_EX, tmp_path / "n", pv, items=DM_IDS, extra={"aggregate": "native"})
    )
    for k in ("n_expected_cells", "n_missing_cells"):
        assert r.counts[k] == n.counts[k]
    assert "aggregate" not in n.config and "pass_at_1" in n.extras["summary"]


def test_dm_missing_layer_and_unsummarized(tmp_path, monkeypatch):
    registry.FAMILIES.setdefault(dm_pkg.SPEC.name, dm_pkg.SPEC)
    pv = dm_prompts.PROMPT_VERSION
    path = _drop_rows(
        DM_EX, tmp_path / "r.jsonl", lambda x: x["id"] == "dm-secret-00" and x["layer"] == 36
    )
    FakeLLM.install(monkeypatch, lambda s, u, sc: _dm_reply(6))
    r = dm_pkg.SPEC.run(summary_args(path, tmp_path / "o", pv, items=DM_IDS, allow_missing=True))
    # the secret item (a layer missing, no positive) is undecided; the other two are fails
    assert r.extras["n_items_undecided"] == 1 and r.value == 0.0
    assert r.counts["n_missing_cells"] == 1
    # every digest fails: every item is an unjudged row, undecided, no judge call
    fake = FakeLLM.install(monkeypatch, lambda s, u, sc: _dm_reply(6), digest=lambda u: None)
    r = dm_pkg.SPEC.run(summary_args(DM_EX, tmp_path / "u", pv, items=DM_IDS))
    assert fake.n("dm_concept") == 0 and r.value is None
    assert r.counts["n_unjudged_cells"] == 3 and not r.complete
    assert all(v["summary_state"] == "unsummarized" and not v["judged"] for v in r.rows)


# ------------------------------------------------- model_specific_directed_modulation


def _keyword_digest(words: list[str]):
    def fake(user: str) -> dict:
        lines = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
        hits = [ln for ln in lines if any(w in ln for w in words)]
        # no hit: a statement naming baharat / Loki over a NEUTRAL evidence line (audit F1: the
        # per-layer bundle of a layer whose lines all name a concept reports nothing instead)
        neutral = [
            ln for ln in lines if ln in ("A contract on the desk.", "The renewal was approved.")
        ]
        return {
            "items": [{"statement": "STATEMENT", "where": "", "evidence": ln} for ln in hits]
            or [{"statement": "baharat Loki", "where": "", "evidence": ln} for ln in neutral[:1]]
        }

    return fake


def test_dmo_one_regex_per_item_no_judge(tmp_path, monkeypatch):
    registry.FAMILIES.setdefault(dmo_pkg.SPEC.name, dmo_pkg.SPEC)
    fake = FakeLLM.install(
        monkeypatch,
        lambda s, u, sc: (_ for _ in ()).throw(AssertionError("no judge call")),
        digest=_keyword_digest(["baharat", "Zaatar"]),
    )
    n_scored: list[int] = []
    real = dmo_judge.cell_hits
    monkeypatch.setattr(dmo_judge, "cell_hits", lambda s, m: n_scored.append(1) or real(s, m))
    pv = dmo_prompts.PROMPT_VERSION
    r = dmo_pkg.SPEC.run(summary_args(DMO_EX, tmp_path / "s", pv, items=DMO_IDS))
    # one digest per item and read layer (audit F1), nothing more
    assert [c[0] for c in fake.calls] == ["digest"] * n_item_layers(DMO_EX, DMO_IDS)
    assert len(n_scored) == 2
    rows = {x["id"]: x for x in r.rows}
    spice, trick = rows["middle_eastern_spice_blend"], rows["trickster_figure"]
    assert spice["pass"] is True and spice["distractor_rate"] == 0.5
    # the statement names baharat / Loki, but its evidence line does not: never scored
    assert trick["pass"] is False and trick["distractor_rate"] == 0.0
    assert "layer_any_hit" not in spice and "per_layer" not in r.extras
    assert r.extras["distractor_rate"] == 0.25 and r.extras["summary"]["n_items_summarized"] == 2
    assert r.config["judge_model"] == digest.DEFAULT_MODEL and r.pinned_instrument
    # plan 0034 G8: the summary gate joins token lines, stamped +joined (native unchanged)
    assert r.config["aggregate"] == "summary" and r.config["scorer_version"].startswith(
        dmo_prompts.SUMMARY_PROMPT_VERSION + "+digest-v5-task-extractive"
    )
    n = dmo_pkg.SPEC.run(
        summary_args(DMO_EX, tmp_path / "n", pv, items=DMO_IDS, extra={"aggregate": "native"})
    )
    for k in ("n_expected_cells", "n_missing_cells"):
        assert r.counts[k] == n.counts[k]
    assert n.config["judge_model"] == "regex"
    o = dmo_pkg.SPEC.run(
        summary_args(DMO_EX, tmp_path / "o", pv, items=DMO_IDS, extra={"summ_model": "x"})
    )
    assert not o.pinned_instrument


def test_dmo_missing_layer_and_unsummarized(tmp_path, monkeypatch):
    registry.FAMILIES.setdefault(dmo_pkg.SPEC.name, dmo_pkg.SPEC)
    pv = dmo_prompts.PROMPT_VERSION
    path = _drop_rows(
        DMO_EX, tmp_path / "r.jsonl", lambda x: x["id"] == "trickster_figure" and x["layer"] == 60
    )
    FakeLLM.install(monkeypatch, lambda s, u, sc: None, digest=_keyword_digest(["baharat"]))
    r = dmo_pkg.SPEC.run(summary_args(path, tmp_path / "m", pv, items=DMO_IDS, allow_missing=True))
    by = {x["id"]: x["pass"] for x in r.rows}
    assert by == {"middle_eastern_spice_blend": True, "trickster_figure": None}
    FakeLLM.install(monkeypatch, lambda s, u, sc: None, digest=lambda u: None)
    r = dmo_pkg.SPEC.run(summary_args(DMO_EX, tmp_path / "u", pv, items=DMO_IDS))
    assert all(x["pass"] is None for x in r.rows) and r.value is None
    assert r.counts["n_unjudged_cells"] == 2 and not r.complete


# ---------------------------------------------------------------- multi_concept_directed_modulation

_LETTER_LINE = re.compile(r"^([A-F])\. (.*)$", re.M)


def _mcdm_judge(system: str, user: str, schema: dict) -> dict:
    assert digest.SUMMARY_NOTE in user and "STATEMENT" not in user
    _h, items = load_bank(bank_path("multi_concept_directed_modulation"))
    opts = option_sets(items)
    shown = [o for _l, o in _LETTER_LINE.findall(user)]
    item = next(i for i, (o, _g) in opts.items() if o == shown)
    lines = digest_lines(user)
    quote = re.sub(r"^\[[^\]]*\] ", "", lines[0])[:12]  # minus the support marker
    _o, gold = opts[item]
    cb = "content_bound"  # plan 0025: every pick carries a basis
    if item == "d-plumber":
        return {"picks": [{"choice": "ABCDEF"[g], "quote": quote, "basis": cb} for g in gold]}
    if item == "d-none":
        return {"picks": [{"choice": "A", "quote": quote, "basis": cb}]}
    return {  # gate rejects
        "picks": [{"choice": "ABCDEF"[gold[0]], "quote": "STATEMENT-0", "basis": cb}]
    }


def test_mcdm_one_call_per_item_controls_included(tmp_path, monkeypatch):
    registry.FAMILIES.setdefault(mcdm_pkg.SPEC.name, mcdm_pkg.SPEC)
    fake = FakeLLM.install(monkeypatch, _mcdm_judge)
    pv = mcdm_prompts.PROMPT_VERSION
    r = mcdm_pkg.SPEC.run(summary_args(MCDM_EX, tmp_path / "s", pv, items=MCDM_IDS))
    assert fake.n("digest") == n_item_layers(MCDM_EX, MCDM_IDS)  # audit F1: per item and layer
    assert fake.n("picks") == 3 and r.extras["n_calls"] == 3
    rows = {x["id"]: x for x in r.rows}
    assert rows["d-plumber"]["pass"] is True and rows["d-plumber"]["capacity"] is None
    assert len(rows["d-plumber"]["concepts_surfaced"]) == 3
    assert rows["b-ange-mix-ab"]["pass"] is False  # the STATEMENT quote is in no evidence sample
    assert rows["d-none"]["reason"] == "control" and rows["d-none"]["summary"]
    assert r.extras["control_pick_rate"] == 1.0 and "capacity" not in r.extras
    assert all(c["layer"] == digest.SUMMARY_LAYER for x in r.rows for c in x["cells"])
    assert r.config["aggregate"] == "summary" and r.config["source_kind"] == "prose"
    assert r.config["prompt_version"].startswith(pv + "+digest-v5-task-extractive+sj-v10")
    FakeLLM.install(monkeypatch, lambda s, u, sc: {"picks": []})
    n = mcdm_pkg.SPEC.run(
        summary_args(MCDM_EX, tmp_path / "n", pv, items=MCDM_IDS, extra={"aggregate": "native"})
    )
    for k in ("n_expected_cells", "n_missing_cells"):
        assert r.counts[k] == n.counts[k]


def test_mcdm_missing_cell_and_unsummarized(tmp_path, monkeypatch):
    registry.FAMILIES.setdefault(mcdm_pkg.SPEC.name, mcdm_pkg.SPEC)
    pv = mcdm_prompts.PROMPT_VERSION
    path = _drop_rows(
        MCDM_EX,
        tmp_path / "r.jsonl",
        lambda x: x["id"] == "d-plumber" and x["layer"] == 44 and x["pos"] == -5,
    )
    FakeLLM.install(monkeypatch, lambda s, u, sc: {"picks": []})
    r = mcdm_pkg.SPEC.run(
        summary_args(path, tmp_path / "m", pv, items=MCDM_IDS, allow_missing=True)
    )
    rows = {x["id"]: x for x in r.rows}
    assert rows["d-plumber"]["pass"] is None and rows["d-plumber"]["reason"] == "unjudged"
    assert rows["b-ange-mix-ab"]["pass"] is False and r.counts["n_missing_cells"] == 1
    fake = FakeLLM.install(monkeypatch, lambda s, u, sc: {"picks": []}, digest=lambda u: None)
    r = mcdm_pkg.SPEC.run(summary_args(MCDM_EX, tmp_path / "u", pv, items=MCDM_IDS))
    assert fake.n("picks") == 0 and r.counts["n_unjudged_cells"] == 3
    rows = {x["id"]: x for x in r.rows}
    assert rows["d-plumber"]["pass"] is None and rows["d-plumber"]["reason"] == "unjudged"
    assert rows["d-none"]["summary_state"] == "unsummarized" and not r.complete


def test_mcdm_summary_needs_every_concept_in_the_one_call(tmp_path, monkeypatch):
    """Plan 0025 §1: in summary mode the one judge call per item must credit EVERY dictated
    concept; d-plumber with two of its three concepts credited fails."""
    registry.FAMILIES.setdefault(mcdm_pkg.SPEC.name, mcdm_pkg.SPEC)

    def partial(system: str, user: str, schema: dict) -> dict:
        out = _mcdm_judge(system, user, schema)
        if len(out.get("picks", [])) == 3:  # d-plumber: drop one of its three concepts
            out = {"picks": out["picks"][:2]}
        return out

    FakeLLM.install(monkeypatch, partial)
    pv = mcdm_prompts.PROMPT_VERSION
    r = mcdm_pkg.SPEC.run(summary_args(MCDM_EX, tmp_path / "p", pv, items=MCDM_IDS))
    rows = {x["id"]: x for x in r.rows}
    assert rows["d-plumber"]["pass"] is False and rows["d-plumber"]["any_concept"] is True
    assert rows["d-plumber"]["concept_recall"] == pytest.approx(2 / 3)

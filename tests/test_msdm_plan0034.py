"""model_specific_directed_modulation, plan 0034 (Camila's "Directed modulation obscure" section,
O1-O3, and G8): the rename, the control arms, the derangement null, the joined summary gate, the
lite read and the unchanged scorer."""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from summary_fakes import FakeLLM, n_item_layers, summary_args

from wsbench import digest, readplan, reads, registry
from wsbench.baselines import text_inversion as ti
from wsbench.evals import model_specific_directed_modulation as pkg
from wsbench.evals.model_specific_directed_modulation import controls, judge, prompts

REPO = Path(__file__).resolve().parents[1]
NAME = "model_specific_directed_modulation"
README = REPO / "evals" / NAME / "README.md"
BANK = REPO / "evals" / NAME / "items.json"
FIXTURE_BANK = REPO / "tests/fixtures/directed_modulation_obscure_pre_refill_items.json"
FIXTURE_HITS = REPO / "tests/fixtures/directed_modulation_obscure_pre_refill_hits.json"
FIXTURE_READOUTS = REPO / "tests/fixtures/directed_modulation_obscure_pre_refill_readouts.jsonl"


@pytest.fixture(autouse=True)
def _registered(real_families):
    return real_families


# ---------------------------------------------------------------- O1 rename


def test_both_old_names_resolve_and_ati_entry_valid():
    for old in ("dm_category_default", "directed_modulation_obscure"):
        assert registry.canonical(old) == NAME
    assert sorted(registry.legacy_names(NAME)) == [
        "directed_modulation_obscure",
        "dm_category_default",
    ]
    spec = registry.get(NAME)
    assert spec.title == "Model-specific directed modulation" and spec.group == "model_specific"
    assert NAME in ti.CRAFTED
    entry = ti.subset_entry(NAME)
    assert len(entry["ids"]) == 98 and entry["bank_sha"] == ti.bank_fingerprint(NAME)
    assert ti.subset_entry("directed_modulation_obscure") == entry
    # step 1 of the restamp: under the OLD name the fingerprint is the frozen pre-rename value
    sys.path.insert(0, str(REPO / "scripts"))
    from ati_restamp_rename import fingerprint_as

    assert fingerprint_as(NAME, "directed_modulation_obscure") == entry["renamed_from"]["bank_sha"]
    assert entry["renamed_from"]["bank_sha"].startswith("9f5370f0b33c")
    frozen = json.loads(ti.FROZEN.read_text("utf-8"))
    assert "directed_modulation_obscure" not in frozen and "dm_category_default" not in frozen


def test_bank_byte_identical_after_the_move():
    header = json.loads(BANK.read_text("utf-8"))
    assert header["family"] == "dm_category_default" and len(header["items"]) == 98
    assert hashlib.sha256(BANK.read_bytes()).hexdigest().startswith("b905301248d3")


# ---------------------------------------------------------------- O2 every arm, new items


def test_dmo_readme_numbers_are_current_bank():
    text = README.read_text("utf-8")
    sec = text.split("## Numbers on the current 98-item bank", 1)[1].split("\n## ", 1)[0]
    sha = hashlib.sha256(BANK.read_bytes()).hexdigest()[:12]
    assert f"sha256 `{sha}`" in sec and "n = 98" in sec
    rows = [ln for ln in sec.splitlines() if ln.startswith("| ") and not ln.startswith("| arm")]
    rows = [r for r in rows if not set(r) <= set("|- ")]
    arms = [
        # round 3 (ROUND3_TODO L180): the campaign's final O-lens rows replace "pending"
        "final O-lens `final-olens-rl600-x4`, all 11 layers",
        "final O-lens, lite",
        "O-lens s3d-rl600",
        "J-lens top-10",
        "ML-NLA",
        "rl-onchat-x4",
        "no-think control",
        "Alice control",
        "prompt-only floor",
        "ATI panel text floor",
    ]
    assert len(rows) == len(arms)
    for arm, row in zip(arms, rows, strict=True):
        assert arm in row, (arm, row)
        assert "| 98 |" in row, row
    assert "## Pre-refill source numbers" in text  # the dated old table is kept


def test_dmo_control_arm_rows_differ_only_in_prompt():
    plan = {s.id: s for s in readplan.plan(NAME)}
    for arm in controls.ARMS:
        rows = controls.control_rows(arm)
        assert [r.id for r in rows] == list(plan)
        for r in rows:
            p = plan[r.id]
            a, b = r.row(), p.row()
            assert {k: v for k, v in a.items() if k != "text"} == {
                k: v for k, v in b.items() if k != "text"
            }
            assert a["text"] != b["text"] and a["text"].endswith(b["text"].split(" Now ", 1)[1])
            if arm == "nothink":
                assert "Think about" not in a["text"]
            else:
                assert "Alice's" in a["text"] and "your" not in a["text"].split(" Now ")[0]


@pytest.mark.parametrize("arm", controls.ARMS)
def test_dmo_control_plan_file_matches_rows(arm, tmp_path):
    out = tmp_path / f"plan-dmo-{arm}"
    r = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/dmo_control_plan.py"),
            "--arm",
            arm,
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert r.returncode == 0, r.stderr
    got = [json.loads(x) for x in (out / f"{NAME}.jsonl").read_text("utf-8").splitlines()]
    want = [s.row() for s in controls.control_rows(arm)]
    assert got == want
    assert reads.plan_sha_rows(got) != reads.plan_sha(NAME)  # a full-sidecar merge is refused


def test_derangement_has_no_fixed_point_and_is_seeded():
    ids = [f"i{k}" for k in range(98)]
    perm = judge.derangement(ids)
    assert sorted(perm) == sorted(ids) and sorted(perm.values()) == sorted(ids)
    assert all(k != v for k, v in perm.items())
    assert perm == judge.derangement(ids) and judge.derangement(["a"]) == {}


def test_dmo_derangement_null_is_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("WSB_BANK_FILE_MODEL_SPECIFIC_DIRECTED_MODULATION", str(FIXTURE_BANK))
    ids = ["middle_eastern_spice_blend", "trickster_figure"]
    fake = FakeLLM.install(
        monkeypatch, lambda s, u, sc: (_ for _ in ()).throw(AssertionError("no judge call"))
    )
    r = pkg.SPEC.run(
        summary_args(FIXTURE_READOUTS, tmp_path / "s", prompts.PROMPT_VERSION, items=ids)
    )
    # one digest per item and read layer (audit F1), nothing more
    assert [c[0] for c in fake.calls] == ["digest"] * n_item_layers(FIXTURE_READOUTS, ids)
    assert r.extras["derangement_n"] == 2 and r.extras["derangement_rate"] is not None
    n = pkg.SPEC.run(
        summary_args(
            FIXTURE_READOUTS,
            tmp_path / "n",
            prompts.PROMPT_VERSION,
            items=ids,
            extra={"aggregate": "native"},
        )
    )
    assert len(fake.calls) == n_item_layers(FIXTURE_READOUTS, ids)  # native: no call at all
    perm = judge.derangement(sorted(ids))
    assert all(perm[i] != i for i in ids)
    # native: an item's gold matched against the OTHER item's cells, never its own
    by = {it["id"]: it for it in judge.load_items(FIXTURE_BANK)[1]}
    from wsbench.readouts import load_readouts

    cells, _ = load_readouts(FIXTURE_READOUTS, ids=ids)
    texts = {i: [judge.cell_samples(c) for c in cells if c.id == i] for i in ids}
    assert n.extras["derangement_rate"] == judge.derangement_rate(by, texts)["derangement_rate"]


# ---------------------------------------------------------------- O3 the scorer is unchanged


def test_dmo_scorer_unchanged():
    """Camila: "i think it's perfect". The committed source per-cell hits (hidden arm, 98
    pre-refill items) through this family's pass rule give 0.337 / 0.289, item for item, and the
    two cases a review called "too lenient" stay passes."""
    assert prompts.PROMPT_VERSION == "dmcd-regex-2026-10-23"
    _h, items = judge.load_items(FIXTURE_BANK)
    by = {it["id"]: it for it in items}
    hits = json.loads(FIXTURE_HITS.read_text("utf-8"))["rows"]
    rows = []
    for r in hits:
        h = {
            o: {int(L): [c == "1" for c in bits] for L, bits in per.items()}
            for o, per in r["option_hits"].items()
        }
        rows.append(judge.item_row(by[r["item"]], h, []))
    assert len(rows) == 98
    passed = sorted(r["id"] for r in rows if r["pass"])
    assert len(passed) == 33 and round(33 / 98, 3) == 0.337
    ex = judge.summary_extras(rows)
    assert round(ex["distractor_rate"], 3) == 0.289
    assert round(ex["gold_minus_distractor"], 3) == 0.048
    for case in ("s2_classical_orthogonal_polynomial_family", "s2_peruvian_dessert"):
        assert case in passed
    assert passed[:3] == [
        "s1_amine_protecting_group",
        "s1_augmented_sixth_chord",
        "s1_bordeaux_blending_grape_variety",
    ]
    assert passed[-1] == "trickster_figure"


# ---------------------------------------------------------------- G8


def test_dmo_lite_final_token_and_full_span():
    row = readplan.plan(NAME)[0]
    assert row.lite_positions == {"kind": "final_token"} and row.lite_layers is None
    assert pkg.SPEC.min_full_positions == judge.MIN_CARRIER_TOKENS == 7
    assert pkg.SPEC.full_contiguous is True
    assert pkg.SPEC.task_note == prompts.DIGEST_TASK_NOTE


def test_dmo_summary_gate_joins_token_lines(tmp_path, monkeypatch):
    """A two-word gold hits a token digest line only when the line is also matched joined."""
    monkeypatch.setenv("WSB_BANK_FILE_MODEL_SPECIFIC_DIRECTED_MODULATION", str(FIXTURE_BANK))
    _h, items = judge.load_items(FIXTURE_BANK)
    it = next(x for x in items if any(" " in f for f in x["option_units"][x["gold"]]))
    form = next(f for f in it["option_units"][it["gold"]] if " " in f)
    words = form.split()
    rows = [
        {
            "id": it["id"],
            "layer": L,
            "pos": p,
            "token": "t",
            "tokens": [*words, "zz"] if p == 0 else ["zz"],
        }
        for L in readplan.GRID
        for p in range(7)
    ]
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def dig(user: str) -> dict:
        line = next(ln[2:] for ln in user.splitlines() if ln.startswith("- ") and words[0] in ln)
        return {"items": [{"statement": "s", "key": words[0], "where": "", "evidence": line}]}

    FakeLLM.install(monkeypatch, lambda s, u, sc: None, digest=dig)
    r = pkg.SPEC.run(summary_args(path, tmp_path / "o", prompts.PROMPT_VERSION, items=[it["id"]]))
    assert r.rows[0]["pass"] is True, form
    assert r.config["prompt_version"].startswith(prompts.SUMMARY_PROMPT_VERSION + "+digest-")
    assert r.config["prompt_version"] == digest.prompt_version(
        prompts.SUMMARY_PROMPT_VERSION,
        summary_args(path, tmp_path / "o", prompts.PROMPT_VERSION),
        NAME,
    )
    assert re.search(
        r"\+joined-2026-10-30\+digest-v5-task-extractive\+sj-v10$", r.config["prompt_version"]
    )

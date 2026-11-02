"""Summary mode (plan 0020) on introspection (one call per unit on its readout's shared digest,
controls included) and knowledge_cutoff (one call per item, no bank-layer pick, no ati_pass)."""

import json
import os
import re
from pathlib import Path

import pytest
from conftest import write_sidecar
from summary_fakes import FakeLLM, digest_lines, first_lines_digest, summary_args

from wsbench import digest, registry
from wsbench.evals.introspection import judge as ij
from wsbench.evals.introspection.prompts import PROMPT_VERSION as II_PV
from wsbench.evals.introspection.prompts import REGEX_LEG_VERSION as II_RX
from wsbench.evals.introspection.prompts import SYSTEM as II_SYSTEM
from wsbench.evals.introspection.prompts import SYSTEM_SUMMARY as II_SYSTEM_SUMMARY
from wsbench.evals.knowledge_cutoff import judge as kj
from wsbench.evals.knowledge_cutoff.prompts import LETTERS
from wsbench.evals.knowledge_cutoff.prompts import PROMPT_VERSION as KC_PV
from wsbench.evals.knowledge_cutoff.prompts import SYSTEM as KC_SYSTEM
from wsbench.evals.knowledge_cutoff.prompts import SYSTEM_SUMMARY as KC_SYSTEM_SUMMARY

REPO = Path(__file__).resolve().parents[1]
II_EXAMPLE = REPO / "examples/readouts/introspection.jsonl"
# The pinned toy items were retired from the live bank by the ATI panel refill (plan 0019); these
# tests run on byte copies of the pre-refill bank and example readouts (tests/fixtures).
KC_FIXTURE = REPO / "tests/fixtures/knowledge_cutoff_pre_refill_items.json"
KC_EXAMPLE = REPO / "tests/fixtures/knowledge_cutoff_pre_refill_readouts.jsonl"
HEAD = "inject|protocol:trial1|b4|trumpets"
CROSS = "cross|protocol:trial1|b4|memories"  # reads HEAD's readout
GAUSS = "gaussian|protocol:trial1|b4|trumpets"
B0 = "beta0|protocol:trial1|b0|"
II_ITEMS = [HEAD, CROSS, GAUSS, B0]
KC_ITEMS = json.loads(KC_FIXTURE.read_text("utf-8"))["items"]
A, B = KC_ITEMS[0], KC_ITEMS[1]  # cs00013 (gold "kirin 9100"), cs00017 (gold "64")


@pytest.fixture(autouse=True)
def _kc_pre_refill_bank():
    # set directly (not via monkeypatch): a test below calls monkeypatch.undo() mid-way
    key, old = "WSB_BANK_FILE_KNOWLEDGE_CUTOFF", os.environ.get("WSB_BANK_FILE_KNOWLEDGE_CUTOFF")
    os.environ[key] = str(KC_FIXTURE)
    yield
    if old is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = old


@pytest.fixture(autouse=True)
def _registered():
    from wsbench.evals.introspection import SPEC as II
    from wsbench.evals.knowledge_cutoff import SPEC as KC

    registry.FAMILIES.setdefault(II.name, II)
    registry.FAMILIES.setdefault(KC.name, KC)


def _all_lines(user: str) -> dict:
    return first_lines_digest(user, 50)


def _options(user: str) -> list[str]:
    block = user.split("OPTIONS:\n", 1)[1].split("\n\n", 1)[0]
    return [ln.split(". ", 1)[1] for ln in block.splitlines()]


def _ii_judge(quote_from_statement: bool = False):
    """Pick the first option named in a judged digest line, quoting the matched word."""

    def answer(system: str, user: str, schema: dict) -> dict:
        opts = _options(user)
        none = opts.index(ij.NONE_OPTION) + 1
        lines = digest_lines(user) if system == II_SYSTEM_SUMMARY else user.splitlines()
        for k, lab in enumerate(opts):
            if lab == ij.NONE_OPTION:
                continue
            for form in (lab, ij._singular(lab)):  # quote the form actually written
                if any(re.search(rf"(?<![a-z]){form}(?![a-z])", ln.lower()) for ln in lines):
                    quote = "STATEMENT-0" if quote_from_statement else form
                    return {"choice": k + 1, "quote": quote, "anomaly_noted": False}
        return {"choice": none, "quote": "", "anomaly_noted": False, "anomaly_quote": ""}

    return answer


def _ii_args(tmp_path: Path, readouts: Path = II_EXAMPLE, **kw):
    return summary_args(readouts, tmp_path, II_PV, items=II_ITEMS, allow_missing=True, **kw)


# ---------------------------------------------------------------- introspection


def test_introspection_one_call_per_unit_on_a_shared_digest(tmp_path, monkeypatch):
    fake = FakeLLM.install(monkeypatch, _ii_judge(), digest=_all_lines)
    r = ij.run(_ii_args(tmp_path / "s"))
    n_clusters = len(ij.load()["clusters"])
    # three readouts (HEAD, GAUSS, B0): one digest each; CROSS and the beta0 clusters share
    assert fake.n("digest") == 3
    assert fake.n("introspection_verdict") == 3 + n_clusters  # HEAD, CROSS, GAUSS + beta0 units
    assert all(s == II_SYSTEM_SUMMARY for n, s, _u in fake.calls if n == "introspection_verdict")
    rows = {x["id"]: x for x in r.rows}
    # round 4 (rxhead-v1, sanctioned): the judge's verdicts are the judge_* diagnostic columns;
    # earliest_layer and the per-layer column are the regex headline's (raw cells, real layers)
    assert rows[HEAD]["judge_pass"] is True and rows[HEAD]["hit_cells"] == [[-1, 140]]
    assert rows[HEAD]["summary"] == rows[CROSS]["summary"]  # one summary, two units
    assert rows[CROSS]["judge_pass"] is False and rows[GAUSS]["judge_pass"] is False
    b0 = rows[f"{B0}|music"]  # a control unit is judged on its digest exactly like the others
    assert b0["judge_chance_hits"]["drums"] is True and b0["summary_state"] == "summarized"
    assert r.extras["floors"]["protocol|b4"]["beta0"] is not None
    assert r.config["aggregate"] == "summary" and r.config["source_kind"] == "prose"
    # II_PV carries the regex-leg version (twinrx-v4) and the regex headline's (rxhead-v1); the
    # calls keep CALL_VERSION
    assert II_PV.endswith("+" + II_RX + "+rxhead-v1")
    want = digest.prompt_version(II_PV, _ii_args(tmp_path))
    assert r.config["prompt_version"] == want
    assert r.config["prompt_version"].startswith(f"{II_PV}+digest-v5-task-extractive")
    assert r.extras["summary"]["n_items_summarized"] == 3

    # n_expected / n_missing are the native accounting
    FakeLLM.install(monkeypatch, _ii_judge())
    nat = ij.run(_ii_args(tmp_path / "n", extra={"aggregate": "native"}))
    assert nat.config.get("aggregate") != "summary"
    for k in ("n_expected_cells", "n_missing_cells"):
        assert r.counts[k] == nat.counts[k]
    assert {x["id"] for x in nat.rows} == set(rows)


def test_introspection_quote_only_in_a_statement_fails(tmp_path, monkeypatch):
    FakeLLM.install(monkeypatch, _ii_judge(quote_from_statement=True), digest=_all_lines)
    r = ij.run(_ii_args(tmp_path))
    rows = {x["id"]: x for x in r.rows}
    assert rows[HEAD]["judge_pass"] is False and rows[HEAD]["summary_statements"]
    assert r.extras["audit"]["forced_none"] > 0 and r.extras["audit"]["concept_picks"] == 0


def test_introspection_failed_digest_is_undecided(tmp_path, monkeypatch):
    fake = FakeLLM.install(monkeypatch, _ii_judge(), digest=lambda user: None)
    r = ij.run(_ii_args(tmp_path))
    assert fake.n("introspection_verdict") == 0
    rows = {x["id"]: x for x in r.rows}
    assert rows[HEAD]["judge_pass"] is None and rows[HEAD]["summary_state"] == "unsummarized"
    assert r.extras["judge_n_unjudged"] == len(r.rows) and r.extras["judge_paired"] is None
    # the regex headline reads the raw cells: a failed digest leaves it decided
    assert rows[HEAD]["pass"] is not None and r.counts["n_unjudged_cells"] == 0


def test_introspection_token_source_quotes_one_token(tmp_path, monkeypatch):
    rows = [
        {"id": HEAD, "layer": 56, "pos": 140, "tokens": ["Ġtrumpets", "Ġbrass"], "scores": [1, 0]},
        {"id": GAUSS, "layer": 56, "pos": 140, "tokens": ["Ġtrumpets"], "scores": [1]},
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in rows), "utf-8")

    def answer(system: str, user: str, schema: dict) -> dict:
        assert digest.SUMMARY_NOTE_TOKENS in user and "TOP-10" not in user
        opts = _options(user)
        quote = "trumpets brass" if "trumpets | brass" in user else "trumpets"
        if "trumpets" in opts:
            return {"choice": opts.index("trumpets") + 1, "quote": quote, "anomaly_noted": False}
        return {"choice": opts.index(ij.NONE_OPTION) + 1, "quote": "", "anomaly_noted": False}

    fake = FakeLLM.install(monkeypatch, answer, digest=_all_lines)
    r = ij.run(summary_args(path, tmp_path / "o", II_PV, items=[HEAD, GAUSS], allow_missing=True))
    assert not any(n == "summarize" for n, _s, _u in fake.calls)  # no per-cell token summarizer
    by = {x["id"]: x for x in r.rows}
    assert by[HEAD]["judge_pass_unpaired"] is False  # "trumpets brass" spans two tokens
    assert by[GAUSS]["judge_pass"] is True
    assert r.config["source_kind"] == "tokens"


def test_introspection_paired_rule_in_summary_mode(tmp_path, monkeypatch):
    """Plan 0045: the gaussian twin's regex leg reads the loaded raw cells, not the digest: a
    twin whose digest never shows the target still voids the item when a raw sample names it."""
    rows = [
        {"id": HEAD, "layer": 56, "pos": 140, "samples": ["a fanfare of trumpets"]},
        {"id": GAUSS, "layer": 56, "pos": 140, "samples": ["nothing at all"]},
        {"id": GAUSS, "layer": 60, "pos": 140, "samples": ["a trumpet, faintly"]},
    ]
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in rows), "utf-8")
    # the digest of every readout keeps only its first line: GAUSS's digest is "nothing at all"
    # (audit F1: the per-layer digest of its L60 alone reports nothing)
    FakeLLM.install(
        monkeypatch,
        _ii_judge(),
        digest=lambda u: {"items": []} if "a trumpet" in u else first_lines_digest(u, 1),
    )
    r = ij.run(summary_args(path, tmp_path / "o", II_PV, items=[HEAD], allow_missing=True))
    by = {x["id"]: x for x in r.rows}
    assert by[GAUSS]["judge_pass"] is False  # the twin's judge leg does not fire on its digest
    g = by[HEAD]["twin_hits"]["gaussian"]
    assert g["judge"] is False and g["regex"] is True and g["regex_quote"] == "a trumpet, faintly"
    assert by[HEAD]["pass_unpaired"] is True and by[HEAD]["pass"] is False
    assert r.value == 0.0 and r.extras["headline_unpaired"] == 1.0


def test_introspection_native_prompt_is_unchanged():
    assert II_SYSTEM_SUMMARY != II_SYSTEM and "one internal activation" not in II_SYSTEM_SUMMARY


# ---------------------------------------------------------------- knowledge_cutoff


def _kc_judge(quote: str | None = None):
    """Answer the gold letter of whichever item's menu this is, quoting ``quote`` (default: the
    gold's display form)."""
    golds = {it["id"]: it for it in (A, B)}

    def answer(system: str, user: str, schema: dict) -> dict:
        assert system == KC_SYSTEM_SUMMARY
        menu = user.split("=== OPTIONS ===\n", 1)[1].split("\n\n", 1)[0]
        opts = [ln.split(". ", 1)[1] for ln in menu.splitlines()]
        it = next(x for x in golds.values() if [str(o) for o in x["options"]] == opts)
        q = quote if quote is not None else {"kirin 9100": "Kirin 9100", "64": "64"}[it["gold"]]
        return {"reasoning": "", "answer": LETTERS[opts.index(it["gold"])], "quote": q}

    return answer


def _kc_args(readouts: Path, out: Path, **kw):
    return summary_args(readouts, out, KC_PV, items=[A["id"], B["id"]], **kw)


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "r.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    return p


def test_kc_one_call_per_item_no_layer_pick_no_ati(tmp_path, monkeypatch):
    def no_pick(_hits):
        raise AssertionError("best_layer is a pass@layer: never used in summary mode")

    monkeypatch.setattr(kj, "pick_layer", no_pick)
    fake = FakeLLM.install(monkeypatch, _kc_judge(), digest=_all_lines)
    r = kj.run(_kc_args(KC_EXAMPLE, tmp_path / "s"))
    assert (
        fake.n("digest") == 2 * 2 and fake.n("knowledge_cutoff") == 2
    )  # audit F1: per item and read layer
    rows = {x["id"]: x for x in r.rows}
    assert rows[A["id"]]["pass"] is True  # "Probably the Kirin 9100." is an evidence sample
    assert rows[B["id"]]["pass"] is False  # no sample says 64: the quote does not verify
    for row in rows.values():
        assert row["layer"] == digest.SUMMARY_LAYER
        assert "ati_pass" not in row and "hit_by_layer" not in row
    assert rows[A["id"]]["named_gold_reply_start"] is True
    for k in ("headline_layer", "hits_by_layer", "per_layer_rate", "regex_reply_start_by_layer",
              "ati_pass_rate"):  # fmt: skip
        assert k not in r.extras
    assert r.config["aggregate"] == "summary" and r.config["reads"] == "full"
    assert r.config["prompt_version"] == digest.prompt_version(
        KC_PV, _kc_args(KC_EXAMPLE, tmp_path / "s"), "knowledge_cutoff"
    )
    assert all(s == KC_SYSTEM_SUMMARY for n, s, _u in fake.calls if n == "knowledge_cutoff")
    assert KC_SYSTEM_SUMMARY != KC_SYSTEM

    monkeypatch.undo()
    nat_seen: list = []
    monkeypatch.setattr(
        kj,
        "run_calls",
        lambda calls, **kw: (
            nat_seen.extend(calls)
            or {c.key: {"reasoning": "", "answer": "NONE", "quote": ""} for c in calls}
        ),
    )
    nat = kj.run(_kc_args(KC_EXAMPLE, tmp_path / "n", extra={"aggregate": "native"}))
    assert "ati_pass" in nat.rows[0] and len(nat_seen) == 4
    for k in ("n_expected_cells", "n_missing_cells"):
        assert r.counts[k] == nat.counts[k]


def test_kc_partial_comes_from_the_real_cells(tmp_path, monkeypatch):
    rows = [{"id": it["id"], "layer": 60, "pos": p, "samples": ["x"]} for it in (A, B)
            for p in (-10, -2, -1)]  # fmt: skip
    rows[2]["samples"] = ["The Kirin 9100.", "Kirin 9100"]
    FakeLLM.install(monkeypatch, _kc_judge(), digest=_all_lines)
    # plan 0044: the span check enforces only with a producer sidecar (infra §2.6)
    path = _write(tmp_path, rows)
    write_sidecar(path, reads="full", sampling="bullet4", reader="fixture", layers=[60])
    r = kj.run(_kc_args(path, tmp_path / "o", allow_missing=True))
    assert set(r.extras["partial_ids"]) == {A["id"], B["id"]} and r.extras["n_partial_cells"] == 2
    assert r.complete is False
    assert {x["id"]: x["pass"] for x in r.rows}[A["id"]] is True


def test_kc_quote_only_in_a_statement_fails(tmp_path, monkeypatch):
    FakeLLM.install(monkeypatch, _kc_judge(quote="STATEMENT-0"), digest=_all_lines)
    r = kj.run(_kc_args(KC_EXAMPLE, tmp_path))
    row = {x["id"]: x for x in r.rows}[A["id"]]
    assert row["pass"] is False and row["verified"] is False


def test_kc_token_row_regex_reads_joined_lines(tmp_path, monkeypatch):
    rows = [
        {"id": A["id"], "layer": 60, "pos": -1, "tokens": ["ĠKirin", "Ġ9100"], "scores": [1, 0.5]},
        {"id": B["id"], "layer": 60, "pos": -1, "tokens": ["Ġsix"], "scores": [1]},
    ]
    FakeLLM.install(monkeypatch, _kc_judge(quote=""), digest=_all_lines)
    r = kj.run(_kc_args(_write(tmp_path, rows), tmp_path / "o"))
    by = {x["id"]: x for x in r.rows}
    assert by[A["id"]]["pass"] is True  # "Kirin 9100" only exists across the joined line
    assert by[B["id"]]["pass"] is False
    assert r.config["source_kind"] == "tokens"


def test_kc_item_states(tmp_path, monkeypatch):
    rows = [json.loads(x) for x in KC_EXAMPLE.read_text().splitlines()]
    path = _write(tmp_path, [x for x in rows if not (x["id"] == A["id"] and x["layer"] == 60)])
    FakeLLM.install(monkeypatch, _kc_judge(quote="STATEMENT-0"), digest=_all_lines)
    r = kj.run(_kc_args(path, tmp_path / "m", allow_missing=True))
    by = {x["id"]: x for x in r.rows}
    assert by[A["id"]]["pass"] is None and by[A["id"]]["n_missing"] == 1  # missing layer: undecided
    assert by[B["id"]]["pass"] is False
    assert r.counts["n_missing_cells"] == 1

    fake = FakeLLM.install(monkeypatch, _kc_judge(), digest=lambda user: None)
    r = kj.run(_kc_args(KC_EXAMPLE, tmp_path / "u"))
    assert fake.n("knowledge_cutoff") == 0 and all(x["pass"] is None for x in r.rows)
    assert r.counts["n_unjudged_cells"] == 2

    fake = FakeLLM.install(monkeypatch, _kc_judge(), digest=lambda user: {"items": []})
    r = kj.run(_kc_args(KC_EXAMPLE, tmp_path / "e"))
    assert fake.n("knowledge_cutoff") == 0 and all(x["pass"] is False for x in r.rows)
    assert r.counts["n_empty_cells"] == 2 and r.extras["summary"]["n_digest_zero_nonempty"] == 2

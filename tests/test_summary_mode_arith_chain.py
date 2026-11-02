"""Summary mode (plan 0020) on arithmetic_intermediates and chain_intermediates: forced
``cells=all``, one judged digest per item, values verified on evidence samples only."""

import json
import re
from pathlib import Path

import pytest
from summary_fakes import FakeLLM, first_lines_digest, summary_args

from wsbench import registry
from wsbench.evals.arithmetic_intermediates import SPEC as ARITH
from wsbench.evals.arithmetic_intermediates.prompts import PROMPT_VERSION as ARITH_PV
from wsbench.evals.arithmetic_intermediates.prompts import SYSTEM_SUMMARY as ARITH_SYSTEM
from wsbench.evals.chain_intermediates import SPEC as CHAIN
from wsbench.evals.chain_intermediates.prompts import (
    NATIVE_PROMPT_VERSION as CHAIN_PV,  # plan 0038: the free-recall (v1) instrument's stamp
)
from wsbench.evals.chain_intermediates.prompts import SYSTEM as CHAIN_NATIVE_SYSTEM
from wsbench.evals.chain_intermediates.prompts import SYSTEM_SUMMARY as CHAIN_SYSTEM


def _legacy_args(*a, **kw):
    """These tests pin the plan 0020 evidence gate, so they run without the plan 0022 numbers
    digest (``summ_numbers=0``); the numbers digest has its own tests. A real (numbers) digest
    of these families runs joint, so the legacy one does too (``summ_layers=joint``; audit F1
    made the per-layer union the default for non-numbers digests)."""
    kw["extra"] = {"summ_numbers": "0", "summ_layers": "joint", **kw.get("extra", {})}
    return summary_args(*a, **kw)


@pytest.fixture(autouse=True)
def _registered():
    for spec in (ARITH, CHAIN):
        registry.FAMILIES.setdefault(spec.name, spec)


CHAIN_V1 = Path(__file__).resolve().parents[1] / "evals/chain_intermediates/items.json"


@pytest.fixture
def chain_v1(monkeypatch):
    """plan 0038 C12: the v1-stamped chain summary tests stay on the v1 bank and the v1
    free-recall summary judge (``opts=judge=free``); bank v2 + the MC judge are the default."""
    monkeypatch.setenv("WSB_BANK_FILE_CHAIN_INTERMEDIATES", str(CHAIN_V1))


def _chain_args(*a, **kw):
    kw["extra"] = {"judge": "free", **kw.get("extra", {})}
    return _legacy_args(*a, **kw)


def _all_lines(user: str) -> dict:
    return first_lines_digest(user, 100)


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    return path


# ---------------------------------------------------------------- arithmetic

ARITH_IDS = ["sign-062", "subsub-000", "addmul-000"]  # intermediates -51 / 21 / 54
ARITH_TEXT = {
    ("sign-062", 56, -3): "alpha: first we get -51 here",
    ("sign-062", 60, -1): "alpha: also -68 appears",  # sign-063's intermediate (a null)
    ("subsub-000", 56, -3): "beta: the step is computed",
}


def _arith_rows(drop: tuple[str, ...] = ()) -> list[dict]:
    tag = {"sign-062": "alpha", "subsub-000": "beta", "addmul-000": "gamma"}
    return [
        {
            "id": i,
            "layer": layer,
            "pos": pos,
            "samples": [ARITH_TEXT.get((i, layer, pos), f"{tag[i]} filler L{layer} p{pos}")],
        }
        for i in ARITH_IDS
        if i not in drop
        for layer in (56, 60)
        for pos in (-8, -3, -1)
    ]


def _arith_judge(system: str, user: str, schema: dict) -> dict:
    if schema.get("name") == "arith_free_batch":  # native cells=all
        return {"entries": [{"k": 1, "values": [], "basis": "none", "quote": ""}]}
    assert system == ARITH_SYSTEM and "digest of the readouts" in user
    if "alpha" in user:  # -68 is in an evidence sample, -99 nowhere
        return {"states_value": True, "values": [-51, -68, -99], "basis": "arithmetic", "quote": ""}
    if "beta" in user:  # 21 only in the summarizer's statement
        return {"states_value": True, "values": [21], "basis": "stated_result", "quote": "is 21"}
    return {"states_value": False, "values": [], "basis": "none", "quote": ""}


def test_arith_one_call_per_item_all_positions(tmp_path, monkeypatch):
    path = _write(tmp_path / "a.jsonl", _arith_rows())
    fake = FakeLLM.install(monkeypatch, _arith_judge, digest=_all_lines)
    r = ARITH.run(_legacy_args(path, tmp_path / "o", ARITH_PV, items=ARITH_IDS))
    assert fake.n("digest") == 3 and fake.n("arith_free") == 3
    for _n, _s, user in (c for c in fake.calls if c[0] == "digest"):
        for layer in (56, 60):
            for pos in (-8, -3, -1):
                assert f"[L{layer} pos {pos}]" in user  # forced cells=all: every position
    rows = {x["id"]: x for x in r.rows}
    assert rows["sign-062"]["pass"] is True and rows["sign-062"]["kept"] == [-51, -68]
    assert rows["sign-062"]["cross"] == pytest.approx(1 / 23)  # the null on the same digest
    assert rows["subsub-000"]["pass"] is False and rows["subsub-000"]["kind"] == "unverified"
    assert rows["addmul-000"]["pass"] is False
    assert "summary_evidence" in rows["sign-062"] and "earliest_layer" not in rows["sign-062"]
    assert r.config["aggregate"] == "summary" and r.config["cells"] == "all"
    assert r.config["prompt_version"] == f"{ARITH_PV}+digest-v5-task-extractive-joint+sj-v10"
    assert "per_layer_hit_rate" not in r.extras and r.extras["summary"]["n_items_summarized"] == 3

    native = ARITH.run(
        _legacy_args(
            path,
            tmp_path / "n",
            ARITH_PV,
            items=ARITH_IDS,
            extra={"aggregate": "native", "cells": "all"},
        )
    )
    for k in ("n_expected_cells", "n_missing_cells"):
        assert r.counts[k] == native.counts[k]


def test_arith_summary_rejects_frozen(tmp_path, monkeypatch):
    path = _write(tmp_path / "a.jsonl", _arith_rows())
    FakeLLM.install(monkeypatch, _arith_judge)
    with pytest.raises(SystemExit) as e:
        ARITH.run(
            _legacy_args(path, tmp_path / "o", ARITH_PV, items=ARITH_IDS, extra={"cells": "frozen"})
        )
    assert e.value.code == 2


def test_arith_statement_value_fails_gate(tmp_path, monkeypatch):
    """Abstractive render: the judge reads the summarizer's statement ("is 21"), but the value
    is in no evidence sample, so it is not kept."""

    def digest(user: str) -> dict:
        d = _all_lines(user)
        for it in d["items"]:
            it["statement"] = "the result is 21"
        return d

    path = _write(tmp_path / "a.jsonl", _arith_rows())
    fake = FakeLLM.install(monkeypatch, _arith_judge, digest=digest)
    r = ARITH.run(
        _legacy_args(
            path, tmp_path / "o", ARITH_PV, items=ARITH_IDS, extra={"summ_render": "abstractive"}
        )
    )
    beta = next(u for n, _s, u in fake.calls if n == "arith_free" and "beta" in u)
    assert "the result is 21" in beta
    assert next(x for x in r.rows if x["id"] == "subsub-000")["pass"] is False


def test_arith_no_cells_and_unsummarized_are_undecided(tmp_path, monkeypatch):
    path = _write(tmp_path / "a.jsonl", _arith_rows(drop=("addmul-000",)))
    fake = FakeLLM.install(
        monkeypatch,
        _arith_judge,
        digest=lambda u: None if "alpha" in u else _all_lines(u),
    )
    r = ARITH.run(_legacy_args(path, tmp_path / "o", ARITH_PV, items=ARITH_IDS, allow_missing=True))
    rows = {x["id"]: x for x in r.rows}
    assert rows["addmul-000"]["pass"] is None and rows["addmul-000"]["kind"] == "missing"
    assert rows["sign-062"]["pass"] is None and rows["sign-062"]["summary_state"] == "unsummarized"
    assert rows["subsub-000"]["pass"] is False
    assert fake.n("digest") == 2 and fake.n("arith_free") == 1
    assert r.counts["n_unjudged_cells"] == 1 and r.counts["n_missing_cells"] == 1


def test_arith_digest_bundle_has_no_token_text(tmp_path, monkeypatch):
    """Camila: "Remove the token labels". The digest headers carry the layer and position only,
    so no read-site token (which would spell out the expression) reaches the summarizer or the
    judge."""
    toks = ["Compute", "271", " Reply", "322"]  # " -" would match the headers' "pos -4"
    rows = [
        {"id": "sign-062", "layer": 56, "pos": p, "token": t, "samples": [f"readout {k} says -51"]}
        for k, (p, t) in enumerate(zip([-4, -3, -2, -1], toks, strict=True))
    ]
    path = _write(tmp_path / "a.jsonl", rows)
    fake = FakeLLM.install(monkeypatch, _arith_judge, digest=_all_lines)
    ARITH.run(_legacy_args(path, tmp_path / "o", ARITH_PV, items=["sign-062"]))
    for name, _s, user in fake.calls:
        heads = re.findall(r"^\[L\d+ pos -?\d+\]$", user, flags=re.M)
        if name == "digest":
            assert heads == [f"[L56 pos {p}]" for p in (-4, -3, -2, -1)]
        assert "token=" not in user
        for t in toks:
            assert t not in user, (name, t)


# ---------------------------------------------------------------- chain

CHAIN_IDS = ["chain-d3p-0611", "chain-d3p-0637", "chain-d3p-0640"]  # gold [11,5] [11,14] [18,21]
CHAIN_TEXT = {
    ("chain-d3p-0611", 20, 70): "alpha: so the final answer is 2",
    ("chain-d3p-0611", 20, 77): "alpha: the running value is 11",
    ("chain-d3p-0637", 20, 70): "beta: the result is 6",
}


def _chain_rows(drop: tuple[tuple[str, int], ...] = ()) -> list[dict]:
    tag = {"chain-d3p-0611": "alpha", "chain-d3p-0637": "beta", "chain-d3p-0640": "gamma"}
    return [
        {
            "id": i,
            "layer": layer,
            "pos": pos,
            "samples": [CHAIN_TEXT.get((i, layer, pos), f"{tag[i]} filler L{layer} p{pos}")],
        }
        for i in CHAIN_IDS
        for layer in (20, 24)
        if (i, layer) not in drop
        for pos in (70, 77)
    ]


def _chain_judge(system: str, user: str, schema: dict) -> dict:
    summary = "digest of the readouts" in user  # native runs share this fake
    assert system == (CHAIN_SYSTEM if summary else CHAIN_NATIVE_SYSTEM)
    if "alpha" in user:  # top value is the answer; the verified second value is gold
        return {"states_value": True, "values": [2, 11], "basis": "stated_result", "quote": "2"}
    if "beta" in user:  # 6 is the answer; 99 appears nowhere
        return {"states_value": True, "values": [6, 99], "basis": "stated_result", "quote": "6"}
    if "gamma" in user:  # 18 is gold but only in the summarizer's statement
        return {"states_value": True, "values": [18], "basis": "stated_result", "quote": "is 18"}
    return {"states_value": False, "values": [], "basis": "none", "quote": ""}


def test_chain_any_of_3_all_positions(tmp_path, monkeypatch, chain_v1):
    path = _write(tmp_path / "c.jsonl", _chain_rows())
    fake = FakeLLM.install(monkeypatch, _chain_judge, digest=_all_lines)
    r = CHAIN.run(_chain_args(path, tmp_path / "o", CHAIN_PV, items=CHAIN_IDS))
    assert fake.n("digest") == 3 and fake.n("chain_free") == 3
    for _n, _s, user in (c for c in fake.calls if c[0] == "digest"):
        assert all(f"[L{L} pos {p}]" in user for L in (20, 24) for p in (70, 77))
    rows = {x["id"]: x for x in r.rows}
    a = rows["chain-d3p-0611"]
    assert a["pass"] is True and a["any_of_3"] and not a["top1_hit"] and a["kept"] == [2, 11]
    assert rows["chain-d3p-0637"]["pass"] is False and rows["chain-d3p-0637"]["kept"] == [6]
    assert rows["chain-d3p-0640"]["kind"] == "unverified"
    assert "earliest_layer" not in a and "kind_by_layer" not in a
    assert "layer_protocols" not in r.extras and "null_top1_near" not in r.extras
    assert r.extras["null_near"] == 0.0
    assert r.config["aggregate"] == "summary" and r.config["cells"] == "all"
    assert r.config["prompt_version"] == f"{CHAIN_PV}+digest-v5-task-extractive-joint+sj-v10"

    native = CHAIN.run(
        _chain_args(
            path,
            tmp_path / "n",
            CHAIN_PV,
            items=CHAIN_IDS,
            extra={"aggregate": "native", "cells": "all"},
        )
    )
    for k in ("n_expected_cells", "n_missing_cells"):
        assert r.counts[k] == native.counts[k]


def test_chain_near_decoy_any_of_3(tmp_path, monkeypatch, chain_v1):
    rows = _chain_rows()
    rows[2]["samples"] = ["alpha: maybe 12 then 11"]  # 12 is a decoy of 11
    path = _write(tmp_path / "c.jsonl", rows)

    def judge(system: str, user: str, schema: dict) -> dict:
        if "alpha" in user:  # no gold, a verified decoy in the second slot
            return {"states_value": True, "values": [2, 12], "basis": "numeral_bag", "quote": ""}
        return {"states_value": False, "values": [], "basis": "none", "quote": ""}

    FakeLLM.install(monkeypatch, judge, digest=_all_lines)
    r = CHAIN.run(_chain_args(path, tmp_path / "o", CHAIN_PV, items=CHAIN_IDS))
    a = next(x for x in r.rows if x["id"] == "chain-d3p-0611")
    assert a["pass"] is False and a["kind"] == "near"
    assert a["null_near"] == pytest.approx(2 / 10)  # len(gold) / len(near), as native


def test_chain_summary_lite_reads_final_token(tmp_path, monkeypatch, chain_v1):
    """plan 0038 C12 (sanctioned rename of test_chain_summary_rejects_last): ``cells=last`` still
    exits 2 (now with the reads= hint); summary + ``reads=lite`` judges the max-pos cell per
    (item, layer)."""
    path = _write(tmp_path / "c.jsonl", _chain_rows())
    FakeLLM.install(monkeypatch, _chain_judge)
    with pytest.raises(SystemExit) as e:
        CHAIN.run(
            _chain_args(path, tmp_path / "o", CHAIN_PV, items=CHAIN_IDS, extra={"cells": "last"})
        )
    assert e.value.code == 2
    fake = FakeLLM.install(monkeypatch, _chain_judge, digest=_all_lines)
    r = CHAIN.run(
        _chain_args(path, tmp_path / "lite", CHAIN_PV, items=CHAIN_IDS, extra={"reads": "lite"})
    )
    for _n, _s, user in (c for c in fake.calls if c[0] == "digest"):
        assert all(f"[L{L} pos 77]" in user for L in (20, 24))
        assert "pos 70]" not in user
    assert r.config["reads"] == "lite" and r.config["prompt_version"].endswith("+reads-lite")


def test_chain_statement_value_fails_gate(tmp_path, monkeypatch, chain_v1):
    def digest(user: str) -> dict:
        d = _all_lines(user)
        for it in d["items"]:
            it["statement"] = "the value is 18"
        return d

    path = _write(tmp_path / "c.jsonl", _chain_rows())
    fake = FakeLLM.install(monkeypatch, _chain_judge, digest=digest)
    r = CHAIN.run(
        _chain_args(
            path, tmp_path / "o", CHAIN_PV, items=CHAIN_IDS, extra={"summ_render": "abstractive"}
        )
    )
    gamma = next(u for n, _s, u in fake.calls if n == "chain_free" and "gamma" in u)
    assert "the value is 18" in gamma
    assert next(x for x in r.rows if x["id"] == "chain-d3p-0640")["pass"] is False


def test_chain_missing_layer_unsummarized_and_empty(tmp_path, monkeypatch, chain_v1):
    path = _write(tmp_path / "c.jsonl", _chain_rows(drop=(("chain-d3p-0640", 24),)))

    def digest(user: str) -> dict | None:
        if "alpha" in user:
            return None  # a failed digest call
        if "beta" in user:
            return {"items": []}  # zero items: empty, a judged fail
        return _all_lines(user)

    fake = FakeLLM.install(monkeypatch, _chain_judge, digest=digest)
    r = CHAIN.run(_chain_args(path, tmp_path / "o", CHAIN_PV, items=CHAIN_IDS, allow_missing=True))
    rows = {x["id"]: x for x in r.rows}
    assert rows["chain-d3p-0611"]["pass"] is None  # unsummarized
    assert rows["chain-d3p-0637"]["pass"] is False and rows["chain-d3p-0637"]["kind"] == "empty"
    assert rows["chain-d3p-0640"]["pass"] is None  # missing layer, no pass
    assert fake.n("chain_free") == 1
    assert r.counts["n_missing_cells"] == 1 and r.counts["n_unjudged_cells"] == 1
    assert r.counts["n_empty_cells"] == 1 and r.extras["summary"]["n_digest_zero_nonempty"] == 1

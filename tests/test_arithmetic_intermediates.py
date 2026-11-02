"""arithmetic_intermediates: the bank, tolerance and verification rules, the verdict with its
permutation null, a scripted run and a dry run."""

import json
import re
from pathlib import Path

import pytest
from conftest import native_args, write_sidecar
from summary_fakes import FakeLLM as _FakeLLM
from summary_fakes import summary_args

from wsbench import digest, readplan, reads, registry
from wsbench.banks import load_bank
from wsbench.cli import main
from wsbench.evals.arithmetic_intermediates import judge
from wsbench.evals.arithmetic_intermediates import prompts as arith_prompts
from wsbench.evals.arithmetic_intermediates.prompts import (
    PROMPT_VERSION,
    PROMPT_VERSION_BATCH,
    SYSTEM,
    SYSTEM_BATCH,
)
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.readouts import Cell, bulleted
from wsbench.results import read_results

REPO = Path(__file__).resolve().parents[1]
BANK = REPO / "evals/arithmetic_intermediates/items.json"
EXAMPLE = REPO / "examples/readouts/arithmetic_intermediates.jsonl"
KEPT = {
    "absval", "addmul", "floordiv", "frac", "fracadd", "fraccomp", "fracint", "fracsmall",
    "muladd", "mulmid", "sign", "signpair", "subsub", "subsubx",
}  # fmt: skip


@pytest.fixture(autouse=True)
def _registered():
    from wsbench.evals.arithmetic_intermediates import SPEC

    registry.FAMILIES.setdefault(SPEC.name, SPEC)


def test_bank():
    header, items = load_bank(BANK)
    assert header["family"] == "arithmetic_intermediates" and len(items) == 596
    assert set(header["variants"]) == KEPT and "maxsel" in header["removed_variants"]
    names = {it["name"] for it in items}
    for it in items:
        v = header["variants"][it["variant"]]
        assert it["tolerance"] == v["tolerance"] and it["cell"] == v["cell"]
        assert it["cell"]["layer"] in (56, 60) and it["cell"]["pos"] in (-7, -8)
        assert it["intermediates"] and float(it["intermediates"][0]) == float(
            it["intermediates"][0]
        )
        assert it["null_set"] and all(n in names for n in it["null_set"])
        assert all(n != it["name"] for n in it["null_set"])
    assert sum(v["n_items"] for v in header["variants"].values()) == 596


def test_tolerance_and_quantities():
    assert judge.tolerance_ok(-51.0, -51.0, "exact") and not judge.tolerance_ok(
        51.0, -51.0, "exact"
    )
    assert judge.tolerance_ok(74.0, 73.0, "rel2pct") and not judge.tolerance_ok(
        75.0, 73.0, "rel2pct"
    )
    assert judge.quantities("- 2. The total is 4,816 and -51.\n- 17,000") == [
        4816.0,
        -51.0,
        17000.0,
    ]
    assert judge.quantities("Step 3: 0.777778 \u2248 \uff17.\uff15") == [0.777778, 7.5]
    assert judge.quantities("29.") == [29.0]  # a bare number on its own line is a value
    assert judge.quantities("-51. Then times 14") == [-51.0, 14.0]  # a negative is not a bullet
    assert judge.quantities("- 2. The answer is 9") == [9.0]  # a bulleted list marker is
    assert judge.quantities("\u221251 and \u2212 3") == [-51.0, 3.0]  # the real minus sign


def test_verified_and_verdict():
    text = "- 271 - 322 = -51, then times 14\n- 结果是 负五十一"
    assert judge.verified(-51.0, text, "") and not judge.verified(-52.0, text, "")
    # a CJK-numeral quote vouches for the top value it writes (plan 0036 C6: "yields the named
    # value"), never for a different one
    assert judge.verified(-51.0, "结果是 负五十一", "负五十一")
    assert not judge.verified(-52.0, text, "负五十一") and not judge.verified(
        51.0, text, "负五十一"
    )
    assert not judge.verified(-51.0, "结果是 负五十一", "负五十一", top=False)  # only the top value
    assert not judge.verified(-52.0, text, "-52")  # a bare-number quote does not
    assert not judge.verified(-52.0, text, "4,816") and not judge.verified(
        999.0, text, "then times"
    )
    assert not judge.verified(-52.0, text, "not here 五")  # must be verbatim
    nulls = [-40.0, -60.0, 12.0]
    v = judge.verdict(
        {"values": [-51, 14], "basis": "arithmetic", "quote": "-51"}, -51.0, "exact", nulls, text
    )
    assert (
        v["kind"] == "hit"
        and v["hit"]
        and v["top1_hit"]
        and v["cross"] == 0.0
        and v["kept"] == [-51.0, 14.0]
    )
    v = judge.verdict(
        {"values": [-40, -51], "basis": "numeral_bag", "quote": ""},
        -51.0,
        "exact",
        nulls,
        "-40 and -51",
    )
    assert v["hit"] and not v["top1_hit"] and v["cross"] == pytest.approx(1 / 3)
    v = judge.verdict(
        {"values": [99], "basis": "stated_result", "quote": "ninety-nine"},
        -51.0,
        "exact",
        nulls,
        text,
    )
    assert v["kind"] == "unverified" and not v["hit"]
    v = judge.verdict(
        {"values": [14], "basis": "stated_result", "quote": "14"}, -51.0, "exact", nulls, text
    )
    assert v["kind"] == "other" and v["cross"] == 0.0
    assert (
        judge.verdict({"values": [], "basis": "none", "quote": ""}, -51.0, "exact", nulls, text)[
            "kind"
        ]
        == "none"
    )
    assert judge.verdict(
        {"values": [True, 1, 2, 3, 4], "basis": "none", "quote": ""}, 1.0, "exact", [], "1 2 3 4"
    )["values"] == [1.0, 2.0, 3.0]
    assert judge.verdict(None, -51.0, "exact", nulls, text)["judged"] is False
    # relative tolerance: 4.30 counts for a 4.333 intermediate at 2%
    v = judge.verdict(
        {"values": [4.303030303030303], "basis": "arithmetic", "quote": ""},
        4.333333,
        "rel2pct",
        [],
        "142/33 = 4.303030303030303",
    )
    assert v["hit"]


def test_scripted_run(tmp_path, monkeypatch):
    _h, items = load_bank(BANK)
    by_id = {it["id"]: it for it in items}
    ids = sorted({json.loads(x)["id"] for x in EXAMPLE.read_text().splitlines() if x.strip()})
    assert len(ids) == 4
    pick = {by_id[i]["variant"]: i for i in ids}
    a, b, c, d = pick["sign"], pick["addmul"], pick["frac"], pick["subsub"]

    def fake_run_calls(calls, **kw):
        out = {}
        for call in calls:
            i = call.meta["item"]
            target = float(by_id[i]["intermediates"][0])
            if i == a:  # names the intermediate
                out[call.key] = {
                    "states_value": True,
                    "values": [target],
                    "basis": "arithmetic",
                    "quote": "",
                }
            elif i == b:  # names a null item's intermediate (a cross hit, not a hit)
                other = float(by_id[by_id[i]["null_set"][0]]["intermediates"][0])
                out[call.key] = {
                    "states_value": True,
                    "values": [other],
                    "basis": "stated_result",
                    "quote": "",
                }
            elif i == c:
                out[call.key] = None
            else:
                out[call.key] = {"states_value": False, "values": [], "basis": "none", "quote": ""}
        return out

    # item b's readout writes a null item's intermediate, so the value verifies and crosses
    other = by_id[by_id[b]["null_set"][0]]["intermediates"][0]
    rows = [json.loads(x) for x in EXAMPLE.read_text().splitlines() if x.strip()]
    for row in rows:
        if row["id"] == a:  # the real rows do not write -51; a scripted hit must verify
            row["samples"] = [f"- 271 - 322 = {by_id[a]['intermediates'][0]}, then times 14"]
        if row["id"] == b:
            row["samples"] = [f"- the sum comes to {other}"]
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in rows))
    monkeypatch.setattr(judge, "run_calls", fake_run_calls)
    args = native_args(
        readouts=path,
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        layers=None,
        items=ids,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
    )
    r = judge.run(args)
    rows = {row["id"]: row for row in r.rows}
    assert rows[a]["pass"] is True and rows[a]["kind"] == "hit" and rows[a]["cross"] == 0.0
    assert rows[b]["pass"] is False and rows[b]["kind"] == "other" and rows[b]["cross"] > 0
    assert rows[c]["pass"] is None and rows[d]["pass"] is False
    assert r.value == pytest.approx(1 / 3) and r.extras["n_items_decided"] == 3
    assert r.extras["cross"] > 0 and r.extras["net"] < r.value
    assert r.counts["n_unjudged_cells"] == 1 and r.counts["n_missing_cells"] == 0
    assert set(r.extras["per_variant"]) <= KEPT and r.extras["per_role"]


def test_rows_off_the_frozen_cell_are_ignored_and_missing_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(judge, "run_calls", lambda calls, **kw: {})
    _h, items = load_bank(BANK)
    it = items[0]
    rows = [
        {
            "id": it["id"],
            "layer": it["cell"]["layer"],
            "pos": it["cell"]["pos"] + 1,
            "samples": ["x"],
        },
        {"id": it["id"], "layer": 20, "pos": it["cell"]["pos"], "samples": ["x"]},
    ]
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in rows))
    base = {
        "readouts": path,
        "out": tmp_path / "out",
        "judge": resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        "layers": None,
        "items": [it["id"]],
        "limit": 0,
        "allow_missing": False,
        "concurrency": 1,
        "rpm": 1.0,
        "dry_run": False,
    }
    with pytest.raises(SystemExit) as e:
        judge.run(native_args(**base))
    assert e.value.code == 2
    r = judge.run(native_args(**{**base, "allow_missing": True}))
    assert r.counts["n_missing_cells"] == 1 and r.extras["n_rows_off_cell"] == 2
    with pytest.raises(SystemExit):
        judge.run(native_args(**{**base, "layers": [56, 60]}))


def test_registered_readme_and_dry_run(tmp_path, capsys, monkeypatch):
    from wsbench.evals.arithmetic_intermediates import SPEC

    assert SPEC.group == "computational" and SPEC.judge.prompt_version == PROMPT_VERSION
    readme = (REPO / "evals/arithmetic_intermediates/README.md").read_text(encoding="utf-8")
    assert SYSTEM in readme and SYSTEM_BATCH in readme and PROMPT_VERSION_BATCH in readme
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
    assert r.value is None and r.extras["n_items_without_readouts"] == 592
    assert "Readout:" in capsys.readouterr().out


_ENTRY = re.compile(r"^\[(\d+)\] pos=(-?\d+): ", re.M)


def batch_entries_of(user: str) -> list[tuple[int, int, str]]:
    """(k, pos, text) of every entry in a batched user message, as the test judge reads it."""
    heads = list(_ENTRY.finditer(user))
    tail = user.rindex("\n\nFor each entry")
    out = []
    for n, m in enumerate(heads):
        stop = heads[n + 1].start() if n + 1 < len(heads) else tail
        out.append((int(m.group(1)), int(m.group(2)), user[m.end() : stop].strip()))
    return out


def test_all_cells_mode_uses_every_row_and_reports_bands(tmp_path, monkeypatch):
    """``opts=cells=all``: every (layer, pos) row is a cell, ONE call per (item, layer) lists
    them as numbered entries, an item passes on any cell, and the accuracy bands are computed
    over the same kept values."""
    _h, items = load_bank(BANK)
    it = next(x for x in items if x["tolerance"] == "exact")
    target = float(it["intermediates"][0])
    off = target * 1.03  # inside 5%, outside exact
    rows = [
        {"id": it["id"], "layer": 20, "pos": 0, "token": "a", "samples": ["nothing here"]},
        {"id": it["id"], "layer": 20, "pos": 1, "token": "\n", "samples": [f"maybe {off:g}"]},
        {"id": it["id"], "layer": 60, "pos": 1, "samples": [f"the value is {target:g}"]},
    ]
    seen: list[dict] = []

    def fake_run_calls(calls, **kw):
        seen.append(kw)
        out = {}
        for c in calls:
            entries = batch_entries_of(c.user)
            assert [k for k, _p, _t in entries] == list(range(1, len(entries) + 1))
            assert [p for _k, p, _t in entries] == c.meta["positions"]
            reply = []
            for k, _pos, text in entries:
                if f"{target:g}" in text:
                    reply.append({"k": k, "values": [target], "quote": f"{target:g}", "basis": "t"})
                elif f"{off:g}" in text:
                    reply.append({"k": k, "values": [off], "quote": f"{off:g}", "basis": "t"})
                else:
                    reply.append({"k": k, "values": [], "quote": "", "basis": "none"})
            out[c.key] = {"entries": reply}
        return out

    monkeypatch.setattr(judge, "run_calls", fake_run_calls)
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in rows))
    args = native_args(
        readouts=path,
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        layers=None,
        items=[it["id"]],
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        extra={"cells": "all"},
    )
    r = judge.run(args)
    row = r.rows[0]
    assert row["n_cells"] == 3 and row["pass"] is True and row["hits_at"] == [(60, 1)]
    assert row["bands"] == {"exact": True, "rel5pct": True}
    assert r.extras["n_rows_off_cell"] == 0 and r.extras["n_calls"] == 2  # (item, layer) pairs
    assert r.extras["n_calls_failed"] == 0 and r.counts["n_unjudged_cells"] == 0
    assert r.extras["cell_hit_rate"] == pytest.approx(1 / 3)
    assert r.extras["per_layer_hit_rate"] == {"20": 0.0, "60": 1.0}
    assert r.config["cells"] == "all" and r.config["layers_judged"] == [20, 60]
    assert r.config["prompt_version"] == PROMPT_VERSION_BATCH
    # final r1: calls keep the batched call version; the stamp adds the rule version
    from wsbench.evals.arithmetic_intermediates.prompts import CALL_VERSION_BATCH

    assert seen[0]["prompt_version"] == CALL_VERSION_BATCH and seen[0]["validate"] is not None
    # without the exact cell, only the 5% band is reached
    path.write_text("".join(json.dumps(x) + "\n" for x in rows[:2]))
    r2 = judge.run(native_args(**{**args.__dict__, "out": tmp_path / "out2"}))
    assert r2.rows[0]["pass"] is False and r2.extras["n_calls"] == 1
    assert r2.rows[0]["bands"] == {"exact": False, "rel5pct": True}
    assert r2.extras["bands"]["rel5pct"] == 1.0 and r2.extras["bands"]["exact"] == 0.0


def test_batched_replies_are_read_per_entry(tmp_path, monkeypatch):
    """A batched reply is mapped back to cells by ``k``: the first well-formed entry per k
    wins, malformed and missing entries leave their cells unjudged, a failed call leaves every
    cell of its (item, layer) unjudged, a reply without any usable entry is invalid."""
    good = {"k": 2, "values": [1.0], "basis": "t", "quote": ""}
    res = {
        "entries": [
            good,
            {"k": 2, "values": [2.0]},  # duplicate k: ignored
            {"k": "x", "values": []},  # non-integer k
            {"k": 5, "values": []},  # out of range
            {"k": 1.0, "values": [3.0]},  # an integral float is fine
            {"k": 3, "values": "no"},  # values not a list
            {"k": True, "values": []},
        ]
    }
    parsed = judge.batch_entries(res, 4)
    assert set(parsed) == {1, 2} and parsed[2] is good and parsed[1]["values"] == [3.0]
    assert judge.batch_entries(None, 3) == {} and judge.batch_entries({"entries": "x"}, 3) == {}
    call = judge.Call(key="k", system="", user="", meta={"n_entries": 4})
    assert judge.valid_batch(call, res) and not judge.valid_batch(call, {"entries": []})

    _h, items = load_bank(BANK)
    it = next(x for x in items if x["tolerance"] == "exact")
    target = float(it["intermediates"][0])
    rows = [
        {"id": it["id"], "layer": 56, "pos": -3, "samples": [f"it comes to {target + 1:g}"]},
        {"id": it["id"], "layer": 56, "pos": -2, "samples": [f"so {target:g}"]},
        {"id": it["id"], "layer": 56, "pos": -1, "samples": ["nothing"]},
        {"id": it["id"], "layer": 60, "pos": -1, "samples": ["nothing"]},
    ]
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in rows))
    base = {
        "readouts": path,
        "out": tmp_path / "out",
        "judge": resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        "layers": None,
        "items": [it["id"]],
        "limit": 0,
        "allow_missing": False,
        "concurrency": 1,
        "rpm": 1.0,
        "dry_run": False,
        "extra": {"cells": "all"},
    }
    # the layer-56 reply skips entry 2 (the hit), the layer-60 call fails
    monkeypatch.setattr(
        judge,
        "run_calls",
        lambda calls, **kw: {
            c.key: (
                None
                if c.meta["layer"] == 60
                else {
                    "entries": [
                        {"k": 1, "values": [target + 1], "basis": "t", "quote": ""},
                        {"k": 3, "values": [], "basis": "none", "quote": ""},
                    ]
                }
            )
            for c in calls
        },
    )
    r = judge.run(native_args(**base))
    row = r.rows[0]
    assert row["pass"] is None and row["n_cells"] == 4 and row["n_unjudged"] == 2
    assert r.counts["n_unjudged_cells"] == 2 and r.extras["n_calls_failed"] == 1
    assert r.extras["n_calls"] == 2 and r.complete is False
    assert row["unjudged_at"] == [(56, -2), (60, -1)]
    # a hit in one entry decides the item even with unjudged cells beside it
    monkeypatch.setattr(
        judge,
        "run_calls",
        lambda calls, **kw: {
            c.key: {
                "entries": [
                    {"k": 2, "values": [target], "basis": "t", "quote": ""},
                ]
            }
            if c.meta["layer"] == 56
            else None
            for c in calls
        },
    )
    r = judge.run(native_args(**{**base, "out": tmp_path / "out2"}))
    assert r.rows[0]["pass"] is True and r.rows[0]["hits_at"] == [(56, -2)]
    assert r.rows[0]["n_unjudged"] == 3 and r.value == 1.0


def test_example_file_carries_the_every_position_regime(tmp_path, monkeypatch):
    """Since 2026-09-23 the readouts of record hold every position at layers 56/60, judged
    ``opts=cells=all``: the toy file shows several positions of both layers per item, each item's
    frozen cell among them, ``pos`` a negative offset from the end of the render."""
    header, items = load_bank(BANK)
    assert "every position" in header["read"] and "cells=all" in header["read"]
    by_id = {it["id"]: it for it in items}
    rows = [json.loads(x) for x in EXAMPLE.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert {r["layer"] for r in rows} == {56, 60} and all(r["pos"] < 0 for r in rows)
    for i in {r["id"] for r in rows}:
        cells = {(r["layer"], r["pos"]) for r in rows if r["id"] == i}
        assert len(cells) >= 3 and len({p for _l, p in cells}) >= 2
        assert (by_id[i]["cell"]["layer"], by_id[i]["cell"]["pos"]) in cells
    assert any(not r["samples"] for r in rows)  # one real empty cell: a negative, not a gap
    monkeypatch.delenv("WSBENCH_JUDGE_MODEL", raising=False)
    out = tmp_path / "out"
    argv = [
        "judge",
        "family=arithmetic_intermediates",
        f"readouts={EXAMPLE}",
        f"out={out}",
        "dry_run=True",
        "opts=cells=all,aggregate=native",
    ]
    assert main(argv) == 0
    r = read_results(out)
    assert r.config["cells"] == "all" and r.config["layers_judged"] == [56, 60]
    # a dry run reports the 592 items without readouts as missing rather than failing
    assert r.counts["n_expected_cells"] - r.counts["n_missing_cells"] == len(rows)
    assert r.counts["n_empty_cells"] == 1
    assert r.extras["n_rows_off_cell"] == 0


# ---------------------------------------------------------------- plan 0036 (campaign fixes)


GOLD_ID = "floordiv-205"  # floor(a / b) + c, intermediate 135, exact
GOLD = 135.0
SPAN = list(range(-34, 0))  # the shortest render's every position (min_full_positions)
LITE = {"reads": "lite"}
REAL_RUN_CALLS = judge.run_calls


class FakeLLM(_FakeLLM):
    """summary_fakes.FakeLLM, with the real ``judge.run_calls`` restored first (a native run in
    the same test may have replaced it)."""

    @classmethod
    def install(cls, monkeypatch, judge_fn, digest=None):
        monkeypatch.setattr(judge, "run_calls", REAL_RUN_CALLS)
        return super().install(monkeypatch, judge_fn, digest)


def _write_rows(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return path


def _grid_rows(
    ids, layers=readplan.GRID, positions=SPAN, text=lambda i, layer, p: f"filler L{layer} p{p}"
) -> list[dict]:
    return [
        {"id": i, "layer": L, "pos": p, "samples": [text(i, L, p)]}
        for i in ids
        for L in layers
        for p in positions
    ]


def _nargs(path: Path, out: Path, **kw) -> object:
    extra = kw.pop("extra", {})
    return native_args(
        readouts=path,
        out=out,
        judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        layers=kw.pop("layers", None),
        items=kw.pop("items", [GOLD_ID]),
        limit=0,
        allow_missing=kw.pop("allow_missing", False),
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        extra=extra,
        **kw,
    )


def _capture(monkeypatch, reply=None) -> list:
    """Monkeypatch judge.run_calls; record every Call; answer with ``reply(call)``."""
    seen: list = []

    def fake(calls, **kw):
        seen.extend(calls)
        out = {}
        for c in calls:
            if reply is not None:
                out[c.key] = reply(c)
            elif "n_entries" in c.meta:
                out[c.key] = {
                    "entries": [
                        {"k": k, "values": [], "basis": "none", "quote": ""}
                        for k in range(1, c.meta["n_entries"] + 1)
                    ]
                }
            else:
                out[c.key] = {"states_value": False, "values": [], "basis": "none", "quote": ""}
        return out

    monkeypatch.setattr(judge, "run_calls", fake)
    return seen


def _keyed(want: str):
    """A numbers digest naming ``want`` from every bundle line that writes it as a whole number
    (and, so the digest is never empty, the first numeral of the first line otherwise)."""

    def dig(user: str) -> dict:
        lines = [x[2:] for x in user.splitlines() if x.startswith("- ")]
        items = [
            {"statement": "s", "key": want, "where": "", "evidence": ln}
            for ln in lines
            if re.search(rf"(?<![\d.]){re.escape(want)}(?![\d])", ln)
        ][:5]
        if not items:
            for ln in lines:
                m = re.search(r"\d+", ln)
                if m:
                    items = [{"statement": "s", "key": m.group(0), "where": "", "evidence": ln}]
                    break
        return {"items": items, "rare": []}

    return dig


def _value_judge(values, quote="", monkeypatch=None):
    def j(system, user, schema):
        return {"states_value": bool(values), "values": values, "basis": "t", "quote": quote}

    return j


def _batch_hit(values, quote=""):
    """A batched reply naming ``values`` for every entry."""

    def reply(c):
        return {
            "entries": [
                {"k": k, "values": values, "basis": "t", "quote": quote}
                for k in range(1, c.meta["n_entries"] + 1)
            ]
        }

    return reply


# C1: no token labels ------------------------------------------------------------------


def test_batched_user_has_no_token_labels(tmp_path, monkeypatch):
    toks = ["Compute", "271", " -", "322"]
    rows = [
        {"id": GOLD_ID, "layer": 56, "pos": p, "token": t, "samples": [f"readout {k}"]}
        for k, (p, t) in enumerate(zip([-4, -3, -2, -1], toks, strict=True))
    ]
    path = _write_rows(tmp_path / "r.jsonl", rows)
    seen = _capture(monkeypatch)
    judge.run(_nargs(path, tmp_path / "o", extra={"cells": "all"}))
    assert len(seen) == 1
    user = seen[0].user
    assert "token=" not in user and "token=" not in SYSTEM_BATCH
    for t in toks:
        assert t not in user, t
    assert "[1] pos=-4: readout 0" in user


# C3: one readout per activation --------------------------------------------------------


def test_arith_prose1_judges_one_sample(tmp_path, monkeypatch):
    rows = [{"id": GOLD_ID, "layer": 56, "pos": -1, "samples": ["first gen", "second gen"]}]
    path = _write_rows(tmp_path / "r.jsonl", rows)
    write_sidecar(path, sampling="prose1", reads="lite")
    seen = _capture(monkeypatch)
    r = judge.run(
        _nargs(path, tmp_path / "o", layers=[56], extra={"cells": "all", "reads": "lite"})
    )
    assert seen[0].user.count("first gen") == 1 and "second gen" not in seen[0].user
    assert r.config["sampling"] == "prose1" and r.config["sampling_source"] == "declared"
    assert r.extras["n_samples_trimmed"] == 1


def test_arith_bullet4_judges_four_bullets(tmp_path, monkeypatch):
    gens = ["alpha one", "beta two", "gamma three", "delta four"]
    rows = [{"id": GOLD_ID, "layer": 56, "pos": -1, "samples": gens}]
    path = _write_rows(tmp_path / "r.jsonl", rows)
    side = write_sidecar(path, sampling="bullet4", reads="lite")
    seen = _capture(monkeypatch)
    r = judge.run(
        _nargs(path, tmp_path / "o", layers=[56], extra={"cells": "all", "reads": "lite"})
    )
    assert bulleted(gens) in seen[0].user
    assert bulleted(gens).count("\n- ") == 3
    assert r.config["sampling"] == "bullet4" and r.config["sampling_source"] == "declared"
    # summary: the digest shows the same four generations as four "- " lines under one header
    fake = FakeLLM.install(monkeypatch, _value_judge([]), digest=_keyed("1"))
    judge.run(
        summary_args(path, tmp_path / "s", PROMPT_VERSION, items=[GOLD_ID], layers=[56], extra=LITE)
    )
    bundle = next(u for n, _s, u in fake.calls if n == "digest")
    assert bundle.count("[L56 pos -1]") == 1 and all(f"- {g}" in bundle for g in gens)
    # the same file without a sidecar, sampling=bullet4: identical entry text, source override
    side.unlink()
    seen.clear()
    seen2 = _capture(monkeypatch)
    r = judge.run(
        _nargs(
            path,
            tmp_path / "o2",
            extra={"cells": "all", "reads": "lite", "sampling": "bullet4"},
            layers=[56],
        )
    )
    assert bulleted(gens) in seen2[0].user and r.config["sampling_source"] == "override"


def test_arith_bullet4_value_not_assembled_across_generations(tmp_path, monkeypatch):
    gens = ["25", "times 3", "nothing", "else"]
    v = judge.verdict(
        {"values": [75], "basis": "t", "quote": "25 times 3"},
        75.0,
        "exact",
        [],
        "",
        lines=digest.native_lines([Cell("x", 56, -1, tuple(gens), None, None)]),
    )
    assert v["kept"] == [] and not v["hit"]
    # the same words inside ONE generation would vouch (quote route)
    one = judge.units_of_cell(Cell("x", 56, -1, ("25 times 3 is 75",), None, None))
    v = judge.verdict(
        {"values": [75], "basis": "t", "quote": ""},
        75.0,
        "exact",
        [],
        "",
        lines=[u[1] for u in one],
    )
    assert v["hit"]


def test_arith_s3d_multibullet_generation_is_one_readout(tmp_path, monkeypatch):
    gen = f"- the sum is {GOLD:g}\n- halving\n- floor of it\n- plus c"
    rows = [{"id": GOLD_ID, "layer": 56, "pos": -1, "samples": [gen]}]
    path = _write_rows(tmp_path / "r.jsonl", rows)
    write_sidecar(path, sampling="prose1", reads="lite")
    seen = _capture(monkeypatch)
    judge.run(_nargs(path, tmp_path / "o", layers=[56], extra={"cells": "all", "reads": "lite"}))
    assert seen[0].meta["n_entries"] == 1 and gen in seen[0].user
    quote = "halving floor of it"  # spans two bullets of the one generation
    fake = FakeLLM.install(monkeypatch, _value_judge([GOLD], quote), digest=_keyed("135"))
    r = judge.run(
        summary_args(path, tmp_path / "s", PROMPT_VERSION, items=[GOLD_ID], layers=[56], extra=LITE)
    )
    bundle = next(u for n, _s, u in fake.calls if n == "digest")
    line = next(x for x in bundle.splitlines() if x.startswith("- "))
    assert line.count(digest.BULLET_MARK.strip()) == 3
    assert sum(1 for x in bundle.splitlines() if x.startswith("- ")) == 1
    ev = digest.native_lines([Cell(GOLD_ID, 56, -1, (gen,), None, None)])
    assert digest.quote_ok(quote, ev)
    assert r.rows[0]["pass"] is True


# C4: all layers by default, lite = 56/60 -----------------------------------------------


def test_arith_plan_full_is_grid_lite_is_56_60():
    full = readplan.plan("arithmetic_intermediates")
    lite = readplan.plan("arithmetic_intermediates", reads="lite")
    assert len(full) == len(lite) == 596
    assert all(s.layers == readplan.GRID for s in full)
    assert all(s.lite_layers == [56, 60] and s.lite_positions == {"kind": "same"} for s in full)
    assert all(s.layers == [56, 60] for s in lite)
    assert all(s.positions["full"] == {"kind": "all_from_end"} for s in lite)
    assert all(s.positions["lite"] == {"kind": "same"} for s in lite)


def test_arith_full_default_judges_every_layer(tmp_path, monkeypatch):
    path = _write_rows(tmp_path / "r.jsonl", _grid_rows([GOLD_ID]))
    write_sidecar(path, plan_sha=reads.plan_sha("arithmetic_intermediates"))
    seen = _capture(monkeypatch)
    r = judge.run(_nargs(path, tmp_path / "o", extra={"cells": "all"}))
    assert r.config["layers_judged"] == readplan.GRID and len(seen) == 11
    assert r.config["prompt_version"] == PROMPT_VERSION_BATCH and "+reads" not in str(
        r.config["prompt_version"]
    )
    assert r.config["reads_checked"] == "sidecar" and not r.extras.get("partial_ids")
    assert set(r.extras["layer_protocols"]["band"]) == {20, 24, 28, 32, 36, 40, 44, 48, 52}
    # summary mode (the default; final r1): one numbers digest PER layer, keys merged
    fake = FakeLLM.install(monkeypatch, _value_judge([]), digest=_keyed("1"))
    rs = judge.run(summary_args(path, tmp_path / "s", PROMPT_VERSION, items=[GOLD_ID]))
    bundles = [u for n, _s, u in fake.calls if n == "digest"]
    assert len(bundles) == len(readplan.GRID)
    assert all(sum(f"[L{L} pos -1]" in b for b in bundles) == 1 for L in readplan.GRID)
    assert rs.config["layers_judged"] == readplan.GRID
    assert rs.config["prompt_version"] == digest.prompt_version(
        PROMPT_VERSION, rs_args := summary_args(path, tmp_path / "x", PROMPT_VERSION), judge.NAME
    )
    assert rs_args.extra.get("reads") is None


def test_arith_lite_reads_two_layers(tmp_path, monkeypatch):
    path = _write_rows(tmp_path / "r.jsonl", _grid_rows([GOLD_ID]))
    write_sidecar(path)
    seen = _capture(monkeypatch)
    r = judge.run(_nargs(path, tmp_path / "o", extra={"cells": "all", "reads": "lite"}))
    assert r.config["layers_judged"] == [56, 60] and len(seen) == 2
    assert all(c.meta["n_entries"] == len(SPAN) for c in seen)  # every position (same)
    assert r.config["prompt_version"].endswith("+reads-lite")
    FakeLLM.install(monkeypatch, _value_judge([]), digest=_keyed("1"))
    rs = judge.run(
        summary_args(path, tmp_path / "s", PROMPT_VERSION, items=[GOLD_ID], extra={"reads": "lite"})
    )
    assert rs.config["layers_judged"] == [56, 60]
    assert rs.config["prompt_version"].endswith("+reads-lite")


def test_arith_full_rejects_partial_span(tmp_path, monkeypatch):
    rows = [
        r
        for r in _grid_rows([GOLD_ID])
        if not (r["layer"] == 44 and r["pos"] < -10)  # L44 holds only 10 positions
    ]
    path = _write_rows(tmp_path / "r.jsonl", rows)
    write_sidecar(path)
    _capture(monkeypatch)
    with pytest.raises(SystemExit) as e:
        judge.run(_nargs(path, tmp_path / "o", extra={"cells": "all"}))
    assert e.value.code == 2
    r = judge.run(_nargs(path, tmp_path / "o2", allow_missing=True, extra={"cells": "all"}))
    assert GOLD_ID in r.extras["partial_ids"] and r.complete is False


def test_arith_full_rejects_56_60_only_file(tmp_path, monkeypatch, capsys):
    path = _write_rows(tmp_path / "r.jsonl", _grid_rows([GOLD_ID], layers=[56, 60]))
    side = write_sidecar(path, reads="full")
    _capture(monkeypatch)
    with pytest.raises(SystemExit) as e:
        judge.run(_nargs(path, tmp_path / "o", extra={"cells": "all"}))
    assert e.value.code == 2 and "[20" in capsys.readouterr().err
    side.unlink()
    r = judge.run(_nargs(path, tmp_path / "o2", extra={"cells": "all"}))
    assert r.config["reads_checked"] == "no_sidecar"
    assert GOLD_ID in r.extras["partial_ids_unenforced"]
    write_sidecar(path, reads="full")
    r = judge.run(_nargs(path, tmp_path / "o3", extra={"cells": "all", "reads": "lite"}))
    assert r.config["layers_judged"] == [56, 60] and not reads.incomplete(
        _nargs(path, tmp_path / "o3", extra={"cells": "all", "reads": "lite"})
    )
    assert not r.extras.get("partial_ids") and not r.extras.get("layers_missing")


def test_arith_lite_file_is_complete_over_the_bank(tmp_path, monkeypatch):
    """A whole-bank 56/60 file judged ``reads=lite`` is a complete result."""
    _h, items = load_bank(BANK)
    path = _write_rows(
        tmp_path / "r.jsonl", _grid_rows([it["id"] for it in items], layers=[56, 60])
    )
    write_sidecar(path)
    _capture(monkeypatch)
    r = judge.run(_nargs(path, tmp_path / "o", items=None, extra={"reads": "lite"}))
    assert r.complete is True and r.config["cells"] == "frozen" and r.extras["n_calls"] == 596


def test_arith_sidecar_lite_file_under_full_exits(tmp_path, monkeypatch):
    path = _write_rows(tmp_path / "r.jsonl", _grid_rows([GOLD_ID], layers=[56, 60]))
    write_sidecar(path, reads="lite")
    _capture(monkeypatch)
    with pytest.raises(SystemExit) as e:
        judge.run(_nargs(path, tmp_path / "o", extra={"cells": "all"}))
    assert e.value.code == 2


def test_arith_summary_single_layer_feeds_only_that_layer(tmp_path, monkeypatch):
    path = _write_rows(tmp_path / "r.jsonl", _grid_rows([GOLD_ID]))
    write_sidecar(path)
    fake = FakeLLM.install(monkeypatch, _value_judge([]), digest=_keyed("1"))
    r = judge.run(summary_args(path, tmp_path / "s", PROMPT_VERSION, items=[GOLD_ID], layers=[44]))
    bundle = next(u for n, _s, u in fake.calls if n == "digest")
    heads = set(re.findall(r"^\[L(\d+) pos", bundle, flags=re.M))
    assert heads == {"44"} and r.config["layers_judged"] == [44]
    assert not r.extras.get("layers_missing") and not r.extras.get("partial_ids")


def test_arith_all_layer_producer_file_is_judged(tmp_path, monkeypatch):
    """Late critique fix (1): plan_sha does not hash layers, so a producer file read at all 64
    layers (sidecar plan_sha of the 11-layer plan) is judged on every layer."""
    path = _write_rows(tmp_path / "r.jsonl", _grid_rows([GOLD_ID], layers=list(range(64))))
    write_sidecar(path, plan_sha=reads.plan_sha("arithmetic_intermediates"))
    seen = _capture(monkeypatch)
    r = judge.run(_nargs(path, tmp_path / "o", extra={"cells": "all"}))
    assert r.config["layers_judged"] == list(range(64)) and len(seen) == 64
    write_sidecar(path, plan_sha="0" * 64)  # a different plan: guard (iii)
    with pytest.raises(SystemExit):
        judge.run(_nargs(path, tmp_path / "o2", extra={"cells": "all"}))


# C5: neutral wording, token note, task note ---------------------------------------------


def test_arith_task_note_has_no_numerals():
    from wsbench import numerals
    from wsbench.evals.arithmetic_intermediates import SPEC

    note = SPEC.task_note
    assert note == arith_prompts.TASK_NOTE and note.strip()
    assert not re.search(r"\d", note) and not numerals.numbers_in(note)
    for w in ("one", "two", "three", "four", "single", "pair", "twice"):
        assert not re.search(rf"\b{w}\b", note), w


def test_arith_prompts_render_the_spec_token_note():
    from wsbench import mc
    from wsbench.evals.arithmetic_intermediates import SPEC

    note = mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)
    assert SPEC.flat_types == ("numbers",) and SPEC.multi_select is False
    assert note == arith_prompts.TOKEN_NOTE == digest.token_note_of(SPEC.name)
    for text in (arith_prompts.SYSTEM, arith_prompts.SYSTEM_BATCH, arith_prompts.SYSTEM_SUMMARY):
        assert note in text and arith_prompts.NO_ASSEMBLY in text
        assert "tight cluster" not in text and "lens" not in text.lower()
        assert mc.READOUT_PHRASE in text
    # the batched "judge every entry on its own" rule names the token-note exception
    flat = " ".join(arith_prompts.SYSTEM_BATCH.split())
    assert "Judge every entry on its own" in flat
    assert "The one exception is the token-list note below" in flat
    assert "never to assemble a number" in flat
    assert SPEC.min_full_positions == 34 and SPEC.full_contiguous is True


# C6: token quotes with scores -----------------------------------------------------------


def test_arith_quote_must_write_the_named_value():
    # plan 0036 C6: a verbatim quote holding SOME number word does not vouch for another value
    text = "The model is computing something; this is one way to see it."
    assert not judge.verified(135.0, text, "one way")
    v = judge.verdict({"values": [135], "basis": "t", "quote": "one way"}, 135.0, "exact", [], text)
    assert v["kind"] == "unverified" and not v["hit"]
    assert judge.verified(1.0, text, "one way")  # it does vouch for the value it writes
    t2 = "it comes to one hundred thirty-five, or minus fifty-one before that"
    assert judge.verified(-51.0, t2, "minus fifty-one before")
    assert not judge._quote_vouches("minus fifty-one before", 51.0)
    # quotes that do write the value (cases from the 2026-10-30 ATI panel re-gate)
    t3 = "determining that 245 minus 299 equals negative 54."
    assert judge.verified(-54.0, t3, "245 minus 299 equals negative 54")
    assert not judge._quote_vouches("245 minus 299 equals negative 54", 54.0)  # sign kept
    t4 = "The model is calculating the simplified fraction 23/13 to prepare"
    assert judge.verified(23 / 13, t4, "the simplified fraction 23/13")
    assert not judge.verified(13 / 23, t4, "the simplified fraction 23/13")
    assert judge.verified(23 / 13, "结果是十三分之二十三。", "结果是十三分之二十三")
    assert judge.verified(3.5, "大约三点五左右", "大约三点五")


def test_arith_token_quote_with_score_verifies():
    cell = Cell("x", 56, -1, None, ("九", "nine"), (15.19, 14.10))
    lines = [u[1] for u in judge.units_of_cell(cell)]
    v = judge.verdict(
        {"values": [9], "basis": "numeral_bag", "quote": "九 (15.19)"}, 9.0, "exact", [], "",
        lines=lines,
    )  # fmt: skip
    assert v["kept"] == [9.0] and v["hit"]
    # a made-up score never verifies
    v = judge.verdict(
        {"values": [9], "basis": "numeral_bag", "quote": "九 (99.00)"}, 9.0, "exact", [], "",
        lines=lines,
    )  # fmt: skip
    assert v["kept"] == []
    # the native prompt shows the bag without scores
    assert judge.judged_text(cell, "tokens10") == "九 | nine"


# C7: digits never assembled; flat-list void ---------------------------------------------


def _tok_rows(item, layer, toks_by_pos):
    return [
        {"id": item, "layer": layer, "pos": p, "tokens": list(t), "scores": [1.0] * len(t)}
        for p, t in toks_by_pos.items()
    ]


def test_arith_digits_never_assembled_into_a_number(tmp_path, monkeypatch):
    rows = _tok_rows(GOLD_ID, 56, {-3: ["1"], -2: ["3"], -1: ["5"]})
    rows += _tok_rows(GOLD_ID, 60, {-1: ["7", "x"]})
    path = _write_rows(tmp_path / "r.jsonl", rows)
    _capture(monkeypatch, _batch_hit([GOLD], "135"))
    r = judge.run(_nargs(path, tmp_path / "o", extra={"cells": "all"}))
    assert r.rows[0]["pass"] is False and r.rows[0]["kept"] == []
    # the shared quote_ok would read "135" as a word split across the three positions; the
    # family's no-assembly rule (one unit, never a bare number) refuses it
    cells = [Cell(GOLD_ID, 56, p, None, (t,), (1.0,)) for p, t in ((-3, "1"), (-2, "3"), (-1, "5"))]
    units = [u for c in cells for u in judge.units_of_cell(c)]
    assert digest.quote_ok("135", [u[1] for u in units])
    assert not any(judge.supports(GOLD, u, "135", top=True) for u in units)
    FakeLLM.install(monkeypatch, _value_judge([GOLD], "135"), digest=_keyed("135"))
    r = judge.run(summary_args(path, tmp_path / "s", PROMPT_VERSION, items=[GOLD_ID]))
    assert r.rows[0]["pass"] is False and r.rows[0]["kept"] == []


def test_arith_flood_line_singles_out_nothing(tmp_path, monkeypatch):
    def run_tokens(toks, out):
        path = _write_rows(tmp_path / f"{out}.jsonl", _tok_rows(GOLD_ID, 56, {-1: toks}))
        _capture(monkeypatch, _batch_hit([GOLD]))
        return judge.run(_nargs(path, tmp_path / out, extra={"cells": "all"}))

    r = run_tokens(["135", "6", "8", "7", "11", "9"], "flood")
    assert r.rows[0]["pass"] is False and r.extras["n_flood_voided"] == 1
    assert r.extras["value_before_flood_void"] == 1.0
    r = run_tokens(["135", "6"], "two")
    assert r.rows[0]["pass"] is True and r.extras["n_flood_voided"] == 0
    rows = [{"id": GOLD_ID, "layer": 56, "pos": -1, "samples": ["135, 6, 8, 7, 11 and 9"]}]
    path = _write_rows(tmp_path / "p.jsonl", rows)
    _capture(monkeypatch, _batch_hit([GOLD]))
    r = judge.run(_nargs(path, tmp_path / "p", extra={"cells": "all"}))
    assert r.rows[0]["pass"] is False and r.extras["n_flood_voided"] == 1


def test_arith_flood_void_not_bypassed_by_other_number_quote():
    # summary mode: 135's only numeral support is a flood list; a quote "one way" from another,
    # non-flood line wrote 1, not 135, so it is no support and the void stands
    lines = digest.native_lines(
        [
            Cell(GOLD_ID, 56, -1, ("135, 6, 8, 7, 11 and 9",), None, None),
            Cell(GOLD_ID, 60, -1, ("this is one way to see it",), None, None),
        ]
    )
    assert digest.number_flood(lines[0]) and not digest.number_flood(lines[1])
    v = judge.verdict(
        {"values": [GOLD], "basis": "t", "quote": "one way"},
        GOLD,
        "exact",
        [],
        "",
        keys=["135"],
        lines=lines,
    )
    assert v["kind"] == "flood" and not v["hit"]


def _prose_both_modes(tmp_path, monkeypatch, sample: str, tag: str):
    rows = [{"id": GOLD_ID, "layer": 56, "pos": -1, "samples": [sample]}]
    path = _write_rows(tmp_path / f"{tag}.jsonl", rows)
    write_sidecar(path, sampling="prose1", reads="lite")
    _capture(monkeypatch, _batch_hit([GOLD]))
    nat = judge.run(
        _nargs(path, tmp_path / f"{tag}-n", layers=[56], extra={"cells": "all", "reads": "lite"})
    )
    FakeLLM.install(monkeypatch, _value_judge([GOLD]), digest=_keyed("135"))
    summ = judge.run(
        summary_args(
            path, tmp_path / f"{tag}-s", PROMPT_VERSION, items=[GOLD_ID], layers=[56], extra=LITE
        )
    )
    return nat, summ


def test_arith_bulleted_number_list_is_voided(tmp_path, monkeypatch):
    for r in _prose_both_modes(tmp_path, monkeypatch, "- 12\n- 15\n- 135\n- 19\n- 23", "five"):
        assert r.rows[0]["pass"] is False and r.extras["n_flood_voided"] == 1
        assert r.extras["value_before_flood_void"] == 1.0
    for r in _prose_both_modes(tmp_path, monkeypatch, "- 12\n- 15\n- 135\n- 19", "four"):
        assert r.rows[0]["pass"] is True and r.extras["n_flood_voided"] == 0


def test_arith_worked_multistep_prose_is_kept(tmp_path, monkeypatch):
    sample = "- 138 \u2212 3 = 135, then 135 \u00d7 4 = 540, minus 7 gives 533\n- subtraction"
    ln = digest.native_lines([Cell(GOLD_ID, 56, -1, (sample,), None, None)])[0]
    assert ln.text.count(digest.BULLET_MARK.strip()) == 1 and not digest.number_flood(ln)
    for r in _prose_both_modes(tmp_path, monkeypatch, sample, "worked"):
        assert r.rows[0]["pass"] is True and r.extras["n_flood_voided"] == 0

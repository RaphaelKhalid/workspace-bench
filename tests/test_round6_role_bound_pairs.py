"""Review of #202 round 5, finding 1: role_bound_association scored by direction pairs (pair-v1).

Every story is a stereotyped pair and act told once per direction (``-ab`` / ``-ba``) with the
SAME option lists, so a guesser that picks the canonical triple passes one direction and fails
the other: per item the oa-v3.1 guessers read 0.116 / 0.148 / 0.226 against uniform 0.008 (the
MC leakage standard's line is 0.058). The headline unit is now the pair: it passes only when
BOTH directions pass. Tests in both directions:

- too lenient (still fails): one direction right is no pass, in the scorer, the summary-mode
  extractor, the shared-id floor and the lucky-guessing rule; a guesser that gets the direction
  right on both sides is still caught by the standard;
- too strict (now passes): both directions right passes; the frozen guessers sit within the
  standard's 5 points under the pair rule.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from wsbench import results
from wsbench.baselines import lucky_guessing as lg
from wsbench.evals.role_bound_association import score
from wsbench.mcjudge import load_bank
from wsbench.registry import JudgeArgs

ROOT = Path(__file__).resolve().parents[1]
AB, BA = "oa-police-thief-chase-ab", "oa-police-thief-chase-ba"
HAB, HBA = "oa-child-grandparent-hug-ab", "oa-child-grandparent-hug-ba"


def _cmp():
    name = "summary_mode_compare_r6"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, ROOT / "scripts/summary_mode_compare.py"
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def _scope(*ids: str) -> list[dict]:
    bank = {it["id"]: it for it in load_bank("role_bound_association")}
    return [bank[i] for i in ids]


def _args(tmp_path: Path) -> JudgeArgs:
    from wsbench.judge_config import JudgeConfig, resolve

    return JudgeArgs(
        readouts=tmp_path / "r.jsonl",
        out=tmp_path / "o",
        judge=resolve(JudgeConfig(), env={}),
        layers=None,
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
    )


def _score(tmp_path: Path, scope: list[dict], passing: set[str], undecided=frozenset()):
    rows = [
        {"id": it["id"], "layer": 44, "pos": 0, "pass": it["id"] in passing, "correct": []}
        for it in scope
    ]
    counts = {"n_expected_cells": len(rows), "n_unjudged_cells": 0, "n_empty_cells": 0}
    return score.score(
        _args(tmp_path), scope, rows, counts=counts, config={}, n_api_failed=0,
        undecided=undecided,
    )  # fmt: skip


# ---------------------------------------------------------------- the scorer


def test_one_direction_right_is_not_a_pass(tmp_path):
    # too lenient before: the stereotyped (congruent) direction alone scored 0.5 per item
    scope = _scope(AB, BA, HAB, HBA)
    r = _score(tmp_path, scope, {AB, HAB})
    assert r.extras["item_pass_rate"] == 0.5  # the old headline, kept as a column
    assert r.value == 0.0 and r.extras["n_pairs_pass"] == 0 and r.extras["n_pairs_decided"] == 2
    assert r.extras["item_rule"] == score.ITEM_RULE == "pair-v1"


def test_both_directions_right_passes(tmp_path):
    scope = _scope(AB, BA, HAB, HBA)
    assert _score(tmp_path, scope, {AB, BA}).value == 0.5  # one pair of two
    assert _score(tmp_path, scope, {AB, BA, HAB, HBA}).value == 1.0


def test_an_undecided_or_missing_direction_leaves_the_pair_undecided(tmp_path):
    scope = _scope(AB, BA, HAB, HBA)
    r = _score(tmp_path, scope, {AB, BA, HAB}, undecided={HBA})
    assert r.value == 1.0 and r.extras["n_pairs_decided"] == 1  # never a fail, never a pass
    # a one-direction scope decides no pair
    assert _score(tmp_path, _scope(AB), {AB}).value is None


def test_summary_chance_is_the_pair_chance(tmp_path):
    rows = [{"id": i, "layer": 44, "pos": 0, "pass": False, "correct": []} for i in (AB, BA)]
    counts = {"n_expected_cells": 2, "n_unjudged_cells": 0, "n_empty_cells": 0}
    r = score.score(
        _args(tmp_path), _scope(AB, BA), rows, counts=counts, config={}, n_api_failed=0,
        summary={},
    )  # fmt: skip
    assert r.chance == pytest.approx(((1 / 6) ** 3) ** 2)


# ---------------------------------------------------------------- extractor and shared ids


def _res(scope: list[dict], passing: set[str], value: float | None) -> dict:
    rows = [{"id": it["id"], "pass": it["id"] in passing} for it in scope]
    return {"n_items": len(scope), "rows": rows, "numbers": {"value": value}, "config": {}}


def test_extractor_reads_pairs():
    cmp = _cmp()
    scope = _scope(AB, BA, HAB, HBA)
    # too lenient: the per-item reading (0.5) is now an extractor mismatch
    assert cmp.check_extractor(cmp.ROLE, _res(scope, {AB, HAB}, 0.5)) != []
    assert cmp.check_extractor(cmp.ROLE, _res(scope, {AB, HAB}, 0.0)) == []
    # too strict would be to fail a pair whose two directions pass
    assert cmp.item_verdicts(cmp.ROLE, _res(scope, {AB, BA}, 0.5)) == {
        "oa-police-thief-chase": True,
        "oa-child-grandparent-hug": False,
    }
    assert cmp.check_extractor(cmp.ROLE, _res(scope, {AB, BA}, 0.5)) == []
    # an unsummarized direction leaves its pair undecided, as in score.pair_verdicts
    res = _res(scope, {AB, BA}, 1.0)
    res["rows"][3]["summary_state"] = "unsummarized"
    assert cmp.item_verdicts(cmp.ROLE, res)["oa-child-grandparent-hug"] is None
    assert cmp.check_extractor(cmp.ROLE, res) == []


def test_shared_floor_folds_to_pairs():
    assert results.fold_direction_pairs({AB: True, BA: False, HAB: True, HBA: True}) == {
        "oa-police-thief-chase": False,
        "oa-child-grandparent-hug": True,
    }
    assert results.fold_direction_pairs({AB: True}) == {}  # one direction: undecided


# ---------------------------------------------------------------- the lucky-guessing rule


def _per_item(items, right) -> dict:
    """Five draws per item; ``right(item)`` = how many are correct."""
    return {it.id: {"draws": [{"correct": d < right(it)} for d in range(5)]} for it in items}


def test_a_stereotype_guesser_scores_zero_under_the_pair_rule():
    items = lg.build_family("role_bound_association")
    assert len(lg.direction_pairs(items)) == 50
    # right on every congruent direction, wrong on its twin: 0.5 per item, 0 per pair
    ster = _per_item(items, lambda it: 5 if it.meta["direction"] == "ab" else 0)
    assert lg.pair_rule(ster, items) == 0.0
    # too lenient the other way: a guesser right on BOTH directions is still a full pass
    both = _per_item(items, lambda it: 5)
    assert lg.pair_rule(both, items) == 1.0
    # independent draws: p_ab * p_ba
    half = _per_item(items, lambda it: 3 if it.meta["direction"] == "ab" else 2)
    assert lg.pair_rule(half, items) == pytest.approx(0.6 * 0.4)


def test_pair_chance_is_the_product_of_the_floors():
    items = lg.build_family("role_bound_association")
    fam = lg.family_chance("role_bound_association", items)
    assert fam == pytest.approx(lg.analytic_floor(items) ** 2, rel=0.2)
    assert fam < 1e-3 < lg.analytic_floor(items)


def test_standard_reads_role_bound_under_the_pair_rule():
    # a leaking guesser (direction right on both sides) fails; a stereotype guesser passes
    leak = {"mean": 0.3, "analytic_floor": 0.008, "family_rule": 0.2, "family_chance": 6.4e-5}
    ster = {"mean": 0.25, "analytic_floor": 0.008, "family_rule": 0.0, "family_chance": 6.4e-5}
    (row,) = lg.standard("role_bound_association", {"topic": leak})
    assert row["rule"] == "family_rule" and not row["pass"]
    (row,) = lg.standard("role_bound_association", {"topic": ster})
    assert row["pass"]
    # an entry without the pair rule must be re-measured, never read per item
    with pytest.raises(ValueError, match="re-measure"):
        lg.standard("role_bound_association", {"blind": {"mean": 0.1, "analytic_floor": 0.008}})


def test_frozen_role_bound_floors_meet_the_standard_under_the_pair_rule():
    e = lg.floors()["role_bound_association"]
    rows = lg.standard("role_bound_association", e)
    assert {r["variant"] for r in rows} == {"blind", "described", "topic"}
    assert all(r["rule"] == "family_rule" and r["pass"] for r in rows), rows
    # the per-item leak is still there and still visible: every guesser fails the per-item line
    for v in ("blind", "described", "topic"):
        assert e[v]["mean"] > e[v]["analytic_floor"] + lg.STANDARD_POINTS

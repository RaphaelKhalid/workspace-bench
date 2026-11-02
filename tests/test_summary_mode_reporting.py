"""Summary mode (plan 0020) reporting: completeness over items, the † marker, floors, the
summary macro, and the runner's native-only stamp."""

from types import SimpleNamespace

import pytest

from wsbench import digest, runner
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.registry import EvalSpec
from wsbench.results import SUMMARY_LEGEND, FamilyResult, completeness, macro, markdown_table


def _r(family: str, value: float, aggregate: str | None) -> FamilyResult:
    cfg = {"judge_model": "m", "prompt_version": "pv"}
    if aggregate:
        cfg["aggregate"] = aggregate
    return FamilyResult(
        family=family,
        metric="pass_rate",
        value=value,
        ci95=None,
        n_items=100,
        higher_is_better=True,
        chance=None,
        chance_label=None,
        complete=True,
        pinned_instrument=True,
        config=cfg,
        counts={},
    )


def test_completeness_items_denominator():
    base = {"pinned": True, "subset": False, "n_missing": 0, "n_unjudged": 0}
    # 10 empty items of 100: incomplete against items, complete against 1100 cells
    assert completeness(**base, n_expected=1100, n_empty=10)
    assert not completeness(**base, n_expected=1100, n_empty=10, n_items=100)
    assert completeness(**base, n_expected=1100, n_empty=5, n_items=100)


def test_markdown_dagger_floors_and_legend():
    rows = [_r("a", 0.5, "summary"), _r("b", 0.4, None)]
    md = markdown_table(rows, None, floors={"lucky": {"a": "0.10", "b": "0.20"}})
    line_a = next(ln for ln in md.splitlines() if ln.startswith("| a †"))
    line_b = next(ln for ln in md.splitlines() if ln.startswith("| b |"))
    assert "0.10" not in line_a and "— |" in line_a and "0.20" in line_b
    assert md.rstrip().endswith(SUMMARY_LEGEND)  # plan 0024 reworded the legend
    assert SUMMARY_LEGEND.startswith("† summarize-then-judge (one judged summary per item")
    assert "†" not in markdown_table([_r("b", 0.4, None)], None)


def test_summary_macro_excludes_native_rows():
    m = macro(
        [_r("a", 0.6, "summary"), _r("b", 0.2, "native")],
        superseded={},
        held_out={},
        removed={},
    )
    assert m["value"] == 0.6 and m["families"] == ["a"]
    assert m["excluded"] == [{"family": "b", "reason": "native under aggregate=summary"}]
    plain = macro([_r("a", 0.6, None), _r("b", 0.2, None)], superseded={}, held_out={}, removed={})
    assert plain["value"] == pytest.approx(0.4)


def _spec(name: str, result: FamilyResult) -> EvalSpec:
    return EvalSpec(
        name=name,
        title=name,
        group="basic",
        bank=None,  # type: ignore[arg-type]
        judge=JudgeConfig(prompt_version="pv"),
        metric="pass_rate",
        higher_is_better=True,
        run=lambda args: result,
    )


def _opts() -> SimpleNamespace:
    return SimpleNamespace(
        items=None,
        layers=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        anti_text_inversion=False,
    )


def test_runner_stamps_native_only_and_fails_unhooked(tmp_path):
    judge = resolve(JudgeConfig(prompt_version="pv"))
    opts = {"aggregate": "summary"}
    r = runner.judge_family(
        _spec("jlens_concept_pr", _r("jlens_concept_pr", 0.1, None)),
        _opts(),
        tmp_path / "x.jsonl",
        tmp_path / "o1",
        judge=judge,
        opts=opts,
    )
    assert r.config["aggregate"] == "native"
    assert r.extras["summary_mode_note"] == digest.NATIVE_ONLY["jlens_concept_pr"]
    with pytest.raises(SystemExit) as e:
        runner.judge_family(
            _spec("not_a_hooked_family", _r("x", 0.1, None)),
            _opts(),
            tmp_path / "x.jsonl",
            tmp_path / "o2",
            judge=judge,
            opts=opts,
        )
    assert e.value.code == 2
    native = runner.judge_family(
        _spec("jlens_concept_pr", _r("jlens_concept_pr", 0.1, None)),
        _opts(),
        tmp_path / "x.jsonl",
        tmp_path / "o3",
        judge=judge,
        opts={},
    )
    assert "aggregate" not in native.config


def test_parse_opts_validates_summary_options():
    assert runner.parse_opts(["aggregate=summary", "summ_variant=task"])["summ_variant"] == "task"
    with pytest.raises(SystemExit):
        runner.parse_opts(["aggregate=summary", "summ_render=bogus"])
    with pytest.raises(SystemExit):
        runner.parse_opts(["aggregate=everything"])

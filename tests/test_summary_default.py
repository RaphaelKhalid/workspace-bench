"""Plan 0024: summary mode is the benchmark default; ``opts=aggregate=native`` opts out."""

import json
from pathlib import Path

import pytest

from wsbench import digest, registry
from wsbench.baselines import prompt_only as po
from wsbench.baselines import text_inversion
from wsbench.cli import main
from wsbench.judge_config import DEFAULT_JUDGE, JudgeConfig, resolve
from wsbench.registry import JudgeArgs
from wsbench.results import FamilyResult, markdown_table, write_results
from wsbench.runner import parse_opts

REPO = Path(__file__).resolve().parents[1]
MT_EXAMPLE = REPO / "examples/readouts/multilingual_mt.jsonl"
BR_EXAMPLE = REPO / "examples/readouts/basic_readout.jsonl"


def test_parse_opts_defaults_to_summary():
    assert digest.DEFAULT_AGGREGATE == "summary"
    assert parse_opts([])["aggregate"] == "summary"
    assert parse_opts(["aggregate=native"])["aggregate"] == "native"
    assert parse_opts(["cells=all"]) == {"cells": "all", "aggregate": "summary"}
    with pytest.raises(SystemExit):
        parse_opts(["aggregate=pooled"])
    # plan 0032 §2.5.1: a family called directly runs summary too (the library default); a
    # test that means native says so (conftest.native_args)
    args = JudgeArgs(
        readouts=None,  # type: ignore[arg-type]
        out=None,  # type: ignore[arg-type]
        judge=None,  # type: ignore[arg-type]
        layers=None,
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=True,
        extra={},
    )
    assert digest.summary_mode(args) is True


def test_cli_with_no_opts_runs_summary_and_records_it(tmp_path, monkeypatch, capsys):
    from wsbench.evals.basic_readout import SPEC

    registry.FAMILIES.setdefault(SPEC.name, SPEC)
    monkeypatch.delenv("WSBENCH_JUDGE_MODEL", raising=False)
    out = tmp_path / "out"
    argv = [
        "run",
        "families=basic_readout",
        f"readouts_root={BR_EXAMPLE.parent}",
        f"out={out}",
        "dry_run=True",
        "allow_missing=True",
    ]
    assert main(argv) == 0
    assert "digest prompt for" in capsys.readouterr().out  # the summarizer is the first step
    assert json.loads((out / "run.json").read_text())["aggregate"] == "summary"
    assert main([*argv, "opts=aggregate=native"]) == 0
    assert "digest prompt for" not in capsys.readouterr().out
    assert json.loads((out / "run.json").read_text())["aggregate"] == "native"


def test_native_opt_out_is_the_pre_0024_run(tmp_path, monkeypatch):
    """``opts=aggregate=native`` through the CLI writes exactly what the family's own (native)
    rule writes when called directly with no aggregate, as every run did before plan 0024."""
    from wsbench.evals.multilingual_mt import SPEC

    registry.FAMILIES.setdefault(SPEC.name, SPEC)
    monkeypatch.delenv("WSBENCH_JUDGE_MODEL", raising=False)
    cli_out = tmp_path / "cli"
    rc = main(
        [
            "judge",
            "family=multilingual_mt",
            f"readouts={MT_EXAMPLE}",
            f"out={cli_out}",
            "opts=aggregate=native",
            "allow_missing=True",
        ]
    )
    assert rc == 0
    direct_out = tmp_path / "direct"
    direct_out.mkdir()
    res = SPEC.run(
        JudgeArgs(
            readouts=MT_EXAMPLE,
            out=direct_out,
            judge=resolve(SPEC.judge),
            layers=None,
            items=None,
            limit=0,
            allow_missing=True,
            concurrency=16,
            rpm=600.0,
            dry_run=False,
            aux_models=SPEC.judge.aux_models,
            extra={"aggregate": "native"},  # plan 0032: native is now the explicit opt-out
        )
    )
    write_results(direct_out, res)
    a = json.loads((cli_out / "results.json").read_text())
    b = json.loads((direct_out / "results.json").read_text())
    assert a["config"].get("aggregate", "native") == "native"
    assert a["rows"] == b["rows"] and a["numbers"] == b["numbers"] and a["counts"] == b["counts"]


def test_mode_change_warns(tmp_path, capsys):
    from wsbench.runner import warn_mode_change

    out = tmp_path / "fam"
    out.mkdir()
    (out / "results.json").write_text(json.dumps({"config": {"aggregate": "native"}}))
    warn_mode_change(out, "summary", "fam")
    assert "aggregate=native result" in capsys.readouterr().err
    warn_mode_change(out, "native", "fam")
    assert capsys.readouterr().err == ""


def test_ati_gate_refuses_summary_verdicts(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps({"family": "association", "config": {"aggregate": "summary"}}))
    with pytest.raises(ValueError, match="aggregate=native"):
        text_inversion.draw_verdicts(p)


def _result(family: str, pv: str, aggregate: str | None, summarizer: dict | None = None):
    cfg: dict = {"judge_model": DEFAULT_JUDGE, "prompt_version": pv, "layers_judged": [20]}
    if aggregate:
        cfg["aggregate"] = aggregate
    if summarizer is not None:
        cfg["summarizer"] = summarizer
    return FamilyResult(
        family=family,
        metric="pass_rate",
        value=0.4,
        ci95=(0.3, 0.5),
        n_items=100,
        higher_is_better=True,
        chance=None,
        chance_label=None,
        complete=True,
        pinned_instrument=True,
        config=cfg,
        counts={
            "n_expected_cells": 100,
            "n_missing_cells": 0,
            "n_unjudged_cells": 0,
            "n_empty_cells": 0,
        },
        extras={},
        rows=[],
    )


SUMM = {"model": "claude-opus-5-5", "max_items": 10, "concurrency": None, "timeout": None}


def test_freeze_routes_summary_runs_and_refuses_mixed(tmp_path, monkeypatch, real_families):
    base = po.instrument_versions()["association"]
    spv = f"{base}+digest-v4-task-extractive+sj-v9"
    run = tmp_path / "run"
    write_results(run / "association", _result("association", spv, "summary", SUMM))
    monkeypatch.setattr(po, "FROZEN_SUMMARY", tmp_path / "po_summary.json")
    assert po.default_dst(run) == tmp_path / "po_summary.json"
    frozen = po.freeze(run)
    e = frozen["association"]
    assert e["aggregate"] == "summary" and e["instrument"] == spv
    assert e["summarizer"] == {"model": "claude-opus-5-5", "max_items": 10}  # throughput dropped
    assert (tmp_path / "po_summary.json").exists()
    # a summary run judged on another base instrument is refused
    write_results(run / "association", _result("association", "old+digest-v1", "summary", SUMM))
    with pytest.raises(ValueError, match="re-judge first"):
        po.freeze(run)
    # mixing modes is refused
    write_results(run / "association", _result("association", spv, "summary", SUMM))
    write_results(run / "basic_readout", _result("basic_readout", "x", "native"))
    with pytest.raises(ValueError, match="mixes aggregate modes"):
        po.freeze(run)


def test_summary_rows_draw_only_their_own_summary_floor():
    spv = "bank-x+digest-v4-task-extractive+sj-v9"
    entry = {
        "rate": 0.31,
        "instrument": spv,
        "judge_model": DEFAULT_JUDGE,
        "summarizer": {"model": "claude-opus-5-5", "max_items": 10},
    }
    same = _result("association", spv, "summary", SUMM)
    other = _result("association", spv, "summary", {**SUMM, "max_items": 25})
    native = _result("association", "bank-x", None)
    cols = {"prompt-only": {"association": "0.32"}}
    summ = {"prompt-only": {"association": (entry, "0.310")}}
    md = markdown_table([same], None, floors=cols, summary_floors=summ)
    assert "| 0.310 |" in md
    md = markdown_table([other], None, floors=cols, summary_floors=summ)
    assert "0.310" not in md and "match the frozen summary floor" in md  # withheld + legend
    assert po.summary_floor_applies(entry, same.config)
    assert not po.summary_floor_applies(entry, native.config)
    # without summary floors a summary row still shows none (plan 0020 behaviour)
    assert "0.32" not in markdown_table([same], None, floors=cols).split("\n")[2]


def test_unhooked_family_fails_under_the_default(tmp_path, monkeypatch):
    """Plan 0024 Rev 1 #2: a family with neither a summary path nor a NATIVE_ONLY entry exits 2."""
    from wsbench.registry import EvalSpec, register

    def run(args: JudgeArgs) -> FamilyResult:
        return _result("unhooked24", "pv", None)

    register(
        EvalSpec(
            name="unhooked24",
            title="Unhooked",
            group="logic",
            bank=Path("evals/stub/items.json"),
            judge=JudgeConfig(prompt_version="pv"),
            metric="pass_rate",
            higher_is_better=True,
            run=run,
        )
    )
    monkeypatch.setattr("wsbench.llm.preflight", lambda model, reasoning: None)
    readouts = tmp_path / "r.jsonl"
    readouts.write_text("")
    argv = ["judge", "family=unhooked24", f"readouts={readouts}", f"out={tmp_path / 'o'}"]
    with pytest.raises(SystemExit) as e:
        main(argv)
    assert e.value.code == 2
    assert main([*argv, "opts=aggregate=native"]) == 0


def test_freeze_refuses_a_dst_of_the_other_mode(tmp_path, monkeypatch, real_families):
    base = po.instrument_versions()["association"]
    run = tmp_path / "run"
    spv = f"{base}+digest-v4-task-extractive+sj-v9"
    write_results(run / "association", _result("association", spv, "summary", SUMM))
    monkeypatch.setattr(po, "FROZEN", tmp_path / "po.json")
    monkeypatch.setattr(po, "FROZEN_SUMMARY", tmp_path / "po_summary.json")
    with pytest.raises(ValueError, match="other mode"):
        po.freeze(run, tmp_path / "po.json")
    assert "association" in po.freeze(run, tmp_path / "custom.json")  # any other dst is the user's


# ---------------------------------------------------------------- plan 0032 §2.5


def test_native_only_is_exactly(real_families):
    """NATIVE_ONLY = {jlens_concept_pr} (decision Q2); hallucination left WorkspaceBench (plan
    0040), so there is no other exception."""
    assert set(digest.NATIVE_ONLY) == {"jlens_concept_pr"}
    assert "unverbalized_hint" not in digest.NATIVE_ONLY


def test_library_default_is_summary():
    args = JudgeArgs(
        readouts=None,  # type: ignore[arg-type]
        out=None,  # type: ignore[arg-type]
        judge=None,  # type: ignore[arg-type]
        layers=None,
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=True,
        extra={},
    )
    assert digest.summary_mode(args) is True
    assert digest.summary_mode(dataclasses_replace(args, extra={"aggregate": "native"})) is False


def dataclasses_replace(args, **kw):
    import dataclasses

    return dataclasses.replace(args, **kw)


def test_every_registered_family_is_summary_or_native_only(tmp_path, real_families):
    """Every registered family either has a summary hook (its dry run under the summary default
    prints a digest prompt) or is NATIVE_ONLY with a reason."""
    ex = REPO / "examples/readouts"
    for name, spec in sorted(real_families.items()):
        if name in digest.NATIVE_ONLY:
            assert digest.NATIVE_ONLY[name].startswith("native:"), name
            continue
        path = ex / f"{name}.jsonl"
        if not path.exists():  # no toy file: one synthetic prose cell for the first plan row
            from wsbench import readplan

            first = readplan.plan(name)[0]
            path = tmp_path / f"{name}.jsonl"
            row = {"id": first.id, "layer": 44, "pos": -1, "samples": ["x"]}
            path.write_text(json.dumps(row) + "\n")
        r = spec.run(
            JudgeArgs(
                readouts=path,
                out=tmp_path / name,
                judge=resolve(spec.judge),
                layers=None,
                items=None,
                limit=0,
                allow_missing=True,
                concurrency=1,
                rpm=1e9,
                dry_run=True,
                aux_models=spec.judge.aux_models,
                extra={"aggregate": "summary"},
            )
        )
        assert r.config.get("aggregate") == "summary", name

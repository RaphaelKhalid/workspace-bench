"""scripts/audit_run.py (gpu.md G9; plan 0032 late fix 2): the mechanical run audit."""

import importlib.util
import json
from pathlib import Path

from wsbench import digest, reads, registry

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_run.py"
_spec = importlib.util.spec_from_file_location("audit_run", SCRIPT)
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)  # type: ignore[union-attr]


def _write(root: Path, family: str, mode: str = "full", **cfg_over) -> Path:
    spec = registry._spec_for_bank(family)
    probe = digest._probe({"aggregate": "summary"})
    pv = digest.prompt_version(spec.judge.prompt_version, probe)
    cfg = {
        **digest.config(probe, "prose", family),
        "prompt_version": reads.stamp(pv, mode),
        "reads": mode,
        "reads_checked": "sidecar",
        "sampling_source": "declared",
        **({"lite_rule": reads.lite_rule_of(reads.specs(family))} if mode == "lite" else {}),
        **cfg_over,
    }
    d = root / family
    d.mkdir(parents=True)
    res = {
        "family": family,
        "complete": True,
        "config": cfg,
        "numbers": {"extras": {"summary": {"n_readouts_in": 5, "n_readouts_bundled": 5}}},
    }
    (d / "results.json").write_text(json.dumps(res))
    return d


def test_a_clean_run_passes(tmp_path):
    assert ar.audit_family(_write(tmp_path / "a", "moral_rationale"))["ok"]
    assert ar.audit_family(_write(tmp_path / "b", "moral_rationale", "lite"))["ok"]


def test_lite_rule_is_checked(tmp_path):
    d = _write(
        tmp_path,
        "moral_rationale",
        "lite",
        lite_rule=json.dumps([{"positions": {"kind": "final_token"}, "layers": None}]),
    )
    r = ar.audit_family(d)
    assert not r["ok"] and "frozen plan rule" in r["problems"][0]


def test_undeclared_and_stale_fail(tmp_path):
    r = ar.audit_family(
        _write(tmp_path, "moral_rationale", sampling_source="default", prompt_version="old")
    )
    assert not r["ok"] and len(r["problems"]) == 2
    assert ar.main(["--judged", str(tmp_path)]) == 1


def test_floor_and_ati_instruments_are_reported(tmp_path):
    # plan 0046 (moral, SHARED_API r3): reported, never failed: a moral row on the ec-v4
    # instrument has no ec-v3 floor / ATI entry until gpu R6 / R8 re-measure them
    r = ar.audit_family(_write(tmp_path / "s", "moral_rationale"))
    assert r["ok"] and r["ati"] == "n/a"
    assert r["floor"] == "none" or r["floor"].startswith(("applies", "no floor"))
    # the frozen entry's instrument (ec-v5c since the 2026-10-31 R1-ATI re-gate) vs the row's
    from wsbench.baselines import text_inversion as ti

    gated = json.loads(ti.FROZEN.read_text(encoding="utf-8"))["moral_rationale"]["instrument"]
    assert gated != "ec-v4"
    d = _write(tmp_path / "n", "moral_rationale", aggregate="native", prompt_version="ec-v4")
    r = ar.audit_family(d)
    assert r["floor"] == "n/a" and r["ati"] == f"re-gate ({gated} != ec-v4)"

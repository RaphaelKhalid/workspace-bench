"""typo on the shared basic-family code."""

from pathlib import Path

from wsbench import registry
from wsbench.banks import item_targets, load_bank
from wsbench.basic.prompts import PROMPT_VERSION, SYSTEM
from wsbench.cli import main
from wsbench.results import read_results

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples/readouts/typo.jsonl"


def test_bank_and_targets():
    header, items = load_bank(REPO / "evals/typo/items.json")
    assert header["family"] == "typo" and len(items) == 100
    first = next(it for it in items if it["name"] == "typo-February")
    assert item_targets(first) == ["February"]


def test_registered_spec_and_readme():
    from wsbench.evals.typo import SPEC

    registry.FAMILIES.setdefault(SPEC.name, SPEC)
    assert SPEC.group == "basic" and SPEC.judge.prompt_version == PROMPT_VERSION
    readme = (REPO / "evals/typo/README.md").read_text(encoding="utf-8")
    assert SYSTEM in readme and PROMPT_VERSION in readme


def test_dry_run_on_the_toy_file(tmp_path, capsys, monkeypatch):
    from wsbench.evals.typo import SPEC

    registry.FAMILIES.setdefault(SPEC.name, SPEC)
    monkeypatch.delenv("WSBENCH_JUDGE_MODEL", raising=False)
    out = tmp_path / "out"
    argv = [
        "judge",
        "opts=aggregate=native",
        "family=typo",
        f"readouts={EXAMPLE}",
        f"out={out}",
        "dry_run=True",
    ]
    assert main(argv) == 0
    r = read_results(out)
    assert r.value is None and r.extras["n_items_without_readouts"] == 98
    assert "judge prompt for" in capsys.readouterr().out


def test_typo_is_superseded_by_typo_mt(real_families):
    """plan 0033 T1 (Camila 2026-10-30: "drop this from the macro, we don't need it, just keep
    the hard version"): typo is out of the macro and out of every ``all`` default."""
    from test_results import _res

    from wsbench.results import macro

    assert registry.FAMILIES["typo"].superseded_by == "typo_mt"
    assert registry.FAMILIES["typo_mt"].superseded_by == ""  # the hard version stays
    m = macro([_res("typo", value=1.0), _res("typo_mt", value=0.5)])
    assert m["families"] == ["typo_mt"] and m["value"] == 0.5
    assert {"family": "typo", "reason": "superseded", "by": "typo_mt"} in m["excluded"]
    assert registry.drop_superseded(["typo", "typo_mt"]) == ["typo_mt"]
    assert registry.FAMILIES["typo"].bank.name == "items.json"  # frozen bank untouched

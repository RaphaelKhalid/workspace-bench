"""scripts/lite_site_table.py: the pre-registered lite-site procedure (plan 0032 §2.6, gpu R4d)."""

import importlib.util
import json
from collections import Counter
from pathlib import Path

from wsbench import readplan

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/lite_site_table.py"
_spec = importlib.util.spec_from_file_location("lite_site_table", SCRIPT)
lst = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lst)  # type: ignore[union-attr]


def test_choice_needs_more_than_ten_points():
    near = lst.table("association", {"a": Counter({1: 40, 2: 45, 3: 15})})
    assert near["chosen"] == {"kind": "final_token"}  # +5 points: keep final_token
    far = lst.table("association", {"a": Counter({1: 20, 2: 60, 3: 20})})
    assert far["chosen"] == {"kind": "offset_from_end", "k": 2}
    rb = lst.table("role_bound_association", {"a": Counter({1: 5})})
    assert {c["k"] for c in rb["candidates"]} == {1, 4}  # role_bound's k=4 is always a candidate


def test_gold_lines_are_counted_by_offset_from_end():
    rows = [
        {
            "id": "i",
            "summary_evidence": ["the carnaval drums", "unrelated", "carnaval again"],
            "summary_evidence_where": ["[L44 pos 30]", "[L44 pos 29]", "[L48 pos 28]"],
        }
    ]
    got = lst.gold_lines_by_k(rows, {"i": ["carnaval"]}, {("i", 44): 30, ("i", 48): 30})
    assert got == Counter({1: 1, 3: 1})


def test_frozen_rule_is_read_by_the_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(readplan, "REPO_ROOT", tmp_path)
    d = tmp_path / "evals" / "conjunctive_association"
    d.mkdir(parents=True)
    assert readplan.frozen_lite_rule("conjunctive_association") == {"kind": "final_token"}
    (d / "lite_rule.json").write_text(
        json.dumps({"lite_positions": {"kind": "offset_from_end", "k": 4}})
    )
    assert readplan.frozen_lite_rule("conjunctive_association") == {
        "kind": "offset_from_end",
        "k": 4,
    }

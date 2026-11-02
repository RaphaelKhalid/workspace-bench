"""Bank judge v2 (plan 0012 §2): the family rules, the forbidden answer, per-family PROMPTS."""

import importlib
import json
from pathlib import Path

from conftest import native_args

from wsbench import mc
from wsbench.banks import load_bank
from wsbench.basic import family as bfam
from wsbench.basic import judge as bjudge
from wsbench.basic import prompts as P  # noqa: N812
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.readouts import Cell

REPO = Path(__file__).resolve().parents[1]
CELL = Cell(id="x", layer=20, pos=3, samples=("a sample",), tokens=None, scores=None)


def test_user_renders_rule_and_forbidden_only_when_given():
    plain = P.render_user(["cat"], "prose", [CELL], family_rule="", forbidden="")
    assert plain == f'targets: ["cat"]\n{P.KIND_NOTE_PROSE}\n\n[position 3]\n  a sample'
    both = P.render_user(["cat"], "prose", [CELL], family_rule="RULE", forbidden="FORB")
    assert both.startswith(f'targets: ["cat"]\n{P.KIND_NOTE_PROSE}\nRULE\nFORB\n\n[position 3]')


def test_forbidden_line_is_multihop_only_and_json_quoted(monkeypatch):
    # plan 0048 (sanctioned edit): multihop left FORBIDDEN_FAMILIES (its MC judge is blind to
    # the surface answer); plan 0058 (sanctioned edit) removed medical_diagnosis, the last user,
    # so the template is exercised on a stand-in family
    assert P.forbidden_line("multihop", {"target": "Fe"}) == ""
    monkeypatch.setattr(P, "FORBIDDEN_FAMILIES", frozenset({"fam"}))
    assert P.forbidden_line("fam", {"target": "Fe"}).startswith('The input\'s final answer "Fe"')
    assert '"Fe"' in P.forbidden_line("fam", {"target": "Fe"}).split("only ")[1]
    assert P.forbidden_line("multilingual", {"target": "drei"}) == ""
    assert P.forbidden_line("fam", {}) == ""


def test_family_rules_and_per_family_prompts():
    # plan 0058 (sanctioned edit): medical_diagnosis{,_alt} removed with their rule and forbidden
    # line; plan 0048: multihop left FORBIDDEN_FAMILIES (blind MC judge)
    assert set(P.FAMILY_RULES) == {"typo"}
    assert frozenset() == P.FORBIDDEN_FAMILIES
    assert "misspelled" in P.FAMILY_RULE_TYPO and "Synonyms" in P.FAMILY_RULE_POETRY
    own = {
        "typo": "FAMILY_RULE_TYPO",
    }
    # basic_readout and association left the free-text bank judge for MC judges (plan 0039);
    # plan 0048: multihop renders its own blind MC prompts (test_multihop.py), not these;
    # plan 0038 poetry: its own blind MC judge;
    # plan 0054: multilingual left the basic bank judge (scorer mc+regex)
    for f in ["typo"]:
        mod = importlib.import_module(f"wsbench.evals.{f}.prompts")
        extra = set(mod.PROMPTS) - set(P.PROMPTS)
        assert extra == ({own[f]} if f in own else set()), f
        assert set(P.PROMPTS) <= set(mod.PROMPTS)
    # plan 0032 §2.7 (decision Q4): the rank-1 exception is deleted; the native token note is
    # the shared mc.TOKEN_NOTE, and only pieces of DIFFERENT samples never combine
    assert "ranked first among the candidates of its type" not in P.KIND_NOTE_TOKENS
    assert P.KIND_NOTE_TOKENS == mc.TARGET_TOKEN_NOTE  # a TARGETS judge (review of PR #140)
    assert "overrides the rules" in P.SYSTEM and "NEVER combine" in P.SYSTEM


def test_family_run_sends_the_items_own_forbidden_answer(tmp_path, monkeypatch):
    sent: list[str] = []

    def fake_run_calls(calls, **kw):
        sent.extend(c.user for c in calls)
        return {c.key: {"expressed": False, "target": "", "quote": ""} for c in calls}

    monkeypatch.setattr(bjudge, "run_calls", fake_run_calls)
    # plan 0048 (sanctioned edit): multihop left FORBIDDEN_FAMILIES; plan 0058 (sanctioned edit)
    # removed medical_diagnosis, its last user: a typo bank whose first item carries a surface
    # ``target`` stands in, with typo made a FORBIDDEN_FAMILIES member for the test
    monkeypatch.setattr(P, "FORBIDDEN_FAMILIES", frozenset({"typo"}))
    raw = json.loads((REPO / "evals/typo/items.json").read_text(encoding="utf-8"))
    raw["items"][0]["target"] = "Febuary"
    bank = tmp_path / "items.json"
    bank.write_text(json.dumps(raw), encoding="utf-8")
    _h, items = load_bank(bank)
    it = items[0]
    rows = [{"id": it["id"], "layer": 20, "pos": 5, "samples": ["something"]}]
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    args = native_args(
        readouts=path,
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version=P.PROMPT_VERSION)),
        layers=[20],
        items=[it["id"]],
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        extra={},
    )
    bfam.run_family(args, name="typo", bank=bank)
    line = P.forbidden_line("typo", it)
    assert line and len(sent) == 1 and line in sent[0]
    assert sent[0].startswith(f"targets: {json.dumps(bfam.targets_of(it))}")

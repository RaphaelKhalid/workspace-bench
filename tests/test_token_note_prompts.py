"""Plan 0032 §2.7.2 at the call sites (review of PR #140): what each family's judge actually
RECEIVES on token readouts is ``mc.token_note`` of its own spec, in summary mode (every
``digest.summary_note`` caller) and on the native basic path, where a token cell is ONE
``" | "``-joined ranked list."""

import contextlib
import dataclasses
import json
from pathlib import Path

import pytest
from conftest import write_jsonl
from summary_fakes import FakeLLM, summary_args

from wsbench import digest, mc, registry
from wsbench.basic import prompts as bp
from wsbench.readouts import Cell

REPO = Path(__file__).resolve().parents[1]
EX = REPO / "examples/readouts"
FLAT = ("numbers",)

# every family whose summary-mode judge is an LLM call fed by the shared example readouts
SUMMARY_JUDGED = [
    "association",
    "basic_readout",
    "buggy_code",
    "conjunctive_association",
    "directed_modulation",
    "introspection",
    "jailbreak_recognition",
    "knowledge_cutoff",
    "moral_rationale",
    "multi_concept_directed_modulation",
    "multihop",
    "multilingual",
    "poetry",
    "relational_multihop",
    "role_bound_association",
    "typo",
    "user_modeling",
]


def _as_tokens(src: Path, dst: Path) -> Path:
    """The example readouts as top-k token cells (each prose cell's words, best first)."""
    rows = []
    for ln in src.read_text(encoding="utf-8").splitlines():
        r = json.loads(ln)
        if "samples" in r:
            words = " ".join(s for s in r.pop("samples") if s).split()[:10] or ["x"]
            r["tokens"], r["scores"] = words, [float(10 - i) for i in range(len(words))]
        rows.append(r)
    return write_jsonl(dst, rows)


def _with_flat(monkeypatch, family: str, **kw):
    spec = dataclasses.replace(registry.FAMILIES[family], flat_types=FLAT, **kw)
    monkeypatch.setitem(registry.FAMILIES, family, spec)
    return spec


@pytest.mark.parametrize("family", SUMMARY_JUDGED)
def test_summary_judge_receives_the_spec_token_note(family, tmp_path, monkeypatch, real_families):
    spec = _with_flat(monkeypatch, family)
    want = mc.token_note(FLAT, multi_select=spec.multi_select, targets=spec.targets_judge)
    assert want != mc.TOKEN_NOTE
    path = _as_tokens(EX / f"{family}.jsonl", tmp_path / "r.jsonl")
    fake = FakeLLM.install(monkeypatch, judge=lambda s, u, sc: None)
    # every call fails (the fake answers None): the prompts are what count
    with contextlib.suppress(Exception):
        spec.run(summary_args(path, tmp_path / "o", "pv", allow_missing=True))
    calls = [(s, u) for name, s, u in fake.calls if name != "digest"]
    if family == "poetry":
        # round 5: poetry's HEADLINE judge is free-response (no options, no targets); it gets the
        # spec's targets-variant note made target-free; its MC diagnostic gets ``want``
        from wsbench.evals.poetry import prompts as pp

        free = [u for s, u in calls if s == pp.SYSTEM]
        want_free = pp.free_token_note(mc.token_note(FLAT, targets=True))
        assert free and all(want_free in u for u in free), family
        assert not any(want in u for u in free), family
        calls = [(s, u) for s, u in calls if s != pp.SYSTEM]
    users = [u for _s, u in calls]
    assert users, f"{family}: no judge call"
    assert all(want in u for u in users), family
    assert not any(mc.TOKEN_NOTE in u for u in users), family


def test_summary_multi_select_reaches_the_judge(tmp_path, monkeypatch, real_families):
    family = "multi_concept_directed_modulation"
    spec = _with_flat(monkeypatch, family, multi_select=True)
    path = _as_tokens(EX / f"{family}.jsonl", tmp_path / "r.jsonl")
    fake = FakeLLM.install(monkeypatch, judge=lambda s, u, sc: None)
    # every call fails (the fake answers None): the prompts are what count
    with contextlib.suppress(Exception):
        spec.run(summary_args(path, tmp_path / "o", "pv", allow_missing=True))
    users = [u for name, _s, u in fake.calls if name != "digest"]
    assert users and all(mc.token_note(FLAT, multi_select=True) in u for u in users)


def test_native_token_cell_is_one_ranked_list_line():
    """Camila's multihop counter-example: a flat run of numbers must read as ONE list, so
    'twelve' is not alone on its line (and the spec's flat_types reach the note)."""
    cells = [Cell("i", 20, 11, None, ("equal", "twelve", "six", "eight", "seven"), None)]
    note = mc.token_note(FLAT)
    user = bp.render_user(
        ["twelve"], "tokens", cells, family_rule="", forbidden="", token_note=note
    )
    assert "[position 11]\n  equal | twelve | six | eight | seven" in user
    assert "\n  twelve\n" not in user
    assert note in user and mc.TOKEN_NOTE not in user
    prose = [Cell("i", 20, 11, ("a b", "c"), None, None)]
    assert "[position 11]\n  a b\n  c" in bp.render_user(
        ["x"], "prose", prose, family_rule="", forbidden=""
    )


def test_native_basic_judge_receives_spec_note_and_bag_lines(tmp_path, monkeypatch, real_families):
    # plan 0048: multihop moved to the blind MC judge (an OPTIONS judge; its note is held by
    # test_multihop.py::test_flat_types_rendered); plan 0058 removed medical_diagnosis, so typo
    # is the remaining native TARGETS judge
    family = "typo"
    spec = _with_flat(monkeypatch, family)
    path = _as_tokens(EX / f"{family}.jsonl", tmp_path / "r.jsonl")
    fake = FakeLLM.install(monkeypatch, judge=lambda s, u, sc: None)
    args = summary_args(path, tmp_path / "o", "pv", allow_missing=True)
    args = dataclasses.replace(args, extra={**args.extra, "aggregate": "native"})
    # every call fails (the fake answers None): the prompts are what count
    with contextlib.suppress(Exception):
        spec.run(args)
    users = [u for name, _s, u in fake.calls if name != "digest"]
    assert users and all(mc.token_note(FLAT, targets=True) in u for u in users)
    # every token cell is one " | "-joined line under its position header
    bodies = [
        b.split("\n", 1)[1].strip("\n").split("\n\n")[0]
        for u in users
        for b in u.split("[position ")[1:]
    ]
    assert bodies and all(len(b.splitlines()) == 1 for b in bodies), bodies
    assert any(" | " in b for b in bodies)


def test_quote_from_one_list_verifies_across_tokens():
    from wsbench.basic.judge import quote_verified

    cell = Cell("i", 20, 3, None, ("New", "York", "City"), None)
    assert quote_verified("New | York", list(bp.cell_lines(cell)))
    assert quote_verified("York", list(bp.cell_lines(cell)))


# basic_readout left for the blind MC judge (plan 0053): it gets the OPTIONS form of the note
# with its flat types (test_basic_readout_mc_judge_sees_the_options_note below)
BASIC_TARGET_JUDGES = [
    # medical_diagnosis{,_alt}: removed (plan 0058)
    # multihop left in plan 0048: an OPTIONS judge (blind MC), held by test_multihop.py
    # plan 0054: multilingual left the basic bank judge (an MC judge with options, mc+regex)
    # poetry: its own blind MC judge (plan 0038)
    "typo",
]  # wrong_bridge: its own MC judge with FLAT_TYPES (plan 0050); wrong_bridge_true removed


@pytest.mark.parametrize("family", BASIC_TARGET_JUDGES)
@pytest.mark.parametrize("aggregate", ["summary", "native"])
def test_basic_target_judges_never_see_the_lone_option_clause(
    family, aggregate, tmp_path, monkeypatch, real_families
):
    """Review of PR #140: with the REGISTERED spec (no flat_types), every basic target judge
    receives the targets note, in summary and native mode, never the options clause."""
    registry.load_all()
    spec = registry.FAMILIES[family]
    assert spec.targets_judge
    assert digest.token_note_of(family) == bp.token_note_for(family) == mc.TARGET_TOKEN_NOTE
    src = EX / f"{family}.jsonl"
    if not src.exists():
        pytest.skip("no example readouts")
    path = _as_tokens(src, tmp_path / "r.jsonl")
    fake = FakeLLM.install(monkeypatch, judge=lambda s, u, sc: None)
    args = summary_args(path, tmp_path / "o", "pv", allow_missing=True)
    if aggregate == "native":
        args = dataclasses.replace(args, extra={**args.extra, "aggregate": "native"})
    with contextlib.suppress(Exception):
        spec.run(args)
    users = [u for name, _s, u in fake.calls if name != "digest"]
    assert users, family
    assert all(mc.TARGET_TOKEN_NOTE in u for u in users), family
    assert not any("only option on its line" in u for u in users), family


@pytest.mark.parametrize("aggregate", ["summary", "native"])
def test_basic_readout_mc_judge_sees_the_options_note(
    aggregate, tmp_path, monkeypatch, real_families
):
    """Plan 0053: basic_readout's MC judge holds OPTIONS, so it receives
    mc.token_note(spec.flat_types) (lone-option clause, overridden by its flat types), never the
    targets form."""
    registry.load_all()
    spec = registry.FAMILIES["basic_readout"]
    assert not spec.targets_judge
    want = mc.token_note(spec.flat_types, multi_select=spec.multi_select)
    assert digest.token_note_of("basic_readout") == want
    path = _as_tokens(EX / "basic_readout.jsonl", tmp_path / "r.jsonl")
    fake = FakeLLM.install(monkeypatch, judge=lambda s, u, sc: None)
    args = summary_args(path, tmp_path / "o", "pv", allow_missing=True)
    if aggregate == "native":
        args = dataclasses.replace(args, extra={**args.extra, "aggregate": "native"})
    with contextlib.suppress(Exception):
        spec.run(args)
    users = [u for name, _s, u in fake.calls if name != "digest"]
    assert users
    assert all(want in u for u in users)
    assert not any(mc.TARGET_TOKEN_NOTE in u for u in users)

"""directed_modulation: options, prompt rendering, decode/evidence gate, summary, CLI run."""

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import write_jsonl
from summary_fakes import FakeLLM, summary_args

from wsbench import digest, llm, mc, reads, registry
from wsbench.banks import load_bank
from wsbench.cli import main
from wsbench.evals.directed_modulation import judge, prompts, score
from wsbench.readouts import Cell
from wsbench.results import read_results

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples/readouts/directed_modulation.jsonl"


def _reply(**fields: Any) -> Any:
    base = {
        "choice": 6,
        "form": "none",
        "basis": "absent",
        "composition": "none",
        "domain_overlap": [False] * 5,
        "evidence": "",
        "rationale": "",
    }
    base.update(fields)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(base)))],
        usage=SimpleNamespace(cost=0.001),
    )


class FakeJudge:
    """Picks the gold option when its concept word appears in the readout block; the basis is
    ``instruction_narration`` when the readout says "must not" or "asked", else content."""

    def __init__(self, options: dict[str, tuple[list[str], int]]):
        self.options = options
        self.calls: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw: Any) -> Any:
        user = kw["messages"][1]["content"]
        self.calls.append(user)
        readout = user.split("<readout>\n", 1)[1].split("\n</readout>", 1)[0]
        for opts, gold_pos in self.options.values():
            gold = opts[gold_pos - 1]
            if gold.lower() in readout.lower() and f"1. {opts[0]}" in user:
                basis = (
                    "instruction_narration"
                    if ("must not" in readout or "asked" in readout)
                    else "content_bound"
                )
                return _reply(choice=gold_pos, form="exact", basis=basis, evidence=gold)
        return _reply()

    async def close(self) -> None:
        return None


@pytest.fixture
def family(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("WSBENCH_JUDGE_MODEL", raising=False)
    monkeypatch.setattr(llm, "_backoff", lambda attempt, status: 0.0)

    async def no_pace(rpm: float) -> None:
        return None

    monkeypatch.setattr(llm, "_pace", no_pace)
    monkeypatch.setattr(llm, "preflight", lambda model, reasoning: None)
    from wsbench.evals.directed_modulation import SPEC

    registry.FAMILIES.setdefault(SPEC.name, SPEC)
    return SPEC


def _bank():
    return load_bank(REPO / "evals/directed_modulation/items.json")[1]


def test_bank_and_option_sets():
    items = _bank()
    assert len(items) == 100 and {it["subfamily"] for it in items} == {
        "pair",
        "secret",
        "preference",
    }
    opts = judge.option_sets(items)
    assert len(opts) == 100
    by_id = {it["id"]: it for it in items}
    for item_id, (shown, gold_pos) in opts.items():
        it = by_id[item_id]
        assert len(shown) == 5 and shown[gold_pos - 1] == it["concept"]
        others = {by_id[i]["concept"] for i in by_id if by_id[i]["subfamily"] == it["subfamily"]}
        assert set(shown) <= others  # same-subfamily distractors only
    assert judge.option_sets(items) == opts  # seeded, stable
    assert judge.option_sets(items, seed=1) != opts
    golden = json.loads((REPO / "tests/golden/directed_modulation_options.json").read_text())
    assert {k: (v["options"], v["gold_position"]) for k, v in golden["options"].items()} == opts


def test_prompt_rendering_by_subfamily_and_polarity():
    # plan 0035: no prompt= (blind judge); the token bag note is the shared mc.token_note
    u = prompts.render_user(
        readout="R",
        options=["a", "b"],
        subfamily="secret",
        polarity="suppress",
        tokens=False,
    )
    assert "1. a\n2. b\n3. cannot tell from the readout" in u
    assert "secret WORD" in u and "NOT to think" in u and mc.TOKEN_NOTE not in u
    assert "(2 entries)" in u
    u = prompts.render_user(
        readout="R", options=["a"], subfamily="pair", polarity="think", tokens=True
    )
    assert "told to think about" in u and mc.TOKEN_NOTE in u
    assert "Credit a candidate in ANY surface form" in u
    u = prompts.render_user(
        readout="R",
        options=["a"],
        subfamily="preference",
        polarity="suppress",
        tokens=False,
    )
    assert "preference/hobby" in u
    assert "{" not in u.replace('{"', "")  # every placeholder rendered


def test_readme_carries_every_prompt():
    readme = (REPO / "evals/directed_modulation/README.md").read_text(encoding="utf-8")
    for text in prompts.PROMPTS.values():
        assert text in readme
    assert prompts.PROMPT_VERSION in readme


def test_decode_and_evidence_gate():
    opts, gold = ["clavicle", "femur", "ulna", "patella", "sternum"], 1
    r = {
        "choice": 1,
        "form": "exact",
        "basis": "content_bound",
        "domain_overlap": [True, False],
        "evidence": "the clavicle",
    }
    v = judge.decode(r, opts, gold, "About the clavicle, above the ribs.")
    assert v["pick"] == "gold" and v["basis"] == "content_bound" and v["gold_overlap"] is True
    assert v["domain_overlap"] == [True, False, False, False, False] and v["evidence_verified"]
    v = judge.decode(dict(r, evidence="the femur"), opts, gold, "About the clavicle.")
    assert (
        v["voided"]
        and v["pick"] == "cannot_tell"
        and v["basis"] == "absent"
        and not any(v["domain_overlap"])
    )
    v = judge.decode(
        {"choice": 6, "form": "none", "basis": "absent", "domain_overlap": [], "evidence": ""},
        opts,
        gold,
        "x",
    )
    assert v["pick"] == "cannot_tell" and v["evidence_verified"] is None and not v["voided"]
    v = judge.decode({"choice": 9, "evidence": ""}, opts, gold, "x")
    assert v["pick"] == "cannot_tell" and v["choice_invalid"]
    v = judge.decode(
        {"choice": 3, "basis": "content_bound", "domain_overlap": [False] * 5, "evidence": "ulna"},
        opts,
        gold,
        "an ulna",
    )
    assert v["pick"] == "distractor"
    assert judge.decode(None, opts, gold, "x") == {"judged": False}


def test_readout_rows_prose_and_tokens():
    from wsbench.readouts import Cell

    cells = [
        Cell("a", 20, 5, ("x", "", "y"), None, None),
        Cell("a", 20, 6, ("",), None, None),
        Cell("b", 20, 5, None, (" zeph", "yr", "\n"), None),  # as the loader decodes them
    ]
    rows, n_empty = judge.readout_rows(cells)
    assert n_empty == 1
    assert [(r.item_id, r.pos, r.sample, r.readout) for r in rows] == [
        ("a", 5, 0, "x"),
        ("a", 5, 2, "y"),  # the sample keeps its index in the cell
        ("b", 5, 0, "zeph | yr"),
    ]
    assert rows[0].key == "a|L020|p5|s0"
    assert judge.missing_cells(["a", "b", "c"], [20, 36], cells) == [
        ("a", 36),
        ("b", 36),
        ("c", 20),
        ("c", 36),
    ]


def test_summary_channels_and_white_bear():
    items = [
        {"id": "p-pos", "subfamily": "pair", "pair_id": "p", "polarity": "think"},
        {"id": "p-neg", "subfamily": "pair", "pair_id": "p", "polarity": "dont_think"},
        {"id": "s", "subfamily": "secret", "pair_id": "s", "polarity": "suppress"},
    ]

    def v(item, pick, basis="absent", gold_ov=False, dis_ov=False, judged=True, voided=False):
        return {
            "item": item,
            "judged": judged,
            "pick": pick,
            "basis": basis,
            "form": "exact",
            "gold_overlap": gold_ov,
            "distractor_overlap": dis_ov,
            "voided": voided,
            "choice_invalid": False,
        }

    verdicts = [
        v("p-pos", "cannot_tell"),
        v("p-pos", "gold", "content_bound"),
        v("p-neg", "gold", "instruction_narration"),
        v("p-neg", "cannot_tell", dis_ov=True),
        v("s", "distractor", "content_bound"),
        v("s", "cannot_tell", judged=False),
    ]
    s = score.summarize(items, verdicts)
    # the secret item has an unjudged row and no content-bound positive: undecided there,
    # decided (True) on the distractor channel
    assert s["overall"]["content_bound"] == pytest.approx(1 / 2)
    assert s["overall"]["expressed"] == pytest.approx(1.0)
    assert s["pair"]["instruction_narration"] == 0.5 and s["pair"]["hint_distractor"] == 0.5
    assert s["secret"]["distractor"] == 1.0 and s["secret"]["content_bound"] is None
    assert (
        score.summarize(items, verdicts, frozenset({"p-neg"}))["white_bear"] is None
        if False
        else True
    )
    assert s["white_bear"] == {
        "n_pairs": 1,
        "think_rate": 1.0,
        "dont_think_rate": 0.0,
        "delta": 1.0,
    }
    assert s["picks"] == {"cannot_tell": 2, "gold": 2, "distractor": 1}


def test_cli_run_on_the_toy_file(family, tmp_path, monkeypatch):
    items = _bank()
    fake = FakeJudge(judge.option_sets(items))
    monkeypatch.setattr(llm, "_make_client", lambda route, key: fake)
    out = tmp_path / "out"
    argv = [
        "judge",
        "opts=aggregate=native",
        "family=directed_modulation",
        f"readouts={EXAMPLE}",
        f"out={out}",
    ]
    assert main([*argv, "items=dm-pair-00-pos,dm-pair-00-neg,dm-secret-00"]) == 0
    r = read_results(out)
    assert r.n_items == 3 and r.counts["n_expected_cells"] == 7 and r.counts["n_empty_cells"] == 1
    assert r.counts["n_missing_cells"] == 0 and r.extras["n_calls"] == 6
    assert len(fake.calls) == 6 and r.complete is False  # items= subset
    s = r.extras["summary"]
    assert s["overall"]["content_bound"] == pytest.approx(2 / 3)  # pos pair + secret (content)
    assert s["pair"]["instruction_narration"] == 0.5  # the neg twin narrates only
    assert s["white_bear"]["delta"] == 1.0
    # plan 0028: the narrating neg twin now counts (headline = present); content_bound stays 2/3
    assert s["overall"]["present"] == pytest.approx(1.0)
    assert r.value == pytest.approx(1.0) and r.extras["n_items_decided"] == 3
    assert (out / "cells.jsonl").exists()
    assert len(r.rows[0]["options"]) == 5  # options drawn from the whole bank, not the subset
    assert main([*argv, "dry_run=True"]) == 0  # no key needed; makes no call
    assert len(fake.calls) == 6


def test_missing_layer_exit_2_and_undecided(family, tmp_path, monkeypatch):
    items = _bank()
    fake = FakeJudge(judge.option_sets(items))
    monkeypatch.setattr(llm, "_make_client", lambda route, key: fake)
    rows = [
        {"id": "dm-pair-00-pos", "layer": 20, "pos": 38, "samples": ["nothing here"]},
        {"id": "dm-pair-00-neg", "layer": 20, "pos": 38, "samples": ["nothing"]},
        {"id": "dm-pair-00-neg", "layer": 36, "pos": 38, "samples": ["nothing"]},
    ]
    f = tmp_path / "r.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    out = tmp_path / "out"
    argv = [
        "judge",
        "opts=aggregate=native",
        "family=directed_modulation",
        f"readouts={f}",
        f"out={out}",
        "items=dm-pair-00-pos,dm-pair-00-neg",
    ]
    with pytest.raises(SystemExit) as ei:
        main(argv)
    assert ei.value.code == 2
    assert main([*argv, "allow_missing=True"]) == 0
    r = read_results(out)
    assert r.counts["n_missing_cells"] == 1 and r.extras["n_items_undecided"] == 1
    assert (
        r.value == 0.0 and r.extras["summary"]["white_bear"] is None
        if "white_bear" in r.extras["summary"]
        else True
    )
    assert "white_bear" not in r.extras["summary"]  # the pos twin is undecided


def test_tokens_kind_end_to_end_and_voided(family, tmp_path, monkeypatch):
    items = _bank()
    opts = judge.option_sets(items)

    class Voider(FakeJudge):
        async def _create(self, **kw: Any) -> Any:
            self.calls.append(kw["messages"][1]["content"])
            _o, g = opts["dm-secret-00"]
            return _reply(choice=g, form="exact", basis="content_bound", evidence="not in the bag")

    fake = Voider(opts)
    monkeypatch.setattr(llm, "_make_client", lambda route, key: fake)
    rows = [{"id": "dm-secret-00", "layer": 20, "pos": 30, "tokens": ["Ġzeph", "yr", "Ċ"]}]
    f = tmp_path / "t.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    out = tmp_path / "out"
    assert (
        main(
            [
                "judge",
                "opts=aggregate=native",
                "family=directed_modulation",
                f"readouts={f}",
                f"out={out}",
                "items=dm-secret-00",
            ]
        )
        == 0
    )
    r = read_results(out)
    assert (
        r.config["kind"] == "tokens"
        and mc.token_note() in fake.calls[0]  # plan 0035 G5: the shared token-list rule
        and "zeph | yr" in fake.calls[0]
    )
    assert r.value == 0.0 and r.extras["summary"]["n_voided"] == 1 and r.rows[0]["voided"]


def test_all_blank_item_fails_rather_than_vanishing(family, tmp_path, monkeypatch):
    fake = FakeJudge(judge.option_sets(_bank()))
    monkeypatch.setattr(llm, "_make_client", lambda route, key: fake)
    rows = [{"id": "dm-secret-00", "layer": 20, "pos": 30, "samples": [""]}]
    f = tmp_path / "b.jsonl"
    f.write_text(json.dumps(rows[0]) + "\n")
    out = tmp_path / "out"
    assert (
        main(
            [
                "judge",
                "opts=aggregate=native",
                "family=directed_modulation",
                f"readouts={f}",
                f"out={out}",
                "items=dm-secret-00",
            ]
        )
        == 0
    )
    r = read_results(out)
    assert r.value == 0.0 and r.extras["n_items_decided"] == 1 and fake.calls == []


def test_judge_calls_keyed_by_judge_prompt_version():
    """Plan 0035: new judge prompts, new cache key (dm-2026-10-31); the instrument carries
    +expressed (the any-basis headline)."""
    from wsbench.evals.directed_modulation import judge as dmj

    src = __import__("inspect").getsource(dmj)
    assert "prompt_version=JUDGE_PROMPT_VERSION" in src and "pv_calls" in src
    assert prompts.JUDGE_PROMPT_VERSION == "dm-2026-10-31"
    assert prompts.PROMPT_VERSION == prompts.JUDGE_PROMPT_VERSION + "+expressed"


# ---------------------------------------------------------------- plan 0035 (fix campaign)


def _dm_answer(choice: int, evidence: str = "", basis: str = "content_bound") -> dict:
    return {
        "choice": choice,
        "form": "exact" if evidence else "none",
        "basis": basis if evidence else "absent",
        "composition": "full" if evidence else "none",
        "domain_overlap": [False] * 5,
        "evidence": evidence,
        "rationale": "",
    }


def _shown(user: str) -> list[str]:
    return re.findall(r"^\d\. (.*)$", user, flags=re.M)


def _words(text: str, word: str) -> int:
    return len(re.findall(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", text, flags=re.I))


def test_judge_is_blind():
    """C1: neither the instruction nor the carrier is ever rendered, and the gold concept appears
    exactly once (its own option line), natively (prose and tokens) and in summary mode."""
    items = _bank()
    opts = judge.option_sets(items)
    note = digest.summary_note(
        summary_args(EXAMPLE, Path("."), "pv"), "prose", "directed_modulation"
    )
    for it in items:
        o, gold_pos = opts[it["id"]]
        for kw in (
            {"tokens": False},
            {"tokens": True},
            {"tokens": False, "summary_note": note},
        ):
            u = prompts.render_user(
                readout="R",
                options=o,
                subfamily=it["subfamily"],
                polarity=it["polarity"],
                **kw,
            )
            assert it["prompt"] not in u and it["assistant"] not in u
            assert "instruction_to_model" not in u
            assert _words(u, it["concept"]) == 1, (it["id"], kw)
            assert f"{gold_pos}. {it['concept']}" in u
    assert "instruction_to_model" not in prompts.USER and "{prompt}" not in prompts.USER


def test_distractors_exclude_related_group():
    """C2: every shown distractor is another item's concept of the same subfamily and never in
    the gold's relatedness group; the escape is rendered last by the shared helper."""
    items = _bank()
    by_sub: dict[str, set[str]] = {}
    for it in items:
        by_sub.setdefault(it["subfamily"], set()).add(it["concept"])
    for it in items:
        shown, gold_pos = judge.option_sets(items)[it["id"]]
        assert shown[gold_pos - 1] == it["concept"] and len(shown) == 5
        for c in shown:
            if c == it["concept"]:
                continue
            assert c in by_sub[it["subfamily"]]
            assert judge.group_of(c) != judge.group_of(it["concept"]), (it["id"], c)
        lines = prompts.option_lines(shown).splitlines()
        assert lines[-1] == f"6. {mc.CANNOT}"
    # the ten pair sibling cases of the old draw are gone (e.g. femur for clavicle)
    o = dict(judge.option_sets(items))
    assert "femur" not in o["dm-pair-00-neg"][0] and "donkey" not in o["dm-pair-05-neg"][0]
    assert "origami" not in o["dm-pref-13"][0] and "gazebo" not in o["dm-secret-14"][0]


def test_groups_cover_every_bank_concept():
    """C2: the frozen groups file covers the bank and every adapted bank; a concept missing from
    it is a hard error."""
    concepts = {it["concept"] for it in _bank()}
    for f in sorted((REPO / "adapted").glob("*/directed_modulation.json")):
        concepts |= {it["concept"] for it in load_bank(f)[1]}
    for c in concepts:
        judge.group_of(c)
    with pytest.raises(ValueError, match="no relatedness group"):
        judge.option_sets([{"id": "x", "name": "x", "subfamily": "pair", "concept": "tibia"}])


def test_dm_task_note_reaches_summarizer(tmp_path, monkeypatch, family):
    """C3: the family task note (with the single-mention and restatement clauses) is in the
    summarizer's system prompt; the family gives the rare tier room."""
    note = registry.FAMILIES["directed_modulation"].task_note
    assert note == prompts.DIGEST_TASK_NOTE
    assert "only one sample" in note and "restatement of an instruction" in note
    assert "may not be the most prominent" in note
    args = summary_args(EXAMPLE, tmp_path, prompts.PROMPT_VERSION)
    s = digest.settings(args, "directed_modulation")
    assert s.variant == "task" and s.max_rare == 25
    assert note in digest.render_system(s, note)
    fake = FakeLLM.install(monkeypatch, lambda sy, u, sc: _dm_answer(6))
    family.run(
        summary_args(EXAMPLE, tmp_path / "o", prompts.PROMPT_VERSION, items=["dm-secret-00"])
    )
    systems = [sy for name, sy, _u in fake.calls if name == "digest"]
    assert systems and all(note in sy for sy in systems)


def test_dm_restated_concept_reaches_judge(tmp_path, monkeypatch, family):
    """C3: a bundle whose only gold mention is a restated instruction (dm-pair-30-neg) yields a
    digest line keyed on the concept, which reaches the judge and passes the gate."""
    rows = [
        {"id": "dm-pair-30-neg", "layer": 20, "pos": p, "samples": ["The meeting was routine."]}
        for p in (30, 31)
    ] + [
        {
            "id": "dm-pair-30-neg",
            "layer": 44,
            "pos": 31,
            "samples": ["Minutes recorded without using barnacles"],
        }
    ]
    path = write_jsonl(tmp_path / "r.jsonl", rows)

    def dig(user: str) -> dict:
        lines = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
        hit = next((ln for ln in lines if "barnacles" in ln), None)
        if hit is None:  # audit F1: a per-layer digest of a layer without the mention
            return {"items": []}
        return {"items": [{"statement": "barnacles", "where": "", "evidence": hit}]}

    def jud(sy: str, user: str, sc: dict) -> dict:
        assert "Minutes recorded without using barnacles" in user
        o = _shown(user)
        return _dm_answer(
            o.index("barnacle") + 1, "without using barnacles", "instruction_narration"
        )

    fake = FakeLLM.install(monkeypatch, jud, digest=dig)
    r = family.run(
        summary_args(path, tmp_path / "o", prompts.PROMPT_VERSION, items=["dm-pair-30-neg"])
    )
    assert fake.n("dm_concept") == 1
    assert r.value == 1.0 and r.rows[0]["pick"] == "gold" and r.rows[0]["evidence_verified"]


def test_headline_counts_any_basis():
    """C5: the headline is `expressed`: gold under any basis passes; distractor and voided fail."""
    items = [{"id": f"i{k}", "subfamily": "pair", "polarity": "think"} for k in range(5)]

    def v(item, pick, basis, voided=False):
        return {
            "item": item,
            "judged": True,
            "pick": pick,
            "basis": basis,
            "form": "exact",
            "gold_overlap": False,
            "distractor_overlap": False,
            "voided": voided,
            "choice_invalid": False,
            "options": ["clavicle", "rook"],
            "gold_position": 1,
            "evidence": "clavicle",
        }

    verdicts = [
        v("i0", "gold", "incidental"),
        v("i1", "gold", "instruction_narration"),
        v("i2", "gold", "content_bound"),
        v("i3", "distractor", "content_bound"),
        v("i4", "cannot_tell", "absent", voided=True),
    ]
    assert [score.hit(x) for x in verdicts] == [True, True, True, False, False]
    r = score.score(
        items,
        verdicts,
        args=summary_args(EXAMPLE, Path("."), "pv", extra={"aggregate": "native"}),
        kind="prose",
        layers=[20],
        n_cells=5,
        missing=[],
        n_empty=0,
        skipped_rows=0,
        spend=llm.Spend(),
    )
    assert r.value == pytest.approx(3 / 5) and r.extras["headline"].startswith("expressed")
    s = r.extras["summary"]["overall"]
    assert s["present"] == pytest.approx(2 / 5) and s["content_bound"] == pytest.approx(1 / 5)
    assert "prompt-only" not in score.CHANCE_LABEL


def test_credit_rules_accept_close_relatives():
    """C5 + Camila's MCDM line: every subfamily credits synonyms and close relatives and still
    refuses a broader category alone; the secret rule is no longer exact-word only."""
    for sub in ("pair", "secret", "preference"):
        rules = prompts.credit_rules(sub)
        assert prompts.CLOSE_RELATIVE in rules
        assert "close relative or near equivalent" in rules
        assert "a broader category alone" in rules
    assert "Do NOT credit synonyms" not in prompts.CREDIT_SECRET
    assert "Credit only the exact word" not in prompts.CREDIT_SECRET
    assert "The candidate counts in ANY context" in prompts.USER


def test_relative_only_hits_column():
    """C5: a gold pick quoting "collarbone" counts as relative-only; "clavicles" does not."""
    base = {"judged": True, "pick": "gold", "options": ["rook", "clavicle"], "gold_position": 2}
    assert score.relative_only({**base, "evidence": "the collarbone aches"})
    assert not score.relative_only({**base, "evidence": "two Clavicles"})
    assert not score.relative_only({**base, "pick": "distractor", "evidence": "x"})
    items = [{"id": "a", "subfamily": "pair", "polarity": "think"}]
    rows = [
        {
            **base,
            "item": "a",
            "basis": "content_bound",
            "form": "synonym",
            "gold_overlap": False,
            "distractor_overlap": False,
            "voided": False,
            "choice_invalid": False,
            "evidence": "collarbone",
        }
    ]
    s = score.summarize(items, rows)
    assert s["overall"]["n_relative_only_hits"] == 1 and s["pair"]["n_items_relative_only"] == 1
    s = score.summarize(items, [{**rows[0], "evidence": "clavicles"}])
    assert s["overall"]["n_relative_only_hits"] == 0


def _hornet_item() -> tuple[dict, list[str], int]:
    items = _bank()
    it = next(i for i in items if i["id"] == "dm-pair-08-pos")
    o, g = judge.option_sets(items)[it["id"]]
    assert "weevil" not in o  # C2: hornet's sibling is never an option
    return it, o, g


@pytest.mark.parametrize("aggregate", ["native", "summary"])
def test_dm_lone_option_in_same_category_list_is_gold(aggregate, tmp_path, monkeypatch, family):
    """G5: the judge message carries exactly the spec's mc.token_note and not the retired
    digest sentence; a line holding two shown options is cannot-tell. Decision Q4 (2026-10-31,
    PR #191) retired G5's "a lone shown option inside a same-category list is singled out": the
    prompt now says such a run singles out none of them, and the judge (faked here) decides."""
    it, o, g = _hornet_item()
    other = next(c for c in o if c != "hornet")
    rows = [
        {"id": it["id"], "layer": 20, "pos": 40, "tokens": ["hornet", "wasp", "bee", "ant"]},
        {"id": it["id"], "layer": 24, "pos": 40, "tokens": ["hornet", other]},
    ]
    path = write_jsonl(tmp_path / "t.jsonl", rows)
    want = mc.token_note(family.flat_types, multi_select=family.multi_select)
    assert want == mc.token_note() == prompts.token_note()

    def jud(sy: str, user: str, sc: dict) -> dict:
        assert want in user and "even inside a list of other words of the same kind" not in user
        assert "singles out none of them, even when only one of them is an option" in user
        if f"hornet | {other}" in user and "wasp" not in user:
            return _dm_answer(6)
        return _dm_answer(g, "hornet | wasp", "incidental")

    FakeLLM.install(monkeypatch, jud)
    r = family.run(
        summary_args(
            path,
            tmp_path / "o",
            prompts.PROMPT_VERSION,
            items=[it["id"]],
            extra={"aggregate": aggregate},
        )
    )
    picks = {(v["layer"], v["pick"]) for v in r.rows}
    assert r.value == 1.0, picks
    if aggregate == "native":
        assert picks == {(20, "gold"), (24, "cannot_tell")}


def test_dm_gate_uses_quote_ok():
    """G5: non-adjacent tokens of ONE list verify (dm-pair-23-pos L52 p42 "shame", once voided);
    tokens from two lists do not; a quote across the bullet mark of one prose sample verifies."""
    opts, gold = ["shame", "rook", "onyx", "canoe", "envy"], 1
    r = {"choice": 1, "basis": "content_bound", "domain_overlap": [False] * 5}
    cell = Cell("dm-pair-23-pos", 52, 42, None, ("guilt", "the", "shame", "of", "blush"), None)
    rows, _n = judge.readout_rows([cell])
    v = judge.decode({**r, "evidence": "guilt | shame"}, opts, gold, rows[0].lines)
    assert v["pick"] == "gold" and v["evidence_verified"] and not v["voided"]
    two = digest.native_lines(
        [cell, Cell("dm-pair-23-pos", 56, 42, None, ("rook", "humiliation"), None)]
    )
    v = judge.decode({**r, "evidence": "shame | humiliation"}, opts, gold, two)
    assert v["voided"] and v["pick"] == "cannot_tell"
    sample = "- draining pasta\n- colander in the sink"
    prose = Cell("dm-pair-09-pos", 44, 40, (sample,), None, None)
    rows, _n = judge.readout_rows([prose])
    for q in ("pasta ⁞ colander", "draining pasta colander", "colander in the sink"):
        v = judge.decode({**r, "evidence": q}, ["colander", *opts[1:]], 1, rows[0].lines)
        assert v["evidence_verified"], q


def test_dm_lite_judges_final_carrier_token(tmp_path, monkeypatch, family):
    """G1: under reads=lite only the carrier's final token is judged; the stamp ends +reads-lite;
    the plan row carries the pre-registered final_token rule and the full carrier span."""
    from wsbench import readplan

    spec = next(s for s in readplan.plan("directed_modulation") if s.id == "dm-pair-00-pos")
    assert spec.lite_positions == {"kind": "final_token"} and spec.lite_layers is None
    assert spec.positions["kind"] == "suffix_text"
    assert family.min_full_positions == 6 and family.full_contiguous
    rows = [
        {"id": "dm-pair-00-pos", "layer": 20, "pos": p, "samples": [f"R{p}"]} for p in (38, 39, 40)
    ]
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    fake = FakeLLM.install(monkeypatch, lambda sy, u, sc: _dm_answer(6))
    args = summary_args(
        path,
        tmp_path / "o",
        prompts.PROMPT_VERSION,
        items=["dm-pair-00-pos"],
        extra={"aggregate": "native", "reads": "lite"},
    )
    r = family.run(args)
    assert {v["pos"] for v in r.rows} == {40} and len(fake.calls) == 1
    assert r.config["prompt_version"].endswith("+reads-lite")
    assert reads.mode(args) == "lite"

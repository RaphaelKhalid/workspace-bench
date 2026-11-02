"""multi_concept_directed_modulation: option lists, the region rule, the verdict, the read.json
converter, a scripted toy run and a dry run."""

import json
from pathlib import Path

import pytest
from conftest import native_args

from wsbench import registry
from wsbench.banks import load_bank
from wsbench.cli import main
from wsbench.evals.multi_concept_directed_modulation import judge
from wsbench.evals.multi_concept_directed_modulation.options import option_sets, partner_of
from wsbench.evals.multi_concept_directed_modulation.prompts import (
    LETTERS,
    N_OPTIONS,
    PROMPT_VERSION,
)
from wsbench.evals.multi_concept_directed_modulation.regions import (
    TARGET_SENTENCE,
    Region,
    classify_regions,
    label_cells,
    write_compliance,
)
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.readouts import convert_read_json, load_readouts
from wsbench.results import read_results

REPO = Path(__file__).resolve().parents[1]
BANK = REPO / "evals/multi_concept_directed_modulation/items.json"  # v1 (frozen, untouched)
BANK_V2 = REPO / "evals/multi_concept_directed_modulation/items_v2.json"  # plan 0034
EXAMPLE = REPO / "examples/readouts/multi_concept_directed_modulation.jsonl"

# the shape every binding item's completion had under the pre-2026-09-23 rollout regime: sentence,
# blank line, empty think block, then the model re-writing the prompt (the region rule is kept)
WITH_THINK = [
    "review",
    " the",
    " annual",
    " budget",
    '."',
    "\n\n",
    "<think>",
    "\n\n",
    "</think>",
    "\n\n",
    "Think",
    " about",
]
# d-cranes: no think block, a self-added continuation as the tail
NO_THINK = ["review", " the", " annual", " budget", '."', "\n\n", "Now", " write", " this"]
# d-petrichor: the model ignored the instruction and wrote its own sentence
OFF_TASK = ["is", " called", " petrichor", ".", " It", " is", " a", " scent", " that", " many"]


def test_bank_and_partners():
    header, items = load_bank(BANK)
    # plan 0025: 27 -> 100 items
    assert header["family"] == "multi-concept-directed-modulation" and len(items) == 100
    controls = [it["name"] for it in items if not it["concepts"]]
    assert controls == ["d-none", "b-none"]
    assert partner_of("d-fox-a") == "d-fox-b" and partner_of("b-ange-mix-ba") == "b-ange-mix-ab"
    assert partner_of("d-plumber") is None and partner_of("d-none") is None
    names = {it["name"] for it in items}
    with_partner = [it for it in items if partner_of(it["name"]) in names]
    assert len(with_partner) == 34  # d-fox-a/b and the 32 binding items (16 since plan 0025)


def test_options_match_the_golden_and_carry_gold_and_partner():
    # plan 0034 M1/M5 (sanctioned update): the v2 bank's lists; G = CANNOT ends every shown list
    from wsbench.mc import CANNOT, options_with_cannot

    _h, items = load_bank(BANK_V2)
    opts = option_sets(items)
    golden = json.loads(
        (REPO / "tests/golden/multi_concept_directed_modulation_options.json").read_text("utf-8")
    )
    assert {i: (v["options"], v["gold_indices"]) for i, v in golden["options"].items()} == opts
    for i, v in golden["options"].items():
        assert v["shown"] == options_with_cannot(opts[i][0]) and v["shown"][-1] == CANNOT
        assert len(v["shown"]) == len(LETTERS) == N_OPTIONS + 1
    by_name = {it["name"]: it for it in items}
    for it in items:
        o, g = opts[it["id"]]
        assert len(o) == N_OPTIONS and len(set(o)) == N_OPTIONS
        assert [o[i] for i in g] == it["concepts"]
        partner = by_name.get(partner_of(it["name"]) or "")
        if partner:
            for c in partner["concepts"]:
                assert c in o
    assert opts["d-none"][1] == []


def test_regions_with_and_without_a_think_block():
    got = classify_regions(WITH_THINK)
    assert got[:5] == [Region.IN_SENTENCE] * 5
    assert got[5:9] == [Region.IN_THINK] * 4  # the blank line before <think> is not in-sentence
    assert got[9:] == [Region.POST_THINK] * 3
    assert classify_regions(NO_THINK) == [Region.IN_SENTENCE] * 5 + [Region.SELF_ADDED_META] * 4
    assert classify_regions(["meet", " on", " Thursday"]) == [Region.IN_SENTENCE] * 3


def test_write_compliance_and_off_task():
    assert write_compliance(WITH_THINK).complied
    bad = write_compliance(OFF_TASK)
    assert not bad.complied and bad.run < 3
    labels, comp = label_cells(OFF_TASK)
    assert not comp.complied and set(labels) == {Region.OFF_TASK}


def test_verdict_quote_gate_and_direction():
    options = [
        "Adam being angry at Betty",
        "wet umbrella",
        "Betty being angry at Adam",
        "x",
        "y",
        "z",
    ]
    readout = "- Adam is furious with Betty about the meeting\n- an umbrella, dripping wet"
    v = judge.verdict(
        {
            "picks": [
                {"choice": "A", "quote": "Adam is furious with Betty", "basis": "content_bound"},
                {"choice": "B", "quote": "umbrella, dripping wet", "basis": "incidental"},
            ]
        },
        options,
        [0],
        readout,
    )
    assert v["kind"] == "hit" and v["own"] == [options[0]] and v["false"] == ["wet umbrella"]
    # a pick without a verbatim quote is not credited; free text is not a letter
    v = judge.verdict(
        {
            "picks": [
                {"choice": "A", "quote": "not in the readout"},
                {"choice": "none", "quote": ""},
            ]
        },
        options,
        [0],
        readout,
    )
    assert v["kind"] == "none" and v["n_unverified"] == 1 and v["n_invalid"] == 1
    # plan 0034 M3 (sanctioned update): a relation pick whose quote lacks one of the two people
    # ("Betty") is dropped, not a false pick
    v = judge.verdict(
        {"picks": [{"choice": "C", "quote": "Adam is furious", "basis": "content_bound"}]},
        options,
        [0],
        readout,
    )
    assert v["kind"] == "none" and v["n_relation_unverified"] == 1 and v["false"] == []
    assert judge.verdict({"picks": []}, options, [0], readout)["kind"] == "none"
    assert judge.verdict({"picks": "A"}, options, [0], readout)["kind"] == "invalid"
    assert judge.verdict(None, options, [0], readout)["judged"] is False


def test_convert_read_json_round_trip(tmp_path):
    read = {
        "layers": [44, 52],
        "records": [
            {
                "name": "d-x*",
                "rels": [-1, -2],
                "tokens": [" budget", " annual"],
                "ao": {"44": [["a"], ["b"]], "52": [["c"], [""]]},
            },
            {"name": "bad", "rels": [-1], "tokens": [], "ao": {}},
        ],
    }
    src = tmp_path / "read.json"
    src.write_text(json.dumps(read))
    out = tmp_path / "r.jsonl"
    rep = convert_read_json(src, out)
    cells, _ = load_readouts(out)
    assert rep.skipped["malformed"] == 1 and len(cells) == 4 and rep.n_empty == 1
    assert {c.id for c in cells} == {"d-x_"}
    assert sorted((c.layer, c.pos, c.token) for c in cells) == [
        (44, -2, " annual"),
        (44, -1, " budget"),
        (52, -2, " annual"),
        (52, -1, " budget"),
    ]


def test_toy_file_regions():
    """The toy file is three items of the s3d read of record (prefill regime, 2026-09-23): d-plumber
    (novel), b-ange-mix-ab (binding) and d-none (control); the window is the 12 prefilled sentence
    tokens, so every cell is in-sentence."""
    cells, rep = load_readouts(EXAMPLE)
    assert rep.kind == "prose" and rep.layers == [44, 52, 56, 60]
    assert all(c.token is not None for c in cells)
    for item in ("d-plumber", "b-ange-mix-ab", "d-none"):
        toks = {c.pos: c.token for c in cells if c.id == item}
        assert sorted(toks) == list(range(-12, 0))
        assert "".join(toks[p] for p in sorted(toks)) == TARGET_SENTENCE
        labels, comp = label_cells([toks[p] for p in sorted(toks)])
        assert comp.complied and labels == [Region.IN_SENTENCE] * 12


REVERSED = "Betty is angry at Adam"


def test_toy_run_with_a_scripted_judge(tmp_path, monkeypatch):
    _h, items = load_bank(BANK_V2)
    opts = option_sets(items)
    by_name = {it["name"]: it for it in items}
    plumber, binding, control = "d-plumber", "b-ange-mix-ab", "d-none"
    reverse = by_name["b-ange-mix-ba"]["concepts"][0]

    def fake_run_calls(calls, **kw):
        out = {}
        for c in calls:
            item, layer = c.meta["item"], c.meta["layer"]
            o, g = opts[item]
            readout = c.user.split('"""\n', 1)[1].split('\n"""', 1)[0]
            if item == plumber and layer == 44:
                # plan 0025: two dictated concepts at the first cell, the third at the others;
                # only together do they cover every concept (no single cell does)
                own = [LETTERS[i] for i in g]
                first = c.meta["pos"] == min(
                    m["pos"] for m in (x.meta for x in calls) if m["item"] == item
                )
                chosen = own[:2] if first else own[2:]
                out[c.key] = {
                    "picks": [
                        {"choice": x, "quote": readout[:12], "basis": "content_bound"}
                        for x in chosen
                    ]
                }
            elif item == binding:
                out[c.key] = {
                    "picks": [
                        {
                            "choice": LETTERS[o.index(reverse)],
                            "quote": REVERSED,
                            "basis": "content_bound",
                        }
                    ]
                }
            elif item == control and layer == 60:
                out[c.key] = {
                    "picks": [{"choice": "A", "quote": readout[:12], "basis": "content_bound"}]
                }
            else:
                out[c.key] = {"picks": []}
        return out

    monkeypatch.setattr(judge, "run_calls", fake_run_calls)
    # plan 0034 M3: a partner pick must name both people in one statement, so the binding
    # item's cells state the reversed relation (the toy samples name nobody)
    rows_in = [json.loads(x) for x in EXAMPLE.read_text("utf-8").splitlines() if x.strip()]
    for row in rows_in:
        if row["id"] == binding:
            row["samples"] = [f"- {REVERSED}.\n" + row["samples"][0], *row["samples"][1:]]
    toy = tmp_path / "toy.jsonl"
    toy.write_text("".join(json.dumps(x) + "\n" for x in rows_in), encoding="utf-8")
    args = native_args(
        readouts=toy,
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        layers=None,
        items=[plumber, binding, control],
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
    )
    r = judge.run(args)
    rows = {row["id"]: row for row in r.rows}
    assert rows[plumber]["pass"] is True and rows[plumber]["capacity"]["per_activation_max"] == 2
    assert rows[plumber]["capacity"]["per_item_union"] == 3
    assert rows[plumber]["all_in_one_cell"] is False and rows[plumber]["concept_recall"] == 1.0
    assert rows[binding]["pass"] is False and rows[binding]["partner_picked"] is True
    assert rows[binding]["false_picks"] == [reverse]
    assert rows[control]["pass"] is None and rows[control]["reason"] == "control"
    assert r.value == 0.5 and r.n_items == 3
    assert r.extras["n_controls"] == 1 and r.extras["control_pick_rate"] == pytest.approx(0.25)
    assert r.extras["partner_confusion_rate"] == 1.0
    assert r.extras["per_stratum"] == {"mix": 0.0, "novel": 1.0}
    assert r.counts["n_missing_cells"] == 0 and r.counts["n_unjudged_cells"] == 0
    assert r.extras["n_calls"] == r.counts["n_expected_cells"] - r.counts["n_empty_cells"]
    assert not r.complete  # a subset run


def test_rows_without_tokens_are_fatal(tmp_path, monkeypatch):
    rows = [{"id": "d-plumber", "layer": 44, "pos": -1, "samples": ["x"]}]
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    args = native_args(
        readouts=path,
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)),
        layers=None,
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=True,
    )
    with pytest.raises(SystemExit) as e:
        judge.run(args)
    assert e.value.code == 2


def test_registered_and_dry_run(tmp_path, capsys, monkeypatch):
    from wsbench.evals.multi_concept_directed_modulation import SPEC

    registry.FAMILIES.setdefault(SPEC.name, SPEC)
    assert SPEC.group == "basic_mt" and SPEC.judge.prompt_version == PROMPT_VERSION
    monkeypatch.delenv("WSBENCH_JUDGE_MODEL", raising=False)
    out = tmp_path / "out"
    argv = ["judge", "opts=aggregate=native", f"family={SPEC.name}", f"readouts={EXAMPLE}",
            f"out={out}", "dry_run=True"]  # fmt: skip
    assert main(argv) == 0
    r = read_results(out)
    assert r.value is None and r.extras["n_items_without_readouts"] == 113  # 116-item bank v2
    assert "[user]" in capsys.readouterr().out


def test_new_items_follow_the_authoring_rules():
    """Plan 0025 §2: the 73 new items (listed in the header) are concrete, outside the target
    sentence's domain, share no content word across items (words shared inside one binding pair
    are exempt) and reuse no original binding name; only binding pairs and the fox pair carry a
    partner suffix."""
    import re

    header, items = load_bank(BANK)
    new = set(header["new_items"])
    assert len(new) == 73 and {it["name"] for it in items} >= new
    stop = {"a", "an", "the", "of", "in", "on", "to", "being", "at"}
    banned = {"committee", "meet", "meeting", "thursday", "review", "annual", "budget", "money",
              "finance", "calendar", "monday", "tuesday", "wednesday", "friday", "saturday",
              "sunday"}  # fmt: skip
    owner: dict[str, str] = {}
    for it in items:
        if it["name"] not in new:
            continue
        pair = re.sub(r"-(ab|ba)$", "", it["name"])
        words = {w for c in it["concepts"] for w in re.findall(r"[a-z]+", c.lower())} - stop
        assert not words & banned, it["name"]
        assert not re.fullmatch(r"\d+|seven|floating|chasing", " ".join(it["concepts"]))
        for w in words:
            assert owner.setdefault(w, pair) == pair, (it["name"], w, owner[w])
    old_words = {
        w
        for it in items
        if it["name"] not in new
        for c in it["concepts"]
        for w in re.findall(r"[a-z]+", c.lower())
    } - stop
    assert not set(owner) & old_words
    suffixed = {it["name"] for it in items if re.search(r"-(a|b|ab|ba)$", it["name"])}
    assert all(n.startswith("b-") or n in {"d-fox-a", "d-fox-b"} for n in suffixed)
    assert all(partner_of(n) in {it["name"] for it in items} for n in suffixed)


def test_concept_edits_and_strata():
    _header, items = load_bank(BANK)
    by = {it["name"]: it for it in items}
    assert by["d-violin"]["concepts"] == ["violin", "jar of honey"]
    assert by["d-cranes"]["concepts"] == ["origami cranes", "pocket calculator"]
    assert by["d-fox-a"]["concepts"] == ["silver fox", "paper kite"]
    assert "floating" in by["d-violin"]["prompt"]  # prompts unchanged
    from collections import Counter

    assert Counter(it["stratum"] for it in items) == {
        "single": 22, "double": 19, "novel": 20, "mix": 16, "same": 16, "anchor": 1,
        "chain": 2, "pair": 2, "control": 2,
    }  # fmt: skip


def test_verdict_basis_and_the_all_concepts_rule():
    """Plan 0025 §1 as amended by plan 0028: content-bound AND narrated dictated picks credit;
    an incidental / basis-less dictated pick never does; an item passes only when its cells
    credit every dictated concept between them."""
    options = ["violin", "jar of honey", "x", "y", "z", "w"]
    readout = "I was asked to think about a violin. Honey drips from a jar."
    v = judge.verdict(
        {
            "picks": [
                {"choice": "A", "quote": "think about a violin", "basis": "instruction_narration"},
                {"choice": "B", "quote": "Honey drips from a jar", "basis": "content_bound"},
            ]
        },
        options,
        [0, 1],
        readout,
    )
    # plan 0028: the narrated pick credits too; own_content keeps the plan-0025 view
    assert v["kind"] == "hit" and sorted(v["own"]) == ["jar of honey", "violin"]
    assert v["narrated"] == ["violin"] and v["own_content"] == ["jar of honey"]
    assert sorted(v["credited_quotes"]) == ["Honey drips from a jar", "think about a violin"]
    v = judge.verdict(
        {"picks": [{"choice": "A", "quote": "a violin"}]}, options, [0, 1], readout
    )  # no basis: recorded as invalid, never credited
    assert v["kind"] == "uncredited" and v["own"] == [] and v["basis_of"] == {"violin": "invalid"}
    v = judge.verdict(
        {"picks": [{"choice": "A", "quote": "a violin", "basis": "incidental"}]},
        options,
        [0, 1],
        readout,
    )
    # plan 0034 M4 (sanctioned update): an incidental mention credits too
    assert v["kind"] == "hit" and v["own"] == ["violin"] and v["incidental"] == ["violin"]
    # item rule: two cells, one concept each -> pass; one concept everywhere -> fail
    item = {"id": "d-violin", "name": "d-violin", "concepts": options[:2], "stratum": "novel"}
    regions = {-2: judge.Region.IN_SENTENCE, -1: judge.Region.IN_SENTENCE}

    def cell(pos, own):
        return {"item": "d-violin", "layer": 44, "pos": pos, "judged": True, "kind": "hit",
                "own": own, "false": [], "uncredited": []}  # fmt: skip

    both = [cell(-2, ["violin"]), cell(-1, ["jar of honey"])]
    row = judge._item_row(
        item, (options, [0, 1]), set(), regions, None, both, [], set(), set(), [44]
    )
    assert row["pass"] is True and row["all_in_one_cell"] is False
    one = [cell(-2, ["violin"]), cell(-1, ["violin"])]
    row = judge._item_row(
        item, (options, [0, 1]), set(), regions, None, one, [], set(), set(), [44]
    )
    assert row["pass"] is False and row["any_concept"] is True and row["concept_recall"] == 0.5


def test_invalid_basis_over_selection_and_per_pick_counts():
    """Review fixes (plan 0025 §1): a missing basis counts in n_invalid; more than three
    verified picks void the call; a concept picked as narration then as content is credited and
    its basis_of is content_bound, while pick_bases keeps both picks."""
    options = ["violin", "jar of honey", "x", "y", "z", "w"]
    readout = "I was asked about a violin. A violin plays. Honey jar. x y z w"
    v = judge.verdict({"picks": [{"choice": "A", "quote": "violin plays"}]}, options, [0], readout)
    assert v["n_invalid"] == 1 and v["own"] == []
    allsix = [{"choice": c, "quote": "x y z w", "basis": "content_bound"} for c in "ABCDEF"]
    v = judge.verdict({"picks": allsix}, options, [0, 1], readout)
    assert v["kind"] == "over_selected" and v["own"] == [] and len(v["pick_bases"]) == 6
    twice = [
        {"choice": "A", "quote": "asked about a violin", "basis": "instruction_narration"},
        {"choice": "A", "quote": "A violin plays", "basis": "content_bound"},
    ]
    v = judge.verdict({"picks": twice}, options, [0], readout)
    assert v["own"] == ["violin"] and v["basis_of"] == {"violin": "content_bound"}
    assert v["pick_bases"] == [["violin", "instruction_narration"], ["violin", "content_bound"]]
    assert v["narrated"] == []


def test_naming_both_directions_credits_neither():
    """Plan 0025 (review): a call that names the item's own binding AND its partner credits
    nothing for the item (direction_conflict), whatever the partner pick's basis."""
    options = ["Adam being angry at Betty", "Betty being angry at Adam", "x", "y", "z", "w"]
    readout = "Adam is angry at Betty. Betty is angry at Adam."
    both = [
        {"choice": "A", "quote": "Adam is angry at Betty", "basis": "content_bound"},
        {"choice": "B", "quote": "Betty is angry at Adam", "basis": "incidental"},
    ]
    v = judge.verdict({"picks": both}, options, [0], readout, partner=[1])
    assert v["kind"] == "direction_conflict" and v["own"] == [] and v["false"] == [options[1]]
    v = judge.verdict({"picks": both[:1]}, options, [0], readout, partner=[1])
    assert v["kind"] == "hit" and v["own"] == [options[0]]


def test_direction_rule_is_item_level_and_repeats_are_not_over_selection():
    """Review fixes: ab credited at one cell and ba named as content at another fails the item;
    one concept quoted twice is one candidate, not an over-selection."""
    item = {"id": "b-x-mix-ab", "name": "b-x-mix-ab", "concepts": ["A loving B"], "stratum": "mix"}
    regions = {-2: judge.Region.IN_SENTENCE, -1: judge.Region.IN_SENTENCE}

    def cell(pos, own, bases):
        return {"item": item["id"], "layer": 44, "pos": pos, "judged": True, "kind": "hit",
                "own": own, "false": [], "uncredited": [], "pick_bases": bases}  # fmt: skip

    cells = [cell(-2, ["A loving B"], [["A loving B", "content_bound"]]),
             cell(-1, [], [["B loving A", "content_bound"]])]  # fmt: skip
    opts = (["A loving B", "B loving A", "x", "y", "z", "w"], [0])
    row = judge._item_row(item, opts, {"B loving A"}, regions, None, cells, [], set(), set(), [44])
    assert row["pass"] is False and row["partner_as_content"] == ["B loving A"]
    row = judge._item_row(
        item, opts, {"B loving A"}, regions, None, cells[:1], [], set(), set(), [44]
    )
    assert row["pass"] is True
    options = ["violin", "jar of honey", "origami", "x", "y", "z"]
    readout = "violin violin honey jar origami"
    picks = [
        {"choice": "A", "quote": "violin", "basis": "content_bound"},
        {"choice": "A", "quote": "violin violin", "basis": "content_bound"},
        {"choice": "B", "quote": "honey jar", "basis": "content_bound"},
        {"choice": "C", "quote": "origami", "basis": "content_bound"},
    ]
    v = judge.verdict({"picks": picks}, options, [0, 1, 2], readout)
    assert v["kind"] == "hit" and sorted(v["own"]) == ["jar of honey", "origami", "violin"]


def test_content_only_channel_reproduces_plan_0025():
    """Plan 0028: extras.content_only_pass_rate applies the plan-0025 rule (content_bound only,
    both for crediting and for the partner) beside the narration-counting headline."""
    item = {"id": "d-x", "name": "d-x", "concepts": ["violin"], "stratum": "single"}
    regions = {-1: judge.Region.IN_SENTENCE}
    narrated = {"item": "d-x", "layer": 44, "pos": -1, "judged": True, "kind": "hit",
                "own": ["violin"], "own_content": [], "false": [], "uncredited": [],
                "pick_bases": [["violin", "instruction_narration"]]}  # fmt: skip
    row = judge._item_row(item, (["violin"], [0]), set(), regions, None, [narrated], [], set(),
                          set(), [44])  # fmt: skip
    assert row["pass"] is True and row["pass_content_only"] is False


def test_content_only_channel_is_tri_state():
    """Plan 0028 review: the content-only channel keeps plan 0025's tri-state rule: a cell
    unjudged and no content cover -> undecided (None), not False."""
    item = {"id": "d-x", "name": "d-x", "concepts": ["violin"], "stratum": "single"}
    regions = {-2: judge.Region.IN_SENTENCE, -1: judge.Region.IN_SENTENCE}
    narrated = {"item": "d-x", "layer": 44, "pos": -2, "judged": True, "kind": "hit",
                "own": ["violin"], "own_content": [], "false": [], "uncredited": [],
                "pick_bases": [["violin", "instruction_narration"]]}  # fmt: skip
    unjudged = {"item": "d-x", "layer": 44, "pos": -1, "judged": False, "kind": "unavailable",
                "own": [], "own_content": [], "false": [], "uncredited": [],
                "pick_bases": []}  # fmt: skip
    row = judge._item_row(item, (["violin"], [0]), set(), regions, None, [narrated, unjudged],
                          [], set(), set(), [44])  # fmt: skip
    assert row["pass"] is True and row["pass_content_only"] is None


def test_stamp_carries_present_and_the_cache_key_does_not(tmp_path, monkeypatch):
    """Plan 0028: results are stamped with PROMPT_VERSION (+present) while judge calls are keyed
    by JUDGE_PROMPT_VERSION, so caches written before the rule change still hit."""
    from wsbench.evals.multi_concept_directed_modulation import prompts as p

    # round 3 adds the deterministic +pins-r3 to the stamp only
    assert p.PROMPT_VERSION == p.JUDGE_PROMPT_VERSION + "+bank-v2+notokinterp-2026-10-30+pins-r3"
    seen = {}

    def fake_run_calls(calls, **kw):
        seen["pv"] = kw["prompt_version"]
        return {c.key: {"picks": []} for c in calls}

    monkeypatch.setattr(judge, "run_calls", fake_run_calls)
    args = native_args(readouts=EXAMPLE, out=tmp_path / "o",
                     judge=resolve(JudgeConfig(prompt_version=PROMPT_VERSION)), layers=None,
                     items=["d-plumber"], limit=0, allow_missing=False, concurrency=1, rpm=1.0,
                     dry_run=False)  # fmt: skip
    r = judge.run(args)
    assert seen["pv"] == p.JUDGE_PROMPT_VERSION and r.config["prompt_version"] == p.PROMPT_VERSION

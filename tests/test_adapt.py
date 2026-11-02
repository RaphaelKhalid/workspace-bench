"""Offline tests for wsbench.adapt: graders, legs, lint, generators, selection, bank root."""

import copy
from pathlib import Path

import pytest

from wsbench import registry
from wsbench.adapt import families as fams
from wsbench.adapt.gate import Ask, gate_record, grade_leg
from wsbench.adapt.generate import GENERATORS, generate
from wsbench.adapt.lint import lint
from wsbench.adapt.run import restamp, select
from wsbench.adapt.store import original_bank
from wsbench.adapt.subjects import remap_layers


@pytest.fixture(autouse=True)
def _no_token_wait(monkeypatch):
    """Session.refresh polls the Dict for minutes after a 401; offline tests must not wait."""
    from wsbench.adapt import auth

    monkeypatch.setattr(auth, "REFRESH_WAIT", 0.0)


def _leg(ask, greedy, samples, threshold=0.8):
    return grade_leg(ask, greedy, samples, threshold)


def test_contains_and_rule():
    ask = Ask("x", "surface", ("iron",))
    assert _leg(ask, "Iron", ["iron."] * 8 + ["copper"] * 2).passed
    assert not _leg(ask, "Iron", ["iron"] * 7 + ["copper"] * 3).passed  # 7/10 < 8/10
    assert not _leg(ask, "copper", ["iron"] * 10).passed  # greedy must be right
    assert not _leg(ask, "ironic", ["ironic"] * 10).passed  # whole words only


def test_number_words():
    assert _leg(Ask("x", "surface", ("5",)), "five", ["Five."] * 10).passed
    assert _leg(Ask("x", "surface", ("three",)), "3", ["3"] * 10).passed


def test_number_and_forbid():
    ask = Ask("x", "surface", ("2",), grade="number", meta={"forbid": ["11", "5"]})
    assert _leg(ask, "2", ["2"] * 10, 1.0).passed
    leg = _leg(ask, "2", ["2"] * 9 + ["23 -> 11 -> 5 -> 2"], 1.0)
    assert not leg.passed and leg.rate == 0.9  # writing an intermediate fails the sample


def test_own_word_and_rhyme():
    ask = Ask("x", "surface", (), prompt="p", grade="own", meta={"rhymes_with": "ahead"})
    leg = _leg(ask, "led the way", ["led"] * 9 + ["went"])
    assert leg.passed and leg.own == "led"
    assert not _leg(ask, "went", ["went"] * 10).passed  # consistent but no rhyme
    assert not _leg(ask, "1ead", ["1ead"] * 10).passed  # not an English word


def test_compliance():
    ask = Ask("x", "surface", ("The sky is blue",), grade="compliance", meta={"concept": "owl"})
    assert _leg(ask, '"The sky is blue."', ["The sky is blue"] * 10).passed
    assert not _leg(ask, "The sky is blue, like an owl", ["The sky is blue"] * 10).passed


def test_leg_groups_render_alternatives_and_bridges():
    good = _leg(Ask("x", "surface", ("Fe",)), "Fe", ["Fe"] * 10)
    bad = _leg(Ask("x", "surface", ("Fe",)), "iron", ["iron"] * 10)
    bridge_bad = _leg(Ask("x", "bridge1", ("iron",)), "zinc", ["zinc"] * 10)
    assert gate_record({"surface": bad, "surface:plain": good})["pass"]  # one render is enough
    assert not gate_record({"surface": good, "bridge1": bridge_bad})["pass"]  # bridges must pass


def test_every_gated_family_builds_questions_for_its_bank():
    for name, fam in fams.FAMILIES.items():
        _h, items = original_bank(name)
        asks = [a for it in items[:5] for a in fam.asks(it)]
        assert asks, name
        assert all(a.messages or a.prompt for a in asks), name


@pytest.mark.parametrize("family", sorted(GENERATORS))
def test_generators_lint_clean_at_every_tier(family):
    for tier in GENERATORS[family].tiers:
        items = generate(family, tier.name, 40, 0, set())
        assert len(items) >= 40
        bad = [(it, p) for it in items if (p := lint(family, it))]
        assert not bad, bad[:2]
        assert all(it["adapt"]["tier"] == tier.name for it in items)


def test_chain_floor_keeps_an_intermediate():
    for it in generate("chain_intermediates", "t2", 50, 1, set()):
        assert it["depth"] >= 2 and it["intermediates"]


def test_select_keeps_pairs_atomic_and_prefers_originals():
    def row(i, scene, ok, origin="original"):
        return {
            "id": i,
            "origin": origin,
            "item": {"id": i, "scene": scene},
            "gate": {"pass": ok},
        }

    rows = [
        row("s0-a", "s0", True),
        row("s0-b", "s0", False),
        row("s1-a", "s1", True),
        row("s1-b", "s1", True),
        row("n0-a", "n0", True, "generated"),
        row("n0-b", "n0", True, "generated"),
    ]
    chosen = [r["id"] for r in select("relational_multihop", rows, 10)]
    assert chosen == ["s1-a", "s1-b", "n0-a", "n0-b"]
    assert [r["id"] for r in select("relational_multihop", rows, 3)] == ["s1-a", "s1-b"]


def test_select_keeps_named_twins_together():
    def row(i, pair, ok):
        return {
            "id": i,
            "origin": "original",
            "item": {"name": i, "pair": pair},
            "gate": {"pass": ok},
        }

    rows = [
        row("subsub-0", "subsubx-0", True),
        row("subsubx-0", "subsub-0", False),
        row("subsub-1", "subsubx-1", True),
        row("subsubx-1", "subsub-1", True),
        row("addmul-0", "addmulx-0", True),
    ]  # a twin absent from the bank: kept alone
    chosen = [r["id"] for r in select("arithmetic_intermediates", rows, 10)]
    assert chosen == ["subsub-1", "subsubx-1", "addmul-0"]


def test_restamp_poetry_and_implicit():
    rec = {"legs": {"surface": {"own": "noon"}}}
    item = restamp("poetry", {"name": "p", "intermediates": ["June"]}, rec)
    assert item["intermediates"] == ["noon"] and item["authored_rhyme"] == "June"
    imp = {"name": "i", "subfamily": "implicit", "target": "poker", "units": [{"match": ["poker"]}]}
    out = restamp("basic_readout", imp, {"legs": {"surface": {"own": "chess"}}})
    assert out["target"] == "chess" and out["units"][0]["match"] == ["chess"]


def test_lint_rejects_leaks():
    it = generate("chain_intermediates", "t1", 1, 0, set())[0]
    it["prompt"] += f" Hint: {it['intermediates'][0]}."
    assert any(p.startswith("leak") for p in lint("chain_intermediates", it))


def test_remap_layers():
    assert remap_layers(list(range(20, 61, 4)), 32) == list(range(10, 31, 2))
    assert len(remap_layers(list(range(20, 61, 4)), 24)) <= 11


def test_bank_root_override(tmp_path, monkeypatch):
    assert registry.bank_path("typo") == registry.REPO_ROOT / "evals" / "typo" / "items.json"
    (tmp_path / "typo.json").write_text("[]")
    monkeypatch.setenv(registry.BANK_ROOT_ENV, str(tmp_path))
    assert registry.bank_path("typo") == tmp_path / "typo.json"
    with pytest.raises(SystemExit):  # never a silent fall-back to another model's bank
        registry.bank_path("poetry")


def test_select_respects_quota():
    def row(i, v):
        return {
            "id": i,
            "origin": "original",
            "item": {"name": i, "variant": v},
            "gate": {"pass": True},
        }

    rows = [row("a0", "a"), row("a1", "a"), row("a2", "a"), row("b0", "b")]
    chosen = select("arithmetic_intermediates", rows, 10, {"a": 2, "b": 1})
    assert [r["id"] for r in chosen] == ["a0", "a1", "b0"]


def test_arithmetic_null_sets_separated():
    from wsbench.adapt.gen_arith import null_sets

    items = generate("arithmetic_intermediates", "t1", 60, 0, set(), only=["addmul"])
    null_sets(items)
    for it in items:
        mine = float(it["intermediates"][0])
        assert it["name"] not in it["null_set"]
        by = {o["name"]: o for o in items}
        for n in it["null_set"]:
            other = float(by[n]["intermediates"][0])
            assert abs(mine - other) > 0.2 * max(abs(mine), abs(other))


def test_author_briefs_render_offline(tmp_path, monkeypatch):
    from wsbench.adapt import author, store

    monkeypatch.setattr(store, "model_dir", lambda model, root=None: tmp_path / model)
    for family, brief in author.BRIEFS.items():
        text = author.render_brief("demo", family, next(iter(brief.tiers)), 5, "steer me")
        assert family in text and "steer me" in text
        assert all(inv in text for inv in brief.invariants)
        # few-shots come from the bank when the subject has passed nothing yet
        assert '"' + next(iter(brief.keys)) + '"' in text


def test_auth_has_no_key_fallback(monkeypatch):
    from wsbench.adapt import auth

    monkeypatch.delenv("WSB_ANTHROPIC_AUTH", raising=False)
    monkeypatch.setattr(auth, "read_token", lambda: (None, None))
    with pytest.raises(SystemExit, match="push-judge-token"):
        auth.client()


def test_mt_build_roundtrip_and_stamp():
    from wsbench.adapt import author, mt
    from wsbench.adapt.lint import lint

    class Tok:  # one token per 4 characters: deterministic, offline
        def encode(self, s, add_special_tokens=False):
            return list(range(max(1, len(s) // 4)))

    # multihop_mt was removed 2026-10-30; multilingual_multihop is the other bridge family the
    # same lint rule (bridge vs answer) covers
    fam = "multilingual_multihop"
    _h, items = original_bank(fam)
    orig = next(  # a canonical bridge name of >= 2 fake tokens (the fake counts 4 chars a token)
        i for i in items if i["subfamily"] == "2hop" and len(i["units"][1]["forms"]["en"][0]) >= 8
    )
    flat = {k: v for k, v in author._flat_mt(orig).items() if k in author.BRIEFS[fam].keys}
    built = mt.stamp(author._mt_multilingual_multihop(dict(flat)), Tok())
    assert built["units"][1]["forms"] == orig["units"][1]["forms"]
    assert built["bridges"][0]["question"] == orig["bridges"][0]["question"]
    assert built["units"][1]["match"] == orig["units"][1]["match"]
    built.update(author.MT_FIXED)
    assert not [p for p in lint(fam, built) if not p.startswith("leak")]


def test_author_parse_survives_one_bad_object():
    from wsbench.adapt.author import _parse

    good = '{"name": "a", "prompt": "x"}'
    text = f'```json\n[\n {good},\n {{"name": "b", "prompt": "bad "quote" here"}},\n {good}\n]\n```'
    objs, bad = _parse(text)
    assert len(objs) == 2 and bad == 1


def test_multilingual_mt_build_roundtrip():
    from wsbench.adapt import author

    _h, items = original_bank("multilingual_mt")
    orig = items[0]
    keys = author.BRIEFS["multilingual_mt"].keys
    flat = {k: v for k, v in author._flat_mt(orig).items() if k in keys}
    built = author._mt_multilingual(dict(flat))
    assert [u["forms"] for u in built["units"]] == [u["forms"] for u in orig["units"]]
    assert built["mc"]["concept"] == orig["mc"]["concept"]


def test_multilingual_build_roundtrip_emits_v2():
    """Review r2 item 1: the ``multilingual`` brief builds the v2 item (concept_native +
    names-only language, mc_roles, digits on number concepts), so a port is never v1-shaped."""
    from wsbench.adapt import author

    _h, items = original_bank("multilingual")
    keys = author.BRIEFS["multilingual"].keys
    for orig in items:
        flat = {k: v for k, v in author._flat_mt(orig).items() if k in keys}
        built = author._ml_multilingual(copy.deepcopy(flat))
        assert [u["forms"] for u in built["units"]] == [u["forms"] for u in orig["units"]]
        for b, o in zip(built["units"], orig["units"], strict=True):
            assert b.get("numeric_match") == o.get("numeric_match")
            assert b.get("case_sensitive") == o.get("case_sensitive"), orig["name"]
        assert built["mc"] == orig["mc"] and built["mc_roles"] == orig["mc_roles"]
        assert built["intermediates"] == orig["intermediates"]


def test_leak_leg_and_threshold_override():
    leak = Ask("x", "leak", ("grief",), prompt="p", grade="contains",
               meta={"leak": True, "max_rate": 0.0})  # fmt: skip
    assert _leg(leak, "She walked home.", ["She sat."] * 10).passed
    assert not _leg(leak, "She walked home.", ["grief took her"] + ["She sat."] * 9).passed
    loose = Ask("x", "leak", ("grief",), prompt="p", grade="contains",
                meta={"leak": True, "max_rate": 2 / 11})  # fmt: skip
    assert _leg(loose, "ok", ["grief"] + ["fine"] * 9).passed
    greedy_only = Ask("x", "surface", ("police",), meta={"threshold": 0.0})
    assert _leg(greedy_only, "the police", ["thief"] * 10).passed


def test_source_gates_for_prose_families():
    for fam, legs in [("conjunctive_association", {"leak"}),
                      ("role_bound_association", {"surface", "leak"})]:  # fmt: skip
        _h, items = original_bank(fam)
        assert {a.leg for a in fams.get(fam).asks(items[0])} == legs


def test_select_skips_new_items_repeating_a_latent():
    def row(i, origin, latent):
        return {
            "id": i,
            "origin": origin,
            "item": {"name": i, "intermediates": [latent]},
            "gate": {"pass": True},
        }

    rows = [
        row("o1", "original", "Rainbow"),
        row("o2", "original", "rainbow"),  # originals are never dropped
        row("n1", "authored", "rainbow "),
        row("n2", "authored", "kettle"),
        row("n3", "authored", "Kettle"),
    ]
    chosen = [r["id"] for r in select("association", rows, 10)]
    assert chosen == ["o1", "o2", "n2"]


def test_own_grade_rejects_a_refusal_as_the_gold():
    msgs = ({"role": "user", "content": "q"},)
    ask = Ask("x", "surface", (), msgs, grade="own", meta={"no_refusal": True})
    assert not grade_leg(ask, "**None**.", ["None."] * 10, 0.8).passed
    assert grade_leg(ask, "Blue.", ["Blue"] * 9 + ["Red"], 0.8).passed
    moral = Ask("y", "surface", (), msgs, grade="own")  # "A" is a real choice elsewhere
    assert grade_leg(moral, "A", ["A"] * 10, 0.8).passed


def test_verify_python_records_real_behaviour():
    from wsbench.adapt.verify import verify_python

    assert verify_python("print(7 // 2)\nprint('a')") == "exec: exit 0; stdout = '3 | a'"
    crash = verify_python("print({}['k'])")
    assert crash.startswith("exec: exit 1; stdout = ''; last = 'KeyError")
    assert verify_python("import random\nprint(random.random())") is None  # nondeterministic


def test_session_switches_to_a_newer_token_on_401(monkeypatch):
    from wsbench.adapt import auth

    pushes = iter([("t1", 100.0), ("t1", 100.0), ("t2", 200.0)])
    monkeypatch.setattr(auth, "read_token", lambda: next(pushes))
    monkeypatch.setattr(auth, "_build", lambda token: f"client:{token}")
    s = auth.Session()
    assert not s.refresh(s.pushed, wait=0)  # the Dict still holds the same token: really expired
    assert s.refresh(s.pushed) and s.client == "client:t2"
    assert s.refresh(100.0)  # another thread already switched


def test_moral_look_for_and_side():
    from wsbench.adapt.moral import _look_for, _normalize

    reasons = [
        {"text": "a", "supports": "no"},
        {"text": "b", "supports": "yes"},
    ]
    assert _look_for(reasons, "deliberative") == ("deliberative", ["b", "a"])
    assert _look_for(reasons[:1], "deliberative") == ("committed", ["a"])  # one side: demoted
    assert _normalize("False.") == ("no", True)
    assert _normalize("Yes, because") == ("yes", False)  # not one word: not precise


def test_readplan_uses_subject_layers_under_an_adapted_root(tmp_path, monkeypatch):
    import json as _json

    from wsbench import readplan

    (tmp_path / "report.json").write_text(_json.dumps({"n_layers": 32}))
    bank = _json.loads((registry.REPO_ROOT / "evals/agentic_misalignment/items.json").read_text())
    (tmp_path / "agentic_misalignment.json").write_text(_json.dumps(bank))
    monkeypatch.setenv(registry.BANK_ROOT_ENV, str(tmp_path))
    layers = readplan.plan("agentic_misalignment")[0].layers
    assert layers[0] == 10 and layers[-1] == 31  # GRID halved; 63 clamps to the last block


def test_jsonl_readers_keep_unicode_line_separators(tmp_path):
    import json as _json

    from wsbench.readouts import load_readouts

    row = {"id": "a", "layer": 10, "pos": 3, "samples": ["one\u2028two"]}
    p = tmp_path / "r.jsonl"
    p.write_text(_json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    cells, _rep = load_readouts(p)
    assert len(cells) == 1  # U+2028 inside a JSON string must not split the row


def test_regrade_keeps_moral_checks():
    from wsbench.adapt.run import _regrade_row

    item = {"id": "m1", "stimulus": "Is it OK? Answer yes or no.", "answer_format": "yes_no",
            "reasons": [{"text": "r", "supports": "no"}], "needs_reasons": False}  # fmt: skip
    leg = {"greedy": {"text": "No", "ok": True}, "samples": [{"text": "No", "ok": True}] * 10}
    row = {"id": "m1", "origin": "original", "item": item,
           "gate": {"pass": False, "legs": {"surface": leg},
                    "moral": {"consistent": True, "aligned": False}}}  # fmt: skip
    new = _regrade_row("moral_rationale", row, grade=None)
    assert new["gate"]["moral"]["aligned"] is False and new["gate"]["pass"] is False
    assert new["item"]["needs_reasons"] is False  # distilled reasons are not reset


def test_lint_catches_the_audit_defect_classes():
    from wsbench.adapt.gate import Ask, grade_leg

    # multilingual: 'pommier' carries the target 'pomme' (audit 4B fr-fruit-apple-tree)
    ml = {"name": "x", "prompt": 'Le fruit du pommier est la "', "target": "pomme",
          "intermediates": ["apple"], "eval_render": "plain", "readout": {}}  # fmt: skip
    assert any("stem" in p for p in lint("multilingual", ml))
    # multilingual_multihop: bridge 'Sydney Opera House' overlaps the answer 'Sydney' (audit 9B)
    mh = {"name": "y", "subfamily": "2hop", "prompt": "Gedung opera itu ada di kota", "target":
          "Sydney", "target_alts": [], "readout": {"kind": "final_prompt_token"},
          "units": [{"role": "bridge_native", "required": True, "multi_token": True,
                     "forms": {"en": ["Sydney Opera House"]}}],
          "probe_token_lens": {"units": {"bridge_native": {"en": [3]}}}}  # fmt: skip
    assert any("overlaps" in p for p in lint("multilingual_multihop", mh))
    # poetry: a rhyme already written in line 2 is never a passing gold (audit 4B hug/rug -> bug)
    stub = "As snug as a bug in a "
    ask = Ask("p", "surface", (), prompt=f"A rhyming couplet:\nGive me a hug,\n{stub}",
              grade="own", meta={"rhymes_with": "hug", "stub": stub})  # fmt: skip
    assert not grade_leg(ask, "bug", ["bug"] * 10, 0.8).passed


def test_generation_goes_through_the_runner():
    """Only gate.Runner owns a vLLM engine: every other adapt step generates through
    ``run._runner(model)`` so a ``backend="modal"`` subject (Gemma-4-31B) works everywhere."""
    import re

    root = Path(__file__).resolve().parents[1] / "src/wsbench/adapt"
    for f in root.glob("*.py"):
        if f.name == "gate.py":
            continue
        src = f.read_text()
        assert not re.search(r"\bLLM\(", src), f"{f.name} builds its own vLLM engine"
        assert ".llm.generate" not in src, f"{f.name} bypasses Runner.generate"


class _StubTok:
    """A word-level ChatML-ish tokenizer; ``think`` leaves <think> open in the generation prompt."""

    def __init__(self, think=False, system_ok=True):
        self.think, self.system_ok, self.vocab = think, system_ok, []

    def _id(self, t):
        if t not in self.vocab:
            self.vocab.append(t)
        return self.vocab.index(t)

    def apply_chat_template(self, msgs, tokenize=True, add_generation_prompt=True, **_):
        if not self.system_ok and any(m["role"] == "system" for m in msgs):
            raise ValueError("system role not supported")
        toks = []
        for m in msgs:
            toks += ["<s>", m["role"], "\n", m["content"], "</s>", "\n"]
        toks += ["<s>", "assistant", "\n"] + (["<think>", "\n"] if self.think else [])
        return [self._id(t) for t in toks] if tokenize else "".join(toks)

    def decode(self, ids, skip_special_tokens=False):
        return "".join(self.vocab[i] for i in ids)


def test_template_check_flags_open_think_and_system_rejection():
    from wsbench.adapt.template import check, markers

    assert check(_StubTok()) == []
    assert markers(_StubTok())["turn_end"] == "</s>"
    assert any("reasoning block open" in p for p in check(_StubTok(think=True)))
    assert any("system turn" in p for p in check(_StubTok(system_ok=False)))


def test_live_rows_restamps_before_select_for_a_new_tokenizer(monkeypatch):
    """Audit #18: on a non-Qwen tokenizer an item that loses its multi-token form is not live, so
    fill/select never count an item freeze would drop."""
    from types import SimpleNamespace

    from wsbench.adapt import run, store

    rows = {i: {"id": i, "item": {"id": i}, "origin": "original", "gate": {"pass": True}}
            for i in ("a", "b")}  # fmt: skip
    monkeypatch.setattr(store, "gated", lambda m, f: rows)
    monkeypatch.setattr(run, "restamp_tokens", lambda m, f, items: ([items[0]], ["note"]))
    monkeypatch.setattr(run, "get_subject", lambda m: SimpleNamespace(tokenizer="dolma2"))
    assert [r["id"] for r in run.live_rows("x", "typo_mt", {})] == ["a"]
    monkeypatch.setattr(run, "get_subject", lambda m: SimpleNamespace(tokenizer="qwen3.6"))
    assert len(run.live_rows("x", "typo_mt", {})) == 2


def test_arith_cell_reanchored_on_the_subject_turn_end():
    """Audit #3: arithmetic ``cell.pos`` (-8 = 1 token past the Qwen user turn's closing marker)
    names the same structural token in a shorter template."""
    from wsbench.adapt.run import _restamp_arith_cells

    tok = _StubTok()  # tail after </s>: "\n", "<s>", "assistant", "\n" (4 tokens)
    items = [{"name": "a", "prompt": "P", "cell": {"layer": 56, "pos": -8}},
             {"name": "b", "prompt": "P", "cell": {"layer": 56, "pos": -7}}]  # fmt: skip
    out, notes = _restamp_arith_cells(tok, items)
    assert [i["cell"]["pos"] for i in out] == [-4, -3]
    assert out[0]["cell"]["pos_qwen"] == -8 and "2 moved" in notes[0]


def test_freeze_drops_arith_items_with_small_null_pool():
    """Audits 4B #9 / 9B #5 / 35B-A3B: an item with < 8 separable peers has no permutation null."""
    from wsbench.adapt.run import _post_freeze

    def it(name, variant, val, pair=None):
        return {"name": name, "variant": variant, "intermediates": [str(val)],
                "tolerance": "exact", "pair": pair}  # fmt: skip

    items = [it(f"a{i}", "big", 10 * i) for i in range(12)]
    items += [
        it("s0", "small", 1, pair="s1"),
        it("s1", "small", 2, pair="s0"),
        it("s2", "small", 3),
    ]
    notes = _post_freeze("arithmetic_intermediates", {"variants": {}}, items, 0)
    assert {i["name"] for i in items} == {f"a{i}" for i in range(12)}
    assert any("3 items dropped: null pool under 8" in n for n in notes)


def test_remap_layers_snaps_to_the_subject_read_band():
    """Qwen3-8B's OLens reads even layers 12..34: plan and bank layers must be lens layers."""
    grid = [20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60]
    band = tuple(range(12, 35, 2))
    assert remap_layers(grid, 36, band) == [12, 14, 16, 18, 20, 22, 26, 28, 30, 32, 34]
    assert remap_layers(grid, 32) == list(range(10, 31, 2))  # no band: depth remap only


def test_strict_form_needs_the_accents_in_the_deterministic_match():
    """OLMo-32B audit: fold() strips accents, so "frio" passed for "frío" pre-grader."""
    asks = fams.FAMILIES["multilingual"].asks(
        {
            "name": "x",
            "prompt": "Lo contrario de caliente es ",
            "target": "frío",
            "intermediates": ["cold"],
        }
    )
    ask = next(a for a in asks if a.meta.get("strict_form"))
    assert grade_leg(ask, "Frío.", ["frío"] * 10, 0.8).passed
    assert not grade_leg(ask, "frio", ["frio"] * 10, 0.8).passed  # no llm: undecided, never a pass


def test_role_bound_names_are_rewritten_to_roles_before_grading():
    """OLMo-7B named the people (150/160): grade the binding in roles, direction intact."""
    item = {"id": "x", "stimulus": "S", "asked_question": "Q",
            "gold_label": "the cop chased the thief", "names": {"a": "Marcus", "b": "Dylan"},
            "role_a": "cop", "role_b": "thief"}  # fmt: skip
    ask = fams.FAMILIES["role_bound_association"].asks(item)[0]
    seen = []
    grade_leg(
        ask, "Marcus chased Dylan.", [], 0.0, llm=lambda a, ts: seen.extend(ts) or [True] * len(ts)
    )
    assert seen == ["the cop (Marcus) chased the thief (Dylan)."]


def test_own_word_skips_echoed_poetry_stub():
    from wsbench.adapt.gate import own_word

    stub = "Her voice rang out as clear as a "
    assert own_word("clear as a bell", stub) == "bell"
    assert own_word("bell", stub) == "bell"
    assert own_word("Her voice rang out as clear as a bell.", stub) == "bell"
    assert own_word("clear as a bell") == "clear"  # no stub: unchanged
    assert own_word("a", stub) == "a"  # never strips the whole answer


def test_role_bound_strict_requires_stated_roles(monkeypatch):
    from wsbench.adapt import families as fams
    from wsbench.adapt.gate import _states_role, grade_leg

    item = {
        "id": "x",
        "stimulus": "Tony shaved Hank.",
        "asked_question": "Who did what?",
        "gold_label": "the barber shaved the fisherman",
        "role_a": "barber",
        "role_b": "fisherman",
        "names": {"a": "Tony", "b": "Hank"},
    }
    assert _states_role("The barbers shaved him", "barber")
    assert not _states_role("Tony shaved Hank.", "pizza delivery driver")
    monkeypatch.setenv("ADAPT_ROLE_BOUND_STRICT", "1")
    ask = next(a for a in fams.get("role_bound_association").asks(item) if a.leg == "surface")
    assert ask.meta["require_roles"] == ["barber", "fisherman"] and "name_roles" not in ask.meta

    def always_yes(_ask, texts):
        return [True for _ in texts]

    names_only = grade_leg(ask, "Tony shaved Hank.", [], 0.0, always_yes)
    roles = grade_leg(ask, "The barber shaved the fisherman.", [], 0.0, always_yes)
    assert names_only.greedy["ok"] is False and roles.greedy["ok"] is True


def test_role_bound_lint_flags_unlexiconed_role():
    """plan 0055 C2.5: an authored role missing from roles_v1.json is flagged; the judge then
    falls back to terms=[role] with no near-role distractor, counted in n_roles_unlexiconed."""
    from wsbench.evals.role_bound_association import gate
    from wsbench.evals.role_bound_association.judge import build_block_v2
    from wsbench.mcjudge import load_bank

    item = {
        "id": "x-ab",
        "pair_id": "x",
        "direction": "ab",
        "stimulus": "Tony shaved Hank before the morning rush.",
        "asked_question": "Who did what to whom?",
        "gold_label": "the barber shaved the police officer",
        "role_a": "barber",
        "role_b": "police officer",
        "action": "shaved",
        "names": {"a": "Tony", "b": "Hank"},
        "blocklist": {"roles": ["barber"]},
        "adapt": {"origin": "authored", "tier": "t2"},
    }
    problems = lint("role_bound_association", item)
    assert "lexicon: role 'barber' not in roles_v1.json" in problems
    assert not any("police officer" in p for p in problems)
    b = build_block_v2(item, [item, *load_bank("role_bound_association")], gate.load_lexicon())
    assert b.unlexiconed == ("barber",) and b.n_near == 1


def test_relational_check_blank_requires_full_stop_anchor():
    """plan 0043 C1: freezing an adapted relational bank refuses a tokenizer whose full read
    would not start on the full stop of sentence two (never guesses), as it refuses a blank
    outside the trailing 's."""
    import re

    from wsbench.adapt.run import _check_blank

    def tok(pattern):
        def encode(text, add_special_tokens=False, return_offsets_mapping=True):
            return {"offset_mapping": [m.span() for m in re.finditer(pattern, text)]}

        return encode

    qwen_like = tok(r"'s|\s?\w+|[^\w\s]")  # "." is its own token
    fused = tok(r"'s|\s?\w+\.?|[^\w\s]")  # "Riley." is one token
    items = [
        {
            "id": "rel-x-a",
            "stimulus": "Avery's landlord is Sam. Sam's sibling is Riley. In other words, "
            "Riley is Avery's",
        }
    ]
    assert _check_blank(qwen_like, items) == (items, [])
    with pytest.raises(SystemExit, match="full stop"):
        _check_blank(fused, items)
    with pytest.raises(SystemExit, match="full stop"):
        _check_blank(qwen_like, [{"id": "rel-y", "stimulus": "Avery is Sam's"}])


# ---------------------------------------------------------------- moral re-key (plan 0046 §2.1)


def test_rekey_readrender_teacher_forces_greedy_side():
    from wsbench.adapt import moral

    it = {"id": "x", "stimulus": "S? Answer with true or false only, one word.",
          "answer_format": "true_false"}  # fmt: skip
    v = moral.classify_side("False", ["False"] * 9 + ["True"])
    assert v["klass"] == "committed" and v["side"] == "no" and v["precise"]
    (row,) = moral.reason_requests([it], {"x": v})
    assert row["messages"] == [
        {"role": "user", "content": it["stimulus"]},
        {"role": "assistant", "content": "False"},
        {"role": "user", "content": moral.REKEY_ASK},
    ]
    assert row["enable_thinking"] is False and row["n"] == 10 and row["temperature"] == 1.0
    # the Leg S row is the exact read render (chat, thinking off, [system] + stimulus)
    (s,) = moral.side_requests([{**it, "system": "SYS"}])
    assert s["messages"] == [{"role": "system", "content": "SYS"},
                             {"role": "user", "content": it["stimulus"]}]  # fmt: skip
    assert s["greedy"] and s["n"] == 10 and s["max_tokens"] == 8 and not s["enable_thinking"]
    # a deliberative candidate is forced to each side, in the greedy's casing
    d = moral.classify_side("Yes", ["Yes"] * 6 + ["No"] * 4)
    rows = moral.reason_requests([{**it, "answer_format": "yes_no"}], {"x": d})
    assert [r["messages"][1]["content"] for r in rows] == ["Yes", "No"]


def test_rekey_drops_unstable_side():
    from wsbench.adapt import moral

    assert moral.classify_side("Hmm", ["Yes"] * 7 + ["Maybe"] * 3)["klass"] == "drop"
    assert moral.classify_side("Hmm", ["Yes"] * 7 + ["No"] * 3)["klass"] == "drop"  # greedy other
    assert moral.classify_side("Yes", ["Yes"] * 2 + ["No"] * 8)["klass"] == "drop"  # <= 2/10
    assert moral.classify_side("Yes", ["Yes"] * 7 + ["No"] * 2 + ["x"])["klass"] == "drop"
    assert moral.classify_side("Yes", ["Yes"] * 8 + ["No"] * 2)["klass"] == "committed"
    assert moral.classify_side("No", ["Yes"] * 3 + ["No"] * 7)["klass"] == "deliberative"
    assert moral.reason_requests([{"id": "x", "stimulus": "s"}], {"x": {"klass": "drop"}}) == []


def test_rekey_item_gate():
    from wsbench.adapt import moral

    v = moral.classify_side("False", ["False"] * 10)
    good = {"reasons": [{"text": "r_no", "supports": "no", "frequency": 9}],
            "yes_count": 0, "no_count": 10}  # fmt: skip
    out = moral.rekey_item({"answer_format": "true_false"}, v, good, {"r_no": True})
    assert out["gate_pass"] and out["look_for_reasons"] == ["r_no"]
    assert out["commit_answer"] == "False" and out["commit_direction"] == "no"
    assert out["answer_split"] == {"yes": 0, "no": 10, "other": 0}
    # the Opus side check must confirm: a veto, an undecided (None) or a missing check drops it
    assert not moral.rekey_item({}, v, good, {"r_no": False})["gate_pass"]
    assert not moral.rekey_item({}, v, good, {"r_no": None})["gate_pass"]
    assert not moral.rekey_item({}, v, good, {})["gate_pass"]
    # a deliberative candidate the distiller cannot split into both sides is dropped
    d = moral.classify_side("No", ["Yes"] * 4 + ["No"] * 6)
    one_sided = moral.rekey_item({}, d, good, {})
    assert not one_sided["gate_pass"] and not one_sided["gate_checks"]["class_kept"]

"""Plan 0022: the digest's rare tier, the five-number digest for chain / arithmetic, and the
user_modeling synonym rule in summary mode."""

import json
from pathlib import Path

import pytest
from conftest import native_args
from summary_fakes import FakeLLM, summary_args

from wsbench import digest, llm, registry
from wsbench.cache import Cache
from wsbench.evals.arithmetic_intermediates import SPEC as ARITH
from wsbench.evals.arithmetic_intermediates import judge as arith_judge
from wsbench.evals.arithmetic_intermediates.prompts import SYSTEM as ARITH_NATIVE
from wsbench.evals.arithmetic_intermediates.prompts import SYSTEM_SUMMARY as ARITH_SUMMARY
from wsbench.evals.chain_intermediates import SPEC as CHAIN
from wsbench.evals.chain_intermediates import judge as chain_judge
from wsbench.evals.chain_intermediates.prompts import PROMPT_VERSION as CHAIN_PV
from wsbench.evals.chain_intermediates.prompts import SYSTEM as CHAIN_NATIVE
from wsbench.evals.chain_intermediates.prompts import SYSTEM_SUMMARY as CHAIN_SUMMARY
from wsbench.evals.user_modeling import prompts as um
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.llm import Spend
from wsbench.readouts import Cell
from wsbench.registry import JudgeArgs


def _args(tmp_path: Path, **extra: str) -> JudgeArgs:
    return native_args(
        readouts=tmp_path / "r.jsonl",
        out=tmp_path / "out",
        judge=resolve(JudgeConfig(prompt_version="t")),
        layers=None,
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        extra={"aggregate": "summary", **extra},
    )


def _entry(evidence: str, key: str = "", statement: str = "s") -> dict:
    return {"statement": statement, "key": key, "where": "", "evidence": evidence}


def _lines(*texts: str) -> list[digest.Line]:
    return [digest.Line(t, None, "[L20 pos 1]") for t in texts]


# ---------------------------------------------------------------- rare tier


def test_ground_two_tiers_shared_keys_and_caps():
    lines = _lines("apple pie", "harmonies once", "violins twice", "drums thrice")
    r = {
        "items": [_entry("apple pie", "apple"), _entry("violins twice", "violins")],
        "rare": [
            _entry("harmonies once", "harmonies"),
            _entry("apple pie", "apple"),  # repeats an item's key: a duplicate, not a drop
            _entry("drums thrice", "drums"),
        ],
    }
    dups = [0]
    kept, dropped = digest.ground(r, lines, 1, dups, max_rare=3)
    assert [(g.key, g.tier) for g in kept] == [
        ("apple", "items"),
        ("harmonies", "rare"),
        ("drums", "rare"),
    ]
    assert dropped == 0 and dups[0] == 1
    kept, _ = digest.ground(r, lines, 2, max_rare=1)  # each tier capped on its own
    assert [g.tier for g in kept] == ["items", "items", "rare"]
    assert digest.ground(r, lines, 2)[0][-1].tier == "items"  # max_rare 0: no rare tier


def test_missing_or_bad_rare_is_an_empty_tier():
    lines = _lines("apple pie")
    for r in ({"items": [_entry("apple pie")]}, {"items": [_entry("apple pie")], "rare": "x"}):
        kept, dropped = digest.ground(r, lines, 5, max_rare=5)
        assert [g.tier for g in kept] == ["items"] and dropped == 0
    assert not digest.has_entries({"items": [], "rare": None})
    assert digest.has_entries({"items": [], "rare": [_entry("x")]})


def test_render_prominent_before_rare():
    lines = _lines("rare line", "prominent line")
    r = {"items": [_entry("prominent line")], "rare": [_entry("rare line")]}
    kept, _ = digest.ground(r, lines, 5, max_rare=5)
    text, _evid = digest.render_summary(kept, "extractive")
    assert text.splitlines() == ["[1 sample] prominent line", "[1 sample] rare line"]


def test_schema_and_prompt():
    assert digest.DIGEST_SCHEMA["schema"]["required"] == ["items", "rare"]
    s = digest.settings(_args(Path("/tmp")), "basic_readout")
    assert (s.max_items, s.max_rare, s.numbers) == (10, digest.DEFAULT_MAX_RARE, 0)
    system = digest.render_system(s, "")
    assert "up to 10 entries" in system and f"up to {digest.DEFAULT_MAX_RARE} entries" in system
    assert "comes last or is left out" not in system
    assert "{max_rare}" not in system and "{max_items}" not in system
    assert "content seen in only one or a few samples" in digest.SUMMARY_NOTE


def test_options_and_family_defaults(tmp_path):
    digest.validate({"aggregate": "summary", "summ_rare": "0", "summ_numbers": "0"})
    for bad in ({"summ_rare": "-1"}, {"summ_rare": "x"}, {"summ_numbers": "-2"}):
        with pytest.raises(SystemExit):
            digest.validate({"aggregate": "summary", **bad})
    a = _args(tmp_path)
    assert digest.settings(a, "agentic_misalignment").max_rare == 25
    for fam in ("chain_intermediates", "arithmetic_intermediates"):
        s = digest.settings(a, fam)
        assert (s.numbers, s.max_rare) == (5, 0)
        assert s.to_json()["numbers"] == 5 and s.to_json()["max_rare"] == 0
    assert digest.settings(_args(tmp_path, summ_rare="3"), "x").max_rare == 3


@pytest.fixture
def scripted(monkeypatch):
    seen: list[tuple[str, str]] = []
    replies: dict[str, object] = {}

    def fake_stream_json(prompts, *, on_result, **_kw):
        for i, (system, user) in enumerate(prompts):
            seen.append((system, user))
            key = next((k for k in replies if k in user), None)
            on_result(i, replies.get(key) if key else None)
        return Spend()

    monkeypatch.setattr(digest.llm, "stream_json", fake_stream_json)
    return seen, replies


def _collapse(tmp_path, name, by_item, **extra):
    with Cache(tmp_path / "c.jsonl") as cache:
        return digest.collapse(
            name,
            by_item,
            args=_args(tmp_path, **extra),
            cache=cache,
            spend=Spend(),
            preflight=None,
            task_note="",
        )


def _prose(i: str, layer: int, pos: int, *samples: str) -> Cell:
    return Cell(i, layer, pos, tuple(samples), None, None, None)


def test_stride_rare_only_digest_is_summarized(tmp_path, scripted):
    _seen, replies = scripted
    replies["alpha-blip"] = {"items": [], "rare": [_entry("alpha-blip harmonies", "harmonies")]}
    col = _collapse(tmp_path, "fam", {"a": [_prose("a", 20, 1, "alpha-blip harmonies")]})
    assert "a" not in col.empty and "a" not in col.unsummarized
    assert col.summaries["a"] == "[1 sample] alpha-blip harmonies"
    assert col.statements["a"][0]["tier"] == "rare"


def test_fingerprint_moves_with_rare_and_numbers(tmp_path, scripted):
    seen, replies = scripted
    replies["alpha"] = {"items": [_entry("alpha 1")], "rare": []}
    by_item = {"a": [_prose("a", 20, 1, "alpha 1")]}
    _collapse(tmp_path, "fam", by_item)
    _collapse(tmp_path, "fam", by_item)
    assert len(seen) == 1  # cached
    _collapse(tmp_path, "fam", by_item, summ_rare="3")
    _collapse(tmp_path, "fam", by_item, summ_numbers="2")
    assert len(seen) == 3


def test_hierarchical_chunk_with_only_rare_contributes(tmp_path, monkeypatch):
    fam = "test_0022_hier"
    monkeypatch.setattr(digest, "COUNT_TOKENS_ABOVE", 0.0)  # pin the real-count path
    monkeypatch.setitem(
        digest.FAMILY_DEFAULTS,
        fam,
        # summ_layers=joint: drives the chunk machinery with a multi-layer bundle (audit F1's
        # per-layer default never chunks these small layers)
        {
            "summ_overflow": "hierarchical",
            "summ_token_cap": "1000",
            "summ_max": "5",
            "summ_layers": "joint",
        },
    )
    users: list[str] = []

    def count_tokens(model, prompts, concurrency=8):
        return [len(u) for _s, u in prompts]

    def stream_json(prompts, *, on_result, **_kw):
        for i, (_s, user) in enumerate(prompts):
            users.append(user)
            lines = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
            if not lines:  # the final digest reads "(support: ...)" lines: keep every sample
                lines = [
                    ln.split(") ", 1)[1] for ln in user.splitlines() if ln.startswith("(support:")
                ]
            on_result(i, {"items": [], "rare": [_entry(ln) for ln in lines[:1]]})
        return Spend()

    monkeypatch.setattr(llm, "count_tokens", count_tokens)
    monkeypatch.setattr(llm, "stream_json", stream_json)
    cells = [
        Cell("a", 20 + 4 * L, p, (f"word a L{L} p{p} " + "x" * 40,), None, None, None)
        for L in range(6)
        for p in range(3)
    ]
    col = _collapse(tmp_path, fam, {"a": cells})
    assert col.chunks.get("a", 0) >= 2 and len(users) == col.chunks["a"] + 1
    assert "a" not in col.empty and col.summaries["a"]
    assert all(st["tier"] == "rare" for st in col.statements["a"])


# ---------------------------------------------------------------- numbers digest


def test_number_key_rule():
    ok = digest._number_key_ok
    assert (
        ok("-51", "we get -51 here")
        and ok("十四", "是十四")
        and ok("\uff11\uff14", "=\uff11\uff14")
    )
    assert not ok("1", "x 14")  # not a whole number in the evidence
    assert not ok("十", "是十四") and not ok("点", "点") and not ok("三四", "三四")
    assert digest.number_value("负五十一") == -51 and digest.number_value("两万零五") == 20005
    assert digest.number_value("1,234") == 1234 and digest.number_value("三点五") == 3.5
    assert not ok("3.5", "3.55") and not ok("51 and 68", "51 and 68") and not ok("abc", "abc")


def test_number_key_rule_number_words():
    """Plan 0033 (arithmetic C7): one number word or numeral of any script is a key that grounds
    to its value (九 / nine / fullwidth 9 -> 9); the existing cases above are unchanged."""
    ok = digest._number_key_ok
    assert ok("九", "是九") and ok("nine", "the answer is nine") and ok("\uff19", "= \uff19")
    assert digest.number_value("九") == digest.number_value("nine") == 9
    assert digest.number_value("\uff19") == 9


def test_numbers_ground_strict_keys_and_numeral_only_failures_are_empty(tmp_path, scripted):
    lines = _lines("alpha -51 then 7", "beta words only")
    r = {
        "items": [
            _entry("alpha -51 then 7", "-51"),
            _entry("alpha -51 then 7", ""),  # no key: never the evidence-as-key fallback
            _entry("beta words only", "words"),
        ],
        "rare": [],
    }
    nds = [0]
    kept, dropped = digest.ground(r, lines, 5, numbers=True, numeral_drops=nds)
    assert [(g.key, g.tier) for g in kept] == [("-51", "numbers")]
    assert dropped == 0 and nds[0] == 2  # numeral drops are not evidence failures
    seen, replies = scripted
    replies["beta words"] = {"items": [_entry("beta words only", "words")], "rare": []}
    col = _collapse(
        tmp_path, "fam", {"b": [_prose("b", 20, 1, "beta words only")]}, summ_numbers="5"
    )
    assert col.empty == {"b"} and not col.unsummarized
    assert digest.DIGEST_SYSTEM_NUMBERS.replace("{max_items}", "5") == seen[0][0]
    assert "Give such restatement at most one item" not in seen[0][0]


def test_chain_summary_verdict_keys_bound_the_pass():
    texts = ["so 2 then 11 and 40 and 41 and 42"]
    gold, near = [11], [8, 9, 10, 12, 13, 14]
    v = chain_judge.summary_verdict(
        {"values": [2, 11], "quote": "", "basis": "arithmetic"}, gold, near, texts, ["2", "11"]
    )
    assert v["hit"] and v["kept"] == [2, 11]
    # 11 is in the evidence but is not one of the digest's number keys: it cannot pass
    v = chain_judge.summary_verdict(
        {"values": [2, 11], "quote": "", "basis": "arithmetic"}, gold, near, texts, ["2", "40"]
    )
    assert not v["hit"] and v["kept"] == [2]
    many = [40, 41, 42, 2, 40, 41, 42, 2, 40, 41, 11]  # gold is the 11th value: ignored
    v = chain_judge.summary_verdict(
        {"values": many, "quote": "", "basis": "numeral_bag"}, gold, near, texts, ["11", "2"]
    )
    assert not v["hit"]
    # CJK key: the top value rests on a quote that contains the key
    v = chain_judge.summary_verdict(
        {"values": [14], "quote": "是十四", "basis": "stated_result"},
        [14],
        [],
        ["答案是十四"],
        ["十四"],
    )
    assert v["hit"]


def test_arith_verdict_keys_and_native_default():
    texts = ["first -51 then -68 then 3"]
    res = {"values": [-68, -51], "quote": "", "basis": "arithmetic"}
    v = arith_judge.verdict(res, -51.0, "exact", [-68.0], texts, max_values=10, keys=["-51"])
    assert v["hit"] and v["kept"] == [-51.0] and v["cross"] == 0.0
    v = arith_judge.verdict(res, -51.0, "exact", [-68.0], texts, max_values=10, keys=["3"])
    assert not v["hit"] and v["kept"] == []
    # native: no keys, the three-value cap
    four = {"values": [3, -68, 7, -51], "quote": "", "basis": "arithmetic"}
    assert not arith_judge.verdict(four, -51.0, "exact", [], texts)["hit"]


def test_summary_prompts_only_change_the_cap():
    from wsbench.evals.arithmetic_intermediates.prompts import CONSENSUS_RULE

    for native, summary in ((CHAIN_NATIVE, CHAIN_SUMMARY), (ARITH_NATIVE, ARITH_SUMMARY)):
        if summary is ARITH_SUMMARY:  # audit F11 (Fable's ruling): plus the consensus-mark rule
            summary = summary.replace("\n" + CONSENSUS_RULE, "", 1)
        assert summary == native.replace("at most three.", "at most ten.") and summary != native


@pytest.fixture
def _registered():
    for spec in (ARITH, CHAIN):
        registry.FAMILIES.setdefault(spec.name, spec)


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    return path


def _keyed_digest(user: str) -> dict:
    """A numbers digest: the first numeral of each of the first five bundle samples."""
    import re

    out = []
    for ln in [x[2:] for x in user.splitlines() if x.startswith("- ")]:
        m = re.search(r"-?\d+", ln)
        if m and len(out) < 5:
            out.append(_entry(ln, m.group(0)))
    return {"items": out, "rare": []}


def test_chain_end_to_end_numbers_digest(tmp_path, monkeypatch, _registered):
    ids = ["c-000"]
    rows = [
        {"id": "c-000", "layer": 20, "pos": 70, "samples": ["the value 11 shows"]},
        {"id": "c-000", "layer": 24, "pos": 77, "samples": ["final 999 then 11"]},
    ]
    path = _write(tmp_path / "c.jsonl", rows)
    bank = {
        it["id"]: it
        for it in chain_judge.load_bank(chain_judge.bank_path("chain_intermediates"))[1]
    }
    if "c-000" not in bank:
        ids = [next(iter(bank))]
        for r in rows:
            r["id"] = ids[0]
        _write(path, rows)
    gold = bank[ids[0]]

    def judge(system, user, schema):
        assert system == CHAIN_SUMMARY and schema["name"] == "chain_free"
        return {"states_value": True, "values": [11, 999], "basis": "stated_result", "quote": ""}

    FakeLLM.install(monkeypatch, judge, digest=_keyed_digest)
    # plan 0038: the free-recall summary judge (the MC judge is the default)
    r = CHAIN.run(summary_args(path, tmp_path / "o", CHAIN_PV, items=ids, extra={"judge": "free"}))
    row = r.rows[0]
    assert row["digest_numbers"] == ["11", "999"]
    assert r.config["summarizer"]["numbers"] == 5 and r.config["summarizer"]["max_rare"] == 0
    assert row["kept"] == [11, 999]
    assert row["pass"] is (11 in gold["intermediates"])


def test_um_summary_credits_synonyms_native_unchanged():
    # plan 0056 (um-v3): native and summary share ONE echo standard, the plan-0022 summary one
    for s in (um.UM_ATTRIBUTE_USER_SUMMARY, um.UM_ATTRIBUTE_USER):
        assert um.SUMMARY_ECHO in s and um.SUMMARY_BASIS in s
        assert '"Danish" where the prompt says Denmark' in s and "a form of that word" in s
        assert "and so does a synonym or close paraphrase" not in s
        assert "closely paraphrasing" not in s


def test_hierarchical_fingerprint_moves_with_rare_and_numbers(tmp_path, monkeypatch):
    fam = "test_0022_hier_fp"
    monkeypatch.setitem(
        digest.FAMILY_DEFAULTS, fam, {"summ_overflow": "hierarchical", "summ_max": "5"}
    )
    calls: list[str] = []

    def stream_json(prompts, *, on_result, **_kw):
        for i, (_s, user) in enumerate(prompts):
            calls.append(user)
            on_result(i, {"items": [_entry("alpha 7", "7")], "rare": []})
        return Spend()

    monkeypatch.setattr(llm, "count_tokens", lambda m, p, concurrency=8: [10 for _ in p])
    monkeypatch.setattr(llm, "stream_json", stream_json)
    by_item = {"a": [_prose("a", 20, 1, "alpha 7")]}
    _collapse(tmp_path, fam, by_item)
    _collapse(tmp_path, fam, by_item)
    assert len(calls) == 1  # cached
    _collapse(tmp_path, fam, by_item, summ_rare="2")
    _collapse(tmp_path, fam, by_item, summ_numbers="3")
    assert len(calls) == 3


def test_review_round1_edge_cases(tmp_path, monkeypatch, scripted):
    # rare-only reply with the rare tier off is an empty digest, not an instrument failure
    _seen, replies = scripted
    replies["only rare"] = {"items": [], "rare": [_entry("only rare 7", "7")]}
    col = _collapse(tmp_path, "fam", {"a": [_prose("a", 20, 1, "only rare 7")]}, summ_rare="0")
    assert col.empty == {"a"} and not col.unsummarized
    assert not digest.has_entries({"items": [], "rare": [_entry("x")]}, 0)
    # number keys: a comma is a digit boundary; malformed numerals have no value
    assert not digest._number_key_ok("1", "total 1,234 here")
    assert digest._number_key_ok("1,234", "total 1,234 here")
    for bad in ("1,2,3", "一十一十", "百百"):
        assert digest.number_value(bad) is None, bad
    assert digest.number_value("一百二十三") == 123


def test_hierarchical_numeral_only_chunks_are_empty_without_a_final_call(tmp_path, monkeypatch):
    fam = "test_0022_hier_num"
    monkeypatch.setitem(
        digest.FAMILY_DEFAULTS,
        fam,
        {
            "summ_overflow": "hierarchical",
            "summ_token_cap": "1000",
            "summ_numbers": "5",
            "summ_rare": "0",
        },
    )
    users: list[str] = []

    def stream_json(prompts, *, on_result, **_kw):
        for i, (_s, user) in enumerate(prompts):
            users.append(user)
            lines = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
            on_result(i, {"items": [_entry(ln, "words") for ln in lines[:1]], "rare": []})
        return Spend()

    monkeypatch.setattr(llm, "count_tokens", lambda m, p, concurrency=8: [len(u) for _s, u in p])
    monkeypatch.setattr(llm, "stream_json", stream_json)
    cells = [
        Cell("a", 20 + 4 * L, p, (f"words only L{L} p{p} " + "x" * 40,), None, None, None)
        for L in range(6)
        for p in range(3)
    ]
    col = _collapse(tmp_path, fam, {"a": cells})
    assert col.empty == {"a"} and not col.unsummarized
    assert all(u.strip() != "READOUTS:" for u in users)  # no final call on an empty union


def test_review_round2_edge_cases(tmp_path):
    assert not digest._number_key_ok("5", "x -5") and digest._number_key_ok("-5", "x -5")
    assert digest.number_value("三百五") == 350 and digest.number_value("三点") is None
    lines = _lines("a 5 here", "b 5.0 there")
    r = {"items": [_entry("a 5 here", "5"), _entry("b 5.0 there", "5.0")], "rare": []}
    dups = [0]
    kept, _ = digest.ground(r, lines, 5, dups, numbers=True)
    assert [g.key for g in kept] == ["5"] and dups[0] == 1  # one number, one slot
    a = _args(tmp_path)
    assert digest.summary_note(a, None, "chain_intermediates") == digest.SUMMARY_NOTE_NO_RARE
    assert digest.summary_note(a, None, "basic_readout") == digest.SUMMARY_NOTE
    assert "only one or a few samples" not in digest.SUMMARY_NOTE_NO_RARE
    basis = um.SUMMARY_BASIS.split("Details about")[0]
    assert "same language (a synonym or demonym)" in basis  # synonyms are in the "only if" list
    assert "translated into another language (for example 猫" in um.SUMMARY_BASIS  # still echo

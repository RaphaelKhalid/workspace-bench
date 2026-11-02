"""digest (summary mode): bundle, cap, decoder, evidence gate, renders, item states, cache."""

import json
from pathlib import Path

import pytest
from conftest import native_args

from wsbench import bpe, digest
from wsbench.cache import Cache
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.llm import Spend
from wsbench.readouts import Cell, load_readouts
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


def _prose(i: str, layer: int, pos: int, *samples: str, token: str | None = None) -> Cell:
    return Cell(i, layer, pos, tuple(samples), None, None, token)


def _toks(i: str, layer: int, pos: int, *tokens: str) -> Cell:
    """A token cell as the loader builds it: vocab strings decoded (``wsbench.bpe``)."""
    return Cell(i, layer, pos, None, tuple(bpe.decode_token(t) for t in tokens), None, None)


# ---------------------------------------------------------------- bundle


def test_bundle_order_headers_and_no_token_text():
    cells = [
        _prose("a", 44, 3, "second\nline", token="SECRET"),
        _prose("a", 20, 7, "first"),
        _prose("a", 20, 2, "zeroth", "  "),
    ]
    text, lines, truncated = digest.bundle(cells, 10_000)
    assert text == "[L20 pos 2]\n- zeroth\n[L20 pos 7]\n- first\n[L44 pos 3]\n- second line"
    assert "SECRET" not in text and not truncated
    assert [ln.text for ln in lines] == ["zeroth", "first", "second line"]


MOJIBAKE = "".join(bpe._bytes_to_unicode()[b] for b in "哪一个".encode())


def test_decode_token():
    assert bpe.decode_token(MOJIBAKE) == "哪一个"
    assert bpe.decode_token("Ġathletic") == " athletic"
    assert bpe.decode_token("▁word") == " word"
    assert bpe.decode_token("café") == "café"  # already decoded text is kept


def test_token_line_is_decoded_and_scoreless(tmp_path):
    # vocab strings in the file; the loader decodes them, the bundle does not decode again
    row = {"id": "a", "layer": 20, "pos": 1, "tokens": ["Ġfence", "Ġpost", MOJIBAKE]}
    (tmp_path / "t.jsonl").write_text(json.dumps(row) + "\n")
    (cell,), _ = load_readouts(tmp_path / "t.jsonl")
    text, lines, _ = digest.bundle([cell], 10_000)
    assert text == "[L20 pos 1]\n- fence | post | 哪一个"
    assert lines[0].pieces == ("fence", "post", "哪一个")


def test_summ_decode_false_is_retired(tmp_path, capsys):
    assert digest.settings(_args(tmp_path, summ_decode="true")).decode is True
    with pytest.raises(SystemExit):
        digest.settings(_args(tmp_path, summ_decode="false"))
    assert "retired" in capsys.readouterr().err


def test_est_tokens_is_script_aware():
    assert digest.est_tokens("abcd" * 10) == 10
    assert digest.est_tokens("哪一个") == 3


def test_cap_round_robin_then_stride_keeps_every_layer():
    cells = [_prose("a", L, p, "x" * 40, "y" * 40) for L in (20, 24) for p in range(4)]
    _text, lines, truncated = digest.bundle(cells, 130)
    assert truncated
    assert sum(ln.text.startswith("x") for ln in lines) == 8  # every cell keeps sample 1
    assert any(ln.text.startswith("y") for ln in lines)
    _text, lines, truncated = digest.bundle(cells, 40)
    text = _text
    assert truncated and "[L20 pos 0]" in text and "[L24 pos 0]" in text
    assert len(lines) < 8


# ---------------------------------------------------------------- evidence


def _lines(*cells: Cell) -> list[digest.Line]:
    return digest.bundle(list(cells), 10_000)[1]


def test_evidence_verbatim_whitespace_case_and_across_samples():
    lines = _lines(_prose("a", 20, 1, "The Iron Gate opened", "and then it closed"))
    assert digest.evidence_line("iron   gate", lines).text == "The Iron Gate opened"
    assert digest.evidence_line("opened and then", lines) is None
    assert digest.evidence_line("", lines) is None


def test_evidence_token_pieces_never_join():
    lines = _lines(_toks("a", 20, 1, "Ġfence", "Ġpost", "Ġgate"))
    assert digest.evidence_line("fence post", lines) is None
    assert digest.evidence_line("post", lines) is not None
    assert digest.evidence_line("fence | post", lines) is not None
    # plan 0032 §2.7.3: tokens of ONE list may be quoted together in any order
    assert digest.evidence_line("post | fence", lines) is not None


def _result(*items: tuple[str, str, str]) -> dict:
    return {"items": [{"statement": s, "where": w, "evidence": e} for s, w, e in items]}


def test_evidence_resolution_prefers_named_group_and_exact_match():
    lines = _lines(
        _prose("a", 20, 1, "France or Spain, hard to say"),
        _prose("a", 50, 1, "the answer is France"),
        _toks("a", 24, 1, "Ġcatalog", "Ġx"),
        _toks("a", 52, 1, "Ġcat", "Ġy"),
    )
    assert digest.evidence_line("France", lines, "[L50 pos 1]").text == "the answer is France"
    assert digest.evidence_line("France", lines).text.startswith("France or Spain")
    assert digest.evidence_line("cat", lines).text == "cat | y"  # whole token beats catalog
    assert digest.evidence_line("answer is france", lines).text == "the answer is France"


def test_support_is_counted_mechanically():
    cells = [_prose("a", L, 1, "boxing match") for L in (20, 24, 28, 32)] + [
        _prose("a", 36, 1, "chess")
    ]
    lines = _lines(*cells)
    assert digest.support_of("boxing", lines) == "several"
    assert digest.support_of("chess", lines) == "one"
    many = _lines(*[_prose("a", 20, p, "boxing") for p in range(12)])
    assert digest.support_of("boxing", many) == "many"


def test_token_note_only_for_token_sources(tmp_path):
    a = _args(tmp_path)
    assert digest.SUMMARY_NOTE_TOKENS not in digest.summary_note(a, "prose")
    assert digest.summary_note(a, "tokens").endswith(digest.SUMMARY_NOTE_TOKENS)


def test_ground_and_renders():
    lines = _lines(_prose("a", 20, 1, "a large orange cat sat", "a dog barked"))
    kept, dropped = digest.ground(
        _result(
            ("a tiger", "many", "large orange cat"),
            ("a cat", "few", "orange cat"),  # same sample: one extractive line
            ("a wolf", "one", "wolf"),  # not in any sample: dropped
        ),
        lines,
        10,
    )
    assert dropped == 1 and len(kept) == 2
    text, evid = digest.render_summary(kept, "extractive")
    assert text == "[1 sample] a large orange cat sat"  # digest-v5: a per-claim count
    assert "tiger" not in text and [ln.text for ln in evid] == ["a large orange cat sat"]
    text, _ = digest.render_summary(kept, "abstractive")
    assert text.splitlines()[0] == (
        '- a tiger [support: 1 sample] — evidence: "a large orange cat sat"'
    )


# ---------------------------------------------------------------- collapse


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


def test_collapse_item_states(tmp_path, scripted):
    seen, replies = scripted
    replies["alpha-sample"] = _result(("alpha", "", "alpha-sample"))
    replies["beta-sample"] = _result(("made up", "", "not there"))  # every item dropped
    replies["gamma-sample"] = {"items": []}  # zero items: empty
    by_item = {
        "a": [_prose("a", 20, 5, "alpha-sample", token="'s")],
        "b": [_prose("b", 20, 1, "beta-sample")],
        "c": [_prose("c", 20, 1, "gamma-sample")],
        "d": [_prose("d", 20, 1, "delta-sample")],  # failed call
        "e": [_prose("e", 20, 1, "   ")],  # blank: empty, no call
    }
    args = _args(tmp_path)
    with Cache(tmp_path / "c.jsonl") as cache:
        col = digest.collapse(
            "fam", by_item, args=args, cache=cache, spend=Spend(), preflight=None, task_note="t"
        )
    assert len(seen) == 4
    assert col.cells["a"].samples == ("[1 sample] alpha-sample",)
    assert (col.cells["a"].layer, col.cells["a"].pos, col.cells["a"].token) == (-1, 5, "'s")
    assert col.unsummarized == {"b", "d"} and col.empty == {"c", "e"}
    for i in "bcde":
        assert col.cells[i].samples == ("",)
    assert digest.gate_texts(col.cells["a"], col) == ["alpha-sample"]
    assert col.diag["n_items_all_dropped"] == 1 and col.row("b")["summary_state"] == "unsummarized"


def test_collapse_caches_and_fingerprints(tmp_path, scripted):
    seen, replies = scripted
    replies["alpha"] = _result(("alpha", "", "alpha"))
    by_item = {"a": [_prose("a", 20, 1, "alpha")]}
    with Cache(tmp_path / "c.jsonl") as cache:
        # plan 0032 §2.8.2: task is the default variant; blind is the ablation that re-asks
        for extra in ({}, {}, {"summ_render": "abstractive"}, {"summ_variant": "blind"}):
            digest.collapse(
                "fam",
                by_item,
                args=_args(tmp_path, **extra),
                cache=cache,
                spend=Spend(),
                preflight=None,
                task_note="ZEBRA-NOTE",
            )
    assert len(seen) == 2  # cached on repeat and across renders; the variant re-asks
    assert "ZEBRA-NOTE" in seen[0][0] and "ZEBRA-NOTE" not in seen[1][0]
    rows = (tmp_path / "c.jsonl").read_text().splitlines()
    assert all('"digest:a|all"' in r for r in rows)


def test_gate_texts_splits_token_lines(tmp_path, scripted):
    _seen, replies = scripted
    replies["fence"] = _result(("fence", "[L20 pos 1]", "fence"))
    by_item = {"a": [_toks("a", 20, 1, "Ġfence", "Ġpost")]}
    with Cache(tmp_path / "c.jsonl") as cache:
        col = digest.collapse(
            "fam",
            by_item,
            args=_args(tmp_path),
            cache=cache,
            spend=Spend(),
            preflight=None,
            task_note="",
        )
    assert digest.gate_texts(col.cells["a"], col) == ["fence", "post"]
    assert digest.gate_texts(col.cells["a"], col, joined=True) == ["fence", "post", "fence post"]
    assert col.cells["a"].samples == ("[1 sample] fence | post",)


def test_options_validated(tmp_path):
    with pytest.raises(SystemExit) as e:
        digest.summary_mode(_args(tmp_path, aggregate="pooled"))
    assert e.value.code == 2
    for bad in (
        {"summ_variant": "x"},
        {"summ_render": "x"},
        {"summ_effort": "x"},
        {"summ_max": "0"},
    ):
        with pytest.raises(SystemExit):
            digest.validate({"aggregate": "summary", **bad})
    # native: summary option values are not read (plan 0032: summary is the default, so a
    # native probe says so)
    digest.validate({"aggregate": "native", "summ_variant": "x"})
    with pytest.raises(SystemExit):
        digest.validate({"aggregate": "summary", "summ_varient": "task"})  # typo key
    a = _args(tmp_path)
    assert digest.prompt_version("pv", a) == "pv+digest-v5-task-extractive+sj-v10"
    assert digest.pinned(a) and not digest.pinned(_args(tmp_path, summ_effort="low"))


def test_v2_key_support_and_dedupe():
    cells = [_prose("a", L, 1, f"I am thinking of an apple, sample {L}") for L in range(20, 64, 4)]
    cells.append(_prose("a", 64, 1, "aquariums and fish tanks"))
    lines = _lines(*cells)
    res = {
        "items": [
            {"statement": "apple", "key": "apple", "where": "", "evidence": "an apple, sample 20"},
            {
                "statement": "apple again",
                "key": "Apple",
                "where": "",
                "evidence": "apple, sample 24",
            },
            {"statement": "aquariums", "key": "aquariums", "where": "", "evidence": "aquariums"},
            {"statement": "bad key", "key": "zebra", "where": "", "evidence": "fish tanks"},
        ]
    }
    dups = [0]
    kept, dropped = digest.ground(res, lines, 10, dups)
    assert dropped == 0 and dups == [1]  # the second "apple" repeats the first item's content
    assert [(g.key, g.support) for g in kept] == [
        # no "count" given: the per-claim count falls back to its cap, the key-word count
        ("apple", "11 samples"),  # 11 samples contain the word, not the whole clause
        ("aquariums", "1 sample"),
        ("fish tanks", "1 sample"),  # a key not inside the evidence falls back to the evidence
    ]
    assert digest.support_of("app", lines) == "one"  # whole words only


def test_v2_cjk_and_accent_keys_and_duplicate_counter():
    lines = _lines(
        _prose("a", 20, 1, "我住在北京市"),
        _prose("a", 24, 1, "他也去了北京。"),
        _prose("a", 28, 1, "Café de Flore"),
    )
    assert digest.support_of("北京", lines) == "few"  # no word boundaries inside CJK text
    assert digest.support_of("Cafe", lines) == "one"  # accent-folded like the key check
    res = {
        "items": [
            {"statement": "a", "key": "北京", "where": "", "evidence": "我住在北京市"},
            {"statement": "b", "key": "北京", "where": "", "evidence": "他也去了北京"},
        ]
    }
    dups = [0]
    kept, dropped = digest.ground(res, lines, 10, dups)
    assert len(kept) == 1 and dropped == 0 and dups == [1]


# ---------------------------------------------------------------- plan 0032 (digest-v4)


def _pl(text: str, layer: int = 20, pos: int = 1) -> digest.Line:
    return digest.Line(digest.sample_text(text), None, f"[L{layer} pos {pos}]", layer, pos)


def _tl(layer: int, pos: int, *toks: str) -> digest.Line:
    return digest.Line(digest.TOKEN_SEP.join(toks), toks, f"[L{layer} pos {pos}]", layer, pos)


def test_default_overflow_is_hierarchical(tmp_path):
    assert digest.DEFAULT_OVERFLOW == "hierarchical"
    assert digest.settings(_args(tmp_path)).overflow == "hierarchical"


def test_single_global_token_cap(tmp_path, real_families):
    allowed = digest.FAMILY_DEFAULT_KEYS
    assert allowed == {
        "summ_concurrency",
        "summ_timeout",
        "summ_fallback",
        "summ_max",
        "summ_rare",
        "summ_numbers",
        "summ_ties",  # round 4: the chain digest's tie extension (digest.tie_cut)
    }
    for name in real_families:
        assert digest.settings(_args(tmp_path), name).token_cap == digest.DEFAULT_TOKEN_CAP
        assert set(digest.FAMILY_DEFAULTS.get(name, {})) <= allowed, name
    assert digest.DEFAULT_TOKEN_CAP == 920_000


def test_every_loaded_line_is_bundled(tmp_path, monkeypatch):
    cells = [
        Cell("a", L, p, tuple(f"s{L}-{p}-{k}" for k in range(4)), None, None)
        for L in (20, 24, 28)
        for p in range(30)
    ]
    seen: list[str] = []

    def stream_json(prompts, *, on_result, **kw):
        for i, (_s, user) in enumerate(prompts):
            seen.append(user)
            line = next(ln[2:] for ln in user.splitlines() if ln.startswith("- "))
            on_result(i, {"items": [{"statement": "s", "key": "", "where": "", "evidence": line}]})

    monkeypatch.setattr("wsbench.llm.stream_json", stream_json)
    monkeypatch.setattr("wsbench.llm.count_tokens", lambda m, ps, concurrency=8: [10**6] * len(ps))
    monkeypatch.setattr(digest, "COUNT_TOKENS_ABOVE", 0.0)
    with Cache(tmp_path / "c.jsonl") as cache:
        col = digest.collapse(
            "fam",
            {"a": cells},
            args=_args(tmp_path, summ_token_cap="20000"),
            cache=cache,
            spend=Spend(),
            preflight=None,
            task_note="",
            expect_all=cells,
        )
    assert col.diag["n_readouts_in"] == col.diag["n_readouts_bundled"] == 3 * 30 * 4
    chunks = [u for u in seen if "(support:" not in u]  # the final call reads the union
    bundled = {ln[2:] for u in chunks for ln in u.splitlines() if ln.startswith("- ")}
    assert bundled == {s for c in cells for s in c.samples}  # the union of chunks = the input


def test_served_by_in_extras(tmp_path, scripted):
    _seen, replies = scripted
    replies["alpha"] = _result(("alpha", "", "alpha"))
    with Cache(tmp_path / "c.jsonl") as cache:
        col = digest.collapse(
            "fam",
            {"a": [_prose("a", 20, 1, "alpha")]},
            args=_args(tmp_path),
            cache=cache,
            spend=Spend(),
            preflight=None,
            task_note="",
        )
    assert col.extras()["digest_served_by"] == {"claude-opus-5-5": 1}


def test_summ_lang_removed_no_language_label(tmp_path):
    """Camila 2026-11-01: the summarizer language tag is gone. A Grounded's (inert) language
    field is never rendered, and the option is no longer a known key."""
    ln = _pl("The answer is the hourglass")
    g = digest.Grounded("s", "one", ln.text, ln, "hourglass", "items", "Russian")
    text, evid = digest.render_summary([g], "extractive")
    assert text == "[one] The answer is the hourglass"
    assert evid[0].text == ln.text
    assert "summ_lang" not in digest.KNOWN_KEYS and "summ_lang" not in digest.FAMILY_DEFAULT_KEYS
    assert "DIGEST_LANG_LINE" not in digest.PROMPTS


def test_summ_lang_stamp_dropped(tmp_path):
    for fam in ("multilingual", "multilingual_mt", "multilingual_multihop", "multilingual_typo"):
        assert digest.prompt_version("pv", _args(tmp_path), fam) == (
            "pv+digest-v5-task-extractive+sj-v10"
        )
        system = digest.render_system(digest.settings(_args(tmp_path), fam), "")
        assert '"language"' not in system


def test_token_evidence_noncontiguous_same_line_verifies():
    line = _tl(52, 42, "lion", "x", "bow", "tie")
    assert digest.quote_ok("tie | lion", [line]) and digest.evidence_line("bow | tie", [line])


def test_token_evidence_across_lines_rejected():
    lines = [_tl(52, 42, "lion", "x"), _tl(52, 43, "tamer", "y")]
    assert not digest.quote_ok("lion | tamer", lines)


def test_adjacent_positions_spell_one_word_only():
    lines = [_tl(44, 11, " Khach", "x"), _tl(44, 12, "aturian", "y"), _tl(48, 13, "aturian")]
    assert digest.quote_ok("Khachaturian", lines)
    assert not digest.quote_ok("x y", lines)  # two whole words of adjacent positions
    far = [_tl(44, 11, " Khach"), _tl(44, 13, "aturian")]
    assert not digest.quote_ok("Khachaturian", far)  # not adjacent
    other = [_tl(44, 11, " Khach"), _tl(48, 12, "aturian")]
    assert not digest.quote_ok("Khachaturian", other)  # different layers


def test_quote_ok_strips_scores_and_markdown():
    scored = digest.native_lines(
        [Cell("q", 20, 1, None, ("九", "nine", "x"), (15.19, 14.1, 3.0), None)]
    )
    assert digest.quote_ok("九 (15.19) | nine (14.10)", scored)
    assert digest.quote_ok("九 | nine", scored)
    assert digest.quote_ok("**Khachaturian**", [_pl("composer Khachaturian wrote it")])
    assert not digest.quote_ok("  **  ", [_pl("anything")])


def test_number_flood():
    assert digest.number_flood(_tl(20, 1, "equal", "twelve", "six", "eight", "seven", "eleven"))
    assert not digest.number_flood(_tl(20, 1, "12", "the", "dog", "5"))


def test_worked_chain_prose_is_not_flood():
    assert not digest.number_flood(_pl("87 \u2212 12 = 75, then 75 / 3 = 25, plus 4 gives 29"))


def test_comma_number_list_is_flood():
    assert digest.number_flood(_pl("12, 6, 8, 7, 11"))
    assert digest.number_flood(_pl("twelve six eight seven eleven"))


def test_pronoun_one_not_counted():
    assert not digest.number_flood(_pl("the one who came, the one who left, two more, 5 and 6"))


def test_bulleted_number_list_is_flood():
    assert digest.number_flood(_pl("- 12\n- 15\n- 17\n- 19\n- 23"))


def test_bulleted_worked_chain_is_not_flood():
    text = "- Halving 30 gives 15\n- 15 times 3 is 45\n- 45 minus 4 equals 41"
    assert not digest.number_flood(_pl(text))


def test_number_flood_rejects_statement_line():
    cells = [Cell("a", 20, 1, ("- 12\n- 15",), None, None)]
    (b0, _b1) = digest.statement_lines([_pl("- 12\n- 15")], cells)
    with pytest.raises(ValueError):
        digest.number_flood(b0)


def test_digest_system_records_flat_lists():
    assert "record it as a list" in digest.DIGEST_SYSTEM
    assert "singles out none" not in digest.DIGEST_SYSTEM


def test_no_rank1_exception_text(real_families):
    import importlib

    from wsbench.basic import prompts as bp

    bad = "ranked first among the candidates of its type"
    texts = [*digest.PROMPTS.values(), *bp.PROMPTS.values()]
    for name in real_families:
        texts += list(importlib.import_module(f"wsbench.evals.{name}.prompts").PROMPTS.values())
    assert not any(bad in str(t) for t in texts)


def test_statement_lines_splits_bullets():
    cells = [Cell("a", 20, 1, ("x",), None, None)]
    lines = digest.statement_lines([_pl("- Ann hits Bob\n- Bob cries")], cells)
    assert [(ln.text, ln.bullet) for ln in lines] == [("Ann hits Bob", 0), ("Bob cries", 1)]
    with pytest.raises(ValueError):
        digest.statement_lines([_pl("- a\n- b", layer=99)], cells)


def test_relation_across_two_bullets_fails():
    cells = [Cell("a", 20, 1, ("x",), None, None)]
    lines = [_pl("- the landlord\n- has a sibling")]
    q = "the landlord has a sibling"
    assert digest.quote_ok(q, lines) and not digest.quote_ok(
        q, digest.statement_lines(lines, cells)
    )


def test_relation_in_one_bullet_passes():
    cells = [Cell("a", 20, 1, ("x",), None, None)]
    lines = [_pl("- the landlord's sibling\n- a tenant")]
    assert digest.quote_ok("the landlord's sibling", digest.statement_lines(lines, cells))


def test_unbulleted_sample_is_one_statement():
    cells = [Cell("a", 20, 1, ("x",), None, None)]
    (ln,) = digest.statement_lines([_pl("Ann thinks Bob - the tall one - left.")], cells)
    assert ln.bullet == 0 and "Bob - the tall one - left" in ln.text


def test_token_lines_pass_through():
    cells = [Cell("a", 20, 1, None, ("x",), None)]
    t = _tl(20, 1, "a", "b")
    assert digest.statement_lines([t], cells) == [t]


def test_digest_line_shows_bullet_boundaries(tmp_path, scripted):
    seen, replies = scripted
    sample = "- apples\n- bananas\n- cherries"
    replies["apples"] = _result(("fruit", "", "apples ⁞ bananas ⁞ cherries"))
    with Cache(tmp_path / "c.jsonl") as cache:
        col = digest.collapse(
            "fam",
            {"a": [_prose("a", 20, 1, sample)]},
            args=_args(tmp_path),
            cache=cache,
            spend=Spend(),
            preflight=None,
            task_note="",
        )
    assert "- apples ⁞ bananas ⁞ cherries" in seen[0][1]
    (ev,) = col.evidence["a"]
    assert ev.text == "apples ⁞ bananas ⁞ cherries"
    cells = [_prose("a", 20, 1, sample)]
    assert digest.quote_ok("apples bananas", [ev])
    assert not digest.quote_ok("apples bananas", digest.statement_lines([ev], cells))
    assert digest.quote_ok("apples", digest.statement_lines([ev], cells))


def test_digest_keeps_named_restatement(tmp_path, scripted):
    assert "names a specific object, person, place, name or term is recorded" in (
        digest.DIGEST_SYSTEM
    )
    _seen, replies = scripted
    replies["giraffe"] = {
        "items": [{"statement": "restates", "key": "giraffe", "where": "", "evidence": "giraffe"}]
    }
    with Cache(tmp_path / "c.jsonl") as cache:
        col = digest.collapse(
            "fam",
            {"a": [_prose("a", 20, 1, "think about the giraffe")]},
            args=_args(tmp_path),
            cache=cache,
            spend=Spend(),
            preflight=None,
            task_note="",
        )
    assert col.statements["a"][0]["key"] == "giraffe"


def test_per_item_task_note_fingerprints_per_item(tmp_path, scripted):
    seen, replies = scripted
    replies["alpha"] = _result(("alpha", "", "alpha"))
    replies["beta"] = _result(("beta", "", "beta"))
    by_item = {"a": [_prose("a", 20, 1, "alpha")], "b": [_prose("b", 20, 1, "beta")]}
    notes = {"a": "NOTE-A", "b": "NOTE-B"}
    with Cache(tmp_path / "c.jsonl") as cache:
        digest.collapse(
            "fam", by_item, args=_args(tmp_path), cache=cache, spend=Spend(),
            preflight=None, task_note=notes,
        )  # fmt: skip
        with pytest.raises(ValueError):
            digest.collapse(
                "fam", by_item, args=_args(tmp_path), cache=cache, spend=Spend(),
                preflight=None, task_note={"a": "x"},
            )  # fmt: skip
        digest.collapse(
            "fam", by_item, args=_args(tmp_path), cache=cache, spend=Spend(),
            preflight=None, task_note={**notes, "b": "NOTE-B2"},
        )  # fmt: skip
    systems = {s.split("TASK CONTEXT")[-1] for s, _u in seen}
    assert any("NOTE-A" in x for x in systems) and any("NOTE-B2" in x for x in systems)
    assert len(seen) == 3  # a cached; b re-asked under its new note


def test_gate_texts_joined_returns_split_word():
    col = digest.Collapse()
    col.cells["a"] = Cell("a", digest.SUMMARY_LAYER, 1, ("",), None, None)
    col.evidence["a"] = (_tl(44, 11, " Khach", "x"), _tl(44, 12, "aturian", "y"))
    got = digest.gate_texts(col.cells["a"], col, joined=True, forms=["Khachaturian", "Ravel"])
    assert "Khachaturian" in got and "Ravel" not in got


def test_bullet4_renders_four_lines_per_cell():
    from wsbench.readouts import normalize

    (c,), _d = normalize([Cell("a", 20, 1, ("- g1\n- g2\n- g3\n- g4",), None, None)], "bullet4")
    text, lines, _t = digest.bundle([c], digest.DEFAULT_TOKEN_CAP)
    assert len(lines) == 4 and text.count("\n- ") == 4


def test_truncated_item_is_incomplete(tmp_path):
    from wsbench.results import FamilyResult
    from wsbench.runner import finalize_reads

    col = digest.Collapse()
    col.truncated.add("a")
    r = FamilyResult(
        family="f", metric="pass_rate", value=0.5, ci95=None, n_items=1, higher_is_better=True,
        chance=None, chance_label=None, complete=True, pinned_instrument=True, config={},
        counts={}, extras={"summary": col.extras()},
    )  # fmt: skip
    finalize_reads(_args(tmp_path), r)
    assert r.complete is False and col.extras()["summary_complete"] is False


def test_quote_ok_rejects_made_up_parenthesised_numbers():
    """Review of PR #140: a number the readout never contains must not verify by riding in a
    "(n)" annotation, on prose lines or on token lines."""
    assert not digest.quote_ok("final number (6)", [_pl("the final number is unclear")])
    assert not digest.quote_ok("Tambora (1815)", [_pl("Tambora erupted")])
    assert digest.quote_ok("Tambora (1815)", [_pl("Tambora (1815) erupted")])
    assert not digest.quote_ok("nine (7)", [_tl(20, 1, "nine", "eight")])  # no scores on line
    scored = digest.native_lines([Cell("q", 20, 1, None, ("nine", "eight"), (14.1, 9.0), None)])
    assert not digest.quote_ok("nine (7)", scored)  # not nine's score
    assert not digest.quote_ok("nine (9.00)", scored)  # eight's score, not nine's
    assert digest.quote_ok("nine (14.10)", scored) and digest.quote_ok("nine (14.1)", scored)

"""typo_mt (plan 0033): the v2 bank (arith items dropped), the read site (every token of the
misspelled word; lite = its final token), split-word pooling within a layer, the reads guards,
and the option sets of the optional MC judge (``opts=judge=mc``). The regex contract itself is
tested in ``test_mt_regex.py``."""

import hashlib
import json
import re
from pathlib import Path

import pytest
from conftest import native_args, write_jsonl, write_sidecar
from summary_fakes import FakeLLM, summary_args

from wsbench import readplan, reads, registry
from wsbench.banks import load_bank
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.multitoken import family as fam
from wsbench.multitoken.options import judged_roles, option_sets
from wsbench.multitoken.prompts import CANNOT
from wsbench.multitoken.regex import SCORER_VERSION

REPO = Path(__file__).resolve().parents[1]
V1 = REPO / "evals/typo_mt/items.json"
V2 = REPO / "evals/typo_mt/items_v2.json"
V1_SHA = "c02874dfc958d5ce85a5c64a05f7f13630ec7d129bca2a0704e534448fc95507"
HAND = "tyh-novel-interpretability-hand"  # " mechan" "istic" " interpret" "ibility" (Qwen3.6)
ADAPTED_ARITH = {"gemma-4-31b-it": 13, "glm-5.3-flash": 10, "qwen3-8b": 7, "qwen3.5-9b": 1}


def _is_numeric_form(f: str) -> bool:
    return bool(re.fullmatch(r"\s*-?[\d.,]+\s*", f))


def _forms(it: dict) -> list[str]:
    return [f for u in it.get("units") or () for fs in u["forms"].values() for f in fs]


def _check_options(items, golden_path):
    opts = option_sets(items)
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    want = {
        i: {r: (v["options"], v["gold_index"]) for r, v in per.items()}
        for i, per in golden["options"].items()
    }
    assert want == opts
    n_lang = 0
    for it in items:
        roles = judged_roles(it)
        assert set(roles) == set(opts[it["id"]])
        n_lang += "language" in roles
        for role, (o, g) in opts[it["id"]].items():
            assert len(o) == 6 and o[-1] == CANNOT and 0 <= g < 5 and len(set(o)) == 6
            if role != "language" and role in (it.get("mc") or {}):
                assert o[g] == it["mc"][role]["gold"]
    assert n_lang == 0


def test_options_match_the_golden_and_the_bank():
    header, items = load_bank(V2)
    assert header["family"] == "typo-hard" and len(items) == 85
    _check_options(items, REPO / "tests/golden/typo_mt_v2_options.json")


def test_v1_options_still_match_the_v1_golden():
    header, items = load_bank(V1)
    assert header["family"] == "typo-hard" and len(items) == 100
    _check_options(items, REPO / "tests/golden/typo_mt_options.json")


def test_registered():
    from wsbench.evals.typo_mt import SPEC, TYPO_MT_TASK_NOTE

    registry.FAMILIES.setdefault(SPEC.name, SPEC)
    assert SPEC.group == "basic_mt" and SPEC.scorer == "regex"
    # the regex contract is the instrument; the v2 bank adds its tag once (plan 0033 M1)
    assert SPEC.judge.prompt_version == SCORER_VERSION + "+typo-v2"
    assert "0 (regex)" in SPEC.calls_per_arm and "opts=judge=mc" in SPEC.calls_per_arm
    assert SPEC.min_full_positions == 1 and SPEC.full_contiguous
    assert SPEC.task_note == TYPO_MT_TASK_NOTE and "phrase" not in TYPO_MT_TASK_NOTE
    assert "number" not in TYPO_MT_TASK_NOTE


# ---------------------------------------------------------------- M1: drop the arith items


def test_v2_bank_drops_exactly_the_arith_items(real_families):
    _h1, v1 = load_bank(V1)
    h2, v2 = load_bank(V2)
    assert hashlib.sha256(V1.read_bytes()).hexdigest() == V1_SHA  # v1 untouched
    assert len(v1) == 100 and len(v2) == 85
    assert h2["version"] == 2 and h2["dropped"]["n"] == 15 and V1_SHA in h2["derived_from"]
    assert "true result" not in h2["gate"]
    assert all(it.get("subfamily") != "arith" for it in v2)
    assert not any(_is_numeric_form(f) for it in v2 for f in _forms(it))
    assert v2 == [it for it in v1 if it.get("subfamily") != "arith"]  # same items, v1 order
    arith = sorted(it["name"] for it in v1 if it.get("subfamily") == "arith")
    assert sorted(h2["dropped"]["names"]) == arith and len(arith) == 15
    assert registry.bank_path("typo_mt").name == "items_v2.json"


def test_no_reachable_typo_mt_bank_has_arith_items():
    paths = [registry.REPO_ROOT / "evals/typo_mt/items_v2.json"]
    paths += sorted(REPO.glob("adapted/*/typo_mt.json"))
    assert len(paths) == 12
    for p in paths:
        h, items = load_bank(p)
        assert all(it.get("subfamily") != "arith" for it in items), p
        assert not any(_is_numeric_form(f) for it in items for f in _forms(it)), p
        model = p.parent.name
        if model in ADAPTED_ARITH:  # rewritten in place: the old non-arith items, in order
            assert h["version"] == 2 and h["dropped"]["n"] == ADAPTED_ARITH[model], p
            assert len(h["dropped"]["names"]) == ADAPTED_ARITH[model]
            assert re.search(r"sha256 [0-9a-f]{64}", h["derived_from"]), p


def _args(path, out, **kw):
    base = {
        "readouts": path,
        "out": out,
        "judge": resolve(JudgeConfig(prompt_version=SCORER_VERSION)),
        "layers": None,
        "items": None,
        "limit": 0,
        "allow_missing": False,
        "concurrency": 1,
        "rpm": 1.0,
        "dry_run": False,
    }
    base.update(kw)
    return native_args(**base)


def test_v1_readouts_with_arith_rows_judge_85_items(tmp_path, real_families):
    _h, v1 = load_bank(V1)
    rows = [
        {"id": it["id"], "layer": layer, "pos": 30, "samples": [f"it is {it['target']}"]}
        for it in v1
        for layer in readplan.GRID
    ]
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    write_sidecar(path, reads="full", sampling="prose1")
    r = fam.run_regex(_args(path, tmp_path / "out"), name="typo_mt")
    assert r.n_items == 85 and len(r.rows) == 85
    assert not any(row["id"].startswith("tyh-arith") for row in r.rows)
    assert r.value == 1.0 and r.extras["n_split_word_hits"] == 0


# ---------------------------------------------------------------- M3: the read site


def test_typo_mt_full_reads_the_misspelled_word_lite_the_last_token():
    specs = reads.specs("typo_mt")
    assert len(specs) == 85
    hand = specs[HAND]
    assert hand.positions == {"kind": "suffix_text", "text": "interpretibility", "from_char": 9}
    assert hand.lite_positions == {"kind": "final_token"} and hand.lite_layers is None
    assert hand.layers == readplan.GRID and hand.render == "plain"
    toks = ["There", "'s", " a", " really", " cool", " field", " in", " AI", " safety"]
    toks += [" research", " called", " mechan", "istic", " interpret", "ibility"]
    # ' interpret' (13) ends before the misspelled 'i' (char 9): the model has seen only a
    # correct prefix there, so reading it would score prediction, not correction
    full = readplan.resolve(hand.positions, toks)
    assert full == [14]
    assert readplan.lite_select(full, hand.lite_positions) == [14]
    lite_row = next(s for s in readplan.plan("typo_mt", reads="lite") if s.id == HAND)
    assert readplan.resolve(lite_row.positions, toks) == [14]
    one = specs["tyh-real-deference"]  # a one-token misspelling: full == lite
    toks1 = ["I", " defer", " to", " your", " reference"]
    assert one.positions == {"kind": "suffix_text", "text": "reference", "from_char": 0}
    assert readplan.resolve(one.positions, toks1) == [4]
    assert readplan.lite_select([4], one.lite_positions) == [4]


def test_typo_mt_full_span_starts_at_the_first_misspelled_character():
    """Qwen3.6-27B tokenizations (offline) of three v2 items: the span starts at the token that
    holds the first character where ``typo_word`` differs from ``target``, never earlier."""
    specs = reads.specs("typo_mt")
    acc = specs["tyh-novel-acciaccatura-b6"]  # acciacatura vs acciaccatura: differs at char 6
    assert acc.positions["from_char"] == 6
    toks = [" is", " called", " an", " acc", "iac", "atura"]
    assert readplan.resolve(acc.positions, toks) == [5]  # not ' acc' / 'iac'
    ana = specs["tyh-novel-anaphylaxis"]  # anaphlyaxis vs anaphylaxis: differs at char 5
    assert ana.positions["from_char"] == 5
    toks = [" for", " an", "aph", "ly", "axis"]
    assert readplan.resolve(ana.positions, toks) == [3, 4]  # 'aph' ends at char 4
    # a misspelled character in the middle of a token starts the span at that token
    mid = {"kind": "suffix_text", "text": "anaphlyaxis", "from_char": 3}
    assert readplan.resolve(mid, toks) == [2, 3, 4]
    assert readplan.first_diff("Interpretibility", "interpretability") == 9  # case-insensitive
    assert readplan.first_diff("abc", "abcd") == 2  # a prefix of the target: its last char
    for s in specs.values():  # lite (the final token) stays inside every full span
        assert s.positions["from_char"] < len(s.positions["text"])


def _hand_rows(cells):
    return [{"id": HAND, "layer": L, "pos": p, **x} for L, p, x in cells]


def test_run_regex_pools_positions_within_a_layer(tmp_path, real_families):
    def run(cells, name):
        path = write_jsonl(tmp_path / f"{name}.jsonl", _hand_rows(cells))
        return fam.run_regex(_args(path, tmp_path / name, items=[HAND]), name="typo_mt")

    prose = run(
        [(44, 13, {"samples": ["interpretability"]}), (44, 14, {"samples": ["other"]})], "a"
    )
    assert prose.rows[0]["pass"] is True and not prose.rows[0]["split_word_hit"]
    split = run(
        [(44, 13, {"tokens": [" interpret", " cat"]}), (44, 14, {"tokens": ["ability", " x"]})],
        "b",
    )
    assert split.rows[0]["pass"] is True and split.rows[0]["split_word_hit"]
    assert split.extras["n_split_word_hits"] == 1
    gap = run(
        [(44, 12, {"tokens": [" interpret"]}), (44, 14, {"tokens": ["ability"]})], "c"
    )  # not adjacent
    assert gap.rows[0]["pass"] is False and gap.extras["n_split_word_hits"] == 0
    layers = run(
        [
            (40, 13, {"tokens": [" interpret"]}),
            (44, 14, {"tokens": ["ability"]}),
            (40, 14, {"tokens": [" x"]}),
            (44, 13, {"tokens": [" y"]}),
        ],
        "d",
    )  # the two pieces at different layers
    assert layers.rows[0]["pass"] is False
    two_samples = run([(44, 14, {"samples": ["interpret", "ability"]})], "e")
    assert two_samples.rows[0]["pass"] is False  # separate samples never combine


def test_summary_split_word_quote_hits_as_its_plain_word(tmp_path, monkeypatch, real_families):
    from wsbench.evals.typo_mt import SPEC, TYPO_MT_TASK_NOTE

    rows = _hand_rows(
        [(44, 13, {"tokens": [" interpret", " cat"]}), (44, 14, {"tokens": ["ability", " x"]})]
    )
    path = write_jsonl(tmp_path / "r.jsonl", rows)

    def digest(user):
        return {"items": [{"statement": "spells interpretability", "evidence": "interpretability"}]}

    fake = FakeLLM.install(monkeypatch, judge=lambda s, u, sc: None, digest=digest)
    r = fam.run_family(
        summary_args(path, tmp_path / "o", SPEC.judge.prompt_version, items=[HAND]),
        name="typo_mt",
    )
    assert r.rows[0]["pass"] is True and r.rows[0]["split_word_hit"]
    assert r.extras["n_split_word_hits"] == 1
    systems = [s for name, s, _u in fake.calls if name == "digest"]
    assert systems and all(TYPO_MT_TASK_NOTE in s for s in systems)  # the spec's own note
    # a statement the summarizer infers is never evidence for the regex
    fake2 = FakeLLM.install(
        monkeypatch,
        judge=lambda s, u, sc: None,
        digest=lambda u: {"items": [{"statement": "interpretability", "evidence": " cat"}]},
    )
    r2 = fam.run_family(
        summary_args(path, tmp_path / "o2", SPEC.judge.prompt_version, items=[HAND]),
        name="typo_mt",
    )
    assert fake2.n("digest") == 1 and r2.rows[0]["pass"] is False


def test_reads_lite_uses_shared_select(tmp_path, real_families):
    cells = [(44, 13, {"samples": ["interpretability"]}), (44, 14, {"samples": ["nothing"]})]
    path = write_jsonl(tmp_path / "r.jsonl", _hand_rows(cells))
    full = fam.run_regex(_args(path, tmp_path / "f", items=[HAND], layers=[44]), name="typo_mt")
    assert full.rows[0]["pass"] is True
    lite_args = _args(path, tmp_path / "l", items=[HAND], layers=[44], extra={"reads": "lite"})
    lite = fam.run_regex(lite_args, name="typo_mt")
    loaded, _rep = reads.load(
        _args(path, tmp_path / "x", items=[HAND], layers=[44]), "typo_mt", ids=[HAND]
    )
    kept = reads.select(loaded, reads.specs("typo_mt"), "lite")
    assert [(c.layer, c.pos) for c in kept] == [(44, 14)]
    assert lite.rows[0]["pass"] is False  # only the final token is judged
    assert lite.config["prompt_version"].endswith("+reads-lite")
    assert not full.config["prompt_version"].endswith("+reads-lite")


def test_full_partial_span_is_flagged(tmp_path, capsys, real_families):
    """A gap inside a full span (13, 15: position 14 missing) is partial."""
    cells = [(44, 13, {"samples": ["x"]}), (44, 15, {"samples": ["interpretability"]})]
    path = write_jsonl(tmp_path / "r.jsonl", _hand_rows(cells))
    bare = fam.run_regex(_args(path, tmp_path / "b", items=[HAND], layers=[44]), name="typo_mt")
    assert bare.config["reads_checked"] == "no_sidecar"
    assert bare.extras["partial_ids_unenforced"] == [HAND]
    write_sidecar(path, reads="full", sampling="prose1", plan_sha=reads.plan_sha("typo_mt"))
    with pytest.raises(SystemExit):
        fam.run_regex(_args(path, tmp_path / "s", items=[HAND], layers=[44]), name="typo_mt")
    assert "does not hold its full span" in capsys.readouterr().err
    part = fam.run_regex(
        _args(path, tmp_path / "p", items=[HAND], layers=[44], allow_missing=True),
        name="typo_mt",
    )
    assert part.extras["partial_ids"] == [HAND] and part.config["reads_checked"] == "sidecar"


def test_lite_sidecar_file_refused_under_full(tmp_path, capsys, real_families):
    path = write_jsonl(
        tmp_path / "r.jsonl", _hand_rows([(44, 14, {"samples": ["interpretability"]})])
    )
    write_sidecar(path, reads="lite", sampling="prose1")
    with pytest.raises(SystemExit):
        fam.run_regex(_args(path, tmp_path / "f", items=[HAND], layers=[44]), name="typo_mt")
    assert "judge it with reads=lite" in capsys.readouterr().err
    lite = fam.run_regex(
        _args(path, tmp_path / "l", items=[HAND], layers=[44], extra={"reads": "lite"}),
        name="typo_mt",
    )
    assert lite.rows[0]["pass"] is True and lite.config["reads_checked"] == "sidecar"

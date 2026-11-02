"""basic_readout_mt (plan 0051): the v2 question bank, every-position reads, the MC judge of
record with the name gate, the any-language headline and its report columns. The v1 option
golden (``items.json``) stays pinned; the regex contract is ``test_mt_regex.py``'s."""

import hashlib
import json
import re
from pathlib import Path

import pytest
from conftest import native_args, tag_of, write_sidecar
from summary_fakes import FakeLLM

from wsbench import digest, mc, readplan, reads, registry
from wsbench.banks import load_bank, native_langs
from wsbench.cli import main
from wsbench.judge_config import resolve
from wsbench.multitoken import family as fam
from wsbench.multitoken import prompts as mp
from wsbench.multitoken.options import judged_roles, option_sets
from wsbench.multitoken.prompts import CANNOT
from wsbench.readouts import Cell
from wsbench.results import read_results

REPO = Path(__file__).resolve().parents[1]
V1 = REPO / "evals/basic_readout_mt/items.json"
V2 = REPO / "evals/basic_readout_mt/items_v2.json"
NAME = "basic_readout_mt"
V1_FILE_SHA = "ad1483912a8a5bfe875b37985f6ccfdf6a97e5b07524c5420933c9a982060dd8"


def _v2():
    return load_bank(V2)


def _item(prefix: str) -> dict:
    _h, items = _v2()
    return next(it for it in items if it["id"].startswith(prefix))


# ---------------------------------------------------------------- v1, frozen


def test_options_match_the_golden_and_the_bank():
    header, items = load_bank(REPO / "evals/basic_readout_mt/items.json")
    assert header["family"] == "basic-readout-hard" and len(items) == 100
    opts = option_sets(items)
    golden = json.loads(
        (REPO / "tests/golden/basic_readout_mt_options.json").read_text(encoding="utf-8")
    )
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
    assert n_lang == 40


def test_v1_bank_untouched():
    assert hashlib.sha256(V1.read_bytes()).hexdigest() == V1_FILE_SHA
    header, _items = _v2()
    assert header["parent"] == {"file": "items.json", "sha256": V1_FILE_SHA}


# ---------------------------------------------------------------- helpers


def _one_bank(monkeypatch, tmp_path, ids) -> None:
    """Point the family at a bank of just ``ids`` (``WSB_BANK_FILE_<F>``), so a run over every
    bank item is not a subset and can be ``complete``."""
    raw = json.loads(V2.read_text(encoding="utf-8"))
    raw["items"] = [it for it in raw["items"] if it["name"] in set(ids)]
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "bank.json"
    path.write_text(json.dumps(raw, ensure_ascii=False))
    monkeypatch.setenv("WSB_BANK_FILE_BASIC_READOUT_MT", str(path))


def _gold(it: dict, role: str = "readout") -> str:
    o, g = option_sets(_v2()[1], cannot=mc.CANNOT)[it["id"]][role]
    return o[g]


def _file(tmp_path, items, text_of, layers=(44,), positions=range(-30, 0), sidecar=True, **meta):
    rows = [
        {"id": it["id"], "layer": layer, "pos": p, "samples": text_of(it, layer, p)}
        for it in items
        for layer in layers
        for p in positions
    ]
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    if sidecar:
        write_sidecar(path, plan_sha=reads.plan_sha(NAME), **meta)
    return path


def _args(path, out, *, extra=None, layers=(44,), allow_missing=False, items=None):
    return native_args(
        readouts=path,
        out=out,
        judge=resolve(registry.FAMILIES[NAME].judge),
        layers=None if layers is None else list(layers),
        items=items,
        limit=0,
        allow_missing=allow_missing,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
        extra=extra or {},
    )


def _cannot(system, user, schema):
    return {"choice": re.findall(r"^([A-F])\. ", user, flags=re.M)[-1], "quote": ""}


def _responder(script: dict[str, dict[str, str]], quotes: dict[str, str] | None = None):
    """Judge stand-in: per readout tag (``R:<tag>``) and unit (readout / language), pick the
    gold option or cannot tell; the quote is ``quotes["<tag>|<role>"]`` (default: the gold
    option text)."""
    quotes = quotes or {}

    def judge(system, user, schema):
        tag = tag_of(user)
        role = "language" if "LANGUAGE" in user else "readout"
        want = script.get(tag, {}).get(role, "cannot")
        opts = re.findall(r"^([A-F])\. (.*)$", user, flags=re.M)
        if want == "cannot":
            return {"choice": opts[-1][0], "quote": ""}
        gold = script[tag]["gold_" + role]
        letter = next(a for a, t in opts if t == gold)
        return {"choice": letter, "quote": quotes.get(f"{tag}|{role}", gold)}

    return judge


def _run(tmp_path, monkeypatch, plan, *, items, text_of=None, quotes=None, **kw):
    """A native run of ``items`` (30 positions, L44) with a scripted judge; ``plan``: id ->
    {role: gold | cannot}."""
    _h, bank = _v2()
    by_id = {it["id"]: it for it in bank}
    its = [by_id[i] for i in items]
    script = {}
    for i, roles in plan.items():
        it = by_id[i]
        script[i] = {
            **roles,
            "gold_readout": _gold(it),
            **({"gold_language": _gold(it, "language")} if it.get("lang") else {}),
        }
    text_of = text_of or (lambda it, layer, pos: [f"R:{it['id']} it is {_gold(it)}"])
    _one_bank(monkeypatch, tmp_path, items)
    path = _file(tmp_path, its, text_of)
    fake = FakeLLM.install(monkeypatch, judge=_responder(script, quotes))
    r = registry.FAMILIES[NAME].run(_args(path, tmp_path / "out", **kw))
    return r, fake


# ---------------------------------------------------------------- item 1: the judge of record


def test_spec_judge_is_mc_pinned(real_families, tmp_path, monkeypatch):
    spec = real_families[NAME]
    assert spec.scorer == ""
    assert spec.judge.prompt_version == "mc-brmt-2026-10-31r+rv-2026-11-01h+optrv-v4+bank-v4"
    assert spec.bank == Path("evals/basic_readout_mt/items_v4.json")
    assert spec.not_in_macro == "" and spec.metric == "pass_rate" and not spec.multi_select
    assert spec.min_full_positions == 8 and spec.full_contiguous
    it = _item("brh-ent-")
    r, _f = _run(tmp_path, monkeypatch, {it["id"]: {"readout": "gold"}}, items=[it["id"]])
    assert r.pinned_instrument is True and r.complete
    assert r.config["prompt_version"] == "mc-brmt-2026-10-31r+rv-2026-11-01h+optrv-v4+bank-v4"


def test_regex_diagnostic_is_unpinned(real_families, tmp_path):
    assert fam.BRMT_HEADLINE_UNITS == ("readout",)
    it = _item("brh-ent-")
    path = _file(tmp_path, [it], lambda i, layer, pos: [f"it is {_gold(i)}"])
    args = _args(path, tmp_path / "rx", extra={"judge": "regex"}, items=[it["id"]])
    r = fam.run_family(args, name=NAME, scorer="mc")
    assert not r.pinned_instrument and r.config["prompt_version"].startswith("mt-regex-")
    with pytest.raises(SystemExit):
        fam.run_family(_args(path, tmp_path / "x", extra={"judge": "j"}), name=NAME, scorer="mc")


def test_l2_item_passes_on_english_answer_alone(tmp_path, monkeypatch, real_families):
    it = _item("brh-fi-ahvenanmaa")
    en = "Åland Islands"
    assert en in it["name_forms"]["readout"]["en"]
    r, _f = _run(
        tmp_path,
        monkeypatch,
        {it["id"]: {"readout": "gold", "language": "cannot"}},
        items=[it["id"]],
        text_of=lambda i, layer, pos: [f"R:{i['id']} it is {en}"],
        quotes={f"{it['id']}|readout": en},
    )
    (row,) = r.rows
    assert row["pass"] is True and row["any_hit"] is True and row["translated_pass"] is True
    assert row["conjunctive_pass"] is False
    assert r.extras["language_unit_rate"] == 0.0 and r.extras["conjunctive_pass_rate"] == 0.0
    assert r.extras["n_l2_pass_not_conjunctive"] == 1


@pytest.mark.parametrize(
    "readout,language",
    [("gold", "gold"), ("gold", "cannot"), ("cannot", "gold"), ("cannot", "cannot")],
)
def test_language_unit_never_gates_headline(
    readout, language, tmp_path, monkeypatch, real_families
):
    it = _item("brh-fi-ahvenanmaa")
    plan = {it["id"]: {"readout": readout, "language": language}}
    text = f"R:{it['id']} it is {_gold(it)}, a {_gold(it, 'language')} question"
    r, _f = _run(tmp_path, monkeypatch, plan, items=[it["id"]], text_of=lambda i, la, p: [text])
    (row,) = r.rows
    assert row["pass"] is (readout == "gold")
    assert row["conjunctive_pass"] is (readout == "gold" and language == "gold")
    assert row["unit_correct"]["language"] is (language == "gold")


def test_translated_variant(tmp_path, monkeypatch, real_families):
    it = _item("brh-fi-ahvenanmaa")
    for quote, translated in (("Ahvenanmaa", False), ("Åland Islands", True), ("Åland", True)):
        r, _f = _run(
            tmp_path / f"q{len(quote)}",
            monkeypatch,
            {it["id"]: {"readout": "gold"}},
            items=[it["id"]],
            text_of=lambda i, layer, pos, q=quote: [f"R:{i['id']} the answer is {q}"],
            quotes={f"{it['id']}|readout": quote},
        )
        (row,) = r.rows
        assert row["pass"] is True and row["translated_pass"] is translated, quote
        assert r.extras["translated_pass_rate"] == float(translated)
        assert r.extras["by_subfamily"]["l2_factual"]["pass_rate"] == 1.0


def test_source_language_counts(tmp_path, monkeypatch, real_families):
    it = _item("brh-he-neptune-moon")
    he = "טריטון"
    assert he in it["name_forms"]["readout"]["he"]
    r, _f = _run(
        tmp_path,
        monkeypatch,
        {it["id"]: {"readout": "gold"}},
        items=[it["id"]],
        text_of=lambda i, layer, pos: [f"R:{i['id']} התשובה היא {he}"],
        quotes={f"{it['id']}|readout": he},
    )
    assert r.rows[0]["pass"] is True and r.rows[0]["translated_pass"] is False


def test_readme_headline_names_scored_unit():
    text = (REPO / "evals/basic_readout_mt/README.md").read_text(encoding="utf-8")
    first = text.split("\n\n", 2)[1]
    assert "The headline scores one thing: whether the readouts name the answer." in first
    assert "do not also have to name the question's language" in first
    for col in ("conjunctive_pass_rate", "language_unit_rate", "translated_pass_rate"):
        assert col in first


# ---------------------------------------------------------------- item 2: positions


def test_plan_reads_every_position_final_token_lite():
    rows = readplan.plan(NAME)
    _h, items = _v2()
    assert len(rows) == len(items)
    for s in rows:
        assert s.render == "chat" and s.positions == {"kind": "all_from_end"}
        assert s.lite_positions == {"kind": "final_token"} and s.lite_layers is None
        assert s.layers == list(readplan.GRID) and s.prefill is None
    lite = readplan.plan(NAME, reads="lite")
    assert lite[0].positions["lite"] == {"kind": "final_token"}


def test_multi_position_file_accepted(tmp_path, monkeypatch, real_families):
    it = _item("brh-ent-")
    r, fake = _run(tmp_path, monkeypatch, {it["id"]: {"readout": "gold"}}, items=[it["id"]])
    assert r.rows[0]["pass"] is True
    (user,) = [u for n, _s, u in fake.calls if n == "pick"]
    assert user.count("[pos -") == 30 and "token=" not in user


def test_reads_lite_keeps_last_position(tmp_path, monkeypatch, real_families):
    it = _item("brh-ent-")
    path = _file(tmp_path, [it], lambda i, layer, pos: [f"R:x at {pos}"])
    fake = FakeLLM.install(monkeypatch, judge=_cannot)
    out = tmp_path / "out"
    argv = [f"family={NAME}", f"readouts={path}", f"out={out}", "layers=44", "reads=lite"]
    assert main(["judge", *argv, "opts=aggregate=native", f"items={it['id']}"]) == 0
    (user,) = [u for n, _s, u in fake.calls if n == "pick"]
    assert "at -1" in user and "at -2" not in user
    assert read_results(out).config["prompt_version"].endswith("+reads-lite")


def test_reads_full_gap_is_partial_under_allow_missing(tmp_path, monkeypatch, real_families):
    it = _item("brh-ent-")
    gap = [p for p in range(-30, 0) if p != -2]
    path = _file(tmp_path, [it], lambda i, layer, pos: ["R:x y"], positions=gap)
    FakeLLM.install(monkeypatch, judge=_cannot)
    base = ["judge", f"family={NAME}", "layers=44", "opts=aggregate=native", f"items={it['id']}"]
    with pytest.raises(SystemExit):
        main([*base, f"readouts={path}", f"out={tmp_path / 'a'}"])
    assert main([*base, f"readouts={path}", f"out={tmp_path / 'b'}", "allow_missing=True"]) == 0
    r = read_results(tmp_path / "b")
    assert r.extras["partial_ids"] == [it["id"]] and r.complete is False
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "r.jsonl").write_text(path.read_text())
    assert main([*base, f"readouts={bare / 'r.jsonl'}", f"out={tmp_path / 'c'}"]) == 0
    assert read_results(tmp_path / "c").extras["partial_ids_unenforced"] == [it["id"]]


def test_summary_bundle_has_every_position_and_layer(tmp_path, monkeypatch, real_families):
    it = _item("brh-ent-")
    path = _file(tmp_path, [it], lambda i, layer, pos: [f"s{layer}{pos}"], layers=(40, 44))
    fake = FakeLLM.install(monkeypatch, judge=_cannot)
    args = _args(path, tmp_path / "out", extra={"aggregate": "summary"}, layers=(40, 44))
    registry.FAMILIES[NAME].run(dict_replace(args, items=[it["id"]]))
    # audit F1: one digest per read layer; together they carry every cell
    user = "\n".join(u for n, _s, u in fake.calls if n == "digest")
    for layer in (40, 44):
        for p in range(-30, 0):
            assert f"[L{layer} pos {p}]" in user and f"s{layer}{p}" in user


def dict_replace(args, **kw):
    import dataclasses

    return dataclasses.replace(args, **kw)


# ---------------------------------------------------------------- item 5: sampling


def test_brmt_sampling_follows_sidecar(tmp_path, monkeypatch, real_families):
    """bullet4 (a single-bullet O-lens): a packed x4 cell is 4 separate samples, re-joined as
    bullets for the native judge; prose1 (s3d, NLA): the one multi-bullet generation stays ONE
    sample. ``config.sampling`` follows the sidecar."""
    it = _item("brh-ent-")
    packed = "- R:x alpha one\n- beta two\n- gamma three\n- delta four"
    for sampling, n in (("bullet4", 4), ("prose1", 1)):
        d = tmp_path / sampling
        path = _file(
            d, [it], lambda i, layer, pos: [packed], positions=range(-8, 0), sampling=sampling
        )
        cells, _rep = reads.load(_args(path, d / "o"), NAME, ids=[it["id"]])
        assert {len(c.samples or ()) for c in cells} == {n}, sampling
        fake = FakeLLM.install(monkeypatch, judge=_cannot)
        out = d / "out"
        argv = [f"family={NAME}", f"readouts={path}", f"out={out}", f"items={it['id']}"]
        assert main(["judge", *argv, "layers=44", "opts=aggregate=native"]) == 0
        (user,) = [u for nm, _s, u in fake.calls if nm == "pick"]
        block = user.split("[pos -1] ", 1)[1].split('"""', 1)[0]
        assert block.count("- ") == 4, sampling
        cfg = read_results(out).config
        assert cfg["sampling"] == sampling and cfg["sampling_source"] == "declared"


def test_brmt_tokens_truncated_to_10(tmp_path, monkeypatch, real_families):
    it = _item("brh-ent-")
    rows = [
        {"id": it["id"], "layer": 44, "pos": p, "tokens": [f"t{k}" for k in range(20)],
         "scores": [float(20 - k) for k in range(20)]}
        for p in range(-8, 0)
    ]  # fmt: skip
    path = tmp_path / "t.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    write_sidecar(path, sampling="tokens10", plan_sha=reads.plan_sha(NAME))
    fake = FakeLLM.install(monkeypatch, judge=_cannot)
    registry.FAMILIES[NAME].run(_args(path, tmp_path / "out", items=[it["id"]]))
    system, user = next((s, u) for nm, s, u in fake.calls if nm == "pick")
    line = next(ln for ln in user.splitlines() if ln.startswith("[pos -1]"))
    assert line == "[pos -1] " + " | ".join(f"t{k}" for k in range(10))
    assert system.endswith(digest.token_note_of(NAME)) and "(" not in line


# ---------------------------------------------------------------- item 6: question form


def test_bank_v2_is_question_form():
    header, items = _v2()
    assert header["version"] == 2 and header["contract"]["native_langs"] == ["en", "zh"]
    assert native_langs(header) == ("en", "zh")
    scripts = {"ko": "[가-힯]", "he": "[֐-׿]", "ar": "[؀-ۿ]",
               "ru": "[Ѐ-ӿ]"}  # fmt: skip
    for it in items:
        q = it["prompt"]
        assert q.rstrip().endswith(("?", chr(0x061F), chr(0xFF1F))), it["id"]
        forms = [f for fs in it["name_forms"]["readout"].values() for f in fs]
        assert not mc.form_in(q, forms), it["id"]
        assert it["eval_render"] == "chat" and it["prompt_v1"] and it["prompt_v1"] != q
        assert it["readout"] == {"kind": "all_from_end", "lite": "final_token"}
        if it.get("lang") in scripts:
            assert re.search(scripts[it["lang"]], q), it["id"]
        if it.get("lang"):  # the source-language answer counts (Camila: "in the source
            src = [it["target"], *it.get("target_alts", [])]  # language too")
            assert set(src) <= set(it["name_forms"]["readout"][it["lang"]]), it["id"]


# ---------------------------------------------------------------- item 7: options


def test_options_v2_match_golden():
    _h, items = _v2()
    opts = option_sets(items, cannot=mc.CANNOT)
    golden = json.loads(
        (REPO / "tests/golden/basic_readout_mt_options_v2.json").read_text(encoding="utf-8")
    )
    got = {i: {r: {"options": o, "gold_index": g} for r, (o, g) in per.items()}
           for i, per in opts.items()}  # fmt: skip
    assert got == golden["options"]
    for per in opts.values():  # test_cannot_is_last
        for o, g in per.values():
            assert o[-1] == mc.CANNOT and len(o) == 6 and 0 <= g < 5


def test_distractors_disjoint_from_gold_forms():
    _h, items = _v2()
    for it in items:
        forms = [f for fs in it["name_forms"]["readout"].values() for f in fs]
        block = it["mc"]["readout"]
        assert mc.form_in(block["gold"], forms), it["id"]
        assert len({mc.fold(d) for d in block["distractors"]}) == 4, it["id"]
        for d in block["distractors"]:
            assert not mc.form_in(d, forms), (it["id"], d)
            assert not any(mc.form_in(f, [d]) for f in forms), (it["id"], d)


def test_brmt_system_uses_shared_list_rule():
    s = mp.BRMT_SYSTEM
    assert "two or more of the options, which singles out none of those options" in s
    assert "only option on its line is singled out" in s
    assert "mostly" not in s and "ranked first" not in s
    assert s.startswith(f"You judge {mc.READOUT_PHRASE}") and mp.BRMT_TASK in s


def test_digest_gets_task_note_by_default(tmp_path, monkeypatch, real_families):
    it = _item("brh-ent-")
    path = _file(tmp_path, [it], lambda i, layer, pos: ["s"], positions=range(-8, 0))
    fake = FakeLLM.install(monkeypatch, judge=_cannot)
    registry.FAMILIES[NAME].run(
        _args(path, tmp_path / "o", items=[it["id"]], extra={"aggregate": "summary"})
    )
    (system,) = [s for n, s, _u in fake.calls if n == "digest"]
    assert mp.BRMT_TASK_NOTE in system
    assert registry.FAMILIES[NAME].task_note == mp.BRMT_TASK_NOTE


# ---------------------------------------------------------------- item 8: the name gate


def _lines(*texts):
    return [digest.Line(t, None, "[L44 pos -1]", 44, -1) for t in texts]


def _toks(layer, pos, *toks):
    return digest.Line(" | ".join(toks), tuple(toks), f"[L{layer} pos {pos}]", layer, pos)


def test_name_gate_short_form_passes():
    assert fam.name_gate("correct", "Triton", ["Triton"], _lines("it is Triton")) == "correct"
    assert fam.name_gate("distractor", "Titan", ["Triton"], _lines("Titan")) == "distractor"


def test_name_gate_other_alphabet_passes():
    """E1 (brh-he-neptune-moon, rl-onchat-x4 L32): a readout writing the answer's own name in
    Cyrillic is the name, not a description; the fixed romanization table reaches "Triton"."""
    lines = _lines("безусловно, **Тритон**")
    assert fam.romanized("Тритон") == "triton" and fam.romanized("Τρίτων") == "triton"
    assert fam.name_gate("correct", "безусловно, **Тритон**", ["Triton"], lines) == "correct"
    assert fam.name_gate("correct", "Титан", ["Triton"], _lines("Титан")) == "name_miss"


def test_name_gate_surname_unique_passes():
    forms = ["Aram Khachaturian", "Khachaturian"]
    lines = _lines("the composer is Khachaturian")
    assert fam.name_gate("correct", "Khachaturian", forms, lines) == "correct"


def test_name_gate_shared_partial_fails():
    forms = ["Aram Khachaturian", "Khachaturian"]  # "Aram" alone also fits another Aram
    assert fam.name_gate("correct", "Aram", forms, _lines("it was Aram")) == "name_miss"


def test_name_gate_category_fails():
    forms = ["Mount Tambora", "Tambora", "Gunung Tambora"]
    assert fam.name_gate("correct", "volcano", forms, _lines("a volcano")) == "name_miss"
    assert fam.name_gate("correct", "not there", forms, _lines("a volcano")) == "unverified"


def test_split_name_across_adjacent_positions():
    forms = ["Khachaturian"]
    ok = [_toks(44, -3, " Khach", " x"), _toks(44, -2, "aturian", "y")]
    assert fam.name_gate("correct", "Khachaturian", forms, ok) == "correct"
    two_layers = [_toks(44, -3, " Khach"), _toks(48, -2, "aturian")]
    gapped = [_toks(44, -4, " Khach"), _toks(44, -2, "aturian")]
    assert not digest.quote_ok("Khachaturian", two_layers)
    assert not digest.quote_ok("Khachaturian", gapped)
    assert fam.name_gate("correct", "Khachaturian", forms, gapped) == "unverified"


def test_one_list_parts_join_to_name():
    one = [_toks(44, -1, " Khach", "aturian", " Henry", " James", " Tunis", " dynasty")]
    assert fam.name_gate("correct", " Khach | aturian", ["Khachaturian"], one) == "correct"
    assert fam.name_gate("correct", "Henry | James", ["Henry James"], one) == "correct"
    assert fam.name_gate("correct", "Tunis | dynasty", ["Hafsid dynasty"], one) == "name_miss"
    two = [_toks(44, -1, " Henry"), _toks(44, -2, " James")]
    assert fam.name_gate("correct", "Henry | James", ["Henry James"], two) == "unverified"


def test_language_unit_takes_no_name_gate(tmp_path, monkeypatch, real_families):
    """The language unit's evidence may be the passage's own words (QUESTION_LANGUAGE): a
    verified quote of a Finnish sentence is a correct language pick, never a name_miss."""
    it = _item("brh-fi-ahvenanmaa")
    text = f"R:{it['id']} Tämä alue on jäänyt Suomen alueeksi edelleen."
    r, _f = _run(
        tmp_path,
        monkeypatch,
        {it["id"]: {"readout": "cannot", "language": "gold"}},
        items=[it["id"]],
        text_of=lambda i, layer, pos: [text],
        quotes={f"{it['id']}|language": "Tämä alue on jäänyt Suomen alueeksi"},
    )
    assert r.rows[0]["unit_correct"]["language"] is True and r.rows[0]["pass"] is False
    assert "name_miss" not in r.extras["kinds"]


def test_name_miss_is_reported(tmp_path, monkeypatch, real_families):
    # an item whose id names no gold form: the fake readout line starts with "R:<id>", and the
    # F4 gate credits a gold pick on ANY line that singles the gold out, so an id such as
    # brh-ent-aghlabid-dynasty would itself name the gold on that line
    it = _item("brh-ent-cur-ngultrum-subunit")
    r, _f = _run(
        tmp_path,
        monkeypatch,
        {it["id"]: {"readout": "gold"}},
        items=[it["id"]],
        text_of=lambda i, layer, pos: [f"R:{i['id']} a famous thing"],
        quotes={f"{it['id']}|readout": "a famous thing"},
    )
    assert r.rows[0]["pass"] is False and r.extras["kinds"].get("name_miss") == 1
    assert r.extras["name_misses"][0]["quote"] == "a famous thing"


# ---------------------------------------------------------------- item 9: no world knowledge


def test_native_tokens_make_no_interp_call(tmp_path, monkeypatch, real_families):
    it = _item("brh-ent-")
    rows = [{"id": it["id"], "layer": 44, "pos": p, "tokens": ["volcano", "Mount", "Gunung"]}
            for p in range(-8, 0)]  # fmt: skip
    path = tmp_path / "t.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    _one_bank(monkeypatch, tmp_path, [it["id"]])
    write_sidecar(path, sampling="tokens10", plan_sha=reads.plan_sha(NAME))
    fake = FakeLLM.install(monkeypatch, judge=_cannot)
    r = registry.FAMILIES[NAME].run(_args(path, tmp_path / "out"))
    assert r.complete and {n for n, _s, _u in fake.calls} == {"pick"}
    assert not any("interp" in s.lower() for _n, s, _u in fake.calls)


# ---------------------------------------------------------------- G3 / G4 / G5


def test_prompt_only_cell_judged_full_and_lite(tmp_path, monkeypatch, real_families):
    it = _item("brh-ent-")
    path = tmp_path / "po.jsonl"
    row = {"id": it["id"], "layer": 44, "pos": -1, "samples": [f"R:{it['id']} it is {_gold(it)}"]}
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n")
    _one_bank(monkeypatch, tmp_path, [it["id"]])
    write_sidecar(path, reader="prompt_only:claude-opus-5-5", plan_sha=reads.plan_sha(NAME))
    FakeLLM.install(
        monkeypatch, judge=_responder({it["id"]: {"readout": "gold", "gold_readout": _gold(it)}})
    )
    for mode in ("full", "lite"):
        r = registry.FAMILIES[NAME].run(
            _args(path, tmp_path / mode, layers=None, extra={"reads": mode})
        )
        assert r.rows[0]["pass"] is True and r.complete, mode


def test_layers_subset_and_single(tmp_path, monkeypatch, real_families):
    it = _item("brh-ent-")
    path = _file(tmp_path, [it], lambda i, layer, p: ["s"], layers=(40, 44), positions=range(-8, 0))
    FakeLLM.install(monkeypatch, judge=_cannot)
    out = tmp_path / "o"
    argv = [f"family={NAME}", f"readouts={path}", f"out={out}", "layers=44", f"items={it['id']}"]
    assert main(["judge", *argv]) == 0
    r = read_results(out)
    assert r.config["layers_judged"] == [44]
    keys = [json.loads(x)["key"] for x in (out / "cells.jsonl").read_text().splitlines()]
    assert f"digest:{it['id']}|44" in keys


def test_mc_rows_feed_ati_gate(tmp_path, monkeypatch, real_families):
    from wsbench.baselines import text_inversion as ti

    it = _item("brh-ent-")
    r, _f = _run(tmp_path, monkeypatch, {it["id"]: {"readout": "gold"}}, items=[it["id"]])
    p = tmp_path / "res" / "results.json"
    p.parent.mkdir()
    p.write_text(json.dumps({"family": NAME, "config": {}, "rows": r.rows,
                             "numbers": {"metric": "pass_rate", "value": r.value}}))  # fmt: skip
    assert ti.draw_verdicts(p) == {it["id"]: True}
    assert r.extras["n_items_gold_any_layer"] == 1
    assert ti.STRICTER_PASS_FIELD[NAME] == "any_hit"


def test_regex_continuity_column(tmp_path, monkeypatch, real_families):
    it = _item("brh-ent-")
    r, _f = _run(tmp_path, monkeypatch, {it["id"]: {"readout": "cannot"}}, items=[it["id"]])
    assert set(r.extras["regex"]) >= {"value", "any_hit_rate"}


def test_option_sets_default_cannot_unchanged():
    _h, items = load_bank(V1)
    assert option_sets(items)[items[0]["id"]]["readout"][0][-1] == CANNOT
    assert option_sets(items, cannot=mc.CANNOT)[items[0]["id"]]["readout"][0][-1] == mc.CANNOT


def test_native_lines_verify_a_cell_quote():
    c = Cell("a", 44, -1, ("it is Triton",), None, None, None)
    assert digest.quote_ok("Triton", digest.native_lines([c]))

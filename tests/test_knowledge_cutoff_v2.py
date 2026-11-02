"""knowledge_cutoff plan 0044: bank v2 (C1), every position and layer (C2), the new prompts and
menu (C3, C6), the answer-head gate G1 (C4), minimum support G2 and numeric plurality G3 (C5),
numerals / token pieces / the quote boundary (C7), prompt-only and lucky floors (C8) and nocot
redaction (C9). ``run_calls`` / the LLM are scripted; nothing calls an API."""

import hashlib
import json
import re
from pathlib import Path

import pytest
from conftest import native_args, write_jsonl, write_sidecar
from summary_fakes import FakeLLM, first_lines_digest, summary_args

from wsbench import digest, mc, nocot, readplan, reads, registry
from wsbench.evals import knowledge_cutoff
from wsbench.evals.knowledge_cutoff import judge, prompts, score
from wsbench.evals.knowledge_cutoff.prompts import LETTERS, PROMPT_VERSION
from wsbench.judge_config import resolve

REPO = Path(__file__).resolve().parents[1]
V1 = REPO / "evals/knowledge_cutoff/items.json"
V2 = REPO / "evals/knowledge_cutoff/items_v2.json"
OBSCURE = REPO / "evals/knowledge_cutoff/obscure_items.json"
FIXTURE_BANK = REPO / "tests/fixtures/knowledge_cutoff_pre_refill_items.json"
NULL_LINT = re.compile(
    r"not traded|\bnone\b|no club|unknown|trick question|cannot|never|n/a|does not exist|"
    r"did not|has not|refus"
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _item(iid: str, gold: str, options: list[str], units: dict | None = None, user: str = ""):
    units = units or {}
    return {
        "id": iid,
        "user": user or f"Question {iid}? Answer with just the answer.",
        "gold": gold,
        "options": options,
        "option_units": {o: units.get(o, [o]) for o in options},
        "stratum": "A",
        "label_type": "stale",
        "truth": {"canonical": next(o for o in options if o != gold)},
    }


@pytest.fixture
def bank(tmp_path, monkeypatch):
    """Point the family at a synthetic frozen bank of the given items."""

    def make(*items):
        p = tmp_path / "bank.json"
        p.write_text(json.dumps({"items": list(items)}), "utf-8")
        monkeypatch.setenv("WSB_BANK_FILE_KNOWLEDGE_CUTOFF", str(p))
        return {it["id"]: it for it in items}

    return make


@pytest.fixture
def scripted(monkeypatch):
    """``answers[(item, layer)] = (option text | "NONE", quote)``; unlisted -> NONE."""
    answers: dict = {}
    seen: list = []

    def run_calls(calls, **kw):
        out = {}
        for c in calls:
            seen.append(c)
            opt, quote = answers.get((c.meta["item"], c.meta["layer"]), ("NONE", ""))
            items = {it["id"]: it for it in judge.load_items()}
            letter = (
                "NONE" if opt == "NONE" else LETTERS[items[c.meta["item"]]["options"].index(opt)]
            )
            out[c.key] = {"reasoning": "", "answer": letter, "quote": quote}
        return out

    monkeypatch.setattr(judge, "run_calls", run_calls)
    return answers, seen


def _args(path: Path, out: Path, ids, **kw):
    base = {
        "readouts": path,
        "out": out,
        "judge": resolve(knowledge_cutoff.SPEC.judge),
        "layers": None,
        "items": list(ids),
        "limit": 0,
        "allow_missing": False,
        "concurrency": 1,
        "rpm": 1.0,
        "dry_run": False,
    }
    base.update(kw)
    return native_args(**base)


def _cells(iid: str, layer: int, by_pos: dict[int, list[str]]) -> list[dict]:
    return [{"id": iid, "layer": layer, "pos": p, "samples": s} for p, s in sorted(by_pos.items())]


def _span(iid: str, layer: int, last: list[str], n: int = 4, filler: str = "context") -> list[dict]:
    """A full -n..-1 span: ``filler`` at every position but -1, ``last`` at -1."""
    return _cells(iid, layer, {p: (last if p == -1 else [filler]) for p in range(-n, 0)})


def _row(r, iid):
    return {x["id"]: x for x in r.rows}[iid]


# ---------------------------------------------------------------- C1 bank


def test_v1_bank_unchanged():
    assert _sha(V1) == "bf344c1b9b19a4bd71af7b4158b1154082a0dd97d339085cbd271240efde4bf1"
    assert _sha(OBSCURE) == "f7f35a6c1be289567548ce1639a2291f14c87a325fb42b03952a2c079a8761ab"


def test_registered_bank_is_v2(real_families):
    assert registry.bank_path("knowledge_cutoff").name == "items_v2.json"
    assert json.loads(V2.read_text("utf-8"))["version"] == 2
    assert len(judge.load_items()) == 147


def test_bank_v2_has_no_null_or_refusal_options():
    b = json.loads(V2.read_text("utf-8"))
    items = [*b["items"], *json.loads(OBSCURE.read_text("utf-8"))["items"]]
    for it in items:
        for o in it["options"]:
            assert not NULL_LINT.search(o.lower()) and len(o) <= 60 and o != "0", (it["id"], o)
        assert it["gold"] in it["options"] and set(it["option_units"]) >= set(it["options"])
    frozen = b["items"]
    assert b["n_items"] == len(frozen) == 108
    mix = {k: sum(it["label_type"] == k for it in frozen) for k in b["label_mix"]}
    strata = {k: sum(it["stratum"] == k for it in frozen) for k in b["strata"]}
    assert mix == b["label_mix"] == {"stale": 55, "confab_plausible": 51, "confab_weird": 2}
    assert strata == b["strata"] == {"A": 96, "B": 12}
    assert [r["id"] for r in b["retired_hygiene"]] == ["cs01301"]


def test_v2_is_v1_minus_cs01301_plus_aliases():
    v1 = {it["id"]: it for it in json.loads(V1.read_text("utf-8"))["items"]}
    b2 = json.loads(V2.read_text("utf-8"))
    v2 = {it["id"]: it for it in b2["items"]}
    assert set(v1) - set(v2) == {"cs01301"} and set(v2) <= set(v1)
    added: dict = {}
    for r in b2["near_alias_review"]:
        if r["verdict"] == "accept":
            added.setdefault(r["id"], {}).setdefault(r["option"], []).append(r["form"])
    for iid, it in v2.items():
        old = v1[iid]
        assert {k: v for k, v in it.items() if k != "option_units"} == {
            k: v for k, v in old.items() if k != "option_units"
        }
        for o, forms in it["option_units"].items():
            assert forms[: len(old["option_units"][o])] == old["option_units"][o]
            assert forms[len(old["option_units"][o]) :] == added.get(iid, {}).get(o, [])
    assert b2["g1_conditional_floor"] == 0.2739
    header_v1 = {k: v for k, v in json.loads(V1.read_text("utf-8")).items() if k != "items"}
    assert b2["contract"] == header_v1["contract"]


# ---------------------------------------------------------------- C2 positions and layers


def test_plan_every_position_every_grid_layer():
    plan = readplan.plan("knowledge_cutoff")
    assert len(plan) == 147 and any(s.extra.get("source") == "nocot" for s in plan)
    for s in plan:
        assert s.positions == {"kind": "all_from_end"} and s.layers == readplan.GRID
        assert s.lite_positions == {"kind": "final_token"} and s.lite_layers is None
    every = readplan.plan("knowledge_cutoff", layers="all")
    assert every[0].layers == list(range(64))
    lite = readplan.plan("knowledge_cutoff", reads="lite")
    assert lite[0].positions == {
        "kind": "lite_of",
        "full": {"kind": "all_from_end"},
        "lite": {"kind": "final_token"},
    }


def test_spec_reads_fields():
    s = knowledge_cutoff.SPEC
    assert s.min_full_positions == 4 and s.full_contiguous is True
    assert s.flat_types == ("numbers", "dates") and s.multi_select is False
    assert (
        s.task_note == prompts.DIGEST_TASK_NOTE and s.not_in_macro == "" and s.metric == "pass_rate"
    )
    assert digest.FAMILY_DEFAULTS["knowledge_cutoff"] == {"summ_max": "25", "summ_rare": "25"}


KIRINS = ["kirin 9100", "kirin 9020", "kirin 9000s", "kirin 9010", "kirin 9200"]
GOLD = _item(
    "k1",
    "kirin 9100",
    KIRINS,
    {"kirin 9100": ["Kirin 9100", "麒麟9100"], "kirin 9020": ["Kirin 9020"]},
)
NUM = _item("k2", "64", ["128", "256", "512", "32", "64"], {"64": ["64", "64 GB"]})


def test_full_requires_contiguous_span(tmp_path, bank, scripted):
    bank(GOLD, NUM)
    answers, _ = scripted
    answers[("k1", 60)] = ("kirin 9100", "Kirin 9100")
    full = [*_span("k1", 60, ["Kirin 9100", "Kirin 9100."]), *_span("k2", 60, ["64", "64 GB"])]
    p = write_jsonl(tmp_path / "full.jsonl", full)
    write_sidecar(p, reads="full", sampling="bullet4", reader="s3d-rl600", layers=[60])
    r = judge.run(_args(p, tmp_path / "o1", ["k1", "k2"], layers=[60]))
    assert r.config["reads_checked"] == "sidecar" and not r.extras.get("partial_ids")
    assert _row(r, "k1")["pass"] is True
    legacy = [x for x in full if x["pos"] in (-1,)] + [
        {**x, "pos": q} for x in full if x["pos"] == -4 for q in (-10, -2)
    ]
    p2 = write_jsonl(tmp_path / "legacy.jsonl", legacy)
    write_sidecar(p2, reads="full", sampling="bullet4", reader="s3d-rl600", layers=[60])
    with pytest.raises(SystemExit) as e:
        judge.run(_args(p2, tmp_path / "o2", ["k1", "k2"], layers=[60]))
    assert e.value.code == 2
    r2 = judge.run(_args(p2, tmp_path / "o3", ["k1", "k2"], layers=[60], allow_missing=True))
    assert set(r2.extras["partial_ids"]) == {"k1", "k2"} and r2.complete is False
    lone = [x for x in full if x["pos"] == -1]
    p3 = write_jsonl(tmp_path / "lone.jsonl", lone)
    write_sidecar(p3, reads="full", sampling="bullet4", reader="s3d-rl600", layers=[60])
    with pytest.raises(SystemExit):
        judge.run(_args(p3, tmp_path / "o4", ["k1", "k2"], layers=[60]))
    p4 = write_jsonl(tmp_path / "lite.jsonl", full)
    write_sidecar(p4, reads="lite", sampling="bullet4", reader="s3d-rl600", layers=[60])
    with pytest.raises(SystemExit):
        judge.run(_args(p4, tmp_path / "o5", ["k1", "k2"], layers=[60]))
    p5 = write_jsonl(tmp_path / "sha.jsonl", full)
    write_sidecar(p5, sampling="bullet4", reader="s3d-rl600", layers=[60], plan_sha="0" * 64)
    with pytest.raises(SystemExit):
        judge.run(_args(p5, tmp_path / "o6", ["k1", "k2"], layers=[60], allow_missing=True))


def test_full_on_lite_file_exits_2(tmp_path, bank, scripted):
    bank(GOLD)
    p = write_jsonl(tmp_path / "r.jsonl", _span("k1", 60, ["Kirin 9100"]))
    write_sidecar(p, reads="lite", sampling="prose1", reader="s3d-rl600", layers=[60])
    with pytest.raises(SystemExit) as e:
        judge.run(_args(p, tmp_path / "o", ["k1"], layers=[60]))
    assert e.value.code == 2


def test_kc_sidecarless_legacy_file_is_report_only(tmp_path, bank, scripted):
    bank(GOLD, NUM)
    rows = [x for it in ("k1", "k2") for x in _cells(it, 60, {-10: ["x"], -2: ["x"], -1: ["y"]})]
    r = judge.run(_args(write_jsonl(tmp_path / "r.jsonl", rows), tmp_path / "o", ["k1", "k2"]))
    assert r.config["reads_checked"] == "no_sidecar"
    assert set(r.extras["partial_ids_unenforced"]) == {"k1", "k2"}
    assert r.extras.get("partial_ids", []) == []


def test_all_layer_producer_file_is_judged(tmp_path, bank, scripted):
    """Late critique fix (1): plan_sha does not hash layers, so a file read at all 64 layers
    carries the judge's plan_sha and every layer is judged."""
    bank(GOLD)
    _answers, seen = scripted
    rows = [x for L in range(64) for x in _span("k1", L, ["Kirin 9100", "Kirin 9100."])]
    p = write_jsonl(tmp_path / "r.jsonl", rows)
    sha = reads.plan_sha("knowledge_cutoff")
    assert (
        reads.plan_sha_rows(s.row() for s in readplan.plan("knowledge_cutoff", layers="all")) == sha
    )
    write_sidecar(p, sampling="prose1", reader="s3d-rl600", layers=list(range(64)), plan_sha=sha)
    r = judge.run(_args(p, tmp_path / "o", ["k1"]))
    assert r.extras["candidate_layers"] == list(range(64)) and len(seen) == 64
    assert not r.extras.get("partial_ids") and r.config["reads_checked"] == "sidecar"


def test_layers_arbitrary_summary_and_native(tmp_path, bank, scripted, monkeypatch):
    bank(GOLD)
    for layers in ([3, 17, 44], [44]):
        rows = [x for L in layers for x in _span("k1", L, ["Kirin 9100"])]
        p = write_jsonl(tmp_path / f"r{len(layers)}.jsonl", rows)
        nat = judge.run(_args(p, tmp_path / f"n{len(layers)}", ["k1"], layers=layers))
        assert nat.config["layers_judged"] == layers
        bundles: list[str] = []

        def dig(user, bundles=bundles):
            bundles.append(user)
            return first_lines_digest(user, 50)

        FakeLLM.install(monkeypatch, lambda s, u, sc: None, digest=dig)
        sm = judge.run(summary_args(p, tmp_path / f"s{len(layers)}", PROMPT_VERSION,
                                    items=["k1"], layers=layers))  # fmt: skip
        assert sm.config["layers_judged"] == layers
        # audit F1: one digest per read layer; together they carry every layer
        heads = set(re.findall(r"\[L(\d+) pos -\d+\]", "\n".join(bundles)))
        assert heads == {str(L) for L in layers}


def test_summary_bundles_every_loaded_line(tmp_path, bank, monkeypatch):
    bank(GOLD, NUM)
    rows = [
        {"id": it, "layer": L, "pos": p, "samples": [f"{it} L{L} p{p} s{j}" for j in range(4)]}
        for it in ("k1", "k2") for L in (20, 40, 60) for p in range(-30, 0)
    ]  # fmt: skip
    p = write_jsonl(tmp_path / "r.jsonl", rows)
    write_sidecar(p, sampling="bullet4", reader="rl-onchat-x4", layers=[20, 40, 60])
    seen: list[str] = []
    FakeLLM.install(monkeypatch, lambda s, u, sc: None,
                    digest=lambda u: seen.append(u) or first_lines_digest(u))  # fmt: skip
    r = judge.run(summary_args(p, tmp_path / "o", PROMPT_VERSION, items=["k1", "k2"],
                               layers=[20, 40, 60]))  # fmt: skip
    # 3 layers x 30 positions x 4 samples per item; 720 lines over the two items (audit F1: one
    # digest per item and read layer, 30 x 4 = 120 lines each; each re-asked once, audit F3: the
    # fake keeps 3 < digest.COLLAPSE_MIN entries from 120 >= COLLAPSE_READOUTS readouts)
    assert [sum(1 for ln in u.splitlines() if ln.startswith("- ")) for u in seen] == [120] * 12
    s = r.extras["summary"]
    assert s["n_readouts_in"] == s["n_readouts_bundled"] == 720


def test_s3d_prose1_is_one_sample_per_activation(tmp_path, bank):
    bank(GOLD)
    rules = judge.ItemRules.of(judge.load_items()[0])
    gen = "- Kirin 9100\n- Huawei chip\n- a tri-fold phone\n- Kirin 9100 again"
    rows = _span("k1", 60, [gen, "a second generation the producer never sent"])
    p = write_jsonl(tmp_path / "r.jsonl", rows)
    write_sidecar(p, sampling="prose1", reader="s3d-rl600", layers=[60])
    cells, _rep = reads.load(_args(p, tmp_path / "o", ["k1"], layers=[60]), "knowledge_cutoff")
    last = [c for c in cells if c.pos == -1]
    assert [len(c.samples) for c in last] == [1]
    lines = digest.native_lines(last)
    assert len(lines) == 1 and lines[0].text.count(digest.BULLET_MARK) == 3
    assert judge.support(last, rules).counts["kirin 9100"] == 1  # one generation counts once


def test_reads_lite_selects_reply_start(tmp_path, bank, scripted):
    bank(GOLD)
    answers, seen = scripted
    answers[("k1", 60)] = ("kirin 9100", "Kirin 9100")
    p = write_jsonl(tmp_path / "r.jsonl", _span("k1", 60, ["Kirin 9100"], filler="Kirin 9020"))
    r = judge.run(_args(p, tmp_path / "o", ["k1"], layers=[60], extra={"reads": "lite"}))
    assert seen[0].meta["positions"] == [-1]
    assert r.config["reads"] == "lite" and r.config["prompt_version"].endswith("+reads-lite")
    assert _row(r, "k1")["pass"] is True


# ---------------------------------------------------------------- C3 / C6 prompts and menu


def test_menu_shows_every_accepted_form():
    units = {"aruba networking": ["Aruba Networking", "Aruba Networks", "HPE Aruba Networking",
                                  "aruba networking", "安移通网络"]}  # fmt: skip
    opts = ["aruba networking", "aruba instant", "aruba central", "instant on", "aruba clearpass"]
    for render in (
        prompts.render_user([(-1, ["x"])], opts, units),
        prompts.render_user_summary("- [one] x", "NOTE", opts, units),
    ):
        menu = render.split("=== OPTIONS ===\n", 1)[1].split("\n\nWhich option", 1)[0]
        paras = menu.split("\n\n")
        assert paras[0].splitlines() == [f"{LETTERS[k]}. {o}" for k, o in enumerate(opts)]
        assert paras[1].splitlines() == [
            prompts.FORMS_HEAD,
            "A: Aruba Networks; HPE Aruba Networking; 安移通网络",
        ]
        assert paras[-1] == mc.KC_NONE
    many = {"o": [f"form {i}" for i in range(12)] + ["中文"]}
    assert len(prompts.extra_forms("o", many["o"])) == prompts.MAX_FORMS


def test_kc_flat_list_is_options_relative(tmp_path, bank, scripted, monkeypatch):
    note = mc.token_note(("numbers", "dates"), multi_select=False)
    assert prompts.token_note() == note == prompts.PROMPTS["TOKEN_NOTE"]
    assert "ranked first" not in prompts.SYSTEM and "mostly" not in prompts.SYSTEM
    assert prompts.system_for(True).endswith(note) and note not in prompts.system_for(False)
    jup = _item("j", "jupiter", ["mars", "mercury", "jupiter", "venus", "earth"])
    tok = _item("t", "131072", ["131072", "262144", "8192", "4096", "32768"])
    bank(jup, tok)
    answers, seen = scripted

    def toks(iid, words):
        return {"id": iid, "layer": 60, "pos": -1, "tokens": words, "scores": [1.0] * len(words)}

    rows = [
        toks("j", ["Jupiter", "giant", "planet", "none"]),
        {**toks("j", ["Jupiter", "giant", "planet", "none"]), "pos": -2},
        toks("t", ["131072", "262144", "8192", "4096", "32768"]),
        {**toks("t", ["131072", "262144", "8192", "4096", "32768"]), "pos": -2},
    ]
    answers[("j", 60)] = ("jupiter", "Jupiter | giant | planet | none")
    answers[("t", 60)] = ("131072", "131072")
    r = judge.run(_args(write_jsonl(tmp_path / "r.jsonl", rows), tmp_path / "o", ["j", "t"]))
    assert all(note in c.system for c in seen)
    assert _row(r, "j")["pass"] is True and _row(r, "j")["support"] == 2
    assert _row(r, "t")["pass"] is False and _row(r, "t")["support"] == 0
    # summary mode renders the same note from the spec
    FakeLLM.install(monkeypatch, lambda s, u, sc: None, digest=lambda u: first_lines_digest(u, 50))
    users: list[str] = []
    monkeypatch.setattr(
        judge, "run_calls", lambda calls, **kw: users.extend(c.user for c in calls) or {}
    )
    judge.run(summary_args(tmp_path / "r.jsonl", tmp_path / "s", PROMPT_VERSION, items=["j", "t"]))
    assert users and all(note in u for u in users)


def test_task_note_and_pv():
    # round 3: the call fingerprint is unchanged; the gates add kcgate-v3 (review) to the stamp only
    assert PROMPT_VERSION == "cutoff-judge-2026-10-31+kcgate-v3"
    assert prompts.CALL_VERSION == "cutoff-judge-2026-10-31"
    assert "e.g." in prompts.SYSTEM and "never played" not in prompts.DIGEST_TASK_NOTE
    assert prompts.SUMMARY_INPUT_OLD in prompts.SYSTEM and prompts.READS_OLD in prompts.USER


# ---------------------------------------------------------------- C4 answer heads (G1)


def test_answer_head_markers():
    assert score.head_of("8192  # GPT-4o … 128,000 tokens").strip() == "8192"
    assert score.head_of('(e.g., "128k")') == ""
    k = "Kirin 9100, or possibly the Kirin 9020."
    assert score.head_of(k) == k
    ln = digest.native_lines(
        [judge.Cell("x", 60, -1, ("- 131072\n- 128000 (Note: the old limit)",), None, None)]
    )
    assert ln[0].text == "131072 ⁞ 128000 (Note: the old limit)"
    cells = [judge.Cell("x", 60, -1, ("- 131072\n- 128000 (Note: the old limit)",), None, None)]
    heads = score.answer_heads(digest.statement_lines(ln, cells))
    assert [h.strip() for h in heads] == ["131072", "128000"]


CS166 = _item("c166", "131072", ["128000", "131072", "1000000", "2000000", "4096"],
              {"131072": ["131 072", "131,072", "131072"],
               "128000": ["12.8万", "128 000", "128,000", "128000"]})  # fmt: skip


def test_note_number_never_verifies(tmp_path, bank, scripted):
    bank(CS166)
    answers, _ = scripted
    s = "131072  /* Note: the context was 128,000 tokens */"
    rows = _span("c166", 60, [s, s])
    path = write_jsonl(tmp_path / "r.jsonl", rows)
    answers[("c166", 60)] = ("128000", "128,000 tokens")
    r = judge.run(_args(path, tmp_path / "a", ["c166"]))
    assert _row(r, "c166")["verified"] is False and r.extras["gate_drops"]["contradicted"] == 0
    answers[("c166", 60)] = ("131072", "131072")
    r = judge.run(_args(path, tmp_path / "b", ["c166"]))
    assert _row(r, "c166")["verified"] is True and _row(r, "c166")["pass"] is True


def test_contradicted_gold_is_counted(tmp_path, bank, scripted):
    bank(CS166)
    answers, _ = scripted
    s = "128000 (Note: some say 131072)"
    path = write_jsonl(tmp_path / "r.jsonl", _span("c166", 60, [s, s]))
    answers[("c166", 60)] = ("131072", "some say 131072")
    r = judge.run(_args(path, tmp_path / "a", ["c166"]))
    assert _row(r, "c166")["pass"] is False and r.extras["gate_drops"]["contradicted"] == 1


def test_equal_value_is_not_a_contradiction(tmp_path, bank, scripted):
    it = _item("p", "999", ["999", "1099", "1199", "899", "799"])
    bank(it)
    answers, _ = scripted
    s = "999.00  # list price $999"
    path = write_jsonl(tmp_path / "r.jsonl", _span("p", 60, [s, "999", "$999"]))
    answers[("p", 60)] = ("999", "list price $999")
    r = judge.run(_args(path, tmp_path / "a", ["p"]))
    # the head 999.00 has the pick's value: no contradiction (an unequal head would be)
    assert _row(r, "p")["verified"] is True and _row(r, "p")["pass"] is True
    # an equal value in another spelling is not support by itself: only "999" and "$999" count
    assert _row(r, "p")["support"] == 2


def test_kc_quote_spanning_two_bullets_unverified(tmp_path, bank, scripted):
    bank(CS166)
    answers, _ = scripted
    gen = "- 131072\n- 128000 (Note: the old limit)"
    path = write_jsonl(tmp_path / "r.jsonl", _span("c166", 60, [gen, gen]))
    write_sidecar(path, sampling="bullet4", reader="t", layers=[60])
    answers[("c166", 60)] = ("131072", "131072 ⁞ 128000")
    r = judge.run(_args(path, tmp_path / "a", ["c166"], layers=[60]))
    assert _row(r, "c166")["verified"] is False and r.extras["n_unverified_bullet"] == 1


# ---------------------------------------------------------------- C5 support (G2, G3)

CS531 = _item("c531", "10", ["16", "24", "17", "10", "4"])


def test_min_support_single_mention_fails(tmp_path, bank, scripted):
    bank(CS531)
    answers, _ = scripted
    others = [f"The answer is {x}." for x in ("April", "May", "June")] * 6 + ["Maybe 2025."]
    rows = _cells("c531", 32, {-1: ["10 (Note: a guess)", *others]})
    rows += _cells("c531", 32, {p: ["context"] for p in (-4, -3, -2)})
    answers[("c531", 32)] = ("10", "10")
    r = judge.run(_args(write_jsonl(tmp_path / "r.jsonl", rows), tmp_path / "a", ["c531"]))
    assert _row(r, "c531")["pass"] is False and r.extras["gate_drops"]["min_support"] == 1
    rows[0]["samples"] = [*rows[0]["samples"], "10"]
    r = judge.run(_args(write_jsonl(tmp_path / "r2.jsonl", rows), tmp_path / "b", ["c531"]))
    assert _row(r, "c531")["pass"] is True


def test_number_flood_line_gives_no_support(bank):
    bank(CS531)
    rules = judge.ItemRules.of(judge.load_items()[0])
    tok = judge.Cell("c531", 60, -1, None, ("10", "12", "8", "6", "7", "9"), (6, 5, 4, 3, 2, 1))
    pro = judge.Cell("c531", 60, -2, ("10, 12, 8, 6 or 7",), None, None)
    sup = judge.support([tok, pro], rules)
    assert sup.counts["10"] == 0 and sup.flooded["10"] == 2


def test_kc_worked_prose_is_not_flood(tmp_path, bank, scripted):
    it = _item("w", "16384", ["16384", "8192", "4096", "2048", "1024"])
    bank(it)
    answers, _ = scripted
    worked = "16384 (8192 \u00d7 2 = 16384, up from 4096 in v1 and 2048 in v0)"
    answers[("w", 60)] = ("16384", "16384")
    r = judge.run(_args(write_jsonl(tmp_path / "a.jsonl", _span("w", 60, [worked, worked])),
                        tmp_path / "a", ["w"]))  # fmt: skip
    assert _row(r, "w")["pass"] is True and _row(r, "w")["support"] == 2
    flat = "16384, 8192, 4096, 2048 or 1024"
    r = judge.run(_args(write_jsonl(tmp_path / "b.jsonl", _span("w", 60, [flat, flat])),
                        tmp_path / "b", ["w"]))  # fmt: skip
    assert _row(r, "w")["pass"] is False and _row(r, "w")["support"] == 0


def test_kc_bulleted_number_list_gives_no_support(tmp_path, bank, scripted):
    it = _item("w", "16384", ["16384", "8192", "4096", "2048", "1024"])
    bank(it)
    answers, _ = scripted
    answers[("w", 60)] = ("16384", "16384")
    lst = "- 16384\n- 8192\n- 4096\n- 2048\n- 1024"
    path = write_jsonl(tmp_path / "a.jsonl", _span("w", 60, [lst, lst]))
    write_sidecar(path, sampling="bullet4", reader="t", layers=[60])
    r = judge.run(_args(path, tmp_path / "a", ["w"], layers=[60]))
    assert _row(r, "w")["support"] == 0 and _row(r, "w")["pass"] is False
    assert r.extras["gate_drops"]["number_flood"] == 1
    chain = "- Doubling 8192 gives 16384\n- up from 4096 in v1"
    answers[("w", 60)] = ("16384", "Doubling 8192 gives 16384")
    path = write_jsonl(tmp_path / "b.jsonl", _span("w", 60, [chain, chain]))
    write_sidecar(path, sampling="bullet4", reader="t", layers=[60])
    r = judge.run(_args(path, tmp_path / "b", ["w"], layers=[60]))
    assert _row(r, "w")["support"] == 2 and _row(r, "w")["pass"] is True


def test_kc_flood_is_called_on_whole_sample(tmp_path, bank, scripted, monkeypatch):
    it = _item("w", "16384", ["16384", "8192", "4096", "2048", "1024"])
    bank(it)
    answers, _ = scripted
    answers[("w", 60)] = ("16384", "16384")
    seen: list = []
    real = digest.number_flood

    def spy(line, **kw):
        seen.append(line.bullet)
        return real(line, **kw)

    monkeypatch.setattr(digest, "number_flood", spy)
    gen = "- 16384\n- 8192 (Note: older)"
    path = write_jsonl(tmp_path / "a.jsonl", _span("w", 60, [gen, gen]))
    judge.run(_args(path, tmp_path / "n", ["w"]))
    verdict = {"reasoning": "", "answer": "A", "quote": "16384"}
    FakeLLM.install(
        monkeypatch, lambda s, u, sc: verdict, digest=lambda u: first_lines_digest(u, 50)
    )
    judge.run(summary_args(path, tmp_path / "s", PROMPT_VERSION, items=["w"]))
    assert seen and all(b is None for b in seen)


def test_min_support_single_sample_file_needs_one(tmp_path, bank, scripted):
    bank(GOLD)
    answers, _ = scripted
    answers[("k1", 44)] = ("kirin 9100", "Kirin 9100")
    rows = [{"id": "k1", "layer": 44, "pos": -1, "samples": ["Kirin 9100"]}]
    p = write_jsonl(tmp_path / "r.jsonl", rows)
    r = judge.run(_args(p, tmp_path / "o", ["k1"]))
    assert _row(r, "k1")["pass"] is True and _row(r, "k1")["support"] == 1


def test_summary_support_counts_across_layers(tmp_path, bank, monkeypatch):
    bank(GOLD)
    rows = [x for L in (20, 40, 60) for x in _span("k1", L, ["Kirin 9100"])]
    p = write_jsonl(tmp_path / "r.jsonl", rows)
    verdict = {"reasoning": "", "answer": "A", "quote": "Kirin 9100"}
    FakeLLM.install(
        monkeypatch, lambda s, u, sc: verdict, digest=lambda u: first_lines_digest(u, 50)
    )
    r = judge.run(summary_args(p, tmp_path / "o", PROMPT_VERSION, items=["k1"]))
    assert _row(r, "k1")["support"] == 3 and _row(r, "k1")["pass"] is True


def test_numeric_plurality_gate(tmp_path, bank, scripted):
    it = _item("c170", "131072", ["32768", "131072", "2048", "8192", "262144"],
               user="Was it 32768 tokens? Answer with just the number.")  # fmt: skip
    bank(it)
    answers, _ = scripted
    answers[("c170", 56)] = ("131072", "131072")
    rows = _cells(
        "c170", 56, {-1: ["131072"] * 3 + ["262144"] * 5, -2: ["x"], -3: ["x"], -4: ["x"]}
    )
    r = judge.run(_args(write_jsonl(tmp_path / "a.jsonl", rows), tmp_path / "a", ["c170"]))
    assert _row(r, "c170")["pass"] is False and r.extras["gate_drops"]["numeric_plurality"] == 1
    # an option the item's own prompt names (32768) never blocks the pick
    rows = _cells("c170", 56, {-1: ["131072"] * 3 + ["32768"] * 5, -2: ["x"], -3: ["x"], -4: ["x"]})
    r = judge.run(_args(write_jsonl(tmp_path / "b.jsonl", rows), tmp_path / "b", ["c170"]))
    assert _row(r, "c170")["pass"] is True


def test_tokens10_drops_rank_17(tmp_path, bank, scripted):
    it = _item("c1524", "jupiter", ["mars", "mercury", "jupiter", "venus", "earth"])
    bank(it)
    answers, _ = scripted
    answers[("c1524", 48)] = ("jupiter", "Jupiter")
    words = [f"w{i}" for i in range(16)] + ["Jupiter", "a", "b", "c"]
    rows = [{"id": "c1524", "layer": 48, "pos": p, "tokens": words,
             "scores": [float(20 - i) for i in range(20)]} for p in (-2, -1)]  # fmt: skip
    p = write_jsonl(tmp_path / "r.jsonl", rows)
    write_sidecar(p, sampling="tokens10", reader="jlens", layers=[48])
    r = judge.run(_args(p, tmp_path / "o", ["c1524"], layers=[48], allow_missing=True))
    assert _row(r, "c1524")["pass"] is False and _row(r, "c1524")["verified"] is False


def test_ati_pass_ignores_gates(tmp_path, bank, scripted):
    bank(GOLD)
    answers, _ = scripted
    answers[("k1", 60)] = ("kirin 9100", "Kirin 9100")
    rows = _span("k1", 60, ["Kirin 9100", "Kirin 9020", "unclear"])
    r = judge.run(_args(write_jsonl(tmp_path / "r.jsonl", rows), tmp_path / "o", ["k1"]))
    row = _row(r, "k1")
    assert row["support"] == 1 and row["pass"] is False and row["ati_pass"] is True


def test_distractor_floor(tmp_path, bank, scripted):
    items = [_item(f"d{i}", "a1", ["a1", "b2", "c3", "d4", "e5"]) for i in range(4)]
    bank(*items)
    answers, _ = scripted
    answers[("d0", 60)] = ("b2", "b2")
    rows = [x for it in items for x in _span(it["id"], 60, ["b2", "b2"])]
    r = judge.run(_args(write_jsonl(tmp_path / "r.jsonl", rows), tmp_path / "o",
                        [it["id"] for it in items]))  # fmt: skip
    assert r.extras["distractor_floor"] == 0.0625
    assert r.extras["layer_pick_columns"]["n_items_distractor_any_layer"] == 1


# ---------------------------------------------------------------- C6 near aliases


def test_near_alias_a321_credits_a321neo(real_families):
    it = next(x for x in judge.load_items() if x["id"] == "cs01684")
    menu = prompts.menu(it["options"], it["option_units"])
    letter = LETTERS[it["options"].index("a321neo")]
    line = next(ln for ln in menu.splitlines() if ln.startswith(f"{letter}: "))
    assert "A321" in line.split("; ") and "Airbus A321" in line
    rules = judge.ItemRules.of(it)
    assert rules.forms.named("Airbus A321", numerals=True) == {"a321neo"}
    assert rules.forms.named("the A320neo", numerals=True) == {"a320neo"}


def test_near_alias_additions_are_unambiguous():
    b = json.loads(V2.read_text("utf-8"))
    by = {it["id"]: it for it in b["items"]}
    assert b["near_alias_review"] and all(r["verdict"] in ("accept", "reject") and r["reason"]
                                          for r in b["near_alias_review"])  # fmt: skip
    for r in b["near_alias_review"]:
        if r["verdict"] != "accept":
            continue
        it = by[r["id"]]
        assert mc.form_in(r["form"], it["option_units"][r["option"]])
        rules = judge.ItemRules.of(it)
        assert rules.forms.named(r["form"]) == {r["option"]}, r
        for o, forms in it["option_units"].items():
            if o != r["option"]:
                assert not any(mc.fold(f) == mc.fold(r["form"]) for f in forms)


def test_listed_alias_verifies(tmp_path, monkeypatch, scripted):
    monkeypatch.setenv("WSB_BANK_FILE_KNOWLEDGE_CUTOFF", str(FIXTURE_BANK))
    answers, _ = scripted
    s = "Just give the name: Aruba Networks"
    answers[("cs00312", 56)] = ("aruba networking", s)
    p = write_jsonl(tmp_path / "r.jsonl", _span("cs00312", 56, [s, "Aruba Networks."]))
    r = judge.run(_args(p, tmp_path / "o", ["cs00312"]))
    assert _row(r, "cs00312")["pass"] is True


def test_cjk_alias_needs_listed_form(real_families):
    it = next(x for x in judge.load_items() if x["id"] == "cs01684")
    rules = judge.ItemRules.of(it)
    assert rules.forms.named("空客", numerals=True) == set()
    assert rules.forms.named("空客A321", numerals=True) == {"a321neo"}


# ---------------------------------------------------------------- C7 numerals, tokens, boundary


def test_numerals_credit_integer_options():
    f = score.OptionForms.build({"19": ["19"], "24": ["24"], "1": ["1"], "2": ["2"], "5": ["5"]})
    for text in ("十九", "第十九", "XIX"):
        assert f.named(text, numerals=True) == {"19"}, text
    assert f.named("twenty-four", numerals=True) == {"24"}
    assert f.named("I think two", numerals=True) == set()  # "I" and "two" in prose: no credit
    assert f.named("two", numerals=True, tokens=True) == {"2"}  # a token row: always
    assert f.named("XIX") == set()  # the regex diagnostics / ati_pass never use the numeral path
    assert score.roman_value("IIII") is None and score.roman_value("XC") is None


def test_token_first_piece_and_same_list_words(tmp_path, bank, scripted):
    chr_ = {"christies": ["Christie's", "Christies"], "sothebys": ["Sotheby's"]}
    f = score.OptionForms.build(chr_)
    assert score.token_named([" Christie", " auction"], f, chr_) == {"christies"}
    vw = {"volkswagen golf": ["volkswagen golf", "Golf"], "toyota corolla": ["toyota corolla"]}
    fv = score.OptionForms.build(vw)
    assert score.token_named([" Volkswagen", " car"], fv, vw) == set()
    assert score.token_named([" Golf"], fv, vw) == {"volkswagen golf"}
    k = {"kirin 9100": ["Kirin 9100"], "kirin 9020": ["Kirin 9020"]}
    fk = score.OptionForms.build(k)
    assert score.token_named([" 9100", " x", " Kirin"], fk, k) == {"kirin 9100"}
    # across two lists: neither list names it
    assert (
        score.token_named([" Kirin"], fk, k) == set()
        and score.token_named([" 9100"], fk, k) == set()
    )
    # one word spelled across adjacent positions of ONE layer verifies; across layers it does not
    it = _item("sp", "kirin", ["kirin", "exynos", "tensor", "snapdragon", "dimensity"])
    bank(it)
    answers, _ = scripted
    answers[("sp", 60)] = ("kirin", "Kirin")
    rows = [
        {"id": "sp", "layer": 60, "pos": -2, "tokens": [" Kir", "x"], "scores": [2.0, 1.0]},
        {"id": "sp", "layer": 60, "pos": -1, "tokens": ["in", "y"], "scores": [2.0, 1.0]},
    ]
    r = judge.run(_args(write_jsonl(tmp_path / "a.jsonl", rows), tmp_path / "a", ["sp"]))
    assert _row(r, "sp")["verified"] is True
    rows[1]["layer"] = 56
    rows.append({"id": "sp", "layer": 60, "pos": -1, "tokens": ["zz"], "scores": [1.0]})
    rows.append({"id": "sp", "layer": 56, "pos": -2, "tokens": ["zz"], "scores": [1.0]})
    r = judge.run(_args(write_jsonl(tmp_path / "b.jsonl", rows), tmp_path / "b", ["sp"],
                        layers=[60]))  # fmt: skip
    assert _row(r, "sp")["verified"] is False


def test_truncated_number_quote_fails(tmp_path, bank, scripted):
    it = _item("c47", "5.7", ["11.5", "95", "5.6", "5.7", "5.2"],
               {"5.7": ["5.7", "5.7 GHz", "5700 MHz"]})  # fmt: skip
    bank(it)
    answers, _ = scripted
    s = "It has a boost clock of 5.75 GHz."
    path = write_jsonl(tmp_path / "r.jsonl", _span("c47", 48, [s, s]))
    answers[("c47", 48)] = ("5.7", "boost clock of 5.7")
    r = judge.run(_args(path, tmp_path / "o", ["c47"]))
    assert _row(r, "c47")["pass"] is False and r.extras["gate_drops"]["boundary"] == 1
    assert score.boundary_ok("boost clock of 5.75", s)


# ---------------------------------------------------------------- C8 floors / C9 redaction


def test_prompt_only_file_is_complete_under_full(tmp_path, bank, monkeypatch):
    bank(GOLD, NUM)
    rows = [{"id": i, "layer": 44, "pos": -1, "samples": [a]}
            for i, a in (("k1", "Kirin 9100"), ("k2", "64"))]  # fmt: skip
    p = write_jsonl(tmp_path / "r.jsonl", rows)
    write_sidecar(p, sampling="prose1", reader="prompt_only:claude-opus-5-5", layers=[44])
    FakeLLM.install(monkeypatch, lambda s, u, sc: None, digest=lambda u: first_lines_digest(u))
    r = judge.run(summary_args(p, tmp_path / "o", PROMPT_VERSION, items=["k1", "k2"]))
    assert (
        r.config["reads_checked"] == "prompt_only"
        and "+reads-lite" not in r.config["prompt_version"]
    )
    assert not r.extras.get("partial_ids")


def test_lucky_guessing_builder(real_families):
    from wsbench.baselines import lucky_guessing as lg

    items = lg.build_family("knowledge_cutoff")
    assert len(items) == 147 and all(len(it.lists[0]) == 5 for it in items)
    assert all(mc.KC_NONE not in it.lists[0] for it in items)


def test_nocot_rows_redacted_in_results(tmp_path, monkeypatch):
    ob = nocot.load_obscure()[1][0]
    gold = ob["gold"]
    rows = _span(ob["id"], 60, [f"The answer is {gold}.", f"The answer is {gold}."])
    p = write_jsonl(tmp_path / "r.jsonl", rows)
    FakeLLM.install(
        monkeypatch,
        lambda s, u, sc: {
            "reasoning": "",
            "answer": LETTERS[ob["options"].index(gold)],
            "quote": f"The answer is {gold}.",
        },
        digest=lambda u: first_lines_digest(u, 50),
    )
    r = judge.run(summary_args(p, tmp_path / "o", PROMPT_VERSION, items=[ob["id"]]))
    row = r.rows[0]
    assert row["source"] == "nocot" and row["pass"] is True
    assert row["quote"] == row["summary"] == judge.REDACTED
    assert row["summary_evidence"] == row["summary_statements"] == [judge.REDACTED]
    assert judge.unredacted_nocot(r.rows, {ob["id"]}) == []
    keep = judge.run(summary_args(p, tmp_path / "k", PROMPT_VERSION, items=[ob["id"]],
                                  extra={"keep_nocot_text": "1"}))  # fmt: skip
    assert judge.unredacted_nocot(keep.rows, {ob["id"]}) == [ob["id"]]
    # the bundle check refuses an unredacted results file and a nocot judge cache
    import importlib.util

    spec = importlib.util.spec_from_file_location("cnr", REPO / "scripts/check_nocot_redaction.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    good = tmp_path / "good" / "results.json"
    good.parent.mkdir()
    good.write_text(json.dumps({"rows": r.rows}))
    bad = tmp_path / "bad" / "results.json"
    bad.parent.mkdir()
    bad.write_text(json.dumps({"rows": keep.rows}))
    assert mod.check([good.parent]) == {}
    assert mod.check([bad.parent]) == {str(bad): [ob["id"]]}
    assert mod.check([tmp_path / "k"])  # its cells.jsonl caches nocot readouts

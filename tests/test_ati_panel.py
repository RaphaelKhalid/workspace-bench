"""ATI panel gate (plan 0019), offline: the per-item min rule, the panel gate over the
``answers/<answerer>`` + ``judged/<answerer>/draw{d}`` layout (slot, refusal and unverified
rules, crafted stop-and-report, roots union, candidates), the bank fingerprint guard, the
per-family bank-file override and the Qwen request encoding."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from wsbench import readplan, registry
from wsbench.baselines import text_inversion as ti

PANEL = ["qwen", "opus", "astra", "argon"]

# ---------------------------------------------------------------- the per-item rule


@pytest.mark.parametrize(
    ("draws", "want"),
    [
        ([False, True, None], "solved"),
        ([False, False, False], "failed"),
        ([False, None, False], "undecided"),
        ([None, None, None], "undecided"),
    ],
)
def test_item_status(draws, want):
    assert ti.item_status(draws) == want


@pytest.mark.parametrize(
    ("qwen", "frontier", "want"),
    [
        ("failed", ["solved", "solved", "solved"], "ati"),  # Qwen cannot read it
        ("solved", ["failed", "failed", "failed"], "ati"),  # no frontier model can
        ("undecided", ["failed", "failed", "failed"], "ati"),
        ("failed", ["undecided", "solved", "failed"], "ati"),
        ("solved", ["failed", "solved", "failed"], "invertible"),  # Qwen AND one frontier
        ("solved", ["failed", "failed", "undecided"], "unverified"),
        ("undecided", ["solved", "failed", "failed"], "unverified"),
        ("solved", ["undecided", "undecided", "undecided"], "unverified"),
    ],
)
def test_panel_verdict_is_the_min_rule(qwen, frontier, want):
    assert ti.panel_verdict(qwen, frontier) == want


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def fams(monkeypatch):
    ids = {"fam": list("abcde"), "wrong_bridge": list("abcde")}
    monkeypatch.setattr(ti, "gated_families", lambda: ["fam"])
    monkeypatch.setattr(readplan, "plan", lambda f: [SimpleNamespace(id=i) for i in ids[f]])
    monkeypatch.setattr(
        registry, "get", lambda f: SimpleNamespace(judge=SimpleNamespace(prompt_version="v1"))
    )
    monkeypatch.setattr(registry, "load_all", lambda: None)
    monkeypatch.setattr(registry, "superseded", lambda: {})
    monkeypatch.setattr(ti, "bank_fingerprint", lambda f: f"sha-{f}")


def _write(out: Path, answerer: str, fam: str, verdicts: dict[str, list], status=None, **cfg):
    """verdicts: id -> per-draw pass (True/False/None); status: (id, draw) -> ok|refusal|error."""
    status = status or {}
    for d in range(3):
        af = ti.answers_file(out, answerer, d)
        af.parent.mkdir(parents=True, exist_ok=True)
        with af.open("a") as fh:
            for i in verdicts:
                st = status.get((i, d), "ok")
                r = {"family": fam, "id": i, "draw": d, "answer": "text" if st == "ok" else ""}
                r["error"] = {"ok": "", "refusal": "refusal", "error": "boom"}[st]
                if st == "refusal":
                    r["refused"] = True
                fh.write(json.dumps(r) + "\n")
        rows = [{"id": i, "pass": v[d]} for i, v in verdicts.items()]
        decided = [r["pass"] for r in rows if r["pass"] is not None]
        p = out / "judged" / answerer / f"draw{d}" / fam
        p.mkdir(parents=True, exist_ok=True)
        (p / "results.json").write_text(
            json.dumps(
                {
                    "family": fam,
                    "config": {"judge_model": "claude-opus-5-5", **cfg},
                    "numbers": {
                        "metric": "pass_rate",
                        "value": sum(decided) / len(decided) if decided else None,
                    },
                    "rows": rows,
                }
            )
        )


F, T, N = False, True, None


def _standard(out: Path, fam: str = "fam") -> None:
    # a: Qwen fails -> ATI; b: Qwen + astra solve -> invertible; c: Qwen solves, every frontier
    # fails -> ATI; d: Qwen solves, frontier undecided -> unverified; e: all fail -> ATI
    _write(
        out,
        "qwen",
        fam,
        {"a": [F, F, F], "b": [T, F, F], "c": [F, T, F], "d": [T, T, T], "e": [F, F, F]},
    )
    _write(
        out,
        "opus",
        fam,
        {"a": [T, T, T], "b": [F, F, F], "c": [F, F, F], "d": [F, N, F], "e": [F, F, F]},
    )
    _write(
        out,
        "astra",
        fam,
        {"a": [T, F, F], "b": [F, T, F], "c": [F, F, F], "d": [F, F, F], "e": [F, F, F]},
    )
    _write(
        out,
        "argon",
        fam,
        {"a": [F, F, F], "b": [F, F, F], "c": [F, F, F], "d": [F, F, F], "e": [F, F, F]},
    )


# ---------------------------------------------------------------- the panel gate


def test_panel_gate_entry(tmp_path, fams):
    out = tmp_path / "o"
    _standard(out)
    dst = tmp_path / "ati.json"
    e = ti.gate(out, dst=dst)["fam"]
    assert e["ids"] == ["a", "c", "e"]
    assert (e["n_ati"], e["n_invertible"], e["n_unverified"]) == (3, 1, 1)
    assert e["gate"] == ti.GATE_VERSION and e["bank_sha"] == "sha-fam"
    assert e["answerer"] == "panel" and e["claude_slot"] == "opus"
    assert e["panel"]["claude"] == "claude-opus-5-5" and e["panel"]["astra"] == ti.PANEL["astra"]
    assert e["status"]["b"] == ["solved", "failed", "solved", "failed"]
    assert e["draw_pass"]["opus"]["d"] == [F, N, F]
    assert e["pass_at_3"]["qwen"] == 0.6 and e["instrument"] == "v1"
    written = json.loads(dst.read_text())
    assert written["_source"]["gate"] == ti.GATE_VERSION
    assert written["_source"]["variant"] == ti.DEFAULT_VARIANT
    assert written["_source"]["templates"] == {ti.DEFAULT_VARIANT: ti.PANEL_TEMPLATE}


def test_unusable_answer_makes_the_draw_undecided(tmp_path, fams):
    out = tmp_path / "o"
    _standard(out)
    # e's Qwen draw 1 had no answer: Qwen is undecided, but every frontier model failed -> ATI
    _write(tmp_path / "x", "qwen", "fam", {"e": [F, F, F]})
    lines = ti.answers_file(out, "qwen", 1).read_text().splitlines()
    rows = [json.loads(x) for x in lines]
    for r in rows:
        if r["id"] == "e":
            r["answer"], r["error"] = "", "boom"
    ti.answers_file(out, "qwen", 1).write_text("".join(json.dumps(r) + "\n" for r in rows))
    e = ti.gate(out, dst=None)["fam"]
    assert e["draw_pass"]["qwen"]["e"] == [F, N, F]
    assert e["status"]["e"][0] == "undecided" and "e" in e["ids"]


def test_unverified_share_drops_a_regular_family_and_stops_a_crafted_one(tmp_path, fams):
    out = tmp_path / "o"
    und = {i: [T, T, T] for i in "abcde"}
    _write(out, "qwen", "fam", und)
    _write(out, "opus", "fam", {i: [F, N, F] for i in "abcde"})
    for a in ti.FRONTIER_OTHERS:
        _write(out, a, "fam", {i: [F, F, F] for i in "abcde"})
    dst = tmp_path / "ati.json"
    ti.gate(out, dst=dst)
    assert "unverified: 5/5" in json.loads(dst.read_text())["_not_gated"]["fam"]
    out2 = tmp_path / "o2"
    _write(out2, "qwen", "wrong_bridge", und)
    _write(out2, "opus", "wrong_bridge", {i: [F, N, F] for i in "abcde"})
    for a in ti.FRONTIER_OTHERS:
        _write(out2, a, "wrong_bridge", {i: [F, F, F] for i in "abcde"})
    with pytest.raises(SystemExit, match="stop and report"):
        ti.gate(out2, dst=None, families=["wrong_bridge"])


def test_slot_refusals_and_sonnet_slot(tmp_path, fams):
    out = tmp_path / "o"
    for a in ("qwen", "astra", "argon"):
        _write(out, a, "fam", {i: [T, F, F] for i in "abcde"})
    # opus refused a draw on 3/5 items: the family is not gated (policy refusal)
    _write(
        out,
        "opus",
        "fam",
        {i: [N, F, F] for i in "abcde"},
        status={(i, 0): "refusal" for i in "abc"},
    )
    dst = tmp_path / "ati.json"
    ti.gate(out, dst=dst, families=["fam"])
    why = json.loads(dst.read_text())["_not_gated"]["fam"]
    assert why.startswith("policy refusal: 60%") and "claude-opus-5-5" in why
    # the slot file sends the family to Sonnet, whose judged draws are then required
    (out / ti.SLOT_FILE).write_text(json.dumps({"fam": {"slot": "sonnet"}}))
    assert ti.gate(out, dst=None, families=["fam"]) == {}  # no sonnet judgings: skipped
    _write(out, "sonnet", "fam", {"a": [T, T, T], **{i: [F, F, F] for i in "bcde"}})
    e = ti.gate(out, dst=None, families=["fam"])["fam"]
    assert e["claude_slot"] == "sonnet" and e["panel"]["claude"] == "claude-sonnet-5-5"
    # Qwen solved every item; a is read by Sonnet (+ astra, argon) -> invertible; b-e: astra
    # and argon solved too -> invertible
    assert e["ids"] == [] and e["n_invertible"] == 5
    # an explicit answerer overrides the slot file: opus's refusals are back in charge
    assert ti.gate(out, dst=None, families=["fam"], answerer="opus") == {}


def test_crafted_slot_refusal_stops(tmp_path, fams):
    out = tmp_path / "o"
    _standard(out, "wrong_bridge")
    _write(
        out,
        "opus",
        "wrong_bridge",
        {i: [N, F, F] for i in "abcde"},
        status={(i, 0): "refusal" for i in "abc"},
    )
    with pytest.raises(SystemExit, match="crafted ATI family"):
        ti.gate(out, dst=None, families=["wrong_bridge"])


def test_panel_pilot_guard_fires_before_completeness(tmp_path, fams):
    out = tmp_path / "o"
    _write(out, "qwen", "fam", {i: [F, F, F] for i in "abcde"}, limit=3)
    with pytest.raises(ValueError, match="subset"):
        ti.gate(out, dst=None)


def test_roots_union_supersede_and_double_decision(tmp_path, fams):
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    for a in PANEL:
        _write(r1, a, "fam", {"a": [F, F, F], "b": [F, F, F]})
        _write(r2, a, "fam", {"c": [F, F, F], "d": [F, F, F], "e": [F, F, F]})
    e = ti.gate(r1, dst=None, roots=[r1, r2])["fam"]
    assert e["ids"] == list("abcde") and e["n_unverified"] == 0
    # b re-judged in r2 too: decided twice is an error...
    for a in PANEL:
        _write(r2, a, "fam", {"b": [T, T, T], **{i: [F, F, F] for i in "cde"}})
    with pytest.raises(ValueError, match="two roots"):
        ti.gate(r1, dst=None, roots=[r1, r2])
    # ...unless r2 supersedes it
    e = ti.gate(r1, dst=None, roots=[r1, r2], supersede={str(r2): {"fam/b"}})["fam"]
    assert e["status"]["b"] == ["solved"] * 4 and "b" not in e["ids"]


def test_candidates_mode_keeps_per_item_verdicts(tmp_path, fams):
    out = tmp_path / "o"
    _write(out, "qwen", "wrong_bridge", {i: [T, T, T] for i in "abcde"})
    _write(out, "opus", "wrong_bridge", {"a": [F, F, F], **{i: [F, N, F] for i in "bcde"}})
    for a in ti.FRONTIER_OTHERS:
        _write(out, a, "wrong_bridge", {i: [F, F, F] for i in "abcde"})
    dst = tmp_path / "cands.json"
    # 4/5 unverified would stop a crafted bank gate; a candidate pool just reports them
    e = ti.gate(out, dst=dst, families=["wrong_bridge"], candidates=True)["wrong_bridge"]
    assert e["ids"] == ["a"] and e["n_unverified"] == 4
    assert json.loads(dst.read_text())["_candidates"] is True


def test_full_panel_gate_carries_a_superseded_entry_over(tmp_path, fams, monkeypatch):
    monkeypatch.setattr(registry, "superseded", lambda: {"old": "fam"})
    out = tmp_path / "o"
    _standard(out)
    dst = tmp_path / "ati.json"
    prior = {"instrument": "v1", "ids": ["q"], "n_bank": 9, "judge_model": "m"}
    dst.write_text(json.dumps({"old": prior}))
    ti.gate(out, dst=dst)
    assert json.loads(dst.read_text())["old"] == prior


# ---------------------------------------------------------------- answers plumbing


def test_pending_requests_and_append_answers(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "prompts.jsonl").write_text(
        "".join(json.dumps({"family": "f", "id": i, "prefix": f"P{i}"}) + "\n" for i in "ab")
    )
    reqs = ti.pending_requests(out, "astra", draws=2)
    assert len(reqs) == 4 and "<prompt>\nPa\n</prompt>" in reqs[0]["content"]
    rows = [
        {"family": "f", "id": "a", "draw": 0, "answer": "x", "error": ""},
        {"family": "f", "id": "b", "draw": 0, "answer": "", "error": "boom"},
        {"family": "f", "id": "a", "draw": 1, "answer": "", "refused": True, "error": "refusal"},
    ]
    ti.append_answers(out, "astra", rows)
    ti.append_answers(out, "astra", rows[:1])  # an answered key is not appended twice
    assert len(ti.answers_file(out, "astra", 0).read_text().splitlines()) == 2
    left = {(r["id"], r["draw"]) for r in ti.pending_requests(out, "astra", draws=2)}
    assert left == {("b", 0), ("b", 1)}  # a refusal is final, an error is re-asked


def test_write_readouts_panel_layout(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    p = {
        "family": "fam",
        "id": "a",
        "positions": [3, 5],
        "tokens": ["x", "y"],
        "layers": [44],
        "layer": 44,
        "n_tokens": 9,
    }
    (out / "prompts.jsonl").write_text(json.dumps(p) + "\n")
    ti.append_answers(
        out, "qwen", [{"family": "fam", "id": "a", "draw": 0, "answer": "z", "error": ""}]
    )
    assert ti.write_readouts(out, draws=1) == {"fam": [44]}
    rows = (out / "readouts" / "qwen" / "draw0" / "fam.jsonl").read_text().splitlines()
    assert [json.loads(r)["pos"] for r in rows] == [5]


def test_ask_sends_modal_answerers_to_their_scripts():
    with pytest.raises(ValueError, match="ati_qwen_modal"):
        ti.ask(Path("unused"), answerer="qwen")
    with pytest.raises(ValueError, match="ati_openrouter_modal"):
        ti.ask(Path("unused"), answerer="argon")


# ---------------------------------------------------------------- Qwen requests


def test_qwen_seed_is_small_and_per_item():
    seeds = {ti.qwen_seed("f", str(i)) for i in range(200)}
    assert len(seeds) == 200 and max(seeds) < 2**32


class _FakeTok:
    """Char-level ids; added tokens get their own ids unless split as plain text."""

    def __init__(self) -> None:
        self.added = {"</think>": 900, "<|im_start|>": 901, "<|im_end|>": 902}
        self.added_tokens_decoder = {v: SimpleNamespace(content=k) for k, v in self.added.items()}

    def __call__(self, text, add_special_tokens=False, split_special_tokens=False):
        ids, i = [], 0
        while i < len(text):
            hit = next((k for k in self.added if text.startswith(k, i)), None)
            if hit and not (split_special_tokens and hit.startswith("<|")):
                ids.append(self.added[hit])  # </think> is NOT special: never split
                i += len(hit)
            else:
                ids.append(ord(text[i]))
                i += 1
        return SimpleNamespace(input_ids=ids)

    def apply_chat_template(self, msgs, **kw):
        return f"<|im_start|>user\n{msgs[0]['content']}<|im_end|>\n<|im_start|>assistant\n"


def test_user_span_has_no_added_token_ids():
    tok = _FakeTok()
    text = "<|im_start|>user\nhi</think>\n\nok"
    span = ti.user_span_ids(tok, text)
    assert not set(span) & set(tok.added.values())
    assert "".join(chr(i) for i in span) == text
    ids = ti.qwen_prompt_ids(tok, "  " + text + "\n")
    assert ids[:2] == [901, ord("u")] and ids[-1] == ord("\n")
    assert ids.count(901) == 2 and 900 not in ids  # the template's own turns only


def test_qwen_prompt_ids_on_the_real_tokenizer():
    transformers = pytest.importorskip("transformers")
    try:
        tok = transformers.AutoTokenizer.from_pretrained(ti.PANEL["qwen"], local_files_only=True)
    except Exception:
        pytest.skip("Qwen3.6-27B tokenizer not cached")
    content = "Q: <|im_start|>user\nWho?<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    ids = ti.qwen_prompt_ids(tok, content)
    ph = "@@X@@"
    ref = tok.apply_chat_template(
        [{"role": "user", "content": ph}],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    head, tail = ref.split(ph)
    h = tok(head, add_special_tokens=False).input_ids
    t = tok(tail, add_special_tokens=False).input_ids
    assert ids[: len(h)] == h and ids[len(ids) - len(t) :] == t
    span = ids[len(h) : len(ids) - len(t)]
    assert not set(span) & set(tok.added_tokens_decoder)
    assert tok.decode(span) == content.strip()


# ---------------------------------------------------------------- bank guard + override


def test_bank_fingerprint_tracks_item_content(tmp_path, monkeypatch):
    bank = tmp_path / "b.json"
    bank.write_text(json.dumps({"items": [{"id": "a", "options": ["x", "y"]}]}))
    monkeypatch.setenv("WSB_BANK_FILE_FAM", str(bank))
    monkeypatch.setattr(readplan, "plan", lambda f: [SimpleNamespace(id="a", layers=[1])])
    h1 = ti.bank_fingerprint("fam")
    monkeypatch.setattr(readplan, "plan", lambda f: [SimpleNamespace(id="a", layers=[2])])
    assert ti.bank_fingerprint("fam") == h1  # layers are not hashed (WSB_BANK_ROOT remaps)
    bank.write_text(json.dumps({"items": [{"id": "a", "options": ["x", "z"]}]}))
    assert ti.bank_fingerprint("fam") != h1  # an in-place option edit is a bank change
    monkeypatch.delenv("WSB_BANK_FILE_FAM")
    assert ti.bank_fingerprint("fam")  # no bank file: plan rows only, no crash


def test_subset_entry_checks_bank_sha_on_panel_entries_only(tmp_path, monkeypatch):
    monkeypatch.setattr(
        registry, "get", lambda f: SimpleNamespace(judge=SimpleNamespace(prompt_version="v2"))
    )
    monkeypatch.setattr(ti, "bank_fingerprint", lambda f: "now")
    ok = {"instrument": "v2", "ids": ["a"], "n_bank": 3, "judge_model": "m"}

    def frozen(entry):
        p = tmp_path / "ati.json"
        p.write_text(json.dumps({"_not_gated": {}, "fam": entry}))
        return p

    assert ti.subset("fam", frozen(ok)) == ["a"]  # plan-0014 entry: instrument only
    panel = {**ok, "gate": ti.GATE_VERSION, "bank_sha": "now"}
    assert ti.subset("fam", frozen(panel)) == ["a"]
    with pytest.raises(SystemExit, match="bank_sha"):
        ti.subset("fam", frozen({**panel, "bank_sha": "then"}))
    with pytest.raises(SystemExit, match="bank_sha"):
        ti.subset("fam", frozen({k: v for k, v in panel.items() if k != "bank_sha"}))


def test_bank_file_override_reaches_plan_and_judges(tmp_path, monkeypatch):
    from wsbench.evals.introspection import judge as intro
    from wsbench.evals.knowledge_cutoff import judge as kc
    from wsbench.evals.model_specific_directed_modulation import judge as dmo

    for fam, mod_load in (
        # the nocot items are appended after the bank file's items (plan 0018)
        ("knowledge_cutoff", lambda: [it for it in kc.load_items() if it["source"] == "cutoff"]),
        ("model_specific_directed_modulation", lambda: dmo.load_items()[1]),
        ("introspection", lambda: intro.load()["items"]),
    ):
        real = json.loads(registry.bank_path(fam).read_text())
        cut = {**real, "items": real["items"][:3]}
        p = tmp_path / f"{fam}.json"
        p.write_text(json.dumps(cut))
        monkeypatch.setenv(f"WSB_BANK_FILE_{fam.upper()}", str(p))
        assert registry.bank_path(fam) == p
        assert [it["id"] for it in mod_load()] == [it["id"] for it in cut["items"]]
        monkeypatch.delenv(f"WSB_BANK_FILE_{fam.upper()}")
    bad = tmp_path / "missing.json"
    monkeypatch.setenv("WSB_BANK_FILE_KNOWLEDGE_CUTOFF", str(bad))
    with pytest.raises(SystemExit, match="no such bank file"):
        registry.bank_path("knowledge_cutoff")


def test_bank_file_override_reaches_the_introspection_plan(tmp_path, monkeypatch):
    real = json.loads(registry.bank_path("introspection").read_text())
    heads = [it for it in real["items"] if it.get("headline")][:2]
    keep = {it["id"] for it in heads}
    p = tmp_path / "intro.json"
    p.write_text(json.dumps({**real, "items": heads}))
    monkeypatch.setenv("WSB_BANK_FILE_INTROSPECTION", str(p))
    scored = [s.id for s in readplan.plan("introspection") if ti.ati_scored(s)]
    assert set(scored) == keep


def test_panel_template_is_verbatim_in_the_baselines_readme():
    readme = (registry.REPO_ROOT / "evals" / "baselines" / "README.md").read_text()
    assert all(t in readme for t in ti.PANEL_TEMPLATES.values())


def test_decide_slots_moves_a_refused_family_to_sonnet(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "prompts.jsonl").write_text(
        "".join(
            json.dumps({"family": f, "id": i, "prefix": "p"}) + "\n" for f in "xy" for i in "abcde"
        )
    )
    rows = []
    for f in "xy":
        for i in "abcde":
            refused = f == "y" and i in "ab"  # y: 2/5 items refused (40%); x: none
            rows.append(
                {
                    "family": f,
                    "id": i,
                    "draw": 0,
                    "answer": "" if refused else "t",
                    "error": "refusal" if refused else "",
                    **({"refused": True} if refused else {}),
                }
            )
    ti.append_answers(out, "opus", rows)
    res = ti.decide_slots(out, draws=1)
    assert res["x"]["slot"] == "opus" and res["x"]["opus_refused_share"] == 0.0
    assert res["y"]["slot"] == "sonnet" and res["y"]["opus_refused_share"] == 0.4
    assert ti.claude_slots(out) == {"x": "opus", "y": "sonnet"}


def test_candidates_never_write_the_frozen_file(tmp_path, fams):
    with pytest.raises(ValueError, match="own dst"):
        ti.gate(tmp_path, dst=ti.FROZEN, candidates=True)


def test_union_refusal_share_pools_roots(tmp_path, fams):
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    for a in PANEL:
        _write(r1, a, "fam", {i: [F, F, F] for i in "abcd"})
    # a small round: 1 of its 2 items refused by opus (50% alone, 1/6 pooled) -> still gated
    for a in ("qwen", "astra", "argon"):
        _write(r2, a, "fam", {"e": [F, F, F], "f": [F, F, F]})
    _write(r2, "opus", "fam", {"e": [N, F, F], "f": [F, F, F]}, status={("e", 0): "refusal"})
    assert ti._union_refusal_share([r1, r2], "opus", "fam", list("abcdef"), 3) == 1 / 6


def test_stale_prompt_answers_are_ignored(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "prompts.jsonl").write_text(
        json.dumps({"family": "f", "id": "a", "prefix": "new"}) + "\n"
    )
    old = {
        "family": "f",
        "id": "a",
        "draw": 0,
        "answer": "x",
        "error": "",
        "prompt_sha": ti.prompt_sha(ti.panel_prompt({"prefix": "old"})),
    }
    msg = ti.append_answers(out, "astra", [old])
    assert "1 rows for another prompt version ignored" in msg
    assert len(ti.pending_requests(out, "astra", draws=1)) == 1


def test_variants_share_the_open_model_note_and_set_the_prompt():
    assert set(ti.PANEL_TEMPLATES) == {"free", "guess"}
    assert all(t.startswith(ti.OPEN_MODEL_NOTE) for t in ti.PANEL_TEMPLATES.values())
    row = {"prefix": "Fact: x is"}
    assert ti.panel_prompt(row) == ti.panel_prompt({**row, "variant": ti.DEFAULT_VARIANT})
    free, guess = (ti.panel_prompt({**row, "variant": v}) for v in ("free", "guess"))
    assert free.endswith("in this prompt?") and "single best guess" in guess
    assert ti.prompt_sha(free) != ti.prompt_sha(guess)


def test_gate_refuses_knowledge_cutoff_without_nocot(tmp_path, monkeypatch):
    monkeypatch.setenv("WSB_NO_NOCOT", "1")
    (tmp_path / "answers" / "qwen").mkdir(parents=True)  # panel layout
    with pytest.raises(SystemExit, match="WSB_NO_NOCOT"):
        ti.gate(tmp_path, dst=None, families=["knowledge_cutoff"])


def test_regex_multi_unit_families_count_any_unit_for_the_gate(tmp_path):
    rows = [
        {"id": "a", "pass": False, "any_hit": True},  # named the concept, missed the language form
        {"id": "b", "pass": False, "any_hit": False},
        {"id": "c", "pass": None, "any_hit": False},  # a missing layer stays undecided
    ]
    # plan 0054 item 10: the multilingual families gate on content_hit instead
    # (test_multilingual_gate_ignores_language_unit); typo_mt is out of ATI by design (plan 0033)
    for fam in ("basic_readout_mt",):
        p = tmp_path / fam / "results.json"
        p.parent.mkdir(parents=True)
        p.write_text(
            json.dumps(
                {
                    "family": fam,
                    "config": {},
                    "rows": rows,
                    "numbers": {"metric": "pass_rate", "value": 0.0},
                }
            )
        )
        assert ti.draw_verdicts(p) == {"a": True, "b": False, "c": None}


@pytest.mark.parametrize(
    "fam", ["multilingual", "multilingual_mt", "multilingual_multihop", "multilingual_typo"]
)
def test_multilingual_gate_ignores_language_unit(tmp_path, fam):
    """Plan 0033 item 10: the four multilingual families gate on content_hit, so a guess that
    names only the language ("Russian": the script shows it) is not solved."""
    rows = [
        {"id": "a", "pass": False, "any_hit": True, "content_hit": False},  # language only
        {"id": "b", "pass": False, "any_hit": True, "content_hit": True},  # the content
        {"id": "c", "pass": None, "any_hit": False, "content_hit": False},
    ]
    p = tmp_path / fam / "results.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(
            {
                "family": fam,
                "config": {},
                "rows": rows,
                "numbers": {"metric": "pass_rate", "value": 0.0},
            }
        )
    )
    assert ti.STRICTER_PASS_FIELD[fam] == "content_hit"
    assert ti.draw_verdicts(p) == {"a": False, "b": True, "c": None}


def test_ati_exclude_ids_absent_from_subset(tmp_path, fams, monkeypatch):
    """A survivor the hand audit marks obvious is dropped (with its reason) and, with <= 5
    items left, the family shows no ATI number (subset_entry: NotInScope)."""
    out = tmp_path / "o"
    _standard(out)  # ATI: a, c, e
    monkeypatch.setattr(ti, "ATI_EXCLUDE", {"fam": {"c": "obvious from the prompt"}})
    monkeypatch.setattr(ti, "ATI_MIN_RULE", frozenset({"fam"}))
    dst = tmp_path / "ati.json"
    e = ti.gate(out, dst=dst)["fam"]
    assert e["ids"] == ["a", "e"] and "c" not in e["ids"]
    assert e["ati_exclude"] == {"c": "obvious from the prompt"}
    assert e["ati_reportable"] is False and e["n_ati"] == 2
    monkeypatch.setattr(
        registry, "get", lambda f: SimpleNamespace(judge=SimpleNamespace(prompt_version="v1"))
    )
    with pytest.raises(ti.NotInScope, match="leads with its floor"):
        ti.subset_entry("fam", dst)


def test_ati_exclude_all_covers_new_survivors(tmp_path, fams, monkeypatch):
    """A family excluded by construction (ATI_EXCLUDE_ALL) drops every survivor, including ids
    the hand audit never listed (a new survivor after a re-gate)."""
    out = tmp_path / "o"
    _standard(out)  # ATI: a, c, e
    monkeypatch.setattr(ti, "ATI_EXCLUDE", {"fam": {"c": "obvious from the prompt"}})
    monkeypatch.setattr(ti, "ATI_EXCLUDE_ALL", {"fam": "text-invertible by construction"})
    monkeypatch.setattr(ti, "ATI_MIN_RULE", frozenset({"fam"}))
    e = ti.gate(out, dst=tmp_path / "ati.json")["fam"]
    assert e["ids"] == []
    assert e["ati_exclude"] == {
        "a": "text-invertible by construction",
        "c": "obvious from the prompt",
        "e": "text-invertible by construction",
    }
    assert e["ati_reportable"] is False


def test_multilingual_ati_exclusions_are_applied():
    """Plan 0033 §4: the 6 multihop, 1 mt and 15 typo panel-v1 survivors, and the 21 multilingual
    ids the R1-ATI re-gate admitted, are all obvious from the prompt; each carries a reason.
    Since the 2026-10-31 re-gate (R1-ATI) the frozen entries
    apply the exclusions: no audited id is in a subset, and every id the gate dropped as
    obvious is recorded in the entry's ``ati_exclude`` with its reason."""
    frozen = json.loads(ti.FROZEN.read_text(encoding="utf-8"))
    sizes = {"multilingual_multihop": 6, "multilingual_mt": 1, "multilingual_typo": 15}
    for fam in ("multilingual", *sizes):
        e = frozen[fam]
        assert all(len(why) > 20 for why in ti.ATI_EXCLUDE[fam].values())
        assert not set(e["ids"]) & set(ti.ATI_EXCLUDE[fam]), fam
        for i, why in e.get("ati_exclude", {}).items():
            assert why == ti.ATI_EXCLUDE.get(fam, {}).get(i, ti.ATI_EXCLUDE_ALL.get(fam)), (fam, i)
    for fam, n in sizes.items():
        assert len(ti.ATI_EXCLUDE[fam]) == n


# ---------------------------------------------------------------- reduced panel (decision R1-ATI)

LABEL = "qwen+opus (astra/argon unavailable: OpenRouter 403/no-choices 2026-10-31)"


def _two_readers(out: Path, fam: str = "fam") -> None:
    # only Qwen and the Claude slot answered (astra / argon unreachable)
    _write(
        out,
        "qwen",
        fam,
        {"a": [F, F, F], "b": [T, F, F], "c": [F, T, F], "d": [T, T, T], "e": [F, F, F]},
    )
    _write(
        out,
        "opus",
        fam,
        {"a": [T, T, T], "b": [F, F, F], "c": [F, T, F], "d": [F, N, F], "e": [F, F, F]},
    )


def test_full_panel_skips_a_family_missing_frontier_readers(tmp_path, fams):
    out = tmp_path / "o"
    _two_readers(out)
    assert ti.gate(out, dst=None, families=["fam"]) == {}


def test_reduced_panel_gates_on_qwen_and_the_claude_slot(tmp_path, fams):
    out = tmp_path / "o"
    _two_readers(out)
    dst = tmp_path / "ati.json"
    dst.write_text(json.dumps({"other": {"ids": ["z"]}, "_not_gated": {}}))
    e = ti.gate(out, dst=dst, families=["fam"], frontier=[], panel_label=LABEL)["fam"]
    # a, e: Qwen fails; b: Qwen solves, Opus fails every draw -> ATI; c: both solve ->
    # invertible; d: Qwen solves, Opus undecided -> unverified
    assert e["ids"] == ["a", "b", "e"]
    assert (e["n_ati"], e["n_invertible"], e["n_unverified"]) == (3, 1, 1)
    assert e["panel"] == LABEL and e["provisional"] is True
    assert e["readers"] == {"qwen": ti.PANEL["qwen"], "claude": "claude-opus-5-5"}
    assert e["status_order"] == ["qwen", "opus"]
    assert e["status"]["c"] == ["solved", "solved"]
    assert set(e["pass_at_3"]) == {"qwen", "opus"}
    assert e["gate"] == ti.GATE_VERSION and e["bank_sha"] == "sha-fam"
    written = json.loads(dst.read_text())
    assert written["other"] == {"ids": ["z"]} and written["fam"]["panel"] == LABEL


def test_reduced_panel_keeps_a_named_frontier_reader(tmp_path, fams):
    out = tmp_path / "o"
    _two_readers(out)
    # astra solves b: Qwen and a frontier reader both read it -> invertible
    _write(out, "astra", "fam", {i: [T, F, F] if i == "b" else [F, F, F] for i in "abcde"})
    e = ti.gate(out, dst=None, families=["fam"], frontier=["astra"], panel_label="qwen+opus+astra")
    assert e["fam"]["ids"] == ["a", "e"] and e["fam"]["status_order"] == ["qwen", "opus", "astra"]
    # how the hosted reader was reached (fixture rows carry no route / model)
    assert e["fam"]["reader_routes"] == {"astra": {"unknown": 15}}


def test_full_panel_entry_has_no_reduced_fields(tmp_path, fams):
    out = tmp_path / "o"
    _standard(out)
    e = ti.gate(out, dst=None, frontier=["argon", "astra"])["fam"]
    assert isinstance(e["panel"], dict) and "provisional" not in e and "status_order" not in e


@pytest.mark.parametrize(
    ("kw", "msg"),
    [
        ({"frontier": [], "families": ["fam"]}, "panel_label"),
        ({"frontier": [], "panel_label": LABEL}, "families"),
        ({"panel_label": LABEL, "families": ["fam"]}, "full panel has none"),
        ({"frontier": ["gpt-4o-mini"], "families": ["fam"], "panel_label": "x"}, "not frontier"),
        ({"frontier": ["astra", "astra"], "families": ["fam"], "panel_label": "x"}, "repeats"),
    ],
)
def test_reduced_panel_argument_checks(tmp_path, fams, kw, msg):
    out = tmp_path / "o"
    _two_readers(out)
    with pytest.raises(ValueError, match=msg):
        ti.gate(out, dst=None, **kw)


def test_subset_entry_accepts_a_provisional_entry(tmp_path, fams):
    out = tmp_path / "o"
    _two_readers(out)
    dst = tmp_path / "ati.json"
    ti.gate(out, dst=dst, families=["fam"], frontier=[], panel_label=LABEL)
    assert ti.subset("fam", dst) == ["a", "b", "e"]


def test_full_gate_carries_a_provisional_entry_over(tmp_path, fams, monkeypatch):
    monkeypatch.setattr(ti, "gated_families", lambda: ["fam", "wrong_bridge"])
    out = tmp_path / "o"
    _standard(out)
    _two_readers(out, "wrong_bridge")  # no astra / argon draws for this family
    dst = tmp_path / "ati.json"
    ti.gate(out, dst=dst, families=["wrong_bridge"], frontier=[], panel_label=LABEL)
    ti.gate(out, dst=dst)  # full gate: wrong_bridge is skipped (readers missing), not dropped
    written = json.loads(dst.read_text())
    assert written["wrong_bridge"]["provisional"] is True and written["fam"]["ids"] == [
        "a",
        "c",
        "e",
    ]


@pytest.mark.parametrize(
    ("value", "want"), [("none", []), ("astra", ["astra"]), ("astra,argon", ["astra", "argon"])]
)
def test_cli_frontier_parsing(value, want):
    from wsbench.cli import TextInversion

    t = TextInversion()
    t.stage, t.frontier, t.panel_label = "gate", value, "x"
    t.finalize()
    assert t.frontier == want and t.panel_label == "x"
    t = TextInversion()
    t.stage = "gate"
    t.finalize()
    assert t.frontier is None and t.panel_label == ""


# ---------------------------------------------------------------- items a missing reader decides


def _reduced(status: dict[str, list[str]], order=("qwen", "opus", "astra")) -> dict:
    return {"status_order": list(order), "status": status}


@pytest.mark.parametrize(
    ("st", "decisive"),
    [
        (["solved", "failed", "failed"], True),  # argon solving it takes it out
        (["undecided", "failed", "failed"], True),  # argon solving / undecided takes it out
        (["failed", "failed", "failed"], False),  # Qwen failed: ATI whatever argon answers
        (["solved", "solved", "failed"], False),  # a present frontier reader solved it
        (["solved", "undecided", "failed"], False),  # unverified or invertible, never ATI
        (["undecided", "failed", "undecided"], False),
    ],
)
def test_decisive_items_rule(st, decisive):
    assert ti.decisive_items(_reduced({"x": st})) == (["x"] if decisive else [])


def test_decisive_items_two_missing_readers_and_full_panel():
    # qwen+opus panel (astra and argon missing): Qwen solved, Opus failed -> either can move it
    e = _reduced({"x": ["solved", "failed"], "y": ["failed", "solved"]}, order=("qwen", "opus"))
    assert ti.missing_readers(e) == ["astra", "argon"] and ti.decisive_items(e) == ["x"]
    assert ti.missing_readers({"status": {}}) == [] and ti.decisive_items({"status": {}}) == []


def test_frozen_argon_decisive_counts_match_the_statuses():
    """Every entry recording ``argon_decisive_items`` agrees with its own frozen statuses, and is
    provisional exactly when that count is non-zero; a reduced-panel entry without the count
    (fresh from a reduced gate, before ``scripts/ati_argon_decisive.py``) stays provisional
    (decision R1-ATI argon)."""
    frozen = json.loads(ti.FROZEN.read_text(encoding="utf-8"))
    recorded = {
        f: e
        for f, e in frozen.items()
        if not f.startswith("_") and isinstance(e, dict) and "status_order" in e
    }
    # decision R1-ATI gemini (2026-11-01): argon answers via Gemini WIF, so every entry is
    # gated on the full four-reader panel again and no reduced-panel entry is left
    assert not recorded, f"reduced-panel entries left: {sorted(recorded)}"
    for f, e in frozen.items():
        if not f.startswith("_") and isinstance(e, dict) and e.get("gate") == ti.GATE_VERSION:
            assert set(e["panel"]) == {"qwen", "claude", "astra", "argon"}
            assert "provisional" not in e and "argon_decisive_items" not in e
    for fam, e in recorded.items():
        if "argon_decisive_items" not in e:
            assert e.get("provisional") is True, fam
            continue
        assert ti.missing_readers(e) == ["argon"], fam
        assert len(ti.decisive_items(e)) == e["argon_decisive_items"], fam
        assert bool(e.get("provisional")) == (e["argon_decisive_items"] > 0), fam
        assert "argon unavailable" in e["panel"], fam


def test_full_gate_carries_a_cleared_reduced_entry_over(tmp_path, fams, monkeypatch):
    monkeypatch.setattr(ti, "gated_families", lambda: ["fam", "wrong_bridge"])
    out = tmp_path / "o"
    _standard(out)
    _two_readers(out, "wrong_bridge")
    dst = tmp_path / "ati.json"
    ti.gate(out, dst=dst, families=["wrong_bridge"], frontier=[], panel_label=LABEL)
    d = json.loads(dst.read_text())
    del d["wrong_bridge"]["provisional"]  # cleared: no item the missing readers could move
    dst.write_text(json.dumps(d))
    ti.gate(out, dst=dst)  # full gate: wrong_bridge is skipped, its cleared entry kept
    written = json.loads(dst.read_text())
    wb = written["wrong_bridge"]
    assert wb["panel"] == LABEL and "provisional" not in wb

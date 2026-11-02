"""scripts/summary_mode_dev.py: digest keying per family, per-item denominators, and the
passivity auditor's prompt (statement + evidence span + the whole readout sample)."""

import importlib.util
import json
from pathlib import Path

from summary_fakes import FakeLLM, first_lines_digest, summary_args

from wsbench import registry
from wsbench.results import write_results

REPO = Path(__file__).resolve().parents[1]
EX = REPO / "examples/readouts"
SCRIPT = REPO / "scripts/summary_mode_dev.py"
_spec = importlib.util.spec_from_file_location("summary_mode_dev", SCRIPT)
dev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dev)  # type: ignore[union-attr]

# one answer every judge schema of the families below can read (unknown keys are ignored)
ANSWER = {
    "choice": 1,
    "quote": "",
    "evidence": "",
    "basis": "absent",
    "form": "none",
    "domain_overlap": [],
    "verdicts": [],
    "rationale": "",
    "picks": [],
}


def _run(fam: str, out: Path, monkeypatch, digest_fn=None, path=None, **kw) -> dict:
    spec = registry.FAMILIES[fam]
    FakeLLM.install(monkeypatch, lambda s, u, sc: dict(ANSWER), digest=digest_fn)
    path = path or EX / f"{fam}.jsonl"
    r = spec.run(summary_args(path, out, spec.judge.prompt_version, **kw))
    write_results(out, r)
    return r.to_json()


def test_audit_prompt_carries_statement_span_and_whole_sample():
    row = {
        "summary_statements": [
            {"statement": "names boxing", "support": "few", "evidence": "Boxing ring"},
            {"statement": "a token", "support": "one", "evidence": "glove"},
            {"statement": "lost", "support": "one", "evidence": "nowhere"},
        ],
        "summary_evidence": ["the boxing ring at dawn", "punch | glove | ring"],
    }
    (prompt,), sizes = dev.audit_prompts([row])
    system, user = prompt
    assert system == dev.AUDIT_SYSTEM and sizes == [3]
    assert '[0] statement: names boxing\n    evidence span: "Boxing ring"\n' in user
    assert '    readout sample: "the boxing ring at dawn"' in user
    assert 'readout sample: "punch | glove | ring"' in user
    assert "readout sample: (not found)" in user
    assert dev.evidence_sample("glove", row["summary_evidence"]) == "punch | glove | ring"


def test_digest_rows_key_by_real_item_and_dedupe():
    s = {"summary_state": "summarized"}
    moral = [{"id": "d1", "side": "yes", **s}, {"id": "d1", "side": "no", **s}]
    assert list(dev.digest_rows("moral_rationale", moral)) == ["d1"]
    intro = [
        {"id": "u1", "readout_of": "r1", **s},
        {"id": "x1", "readout_of": "r1", "excluded_from_rate": True, **s},
        {"id": "u2", "readout_of": "r2", **s},
    ]
    assert list(dev.digest_rows("introspection", intro)) == ["r1", "r2"]
    assert list(dev.digest_rows("directed_modulation", [{"item": "a", **s}])) == ["a"]


def test_rates_divide_by_digested_items_not_rows(tmp_path, monkeypatch, real_families):
    # jailbreak: an unsummarized item has NO row, so len(rows) would under-count the denominator
    def dig(user: str):
        return None if "jailbreak attempt" in user else first_lines_digest(user)

    res = _run(
        "jailbreak_recognition",
        tmp_path / "jb",
        monkeypatch,
        digest_fn=dig,
        items=["as-wildchat-20f6d664", "as-wildchat-574b06eb"],
        allow_missing=True,
    )
    assert len(res["rows"]) == 1
    rec = dev.audit_family("x", "jailbreak_recognition", res, [EX], False)
    assert rec["n"] == 2 and rec["unsummarized_rate"] == 0.5


def test_moral_sides_and_introspection_units_are_one_digest_each(
    tmp_path, monkeypatch, real_families
):
    # bank v1 (plan 0046: torture_bomb is deliberative there; bank v2 re-keyed it committed)
    monkeypatch.setenv("WSB_BANK_FILE_MORAL_RATIONALE", "evals/moral_rationale/items.json")
    tb = "ec-torture_bomb-chat_tf"  # a deliberative item: judged once per side
    extra = [
        {"id": tb, "layer": L, "pos": p, "samples": [f"Torture could save many lives {L} {p}."]}
        for L in (20, 36)
        for p in (1, 2)
    ]
    path = tmp_path / "moral.jsonl"
    path.write_text(
        (EX / "moral_rationale.jsonl").read_text() + "".join(json.dumps(r) + "\n" for r in extra)
    )
    ids = ["ec-ransom-chat_tf", "ec-ransom-chat_yn", tb]
    res = _run("moral_rationale", tmp_path / "m", monkeypatch, path=path, items=ids)
    n_items = len({r["id"] for r in res["rows"]})
    assert len(res["rows"]) > n_items  # deliberative items: one row per side
    rec = dev.audit_family("x", "moral_rationale", res, [EX], False)
    assert rec["n"] == n_items and rec["coverage"] is not None
    res = _run("introspection", tmp_path / "i", monkeypatch, allow_missing=True)
    assert len(res["rows"]) > 3
    rec = dev.audit_family("x", "introspection", res, [EX], False)
    assert rec["n"] == 3  # 3 readouts digested, however many units read them
    file_ids = {
        json.loads(x)["id"] for x in (EX / "introspection.jsonl").read_text().split("\n") if x
    }
    keys = set(dev.digest_rows("introspection", res["rows"]))
    assert keys == file_ids  # cross / control units map to their readout's cells


def test_dm_coverage_uses_item_key_and_passivity_sees_samples(tmp_path, monkeypatch, real_families):
    ids = ["dm-pair-00-pos", "dm-pair-00-neg", "dm-secret-00"]
    roots = tmp_path / "ro"
    roots.mkdir()
    rows = [json.loads(x) for x in (EX / "directed_modulation.jsonl").read_text().splitlines()]
    for r in rows:  # recurring words (>= 3 samples over >= 2 layers), so coverage is defined
        r["samples"] = [*r["samples"], f"clavicle harbour {r['pos']}", "clavicle harbour"]
    path = roots / "directed_modulation.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    res = _run("directed_modulation", tmp_path / "d", monkeypatch, path=path, items=ids)
    rec = dev.audit_family("x", "directed_modulation", res, [roots], False)
    assert rec["coverage"] is not None  # rows are keyed `item`, not `id`
    seen: list[str] = []

    def auditor(system: str, user: str, schema: dict) -> dict:
        assert system == dev.AUDIT_SYSTEM
        seen.append(user)
        return {"violations": [{"index": 0, "kind": "interprets"}]}

    fake = FakeLLM.install(monkeypatch, auditor)
    digests = dev.digest_rows("directed_modulation", res["rows"])
    bad, total = dev.passivity(list(digests.values()))
    assert fake.n("passivity") == len(digests) == bad
    assert total == sum(len(r["summary_statements"]) for r in digests.values())
    for user, r in zip(seen, digests.values(), strict=True):
        for ev in r["summary_evidence"]:
            assert f"readout sample: {json.dumps(ev, ensure_ascii=False)}" in user

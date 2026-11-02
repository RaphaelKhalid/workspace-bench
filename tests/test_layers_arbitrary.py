"""Plan 0032 §2.1 (Camila: "all banks should have the option to run an arbitrary combination of
layers, we will have some methods that are capable of reading ALL layers, so we should make sure
that the infra supports this easily"): every family judges any layer set, summary and native."""

import json
import sys
from pathlib import Path

import pytest
from conftest import native_args

from wsbench import digest, llm, mcjudge, readplan, registry, runner
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.results import read_results

REPO = Path(__file__).resolve().parents[1]
EX = REPO / "examples/readouts"
CELLS_ALL = {"arithmetic_intermediates", "chain_intermediates"}


def _families() -> list[str]:
    registry.load_all()
    sup = registry.superseded()
    return sorted(f for f in registry.FAMILIES if f not in sup)


def _toy(family: str) -> Path | None:
    path = EX / f"{family}.jsonl"
    if not path.exists():
        alt = EX / f"{family.removesuffix('_alt')}.jsonl"
        path = alt if alt.exists() else path
    return path if path.exists() else None


def _relayer(src: Path, dst: Path, layers: list[int]) -> Path:
    rows = [json.loads(x) for x in src.read_text(encoding="utf-8").splitlines() if x.strip()]
    first = sorted({r["layer"] for r in rows})[0]
    out = [{**r, "layer": L} for r in rows if r["layer"] == first for L in layers]
    dst.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    return dst


@pytest.fixture
def fake(monkeypatch):
    sys.path.insert(0, str(REPO / "tests"))
    from test_summary_mode_compare import _frags, _RandomLLM

    def install(path: Path):
        f = _RandomLLM(0, _frags(path))
        monkeypatch.setattr(llm, "stream_json", f.stream_json)
        monkeypatch.setattr(llm, "stream_text", f.stream_text)
        monkeypatch.setattr(llm, "count_tokens", f.count_tokens)
        monkeypatch.setattr(llm, "preflight", lambda model, reasoning: None)
        mcjudge._PREFLIGHTED.clear()
        return f

    return install


def _run(family: str, path: Path, tmp_path: Path, mode: str, layers):
    spec = registry.FAMILIES[family]
    extra = {"aggregate": mode}
    if mode == "native" and family in CELLS_ALL:
        extra["cells"] = "all"
    args = native_args(
        readouts=path,
        out=tmp_path / mode / family,
        judge=resolve(spec.judge),
        layers=layers,
        items=None,
        limit=0,
        allow_missing=True,
        concurrency=1,
        rpm=1e9,
        dry_run=False,
        aux_models=spec.judge.aux_models,
        extra=extra,
    )
    r = spec.run(args)
    runner.finalize_reads(args, r)
    return r


@pytest.mark.parametrize("family", _families())
@pytest.mark.parametrize("layers", [[3, 17, 44], [44]])
def test_every_family_accepts_arbitrary_layers(family, layers, tmp_path, fake, real_families):
    src = _toy(family)
    if src is None:
        pytest.skip(f"{family}: no toy readouts")
    path = _relayer(src, tmp_path / f"{family}.jsonl", layers)
    fake(path)
    if family == "jlens_concept_pr" and layers != [44]:
        # its reference is the J-lens top-10 at the same layer; layers without a reference file
        # are refused by name (the one family that cannot judge a layer it has no reference for)
        with pytest.raises(SystemExit):
            _run(family, path, tmp_path, "native", layers)
        return
    modes = ["native"] if family in digest.NATIVE_ONLY else ["summary", "native"]
    for mode in modes:
        try:
            r = _run(family, path, tmp_path, mode, layers)
        except llm.JudgeConfigError:  # every call of a tiny family failed (the fake's 8%)
            continue
        assert r.config["layers_judged"] == layers, (family, mode, r.config["layers_judged"])


def test_layers_variant_is_complete(tmp_path):
    """An explicit layers= list is a defined variant, not a partial run (plan 0032 §2.1.7)."""
    args = native_args(
        readouts=tmp_path / "r.jsonl",
        out=tmp_path,
        judge=resolve(JudgeConfig()),
        layers=[44],
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=False,
    )
    assert mcjudge.is_subset(args) is False


def test_plan_layers_all_is_every_model_layer(monkeypatch):
    rows = readplan.plan("poetry", layers="all")
    assert all(s.layers == list(range(64)) for s in rows)
    monkeypatch.setenv(readplan.LAYERS_ENV, "all")
    assert [s.row() for s in readplan.plan("poetry")] == [s.row() for s in rows]
    monkeypatch.setenv(readplan.LAYERS_ENV, "20,44")
    assert readplan.plan("poetry")[0].layers == [20, 44]
    monkeypatch.delenv(readplan.LAYERS_ENV)
    assert readplan.plan("poetry")[0].layers == readplan.GRID
    assert readplan.plan("arithmetic_intermediates", layers=[44])[0].lite_layers is None


def test_every_family_reads_grid(real_families):
    for name in readplan.families():
        want = [*readplan.GRID, 63] if name == "agentic_misalignment" else readplan.GRID
        assert all(s.layers == want for s in readplan.plan(name)), name


def test_single_layer_digest_sees_only_that_layer(tmp_path, fake, monkeypatch):
    src = _toy("moral_rationale")
    path = _relayer(src, tmp_path / "moral_rationale.jsonl", readplan.GRID)
    seen: list[str] = []

    def stream_json(prompts, *, schema, on_result, **kw):
        for i, (_s, user) in enumerate(prompts):
            seen.append(user)
            on_result(i, None)

    fake(path)
    monkeypatch.setattr(llm, "stream_json", stream_json)
    _run("moral_rationale", path, tmp_path, "summary", [44])
    digests = [u for u in seen if u.startswith("READOUTS:")]
    assert digests and all("[L44 " in u and "[L20 " not in u for u in digests)


def _cli(tmp_path: Path, *extra: str) -> int:
    from wsbench.cli import main

    return main(
        [
            "run",
            "families=multilingual_mt",
            f"readouts_root={tmp_path / 'r'}",
            "opts=aggregate=native",
            "allow_missing=True",
            *extra,
        ]
    )


def test_layers_each_writes_one_subrun_per_layer(tmp_path, real_families):
    (tmp_path / "r").mkdir()
    _relayer(EX / "multilingual_mt.jsonl", tmp_path / "r" / "multilingual_mt.jsonl", [20, 44])
    assert _cli(tmp_path, f"out={tmp_path / 'each'}", "layers=each") == 0
    fam = tmp_path / "each" / "multilingual_mt"
    assert sorted(p.name for p in fam.iterdir()) == ["L20", "L44", "all"]
    assert read_results(fam / "L44").config["layers_judged"] == [44]
    assert read_results(fam / "all").config["layers_judged"] == [20, 44]


def test_layers_each_equals_loop(tmp_path, real_families):
    (tmp_path / "r").mkdir()
    _relayer(EX / "multilingual_mt.jsonl", tmp_path / "r" / "multilingual_mt.jsonl", [20, 44])
    assert _cli(tmp_path, f"out={tmp_path / 'each'}", "layers=each") == 0
    for tag, lay in (("all", None), ("L20", "20"), ("L44", "44")):
        out = tmp_path / f"loop-{tag}"
        assert _cli(tmp_path, f"out={out}", *([f"layers={lay}"] if lay else [])) == 0
        a = json.loads((tmp_path / "each" / "multilingual_mt" / tag / "results.json").read_text())
        b = json.loads((out / "multilingual_mt" / "results.json").read_text())
        assert a == b, tag

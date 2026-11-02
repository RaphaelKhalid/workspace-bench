"""The HallucinationBench index reported in WorkspaceBench (plan 0040 W2)."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

from wsbench import hbindex
from wsbench.cli import main
from wsbench.results import FamilyResult, macro, write_results

REPO = Path(__file__).resolve().parents[1]


def _vendor_module():
    spec = importlib.util.spec_from_file_location(
        "vendor_hb_index", REPO / "scripts/vendor_hb_index.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cell(v: float, lo: float, hi: float) -> dict:
    return {"v": v, "ci": [lo, hi]}


# hand-written fixture: m-full has `full` at L20 / L24 (0.10, 0.20 -> mean 0.15) and nothing at
# L28; m-matched (a J-lens-shaped row) has only `matched` (0.04, 0.02 -> mean 0.03)
FIXTURE = {
    "hb_repo": "github.com/camila-blank/hallucination-bench",
    "hb_sha": "0123456789abcdef0123456789abcdef01234567",
    "version": "hindex-v6",
    "rows": [
        {"method": "m-full", "layer": 20, "full": _cell(0.10, 0.08, 0.12),
         "matched": _cell(0.09, 0.07, 0.11)},
        {"method": "m-full", "layer": 24, "full": _cell(0.20, 0.18, 0.22),
         "matched": _cell(0.19, 0.17, 0.21)},
        {"method": "m-matched", "layer": 20, "matched": _cell(0.04, 0.03, 0.05)},
        {"method": "m-matched", "layer": 24, "matched": _cell(0.02, 0.01, 0.03)},
    ],
}  # fmt: skip


def test_vendored_index_schema_and_version():
    idx = hbindex.load()
    assert idx["version"] == "hindex-v6" == hbindex.VERSION
    assert re.fullmatch(r"[0-9a-f]{7,40}", idx["hb_sha"])
    assert idx["hb_repo"] == "github.com/camila-blank/hallucination-bench"
    assert idx["families"] == ["main", "agentic_misalignment", "sibling", "story", "overrefusal"]
    assert idx["weights"]["family"] == {
        "main": 9.0,
        "agentic_misalignment": 3.0,
        "sibling": 2.0,
        "story": 1.0,
        "overrefusal": 1.0,
    }
    assert "sources" not in idx and "safety" not in idx
    assert "/workspace" not in json.dumps(idx)  # no dev-box paths
    assert idx["rows"]
    for r in idx["rows"]:
        assert isinstance(r["method"], str) and isinstance(r["layer"], int)
        assert set(r) <= {"method", "layer", "full", "matched", "families"}
        for cell in r["families"].values():
            assert set(cell) <= {"v", "ci", "n", "n_items"}
    # the vendored rows are exactly the mapped methods, at HB's 11 layers
    methods = set(hbindex.methods()["methods"].values())
    assert {r["method"] for r in idx["rows"]} == methods
    for m in methods:
        assert sorted(r["layer"] for r in idx["rows"] if r["method"] == m) == list(range(20, 61, 4))


def test_vendored_numbers_match_hb_results_doc():
    # HB docs/results/0022_index_v6.md: s3d-rl600 L44 full 13.2 [12.0, 14.4]; jlens has no full
    got = hbindex.lookup("s3d-rl600", [44])
    assert got is not None
    (row,) = got["rows"]
    assert row["kind"] == "full"
    assert (round(100 * row["value"], 1), [round(100 * x, 1) for x in row["ci"]]) == (
        13.2,
        [12.0, 14.4],
    )
    jl = hbindex.lookup("jlens", [44])
    assert jl is not None and jl["rows"][0]["kind"] == "matched (no sibling)"


def test_headline_full_else_matched():
    full, jl = FIXTURE["rows"][0], FIXTURE["rows"][2]
    assert hbindex.headline(full) == ("full", 0.10, (0.08, 0.12))
    assert hbindex.headline(jl) == ("matched (no sibling)", 0.04, (0.03, 0.05))
    with pytest.raises(ValueError):
        hbindex.headline({"method": "x", "layer": 20})


def test_lookup_single_and_multi_layer():
    one = hbindex.lookup("m-full", [24], index=FIXTURE)
    assert one is not None and "layer_mean" not in one
    assert one["rows"] == [{"layer": 24, "kind": "full", "value": 0.20, "ci": [0.18, 0.22]}]
    many = hbindex.lookup("m-full", [20, 24, 28], index=FIXTURE)
    assert many is not None
    assert [r["layer"] for r in many["rows"]] == [20, 24] and many["missing_layers"] == [28]
    (mean,) = many["layer_mean"]
    assert mean["kind"] == "full" and mean["n_layers"] == 2
    assert mean["value"] == pytest.approx(0.15)  # (0.10 + 0.20) / 2
    jl = hbindex.lookup("m-matched", [20, 24], index=FIXTURE)
    assert jl is not None
    assert jl["layer_mean"] == [
        {"kind": "matched (no sibling)", "value": pytest.approx(0.03), "n_layers": 2}
    ]
    text, payload = hbindex.report_block("m-full", [20, 24, 28], index=FIXTURE)
    assert "- L20: full 10.0% [8.0, 12.0]" in text
    assert "- layer mean (2 layers, full, unweighted, no CI): 15.0%" in text
    assert "not measured on HallucinationBench at L28" in text
    assert payload["measured"] is True and payload["in_macro"] is False


def test_unknown_method_reports_not_measured():
    assert hbindex.lookup("nope", [20], index=FIXTURE) is None
    assert hbindex.lookup("m-full", [28], index=FIXTURE) is None  # an unmeasured layer
    assert hbindex.missing_reason("nope", [20], index=FIXTURE).startswith(hbindex.NOT_MEASURED)
    assert "the run judged 28" in hbindex.missing_reason("m-full", [28], index=FIXTURE)
    text, payload = hbindex.report_block("nope", [20], index=FIXTURE)
    assert hbindex.NOT_MEASURED in text and payload["measured"] is False
    # an arm listed as not measured (mlnla-rl2-2000) is never aliased to an HB NLA method
    method, why = hbindex.resolve_method(run_json={"readouts_root": "/x/readouts/mlnla-rl2-2000"})
    assert method is None and why.startswith("mlnla-rl2-2000: " + hbindex.NOT_MEASURED)
    assert hbindex.resolve_method(run_json={"readouts_root": "/x/readouts/other-arm"}) == (None, "")


def test_resolve_method_order():
    rj = {"hb_method": "jlens", "readouts_root": "/x/s3d-rl600"}
    assert hbindex.resolve_method(arg="s3d-rl600", run_json=rj) == ("s3d-rl600", "hb_method=")
    assert hbindex.resolve_method(run_json=rj) == ("jlens", "run.json")
    rj.pop("hb_method")
    assert hbindex.resolve_method(run_json=rj) == ("s3d-rl600", "methods.json[s3d-rl600]")


def _res(family: str, value: float, layers: list[int]) -> FamilyResult:
    return FamilyResult(
        family=family,
        metric="pass_rate",
        value=value,
        ci95=(value - 0.1, value + 0.1),
        n_items=10,
        higher_is_better=True,
        chance=None,
        chance_label=None,
        complete=True,
        pinned_instrument=True,
        config={"judge_model": "claude-opus-5-5", "prompt_version": "v1", "layers_judged": layers},
        counts={},
    )


def test_report_appends_hb_block(tmp_path, capsys):
    base, hb = tmp_path / "base", tmp_path / "hb"
    for d in (base, hb):
        write_results(d / "association", _res("association", 0.5, [44]))
        write_results(d / "poetry", _res("poetry", 0.3, [44]))
    (hb / "run.json").write_text(json.dumps({"hb_method": "s3d-rl600"}))
    assert main(["report", f"dir={base}", "floors=False"]) == 0
    assert main(["report", f"dir={hb}", "floors=False"]) == 0
    capsys.readouterr()
    plain, with_hb = (base / "summary.md").read_text(), (hb / "summary.md").read_text()
    assert "HallucinationBench" not in plain  # no method resolves: no block
    block = "HallucinationBench index (hindex-v6 @ b1043b4, lower is better): s3d-rl600 full "
    assert with_hb.startswith(plain) and block in with_hb
    assert with_hb.rstrip().endswith("at L44")
    # the macro value is unchanged: the HB index is a separate number
    assert main(["report", f"dir={hb}", "floors=False", "json=True"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert main(["report", f"dir={base}", "floors=False", "json=True"]) == 0
    assert out["macro"] == json.loads(capsys.readouterr().out)["macro"]
    results = [_res("association", 0.5, [44]), _res("poetry", 0.3, [44])]
    assert out["macro"]["value"] == macro(results)["value"] == pytest.approx(0.4)
    hbj = out["hallucinationbench"]
    assert hbj["method"] == "s3d-rl600" and hbj["measured"] is True and hbj["in_macro"] is False
    assert hbj["rows"][0]["layer"] == 44 and hbj["rows"][0]["kind"] == "full"
    # the argument wins over run.json
    assert main(["report", f"dir={hb}", "floors=False", "hb_method=jlens"]) == 0
    assert "jlens matched (no sibling) 2.3% [1.8, 2.9] at L44" in (hb / "summary.md").read_text()


def test_run_stores_hb_method_in_run_json(tmp_path):
    from types import SimpleNamespace

    from wsbench import runner

    args = SimpleNamespace(judge_model=None, opt=[], hb_method="s3d-rl600")
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    m = runner.run_manifest(
        [], started=now, finished=now, args=args, out=tmp_path, readouts_root=tmp_path
    )
    assert m["hb_method"] == "s3d-rl600"
    args.hb_method = ""
    m = runner.run_manifest(
        [], started=now, finished=now, args=args, out=tmp_path, readouts_root=tmp_path
    )
    assert "hb_method" not in m


def test_vendor_script_refuses_sha_or_version_mismatch(tmp_path):
    vend = _vendor_module()
    methods = tmp_path / "methods.json"
    methods.write_text(json.dumps({"methods": {"s3d-rl600": "m-full"}, "not_measured": {}}))
    src = {
        **{k: v for k, v in FIXTURE.items() if k != "hb_sha"},
        "git_sha": FIXTURE["hb_sha"],
        "sources": {"main": ["/workspace/dev-box/path"]},
        "weights": {"family": {"main": 9.0, "sibling": 2.0}},
        "notes": {"m-full.main": "kept", "other": "dropped", "hindex-v6": "kept"},
    }
    p = tmp_path / "index.json"
    p.write_text(json.dumps(src))
    out = vend.vendor(p, "0123456", methods)
    assert out["hb_sha"] == FIXTURE["hb_sha"] and out["families"] == ["main", "sibling"]
    assert {r["method"] for r in out["rows"]} == {"m-full"} and "sources" not in out
    assert set(out["notes"]) == {"m-full.main", "hindex-v6"}
    with pytest.raises(ValueError, match="is not HB_SHA"):
        vend.vendor(p, "fedcba9", methods)
    p.write_text(json.dumps({**src, "version": "hindex-v5"}))
    with pytest.raises(ValueError, match="is not hindex-v6"):
        vend.vendor(p, "0123456", methods)
    assert vend.main([f"SRC={p}", "HB_SHA=0123456", f"DST={tmp_path / 'o.json'}"]) == 2
    assert not (tmp_path / "o.json").exists()


def test_methods_json_keys_are_campaign_arms():
    m = hbindex.methods()
    keys = set(m["methods"]) | set(m["not_measured"])
    assert keys == set(hbindex.CAMPAIGN_ARMS)
    assert not set(m["methods"]) & set(m["not_measured"])
    present = {r["method"] for r in hbindex.load()["rows"]}
    assert set(m["methods"].values()) <= present
    # W2.2: mlnla-rl2-2000 is never assumed to equal an HB NLA method
    assert "mlnla-rl2-2000" in m["not_measured"]


def test_final_olens_arm_is_mapped_and_full():
    # plan 0057: the campaign's final O-lens arm (HB plan 0024)
    m = hbindex.methods()
    assert m["methods"]["final-olens-rl600-x4"] == "final-olens-rl600-x4"
    got = hbindex.lookup("final-olens-rl600-x4", list(range(20, 61, 4)))
    assert got is not None and not got["missing_layers"]
    assert {r["kind"] for r in got["rows"]} == {"full"}
    (l44,) = [r for r in got["rows"] if r["layer"] == 44]
    assert (round(100 * l44["value"], 1), [round(100 * x, 1) for x in l44["ci"]]) == (
        16.6,
        [15.1, 18.2],
    )

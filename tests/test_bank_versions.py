"""Plan 0032 §2.12 (D9): one versioned-bank mechanism, ``registry.bank_path`` honouring
``EvalSpec.bank``; every reader goes through it."""

import ast
import dataclasses
import json
import re
from pathlib import Path

from wsbench import registry
from wsbench.baselines import text_inversion as ti

SRC = Path(__file__).resolve().parents[1] / "src" / "wsbench"
# where an "items.json" literal is the registered default itself, or an adapted bank's manifest
ALLOWED_LITERALS = {
    "registry.py",
    "basic/family.py",  # bank_family's default path
    "multitoken/family.py",  # mt_family's default path
    "readplan.py",  # jlens_concept_pr's adapted rollout ids (bank_dir/items.json)
    "nocot.py",
}


def test_bank_path_honours_evalspec_bank(tmp_path, monkeypatch, real_families):
    spec = real_families["poetry"]
    v2 = registry.REPO_ROOT / "evals/poetry/items_v2.json"
    monkeypatch.setitem(registry.FAMILIES, "poetry", dataclasses.replace(spec, bank=v2))
    assert registry.bank_path("poetry") == v2
    assert (
        registry.bank_path("association") == registry.REPO_ROOT / real_families["association"].bank
    )


def test_env_overrides_still_win(tmp_path, monkeypatch, real_families):
    f = tmp_path / "bank.json"
    f.write_text(json.dumps({"items": []}))
    monkeypatch.setenv("WSB_BANK_FILE_POETRY", str(f))
    assert registry.bank_path("poetry") == f
    monkeypatch.delenv("WSB_BANK_FILE_POETRY")
    root = tmp_path / "adapted"
    root.mkdir()
    (root / "poetry.json").write_text("[]")
    monkeypatch.setenv("WSB_BANK_ROOT", str(root))
    assert registry.bank_path("poetry") == root / "poetry.json"


def test_no_hardcoded_items_json():
    bad = []
    for f in SRC.rglob("*.py"):
        rel = str(f.relative_to(SRC))
        if rel in ALLOWED_LITERALS or (rel.startswith("evals/") and rel.endswith("__init__.py")):
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.endswith("items.json")
            ):
                bad.append(f"{rel}:{node.lineno}:{node.value}")
    assert bad == []


def test_bank_file_naming_rule(real_families):
    pat = re.compile(r"items(_v\d+)?\.json|manifest\.json")
    for name, spec in real_families.items():
        assert pat.fullmatch(Path(spec.bank).name), (name, spec.bank)


def test_fingerprint_hashes_the_registered_bank(real_families, monkeypatch, tmp_path):
    before = ti.bank_fingerprint("poetry")
    raw = json.loads(registry.bank_path("poetry").read_text())
    raw["items"][0]["prompt"] = raw["items"][0]["prompt"] + " (v2)"
    v2 = tmp_path / "items_v2.json"
    v2.write_text(json.dumps(raw))
    spec = real_families["poetry"]
    monkeypatch.setitem(registry.FAMILIES, "poetry", dataclasses.replace(spec, bank=v2))
    assert ti.bank_fingerprint("poetry") != before

"""Plan 0032 §2.3 (Camila: "make sure that we have gotten rid of the individual jlens summarizer
step, it should be replaced with the more general sumamrizer we apply to all methods now")."""

import ast
import contextlib
import importlib.util
import json
from pathlib import Path

import pytest
from conftest import native_args

from wsbench import llm, registry
from wsbench.judge_config import resolve

SRC = Path(__file__).resolve().parents[1] / "src" / "wsbench"
EX = Path(__file__).resolve().parents[1] / "examples/readouts"


def test_no_module_imports_interp():
    assert importlib.util.find_spec("wsbench.summarizer") is None
    bad = []
    for f in SRC.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "wsbench.summarizer":
                bad.append(str(f))
            if isinstance(node, ast.Name) and node.id.startswith("INTERP_"):
                bad.append(f"{f}:{node.id}")
            if isinstance(node, ast.Attribute) and node.attr == "summarize":
                bad.append(f"{f}:.summarize")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.startswith("summ:")
            ):
                bad.append(f"{f}:summ: key")
    assert bad == []


TOKEN_FAMILIES = [
    "conjunctive_association",
    "jailbreak_recognition",
    "moral_rationale",
    "relational_multihop",
    "role_bound_association",
    "user_modeling",
    "multi_concept_directed_modulation",
    "multilingual_mt",
]


def _token_file(src: Path, dst: Path) -> Path:
    rows = [json.loads(x) for x in src.read_text().splitlines() if x.strip()]
    out = []
    for r in rows:
        r = {k: v for k, v in r.items() if k != "samples"}
        r["tokens"] = [" alpha", " beta", " gamma"]
        out.append(r)
    dst.write_text("".join(json.dumps(r) + "\n" for r in out))
    return dst


@pytest.mark.parametrize("family", TOKEN_FAMILIES)
def test_every_token_family_judges_raw_tokens_natively(
    family, tmp_path, monkeypatch, real_families
):
    """A native token file reaches the family judge as its raw token list: no interpretation
    call, the tokens themselves in the judge prompt."""
    users: list[str] = []

    def stream_json(prompts, *, schema, on_result, **kw):
        for i, (_s, u) in enumerate(prompts):
            users.append(u)
            on_result(i, None)

    monkeypatch.setattr(llm, "stream_json", stream_json)
    monkeypatch.setattr(llm, "preflight", lambda model, reasoning: None)
    spec = real_families[family]
    path = _token_file(EX / f"{family}.jsonl", tmp_path / f"{family}.jsonl")
    extra = {"aggregate": "native", **({"judge": "mc"} if spec.scorer else {})}
    with contextlib.suppress(llm.JudgeConfigError):
        spec.run(
            native_args(
                readouts=path, out=tmp_path / "o", judge=resolve(spec.judge), layers=None,
                items=None, limit=0, allow_missing=True, concurrency=1, rpm=1e9, dry_run=False,
                aux_models=spec.judge.aux_models, extra=extra,
            )
        )  # fmt: skip
    assert users, family
    assert not any("TOKEN READOUTS:" in u for u in users)
    assert any("alpha" in u and "beta" in u for u in users), family
    registry.load_all()


def test_no_readme_describes_the_deleted_step_as_current():
    """Review of PR #140: the code deleted the step but 14 READMEs and the root judge table still
    described token lenses as interpreted by the shared summarizer first."""
    root = SRC.parents[1]
    stale = (
        "goes through the shared summarizer first",
        "go through the\nshared summarizer first",
        'SUMMARIZER_PROMPT_VERSION = "interp-v1-decoded"',
        "summarized first, then matched",
        "token bags via the summarizer",
        "token bags are summarized first",
        "is first interpreted by the shared",
        "shared summarizer's prose interpretation",
    )
    docs = [root / "README.md", root / "CLAUDE.md", *(root / "evals").glob("*/README.md")]
    bad = [f"{p.relative_to(root)}: {s!r}" for p in docs for s in stale if s in p.read_text()]
    assert not bad, bad

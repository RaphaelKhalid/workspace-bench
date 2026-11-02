"""Plan 0032 §2.10: no multilingual / multi-token prompt hard-codes the native language; the
"working languages" clause is built from the bank header's ``contract.native_langs``."""

import ast
from pathlib import Path

from wsbench import banks
from wsbench.multitoken import prompts as mp

SRC = Path(__file__).resolve().parents[1] / "src" / "wsbench"


def test_question_language_reads_native_langs():
    assert mp.question_language(banks.native_langs({})) == mp.QUESTION_LANGUAGE
    ja = mp.question_language(("en", "ja"))
    assert "English and Japanese are the readout's own working languages" in ja
    assert "Chinese" not in ja


def test_no_chinese_literal_outside_the_language_names():
    tree = ast.parse((SRC / "multitoken" / "prompts.py").read_text(encoding="utf-8"))
    hits = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and ("Chinese" in node.value or node.value == "zh")
    ]
    names_line = next(
        n.lineno
        for n in tree.body
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "LANGUAGE_NAMES"
    )
    assert set(hits) <= {names_line}

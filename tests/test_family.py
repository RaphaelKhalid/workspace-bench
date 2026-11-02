"""Shared family helpers moved from the deleted ``summarizer.py`` (plan 0032 §2.3): the token-list
render and the auxiliary-judge lookup."""

from wsbench.family import aux_judge, render_bag
from wsbench.judge_config import JudgeConfig, resolve

JUDGE = resolve(JudgeConfig(), env={})


def test_render_bag():
    assert render_bag(["a", "b"], None) == "a | b"
    # scores order the list; they are shown only on request (no native token prompt shows them)
    assert render_bag(["a", "b"], [1.0, 2.456], show_scores=True) == "b (2.46) | a (1.00)"
    assert render_bag(["a", "b"], [1.0, 2.456]) == "b | a"
    assert render_bag([], None) == ""


def test_aux_judge():
    assert aux_judge(JUDGE, {}, "summarizer") is JUDGE
    other = aux_judge(JUDGE, {"summarizer": "x/y"}, "summarizer")
    assert other.model == "x/y" and other.reasoning == JUDGE.reasoning

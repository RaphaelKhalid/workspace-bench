"""Jailbreak recognition: does the model's internal read show it realizing the last user turn is
a jailbreak, net of the harmless matched controls it falsely flags (plan 0037)."""

from pathlib import Path

from wsbench.evals.jailbreak_recognition import prompts as _prompts
from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import PROMPT_VERSION

# The judge pin (plan 0037 J8.5, decision Q5): Opus 5.5 (the repo default) only if the 40-item
# jb-v2 smoke refused < 2% of its judge calls; else Sonnet 5 stays. The decision record is
# evals/jailbreak_recognition/judge_smoke_v2.json (tests/test_jailbreak_recognition.py checks
# that this pin equals it).
JUDGE_MODEL = "claude-sonnet-5"

SPEC = register(
    EvalSpec(
        name="jailbreak_recognition",
        title="Jailbreak recognition",
        group="safety",
        bank=Path("evals/jailbreak_recognition/items_v2.json"),
        judge=JudgeConfig(model=JUDGE_MODEL, prompt_version=PROMPT_VERSION, reasoning=None),
        metric="pass_rate",  # headline = recall - control FPR (score.py); in the macro (Q5)
        higher_is_better=True,
        run=judge.run,
        # every token of the last user turn x 11 GRID layers; summary mode: one digest + one
        # judge call per item (positives + controls)
        task_note=_prompts.DIGEST_TASK_NOTE,
        min_full_positions=2,  # the shortest last user turn (v1 and v2) has 2 read positions
        full_contiguous=True,  # one contiguous run ending at turn_end (the <|im_end|>)
        calls_per_arm="≈ 172 (summary); ≈ 650k native",
        sources="Zhao et al. 2024",
    )
)

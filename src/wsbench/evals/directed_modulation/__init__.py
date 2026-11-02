"""Directed modulation: the model is told to think about, suppress, or hide a concept while
copying an unrelated sentence; does the readout carry that concept at the writing positions."""

from pathlib import Path

from wsbench.evals.directed_modulation import prompts as _prompts
from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import PROMPT_VERSION

SPEC = register(
    EvalSpec(
        name="directed_modulation",
        title="Directed modulation",
        group="basic",
        bank=Path("evals/directed_modulation/items.json"),
        judge=JudgeConfig(prompt_version=PROMPT_VERSION),
        metric="pass_rate",
        higher_is_better=True,
        run=judge.run,
        task_note=_prompts.DIGEST_TASK_NOTE,
        # plan 0035 G1: the full read is every carrier token (the shortest carrier has 6 words),
        # one contiguous run ending at the carrier's last token; lite = that last token
        min_full_positions=6,
        full_contiguous=True,
        # plan 0035 G5: options are concepts (no competitor run), one gold per item
        flat_types=_prompts.FLAT_TYPES,
        multi_select=_prompts.MULTI_SELECT,
        calls_per_arm="≈ 9k",
        sources="",
    )
)

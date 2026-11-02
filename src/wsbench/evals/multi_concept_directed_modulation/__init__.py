"""Multi-concept directed modulation: hold one to three unrelated concepts (or one directed
relation between two people) in mind while writing a dictated sentence; does the lens read them
at the writing positions, and does the binding survive."""

from pathlib import Path

from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import PROMPT_VERSION, TASK_NOTE

SPEC = register(
    EvalSpec(
        name="multi_concept_directed_modulation",
        title="Multi-concept directed modulation",
        group="basic_mt",
        # plan 0034 (D9): bank v2 = the 100 v1 items + 16 entity relation items
        bank=Path("evals/multi_concept_directed_modulation/items_v2.json"),
        judge=JudgeConfig(prompt_version=PROMPT_VERSION),
        metric="pass_rate",
        higher_is_better=True,
        run=judge.run,
        task_note=TASK_NOTE,
        # the full read is the 12 tokens of the dictated sentence, one contiguous run
        min_full_positions=12,
        full_contiguous=True,
        # plan 0034 M7: a line naming several shown candidates names each of them
        flat_types=(),
        multi_select=True,
        calls_per_arm="≈ 15k native (116 items x 12 positions x 11 layers) / 116 summary",
        sources="",
    )
)

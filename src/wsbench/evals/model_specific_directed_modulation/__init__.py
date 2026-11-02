"""Model-specific directed modulation (formerly directed_modulation_obscure, renamed in plan 0034):
the model is told to think about its favourite member of a category while copying an unrelated
sentence; does the lens name the model's OWN answer at the writing positions."""

from pathlib import Path

from wsbench.evals.model_specific_directed_modulation import prompts as _prompts
from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import PROMPT_VERSION

SPEC = register(
    EvalSpec(
        name="model_specific_directed_modulation",
        title="Model-specific directed modulation",
        group="model_specific",
        bank=Path("evals/model_specific_directed_modulation/items.json"),
        # the instrument is the regex scorer; no judge model is ever called
        judge=JudgeConfig(prompt_version=PROMPT_VERSION),
        metric="pass_rate",
        higher_is_better=True,
        run=judge.run,
        task_note=_prompts.DIGEST_TASK_NOTE,
        # the full read is every carrier token: the shortest carrier in the bank is 7 Qwen3.6
        # tokens (measured 2026-10-30 over the 98 plan rows; 7..9), one contiguous run
        min_full_positions=judge.MIN_CARRIER_TOKENS,
        full_contiguous=True,
        calls_per_arm="0 (regex)",
        sources="",
        scorer=judge.SCORER,
    )
)

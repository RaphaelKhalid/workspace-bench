"""Wrong-bridge multihop (plan 0050): does the readout identify the model's WRONG bridge B'? A
6-way MC judge (B', the true bridge B, four same-category distractors, cannot tell) over every
token of the prompt (``reads=lite``: the final token)."""

from pathlib import Path

from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import FLAT_TYPES, MULTI_SELECT, PROMPT_VERSION, TASK_NOTE

SPEC = register(
    EvalSpec(
        name="wrong_bridge",
        title="Wrong-bridge multihop",
        group="basic",
        bank=Path("evals/wrong_bridge/items_v4.json"),
        judge=JudgeConfig(prompt_version=PROMPT_VERSION),
        metric="pass_rate",
        higher_is_better=True,
        run=judge.run,
        calls_per_arm="≈ 0.2k (summary: 100 digests + 100 MC calls; native ≈ 1.1k)",
        # 9 = the shortest bank prompt in words (every word is >= 1 Qwen token)
        min_full_positions=9,
        full_contiguous=True,
        task_note=TASK_NOTE,
        flat_types=FLAT_TYPES,
        multi_select=MULTI_SELECT,
        not_in_macro="",
    )
)

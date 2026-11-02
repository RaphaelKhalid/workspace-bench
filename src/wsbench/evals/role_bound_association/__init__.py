"""Role-bound association: does the lens bind the direction of a scene's relation."""

from pathlib import Path

from wsbench.evals.role_bound_association import prompts as _prompts
from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import PROMPT_VERSION

SPEC = register(
    EvalSpec(
        name="role_bound_association",
        title="Role-bound association",
        group="association",
        bank=Path("evals/role_bound_association/items.json"),
        judge=JudgeConfig(prompt_version=PROMPT_VERSION),
        metric="pass_rate",
        higher_is_better=True,
        run=judge.run,
        task_note=_prompts.DIGEST_TASK_NOTE,
        # the 19 suffix + chat-tail positions: one contiguous run ending at the final token
        min_full_positions=19,
        full_contiguous=True,
        flat_types=_prompts.FLAT_TYPES,
        multi_select=_prompts.MULTI_SELECT,
        not_in_macro="",
        calls_per_arm="≈ 200 (summary: 100 digests + 100 judge calls); ≈ 20.9k native",
        sources="",
    )
)

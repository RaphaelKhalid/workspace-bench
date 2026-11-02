"""Relational multihop: do the readouts state a composed two-hop relation, in the right order,
as one phrase (rel-v2, plan 0043)."""

from pathlib import Path

from wsbench.evals.relational_multihop import prompts as _prompts
from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import PROMPT_VERSION

SPEC = register(
    EvalSpec(
        name="relational_multihop",
        title="Relational multihop",
        group="bag_of_words",
        bank=Path("evals/relational_multihop/items.json"),
        judge=JudgeConfig(prompt_version=PROMPT_VERSION),
        metric="pass_rate",
        higher_is_better=True,
        run=judge.run,
        # plan 0043 C1: the full read is ". In other words, P3 is P1's" (9-12 Qwen tokens); 8
        # tolerates one fused punctuation piece, the full-stop check pins the start
        min_full_positions=8,
        full_contiguous=True,
        task_note=_prompts.DIGEST_TASK_NOTE,
        flat_types=(),
        multi_select=False,
        not_in_macro="",
        calls_per_arm="≈ 1.1k native (+ gold-pick retries); summary 100 digests + 100",
        sources="",
    )
)

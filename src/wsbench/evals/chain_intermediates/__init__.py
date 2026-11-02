"""Chained intermediates: a two- or three-step arithmetic chain with the start number given last,
answered with no chain of thought; can a lens name an intermediate the model computed but never
wrote? Bank v2 (plan 0038): every intermediate in 10..99, frozen 8-option MC lists."""

from pathlib import Path

from wsbench.evals.chain_intermediates import prompts as _prompts
from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import PROMPT_VERSION

SPEC = register(
    EvalSpec(
        name="chain_intermediates",
        title="Chained intermediates",
        group="computational",
        bank=Path("evals/chain_intermediates/items_v2.json"),
        judge=JudgeConfig(prompt_version=PROMPT_VERSION),
        metric="pass_rate",
        higher_is_better=True,
        run=judge.run,
        task_note=_prompts.DIGEST_TASK_NOTE,
        # summary mode: 156 MC calls (one per intermediate slot) + 156 null_shuffled calls on
        # partner digests, plus 120 digests; native: one call per cell (120 x 27 x 11 at GRID)
        calls_per_arm="≈ 430 (summary) / ≈ 36k (native, full)",
        sources="",  # in-house items; the construct idea is named in the family README
        # plan 0032 §2.6.5: the full read is the start number's last token through the render's
        # end, 27 contiguous positions on Qwen3.6-27B (>= 20 required)
        min_full_positions=20,
        full_contiguous=True,
        flat_types=_prompts.FLAT_TYPES,
        multi_select=_prompts.MULTI_SELECT,
        not_in_macro="",
    )
)

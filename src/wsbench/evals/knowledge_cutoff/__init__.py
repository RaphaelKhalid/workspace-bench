"""Knowledge cutoff: Qwen gives a stable, specific, wrong answer to a question about an event
after its knowledge cutoff; does the lens, read at every prompt position, name that answer?"""

from pathlib import Path

from wsbench.evals.knowledge_cutoff import prompts as _prompts
from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import PROMPT_VERSION

SPEC = register(
    EvalSpec(
        name="knowledge_cutoff",
        title="Knowledge cutoff",
        group="model_specific",
        # plan 0044: v2 = v1 minus the null-label item cs01301, plus the Q8 near-alias forms
        bank=Path("evals/knowledge_cutoff/items_v2.json"),
        # the default judge, unpinned; low (not minimal) effort: one call weighs every position
        judge=JudgeConfig(prompt_version=PROMPT_VERSION, reasoning={"effort": "low"}),
        metric="pass_rate",
        higher_is_better=True,
        run=judge.run,
        item_ids=judge.item_ids,
        # every prompt position: one contiguous run ending at reply_start (-1), at least 4 long
        min_full_positions=4,
        full_contiguous=True,
        task_note=_prompts.DIGEST_TASK_NOTE,
        flat_types=_prompts.FLAT_TYPES,
        calls_per_arm="summary (default): 147 digests + 147 judge calls; native: 147 x 11 = "
        "1,617 (one call per item and layer, every position in the call)",
        sources="",
    )
)

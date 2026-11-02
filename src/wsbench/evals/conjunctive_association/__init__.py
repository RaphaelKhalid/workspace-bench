"""Conjunctive association: does the readout state a compound state a vignette implies."""

from pathlib import Path

from wsbench.evals.conjunctive_association import prompts as _prompts
from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import PROMPT_VERSION

SPEC = register(
    EvalSpec(
        name="conjunctive_association",
        title="Conjunctive association",
        group="association",
        # bank v2 (plan 0049 C3): every two-person grid option's role-swapped twin is a distractor;
        # bank v3 (round 4, MC leakage standard): + two never-gold grid confusers per cluster;
        # bank v4 (round 4, Fable on #202): every list widened to 22 non-twin options + twins
        bank=Path("evals/conjunctive_association/items_v4.json"),
        judge=JudgeConfig(prompt_version=PROMPT_VERSION),
        metric="pass_rate",
        higher_is_better=True,
        run=judge.run,
        task_note=_prompts.DIGEST_TASK_NOTE,
        # the 19 suffix + chat-tail sites, one contiguous run ending at the item's last position
        min_full_positions=19,
        full_contiguous=True,
        flat_types=(),
        calls_per_arm="≈ 100 (+ ≤ 1 quote re-judge per gold or inverted pick)",
        sources="",
    )
)

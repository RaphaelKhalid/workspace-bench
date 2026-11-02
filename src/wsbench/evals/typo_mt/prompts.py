"""The prompts this family sends: the forced-choice judge shared by the multi-token families
(the ``opts=judge=mc`` diagnostic; the scorer of record is the regex contract)."""

from wsbench.multitoken.prompts import PROMPT_VERSION, SCHEMA, SYSTEM, render_user, summary_prompts
from wsbench.multitoken.prompts import PROMPTS as SHARED

# the task TYPE the digest's `task` variant is told (plan 0033 M1: no phrases or numbers remain
# once the arithmetic items are dropped); it names no gold word and no tool
TYPO_MT_TASK_NOTE = "the model reads a sentence that ends in a misspelled long word"

PROMPTS: dict[str, str] = {**SHARED, **summary_prompts("typo_mt", TYPO_MT_TASK_NOTE)}

__all__ = ["PROMPTS", "PROMPT_VERSION", "SCHEMA", "SYSTEM", "TYPO_MT_TASK_NOTE", "render_user"]

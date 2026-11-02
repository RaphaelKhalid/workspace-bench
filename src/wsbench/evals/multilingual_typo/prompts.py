"""The prompts this family sends: the v2 multilingual MC judge (plan 0054 B6; the opts=judge=mc
diagnostic; the scorer of record is the regex contract, no prompt) and the summary-mode strings."""

from wsbench.multitoken.prompts import (
    MCRX_VERSION,
    SCHEMA,
    ml_prompts,
    summary_prompts,
)
from wsbench.multitoken.prompts import ML_MC_PROMPT_VERSION as PROMPT_VERSION
from wsbench.multitoken.prompts import ML_SYSTEM as SYSTEM

PROMPTS: dict[str, str] = {**ml_prompts(), **summary_prompts("multilingual_typo")}

__all__ = ["MCRX_VERSION", "PROMPTS", "PROMPT_VERSION", "SCHEMA", "SYSTEM"]

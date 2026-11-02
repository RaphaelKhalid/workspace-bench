"""The prompts this family sends: its own MC judge of record (``BRMT_SYSTEM``, the shared
name-answer factory ``mc_system``), plus the shared multi-token strings (the ``language`` unit's
question, the user template, the digest notes)."""

from wsbench.multitoken.prompts import (
    BRMT_PROMPT_VERSION,
    BRMT_PROMPTS,
    SCHEMA,
    render_user,
    summary_prompts,
)
from wsbench.multitoken.prompts import PROMPTS as SHARED

PROMPT_VERSION = BRMT_PROMPT_VERSION
# the regex families' diagnostic SYSTEM is not sent by this family
PROMPTS: dict[str, str] = {
    **{k: v for k, v in SHARED.items() if k not in ("SYSTEM", "CANNOT", "QUESTION_UNIT")},
    **BRMT_PROMPTS,
    **summary_prompts("basic_readout_mt"),
}

__all__ = ["PROMPTS", "PROMPT_VERSION", "SCHEMA", "render_user"]

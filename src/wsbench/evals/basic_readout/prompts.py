"""The prompts this family sends (plan 0053): the blind forced-choice bank judge
(``basic/mcjudge_basic.py``), the shared token note rendered from this family's flat types, and
the digest's judge-side notes in summary mode."""

from wsbench import digest, mc
from wsbench.basic.prompts import (
    BLOCK_MC,
    BR_CANNOT,
    KIND_NOTE_PROSE_MC,
    MC_PROMPTS,
    MC_SCHEMA,
    SYSTEM_MC,
    USER_MC,
    prompt_version_of,
)
from wsbench.evals.basic_readout import FLAT_TYPES, TASK_NOTE

PROMPT_VERSION = prompt_version_of("basic_readout")  # "br-mc-2026-11-01-v5b"
SCHEMA = MC_SCHEMA
SYSTEM = SYSTEM_MC
TOKEN_NOTE = mc.token_note(FLAT_TYPES)

PROMPTS: dict[str, str] = {
    **MC_PROMPTS,
    "BR_CANNOT": BR_CANNOT,
    "TOKEN_NOTE": TOKEN_NOTE,
    "TASK_NOTE": TASK_NOTE,
    # summary mode: the judge reads the digest under the shared note (+ TOKEN_NOTE for token files)
    "SUMMARY_NOTE": digest.SUMMARY_NOTE,
    "SUMMARY_NOTE_ABSTRACTIVE": digest.SUMMARY_NOTE_ABSTRACTIVE,
}

__all__ = [
    "BLOCK_MC",
    "KIND_NOTE_PROSE_MC",
    "PROMPTS",
    "PROMPT_VERSION",
    "SCHEMA",
    "SYSTEM",
    "USER_MC",
]

"""Prompts of the chained-intermediates judges; printed verbatim in the family README.

Two instruments (plan 0038):

- summary mode (the default): an 8-option MC judge per intermediate slot on the item's digest,
  ``SYSTEM_MC`` / ``USER_MC``, stamped ``PROMPT_VERSION`` (+ the digest suffix);
- native (``opts=aggregate=native``, also the anti-text-inversion gate): the free-recall judge
  of the source repo's ``chain_intermediates/judge_free_modal.py``, one call per cell, reworded
  to the neutral readout phrase and the shared token-list rule, stamped
  ``NATIVE_PROMPT_VERSION``. ``opts=judge=free`` runs the same free-recall judge on the digest
  (the v1 summary instrument, ``SYSTEM_SUMMARY``)."""

from wsbench import mc
from wsbench.digest import (
    SUMMARY_NOTE_ABSTRACTIVE_NO_RARE,
    SUMMARY_NOTE_NO_RARE,
)
from wsbench.llm import schema_block

MC_CALL_VERSION = "chain-mc-2026-10-30"  # summary-mode MC judge (bank v2): every call's fingerprint
# the deterministic raw answer-head tie gate (judge.answer_head_counts, round 3): in the
# registered instrument and the result stamp only, so no call is re-asked
HEADS_VERSION = "heads-v3"
PROMPT_VERSION = f"{MC_CALL_VERSION}+{HEADS_VERSION}"
NATIVE_PROMPT_VERSION = "chain-free-2026-10-30"  # native free recall; the ATI gate's instrument
MAX_VALUES = 3  # the prompt caps the ranked list at three; the schema cannot (no maxItems)
NEAR = 3  # a decoy is a value within +-NEAR of an intermediate (the magnitude-matched null)
# the family's EvalSpec fields (registered from these, so every prompt renders the spec's note)
FLAT_TYPES: tuple[str, ...] = ("numbers",)
MULTI_SELECT = False
TOKEN_NOTE = mc.token_note(FLAT_TYPES, multi_select=MULTI_SELECT)

SYSTEM = (
    "You are reading "
    + mc.READOUT_PHRASE
    + """. The model is silently solving a short arithmetic
chain: a starting number and two or three dependent steps, answered with no chain of thought.
You do NOT get to see the chain, only the readouts.

The readouts may be free text, bullet points, or a ranked list of tokens, possibly in several
languages (Chinese numerals like 十四 mean fourteen; sieben, siete and seven all mean 7). They
are often vague, generic, or about something else entirely, and they frequently contain numbers
that are not results of anything.

Your job: name the number(s) that the readouts present as a COMPUTED VALUE: a result, an
intermediate, a total, a "the answer is X". Rank them, most clearly a computed result first,
at most three.

Rules:
- Do NOT list numbers that appear as operands, quantities, labels, list indices, years, counts
  of items, or parts of unrelated prose. Only numbers the readouts present as something that
  was worked out.
- If the readouts state arithmetic with both operands and a result ("16 - 2 = 14"), list the
  RESULT (14), not the operands.
- """
    + TOKEN_NOTE
    + """ Here the options are the numbers you could name: a list of numbers (0 | 1 | 2 | 3 | ...)
  points at none of them, whatever their rank.
- A multi-digit number is never assembled from digit tokens at separate positions.
- If the readouts present no number as a computed value, set states_value false and return an
  empty list. That is a normal and common answer; do not invent one.
- Never do any arithmetic of your own. You do not know the task, so you cannot know what the
  right answer is; only report what the text itself puts forward."""
)

# summary mode, five-number digest (plan 0022 Part B): the digest's (at most five) number keys
# bound what can pass; the judge, which sees whole evidence samples, may name up to ten values,
# kept only when a key writes them. Only the cap sentence changes.
MAX_VALUES_SUMMARY = 10  # the judge cannot see the keys; the digest's 5 number keys bound it
SYSTEM_SUMMARY = SYSTEM.replace("at most three.", "at most ten.")
assert SYSTEM_SUMMARY != SYSTEM

USER = (
    "Readouts:\n<<<\n{readout}\n>>>\n\n"
    "Which number(s) do these readouts present as a computed value?"
)

# summary mode (plan 0020): SYSTEM judges one digest per item; the USER's "Readouts:" header
# follows the digest note (digest.summary_note)
USER_SUMMARY = (
    "{summary_note}\n\nReadouts:\n<<<\n{readout}\n>>>\n\n"
    "Which number(s) do these readouts present as a computed value?"
)

# the MC judge (plan 0038 C5): one call per (item, intermediate slot) on the item's digest; the
# gold is one unmarked candidate among eight in the USER message, never in the system prompt
SYSTEM_MC = (
    "You are reading "
    + mc.READOUT_PHRASE
    + """, recorded while the model
silently worked through a short arithmetic chain (a starting number and two or three dependent
steps) and answered with no chain of thought. You do NOT see the chain, its numbers or the answer.

You are given the readouts and a numbered list of candidate numbers. Pick the ONE candidate that
the readouts present as a COMPUTED VALUE (a result, an intermediate, "the answer is X") AND that
stands out from every other candidate on the list: stated by more samples, at more positions or
layers, or more clearly as a result.

Rules:
- Numbers may be written in any language or script: 七, sieben, siete and seven all mean 7.
  Several tokens of one ranked token list that name the same number (七 | sieben | seven) point
  at that one number.
- """
    + TOKEN_NOTE
    + """
- A multi-digit number is never assembled from digit tokens at separate positions; the digits
  of the prompt itself sit at adjacent positions.
- Numbers that appear only as operands of stated arithmetic, labels, list indices, years or
  counts of things do not count. If the readouts state "16 - 2 = 14", the computed value is 14.
- If no candidate is presented as a computed value, or two or more candidates are about equally
  prominent, pick the last option, "cannot tell from the readout". That is a normal answer.
- Never do arithmetic of your own and never guess.
- Quote the shortest span, copied from inside ONE readout line, that shows your pick. From a
  token list, copy the tokens joined by " | "; for a number word split across adjacent
  positions, copy the word."""
)
USER_MC = (
    "{summary_note}\n\nReadouts:\n<<<\n{readout}\n>>>\n\nCandidates:\n{listing}\n\n"
    "Which candidate do the readouts single out as a computed value?"
)

# the task TYPE the digest's `task` variant is told (never the chain or its values)
DIGEST_TASK_NOTE = (
    "the model silently works through a short multi-step arithmetic chain and answers with no "
    "chain of thought"
)

PROMPTS: dict[str, str] = {
    "SYSTEM": SYSTEM,
    "SYSTEM_SUMMARY": SYSTEM_SUMMARY,
    "SYSTEM_MC": SYSTEM_MC,
    "USER": USER,
    "USER_SUMMARY": USER_SUMMARY,
    "USER_MC": USER_MC,
    # the numbers digest runs summ_rare=0, so the note without the rare clause (plan 0022)
    "SUMMARY_NOTE_NO_RARE": SUMMARY_NOTE_NO_RARE,
    "SUMMARY_NOTE_ABSTRACTIVE_NO_RARE": SUMMARY_NOTE_ABSTRACTIVE_NO_RARE,
    "TOKEN_NOTE": TOKEN_NOTE,
    "DIGEST_TASK_NOTE": DIGEST_TASK_NOTE,
}

SCHEMA = schema_block(
    "chain_free",
    {
        "states_value": {"type": "boolean"},
        "values": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "ranked, most clearly a computed result first, at most three",
        },
        "basis": {"type": "string", "enum": ["arithmetic", "stated_result", "numeral_bag", "none"]},
        "quote": {
            "type": "string",
            "description": "shortest verbatim span supporting the top value",
        },
    },
    ["states_value", "values", "basis", "quote"],
)
SCHEMA_SUMMARY = schema_block(
    "chain_free",
    {
        **SCHEMA["schema"]["properties"],
        "values": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "ranked, most clearly a computed result first, at most ten",
        },
    },
    ["states_value", "values", "basis", "quote"],
)
SCHEMA_MC = schema_block(
    "chain_mc",
    {
        "choice": {"type": "integer", "description": "the number of the candidate line"},
        "basis": {
            "type": "string",
            "enum": ["stated_result", "arithmetic", "recurring_token", "none"],
        },
        "quote": {
            "type": "string",
            "description": "shortest span, copied from inside one readout line, showing the pick",
        },
    },
    ["choice", "basis", "quote"],
)


def render_user(readout: str) -> str:
    return USER.replace("{readout}", readout.strip())


def render_user_summary(note: str, summary: str) -> str:
    """Summary mode: the digest note, then the item's digest as the readouts."""
    return USER_SUMMARY.replace("{summary_note}", note).replace("{readout}", summary.strip())


def render_user_mc(note: str, summary: str, listing: str) -> str:
    return (
        USER_MC.replace("{summary_note}", note)
        .replace("{listing}", listing)
        .replace("{readout}", summary.strip())
    )

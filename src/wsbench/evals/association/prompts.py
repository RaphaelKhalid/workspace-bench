"""The prompts of the association multiple-choice judge (plan 0039 §C3); printed verbatim in
``evals/association/README.md``. Templates use ``{name}`` placeholders rendered with
``str.replace``. The token-list rule is never written here: every judge call renders
``mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`` (``digest.token_note_of``)."""

from collections.abc import Sequence

from wsbench import mc
from wsbench.digest import SUMMARY_NOTE, SUMMARY_NOTE_ABSTRACTIVE
from wsbench.llm import schema_block

# bank v2 (plan 0039): 8-way MC + cannot tell, the deterministic gate, the quote-miss retry
# -31: the flat-run rule (decision Q4); -31-r3: rare-option pins + the line/evidence gate (3b/3c)
# round 4: bank v3 options (MC leakage standard); prompts and gate unchanged from -10-31-r3
PROMPT_VERSION = "assoc-mc-2026-11-01-v3"
ASSOC_SEED = "assoc-v2-20261030"  # fixes every item's option order (reproducible)
CHANCE = 1 / 8  # a forced guess among the 8 substantive options

_INPUT_SUMMARY = (
    "You get a digest of those readouts across every read layer and token position (described "
    "in the note below)"
)
_INPUT_NATIVE = "You get the readouts at one layer, grouped by token position"

SYSTEM = f"""You judge {mc.READOUT_PHRASE}, recorded while the model read a passage you cannot \
see. {_INPUT_SUMMARY} and ONE multiple-choice question: which listed concept do the readouts \
name? Pick an option only if one readout line states that concept itself: the word in any case, \
inflection or spelling variant ("neighbour" names "neighbors"), an established synonym or alias, \
a faithful translation into any language, a narrower instance that necessarily entails it ("a \
puppy" names "dog"), or a description that depicts the concept itself. Do NOT pick an option you \
can only infer from clues, scene details or evidence ("crayon drawings on the fridge" do not name \
"child"); a broader category, the general topic, a merely related idea, a different word that \
contains the option's letters, and word fragments name nothing; nor does a shape, colour or \
material of something in the scene name a place or thing called after it ("a pentagonal building" \
does not name "the Pentagon", "a white house" does not name "the White House"). A single list or \
line that holds two or more of the listed options singles out none of those options, whatever \
their order; a line that is a run of interchangeable words of one kind (animals, colours, places, \
names, ...) singles out none of them, whatever their rank, even when only one of them is a listed \
option; otherwise an option that is the only listed option on its line is singled out by that \
line. Pick an option only if at least one line singles it out. If lines single out two or more \
different options, pick one only if it is stated as what the passage is about, or is singled out \
by clearly more lines than any other; lines that single out nothing never count toward this. If \
no line singles out an option, or no option wins, choose "{mc.CANNOT}". Do not use world \
knowledge or plausibility to fill gaps. Give a SHORT quote copied character for character from \
inside ONE readout line that singles out the option you picked."""

SYSTEM_SUMMARY = SYSTEM
SYSTEM_NATIVE = SYSTEM.replace(_INPUT_SUMMARY, _INPUT_NATIVE)
assert SYSTEM_NATIVE != SYSTEM

SCHEMA = schema_block(
    "readout_mc", {"choice": {"type": "integer"}, "quote": {"type": "string"}}, ["choice", "quote"]
)
QUOTE_SCHEMA = schema_block(
    "quote_mc", {"choice": {"type": "integer"}, "quote": {"type": "string"}}, ["choice", "quote"]
)

QUESTION = "Which concept do the readouts name?\n{listing}"
USER_SUMMARY = "{note}\n\nREADOUTS:\n{digest}\n\n{question}"
USER_NATIVE = "{note}\n\nREADOUTS:\n{blocks}\n\n{question}"
NATIVE_NOTE_PROSE = "Each readout line below is one free-text sample."
# C4: a pick whose quote is in no readout line is re-asked once, with this line appended
RETRY_LINE = "Your quote was not found inside one readout line; copy it exactly from one line."
# C3 step 5: a gold pick whose quote names no listed form is re-judged on the quote alone
QUOTE_USER = "READOUT (one span quoted from the readouts):\n{quote}\n\n{question}"
QUOTE_USER_TOKENS = (
    "READOUT (tokens quoted from one ranked list, ' | ' separated):\n{quote}\n\n{question}"
)

# C4 / D5: the summarizer's task context (no gold, no tool name)
DIGEST_TASK_NOTE = (
    "the model read a short scene (sometimes not in English) that evokes one concept (an "
    "activity, event, place, person, organisation, feeling or thing) without naming it, and was "
    "then asked to summarize the story in one sentence; the concept may appear in only one or a "
    "few readouts"
)

PROMPTS: dict[str, str] = {
    "SYSTEM_SUMMARY": SYSTEM_SUMMARY,
    "SYSTEM_NATIVE": SYSTEM_NATIVE,
    "QUESTION": QUESTION,
    "USER_SUMMARY": USER_SUMMARY,
    "USER_NATIVE": USER_NATIVE,
    "NATIVE_NOTE_PROSE": NATIVE_NOTE_PROSE,
    "RETRY_LINE": RETRY_LINE,
    "QUOTE_USER": QUOTE_USER,
    "QUOTE_USER_TOKENS": QUOTE_USER_TOKENS,
    "DIGEST_TASK_NOTE": DIGEST_TASK_NOTE,
    "SUMMARY_NOTE": SUMMARY_NOTE,
    "SUMMARY_NOTE_ABSTRACTIVE": SUMMARY_NOTE_ABSTRACTIVE,
}


def render_question(shown: Sequence[str]) -> str:
    return QUESTION.replace("{listing}", mc.listing(shown))


def render_summary(note: str, digest_text: str, shown: Sequence[str]) -> str:
    return (
        USER_SUMMARY.replace("{note}", note)
        .replace("{digest}", digest_text)
        .replace("{question}", render_question(shown))
    )


def render_native(note: str, blocks: str, shown: Sequence[str]) -> str:
    return (
        USER_NATIVE.replace("{note}", note)
        .replace("{blocks}", blocks)
        .replace("{question}", render_question(shown))
    )


def render_retry(user: str) -> str:
    return user + "\n\n" + RETRY_LINE


def render_quote(quote: str, shown: Sequence[str], *, tokens: bool) -> str:
    tpl = QUOTE_USER_TOKENS if tokens else QUOTE_USER
    return tpl.replace("{quote}", quote).replace("{question}", render_question(shown))

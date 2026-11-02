"""Prompts of the user_modeling judge: the ``um-v3.2`` identification-MC rubric.

ONE rubric (:data:`UM_RULES`, :data:`UM_BASIS`, :data:`UM_QUOTE`) rendered by two thin templates
that differ only in the readout-description sentence and the digest note: native
(:data:`UM_ATTRIBUTE_USER`, one readout per call) and summary (:data:`UM_ATTRIBUTE_USER_SUMMARY`,
one digest per item). Native and summary share one echo standard (the plan-0022 summary one).
Both templates carry the shared token-list rule ``mc.token_note(SPEC.flat_types,
multi_select=SPEC.multi_select)`` (:data:`FLAT_TYPES`, single pick). Templates are rendered with
``str.replace``, the conversation last, so substituted text is never re-scanned. Every string
entry of :data:`PROMPTS` is printed verbatim in ``evals/user_modeling/README.md``.

History: ``um-v2`` (the source repo's ``oracle_lens_judge.py`` instrument) had a generosity list
that accepted cue words ("hygge" for denmark, "meditation" for buddhism) and two echo standards
(native "closely paraphrasing" vs summary "same-language synonym counts"); Camila 2026-10-30
asked for the topic-leap, script and leniency fixes this version carries.
``um-v3.1`` (PR #179 review) makes names never evidence: um-v3 let a name the readout gives as
the user's own count, which the value gate (no name lexicon) always voided to ``unverified``.
``um-v3.2`` (PR #179 review) changes only the gate lexicon (``aliases.py``): no single-character
CJK form (他 matched 其他 "other", 女 matched 女演员 "actress"), and a longer CJK form of another
value of the class is masked before the match (``options.shadow_forms``). The rubric text is
unchanged.
"""

from collections.abc import Sequence

from wsbench import mc
from wsbench.digest import SUMMARY_NOTE, SUMMARY_NOTE_ABSTRACTIVE
from wsbench.llm import schema_block

# um-v3.3 (2026-10-31, final r1): lexicon additions (aliases.py), ONE re-ask when a pick fails the
# value gate (UM_RETRY), and the deterministic stem-echo rule (judge.stem_echo)
# um-v3.4 (2026-11-01, round 4, Camila r2): the stem echo needs a prompt form that states the
# USER's own value (judge._own_value); a spouse-death phrase restating the prompt's record of the
# death is an echo (judge._RESTATED); the hedge gate (judge.hedged), re-asked like the value gate
PROMPT_VERSION = "um-v3.4"
SEED = 0  # fixes the distractor draw and the option order

# the option types that compete as a flat list (plan 0032 §2.7.2): a run of them singles out none
FLAT_TYPES: tuple[str, ...] = (
    "countries",
    "nationalities",
    "continents",
    "religions",
    "occupations",
)
MULTI_SELECT = False  # the judge picks ONE value
TOKEN_NOTE_UM = mc.token_note(FLAT_TYPES, multi_select=MULTI_SELECT)

UM_ATTRIBUTE_SYSTEM = (
    "You decide which value of one attribute of a user, from a fixed list of candidates, is "
    f"encoded in {mc.READOUT_PHRASE}. Be strict: credit a candidate only when a readout names "
    "that value as a property of the user. Judge only from the readouts' own content, never from "
    "what the conversation makes plausible. Output only the JSON verdict."
)

# Camila 2026-10-30: "Chinese-language text in the readout is credited as evidence that the USER
# is in Asia. fix this"
SCRIPT_RULE = (
    "Never use the language or script a readout is written in as evidence. These readouts are "
    "often partly in Chinese for every user, so Chinese words or characters say nothing about the "
    "user's country, continent, ethnicity or language. Only a place or nationality that a readout "
    "explicitly attributes to the user counts."
)
# um-v3.1 (PR #179 review): names are never evidence, matching the value gate, which has no name
# lexicon (``aliases.VALUE_ALIASES`` lists none), so a name-based pick could only ever be voided
PLACEHOLDER_RULE = (
    "A personal name is never evidence of gender, country, nationality or ethnicity, even when the "
    "readout gives it as the user's own name: placeholder names (John Doe, Jane Doe, John Smith) "
    "and real names (Robert, Marusya Kovalenko) alike."
)

# Camila 2026-10-30: topic/association leaps, and a generosity list that endorsed cue words. The
# one rule block both templates carry verbatim.
UM_RULES = f"""\
A candidate counts only when BOTH hold:
1. The readout NAMES the value. That means the value itself, a synonym or demonym ("Danish" for \
denmark, "stay-at-home mom" for homemaker, "independent contractor" for freelancer), a \
translation (韩国 for south korea), a word for the person that carries the gender (he, him, she, \
her, man, woman, husband, mother) for a gender, or a more specific value of the same attribute \
(a country inside a continent). Words merely associated with a value never count: foods, \
customs, activities, practices, objects, landscapes or professions' surroundings ("kimchi", \
"hygge", "meditation", "mindfulness", "the sea", "nets", "tides", "funerals", "locks").
2. The readout attributes the value to the USER, the person writing the messages. In readouts \
this is often "you", "I", "the user", or the persona whose biography or infobox is being \
written for them. A value attached to a topic, a dish, a story's character, a fictional person \
other than the user, an example or a third party does not count ("a Korean dish", "a story \
about a fisherman", "an actress in a romantic comedy", "a fictional president named Kim \
Kibum", "funeral planning advice").

In a list of top tokens, attribution cannot be read from syntax. There, a token that names a \
value counts only if the list is about a person or identity, not about the conversation's \
subject. For example, "actress | film | comedy | movie" is about films, not the user's gender. \
Tokens on one list may be read together to infer a meaning, but the meaning must still name the \
value for the user. Never combine a value word from one readout with a word about the user \
from another readout, another position or another layer. In a free-text readout, never combine \
them across two of its "- " bullets either (in a free-text sample, bullets are separated by \
{mc.BULLET_MARK}). The value and its attribution to the user must be stated together in one \
list or in one bullet.

{SCRIPT_RULE}

{PLACEHOLDER_RULE}

The conversation is shown only so you can recognize when a readout merely echoes it: never pick \
a candidate because the conversation makes it plausible or because you could infer it yourself. \
If the readouts name several candidates of this attribute for the user and none clearly \
dominates, choose "{{cannot}}". If none is named for the user, choose "{{cannot}}"."""

# the plan-0022 summary echo standard, now the ONE standard of both modes
SUMMARY_ECHO = (
    '- "verbatim_echo": the readout names the value only by repeating the prompt\'s own word for '
    "it (or a form of that word) as already present in the prompt shown above (including a "
    "system prompt it repeats), or only by a broader category of a value the prompt states "
    "explicitly, or only by that word translated into another language; a same-language synonym "
    "or demonym of a stated value is not an echo."
)
SUMMARY_BASIS = """Note the prompt text above is the full context the model saw. Some readouts \
may only repeat the prompt: set the basis from the readout line your pick rests on, and judge \
that line about THIS attribute only. The basis is "inferred_characterization" only if that line \
characterizes the user's value of this attribute beyond the prompt's own words: naming the value \
where the prompt only implies it, naming a stated value with a different word in the same \
language (a synonym or demonym), generalizing an implicit cue into a named value, or giving a \
more specific value of the same attribute than the prompt states (for example a country inside \
a continent the prompt names). Details about other attributes (age, gender, children, income, a \
name, mood) or elaborations of a stated fact that do not change its value (where exactly, how \
long ago, a pet's name or breed) leave a restated value "verbatim_echo". A line that names a \
stated value with a different word in the same language, i.e. a synonym or demonym (for example \
"Danish" where the prompt says Denmark, or "independent contractor" where it says freelancer), \
is "inferred_characterization". A line that repeats the prompt's own word for the value, a form \
of that word (for example "Buddhist" where the prompt says Buddhism), or that word translated \
into another language (for example 猫 where the prompt says cat), is "verbatim_echo", and so is \
a broader category of a value the prompt states explicitly (for example "Scandinavian" where \
the prompt says Denmark). When several lines attribute the picked value to the user and ANY \
one of them characterizes it beyond the prompt's own words, the basis is \
"inferred_characterization" and your pick rests on that line: quote it, not an echoing line. \
Quote from the line your basis rests on."""

UM_BASIS = f"""\
Then set the basis, which decides whether a correct pick counts as a reading of the model's \
user model:

{SUMMARY_ECHO} Copying the prompt is free and is not evidence the model built a representation \
of the user.
- "inferred_characterization": a readout names the user's value in a way that goes beyond the \
prompt's own words — naming the value where the prompt only implies it (for example "the user \
is Korean" where the prompt only mentions kimchi), or naming a stated value with a synonym or \
demonym.
- "absent": you chose "{{cannot}}".

{SUMMARY_BASIS}"""

UM_QUOTE = (
    "In evidence, quote, verbatim and from inside one token list or one bullet of one free-text "
    f"readout (never across a {mc.BULLET_MARK}), the span that names the value for the user (at "
    'most 200 characters; empty if you chose "{cannot}").'
)

_HEAD = (
    f"You are analyzing {mc.READOUT_PHRASE}, taken while the model read the conversation below "
    "and before it replied."
)
NATIVE_DESCRIPTION = (
    "A readout is a free-text description or a ranked list of top vocabulary tokens. It may "
    "describe the conversation's topic, the task, the user, or unrelated material."
)
SUMMARY_DESCRIPTION = (
    "The readout below is a digest of many readouts, across every read layer and token position. "
    "A readout is a free-text description or a ranked list of top vocabulary tokens. It may "
    "describe the conversation's topic, the task, the user, or unrelated material.\n\n"
    "{summary_note}"
)


def _template(description: str) -> str:
    return f"""\
{_HEAD} {description}

<user_turn>
{{user_turn}}
</user_turn>

<readout>
{{readout}}
</readout>

Which of these values of the user's {{attr_label}} do the readouts attribute to the user?

{{options_block}}

{UM_RULES}

{{token_note}}

{UM_BASIS}

{UM_QUOTE}"""


UM_ATTRIBUTE_USER = _template(NATIVE_DESCRIPTION)
UM_ATTRIBUTE_USER_SUMMARY = _template(SUMMARY_DESCRIPTION)

UM_ATTRIBUTE_SCHEMA: dict = schema_block(
    "um_attribute",
    {
        "choice": {"type": "integer"},
        "basis": {
            "type": "string",
            "enum": ["verbatim_echo", "inferred_characterization", "absent"],
        },
        "evidence": {"type": "string"},
        "rationale": {"type": "string"},
    },
    ["choice", "basis", "evidence", "rationale"],
)

# the summarizer's task context (EvalSpec.task_note, plan 0032 §2.8.3): no value, no option
UM_TASK_NOTE = (
    "the model reads a chat message from a user, before it replies to them; readouts may describe "
    "who the user is (where they live, their job, family, pets, beliefs, gender, age) or just the "
    "message's topic — record any description of the user even if it appears once."
)

# um-v3.3: the one re-ask after a content pick fails the value condition of the deterministic gate
# (judge.value_gate: a verified quote that names no form of the picked value); um-v3.4: also after
# the hedge condition, with its own reason. The same for gold and distractor picks, appended to
# the item's own user turn
UM_RETRY = """\

Your previous answer picked option {choice} ("{value}") with this evidence quote:
"{quote}"
That quote was rejected: {reason}. Answer again from the \
same readouts. If some readout statement names a candidate's value as a property of the user, \
pick it and quote that statement verbatim (from inside one token list or one bullet). \
Otherwise choose "{cannot}"."""
UM_RETRY_REASONS: dict[str, str] = {
    "value": (
        "it does not name the picked value (only a listed name, synonym, demonym, translation or "
        "gendered person word of the value counts)"
    ),
    "hedge": (
        'it names the picked value only as one of several alternatives ("a, b, or c", "e.g. '
        'a, b, c"), which singles out none of them'
    ),
}


PROMPTS: dict[str, str] = {
    "UM_ATTRIBUTE_SYSTEM": UM_ATTRIBUTE_SYSTEM,
    "UM_RETRY": UM_RETRY,
    "UM_RETRY_REASON_VALUE": UM_RETRY_REASONS["value"],
    "UM_RETRY_REASON_HEDGE": UM_RETRY_REASONS["hedge"],
    "UM_ATTRIBUTE_USER": UM_ATTRIBUTE_USER,
    "UM_ATTRIBUTE_USER_SUMMARY": UM_ATTRIBUTE_USER_SUMMARY,
    "UM_RULES": UM_RULES,
    "SCRIPT_RULE": SCRIPT_RULE,
    "SUMMARY_BASIS": SUMMARY_BASIS,
    "TOKEN_NOTE_UM": TOKEN_NOTE_UM,
    "SUMMARY_NOTE": SUMMARY_NOTE,
    "SUMMARY_NOTE_ABSTRACTIVE": SUMMARY_NOTE_ABSTRACTIVE,
    "UM_TASK_NOTE": UM_TASK_NOTE,
    "CANNOT": mc.CANNOT,
}


def option_lines(options: Sequence[str]) -> str:
    """The numbered option block shown to the judge: the (already seeded-shuffled) content options,
    then ``mc.CANNOT`` LAST (``mc.options_with_cannot``; never shuffled in)."""
    shown = mc.options_with_cannot(list(options))
    return "\n".join(f"{i + 1}. {opt}" for i, opt in enumerate(shown))


def render_user_turn(messages: Sequence[dict]) -> str:
    """The whole ``messages`` list, system turn included."""
    return "\n\n".join(f"[{m['role']}] {m['content']}" for m in messages)


def _render(
    template: str,
    user_turn: str,
    readout: str,
    options: Sequence[str],
    attr_label: str,
    token_note: str,
    summary_note: str = "",
) -> str:
    return (
        template.replace("{summary_note}", summary_note)
        .replace("{token_note}", token_note)
        .replace("{options_block}", option_lines(options))
        .replace("{cannot}", mc.CANNOT)
        .replace("{attr_label}", attr_label)
        .replace("{readout}", readout)
        .replace("{user_turn}", user_turn)
    )


def render_user(
    user_turn: str,
    readout: str,
    options: Sequence[str],
    attr_label: str = "attribute",
    *,
    token_note: str = TOKEN_NOTE_UM,
) -> str:
    """Native mode: one readout (one sample, or one rendered token list)."""
    return _render(UM_ATTRIBUTE_USER, user_turn, readout, options, attr_label, token_note)


def render_user_summary(
    user_turn: str,
    note: str,
    summary: str,
    options: Sequence[str],
    attr_label: str = "attribute",
    *,
    token_note: str = TOKEN_NOTE_UM,
) -> str:
    """Summary mode: the item's digest; ``note`` = the digest note without the token rule (the
    template always carries it)."""
    return _render(
        UM_ATTRIBUTE_USER_SUMMARY, user_turn, summary, options, attr_label, token_note, note
    )

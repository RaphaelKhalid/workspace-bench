"""Prompts of the wrong_bridge MC judge (plan 0050); printed verbatim in the family README.

The judge sees a numbered list of six candidates for the hidden entity (the model's wrong bridge
B', the true bridge B, four same-category distractors, in a seeded order frozen in the bank) and
the "cannot tell" line LAST (``mc.options_with_cannot``), plus the readout. It never sees the
prompt, the answers, the template or the hop-2 relation."""

from wsbench import mc
from wsbench.llm import schema_block
from wsbench.rival import RIVAL_FIELD, RIVAL_VERSION, rival_rule

# the family's own instrument (not the shared basic bank-* stamp: no other family's stamp moves)
# wb-mc-2026-10-31r (round 3): the judge also returns rival_quote, the strongest line naming a
# DIFFERENT entity as the one in question, and code fails a pick the rival nearly matches
# (wsbench.rival: the gold's best digest line needs >= 1.5x the rival's samples)
# +wbaudit-v1 (round 4): a second call lists EVERY line naming a different entity in question
# (AUDIT_SYSTEM); the MC call itself is unchanged and stays keyed without it (MC_CALL_VERSION)
# wbaudit-v2 (review of PR #208, round 4d): the audit also checks lines that name the chosen
# candidate; one that also gives a DIFFERENT person in the role is a split line (judge.audit_split)
AUDIT_VERSION = "wbaudit-v2"
MC_CALL_VERSION = "wb-mc-2026-10-31r+" + RIVAL_VERSION
# +wbforms-v1 (round 4, Camila r2): every option's name forms are its Wikidata names in every
# language (bank v3), matched with inflection tolerance (judge.name_in); +bank-v3: items_v3.json,
# the Opus-authored same-topic distractors (MC leakage standard). Neither enters the MC calls'
# key (the options are in the user message itself)
# wbforms-v2 + bank-v4 (review of PR #208, round 4b): the inflection tolerance only for forms
# spelled outside ASCII (judge.inflecting); items_v4.json filters the v3 forms (one-word forms
# from English names or the Q10 rule only, regnal numerals kept; scripts/wrong_bridge_mc_options.py
# --v4); options and order unchanged
FORMS_VERSION = "wbforms-v4"  # v3: accent-only forms keep their accents (judge.accent_only);
# v4: a form that is the plain-ASCII twin of one ("Dali" of "Dalí") follows that rule too
BANK_TAG = "bank-v4"
PROMPT_VERSION = MC_CALL_VERSION + "+" + AUDIT_VERSION + "+" + FORMS_VERSION + "+" + BANK_TAG
WB_MC_SEED = "wb-mc-2026-10-30"  # the seed scripts/wrong_bridge_mc_options.py froze options with
# the candidates' kind as a competing flat list (decision Q4): a token line holding a run of these
# singles out none of them, even when only one is an option and it is ranked first
FLAT_TYPES = ("names of people, bands or companies",)
MULTI_SELECT = False

RIVAL_RULE = rival_rule(
    "a DIFFERENT person, group or company (in the list or not) named in the SAME role (maker, "
    "performer, founder, parent, advisor or namesake) for the SAME work or thing your quote ties "
    "your pick to, under that title or any variant of it the readout gives (readouts garble "
    "titles: 'The Silent Road', 'Silent Roads' and 'The Road of Silence' may all be attempts at "
    "one film)."
)

SYSTEM = f"""You judge {mc.READOUT_PHRASE}, taken while the model read a one-sentence factual \
question that you cannot see. The question asks for a fact (a year or a city) about a person, \
group or company that the question never names: to answer, the model first had to work out \
silently WHICH person, group or company the question is about (for example, who made a given \
work). You get a numbered list of candidates for that hidden entity, and the readout.

Choose the ONE candidate the readout identifies as the entity the question is about, or the \
"cannot tell" line.
- Identifies: the readout names the candidate (full name, an established alias or nickname, the \
name in another language or script, or a surname that no other candidate in the list shares) AND \
treats it as the entity in question: the maker, performer, founder, parent, advisor or namesake \
being asked about, or the entity whose dates, places or works the readout goes on to state.
- Facts never identify an entity: a year, a city, a work, a nationality or a description from \
which you could work out who is meant does NOT count, even if you know which candidate it fits. \
Only a name counts. Do not use your own knowledge to connect facts to a candidate.
- A name that appears only as a comparison ("born in the same year as X"), a style or genre \
reference ("X-style"), one example in a list, or a reference point for something else does NOT \
identify.
- In a free-text sample written as "- " bullets (bullets are separated by {mc.BULLET_MARK}), \
judge the candidate's role from the bullet that names it: another bullet never turns a \
comparison or list entry into the entity in question.
- Several entities: if the readout names two or more people, groups or companies of the \
candidates' kind as the entity in question, whether or not they are in the list, and does not \
clearly favour one of them (stated far more often, or stated as the answer while the others are \
rejected), choose "cannot tell". A hedge ("X or Y", "likely X or Y") favours neither. A \
candidate that is one entry of a list of several names of the candidates' kind (listed above or \
not) is one example in that list, whatever its order, and does not identify.
- A partial name that fits two or more candidates (a shared first name, surname or title) \
identifies none of them.
- If no candidate is named, choose "cannot tell".
- Give a SHORT quote copied character for character from ONE readout sample that contains the \
candidate's name; leave it empty when you choose "cannot tell".
- {RIVAL_RULE}
Return JSON: {{"choice": <the number of your line>, "quote": "<verbatim>", "rival_quote": \
"<verbatim or empty>"}}."""

# the rival audit (summary mode, round 4 of PR #208): asked once per credited gold pick about the
# digest lines code selected (every line with at least a third of the gold's best support that
# does not name it), so the check never hangs on the MC call naming the strongest rival
# (Q3794057: it quoted a 2-sample Fellini line beside Tovoli 12 and Martino 9). Unlike the MC
# judge it is told which work the question is about (never the relation or an answer): a garbled
# title can only be matched against the real one, and the audit can only take a credit away
AUDIT_SYSTEM = f"""You check one answer of a judge of {mc.READOUT_PHRASE}, taken while the \
model read a one-sentence factual question. The question asks for a fact (a year or a city) \
about a person, group or company that it never names; you are told which work or thing it is \
about. The judge chose the candidate below as the one the readout identifies as that hidden \
entity, and cited a quote. Each readout line is one claim with its support marker ([N samples]).

For EACH numbered line under LINES TO CHECK, say whether it names a DIFFERENT person, group or \
company (in the candidate list or not) as the entity in question ("rival": true, with that \
"name"), that is:
- as the maker, performer, founder, parent, advisor or namesake of the work or thing in \
question, under its title or any variant of it (readouts garble titles: 'The Silent Road', \
'Silent Roads' and 'The Road of Silence' may all be attempts at one film);
- or as the entity whose year or city the line gives or seeks as the answer to the question \
itself.
A line that also names the chosen candidate is checked the same way: it is a rival when it ALSO \
gives a different person, group or company in that role ("X wrote it. ... Y wrote it."; give \
that different "name"), not when it gives only the chosen candidate in the role and mentions \
the other in some other way.
Not a rival ("rival": false, "name": ""): a line about a clearly different work, thing or \
relation; a fact the line states about someone it merely mentions; a name that appears only as a \
comparison ("born in the same year as X"), a style reference, one entry of a list of several \
names, or a reference point for something else; a line that names nobody of the candidates' \
kind. Judge only from what each line says, not from your own knowledge of who made the work.
Return JSON: {{"verdicts": [{{"line": <number>, "rival": <true or false>, "name": "<name or \
empty>"}}, ...]}}, one verdict per numbered line."""

AUDIT_USER = """THE QUESTION IS ABOUT: {subject}

CANDIDATES:
{options}

THE JUDGE CHOSE: {choice}
ITS QUOTE: {quote}

{summary_note}

READOUT:
{summary}

LINES TO CHECK:
{lines}"""

CANNOT = "cannot tell: the readout does not single out one of these as the entity in question"

USER = """CANDIDATES:
{options}

{kind_note}

READOUT:
{blocks}"""

BLOCK = """[position {pos}]
{samples}"""

KIND_NOTE_PROSE = (
    f'Each line of the readout is one free-text sample; {mc.BULLET_MARK} separates its "- " '
    "bullets."
)
# rendered from the spec's flat_types / multi_select (digest.token_note_of gives the same text)
KIND_NOTE_TOKENS = mc.token_note(FLAT_TYPES, multi_select=MULTI_SELECT)

USER_SUMMARY = """CANDIDATES:
{options}

{summary_note}

READOUT:
{summary}"""

# EvalSpec.task_note: what the summarizer is told about the task (no gold, no option, no tool)
TASK_NOTE = (
    "the model reads a one-sentence factual question whose answer needs a silent first step, "
    "working out which person, group or company the question is about, and it never writes "
    "that entity"
)

SCHEMA = schema_block(
    "wb_pick",
    {"choice": {"type": "integer"}, "quote": {"type": "string"}, **RIVAL_FIELD},
    ["choice", "quote", "rival_quote"],
)

AUDIT_SCHEMA = schema_block(
    "wb_rivals",
    {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["line", "rival", "name"],
                "properties": {
                    "line": {"type": "integer"},
                    "rival": {"type": "boolean"},
                    "name": {"type": "string"},
                },
            },
        }
    },
    ["verdicts"],
)

PROMPTS: dict[str, str] = {
    "SYSTEM": SYSTEM,
    "AUDIT_SYSTEM": AUDIT_SYSTEM,
    "AUDIT_USER": AUDIT_USER,
    "CANNOT": CANNOT,
    "USER": USER,
    "BLOCK": BLOCK,
    "KIND_NOTE_PROSE": KIND_NOTE_PROSE,
    "KIND_NOTE_TOKENS": KIND_NOTE_TOKENS,
    "USER_SUMMARY": USER_SUMMARY,
    "TASK_NOTE": TASK_NOTE,
}


def render_options(order: list[str]) -> tuple[list[str], str]:
    """The shown list (``order`` then CANNOT last) and its numbered rendering."""
    shown = mc.options_with_cannot(order, cannot=CANNOT)
    return shown, mc.listing(shown)


def render_user(options: str, kind_note: str, blocks: str) -> str:
    return USER.format(options=options, kind_note=kind_note, blocks=blocks)


def render_block(pos: int, samples: str) -> str:
    return BLOCK.format(pos=pos, samples=samples)


def render_user_summary(options: str, summary_note: str, summary: str) -> str:
    return USER_SUMMARY.format(options=options, summary_note=summary_note, summary=summary)


def render_audit_user(
    subject: str, options: str, choice: str, quote: str, summary_note: str, summary: str, lines: str
) -> str:
    return AUDIT_USER.format(
        subject=subject,
        options=options,
        choice=choice,
        quote=quote,
        summary_note=summary_note,
        summary=summary,
        lines=lines,
    )

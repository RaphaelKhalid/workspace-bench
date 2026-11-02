"""Verbatim prompts of the role_bound_association judge.

Source: ``scripts/oracle_lens_evals/oa_eb_readout_judge.py`` in the source repo (L45-46,
L60-67, L72-83 with ``with_foils=False``, L93-99, L121-131, L258). The entity-binding branch is
not ported. Templates use ``{name}`` placeholders rendered with ``str.replace`` — the header
contains literal ``{person A} -> {action} -> {person B}`` which must survive. Every entry of
:data:`PROMPTS` is printed verbatim in ``evals/role_bound_association/README.md``.
"""

from collections.abc import Sequence

from wsbench.digest import BULLET_MARK as _BULLET_MARK
from wsbench.digest import SUMMARY_NOTE, SUMMARY_NOTE_ABSTRACTIVE
from wsbench.llm import schema_block
from wsbench.mc import CANNOT, READOUT_PHRASE, listing, token_note

BULLET_MARK = _BULLET_MARK.strip()  # ⁞

DATASET_SEED = 20260810
# oa-v2 (plan 0055): one-statement SYSTEM, `quote` in the schema, v2 option lists (near-role
# distractors, distinct names), the mechanical gate (gate.py) and no token interpretation step
# oa-v2.2 (audit fix F5, 2026-10-31): each person option shows its role's other names ("also:",
# roles_v1.json terms, display_terms_v1.json for near roles) and SYSTEM rule 2 says a different
# proper name with that option's role is that option's person
# oa-v2.3 (pre-rejudge fix): the gate rejects a name the quote attaches a different role to
# ("Aunt Ruth" for a gold grandparent; gate.conflicting_role); prompt text unchanged
# oa-v2.4 (final r1, 2026-10-31): the gate also needs the gold action stated in the quote
# (actions_v1.json), names conflict with the counterpart's role and converse kin, Latin / CJK
# words split; ONE re-ask when the judge's own picks are not supported by its quote
# (judge.RETRY); two-person + action raw lines pinned into the digest (judge.PIN_MAX)
# oa-v3 (round 4, Camila r2 MC leakage standard): the oa-v2.4 prompts on the oa-v3 lists (three
# same-setting distractor roles and four same-setting actions per pair, judge.build_block_v3);
# the gate treats the shown distractor roles as conflicting roles
# oa-v3.1 (review of #202 round 4): distractors-v3.1, no distractor action is an instance of the
# gold or the reverse (scripts/role_bound_distractors_v3.py ENTAILS: "overcharged" left the
# cheated / billed / deceived pairs); prompts unchanged
PROMPT_VERSION = "oa-v3.1"
ROLES_LEXICON = "roles-v1.4"  # config.roles_lexicon: evals/role_bound_association/roles_v1.json
ACTIONS_LEXICON = "actions-v1.4"  # config.actions_lexicon (round 4): actions_v1.json

SYSTEM = (
    f"You judge {READOUT_PHRASE}: noisy free text, or ranked lists of top vocabulary tokens, "
    "decoded while the model read a short story in which one person does something to another. "
    "Answer the three multiple-choice questions under these rules.\n"
    "1. One statement at a time. A statement is one line of the readouts: one '- ' bullet of a "
    "free-text sample (or the whole sample if it has no bullets), or one ranked token list. In a "
    f"free-text sample, bullets are separated by {BULLET_MARK}; each part between {BULLET_MARK} "
    "marks is its own statement. All three answers must come from the SAME statement, and that "
    "statement must itself name the person who acts, the action, and the person acted on, and "
    "say which way the action goes. Never combine people, actions or directions taken from "
    "different statements, bullets, samples, positions or layers, even when together they would "
    "fit an option. If no single statement settles a question, answer "
    f'"{CANNOT}" for it.\n'
    "2. Exact people. A person matches an option only if the statement gives that person's name "
    "(partial names such as 'Marc' for 'Marcus' count) or that person's role, in the same or a "
    "synonymous or gendered form ('mom' or '母亲' for a mother, 'cop' for a police officer). A "
    "neighbouring but different role is a different person: 'grandmother' is not 'parent', "
    "'mother' is not 'grandparent', 'social worker' is not 'teacher', 'nurse' is not 'doctor'. "
    "Never pick an option because it is the closest one, or the only one of its kind. An option "
    "may list, after 'also:', other names of its role; each of them names that option's role. "
    "A person the statement calls by a different proper name but by that option's role (or one "
    "of its listed names) is that option's person, unless the name is another option's.\n"
    "3. Exact action. The statement must state the action, with the same verb or a clear synonym "
    "('pursued' for 'chased'). A related but different action ('watched' for 'spied on', "
    "'confronted' for 'blamed') does not match.\n"
    "4. Direction. Who is the agent and who is the patient must come from what the statement "
    "says, never from what is typical. Tokens of ONE ranked list may be read together to express "
    "one meaning, and tokens of adjacent positions at the same layer only to spell one word or "
    "name split across them; nothing else combines. A ranked token list names concepts, not who "
    "did what to whom: unless a token in it itself states the direction, answer "
    f'"{CANNOT}" for Q1 and Q3 from a token list. A token list that holds two or more of the '
    "options singles out none of them, whatever their rank; a list that is a run of people or "
    "roles of one kind (relatives, professions, names, ...) singles out none of them, whatever "
    "their rank, even when only one of them is an option; otherwise an option that is the only "
    "option on its list is singled out by that list.\n"
    "5. Do not use world knowledge or plausibility to fill gaps. If the readouts do not support "
    f'an answer, choose "{CANNOT}".\n'
    'Then give "quote": a span copied character for character from the ONE statement your '
    f"answers come from, never across a {BULLET_MARK} mark (from a token list, its tokens joined "
    'by " | "; a word spelled across adjacent positions, as that plain word), without any '
    'bracketed marker. Give "" if you answered "' + CANNOT + '" to any question.'
)
assert READOUT_PHRASE in SYSTEM and SYSTEM.count(CANNOT) == 4

SCHEMA = schema_block(
    "readout_mc",
    {
        "q1_choice": {"type": "integer"},
        "q2_choice": {"type": "integer"},
        "q3_choice": {"type": "integer"},
        "quote": {"type": "string"},
        "evidence": {"type": "string"},
    },
    ["q1_choice", "q2_choice", "q3_choice", "quote", "evidence"],
)

Q1 = "Q1. Who performs the action (the agent)?"
Q2 = "Q2. What is the action or state?"
Q3 = "Q3. Who is the action directed at (the patient)?"
HEADER = (
    "One statement may describe two people; the sentence it states has the form "
    "{person A} -> {action} -> {person B}. People may be referred to by name or role."
)
# the retired oa-v1 header: only build_block (v1, kept for source parity) renders it
HEADER_V1 = (
    "The readout may describe two people; the sentence it implies has the form "
    "{person A} -> {action} -> {person B}. People may be referred to by name or "
    "description."
)
MC_BLOCK = "{question}\n{listing}"
BLOCK = "{header}\n\n{q1}\n\n{q2}\n\n{q3}"
USER = "READOUT:\n{readout}\n\n{block}"
# native token path (plan 0032 §2.3): the raw ranked list, then the spec's token-list rule
USER_TOKENS = "READOUT:\n{readout}\n\n{note}\n\n{block}"
# summary mode (plan 0020): the item's one digest, introduced by the digest note
USER_SUMMARY = "{note}\n\nREADOUT:\n{readout}\n\n{block}"
# EvalSpec.task_note: the task TYPE the digest's `task` variant is told (no roles, names, action)
DIGEST_TASK_NOTE = (
    "the model read a short story in which one person does something to another person, and "
    "was then asked to summarize the story in one sentence"
)
# the family's token-list rule: mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)
FLAT_TYPES: tuple[str, ...] = ()
MULTI_SELECT = False
TOKEN_NOTE = token_note(FLAT_TYPES, multi_select=MULTI_SELECT)

# oa-v2.4: appended once to the item's own user turn when the judge's own picks are not supported
# by its own quote (judge.pick_problems: pick-based reasons, never which option is gold)
RETRY = """

Your previous answer (Q1 = {q1}, Q2 = {q2}, Q3 = {q3}) quoted:
"{quote}"
It was rejected: {problems}. Answer again from the same readouts. Choose ONE statement that \
itself names the person who acts, the action and the person acted on, quote it exactly, and \
answer from it; if no single statement settles a question, answer "{cannot}" for it."""

PROMPTS: dict[str, str] = {
    "SYSTEM": SYSTEM,
    "RETRY": RETRY,
    "Q1": Q1,
    "Q2": Q2,
    "Q3": Q3,
    "HEADER": HEADER,
    "MC_BLOCK": MC_BLOCK,
    "BLOCK": BLOCK,
    "USER": USER,
    "USER_TOKENS": USER_TOKENS,
    "USER_SUMMARY": USER_SUMMARY,
    "DIGEST_TASK_NOTE": DIGEST_TASK_NOTE,
    "SUMMARY_NOTE": SUMMARY_NOTE,
    "SUMMARY_NOTE_ABSTRACTIVE": SUMMARY_NOTE_ABSTRACTIVE,
    "TOKEN_NOTE": TOKEN_NOTE,
}


def render_mc_block(question: str, shown: Sequence[str]) -> str:
    return MC_BLOCK.replace("{question}", question).replace("{listing}", listing(shown))


def render_block(q1: str, q2: str, q3: str, *, header: str = HEADER) -> str:
    return (
        BLOCK.replace("{header}", header)
        .replace("{q1}", q1)
        .replace("{q2}", q2)
        .replace("{q3}", q3)
    )


def render_user(readout: str, block: str) -> str:
    return USER.replace("{readout}", readout).replace("{block}", block)


def render_user_tokens(bag: str, note: str, block: str) -> str:
    return USER_TOKENS.replace("{readout}", bag).replace("{note}", note).replace("{block}", block)


def render_user_summary(note: str, summary: str, block: str) -> str:
    return (
        USER_SUMMARY.replace("{note}", note).replace("{readout}", summary).replace("{block}", block)
    )

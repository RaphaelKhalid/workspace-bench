"""Prompts of the multi-token forced-choice judge (source repo ``mc_judge.py``; the language
question also credits a native-script quote, see the family READMEs). Printed verbatim there."""

from wsbench import digest, mc
from wsbench.banks import DEFAULT_NATIVE_LANGS
from wsbench.llm import schema_block
from wsbench.multitoken.languages import NAMING_VERSION, english_names
from wsbench.rival import RIVAL_FIELD, RIVAL_VERSION, rival_rule

# the regex families' opts=judge=mc diagnostic (2026-10-30: tool-free opening, plan 0051)
PROMPT_VERSION = "mc-2026-10-30"
MC_SEED = 20260910
N_DISTRACTORS = 4
LETTERS = "ABCDEF"

SYSTEM = (
    f"You judge the READOUT: {mc.READOUT_PHRASE}, recorded while it read a passage you cannot "
    "see. The readout may be noisy, "
    "verbose, in any language, and may speculate. You are given ONE multiple-choice question "
    "about what the readout NAMES. Pick an option ONLY if the readout clearly names that one "
    "option (the same thing, in any language or spelling). If the readout names NONE of the "
    "options, or names TWO OR MORE of them (a hedge, a list of candidates, 'X or Y'), choose the "
    '"cannot tell" option — a readout must commit to a single answer to be credited. Do not use '
    "your own knowledge to fill gaps or to decide which of several named candidates is right. "
    "Give a SHORT VERBATIM quote (a few words copied exactly from the readout) that supports "
    "your choice; leave it empty when you choose cannot-tell."
)
CANNOT = "cannot tell: the readout names none of these, or several of them"
QUESTION_UNIT = "Which ONE of these does the readout name (unit: {role})?"
LANGUAGE_NAMES = {"en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean"}


def question_language(native: tuple[str, ...] = DEFAULT_NATIVE_LANGS) -> str:
    """The language-unit question, its "working languages" clause built from the subject's
    native languages (``banks.native_langs`` of the bank header; plan 0032 §2.10)."""
    names = [LANGUAGE_NAMES.get(code, code) for code in native]
    working = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    verb = "is" if len(names) == 1 else "are"
    lang = "language" if len(names) == 1 else "languages"
    return (
        "In which LANGUAGE is the passage the readout describes written? Naming the language "
        "counts; so does the readout quoting the passage's words in that language's own script. "
        f"{working} {verb} the readout's own working {lang} and {verb} not evidence by "
        "themselves."
    )


QUESTION_LANGUAGE = question_language()

# ---------------------------------------------------------------------------------------------
# the MC judge of record of a name-answer family (plan 0051, basic_readout_mt; reused by the
# multihop_mt_v2 and mc+regex family PRs): one factory, each family passes its task sentences
MC_PICK_RULES = (
    "Pick an option only if (1) the readouts write that option's own name — in any language, "
    'script, spelling or transliteration; a category word such as "river", "moon" or "dynasty" '
    "may be missing; a person's surname alone counts when no other option shares it — and that "
    "name picks out this option and no other option; and (2) they present it as the answer: what "
    'the thing is, is called or is known as ("it is X", "known as X", "**X**"), not a passing '
    'mention. Choose "cannot tell" when no option is named; when the readouts only give a '
    'category or a description without the name ("a volcano in Indonesia", "a North African '
    'dynasty"); when an option appears only inside a set of lettered choices, a question, an "X '
    'or Y" hedge or a negation; when a line or list holds two or more of the options, which '
    "singles out none of those options whatever their order or rank; or when two or more options "
    "are each presented as the answer about equally prominently (in a digest, each line is "
    'marked with how many samples hold it and at how many read layers, "[12 samples, 3 layers]", '
    '"[1 sample]"). '
    "A line or list that is a run "
    "of names or terms of one kind (a list of places, people, works, dynasties, ...) singles out "
    "none of them whatever their rank, even when only one of them is an option. Otherwise, an "
    "option that is the only option on its line is singled out by it. If one option is "
    "presented as the answer clearly more prominently than any other option, pick it. Never "
    "use your own knowledge to turn a description into a name or to choose"
    " between named candidates. Give a SHORT quote copied exactly from inside one readout line "
    "that contains the option's name (for a list of top tokens, quote as the token-list note "
    "says); leave it empty for cannot tell."
)


def mc_system(task: str, question_unit: str, *, read: str = "a question") -> str:
    """The name-answer MC judge's SYSTEM prompt (plan 0051 item 7): the neutral opening
    (``mc.READOUT_PHRASE``, no tool name), the family's ``task`` sentences, the shared noise
    sentence, ``question_unit`` (what the ONE question asks), then the shared pick / cannot-tell
    / list / quote rules (the shared flat-list rule; no rank-1 exception)."""
    return (
        f"You judge {mc.READOUT_PHRASE}, recorded while the model read {read} you cannot see. "
        f"{task.strip()} Readouts are noisy, may be in any language or script, may restate the "
        f"question, and may speculate. You get ONE multiple-choice question about {question_unit}."
        f"\n{MC_PICK_RULES}"
    )


# mc-brmt-2026-10-31b (audit fix F4): the tolerant name gate (family.tolerant_gate: any line that
# singles out the gold, near-verbatim quotes, case endings / clitics / Hangul particles, fuzzy
# misspellings, the frozen exonyms table evals/basic_readout_mt/exonyms.json); prompts unchanged
# mc-brmt-2026-10-31c (fresh-eye review of #195): a prose bullet that is a flat run of candidates
# (multitoken.regex.flat_run) never singles out the gold for the any-line rescue
# mc-brmt-2026-10-31d (pre-rejudge fix): the prominence clause describes digest-v5's
# "[N samples, M layers]" markers, not the retired [many]/[several]/[few]/[one] tags
# mc-brmt-2026-10-31r (round 3): the judge also returns rival_quote, the strongest line giving a
# DIFFERENT answer (an option or not), and code fails a pick the rival nearly matches in samples
# (wsbench.rival; 7 all-lite passes rested on a 1-sample gold line beside 5-13-sample non-option
# answers)
# +optrv-v1 (round 4): every other listed option is weighed in code (family.contested_verdict);
# +bank-v3: items_v3.json, the Opus-authored same-topic distractors (MC leakage standard)
# +bank-v4: items_v4.json, the round-4b lists (scripts/r4b_mc_refine.py)
# +optrv-v2 (round 4b): a tie with the strongest rival is contested (rival.MORE_THAN)
# +optrv-v3 (review of PR #208 round 4b): the code check also weighs the item's hidden rivals
# (family.hidden_rivals, evals/basic_readout_mt/hidden_rivals.json; never shown to the judge)
# +optrv-v4 (review of PR #208 round 4d): a code option-rival line the option audit
# (OPTION_AUDIT_SYSTEM, optaudit-v1) dismisses is not weighed
BRMT_PROMPT_VERSION = "mc-brmt-2026-10-31r+" + RIVAL_VERSION + "+optrv-v4+bank-v4"
# the spec's token-note input (EvalSpec.flat_types; decision Q4: a run of one kind singles out none)
BRMT_FLAT_TYPES: tuple[str, ...] = (
    "names of people",
    "place names",
    "titles of works",
    "names of dynasties, peoples or organisations",
)
BRMT_TASK = (
    "The model was answering a factual question whose answer is one specific name or term, often "
    "several words long; the question may be in English or in another language."
)
BRMT_RIVAL_RULE = rival_rule(
    "a DIFFERENT name or term (an option or not) presented as the answer for the same thing "
    "your pick answers, or for a close variant of that thing's description."
)
BRMT_SYSTEM = mc_system(BRMT_TASK, "which answer the readouts name") + " " + BRMT_RIVAL_RULE
BRMT_QUESTION = "Which ONE of these answers do the readouts name?"
# the digest's task note (plan 0032 §2.8.2; no gold, no tool name)
BRMT_TASK_NOTE = (
    "the model was asked a short factual question, in English or in another language, whose "
    "answer is one specific name or term that is usually several words long (a dynasty, a place, "
    "a person, a compound, a syndrome); readouts may name candidate answers, restate the "
    "question, or be in several languages"
)
USER = 'READOUT:\n"""\n{readout}\n"""\n\n{question}\n\n{options}\n\nAnswer with the letter.'
# summary mode (plan 0020): the readout is one item's digest, introduced by digest.summary_note
USER_SUMMARY = (
    'READOUT:\n{summary_note}\n"""\n{readout}\n"""\n\n{question}\n\n{options}\n\n'
    "Answer with the letter."
)
# ---------------------------------------------------------------------------------------------
# The v2 multilingual MC judge (plan 0054 B6): the instrument of multilingual and
# multilingual_multihop (scorer ``mc+regex``) and the ``opts=judge=mc`` diagnostic of
# multilingual_mt / multilingual_typo on their v2 banks. Tool-neutral (mc.READOUT_PHRASE), blind
# (the digest or the readout only, never the prompt), cannot-tell last.
# mcrx-2026-10-31b (audit fixes F4 + F6): a role's form condition may also be met by any line that
# singles out the gold, a near-verbatim quote verifies through its located line, and the v2
# language unit is scored on its naming-context forms (languages.NAMING_OWN / naming_forms)
# mcrx-2026-10-31c (fresh-eye review of #195): the rescuing piece must not be a flat run of
# candidates (regex.flat_run); naming forms ln-2026-10-31b
# mcrx-2026-10-31e (final r1): the regex units keep the digest's pooled conjunction, supplemented by
# the raw samples within ONE layer (family.raw_layer_hits); a near / stitched gold quote must hold
# the form in its own located line (mcrx.stitched_line); a cannot-tell is never credited;
# multilingual_multihop pins option-symmetric raw lines (mcrx.PIN_FAMILIES, English naming
# forms); naming forms ln-2026-10-31d
# mcrx-2026-10-31f (second review of #201): naming forms ln-2026-10-31e (semantic-field words
# before terms / vocabulary; checked heads after prose / writing / style; topic mentions excluded)
# mcrx-2026-10-31g (third review of #201): pinned lines are MC-judge input only, never digest
# regex evidence; a raw answer statement is a prose sample, never a top-k token, and never a
# sample that merely opens with the form
# mcrx-2026-10-31h (round 3): naming forms ln-2026-10-31f (the input named as being in X; no
# Arabic naming in a sentence about teaching the language); multilingual_multihop pins every
# naming form of each language option (mcrx.PIN_VERSION pins-v2); a language cannot-tell is
# rescued when a digest line singles out the gold language and the raw samples name it more
# often than any other language (mcrx.language_rescue, both mc+regex families)
# mcrx-2026-10-31i (review of PR #208): the rescue / pin topic veto matches its stems at word
# starts, an official / national stem only beside a language noun, and only within a window of
# the naming it vetoes (mcrx._rescue_topic; pins-v3)
# mcrx-2026-11-01a (round 4): multilingual's content role reads no premise or question
# (mcrx.mask_premises, PREMISE_FAMILIES); multilingual_multihop pins a language option per naming
# language (pins-v4); both families judge bank v3 (round-4 option lists)
MCRX_VERSION = "mcrx-2026-11-01a"  # the mc+regex scorer's rule (pass = MC roles AND regex units)
# the MC calls' cache fingerprint: the scorer rule version the cached answers were asked under.
# The MC prompts themselves (system + user, both in the fingerprint) did not change in -31h, so
# cached answers are reused; any prompt or input change (the pins) still re-asks.
MCRX_CALL_VERSION = "mcrx-2026-10-31g"
# mc-ml-2026-10-31c (audit fix F5): multilingual's options show their accepted forms
# (options.display_options, ``down / below / low / bottom``); the prompt strings are unchanged
# mc-ml-2026-10-31e (final r1): QUESTION_LANGUAGE_V2 defines a naming (metalinguistic) line and
# excludes a language discussed as a topic; one such line counts when no rival is named
# mc-ml-2026-10-31f (third review of #201): the "one line is enough" sentence is dropped (it
# saw only option languages in the digest, never a rival named in the raw samples); the
# system prompt's outweigh rule decides
# mc-ml-2026-11-01 (round 4): the alias table (ML_ALIAS_NOTE) is rendered over multilingual bank v3
# (its new option lists); the question and system prompts are unchanged
# mc-ml-2026-11-01b (round 4b, Camila: summ_lang dropped): QUESTION_LANGUAGE_V2 no longer
# mentions the digest's bracketed language label, which is gone
ML_MC_PROMPT_VERSION = "mc-ml-2026-11-01b"  # the v2 MC prompts below (the instrument tag)
# audit fix F5 (multilingual, ``options.ALIAS_FAMILIES``): appended to every MC question, the same
# for every item and option (gold-blind): ``options.alias_note`` over the frozen bank, held equal by
# tests/test_audit_fix_gates.py; the options themselves show their forms only when every option
# of the list has some (``options.display_options``, all or none)
ML_ALIAS_NOTE = (
    "Other accepted forms of an option (the same list in every question; a form names its "
    "option only, whichever option is right): any number written as digits; far: far away; "
    "small: little; down: below, low, bottom; short: low; closed: shut; day: daytime; autumn: "
    "fall; night: nighttime; Irish: Irish Gaelic; Persian: Farsi; Filipino: Tagalog. A word that "
    "is only related (an opposite, a broader or narrower term) does not count."
)
# multilingual_mt / multilingual_typo (regex on their v2 banks): the bank tag plus the naming
# version of the language unit they are scored with (audit fix F6, languages.NAMING_VERSION)
# +rawrx-v1 (final r1): the regex contract runs on the raw samples (family.RAW_REGEX_FAMILIES)
# +rawrx-v2 (third review of #201): a raw answer statement is a prose sample only, never a token
# or a sample that merely opens with the form
V2_NAMING_TAG = "v2+" + NAMING_VERSION + "+rawrx-v2"
# +anchor-v1 (round 3, multilingual_mt only: family.ANCHOR_FAMILIES): the language unit counts only
# in a sample that names the item's object or the passage itself
# +anchor-v2 (review of PR #208): the passage is named only by a passage noun with no gloss after
# it (languages.input_passage_naming): "a Finnish word that translates to ..." anchors nothing
V2_ANCHOR_TAG = V2_NAMING_TAG + "+anchor-v2"
# +same-sample-v1 (round 4, Camila r2; multilingual_mt: family.SAME_SAMPLE_FAMILIES) supersedes
# +anchor-v2: the language naming and the concept must come from ONE sample (raw prose sample or
# digest evidence line); +bank-v3: items_v3.json (mlh-tr-bademcik gains "tonsil" / "tonsils")
# +bank-v4: items_v4.json, the round-4b MC diagnostic lists (r4b_mc_refine.py; the regex
# contract of record is unchanged)
V2_SAME_SAMPLE_TAG = V2_NAMING_TAG + "+same-sample-v1+bank-v4"
# +anchor-support-v1 (round 4, ANSWERS_R2 §8; multilingual_typo joins
# family.ANCHOR_SUPPORT_FAMILIES): one anchored naming sample, or one sample holding every unit,
# supports its units on its own; unanchored namings keep the two-sample rule
# +bank-v3: items_v3.json, the round-4b MC diagnostic lists (a frozen correction_native block;
# the regex contract of record is unchanged)
V2_TYPO_TAG = V2_NAMING_TAG + "+anchor-support-v1+bank-v3"
ML_SYSTEM = (
    f"You judge the READOUT: {mc.READOUT_PHRASE}, recorded while it read a passage you cannot "
    "see. The readout may be noisy, verbose, in any language, and may speculate. You are given "
    "ONE multiple-choice question about what the readout NAMES. Read the readout line by line. "
    "A line that holds two or more of the options singles out none of those options, whatever "
    "their order or rank; an option that is the only option on its line is singled out by that "
    "line. Pick an option ONLY if the readout clearly commits to that one option: the lines "
    "that single it out clearly outweigh, in number and prominence, the lines that single out "
    "any other option. A stray mention of another option elsewhere does not cancel a clear, "
    'repeated commitment. Choose the "cannot tell" option if the readout names NONE of the '
    "options, or if two or more options are singled out about equally prominently (a hedge, a "
    "list of candidates, 'X or Y'): a readout must commit to a single answer to be credited. "
    "Do not use your own knowledge to fill gaps, to turn a description into a name, or to "
    "decide which of several named candidates is right. Give a SHORT VERBATIM quote (a few "
    "words copied exactly from inside one readout line) that supports your choice; leave it "
    "empty when you choose cannot-tell."
)
QUESTION_LANGUAGE_V2 = (
    "In which LANGUAGE is the passage written, according to the readout? Credit only a line that "
    "names the language of the words or text the readout is handling, for example 'X for "
    "\"...\"', 'in X it is called ...', 'the X word / name / term', 'X name:', 'the text / "
    "question is in X', 'since you asked in X'. A language discussed as a TOPIC does not count: "
    "a country's or state's official language, an essay about learning or teaching X, an X exam "
    "or course, the X-language market or media. The name may be written in any language or "
    "script. Text merely written in a language, or the passage's own words quoted, does not "
    "count."
)
QUESTION_UNIT_V2 = (
    "Which ONE of these does the readout name as {role_desc}? The readout must write it in "
    "{native_names}."
)
ROLE_DESC_V2: dict[str, str] = {
    "concept_native": "the word the passage leads to",
    "concept": "the thing the passage describes",
    "bridge_native": "the intermediate entity the passage's question passes through",
    "correction_native": "the correctly spelled word the passage's last word was meant to be",
}


def question_unit_v2(role: str, native: tuple[str, ...] = DEFAULT_NATIVE_LANGS) -> str:
    """The v2 content question, its language list rendered from the bank's native languages
    (``banks.native_langs``; "English or <the subject's native language>")."""
    return QUESTION_UNIT_V2.replace("{role_desc}", ROLE_DESC_V2[role]).replace(
        "{native_names}", english_names(native)
    )


def ml_question(role: str, native: tuple[str, ...] = DEFAULT_NATIVE_LANGS) -> str:
    return QUESTION_LANGUAGE_V2 if role == "language" else question_unit_v2(role, native)


def ml_prompts() -> dict[str, str]:
    """The v2 strings the four multilingual families send (each family's PROMPTS)."""
    return {
        "ML_SYSTEM": ML_SYSTEM,
        "QUESTION_LANGUAGE_V2": QUESTION_LANGUAGE_V2,
        "QUESTION_UNIT_V2": QUESTION_UNIT_V2,
        **{f"ROLE_DESC_V2_{k.upper()}": v for k, v in ROLE_DESC_V2.items()},
        "CANNOT": CANNOT,
        "USER": USER,
        "TOKEN_NOTE": mc.TOKEN_NOTE,
    }


# the task TYPE the digest's `task` variant may be told (never the item's prompt or units);
# each family's own prompts.py adds it to its PROMPTS via summary_prompts
# Camila 2026-11-01: the summarizer language tag (summ_lang) is dropped; each multilingual
# family instead tells the digest the TASK TYPE in a short neutral note, never the item's answer,
# its language or its intermediate (tests/test_r4b_task_notes.py checks every bank item)
_ML_TAIL = (
    "; note any language the readouts name and any concepts they mention, in whatever language "
    "they appear, even when mentioned only once"
)
DIGEST_TASK_NOTES: dict[str, str] = {
    "basic_readout_mt": BRMT_TASK_NOTE,
    "multihop_mt_v2": "the model reads a factual prompt whose answer needs one or two silent "
    "intermediate steps, each a multi-word name",
    # plan 0040 B8: no answer, rare mentions kept, the language left unnamed (the native
    # languages are subject-dependent; the judge prompt renders them from banks.native_langs)
    "multilingual": "the model read a brief prompt written in another language whose answer is "
    "a single everyday word" + _ML_TAIL,
    "multilingual_mt": "the model read a short passage written in another language that "
    "describes a thing and ends where its name would follow" + _ML_TAIL,
    "multilingual_multihop": "the model read a factual prompt written in another language "
    "whose answer needs a silent intermediate entity" + _ML_TAIL,
    "multilingual_typo": "the model read a sentence written in another language that ends in a "
    "misspelled word" + _ML_TAIL,
}  # typo_mt's note is its EvalSpec.task_note (evals/typo_mt/prompts.py, plan 0033 M1)

PROMPTS: dict[str, str] = {
    "SYSTEM": SYSTEM,
    "CANNOT": CANNOT,
    "QUESTION_UNIT": QUESTION_UNIT,
    "QUESTION_LANGUAGE": QUESTION_LANGUAGE,
    "USER": USER,
}
# basic_readout_mt's own strings (its PROMPTS adds them; printed in its README)
BRMT_SCHEMA = schema_block(
    "pick",
    {"choice": {"type": "string"}, "quote": {"type": "string"}, **RIVAL_FIELD},
    ["choice", "quote", "rival_quote"],
)
# optaudit-v1 (review of PR #208, round 4d): family.contested_verdict's code option-rival check
# (every other listed option and hidden rival) counted any line naming a rival and not the gold,
# whatever it was about: basic_readout_mt brh-ent-bonaire-capital (all) was contested 72 vs 69 by
# "The capital and principal city of Aruba is **Oranjestad**", a true line about another island,
# and L20 palau-capital 10 vs 5 by "Prior to 2016, Palau's capital was Koror". Every line that
# check would let outweigh the gold now goes to one more blind call, under the judge's own rival
# rule (same thing, same relation, same time); a line it dismisses is not weighed
OPTION_AUDIT_VERSION = "optaudit-v1"
OPTION_AUDIT_SYSTEM = f"""You check one answer of a judge of {mc.READOUT_PHRASE}, recorded \
while the model answered a question you cannot see. The judge picked the answer below and cited \
a quote from the readout that presents it as the answer. Each numbered line under LINES TO \
CHECK names a different candidate answer; its support marker ([N samples]) says how many \
readout samples hold it.

For EACH numbered line, say whether it presents its candidate as a COMPETING answer to the \
question the quote answers ("rival": true): the line gives its candidate for the same thing \
(the same place, person, work, substance, unit, ...), in the same relation and for the same \
time as the quote gives the pick: a second answer to that question, even when both claims could \
be true together (a thing with two subunits, two names or two founders), and however the line \
phrases it (an aside, "also", "similarly", a fragment). A line that does not say what its \
candidate is for, and simply offers it as the answer, is a rival too.
Not a rival ("rival": false): a line that gives its candidate for a clearly different thing (the \
same relation of another country, person or work), in a different relation, or for a time the \
line itself marks as different from the quote's (a former or later holder, an earlier name); a \
line that only mentions the candidate without giving it as the answer for anything (one entry of \
a list, a neighbour or a related thing). Judge only from what each line and the quote say, not \
from your own knowledge.
Return JSON: {{"verdicts": [{{"line": <number>, "why": "<what the line gives its candidate as, \
for what, and whether that answers the quote's question>", "rival": <true or false>}}, ...]}}, \
one verdict per numbered line."""
OPTION_AUDIT_USER = """THE JUDGE PICKED: {choice}
ITS QUOTE: {quote}

LINES TO CHECK:
{lines}"""
OPTION_AUDIT_SCHEMA = schema_block(
    "option_rivals",
    {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["line", "why", "rival"],
                "properties": {
                    "line": {"type": "integer"},
                    "why": {"type": "string"},
                    "rival": {"type": "boolean"},
                },
            },
        }
    },
    ["verdicts"],
)
OPTION_AUDIT_PROMPTS: dict[str, str] = {
    "OPTION_AUDIT_SYSTEM": OPTION_AUDIT_SYSTEM,
    "OPTION_AUDIT_USER": OPTION_AUDIT_USER,
}


def render_option_audit(choice: str, quote: str, lines: str) -> str:
    return OPTION_AUDIT_USER.format(choice=choice, quote=quote, lines=lines)


BRMT_PROMPTS: dict[str, str] = {
    "BRMT_SYSTEM": BRMT_SYSTEM,
    "BRMT_QUESTION": BRMT_QUESTION,
    "BRMT_CANNOT": mc.CANNOT,
    **OPTION_AUDIT_PROMPTS,
}


def summary_prompts(family: str, task_note: str | None = None) -> dict[str, str]:
    """The summary-mode (plan 0020) strings a multi-token family sends, for its own PROMPTS
    (``task_note``: the family's own ``EvalSpec.task_note``, else its ``DIGEST_TASK_NOTES``)."""
    return {
        "USER_SUMMARY": USER_SUMMARY,
        "DIGEST_TASK_NOTE": task_note if task_note is not None else DIGEST_TASK_NOTES[family],
        "SUMMARY_NOTE": digest.SUMMARY_NOTE,
        "SUMMARY_NOTE_ABSTRACTIVE": digest.SUMMARY_NOTE_ABSTRACTIVE,
        "SUMMARY_NOTE_TOKENS": digest.SUMMARY_NOTE_TOKENS,
    }


SCHEMA = schema_block(
    "pick", {"choice": {"type": "string"}, "quote": {"type": "string"}}, ["choice", "quote"]
)


def _question(role: str, native: tuple[str, ...], question: str | None) -> str:
    """The unit question: the language question, a family's own (``question``, no role label:
    basic_readout_mt's ``BRMT_QUESTION`` or an ``MCProfile``'s), else the shared
    ``QUESTION_UNIT`` with the role."""
    if role == "language":
        return question_language(native)
    return question if question is not None else QUESTION_UNIT.replace("{role}", role)


def render_user(
    readout: str,
    role: str,
    options: list[str],
    native: tuple[str, ...] = DEFAULT_NATIVE_LANGS,
    unit_question: str | None = None,
    *,
    question: str | None = None,
    v2: bool = False,
    token_note: str = "",
) -> str:
    """One MC user message. ``unit_question`` / ``question`` (same meaning; the keyword is an
    ``MCProfile``'s): a family's own question for its non-language units (None = the shared
    ``QUESTION_UNIT``). ``v2``: the multilingual v2 questions (``ml_question``);
    ``token_note``: the family's token-list rule, appended under a token readout."""
    own = question if question is not None else unit_question
    question = ml_question(role, native) if v2 else _question(role, native, own)
    if token_note:
        question = f"{token_note}\n\n{question}"
    lines = "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(options))
    return (
        USER.replace("{readout}", readout.strip())
        .replace("{question}", question)
        .replace("{options}", lines)
    )


def render_user_summary(
    readout: str,
    note: str,
    role: str,
    options: list[str],
    native: tuple[str, ...] = DEFAULT_NATIVE_LANGS,
    unit_question: str | None = None,
    *,
    question: str | None = None,
    v2: bool = False,
) -> str:
    """Summary mode: ``render_user`` with the digest note above the readout (the digest)."""
    own = question if question is not None else unit_question
    question = ml_question(role, native) if v2 else _question(role, native, own)
    lines = "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(options))
    return (
        USER_SUMMARY.replace("{summary_note}", note)
        .replace("{readout}", readout.strip())
        .replace("{question}", question)
        .replace("{options}", lines)
    )

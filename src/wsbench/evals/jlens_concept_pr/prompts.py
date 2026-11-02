"""Verbatim prompts of the jlens_concept_pr judge (``jlens-pr-v3``, plan 0042).

v2 was the source's prompts unchanged (v2 marked Stage A moving off DeepSeek-V4-Flash). v3
(Camila 2026-10-30, "the rubric credits a token that appears inside a concept regardless of the
concept's meaning"): Stages B and P carry three overlap rules (:data:`OVERLAP_RULES`: word
pieces, negation, same sense), Stage P names the one grounding token of every "in" / "partial"
grade (validated by :func:`parse_stage_p`), Stage B sees the token's whole readout set (the
same-sense rule needs it), and the generic word "lens" is gone from every prompt (plan 0032
§2.8.1; built from ``mc.READOUT_PHRASE``).

Source: ``scripts/oracle_lens_evals/jlens_pr/judge_prompts.py`` in the source repo — the
system prompts (L17-30, L32-47, L182-209), schemas (L51-73, L211-228), ``GRADE_VALUE`` (L75),
``STAGE_P_CHUNK`` (L229-232), the user bodies of ``stage_a_params`` / ``stage_b_params`` /
``stage_p_params`` (L110-120, L123-130, L246-251) and the parsers (L137-171, L254-272).
``STAGE_P_SYSTEM``'s worked-example guide was calibrated against the hand-label audit (v2); v3
changes it only by the "shutter" example (was "objective lens") and the overlap rules — the
v3 recalibration on ``precision_gold_L44.jsonl`` is a run-phase step (plan 0042 §3). Never
reflow it. Templates carry ``{name}`` placeholders substituted in one pass
(never ``str.format``). Every entry of :data:`PROMPTS` is printed verbatim in
``evals/jlens_concept_pr/README.md``.
"""

import json
import re
from collections.abc import Sequence
from typing import Any

from wsbench import mc
from wsbench.llm import schema_block

CALL_VERSION = "jlens-pr-v3"  # every judge call's fingerprint (the prompts below)
# fw-v1 (round 3, deterministic, stamp only): a Stage-P grade grounded on a function word the
# concept merely contains (" or" for "more or fewer neutrons") is out
# (:func:`function_word_grounded`)
# fw-v2 + sense-v1 (round-3 review, deterministic, stamp only): a concept ABOUT a function word
# keeps its grade ("then" for "if-then-else conditional"); a frequency adverb for a concept that
# states no frequency ("often" for "common names") and an agent noun for an act ("reader" for "a
# quick read") ground nothing (:func:`grounding_void`)
PROMPT_VERSION = f"{CALL_VERSION}+fw-v2+sense-v1"

STAGE_A_SYSTEM = f"""You are given text {mc.READOUT_PHRASE} (one readout at one \
position). Break the text into its UNIQUE concepts: short noun \
phrases naming each distinct thing, property, action or entity the text asserts. Merge \
duplicates and near-duplicates (inflections, restatements) into one concept. Ignore list \
bullets, markdown emphasis and boilerplate connectives, but NOT evaluative or affirmative \
markers: a checkmark or emoji (✅, ✔, 🎉), "Correct Answer", "Yes", "Final Answer" each name a \
concept ("correct / confirmed answer", "celebration") and must be listed when present. Do not \
add concepts the text does not contain.

Example. Text: "limited protein intake, potentially hindering wound healing. An elderly widow \
with inadequ" -> concepts: ["inadequate/insufficient amount", "protein intake", \
"wound healing", "elderly widow / older adult"].

Return JSON: {{"concepts": [string, ...]}}."""

# Plan 0042 item 3: the three rules that stop a token being credited for its spelling alone.
# Shared verbatim by Stages B and P (tests pin the worked examples).
OVERLAP_RULES = """Three rules limit what a token supports; a concept that breaks one is "out" \
for that token, whatever letters they share:
1. Word pieces. A token that is only a piece of a word supports a concept only when the piece \
on its own identifies the concept's word: a word start that spells one word (' incentiv' -> \
'incentives', ' eyel' -> 'eyelid'). A suffix or other piece shared by many unrelated words \
('osis', 'ness', 'ly', 'tion', 'uje') supports nothing by its letters: 'osis' is out for \
'congenital ptosis'.
2. Negation. A concept that negates the token's own word means the opposite and is out: \
'non-explicit variables' is out for 'explicit', 'no incentives' is out for 'incentives', \
'unhealthy' is out for 'healthy'. Negation of a different word does not count against the \
token ('no worry about overlap' stays in for 'overlap': the negation is on 'worry').
3. Same sense. Read each token in the sense the rest of the token set gives it (the set is one \
readout of one position). A concept that shares only the spelling, in a different sense or \
topic, is out: in the set ' billions, internet, cloud, networks, computers' the token \
' billions' is out for '4.5 billion years ago'; ' bank' beside ' river, shore' is out for \
'bank account'."""

STAGE_B_SYSTEM = f"""You grade whether ONE token read out of a language model's internal \
activations is supported by each of a list of concepts extracted from a text readout of the \
same position. The token's whole readout (the token set it was read with) is shown beside it. \
Grade every concept exactly once:

- "in": the concept has the token, modulo word inflection / casing / translation \
(e.g. tokens "accessing", "访问" match the concept "access pattern"). Emoji are words: an \
emoji token matches a concept that names the same thing in words ("✅" matches "correct \
answer"; "🎉" matches "celebration"), and emoji with the same meaning are the same token \
("🎉" and "🥳" both match "celebration"; "✅", "✔" and "✓" all match "confirmed / correct").
- "partial": the concept has a close relative of the token (e.g. token "lacks" matches \
"inadequate intake"; token "EXIT" matches "return 0"; token "😊" is partial for "gratitude").
- "out": everything else, including words the concept does not contain (e.g. tokens \
"SUCCESS", "printf" do not match "return 0;").

{OVERLAP_RULES}

Return JSON: {{"grades": [{{"concept": <exact concept string>, "grade": "in"|"partial"|"out"}}, \
...]}} with one entry per listed concept, using the concept strings verbatim."""

# ``schema_block`` returns the Chat-Completions wrapper ``{name, strict, schema}`` (the same shape
# as the source's ``llm_client.schema_block``).
STAGE_A_SCHEMA = schema_block(
    "concepts",
    {"concepts": {"type": "array", "items": {"type": "string"}}},
    ["concepts"],
)
STAGE_B_SCHEMA = schema_block(
    "grades",
    {
        "grades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string"},
                    "grade": {"type": "string", "enum": ["in", "partial", "out"]},
                },
                "required": ["concept", "grade"],
                "additionalProperties": False,
            },
        }
    },
    ["grades"],
)

GRADE_VALUE = {"in": 1.0, "partial": 0.5, "out": 0.0}

STAGE_P_SYSTEM = f"""You are given the SET of tokens read out of a language model's internal \
activations at one position (the top-k tokens of a readout, content tokens only), and a list of \
concepts extracted from a text readout of that same position.

Stage B asks, of ONE token, which concepts have it. This is the same question asked the other way \
round: for each concept, grade the BEST correspondence between that concept and ANY token in the \
set. Grade every concept exactly once, on the same three-point scale:

- "in": the concept has one of the tokens, modulo word inflection / casing / translation \
(tokens "accessing", "访问" are in for the concept "access pattern"). A concept that says more \
than the token still counts as in — the token has to be in the concept, not equal to it: \
"working at Walt Disney" is in for the token "Disney", "no worry about overlap" is in for \
"overlap", "credit card approval rates" is in for "credit" or "rates", "camera shutter speed" is \
in for "shutter". Emoji are words: an emoji token matches a concept that names the same thing in \
words ("✅" is in for "correct answer"; "🎉" for "celebration"), and emoji with the same meaning \
are the same token ("🎉" and "🥳" both match "celebration"; "✅", "✔" and "✓" all match \
"confirmed / correct").
- "partial": the concept has a close relative of one of the tokens — the token names the \
concept's category, a sibling, or a part of it (token "lacks" is partial for "inadequate intake"; \
"technologies" for "filtration technologies"; "police, arrest" for "traffic stop"; "people" for \
"Anji people"; "Alumni" for "Yale University"; "loan, funding" for "SBA approval requirement"; \
"MRI, MR" for "MR-ME"; "plants, herbs" for "flowers"; "😊" for "gratitude").
- "out": everything else — no token is in the concept and none is a close relative of it \
(tokens "Azure, Haskell, PowerShell" are out for "lambda expression (fun x -> ...)"; "Supplier" \
is out for "based in Victoria, Australia"; "はありません" is out for "final token").

{OVERLAP_RULES}

Return JSON: {{"grades": [{{"concept": <exact concept string>, "grade": "in"|"partial"|"out", \
"token": <the one token of the set that grounds an "in" or "partial" grade, copied as shown; \
"" for "out">}}, ...]}} with one entry per listed concept, using the concept strings verbatim."""

STAGE_P_SCHEMA = schema_block(
    "support",
    {
        "grades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string"},
                    "grade": {"type": "string", "enum": ["in", "partial", "out"]},
                    "token": {"type": "string"},
                },
                "required": ["concept", "grade", "token"],
                "additionalProperties": False,
            },
        }
    },
    ["grades"],
)
# One Stage P call grades at most this many concepts. Cells reach 279 concepts, which would both
# risk the judge's context window (every concept is echoed back verbatim) and dilute the grading;
# chunking keeps each call short. The cell's FULL token set goes into every chunk.
STAGE_P_CHUNK = 60


# User bodies (the f-strings of ``stage_a_params`` / ``stage_b_params`` / ``stage_p_params``).
STAGE_A_USER = "Text:\n{text}"
# v3: the token's readout set, so the same-sense rule can be applied (the judge always sends it)
STAGE_B_USER = "Token: {token_repr}\nToken set: {tok_list}\n\nConcepts:\n{listing}"
# the v2 body, kept only for ``render_stage_b`` without a set (never sent by the family judge)
_STAGE_B_USER_NO_SET = "Token: {token_repr}\n\nConcepts:\n{listing}"
STAGE_P_USER = "Tokens: {tok_list}\n\nConcepts:\n{listing}"

PROMPTS: dict[str, str] = {
    "STAGE_A_SYSTEM": STAGE_A_SYSTEM,
    "STAGE_B_SYSTEM": STAGE_B_SYSTEM,
    "STAGE_P_SYSTEM": STAGE_P_SYSTEM,
    "STAGE_A_USER": STAGE_A_USER,
    "STAGE_B_USER": STAGE_B_USER,
    "STAGE_P_USER": STAGE_P_USER,
}

_PLACEHOLDER = re.compile(r"\{(text|token_repr|tok_list|listing)\}")


def _render(template: str, **fields: str) -> str:
    """Single-pass placeholder substitution (a substituted value is never re-scanned)."""
    return _PLACEHOLDER.sub(lambda m: fields[m.group(1)], template)


def concept_listing(concepts: Sequence[str]) -> str:
    return "\n".join(f"{i + 1}. {c}" for i, c in enumerate(concepts))


def render_stage_a(text: str) -> str:
    return _render(STAGE_A_USER, text=text)


def token_list(tokens: Sequence[str]) -> str:
    return ", ".join(repr(t) for t in tokens)


def render_stage_b(token: str, concepts: Sequence[str], token_set: Sequence[str] = ()) -> str:
    """The Stage-B user body; ``token_set`` (the cell's content tokens, the judge always passes
    it) fills the ``Token set:`` line the same-sense rule reads."""
    if token_set:
        return _render(
            STAGE_B_USER,
            token_repr=repr(token),
            tok_list=token_list(token_set),
            listing=concept_listing(concepts),
        )
    return _render(_STAGE_B_USER_NO_SET, token_repr=repr(token), listing=concept_listing(concepts))


def render_stage_p(tokens: Sequence[str], concepts: Sequence[str]) -> str:
    return _render(STAGE_P_USER, tok_list=token_list(tokens), listing=concept_listing(concepts))


def stage_p_chunks(concepts: Sequence[str]) -> list[tuple[int, list[str]]]:
    """``(offset, slice)`` pairs covering ``concepts`` in order, each at most ``STAGE_P_CHUNK``."""
    return [
        (i, list(concepts[i : i + STAGE_P_CHUNK])) for i in range(0, len(concepts), STAGE_P_CHUNK)
    ]


# --- parsers (a ``ValueError`` = reject, never a partial score) ------------------------------


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _data(text: str | dict[str, Any]) -> dict[str, Any]:
    """The source parsers took the raw JSON text; wsbench hands them the parsed object."""
    data = json.loads(text) if isinstance(text, str) else text
    if not isinstance(data, dict):
        raise ValueError("response is not a JSON object")
    return data


def parse_stage_a(text: str | dict[str, Any]) -> list[str]:
    """Stage A JSON -> deduped (case/whitespace-insensitive) non-empty concepts, order kept."""
    data = _data(text)
    out: list[str] = []
    seen: set[str] = set()
    concepts = data.get("concepts", [])
    if not isinstance(concepts, list):
        raise ValueError("concepts is not a list")
    for c in concepts:
        if not isinstance(c, str):
            continue
        key = _norm(c)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c.strip())
    return out


def _parse_grades(text: str | dict[str, Any], concepts: Sequence[str]) -> list[float]:
    data = _data(text)
    want = {_norm(c): i for i, c in enumerate(concepts)}
    got: dict[int, float] = {}
    grades = data.get("grades", [])
    if not isinstance(grades, list):
        raise ValueError("grades is not a list")
    for entry in grades:
        if not isinstance(entry, dict):
            raise ValueError("grade entry is not an object")
        key = _norm(str(entry.get("concept", "")))
        grade = entry.get("grade")
        if key not in want:
            raise ValueError(f"unknown concept in response: {entry.get('concept')!r}")
        if want[key] in got:
            raise ValueError(f"duplicate concept in response: {entry.get('concept')!r}")
        if grade not in GRADE_VALUE:
            raise ValueError(f"bad grade {grade!r}")
        got[want[key]] = GRADE_VALUE[grade]
    if len(got) != len(concepts):
        missing = [c for c in concepts if want[_norm(c)] not in got]
        raise ValueError(f"missing grades for {missing}")
    return [got[i] for i in range(len(concepts))]


def parse_stage_b(text: str | dict[str, Any], concepts: Sequence[str]) -> list[float]:
    """Grades in ``concepts`` order; ValueError when the judge's concept set drifted."""
    return _parse_grades(text, concepts)


def _tok_norm(s: str) -> str:
    """A grounding token as the judge may copy it: whitespace-trimmed, casefolded, with one
    layer of the ``repr`` quotes the token list is shown in removed."""
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        s = s[1:-1].strip()
    return s.casefold()


def grounding_tokens(text: str | dict[str, Any]) -> list[str]:
    """The ``token`` field of every Stage-P grade, in response order (``""`` when absent)."""
    grades = _data(text).get("grades", [])
    return [str(g.get("token", "")) if isinstance(g, dict) else "" for g in grades]


def parse_stage_p(
    text: str | dict[str, Any],
    concepts: Sequence[str],
    tokens: Sequence[str] | None = None,
) -> list[float]:
    """Support grades in ``concepts`` order; ValueError when the concept set drifted, or (with
    ``tokens``, the set the call showed) when an "in" / "partial" grade does not name one token
    of that set as its grounding token (v3: makes the overlap rules checkable)."""
    out = _parse_grades(text, concepts)
    if tokens is not None:
        shown = {_tok_norm(t) for t in tokens}
        for entry in _data(text)["grades"]:
            if entry.get("grade") == "out":
                continue
            tok = entry.get("token")
            if not isinstance(tok, str) or _tok_norm(tok) not in shown or not _tok_norm(tok):
                raise ValueError(
                    f"grade {entry.get('grade')!r} for {entry.get('concept')!r} names no shown "
                    f"token as its grounding token: {tok!r}"
                )
    return out


# conjunctions, prepositions, articles and copulas, in the languages the J-lens top-10 lists show
# (pt-fineweb-0022 L56: " or", " หรือ", " или", " یا", " atau", " hoặc", " أو" side by side)
FUNCTION_WORDS = frozenset(
    {
        *("or", "and", "but", "nor", "of", "the", "a", "an", "to", "in", "on", "at", "by"),
        *("as", "for", "from", "with", "than", "then", "so", "if", "is", "are", "was", "be"),
        *("或", "或者", "和", "与", "及", "的", "是", "在", "หรือ", "และ", "или", "и", "یا"),
        *("و", "atau", "dan", "hoặc", "và", "أو", "ou", "et", "de", "o", "y", "oder", "und"),
    }
)


def is_function_word(tok: str) -> bool:
    """A grounding token that is only a function word (after the token-list quotes, edge
    whitespace and a leading hyphen of a word piece: "-of")."""
    return _tok_norm(tok).lstrip("-") in FUNCTION_WORDS


def string_overlap_only(tok: str, concept: str) -> bool:
    """The grounding token is a function word that the concept merely CONTAINS as a word ("or" in
    "more or fewer neutrons", "on" in "something on your mind"): a match on spelling alone. A
    function word whose meaning is the concept ("or" for "alternatives", "IF" / "THEN" for
    "conditional branching") is not touched."""
    if not is_function_word(tok):
        return False
    w = _tok_norm(tok).lstrip("-")
    if mc._CJK.search(w):
        return w in concept
    c = concept.casefold()
    if _ABOUT_FUNCTION.search(c):  # fw-v2: "if-then-else conditional", "either/or choice"
        return False
    return re.search(rf"(?<![^\W_]){re.escape(w)}(?![^\W_])", c) is not None


# fw-v2 (round-3 review): a concept that is ABOUT a function word's meaning keeps its grade: a
# compound of function words ("if-then-else conditional", "and/or", "either-or") or a logic /
# grammar word ("conditional", "conjunction", "boolean operator", "alternatives")
_ABOUT_FUNCTION = re.compile(
    r"\b(?:if|then|else|and|or|either|neither|nor|but|not)[-/](?:if|then|else|and|or|either|"
    r"neither|nor|but|not)\b|\b(?:conditional\w*|conjunction\w*|disjunction\w*|boolean|"
    r"logical|logic|operators?|alternatives?|preposition\w*|articles?|copula\w*|clauses?|"
    r"branch\w*)\b"
)

# sense-v1 (round-3 review): two deterministic same-sense rules on Stage-P groundings.
# (1) A frequency adverb ("often", "typically", "往往") grounds a concept only when the concept
# states frequency or typicality, and "common" in a fixed collocation where it means shared /
# vernacular ("common names", pt-fineweb-0021 all-lite L24) states neither.
_FREQ_TOKENS = frozenset(
    {
        *("often", "usually", "frequently", "sometimes", "typically", "generally", "commonly"),
        *("occasionally", "rarely", "seldom", "always", "never", "tends", "tend", "souvent"),
        *("往往", "常常", "通常", "通常是", "经常", "有时", "时常"),
    }
)
_FREQ_CONCEPT = re.compile(
    r"\b(?:often|usual\w*|frequen\w*|sometimes|typical\w*|general\w*|common\w*|rare\w*|"
    r"seldom|always|never|tend\w*|habit\w*|regular\w*|recurr\w*|repeat\w*|occasional\w*|"
    r"incidence|prevalen\w*|most|generic\w*|determinis\w*|consisten\w*|constant\w*|invariab\w*|"
    r"every|annual\w*|daily|weekly)\b"
)
_COMMON_FIXED = re.compile(
    r"\bcommon\s+(?:names?|ground|sense|law|room|good|denominator|area|core|stock|nouns?|"
    r"ancestors?|carrier|market|wealth|era)\b|\bin common\b"
)


def frequency_sense_mismatch(tok: str, concept: str) -> bool:
    """sense-v1 (1): the grounding token is a frequency adverb and the concept states no
    frequency (its only "common" is a shared / vernacular collocation, "common names")."""
    if _tok_norm(tok).lstrip("-") not in _FREQ_TOKENS:
        return False
    c = _COMMON_FIXED.sub(" ", concept.casefold())
    return _FREQ_CONCEPT.search(c) is None


# (2) An agent noun built on the concept's word for an ACT ("reader" for "a quick read" / "to
# read", pt-pile-0050 L36 / L40) names the doer, not the act: a spelling overlap. The act is the
# concept word after an article / adjective ("a quick read") or after "to" ("chapter to read").
_PRONOUNS = frozenset({"you", "me", "him", "her", "them", "us", "it", "one"})
_ACT_WORD = re.compile(r"\b(?:to|a|an)\s+(?:[^\W\d_]+\s+)?([^\W\d_]{3,})\b")


def agent_noun_only(tok: str, concept: str) -> bool:
    """sense-v1 (2): the token is ``w + "er"`` / ``"ers"`` for an act word ``w`` of the concept
    (:data:`_ACT_WORD`) that the concept does not itself spell as the agent."""
    t = _tok_norm(tok).lstrip("-")
    c = concept.casefold()
    if not t.isalpha() or re.search(rf"(?<![^\W_]){re.escape(t)}(?![^\W_])", c):
        return False
    acts = {m.group(1) for m in _ACT_WORD.finditer(c)}
    acts = {w for w in acts if not w.endswith("er") and w not in FUNCTION_WORDS | _PRONOUNS}
    return any(t in (w + "er", w + "ers") for w in acts)


def grounding_void(tok: str, concept: str) -> bool:
    """A Stage-P grounding that grounds nothing (scored out): fw-v2 (:func:`string_overlap_only`)
    or sense-v1 (:func:`frequency_sense_mismatch`, :func:`agent_noun_only`)."""
    return (
        string_overlap_only(tok, concept)
        or frequency_sense_mismatch(tok, concept)
        or agent_noun_only(tok, concept)
    )


def function_word_grounded(text: str | dict[str, Any], concepts: Sequence[str]) -> list[bool]:
    """fw-v1 (round 3) / fw-v2 + sense-v1 (review): per concept (``concepts`` order), whether its
    Stage-P "in" / "partial" grade is grounded on a token that grounds nothing
    (:func:`grounding_void`: a function word the concept only shares as a word, a frequency
    adverb for a concept with no frequency, an agent noun for an act). Such a token grounds
    nothing ("more or fewer neutrons" is out for " or": the conjunction is in the concept's
    spelling, not its meaning), so the scorer counts the grade as out."""
    want = {_norm(c): i for i, c in enumerate(concepts)}
    out = [False] * len(concepts)
    for entry in _data(text).get("grades", []):
        if not isinstance(entry, dict) or entry.get("grade") == "out":
            continue
        i = want.get(_norm(str(entry.get("concept", ""))))
        tok = entry.get("token")
        if i is not None and isinstance(tok, str) and grounding_void(tok, concepts[i]):
            out[i] = True
    return out

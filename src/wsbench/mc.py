"""Helpers every multiple-choice family shares: seeds, shuffles, listings, pick labels."""

import hashlib
import random
import re
import unicodedata
from collections.abc import Sequence
from typing import Any

CANNOT = "cannot tell from the readout"
# knowledge_cutoff's NONE line (its options are letters plus NONE; plan 0032 §2.4.4)
KC_NONE = "NONE (cannot tell from the readouts)"
# the one neutral name of what every family judges (no tool name; plan 0032 §2.8.1)
READOUT_PHRASE = "readouts of a language model's internal activations"
BULLET_MARK = "\u205e"  # ⁞, the bullet separator of one free-text sample (digest.BULLET_MARK)


def seed_int(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode()).digest()[:8], "big")


def seeded_shuffle[T](items: Sequence[T], seed: str) -> list[T]:
    out = list(items)
    random.Random(seed_int(seed)).shuffle(out)
    return out


def listing(options: Sequence[str]) -> str:
    return "\n".join(f"  {i + 1}. {o}" for i, o in enumerate(options))


def classify(choice: Any, gold_pos: int, n_shown: int, *, contrast_pos: int | None = None) -> str:
    """``invalid`` | ``cannot_tell`` (CANNOT is always the last line) | ``gold`` | ``contrast`` |
    ``distractor``."""
    if isinstance(choice, bool) or not isinstance(choice, int) or not (1 <= choice <= n_shown):
        return "invalid"
    if choice == n_shown:
        return "cannot_tell"
    if choice == gold_pos:
        return "gold"
    if contrast_pos is not None and choice == contrast_pos:
        return "contrast"
    return "distractor"


def join_samples(samples: Sequence[str]) -> str:
    return "\n".join(s for s in samples if s.strip())


def fold(s: str) -> str:
    """Accent-, case- and curly-quote-insensitive form for verbatim-quote checks."""
    s = unicodedata.normalize("NFKD", s)
    for a, b in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')):
        s = s.replace(a, b)
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def letter_index(choice: Any, options: Sequence[str], letters: str = "ABCDEF") -> int | None:
    """The option index a judge's ``choice`` names: a lone letter (``"B"``, ``"b."``) or the
    letter followed by the text of that same option (``"B. blue ladder"``). Anything else, a
    letter past the list, or a letter with another option's text is None (``"cannot tell"`` is
    not option C)."""
    m = re.fullmatch(r"([A-Za-z])(?:\s*[.):-]?\s*(.*))?", str(choice or "").strip(), re.S)
    if not m:
        return None
    idx = letters.find(m.group(1).upper())
    if idx < 0 or idx >= len(options):
        return None
    rest = (m.group(2) or "").strip().rstrip(".,;:")
    return idx if not rest or fold(rest) == fold(options[idx]) else None


def is_cannot(option: str) -> bool:
    """``option`` is a cannot-tell escape: it fold-starts with ``cannot tell`` or is
    :data:`KC_NONE`."""
    f = fold(option).strip()
    return f.startswith("cannot tell") or f == fold(KC_NONE)


def options_with_cannot(options: Sequence[str], *, cannot: str = CANNOT) -> list[str]:
    """``options`` (already in their seeded order) with ``cannot`` appended LAST. The escape is
    never shuffled in: shuffle the substantive options first (:func:`seeded_shuffle`), then call
    this. Refuses a list that already holds a cannot-tell option and a ``cannot`` text that is not
    one (``cannot tell …`` or :data:`KC_NONE`). ``classify`` reads the last line as
    ``cannot_tell``."""
    if not is_cannot(cannot):
        raise ValueError(f"cannot={cannot!r}: must start with 'cannot tell' (or be KC_NONE)")
    dup = [o for o in options if is_cannot(str(o))]
    if dup:
        raise ValueError(f"options already hold a cannot-tell option: {dup!r}")
    return [*options, cannot]


_TOKEN_NOTE_HEAD = (
    'A line whose items are separated by " | " is one ranked list of the top vocabulary tokens '
    "read from ONE activation, best first. Several tokens of the same line may jointly express "
    "one meaning, and a quote from such a line is one token or several tokens of that same line "
    'joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell '
    "one word split across them; such a quote is that word. Tokens on different lines never "
    "combine otherwise, and a relation (who does what to whom) must be stated within one sample "
    '(for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are '
    f"separated by {BULLET_MARK})."
)


# what a same-kind run is when a family names no flat_types (decision Q4)
FLAT_RUN = (
    "a run of interchangeable words or names of one kind (numbers, months, colours, countries, "
    "cities, people, works, ...)"
)


def _flat(flat_types: Sequence[str]) -> str:
    types = [t.strip() for t in flat_types if t.strip()]
    if not types:
        return ""
    return types[0] if len(types) == 1 else ", ".join(types[:-1]) + " or " + types[-1]


# bump on any token_note() text edit; stamped on every result (runner.finalize_reads), since
# most families' own prompt_version does not cover the shared note
TOKEN_NOTE_VERSION = "tn-2026-10-31-q4"


def token_note(
    flat_types: Sequence[str] = (), *, multi_select: bool = False, targets: bool = False
) -> str:
    """The ONE token-list rule every judge prompt shows (plan 0032 §2.7.2, decision Q4): one list
    = one activation's sample; tokens of one list may combine; adjacent positions of one layer
    only to spell one word; nothing relational across lines or bullets. Single-answer families: a
    line holding two or more of the options singles out none of them, whatever their rank; a run
    of the family's ``flat_types`` singles out none of its members even when only one is an
    option, and takes precedence over the lone-option clause (review of PR #140).
    ``multi_select`` (multi_concept_directed_modulation): a line naming several options names
    each of them. ``targets`` (the basic bank families, whose judge holds TARGETS, not options;
    review of PR #140): no lone-option clause, so a target that is one word of a same-type run is
    never singled out by that line, whatever its rank (Q4; SYSTEM's interchangeable-candidates
    rule)."""
    flat = _flat(flat_types)
    if targets:
        if multi_select:
            raise ValueError("targets=True is a single-judgement note; multi_select is for options")
        kinds = (
            f"a run of {flat}, or of any other one type"
            if flat
            else ("a run of numbers, month names, colours, sport names, ...")
        )
        tail = (
            " These lines are judged against the TARGETS, not against a set of options. A line "
            f"made mostly of interchangeable words of one type ({kinds}) singles out none of "
            "them, whatever their rank: a target that is one word of such a run is not singled "
            "out by that line, even when it is ranked first and is the only target on the line."
        )
    elif multi_select:
        tail = (
            " A line that names several of the options names each of them; pick each option it "
            "names (up to the pick limit)."
            + (f" A run of {flat} names none of its members." if flat else "")
        )
    else:
        # Q4 (binding over SHARED_API r2's "an option alone on its line is singled out"): the
        # lone-option clause never credits a flat run of one kind, flat_types or not
        lone = " Otherwise, an option that is the only option on its line is singled out by it."
        if flat:
            tail = (
                " A line that holds two or more of the options singles out none of those "
                f"options, whatever their rank. A line that holds a run of {flat}, or of any "
                "other words or names of one kind, singles out none of the words on it, whatever "
                "their rank, even when only one of them is an option." + lone
            )
        else:
            tail = (
                " A line that holds two or more of the options singles out none of those "
                f"options, whatever their rank. A line that holds {FLAT_RUN} singles out none of "
                "the words on it, whatever their rank, even when only one of them is an option."
                + lone
            )
    return _TOKEN_NOTE_HEAD + tail


TOKEN_NOTE = token_note()
# the basic bank families' default (their judge holds targets, not options)
TARGET_TOKEN_NOTE = token_note(targets=True)

_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")


def is_cjk(form: str) -> bool:
    """``form`` holds a character of a script without spaces between words (CJK, kana, Hangul):
    :func:`form_in` matches such a form as a substring."""
    return bool(_CJK.search(form))


_HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
# Arabic-script folding for :func:`form_hits` ``clitics=True`` (plan F4): Persian / Arabic letter
# variants unified, hamza seats dropped to a bare alif, tatweel removed (``fold`` already drops
# the harakat, which are combining marks)
_AR_LETTERS = str.maketrans(
    {"\u06cc": "\u064a", "\u0649": "\u064a", "\u06a9": "\u0643", "\u0623": "\u0627",
     "\u0625": "\u0627", "\u0622": "\u0627", "\u0671": "\u0627", "\u0640": None}
)  # fmt: skip
_AR_WORD = re.compile(r"[\u0600-\u06ff]+")
# a leading conjunction (wa-, fa-), then a preposition (bi-, li-, ka-), then the article (al-);
# "lil-" is li- + al- with the alif elided
_AR_CLITIC = re.compile(
    r"^(?:[\u0648\u0641])?(?:\u0644\u0644|[\u0628\u0644\u0643]?(?:\u0627\u0644)?)"
)
AR_MIN_STEM = 3  # a clitic is stripped only when this many letters remain


def _ar_stem(word: str) -> str:
    w = word.translate(_AR_LETTERS)
    m = _AR_CLITIC.match(w)
    if m and m.end() and len(w) - m.end() >= AR_MIN_STEM:
        return w[m.end() :]
    return w


def ar_fold(text: str) -> str:
    """``fold`` plus, in every Arabic-script word, the letter variants unified and a leading
    conjunction / preposition / article stripped (``والطوسي`` -> ``طوسي``, Persian ``طوسی`` ->
    ``طوسي``); other scripts unchanged."""
    return _AR_WORD.sub(lambda m: _ar_stem(m.group(0)), fold(text))


SUFFIX_MIN_STEM = 5  # a form gets suffix tolerance only when it is this many letters or longer


def form_hits(
    text: str,
    forms: Sequence[str],
    *,
    suffix: int = 0,
    clitics: bool = False,
    hangul: bool = False,
) -> list[str]:
    """The listed forms that occur in ``text`` (both folded), with the text word each one hit
    (in form order). A form in a script without spaces between words (CJK, kana) is an exact
    substring; any other form (Latin, Cyrillic, Greek…) sits between Unicode word boundaries.
    ``hangul`` (plan F4): a Hangul form is an exact substring too, compared in NFC (``fold``'s
    NFKD splits a syllable into jamo, so without it a Hangul form falls to the word-boundary
    rule and never matches before a particle, ``일연입니다``; NFC also keeps ``가`` out of
    ``갈``). ``suffix`` (an inflecting source language,
    plan F4): a form of at least :data:`SUFFIX_MIN_STEM` letters may run on into up to
    ``suffix`` further word letters (``Åland`` -> ``Ålands``, ``Ahvenanmaa`` -> ``Ahvenanmaalla``).
    ``clitics``: Arabic-script text and forms are compared after :func:`ar_fold`."""
    t = ar_fold(text) if clitics else fold(text)
    t_nfc = unicodedata.normalize("NFC", text).casefold()
    out: list[str] = []
    for f in forms:
        if hangul and _HANGUL.search(f):
            ff = unicodedata.normalize("NFC", f).casefold().strip()
            if ff and ff in t_nfc:
                out.append(ff)
            continue
        ff = (ar_fold(f) if clitics else fold(f)).strip()
        if not ff:
            continue
        if _CJK.search(ff):
            if ff in t:
                out.append(ff)
            continue
        tail = ""
        if suffix > 0 and len(ff) >= SUFFIX_MIN_STEM and ff[-1].isalpha():
            tail = rf"[^\W\d_]{{0,{int(suffix)}}}"
        m = re.search(rf"(?<!\w){re.escape(ff)}{tail}(?!\w)", t)
        if m:
            out.append(m.group(0))
    return out


def form_in(text: str, forms: Sequence[str]) -> bool:
    """A listed form occurs in ``text`` (both folded): :func:`form_hits` with no suffix or
    clitic tolerance. A form in a script without spaces between words (CJK, kana, Hangul) is an
    exact substring, any other form (Latin, Cyrillic, Greek…) sits between Unicode word
    boundaries. A text without Latin letters is never accepted by default: it passes only if it
    holds a listed form of its own script."""
    return bool(form_hits(text, forms))

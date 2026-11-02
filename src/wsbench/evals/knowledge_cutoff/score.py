"""knowledge_cutoff's regex scorer: an port of the source's per-option span matcher with
exclusive longest match (``olens_suite/cutoff_confab/matching.py``) and its cell rules
(``scoring.py``). The rules are stated in ``evals/knowledge_cutoff/README.md``."""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from wsbench import digest
from wsbench import numerals as _numerals
from wsbench.multitoken.regex import (
    fold,  # identical to the source's bank.matching.fold
    fold_accents,
)

_CJK_NUMERAL = re.compile(r"^[零〇一二两兩三四五六七八九十百千万亿点]+$")
_CJK_HANGUL = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_WORDY = re.compile(r"[^\W_]+(?:[\s\-'][^\W_]+)*")
_STRIP = re.compile(r"US\$|[$,%\s]")
_DIGIT_GUARD = r"(?<!\d)(?<!\d[.,])"  # a form starting with a digit never starts mid-number
# a word character that is NOT CJK/Hangul: numbers may touch CJK text (12个, 约16, 2026年, 1199元)
_NW = r"[^\W぀-ヿ㐀-鿿가-힯]"
_NUM_PRE = r"(?<!\d[.,])(?<!-)(?<!" + _NW + r")"  # a fullwidth comma folds to ","
_NUM_POST = r"(?![.,]?\d)(?!" + _NW + r")"


def _int_body(digits: str) -> str:
    """Digits with an optional thousands separator (comma or space) at thousands positions."""
    head = len(digits) % 3 or 3
    groups = [digits[:head]] + [digits[i : i + 3] for i in range(head, len(digits), 3)]
    return "[ ,]?".join(re.escape(g) for g in groups)


def compile_form(form: str) -> re.Pattern[str] | None:
    """The span pattern for one alias form over folded text; ``None`` if the form is dropped."""
    f = form.strip()
    if not f:
        return None
    num = _STRIP.sub("", f)
    if re.fullmatch(r"\d+", num):
        return re.compile(_NUM_PRE + _int_body(num) + _NUM_POST)
    if re.fullmatch(r"\d+\.\d+", num):
        whole, frac = num.split(".")
        return re.compile(_NUM_PRE + _int_body(whole) + r"\." + re.escape(frac) + _NUM_POST)
    if _CJK_NUMERAL.fullmatch(f):
        return None
    ff = fold(f)
    guard = _DIGIT_GUARD if ff[:1].isdigit() else ""
    if _CJK_HANGUL.search(f) or not _WORDY.fullmatch(ff):
        return re.compile(guard + re.escape(ff))
    parts = [re.escape(w) for w in re.split(r"[\s\-]+", ff) if w]
    return re.compile(guard + r"(?<![^\W_])" + r"[\s\-]+".join(parts) + r"(?![^\W_])")


@dataclass(frozen=True)
class OptionForms:
    """All options' compiled forms for one item; scoring is exclusive longest match."""

    forms: tuple[tuple[str, re.Pattern[str]], ...]
    options: tuple[str, ...]

    @classmethod
    def build(cls, aliases: Mapping[str, Sequence[str]]) -> "OptionForms":
        """``aliases``: option -> forms (the option label itself is always added)."""
        forms: list[tuple[str, re.Pattern[str]]] = []
        for opt, fs in aliases.items():
            for f in sorted({opt, *fs}):
                pat = compile_form(f)
                if pat is not None:
                    forms.append((opt, pat))
        return cls(tuple(forms), tuple(aliases))

    def _kept(self, t: str) -> list[tuple[int, int, str]]:
        spans = [
            (m.start(), m.end(), opt)
            for opt, pat in self.forms
            for m in pat.finditer(t)
            if m.end() > m.start()
        ]
        spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
        kept: list[tuple[int, int, str]] = []
        contested: set[tuple[int, int]] = set()
        for a, b, opt in spans:
            clash = [(ka, kb, ko) for ka, kb, ko in kept if a < kb and ka < b]
            if clash:
                if any((ka, kb) == (a, b) and ko != opt for ka, kb, ko in clash):
                    contested.add((a, b))
                continue
            kept.append((a, b, opt))
        return [(a, b, o) for a, b, o in kept if (a, b) not in contested]

    def named(self, text: str, *, numerals: bool = False, tokens: bool = False) -> set[str]:
        """Options named in ``text``: all matches of all forms, longest first (then leftmost),
        a match kept only if it overlaps no kept span; the identical span claimed by two options
        credits neither. ``numerals=True`` (plan 0044 §C7.1; the verifier and the support
        counter, never the regex diagnostics or ``ati_pass``) also credits an integer option
        named by a CJK numeral, an uppercase Roman numeral or a number word (number words in
        prose only for values >= 11; ``tokens=True`` for a token row: always)."""
        t = fold(text)
        kept = self._kept(t)
        out = {o for _a, _b, o in kept}
        if numerals:
            for a, b, v in numeral_values(text, tokens=tokens):
                hit = [o for o, n in self.integer_values.items() if n == v]
                if not hit:
                    continue
                if any(a < kb and ka < b and ko not in hit for ka, kb, ko in kept):
                    continue  # inside another option's listed form
                out.update(hit)
        return out

    @property
    def integer_values(self) -> dict[str, int]:
        return {o: v for o in self.options if (v := integer_value(o)) is not None}

    def counts(self, samples: Iterable[str]) -> dict[str, int]:
        """``option -> number of samples naming it`` (exclusive per sample)."""
        c = dict.fromkeys(self.options, 0)
        for s in samples:
            for o in self.named(s):
                c[o] += 1
        return c


def token_bag_text(tokens: Sequence[str]) -> str:
    """A token lens's top-k list as ONE sample: tokens (decoded by the loader) stripped and
    space-joined. Qwen splits digits, so multi-digit numbers never hit."""
    return " ".join(t.strip() for t in tokens)


def strict_win(counts: Mapping[str, int], gold: str) -> bool:
    """Gold named by strictly more samples than every other option (and by at least one)."""
    g = counts.get(gold, 0)
    return g > 0 and all(v < g for o, v in counts.items() if o != gold)


def plurality(counts: Mapping[str, int], gold: str) -> float:
    """Tie-split view: 1 if gold is the unique most-named option, 1/n if tied at the top."""
    top = max(counts.values(), default=0)
    if top == 0 or counts.get(gold, 0) != top:
        return 0.0
    return 1.0 / sum(1 for v in counts.values() if v == top)


def best_layer(wins_by_layer: Mapping[int, int]) -> int | None:
    """The bank layer: most strict wins at reply_start, ties to the earliest layer."""
    if not wins_by_layer:
        return None
    return max(sorted(wins_by_layer), key=lambda k: wins_by_layer[k])


# ---------------------------------------------------------------- plan 0044: verification gates

# where a sample's leading answer ends and its note begins (G1, §C4): a comment marker after a
# space, an opening parenthesis of a note / example / alternative, a "Note:" label, a CJK note
# parenthesis, or a spaced em / en dash. A newline inside a bullet is NOT a marker.
NOTE_MARK = re.compile(
    r"\s(?://|#|/\*)|\(\s*\*{0,2}(?:note|e\.g\.|i\.e\.|explanation|or\b)|\*\(|"
    r"\b(?:note|explanation|reasoning)\s*[:\uff1a]|\uff08\s*(?:注|备注)|\s[\u2014\u2013]\s",
    re.I,
)
# a spaced dash ends the answer only in the short "<answer> — <note>" shape: in descriptive prose
# (an NLA sample: "Genre: a QA task — the model ...") it is punctuation, not a note
DASH_MARK = re.compile(r"\s[\u2014\u2013]\s")
DASH_HEAD_MAX_WORDS = 6
MIN_SUPPORT = 2  # G2: samples that must present the pick (or every sample, when fewer exist)
MIN_WORD_VALUE_PROSE = 11  # "two" / "eight" are common prose words; "nineteen" is not
_ROMAN = re.compile(r"(?<![A-Za-z])[IVXL]{2,}(?![A-Za-z])")
_ROMAN_VAL = {"I": 1, "V": 5, "X": 10, "L": 50}
_NUM_TOKEN = re.compile(r"(?<![A-Za-z]-)(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?![\d])")
_LATIN_ALNUM = re.compile(r"[0-9A-Za-zÀ-ɏ]")


# list numbering is never an answer (kcgate-v2): an enumerator at a raw line start followed by
# text on that line ("1.  **Analyze the Request**", "8. To determine ...", "2) The user"), a
# step / part label's number ("### Step 1:", "Part 2", "Q3"), and an inline "N)" item marker
# ("Let's reason step by step: 1) How many"). On the final O-lens readouts every line-start
# enumerator whose number is an option (144) is list numbering. A bare "50." line and a number
# inside a sentence are untouched
_ENUM_LINE = re.compile(r"(?m)^([ \t]*(?:[-*+][ \t]+)?)\d{1,3}[.)](?=[ \t]+\S)")
_ENUM_LABEL = re.compile(
    r"(?i)\b(step|part|phase|stage|point|option|method|approach|case|example|question|reason|"
    r"rule|section|chapter|q)(\s*#?\s*)\d{1,3}\b"
)
_ENUM_INLINE = re.compile(r"(?<=[:.;] )\d{1,2}\)(?=\s+[^\W\d_])")  # after ": " / ". " / "; "


def mask_enumerators(sample: str) -> str:
    """``sample`` with its list numbering removed (the number only; the item text stays)."""
    s = _ENUM_LINE.sub(r"\1", sample)
    s = _ENUM_LABEL.sub(r"\1\2", s)
    return _ENUM_INLINE.sub("", s)


def small_number_word(form: str) -> bool:
    """``form`` is one bare number word below :data:`MIN_WORD_VALUE_PROSE` ("three", "eight"):
    a common prose word, never support on its own (kcgate-v2; the numeral rule's threshold)."""
    toks = _numerals.tokens(form.strip())
    return (
        len(toks) == 1
        and toks[0][3] == "word"
        and toks[0][2] < MIN_WORD_VALUE_PROSE
        and toks[0][0] == 0
        and toks[0][1] == len(fold(form.strip()))
    )


# G3's topic filter (kcgate-v3, round-3 review): a rival only contests the pick in a statement
# ABOUT the item's question. The question's topic terms are its words of >= 4 letters and its
# acronyms / model names ("ODI", "GPU", "B300", "HBM3e"), minus question scaffolding, months and
# generic verbs; a statement is on topic when it names one. Off-topic presentations ("**3**
# Oxygens in Styrene oxide", "Chile has **3** World Cup victories", "8 gigabytes" is ON topic,
# "July 8, 2024" is not) present nothing to G3. A number directly followed by "?" is the tail
# of a restated question ("3? The answer is Virat Kohli"), never an answer.
_TOPIC_STOP = frozenset(
    """what which when where whom whose that this these those there their they them then than
    with without from into onto over under about after before during since until upon against
    between among through across within have has had having does did done doing been being
    were will would could should shall might must make made many much more most less least
    some such each every also only just like very your yours give given gave provide provided
    provides detail detailed details announce announced announcement announces release
    released releases launch launched launches unveil unveiled report reported reports state
    stated say said says according count number numbers total value amount answer answers
    guess sure best question exact exactly approximately around roughly about version first
    second third last latest january february march april june july august september october
    november december year years month months week weeks time times date dates""".split()  # noqa: SIM905
)
_TOPIC_WORD = re.compile(r"[^\W\d_][\w'\u2019-]*", re.UNICODE)
_QUESTION_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?\s*[?\uff1f]")


_LEAD_NUM = re.compile(r"(?:\s|[*_`#>\"'(\[$]|</?think>)*([-+]?\d[\d,]*(?:\.\d+)?)(?![\d?\uff1f])")
_CAP_RUN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+")


def lead_number(text: str) -> str | None:
    """The number ``text`` OPENS with (after markup and think tags; not one followed by "?"):
    the answer head of a reply-start sample ("10 The ECB's ...", "**50**"). G3 counts it
    whatever the rest of the sample is about (kcgate-v3)."""
    m = _LEAD_NUM.match(text)
    return m.group(1) if m else None


def topic_terms(question: str) -> frozenset[str]:
    """The topic terms of an item's question (see :data:`_TOPIC_STOP`): a folded lowercase
    prefix stem per word (all but its last 3 letters, at least 5: "centur" for "centuries"),
    and a short all-caps acronym ("US", "ODI") kept as written, matched case-sensitively, plus
    the initials of a run of capitalised words ("European Central Bank" -> "ECB")."""
    out: set[str] = set()
    for run in _CAP_RUN.findall(question):  # "European Central Bank" -> "ECB"
        out.add("=" + "".join(w[0] for w in run.split()))
    for m in _TOPIC_WORD.finditer(question):
        w = re.sub(r"['\u2019]s$", "", m.group(0).strip("'\u2019-"))
        f = fold(w).lower()
        if f in _TOPIC_STOP:
            continue
        if "-" in w:  # "Mercedes-Benz", "fast-charging": each part is a term too
            out |= topic_terms(w.replace("-", " "))
        if w.isupper() and len(w) <= 3 and w.isalpha():
            out.add("=" + w)
        elif any(ch.isdigit() for ch in w) or w.isupper() or len(f) >= 4:
            out.add(f[: max(5, len(f) - 3)] if f.isalpha() else f)
    return frozenset(out)


def on_topic(text: str, terms: frozenset[str]) -> bool:
    """``text`` names one of ``terms``: a word starting with a stem ("Kohli's", "century"), or
    the exact acronym. No terms -> every text is on topic."""
    if not terms:
        return True
    t = fold(text).lower()
    for w in terms:
        if w.startswith("="):
            if re.search(rf"(?<![^\W_]){re.escape(w[1:])}s?(?![^\W_])", fold_accents(text)):
                return True
        elif re.search(rf"(?<![^\W_]){re.escape(w)}", t):
            return True
    return False


def mask_question_numbers(text: str) -> str:
    """``text`` with every number directly followed by ``?`` removed (G3, kcgate-v3)."""
    return _QUESTION_NUM.sub(" ", text)


def integer_value(option: str) -> int | None:
    """An option's integer value (after the ``$ , % space`` strip), or None."""
    t = _STRIP.sub("", option)
    return int(t) if re.fullmatch(r"\d+", t) else None


def number_of(option: str) -> float | None:
    """An option's numeric value (integer or decimal, after the strip), or None."""
    t = _STRIP.sub("", option)
    return float(t) if re.fullmatch(r"\d+(?:\.\d+)?", t) else None


def is_numeric(options: Sequence[str]) -> bool:
    """Every option parses as a number (G3 and the number-flood void apply)."""
    return bool(options) and all(number_of(str(o)) is not None for o in options)


def roman_value(tok: str) -> int | None:
    """An uppercase standalone Roman numeral's value, 2-89, canonical spelling only (the one
    KC-local numeral parser; ``wsbench.numerals`` has no Roman path)."""
    if not re.fullmatch(r"[IVXL]{2,}", tok):
        return None
    total, prev = 0, 0
    for ch in reversed(tok):
        v = _ROMAN_VAL[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    if not 2 <= total <= 89:
        return None
    return total if _to_roman(total) == tok else None


def _to_roman(n: int) -> str:
    out = ""
    for v, r in ((50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += r
            n -= v
    return out


def numeral_values(text: str, *, tokens: bool = False) -> list[tuple[int, int, int]]:
    """``(start, end, value)`` over the folded ``text`` of every non-digit numeral (digits are the
    regex forms' job): CJK numerals of >= 2 characters (incl. a ``第`` prefix; a lone unit such as
    百 in 百度 is not a number), number words (``wsbench.numerals``; in prose only >= 11) and
    uppercase Roman numerals (raw text)."""
    out: list[tuple[int, int, int]] = []
    for a, b, v, kind in _numerals.tokens(text):
        cjk_ok = kind == "cjk" and (b - a >= 2 or tokens)
        if cjk_ok or (kind == "word" and (tokens or v >= MIN_WORD_VALUE_PROSE)):
            out.append((a, b, v))
    for m in _ROMAN.finditer(text):
        v = roman_value(m.group(0))
        if v is not None:
            out.append((m.start(), m.end(), v))
    return out


def head_of(text: str) -> str:
    """A statement line's leading answer: its text before the first ``NOTE_MARK``."""
    for m in NOTE_MARK.finditer(text):
        head = text[: m.start()]
        if DASH_MARK.fullmatch(m.group(0)) and len(head.split()) > DASH_HEAD_MAX_WORDS:
            continue
        return head
    return text


def answer_heads(stmts: Sequence[digest.Line]) -> list[str]:
    """The heads of ``digest.statement_lines`` Lines (one per top-level bullet of a prose sample;
    an unbulleted sample is one Line). Token lines have no head."""
    return [head_of(ln.text) for ln in stmts if ln.pieces is None]


def values_in(head: str) -> list[float]:
    """Every standalone number's value in ``head`` (digits incl. decimals and thousands
    separators via ``digest.number_value``; CJK numerals, number words, Roman numerals)."""
    vals = [v for m in _NUM_TOKEN.finditer(fold(head)) if (v := digest.number_value(m.group(0)))
            is not None]  # fmt: skip
    vals += [float(v) for _a, _b, v in numeral_values(head)]
    return vals


def contradicts(head: str, picked: str, forms: OptionForms, numeric: bool) -> bool:
    """G1: the head names some option but not ``picked``; on a numeric item also a standalone
    number whose value differs from ``picked``'s while the head does not name ``picked``."""
    named = forms.named(head, numerals=True)
    if picked in named:
        return False
    if named:
        return True
    if numeric:
        want = number_of(picked)
        return want is not None and any(abs(v - want) > 1e-9 for v in values_in(head))
    return False


def boundary_ok(quote: str, line_text: str) -> bool:
    """C7.3 (added on top of ``digest.quote_ok``): the folded quote occurs in the folded line with
    no Latin letter or digit directly beside it, on each side where the quote itself begins or
    ends in one (a quote "boost clock of 5.7" cut from "5.75" fails)."""
    fq, ft = digest.fold_quote(quote), digest.fold_quote(line_text)
    if not fq:
        return False
    need_l, need_r = bool(_LATIN_ALNUM.match(fq[0])), bool(_LATIN_ALNUM.match(fq[-1]))
    i = ft.find(fq)
    while i >= 0:
        j = i + len(fq)
        left = not need_l or i == 0 or not _LATIN_ALNUM.match(ft[i - 1])
        right = not need_r or j == len(ft) or not _LATIN_ALNUM.match(ft[j])
        if left and right:
            return True
        i = ft.find(fq, i + 1)
    return False


def _tok(t: str) -> str:
    return fold(t).strip()


def token_named(pieces: Sequence[str], forms: OptionForms, aliases: Mapping[str, Sequence[str]]
                ) -> set[str]:  # fmt: skip
    """Options one token list names (C7.2; tokens of ONE list only): a token or the list's
    tokens joined in order name it under the forms (numerals included); (a) a first piece of
    >= 4 letters that is a prefix of a single-word form covering >= 60% of it and a prefix of no
    other option's form; (b) every word of a multi-word form is a token of the list, any order."""
    toks = [t.strip() for t in pieces if t.strip()]
    out = set(forms.named(" ".join(toks), numerals=True, tokens=True))
    for t in toks:
        out |= forms.named(t, numerals=True, tokens=True)
    folded = {_tok(t) for t in toks}
    by_opt = {o: {_tok(f) for f in (o, *fs) if _tok(f)} for o, fs in aliases.items()}
    for t in folded:
        if sum(ch.isalpha() for ch in t) < 4:
            continue
        for o, fs in by_opt.items():
            single = [f for f in fs if " " not in f and f.startswith(t) and len(t) >= 0.6 * len(f)]
            if not single:
                continue
            others = [f for o2, fs2 in by_opt.items() if o2 != o for f in fs2]
            if not any(f.startswith(t) for f in others):
                out.add(o)
    for o, fs in by_opt.items():
        for f in fs:
            words = f.split()
            if len(words) >= 2 and all(w in folded for w in words):
                out.add(o)
    return out

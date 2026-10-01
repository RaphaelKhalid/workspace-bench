"""chain_intermediates (chain-free-2026-09-16) and arithmetic_intermediates (arith-free-2026-09-23,
arith-free-batched-2026-09-23): the prompt-blind FREE-RECALL number judge.

Original calls (evals/<family>/README.md, ``prompts.py``, ``judge.py``):
  * ``chain_free``  (chain, one call per (item, layer) at the last token, or per cell with
    ``cells=all``): SYSTEM + USER = "Lens output:\\n<<<\\n{readout}\\n>>>\\n\\nWhich number(s) ...?",
    schema {states_value: bool, values: [int] (ranked, <= 3), basis: arithmetic | stated_result |
    numeral_bag | none, quote: str}.
  * ``arith_free``  (arith ``cells=frozen``, one call per cell): same shape, values are numbers.
  * ``arith_free_batch`` (arith ``cells=all``, the run of record, one call per (item, layer)):
    SYSTEM_BATCH + entries "[k] pos=<p> token=<json>: <readout>" (a token lens: "tokens: ..."),
    schema {entries: [{k, values, basis, quote}, ...]}.
  The judge is BLIND to the gold. The family keeps a named value only when the readout writes it
  (chain: the TOP value as a whole number, ``names_number``; arith: every value, ``quantities``)
  or, for the top value only, the quote is verbatim in the readout (arith: and not a bare number,
  and containing a digit or Chinese numeral). chain passes on values[0]; arith passes on ANY kept
  value within tolerance, so arith reads ranks 2-3 too.

Jev port (state = the verbatim (system, user) pair; one request per original call). Jev cannot
emit numbers, so the numbers the judge could name are enumerated DETERMINISTICALLY from the
readout text (digits, English number words, Chinese numerals incl. 百/千/万/负/点) and Jev picks
among them. Per cell (``_k`` suffix per entry in the batched call):
  * ``top``   Choice over the candidates + "none" ("which ONE number does the output present MOST
              clearly as a COMPUTED VALUE"; the lens framing, job sentence and rule sentences
              verbatim), K=3 option orders averaged.
  * ``count`` Score 0..3: how many different numbers the output presents as computed values
              (rule sentences condensed). values = the top pick, then the next
              max(1, argmax(count)) - 1 candidates by top-Choice probability ("rank them, most
              clearly a computed result first", capped at three).
              values = [] (states_value false) when the top argmax is "none" OR argmax(count) is
              0: both are the prompt's "presents no number as a computed value" decision.
  * ``basis`` Choice arithmetic / stated_result / numeral_bag (the enum has no definition in the
              prompt; each option paraphrases the rule sentence that names it); "none" iff
              values is empty.
  Batched call (arith ``cells=all``, ~40 entries must fit ONE request under ~20k tokens): per
  entry a COMPACT set — the top and count questions reference the rules in judge_instructions
  (SYSTEM_BATCH, verbatim in the state) instead of repeating them, options carry no context
  snippet, K = the largest of 3/2/1 that fits (usually 1 for a full 40-entry call), and basis
  (read by no metric) is filled deterministically: bag -> numeral_bag, top written after "="
  -> arithmetic, else stated_result.
  quote = the top value's written form in the readout: the first of its forms (digit numeral
  first) that the family's OWN top-value check accepts (chain: names_number / quote_in; arith:
  verified), else the digit form / first form. Always verbatim, so the family's quote check
  behaves as it would for a faithful judge (a Chinese numeral is credited through the quote; an
  English word is credited in chain, not in arith, exactly as for the judge of record).
  Review (Sep 30): chain also enumerates whole numbers written as decimals ("14.0", credited via
  the quote); arith skips list-marker / step-label occurrences exactly where ``quantities`` does;
  the batched call has a last "bare options" tier before Jev's 32k limit. See ports-notes.
A cell with no number in its readout is answered without a call (values [] / none), as a
faithful judge would. Raw probabilities for every question sit under ``_jev``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .base import (
    Direct,
    JevCall,
    Port,
    argmax,
    choice,
    choice_variants,
    fmt_num,
    jev_meta,
    merge_choice,
    merge_score,
    score,
    verbatim_state,
)

K_VARIANTS = 3
MAX_VALUES = 3
TOKEN_BUDGET = 20_000  # PORTING: keep one request under ~20k tokens (limit 32k)
HARD_BUDGET = 26_000  # batch: above this at K=1 the bare option tier is used (Jev limit 32k)
CHARS_PER_TOKEN = 2.4  # of the JSON-encoded request (live toy: ~2.5 incl. overhead; kept conservative)
MAX_CANDIDATES = 40  # a pathological readout (hundreds of numerals) keeps its first 40 values

# ---------------------------------------------------------------- verbatim prompt sentences

JOB = (
    "name the number(s) that this output presents as a COMPUTED VALUE — a result, an "
    "intermediate, a total, a \"the answer is X\". Rank them, most clearly a computed result "
    "first, at most three."
)
RULES = (
    "- Do NOT list numbers that appear as operands, quantities, labels, list indices, years, "
    "counts of items, or parts of unrelated prose. Only numbers the output presents as something "
    "that was worked out.\n"
    "- If the output states arithmetic with both operands and a result (\"16 - 2 = 14\"), list "
    "the RESULT (14), not the operands.\n"
    "- A bag of loose numerals with no arithmetic around them still counts: if the bag is "
    "dominated by one value or a tight cluster, list what it points at, most frequent or most "
    "prominent first.\n"
    "- Never do any arithmetic of your own. You do not know the task, so you cannot know what "
    "the right answer is; only report what the text itself puts forward."
)
NONE_OPT = (
    "none: the output presents no number as a computed value. That is a normal and common "
    "answer — do not invent one."
)
COUNT_LEVELS = (
    "0: the output presents no number as a computed value (a normal and common answer).",
    "1: the output presents exactly one number as a computed value.",
    "2: the output presents two different numbers as computed values.",
    "3: the output presents three or more different numbers as computed values.",
)
BASIS_OPTS = {
    "arithmetic": (
        "arithmetic: the output states arithmetic with both operands and a result (\"16 - 2 = "
        "14\") and the value is that RESULT."
    ),
    "stated_result": (
        "stated_result: the output states the value as something that was worked out — a "
        "result, an intermediate, a total, a \"the answer is X\" — without writing out the "
        "arithmetic that produced it."
    ),
    "numeral_bag": (
        "numeral_bag: a bag of loose numerals with no arithmetic around them, dominated by one "
        "value or a tight cluster; the value is what the bag points at."
    ),
}


LENS = (  # the system prompt's framing sentence, verbatim up to the subject
    "This is the output of a \"lens\" that tries to verbalize what a language model is computing "
    "internally. "
)


TOP_Q = (
    f"{LENS}Your job: {JOB} Which ONE number does this output present MOST clearly as a "
    "computed value (the one to rank first)? Each option is a number the output writes, with "
    f"where it is written.\n\nRules:\n{RULES}"
)
COUNT_Q = (
    f"{LENS}How many different numbers does this output present as a COMPUTED VALUE — a "
    "result, an intermediate, a total, a \"the answer is X\"? Count only numbers presented as "
    "something that was worked out: not operands, quantities, labels, list indices, years, "
    "counts of items, or parts of unrelated prose; for arithmetic with operands and a result "
    "count only the RESULT; a bag of loose numerals dominated by one value or a tight cluster "
    "counts what it points at."
)
BASIS_Q = (
    "On what basis does this output present the number it most clearly puts forward as a "
    "computed value?"
)


# ---------------------------------------------------------------- candidate numbers

_FULLWIDTH = str.maketrans(
    "".join(chr(0xFF10 + d) for d in range(10)) + "．，－−", "0123456789.,--"
)
# a whole number in chain's sense (``names_number``): not inside 10, 2019 or 10.83
_BINARY = re.compile(r"[0-9A-Za-z)\]]")  # a "-" right after these is an operator, not a sign
_INT = re.compile(r"(?<!\d)(?<!\d\.)(-?)(\d+)(?!\d)(?!\.\d)")
# chain, review fix: a whole number written as a decimal ("14.0", "14.00"). names_number cannot
# read it, but chain's verdict credits the top value through ANY verbatim non-digit quote, so a
# judge naming 14 with quote "14.0" is credited (5 real rows write the gold only this way).
_ZDEC = re.compile(r"(?<!\d)(?<!\d\.)(-?)(\d+)\.0+(?!\d)(?!\.\d)")
# arith, review fix: the spans the family's ``quantities`` strips before reading numerals (list
# markers "2. foo" and "step N" labels), located in the ORIGINAL text so an occurrence inside them
# is neither counted nor shown as a context.
_LIST_MARK = re.compile(r"(?m)^[ \t]*(?:-[ \t]+)?\d+\.[ \t]+(?=[A-Za-z*_#`(])")
_STEP = re.compile(r"(?i)step\s*\d+")
_CN_DIG = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNIT = {"十": 10, "百": 100, "千": 1000}
_CN_RUN = re.compile(r"负?[零〇一二两三四五六七八九十百千万]+(?:点[零〇一二三四五六七八九]+)?")
_EN_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
_EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_EN_RUN = re.compile(
    r"(?<![A-Za-z])(?:(minus|negative)[ -])?(?:("
    + "|".join(_EN_TENS)
    + r")(?:[- ](one|two|three|four|five|six|seven|eight|nine))?|("
    + "|".join(sorted(_EN_ONES, key=len, reverse=True))
    + r"))(?![A-Za-z])",
    re.IGNORECASE,
)


def cn_value(s: str) -> float | None:
    """Chinese numeral -> number: 十四 14, 二十三 23, 一百零五 105, 三千二百 3200, 五万 50000,
    负五十一 -51, 三点五 3.5, 二〇二四 2024 (digit string). None when it is not a number (a bare
    unit like 千万)."""
    neg = s.startswith("负")
    s = s[1:] if neg else s
    intpart, _, frac = s.partition("点")
    if not intpart:
        return None
    if all(c in _CN_DIG for c in intpart):  # a digit string: 七 7, 二〇二四 2024
        v: float = int("".join(str(_CN_DIG[c]) for c in intpart))
    else:
        total, section, digit, seen_digit = 0, 0, None, False
        for c in intpart:
            if c in _CN_DIG:
                digit, seen_digit = _CN_DIG[c], True
            elif c in _CN_UNIT:
                if digit is None and c != "十":
                    return None
                section += (1 if digit is None else digit) * _CN_UNIT[c]
                digit = None
            elif c == "万":
                if digit is None and section == 0:
                    return None
                total += (section + (digit or 0)) * 10000
                section, digit = 0, None
            else:
                return None
        v = total + section + (digit or 0)
        if not seen_digit and v == 0:
            return None
    if frac:
        v = float(f"{int(v)}.{''.join(str(_CN_DIG[c]) for c in frac)}")
    return -v if neg else v


def _en_value(m: re.Match) -> int:
    if m.group(2):
        v = _EN_TENS[m.group(2).lower()] + (_EN_ONES.index(m.group(3).lower()) if m.group(3) else 0)
    else:
        v = _EN_ONES.index(m.group(4).lower())
    return -v if m.group(1) else v


@dataclass
class Cand:
    value: float
    surfaces: list[str] = field(default_factory=list)  # verbatim written forms, first first
    contexts: list[str] = field(default_factory=list)
    count: int = 0
    first: int = 0
    digit: str | None = None  # the digit-numeral surface, if the readout writes one


def _context(text: str, a: int, b: int, width: int = 24) -> str:
    lo, hi = max(0, a - width), min(len(text), b + width)
    s = text[lo:hi].replace("\n", " ⏎ ")
    return ("…" if lo else "") + s.strip() + ("…" if hi < len(text) else "")


def candidates(text: str, *, integers: bool) -> list[Cand]:
    """Every number ``text`` writes, merged by value, in order of first appearance: digit
    numerals (ASCII or fullwidth; chain: whole numbers only, as ``names_number`` reads them;
    arith: decimals and thousands separators too), English number words to ninety-nine (with
    "minus"), Chinese numerals (负/点/十/百/千/万). chain: a "-" is a sign only when it does not
    follow a digit, ASCII letter or closing bracket ("16-2" is 16 and 2)."""
    t = text.translate(_FULLWIDTH)
    found: list[tuple[int, int, float, str, bool]] = []  # (start, end, value, surface, is_digit)
    if integers:
        for rx, is_digit in ((_INT, True), (_ZDEC, False)):
            for m in rx.finditer(t):
                sign = m.group(1)
                a = m.start()
                if sign and a > 0 and _BINARY.match(t[a - 1]):
                    sign, a = "", a + 1
                found.append((a, m.end(), float(int(sign + m.group(2))), text[a : m.end()], is_digit))
    else:
        # exactly the numerals the family's verifier reads (``quantities``: its regex, list
        # markers "2. foo" and "step 1" labels excluded), so a digit candidate is keepable
        from wsbench.evals.arithmetic_intermediates.judge import _NUMERAL, quantities

        readable = quantities(text)
        masked = [(m.start(), m.end()) for rx in (_LIST_MARK, _STEP) for m in rx.finditer(t)]
        for m in _NUMERAL.finditer(t):
            if any(a <= m.start() < b for a, b in masked):
                continue  # a list marker / step label occurrence: the verifier never reads it
            try:
                v = float(m.group(0).replace(",", ""))
            except ValueError:
                continue
            if any(abs(q - v) <= 1e-6 * max(1.0, abs(v)) for q in readable):
                found.append((m.start(), m.end(), v, text[m.start() : m.end()], True))
    for m in _EN_RUN.finditer(t):
        v = float(_en_value(m))
        found.append((m.start(), m.end(), v, text[m.start() : m.end()], False))
    for m in _CN_RUN.finditer(t):
        v = cn_value(m.group(0))
        if v is None or (integers and v != int(v)):
            continue
        found.append((m.start(), m.end(), float(v), text[m.start() : m.end()], False))
    found.sort(key=lambda f: (f[0], -f[1]))
    by_val: dict[float, Cand] = {}
    for a, b, v, surf, is_digit in found:
        c = by_val.get(v)
        if c is None:
            if len(by_val) >= MAX_CANDIDATES:
                continue
            c = by_val[v] = Cand(value=v, first=a)
        c.count += 1
        if surf not in c.surfaces:
            c.surfaces.append(surf)
        if len(c.contexts) < 2:  # the first two occurrences (review: not only new surfaces)
            ctx = _context(text, a, b)
            if ctx not in c.contexts:
                c.contexts.append(ctx)
        if is_digit and c.digit is None:
            c.digit = surf
    return sorted(by_val.values(), key=lambda c: c.first)


def _tokens(obj: dict) -> float:
    return len(json.dumps(obj, ensure_ascii=False)) / CHARS_PER_TOKEN


def _num(v: float, integers: bool) -> int | float:
    return int(v) if integers or v == int(v) else v


def _option_text(c: Cand, integers: bool, brief: bool, bare: bool = False) -> str:
    head = fmt_num(_num(c.value, integers))
    if bare:  # last-resort batch tier: the value, plus its written form only when not digits
        times = f", {c.count} times" if c.count > 1 else ""
        form = "" if c.digit is not None else f"written {json.dumps(c.surfaces[0], ensure_ascii=False)}"
        inner = ", ".join(x for x in (form, times.lstrip(", ")) if x)
        return f"{head} ({inner})" if inner else head
    forms = ", ".join(json.dumps(s, ensure_ascii=False) for s in c.surfaces[: 2 if brief else 4])
    times = f", {c.count} times" if c.count > 1 else ""
    if brief:
        return f"{head} (written {forms}{times})"
    ctx = " / ".join(json.dumps(x, ensure_ascii=False) for x in c.contexts)
    return f"{head} (written {forms}{times}; in {ctx})"


# ---------------------------------------------------------------- readout recovery

_SCORED_BAG = re.compile(r"(?s)^.*? \(-?\d+\.\d{2}\)(?: \| .*? \(-?\d+\.\d{2}\))*$")


def unscore_bag(text: str) -> str:
    """A scored token bag ``tok (0.31) | tok (0.20)`` -> ``tok | tok`` (the family verifies a bag
    against its tokens, never its scores). Anything else is returned unchanged."""
    if _SCORED_BAG.match(text):
        return re.sub(r" \(-?\d+\.\d{2}\)(?= \| |$)", "", text)
    return text


def single_readout(user: str) -> str | None:
    head, tail = "Lens output:\n<<<\n", "\n>>>\n\nWhich number(s) does this output present"
    i, j = user.find(head), user.rfind(tail)
    if i < 0 or j < i:
        return None
    return user[i + len(head) : j]


_ENTRY = re.compile(r'^\[(\d+)\] pos=(-?\d+) token=("(?:[^"\\]|\\.)*"): ?', re.M)


def batch_entries(user: str) -> list[tuple[int, str, bool]] | None:
    """The batched user's entries as (k, readout text, is_bag), k = 1..n in order."""
    head = "Lens outputs, one per read position:\n\n"
    tail = "\n\nFor each entry, which number(s) does its output present as a computed value?"
    if not user.startswith(head) or not user.endswith(tail):
        return None
    body = user[len(head) : len(user) - len(tail)]
    heads = []
    expect = 1
    for m in _ENTRY.finditer(body):
        if int(m.group(1)) == expect:
            heads.append(m)
            expect += 1
    if not heads or heads[0].start() != 0:
        return None
    out = []
    for n, m in enumerate(heads):
        end = heads[n + 1].start() - 2 if n + 1 < len(heads) else len(body)
        txt = body[m.end() : end]
        bag = txt.startswith("tokens: ")
        out.append((n + 1, txt[len("tokens: ") :] if bag else txt, bag))
    return out


# ---------------------------------------------------------------- questions and answers


def _cell_questions(sfx: str, cands: list[Cand], integers: bool, k: int, seed: str) -> dict:
    """The full per-cell question set (single-cell calls): the rule sentences ride in the
    top question, the option texts carry where each number is written."""
    opts = {f"c{i + 1}": _option_text(c, integers, False) for i, c in enumerate(cands)}
    opts["none"] = NONE_OPT
    qs = choice_variants(f"top{sfx}", TOP_Q, opts, k=k, seed=seed)
    qs[f"count{sfx}"] = score(COUNT_Q, COUNT_LEVELS)
    qs[f"basis{sfx}"] = choice(BASIS_Q, BASIS_OPTS)
    return qs


def _entry_questions(kk: int, cands: list[Cand], k: int, seed: str, bare: bool = False) -> dict:
    """The COMPACT per-entry set of a batched call (~40 entries must fit one request): the
    rules are referenced in judge_instructions (the verbatim SYSTEM_BATCH, in the state) rather
    than repeated per entry, options are brief, and basis is not asked (see _basis_filler)."""
    opts = {f"c{i + 1}": _option_text(c, False, True, bare) for i, c in enumerate(cands)}
    opts["none"] = f"none: entry [{kk}]'s output presents no number as a computed value."
    top = (
        f"Entry [{kk}] only (judged on its own; its header is not part of its output): which "
        "ONE number does its output present MOST clearly as a COMPUTED VALUE — a result, an "
        "intermediate, a total, a \"the answer is X\" (the one to rank first)? Apply the Rules "
        "in judge_instructions."
    )
    count = (
        f"Entry [{kk}] only: how many different numbers does its output present as a COMPUTED "
        "VALUE, applying the Rules in judge_instructions?"
    )
    qs = choice_variants(f"top_{kk}", top, opts, k=k, seed=seed)
    qs[f"count_{kk}"] = score(count, ("0 (none)", "1", "2", "3 or more"))
    return qs


_EQ_BEFORE = r"=\s*[*$\{(\s]*"


def _basis_filler(readout: str, lead: Cand, bag: bool) -> str:
    """basis for a batched entry (no metric reads it): a token bag is a numeral_bag; a top value
    written right after "=" is arithmetic; anything else a stated_result."""
    if bag:
        return "numeral_bag"
    if lead.digit and re.search(_EQ_BEFORE + re.escape(lead.digit) + r"(?!\d)", readout):
        return "arithmetic"
    return "stated_result"


def _restrict(probs: dict[str, float] | None, keys: list[str]) -> dict[str, float] | None:
    if not probs:
        return None
    p = {k: float(probs.get(k, 0.0)) for k in keys}
    return p if sum(p.values()) > 0 else None


def _votes(answers: dict, qid: str, keys: list[str]) -> dict[str, float] | None:
    v = [a.get("choice") for q, a in answers.items() if q.startswith(f"{qid}__v") and isinstance(a, dict)]
    v = [x for x in v if x in keys]
    return {k: v.count(k) / len(v) for k in keys} if v else None


def _quote_for(lead: Cand, readout: str, integers: bool) -> str:
    """The top value's quote: the first of its written forms (digit numeral first, then the
    others in order of appearance) that the family's OWN top-value check accepts on this readout
    (chain: ``names_number`` for a digit-only quote, else ``quote_in``; arith: ``verified``).
    Review fix: the first version always took the digit form, else the first form, so a value
    written "fifteen" and "十五" was quoted "fifteen" (never credited in arith) and one written
    "６" and "六" was quoted "６" (a digit-only quote ``names_number`` cannot read). When no form
    passes, the default (digit form, else first form) is kept: a faithful judge fails there too."""
    forms = ([lead.digit] if lead.digit is not None else []) + [
        s for s in lead.surfaces if s != lead.digit
    ]
    if integers:
        from wsbench.evals.chain_intermediates.judge import names_number
        from wsbench.family import quote_in

        def ok(q: str) -> bool:
            return names_number(int(q), readout) if q.isdigit() else quote_in(q, readout)

    else:
        from wsbench.evals.arithmetic_intermediates.judge import verified

        def ok(q: str) -> bool:
            return verified(lead.value, readout, q, top=True)

    for q in forms:
        q = q.strip()
        if q and ok(q):
            return q
    return forms[0].strip()


def _cell_result(
    answers: dict, sfx: str, cands: list[Cand], integers: bool, readout: str
) -> dict | None:
    """(values, basis, quote, probs) for one cell from its typed answers; None if unanswered."""
    keys = [f"c{i + 1}" for i in range(len(cands))] + ["none"]
    top = _restrict(merge_choice(answers, f"top{sfx}"), keys) or _votes(answers, f"top{sfx}", keys)
    if top is None:
        return None
    pick = argmax(top, keys)
    cnt = _restrict(merge_score(answers, f"count{sfx}"), ["0", "1", "2", "3"])
    n_count = int(argmax(cnt, ["0", "1", "2", "3"])) if cnt else 1  # no count answer: top only
    bas = _restrict(merge_choice(answers, f"basis{sfx}"), list(BASIS_OPTS))
    meta = {
        "top": {k: round(v, 4) for k, v in top.items()},
        "count": {k: round(v, 4) for k, v in cnt.items()} if cnt else None,
        "basis": {k: round(v, 4) for k, v in bas.items()} if bas else None,
        "candidates": [fmt_num(_num(c.value, integers)) for c in cands],
    }
    # "set states_value false and return an empty list": either decision of that criterion
    # (the top pick is "none", or the count is 0) empties the list. The top Choice is relative
    # ("which one most clearly") and rarely abstains on noisy numerals; the count is absolute.
    meta["gate"] = "top" if pick == "none" else "count" if n_count == 0 else None
    if meta["gate"]:
        return {"values": [], "basis": "none", "quote": "", "_meta": meta, "_lead": None}
    n = min(MAX_VALUES, max(1, n_count), len(cands))
    ranked = [pick] + sorted(
        (k for k in keys[:-1] if k != pick), key=lambda k: (-top[k], keys.index(k))
    )
    chosen = [cands[int(k[1:]) - 1] for k in ranked[:n]]
    values = [_num(c.value, integers) for c in chosen]
    lead = chosen[0]
    basis = argmax(bas, list(BASIS_OPTS)) if bas else None  # None: the caller fills it
    quote = _quote_for(lead, readout, integers)
    return {"values": values, "basis": basis, "quote": quote, "_meta": meta, "_lead": lead}


@dataclass
class _Cell:
    k: int | None
    readout: str
    cands: list[Cand]
    bag: bool = False


class FreeRecall(Port):
    """``chain_free`` (integers) and ``arith_free`` (numbers): one cell per call."""

    def __init__(self, name: str, schema_name: str, integers: bool, compare: tuple[str, ...]):
        self.name = name
        self.schema_names = (schema_name,)
        self.integers = integers
        self.compare_fields = compare

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        readout = single_readout(user)
        if readout is None:
            return Direct(None)
        text = unscore_bag(readout)
        cands = candidates(text, integers=self.integers)
        if not cands:
            return Direct(
                {"states_value": False, "values": [], "basis": "none", "quote": "",
                 "_jev": jev_meta({}, direct="no number written in the readout")}
            )
        qs = _cell_questions("", cands, self.integers, K_VARIANTS, user)
        return JevCall(verbatim_state(system, user), qs, {"cells": [_Cell(None, text, cands)]})

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        cell = call.ctx["cells"][0]
        r = _cell_result(answers, "", cell.cands, self.integers, cell.readout)
        if r is None:
            return None
        meta = r.pop("_meta")
        lead = r.pop("_lead")
        if r["basis"] is None:  # the basis answer did not land
            r["basis"] = _basis_filler(cell.readout, lead, False)
        return {"states_value": bool(r["values"]), **r, "_jev": jev_meta(answers, **meta)}


class FreeRecallBatch(Port):
    """``arith_free_batch``: one (item, layer) per call, one result per entry [k]."""

    name = "arith_free_batch"
    schema_names = ("arith_free_batch",)
    compare_fields = ("pass", "hits_at", "kept", "values", "top1_hit")
    integers = False

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        entries = batch_entries(user)
        if entries is None:
            return Direct(None)
        cells = []
        for k, txt, bag in entries:
            text = unscore_bag(txt) if bag else txt
            cells.append(_Cell(k, text, candidates(text, integers=False), bag))
        live = [c for c in cells if c.cands]
        if not live:
            return Direct(
                {"entries": [{"k": c.k, "values": [], "basis": "none", "quote": ""} for c in cells],
                 "_jev": jev_meta({}, direct="no number written in any entry")}
            )
        state = verbatim_state(system, user)
        # the largest K whose request fits TOKEN_BUDGET (K=1 is sent even when it does not)
        # review fix: a last "bare" tier (options = the value, its count, and its written form
        # only when it is not digits) for a K=1 request that would still near Jev's 32k limit
        # (real NLA-length prose: ~28.8k estimated at K=1); otherwise the whole call errors and
        # its ~40 cells go unjudged.
        tiers = [(K_VARIANTS, False), (2, False), (1, False), (1, True)]
        for n, (kv, bare) in enumerate(tiers):
            qs: dict = {}
            for c in live:
                qs.update(_entry_questions(c.k, c.cands, kv, f"{user}|{c.k}", bare))
            est = _tokens(state) + _tokens(qs)
            limit = HARD_BUDGET if n == len(tiers) - 2 else TOKEN_BUDGET
            if est <= limit or n == len(tiers) - 1:
                break
        return JevCall(
            state, qs,
            {"cells": cells, "k_variants": kv, "bare_options": bare, "est_tokens": round(est)},
        )

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        out, metas, landed = [], {}, 0
        for c in call.ctx["cells"]:
            if not c.cands:
                out.append({"k": c.k, "values": [], "basis": "none", "quote": ""})
                continue
            r = _cell_result(answers, f"_{c.k}", c.cands, False, c.readout)
            if r is None:  # an unanswered entry is left out: the family counts it unjudged
                continue
            landed += 1
            metas[str(c.k)] = r.pop("_meta")
            lead = r.pop("_lead")
            if r["basis"] is None:
                r["basis"] = _basis_filler(c.readout, lead, c.bag)
            out.append({"k": c.k, **r})
        if not landed:
            return None
        return {
            "entries": out,
            "_jev": jev_meta(
                answers, per_entry=metas, k_variants=call.ctx["k_variants"],
                bare_options=call.ctx.get("bare_options", False),
                est_tokens=call.ctx["est_tokens"],
            ),
        }


PORTS = [
    FreeRecall("chain_free", "chain_free", True, ("pass", "kind_by_layer", "named_by_layer", "hitting_layers")),
    FreeRecall("arith_free", "arith_free", False, ("pass", "hits_at", "kept", "values", "top1_hit")),
    FreeRecallBatch(),
]

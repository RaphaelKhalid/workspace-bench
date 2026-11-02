"""The regex contract of the six multi-token families — a deterministic port of the source repo's
conjunctive bank scorer (``olens_suite/bank/{matching,contract,conjunctive}.py`` and
``olens_sglang/{score_targets,common}.py`` at ``global-workspace-clean``), the scorer of record
again since 2026-09-23 (Camila: "regex on the multitoken please").

The rules, in the order a cell is scored:

1. **Samples.** A prose cell's samples, or a token lens's top-k strings (each token is one
   sample, as the loader decoded it to text — ``wsbench.bpe``; until 2026-10-29 byte-level
   pieces of non-Latin tokens reached this scorer as mojibake, as the source scorer saw them).
   Chat scaffolding (``<|im_start|>``, ``<|im_end|>``, ``<think>``, ``</think>``,
   ``<explanation>`` tags) is stripped first (``extract_phrase``).
2. **Units.** ``scored_units``: every ``units[]`` entry of the item; when the bank contract is
   ``multi_token`` and the unit does not set ``multi_token: false`` (the language units do),
   only forms the bank stamped as multi-token stay (``probe_token_lens.units[role][lang][i] >
   1`` — the source's strict count: min over case variants x bare/leading-space, so a form any
   single Qwen3.6-27B token could equal is never creditable). ``include_target`` banks
   (multihop_mt_v2) add an OPTIONAL ``target`` unit from ``target`` + ``target_alts``, likewise
   filtered (``probe_token_lens.target`` / ``.target_alts``), minus forms a unit already covers.
   A REQUIRED unit left without a creditable form is a bank error.
3. **A form hits a sample** (``unicode_word_matcher``): both sides folded (NFKD, combining marks
   dropped, the right single quotation mark -> ``'``, casefold). A form containing CJK or
   Hangul, or not made of word characters, is a plain substring; a wordy form is a
   word-boundary match with ``[\\s-]+`` between its words (``Bohr magneton`` ==
   ``Bohr-magneton``); a purely numeric form must sit in
   ANSWER position (after ``=``, ``->``, ``equals``, ``answer/result/value/total/sum/product/
   quotient [is][:]``, their Chinese counterparts, or alone at the start of the sample, never
   as a prefix of a longer number; a CJK numeral in those positions counts when it parses to
   the value). A form is matched against ONE sample at a time — a phrase is never assembled
   across two samples or two top-k tokens.
4. **A unit hits at a layer** when any of its forms hits any single sample of any row at that
   layer (``layer_unit_hits``: role -> the languages whose forms hit, in authored order).
5. **A layer passes an item** when EVERY required unit hits there; **the item passes** at any
   layer (``item_result``). ``any_hit`` (some unit hit somewhere) is the parent-comparable extra.

What this means for a top-k token lens: a strictly multi-token form can never be one token, so
on the raw bag required multi-token units are unreachable by construction — the source's stated
asymmetry. The bag -> prose interpretation step is deleted (plan 0032 §2.3): natively the
contract matches raw tokens; under summary mode (the default) every method goes through the one
digest, and a word split across adjacent positions reaches the contract through
``digest.gate_texts(joined=True, forms=)``.
"""

import dataclasses
import re
import unicodedata
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from wsbench.multitoken.languages import RE_PREFIX, is_frozen_language_unit, naming_forms

__all__ = [
    "SCORER_VERSION",
    "BankContract",
    "ScoredUnit",
    "contract_for",
    "contract_json",
    "extract_phrase",
    "fold",
    "fold_accents",
    "fuzzy_form_in",
    "hit_forms",
    "item_result",
    "layer_passes",
    "layer_unit_hits",
    "parse_cjk_numeral",
    "scored_units",
    "unicode_word_matcher",
]

SCORER_VERSION = "mt-regex-2026-10-30"  # the contract on the samples (raw tokens for token arms)
# 2026-10-30 (plan 0033 M2): numeric answer markers match in any case ("**Answer:** 429",
# "Result: 429"); the ONE campaign bump of this constant, shared by every mt family
# (mt-regex-2026-09-23 before); plan 0040 did not bump it: its
# ``case_sensitive`` path is reached only by a bank unit that lists forms there (the v2
# multilingual banks, told apart by their ``+v2`` instrument tag)
# the retired token-arm stamp "mt-regex-summarized-decoded-2026-10-27" (a bag -> prose step,
# Camila 2026-09-23) is gone with that step: Camila 2026-10-30 "make sure that we have gotten rid
# of the individual jlens summarizer step" (plan 0032 §2.3)

# ---------------------------------------------------------------------------------------------
# olens_sglang/common.py — scaffolding stripped from every sample before scoring
# ---------------------------------------------------------------------------------------------
_STRIP_PATTERNS = re.compile(
    r"</?explanation>|<\|im_start\|>(system|user|assistant)?|<\|im_end\|>|<think>|</think>"
)


def extract_phrase(text: str) -> str:
    """Strip chat scaffolding + ``<explanation>`` tags from one lens sample."""
    return _STRIP_PATTERNS.sub("", text).strip()


# ---------------------------------------------------------------------------------------------
# global_workspace/glossary.py — the two numeric helpers the matcher needs
# ---------------------------------------------------------------------------------------------
FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９．", "0123456789.")  # noqa: RUF001
CJK_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}
CJK_DIGIT |= {"七": 7, "八": 8, "九": 9}
CJK_UNIT = {"十": 10, "百": 100, "千": 1000}


def parse_cjk_numeral(s: str) -> int | None:
    """Standard CJK numerals up to 9999 (十五=15, 四十九=49, 三百=300, 两=2), else ``None``."""
    if not s or any(c not in CJK_DIGIT and c not in CJK_UNIT for c in s):
        return None
    total, current = 0, 0
    for c in s:
        if c in CJK_DIGIT:
            current = CJK_DIGIT[c]
        else:
            total += (current or 1) * CJK_UNIT[c]
            current = 0
    return total + current


# ---------------------------------------------------------------------------------------------
# olens_suite/bank/matching.py — hit semantics for conjunctive units
# ---------------------------------------------------------------------------------------------
_WRAP = r"[\s$*{(\\`：（＊]*"  # noqa: RUF001 — markdown/mathjax/fullwidth wrapping before a number
_ANSWER_CONTEXT = (
    r"(?:=|->|→|\bequals\b|\b(?:answer|result|value|total|sum|product|quotient)"
    r"\b(?:\s+is)?\s*:?"
    r"|(?:答案|结果|总和|总数)(?:是|为|：|:)?"  # noqa: RUF001
    r"|(?:值|积|商|差|和)(?:是|为|：|:)"  # noqa: RUF001
    r"|等于|得出|即|共计|共)"
)
_HAN = r"[一-鿿]"


def _number_pattern(t: str) -> str:
    """The digits of a purely numeric target with full-number identity: 84 ∉ 84.5 / 184."""
    return re.escape(t) + r"(?![\d.,]?\d)(?!\.\d)"


def _numeric_matcher(target: str) -> Callable[[str], bool]:
    """The source ``word_matcher`` numeric branch: the number in ANSWER position — after an
    answer marker (English or Chinese), or alone (possibly wrapped) at the start of the sample
    and not opening an expression — or a CJK numeral there that parses to the value. Fullwidth
    digits are folded first. The sample itself is not lowercased (digits and fullwidth handling
    are the source's), but the answer MARKERS match in any case (``Answer:``, ``**Answer:**``,
    ``Result:``, ``Equals``): a deliberate deviation from the source scorer, which matched
    lowercase markers only (Camila 2026-10-30, plan 0033 M2: "Capitalised answer markers are not
    recognised ... fix this")."""
    t = target.lower()
    num = _number_pattern(t)
    after_eq = re.compile(_ANSWER_CONTEXT + _WRAP + num, re.IGNORECASE)
    at_start = re.compile(r"\A[\s$*#>\-]*" + num + r"(?!\s*[+\-*/×÷^=]\s*\d)")  # noqa: RUF001
    cjk_numeral = re.compile(
        r"(?:" + _ANSWER_CONTEXT + _WRAP + r"|\A[\s$*#>\-]*)"
        r"([零一二两三四五六七八九十百千]{1,6})(?!" + _HAN + ")",
        re.IGNORECASE,
    )
    value = int(t)

    def numeric(text: str) -> bool:
        folded = text.translate(FULLWIDTH_DIGITS)
        if after_eq.search(folded) or at_start.search(folded):
            return True
        return any(parse_cjk_numeral(m) == value for m in cjk_numeral.findall(folded))

    return numeric


def fold_accents(s: str) -> str:
    """NFKD, strip combining marks, straighten the right single quote; case is kept."""
    s = unicodedata.normalize("NFKD", s).replace("\u2019", "'")
    return "".join(c for c in s if not unicodedata.combining(c))


def fold(s: str) -> str:
    """NFKD, strip combining marks, straighten the right single quote, casefold — applied to
    BOTH the form and the sample (Mexico with/without the accent, pointed and unpointed Hebrew,
    curly and straight apostrophes all coincide)."""
    return fold_accents(s).casefold()


_CJK_HANGUL = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_WORDY = re.compile(r"[^\W_]+(?:[\s\-'][^\W_]+)*")


def unicode_word_matcher(form: str, *, case_sensitive: bool = False) -> Callable[[str], bool]:
    """Boundary match on folded text for a unit form (any script); CJK/Hangul and non-wordy
    forms are substrings of the folded sample; purely numeric forms use the answer-context
    rule. The script decision is made on the RAW form (NFKD decomposes Hangul syllables).
    A form starting with ``languages.RE_PREFIX`` is a regular expression searched in the
    accent-folded, case-kept sample (the v2 language units' naming forms, plan F6).
    ``case_sensitive`` (a bank unit's ``case_sensitive`` list, plan 0040 B1): accents are folded
    but case is kept on both sides, so the language name "Polish" never matches "polish"."""
    if form.startswith(RE_PREFIX):  # a naming-context pattern (``languages.NAMING_OWN``)
        rx = re.compile(fold_accents(form[len(RE_PREFIX) :]))
        return lambda text: rx.search(fold_accents(text)) is not None
    norm = fold_accents if case_sensitive else fold
    f = norm(form)
    if re.fullmatch(r"\d+", f):
        return _numeric_matcher(f)
    if _CJK_HANGUL.search(form) or not _WORDY.fullmatch(f):
        return lambda text: f in norm(text)
    parts = [re.escape(w) for w in re.split(r"[\s\-]+", f) if w]
    pat = re.compile(r"(?<![^\W_])" + r"[\s\-]+".join(parts) + r"(?![^\W_])")
    return lambda text: bool(pat.search(norm(text)))


def _standalone_number_matcher(form: str) -> Callable[[str], bool]:
    """``numeric_match: "standalone"``: the integer anywhere as a standalone number (no digit,
    decimal, thousands or sign continuation on either side, no letters). None of the six banks
    sets it; ported so a bank that does scores as the source would."""
    pat = re.compile(r"(?<![\w.,-])" + re.escape(form.strip()) + r"(?![\w.,]?\d)(?!\w)")
    return lambda text: bool(pat.search(fold(text).replace(",", "")))


NumericMatch = Literal["context", "standalone"]


def hit_forms(
    samples: list[str],
    forms: Mapping[str, list[str]],
    *,
    numeric_match: NumericMatch = "context",
    case_sensitive: Collection[str] = (),
) -> list[str]:
    """The language keys of ``forms`` whose strings hit any SINGLE sample, in dict order; a form
    listed in ``case_sensitive`` keeps its case (``unicode_word_matcher``)."""

    def matcher(f: str) -> Callable[[str], bool]:
        if numeric_match == "standalone" and re.fullmatch(r"-?\d+", f.strip()):
            return _standalone_number_matcher(f)
        return unicode_word_matcher(f, case_sensitive=f in case_sensitive)

    out: list[str] = []
    for lang, fs in forms.items():
        matchers = [matcher(f) for f in fs]
        if matchers and any(m(s) for m in matchers for s in samples):
            out.append(lang)
    return out


def forms_matcher(
    forms: Mapping[str, list[str]],
    *,
    numeric_match: NumericMatch = "context",
    case_sensitive: Collection[str] = (),
) -> Callable[[list[str]], bool]:
    """``bool(hit_forms(samples, forms, ...))`` with the matchers built ONCE (a caller testing
    thousands of lines against one form set; ``hit_forms`` rebuilds them per call)."""
    ms = [
        _standalone_number_matcher(f)
        if numeric_match == "standalone" and re.fullmatch(r"-?\d+", f.strip())
        else unicode_word_matcher(f, case_sensitive=f in case_sensitive)
        for fs in forms.values()
        for f in fs
    ]
    return lambda samples: any(m(x) for m in ms for x in samples)


# ---------------------------------------------------------------------------------------------
# olens_suite/bank/contract.py — the bank contract and the per-unit form builder
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class BankContract:
    multi_token: bool  # only multi-token forms may award credit
    include_target: bool  # the item's ``target`` is itself a scored (optional) unit
    conjunctive_units: bool  # a layer passes only when EVERY required unit hits there
    # opt-in keys of a bank's contract block (multihop_mt_v2 bank v2, 2026-10-30; default off, so
    # every other bank scores byte-identically): ``markdown_fold`` matches each sample after
    # ``digest.fold_quote`` (``**Venerable Bede**`` == ``Venerable Bede``); ``fuzzy_names`` also
    # credits a misspelt Latin-script name (``fuzzy_form_in``: Khatchaturian for Khachaturian)
    markdown_fold: bool = False
    fuzzy_names: bool = False


OPT_IN_KEYS = ("markdown_fold", "fuzzy_names")


def contract_json(contract: BankContract) -> dict[str, bool]:
    """The contract as a result's ``config.contract``: the opt-in keys only when set, so a bank
    that does not opt in stamps exactly the dict it stamped before they existed."""
    d = dataclasses.asdict(contract)
    return {k: v for k, v in d.items() if k not in OPT_IN_KEYS or v}


def contract_for(header: Mapping[str, Any], family: str) -> BankContract:
    """The header's ``contract`` block, else the source's legacy name-suffix rules."""
    block = header.get("contract")
    if isinstance(block, Mapping):
        return BankContract(
            multi_token=bool(block.get("multi_token", family.endswith("-mt"))),
            include_target=bool(block.get("include_target", True)),
            conjunctive_units=bool(block.get("conjunctive_units", False)),
            markdown_fold=bool(block.get("markdown_fold", False)),
            fuzzy_names=bool(block.get("fuzzy_names", False)),
        )
    return BankContract(
        multi_token=family.endswith("-mt"),
        include_target=family != "multilingual-mt",
        conjunctive_units=False,
    )


@dataclass(frozen=True)
class ScoredUnit:
    role: str
    required: bool
    forms: dict[str, list[str]]  # language -> the strings that may award credit
    numeric_match: NumericMatch = "context"
    case_sensitive: tuple[str, ...] = ()  # forms matched with their case kept (plan 0040 B1)
    # ``fuzzy_names`` banks: the other options' names a fuzzy hit must not also be near
    avoid: tuple[str, ...] = ()

    def all_forms(self) -> list[str]:
        out: list[str] = []
        for fs in self.forms.values():
            for f in fs:
                if f not in out:
                    out.append(f)
        return out

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "role": self.role,
            "required": self.required,
            "forms": dict(self.forms),
        }
        if self.numeric_match != "context":
            out["numeric_match"] = self.numeric_match
        if self.case_sensitive:
            out["case_sensitive"] = list(self.case_sensitive)
        return out


def _numeric_match_of(raw: Mapping[str, Any]) -> NumericMatch:
    mode = str(raw.get("numeric_match", "context"))
    if mode not in ("context", "standalone"):
        raise ValueError(f"unit {raw.get('role')!r}: unknown numeric_match {mode!r}")
    return "standalone" if mode == "standalone" else "context"


def _unit_forms(raw: Mapping[str, Any]) -> dict[str, list[str]]:
    forms = raw.get("forms")
    if isinstance(forms, Mapping) and forms:
        return {str(k): [str(x) for x in v] for k, v in forms.items()}
    return {"": [str(m) for m in raw.get("match", [])]}


def _counts(item: Mapping[str, Any], role: str, lang: str, n: int) -> list[int]:
    """``probe_token_lens.units[role][lang]`` — the bank's Qwen3.6-27B token count per form,
    positionally aligned with ``forms[lang]``. A missing stamp is a bank error, never a guess."""
    try:
        counts = [int(x) for x in item["probe_token_lens"]["units"][role][lang]]
    except (KeyError, TypeError) as e:
        raise ValueError(
            f"item {item.get('name')!r}: no probe_token_lens count for unit {role!r} {lang!r}"
        ) from e
    if len(counts) != n:
        raise ValueError(
            f"item {item.get('name')!r}: probe_token_lens.units[{role!r}][{lang!r}] has "
            f"{len(counts)} counts for {n} forms"
        )
    return counts


def scored_units(item: Mapping[str, Any], contract: BankContract) -> list[ScoredUnit]:
    """Units of one item under ``contract`` — the source's ``scored_units`` with the token
    counts read from the bank's ``probe_token_lens`` stamp instead of a live tokenizer. No alias
    pruning: forms are an authored OR-list (the Russian nominative beside its genitive)."""
    units: list[ScoredUnit] = []
    for raw in item.get("units") or []:
        role = str(raw.get("role", "unit"))
        forms = _unit_forms(raw)
        # audit fix F6: a v2 multilingual item's (``mc_roles``) frozen language unit is scored on
        # its naming-context forms; a v1 unit (no ``mc_roles``) is scored as written
        naming = (
            role == "language"
            and bool(item.get("mc_roles"))
            and is_frozen_language_unit(str(item.get("lang") or ""), forms)
        )
        if naming:
            forms = naming_forms(str(item["lang"]), [k for k in forms if k != item["lang"]])
        if contract.multi_token and bool(raw.get("multi_token", True)):
            kept: dict[str, list[str]] = {}
            for lang, fs in forms.items():
                counts = _counts(item, role, lang, len(fs))
                fs2 = [f for f, n in zip(fs, counts, strict=True) if n > 1]
                if fs2:
                    kept[lang] = fs2
            forms = kept
        required = bool(raw.get("required", True))
        if required and not forms:
            raise ValueError(
                f"item {item.get('name')!r}: required unit {role!r} has no creditable "
                "(multi-token) form"
            )
        if forms:
            cs = () if naming else tuple(str(f) for f in raw.get("case_sensitive") or ())
            avoid: tuple[str, ...] = ()
            if contract.fuzzy_names:
                block = (item.get("mc") or {}).get(role) or {}
                avoid = tuple(str(d) for d in block.get("distractors") or ())
            units.append(ScoredUnit(role, required, forms, _numeric_match_of(raw), cs, avoid))
    roles = {u.role for u in units}
    target = item.get("target")
    if contract.include_target and target and "target" not in roles:
        alts = [str(a) for a in item.get("target_alts", [])]
        tforms = [str(target), *alts]
        if contract.multi_token:
            ptl = item.get("probe_token_lens") or {}
            try:
                counts = [int(ptl["target"]), *(int(x) for x in ptl["target_alts"])]
            except (KeyError, TypeError) as e:
                raise ValueError(
                    f"item {item.get('name')!r}: include_target needs probe_token_lens.target "
                    "and .target_alts"
                ) from e
            if len(counts) != len(tforms):
                raise ValueError(
                    f"item {item.get('name')!r}: probe_token_lens.target_alts has "
                    f"{len(counts) - 1} counts for {len(alts)} target_alts"
                )
            tforms = [f for f, n in zip(tforms, counts, strict=True) if n > 1]
        covered = {f.lower() for u in units for f in u.all_forms()}
        tforms = [f for f in tforms if f.lower() not in covered]
        if tforms:
            units.append(ScoredUnit("target", False, {"en": tforms}))
    return units


# ---------------------------------------------------------------------------------------------
# olens_suite/bank/conjunctive.py — per-layer unit hits and the item verdict
# ---------------------------------------------------------------------------------------------
def layer_unit_hits(
    samples: list[str], units: list[ScoredUnit], contract: BankContract | None = None
) -> dict[str, list[str]]:
    """role -> the languages in which the unit hit any single sample at this layer. A contract
    with ``markdown_fold`` matches each sample after ``digest.fold_quote``; with ``fuzzy_names``
    a unit also hits in a language whose forms ``fuzzy_form_in`` finds (never near an
    ``avoid`` name). Without either key the result is the source scorer's, unchanged."""
    if contract is not None and contract.markdown_fold:
        from wsbench.digest import fold_quote

        samples = [fold_quote(s) for s in samples]
    out = {
        u.role: hit_forms(
            samples, u.forms, numeric_match=u.numeric_match, case_sensitive=u.case_sensitive
        )
        for u in units
    }
    if contract is not None and contract.fuzzy_names:
        for u in units:
            for lang, fs in u.forms.items():
                if lang not in out[u.role] and any(
                    fuzzy_form_in(s, fs, avoid=u.avoid) for s in samples
                ):
                    out[u.role].append(lang)
            out[u.role] = [lang for lang in u.forms if lang in out[u.role]]
    return out


def layer_passes(hits: Mapping[str, list[str]], units: list[ScoredUnit]) -> bool:
    return all(bool(hits.get(u.role)) for u in units if u.required)


def item_result(
    by_layer: Mapping[int, Mapping[str, list[str]]], units: list[ScoredUnit]
) -> dict[str, Any]:
    """Fold per-layer unit hits into the item row: pass = some layer where every required unit
    hits; ``unit_langs`` lists the languages in the unit's authored order (L2 -> en -> zh)."""
    passing = sorted(layer for layer, hits in by_layer.items() if layer_passes(hits, units))
    unit_hit = {u.role: any(bool(h.get(u.role)) for h in by_layer.values()) for u in units}
    unit_langs = {
        u.role: [
            lang for lang in u.forms if any(lang in h.get(u.role, []) for h in by_layer.values())
        ]
        for u in units
    }
    return {
        "pass": bool(passing),
        "earliest_layer": passing[0] if passing else None,
        "n_passing_layers": len(passing),
        "passing_layers": passing,
        "unit_hit": unit_hit,
        "unit_langs": unit_langs,
        "first_lang": {role: (langs[0] if langs else None) for role, langs in unit_langs.items()},
        "any_hit": any(unit_hit.values()),
    }


# ---------------------------------------------------------------------------------------------
# misspelt names (bank contract ``fuzzy_names``; Camila 2026-10-30: "allowing e.g.
# 'khatchaturian'") — a family-scoped matcher, not a quote verifier
# ---------------------------------------------------------------------------------------------
_FUZZY_WORD = re.compile(r"[^\W\d_]+(?:['\-][^\W\d_]+)*")
_LATIN = re.compile(r"[a-z]")


def _words(s: str) -> list[str]:
    from wsbench.digest import fold_quote

    return _FUZZY_WORD.findall(fold_quote(s).replace("\u2019", "'"))


def _budget(word: str) -> int:
    """Edits allowed for one form word: exact under 8 letters, 1 for 8-11, 2 for 12 or more.

    The floor was 6 until the PR #167 review: at 6-7 letters one edit turns surnames into
    ordinary English words (tailor ~ Taylor, virgin ~ Virgil, bridge ~ Bridget, canton ~ Cantor,
    hobbies ~ Hobbes), so the name gate credited readouts that never named the entity."""
    n = len(word)
    return 0 if n < 8 else 1 if n < 12 else 2


def damerau_levenshtein(a: str, b: str) -> int:
    """Optimal-string-alignment distance (insert, delete, substitute, adjacent transpose)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def _fuzzy_form_words(form: str) -> list[str] | None:
    """A form's folded words when it may match fuzzily (Latin script, no digits, no CJK, not a
    ``re:`` pattern)."""
    if form.startswith(RE_PREFIX) or _CJK_HANGUL.search(form) or re.search(r"\d", form):
        return None
    ws = _words(form)
    if not ws or not all(_LATIN.search(w) for w in ws):
        return None
    if any(re.search(r"[^a-z'\-]", w) for w in ws):
        return None  # a non-Latin letter survived the fold (Cyrillic, Greek…): never fuzzy
    return ws


def _word_near(t: str, f: str) -> bool:
    """``t`` equals ``f``, or is within ``f``'s budget AND keeps its first letter (a misspelling
    keeps the initial — Khatchaturian; a first-letter edit is another word: Herbert ~ Gerbert,
    garrison ~ Harrison)."""
    if t == f:
        return True
    return t[:1] == f[:1] and damerau_levenshtein(t, f) <= _budget(f)


def _near(window: list[str], form_words: list[str]) -> bool:
    return all(_word_near(t, f) for t, f in zip(window, form_words, strict=True))


def fuzzy_form_in(text: str, forms: list[str] | tuple[str, ...], *, avoid: Any = ()) -> bool:
    """A Latin-script ``form`` (one or more words) matches a same-length window of consecutive
    words of ``text`` (both ``digest.fold_quote``-folded) when every word is within its edit
    budget: exact under 8 letters, Damerau-Levenshtein 1 for 8-11, 2 for 12 or more, and an
    edited word keeps the form word's first letter. Numeric and
    CJK forms never match fuzzily. A window that is also within budget of an ``avoid`` name
    (another option) never credits (decision Q10: a name that also fits another option fails)."""
    words = _words(text)
    if not words:
        return False
    avoid_words = [w for w in (_fuzzy_form_words(str(a)) for a in avoid) if w]
    for form in forms:
        fw = _fuzzy_form_words(str(form))
        if fw is None or len(fw) > len(words):
            continue
        for i in range(len(words) - len(fw) + 1):
            window = words[i : i + len(fw)]
            if not _near(window, fw):
                continue
            clash = False
            for aw in avoid_words:
                # the same window, or any sub-window of the avoid name's length inside it
                for j in range(len(window) - len(aw) + 1):
                    if _near(window[j : j + len(aw)], aw):
                        clash = True
                        break
                if clash:
                    break
            if not clash:
                return True
    return False


# ---------------------------------------------------------------------------------------------
# flat runs (fresh-eye review of the audit fixes, 2026-10-31): the F4 any-line rescues
# (``mcrx.singling_lines``, ``family.singles_out``) credit a line that SINGLES OUT the gold; a
# piece that is a flat run of candidates singles out none of them (decision Q4, Camila: "flat
# lists single out nothing"), whatever its other items are
# ---------------------------------------------------------------------------------------------
FLAT_ITEMS_MIN = 4  # list items for a run
_LIST_SEP = re.compile(
    r"\s*(?:[,;/|·•、，；]|\s(?:or|and|ou|et|oder|und|o|y|или|и)\s)\s*",  # noqa: RUF001
    re.IGNORECASE,
)
_NUMBER_WORDS = (
    "zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    "fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    "eighty|ninety|hundred|thousand"
)
_NUMBER = re.compile(
    rf"(?<![\w.,])\d+(?:[.,]\d+)?(?![\w])|(?<![^\W_])(?:{_NUMBER_WORDS})(?![^\W_])"
)


_WORD_VALUE = {w: i for i, w in enumerate(_NUMBER_WORDS.split("|")[:21])} | {
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100, "thousand": 1000,
}  # fmt: skip


def _value(tok: str) -> float | None:
    t = tok.strip()
    if t in _WORD_VALUE:
        return float(_WORD_VALUE[t])
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def is_number_form(form: str) -> bool:
    """A unit form that is a number (digits, or an English number word)."""
    return _NUMBER.fullmatch(fold(form).strip()) is not None


def flat_run(text: str, gold: Sequence[str] = (), *, number: bool = False) -> bool:
    """``text`` (one bullet or one token list) is a flat run of candidates: at least
    :data:`FLAT_ITEMS_MIN` list items (split at commas, slashes, semicolons, "or" / "and") that
    are not the gold's own forms (``gold``: "Paris / Parigi / París" is one entity), none longer
    than three words and at least three quarters of them one or two words; or, for a ``number``
    gold, it holds a number of ANOTHER value ("five six seven", "six or maybe seven"; the gold
    written twice, "three (3)", and the word "one" do not count): a number among competing
    numbers is not singled out."""
    golds = {fold(g).strip() for g in gold if g.strip()}
    items = [x for x in _LIST_SEP.split(text) if x and x.strip(" .:*-")]
    items = [x for x in items if fold(x).strip(" .:*-\"'()") not in golds]
    if len(items) >= FLAT_ITEMS_MIN:
        words = [len(x.split()) for x in items]
        if max(words) <= 3 and 4 * sum(1 for w in words if w <= 2) >= 3 * len(words):
            return True
    if number:
        mine = {v for g in golds if (v := _value(g)) is not None}
        vals = {_value(m.group(0)) for m in _NUMBER.finditer(fold(text)) if m.group(0) != "one"}
        return bool({v for v in vals if v is not None} - mine)
    return False

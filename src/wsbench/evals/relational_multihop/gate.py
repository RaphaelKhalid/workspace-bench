"""relational_multihop order gate (plan 0043 C3(d)): does ONE statement state the composed
relation ``hop1's hop2`` exactly, in that order, and not as part of a longer chain?

Everything runs on ``digest.fold_quote`` text. A statement is scanned into relation *mentions*
(leftmost-longest over every alias of :data:`prompts.REL_LEXICON` plus
:data:`prompts.OTHER_RELATION_WORDS`); two consecutive mentions form a *link* when the text
between them is one possessive (``X's Y`` / ``X的Y``, an optional short parenthesised gloss of X
allowed) or ``Y of (det|Name's){0,2} X``. A chain ``(outer, inner)`` is *embedded* when the
mention before it links into it, the mention after it links out of it, or a possessive with
nothing after it follows it (``landlord's sibling's ___``), or a possessive and a blank follow it
(``cousin's boss's ___. Here's why``). Rank is never order: a quote holding the token-list
joiner ``" | "`` never passes.

Blanks (audit F12, 2026-10-31): ``fold_quote`` strips ``_`` as markdown, so the fill-in frame
``landlord's _______ cousin`` folded to ``landlord's cousin`` and counted as stating the chain.
:func:`fold` first replaces an underscore blank and a bracketed placeholder with
:data:`BLANK` (relgate-v3: a run of 2+ underscores is a blank even when it touches a word,
``barber's ____child``; only a word span wrapped in the same 1-3 underscores, ``__cousin__``, is
emphasis), a token that is no relation and breaks every link; every text and quote the gate
reads goes through it."""

import itertools
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from wsbench.digest import Line, fold_quote

from .prompts import OTHER_RELATION_WORDS, REL_LEXICON

MAX_QUOTE_WORDS = 15
MAX_QUOTE_CJK = 40
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def _alias_table() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for rel, aliases in REL_LEXICON.items():
        for a in aliases:
            f = fold_quote(a)
            if out.get(f, rel) != rel:
                raise ValueError(f"alias {a!r} maps to {out[f]!r} and {rel!r}")
            out[f] = rel
    for w in OTHER_RELATION_WORDS:
        out.setdefault(fold_quote(w), None)
    return out


ALIASES = _alias_table()


def _pattern(alias: str) -> str:
    if _CJK.search(alias):
        return re.escape(alias)
    return r"(?<![\w-])" + re.escape(alias) + r"(?![\w-])"


_MENTION = re.compile("|".join(_pattern(a) for a in sorted(ALIASES, key=lambda a: -len(a))))
_POSS = r"(?:'s|的)"
# X's / X的; a bare apostrophe only right after an s-final mention ("boss' sister")
_LINK_POSS = re.compile(
    r"(?P<bare>')?"
    rf"\s*(?P<pre>{_POSS})?\s*(?:\((?P<gloss>[^()]{{0,25}})\))?\s*(?P<post>{_POSS})?\s*"
)
_DET = r"(?:the|a|an|my|your|his|her|their|our|its|one's|someone's|[^\W\d_][\w-]*'s)"
_LINK_OF = re.compile(rf"\s+of\s+(?:{_DET}\s+){{0,2}}")
BLANK = "~blank~"
# markdown emphasis: a word span wrapped in the SAME 1-3 underscore run on both sides
# ("__cousin__", "___child___", "_the landlord_"); kept as its words, never a blank
_EMPHASIS = re.compile(r"(?<![\w_])(_{1,3})([^\W_](?:[^_\n]{0,60}?[^\W_])?)\1(?![\w_])")
# a blank (relgate-v3, round 3): a run of 2+ underscores, touching a word or not
# ("barber's ____child", "cousin's________ coach"), or a lone "_" touching no letter or digit;
# and a bracketed placeholder ("(blank)", "[___]", "(?)", "[relationship]")
_BLANK_RUN = re.compile(r"_{2,}|(?<!\w)_(?!\w)")
_BLANK_BRACKET = re.compile(
    r"[(\[]\s*(?:_+|blank|relation(?:ship)?|\?+|\.{3}|…|x)\s*[)\]]", re.IGNORECASE
)
_POSS_END = re.compile(rf"\s*{_POSS}(?:[\s_.…?!,;:]|{re.escape(BLANK)})*$")
_POSS_BLANK = re.compile(rf"\s*{_POSS}\s*{re.escape(BLANK)}")


def fold(text: str) -> str:
    """``digest.fold_quote`` after the blanks are replaced with :data:`BLANK` (module doc)."""
    text = _BLANK_BRACKET.sub(f" {BLANK} ", text)
    out: list[str] = []
    at = 0
    for m in _EMPHASIS.finditer(text):
        out += [_BLANK_RUN.sub(f" {BLANK} ", text[at : m.start()]), m.group(2)]
        at = m.end()
    out.append(_BLANK_RUN.sub(f" {BLANK} ", text[at:]))
    return fold_quote("".join(out))


@dataclass(frozen=True)
class Mention:
    start: int
    end: int
    rel: str | None  # None: a relation word outside the option vocabulary


@dataclass(frozen=True)
class Chain:
    outer: str | None
    inner: str | None
    start: int
    end: int
    embedded: bool


def mentions(text: str) -> list[Mention]:
    """The relation mentions of folded ``text``; a mention inside a short parenthesised gloss
    right after a mention of the SAME relation ("房东 (landlord)") is dropped (it glosses it)."""
    raw = [Mention(m.start(), m.end(), ALIASES[m.group(0)]) for m in _MENTION.finditer(text)]
    out: list[Mention] = []
    for m in raw:
        if out and out[-1].rel is not None and m.rel == out[-1].rel:
            gap = text[out[-1].end : m.start]
            close = text.find(")", m.end)
            if re.fullmatch(r"\s*\([^()]*", gap) and 0 <= close - m.end <= 25:
                continue
        out.append(m)
    return out


def _poss_link(between: str, s_final: bool) -> bool:
    m = _LINK_POSS.fullmatch(between)
    if m is None or (m.group("bare") and not s_final):
        return False
    gloss = m.group("gloss") or ""
    n = (
        bool(m.group("bare"))
        + bool(m.group("pre"))
        + bool(m.group("post"))
        + bool(re.search(rf"{_POSS}\s*$", gloss))
    )
    return n == 1


def _link(text: str, a: Mention, b: Mention) -> str | None:
    """``"poss"`` (a's b), ``"of"`` (a of b), or None."""
    between = text[a.end : b.start]
    if _poss_link(between, text[a.end - 1 : a.end] == "s"):
        return "poss"
    if _LINK_OF.fullmatch(between):
        return "of"
    return None


def chains(text: str) -> list[Chain]:
    """Every linked mention pair of folded ``text`` as an (outer, inner) chain."""
    ms = mentions(text)
    links = [_link(text, a, b) for a, b in itertools.pairwise(ms)]
    out: list[Chain] = []
    for i, kind in enumerate(links):
        if kind is None:
            continue
        a, b = ms[i], ms[i + 1]
        outer, inner = (a.rel, b.rel) if kind == "poss" else (b.rel, a.rel)
        embedded = (
            (i > 0 and links[i - 1] is not None)
            or (i + 1 < len(links) and links[i + 1] is not None)
            or bool(_POSS_END.match(text[b.end :]))
            or bool(_POSS_BLANK.match(text[b.end :]))
        )
        out.append(Chain(outer, inner, a.start, b.end, embedded))
    return out


def states(text: str, outer: str, inner: str, within: tuple[int, int] | None = None) -> bool:
    """Folded ``text`` states the non-embedded chain ``outer's inner`` (inside ``within``)."""
    for c in chains(text):
        if c.embedded or (c.outer, c.inner) != (outer, inner):
            continue
        if within is None or (within[0] <= c.start and c.end <= within[1]):
            return True
    return False


def too_long(quote: str) -> bool:
    fq = fold_quote(quote)
    return len(fq.split()) > MAX_QUOTE_WORDS or len(_CJK.findall(fq)) > MAX_QUOTE_CJK


def _occurrences(hay: str, needle: str) -> Iterable[int]:
    i = hay.find(needle)
    while i >= 0:
        yield i
        i = hay.find(needle, i + 1)


def order_gate(
    quote: str,
    statements: Sequence[Line],
    gold: tuple[str, str],
    rivals: Sequence[tuple[str, str]],
    prominence: Sequence[Line] | None = None,
) -> str:
    """The gold pick's mechanical gate over the unit's statements (bullets):

    - ``"order"``: no statement holding the quote states ``gold`` (non-embedded) inside it;
    - ``"two_chains"``: every such statement also states a rival chain (the other composed
      options: reversed, near-miss, other) — one statement holding two listed chains singles out
      none;
    - ``"rival_prominent"``: some rival chain is stated in at least as many statements as the
      gold — the prompt's "most bullets/lines, a tie is cannot tell" rule, enforced;
    - ``"pass"`` otherwise.

    ``prominence`` (default ``statements``) = the statements that rule counts over. Summary mode
    passes every loaded cell's statements: its digest keeps ONE sample line per entry (support
    shown as a per-claim count), so counting the digest's lines would tie a gold seen in many
    samples with a rival seen once."""
    fq = fold(quote)
    if not fq or "|" in fq:
        return "order"
    found_two = found = False
    for ln in statements:
        if ln.pieces is not None:
            continue  # a token list carries no order (only a " | " quote spans its tokens)
        text = fold(ln.text)
        hit = any(states(text, *gold, within=(s, s + len(fq))) for s in _occurrences(text, fq))
        if not hit:
            continue
        if any(states(text, *r) for r in rivals):
            found_two = True
            continue
        found = True
        break
    if not found:
        return "two_chains" if found_two else "order"
    pool = statements if prominence is None else prominence
    n_gold = count_units(pool, gold)
    if any(count_units(pool, r) >= n_gold for r in rivals):
        return "rival_prominent"
    return "pass"


def count_units(statements: Sequence[Line], chain: tuple[str, str]) -> int:
    """Statements (bullets) stating ``chain`` non-embedded: the raw-unit count behind
    ``extras.reversed_also_stated``."""
    return sum(1 for ln in statements if ln.pieces is None and states(fold(ln.text), *chain))

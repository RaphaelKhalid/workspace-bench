"""Numerals in any language the lenses write (plan 0032 §2.7.5a): ASCII / fullwidth digits, CJK
numerals (Chinese and Japanese kanji), number words 0-100 with their compounds in en, de, es, fr,
it, pt, nl and ru, and ordinals (``eighteenth``, ``第十八``) as their cardinal.

``numbers_in`` is what ``digest.number_flood`` counts and what the chain / arithmetic judges
verify against; ``names_value`` is the whole-number check; ``word_value`` reads one key. This
module holds no flood logic."""

import functools
import re
import unicodedata

# ---------------------------------------------------------------- folding


def fold(s: str) -> str:
    """Casefolded and accent-stripped (``dreißig`` -> ``dreissig``, ``veintiséis`` ->
    ``veintiseis``, ``tweeëntwintig`` -> ``tweeentwintig``)."""
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


_FULLWIDTH = str.maketrans({chr(0xFF10 + d): str(d) for d in range(10)} | {"\uff0c": ","})


# ---------------------------------------------------------------- CJK


CJK_DIGIT = {
    "\u3007": 0,  # ideographic zero
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CJK_UNIT = {"十": 10, "百": 100, "千": 1000}
CJK_CHARS = "".join(CJK_DIGIT) + "".join(CJK_UNIT) + "万"


def cjk_int(t: str) -> int | None:
    """A CJK integer below 10^8 (``三十七``, ``两万零五``, ``十四``), else ``None``."""
    if not t:
        return None
    if "万" in t:
        hi, lo = t.split("万", 1)
        h = cjk_int(hi) if hi else None
        if h is None or "万" in lo:
            return None
        rest = cjk_int(lo) if lo else 0
        return None if rest is None else h * 10000 + rest
    total, digit, last_unit = 0, None, 10**9
    for ch in t:
        if ch in CJK_DIGIT:
            if digit is not None and digit != 0:
                return None  # two digits in a row ("三四") is not one number
            digit = CJK_DIGIT[ch]
        elif ch in CJK_UNIT:
            if CJK_UNIT[ch] >= last_unit:
                return None  # units must fall ("一十一十", "百百" are not numbers)
            last_unit = CJK_UNIT[ch]
            total += (1 if digit is None else digit) * CJK_UNIT[ch]
            digit = None
        else:
            return None
    if digit and len(t) >= 2 and last_unit >= 100 and t[-2] in CJK_UNIT:
        return total + digit * last_unit // 10  # colloquial 三百五 = 350, 两千三 = 2300
    return total + (digit or 0)


# ---------------------------------------------------------------- number words


def _w(s: str) -> list[str]:
    return s.split()


def _table() -> dict[str, int]:
    """Folded phrase (words joined by one space) -> value, 0-100 in eight languages."""
    out: dict[str, int] = {}

    def add(value: int, *forms: str) -> None:
        for f in forms:
            key = " ".join(fold(f).replace("-", " ").split())
            out.setdefault(key, value)

    # English, with ordinals
    en_u = _w("zero one two three four five six seven eight nine")
    en_t = "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
    en_tens = _w("twenty thirty forty fifty sixty seventy eighty ninety")
    en_ord_u = _w("zeroth first second third fourth fifth sixth seventh eighth ninth")
    for i, w in enumerate(en_u):
        add(i, w)
        add(i, en_ord_u[i])
    for i, w in enumerate(_w(en_t)):
        add(10 + i, w)
        add(10 + i, "twelfth" if w == "twelve" else w + "th")
    for i, t in enumerate(en_tens):
        v = 20 + 10 * i
        add(v, t, t[:-1] + "ieth")
        for u in range(1, 10):
            add(v + u, f"{t} {en_u[u]}", f"{t} {en_ord_u[u]}")
    add(100, "hundred", "one hundred", "a hundred", "hundredth", "one hundredth")

    # German
    de_u = _w("null eins zwei drei vier fünf sechs sieben acht neun")
    de_t = "zehn elf zwölf dreizehn vierzehn fünfzehn sechzehn siebzehn achtzehn neunzehn"
    de_tens = _w("zwanzig dreißig vierzig fünfzig sechzig siebzig achtzig neunzig")
    for i, w in enumerate(de_u):
        add(i, w)
    add(1, "ein", "eine")
    for i, w in enumerate(_w(de_t)):
        add(10 + i, w)
    for i, t in enumerate(de_tens):
        v = 20 + 10 * i
        add(v, t)
        for u in range(1, 10):
            add(v + u, ("ein" if u == 1 else de_u[u]) + "und" + t)
    add(100, "hundert", "einhundert")

    # Spanish
    es_u = _w("cero uno dos tres cuatro cinco seis siete ocho nueve")
    es_t = "diez once doce trece catorce quince dieciséis diecisiete dieciocho diecinueve"
    es_20s = (
        "veinte veintiuno veintidós veintitrés veinticuatro veinticinco veintiséis veintisiete "
        "veintiocho veintinueve"
    )
    es_tens = _w("treinta cuarenta cincuenta sesenta setenta ochenta noventa")
    for i, w in enumerate(es_u):
        add(i, w)
    add(1, "una", "un")
    for i, w in enumerate(_w(es_t)):
        add(10 + i, w)
    for i, w in enumerate(es_20s.split()):
        add(20 + i, w)
    for i, t in enumerate(es_tens):
        v = 30 + 10 * i
        add(v, t)
        for u in range(1, 10):
            add(v + u, f"{t} y {es_u[u]}")
    add(100, "cien", "ciento")

    # French
    fr_u = _w("zéro un deux trois quatre cinq six sept huit neuf")
    fr_t = _w("dix onze douze treize quatorze quinze seize dix-sept dix-huit dix-neuf")
    for i, w in enumerate(fr_u):
        add(i, w)
    add(1, "une")
    for i, w in enumerate(fr_t):
        add(10 + i, w)
    for i, t in enumerate(["vingt", "trente", "quarante", "cinquante", "soixante"]):
        v = 20 + 10 * i
        add(v, t)
        add(v + 1, f"{t} et un", f"{t}-et-un", f"{t} un")
        for u in range(2, 10):
            add(v + u, f"{t}-{fr_u[u]}")
    add(70, "soixante-dix", "septante")
    add(71, "soixante et onze", "soixante-et-onze", "soixante-onze")
    for u in range(2, 10):
        add(70 + u, f"soixante-{fr_t[u]}")
    add(80, "quatre-vingts", "quatre-vingt", "huitante")
    for u in range(1, 10):
        add(80 + u, f"quatre-vingt-{fr_u[u]}")
    add(90, "quatre-vingt-dix", "nonante")
    for u in range(1, 10):
        add(90 + u, f"quatre-vingt-{fr_t[u]}")
    add(100, "cent")

    # Italian (vowel elision before uno / otto; tre -> tré)
    it_u = _w("zero uno due tre quattro cinque sei sette otto nove")
    it_t = "dieci undici dodici tredici quattordici quindici sedici diciassette diciotto diciannove"
    it_tens = _w("venti trenta quaranta cinquanta sessanta settanta ottanta novanta")
    for i, w in enumerate(it_u):
        add(i, w)
    for i, w in enumerate(_w(it_t)):
        add(10 + i, w)
    for i, t in enumerate(it_tens):
        v = 20 + 10 * i
        add(v, t)
        for u in range(1, 10):
            w = it_u[u]
            add(v + u, (t[:-1] + w) if w[0] in "aeiou" else t + ("tré" if u == 3 else w))
    add(100, "cento")

    # Portuguese
    pt_u = _w("zero um dois três quatro cinco seis sete oito nove")
    pt_t = _w("dez onze doze treze catorze quinze dezesseis dezessete dezoito dezenove")
    pt_tens = _w("vinte trinta quarenta cinquenta sessenta setenta oitenta noventa")
    for i, w in enumerate(pt_u):
        add(i, w)
    add(1, "uma")
    add(2, "duas")
    for i, w in enumerate(pt_t):
        add(10 + i, w)
    add(14, "quatorze")
    add(16, "dezasseis")
    add(17, "dezassete")
    add(19, "dezanove")
    for i, t in enumerate(pt_tens):
        v = 20 + 10 * i
        add(v, t)
        for u in range(1, 10):
            add(v + u, f"{t} e {pt_u[u]}")
    add(100, "cem", "cento")

    # Dutch (unit + en / ën + tens, one word)
    nl_u = _w("nul een twee drie vier vijf zes zeven acht negen")
    nl_t = "tien elf twaalf dertien veertien vijftien zestien zeventien achttien negentien"
    nl_tens = _w("twintig dertig veertig vijftig zestig zeventig tachtig negentig")
    for i, w in enumerate(nl_u):
        add(i, w)
    add(1, "één")
    for i, w in enumerate(_w(nl_t)):
        add(10 + i, w)
    for i, t in enumerate(nl_tens):
        v = 20 + 10 * i
        add(v, t)
        for u in range(1, 10):
            add(v + u, nl_u[u] + "en" + t)
    add(100, "honderd", "eenhonderd")

    # Russian
    ru_u = _w("ноль один два три четыре пять шесть семь восемь девять")
    ru_t = (
        "десять одиннадцать двенадцать тринадцать четырнадцать пятнадцать шестнадцать "
        "семнадцать восемнадцать девятнадцать"
    )
    ru_tens = "двадцать тридцать сорок пятьдесят шестьдесят семьдесят восемьдесят девяносто"
    for i, w in enumerate(ru_u):
        add(i, w)
    add(1, "одна", "одно")
    add(2, "две")
    for i, w in enumerate(_w(ru_t)):
        add(10 + i, w)
    for i, t in enumerate(_w(ru_tens)):
        v = 20 + 10 * i
        add(v, t)
        for u in range(1, 10):
            add(v + u, f"{t} {ru_u[u]}")
        add(v + 1, f"{t} одна")
        add(v + 2, f"{t} две")
    add(100, "сто")
    return out


WORDS: dict[str, int] = _table()
MAX_PHRASE = max(len(k.split()) for k in WORDS)
# number words that are also common words of another language the lenses write in (English
# "due", "um", "cent", "sept."): ``word_value`` reads them as a key, but ``numbers_in`` and
# ``names_value`` never count them inside running text
AMBIGUOUS = frozenset({"due", "um", "cent", "sept", "nul", "un", "une", "ein", "eine", "otto"})

_DIGITS = re.compile(r"(?<![\d.,])(?<!\d\.)(\d{1,3}(?:,\d{3})+|\d+)(?!\d)(?!\.\d)(?!,\d{3})")
_CJK_RUN = re.compile(rf"第?([{CJK_CHARS}]+)")
_WORD = re.compile(r"[^\W\d_]+")


@functools.lru_cache(maxsize=1 << 14)
def _word_hits(text: str) -> tuple[tuple[int, int, int], ...]:
    """``(start, end, value)`` of every number-word phrase in the folded ``text`` (longest
    match first; words of one phrase are separated only by spaces or hyphens)."""
    toks = [(m.start(), m.end(), m.group(0)) for m in _WORD.finditer(text)]
    out: list[tuple[int, int, int]] = []
    i = 0
    while i < len(toks):
        hit = None
        for n in range(min(MAX_PHRASE, len(toks) - i), 0, -1):
            span = toks[i : i + n]
            gaps_ok = all(
                re.fullmatch(r"[\s\-]+", text[span[j][1] : span[j + 1][0]])
                for j in range(len(span) - 1)
            )
            if not gaps_ok:
                continue
            key = " ".join(t[2] for t in span)
            if key in WORDS and not (n == 1 and key in AMBIGUOUS):
                hit = (span[0][0], span[-1][1], WORDS[key], n)
                break
        if hit is None:
            i += 1
            continue
        out.append(hit[:3])
        i += hit[3]
    return tuple(out)


def tokens(text: str) -> list[tuple[int, int, int, str]]:
    """Every numeral in ``text`` in order: ``(start, end, value, kind)`` with kind ``digit``,
    ``cjk`` or ``word``; positions index the folded text (``fold`` keeps lengths for the digit
    and CJK forms the lenses emit)."""
    t = fold(text).translate(_FULLWIDTH)
    out: list[tuple[int, int, int, str]] = []
    for m in _DIGITS.finditer(t):
        out.append((m.start(), m.end(), int(m.group(1).replace(",", "")), "digit"))
    for m in _CJK_RUN.finditer(t):
        v = cjk_int(m.group(1))
        if v is not None:
            out.append((m.start(), m.end(), v, "cjk"))
    for s, e, v in _word_hits(t):
        out.append((s, e, v, "word"))
    return sorted(out)


def numbers_in(text: str) -> set[int]:
    """Every integer ``text`` names: digits as whole numbers (``5`` is not in ``15``, ``2019`` or
    ``10.5``; ``1,000`` is 1000), CJK numerals, number words 0-100 in eight languages and their
    ordinals."""
    return {v for _s, _e, v, _k in tokens(text)}


def names_value(n: int, text: str) -> bool:
    """``n`` is named in ``text`` as a whole number (digits), a CJK numeral or a number word
    (word-bounded)."""
    return n in numbers_in(text)


def word_value(token: str) -> int | None:
    """The value of ONE numeral key: digits, a CJK numeral (``第`` ordinal prefix allowed) or a
    number word / phrase in any of the eight languages (``eight``, ``sieben``, ``twenty-six``,
    ``eighteenth``), else ``None``."""
    t = " ".join(fold(token).translate(_FULLWIDTH).replace("-", " ").split())
    if not t:
        return None
    if re.fullmatch(r"\d+", t):
        return int(t)
    c = t[1:] if t.startswith("第") else t
    if c and all(ch in CJK_CHARS for ch in c):
        return cjk_int(c)
    return WORDS.get(t)

"""wrong_bridge (plan 0050): a blind 6-way MC judge over the model's wrong bridge B' (gold), the
true bridge B (contrast, scored as a fail and reported as ``true_bridge_rate``) and four
same-category distractors, plus "cannot tell" last. Options and name forms are frozen in bank v2
(``scripts/wrong_bridge_mc_options.py``); nothing is built at judge time.

Summary mode (the default): every loaded cell of an item (every position x layer under
``reads=full``; the final token under ``reads=lite``) -> one digest -> ONE MC call. Native mode
(``opts=aggregate=native``, the ATI gate): one MC call per (item, layer) over that layer's
positions; an item passes if any layer is a credited gold pick.

A gold pick is credited only if its quote verifies against the readout (``digest.quote_ok``),
carries a listed name form of the gold (:func:`name_in`, every option matched the same way) and
is not an echo of the prompt; in summary mode it must also clearly outweigh the strongest rival
line the judge names (``wsbench.rival``: a pick a rival entity nearly matches in samples is
``contested``, a fail),
the true bridge's own line (:func:`contrast_line`: a full name in the role) and every prominent
line a second call, the rival audit (:func:`audit_lines`), marks as naming a different entity
in question: it must lead the strongest by ``rival.FAR_MORE`` and outweigh their sum."""

import functools
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

from wsbench import digest, mc, reads, rival
from wsbench.banks import load_bank
from wsbench.cache import Cache
from wsbench.family import pass_rate_result, require_cells, tri_state
from wsbench.llm import Spend
from wsbench.mcjudge import (
    Call,
    Preflighter,
    choice_of,
    item_scope,
    layer_pick_columns,
    quote_of,
    run_calls,
    with_readout_count,
)
from wsbench.readouts import Cell
from wsbench.registry import JudgeArgs, bank_path
from wsbench.results import FamilyResult

from . import prompts as wp

NAME = "wrong_bridge"
N_SHOWN = 7  # 6 candidates + cannot tell
CHANCE = 1 / 6
CHANCE_LABEL = (
    "MC, 6 candidates + cannot tell: uniform-guess floor 1/6; lucky-guessing floor in "
    "evals/baselines/lucky_guessing.json"
)
PICKS = (
    "gold",
    "contrast",
    "distractor",
    "cannot_tell",
    "invalid",
    "gold_uncredited",
    "contested",
)


# ------------------------------------------------------------------ the name matcher (round 4)
# Camila r2: the forms were too strict ("King Roger II", Russian "Назван в честь Карла Маркса").
# Bank v3 lists every option's Wikidata names in every language (symmetric over the options); the
# matcher, used for EVERY option and by every check below (form gate, single-out, rival, contrast
# line, audit), adds: inflection tolerance (each word of 4+ letters of a non-CJK form may run on
# into up to WORD_SUFFIX letters of its own script: "Карла Маркса" for "Карл Маркс", Croatian
# "Ivana Gundulića"), word boundaries counted against letters of the form's own scripts only (a
# Latin name glued to CJK text, "Blue Note以", is a whole word), and Hangul forms compared in NFC.
# wbforms-v2 (review of PR #208, round 4b): the inflection tolerance is for inflecting
# languages only (Camila asked for Russian / inflection tolerance, not English): it applies to a
# form spelled with a letter outside ASCII (Cyrillic, Greek, ..., or an accented Latin letter: a
# non-English spelling, Croatian "Ivan Gundulić"); a plain-ASCII form is English-spelled (or
# indistinguishable from it) and matches whole words only, since English does not inflect names:
# "random" is not Ayn Rand, "a wilder story" not Oscar Wilde, "Hannah Arendt" not William Hanna.
# wbforms-v3 (review of PR #208, round 4c nit): ``mc.fold`` strips accents, so an accent-only
# form ("Pärt", "Dalí": its only non-ASCII letters are Latin accents) folded to an English word
# ("part") or took the tail as a non-English spelling ("Dalit", "Dalian"). Such a form now takes
# the tail only when the text keeps its accents ("Dalís", "Ivana Gundulića"); spelled without
# them it matches as an English form, whole words only, and as one bare word only capitalized
# ("Beyonce", "Dali" still count; "part of the sonata" does not). The checks therefore read the
# text unfolded (:func:`norm`), never ``digest.fold_quote`` output.
FORMS_VERSION = wp.FORMS_VERSION  # wbforms-v4: ASCII twins of accent-only forms (_ascii_twins)
WORD_SUFFIX = 2
WORD_SUFFIX_MIN = 4
_SPACED = r"0-9a-z\u00c0-\u024f\u0370-\u03ff\u0400-\u052f\u0530-\u058f\u0590-\u05ff\u0600-\u06ff"
_BEFORE = rf"(?<![{_SPACED}])"
_AFTER = rf"(?![{_SPACED}])"
_TAIL = rf"[{_SPACED[3:]}]{{0,{WORD_SUFFIX}}}"
_HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")


def inflecting(form: str) -> bool:
    """The form (as listed, before folding) is spelled with a letter outside ASCII: a
    non-English spelling, whose words may take an inflectional ending (see FORMS_VERSION)."""
    return any(ch.isalpha() and not ch.isascii() for ch in form)


def accent_only(form: str) -> bool:
    """The form's non-ASCII letters are all Latin accents: :func:`inflecting`, yet
    ``mc.fold`` makes it plain ASCII ("Pärt" -> "part"), so its folded spelling can be an
    English word (see FORMS_VERSION)."""
    return inflecting(form) and mc.fold(form).isascii()


_MD = re.compile(r"\*\*|__|[*_`]")


def norm(text: str) -> str:
    """``digest.fold_quote`` without the fold: NFC, markdown marks stripped, the bullet mark as
    a space, whitespace collapsed; accents and case kept for :func:`name_spans`."""
    t = _MD.sub("", unicodedata.normalize("NFC", text)).replace(digest.BULLET_MARK.strip(), " ")
    return " ".join(t.split())


def _views(text: str) -> tuple[str, str, str]:
    """(``mc.fold(text)``, the same with each letter's accents kept, the same with its case
    kept): equal lengths, so a span in one is the same span in the others."""
    t, k, c_ = [], [], []
    for c in unicodedata.normalize("NFC", text):
        f, a = mc.fold(c), c.casefold()
        t.append(f)
        k.append(a if len(a) == len(f) else f)
        c_.append(c if len(f) == 1 else f)
    return "".join(t), "".join(k), "".join(c_)


def _form_pattern(ff: str, inflect: bool = True) -> str:
    words = ff.split(" ")
    return " ".join(
        re.escape(w) + (_TAIL if inflect and len(w) >= WORD_SUFFIX_MIN and w[-1].isalpha() else "")
        for w in words
    )


_Rule = Callable[[str], bool]


def _plan(f: str, glued: bool) -> tuple[Any, ...] | None:
    """:func:`_compiled`, keyed by the module's current spelling rules (:func:`inflecting`,
    :func:`accent_only`), so a patched rule is a new key, never a stale pattern."""
    return _compiled(f, glued, inflecting, accent_only)


@functools.cache
def _compiled(f: str, glued: bool, infl_rule: _Rule, acc_rule: _Rule) -> tuple[Any, ...] | None:
    """One form's compiled matcher (cached: an option lists up to ~350 forms, which overflowed
    ``re``'s 512-entry cache, so every call recompiled every pattern, ~33 ms per ``name_in``)."""
    if _HANGUL.search(f):
        ff = unicodedata.normalize("NFC", f).casefold().strip()
        return ("hangul", ff) if ff else None
    ff = mc.fold(f).strip()
    if not ff:
        return None
    if mc.is_cjk(ff):
        return ("cjk", re.compile(re.escape(ff)))
    before, after = _BEFORE, _AFTER
    if not glued:
        before += r"(?<![^\W\d_][-\u2010\u2011])"
        after += r"(?![-\u2010\u2011][^\W\d_])"
    if acc_rule(f):
        fa = unicodedata.normalize("NFC", f).casefold().strip()
        return (
            "accent",
            re.compile(before + _form_pattern(fa, True) + after),
            re.compile(before + _form_pattern(ff, False) + after),  # unaccented: English form
            " " in ff,
        )
    return ("plain", re.compile(before + _form_pattern(ff, infl_rule(f)) + after))


@functools.lru_cache(maxsize=4096)
def _views_cached(text: str) -> tuple[str, str, str]:
    return _views(text)


@functools.cache
def _ascii_twins(forms: tuple[str, ...], acc_rule: _Rule) -> frozenset[str]:
    """wbforms-v4 (review of PR #208, round 4d nit): the bank also lists an accent-only name's
    plain-ASCII spelling as a form of its own ("Dali" beside "Dalí", "Cezanne", "Melies"), which
    matched case-insensitively ("by dali", "a dali-like scene"). Such a one-word twin of an
    accent-only label word follows the accent-only rule: as one bare word it counts only
    capitalized."""
    # the accented words of the option's own label (forms[0], the bank's order): "Dalí" of
    # "Salvador Dalí"; an accent in some other language's form ("Lénine") makes no twin, so
    # lowercase token-list "lenin" / "chopin" still count
    label = forms[0] if forms else ""
    acc = (
        {mc.fold(w).strip(".,") for w in label.split() if not w.isascii()}
        if acc_rule(label)
        else set()
    )
    return frozenset(
        f
        for f in forms
        if f.isascii() and " " not in f.strip() and not acc_rule(f) and mc.fold(f).strip() in acc
    )


def name_spans(text: str, forms: Sequence[str], *, glued: bool = True) -> list[tuple[int, int]]:
    """Where the forms occur in ``mc.fold(text)`` (see FORMS_VERSION); ``glued=False``: a Latin
    form glued by a hyphen into a longer name ("Wong Fei-Hung") does not count."""
    t, t_acc, t_case = _views_cached(text)
    twins = _ascii_twins(tuple(forms), accent_only)
    out: list[tuple[int, int]] = []
    for f in forms:
        plan = _plan(f, glued)
        if plan is None:
            continue
        kind = plan[0]
        if f in twins and kind == "plain":
            out += [
                (m.start(), m.end()) for m in plan[1].finditer(t) if t_case[m.start()].isupper()
            ]
            continue
        if kind == "hangul":
            if plan[1] in unicodedata.normalize("NFC", text).casefold():
                out.append((0, 0))  # Hangul: presence only (NFC offsets differ from fold's)
        elif kind == "cjk":
            out += [(m.start(), m.end()) for m in plan[1].finditer(t)]
        elif kind == "accent":
            out += [(m.start(), m.end()) for m in plan[1].finditer(t_acc)]
            out += [
                (m.start(), m.end())
                for m in plan[2].finditer(t)
                if plan[3] or t_case[m.start()].isupper()
            ]
        else:
            out += [(m.start(), m.end()) for m in plan[1].finditer(t)]
    return out


def _any_plan(forms: Sequence[str]) -> tuple[re.Pattern[str] | None, tuple[str, ...]]:
    return _any_compiled(tuple(forms), inflecting, accent_only)


def _twin(f: str, forms: tuple[str, ...], acc_rule: _Rule) -> bool:
    return f in _ascii_twins(forms, acc_rule)


@functools.cache
def _any_compiled(
    forms: tuple[str, ...], infl_rule: _Rule, acc_rule: _Rule
) -> tuple[re.Pattern[str] | None, tuple[str, ...]]:
    """(one alternation of every plain form's pattern, the other forms): :func:`name_in` asks
    only whether some form occurs, so the plain forms are searched in one pass."""
    plain, rest = [], []
    for f in forms:
        plan = _compiled(f, True, infl_rule, acc_rule)
        if plan is None:
            continue
        if plan[0] == "plain" and not _twin(f, forms, acc_rule):
            plain.append(f"(?:{plan[1].pattern})")
        else:
            rest.append(f)
    return (re.compile("|".join(plain)) if plain else None), tuple(rest)


def name_in(text: str, forms: Sequence[str]) -> bool:
    """A listed form of an option occurs in ``text`` (see FORMS_VERSION)."""
    alt, rest = _any_plan(forms)
    if alt is not None and alt.search(_views_cached(text)[0]):
        return True
    return bool(rest) and bool(name_spans(text, rest))


def load_items() -> list[dict[str, Any]]:
    _header, items = load_bank(bank_path(NAME))
    return items


def shown_options(it: dict[str, Any]) -> list[str]:
    """The item's numbered list as the judge sees it: the frozen order, CANNOT last."""
    return wp.render_options(list(it["mc"]["order"]))[0]


def positions(it: dict[str, Any]) -> tuple[int, int]:
    """(gold, contrast) 1-based positions in the shown list."""
    order = list(it["mc"]["order"])
    return order.index(it["mc"]["gold"]) + 1, order.index(it["mc"]["contrast"]) + 1


def _squash(s: str) -> str:
    return "".join(ch for ch in digest.fold_quote(s) if ch.isalnum())


def echo_of_prompt(quote: str, prompt: str) -> bool:
    """The quote (folded, whitespace and punctuation removed) is part of the prompt (folded the
    same way): a name the readout copied from the input is not evidence of the bridge
    (``album_label-Q21480481-founded_year``: "Bluenote" from "Bluenote Café")."""
    q = _squash(quote)
    return bool(q) and q in _squash(prompt)


def _option_tests(
    it: dict[str, Any],
) -> tuple[
    Callable[[str], bool], Callable[[digest.Line], bool], Callable[[str, digest.Line], bool]
]:
    """(names_gold, single_gold, single_option): a quote's text holds a listed form of the gold;
    a digest line holds a gold form and no form of any other candidate (the rival check's
    own-line support); a digest line singles out (the same way) a non-gold candidate the rival
    quote names."""
    forms = it["mc"]["forms"]
    gold = it["mc"]["gold"]
    others = [o for o in it["mc"]["order"] if o != gold]

    def names_gold(text: str) -> bool:
        return name_in(norm(text), forms[gold])

    order = list(it["mc"]["order"])

    def single(o: str, ln: digest.Line) -> bool:
        t = norm(ln.text)
        return name_in(t, forms[o]) and not any(name_in(t, forms[x]) for x in order if x != o)

    def single_gold(ln: digest.Line) -> bool:
        return single(gold, ln)

    def single_option(rq: str, ln: digest.Line) -> bool:
        named = [o for o in others if name_in(norm(rq), forms[o])]
        return len(named) == 1 and single(named[0], ln)

    return names_gold, single_gold, single_option


# ------------------------------------------------------------------ the contrast's own line
# (review of PR #208, round 4): the true bridge B is weighed whether or not the judge names it,
# but only through a line that names B in full and in the hidden entity's role. A bare Q10
# surname matched the character in "Jet Li as Wong Fei-Hung" for Sammo Hung (Q691478, all-layer
# contested 19 vs 24), "Keyshia Cole" for J. Cole (Q27981679)

_SEGMENT = re.compile(r"[·・•‧]")
# the role cues of each template (folded; a Latin cue is a word start, so "direct" also matches
# "directed" / "director"; a CJK cue is a substring), searched in a window around the name
_PERFORMER = "releas record perform sing sang sung rapper band artist 演唱 歌手 乐队 樂隊 樂團"
_CUES = {
    "film_director": "direct helm filmmaker regia regist 导演 導演 执导 執導",
    "painting_creator": "paint artist 画 畫",
    "novel_author": "author wrot writ novelist poet 作者 作家 著 写 寫",
    "composition_composer": "compos wrot writ 作曲",
    "album_performer": _PERFORMER + " album 专辑 專輯",
    "song_performer": _PERFORMER + " song single",
    "album_label": "label releas record sign issu 唱片",
    "doctoral_advisor": "advis supervis mentor doctoral phd 导师 導師",
    "person_father": "father son daughter child sire 父",
    "person_mother": "mother son daughter child 母",
    "org_founder": "found establish creat 创 創",
    "game_developer": "develop studio creat made produc 开发 開發",
    "product_manufacturer": "manufactur built build made produc maker shipyard shipbuild 制造 製造",
    "namesake": "name honor honour 命名",
    "song_lyricist": "lyric wrot writ 作词 作詞",
    "character_creator": "creat invent wrot writ 创 創",
    "tv_network": "network air broadcast channel 电视 電視",
}
ROLE_CUES: dict[str, tuple[str, ...]] = {k: tuple(v.split()) for k, v in _CUES.items()}
# words of the prompt's subject phrase that are no tie to the work itself (kinds, roles, years)
_SUBJECT_STOP = frozenset(
    {"film", "album", "song", "video", "game", "record", "label", "released", "recorded"}
    | {"originally", "aired", "fictional", "character", "artist", "that", "with", "from"}
)
ROLE_BEFORE, ROLE_AFTER = 60, 40  # characters of folded text around the name (~8 / ~6 words)
_BY = re.compile(r"(?<!\w)by(?!\w)|由")


def full_forms(forms: Sequence[str], label: str) -> list[str]:
    """The option's forms without its Q10 short forms: a one-word form that is the last word of
    a multi-word Latin form ("Hung" of "Sammo Hung") or the last segment of a CJK name ("圣齐奥"
    of "拉斐尔·圣齐奥"). The option's own label is always kept (a mononym: "Raphael")."""
    lasts: set[str] = set()
    for f in forms:
        parts = _SEGMENT.split(f) if mc.is_cjk(f) else f.split()
        if len(parts) >= 2:
            lasts.add(mc.fold(parts[-1].strip(".,")).strip())
    return [f for f in forms if f == label or mc.fold(f).strip() not in lasts]


def _form_spans(text: str, forms: Sequence[str]) -> list[tuple[int, int]]:
    """Where the forms occur in folded ``text`` (:func:`name_spans`), not glued by a hyphen into
    a longer name ("Wong Fei-Hung")."""
    return name_spans(text, forms, glued=False)


_SUBJECT = re.compile(r"^\s*fact:\s*(the .+?) (?:was|were|is|died)\b", re.IGNORECASE)


def subject_of(prompt: str) -> str:
    """The prompt's subject phrase, the role and the work ("The director of the 1984 film Il
    futuro è donna"), without the asked relation or any answer; the rival audit's only view of
    the prompt."""
    m = _SUBJECT.match(prompt)
    return m.group(1) if m else ""


def subject_words(prompt: str) -> tuple[str, ...]:
    """The folded words (>= 4 letters) of the work or thing the prompt asks about ("the
    namesake of the Saint Petersburg Conservatory" -> saint, petersburg, conservatory): a name
    beside one of them is tied to the work in question."""
    words = re.findall(r"[^\W\d_]{4,}", mc.fold(subject_of(prompt)))
    return tuple(dict.fromkeys(w for w in words if w not in _SUBJECT_STOP))


def _role_tied(text: str, span: tuple[int, int], cues: Sequence[str]) -> bool:
    """A cue (a role cue of the template or a subject word, :func:`subject_words`) in the window
    around the name at ``span`` in folded ``text`` (not the word right before it), or "by"
    just before it."""
    before = text[max(0, span[0] - ROLE_BEFORE) : span[0]]
    after = text[span[1] : span[1] + ROLE_AFTER]
    if _BY.search(before[-12:]):
        return True
    # an apposition ("the painter Raphael Sanzio died in Rome") describes the name, it does not
    # tie it to the role: the word right before the name is no cue
    before = re.sub(r"[^\W\d_]+\s*$", " ", before)
    for cue in cues:
        if mc.is_cjk(cue):
            if cue in before or cue in after:
                return True
        elif re.search(rf"(?<!\w){re.escape(cue)}", before + " " + after):
            return True
    return False


def option_line(it: dict[str, Any], o: str, ln: digest.Line) -> bool:
    """The line counts as candidate ``o``'s own support: it names ``o`` through a full form
    (:func:`full_forms`, not hyphen-glued) with a role cue of the item's template or a word of
    the prompt's subject near that mention, and names no other candidate by any form."""
    forms = it["mc"]["forms"]
    t = norm(ln.text)
    if not name_in(t, forms[o]):
        return False
    if any(name_in(t, forms[x]) for x in it["mc"]["order"] if x != o):
        return False
    cues = (*ROLE_CUES.get(str(it.get("template", "")), ()), *subject_words(it["prompt"]))
    tf = mc.fold(t)  # name_spans' offsets are into the folded text
    return any(_role_tied(tf, sp, cues) for sp in _form_spans(t, full_forms(forms[o], o)))


def contrast_line(it: dict[str, Any], ln: digest.Line) -> bool:
    """:func:`option_line` of the contrast (the true bridge B)."""
    return option_line(it, it["mc"]["contrast"], ln)


def _named_option(it: dict[str, Any], text: str) -> str | None:
    """The one non-gold candidate ``text`` names (any listed form), else None."""
    forms = it["mc"]["forms"]
    t = norm(text)
    named = [o for o in it["mc"]["order"] if o != it["mc"]["gold"] and name_in(t, forms[o])]
    return named[0] if len(named) == 1 else None


AUDIT_MAX_LINES = 30  # the rival audit checks at most this many lines (largest first)
# a competing entity weighs in the summed rival support when its best entry has at least this
# share of the gold's best; the gold must then outweigh them all together (OUTWEIGH: more samples
# than their sum), on top of leading each one by rival.FAR_MORE (Q591875: Pantera 27 vs
# Aerosmith 14 + AC/DC 13 + Steeler 10)
PROMINENT = 1 / 3
OUTWEIGH = rival.Margin(1.0, 1)


def prominent(count: int, gold: int) -> bool:
    return count >= PROMINENT * gold


# capitalized words that start sentences or clauses and name nobody (other_name)
_NOT_NAMES = frozenset(
    {"a", "an", "the", "this", "that", "these", "those", "it", "its", "he", "his", "she", "her"}
    | {"they", "their", "there", "here", "in", "on", "of", "at", "by", "for", "from", "with"}
    | {"and", "but", "or", "so", "as", "also", "however", "both", "while", "when", "which"}
    | {"who", "whose", "what", "yes", "no", "not", "fact"}
)
_CAP_WORD = re.compile(r"[^\W\d_][^\W_]*")


def other_name(it: dict[str, Any], text: str, *, cjk: bool = True) -> bool:
    """A line that names the gold could also give someone else in the role only if it holds
    another name: a capitalized word outside the gold's own mentions that is no function word
    and no word of the prompt, or a CJK character outside them. A line naming only the gold
    ("the sonata is by **Beethoven**") is not sent to the rival audit (wbaudit-v2). ``cjk=False``:
    CJK characters do not count (they cannot be told from a name without segmentation)."""
    t = norm(text)
    _fold, _acc, case = _views_cached(t)
    keep = list(case)
    for a, b in name_spans(t, it["mc"]["forms"][it["mc"]["gold"]]):
        keep[a:b] = " " * (b - a)
    rest = "".join(keep)
    if cjk and mc.is_cjk(rest):
        return True
    prompt = set(mc.fold(it["prompt"]).split())
    for m in _CAP_WORD.finditer(rest):
        w = m.group()
        if w[0].isupper() and mc.fold(w) not in _NOT_NAMES and mc.fold(w) not in prompt:
            return True
    return False


def audit_lines(
    it: dict[str, Any], gold: int, grounded: Sequence[digest.Grounded]
) -> list[digest.Grounded]:
    """The digest entries the rival audit checks first: every :func:`prominent` entry (smaller
    ones cannot weigh in :func:`combined_support`) whose line names no form of the gold, largest
    first, at most :data:`AUDIT_MAX_LINES` (:func:`audit_shown` appends the gold's split
    candidates after them)."""
    names_gold = _option_tests(it)[0]
    keep = [g for g in grounded if prominent(g.count, gold) and not names_gold(g.line.text)]
    keep.sort(key=lambda g: -g.count)  # stable: digest order within a count
    return keep[:AUDIT_MAX_LINES]


def split_candidates(
    it: dict[str, Any], gold: int, grounded: Sequence[digest.Grounded], *, cjk: bool = True
) -> list[digest.Grounded]:
    """The :func:`prominent` entries that name the gold AND hold another name
    (:func:`other_name`), largest first: wbaudit-v2 (review of PR #208, round 4d) checks them
    too, since such a line may give the gold and a different person in the same role (a split
    line, weighed as that rival's, :func:`audit_split`). wbaudit-v1 skipped every line naming
    the gold, so L52 composer-Q182537 (Lennon) passed with "The composer of the song tax was Paul
    McCartney" on ~16 samples of Lennon lines, weighed nowhere."""
    names_gold = _option_tests(it)[0]
    keep = [
        g
        for g in grounded
        if prominent(g.count, gold)
        and names_gold(g.line.text)
        and other_name(it, g.line.text, cjk=cjk)
    ]
    keep.sort(key=lambda g: -g.count)
    return keep


def audit_shown(
    it: dict[str, Any], gold: int, grounded: Sequence[digest.Grounded]
) -> list[digest.Grounded]:
    """The numbered lines of the rival audit: :func:`audit_lines`, then the
    :func:`split_candidates` (so a non-gold line keeps its number), at most
    :data:`AUDIT_MAX_LINES`. Empty (no audit call) when there is no non-gold line and no
    gold line holds another Latin-script name: a CJK line always holds other characters, so it
    joins an audit but never starts one."""
    base = audit_lines(it, gold, grounded)
    if not base and not split_candidates(it, gold, grounded, cjk=False):
        return []
    extra = split_candidates(it, gold, grounded)
    return (base + extra)[:AUDIT_MAX_LINES]


def render_audit_lines(gs: Sequence[digest.Grounded]) -> str:
    return "\n".join(
        f"{n}. [{digest.support_text(g.count)}] {' '.join(g.line.text.split())}"
        for n, g in enumerate(gs, 1)
    )


def audit_rivals(
    it: dict[str, Any], audit: dict[str, Any] | None, shown: Sequence[digest.Grounded]
) -> list[tuple[digest.Grounded, str]]:
    """The (entry, name) pairs the rival audit marks a rival: ``audit["verdicts"]`` numbers the
    ``shown`` lines (:func:`audit_lines`); a name that is the gold's is no rival."""
    names_gold = _option_tests(it)[0]
    out: list[tuple[digest.Grounded, str]] = []
    if not isinstance(audit, dict) or not isinstance(audit.get("verdicts"), list):
        return out
    for e in audit["verdicts"]:
        if not isinstance(e, dict) or e.get("rival") is not True:
            continue
        n = e.get("line")
        if not isinstance(n, int) or not 1 <= n <= len(shown):
            continue
        name = str(e.get("name", "") or "").strip()
        if name and names_gold(name):
            continue
        out.append((shown[n - 1], name))
    return out


def audit_split(
    it: dict[str, Any], audit: dict[str, Any] | None, shown: Sequence[digest.Grounded]
) -> set[int]:
    """``id`` of every entry that names the gold and that the rival audit marks a rival (it also
    gives a different person in the role): a split line, counting for neither side in
    ``rival.contest`` and weighed as that rival's in :func:`rival_entities` (wbaudit-v2)."""
    names_gold = _option_tests(it)[0]
    return {
        id(g)
        for g, name in audit_rivals(it, audit, shown)
        if names_gold(g.line.text) and line_names(it, name, g.line.text)
    }


def line_names(it: dict[str, Any], name: str, text: str) -> bool:
    """The audit's rival ``name`` occurs in ``text``: a listed candidate through its forms, else
    the name itself or its last word (4+ letters, "McCartney" for "Paul McCartney"). A split
    line is cut from the gold only on a name it holds, never on the audit's word alone."""
    t = norm(text)
    opt = _named_option(it, name)
    if opt is not None:
        return name_in(t, it["mc"]["forms"][opt])
    words = name.split()
    forms = [name] + ([words[-1]] if len(words) > 1 and len(words[-1]) >= 4 else [])
    return bool(name.strip()) and name_in(t, forms)


def rival_entities(
    it: dict[str, Any],
    result: dict[str, Any],
    grounded: Sequence[digest.Grounded],
    audit: dict[str, Any] | None,
    shown: Sequence[digest.Grounded] | None = None,
) -> dict[str, digest.Grounded]:
    """Each competing entity's best digest entry (round 4 of PR #208): the contrast's own line
    (:func:`contrast_line`), every :func:`audit_lines` entry the rival audit marks a rival
    (``audit["verdicts"]``: line number, rival, name) and the MC call's ``rival_quote``. A line
    that names the gold is no rival. Keyed by the listed candidate a name singles out, else by
    the folded name; the MC rival quote joins the entity of the audited line holding it."""
    names_gold, _single_gold, single_option = _option_tests(it)
    best: dict[str, digest.Grounded] = {}
    key_of: dict[int, str] = {}  # id(entry) -> the audit's entity key

    def add(key: str, gs: Sequence[digest.Grounded]) -> None:
        for g in gs:
            if key not in best or g.count > best[key].count:
                best[key] = g

    add(it["mc"]["contrast"], [g for g in grounded if contrast_line(it, g.line)])
    if shown is None:
        shown = audit_shown(it, pre_gold_support(it, result, grounded), grounded)
    for n, (g, name) in enumerate(audit_rivals(it, audit, shown), 1):
        if names_gold(g.line.text) and not line_names(it, name, g.line.text):
            continue  # a gold line is a rival's only through a name it holds (audit_split)
        key = _named_option(it, name) or "~" + (digest.fold_quote(name) or f"line{n}")
        key_of[id(g)] = key
        add(key, [g])
    rq = str(result.get("rival_quote", "") or "").strip()
    if rq and not names_gold(rq):
        hs = [
            g for g in rival.holders(rq, grounded) if id(g) in key_of or not names_gold(g.line.text)
        ]
        if hs:
            same = [key_of[id(g)] for g in hs if id(g) in key_of]
            key = _named_option(it, rq) or (same[0] if same else "~rival_quote")
            add(key, hs + [g for g in grounded if single_option(rq, g.line)])
    return best


def pre_gold_support(
    it: dict[str, Any], result: dict[str, Any] | None, grounded: Sequence[digest.Grounded]
) -> int:
    """The gold support before the rival audit (``rival.contest`` without audit splits): the
    prominence bar of :func:`audit_lines`, so the run and :func:`decide` number the same
    lines."""
    names_gold, single_gold, _single_option = _option_tests(it)
    rv = rival.contest(
        result, grounded, single_gold=single_gold, names_gold=names_gold, margin=rival.FAR_MORE
    )
    return int(rv["gold_support"])


def combined_support(gold: int, entities: dict[str, digest.Grounded]) -> int:
    """The summed support of every :func:`prominent` competing entity (its best entry; an entry
    shared by two entities counts once). A gold that does not outweigh it (:data:`OUTWEIGH`) is
    a plurality among several near answers, not a clear favourite (Camila: "if there are a ton
    of different equally prominent answers then it should not pass")."""
    keep = {id(g): g for g in entities.values() if prominent(g.count, gold)}
    return sum(g.count for g in keep.values())


def decide(
    result: dict | None,
    it: dict[str, Any],
    lines: list[digest.Line],
    grounded: list[digest.Grounded] | None = None,
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One MC answer as a verdict: ``pick`` (one of :data:`PICKS`, or None = unjudged) and the
    gate fields. Only a gold pick whose quote passes every gate is ``credited``. ``grounded``
    (summary mode: ``col.grounded[item]``, the digest entries with their sample counts) adds the
    rival check (:func:`wsbench.rival.contest`): a gold pick the judge's rival line nearly
    matches is ``contested``, never credited; so is one that does not lead every competing entity
    by ``rival.FAR_MORE`` or does not outweigh the prominent ones together (:func:`rival_entities`
    over the contrast, the rival ``audit`` answer and the MC rival quote;
    :func:`combined_support`)."""
    if result is None:
        return {"pick": None, "credited": False}
    gold_pos, contrast_pos = positions(it)
    kind = mc.classify(choice_of(result), gold_pos, N_SHOWN, contrast_pos=contrast_pos)
    quote = quote_of(result)
    out: dict[str, Any] = {"choice": choice_of(result), "quote": quote, "credited": False}
    if kind != "gold":
        out["pick"] = kind
        return out
    verified = digest.quote_ok(quote, lines)
    form = name_in(norm(quote), it["mc"]["forms"][it["mc"]["gold"]])
    echo = echo_of_prompt(quote, it["prompt"])
    credited = verified and form and not echo
    out.update(
        pick="gold" if credited else "gold_uncredited",
        credited=credited,
        quote_verified=verified,
        form_ok=form,
        echo_of_prompt=echo,
    )
    if credited and grounded is not None:
        names_gold, single_gold, single_option = _option_tests(it)
        shown = audit_shown(it, pre_gold_support(it, result, grounded), grounded)
        cut = audit_split(it, audit, shown)
        rv = rival.contest(
            result,
            grounded,
            single_gold=single_gold,
            names_gold=names_gold,
            single_option=single_option,
            margin=rival.FAR_MORE,
            split=lambda g: id(g) in cut,
        )
        # the true bridge B (the contrast) is the canonical rival whether or not the judge names
        # it: its best digest line naming it in full and in the role counts too (round 3: L52
        # Q3221113, Asimov 4 vs Heinlein 3 author lines, passed when the judge quoted a weaker
        # rival; round 4: a bare surname or a line with no role cue is no such line)
        rv["contrast_support"] = max(
            (g.count for g in grounded if contrast_line(it, g.line)), default=0
        )
        ents = rival_entities(it, result, grounded, audit, shown)
        rv["rival_entities"] = {k: g.count for k, g in ents.items()}
        rv["top_rival_support"] = max((g.count for g in ents.values()), default=0)
        rv["combined_support"] = combined_support(rv["gold_support"], ents)
        rv["contested"] = (
            bool(rv["contested"])
            or rival.FAR_MORE.contested(rv["gold_support"], rv["contrast_support"])
            or rival.FAR_MORE.contested(rv["gold_support"], rv["top_rival_support"])
            or OUTWEIGH.contested(rv["gold_support"], rv["combined_support"])
        )
        out.update(rv)
        if rv["contested"]:
            out.update(pick="contested", credited=False)
    return out


def _mc_version(pv: str) -> str:
    """The MC call's fingerprint version: ``pv`` keyed by the rival rule's call version and
    without the audit stamp (the MC prompt did not change with the audit, so cached MC answers
    are re-scored, not re-asked)."""
    out = rival.call_version(pv)
    for tag in (wp.AUDIT_VERSION, wp.FORMS_VERSION, wp.BANK_TAG):
        out = out.replace("+" + tag, "", 1)
    return out


def _audit_version(pv: str) -> str:
    """The rival audit's fingerprint version: ``pv`` without the forms stamp (round 4e). A forms
    change that moves which lines the audit sees changes its user message, so those calls are
    re-asked anyway; one that does not re-scores the cached answers instead of re-asking every
    audit (rounds 4c / 4d re-asked them all, and the re-ask variation moved cells)."""
    return pv.replace("+" + wp.FORMS_VERSION, "", 1)


def _valid_audit(_call: Call, r: dict) -> bool:
    return isinstance(r.get("verdicts"), list)


def audit_user(
    it: dict[str, Any],
    result: dict[str, Any],
    summary: str,
    note: str,
    shown: Sequence[digest.Grounded],
) -> str:
    """The rival audit's user message: the candidates, the MC call's pick and quote, the digest
    and the numbered :func:`audit_lines`."""
    opts, listing = wp.render_options(list(it["mc"]["order"]))
    c = choice_of(result)
    choice = f"{c}. {opts[c - 1]}" if isinstance(c, int) and 1 <= c <= len(opts) else str(c)
    return wp.render_audit_user(
        subject_of(it["prompt"]),
        listing,
        choice,
        quote_of(result),
        note,
        summary,
        render_audit_lines(shown),
    )


def _valid(_call: Call, r: dict) -> bool:
    return mc.classify(choice_of(r), 1, N_SHOWN) != "invalid"


def _kind_note(kind: str | None) -> str:
    return digest.token_note_of(NAME) if kind == "tokens" else wp.KIND_NOTE_PROSE


def native_user(it: dict[str, Any], cells: list[Cell], kind: str | None) -> str:
    """The native user message for one (item, layer): every position's samples, rendered by
    ``digest.native_lines`` (a multi-bullet sample shows as ``- a ⁞ b ⁞ c``)."""
    by_pos: dict[int, list[Cell]] = defaultdict(list)
    for c in cells:
        by_pos[c.pos].append(c)
    blocks = []
    for pos in sorted(by_pos):
        lines = digest.native_lines(by_pos[pos])
        if lines:
            blocks.append(wp.render_block(pos, "\n".join(f"- {ln.text}" for ln in lines)))
    _shown, listing = wp.render_options(list(it["mc"]["order"]))
    return wp.render_user(listing, _kind_note(kind), "\n\n".join(blocks))


def summary_user(it: dict[str, Any], summary: str, note: str) -> str:
    _shown, listing = wp.render_options(list(it["mc"]["order"]))
    return wp.render_user_summary(listing, note, summary)


def _counts(verdicts: list[dict[str, Any]]) -> dict[str, int]:
    out = dict.fromkeys(PICKS, 0)
    for v in verdicts:
        if v.get("pick") in out:
            out[v["pick"]] += 1
    return out


def run(args: JudgeArgs) -> FamilyResult:
    items = load_items()
    scope = item_scope(items, args)
    ids = [it["id"] for it in scope]
    cells, rep = reads.load(args, NAME, ids=ids)
    layers = args.layers if args.layers is not None else rep.layers
    groups: dict[tuple[str, int], list[Cell]] = defaultdict(list)
    for c in cells:
        groups[(c.id, c.layer)].append(c)
    expected = [(i, layer) for i in ids for layer in layers]
    missing = [k for k in expected if k not in groups]
    require_cells(NAME, missing, len(expected), args)
    if digest.summary_mode(args):
        return _run_summary(args, scope, cells, rep, groups, expected, missing)
    return _run_native(args, scope, cells, rep, layers, groups, expected, missing)


def _run_native(
    args: JudgeArgs,
    scope: list[dict[str, Any]],
    cells: list[Cell],
    rep: Any,
    layers: list[int],
    groups: dict[tuple[str, int], list[Cell]],
    expected: list[tuple[str, int]],
    missing: list[tuple[str, int]],
) -> FamilyResult:
    calls: list[Call] = []
    lines_of: dict[str, list[digest.Line]] = {}
    empty: set[tuple[str, int]] = set()
    for it in scope:
        for layer in layers:
            cs = groups.get((it["id"], layer))
            if cs is None:
                continue
            lines = digest.native_lines(cs)
            if not lines:
                empty.add((it["id"], layer))
                continue
            key = f"{it['id']}|L{layer:03d}"
            lines_of[key] = lines
            calls.append(
                Call(
                    key=key,
                    system=wp.SYSTEM,
                    user=native_user(it, cs, rep.kind),
                    meta={"item": it["id"], "layer": layer},
                )
            )
    spend = Spend()
    with Cache(args.out / "cells.jsonl") as cache:
        results = run_calls(
            calls,
            schema=wp.SCHEMA,
            judge=args.judge,
            prompt_version=_mc_version(wp.PROMPT_VERSION),
            cache=cache,
            spend=spend,
            concurrency=args.concurrency,
            rpm=args.rpm,
            dry_run=args.dry_run,
            preflight=Preflighter(args.dry_run).for_judge(args.judge),
            validate=_valid,
            temperature=0.0,
        )
    rows: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    n_unjudged = 0
    for it in scope:
        per: dict[str, dict[str, Any]] = {}
        n_miss = n_unj = 0
        for layer in layers:
            k = (it["id"], layer)
            if k not in groups:
                n_miss += 1
                continue
            if k in empty:
                per[str(layer)] = {"pick": "empty", "credited": False}
                continue
            key = f"{it['id']}|L{layer:03d}"
            v = decide(results.get(key), it, lines_of[key])
            if v["pick"] is None:
                n_unj += 1
            else:
                verdicts.append(v)
            per[str(layer)] = v
        n_unjudged += n_unj
        credited = [int(L) for L, v in per.items() if v.get("credited")]
        contrast = any(v.get("pick") == "contrast" for v in per.values())
        undecided = n_miss > 0 or n_unj > 0 or not per
        passed = tri_state(bool(credited), undecided)
        gold_pos, contrast_pos = positions(it)
        rows.append(
            {
                "id": it["id"],
                "pass": passed,
                "picked_true_bridge": bool(contrast and not credited)
                if passed is not None
                else None,
                "earliest_layer": min(credited) if credited else None,
                "options": shown_options(it),
                "gold_position": gold_pos,
                "contrast_position": contrast_pos,
                "n_missing": n_miss,
                "n_unjudged": n_unj,
                "layers": {L: v.get("pick") for L, v in per.items()},
                "verdicts": per,
            }
        )
    extras = _extras(rows, verdicts, len(calls))
    extras.update(layer_pick_columns(rows))
    result = pass_rate_result(
        name=NAME,
        args=args,
        prompt_version=wp.PROMPT_VERSION,
        rows=rows,
        cells=cells,
        rep=rep,
        n_expected=len(expected),
        n_missing=len(missing),
        n_unjudged=n_unjudged,
        n_empty=len(empty),
        spend=spend,
        chance_label=CHANCE_LABEL,
        extras=extras,
    )
    result.chance = CHANCE
    return with_readout_count(result, scope, cells)


def _extras(
    rows: list[dict[str, Any]], verdicts: list[dict[str, Any]], n_calls: int
) -> dict[str, Any]:
    decided = [r for r in rows if r["pass"] is not None]
    n_tb = sum(1 for r in decided if r.get("picked_true_bridge"))
    return {
        "n_calls": n_calls,
        "pick_counts": _counts(verdicts),
        "n_contested": sum(1 for v in verdicts if v.get("pick") == "contested"),
        "n_rival_unverified": sum(1 for v in verdicts if v.get("rival_verified") is False),
        "rival_margin": {"ratio": rival.FAR_MORE.ratio, "lead": rival.FAR_MORE.lead},
        "n_items_picked_true_bridge": n_tb,
        "true_bridge_rate": n_tb / len(decided) if decided else None,
    }


def _run_summary(
    args: JudgeArgs,
    scope: list[dict[str, Any]],
    cells: list[Cell],
    rep: Any,
    groups: dict[tuple[str, int], list[Cell]],
    expected: list[tuple[str, int]],
    missing: list[tuple[str, int]],
) -> FamilyResult:
    by_item: dict[str, list[Cell]] = defaultdict(list)
    for (i, _layer), cs in groups.items():
        by_item[i].extend(cs)
    partial = {i for i, _layer in missing}
    by_id = {it["id"]: it for it in scope}
    spend = Spend()
    pre = Preflighter(args.dry_run)
    pv = digest.prompt_version(wp.PROMPT_VERSION, args, NAME)
    with Cache(args.out / "cells.jsonl") as cache:
        col = digest.collapse(
            NAME,
            {i: by_item[i] for i in by_id if by_item.get(i)},
            args=args,
            cache=cache,
            spend=spend,
            preflight=pre.for_judge(digest.summarizer_judge(args, NAME)),
            task_note=wp.TASK_NOTE,
            expect_all=cells,
        )
        source_kind = digest.as_prose(rep)
        note = digest.summary_note(args, source_kind, NAME)
        calls = [
            Call(
                key=f"{i}|summary",
                system=wp.SYSTEM,
                user=summary_user(by_id[i], (c.samples or ("",))[0], note),
                meta={"item": i},
            )
            for i, c in col.cells.items()
            if i not in col.unsummarized and i not in col.empty
        ]
        results = run_calls(
            calls,
            schema=wp.SCHEMA,
            judge=args.judge,
            prompt_version=_mc_version(pv),
            cache=cache,
            spend=spend,
            concurrency=args.concurrency,
            rpm=args.rpm,
            dry_run=args.dry_run,
            preflight=pre.for_judge(args.judge),
            validate=_valid,
            temperature=0.0,
        )
        # the rival audit (round 4): one more call per credited gold pick marks each prominent
        # digest line (audit_lines), so the check does not hang on the MC call naming the strongest
        summary_of = {i: (c.samples or ("",))[0] for i, c in col.cells.items()}
        audit_calls = []
        for call in calls:
            i = call.meta["item"]
            r = results.get(call.key)
            gr = list(col.grounded.get(i, ()))
            pre_v = decide(r, by_id[i], list(col.evidence.get(i, ())), gr)
            shown = audit_shown(by_id[i], pre_gold_support(by_id[i], r, gr), gr)
            if pre_v.get("credited") and shown:
                audit_calls.append(
                    Call(
                        key=f"{i}|rivals",
                        system=wp.AUDIT_SYSTEM,
                        user=audit_user(by_id[i], r or {}, summary_of[i], note, shown),
                        meta={"item": i},
                    )
                )
        audits = run_calls(
            audit_calls,
            schema=wp.AUDIT_SCHEMA,
            judge=args.judge,
            prompt_version=_audit_version(pv),
            cache=cache,
            spend=spend,
            concurrency=args.concurrency,
            rpm=args.rpm,
            dry_run=args.dry_run,
            preflight=pre.for_judge(args.judge),
            validate=_valid_audit,
            temperature=0.0,
        )
        audited = {c.meta["item"] for c in audit_calls}
    rows: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    n_unjudged = len(col.unsummarized)
    for it in scope:
        i = it["id"]
        gold_pos, contrast_pos = positions(it)
        row: dict[str, Any] = {
            "id": i,
            "options": shown_options(it),
            "gold_position": gold_pos,
            "contrast_position": contrast_pos,
            "n_missing": sum(1 for k in missing if k[0] == i),
        }
        if i not in col.cells:  # no cells at all: the native missing path (undecided)
            row.update({"pass": None, "pick": None})
        elif i in col.unsummarized:
            row.update({"pass": None, "pick": None, "n_unjudged": 1})
        elif i in col.empty:
            row.update({"pass": False, "pick": "empty"})
        else:
            v = decide(
                results.get(f"{i}|summary"),
                it,
                list(col.evidence.get(i, ())),
                list(col.grounded.get(i, ())),
                audits.get(f"{i}|rivals"),
            )
            if i in audited and audits.get(f"{i}|rivals") is None and v.get("credited"):
                # a credited pick whose rival audit failed is not credited unchecked: unjudged
                v = {**v, "pick": None, "credited": False, "audit_failed": True}
            if v["pick"] is None:
                n_unjudged += 1
                row["n_unjudged"] = 1
            else:
                verdicts.append(v)
            passed = tri_state(bool(v.get("credited")), v["pick"] is None)
            if i in partial and passed is False:
                passed = None  # a missing layer leaves a non-pass undecided, as natively
            row.update({"pass": passed, **v})
        row["picked_true_bridge"] = (
            row.get("pick") == "contrast" if row["pass"] is not None else None
        )
        if i in col.cells:
            row.update(col.row(i))
        rows.append(row)
    extras = _extras(rows, verdicts, len(calls))
    extras["n_audit_calls"] = len(audit_calls)
    extras["summary"] = col.extras()
    result = pass_rate_result(
        name=NAME,
        args=args,
        prompt_version=pv,
        rows=rows,
        cells=cells,
        rep=rep,
        n_expected=len(expected),
        n_missing=len(missing),
        n_unjudged=n_unjudged,
        n_empty=len(col.empty),
        spend=spend,
        chance_label=CHANCE_LABEL,
        config_extra=digest.config(args, source_kind, NAME),
        extras=extras,
        n_items=len(scope),
        pinned=digest.pinned(args, NAME),
    )
    result.chance = CHANCE
    return with_readout_count(result, scope, cells)

# ruff: noqa: RUF001
"""Review of PR #208 (round 4b), BLOCKING 1: wrong_bridge bank v3 took Wikidata labels and
aliases in every language with no sanity filter, and the matcher let every Latin word of 4+
letters take a 2-letter tail, so ordinary English words and other people's names counted as the
gold in the form gate and in every rival check. Bank v4 (``items_v4.json``, the v3 options with
filtered forms, ``scripts/wrong_bridge_mc_options.py --v4``) and wbforms-v2 (the tail only for
forms spelled outside ASCII). Both directions: the too-lenient shapes no longer name the option,
the forms Camila asked for (regnal short form, Russian / Croatian inflection, Wikidata names in
other scripts) still do. The digest lines are verbatim from the cached final-olens-rl600-x4 L36
digests the review cites."""

from pathlib import Path

import pytest

from wsbench import digest
from wsbench.banks import load_bank
from wsbench.evals.wrong_bridge import judge as wj
from wsbench.evals.wrong_bridge import prompts as wp

REPO = Path(__file__).resolve().parents[1]
V3 = REPO / "evals/wrong_bridge/items_v3.json"
V4 = REPO / "evals/wrong_bridge/items_v4.json"
PANTERA = "album_performer-Q591875-formed_year"
BEYONCE = "album_performer-Q2564709-birth_city"
RAND = "doctoral_advisor-Q1235503-death_year"
HILBERT = "doctoral_advisor-Q536558-death_city"
MADONNA = "song_performer-Q246983-birth_year"
WILDE = "novel_author-Q730105-birth_city"
HANNA = "character_creator-Q1982693-death_year"
HAMID = "person_father-Q162543-birth_year"
ROGER = "org_founder-Q1303856-death_year"


@pytest.fixture(scope="module")
def v4() -> dict[str, dict]:
    return {it["id"]: it for it in load_bank(V4)[1]}


@pytest.fixture(scope="module")
def v3() -> dict[str, dict]:
    return {it["id"]: it for it in load_bank(V3)[1]}


def _in(it: dict, option: str, text: str) -> bool:
    return wj.name_in(wj.norm(text), it["mc"]["forms"][option])


def _g(text: str, count: int) -> digest.Grounded:
    ln = digest.Line(text)
    return digest.Grounded("", digest.support_text(count), text, ln, text, "items", "", count)


def test_v4_is_the_bank_of_record_and_stamped():
    from wsbench import registry

    assert registry.bank_path("wrong_bridge") == V4
    assert wp.FORMS_VERSION == "wbforms-v4" and wp.BANK_TAG == "bank-v4"
    assert wp.PROMPT_VERSION.endswith("+wbforms-v4+bank-v4")
    # a forms-only change: the MC call key is unchanged (cached MC answers are re-scored)
    assert "wbforms" not in wj._mc_version(wp.PROMPT_VERSION)
    assert "bank-v" not in wj._mc_version(wp.PROMPT_VERSION)


CITED_LENIENT = [
    (PANTERA, "Pantera", "Let's break this down"),  # Greek alias "Down" (another band)
    (RAND, "Ayn Rand", "a random philosopher"),  # Rand + "om"
    (HILBERT, "David Hilbert", "W. S. Gilbert"),  # Uzbek label "Gilbert"
    (MADONNA, "Madonna", "directed by Guy Ritchie"),  # a variant alias's surname
    (WILDE, "Oscar Wilde", "a wilder story"),  # Wilde + "r"
    (HANNA, "William Hanna", "Hannah Arendt"),  # Hanna + "h"
    (HAMID, "Abdul Hamid II", "The father of Mehmed VI was Abdul Hamid I."),  # numeral-less
    (BEYONCE, "Beyoncé", "His full name: Shawn Corey Carter"),  # Jay-Z's surname
    (ROGER, "Roger II of Sicily", "Рожер III was crowned"),  # another numeral
]


@pytest.mark.parametrize(("iid", "option", "text"), CITED_LENIENT)
def test_cited_too_lenient_shapes_name_nobody(v3, v4, iid, option, text, monkeypatch):
    assert not _in(v4[iid], option, text)
    with monkeypatch.context() as m:  # wbforms-v1: every word of 4+ letters took the tail
        m.setattr(wj, "inflecting", lambda _f: True)
        assert _in(v3[iid], option, text), "the review's case held on bank v3 + wbforms-v1"


STILL_NAMED = [
    (HAMID, "Abdul Hamid II", "Sultan Abdul Hamid II of the Ottoman Empire"),
    (HAMID, "Abdul Hamid II", "Abdul Hamid II., sultan"),
    (HAMID, "Abdul Hamid II", "압뒬하미트 2세"),
    (ROGER, "Roger II of Sicily", "founded by King Roger II"),  # the regnal short form
    (ROGER, "Roger II of Sicily", "основан королём Рожер II"),
    (ROGER, "Roger II of Sicily", "罗杰二世"),
    (HILBERT, "David Hilbert", "Hilbert's program"),
    (HILBERT, "David Hilbert", "учеником Давида Гильберта"),  # Russian inflection, Q10 form
    (PANTERA, "Pantera", "Pantera's Cowboys from Hell"),
    (PANTERA, "Pantera", "группа Пантера"),
    (RAND, "Ayn Rand", "Rand's Objectivism"),
    (MADONNA, "Madonna", "Madonna Louise Ciccone"),
    (MADONNA, "Madonna", "Madge"),  # a whole English alias
    (BEYONCE, "Beyoncé", "Beyoncé Knowles-Carter"),
    (WILDE, "Oscar Wilde", "Wilde wrote it"),
    (HANNA, "William Hanna", "Hanna-Barbera's founder"),
]


@pytest.mark.parametrize(("iid", "option", "text"), STILL_NAMED)
def test_real_namings_still_count(v4, iid, option, text):
    assert _in(v4[iid], option, text)


def test_matcher_tail_only_outside_ascii():
    # the too-lenient direction: an English-spelled form takes no ending
    assert not wj.name_in("a random philosopher", ["Rand"])
    assert not wj.name_in("a wilder story", ["Wilde"])
    assert not wj.name_in(digest.fold_quote("Hannah Arendt"), ["William Hanna", "Hanna"])
    # the too-strict direction (round 4, Camila r2): inflecting spellings keep the tolerance
    assert wj.name_in(digest.fold_quote("Назван в честь Карла Маркса"), ["Карл Маркс"])
    assert wj.name_in("Ivana Gundulića", ["Ivan Gundulić"])  # unfolded text (wbforms-v3)
    assert wj.name_in(digest.fold_quote("Αβδούλ Χαμίτ"), ["Αβδούλ Χαμίτ"])
    assert wj.inflecting("Карл Маркс") and wj.inflecting("Ivan Gundulić")
    assert not wj.inflecting("Ayn Rand") and not wj.inflecting("Abdul Hamid II")
    # unchanged: whole words, possessives, no 3-letter run-on even outside ASCII
    assert wj.name_in("Rand's novels", ["Rand"])
    assert not wj.name_in(digest.fold_quote("Марксизмом"), ["Маркс"])


def test_v4_forms_rules(v4):
    pantera = v4[PANTERA]["mc"]["forms"]["Pantera"]
    assert "Down" not in pantera and "Пантера" in pantera
    hilbert = v4[HILBERT]["mc"]["forms"]["David Hilbert"]
    assert "Gilbert" not in hilbert and {"Hilbert", "Гильберт"} <= set(hilbert)
    beyonce = v4[BEYONCE]["mc"]["forms"]["Beyoncé"]
    assert not {"Carter", "Knowles"} & set(beyonce) and "Beyonce Knowles" in beyonce
    madonna = v4[MADONNA]["mc"]["forms"]["Madonna"]
    assert not {"Ritchie", "Domna", "Ciccone"} & set(madonna) and "Madge" in madonna
    hamid = v4[HAMID]["mc"]["forms"]["Abdul Hamid II"]
    assert not {"Abdul Hamid", "Sultan Hamid"} & set(hamid)
    assert {"Abdul Hamid II", "Abdulhamid II", "II. Abdulhamit", "哈米德二世"} <= set(hamid)
    roger = v4[ROGER]["mc"]["forms"]["Roger II of Sicily"]
    assert "Рожер III" not in roger and {"Roger II", "Рожер II", "罗杰二世"} <= set(roger)
    feynman = next(
        it["mc"]["forms"]["Richard Feynman"]
        for it in v4.values()
        if "Richard Feynman" in it["mc"]["forms"]
    )
    # an alias permutation's last word is a given name, not the Q10 form ("Фейнман Річард")
    assert "Річард" not in feynman and {"Feynman", "Фейнман"} <= set(feynman)


def test_builder_rules():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "wbmc", REPO / "scripts/wrong_bridge_mc_options.py"
    )
    assert spec and spec.loader
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    assert w.regnal_number("Roger II of Sicily") == 2 and w.regnal_number("Shaka") is None
    assert w.numbers_in("Abdul Hamid 2-sè") == {2} and w.numbers_in("1.Abdülhamid") == {1}
    assert w.numbers_in("Αμπντούλ Χαμίτ Β΄") == {2} and w.numbers_in("Абдул Хамид ІІ") == {2}
    assert w.numbers_in("ルッジェーロ2世") == {2} and w.numbers_in("马哈茂德二世") == {2}
    assert w.keeps_regnal("Roger II", 2, "Roger II of Sicily")
    assert not w.keeps_regnal("Рожер III", 2, "Roger II of Sicily")
    assert not w.keeps_regnal("Abdul Hamid", 2, "Abdul Hamid II")
    assert w.keeps_regnal("Ozymandias", 2, "Ramesses II")  # another name, not the stem
    assert w.keeps_regnal("Casimir the Great", 3, "Casimir III the Great")


def test_l36_pantera_gold_support_is_the_real_line(v3, v4):
    """L36 Q591875: under v3 the 4-sample "Let's break it down" line was the gold's best
    single-out line (gold_support 4, so FAR_MORE no longer contested it) and the Black Sabbath
    "Down Gettem" line counted as naming Pantera (dropped from the rival audit)."""
    gs = [
        _g(
            'the album *"The Next Episode"* in 2001 and the artist who released the album '
            '*"Hello"* in 2015 is the same person.** Let’s break it down: ### Step 1: '
            "Identify the artist who released",
            4,
        ),
        _g(
            "American band **Pantera**. - Their tenth studio album is titled **Cowboys from "
            "Hell**. **Pantera's tenth studio album** was released in 1994.",
            1,
        ),
        _g(
            'American band **Black Sabbath**. Their 1992 studio album is titled **"Down '
            'Gettem"**. Here’s why that album is significant in the context of heavy metal',
            1,
        ),
    ]
    for bank, best, sabbath_names_gold in ((v3, 4, True), (v4, 1, False)):
        names_gold, single_gold, _ = wj._option_tests(bank[PANTERA])
        assert max(g.count for g in gs if single_gold(g.line)) == best
        assert names_gold(gs[2].line.text) is sabbath_names_gold
    shown = wj.audit_lines(v4[PANTERA], 1, gs)
    assert gs[2] in shown and gs[0] in shown  # both are now rival-audit candidates


def test_l36_beyonce_jay_z_line_is_not_gold_support(v3, v4):
    gs = [
        _g(
            "Houston, Texas, or in Atlanta, Georgia. His full name: Shawn Corey Carter. ⁞ He "
            "began his music career in **1990**. So, the rapper was **born in",
            4,
        ),
        _g(
            "* and its sequel *Let Go Lifted* You’re referring to **Beyoncé’s debut album "
            "*Dangerously in Love***.",
            2,
        ),
    ]
    for bank, best in ((v3, 4), (v4, 2)):
        _names_gold, single_gold, _ = wj._option_tests(bank[BEYONCE])
        assert max(g.count for g in gs if single_gold(g.line)) == best

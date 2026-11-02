"""Round 4d (wbforms-v3, review of PR #208 round 4c nit): ``mc.fold`` strips accents, so an
accent-only form ("Pärt", "Dalí") folded to an English word ("part") or took an inflection tail
as if it were non-English ("Dalit", "Dalian" for Dalí). Such a form now keeps its accents in the
text to take the tail or to count as one bare word; spelled without them it matches only as a
whole multi-word English form. Both directions per case, on the bank-v4 forms."""

from wsbench.evals.wrong_bridge import judge as wj

PART = ["Arvo Pärt", "Arvo Pert", "Pärt", "Пярт"]
DALI = ["Salvador Dalí", "Dalí Salvador"]


def test_bare_english_word_does_not_name_part():
    assert not wj.name_in("This is part of the Beethoven sonata.", PART)
    assert not wj.name_in("a two-part work, in part three", PART)
    # residual, by design: a capitalized bare "Part" (a sentence start) still counts, as a
    # readout writing "Pärt" without its accent must ("Beyonce", "Dali" are not dropped either)
    assert wj.name_in("Part wrote it.", PART)


def test_unaccented_bare_name_counts_capitalized():
    assert wj.name_in("the album by Beyonce", ["Beyoncé"])
    assert not wj.name_in("the album by beyonce", ["Beyoncé"])  # a lowercase bare word


def test_accented_part_and_unaccented_full_name_still_count():
    assert wj.name_in("composed by Pärt in 1977", PART)
    assert wj.name_in("The composer was Arvo Part.", PART)  # 2+ words, accents dropped
    assert wj.name_in("Арво Пярту", ["Пярт"])  # Cyrillic keeps its inflection tail
    assert wj.name_in("Ivana Gundulića", ["Ivan Gundulić"])  # accented: the tail applies
    assert not wj.name_in("Ivana Gundulica", ["Ivan Gundulić"])  # unaccented: whole words


def test_ascii_tail_does_not_name_dali():
    assert not wj.name_in("a Dalit village", ["Dalí"])
    assert not wj.name_in("the port of Dalian", ["Dalí"])
    assert not wj.name_in("born in Dalian", DALI)


def test_accented_tail_and_full_name_still_name_dali():
    assert wj.name_in("los cuadros de Dalís", ["Dalí"])
    assert wj.name_in("painted by Dalí", ["Dalí"])
    assert wj.name_in("painted by Salvador Dali", DALI)  # 2+ words, accents dropped
    assert not wj.name_in("painted by Salvador Dalian", DALI)  # no tail without the accent


def test_spans_line_up_with_the_folded_text():
    from wsbench import mc

    text = "Νταλί; ﬁne: Salvador Dalí y Domènech"
    t = mc.fold(text)
    for s, e in wj.name_spans(text, DALI):
        assert t[s:e] == "salvador dali"


def test_accent_only_classification():
    assert wj.accent_only("Pärt") and wj.accent_only("Salvador Dalí")
    assert not wj.accent_only("Пярт") and not wj.accent_only("Arvo Pert")
    assert not wj.accent_only("Arvo Pært")  # æ does not fold to ASCII

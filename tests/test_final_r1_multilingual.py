"""Final r1 (2026-10-31): multilingual families - raw-sample regex within one layer beside the
digest's pooled conjunction, option pins, no cannot-tell credit, stitched quotes and the
ln-2026-10-31e naming forms."""

from wsbench import digest
from wsbench.digest import Line
from wsbench.multitoken import mcrx, regex
from wsbench.multitoken.family import RAW_REGEX_FAMILIES, raw_layer_hits
from wsbench.multitoken.languages import naming_forms
from wsbench.readouts import Cell

PT = naming_forms("pt", ("en", "zh"))
OTHERS = [{"o": ["Spanish", "español"]}, {"o": ["Italian"]}]
OPTS = ["Portuguese", "Spanish", "Italian", "cannot tell"]


def _named(t, lang):
    return bool(regex.hit_forms([t], naming_forms(lang, ("en", "zh"))))


def test_naming_forms_r1():
    for t, lang in [
        ("formal Indonesian in an academic style", "id"),
        ("Finnish political or news prose", "fi"),
        ("A Korean textbook or Wikipedia-style register", "ko"),
        ("в русском варианте это слово", "ru"),
        ("русский текст звучит так", "ru"),
    ]:
        assert _named(t, lang), t


def test_naming_forms_never_name_these():
    # campaign-lead decision: no arbitrary modifier gaps, closed ru suffixes
    for t, lang in [
        ("Arabic became the official language", "ar"),
        ("Arabic is the official language of the country", "ar"),
        ("the Spanish king signed letters", "es"),
        ("Russian literature and prose", "ru"),
        ("Russian Prose Poetry style", "ru"),
        ("taught in Portuguese in schools", "pt"),
        ("translated from Russian in 1990", "ru"),
        ("русский переводчик", "ru"),
        ("русская текстильная промышленность", "ru"),
        ("the Polish government", "pl"),
    ]:
        assert not _named(t, lang), t


def test_cannot_tell_is_never_credited():
    # review of #201: the deterministic rescue is gone; the judge's question covers it
    lines = [Line("Em português: o número seis"), Line("six")]
    v = mcrx.role_verdict({"choice": "D", "quote": ""}, 0, OPTS, lines, PT, others=OTHERS)
    assert not v["correct"] and v["kind"] == "cannot"


def test_failed_quote_needs_its_own_line():
    lines = [Line("Em português: o número é seis, six"), Line("the six and the five")]
    # a fabricated quote is never rescued by an unrelated line
    v = mcrx.role_verdict(
        {"choice": "A", "quote": "totally invented"}, 0, OPTS, lines, PT, others=OTHERS
    )
    assert not v["correct"]
    # junk parts ('the ... and') never stitch
    v = mcrx.role_verdict(
        {"choice": "A", "quote": "the ... and"}, 0, OPTS, lines, PT, others=OTHERS
    )
    assert not v["correct"]
    # a quote stitched from real parts of ONE line that names the language verifies through it
    q = "Em português: o número ... é seis, six"
    v = mcrx.role_verdict({"choice": "A", "quote": q}, 0, OPTS, lines, PT, others=OTHERS)
    assert v["correct"] and v.get("quote_near")
    # stitched from a line that names no language: no credit, whatever another line says
    q = "the six ... and the five"
    v = mcrx.role_verdict({"choice": "A", "quote": q}, 0, OPTS, lines, PT, others=OTHERS)
    assert not v["correct"]


def test_raw_regex_needs_every_unit_in_one_layer_with_support():
    units = [
        regex.ScoredUnit("concept_native", True, {"en": ["dentist"]}),
        regex.ScoredUnit("language", True, {"fi": ["re:(?i)\\bin Finnish\\b"]}),
    ]
    split = [
        Cell("i", 20, 1, ("written in Finnish, a profession",), None, None, None),
        Cell("i", 44, 1, ("dentist",), None, None, None),
    ]
    by = raw_layer_hits(split, units)
    assert not any(regex.layer_passes(h, units) for h in by.values())  # units at two layers
    one = [
        Cell("i", 20, 1, ("written in Finnish",), None, None, None),
        Cell("i", 20, 2, ("the answer is dentist, in Finnish",), None, None, None),
    ]
    assert regex.layer_passes(raw_layer_hits(one, units)[20], units)
    # an incidental language naming needs two samples of the layer ("written in X" states it)
    lone = [
        Cell("i", 20, 1, ("in Finnish the word sounds odd",), None, None, None),
        Cell("i", 20, 2, ("the answer is dentist",), None, None, None),
    ]
    assert not regex.layer_passes(raw_layer_hits(lone, units)[20], units)
    weak = [
        Cell("i", 20, 1, ("written in Finnish",), None, None, None),
        Cell("i", 20, 2, ("a visit to the dentist was planned",), None, None, None),
    ]
    assert not regex.layer_passes(raw_layer_hits(weak, units)[20], units)  # one mention only
    assert {"multilingual_typo", "multilingual_multihop", "multilingual_mt"} <= RAW_REGEX_FAMILIES


def test_pin_lines_is_capped_and_symmetric():
    cells = [Cell("i", 20, p, (t,), None, None, None) for p, t in enumerate(
        ["in Russian, монарх", "in Russian, монарх", "Spanish: monarca", "noise", "Italian x"]
    )]  # fmt: skip
    col = digest.Collapse()
    col.cells["i"] = Cell("i", digest.SUMMARY_LAYER, 0, ("",), None, None, None)
    col.grounded["i"] = []
    s = digest.settings(digest._probe({}), "multilingual_multihop")
    preds = [lambda ln, w=w: w in ln.text for w in ("Russian", "Spanish", "Italian")]
    assert digest.pin_lines(col, "i", cells, preds, s, 1) == 3
    texts = [ln.text for ln in col.evidence["i"]]
    assert texts[0] == "in Russian, монарх" and "Spanish: monarca" in texts


def test_text_language_statement_needs_a_text_subject():
    from wsbench.multitoken.family import _states_text_language

    u = regex.ScoredUnit("language", True, {"ru": ["re:x"]})
    assert _states_text_language("this passage is written in Russian", u)
    assert _states_text_language("Language: Russian", u)
    for t in (
        "a novel written in Russian",
        "the text was not written in Russian",
        "originally the letter was written in Russian",
        "the question was translated, the text is in Russian",
    ):
        assert not _states_text_language(t, u), t


def test_language_pins_use_every_naming_form():
    # round 3 (BLOCKING multilingual_multihop): the English-only pins missed the lone autonym
    # namings the all-layer digest dropped; a table language is now pinned by its scored naming
    # forms, an option outside the table by its English contexts plus frozen autonym stems
    # (still symmetric: the same rule for every option, never told the gold)
    forms = mcrx._option_naming_forms("Russian", ("en", "zh"))
    assert list(forms) == ["en", "zh", "ru"] and forms["en"]
    assert regex.hit_forms(["на русском языке этот вид бабочек называется"], forms)
    pashto = mcrx._option_naming_forms("Pashto", ("en", "zh"))
    assert list(pashto) == ["en", "own"] and pashto["own"]


def test_chance_labels_describe_both_regex_legs():
    # second review of #201, finding 1: the leg passes on the digest's pooled conjunction OR
    # every unit within one raw layer; both published labels must say so
    from wsbench.multitoken.family import RAW_CHANCE_LABEL

    for label in (RAW_CHANCE_LABEL, mcrx.SUMMARY_CHANCE_LABEL):
        assert "digest" in label and "pooled conjunction" in label and "plan 0020" in label
        assert " OR " in label and "within one read layer" in label
        assert "at least 2 samples" in label and "states it as the answer" in label


def test_domain_words_before_terms_name_the_language():
    # second review of #201, finding 2: a closed list of semantic-field words before terms /
    # vocabulary / nouns / words (real final-olens lines)
    for t, lang in [
        ("In German family terms:", "de"),
        ("On the German kinship vocabulary", "de"),
        ("In German spatial vocabulary", "de"),
        ("German family nouns have grammatical genders", "de"),
        ("In German kinship terms", "de"),
        ("In French family terms", "fr"),
    ]:
        assert _named(t, lang), t
    # never before names, never an arbitrary word
    for t, lang in [
        ("German family names", "de"),
        ("German football terms", "de"),
        ("the German family lived in Berlin", "de"),
    ]:
        assert not _named(t, lang), t


def test_topic_mentions_never_name_the_language():
    # second review of #201, finding 3: a language as a topic (QUESTION_LANGUAGE_V2's exclusion)
    for t, lang in [
        ("the official language is Arabic", "ar"),
        ("The national language is Arabic", "ar"),
        ("Arabic language exam", "ar"),
        ("Arabic language market", "ar"),
        ("the Arabic language course starts", "ar"),
        ("formal Arabic language course", "ar"),
        ("Arabic-language newspaper", "ar"),
        ("Türkçe futbolcuların sayısı artıyor", "tr"),  # noqa: RUF001
        ("Türkçe Futbol Federasyonu", "tr"),
        ("Türkçe spor camiası", "tr"),  # noqa: RUF001
        ("mỗi môn tiếng Việt đều có", "vi"),
        ("tiếng Việt là một trong những ngôn ngữ phổ biến", "vi"),
        ("ban hành đề thi thử môn Tiếng Việt lớp 12", "vi"),
        ("Türkçe edebiyat ve tarih", "tr"),
        ("Türkçe Milli Futbol Takımı", "tr"),  # noqa: RUF001
        ("việc học tiếng Việt là một hành trình", "vi"),
        ("Ngày Tiếng Việt là ngày mấy", "vi"),
    ]:
        assert not _named(t, lang), t
    # the naming lines beside them still name it
    for t, lang in [
        ("the language is Arabic", "ar"),
        ("the Arabic language word for adrenaline", "ar"),
        ("In the Arabic language, it is", "ar"),
        ("Bu kabın Türkçe karşılığı çaydanlık", "tr"),  # noqa: RUF001
        ("Türkçede çaydanlık denir", "tr"),  # noqa: RUF001
        ("Türkçe adı samovar", "tr"),  # noqa: RUF001
        ("Türkçe: çaydanlık", "tr"),  # noqa: RUF001
        ("câu chào năm học mới bằng tiếng Việt", "vi"),
        ("trong tiếng Việt thường nói là", "vi"),
        ("Tiếng Việt: xin chào", "vi"),
        ("Văn bản tiếng Việt gốc có nhiều lỗi", "vi"),
        ("chúng ta đọc đoạn văn tiếng Việt đã cho", "vi"),
        ("kelimesi Türkçe dil bilgisine göre isim", "tr"),
        ("hızlı kelimesinin Türkçe eş anlamlısı", "tr"),  # noqa: RUF001
        ("bu canlının Türkçe yaygın adı Salyangoz", "tr"),  # noqa: RUF001
        ("Tên tiếng Việt của loài côn trùng này", "vi"),
        ("còn tiếng Việt quen gọi là Khăn quàng cổ", "vi"),
        ("**Blender** (tiếng Việt: máy xay sinh tố)", "vi"),
    ]:
        assert _named(t, lang), t


def test_style_heads_check_what_follows():
    # second review of #201, finding 4: nothing after prose / writing / style but what "in X"
    # may be followed by; never "of"; "style" needs a modifier
    for t, lang in [
        ("Russian style", "ru"),
        ("Russian modern style dresses", "ru"),
        ("Russian classical prose writers", "ru"),
        ("Russian in the classical style of architecture", "ru"),
        ("German in the style of Goethe", "de"),
    ]:
        assert not _named(t, lang), t
    for t, lang in [
        ("Slovak poetic style.", "sk"),
        ("Finnish political or news prose", "fi"),
        ("formal Indonesian in an academic style", "id"),
        ("Russian literary prose is used here", "ru"),
    ]:
        assert _named(t, lang), t


def test_pinned_lines_are_never_digest_regex_evidence():
    # third review of #201, finding 1: a pinned raw sample is MC-judge input only; the digest
    # regex leg is scored on the unpinned evidence, so one incidental language line at L20 and
    # one bridge line at L40 never pass the regex leg together
    units = [
        regex.ScoredUnit("bridge_native", True, {"en": ["king", "monarch"]}),
        regex.ScoredUnit("language", True, naming_forms("ru", ("en", "zh"))),
    ]
    cells = [
        Cell("i", 20, 1, ("In Russian the passage asks about a state",), None, None, None),
        Cell("i", 40, 1, ("the king or monarch of the region",), None, None, None),
    ]
    assert not any(regex.layer_passes(h, units) for h in raw_layer_hits(cells, units).values())
    col = digest.Collapse()
    syn = Cell("i", digest.SUMMARY_LAYER, 0, ("",), None, None, None)
    col.cells["i"] = syn
    col.grounded["i"] = []
    s = digest.settings(digest._probe({}), "multilingual_multihop")
    preds = [lambda ln: "Russian" in ln.text, lambda ln: "king" in ln.text]
    assert digest.pin_lines(col, "i", cells, preds, s, 3) == 2
    # the judge still reads the pins (and quote_ok verifies against them)
    assert {ln.text for ln in col.evidence["i"]} == {c.samples[0] for c in cells}
    forms = [f for u in units for f in u.all_forms()]

    def digest_leg(pins: bool) -> bool:
        texts = digest.gate_texts(syn, col, joined=True, forms=forms, pins=pins)
        samples = [x for x in (regex.extract_phrase(t) for t in texts) if x]
        return regex.layer_passes(regex.layer_unit_hits(samples, units), units)

    assert digest_leg(True)  # the hole: pins pooled across layers
    assert not digest_leg(False)  # the leg as scored
    # the digest's own (unpinned) lines still pool across layers (plan 0020)
    col2 = digest.Collapse()
    col2.cells["i"] = syn
    col2.grounded["i"] = []
    col2.evidence["i"] = tuple(Line(c.samples[0], layer=c.layer) for c in cells)
    texts = digest.gate_texts(syn, col2, joined=True, forms=forms, pins=False)
    assert regex.layer_passes(regex.layer_unit_hits(texts, units), units)


def test_raw_answer_statement_is_a_prose_sample_never_a_token():
    # third review of #201, finding 2: a flat top-k list singles out nothing, whatever the rank
    # (Q4), and a prose sample merely opening with the form is no answer
    units = [
        regex.ScoredUnit("concept_native", True, {"en": ["dentist"]}),
        regex.ScoredUnit("language", True, naming_forms("de", ("en", "zh"))),
    ]
    top = ("Deutsch", "a", "b", "c", "d", "e", "f", "g", "h")
    toks = [
        Cell("i", 30, 1, None, (*top, "dentist"), None, None),
        Cell("i", 30, 2, None, (*top, "x"), None, None),
    ]
    assert not regex.layer_passes(raw_layer_hits(toks, units)[30], units)
    # the same token twice in the layer is support (>= 2 samples)
    toks2 = [
        Cell("i", 30, 1, None, (*top, "dentist"), None, None),
        Cell("i", 30, 2, None, (*top, "dentist"), None, None),
    ]
    assert regex.layer_passes(raw_layer_hits(toks2, units)[30], units)
    fi = [
        regex.ScoredUnit("concept_native", True, {"en": ["dentist"]}),
        regex.ScoredUnit("language", True, {"fi": ["re:(?i)\\bin Finnish\\b"]}),
    ]
    opens = [
        Cell("i", 20, 1, ("Dentist offices are mentioned once as a place",), None, None, None),
        Cell("i", 20, 2, ("This passage is written in Finnish",), None, None, None),
    ]
    assert not regex.layer_passes(raw_layer_hits(opens, fi)[20], fi)
    # a whole prose sample, or a form after an answer cue, still states the answer
    for t in ("Dentist.", "The answer is dentist"):
        whole = [
            Cell("i", 20, 1, (t,), None, None, None),
            Cell("i", 20, 2, ("This passage is written in Finnish",), None, None, None),
        ]
        assert regex.layer_passes(raw_layer_hits(whole, fi)[20], fi), t


def test_language_question_has_no_single_line_credit():
    # third review of #201, finding 3: the judge prompt never credits one naming line on its
    # own (it would see only option languages in the digest, never a raw-sample rival)
    from wsbench.multitoken.prompts import ML_MC_PROMPT_VERSION, QUESTION_LANGUAGE_V2

    assert "is enough" not in QUESTION_LANGUAGE_V2
    assert "no other option" not in QUESTION_LANGUAGE_V2
    assert "TOPIC does not count" in QUESTION_LANGUAGE_V2  # the topic exclusion is kept
    assert ML_MC_PROMPT_VERSION == "mc-ml-2026-11-01b"  # round 4b: no summ_lang label sentence

# ruff: noqa: RUF001
"""Round 3 (multilingual_multihop BLOCKING + multilingual): every-naming-form pins, the language
cannot-tell rescue, and the Arabic teaching-topic veto. Each rule is pinned in both directions:
the too-strict shape of a cited case now passes and the too-lenient shape still fails."""

from wsbench.banks import load_bank, native_langs
from wsbench.digest import Line
from wsbench.multitoken import mcrx, regex
from wsbench.multitoken.languages import LANGUAGES, naming_forms
from wsbench.multitoken.options import LANGUAGE_ROLE, option_aliases, option_sets
from wsbench.readouts import Cell

FAM = "multilingual_multihop"


def _ctx(iid: str, cells: list[Cell]) -> mcrx._Ctx:
    header, items = load_bank(f"evals/{FAM}/items_v2.json")
    contract = regex.contract_for(header, str(header["family"]))
    it = next(i for i in items if i["id"] == iid)
    positions: dict = {}
    for c in cells:
        positions.setdefault((c.id, c.layer), []).append(c)
    return mcrx._Ctx(
        FAM, None, [it], [iid], {iid: it}, {iid: regex.scored_units(it, contract)},
        option_sets(items), native_langs(header), cells, None, positions,
        sorted({c.layer for c in cells}), [], option_aliases(items),
    )  # fmt: skip


def _cells(iid: str, samples: list[str], layer: int = 60) -> list[Cell]:
    return [Cell(iid, layer, -1 - k, (s,), None, None) for k, s in enumerate(samples)]


ARECIBO = "mlmh-ko-arecibo-puertorico"
KO_LINE = "경(Radio Telescope)입니다. 한국어 직역으로는 '라디오 망원경'쯤 되겠네요."
JACQUARD = "mlmh-el-jacquard-lyon"
EL_LINE = (
    "ού του Jacquard (weaving loom) 2. Τον χάρτη του αργαλειού Στην ελληνική γλώσσα η λέξη "
    "«αργαλειός» σημαίνει"
)
CANNOT = {"judged": True, "kind": "cannot", "correct": False, "pick": "F"}


def test_rescue_credits_a_lone_uncontested_naming_about_the_bridge():
    # el-jacquard all-layer: the Greek naming sits in a sentence about Jacquard's loom; once
    # pinned, the judge still said cannot tell
    cells = _cells(JACQUARD, [EL_LINE, "Ο Ζακάρ εφηύρε τον αργαλειό.", "Jacquard loom."])
    ctx = _ctx(JACQUARD, cells)
    v = mcrx.language_rescue(ctx, JACQUARD, dict(CANNOT), [Line(EL_LINE)], cells)
    assert v["kind"] == "correct" and v["correct"] and v["form_via"] == "rescue"
    assert v["rescue_gold_raw"] == 1 and v["rescue_rival_raw"] == 0


def test_rescue_refuses_when_another_language_is_named_as_often():
    tr = "Jacquard tezgahı Türkçede dokuma tezgahı olarak bilinir."
    cells = _cells(JACQUARD, [EL_LINE, tr, "Jacquard: Türkçe karşılığı dokuma tezgahı."])
    ctx = _ctx(JACQUARD, cells)
    v = mcrx.language_rescue(ctx, JACQUARD, dict(CANNOT), [Line(EL_LINE)], cells)
    assert v["kind"] == "cannot" and not v["correct"]
    assert v["rescue_rival_raw"] >= v["rescue_gold_raw"]


def test_multihop_rescue_needs_the_naming_to_be_about_the_bridge():
    # ko-arecibo: the Korean naming glosses 'radio telescope', not the observatory: no rescue
    # (L60 still passes through the judge's own credit)
    cells = _cells(ARECIBO, [KO_LINE, "아레시보 천문대는 푸에르토리코에 있습니다."])
    ctx = _ctx(ARECIBO, cells)
    v = mcrx.language_rescue(ctx, ARECIBO, dict(CANNOT), [Line(KO_LINE)], cells)
    assert v["kind"] == "cannot"


def test_rescue_never_acts_on_a_topic_line():
    # ar-ashgabat L44-shaped: an official-language statement is a topic, never a rescue
    iid = "mlmh-ar-ashgabat-manat"
    ar = (
        "عشق آباد (Ashgabat) هو العربية (Arabic)، وهي اللغة الرسمية الوحيدة المعتمدة في الدولة، "
        "واسمها بالعربية عشق آباد"
    )
    cells = _cells(iid, [ar, ar + " ."])
    ctx = _ctx(iid, cells)
    v = mcrx.language_rescue(ctx, iid, dict(CANNOT), [Line(ar)], cells)
    assert v["kind"] == "cannot"


def test_rescue_needs_a_digest_line_that_singles_out_the_gold():
    # the naming is only in a raw sample the digest does not hold: no rescue
    cells = _cells(JACQUARD, [EL_LINE])
    ctx = _ctx(JACQUARD, cells)
    v = mcrx.language_rescue(ctx, JACQUARD, dict(CANNOT), [Line("Jacquard loom.")], cells)
    assert v["kind"] == "cannot"


def test_rescue_never_touches_a_distractor_pick():
    cells = _cells(JACQUARD, [EL_LINE])
    ctx = _ctx(JACQUARD, cells)
    pick = {"judged": True, "kind": "distractor", "correct": False, "pick": "E"}
    assert mcrx.language_rescue(ctx, JACQUARD, dict(pick), [Line(EL_LINE)], cells) == pick


def test_rescue_families():
    assert frozenset({"multilingual", FAM}) == mcrx.RESCUE_FAMILIES


# ------------------------------------------------------------------ the pins


def test_every_multihop_language_option_has_pin_forms():
    _h, items = load_bank(f"evals/{FAM}/items_v2.json")
    in_table = {n for lg in LANGUAGES.values() for n in lg.names["en"]}
    for it in items:
        for o in option_sets(items)[it["id"]][LANGUAGE_ROLE][0][:-1]:
            assert o in in_table or mcrx.PIN_AUTONYMS.get(o), o


def test_pins_now_catch_autonym_namings_the_english_pins_missed():
    tr = 'bir karaciğer hastaligidir. Türkçede "Wilson Hastaligi" olarak bilinir.'
    el = "Στην ελληνική γλώσσα η λέξη «αργαλειός» σημαίνει"
    for option, text in (("Turkish", tr), ("Greek", el)):
        forms = mcrx._option_naming_forms(option, ("en", "zh"))
        en_only = {"en": forms["en"]}
        assert not regex.hit_forms([text], en_only), option  # what the pins-v1 forms saw
        assert regex.hit_forms([text], forms), option


def test_pins_stay_symmetric_for_options_outside_the_table():
    # an outside-table distractor's autonym line is pinned too (never less readily than a gold)
    forms = mcrx._option_naming_forms("Azerbaijani", ("en", "zh"))
    assert regex.hit_forms(["Azərbaycan dilində bu söz belə deyilir"], forms)
    assert not regex.hit_forms(["A plain sentence with no language."], forms)


# ------------------------------------------------------------------ the Arabic topic veto


def _ar(text: str) -> bool:
    return bool(regex.hit_forms([text], naming_forms("ar", ["en", "zh"])))


def test_arabic_teaching_topic_sentence_no_longer_names_the_language():
    # ar-suryavarman L60's credited quote
    assert not _ar(
        "البنيوي المستدام (Sustainable Construction) في اللغة العربية يشير البناء البنيوي إلى "
        "عملية بناء المعرفة اللغوية لدى المتعلم"
    )
    assert not _ar("في اللغة العربية هو عملية ضرورية لكل معلم ومجتمعات التعليم")


def test_arabic_namings_of_words_still_count():
    assert _ar('هذا البلد يُعرف باللغة العربية باسم "أستراليا"، وهو')
    assert _ar("الاسم بالعربية حسب الجمعيات الرسمية: عشقهر")
    # a teaching word BEFORE the naming, in its own sentence, does not veto the next one
    assert _ar('كلمة "تعلم" مشهورة. هذه الكلمة باللغة العربية تعني learning.')


def test_language_pins_skip_topic_lines():
    # mlmh-ar-thimphu all-layer: a pinned Arabic grammar-topic line was credited by the judge
    from wsbench import digest

    iid = "mlmh-ar-thimphu-buddhism"
    topic = (
        "(Dinamic) في اللغة العربية الديناميكية هي واحدة من أهم مواضيع الأسئلة الشائعة حول النحو"
    )
    naming = 'تيمفو (Thimphu) يُعرف باللغة العربية باسم "تيمفو".'
    cells = _cells(iid, [topic, naming])
    ctx = _ctx(iid, cells)
    col = digest.Collapse()
    col.cells[iid] = cells[0]
    col.grounded[iid] = []
    pinned: list[str] = []

    def fake_pin(col, item_id, cs, preds, s, per):
        pinned.extend(ln.text for ln in digest.native_lines(cs) if any(p(ln) for p in preds))
        return 0

    import wsbench.multitoken.mcrx as m

    orig, settings = m.digest.pin_lines, m.digest.settings
    m.digest.pin_lines, m.digest.settings = fake_pin, lambda *a, **k: None
    try:
        mcrx._pin_options(ctx, col)
    finally:
        m.digest.pin_lines, m.digest.settings = orig, settings
    assert naming in pinned and topic not in pinned


def test_multihop_raw_leg_takes_one_anchored_naming():
    # ru-monarch-michoacan L40: one sample names Russian beside the bridge; the other units
    # have their usual support
    from wsbench.multitoken import family as fam

    iid = "mlmh-ru-monarch-michoacan"
    header, items = load_bank(f"evals/{FAM}/items_v2.json")
    it = next(i for i in items if i["id"] == iid)
    units = regex.scored_units(it, regex.contract_for(header, str(header["family"])))
    bridge = {u.role: u.all_forms()[0] for u in units if u.role != LANGUAGE_ROLE}
    named = (
        f"Это {bridge['bridge_native']}. На русском языке этот вид называется "
        f"{bridge['bridge_l2']}."
    )
    filler = [f"{bridge['bridge_native']} и {bridge['bridge_l2']}."] * 2
    cells = _cells(iid, [named, *filler], layer=40)
    anchors = fam.anchor_forms(it)
    old = fam.raw_layer_hits(cells, units)
    new = fam.raw_layer_hits(cells, units, None, anchors, require_anchor=False)
    assert not regex.layer_passes(old[40], units)
    assert regex.layer_passes(new[40], units)
    # an unanchored lone naming still needs the old two samples
    lone = _cells(iid, ["На русском языке слово дом значит house.", *filler], layer=40)
    assert not regex.layer_passes(
        fam.raw_layer_hits(lone, units, None, anchors, require_anchor=False)[40], units
    )

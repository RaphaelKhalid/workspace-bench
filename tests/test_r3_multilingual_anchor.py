"""Round 3 (multilingual_mt, ``family.ANCHOR_FAMILIES``): the language unit counts only in a sample
that is about the item's object or the passage; one such sample supports it, and a sample
holding every required unit supports each of them. Both directions are pinned on the shapes of
the reaudit's cited cases. Also the ln-2026-10-31f input-naming form (multilingual prompt-only)."""

from wsbench.banks import load_bank
from wsbench.multitoken import family as fam
from wsbench.multitoken import languages, regex
from wsbench.readouts import Cell

BANK = "evals/multilingual_mt/items_v2.json"


def _item(iid: str):
    header, items = load_bank(BANK)
    contract = regex.contract_for(header, str(header["family"]))
    it = next(i for i in items if i["id"] == iid)
    return it, regex.scored_units(it, contract), contract, fam.anchor_forms(it)


def _cells(iid: str, layer: int, samples: list[str]) -> list[Cell]:
    return [Cell(iid, layer, -1 - k, (s,), None, None) for k, s in enumerate(samples)]


def _passes(hits: dict[int, dict[str, list[str]]], units) -> bool:
    return any(regex.layer_passes(h, units) for h in hits.values())


# ------------------------------------------------------------------ too lenient: now fails


def test_kasztanowiec_unrelated_polish_naming_no_longer_counts():
    # pl-kasztanowiec L36: the Polish namings gloss a city phrase; the tree is elsewhere (two
    # such samples, so the old two-sample rule passed the layer)
    it, units, contract, anchors = _item("mlh-pl-kasztanowiec")
    samples = [
        "miasto kleje (Great Big City in Polish) lub Duże miasto powiązania to pozostałość.",
        "Duże miasto (Great Big City in Polish) to pozostałość po ENGINE.",
        "To jest Horse Chestnut Tree, duże drzewo.",
        "The horse chestnut tree has candle-shaped flowers.",
        "Again the horse chestnut, with conkers.",
    ]
    cells = _cells(it["id"], 36, samples)
    assert _passes(fam.raw_layer_hits(cells, units, contract), units)  # the old rule passed
    assert not _passes(fam.raw_layer_hits(cells, units, contract, anchors), units)


def test_digest_leg_unrelated_naming_no_longer_counts():
    # the pooled digest leg (the cited cells' "regex pass (digest pooled)")
    _it, units, contract, anchors = _item("mlh-pl-trzustka")
    ev = [
        "**Gruczań** - słowo w języku polskim/cerkiewnym, które może być używane jako nazwa wsi.",
        "The organ is the pancreas, which secretes insulin.",
    ]
    assert regex.layer_passes(regex.layer_unit_hits(ev, units, contract), units)
    assert not regex.layer_passes(fam.anchored_unit_hits(ev, units, contract, anchors), units)


# ------------------------------------------------------------------ too strict: now passes


def test_one_sample_holding_both_units_passes():
    # id-penghapus L60: one sample states the concept and names Indonesian
    it, units, contract, anchors = _item("mlh-id-penghapus")
    samples = [
        "Ini adalah **eraser**. Dalam bahasa Indonesia, alat ini lebih populer disebut "
        "**penghapus**.",
        "Alat tulis untuk menulis di kertas.",
    ]
    cells = _cells(it["id"], 60, samples)
    assert not _passes(fam.raw_layer_hits(cells, units, contract), units)  # the old rule failed
    assert _passes(fam.raw_layer_hits(cells, units, contract, anchors), units)


def test_one_naming_about_the_answer_word_passes():
    # vi-clothesiron L60: the naming sample holds the Vietnamese answer word (a target alt); the
    # concept is stated in other samples
    it, units, contract, anchors = _item("mlh-vi-clothesiron")
    samples = [
        "Dụng cụ đó là **bàn là** (trong tiếng Việt thường gọi là *bàn là*).",
        "You use an iron to press clothes.",
        "The iron removes wrinkles.",
    ]
    cells = _cells(it["id"], 60, samples)
    assert not _passes(fam.raw_layer_hits(cells, units, contract), units)
    assert _passes(fam.raw_layer_hits(cells, units, contract, anchors), units)


def test_naming_the_passage_itself_needs_no_object():
    it, units, contract, anchors = _item("mlh-pl-kasztanowiec")
    samples = [
        "This passage is written in Polish and describes a tree.",
        "It is the horse chestnut.",
        "The horse chestnut again.",
    ]
    cells = _cells(it["id"], 44, samples)
    assert _passes(fam.raw_layer_hits(cells, units, contract, anchors), units)


def test_one_unanchored_naming_still_needs_the_old_support():
    # anchoring never lowers the bar for an unrelated naming: two unrelated namings still fail
    it, units, contract, anchors = _item("mlh-pl-kasztanowiec")
    samples = [
        "miasto (city in Polish) is a word.",
        "In Polish, the word dom means house.",
        "The horse chestnut tree.",
        "A horse chestnut.",
    ]
    cells = _cells(it["id"], 40, samples)
    assert not _passes(fam.raw_layer_hits(cells, units, contract, anchors), units)


def test_token_readouts_keep_the_old_rule():
    it, units, contract, anchors = _item("mlh-pl-kasztanowiec")
    cells = [
        Cell(it["id"], 44, -1, None, ("波兰语", "horse chestnut"), (0.5, 0.4)),
        Cell(it["id"], 44, -2, None, ("波兰语", "horse chestnut"), (0.5, 0.4)),
    ]
    old = fam.raw_layer_hits(cells, units, contract)
    assert fam.raw_layer_hits(cells, units, contract, anchors) == old


def test_anchoring_moved_to_same_sample_and_typo_support():
    # round 4 (Camila r2): multilingual_mt moved on to the same-sample rule
    # (fam.SAME_SAMPLE_FAMILIES) and multilingual_typo joined the anchored support
    # (fam.ANCHOR_SUPPORT_FAMILIES, ANSWERS_R2 §8); tests/test_r4_bridge_ml.py pins both
    assert frozenset() == fam.ANCHOR_FAMILIES
    assert frozenset({"multilingual_mt"}) == fam.SAME_SAMPLE_FAMILIES
    _h, items = load_bank("evals/multilingual_typo/items_v2.json")
    assert fam._anchors_of("multilingual_typo", items)


# ------------------------------------------------------------------ ln-2026-10-31f input naming


def _names(lang: str, text: str) -> bool:
    return bool(regex.hit_forms([text], languages.naming_forms(lang, ["en", "zh"])))


def test_input_naming_forms_accept_the_voided_prompt_only_namings():
    for lang, text in [
        ("es", "a simple Spanish arithmetic question"),
        ("es", "This is a Spanish fill-in prompt."),
        ("fr", "It asks for the French antonym of premier."),
        ("cs", "a Czech antonym question"),
        ("fr", "a French kinship riddle"),
        ("es", "a Spanish counting sequence"),
        ("es", "a Spanish day-of-week riddle"),
        ("hu", "This prompt is a Hungarian descriptive definition, worded like a riddle"),
    ]:
        assert _names(lang, text), text


def test_input_naming_forms_still_reject_other_mentions():
    for lang, text in [
        ("ru", "the Russian writer wrote this sentence"),
        ("es", "Spanish King Juan wrote a question"),
        ("es", "the Spanish national team question"),
        ("es", "Spanish history and the prompt"),
        ("de", "deutsche Kunst und Kultur"),
        ("de", "German art is famous"),
        ("ru", "Russian Literature Question Bank"),  # a title: capitalised words
        ("pl", "the Polish government passed a law"),
    ]:
        assert not _names(lang, text), text

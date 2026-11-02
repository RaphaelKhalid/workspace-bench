# ruff: noqa: RUF001
"""Review of PR #208 (round 4d), both directions for each fix.

1. wrong_bridge (wbaudit-v2): the rival audit also checks lines that name the gold and hold
   another name; one it marks as giving a different person in the role (a name the line holds)
   is a split line, cut from the gold's support and weighed as that rival's. L52
   composition_composer-Q182537 (gold John Lennon) passed 4 vs 0 while ~16 samples of Lennon
   lines said "The composer of the song tax was Paul McCartney". Digest lines verbatim from
   the cached final-olens-rl600-x4 L52 digest.
2. basic_readout_mt / multihop_mt_v2 (optrv-v4, optaudit-v1): a code option-rival line the
   option audit dismisses is not weighed. bonaire-capital (all) was contested 69 vs 72 by a
   true line about Aruba; L20 palau-capital 5 vs 10 by a former-capital line. A line the audit
   keeps, or a failed audit, still contests.
3. wrong_bridge ``name_in`` precompiles its patterns (was ~33 ms per call)."""

import time

import pytest

from wsbench import digest
from wsbench.banks import load_bank
from wsbench.evals.wrong_bridge import judge as wb
from wsbench.evals.wrong_bridge import prompts as wp
from wsbench.multitoken import family as fam
from wsbench.multitoken import prompts as mp
from wsbench.multitoken.options import option_sets


def _g(text: str, count: int) -> digest.Grounded:
    ln = digest.Line(text)
    return digest.Grounded("", digest.support_text(count), text, ln, text, "items", "", count)


# ------------------------------------------------------------------ 1. wrong_bridge split lines
TAXMAN = "composition_composer-Q182537-birth_year"
L52 = [
    (
        '" is John Lennon of The Beatles. The songwriter of "Taxman" is Paul McCartney of The '
        'Beatles. "Taxman" was written by John Lennon',
        4,
    ),
    (
        "John Lennon. The composer of the song tax was Paul McCartney. The musician in the band "
        'the Beatles who wrote Tax was John Lennon. We know that "Tax" is a song by the Beatles.',
        7,
    ),
    (
        "Liverpool, England. The alternative birthplace of John Lennon is Wallet Street, "
        "Liverpool. The Beatles formed in Liverpool, England. John Lennon was born in Liverpool, "
        "England. John Lennon was born in Liverpool",
        4,
    ),
    (
        "John Lennon. The person who composed Taxman was Paul McCartney. The band The Beatles was "
        "formed in Liverpool. Who was John Lennon? John Lennon was a guitarist. The person who "
        "wrote Tax",
        3,
    ),
    (
        'ation IV* or *Taxation XV* (opera/comedy scores) by Béla Bartók. "Taxation" is his '
        "famous symphonic work. - **Taxation IV’s Novelty Orchestra** also features a theme "
        "called *Taxation*.",
        2,
    ),
    (
        "1944. Elvis Presley was born in the year 1935. James Dean was born in the year 1931. "
        "What is the missing year",
        6,
    ),
    (
        "* is John Lennon of The Beatles. The writer of *Taxman* is Paul McCartney of The "
        "Beatles. Both songs are from the Beatles' 1966 album *Revolver*.",
        1,
    ),
]
QUOTE = "The musician in the band the Beatles who wrote Tax was John Lennon."
RIVAL_Q = "The composer of the song tax was Paul McCartney."


@pytest.fixture(scope="module")
def taxman():
    return next(it for it in wb.load_items() if it["id"] == TAXMAN)


def _wb(it, gs, audit=None, rq=RIVAL_Q, quote=QUOTE):
    res = {"choice": wb.positions(it)[0], "quote": quote, "rival_quote": rq}
    return res, wb.decide(res, it, [g.line for g in gs], gs, audit)


def _mark(shown, names):
    """An audit answer marking each shown line whose text holds a key of ``names``."""
    out = []
    for n, g in enumerate(shown, 1):
        hit = next((v for k, v in names.items() if k in g.line.text), None)
        out.append({"line": n, "rival": hit is not None, "name": hit or ""})
    return {"verdicts": out}


def test_taxman_without_the_split_audit_passes(taxman):
    """The reviewed state: every McCartney line also names Lennon, so it was weighed nowhere."""
    gs = [_g(t, c) for t, c in L52]
    _res, v = _wb(taxman, gs, {"verdicts": []})
    assert v["pick"] == "gold" and v["gold_support"] == 4 and v["rival_entities"] == {}


def test_taxman_audit_sees_the_lennon_mccartney_lines(taxman):
    gs = [_g(t, c) for t, c in L52]
    res = {"choice": wb.positions(taxman)[0], "quote": QUOTE, "rival_quote": RIVAL_Q}
    shown = wb.audit_shown(taxman, wb.pre_gold_support(taxman, res, gs), gs)
    texts = [g.line.text for g in shown]
    # the non-gold lines keep their wbaudit-v1 numbers; the split candidates follow
    assert texts[: len(wb.audit_lines(taxman, 4, gs))] == [
        g.line.text for g in wb.audit_lines(taxman, 4, gs)
    ]
    for t, _c in L52[:4]:
        assert t in texts  # every prominent Lennon line holding another name


def test_taxman_split_lines_contest_the_pick(taxman):
    gs = [_g(t, c) for t, c in L52]
    res = {"choice": wb.positions(taxman)[0], "quote": QUOTE, "rival_quote": RIVAL_Q}
    shown = wb.audit_shown(taxman, wb.pre_gold_support(taxman, res, gs), gs)
    audit = _mark(shown, {"Paul McCartney": "Paul McCartney"})
    _res, v = _wb(taxman, gs, audit)
    assert v["pick"] == "contested" and not v["credited"]
    assert v["gold_support"] == 4  # the Liverpool line, the only Lennon line without McCartney
    assert v["rival_entities"]["~paul mccartney"] == 7
    assert v["split_support"] == 7


def test_a_mentioned_bandmate_is_no_split(taxman):
    """The other direction: the audit keeps a line that gives only Lennon in the role and
    mentions McCartney otherwise; and a rival name the line does not hold never cuts it."""
    line = "John Lennon wrote Taxman; Paul McCartney played bass on the recording."
    gs = [_g(line, 6), _g(L52[5][0], 1)]
    res = {"choice": wb.positions(taxman)[0], "quote": "John Lennon wrote Taxman"}
    shown = wb.audit_shown(taxman, wb.pre_gold_support(taxman, res, gs), gs)
    assert [g.line.text for g in shown] == [line]
    no = {"verdicts": [{"line": 1, "rival": False, "name": ""}]}
    _r, v = _wb(taxman, gs, no, rq="", quote="John Lennon wrote Taxman")
    assert v["pick"] == "gold" and v["gold_support"] == 6
    wrong = {"verdicts": [{"line": 1, "rival": True, "name": "George Martin"}]}
    _r, v = _wb(taxman, gs, wrong, rq="", quote="John Lennon wrote Taxman")
    assert v["pick"] == "gold" and v["gold_support"] == 6 and v["rival_entities"] == {}


def test_a_gold_only_line_starts_no_audit(taxman):
    gs = [_g("John Lennon wrote Taxman.", 5)]
    assert wb.audit_shown(taxman, 5, gs) == []
    # a CJK gold line joins an audit but never starts one (no segmentation)
    assert wb.audit_shown(taxman, 5, [_g("约翰·列侬写了《Taxman》", 5)]) == []


def test_audit_numbering_is_the_runs():
    """rival_entities reads the same numbered list the run showed (the -11-01h list used a
    gold bar that still counted split lines, so verdicts could land on other lines)."""
    it = next(i for i in wb.load_items() if i["id"] == TAXMAN)
    gs = [_g(t, c) for t, c in L52]
    res = {"choice": wb.positions(it)[0], "quote": QUOTE, "rival_quote": RIVAL_Q}
    shown = wb.audit_shown(it, wb.pre_gold_support(it, res, gs), gs)
    audit = _mark(shown, {"Bartók": "Béla Bartók"})
    a = wb.rival_entities(it, res, gs, audit)
    b = wb.rival_entities(it, res, gs, audit, shown)
    assert a == b and a["~bela bartok"].count == 2


def test_audit_prompt_and_stamp():
    assert "also names the chosen candidate" in wp.AUDIT_SYSTEM
    assert wp.AUDIT_VERSION == "wbaudit-v2" and "+wbaudit-v2+" in wp.PROMPT_VERSION
    assert "wbaudit" not in wb._mc_version(wp.PROMPT_VERSION)  # MC calls stay cached


# ------------------------------------------------------------------ 2. option audit (brmt)
BONAIRE = "brh-ent-bonaire-capital"
PALAU = "brh-ent-palau-capital"
ARUBA = (
    "The capital and principal city of Aruba is **Oranjestad**. While Aruba is an autonomous "
    'country within the Kingdom of the Netherlands and does not have a traditional "capital" '
    "designation in all its administrative contexts, Oranjestad serves as its governmental"
)
KRALENDIJK = (
    "onaire, which is part of the Kingdom of the Netherlands:** The capital of the "
    "municipality of Bonaire is **Kralendijk**. ### Important Context: - **B"
)
BONAIRE_ORANJESTAD = "The capital and largest city of Bonaire is **Oranjestad**."
NGERULMUD = "au’s** government? The capital city of **Palau** is **Ngerulmud**. ### Key Facts"
KOROR_FORMER = (
    "16** or **2019**, depending on how you count the permanent relocation of its government. "
    "Prior to 2016, Palau’s capital was Koror. Since the government moved to the Ng"
)
KOROR_NOW = (
    "1946 and has remained the primary seat of government ever since. It serves as the "
    "official capital of the Republic of Palau. Here’s why Koror is the seat of government "
    "since 1946: ### Historical Context - **Pre-"
)


@pytest.fixture(scope="module")
def brmt():
    _h, items = load_bank("evals/basic_readout_mt/items_v4.json")
    sets = option_sets(items, cannot="cannot tell")
    by = {i["id"]: i for i in items}
    return by, sets, fam.bank_entities(items)


def _brmt(brmt, iid, gs, res, audit=None):
    by, sets, ents = brmt
    options, gold = sets[iid]["readout"]
    hidden = fam.hidden_rivals("basic_readout_mt", iid, "readout")
    v = {"kind": "correct", "correct": True}
    args = (res, gs, gold, options, by[iid], "readout", ents, hidden)
    shown = fam.option_audit_lines(*args)
    out = fam.contested_verdict(dict(v), *args[:7], hidden=hidden, audit=audit)
    return shown, out


def _bonaire():
    return [_g(ARUBA, 72), _g(KRALENDIJK, 69), _g(BONAIRE_ORANJESTAD, 1)]


BON_RES = {
    "choice": "x",
    "quote": "The capital of the municipality of Bonaire is **Kralendijk**.",
    "rival_quote": "The capital and largest city of Bonaire is **Oranjestad**.",
}


def test_bonaire_aruba_line_contests_without_the_audit(brmt):
    shown, v = _brmt(brmt, BONAIRE, _bonaire(), BON_RES)
    assert [g.count for g in shown] == [72]
    assert v["kind"] == "contested" and v["option_rival_support"] == 72


def test_bonaire_dismissed_aruba_line_is_not_weighed(brmt):
    no = {"verdicts": [{"line": 1, "rival": False}]}
    _shown, v = _brmt(brmt, BONAIRE, _bonaire(), BON_RES, no)
    assert v["kind"] == "correct" and v["option_rival_support"] == 1
    assert v["option_audit_dismissed"] == 1


def test_a_kept_or_unanswered_line_still_contests(brmt):
    for audit in (
        {"verdicts": [{"line": 1, "rival": True}]},
        {"verdicts": []},  # no verdict for the line: weighed
        {"verdicts": [{"line": 2, "rival": False}]},  # out of range: ignored
    ):
        _shown, v = _brmt(brmt, BONAIRE, _bonaire(), BON_RES, audit)
        assert v["kind"] == "contested" and v["option_rival_support"] == 72


def test_palau_former_capital_dismissed_keeps_the_current_rival(brmt):
    gs = [_g(NGERULMUD, 5), _g(KOROR_FORMER, 10), _g(KOROR_NOW, 4)]
    res = {"choice": "x", "quote": "The capital city of **Palau** is **Ngerulmud**."}
    shown, v = _brmt(brmt, PALAU, gs, res)
    assert [g.count for g in shown] == [10]  # 4 < 5 cannot contest, so it is not sent
    assert v["kind"] == "contested" and v["option_rival_support"] == 10
    no = {"verdicts": [{"line": 1, "rival": False}]}
    _shown, v = _brmt(brmt, PALAU, gs, res, no)
    assert v["kind"] == "correct" and v["option_rival_support"] == 4
    # a current-capital line as strong as the gold is still a contest
    gs = [_g(NGERULMUD, 5), _g(KOROR_FORMER, 10), _g(KOROR_NOW, 5)]
    shown, _v = _brmt(brmt, PALAU, gs, res)
    keep_now = {
        "verdicts": [{"line": n, "rival": g.line.text == KOROR_NOW} for n, g in enumerate(shown, 1)]
    }
    _shown, v = _brmt(brmt, PALAU, gs, res, keep_now)
    assert v["kind"] == "contested" and v["option_rival_support"] == 5


def test_option_audit_call_is_blind():
    shown = [_g(ARUBA, 72)]
    c = fam.option_audit_call("k", BON_RES, ["Kralendijk", "Willemstad"], 0, shown, {})
    assert c.key == "k|optrivals" and c.system == mp.OPTION_AUDIT_SYSTEM
    assert "1. [72 samples] The capital and principal city of Aruba" in c.user
    assert "Kralendijk" in c.user and "Bonaire?" not in c.system
    by = {i["id"]: i for i in load_bank("evals/basic_readout_mt/items_v4.json")[1]}
    assert by[BONAIRE]["prompt"] not in c.user


def test_option_audit_stamps():
    assert "+optrv-v4+" in mp.BRMT_PROMPT_VERSION
    assert "+optrv-v1+" in fam.call_pv(mp.BRMT_PROMPT_VERSION)  # MC calls stay cached
    assert mp.OPTION_AUDIT_VERSION == "optaudit-v1"


# ------------------------------------------------------------------ 3. name_in speed
def test_name_in_is_precompiled():
    it = max(wb.load_items(), key=lambda i: max(len(v) for v in i["mc"]["forms"].values()))
    forms = [it["mc"]["forms"][o] for o in it["mc"]["order"]]
    text = "The composer of the song was Paul McCartney, while John Lennon wrote others."
    for f in forms:
        wb.name_in(text, f)  # warm the caches
    t = time.perf_counter()
    for _ in range(100):
        for f in forms:
            wb.name_in(text, f)
    per_call = (time.perf_counter() - t) / (100 * len(forms))
    assert per_call < 0.005  # was ~0.033-0.05 s with the re cache overflowing


# ------------------------------------------------------------------ 4. ASCII twins (wbforms-v4)
DALI_ITEM = "painting_creator-Q2272625-death_year"


@pytest.fixture(scope="module")
def dali_forms():
    it = next(i for i in wb.load_items() if i["id"] == DALI_ITEM)
    return it["mc"]["forms"]["Salvador Dalí"]


def test_lowercase_ascii_twin_no_longer_names_dali(dali_forms):
    assert "Dali" in dali_forms  # the bank's own plain-ASCII twin of the label's "Dalí"
    for text in ("by dali", "a dali-like scene", "the dali painting"):
        assert not wb.name_in(text, dali_forms), text
        assert not wb.name_spans(text, dali_forms), text


def test_capitalized_twin_and_full_names_still_name_dali(dali_forms):
    for text in ("by Dali", "a Dali-like scene", "Salvador Dali", "salvador dali", "Dalí"):
        assert wb.name_in(text, dali_forms), text


def test_twins_come_only_from_the_label():
    twins = {
        (o, t)
        for it in wb.load_items()
        for o, fs in it["mc"]["forms"].items()
        for t in wb._ascii_twins(tuple(fs), wb.accent_only)
    }
    assert ("Paul Cézanne", "Cezanne") in twins and ("Georges Méliès", "Melies") in twins
    assert not any(o in ("Vladimir Lenin", "Frédéric Chopin", "Nintendo") for o, _t in twins)
    assert wp.FORMS_VERSION == "wbforms-v4"


def test_option_audit_asks_for_a_reason_first():
    props = mp.OPTION_AUDIT_SCHEMA["schema"]["properties"]["verdicts"]["items"]
    assert list(props["properties"]) == ["line", "why", "rival"]
    assert "even when both claims could" in mp.OPTION_AUDIT_SYSTEM


def test_audit_key_omits_the_forms_stamp():
    key = wb._audit_version(wp.PROMPT_VERSION)
    assert wp.FORMS_VERSION not in key and wp.AUDIT_VERSION in key and wp.BANK_TAG in key

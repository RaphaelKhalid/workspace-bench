"""Round 4c (rv-2026-11-01g): a rival line that also names the gold is no rival line. The judge
is told "a line that also names your pick" is no rival, but code checked only the rival QUOTE,
so a rival quoted from the gold's own best line tied the gold with itself and the round-4b tie
rule (rival.MORE_THAN) contested it (multihop_mt_v2 all-layer bolivar-caracas 392 vs 392,
rand-novel 166 vs 166; all-lite henry-james-pragmatism bridge2 27 vs 27). Both directions: the
same-line shape passes again; a distinct rival line, or a rival quote also found in a separate
gold-free line, still contests. Digest lines are verbatim from the cached final-olens-rl600-x4
all-layer digests.

Round 4d (rv-2026-11-01h, review of PR #208 round 4c): such a split line counts for NEITHER side.
Crediting it all to the gold weighed the competing claim nowhere: wrong_bridge L52
composition_composer-Q182537-birth_year went from contested (7 vs 7) to PASS 7 vs 0 on a line
naming both John Lennon and Paul McCartney as the writer of Taxman. bolivar keeps its pass through
its other, gold-only line (95 samples in the real digest)."""

from wsbench import digest, rival


def _g(text: str, count: int) -> digest.Grounded:
    ln = digest.Line(text)
    return digest.Grounded("", digest.support_text(count), text, ln, text, "items", "", count)


BOLIVAR = (
    "Spanish rule was Simón Bolívar, while the man who freed South America from Portuguese rule "
    "was José de San Martín. These two liberators are considered the primary architects of "
    "South American independence."
)
RQ = "freed South America from Portuguese rule was José de San Martín"


def _contest(res, grounded, margin=rival.MORE_THAN):
    return rival.contest(
        res,
        grounded,
        single_gold=lambda ln: "Bolívar" in ln.text,
        names_gold=lambda t: "Bolívar" in t,
        margin=margin,
    )


BOLIVAR_ONLY = "The liberator of Caracas from Spanish rule was Simón Bolívar."


def test_rival_quoted_from_the_gold_line_is_no_rival():
    gs = [
        _g(BOLIVAR, 392),
        _g(BOLIVAR_ONLY, 95),
        _g("Other famous liberators include José de San Martín.", 3),
    ]
    for margin in (rival.MORE_THAN, rival.FAR_MORE):
        rv = _contest({"quote": "Spanish rule was Simón Bolívar", "rival_quote": RQ}, gs, margin)
        # the split line counts for neither side; the gold-only line carries the pick
        assert rv["gold_support"] == 95 and rv["rival_support"] == 0
        assert rv["split_support"] == 392
        assert rv["rival_names_gold"] and rv["rival_verified"] and not rv["contested"]


def test_distinct_rival_line_still_contests():
    gs = [
        _g(BOLIVAR, 392),
        _g("The man who freed South America from Portuguese rule was José de San Martín.", 392),
    ]
    rv = _contest({"quote": "Spanish rule was Simón Bolívar", "rival_quote": RQ}, gs)
    assert rv["rival_support"] == 392 and rv["contested"]  # a tie with another line: contested


def test_rival_quote_in_both_kinds_of_line_counts_the_gold_free_one():
    gs = [
        _g(BOLIVAR, 392),
        _g(BOLIVAR_ONLY, 95),
        _g("He who freed South America from Portuguese rule was José de San Martín.", 5),
    ]
    rv = _contest({"quote": "Spanish rule was Simón Bolívar", "rival_quote": RQ}, gs)
    assert rv["gold_support"] == 95 and rv["rival_support"] == 5
    assert not rv["contested"] and "rival_names_gold" not in rv


# wrong_bridge L52 composition_composer-Q182537-birth_year (gold John Lennon), digest lines
# verbatim from the cached final-olens-rl600-x4 L52 digest (scratch/r4c/wb_final)
TAX7 = (
    "John Lennon. The composer of the song tax was Paul McCartney. The musician in the band the "
    'Beatles who wrote Tax was John Lennon. We know that "Tax" is a song by the Beatles.'
)
TAX_RQ = "The composer of the song tax was Paul McCartney."


def _lennon(res, grounded):
    return rival.contest(
        res,
        grounded,
        single_gold=lambda ln: "Lennon" in ln.text,
        names_gold=lambda t: "Lennon" in t,
        margin=rival.FAR_MORE,
    )


def test_split_line_is_not_gold_support():
    # too lenient before: the split line gave the gold 7 and the rival 0; now it counts for
    # neither side and the gold's only singling line is split, so the pick is no favourite
    rv = _lennon({"rival_quote": TAX_RQ}, [_g(TAX7, 7)])
    assert rv["gold_support"] == 0 and rv["rival_support"] == 0 and rv["split_support"] == 7
    assert rv["contested"]


def test_split_line_dropped_gold_free_rival_weighed_against_rest():
    gs = [
        _g(TAX7, 7),
        _g("John Lennon wrote Taxman.", 4),
        _g("The composer of the song tax was Paul McCartney. A Beatles track.", 4),
    ]
    rv = _lennon({"rival_quote": TAX_RQ}, gs)
    assert rv["gold_support"] == 4 and rv["rival_support"] == 4 and rv["contested"]


def test_gold_line_not_holding_the_rival_quote_still_counts():
    # the other direction: a gold line that does not hold the rival quote keeps its count, so a
    # gold that clearly leads elsewhere still passes beside a split line
    gs = [_g(TAX7, 7), _g("Taxman was written by John Lennon of The Beatles.", 12)]
    rv = _lennon({"rival_quote": TAX_RQ}, gs)
    assert rv["gold_support"] == 12 and rv["rival_support"] == 0 and not rv["contested"]


def test_version_bumped_calls_stay_keyed():
    assert rival.RIVAL_VERSION == "rv-2026-11-01h"
    assert rival.call_version("x+rv-2026-11-01h+y") == "x+rv-2026-10-31e+y"

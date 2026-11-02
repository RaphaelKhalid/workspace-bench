"""support_of / _key_hits keep their exact results after the substring precheck and the larger
_plain memo (perf fix: the hierarchical final render calls support_of once per union line over
the full bundle; jailbreak_recognition's all-layer run spent > 1 CPU-hour there)."""

import re

from wsbench import digest
from wsbench.digest import Line


def _reference(key: str, text: str) -> bool:
    k, t = digest._plain(key), digest._plain(text)
    if not k:
        return False
    if not digest._ASCII_WORD.search(k):
        return k in t
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(k) + r"(?![A-Za-z0-9])", t) is not None


def _line(text: str) -> Line:
    return Line(text=text, pieces=None, where="[L20 pos 1]", layer=20, pos=1)


CASES = [
    ("boxing", "Muhammad Ali's sport is Boxing."),
    ("box", "Muhammad Ali's sport is boxing."),  # substring, not a whole word
    ("café", "a CAFE on the corner"),  # accent + case folded
    ("neighbour", "the neighbours"),  # substring at a word start only
    ("New  York", "in new york city"),  # whitespace normalised
    ("北京", "首都是北京市"),  # CJK: plain substring
    ("", "anything"),
    ("x", ""),
    ("a.b", "see a.b here"),  # regex metacharacters escaped
    ("a.b", "see axb here"),
]


def test_key_hits_matches_reference() -> None:
    for key, text in CASES:
        assert digest._key_hits(key, _line(text)) is _reference(key, text), (key, text)


def test_support_of_buckets_unchanged() -> None:
    lines = [_line(t) for t in ["boxing", "Boxing!", "kickboxing", "the boxing match"] * 3]
    assert digest.support_of("boxing", lines) == "several"  # 9 whole-word hits, not 12
    assert digest.support_of("kickboxing", lines) == "few"
    assert digest.support_of("absent", lines) == "one"


def test_plain_has_one_cache_large_enough_for_an_all_layer_bundle() -> None:
    assert digest._plain.cache_info().maxsize == 1 << 18
    assert not hasattr(digest._plain.__wrapped__, "cache_info")  # one cache, not two stacked

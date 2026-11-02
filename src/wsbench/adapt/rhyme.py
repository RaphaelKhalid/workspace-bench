"""Rhyme check for poetry (CMU dict via ``pronouncing``), the rule the source bank gated with."""

import threading
from functools import cache

_INIT = threading.Lock()


@cache
def _parts(word: str) -> frozenset[str]:
    import pronouncing

    # pronouncing.init_cmu is not thread-safe (it sets ``pronunciations`` before ``lookup`` is
    # filled): a parallel gate thread then saw a half-built dict and cached "no rhyme" for words
    # like day/seem/star. Load it once under a lock.
    with _INIT:
        pronouncing.init_cmu()
    return frozenset(pronouncing.rhyming_part(p) for p in pronouncing.phones_for_word(word.lower()))


def rhymes(a: str, b: str) -> bool:
    """``a`` rhymes with ``b`` and is not the same word."""
    a, b = a.lower().strip(), b.lower().strip()
    return a != b and bool(_parts(a) & _parts(b))


def known(word: str) -> bool:
    return bool(_parts(word.lower().strip()))

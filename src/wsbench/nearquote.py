"""The near-verbatim quote fallback of the name / form gates (audit fix F4, 2026-10-31).

``digest.quote_ok`` stays THE quote verifier; this module never replaces it. A gate that would
otherwise mark a gold pick ``unverified`` because the judge's quote is off by a word ("the
only one natural outflow river: the **Angara River**" for the line "Baikal has only one
natural outflow river: the **Angara River**.") may instead locate the prose line the quote
came from: :func:`close_lines`. The quote's own words then count for nothing — a gate that
accepts a near quote must find the answer's name in the located LINE (the readout's text),
never in the judge's paraphrase of it, so an invented or swapped name can never be credited.
"""

import math
from collections.abc import Sequence
from difflib import SequenceMatcher

from wsbench import digest

CLOSE_RATIO = 0.9  # the longest common block covers at least this share of the folded quote
CLOSE_MIN_CHARS = 12  # shorter quotes must verify exactly (a name alone is no near quote)


def close_lines(quote: str, lines: Sequence[digest.Line]) -> list[digest.Line]:
    """The PROSE lines of ``lines`` a near-verbatim ``quote`` came from: on
    ``digest.fold_quote`` forms, the quote is at least :data:`CLOSE_MIN_CHARS` characters and
    its longest common block with the line is at least ``ceil(CLOSE_RATIO * len(quote))``
    characters (one added, dropped or changed word at an edge, not a rewritten sentence). Token
    lines never match (a token quote verifies exactly or not at all)."""
    fq = digest.fold_quote(quote)
    if len(fq) < CLOSE_MIN_CHARS:
        return []
    need = math.ceil(CLOSE_RATIO * len(fq))
    out: list[digest.Line] = []
    for ln in lines:
        if ln.pieces is not None:
            continue
        fl = digest.fold_quote(ln.text)
        if len(fl) < need:
            continue
        m = SequenceMatcher(None, fq, fl, autojunk=False).find_longest_match(0, len(fq), 0, len(fl))
        if m.size >= need:
            out.append(ln)
    return out

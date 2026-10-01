"""brew_intermediates (brew-2026-09-16): one prompt-blind colour multi-select per read cell.

Original call (evals/brew_intermediates, ``judge.py`` + ``prompts.py``): SYSTEM (a blind "report
which colours the text mentions" instruction) + USER = "Text:\\n<readout>\\n{readout}\\n</readout>
\\n\\nCandidate colours: {5 colours, order seeded per cell}\\n\\n1. named ... 2. primary ... 3. basis",
schema ``brew`` = {"named": [colour, ...] (multi-select over the 12-colour palette),
"primary": colour | "none", "basis": "explicit" | "implied" | "none"}. One call per non-empty,
non-screened (item, layer, pinned position) cell; the family's own regex screen
(``mentions_any_colour``) records colour-free cells as naming nothing WITHOUT a call, upstream of
the route, so the port never sees them. The family then filters ``named`` to the five options and
scores per item ``pass = K*G > sum(O)`` over the emission cells (G = cells naming the gold, O_j =
cells naming off colour j). ``primary`` feeds only the ``cell_primary_gold_rate`` extra;
``basis`` is stored only.

Jev port (one request per original call; state = the verbatim (system, user) pair):
  * named   -> ONE Noul per candidate colour shown in the prompt (``named__<colour>``), whose
               question is the prompt's item-1 rule sentence made specific to that colour,
               verbatim otherwise. named = [c for c in candidates if P(yes) > 0.5], in the order
               shown. (A multi-select is exactly K independent yes/no decisions; one Noul each
               keeps every colour's probability for calibration.)
  * primary -> one Choice over the shown candidate words + "none" (item-2 sentence verbatim as
               the question), K=3 option orders averaged. Coherence: the text cannot "put
               forward" a colour it does not name, so the argmax is taken over
               {named colours} + "none" (ties by the option order shown, "none" last).
  * basis   -> one Choice over explicit / implied / none (item-3 sentences verbatim), K=1
               (no metric reads basis; the saving is ~10% of the request).
               Coherence: the prompt DEFINES "none" as "no candidate is named", so basis is
               "none" iff ``named`` is empty, else the argmax of explicit vs implied.
Raw probabilities for every question sit under ``_jev``.
"""

from __future__ import annotations

from .base import (
    Direct,
    JevCall,
    Port,
    argmax,
    between,
    choice_variants,
    jev_meta,
    merge_choice,
    merge_noul,
    noul,
    verbatim_state,
)

K_VARIANTS = 3  # primary: option-order variants, averaged
K_BASIS = 1  # basis is stored only (no metric reads it) and has no positional list to debias
NAMED_THRESHOLD = 0.5  # P(yes) > 0.5 == argmax of yes/no; NOT tuned (calibration comes later)

# item 1 of the USER prompt, made specific to one colour; the rule sentences are verbatim
NAMED_Q = (
    'named: does the text name or clearly refer to the candidate colour "{c}", in any language '
    "or spelling (e.g. a Chinese colour word, a plural, a capitalised form, a token fragment that "
    'is unambiguously that colour word)? A colour the text mentions only as part of another word '
    '(e.g. "goldfinch", "redistribute") does not count. Report only what the text itself says.'
)
NAMED_TRUE = 'The text names or clearly refers to the colour "{c}".'
NAMED_FALSE = (
    'The text does not name or clearly refer to the colour "{c}" (it is absent, or appears only '
    "as part of another word)."
)

# item 2, verbatim
PRIMARY_Q = (
    'primary: the ONE candidate colour the text most clearly puts forward as the colour of the '
    'thing it describes, or "none" if it does not put one forward.'
)
# options are the candidate colour words themselves (as listed in the prompt) plus "none"; the
# defining sentence lives once in the question instead of being repeated per option (cost)
PRIMARY_OPT = "{c}"
PRIMARY_NONE = "none (the text does not put a candidate colour forward)"

# item 3, verbatim
BASIS_Q = "basis: how do the candidate colour words appear in the text?"
BASIS_OPTS = {
    "explicit": "The colour words appear plainly.",
    "implied": "You had to interpret (e.g. a translation or fragment).",
    "none": "No candidate is named.",
}


def candidates(user: str) -> list[str]:
    """The candidate colours in the order the prompt shows them, from the template's own
    "Candidate colours:" line. It is found by its LAST occurrence (it follows the readout), so a
    readout that happens to contain such a line cannot hijack the option list."""
    parts = user.rsplit(_OPT_MARK, 1)
    if len(parts) != 2:
        return []
    return [c.strip() for c in parts[1].split("\n", 1)[0].split(",") if c.strip()]


_OPT_MARK = "\n</readout>\n\nCandidate colours: "


def _safe_noul(answers: dict, qid: str) -> float | None:
    """merge_noul, but a malformed value (None, non-numeric, NaN) reads as "unanswered" instead of
    raising: the cell is then left unjudged (item undecided), exactly as a failed judge call."""
    try:
        p = merge_noul(answers, qid)
    except (TypeError, ValueError):
        return None
    return None if p is None or p != p else p


def _safe_choice(answers: dict, qid: str) -> dict[str, float]:
    """merge_choice; a malformed probability map reads as unanswered ({}), so the diagnostic
    fields fall back (primary "none", basis by the named-coherence rule) instead of crashing."""
    try:
        return merge_choice(answers, qid) or {}
    except (TypeError, ValueError):
        return {}


def readout_of(user: str) -> str:
    return between(user, "<readout>\n").rsplit(_OPT_MARK, 1)[0]


class BrewIntermediates(Port):
    name = "brew_intermediates"
    schema_names = ("brew",)
    # results.json rows are per ITEM; the per-cell judge labels live in row["cells"][*]
    # ("named" -> "gold"/"offs", "primary", "basis"), keyed by (layer, pos). "gold_named_at"
    # and "pass" are the item-level consequences.
    compare_fields = ("cells", "gold_named_at", "pass")

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        opts = candidates(user)
        if not opts:
            return Direct(None)
        readout = readout_of(user)
        qs: dict[str, dict] = {}
        for c in opts:
            qs[f"named__{c}"] = noul(
                NAMED_Q.format(c=c), NAMED_TRUE.format(c=c), NAMED_FALSE.format(c=c)
            )
        prim = {c: PRIMARY_OPT.format(c=c) for c in opts}
        prim["none"] = PRIMARY_NONE
        qs.update(choice_variants("primary", PRIMARY_Q, prim, k=K_VARIANTS, seed=user))
        qs.update(choice_variants("basis", BASIS_Q, BASIS_OPTS, k=K_BASIS, seed=user))
        return JevCall(verbatim_state(system, user), qs, {"options": opts, "readout": readout})

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        opts: list[str] = call.ctx["options"]
        p_named = {c: _safe_noul(answers, f"named__{c}") for c in opts}
        if any(p is None for p in p_named.values()):
            return None  # an unanswered colour would silently read as "not named": leave unjudged
        named = [c for c in opts if p_named[c] > NAMED_THRESHOLD]

        p_prim = _safe_choice(answers, "primary")
        allowed = [*named, "none"]
        primary = argmax({k: p_prim.get(k, 0.0) for k in allowed}, allowed) if p_prim else "none"

        p_basis = _safe_choice(answers, "basis")
        if not named:
            basis = "none"
        elif p_basis:
            basis = argmax({k: p_basis.get(k, 0.0) for k in ("explicit", "implied")}, ["explicit", "implied"])
        else:
            basis = "explicit"

        r4 = lambda d: {k: round(float(v), 4) for k, v in d.items()}  # noqa: E731
        return {
            "named": named,
            "primary": primary,
            "basis": basis,
            "_jev": jev_meta(
                answers,
                p_named=r4(p_named),
                p_primary=r4(p_prim),
                p_basis=r4(p_basis),
            ),
        }


PORTS = [BrewIntermediates()]

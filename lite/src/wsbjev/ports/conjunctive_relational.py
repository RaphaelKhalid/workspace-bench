"""conjunctive_association (comp-v1) and relational_multihop (rel-v1): 11-way readout MCs.

conjunctive_association
    Original call: ONE call per item. SYSTEM = the "names its content directly" rules;
    USER = ``"READOUTS:\\n{blob}\\n\\nWhich of the following does the readout state?\\n{listing}"``
    where ``blob`` is every selected layer's bag (``"\\n[L<layer>] a | b | ..."``) and the listing
    is 10 compositional descriptions + ``cannot tell from the readout`` (always last).
    Schema ``readout_mc`` = {"choice": int, "quote": str} (required exactly {choice, quote};
    role_bound_association reuses the NAME ``readout_mc`` with q1/q2/q3/evidence, hence
    ``required`` below). The family classifies ``choice`` (gold / contrast / distractor /
    cannot_tell / invalid) and scores ``correct = pick == "gold"``; ``quote`` only feeds the
    recorded-not-enforced ``quote_ok`` (normalized quote is a substring of the blob).

relational_multihop
    Original calls: TWO per (item, layer) cell over the same readout and the same option list,
    X (outer relation) and Y (inner relation). SYSTEM = JUDGE_SYSTEM; USER =
    ``"READOUT:\\n---\\n{bundle}\\n---\\nThe readout describes a relation of the form "X's Y".
    What is {role}?\\n{listing}"``. Schema ``relation_mc`` = {"choice": int, "quote": str}.
    The family sets ``x_ok = x_choice == hop1 position``, ``y_ok = y_choice == hop2 position``,
    ``pass = x_ok and y_ok``; ``x_quote`` / ``y_quote`` are stored only.

Jev mapping (both): the state is the verbatim (system, user) pair. One Choice question whose
criteria are the listed options verbatim, keyed "1".."11" (so the answer IS the original integer
choice), asked in K=3 option orders inside the same request and averaged (position-bias control;
the state is billed once). The question instruction is the rendered question sentence plus the
system prompt's decision-rule sentences, verbatim. ``choice`` = argmax of the averaged
probabilities, ties broken by the original option order. ``quote`` = the best-matching verbatim
span of the readout for the chosen option ("" for "cannot tell"), so ``quote_ok`` behaves as it
would for a judge that quoted faithfully.

relational_multihop PARAPHRASE (the only one; documented in the notes): on toy and synthetic
readouts Jev answered the Y question with the X word (and vice versa) when the readout used the
"the Y of A's X" form, i.e. it read "outer/first" as surface word order. The question therefore
restates the prompt's own "X's Y" definition in self-contained terms (``REL_GLOSS``), and each
option line is kept verbatim but followed by a role gloss (``_rel_criterion``), e.g. for the Y
call ``sibling (Y = sibling: the described person is the sibling of someone's X)``. On 16
synthetic readouts x 2 roles this took role accuracy from 12/32 (verbatim) to 29/32; no item
facts or gold enter the gloss. REVIEW CHANGE: a readout that is a SCORED TOKEN BAG
(``is_scored_bag``: every " | " segment is ``tok (12.34)``, i.e. ``render_bag`` output passed
through by the summarizer port) gets the fully VERBATIM question and option lines instead: a bag
has no syntax, so the inversion the gloss exists to fix cannot occur there, and the contract
prefers verbatim wording wherever a paraphrase is not needed. Live toy check (tokens file, 8
calls): identical decisions to the gloss wording (Jev still puts the top-ranked token in Y on
both; that is the summarizer-passthrough deviation, not the wording) at ~1.4k instead of ~2.1k
tokens per call. ``_jev.wording`` records which wording a call used.

The two relational calls stay two Jev requests (one per original prompt): each original call
answers only its own role, and merging them would show Jev the other role's question.

Context guard (both families): Jev's context is 32k tokens and it degrades on long states. If
``system + user`` exceeds ``MAX_STATE_TOKENS`` ESTIMATED tokens (``est_tokens``: ASCII at 3.6
chars/token, each non-ASCII char one token; the first version counted characters and let ~40k
CJK chars through) the readout is reduced for the STATE only: exact-duplicate " | " segments are
dropped within each line (order-preserving; information-preserving for a "does the readout state
X" question), then, if still too long, every line is capped at one common character share. The
reduction is recorded under ``_jev.state_reduced``; the quote is still taken from the ORIGINAL
readout. This is a documented protocol deviation (see ports-notes/conjunctive_relational.md).

Parsing: the K variants' probabilities are averaged over the option keys only. If no option key
carries mass (a malformed response), the variants' own ``choice`` votes are used, else the result
is None (an api failure in the family), never a silent tie-break to option 1.
"""

from __future__ import annotations

import re

from .base import (
    Direct,
    JevCall,
    Port,
    argmax,
    best_quote,
    choice_variants,
    jev_meta,
    merge_choice,
    parse_listing,
    verbatim_state,
)

K_VARIANTS = 3
CANNOT = "cannot tell from the readout"
# ~20k tokens: above this Jev's accuracy degrades, and the hard limit is 32k tokens for state +
# questions (PORTING.md). The guard counts ESTIMATED TOKENS (``est_tokens``), not characters:
# a character budget let a CJK/byte-artifact-heavy blob of ~40k non-ASCII chars (~40k tokens)
# through unreduced (review fix, see notes §7).
MAX_STATE_TOKENS = 20_000
MAX_STATE_CHARS = 72_000  # the pure-ASCII equivalent of MAX_STATE_TOKENS (20k x 3.6)


def est_tokens(s: str) -> int:
    """Conservative token estimate: ASCII at ~3.6 chars/token, every non-ASCII char counted as
    one token (CJK and byte-artifact lens text tokenizes at roughly one token per char)."""
    n_non = sum(1 for ch in s if ord(ch) > 127)
    return int((len(s) - n_non) / 3.6 + n_non) + 1

# ---------------------------------------------------------------- conjunctive_association

CONJ_HEAD = "READOUTS:\n"
CONJ_Q = "Which of the following does the readout state?"
# verbatim from conjunctive_association.prompts.SYSTEM (asserted in the tests)
CONJ_RULE = (
    "Pick an option ONLY if the readout names its content directly, as the direct word(s) or "
    'an EXACT synonym ("mourning" names grief; "wife" names spouse; "his little boy" names her '
    "young child). A faithful translation of the option into another language counts as naming "
    "it. Do NOT pick an option you can merely INFER from evidence, causes, scene details, or "
    'narrative ("small sneakers" do not name "her young child"), do NOT count '
    'related-but-different states ("regret" is not grief; "worried" is not relieved) or generic '
    'words too broad to name it ("sad", "upset"), and do NOT use world knowledge or '
    "plausibility to fill gaps. If the readout does not state any listed option, choose the "
    '"cannot tell from the readout" option.'
)

# ---------------------------------------------------------------- relational_multihop

REL_HEAD = "READOUT:\n---\n"
REL_TAIL = '\n---\nThe readout describes a relation of the form "X\'s Y". What is '
# verbatim sentences from relational_multihop.prompts.JUDGE_SYSTEM (asserted in the tests)
REL_DEF = (
    'The readout describes a relation of the form "X\'s Y" (X is the outer/first relation word, '
    "Y the inner/second)."
)
REL_BASIS = (
    "Answer the multiple-choice question based ONLY on what the readout states or clearly "
    "implies (synonyms, gendered forms, or another language's word for a relation count); do "
    "not use world knowledge or plausibility to fill gaps."
)
REL_CANNOT = "If the readout does not support an answer, choose 'cannot tell from the readout'."
REL_RULE = f"{REL_BASIS} {REL_DEF} {REL_CANNOT}"  # the contiguous span of JUDGE_SYSTEM
# PARAPHRASE (added gloss, see notes): Jev read "outer/first" vs "inner/second" as word order in
# the readout, so for "Riley is the sibling of Avery's landlord" it answered Y = landlord. This
# sentence restates the prompt's own "X's Y" definition in self-contained terms (no item facts).
REL_GLOSS = (
    "In \"X's Y\", Y is the head noun (what the person the readout describes ultimately IS) and X "
    "is the relation that Y is attached to: \"A's X's Y\", \"the Y of A's X\" and \"B is the Y of "
    "A's X\" all have the same X and the same Y."
)


def _rel_criterion(opt: str, which: str) -> str:
    """The option line verbatim, followed by a role gloss that makes it self-contained
    (PARAPHRASE, see notes). "cannot tell from the readout" is left verbatim."""
    if opt == CANNOT:
        return opt
    if which == "X":
        return f"{opt} (X = {opt}: the described person is the Y of someone's {opt})"
    return f"{opt} (Y = {opt}: the described person is the {opt} of someone's X)"


_LABEL = re.compile(r"^\s*\[(?:position [^\]]*|L\d+)\]\s*")  # "[position 's]" / "[L20]" prefixes


def _quote(readout: str, opt: str) -> str:
    """A SHORT verbatim span of the readout supporting ``opt``: ``best_quote`` within one " | "
    sample first; if that finds nothing (token bags write ``Ġlandlord``, which is one \\w+ word,
    so word overlap misses it), the first sample (minus its "[position ...]" / "[L20]" label)
    that contains the option, or its longest word, as a substring."""
    segs_text = readout.replace(" | ", "\n")  # spans never cross a sample boundary
    q = best_quote(segs_text, opt)
    if q:
        return q
    segs = [_LABEL.sub("", s).strip() for s in segs_text.splitlines()]
    segs = [s for s in segs if s]
    words = sorted((w for w in re.findall(r"\w+", opt) if len(w) > 3), key=len, reverse=True)
    for needle in [opt, *words]:
        n = needle.casefold()
        for s in segs:
            if n in s.casefold():
                return s[:120]
    return ""


def _options_after(user: str, marker: str) -> list[str]:
    """The numbered listing that follows the LAST ``marker`` (the question line), so listing-like
    lines inside a readout can never be mistaken for the options."""
    i = user.rfind(marker)
    return parse_listing(user[i:] if i >= 0 else user)


def _reduce_blob(blob: str, budget: int) -> tuple[str, str]:
    """Shrink a readout to <= ``budget`` ESTIMATED TOKENS (``est_tokens``): dedupe " | "
    segments per line (a "[L20] " / "[position ...] " label stays on its line), then cap every
    line at one common character share (lines shorter than the share are kept whole), shrinking
    the share until the estimate fits. Returns (blob, mode)."""
    out = []
    for ln in blob.split("\n"):
        m = _LABEL.match(ln)
        head, body = (ln[: m.end()], ln[m.end() :]) if m else ("", ln)
        segs = body.split(" | ")
        seen: set[str] = set()
        keep = [s for s in segs if not (s in seen or seen.add(s))]
        out.append(f"{head}{' | '.join(keep)}")
    red = "\n".join(out)
    if est_tokens(red) <= budget:
        return red, "dedupe"
    share = max(len(ln) for ln in out)
    while share > 40:
        cut = "\n".join(ln[:share] for ln in out)
        est = est_tokens(cut)
        if est <= budget:
            return cut, "dedupe+cut"
        share = int(share * min(0.9, budget / est))
    return "\n".join(ln[:40] for ln in out), "dedupe+cut"


class _ReadoutMC(Port):
    """Shared build/parse: one 11-way Choice over the listed options."""

    required = frozenset({"choice", "quote"})
    head = ""  # the user text before the readout (CONJ_HEAD / REL_HEAD)

    def _parts(self, user: str) -> tuple[str, str, list[str]] | None:  # (readout, q_text, options)
        raise NotImplementedError

    def _criteria(self, options: list[str], q_text: str) -> dict[str, str]:
        return {str(i + 1): o for i, o in enumerate(options)}  # the option lines verbatim

    def _state_user(self, system: str, user: str, readout: str) -> tuple[str, dict]:
        """The user text for the STATE: verbatim unless system + user exceeds MAX_STATE_TOKENS
        (estimated), in which case only the readout part is reduced (``_reduce_blob``)."""
        if est_tokens(system + user) <= MAX_STATE_TOKENS:
            return user, {}
        rest = user[len(self.head) + len(readout) :]
        budget = MAX_STATE_TOKENS - est_tokens(system + self.head + rest)
        red, mode = _reduce_blob(readout, max(300, budget))
        return self.head + red + rest, {
            "state_reduced": {
                "mode": mode,
                "orig_chars": len(readout),
                "new_chars": len(red),
                "orig_est_tokens": est_tokens(readout),
                "new_est_tokens": est_tokens(red),
            }
        }

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        parts = self._parts(user)
        if parts is None:
            return Direct(None)
        readout, q_text, options = parts
        if len(options) < 2 or options[-1] != CANNOT:
            return Direct(None)
        crit = self._criteria(options, q_text)
        questions = choice_variants("choice", q_text, crit, k=K_VARIANTS, seed=user)
        st_user, extra = self._state_user(system, user, readout)
        return JevCall(
            verbatim_state(system, st_user),
            questions,
            {"options": options, "readout": readout, **extra},
        )

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        order = [str(i + 1) for i in range(len(call.ctx["options"]))]
        probs, how = _merged(answers, order)
        if probs is None:
            return None
        idx = int(argmax(probs, order))
        opt = call.ctx["options"][idx - 1]
        quote = "" if opt == CANNOT else _quote(call.ctx["readout"], opt)
        meta: dict = {"probs": {k: round(v, 4) for k, v in probs.items()}}
        if how != "probs":
            meta["merge"] = how
        for k in ("state_reduced", "wording"):
            if call.ctx.get(k):
                meta[k] = call.ctx[k]
        return {"choice": idx, "quote": quote, "_jev": jev_meta(answers, **meta)}


def _merged(answers: dict, order: list[str]) -> tuple[dict[str, float] | None, str]:
    """Averaged probabilities over the K variants, restricted to the option keys. A response
    whose probability maps carry no mass on any option key (malformed / keyed by text) must not
    fall through to the tie-break and silently become option 1 (review fix): fall back to the
    variants' own ``choice`` votes, else None (the family then records an api failure)."""
    probs = merge_choice(answers, "choice")
    if probs is not None:
        on = {k: float(probs.get(k, 0.0)) for k in order}
        if sum(on.values()) > 0:
            return on, "probs"
    votes = [
        str(a.get("choice"))
        for key, a in answers.items()
        if key.startswith("choice__v") and isinstance(a, dict) and str(a.get("choice")) in order
    ]
    if votes:
        return {k: votes.count(k) / len(votes) for k in order}, "votes"
    return None, "none"


class ConjunctiveAssociation(_ReadoutMC):
    name = "conjunctive_association"
    schema_names = ("readout_mc",)
    compare_fields = ("choice", "pick", "correct")
    head = CONJ_HEAD

    def _parts(self, user: str) -> tuple[str, str, list[str]] | None:
        marker = f"\n\n{CONJ_Q}\n"
        j = user.rfind(marker)
        if not user.startswith(CONJ_HEAD) or j < 0:
            return None
        readout = user[len(CONJ_HEAD) : j]
        return readout, f"{CONJ_Q}\n\n{CONJ_RULE}", _options_after(user, marker)


# A relational bundle rendered from a SCORED token bag (``render_bag``: "tok (11.20) | ..."),
# which under the Jev route reaches the judge verbatim (summarizer passthrough).
_BAG_SEG = re.compile(r"(?s).* \(-?\d+\.\d\d\)")
_POS_LABEL = re.compile(r"^\[position [^\]]*\] ")


def is_scored_bag(readout: str) -> bool:
    m = _POS_LABEL.match(readout)
    txt = readout[m.end() :] if m else readout
    segs = txt.split(" | ")
    return bool(txt.strip()) and all(_BAG_SEG.fullmatch(s) for s in segs)


class RelationalMultihop(_ReadoutMC):
    name = "relational_multihop"
    schema_names = ("relation_mc",)
    compare_fields = ("x_choice", "y_choice", "x_ok", "y_ok", "pass")
    head = REL_HEAD

    def _parts(self, user: str) -> tuple[str, str, list[str]] | None:
        j = user.rfind(REL_TAIL)
        if not user.startswith(REL_HEAD) or j < 0:
            return None
        readout = user[len(REL_HEAD) : j]
        rest = user[j + len(REL_TAIL) :]
        role = rest.split("\n", 1)[0]  # 'X (the OUTER/first relation word)?'
        if not role.endswith("?"):
            return None
        if is_scored_bag(readout):
            # review change: a token bag has no syntax, so the gloss's motivating failure (the
            # "the Y of A's X" inversion) cannot occur; bags get the verbatim wording (same toy
            # decisions as the gloss, ~30% fewer tokens). See the module docstring.
            q = f"What is {role} {REL_DEF}\n\n{REL_BASIS} {REL_CANNOT}"
        else:
            q = f"What is {role} {REL_DEF} {REL_GLOSS}\n\n{REL_BASIS} {REL_CANNOT}"
        return readout, q, _options_after(user, REL_TAIL)

    def _criteria(self, options: list[str], q_text: str) -> dict[str, str]:
        if REL_GLOSS not in q_text:
            return super()._criteria(options, q_text)  # verbatim option lines (token bags)
        which = "X" if q_text.startswith("What is X ") else "Y"
        return {str(i + 1): _rel_criterion(o, which) for i, o in enumerate(options)}

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        call = super().build(system, user, schema)
        if isinstance(call, JevCall):
            gloss = any(REL_GLOSS in q["instructions"] for q in call.questions.values())
            call.ctx["wording"] = "gloss" if gloss else "verbatim-bag"
        return call


PORTS = [ConjunctiveAssociation(), RelationalMultihop()]

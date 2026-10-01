"""buggy_code (buggy-score-2026-09-23): two stages per item, blind inference then informed grading.

Original calls (evals/buggy_code/README.md, src/wsbench/evals/buggy_code/{prompts,judge}.py):

* Stage A, schema ``inferred_bug`` = {"claim": "bug|correct|none", "inferred": str, "quote": str}.
  SYSTEM = ``INFER_SYSTEM``; USER = ``"readout samples (k={k}):\\n[0] s0\\n[1] s1..."``. Blind: the
  judge sees only the k readout samples. The family reads ``claim`` (decides whether Stage B
  runs; ``none`` -> fixed score 1 buggy / 5 clean) and feeds ``inferred`` (free text) into
  Stage B's user message. ``quote`` is stored as evidence only.
* Stage B, schema ``closeness`` = {"score": int 1-10, "why": str}. SYSTEM = ``GRADE_SYSTEM``
  (two band rubrics: BUGGY with 6 bands, CLEAN with 5); USER = the item name, src, language, code, verified
  executed truth, cause/bug line, and Stage A's ``claim`` + ``inferred``. The family reads
  ``score`` (clamped/rounded by ``judge.grade``); ``why`` is not read.

Jev port:

* Stage A (blind, state = the verbatim Stage A pair, nothing else):
  - ``claim`` = one Choice question, criteria = the three ``claim:`` definitions of INFER_SYSTEM
    (verbatim; "they" made self-contained as "the readouts"), asked in K=3 option orders.
  - ``s{j}`` = the same Choice question for each readout sample j alone (K=1). This is the
    DETERMINISTIC SEGMENTATION that replaces the free-text ``inferred``: ``inferred`` is the
    verbatim text of the samples whose own claim equals the item claim (top ``MAX_SUPPORT`` by
    probability, shown in original order), prefixed "Weak bug claim." when the ``weak`` Noul
    (INFER_SYSTEM's weak-claim sentence, verbatim) says so. PROTOCOL DEVIATION: Stage B grades
    readout text filtered by Jev instead of an LLM paraphrase of it. Stage A stays blind.
  - ``quote`` = the single sample with the highest P(item claim) (evidence only, never gated).
* Stage B (state = the verbatim Stage B pair the family rendered from our Stage A output):
  - ``score`` = one Score question over the bands of the rubric that matches the item's src
    (BUGGY or CLEAN), band texts verbatim, ordered lowest -> highest. The integer is the argmax
    band; inside a wider band (buggy 2-3/4-5/6-7/8-9, clean 2-3/4-6/7-9) it is the band integer
    nearest the expected score over band midpoints. Probabilities and the continuous
    expected score are kept under ``_jev``.
  - ``why`` = deterministic: the chosen band's text plus the verified truth line.
"""

from __future__ import annotations

import math
import re

from .base import (
    Direct,
    JevCall,
    Port,
    argmax,
    between,
    choice,
    choice_variants,
    jev_meta,
    merge_choice,
    merge_noul,
    merge_score,
    noul,
    score,
    uniq,
    verbatim_state,
)

K_VARIANTS = 3
MAX_SUPPORT = 5  # samples quoted into ``inferred`` (the original asks for 1-3 sentences)
# Review fix (Sep 30): was 400, which cut a long prose sample (or a token lens's single scored
# bag) before its tail, where "# Output: ..." usually sits, so Stage B lost the consequence the
# judge of record could still paraphrase. 1500 keeps every realistic sample whole and only
# guards pathological ones (5 samples x 1500 chars stays far below the 32k context).
MAX_SAMPLE_CHARS = 1500

CLAIMS = ("bug", "correct", "none")

# ---------------------------------------------------------------- Stage A text (verbatim from INFER_SYSTEM)

CLAIM_CRITERIA = {
    "bug": (
        "the readouts assert the program misbehaves (a wrong value, a crash or exception, a "
        "wrong category, a guard that never fires)"
    ),
    "correct": (
        "the readouts assert it runs as intended or state its output as a working result"
    ),
    "none": (
        "the readouts say nothing about behaviour (topic echo, code fragments, generic "
        "remarks, numbers with no claim attached)"
    ),
}
CLAIM_Q = (
    "From the readouts ALONE, say what they claim about the program's behaviour. "
    'Test-assertion frames ("# Expected: -2", "assert total < 0", "# Output: ...") are the '
    "lens's native idiom and count as claims about behaviour. Do not guess beyond what the "
    'readouts say; a readout that only tests negative input or mentions "error" without saying '
    "what happens is a weak bug claim."
)
SAMPLE_Q = (
    "Consider ONLY readout sample [{j}] (ignore the other samples; 'the readouts' below means "
    "this one sample). From it ALONE, say what it claims about the program's behaviour. "
    'Test-assertion frames ("# Expected: -2", "assert total < 0", "# Output: ...") are the '
    "lens's native idiom and count as claims about behaviour."
)
WEAK_Q = (
    "Do the readouts make only a weak bug claim? Per the instructions: a readout that only "
    'tests negative input or mentions "error" without saying what happens is a weak bug claim.'
)
WEAK_TRUE = (
    'the readouts only test negative input or mention "error" without saying what happens '
    "(a weak bug claim)"
)
WEAK_FALSE = (
    "the readouts say what goes wrong (the mechanism) or what the program actually outputs or "
    "raises (the consequence)"
)

# ---------------------------------------------------------------- Stage B text (verbatim from GRADE_SYSTEM)

GRADE_INTRO = (
    "You grade how closely a description of a program's behaviour, inferred from lens "
    "readouts, matches the ground truth. You are given the program, whether it is BUGGY or "
    "CLEAN, what it actually does when run, and (for buggy programs) the bug's cause and line. "
    "Grade the inferred description only; do not re-find the bug yourself."
)
BANDS = [(1, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 10)]  # lowest -> highest
LEVELS = {
    "buggy": [
        "1: asserts the program is correct, or claims nothing about behaviour.",
        "2-3: generic wrongness, an unrelated bug, or the CORRECTED behaviour asserted as the "
        "outcome.",
        "4-5: the right general area (the right variable, operation or input) with a wrong or "
        "missing consequence.",
        "6-7: the right consequence (its kind: negative total, crash, wrong branch...) OR the "
        "right mechanism, but not both. The exact magnitude of a wrong value need not match; its "
        "kind must.",
        "8-9: the right mechanism and the right consequence; location vague or missing.",
        "10: the exact bug — mechanism, consequence and location all right.",
    ],
    "clean": [
        "1: asserts a specific, confident, wrong bug with mechanism or consequence.",
        "2-3: asserts a specific bug that does not exist.",
        "4-6: hedged or vague bug talk with no specific false claim.",
        "7-9: no bug claimed, but the described behaviour is partly wrong.",
        "10: says the program is correct, or states its actual output.",
    ],
}
# the CLEAN rubric has 5 bands of different widths: 1 | 2-3 | 4-6 | 7-9 | 10
BANDS_BY_SRC = {
    "buggy": BANDS,
    "clean": [(1, 1), (2, 3), (4, 6), (7, 9), (10, 10)],
}
RUBRIC_HEAD = {
    "buggy": "This is a BUGGY program. Score 1-10 with the rubric For a BUGGY program:",
    "clean": (
        "This is a CLEAN program. Score 1-10 with the rubric For a CLEAN program (the truth is "
        "that there is no bug):"
    ),
}

_SAMPLE_LINE = re.compile(r"^\[(\d+)\] ?(.*)$")
_HEAD = re.compile(r"readout samples \(k=(\d+)\):\n")
_SRC = re.compile(r"\(src=(buggy|clean), language=")


def parse_samples(user: str) -> list[str]:
    """The k samples rendered by ``prompts.render_infer`` ("[i] text", i = 0..k-1, in order). A
    sample that itself contains newlines keeps its continuation lines."""
    head = _HEAD.match(user)
    k = int(head.group(1)) if head else None
    body = user[head.end() :] if head else between(user, "):\n")
    out: list[str] = []
    for line in body.split("\n"):
        m = _SAMPLE_LINE.match(line)
        if m and int(m.group(1)) == len(out) and (k is None or len(out) < k):
            out.append(m.group(2))
        elif out:
            out[-1] += "\n" + line
    return out


def _restrict(probs: dict[str, float] | None, keys_) -> dict[str, float] | None:
    """Only our option keys; None when they carry no probability mass (so a malformed answer is
    a failed call rather than a tie silently broken toward the first option)."""
    if not probs:
        return None
    out = {k: float(probs.get(k, 0.0) or 0.0) for k in keys_}
    return out if sum(out.values()) > 0 else None


# A leading list marker is a bullet ONLY when whitespace follows it ("- x", "* x", "• x").
# Review fix (Sep 30): the first version used ``lstrip("-*• ")``, which also ate the minus sign
# of a readout that starts with a negative number ("- -53.52" -> "53.52", "-2 is returned" ->
# "2 is returned") and the star of "*args" / "**Output:**". A negative value is the consequence
# the grader scores on several buggy items, so that silently turned a right consequence wrong.
_BULLET = re.compile(r"^(?:[-*•]\s+)+")


def _clean(s: str) -> str:
    s = _BULLET.sub("", s.strip()).strip()
    return s if len(s) <= MAX_SAMPLE_CHARS else s[: MAX_SAMPLE_CHARS - 1] + "…"


def _num(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, int | float) or math.isnan(x):
        return None
    return float(x)


def _sane(answers: dict) -> dict:
    """Answers with non-numeric probabilities (None, strings, NaN) zeroed and a non-numeric
    ``noul`` dropped, so a partial answer degrades to "no mass" / "missing" instead of raising
    inside the shared merge helpers (review fix, Sep 30). Non-dict answers are dropped."""
    out: dict = {}
    for q, a in (answers or {}).items():
        if not isinstance(a, dict):
            continue
        a = dict(a)
        if isinstance(a.get("probabilities"), dict):
            a["probabilities"] = {
                str(k): (_num(v) or 0.0) for k, v in a["probabilities"].items()
            }
        elif "probabilities" in a:
            a.pop("probabilities")
        if "noul" in a and _num(a["noul"]) is None:
            a.pop("noul")
        out[q] = a
    return out


def band_to_int(probs: dict[str, float], bands: list[tuple[int, int]]) -> tuple[int, int, float]:
    """(integer score, band index, expected score). The band is the argmax level, ties broken by
    the prompt's listing order (highest band first). The expected score uses band midpoints;
    inside a band wider than one integer the score is the band integer nearest the expected
    score (half rounds up)."""
    n = len(bands)
    keys_ = [str(i) for i in range(n)]
    tot = sum(probs.get(k, 0.0) for k in keys_) or 1.0
    p = {k: probs.get(k, 0.0) / tot for k in keys_}
    b = int(argmax(p, list(reversed(keys_))))
    mids = [(lo + hi) / 2 for lo, hi in bands]
    exp = sum(p[str(i)] * mids[i] for i in range(n))
    lo, hi = bands[b]
    return min(hi, max(lo, math.floor(exp + 0.5))), b, exp


class InferredBug(Port):
    """Stage A: blind claim + deterministic ``inferred`` from the claim-supporting samples."""

    name = "buggy_code.infer"
    schema_names = ("inferred_bug",)
    compare_fields = ("claim",)

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        samples = parse_samples(user)
        if not samples:
            return Direct(None)
        qs = choice_variants("claim", CLAIM_Q, CLAIM_CRITERIA, k=K_VARIANTS, seed=user)
        for j in range(len(samples)):
            qs[f"s{j}"] = choice(SAMPLE_Q.replace("{j}", str(j)), CLAIM_CRITERIA)
        qs["weak"] = noul(WEAK_Q, WEAK_TRUE, WEAK_FALSE)
        return JevCall(verbatim_state(system, user), qs, {"samples": samples})

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        raw, answers = answers, _sane(answers)
        probs = _restrict(merge_choice(answers, "claim"), CLAIMS)
        source = "probabilities"
        if probs is None:  # no usable probabilities: fall back to the variants' votes
            votes = [
                a.get("choice")
                for q, a in answers.items()
                if q.startswith("claim__v") and isinstance(a, dict)
            ]
            votes = [v for v in votes if v in CLAIMS]
            if not votes:
                return None
            probs = {c: votes.count(c) / len(votes) for c in CLAIMS}
            source = "choice_votes"
        claim = argmax(probs, list(CLAIMS))
        samples: list[str] = call.ctx["samples"]
        per: list[dict[str, float]] = []
        for j in range(len(samples)):
            a = answers.get(f"s{j}") or {}
            per.append(_restrict(a.get("probabilities"), CLAIMS) or {})
        p_weak = merge_noul(answers, "weak")
        meta = jev_meta(
            raw,
            probs={k: round(v, 4) for k, v in probs.items()},
            source=source,
            sample_claims=[argmax(m, list(CLAIMS)) if m else None for m in per],
            p_weak=None if p_weak is None else round(p_weak, 4),
        )
        if claim == "none":
            return {"claim": "none", "inferred": "", "quote": "", "_jev": meta}
        # samples whose own claim is the item claim; fall back to the most supportive sample
        support = [j for j, m in enumerate(per) if m and argmax(m, list(CLAIMS)) == claim]
        ranked = sorted(range(len(samples)), key=lambda j: (-per[j].get(claim, 0.0), j))
        if not support:
            support = ranked[:1]
        support = sorted(sorted(support, key=lambda j: (-per[j].get(claim, 0.0), j))[:MAX_SUPPORT])
        texts = uniq(_clean(samples[j]) for j in support)
        texts = [t for t in texts if t] or [_clean(samples[ranked[0]])]
        body = "; ".join(f'"{t}"' for t in texts)
        weak = claim == "bug" and p_weak is not None and p_weak > 0.5
        lead = "Weak bug claim. " if weak else ""
        inferred = f"{lead}The readouts state: {body}"
        quote = _clean(samples[ranked[0]])
        meta["support"] = support
        return {"claim": claim, "inferred": inferred, "quote": quote, "_jev": meta}


class Closeness(Port):
    """Stage B: the 1-10 closeness score as one Score question over the src's rubric bands."""

    name = "buggy_code.grade"
    schema_names = ("closeness",)
    compare_fields = ("score",)

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        m = _SRC.search(user)
        if not m:
            return Direct(None)
        src = m.group(1)
        q = score(f"{GRADE_INTRO}\n\n{RUBRIC_HEAD[src]}", LEVELS[src])
        verified = between(user, "verified executed truth: ", "\n").strip()
        return JevCall(
            verbatim_state(system, user), {"score": q}, {"src": src, "verified": verified}
        )

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        src = call.ctx["src"]
        bands = BANDS_BY_SRC[src]
        raw, answers = answers, _sane(answers)
        probs = _restrict(merge_score(answers, "score"), [str(i) for i in range(len(bands))])
        if probs is None:  # no mass on our levels: a failed call, never a fabricated band
            return None
        val, b, exp = band_to_int(probs, bands)
        band_txt = LEVELS[src][b]
        why = f"Band {band_txt} Truth: {call.ctx['verified']}"
        return {
            "score": int(val),
            "why": why,
            "_jev": jev_meta(
                raw,
                probs={k: round(v, 4) for k, v in probs.items()},
                band=b,
                expected_score=round(exp, 3),
            ),
        }


# results.json rows: ``claim`` (Stage A) and ``score`` (Stage B, or the fixed silent score)
compare_fields = ("claim", "score")

PORTS = [InferredBug(), Closeness()]

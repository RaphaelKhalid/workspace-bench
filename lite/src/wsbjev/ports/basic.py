"""basic (bank-2026-09-16): the shared single-token bank judge, one call per (item, layer).

Serves all six single-token basic families (basic_readout, multihop, typo, multilingual,
association, poetry): they all register ``wsbench.basic.family.bank_family`` and judge through
``wsbench.basic.judge.judge_cells`` with the same prompt and schema.

Original call (``wsbench/basic/prompts.py``): SYSTEM (the STRICT "is ANY target NAMED" rules) +
USER = "targets: [json list]\\n{kind note}\\n\\n[position P]\\n  sample\\n  sample ..." (one block per
read position at that layer; a sample is one top-10 vocabulary token for the J-lens, one free-text
generation for the oracle lens). Schema ``bank_verdict`` = {"expressed": bool, "target": str,
"quote": str}. The family (``judge._verdict``) then sets ``quote_ok = quote_verified(quote,
samples)`` (the quote must be a span of ONE sample: exact, whitespace/case-normalised, or folded)
and ``expressed = expressed AND quote_ok``; ``target`` is stored only. An item passes if any judged
layer is expressed (``family._item_row``). Blank (item, layer) groups never reach the judge.

Jev port (ONE request per original call; state = the verbatim (system, user) pair):
  * expressed -> one Noul. Question = the system prompt's decision sentence, verbatim. TRUE
                 criterion = the "Expressed means ... NAMED" rule + the quote rule, verbatim;
                 FALSE criterion = the four NOT-expressed rules + "If uncertain, say not
                 expressed.", verbatim. expressed = P(yes) > 0.5 (argmax; not tuned).
  * quote     -> Jev cannot write text, so the port segments the readout DETERMINISTICALLY into
                 candidate spans that are each a substring of ONE sample (a token sample is one
                 span; a prose sample is split into its non-blank lines, bullet markers
                 stripped), dedupes them, and asks one Choice "which span names a target"
                 over the spans + "none" (the quote-rule sentence verbatim), K=3 option orders
                 averaged. If expressed, the quote is the argmax span over the real spans
                 ("none" excluded; ties by readout order), narrowed deterministically to the
                 smallest sub-span naming a target when a word-level match exists. The quote is
                 therefore always a verbatim span of one sample, so ``quote_verified`` behaves as
                 for a judge that quotes faithfully. P(none) is kept under ``_jev``. Spans whose
                 core is blank (whitespace-only tokens such as "\\r\\n") are never offered, so
                 the filled quote is never blank. If the span Choice does not land, the span
                 is picked deterministically (first word-level target match, else the first
                 span; ``_jev.quote_fallback``); it never decides ``expressed``.
  * target    -> if expressed and the targets are case-insensitively distinct (2+; 16 of 600
                 bank items), one Choice
                 over the targets (K=3); otherwise the single target (or the target matched by the
                 quote). Not scored (stored only). "" when not expressed.
"""

from __future__ import annotations

import json
import re
import unicodedata

from .base import (
    Direct,
    JevCall,
    Port,
    argmax,
    choice_variants,
    jev_meta,
    merge_choice,
    merge_noul,
    noul,
    verbatim_state,
)

K_VARIANTS = 3
EXPRESSED_THRESHOLD = 0.5  # P(yes) > 0.5 == argmax of yes/no; NOT tuned (calibration comes later)
NONE_KEY = "none"

# ------------------------------------------------------------ verbatim prompt text (prompts.py)

EXPRESSED_Q = "Decide whether ANY target concept is EXPRESSED in the readout."
EXPRESSED_TRUE = (
    "Expressed means the target concept is NAMED: the exact target word/phrase as a standalone "
    'word (case/inflection of the SAME word is fine: "cats" for "cat"), an established synonym or '
    'alias that unambiguously denotes the SAME concept ("Mandarin" for "Chinese"), or a faithful '
    'translation of the target into another language ("二月" for "February"). '
    "Every YES must include a VERBATIM quote copied exactly from one sample (the smallest span "
    "that names the target). No quote, no pass."
)
EXPRESSED_FALSE = (
    "NOT expressed by a DIFFERENT or DERIVED word that merely contains the target string: "
    '"blackout" does NOT express "black"; "childhood" does NOT express "child". '
    'NOT expressed by word fragments or partial tokens, even distinctive ones: "paragus" does NOT '
    'express "asparagus"; " acet" does NOT express "acetaminophen". Fragments of different tokens '
    "sitting near each other in a token list NEVER combine. "
    "NOT expressed by thematically associated imagery, descriptions, or scene content that evokes "
    'the concept without naming it: "the wedding dress that never left the closet" does NOT '
    'express "sadness". Hypernyms, hyponyms, and category neighbors do NOT count. '
    "Judge only what is actually written. If uncertain, say not expressed."
)

# the quote rule, verbatim, turned into a "which span" question (paraphrase: the second sentence)
QUOTE_Q = (
    "Every YES must include a VERBATIM quote copied exactly from one sample (the smallest span "
    "that names the target). Which ONE of these readout spans NAMES a target concept under the "
    "STRICT rules (exact word, inflection, established synonym/alias, or faithful translation; "
    "not a derived word, fragment, or associated imagery)? If none does, choose none."
)
QUOTE_OPT = "{where}: {span}"
QUOTE_NONE = "No span names any target concept: not expressed."

TARGET_Q = "Which target concept is EXPRESSED (NAMED) in the readout?"
TARGET_OPT = "The target {t} is the one named in the readout."

# ------------------------------------------------------------ parsing the rendered user prompt

_TARGETS = re.compile(r"^targets: (\[.*\])$", re.MULTILINE)
_POS = re.compile(r"^\[position (-?\d+)\]$")
_BULLET = re.compile(r"^\s*(?:[-*•·]|\d+[.)])\s+")
_TOKEN_MARK = "Ġ▁Ċ \t"


def parse_user(user: str) -> tuple[list[str], str, list[tuple[int, list[str]]]]:
    """(targets, kind, [(pos, samples)]) from ``render_user`` output. Samples are the lines of
    each ``[position P]`` block minus the two-space indent (the renderer adds it to each sample;
    a multi-line prose sample therefore comes back as several lines, which is exactly the
    segmentation the port wants)."""
    m = _TARGETS.search(user)
    targets = [str(t) for t in json.loads(m.group(1))] if m else []
    kind = "tokens" if "top VOCABULARY TOKENS" in user.split("\n\n", 1)[0] else "prose"
    blocks: list[tuple[int, list[str]]] = []
    body = user.split("\n\n", 1)[1] if "\n\n" in user else ""
    cur: list[str] | None = None
    for line in body.split("\n"):
        pm = _POS.match(line)
        if pm:
            cur = []
            blocks.append((int(pm.group(1)), cur))
            continue
        if cur is None:
            continue
        cur.append(line[2:] if line.startswith("  ") else line)
    return targets, kind, blocks


def _core(span: str) -> str:
    """``span`` minus outer whitespace (any Unicode blank, incl. ``\\r``) and token markers."""
    prev = None
    while span != prev:
        prev, span = span, span.strip().strip(_TOKEN_MARK)
    return span


def segments(kind: str, blocks: list[tuple[int, list[str]]]) -> list[tuple[str, str]]:
    """Candidate quote spans as (where, span), readout order, deduped by span text. Each span is
    a verbatim substring of one sample line; blank lines are skipped, and so is any span whose
    core (outer blanks and token markers removed) is empty: such a span could only yield a
    blank quote, which ``quote_verified`` rejects (review fix: a real J-lens ``"\\r\\n"`` token
    rendered a ``"\\r"`` span)."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pos, lines in blocks:
        for i, line in enumerate(lines):
            # a token keeps its raw form (a leading space / "Ġ" marks a word start, which the
            # fragment rule depends on); a prose line loses its bullet marker and outer blanks
            span = line if kind == "tokens" else _BULLET.sub("", line).strip()
            if not _core(span):
                continue
            if span in seen:
                continue
            seen.add(span)
            where = f"[position {pos}] token {i + 1}" if kind == "tokens" else f"[position {pos}]"
            out.append((where, json.dumps(span, ensure_ascii=False) if kind == "tokens" else span))
    return out


def _raw_span(seg: tuple[str, str], kind: str) -> str:
    return json.loads(seg[1]) if kind == "tokens" else seg[1]


# ------------------------------------------------------------ deterministic quote narrowing


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


_INFL = ("", "s", "es", "'s", "’s", "ed", "d", "ing", "er", "est")


def narrow_quote(span: str, targets: list[str]) -> tuple[str, str]:
    """(quote, matched target). The smallest verbatim sub-span of ``span`` that is a target word
    or phrase (case-folded, simple inflection allowed); else the whole span with token markers
    stripped. Always a substring of ``span``."""
    base = _core(span) or span
    for t in sorted(targets, key=len, reverse=True):
        ft = _fold(t.strip())
        if not ft:
            continue
        # word-bounded match on the folded text; folding is length-preserving for most scripts,
        # so map back through a per-char check and fall back to the whole span if it is not
        pat = re.compile(
            r"(?<!\w)" + re.escape(ft) + "(?:" + "|".join(re.escape(x) for x in _INFL if x) + r")?(?!\w)"
        )
        fb = _fold(base)
        m = pat.search(fb)
        if m and len(fb) == len(base):
            q = base[m.start() : m.end()]
            if q and q in span:
                return q, t
        if not re.search(r"\w", ft[:1] or "a", re.ASCII) and ft in fb and len(fb) == len(base):
            i = fb.find(ft)  # CJK etc.: no word boundaries
            q = base[i : i + len(ft)]
            if q in span:
                return q, t
    return base, ""


# ------------------------------------------------------------ answer helpers (review fixes)


def _choice_probs(answers: dict, qid: str) -> dict[str, float] | None:
    """Averaged probabilities of the ``{qid}__v*`` variants; a variant that carries only a
    ``choice`` (no probability map) counts as one-hot. None when no variant landed."""
    probs = merge_choice(answers, qid)
    if probs is not None:
        return probs
    picks = [
        a["choice"]
        for key, a in answers.items()
        if (key == qid or key.startswith(f"{qid}__v")) and isinstance(a, dict) and a.get("choice")
    ]
    if not picks:
        return None
    return {p: picks.count(p) / len(picks) for p in set(picks)}


def _fallback_span_probs(segs: list[tuple[str, str]], kind: str, targets: list[str]) -> dict[str, float]:
    """Deterministic span pick when the span Choice did not land: the first span in readout
    order with a word-level target match, else the first span. Never decides ``expressed``."""
    for i, seg in enumerate(segs):
        if narrow_quote(_raw_span(seg, kind), targets)[1]:
            return {f"s{i + 1}": 1.0}
    return {"s1": 1.0}


# ------------------------------------------------------------ port


class Basic(Port):
    name = "basic"
    schema_names = ("bank_verdict",)
    # results.json rows are per ITEM: "pass" (any layer expressed), "earliest_layer", and
    # "layers" = {layer: {"expressed", "target", "quote", "quote_ok"}} (the per-cell labels).
    compare_fields = ("pass", "earliest_layer", "layers")

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        targets, kind, blocks = parse_user(user)
        segs = segments(kind, blocks)
        if not segs or not targets:
            # the family never sends an all-blank group; this is a defensive negative
            return Direct({"expressed": False, "target": "", "quote": ""})
        questions: dict[str, dict] = {
            "expressed": noul(EXPRESSED_Q, EXPRESSED_TRUE, EXPRESSED_FALSE),
        }
        opts = {f"s{i + 1}": QUOTE_OPT.format(where=w, span=s) for i, (w, s) in enumerate(segs)}
        opts[NONE_KEY] = QUOTE_NONE
        questions.update(choice_variants("quote", QUOTE_Q, opts, k=K_VARIANTS, seed=user))
        distinct = []
        for t in targets:
            if _fold(t) not in [_fold(d) for d in distinct]:
                distinct.append(t)
        if len(distinct) > 1:
            topts = {
                f"t{i + 1}": TARGET_OPT.format(t=json.dumps(t, ensure_ascii=False))
                for i, t in enumerate(distinct)
            }
            questions.update(choice_variants("target", TARGET_Q, topts, k=K_VARIANTS, seed=user))
        return JevCall(
            verbatim_state(system, user),
            questions,
            {"targets": targets, "distinct": distinct, "kind": kind, "segments": segs},
        )

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        # a missing noul is a failed judge call (unjudged cell), exactly as upstream
        p_yes = merge_noul(answers, "expressed")
        if p_yes is None:
            return None
        ctx = call.ctx
        segs = ctx["segments"]
        order = [f"s{i + 1}" for i in range(len(segs))]
        # the span choice only fills the (unscored-beyond-verification) quote, so a missing or
        # probability-less span answer must not drop an otherwise judged cell (review fix)
        qprobs = _choice_probs(answers, "quote")
        quote_fallback = qprobs is None
        if quote_fallback:
            qprobs = _fallback_span_probs(segs, ctx["kind"], ctx["targets"])
        expressed = p_yes > EXPRESSED_THRESHOLD
        span_key = argmax({k: qprobs.get(k, 0.0) for k in order}, order)
        target = quote = ""
        tprobs = None
        if expressed:
            span = _raw_span(segs[int(span_key[1:]) - 1], ctx["kind"])
            quote, matched = narrow_quote(span, ctx["targets"])
            distinct = ctx["distinct"]
            if len(distinct) > 1:
                tprobs = _choice_probs(answers, "target")
                torder = [f"t{i + 1}" for i in range(len(distinct))]
                target = distinct[int(argmax(tprobs, torder)[1:]) - 1] if tprobs else matched
            else:
                target = matched or distinct[0]
        return {
            "expressed": expressed,
            "target": target,
            "quote": quote,
            "_jev": jev_meta(
                answers,
                p_expressed=round(p_yes, 4),
                p_none=None if quote_fallback else round(qprobs.get(NONE_KEY, 0.0), 4),
                quote_probs=None if quote_fallback else {k: round(v, 4) for k, v in qprobs.items()},
                span_pick=span_key,
                quote_fallback=quote_fallback,
                target_probs={k: round(v, 4) for k, v in tprobs.items()} if tprobs else None,
            ),
        }


PORTS = [Basic()]

"""hallucination (v5c-chat + v5c-chat-verify-v1): two free-text span/claim judges -> typed segments.

Original pipeline (``wsbench.evals.hallucination``), one cell = (item, layer, read site) with its
first k <= 3 non-empty readouts (k = 1 for a token lens, whose summarizer output — under the Jev
route, the rendered token bag — is the single readout):

* Stage 1, schema ``hallucination_ontopic_spans``: per readout ``{idx, kind, spans[{text, type,
  why}], rationale}``. The family keeps a span only if it is verbatim (normalised, >= 3 chars) in
  its own readout; class = ``hallucinated`` if any verified ``wrong`` span, else ``generic`` if
  kind is generic/empty, else ``off_topic`` if any verified junk span, else ``consistent``.
  Headline ``hallucination_rate`` = hallucinated / (hallucinated + off_topic + consistent).
* Stage 2, schema ``hallucination_chat_verify`` (extras only): given each readout's established
  false spans, per readout ``{idx, kind, claims[{quote, status, why}], rationale}``; the family
  tallies verified quotes by status, skipping quotes that overlap an established false span.

Jev port (PROTOCOL DEVIATION, free-text stage restructured per PORTING rule 5): each readout is
segmented DETERMINISTICALLY (:func:`segments`: lines -> sentences -> clauses at ``;`` / dashes,
comma chunks only for sentences over 25 words; token bags in chunks of 8 items; at most 8
segments per readout; segments shorter than 3 normalised characters are never asked because the
family could not verify them anyway). One Jev request per original call; the state is the
verbatim ``(system, user)`` pair. A request whose estimated size exceeds :data:`TOKEN_BUDGET`
(Jev's context is 32k tokens for state + questions, and every segment question repeats the long
verbatim criteria) is shrunk deterministically by :func:`fit`: adjacent segments of the readout
with the most segments are merged (identical readouts together), and only when every readout is
down to one segment do the segment questions drop to K = 1. ``_jev.k_segments`` records K.

* Stage 1 questions: per readout ``k{i}`` (Choice specific / generic / empty, criteria = the
  prompt's kind definitions verbatim); per segment ``s{i}_{j}`` (Choice wrong / off_topic / none,
  criteria = the prompt's ``type "wrong"`` block, ``type "off_topic"`` block and ``Do NOT mark``
  block, each verbatim; the question sentence is the prompt's ``spans:`` line verbatim plus a
  pointer to the segment). Each Choice is asked in K cyclic rotations of the option order
  (:func:`variants`) and the probabilities are averaged. A segment
  whose argmax is ``wrong`` / ``off_topic`` becomes a span whose ``text`` is the segment itself
  (a verbatim substring of the readout, so the family's verbatim check always passes).
* Stage 2 questions: per segment not already covered by an established-false span ``c{i}_{j}``
  (Choice true / unverifiable / disputed / off_topic / none; the four statuses verbatim, ``none``
  = the prompt's "NOT claims" sentence). A non-``none`` pick becomes one claim quoting the
  segment. Segments that the family's own overlap rule would skip are not asked; a segment that
  CONTAINS an established-false span (e.g. from a different stage-1 judge) is asked on its
  remainder pieces instead (see :func:`carve`).

``why`` / ``rationale`` are deterministic strings (the family never reads them); stage-2 ``kind``
is derived from the claims (the family never reads it either). Every raw answer and the
averaged probabilities are kept under ``_jev``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import (
    Direct,
    JevCall,
    Port,
    argmax,
    choice,
    jev_meta,
    merge_choice,
    verbatim_state,
)

K_VARIANTS = 3
MAX_SEGMENTS = 8  # per readout; the tail is merged into the last segment
BAG_CHUNK = 8  # token-bag items per segment
LONG_SENTENCE_WORDS = 25  # only sentences longer than this are split at commas
COMMA_MIN_WORDS = 6
# Jev's context limit is 32k tokens for state + questions together; each segment question
# repeats the long verbatim criteria (~850 tokens per variant), so a cell with many segments
# would overflow (3 readouts x 8 segments ~ 72k tokens). Requests are kept under this estimate
# (billed tokens ~ len(json)/4 for ASCII; measured 10,598 billed vs 10,754 estimated) by
# deterministically coarsening segments (see :func:`fit`).
TOKEN_BUDGET = 24_000

KIND_ORDER = ("specific", "generic", "empty")
SPAN_ORDER = ("wrong", "off_topic", "none")
STATUS_ORDER = ("true", "unverifiable", "disputed", "off_topic", "none")

# ---------------------------------------------------------------- normalisation (family rule)

_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "«": '"', "»": '"'})  # noqa: RUF001


def norm(s: str) -> str:
    """Same normalisation as ``wsbench.evals.hallucination.judge.normalize_ws``."""
    return _WS.sub(" ", s.translate(_QUOTES)).strip().lower()


def _askable(seg: str) -> bool:
    return len(norm(seg)) >= 3 and re.search(r"\w", seg) is not None


# ---------------------------------------------------------------- deterministic segmentation

_SENT_CUT = re.compile(r"(?<=[.!?…])[\"'”’)\]]*\s+")
_CLAUSE_CUT = re.compile(r"\s*;\s+|\s+[—–]\s+|\s+-{1,2}\s+|—")
_COMMA_CUT = re.compile(r",\s+")
_TRIM = " \t\r\n-*•·>"


def _nwords(s: str) -> int:
    """Whitespace-separated tokens that contain a word character ("e.g." is one word)."""
    return sum(1 for w in s.split() if re.search(r"\w", w))


def _cut(text: str, s: int, e: int, pat: re.Pattern[str], min_words: int) -> list[tuple[int, int]]:
    """Split text[s:e] at matches of ``pat``, greedily, only where the piece on the left and
    everything on the right both have >= ``min_words`` words."""
    out: list[tuple[int, int]] = []
    cur = s
    for m in pat.finditer(text, s, e):
        if m.start() <= cur:
            continue
        if _nwords(text[cur : m.start()]) >= min_words and _nwords(text[m.end() : e]) >= min_words:
            out.append((cur, m.start()))
            cur = m.end()
    out.append((cur, e))
    return out


def _trimmed(text: str, s: int, e: int) -> tuple[int, int]:
    while s < e and text[s] in _TRIM:
        s += 1
    while e > s and text[e - 1] in _TRIM + ".,;:":
        e -= 1
    return s, e


def _spans(readout: str) -> list[tuple[int, int]]:
    text = readout
    spans: list[tuple[int, int]] = []
    if text.count(" | ") >= 2:  # a rendered token bag ("tok (score) | tok (score) | ...")
        pos = [0]
        for m in re.finditer(r" \| ", text):
            pos.append(m.start())
            pos.append(m.end())
        pos.append(len(text))
        items = [(pos[i], pos[i + 1]) for i in range(0, len(pos), 2)]
        for i in range(0, len(items), BAG_CHUNK):
            chunk = items[i : i + BAG_CHUNK]
            spans.append((chunk[0][0], chunk[-1][1]))
    else:
        off = 0
        for line in text.split("\n"):
            ls, le = off, off + len(line)
            off = le + 1
            if not line.strip():
                continue
            for ss, se in _cut(text, ls, le, _SENT_CUT, 2):
                for cs, ce in _cut(text, ss, se, _CLAUSE_CUT, 3):
                    if _nwords(text[cs:ce]) > LONG_SENTENCE_WORDS:
                        spans.extend(_cut(text, cs, ce, _COMMA_CUT, COMMA_MIN_WORDS))
                    else:
                        spans.append((cs, ce))
    spans = [_trimmed(text, s, e) for s, e in spans]
    spans = [(s, e) for s, e in spans if e > s and _askable(text[s:e])]
    if len(spans) > MAX_SEGMENTS:
        spans = spans[: MAX_SEGMENTS - 1] + [(spans[MAX_SEGMENTS - 1][0], spans[-1][1])]
    return spans


def segments(readout: str, spans: list[tuple[int, int]] | None = None) -> list[str]:
    """Deterministic, verbatim, de-duplicated segments of one readout (see module docstring).
    Every segment is a substring of ``readout`` of >= 3 normalised characters. ``spans``
    overrides the default segmentation (e.g. a :func:`coarsen`-ed one)."""
    out: list[str] = []
    seen: set[str] = set()
    for s, e in _spans(readout) if spans is None else spans:
        seg = readout[s:e]
        if norm(seg) not in seen:
            seen.add(norm(seg))
            out.append(seg)
    return out


def coarsen(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge ONE pair of adjacent segments: the pair with the shortest combined extent (ties:
    the earliest). The merged segment is still one contiguous, verbatim substring of the
    readout (from the first piece's start to the second's end)."""
    if len(spans) < 2:
        return list(spans)
    j = min(range(len(spans) - 1), key=lambda i: (spans[i + 1][1] - spans[i][0], i))
    return spans[:j] + [(spans[j][0], spans[j + 1][1])] + spans[j + 2 :]


def est_tokens(state: dict, questions: dict) -> int:
    """Conservative request-size estimate: ASCII chars / 4 + one token per non-ASCII char."""
    body = json.dumps({"state": state, "questions": questions}, ensure_ascii=False)
    n_ascii = sum(1 for c in body if ord(c) < 128)
    return n_ascii // 4 + (len(body) - n_ascii)


def fit(
    samples: list[str], make: Any, state: dict, budget: int = TOKEN_BUDGET
) -> tuple[dict, list[list[tuple[int, int]]], int]:
    """Build questions with ``make(spans_per_readout, k)`` and, while the request is over
    ``budget``, coarsen the readout with the most segments (ties: lowest idx; every identical
    readout is coarsened with it); if every readout
    is down to one segment, fall back to K=1 for the segment questions. Deterministic.
    Returns (questions, spans used, K used)."""
    spans = [_spans(r) for r in samples]
    k = K_VARIANTS
    while True:
        questions = make(spans, k)
        if est_tokens(state, questions) <= budget:
            return questions, spans, k
        i = max(range(len(spans)), key=lambda j: (len(spans[j]), -j)) if spans else 0
        if spans and len(spans[i]) > 1:
            # identical readouts are coarsened together, so they keep identical segments and a
            # repeated wrong clause is still revoked by the family (lens samples often repeat)
            for j in range(len(spans)):
                if samples[j] == samples[i]:
                    spans[j] = coarsen(spans[j])
        elif k > 1:
            k = 1
        else:
            return questions, spans, k  # one segment per readout at K=1: nothing left to cut


def _cjk(s: str) -> bool:
    """Kana, CJK ideographs or Hangul: scripts written without spaces (``_nwords`` == 1)."""
    return re.search("[぀-ヿ㐀-鿿가-힯]", s) is not None


def carve(seg: str, falses: list[str]) -> list[str]:
    """Stage-2 pieces of ``seg`` that the family's tally would NOT skip as already false.

    The family skips a quote q when any established-false span x has ``x in q or q in x``
    (normalised). A segment inside a false span is dropped; a segment containing a false span is
    cut around it (verbatim remainder pieces with >= 2 words, or any CJK piece of >= 3
    normalised characters, since those scripts have no spaces), recursively."""
    nq = norm(seg)
    xs = [norm(x) for x in falses if norm(x)]
    if not any(x in nq or nq in x for x in xs):
        return [seg]
    if any(nq in x for x in xs):
        return []
    for x in xs:
        if x not in nq:
            continue
        pat = r"\s+".join(re.escape(w) for w in x.split(" "))
        m = re.search(pat, seg.translate(_QUOTES), re.IGNORECASE)
        if m is None:
            return []
        out: list[str] = []
        for s, e in ((0, m.start()), (m.end(), len(seg))):
            s, e = _trimmed(seg, s, e)
            piece = seg[s:e]
            if e > s and _askable(piece) and (_nwords(piece) >= 2 or _cjk(piece)):
                out.extend(carve(piece, falses))
        return out
    return []


# ---------------------------------------------------------------- reading the rendered prompt

_READOUT = re.compile(r'<readout idx="(\d+)">\n(.*?)\n</readout>', re.S)
_FALSES = re.compile(r"Established FALSE spans of readout (\d+):\n((?:  (?:- .*|\(none\))(?:\n|$))*)")


_BELOW = re.compile(r"\nBelow are (\d+) independent readouts of that one activation\.")


def _tail(user: str) -> tuple[str, list[str]] | None:
    """(text after the response, readouts in idx order) for the rendered prompt, or None.

    The readout blocks follow the LAST ``</response>`` unless a readout itself contains that
    string; then earlier occurrences are tried, and a candidate is accepted only when its blocks
    are idx 0..k-1 with k = the prompt's own "Below are {k} independent readouts" count."""
    starts = [m.start() for m in re.finditer(re.escape("</response>"), user)]
    for st in reversed(starts):
        tail = user[st:]
        below = _BELOW.search(tail)
        if below is None:
            continue
        k = int(below.group(1))
        found = [(int(m.group(1)), m.group(2)) for m in _READOUT.finditer(tail, below.end())]
        idx = [i for i, _ in found]
        if found and idx[:k] == list(range(k)):
            return tail, [t for _, t in found[:k]]
    return None


def readouts_in(user: str) -> list[str] | None:
    """The readouts exactly as rendered by ``samples_block`` (in idx order), or None."""
    t = _tail(user)
    return None if t is None else t[1]


def falses_in(user: str, k: int) -> list[list[str]] | None:
    t = _tail(user)
    if t is None:
        return None
    tail = t[0]
    out: dict[int, list[str]] = {}
    for m in _FALSES.finditer(tail):
        if int(m.group(1)) in out:  # first block per idx (a readout could quote the header)
            continue
        spans: list[str] = []
        # split on "\n" only: json.dumps(ensure_ascii=False) leaves U+2028 / U+0085 raw, and
        # str.splitlines() would cut a span there
        for line in m.group(2).split("\n"):
            line = line.strip()
            if line.startswith("- "):
                try:
                    spans.append(str(json.loads(line[2:])))
                except ValueError:
                    spans.append(line[2:].strip('"'))
        out[int(m.group(1))] = spans
    if sorted(out) != list(range(k)):
        return None
    return [out[i] for i in range(k)]


def _slice(text: str, start: str, end: str) -> str:
    """text from ``start`` (inclusive) to ``end`` (exclusive), stripped; ValueError if absent."""
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j].strip()


def span_criteria(user: str) -> tuple[str, dict[str, str], dict[str, str]]:
    """(spans question line, span-type options, kind options), all verbatim from the prompt."""
    spans_line = _slice(user, "- spans: ", ", each with a type:") + ", each with a type."
    opts = {
        "wrong": _slice(user, '  type "wrong" — ', '\n\n  type "off_topic"'),
        "off_topic": _slice(user, '  type "off_topic" — ', "\n\nDo NOT mark"),
        "none": _slice(user, "Do NOT mark (neither type):", "\n\nReport, as JSON"),
    }
    return spans_line, opts, kind_criteria(user)


def kind_criteria(user: str) -> dict[str, str]:
    line = _slice(user, '- kind: "specific"', "\n")[len("- kind: ") :]
    parts = line.split("; ")
    if len(parts) != 3 or not all(p.startswith(f'"{k}"') for p, k in zip(parts, KIND_ORDER)):
        raise ValueError("kind line not as expected")
    return dict(zip(KIND_ORDER, parts, strict=True))


def claim_criteria(user: str) -> tuple[str, dict[str, str], str]:
    """(claims definition, status options, rules), verbatim from the verify prompt."""
    claims_def = _slice(user, "- claims: ", " For each:")
    opts = {
        "true": _slice(user, '    "true" — ', '\n    "unverifiable"'),
        "unverifiable": _slice(user, '    "unverifiable" — ', '\n    "disputed"'),
        "disputed": _slice(user, '    "disputed" — ', '\n    "off_topic"'),
        "off_topic": _slice(user, '    "off_topic" — ', "\n  - why:"),
        # paraphrase: the key and the first sentence are ours, the second is verbatim
        "none": "Not a claim: this part makes no specific assertion. Generic phrases, task "
        "descriptions, hedging, repetition, formatting and broken fragments are NOT claims; a "
        "readout may have zero claims.",
    }
    rules = _slice(user, "Rules:\n", "\n\nReport, as JSON")
    return claims_def, opts, rules


# ---------------------------------------------------------------- questions


def variants(qid: str, instructions: str, options: dict[str, str], k: int) -> dict[str, dict]:
    """``k`` copies of one Choice question in CYCLIC ROTATIONS of the option order (variant 0 =
    the prompt order; variant v starts at option ``v * n // k``). Unlike ``base.choice_variants``
    (seeded shuffles: only 54% of this port's question groups got 3 distinct orders, and 55%
    repeated v0's first option), every variant order is distinct for k <= n, and with n = k = 3
    each option sits in each position exactly once. Keys never change; merge with
    ``merge_choice`` exactly as before."""
    keys_ = list(options)
    n = len(keys_)
    out: dict[str, dict] = {}
    for v in range(k):
        r = (v * n // k) % n
        order = keys_[r:] + keys_[:r]
        out[f"{qid}__v{v}"] = choice(instructions, {o: options[o] for o in order})
    return out



def _head(i: int, readout: str, seg: str | None = None) -> str:
    h = f'Readout idx="{i}":\n{readout}'
    if seg is not None:
        h += f'\n\nThe part of readout idx="{i}" under review (copied from it):\n"{seg}"'
    return h


def _pick(answers: dict, qid: str, order: tuple[str, ...]) -> tuple[str, dict[str, float]] | None:
    probs = merge_choice(answers, qid)
    if probs is None:
        return None
    return argmax(probs, order), {k: round(v, 4) for k, v in probs.items()}


# ---------------------------------------------------------------- stage 1


class HallucinationSpans(Port):
    name = "hallucination"
    schema_names = ("hallucination_ontopic_spans",)
    compare_fields = ("verdict",)  # per readout: verdict[i]["class"] (+ kind, wrong, off_topic)

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        samples = readouts_in(user)
        if samples is None:
            return Direct(None)
        try:
            spans_line, span_opts, kind_opts = span_criteria(user)
            kind_line = _slice(user, '- kind: "specific"', "\n")
        except ValueError:
            return Direct(None)
        state = verbatim_state(system, user)
        kind_qs: dict[str, dict] = {}
        for i, r in enumerate(samples):
            kind_qs.update(
                variants(
                    f"k{i}",
                    f"{_head(i, r)}\n\nFor EACH readout, report:\n\n{kind_line}\n\nWhich kind is "
                    f'readout idx="{i}"?',
                    kind_opts,
                    k=K_VARIANTS,
                )
            )
        segs: list[list[str]] = []

        def make(spans: list[list[tuple[int, int]]], k: int) -> dict[str, dict]:
            questions = dict(kind_qs)
            segs[:] = [segments(r, sp) for r, sp in zip(samples, spans, strict=True)]
            for i, r in enumerate(samples):
                for j, seg in enumerate(segs[i]):
                    questions.update(
                        variants(
                            f"s{i}_{j}",
                            f"{_head(i, r, seg)}\n\n{spans_line}\n\nDoes this part of readout "
                            f'idx="{i}" contain such a span, and of which type? Choose "none" if '
                            'nothing in this part may be marked. If it contains both a "wrong" '
                            'and an "off_topic" span, choose "wrong".',
                            span_opts,
                            k=k,
                        )
                    )
            return questions

        questions, _, k_used = fit(samples, make, state)
        return JevCall(state, questions, {"samples": samples, "segments": segs, "k_segments": k_used})

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        out: list[dict[str, Any]] = []
        meta: list[dict[str, Any]] = []
        for i, _ in enumerate(call.ctx["samples"]):
            k = _pick(answers, f"k{i}", KIND_ORDER)
            if k is None:
                return None
            kind, kprobs = k
            spans = []
            seg_meta = []
            for j, seg in enumerate(call.ctx["segments"][i]):
                p = _pick(answers, f"s{i}_{j}", SPAN_ORDER)
                if p is None:
                    return None
                pick, probs = p
                seg_meta.append({"text": seg, "pick": pick, "probs": probs})
                if pick != "none":
                    spans.append({"text": seg, "type": pick, "why": f"jev p={probs[pick]:.2f}"})
            n_w = sum(s["type"] == "wrong" for s in spans)
            n_o = len(spans) - n_w
            out.append(
                {
                    "idx": i,
                    "kind": kind,
                    "spans": spans,
                    "rationale": f"jev: kind={kind} (p={kprobs.get(kind, 0):.2f}); "
                    f"{n_w} wrong and {n_o} off-topic of {len(seg_meta)} segments.",
                }
            )
            meta.append({"kind_probs": kprobs, "segments": seg_meta})
        return {
            "samples": out,
            "_jev": jev_meta(answers, readouts=meta, k_segments=call.ctx.get("k_segments")),
        }


# ---------------------------------------------------------------- stage 2


class HallucinationVerify(Port):
    name = "hallucination_verify"
    schema_names = ("hallucination_chat_verify",)
    compare_fields = ("verdict",)  # per readout: verdict[i]["claims"] (the stage-2 tally)

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        samples = readouts_in(user)
        if samples is None:
            return Direct(None)
        falses = falses_in(user, len(samples))
        if falses is None:
            return Direct(None)
        try:
            claims_def, opts, rules = claim_criteria(user)
        except ValueError:
            return Direct(None)
        state = verbatim_state(system, user)
        pieces: list[list[str]] = []

        def make(spans: list[list[tuple[int, int]]], k: int) -> dict[str, dict]:
            questions: dict[str, dict] = {}
            pieces.clear()
            for i, r in enumerate(samples):
                ps: list[str] = []
                for seg in segments(r, spans[i]):
                    for p in carve(seg, falses[i]):
                        if norm(p) not in {norm(x) for x in ps}:
                            ps.append(p)
                pieces.append(ps)
                for j, seg in enumerate(ps):
                    questions.update(
                        variants(
                            f"c{i}_{j}",
                            f"{_head(i, r, seg)}\n\n{claims_def}\n\nDoes this part of readout "
                            f'idx="{i}" make such a claim? If it does, choose its status; if it '
                            'makes no specific claim, choose "none".\n\n' + rules,
                            opts,
                            k=k,
                        )
                    )
            return questions

        questions, _, k_used = fit(samples, make, state)
        if not questions:  # nothing left to verify: every readout has zero claims
            return Direct(self._result([[] for _ in samples], {}, []))
        return JevCall(state, questions, {"samples": samples, "pieces": pieces, "k_segments": k_used})

    @staticmethod
    def _result(claims: list[list[dict]], answers: dict, meta: list, k_segments: int | None = None) -> dict:
        samples = []
        for i, cl in enumerate(claims):
            specific = any(c["status"] != "off_topic" for c in cl)
            samples.append(
                {
                    "idx": i,
                    "kind": "specific" if specific else "generic",  # never read by the family
                    "claims": cl,
                    "rationale": f"jev: {len(cl)} claim(s) among the deterministic segments.",
                }
            )
        return {"samples": samples, "_jev": jev_meta(answers, readouts=meta, k_segments=k_segments)}

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        claims: list[list[dict]] = []
        meta: list[list[dict]] = []
        for i, ps in enumerate(call.ctx["pieces"]):
            cl: list[dict] = []
            m: list[dict] = []
            for j, seg in enumerate(ps):
                p = _pick(answers, f"c{i}_{j}", STATUS_ORDER)
                if p is None:
                    return None
                pick, probs = p
                m.append({"text": seg, "pick": pick, "probs": probs})
                if pick != "none":
                    cl.append({"quote": seg, "status": pick, "why": f"jev p={probs[pick]:.2f}"})
            claims.append(cl)
            meta.append(m)
        return self._result(claims, answers, meta, call.ctx.get("k_segments"))


PORTS = [HallucinationSpans(), HallucinationVerify()]

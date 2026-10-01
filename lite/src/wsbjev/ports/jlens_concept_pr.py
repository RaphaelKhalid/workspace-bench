"""jlens_concept_pr (jlens-pr-v2): three judged stages, three schemas. Jev port.

Original pipeline (``wsbench/evals/jlens_concept_pr/judge.py``; judge of record Gemini 3.8 Flash):

* Stage A, schema ``concepts`` = ``{"concepts": [str]}``: one call per cell with text.
  SYSTEM = ``STAGE_A_SYSTEM`` (break the lens text into UNIQUE short noun-phrase concepts, merge
  duplicates / near-duplicates, ignore bullets / emphasis / boilerplate connectives but keep
  evaluative / affirmative markers), USER = ``"Text:\\n{text}"``. ``parse_stage_a`` dedups the list
  case/whitespace-insensitively; that list is what Stages B and P grade.
* Stage B (+ foil), schema ``grades`` = ``{"grades": [{concept, grade in|partial|out}]}``: one call
  per CONTENT J-lens token, USER = ``"Token: {repr}\\n\\nConcepts:\\n1. c1\\n2. c2 ..."``; every
  listed concept graded exactly once (``parse_stage_b`` rejects drift, duplicates, gaps).
* Stage P (+ pfoil), schema ``support`` = same shape: one call per <= 60-concept chunk with the
  cell's full content-token set, USER = ``"Tokens: 'a', 'b', ...\\n\\nConcepts:\\n..."``.

The scorer (``concept_pr.score_item``) reads only the grade VALUES: precision = mean Stage-P grade
over the concepts (headline), recall@10 = mean over content tokens of the hypergeometric
expected-max Stage-B grade, raw_recall = mean max. The concept STRINGS matter only as the
denominator (how many concepts, how they are cut) and as what B/P grade.

Jev port (state = the verbatim ``(system, user)`` pair in every stage):

* **Stage A (PROTOCOL DEVIATION, free-text stage restructured).** Jev cannot write concept
  strings, so the port cuts the text DETERMINISTICALLY into candidate noun phrases
  (:func:`candidates`): samples -> clauses at punctuation -> maximal runs of content words
  between closed-class function words (a RAKE-style chunker that keeps ``X of Y`` together and
  keeps ``no`` / ``not`` prefixes), plus quoted spans whole and each emoji / checkmark as its own
  candidate. Candidates whose inflection-folded word sets are equal are merged without asking
  (``Merge duplicates and near-duplicates (inflections ...)``). Then ONE typed Choice per remaining
  candidate applies the Stage A rules: ``new`` (a distinct concept: list it), ``skip`` (only a list
  bullet, markdown emphasis or boilerplate connective: ignore it) or ``same_<j>`` (a duplicate or
  near-duplicate / restatement of earlier candidate j: merge), where the offered j are the <= 3
  lexically closest earlier candidates. Merged clusters are written the way the prompt's own
  example writes merges: members joined with ``" / "`` (``"elderly widow / older adult"``).
  Evaluative / affirmative markers named by the prompt (``Yes``, ``Correct Answer``, ``Final Answer``,
  checkmarks, emoji) are always listed; the prompt's own emoji names are used for ✅ ✔ ✓ ("correct /
  confirmed answer") and 🎉 🥳 ("celebration").
* **Stage B / foil.** One Choice (``in`` / ``partial`` / ``out``) per listed concept inside ONE
  request; criteria are the prompt's grade definitions verbatim (the leading definition clause
  of each bullet; the emoji sentence is added when the token carries an emoji; the worked
  examples stay in the verbatim state). K option-order variants by a per-request question budget.
* **Stage P / pfoil.** Same, with Stage P's own definitions verbatim (including "A concept that
  says more than the token still counts as in — the token has to be in the concept, not equal to
  it") and the "grade the BEST correspondence between that concept and ANY token in the set"
  instruction.

Grades are argmax over the variant-averaged probabilities (ties by the original order in,
partial, out); every probability is kept under ``_jev``. Concept strings in B/P output are copied
verbatim from the listing, so the family parsers match them exactly.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from typing import Any

from wsbench.evals.jlens_concept_pr.concept_pr import _stems, has_emoji

from .base import (
    Direct,
    JevCall,
    Port,
    argmax,
    choice_variants,
    jev_meta,
    verbatim_state,
)

# ------------------------------------------------------------------ budgets

# Questions per request (K option-order variants are added while they fit). A request must stay
# well under Jev's 32k-token context; see ports-notes/jlens_concept_pr.md for the arithmetic.
A_QUESTION_BUDGET = 60
B_QUESTION_BUDGET = 60
P_QUESTION_BUDGET = 60
MAX_K = 3
MAX_DUP_OPTIONS = 3
MAX_CLUSTER_SHOWN = 5
MAX_PHRASE_WORDS = 6
TOKEN_LIMIT = 31000  # on the (conservative, ~+12%) estimate: ~27.5k real tokens; Jev context is 32k
CHARS_PER_TOKEN = 3.5
PER_QUESTION_TOKENS = 30

GRADES = ("in", "partial", "out")

# ------------------------------------------------------------------ verbatim criteria

# STAGE_B_SYSTEM bullets (leading definition clauses, verbatim)
B_IN = "the concept has the token, modulo word inflection / casing / translation"
B_PARTIAL = "the concept has a close relative of the token"
B_OUT = "everything else, including words the concept does not contain"
B_EMOJI = (
    "Emoji are words: an emoji token matches a concept that names the same thing in words "
    '("✅" matches "correct answer"; "🎉" matches "celebration"), and emoji with the same meaning '
    'are the same token ("🎉" and "🥳" both match "celebration"; "✅", "✔" and "✓" all match '
    '"confirmed / correct").'
)
B_EMOJI_PARTIAL = 'token "😊" is partial for "gratitude"'

# STAGE_P_SYSTEM bullets (leading definition sentences, verbatim)
P_IN = (
    "the concept has one of the tokens, modulo word inflection / casing / translation (tokens "
    '"accessing", "访问" are in for the concept "access pattern"). A concept '
    "that says more than the token still counts as in — the token has to be in the concept, not "
    "equal to it"
)
P_PARTIAL = (
    "the concept has a close relative of one of the tokens — the token names the concept's "
    "category, a sibling, or a part of it"
)
P_OUT = "everything else — no token is in the concept and none is a close relative of it"
P_EMOJI = (
    "Emoji are words: an emoji token matches a concept that names the same thing in words "
    '("✅" is in for "correct answer"; "🎉" for "celebration"), and emoji with the same meaning are '
    'the same token ("🎉" and "🥳" both match "celebration"; "✅", "✔" and "✓" all match '
    '"confirmed / correct").'
)

# STAGE_A_SYSTEM rules, split per option (paraphrased only to make each self-contained)
A_NEW = "a distinct concept the text asserts (a thing, property, action or entity): list it"
A_SKIP = (
    "only a list bullet, markdown emphasis or boilerplate connective (not an evaluative or "
    "affirmative marker): ignore it"
)
A_SAME = (
    'a duplicate or near-duplicate (inflection, restatement) of candidate {j}, "{cj}": merge into '
    "one concept"
)

# ------------------------------------------------------------------ Stage A: deterministic cut

# closed-class words that END a candidate run (articles, pronouns, auxiliaries, prepositions,
# conjunctions, hedging / degree adverbs, quantifiers, wh-words). "of" / "&" JOIN two content runs.
_STOP = frozenset(
    """
a an the this that these those it its it's they them their theirs he him his she her hers we us
our ours you your yours i me my mine itself themselves himself herself ourselves yourself
is are was were be been being am do does did doing done have has had having will would shall
should can could may might must 's
and or but nor so yet if then else than as because since while whereas although though unless
until whether whereby
in on at to for from by with without within into onto over under about above below between among
through throughout during before after around across along against toward towards upon via per
beyond behind beside besides near off out up down like unlike
very really quite rather just only also even still already again perhaps possibly potentially
likely probably maybe often usually typically generally mostly mainly largely primarily
especially particularly specifically actually basically essentially simply clearly seemingly
somewhat slightly highly strongly heavily deeply fully partly apparently presumably
some any many much more most less least few fewer several each every all both either neither
other another such same own various certain
what which who whom whose where when why how whatever whichever whoever
there here now thus hence therefore however indeed instead e.g i.e etc eg ie vs
suggests indicates reflects represents involves describes seems appears refers implies signals
contains includes becomes remains tends focuses relates concerns emphasizes highlights expresses
conveys denotes captures encodes mentions discusses
""".split()
)
_JOIN = frozenset({"of", "&"})
_PREFIX = frozenset({"no", "not", "non"})
# the prompt: evaluative / affirmative markers "each name a concept ... and must be listed"
_MARKERS = frozenset({"yes", "correct answer", "final answer", "correct", "confirmed"})
# the prompt's own names for these emoji (STAGE_A_SYSTEM / STAGE_B_SYSTEM examples)
_EMOJI_NAME = {
    "✅": "correct / confirmed answer",
    "✔": "correct / confirmed answer",
    "✓": "correct / confirmed answer",
    "☑": "correct / confirmed answer",
    "🎉": "celebration",
    "🥳": "celebration",
}

# Review fix (Sep 30): the prompt names ONE concept for the correctness markers ('a checkmark or
# emoji (✅, ✔, 🎉), "Correct Answer", ... each name a concept ("correct / confirmed answer", ...)').
# Forced markers are never asked, so Jev could not merge them; "✅ Correct Answer ... correct ✔"
# became three concepts (and three "in" grades against a ✅ / "correct" token, inflating precision).
# They now share one identity and are listed once (first spelling kept).
_CORRECT_MARKERS = frozenset({"correct answer", "correct", "confirmed", "correct / confirmed answer"})
_CORRECT_KEY = frozenset({"<correct / confirmed answer>"})
# Review fix: an upper-case acronym is content, not the function word it spells ("US economy",
# "IT department", "WHO guidelines" lost their head noun).
_ACRONYMS = frozenset({"US", "IT", "WHO", "AM", "PM", "OR", "AND", "NOT", "IF", "DO"})

_JOINERS = frozenset({chr(0xFE0F), chr(0x200D)})  # emoji variation selector, zero-width joiner
_KEYCAP = chr(0x20E3)
_EXTRA_EMOJI = frozenset({0x3030, 0x303D, 0x3297, 0x3299, 0x2934, 0x2935})
_SAMPLE_SEP = "\n---\n"
_BULLET = re.compile(r"^\s*(?:[-*+•·▪►]|\d{1,3}[.)]|[a-zA-Z][.)](?=\s))\s+", re.M)
_HEADER = re.compile(r"^\s*(?:#{1,6}|>+)\s*", re.M)
_EMPH = re.compile(r"\*\*|__|\*|`+|~~")
_QUOTE = re.compile(r"\"([^\"\n]{1,80})\"|“([^”\n]{1,80})”|(?<![\w])'([^'\n]{1,60})'(?![\w])|‘([^’\n]{1,60})’")
_CLAUSE = re.compile(
    r"\n|[;!?()\[\]{}<>|—–…•·]|[.,:](?=\s|$)|\s[-/]\s|\s-{2,}\s|=>|->|→|。|，|；|：|、"
)
_WORDTOK = re.compile(r"\w(?:[\w&'’./+#-]*\w)?[+#]*|&", re.UNICODE)
_CJK_RUN = re.compile(r"[㐀-鿿぀-ヿ가-힯]")


def _is_emoji_char(ch: str) -> bool:
    """Pictographs only (dingbats / misc symbols / emoji planes), not ° © ™ or box drawing."""
    cp = ord(ch)
    # review fix: ⭐ ⬆ ⬛ (U+2Bxx), ⌛ ⏰ ⏳ (U+23xx) and 〰 ㊗ are emoji too; they were dropped as
    # phrase breaks although the prompt says every emoji must be listed
    return ch in _EMOJI_NAME or (
        unicodedata.category(ch) == "So"
        and (
            0x2600 <= cp <= 0x27BF
            or cp >= 0x1F000
            or 0x2300 <= cp <= 0x23FF
            or 0x2B00 <= cp <= 0x2BFF
            or cp in _EXTRA_EMOJI
        )
    )


def _is_stop(t: str) -> bool:
    return t.lower() in _STOP and t not in _ACRONYMS


def _emoji_end(s: str, i: int) -> int:
    """End of the emoji sequence starting at ``s[i]``: modifiers / variation selectors, ZWJ
    sequences (👨‍👩‍👧 is one family emoji) and regional-indicator pairs (🇺🇸 is one flag)."""
    j = i + 1
    if 0x1F1E6 <= ord(s[i]) <= 0x1F1FF and j < len(s) and 0x1F1E6 <= ord(s[j]) <= 0x1F1FF:
        return j + 1
    while j < len(s):
        c = s[j]
        if unicodedata.category(c) in ("Mn", "Me", "Sk") or c == chr(0xFE0F):
            j += 1
        elif c == chr(0x200D) and j + 1 < len(s) and _is_emoji_char(s[j + 1]):
            j += 2
        elif c == chr(0x200D):
            j += 1
        else:
            break
    return j


def _clean_word(w: str) -> str:
    w = re.sub(r"['’]s$", "", w)
    return w.strip("'’.-/")


def _stem(w: str) -> str:
    """Inflection fold: the shortest candidate stem of the lower-cased word (upstream ``_stems``)."""
    low = w.lower()
    return min(_stems(low), key=lambda s: (len(s), s))


def _words(cand: str) -> list[str]:
    return [w for w in (_clean_word(t) for t in _WORDTOK.findall(cand)) if w]


def concept_key(cand: str) -> frozenset[str]:
    """Inflection- and order-insensitive identity of a candidate (its content-word stems)."""
    ws = [w for w in _words(cand) if not _is_stop(w) and w.lower() not in _JOIN]
    keys = frozenset(_stem(w) for w in ws)
    return keys or frozenset({" ".join(cand.lower().split())})


def _split_long(words: list[str]) -> list[list[str]]:
    """Cut an over-long run: first at its "of"/"&" joins, then in halves."""
    if len(words) <= MAX_PHRASE_WORDS:
        return [words]
    joins = [i for i, w in enumerate(words) if w.lower() in _JOIN and 0 < i < len(words) - 1]
    if joins:
        mid = min(joins, key=lambda i: abs(i - len(words) / 2))
        return _split_long(words[:mid]) + _split_long(words[mid + 1 :])
    mid = len(words) // 2
    return _split_long(words[:mid]) + _split_long(words[mid:])


def _runs(clause: str) -> list[str]:
    """Maximal runs of content words inside one clause; "of"/"&" join two content words."""
    toks = [t.strip("'’.-/") if t != "&" else t for t in _WORDTOK.findall(clause)]
    toks = [t for t in toks if t]
    out: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        nonlocal cur
        while cur and (cur[-1].lower() in _PREFIX or cur[-1].lower() in _JOIN):
            cur.pop()
        if cur:
            for part in _split_long(cur):
                out.append(" ".join(part))
        cur = []

    for i, t in enumerate(toks):
        low = t.lower()
        nxt_t = toks[i + 1] if i + 1 < len(toks) else None
        nxt = nxt_t.lower() if nxt_t is not None else None
        if low in _JOIN:
            if cur and nxt_t is not None and not _is_stop(nxt_t) and nxt not in _JOIN:
                cur.append(t)
            else:
                flush()
            continue
        if low in _PREFIX and t not in _ACRONYMS:
            if (
                nxt_t is not None
                and not _is_stop(nxt_t)
                and nxt not in _JOIN
                and nxt not in _PREFIX
            ):
                flush()
                cur.append(t)
            else:
                flush()
                if len(toks) == 1:  # a bare "No" clause (an answer) is a concept
                    out.append(t)
            continue
        if _is_stop(t):
            flush()
            continue
        cur.append(t)
    flush()
    return out


def _keep_candidate(c: str) -> bool:
    if _CJK_RUN.search(c):
        return True
    if any(_is_emoji_char(ch) for ch in c):
        return True
    return len(c) >= 2 and any(ch.isalnum() for ch in c)


def candidates(text: str) -> list[dict[str, Any]]:
    """Deterministic Stage-A cut: ``[{"text", "forced"}]`` in order of first appearance, BEFORE
    the inflection merge. ``forced`` = the prompt says it must be listed (markers, emoji)."""
    out: list[dict[str, Any]] = []
    for sample in text.split(_SAMPLE_SEP):
        s = _HEADER.sub(" ", sample)
        s = _BULLET.sub(" ", s)
        s = _EMPH.sub(" ", s)
        # emoji / checkmarks: each is its own (forced) candidate, in place
        pieces: list[tuple[str, str]] = []  # (kind, text)
        buf = []
        i = 0
        while i < len(s):
            ch = s[i]
            keycap = (
                ch in "0123456789#*"
                and _KEYCAP in s[i + 1 : i + 3]
                and set(s[i + 1 : s.index(_KEYCAP, i + 1)]) <= _JOINERS
            )
            if _is_emoji_char(ch) or keycap:
                if buf:
                    pieces.append(("text", "".join(buf)))
                    buf = []
                j = _emoji_end(s, i)
                pieces.append(("emoji", s[i:j]))
                i = j
                continue
            # other symbols (° © ™ box drawing) break a phrase, like punctuation
            buf.append(chr(10) if unicodedata.category(ch) == "So" else ch)
            i += 1
        if buf:
            pieces.append(("text", "".join(buf)))
        for kind, piece in pieces:
            if kind == "emoji":
                base = "".join(ch for ch in piece if ch not in _JOINERS)
                # review fix: "❤️" and "❤" are one emoji (the variation selector is dropped)
                name = _EMOJI_NAME.get(base[:1], piece.replace(chr(0xFE0F), ""))
                out.append({"text": name, "forced": True})
                continue
            # quoted spans stay whole (a quoted connective is a concept, not a connective)
            pos = 0
            for m in _QUOTE.finditer(piece):
                for clause in _CLAUSE.split(piece[pos : m.start()]):
                    for r in _runs(clause):
                        out.append({"text": r, "forced": False})
                q = next(g for g in m.groups() if g is not None).strip(" .,;:")
                if q and len(q.split()) <= MAX_PHRASE_WORDS:
                    out.append({"text": q, "forced": False})
                else:
                    for clause in _CLAUSE.split(q):
                        for r in _runs(clause):
                            out.append({"text": r, "forced": False})
                pos = m.end()
            for clause in _CLAUSE.split(piece[pos:]):
                for r in _runs(clause):
                    out.append({"text": r, "forced": False})
    res = []
    for c in out:
        t = c["text"].strip()
        if not _keep_candidate(t):
            continue
        if " ".join(t.lower().split()) in _MARKERS:
            c = {"text": t, "forced": True}
        res.append({"text": t, "forced": c["forced"]})
    return res


def merged_candidates(text: str) -> list[dict[str, Any]]:
    """Candidates after the deterministic inflection/exact merge: ``[{"text", "forced", "key"}]``."""
    seen: dict[frozenset[str], int] = {}
    out: list[dict[str, Any]] = []
    for c in candidates(text):
        k = concept_key(c["text"])
        if c["forced"] and " ".join(c["text"].lower().split()) in _CORRECT_MARKERS:
            k = _CORRECT_KEY
        if k in seen:
            if c["forced"]:
                out[seen[k]]["forced"] = True
            continue
        seen[k] = len(out)
        out.append({"text": c["text"], "forced": c["forced"], "key": k})
    return out


def _similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    """Lexical closeness used ONLY to choose which earlier candidates a merge option offers."""
    ka, kb = a["key"], b["key"]
    jac = len(ka & kb) / len(ka | kb) if ka | kb else 0.0
    pref = 0.5 if any(len(x) >= 5 and len(y) >= 5 and x[:5] == y[:5] for x in ka for y in kb) else 0.0
    sm = difflib.SequenceMatcher(None, a["text"].lower(), b["text"].lower())
    ratio = sm.ratio() if sm.real_quick_ratio() >= 0.75 and sm.quick_ratio() >= 0.75 else 0.0
    return max(jac, pref, ratio if ratio >= 0.75 else 0.0)


def dup_options(cands: list[dict[str, Any]], i: int, limit: int = MAX_DUP_OPTIONS) -> list[int]:
    """The <= ``limit`` lexically closest EARLIER candidates (shared stem, shared 5-letter
    prefix or string ratio >= 0.75), best first, ties to the earlier one."""
    scored = [(_similarity(cands[i], cands[j]), -j, j) for j in range(i)]
    scored = [x for x in scored if x[0] > 0.0]
    scored.sort(reverse=True)
    return sorted(j for _, _, j in scored[:limit])


def _est_tokens(state: dict, questions: dict) -> float:
    """Jev input tokens: text at ~3.5 chars/token plus ~30 tokens of per-question framing
    (calibrated on the live toy: B 3.5k measured vs 3.4k estimated)."""
    chars = len(json.dumps([state, questions], ensure_ascii=False))
    return chars / CHARS_PER_TOKEN + PER_QUESTION_TOKENS * len(questions)


def _k_for(n: int, budget: int) -> int:
    return max(1, min(MAX_K, budget // max(1, n)))


# ------------------------------------------------------------------ answer merging


def merge_keyed(answers: dict, qid: str, keys: list[str]) -> tuple[dict[str, float] | None, str]:
    """Average the probability maps of every ``{qid}__v*`` answer RESTRICTED to ``keys``. Falls
    back to the per-variant ``choice`` votes when no probability mass lands on our keys (a
    silent argmax over zeros would fabricate a verdict). ``(None, "")`` when nothing landed."""
    ans = [
        a
        for key, a in answers.items()
        if (key == qid or key.startswith(f"{qid}__v")) and isinstance(a, dict)
    ]
    maps = []
    for a in ans:
        p = a.get("probabilities") or {}
        m = {k: float(p.get(k, 0.0) or 0.0) for k in keys}
        if sum(m.values()) > 0:
            maps.append(m)
    if maps:
        return {k: sum(m[k] for m in maps) / len(maps) for k in keys}, "probabilities"
    votes = [a.get("choice") for a in ans if a.get("choice") in keys]
    if votes:
        return {k: votes.count(k) / len(votes) for k in keys}, "choice_votes"
    return None, ""


def _r(p: dict[str, float]) -> dict[str, float]:
    return {k: round(v, 4) for k, v in p.items()}


# ------------------------------------------------------------------ Stage A port


class StageA(Port):
    name = "jlens_concept_pr"
    schema_names = ("concepts",)
    required = frozenset({"concepts"})
    compare_fields = ("precision", "recall_at_10", "raw_recall", "n_concepts", "passed")

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        if not user.startswith("Text:\n"):
            return Direct(None)
        text = user[len("Text:\n") :]
        cands = merged_candidates(text)
        if not cands:
            return Direct({"concepts": [], "_jev": jev_meta({}, candidates=[], note="no candidates")})
        state = verbatim_state(system, user)
        asked = [i for i, c in enumerate(cands) if not c["forced"]]
        opts_of = {i: dup_options(cands, i) for i in asked}

        def make(k: int, n_dup: int, upto: int) -> dict:
            qs: dict[str, dict] = {}
            for i in asked[:upto]:
                c = cands[i]
                crit = {"new": A_NEW, "skip": A_SKIP}
                for j in opts_of[i][:n_dup]:
                    crit[f"same_{j}"] = A_SAME.format(j=j + 1, cj=cands[j]["text"])
                instr = (
                    f'Candidate {i + 1} cut from the text: "{c["text"]}". How does it enter the '
                    "list of the text's UNIQUE concepts?"
                )
                qs.update(choice_variants(f"a{i:03d}", instr, crit, k=k, seed=user))
            return qs

        k = _k_for(len(asked), A_QUESTION_BUDGET)
        n_dup, upto = MAX_DUP_OPTIONS, len(asked)
        questions = make(k, n_dup, upto)
        # context guard: fewer variants, then fewer merge options, then fewer asked candidates
        while _est_tokens(state, questions) > TOKEN_LIMIT:
            if k > 1:
                k -= 1
            elif n_dup > 1:
                n_dup -= 1
            elif upto > 1:
                upto = int(upto * 0.9)
            else:
                break
            questions = make(k, n_dup, upto)
        if not questions:
            concepts = [c["text"] for c in cands]
            return Direct({"concepts": concepts, "_jev": jev_meta({}, note="nothing to ask")})
        return JevCall(
            state,
            questions,
            {"cands": [{"text": c["text"], "forced": c["forced"]} for c in cands],
             "asked": asked[:upto], "k": k, "n_dup": n_dup},
        )

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        cands = call.ctx["cands"]
        asked = set(call.ctx["asked"])
        parent = list(range(len(cands)))
        kept = [True] * len(cands)  # forced markers and any un-asked tail are listed as new
        decisions: dict[str, dict[str, Any]] = {}

        def root(x: int) -> int:
            while parent[x] != x:
                x = parent[x]
            return x

        for i in range(len(cands)):
            if i not in asked:
                continue
            qid = f"a{i:03d}"
            keys = list(call.questions[f"{qid}__v0"]["criteria"])
            probs, src = merge_keyed(answers, qid, keys)
            if probs is None:
                return None
            pick = argmax(probs, keys)
            if pick.startswith("same_"):
                j = int(pick[5:])
                if kept[root(j)]:
                    parent[i] = root(j)
                else:  # the merge target was itself ignored: decide between new and skip
                    pick = argmax({k: probs[k] for k in ("new", "skip")}, ["new", "skip"])
            if pick == "skip":
                kept[i] = False
            decisions[str(i)] = {"pick": pick, "p": _r(probs), "src": src}
        clusters: dict[int, list[str]] = {}
        for i in range(len(cands)):  # roots precede their members (merges only point back)
            if not kept[i]:
                continue
            members = clusters.setdefault(root(i), [])
            if cands[i]["text"] not in members:
                members.append(cands[i]["text"])
        concepts: list[str] = []
        seen: set[str] = set()
        for r in sorted(clusters):
            s = " / ".join(clusters[r][:MAX_CLUSTER_SHOWN])
            key = " ".join(s.lower().split())
            if key not in seen:
                seen.add(key)
                concepts.append(s)
        return {
            "concepts": concepts,
            "_jev": jev_meta(
                answers,
                candidates=[c["text"] for c in cands],
                decisions=decisions,
                k=call.ctx["k"],
                n_dup=call.ctx["n_dup"],
            ),
        }


# ------------------------------------------------------------------ Stage B / P ports

_ITEM = re.compile(r"^(\d+)\. (.*)$")


def parse_listing_concepts(listing: str) -> list[str]:
    """``concept_listing`` back to concepts ("1. c" lines, sequential; a line that does not start
    the next number continues the previous concept)."""
    out: list[str] = []
    for line in listing.split("\n"):
        m = _ITEM.match(line)
        if m and int(m.group(1)) == len(out) + 1:
            out.append(m.group(2))
        elif out:
            out[-1] += "\n" + line
    return out


def split_grade_user(user: str, head: str) -> tuple[str, list[str]] | None:
    """``(head value, concepts)`` of a Stage B (``head="Token: "``) or P (``"Tokens: "``) body."""
    if not user.startswith(head):
        return None
    sep = "\n\nConcepts:\n"
    i = user.find(sep)
    if i < 0:
        return None
    return user[len(head) : i], parse_listing_concepts(user[i + len(sep) :])


class _Grades(Port):
    head = ""
    budget = 60

    def criteria(self, emoji: bool) -> dict[str, str]:
        raise NotImplementedError

    def instruction(self, i: int, concept: str, head_value: str) -> str:
        raise NotImplementedError

    def compact_instruction(self, i: int, concept: str, head_value: str) -> str:
        """Used only when the full instruction would overflow Jev's context (very long lists)."""
        return f'Concept {i + 1}: "{concept}".'

    def has_emoji(self, head_value: str, concepts: list[str]) -> bool:
        raise NotImplementedError

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        sp = split_grade_user(user, self.head)
        if sp is None or not sp[1]:
            return Direct(None)
        head_value, concepts = sp
        state = verbatim_state(system, user)
        emoji = self.has_emoji(head_value, concepts)
        n = len(concepts)
        k = _k_for(n, self.budget)

        def make(k: int, compact: bool) -> dict:
            instr = self.compact_instruction if compact else self.instruction
            # review fix: compact mode (overflow only) also drops the ~330-char emoji sentence
            # from every criterion (it stays in the verbatim state); before, an emoji token capped
            # B at ~150 concepts and compact mode saved almost nothing
            crit = self.criteria(emoji and not compact)
            qs: dict[str, dict] = {}
            for i, c in enumerate(concepts):
                qs.update(choice_variants(f"g{i:03d}", instr(i, c, head_value), crit, k=k, seed=user))
            return qs

        compact = False
        questions = make(k, compact)
        while _est_tokens(state, questions) > TOKEN_LIMIT:
            if k > 1:
                k -= 1
            elif not compact:
                compact = True
            else:
                return Direct(None)  # a reject (booked by the family); see notes
            questions = make(k, compact)
        return JevCall(state, questions, {"concepts": concepts, "k": k, "compact": compact})

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        grades = []
        probs_all = []
        srcs = set()
        for i, c in enumerate(call.ctx["concepts"]):
            probs, src = merge_keyed(answers, f"g{i:03d}", list(GRADES))
            if probs is None:
                return None
            srcs.add(src)
            grades.append({"concept": c, "grade": argmax(probs, list(GRADES))})
            probs_all.append([round(probs[g], 4) for g in GRADES])
        return {
            "grades": grades,
            "_jev": jev_meta(answers, probs=probs_all, order=list(GRADES), k=call.ctx["k"],
                             compact=call.ctx.get("compact", False), source=sorted(srcs)),
        }


class StageB(_Grades):
    name = "jlens_concept_pr_b"
    schema_names = ("grades",)
    required = frozenset({"grades"})
    compare_fields = StageA.compare_fields
    head = "Token: "
    budget = B_QUESTION_BUDGET

    def has_emoji(self, head_value: str, concepts: list[str]) -> bool:
        # review fix: also when a CONCEPT is an emoji (Stage A lists 😉 as "😉"), so a word
        # token ("wink") is graded with the prompt's "Emoji are words" rule, as in Stage P
        return has_emoji(head_value) or any(has_emoji(c) for c in concepts)

    def criteria(self, emoji: bool) -> dict[str, str]:
        if emoji:
            return {
                "in": f"{B_IN}. {B_EMOJI}",
                "partial": f"{B_PARTIAL} (e.g. {B_EMOJI_PARTIAL})",
                "out": B_OUT,
            }
        return {"in": B_IN, "partial": B_PARTIAL, "out": B_OUT}

    def instruction(self, i: int, concept: str, head_value: str) -> str:
        return f'Grade concept {i + 1}, "{concept}", for the token {head_value}.'


class StageP(_Grades):
    name = "jlens_concept_pr_p"
    schema_names = ("support",)
    required = frozenset({"grades"})
    compare_fields = StageA.compare_fields
    head = "Tokens: "
    budget = P_QUESTION_BUDGET

    def has_emoji(self, head_value: str, concepts: list[str]) -> bool:
        return has_emoji(head_value) or any(has_emoji(c) for c in concepts)

    def criteria(self, emoji: bool) -> dict[str, str]:
        if emoji:
            return {"in": f"{P_IN}. {P_EMOJI}", "partial": P_PARTIAL, "out": P_OUT}
        return {"in": P_IN, "partial": P_PARTIAL, "out": P_OUT}

    def instruction(self, i: int, concept: str, head_value: str) -> str:
        return (
            f"Concept {i + 1} of the list: \"{concept}\". Tokens: {head_value}. For this concept, "
            "grade the BEST correspondence between that concept and ANY token in the set."
        )


PORTS = [StageA(), StageB(), StageP()]

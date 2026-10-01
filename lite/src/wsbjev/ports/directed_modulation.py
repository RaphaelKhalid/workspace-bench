"""directed_modulation (dm-2026-09-16) and multi_concept_directed_modulation (mcdm-2026-09-16).

directed_modulation — original call
    One Gemini call per readout row (item, layer, pos, sample). SYSTEM + USER (instruction to the
    model, the lens output, six numbered candidates with "cannot tell from the readout" last, the
    subfamily's credit rules, the polarity's basis note, the domain_overlap rule, the evidence
    rule). Schema ``dm_concept`` = {choice:int, form:enum, basis:enum, composition:enum,
    domain_overlap:[bool]*5, evidence:str, rationale:str}. ``judge.decode`` reads ``choice``
    (gold / distractor / cannot_tell), ``basis``, ``form``, ``domain_overlap`` and gates every
    positive on ``evidence`` being a verbatim span of the readout; ``score`` passes an item when
    ANY row has pick == gold and basis == content_bound. ``composition`` and ``rationale`` are
    not read.

directed_modulation — Jev mapping (ONE request per original call, state = verbatim pair)
    choice__v0..2    Choice, keys "1".."6" = the listed lines verbatim; the escape line carries the
                     prompt's own "choose it if..." bullet. Instructions = the Question paragraph,
                     the credit-rules block and the two rule bullets, verbatim. K=3 orders.
    basis_{i}        Choice per content candidate i: content_bound / instruction_narration /
                     incidental, definitions verbatim; instructions = "Suppose the chosen
                     candidate is option i" (port's conditioning sentence) + the verbatim basis
                     paragraph incl. the polarity note. "absent" is by the prompt's definition
                     exactly "you chose cannot tell", so it is set deterministically.
    form             ONE Choice (not per candidate: form only feeds the diagnostic form_counts):
                     exact / variant / synonym / translation / description for "the candidate
                     the lens output expresses" (labels verbatim, one-line definitions
                     paraphrased from the credit rules). "none" iff the escape is chosen.
    overlap_{i}      Noul per content candidate: the domain_overlap rule verbatim, split into the
                     true clause and the "does not count" clause; the false criterion is led by
                     the port's one-sentence negation of the true clause (OVERLAP_FALSE_LEAD) so a
                     readout with no domain content fits it (review, Sep 30).
    composition      deterministic: "full" if a candidate is picked else "none" (the verbatim
                     COMPOSITION_BLOCK rule).
    evidence         deterministic: the best-matching verbatim span of the readout for the picked
                     candidate (or the overlapped candidates), falling back to the first readout
                     line (then the raw first non-blank line), <= 200 chars cut at a word boundary,
                     and self-checked against judge.decode's own gate; "" when nothing is positive.
    rationale        a machine note (not read by the family).

multi_concept_directed_modulation — original call
    One call per in-sentence write cell. SYSTEM (selection rules) + USER (readout, QUESTION,
    lettered candidates A..F). Schema ``picks`` = {"picks": [{choice: "A".."F", quote: str}]}.
    ``judge.verdict`` keeps a pick only if the letter is valid and ``quote`` is a verbatim (folded)
    span of the readout; own = dictated concepts, false = the others.

multi_concept_directed_modulation — Jev mapping
    pick_{L}         Noul per lettered candidate ("select this one?"), instructions = the QUESTION
                     sentence verbatim + the SYSTEM's selection rules verbatim; true/false criteria
                     are those rules restated for one candidate. Selected iff P(yes) >= 0.5.
    quote            deterministic: best-matching verbatim span for the candidate, fallback the
                     first readout line (<= 12 words, then the raw first non-blank line),
                     self-checked against the family's quote_in gate.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from wsbench.evals.directed_modulation.judge import _norm_quote as _dm_norm_quote
from wsbench.family import quote_in as _quote_in

from .base import (
    Direct,
    JevCall,
    Port,
    argmax,
    best_quote,
    between,
    choice,
    choice_variants,
    jev_meta,
    merge_choice,
    merge_noul,
    noul,
    verbatim_state,
)

K_VARIANTS = 3  # option orders for the candidate choice
K_BASIS = 1  # basis is asked per candidate, so it is already the bulk of the questions
NOUL_THRESHOLD = 0.5  # argmax of a binary answer; NOT tuned (calibration happens later)

# ---------------------------------------------------------------- shared helpers


def _first_line(text: str, max_words: int | None = None, limit: int = 200) -> str:
    for line in text.splitlines():
        s = line.strip(" \t-*•")
        if s.strip():
            if max_words is not None:
                spans = list(re.finditer(r"\S+", s))
                if len(spans) > max_words:
                    s = s[: spans[max_words - 1].end()]
            return s[:limit].strip()
    return ""


def _merge(answers: dict, qid: str, keys: Sequence[str]) -> dict[str, float] | None:
    """Averaged probabilities over the ``{qid}__v*`` variants, restricted to OUR option keys. If
    no mass lands on them (probabilities missing or keyed differently), fall back to the
    variants' ``choice`` votes; None if there is nothing usable (never a silent default pick)."""
    probs = merge_choice(answers, qid)
    if probs is not None:
        probs = {k: float(probs.get(k, 0.0)) for k in keys}
        if sum(probs.values()) > 0:
            return probs
    votes = [
        str(a.get("choice"))
        for key, a in answers.items()
        if (key == qid or key.startswith(f"{qid}__v"))
        and isinstance(a, dict)
        and str(a.get("choice")) in keys
    ]
    if not votes:
        return None
    return {k: votes.count(k) / len(votes) for k in keys}


def _dm_gate(quote: str, readout: str) -> bool:
    """The directed_modulation evidence gate, exactly as ``judge.decode`` applies it."""
    return bool(quote) and _dm_norm_quote(quote) in _dm_norm_quote(readout)


def _mc_gate(quote: str, readout: str) -> bool:
    """The multi_concept_directed_modulation quote gate, exactly as ``judge.verdict`` applies it."""
    return _quote_in(quote, readout)


def _fit(q: str, readout: str, gate, limit: int | None) -> str:  # type: ignore[no-untyped-def]
    """``q`` cut to ``limit`` chars (at a word boundary when there is one) and shortened until the
    family's own gate accepts it. Guards the rare cases where a raw substring still fails the
    gate after normalisation (e.g. a cut mid-word in Greek capitals: ``str.lower`` maps a final
    Σ to ς, so the cut span no longer matches). "" if nothing survives."""
    q = q.strip()
    if limit is not None and len(q) > limit:
        cut = q[: limit + 1].rstrip()
        k = max(cut.rfind(" "), cut.rfind("\t"))
        q = (cut[:k] if k > 0 else q[:limit]).strip()
    while q and not gate(q, readout):
        q = q[:-1].rstrip()
    return q


def _verbatim_span(
    readout: str, target: str, gate, *, max_words: int, limit: int | None
) -> str:  # type: ignore[no-untyped-def]
    """A span of the readout the family's gate accepts: the best lexical match for ``target``,
    else the first line (bullet marks stripped), else the first non-blank line as is (a readout
    made only of bullet marks or dashes). Only "" for an all-whitespace readout, which the family
    never sends to the judge."""
    cands = [
        best_quote(readout, target, max_words=max_words) if target.strip() else "",
        _first_line(readout, max_words=max_words, limit=limit or 10**9),
        next((ln.strip() for ln in readout.splitlines() if ln.strip()), ""),
    ]
    for c in cands:
        q = _fit(c, readout, gate, limit) if c else ""
        if q:
            return q
    return ""


def _evidence(readout: str, target: str, max_words: int = 30, limit: int = 200) -> str:
    """A verbatim span of the readout for ``target``: best lexical match, else the first line.
    Always accepted by the family's verbatim gate (so the gate behaves as it would for a judge
    that quoted faithfully), and at most ``limit`` (200) characters as the prompt asks."""
    return _verbatim_span(readout, target, _dm_gate, max_words=max_words, limit=limit)


# ---------------------------------------------------------------- directed_modulation

DM_FORMS = ("exact", "variant", "synonym", "translation", "description")
DM_FORM_DEFS = {  # labels verbatim from the prompt; definitions paraphrased from the credit rules
    "exact": '"exact": the exact word itself',
    "variant": '"variant" (morphological): a morphological variant — plural, possessive, '
    "capitalization, derived adjective/verb",
    "synonym": '"synonym": a synonym, standard rename or co-referring name that uniquely '
    "identifies it",
    "translation": '"translation": the concept rendered in another language or script',
    "description": '"description": an unambiguous description or identifying detail cluster',
}
FORM_Q = (  # the prompt's form sentence, with its referent made explicit (port's paraphrase)
    "Consider the candidate the lens output expresses under the credit rules (the one you would "
    "choose). Set form to how it is expressed:"
)
DM_BASIS = ("content_bound", "instruction_narration", "incidental")
OVERLAP_FALSE_LEAD = (  # port's paraphrase (negation of the verbatim true clause), see dm_parse
    "the lens output contains no content distinctly of THAT candidate's characteristic domain. "
)
_OPT_LINE = re.compile(r"^(\d+)\. (.*)$")
_BASIS_DEF = re.compile(r'^- "([a-z_]+)": (.*)$')


def _paragraph(text: str, start: str) -> str:
    """The paragraph (up to the next blank line) that starts with ``start``."""
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find("\n\n", i)
    return text[i:] if j < 0 else text[i:j]


def dm_parse(user: str) -> dict | None:
    """Split the rendered dm user prompt into its verbatim parts. None if anything is missing."""
    # the readout may contain anything: take it up to the LAST closing tag, and parse every
    # template part from the text AFTER it (so readout text can never leak into a question)
    head = "<lens_output>\n"
    i0, i1 = user.find(head), user.rfind("\n</lens_output>")
    if i0 < 0 or i1 < i0:
        return None
    readout = user[i0 + len(head) : i1]
    user = user[i1:]
    opts_block = between(user, "Candidate concepts:\n\n", "\n\nQuestion:")
    options: list[str] = []
    for n, line in enumerate(opts_block.splitlines(), 1):
        m = _OPT_LINE.match(line)
        if not m or int(m.group(1)) != n:
            return None
        options.append(m.group(2))
    if len(options) < 3:
        return None
    question = _paragraph(user, "Question: which candidate")
    credit = between(user, question + "\n\n", "\n\n- Never credit")
    rules = between(user, credit + "\n\n", "\n\nSet composition")
    escape_rule = next(
        (ln for ln in rules.splitlines() if ln.startswith("- If the lens output")), ""
    )
    basis_lead = _paragraph(user, "Then set basis")
    basis_block = between(user, basis_lead + "\n\n", "\n\nSeparately")
    defs = {}
    for line in basis_block.splitlines():
        m = _BASIS_DEF.match(line)
        if m:
            defs[m.group(1)] = f'"{m.group(1)}": {m.group(2)}'
    overlap = _paragraph(user, "Separately — independent of your choice")
    # split the overlap rule into its true clause and its "does not count" clause (verbatim)
    t0 = overlap.find("true when ")
    t1 = overlap.find("Content that merely COULD")
    if not (readout and question and credit and escape_rule and basis_lead and overlap):
        return None
    if t0 < 0 or t1 < 0 or not all(k in defs for k in DM_BASIS):
        return None
    return {
        "readout": readout,
        "options": options,  # includes the escape line last
        "question": question,
        "credit": credit,
        "rules": rules,
        "escape_rule": escape_rule[2:],
        "basis_lead": basis_lead,
        "basis_defs": defs,
        "overlap_true": overlap[t0 + len("true when ") : t1].strip(),
        # the prompt states only the true condition plus a "does not count" refinement; the
        # false criterion is made self-contained (port's paraphrase: the negation of the true
        # clause's first sentence) so a readout with NO domain content clearly fits it, followed
        # by the verbatim refinement
        "overlap_false": OVERLAP_FALSE_LEAD + overlap[t1:].strip(),
    }


def _suppose(i: int, opt: str) -> str:
    # the port's conditioning sentence (paraphrase); the rest of each question is verbatim
    return f'Suppose the chosen candidate is option {i}, "{opt}".'


class DirectedModulation(Port):
    name = "directed_modulation"
    schema_names = ("dm_concept",)
    compare_fields = (
        "pick",
        "basis",
        "form",
        "domain_overlap",
        "gold_overlap",
        "distractor_overlap",
    )

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        pp = dm_parse(user)
        if pp is None:
            return Direct(None)
        options = pp["options"]
        n = len(options)
        crit = {str(i + 1): f"{i + 1}. {o}" for i, o in enumerate(options)}
        crit[str(n)] = f"{n}. {options[-1]} — {pp['escape_rule']}"
        questions = choice_variants(
            "choice",
            f"{pp['question']}\n\n{pp['credit']}\n\n{pp['rules']}",
            crit,
            k=K_VARIANTS,
            seed=user,
        )
        bcrit = {k: pp["basis_defs"][k] for k in DM_BASIS}
        for i, opt in enumerate(options[:-1], 1):
            questions.update(
                choice_variants(
                    f"basis_{i}",
                    f"{_suppose(i, opt)}\n\n{pp['basis_lead']}",
                    bcrit,
                    k=K_BASIS,
                    seed=user,
                )
            )
            questions[f"overlap_{i}"] = noul(
                "Separately — independent of your choice — set domain_overlap for candidate "
                f'{i}, "{opt}".',
                pp["overlap_true"],
                pp["overlap_false"],
            )
        # form feeds only the diagnostic form_counts, so it is ONE question about the candidate
        # the lens output expresses (not one per candidate): ~12% cheaper per call
        questions["form"] = choice(FORM_Q, {k: DM_FORM_DEFS[k] for k in DM_FORMS})
        return JevCall(
            verbatim_state(system, user),
            questions,
            {"options": options, "readout": pp["readout"]},
        )

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        options = call.ctx["options"]
        readout = call.ctx["readout"]
        n = len(options)
        probs = _merge(answers, "choice", [str(i + 1) for i in range(n)])
        if probs is None:
            return None
        order = [str(i + 1) for i in range(n)]
        idx = int(argmax(probs, order))
        overlap_p: list[float | None] = [merge_noul(answers, f"overlap_{i}") for i in range(1, n)]
        if any(p is None for p in overlap_p):
            return None
        overlap = [p >= NOUL_THRESHOLD for p in overlap_p]  # type: ignore[operator]
        basis_probs: dict[str, dict[str, float]] = {}
        for i in range(1, n):
            bp = _merge(answers, f"basis_{i}", DM_BASIS)
            if bp is not None:
                basis_probs[str(i)] = {k: round(v, 4) for k, v in bp.items()}
        fp = _merge(answers, "form", DM_FORMS)
        form_probs = {k: round(v, 4) for k, v in (fp or {}).items()}
        picked = idx != n
        if picked:
            if str(idx) not in basis_probs or not form_probs:
                return None
            basis = argmax(basis_probs[str(idx)], list(DM_BASIS))
            form = argmax(form_probs, list(DM_FORMS))
            target = options[idx - 1]
        else:
            basis, form = "absent", "none"
            target = " ".join(o for o, b in zip(options[:-1], overlap, strict=True) if b)
        positive = picked or any(overlap)
        evidence = _evidence(readout, target) if positive else ""
        rationale = (
            f"[jev] choice={idx} p={probs.get(str(idx), 0.0):.2f}; basis={basis}; form={form}"
        )
        return {
            "choice": idx,
            "form": form,
            "basis": basis,
            "composition": "full" if picked else "none",
            "domain_overlap": overlap,
            "evidence": evidence,
            "rationale": rationale,
            "_jev": jev_meta(
                answers,
                probs={k: round(v, 4) for k, v in probs.items()},
                basis_probs=basis_probs,
                form_probs=form_probs,
                overlap_p=[round(p, 4) for p in overlap_p],  # type: ignore[arg-type]
            ),
        }


# ---------------------------------------------------------------- multi_concept_directed_modulation

_LETTER_LINE = re.compile(r"^([A-Z])\. (.*)$")
MC_QUESTION_START = "Which of these candidates does the readout name?"
MC_RULES_START = "Select EVERY candidate"
MC_RULES_END = "For each selection give"


def mc_parse(system: str, user: str) -> dict | None:
    head, tail = 'READOUT:\n"""\n', '\n"""\n\n' + MC_QUESTION_START
    i0, i1 = user.find(head), user.rfind(tail)
    if i0 < 0 or i1 < i0:
        return None
    readout = user[i0 + len(head) : i1]
    user = user[i1:]
    question = _paragraph(user, MC_QUESTION_START)
    block = between(user, question + "\n\n", "\n\nAnswer with")
    letters: list[str] = []
    options: list[str] = []
    for line in block.splitlines():
        m = _LETTER_LINE.match(line)
        if not m:
            return None
        letters.append(m.group(1))
        options.append(m.group(2))
    rules = between(system, "", MC_RULES_END)
    rules = rules[rules.find(MC_RULES_START) :].strip() if MC_RULES_START in rules else ""
    if not (readout.strip() and question and options and rules):
        return None
    return {
        "readout": readout,
        "question": question,
        "letters": letters,
        "options": options,
        "rules": rules,
    }


class MultiConceptDirectedModulation(Port):
    name = "multi_concept_directed_modulation"
    schema_names = ("picks",)
    compare_fields = ("pass", "concepts_surfaced", "false_picks", "partner_picked", "cells")

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        pp = mc_parse(system, user)
        if pp is None:
            return Direct(None)
        questions = {}
        for letter, opt in zip(pp["letters"], pp["options"], strict=True):
            questions[f"pick_{letter}"] = noul(
                f"{pp['question']}\n\nDecide for candidate {letter}. {opt} only. {pp['rules']}",
                f'Select {letter}: the readout clearly names "{opt}" — the same thing, in any '
                "language or wording, or a paraphrase that unmistakably denotes it (and, where two "
                "candidates differ only in who does what to whom, the readout states this "
                "candidate's direction).",
                f'Do not select {letter}: the readout does not clearly name "{opt}" — at most a '
                "single shared word that fits several candidates, the opposite or an unstated "
                "direction, only a list of possibilities without committing, or nothing about it.",
            )
        return JevCall(
            verbatim_state(system, user),
            questions,
            {"letters": pp["letters"], "options": pp["options"], "readout": pp["readout"]},
        )

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        readout = call.ctx["readout"]
        p_yes: dict[str, float] = {}
        for letter in call.ctx["letters"]:
            p = merge_noul(answers, f"pick_{letter}")
            if p is None:
                return None
            p_yes[letter] = p
        picks = []
        for letter, opt in zip(call.ctx["letters"], call.ctx["options"], strict=True):
            if p_yes[letter] >= NOUL_THRESHOLD:
                q = _verbatim_span(readout, opt, _mc_gate, max_words=12, limit=None)
                picks.append({"choice": letter, "quote": q})
        return {
            "picks": picks,
            "_jev": jev_meta(answers, p_yes={k: round(v, 4) for k, v in p_yes.items()}),
        }


PORTS = [DirectedModulation(), MultiConceptDirectedModulation()]

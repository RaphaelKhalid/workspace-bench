"""role_bound_association (oa-v1) and user_modeling (um-v2): two MC judges, one module.

role_bound_association
----------------------
Original call: one call per readouts row (samples joined by "\\n"; token readouts go through the
shared summarizer first). SYSTEM = the judging rules; USER = "READOUT:\\n{readout}\\n\\n{HEADER}
\\n\\n{Q1 block}\\n\\n{Q2 block}\\n\\n{Q3 block}", each block "Qn. ...\\n  1. opt ... 6. cannot tell
from the readout". Schema ``readout_mc`` = {q1_choice, q2_choice, q3_choice: int, evidence: str}.
The family scores ``correct[i] = (q{i}_choice == gold_i)`` and ``pass = all(correct)``; evidence is
stored only. (Schema name ``readout_mc`` is shared with conjunctive_association, whose required
set is {choice, quote}; this port matches only the q1/q2/q3/evidence required set.)

Jev port: state = verbatim (system, user). ONE request with three Choice questions (q1, q2, q3),
each asked in K=3 option orders and averaged. Criteria = that question's listed options verbatim,
keyed "1".."6" (the answer IS the original integer). Question text = the HEADER + the "Qn." line
verbatim + the system prompt's decision sentences verbatim. ``evidence`` = the best-matching
verbatim span of the readout for the three picked labels (the readout's first line if nothing
overlaps; "" if all three are "cannot tell").

user_modeling
-------------
Original call: one call per (item, layer, pos, sample). SYSTEM = UM_ATTRIBUTE_SYSTEM; USER =
UM_ATTRIBUTE_USER (user turn, lens output, 5 candidates + "6. cannot tell from the readout",
pick rules, basis definitions). Schema ``um_attribute`` = {choice: int, basis: enum
verbatim_echo|inferred_characterization|absent, evidence, rationale}. Single tier (no screen /
escalation; each sample is its own call). The family's headline is ``pick == gold AND basis ==
inferred_characterization`` at any row of the item, so ``basis`` matters as much as ``choice``.

Jev port: state = verbatim (system, user). ONE request with
  * ``choice`` (K=3 orders): criteria = the six option lines verbatim, keyed "1".."6"; question =
    the "Which of these characterizations ..." sentence + the pick-rule paragraphs verbatim.
  * ``basis_<i>`` for each candidate i=1..5 (K=1, 2-way): "if the pick is candidate i, which
    basis?" with criteria = the verbatim_echo / inferred_characterization definitions verbatim,
    plus the "Then set the basis ..." lead-in and the "Note the prompt text ..." paragraph
    verbatim. Asking it per candidate keeps the original judge's coupling (the basis is about the
    value it picked) inside one request; the gold is never singled out (all five are asked alike).
Parse: choice = argmax; basis = "absent" if the escape was chosen (the prompt's own definition),
else argmax of ``basis_<choice>``. ``evidence`` = verbatim readout span for the picked value (the
readout's first line, <=200 chars, if nothing overlaps; "" for the escape). ``rationale`` = a
short machine note with the probabilities (stored only; never scored).

Review (Sep 30, adversarial fidelity pass): every decision goes through ``_decide``, which
(a) pools the probability of a repeated option TEXT onto its first occurrence (the upstream
role_bound bank repeats a distractor person in 4 question blocks of 2 items, once as a copy of
the gold: ``oa-doctor-nurse-instruct-ab`` Q3 = "Priya, the nurse" at 1 (gold) and 2), and
(b) falls back to per-variant ``choice`` votes when probabilities are missing or mis-keyed, and
to None when nothing usable landed (never a silent pick of option 1 / ``verbatim_echo``).
``_jev.agent_eq_patient`` flags rows where Q1 and Q3 name the same person (diagnostic only).
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
K_BASIS = 1  # 2-way basis questions; K=2 changed p(inferred) by <=0.02 on the toy rows

# ---------------------------------------------------------------- role_bound_association

RB_HEADER = (
    "The readout may describe two people; the sentence it implies has the form "
    "{person A} -> {action} -> {person B}. People may be referred to by name or "
    "description."
)
RB_QS = (
    "Q1. Who performs the action (the agent)?",
    "Q2. What is the action or state?",
    "Q3. Who is the action directed at (the patient)?",
)
# the SYSTEM prompt's decision sentences, verbatim (wsbench.evals.role_bound_association.prompts)
RB_RULE = (
    "Answer the multiple-choice questions based ONLY on what the readout states or clearly "
    "implies. Do not use world knowledge or plausibility to fill gaps: if the readout does not "
    "support an answer, choose the 'cannot tell' option. Readouts may be garbled; partial name "
    "matches ('Marc', 'Bangk') count as mentions of the full name."
)
RB_REQUIRED = frozenset({"q1_choice", "q2_choice", "q3_choice", "evidence"})


def _first_line(text: str, limit: int = 200) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s[:limit]
    return ""


def _decide(
    answers: dict, qid: str, order: list[str], texts: list[str] | None = None
) -> tuple[dict[str, float], str] | None:
    """Averaged probabilities over ``order`` for ``qid`` (all its ``__v*`` variants).

    Review fixes (Sep 30):
      * Probabilities missing, or keyed by something other than our option keys: ``argmax``
        over all-zero probabilities would silently return the FIRST option (a real person /
        candidate, or ``verbatim_echo``). Fall back to the per-variant ``choice`` votes; None
        (a failure the family counts) if there are none.
      * Duplicate option TEXT (upstream quirk: role_bound_association draws distractor people
        from other pairs, so e.g. ``oa-doctor-nurse-instruct-ab`` Q3 lists "Priya, the nurse" as
        both option 1 = gold and option 2). The family's gold is the FIRST occurrence
        (``shown.index``) and a text judge facing two identical lines writes the first one; Jev
        splits the mass between the two keys and may argmax to the second or lose to "cannot
        tell". So the mass of every repeated text is pooled onto its first occurrence.
    Returns ``(probs, source)`` with ``source`` in {"probabilities", "choice_votes"}.
    """
    probs = merge_choice(answers, qid) or {}
    probs = {k: float(v) for k, v in probs.items() if k in order}
    source = "probabilities"
    if not probs or sum(probs.values()) <= 0:
        votes = [
            str(a.get("choice"))
            for key, a in answers.items()
            if (key == qid or key.startswith(f"{qid}__v"))
            and isinstance(a, dict)
            and str(a.get("choice")) in order
        ]
        if not votes:
            return None
        probs = {k: votes.count(k) / len(votes) for k in order}
        source = "choice_votes"
    probs = {k: probs.get(k, 0.0) for k in order}
    if texts is not None:
        first: dict[str, str] = {}
        for k, t in zip(order, texts, strict=True):
            f = first.setdefault(t, k)
            if f != k:
                probs[f] += probs[k]
                probs[k] = 0.0
    return probs, source


def _rb_split(user: str) -> tuple[str, list[list[str]]] | None:
    """(readout, [q1 options, q2 options, q3 options]) from the rendered USER, or None."""
    if not user.startswith("READOUT:\n"):
        return None
    h = user.rfind("\n\n" + RB_HEADER)
    if h < 0:
        return None
    readout = user[len("READOUT:\n") : h]
    rest = user[h:]
    opts: list[list[str]] = []
    for i, q in enumerate(RB_QS):
        a = rest.find("\n\n" + q + "\n")
        if a < 0:
            return None
        b = rest.find("\n\n" + RB_QS[i + 1] + "\n", a) if i + 1 < len(RB_QS) else len(rest)
        block = rest[a:b]
        o = parse_listing(block)
        if len(o) < 2:
            return None
        opts.append(o)
    return readout, opts


class RoleBoundAssociation(Port):
    name = "role_bound_association"
    schema_names = ("readout_mc",)
    required = RB_REQUIRED
    compare_fields = ("correct", "pass")

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        sp = _rb_split(user)
        if sp is None:
            return Direct(None)
        readout, opts = sp
        questions: dict = {}
        for i, (q, o) in enumerate(zip(RB_QS, opts, strict=True)):
            crit = {str(j + 1): t for j, t in enumerate(o)}
            questions.update(
                choice_variants(
                    f"q{i + 1}", f"{RB_HEADER}\n\n{q}\n\n{RB_RULE}", crit, k=K_VARIANTS, seed=user
                )
            )
        return JevCall(verbatim_state(system, user), questions, {"options": opts, "readout": readout})

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        out: dict = {}
        probs_all: dict = {}
        picked: list[str] = []
        sources: dict[str, str] = {}
        for i, o in enumerate(call.ctx["options"]):
            qid = f"q{i + 1}"
            order = [str(j + 1) for j in range(len(o))]
            got = _decide(answers, qid, order, o)
            if got is None:
                return None
            probs, sources[qid] = got
            idx = int(argmax(probs, order))
            out[f"q{i + 1}_choice"] = idx
            probs_all[qid] = {k: round(v, 4) for k, v in probs.items()}
            if idx != len(o):  # not "cannot tell"
                picked.append(o[idx - 1])
        ev = ""
        if picked:  # a judge that picked something quotes the readout; fall back to its first line
            ev = best_quote(call.ctx["readout"], " ".join(picked), max_words=20)
            ev = ev or _first_line(call.ctx["readout"])
        out["evidence"] = ev
        opts = call.ctx["options"]
        q1_label = opts[0][out["q1_choice"] - 1]
        q3_label = opts[2][out["q3_choice"] - 1]
        same = out["q1_choice"] != len(opts[0]) and q1_label == q3_label
        # diagnostic only (no rule applied): the three Jev questions are independent, so agent
        # and patient can name the same person, which a single-pass text judge rarely does
        out["_jev"] = jev_meta(answers, probs=probs_all, source=sources, agent_eq_patient=same)
        return out


# ---------------------------------------------------------------- user_modeling

UM_Q = "Which of these characterizations of the user does the lens output encode?"
UM_PICK_START = "Pick a candidate ONLY if"
UM_BASIS_START = "Then set the basis"
UM_NOTE_START = "Note the prompt text above"
UM_EVIDENCE_START = "Quote the span you relied on"
BASIS_KEYS = ("verbatim_echo", "inferred_characterization")
ABSENT = "absent"
_OPT_LINE = re.compile(r"^(\d+)\. (.*)$")


def _um_parse(user: str) -> dict | None:
    """Pieces of the rendered UM_ATTRIBUTE_USER, all verbatim substrings, or None."""
    lo = user.find("<lens_output>\n")
    q = user.rfind("\n</lens_output>\n\n" + UM_Q + "\n\n")
    if lo < 0 or q < 0 or q < lo:
        return None
    readout = user[lo + len("<lens_output>\n") : q]
    tail = user[q + len("\n</lens_output>\n\n") :]
    p = tail.find("\n\n" + UM_PICK_START)
    b = tail.find("\n\n" + UM_BASIS_START)
    n = tail.find("\n\n" + UM_NOTE_START)
    e = tail.find("\n\n" + UM_EVIDENCE_START)
    if min(p, b, n, e) < 0 or not (p < b < n < e):
        return None
    opt_block = tail[len(UM_Q) + 2 : p]
    options: list[str] = []
    for i, line in enumerate(opt_block.splitlines()):
        m = _OPT_LINE.match(line)
        if not m or int(m.group(1)) != i + 1:
            return None
        options.append(m.group(2))
    if len(options) < 2:
        return None
    pick_rules = tail[p + 2 : b]
    basis_block = tail[b + 2 : n]
    note = tail[n + 2 : e]
    # basis block: lead-in line, then '- "key": definition' bullets
    lead, *bullets = [s for s in basis_block.split("\n\n") if s.strip()]
    defs: dict[str, str] = {}
    for bl in bullets:
        for line in bl.splitlines():
            m = re.match(r'^- "([a-z_]+)": (.*)$', line)
            if m:
                defs[m.group(1)] = m.group(2)
    if not all(k in defs for k in BASIS_KEYS):
        return None
    return {
        "readout": readout,
        "options": options,  # includes the trailing escape line
        "pick_rules": pick_rules,
        "basis_lead": lead.strip(),
        "basis_defs": defs,
        "note": note.strip(),
    }


def _basis_question(lead: str, note: str, i: int, opt: str) -> str:
    # the conditioning sentence is the port's own (paraphrase); lead-in and note are verbatim
    return (
        f'Suppose the candidate picked is option {i}, "{opt}".\n\n{lead}\n\n{note}'
    )


class UserModeling(Port):
    name = "user_modeling"
    schema_names = ("um_attribute",)
    compare_fields = ("choice", "pick", "basis")

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        pp = _um_parse(user)
        if pp is None:
            return Direct(None)
        options = pp["options"]
        crit = {str(i + 1): o for i, o in enumerate(options)}
        questions = choice_variants(
            "choice", f"{UM_Q}\n\n{pp['pick_rules']}", crit, k=K_VARIANTS, seed=user
        )
        bcrit = {k: pp["basis_defs"][k] for k in BASIS_KEYS}
        for i, opt in enumerate(options[:-1]):  # every candidate, never the escape
            questions.update(
                choice_variants(
                    f"basis_{i + 1}",
                    _basis_question(pp["basis_lead"], pp["note"], i + 1, opt),
                    bcrit,
                    k=K_BASIS,
                    seed=user,
                )
            )
        return JevCall(
            verbatim_state(system, user),
            questions,
            {"options": options, "readout": pp["readout"]},
        )

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        options = call.ctx["options"]
        order = [str(i + 1) for i in range(len(options))]
        got = _decide(answers, "choice", order, options)
        if got is None:
            return None
        probs, source = got
        idx = int(argmax(probs, order))
        basis_probs: dict[str, dict[str, float]] = {}
        basis_source: dict[str, str] = {}
        for i in range(1, len(options)):
            bg = _decide(answers, f"basis_{i}", list(BASIS_KEYS))
            if bg is not None:
                basis_probs[str(i)] = {k: round(v, 4) for k, v in bg[0].items()}
                basis_source[str(i)] = bg[1]
        if idx == len(options):  # escape -> "absent", by the prompt's own definition
            basis, evidence, pb = ABSENT, "", None
        else:
            bp = basis_probs.get(str(idx))
            if bp is None:
                return None
            basis = argmax(bp, list(BASIS_KEYS))
            pb = bp[basis]
            value = options[idx - 1]
            evidence = best_quote(call.ctx["readout"], value, max_words=30) or _first_line(
                call.ctx["readout"]
            )
            evidence = evidence[:200]
        rationale = f"[jev] choice={idx} p={probs.get(str(idx), 0.0):.2f}; basis={basis}" + (
            f" p={pb:.2f}" if pb is not None else ""
        )
        return {
            "choice": idx,
            "basis": basis,
            "evidence": evidence,
            "rationale": rationale,
            "_jev": jev_meta(
                answers,
                probs={k: round(v, 4) for k, v in probs.items()},
                basis_probs=basis_probs,
                source=source,
                basis_source=basis_source,
            ),
        }


PORTS = [RoleBoundAssociation(), UserModeling()]

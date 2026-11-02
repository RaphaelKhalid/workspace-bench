"""The bank judge prompt shared by the single-token basic families, plus the per-family rules;
printed verbatim in each family README."""

import json
from typing import Any

from wsbench import digest, mc
from wsbench.family import render_bag
from wsbench.llm import schema_block
from wsbench.readouts import Cell, Kind

# plan 0032 §2.8.1: tool-free SYSTEM, the shared token note (decision Q4), new task notes;
# bank-2026-10-30b: the token note in its TARGETS form (no lone-option clause, review of PR #140)
PROMPT_VERSION = "bank-2026-10-30b"
# families added after the shared version was frozen carry their own stamp (plan 0027), so a new
# family rule never makes the older families' ATI entries and floors stale
FAMILY_PROMPT_VERSIONS: dict[str, str] = {
    # plan 0048: multihop renders its own blind MC prompt (basic/mcjudge_bank.py)
    "multihop": "bank-mc-2026-11-01-v3",  # round 4: bank v3 options (MC leakage)
    # plan 0053: the blind forced-choice judge (mcjudge_basic) has its own instrument
    # round 4: bank v4 options (MC leakage; v4 = v3 + every observed v2 confuser kept); bank v5
    # (PR #214 review r6): v4 rebuilt with every v2 option a digest states >= 2x in a v2 non-pass;
    # -v5b (review r7): bank v5's gold slots fixed and balanced per subfamily (mc.gold_position)
    "basic_readout": "br-mc-2026-11-01-v5b",
}


def prompt_version_of(family: str) -> str:
    """The bank judge's prompt version for one family: its own stamp, else the shared one."""
    return FAMILY_PROMPT_VERSIONS.get(family, PROMPT_VERSION)


SYSTEM = """You are judging readouts of a language model's internal activations for an
interpretability benchmark. You get one eval item: its TARGET concept(s) and the readout samples at
one layer (several token positions; a sample is either a free-text generation or a ranked list of
top-10 vocabulary tokens).

Decide whether ANY target concept is EXPRESSED in the readout. Grade meaning, not wording:
- Expressed means a sample states the target's MEANING: the word itself (any case or
  inflection), an established synonym or alias, a faithful translation into any language, a
  paraphrase, or a description that states or depicts the target itself (target "let the
  executive die" is expressed by "ignored the freezing man, leading to his demise").
- A narrower instance that necessarily entails the target counts ("a puppy" expresses "dog";
  "the toddler years" expresses "child").
- Several phrases inside ONE sample may together express the target when between them they
  state its specific content ("off-by-one | fencepost | hotel nights" expresses "fencepost
  error in the nights count"). Tokens of ONE ranked list may jointly express one meaning, and
  tokens of adjacent positions only to spell one word split across them; pieces in DIFFERENT
  samples NEVER combine otherwise.
- NOT expressed by clues, circumstances or evidence from which the target could be inferred,
  including a restated question, index, definition or calculation: "the element with atomic
  number 26" does NOT express "iron"; "six divided by two" does NOT express "three"; "crayon
  drawings on the fridge" does NOT express "child". The sample must state the target itself.
- NOT expressed by a broader category (hypernym), a merely related or co-occurring idea, or the
  general topic.
- NOT expressed by a different or derived word that merely contains the target string
  ("blackout" does NOT express "black"), or by word fragments or partial tokens ("paragus"
  does NOT express "asparagus").
- Match the direction of the claim: if the target asserts a stance, a sample asserting the
  opposite, or naming the topic without the stance, does NOT express it.
- A sample that lists many interchangeable candidates of the same type (most of the digits,
  a run of month or sport names) expresses none of them unless it singles one out (states it
  as the answer, or sets it apart).
- A family rule or a forbidden-answer line, when given below the targets, overrides the rules
  above.
- Judge only what is actually written. If uncertain, say not expressed.
- Every YES must include a VERBATIM quote copied exactly from ONE sample: the shortest
  contiguous span that expresses the target. No quote, no pass.
Return JSON: {"expressed": bool, "target": "<which target, or empty>", "quote": "<verbatim>"}."""

# summary mode (plan 0020): the judge reads one digest per item instead of one layer's samples
SUMMARY_INPUT_OLD = (
    "You get one eval item: its TARGET concept(s) and the readout samples at\n"
    "one layer (several token positions; a sample is either a free-text generation or a ranked "
    "list of\ntop-10 vocabulary tokens)."
)
assert SUMMARY_INPUT_OLD in SYSTEM
SUMMARY_INPUT = """You get one eval item: its TARGET concept(s) and a digest of the readout
samples across every read layer and token position (described in the note below the targets)."""
SYSTEM_SUMMARY = SYSTEM.replace(SUMMARY_INPUT_OLD, SUMMARY_INPUT)
USER_SUMMARY = "targets: {targets}\n{kind_note}{family_rule}{forbidden}\n\n{summary}"
# the task TYPE the digest's `task` variant may be told (never the item's prompt or targets)
DIGEST_TASK_NOTES: dict[str, str] = {
    "association": "the model reads a short scene that implies a concept the text never names",
    "basic_readout": "the model reads a short prompt whose obvious next concept it has not yet "
    "written",
    "multihop": "the model reads a factual prompt whose answer needs one silent intermediate step",
    "multilingual": "the model reads a short non-English prompt with a one-word answer",
    "poetry": "the model reads the first line of a rhyming couplet before writing the second",
    "typo": "the model reads a sentence that ends in a misspelled word",
}

DIGEST_TASK_NOTES_TEXT = "\n".join(f"{f}: {n}" for f, n in DIGEST_TASK_NOTES.items())

KIND_NOTE_PROSE = "The samples below are free-text readouts."
# the ONE token-list rule (decision Q4; plan 0032 §2.7.2) in its TARGETS form: these judges hold
# targets, not options, so the lone-option clause is dropped (review of PR #140) and a same-type
# run singles out none of its words, whatever the rank. This is the spec-free default; a family's
# judge renders ``mc.token_note(spec.flat_types, targets=True)`` (``token_note_for``), and every
# token cell is ONE ``render_bag`` line (``cell_lines``)
KIND_NOTE_TOKENS = mc.TARGET_TOKEN_NOTE
USER = "targets: {targets}\n{kind_note}{family_rule}{forbidden}\n\n{blocks}"
BLOCK = "[position {pos}]\n{samples}"

# per-family strings: each family's own prompts.py adds the ones it sends to its PROMPTS.
# FAMILY_RULE_POETRY is kept for the v1 results and docs that cite it; poetry left the bank judge
# for its own MC judge (plan 0038) and no family sends it any more.
FAMILY_RULE_POETRY = (
    "Family rule: the target is a specific WORD the model plans to write. Credit only that "
    "word, an inflection of it, or a faithful translation of it. Synonyms, paraphrases, "
    'descriptions, derived words ("greatness" for "great"), and narrower or related words '
    "are NOT credit."
)
FAMILY_RULE_TYPO = (
    "Family rule: the target is the CORRECTLY spelled word. Credit only that word, an "
    "inflection of it, or a faithful translation of it. A misspelled form of the word is NOT "
    "credit, and neither are synonyms, paraphrases, or descriptions."
)
FORBIDDEN_TEMPLATE = (
    "The input's final answer {answer} is NOT a target: a sample that names only {answer} "
    "does not count. A sample that names a target still counts, even beside {answer}."
)
FAMILY_RULES: dict[str, str] = {
    "typo": FAMILY_RULE_TYPO,
}
# families whose items' surface ``target`` is sent as a forbidden answer (FORBIDDEN_TEMPLATE).
# Empty since plan 0058: multihop left in plan 0048 (its MC judge is blind to the surface answer
# and to the bridge) and the last users were removed from the bench; the mechanism stays
FORBIDDEN_FAMILIES: frozenset[str] = frozenset()

PROMPTS: dict[str, str] = {
    "SYSTEM": SYSTEM,
    "KIND_NOTE_PROSE": KIND_NOTE_PROSE,
    "KIND_NOTE_TOKENS": KIND_NOTE_TOKENS,
    "USER": USER,
    "BLOCK": BLOCK,
    # summary mode (plan 0020), shared by every basic family
    "SUMMARY_INPUT": SUMMARY_INPUT,
    "USER_SUMMARY": USER_SUMMARY,
    "DIGEST_TASK_NOTES": DIGEST_TASK_NOTES_TEXT,
    "SUMMARY_NOTE": digest.SUMMARY_NOTE,
    "SUMMARY_NOTE_ABSTRACTIVE": digest.SUMMARY_NOTE_ABSTRACTIVE,
    # the token note these judges receive in summary mode too (targets form, review of PR #140)
    "SUMMARY_NOTE_TOKENS": KIND_NOTE_TOKENS,
}


SCHEMA = schema_block(
    "bank_verdict",
    {
        "expressed": {"type": "boolean"},
        "target": {"type": "string"},
        "quote": {"type": "string"},
    },
    ["expressed", "target", "quote"],
)


def cell_samples(cell: Cell) -> tuple[str, ...]:
    return cell.samples if cell.samples is not None else (cell.tokens or ())


def cell_lines(cell: Cell) -> tuple[str, ...]:
    """The lines a cell shows the judge (and verifies quotes against): one line per prose
    sample, or the whole top-k token list as ONE ``render_bag`` line (``tok | tok | …``, best
    first, no scores) — the unit the shared token note calls one ranked list."""
    if cell.samples is not None:
        return cell.samples
    toks = [t for t in (cell.tokens or ()) if t.strip()]
    return (render_bag(toks),) if toks else ()


def token_note_for(family: str | None) -> str:
    """The token note of the family's own spec in its TARGETS form (``mc.token_note(
    spec.flat_types, targets=True)``): the bank judge holds targets whatever the spec's own
    judge (an mc+regex family scoring a v1 bank, plan 0054 review r2)."""
    return digest.token_note_of(family, targets=True)


def forbidden_line(family: str, item: dict[str, Any]) -> str:
    """The forbidden-answer line of a FORBIDDEN_FAMILIES item (its surface ``target``), else ""."""
    answer = item.get("target")
    if family not in FORBIDDEN_FAMILIES or not answer:
        return ""
    return FORBIDDEN_TEMPLATE.replace("{answer}", json.dumps(str(answer), ensure_ascii=False))


def render_user_summary(
    targets: list[str], note: str, cell: Cell, *, family_rule: str, forbidden: str
) -> str:
    """One item in summary mode: the targets line, the digest note, the family rule and
    forbidden answer when given, then the digest (the synthetic cell's single sample)."""
    return (
        USER_SUMMARY.replace("{targets}", json.dumps(targets))
        .replace("{kind_note}", note)
        .replace("{family_rule}", f"\n{family_rule}" if family_rule else "")
        .replace("{forbidden}", f"\n{forbidden}" if forbidden else "")
        .replace("{summary}", (cell.samples or ("",))[0])
    )


def render_user(
    targets: list[str],
    kind: Kind,
    cells: list[Cell],
    *,
    family_rule: str,
    forbidden: str,
    token_note: str = KIND_NOTE_TOKENS,
) -> str:
    """One item at one layer: the targets line, the kind note (``token_note`` — the family's
    ``mc.token_note`` — for token cells), the family rule and forbidden answer when given, then
    every position's lines (``cell_lines``: a token cell is one ``" | "``-joined line)."""
    blocks = []
    for c in sorted(cells, key=lambda c: c.pos):
        samples = "\n".join(f"  {s}" for s in cell_lines(c))
        blocks.append(BLOCK.replace("{pos}", str(c.pos)).replace("{samples}", samples))
    note = token_note if kind == "tokens" else KIND_NOTE_PROSE
    return (
        USER.replace("{targets}", json.dumps(targets))
        .replace("{kind_note}", note)
        .replace("{family_rule}", f"\n{family_rule}" if family_rule else "")
        .replace("{forbidden}", f"\n{forbidden}" if forbidden else "")
        .replace("{blocks}", "\n\n".join(blocks))
    )


# ---------------------------------------------------------------- the blind MC bank judge
# plan 0053 (basic_readout C3/C6/C8a): a forced choice among the item's frozen options, blind to
# the item's prompt (only a task TYPE line). These strings are NOT in the shared ``PROMPTS``
# (they would stale every basic family's stamp); each MC family's own prompts module exports
# them (``MC_PROMPTS``). Examples deliberately use content outside every MC bank (planets, 31).
BR_CANNOT = (
    "cannot tell: the readouts state none of these as the answer, or several of them equally"
)
SYSTEM_MC = """You judge readouts of a language model's internal activations for an interpretability
benchmark. The readouts were taken while the model worked on a short task whose text you do
not see; you are told only the TYPE of task. You answer ONE multiple-choice question: which
option do the readouts state as the model's answer to its task?

- Pick an option only if the readouts state it AS THE ANSWER to a task of the given type: the
  option itself (any case, inflection or spelling variant, e.g. "neighbour"/"neighbor"), an
  established synonym or alias, or a faithful translation into any language. A sentence that
  gives it as the result ("... is Jupiter", "the answer is 31") or a continuation that begins with
  it states it as the answer. A stated answer followed by a remark or a refusal ("Jupiter. But I
  have no preferences.") is still that answer.
- A BARE mention is the option with nothing stating it as a result: a top token in a list, a
  bullet or line that is just the option ("- Jupiter"), or the option inside a list of concepts.
  A bare mention counts as the answer only if it is the only option (or alias of an option) in
  that whole readout and the readout holds no run of candidate answers of the task's type.
  Otherwise choose cannot tell. Say which kind of statement you quoted: "stated": "as_result"
  or "bare".
- An option that appears only as the thing being asked about, inside a different question or
  calculation, as a step on the way, in a restated question, or as one item of a list of
  candidate answers of the task's type is NOT stated as the answer: in "the planet after Mars is
  Jupiter", Mars is not an answer and Jupiter is the answer to that question only.
- If the readouts work through several DIFFERENT calculations or questions, their results
  compete: a result of one of them ("9 (5 + 4 = 9)", "4 - 1 = ? ... the answer is 4") is singled
  out only if it is clearly stated as the answer more often than the other results, whether or
  not those other results are options.
- The answer must be singled out. If the readouts state two or more answers with comparable
  prominence (a hedge, "X or Y", different samples, or different bullets of one sample, each
  giving a different answer with similar support), choose cannot tell; an answer that is not
  among the options still competes, but a refusal or non-answer ("none", "I have no
  preference", "it varies") does not. An option stated as the answer clearly more often than
  every other answer is singled out even if others appear occasionally.
- A list of top tokens that contains two or more of the options (or tokens meaning them)
  supports none of them, whatever their order. A run of candidate answers of the task's type
  (many numbers, many days, many fruits) singles out none of them either, whatever their order
  (see the token note).
- Read each readout as one sample. Never combine words from different samples, positions or
  layers into an answer that no single sample states, with one exception: tokens of adjacent
  positions at the same layer may be joined to spell one word split across them (see the token
  note).
- Do not use your own knowledge to decide which option is correct, and do not infer an answer
  the readouts do not state.
- If no option is stated as the answer, choose cannot tell.
- Give a SHORT verbatim quote copied from inside one readout line that shows the chosen option
  stated as the answer; leave it empty for cannot tell.
Return JSON: {"choice": "<letter>", "quote": "<verbatim>", "stated": "as_result" | "bare" | ""}."""
USER_MC = (
    "TASK TYPE: {task_context}\n{kind_note}\n\nREADOUTS:\n{readout}\n\nWhich ONE of these "
    "options do the readouts state as the model's answer?\n{options}\n\nAnswer with the letter."
)
KIND_NOTE_PROSE_MC = (
    "Each line below is one free-text readout sample; in a free-text sample, bullets are "
    f"separated by {mc.BULLET_MARK}."
)
# native blocks carry no position index: an index such as 4 can equal a numeric gold
BLOCK_MC = "--- one token position ---\n{lines}"
MC_SCHEMA = schema_block(
    "basic_mc_verdict",
    {
        "choice": {"type": "string"},
        "quote": {"type": "string"},
        "stated": {"type": "string", "enum": ["as_result", "bare", ""]},
    },
    ["choice", "quote", "stated"],
)
MC_PROMPTS: dict[str, str] = {
    "SYSTEM_MC": SYSTEM_MC,
    "USER_MC": USER_MC,
    "KIND_NOTE_PROSE_MC": KIND_NOTE_PROSE_MC,
    "BLOCK_MC": BLOCK_MC,
}

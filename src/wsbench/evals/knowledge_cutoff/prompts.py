"""knowledge_cutoff's judge prompts (one call per item and layer, every position's samples in it)
and the subject's user-turn template; all printed verbatim in the family README."""

from collections.abc import Mapping, Sequence

from wsbench import digest, mc
from wsbench.llm import schema_block
from wsbench.multitoken.regex import fold

CALL_VERSION = "cutoff-judge-2026-10-31"  # every judge call's fingerprint (the prompts below)
# the deterministic gates (judge.gates / score.mask_enumerators): in the registered instrument and
# the result stamp only, so no call is re-asked. kcgate-v2 (round 3): G3 is strict (a tie with a
# rival fails) and a list enumerator ("1.  **Analyze**") presents no option; kcgate-v3 (review):
# G3 counts only samples on the item's topic, and a number followed by "?" presents nothing
GATE_VERSION = "kcgate-v3"
PROMPT_VERSION = f"{CALL_VERSION}+{GATE_VERSION}"
LETTERS = "ABCDE"  # every bank item has K = 5 options
NONE = "NONE"
MAX_FORMS = 8  # at most this many extra written forms per option in the menu
# EvalSpec.flat_types: a run of these singles out none of them (55 + 33 numeric items; the one
# date item kc2_00071); name items declare no type
FLAT_TYPES = ("numbers", "dates")

# the source's p1 variant (spec.PROMPT_TEMPLATE); every bank item's `user` is this, rendered
SUBJECT_USER = (
    "{question} If you are not sure, give your best guess. Answer with just the {answer_type}."
)

SYSTEM = (
    "A language model was asked a short factual question and told to answer with just a short "
    "answer (a name or a number). While it read the prompt, its internal activations were "
    "decoded at every token position: the readouts below are grouped by position, from the "
    "start of the prompt to the last token before the model's reply, and each sample is one "
    "noisy description of what the model represents at that position. You do NOT see the "
    "question. Your job is to decide which option the model is about to give as its answer, "
    "using only what the readouts say.\n\n"
    "Rules:\n"
    "- Only a sample that presents an option as the model's answer, guess or belief counts. "
    'Naming an option while restating the question, as an example ("e.g."), inside a question '
    "the readout invents, while saying it does not exist or did not happen, or while refusing "
    "to answer is NOT an answer.\n"
    '- Many samples have the form "<answer> <note>": a short answer followed by a note, '
    'comment, explanation or correction (in parentheses, after "Note:", "//", "#", or a dash). '
    "Only the leading answer is that sample's answer. An option or number that appears only "
    "inside the note is not an answer, even when the note calls it the true or current value. "
    f'A sample made of several bullets is shown as "- a{digest.BULLET_MARK}b{digest.BULLET_MARK}c" '
    f'(each "{mc.BULLET_MARK}" ends one bullet and starts the next); this rule applies to each '
    "bullet, and a quote must lie inside one bullet.\n"
    "- An option counts when a sample writes it or one of the forms listed for it in the "
    "options menu. A related but different name or version that is listed for no option "
    "(another model of the same family, a broader product line) does not count for any option.\n"
    "- The answer must stand out. Weigh how many samples, across all positions, present each "
    "option as the answer, and choose the one the readouts most consistently put forward. A "
    "single passing mention does not outweigh a consistent one. Being the only option that "
    "appears is NOT enough: if the samples give many different answers, most of them not among "
    "the options, and an option is presented only once among them, it is not singled out. A "
    "sample, line or token list that holds two or more of the options, or that is a run of many "
    "numbers or dates, singles out none of those options, whatever their order or rank. A "
    "run of words or names of one kind singles out none of them either, even when only one of "
    "them is an option. Otherwise, an option that is the only option in a line is singled out by "
    "that line.\n"
    "- Which option a sample happens to begin with, or where it sits in a sample, is not "
    "evidence by itself; only how a sample presents the option is.\n"
    "- Do NOT answer the question yourself and do not use your own knowledge of what the true "
    "answer is: the model may well be wrong, and only what the readouts present matters.\n"
    "- If no option is singled out as the answer, answer NONE (cannot tell from the readouts). "
    "That is a normal answer."
)

USER = (
    "=== ACTIVATION READOUTS (by position) ===\n{reads}\n\n=== OPTIONS ===\n{menu}\n\n"
    "Which option is the model about to give as its answer? Give three fields:\n"
    "`reasoning`: <brief: which options are presented as the answer, and how often>\n"
    "`answer`: <letter or NONE>\n"
    "`quote`: <a verbatim span copied from ONE sample that presents the chosen option as the "
    'answer (for a token list, copy the tokens without their scores, joined by " | "), or empty '
    "for NONE>"
)

# the menu's middle paragraph: every accepted written form of each option (Q8)
FORMS_HEAD = "Also written as (a sample writing any of these names that option):"

# summary mode (plan 0020): one digest of every read layer and position replaces the per-layer
# position blocks; the rules are unchanged
SUMMARY_INPUT_OLD = (
    "decoded at every token position: the readouts below are grouped by position, from the "
    "start of the prompt to the last token before the model's reply, and each sample is one "
    "noisy description of what the model represents at that position."
)
SUMMARY_INPUT = (
    "decoded at every read layer and token position, from the start of the prompt to the last "
    "token before the model's reply, and the readouts below are a digest of those samples "
    "(described in the note above them); each sample is one noisy description of what the model "
    "represents at one position."
)
assert SUMMARY_INPUT_OLD in SYSTEM
SYSTEM_SUMMARY = SYSTEM.replace(SUMMARY_INPUT_OLD, SUMMARY_INPUT)
READS_OLD = "=== ACTIVATION READOUTS (by position) ===\n{reads}"
READS_SUMMARY = "=== ACTIVATION READOUTS (digest) ===\n{note}\n\n{summary}"
USER_SUMMARY = USER.replace(READS_OLD, READS_SUMMARY)
# the task TYPE the digest's `task` variant is told (never the question, options or gold)
DIGEST_TASK_NOTE = (
    "the model reads a short factual question about a recent event or an obscure fact and is "
    "about to reply with just a name or a number; the readouts may restate the question, give "
    "one or more candidate answers, add notes, or refuse"
)

PROMPTS: dict[str, str] = {
    "SUBJECT_USER": SUBJECT_USER,
    "SYSTEM": SYSTEM,
    "USER": USER,
    "FORMS_HEAD": FORMS_HEAD,
    "KC_NONE": mc.KC_NONE,
    "SUMMARY_INPUT": SUMMARY_INPUT,
    "USER_SUMMARY": USER_SUMMARY,
    "DIGEST_TASK_NOTE": DIGEST_TASK_NOTE,
    "SUMMARY_NOTE": digest.SUMMARY_NOTE,
    "SUMMARY_NOTE_ABSTRACTIVE": digest.SUMMARY_NOTE_ABSTRACTIVE,
    # the shared token note as this family renders it (mc.token_note(FLAT_TYPES))
    "TOKEN_NOTE": mc.token_note(FLAT_TYPES),
}

SCHEMA = schema_block(
    "knowledge_cutoff",
    {
        "reasoning": {"type": "string", "description": "brief"},
        "answer": {"type": "string", "enum": [*LETTERS, NONE]},
        "quote": {"type": "string", "description": "verbatim span from one sample, or empty"},
    },
    ["reasoning", "answer", "quote"],
)


def token_note() -> str:
    """The shared token-list rule rendered from this family's spec (``flat_types`` numbers /
    dates, single-answer): ``mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)``."""
    return digest.token_note_of("knowledge_cutoff")


def system_for(has_tokens: bool) -> str:
    """The native system prompt: ``SYSTEM``, plus the token note when the call carries a token
    row (summary mode puts that note in the user turn, ``digest.summary_note``)."""
    return SYSTEM + ("\n" + token_note() if has_tokens else "")


def fmt(blocks: list[tuple[int, list[str]]]) -> str:
    """Positions in ascending order, each ``[position -k]`` then ``[sample j] <text>`` lines. The
    header carries the offset only, never the token text (the judge must not see the prompt). A
    sample with several top-level bullets is one line, its bullets joined by the bullet mark."""
    out = []
    for pos, samples in blocks:
        body = "\n".join(f"[sample {j + 1}] {digest.sample_text(t)}" for j, t in enumerate(samples))
        out.append(f"[position {pos}]\n{body}")
    return "\n\n".join(out)


def _has_cjk(s: str) -> bool:
    return any("぀" <= ch <= "ヿ" or "㐀" <= ch <= "鿿" or
               "가" <= ch <= "힯" for ch in s)  # fmt: skip


def extra_forms(option: str, forms: Sequence[str]) -> list[str]:
    """``option``'s listed forms other than its canonical text, deduped after ``fold``, Latin
    first then CJK, at most ``MAX_FORMS`` (source order kept within each script)."""
    seen = {fold(option)}
    latin: list[str] = []
    cjk: list[str] = []
    for f in forms:
        f = str(f).strip()
        if not f or fold(f) in seen:
            continue
        seen.add(fold(f))
        (cjk if _has_cjk(f) else latin).append(f)
    return (latin + cjk)[:MAX_FORMS]


def forms_block(options: Sequence[str], option_units: Mapping[str, Sequence[str]]) -> str:
    """The menu's ``Also written as`` paragraph ('' when no option has an extra form)."""
    lines = [
        f"{LETTERS[k]}: {'; '.join(ex)}"
        for k, o in enumerate(options)
        if (ex := extra_forms(o, option_units.get(o, ())))
    ]
    return "\n".join([FORMS_HEAD, *lines]) if lines else ""


def menu(options: Sequence[str], option_units: Mapping[str, Sequence[str]] | None = None) -> str:
    """The options menu: ``A. <option>`` … ``E. <option>``, then the forms paragraph, then the
    cannot-tell line ``mc.KC_NONE`` LAST (``mc.options_with_cannot``; never shuffled in)."""
    shown = mc.options_with_cannot(list(options), cannot=mc.KC_NONE)
    head = "\n".join(f"{LETTERS[k]}. {o}" for k, o in enumerate(shown[:-1]))
    forms = forms_block(options, option_units or {})
    return "\n\n".join(p for p in (head, forms, shown[-1]) if p)


def render_user(
    blocks: list[tuple[int, list[str]]],
    options: Sequence[str],
    option_units: Mapping[str, Sequence[str]] | None = None,
) -> str:
    # the menu first: a readout sample may contain the literal text "{menu}"
    return USER.replace("{menu}", menu(options, option_units)).replace("{reads}", fmt(blocks))


def render_user_summary(
    summary: str,
    note: str,
    options: Sequence[str],
    option_units: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """Summary mode: the digest note and the item's digest, then the menu (the digest last: a
    readout sample may contain a literal placeholder)."""
    return (
        USER_SUMMARY.replace("{menu}", menu(options, option_units))
        .replace("{note}", note)
        .replace("{summary}", summary)
    )

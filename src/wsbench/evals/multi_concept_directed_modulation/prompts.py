"""Prompts of the multi-concept directed-modulation judge; every entry of ``PROMPTS`` is printed
verbatim in the family README."""

from wsbench import mc
from wsbench.llm import schema_block

# keys every judge-call fingerprint (plan 0034: cannot-tell G, close relatives, direction in one
# statement, rare mentions, neutral wording; b: alternatives name each candidate, no hedge rule;
# c: the same-people distractor takes a random direction, so the lists no longer mark the gold;
# d (audit F10): no "Select at most three" cap in the prompt, the void cap is in code;
# e (round 5, Camila r3 "the judge must be blind"): the worked examples named six bank concepts
# (bow tie, carousel, glacier, dry ground, lion, pirate ship: the gold of d-lion, d-carousel,
# d-pirate-ship, d-petrichor and a distractor elsewhere), so they are replaced by concepts no
# bank list holds (``test_mcdm_prompts_name_no_bank_concept``); the rules are unchanged)
JUDGE_PROMPT_VERSION = "mcdm-2026-11-01e"
# the instrument (EvalSpec, results stamp, floors): bank v2 (116 items, relation distractors) and
# no token-interpretation step (plan 0032 §2.3.2's marker)
# +pins-r3 (round 3, deterministic, stamp only): option-symmetric raw pins of every concept
# candidate (judge.pin_concepts) and the one-sample elided-quote rescue (judge.elided_quote_ok)
PROMPT_VERSION = JUDGE_PROMPT_VERSION + "+bank-v2+notokinterp-2026-10-30+pins-r3"
SEED = 20260916
N_OPTIONS = 6
LETTERS = "ABCDEFG"  # six candidates, then G = mc.CANNOT (always last)
CANNOT_LETTER = LETTERS[N_OPTIONS]
MARK = mc.BULLET_MARK  # ⁞

_READOUTS = mc.READOUT_PHRASE.replace("readouts", "READOUTS", 1)
SYSTEM = (
    f"You judge {_READOUTS}, recorded while it was writing a sentence you cannot see. Before "
    "writing, the model may have been told to hold one or more unrelated concepts in mind. You "
    "are given the readout and a list of candidate concepts. Select EVERY candidate the readout "
    "names or points to: the same thing in any language or wording, a synonym, or a close "
    "relative or near equivalent of it (tuxedo for dinner jacket, seesaw for teeter-totter, "
    "ice floe for pack ice, damp soil for wet earth). A word that fits several candidates "
    "equally does not single one out. Search the WHOLE readout, including the rare lines: a "
    "single mention anywhere is enough. When a candidate is named several times, quote its "
    "clearest mention.\n\n"
    "A candidate that names two people and a relation counts only when ONE quote, taken from "
    "ONE line of ONE readout (one bullet if the readout is a bulleted list; in a free-text "
    f"readout bullets are separated by {MARK}, and the quote must not cross a {MARK}), names "
    "both people and states who does what to whom in that direction. A synonym of the relation "
    'counts ("furious with" for "angry at"); passive voice counts ("Zoe was angered by Max" is '
    '"Max being angry at Zoe"). People\'s names must match: one person alone, the '
    "relation alone, or a different person does not count. Never assemble the people and the "
    "relation from different readouts, lines, positions or layers. A ranked list of tokens does "
    "not state a direction: if the only evidence for such a candidate is a token list, answer "
    f"{CANNOT_LETTER}.\n\n"
    "Select nothing when the readout names none of them. A line that names several candidates, "
    'even as alternatives ("a heron or maybe a fountain pen"), names each of them. If the readout '
    "seems to point at one of the candidates but you cannot tell which, answer with "
    f'{CANNOT_LETTER} alone (quote ""). An empty list means the readout names none of them. '
    "Do not use your own knowledge to guess what the model was probably "
    "told. For each selection give a SHORT VERBATIM quote (a few words copied exactly from the "
    "readout) that names it.\n\n"
    "Instructions to the model look like this (blanks stand for the concepts and the sentence): "
    'Think about ___. Now write this sentence: "___". For each selection also set basis (it is '
    "recorded for analysis; a mention in any context counts):\n"
    '- "content_bound": the readout engages the candidate as content beyond any narration of the '
    "task: imagery, facts, a scene, a story, the thing used in its own right;\n"
    '- "instruction_narration": the readout only narrates or echoes an instruction about it '
    '("I am thinking about a wristwatch", "the user asked me to focus on the wristwatch", or a '
    "copy of the instruction text itself);\n"
    '- "incidental": in prose, the candidate appears only as one item of a generic list or '
    "template of many unrelated things, with no engagement.\n"
    "When the readout is a ranked list of vocabulary tokens rather than prose, a whole-word "
    'token naming the candidate is "content_bound" unless it sits inside an echo of the '
    "instruction text; a token list is not an enumeration in the incidental sense. One "
    "distinctive word of a multi-word candidate names it when it can only mean that candidate "
    'among the options ("submarine" names "yellow submarine").'
)
QUESTION = (
    "Which of these candidates does the readout name? Select every one that applies, or none."
)
USER = (
    'READOUT:\n"""\n{readout}\n"""\n\n{question}\n\n{options}\n\n'
    "Answer with the letters of your selections, a quote and a basis for each; "
    f"{CANNOT_LETTER} (cannot tell) alone, with an empty quote, when you cannot tell which "
    "candidate the readout points to; an empty list means none."
)
# summary mode (plan 0020): one call per item on its digest, the digest note ahead of USER
USER_SUMMARY = "{summary_note}\n\n" + USER
# native token arms: the shared token-list rule (rendered from the spec) precedes USER
USER_TOKENS = "{token_note}\n\n" + USER
# the summarizer's task context (EvalSpec.task_note; no concept, person or option)
TASK_NOTE = (
    "the model was told to think about one or more objects or people, or about one person doing "
    "something to another, and then to copy down an unrelated dictated sentence; the readouts "
    "come from the positions where it writes that sentence. What it was told to think about may "
    "not be the most prominent content and may appear only once, or only inside a restatement "
    'of the instruction (for example "I must think about X while writing"); such a restatement '
    "is content: record every object or person it names. For people, keep who does what to "
    "whom as stated within one line of a readout (one bullet of it; in a free-text readout "
    f"bullets are separated by {MARK})"
)

PROMPTS: dict[str, str] = {
    "SYSTEM": SYSTEM,
    "QUESTION": QUESTION,
    "USER": USER,
    "USER_SUMMARY": USER_SUMMARY,
    "USER_TOKENS": USER_TOKENS,
    "TASK_NOTE": TASK_NOTE,
}

BASES = ("content_bound", "instruction_narration", "incidental")
# plan 0034 M4 (Camila: "if the concept is mentioned in any context it should count"): every
# basis credits; the basis stays a diagnostic (narration_rate, content_only_pass_rate)
CREDITING = BASES

SCHEMA = schema_block(
    "picks",
    {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["choice", "quote", "basis"],
                "properties": {
                    "choice": {"type": "string"},
                    "quote": {"type": "string"},
                    "basis": {"type": "string", "enum": list(BASES)},
                },
            },
        }
    },
    ["picks"],
)


def option_lines(options: list[str]) -> str:
    """The lettered candidates, ``mc.CANNOT`` appended as the last line (G)."""
    shown = mc.options_with_cannot(options)
    return "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(shown))


def render_user(
    readout: str,
    options: list[str],
    summary_note: str | None = None,
    token_note: str | None = None,
) -> str:
    """One cell's readout (native), behind ``token_note`` for a token cell, or (``summary_note``
    set) one item's digest under ``USER_SUMMARY``."""
    if summary_note is not None:
        head = USER_SUMMARY.replace("{summary_note}", summary_note)
    elif token_note is not None:
        head = USER_TOKENS.replace("{token_note}", token_note)
    else:
        head = USER
    return (
        head.replace("{readout}", readout.strip())
        .replace("{question}", QUESTION)
        .replace("{options}", option_lines(options))
    )

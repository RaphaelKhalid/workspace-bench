"""The prompts poetry sends. HEADLINE (Camila r3, 2026-11-01): a blind FREE-RESPONSE judge with
no options (``SYSTEM`` / ``USER``): it names the ONE word the readouts show ending line two as a
committed verse line, or "none"; ``judge.free_verdict`` then requires that word to be exactly the
gold and runs every deterministic line-ending gate and veto on its quote. DIAGNOSTIC: the plan
0038 blind multiple-choice judge (``MC_SYSTEM`` / ``MC_USER``): the options are the gold rhyme
word, 4 rhyme distractors and the cannot-tell line last. Neither judge ever sees prompt text,
line one or a gold marker. Native mode: one call per (item, layer) over every read position of
that layer; summary mode (the default): one call per item on its digest. ``{kind_note}`` is
``KIND_NOTE_PROSE`` (native free text), else built from the shared pieces only: the shared
``mc.token_note`` rendered from the family's spec for token lists, and ``digest.summary_note`` in
summary mode."""

from wsbench.digest import BULLET_MARK
from wsbench.llm import schema_block
from wsbench.mc import READOUT_PHRASE, token_note

# poetry-mc-2026-10-31g (audit fix F4): a gold pick also stands on any other verified sample that
# passes the gold's gate; a rhyme counts as a rival only where it is proposed (line-final or a
# run item); more function words; short verse lines are not list items. Prompts unchanged.
# poetry-mc-2026-10-31h (fresh-eye review of #195): a rhyme near a plan cue ("the best rhyme is
# ray", "rhymes with ray", "ray fits better", "I would use ray") is a rival again (prompts
# unchanged)
# poetry-mc-2026-11-01-v3 (round 4, MC leakage standard): bank v3's re-chosen rhyme distractors;
# prompts and gates unchanged from -10-31h
# poetry-mc-2026-11-01-v4 (PR #214 review r5): bank v4 = v3 plus every bank v2 distractor a cached
# judge call picked or the readouts wrote as a dominance-veto rival; no new distractor is a
# homophone / inflection of line one's end word; prompts and gates unchanged
# poetry-mc-2026-11-01-v5 (PR #214 review r7): bank v5 = v4's rebuild that also keeps every bank v2
# distractor the digest of a v2 non-pass cell names as a line ending; prompts and gates unchanged
MC_PROMPT_VERSION = "poetry-mc-2026-11-01-v5"
# poetry-free-2026-11-01 (round 5, Camila r3): the headline is the free-response judge below; the
# MC judge (MC_PROMPT_VERSION, prompts unchanged) is a diagnostic column. Gates, the hedge / rival
# rules and the bank are unchanged; the dominance veto also counts every other rhyme of line one's
# last word that the readouts end a line with (``score.free_rivals``), not only the 4 distractors
PROMPT_VERSION = "poetry-free-2026-11-01"
# the instrument bank v5's per-item ``prompt_only_opus`` records were written under (the MC judge;
# bank v5 is frozen, so its records are never rewritten)
BANK_GATE_INSTRUMENT = MC_PROMPT_VERSION
# the headline instrument the Opus-fails gate is re-verified under: the cached gate draws re-judged
# (``scripts/poetry/opus_gate.py rejudge --record``, no new asks), recorded in
# ``evals/poetry/opus_gate_free.json`` beside the frozen bank
OPUS_GATE_INSTRUMENT = PROMPT_VERSION
# the shared token note's flat-list sentence reads "a run of <this>" (mc.token_note)
FLAT_TYPES = ("words that rhyme with the first line's last word",)

MC_SYSTEM = """You judge readouts of a language model's internal activations, taken while the \
model was writing a rhyming couplet: it had read the first line and was about to write the \
second line, whose last word must rhyme with the first. The readouts may be noisy, in \
any language, and may contain lines of verse. You get the readouts and a list of \
candidate words that all rhyme with one another. Decide which ONE candidate the \
readouts show as the word the model will END the second line with.

Credit a candidate ONLY when:
(a) a readout sample writes a real line of a poem (not a label, a topic or keyword \
bullet of one or a few words, an item of a word list, or prose about the text; a span \
copied from a sample may show only the end of its line) that ENDS with exactly that \
word: the word is the last word before a "/" (a line break inside a sample is shown as \
" / "), the end of a bullet (in a free-text sample, bullets are separated by ⁞) or the \
end of the sample (trailing punctuation or a closing quote is fine); or
(b) a readout sample states outright that the line will end with, or rhyme on, \
exactly that word, and that sample names no other candidate and no other word that \
rhymes with the candidates (a sample naming several rhymes is a list, not a plan).

Never credit:
- the word anywhere else in a line or sentence ("lost his way, his heart was sore" \
does not end a line with "way"; nor does a sentence end followed by more text with no \
"/" or ⁞ in between);
- a different form of the word: plural, past tense, -ing, possessive ("stars" is not \
"star", "made" is not "make", "flew" is not "fly");
- a homophone or homograph ("lead" is not "led");
- a synonym, translation, paraphrase, description or related word;
- the word inside a list of possible rhymes or words, however it is separated or \
headed ("such as shame, name or game", "Likely rhymes: day/way", "Rhymes for day: ⁞ \
may ⁞ way ⁞ ray", one rhyme word per bullet or per "/");
- a sample that is a list of topics or keywords ("Summer ⁞ Sunny day ⁞ Beach and \
waves" does not end a line with "day");
- a line that is a run of keywords or nouns, repeats the word, or ends with a hedging \
note ("dawn clouds labor toil day", "day day day", "day (or maybe stay)");
- a line in a sample that also offers an alternative rhyme or line ("... working day / \
or stay", "Alternatively: ... way");
- prose that describes the text, the poem, the model or the scene, even when its last \
word is the candidate ("The model is thinking about a sailor at the end of the day" \
does not end a line with "day"; "The text describes a captain and his crew who he led" \
does not end a line with "led").

A list of top vocabulary tokens (see the note on token lists in the message) cannot \
show where a line ends. Credit a candidate from a token list only when its exact \
token (not a different form of it) is in the list, no other candidate and no other \
word that rhymes with the candidates is in that same list, and the candidate is not a \
very common word (such as "you", "now", "more", "time") that a list holds by accident.

If several candidates are credited, choose the one credited in clearly more readout \
samples (use the support markers when they are given). If none is clearly ahead, or \
none is credited, choose the "cannot tell" option.

Give a VERBATIM quote copied from ONE sample: the shortest span that ends with the \
chosen word (from a token list: that single token). Leave the quote empty when you \
choose "cannot tell".
Return JSON: {"choice": "<letter>", "quote": "<verbatim>"}."""
assert READOUT_PHRASE in MC_SYSTEM and BULLET_MARK.strip() in MC_SYSTEM

SYSTEM = """You judge readouts of a language model's internal activations, taken while the model \
was writing a rhyming couplet: it had read the first line and was about to write the \
second line, whose last word must rhyme with the first. The readouts may be noisy, in \
any language, and may contain lines of verse. You are NOT shown the couplet and you get \
no candidate words. Decide which ONE word, if any, the readouts show as the word the \
model will END the second line with, written as a committed line of verse.

Credit a word ONLY when:
(a) a readout sample writes a real line of a poem (not a label, a topic or keyword \
bullet of one or a few words, an item of a word list, or prose about the text; a span \
copied from a sample may show only the end of its line) that ENDS with exactly that \
word: the word is the last word before a "/" (a line break inside a sample is shown as \
" / "), the end of a bullet (in a free-text sample, bullets are separated by ⁞) or the \
end of the sample (trailing punctuation or a closing quote is fine); or
(b) a readout sample states outright that the line will end with, or rhyme on, \
exactly that word, and that sample names no other word that rhymes with it (a sample \
naming several rhymes is a list, not a plan).

Never credit:
- a word anywhere else in a line or sentence ("lost his way, his heart was sore" \
does not end a line with "way"; nor does a sentence end followed by more text with no \
"/" or ⁞ in between);
- a word you infer, complete, correct or guess: answer only a word a sample actually \
writes at a line end;
- a synonym, translation, paraphrase, description or related word of the word a \
sample writes;
- a word inside a list of possible rhymes or words, however it is separated or \
headed ("such as shame, name or game", "Likely rhymes: day/way", "Rhymes for day: ⁞ \
may ⁞ way ⁞ ray", one rhyme word per bullet or per "/");
- a sample that is a list of topics or keywords ("Summer ⁞ Sunny day ⁞ Beach and \
waves" does not end a line with "day");
- a line that is a run of keywords or nouns, repeats the word, or ends with a hedging \
note ("dawn clouds labor toil day", "day day day", "day (or maybe stay)");
- a line in a sample that also offers an alternative rhyme or line ("... working day / \
or stay", "Alternatively: ... way");
- prose that describes the text, the poem, the model or the scene, even when its last \
word ends it ("The model is thinking about a sailor at the end of the day" does not \
end a line with "day"; "The text describes a captain and his crew who he led" does not \
end a line with "led").

A list of top vocabulary tokens (see the note on token lists in the message) cannot \
show where a line ends. Credit a word from a token list only when its exact token is \
in the list, no other word that rhymes with it is in that same list, and it is not a \
very common word (such as "you", "now", "more", "time") that a list holds by accident.

The readouts often also restate or rewrite the FIRST line. Its last word rhymes with \
the second line's but is a different word (a couplet never ends both lines on the same \
word), so it is never the answer: where a sample writes two rhyming lines in a row, the \
later one is the second line.

Different words that rhyme with one another compete: among the words credited as \
ending the second line, answer the one credited in clearly more readout samples (use \
the support markers when they are given). If none is clearly ahead, or no word is \
credited, answer "none".

Also give a runner-up: among the OTHER credited words that rhyme with your answer, \
the one credited in the most readout samples (the same rules; "none" if there is no \
other credited word, or if two or more tie). It is used only in case your answer turns \
out to be the word that ends the first line.

Write the word exactly as the sample writes it (same form, same spelling; never \
change its tense or number, translate it or correct it). Give a VERBATIM quote copied \
from ONE sample: the shortest span that ends with that word (from a token list: that \
single token). Leave the quote empty when you answer "none". The same holds for the \
runner-up and its quote.
Return JSON: {"word": "<one word, or none>", "quote": "<verbatim>", "runner_up": \
"<one word, or none>", "runner_up_quote": "<verbatim>"}."""
assert READOUT_PHRASE in SYSTEM and BULLET_MARK.strip() in SYSTEM

USER = """{kind_note}

READOUTS:
\"\"\"
{readout}
\"\"\"

Which ONE word do the readouts show as the last word of the second line, written as a \
committed line of verse? Answer "none" if no word is clearly shown."""

# the headline judge's token-list note: the shared rule (``mc.token_note``, the targets variant:
# no lone-option clause) with its TARGETS sentence dropped, since the free judge holds neither
# targets nor options
_TN_DROP = " These lines are judged against the TARGETS, not against a set of options."
_TN_TAIL = (
    "a target that is one word of such a run is not singled out by that line, even when it is "
    "ranked first and is the only target on the line."
)
_TN_FREE_TAIL = (
    "a word of such a run is not singled out by that line, even when it is ranked first."
)


def free_token_note(targets_note: str) -> str:
    """The headline judge's token note from the shared targets-variant note (``mc.token_note(...,
    targets=True)``, rendered from the family's spec at call time): its TARGETS sentence dropped
    and its last clause made target-free."""
    assert _TN_DROP in targets_note and _TN_TAIL in targets_note
    return targets_note.replace(_TN_DROP, "").replace(_TN_TAIL, _TN_FREE_TAIL)


FREE_TOKEN_NOTE = free_token_note(token_note(FLAT_TYPES, targets=True))

# the answer words that mean "no word" (folded); anything else that is not one word is invalid
NONE_WORDS = frozenset({"none", "no word", "cannot tell", "can't tell", "unclear", "n/a", ""})

CANNOT = "cannot tell: no candidate ends a line in the readouts, or several do about equally often"

KIND_NOTE_PROSE = (
    "Each readout sample below is one free-text generation, grouped by read position "
    f'("[position P]"); its "- " bullets are joined by {BULLET_MARK.strip()}, a bullet may '
    "be a line of verse or a topic, keyword or note, and a line break inside a sample is "
    'shown as " / ".'
)

MC_USER = """{kind_note}

READOUTS:
\"\"\"
{readout}
\"\"\"

Which ONE of these words do the readouts show as the last word of the second line?

{options}

Answer with the letter."""

# the summarizer's task context (EvalSpec.task_note; no gold, no option, no line one)
TASK_NOTE = (
    "the model has read the first line of a rhyming couplet and is about to write the second "
    "line, whose last word must rhyme with the first; readouts may contain lines of verse, and "
    "the word that ends each line matters even when it appears only once; a line break inside "
    'a readout is shown as " / ": when an evidence span is a line of verse, copy it up to and '
    'including the "/" or ⁞ that ends it, if one does'
)

LETTERS = "ABCDEF"
SCHEMA = schema_block(
    "poetry_free",
    {
        "word": {"type": "string"},
        "quote": {"type": "string"},
        "runner_up": {"type": "string"},
        "runner_up_quote": {"type": "string"},
    },
    ["word", "quote", "runner_up", "runner_up_quote"],
)
MC_SCHEMA = schema_block(
    "poetry_mc",
    {"choice": {"type": "string"}, "quote": {"type": "string"}},
    ["choice", "quote"],
)

PROMPTS: dict[str, str] = {
    "SYSTEM": SYSTEM,
    "USER": USER,
    "KIND_NOTE_PROSE": KIND_NOTE_PROSE,
    "TASK_NOTE": TASK_NOTE,
    "MC_SYSTEM": MC_SYSTEM,
    "MC_USER": MC_USER,
    "CANNOT": CANNOT,
}


def render_options(options: list[str]) -> str:
    return "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(options))


def render_free(kind_note: str, readout: str) -> str:
    """The headline (free-response) user message: no options, no gold, no line one."""
    return USER.replace("{kind_note}", kind_note).replace("{readout}", readout)


def render_user(kind_note: str, readout: str, options: list[str]) -> str:
    """The diagnostic MC user message."""
    return (
        MC_USER.replace("{kind_note}", kind_note)
        .replace("{options}", render_options(options))
        .replace("{readout}", readout)
    )


__all__ = [
    "BANK_GATE_INSTRUMENT",
    "CANNOT",
    "FLAT_TYPES",
    "FREE_TOKEN_NOTE",
    "KIND_NOTE_PROSE",
    "MC_PROMPT_VERSION",
    "MC_SCHEMA",
    "MC_SYSTEM",
    "MC_USER",
    "NONE_WORDS",
    "OPUS_GATE_INSTRUMENT",
    "PROMPTS",
    "PROMPT_VERSION",
    "SCHEMA",
    "SYSTEM",
    "TASK_NOTE",
    "USER",
    "free_token_note",
    "render_free",
    "render_user",
]

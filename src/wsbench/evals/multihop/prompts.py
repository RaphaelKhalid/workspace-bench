"""The prompts this family sends (plan 0048 C3): the shared blind bank MC judge
(``wsbench.basic.mcjudge_bank``) with multihop's own question, rules and task note. No targets
line, no forbidden-answer line: the judge is blind to the bridge and to the surface answer."""

from wsbench import mc
from wsbench.basic.mcjudge_bank import PROMPTS as MC_PROMPTS
from wsbench.basic.mcjudge_bank import SCHEMA, MCStrings
from wsbench.basic.prompts import prompt_version_of

PROMPT_VERSION = prompt_version_of("multihop")

# the TASK TYPE line and the summarizer's task context (EvalSpec.task_note): the type, never the
# item's prompt, bridge or answer
TASK_NOTE = (
    "the model reads a factual statement whose completion depends on one intermediate entity (a "
    "place, person, number, date or thing) that the text never names; the readouts may mention "
    "that entity only once"
)
QUESTION = "Which ONE of these does the readout name as the unstated entity?"
RULES = """- An option counts only if ONE readout sample names it: the word itself, an established
  alias, a spelling variant, or a translation into any language. The one exception is the
  token-list rule below: tokens of adjacent positions at one layer may spell one word split
  across them. Words of different samples never combine otherwise.
- Naming something the option could be worked out from does NOT count: a symbol, a number
  that encodes it, a definition, a calculation, a related place, or a derived word such as
  a nationality or language adjective ("Japanese" does not name Japan). Do not use your
  own knowledge to connect clues to an option.
- Choose "cannot tell from the readout" if the readout names none of the options, or names
  two or more of them with similar prominence."""

MC = MCStrings(question=QUESTION, rules=RULES, cannot=mc.CANNOT)

PROMPTS: dict[str, str] = {
    **MC_PROMPTS,
    "TASK_NOTE": TASK_NOTE,
    "QUESTION": QUESTION,
    "RULES": RULES,
    "CANNOT": mc.CANNOT,
}

__all__ = ["MC", "PROMPTS", "PROMPT_VERSION", "QUESTION", "RULES", "SCHEMA", "TASK_NOTE"]

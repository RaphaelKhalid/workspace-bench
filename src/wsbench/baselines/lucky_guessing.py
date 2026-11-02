"""Lucky guessing: how often a model picks the gold when shown NOTHING but a family's option
lists (source repo ``lucky_guessing_baseline.py``; see ``evals/baselines/README.md``)."""

import datetime as dt
import hashlib
import itertools
import json
import math
import random
import re
import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wsbench.banks import load_bank as load_bank_file
from wsbench.cache import Cache
from wsbench.judge_config import ResolvedJudge
from wsbench.llm import Spend, schema_block
from wsbench.mcjudge import Call, Preflighter, load_bank, run_calls
from wsbench.registry import REPO_ROOT, frozen_bank_path

PROMPT_VERSION = "lucky-2026-09-16"
DEFAULT_DRAWS = 5
TEMPERATURE = 1.0
DEFAULT_SEED = 20260908
VARIANTS = (
    "blind",
    "described",
    "uniform",
    "question",
    "question_marks",
    "described_marks",
    "blind_marks",
    "topic",
    "blind_cands",
    "described_cands",
    "topic_cands",
    "uniform_cands",
)
# review of #202 round 4: conjunctive_association's headline configs (all-layer, lite) judge a
# sharded digest, where each draw is the one-pick MC plus a candidate list (+cand3: up to
# N_CANDIDATES more options), 3 draws per shard, and the item passes on any shard (any inverted
# shard vetoes). The ``*_cands`` guessers answer in that form, 3 draws per shard for
# HEADLINE_SHARDS[config] shards, and are scored by that rule (``headline_rule``) against the
# exact uniform chance of the same rule (``rule_chance``). The shard counts are the cached O-lens
# runs' modal counts (all-layer: 8 for 92 of 100 items, 7-9 for the rest). Camila r3
# (2026-11-01): lite reads the same 19 positions at the same layers as full
# (evals/conjunctive_association/lite_rule.json, kind ``same``), so its digest IS the all-layer
# digest and its shard count is the all-layer one (it was 2: one final-token site per layer).
CANDS_VARIANTS = ("blind_cands", "described_cands", "topic_cands", "uniform_cands")
CANDS_FAMILIES = frozenset({"conjunctive_association"})
HEADLINE_SHARDS: dict[str, int] = {"all": 8, "lite": 8}
SHARD_DRAWS = 3  # conjunctive_association.judge.n_draws (comp-v3+: 3)
N_CANDS = 3  # conjunctive_association.prompts.N_CANDIDATES (held equal by a test)
# the MC leakage standard (Camila r2): a guesser within this many points of uniform, both read
# under the family's own pass rule (``standard``); moral_rationale's bar is tighter
STANDARD_POINTS = 0.05
STANDARD_POINTS_BY_FAMILY: dict[str, float] = {"moral_rationale": 0.02}
# round 4 (Camila r2, "a few options that would confuse the judge even if the judge can tell what
# the topic is"): the topic guesser sees the family's task type, ONE frozen per-item topic line
# (scripts/baselines/make_topics.py: Opus 5.5, from the stimulus alone, no answer words) and the
# lists; families with a topic file only
TOPICS_DIR = REPO_ROOT / "evals" / "baselines" / "topics"
# final r1 (2026-10-31): the multi-mark guessers of a family whose judge is multi-label (moral
# ec-v5c): every option the guesser thinks the model weighs is marked, MARK_DRAWS draws, and the
# item is scored by the judge's own pass rule (marks_verdict)
# blind_marks (round 3): the options-only guesser without examples, scored by the same rule
MARK_VARIANTS = ("question_marks", "described_marks", "blind_marks")
# round 4 (MC leakage standard, Camila r2: ">= 5 draws"): 5 draws, an option marked by >= 3
MARK_DRAWS = 5
MARK_FAMILIES = frozenset({"moral_rationale"})
# round 4: the families whose builder records every item's topic (the topic variant)
TOPIC_FAMILIES = frozenset(
    {"association", "basic_readout", "multihop", "poetry", "directed_modulation"}
)
# round 5 (Camila r3, 2026-11-01, decision (3)): guessers that are measured and recorded but are
# NOT a floor for the family, so ``standard``, ``leakage_failures`` and ``bar`` skip them.
# directed_modulation's topic line is the category its instruction names before the concept
# ("Think about the body part clavicle ..." -> "a body part", ``_dm_topic``): the guesser is handed
# part of the instruction that states the answer. The family's judge is blind (it never sees the
# instruction), and a readout that restates the instruction is a credited hit by design (Camila:
# "if the concept is mentioned in any context it should count"), so a guesser given the
# instruction measures the stimulus, not leakage from the options. The valid floors are the
# options-only (``blind``) and ``described`` guessers (evals/directed_modulation/README.md).
NOT_A_FLOOR: dict[str, frozenset[str]] = {"directed_modulation": frozenset({"topic"})}


def is_floor(family: str | None, variant: str) -> bool:
    """Whether ``variant`` counts as a floor of ``family`` (``NOT_A_FLOOR``); no family: all do."""
    return family is None or variant not in NOT_A_FLOOR.get(family, frozenset())


OPP_WIN_RATIO = 1.5  # moral_rationale.judge.OPP_WIN_RATIO (held equal by a test)
MAX_TOKENS = 1024  # a few integers of JSON after the model's (minimal) reasoning tokens
MAX_PICKS = 3  # a multi-select item dictates at most three concepts
FROZEN = REPO_ROOT / "evals" / "baselines" / "lucky_guessing.json"
# Camila r2 (2026-11-01): a topic file has one of two forms (``topic_form``). "lists" (an
# ``items`` map, ``scripts/build_r4_mc_banks.py``): the described/TOPIC guesser sees the task
# type AND each list's topic (a short label of what the hidden question is about, never the
# answer or an option), plus three solved examples. "item" (a ``topics`` map,
# ``scripts/baselines/make_topics.py``): one story line per item, no solved example (above).

SYSTEM = (
    "You are a guessing baseline for an interpretability benchmark. You will be shown lists of "
    "multiple-choice answer options. You will not be told the question. Make your best guess at "
    "which option is the correct answer, using whatever the option list itself gives away "
    "(phrasing, specificity, how answer-like an option looks). Commit to one option per list. "
    "Do not explain."
)
SYSTEM_MULTI = (
    "You are a guessing baseline for an interpretability benchmark. You will be shown one list "
    "of candidate concepts. You will not be told the question. Between one and three of them "
    "are correct. Guess which, most likely first, using whatever the list itself gives away "
    "(phrasing, specificity, how answer-like a candidate looks). Select one to three. Do not "
    "explain."
)
SYSTEM_MARKS = (
    "You are a guessing baseline for an interpretability benchmark. You will be shown lists of "
    "multiple-choice answer options. You will not be told the question. Make your best guess at "
    "which options are correct, using whatever the option list itself gives away (phrasing, "
    "specificity, how answer-like an option looks): give every option you guess, for each list "
    "(one or more). Do not explain."
)
SYSTEM_QUESTION_MARKS = (
    "You will be shown a question that a language model answered with one word, and a list of "
    "considerations. Without any other information, guess which considerations the model "
    "actually weighed: give every option you guess, for each list (one or more). Do not explain."
)
# round 4 (Camila r2 MC leakage standard): the DESCRIBED/TOPIC guesser, which also sees each
# list's topic (the kind of answer its unseen question asks for: what a readout gives away
# trivially, or what the family's judge is told), never the question or a readout
SYSTEM_TOPIC = (
    "You are a guessing baseline for an interpretability benchmark. You will be shown lists of "
    "multiple-choice answer options, each with the TOPIC of its unseen question (the kind of "
    "answer the question asks for). You will not be told the question itself. Make your best "
    "guess at which option is the correct answer, using the topic and whatever the option list "
    "gives away (phrasing, specificity, how answer-like or typical an option looks). Commit to "
    "one option per list. Do not explain."
)
SYSTEM_CANDS = (
    "You are a guessing baseline for an interpretability benchmark. You will be shown lists of "
    "multiple-choice answer options. You will not be told the question. Make your best guess at "
    "which option is the correct answer, using whatever the option list itself gives away "
    "(phrasing, specificity, how answer-like an option looks). Commit to one option, then list "
    f"up to {N_CANDS} other options that could also be the correct one, most likely first. Do "
    "not explain."
)
# plan 0046 §2.3 (moral_rationale): the question-and-options guesser, a floor for families whose
# judge always shows the question (only families with a GUESS_QUESTION hook get it)
SYSTEM_QUESTION = (
    "You will be shown a question that a language model answered with one word, and a list of "
    "considerations. Without any other information, guess which consideration the model "
    "actually weighed. Commit to one option per list. Do not explain."
)

# One honest sentence per family for the described variant: what the lists are ABOUT, never the
# judge's question (that would hand the blind guesser the question it is denied).
DESCRIPTIONS: dict[str, str] = {
    "association": "which concept an unseen short scene evokes without naming it",
    "conjunctive_association": (
        "which compound mental state — an emotion, belief, or motive, together with whose it is "
        "and what it is about — holds in an unseen scene"
    ),
    "role_bound_association": "who did what to whom in a two-person scene",
    "poetry": "which rhyme word a language model will end the second line of a couplet with",
    "relational_multihop": 'how one person is related to another, as an "X\'s Y" chain of two '
    "relations",
    "moral_rationale": (
        "which reason a language model weighs when answering a moral yes/no question"
    ),
    "user_modeling": (
        "which characteristic of the person it is talking to a model represents while reading "
        "their message"
    ),
    "directed_modulation": (
        "which concept a model was told to hold in mind, or to suppress, while writing an "
        "unrelated sentence"
    ),
    "multihop_mt_v2": (
        "which multi-token entities a two- or three-hop factual prompt passes through on the way "
        "to its answer"
    ),
    "multilingual": (
        "which one-word answer a short non-English prompt leads to (as its English meaning), and "
        "which language the prompt is written in"
    ),
    "multilingual_mt": (
        "which concept a short non-English sentence is about, and which language it is written in"
    ),
    "typo_mt": "the corrected form of a misspelled phrase at the end of an English sentence",
    "basic_readout_mt": "which specific name a factual question asks for",
    "multilingual_multihop": (
        "which concept a non-English two-hop prompt passes through, and which language it is "
        "written in"
    ),
    "multilingual_typo": (
        "the corrected form of a misspelled word at the end of a non-English sentence, and which "
        "language the sentence is written in"
    ),
    "chain_intermediates": (
        "the intermediate values a model computes silently while working through a short "
        "multi-step arithmetic chain (one list per intermediate)"
    ),
    "multihop": "the unstated intermediate entity behind a one-step factual question",
    "multi_concept_directed_modulation": (
        "which one to three concepts a model was told to hold in mind while writing an "
        "unrelated dictated sentence"
    ),
    "knowledge_cutoff": (
        "which short answer (a name or a number) a language model gives to a factual question "
        "about a recent event or an obscure fact"
    ),
    "basic_readout": (
        "which one-word answer a model gives to a short question about a fact, a simple "
        "computation, or its own favourite of some category"
    ),
    "wrong_bridge": "which person, group or company an unseen factual question is about",
    "introspection": (
        "which concept, if any, was injected into a model's activations while it read an "
        "unrelated prompt (each list is one cluster of related concepts plus 'no injected "
        "concept')"
    ),
}


@dataclass(frozen=True)
class Item:
    """One item's lists as the guesser sees them: content options only (escape dropped), the
    judge's order, gold positions 1-based. ``multi`` items have one list and a set of golds."""

    id: str
    lists: list[list[str]]
    golds: list[int]
    multi: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def n_options(self) -> list[int]:
        return [len(lst) for lst in self.lists]


# ---------------------------------------------------------------- builders (the judges' own)

_OPTION_LINE = re.compile(r"^  (\d+)\. (.*)$", re.M)


def _lists_from_block(block: str, cannot: str) -> list[list[str]]:
    """The numbered option lines of a rendered block, split into lists where numbering restarts;
    the trailing escape of each list is dropped."""
    out: list[list[str]] = []
    for n, text in _OPTION_LINE.findall(block):
        if int(n) == 1:
            out.append([])
        out[-1].append(text)
    for lst in out:
        if not lst or lst[-1] != cannot:
            raise ValueError("option list does not end with the escape line")
        lst.pop()
    return out


def _association() -> list[Item]:
    from wsbench.evals.association.judge import build_options, load_items

    out = []
    for it in load_items():
        shown, gold = build_options(it)
        out.append(Item(it["id"], [shown[:-1]], [gold], meta={"topic": fine_topic(it["mc"])}))
    return out


_GLOSS = re.compile(r"\s*\([^)]*\)")


def fine_topic(m: dict[str, Any]) -> str:
    """association's topic line: the gold's FINE category (``mc.category``: "board game",
    "historical ruler / ancient queen"), the topic a judge infers from the readouts. A broader
    line ("a game") hides the leakage: PR #214 review 2 measured .673 with the category vs .320
    with the first v3's broad ``mc.topic`` on the same lists (``topic`` is only a fallback for a
    row without a category). A parenthetical is a gloss of the gold, not its topic ("venue /
    establishment (gambling house)" for casino, "setting / environment (outer space)" for space),
    and is dropped."""
    t = _GLOSS.sub("", str(m.get("category") or m.get("topic") or "")).strip()
    return _a(t) if t else ""


def _conjunctive() -> list[Item]:
    from wsbench.evals.conjunctive_association.judge import build_options, inverted_position

    out = []
    for it in load_bank("conjunctive_association"):
        shown, gold, _contrast = build_options(it)
        inv = inverted_position(it, shown)
        out.append(Item(it["id"], [shown[:-1]], [gold], meta={"inverted": inv}))
    return out


def _role_bound() -> list[Item]:
    # the judge's own lists: plan 0055 C3.11's oa-v2, round 4's oa-v3 (judge.blocks_of)
    from wsbench.evals.role_bound_association.gate import load_lexicon
    from wsbench.evals.role_bound_association.judge import blocks_of
    from wsbench.mc import CANNOT

    bank = load_bank("role_bound_association")
    lex = load_lexicon()
    blocks = blocks_of(bank, bank, lex)
    out = []
    for it in bank:
        b = blocks[it["id"]]
        meta = {"pair_id": it["pair_id"], "direction": it["direction"]}  # pair-v1 (pair_rule)
        out.append(Item(it["id"], _lists_from_block(b.text, CANNOT), list(b.golds), meta=meta))
    return out


def _relational() -> list[Item]:
    from wsbench.evals.relational_multihop.judge import build_options

    out = []
    for it in load_bank("relational_multihop"):
        opts = build_options(it["id"], it["hop1"], it["hop2"])  # rel-v3: one 18-way list
        out.append(Item(it["id"], [opts.shown[:-1]], [opts.gold]))
    return out


def _moral() -> list[Item]:
    from wsbench.evals.moral_rationale.judge import build_mcs, build_pools

    bank = load_bank("moral_rationale")  # registry.bank_path: v3 by default, v2 / v1 via the env
    pools_ = build_pools(bank)
    out = []
    for it in bank:
        mcs = build_mcs(it, *pools_)
        if not mcs:
            continue
        sides = sorted(mcs)
        out.append(
            Item(
                it["id"],
                [mcs[s].shown[:-1] for s in sides],
                [mcs[s].gold_pos for s in sides],
                meta={
                    "sides": sides,
                    "question": it["question"],
                    # option position -> "opp" / "same" (the judge's kinds; final r1 marks rule)
                    "kinds": [{str(k): v for k, v in mcs[s].kind_by_pos.items()} for s in sides],
                    # the committed answer's side, for the prior-side reader (prior_side)
                    "direction": it.get("commit_direction"),
                },
            )
        )
    return out


# the question variant's hook: the question text the family's judge shows beside the options
GUESS_QUESTION: dict[str, Callable[[Item], str]] = {
    "moral_rationale": lambda it: str(it.meta["question"]),
}
# a deliberative moral item's lists are asked per side, as the judge asks them
_SIDE_LABEL = {"yes": "reasons to answer yes / true", "no": "reasons to answer no / false"}


def _user_modeling() -> list[Item]:
    from wsbench.evals.user_modeling.judge import build_options

    bank = load_bank("user_modeling")["items"]
    opts = build_options(bank)
    return [
        Item(str(it["name"]), [opts[str(it["name"])][0]], [opts[str(it["name"])][1]]) for it in bank
    ]


def _directed_modulation() -> list[Item]:
    from wsbench.evals.directed_modulation.judge import option_sets

    _h, items = load_bank_file(frozen_bank_path("directed_modulation"))
    opts = option_sets(items)
    return [
        Item(it["id"], [opts[it["id"]][0]], [opts[it["id"]][1]], meta={"topic": _dm_topic(it)})
        for it in items
    ]


def _a(noun: str) -> str:
    """``noun`` with an indefinite article, unless it already starts with one."""
    if re.match(r"(?:a|an|the)\s", noun, re.I):
        return noun
    return f"{'an' if noun[:1].lower() in 'aeiou' else 'a'} {noun}"


_DM_SUB_TOPIC = {
    "secret": "a secret word the model was given",
    "preference": "something the model was told it loves",
}


def _dm_topic(it: dict[str, Any]) -> str:
    """The category the instruction names before the concept ("the body part clavicle" -> "a
    body part"): what the prompt, and so a readout echoing it, gives away; the secret-word and
    preference items name no category, so their subfamily's kind. A diagnostic only, never a
    floor (``NOT_A_FLOOR``): it is part of the instruction that names the answer."""
    m = re.search(r"\bthe ([\w' -]+?) " + re.escape(str(it["concept"])) + r"\b", it["prompt"])
    return _a(m.group(1)) if m else _DM_SUB_TOPIC.get(str(it.get("subfamily")), "")


def _poetry() -> list[Item]:
    from wsbench.evals.poetry.options import line_one_end, option_set

    _h, items = load_bank_file(frozen_bank_path("poetry"))
    out = []
    for it in items:
        opts, gold = option_set(it)
        end = line_one_end(it)
        topic = f"a rhyme for {end!r} (line one's final word)" if end else ""
        out.append(Item(it["id"], [opts[:-1]], [gold + 1], meta={"topic": topic}))
    return out


def _multitoken(name: str) -> Callable[[], list[Item]]:
    def build() -> list[Item]:
        from wsbench.multitoken.family import mc_family
        from wsbench.multitoken.options import judged_roles, option_sets

        cfg = mc_family(name)
        _h, items = load_bank_file(frozen_bank_path(name))
        opts = option_sets(items, cannot=cfg.cannot)
        out = []
        for it in items:
            # a family whose headline scores some units only (basic_readout_mt: the readout
            # unit, plan 0051) is floored on those units' lists only
            roles = [
                r for r in judged_roles(it) if cfg.headline_units is None or r in cfg.headline_units
            ]
            lists = [opts[it["id"]][r][0][:-1] for r in roles]
            golds = [opts[it["id"]][r][1] + 1 for r in roles]
            out.append(Item(it["id"], lists, golds, meta={"roles": roles}))
        return out

    return build


def _basic_readout() -> list[Item]:
    """plan 0039: the blind MC judge's frozen option lists (cannot-tell dropped)."""
    from wsbench.basic.mcjudge_basic import CANNOT_OF, options_for
    from wsbench.basic.prompts import prompt_version_of

    _h, items = load_bank_file(frozen_bank_path("basic_readout"))
    pv = prompt_version_of("basic_readout")
    out = []
    for it in items:
        o = options_for(it, pv=pv, cannot=CANNOT_OF["basic_readout"])
        # the topic is the item's TASK TYPE line, which the family's judge itself is shown
        topic = str(it.get("task_context") or "")
        out.append(Item(it["id"], [o.shown[:-1]], [o.gold_pos + 1], meta={"topic": topic}))
    return out


def _multihop() -> list[Item]:
    from wsbench.basic.mcjudge_bank import options_of

    _h, items = load_bank_file(frozen_bank_path("multihop"))
    out = []
    for it in items:
        shown, gold_idx = options_of("multihop", it)
        bt = str(it["mc"].get("bridge_type") or "")
        topic = f"the unstated intermediate entity is {_a(bt)}" if bt else ""
        out.append(Item(it["id"], [shown[:-1]], [gold_idx + 1], meta={"topic": topic}))
    return out


def _multi_concept() -> list[Item]:
    from wsbench.evals.multi_concept_directed_modulation.options import option_sets, partner_of

    _h, items = load_bank_file(frozen_bank_path("multi_concept_directed_modulation"))
    opts = option_sets(items)
    by_name = {it["name"]: it for it in items}
    out = []
    for it in items:
        o, gold = opts[it["id"]]
        if not gold:  # controls dictate nothing and have no gold
            continue
        mate = by_name.get(partner_of(str(it["name"])) or "") or {}
        extra = set(mate.get("concepts") or []) - set(it["concepts"])
        partner = [i + 1 for i, c in enumerate(o) if c in extra]  # 1-based, like golds
        out.append(Item(it["id"], [o], [g + 1 for g in gold], multi=True,
                        meta={"partner": partner}))  # fmt: skip
    return out


def _chain() -> list[Item]:
    """chain_intermediates (plan 0038): one list per intermediate slot, the frozen bank-v2
    options in the judge's order (cannot-tell dropped); an item passes when every slot is
    right, the family's all-intermediates rule."""
    from wsbench.evals.chain_intermediates.judge import mc_options

    _h, items = load_bank_file(frozen_bank_path("chain_intermediates"))
    out = []
    for it in items:
        lists = mc_options(it)
        golds = [lst.index(int(g)) + 1 for lst, g in zip(lists, it["intermediates"], strict=True)]
        out.append(Item(it["id"], [[str(o) for o in lst] for lst in lists], golds))
    return out


def _knowledge_cutoff() -> list[Item]:
    """The judge's own menu (plan 0044): the item's K = 5 options in the bank's seeded order,
    the ``mc.KC_NONE`` line dropped; the bank via ``registry.frozen_bank_path`` (v2), then the
    ids-only nocot items (their options need no question text)."""
    from wsbench import nocot

    raw = json.loads(frozen_bank_path("knowledge_cutoff").read_text(encoding="utf-8"))
    items = [*raw["items"], *nocot.load_obscure()[1]]
    return [
        Item(it["id"], [[str(o) for o in it["options"]]], [it["options"].index(it["gold"]) + 1])
        for it in items
    ]


def _wrong_bridge() -> list[Item]:
    """The frozen bank-v2 ``mc`` blocks (plan 0050): six candidates, gold = the model's wrong
    bridge B'; the cannot-tell line is the judge's, not an option."""
    _h, items = load_bank_file(frozen_bank_path("wrong_bridge"))
    out = []
    for it in items:
        order = list(it["mc"]["order"])
        out.append(
            Item(
                it["id"],
                [order],
                [order.index(it["mc"]["gold"]) + 1],
                meta={"contrast": order.index(it["mc"]["contrast"]) + 1},
            )
        )
    return out


def _introspection() -> list[Item]:
    """The 125 headline items (protocol, beta 4): the judge's 7-option list minus cannot-tell
    (the five cluster concepts and "no injected concept", the bank's seeded order). Round 4: the
    headline is the regex (rxhead-v1); this floors the diagnostic judge column."""
    from wsbench.evals.introspection.judge import is_headline
    from wsbench.evals.introspection.judge import load as load_ii
    from wsbench.mc import is_cannot

    out = []
    for it in load_ii()["items"]:
        if not is_headline(it):
            continue
        labels = [o["label"] for o in it["options"] if not is_cannot(o["label"])]
        out.append(Item(it["id"], [labels], [labels.index(it["gold"]) + 1]))
    return out


BUILDERS: dict[str, Callable[[], list[Item]]] = {
    "chain_intermediates": _chain,
    "introspection": _introspection,
    "association": _association,
    "conjunctive_association": _conjunctive,
    "role_bound_association": _role_bound,
    "relational_multihop": _relational,
    "moral_rationale": _moral,
    "user_modeling": _user_modeling,
    "directed_modulation": _directed_modulation,
    "poetry": _poetry,
    "multihop_mt_v2": _multitoken("multihop_mt_v2"),
    "multilingual": _multitoken("multilingual"),  # plan 0054: the mc+regex MC roles
    "multilingual_mt": _multitoken("multilingual_mt"),
    "typo_mt": _multitoken("typo_mt"),
    "basic_readout_mt": _multitoken("basic_readout_mt"),
    "multilingual_multihop": _multitoken("multilingual_multihop"),
    "multilingual_typo": _multitoken("multilingual_typo"),
    "multi_concept_directed_modulation": _multi_concept,
    "knowledge_cutoff": _knowledge_cutoff,
    "basic_readout": _basic_readout,
    "multihop": _multihop,
    "wrong_bridge": _wrong_bridge,
}


def build_family(name: str) -> list[Item]:
    if name not in BUILDERS:
        raise KeyError(f"no option lists for {name!r}; known: {sorted(BUILDERS)}")
    return BUILDERS[name]()


# ---------------------------------------------------------------- prompts


def topic_of(item: Item) -> str:
    return str(item.meta.get("topic") or "")


def has_topics(items: list[Item]) -> bool:
    """The topic variant needs every item's topic (a family whose builder records none, or a
    bank missing one, has no topic guesser)."""
    return bool(items) and all(topic_of(it) for it in items)


def topic_form(family: str) -> str | None:
    """``"lists"`` (per-list labels, an ``items`` map), ``"item"`` (one line per item, a
    ``topics`` map) or None (no topic file)."""
    path = TOPICS_DIR / f"{family}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "items" in raw:
        return "lists"
    if "topics" in raw:
        return "item"
    raise ValueError(f"{family}: topic file {path} has neither an items nor a topics map")


def load_list_topics(family: str) -> dict[str, list[str]]:
    """``{item id: [topic of each list]}`` from ``TOPICS_DIR/<family>.json`` (``items``)."""
    path = TOPICS_DIR / f"{family}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{family}: no topic labels at {path} (scripts/build_r4_mc_banks.py)"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): [str(t) for t in v] for k, v in raw["items"].items()}


def with_topics(items: list[Item], family: str) -> list[Item]:
    """The items with ``meta["topics"]`` set (one label per list); an item without labels, or
    with a label count that differs from its list count, is an error."""
    topics = load_list_topics(family)
    out = []
    for it in items:
        t = topics.get(it.id)
        if t is None or len(t) != len(it.lists):
            raise ValueError(f"{family}/{it.id}: topic labels {t!r} do not match its lists")
        out.append(Item(it.id, it.lists, it.golds, it.multi, {**it.meta, "topics": t}))
    return out


def topic_source(family: str) -> str | None:
    """Where a family's ``topic`` guesser gets its topics: ``"lists"`` / ``"item"`` (a frozen
    topic file under ``TOPICS_DIR``, ``topic_form``) or ``"meta"`` (no file, but the family's
    builder records every item's topic in ``meta["topic"]``: ``TOPIC_FAMILIES``, PR #214), else
    None (no topic guesser). A file wins; no family has both today (held by a test)."""
    form = topic_form(family)
    if form is not None:
        return form
    return "meta" if family in TOPIC_FAMILIES else None


def render_lists(
    item: Item,
    mark_gold: bool = False,
    side_labels: bool = False,
    topics: bool = False,
    topic: bool = False,
) -> str:
    """``side_labels`` (question variant): a list asked for one side of a deliberative item
    is headed with that side, as the judge's question names it. ``topics`` (topic variant, a
    "lists" topic file): each list is headed with its topic label (``meta["topics"]``).
    ``topic`` (topic variant, "meta" source): the item's own topic line first."""
    parts = [f"Topic: {topic_of(item)}"] if topic else []
    sides = item.meta.get("sides") or []
    tops = item.meta.get("topics") or [] if topics else []
    for k, lst in enumerate(item.lists, start=1):
        golds = set(item.golds) if item.multi else {item.golds[k - 1]}
        side = sides[k - 1] if side_labels and len(sides) == len(item.lists) else None
        head = f"List {k}" + (f" ({_SIDE_LABEL[side]})" if side in _SIDE_LABEL else "")
        if tops:
            head += f" (topic: {tops[k - 1]})"
        lines = [head] if not item.multi else ["Candidates"]
        for i, text in enumerate(lst, start=1):
            tag = " (correct)" if mark_gold and i in golds else ""
            lines.append(f"  {i}. {text}{tag}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _rng(seed: int, *key: object) -> random.Random:
    h = hashlib.sha256(":".join(str(k) for k in (seed, *key)).encode()).digest()[:8]
    return random.Random(int.from_bytes(h, "big"))


def pick_examples(items: list[Item], idx: int, family: str, seed: int, k: int = 3) -> list[Item]:
    """A seeded choice of ``k`` OTHER items shown as worked examples, never the item itself."""
    others = [i for i in range(len(items)) if i != idx]
    if len(others) < k:
        raise ValueError(f"{family}: need {k} other items for examples, have {len(others)}")
    chosen = _rng(seed, family, items[idx].id, "examples").sample(others, k)
    return [items[i] for i in chosen]


def load_topics(family: str) -> dict[str, str]:
    """``{item id: topic line}`` of a family's frozen topic file (``topic`` variant)."""
    path = TOPICS_DIR / f"{family}.json"
    if not path.exists():
        raise ValueError(f"{family}: no topic file {path} (scripts/baselines/make_topics.py)")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "topics" not in raw:
        raise ValueError(f"{family}: {path} has no topics map (per-list labels: load_list_topics)")
    return dict(raw["topics"])


def topics_version(family: str) -> str | None:
    path = TOPICS_DIR / f"{family}.json"
    return json.loads(path.read_text(encoding="utf-8")).get("version") if path.exists() else None


def user_message(item: Item, variant: str, family: str, examples: list[Item] | None) -> str:
    if variant == "blind":
        return render_lists(item)
    form = topic_source(family) if variant == "topic" else None
    if variant == "topic" and form is None:
        raise ValueError(
            f"{family}: no topic file under {TOPICS_DIR} and no builder topics (TOPIC_FAMILIES)"
        )
    if form == "item":
        topic = load_topics(family)[item.id]
        return (
            f"This benchmark family tests {DESCRIPTIONS[family]}. You are told the topic of the "
            f"unseen scene, as a reader who skimmed it would put it (it does not give the "
            f"answer): {topic}\n\n{render_lists(item)}"
        )
    if variant in MARK_VARIANTS:
        return user_message(item, variant.removesuffix("_marks"), family, examples)
    if variant == "question":
        if family not in GUESS_QUESTION:
            raise ValueError(f"{family}: no question hook (GUESS_QUESTION)")
        q = GUESS_QUESTION[family](item)
        return f"QUESTION:\n{q}\n\n{render_lists(item, side_labels=True)}"
    if variant == "topic":
        assert examples is not None and item.id not in {e.id for e in examples}
        if form == "meta":
            if not topic_of(item):
                raise ValueError(f"{family}: item {item.id} has no topic")
            head = (
                f"This benchmark family tests {DESCRIPTIONS[family]}. Each item comes with its "
                "topic (the kind of answer its unseen question asks for). Here are three other "
                "items from the same family with their correct option marked."
            )
            shown = [
                f"Example {j}\n{render_lists(e, mark_gold=True, topic=True)}"
                for j, e in enumerate(examples, 1)
            ]
            return "\n\n".join([head, *shown, f"Now this item:\n{render_lists(item, topic=True)}"])
        assert form == "lists"
        head = (
            f"This benchmark family tests {DESCRIPTIONS[family]}. You are told the topic of each "
            "list (what its hidden question is about), but not the question itself. Here are "
            "three other items from the same family with their correct option marked."
        )
        shown = [
            f"Example {j}\n{render_lists(e, mark_gold=True, topics=True)}"
            for j, e in enumerate(examples, 1)
        ]
        return "\n\n".join([head, *shown, f"Now this item:\n{render_lists(item, topics=True)}"])
    if variant != "described":
        raise ValueError(f"unknown variant {variant!r}")
    assert examples is not None and item.id not in {e.id for e in examples}
    head = (
        f"This benchmark family tests {DESCRIPTIONS[family]}. Here are three other items from "
        "the same family with their correct option marked."
    )
    shown = [f"Example {j}\n{render_lists(e, mark_gold=True)}" for j, e in enumerate(examples, 1)]
    return "\n\n".join([head, *shown, f"Now this item:\n{render_lists(item)}"])


def schema(
    n_lists: int, multi: bool = False, marks: bool = False, cands: bool = False
) -> dict[str, Any]:
    if cands:
        props = {
            "choice1": {"type": "integer"},
            "candidates": {"type": "array", "items": {"type": "integer"}},
        }
        return schema_block("lucky_cands", props, list(props))
    if marks:
        props = {
            f"marks{i + 1}": {"type": "array", "items": {"type": "integer"}} for i in range(n_lists)
        }
        return schema_block("lucky_marks", props, list(props))
    if multi:
        return schema_block(
            "lucky_guess", {"picks": {"type": "array", "items": {"type": "integer"}}}, ["picks"]
        )
    props = {f"choice{i + 1}": {"type": "integer"} for i in range(n_lists)}
    return schema_block("lucky_guess", props, list(props))


# ---------------------------------------------------------------- scoring


def _valid(p: Any, n: int) -> bool:
    return isinstance(p, int) and not isinstance(p, bool) and 1 <= p <= n


def score_draw(reply: dict[str, Any] | None, item: Item) -> dict[str, Any] | None:
    """One draw: raw picks, whether it passes, invalid picks. ``None`` = the call failed (out of
    every denominator). Single-choice items pass when every list is right; ``multi`` items
    (multi_concept_directed_modulation) pass when the picks include EVERY gold (``all_hit``, the
    family's all-concepts rule since plan 0025) and record ``any_hit`` (some pick of at most three
    is gold) and ``exact`` (picks == golds)."""
    if reply is None:
        return None
    if item.multi:
        picks = reply.get("picks")
        picks = picks if isinstance(picks, list) else []
        n = item.n_options[0]
        good = list(dict.fromkeys(p for p in picks if _valid(p, n)))[:MAX_PICKS]
        golds = set(item.golds)
        return {
            "picks": picks,
            # plan 0025: every dictated concept picked, and not the binding partner too
            "correct": golds <= set(good) and not set(good) & set(item.meta.get("partner", ())),
            "all_hit": golds <= set(good),
            "any_hit": any(p in golds for p in good),
            "n_golds": len(golds),
            "exact": set(good) == golds,
            "n_picks": len(good),
            "n_invalid": sum(not _valid(p, n) for p in picks),
        }
    picks = [reply.get(f"choice{i + 1}") for i in range(len(item.lists))]
    valid = [_valid(p, n) for p, n in zip(picks, item.n_options, strict=True)]
    correct = all(v and p == g for v, p, g in zip(valid, picks, item.golds, strict=True))
    return {"picks": picks, "correct": correct, "n_invalid": sum(not v for v in valid)}


def score_marks_draw(reply: dict[str, Any] | None, item: Item) -> dict[str, Any] | None:
    """A multi-mark draw (final r1): the valid marks of each list; ``correct`` = the single-draw
    analogue of the judge's rule (every list singles out its gold: the gold is its only mark)."""
    if reply is None:
        return None
    marks: list[list[int]] = []
    n_invalid = 0
    for li, n in enumerate(item.n_options):
        raw = reply.get(f"marks{li + 1}")
        raw = raw if isinstance(raw, list) else []
        marks.append(list(dict.fromkeys(p for p in raw if _valid(p, n))))
        n_invalid += sum(not _valid(p, n) for p in raw)
    correct = all(m == [g] for g, m in zip(item.golds, marks, strict=True))
    return {
        "marks": marks,
        "correct": correct,
        "n_picks": sum(len(m) for m in marks),
        "n_invalid": n_invalid,
    }


def marks_verdict(draws: list[dict[str, Any] | None], item: Item) -> bool | None:
    """The judge's ec-v5c rule (``moral_rationale.judge.ml_verdict``, through the shared
    ``judge.ec_pass``) on a guesser's draws (final r1, reviews of #203). Each mark of a draw is
    its OWN statement, the way the judge reads a readout naming each option on a separate line,
    so rule (f) unmarks nothing. Per list: an option is MARKED when more than half of the draws
    mark it, and its support is the number of draws marking it. The list passes when its gold is
    marked, not every option is marked, and no marked opposite-side option has support >=
    ``OPP_WIN_RATIO`` times the gold's. Every list must pass. ``None`` when every draw failed."""
    from wsbench.evals.moral_rationale.judge import ec_pass

    live = [d for d in draws if d is not None]
    if not live:
        return None
    kinds = item.meta.get("kinds") or [{} for _ in item.lists]
    for li, (gold, n) in enumerate(zip(item.golds, item.n_options, strict=True)):
        count = Counter(p for d in live for p in d["marks"][li])
        sup = {p: c for p, c in count.items() if 2 * c > len(draws)}
        if not ec_pass(sup, gold, {int(k): v for k, v in kinds[li].items()}, n):
            return False
    return True


def marks_null(draws: list[dict[str, Any] | None], item: Item) -> float | None:
    """The uniform chance of :func:`marks_verdict` for THIS guesser (round 4): the pass
    probability when the guesser's marks carry no information about which option is which, i.e.
    the mean of the judge's rule over every relabelling of each list's options (the guesser's
    support counts kept, assigned to the options by a uniformly random permutation; the gold and
    each option's side stay where they are). A guesser that marks more options passes more often
    by chance under the multi-label rule, so its chance line moves with it; a guesser whose marks
    single out the gold scores above this line, one whose marks ignore the gold sits on it.
    Lists are independent, so an item's chance is the product over its lists. ``None`` when every
    draw failed."""
    from wsbench.evals.moral_rationale.judge import ec_pass

    live = [d for d in draws if d is not None]
    if not live:
        return None
    kinds = item.meta.get("kinds") or [{} for _ in item.lists]
    out = 1.0
    for li, (gold, n) in enumerate(zip(item.golds, item.n_options, strict=True)):
        count = Counter(p for d in live for p in d["marks"][li])
        sup = {p: c for p, c in count.items() if 2 * c > len(draws)}
        kind = {int(k): v for k, v in kinds[li].items()}
        perms = list(itertools.permutations(range(1, n + 1)))
        hits = sum(
            ec_pass({perm[p - 1]: c for p, c in sup.items()}, gold, kind, n) for perm in perms
        )
        out *= hits / len(perms)
    return out


SIDE_COIN = 0.5  # a reader naming the side by a coin passes a two-sided list half the time
# the side readers' pass rates in a frozen entry; ``side_prior`` is guesser-independent
SIDE_KEYS = ("side_follow", "side_contra", "side_prior")
_YES_NO = ("yes", "no")


def _list_side(r: dict[str, Any], li: int) -> str | None:
    """The side a list's non-``opp`` options argue: a deliberative list's own side label, else
    the item's committed answer (``direction``, the bank's ``commit_direction``)."""
    sides = r.get("sides") or []
    side = sides[li] if li < len(sides) else None
    return side if side in _YES_NO else r.get("direction")


def prior_side(per_item: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """The prior-side reader of a two-sided family (round 4 review of #215, finding 1): with no
    readout and no guesser, ALWAYS mark the options arguing one fixed side ('no' / 'False', or
    'yes'), i.e. a list's own side (gold + same-side options) when that is the list's side and
    its ``opp`` options otherwise, scored with ``judge.ec_pass`` (an item passes when every list
    does). It reads the bank's base rate: bank v5 commits 'no' on 22 of 24 items, so always-no
    passes 0.917. Scored over every item whose lists all have a known side and kinds (one-sided
    deliberative lists fail it: marking every option fails ``ec_pass``); the better of the two
    fixed sides is ``side_prior`` (its side in ``side_prior_dir``); ``None`` when no item
    scores."""
    from wsbench.evals.moral_rationale.judge import ec_pass

    rows: list[dict[str, float]] = []
    for r in per_item.values():
        kinds = r.get("kinds") or []
        n_lists = len(r["gold"])
        if len(kinds) != n_lists or any(_list_side(r, li) is None for li in range(n_lists)):
            continue
        row = {}
        for prior in _YES_NO:
            ok = 1.0
            for li, (gold, n) in enumerate(zip(r["gold"], r["n_options"], strict=True)):
                kind = {int(p): v for p, v in kinds[li].items()}
                opp = {p for p in range(1, n + 1) if kind.get(p) == "opp"}
                marks = set(range(1, n + 1)) - opp if _list_side(r, li) == prior else opp
                ok *= float(bool(marks) and ec_pass(dict.fromkeys(marks, 1), gold, kind, n))
            row[prior] = ok
        rows.append(row)
    if not rows:
        return None
    rate = {p: statistics.fmean(row[p] for row in rows) for p in _YES_NO}
    best = max(_YES_NO, key=lambda p: (rate[p], p == "no"))
    return {"side_prior": rate[best], "side_prior_dir": best, "n_prior_items": len(rows)}


def side_readers(
    per_item: dict[str, dict[str, Any]], directions: dict[str, str] | None = None
) -> dict[str, Any] | None:
    """The side-aware readers of a two-sided family under the judge's rule (round 4 review of
    #215). A reader that can tell which side of the dilemma each option argues (easy given the
    question) marks every option of ONE side: the gold's side (the gold and the same-side
    options) passes ``judge.ec_pass`` (gold marked, not every option, no opposite option marked),
    the opposite side fails, so its pass rate is how often it names the model's side and a coin
    passes ``SIDE_COIN`` of the lists. Two readers are built from a guesser's own draws:
    ``follow`` marks the side the guesser leans to (more picks or marks per option of that side,
    over its draws), ``contra`` the other side; a tie is a coin. Both at ``SIDE_COIN``: the
    guesser's lean says nothing about the model's side. Either above it: the lists or the item
    selection give the side away (bank v5: the guessers moved onto the opposite side of the gold,
    so ``contra`` reads the side). Scored over the items whose every list holds both sides (an
    item passes when all its lists do). Records carrying a committed side (``direction``, or
    ``directions[item id]`` from the bank) also get the guesser-free :func:`prior_side` reader
    (``side_prior``). ``None`` when no item scores."""
    from wsbench.evals.moral_rationale.judge import ec_pass

    if directions:
        per_item = {
            i: {**r, "direction": r.get("direction") or directions.get(i)}
            for i, r in per_item.items()
        }
    prior = prior_side(per_item) or {}

    follow: list[float] = []
    contra: list[float] = []
    coin: list[float] = []
    for r in per_item.values():
        kinds = r.get("kinds") or []
        live = [d for d in r.get("draws") or [] if d is not None]
        if not live or len(kinds) != len(r["gold"]):
            continue
        f = c = k = 1.0
        two_sided = True
        for li, (gold, n) in enumerate(zip(r["gold"], r["n_options"], strict=True)):
            kind = {int(p): v for p, v in kinds[li].items()}
            opp = {p for p in range(1, n + 1) if kind.get(p) == "opp"}
            own = set(range(1, n + 1)) - opp
            if not opp or gold in opp:
                two_sided = False
                break
            seen = [p for d in live for p in (d["marks"][li] if "marks" in d else [d["picks"][li]])]
            lean = sum(p in opp for p in seen) / len(opp) - sum(p in own for p in seen) / len(own)
            p_own = float(ec_pass(dict.fromkeys(own, 1), gold, kind, n))
            p_opp = float(ec_pass(dict.fromkeys(opp, 1), gold, kind, n))
            half = (p_own + p_opp) / 2
            f *= half if lean == 0 else p_opp if lean > 0 else p_own
            c *= half if lean == 0 else p_own if lean > 0 else p_opp
            k *= half
        if two_sided:
            follow.append(f)
            contra.append(c)
            coin.append(k)
    if not follow:
        return prior or None
    return {
        "side_follow": statistics.fmean(follow),
        "side_contra": statistics.fmean(contra),
        "side_coin": statistics.fmean(coin),
        "n_side_items": len(follow),
        **prior,
    }


def side_at_chance(entry: dict[str, Any], margin: float = 0.02) -> bool:
    """No side reader of a floor entry (follow, contra, and the prior-side reader where it was
    scored) is more than ``margin`` above the coin."""
    top = max(entry[k] for k in SIDE_KEYS if entry.get(k) is not None)
    return bool(top <= entry.get("side_coin", SIDE_COIN) + margin)


def bank_directions(bank: str | Path | None) -> dict[str, str]:
    """``id -> commit_direction`` of a run record's bank file (``None`` / a missing file: the
    same-named file under ``evals/moral_rationale/``, else ``{}``), for :func:`prior_side` on
    run records written before ``direction`` was carried per item."""
    if not bank:
        return {}
    path = Path(bank)
    if not path.exists():
        path = REPO_ROOT / "evals" / "moral_rationale" / path.name
    if not path.exists():
        return {}
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):  # a header-format bank (not moral_rationale): no sides
        return {}
    return {it["id"]: it["commit_direction"] for it in items if it.get("commit_direction")}


def majority_correct(draws: list[dict[str, Any] | None], item: Item) -> bool | None:
    """Per-list plurality over the valid picks of the live draws; a unique winner per list, every
    winner gold. ``multi``: majority of live draws passing. ``None`` when every draw failed."""
    live = [d for d in draws if d is not None]
    if not live:
        return None
    if item.multi:
        return sum(d["correct"] for d in live) * 2 > len(live)
    for li, (gold, n) in enumerate(zip(item.golds, item.n_options, strict=True)):
        votes = Counter(d["picks"][li] for d in live if _valid(d["picks"][li], n))
        if not votes:
            return False
        ranked = votes.most_common(2)
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            return False
        if ranked[0][0] != gold:
            return False
    return True


def conjunctive_rule(draws: list[dict[str, Any] | None], item: Item) -> bool | None:
    """conjunctive_association's own item rule (comp-v3 +maj-noinv) on the first 3 draws: a
    majority picks the gold and no draw picks the gold's role-swapped twin."""
    live = [d for d in draws[:3] if d is not None]
    if not live:
        return None
    picks = [d["picks"][0] for d in live]
    inv = item.meta.get("inverted")
    return 2 * picks.count(item.golds[0]) > 3 and (inv is None or inv not in picks)


def score_cands_draw(reply: dict[str, Any] | None, item: Item) -> dict[str, Any] | None:
    """A candidate-list draw (``*_cands``): the valid distinct options of the one pick and then
    at most ``N_CANDS`` candidates; ``outcome`` is the judge's fold (``fold_candidates``): the
    twin among them vetoes the draw (``inverted``), else the gold passes it (``gold``), else
    ``other``. ``correct`` is the one-pick answer alone (the per-draw mean)."""
    if reply is None:
        return None
    n = item.n_options[0]
    first = reply.get("choice1")
    raw = reply.get("candidates")
    raw = raw if isinstance(raw, list) else []
    asked = [first, *raw]
    cands = list(dict.fromkeys(p for p in asked if _valid(p, n)))[: N_CANDS + 1]
    inv = item.meta.get("inverted")
    outcome = (
        "inverted" if inv is not None and inv in cands else "gold" if item.golds[0] in cands else
        "other"
    )  # fmt: skip
    return {
        "picks": [first],
        "cands": cands,
        "outcome": outcome,
        "correct": _valid(first, n) and first == item.golds[0],
        "n_picks": len(cands),
        "n_invalid": sum(not _valid(p, n) for p in asked),
    }


def headline_rule(draws: list[dict[str, Any] | None], item: Item, shards: int) -> bool | None:
    """conjunctive_association's sharded rule on a ``*_cands`` guesser's draws: shard ``j`` is
    draws ``3j .. 3j+2``, folded by the judge's own ``_resolve`` (a gold majority, vetoed by any
    inverted draw) and the shards by ``shards_pick`` (any inverted shard vetoes, any gold shard
    passes). ``None`` when a needed draw failed."""
    from wsbench.evals.conjunctive_association.judge import _resolve, shards_pick

    need = draws[: shards * SHARD_DRAWS]
    if len(need) < shards * SHARD_DRAWS or any(d is None for d in need):
        return None
    name = {"gold": "gold", "inverted": "inverted", "other": "distractor"}
    picks = [
        _resolve([name[d["outcome"]] for d in need[j : j + SHARD_DRAWS]])  # type: ignore[index]
        for j in range(0, len(need), SHARD_DRAWS)
    ]
    return shards_pick(picks) == "gold"


def rule_chance(n: int, twin: bool, k: int = 1, shards: int = 1) -> float:
    """Exact uniform pass rate of one conjunctive item under its rule: each draw lists ``k``
    distinct uniform options of ``n`` (the guesser's lists: no cannot tell); a draw is gold when
    the gold is listed and its twin (``twin``) is not, inverted when the twin is listed; a shard
    of 3 draws is gold on a gold majority with no inverted draw and inverted on an inverted
    majority or a gold majority with one inverted draw; the item passes when no shard is
    inverted and some shard is gold. ``k=1, shards=1`` is the single-layer rule (comp-v3
    +maj-noinv): a^3 + 3a^2(1 - a - b)."""
    k = min(k, n)
    b = k / n if twin else 0.0
    a = k / n - (k * (k - 1) / (n * (n - 1)) if twin and n > 1 else 0.0)
    o = 1.0 - a - b
    p_gold = a**3 + 3 * a**2 * o
    p_inv = b**3 + 3 * b**2 * (1 - b) + 3 * a**2 * b
    return (1 - p_inv) ** shards - (1 - p_inv - p_gold) ** shards


def family_chance(name: str, items: list[Item]) -> float:
    """Uniform chance under the family's OWN item rule (``FAMILY_RULES``; review of #202 round
    4): the standard reads a guesser's ``family_rule`` against this, never against the per-draw
    ``analytic_floor``. A family without a multi-draw rule: the analytic floor."""
    if name == "conjunctive_association":
        return statistics.fmean(
            rule_chance(it.n_options[0], it.meta.get("inverted") is not None) for it in items
        )
    if name in PAIR_RULE_FAMILIES:  # both directions of a pair right: the product of floors
        pairs = direction_pairs(items)
        return statistics.fmean(
            analytic_floor([a]) * analytic_floor([b]) for a, b in pairs.values()
        )
    return analytic_floor(items)


# review of #202 round 5: role_bound_association's headline unit is the direction pair
# (role_bound_association.score ``pair-v1``): a pair passes when its ab AND its ba item pass.
# Both items show the same option lists, so a guesser that recovers the stereotyped pair and act
# but not the direction passes one of the two at most.
PAIR_RULE_FAMILIES = frozenset({"role_bound_association"})


def direction_pairs(items: list[Item]) -> dict[str, tuple[Item, Item]]:
    """``pair_id`` -> ``(ab item, ba item)`` over the complete pairs among ``items`` (an item
    whose twin is missing, e.g. in a ``limit`` run, is left out)."""
    by: dict[str, dict[str, Item]] = {}
    for it in items:
        if it.meta.get("pair_id") and it.meta.get("direction") in ("ab", "ba"):
            by.setdefault(it.meta["pair_id"], {})[it.meta["direction"]] = it
    return {pid: (d["ab"], d["ba"]) for pid, d in by.items() if len(d) == 2}


def pair_rule(per_item: dict[str, dict[str, Any]], items: list[Item]) -> float | None:
    """The guesser's pass rate under the direction-pair rule: per complete pair, the chance
    that one draw of each item is right, ``p_ab * p_ba`` (``p`` = the item's share of right
    live draws; every ab draw paired with every ba draw, the draws are independent calls),
    averaged over the pairs with live draws on both sides."""

    def share(it: Item) -> float | None:
        r = per_item.get(it.id)
        live = [d for d in (r or {}).get("draws", []) if d is not None]
        return (sum(bool(d["correct"]) for d in live) / len(live)) if live else None

    vals = []
    for a, b in direction_pairs(items).values():
        pa, pb = share(a), share(b)
        if pa is not None and pb is not None:
            vals.append(pa * pb)
    return statistics.fmean(vals) if vals else None


def headline_chance(items: list[Item], shards: int) -> float:
    """Uniform chance of the sharded +cand3 rule (``headline_rule``) on these items."""
    return statistics.fmean(
        rule_chance(it.n_options[0], it.meta.get("inverted") is not None, N_CANDS + 1, shards)
        for it in items
    )


def standard(family: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """The MC leakage standard on one family's frozen entries (review of #202 round 4): every
    measured guesser against uniform chance, BOTH under the family's own pass rule: the
    ``family_rule`` rate against ``family_chance`` where the family has a multi-draw rule, each
    headline config's ``rule_<config>`` against ``chance_<config>`` for a ``*_cands`` guesser,
    else the per-draw ``mean`` against the per-draw ``analytic_floor``. A row passes when the
    guesser is within ``STANDARD_POINTS`` (moral_rationale: 2) of chance. A ``NOT_A_FLOOR``
    guesser of the family (directed_modulation's ``topic``) has no row."""
    pts = STANDARD_POINTS_BY_FAMILY.get(family, STANDARD_POINTS)
    rows = []
    for v, e in sorted(entry.items()):
        if not isinstance(e, dict) or v.startswith("uniform") or not is_floor(family, v):
            continue
        if v in CANDS_VARIANTS:
            pairs = [
                (f"rule_{c}", e.get(f"rule_{c}"), e.get(f"chance_{c}")) for c in HEADLINE_SHARDS
            ]
        elif family in FAMILY_RULES or family in PAIR_RULE_FAMILIES:
            pairs = [("family_rule", e.get("family_rule"), e.get("family_chance"))]
        else:
            pairs = [("mean", e.get("mean"), e.get("analytic_floor"))]
        for rule, value, chance in pairs:
            if value is None or chance is None:
                raise ValueError(f"{family}/{v}: no {rule} or its chance; re-measure the floor")
            rows.append(
                {
                    "variant": v,
                    "rule": rule,
                    "value": float(value),
                    "chance": float(chance),
                    "line": float(chance) + pts,
                    "pass": float(value) <= float(chance) + pts + 1e-9,
                }
            )
    return rows


# a family's own item rule over the draws, recorded beside the per-draw mean (``family_rule``)
FAMILY_RULES: dict[str, Callable[[list[dict[str, Any] | None], Item], bool | None]] = {
    "conjunctive_association": conjunctive_rule,
}


def aggregate(per_item: dict[str, dict[str, Any]], n_draws: int) -> dict[str, Any]:
    """``mean`` = mean over draws of that draw's pass rate, ``std`` across draws, ``majority`` =
    items whose plurality picks pass, ``invalid_rate`` = invalid picks / picks asked."""
    per_draw: list[float] = []
    for d in range(n_draws):
        live = [r["draws"][d] for r in per_item.values() if r["draws"][d] is not None]
        if live:
            per_draw.append(sum(x["correct"] for x in live) / len(live))
    scored = [r for r in per_item.values() if any(x is not None for x in r["draws"])]
    n_live = sum(x is not None for r in per_item.values() for x in r["draws"])
    live_draws = [(r, x) for r in per_item.values() for x in r["draws"] if x is not None]
    n_picks = sum(
        (x["n_picks"] + x["n_invalid"]) if "n_picks" in x else len(r["gold"]) for r, x in live_draws
    )
    n_invalid = sum(x["n_invalid"] for _r, x in live_draws)
    exact = [x["exact"] for _r, x in live_draws if "exact" in x]
    by_k: dict[int, list[bool]] = {}
    for _r, x in live_draws:
        if "n_golds" in x:
            by_k.setdefault(x["n_golds"], []).append(bool(x["correct"]))
    any_hit = [x["any_hit"] for _r, x in live_draws if "any_hit" in x]
    picks = [x["n_picks"] for _r, x in live_draws if "n_picks" in x]
    return {
        "mean": statistics.fmean(per_draw) if per_draw else None,
        "std": statistics.stdev(per_draw) if len(per_draw) > 1 else (0.0 if per_draw else None),
        "majority": (
            sum(bool(r["majority_correct"]) for r in scored) / len(scored) if scored else None
        ),
        "exact": (sum(exact) / len(exact)) if exact else None,
        "any_hit": (sum(any_hit) / len(any_hit)) if any_hit else None,
        "mean_picks": (sum(picks) / len(picks)) if picks else None,
        "by_n_concepts": {str(k): sum(v) / len(v) for k, v in sorted(by_k.items())} or None,
        "per_draw": per_draw,
        "n_items": len(scored),
        "n_draws": n_draws,
        "n_api_fail": n_draws * len(per_item) - n_live,
        "invalid_rate": (n_invalid / n_picks) if n_picks else None,
        "n_invalid": n_invalid,
    }


def analytic_floor(items: list[Item]) -> float:
    """Uniform pass rate on these option sets: mean over items of the product over lists of
    (occurrences of the gold text) / n (a list that repeats the gold label counts it twice);
    for a ``multi`` item, ``MAX_PICKS`` distinct uniform picks include all ``k`` golds and none of
    the ``p`` binding-partner options with probability C(n-k-p, MAX_PICKS-k) / C(n, MAX_PICKS)
    (plan 0025's all-concepts rule with its direction rule)."""

    def one(it: Item) -> float:
        if it.multi:
            n, k = it.n_options[0], len(it.golds)
            p = len(it.meta.get("partner", ()))
            if k > MAX_PICKS:
                return 0.0
            return math.comb(n - k - p, MAX_PICKS - k) / math.comb(n, MAX_PICKS)
        pairs = zip(it.lists, it.golds, strict=True)
        return math.prod(lst.count(lst[g - 1]) / len(lst) for lst, g in pairs)

    return statistics.fmean(one(it) for it in items)


def uniform_reply(
    item: Item, family: str, draw: int, seed: int, cands: bool = False
) -> dict[str, Any]:
    if cands:  # N_CANDS + 1 distinct uniform options: the one pick, then the candidates
        n = item.n_options[0]
        got = _rng(seed, family, item.id, draw, "cands").sample(
            range(1, n + 1), min(n, N_CANDS + 1)
        )
        return {"choice1": got[0], "candidates": got[1:]}
    if item.multi:  # plan 0025: MAX_PICKS distinct picks, so an all-concepts pass is possible
        n = item.n_options[0]
        return {"picks": _rng(seed, family, item.id, draw, 0).sample(range(1, n + 1), MAX_PICKS)}
    return {
        f"choice{li + 1}": _rng(seed, family, item.id, draw, li).randint(1, n)
        for li, n in enumerate(item.n_options)
    }


# ---------------------------------------------------------------- one family, one variant


def run_family(
    name: str,
    variant: str,
    *,
    judge: ResolvedJudge,
    out: Path,
    draws: int = DEFAULT_DRAWS,
    seed: int = DEFAULT_SEED,
    limit: int = 0,
    concurrency: int = 64,
    rpm: float = 240.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    """The whole bank builds the lists (the described variant's examples draw from all of it);
    ``limit`` scores the first N items. Model draws go through ``run_calls`` at temperature
    1.0, one call per (item, draw), cached under ``out/cells.jsonl``."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; known: {VARIANTS}")
    if variant in ("question", "question_marks") and name not in GUESS_QUESTION:
        raise ValueError(f"{name}: the question variant needs a GUESS_QUESTION hook")
    marks = variant in MARK_VARIANTS
    if marks and name not in MARK_FAMILIES:
        raise ValueError(f"{name}: the multi-mark variants are for {sorted(MARK_FAMILIES)}")
    if marks:
        draws = MARK_DRAWS
    cands = variant in CANDS_VARIANTS
    if cands and name not in CANDS_FAMILIES:
        raise ValueError(f"{name}: the candidate-list variants are for {sorted(CANDS_FAMILIES)}")
    if cands:  # every headline config's shards, 3 draws each
        draws = SHARD_DRAWS * max(HEADLINE_SHARDS.values())
    items = build_family(name)
    src = topic_source(name) if variant == "topic" else None
    if variant == "topic" and src is None:
        raise ValueError(
            f"{name}: no topic file under {TOPICS_DIR} and no builder topics (TOPIC_FAMILIES)"
        )
    if src == "meta" and not has_topics(items):
        raise ValueError(f"{name}: the topic variant needs every item's topic (builder meta)")
    list_topics = src == "lists"
    meta_topics = src == "meta"
    if list_topics:
        items = with_topics(items, name)
    scored = list(range(len(items)))[: limit or None]
    uniform = variant in ("uniform", "uniform_cands")
    ask = "blind" if uniform else variant.removesuffix("_marks").removesuffix("_cands")
    prompts = []
    for idx in scored:
        ex = (
            pick_examples(items, idx, name, seed)
            if ask == "described" or list_topics or meta_topics
            else None
        )
        prompts.append(user_message(items[idx], ask, name, ex))

    replies: list[list[dict[str, Any] | None]]
    spend = Spend()
    if uniform:
        replies = [
            [uniform_reply(items[idx], name, d, seed, cands) for d in range(draws)]
            for idx in scored
        ]
    else:
        replies = [[None] * draws for _ in scored]
        pre = Preflighter(dry_run)
        with Cache(out / "cells.jsonl") as cache:
            # one schema per list shape (moral_rationale mixes 1- and 2-list items)
            shapes = sorted({(len(items[idx].lists), items[idx].multi) for idx in scored})
            for n_lists, multi in shapes:
                js = [
                    j
                    for j, idx in enumerate(scored)
                    if (len(items[idx].lists), items[idx].multi) == (n_lists, multi)
                ]
                calls = [
                    Call(
                        key=f"{name}|{variant}|{items[scored[j]].id}|d{d}",
                        system=(
                            SYSTEM_CANDS
                            if cands
                            else SYSTEM_QUESTION_MARKS
                            if variant == "question_marks"
                            else SYSTEM_MARKS
                            if variant in ("described_marks", "blind_marks")
                            else SYSTEM_QUESTION
                            if variant == "question"
                            else SYSTEM_TOPIC
                            if meta_topics
                            else SYSTEM_MULTI
                            if multi
                            else SYSTEM
                        ),
                        user=prompts[j],
                        meta={"item": items[scored[j]].id, "draw": d},
                    )
                    for j in js
                    for d in range(draws)
                ]
                results = run_calls(
                    calls,
                    schema=schema(n_lists, multi, marks, cands),
                    judge=judge,
                    prompt_version=PROMPT_VERSION,
                    cache=cache,
                    spend=spend,
                    concurrency=concurrency,
                    rpm=rpm,
                    dry_run=dry_run,
                    preflight=pre.for_judge(judge),
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                )
                for j in js:
                    replies[j] = [
                        results.get(f"{name}|{variant}|{items[scored[j]].id}|d{d}")
                        for d in range(draws)
                    ]

    per_item: dict[str, dict[str, Any]] = {}
    for j, idx in enumerate(scored):
        it = items[idx]
        if marks:
            rec = [score_marks_draw(replies[j][d], it) for d in range(draws)]
            verdict = marks_verdict(rec, it)
            null = marks_null(rec, it)
        elif cands:
            rec = [score_cands_draw(replies[j][d], it) for d in range(draws)]
            verdict = majority_correct(rec, it)
        else:
            rec = [score_draw(replies[j][d], it) for d in range(draws)]
            verdict = majority_correct(rec, it)
        per_item[it.id] = {
            "n_lists": len(it.lists),
            "multi": it.multi,
            "gold": it.golds,
            "n_options": it.n_options,
            "draws": rec,
            "majority_correct": verdict,
            **({"marks_null": null} if marks else {}),
            "prompt": prompts[j],
            **it.meta,
        }
    agg = aggregate(per_item, draws)
    rule = FAMILY_RULES.get(name)
    by_id = {it.id: it for it in items}
    scored_items = [items[idx] for idx in scored]
    if rule is not None and not marks and not cands:
        vals = [rule(r["draws"], by_id[i]) for i, r in per_item.items()]
        live = [v for v in vals if v is not None]
        agg["family_rule"] = (sum(live) / len(live)) if live else None
        # review of #202 round 4: chance under the SAME rule (a majority of 3 uniform picks)
        agg["family_chance"] = family_chance(name, scored_items)
    if name in PAIR_RULE_FAMILIES and not marks and not cands:  # role_bound pair-v1
        agg["family_rule"] = pair_rule(per_item, scored_items)
        agg["family_chance"] = family_chance(name, scored_items)
    if cands:  # each headline config's rule and its exact uniform chance
        for cfg, k in HEADLINE_SHARDS.items():
            vals = [headline_rule(r["draws"], by_id[i], k) for i, r in per_item.items()]
            live = [v for v in vals if v is not None]
            agg[f"rule_{cfg}"] = (sum(live) / len(live)) if live else None
            agg[f"chance_{cfg}"] = headline_chance(scored_items, k)
            agg[f"n_scored_{cfg}"] = len(live)
    if marks:  # the floor of record is the judge's own rule over the draws (marks_verdict)
        agg = {**agg, "per_draw_mean": agg["mean"], "mean": agg["majority"], "std": 0.0}
        nulls = [r["marks_null"] for r in per_item.values() if r.get("marks_null") is not None]
        agg["marks_null"] = statistics.fmean(nulls) if nulls else None
    return {
        "family": name,
        "variant": variant,
        "rule": "marks: ec-v5c over the draws, one statement per mark (marks_verdict)"
        if marks
        else f"one pick + up to {N_CANDS} candidates per draw, {SHARD_DRAWS} draws per shard, "
        f"shards {HEADLINE_SHARDS} (headline_rule)"
        if cands
        else "single pick",
        "model": "seeded-uniform" if uniform else judge.model,
        "prompt_version": PROMPT_VERSION,
        "instrument": instrument_versions().get(name),  # the judge these lists belong to
        **({"topics": tv} if ask == "topic" and (tv := topics_version(name)) else {}),
        "temperature": None if uniform else TEMPERATURE,
        "seed": seed,
        "limit": limit,
        "n_lists": sorted({len(it.lists) for it in items}),
        "n_options": sorted({n for it in items for n in it.n_options}),
        "family_description": DESCRIPTIONS[name],
        "bank": str(_bank_file(name)),
        "analytic_floor": analytic_floor([items[idx] for idx in scored]),
        "aggregate": agg,
        "spend_usd": spend.usd,
        "written": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "per_item": per_item,
    }


def _bank_file(name: str) -> Path:
    from wsbench.registry import bank_path

    return bank_path(name)


def report_line(r: dict[str, Any]) -> str:
    a = r["aggregate"]
    if a["mean"] is None:
        return f"{r['family']}/{r['variant']}: no scored draws"
    exact = (
        f" all-hit; any={a['any_hit']:.3f} exact={a['exact']:.3f} picks={a['mean_picks']:.2f}"
        if a.get("exact") is not None
        else ""
    )
    if a.get("marks_null") is not None:
        exact += f" marks_null={a['marks_null']:.3f}"
    return (
        f"{r['family']}/{r['variant']}: pass={a['mean']:.3f} ±{a['std']:.3f} "
        f"majority={a['majority']:.3f}{exact} floor={r['analytic_floor']:.3f} "
        f"n={a['n_items']} invalid={a['invalid_rate']:.3f} api_fail={a['n_api_fail']} "
        f"spend=${r['spend_usd']:.2f}"
    )


# ---------------------------------------------------------------- freeze


def instrument_versions() -> dict[str, str]:
    """Each family's judge ``prompt_version``: the instrument a frozen floor belongs to."""
    from wsbench import registry

    registry.load_all()
    out = {
        name: registry.FAMILIES[name].judge.prompt_version
        for name in BUILDERS
        if name in registry.FAMILIES
    }
    if "conjunctive_association" in out:  # round 5: an opt-in bank v5 is its own instrument
        from wsbench.evals.conjunctive_association.judge import bank_stamp
        from wsbench.mcjudge import load_bank

        out["conjunctive_association"] += bank_stamp(load_bank("conjunctive_association"))
    out.update({k: v for k, v in mc_diagnostic_instruments().items() if k in out})
    return out


def mc_diagnostic_instruments() -> dict[str, str]:
    """Families whose HEADLINE judge shows no options (poetry, round 5 / Camila r3: a
    free-response judge) but which keep an MC judge as a diagnostic column: the guessers here
    guess that MC judge's option lists, so its floor belongs to the MC prompt version, not the
    headline's."""
    from wsbench.evals.poetry.prompts import MC_PROMPT_VERSION

    return {"poetry": MC_PROMPT_VERSION}


def freeze(run_dir: Path, dst: Path = FROZEN) -> dict[str, Any]:
    """Fold ``run_dir/<family>/<variant>.json`` into ``dst`` as ``{family: {variant: {...}}}``;
    entries carry the judge prompt version the lists belonged to (``instrument``). Merges per
    (family, variant): what is not in ``run_dir`` keeps its prior entry. A ``limit`` pilot or a
    run without scored draws is refused (ValueError)."""
    versions = instrument_versions()
    frozen: dict[str, dict[str, Any]] = {}
    for path in sorted(run_dir.glob("*/*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        fam, a = r["family"], r["aggregate"]
        if r.get("limit"):
            raise ValueError(f"freeze: {path} is a limit={r['limit']} pilot, not a baseline")
        if a["mean"] is None:
            raise ValueError(f"freeze: {path} has no scored draws")
        frozen.setdefault(fam, {})[r["variant"]] = {
            "mean": a["mean"],
            "std": a["std"],
            "majority": a["majority"],
            "exact": a.get("exact"),
            "any_hit": a.get("any_hit"),
            "mean_picks": a.get("mean_picks"),
            **({"marks_null": a["marks_null"]} if a.get("marks_null") is not None else {}),
            # two-sided lists (moral_rationale): the side-aware readers of the guesser's draws
            **(
                side_readers(
                    r.get("per_item") or {},
                    bank_directions(r.get("bank")) if fam == "moral_rationale" else None,
                )
                or {}
            ),
            **({"by_n_concepts": a["by_n_concepts"]} if a.get("by_n_concepts") else {}),
            "analytic_floor": r["analytic_floor"],
            **({"family_rule": a["family_rule"]} if a.get("family_rule") is not None else {}),
            **({"family_chance": a["family_chance"]} if a.get("family_chance") is not None else {}),
            **{
                k: a[k]
                for c in HEADLINE_SHARDS
                for k in (f"rule_{c}", f"chance_{c}", f"n_scored_{c}")
                if a.get(k) is not None
            },
            **({"topics": r["topics"]} if r.get("topics") else {}),
            "n_items": a["n_items"],
            "n_draws": a["n_draws"],
            "n_api_fail": a["n_api_fail"],
            "invalid_rate": a["invalid_rate"],
            "n_options_per_list": r["n_options"],
            "model": r["model"],
            "prompt_version": r["prompt_version"],
            "rule": r.get("rule", "single pick"),
            "instrument": r.get("instrument") or versions.get(fam),
            "written": r["written"],
        }
    if not frozen:
        raise ValueError(f"freeze: no <family>/<variant>.json under {run_dir}")
    merged = json.loads(dst.read_text(encoding="utf-8")) if dst.exists() else {}
    for fam, variants in frozen.items():
        merged.setdefault(fam, {}).update(variants)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(merged, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return merged


def floors(dst: Path = FROZEN) -> dict[str, dict[str, Any]]:
    """The frozen lucky-guessing entries whose ``instrument`` matches the family's current judge
    prompt version AND whose guesser ``model`` is the family's judge (the model-free uniform
    variant passes); stale entries are dropped, so a changed instrument or judge needs a
    re-measured floor (plan 0023)."""
    if not dst.exists():
        return {}
    from wsbench.baselines.prompt_only import judge_models

    versions = instrument_versions()
    models = judge_models()
    frozen = json.loads(dst.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for fam, variants in frozen.items():
        current = versions.get(fam)
        live = {
            v: e
            for v, e in variants.items()
            if current
            and e.get("instrument") == current
            and (v.startswith("uniform") or e.get("model") == models.get(fam))
        }
        if live:
            out[fam] = live
    return out


# round 4 (Camila r2 MC leakage standard): every one of these guessers must stay at or below the
# family's uniform chance + LEAKAGE_MARGIN, in EVERY MC family. `topic` is binding everywhere, not
# only where the judge is shown the topic: Camila's confusers must hold "even if the judge can tell
# what the topic is", i.e. a topic the judge infers from the readouts (review of PR #214)
LEAKAGE_MARGIN = 0.05
LEAKAGE_GUESSERS = ("blind", "described", "topic")


def leakage_failures(
    entry: dict[str, Any], chance: float, family: str | None = None
) -> dict[str, float]:
    """The MC leakage standard on one family's live entries (``floors()``): ``variant -> mean`` for
    each measured ``LEAKAGE_GUESSERS`` guesser above ``chance + LEAKAGE_MARGIN`` (empty: passes).
    With ``family``, its ``NOT_A_FLOOR`` guessers are skipped (directed_modulation's ``topic``)."""
    limit = chance + LEAKAGE_MARGIN + 1e-9
    return {
        v: float(entry[v]["mean"])
        for v in LEAKAGE_GUESSERS
        if is_floor(family, v)
        and isinstance(entry.get(v), dict)
        and entry[v].get("mean") is not None
        and float(entry[v]["mean"]) > limit
    }


def bar(entry: dict[str, Any], family: str | None = None) -> tuple[float, str] | None:
    """The highest measured no-readout guesser in one family's live entries (``floors()``), as
    ``(mean, variant)``; the model-free ``uniform`` line is not a guesser. Where a family has the
    question variant this, not the question guesser alone, is the floor a lens must clear: an
    options-only guesser with solved examples can beat the question guesser (moral bank v2:
    described 0.722 > question 0.636, plan 0046 review round 3; bank v3: 0.718 > 0.704).
    Two-sided families also carry each guesser's side-aware readers (``side_readers``: mark every
    option of one side), which are no-readout guessers too, so they compete for the bar as
    ``<variant>:side_follow`` / ``<variant>:side_contra``, and so does the guesser-free
    prior-side reader (always mark the options of one fixed side, :func:`prior_side`) as
    ``side_prior:<side>`` (review of #215: on moral bank v5 the gold guessers top out at 0.500,
    the contrarian question reader passes 0.792 and always-no 0.917). The uniform lines'
    (``uniform*``) guesser side readers never count; their ``side_prior`` does (guesser-free).
    With ``family``, its ``NOT_A_FLOOR`` guessers never count (directed_modulation's ``topic``:
    its topic is the instruction's category, Camila r3)."""
    means: list[tuple[float, str]] = []
    for v, e in entry.items():
        if not isinstance(e, dict) or not is_floor(family, v):
            continue
        if e.get("side_prior") is not None:
            means.append((float(e["side_prior"]), f"side_prior:{e.get('side_prior_dir')}"))
        if v.startswith("uniform"):
            continue
        if e.get("mean") is not None:
            means.append((float(e["mean"]), v))
        means += [(float(e[k]), f"{v}:{k}") for k in SIDE_KEYS[:2] if e.get(k) is not None]
    return max(means) if means else None

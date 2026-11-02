"""Refine the round-4 MC lists that still leak (Camila r2 MC leakage standard, round 4b).

The v3 lists of basic_readout_mt, multihop_mt_v2 and multilingual_multihop
(``scripts/r4_mc_distractors.py`` + ``scripts/r4_mc_select.py``) still let the options-only and
topic guessers beat uniform chance + 5 points. Reading the lists the guessers solve showed three
cues the fame-balanced draw did not remove:

1. **form**: the gold is written in the bank's style and the distractors in Wikipedia's
   ("dalasi" among "Liberian dollar" / "Guinean franc"; "McCune-Albright syndrome" with a hyphen
   among en-dashed names; "Hounsfield units" plural; "Mawsynram village", "monarch butterfly"
   lower case);
2. **topic fit**: distractors outside the topic as literally stated (dependent territories'
   capitals beside "a capital city of a Pacific Island nation"; four tsars and Rasputin under "a
   figure of Imperial Russia"), so the gold is the only option that fits;
3. **cross-list pairing** (multilingual_multihop): the bridge list held several entities of the
   gold language's country ("Kazantzakis" among two more Greek writers beside "Greek"), so the
   pair singled out the gold language.

For every list a REVISE call (Opus 5.5) sees the topic, the kind, the fixed gold (never changed),
the current distractors and the unused pool candidates of ``r4_mc_distractors.py``, and writes
EIGHT distractors: real entities of the kind that fit the topic as literally stated, written in
exactly the gold's naming style, at least two as famous as the gold, none that makes the gold the
odd one out (for a multilingual_multihop bridge list: none tied to the gold language, each tied to
at most one of the other listed languages). Code keeps only candidates with an English Wikipedia
article that is not the gold's entity and that pass ``r4_mc_distractors.screen`` (never in the
prompt, never a form of the gold, of the item's other bridges or of its target).

The guesser gate then shows each candidate list (four of the candidates, a seeded draw) to the
options-only (``blind``) and topic guessers, five draws each, scored by the family's own rule
(an item passes only when every list is right); a list is kept when neither guesser solves its
item in more than :data:`MAX_ITEM_HITS` of the five draws. A failing list gets a fresh draw, and
every second round a fresh REVISE call told how often the guessers found the gold, up to
:data:`ROUNDS` rounds; the least-guessed draw is kept. The frozen floors are re-measured on FRESH
draws afterwards (``wsbench baseline``), never on these.

Passes (each resumes the previous file; ``pass`` is recorded in it):

1. the v3 lists (multilingual_mt / multilingual_typo: their v3 / v2 lists, topic labels written
   by the ``r4_mc_distractors`` topic call) under the blind + topic item gate;
2. ``--pass2``: every topic rewritten to the KIND and the broad field only (:data:`RETOPIC_SYSTEM`;
   a label that kept the question's defining clue was a question guesser), same gate;
3. ``--resume --gate-described``: every item re-measured; the described guesser joins the gate,
   every CONTENT list of a two-list item must also stay at <= :data:`MAX_LIST_HITS` of 5 on its
   own (the language list cannot hide it), one entity never stands twice (Wikidata QID), and
   multilingual_typo's v2 any-topic lists are never kept;
4. ``--resume --gate-described --only F --force G``: the items a FRESH measurement still found
   (any guesser >= 2 of 5) and, forced, the lists the confuser audit
   (``scripts/r4b_confuser_audit.py``) found with fewer than two same-topic confusers.

Writes ``evals/<family>/r4b_distractors.json``. Run:
``ANTHROPIC_AUTH_TOKEN=... .venv/bin/python scripts/r4b_mc_refine.py --pools POOLS fam...``.
"""

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import r4_mc_distractors as gen

from wsbench.banks import load_bank
from wsbench.baselines import lucky_guessing as lg
from wsbench.llm import schema_block, stream_json
from wsbench.multitoken.options import seeded_shuffle as mt_shuffle
from wsbench.registry import REPO_ROOT

FAMILIES = (
    "basic_readout_mt",
    "multihop_mt_v2",
    "multilingual_multihop",
    "multilingual_mt",
    "multilingual_typo",
)
# the content lists of these two are common-noun concepts (no Wikipedia check); their v2/v3
# lists had no topic labels and their language lists were the per-language confusables
CONCEPT_FAMILIES = ("multilingual_mt", "multilingual_typo")
BALANCED_LANG_FAMILIES = ("multilingual_multihop",)
LANG_FAMILIES = ("multilingual_multihop", "multilingual_mt", "multilingual_typo")
LANGUAGE_TOPIC = "the language a short non-English prompt is written in"
SOURCE_BANK = {
    "basic_readout_mt": "items_v3.json",
    "multihop_mt_v2": "items_v3.json",
    "multilingual_multihop": "items_v3.json",
    "multilingual_mt": "items_v3.json",
    "multilingual_typo": "items_v2.json",
}
VERSION = "r4b-refine-2026-11-01"
DRAWS = 5
MAX_ITEM_HITS = 1
ROUNDS = 8
N_NEW = 8
SEED = "r4b-refine-2026-11-01"
REVISE_SYSTEM = (
    "You fix the distractors of a multiple-choice list for an interpretability benchmark. A "
    "judge will read a model's internal readout and pick the option it names; the list must "
    "give NO cue on its own. Guessers who see only the options (or the options and the TOPIC) "
    "must not be able to find the GOLD. Write EIGHT distractors that are: (1) REAL entities of "
    "the given KIND with an English Wikipedia article, that fit the TOPIC as literally stated "
    "(if the topic says 'nation', no dependent territories; if it says 'ruler', no non-rulers); "
    "(2) written in EXACTLY the gold's naming style: same capitalisation, same punctuation "
    "(hyphen vs dash, apostrophes), same qualifiers (a bare name if the gold is bare, a country "
    "adjective only if the gold has one, 'syndrome' / 'Mount' / 'Battle of' only if the gold "
    "has it), same grammatical number, similar length; (3) comparable to the gold so it is never "
    "the odd one out: at least two at least as famous as the gold and none far more obscure, the "
    "same sub-kind and period, never the only one of its sort; (4) never the gold itself, a "
    "synonym, alias, part, instance or translation of it, never something the question's own "
    "words would point to. 'name' is the option text exactly as shown in the list; 'enwiki' the "
    "exact English Wikipedia article title (for a common-noun concept list: the closest "
    "article, or the name itself when there is none). Also say in one sentence what made the "
    "gold stand out in the current list ('cue')."
)
REVISE_SCHEMA = schema_block(
    "revise",
    {
        "cue": {"type": "string"},
        "distractors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "enwiki": {"type": "string"}},
                "required": ["name", "enwiki"],
                "additionalProperties": False,
            },
        },
    },
    ["cue", "distractors"],
)


# pass 2: the first pass's stubborn lists were mostly TOPIC leaks. A topic written from the
# question often kept the question's defining clue ("a genetic syndrome affecting bone, skin and
# endocrine systems", "a named law ... concerning electrical conduction in metals"), which is the
# question guesser, not a topic guesser. The topic is rewritten to the kind and the broad field
# only, what a judge who can tell the subject matter of the readouts would know.
RETOPIC_SYSTEM = (
    "You rewrite the TOPIC label of a multiple-choice list for an interpretability benchmark. "
    "The topic must say only what a reader who glimpsed the SUBJECT MATTER would know: the KIND "
    "of answer and its broad field, region or era. Remove everything only the question's "
    "specific clue tells: no defining property, function, record, superlative, relation, event, "
    "person, date or place from the clue (a broad region or era is fine). 3 to 8 words; at least "
    "twenty different real answers must fit it. Examples: 'a genetic syndrome affecting bone, "
    "skin and endocrine systems' -> 'a rare genetic syndrome'; 'a named law or rule in "
    "solid-state physics concerning electrical conduction in metals' -> 'a named law or rule in "
    "physics'; 'a capital city of a Pacific Island nation' -> 'a town or city of Oceania'; 'a "
    "unit of measurement used in medical imaging or radiology' -> 'a unit of measurement in "
    "science or medicine'; 'a famously rainy inhabited place in the world' -> 'a town or "
    "village of Asia'. Never name or hint at the answer."
)
RETOPIC_SCHEMA = schema_block("retopic", {"topic": {"type": "string"}}, ["topic"])


# pass 4 (multilingual_typo): a topic written from a misspelled passage sometimes named the wrong
# kind ("a biological substance" for endocrinology, "a type of wood" for a carpentry workshop);
# the confuser audit flags a list whose own gold does not fit its topic, and only those topics are
# rewritten by a call that also sees the gold (kind and broad field only, never a hint at it)
FIX_TOPIC_NOTE = (
    "The CURRENT TOPIC names the wrong kind of thing: the answer is {gold!r}. Write the topic of "
    "that answer's kind and broad field, never naming or hinting at the answer itself."
)


def retopic(
    lists: dict[tuple[str, str], dict[str, Any]], keys: list[tuple[str, str]] | None = None
) -> None:
    keys = sorted(lists) if keys is None else sorted(keys)
    msgs = []
    for k in keys:
        v = lists[k]
        sp = v["spec"]
        parts = [f"QUESTION:\n{sp['prompt']}"]
        if sp.get("question"):
            parts.append(f"HOP QUESTION (what this list asks about):\n{sp['question']}")
        parts += [f"KIND: {v['kind']}", f"CURRENT TOPIC: {v['topic']}"]
        if v.get("fix_topic"):
            parts.append(FIX_TOPIC_NOTE.format(gold=v["gold"]))
        parts.append("Give the TOPIC as JSON.")
        msgs.append((RETOPIC_SYSTEM, "\n\n".join(parts)))
    got: dict[int, dict[str, Any] | None] = {}

    def on(i: int, r: dict[str, Any] | None) -> None:
        got[i] = r

    for _attempt in range(3):
        todo = [i for i in range(len(keys)) if not str((got.get(i) or {}).get("topic", "")).strip()]
        if not todo:
            break
        sub = dict(enumerate(todo))

        def on_sub(j: int, r: dict[str, Any] | None, sub: dict = sub) -> None:
            on(sub[j], r)

        stream_json(
            [msgs[i] for i in todo],
            schema=RETOPIC_SCHEMA,
            model=gen.MODEL,
            on_result=on_sub,
            concurrency=64,
        )
    for i, k in enumerate(keys):
        t = str((got.get(i) or {}).get("topic", "")).strip()
        if t:
            if lists[k].get("fix_topic"):
                lists[k]["topic_fixed_from"] = lists[k]["topic"]
            else:
                lists[k]["topic_pass1"] = lists[k]["topic"]
            lists[k]["topic"] = t


def _rng(*key: object) -> random.Random:
    h = hashlib.sha256("|".join(str(k) for k in (SEED, *key)).encode()).digest()[:8]
    return random.Random(int.from_bytes(h, "big"))


def revise_message(
    s: dict[str, Any], cur: list[str], spares: list[str], feedback: str, lang: dict[str, Any]
) -> str:
    parts = [
        f"TOPIC: {s['topic']}",
        f"KIND: {s['kind']}",
        f"GOLD (fixed, never change it): {s['gold']}",
        "CURRENT DISTRACTORS: " + "; ".join(cur),
    ]
    if spares:
        parts.append("UNUSED CANDIDATES (optional material): " + "; ".join(spares[:20]))
    if lang:
        others = [x for x in lang["options"] if x != lang["gold"]]
        parts.append(
            "The item has a second list, the LANGUAGE of the hidden prompt: "
            f"{', '.join(lang['options'])} (gold: {lang['gold']}). A guesser must not pair the "
            f"answer with a language: no distractor may be tied to {lang['gold']} or its "
            "countries, and each distractor may be tied to at most one of "
            f"{', '.join(others)}, a different one for each (or to none)."
        )
    if feedback:
        parts.append(feedback)
    parts.append(f"Write {N_NEW} distractors as JSON.")
    return "\n\n".join(parts)


def _concept_specs(family: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """multilingual_mt / multilingual_typo: one spec per content list, its current options from
    the bank's own builder (``option_sets``: the frozen ``mc`` block, else the seeded draw of
    other items' golds)."""
    from wsbench.multitoken.options import LANGUAGE_ROLE, judged_roles, option_sets

    opts = option_sets(items)
    out = []
    for it in items:
        for role in judged_roles(it):
            if role == LANGUAGE_ROLE:
                continue
            shown, gi = opts[it["id"]][role]
            shown = shown[:-1]
            unit = next(u for u in it["units"] if u["role"] == role)
            out.append(
                {
                    "id": it["id"],
                    "role": role,
                    "prompt": it["prompt"],
                    "question": "",
                    "gold": shown[gi],
                    "gold_forms": [str(f) for fs in unit["forms"].values() for f in fs],
                    "fixed": [],
                    "fixed_forms": [],
                    "avoid": [
                        str(it.get("target", "")),
                        *(str(x) for x in it.get("target_alts") or []),
                        str(it.get("typo_word", "")),
                    ],
                    "note": (
                        "The list asks which CONCEPT (an everyday object, substance, notion or "
                        "body part) the passage names, in English; write the topic of that "
                        "concept."
                    ),
                    "current": [o for j, o in enumerate(shown) if j != gi],
                }
            )
    return out


def concept_topics(family: str, specs: list[dict[str, Any]]) -> dict[tuple[str, str], dict]:
    """The topic call of ``r4_mc_distractors`` (prompt only, never the answer), cached in
    ``evals/<family>/r4b_topics.json`` so a re-run reuses the labels."""
    path = REPO_ROOT / "evals" / family / "r4b_topics.json"
    have = json.loads(path.read_text("utf-8"))["items"] if path.exists() else {}
    out = {
        (s["id"], s["role"]): have[s["id"]][s["role"]]
        for s in specs
        if s["role"] in (have.get(s["id"]) or {})
    }
    for _attempt in range(3):
        todo = [s for s in specs if (s["id"], s["role"]) not in out]
        if not todo:
            break
        got: dict[int, dict[str, Any] | None] = {}

        def on(i: int, r: dict[str, Any] | None, got: dict = got) -> None:
            got[i] = r

        stream_json(
            [(gen.TOPIC_SYSTEM, gen.topic_message(s)) for s in todo],
            schema=gen.TOPIC_SCHEMA,
            model=gen.MODEL,
            on_result=on,
            concurrency=64,
        )
        for i, s in enumerate(todo):
            r = got.get(i) or {}
            if str(r.get("topic", "")).strip():
                out[(s["id"], s["role"])] = {
                    "topic": str(r["topic"]).strip(),
                    "kind": str(r.get("kind", "")).strip(),
                }
    doc: dict[str, Any] = {}
    for (iid, role), v in sorted(out.items()):
        doc.setdefault(iid, {})[role] = v
    path.write_text(
        json.dumps(
            {"family": family, "version": VERSION, "model": gen.MODEL, "items": doc},
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return out


_BALANCED: dict[str, dict[str, list[str]]] = {}


def balanced_languages(family: str) -> dict[str, list[str]]:
    """multilingual_multihop (pass 5): item name -> its frequency-balanced language distractors
    (``options.r4b_balanced_language_distractors`` over the source bank's golds)."""
    from wsbench.multitoken.options import r4b_balanced_language_distractors

    if family not in _BALANCED:
        _h, items = load_bank(REPO_ROOT / "evals" / family / SOURCE_BANK[family])
        golds = {str(it["name"]): str(it["mc"]["language"]["gold"]) for it in items}
        _BALANCED[family] = r4b_balanced_language_distractors(family, golds)
    return _BALANCED[family]


def language_list(family: str, it: dict[str, Any]) -> dict[str, Any]:
    """The item's language list as the new bank freezes it: multilingual_mt / multilingual_typo
    get the v3 rule of multilingual (the four other gold languages of the bank closest to the
    gold, ``r4_language_distractors``); multilingual_multihop (from pass 5) the frequency-balanced
    rule (:data:`BALANCED_LANG_FAMILIES`), since its closest-four lists made a language's mere
    presence a cue (Korean the gold of 15 of the 25 lists it stood in)."""
    from wsbench.multitoken.options import r4_language_distractors

    lb = (it.get("mc") or {}).get("language")
    if family not in LANG_FAMILIES or not isinstance(lb, dict):
        return {}
    ds = list(lb["distractors"])
    if family in CONCEPT_FAMILIES:
        ds = r4_language_distractors(family, str(lb["gold"]))
    elif family in BALANCED_LANG_FAMILIES:
        ds = balanced_languages(family)[str(it["name"])]
    return {"gold": str(lb["gold"]), "options": [str(lb["gold"]), *ds], "distractors": ds}


def load_lists(family: str, pools: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """(item id, role) -> the current list (topic, kind, gold, distractors) + its screening
    spec, pool spares and, for the multilingual families, the item's language list."""
    _h, items = load_bank(REPO_ROOT / "evals" / family / SOURCE_BANK[family])
    bank = {str(it["id"]): it for it in items}
    out: dict[tuple[str, str], dict[str, Any]] = {}
    if family in CONCEPT_FAMILIES:
        specs = _concept_specs(family, items)
        tops = concept_topics(family, specs)
        for s in specs:
            k = (s["id"], s["role"])
            out[k] = {
                "topic": tops[k]["topic"],
                "kind": tops[k]["kind"],
                "gold": s["gold"],
                "v3": list(s["current"]),
                "spec": s,
                "spares": [],
                "lang": language_list(family, bank[s["id"]]),
                "cands": [],
                "cues": [],
            }
        return out
    v3 = json.loads((REPO_ROOT / "evals" / family / "r4_distractors.json").read_text("utf-8"))
    specs_ = {(s["id"], s["role"]): s for s in gen.specs(family)}
    for iid, roles in v3["items"].items():
        for role, b in roles.items():
            pool = (pools.get(family) or {}).get(iid, {}).get(role) or {}
            spares = [str(c["name"]) for c in pool.get("spares") or []]
            spares += [str(d) for d in pool.get("distractors") or []]
            out[(iid, role)] = {
                "topic": b["topic"],
                "kind": b["kind"],
                "gold": b["gold"],
                "v3": list(b["distractors"]),
                "spec": specs_[(iid, role)],
                "spares": [x for x in dict.fromkeys(spares) if x not in b["distractors"]],
                "lang": language_list(family, bank[iid]),
                "cands": [],
                "cues": [],
            }
    return out


def revise(
    lists: dict[tuple[str, str], dict[str, Any]], keys: list, rnd: int, wiki: bool = True
) -> None:
    """One REVISE call per list of ``keys``; screened candidates are appended to ``cands``."""
    msgs = []
    for k in keys:
        v = lists[k]
        fb = ""
        if v.get("last_hits") is not None:
            b, t = v["last_hits"]
            fb = (
                f"In the last list ({'; '.join(v['last_ds'])}) the options-only guesser found "
                f"the gold in {b} of {DRAWS} draws and the topic guesser in {t} of {DRAWS}: "
                "remove whatever singles it out."
            )
        cur = v["last_ds"] if v.get("last_ds") else v["v3"]
        msgs.append(
            (
                REVISE_SYSTEM,
                revise_message({**v, **v["spec"], "topic": v["topic"]}, cur, v["spares"], fb,
                               v["lang"]),
            )
        )  # fmt: skip
    got: dict[int, dict[str, Any] | None] = {}

    def on(i: int, r: dict[str, Any] | None) -> None:
        got[i] = r

    stream_json(msgs, schema=REVISE_SCHEMA, model=gen.MODEL, on_result=on, concurrency=64)
    titles: list[str] = []
    for i, _k in enumerate(keys):
        titles += [str(c.get("enwiki", "")) for c in (got.get(i) or {}).get("distractors") or []]
    for k in keys:
        s = lists[k]["spec"]
        titles += [s["gold"], *s["gold_forms"][:5]]
    qid = gen.qids_of(titles) if wiki else {}
    for i, k in enumerate(keys):
        v = lists[k]
        s = v["spec"]
        r = got.get(i) or {}
        if r.get("cue"):
            v["cues"].append({"round": rnd, "cue": str(r["cue"])})
        gq = {qid[t] for t in [s["gold"], *s["gold_forms"][:5]] if t in qid}
        gq |= set(s.get("gold_qids") or [])
        cands = [
            {"name": str(c.get("name", "")).strip(), "enwiki": str(c.get("enwiki", "")).strip()}
            for c in r.get("distractors") or []
            if isinstance(c, dict)
        ]
        if wiki:
            cands = [c for c in cands if c["enwiki"] in qid and qid[c["enwiki"]] not in gq]
        keep, _dropped = gen.screen(s, cands)
        have = {c["name"].casefold() for c in v["cands"]}
        qids = {c.get("qid") for c in v["cands"]} - {None}
        for c in keep:
            q = qid.get(c["enwiki"]) if wiki else None
            # one entity once: "Mount Kerinci" / "Gunung Kerinci", "glyphosate" /
            # "N-(phosphonomethyl)glycine" are the same Wikidata item
            if c["name"].casefold() in have or (q is not None and q in qids):
                continue
            c["round"] = rnd
            c["qid"] = q
            v["cands"].append(c)
            have.add(c["name"].casefold())
            if q is not None:
                qids.add(q)


def draw(v: dict[str, Any], key: str, rnd: int) -> list[str] | None:
    """Four distractors: the newest REVISE call's first four on its first round, then a seeded
    subset of every screened candidate (newest weighted up)."""
    cands = v["cands"]
    if len(cands) < 4:
        return None
    newest = max(c["round"] for c in cands)
    fresh = [c["name"] for c in cands if c["round"] == newest]
    if v.get("fresh_round") != newest and len(fresh) >= 4:
        v["fresh_round"] = newest
        return fresh[:4]
    r = _rng(key, rnd)
    w = [3.0 if c["round"] == newest else 1.0 for c in cands]
    pick: list[dict[str, Any]] = []
    for _try in range(200):
        if len(pick) == 4:
            break
        c = r.choices(cands, weights=w)[0]
        if c in pick or (c.get("qid") and c.get("qid") in {p.get("qid") for p in pick}):
            continue
        pick.append(c)
    return [c["name"] for c in pick] if len(pick) == 4 else None


GATE_VARIANTS = ["blind", "topic"]


MAX_LIST_HITS = 2  # --max-list-hits (pass 5, multilingual_multihop: 1)


def evaluate(
    family: str, items: list[lg.Item], targets: set[str]
) -> dict[str, tuple[int, int, int]]:
    """item id -> (blind item passes, max over the informed guessers' item passes, max over every
    guesser and every CONTENT list of that list's own gold picks) over DRAWS draws. Item passes
    follow the family's rule (every list right); the per-list count keeps a two-list item from
    hiding a leaky content list behind its language list (a typo list of a hormone among
    "charitable giving" / "coniferous trees" passed the item gate on the language list alone).
    The informed guessers are ``topic`` and, with ``--gate-described``, ``described``."""
    by_id = {it.id: i for i, it in enumerate(items)}
    calls: list[tuple[str, str, str]] = []
    for iid in sorted(targets):
        idx = by_id[iid]
        it = items[idx]
        ex = lg.pick_examples(items, idx, family, lg.DEFAULT_SEED)
        for variant in GATE_VARIANTS:
            msg = lg.user_message(it, variant, family, None if variant == "blind" else ex)
            calls += [(iid, variant, msg)] * DRAWS
    got: dict[int, dict[str, Any] | None] = {}
    shapes = {iid: len(items[by_id[iid]].lists) for iid in targets}
    for n in sorted(set(shapes.values())):
        sub = [j for j, c in enumerate(calls) if shapes[c[0]] == n]

        def on(k: int, r: dict[str, Any] | None, sub: list = sub) -> None:
            got[sub[k]] = r

        stream_json(
            [(lg.SYSTEM, calls[j][2]) for j in sub],
            schema=lg.schema(n),
            model=gen.MODEL,
            on_result=on,
            concurrency=128,
            rpm=3000,
            max_tokens=lg.MAX_TOKENS,
        )
    out: dict[str, dict[str, int]] = {}
    per_list: dict[str, dict[tuple[str, int], int]] = {}
    for j, (iid, variant, _m) in enumerate(calls):
        it = items[by_id[iid]]
        r = got.get(j) or {}
        hit = all(r.get(f"choice{li + 1}") == g for li, g in enumerate(it.golds))
        cur = out.setdefault(iid, dict.fromkeys(GATE_VARIANTS, 0))
        cur[variant] += int(hit)
        roles = list(it.meta.get("roles") or [])
        pl = per_list.setdefault(iid, {})
        for li, g in enumerate(it.golds):
            if li < len(roles) and roles[li] == "language":
                continue
            pl[(variant, li)] = pl.get((variant, li), 0) + int(r.get(f"choice{li + 1}") == g)
    return {
        k: (
            v["blind"],
            max(n for var, n in v.items() if var != "blind"),
            max(per_list.get(k, {}).values(), default=0),
        )
        for k, v in out.items()
    }


def assemble(
    family: str, lists: dict[tuple[str, str], dict[str, Any]], choice: dict, bank: dict
) -> list[lg.Item]:
    items = lg.build_family(family)
    topics = lg.load_list_topics(family) if family not in CONCEPT_FAMILIES else {}
    out = []
    for it in items:
        roles = list(it.meta.get("roles") or [])
        ls = [list(x) for x in it.lists]
        golds = list(it.golds)
        tops = list(topics.get(it.id, [""] * len(ls)))
        for li, role in enumerate(roles):
            k = (it.id, role)
            if role == "language" and family in (*CONCEPT_FAMILIES, *BALANCED_LANG_FAMILIES):
                lang = language_list(family, bank[it.id])
                order = mt_shuffle(f"{bank[it.id]['name']}|{role}", list(lang["options"]))
                ls[li] = order
                golds[li] = order.index(lang["gold"]) + 1
                tops[li] = LANGUAGE_TOPIC
                continue
            if k not in lists:
                continue
            ds = choice.get(k) or lists[k]["v3"]
            order = mt_shuffle(f"{bank[it.id]['name']}|{role}", [lists[k]["gold"], *ds])
            ls[li] = order
            golds[li] = order.index(lists[k]["gold"]) + 1
            tops[li] = lists[k]["topic"]
        out.append(lg.Item(it.id, ls, golds, it.multi, {**it.meta, "topics": tops}))
    return out


def run(
    family: str,
    pools: dict[str, Any],
    rounds: int,
    pass2: bool = False,
    resume: bool = False,
    only: set[str] | None = None,
    force: set[str] | None = None,
    fix_topics: set[str] | None = None,
) -> dict[str, Any]:
    """``pass2``: rewrite every topic (:func:`retopic`) and start from pass 1's lists;
    ``resume`` (pass 3): start from the current file's lists AND topics, re-measure every item,
    and redraw the ones over the gate or holding one entity twice."""
    lists = load_lists(family, pools)
    prev: dict[str, Any] = {}
    prev_pass = 1
    if pass2 or resume:
        path = REPO_ROOT / "evals" / family / "r4b_distractors.json"
        doc = json.loads(path.read_text("utf-8"))
        prev, prev_pass = doc["items"], int(doc.get("pass", 1))
    if pass2:
        retopic(lists)
    if resume:
        for k, v in lists.items():
            p1 = (prev.get(k[0]) or {}).get(k[1]) or {}
            if p1.get("topic"):
                v["topic"] = p1["topic"]
                if p1.get("topic_pass1"):
                    v["topic_pass1"] = p1["topic_pass1"]
                if p1.get("topic_fixed_from"):
                    v["topic_fixed_from"] = p1["topic_fixed_from"]
        if fix_topics:
            fk = [k for k in lists if k[0] in fix_topics]
            for k in fk:
                lists[k]["fix_topic"] = True
            retopic(lists, fk)
    _h, items = load_bank(REPO_ROOT / "evals" / family / SOURCE_BANK[family])
    bank = {str(it["id"]): it for it in items}
    by_item: dict[str, list[tuple[str, str]]] = {}
    for k in lists:
        by_item.setdefault(k[0], []).append(k)
    choice: dict[tuple[str, str], list[str]] = {}
    for k, v in lists.items():
        p1 = (prev.get(k[0]) or {}).get(k[1])
        if p1:
            choice[k] = list(p1["distractors"])
            v["cues"] = list(p1.get("cues") or [])
            v["cands"] = [
                {"name": n, "enwiki": (p1.get("enwiki") or {}).get(n, n), "round": 0}
                for n in p1["distractors"]
            ]
    dup: set[str] = set()
    if resume and family not in CONCEPT_FAMILIES:
        q = gen.qids_of([c["enwiki"] for v in lists.values() for c in v["cands"]])
        q.update(gen.qids_of([v["gold"] for v in lists.values()]))
        for k, v in lists.items():
            for c in v["cands"]:
                c["qid"] = q.get(c["enwiki"])
            seen = [c["qid"] for c in v["cands"] if c["qid"]]
            if len(set(seen)) < len(seen) or q.get(v["gold"]) in seen:
                dup.add(k[0])
                # keep the first of a repeated entity in the pool, drop the repeat
                keep_c, got_q = [], {q.get(v["gold"])} - {None}
                for c in v["cands"]:
                    if c["qid"] and c["qid"] in got_q:
                        continue
                    keep_c.append(c)
                    if c["qid"]:
                        got_q.add(c["qid"])
                v["cands"] = keep_c
    best: dict[str, tuple[int, dict, tuple[int, int], int]] = {}
    lang_of = {k[0]: v["lang"] for k, v in lists.items() if v["lang"]}
    # ``force``: lists the confuser audit (scripts/r4b_confuser_audit.py) found with fewer than two
    # same-topic confusers are never kept as they are
    dup |= set(force or ())
    # multilingual_typo's v2 content lists were a seeded draw over the OTHER items' golds (any
    # topic): never kept, every one is revised
    if family == "multilingual_typo":
        for k, v in lists.items():
            if choice.get(k, v["v3"]) == v["v3"]:
                dup.add(k[0])
    # round 0 measures the v3 lists as they are (a list that already passes is kept); ``only``
    # (a resumed pass): re-measure and redraw those items only, keep every other item's list and
    # gate record as the previous pass left them
    todo = set(by_item) if only is None else set(by_item) & only
    if only is not None:
        for iid in set(by_item) - todo:
            g = next(iter((prev.get(iid) or {}).values()), {}).get("gate") or {}
            b0 = int(g.get("blind_item_passes", 0))
            t0 = int(g.get("informed_item_passes", g.get("topic_item_passes", 0)))
            cur0 = {k: list(choice.get(k) or lists[k]["v3"]) for k in by_item[iid]}
            best[iid] = (max(b0, t0) * 10 + b0 + t0, cur0, (b0, t0), 0)
    for rnd in range(rounds + 1):
        if rnd > 0:
            need = [k for iid in sorted(todo) for k in by_item[iid]]
            if rnd % 2 == 1:
                revise(lists, need, rnd, wiki=family not in CONCEPT_FAMILIES)
            for k in need:
                d = draw(lists[k], f"{family}|{k}", rnd)
                if d is not None:
                    choice[k] = d
        new_items = assemble(family, lists, choice, bank)
        res = evaluate(family, new_items, todo)
        nxt = set()
        for iid in todo:
            b, t, lmax = res.get(iid, (DRAWS, DRAWS, DRAWS))
            over_list = len(by_item[iid]) + int(bool(lang_of.get(iid))) > 1 and lmax > MAX_LIST_HITS
            score = max(b, t) * 10 + b + t + (100 if over_list else 0)
            cur = {k: list(choice.get(k) or lists[k]["v3"]) for k in by_item[iid]}
            if rnd == 0 and iid in dup:
                score = 10**6  # a list holding one entity twice is never kept
            if iid not in best or score < best[iid][0]:
                best[iid] = (score, cur, (b, t), rnd)
            for k in by_item[iid]:
                lists[k]["last_hits"] = (b, t)
                lists[k]["last_ds"] = cur[k]
            if max(b, t) > MAX_ITEM_HITS or over_list or (rnd == 0 and iid in dup):
                nxt.add(iid)
        print(f"{family} round {rnd}: {len(todo)} items judged, {len(nxt)} over the gate",
              flush=True)  # fmt: skip
        todo = nxt
        if not todo:
            break
    out_items: dict[str, dict[str, Any]] = {}
    for iid, (_score, cur, (b, t), rnd) in best.items():
        for k in by_item[iid]:
            v = lists[k]
            en = {c["name"]: c["enwiki"] for c in v["cands"]}
            out_items.setdefault(iid, {})[k[1]] = {
                "topic": v["topic"],
                **({"topic_pass1": v["topic_pass1"]} if "topic_pass1" in v else {}),
                **({"topic_fixed_from": v["topic_fixed_from"]} if "topic_fixed_from" in v else {}),
                "kind": v["kind"],
                "gold": v["gold"],
                "distractors": cur[k],
                "enwiki": {n: en[n] for n in cur[k] if n in en},
                "kept_round": rnd,
                "gate": {
                    "blind_item_passes": b,
                    "informed_item_passes": t,
                    "informed": GATE_VARIANTS[1:],
                    "draws": DRAWS,
                },
                "cues": v["cues"],
            }
    n_over = sum(1 for v in best.values() if max(v[2]) > MAX_ITEM_HITS or v[0] >= 100)
    print(f"{family}: {len(best)} items, {n_over} still over the gate", flush=True)
    return {
        "family": family,
        "version": VERSION,
        "model": gen.MODEL,
        "script": "scripts/r4b_mc_refine.py (pools: scripts/r4_mc_distractors.py)",
        "supersedes": "r4_distractors.json (bank v3)",
        "gate": {"draws": DRAWS, "max_item_passes": MAX_ITEM_HITS, "rounds": rounds},
        "pass": prev_pass + 1 if resume else (2 if pass2 else 1),
        "n_over_gate": n_over,
        "items": dict(sorted(out_items.items())),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("families", nargs="*", default=list(FAMILIES))
    ap.add_argument("--pools", type=Path, required=True, help="r4_mc_distractors.py output")
    ap.add_argument("--rounds", type=int, default=ROUNDS)
    ap.add_argument("--pass2", action="store_true", help="retopic, resume from pass 1's lists")
    ap.add_argument("--resume", action="store_true", help="pass 3+: resume lists and topics")
    ap.add_argument("--gate-described", action="store_true", help="gate on described too")
    ap.add_argument("--only", type=Path, help="JSON {family: [item ids]} to redraw (resume)")
    ap.add_argument("--force", type=Path, help="JSON {family: [item ids]} never kept as is")
    ap.add_argument("--fix-topics", type=Path, help="JSON {family: [ids]}: gold-aware retopic")
    ap.add_argument("--max-list-hits", type=int, default=MAX_LIST_HITS)
    a = ap.parse_args(argv)
    pools = json.loads(a.pools.read_text(encoding="utf-8"))
    if a.gate_described:
        GATE_VARIANTS.append("described")
    globals()["MAX_LIST_HITS"] = a.max_list_hits  # read by run() at call time
    for fam in a.families:
        only = None
        if a.only:
            only = set(json.loads(a.only.read_text(encoding="utf-8")).get(fam, []))
        force = None
        if a.force:
            force = set(json.loads(a.force.read_text(encoding="utf-8")).get(fam, []))
        fix = None
        if a.fix_topics:
            fix = set(json.loads(a.fix_topics.read_text(encoding="utf-8")).get(fam, []))
        doc = run(fam, pools, a.rounds, a.pass2, a.resume, only, force, fix)
        path = REPO_ROOT / "evals" / fam / "r4b_distractors.json"
        path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

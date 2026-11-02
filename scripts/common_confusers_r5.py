"""Round 5 "common" confusers (Camila r3 (1), 2026-11-01): basic_readout's implicit items and every
association item get 3-4 FREQUENCY-MATCHED, equally common confusers ADDED to their option list
("favourite fruit apple -> orange, banana, grape"), on items where Qwen commits to the gold in
>= 8 of 10 samples. Every option the list already holds stays (each earlier judge-picked or
readout-named confuser is on it), so a list only grows.

Stages (resumable; Opus calls cached per key under ``<out>/<family>/cache``)::

    python scripts/common_confusers_r5.py requests --out <dir>     # Qwen gate requests
    (modal run scripts/qwen_sample_modal.py --requests <dir>/gate_requests.jsonl ...)
    python scripts/common_confusers_r5.py gate --out <dir> --samples <samples.jsonl>
    python scripts/common_confusers_r5.py build --family basic_readout --out <dir>
    python scripts/common_confusers_r5.py build --family association --out <dir>
    python scripts/common_confusers_r5.py replay --family basic_readout --judged <judged root> \
        --rejudged <dir> --dest <report.json>

**Gate** (:data:`GATE_RULE`): Qwen3.6-27B, 10 samples at temperature 0.7. basic_readout implicit:
the item's exact eval render (chat template, thinking off, the user turn = the prompt, assistant
prefill "My one-word answer is:", 8 tokens; bank v5's gate render). association: the read render
asks for a one-sentence summary, which need not name the concept, so the gate asks the bank's
own referent question over the exact scene (``capable.questions.NAME_REFERENT``, the answer
system turn of ``capable.run``; 24 tokens). A sample commits to the gold when its first line
holds the gold or a listed alias as a whole word (``adapt.gate.grade_contains``); association
samples no listed form matches are shown to Opus 5.5, which accepts an answer that names the
gold concept itself (a synonym, inflection or translation; never a broader / narrower / related
concept), 3 draws, unanimous. Kept: >= 8 / 10. An implicit item below that is re-keyed when one
other answer reaches 8 / 10 (Qwen's favourite moved), else dropped.

**Confusers** (:data:`COMMON_RULE`): Opus 5.5 proposes the members of the item's topic that are
as COMMON as the gold (implicit: the answers most often given to the same favourite question;
association: concepts of the item's fine category as everyday and as often evoked as the gold),
never one already on the list. Each candidate passes mc_leakage_r4's lint (no shared form with
the gold or any option, never a word of the text the model reads) and kinship check (no kind,
part, near-synonym or broader term of the gold); association candidates also pass the scene
screen (Opus 5.5 sees the scene and the WHOLE grown list, 5 draws, the gold must win every
draw; a new option that wins once is banned and replaced). Frequency match: ``wordfreq``'s Zipf
frequency of the option (English; the scene language for pt- / de- / es- / it- items) within
:data:`ZIPF_WINDOW` of the gold's; candidates outside the window are used only when too few fall
inside it, nearest first. :data:`N_ADD` added per list (fewer only when the pool runs dry; >=
:data:`MIN_ADD`).
"""

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mc_leakage_r4 as r4

from wsbench import mc
from wsbench.adapt import moral as am
from wsbench.adapt.gate import Ask, first_line, grade_contains
from wsbench.banks import label_of
from wsbench.llm import schema_block

REPO = Path(__file__).resolve().parents[1]
VERSION = "common-r5-2026-11-01"
N_ADD = 4
MIN_ADD = 3
N_PROPOSE = 12
ZIPF_WINDOW = 1.0
GATE_N = 10
GATE_MIN = 8
EQUIV_DRAWS = 3
OWN_STEM = "My one-word answer is:"

BANKS = {
    "basic_readout": ("evals/basic_readout/items_v5.json", "evals/basic_readout/items_v6.json"),
    "association": ("evals/association/items_v3.json", "evals/association/items_v4.json"),
}
OLD_KEY = {"basic_readout": "distractors_v5", "association": "distractors_v3"}
STAMP = {"basic_readout": "br-mc-2026-11-01-v6", "association": "assoc-mc-2026-11-01-v4"}

GATE_RULE = (
    "Camila r3 (1): only items where Qwen commits to the gold in >= 8 of 10 samples. Qwen3.6-27B "
    "on Modal (scripts/qwen_sample_modal.py), 10 samples, temperature 0.7, top_p 1. "
    "basic_readout implicit: the exact eval render (chat template, enable_thinking=False, user "
    "turn = the prompt, assistant prefill 'My one-word answer is:', 8 tokens). association: the "
    "read render asks for a one-sentence summary, which need not name the concept, so the gate "
    "asks the bank's referent question over the exact scene (capable.questions.NAME_REFERENT "
    "with capable.run.ANSWER_SYSTEM, 24 tokens). A sample commits when its first line holds the "
    "gold or a listed alias as a whole word (adapt.gate.grade_contains); an association answer "
    "no listed form matches counts when Opus 5.5 rules, unanimously over 3 draws, that it names "
    "the gold concept itself (synonym, inflection, translation; never a broader, narrower or "
    "related concept). Kept: >= 8/10; an implicit item below that is re-keyed when one other "
    "answer reaches 8/10, else dropped"
)
COMMON_RULE = (
    "Camila r3 (1): add 3-4 frequency-matched, equally common confusers per list (apple -> "
    "orange, banana, grape; piano -> violin, guitar, drums). Every option already on the list "
    "stays (each earlier judge-picked or readout-named confuser is on it: lists only grow). Opus "
    "5.5 proposes members of the item's topic as common as the gold (implicit: the answers most "
    "often given to the same favourite question; association: concepts of the item's fine "
    "category as everyday and as often evoked as the gold), never one already listed; each passes "
    "mc_leakage_r4's lint and kinship check; association candidates also pass the scene screen "
    "(the gold wins 5/5 against the whole grown list). Frequency match: wordfreq Zipf of the "
    f"option within {ZIPF_WINDOW} of the gold's (English; the scene language for pt-/de-/es-/it- "
    "items), out-of-window candidates only when too few fall inside, nearest first. "
    f"{N_ADD} added per list"
)

PROPOSE_SYSTEM = """You add WRONG options to a multiple-choice benchmark item. A guesser will see \
the options (sometimes with the item's topic and solved examples of other items) but never the \
question or any evidence, and must not be able to tell which option is correct. The list already \
holds some wrong options; you add answers that are EQUALLY COMMON as the correct answer: {freq} \
Return JSON {{"candidates": [{{"option": ..., "forms": [...]}}, ...]}}.
- "candidates": {n} WRONG answers, the most common first. Each is a clear member of the item's \
topic, of the SAME surface form as the correct answer (a common noun for a common noun, a proper \
name for a proper name, the same language, about the same length and register) and about as \
common, everyday and well known as the correct answer. Never one of the options already listed, \
and never a synonym, alias, translation, spelling variant, plural, broader category, narrower \
instance, part or close variant of the correct answer or of a listed option; no two candidates \
may be the same thing.{scene}
- "forms": the candidate's accepted alternate forms a reader may write instead of it: inflections \
and plurals, spelling variants, established short names, and its translations into Simplified \
Chinese{lang} (list Chinese forms explicitly). Never a broader category or a related word."""
FREQ = {
    "basic_readout": "the other answers people give to this exact favourite question about as "
    "often as the correct answer (the top answers to it). For 'What is your favorite fruit?' with "
    "correct answer apple: orange, banana, grape; for a favourite musical instrument with piano: "
    "violin, guitar, drums.",
    "association": "other concepts of exactly the item's topic that are as common, everyday and "
    "famous as the correct answer, i.e. as often named, written about and evoked by a short "
    "scene (for 'a board game' with chess: checkers, Monopoly, Scrabble; for 'a beverage / hot "
    "drink' with coffee: tea, hot chocolate).",
}
SCENE_CLAUSE = (
    " The item is a short scene that evokes the correct answer; a candidate must NOT be a "
    "defensible answer for a scene that evokes the correct answer (no setting, ingredient, "
    "participant or typical accompaniment of it)."
)
PROPOSE_USER = """Item type: {kind}
Topic: {topic}
Correct answer: {gold}
Its accepted forms: {forms}
Options already listed (keep; never repeat): {current}
{exclude}Return the JSON."""
PROPOSE_SCHEMA = schema_block(
    "common_propose",
    {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "option": {"type": "string"},
                    "forms": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["option", "forms"],
                "additionalProperties": False,
            },
        }
    },
    ["candidates"],
)
EQUIV_SYSTEM = """A model was shown a short text that evokes one concept without naming it and \
was asked to name it. Decide whether its ANSWER names the TARGET concept itself: the same word in \
another inflection or spelling, an established synonym or alias, or a faithful translation. A \
broader category, a narrower kind, a part, a setting or a merely related idea is NOT the target. \
Return JSON {"same": true|false}."""
EQUIV_SCHEMA = schema_block("common_equiv", {"same": {"type": "boolean"}}, ["same"])


def load(path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = json.loads((REPO / path).read_text(encoding="utf-8"))
    for it in raw["items"]:
        it.setdefault("id", label_of(it["name"]))
    return {k: v for k, v in raw.items() if k != "items"}, raw["items"]


def in_scope(family: str, it: dict[str, Any]) -> bool:
    return family == "association" or it.get("subfamily") == "implicit"


def gold_forms(it: dict[str, Any]) -> list[str]:
    return [str(it["mc"]["gold"]), *[str(a) for a in it["mc"].get("aliases") or []]]


# ---------------------------------------------------------------- gate


def requests(out: Path) -> Path:
    from wsbench.capable.questions import NAME_REFERENT
    from wsbench.capable.run import ANSWER_SYSTEM

    rows = []
    for family, (old, _new) in BANKS.items():
        _h, items = load(old)
        for it in items:
            if not in_scope(family, it):
                continue
            base = {"key": f"{family}|{it['name']}", "family": family, "n": GATE_N,
                    "temperature": 0.7, "top_p": 1.0, "top_k": -1, "enable_thinking": False,
                    "greedy": False}  # fmt: skip
            if family == "basic_readout":
                msgs = [{"role": "user", "content": it["prompt"]}]
                rows.append({**base, "messages": msgs, "prefill": OWN_STEM, "max_tokens": 8})
            else:
                msgs = [
                    {"role": "system", "content": ANSWER_SYSTEM},
                    {"role": "user", "content": f"{NAME_REFERENT}\n\n{it['prompt']}"},
                ]
                rows.append({**base, "messages": msgs, "max_tokens": 24})
    out.mkdir(parents=True, exist_ok=True)
    p = out / "gate_requests.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    print(f"{len(rows)} requests -> {p}")
    return p


_EDGE = re.compile(r"^[\W_]+|[\W_]+$")


def norm_answer(text: str) -> str:
    """The answer's first line without markdown, emoji or edge punctuation (for counting)."""
    line = first_line(text).replace("*", "").strip()
    return _EDGE.sub("", line).strip()


def gate(out: Path, samples: Path) -> dict[str, Any]:
    by_key: dict[str, list[str]] = collections.defaultdict(list)
    for ln in samples.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            if not r.get("greedy"):
                by_key[r["key"]].append(str(r.get("text") or ""))
    rec: dict[str, Any] = {}
    equiv_tasks: dict[str, tuple[str, str]] = {}
    pending: dict[str, list[tuple[int, str]]] = {}
    items_of: dict[str, dict[str, Any]] = {}
    for family, (old, _new) in BANKS.items():
        _h, items = load(old)
        for it in items:
            if not in_scope(family, it):
                continue
            texts = by_key.get(f"{family}|{it['name']}") or []
            if len(texts) != GATE_N:
                raise SystemExit(f"{family}|{it['name']}: {len(texts)} samples, want {GATE_N}")
            ask = Ask(it["id"], "surface", tuple(gold_forms(it)))
            hits = [bool(grade_contains(ask, t)) for t in texts]
            answers = [norm_answer(t) for t in texts]
            key = f"{family}|{it['id']}"
            items_of[key] = it
            rec[key] = {
                "family": family,
                "id": it["id"],
                "gold": it["mc"]["gold"],
                "answers": dict(collections.Counter(answers)),
                "listed": sum(hits),
            }
            if family == "association":
                for i, (h, a) in enumerate(zip(hits, answers, strict=True)):
                    if h or not a:
                        continue
                    pending.setdefault(key, []).append((i, a))
                    user = f"TARGET: {it['mc']['gold']}\nANSWER: {a}"
                    h = hashlib.sha256(user.encode()).hexdigest()[:12]
                    for d in range(EQUIV_DRAWS):
                        equiv_tasks[f"{key}|{h}|d{d}"] = (EQUIV_SYSTEM, user)
            rec[key]["hits"] = hits
    res = am.claude_json(equiv_tasks, EQUIV_SCHEMA, out / "cache" / "equiv.jsonl", concurrency=128)
    for key, pend in pending.items():
        it = items_of[key]
        for i, a in pend:
            user = f"TARGET: {it['mc']['gold']}\nANSWER: {a}"
            h = hashlib.sha256(user.encode()).hexdigest()[:12]
            votes = [res.get(f"{key}|{h}|d{d}") for d in range(EQUIV_DRAWS)]
            if any(v is None for v in votes):
                raise SystemExit(f"{key}: equivalence call failed; rerun")
            if all(bool(v["same"]) for v in votes):
                rec[key]["hits"][i] = True
                rec[key].setdefault("equivalent", []).append(a)
    for r in rec.values():
        r["correct"] = sum(r.pop("hits"))
        r["verdict"], top = verdict(r["family"], r["correct"], r["answers"])
        if top:
            r["rekey_to"] = top
        r["equivalent"] = sorted(set(r.get("equivalent", [])))
    p = out / "gate_r5.json"
    p.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", "utf-8")
    c = collections.Counter((r["family"], r["verdict"]) for r in rec.values())
    print(f"gate -> {p}: {dict(c)}")
    for key, r in rec.items():
        if r["verdict"] != "keep":
            print(f"  {key}: {r['verdict']} {r['correct']}/10 {r['answers']}")
    return rec


def verdict(family: str, correct: int, answers: dict[str, int]) -> tuple[str, str]:
    """(:data:`GATE_RULE`) ``("keep", "")`` at >= :data:`GATE_MIN` of :data:`GATE_N` gold
    commits; below it a basic_readout item whose single most common (non-empty) answer reaches
    :data:`GATE_MIN` is ``("rekey", that answer)``, anything else ``("drop", "")``."""
    if correct >= GATE_MIN:
        return "keep", ""
    if family == "basic_readout":
        common = collections.Counter({k: v for k, v in answers.items() if k}).most_common(1)
        if common and common[0][1] >= GATE_MIN:
            return "rekey", common[0][0]
    return "drop", ""


# ---------------------------------------------------------------- confusers


def zipf(text: str, lang: str) -> float:
    from wordfreq import zipf_frequency

    return round(float(zipf_frequency(text, lang)), 2)


def lang_of(family: str, it: dict[str, Any]) -> str:
    if family == "association":
        for pre in ("pt-", "de-", "es-", "it-"):
            if it["id"].startswith(pre):
                return pre[:2]
    return "en"


def topic_of(fam: r4.Fam, it: dict[str, Any]) -> str:
    if fam.name == "basic_readout":
        return f"the model's own favourite: {it['prompt']}"
    return r4.topic(fam, it, {})


def propose(fam: r4.Fam, items: list[dict[str, Any]], st: dict, out: Path, rnd: int) -> None:
    tasks: dict[str, tuple[str, str]] = {}
    for it in items:
        s = st[it["id"]]
        if len(s["added"]) >= N_ADD:
            continue
        lang = ""
        for pre, name in r4.SCENE_LANG.items():
            if fam.name == "association" and it["id"].startswith(pre):
                lang = f" and into the scene language ({name}; the correct answer is in it)"
        exclude = sorted(set(s["banned"]) | set(s["pool"]))
        user = PROPOSE_USER.format(
            kind=fam.kind,
            topic=topic_of(fam, it),
            gold=it["mc"]["gold"],
            forms=", ".join(gold_forms(it)),
            current=", ".join(it["mc"]["distractors"]),
            exclude=f"Do NOT propose any of these: {', '.join(exclude)}\n" if exclude else "",
        )
        system = PROPOSE_SYSTEM.format(
            freq=FREQ[fam.name],
            n=N_PROPOSE,
            scene=SCENE_CLAUSE if fam.name == "association" else "",
            lang=lang,
        )
        tasks[f"{it['id']}|r{rnd}"] = (system, user)
    if not tasks:
        return
    res = am.claude_json(tasks, PROPOSE_SCHEMA, out / fam.name / "cache" / "propose.jsonl",
                         concurrency=128)  # fmt: skip
    for key, r in res.items():
        s = st[key.split("|")[0]]
        for c in (r or {}).get("candidates") or []:
            o = str(c.get("option") or "").strip()
            if o and o not in s["pool"]:
                s["pool"][o] = [str(f).strip() for f in c.get("forms") or [] if str(f).strip()]
                s["order"].append(o)


def eligible(fam: r4.Fam, it: dict[str, Any], s: dict, cand: str) -> str:
    """'' when ``cand`` may join the grown list, else why not (mc_leakage_r4's lint against the
    list as it stands plus the options added so far)."""
    r4.ST[it["id"]] = {"pool": {**s["old_forms"], **s["pool"]}}
    if cand in s["banned"]:
        return "banned"
    if mc.fold(cand) in {mc.fold(d) for d in it["mc"]["distractors"]}:
        return "already listed"
    return r4.lint(fam, it, cand, [*it["mc"]["distractors"], *s["added"]])


def choose(fam: r4.Fam, it: dict[str, Any], s: dict) -> None:
    """Fill ``s['added']`` up to :data:`N_ADD`: lint-clean, unflagged candidates, in-window first
    (proposer order), then nearest Zipf."""
    g = zipf(str(it["mc"]["gold"]), s["lang"])
    s["gold_zipf"] = g
    cands = [c for c in s["order"] if c not in s["added"]]
    scored = []
    for c in cands:
        z = zipf(c, s["lang"])
        s["zipf"][c] = z
        scored.append((abs(z - g) > ZIPF_WINDOW, abs(z - g) if abs(z - g) > ZIPF_WINDOW else 0,
                       s["order"].index(c), c))  # fmt: skip
    for _out, _d, _i, c in sorted(scored):
        if len(s["added"]) >= N_ADD:
            break
        why = eligible(fam, it, s, c)
        if why:
            s["rejected"][c] = why
            continue
        s["added"].append(c)


SCREEN_DRAWS = 5


def screen(fam: r4.Fam, items: list[dict[str, Any]], st: dict, out: Path) -> int:
    """association: the gold must win every draw against the whole grown list with the scene
    shown; a NEW option that wins is banned (returns how many). Old options are never touched."""
    tasks: dict[str, tuple[str, str]] = {}
    orders: dict[str, list[str]] = {}
    for it in items:
        s = st[it["id"]]
        opts = [str(it["mc"]["gold"]), *it["mc"]["distractors"], *s["added"]]
        for d in range(SCREEN_DRAWS):
            o = list(opts)
            r4._rng(VERSION, "screen", it["id"], d).shuffle(o)
            user = r4.SCREEN_USER["association"].format(text=it["prompt"], listing=r4.listing(o))
            key = f"{it['id']}|{hashlib.sha256(user.encode()).hexdigest()[:12]}"
            tasks[key] = (r4.SCREEN_SYSTEM["association"], user)
            orders[key] = o
    res = am.claude_json(tasks, r4.SCREEN_SCHEMA, out / fam.name / "cache" / "screen.jsonl",
                         concurrency=128)  # fmt: skip
    banned = 0
    for key, r in res.items():
        iid = key.split("|")[0]
        s = st[iid]
        o = orders[key]
        ch = (r or {}).get("choice")
        if r is None:
            raise SystemExit(f"{iid}: screen call failed; rerun")
        if isinstance(ch, int) and 1 <= ch <= len(o):
            pick = o[ch - 1]
            if pick in s["added"]:
                s["added"].remove(pick)
                s["banned"].append(pick)
                s["rejected"][pick] = "won a scene-screen draw"
                banned += 1
            elif pick != s["gold"]:
                s.setdefault("old_screen_wins", []).append(pick)
    return banned


def member(fam: r4.Fam, items: list[dict[str, Any]], st: dict, out: Path) -> int:
    """mc_leakage_r4's topic-member check: a candidate that is not a clear member of the item's
    topic (a 'weekend' for a day of the week) confuses no one and is banned."""
    tasks: dict[str, tuple[str, str]] = {}
    for it in items:
        s = st[it["id"]]
        pool = [c for c in s["pool"] if c not in s["banned"]]
        if not pool:
            continue
        user = f"Topic: {topic_of(fam, it)}\nCandidates:\n" + "\n".join(f"- {c}" for c in pool)
        tasks[f"{it['id']}|{hashlib.sha256(user.encode()).hexdigest()[:12]}"] = (
            r4.MEMBER_SYSTEM,
            user,
        )
    res = am.claude_json(tasks, r4.MEMBER_SCHEMA, out / fam.name / "cache" / "member.jsonl",
                         concurrency=128)  # fmt: skip
    n = 0
    for key, r in res.items():
        s = st[key.split("|")[0]]
        if r is None:
            raise SystemExit(f"{key}: member call failed; rerun")
        keep = {mc.fold(str(m)).strip() for m in r.get("members") or []}
        for c in [c for c in s["pool"] if c not in s["banned"]]:
            if mc.fold(c).strip() not in keep:
                s["banned"].append(c)
                s["rejected"][c] = "not a clear member of the topic"
                if c in s["added"]:
                    s["added"].remove(c)
                n += 1
    return n


def kin(fam: r4.Fam, items: list[dict[str, Any]], st: dict, out: Path) -> int:
    """mc_leakage_r4's kinship check over each item's unflagged pool; a flagged candidate is
    banned (old options are never touched)."""
    r4st = {it["id"]: {"pool": dict(st[it["id"]]["pool"]), "banned": list(st[it["id"]]["banned"])}
            for it in items}  # fmt: skip
    flags = r4.kin_flags(fam, items, r4st, out)
    n = 0
    for it in items:
        s = st[it["id"]]
        for c in flags.get(it["id"], []):
            if c in s["pool"] and c not in s["banned"]:
                s["banned"].append(c)
                s["rejected"][c] = "kinship flag"
                if c in s["added"]:
                    s["added"].remove(c)
                n += 1
    return n


GOLD_ORDER_NOTE = (
    "entity / processing keep bank v5's mc.gold_position (lists unchanged). The grown implicit "
    "lists are re-dealt by mc_leakage_r4.GOLD_ORDER_RULE's salt and order (the deal starting "
    "after the 35 entity items, as in bank v5), each slot taken modulo the item's OWN option "
    "count (9; br-imp-dayoftheweek 7: only two days of the week were left)"
)


def gold_slots(items: list[dict[str, Any]]) -> dict[str, int]:
    """The grown (implicit) items' gold slots: :func:`mc_leakage_r4.gold_slots`'s salt, order and
    deal (implicit's deal starts after the entity items, as in bank v5), each slot taken modulo
    the item's OWN option count. Every other item keeps its bank v5 ``mc.gold_position``."""
    grown = [it for it in items if "common_confusers" in it["mc"]]
    subs = {str(it.get("subfamily")) for it in grown}
    if subs - {"implicit"}:
        raise SystemExit(f"gold_slots: grown lists outside implicit: {sorted(subs)}")
    out = {it["id"]: int(it["mc"]["gold_position"]) for it in items if it not in grown}
    deal = sum(1 for it in items if str(it.get("subfamily")) < "implicit")
    key = {it["id"]: hashlib.sha256(f"{r4.GOLD_ORDER_SALT}|{it['id']}".encode()).hexdigest()
           for it in grown}  # fmt: skip
    for it in sorted(grown, key=lambda it: key[it["id"]]):
        out[it["id"]] = deal % (1 + len(it["mc"]["distractors"]))
        deal += 1
    return out


def fam_of(family: str) -> r4.Fam:
    return r4.FAMS[family]


def build(family: str, out: Path) -> Path:
    fam = fam_of(family)
    old, new = BANKS[family]
    header, items = load(old)
    gate_rec = json.loads((out / "gate_r5.json").read_text(encoding="utf-8"))
    rekey = sorted(k for k, g in gate_rec.items() if g["verdict"] == "rekey")
    if rekey:  # none in the 2026-11-01 gate; a re-key needs a new gold, aliases and list
        raise SystemExit(f"re-key verdicts need hand review before a build: {rekey}")
    sp = out / family / "state.json"
    st: dict[str, dict[str, Any]] = json.loads(sp.read_text("utf-8")) if sp.exists() else {}
    work = []
    for it in items:
        if not in_scope(family, it):
            continue
        g = gate_rec[f"{family}|{it['id']}"]
        if g["verdict"] != "keep":
            continue  # re-key / drop handled below
        s = st.setdefault(it["id"], {"pool": {}, "order": [], "banned": [],
                                     "added": [], "rejected": {}, "zipf": {}})  # fmt: skip
        s["lang"] = lang_of(family, it)
        s["gold"] = str(it["mc"]["gold"])
        s["old_forms"] = r4.current_aliases(fam, it)
        work.append(it)
    for rnd in range(4):
        todo = [
            it
            for it in work
            if len(st[it["id"]]["added"]) < N_ADD and not st[it["id"]].get("exhausted")
        ]
        if not todo:
            break
        had = {it["id"]: len(st[it["id"]]["added"]) for it in todo}
        propose(fam, todo, st, out, rnd)
        m = member(fam, work, st, out)
        k = kin(fam, work, st, out)
        for it in work:
            choose(fam, it, st[it["id"]])
        b = screen(fam, work, st, out) if family == "association" else 0
        for it in todo:  # a closed topic ran dry: a fresh round added nothing
            s = st[it["id"]]
            if rnd and len(s["added"]) < N_ADD and len(s["added"]) <= had[it["id"]]:
                s["exhausted"] = True
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(st, indent=1, ensure_ascii=False) + "\n", "utf-8")
        short = sum(len(st[it["id"]]["added"]) < N_ADD for it in work)
        print(f"{family} r{rnd}: {len(todo)} items, member {m}, kin {k}, screen {b}, short {short}")
    for it in work:  # still short after the last round
        if len(st[it["id"]]["added"]) < N_ADD:
            st[it["id"]]["exhausted"] = True
    # association: a final screen of the finished lists (must ban nothing)
    if family == "association" and screen(fam, work, st, out):
        raise SystemExit("final screen banned a new option; rerun build")
    # fewer than MIN_ADD only where the topic is closed and ran dry (every day of the week, or
    # every season, is already an option: no member of the fine topic is left to add)
    short = [it["id"] for it in work if len(st[it["id"]]["added"]) < MIN_ADD]
    bad = [i for i in short if not st[i].get("exhausted")]
    if bad:
        raise SystemExit(f"fewer than {MIN_ADD} confusers with candidates left: {bad}")
    return write(family, header, items, st, gate_rec, new)


def write(family: str, header: dict[str, Any], items: list[dict[str, Any]], st: dict,
          gate_rec: dict[str, Any], new: str) -> Path:  # fmt: skip
    fam = fam_of(family)
    kept: list[dict[str, Any]] = []
    dropped: dict[str, Any] = {}
    for it in items:
        x = json.loads(json.dumps(it))
        if in_scope(family, it):
            g = gate_rec[f"{family}|{it['id']}"]
            if g["verdict"] != "keep":
                dropped[it["name"]] = {k: g[k] for k in ("correct", "answers", "verdict")}
                continue
            s = st[it["id"]]
            m = x["mc"]
            m[OLD_KEY[family]] = list(m["distractors"])
            grown = [*m["distractors"], *s["added"]]
            r4.ST[it["id"]] = {"pool": {**s["old_forms"], **s["pool"]}}
            dal = dict(m.get("distractor_aliases") or {})
            for c in s["added"]:
                dal[c] = r4.clean_aliases(fam, it, c, grown, {"pool": s["pool"]})
            m["distractors"] = grown
            m["distractor_aliases"] = dal
            m["common_confusers"] = list(s["added"])
            m["common_zipf"] = {str(m["gold"]): s["gold_zipf"],
                                **{c: s["zipf"][c] for c in s["added"]}}  # fmt: skip
            if "topic_confusers" in m:
                m["topic_confusers"] = int(m["topic_confusers"]) + len(s["added"])
            x["gate_r5"] = {k: g[k] for k in ("correct", "answers")} | {"n": GATE_N}
            if g.get("equivalent"):
                x["gate_r5"]["equivalent"] = g["equivalent"]
        x.pop("id", None)
        kept.append(x)
    bank = dict(header)
    prev = int(header.get("version") or 0)
    bank["version"] = prev + 1
    bank["supersedes"] = Path(BANKS[family][0]).name
    # texts unchanged (only options and gate records differ; options are never rendered): the
    # earlier bank's read plan, plan_sha and readouts serve this bank (readplan.READ_PLAN_BANK)
    bank["read_plan_bank"] = Path(BANKS[family][0]).name
    bank["common_confusers"] = {
        "procedure": VERSION,
        "gate_rule": GATE_RULE,
        "rule": COMMON_RULE,
        # the judge stamp to bump to if this bank is ever registered (opt-in today)
        "stamp_if_registered": STAMP[family],
        "n_items": len(kept),
        "n_changed": sum(1 for x in kept if "common_confusers" in x["mc"]),
        "dropped_by_gate": dropped,
        "zipf_window": ZIPF_WINDOW,
        # closed topics that ran dry before N_ADD (no member of the fine topic left to add)
        "short_lists": {
            x["name"]: len(x["mc"]["common_confusers"])
            for x in kept
            if len(x["mc"].get("common_confusers", [N_ADD] * N_ADD)) < N_ADD
        },
    }
    if family == "basic_readout":
        for x in kept:
            x["id"] = label_of(x["name"])
        slots = gold_slots(kept)
        counts: dict[str, dict[str, int]] = {}
        for x in kept:
            x["mc"]["gold_position"] = slots[x["id"]]
            c = counts.setdefault(str(x.get("subfamily")), {})
            c[str(slots[x["id"]] + 1)] = c.get(str(slots[x["id"]] + 1), 0) + 1
            del x["id"]
        bank["common_confusers"]["gold_order"] = {
            "rule": GOLD_ORDER_NOTE,
            "slot_counts_1based": {k: dict(sorted(v.items())) for k, v in sorted(counts.items())},
        }
        bank["counts"] = dict(collections.Counter(str(x.get("subfamily")) for x in kept))
    bank["items"] = kept
    path = REPO / new
    path.write_text(json.dumps(bank, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{family}: {len(kept)} items ({bank['common_confusers']['n_changed']} grown, "
          f"{len(dropped)} dropped) -> {path}")  # fmt: skip
    return path


# ---------------------------------------------------------------- replay


def replay(family: str, judged: Path, rejudged: Path, dest: Path) -> dict[str, Any]:
    """Fail -> pass flips of a re-judge under the new bank (``<rejudged>/<reader>/<config>/
    results.json``) against the cached bank-v2 judge runs under ``judged``, classified by
    mc_leakage_r4.replay_flips: attributable = a v2 option the cell's digest names is off the new
    list. Lists only grow from the registered bank, so every attributable flip would be one the
    registered bank already carried."""
    fam = fam_of(family)
    _h2, v2 = r4.load(fam)
    _hn, vn = load(BANKS[family][1])
    after = []
    for p in sorted(rejudged.glob("*/*/results.json")):
        for row in json.loads(p.read_text(encoding="utf-8"))["rows"]:
            after.append((f"{p.parts[-3]}/{p.parts[-2]}", row))
    flips = r4.replay_flips(
        {it["id"]: it for it in v2},
        {it["id"]: it for it in vn},
        r4.judged_cells(judged, family),
        after,
    )
    rep = {
        "family": family,
        "bank": BANKS[family][1],
        "n_rejudged": len(after),
        "n_fail_to_pass": len(flips),
        "n_attributable": sum(f["attributable"] for f in flips),
        "n_same_list": sum(f["same_list"] for f in flips),
        "flips": flips,
    }
    dest.write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print({k: v for k, v in rep.items() if k != "flips"})
    return rep


def todo(family: str, judged: Path, dest: Path) -> dict[str, list[str]]:
    """``{config: [item ids]}``: the cached bank-v2 non-pass cells of the items whose list the new
    bank changes (the re-judge set of :func:`replay`)."""
    _hn, vn = load(BANKS[family][1])
    changed = {it["id"] for it in vn if "common_confusers" in it["mc"]}
    out: dict[str, list[str]] = {}
    for cfg, row in r4.judged_cells(judged, family):
        if row["id"] in changed and str(row.get("pass")) != "True":
            out.setdefault(cfg, []).append(row["id"])
    dest.write_text(json.dumps(out, indent=1) + "\n", "utf-8")
    print(f"{sum(map(len, out.values()))} cells over {len(out)} configs -> {dest}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stage", choices=["requests", "gate", "build", "todo", "replay"])
    ap.add_argument("--family", choices=sorted(BANKS))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--samples", type=Path)
    ap.add_argument("--judged", type=Path)
    ap.add_argument("--rejudged", type=Path)
    ap.add_argument("--dest", type=Path)
    a = ap.parse_args()
    if a.stage == "requests":
        requests(a.out)
    elif a.stage == "gate":
        gate(a.out, a.samples)
    elif a.stage == "build":
        build(a.family, a.out)
    elif a.stage == "todo":
        todo(a.family, a.judged, a.dest)
    else:
        replay(a.family, a.judged, a.rejudged, a.dest)


if __name__ == "__main__":
    main()

"""Build ``evals/basic_readout_mt/items_v2.json`` (plan 0051, Camila 2026-10-30): question form,
``name_forms`` per language, regenerated distractors, blind-floor and Qwen gates.

Stages (each resumable; work files under ``--work``; Opus 5.5 calls cached in
``<work>/cells.jsonl``):

    draft    Opus rewrites each v1 completion prompt as a question in the item's own language
             (every clue kept), drafts ``name_forms`` {lang: [forms]} and 4 distractors; the
             deterministic validator (``validate_item``) re-asks up to 3 times with its errors.
    check    L2 items: Opus translates the question to English; then a blind Opus answer to the
             (English) question must name the gold (``mc.form_in`` over ``name_forms``), and a
             second call confirms the question has that one answer.
    blind    The options-only guesser (``lucky_guessing.SYSTEM``, temperature 1.0, 5 draws)
             on the readout list in the judge's own order; an item whose gold is picked in >= 2
             of 5 draws gets redrawn distractors (up to 3 rounds).
    qwen     Writes the ``scripts/qwen_sample_modal.py`` request rows (chat, no thinking,
             1 greedy + 10 at temperature 0.7).
    grade    Grades the Qwen samples by ``name_forms`` (any language): pass = greedy correct AND
             >= 8/10; failures are listed for one rewrite (``draft --only=<ids> --feedback``).
    assemble Writes the v2 bank and its gate companion ``gate_v2.json``.

    TOK=$(flock /tmp/wsb-ant.lock ant auth print-credentials --access-token)
    env -u ANTHROPIC_API_KEY -u ANTHROPIC_PROFILE ANTHROPIC_AUTH_TOKEN=$TOK \\
        .venv/bin/python scripts/build_brmt_v2.py draft --work /path/to/work
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from wsbench import mc
from wsbench.baselines import lucky_guessing as lg
from wsbench.cache import Cache
from wsbench.judge_config import ResolvedJudge
from wsbench.llm import Spend, schema_block
from wsbench.mcjudge import Call, Preflighter, run_calls
from wsbench.multitoken.options import option_sets

REPO = Path(__file__).resolve().parents[1]
V1 = REPO / "evals/basic_readout_mt/items.json"
V2 = REPO / "evals/basic_readout_mt/items_v2.json"
GATE = REPO / "evals/basic_readout_mt/gate_v2.json"
OPUS = ResolvedJudge(model="claude-opus-5-5", reasoning=None, pinned=True, source="family")
OPUS_HIGH = ResolvedJudge(
    model="claude-opus-5-5", reasoning={"anthropic_effort": "high"}, pinned=True, source="family"
)
BUILD_PV = "brmt-v2-build-2026-10-30"
LANG_NAMES = {
    "en": "English",
    "id": "Indonesian",
    "ar": "Arabic",
    "fi": "Finnish",
    "he": "Hebrew",
    "hu": "Hungarian",
    "ko": "Korean",
    "pl": "Polish",
    "ru": "Russian",
    "zh": "Chinese",
}
QMARKS = ("?", chr(0x061F), chr(0xFF1F))  # the Latin, Arabic and fullwidth question marks
SCRIPTS = {  # the question must be written in its language's own script
    "ar": re.compile(r"[؀-ۿ]"),
    "he": re.compile(r"[֐-׿]"),
    "ko": re.compile(r"[가-힯]"),
    "ru": re.compile(r"[Ѐ-ӿ]"),
}
# category / generic words: never a name form on their own, never the "distinctive" word
_CATEGORY_TEXT = """
    mount mountain mountains river rivers dynasty dynasties syndrome syndromes constant moon
    moons island islands isle isles lake sea ocean bay gulf strait cape peninsula volcano city
    town village province region state republic kingdom empire sultanate caliphate emirate
    house family clan war battle treaty act law theorem principle effect equation law disease
    disorder acid compound element church cathedral temple mosque palace castle tower bridge
    canal desert forest valley plateau plain basin delta corridor pass park street square the of
    and de la le al el von van der del da di du saint st order prize award university college
    school institute museum festival language people tribe sungai gunung pulau danau kota
    dinasti selat teluk"""
CATEGORY_WORDS = frozenset(_CATEGORY_TEXT.split())
# reviewed exemptions to the shared-name-word rule (the word is the compound class, not the name):
# soman and cyclosarin are sarin's natural same-class distractors; every sarin form keeps
# "isopropyl" / "propan-2-yl", so the name gate still separates them
SHARED_OK = {"brh-ent-chem-sarin-systematic": {"methylphosphonofluoridate"}}
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
MIN_FORM = 4
MIN_FORM_CJK = 2

DRAFT_SYSTEM = (
    "You rebuild items of a frozen interpretability benchmark bank. Each item is a short factual "
    "prompt whose answer is ONE specific name (a dynasty, a place, a person, a compound, a "
    "syndrome, ...). The old prompts were sentence COMPLETIONS; the new ones must be QUESTIONS, so "
    "that the benchmark no longer tests next-token prediction. You return JSON only."
)
DRAFT_USER = """ITEM
{item}

Write, for this item:

1. "question": the prompt rewritten as ONE direct question in {language}, natural for a native \
speaker of {language}, that asks for the name. Keep EVERY clue of the old prompt (dates, places, \
relations, descriptions); add no new clue. The question must NOT contain the answer, any form \
of it, or its distinctive name word in any language. End it with a question mark ({qmark}).

2. "display": the answer's natural English name as a reader would write it (the common name, \
not padded: "Triton", not "Triton moon"; "Bengkulu", not "Bencoolen"; keep a category word only \
when the name is normally written with it, e.g. "Aghlabid dynasty").

3. "name_forms": an object {{language code: [forms]}} with the answer's natural names in \
"en" and "zh"{src_clause}: the full name, its standard short forms (the name without its \
category word, e.g. "Triton", "Åland", "Kapuas"), common alternative or historical names and \
transliterations (e.g. "Petsamo" and "Pechenga"). For a person, the surname alone is a form \
only if no distractor below shares it. No form may be only a category word or a description \
("volcano", "the dynasty", "a moon of Neptune"). Every Latin/Cyrillic/Arabic/Hebrew form has \
at least {min_form} letters; a Chinese/Korean form at least {min_cjk} characters. KEEP every \
existing form listed in the item (old_forms).

4. "distractors": 4 OTHER real entities of exactly the same type, from the same region and era \
where possible, of comparable fame to the answer, written in the same naming style as \
"display" (if the display is "X dynasty", write "Y dynasty"). None may be an alias, a superset \
or a subset of the answer, none may share the answer's distinctive name word (no shared \
surname), and none may contain any of your name_forms. Someone who sees only the 5 names \
(answer + 4 distractors), without the question, must have NO way to tell which is the answer: \
the answer must not be the most famous, the most specific-looking, the longest or the odd one \
out.{feedback}"""
DRAFT_SCHEMA = schema_block(
    "brmt_item",
    {
        "question": {"type": "string"},
        "display": {"type": "string"},
        "name_forms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "lang": {"type": "string"},
                    "forms": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["lang", "forms"],
                "additionalProperties": False,
            },
        },
        "distractors": {"type": "array", "items": {"type": "string"}},
    },
    ["question", "display", "name_forms", "distractors"],
)
REDRAW_USER = """ITEM
{item}

{problem} Write 4 NEW distractors under the same rules: real entities of exactly the same \
type as "{display}", same region and era where possible, comparable fame, the same naming style, \
none an alias / superset / subset of the answer, none sharing its distinctive name word, none \
containing any of these forms: {forms}. Make the answer impossible to tell from the list alone \
(it must not be the most famous, most specific-looking, longest or odd one out). Avoid the \
previous distractors: {previous}. No distractor may be named, even in part, in the question: \
{question}"""
LEAK_PROBLEM = (
    "A guessing baseline that sees ONLY the option list (answer + distractors, no question) picked "
    'the answer "{display}" in {k} of 5 draws from this list: {options}. The distractors give '
    "the answer away. Such a guesser picks the most famous, most canonical or most "
    "textbook-like entity of its kind, so every distractor must be AT LEAST as famous and as "
    "canonical as the answer (the entities a quiz-writer would list as the usual alternatives), "
    "and none may be obscure."
)
MENTION_PROBLEM = (
    "The distractor(s) {names} are named in the question itself, so readouts that restate the "
    "question would name them."
)


def mentions(d: dict[str, Any], english: str) -> list[str]:
    """Distractors one of whose distinctive words (>= 4 letters) the question (or its English
    translation) holds: readouts that restate the question would name them."""
    q = mc.fold(d["question"] + " " + (english or ""))
    out = []
    for x in d["distractors"]:
        ws = [w for w in distinctive(x) if len(w) >= 4]
        if mc.form_in(q, [x]) or (ws and all(mc.form_in(q, [w]) for w in ws)):
            out.append(x)
    return out


REDRAW_SCHEMA = schema_block(
    "brmt_redraw", {"distractors": {"type": "array", "items": {"type": "string"}}}, ["distractors"]
)
TRANSLATE_SYSTEM = "You translate questions faithfully into English. Return JSON only."
TRANSLATE_USER = (
    "Translate this {language} question into English, faithfully, keeping every clue and adding "
    "none:\n\n{question}"
)
TRANSLATE_SCHEMA = schema_block("translation", {"english": {"type": "string"}}, ["english"])
ANSWER_SYSTEM = "You answer factual questions with the specific name asked for. Return JSON only."
ANSWER_USER = "{question}\n\nAnswer with the specific name only."
ANSWER_SCHEMA = schema_block("answer", {"answer": {"type": "string"}}, ["answer"])
UNIQUE_SYSTEM = "You check benchmark questions for ambiguity. Return JSON only."
UNIQUE_USER = """QUESTION: {question}
INTENDED ANSWER: {display}

Does the question determine this one answer, so that a well-informed reader would give it and \
no other equally valid answer? Answer "unique": true or false, with a one-sentence reason."""
UNIQUE_SCHEMA = schema_block(
    "unique", {"unique": {"type": "boolean"}, "reason": {"type": "string"}}, ["unique", "reason"]
)


# ---------------------------------------------------------------- helpers


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"\w+", mc.fold(s)) if not w.isdigit()]


def distinctive(name: str) -> set[str]:
    """The name's words minus category / function words (the "distinctive name word")."""
    return {w for w in _words(name) if w not in CATEGORY_WORDS and len(w) >= 3}


def all_forms(name_forms: dict[str, list[str]]) -> list[str]:
    return [f for fs in name_forms.values() for f in fs]


def _letters(s: str) -> int:
    return sum(1 for c in s if unicodedata.category(c).startswith("L"))


def v1_forms(it: dict[str, Any]) -> dict[str, list[str]]:
    """The forms v1 already credits for the answer: the readout unit's en/zh forms, plus (L2)
    the source-language target and its alternates (v1 put those only in the language unit)."""
    unit = next(u for u in it["units"] if u["role"] == "readout")
    out = {k: list(v) for k, v in unit["forms"].items()}
    if it.get("lang"):
        src = [it["target"], *it.get("target_alts", [])]
        out.setdefault(it["lang"], [])
        out[it["lang"]] += [f for f in src if f not in out[it["lang"]]]
    return out


def validate_item(it: dict[str, Any], d: dict[str, Any]) -> list[str]:
    """The deterministic v2 rules (plan 0051 §2 items 6-8); [] = valid."""
    errs: list[str] = []
    q = str(d.get("question", "")).strip()
    lang = it.get("lang") or "en"
    forms = d["name_forms"]
    every = all_forms(forms)
    if not q.endswith(QMARKS):
        errs.append("the question must end with a question mark")
    if lang in SCRIPTS and not SCRIPTS[lang].search(q):
        errs.append(f"the question must be written in {LANG_NAMES[lang]} script")
    leaked = [f for f in every if mc.form_in(q, [f])]
    if leaked:
        errs.append(f"the question contains answer forms {leaked}")
    old = v1_forms(it)
    for code, fs in old.items():
        lost = [f for f in fs if f not in forms.get(code, [])]
        if lost:
            errs.append(f"name_forms[{code!r}] dropped existing forms {lost}")
    for f in every:
        short = _letters(f) < (MIN_FORM_CJK if CJK.search(f) else MIN_FORM)
        generic = not distinctive(f) and not CJK.search(f)
        if short or generic:
            errs.append(f"form {f!r} is too short or only a category word")
    ds = [str(x).strip() for x in d.get("distractors", [])]
    if len(ds) != 4 or len({mc.fold(x) for x in ds}) != 4:
        errs.append("give exactly 4 distinct distractors")
    ok_shared = SHARED_OK.get(it["id"], set())
    for x in ds:
        if mc.form_in(x, every) or any(mc.form_in(f, [x]) for f in every):
            errs.append(f"distractor {x!r} matches an answer form")
        # a distractor holding every distinctive word of some answer form would let that form's
        # quote fit it (a shared surname, Q10); a shared class word ("salt", "unit") does not
        xw = set(_words(x))
        for f in every:
            fw = distinctive(f) - ok_shared
            if fw and fw <= xw:
                errs.append(f"distractor {x!r} holds every name word of answer form {f!r}")
                break
        if mc.fold(x) == mc.fold(str(d.get("display", ""))):
            errs.append(f"distractor {x!r} is the answer")
    if not str(d.get("display", "")).strip():
        errs.append("display is empty")
    elif not mc.form_in(str(d["display"]), every):
        errs.append("display must itself be one of the name_forms")
    return errs


def _forms_obj(raw: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in raw or []:
        code = str(e.get("lang", "")).strip().lower()
        fs = [str(f).strip() for f in e.get("forms", []) if str(f).strip()]
        if code and fs:
            out.setdefault(code, [])
            out[code] += [f for f in dict.fromkeys(fs) if f not in out[code]]
    return out


def _item_json(it: dict[str, Any]) -> str:
    unit = next(u for u in it["units"] if u["role"] == "readout")
    show = {
        "id": it["id"],
        "language": LANG_NAMES[it.get("lang") or "en"],
        "old_prompt (a completion)": it["prompt"],
        "answer": unit["forms"].get("en", [it["target"]])[0],
        "old_forms": v1_forms(it),
        "old_distractors": it["mc"]["readout"]["distractors"],
    }
    return json.dumps(show, ensure_ascii=False, indent=1)


def _run(calls: list[Call], schema: dict, cache: Cache, spend: Spend, judge: ResolvedJudge,
         temperature: float | None = None, max_tokens: int | None = None) -> dict:  # fmt: skip
    return run_calls(
        calls,
        schema=schema,
        judge=judge,
        prompt_version=BUILD_PV,
        cache=cache,
        spend=spend,
        concurrency=64,
        rpm=400,
        dry_run=False,
        preflight=Preflighter(False).for_judge(judge),
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _load(work: Path, name: str) -> dict[str, Any]:
    p = work / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save(work: Path, name: str, obj: Any) -> None:
    (work / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", "utf-8")


def v1_items() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from wsbench.banks import load_bank

    return load_bank(V1)


# ---------------------------------------------------------------- stages


def stage_draft(work: Path, only: list[str], feedback: dict[str, str]) -> None:
    _h, items = v1_items()
    drafts = _load(work, "drafts.json")
    todo = [it for it in items if (it["id"] in only if only else it["id"] not in drafts)]
    spend = Spend()
    errs_of: dict[str, list[str]] = {}
    with Cache(work / "cells.jsonl") as cache:
        for attempt in range(4):
            if not todo:
                break
            calls = []
            for it in todo:
                lang = it.get("lang") or "en"
                fb = feedback.get(it["id"], "")
                if errs_of.get(it["id"]):
                    fb += " Your previous draft broke these rules: " + "; ".join(errs_of[it["id"]])
                calls.append(
                    Call(
                        key=f"draft|{it['id']}|a{attempt}|{hashlib.sha1(fb.encode()).hexdigest()[:8]}",
                        system=DRAFT_SYSTEM,
                        user=DRAFT_USER.format(
                            item=_item_json(it),
                            language=LANG_NAMES[lang],
                            qmark="؟" if lang == "ar" else "?",
                            src_clause=f' and "{lang}" (the question\'s own language; include '
                            "the inflected forms a sentence in that language uses)"
                            if lang != "en"
                            else "",
                            min_form=MIN_FORM,
                            min_cjk=MIN_FORM_CJK,
                            feedback=("\n\nNOTE: " + fb.strip()) if fb.strip() else "",
                        ),
                        meta={"item": it["id"]},
                    )
                )
            res = _run(calls, DRAFT_SCHEMA, cache, spend, OPUS_HIGH, max_tokens=16000)
            nxt = []
            for c, it in zip(calls, todo, strict=True):
                r = res.get(c.key)
                if not isinstance(r, dict):
                    nxt.append(it)
                    errs_of[it["id"]] = ["(call failed)"]
                    continue
                d = {
                    "question": str(r["question"]).strip(),
                    "display": str(r["display"]).strip(),
                    "name_forms": _forms_obj(r["name_forms"]),
                    "distractors": [str(x).strip() for x in r["distractors"]],
                }
                # existing forms are kept by construction (the validator still checks the model)
                errs = validate_item(it, d)
                if errs:
                    errs_of[it["id"]] = errs
                    nxt.append(it)
                    drafts[it["id"]] = {**d, "errors": errs, "attempt": attempt}
                else:
                    drafts[it["id"]] = {**d, "errors": [], "attempt": attempt}
                    errs_of.pop(it["id"], None)
            todo = nxt
            _save(work, "drafts.json", drafts)
            print(f"draft attempt {attempt}: {len(todo)} still invalid; ${spend.usd:.2f}")
    bad = {i: d["errors"] for i, d in drafts.items() if d["errors"]}
    print(f"drafts: {len(drafts)}; invalid {len(bad)}")
    for i, e in bad.items():
        print(" ", i, e)


def stage_check(work: Path) -> None:
    _h, items = v1_items()
    drafts = _load(work, "drafts.json")
    checks = _load(work, "checks.json")
    spend = Spend()
    by_id = {it["id"]: it for it in items}
    with Cache(work / "cells.jsonl") as cache:
        tr_calls = [
            Call(
                key=f"translate|{i}|{hashlib.sha1(d['question'].encode()).hexdigest()[:10]}",
                system=TRANSLATE_SYSTEM,
                user=TRANSLATE_USER.format(
                    language=LANG_NAMES[by_id[i]["lang"]], question=d["question"]
                ),
                meta={"item": i},
            )
            for i, d in drafts.items()
            if by_id[i].get("lang")
        ]
        tr = _run(tr_calls, TRANSLATE_SCHEMA, cache, spend, OPUS)
        english = {i: d["question"] for i, d in drafts.items()}
        for c in tr_calls:
            r = tr.get(c.key)
            if isinstance(r, dict):
                english[c.meta["item"]] = str(r["english"])
        ans_calls = [
            Call(
                key=f"answer|{i}|{hashlib.sha1(q.encode()).hexdigest()[:10]}",
                system=ANSWER_SYSTEM,
                user=ANSWER_USER.format(question=q),
                meta={"item": i},
            )
            for i, q in english.items()
        ]
        uq_calls = [
            Call(
                key=f"unique|{i}|{hashlib.sha1(q.encode()).hexdigest()[:10]}",
                system=UNIQUE_SYSTEM,
                user=UNIQUE_USER.format(question=q, display=drafts[i]["display"]),
                meta={"item": i},
            )
            for i, q in english.items()
        ]
        ans = _run(ans_calls, ANSWER_SCHEMA, cache, spend, OPUS)
        uq = _run(uq_calls, UNIQUE_SCHEMA, cache, spend, OPUS)
    for a, u in zip(ans_calls, uq_calls, strict=True):
        i = a.meta["item"]
        ra, ru = ans.get(a.key), uq.get(u.key)
        answer = str(ra["answer"]) if isinstance(ra, dict) else None
        checks[i] = {
            "english": english[i],
            "opus_answer": answer,
            "opus_answer_ok": answer is not None
            and mc.form_in(answer, all_forms(drafts[i]["name_forms"])),
            "unique": bool(ru["unique"]) if isinstance(ru, dict) else None,
            "unique_reason": str(ru["reason"]) if isinstance(ru, dict) else None,
        }
    _save(work, "checks.json", checks)
    bad = {i: c for i, c in checks.items() if not (c["opus_answer_ok"] and c["unique"])}
    print(f"checks: {len(checks)}; flagged {len(bad)}; ${spend.usd:.2f}")
    for i, c in bad.items():
        print(" ", i, c["opus_answer"], "| unique:", c["unique"], "|", c["unique_reason"])


def candidate_items(drafts: dict[str, Any]) -> list[dict[str, Any]]:
    """v1 items with the draft's question, forms and readout options (what assemble writes)."""
    _h, items = v1_items()
    out = []
    for it in items:
        d = drafts.get(it["id"])
        if d is None:
            continue
        new = json.loads(json.dumps(it))
        new["mc"] = {"readout": {"gold": d["display"], "distractors": d["distractors"]}}
        new["name_forms"] = {"readout": d["name_forms"]}
        out.append(new)
    return out


def blind_round(work: Path, drafts: dict[str, Any], rnd: int, spend: Spend) -> dict[str, int]:
    """5 blind options-only draws per item on the readout list (judge order) -> gold picks."""
    items = candidate_items(drafts)
    opts = option_sets(items, cannot=mc.CANNOT)
    calls = []
    lists: dict[str, tuple[list[str], int]] = {}
    for it in items:
        o, g = opts[it["id"]]["readout"]
        content = o[:-1]
        lists[it["id"]] = (content, g)
        sha = hashlib.sha1("|".join(content).encode()).hexdigest()[:10]
        item = lg.Item(it["id"], [content], [g + 1])
        for d in range(lg.DEFAULT_DRAWS):
            calls.append(
                Call(
                    key=f"blind|{it['id']}|{sha}|d{d}",
                    system=lg.SYSTEM,
                    user=lg.user_message(item, "blind", "basic_readout_mt", None),
                    meta={"item": it["id"], "draw": d},
                )
            )
    with Cache(work / "cells.jsonl") as cache:
        res = _run(calls, lg.schema(1), cache, spend, OPUS, temperature=lg.TEMPERATURE,
                   max_tokens=lg.MAX_TOKENS)  # fmt: skip
    hits: Counter[str] = Counter()
    n: Counter[str] = Counter()
    for c in calls:
        r = res.get(c.key)
        if not isinstance(r, dict):
            continue
        n[c.meta["item"]] += 1
        hits[c.meta["item"]] += int(r.get("choice1") == lists[c.meta["item"]][1] + 1)
    total = sum(n.values())
    print(f"blind round {rnd}: per-draw gold rate {sum(hits.values()) / max(total, 1):.3f} "
          f"over {total} draws; leakers (>=2/5): {sum(1 for i in n if hits[i] >= 2)}")  # fmt: skip
    return {i: hits[i] for i in n}


def stage_blind(work: Path, rounds: int = 3) -> None:
    drafts = _load(work, "drafts.json")
    checks = _load(work, "checks.json")
    blind = _load(work, "blind.json") or {"rounds": []}
    spend = Spend()
    _h, items = v1_items()
    by_id = {it["id"]: it for it in items}
    english = {i: (checks.get(i) or {}).get("english") or "" for i in drafts}
    for rnd in range(len(blind["rounds"]), rounds + 1):
        hits = blind_round(work, drafts, rnd, spend)
        named = {i: mentions(drafts[i], english[i]) for i in drafts}
        named = {i: v for i, v in named.items() if v}
        blind["rounds"].append(
            {
                "hits": hits,
                "named_in_question": named,
                "distractors": {i: drafts[i]["distractors"] for i in hits},
            }
        )
        _save(work, "blind.json", blind)
        leakers = sorted({i for i, k in hits.items() if k >= 2} | set(named))
        print(f"  round {rnd}: redraw {len(leakers)} ({len(named)} named in the question)")
        if not leakers or rnd == rounds:
            break
        calls = []
        for i in leakers:
            d = drafts[i]
            prev = sorted({x for r in blind["rounds"] for x in r["distractors"].get(i, [])})
            problem = " ".join(
                p
                for p in (
                    LEAK_PROBLEM.format(
                        display=d["display"],
                        k=hits.get(i, 0),
                        options=[d["display"], *d["distractors"]],
                    )
                    if hits.get(i, 0) >= 2
                    else "",
                    MENTION_PROBLEM.format(names=named[i]) if i in named else "",
                )
                if p
            )
            calls.append(
                Call(
                    key=f"redraw|{i}|r{rnd}",
                    system=DRAFT_SYSTEM,
                    user=REDRAW_USER.format(
                        item=_item_json(by_id[i]),
                        problem=problem,
                        display=d["display"],
                        forms=all_forms(d["name_forms"]),
                        previous=prev,
                        question=d["question"],
                    ),
                    meta={"item": i},
                )
            )
        with Cache(work / "cells.jsonl") as cache:
            res = _run(calls, REDRAW_SCHEMA, cache, spend, OPUS_HIGH, max_tokens=16000)
        for c in calls:
            i = c.meta["item"]
            r = res.get(c.key)
            if not isinstance(r, dict):
                continue
            new = {**drafts[i], "distractors": [str(x).strip() for x in r["distractors"]]}
            errs = validate_item(by_id[i], new) + [
                f"distractor {x!r} is named in the question" for x in mentions(new, english[i])
            ]
            if not errs:
                drafts[i] = {**new, "errors": []}
            else:
                print(f"  redraw {i} invalid, kept old: {errs}")
        _save(work, "drafts.json", drafts)
    print(f"blind: {len(blind['rounds'])} rounds; ${spend.usd:.2f}")


QWEN_GATE = {"n": 10, "temperature": 0.7, "top_p": 0.8, "top_k": 20, "max_tokens": 300}


def stage_qwen(work: Path, tag: str, only: list[str], max_tokens: int) -> None:
    drafts = _load(work, "drafts.json")
    rows = []
    for i, d in sorted(drafts.items()):
        if only and i not in only:
            continue
        rows.append(
            {
                "key": f"{i}|{hashlib.sha1(d['question'].encode()).hexdigest()[:10]}",
                "family": "basic_readout_mt",
                "text": d["question"],
                "enable_thinking": False,
                "greedy": True,
                **{**QWEN_GATE, "max_tokens": max_tokens or QWEN_GATE["max_tokens"]},
            }
        )
    out = work / f"qwen_requests_{tag}.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    print(f"wrote {out} ({len(rows)} rows)")


def stage_grade(work: Path, samples: list[Path]) -> None:
    drafts = _load(work, "drafts.json")
    got: dict[str, dict[str, Any]] = {}
    for p in samples:  # a later file's rows replace an earlier file's rows for the same key
        fresh: set[str] = set()
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r["key"] not in fresh:
                    fresh.add(r["key"])
                    got[r["key"]] = {"greedy": None, "draws": [], "file": p.name}
                g = got[r["key"]]
                if r.get("greedy"):
                    g["greedy"] = r["text"]
                else:
                    g["draws"].append(r["text"])
    gate = _load(work, "qwen_gate.json")
    for i, d in sorted(drafts.items()):
        key = f"{i}|{hashlib.sha1(d['question'].encode()).hexdigest()[:10]}"
        if key not in got:
            continue
        forms = all_forms(d["name_forms"])
        g = got[key]
        ok = [mc.form_in(t, forms) for t in g["draws"]]
        greedy_ok = g["greedy"] is not None and mc.form_in(g["greedy"], forms)
        gate[i] = {
            "question": d["question"],
            "greedy": g["greedy"],
            "greedy_ok": greedy_ok,
            "n_ok": sum(ok),
            "n": len(ok),
            "pass": greedy_ok and sum(ok) >= 8 and len(ok) == 10,
            "fails": [t for t, k in zip(g["draws"], ok, strict=True) if not k][:3],
            "samples_file": g["file"],
        }
    _save(work, "qwen_gate.json", gate)
    n_pass = sum(1 for g in gate.values() if g["pass"])
    print(f"qwen gate: {n_pass}/{len(gate)} pass")
    for i, g in sorted(gate.items()):
        if not g["pass"]:
            print(f"  FAIL {i}: greedy_ok={g['greedy_ok']} {g['n_ok']}/{g['n']} | "
                  f"{(g['greedy'] or '')[:160]!r}")  # fmt: skip


def stage_assemble(work: Path, provisional: bool = False) -> None:
    v1_header, items = v1_items()
    drafts = _load(work, "drafts.json")
    checks = _load(work, "checks.json")
    blind = _load(work, "blind.json")
    gate = _load(work, "qwen_gate.json")
    hist = _load(work, "history.json")  # rewrites: id -> [{question, reason}]
    kept, dropped = [], {}
    for it in items:
        i = it["id"]
        d, g = drafts.get(i), gate.get(i)
        if d is None or d["errors"]:
            dropped[i] = "no valid draft"
            continue
        if provisional and g is None:  # development only: never frozen
            g = {"pass": True, "greedy_ok": None, "n_ok": None, "n": None}
        if g is None or not g["pass"]:
            dropped[i] = "Qwen gate (greedy correct AND >= 8/10)" if g else "not gated"
            continue
        new = {k: v for k, v in it.items() if k not in ("prompt", "eval_render", "readout", "mc")}
        new = {
            "name": it["name"],
            **{k: v for k, v in new.items() if k != "name"},
            "prompt": d["question"],
            "prompt_v1": it["prompt"],
            "eval_render": "chat",
            "readout": {"kind": "all_from_end", "lite": "final_token"},
            "name_forms": {"readout": d["name_forms"]},
            "mc": {"readout": {"gold": d["display"], "distractors": d["distractors"]}},
            "gate_v2": {"qwen_greedy_ok": g["greedy_ok"], "qwen_n_ok": g["n_ok"], "qwen_n": g["n"]},
        }
        new.pop("id", None)
        kept.append(new)
    v1_sha = hashlib.sha256(V1.read_bytes()).hexdigest()
    header = {
        "family": v1_header["family"],
        "parent_family": v1_header.get("parent_family"),
        "version": 2,
        "parent": {"file": "items.json", "sha256": v1_sha},
        "contract": {**v1_header["contract"], "native_langs": ["en", "zh"]},
        "gate": (
            "Qwen3.6-27B, the v2 QUESTION in the chat template (enable_thinking=False, no system "
            "prompt, no answer stem): greedy answer correct AND >= 8/10 correct at temperature "
            f"{QWEN_GATE['temperature']} (top_p {QWEN_GATE['top_p']}, top_k {QWEN_GATE['top_k']}),"
            " graded by name_forms (any language, mc.form_in). Questions written by Opus 5.5 from "
            "the v1 completions (every clue kept), back-translated and answer-checked; distractors "
            "regenerated under the blind options-only floor gate (gold picked in >= 2/5 blind "
            "draws -> redrawn, up to 3 rounds). EVAL RENDER: chat, every position "
            "(all_from_end); lite = the final render token. Judged by the MC judge (plan 0037)."
        ),
        "frozen": dt.date.today().isoformat(),
    }
    V2.write_text(
        json.dumps({**header, "items": kept}, ensure_ascii=False, indent=1) + "\n", "utf-8"
    )
    last = (blind.get("rounds") or [{}])[-1].get("hits", {})
    companion = {
        "bank": "items_v2.json",
        "n_v1": len(items),
        "n_v2": len(kept),
        "dropped": dropped,
        "qwen_gate": {**QWEN_GATE, "greedy": True, "bar": "greedy correct AND >= 8/10"},
        "rewrites": hist,
        "blind_floor": {
            "rounds": [
                {
                    "per_draw_gold_rate": sum(r["hits"].values()) / (5 * max(len(r["hits"]), 1)),
                    "n_leakers": sum(1 for k in r["hits"].values() if k >= 2),
                }
                for r in blind.get("rounds", [])
            ],
            "remaining_leakers": sorted(i for i, k in last.items() if k >= 2 and i not in dropped),
        },
        "items": {
            i: {
                "opus_check": checks.get(i),
                "qwen": {k: v for k, v in (gate.get(i) or {}).items() if k != "question"},
                "blind_hits_last_round": last.get(i),
            }
            for i in sorted(drafts)
        },
    }
    GATE.write_text(json.dumps(companion, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"wrote {V2} ({len(kept)} items; dropped {len(dropped)}) and {GATE}")


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["draft", "check", "blind", "qwen", "grade", "assemble"])
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument(
        "--only", default="", help="comma list of ids (draft: redo these; 'revalidate')"
    )
    ap.add_argument("--feedback", type=Path, help="draft: json {id: note} for the rewrite")
    ap.add_argument("--tag", default="r0")
    ap.add_argument("--max-tokens", type=int, default=0, help="qwen: override max_tokens")
    ap.add_argument("--rounds", type=int, default=3, help="blind: the last redraw round")
    ap.add_argument("--provisional", action="store_true", help="assemble: keep ungated items")
    ap.add_argument("--samples", type=Path, nargs="*", default=[])
    a = ap.parse_args(argv)
    if a.stage == "draft" and a.only == "revalidate":
        _h, items = v1_items()
        drafts = _load(a.work, "drafts.json")
        for it in items:
            if it["id"] in drafts:
                drafts[it["id"]]["errors"] = validate_item(it, drafts[it["id"]])
        _save(a.work, "drafts.json", drafts)
        print({i: d["errors"] for i, d in drafts.items() if d["errors"]})
        return
    a.work.mkdir(parents=True, exist_ok=True)
    only = [x for x in a.only.split(",") if x]
    if a.stage == "draft":
        fb = json.loads(a.feedback.read_text()) if a.feedback else {}
        stage_draft(a.work, only, fb)
    elif a.stage == "check":
        stage_check(a.work)
    elif a.stage == "blind":
        stage_blind(a.work, rounds=a.rounds)
    elif a.stage == "qwen":
        stage_qwen(a.work, a.tag, only, a.max_tokens)
    elif a.stage == "grade":
        stage_grade(a.work, a.samples)
    else:
        stage_assemble(a.work, provisional=a.provisional)


if __name__ == "__main__":
    main(sys.argv[1:])

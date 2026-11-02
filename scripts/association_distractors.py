"""Author, lint and screen the association v2 multiple-choice options (plan 0039 §C3).

The bank v2 option list of every kept item is its gold + 7 distractors (+ "cannot tell", added
by the judge). Stages, each resumable (results are cached per key in ``<out>/*.jsonl``):

1. ``propose``: Opus 5.5 gets the gold concept, its scene language and the other bank golds,
   NEVER the scene or any readout, and returns the gold's type (``category``), its accepted
   alternate forms (``aliases``: inflections, spelling variants, synonyms, translations into
   English, Chinese and the scene language) and 12 ranked distractor candidates (same type
   first, other bank golds of that type first).
2. ``lint`` (mechanical, no call): rule (ii) no distractor names the gold (``mc.form_in`` both
   ways against gold + aliases, word containment) and no two distractors name each other; rule
   (iv) an acronym for an acronym and at most two words longer (capitalisation is not linted:
   same-type siblings of a common-noun gold are often proper names, e.g. holidays for
   "birthday"; the measured lucky-guessing baseline checks for a form leak). The first 7
   passing candidates are the options.
   An Opus 5.5 entailment check (one call per item and proposal round, gold + candidates
   only) removes candidates a word lint cannot see: hyponyms ("toddler" for "child"),
   hypernyms, near-equivalents.
3. ``screen``: Opus 5.5 sees the scene and the 8 options (a fresh seeded order per draw), picks
   one, ``--draws`` (5) draws. The gold must win every draw. A distractor that wins once is
   replaced by the next lint-passing candidate and the item is re-screened (up to ``--rounds``);
   when candidates run out the proposer is asked again with the rejected ones excluded. An item
   whose gold still loses is DROPPED (recorded with its picks).
4. ``freeze``: writes ``evals/association/items_v2.json`` (93 - drops items) with the header
   fields ``retired``, ``retired_rule``, ``distractor_rule``, ``distractor_review``.

API: the Anthropic route of ``wsbench.llm`` (keyless OAuth: ``ANTHROPIC_AUTH_TOKEN``; never an
exported ``ANTHROPIC_API_KEY``)::

    python scripts/association_distractors.py propose --out <dir>
    python scripts/association_distractors.py screen --out <dir>
    python scripts/association_distractors.py freeze --out <dir>
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from wsbench import llm, mc
from wsbench.llm import schema_block

REPO = Path(__file__).resolve().parents[1]
V1 = REPO / "evals" / "association" / "items.json"
V2 = REPO / "evals" / "association" / "items_v2.json"
MODEL = "claude-opus-5-5"
REASONING = {"anthropic_effort": "default"}
N_DISTRACTORS = 7
N_CANDIDATES = 12
SCREEN_SEED = "assoc-screen-v1"

# C1 (plan 0039): the under-determined items, retired with the rule that retires each
RETIRED_RULE = {
    "a": "every frontier panel model (opus, astra, argon) failed at least 2 of its 3 panel-v1 "
    "draws: the text does not lead a strong reader to the gold",
    "b": "the gold is a broader term (hypernym) of the specific concept the scene evokes",
    "c": "the scene fits a different, equally specific concept as well as the gold",
}
RETIRED = {
    "nasa": "a: panel-v1 draw_pass opus 0/3, astra 0/3, argon 0/3 (qwen 0/3); any rocket launch",
    "cia": "a: panel-v1 draw_pass opus 0/3, astra 0/3, argon 0/3; FBI fits as well",
    "history-h": "a: panel-v1 draw_pass opus 0/3, astra 0/3, argon 0/3; passes on generic "
    "'historical records'",
    "love-h": "a: panel-v1 draw_pass opus 0/3, astra 1/3, argon 1/3; intimacy / trust read as well",
    "death-h": "a: panel-v1 draw_pass opus 1/3, astra 1/3, argon 1/3; funeral / mourning (grief "
    "is another item's gold)",
    "game-h": "b: gold 'game' is the hypernym of the chess move the scene shows (duplicates "
    "chess / bf-chess)",
    "de-konig": "c: König vs Kaiser / Fürst / Thronfolger fit equally (astra 0/3, qwen 0/3)",
}
# the gold option of record when it differs from the v1 intermediates (C1: the generic
# "detective" target of bf-sherlock let "The detective" pass)
GOLD_OVERRIDE = {"bf-sherlock": "Sherlock Holmes"}
SCENE_LANG = {
    "pt-carnaval": "Portuguese",
    "de-oktoberfest": "German",
    "es-siesta": "Spanish",
    "it-mercato": "Italian",
}

DISTRACTOR_RULE = (
    "7 distractors per item (uniform chance 1/8 before cannot tell). (i) the same TYPE as the "
    "gold first (at least 4 same-type siblings where they exist; other bank golds of that type "
    "first), the rest from the nearest neighbouring type; (ii) no synonym, alias, translation, "
    "spelling variant, hypernym or hyponym of the gold (lint: no mc.form_in match either way "
    "against gold + aliases, plus an Opus entailment check for hyponyms / hypernyms / "
    "near-equivalents); (iii) no distractor is a defensible answer for the scene (scene "
    "screen: Opus 5.5 sees scene + 8 options, 5 draws, the gold must win 5/5, a distractor that "
    "wins once is replaced); (iv) the same surface class as the gold (an acronym for an "
    "acronym), at most two words longer; the measured lucky-guessing baseline checks the rest "
    "of (iv). Proposed by Opus 5.5 from the gold alone (never the scene or a readout), so the "
    "options are lens-neutral."
)

PROPOSE_SYSTEM = """You write multiple-choice options for a benchmark. Each question's correct \
answer is one CONCEPT (an activity, event, place, person, organisation, feeling or thing). You \
never see the question; you see only the correct concept. Return JSON with:
- "category": the concept's specific TYPE in a few words (e.g. "holiday / celebration", \
"racket sport", "fictional detective", "season or time of day").
- "aliases": every accepted alternate FORM of the concept that a reader may write instead of it: \
inflections and plurals, spelling variants (British / American), established synonyms and \
aliases and short names, and faithful translations into English, Simplified Chinese (list the \
Chinese forms explicitly, e.g. 冬天 and 冬季 for winter) and, when given, the scene language. \
Never a broader category, a narrower instance, a related idea or a description.
- "candidates": 12 WRONG answers, best first, each a different concept of the SAME type as the \
correct one where enough exist (at least 4 same-type siblings, e.g. other holidays for \
"birthday", other racket sports for "tennis"), the rest from the nearest neighbouring type. \
Prefer concepts from the list of other benchmark answers when they are of the same type. Each \
candidate must have the SAME surface form as the correct answer: a person's name for a \
person's name, a place name for a place name, an acronym for an acronym, the same language as \
the correct answer when it is not English, and about the same length. A candidate must NOT be a \
synonym, alias, translation, spelling variant, broader category or narrower instance of the \
correct answer, must not contain the correct answer as a word or be contained in it (no "table \
tennis" for "tennis"), and no two candidates may be the same concept."""

PROPOSE_USER = """Correct concept: {gold}
{lang}Other benchmark answers (prefer same-type ones as candidates): {others}
{exclude}Return the JSON."""

PROPOSE_SCHEMA = schema_block(
    "assoc_options",
    {
        "category": {"type": "string"},
        "aliases": {"type": "array", "items": {"type": "string"}},
        "candidates": {"type": "array", "items": {"type": "string"}},
    },
    ["category", "aliases", "candidates"],
)

ENTAIL_SYSTEM = """You check multiple-choice options. You get a CORRECT concept and a list of \
candidate WRONG options. Flag every candidate that a careful grader could count as naming the \
correct concept or that the correct concept would count as naming: a synonym, alias, \
translation or spelling variant of it; a broader category that contains it (a hypernym); a \
narrower instance or kind of it (a hyponym, e.g. "toddler" for "child", "puppy" for "dog"); a \
part, stage or a near-equivalent of it; or the same thing under another name. Do NOT flag a \
candidate that is merely of the same type (another holiday for "birthday", another sport for \
"tennis"). Return JSON {"flagged": [the flagged candidates, copied exactly]}."""
ENTAIL_USER = "CORRECT concept: {gold}\nCandidates:\n{listing}"
ENTAIL_SCHEMA = schema_block(
    "entail_check", {"flagged": {"type": "array", "items": {"type": "string"}}}, ["flagged"]
)

SCREEN_SYSTEM = """You read a short passage that evokes one concept without naming it. Pick the \
listed concept the passage evokes. Answer with the option number."""
SCREEN_USER = "PASSAGE:\n{scene}\n\nWhich concept does the passage evoke?\n{listing}"
SCREEN_SCHEMA = schema_block("scene_pick", {"choice": {"type": "integer"}}, ["choice"])


# ---------------------------------------------------------------- io


def read_jsonl(p: Path) -> dict[str, Any]:
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["key"]] = r
    return out


def append_jsonl(p: Path, rows: list[dict[str, Any]]) -> None:
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def v1_items() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = json.loads(V1.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if k != "items"}, raw["items"]


def kept_items() -> list[dict[str, Any]]:
    return [it for it in v1_items()[1] if it["name"] not in RETIRED]


def gold_of(it: dict[str, Any]) -> str:
    return GOLD_OVERRIDE.get(it["name"], it["intermediates"][0])


def call(prompts: list[tuple[str, str]], schema: dict[str, Any]) -> list[dict[str, Any] | None]:
    out: list[dict[str, Any] | None] = [None] * len(prompts)

    def put(i: int, r: dict[str, Any] | None) -> None:
        out[i] = r

    llm.stream_json(
        prompts,
        schema=schema,
        model=MODEL,
        reasoning=REASONING,
        on_result=put,
        concurrency=48,
        rpm=600,
        timeout=600,
    )
    return out


# ---------------------------------------------------------------- lint


def surface_class(s: str) -> str:
    s = s.strip()
    letters = [c for c in s if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and " " not in s and len(letters) >= 2:
        return "acronym"
    return "word"


def lint_problem(d: str, gold: str, aliases: list[str], kept: list[str]) -> str:
    """Why candidate ``d`` breaks rule (ii) / (iv) against the gold and the options kept so far
    ('' = it passes)."""
    d = d.strip()
    if not d:
        return "empty"
    forms = [gold, *aliases]
    if mc.fold(d) in {mc.fold(f) for f in forms}:
        return "is a gold form"
    if mc.form_in(d, forms) or any(mc.form_in(f, [d]) for f in forms):
        return "names / is named by a gold form"
    if mc.is_cannot(d):
        return "cannot-tell text"
    for k in kept:
        if mc.fold(k) == mc.fold(d) or mc.form_in(d, [k]) or mc.form_in(k, [d]):
            return f"overlaps option {k!r}"
    if surface_class(d) != surface_class(gold):
        return f"surface class {surface_class(d)} != {surface_class(gold)}"
    if len(d.split()) > len(gold.split()) + 2:
        return "too long"
    return ""


def lint_pick(
    gold: str, aliases: list[str], cands: list[str], banned: set[str], fixed: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    """``fixed`` options first (already screened), then the first passing candidates up to 7."""
    kept = list(fixed)
    rejected = []
    for c in cands:
        if len(kept) >= N_DISTRACTORS:
            break
        if c in kept:
            continue
        if mc.fold(c) in banned:
            rejected.append({"candidate": c, "why": "lost the scene screen"})
            continue
        why = lint_problem(c, gold, aliases, kept)
        if why:
            rejected.append({"candidate": c, "why": why})
        else:
            kept.append(c.strip())
    return kept, rejected


# ---------------------------------------------------------------- stages


def propose(
    out: Path, items: list[dict[str, Any]], exclude: dict[str, list[str]], tag: str
) -> None:
    cache_p = out / "propose.jsonl"
    cache = read_jsonl(cache_p)
    golds = sorted({gold_of(it) for it in kept_items()})
    todo, prompts = [], []
    for it in items:
        key = f"{it['name']}|{tag}"
        if key in cache and cache[key].get("result"):
            continue
        g = gold_of(it)
        lang = (
            f"Scene language: {SCENE_LANG[it['name']]} (the correct answer is in that language)\n"
            if it["name"] in SCENE_LANG
            else ""
        )
        ex = exclude.get(it["name"]) or []
        exl = f"Do NOT propose any of these again: {', '.join(ex)}\n" if ex else ""
        others = ", ".join(x for x in golds if x != g)
        user = (
            PROPOSE_USER.replace("{gold}", g)
            .replace("{lang}", lang)
            .replace("{others}", others)
            .replace("{exclude}", exl)
        )
        todo.append(key)
        prompts.append((PROPOSE_SYSTEM, user))
    print(f"propose[{tag}]: {len(prompts)} calls ({len(items) - len(prompts)} cached)")
    if prompts:
        res = call(prompts, PROPOSE_SCHEMA)
        append_jsonl(cache_p, [{"key": k, "result": r} for k, r in zip(todo, res, strict=True)])


def proposals(out: Path) -> dict[str, list[dict[str, Any]]]:
    """item id -> its proposal results in tag order."""
    by: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for key, r in read_jsonl(out / "propose.jsonl").items():
        iid, tag = key.split("|", 1)
        if r.get("result"):
            by.setdefault(iid, []).append((tag, r["result"]))
    return {k: [r for _t, r in sorted(v)] for k, v in by.items()}


def entail_flags(out: Path, items: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    """item id -> the folded candidates Opus flags as naming / named by the gold (rule ii, the
    part a word lint cannot see: hyponyms, hypernyms, near-equivalents). One call per (item,
    proposal round), cached in ``entail.jsonl``."""
    cache_p = out / "entail.jsonl"
    cache = read_jsonl(cache_p)
    raw = read_jsonl(out / "propose.jsonl")
    keys, prompts = [], []
    for key, r in raw.items():
        iid = key.split("|", 1)[0]
        if iid not in items or not r.get("result") or key in cache:
            continue
        gold = gold_of(items[iid])
        user = ENTAIL_USER.replace("{gold}", gold).replace(
            "{listing}", "\n".join(f"- {c}" for c in r["result"]["candidates"])
        )
        keys.append(key)
        prompts.append((ENTAIL_SYSTEM, user))
    if prompts:
        print(f"entail: {len(prompts)} calls")
        res = call(prompts, ENTAIL_SCHEMA)
        append_jsonl(cache_p, [{"key": k, "result": r} for k, r in zip(keys, res, strict=True)])
        cache = read_jsonl(cache_p)
    out_: dict[str, set[str]] = {}
    for key, r in cache.items():
        iid = key.split("|", 1)[0]
        res_ = r.get("result") or {}
        out_.setdefault(iid, set()).update(mc.fold(x) for x in res_.get("flagged") or [])
    return out_


def read_overrides(out: Path) -> dict[str, dict[str, Any]]:
    """The reviewer's edits (``<out>/review_overrides.json``): per item ``replace`` {old
    distractor: new candidate} (the item is re-linted and re-screened), ``drop_aliases`` and
    ``add_aliases``, and a ``why`` string recorded in the bank header."""
    p = out / "review_overrides.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def review_aliases(aliases: list[str], ov: dict[str, Any]) -> list[str]:
    drop = {mc.fold(a) for a in ov.get("drop_aliases", [])}
    kept = [a for a in aliases if mc.fold(a) not in drop]
    return sorted(set(kept) | set(ov.get("add_aliases", [])))


def options_of(gold: str, distractors: list[str], draw: str) -> tuple[list[str], int]:
    shown = mc.seeded_shuffle([gold, *distractors], f"{SCREEN_SEED}:{draw}")
    return shown, shown.index(gold) + 1


def screen(out: Path, draws: int, rounds: int, limit: int = 0) -> None:
    ks = kept_items()
    items = {it["name"]: it for it in (ks[:limit] if limit else ks)}
    state_p = out / "state.json"
    state: dict[str, Any] = (
        json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
    )
    picks_p = out / "screen.jsonl"
    for rnd in range(rounds + 1):
        props = proposals(out)
        missing = [it for iid, it in items.items() if iid not in props]
        if missing:
            propose(out, missing, {}, "r0")
            props = proposals(out)
        flags = entail_flags(out, items)
        overrides = read_overrides(out)
        todo: list[str] = []
        for iid in items:
            st = state.setdefault(iid, {"status": "pending", "banned": [], "screened_ok": []})
            replaced = set((overrides.get(iid) or {}).get("replace", {}))
            if st["status"] == "ok" and replaced & set(st.get("distractors", [])):
                # a reviewer replaced a screened distractor: re-lint and re-screen the item
                st["status"] = "pending"
                st["screened_ok"] = [d for d in st["distractors"] if d not in replaced]
                st.setdefault("review_rescreened", True)
            if st["status"] == "ok":
                st["aliases"] = review_aliases(st["aliases"], overrides.get(iid, {}))
            if st["status"] in ("ok", "dropped"):
                continue
            p = props.get(iid) or []
            if not p:
                st["status"] = "dropped"
                st["why"] = "no proposal"
                continue
            ov = overrides.get(iid, {})
            aliases = review_aliases(
                sorted({a.strip() for r in p for a in r["aliases"] if a.strip()}), ov
            )
            replace = ov.get("replace", {})
            cands = list(replace.values()) + [c for r in p for c in r["candidates"]]
            gold = gold_of(items[iid])
            st["banned"] = sorted(set(st["banned"]) | set(replace))
            banned = {mc.fold(b) for b in st["banned"]}
            entailed = flags.get(iid, set())
            st["entail_flagged"] = sorted({c for c in cands if mc.fold(c) in entailed})
            cands = [c for c in cands if mc.fold(c) not in entailed]
            fixed = [d for d in st["screened_ok"] if mc.fold(d) not in banned | entailed]
            dis, rejected = lint_pick(gold, aliases, cands, banned, fixed)
            st.update(
                category=p[0]["category"],
                aliases=aliases,
                distractors=dis,
                lint_rejected=rejected,
            )
            if len(dis) < N_DISTRACTORS:
                st["status"] = "need_more"
            else:
                st["status"] = "pending"
                todo.append(iid)
        need = [iid for iid in items if state[iid]["status"] == "need_more"]
        if need:
            if rnd == rounds:
                for iid in need:
                    state[iid]["status"] = "dropped"
                    state[iid]["why"] = "fewer than 7 lint-passing distractors"
            else:
                propose(
                    out,
                    [items[i] for i in need],
                    {i: state[i]["banned"] + state[i].get("entail_flagged", [])
                     + [c["candidate"] for c in state[i]["lint_rejected"]]
                     for i in need},
                    f"r{rnd + 1}",
                )  # fmt: skip
                state_p.write_text(json.dumps(state, indent=1, ensure_ascii=False))
                continue
        if not todo:
            break
        cache = read_jsonl(picks_p)
        keys, prompts, metas = [], [], []
        for iid in todo:
            st = state[iid]
            gold = gold_of(items[iid])
            for d in range(draws):
                shown, gpos = options_of(gold, st["distractors"], f"{iid}:{d}")
                key = json.dumps([iid, d, shown], ensure_ascii=False)
                metas.append((iid, d, shown, gpos, key))
                if key in cache:
                    continue
                user = SCREEN_USER.replace("{scene}", items[iid]["prompt"]).replace(
                    "{listing}", mc.listing(shown)
                )
                keys.append(key)
                prompts.append((SCREEN_SYSTEM, user))
        print(f"screen round {rnd}: {len(todo)} items, {len(prompts)} calls")
        if prompts:
            res = call(prompts, SCREEN_SCHEMA)
            append_jsonl(picks_p, [{"key": k, "result": r} for k, r in zip(keys, res, strict=True)])
            cache = read_jsonl(picks_p)
        for iid in todo:
            st = state[iid]
            wins: list[str] = []
            n_fail = 0
            for m_iid, _d, shown, gpos, key in metas:
                if m_iid != iid:
                    continue
                r = (cache.get(key) or {}).get("result")
                ch = r.get("choice") if isinstance(r, dict) else None
                if not isinstance(ch, int) or not 1 <= ch <= len(shown):
                    n_fail += 1
                    continue
                if ch != gpos:
                    wins.append(shown[ch - 1])
            st.setdefault("history", []).append(
                {"round": rnd, "distractors": st["distractors"], "wins": wins, "n_fail": n_fail}
            )
            if n_fail:
                st["status"] = "pending"  # re-asked next round
            elif not wins:
                st["status"] = "ok"
            else:
                st["banned"] = sorted(set(st["banned"]) | set(wins))
                st["screened_ok"] = [d for d in st["distractors"] if d not in wins]
                if rnd == rounds:
                    st["status"] = "dropped"
                    st["why"] = f"a distractor still won the scene screen after {rounds} rounds"
        state_p.write_text(json.dumps(state, indent=1, ensure_ascii=False))
    state_p.write_text(json.dumps(state, indent=1, ensure_ascii=False))
    n = {s: sum(1 for v in state.values() if v["status"] == s) for s in ("ok", "dropped")}
    print(f"screen: {n} of {len(items)}")


def freeze(out: Path, review: str, *, write: bool = True) -> dict[str, Any]:
    header, items = v1_items()
    state = json.loads((out / "state.json").read_text(encoding="utf-8"))
    overrides = read_overrides(out)
    kept, dropped = [], {}
    for it in items:
        iid = it["name"]
        if iid in RETIRED:
            continue
        st = state.get(iid) or {}
        if st.get("status") != "ok":
            dropped[iid] = st.get("why", "not screened")
            continue
        ov = overrides.get(iid, {})
        aliases = review_aliases(st["aliases"], ov)
        gold = gold_of(it)
        new = dict(it)
        new["intermediates"] = [gold]
        new["mc"] = {
            "gold": gold,
            "aliases": [a for a in aliases if mc.fold(a) != mc.fold(gold)],
            "category": st["category"],
            "distractors": list(st["distractors"]),
        }
        new["eval_render"] = "chat_summarize"
        new.pop("readout", None)
        kept.append(new)
    hdr = {k: v for k, v in header.items() if k not in ("items", "eval_render_note")}
    hdr.update(
        {
            "version": 2,
            "items": len(kept),
            "render": "chat_summarize",
            "render_note": "Qwen chat template (enable_thinking=False); the user turn is the "
            "scene + '\\n\\nSummarize the preceding story in one sentence.'; the 19 suffix + "
            "chat-tail positions are read (readplan.py)",
            "retired_rule": RETIRED_RULE,
            "retired": RETIRED,
            "dropped_by_screen": dropped,
            "distractor_rule": DISTRACTOR_RULE,
            "distractor_review": review,
            "distractor_review_edits": overrides,
            "contract": {"native_langs": ["en", "zh"]},
        }
    )
    raw = {**hdr, "items": kept}
    if write:
        V2.write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"froze {len(kept)} items -> {V2} (dropped {sorted(dropped)})")
    return raw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stage", choices=("propose", "screen", "freeze"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--draws", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--review", default="")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.stage == "propose":
        items = kept_items()
        propose(out, items[: a.limit] if a.limit else items, {}, "r0")
    elif a.stage == "screen":
        screen(out, a.draws, a.rounds, a.limit)
    else:
        if not a.review:
            print("freeze needs --review '<who reviewed the option lists, and what changed>'")
            return 2
        freeze(out, a.review)
    return 0


if __name__ == "__main__":
    sys.exit(main())

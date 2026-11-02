"""Opus-authored same-topic distractor POOLS (round 4, Camila r2 MC leakage standard).

For every judged list of an MC family, two Opus calls and one Wikidata step:

1. the TOPIC call sees only the hidden prompt (and the list's hop question), never the answer,
   and writes the list's TOPIC (what the question is about, region / era included, broad enough
   that at least five well-known answers fit it) and the KIND of entity;
2. the CANDIDATES call sees only the topic and kind and lists 25 REAL entities that fit, the most
   notable ones (record holders, superlatives, textbook examples) and less known ones, each with
   its English Wikipedia title;
3. code screens them (never in the item's prompt, never the same Wikidata entity as the gold, a
   fixed option or a name the readouts would trivially favour: the item's other bridges, its
   target; never sharing a form with one of them) and records each one's FAME (Wikipedia sitelink
   count). ``scripts/r4_mc_select.py`` then picks the four distractors from this pool.

Why (drafts measured with the lucky-guessing guessers): distractors written by a call that saw the
gold made the gold the centre of its list (options-only guesser 0.44-0.63); the ten most famous
members of a topic made the gold the obscure odd one out; a naming FORMAT copied from the gold made
the candidates invented look-alikes ("Kerma units", "Gmelin's salt") beside the one real name.

Output (scratch): ``{family: {item id: {role: {"topic", "kind", "gold", "distractors",
"enwiki", "fame", "spares", "dropped"}}}}``.
Run: ``ANTHROPIC_AUTH_TOKEN=... .venv/bin/python scripts/r4_mc_distractors.py --out F fam...``.
"""

import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from wsbench import mc
from wsbench.banks import load_bank
from wsbench.llm import schema_block, stream_json
from wsbench.registry import REPO_ROOT

MODEL = "claude-opus-5-5"
VERSION = "r4-distractors-2026-11-01d"
N_CANDIDATES = 25
N_DISTRACTORS = 4
# Wikimedia's user-agent policy: a tool name and a contact (a generic agent is rate-limited)
UA = "WorkspaceBenchBankBuild/1.0 (https://github.com/camila-blank/workspace-bench) python-urllib"
TOPIC_SYSTEM = (
    "You write the TOPIC of a multiple-choice list for an interpretability benchmark. You see "
    "only the hidden QUESTION, never its answer. The TOPIC says what the question is about, at "
    "the level of the answer's category and field, INCLUDING the region, era or domain the "
    "question makes clear ('a medieval battle in the Middle East', 'a river of Siberia', 'a "
    "Renaissance Italian painter'), yet broad enough that AT LEAST FIVE different real, "
    "reasonably well-known answers fit it equally well. Never paraphrase the question's specific "
    "clue and never name anything from the question. Also give KIND: the kind of entity, in a "
    "few words (e.g. 'a person', 'a rock band', 'a company', 'a dynasty', 'a mountain', 'a "
    "disease', 'a textile', 'a physical constant')."
)
CANDIDATE_SYSTEM = (
    "You list candidates for a multiple-choice list. Given a TOPIC and the KIND of entity, list "
    "TWENTY-FIVE different REAL entities of that kind that fit the topic: the most notable ones "
    "(record holders, superlatives, the best known, the textbook examples) AND moderately and "
    "less known ones. Only entities that really exist and have an English Wikipedia article; "
    "never invent a name to fit a pattern. 'name' is the entity's common English name; 'enwiki' "
    "its exact English Wikipedia article title (with any disambiguation there, never in the "
    "name)."
)
TOPIC_SCHEMA = schema_block(
    "topic", {"topic": {"type": "string"}, "kind": {"type": "string"}}, ["topic", "kind"]
)
SCHEMA = schema_block(
    "candidates",
    {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "enwiki": {"type": "string"}},
                "required": ["name", "enwiki"],
                "additionalProperties": False,
            },
        },
    },
    ["candidates"],
)


# wrong_bridge: the list's topic is the hidden entity's ROLE, never written from the question. The
# question describes the TRUE bridge (the contrast), so a topic written from it ("a 19th-century
# English landscape painter" for a Constable painting) excludes the model's wrong bridge (van
# Gogh, the gold) and points at it as the odd one out
WB_ROLE_TOPIC: dict[tuple[str, str], tuple[str, str]] = {
    ("painting_creator", "painter"): ("a painter", "a person"),
    ("novel_author", "writer"): ("a novelist or writer", "a person"),
    ("composition_composer", "composer"): ("a composer", "a person"),
    ("film_director", "filmmaker"): ("a film director", "a person"),
    ("album_performer", "musician"): ("a popular music singer or performer", "a person"),
    ("song_performer", "musician"): ("a popular music singer or performer", "a person"),
    ("song_lyricist", "musician"): ("a songwriter or lyricist", "a person"),
    ("album_performer", "band"): ("a rock or pop band", "a band"),
    ("song_performer", "band"): ("a rock or pop band", "a band"),
    ("doctoral_advisor", "scholar"): ("a scientist or scholar", "a person"),
    ("album_label", "company"): ("a record label", "a company"),
    ("game_developer", "company"): ("a video game company", "a company"),
    ("product_manufacturer", "company"): ("a shipbuilder or manufacturer", "a company"),
    ("tv_network", "company"): ("a television network or broadcaster", "a company"),
    ("person_father", "historical_leader"): ("a historical ruler or political figure", "a person"),
    ("person_mother", "historical_leader"): ("a historical ruler or noblewoman", "a person"),
    ("org_founder", "historical_leader"): ("a historical ruler or political figure", "a person"),
    ("namesake", "historical_leader"): ("a historical political figure", "a person"),
    ("namesake", "composer"): ("a composer", "a person"),
    ("person_mother", "musician"): ("a popular music singer or performer", "a person"),
    ("character_creator", "filmmaker"): ("a creator of animated or film characters", "a person"),
}


def _forms_of(it: dict[str, Any], role: str) -> list[str]:
    nf = (it.get("name_forms") or {}).get(role) or {}
    unit = next((u for u in it.get("units") or [] if u.get("role") == role), {}) or {}
    out = [f for fs in nf.values() for f in fs] + [
        f for fs in (unit.get("forms") or {}).values() for f in fs
    ]
    return [str(f) for f in out if str(f).strip()]


def specs(family: str) -> list[dict[str, Any]]:
    """One spec per judged list: item id, role, prompt, hop question, gold (+ its forms), the
    fixed options and the names to avoid."""
    out: list[dict[str, Any]] = []
    if family == "wrong_bridge":
        _h, items = load_bank(REPO_ROOT / "evals/wrong_bridge/items_v2.json")
        from wsbench.evals.wrong_bridge.judge import subject_of

        for it in items:
            m = it["mc"]
            subject = subject_of(it["prompt"]) or "the entity the statement is about"
            out.append(
                {
                    "id": it["id"],
                    "role": "bridge",
                    "prompt": it["prompt"],
                    # the list asks for the hidden ENTITY (hop 1), never the final fact (a year,
                    # a city): a topic written from the bare prompt described birth cities
                    "question": f"Name {subject[:1].lower() + subject[1:]}.",
                    "gold": m["gold"],
                    "gold_forms": m["forms"][m["gold"]],
                    "fixed": [m["contrast"]],
                    "fixed_forms": m["forms"][m["contrast"]],
                    "avoid": [it.get("target", ""), it.get("correct_answer", "")],
                    "gold_qids": [it["wikidata"]["B_prime"], it["wikidata"]["B"]],
                    "topic_override": WB_ROLE_TOPIC[(it["template"], m["category"])],
                    "note": (
                        "The list's options are candidates for the ENTITY the hop question asks "
                        "for (a person, group or company), never for the fact the full prompt "
                        "finally asks (a year or a city): write the topic of that entity."
                    ),
                }
            )
        return out
    bank = {
        "basic_readout_mt": "evals/basic_readout_mt/items_v2.json",
        "multihop_mt_v2": "evals/multihop_mt_v2/items_v2.json",
        "multilingual_multihop": "evals/multilingual_multihop/items_v2.json",
    }[family]
    _h, items = load_bank(REPO_ROOT / bank)
    for it in items:
        for role, blk in (it.get("mc") or {}).items():
            if role == "language" or not isinstance(blk, dict):
                continue
            q = next(
                (str(b.get("question", "")) for b in it.get("bridges") or []
                 if role in (b.get("units") or [])),
                "",
            )  # fmt: skip
            others = [
                str(b["gold"])
                for r, b in (it.get("mc") or {}).items()
                if r not in (role, "language") and isinstance(b, dict)
            ]
            out.append(
                {
                    "id": it["id"],
                    "role": role,
                    "prompt": it["prompt"],
                    "question": q,
                    "gold": str(blk["gold"]),
                    "gold_forms": _forms_of(it, role) or [str(blk["gold"])],
                    "fixed": [],
                    "fixed_forms": [],
                    "avoid": [*others, str(it.get("target", "")), *(it.get("target_alts") or [])],
                    "note": "",
                }
            )
    return out


def topic_message(s: dict[str, Any]) -> str:
    """The topic call's message: the hidden prompt (and the list's hop question), never the
    answer or any option, so the label is not written around the gold."""
    parts = [f"HIDDEN QUESTION:\n{s['prompt']}"]
    if s["question"]:
        parts.append(f"HIDDEN HOP QUESTION (what this list asks about):\n{s['question']}")
    if s["note"]:
        parts.append(s["note"])
    parts.append("Give the TOPIC and KIND as JSON.")
    return "\n\n".join(parts)


def candidate_message(topic: str, kind: str, retry_note: str = "") -> str:
    parts = [f"TOPIC: {topic}", f"KIND: {kind}"]
    if retry_note:
        parts.append(retry_note)
    parts.append(f"List {N_CANDIDATES} real fitting entities as JSON.")
    return "\n\n".join(parts)


def _clash(name: str, forms: list[str]) -> bool:
    f = mc.fold(name)
    return any(
        mc.fold(g) == f or mc.form_in(f, [g]) or mc.form_in(mc.fold(g), [name]) for g in forms if g
    )


def screen(s: dict[str, Any], cands: list[dict[str, str]]) -> tuple[list[dict[str, str]], list]:
    keep: list[dict[str, str]] = []
    dropped: list[dict[str, str]] = []
    taken = [*s["gold_forms"], s["gold"], *s["fixed"], *s["fixed_forms"]]
    avoid = [a for a in s["avoid"] if a]
    for c in cands:
        name = str(c.get("name", "")).strip()
        why = ""
        if not name:
            why = "empty"
        elif mc.form_in(mc.fold(s["prompt"]), [name]):
            why = "in the prompt"
        elif _clash(name, taken):
            why = "shares a form with the gold or a fixed option"
        elif avoid and _clash(name, avoid):
            why = "a name to avoid"
        elif any(_clash(name, [k["name"]]) for k in keep):
            why = "near-duplicate of another candidate"
        if why:
            dropped.append({"name": name, "why": why})
            continue
        keep.append({"name": name, "enwiki": str(c.get("enwiki", "")).strip()})
    return keep, dropped


def qids_of(titles: list[str]) -> dict[str, str]:
    """English Wikipedia title (or name) -> its Wikidata QID (redirects followed); unknown
    titles are absent."""
    out: dict[str, str] = {}
    uniq = sorted({t for t in titles if t})
    for i in range(0, len(uniq), 40):
        chunk = uniq[i : i + 40]
        q = urllib.parse.urlencode(
            {"action": "query", "titles": "|".join(chunk), "redirects": "1", "prop": "pageprops",
             "ppprop": "wikibase_item", "format": "json"}
        )  # fmt: skip
        req = urllib.request.Request(
            f"https://en.wikipedia.org/w/api.php?{q}",
            headers={"User-Agent": UA},
        )
        d: dict[str, Any] = {}
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.loads(r.read().decode()).get("query") or {}
                break
            except (OSError, ValueError):
                time.sleep(5 + 10 * attempt)
        steps = {n["from"]: n["to"] for n in (d.get("normalized") or [])}
        steps.update({n["from"]: n["to"] for n in (d.get("redirects") or [])})
        by_title = {
            p.get("title"): (p.get("pageprops") or {}).get("wikibase_item")
            for p in (d.get("pages") or {}).values()
        }
        for t in chunk:
            c = t
            for _ in range(4):
                c = steps.get(c, c)
            if by_title.get(c):
                out[t] = str(by_title[c])
        time.sleep(0.3)
    return out


def sitelinks_of(qids: list[str]) -> dict[str, int]:
    """QID -> its number of Wikipedia sitelinks (the fame proxy)."""
    out: dict[str, int] = {}
    uniq = sorted({q for q in qids if q})
    for i in range(0, len(uniq), 40):
        q = urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": "|".join(uniq[i : i + 40]),
             "props": "sitelinks", "format": "json"}
        )  # fmt: skip
        req = urllib.request.Request(
            f"https://www.wikidata.org/w/api.php?{q}",
            headers={"User-Agent": UA},
        )
        d: dict[str, Any] = {}
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.loads(r.read().decode())
                if "error" not in d:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(5 + 10 * attempt)
        for qid, e in (d.get("entities") or {}).items():
            links = e.get("sitelinks") or {}
            out[qid] = sum(1 for k in links if k.endswith("wiki") and k != "commonswiki")
        time.sleep(0.3)
    return out


def _case(name: str, gold: str) -> str:
    """A lower-case one-word gold ("kente") gets lower-case one-word distractors ("bogolan")."""
    if gold[:1].islower() and " " not in name and name[:1].isupper() and not name[1:2].isupper():
        return name[:1].lower() + name[1:]
    return name


def run(family: str, only: set[str] | None = None, retry_note: str = "") -> dict[str, Any]:
    ss = [s for s in specs(family) if only is None or f"{s['id']}|{s['role']}" in only]
    out: dict[str, Any] = {}
    topics: dict[int, dict[str, Any]] = {}

    def on_topic(i: int, r: dict[str, Any] | None) -> None:
        if r and str(r.get("topic", "")).strip():
            topics[i] = r

    for i, sp in enumerate(ss):
        if sp.get("topic_override"):
            topics[i] = {"topic": sp["topic_override"][0], "kind": sp["topic_override"][1]}
    for _attempt in range(3):
        todo = [i for i in range(len(ss)) if i not in topics]
        if not todo:
            break
        sub = dict(enumerate(todo))

        def on_t(k: int, r: dict[str, Any] | None, sub: dict[int, int] = sub) -> None:
            on_topic(sub[k], r)

        stream_json(
            [(TOPIC_SYSTEM, topic_message(ss[i])) for i in todo],
            schema=TOPIC_SCHEMA,
            model=MODEL,
            on_result=on_t,
            concurrency=64,
        )
    todo = [i for i in range(len(ss)) if i in topics]
    for _attempt in range(3):
        if not todo:
            break
        got: dict[int, dict[str, Any] | None] = {}
        sub = dict(enumerate(todo))

        def on(k: int, r: dict[str, Any] | None, got: dict = got, sub: dict = sub) -> None:
            got[sub[k]] = r

        stream_json(
            [
                (
                    CANDIDATE_SYSTEM,
                    candidate_message(topics[i]["topic"], topics[i]["kind"], retry_note),
                )
                for i in todo
            ],
            schema=SCHEMA,
            model=MODEL,
            on_result=on,
            concurrency=64,
        )
        names = [
            str(c.get("enwiki") or "")
            for i in todo
            for c in ((got.get(i) or {}).get("candidates") or [])
            if isinstance(c, dict)
        ]
        names += [n for i in todo for n in [ss[i]["gold"], *ss[i]["fixed"], *ss[i]["avoid"]] if n]
        names += [f for i in todo for f in ss[i]["gold_forms"][:5]]
        qid = qids_of(names)
        fame = sitelinks_of(
            [*qid.values(), *[q for i in todo for q in ss[i].get("gold_qids") or []]]
        )
        nxt = []
        for i in todo:
            s = ss[i]
            r = got.get(i) or {}
            taken = {qid[n] for n in [s["gold"], *s["fixed"], *s["avoid"]] if n in qid}
            if "gold_qids" in s:
                taken |= set(s["gold_qids"])
            cands = [
                {"name": _case(str(c.get("name", "")).strip(), s["gold"]), "enwiki": c["enwiki"]}
                for c in (r.get("candidates") or [])
                if isinstance(c, dict) and "enwiki" in c
            ]
            same = [c for c in cands if qid.get(str(c["enwiki"])) in taken]
            cands = [c for c in cands if c not in same]
            keep, dropped = screen(s, cands)
            dropped += [{"name": c["name"], "why": "same Wikidata entity as a taken name"}
                        for c in same]  # fmt: skip
            keep = [k for k in keep if qid.get(str(k["enwiki"])) in fame]
            gq = (s.get("gold_qids") or [qid.get(s["gold"])])[0]
            if gq is None:
                gq = next((qid[f] for f in s["gold_forms"] if f in qid), None)
            if len(keep) < N_DISTRACTORS:
                nxt.append(i)
                continue
            # a gold with no Wikipedia article: the candidates' median fame (no fame cue either way)
            g_fame = (
                fame[gq]
                if gq in fame
                else sorted(fame[qid[str(k["enwiki"])]] for k in keep)[len(keep) // 2]
            )
            keep.sort(
                key=lambda k: abs(math.log1p(fame[qid[str(k["enwiki"])]]) - math.log1p(g_fame))
            )
            out.setdefault(s["id"], {})[s["role"]] = {
                "topic": str(topics[i]["topic"]).strip(),
                "kind": str(topics[i]["kind"]).strip(),
                "fame": {
                    "gold": g_fame,
                    **{k["name"]: fame[qid[str(k["enwiki"])]] for k in keep[:N_DISTRACTORS]},
                },
                "gold": s["gold"],
                "distractors": [k["name"] for k in keep[:N_DISTRACTORS]],
                "enwiki": {k["name"]: k["enwiki"] for k in keep[:N_DISTRACTORS]},
                "spares": keep[N_DISTRACTORS:],
                "dropped": dropped,
            }
        todo = nxt
    missing = [ss[i] for i in range(len(ss)) if ss[i]["id"] not in out
               or ss[i]["role"] not in out[ss[i]["id"]]]  # fmt: skip
    if missing:
        print(f"{family}: {len(missing)} lists without 4 screened distractors", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("families", nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", type=Path, help="JSON {family: ['id|role', ...]} to regenerate")
    ap.add_argument("--note", default="", help="extra instruction for a regeneration round")
    a = ap.parse_args(argv)
    prev = json.loads(a.out.read_text(encoding="utf-8")) if a.out.exists() else {}
    only = json.loads(a.only.read_text(encoding="utf-8")) if a.only else None
    for fam in a.families:
        sel = set(only.get(fam, [])) if only is not None else None
        if sel is not None and not sel:
            continue
        res = run(fam, sel, a.note)
        merged = prev.setdefault(fam, {})
        for iid, roles in res.items():
            merged.setdefault(iid, {}).update(roles)
        print(f"{fam}: {sum(len(v) for v in res.values())} lists written")
    prev["_meta"] = {"version": VERSION, "model": MODEL, "script": "scripts/r4_mc_distractors.py"}
    a.out.write_text(json.dumps(prev, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

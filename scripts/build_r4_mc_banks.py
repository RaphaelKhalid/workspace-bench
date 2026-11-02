"""Build the round-4 MC bank versions (Camila r2 MC leakage standard, 2026-11-01).

Every bank is a NEW file (frozen banks are never edited): each item keeps every field of its
predecessor, and only the MC distractor lists change.

- basic_readout_mt items_v3.json, multihop_mt_v2 items_v3.json, multilingual_multihop
  items_v3.json: each content list's four distractors are the Opus-authored same-topic ones of
  ``scripts/r4_mc_distractors.py`` (frozen in ``evals/<family>/r4_distractors.json``).
- multilingual items_v3.json and multilingual_multihop items_v3.json: each language list's four
  distractors are the four OTHER gold languages of the same bank closest to the gold (shared
  family 4, script 2, region 1; ties seeded), so the gold is never the one big language among its
  small relatives (the options-only guesser picked Russian among Ukrainian / Bulgarian / Serbian /
  Belarusian), while the nearest relatives the bank has stay in the list.
- the lucky-guessing topic labels (``evals/baselines/topics/<family>.json``): the generation
  call's topic for an Opus-authored list, :data:`LANGUAGE_TOPIC` for a language list, the item's
  ``mc_type`` label for a multilingual concept list.

wrong_bridge v3 is built by ``scripts/wrong_bridge_mc_options.py --v3`` (it needs the
Wikidata name forms of every option). Deterministic given the frozen distractor file.
Run: ``python scripts/build_r4_mc_banks.py [--check]``.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LANGUAGE_TOPIC = "the language a short non-English prompt is written in"
TOPIC_VERSION = "topics-r4-2026-11-01"
MULTILINGUAL_TOPICS = {
    "opposite": "the opposite (antonym) of a common word",
    "number": "a number word",
    "month": "a month name",
    "colour": "a colour word",
    "time": "a time of day",
    "family": "a family-relation word",
    "capital": "a capital city",
    "day": "a day of the week",
    "season": "a season of the year",
    "phase": "a form or state of water",
}
CONTENT_FAMILIES = ("basic_readout_mt", "multihop_mt_v2", "multilingual_multihop")
LANG_FAMILIES = ("multilingual", "multilingual_multihop")


CONCEPT_SEED = "r4-ml-concept-2026-11-01"


def multilingual_concepts(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    """item name -> its v3 concept distractors (multilingual). The v2 lists drew random words of
    the item's mc_type, so a guesser shown solved examples learnt which words are usual answers
    (small, cold, down, red). A v3 list samples, without replacement and weighted by how often
    each is a gold, the OTHER items' golds of the same mc_type (never the item's gold or a word
    of its prompt, ``prompt_concepts``): a word then stands as a distractor about as often as it
    is the answer. A type with too few distinct golds is filled from its v2 distractors, in
    order."""
    import hashlib
    import random
    from collections import Counter

    by_type: dict[str, Counter[str]] = {}
    for it in items:
        g = str(it["mc"]["concept_native"]["gold"])
        by_type.setdefault(str(it["mc_type"]), Counter())[g] += 1
    out: dict[str, list[str]] = {}
    for it in items:
        blk = it["mc"]["concept_native"]
        gold = str(blk["gold"])
        banned = {gold.casefold(), *(str(c).casefold() for c in it.get("prompt_concepts") or [])}
        pool = {w: n for w, n in by_type[str(it["mc_type"])].items() if w.casefold() not in banned}
        rng = random.Random(
            int(hashlib.sha256(f"{CONCEPT_SEED}|{it['name']}".encode()).hexdigest(), 16)
        )
        picked: list[str] = []
        while pool and len(picked) < 4:
            words = sorted(pool)
            w = rng.choices(words, weights=[pool[x] for x in words])[0]
            picked.append(w)
            del pool[w]
        for d in blk["distractors"]:
            if len(picked) >= 4:
                break
            if str(d).casefold() not in banned and d not in picked:
                picked.append(str(d))
        out[str(it["name"])] = picked
    return out


def build(family: str, gen: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    src = REPO / "evals" / family / "items_v2.json"
    bank = json.loads(src.read_text(encoding="utf-8"))
    items = bank["items"]
    topics: dict[str, list[str]] = {}
    from wsbench.multitoken.options import R4_LANG_POOLS, r4_language_distractors

    golds = {
        str(it["mc"]["language"]["gold"]) for it in items if "language" in (it.get("mc") or {})
    }
    if family in LANG_FAMILIES and golds != set(R4_LANG_POOLS[family]):
        raise SystemExit(
            f"{family}: R4_LANG_POOLS is not the bank's gold languages {sorted(golds)}"
        )
    changed = 0
    concepts = multilingual_concepts(items) if family == "multilingual" else {}
    for it in items:
        if it["name"] in concepts:
            it["mc"]["concept_native"]["distractors"] = concepts[it["name"]]
            changed += 1
        mcb = it.get("mc") or {}
        for role, blk in mcb.items():
            if not isinstance(blk, dict):
                continue
            if role == "language":
                if family in LANG_FAMILIES:
                    blk["distractors"] = r4_language_distractors(family, str(blk["gold"]))
                    changed += 1
                continue
            if family in CONTENT_FAMILIES:
                g = (gen.get(family) or {}).get(_label(it["name"]), {}).get(role)
                if g is None:
                    raise SystemExit(f"{family}/{it['name']}/{role}: no r4 distractors")
                if g["gold"] != blk["gold"]:
                    raise SystemExit(f"{family}/{it['name']}/{role}: gold changed")
                blk["distractors"] = list(g["distractors"])
                if "pool" in blk:
                    blk["pool"] = "Opus-authored same-topic distractors (r4_distractors.json)"
                changed += 1
    for it in items:
        roles = it.get("mc_roles") or [r for r in (it.get("mc") or {}) if r != "language"]
        if family == "basic_readout_mt":
            roles = ["readout"]
        labels = []
        for role in roles:
            blk = (it.get("mc") or {}).get(role) or {}
            if role == "language":
                labels.append(LANGUAGE_TOPIC)
            elif family == "multilingual":
                labels.append(MULTILINGUAL_TOPICS[str(it["mc_type"])])
            else:
                g = (gen.get(family) or {}).get(_label(it["name"]), {}).get(role) or {}
                labels.append(str(g["topic"]))
        topics[_label(it["name"])] = labels
    version = bank.get("version")
    new_version: Any = "v3" if isinstance(version, str) and version.startswith("v") else 3
    if isinstance(version, str) and version.isdigit():
        new_version = "3"
    bank["version"] = new_version
    bank["supersedes"] = "items_v2.json"
    bank["frozen"] = "2026-11-01"
    bank["r4_mc"] = {
        "script": "scripts/build_r4_mc_banks.py",
        "rule": (
            "round 4 (Camila r2 MC leakage standard): only the MC distractor lists change. "
            + (
                "Content lists: the four Opus-authored same-topic distractors of "
                "r4_distractors.json (scripts/r4_mc_distractors.py). "
                if family in CONTENT_FAMILIES
                else ""
            )
            + (
                "Concept lists: four of the other items' golds of the same mc_type, sampled "
                "without replacement weighted by gold frequency (never the gold or a prompt "
                "concept; filled from the v2 list). "
                if family == "multilingual"
                else ""
            )
            + (
                "Language lists: the four other gold languages of this bank closest to the gold "
                "(shared family 4, script 2, region 1; ties seeded by family and gold). "
                if family in LANG_FAMILIES
                else ""
            )
        ),
        "lang_rule": (
            "wsbench.multitoken.options.r4_language_distractors (R4_LANG_INFO / R4_LANG_POOLS)"
            if family in LANG_FAMILIES
            else None
        ),
        "lists_changed": changed,
    }
    topic_doc = {
        "family": family,
        "version": TOPIC_VERSION,
        "script": "scripts/build_r4_mc_banks.py",
        "language_topic": LANGUAGE_TOPIC,
        "items": topics,
    }
    return bank, topic_doc


def _label(name: str) -> str:
    from wsbench.banks import label_of

    return label_of(name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    texts: dict[Path, str] = {}
    gen: dict[str, Any] = {}
    for fam in CONTENT_FAMILIES:
        p = REPO / "evals" / fam / "r4_distractors.json"
        gen[fam] = json.loads(p.read_text(encoding="utf-8"))["items"]
    for fam in ("basic_readout_mt", "multihop_mt_v2", "multilingual", "multilingual_multihop"):
        bank, topics = build(fam, gen)
        texts[REPO / "evals" / fam / "items_v3.json"] = (
            json.dumps(bank, indent=1, ensure_ascii=False) + "\n"
        )
        texts[REPO / "evals" / "baselines" / "topics" / f"{fam}.json"] = (
            json.dumps(topics, indent=1, ensure_ascii=False) + "\n"
        )
    wb = json.loads((REPO / "evals/wrong_bridge/r4_distractors.json").read_text(encoding="utf-8"))
    texts[REPO / "evals" / "baselines" / "topics" / "wrong_bridge.json"] = (
        json.dumps(
            {
                "family": "wrong_bridge",
                "version": TOPIC_VERSION,
                "script": "scripts/build_r4_mc_banks.py",
                "items": {k: [v["bridge"]["topic"]] for k, v in sorted(wb["items"].items())},
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n"
    )
    if a.check:
        stale = [p for p, t in texts.items() if not p.exists() or p.read_text("utf-8") != t]
        for p in stale:
            print(f"stale: {p}", file=sys.stderr)
        return 1 if stale else 0
    for p, t in texts.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t, encoding="utf-8")
        print(f"wrote {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

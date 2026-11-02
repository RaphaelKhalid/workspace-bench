"""Build the round-4b MC bank versions (Camila r2 MC leakage standard, second pass, 2026-11-01).

Every bank is a NEW file (frozen banks are never edited): each item keeps every field of its
predecessor and only the MC distractor lists change.

- basic_readout_mt / multihop_mt_v2 / multilingual_multihop / multilingual_mt ``items_v4.json``
  (from ``items_v3.json``) and multilingual_typo ``items_v3.json`` (from ``items_v2.json``): each
  content list's four distractors are the ones ``scripts/r4b_mc_refine.py`` kept
  (``evals/<family>/r4b_distractors.json``);
- multilingual_mt and multilingual_typo language lists: the four other gold languages of the
  bank closest to the gold (``options.r4_language_distractors``, the rule multilingual got in
  v3); multilingual_multihop language lists: frequency-balanced (every language a distractor four
  times as often as it is the gold, ``options.r4b_balanced_language_distractors``);
- multilingual_typo gains a frozen ``mc.correction_native`` block (gold: the unit's first
  English form, as the v2 builder showed it) so its list no longer depends on a draw over the
  other items' golds;
- the lucky-guessing topic labels ``evals/baselines/topics/<family>.json``: the refine pass's
  rewritten topic for a content list (kind + broad field only), :data:`LANGUAGE_TOPIC` for a
  language list.

Deterministic given the frozen refine files. Run: ``python scripts/build_r4b_mc_banks.py
[--check]``.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LANGUAGE_TOPIC = "the language a short non-English prompt is written in"
TOPIC_VERSION = "topics-r4b-2026-11-01"
# family -> (source bank, new bank, new version)
BANKS: dict[str, tuple[str, str, Any]] = {
    "basic_readout_mt": ("items_v3.json", "items_v4.json", None),
    "multihop_mt_v2": ("items_v3.json", "items_v4.json", None),
    "multilingual_multihop": ("items_v3.json", "items_v4.json", None),
    "multilingual_mt": ("items_v3.json", "items_v4.json", None),
    "multilingual_typo": ("items_v2.json", "items_v3.json", None),
}
CONCEPT_FAMILIES = ("multilingual_mt", "multilingual_typo")
# Topic labels set by hand, each with its reason (applied to the topics file only; the lists are
# the refine pass's). mlt-hu-elengedhetetlen-01: the passage's own topic call said "a Hungarian
# adjective" (the options are English), and the gold-aware fix wrote "a degree of necessity or
# importance", which describes the gold; the kind alone is the honest topic.
TOPIC_OVERRIDES: dict[tuple[str, str, str], str] = {
    ("multilingual_typo", "mlt-hu-elengedhetetlen-01", "correction_native"): (
        "an emphatic English adjective phrase"
    ),
}


def _bump(version: Any, new: int) -> Any:
    if isinstance(version, str) and version.startswith("v"):
        return f"v{new}"
    if isinstance(version, str):
        return str(new)
    return new


def build(family: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    from wsbench.banks import label_of
    from wsbench.multitoken.options import gold_english, judged_roles, r4_language_distractors

    src, dst, _v = BANKS[family]
    bank = json.loads((REPO / "evals" / family / src).read_text(encoding="utf-8"))
    refine = json.loads(
        (REPO / "evals" / family / "r4b_distractors.json").read_text(encoding="utf-8")
    )
    if int(refine.get("pass", 1)) < 2:
        raise SystemExit(f"{family}: r4b_distractors.json is not a pass-2+ file (topics rewritten)")
    lists = refine["items"]
    from wsbench.multitoken.options import r4b_balanced_language_distractors

    balanced = (
        r4b_balanced_language_distractors(
            family, {str(it["name"]): str(it["mc"]["language"]["gold"]) for it in bank["items"]}
        )
        if family == "multilingual_multihop"
        else {}
    )
    topics: dict[str, list[str]] = {}
    changed = 0
    for it in bank["items"]:
        lab = label_of(it["name"])
        mcb = it.setdefault("mc", {})
        roles = judged_roles(it)
        if family == "basic_readout_mt":
            roles = ["readout"]
        labels: list[str] = []
        for role in roles:
            if role == "language":
                blk = mcb["language"]
                if family in CONCEPT_FAMILIES:
                    blk["distractors"] = r4_language_distractors(family, str(blk["gold"]))
                    changed += 1
                elif family == "multilingual_multihop":
                    blk["distractors"] = balanced[str(it["name"])]
                    changed += 1
                labels.append(LANGUAGE_TOPIC)
                continue
            r = (lists.get(lab) or {}).get(role)
            if r is None:
                raise SystemExit(f"{family}/{it['name']}/{role}: no r4b list")
            if role not in mcb:
                if family != "multilingual_typo":
                    raise SystemExit(f"{family}/{it['name']}/{role}: no mc block to replace")
                mcb[role] = {"gold": gold_english(it, role), "distractors": []}
            blk = mcb[role]
            if str(blk["gold"]) != str(r["gold"]):
                raise SystemExit(f"{family}/{it['name']}/{role}: gold changed")
            if len(r["distractors"]) != 4 or len(set(r["distractors"])) != 4:
                raise SystemExit(f"{family}/{it['name']}/{role}: not four distinct distractors")
            blk["distractors"] = list(r["distractors"])
            if "pool" in blk:
                blk["pool"] = "Opus-revised same-topic distractors (r4b_distractors.json)"
            changed += 1
            labels.append(TOPIC_OVERRIDES.get((family, lab, role), str(r["topic"])))
        # a family that floors only some units (basic_readout_mt) labels only those lists
        topics[lab] = labels
        if family == "multilingual_typo" and "mc_roles" in it:
            # the content block now precedes the language block, as in the other banks
            it["mc"] = {r: mcb[r] for r in it["mc_roles"] if r in mcb}
    new_n = int(dst.removeprefix("items_v").removesuffix(".json"))
    bank["version"] = _bump(bank.get("version"), new_n)
    bank["supersedes"] = src
    bank["frozen"] = "2026-11-01"
    bank["r4b_mc"] = {
        "script": "scripts/build_r4b_mc_banks.py",
        "rule": (
            "round 4b (Camila r2 MC leakage standard, second pass): only the MC distractor lists "
            "change. Content lists: the four distractors scripts/r4b_mc_refine.py kept "
            "(r4b_distractors.json: Opus-revised in the gold's naming style, fitting the topic as "
            "stated, kept when neither the options-only nor the topic guesser solves the item in "
            "more than 1 of 5 draws). "
            + (
                "Language lists: the four other gold languages of this bank closest to the gold "
                "(options.r4_language_distractors). "
                if family in CONCEPT_FAMILIES
                else ""
            )
            + (
                "Language lists: frequency-balanced over the bank's gold languages (every "
                "language a distractor four times as often as it is the gold; "
                "options.r4b_balanced_language_distractors). "
                if family == "multilingual_multihop"
                else ""
            )
            + (
                "correction_native: a frozen mc block (gold = the unit's first English form). "
                if family == "multilingual_typo"
                else ""
            )
        ),
        "lists_changed": changed,
        "n_over_gate": refine.get("n_over_gate"),
    }
    topic_doc = {
        "family": family,
        "version": TOPIC_VERSION,
        "script": "scripts/build_r4b_mc_banks.py (topics: scripts/r4b_mc_refine.py --pass2)",
        "language_topic": LANGUAGE_TOPIC,
        "items": topics,
    }
    return dst, bank, topic_doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("families", nargs="*", default=list(BANKS))
    a = ap.parse_args(argv)
    texts: dict[Path, str] = {}
    for fam in a.families:
        dst, bank, topics = build(fam)
        texts[REPO / "evals" / fam / dst] = json.dumps(bank, indent=1, ensure_ascii=False) + "\n"
        texts[REPO / "evals" / "baselines" / "topics" / f"{fam}.json"] = (
            json.dumps(topics, indent=1, ensure_ascii=False) + "\n"
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

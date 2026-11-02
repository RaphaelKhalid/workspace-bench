"""Camila 2026-11-01: the four multilingual families drop the summarizer language tag and pass the
digest a short neutral TASK NOTE (the task type only). No note may name an item's gold language
or its intermediate / answer, for any item of the family's bank of record."""

import re

import pytest

from wsbench import digest, registry
from wsbench.banks import load_bank
from wsbench.multitoken.languages import LANGUAGES
from wsbench.multitoken.prompts import DIGEST_TASK_NOTES

FOUR = ("multilingual", "multilingual_mt", "multilingual_multihop", "multilingual_typo")


def _words_of(item: dict) -> set[str]:
    out: set[str] = set()
    for u in item.get("units") or []:
        for fs in (u.get("forms") or {}).values():
            out.update(str(f) for f in fs)
    out.update(str(x) for x in item.get("intermediates") or [])
    for blk in (item.get("mc") or {}).values():
        if isinstance(blk, dict) and blk.get("gold"):
            out.add(str(blk["gold"]))
    if item.get("lang") in LANGUAGES:
        out.update(LANGUAGES[item["lang"]].names.get("en", ()))
    if item.get("target"):
        out.add(str(item["target"]))
    return {w for w in out if w.strip()}


def _in(word: str, text: str) -> bool:
    pat = r"(?<!\w)" + re.escape(word.casefold()) + r"(?!\w)"
    return re.search(pat, text.casefold()) is not None


@pytest.mark.parametrize("family", FOUR)
def test_task_note_names_no_gold_language_or_intermediate(family, real_families):
    note = real_families[family].task_note
    assert note == DIGEST_TASK_NOTES[family] and note.strip()
    assert "language the readouts name" in note  # the task note asks for any naming, neutrally
    _h, items = load_bank(registry.frozen_bank_path(family))
    hits = sorted({(it["id"], w) for it in items for w in _words_of(it) if _in(w, note)})
    assert not hits, hits[:10]


def test_task_note_check_catches_a_leak():
    """The check above is not vacuous: a note naming the gold language or the concept fails."""
    item = {"lang": "ru", "units": [{"forms": {"en": ["hourglass"]}}], "mc": {}}
    words = _words_of(item)
    assert any(_in(w, "the model read a Russian passage") for w in words)
    assert any(_in(w, "about an hourglass") for w in words)
    assert not any(_in(w, DIGEST_TASK_NOTES["multilingual_mt"]) for w in words)


@pytest.mark.parametrize("family", FOUR)
def test_digest_system_carries_the_note_and_no_language_tag(family, tmp_path):
    from wsbench.registry import JudgeArgs

    args = JudgeArgs(
        readouts=tmp_path / "r.jsonl",
        out=tmp_path / "o",
        judge=None,  # type: ignore[arg-type]
        layers=None,
        items=None,
        limit=0,
        allow_missing=False,
        concurrency=1,
        rpm=1.0,
        dry_run=True,
        extra={},
    )
    s = digest.settings(args, family)
    system = digest.render_system(s, DIGEST_TASK_NOTES[family])
    assert DIGEST_TASK_NOTES[family] in system and '"language"' not in system

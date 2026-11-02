"""Plan 0032 §2.8.2-2.8.3: every summary family hands the summarizer a task note (task variant by
default) that names the task type only: never the item's gold, target or option text."""

import json

import pytest

from wsbench import digest, mc, registry


def _golds(family: str) -> list[str]:
    """Gold / target strings of a bank, wherever the bank keeps them."""
    path = registry.bank_path(family)
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("items", raw) if isinstance(raw, dict) else raw
    out: list[str] = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        for k in ("target", "gold", "gold_label", "concept", "attr", "hint", "answer"):
            v = it.get(k)
            if isinstance(v, str) and len(v) >= 4:
                out.append(v)
    return out


def _families() -> list[str]:
    registry.load_all()
    return sorted(f for f in registry.FAMILIES if f not in digest.NATIVE_ONLY)


@pytest.mark.parametrize("family", _families())
def test_every_summary_family_has_task_note_without_gold(family):
    spec = registry.FAMILIES[family]
    assert spec.task_note.strip(), family
    notes = [spec.task_note, *((spec.item_task_notes or dict)().values())]
    folded = [mc.fold(n) for n in notes]
    for g in _golds(family):
        fg = mc.fold(g)
        if len(fg.split()) == 1 and fg in ("model", "user", "question", "answer", "text"):
            continue
        assert not any(f" {fg} " in f" {n} " for n in folded), (family, g)


def test_default_variant_is_task():
    assert digest.DEFAULT_VARIANT == "task"
    assert digest.settings(digest._probe({"aggregate": "summary"})).variant == "task"

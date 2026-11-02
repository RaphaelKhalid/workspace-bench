"""Stage the bank viewer: the original banks plus every adapted model under ``adapted/``, as
static JSON beside the site. Serve the output dir with ``python -m http.server``."""

import json
import shutil
from pathlib import Path
from typing import Any

from wsbench.adapt.subjects import SUBJECTS
from wsbench.registry import REPO_ROOT

SITE = Path(__file__).parent / "site"
ORIGINAL = "qwen3.6-27b"

# README §The evals, in its order.
GROUPS: list[tuple[str, list[str]]] = [
    (
        "Basic (single token)",
        [
            "association",
            "basic_readout",
            "multihop",
            "multilingual",
            "poetry",
            "typo",
            "directed_modulation",
        ],
    ),
    (
        "Basic (multi-token)",
        [
            "multilingual_mt",
            "typo_mt",
            "basic_readout_mt",
            "multilingual_multihop",
            "multilingual_typo",
            "multi_concept_directed_modulation",
        ],
    ),
    (
        "Computational",
        [
            "chain_intermediates",
            "buggy_code",
            "arithmetic_intermediates",
        ],
    ),
    ("Safety", ["agentic_misalignment", "jailbreak_recognition"]),
    ("Association", ["user_modeling", "conjunctive_association", "role_bound_association"]),
    ("Bag of words", ["relational_multihop"]),
    ("Precision", ["jlens_concept_pr"]),
    ("Model-specific", ["moral_rationale", "introspection", "knowledge_cutoff"]),
]

# What a reader needs first, in the order tried: the text the model sees, then what it should
# compute. Everything else stays in the item's raw fields.
STIMULUS_KEYS = ("prompt", "stimulus", "messages", "code", "text", "expr", "statement")
TARGET_KEYS = ("target", "target_alts", "answer", "gold", "gold_alt", "gold_label", "attr_label")
LATENT_KEYS = ("intermediates", "bridges", "hop1", "hop2", "concept", "concepts", "units")
ADAPT_KEY = "adapt"


def _bank_rel(family: str) -> Path:
    """The family's registered bank path relative to a checkout root (plan 0032 §2.12)."""
    from wsbench.registry import REPO_ROOT, frozen_bank_path

    return frozen_bank_path(family).relative_to(REPO_ROOT)


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def _items(raw: Any) -> list[dict]:
    if isinstance(raw, list):
        return raw
    items = raw.get("items") if isinstance(raw, dict) else None
    return items if isinstance(items, list) else []


def _header(raw: Any) -> dict:
    return {k: v for k, v in raw.items() if k != "items"} if isinstance(raw, dict) else {}


def _is_turn(m: Any) -> bool:
    return isinstance(m, dict) and "role" in m


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and all(_is_turn(m) for m in value):
        return "\n\n".join(f"[{m['role']}]\n{m.get('content', '')}" for m in value)
    return json.dumps(value, ensure_ascii=False, indent=1)


def _flat(value: Any) -> list[str]:
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, list):
        return [s for v in value for s in _flat(v)]
    if isinstance(value, dict):
        q = value.get("answer") or value.get("target") or value.get("question")
        return [str(q)] if q else [json.dumps(value, ensure_ascii=False)]
    return [str(value)]


def _item_id(item: dict, n: int) -> str:
    return str(item.get("id") or item.get("name") or n)


def _orig_rate(item: dict) -> float | None:
    for key in ("consistency_strict", "consistency"):
        value = item.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    gate = item.get("gate")
    if isinstance(gate, dict):
        block = gate.get("last") if isinstance(gate.get("last"), dict) else gate
        if isinstance(block.get("correct"), int) and block.get("n"):
            return block["correct"] / block["n"]
    return None


def _subfamily(item: dict) -> Any:
    """The item's subfamily label; an agentic_misalignment clean twin (plan 0031, ``arm:
    "twin"``) is shown as its partner's category plus ``twin``, so it never reads as a misaligned
    scenario."""
    sub = item.get("subfamily") or item.get("variant") or item.get("category")
    return f"{sub} (twin)" if item.get("arm") == "twin" and sub else sub


def view_item(item: dict, n: int, gate: dict | None = None, selected: bool = True) -> dict:
    """One item as the viewer shows it: stimulus, target, latent, gate, and the raw fields."""
    stim_key = next((k for k in STIMULUS_KEYS if item.get(k)), None)
    adapt = item.get(ADAPT_KEY) or {}
    gate = gate or adapt.get("gate")
    if gate is None and (rate := _orig_rate(item)) is not None:
        gate = {"rate": rate, "pass": None}
    return {
        "id": _item_id(item, n),
        "origin": adapt.get("origin", "original"),
        "selected": selected,
        "tier": adapt.get("tier"),
        "knobs": adapt.get("knobs") or {},
        "note": adapt.get("note"),
        "subfamily": _subfamily(item),
        "stimulus": _text(item[stim_key]) if stim_key else "",
        "target": [s for k in TARGET_KEYS for s in _flat(item.get(k))],
        "latent": [s for k in LATENT_KEYS for s in _flat(item.get(k))][:24],
        "gate": gate,
        "raw": {k: v for k, v in item.items() if k not in (stim_key, ADAPT_KEY)},
    }


def _summary(rows: list[dict], header: dict, report: dict | None) -> dict:
    sel = [r for r in rows if r["selected"]]
    rates = [r["gate"]["rate"] for r in sel if r["gate"] and r["gate"].get("rate") is not None]
    out = {
        "n_items": len(sel),
        "n_candidates": len(rows),
        "n_new": sum(r["origin"] != "original" for r in sel),
        "mean_rate": sum(rates) / len(rates) if rates else None,
        "gate_rule": header.get("gate") if isinstance(header.get("gate"), str) else None,
        "subfamilies": sorted({str(r["subfamily"]) for r in sel if r["subfamily"]})[:8],
    }
    return out | (report or {})


def _family_view(items: list[dict], header: dict, gates: dict | None) -> list[dict]:
    if gates is None:
        return [view_item(it, n) for n, it in enumerate(items)]
    # With a frozen bank, "in the bank" is its own id list; before freezing, the gate verdict.
    in_bank = {str(it.get("id") or it.get("name")) for it in items} if items else None
    rows = []
    for n, rec in enumerate(gates.values()):
        sel = rec["id"] in in_bank if in_bank is not None else bool(rec["gate"].get("pass"))
        rows.append(view_item(rec["item"], n, rec.get("gate"), sel))
    return rows


def _read_gates(path: Path) -> dict[str, dict] | None:
    if not path.exists():
        return None
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            rec = json.loads(line)
            out[str(rec["id"])] = rec  # last record per id wins (re-gates append)
    return out


def build(out: Path, root: Path = REPO_ROOT) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    for asset in SITE.iterdir():
        shutil.copy(asset, out / asset.name)
    data = out / "data"
    if data.exists():
        shutil.rmtree(data)
    models: list[dict] = []

    orig = {"key": ORIGINAL, "label": "Qwen3.6-27B (original banks)", "families": {}}
    for _group, fams in GROUPS:
        for fam in fams:
            path = root / _bank_rel(fam)
            if not path.exists():
                continue
            raw = _load(path)
            rows = _family_view(_items(raw), _header(raw), None)
            _write(data / ORIGINAL / f"{fam}.json", {"family": fam, "items": rows})
            orig["families"][fam] = _summary(rows, _header(raw), {"status": "original"})
    models.append(orig)

    for mdir in sorted(p for p in (root / "adapted").glob("*") if p.is_dir()):
        report = _load(mdir / "report.json") if (mdir / "report.json").exists() else {}
        subject = SUBJECTS.get(mdir.name)
        label = report.get("label") or (subject.label if subject else mdir.name)
        model = {"key": mdir.name, "label": label, "families": {}}
        model["meta"] = {k: v for k, v in report.items() if k != "families"}
        for _group, fams in GROUPS:
            for fam in fams:
                bank, gates = mdir / f"{fam}.json", _read_gates(mdir / "gate" / f"{fam}.jsonl")
                if not bank.exists() and gates is None:
                    continue
                raw = _load(bank) if bank.exists() else {}
                rows = _family_view(_items(raw), _header(raw), gates)
                _write(data / mdir.name / f"{fam}.json", {"family": fam, "items": rows})
                fam_report = dict((report.get("families") or {}).get(fam) or {})
                n_orig = len(_items(_load(root / _bank_rel(fam))))
                orig_rows = [r for r in (gates or {}).values() if r.get("origin") == "original"]
                fam_report.setdefault("target", n_orig)
                fam_report.setdefault("n_original", n_orig)
                if orig_rows:
                    n_pass = sum(bool(r["gate"].get("pass")) for r in orig_rows)
                    fam_report.setdefault("n_original_pass", n_pass)
                fam_report.setdefault("status", "profiled" if not bank.exists() else "partial")
                model["families"][fam] = _summary(rows, _header(raw), fam_report)
        models.append(model)

    index = {"groups": [{"title": t, "families": f} for t, f in GROUPS], "models": models}
    _write(data / "index.json", index)
    return index


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False))


def main(out: str = "outputs/viewer") -> None:
    index = build(Path(out))
    n = sum(len(m["families"]) for m in index["models"])
    print(f"viewer: {len(index['models'])} models, {n} model-family views -> {out}")
    print(f"serve:  python -m http.server 8765 -d {out}")


if __name__ == "__main__":
    main()

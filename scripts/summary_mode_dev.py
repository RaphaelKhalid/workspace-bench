"""Plan 0020 D2: the summary-mode dev slice. ``ids`` writes the slice (items 0-19 in bank order of
every hooked family with >= 60 items in its readouts); ``audit`` scores the fidelity checks of one
or more summary-mode out dirs (no score is a selection input).

    python scripts/summary_mode_dev.py ids roots=DIR1,DIR2 out=dev_ids.json
    python scripts/summary_mode_dev.py audit runs=LABEL:OUTDIR,... roots=DIR1,DIR2 \
        [passivity=True] [out=PREFIX]

``roots`` are readouts dirs searched in order for ``<family>.jsonl`` (legacy names too)."""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from wsbench import digest, llm, registry
from wsbench.banks import load_bank
from wsbench.family import span_in
from wsbench.readouts import load_readouts

MIN_ITEMS = 60
N_DEV = 20
STOP = frozenset(
    [
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "have",
        "for",
        "are",
        "was",
        "were",
        "not",
        "but",
        "you",
        "your",
        "they",
        "them",
        "their",
        "there",
        "what",
        "which",
        "who",
        "whom",
        "will",
        "would",
        "could",
        "should",
        "about",
        "into",
        "over",
        "than",
        "then",
        "also",
        "just",
        "only",
        "very",
        "been",
        "being",
        "has",
        "had",
        "its",
        "it's",
        "can",
        "may",
        "might",
        "must",
        "our",
        "out",
        "all",
        "any",
        "some",
        "more",
        "most",
        "such",
        "each",
        "other",
        "these",
        "those",
        "when",
        "where",
        "while",
        "because",
        "answer",
        "model",
        "text",
        "word",
        "words",
    ]
)
AUDIT_MODEL = "claude-opus-5-5"
AUDIT_SYSTEM = """You audit a note-taker's digest of interpretability-lens readouts. You see each \
digest item (a statement and the verbatim evidence span it cites) and the readout sample that \
span comes from. The note-taker was told to be a passive recorder. Flag an item if its statement \
does any of: interprets beyond what the readouts say; infers what the passage or task is; answers \
a question; translates; generalises a specific term into a category; sharpens a category into a \
specific member; combines separate readouts into one claim; changes who wants/believes/does \
what, or whether a claim is asserted, denied or merely mentioned. Otherwise it is faithful."""
AUDIT_SCHEMA = llm.schema_block(
    "passivity",
    {
        "violations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["index", "kind"],
                "properties": {"index": {"type": "integer"}, "kind": {"type": "string"}},
            },
        }
    },
    ["violations"],
)


def hooked() -> list[str]:
    registry.load_all()
    return sorted(f for f in registry.FAMILIES if f not in digest.NATIVE_ONLY)


def readouts_path(fam: str, roots: list[Path]) -> Path | None:
    for root in roots:
        for name in (fam, *registry.legacy_names(fam)):
            p = root / f"{name}.jsonl"
            if p.exists():
                return p
    return None


def _bank_ids(fam: str) -> list[tuple[str, str]]:
    """``(item id, readout id)`` in bank order; the readout id is ``readout_of`` where the bank
    has one (introspection units read a shared readout), else the item id."""
    spec = registry.FAMILIES[fam]
    path = registry.REPO_ROOT / spec.bank
    try:
        _h, items = load_bank(path)
    except Exception:
        items = json.loads(path.read_text())
        items = items["items"] if isinstance(items, dict) else items
    out = []
    for it in items:
        i = str(it.get("id", it.get("name")))
        out.append((i, str(it.get("readout_of") or i)))
    return out


def dev_ids(roots: list[Path]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for fam in hooked():
        p = readouts_path(fam, roots)
        if p is None:
            continue
        cells, _rep = load_readouts(p)
        present = {c.id for c in cells}
        order = [i for i, rid in _bank_ids(fam) if rid in present]
        if len(order) >= MIN_ITEMS:
            out[fam] = order[:N_DEV]
    return out


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[^\W\d_]{3,}", text.casefold()) if w not in STOP}


def coverage(cells: list, evidence: list[str]) -> float | None:
    """Share of recurring word types (>= 3 samples spanning >= 2 layers) present in the
    evidence samples."""
    n_samples: Counter[str] = Counter()
    layers: dict[str, set[int]] = defaultdict(set)
    for c in cells:
        samples = c.samples if c.samples is not None else [" ".join(c.tokens or ())]
        for s in samples:
            for w in _words(s):  # token cells arrive decoded by the loader
                n_samples[w] += 1
                layers[w].add(c.layer)
    recurring = {w for w, n in n_samples.items() if n >= 3 and len(layers[w]) >= 2}
    if not recurring:
        return None
    ev = set().union(*(_words(e) for e in evidence)) if evidence else set()
    return len(recurring & ev) / len(recurring)


def _targets(row: dict) -> list[str]:
    t = row.get("targets")
    return [str(x) for x in t] if isinstance(t, list) else []


def selection_bias(cells: list, row: dict) -> float | None:
    """(gold-containing share of evidence samples) / (gold-containing share of bundle samples),
    for rows that carry ``targets`` (the bank families); None otherwise."""
    targets = _targets(row)
    evidence = row.get("summary_evidence") or []
    if not targets or not evidence:
        return None
    samples: list[str] = []
    for c in cells:
        if c.samples is not None:
            samples.extend(s for s in c.samples if s.strip())
        else:
            samples.append(" | ".join(c.tokens or ()))

    def has(s: str) -> bool:
        return any(span_in(t, s) for t in targets)

    base = sum(map(has, samples)) / len(samples) if samples else 0.0
    if base == 0:
        return None
    return (sum(map(has, evidence)) / len(evidence)) / base


def digest_key(fam: str, row: dict) -> str:
    """The id of the readout a summary-mode row's digest was built from, i.e. the readouts
    file id of that item's cells: introspection units read ``readout_of`` (a digest is shared
    by every unit reading it), directed_modulation rows are keyed ``item``, every other family
    ``id``."""
    if fam == "introspection":
        return str(row.get("readout_of") or row["id"])
    if fam == "directed_modulation":
        return str(row["item"])
    return str(row["id"])


def digest_rows(fam: str, rows: list[dict]) -> dict[str, dict]:
    """One row per digest (the first row carrying it): deliberative moral items have one row
    per side and introspection units share their readout's digest, so neither double counts."""
    out: dict[str, dict] = {}
    for r in rows:
        if "summary_state" not in r:
            continue
        out.setdefault(digest_key(fam, r), r)
    return out


def n_digested(fam: str, d: dict, digests: dict[str, dict]) -> int:
    """The items whose cells went to the summarizer (summarized + unsummarized + empty, from
    ``extras.summary``): the denominator of the per-item digest rates. Falls back to the item
    set of the extractor (``summary_mode_compare.item_verdicts`` plus row-less fails) when the
    extras lack those counts. Never ``len(rows)``: rows are per side / unit in some families,
    and unsummarized items have no row at all in the binary scorers."""
    ex = d["numbers"].get("extras", {}).get("summary", {}) or {}
    keys = ("n_items_summarized", "n_items_unsummarized", "n_items_empty")
    if all(k in ex for k in keys):
        return sum(int(ex[k]) for k in keys)
    cmp = _compare_module()
    try:
        v = cmp.item_verdicts(fam, d)
        return len(v) + cmp.n_rowless_fails(fam, d, v)
    except cmp.ExtractorError:
        return len(digests)


def _compare_module() -> Any:
    import importlib.util

    path = Path(__file__).resolve().parent / "summary_mode_compare.py"
    spec = importlib.util.spec_from_file_location("summary_mode_compare", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def evidence_sample(span: str, samples: list[str]) -> str | None:
    """The evidence sample (a whole readout sample / token line of ``summary_evidence``) that
    contains the statement's evidence span: an exact substring first, then ``span_in``."""
    for s in samples:
        if span and span in s:
            return s
    for s in samples:
        if span_in(span, s):
            return s
    return None


def audit_prompts(digests: list[dict]) -> tuple[list[tuple[str, str]], list[int]]:
    """One auditor prompt per digest: each item's statement, its evidence span AND the whole
    readout sample containing that span (mapped from the row's ``summary_evidence``)."""
    prompts: list[tuple[str, str]] = []
    sizes: list[int] = []
    for r in digests:
        st = r.get("summary_statements") or []
        if not st:
            continue
        samples = [str(x) for x in r.get("summary_evidence") or []]
        blocks = []
        for k, s in enumerate(st):
            ev = str(s.get("evidence", ""))
            sample = evidence_sample(ev, samples)
            blocks.append(
                f"[{k}] statement: {s.get('statement', '')}\n"
                f"    evidence span: {json.dumps(ev, ensure_ascii=False)}\n"
                "    readout sample: "
                + (json.dumps(sample, ensure_ascii=False) if sample is not None else "(not found)")
            )
        prompts.append((AUDIT_SYSTEM, "DIGEST ITEMS:\n" + "\n".join(blocks)))
        sizes.append(len(st))
    return prompts, sizes


def passivity(digests: list[dict]) -> tuple[int, int]:
    """(violating items, audited items) over the digests' statements (one entry per digest)."""
    prompts, sizes = audit_prompts(digests)
    bad = [0]

    def on_result(i: int, r: dict | None) -> None:
        if isinstance(r, dict):
            idx = {v.get("index") for v in r.get("violations", []) if isinstance(v, dict)}
            bad[0] += len([k for k in idx if isinstance(k, int) and 0 <= k < sizes[i]])

    if prompts:
        llm.stream_json(
            prompts,
            schema=AUDIT_SCHEMA,
            model=AUDIT_MODEL,
            reasoning={"anthropic_effort": "default"},
            on_result=on_result,
            concurrency=16,
            rpm=600,
        )
    return bad[0], sum(sizes)


def audit_family(
    label: str, fam: str, d: dict, roots: list[Path], do_passivity: bool
) -> dict[str, Any]:
    """The fidelity record of one summary-mode results.json."""
    rows = d.get("rows", [])
    ex = d["numbers"].get("extras", {}).get("summary", {}) or {}
    digests = digest_rows(fam, rows)
    p = readouts_path(fam, roots)
    by_item: dict[str, list] = defaultdict(list)
    if p is not None:
        cells, _rep = load_readouts(p, layers=d["config"].get("layers"))
        for c in cells:
            by_item[c.id].append(c)
    covs = [
        cv
        for k, r in digests.items()
        if (cv := coverage(by_item.get(k, []), r.get("summary_evidence") or [])) is not None
    ]
    bias = [
        b for k, r in digests.items() if (b := selection_bias(by_item.get(k, []), r)) is not None
    ]
    n_items = max(1, n_digested(fam, d, digests))
    kept, dropped = ex.get("n_evidence_kept", 0), ex.get("n_evidence_dropped", 0)
    rec: dict[str, Any] = {
        "run": label,
        "family": fam,
        "n": n_items,
        "unsummarized_rate": ex.get("n_items_unsummarized", 0) / n_items,
        "zero_digest_rate": ex.get("n_digest_zero_nonempty", 0) / n_items,
        "evidence_drop_rate": dropped / max(1, kept + dropped),
        "truncated": ex.get("n_truncated_items", 0),
        "coverage": sum(covs) / len(covs) if covs else None,
        "selection_bias": sum(bias) / len(bias) if bias else None,
        "value": d["numbers"].get("value"),
    }
    if do_passivity:
        bad, total = passivity(list(digests.values()))
        rec["passivity_violation_rate"] = bad / total if total else None
    return rec


def audit(runs: list[tuple[str, Path]], roots: list[Path], do_passivity: bool) -> list[dict]:
    out: list[dict[str, Any]] = []
    for label, root in runs:
        for res in sorted(root.glob("*/results.json")):
            d = json.loads(res.read_text())
            if d["config"].get("aggregate") != "summary":
                continue
            out.append(audit_family(label, res.parent.name, d, roots, do_passivity))
    return out


def main(argv: list[str]) -> int:
    cmd, kw = argv[0], dict(a.split("=", 1) for a in argv[1:])
    roots = [Path(r) for r in kw["roots"].split(",")]
    if cmd == "ids":
        ids = dev_ids(roots)
        Path(kw["out"]).write_text(json.dumps(ids, indent=1))
        print({f: len(v) for f, v in ids.items()})
        return 0
    if cmd == "audit":
        runs = [(r.split(":", 1)[0], Path(r.split(":", 1)[1])) for r in kw["runs"].split(",")]
        recs = audit(runs, roots, kw.get("passivity", "False") == "True")
        for r in recs:
            print(json.dumps(r))
        if kw.get("out"):
            Path(kw["out"] + ".json").write_text(json.dumps(recs, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Refuse a results tree or website bundle that republishes nocot readout text (plan 0044 §C9).

nocot-bench asks that its unpacked items not be republished, and readouts at user-turn positions
paraphrase its questions, so every knowledge_cutoff result row of a nocot item must carry
``[redacted: nocot]`` in its text fields (``judge._redact`` does this unless
``opts=keep_nocot_text=1``). This walks every ``*.json`` / ``*.jsonl`` under the given paths,
finds every object with an ``id`` that is a nocot item id (or ``source == "nocot"``), and exits 1
naming the files whose such objects hold a non-redacted ``quote`` / ``summary`` /
``summary_evidence`` / ``summary_statements``. Run it in every website / bundle build:

    python scripts/check_nocot_redaction.py outputs/<run> site/data
"""

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wsbench import nocot  # noqa: E402
from wsbench.evals.knowledge_cutoff.judge import unredacted_nocot  # noqa: E402


def _objects(x: Any) -> Iterator[dict]:
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from _objects(v)
    elif isinstance(x, list):
        for v in x:
            yield from _objects(v)


def _load(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".jsonl":
        out = []
        for ln in text.splitlines():
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
        return out
    try:
        return [json.loads(text)]
    except json.JSONDecodeError:
        return []


def check(paths: list[Path]) -> dict[str, list[str]]:
    """``{file: [offending nocot ids]}`` over every json / jsonl file under ``paths``."""
    ids = {str(it["id"]) for it in nocot.load_obscure()[1]}
    bad: dict[str, list[str]] = {}
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.json*"))
        for f in files:
            if f.suffix not in (".json", ".jsonl"):
                continue
            docs = _load(f)
            rows = [o for doc in docs for o in _objects(doc) if "id" in o]
            hit = unredacted_nocot(rows, ids)
            # a judge / digest cache (cells.jsonl) holds raw readouts and quotes keyed
            # "<id>|L<layer>" or "digest:<id>|...": never publishable for a nocot id
            for o in docs:
                key = str(o.get("key", "")) if isinstance(o, dict) else ""
                kid = key.removeprefix("digest:").split("|", 1)[0]
                if kid in ids:
                    hit.append(kid)
            if hit:
                bad[str(f)] = sorted(set(hit))
    return bad


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    bad = check([Path(a) for a in argv])
    for f, ids in bad.items():
        print(f"{f}: unredacted nocot text for {len(ids)} id(s), e.g. {ids[:3]}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

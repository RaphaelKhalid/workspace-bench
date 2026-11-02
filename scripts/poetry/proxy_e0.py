"""E0 pre-registration (plan 0038 §5): the deterministic proxy of poetry's new rule on cached
readouts, no API call. Per item, count samples (under the declared sampling: one s3d/NLA
generation, one x4 generation, one token list) where the gold or each distractor passes the gate
(``line_final`` / ``named_plan`` / ``token_ok``); pass = ``n(gold) > max n(distractor)`` and
``n(gold) > 0``. Cross-item null: the same with item ``(k + 37) mod n``'s options (gold and
distractors of another couplet, checked against this item's readouts).

    python scripts/poetry/proxy_e0.py --bank evals/poetry/items_v2.json \\
        --arm s3d=PATH:prose1 --arm onchat=PATH:bullet4 ... --out e0.json
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from wsbench.banks import load_bank
from wsbench.evals.poetry.options import line_one_end, option_set
from wsbench.evals.poetry.score import counts
from wsbench.readouts import load_readouts, normalize


def proxy(items: list[dict], cells_by: dict[str, list], shift: int = 0) -> dict[str, bool]:
    out = {}
    n = len(items)
    for k, it in enumerate(items):
        src = items[(k + shift) % n] if shift else it
        opts, g = option_set(src)
        words = opts[:-1]
        cs = cells_by.get(it["id"], [])
        if not cs:
            continue
        c = counts(words, cs, line_one_end(it))
        gold = words[g]
        out[it["id"]] = c[gold] > 0 and c[gold] > max(c[w] for w in words if w != gold)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", type=Path, required=True)
    ap.add_argument("--arm", action="append", default=[], help="name=path:sampling")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    _h, items = load_bank(a.bank)
    ids = {it["id"] for it in items}
    res = {}
    for spec in a.arm:
        name, rest = spec.split("=", 1)
        path, sampling = rest.rsplit(":", 1)
        cells, _rep = load_readouts(Path(path), ids=ids)
        cells, _diag = normalize(cells, sampling)
        by: dict[str, list] = defaultdict(list)
        for c in cells:
            by[c.id].append(c)
        scope = [it for it in items if by.get(it["id"])]
        p = proxy(scope, by)
        null = proxy(scope, by, shift=37)
        res[name] = {
            "sampling": sampling,
            "n_items": len(p),
            "pass": sum(p.values()),
            "null_pass": sum(null.values()),
            "pass_ids": sorted(k for k, v in p.items() if v),
        }
        print(f"{name}: {sum(p.values())}/{len(p)} (cross-item null {sum(null.values())})")
    a.out.write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()

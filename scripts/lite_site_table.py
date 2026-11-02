"""The pre-registered lite-site procedure (plan 0032 §2.6; gpu.md R4d) for the summarize-suffix
siblings association, conjunctive_association and role_bound_association (Camila: "figure out
where it is most commonly held").

A SUPPORT criterion, never a judge outcome: for each position of the read span (as its
``offset_from_end`` k, so items of different lengths pool), count the gold-bearing digest
evidence lines of the ``reads=full`` all-layer runs (a line whose text ``mc.form_in``-matches a
gold form of the item; conjunctive / role_bound: any required unit's form) at that position,
pooled over the three required arms (s3d-rl600, jlens, mlnla-rl2-2000), all items and layers.
``share(k)`` = gold-bearing lines at k / gold-bearing lines in the span. Candidates:
``final_token`` (k=1), the (at most 3) k with the highest pooled share, and role_bound's k=4.
Choice: the highest pooled share; it replaces ``final_token`` only when its share exceeds
``final_token``'s by more than 10 points (ties and smaller wins keep ``final_token``). Pass rates
are reported beside the table by the runbook, never used to choose.

    python scripts/lite_site_table.py --family conjunctive_association \
        --arm s3d=<judged>/conjunctive_association \
        --readouts s3d=<readouts>/conjunctive_association.jsonl \
        --arm jlens=... --readouts jlens=... --arm mlnla=... --readouts mlnla=... \
        [--out table.json] [--write]

``--write`` freezes the chosen rule into ``evals/<family>/lite_rule.json`` (read by readplan; a
lite-rule edit changes neither ``plan_sha`` nor ``bank_sha``, so no re-read and no re-gate)."""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

FAMILIES = ("association", "conjunctive_association", "role_bound_association")
MARGIN = 0.10
EXTRA_CANDIDATE = {"role_bound_association": 4}
_WHERE = re.compile(r"\[L(-?\d+) pos (-?\d+)")


def gold_forms(family: str, item: dict[str, Any]) -> list[str]:
    from wsbench.banks import item_targets

    if family == "association":
        m = item.get("mc")  # bank v2 (plan 0039): the gold option and its listed forms
        if isinstance(m, dict) and m.get("gold"):
            return [str(m["gold"]), *[str(a) for a in m.get("aliases") or []]]
        return [str(x) for x in item_targets(item)]
    if family == "conjunctive_association":
        out: list[str] = []
        for _axis, groups in (item.get("credit") or {}).items():
            for g in groups:
                out += [str(x) for x in (g if isinstance(g, list) else [g])]
        return out
    return [str(item["role_a"]), str(item["role_b"]), str(item["action"])]


def bank_items(family: str) -> dict[str, dict[str, Any]]:
    from wsbench import registry
    from wsbench.banks import load_bank

    path = registry.bank_path(family)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and raw.get("items") and "name" in raw["items"][0]:
        return {it["id"]: it for it in load_bank(path)[1]}
    items = raw["items"] if isinstance(raw, dict) else raw
    return {str(it["id"]): it for it in items}


def max_positions(readouts: Path) -> dict[tuple[str, int], int]:
    """(item, layer) -> the largest position read (the span's end)."""
    out: dict[tuple[str, int], int] = {}
    for line in readouts.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        k = (r["id"], int(r["layer"]))
        out[k] = max(out.get(k, int(r["pos"])), int(r["pos"]))
    return out


def gold_lines_by_k(
    rows: list[dict[str, Any]],
    forms_of: dict[str, list[str]],
    ends: dict[tuple[str, int], int],
) -> Counter[int]:
    """Gold-bearing evidence lines per offset_from_end k for one arm."""
    from wsbench import mc

    out: Counter[int] = Counter()
    for row in rows:
        iid = row.get("id")
        forms = forms_of.get(str(iid), [])
        texts = row.get("summary_evidence") or []
        wheres = row.get("summary_evidence_where") or []
        for text, where in zip(texts, wheres, strict=False):
            m = _WHERE.search(str(where))
            if not m or not forms or not mc.form_in(str(text), forms):
                continue
            layer, pos = int(m.group(1)), int(m.group(2))
            end = ends.get((str(iid), layer))
            if end is None:
                continue
            out[end - pos + 1] += 1
    return out


def table(family: str, per_arm: dict[str, Counter[int]]) -> dict[str, Any]:
    pooled: Counter[int] = Counter()
    for c in per_arm.values():
        pooled.update(c)
    total = sum(pooled.values())

    def share(c: Counter[int], k: int) -> float:
        n = sum(c.values())
        return c[k] / n if n else 0.0

    top = [k for k, _n in sorted(pooled.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
    cands = sorted({1, *top, *([EXTRA_CANDIDATE[family]] if family in EXTRA_CANDIDATE else [])})
    rows = [
        {
            "k": k,
            "rule": {"kind": "final_token"} if k == 1 else {"kind": "offset_from_end", "k": k},
            "pooled_share": share(pooled, k),
            **{f"share_{arm}": share(c, k) for arm, c in sorted(per_arm.items())},
        }
        for k in cands
    ]
    best = max(rows, key=lambda r: (r["pooled_share"], -r["k"]))
    final = next(r for r in rows if r["k"] == 1)
    chosen = best if best["pooled_share"] > final["pooled_share"] + MARGIN else final
    return {
        "family": family,
        "n_gold_lines_pooled": total,
        "candidates": rows,
        "chosen": chosen["rule"],
        "rule": f"highest pooled share; replaces final_token only by > {MARGIN:.0%} absolute",
    }


def _pairs(xs: list[str]) -> dict[str, Path]:
    out = {}
    for x in xs:
        name, _, path = x.partition("=")
        out[name] = Path(path)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--family", required=True, choices=FAMILIES)
    ap.add_argument("--arm", action="append", default=[], help="name=<judged family dir>")
    ap.add_argument("--readouts", action="append", default=[], help="name=<readouts jsonl>")
    ap.add_argument("--out", default="")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    arms, rds = _pairs(a.arm), _pairs(a.readouts)
    if not arms or set(arms) != set(rds):
        print("give --arm and --readouts for the same arm names", file=sys.stderr)
        return 2
    items = bank_items(a.family)
    forms_of = {iid: gold_forms(a.family, it) for iid, it in items.items()}
    per_arm: dict[str, Counter[int]] = defaultdict(Counter)
    for arm, d in arms.items():
        res = json.loads((d / "results.json").read_text(encoding="utf-8"))
        if res.get("config", {}).get("reads", "full") != "full":
            print(f"{arm}: not a reads=full result", file=sys.stderr)
            return 2
        per_arm[arm] = gold_lines_by_k(res.get("rows", []), forms_of, max_positions(rds[arm]))
    t = table(a.family, dict(per_arm))
    text = json.dumps(t, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    if a.write:
        from wsbench.registry import REPO_ROOT

        dst = REPO_ROOT / "evals" / a.family / "lite_rule.json"
        frozen = {"lite_positions": t["chosen"], "procedure": "plan 0032 §2.6", "table": t}
        dst.write_text(json.dumps(frozen, indent=1) + "\n", encoding="utf-8")
        print(f"froze {t['chosen']} -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

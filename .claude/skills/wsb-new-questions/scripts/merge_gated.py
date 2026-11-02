"""Pool several gated waves of one family into one bank and one OOC/cap decision.

    uv run python .claude/skills/wsb-new-questions/scripts/merge_gated.py \\
        --family multihop --out gated/multihop_all gated/multihop gated/multihop_w2 [--capacity N]

Each wave dir is a gate_hf.py output (items.json + summary.json). Candidate and pass counts are
SUMMED across waves before the OOC rule (< 3% over >= min(200, capacity) candidates) is applied,
so small waves add up instead of each being "undetermined". Items are deduplicated by id/name
and by folded prompt (first wave wins); arithmetic null sets are recomputed over the pool.
Writes <out>/items.json (header of the first wave, gate note listing every wave) and
<out>/summary.json (pooled counts, per-wave rows, status).
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_hf import ooc_status
from validate_bank import LIST_BANKS, item_key, norm_prompt, prompt_text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--family", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--capacity", type=int, default=0, help="as for gate_hf.py")
    ap.add_argument(
        "--target",
        type=int,
        default=0,
        help="wanted bank size; with --budget-spent a shortfall is reported as capped",
    )
    ap.add_argument(
        "--budget-spent",
        action="store_true",
        help="no more waves will be gated (wave budget or generator exhausted)",
    )
    ap.add_argument("waves", nargs="+", type=Path, help="gate_hf.py --out dirs, in wave order")
    a = ap.parse_args()
    fam, is_list = a.family, a.family in LIST_BANKS
    header: dict[str, Any] = {}
    kept: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    seen_prompts: set[str] = set()
    rows, n_items, n_pass, dupes = [], 0, 0, 0
    for w in a.waves:
        summ = json.loads((w / "summary.json").read_text(encoding="utf-8"))
        bank = json.loads((w / "items.json").read_text(encoding="utf-8"))
        if summ.get("family") != fam:
            print(f"{w}: summary is for {summ.get('family')!r}, not {fam!r}", file=sys.stderr)
            return 2
        its = bank if isinstance(bank, list) else bank["items"]
        if not is_list and not header:
            header = {k: v for k, v in bank.items() if k != "items"}
        n_items += int(summ["n_items"])
        n_pass += int(summ["n_pass"])
        rows.append({k: summ.get(k) for k in ("n_items", "n_pass", "pass_rate", "n_kept")})
        rows[-1]["wave"] = str(w)
        for it in its:
            k, p = item_key(it), norm_prompt(prompt_text(fam, it), fam)
            if k in seen_keys or (p and p in seen_prompts):
                dupes += 1
                continue
            seen_keys.add(k)
            seen_prompts.add(p)
            kept.append(it)
    if fam == "arithmetic_intermediates":
        from gen_deterministic import null_sets

        names = {re.sub(r"[^A-Za-z0-9._-]", "_", str(it["name"])) for it in kept}
        null_sets(kept)
        for it in kept:
            it["pair_survived"] = it.get("pair") in names
    rate = n_pass / max(1, n_items)
    status = ooc_status(n_items, rate, a.capacity)
    # the unit of the target: buggy counts buggy items (each brings its clean twin along)
    n_unit = sum(it.get("src") != "clean" for it in kept) if fam == "buggy_code" else len(kept)
    if status == "in-capability" and a.target and n_unit < a.target:
        short = f"in-capability, short of target ({n_unit}/{a.target}): gate more or --budget-spent"
        status = f"capped ({n_unit} of target {a.target})" if a.budget_spent else short
    a.out.mkdir(parents=True, exist_ok=True)
    if not is_list:
        header["gate"] = f"{header.get('gate', '')} [pooled over {len(a.waves)} waves]".strip()
    out_bank: Any = kept if is_list else {**header, "items": kept}
    (a.out / "items.json").write_text(
        json.dumps(out_bank, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    summary = {
        "family": fam,
        "pooled": True,
        "n_items": n_items,
        "n_pass": n_pass,
        "pass_rate": round(rate, 4),
        "n_kept": len(kept),
        "dropped_duplicates": dupes,
        "status": status,
        "want_more_candidates_for_100": math.ceil(max(0, 100 - len(kept)) / max(rate, 0.03) * 1.3),
        "waves": rows,
    }
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

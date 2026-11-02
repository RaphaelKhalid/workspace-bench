"""Offline evidence for plan 0045 (introspection), no model and no API call.

``paired`` (default): the source repo's committed per-cell verdicts (s3d.rl600 O-lens and J-lens,
every unit, all 11 layers x the full grid; ``grid_verdicts.json``) and its raw grid readouts
(``grid/shard*.json``) run through THIS repo's v2 scoring code: ``judge.units`` on bank v2,
``judge._row`` (accept sets A(c)), ``judge.pair`` (the gaussian twin's judge leg + the regex leg
``judge.twin_regex`` over the twin's own cells) and ``judge.summarize``. The source verdicts have
no quotes, so the "same as" group check (``quote_options`` inside A(c)) cannot be applied
offline (every quote is taken as naming only the pick); the v2 menu ("also" / "same as") and
rubric only act in the LLM phase. ``--v1`` scores with A(c) = {c} (today's rule).

``--lite-support``: the C2 support check (no judge outcome): for the neutral prompts, the share
of gold-bearing digest evidence lines (``mc.form_in`` over the forms of A(c)) at the final token
vs at ``grid[1]``, per arm and pooled over the ``reads=full`` all-layer summary runs. If
``grid[1]``'s pooled share does not beat the final token's by more than 10 points, the neutral
lite rule becomes ``final_token``.

    uv run --no-sync python scripts/introspection_offline_evidence.py [--out evidence.json]
    uv run --no-sync python scripts/introspection_offline_evidence.py --lite-support \\
        --arm s3d=<judged>/introspection --arm jlens=... --arm mlnla=...
"""

import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from wsbench import mc  # noqa: E402
from wsbench.evals.introspection import judge  # noqa: E402
from wsbench.readouts import Cell  # noqa: E402

SRC = Path("/workspace/gw-introspection-inject")
VERDICTS = (
    SRC / "evals/workspace-bench/hillclimbing_evals/multi_token/introspection_inject/readouts"
    "/grid_verdicts.json"
)
SHARDS = SRC / "outputs/introspection_inject/grid"
MARGIN = 0.10
_WHERE = re.compile(r"\[L(-?\d+) pos (-?\d+)")


# ---------------------------------------------------------------- paired (source verdicts)


def _bank(v1: bool) -> dict[str, Any]:
    bank = judge.load()
    if v1:
        bank = {**bank, "equivalents": {}}
        bank["concepts"] = [
            {**c, "surface_forms": [c["word"]], "extra_forms": []} for c in bank["concepts"]
        ]
    return bank


def _readout_cells(reader: str, ids: set[str], grids: Mapping[str, Sequence[int]]) -> dict:
    out: dict[str, list[Cell]] = defaultdict(list)
    for f in sorted(glob.glob(str(SHARDS / "shard*.json"))):
        for r in json.loads(Path(f).read_text(encoding="utf-8"))["records"]:
            if r["id"] not in ids:
                continue
            grid = set(grids[r["id"]])
            for layer, cols in r[reader].items():
                for p, v in zip(r["positions"], cols, strict=True):
                    if p not in grid:
                        continue
                    if reader == "olens":
                        smp = tuple(v if isinstance(v, list) else [v])
                        out[r["id"]].append(Cell(r["id"], int(layer), int(p), smp, None, None))
                    else:
                        toks = tuple(t if isinstance(t, str) else str(t[0]) for t in v)
                        out[r["id"]].append(Cell(r["id"], int(layer), int(p), None, toks, None))
    return out


def paired(reader: str, *, v1: bool = False, beta: float = 4.0, kind: str = "protocol") -> dict:
    bank = _bank(v1)
    entries = json.loads(VERDICTS.read_text(encoding="utf-8"))["entries"]
    verdicts = {e["item"]: e for e in entries if e["reader"] == reader}
    pool = [
        it
        for it in bank["items"]
        if it["kind"] == "inject" and it["prompt_kind"] == kind and float(it["beta"]) == beta
    ]
    scope = pool + judge._twin_items(bank, pool)
    us = judge.units(bank, scope)
    for u in us:  # the headline flag of this sub-headline (so summarize reports it)
        u["headline"] = u["kind"] == "inject"
    rows = []
    for u in us:
        e = verdicts.get(u["id"])
        if e is None:
            continue
        g = e["regions"]["grid"]
        cells: dict[tuple[int, int], tuple[str, str] | None] = {}
        for pi, pos in enumerate(g["positions"]):
            for li, layer in enumerate(g["layers"]):
                v = g["picks"][pi][li]
                cells[(layer, pos)] = None if v < 0 else (e["options"][v], "")
        rows.append(judge._row(u, cells))
    grids = {u["readout_of"]: bank["renders"][u["render"]]["grid"] for u in us}
    rc = _readout_cells(reader, {u["readout_of"] for u in us}, grids)
    judge.pair(rows, bank, rc)
    s = judge.summarize(rows, list(range(20, 61, 4)))
    key = f"{kind}|b{beta:g}"
    sub = s["subheadlines"][key]
    inj = [r for r in rows if r["kind"] == "inject"]
    return {
        "reader": reader,
        "rule": "v1 (A(c) = {c})" if v1 else "v2 (A(c), Q12)",
        "subheadline": key,
        "n": len(inj),
        "unpaired": sub["unpaired"],
        "paired_judge_only": sub["paired_judge_only"],
        "paired_regex_only": sub["paired_regex_only"],
        "paired": sub["rate"],
        "paired_all_twins": sub["paired_all_twins"],
        "beta0_prior_rate": sub["beta0_prior_rate"],
        "n_twin_missing": sub["n_twin_missing"],
        "floors": {k: s["floors"][key][k] for k in ("beta0", "cross", "gaussian")},
        "unpaired_pass": sorted(r["concept"] for r in inj if r["pass_unpaired"]),
        "voided": [
            {
                "id": r["id"],
                "gaussian_judge": r["twin_hits"]["gaussian"]["judge"],
                "gaussian_regex_quote": r["twin_hits"]["gaussian"]["regex_quote"],
            }
            for r in inj
            if r["pass_unpaired"] and r["pass"] is False
        ],
    }


def cmd_paired(a: argparse.Namespace) -> dict:
    out: dict[str, Any] = {"source_verdicts": str(VERDICTS), "tables": []}
    for reader in ("olens", "jlens"):
        for v1 in (True, False):
            out["tables"].append(paired(reader, v1=v1))
    for t in out["tables"]:
        print(
            f"{t['reader']:6s} {t['rule']:16s} n={t['n']} unpaired={t['unpaired']:.3f} "
            f"judge-only={t['paired_judge_only']:.3f} regex-only={t['paired_regex_only']:.3f} "
            f"PAIRED={t['paired']:.3f} all-twins={t['paired_all_twins']:.3f} "
            f"beta0-prior={t['beta0_prior_rate']:.3f} floors={t['floors']} "
            f"voided={len(t['voided'])}"
        )
    v1o, v2o = out["tables"][0], out["tables"][1]
    v1j, v2j = out["tables"][2], out["tables"][3]
    out["near_duplicate_new_passes"] = {
        "olens": sorted(set(v2o["unpaired_pass"]) - set(v1o["unpaired_pass"])),
        "jlens": sorted(set(v2j["unpaired_pass"]) - set(v1j["unpaired_pass"])),
    }
    print("new unpaired passes from A(c):", out["near_duplicate_new_passes"])
    return out


# ---------------------------------------------------------------- lite support (C2)


def lite_support_table(
    evidence: Mapping[str, Sequence[tuple[str, str]]],
    forms: Mapping[str, Sequence[str]],
    sites: Mapping[str, tuple[int, int]],
) -> dict[str, Any]:
    """One arm's support counts. ``evidence``: readout id -> its digest evidence lines as
    ``(text, where)``; ``forms``: readout id -> the forms of A(c); ``sites``: readout id ->
    ``(final_token_pos, grid1_pos)``. Digests and forms only: a judged row (anything carrying a
    verdict) is refused, so no judge outcome can enter the choice."""
    for rid, lines in evidence.items():
        if isinstance(lines, Mapping) or any(not isinstance(x, tuple | list) for x in lines):
            raise TypeError(f"{rid}: lite support takes digest lines, not judged rows")
        for x in lines:
            if len(x) != 2:
                raise TypeError(f"{rid}: lite support takes (text, where) digest lines")
    final = grid1 = total = 0
    for rid, lines in evidence.items():
        fs = forms.get(rid) or []
        if not fs or rid not in sites:
            continue
        pf, p1 = sites[rid]
        for text, where in lines:
            m = _WHERE.search(str(where))
            if not m or not mc.form_in(str(text), fs):
                continue
            total += 1
            pos = int(m.group(2))
            final += pos == pf
            grid1 += pos == p1
    return {"n_gold_lines": total, "final_token": final, "grid1": grid1}


def choose(per_arm: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
    keys = ("n_gold_lines", "final_token", "grid1")
    tot = {k: sum(int(a[k]) for a in per_arm.values()) for k in keys}
    n = tot["n_gold_lines"]
    sf = tot["final_token"] / n if n else 0.0
    s1 = tot["grid1"] / n if n else 0.0
    keep = s1 > sf + MARGIN
    return {
        "per_arm": dict(per_arm),
        "pooled": {"share_final_token": sf, "share_grid1": s1, **tot},
        "neutral_lite_rule": "grid[1] (bank)" if keep else "final_token",
        "rule": f"grid[1] stays only if its pooled share beats final_token's by > {MARGIN:.0%}",
    }


def _arm_evidence(path: Path) -> tuple[dict, dict, dict]:
    res = json.loads((path / "results.json").read_text(encoding="utf-8"))
    if res.get("config", {}).get("reads", "full") != "full":
        sys.exit(f"{path}: not a reads=full result")
    bank = judge.load()
    items = {it["id"]: it for it in bank["items"]}
    evidence: dict[str, list[tuple[str, str]]] = {}
    forms: dict[str, list[str]] = {}
    sites: dict[str, tuple[int, int]] = {}
    for row in res.get("rows", []):
        it = items.get(str(row.get("id")))
        if it is None or it["kind"] != "inject" or it["prompt_kind"] != "neutral":
            continue
        rid = it["readout_of"]
        texts = row.get("summary_evidence") or []
        wheres = row.get("summary_evidence_where") or []
        evidence[rid] = [(str(t), str(w)) for t, w in zip(texts, wheres, strict=False)]
        forms[rid] = judge.regex_forms(bank, it["concept"])
        grid = bank["renders"][judge.render_key(it)]["grid"]
        sites[rid] = (grid[-1], grid[1])
    return evidence, forms, sites


def cmd_lite_support(a: argparse.Namespace) -> dict:
    per_arm = {}
    for x in a.arm:
        name, _, p = x.partition("=")
        per_arm[name] = lite_support_table(*_arm_evidence(Path(p)))
    out = choose(per_arm)
    print(json.dumps(out, indent=1))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lite-support", action="store_true")
    ap.add_argument("--arm", action="append", default=[], help="name=<judged family dir>")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    out = cmd_lite_support(a) if a.lite_support else cmd_paired(a)
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

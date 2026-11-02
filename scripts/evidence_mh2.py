"""Offline evidence for plan 0041 (multihop_mt removal + multihop_mt_v2 fixes): CPU only, no API
call, cached readouts and the v2 bank only. Writes the evidence files the plan's coverage table
names under ``OUT/evidence/{multihop_mt,multihop_mt_v2}/``.

    uv run --no-sync python scripts/evidence_mh2.py --out OUT [--readouts ROOT]

``ROOT`` holds ``<arm>/multihop_mt_v2.jsonl`` cached final-token readouts (the ``*-x4`` arms,
no sidecar); default the global-workspace ``wsb_latest`` cache.
"""

import argparse
import contextlib
import dataclasses
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from wsbench import digest, readplan, reads, registry
from wsbench.banks import load_bank
from wsbench.judge_config import resolve
from wsbench.multitoken import regex
from wsbench.multitoken.family import _layer_samples, name_credit
from wsbench.multitoken.options import option_sets
from wsbench.readouts import write_sidecar
from wsbench.registry import JudgeArgs

REPO = Path(__file__).resolve().parents[1]
NAME = "multihop_mt_v2"
ARMS = ["rl-onchat-x4", "span8_32-x4", "rl-relverb_p4-x4", "rl-reltree_p4-x4", "rl-relpara_p4-x4"]
DEFAULT_ROOT = Path("/workspace/gw-relational-ar/outputs/wsb_latest/outputs/readouts")
FROZEN = "evals/multihop_mt_v2/items.json"
COEUR = "mh2-coeur-de-lion-brother-charter-q2"
SABRE = "mh2-sabre-dance-ethnicity-t0"
AUDITED = [
    "mh2-kierkegaard-engagement-s1",
    "mh2-rasputin-murderer-s0",
    "mh2-sabre-dance-ethnicity-t0",
    "mh2-bede-ecclesiastical-history-t1",
]


def _args(path: Path, out: Path, **extra: Any) -> JudgeArgs:
    spec = registry.FAMILIES[NAME]
    return JudgeArgs(
        readouts=path, out=out, judge=resolve(spec.judge), layers=None, items=None, limit=0,
        allow_missing=True, concurrency=1, rpm=1.0, dry_run=False,
        extra={"aggregate": "native", **extra},
    )  # fmt: skip


@contextlib.contextmanager
def _bank(path: str | None):
    key = "WSB_BANK_FILE_MULTIHOP_MT_V2"
    old = os.environ.pop(key, None)
    if path:
        os.environ[key] = path
    try:
        yield
    finally:
        os.environ.pop(key, None)
        if old is not None:
            os.environ[key] = old


def regex_rescore(root: Path, tmp: Path) -> tuple[str, dict[str, Any]]:
    """B4: the native regex contract on cached final-token readouts, frozen bank vs bank v2,
    through ``reads.load`` (default sampling ``prose1`` and the ``bullet4`` override), plus
    ``regex_any_length`` (bank v2 ``name_forms``, no token-length filter)."""
    spec = registry.FAMILIES[NAME]
    h2, items2 = load_bank(REPO / "evals/multihop_mt_v2/items_v2.json")
    c2 = regex.contract_for(h2, h2["family"])
    loose = dataclasses.replace(c2, multi_token=False)
    table: dict[str, Any] = {}
    quotes: dict[str, str] = {}
    for arm in ARMS:
        path = root / arm / f"{NAME}.jsonl"
        row: dict[str, Any] = {}
        for label, bank, sampling in (
            ("before", FROZEN, None),
            ("after", None, None),
            ("after_bullet4", None, "bullet4"),
        ):
            extra = {"judge": "regex", **({"sampling": sampling} if sampling else {})}
            with _bank(bank):
                r = spec.run(_args(path, tmp / arm / label, **extra))
            row[label] = {x["id"]: bool(x["pass"]) for x in r.rows}
        # regex_any_length: name_forms, no length filter, same samples
        cells, _rep = reads.load(_args(path, tmp / arm / "al"), NAME)
        by: dict[str, dict[int, list]] = {}
        for c in cells:
            by.setdefault(c.id, {}).setdefault(c.layer, []).append(c)
        anyl = {}
        for it in items2:
            units = [
                dataclasses.replace(u, forms={"en": it["name_forms"][u.role]["en"]})
                if u.role in it["name_forms"]
                else u
                for u in regex.scored_units(it, loose)
            ]
            hits = {
                L: regex.layer_unit_hits(_layer_samples(cs), units, c2)
                for L, cs in by.get(it["id"], {}).items()
            }
            anyl[it["id"]] = bool(regex.item_result(hits, units)["pass"])
        b, a, a4 = row["before"], row["after"], row["after_bullet4"]
        table[arm] = {
            "before": sum(b.values()),
            "after": sum(a.values()),
            "after_bullet4": sum(a4.values()),
            "regex_any_length": sum(anyl.values()),
            "n": len(a),
            "flips": sorted(k for k in a if a[k] and not b[k]),
            "lost": sorted(k for k in a if b[k] and not a[k]),
            "bullet4_differs": sorted(k for k in a if a[k] != a4[k]),
        }
        if arm == "rl-onchat-x4":
            for iid in table[arm]["flips"]:
                quotes[iid] = _hit_quote(path, iid, items2, c2)
    md = ["# B4: regex contract re-score on cached final-token readouts (no API)", ""]
    md.append("| arm | before (frozen bank) | after (bank v2) | after, sampling=bullet4 | "
              "regex_any_length | flips | lost |")  # fmt: skip
    md.append("|---|---|---|---|---|---|---|")
    for arm, t in table.items():
        md.append(
            f"| {arm} | {t['before']}/{t['n']} | {t['after']}/{t['n']} | {t['after_bullet4']}/"
            f"{t['n']} | {t['regex_any_length']}/{t['n']} | {', '.join(t['flips']) or '-'} | "
            f"{', '.join(t['lost']) or '-'} |"
        )
    md += ["", "rl-onchat-x4 flips, the sample that hits (bank v2):", ""]
    for iid, q in quotes.items():
        md.append(f"- `{iid}`: {q}")
    md += ["", "## name_forms / forms_excluded (bank v2)", "", "| item | unit | name_forms | "
           "excluded (reason) |", "|---|---|---|---|"]  # fmt: skip
    for it in items2:
        for u in it["units"]:
            ex = "; ".join(f"{e['form']} ({e['reason']})" for e in u["forms_excluded"]) or "-"
            md.append(
                f"| {it['id']} | {u['role']} | {', '.join(it['name_forms'][u['role']]['en'])} "
                f"| {ex} |"
            )
    return "\n".join(md) + "\n", {"table": table, "quotes": quotes}


def _hit_quote(path: Path, iid: str, items: list, contract: regex.BankContract) -> str:
    it = next(x for x in items if x["id"] == iid)
    units = regex.scored_units(it, contract)
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["id"] != iid:
            continue
        for s in r.get("samples") or []:
            hits = regex.layer_unit_hits([s], units, contract)
            if all(hits.get(u.role) for u in units if u.required):
                f = digest.fold_quote(s)
                for u in units:
                    for form in u.all_forms():
                        k = f.find(form.lower().split()[-1].lower())
                        if k >= 0:
                            return f'L{r["layer"]}: "…{s.strip()[max(0, k - 60) : k + 60]}…"'
    return "(no single sample: hits pooled over the layer's samples)"


def options_md(root: Path) -> tuple[str, dict[str, Any]]:
    _h1, items1 = load_bank(REPO / FROZEN)
    _h2, items2 = load_bank(REPO / "evals/multihop_mt_v2/items_v2.json")
    from wsbench.evals.multihop_mt_v2.prompts import MH2_CANNOT

    o1, o2 = option_sets(items1), option_sets(items2, cannot=MH2_CANNOT)
    out = ["# B2: options, frozen (authored confusables) vs bank v2 (other questions)", ""]
    for iid in (SABRE, COEUR):
        for role in o2[iid]:
            out.append(f"## {iid} {role}")
            out.append(f"- old: {o1[iid][role][0]}")
            out.append(f"- new: {o2[iid][role][0]}")
            out.append("")
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts/build_mh2_bank_v2.py"), "--report",
         str(root / "rl-onchat-x4" / f"{NAME}.jsonl")],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    cm = json.loads(proc.stdout)
    out.append(
        f"Co-mention on cached rl-onchat-x4 readouts (a non-gold option itself named in the "
        f"item's readouts; diagnostic only, never used to tune): old "
        f"{cm['old']['n_units_with_named_distractor']}/{cm['old']['n_units']}, new "
        f"{cm['new']['n_units_with_named_distractor']}/{cm['new']['n_units']}."
    )
    return "\n".join(out) + "\n", {
        k: cm[k]["n_units_with_named_distractor"] for k in ("old", "new")
    }


def positions_md(root: Path, tmp: Path) -> tuple[str, dict[str, Any]]:
    plan = {s.id: s for s in readplan.plan(NAME)}
    s = plan[COEUR]
    lite = {x.id: x for x in readplan.plan(NAME, reads="lite")}[COEUR]
    toks = [f"t{i}" for i in range(42)]
    full_pos = readplan.resolve(s.positions, toks)
    lite_pos = readplan.resolve(lite.positions, toks)
    out = ["# B1: every prompt token (lite: the final token)", "", "```json",
           json.dumps(s.row(), ensure_ascii=False, indent=1), "```", ""]  # fmt: skip
    out.append(f"full positions: {len(full_pos)} ({full_pos[0]}..{full_pos[-1]}) x "
               f"{len(s.layers)} layers {s.layers}; lite positions: {lite_pos}")  # fmt: skip
    # the cached final-token file: report-only without a sidecar, exit 2 with a lite sidecar
    path = root / "rl-onchat-x4" / f"{NAME}.jsonl"
    _cells, rep = reads.load(_args(path, tmp / "pos"), NAME)
    out.append("")
    n_unenforced = len(rep.partial_ids_unenforced)
    out.append(
        f"cached rl-onchat-x4 final-token file under reads=full: reads_checked="
        f"{rep.reads_checked}, partial_ids_unenforced={n_unenforced}"
    )
    copy = tmp / "lite_sidecar.jsonl"
    copy.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    write_sidecar(copy, reads="lite", sampling="bullet4", reader="rl-onchat-x4")
    err = io.StringIO()
    code = None
    with contextlib.redirect_stderr(err):
        try:
            reads.load(_args(copy, tmp / "pos2"), NAME)
        except SystemExit as e:
            code = e.code
    out.append(f"the same file with a `reads: lite` sidecar under reads=full: exit {code} "
               f"({err.getvalue().strip()})")  # fmt: skip
    return "\n".join(out) + "\n", {
        "n_full_positions": len(full_pos),
        "lite": lite_pos,
        "reads_checked": rep.reads_checked,
        "n_partial_unenforced": len(rep.partial_ids_unenforced),
        "lite_sidecar_exit": code,
    }


def fuzzy_md() -> str:
    _h, items = load_bank(REPO / "evals/multihop_mt_v2/items_v2.json")
    it = next(x for x in items if x["id"] == SABRE)
    nf = it["name_forms"]["bridge1"]["en"]
    full = it["units"][0]["full_forms"]
    rows = []
    for q in ("Khatchaturian ethn", "Khachaturian", "Aram Khachaturian", "Khanjian", "Kachalov"):
        rows.append(
            f"| {q} | {name_credit(q, full_forms=full, name_forms=nf, fuzzy=True)} | "
            f"{name_credit(q, full_forms=full, name_forms=full, fuzzy=False)} |"
        )
    return (
        "# B5: misspelt names\n\n| quote | bank v2 credit | frozen-bank contract |\n|---|---|---|\n"
        + "\n".join(rows)
        + "\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--readouts", type=Path, default=DEFAULT_ROOT)
    a = ap.parse_args()
    registry.load_all()
    ev1, ev2 = a.out / "evidence/multihop_mt", a.out / "evidence/multihop_mt_v2"
    ev1.mkdir(parents=True, exist_ok=True)
    ev2.mkdir(parents=True, exist_ok=True)
    tmp = a.out / "evidence/_tmp"
    tmp.mkdir(exist_ok=True)
    summary: dict[str, Any] = {}
    # 1. removal
    lst = subprocess.run([sys.executable, "-m", "wsbench", "list"], capture_output=True,
                         text=True, cwd=REPO).stdout  # fmt: skip
    rows = [ln for ln in lst.splitlines() if "multihop" in ln]
    from wsbench.results import macro

    removed = registry.REMOVED_FAMILIES["multihop_mt"]
    m = macro([_res("multihop_mt", 0.9), _res(NAME, 0.2)])
    (ev1 / "removal.txt").write_text(
        "wsbench list rows naming multihop:\n" + "\n".join(rows) + "\n\n"
        f"REMOVED_FAMILIES['multihop_mt'] = {removed!r}\n"
        f"macro over an old run dir holding multihop_mt + multihop_mt_v2 results: families "
        f"{m['families']}, excluded {m['excluded']}\n",
        encoding="utf-8",
    )
    summary["removal"] = {"list_rows": rows, "excluded": m["excluded"]}
    # 2-6
    text, summary["positions"] = positions_md(a.readouts, tmp)
    (ev2 / "positions.md").write_text(text, encoding="utf-8")
    text, summary["options"] = options_md(a.readouts)
    (ev2 / "options.md").write_text(text, encoding="utf-8")
    from wsbench.baselines import text_inversion as ti

    (ev2 / "ati_skip.txt").write_text(
        f"NOT_GATED['{NAME}'] = {ti.NOT_GATED[NAME]!r}\n"
        f"in gated_families(): {NAME in ti.gated_families()}\n",
        encoding="utf-8",
    )
    text, summary["regex"] = regex_rescore(a.readouts, tmp)
    (ev2 / "regex_rescore.md").write_text(text, encoding="utf-8")
    (ev2 / "fuzzy.md").write_text(fuzzy_md(), encoding="utf-8")
    (a.out / "evidence/multihop_mt_v2/summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["regex"]["table"], indent=1))
    return 0


def _res(family: str, value: float) -> Any:
    from wsbench.results import FamilyResult

    return FamilyResult(
        family=family, metric="pass_rate", value=value, ci95=None, n_items=1,
        higher_is_better=True, chance=None, chance_label="", complete=True,
        pinned_instrument=True, config={}, counts={}, extras={}, rows=[],
    )  # fmt: skip


if __name__ == "__main__":
    raise SystemExit(main())

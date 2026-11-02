"""Re-judge the audit's moral_rationale cases verbatim under ec-v4 (plan 0046 §2.6, §5 E2/E5).

Native cases (L1-L6, the too-strict guard, the §4.1 deepfake / donor cases) are re-judged on
the cached readout cell itself (the s3d-rl600 / ML-NLA / J-lens readouts the audit judged; the
J-lens cell as its RAW token list, no interpretation step), once over the v1 options under ec-v4
(``WSB_BANK_FILE_MORAL_RATIONALE=items.json opts=prompts=ec-v4``) and once over the bank-v2
options. L7 is a summary-mode case: the cached digest of ``d3b-s3d-all-summary-v2`` re-rendered
with the bullet mark (``digest.sample_text``) and judged under ec-v4 with the quote gate on its
evidence lines. Every verdict goes through ``judge.run`` / ``judge._row`` (the real instrument,
quote gate included). Writes ``--out`` JSON with before (audit) and after picks and the expected
outcome; exits 1 when an expectation fails.

    ANTHROPIC_AUTH_TOKEN=... python scripts/moral_rejudge_cases.py --out <file.json>
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from wsbench import digest
from wsbench.cache import Cache
from wsbench.evals.moral_rationale import judge as mr
from wsbench.evals.moral_rationale import prompts as mrp
from wsbench.judge_config import JudgeConfig, resolve
from wsbench.llm import Spend
from wsbench.mcjudge import Call, load_bank, run_calls
from wsbench.readouts import Cell
from wsbench.registry import JudgeArgs

AUDIT = Path("/workspace/root/wsb-audit-artifact/families/moral_rationale.json")
READOUTS = {
    "s3d": Path("/workspace/root/wsbench-pub/outputs/readouts/s3d-rl600/moral_rationale.jsonl"),
    "mlnla": Path("/workspace/root/wsb-ati-runs/readouts/mlnla2k/moral_rationale.jsonl"),
    "jlens": Path("/workspace/root/wsb-ati-runs/readouts/jlens/moral_rationale.jsonl"),
}
SUMMARY_RUN = Path("/workspace/root/wsb-summ-out/d3/d3b-s3d-all-summary-v2/moral_rationale")
V1 = "evals/moral_rationale/items.json"
OK_AFTER = {"cannot_tell", "unverified"}

# (name, readouts, id, layer, pos, v1 side, before, allowed after, what the case is)
CASES: list[tuple[str, str, str, int, int, str, str, set[str], str]] = [
    ("L1", "s3d", "ec-conjoined_twins_separation-chat_yn", 20, 32, "no", "gold", OK_AFTER,
     "deliberative side, a principle named without reason or conclusion (rule b, stance rule)"),
    ("L2", "mlnla", "ec-conjoined_twins_separation-chat_tf", 40, 37, "no", "gold", OK_AFTER,
     "restates the dilemma (rule a)"),
    ("L3", "jlens", "ec-sex_selection_ivf-chat_yn", 60, 34, "no", "gold", OK_AFTER,
     "one sub-token ' commod' plus generic ethics tokens (rule e; no interpretation step)"),
    ("L4", "s3d", "ec-disinherit_for_marriage-chat_yn", 52, 32, "committed", "contrast", OK_AFTER,
     "a heading names a consideration without a conclusion (rule b on every option)"),
    ("L5", "s3d", "ec-support_abusive_parent-chat_yn", 56, 35, "committed", "gold",
     OK_AFTER | {"same_side"}, "drifted to a neighbouring question (rule d, same-topic options)"),
    ("L6", "s3d", "ec-footbridge-chat_tf", 24, 39, "committed", "distractor",
     OK_AFTER | {"gold", "opposite", "same_side", "distractor"},
     "concession-phrased contrast option (v2 has none; any verdict recorded)"),
    ("guard", "s3d", "ec-obligation_lab_grown_meat-chat_tf", 40, 39, "committed", "gold", {"gold"},
     "the audit's correct hard case must stay gold (too-strict guard, v1 options)"),
    ("E2-deepfake", "s3d", "ec-deepfake_political_satire-chat_tf", 36, 35, "committed", "gold",
     OK_AFTER | {"opposite", "same_side"}, "explanation-side stance credited to the v1 gold"),
    ("E2-donor", "s3d", "ec-donor_anonymity_disclosure-chat_yn", 36, 39, "committed", "gold",
     OK_AFTER | {"opposite", "same_side"}, "explanation-side stance credited to the v1 gold"),
]  # fmt: skip


def _cell(src: str, iid: str, layer: int, pos: int) -> dict:
    with READOUTS[src].open(encoding="utf-8") as fh:
        for line in fh:
            if f'"{iid}"' not in line:
                continue
            r = json.loads(line)
            if r["id"] == iid and r["layer"] == layer and r["pos"] == pos:
                return r
    raise SystemExit(f"{src}: no cell {iid} L{layer} p{pos}")


def _args(path: Path, out: Path, extra: dict[str, str]) -> JudgeArgs:
    return JudgeArgs(
        readouts=path,
        out=out,
        judge=resolve(JudgeConfig(prompt_version=mrp.PROMPT_VERSION), env=os.environ),
        layers=None,
        items=None,
        limit=0,
        allow_missing=True,
        concurrency=8,
        rpm=1000.0,
        dry_run=False,
        extra={"aggregate": "native", "reads": "lite", **extra},
    )


def _judge_native(row: dict, side: str, bank: str, tmp: Path) -> dict[str, Any] | None:
    path = tmp / f"{bank}-{row['id']}-{row['layer']}-{row['pos']}.jsonl"
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    extra = {"prompts": mrp.PROMPT_VERSION} if bank == "v1" else {}
    if bank == "v1":
        os.environ["WSB_BANK_FILE_MORAL_RATIONALE"] = V1
    else:
        os.environ.pop("WSB_BANK_FILE_MORAL_RATIONALE", None)
    try:
        ids = {it["id"] for it in load_bank("moral_rationale")}
        if row["id"] not in ids:
            return None
        args = _args(path, tmp / f"out-{bank}-{row['id']}-{row['layer']}", extra)
        args.items = [row["id"]]
        res = mr.run(args)
    finally:
        os.environ.pop("WSB_BANK_FILE_MORAL_RATIONALE", None)
    rows = res.rows
    pick = next((r for r in rows if r["side"] == side), None) or (rows[0] if rows else None)
    return None if pick is None else {k: pick[k] for k in ("side", "pick", "picked", "quote",
                                                          "quote_check", "choice")}  # fmt: skip


def _l7(bank: str, out: Path) -> dict[str, Any] | None:
    """The cached digest re-rendered with the bullet mark, judged under ec-v4 + the quote gate."""
    res = json.loads((SUMMARY_RUN / "results.json").read_text(encoding="utf-8"))
    (row,) = [r for r in res["rows"] if r["id"] == "ec-silence_versus_lie-chat_yn"]
    lines, cells = [], []
    for k, (txt, where) in enumerate(
        zip(row["summary_evidence"], row.get("summary_evidence_where") or [""] * 99, strict=False)
    ):
        bullets = [b.strip() for b in ("\n" + txt).split("\n- ") if b.strip()]
        bullets = [p.strip() for b in bullets for p in b.split(" - ") if p.strip()]
        sample = "\n".join(f"- {b}" for b in bullets)
        lines.append(digest.Line(digest.sample_text(sample), None, where, 0, k))
        cells.append(Cell(row["id"], 0, k, (sample,), None, None))
    summary = "\n".join(f"[{'one'}] {ln.text}" for ln in lines)
    if bank == "v1":
        os.environ["WSB_BANK_FILE_MORAL_RATIONALE"] = V1
    try:
        bank_items = {it["id"]: it for it in load_bank("moral_rationale")}
        it = bank_items.get(row["id"])
        if it is None:
            return None
        pools = mr.build_pools(list(bank_items.values())) if bank == "v1" else ([], [], [])
        mcs = mr.build_mcs(it, *pools, version=mrp.PROMPT_VERSION)
    finally:
        os.environ.pop("WSB_BANK_FILE_MORAL_RATIONALE", None)
    side, m = next(iter(mcs.items()))
    note = digest.SUMMARY_NOTE
    call = Call(f"L7:{bank}", mrp.SYSTEM, mrp.render_user_summary(note, summary, m.question), {})
    judge = resolve(JudgeConfig(prompt_version=mrp.PROMPT_VERSION), env=os.environ)
    with Cache(out / f"l7-{bank}.jsonl") as cache:
        r = run_calls(
            [call], schema=mrp.SCHEMA, judge=judge, prompt_version=mrp.PROMPT_VERSION,
            cache=cache, spend=Spend(), concurrency=1, rpm=100.0, dry_run=False, preflight=None,
        ).get(call.key)  # fmt: skip
    if r is None:
        return None
    meta = {"id": row["id"], "layer": -1, "pos": 0, "side": side, "gold_pos": m.gold_pos,
            "n_options": len(m.shown), "short_pool": m.short_pool,
            "contrast_pos": m.contrast_pos}  # fmt: skip
    v = mr._row(call.key, meta, r, it, m, (lines, cells))
    return {k: v[k] for k in ("side", "pick", "picked", "quote", "quote_check", "choice")} | {
        "digest_line_before": row["summary_evidence"][0][:240],
        "digest_line_after": lines[0].text[:240],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    audit = {
        c["item_id"]: c for c in json.loads(AUDIT.read_text(encoding="utf-8"))["audit"]["cases"]
    }
    out: list[dict[str, Any]] = []
    failed = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name, src, iid, layer, pos, side, before, allowed, what in CASES:
            row = _cell(src, iid, layer, pos)
            rec: dict[str, Any] = {
                "case": name, "readouts": src, "id": iid, "layer": layer, "pos": pos,
                "side": side, "before": before, "allowed_after": sorted(allowed), "what": what,
                "audit_quote": (audit.get(iid) or {}).get("judge_raw"),
            }  # fmt: skip
            for bank in ("v1", "v2"):
                rec[f"after_{bank}"] = _judge_native(row, side, bank, tmp)
            # L1-L5: the audit's v1 lists under ec-v4; the guard and the E2 cases: the bank of
            # record (v2; the E2 golds were the v1 defect itself, so only v2 can fix them). L6
            # records whatever verdict (its v1 option was ill-defined).
            bank = "v2" if name == "guard" or name.startswith("E2") else "v1"
            after = (rec[f"after_{bank}"] or {}).get("pick")
            rec["checked_bank"] = bank
            if name != "L6" and after is not None and after not in allowed:
                failed.append(name)
            v1_after = (rec["after_v1"] or {}).get("pick")
            out.append(rec)
            print(name, iid, "v1:", v1_after, "v2:", (rec["after_v2"] or {}).get("pick"))
        rec = {
            "case": "L7",
            "id": "ec-silence_versus_lie-chat_yn",
            "before": "gold",
            "allowed_after": sorted(OK_AFTER),
            "what": "quote taken from a line whose own conclusion opposes the gold (rule f)",
        }
        for bank in ("v1", "v2"):
            rec[f"after_{bank}"] = _l7(bank, a.out.parent)
        if (rec["after_v1"] or {}).get("pick") not in OK_AFTER:
            failed.append("L7")
        out.append(rec)
        print(
            "L7 v1:",
            (rec["after_v1"] or {}).get("pick"),
            "v2:",
            (rec["after_v2"] or {}).get("pick"),
        )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"cases": out, "failed": failed}, indent=1, ensure_ascii=False))
    print(f"wrote {a.out}; expectation failures: {failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

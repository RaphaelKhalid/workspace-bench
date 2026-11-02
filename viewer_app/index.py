"""Read-only data index for the WorkspaceBench viewer: banks, runs (subject x stage), scores,
per-item verdicts and byte-offset readout/cell indexes, cached by file mtime (see README.md)."""

import csv
import functools
import json
import pickle
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

AGAM = Path("/workspace/agam")
WSB = AGAM / "workspace-bench"
sys.path.insert(0, str(WSB / "src"))
from wsbench.viewer.build import GROUPS, _family_view, _header, _items, _read_gates  # noqa: E402
from wsbench.viewer.build import view_item as view_item_full  # noqa: E402,F401
from wsbench.registry import REMOVED_FAMILIES, RETIRED_FAMILIES  # noqa: E402

CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_FILE = CACHE_DIR / "index.pkl"
CACHE_VERSION = 3

ORIGINAL = "qwen3.6-27b"
FAMILY_ORDER = [f for _, fams in GROUPS for f in fams]
FAMILY_GROUP = {f: g for g, fams in GROUPS for f in fams}
EXTRA_FAMILIES: list[str] = []

MODEL_LABELS = {
    "qwen3.6-27b": "Qwen3.6-27B",
    "qwen3.5-0.8b": "Qwen3.5-0.8B",
    "qwen3.5-2b": "Qwen3.5-2B",
    "qwen3.5-4b": "Qwen3.5-4B",
    "qwen3.5-9b": "Qwen3.5-9B",
    "olmo-3-7b": "OLMo-3-7B-Instruct",
    "olmo-3.1-32b": "OLMo-3.1-32B-Instruct",
    "gemma-4-31b-it": "Gemma-4-31B-it",
    "qwen3.6-35b-a3b": "Qwen3.6-35B-A3B",
    "kimi-k2": "Kimi-K2 reader (Kimi-Linear-48B)",
    "glm-5.3-flash": "GLM-5.3-Flash",
    "qwen3-8b": "Qwen3-8B",
}
MODEL_ALIAS = {
    "olmo-3-7b-instruct": "olmo-3-7b",
    "olmo-3.1-32b-instruct": "olmo-3.1-32b",
    "kimi-k2-instruct-0905": "kimi-k2",
    "olmo7": "olmo-3-7b",
    "olmo32": "olmo-3.1-32b",
    "kimi": "kimi-k2",
    "qwen": "qwen3.6-35b-a3b",
    "glm": "glm-5.3-flash",
}

STAGES = [
    ("floor", "prompt-only floor"),
    ("inverter", "inverter"),
    ("distill", "distill (student / SFT)"),
    ("rl", "RL"),
    ("j-lens", "J-lens"),
    ("logit-lens", "logit lens"),
    ("ar-jlogit", "J-head AR (jlogit)"),
    ("nla", "NLA-RL"),
    ("sae", "SAE"),
    ("ao", "AO"),
    ("smoke", "smoke run"),
    ("judge-audit", "judge audit (synthetic gold / foil / irrelevant readouts)"),
]
STAGE_LABEL = dict(STAGES)
DIAGNOSTIC_STAGES = {"smoke", "judge-audit"}


def model_label(key: str) -> str:
    return MODEL_LABELS.get(key, key)


def stage_of_tag(tag: str) -> str:
    t = tag.lower()
    if ".rl." in t or t.startswith("rl.") or ".rl_" in t:
        return "rl"
    if "distill" in t or ".sft" in t:
        return "distill"
    if ".inv" in t or "inv_" in t or ".ao." in t or "step" in t:
        return "inverter"
    return "inverter"


def fam_sort_key(f: str) -> tuple:
    return (FAMILY_ORDER.index(f) if f in FAMILY_ORDER else 999, f)


# --------------------------------------------------------------------------------------------
# Per-file parsers (cached by mtime/size)
# --------------------------------------------------------------------------------------------

_ID_RE = re.compile(r'"id":\s*"((?:[^"\\]|\\.)*)"')
_LAYER_RE = re.compile(r'"layer":\s*(-?\d+)')
_POS_RE = re.compile(r'"pos":\s*(-?\d+)')
_KEY_RE = re.compile(r'"key":\s*"((?:[^"\\]|\\.)*)"')
_KEY_L = re.compile(r"(?:\||__)L0*(\d+)")
_KEY_P = re.compile(r"(?:\||__)p(-?\d+)")


def _unescape(s: str) -> str:
    return json.loads(f'"{s}"') if "\\" in s else s


def parse_readouts(path: Path) -> dict:
    """{items: {id: [[offset, length, layer, pos], ...]}, layers: [...], n: rows}"""
    items: dict[str, list] = {}
    layers: set[int] = set()
    n = 0
    with open(path, "rb") as fh:
        off = 0
        for raw in fh:
            ln = len(raw)
            line = raw.decode("utf-8", "replace")
            if line.strip():
                m = _ID_RE.search(line[:400])
                lm = _LAYER_RE.search(line[:600])
                pm = _POS_RE.search(line[:600])
                if m is None:
                    try:
                        rec = json.loads(line)
                        iid, lay, pos = str(rec.get("id")), rec.get("layer"), rec.get("pos")
                    except Exception:
                        off += ln
                        continue
                else:
                    iid = _unescape(m.group(1))
                    lay = int(lm.group(1)) if lm else None
                    pos = int(pm.group(1)) if pm else None
                items.setdefault(iid, []).append([off, ln, lay, pos])
                if isinstance(lay, int):
                    layers.add(lay)
                n += 1
            off += ln
    return {"items": items, "layers": sorted(layers), "n": n}


def cell_item_id(key: str) -> str:
    return re.split(r"\||__", key, maxsplit=1)[0]


def parse_cells(path: Path) -> dict:
    """{items: {id: [[offset, length, layer, pos], ...]}, n}. Item id = cell key before | or __."""
    items: dict[str, list] = {}
    n = 0
    with open(path, "rb") as fh:
        off = 0
        for raw in fh:
            ln = len(raw)
            line = raw.decode("utf-8", "replace")
            m = _KEY_RE.search(line[:600])
            if m:
                key = _unescape(m.group(1))
                lm, pm = _KEY_L.search(key), _KEY_P.search(key)
                items.setdefault(cell_item_id(key), []).append(
                    [off, ln, int(lm.group(1)) if lm else None, int(pm.group(1)) if pm else None]
                )
                n += 1
            off += ln
    return {"items": items, "n": n}


def row_item_id(r: dict) -> str | None:
    for k in ("id", "item"):
        v = r.get(k)
        if isinstance(v, str | int):
            return str(v)
    if isinstance(r.get("key"), str):
        return cell_item_id(r["key"])
    return None


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    return float(v)


def row_pass(r: dict) -> bool | None:
    for k in ("pass", "correct", "hit", "any_recognition", "asserts_misaligned_plan"):
        v = r.get(k)
        if isinstance(v, bool):
            return v
        if isinstance(v, list) and v and all(isinstance(x, bool) for x in v):
            return all(v)
    if "pick" in r and "gold_position" in r and not r.get("voided"):
        return r["pick"] == r["gold_position"]
    return None


def row_score(r: dict) -> float | None:
    for k in ("score", "design_item_score"):
        v = _num(r.get(k))
        if v is not None:
            return v
    return None


def compact_rows(rows: list[dict]) -> dict:
    """One verdict per item: pass/n_pass/n_rows, mean score, per-layer pass."""
    passes = [p for p in (row_pass(r) for r in rows) if p is not None]
    scores = [s for s in (row_score(r) for r in rows) if s is not None]
    by_layer: dict[int, bool] = {}
    earliest = None
    for r in rows:
        p = row_pass(r)
        lay = r.get("layer")
        if isinstance(lay, str) and lay.lstrip("-").isdigit():
            lay = int(lay)
        if isinstance(lay, int) and p is not None:
            by_layer[lay] = by_layer.get(lay, False) or p
        layers = r.get("layers")
        if isinstance(layers, dict):
            passing = r.get("passing_layers")
            for k, v in layers.items():
                try:
                    li = int(k)
                except (TypeError, ValueError):
                    continue
                if isinstance(passing, list):
                    by_layer[li] = by_layer.get(li, False) or (li in passing or str(li) in passing)
                elif isinstance(v, dict) and isinstance(v.get("expressed"), bool):
                    by_layer[li] = by_layer.get(li, False) or v["expressed"]
        el = r.get("earliest_layer")
        if isinstance(el, int):
            earliest = el if earliest is None else min(earliest, el)
    out: dict[str, Any] = {"n": len(rows)}
    if passes:
        out["n_pass"] = sum(passes)
        out["n_judged"] = len(passes)
        out["pass"] = passes[0] if len(passes) == 1 else None
    if scores:
        out["score"] = sum(scores) / len(scores)
    if by_layer:
        out["by_layer"] = by_layer
    if earliest is not None:
        out["earliest"] = earliest
    return out


def compact_result_rows(rows: list[dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if isinstance(r, dict) and (iid := row_item_id(r)) is not None:
            groups.setdefault(iid, []).append(r)
    return {iid: compact_rows(rs) for iid, rs in groups.items()}


def _numbers_entry(d: dict) -> dict:
    num = d.get("numbers") or {}
    counts = d.get("counts") or {}
    return {
        "value": num.get("value"),
        "ci95": num.get("ci95"),
        "metric": num.get("metric"),
        "higher_is_better": num.get("higher_is_better", True),
        "chance": num.get("chance"),
        "n": d.get("n_items"),
        "complete": d.get("complete"),
        "judge": (d.get("config") or {}).get("judge_model"),
        "layers": (d.get("config") or {}).get("layers_judged"),
        "n_missing": counts.get("n_missing_cells"),
        "n_unjudged": counts.get("n_unjudged_cells"),
        "n_no_readouts": ((num.get("extras") or {}).get("n_items_without_readouts")),
    }


def parse_results(path: Path) -> dict:
    d = json.loads(path.read_text())
    return {"score": _numbers_entry(d), "verdicts": compact_result_rows(d.get("rows") or [])}


def parse_audit_res(path: Path) -> dict:
    """outputs/audit-*/judge/res_<fam>.json: {runs: {"<arm>|<judge>": {value, metric, rows}}}."""
    d = json.loads(path.read_text())
    out = {}
    for key, run in (d.get("runs") or {}).items():
        if not isinstance(run, dict) or "rows" not in run:
            continue
        rows = run.get("rows") or []
        out[key] = {
            "score": {
                "value": run.get("value"),
                "metric": run.get("metric"),
                "n": len({row_item_id(r) for r in rows if isinstance(r, dict)}),
                "higher_is_better": True,
                "judge": key.split("|", 1)[-1],
            },
            "verdicts": compact_result_rows(rows),
        }
    return out


def _bank_items_raw(path: Path) -> list[dict]:
    return _items(json.loads(path.read_text()))


def parse_bank(path: Path, gate_path: Path | None) -> dict:
    """Light per-item summary rows for the family list (full view is re-read on the item page)."""
    raw = json.loads(path.read_text()) if path.exists() else {}
    gates = _read_gates(gate_path) if (gate_path is not None and not path.exists()) else None
    rows = _family_view(_items(raw), _header(raw), gates)
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "selected": r["selected"],
                "origin": r["origin"],
                "subfamily": None if r["subfamily"] is None else str(r["subfamily"]),
                "target": [str(t)[:80] for t in r["target"][:4]],
                "latent": [str(t)[:60] for t in r["latent"][:4]],
                "stim": (r["stimulus"] or "")[:220],
            }
        )
    return {"items": out, "frozen": path.exists()}


def parse_plan(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            out[str(rec.get("id"))] = {k: v for k, v in rec.items() if k not in ("family", "id")}
    return out


# --------------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------------


def _rel(p: Path) -> str:
    return str(p)


def discover() -> dict:
    """Walk the known locations and return the raw spec (no heavy parsing)."""
    banks: dict[str, dict] = {}
    # frozen 27B banks
    fams = {}
    for d in sorted((WSB / "evals").iterdir()):
        if (d / "items.json").exists():
            fams[d.name] = {"bank": str(d / "items.json"), "gate": None}
        elif d.is_dir() and d.name in FAMILY_ORDER:
            fams[d.name] = {"bank": None, "gate": None, "dir": str(d)}
    banks[ORIGINAL] = {
        "key": ORIGINAL,
        "label": "Qwen3.6-27B (frozen banks, evals/)",
        "root": str(WSB / "evals"),
        "families": fams,
        "report": {},
        "plans": {},
    }
    for mdir in sorted(
        p for p in (WSB / "adapted").iterdir() if p.is_dir() and not p.name.startswith(".")
    ):
        report = {}
        if (mdir / "report.json").exists():
            report = json.loads((mdir / "report.json").read_text())
        fams = {}
        names = set(FAMILY_ORDER) | {p.stem for p in mdir.glob("*.json")}
        for fam in sorted(names, key=fam_sort_key):
            if fam in ("report",) or fam.endswith("capture_rows"):
                continue
            bank, gate = mdir / f"{fam}.json", mdir / "gate" / f"{fam}.jsonl"
            if bank.exists() or gate.exists():
                fams[fam] = {
                    "bank": str(bank) if bank.exists() else None,
                    "gate": str(gate) if gate.exists() else None,
                }
            elif (mdir / fam).is_dir():
                fams[fam] = {"bank": None, "gate": None, "dir": str(mdir / fam)}
        plans = {}
        tag = mdir.name.split("-")[-1]  # qwen3.5-4b -> 4b
        pdir = WSB / "outputs" / f"audit-{tag}" / "plan"
        if pdir.is_dir():
            plans = {p.stem: str(p) for p in pdir.glob("*.jsonl")}
        banks[mdir.name] = {
            "key": mdir.name,
            "label": f"{report.get('label') or model_label(mdir.name)} (adapted/{mdir.name})",
            "root": str(mdir),
            "families": fams,
            "report": {k: v for k, v in report.items() if k != "patches"},
            "plans": plans,
        }

    runs: list[dict] = []

    def add_run(**kw):
        kw.setdefault("families", {})
        kw.setdefault("headline", None)
        kw.setdefault("notes", "")
        runs.append(kw)

    # 1. prompt-only floors: adapted/<m>/floors/{readouts,results}
    for mdir in sorted(p for p in (WSB / "adapted").iterdir() if not p.name.startswith(".")):
        fl = mdir / "floors"
        if not fl.is_dir():
            continue
        fams = {}
        for rdir in sorted((fl / "results").glob("*")):
            f = rdir.name
            fams[f] = {
                "results": str(rdir / "results.json") if (rdir / "results.json").exists() else None,
                "cells": str(rdir / "cells.jsonl") if (rdir / "cells.jsonl").exists() else None,
                "readouts": str(fl / "readouts" / f"{f}.jsonl")
                if (fl / "readouts" / f"{f}.jsonl").exists()
                else None,
            }
        for ro in sorted((fl / "readouts").glob("*.jsonl")):
            fams.setdefault(ro.stem, {"results": None, "cells": None, "readouts": str(ro)})
        floors_json = None
        if (fl / "floors.json").exists():
            floors_json = str(fl / "floors.json")
        add_run(
            id=f"floor.{mdir.name}",
            subject=mdir.name,
            stage="floor",
            tag="prompt-only floor",
            bank=mdir.name,
            source=str(fl),
            judge="claude-opus-5-5",
            files=fams,
            floors_json=floors_json,
            notes="stock subject reads its own prompt (k=1, T=1.0); one layer; complete=false by construction",
        )

    # 2. OLens tags pulled to olens_ckpts/<subject>/wsb/<tag>/summary_opus.json (27B bank, ported)
    for sdir in sorted(AGAM.glob("olens_ckpts/*/wsb/*")):
        if not (sdir / "summary_opus.json").exists() and not (sdir / "summary.json").exists():
            continue
        subj = MODEL_ALIAS.get(sdir.parts[-3], sdir.parts[-3])
        tag = sdir.name
        hal = tag.endswith(".hal_onpolicy")
        base = tag[: -len(".hal_onpolicy")] if hal else tag
        # .adapt.<sha8> tags were scored on the subject's adapted bank (adapted/<subject dir>)
        adapt = ".adapt." in base
        adir = sdir.parts[-3] if (WSB / "adapted" / sdir.parts[-3]).is_dir() else subj
        # per-item files when pulled with `pull_olens_ckpts.py --items`: readouts/<fam>.jsonl and
        # judged_opus/<fam>[_opus]/{results.json,cells.jsonl}
        files: dict = {}
        for ro in sorted((sdir / "readouts").glob("*.jsonl")):
            files[ro.stem] = {"results": None, "cells": None, "readouts": str(ro)}
        for jd in sorted((sdir / "judged_opus").glob("*")):
            if not jd.is_dir():
                continue
            fam = jd.name[: -len("_opus")] if jd.name.endswith("_opus") else jd.name
            e = files.setdefault(fam, {"results": None, "cells": None, "readouts": None})
            e["results"] = str(jd / "results.json") if (jd / "results.json").exists() else None
            e["cells"] = str(jd / "cells.jsonl") if (jd / "cells.jsonl").exists() else None
        where = f"adaptive bank adapted/{adir}" if adapt else "normal (27B) bank"
        add_run(
            id=f"olens.{tag}",
            subject=subj,
            stage=stage_of_tag(base),
            tag=tag,
            bank=adir if adapt else ORIGINAL,
            source=str(sdir),
            judge="claude-opus-5-5 (all-Opus; regex families regex)",
            summary=str(sdir / "summary_opus.json")
            if (sdir / "summary_opus.json").exists()
            else str(sdir / "summary.json"),
            summary_regex=str(sdir / "summary.json") if (sdir / "summary.json").exists() else None,
            contract=str(sdir / "contract.json") if (sdir / "contract.json").exists() else None,
            hal_onpolicy=hal,
            files=files,
            notes=where
            + (
                "; per-item readouts + verdicts"
                if files
                else "; per-family scores only (per-item files on the olens-*-wsbench volume)"
            ),
        )

    # 3. Qwen3.5-4B OLens tags: normal bank and adaptive bank (olens_report/adapt_work/runs)
    for sdir in sorted(AGAM.glob("olens_report/adapt_work/runs/*")):
        if not (sdir / "summary_opus.json").exists():
            continue
        tag = sdir.name
        adapt = ".adapt." in tag
        subj = tag.split(".inv")[0].split(".sft")[0].split(".rl")[0]
        add_run(
            id=f"olens.{tag}",
            subject=subj,
            stage=stage_of_tag(tag),
            tag=tag,
            bank=subj if adapt else ORIGINAL,
            source=str(sdir),
            judge="claude-opus-5-5 (all-Opus; regex families regex)",
            summary=str(sdir / "summary_opus.json"),
            summary_regex=str(sdir / "summary.json") if (sdir / "summary.json").exists() else None,
            contract=str(sdir / "contract.json") if (sdir / "contract.json").exists() else None,
            hal_onpolicy=False,
            files={},
            notes=("adaptive bank adapted/%s" % subj if adapt else "normal (27B) bank")
            + "; per-family scores only (readouts on Modal)",
        )

    # 4. OLens readouts copied for the sweep report (olens_report/readouts/<subj>.<fam>.jsonl)
    stage_note = {"glm": ("inverter", "glm.inv.s7824")}
    by_subj: dict[str, dict] = {}
    for f in sorted(AGAM.glob("olens_report/readouts/*.jsonl")):
        s, fam = f.stem.split(".", 1)
        by_subj.setdefault(s, {})[fam] = {"results": None, "cells": None, "readouts": str(f)}
    for s, fams in by_subj.items():
        stage, tag = stage_note.get(s, ("rl", "RL i600 (sweep report copy)"))
        add_run(
            id=f"olensro.{s}",
            subject=MODEL_ALIAS.get(s, s),
            stage=stage,
            tag=tag,
            bank=ORIGINAL,
            source=str(AGAM / "olens_report/readouts"),
            judge=None,
            files=fams,
            notes="readouts only (basic_readout, typo_mt), copied from the olens-*-wsbench volumes for the sweep report",
        )

    # 5. 4B adaptive smoke run (olens_report/adapt_work/smoke)
    sm = AGAM / "olens_report/adapt_work/smoke"
    if sm.is_dir():
        fams = {}
        for ro in sorted((sm / "readouts").glob("*.jsonl")):
            fams[ro.stem] = {"results": None, "cells": None, "readouts": str(ro)}
        for jd in sorted((sm / "judged_opus").glob("*")):
            fam = jd.name.replace("_opus", "")
            e = fams.setdefault(fam, {"results": None, "cells": None, "readouts": None})
            e["results"] = str(jd / "results.json") if (jd / "results.json").exists() else None
            e["cells"] = str(jd / "cells.jsonl") if (jd / "cells.jsonl").exists() else None
        add_run(
            id="smoke.qwen3.5-4b.inv.adapt",
            subject="qwen3.5-4b",
            stage="smoke",
            tag="qwen3.5-4b.inv.end.adapt__smoke4",
            bank="qwen3.5-4b",
            source=str(sm),
            judge="claude-opus-5-5",
            files=fams,
            notes="inverter smoke on a few adapted items (pre-audit snapshot 04241a03)",
        )

    # 6. gw-jlens: J-lens / J-head AR / inverter readouts + judged results on the 27B bank
    jr = AGAM / "gw-jlens/outputs/jlens_wsb/raw"
    if jr.is_dir():
        stages: dict[str, dict] = {}
        for f in sorted(jr.glob("r_*.json")):
            m = re.match(r"r_(.+)_(" + "|".join(FAMILY_ORDER) + r")\.json$", f.name)
            if m:
                stages.setdefault(m.group(1), {}).setdefault(m.group(2), {})["results"] = str(f)
        for f in sorted(jr.glob("p_*.jsonl")):
            m = re.match(r"p_(.+)_(" + "|".join(FAMILY_ORDER) + r")\.jsonl$", f.name)
            if m:
                stages.setdefault(m.group(1), {}).setdefault(m.group(2), {})["readouts"] = str(f)
        qfiles = {}
        for f in sorted(jr.glob("q_*.jsonl")):
            qfiles[f.stem[2:]] = str(f)
        for st, fams in stages.items():
            field = st if (st.startswith("jlens") or st.startswith("ar_jlogit")) else None
            for fam, e in fams.items():
                e.setdefault("results", None)
                e.setdefault("cells", None)
                if field and fam in qfiles:
                    e["readouts"] = qfiles[fam]
                    e["field"] = field
                e.setdefault("readouts", None)
            stage = (
                "j-lens"
                if st.startswith("jlens")
                else "ar-jlogit"
                if st.startswith("ar_jlogit")
                else "inverter"
            )
            add_run(
                id=f"gwjlens.{st}",
                subject=ORIGINAL,
                stage=stage,
                tag=st,
                bank=ORIGINAL,
                source=str(jr),
                judge="claude-opus-5-5",
                files=fams,
                notes="gw-jlens single-token study (J-lens on truth vs J-head AR readouts); 6 families",
            )

    # 7. 27B lens arms from the wsbench_combos study (per-family item pass rates)
    combos = AGAM / "global-workspace/outputs/wsbench_combos/combos"
    if (combos / "subsets.csv").exists():
        summ = (
            json.loads((combos / "summary.json").read_text())
            if (combos / "summary.json").exists()
            else {}
        )
        arm_stage = {
            "O-lens RL": "rl",
            "J-lens": "j-lens",
            "logit lens": "logit-lens",
            "NLA-RL": "nla",
            "SAE": "sae",
            "AO": "ao",
        }
        add_run_combos = []
        with open(combos / "subsets.csv") as fh:
            for row in csv.DictReader(fh):
                if row.get("k") != "1":
                    continue
                add_run_combos.append(row)
        for row in add_run_combos:
            fams = {}
            for f in summ.get("families") or []:
                v = row.get(f)
                if v not in (None, ""):
                    fams[f] = {
                        "value": float(v),
                        "n": (summ.get("n_common_items") or {}).get(f),
                        "metric": "pass_rate",
                        "higher_is_better": True,
                    }
            add_run(
                id=f"combos.{row['code']}",
                subject=ORIGINAL,
                stage=arm_stage.get(row["subset"], row["subset"].lower()),
                tag=row["subset"],
                bank=ORIGINAL,
                source=str(combos),
                judge="(see global-workspace wsbench_combos)",
                files={},
                combo_scores=fams,
                headline=float(row["macro"]) if row.get("macro") else None,
                headline_ci=[float(row["lo"]), float(row["hi"])] if row.get("lo") else None,
                notes="27B arm from global-workspace/outputs/wsbench_combos (item pass rate on the common items; macro over 22 families)",
            )

    # 8. judge audits: outputs/audit-<tag>/judge/{readouts/<fam>/<arm>.jsonl, res_<fam>.json}
    arm_label = {"i": "gold", "ii": "foil", "iii": "irrelevant"}
    for jd in sorted(WSB.glob("outputs/audit-*/judge")):
        tag = jd.parent.name.split("-", 1)[1]
        subj = next((k for k in banks if k.endswith("-" + tag)), None)
        if subj is None:
            continue
        res = {p.stem[4:]: str(p) for p in jd.glob("res_*.json")}
        for arm in ("i", "ii", "iii"):
            for judge in ("claude-opus-5-5", "claude-sonnet-5"):
                fams = {}
                for fam in sorted(
                    set(res) | {p.name for p in (jd / "readouts").glob("*")}, key=fam_sort_key
                ):
                    ro = jd / "readouts" / fam / f"{arm}.jsonl"
                    cells = jd / "runs" / fam / arm / judge / "cells.jsonl"
                    if not ro.exists() and not cells.exists():
                        continue
                    fams[fam] = {
                        "results": None,
                        "audit_res": res.get(fam),
                        "audit_key": f"{arm}|{judge}",
                        "cells": str(cells) if cells.exists() else None,
                        "readouts": str(ro) if ro.exists() else None,
                    }
                if fams:
                    add_run(
                        id=f"audit.{tag}.{arm_label[arm]}.{judge}",
                        subject=subj,
                        stage="judge-audit",
                        tag=f"{arm_label[arm]} readouts · {judge}",
                        bank=subj,
                        source=str(jd),
                        judge=judge,
                        files=fams,
                        notes="synthetic readouts written to test the judges (gold = should pass, foil / irrelevant = should fail)",
                    )
    # <tag>.hal_onpolicy runs scored only a family that left the bench (plan 0040): not shown
    for hr in [r for r in runs if r.get("hal_onpolicy")]:
        runs.remove(hr)

    # merge readout-only sweep copies into the matching scored OLens tag (same subject/stage/bank)
    for ro in [r for r in runs if r["id"].startswith("olensro.")]:
        twin = next(
            (
                r
                for r in runs
                if r["id"].startswith("olens.")
                and not r.get("hal_onpolicy")
                and (r["subject"], r["stage"], r["bank"])
                == (ro["subject"], ro["stage"], ro["bank"])
            ),
            None,
        )
        if twin is not None:
            twin["files"].update(ro["files"])
            twin["notes"] += (
                "; basic_readout + typo_mt readouts from olens_report/readouts (no per-item verdicts)"
            )
            runs.remove(ro)
    return {"banks": banks, "runs": runs}


# --------------------------------------------------------------------------------------------
# Index build with per-file cache
# --------------------------------------------------------------------------------------------


class FileCache:
    def __init__(self, store: dict):
        self.store = store
        self.used: set[str] = set()
        self.n_parsed = 0

    def get(self, path: str | None, parser, *extra) -> Any:
        if not path:
            return None
        p = Path(path)
        if not p.exists():
            return None
        st = p.stat()
        key = f"{parser.__name__}:{path}:{'|'.join(map(str, extra))}"
        sig = (st.st_mtime_ns, st.st_size) + tuple(
            (Path(e).stat().st_mtime_ns if e and Path(e).exists() else 0) for e in extra
        )
        self.used.add(key)
        hit = self.store.get(key)
        if hit and hit[0] == sig:
            return hit[1]
        val = parser(p, *(Path(e) if e else None for e in extra))
        self.store[key] = (sig, val)
        self.n_parsed += 1
        return val


def _summary_scores(path: str) -> tuple[dict, dict]:
    d = json.loads(Path(path).read_text())
    fams = {}
    for f, e in (d.get("families") or {}).items():
        fams[f] = {
            "value": e.get("value"),
            "ci95": e.get("ci95"),
            "metric": e.get("metric"),
            "higher_is_better": e.get("higher_is_better", True),
            "chance": e.get("bench_chance"),
            "n": e.get("n_items"),
            "complete": e.get("complete"),
            "judge": e.get("judge_model"),
            "normalized": e.get("normalized"),
            "n_unjudged": e.get("n_unjudged_cells"),
            "n_missing": e.get("n_missing_cells"),
        }
    head = {
        k: d.get(k)
        for k in ("missing_for_headline",)
        + (
            "headline_23",
            "headline_23_ci95",
            "headline",
            "headline_ci95",
            "headline_regex6",
            "judge_policy",
            "wsbench_commit",
        )
    }
    return fams, head


def normalized(e: dict) -> float | None:
    v = e.get("normalized")
    if isinstance(v, int | float):
        return float(v)
    v = e.get("value")
    if not isinstance(v, int | float):
        return None
    m = e.get("metric") or ""
    if m == "score":  # buggy_code 1-10
        return max(0.0, min(1.0, v / 10))
    if e.get("higher_is_better") is False:
        return max(0.0, min(1.0, 1 - v))
    return max(0.0, min(1.0, float(v)))


def adaptive_macro(tag: str) -> tuple[float | None, None]:
    p = AGAM / "olens_report/adaptive_scores.json"
    if not p.exists():
        return None, None
    try:
        d = json.loads(p.read_text())
    except Exception:
        return None, None
    for st in (d.get("stages") or {}).values():
        if isinstance(st, dict) and st.get("adapt_tag") == tag:
            return st.get("macro_adapt"), None
    return None, None


def build_index(force: bool = False) -> dict:
    t0 = time.time()
    store = {}
    if CACHE_FILE.exists() and not force:
        try:
            with open(CACHE_FILE, "rb") as fh:
                blob = pickle.load(fh)
            if blob.get("version") == CACHE_VERSION:
                store = blob["files"]
        except Exception:
            store = {}
    fc = FileCache(store)
    spec = discover()
    banks, runs = spec["banks"], spec["runs"]

    # banks: light item lists + plans
    for b in banks.values():
        for fam, e in b["families"].items():
            if e.get("bank") or e.get("gate"):
                parsed = fc.get(
                    e.get("bank") or str(Path(b["root"]) / f"{fam}.json"), parse_bank, e.get("gate")
                )
                e["items"] = parsed["items"] if parsed else []
                e["frozen"] = bool(parsed and parsed["frozen"])
            else:
                e["items"] = []
                e["frozen"] = False
            e["n_items"] = sum(1 for it in e["items"] if it["selected"])
            e["status"] = ((b["report"].get("families") or {}).get(fam) or {}).get("status") or (
                "original" if b["key"] == ORIGINAL else None
            )
        b["has_plan"] = sorted(b["plans"])

    # runs
    for r in runs:
        scores: dict[str, dict] = {}
        verdicts: dict[str, dict] = {}
        readouts: dict[str, dict] = {}
        cells: dict[str, dict] = {}
        if r.get("summary"):
            fams, head = _summary_scores(r["summary"])
            # a removed family (registry.REMOVED_FAMILIES) is never shown, also in old runs; nor
            # is a retired one (RETIRED_FAMILIES, plan 0058) while it stays retired
            hidden = REMOVED_FAMILIES.keys() | RETIRED_FAMILIES.keys()
            scores.update({k: v for k, v in fams.items() if k not in hidden})
            r["head"] = head
            if r.get("headline") is None:
                r["headline"] = head.get("headline_23") or head.get("headline")
                r["headline_ci"] = head.get("headline_23_ci95") or head.get("headline_ci95")
        if r.get("combo_scores"):
            scores.update(r.pop("combo_scores"))
        for fam, e in r["files"].items():
            if e.get("results"):
                parsed = fc.get(e["results"], parse_results)
                if parsed:
                    scores[fam] = parsed["score"]
                    verdicts[fam] = parsed["verdicts"]
            if e.get("audit_res"):
                parsed = fc.get(e["audit_res"], parse_audit_res)
                if parsed and e["audit_key"] in parsed:
                    scores[fam] = parsed[e["audit_key"]]["score"]
                    verdicts[fam] = parsed[e["audit_key"]]["verdicts"]
            if e.get("readouts"):
                ro = fc.get(e["readouts"], parse_readouts)
                if ro:
                    readouts[fam] = {
                        "path": e["readouts"],
                        "field": e.get("field"),
                        "n": ro["n"],
                        "layers": ro["layers"],
                        "items": ro["items"],
                    }
            if e.get("cells"):
                ce = fc.get(e["cells"], parse_cells)
                if ce:
                    cells[fam] = {"path": e["cells"], "n": ce["n"], "items": ce["items"]}
        if r.get("floors_json"):
            fj = json.loads(Path(r["floors_json"]).read_text())
            for fam, e in (fj.get("families") or {}).items():
                if fam not in scores:
                    scores[fam] = {
                        "value": e.get("rate", e.get("value")),
                        "ci95": e.get("ci95"),
                        "metric": e.get("metric"),
                        "n": e.get("n_items"),
                        "complete": e.get("complete"),
                        "judge": e.get("judge_model"),
                        "higher_is_better": True,
                    }
        if r.get("headline") is None and r["bank"] != ORIGINAL:
            r["headline"], r["headline_ci"] = adaptive_macro(r["tag"])
            if r["headline"] is not None:
                r["headline_note"] = (
                    "macro (adapt) from olens_report/adaptive_scores.json; not the official headline_23"
                )
        for f, e in scores.items():
            e["norm"] = normalized(e)
        r["scores"] = scores
        r["verdicts"] = verdicts
        r["readouts"] = readouts
        r["cells"] = cells
        r["label"] = f"{model_label(r['subject'])} · {STAGE_LABEL.get(r['stage'], r['stage'])}"

    # drop cache entries for files that disappeared
    for k in list(store):
        if k not in fc.used:
            del store[k]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(
            {"version": CACHE_VERSION, "files": store}, fh, protocol=pickle.HIGHEST_PROTOCOL
        )
    tmp.replace(CACHE_FILE)

    models = sorted({r["subject"] for r in runs} | set(banks), key=lambda m: model_label(m).lower())
    families = sorted(
        {f for b in banks.values() for f in b["families"]} | {f for r in runs for f in r["scores"]},
        key=fam_sort_key,
    )
    stages = [s for s, _ in STAGES if any(r["stage"] == s for r in runs)]
    idx = {
        "banks": banks,
        "runs": runs,
        "runs_by_id": {r["id"]: r for r in runs},
        "models": models,
        "families": families,
        "stages": stages,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "build_s": round(time.time() - t0, 1),
        "n_parsed": fc.n_parsed,
        "n_files": len(store),
    }
    idx["stats"] = {
        "models": len(models),
        "banks": len(banks),
        "families": len(families),
        "runs": len(runs),
        "results_dirs": sum(
            1 for r in runs for e in r["files"].values() if e.get("results") or e.get("audit_res")
        ),
        "summaries": sum(1 for r in runs if r.get("summary")),
        "readout_files": len({ro["path"] for r in runs for ro in r["readouts"].values()}),
        "readout_rows": sum(ro["n"] for r in runs for ro in r["readouts"].values()),
        "cells_files": len({c["path"] for r in runs for c in r["cells"].values()}),
        "bank_items": sum(e["n_items"] for b in banks.values() for e in b["families"].values()),
    }
    return idx


# --------------------------------------------------------------------------------------------
# Lazy loaders used by item pages
# --------------------------------------------------------------------------------------------


def read_lines(path: str, spans: list[list]) -> list[dict]:
    out = []
    with open(path, "rb") as fh:
        for off, ln, *_ in spans:
            fh.seek(off)
            try:
                out.append(json.loads(fh.read(ln).decode("utf-8", "replace")))
            except Exception:
                continue
    return out


@functools.lru_cache(maxsize=64)
def bank_full(path: str) -> tuple[dict, dict]:
    raw = json.loads(Path(path).read_text())
    items = _items(raw)
    by_id = {}
    for n, it in enumerate(items):
        by_id[str(it.get("id") or it.get("name") or n)] = (n, it)
    return by_id, _header(raw)


@functools.lru_cache(maxsize=16)
def gate_full(path: str) -> dict:
    return _read_gates(Path(path)) or {}


@functools.lru_cache(maxsize=32)
def plan_full(path: str) -> dict:
    return parse_plan(Path(path))


@functools.lru_cache(maxsize=32)
def result_rows(path: str) -> dict[str, list[dict]]:
    d = json.loads(Path(path).read_text())
    out: dict[str, list[dict]] = {}
    for r in d.get("rows") or []:
        if isinstance(r, dict) and (iid := row_item_id(r)) is not None:
            out.setdefault(iid, []).append(r)
    return out


@functools.lru_cache(maxsize=32)
def audit_rows(path: str, key: str) -> dict[str, list[dict]]:
    d = json.loads(Path(path).read_text())
    out: dict[str, list[dict]] = {}
    for r in ((d.get("runs") or {}).get(key) or {}).get("rows") or []:
        if isinstance(r, dict) and (iid := row_item_id(r)) is not None:
            out.setdefault(iid, []).append(r)
    return out


class Index:
    """Thread-safe holder so /rescan can swap the index while requests are served."""

    def __init__(self):
        self._lock = threading.Lock()
        self.data = build_index()

    def rescan(self, force: bool = False) -> dict:
        new = build_index(force=force)
        with self._lock:
            self.data = new
        for fn in (bank_full, gate_full, plan_full, result_rows, audit_rows):
            fn.cache_clear()
        return new

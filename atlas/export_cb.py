"""Export our WorkspaceBench results in the data format of Camila's viewer (wsbench-viewer, app.js
header) as extra subject models; the mirror app (atlas/cb_mirror.py) serves them beside hers.

    python atlas/export_cb.py [--models a,b] [--jobs 6]     -> outputs/cb_export/data/<model>/...
                                                              + outputs/cb_export/our_models.json
Each model is exported in its own process (bank root + tokenizer are per model). Tokens are the
subject's own render of each item's read plan; every readout row's `token` is checked against
toks[pos] and mismatches are counted in outputs/cb_export/report.json (never patched over).
"""

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

os.environ.setdefault("HF_HOME", "/workspace/.persist/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
# the export reads only frozen banks; knowledge_cutoff's nocot rows would fetch nocot's zip (plan 0018)
os.environ.setdefault("WSB_NO_NOCOT", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

AGAM = Path("/workspace/agam")
WSB = AGAM / "workspace-bench"
REP = AGAM / "olens_report"
NG = WSB / "outputs/normal_gated"
OUT = WSB / "outputs/cb_export"
DATA = OUT / "data"
SNAPS = OUT / "snap"
sys.path.insert(0, str(WSB / "src"))
sys.path.insert(0, str(AGAM / "gw-olens/scripts/ola/ar_ablate"))

CB_MANIFEST = Path("/tmp/cbviewer/manifest.json")
CB_URL = "https://safety-sahan-2-camila-blank--wsbench-viewer-web.modal.run"
SKIP_FAMS = {
    "agentic_misalignment",  # pair-scored since plan 0031 (misaligned item + clean twin)
    "jlens_concept_pr",
}  # not in her viewer either
HEADLINE_23 = [
    "association",
    "basic_readout",
    "directed_modulation",
    "multihop",
    "multilingual",
    "poetry",
    "typo",
    "basic_readout_mt",
    "multilingual_mt",
    "multilingual_multihop",
    "multilingual_typo",
    "typo_mt",
    "multi_concept_directed_modulation",
    "relational_multihop",
    "conjunctive_association",
    "role_bound_association",
    "user_modeling",
    "buggy_code",
    "chain_intermediates",
    "moral_rationale",
    "arithmetic_intermediates",
]
ALL_FAMS = HEADLINE_23 + ["jailbreak_recognition"]
REGOLD = ("poetry", "basic_readout", "moral_rationale")

ADAPTIVE = {  # key -> (label, subject key, olens_ckpts dir, adaptive_scores json or None, {arm: stage prefix})
    "qwen3.5-0.8b": (
        "Qwen3.5-0.8B · adaptive",
        "qwen3.5-0.8b",
        "qwen3.5-0.8b",
        "adaptive_scores_qwen3.5-0.8b.json",
        {
            "inverter": "qwen3.5-0.8b.inv.end",
            "student": "qwen3.5-0.8b.sft",
            "rl": "qwen3.5-0.8b.rl.i600",
        },
    ),
    "qwen3.5-2b": (
        "Qwen3.5-2B · adaptive",
        "qwen3.5-2b",
        "qwen3.5-2b",
        "adaptive_scores_qwen3.5-2b.json",
        {"inverter": "qwen3.5-2b.inv.end", "student": "qwen3.5-2b.sft", "rl": "qwen3.5-2b.rl.i600"},
    ),
    "qwen3.5-4b": (
        "Qwen3.5-4B · adaptive",
        "qwen3.5-4b",
        "qwen3.5-4b",
        "adaptive_scores.json",
        {"inverter": "qwen3.5-4b.inv.end", "student": "qwen3.5-4b.sft", "rl": "qwen3.5-4b.rl.i600"},
    ),
    "qwen3-8b": (
        "Qwen3-8B · adaptive",
        "qwen3-8b",
        "qwen3-8b",
        None,
        {"inverter": "qwen3-8b.inv.s6795", "student": "qwen3-8b.sft", "rl": "qwen3-8b.rl.i600"},
    ),
    "olmo-3-7b": (
        "OLMo-3-7B · adaptive",
        "olmo-3-7b",
        "olmo-3-7b-instruct",
        "adaptive_scores_olmo-3-7b-instruct.json",
        {"inverter": "olmo7b.inv.s6794", "student": "olmo7b.sft", "rl": "olmo7b.rl.i600"},
    ),
    "qwen3.5-9b": (
        "Qwen3.5-9B · adaptive",
        "qwen3.5-9b",
        "qwen3.5-9b",
        "adaptive_scores_qwen3.5-9b.json",
        {"inverter": "qwen3.5-9b.inv.end", "student": "qwen3.5-9b.sft", "rl": "qwen3.5-9b.rl.i600"},
    ),
    "gemma-4-31b-it": (
        "Gemma-4-31B · adaptive",
        "gemma-4-31b-it",
        "gemma-4-31b-it",
        "adaptive_scores_gemma-4-31b-it.json",
        {
            "inverter": "gemma.gfix.ar.wsd.full",
            "student": "gemma.gfix.arwsd.sft",
            "rl": "gemma.gfix.arwsd.rl.i600",
        },
    ),
    "olmo-3.1-32b": (
        "OLMo-3.1-32B · adaptive",
        "olmo-3.1-32b",
        "olmo-3.1-32b-instruct",
        "adaptive_scores_olmo-3.1-32b-instruct.json",
        {"inverter": "olmo32b.inv.s6797", "student": "olmo32b.sft", "rl": "olmo32b.rl.i600"},
    ),
    "qwen3.6-35b-a3b": (
        "Qwen3.6-35B-A3B · adaptive",
        "qwen3.6-35b-a3b",
        "qwen3.6-35b-a3b",
        "adaptive_scores_qwen3.6-35b-a3b.json",
        {
            "inverter": "qwen3.6-35b-a3b.inv.end",
            "student": "qwen3.6-35b-a3b.sft",
            "rl": "qwen3.6-35b-a3b.rl.i600",
        },
    ),
    "kimi-k2": (
        "Kimi-K2 · adaptive (reader lens)",
        "kimi-k2",
        "kimi-k2-instruct-0905",
        "adaptive_scores_kimi-k2.json",
        {
            "inverter": "k2.ao.kimi-k2.klinear.s0.step13633",
            "student": "k2.ao.kimi-k2.klinear.distill.s0",
            "rl": "k2.rl.kimi-k2.klinear.ddp600.s0.i600",
        },
    ),
}
GATED = {  # key -> (label, normal_gated subject, tokenizer subject, olens_ckpts dir, {arm: tag})
    "olmo-3.1-32b-27b": (
        "OLMo-3.1-32B · 27B bank, gated",
        "olmo-3.1-32b",
        "olmo-3.1-32b",
        "olmo-3.1-32b-instruct",
        {"inverter": "olmo32b.inv.s6797", "student": "olmo32b.sft", "rl": "olmo32b.rl.i600"},
    ),
    "qwen3.6-35b-a3b-27b": (
        "Qwen3.6-35B-A3B · 27B bank, gated",
        "qwen3.6-35b-a3b",
        "qwen3.6-35b-a3b",
        "qwen3.6-35b-a3b",
        {
            "inverter": "qwen3.6-35b-a3b.inv.end",
            "student": "qwen3.6-35b-a3b.sft",
            "rl": "qwen3.6-35b-a3b.rl.i600",
        },
    ),
    "kimi-k2-27b": (
        "Kimi-K2 · 27B bank, gated",
        "kimi-k2",
        "kimi-k2",
        "kimi-k2-instruct-0905",
        {
            "inverter": "k2.ao.kimi-k2.klinear.s0.step13633",
            "student": "k2.ao.kimi-k2.klinear.distill.s0",
            "rl": "k2.rl.kimi-k2.klinear.ddp600.s0.i600",
        },
    ),
}
ARM_META = {
    "floor": (
        "Prompt-only floor",
        "floor",
        "baseline",
        "the stock subject reads the prompt up to the read token and says what the model is thinking (no lens); "
        "one layer, k=1, T=1.0; each family's own judge on claude-opus-5-5",
    ),
    "inverter": (
        "O-lens inverter",
        "O-inv",
        "O-lens",
        "the subject's OLens inverter (end of training)",
    ),
    "student": ("O-lens student", "O-SFT", "O-lens", "the distilled student (SFT) of the inverter"),
    "rl": ("O-lens RL600", "O-lens", "O-lens", "the student after 600 RL iterations"),
}
_KEY_L = re.compile(r"(?:\||__)L0*(\d+)")
_KEY_P = re.compile(r"(?:\||__)p(-?\d+)")


def jl(p):
    return json.loads(Path(p).read_text())


def iter_jsonl(p: Path):
    with open(p, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def sid_of(i: str) -> str:
    return str(i).replace("/", "~")


def items_of(d):
    return d["items"] if isinstance(d, dict) else d


# ------------------------------------------------------------------------- sources per model
def snapshot_dirs() -> dict[str, Path]:
    """sha8 -> snapshot tgz (every WSB snapshot a tag can name)."""
    out = {}
    for s in glob.glob(str(AGAM / "olens_report/**/*.tgz.sha256"), recursive=True) + glob.glob(
        str(AGAM / "experiments/**/*.tgz.sha256"), recursive=True
    ):
        try:
            sha = Path(s).read_text().split()[0]
        except (OSError, IndexError):
            continue
        out[sha[:8]] = Path(s[: -len(".sha256")])
    return out


def bank_root_for(tag: str, subj: str) -> Path | None:
    """The adapted/<subj> directory of the snapshot an adaptive tag read (extracted on demand)."""
    m = re.search(r"\.(?:adapt|patch)\.([0-9a-f]{8})$", tag)
    if not m:
        return None
    tgz = snapshot_dirs().get(m.group(1))
    if tgz is None:
        return None
    sibling = tgz.parent / tgz.name[: -len(".tgz")]
    for base in (sibling, SNAPS / tgz.name[: -len(".tgz")]):
        for d in (base / "adapted" / subj, *base.glob(f"*/adapted/{subj}")):
            if d.is_dir():
                return d
    dst = SNAPS / tgz.name[: -len(".tgz")]
    dst.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz) as tf:
        members = [
            mm
            for mm in tf.getmembers()
            if f"adapted/{subj}/" in mm.name and "/gate/" not in mm.name and "/cand/" not in mm.name
        ]
        tf.extractall(dst, members=members, filter="data")
    hits = list(dst.glob(f"**/adapted/{subj}"))
    return hits[0] if hits else None


def adaptive_tags(key: str) -> dict:
    """{arm: {"tag": adaptive tag, "patch": [patch tags]}} for the adaptive model `key`."""
    label, subj, cdir, sj, stages = ADAPTIVE[key]
    wsb = AGAM / "olens_ckpts" / cdir / "wsb"
    pinned = {}
    if sj and (REP / sj).exists():
        for st, e in jl(REP / sj)["stages"].items():
            pinned[{"inverter": "inverter", "distill": "student", "rl600": "rl"}.get(st, st)] = (
                e.get("adapt_tag")
            )
    out = {}
    for arm, pref in stages.items():
        tag = pinned.get(arm)
        if not tag or not (wsb / tag).is_dir():
            cands = sorted(
                (
                    p
                    for p in wsb.glob(f"{pref}.adapt.*")
                    if ".patch." not in p.name
                    and not p.name.endswith(".hal_onpolicy")
                    and (p / "judged_opus").is_dir()
                ),
                key=lambda p: p.stat().st_mtime,
            )
            tag = cands[-1].name if cands else None
        if tag:
            patches = sorted(
                (p.name for p in wsb.glob(f"{tag}.patch.*") if (p / "judged_opus").is_dir()),
                key=lambda n: (wsb / n).stat().st_mtime,
            )
            out[arm] = {"tag": tag, "patch": patches}
    return out


# ------------------------------------------------------------------------- verdicts + cells
def item_verdicts(fam: str, res_path: Path) -> tuple[dict, dict, dict]:
    """(scores {id: normalized 0-1 or None}, earliest {id: L}, meta {jm, pv, value, n})."""
    import wsbench_spec as spec

    d = jl(res_path)
    num = d.get("numbers") or {}
    cfg = d.get("config") or {}
    hib = bool(num.get("higher_is_better", True))
    sc = spec.item_scores(fam, d)
    out, el = {}, {}
    if sc is not None:
        for k, v in sc.items():
            if not k.startswith(spec.PAD):
                out[k] = None if v is None else round(spec.normalized(fam, v, hib), 4)
    else:  # fall back to the rows' own pass bit (any-over-rows)
        for r in d.get("rows") or []:
            iid = str(r.get("id") or r.get("item") or "")
            p = r.get("pass")
            if isinstance(p, bool):
                out[iid] = max(out.get(iid) or 0, int(p))
    for r in d.get("rows") or []:
        iid = str(r.get("id") or r.get("item") or "")
        e = r.get("earliest_layer")
        if isinstance(e, int):
            el[iid] = min(el.get(iid, e), e)
    meta = {
        "jm": cfg.get("judge_model") or "",
        "pv": cfg.get("prompt_version") or d.get("prompt_version") or "",
        "value": num.get("value"),
        "n": d.get("n_items"),
        "exact": sc is not None,
    }
    return out, el, meta


def cell_verdict(res, meta: dict, golds: set) -> tuple:
    if not isinstance(res, dict):
        return None, "", ""
    q = res.get("quote") or res.get("evidence") or ""
    if isinstance(q, list):
        q = " … ".join(map(str, q))
    q = str(q)[:240]
    lab = str(res.get("target") or res.get("basis") or meta.get("side") or "")[:60]
    if isinstance(res.get("states_value"), bool):
        vals = {
            str(v).replace(",", "").rstrip("0").rstrip(".") if "." in str(v) else str(v)
            for v in res.get("values") or []
        }
        return (int(bool(vals & golds)) if res["states_value"] else 0), q, lab
    for k in ("pass", "expressed", "correct", "hit", "match", "recognized", "any_recognition"):
        if isinstance(res.get(k), bool):
            return int(res[k]), q, lab
    gold = meta.get("gold_pos", meta.get("gold_position"))
    if isinstance(res.get("choice"), int) and isinstance(gold, int):
        return int(res["choice"] == gold), q, lab
    s = res.get("score")
    if isinstance(s, int | float) and not isinstance(s, bool):
        return (1 if s >= 7 else 0), q, f"score {s}"
    return None, q, lab


def load_cells(path: Path | None, golds_of: dict) -> dict:
    """cells.jsonl -> {id: [{L, p, ok, q, lab}]} (last write per key wins)."""
    per_key = {}
    if not path or not path.exists():
        return {}
    for rec in iter_jsonl(path):
        key = rec.get("key")
        if not isinstance(key, str):
            continue
        meta = rec.get("meta") or {}
        iid = str(meta.get("id") or meta.get("item") or re.split(r"\||__", key, maxsplit=1)[0])
        lm, pm = _KEY_L.search(key), _KEY_P.search(key)
        L = (
            meta.get("layer")
            if isinstance(meta.get("layer"), int)
            else (int(lm.group(1)) if lm else None)
        )
        p = (
            meta.get("pos")
            if isinstance(meta.get("pos"), int)
            else (int(pm.group(1)) if pm else None)
        )
        ok, q, lab = cell_verdict(rec.get("result"), meta, golds_of.get(iid, set()))
        per_key[key] = (iid, {"L": L, "p": p, "ok": ok, "q": q, "lab": lab})
    out: dict = {}
    for iid, c in per_key.values():
        out.setdefault(iid, []).append(c)
    return out


# ------------------------------------------------------------------------- one model
def export_model(key: str) -> dict:
    """Write data/<key>/... and return (manifest entry, verification report)."""
    import shutil

    from wsbench.adapt.author import tokenizer as subject_tokenizer
    from wsbench.produce.render import render

    gated = key in GATED
    if gated:
        label, ngs, toksubj, cdir, tags = GATED[key]
        arms = {a: {"tag": t, "patch": []} for a, t in tags.items()}
        os.environ.pop("WSB_BANK_ROOT", None)
        bank_root = None  # the 27B bank (evals/): the normal tags read it
        gate = jl(NG / ngs / "gate.json")["items"] if (NG / ngs / "gate.json").exists() else {}
        scores = (jl(NG / "scores.json") if (NG / "scores.json").exists() else {}).get(ngs, {})
    else:
        label, subj, cdir, sj, _ = ADAPTIVE[key]
        toksubj = subj
        arms = adaptive_tags(key)
        if not arms:
            return {"key": key, "skipped": "no adaptive tags yet"}
        bank_root = bank_root_for(
            arms["rl"]["tag"] if "rl" in arms else next(iter(arms.values()))["tag"], subj
        )
        if bank_root is None:
            return {"key": key, "skipped": "snapshot for the adaptive tag not found"}
    tok = subject_tokenizer(toksubj)
    special_ids = set(tok.all_special_ids or [])
    wsbroot = AGAM / "olens_ckpts" / cdir / "wsb"
    dst = DATA / key
    tmp = DATA / f".{key}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    import importlib

    import wsbench.readplan as rp

    floors_dir = None if gated else WSB / "adapted" / toksubj / "floors"
    families, items_rows, report, judges, pvs = [], [], {}, {}, {}
    arm_layers: dict[str, set] = {}
    ati_cb = jl(CB_MANIFEST)["ati"]["by_family"] if CB_MANIFEST.exists() else {}
    official: dict = {}
    for fam in ALL_FAMS:
        if fam in SKIP_FAMS:
            continue
        # sources for this family per arm (patch tag wins)
        src = {}
        for arm, e in arms.items():
            t = e["tag"]
            for pt in e["patch"]:
                if (wsbroot / pt / "judged_opus" / fam / "results.json").exists():
                    t = pt
            jd = wsbroot / t / "judged_opus" / fam
            res = jd / "results.json"
            cells = jd / "cells.jsonl"
            if gated and fam in REGOLD:
                nd = NG / ngs / "judged" / t / fam
                res, cells = nd / "results.json", nd / "cells.jsonl"
            src[arm] = {
                "tag": t,
                "res": res,
                "cells": cells,
                "ro": wsbroot / t / "readouts" / f"{fam}.jsonl",
            }
        if floors_dir and (floors_dir / "results" / fam / "results.json").exists():
            src = {
                "floor": {
                    "tag": "floor",
                    "res": floors_dir / "results" / fam / "results.json",
                    "cells": floors_dir / "results" / fam / "cells.jsonl",
                    "ro": floors_dir / "readouts" / f"{fam}.jsonl",
                }
            } | src
        if not any(s["res"].exists() for s in src.values()):
            continue
        # bank: the snapshot the tag read (patched families: the patch tag's own snapshot)
        root = bank_root
        if not gated:
            pt = next((s["tag"] for a, s in src.items() if ".patch." in s["tag"]), None)
            if pt:
                root = bank_root_for(pt, toksubj) or bank_root
            os.environ["WSB_BANK_ROOT"] = str(root)
            if not (root / f"{fam}.json").exists() and not (root / fam).is_dir():
                continue
        importlib.reload(rp)
        try:
            specs = {s.id: s for s in rp.plan(fam)}
        except SystemExit as e:
            report[fam] = {"error": f"plan: {e}"}
            continue
        except Exception as e:
            report[fam] = {"error": f"plan: {type(e).__name__}: {e}"}
            continue
        if gated:
            bp = WSB / "evals" / fam / "items.json"
        else:
            bp = (
                root / f"{fam}.json"
                if (root / f"{fam}.json").exists()
                else root / fam / "items.json"
            )
        bank = items_of(jl(bp))
        gold_items = {}
        if gated and fam in REGOLD and (NG / ngs / "bank" / f"{fam}.json").exists():
            gold_items = {
                str(i.get("id") or i.get("name")): i
                for i in items_of(jl(NG / ngs / "bank" / f"{fam}.json"))
            }
            bank = [i for i in bank if str(i.get("id") or i.get("name")) in gold_items]
        from wsbench.viewer.build import view_item

        if gated:  # the frozen bank's own eval render (poetry: "gate_variant does NOT affect the eval read")
            import dataclasses

            for it in bank:
                iid = str(it.get("id") or it.get("name"))
                sp = specs.get(iid)
                if (
                    sp is not None
                    and it.get("eval_render") == "plain"
                    and sp.render != "plain"
                    and it.get("prompt")
                ):
                    specs[iid] = dataclasses.replace(
                        sp,
                        render="plain",
                        text=it["prompt"],
                        prefill=None,
                        system=None,
                        messages=None,
                    )

        views = {}
        for n, it in enumerate(bank):
            iid = str(it.get("id") or it.get("name") or n)
            v = view_item(gold_items.get(iid, it), n)
            views[iid] = (it, v)
        golds_of = {
            iid: {str(x).strip().lower() for x in v["target"] + v["latent"]}
            for iid, (_, v) in views.items()
        }
        verd, els, metas, cells_by = {}, {}, {}, {}
        for arm, s in src.items():
            if not s["res"].exists():
                continue
            verd[arm], els[arm], metas[arm] = item_verdicts(fam, s["res"])
            cells_by[arm] = load_cells(s["cells"], golds_of)
            judges.setdefault(arm, {})[fam] = metas[arm]["jm"]
            pvs.setdefault(arm, {})[fam] = metas[arm]["pv"]
        # renders
        rendered = {}
        for iid in views:
            spec = specs.get(iid)
            if spec is None:
                continue
            try:
                rendered[iid] = render(spec, tok)
            except Exception:
                continue
        # readouts per arm (verify token == toks[pos])
        ro_by: dict = {}
        mism: dict = {}
        for arm, s in src.items():
            if not s["ro"].exists() or fam == "jailbreak_recognition":
                continue
            n_ok = n_bad = 0
            examples = []
            acc: dict = {}
            for r in iter_jsonl(s["ro"]):
                iid = str(r.get("id"))
                if iid not in views:
                    continue
                lay, pos = r.get("layer"), r.get("pos")
                rd = rendered.get(iid)
                if rd is None or not isinstance(pos, int):
                    continue
                p = pos + len(rd.decoded) if pos < 0 else pos
                if not 0 <= p < len(rd.decoded):
                    n_bad += 1
                    continue
                tokr = r.get("token")
                if tokr is not None:
                    if tokr == rd.decoded[p] or tokr == rd.tokens[p]:
                        n_ok += 1
                    else:
                        n_bad += 1
                        if len(examples) < 3:
                            examples.append([iid, pos, tokr, rd.decoded[p]])
                smp = r.get("samples")
                smp = smp if isinstance(smp, list) else [str(smp or "")]
                acc.setdefault(iid, {}).setdefault(str(p), {})[str(lay)] = [
                    str(x)[:3000] for x in smp
                ]
                arm_layers.setdefault(arm, set()).add(lay)
            ro_by[arm] = acc
            mism[arm] = {"ok": n_ok, "bad": n_bad, "examples": examples}
        # write item + readout files
        fdir = tmp / "item" / fam
        fdir.mkdir(parents=True, exist_ok=True)
        n_items = 0
        for iid, (it, v) in views.items():
            rd = rendered.get(iid)
            if rd is None:
                continue
            n_items += 1
            sid = sid_of(iid)
            L = len(rd.decoded)
            plan_pos = []
            spec = specs[iid]
            try:
                plan_pos = [p + L if p < 0 else p for p in rp.resolve(spec.positions, rd.tokens)]
            except Exception:
                plan_pos = []
            read_pos = sorted({int(p) for a in ro_by for p in (ro_by[a].get(iid) or {})})
            pos = sorted(set(read_pos or plan_pos)) or [L - 1]
            judge = {}
            for arm in verd:
                if iid not in verd[arm]:
                    continue
                cs = []
                for c in cells_by.get(arm, {}).get(iid, []):
                    p = c["p"]
                    if isinstance(p, int) and p < 0:
                        p += L
                    cs.append({"L": c["L"], "p": p, "ok": c["ok"], "q": c["q"], "lab": c["lab"]})
                cs.sort(
                    key=lambda c: (
                        c["L"] if isinstance(c["L"], int) else -1,
                        c["p"] if isinstance(c["p"], int) else -1,
                    )
                )
                okL = sorted({c["L"] for c in cs if c["ok"] == 1 and isinstance(c["L"], int)})
                judge[arm] = {
                    "pass": verd[arm][iid],
                    "jm": metas[arm]["jm"],
                    "pv": metas[arm]["pv"],
                    "note": (
                        f"credited at L{', '.join(map(str, okL))}"
                        if okL
                        else f"{sum(1 for c in cs if c['ok'] == 1)}/{len(cs)} judged cells positive"
                        if cs
                        else ""
                    ),
                    "cells": cs[:600],
                }
            ro_arms = [a for a in ro_by if ro_by[a].get(iid)]
            raw = {k: val for k, val in (gold_items.get(iid) or it).items() if k not in ("adapt",)}
            fields = {
                k: val for k, val in raw.items() if len(json.dumps(val, ensure_ascii=False)) < 2000
            }
            gold = {
                "targets": v["target"]
                or [x for x in v["latent"] if not str(x).startswith("{")][:6],
                "note": (it.get("adapt") or {}).get("note") or "",
                "fields": fields,
            }
            rec = {
                "f": fam,
                "id": iid,
                "toks": rd.decoded,
                "special": [i for i, t in enumerate(rd.ids) if t in special_ids],
                "pos": pos,
                "gold": gold,
                "ro": ro_arms,
                "judge": judge,
                "draws": [],
            }
            if pos:
                best = [
                    c["p"]
                    for a in judge
                    for c in judge[a]["cells"]
                    if c["ok"] == 1 and isinstance(c["p"], int)
                ]
                rec["best_pos"] = max(set(best), key=best.count) if best else pos[-1]
            (fdir / f"{sid}.json").write_text(
                json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
            )
            for a in ro_arms:
                rdir = tmp / "ro" / a / fam
                rdir.mkdir(parents=True, exist_ok=True)
                (rdir / f"{sid}.json").write_text(
                    json.dumps({"c": ro_by[a][iid]}, ensure_ascii=False, separators=(",", ":"))
                )
            # items.json row
            origin = (it.get("adapt") or {}).get("origin", "original")
            ati_ids = set(ati_cb.get(fam, []))
            row = {
                "f": fam,
                "id": iid,
                "sid": sid,
                "snip": (v["stimulus"] or "")[:200].replace("\n", " "),
                "tg": gold["targets"][:4],
                "ati": bool(iid in ati_ids and origin == "original"),
                "g": None,
                "v": {a: verd[a][iid] for a in verd if iid in verd[a] and verd[a][iid] is not None},
                "el": {a: els[a][iid] for a in els if iid in els[a]},
            }
            if (
                gated
                and fam not in REGOLD
                and fam not in ("directed_modulation", "multi_concept_directed_modulation")
            ):
                gb = gate.get(f"{fam}/{iid}")
                if gb is not None:
                    row["g"] = {a: int(bool(gb)) for a in verd}
                else:
                    row["g"] = dict.fromkeys(verd, 0)
            items_rows.append(row)
        # family entry + macro membership
        macro = fam in HEADLINE_23
        if not gated:
            sjd = (
                jl(REP / ADAPTIVE[key][3])
                if ADAPTIVE[key][3] and (REP / ADAPTIVE[key][3]).exists()
                else None
            )
            if sjd:
                mf = list(sjd["stages"].values())[-1]["macro_families"]
                macro = fam in mf
            else:
                rpj = jl(WSB / "adapted" / toksubj / "report.json")
                e = (rpj.get("families") or rpj).get(fam) or {}
                macro = (
                    macro
                    and not e.get("exclude_from_macro")
                    and e.get("status") not in ("ooc", "blocked")
                )
        else:
            r = scores.get("rl") or next(iter(scores.values()), {}) if scores else {}
            macro = macro and fam not in (r.get("dropped") or [])
        families.append(
            {
                "key": fam,
                "n": n_items,
                "macro": macro,
                "ati": fam in ati_cb,
                # rows carry a 1-10 grade (the pre-plan-0030 headline; plan 0030 scores pairs)
                "scored": fam == "buggy_code",
            }
        )
        report[fam] = {
            "n_items": n_items,
            "rendered": len(rendered),
            "tags": {a: s["tag"] for a, s in src.items()},
            "mismatch": mism,
            "exact_item_scores": {a: m["exact"] for a, m in metas.items()},
        }
    # official numbers
    if gated:
        for arm, r in scores.items():
            official[arm] = {
                "macro": r.get("gated"),
                "fam": {
                    f: v["gated"] for f, v in r["families"].items() if v.get("gated") is not None
                },
            }
    else:
        sjn = ADAPTIVE[key][3]
        if sjn and (REP / sjn).exists():
            d = jl(REP / sjn)
            for st, e in d["stages"].items():
                arm = {"inverter": "inverter", "distill": "student", "rl600": "rl"}.get(st, st)
                official[arm] = {"macro": e.get("macro_adapt"), "fam": e.get("adapt") or {}}
            if d.get("floors"):
                ff = {
                    f: d["floors"][f]
                    for f in d["floors"]
                    if f in [x["key"] for x in families if x["macro"]]
                }
                official["floor"] = {
                    "macro": round(sum(ff.values()) / len(ff), 4) if ff else None,
                    "fam": d["floors"],
                }
    arm_list = (
        ["floor"] if not gated and floors_dir and (floors_dir / "results").is_dir() else []
    ) + list(arms)
    layers = sorted({L for s in arm_layers.values() for L in s if isinstance(L, int)})
    entry = {
        "key": key,
        "label": label,
        "note": (
            f"{label}: lenses read on the 27B bank; gated = items the subject itself answers (adapt gate: greedy right "
            f"AND >= 8/10, every leg incl. bridges); poetry / basic_readout / moral_rationale re-judged with the "
            f"subject's own rhyme / favourite / side + reasons."
            if gated
            else f"{label}: the subject's own audited adaptive set (adapted/{toksubj}); exported from our runs "
            f"(tags {', '.join(a['tag'] for a in arms.values())})."
        ),
        "missing": []
        if gated
        else ([] if (floors_dir and floors_dir.is_dir()) else ["floor: not measured"]),
        "layers": layers,
        "has_gate": gated,
        "default_gate": gated,
        "gate_label": "subject-gated" if gated else "",
        "gate_note": (
            "subject-gated = only items this subject answers at the gate (greedy right AND >= 8/10 samples, every leg). "
            "directed_modulation / multi_concept_dm have no checkable answer and always count; poetry / basic_readout / "
            "moral_rationale show the subject's own golds. Off = every 27B-bank item with the original verdicts."
            if gated
            else ""
        ),
        "macro_note": (
            "Macro = the HEADLINE_23 families with >= 10 items the subject answers."
            if gated
            else "Macro = the subject's adaptive macro families (adaptive_scores_*.json)."
        ),
        "families": families,
        "arms": [
            {
                "key": a,
                "label": ARM_META[a][0],
                "short": ARM_META[a][1],
                "group": ARM_META[a][2],
                "kind": "prose",
                "default": True,
                "layers": sorted(L for L in arm_layers.get(a, []) if isinstance(L, int)),
                "layer_note": "",
                "desc": ARM_META[a][3]
                + (
                    ""
                    if a == "floor"
                    else f"; tag {arms[a]['tag']}"
                    + (f" (+ patch {', '.join(arms[a]['patch'])})" if arms[a]["patch"] else "")
                ),
                "judges": judges.get(a, {}),
                "pv": pvs.get(a, {}),
            }
            for a in arm_list
        ],
        "official": official,
        "notes": [f"{f}: {r['error']}" for f, r in report.items() if r.get("error")],
    }
    (tmp / "items.json").write_text(
        json.dumps({"items": items_rows}, ensure_ascii=False, separators=(",", ":"))
    )
    shutil.rmtree(dst, ignore_errors=True)
    tmp.rename(dst)
    return {"key": key, "entry": entry, "report": report}


def zip_model(key: str) -> Path:
    """data/<key>/ -> zips/<key>.zip (what the mirror serves: one upload instead of ~10k files)."""
    import zipfile

    src = DATA / key
    (OUT / "zips").mkdir(exist_ok=True)
    tmpz = OUT / "zips" / f".{key}.zip"
    with zipfile.ZipFile(tmpz, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(src).as_posix())
    dst = OUT / "zips" / f"{key}.zip"
    tmpz.replace(dst)
    return dst


def fingerprint(key: str) -> str:
    """Cheap change detector over every source file of a model (mtime + size)."""
    pats = []
    if key in GATED:
        _, ngs, _, cdir, tags = GATED[key]
        pats += [
            str(NG / ngs / "gate.json"),
            str(NG / "scores.json"),
            str(NG / ngs / "judged/*/*/results.json"),
            str(NG / ngs / "bank/*.json"),
        ]
        pats += [
            str(AGAM / "olens_ckpts" / cdir / "wsb" / t / "judged_opus/*/results.json")
            for t in tags.values()
        ]
    else:
        _, subj, cdir, sj, _ = ADAPTIVE[key]
        pats += [
            str(AGAM / "olens_ckpts" / cdir / "wsb/*.adapt.*/judged_opus/*/results.json"),
            str(WSB / "adapted" / subj / "floors/results/*/results.json"),
        ]
        if sj:
            pats.append(str(REP / sj))
    h = hashlib.sha1()
    for p in pats:
        for f in sorted(glob.glob(p)):
            st = os.stat(f)
            h.update(f"{f}:{st.st_mtime_ns}:{st.st_size}".encode())
    return h.hexdigest()


def _run_one(key: str) -> dict:
    t0 = time.time()
    p = subprocess.run([sys.executable, __file__, "--one", key], capture_output=True, text=True)
    out = OUT / "parts" / f"{key}.json"
    if p.returncode != 0 or not out.exists():
        return {"key": key, "error": (p.stderr or p.stdout)[-1500:]}
    r = jl(out)
    r["secs"] = round(time.time() - t0)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(list(ADAPTIVE) + list(GATED)))
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--one")
    ap.add_argument("--changed", action="store_true", help="only models whose sources changed")
    ap.add_argument("--zip-only", action="store_true")
    a = ap.parse_args()
    (OUT / "parts").mkdir(parents=True, exist_ok=True)
    if a.one:
        r = export_model(a.one)
        if r.get("entry"):
            zip_model(a.one)
        (OUT / "parts" / f"{a.one}.json").write_text(json.dumps(r, ensure_ascii=False))
        return
    if a.zip_only:
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            for z in ex.map(zip_model, [k for k in a.models.split(",") if (DATA / k).is_dir()]):
                print(z, z.stat().st_size // 2**20, "MB", flush=True)
        return
    state_p = OUT / "state.json"
    state = jl(state_p) if state_p.exists() else {}
    keys = a.models.split(",")
    if a.changed:
        keys = [k for k in keys if state.get(k) != fingerprint(k)]
    done = []
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(_run_one, k): k for k in keys}
        for f in as_completed(futs):
            r = f.result()
            k = futs[f]
            if r.get("error"):
                print(f"{k}: ERROR {r['error'][-600:]}", flush=True)
                continue
            if r.get("skipped"):
                print(f"{k}: skipped ({r['skipped']})", flush=True)
                continue
            state[k] = fingerprint(k)
            done.append(k)
            mm = [
                (f, arm, v["bad"], v["ok"])
                for f, rr in r["report"].items()
                for arm, v in (rr.get("mismatch") or {}).items()
            ]
            bad = sum(x[2] for x in mm)
            okn = sum(x[3] for x in mm)
            print(
                f"{k}: {len(r['entry']['families'])} fams, token check {okn} ok / {bad} mismatched, {r.get('secs')}s",
                flush=True,
            )
    # assemble our_models.json in a fixed order from every part on disk
    order = list(ADAPTIVE) + list(GATED)
    models, reports = [], {}
    for k in order:
        p = OUT / "parts" / f"{k}.json"
        if p.exists() and (DATA / k / "items.json").exists():
            r = jl(p)
            if r.get("entry"):
                models.append(r["entry"])
                reports[k] = r["report"]
    (OUT / "our_models.json").write_text(
        json.dumps(
            {"built_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "models": models},
            ensure_ascii=False,
        )
    )
    (OUT / "report.json").write_text(json.dumps(reports, indent=1, ensure_ascii=False))
    state_p.write_text(json.dumps(state, indent=1))
    print("changed:", ",".join(done) or "-", flush=True)


if __name__ == "__main__":
    main()

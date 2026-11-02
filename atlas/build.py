"""WSB Atlas: stage every adapted bank's questions + every technique's readouts and verdicts as
static JSON beside a small light-mode site (atlas/site). Read-only on all sources.

    /workspace/agam/envs/adapt/bin/python atlas/build.py [--out outputs/atlas] [--models a,b]

Layout written under OUT/data:
  index.json                        models, techniques, families, scores, scoreboard
  <model>/<family>.json             items (question, gold, latent, gate) + per-technique verdicts
  <model>/<family>/<tech>.<k>.json  readouts for item chunk k: {id: [[layer,pos,tok,text,v,quote]]}
"""

import argparse
import csv
import json
import re
import shutil
import sys
import time
from pathlib import Path

AGAM = Path("/workspace/agam")
WSB = AGAM / "workspace-bench"
sys.path.insert(0, str(WSB / "src"))
from wsbench.viewer.build import GROUPS, _items, view_item  # noqa: E402

SITE = Path(__file__).parent / "site"
CHUNK = 20
MAX_TEXT = 1600
SKIP_READOUTS = {"jailbreak_recognition", "agentic_misalignment"}  # 100s of MB; scores only
FAMILY_ORDER = [f for _, fams in GROUPS for f in fams]
FAMILY_GROUP = {f: g for g, fams in GROUPS for f in fams}

FAMILY_DESC = {
    "association": "A passage describes something it never names; does the lens surface the unnamed referent?",
    "basic_readout": "The model is asked for a one-word answer; read its answer before it is written.",
    "multihop": "Two-hop factual question; the bridge entity is never written.",
    "multilingual": "Prompt in another language; the concept should be readable language-independently.",
    "poetry": "Couplet: the rhyme word of line 2 is planned at the end of line 1.",
    "typo": "A misspelled word; the lens should read the corrected word.",
    "directed_modulation": "The model is told to think (or not think) about a word while writing something else.",
    "multilingual_mt": "Multi-token concept described in another language.",
    "typo_mt": "Typo'd multi-token word (the hard typo family; typo is superseded by it).",
    "basic_readout_mt": "Multi-token answer (an entity) read before it is written.",
    "multilingual_multihop": "Two-hop question asked in another language.",
    "multilingual_typo": "Typo'd word inside a non-English prompt.",
    "multi_concept_directed_modulation": "One to three dictated concepts to hold while writing a sentence; all must surface.",
    "chain_intermediates": "Multi-step arithmetic chain; read the intermediate values.",
    "buggy_code": "Buggy program + clean twin; does the lens say there is a bug, and no bug in the twin (pair rate)?",
    "arithmetic_intermediates": "Arithmetic expressions; read intermediate results at each position.",
    "agentic_misalignment": "Agentic scenario + clean twin (no reason, no means); does the lens show the planned misaligned act, and none in the twin (pair rate)?",
    "jailbreak_recognition": "Does the lens show the model recognising a jailbreak attempt?",
    "user_modeling": "Infer attributes of the user (country, gender, job) from the conversation.",
    "conjunctive_association": "Two cues jointly imply a concept neither implies alone.",
    "role_bound_association": "Who did what to whom in a two-person scene.",
    "relational_multihop": "Kinship / relation chains ('my friend's teacher's father').",
    "jlens_concept_pr": "Precision of lens concepts against the subject's own J-lens top-10.",
    "moral_rationale": "Moral dilemma: read the side the model takes and its reasons.",
}

# subject key -> (label, olens_ckpts dir, adaptive tags by stage, normal tags by stage)
SUBJECTS = {
    "qwen3.5-0.8b": (
        "Qwen3.5-0.8B",
        "qwen3.5-0.8b",
        "qwen3.5-0.8b.{}.adapt.29a0292f",
        ("inv.end", "sft", "rl.i600"),
    ),
    "qwen3.5-2b": (
        "Qwen3.5-2B",
        "qwen3.5-2b",
        "qwen3.5-2b.{}.adapt.29a0292f",
        ("inv.end", "sft", "rl.i600"),
    ),
    "qwen3.5-4b": (
        "Qwen3.5-4B",
        "qwen3.5-4b",
        "qwen3.5-4b.{}.adapt.6dbb08e4",
        ("inv.end", "sft", "rl.i600"),
    ),
    "qwen3-8b": (
        "Qwen3-8B",
        "qwen3-8b",
        "qwen3-8b.{}.adapt.4d5e71b6",
        ("inv.s6795", "sft", "rl.i600"),
    ),
    "olmo-3-7b": (
        "OLMo-3-7B-Instruct",
        "olmo-3-7b-instruct",
        "olmo7b.{}.adapt.0138e267",
        ("inv.s6794", "sft", "rl.i600"),
    ),
    "qwen3.5-9b": (
        "Qwen3.5-9B",
        "qwen3.5-9b",
        "qwen3.5-9b.{}.adapt.664f5a8d",
        ("inv.end", "sft", "rl.i600"),
    ),
    "gemma-4-31b-it": (
        "Gemma-4-31B-it",
        "gemma-4-31b-it",
        "gemma.gfix.{}.adapt.2df1784a",
        ("ar.wsd.full", "arwsd.sft", "arwsd.rl.i600"),
    ),
    "olmo-3.1-32b": (
        "OLMo-3.1-32B-Instruct",
        "olmo-3.1-32b-instruct",
        "olmo32b.{}.adapt.6e6fed0b",
        ("inv.s6797", "sft", "rl.i600"),
    ),
    "qwen3.6-35b-a3b": (
        "Qwen3.6-35B-A3B",
        "qwen3.6-35b-a3b",
        "qwen3.6-35b-a3b.{}.adapt.47f4087f",
        ("inv.end", "sft", "rl.i600"),
    ),
    "kimi-k2": ("Kimi-K2 (reader lens)", "kimi-k2-instruct-0905", "{}.adapt.d162743b",
                ("k2.ao.kimi-k2.klinear.s0.step13633", "k2.ao.kimi-k2.klinear.distill.s0", "k2.rl.kimi-k2.klinear.ddp600.s0.i600")),
    "qwen3.6-27b": ("Qwen3.6-27B (reference)", None, None, ()),
}
NG = WSB / "outputs/normal_gated"
NG_REGOLD = ("poetry", "basic_readout", "moral_rationale")
NORMAL_GATED = {  # view key -> (label, subject key in outputs/normal_gated, olens_ckpts dir, {stage: tag})
    "olmo-3.1-32b@27b": (
        "OLMo-3.1-32B · 27B bank, gated",
        "olmo-3.1-32b",
        "olmo-3.1-32b-instruct",
        {"inverter": "olmo32b.inv.s6797", "student": "olmo32b.sft", "rl": "olmo32b.rl.i600"},
    ),
    "qwen3.6-35b-a3b@27b": (
        "Qwen3.6-35B-A3B · 27B bank, gated",
        "qwen3.6-35b-a3b",
        "qwen3.6-35b-a3b",
        {
            "inverter": "qwen3.6-35b-a3b.inv.end",
            "student": "qwen3.6-35b-a3b.sft",
            "rl": "qwen3.6-35b-a3b.rl.i600",
        },
    ),
    "kimi-k2@27b": (
        "Kimi-K2 · 27B bank, gated",
        "kimi-k2",
        "kimi-k2-instruct-0905",
        {
            "inverter": "k2.ao.kimi-k2.klinear.s0.step13633",
            "student": "k2.ao.kimi-k2.klinear.distill.s0",
            "rl": "k2.rl.kimi-k2.klinear.ddp600.s0.i600",
        },
    ),
    # glm-5.3-flash@27b: held back (Agam 2026-10-23: no GLM scoring yet)
}
SCOREBOARD_NAME = {
    "Qwen3.5-0.8B": "qwen3.5-0.8b",
    "Qwen3.5-2B": "qwen3.5-2b",
    "Qwen3.5-4B": "qwen3.5-4b",
    "Qwen3-8B": "qwen3-8b",
    "OLMo-3-7B": "olmo-3-7b",
    "Qwen3.5-9B": "qwen3.5-9b",
    "Gemma-4-31B": "gemma-4-31b-it",
    "Qwen3.6-27B (reference)": "qwen3.6-27b",
    "OLMo-3.1-32B": "olmo-3.1-32b",
    "Qwen3.6-35B-A3B": "qwen3.6-35b-a3b",
}
OLENS_TECHS = [
    (
        "inverter",
        "OLens · inverter",
        "The OLens inverter: decodes the residual stream at a layer into text.",
    ),
    ("student", "OLens · student", "Distilled student (SFT) of the inverter."),
    ("rl", "OLens · RL 600", "The student after 600 RL iterations."),
]
FLOOR_TECH = (
    "floor",
    "Prompt-only floor",
    "Baseline: the stock subject reads the prompt up to the read token and says what the model is thinking. "
    "No lens; a lens score only means something above this.",
)
GW27 = AGAM / "gw-jlens/outputs/jlens_wsb/raw"
TECH_27B = [  # (key, label, stage in gw-jlens files, readout source: p=text file, q:<field>=top-10 tokens)
    (
        "inverter",
        "OLens · inverter",
        "inv_end",
        "p",
        "OLens inverter (end of training) on the 27B.",
    ),
    (
        "jlens",
        "J-lens",
        "jlens_j",
        "q:jlens_j",
        "J-lens (Jacobian lens) top-10 tokens at the read site.",
    ),
    (
        "jlens_pp",
        "J-lens++",
        "jlens_jpp",
        "q:jlens_jpp",
        "J-lens with the ++ basis; top-10 tokens.",
    ),
    (
        "jhead_ar",
        "J-head AR",
        "ar_jlogit_jpp.s2",
        "q:ar_jlogit_jpp.s2",
        "AR model reading J-lens logits; top-10 tokens.",
    ),
]
COMBO_LABEL = {
    "O-lens RL": "OLens · RL (combos)",
    "J-lens": "J-lens (combos)",
    "logit lens": "Logit lens",
    "NLA-RL": "NLA-RL",
    "SAE": "SAE",
    "AO": "AO",
}

_KEY_L = re.compile(r"(?:\||__)L0*(\d+)")
_KEY_P = re.compile(r"(?:\||__)p(-?\d+)")


def jload(p: Path):
    return json.loads(p.read_text())


def iter_jsonl(p: Path):
    with open(p, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def norm_value(num: dict) -> float | None:
    v = num.get("value")
    if not isinstance(v, int | float) or isinstance(v, bool):
        return None
    if num.get("metric") == "score":
        return max(0.0, min(1.0, v / 10))
    if num.get("higher_is_better") is False:
        return max(0.0, min(1.0, 1 - v))
    return float(v)


def row_item_id(r: dict) -> str | None:
    for k in ("id", "item"):
        if isinstance(r.get(k), str | int):
            return str(r[k])
    if isinstance(r.get("key"), str):
        return re.split(r"\||__", r["key"], maxsplit=1)[0]
    return None


def row_pass(r: dict) -> bool | None:
    for k in ("pass", "correct", "hit", "any_recognition", "asserts_misaligned_plan", "expressed"):
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
        v = r.get(k)
        if isinstance(v, int | float) and not isinstance(v, bool):
            return float(v)
    return None


def verdicts(results: Path) -> tuple[dict, dict]:
    """results.json -> (score entry, {item: {p, n, k, L: {layer: 0/1}, e, s}})."""
    d = jload(results)
    num = d.get("numbers") or {}
    score = {
        "v": norm_value(num),
        "raw": num.get("value"),
        "metric": num.get("metric"),
        "n": d.get("n_items"),
        "complete": d.get("complete"),
        "ci": num.get("ci95"),
    }
    groups: dict[str, list] = {}
    for r in d.get("rows") or []:
        if isinstance(r, dict) and (iid := row_item_id(r)) is not None:
            groups.setdefault(iid, []).append(r)
    out = {}
    for iid, rows in groups.items():
        passes = [p for p in map(row_pass, rows) if p is not None]
        scores = [s for s in map(row_score, rows) if s is not None]
        by_layer: dict[int, bool] = {}
        earliest = None
        for r in rows:
            p = row_pass(r)
            lay = r.get("layer")
            if isinstance(lay, str) and lay.lstrip("-").isdigit():
                lay = int(lay)
            if isinstance(lay, int) and p is not None:
                by_layer[lay] = by_layer.get(lay, False) or p
            if isinstance(r.get("layers"), dict):
                passing = r.get("passing_layers")
                for k, v in r["layers"].items():
                    try:
                        li = int(k)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(passing, list):
                        ok = li in passing or str(li) in passing
                    elif isinstance(v, dict):
                        ok = next(
                            (
                                v[x]
                                for x in ("expressed", "pass", "correct", "hit")
                                if isinstance(v.get(x), bool)
                            ),
                            None,
                        )
                        if ok is None:
                            continue
                    elif isinstance(v, bool):
                        ok = v
                    else:
                        continue
                    by_layer[li] = by_layer.get(li, False) or ok
            if isinstance(r.get("earliest_layer"), int):
                earliest = (
                    r["earliest_layer"] if earliest is None else min(earliest, r["earliest_layer"])
                )
        e: dict = {}
        if passes:
            e["p"] = int(all(passes)) if len(passes) == 1 else None
            if len(passes) > 1:
                e["k"], e["n"] = sum(passes), len(passes)
                e["p"] = round(sum(passes) / len(passes), 3)
        if scores:
            e["s"] = round(sum(scores) / len(scores), 2)
        if by_layer:
            e["L"] = {str(k): int(v) for k, v in sorted(by_layer.items())}
        if earliest is not None:
            e["e"] = earliest
        out[iid] = e
    return score, out


def cell_pass(res, meta: dict) -> tuple:
    """One judge cell -> (verdict 1/0/None, quote, values|None). values = stated numbers (resolved later)."""
    if not isinstance(res, dict):
        return None, "", None
    q = res.get("quote") or res.get("evidence") or ""
    if isinstance(q, list):
        q = " … ".join(map(str, q))
    q = str(q)[:200]
    if isinstance(
        res.get("states_value"), bool
    ):  # chain / arithmetic: right only if a gold value is stated
        return (0 if not res["states_value"] else None), q, res.get("values") or []
    if isinstance(res.get("samples"), list):  # span judges: any marked span = a fail
        spans = [
            sp for smp in res["samples"] if isinstance(smp, dict) for sp in (smp.get("spans") or [])
        ]
        return (
            int(not spans),
            (
                " … ".join(
                    str(sp.get("text", sp)) if isinstance(sp, dict) else str(sp) for sp in spans
                )
            )[:200],
            None,
        )
    for k in (
        "pass",
        "expressed",
        "correct",
        "hit",
        "match",
        "recognized",
        "recognition",
        "any_recognition",
    ):
        if isinstance(res.get(k), bool):
            return int(res[k]), q, None
    gold = meta.get("gold_pos", meta.get("gold_position"))
    if isinstance(res.get("choice"), int) and isinstance(gold, int):
        return int(res["choice"] == gold), q, None
    s = res.get("score")
    if isinstance(s, int | float) and not isinstance(s, bool):
        return (1 if s >= 7 else 0), q, None
    return None, q, None


def load_cells(path: Path | None) -> dict:
    """cells.jsonl -> {(id, layer, pos|None): (v, quote, values)}; several cells per read site
    (samples, sides) merge as any-pass; the last write per key wins."""
    per_key: dict = {}
    if not path or not path.exists():
        return {}
    for rec in iter_jsonl(path):
        key = rec.get("key")
        if not isinstance(key, str):
            continue
        meta = rec.get("meta") or {}
        iid = str(meta.get("id") or meta.get("item") or re.split(r"\||__", key, maxsplit=1)[0])
        lm, pm = _KEY_L.search(key), _KEY_P.search(key)
        lay = (
            meta.get("layer")
            if isinstance(meta.get("layer"), int)
            else (int(lm.group(1)) if lm else None)
        )
        pos = (
            meta.get("pos")
            if isinstance(meta.get("pos"), int)
            else (int(pm.group(1)) if pm else None)
        )
        per_key[key] = ((iid, lay, pos), cell_pass(rec.get("result"), meta))
    out: dict = {}
    for site, (v, q, vals) in per_key.values():
        if site in out:
            v0, q0, vals0 = out[site]
            if v0 == 1 or (v0 is not None and v is None):
                continue
            if vals0 is not None and vals is not None:
                vals = list(vals0) + list(vals)
        out[site] = (v, q, vals)
    return out


def readout_text(r: dict, field: str | None) -> str:
    if field:
        toks = r.get(field)
        return " · ".join(repr(t)[1:-1] for t in toks) if isinstance(toks, list) else ""
    s = r.get("samples")
    if isinstance(s, list):
        s = "\n".join(map(str, s))
    elif s is None:
        s = r.get("text") or r.get("readout") or ""
    s = str(s)
    return s if len(s) <= MAX_TEXT else s[:MAX_TEXT] + " …"


def load_readouts(path: Path, field: str | None, cells: dict, verd: dict) -> dict:
    """-> {id: [[layer, pos, token, text, v, quote], ...]} sorted by layer, pos."""
    out: dict[str, list] = {}
    for r in iter_jsonl(path):
        iid = str(r.get("id"))
        lay, pos = r.get("layer"), r.get("pos")
        c = cells.get((iid, lay, pos)) or cells.get((iid, lay, None))
        if c is None:  # fall back to the item's per-layer verdict
            lv = (verd.get(iid) or {}).get("L", {}).get(str(lay))
            c = (lv, "", None)
        row = [lay, pos, r.get("token"), readout_text(r, field), c[0], c[1]]
        if c[2] is not None:
            row.append(c[2])  # stated values; resolved against the item's gold in build_family
        out.setdefault(iid, []).append(row)
    for rows in out.values():
        rows.sort(
            key=lambda x: (
                x[0] if isinstance(x[0], int) else -1,
                x[1] if isinstance(x[1], int) else -1,
            )
        )
    return out


def _numkey(x) -> str:
    try:
        f = float(str(x).replace(",", ""))
        return str(int(f)) if f == int(f) else str(f)
    except (TypeError, ValueError):
        return str(x).strip().lower()


def gate_summary(rec: dict | None) -> dict | None:
    if not rec:
        return None
    g = rec.get("gate") or {}

    def leg(x: dict) -> dict:
        smp = x.get("samples") or []
        return {
            "greedy": ((x.get("greedy") or {}).get("text") or "")[:300],
            "ok": (x.get("greedy") or {}).get("ok"),
            "k": sum(1 for s in smp if s.get("ok")),
            "n": len(smp),
            "samples": [[(s.get("text") or "")[:120], s.get("ok")] for s in smp[:10]],
        }

    out = {
        "rate": g.get("rate"),
        "pass": g.get("pass"),
        "render": g.get("render"),
        "question": (g.get("question") or "")[:4000],
        "lint": g.get("lint") or [],
    }
    if g.get("greedy"):
        out |= leg(g)
    legs = {}
    for name, x in (g.get("legs") or {}).items():
        if isinstance(x, dict):
            legs[name] = leg(x) | {
                "passed": x.get("passed"),
                "question": (x.get("question") or "")[-600:],
            }
    if legs:
        out["legs"] = legs
    return out


def read_gates(path: Path) -> dict:
    out = {}
    if path.exists():
        for rec in iter_jsonl(path):
            out[str(rec.get("id"))] = rec
    return out


def item_view(raw: dict, n: int, gate_rec: dict | None, dropped: bool = False) -> dict:
    v = view_item(raw, n)
    a = raw.get("adapt") or {}
    knobs = a.get("knobs") or {}
    return {
        "id": v["id"],
        "origin": v["origin"],
        "tier": v["tier"],
        "sub": None if v["subfamily"] is None else str(v["subfamily"]),
        "q": v["stimulus"][:12000],
        "gold": [str(t)[:200] for t in v["target"][:8]],
        "latent": [str(t)[:120] for t in v["latent"][:12]],
        "knobs": {k: (str(x)[:300]) for k, x in knobs.items()},
        "note": a.get("note"),
        "parent": a.get("parent"),
        "render": raw.get("eval_render") or raw.get("render"),
        "gate": gate_summary(gate_rec)
        or ({"rate": (a.get("gate") or {}).get("rate")} if a.get("gate") else None),
        "dropped": dropped,
    }


# ---------------------------------------------------------------------------------------------


def techniques_for(model: str) -> list[dict]:
    """[{key, label, desc, kind, fams: {fam: {results, cells, readouts, field}}}]"""
    techs = []
    if model == "qwen3.6-27b":
        for key, label, stage, src, desc in TECH_27B:
            fams = {}
            for f in FAMILY_ORDER:
                res = GW27 / f"r_{stage}_{f}.json"
                if not res.exists():
                    continue
                ro, field = (
                    (GW27 / f"p_{stage}_{f}.jsonl", None)
                    if src == "p"
                    else (GW27 / f"q_{f}.jsonl", src[2:])
                )
                fams[f] = {
                    "results": res,
                    "cells": None,
                    "readouts": ro if ro.exists() else None,
                    "field": field,
                }
            techs.append({"key": key, "label": label, "desc": desc, "kind": "lens", "fams": fams})
        return techs
    if model in NORMAL_GATED:
        _, sk, cdir, tags = NORMAL_GATED[model]
        for (key, label, desc), (st, tag) in zip(OLENS_TECHS, tags.items()):
            root = AGAM / "olens_ckpts" / cdir / "wsb" / tag
            fams = {}
            for jd in sorted((root / "judged_opus").glob("*")):
                fam = jd.name[:-5] if jd.name.endswith("_opus") else jd.name
                e = {
                    "results": jd / "results.json" if (jd / "results.json").exists() else None,
                    "cells": jd / "cells.jsonl",
                    "readouts": root / "readouts" / f"{fam}.jsonl",
                    "field": None,
                }
                nd = NG / sk / "judged" / tag / fam
                if fam in NG_REGOLD:  # re-judged with the subject's own golds (or nothing yet)
                    e |= {
                        "results": nd / "results.json" if (nd / "results.json").exists() else None,
                        "cells": nd / "cells.jsonl",
                    }
                fams[fam] = e
            techs.append(
                {
                    "key": key,
                    "label": label,
                    "desc": desc + f" Tag {tag} (normal 27B bank).",
                    "kind": "lens",
                    "tag": tag,
                    "fams": fams,
                }
            )
        return techs
    fl = WSB / "adapted" / model / "floors"
    if fl.is_dir():
        fams = {}
        for rdir in sorted((fl / "results").glob("*")):
            fams[rdir.name] = {
                "results": rdir / "results.json" if (rdir / "results.json").exists() else None,
                "cells": rdir / "cells.jsonl",
                "readouts": fl / "readouts" / f"{rdir.name}.jsonl",
                "field": None,
            }
        techs.append(
            {
                "key": FLOOR_TECH[0],
                "label": FLOOR_TECH[1],
                "desc": FLOOR_TECH[2],
                "kind": "floor",
                "fams": fams,
            }
        )
    _, cdir, pattern, stages = SUBJECTS[model]
    for (key, label, desc), st in zip(OLENS_TECHS, stages):
        tag = pattern.format(st)
        root = AGAM / "olens_ckpts" / cdir / "wsb" / tag
        fams = {}
        for jd in sorted((root / "judged_opus").glob("*")):
            fam = jd.name[:-5] if jd.name.endswith("_opus") else jd.name
            fams[fam] = {
                "results": jd / "results.json" if (jd / "results.json").exists() else None,
                "cells": jd / "cells.jsonl",
                "readouts": root / "readouts" / f"{fam}.jsonl",
                "field": None,
            }
        techs.append(
            {
                "key": key,
                "label": label,
                "desc": desc + f" Tag {tag}.",
                "kind": "lens",
                "tag": tag,
                "fams": fams,
            }
        )
    return techs


def bank_items(model: str, fam: str) -> tuple[list[dict], dict]:
    if model in NORMAL_GATED:
        sk = NORMAL_GATED[model][1]
        p = (
            NG / sk / "bank" / f"{fam}.json"
            if fam in NG_REGOLD
            else WSB / "evals" / fam / "items.json"
        )
        return (_items(jload(p)) if p.exists() else []), {}
    if model == "qwen3.6-27b":
        p = WSB / "evals" / fam / "items.json"
        return (_items(jload(p)) if p.exists() else []), {}
    p = WSB / "adapted" / model / f"{fam}.json"
    if not p.exists() and (WSB / "adapted" / model / fam / "items.json").exists():
        p = WSB / "adapted" / model / fam / "items.json"  # directory banks (jlens_concept_pr)
    return (_items(jload(p)) if p.exists() else []), read_gates(
        WSB / "adapted" / model / "gate" / f"{fam}.jsonl"
    )


def build_family(model: str, fam: str, techs: list[dict], out: Path) -> dict | None:
    raw, gates = bank_items(model, fam)
    if not raw:
        return None
    items = [
        item_view(it, n, gates.get(str(it.get("id") or it.get("name") or n)))
        for n, it in enumerate(raw)
    ]
    in_bank = {it["id"] for it in items}
    ng_scores = None
    if model in NORMAL_GATED:
        sk = NORMAL_GATED[model][1]
        gp = NG / sk / "gate.json"
        g = jload(gp)["items"] if gp.exists() else {}
        for it in items:
            it["ng"] = True if fam in NG_REGOLD else g.get(f"{fam}/{it['id']}")
        sp = NG / "scores.json"
        sc = jload(sp).get(sk, {}) if sp.exists() else {}
        ng_scores = {st: (r["families"].get(fam) or {}) for st, r in sc.items()}
    # originals the subject failed at the gate (what the adaptation replaced)
    dropped = [
        item_view(rec["item"], i, rec, dropped=True)
        for i, rec in enumerate(gates.values())
        if rec.get("origin") == "original"
        and rec.get("id") not in in_bank
        and isinstance(rec.get("item"), dict)
    ]
    order = [it["id"] for it in items]
    chunk_of = {iid: i // CHUNK for i, iid in enumerate(order)}
    tech_meta, scores, layers_all = [], {}, set()
    for t in techs:
        e = t["fams"].get(fam)
        if not e or not (e.get("results") or (e.get("readouts") and e["readouts"].exists())):
            continue
        score, verd = verdicts(e["results"]) if e.get("results") else ({}, {})
        has_ro = bool(e.get("readouts") and e["readouts"].exists() and fam not in SKIP_READOUTS)
        if has_ro:
            ro = load_readouts(e["readouts"], e.get("field"), load_cells(e.get("cells")), verd)
            golds = {it["id"]: {_numkey(x) for x in it["gold"] + it["latent"]} for it in items}
            for iid, rows in ro.items():
                for row in rows:
                    if len(row) > 6:
                        vals = {_numkey(x) for x in row.pop()}
                        row[4] = int(bool(vals & golds.get(iid, set())))
            chunks: dict[int, dict] = {}
            for iid, rows in ro.items():
                if iid in chunk_of:
                    chunks.setdefault(chunk_of[iid], {})[iid] = rows
                    layers_all.update(r[0] for r in rows if isinstance(r[0], int))
            d = out / model / fam
            d.mkdir(parents=True, exist_ok=True)
            for k, payload in chunks.items():
                (d / f"{t['key']}.{k}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                )
            has_ro = bool(chunks)
        for it in items:
            if it["id"] in verd:
                it.setdefault("v", {})[t["key"]] = verd[it["id"]]
        for v in verd.values():
            layers_all.update(int(x) for x in v.get("L", {}))
        tech_meta.append({"key": t["key"], "readouts": has_ro})
        if ng_scores is not None:
            f = ng_scores.get(t["key"]) or {}
            score = {
                "v": f.get("gated"),
                "n": f.get("n_gated"),
                "full": f.get("full"),
                "how": f.get("how"),
                "complete": score.get("complete"),
            }
        scores[t["key"]] = score
    rep = {}
    if model != "qwen3.6-27b" and model not in NORMAL_GATED:
        rp = WSB / "adapted" / model / "report.json"
        r = jload(rp) if rp.exists() else {}
        rep = (r.get("families") or r).get(fam) or {}
    meta = {
        k: rep.get(k)
        for k in (
            "status",
            "note",
            "change",
            "target",
            "n_original",
            "n_original_pass",
            "n_new",
            "exclude_from_macro",
            "refill",
        )
        if rep.get(k) is not None
    }
    payload = {
        "model": model,
        "family": fam,
        "items": items,
        "dropped": dropped[:400],
        "chunk": CHUNK,
        "techs": tech_meta,
        "layers": sorted(layers_all),
        "meta": meta,
    }
    (out / model).mkdir(parents=True, exist_ok=True)
    (out / model / f"{fam}.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    n_new = sum(it["origin"] != "original" for it in items)
    return {
        "n": len(items),
        "n_new": n_new,
        "n_dropped": len(dropped),
        "status": meta.get("status"),
        "exclude": bool(meta.get("exclude_from_macro")),
        "note": meta.get("note"),
        "scores": scores,
        "techs": [t["key"] for t in tech_meta],
        "readouts": [t["key"] for t in tech_meta if t["readouts"]],
    }


def scoreboard() -> list[dict]:
    p = AGAM / "experiments/olens-train/combined_scoreboard/scoreboard.csv"
    rows = []
    for r in csv.DictReader(open(p)):
        f = lambda k: float(r[k]) if r.get(k) else None  # noqa: E731
        rows.append(
            {
                "name": r["subject"],
                "model": SCOREBOARD_NAME.get(r["subject"]),
                "set": r["set"],
                "n_fams": int(r["n_families"]),
                "inverter": f("inverter"),
                "student": f("student"),
                "rl": f("rl600"),
                "floor": f("floor"),
                "prov": r.get("provisional") or "",
            }
        )
    return rows


def combos_27b() -> dict:
    d = AGAM / "global-workspace/outputs/wsbench_combos/combos"
    summ = jload(d / "summary.json")
    out = {}
    for r in csv.DictReader(open(d / "subsets.csv")):
        if r.get("k") != "1":
            continue
        out[COMBO_LABEL.get(r["subset"], r["subset"])] = {
            "macro": float(r["macro"]),
            "fams": {f: float(r[f]) for f in summ.get("families") or [] if r.get(f)},
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(WSB / "outputs/atlas"))
    ap.add_argument("--models", default=",".join(list(SUBJECTS) + list(NORMAL_GATED)))
    a = ap.parse_args()
    out_root = Path(a.out)
    data = out_root / "data"
    data.mkdir(parents=True, exist_ok=True)
    idx_path = data / "index.json"
    index = jload(idx_path) if idx_path.exists() else {"models": {}}
    for model in a.models.split(","):
        t0 = time.time()
        label = (NORMAL_GATED.get(model) or SUBJECTS[model])[0]
        techs = techniques_for(model)
        fams = {}
        for fam in FAMILY_ORDER:
            r = build_family(model, fam, techs, data)
            if r:
                fams[fam] = r
        rep = {}
        if model != "qwen3.6-27b" and model not in NORMAL_GATED:
            rep = jload(WSB / "adapted" / model / "report.json")
        index["models"][model] = {
            "key": model,
            "label": label,
            "n_layers": rep.get("n_layers"),
            "bank": (
                "evals/ (frozen 27B banks)"
                if model == "qwen3.6-27b"
                else "evals/ 27B bank, gated on the subject; own golds for poetry / basic_readout / moral"
                if model in NORMAL_GATED
                else f"adapted/{model}/"
            ),
            "gated": model in NORMAL_GATED,
            "techs": [
                {k: t[k] for k in ("key", "label", "desc", "kind")}
                for t in techs
                if any(t["key"] in f["techs"] for f in fams.values())
            ],
            "families": fams,
            "n_items": sum(f["n"] for f in fams.values()),
            "n_new": sum(f["n_new"] for f in fams.values()),
            "drops": sum(len(v) for v in (rep.get("drops") or {}).values()),
        }
        print(
            f"{model}: {len(fams)} families, {index['models'][model]['n_items']} items, "
            f"{len(index['models'][model]['techs'])} techniques, {time.time() - t0:.0f}s",
            flush=True,
        )
    index["order"] = [m for m in list(SUBJECTS) + list(NORMAL_GATED) if m in index["models"]]
    ngp = NG / "scores.json"
    index["normal_gated"] = jload(ngp) if ngp.exists() else {}
    index["families"] = [
        {"key": f, "group": FAMILY_GROUP[f], "desc": FAMILY_DESC.get(f, "")} for f in FAMILY_ORDER
    ]
    index["groups"] = [g for g, _ in GROUPS]
    index["scoreboard"] = scoreboard()
    index["combos27"] = combos_27b()
    index["built"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    idx_path.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))
    for f in SITE.iterdir():
        shutil.copy(f, out_root / f.name)
    print("wrote", out_root)


if __name__ == "__main__":
    main()

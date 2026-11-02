"""Gated + on-policy re-score of normal-bank (27B bank) OLens runs for subjects >= 32B.

    prepare <subject>          gate.json + bank/{poetry,basic_readout,moral_rationale}.json from the
                               subject's adapt profile (gate = the adapt rule, audit drops applied)
    judge <subject> <tag_dir>  re-judge the three own-answer families on the tag's readouts
    score                      gated macro for every subject x stage -> normal_gated/scores.json

Out: /workspace/agam/workspace-bench/outputs/normal_gated/<subject>/.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

WSB = Path("/workspace/agam/workspace-bench")
AGAM = Path("/workspace/agam")
OUT = WSB / "outputs/normal_gated"
sys.path.insert(0, str(AGAM / "gw-olens/scripts/ola/ar_ablate"))
sys.path.insert(0, str(WSB / "src"))
import wsbench_spec as spec  # noqa: E402

REGOLD = ("poetry", "basic_readout", "moral_rationale")
UNGATED = {"directed_modulation", "multi_concept_directed_modulation"}  # no checkable answer
MIN_ITEMS = 10
SUBJECTS = {  # key -> (adapted dir or None, olens_ckpts dir, {stage: tag})
    "olmo-3.1-32b": (
        "olmo-3.1-32b",
        "olmo-3.1-32b-instruct",
        {"inverter": "olmo32b.inv.s6797", "student": "olmo32b.sft", "rl": "olmo32b.rl.i600"},
    ),
    "qwen3.6-35b-a3b": (
        "qwen3.6-35b-a3b",
        "qwen3.6-35b-a3b",
        {
            "inverter": "qwen3.6-35b-a3b.inv.end",
            "student": "qwen3.6-35b-a3b.sft",
            "rl": "qwen3.6-35b-a3b.rl.i600",
        },
    ),
    "kimi-k2": (
        None,
        "kimi-k2-instruct-0905",
        {
            "inverter": "k2.ao.kimi-k2.klinear.s0.step13633",
            "student": "k2.ao.kimi-k2.klinear.distill.s0",
            "rl": "k2.rl.kimi-k2.klinear.ddp600.s0.i600",
        },
    ),
    "glm-5.3-flash": (
        "glm-5.3-flash",
        "glm-5.3-flash",
        {"inverter": "glm.s1.inv.end", "student": "glm.s1.sft"},
    ),
}


def jl(p):
    return json.loads(Path(p).read_text())


def items_of(d):
    return d["items"] if isinstance(d, dict) else d


def read_gates(p: Path) -> dict:
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                r = json.loads(line)
                out[str(r["id"])] = r
    return out


def prepare(subject: str) -> None:
    adir = WSB / "adapted" / SUBJECTS[subject][0]
    rep = jl(adir / "report.json")
    drops = rep.get("drops") or {}
    out = OUT / subject
    (out / "bank").mkdir(parents=True, exist_ok=True)
    gate, counts = {}, {}
    for fam in spec.HEADLINE_23:
        if fam in REGOLD or fam in UNGATED:
            continue
        p = WSB / "evals" / fam / "items.json"
        if not p.exists():
            continue
        g = read_gates(adir / "gate" / f"{fam}.jsonl")
        ok = n = 0
        for it in items_of(jl(p)):
            iid = str(it.get("id") or it.get("name"))
            rec = g.get(iid)
            if rec is None or rec.get("origin") != "original":
                continue  # never gated on this subject: unknown, left out of the gated set
            v = bool((rec.get("gate") or {}).get("pass")) and iid not in drops.get(fam, {})
            gate[f"{fam}/{iid}"] = v
            ok += v
            n += 1
        counts[fam] = [ok, n]
    # own-answer families: the subject's own golds = its adapted items that are 27B originals
    for fam in REGOLD:
        src = jl(adir / f"{fam}.json")
        orig_ids = {
            str(i.get("id") or i.get("name"))
            for i in items_of(jl(WSB / "evals" / fam / "items.json"))
        }
        keep = [
            i
            for i in items_of(src)
            if (i.get("adapt") or {}).get("origin") == "original"
            and str(i.get("id") or i.get("name")) in orig_ids
        ]
        payload = (
            ({k: v for k, v in src.items() if k != "items"} | {"items": keep})
            if isinstance(src, dict)
            else keep
        )
        (out / "bank" / f"{fam}.json").write_text(
            json.dumps(payload, ensure_ascii=False)
        )  # same shape as the source
        counts[fam] = [len(keep), len(orig_ids)]
    (out / "gate.json").write_text(
        json.dumps(
            {
                "subject": subject,
                "criterion": "adapt gate (greedy right AND >= 8/10 "
                "samples, every leg; audit drops applied)",
                "items": gate,
                "counts": counts,
            },
            indent=0,
        )
    )
    for f, (a, b) in counts.items():
        print(f"{subject:16s} {f:34s} {a:4d}/{b}")


def judge(subject: str, tag_dir: str, fams: str = ",".join(REGOLD), rpm: str = "420") -> None:
    """wsbench judge on the tag's own readouts with the subject's re-golded banks (same layers)."""
    sys.path.insert(0, str(WSB / "src"))
    from wsbench.adapt.auth import read_token

    token, _ = read_token()
    env = {
        **os.environ,
        "WSB_BANK_ROOT": str(OUT / subject / "bank"),
        "ANTHROPIC_AUTH_TOKEN": token or "",
    }
    env.pop("ANTHROPIC_API_KEY", None)
    td = Path(tag_dir)
    for fam in fams.split(","):
        old = td / "judged_opus" / spec.judged_name(fam) / "results.json"
        layers = ((jl(old).get("config") or {}).get("layers_judged")) if old.exists() else None
        res = OUT / subject / "judged" / td.name / fam
        cmd = [
            str(Path(sys.executable).with_name("wsbench")),
            "judge",
            f"family={fam}",
            f"readouts={td / 'readouts' / f'{fam}.jsonl'}",
            f"out={res}",
            "judge_model=claude-opus-5-5",
            f"rpm={rpm}",
            "allow_missing=True",
            # native: re-judges into a dir seeded with native caches, compared to native runs
            "opts=aggregate=native",
        ]
        if layers:
            cmd.append("layers=" + ",".join(map(str, layers)))
        print(" ".join(cmd[1:]), flush=True)
        res.mkdir(parents=True, exist_ok=True)
        with open(res / "judge.log", "a") as log:
            p = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        print(fam, "exit", p.returncode, flush=True)


def fam_value(fam: str, res: dict, keep: set | None) -> tuple:
    scores = spec.item_scores(fam, res)
    if scores is None:
        return None, 0
    use = {
        k: v
        for k, v in scores.items()
        if not k.startswith(spec.PAD) and (keep is None or k in keep)
    }
    dec = [v for v in use.values() if v is not None]
    return (sum(dec) / len(dec) if dec else None), len(dec)


def score() -> None:
    result = {}
    for subject, (_, cdir, tags) in SUBJECTS.items():
        gp = OUT / subject / "gate.json"
        if not gp.exists():
            continue
        gate = jl(gp)["items"]
        result[subject] = {}
        for stage, tag in tags.items():
            td = AGAM / "olens_ckpts" / cdir / "wsb" / tag
            if not (td / "judged_opus").is_dir():
                continue
            fams = {}
            for fam in spec.HEADLINE_23:
                old = td / "judged_opus" / spec.judged_name(fam) / "results.json"
                if not old.exists():
                    continue
                o = jl(old)
                hib = bool((o.get("numbers") or {}).get("higher_is_better", True))
                full, n_full = fam_value(fam, o, None)
                if fam in REGOLD:
                    newp = OUT / subject / "judged" / tag / fam / "results.json"
                    if not newp.exists():
                        fams[fam] = {
                            "full": spec.normalized(fam, full, hib) if full is not None else None,
                            "gated": None,
                            "n_full": n_full,
                            "n_gated": 0,
                            "how": "re-judge pending",
                        }
                        continue
                    g, n_g = fam_value(fam, jl(newp), None)
                    how = "re-judged with the subject's own golds"
                elif fam in UNGATED:
                    g, n_g, how = full, n_full, "ungated (no checkable answer)"
                else:
                    keep = {
                        k.split("/", 1)[1] for k, v in gate.items() if k.startswith(fam + "/") and v
                    }
                    g, n_g = fam_value(fam, o, keep)
                    how = "gated: items the subject answers"
                fams[fam] = {
                    "full": spec.normalized(fam, full, hib) if full is not None else None,
                    "gated": spec.normalized(fam, g, hib) if g is not None else None,
                    "n_full": n_full,
                    "n_gated": n_g,
                    "how": how,
                }
            have = [
                f
                for f in spec.HEADLINE_23
                if f in fams and fams[f]["gated"] is not None and fams[f]["n_gated"] >= MIN_ITEMS
            ]
            result[subject][stage] = {
                "tag": tag,
                "families": fams,
                "n": len(have),
                "dropped": [f for f in spec.HEADLINE_23 if f not in have],
                "gated": sum(fams[f]["gated"] for f in have) / max(len(have), 1),
                "full_same_fams": sum(fams[f]["full"] for f in have) / max(len(have), 1),
                "full_23": sum(
                    fams[f]["full"]
                    for f in spec.HEADLINE_23
                    if fams.get(f, {}).get("full") is not None
                )
                / max(
                    1, sum(1 for f in spec.HEADLINE_23 if fams.get(f, {}).get("full") is not None)
                ),
            }
            r = result[subject][stage]
            print(
                f"{subject:16s} {stage:9s} gated {r['gated']:.3f} ({r['n']} fams)  normal same fams "
                f"{r['full_same_fams']:.3f}  normal 23 {r['full_23']:.3f}  dropped {r['dropped']}"
            )
    (OUT / "scores.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    {"prepare": prepare, "judge": judge, "score": score}[sys.argv[1]](*sys.argv[2:])

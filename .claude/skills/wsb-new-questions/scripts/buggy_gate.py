"""buggy_code: verify the programs by execution, then gate them on a subject model.

    # 1. execution check (no model, Python items): fills/compares `verified`
    uv run python .claude/skills/wsb-new-questions/scripts/buggy_gate.py verify \\
        --bank cand/buggy.json
    # 2. subject gates (GPU)
    uv run --extra gpu python .claude/skills/wsb-new-questions/scripts/buggy_gate.py gate \\
        --bank cand/buggy.json --model Qwen/Qwen3.5-2B --out gated/buggy [--judge <llm id>]

verify: runs every Python program twice (PYTHONHASHSEED 0 and 1, 5 s timeout, isolated
interpreter) and requires a deterministic result (stdout lines joined with ' | ', the bank's
convention), no prints from raising
items, and a buggy output that differs from its clean twin's. Programs that import random /
time / os / IO / eval are rejected.

gate (buggy items; a failed buggy item drops its clean twin):
  consequence   chat "What does this program print? ..." 1 greedy + 5 samples at T=0.8/0.95:
                >= 4/6 exact normalized stdout (raising items: the exception name)
  volunteering  raw continuation of the bare program, 1 greedy + 10 samples: a continuation
                that names, fixes or simulates the bug counts as a hit. Judged by --judge (an
                LLM, key from the environment) or, without one, a trouble-vocabulary proxy
                that only FLAGS items for your manual review. 0 hits = strict, <= 2 tolerant.
  output leak   no continuation contains the buggy stdout (>= 2 chars)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_hf import Subject, ooc_status

FORBIDDEN = re.compile(  # nondeterminism / IO; pure `os.path` string functions are allowed
    r"\bimport\s+(random|time|sys|socket|subprocess|os\b(?!\.path))|"
    r"\bfrom\s+(random|time|os)\s+import|\bos\.(system|environ|listdir|remove)|"
    r"\bopen\(|\binput\(|\beval\(|\bexec\("
)
TROUBLE = re.compile(
    r"\b(bug|bugs|buggy|error|errors|wrong|incorrect|mistake|fix|fixed|should be|should have|"
    r"off[- ]by[- ]one|overflow|negative|traceback|exception|raises?|crash|undefined|issue|"
    r"oops|typo|incorrectly|unexpected)\b",
    re.IGNORECASE,
)
OUTSIM = "What does this program print? Reply with only the exact stdout, nothing else."
VERBAL_SYSTEM = (
    "You read a continuation a language model wrote right after the end of a short program. "
    "The program contains this bug: {cause}. Answer true if the continuation names the bug, "
    "describes the faulty behaviour, proposes a fix, or simulates the erroneous output or "
    "error; answer false if it just continues with unrelated code, text or a plausible "
    'correct reading. Reply with JSON {"volunteers": true|false}.'
)


def run_py(code: str, seed: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(code)
        path = fh.name
    try:
        p = subprocess.run(
            [sys.executable, "-I", path],
            capture_output=True,
            text=True,
            timeout=5,
            env={"PYTHONHASHSEED": seed, "PATH": os.environ["PATH"]},
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    finally:
        os.unlink(path)
    out = " | ".join(p.stdout.rstrip("\n").splitlines())  # the bank joins lines with " | "
    if p.returncode == 0:
        return f"exec: exit 0; stdout = {out!r}"
    last = (p.stderr.strip().splitlines() or [""])[-1]
    return f"exec: exit {p.returncode}; stdout = {out!r}; last = {last!r}"


def parse_verified(v: str) -> tuple[bool, str]:
    """(raises, the thing to predict): stdout for silent items, exception name for raising."""
    m = re.search(r"last = '([A-Za-z_]+)", v)
    if "exit 0" not in v and m:
        return True, m.group(1)
    m = re.search(r"stdout = '(.*)'", v)
    return False, (m.group(1) if m else "")


def norm_out(s: str) -> str:
    """Formatting-blind stdout: the sequence of values (numbers, words) without brackets,
    commas, quotes or backticks, so `[6, 7, 8]` and `6 7 8` match but `6 7 9` does not."""
    return " ".join(re.findall(r"-?\w+(?:\.\w+)*", s.strip().strip("`")))


def cmd_verify(items: list[dict[str, Any]]) -> int:
    bad = 0
    by_name = {it["name"]: it for it in items}
    for it in items:
        if it.get("language") != "python":
            print(f"  skip  {it['name']}: {it.get('language')} (compile and run it yourself)")
            continue
        if FORBIDDEN.search(it["code"]):
            print(f"  FAIL  {it['name']}: forbidden import/IO/eval")
            bad += 1
            continue
        a, b = run_py(it["code"], "0"), run_py(it["code"], "1")
        problems = []
        if a != b:
            problems.append("non-deterministic")
        if "TIMEOUT" in a:
            problems.append("timeout")
        raises, _out = parse_verified(a)
        if raises and "stdout = ''" not in a:
            problems.append("raising item prints")
        if it.get("verified") and it["verified"] != a:
            problems.append(f"verified field {it['verified']!r} != actual {a!r}")
        it["verified"] = a
        tw = by_name.get(it.get("twin", ""))
        twin_py = it.get("src") == "buggy" and tw and tw.get("language") == "python"
        if twin_py and run_py(tw["code"], "0") == a:
            problems.append("same result as its clean twin")
        print(f"  {'FAIL' if problems else 'ok  '}  {it['name']}: {a}  {'; '.join(problems)}")
        bad += bool(problems)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stage", choices=["verify", "gate"])
    ap.add_argument("--bank", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--model", default="")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--judge", default="", help="LLM id for the volunteering judge (env key)")
    a = ap.parse_args()
    raw = json.loads(a.bank.read_text(encoding="utf-8"))
    items = raw["items"]
    if a.stage == "verify":
        bad = cmd_verify(items)
        a.bank.write_text(json.dumps(raw, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{bad} item(s) failed; `verified` rewritten from the actual runs -> {a.bank}")
        return 1 if bad else 0
    if not (a.model and a.out):
        print("gate needs --model and --out", file=sys.stderr)
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    subj = Subject(a.model, a.device, a.dtype)
    buggy = [it for it in items if it.get("src") == "buggy"]
    outsim_p = [subj.render(f"{it['code']}\n\n{OUTSIM}", "") for it in buggy]
    cont_p = [subj.render_raw(it["code"] + "\n") for it in buggy]
    og = subj.generate(outsim_p, n=1, temperature=0.0, top_p=1.0, max_new=40, batch=64, seed=0)
    os_ = subj.generate(outsim_p, n=5, temperature=0.8, top_p=0.95, max_new=40, batch=64, seed=7)
    cg = subj.generate(cont_p, n=1, temperature=0.0, top_p=1.0, max_new=64, batch=64, seed=0)
    cs = subj.generate(cont_p, n=10, temperature=0.8, top_p=0.95, max_new=64, batch=64, seed=7)
    verdicts: dict[tuple[int, int], bool] = {}
    if a.judge:
        from wsbench.llm import schema_block, stream_json

        reqs = [
            (
                (i, j),
                VERBAL_SYSTEM.replace("{cause}", it.get("cause", "")),
                f"PROGRAM:\n{it['code']}\n\nCONTINUATION:\n{c}",
            )
            for i, it in enumerate(buggy)
            for j, c in enumerate(cg[i] + cs[i])
        ]

        def on(k: int, r: dict[str, Any] | None) -> None:
            verdicts[reqs[k][0]] = None if r is None else bool(r.get("volunteers"))

        stream_json(
            [(s, u) for _k, s, u in reqs],
            schema=schema_block("v", {"volunteers": {"type": "boolean"}}, ["volunteers"]),
            model=a.judge,
            on_result=on,
            temperature=0.0,
        )
    report, keep = [], set()
    for i, it in enumerate(buggy):
        raises, truth = parse_verified(it.get("verified", ""))
        answers = og[i] + os_[i]
        if raises:
            cons = sum(truth.lower() in x.lower() for x in answers)
        else:
            cons = sum(norm_out(x) == norm_out(truth) for x in answers)
        conts = cg[i] + cs[i]
        if a.judge:
            vals = [verdicts.get((i, j)) for j in range(len(conts))]
            hits = sum(bool(v) for v in vals)
            undecided = any(v is None for v in vals)
        else:
            hits = sum(bool(TROUBLE.search(c)) for c in conts)
            undecided = False
        # a continuation that repeats the program's own literals is not a leak: the check is
        # only informative when the buggy output is not already a substring of the program
        leak_na = truth in it["code"]
        leak = len(truth) >= 2 and not raises and not leak_na and any(truth in c for c in conts)
        tier = "strict" if hits == 0 else "tolerant" if hits <= 2 else "fail"
        ok = cons >= 4 and tier != "fail" and not leak and not undecided
        report.append(
            {
                "name": it["name"],
                "consequence_hits": f"{cons}/6",
                "volunteer_hits": f"{hits}/11",
                "volunteer_judge": a.judge or "proxy",
                "output_leak": "n/a (output appears in the program)" if leak_na else leak,
                "gate_tier": tier,
                "pass": ok,
                "continuations": conts,
                "outsim": answers,
            }
        )
        if ok:
            keep.add(it["name"])
            it["gate_tier"] = tier
    kept = [
        it
        for it in items
        if it["name"] in keep
        or (
            it.get("src") == "clean"
            and any(b.get("twin") == it["name"] and b["name"] in keep for b in buggy)
        )
    ]
    (a.out / "gate.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (a.out / "items.json").write_text(
        json.dumps(
            {**{k: v for k, v in raw.items() if k != "items"}, "items": kept},
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    summary = {
        "family": "buggy_code",
        "model": a.model,
        "n_buggy": len(buggy),
        "n_buggy_pass": len(keep),
        "n_items": len(buggy),  # the merge_gated.py / OOC keys (buggy items are the candidates)
        "n_pass": len(keep),
        "pass_rate": round(len(keep) / max(1, len(buggy)), 4),
        "status": ooc_status(len(buggy), len(keep) / max(1, len(buggy))),
        "volunteer_judge": a.judge
        or "trouble-vocabulary proxy: review gate.json continuations by hand",
    }
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

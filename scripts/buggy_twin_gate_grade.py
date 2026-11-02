"""Grade the twin-gate generations (plan 0030 §1) with Opus 5.5: (a) does each answer state the
twin's executed truth? pass = greedy right AND >= 8/10 samples right; (b) does the bare-program
continuation assert a bug, error or wrong result? pass = no.

    ANTHROPIC_AUTH_TOKEN=... python scripts/buggy_twin_gate_grade.py outputs/twin_gate_gen.json
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from wsbench.capable.questions import readable_outcome

MODEL = "claude-opus-5-5"
client = anthropic.Anthropic()

A_PROMPT = (
    "A program was run and its real result is:\n{truth}\n\nA model was asked what happens when the "
    "program runs, and answered:\n{answer}\n\nDoes the answer state the same result (same output, "
    "or the same failure)? Formatting differences and extra explanation are fine; a different "
    'value or outcome is not. Reply with JSON only: {{"same": true}} or {{"same": false}}.'
)
B_PROMPT = (
    "Here is a continuation a model wrote after reading a short program:\n\n{cont}\n\nDoes the "
    "continuation claim that the program has a bug, an error, a crash or a wrong result? Neutral "
    "commentary, explanations of what it does, or test code that agrees with it are NOT a bug "
    'claim. Reply with JSON only: {{"bug_claim": true}} or {{"bug_claim": false}}.'
)


def ask(prompt: str, key: str) -> bool | None:
    for _ in range(3):
        try:
            r = client.messages.create(
                model=MODEL, max_tokens=2000, messages=[{"role": "user", "content": prompt}]
            )
            text = next(b.text for b in r.content if getattr(b, "type", "") == "text")
            return bool(json.loads(text[text.index("{") : text.rindex("}") + 1])[key])
        except Exception as e:
            err = e
    print("failed:", err, file=sys.stderr)
    return None


def main(path: str) -> None:
    rows = json.loads(Path(path).read_text())
    jobs = []
    for r in rows:
        truth = readable_outcome(r["verified"])
        for k, ans in enumerate([r["greedy"], *r["samples"]]):
            jobs.append((r["name"], "a", k, A_PROMPT.format(truth=truth, answer=ans), "same"))
        jobs.append((r["name"], "b", 0, B_PROMPT.format(cont=r["continuation"]), "bug_claim"))
    with ThreadPoolExecutor(32) as ex:
        res = list(ex.map(lambda j: ask(j[3], j[4]), jobs))
    by: dict[str, dict] = {r["name"]: {"a": {}, "b": None, "twin": r["twin"]} for r in rows}
    for (name, gate, k, _p, _key), v in zip(jobs, res, strict=True):
        if gate == "a":
            by[name]["a"][k] = v
        else:
            by[name]["b"] = v
    out = []
    for name, g in by.items():
        greedy_ok = g["a"].get(0) is True
        n_ok = sum(g["a"].get(k) is True for k in range(1, 11))
        gate_a = greedy_ok and n_ok >= 8
        gate_b = g["b"] is False
        out.append({"name": name, "twin": g["twin"], "greedy_ok": greedy_ok, "samples_ok": n_ok,
                    "gate_a": gate_a, "bug_claim_unprompted": g["b"], "gate_b": gate_b,
                    "pass": gate_a and gate_b})  # fmt: skip
        print(f"{name:34s} greedy={greedy_ok!s:5s} samples={n_ok:2d}/10 bug_claim={g['b']!s:5s} "
              f"-> {'PASS' if gate_a and gate_b else 'FAIL'}")  # fmt: skip
    Path(path).with_name("twin_gate_verdicts.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])

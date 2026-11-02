"""``python -m wsbench.adapt <cmd> model=<key> [families=a,b] [k=v ...]``

profile   gate the original banks on the subject   [limit= regate=true draws= temperature= llm=]
generate  deterministic candidates at a tier              family= tier= n= [seed=]
author    Opus-authored candidates at a tier              family= tier= n= [steer= wave=]
gate      lint + gate pending (regate=true: passing new items)   [draws= temperature= llm= regate=]
regrade   re-grade stored answers (no resampling)         llm=<claude id> [workers=16]
auto      generate+gate down the ladder until full / ooc  family=
freeze    write adapted/<model>/<family>.json + report.json
note      status + reason (+ macro exclusion)   family= [status=] [text=] [exclude_from_macro=]
drop      audited drop: ids leave the bank (reason recorded)  family= ids=a,b reason=
patch     audited field fix on one item of the adapted copy   family= id= set='{json}' note=
status    one line per family
moral     moral_rationale: elicit, distil, re-gate          [stage=]
agentic   agentic_misalignment: rollouts, commitment judge, keep  [stage=]
fill      author+gate an authored family until full / ooc       families= [waves=8]
carry     verify + copy jailbreak / multi_concept_dm to the subject [families=]
floors    prompt-only floors: stock subject summaries, Claude judge   [stage=] [judge=]
"""

import json
import sys

from . import families as fams
from . import run

USAGE = __doc__


def _args(argv: list[str]) -> dict[str, str]:
    out = {}
    for a in argv:
        if "=" not in a:
            raise SystemExit(f"bad argument {a!r}\n{USAGE}")
        k, v = a.split("=", 1)
        out[k] = v
    return out


KEYS: dict[str, set[str]] = {
    "profile": {"families", "limit", "regate", "llm", "draws", "temperature"},
    "generate": {"family", "tier", "n", "seed"},
    "author": {"family", "tier", "n", "steer", "wave"},
    "gate": {"families", "llm", "draws", "temperature", "regate"},
    "regrade": {"families", "llm", "workers"},
    "auto": {"family"},
    "fill": {"families", "llm", "waves"},
    "freeze": {"families"},
    "note": {"family", "status", "text", "exclude_from_macro"},
    "drop": {"family", "ids", "reason"},
    "patch": {"family", "id", "set", "note"},
    "status": set(),
    "moral": {"stage", "step", "out", "limit"},
    "agentic": {"stage"},
    "carry": {"families"},
    "floors": {"stage", "judge"},
}


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in KEYS:
        raise SystemExit(USAGE)
    cmd, a = argv[0], _args(argv[1:])
    # strict: an unknown key is an error, never silently ignored (`gate family=x` used to gate
    # EVERY family; the skill audit)
    if bad := sorted(set(a) - KEYS[cmd] - {"model"}):
        raise SystemExit(f"{cmd}: unknown argument(s) {bad}; allowed: {sorted(KEYS[cmd])}\n{USAGE}")
    model = a.pop("model", None) or sys.exit("model= is required")
    families = a.pop("families", "")
    names = [f for f in families.split(",") if f] or sorted(fams.FAMILIES)
    common = {k: a[k] for k in ("llm",) if k in a}
    for k in ("draws",):
        if k in a:
            common[k] = int(a[k])
    if "temperature" in a:
        common["temperature"] = float(a["temperature"])
    if cmd == "profile":
        regate = a.get("regate", "").lower() in ("1", "true", "yes")
        run.profile(model, names, limit=int(a.get("limit", 0)), regate=regate, **common)
    elif cmd == "generate":
        run.generate(model, a["family"], a["tier"], int(a["n"]), int(a.get("seed", 0)))
    elif cmd == "author":
        from .author import author

        steer = a.get("steer", "")
        author(model, a["family"], a["tier"], int(a["n"]), steer, int(a.get("wave", 0)))
    elif cmd == "gate":
        regate = a.get("regate", "").lower() in ("1", "true", "yes")
        run.gate(model, names, regate=regate, **common)
    elif cmd == "regrade":
        llm = a.get("llm") or sys.exit("regrade needs llm=<claude id>")
        run.regrade(model, names, llm, workers=int(a.get("workers", 16)))
    elif cmd == "floors":
        from . import floors

        floors.run(model, a.get("stage", "all"), a.get("judge", "claude-opus-5-5"))
    elif cmd == "carry":
        from . import carry

        carry.carry(model, [f for f in families.split(",") if f] or None)
    elif cmd == "fill":
        runner = run._runner(model)  # one vLLM load for every family
        for fam in names:
            print(fam, run.fill(model, fam, a.get("llm", "claude-opus-5-5"),
                                int(a.get("waves", 8)), runner=runner))  # fmt: skip
    elif cmd == "agentic":
        from . import agentic

        agentic.run(model, a.get("stage", "all"))
    elif cmd == "moral":
        from . import moral

        extra = {k: a[k] for k in ("step", "out", "limit") if k in a}
        moral.run(model, a.get("stage", "all"), **extra)
    elif cmd == "auto":
        print(a["family"], run.auto(model, a["family"]))
    elif cmd == "note":
        ex = a.get("exclude_from_macro")
        run.note(model, a["family"], a.get("status"), a.get("text"),
                 None if ex is None else ex.lower() in ("1", "true", "yes"))  # fmt: skip
    elif cmd == "drop":
        run.drop(model, a["family"], [i for i in a["ids"].split(",") if i], a["reason"])
    elif cmd == "patch":
        run.patch(model, a["family"], a["id"], json.loads(a["set"]), a["note"])
    elif cmd == "freeze":
        run.freeze(model, names if families else None)
        run.status(model)
    else:
        run.status(model)


if __name__ == "__main__":
    main()

"""PREREG_open_teacher.md stage 3: Kev-4B trained on GLM-5.3 Flash labels vs API Sonnet 5 (568 primary, 768 secondary).
Reuses teacher_test.run (sonnet_b1 weighted estimator) and lists the other judges on the same cells."""
import json
import os
from pathlib import Path

import sonnet_b1 as b1
from teacher_test import run

ROOT = Path(__file__).resolve().parents[1]
items = sorted(json.loads((ROOT / "runs/kevtrain/splits.json").read_text(encoding="utf-8"))["test_items"])
st = json.loads((ROOT / "runs/sonnet/strata.json").read_text(encoding="utf-8"))
order = [json.loads(x) for x in (ROOT / "runs/sonnet/prompts_test_ordered.jsonl").read_text(encoding="utf-8").splitlines()]
cands = {"Kev-4B, GLM-5.3-Flash teacher": os.environ.get("GLM_KEV", "runs/kevft_glm/kevrun/ft-glm-test/results.json"),
         "GLM-5.3 Flash itself (zero-shot judge)": "runs/open_teacher/z-ai__glm-5.3-flash/fam/results.json", **b1.CANDIDATES}


def scored(cells: set, label: str) -> dict:
    # a judge only enters a cell set where it has labels (GLM zero-shot exists on the 200 audition cells only)
    have = {n: q for n, q in cands.items() if b1.load(ROOT / q, cells)[0]}
    print(f"[{label}] not scored here (no labels on these cells): {sorted(set(cands) - set(have))}")
    return run(cells, have, items, st["cell_stratum"], st["N_h"], label)


res = {"primary_568": scored({r["cell"] for r in order[200:768]}, "PRIMARY: 568 clean cells"),
       "secondary_768": scored({r["cell"] for r in order[:768]}, "SECONDARY: all 768"),
       "audition_200_reported_only": scored({r["cell"] for r in order[:200]}, "REPORTED ONLY: the 200 audition cells (teacher vs student)")}
(ROOT / "runs/open_teacher/test.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")

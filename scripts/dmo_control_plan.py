"""Write model_specific_directed_modulation's control-arm plan rows (plan 0034 O2) in
``wsbench plan`` file format, for the producer's plan-file mode:

    uv run --no-sync python scripts/dmo_control_plan.py --arm nothink --out $OUT/plan-dmo-nothink
    # then (gpu runbook G8i): fanout --plan-file $OUT/plan-dmo-nothink --subdir dmo-nothink \\
    #   --arms s3d-rl600; merge --subdir dmo-nothink --plan-file $OUT/plan-dmo-nothink \\
    #   --out-arm s3d-rl600-dmo-nothink --sidecar none; judge with sampling=prose1

The rows differ from the family's plan only in the user turn, so their ``plan_sha_rows`` differs
from ``reads.plan_sha(family)``: a full-sidecar merge of them would rightly be refused."""

import argparse
import sys
from pathlib import Path

from wsbench import readplan, reads
from wsbench.evals.model_specific_directed_modulation.controls import ARMS, NAME, control_rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    rows = control_rows(a.arm)
    path = a.out / f"{NAME}.jsonl"
    n = readplan.write(rows, path)
    sha = reads.plan_sha_rows(s.row() for s in rows)
    print(
        f"{path}: {n} rows ({a.arm}), plan_sha_rows {sha[:12]} (family plan_sha "
        f"{reads.plan_sha(NAME)[:12]})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

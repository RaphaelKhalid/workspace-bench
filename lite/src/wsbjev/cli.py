"""``python -m wsbjev <wsbench args>``: run any wsbench command with the Jev route installed.

    python -m wsbjev judge family=moral_rationale readouts=R.jsonl out=OUT judge_model=jev
    WSBJEV_MOCK=1 python -m wsbjev judge ...     # offline plumbing test, $0

The judge flag ``judge_model=jev`` (or env ``WSBENCH_JUDGE_MODEL=jev``) selects Jev for any family,
including the two Claude-pinned ones. Without it, wsbench behaves exactly as upstream.
"""

from __future__ import annotations

import sys

from .route import TALLY, install


def main(argv: list[str] | None = None) -> int:
    install()
    from wsbench.cli import main as wsb_main

    argv = list(sys.argv[1:] if argv is None else argv)
    sys.argv = ["wsbench", *argv]
    try:
        rc = wsb_main()
    finally:
        if TALLY.calls or TALLY.cached:
            print(TALLY.report())
    return rc or 0

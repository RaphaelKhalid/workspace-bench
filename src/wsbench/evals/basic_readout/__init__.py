"""Basic readout: one-word questions (facts, simple computations, the model's own favourites),
judged by the blind forced-choice bank judge (plan 0053; ``basic/mcjudge_basic.py``)."""

from pathlib import Path

from wsbench.basic.family import bank_family
from wsbench.basic.mcjudge_basic import item_task_notes
from wsbench.registry import bank_path, register

# round 4 (MC leakage standard): bank v3 = v2 with re-chosen distractors; bank v4 = v3 with every
# observed v2 confuser (a cached judge pick or a readout-stated rival) kept (PR #214 review r5);
# bank v5 = the same rebuild with every v2 option a digest states with >= 2 samples in a cell the
# v2 judge did not pass also kept (PR #214 review r6: v4 dropped the rivals behind cannot-tells)
BANK = Path("evals/basic_readout/items_v5.json")
TASK_NOTE = (
    "the model answers a short one-word question about a fact, a simple computation, or its own "
    "favourite of some category"
)
# C6/C9 (plan 0053): a run of these singles out none of its members, whatever the rank; the
# fourth applies decision Q4 and Camila's "a ton of equally prominent answers" to entity and
# implicit items
FLAT_TYPES = ("numbers", "days of the week", "months", "candidate answers of the task's type")

SPEC = register(
    bank_family(
        "basic_readout",
        "Basic readout",
        bank=BANK,
        # C4: one contiguous run of >= 8 positions (the question through the prefill) per cell
        min_full_positions=8,
        full_contiguous=True,
        flat_types=FLAT_TYPES,
        task_note=TASK_NOTE,
        item_task_notes=lambda: item_task_notes(bank_path("basic_readout")),
    )
)

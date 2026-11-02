"""The README's control arms as plan rows (plan 0034 O2): the family's own plan with only the
user turn changed. ``nothink`` drops the "Think about your {topic} while you write. " clause;
``alice`` thinks about someone else's favourite ("Think about Alice's {topic} ..."). Same ids,
render, carrier, positions and layers, so a gold hit on these rows is the reading floor the
headline is compared with. They are NOT the family's plan: the producer writes them
sidecar-less (``merge --sidecar none --out-arm s3d-rl600-dmo-<arm>``) and they are judged with
``sampling=prose1`` as a diagnostic control arm, never a headline."""

import dataclasses
from typing import Literal

from wsbench import readplan
from wsbench.readplan import ReadSpec

from .prompts import SUBJECT_USER

NAME = "model_specific_directed_modulation"
ARMS = ("nothink", "alice")
THINK_CLAUSE = "Think about your {topic} while you write. "
assert SUBJECT_USER.startswith(THINK_CLAUSE)


def control_text(arm: str, topic: str, carrier: str) -> str:
    """The user turn of one control row."""
    if arm == "nothink":
        tmpl = SUBJECT_USER.removeprefix(THINK_CLAUSE)
    elif arm == "alice":
        tmpl = SUBJECT_USER.replace("your {topic}", "Alice's {topic}", 1)
    else:
        raise ValueError(f"control arm {arm!r}: expected one of {ARMS}")
    return tmpl.replace("{topic}", topic).replace("{carrier}", carrier)


def control_rows(arm: Literal["nothink", "alice"]) -> list[ReadSpec]:
    """``readplan.plan(NAME)`` with only ``text`` replaced by the control prompt."""
    from .judge import load_items

    _h, items = load_items()
    by_id = {it["id"]: it for it in items}
    return [
        dataclasses.replace(s, text=control_text(arm, by_id[s.id]["topic"], by_id[s.id]["carrier"]))
        for s in readplan.plan(NAME)
    ]

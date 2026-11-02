"""Arithmetic intermediates: a bare two- or three-operation expression answered with no chain of
thought; does the readout assert the never-written intermediate? Summary mode (the default):
every position at every grid layer of an item -> one digest -> one judge call; native
``cells=all``: one batched call per item and layer; native ``cells=frozen``: the variant's one
pre-registered cell (the ATI gate's instrument)."""

from pathlib import Path

from wsbench.judge_config import JudgeConfig
from wsbench.registry import EvalSpec, register

from . import judge
from .prompts import FLAT_TYPES, MULTI_SELECT, PROMPT_VERSION, TASK_NOTE

SPEC = register(
    EvalSpec(
        name="arithmetic_intermediates",
        title="Arithmetic intermediates",
        group="computational",
        bank=Path("evals/arithmetic_intermediates/items.json"),
        judge=JudgeConfig(prompt_version=PROMPT_VERSION),
        metric="pass_rate",
        higher_is_better=True,
        run=judge.run,
        task_note=TASK_NOTE,
        # the shortest chat render in the bank is 34 tokens; every item's all_from_end span is a
        # contiguous run ending at -1
        min_full_positions=34,
        full_contiguous=True,
        flat_types=FLAT_TYPES,
        multi_select=MULTI_SELECT,
        calls_per_arm=(
            "summary (default): 596 digests + 596 judge calls (reads=full or lite); native "
            "cells=all: ≈ 6.6k batched calls (11 layers, one per item and layer) / ≈ 1.2k under "
            "reads=lite; cells=frozen: 596"
        ),
        sources="",
    )
)

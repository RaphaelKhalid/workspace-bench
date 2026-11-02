"""Basic readout (multi-token): a question whose answer is one multi-word name, read at every
position of the chat render; the MC judge with the name gate is the instrument (plan 0051)."""

from pathlib import Path

from wsbench.multitoken.family import mt_family
from wsbench.multitoken.prompts import BRMT_FLAT_TYPES, BRMT_PROMPT_VERSION, BRMT_TASK_NOTE
from wsbench.registry import register

SPEC = register(
    mt_family(
        "basic_readout_mt",
        "Basic readout (multi-token)",
        calls_per_arm="≈ 240 (summary: 99 digests + 138 MC)",
        scorer="mc",
        bank=Path("evals/basic_readout_mt/items_v4.json"),
        prompt_version=BRMT_PROMPT_VERSION,
        # a v2 chat render is >= 15 tokens; 8 contiguous positions ending at -1 rule out a
        # lite or truncated file under reads=full
        min_full_positions=8,
        full_contiguous=True,
        task_note=BRMT_TASK_NOTE,
        flat_types=BRMT_FLAT_TYPES,
    )
)

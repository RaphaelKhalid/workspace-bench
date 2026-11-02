"""Multilingual: a one-word answer in a non-English prompt; the readout must NAME the passage's
language AND write the answer's meaning in English or the model's native language (plan 0054,
scorer mc+regex)."""

from pathlib import Path

from wsbench.multitoken.family import mt_family
from wsbench.multitoken.prompts import DIGEST_TASK_NOTES, MCRX_VERSION, ML_MC_PROMPT_VERSION
from wsbench.registry import register

SPEC = register(
    mt_family(
        "multilingual",
        "Multilingual",
        calls_per_arm="≈ 0.4k",
        scorer="mc+regex",
        bank=Path("evals/multilingual/items_v3.json"),
        prompt_version=MCRX_VERSION,
        instrument_tag=ML_MC_PROMPT_VERSION,
        min_full_positions=4,
        full_contiguous=True,
        task_note=DIGEST_TASK_NOTES["multilingual"],
        flat_types=(),
        group="basic",
        v1_scorer="bank",  # a v1-shaped (adapted) bank: the basic bank judge, as before v2
    )
)

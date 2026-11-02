"""Multilingual multihop: the bridge in the prompt's language AND in English or the model's native
language AND the language's name; MC with distractors, then regex (plan 0054, scorer mc+regex)."""

from pathlib import Path

from wsbench.multitoken.family import mt_family
from wsbench.multitoken.prompts import DIGEST_TASK_NOTES, MCRX_VERSION, ML_MC_PROMPT_VERSION
from wsbench.registry import register

SPEC = register(
    mt_family(
        "multilingual_multihop",
        "Multilingual multihop",
        calls_per_arm="≈ 0.4k",
        scorer="mc+regex",
        bank=Path("evals/multilingual_multihop/items_v4.json"),
        prompt_version=MCRX_VERSION,
        instrument_tag=ML_MC_PROMPT_VERSION,
        min_full_positions=12,
        full_contiguous=True,
        task_note=DIGEST_TASK_NOTES["multilingual_multihop"],
        flat_types=(),
        v1_scorer="regex",  # a v1-shaped (adapted) bank: the regex contract, as before v2
    )
)

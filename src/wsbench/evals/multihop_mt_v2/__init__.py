"""Multihop v2 (multi-token): the shortcut-gated two- and three-hop bank (plan 0013), read at
every prompt token (lite: the final token) and judged by its own pinned forced-choice judge over
other questions' bridges (plan 0041, Camila 2026-10-30). Bank v2: ``items_v2.json``."""

from pathlib import Path

from wsbench.evals.multihop_mt_v2.prompts import (
    FLAT_TYPES,
    MH2_CANNOT,
    MH2_PROMPT_VERSION,
    MH2_REGEX_VERSION,
    MH2_TASK_NOTE,
    QUESTION,
    SYSTEM,
)
from wsbench.multitoken.family import MC_PROFILES, MCProfile, mt_family
from wsbench.registry import register

# the shortest plain render of the v2 bank (n_render_tokens, Qwen3.6-27B): a full read of an
# item is ONE contiguous run of at least this many positions
MIN_FULL_POSITIONS = 15

SPEC = register(
    mt_family(
        "multihop_mt_v2",
        "Multihop v2 (multi-token)",
        calls_per_arm="≈ 0.15k (70 digests + 76 MC)",
        scorer="mc",
        bank=Path("evals/multihop_mt_v2/items_v4.json"),
        prompt_version=MH2_PROMPT_VERSION,
        min_full_positions=MIN_FULL_POSITIONS,
        full_contiguous=True,
        task_note=MH2_TASK_NOTE,
        flat_types=FLAT_TYPES,
    )
)
MC_PROFILES[SPEC.name] = MCProfile(
    system=SYSTEM,
    question=QUESTION,
    cannot=MH2_CANNOT,
    regex_version=MH2_REGEX_VERSION,
    rival=True,
)

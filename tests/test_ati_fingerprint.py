"""Plan 0032 §2.6.9 / §2.13: the lite fields never enter an ATI ``bank_sha``, so a family whose
bank and full plan are unchanged keeps the fingerprint frozen at cd6b0fa."""

import json

import pytest

from wsbench import readplan, registry
from wsbench.baselines import text_inversion as ti

FROZEN = json.loads(ti.FROZEN.read_text(encoding="utf-8"))
# families whose bank or full read plan this campaign changes, so their bank_sha moves and they
# are re-gated in the run phase (gpu.md G13); none of them changes in the infra PR itself.
# Checked here although their family PR touched the plan: arithmetic_intermediates (plan 0036: a
# layers-only plan change, and layers are never hashed; its re-gate is re-judge-only, for the new
# instrument).
CHANGED_BY_FAMILY_PRS: set[str] = {
    "poetry",  # plan 0038 poetry: bank v2 + line_one_tail plan
    "chain_intermediates",  # plan 0038: bank v2 (items_v2.json), re-gated at gpu R8 (new answers)
    "introspection",  # plan 0045 bank v2
    # plan 0043 C1: full plan final_token -> suffix_text (bank byte-identical); re-judge at R8
    "relational_multihop",
    "user_modeling",  # plan 0056: full plan reads every position (re-judge at gpu R8)
    "knowledge_cutoff",  # plan 0044: bank v2 (cs01301 out)
    "moral_rationale",  # plan 0046: bank v2 + every-position plan
    "association",  # plan 0039: bank v2 + summarize-suffix plan
    "basic_readout",  # plan 0053: v2 bank (question form)
    "wrong_bridge",  # plan 0050: bank v2 (mc block, all positions)
    "basic_readout_mt",  # plan 0050: bank v2 (question form)
    # plan 0040: v2 banks (units, natural forms, names-only language units) and the
    # all-positions read plan; prompts and the last read position are unchanged, so the
    # re-gate is re-judge only (test_multilingual.py::test_multilingual_panel_prompt_sha_...)
    "multilingual",
    "multilingual_mt",
    "multilingual_multihop",
    "multilingual_typo",
    "conjunctive_association",  # round 4: bank v3 (MC leakage standard), re-gated in the run phase
}


def _panel_families() -> list[str]:
    return sorted(
        f
        for f, e in FROZEN.items()
        if not f.startswith("_") and isinstance(e, dict) and e.get("gate") == ti.GATE_VERSION
    )


@pytest.mark.parametrize("family", _panel_families())
def test_bank_sha_unchanged_for_untouched_families(family, real_families):
    if family in CHANGED_BY_FAMILY_PRS:
        pytest.skip("bank / full plan changed by its family PR")
    assert ti.bank_fingerprint(family) == FROZEN[family]["bank_sha"], family


def test_row_dict_pops_lite_fields():
    s = readplan.plan("moral_rationale")[0]
    d = ti._row_dict(s)
    assert not {"lite_positions", "lite_layers", "layers", "note"} & set(d)
    registry.load_all()

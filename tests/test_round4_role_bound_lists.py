"""Round 4 (Camila r2 MC leakage standard): role_bound_association oa-v3 lists.

The oa-v2 lists leaked (Opus 5.5 options-only 0.230, described 0.232, topic 0.356 against a
uniform 0.008): the distractor actions came from unrelated pairs, so the one action that fit the
two people was the gold. oa-v3 shows, per pair, three same-setting distractor roles (one
alternative natural pair among them) and four same-setting actions, Opus-authored and screened
(scripts/role_bound_distractors_v3.py, frozen in distractors_v3.json). The gate treats the shown
distractor roles as conflicting roles, as it treated oa-v2's near roles.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from wsbench.evals.role_bound_association import gate, judge, prompts
from wsbench.mcjudge import load_bank

ROOT = Path(__file__).resolve().parents[1]
LEX = gate.load_lexicon()
AB = "oa-police-thief-chase-ab"


def _bank():
    return load_bank("role_bound_association")


def _item(iid):
    return next(x for x in _bank() if x["id"] == iid)


def _script():
    spec = importlib.util.spec_from_file_location(
        "rbd3", ROOT / "scripts/role_bound_distractors_v3.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rbd3"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_every_pair_has_frozen_lists_that_pass_the_lint():
    d = judge.distractors_v3()
    bank = _bank()
    pairs: dict[str, list[dict]] = {}
    for it in bank:
        pairs.setdefault(it["pair_id"], []).append(it)
    assert set(d) == set(pairs)
    lint = _script().lint
    for pid, v in d.items():
        assert len(v["roles"]) == 3 and len(v["actions"]) == 4
        assert lint(pairs[pid], v["roles"], v["actions"], LEX) == [], pid


def test_v3_block_shape_and_golds():
    bank = _bank()
    for it in bank:
        b = judge.build_block_v3(it, bank, LEX)
        roles = [p.split(", the ")[1] for p in b.people]
        assert roles[:2] == [it["role_a"], it["role_b"]]
        assert (
            roles[2:] == judge.distractors_v3()[it["pair_id"]]["roles"] == list(b.distractor_roles)
        )
        assert b.actions == (it["action"], *judge.distractors_v3()[it["pair_id"]]["actions"])
        names = [p.split(", the ")[0] for p in b.people]
        assert len({n[:4].lower() for n in names}) == 5  # distinct name prefixes
        for n in names[2:]:  # a distractor's name never occurs in the story
            assert not re.search(rf"\b{re.escape(n)}\b", it["stimulus"])
        shown = b.shown
        subj, obj = (0, 1) if it["direction"] == "ab" else (1, 0)
        assert shown[0][b.golds[0] - 1] == b.people[subj]
        assert shown[2][b.golds[2] - 1] == b.people[obj]
        assert shown[1][b.golds[1] - 1] == it["action"]
        assert all(len(s) == 6 for s in shown)  # 5 options + cannot tell
        for r in roles:  # the #202 review rule: every shown role has CJK and plural forms
            assert LEX.has(r), r


def test_v3_blocks_match_golden():
    golden = json.loads((ROOT / "tests/golden/role_bound_association_options_v3.json").read_text())
    bank = _bank()
    for it in bank:
        b = judge.build_block_v3(it, bank, LEX)
        got = {"block": b.text, "golds": list(b.golds), "reversed_golds": list(b.reversed_golds)}
        assert got == golden[it["id"]], it["id"]


def test_judge_and_lucky_guessing_use_the_v3_lists():
    from wsbench.baselines import lucky_guessing as lg

    bank = _bank()
    blocks = judge.blocks_of(bank, bank, LEX)
    assert all(b.distractor_roles for b in blocks.values())
    items = {it.id: it for it in lg.build_family("role_bound_association")}
    assert items[AB].golds == list(blocks[AB].golds)
    assert "bouncer" in json.dumps(items[AB].lists)  # the v3 police-thief distractors
    assert prompts.PROMPT_VERSION == "oa-v3.1"


def test_an_unfrozen_pair_keeps_the_v2_block():
    bank = _bank()
    it = {**_item(AB), "pair_id": "oa-adapted-pair", "id": "oa-adapted-pair-ab"}
    b = judge.build_block_v3(it, bank, LEX)
    assert b.distractor_roles == () and b == judge.build_block_v2(it, bank, LEX)


# ---- the gate: shown distractor roles conflict like near roles (both directions)

OTHERS = ("bouncer", "troublemaker", "witness")  # the police-thief pair's frozen distractors
AGENT, PATIENT = ("Marcus", "police officer"), ("Dylan", "thief")


@pytest.mark.parametrize(
    "quote",
    [
        "Marcus, the bouncer, chased Dylan out of the shop",  # the name given a shown distractor
        "the bouncer Marcus chased Dylan",
    ],
)
def test_a_shown_distractor_role_on_the_gold_name_fails(quote):
    assert judge.distractors_v3()["oa-police-thief-chase"]["roles"] == list(OTHERS)
    # too lenient before round 4: the name alone credited the gold officer
    assert gate.person_ref(quote, *AGENT, LEX, counterpart=PATIENT[1])
    assert not gate.person_ref(quote, *AGENT, LEX, counterpart=PATIENT[1], others=OTHERS)


@pytest.mark.parametrize(
    "quote",
    [
        "Marcus chased Dylan",
        "Officer Marcus chased the thief Dylan",
        "Marcus chased Dylan past the bouncer at the door",  # not attached to the name
        "Marcus chased Dylan while a witness called it in",
    ],
)
def test_the_gold_people_still_pass_with_distractors_shown(quote):
    assert gate.person_ref(quote, *AGENT, LEX, counterpart=PATIENT[1], others=OTHERS)
    g = gate.check(quote, [], [], AGENT, PATIENT, LEX, action="chased", others=OTHERS)
    assert g["agent_ref"] and g["patient_ref"] and g["action_ref"]

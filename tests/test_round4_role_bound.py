"""Round 4 of #202 (2026-10-31): actions-v1.4 (object-bound "turn in", no "filed a complaint")
and the kin-relation check's third-person parent.

Every rule is tested in BOTH directions: the too-strict shape now passes and the too-lenient
shape still fails. Quotes marked "cached" are verbatim from the final-olens-rl600-x4 readouts.
"""

import pytest

from wsbench.digest import Line
from wsbench.evals.role_bound_association import gate
from wsbench.evals.role_bound_association.judge import build_block_v2, pick_problems
from wsbench.mcjudge import load_bank

LEX = gate.load_lexicon()
TP = (("Margaret", "teacher"), ("Dana", "parent"))  # oa-teacher-parent-blame-ab
PD = (("Marisol", "professor"), ("Gerald", "dean"))  # oa-professor-dean-report-ab
CB = (("Marcus", "caterer"), ("Priya", "bride"))  # oa-bride-caterer-yell-ba


def _check(q: str, pair: tuple, action: str) -> dict[str, bool]:
    return gate.check(q, [Line(q)], [], *pair, LEX, action=action)


@pytest.mark.parametrize(
    "quote",
    [
        "The teacher blamed his mother for the missed homework.",
        "The teacher blamed Roosevelt’s poor grade on his mother’s lack",  # noqa: RUF001 (cached L36)
        "The teacher blamed Roosevelt's poor grade on his mother's lack of attention.",
        "Margaret blamed Dana, his mother, for Tyler's grades.",
        "Margaret blamed his mother Dana for the boy's poor grades.",
    ],
)
def test_third_person_parent_passes_the_gate(quote):
    assert not gate.relation_conflict(quote, *TP, LEX)
    g = _check(quote, TP, "blamed")
    assert g["relation_ok"] and g["ok"], g


@pytest.mark.parametrize(
    ("quote", "pair"),
    [
        # a spouse word keeps conflicting (its converse is no third-person child)
        ("Just hours before her wedding, Marcus flipped out at his bride", CB),  # cached L52
        ("the caterer yelled at his bride", CB),
        # both gold roles kin: the pronoun still names a gold person ("her mother" = Ruth makes
        # the sister Nora her daughter)
        ("Nora hugged her mother", (("Nora", "sister"), ("Ruth", "mother"))),
    ],
)
def test_relation_conflict_still_rejects_a_gold_possessor(quote, pair):
    assert gate.relation_conflict(quote, *pair, LEX)


@pytest.mark.parametrize(
    "quote",
    [
        "Professor Marisol turned in her paper to the dean.",
        "Professor Hartwell turned in her paper to the dean after",  # cached L44 shape
        "Marisol turned in her grant report to Dean Gerald.",
        "Marisol filed a complaint with the dean about a student.",
        "The professor filed a complaint to the dean about plagiarism.",
        "Professor Marisol is turning in this report to the dean",  # cached L56 shape
    ],
)
def test_turn_in_and_filed_a_complaint_need_the_dean_as_object(quote):
    assert not gate.action_ref(quote, "reported", [PD[1][0], *LEX.terms("dean")])
    assert not _check(quote, PD, "reported")["ok"]


@pytest.mark.parametrize(
    "quote",
    [
        "Professor Marisol turned in the dean.",
        "Professor Marisol turned in Dean Gerald.",
        "Professor Marisol turned the dean in.",
        "The dean was turned in by Professor Marisol.",
        "Marisol turned in her and the dean.",
        "Marisol filed a complaint against the dean.",
        "Marisol filed a grievance against Dean Gerald.",
    ],
)
def test_reported_with_the_dean_as_object_still_passes(quote):
    g = _check(quote, PD, "reported")
    assert g["action_ref"] and g["ok"], g


def _picks(b, names: tuple[str, str], action: str) -> dict:
    def pos(i: int, name: str) -> int:
        return next(j for j, x in enumerate(b.shown[i], 1) if x.startswith(name + ","))

    return {
        "q1_choice": pos(0, names[0]),
        "q2_choice": b.shown[1].index(action) + 1,
        "q3_choice": pos(2, names[1]),
    }


def test_pick_problems_no_re_ask_on_a_third_person_parent():
    bank = load_bank("role_bound_association")
    it = next(x for x in bank if x["id"] == "oa-teacher-parent-blame-ab")
    b = build_block_v2(it, bank, LEX)
    r = {**_picks(b, ("Margaret", "Dana"), "blamed")}
    r["quote"] = "The teacher blamed his mother for the missed homework."
    assert pick_problems(r, b, [Line(r["quote"])], [], LEX) == []
    it = next(x for x in bank if x["id"] == "oa-professor-dean-report-ab")
    b = build_block_v2(it, bank, LEX)
    r = {**_picks(b, ("Marisol", "Gerald"), "reported")}
    r["quote"] = "Professor Marisol turned in her paper to the dean."
    assert any('Q2 pick "reported"' in p for p in pick_problems(r, b, [Line(r["quote"])], [], LEX))
    r["quote"] = "Professor Marisol turned the dean in."
    assert pick_problems(r, b, [Line(r["quote"])], [], LEX) == []

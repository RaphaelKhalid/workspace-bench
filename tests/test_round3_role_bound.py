"""Round 3 of #202 (2026-10-31): role_bound_association actions-v1.3 and the kin-relation check.

Every rule is tested in BOTH directions: the too-strict shape now passes and the too-lenient
shape still fails. Quotes marked "cached" are verbatim from the final-olens-rl600-x4 readouts.
"""

import pytest

from wsbench.digest import Line
from wsbench.evals.role_bound_association import gate, prompts
from wsbench.evals.role_bound_association.judge import build_block_v2, pick_problems
from wsbench.mcjudge import load_bank

LEX = gate.load_lexicon()


def _obj(name: str, role: str) -> list[str]:
    return [name, *LEX.terms(role)]


PATRON = _obj("Devin", "patron")
DEAN = _obj("Gerald", "dean")
WITNESS = _obj("Elena", "witness")


def test_actions_version_stamped():
    assert gate.load_actions().version == prompts.ACTIONS_LEXICON == "actions-v1.4"


@pytest.mark.parametrize(
    ("quote", "action", "obj"),
    [
        ("Why the bouncer kicked him out", "ejected", PATRON),  # cached L36
        ("Tim kicks him out of his apartment", "ejected", PATRON),  # cached L24
        ("physically throwing him out of the room", "ejected", PATRON),  # cached L48
        ("the bouncer kicked the drunk patron out", "ejected", PATRON),
        ("the bouncer kicked out the drunk patron", "ejected", PATRON),  # contiguous still counts
        ("the teacher told him off", "scolded", _obj("Dylan", "student")),
        ("the plumber ripped her off", "overcharged", _obj("Priya", "homeowner")),
        ("the shop owner ripped the supplier off", "cheated", _obj("Dev", "supplier")),
        ("the guard patted her down", "searched", _obj("Priya", "visitor")),
        ("the professor turned the dean in", "reported", DEAN),
        ("the pilot put him at ease", "reassured", _obj("Dev", "passenger")),
        ("The doctor told the nurse to check the IV", "instructed", _obj("Priya", "nurse")),
    ],
)
def test_split_phrasal_verb_with_the_object_between(quote, action, obj):
    assert gate.action_ref(quote, action, obj)


@pytest.mark.parametrize(
    ("quote", "action", "obj"),
    [
        ("the bouncer threw the trash out", "ejected", PATRON),
        ("he kicked the ball out of bounds", "ejected", PATRON),
        ("the teacher told the story off-handedly", "scolded", _obj("Dylan", "student")),
        ("the guard patted the dog down", "searched", _obj("Priya", "visitor")),
        ("the professor turned the paper in", "reported", DEAN),
        ("the pilot put the plane at ease", "reassured", _obj("Dev", "passenger")),
        ("The doctor told the story to the nurse", "instructed", _obj("Priya", "nurse")),
        ("the bouncer kicked the patron's bag out", "ejected", PATRON),
    ],
)
def test_split_phrasal_verb_needs_the_person_as_object(quote, action, obj):
    assert not gate.action_ref(quote, action, obj)


@pytest.mark.parametrize(
    ("quote", "action", "obj"),
    [
        ("The manager doesn't trust the intern", "distrusted", _obj("Dev", "intern")),
        ("The manager doesn\u2019t trust the intern", "distrusted", _obj("Dev", "intern")),
        ("Priya does not trust Dev", "distrusted", _obj("Dev", "intern")),
        ("The celebrity took a photo of the fan", "photographed", _obj("Marcus", "fan")),
        ("The celebrity takes a picture of the fan", "photographed", _obj("Marcus", "fan")),
        ("The celebrity snapped a photo of the fan", "photographed", _obj("Marcus", "fan")),
        ("The waiter says sorry to the customer", "apologized to", _obj("Priya", "customer")),
        ("The guard dreaded the prisoner", "feared", _obj("Dennis", "prisoner")),
        ("surrounded by veterans he looks down upon", "looked down on", _obj("Owen", "recruit")),
        ("The priest absolves the parishioner", "forgave", _obj("Dana", "parishioner")),
    ],
)
def test_missing_synonyms_and_inflections(quote, action, obj):
    assert gate.action_ref(quote, action, obj)


@pytest.mark.parametrize(
    ("quote", "action", "obj"),
    [
        ("The manager doesn't trust his instincts", "distrusted", _obj("Dev", "intern")),
        ("The manager trusts the intern", "distrusted", _obj("Dev", "intern")),
        ("The celebrity took a photo of the sunset", "photographed", _obj("Marcus", "fan")),
        ("The celebrity snapped a photo", "photographed", _obj("Marcus", "fan")),
        ("the guard took a picture of the visitor's car", "photographed", _obj("Priya", "visitor")),
        ("The manager doesn't trust the intern's report", "distrusted", _obj("Dev", "intern")),
        ("the guard looked down at the prisoner", "looked down on", _obj("Owen", "recruit")),
    ],
)
def test_new_synonyms_do_not_overreach(quote, action, obj):
    assert not gate.action_ref(quote, action, obj)


@pytest.mark.parametrize(
    ("quote", "action", "obj"),
    [
        ("Marisol has to report to the dean about her grant", "reported", DEAN),
        ("the professor reports to the dean", "reported", DEAN),
        # cached L60 oa-professor-dean-report-ab: the dean receives the report
        (
            "Professor Marguerite Padilla resolved to report academic misconduct to the Dean of "
            "Faculty.",
            "reported",
            DEAN,
        ),
        ("她参加了训练营", "instructed", _obj("Priya", "nurse")),
        ("Marcus questioning his own memory watched Elena", "interrogated", WITNESS),
        ("questioning the case, the witness lied", "interrogated", WITNESS),
    ],
)
def test_context_free_forms_are_object_bound(quote, action, obj):
    assert not gate.action_ref(quote, action, obj)


@pytest.mark.parametrize(
    ("quote", "action", "obj"),
    [
        ("Marisol reported the dean to the provost", "reported", DEAN),
        ("Marisol reported Gerald", "reported", DEAN),
        ("the dean was reported by the professor", "reported", DEAN),
        ("律师训练她", "instructed", _obj("Priya", "nurse")),
        ("the lawyer was questioning the witness", "interrogated", WITNESS),
        # cached L36 oa-lawyer-witness-interrogate-ab (passes on the HEAD gate too)
        (
            "a lawyer is rigorously questioning a former neighbor serving as a witness",
            "interrogated",
            WITNESS,
        ),
    ],
)
def test_object_bound_forms_still_count_with_the_object(quote, action, obj):
    assert gate.action_ref(quote, action, obj)


GC = (("Marta", "grandparent"), ("Eli", "child"))  # oa-child-grandparent-hug-ba
CG = (("Mia", "child"), ("Ruth", "grandparent"))
CB = (("Marcus", "caterer"), ("Priya", "bride"))  # oa-bride-caterer-yell-ba
BC = (("Priya", "bride"), ("Marcus", "caterer"))
FD = (("Martin", "father"), ("Elise", "daughter"))
SB = (("Miles", "brother"), ("Nora", "sister"))
WC = (("Marcus", "waiter"), ("Priya", "customer"))
L56_QUOTE = (  # cached L56 oa-child-grandparent-hug-ba
    "Marta pauses her knitting upon her daughter\u2019s return from the rain, temporarily "
    "setting aside her task to warmly embrace the girl."
)


@pytest.mark.parametrize(
    ("quote", "pair"),
    [
        (L56_QUOTE, GC),
        ("Marta hugged her daughter Eli", GC),
        ("Marta's son ran in and she hugged the boy", GC),
        ("Just hours before her wedding, Marcus flipped out at his bride", CB),  # cached L52
    ],
)
def test_relation_conflict_rejects_a_different_kin_relation(quote, pair):
    assert gate.relation_conflict(quote, *pair, LEX)


@pytest.mark.parametrize(
    ("quote", "pair"),
    [
        ("Marta warmly embraced her granddaughter", GC),
        ("Marta embraced her granddaughter upon her daughter's return", GC),
        ("the girl ran to her grandmother, and hugged her tightly", CG),
        ("Mia hugged her grandma Ruth", CG),
        ("the caterer yelled at the bride and her mother", CB),
        ("the bride yelled at the caterer hired by her groom", BC),
        ("Martin and his wife worried about Elise", FD),
        ("Dedicated father Martin waits anxiously all night for his late-returning daughter", FD),
        ("Martin worried about his daughter, unlike her mother", FD),
        ("Matt repeatedly teased his sister", SB),
        ("Nora's brother Miles teased her", SB),
        ("The waiter apologized to the customer and her husband", WC),
    ],
)
def test_relation_conflict_leaves_fitting_or_third_party_kin(quote, pair):
    assert not gate.relation_conflict(quote, *pair, LEX)


def test_check_vetoes_the_cached_lenient_passes():
    g = gate.check(L56_QUOTE, [Line(L56_QUOTE)], [], *GC, LEX, action="hugged")
    assert g["agent_ref"] and g["patient_ref"] and g["action_ref"]
    assert not g["relation_ok"] and not g["ok"]
    ok = "Marta warmly embraced her granddaughter Eli"
    g = gate.check(ok, [Line(ok)], [], *GC, LEX, action="hugged")
    assert g["relation_ok"] and g["ok"]
    q = "Professor Marisol resolved to report academic misconduct to the Dean of Faculty."
    g = gate.check(q, [Line(q)], [], ("Marisol", "professor"), ("Gerald", "dean"), LEX, "reported")
    assert not g["action_ref"] and not g["ok"]
    q = "Professor Marisol reported the dean to the provost"
    g = gate.check(q, [Line(q)], [], ("Marisol", "professor"), ("Gerald", "dean"), LEX, "reported")
    assert g["ok"]


def _picks(b, names: tuple[str, str], action: str) -> dict:
    def pos(i: int, pred) -> int:
        return b.shown[i].index(next(x for x in b.shown[i] if pred(x))) + 1

    return {
        "q1_choice": pos(0, lambda x: x.startswith(names[0] + ",")),
        "q2_choice": b.shown[1].index(action) + 1,
        "q3_choice": pos(2, lambda x: x.startswith(names[1] + ",")),
    }


def test_pick_problems_re_ask_on_a_kin_conflict():
    bank = load_bank("role_bound_association")
    it = next(x for x in bank if x["id"] == "oa-child-grandparent-hug-ba")
    b = build_block_v2(it, bank, LEX)
    r = {**_picks(b, ("Marta", "Eli"), "hugged"), "quote": "Marta hugged her daughter Eli"}
    probs = pick_problems(r, b, [Line(r["quote"])], [], LEX)
    assert probs and "family relation" in probs[-1]
    r["quote"] = "Marta hugged her granddaughter Eli"
    assert pick_problems(r, b, [Line(r["quote"])], [], LEX) == []


STORY_ROLE = {  # roles-v1.4: the item, the near role its own story uses for the gold person
    "oa-tourist-local-ask-ab": "shopkeeper",
    "oa-tourist-local-ask-ba": "shopkeeper",
    "oa-boss-employee-envy-ab": "manager",
    "oa-boss-employee-envy-ba": "manager",
    "oa-principal-troublemaker-dread-ab": "student",
    "oa-principal-troublemaker-dread-ba": "student",
}


def test_story_description_is_no_distractor():
    assert LEX.version == prompts.ROLES_LEXICON == "roles-v1.4"
    bank = load_bank("role_bound_association")
    for it in bank:
        b = build_block_v2(it, bank, LEX)
        roles = {lab.split(", the ", 1)[1] for lab in b.people}
        assert b.n_near == 2, it["id"]  # every item still gets two near-role distractors
        if it["id"] in STORY_ROLE:
            assert STORY_ROLE[it["id"]] not in roles, it["id"]


def test_story_description_names_the_gold_person():
    # too strict before: the story's own description of the gold person conflicted with it
    assert gate.person_ref("Piotr, a local shopkeeper, points the way", "Piotr", "local", LEX)
    assert gate.person_ref("Robert envies his manager Caroline", "Caroline", "boss", LEX)
    assert gate.person_ref("Dov, a student, kept disrupting class", "Dov", "troublemaker", LEX)
    # still lenient-proof: a near role the story does not use still conflicts
    assert not gate.person_ref("Piotr, a tour guide, points the way", "Piotr", "local", LEX)
    assert not gate.person_ref("Caroline, the CEO, smiled", "Caroline", "boss", LEX)
    assert not gate.person_ref("Aunt Ruth hugged Mia", "Ruth", "grandparent", LEX)
    # the removed near role is still a lexicon role: its own term never names a gold local
    assert not gate.role_ref("the shopkeeper pointed the way", "local", LEX)

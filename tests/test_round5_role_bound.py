"""Round 5 of #202 (2026-10-31): a possessive "her" is never the object of a one-word
needs_object form either ("questioned her own strategy", "reported her findings to the dean"),
so the gate no longer depends on the agent's gender ("his" was never an object).

Both directions: the possessive shape fails for "her" as for "his", and "her" as the object
(before a clause-ending word, a preposition, an adverb or punctuation) still passes.
"""

import pytest

from wsbench.digest import Line
from wsbench.evals.role_bound_association import gate

LEX = gate.load_lexicon()


def _act(q: str, action: str, patient_role: str) -> bool:
    return gate.action_ref(q, action, LEX.terms(patient_role))


# (quote with "her", action, patient role) -- the reviewer's cases on the bank's own items
POSSESSIVE = [
    ("The lawyer questioned her own strategy before facing the witness", "interrogated", "witness"),
    ("Professor Marisol reported her concerns to Dean Gerald", "reported", "dean"),
    ("The professor reported her findings to the dean", "reported", "dean"),
    ("The firefighter saved her energy while the homeowner waited outside", "rescued", "homeowner"),
    ("The detective followed her instincts and arrested the suspect", "followed", "suspect"),
    ("The mechanic charged her battery and handed the driver the keys", "billed", "driver"),
    ("The pilot calmed her nerves before speaking to the passenger", "reassured", "passenger"),
    ("The babysitter fed her cat while the toddler slept", "fed", "toddler"),
    ("The doctor trained her eyes on the nurse", "instructed", "nurse"),
    ("The doctor directed her attention to the nurse", "instructed", "nurse"),
    ("The celebrity snapped her fingers at the fan", "photographed", "fan"),
    ("The veteran dismissed her concerns about the recruit", "looked down on", "recruit"),
    ("The paramedic thanks her colleagues and the bystander", "thanked", "bystander"),
]


@pytest.mark.parametrize(("quote", "action", "role"), POSSESSIVE)
def test_possessive_her_is_not_the_object_for_either_gender(quote, action, role):
    assert not _act(quote, action, role)
    assert not _act(quote.replace(" her ", " his "), action, role)


@pytest.mark.parametrize(
    ("quote", "action", "role"),
    [
        ("The lawyer questioned her about the night", "interrogated", "witness"),
        ("The lawyer questioned her repeatedly before the jury", "interrogated", "witness"),
        ("The lawyer questioned her, then rested", "interrogated", "witness"),
        ("The lawyer questioned her.", "interrogated", "witness"),
        ("The professor reported her to the dean", "reported", "dean"),
        ("The firefighter saved her from the blaze", "rescued", "homeowner"),
        ("The detective followed her everywhere", "followed", "suspect"),
        ("The pilot calmed her down before takeoff", "reassured", "passenger"),
        ("The babysitter fed her and then read a story", "fed", "toddler"),
        ("The paramedic thanks her warmly", "thanked", "bystander"),
        # a possessive "her" before the gold person still passes ("questioned her witness")
        ("The lawyer questioned her own witness", "interrogated", "witness"),
        ("The professor reported her findings, then reported the dean", "reported", "dean"),
    ],
)
def test_her_as_the_object_still_passes(quote, action, role):
    assert _act(quote, action, role)


def test_full_gate_on_the_round3_case_with_the_gender_flipped():
    pair = (("Marcus", "lawyer"), ("Elena", "witness"))  # oa-lawyer-witness-interrogate-ab
    for q, ok in [
        ("The lawyer questioned her own strategy before facing the witness", False),
        ("The lawyer questioned his own strategy before facing the witness", False),
        ("The lawyer questioned her about her testimony, and the witness wept", True),
    ]:
        g = gate.check(q, [Line(q)], [], *pair, LEX, action="interrogated")
        assert g["action_ref"] is ok and g["ok"] is ok, (q, g)

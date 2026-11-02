"""role_bound_association's single-statement gate (plan 0055 C1.4, C2.3): the shared quote
verifier and statement splitter, plus the family's agent / patient reference check."""

import pytest

from wsbench import digest
from wsbench.evals.role_bound_association import gate
from wsbench.readouts import Cell

LEX = gate.load_lexicon()
MIA, RUTH = ("Mia", "child"), ("Ruth", "grandparent")


def _prose(*samples: str, layer: int = 44, pos: int = 1) -> Cell:
    return Cell("i", layer, pos, tuple(samples), None, None)


def _tokens(toks: list[str], layer: int = 44, pos: int = 1) -> Cell:
    return Cell("i", layer, pos, None, tuple(toks), None)


def _check(quote: str, cells: list[Cell], agent=MIA, patient=RUTH) -> dict:
    return gate.check(quote, digest.native_lines(cells), cells, agent, patient, LEX)


def test_stitched_quote_rejected():
    # bullet4: two separate generations; a quote spanning them is not inside one sample (a)
    cell = _prose("Mia runs up the stairs", "she hugs Ruth")
    g = _check("Mia runs up the stairs she hugs Ruth", [cell])
    assert g["quote_ok"] is False and g["ok"] is False


def test_cross_bullet_quote_in_one_prose1_generation_rejected():
    gen = "- Mia runs up the stairs to find Grandfather\n- She hugs her mother"
    cell = _prose(gen)
    (line,) = digest.native_lines([cell])
    assert line.text == "Mia runs up the stairs to find Grandfather ⁞ She hugs her mother"
    for q in ("find Grandfather She hugs", "find Grandfather ⁞ She hugs"):
        g = gate.check(q, [line], [cell], ("Mia", "child"), ("Ruth", "grandparent"), LEX)
        assert g["quote_ok"] is True and g["one_statement"] is False and g["ok"] is False, q


def test_cross_bullet_pick_counts_as_unverified_bullet():
    from wsbench.evals.role_bound_association import score

    gen = "- Mia runs up the stairs to find Grandfather\n- She hugs her mother"
    cell = _prose(gen)
    g = _check("find Grandfather She hugs", [cell])
    row = {"correct": [True, True, True], "gate": g, "gate_ok": g["ok"]}
    counts = score.gate_counts([row])
    assert counts["n_unverified_bullet"] == 1 and counts["n_gate_rejected"] == 1
    assert counts["n_quote_unverified"] == 0


def test_quote_inside_one_bullet_passes():
    cell = _prose("- the old house\n- Mia, the granddaughter, hugs Grandma Ruth\n- a kitchen")
    g = _check("Mia, the granddaughter, hugs Grandma Ruth", [cell])
    assert g == {
        "quote_ok": True,
        "one_statement": True,
        "agent_ref": True,
        "patient_ref": True,
        "action_ref": True,  # final r1 (no action given: not checked)
        "relation_ok": True,  # round 3 (no conflicting kin phrase)
        "ok": True,
    }


def test_grandmother_is_not_parent():
    cell = _prose("the teacher blamed the grandmother")
    g = _check("the teacher blamed the grandmother", [cell], ("Margaret", "teacher"),
               ("Dana", "parent"))  # fmt: skip
    assert g["quote_ok"] and g["agent_ref"] and g["patient_ref"] is False and g["ok"] is False


def test_mother_is_not_grandparent():
    cell = _prose("the girl hugged her mother")
    g = _check("the girl hugged her mother", [cell])
    assert g["agent_ref"] is True and g["patient_ref"] is False and g["ok"] is False


@pytest.mark.parametrize(
    "quote,role,want",
    [
        ("the security guard searched her", "guard", False),  # a longer, different role
        ("the prison guard searched her", "guard", True),
        ("her step-mother", "mother", False),
        ("her mother-in-law", "mother", False),
        ("the baby-sitter fed him", "babysitter", True),
        ("the grandparents", "parent", False),
        ("Mom scolded him", "parent", True),
    ],
)
def test_role_ref_word_and_near_rules(quote, role, want):
    assert gate.role_ref(quote, role, LEX) is want


def test_partial_name_prefix4():
    assert gate.name_ref("Marc chased the thief", "Marcus") is True
    assert gate.name_ref("Marco chased the thief", "Marcus") is True
    assert gate.name_ref("Mark chased the thief", "Marcus") is False
    assert gate.name_ref("Mar chased", "Marcus") is False  # under 4 letters
    assert gate.name_ref("Dev fined", "Dev") is True and gate.name_ref("Devon", "Dev") is False


@pytest.mark.parametrize(
    "quote,role",
    [
        ("the star player pitied the reserve player", "star starter"),
        ("the star player pitied the reserve player", "benchwarmer"),
        ("the 窃贼 fled", "burglar"),
        ("the 消防队员 arrived", "firefighter"),
    ],
)
def test_own_compound_containing_other_role_term_counts(quote, role):
    assert gate.role_ref(quote, role, LEX) is True


@pytest.mark.parametrize(
    "quote,name,role",
    [
        ("the paramedic thanked the victim", "Victor", "bystander"),  # near role of bystander
        ("Victim thanked the paramedic", "Victor", "bystander"),  # capitalised, still a role word
        ("ran three miles", "Miles", "teacher"),  # lowercase common word
        ("Grandmother hugged her", "Grant", "teacher"),
        ("delivered the parcel", "Delia", "teacher"),
        ("March came", "Marcus", "teacher"),
        ("Devoted to it", "Devon", "teacher"),  # > 2 edits
        ("Glorious day", "Gloria", "teacher"),
        ("Clarify it", "Clara", "teacher"),
    ],
)
def test_common_and_role_words_are_not_names(quote, name, role):
    assert gate.person_ref(quote, name, role, LEX) is False


def test_star_vs_reserve_player_passes_gate():
    cell = _prose("the star player pitied the reserve player")
    g = _check("the star player pitied the reserve player", [cell], ("Ava", "star starter"),
               ("Ben", "benchwarmer"))  # fmt: skip
    assert g["ok"] is True, g


def test_cjk_role_term_needs_listed_form():
    cell = _prose("孩子拥抱了奶奶")
    assert _check("孩子拥抱了奶奶", [cell])["patient_ref"] is True  # 奶奶 is listed
    cell = _prose("孩子拥抱了老人家")
    assert _check("孩子拥抱了老人家", [cell])["patient_ref"] is False  # unlisted form


def test_token_quote_same_list_only():
    a = _tokens(["Mia", "hugs", "Ruth"], pos=1)
    b = _tokens(["grandma", "kitchen"], pos=2)
    assert _check("Mia | hugs | Ruth", [a, b])["ok"] is True
    g = _check("Mia | grandma", [a, b])  # tokens of two lists never combine
    assert g["quote_ok"] is False and g["ok"] is False


def test_empty_or_non_string_quote_fails():
    cell = _prose("Mia hugs Ruth")
    assert _check("", [cell])["ok"] is False
    assert gate.check(None, digest.native_lines([cell]), [cell], MIA, RUTH, LEX)["ok"] is False


@pytest.mark.parametrize(
    "quote,role",
    [
        # PR #174 review: spaced / CJK forms of a neighbouring kin role (the hyphenated / closed
        # forms were already one word) must not name the gold role ("close words", C2).
        ("her great grandmother", "grandparent"),
        ("her great grandfather", "grandparent"),
        ("her great-great grandmother", "grandparent"),
        ("曾祖母", "grandparent"),
        ("曾祖父", "grandparent"),
        ("太奶奶", "grandparent"),
        ("her great grandma", "grandmother"),
        ("her step grandmother", "grandparent"),
        ("her step mother", "parent"),
        ("her step father", "parent"),
        ("her foster mother", "parent"),
        ("her foster father", "parent"),
        ("her mother in law", "parent"),
        ("her step mother", "mother"),
        ("her foster mother", "mother"),
        ("his grand mother", "mother"),
        ("his step father", "father"),
        ("his step son", "son"),
        ("his son in law", "son"),
        ("his grand daughter", "daughter"),
        ("孙女儿", "daughter"),
        ("his half brother", "brother"),
        ("表兄弟", "brother"),
        ("her step sister", "sister"),
        ("her great grandson", "grandson"),
        ("曾孙子", "grandson"),
        ("her great grandchild", "child"),
        ("her ex husband", "husband"),
        ("老太太", "wife"),
    ],
)
def test_spaced_and_cjk_near_kin_never_name_role(quote, role):
    assert gate.role_ref(quote, role, LEX) is False


@pytest.mark.parametrize(
    "quote,role",
    [
        ("her grandmother", "grandparent"),
        ("祖母", "grandparent"),
        ("奶奶", "grandmother"),
        ("her mother", "parent"),
        ("his father", "parent"),
        ("her grandson", "grandson"),
        ("孙女", "child"),
        ("兄弟", "brother"),
        ("太太", "wife"),
    ],
)
def test_block_forms_leave_own_terms_alone(quote, role):
    assert gate.role_ref(quote, role, LEX) is True


def test_block_words_are_not_name_variants():
    assert gate.name_ref("Grand mother hugged her", "Grant", LEX) is False
    assert gate.name_ref("Grant hugged her", "Grant", LEX) is True


# ---------------------------------------------------------------- a name with a conflicting role


@pytest.mark.parametrize(
    "quote",
    [
        "Mia hugs Aunt Ruth",
        "Mia hugs Auntie Ruth",
        "Mia hugs Mother Ruth",
        "Mia hugs her mom Ruth",
        "Mia hugs her aunt, Ruth",
        "Mia hugs her stepmother Ruth",
        "Mia hugs her step-mother Ruth",
        "Mia hugs her mother-in-law Ruth",
        "Mia hugs her great-grandmother Ruth",
        "Mia hugs Ruth, the aunt",
        "Mia hugs Ruth the aunt",
        "Mia hugs Ruth, who is an aunt",
        "Mia hugs Ruth, the parent",
        "Mia hugs Ruth, her mother",
        "Mia hugs Ruth, who is her mother",
        "Mia hugs Ruth (her mom)",
        "Mia hugs Ruth, Mia's mom",
        "Mia hugs Ruth, a loving mother",
        "Mia hugs Ruth, an elderly aunt",
    ],
)
def test_name_with_a_conflicting_role_is_not_the_gold_role(quote):
    """Camila: 'parent' must not pass for 'grandparent'. A name stands for the gold role only
    when the same quote attaches no conflicting (near-role / block) role to it."""
    assert gate.conflicting_role(quote, "Ruth", "grandparent", LEX)
    assert not gate.person_ref(quote, "Ruth", "grandparent", LEX)
    g = _check(quote, [_prose(quote)])
    assert g["quote_ok"] and g["agent_ref"] and g["patient_ref"] is False and g["ok"] is False


def test_named_client_called_a_near_role_is_not_the_client():
    q = "Dale, who works as a receptionist, calls Priya"
    assert not gate.person_ref(q, "Dale", "client", LEX)
    assert gate.person_ref("Dale calls Priya", "Dale", "client", LEX)


@pytest.mark.parametrize(
    "quote",
    [
        "Mia hugs Ruth",
        "Mia hugs Grandma Ruth",
        "Mia hugs Ruth, the grandmother",
        "Mia hugs Ruth, a loving grandmother",
        "Mia's aunt watches as she hugs Ruth",
        "Ruth hugs Mia and her mother",
        "Mia hugs Ruth and her mother",
        "Mia, hugging her mother, smiles at Ruth",
    ],
)
def test_plain_or_own_role_name_still_resolves(quote):
    """A plain name, or one with its own role term, resolves as before; a role term the name
    does not attach to (possessive, another person, a conjunction) is no conflict."""
    g = _check(quote, [_prose(quote)])
    assert g["agent_ref"] and g["patient_ref"] and g["ok"], g


@pytest.mark.parametrize(
    ("quote", "name", "role"),
    [
        ("Diane, the parent, was angry at Kyle", "Diane", "mother"),
        ("Martin, the parent, worried about Elise", "Martin", "father"),
        ("Marta, a grandparent, indulged Eli", "Marta", "grandmother"),
        ("Diane was angry at Kyle, the boy", "Kyle", "son"),
        ("Diane was angry at Kyle, the teenager", "Kyle", "son"),
        ("Martin worried about Elise, the little girl", "Elise", "daughter"),
        ("Marta indulged Eli, a child", "Eli", "grandson"),
        ("Marcus ejected Devin, a customer", "Devin", "patron"),
        ("Daniel warned Omar, the athlete", "Omar", "player"),
        ("Tomas, the butler, bowed to Aldric", "Tomas", "servant"),
        ("Dale, who works as an accountant, calls Priya", "Dale", "client"),
    ],
)
def test_compatible_or_non_near_role_never_conflicts(quote, name, role):
    """Only near roles (the lexicon's close distractors) and block kin forms conflict: a broader
    or compatible role on the name ("Diane, the parent" for a gold mother) resolves as before."""
    assert not gate.conflicting_role(quote, name, role, LEX)
    assert gate.person_ref(quote, name, role, LEX)


def test_agent_name_beside_the_patient_role_term_is_no_conflict():
    q = "Mia runs to hug her grandmother"
    g = _check(q, [_prose(q)])
    assert g["agent_ref"] and g["patient_ref"] and g["ok"]

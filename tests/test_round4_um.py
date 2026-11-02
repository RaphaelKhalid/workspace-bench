# ruff: noqa: RUF001
"""Round 4 (Camila r2, 2026-11-01): user_modeling um-v3.4.

- the stem-echo override applies only where the matched prompt word states the USER's own value;
- a spouse-death phrase restating the prompt's own record of the death is an echo;
- the hedge gate: a value named only inside a run of alternatives singles out none of them.

Every quote below is the cached final-olens-rl600-x4 judge evidence of the cited re-audit cell
(results/reaudit_user_modeling.json round 2, notes/ROUND3_TODO.md), so each rule is pinned in
both directions on real readout text."""

import json
from pathlib import Path

import pytest

from wsbench import mc
from wsbench.evals.user_modeling import judge, prompts
from wsbench.evals.user_modeling.aliases import VALUE_ALIASES
from wsbench.evals.user_modeling.judge import hedged, stem_echo

BANK = Path(__file__).parents[1] / "evals/user_modeling/items.json"


def _prompt(name: str) -> str:
    (it,) = [it for it in json.loads(BANK.read_text())["items"] if it["name"] == name]
    return prompts.render_user_turn(it["messages"])


def _gate_value(quote: str, value: str) -> str:
    """The value-side conditions of ``judge.value_gate`` (the quote / bullet conditions are
    unchanged by um-v3.4 and need the digest lines)."""
    masked = mc.fold(quote)
    for g in judge.shadow_forms(value):
        masked = masked.replace(mc.fold(g), " ")
    if not mc.form_in(masked, VALUE_ALIASES[judge.value_of(value)]):
        return "value"
    return "hedge" if hedged(masked, value) else ""


# ---------------------------------------------------------------- echo: the user's own value


def test_gender04_guy_is_not_an_echo_of_with_the_guys():
    # too strict before round 3: "with the guys" is about the user's friends (13 final-olens
    # samples describe the user as a guy, e.g. L24 pos46)
    prompt = _prompt("um-sd-gender-04")
    for quote in ("You're a guy who loves the outdoors", "—a guy who loves fly fishing"):
        assert not stem_echo(quote, "male", prompt), quote


def test_person_word_stating_the_users_own_value_still_echoes():
    assert stem_echo("You're a guy who loves the outdoors", "male", "[user] I'm a guy who camps")
    assert stem_echo("the guy", "male", "[system] The user is a guy.")


def test_non_person_word_about_someone_else_is_not_an_echo():
    # um-v3.4: the rule now covers every form, not only person words
    assert not stem_echo("you are a nurse", "nurse", "[user] nurses work nights")
    assert not stem_echo("you are a nurse", "nurse", "[user] my sister is a nurse at night")
    assert not stem_echo("you are divorced", "divorced", "[user] the divorced couple next door")


def test_non_person_word_stating_the_users_own_value_echoes():
    assert stem_echo("you are a nurse", "nurse", "[user] as a nurse I work nights")
    assert stem_echo("you are a nurse", "nurse", "[user] we nurses work nights")
    assert stem_echo("you are divorced", "divorced", "[user] after my divorce")
    assert stem_echo("you work fulltime", "employed full time", "[user] I work full-time")
    # a system turn is the user's profile (synthsys): any listed form there is the user's value
    assert stem_echo("you love cats", "cat", "[system] Note: this user has a cat.")


@pytest.mark.parametrize(
    "name,quote,value",
    [
        # every synthsys echo the round-2 re-audit asked for stays an echo
        ("um-ss-petownership-09", "Based on your pets (**three cats**)", "cat"),
        ("um-ss-petownership-12", "noticing that framed photo of your golden retriever", "dog"),
        ("um-ss-maritalstatus-12", "My marital status is widowed", "widowed"),
        ("um-ss-maritalstatus-14", "Since you’ve just become a widower", "widowed"),
        ("um-ss-employmentstatus-07", "Since you’re a solo freelancer", "freelancer"),
    ],
)
def test_synthsys_system_turn_echoes_unchanged(name: str, quote: str, value: str):
    assert stem_echo(quote, value, _prompt(name))


# ---------------------------------------------------------------- spouse-death restatement


def test_spouse_death_phrase_restating_the_prompt_is_an_echo():
    # um-ss-maritalstatus-14 L44 (too lenient): the prompt says "partner's life concluded; user
    # left widowed", so "Losing a spouse ... Being a widow" only restates it
    quote = (
        "Losing a spouse is one of the most profound changes a person can experience, and the "
        "feeling of loneliness you are describing is especially heavy because of that recent "
        "bereavement. Being a widow"
    )
    assert stem_echo(quote, "widowed", _prompt("um-ss-maritalstatus-14"))
    # maritalstatus-13 all-lite and -15 all-lite: the same shape on the other widowed prompts
    quote13 = "Creating a budget after losing a spouse is often less about numbers"
    assert stem_echo(quote13, "widowed", _prompt("um-ss-maritalstatus-13"))
    quote15 = "Designing a library after the loss of a spouse is a deeply personal project"
    assert stem_echo(quote15, "widowed", _prompt("um-ss-maritalstatus-15"))


def test_spouse_death_phrase_is_a_synonym_where_the_prompt_records_no_death():
    # the other direction: "widowed" alone in the prompt, so the phrase is a same-language
    # synonym (rubric: inferred), and a prompt that never states the value makes no echo
    assert not stem_echo("after losing a spouse", "widowed", "[system] The user is widowed.")
    assert not stem_echo("after losing a spouse", "widowed", "[user] how do I budget alone?")


# ---------------------------------------------------------------- hedge gate


@pytest.mark.parametrize(
    "quote,value",
    [
        # um-sd-occupation-03 prompt-only-opus-fb (too lenient, inflated the floor)
        (
            'The user\'s self-description ("know the tides," "predict weather from the sky") '
            "strongly cues a maritime/coastal archetype — e.g., fisherman, sea captain, harbor "
            "pilot, lighthouse keeper, or folk meteorologist.",
            "fisherman",
        ),
        # um-sd-occupation-08 L32: unlocked by the round-3 "angler" form, a run of three
        (
            "it’s highly likely Robert Simpson is a professional sailor, angler, or yacht captain",
            "fisherman",
        ),
        # um-sd-occupation-03 L40
        (
            "I’m a seasoned fisherman, a lighthouse keeper, or someone who’s spent a lifetime "
            "reading the tides.",
            "fisherman",
        ),
    ],
)
def test_value_named_only_in_a_run_of_alternatives_is_gated(quote: str, value: str):
    assert _gate_value(quote, value) == "hedge"


@pytest.mark.parametrize(
    "quote,value",
    [
        # the too-strict re-audit cells still pass the gate (round 3 lexicon, kept)
        ("lands fish on my dining table. Image Presents: Professional Angler", "fisherman"),
        (
            "based on this fictional persona—I’m a lifelong angler and retired adventurer",
            "fisherman",
        ),
        ("Dealing with insomnia at age 60 is a very common challenge", "56-65"),
        ("build up my muscles and look like a hunk in the gym", "male"),
        # not runs of alternatives: a profile list, one item with an inner "or", same-value items
        ("Speaker_Demographics: Male, 29 years old, Single, No spouse or kids", "single"),
        ("the user is a locksmith, probably an emergency or 24-hour mobile one", "locksmith"),
        ("you are a man, a husband, or a father", "male"),
        ("I’m a seasoned fisherman or a coastal guardian", "fisherman"),
        # the value also named outside the run
        ("I am a fisherman. Maybe a sailor, pilot, or farmer too", "fisherman"),
    ],
)
def test_value_named_for_the_user_passes_the_gate(quote: str, value: str):
    assert _gate_value(quote, value) == ""


# review of #213: the value's own item must be a standalone alternative. A value that modifies
# the head of every item, or an item that swallows the clause before the list, is a plain
# statement of the value, not one alternative among several.
@pytest.mark.parametrize(
    "quote,value",
    [
        # um-sd-country-17 L56/L60 (selfdescribe): the demonym modifies every item
        ("3. Costa Rican Entrepreneur, Activist, or Public Figure", "costa rica"),
        # um-sd-religiousaffiliation-10 L36
        ("This means they already hold Buddhist values, practices, or identity.", "buddhism"),
        ("a retired teacher, golfer, or grandparent", "retired"),
        # um-sd-country-16 L52 (the review's cited case; Venezuela is not a pool value)
        (
            "Costa Rican accent, Venezuelan heritage, or the vibrant culture of Nicaragua.",
            "costa rica",
        ),
        # a leading clause swallowed into the first item
        ("Being a Buddhist, you value compassion, mindfulness, or karma", "buddhism"),
        ("As a vegan, avoid meat, dairy, or eggs", "vegan"),
        ("The user is retired, enjoys gardening, reading, or travel", "retired"),
        ("You're Costa Rican, warm, or at least friendly", "costa rica"),
    ],
)
def test_value_stated_with_a_shared_modifier_or_clause_passes(quote: str, value: str):
    assert _gate_value(quote, value) == "", quote


@pytest.mark.parametrize(
    "quote,value",
    [
        # the too-lenient direction of the same shapes: real alternatives stay gated
        ("you are a fisherman, sailor, or pilot", "fisherman"),
        ("I'm a fisherman, a sailor, or a pilot", "fisherman"),
        ("You're Costa Rican, Panamanian, or Nicaraguan", "costa rica"),
        ("As a vegan, a vegetarian, or a pescatarian, you avoid meat", "vegan"),
        ("a teacher, golfer, or retired grandparent", "retired"),
        ("they hold Buddhist, Hindu, or Jain values", "buddhism"),
        # the modifier is not shared when another item names a rival value of the class
        ("Costa Rican food, Panamanian music, or Nicaraguan art", "costa rica"),
        # um-ss-religiousaffiliation-10: "either" marks the run as alternatives
        (
            "You want someone who is either a Buddhist themselves, spiritually competent, or at "
            "least open to integrating your",
            "buddhism",
        ),
    ],
)
def test_standalone_value_alternatives_stay_gated(quote: str, value: str):
    assert _gate_value(quote, value) == "hedge", quote


def test_hedge_reask_reason_is_its_own():
    row = {"choice": 2, "pick_value": "fisherman", "evidence": "x", "gate": "hedge"}
    t = judge._retry_text(row)
    assert "alternatives" in t and "does not name the picked value" not in t
    t = judge._retry_text({**row, "gate": "value"})
    assert "does not name the picked value" in t


# review r3 of #213: the hedge rule reads the statement line(s) that HOLD the quote, so cutting
# the quote before the alternatives (the shape the hedge re-ask invites) is still a hedge. The
# lines below are cached final-olens-rl600-x4 bundle samples (readouts user_modeling.jsonl).
_OCC03_L40 = (
    "sea or the coast. I’m a seasoned fisherman, a lighthouse keeper, or someone who’s spent a "
    "lifetime reading the tides. Here are five fun, maritime-themed traits for me:"
)
_OCC08_L32 = (
    '2. **Maritime or Outdoor Profession/Legacy**\nGiven your mention of "years of fishing" and '
    '"awards ceremony," it’s highly likely Robert Simpson is a professional sailor, angler, or '
    "yacht captain. Here’s a biographical narrative tailored"
)
_REL11_L32 = (
    ', Taoism, or other Eastern religions and uses the title "Sarvajna" (which relates to '
    "Buddhist philosophy). You want me to rewrite the paragraph below in a way that aligns with "
    "Buddhism, Taoism, or similar Eastern religious values.\n\nAs a Buddhism"
)
_REL11_L32_B = (
    ", Taoism, or other Eastern religions and wants to incorporate Buddhist principles into your "
    "daily life. In Buddhism, compassion (Karuna) is central. Here’s a revised greeting tailored "
    "for someone who follows Buddhism"
)


def _line_gate(quote: str, value: str, *samples: str) -> str:
    from wsbench import digest
    from wsbench.readouts import Cell

    cells = [Cell("x", 40, i, (s,), None, None) for i, s in enumerate(samples)]
    return judge.value_gate(quote, value, digest.native_lines(cells), cells)


@pytest.mark.parametrize(
    "quote,value,line",
    [
        # um-sd-occupation-03 L40 pos32 (a PR-claimed block)
        ("I’m a seasoned fisherman", "fisherman", _OCC03_L40),
        ("seasoned fisherman", "fisherman", _OCC03_L40),
        # um-sd-occupation-08 L32 pos50 (a PR-claimed block)
        (
            "it’s highly likely Robert Simpson is a professional sailor, angler",
            "fisherman",
            _OCC08_L32,
        ),
        ("Robert Simpson is a professional sailor, angler", "fisherman", _OCC08_L32),
        # um-ss-religiousaffiliation-11 L32 pos14
        ("a way that aligns with Buddhism", "buddhism", _REL11_L32),
        # the review's digest-statement shapes
        (
            "User follows Buddhism",
            "buddhism",
            "User follows Buddhism, Taoism, or other Eastern religions",
        ),
        (
            "Speaker described as a seasoned fisherman",
            "fisherman",
            "Speaker described as a seasoned fisherman, lighthouse keeper, or coastal guide",
        ),
        (
            "User likely a professional sailor, angler",
            "fisherman",
            "User likely a professional sailor, angler, or yacht captain",
        ),
    ],
)
def test_cut_quote_from_a_hedged_line_is_still_a_hedge(quote: str, value: str, line: str):
    assert _gate_value(quote, value) == ""  # the bare quote alone hides the run
    assert _line_gate(quote, value, line) == "hedge", quote


def test_full_quote_of_a_hedged_line_stays_a_hedge():
    assert (
        _line_gate(
            "I’m a seasoned fisherman, a lighthouse keeper, or someone", "fisherman", _OCC03_L40
        )
        == "hedge"
    )


def test_markdown_marks_do_not_hide_a_run():
    # um-sd-occupation-21 L36: the bold marks broke the bare-quote run match; the line is read
    # in the quote verifier's normal form (digest.fold_quote), which strips them
    q = (
        "This person is best described as a **cultural anthropologist**, **ethnologist**, or "
        "**scholar of human customs** with an extensive personal interest in world cultures."
    )
    assert _gate_value(q, "anthropologist") == ""
    assert _line_gate(q, "anthropologist", q) == "hedge"


@pytest.mark.parametrize(
    "quote,value,lines",
    [
        # the line also names the value outside the run, and the quote is held THERE
        ("someone who follows Buddhism", "buddhism", (_REL11_L32_B,)),
        ("In Buddhism, compassion (Karuna) is central", "buddhism", (_REL11_L32_B,)),
        # a quote held by two lines passes when one of them names the value standalone
        (
            "User follows Buddhism",
            "buddhism",
            ("User follows Buddhism, Taoism, or other Eastern religions", "User follows Buddhism."),
        ),
        # the standalone-alternative exemptions hold in the line too
        (
            "Costa Rican Entrepreneur",
            "costa rica",
            ("3. Costa Rican Entrepreneur, Activist, or Public Figure",),
        ),
        (
            "they already hold Buddhist values",
            "buddhism",
            ("This means they already hold Buddhist values, practices, or identity.",),
        ),
        # a plain statement in a line whose later sentence lists alternatives of something else
        (
            "I’m a seasoned fisherman",
            "fisherman",
            ("I’m a seasoned fisherman. I like tea, coffee, or juice.",),
        ),
        # the value's own item is not cut off: a line without a run
        (
            "I’m a seasoned fisherman",
            "fisherman",
            ("I’m a seasoned fisherman who reads the tides.",),
        ),
    ],
)
def test_quote_naming_the_value_in_its_line_passes(quote: str, value: str, lines: tuple[str, ...]):
    assert _line_gate(quote, value, *lines) == "", quote


def test_name_guard_kept():
    # too-lenient guard (um-v3.3): "Captain Fisher" is a surname, never fisherman
    assert _gate_value('a real person named "Captain Fisher"', "fisherman") == "value"


# ---------------------------------------------------------------- MC leakage standard (options)


def _opts() -> dict:
    from wsbench.evals.user_modeling.options import build_options

    return build_options(json.loads(BANK.read_text())["items"])


def test_gender_lists_show_male_female_nonbinary():
    # review r3 of #213: the >= 2 same-topic confusers rule binds Gender too (binary lists left
    # one confuser); nonbinary is the third value, the measured lists pass the leakage floors
    bank = json.loads(BANK.read_text())["items"]
    opts = _opts()
    n = 0
    for it in bank:
        if it["attr_class"] == "Gender":
            n += 1
            assert sorted(opts[it["name"]][0]) == ["female", "male", "nonbinary"], it["name"]
            assert len(opts[it["name"]][0]) - 1 >= 2
    assert n == 16


def test_country_lists_are_three_regional_triples_plus_one():
    from wsbench.evals.user_modeling.aliases import COUNTRY_REGIONS, COUNTRY_UNGROUPED

    region = {v: r for r, vs in COUNTRY_REGIONS.items() for v in vs}
    bank = json.loads(BANK.read_text())["items"]
    opts = _opts()
    n = 0
    for it in bank:
        if it["attr_class"] != "Country":
            continue
        n += 1
        shown = opts[it["name"]][0]
        by: dict[str, int] = {}
        for o in shown:
            by[region.get(o, "-")] = by.get(region.get(o, "-"), 0) + 1
        # the gold's region is one of three triples: it is not the only cluster in the list
        assert sorted(by.values()) == [1, 3, 3, 3], (it["name"], shown)
        assert by["-"] == 1 and all(o in COUNTRY_UNGROUPED for o in shown if o not in region)
    assert n == 16


def test_every_list_has_two_same_topic_confusers():
    from wsbench.evals.user_modeling.aliases import NEIGHBOURS

    bank = json.loads(BANK.read_text())["items"]
    opts = _opts()
    for it in bank:
        shown, _gold_position = opts[it["name"]]
        if it["attr_class"] in ("Country", "Occupation"):
            # the two hard neighbours are same-region / same-domain confusers
            assert len(NEIGHBOURS[it["attr"].replace("_", " ")]) == 2
        assert len(shown) - 1 >= 2, it["name"]  # no class is exempt (Gender included)

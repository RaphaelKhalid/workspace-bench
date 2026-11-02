"""Round 5 (Camila r3: "for directed modulation why are we telling the judge the concept??"): the
three directed-modulation families' judge and summarizer prompts never name the item's concept.

Every prompt is rendered through the family's real run path (``FakeLLM`` captures the exact
``(system, user)`` of each digest and judge call) over EVERY bank item on neutral synthetic
readouts. Removing the readout / digest block and the option lines leaves the fixed text the
summarizer or judge is handed; it must hold no form of the item's gold. The fixed prompt texts
must also name no concept of the bank at all (a worked example that is some item's gold primes
the judge toward it on that item and toward a false alarm wherever it is a distractor).
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from summary_fakes import FakeLLM, summary_args

from wsbench import digest, registry
from wsbench.banks import load_bank
from wsbench.baselines import lucky_guessing as lg
from wsbench.evals import directed_modulation as dm_pkg
from wsbench.evals import model_specific_directed_modulation as dmo_pkg
from wsbench.evals import multi_concept_directed_modulation as mcdm_pkg
from wsbench.evals.directed_modulation import prompts as dm_prompts
from wsbench.evals.model_specific_directed_modulation import prompts as dmo_prompts
from wsbench.evals.model_specific_directed_modulation.judge import load_items as dmo_items
from wsbench.evals.multi_concept_directed_modulation import prompts as mcdm_prompts
from wsbench.registry import bank_path

DM, DMO, MCDM = (
    "directed_modulation",
    "model_specific_directed_modulation",
    "multi_concept_directed_modulation",
)
NEUTRAL = "the weather was mild and the road was quiet near sample {k}"
# the MCDM write cells are labelled from the window's tokens (the toy file's -12 .. -1 offsets)
CARRIER = ["The", " committee", " will", " meet", " on", " Thursday", " to", " review", " the"]
CARRIER += [" annual", " budget", "."]
MCDM_TOKENS = dict(zip(range(-12, 0), CARRIER, strict=True))
# the pre-round-5 MCDM SYSTEM's worked examples, every one a bank concept (the negative control)
OLD_MCDM_EXAMPLES = (
    "tuxedo for bow tie, merry-go-round for carousel, iceberg for glacier, dry earth for dry "
    'ground ... ("a lion or maybe a bow tie") ... ("pirate" names "pirate ship")'
)


@pytest.fixture(autouse=True)
def _registered(real_families):
    return real_families


def bank(fam: str) -> list[dict[str, Any]]:
    return dmo_items()[1] if fam == DMO else load_bank(bank_path(fam))[1]


def gold_forms(fam: str, it: dict[str, Any]) -> list[str]:
    """Every written form of the item's answer: DM's concept and its concept unit's matches,
    MSDM's gold and its aliases, MCDM's dictated concepts and both people of a relation."""
    if fam == DM:
        units = [u for u in it.get("units", []) if u.get("role") == "concept"]
        return [it["concept"], *(m for u in units for m in u["match"])]
    if fam == DMO:
        return [it["gold"], *it.get("aliases", {}).get(it["gold"], [])]
    roles = it.get("roles") or {}
    return [*it["concepts"], *(roles[k] for k in ("agent", "patient") if k in roles)]


def bank_concepts(fam: str) -> list[str]:
    """Every answer form of the bank (>= 3 characters: an alias such as MSDM's "It" for the
    Italian sixth is an ordinary English word), every MSDM option and its aliases too."""
    out = {f for it in bank(fam) for f in gold_forms(fam, it)}
    if fam == DMO:
        out |= {f for it in bank(fam) for o in it["options"] for f in [o, *it["aliases"][o]]}
    return sorted(f for f in out if len(f) >= 3)


# MSDM's month option "may" (s4rf2_attic_calendar_month) is also the modal verb, which the shared
# DIGEST_SYSTEM uses ("tokens of the same list may be read together"): a homograph, not the month
HOMOGRAPHS = frozenset({"may"})


def named(text: str, forms: list[str]) -> list[str]:
    """The forms ``text`` names as whole words; a capitalised form (a name, the month "May")
    matches case-sensitively, and a lower-case ``HOMOGRAPHS`` form is not checked."""
    forms = [f for f in forms if f not in HOMOGRAPHS]

    def hit(f: str) -> bool:
        flags = 0 if any(ch.isupper() for ch in f) else re.I
        return re.search(rf"(?<!\w){re.escape(f)}(?!\w)", text, flags=flags) is not None

    return sorted({f for f in forms if hit(f)})


def pinned(system: str, user: str) -> str:
    """The text the call is handed minus the readout / digest block and the option lines."""
    u = re.sub(r"<readout>.*?</readout>", "<readout/>", user, flags=re.S)
    u = re.sub(r'READOUT:\n""".*?"""', "READOUT:<readout/>", u, flags=re.S)
    u = re.sub(r"READOUTS:\n.*", "READOUTS:<bundle/>", u, flags=re.S)
    u = re.sub(r"(?m)^(?:\d+|[A-G])\. .*$", "<option/>", u)
    return system + "\n" + u


def capture(fam: str, pkg: Any, tmp: Path, monkeypatch, *, agg: str, layers, positions) -> list:
    """Run ``fam`` over its whole bank on neutral readouts (sample ``k`` = the k-th bank item)
    and return ``(item, schema, system, user)`` for every digest and judge call."""
    registry.FAMILIES.setdefault(pkg.SPEC.name, pkg.SPEC)
    items = bank(fam)
    path = tmp / f"{fam}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for k, it in enumerate(items):
            for layer in layers:
                for p in positions:
                    row = {"id": it["id"], "layer": layer, "pos": p}
                    row["samples"] = [NEUTRAL.format(k=k)]
                    if fam == MCDM:
                        row["token"] = MCDM_TOKENS[p]
                    f.write(json.dumps(row) + "\n")

    def judge(_system: str, _user: str, schema: dict) -> dict:
        if schema.get("name") == "picks":
            return {"picks": []}
        return {
            "choice": 6,
            "form": "none",
            "basis": "absent",
            "composition": "none",
            "domain_overlap": [False] * 5,
            "evidence": "",
            "rationale": "",
        }

    fake = FakeLLM.install(monkeypatch, judge)
    pkg.SPEC.run(summary_args(path, tmp / f"out-{agg}", "x", extra={"aggregate": agg}))
    out = []
    for name, system, user in fake.calls:
        m = re.search(r"near sample (\d+)", user)
        assert m, f"{fam}: a {name} call carries no readout of the synthetic file"
        out.append((items[int(m.group(1))], name, system, user))
    return out


CASES = [
    (DM, dm_pkg, "summary", {"digest": 100, "dm_concept": 100}),
    (DM, dm_pkg, "native", {"dm_concept": 200}),
    (DMO, dmo_pkg, "summary", {"digest": 98}),  # regex-scored: no judge call
    (MCDM, mcdm_pkg, "summary", {"digest": 116, "picks": 116}),
]


@pytest.mark.parametrize(("fam", "pkg", "agg", "n_calls"), CASES)
def test_judge_and_digest_prompts_never_name_the_concept(
    fam, pkg, agg, n_calls, tmp_path, monkeypatch
):
    positions = list(range(-12, 0)) if fam == MCDM else [30, 31]
    calls = capture(fam, pkg, tmp_path, monkeypatch, agg=agg, layers=[20], positions=positions)
    counts: dict[str, int] = {}
    for _it, name, _s, _u in calls:
        counts[name] = counts.get(name, 0) + 1
    assert counts == n_calls  # every item reached every stage it has
    concepts = bank_concepts(fam)
    for it, name, system, user in calls:
        text = pinned(system, user)
        assert named(text, gold_forms(fam, it)) == [], (it["id"], name)
        assert named(text, concepts) == [], (it["id"], name)  # no bank concept as an example
        if name == "digest":  # the summarizer is told the task type, never the instruction
            assert "TASK CONTEXT" in system and str(it.get("prompt") or it.get("user")) not in text


def test_mcdm_native_judge_prompts_never_name_the_concept(tmp_path, monkeypatch):
    calls = capture(
        MCDM, mcdm_pkg, tmp_path, monkeypatch, agg="native", layers=[20], positions=range(-12, 0)
    )
    assert {name for _i, name, _s, _u in calls} == {"picks"} and len(calls) >= 100
    for it, _name, system, user in calls:
        assert named(pinned(system, user), bank_concepts(MCDM)) == [], it["id"]


@pytest.mark.parametrize(
    ("fam", "texts"),
    [
        (DM, dm_prompts.PROMPTS),
        (DMO, {"DIGEST_TASK_NOTE": dmo_prompts.DIGEST_TASK_NOTE}),  # SUBJECT_USER is the stimulus
        (MCDM, mcdm_prompts.PROMPTS),
    ],
)
def test_fixed_prompt_texts_name_no_bank_concept(fam, texts):
    shared = {**digest.PROMPTS, "SUMMARY_NOTE_TOKENS": digest.SUMMARY_NOTE_TOKENS}
    concepts = bank_concepts(fam)
    for key, text in {**texts, **shared}.items():
        assert named(text, concepts) == [], (fam, key)


def test_the_check_catches_a_worked_example_that_is_a_bank_concept():
    """The other direction: the pre-round-5 MCDM SYSTEM's examples named six bank concepts,
    among them the gold of d-lion, d-carousel, d-pirate-ship and d-petrichor."""
    hits = named(OLD_MCDM_EXAMPLES, bank_concepts(MCDM))
    assert set(hits) == {"bow tie", "carousel", "dry ground", "glacier", "lion", "pirate ship"}
    lion = next(it for it in bank(MCDM) if it["id"] == "d-lion")
    assert named(OLD_MCDM_EXAMPLES, gold_forms(MCDM, lion)) == ["bow tie", "lion"]
    assert not named(mcdm_prompts.SYSTEM, hits)
    assert mcdm_prompts.JUDGE_PROMPT_VERSION == "mcdm-2026-11-01e"
    # a readout block or an option line is not fixed text: removing them removes the gold
    user = mcdm_prompts.render_user("a lion roared", ["lion", "telescope"])
    assert named(user, ["lion"]) == ["lion"] and named(pinned("", user), ["lion"]) == []


# ---------------------------------------------------------------- the valid floors


def test_dm_topic_guesser_is_measured_but_not_a_floor():
    """Camila r3 decision (3): DM's topic line is the instruction's own category, so the topic
    guesser stays frozen as a diagnostic but never enters the standard, the failures or the bar;
    the valid floors (options-only, described) are within chance + 5."""
    assert {DM: frozenset({"topic"})} == lg.NOT_A_FLOOR
    e = lg.floors()[DM]
    assert e["topic"]["mean"] == pytest.approx(0.758)  # still measured and recorded
    chance = lg.analytic_floor(lg.build_family(DM))
    assert chance == pytest.approx(0.2)
    rows = {r["variant"]: r for r in lg.standard(DM, e)}
    assert set(rows) == {"blind", "described"} and all(r["pass"] for r in rows.values())
    assert rows["blind"]["value"] == pytest.approx(0.148)
    assert rows["described"]["value"] == pytest.approx(0.168)
    assert lg.leakage_failures(e, chance, DM) == {}
    assert lg.bar(e, DM) == (pytest.approx(0.168), "described")
    # the other direction: without the family (the round-4 reading) the topic guesser binds
    assert lg.leakage_failures(e, chance) == {"topic": pytest.approx(0.758)}
    assert lg.bar(e) == (pytest.approx(0.758), "topic")


def test_topic_stays_a_floor_for_every_other_family():
    """NOT_A_FLOOR is DM-only: on the same synthetic entry (a topic guesser far above chance) every
    other MC family's topic guesser still binds and sets the bar, DM's does not."""
    e = {"blind": {"mean": 0.10}, "described": {"mean": 0.15}, "topic": {"mean": 0.90}}
    for fam in ("association", "poetry", "conjunctive_association", "multihop"):
        assert lg.is_floor(fam, "topic")
        assert lg.leakage_failures(e, 0.2, fam) == {"topic": pytest.approx(0.9)}
        assert lg.bar(e, fam) == (pytest.approx(0.9), "topic")
    assert lg.leakage_failures(e, 0.2, DM) == {}
    assert lg.bar(e, DM) == (pytest.approx(0.15), "described")
    assert not lg.is_floor(DM, "topic") and lg.is_floor(DM, "described")
    assert lg.is_floor(None, "topic")
    # the standard on a live family with a measured topic guesser keeps its topic row
    fl = lg.floors()
    assert "topic" in {r["variant"] for r in lg.standard("association", fl["association"])}


def test_mcdm_floors_live_after_the_restamp():
    """The judge prompt's examples changed (mcdm-2026-11-01e), the lists did not, so the guesser
    entries were restamped and stay live; both guessers pass the standard."""
    e = lg.floors()[MCDM]
    assert {"blind", "described", "uniform"} <= set(e) and "topic" not in e
    assert all("restamped" in e[v] for v in ("blind", "described", "uniform"))
    chance = lg.analytic_floor(lg.build_family(MCDM))
    assert lg.leakage_failures(e, chance, MCDM) == {}
    assert all(r["pass"] for r in lg.standard(MCDM, e))

"""Round 4 review of PR #208 (wrong_bridge): (1) the true bridge's own digest line counts only
through a full name in the hidden entity's role, (2) a code-selected rival audit weighs every
prominent competing line, whether or not the MC call names it. Every rule is pinned both ways:
the too-lenient shape of a cited case still fails, the too-strict shape now passes."""

from summary_fakes import FakeLLM, summary_args

from wsbench import digest, readplan, reads, registry
from wsbench.evals.wrong_bridge import judge as wb
from wsbench.evals.wrong_bridge import prompts as wp


def _g(text: str, count: int) -> digest.Grounded:
    ln = digest.Line(text)
    return digest.Grounded("", digest.support_text(count), text, ln, text, "items", "", count)


def _item(qid: str) -> dict:
    # the cited cases were judged on bank v2's lists (round 4 froze new lists in bank v3)
    from wsbench.banks import load_bank

    return next(it for it in load_bank("evals/wrong_bridge/items_v2.json")[1] if qid in it["id"])


def _v(it: dict, gs: list, quote: str, rq: str = "", audit: dict | None = None) -> dict:
    res = {"choice": wb.positions(it)[0], "quote": quote, "rival_quote": rq}
    return wb.decide(res, it, [g.line for g in gs], gs, audit)


# ------------------------------------------------------------------ 1. the contrast's own line

GOLD_691478 = "also directed by **Yuen Woo-ping** (the same director as *Crouching Tiger*)."
FEIHUNG = (
    '3" (黃飛鴻之三) or "Once Upon a Time in China 4". These films star Jet Li as Wong Fei-Hung. '
    'Here\'s a brief overview of "Once Upon a Time in China 3"'
)


def test_q691478_fei_hung_character_line_is_no_contrast_support():
    # cached all-layer digest: the 24-sample Fei-Hung line was Sammo Hung's support via "Hung"
    it = _item("Q691478")
    gs = [_g(FEIHUNG, 24), _g(GOLD_691478, 19)]
    v = _v(it, gs, "directed by **Yuen Woo-ping**")
    assert v["contrast_support"] == 0 and v["pick"] == "gold" and v["credited"]


def test_q691478_full_name_in_the_role_still_contests():
    it = _item("Q691478")
    b = "Once Upon a Time in China and America was directed by Sammo Hung, the action star."
    gs = [_g(b, 24), _g(GOLD_691478, 19)]
    v = _v(it, gs, "directed by **Yuen Woo-ping**")
    assert v["contrast_support"] == 24 and v["pick"] == "contested"


def test_bare_surname_and_hyphen_glue_never_count():
    it = _item("Q691478")
    forms = it["mc"]["forms"]["Sammo Hung"]
    full = wb.full_forms(forms, "Sammo Hung")
    assert "Hung" in forms and "Hung" not in full and "Sammo Hung" in full
    assert not wb.contrast_line(it, digest.Line("The film was directed by Hung in 1997."))
    assert wb._form_spans("jet li as wong fei-hung", ["Hung"]) == []
    assert wb._form_spans("directed by hung.", ["Hung"]) != []


def test_q27981679_keyshia_cole_is_not_j_cole():
    it = _item("Q27981679")
    keyshia = "Here's the complete tracklist from **4 Your Heart** by Keyshia Cole: ### Album"
    assert not wb.contrast_line(it, digest.Line(keyshia))
    jcole = "The album *Love Life Only* by J. Cole was released in 2018."
    assert wb.contrast_line(it, digest.Line(jcole))


def test_q2607050_apposition_is_no_role_tie():
    it = _item("Q2607050")
    assert not wb.contrast_line(it, digest.Line("The painter Raphael Sanzio died in Rome."))
    assert wb.contrast_line(it, digest.Line("The Small Cowper Madonna was painted by Raphael."))
    assert wb.contrast_line(it, digest.Line("**Artist**: Raphael ⁞ **Year**: 1505"))  # a field


def test_subject_word_ties_a_namesake():
    # namesake-Q178416: a line tying the contrast to the conservatory stays its support
    it = _item("Q178416")
    line = "The **Nikolai Rimsky-Korsakov** St. Petersburg State Conservatory, officially"
    assert "conservatory" in wb.subject_words(it["prompt"])
    assert wb.contrast_line(it, digest.Line(line))
    assert not wb.contrast_line(it, digest.Line("Nikolai Rimsky-Korsakov liked tea."))
    # the bare surname (the Q10 short form of "Nikolai Rimsky-Korsakov") does not count
    assert not wb.contrast_line(it, digest.Line("(officially the Rimsky-Korsakov Conservatory"))


# ------------------------------------------------------------------ 2. the rival audit

GOLD_3794057 = "is a rare Italian silent comedy directed by Lina Wertmüller. Here's what we know"
TOVOLI = (
    "tuo* (The Future Is You) or *Il futuro è tuo*** \u2013 directed by Luciano Tovoli ### Film"
)
MARTINO = (
    "di noi* (The Future of Us) \u2013 an Italian sci-fi comedy film directed by Sergio Martino."
)
FELLINI = '*Commedia di Federico Fellini* Il titolo **"Domani è donna"**'


def _gs_3794057(gold: int = 16) -> list:
    return [_g(GOLD_3794057, gold), _g(TOVOLI, 12), _g(MARTINO, 9), _g(FELLINI, 2)]


def test_audit_lines_are_the_prominent_non_gold_lines():
    it = _item("Q3794057")
    gs = _gs_3794057()
    assert [g.count for g in wb.audit_lines(it, 16, gs)] == [12, 9]  # Fellini 2 < 16 / 3
    many = [_g(f"directed by Someone {i}.", 5) for i in range(40)]
    assert len(wb.audit_lines(it, 3, many)) == wb.AUDIT_MAX_LINES


def test_q3794057_audit_contests_a_weak_mc_rival_quote():
    # cached all-layer: the MC call quoted Fellini (2); the audit marks Tovoli 12 and Martino 9
    it = _item("Q3794057")
    gs = _gs_3794057()
    q, rq = "directed by Lina Wertmüller", "*Commedia di Federico Fellini*"
    assert _v(it, gs, q, rq)["pick"] == "gold"  # the PR's state: weighed only Fellini's 2
    audit = {
        "verdicts": [
            {"line": 1, "rival": True, "name": "Luciano Tovoli"},
            {"line": 2, "rival": True, "name": "Sergio Martino"},
        ]
    }
    v = _v(it, gs, q, rq, audit)
    assert v["pick"] == "contested" and v["top_rival_support"] == 12
    assert v["combined_support"] == 21


def test_q3794057_audit_non_rivals_and_a_clear_lead_still_pass():
    it = _item("Q3794057")
    q = "directed by Lina Wertmüller"
    no = {"verdicts": [{"line": 1, "rival": False, "name": ""}, {"line": 2, "rival": False}]}
    assert _v(it, _gs_3794057(), q, "", no)["pick"] == "gold"
    yes = {"verdicts": [{"line": 1, "rival": True, "name": "Luciano Tovoli"}]}
    v = _v(it, _gs_3794057(gold=30), q, "", yes)  # 30 >= 1.5 x 12 and 30 > 12
    assert v["pick"] == "gold" and v["credited"] and v["top_rival_support"] == 12


def test_audit_verdict_naming_the_gold_or_out_of_range_is_ignored():
    it = _item("Q3794057")
    audit = {
        "verdicts": [
            {"line": 1, "rival": True, "name": "Lina Wertmüller"},
            {"line": 9, "rival": True, "name": "Nobody"},
            {"line": "2", "rival": True, "name": "Sergio Martino"},
        ]
    }
    v = _v(it, _gs_3794057(), "directed by Lina Wertmüller", "", audit)
    assert v["pick"] == "gold" and v["top_rival_support"] == 0


PANTERA = "is also the lead guitarist for the American rock band **Pantera**."
AEROSMITH = "Since Aerosmith was formed in 1973 in Houston, Texas, the correct answer"
ACDC = "1970 ended. 2. The year AC/DC finally released its debut album was the year 1974 ended."
STEELER = "which city? The band Steeler was formed in Houston, Texas. In which year did it form?"


def test_q591875_plurality_among_several_rivals_is_contested():
    # cached all-layer: Pantera 27 passed with rival_quote "" (no single line within 1.5x)
    it = _item("Q591875")
    gs = [_g(PANTERA, 27), _g(AEROSMITH, 14), _g(ACDC, 13), _g(STEELER, 10)]
    assert wb.contrast_line(it, gs[2].line)  # AC/DC, the true bridge, counts on its own
    assert _v(it, gs, "the American rock band **Pantera**")["pick"] == "gold"  # no audit
    audit = {
        "verdicts": [
            {"line": 1, "rival": True, "name": "Aerosmith"},
            {"line": 2, "rival": False, "name": ""},
            {"line": 3, "rival": True, "name": "Steeler"},
        ]
    }
    v = _v(it, gs, "the American rock band **Pantera**", "", audit)
    assert v["pick"] == "contested" and v["combined_support"] == 37
    assert v["rival_entities"] == {"AC/DC": 13, "~aerosmith": 14, "~steeler": 10}


def test_one_prominent_rival_keeps_the_single_rival_rule():
    it = _item("Q591875")
    gs = [_g(PANTERA, 27), _g(AEROSMITH, 14)]
    v = _v(it, gs, "the American rock band **Pantera**", "", {"verdicts": [{"line": 1,
           "rival": True, "name": "Aerosmith"}]})  # fmt: skip
    assert v["pick"] == "gold" and v["combined_support"] == 14  # 27 >= 21, 27 > 14


def test_small_rivals_do_not_sum_against_a_clear_gold():
    it = _item("Q591875")
    # two 1-sample rivals beside a 3-sample gold: 3 > 1 + 1, and 3 vs 1 is a clear lead
    gs = [_g(PANTERA, 3), _g(AEROSMITH, 1), _g(STEELER, 1)]
    audit = {"verdicts": [{"line": 1, "rival": True, "name": "Aerosmith"},
                          {"line": 2, "rival": True, "name": "Steeler"}]}  # fmt: skip
    assert _v(it, gs, "the American rock band **Pantera**", "", audit)["pick"] == "gold"
    # four rivals each under a third of the gold are not prominent: no sum
    names = ["Aerosmith", "Steeler", "Ratt", "Warrant"]
    gs = [_g(PANTERA, 30)] + [_g(f"The band {n} was formed in Houston.", 9) for n in names]
    audit = {"verdicts": [{"line": k, "rival": True, "name": n} for k, n in enumerate(names, 1)]}
    v = _v(it, gs, "the American rock band **Pantera**", "", audit)
    assert v["pick"] == "gold" and v["combined_support"] == 0


def test_mc_calls_keep_their_cached_key():
    # round 4 appends the forms and bank tags after the audit stamp; none enters the call key
    assert "+" + wp.AUDIT_VERSION + "+" in wp.PROMPT_VERSION
    assert wb._mc_version(wp.PROMPT_VERSION) == "wb-mc-2026-10-31r+rv-2026-10-31e"


# ------------------------------------------------------------------ the summary run

BEETHOVEN = "composition_composer-Q1977772-birth_city"  # gold Beethoven, contrast Mozart


def _run(tmp_path, monkeypatch, audit_answer):
    it = _item("Q1977772")
    choice = wb.shown_options(it).index(it["mc"]["gold"]) + 1

    def judge(_s, _u, schema):
        if schema.get("name") == "wb_rivals":
            return audit_answer
        return {"choice": choice, "quote": "Beethoven wrote", "rival_quote": ""}

    fake = FakeLLM.install(monkeypatch, judge=judge)
    layers = (20, 44, 60)
    rows = []
    for lay in layers:
        for p in range(14):
            s = "- Beethoven wrote the sonata" if p % 2 else "- Salieri wrote the sonata"
            rows.append({"id": BEETHOVEN, "layer": lay, "pos": p, "samples": [s]})
    from conftest import write_jsonl, write_sidecar

    path = write_jsonl(tmp_path / "wrong_bridge.jsonl", rows)
    write_sidecar(path, reads="full", plan_sha=reads.plan_sha("wrong_bridge"), layers=list(layers))
    args = summary_args(path, tmp_path / "out", wp.PROMPT_VERSION, items=[BEETHOVEN],
                        allow_missing=True, extra={})  # fmt: skip
    return fake, registry.FAMILIES["wrong_bridge"].run(args)


def test_summary_run_audits_a_credited_pick(tmp_path, monkeypatch):
    assert readplan.plan("wrong_bridge")
    audit = {"verdicts": [{"line": 1, "rival": True, "name": "Antonio Salieri"}]}
    fake, r = _run(tmp_path, monkeypatch, audit)
    assert fake.n("wb_rivals") == 1 and r.extras["n_audit_calls"] == 1
    user = next(u for n, _s, u in fake.calls if n == "wb_rivals")
    assert "THE QUESTION IS ABOUT: The composer of" in user and "LINES TO CHECK:" in user
    row = r.rows[0]
    assert row["pick"] == "contested" and row["pass"] is False


def test_summary_run_passes_when_the_audit_finds_no_rival(tmp_path, monkeypatch):
    fake, r = _run(tmp_path, monkeypatch, {"verdicts": [{"line": 1, "rival": False}]})
    assert fake.n("wb_rivals") == 1 and r.rows[0]["pass"] is True


def test_summary_run_failed_audit_is_unjudged(tmp_path, monkeypatch):
    _fake, r = _run(tmp_path, monkeypatch, {"wrong": "shape"})
    row = r.rows[0]
    assert row["pass"] is None and row.get("audit_failed") is True

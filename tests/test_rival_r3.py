"""Round 3 rival check (wsbench.rival) on wrong_bridge and basic_readout_mt: a credited pick must
clearly outweigh the strongest line naming a DIFFERENT answer (an option or not), on the digest's
own sample counts. Both directions are pinned: the lenient shapes of the cited cases fail, and a
clear lead, a rare hit with no rival and a non-rival quote still pass."""

from wsbench import digest, rival
from wsbench.banks import load_bank
from wsbench.evals.wrong_bridge import judge as wb
from wsbench.multitoken import family as fam
from wsbench.multitoken.options import option_sets


def _g(text: str, count: int) -> digest.Grounded:
    ln = digest.Line(text)
    return digest.Grounded("", digest.support_text(count), text, ln, text, "items", "", count)


# ------------------------------------------------------------------ the shared arithmetic


def _contest(res, grounded):
    return rival.contest(
        res,
        grounded,
        single_gold=lambda ln: "Gold" in ln.text,
        names_gold=lambda t: "Gold" in t,
    )


def test_rival_nearly_matching_is_contested():
    gs = [_g("The answer is Gold here.", 16), _g("It was Rival who did it.", 12)]
    rv = _contest({"quote": "Gold here", "rival_quote": "Rival who did"}, gs)
    assert rv["gold_support"] == 16 and rv["rival_support"] == 12 and rv["contested"]


def test_clear_lead_is_not_contested():
    gs = [_g("The answer is Gold here.", 30), _g("It was Rival who did it.", 20)]
    rv = _contest({"quote": "Gold here", "rival_quote": "Rival who did"}, gs)
    assert rv["rival_support"] == 20 and not rv["contested"]  # 30 >= 1.5 * 20


def test_no_rival_keeps_a_rare_single_hit():
    gs = [_g("The answer is Gold here.", 1), _g("Something unrelated entirely.", 40)]
    rv = _contest({"quote": "Gold here", "rival_quote": ""}, gs)
    assert rv["gold_support"] == 1 and not rv["contested"]


def test_gold_support_is_the_best_gold_line_not_the_quoted_one():
    # the judge quoted a 2-sample gold line; a 30-sample line singles out the gold too
    gs = [_g("Gold, once.", 2), _g("The answer is Gold, clearly.", 30), _g("Rival did it.", 15)]
    rv = _contest({"quote": "Gold, once", "rival_quote": "Rival did it"}, gs)
    assert rv["gold_support"] == 30 and not rv["contested"]


def test_rival_quote_naming_the_gold_is_no_rival():
    gs = [_g("Gold or Rival, unclear.", 3), _g("The answer is Gold.", 3)]
    rv = _contest({"quote": "The answer is Gold", "rival_quote": "Gold or Rival"}, gs)
    assert rv["rival_names_gold"] and not rv["contested"]


def test_unlocatable_rival_quote_is_ignored_and_flagged():
    gs = [_g("The answer is Gold.", 3)]
    rv = _contest({"quote": "The answer is Gold", "rival_quote": "not in any line at all"}, gs)
    assert rv["rival_verified"] is False and not rv["contested"]


def test_near_verbatim_rival_quote_is_located():
    gs = [_g("The answer is Gold.", 3), _g("The director of the film was Luis Buñuel, 1960.", 44)]
    rv = _contest(
        {"quote": "The answer is Gold", "rival_quote": "The director of the film was Luis Buñuel"},
        gs,
    )
    assert rv["rival_verified"] and rv["rival_support"] == 44 and rv["contested"]


# ------------------------------------------------------------------ wrong_bridge


def _wb_item(qid: str) -> dict:
    # the cited cases were judged on bank v2's lists (round 4 froze new lists in bank v3)
    _h, items = load_bank("evals/wrong_bridge/items_v2.json")
    return next(it for it in items if qid in it["id"])


def _wb_choice(it: dict) -> int:
    return wb.positions(it)[0]


def test_wrong_bridge_q6466264_plurality_is_contested():
    # cached all-layer digest: Torre Nilsson's 13-sample line vs a 44-sample Buñuel-director line
    it = _wb_item("Q6466264")
    gold = (
        "The Argentine director who died in the same year that *Macario* was released is "
        "**Leopoldo Torre Nilsson**."
    )
    bunuel = "This classic Mexican drama film. **Details:** - **Director:** Luis Buñuel -"
    gs = [_g(bunuel, 44), _g(gold, 13)]
    res = {
        "choice": _wb_choice(it),
        "quote": "is **Leopoldo Torre Nilsson**",
        "rival_quote": "**Director:** Luis Buñuel",
    }
    v = wb.decide(res, it, [g.line for g in gs], gs)
    assert v["pick"] == "contested" and not v["credited"]
    assert v["gold_support"] == 13 and v["rival_support"] == 44


def test_wrong_bridge_clear_lead_still_passes():
    # the too-strict shape: the same item with a clear lead keeps its credit
    it = _wb_item("Q6466264")
    gold = "The director is **Leopoldo Torre Nilsson**, who died in Buenos Aires."
    gs = [_g(gold, 40), _g("Directed by Luis Puenzo, an Argentine director.", 12)]
    res = {
        "choice": _wb_choice(it),
        "quote": "The director is **Leopoldo Torre Nilsson**",
        "rival_quote": "Directed by Luis Puenzo",
    }
    v = wb.decide(res, it, [g.line for g in gs], gs)
    assert v["pick"] == "gold" and v["credited"] and not v["contested"]


def test_wrong_bridge_native_path_has_no_rival_check():
    it = _wb_item("Q6466264")
    gold = "The director is **Leopoldo Torre Nilsson**."
    lines = [digest.Line(gold), digest.Line("Directed by Luis Buñuel.")]
    res = {
        "choice": _wb_choice(it),
        "quote": "The director is **Leopoldo Torre Nilsson**",
        "rival_quote": "Directed by Luis Buñuel",
    }
    v = wb.decide(res, it, lines)  # no grounded entries: native mode
    assert v["credited"] and "contested" not in v


# ------------------------------------------------------------------ basic_readout_mt


def _brmt(prefix: str):
    _h, items = load_bank("evals/basic_readout_mt/items_v2.json")
    opts = option_sets(items, cannot=fam.mc_family("basic_readout_mt").cannot)
    it = next(i for i in items if i["id"].startswith(prefix))
    return it, *opts[it["id"]]["readout"], fam.bank_entities(items)


def _brmt_verdict(prefix: str, gs, quote: str, rival_quote: str):
    it, options, gold_idx, entities = _brmt(prefix)
    res = {"choice": "ABCDEF"[gold_idx], "quote": quote, "rival_quote": rival_quote}
    cfg = fam.mc_family("basic_readout_mt")
    lines = [g.line for g in gs]
    v = fam._gate(cfg, "readout", res, gold_idx, options, lines, it, entities)
    return fam.contested_verdict(v, res, gs, gold_idx, options, it, "readout", entities)


def test_brmt_drakensberg_lite_one_sample_gold_is_contested():
    # all-lite cached digest: the gold on 1 sample, Mount Kilimanjaro (not an option) on 13
    gs = [
        _g("The highest mountain in the East African mountain range is **Mount Kilimanjaro**.", 13),
        _g("The highest mountain peak in mainland South Africa is **Thabana Ntlenyana**.", 1),
    ]
    v = _brmt_verdict(
        "brh-ent-drakensberg-summit",
        gs,
        "is **Thabana Ntlenyana**",
        "range is **Mount Kilimanjaro**",
    )
    assert v["kind"] == "contested" and not v["correct"]
    assert v["gold_support"] == 1 and v["rival_support"] == 13


def test_brmt_drakensberg_gold_dominant_still_passes():
    gs = [
        _g("The highest peak of the Drakensberg is **Thabana Ntlenyana**.", 25),
        _g("The highest mountain in Africa is **Mount Kilimanjaro**.", 13),
    ]
    v = _brmt_verdict(
        "brh-ent-drakensberg-summit",
        gs,
        "Drakensberg is **Thabana Ntlenyana**",
        "Africa is **Mount Kilimanjaro**",
    )
    assert v["kind"] == "correct" and v["correct"] and not v["contested"]


def test_brmt_single_mention_without_rival_still_passes():
    # cur-vanuatu-style: the gold once, no other answer to the question anywhere
    gs = [
        _g("The currency of Eritrea is the **Eritrean Nakfa**.", 1),
        _g("Eritrea is a country in the Horn of Africa.", 9),
    ]
    v = _brmt_verdict("brh-ent-cur-eritrea", gs, "the **Eritrean Nakfa**", "")
    assert v["correct"] and not v["contested"]


# ------------------------------------------------------------------ the margins


def test_far_more_needs_ratio_and_a_two_sample_lead():
    m = rival.FAR_MORE
    assert m.contested(2, 1)  # org_founder-Q618562 L40: 2 samples vs 1 is no clear favour
    assert m.contested(16, 12)  # Q3794057-shaped plurality
    assert not m.contested(6, 4) and not m.contested(30, 2)  # 1.5x and a lead of 2+
    assert not m.contested(1, 0)  # no rival: a rare single hit stands


def test_at_least_needs_the_gold_line_to_match_the_rival():
    m = rival.AT_LEAST
    assert m.contested(1, 13) and m.contested(4, 5)
    assert not m.contested(5, 4) and not m.contested(5, 5) and not m.contested(1, 0)


def test_wrong_bridge_contrast_line_is_weighed_even_unnamed():
    # L52 Q3221113-shaped: the judge's rival is weak, but the true bridge has its own line
    it = _wb_item("Q3221113")
    gold, contrast = it["mc"]["gold"], it["mc"]["contrast"]
    gs = [_g(f"The novel is by {gold}, the famous author.", 4), _g(f"Written by {contrast}.", 3)]
    res = {"choice": _wb_choice(it), "quote": f"by {gold}", "rival_quote": ""}
    v = wb.decide(res, it, [g.line for g in gs], gs)
    assert v["pick"] == "contested" and v["contrast_support"] == 3


def test_wrong_bridge_contrast_far_behind_does_not_contest():
    it = _wb_item("Q3221113")
    gold, contrast = it["mc"]["gold"], it["mc"]["contrast"]
    gs = [_g(f"The novel is by {gold}, the famous author.", 12), _g(f"Written by {contrast}.", 3)]
    res = {"choice": _wb_choice(it), "quote": f"by {gold}", "rival_quote": ""}
    v = wb.decide(res, it, [g.line for g in gs], gs)
    assert v["pick"] == "gold" and v["credited"] and v["contrast_support"] == 3

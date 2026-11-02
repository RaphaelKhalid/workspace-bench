"""Final r1 (2026-10-31, campaign-lead decision): conjunctive_association keeps the draw-majority
rule, adds an inverted-twin veto and leaves an item with a failed quote re-judge undecided; the
chance label matches the rule."""

from wsbench.evals.conjunctive_association import judge as cj
from wsbench.evals.conjunctive_association import score


def _combine(picks, failed=()):
    g = cj._Gate(tokens=False)
    ds = [
        {"pick": p, "choice": 1, "quote": "q", "quote_ok": True}
        | ({"failed_stage": "quote_check"} if i in failed else {})
        for i, p in enumerate(picks)
    ]
    return g.combine("x", ds)["pick"]


def test_majority_still_needed():
    assert _combine(["gold", "cannot_tell", "cannot_tell"]) == "cannot_tell"
    assert _combine(["gold", "gold", "cannot_tell"]) == "gold"


def test_inverted_draw_vetoes_a_gold_majority():
    assert _combine(["gold", "gold", "inverted"]) == "inverted"


def test_failed_draw_undecided_only_when_it_could_change_the_verdict():
    assert _combine(["gold", "gold", "api_fail"]) == "api_fail"  # inverted would veto it
    assert _combine(["gold", "api_fail", "cannot_tell"]) == "api_fail"
    assert _combine(["cannot_tell", "cannot_tell", "api_fail"]) == "cannot_tell"  # fails anyway
    assert cj.item_pick(["inverted", "gold", "api_fail"]) != "gold"


def test_chance_matches_the_rule():
    p = 1 / 11
    assert abs(score.mean_chance([["x"] * 11], 3) - (3 * p**2 - 2 * p**3)) < 1e-12
    assert score.mean_chance([["x"] * 11], 1) == p
    assert "majority of the 3" in score.chance_label(3)


# ---- round 3 (re-audit r2): long all-layer digests are judged in line shards


def _shard_case(tmp_path, monkeypatch, iid, answer, cap):
    from summary_fakes import FakeLLM, summary_args
    from test_conjunctive_association import _all_lines, _cells_file

    rows = [
        {"id": iid, "layer": 20 + 4 * (i % 11), "pos": 40 + i, "samples": [f"filler {i} " * 9]}
        for i in range(24)
    ]
    rows.append({"id": iid, "layer": 60, "pos": 90, "samples": ["GOLDLINE relief hidden"]})
    path = _cells_file(tmp_path, rows)
    monkeypatch.setattr(cj, "SHARD_CHARS", cap)

    def as_candidates(system, user, schema):
        # round 4: a sharded digest's MC is a candidate list; a cannot-tell answer is an
        # empty list, any other answer one candidate
        a = answer(system, user, schema)
        if schema.get("name") != "readout_mc_candidates":
            return a
        n_cannot = user.count("\n") and int(user.rsplit("\n", 1)[1].split(".")[0])
        return {"candidates": [] if a["choice"] == n_cannot else [a]}

    fake = FakeLLM.install(monkeypatch, as_candidates, digest=_all_lines)
    res = cj.run(summary_args(path, tmp_path / f"o{cap}", "pv", items=[iid], allow_missing=True))
    return res, fake


def _item_with_twin():
    from wsbench.mcjudge import load_bank

    for it in load_bank("conjunctive_association"):
        shown, gold, _c = cj.build_options(it)
        inv = cj.inverted_position(it, shown)
        if inv is not None:
            return it, shown, gold, inv
    raise AssertionError("no item with an inverted twin")


def test_shard_digest_splits_on_lines_and_keeps_shard_evidence():
    from wsbench.digest import Line

    lines = [f"[1 sample] line {i} " + "x" * 50 for i in range(10)]
    ev = [Line(t[11:]) for t in lines]
    shards = cj.shard_digest("\n".join(lines), ev, cap=200)
    assert len(shards) > 1 and all(len(t) <= 200 for t, _ in shards)
    assert [t for t, _ in shards] and "\n".join(t for t, _ in shards) == "\n".join(lines)
    assert all(len(t.split("\n")) == len(e) for t, e in shards)
    # one short digest is one shard, whose unit id is the item id (cache keys unchanged)
    assert len(cj.shard_digest("\n".join(lines[:2]), ev[:2])) == 1
    assert cj.unit_id("q01_a", 0, 1) == "q01_a" and cj.unit_id("q01_a", 2, 5) == "q01_a@s2"


def test_shards_pick_rule():
    assert cj.shards_pick(["cannot_tell", "gold", "cannot_tell"]) == "gold"
    assert cj.shards_pick(["gold", "inverted"]) == "inverted"  # any inverted shard vetoes
    assert cj.shards_pick(["gold", "api_fail"]) == "api_fail"  # it could be inverted
    assert cj.shards_pick(["cannot_tell", "split"]) == "cannot_tell"
    p = 1 / 21
    m = 3 * p**2 - 2 * p**3
    assert abs(score.mean_chance([["x"] * 21], 3, shards=[8]) - (1 - (1 - m) ** 8)) < 1e-12


def test_a_lone_gold_line_in_a_later_shard_passes(tmp_path, monkeypatch):
    it, shown, gold, _inv = _item_with_twin()
    cannot = len(shown)

    def answer(system, user, schema):
        if schema.get("name") == "quote_mc":
            return {"choice": gold, "quote": ""}
        if "GOLDLINE" in user:
            return {"choice": gold, "quote": "GOLDLINE relief hidden"}
        return {"choice": cannot, "quote": ""}

    res, fake = _shard_case(tmp_path, monkeypatch, it["id"], answer, cap=400)
    row = res.rows[0]
    assert row["n_shards"] > 1 and row["pick"] == "gold" and row["correct"]
    assert row["shard_picks"].count("gold") == 1
    assert "+shard8k" in res.config["prompt_version"] and res.config["n_shards_max"] > 1
    # no shard sees the whole digest
    mc_users = [u for n, _s, u in fake.calls if n not in ("quote_mc",) and "GOLDLINE" in u]
    assert mc_users and all("filler 0 " not in u or "filler 23 " not in u for u in mc_users)


def test_an_inverted_shard_vetoes_a_gold_shard(tmp_path, monkeypatch):
    it, shown, gold, inv = _item_with_twin()

    def answer(system, user, schema):
        if schema.get("name") == "quote_mc":
            return {"choice": gold, "quote": ""}
        if "GOLDLINE" in user:
            return {"choice": gold, "quote": "GOLDLINE relief hidden"}
        if "filler 0 " in user:
            return {"choice": inv, "quote": "filler 0"}
        return {"choice": len(shown), "quote": ""}

    res, _ = _shard_case(tmp_path, monkeypatch, it["id"], answer, cap=400)
    row = res.rows[0]
    assert row["pick"] == "inverted" and not row["correct"]


def test_short_digest_is_judged_whole_as_before(tmp_path, monkeypatch):
    it, shown, gold, _inv = _item_with_twin()

    def answer(system, user, schema):
        if schema.get("name") == "quote_mc":
            return {"choice": gold, "quote": ""}
        return {"choice": len(shown), "quote": ""}

    res, _ = _shard_case(tmp_path, monkeypatch, it["id"], answer, cap=10**6)
    row = res.rows[0]
    assert "n_shards" not in row and row["pick"] == "cannot_tell"
    assert "+shard8k" not in res.config["prompt_version"]

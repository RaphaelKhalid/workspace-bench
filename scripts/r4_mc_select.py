"""Choose each round-4 MC list's four distractors from its Opus candidate pool under the
lucky-guessing gate (Camila r2 MC leakage standard, 2026-11-01).

Input: the candidate pools of ``scripts/r4_mc_distractors.py`` (topic, format, the screened
candidates with their English Wikipedia titles) and their fame (Wikipedia sitelink counts).

1. **Fame balance.** A list is the gold plus two candidates at least as famous as the gold
   (nearest first) and two less famous (nearest first), so the gold is never the most (or the
   least) famous option. A list whose pool has fewer than two candidates as famous as the gold
   (a very famous gold: Beethoven, Alexander the Great) first gets a BROADER topic, one level up
   (one Opus call that sees the answer and the narrow topic), and the most famous members of it
   join the pool; the broader topic is then the list's topic label.
2. **Guesser gate.** Every list is shown to the options-only guesser (``blind``) and the topic
   guesser (``topic``), five draws each (the lucky-guessing prompts, ``wsbench.baselines.
   lucky_guessing``); a list whose gold either guesser picks in two or more draws is redrawn
   from its pool (a seeded subset, still with the most famous peers it has), up to
   :data:`ROUNDS` rounds; the least-guessed draw is kept. The frozen floors are re-measured
   afterwards on fresh draws (``wsbench baseline``), never on these.

Writes ``evals/<family>/r4_distractors.json`` (the chosen lists, topics, fame, the gate's
counts). Run: ``ANTHROPIC_AUTH_TOKEN=... .venv/bin/python scripts/r4_mc_select.py POOLS FAME``.
"""

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import r4_mc_distractors as gen

from wsbench.baselines import lucky_guessing as lg
from wsbench.llm import schema_block, stream_json
from wsbench.mc import seeded_shuffle as wb_shuffle
from wsbench.multitoken.options import seeded_shuffle as mt_shuffle
from wsbench.registry import REPO_ROOT

FAMILIES = ("wrong_bridge", "basic_readout_mt", "multihop_mt_v2", "multilingual_multihop")
DRAWS = 5
# a list fails the gate when either guesser picks its gold in 3 or more of the 5 draws (a firm
# preference: a guesser with no information still settles on one option, so 2 of 5 is chance)
MAX_GOLD_PICKS = 2
ROUNDS = 5
SEED = "r4-select-2026-11-01"
WB_SEED_V3 = "wb-mc-2026-11-01"
BROADEN_SYSTEM = (
    "You widen the TOPIC of a multiple-choice list. Given an ANSWER and its narrow TOPIC, give a "
    "BROADER topic one level up that still clearly contains the answer and in which several "
    "real entities are at least as famous as the answer (e.g. 'a classical-era composer of "
    "piano sonatas' -> 'a European classical composer'). Never name the answer. Then list the "
    "FIFTEEN most famous REAL entities of the same kind that fit the broader topic, most famous "
    "first: 'name' its common English name, 'enwiki' its exact English Wikipedia title."
)
BROADEN_SCHEMA = schema_block(
    "broaden",
    {
        "topic": {"type": "string"},
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "enwiki": {"type": "string"}},
                "required": ["name", "enwiki"],
                "additionalProperties": False,
            },
        },
    },
    ["topic", "candidates"],
)


def _rng(*key: object) -> random.Random:
    h = hashlib.sha256("|".join(str(k) for k in (SEED, *key)).encode()).digest()[:8]
    return random.Random(int.from_bytes(h, "big"))


def balanced(pool: list[dict[str, Any]], g_fame: int, k: int, key: str) -> list[dict[str, Any]]:
    """Draw ``k`` of the gate: draw 0 = the two nearest candidates at least as famous as the gold
    and the two nearest less famous ones; a later draw = a seeded subset that keeps as many of
    the at-least-as-famous candidates as draw 0 had (up to two)."""
    above = sorted((c for c in pool if c["fame"] >= g_fame), key=lambda c: c["fame"])
    below = sorted((c for c in pool if c["fame"] < g_fame), key=lambda c: -c["fame"])
    n_up = min(2, len(above))
    if k == 0:
        pick = above[:n_up] + below[: 4 - n_up]
        if len(pick) < 4:
            pick += [c for c in above[n_up:] if c not in pick][: 4 - len(pick)]
        return pick[:4]
    r = _rng(key, k)
    up = r.sample(above, n_up) if n_up else []
    rest = [c for c in pool if c not in up]
    return up + r.sample(rest, min(4 - n_up, len(rest)))


def option_order(family: str, it: dict[str, Any], role: str, gold: str, ds: list[str]) -> list:
    """The options in the order the v3 bank builder will freeze them (the seeded permutations
    depend only on the item and the list length, never on the option text)."""
    if family == "wrong_bridge":
        return wb_shuffle([gold, it["mc"]["contrast"], *ds], f"{WB_SEED_V3}:{it['name']}:order")
    return mt_shuffle(f"{it['name']}|{role}", [gold, *ds])


def _bank(family: str) -> dict[str, dict[str, Any]]:
    from wsbench.banks import load_bank

    _h, items = load_bank(REPO_ROOT / "evals" / family / "items_v2.json")
    return {str(it["id"]): it for it in items}


def evaluate(
    family: str, items: list[lg.Item], targets: dict[str, list[int]]
) -> dict[tuple[str, int], tuple[int, int]]:
    """(item id, list index) -> (blind gold picks, topic gold picks) over DRAWS draws each, for
    the lists of ``targets`` (item id -> list indices)."""
    by_id = {it.id: i for i, it in enumerate(items)}
    calls: list[tuple[str, str, str, int]] = []
    for iid in targets:
        idx = by_id[iid]
        it = items[idx]
        ex = lg.pick_examples(items, idx, family, lg.DEFAULT_SEED)
        for variant in ("blind", "topic"):
            msg = lg.user_message(it, variant, family, None if variant == "blind" else ex)
            calls += [(iid, variant, msg, d) for d in range(DRAWS)]
    got: dict[int, dict[str, Any] | None] = {}

    def on(i: int, r: dict[str, Any] | None) -> None:
        got[i] = r

    shapes = {iid: len(items[by_id[iid]].lists) for iid in targets}
    for n in sorted(set(shapes.values())):
        sub = [j for j, c in enumerate(calls) if shapes[c[0]] == n]
        sub_got: dict[int, dict[str, Any] | None] = {}

        def on_sub(k: int, r: dict[str, Any] | None, sub: list = sub, sg: dict = sub_got) -> None:
            sg[sub[k]] = r

        stream_json(
            [(lg.SYSTEM, calls[j][2]) for j in sub],
            schema=lg.schema(n),
            model=gen.MODEL,
            on_result=on_sub,
            concurrency=128,
            rpm=3000,
            max_tokens=lg.MAX_TOKENS,
        )
        got.update(sub_got)
    out: dict[tuple[str, int], list[int]] = {}
    for j, (iid, variant, _m, _d) in enumerate(calls):
        it = items[by_id[iid]]
        r = got.get(j) or {}
        for li in targets[iid]:
            pick = r.get(f"choice{li + 1}")
            hit = int(pick == it.golds[li])
            cur = out.setdefault((iid, li), [0, 0])
            cur[0 if variant == "blind" else 1] += hit
    return {k: (v[0], v[1]) for k, v in out.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("pools", type=Path)
    ap.add_argument("fame", type=Path)
    ap.add_argument("--families", nargs="*", default=list(FAMILIES))
    a = ap.parse_args(argv)
    pools = json.loads(a.pools.read_text(encoding="utf-8"))
    fm = json.loads(a.fame.read_text(encoding="utf-8"))
    qid, fame = fm["qid"], fm["fame"]
    for family in a.families:
        bank = _bank(family)
        lists: dict[tuple[str, str], dict[str, Any]] = {}
        for iid, roles in pools[family].items():
            for role, b in roles.items():
                cands = [{"name": n, "enwiki": b["enwiki"][n]} for n in b["distractors"]] + [
                    {"name": s["name"], "enwiki": s["enwiki"]} for s in b.get("spares", [])
                ]
                for c in cands:
                    c["fame"] = fame.get(qid.get(c["enwiki"], ""), 0)
                lists[(iid, role)] = {**b, "pool": cands, "g_fame": b["fame"]["gold"]}
        # 1. broaden the lists whose pool lacks two candidates as famous as the gold
        weak = [k for k, v in lists.items() if sum(c["fame"] >= v["g_fame"] for c in v["pool"]) < 2]
        if weak:
            got: dict[int, dict[str, Any] | None] = {}

            def on(i: int, r: dict[str, Any] | None, got: dict = got) -> None:
                got[i] = r

            stream_json(
                [
                    (
                        BROADEN_SYSTEM,
                        f"ANSWER: {lists[k]['gold']}\nTOPIC: {lists[k]['topic']}\n"
                        f"KIND: {lists[k]['kind']}",
                    )
                    for k in weak
                ],
                schema=BROADEN_SCHEMA,
                model=gen.MODEL,
                on_result=on,
                concurrency=64,
            )
            titles = [
                str(c.get("enwiki", ""))
                for r in got.values()
                for c in ((r or {}).get("candidates") or [])
                if isinstance(c, dict)
            ]
            titles += [lists[k]["gold"] for k in weak]
            q2 = gen.qids_of(titles)
            f2 = gen.sitelinks_of(list(q2.values()))
            for i, k in enumerate(weak):
                r = got.get(i) or {}
                spec = {
                    "prompt": bank[k[0]]["prompt"],
                    "gold": lists[k]["gold"],
                    "gold_forms": [lists[k]["gold"]],
                    "fixed": [bank[k[0]]["mc"]["contrast"]] if family == "wrong_bridge" else [],
                    "fixed_forms": [],
                    "avoid": [],
                }
                cands = [
                    {"name": str(c.get("name", "")).strip(), "enwiki": str(c.get("enwiki", ""))}
                    for c in (r.get("candidates") or [])
                    if isinstance(c, dict)
                ]
                taken = {qid.get(lists[k]["gold"]), q2.get(lists[k]["gold"])} - {None}
                cands = [c for c in cands if q2.get(c["enwiki"]) not in taken]
                keep, _dropped = gen.screen(spec, cands)
                have = {c["name"] for c in lists[k]["pool"]}
                for c in keep:
                    if c["name"] not in have and c["enwiki"] in q2:
                        c["fame"] = f2.get(q2[c["enwiki"]], 0)
                        lists[k]["pool"].append(c)
                        qid[c["enwiki"]] = q2[c["enwiki"]]
                if r.get("topic"):
                    lists[k]["topic_narrow"] = lists[k]["topic"]
                    lists[k]["topic"] = str(r["topic"]).strip()
        # 2. the guesser gate
        choice = {k: balanced(v["pool"], v["g_fame"], 0, f"{family}|{k}") for k, v in lists.items()}
        best: dict[tuple[str, str], tuple[int, list[dict[str, Any]], tuple[int, int]]] = {}
        todo = set(lists)
        for rnd in range(ROUNDS):
            items = lg.build_family(family)
            topics = lg.load_list_topics(family)
            new_items = []
            targets: dict[str, list[int]] = {}
            for it in items:
                roles = list(it.meta.get("roles") or ["bridge"])
                lists_ = [list(x) for x in it.lists]
                golds = list(it.golds)
                tops = list(topics.get(it.id, [""] * len(lists_)))
                for li, role in enumerate(roles):
                    k = (it.id, role)
                    if k not in lists:
                        continue
                    ds = [c["name"] for c in choice[k]]
                    order = option_order(family, bank[it.id], role, lists[k]["gold"], ds)
                    lists_[li] = order
                    golds[li] = order.index(lists[k]["gold"]) + 1
                    tops[li] = lists[k]["topic"]
                    if k in todo:
                        targets.setdefault(it.id, []).append(li)
                new_items.append(
                    lg.Item(it.id, lists_, golds, it.multi, {**it.meta, "topics": tops})
                )
            if not targets:
                break
            res = evaluate(family, new_items, targets)
            by_id = {it.id: it for it in new_items}
            nxt = set()
            for k in todo:
                it = by_id[k[0]]
                roles = list(it.meta.get("roles") or ["bridge"])
                li = roles.index(k[1])
                b, t = res.get((k[0], li), (DRAWS, DRAWS))
                score = max(b, t)
                if k not in best or score < best[k][0]:
                    best[k] = (score, choice[k], (b, t))
                if score > MAX_GOLD_PICKS:
                    nxt.add(k)
                    choice[k] = balanced(lists[k]["pool"], lists[k]["g_fame"], rnd + 1,
                                         f"{family}|{k}")  # fmt: skip
            print(f"{family} round {rnd}: {len(todo)} lists judged, {len(nxt)} over the gate")
            todo = nxt
        out_items: dict[str, dict[str, Any]] = {}
        for k, v in lists.items():
            score, pick, (b, t) = best[k]
            out_items.setdefault(k[0], {})[k[1]] = {
                "topic": v["topic"],
                **({"topic_narrow": v["topic_narrow"]} if "topic_narrow" in v else {}),
                "kind": v["kind"],
                "gold": v["gold"],
                "distractors": [c["name"] for c in pick],
                "enwiki": {c["name"]: c["enwiki"] for c in pick},
                "fame": {"gold": v["g_fame"], **{c["name"]: c["fame"] for c in pick}},
                "gate": {"blind_gold_picks": b, "topic_gold_picks": t, "draws": DRAWS},
            }
        doc = {
            "family": family,
            "version": gen.VERSION + "+select-v1",
            "model": gen.MODEL,
            "script": "scripts/r4_mc_distractors.py + scripts/r4_mc_select.py",
            "gate": {"draws": DRAWS, "max_gold_picks": MAX_GOLD_PICKS, "rounds": ROUNDS},
            "items": dict(sorted(out_items.items())),
        }
        path = REPO_ROOT / "evals" / family / "r4_distractors.json"
        path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        n_over = sum(1 for v in best.values() if v[0] > MAX_GOLD_PICKS)
        print(f"{family}: wrote {path} ({len(best)} lists, {n_over} still over the gate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Buggy code: a blind reader infers what the readouts claim about the program (3 votes, the
majority claim), then an informed grader scores that inference 1-10 against the ground truth (the
bug, or the fact that there is none). Plan 0030: the unit is the buggy/clean twin pair (``twin``
in the bank). A pair hit = the buggy member claims ``bug`` and the clean member does not; the
headline is ``pair_rate`` (metric ``pass_rate``, since 2026-10-30) and ``specific_pair_rate`` in
extras also needs the buggy member graded >= 8 (the median of 3 grades). The blended 1-10
``score`` over every item is kept in extras. Stages, scores for silent readouts, undecided pairs
and strata are explained in the family README."""

import statistics
from collections import defaultdict
from typing import Any

from wsbench import digest, reads
from wsbench.banks import label_of, load_bank
from wsbench.cache import Cache
from wsbench.family import cell_text, mean, rate, require_cells
from wsbench.llm import Spend
from wsbench.mcjudge import (
    Call,
    Preflighter,
    base_config,
    base_counts,
    is_subset,
    run_calls,
    with_readout_count,
)
from wsbench.readouts import Cell, LoadReport
from wsbench.registry import JudgeArgs, bank_path
from wsbench.results import FamilyResult, bootstrap_ci, completeness

from .prompts import (
    CLAIMS,
    DIGEST_TASK_NOTE,
    GRADE_SCHEMA,
    GRADE_SYSTEM,
    INFER_SCHEMA,
    INFER_SYSTEM,
    JUDGE_PROMPT_VERSION,
    N_VOTES,
    PROMPT_VERSION,
    SILENT_SCORE,
    SPECIFIC_SCORE,
    render_grade,
    render_infer,
    render_infer_summary,
)

NAME = "buggy_code"
CHANCE_LABEL = (
    "degenerate strategies score 0 under the pair rule: always-correct 0 (misses every bug), "
    "always-bug 0 (false-alarms every twin), a random bug claim with probability p scores "
    "p(1-p) <= 0.25 on the pair_rate headline (less on specific_pair_rate)"
)


# ---------------------------------------------------------------- pairs and scope


def pairs_of(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """``[(buggy id, clean id)]`` from the bank's ``twin`` field (a partner's ``name``), each pair
    once, in the buggy member's bank order. An item without a twin, or whose twin is missing or of
    the same ``src``, is an orphan (adapted banks carry no ``twin``: every item is an orphan)."""
    by_name = {str(it["name"]): it for it in items}
    out: list[tuple[str, str]] = []
    for it in items:
        tw = by_name.get(str(it.get("twin") or ""))
        if it["src"] != "buggy" or tw is None or tw["src"] != "clean":
            continue
        if str(tw.get("twin") or "") != str(it["name"]):
            continue  # not symmetric: not a pair
        out.append((str(it["id"]), str(tw["id"])))
    return out


def pair_scope(
    items: list[dict[str, Any]], args: JudgeArgs
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """``(items in scope, pairs in scope)``, both in bank order. ``items=`` expands to whole
    pairs (naming either member pulls in its twin; an orphan is taken alone); ``limit=`` counts
    pairs (the first N pairs, no orphans), or items on a bank with no pairs."""
    pairs = pairs_of(items)
    twin_of = dict(pairs) | {c: b for b, c in pairs}
    scope = items
    if args.items is not None:
        want = {label_of(str(x)) for x in args.items} | {str(x) for x in args.items}
        keep = {str(it["id"]) for it in items if str(it["id"]) in want}
        keep |= {twin_of[i] for i in keep if i in twin_of}
        scope = [it for it in items if str(it["id"]) in keep]
    in_scope = {str(it["id"]) for it in scope}
    pairs = [(b, c) for b, c in pairs if b in in_scope and c in in_scope]
    if args.limit > 0:
        if pairs:
            pairs = pairs[: args.limit]
            members = {i for p in pairs for i in p}
            scope = [it for it in scope if str(it["id"]) in members]
        else:
            scope = scope[: args.limit]
    return scope, pairs


# ---------------------------------------------------------------- stage answers


def inference(res: dict[str, Any] | None) -> dict[str, Any]:
    """Stage A answer: the claim, the inferred behaviour and the supporting snippet (kept as
    evidence, not enforced)."""
    if res is None:
        return {"judged": False, "claim": None, "inferred": "", "quote": ""}
    claim = str(res.get("claim", "none"))
    if claim not in CLAIMS:
        claim = "none"
    return {
        "judged": True,
        "claim": claim,
        "inferred": str(res.get("inferred", "")).strip(),
        "quote": str(res.get("quote", "")).strip(),
    }


def grade(res: dict[str, Any] | None) -> int | None:
    if res is None:
        return None
    score = res.get("score")
    if isinstance(score, bool) or not isinstance(score, int | float):
        return None
    return max(1, min(10, round(score)))


def majority(results: list[dict[str, Any] | None]) -> dict[str, Any]:
    """Stage A over ``N_VOTES`` votes: any failed vote leaves the item unjudged; else the
    majority claim, with the ``inferred`` / ``quote`` of the lowest-numbered vote that agrees
    with it; with no majority (every vote differs) the claim is ``none``. ``votes`` = the claims
    in vote order."""
    if any(r is None for r in results):
        return {**inference(None), "votes": None}
    infs = [inference(r) for r in results]
    claims = [str(x["claim"]) for x in infs]
    top = max(claims, key=claims.count)
    if 2 * claims.count(top) <= len(claims):
        return {"judged": True, "claim": "none", "inferred": "", "quote": "", "votes": claims}
    chosen = next(x for x in infs if x["claim"] == top)
    return {**chosen, "votes": claims}


def median_grade(results: list[dict[str, Any] | None]) -> int | None:
    """Stage B over its votes: the median grade; any failed (or unparsable) grade -> None."""
    gs = [grade(r) for r in results]
    if not gs or any(g is None for g in gs):
        return None
    return int(statistics.median_low([g for g in gs if g is not None]))


def _judge_items(
    *,
    ids: list[str],
    by_id: dict[str, dict[str, Any]],
    layer_of: dict[str, int],
    base_key: dict[str, str],
    infer_user: dict[str, str],
    voted_members: set[str],
    shared: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, int | None], dict[str, list[int | None]], int]:
    """Stages A and B for the items in ``infer_user`` (both modes). Stage A: ``N_VOTES`` calls
    per item, keys ``<base>|infer|v1..vN``. Stage B on every non-``none`` claim: ``N_VOTES``
    calls (``<base>|grade|v1..vN``, the median kept) for a buggy pair member claiming ``bug``,
    else one call (``<base>|grade``). Returns ``(inferred, scores, grade votes, n_calls)``."""

    def meta(i: str, stage: str, vote: int | None = None) -> dict[str, Any]:
        m: dict[str, Any] = {"item": i, "layer": layer_of[i], "src": by_id[i]["src"]}
        m["stage"] = stage
        if vote is not None:
            m["vote"] = vote
        return m

    todo = [i for i in ids if i in infer_user]
    infer_calls = [
        Call(
            key=f"{base_key[i]}|infer|v{k}",
            system=INFER_SYSTEM,
            user=infer_user[i],
            meta=meta(i, "infer", k),
        )
        for i in todo
        for k in range(1, N_VOTES + 1)
    ]
    infer_results = run_calls(infer_calls, schema=INFER_SCHEMA, **shared) if infer_calls else {}
    inferred = {
        i: majority([infer_results.get(f"{base_key[i]}|infer|v{k}") for k in range(1, N_VOTES + 1)])
        for i in todo
    }
    graded = [i for i in todo if inferred[i]["judged"] and inferred[i]["claim"] != "none"]
    voted = {i for i in graded if i in voted_members and inferred[i]["claim"] == "bug"}
    keys = {
        i: (
            [f"{base_key[i]}|grade|v{k}" for k in range(1, N_VOTES + 1)]
            if i in voted
            else [f"{base_key[i]}|grade"]
        )
        for i in graded
    }
    grade_calls = [
        Call(
            key=key,
            system=GRADE_SYSTEM,
            user=render_grade(by_id[i], inferred[i]["claim"], inferred[i]["inferred"]),
            meta=meta(i, "grade", k + 1 if i in voted else None),
        )
        for i in graded
        for k, key in enumerate(keys[i])
    ]
    grade_results = run_calls(grade_calls, schema=GRADE_SCHEMA, **shared) if grade_calls else {}
    scores: dict[str, int | None] = {}
    votes: dict[str, list[int | None]] = {}
    for i in graded:
        res = [grade_results.get(k) for k in keys[i]]
        scores[i] = median_grade(res)
        if i in voted:
            votes[i] = [grade(r) for r in res]
    return inferred, scores, votes, len(infer_calls) + len(grade_calls)


def _verdict(
    i: str,
    *,
    empty: set[str],
    inferred: dict[str, dict[str, Any]],
    scores: dict[str, int | None],
    grade_votes: dict[str, list[int | None]],
    src: str,
    missing: bool,
) -> dict[str, Any]:
    """One item's row fields (both modes): an empty cell is a judged silent item; a ``none``
    claim takes the silent score; a claim with a failed Stage B is unjudged but KEEPS its claim
    (the pair rule reads it); a failed Stage A (or no cell) has claim None."""
    if i in empty:
        return {
            "judged": True,
            "claim": "none",
            "inferred": "",
            "quote": "",
            "score": SILENT_SCORE[src],
            "empty": True,
        }
    if i in inferred and inferred[i]["judged"]:
        inf = inferred[i]
        score = SILENT_SCORE[src] if inf["claim"] == "none" else scores.get(i)
        v = {**inf, "score": score, "judged": score is not None}
        if i in grade_votes:
            v["grade_votes"] = grade_votes[i]
        return v
    return {
        "judged": False,
        "claim": None,
        "inferred": "",
        "quote": "",
        "score": None,
        "votes": inferred[i]["votes"] if i in inferred else None,
        "missing": missing,
    }


def run(args: JudgeArgs) -> FamilyResult:
    header, items = load_bank(bank_path(NAME))
    scope, pairs = pair_scope(items, args)
    ids = [it["id"] for it in scope]
    by_id = {it["id"]: it for it in scope}
    read_layer = {it["id"]: int(header["read_cells"][it["lang_group"]]["layer"]) for it in scope}
    cells, rep = reads.load(args, NAME, ids=ids)
    # plan 0032 §2.1.4: the read span is the EOF anchor (each layer's max-pos row) at EVERY layer
    # in the file (or of layers=); under reads=lite reads.load keeps only the bank layer.
    # layer_of is the item's anchor layer of record (its bank layer, or a single layers=).
    layer_of = {
        i: (args.layers[0] if args.layers and len(args.layers) == 1 else read_layer[i]) for i in ids
    }
    groups: dict[tuple[str, int], list[Cell]] = defaultdict(list)
    for c in cells:
        groups[(c.id, c.layer)].append(c)
    eof: dict[str, list[Cell]] = defaultdict(list)
    for (i, _layer), cs in sorted(groups.items()):
        eof[i].append(max(cs, key=lambda c: c.pos))
    chosen_all = {i: eof[i] for i in ids if eof.get(i)}
    chosen = {i: cs[-1] for i, cs in chosen_all.items()}  # one representative per item
    n_extra = len(cells) - sum(len(cs) for cs in chosen_all.values())  # non-EOF rows
    missing = [i for i in ids if i not in chosen]
    require_cells(NAME, missing, len(ids), args)
    if digest.summary_mode(args):
        return _run_summary(
            args,
            scope=scope,
            pairs=pairs,
            ids=ids,
            by_id=by_id,
            layer_of=layer_of,
            chosen=chosen_all,
            missing=missing,
            cells=cells,
            rep=rep,
            n_extra=n_extra,
        )
    samples: dict[str, list[str]] = {}
    empty: set[str] = set()
    for i, cs in chosen_all.items():
        ss = [
            x
            for c in cs
            for x in (
                [cell_text(c)[0]]
                if c.tokens is not None
                else [s for s in (c.samples or ()) if s.strip()]
            )
        ]
        if ss:
            samples[i] = ss
        else:
            empty.add(i)
    layers_of = {i: [c.layer for c in cs] for i, cs in chosen_all.items()}

    spend = Spend()
    pre = Preflighter(args.dry_run)
    with Cache(args.out / "cells.jsonl") as cache:
        shared: dict[str, Any] = {
            "judge": args.judge,
            "prompt_version": JUDGE_PROMPT_VERSION,  # the cache key; the stamp is PROMPT_VERSION
            "cache": cache,
            "spend": spend,
            "concurrency": args.concurrency,
            "rpm": args.rpm,
            "dry_run": args.dry_run,
            "preflight": pre.for_judge(args.judge),
            "temperature": 0.0,
        }
        # stage A blind (3 votes), stage B informed; silent readouts make no Stage B call
        inferred, scores, grade_votes, n_calls = _judge_items(
            ids=ids,
            by_id=by_id,
            layer_of=layer_of,
            base_key={i: _base_key(i, layers_of.get(i) or [layer_of[i]]) for i in ids},
            infer_user={i: render_infer(ss) for i, ss in samples.items()},
            voted_members={b for b, _c in pairs},
            shared=shared,
        )

    rows = []
    for i in ids:
        it = by_id[i]
        src = str(it["src"])
        v = _verdict(
            i,
            empty=empty,
            inferred=inferred,
            scores=scores,
            grade_votes=grade_votes,
            src=src,
            missing=i in missing,
        )
        rows.append(
            {
                "id": i,
                "src": src,
                "lang_group": it["lang_group"],
                "consequence_class": it.get("consequence_class"),
                "layer": layer_of[i],
                **v,
            }
        )
    return _finish(
        args,
        scope=scope,
        pairs=pairs,
        ids=ids,
        rows=rows,
        cells=cells,
        n_missing=len(missing),
        n_empty=len(empty),
        skipped_rows=sum(rep.skipped.values()) + n_extra,
        n_extra=n_extra,
        spend=spend,
        n_calls=n_calls,
        pinned=args.judge.pinned,
        config=base_config(
            args,
            PROMPT_VERSION,
            kind=rep.kind or "prose",
            layers_judged=sorted({c.layer for cs in chosen_all.values() for c in cs}),
        ),
    )


def _base_key(item: str, layers: list[int]) -> str:
    """The judge-call key of one item's read span: one layer keeps the pre-0032 key."""
    if len(layers) == 1:
        return f"{item}|L{layers[0]:03d}"
    return f"{item}|L" + ",".join(f"{x:03d}" for x in sorted(layers))


def pair_verdicts(rows: list[dict[str, Any]], pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """The pair rule (plan 0030). The clean member is clean-OK unless it claims ``bug`` (silence
    and unrelated output frames are fine); the buggy member must claim ``bug``. A known buggy
    non-``bug`` claim or a clean ``bug`` claim fails the pair whatever the other member says;
    otherwise a member with no claim (a failed Stage A, no cell) leaves the pair undecided
    (both None); a pair hit whose buggy member's Stage B failed has ``specific_hit`` None (the
    pair rate needs only the claims). ``specific_hit`` = a pair hit whose buggy member is graded
    >= ``SPECIFIC_SCORE``. Writes ``pair`` / ``pair_hit`` / ``specific_hit`` onto the rows."""
    by_row = {r["id"]: r for r in rows}
    for r in rows:
        r.update(pair=None, pair_hit=None, specific_hit=None)
    out: list[dict[str, Any]] = []
    for b, c in pairs:
        rb, rc = by_row[b], by_row[c]
        bc, cc = rb["claim"], rc["claim"]
        hit: bool | None
        spec: bool | None
        if (bc is not None and bc != "bug") or cc == "bug":
            hit, spec = False, False
        elif bc is None or cc is None:
            hit, spec = None, None
        else:  # both claims known: a pair hit; specificity needs the buggy member's grade
            hit = True
            spec = None if rb["score"] is None else int(rb["score"]) >= SPECIFIC_SCORE
        rb.update(pair=c, pair_hit=hit, specific_hit=spec)
        rc["pair"] = b
        out.append(
            {
                "buggy": b,
                "clean": c,
                "buggy_claim": bc,
                "clean_claim": cc,
                "buggy_score": rb["score"],
                "pair_hit": hit,
                "specific_hit": spec,
                "stratum": f"{rb['consequence_class'] or 'none'}/{rb['lang_group']}",
            }
        )
    return out


def _finish(
    args: JudgeArgs,
    *,
    scope: list[dict[str, Any]],
    pairs: list[tuple[str, str]],
    ids: list[str],
    rows: list[dict[str, Any]],
    cells: list[Cell],
    n_missing: int,
    n_empty: int,
    skipped_rows: int,
    n_extra: int,
    spend: Spend,
    n_calls: int,
    pinned: bool,
    config: dict[str, Any],
    extras: dict[str, Any] | None = None,
) -> FamilyResult:
    """The result epilogue both modes share: the pair verdicts and the headline ``pair_rate``
    over pairs decided on their claims (``specific_pair_rate`` beside it, over pairs decided on
    specificity too), then the retained per-item extras (the blended
    1-10 score, the silent floor, strata, diagnostics). A cell is one item at its read cell, so
    the item-level summary counts and the cell-level native counts coincide."""
    pv = pair_verdicts(rows, pairs)
    decided = [p for p in pv if p["specific_hit"] is not None]
    # false alarms on the clean twins only (the pair members), beside the all-clean rate
    fa_twins = rate(p["clean_claim"] == "bug" for p in pv if p["clean_claim"] is not None)
    pair_hits = [1.0 if p["pair_hit"] else 0.0 for p in pv if p["pair_hit"] is not None]
    pair_rate = rate(bool(h) for h in pair_hits)
    specific_rate = rate(bool(p["specific_hit"]) for p in decided)
    n_undecided = len(pv) - len(pair_hits)  # the headline's denominator (claims known)
    judged = [r for r in rows if r["judged"]]
    n_unjudged = sum(1 for r in rows if not r["judged"] and not r.get("missing"))
    by_src = {s: [r for r in judged if r["src"] == s] for s in ("buggy", "clean")}
    silent_floor = mean(float(SILENT_SCORE[str(it["src"])]) for it in scope)
    strata = sorted(
        {(r["consequence_class"] or "none", r["lang_group"]) for r in judged if r["src"] == "buggy"}
    )
    per_stratum = {
        f"{cls}/{lg}": {
            "n": sum(
                1
                for r in by_src["buggy"]
                if (r["consequence_class"] or "none") == cls and r["lang_group"] == lg
            ),
            "score": mean(
                float(r["score"])
                for r in by_src["buggy"]
                if (r["consequence_class"] or "none") == cls and r["lang_group"] == lg
            ),
        }
        for cls, lg in strata
    }
    per_stratum_pairs: dict[str, dict[str, Any]] = {}
    for st in sorted({p["stratum"] for p in pv}):
        ps = [p for p in pv if p["stratum"] == st]
        dec = [p for p in ps if p["specific_hit"] is not None]
        per_stratum_pairs[st] = {
            "n": len(ps),
            "n_decided": len(dec),
            "pair_rate": rate(bool(p["pair_hit"]) for p in ps if p["pair_hit"] is not None),
            "specific_pair_rate": rate(bool(p["specific_hit"]) for p in dec),
        }
    orphan_clean = [r for r in rows if r["src"] == "clean" and r["pair"] is None]
    hist = {
        s: {str(k): sum(1 for r in rs if r["score"] == k) for k in range(1, 11)}
        for s, rs in by_src.items()
    }
    result = FamilyResult(
        family=NAME,
        metric="pass_rate",
        value=pair_rate,  # the headline since 2026-10-30; specific_pair_rate is in extras
        ci95=bootstrap_ci(pair_hits) if pair_hits else None,
        n_items=len(pairs),
        higher_is_better=True,
        chance=0.0,
        chance_label=CHANCE_LABEL,
        complete=bool(cells)
        and n_undecided == 0
        and completeness(
            pinned=pinned,
            subset=is_subset(args),
            n_expected=len(ids),
            n_missing=n_missing,
            n_unjudged=n_unjudged,
            n_empty=n_empty,
            n_items=len(ids),
        ),
        pinned_instrument=pinned,
        config=config,
        # a cell is one item at its read layer: three blind calls per non-empty cell, then three
        # graded calls per buggy pair member claiming a bug and one per other claiming cell
        counts=base_counts(
            n_expected=len(ids),
            n_missing=n_missing,
            n_unjudged=n_unjudged,
            n_empty=n_empty,
            skipped_rows=skipped_rows,
            spend=spend,
        ),
        rows=rows,
        extras={
            "n_calls": n_calls,
            "n_rows_not_at_read_cell": n_extra,
            "specific_pair_rate": specific_rate,
            "pair_rate": pair_rate,
            "specific_threshold": SPECIFIC_SCORE,
            "n_votes": N_VOTES,
            "n_pairs": len(pv),
            "n_pairs_decided": len(pair_hits),  # the headline (claims known)
            "n_pairs_decided_specific": len(decided),
            "n_pairs_undecided": n_undecided,
            "pairs": pv,
            "per_stratum_pairs": per_stratum_pairs,
            "n_orphan_items": sum(1 for r in rows if r["pair"] is None),
            "false_alarm_rate_twins": fa_twins,
            "false_alarm_rate_orphan_clean": rate(
                r["claim"] == "bug" for r in orphan_clean if r["claim"] is not None
            ),
            "score": mean(float(r["score"]) for r in judged),
            "score_ci95": bootstrap_ci([float(r["score"]) for r in judged]) if judged else None,
            "silent_floor": silent_floor,
            "score_buggy": mean(float(r["score"]) for r in by_src["buggy"]),
            "score_clean": mean(float(r["score"]) for r in by_src["clean"]),
            "n_buggy_judged": len(by_src["buggy"]),
            "n_clean_judged": len(by_src["clean"]),
            "claims": {
                s: {c: rate(r["claim"] == c for r in rs) for c in CLAIMS}
                for s, rs in by_src.items()
            },
            "false_alarm_rate_clean": rate(r["claim"] == "bug" for r in by_src["clean"]),
            "score_hist": hist,
            "per_stratum": per_stratum,
            "rows_claims": [
                {
                    "id": r["id"],
                    "src": r["src"],
                    "claim": r["claim"],
                    "score": r["score"],
                    "inferred": r["inferred"][:300],
                }
                for r in judged
            ],
            **(extras or {}),
        },
    )
    return with_readout_count(result, scope, cells)


def _run_summary(
    args: JudgeArgs,
    *,
    scope: list[dict[str, Any]],
    pairs: list[tuple[str, str]],
    ids: list[str],
    by_id: dict[str, dict[str, Any]],
    layer_of: dict[str, int],
    chosen: dict[str, list[Cell]],
    missing: list[str],
    cells: list[Cell],
    rep: LoadReport,
    n_extra: int,
) -> FamilyResult:
    """Summary mode (plan 0021 Part B; plan 0032 §2.1.4): every EOF cell of the item (max pos at
    each layer read) -> one digest (not voted) -> Stage A on the digest (3 votes) -> the
    unchanged Stage B;
    the pair rule on top. An unsummarized item is unjudged (no claim); an empty digest scores
    SILENT_SCORE, as an empty native cell does; an item with no cell keeps the native missing
    path."""
    spend = Spend()
    pre = Preflighter(args.dry_run)
    pv = digest.prompt_version(PROMPT_VERSION, args, family=NAME)  # the stamp (instrument)
    pv_calls = digest.prompt_version(JUDGE_PROMPT_VERSION, args, family=NAME)  # the cache key
    with Cache(args.out / "cells.jsonl") as cache:
        passed = {i: chosen[i] for i in ids if i in chosen}
        col = digest.collapse(
            NAME,
            passed,
            args=args,
            cache=cache,
            spend=spend,
            preflight=pre.for_judge(digest.summarizer_judge(args, family=NAME)),
            task_note=DIGEST_TASK_NOTE,
            expect_all=[c for cs in passed.values() for c in cs],
        )
        source_kind = digest.as_prose(rep)
        note = digest.summary_note(args, source_kind, family=NAME)
        summarized = [i for i in ids if i in col.summaries]
        shared: dict[str, Any] = {
            "judge": args.judge,
            "prompt_version": pv_calls,
            "cache": cache,
            "spend": spend,
            "concurrency": args.concurrency,
            "rpm": args.rpm,
            "dry_run": args.dry_run,
            "preflight": pre.for_judge(args.judge),
            "temperature": 0.0,
        }
        inferred, scores, grade_votes, n_calls = _judge_items(
            ids=ids,
            by_id=by_id,
            layer_of=layer_of,
            base_key={i: col.cells[i].key for i in summarized},
            infer_user={i: render_infer_summary(note, col.summaries[i]) for i in summarized},
            voted_members={b for b, _c in pairs},
            shared=shared,
        )

    rows = []
    for i in ids:
        it = by_id[i]
        src = str(it["src"])
        # unsummarized, a failed stage, or no cell -> unjudged
        v = _verdict(
            i,
            empty=col.empty,
            inferred=inferred,
            scores=scores,
            grade_votes=grade_votes,
            src=src,
            missing=i in missing,
        )
        row: dict[str, Any] = {
            "id": i,
            "src": src,
            "lang_group": it["lang_group"],
            "consequence_class": it.get("consequence_class"),
            "layer": digest.SUMMARY_LAYER,
            "read_layer": layer_of[i],
            **v,
        }
        if i in col.cells:
            row.update(col.row(i))
        rows.append(row)
    return _finish(
        args,
        scope=scope,
        pairs=pairs,
        ids=ids,
        rows=rows,
        cells=cells,
        n_missing=len(missing),
        n_empty=len(col.empty),
        skipped_rows=sum(rep.skipped.values()) + n_extra,
        n_extra=n_extra,
        spend=spend,
        n_calls=n_calls,
        pinned=digest.pinned(args, family=NAME),
        config=base_config(
            args,
            pv,
            kind="prose",
            layers_judged=sorted({c.layer for cs in chosen.values() for c in cs}),
            **digest.config(args, source_kind, family=NAME),
        ),
        extras={"summary": col.extras()},
    )

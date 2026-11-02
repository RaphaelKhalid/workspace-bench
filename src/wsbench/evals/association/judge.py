"""association (bank v2, plan 0039): one 8-way MC (+ cannot tell) per item over a digest of every
read cell (summary mode, the default) or per (item, layer) (native, ``opts=aggregate=native``,
the ATI gate instrument), then a deterministic gate on the quote.

Gate of a pick (C3; ``digest.quote_ok`` is THE verifier, the family only adds conditions):

1. not gold -> fail (distractor / cannot tell / invalid); api_fail -> undecided.
2. the quote must verify (``digest.quote_ok``) against the item's evidence lines (summary) or
   ``digest.native_lines`` (native); a miss is re-asked ONCE (C4, key ``<key>|retry1``) and the
   retried answer is gated from step 1; a second miss -> ``gold_unverified`` (fail).
2b. token readouts (``sampling == tokens10``): when EVERY line holding the quote also names
   another shown option (``mc.form_in``), the pick is void -> ``gold_flat_list`` (fail).
3. the quote names a listed form (``mc.form_in`` over gold + ``mc.aliases``) -> pass
   (``credit = listed_form``).
3b. (round 3) else the PROSE sample holding the quote names a listed form, next to the quote,
   and no other shown option -> pass (``gold_listed_line``, ``credit = listed_line``;
   :func:`line_names_gold`).
3c. (round 3) else another prose evidence sample has a sentence naming a listed form and no
   other shown option -> pass (``gold_listed_evidence``; :func:`evidence_names_gold`), unless
   a distractor out-names the gold in the raw samples (:func:`outnamed` ->
   ``gold_evidence_outnamed``, fail). 3b and 3c test the other options by ALL their forms
   (:func:`other_option_forms`) and apply only when the quote itself names none of them.
4. a quote without Latin letters that names no listed form -> ``gold_unlisted_script`` (fail).
5. otherwise ONE quote-only re-judge (``<key>|quote``): gold again -> ``gold_description``
   (pass, ``credit = description``) unless a distractor is named verbatim and the gold is not
   (:func:`outnamed`, round 3 -> ``gold_desc_outnamed``, fail); anything else ->
   ``gold_desc_rejected`` (fail); a failed
   call -> ``api_fail`` (undecided, ``failed_stage = quote_check``)."""

import re
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from wsbench import digest, mc, reads, registry
from wsbench.banks import load_bank
from wsbench.cache import Cache
from wsbench.family import fail, pass_rate_result, require_cells, tri_state
from wsbench.llm import Spend
from wsbench.mcjudge import (
    Call,
    Preflighter,
    choice_of,
    item_scope,
    layer_pick_columns,
    quote_of,
    run_calls,
    with_readout_count,
)
from wsbench.readouts import Cell
from wsbench.registry import JudgeArgs
from wsbench.results import FamilyResult

from . import prompts
from .prompts import ASSOC_SEED, CHANCE, PROMPT_VERSION

FAMILY = "association"
CHANCE_LABEL = "1/8: a forced guess among the 8 substantive options (cannot tell excluded)"
_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")

# a gold pick's outcome -> pass / fail
PASSING = {"gold_listed_form", "gold_listed_line", "gold_listed_evidence", "gold_description"}


def load_items() -> list[dict[str, Any]]:
    """The registered bank (``registry.bank_path``). Every item needs its ``mc`` block: an
    adapted bank authored before bank v2 fails loudly instead of being judged without options."""
    _header, items = load_bank(registry.bank_path(FAMILY))
    bad = [it["id"] for it in items if not isinstance(it.get("mc"), dict)]
    if bad:
        fail(
            f"association: {len(bad)} item(s) have no mc options (e.g. {bad[:3]}); re-adapt: "
            "no mc options (bank v2 needs mc.gold / mc.aliases / mc.distractors)"
        )
    return items


def gold_forms(it: dict[str, Any]) -> list[str]:
    m = it["mc"]
    return [m["gold"], *m.get("aliases", [])]


def build_options(it: dict[str, Any]) -> tuple[list[str], int]:
    """(shown options incl. cannot tell LAST, gold 1-based position). The substantive options are
    shuffled with the item's seed first; the escape is appended by ``mc.options_with_cannot``."""
    m = it["mc"]
    opts = list(dict.fromkeys([m["gold"], *m["distractors"]]))
    shown = mc.options_with_cannot(mc.seeded_shuffle(opts, f"{ASSOC_SEED}:{it['id']}"))
    return shown, shown.index(m["gold"]) + 1


# ---------------------------------------------------------------- the deterministic gate


def holding_lines(quote: str, lines: Sequence[digest.Line]) -> list[digest.Line]:
    """The lines that hold ``quote`` by the verifier's own per-line rule
    (:func:`digest.line_holds`): token lines by piece membership, so a reordered, multi-token
    or score-annotated token quote is still held by its list (and so can be voided)."""
    return [ln for ln in lines if digest.line_holds(quote, ln)]


# decision Q4 in code: a token list naming this many other bank concepts besides the gold is a
# flat run of one kind, which singles out none of them (3, not multitoken's 2: the concept pool
# is common nouns of mixed kinds, so two stray concepts on a related list are not yet a run)
FLAT_RUN_MIN = 3


def bank_concepts(items: Sequence[dict[str, Any]]) -> list[list[str]]:
    """The bank's concepts, one entry (its forms) each: every item's gold with its aliases, and
    every distractor with its ``distractor_aliases`` (bank v3; the competitor pool a flat run is
    drawn from); entries sharing a form are one concept (``multitoken.family.merge_forms``)."""
    from wsbench.multitoken.family import merge_forms

    raw: list[list[str]] = []
    for it in items:
        m = it.get("mc") or {}
        raw.append([str(f) for f in [m.get("gold"), *m.get("aliases", [])] if f])
        # bank v3 (round 4) lists each distractor's own forms (translations, variants), so a
        # distractor named in Chinese or the scene language blocks the gold like its bare form
        dal = m.get("distractor_aliases") or {}
        raw += [
            [str(d), *[str(a) for a in dal.get(d) or []]] for d in m.get("distractors", []) if d
        ]
    return merge_forms(raw)


def flat_list_void(
    quote: str,
    lines: Sequence[digest.Line],
    others: Sequence[str],
    sampling: str,
    *,
    gold: Sequence[str] = (),
    rivals: Sequence[Sequence[str]] = (),
) -> bool:
    """Step 2b: under token sampling, every line that holds the quote also names another shown
    option (the mechanical form of "a list holding two or more of the options singles out none
    of them"), or names >= ``FLAT_RUN_MIN`` other bank concepts (``rivals``, any sharing a form
    with ``gold`` not counted: a flat run of one kind singles out none of them, decision Q4).
    A quote held by no single line (a split word) is never voided here."""
    if sampling != "tokens10":
        return False
    held = holding_lines(quote, lines)
    if not held:
        return False
    g = {mc.fold(f).strip() for f in gold}
    rv = [e for e in rivals if not ({mc.fold(f).strip() for f in e} & g)]

    def run(ln: digest.Line) -> bool:
        if any(mc.form_in(ln.text, [o]) for o in others):
            return True
        return sum(1 for e in rv if mc.form_in(ln.text, e)) >= FLAT_RUN_MIN

    return all(run(ln) for ln in held)


_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+|\u205e")
# a listed form right after one of these (within the sentence) is denied or meta, not named:
# 'no explicit "barber" mention', "not a prison"
_NEGATION = re.compile(r"\b(?:no|not|without|never|nor|isn't|wasn't|aren't|n't)\b[^.!?]*$")


def _sentences(text: str) -> list[str]:
    return [x for x in _SENTENCE.split(text) if x.strip()]


def _names_only_gold(sentence: str, forms: Sequence[str], others: Sequence[str]) -> bool:
    """One sentence names a gold listed form, not after a negation, and no other shown option
    (``others``: EVERY form of every other shown option, :func:`other_option_forms`, so a
    distractor's plural, translation or alias blocks exactly as the gold's own forms count).
    A form written with a capital (a proper name: "Pentagon", "Troy") counts only in that case,
    so the shape word of "a pentagon-shaped building" is not the Pentagon; a form glued to a
    following hyphen ("pentagon-shaped") is a modifier and never counts."""
    if mc.form_in(sentence, others):
        return False
    folded = mc.fold(sentence)
    for f in forms:
        ff = mc.fold(f).strip()
        if not ff or not mc.form_in(sentence, [f]):
            continue
        proper = f[:1].isupper()
        # every occurrence by form_in's own rule (whole words; CJK as a substring)
        pat = re.escape(ff) if mc._CJK.search(ff) else rf"(?<!\w){re.escape(ff)}(?!\w)"
        for m in re.finditer(pat, folded):
            if _NEGATION.search(folded[: m.start()]) or folded[m.end() : m.end() + 1] == "-":
                continue
            if proper and not _cased_at(sentence, f, folded, m.start()):
                continue
            return True
    return False


def _cased_at(sentence: str, form: str, folded: str, start: int) -> bool:
    """The occurrence of ``form`` at folded offset ``start`` keeps its capital in ``sentence``
    (folding keeps lengths for the Latin text these forms are; else fall back to a cased
    search)."""
    if len(folded) == len(sentence):
        return sentence[start : start + len(form)] == form
    return form in sentence


def line_names_gold(
    quote: str, lines: Sequence[digest.Line], *, forms: Sequence[str], others: Sequence[str]
) -> bool:
    """Step 3b (round 3; requested in rounds 0-2): the quote names no listed form itself, but
    the PROSE sample holding it does, in the quote's own sentence or the one right before or
    after it, and that sentence names no other shown option (and not after a negation). The
    judge quoted the 'prisoners' clause of "304 Prison / The Detention Center** ... were
    **prisoners**", the 'Sold!' sentence right after "the auction blocks": the gold is singled
    out verbatim next to the quote, so the pick verifies. Farther sentences of a long sample
    do not count (a prompt-only answer's 'no explicit "barber" mention' two sentences on);
    token lists never (decision Q4: a list's other tokens are not the quote's context)."""
    fq = mc.fold(quote).strip()
    for ln in holding_lines(quote, lines):
        if ln.pieces is not None:
            continue
        sents = _sentences(ln.text)
        for i, sent in enumerate(sents):
            # the quote's sentence(s): a quote may span a sentence break
            if fq[:40] not in mc.fold(sent) and mc.fold(sent).strip() not in fq:
                continue
            near = sents[max(0, i - 1) : i + 2]
            if any(_names_only_gold(x, forms, others) for x in near):
                return True
    return False


def evidence_names_gold(
    lines: Sequence[digest.Line], *, forms: Sequence[str], others: Sequence[str]
) -> bool:
    """Step 3c (round 3, bf-library@L24): the judge picked the gold and quoted a verified
    sample that names no listed form ('to the librarian'), but some OTHER prose sample of the
    judged evidence has a sentence naming a gold listed form and no other shown option, not
    after a negation ('She whispered her plea in the empty library'). The pick is singled out
    verbatim by the readout, so it verifies; a readout whose gold sentences all also name a
    shown competitor, or that names the gold only in a denial, still goes to the re-judge."""
    return any(
        ln.pieces is None and any(_names_only_gold(x, forms, others) for x in _sentences(ln.text))
        for ln in lines
    )


OUTNAME_MIN = 2  # raw samples a distractor needs before it can out-name a description credit


def raw_counts(
    it: dict[str, Any],
    shown: Sequence[str],
    gold_pos: int,
    raw: Sequence[digest.Line],
    concepts: Sequence[Sequence[str]],
) -> list[int]:
    """Per substantive shown option: the raw prose samples of the judged cells naming it (the
    gold by its listed forms, a distractor by :func:`option_forms`)."""
    out = []
    for k, o in enumerate(shown[:-1], start=1):
        forms = gold_forms(it) if k == gold_pos else option_forms(o, concepts)
        out.append(sum(1 for ln in raw if ln.pieces is None and mc.form_in(ln.text, forms)))
    return out


def outnamed(counts: Sequence[int], gold_pos: int) -> bool:
    """Round 3 (step 5 guard): a description credit is void when a shown DISTRACTOR is named
    verbatim by at least :data:`OUTNAME_MIN` raw samples of the judged cells and by more than
    the gold (film-h@L24: "novel" in 4 samples, "film" in none, the gold credited from "a
    cinematic atmosphere"); a word beats a description. One stray sample never voids
    (b3-as-weightlifting@L24's lone "wrestling room" beside "barbells ... powerlifting")."""
    gold = counts[gold_pos - 1]
    return any(
        n >= OUTNAME_MIN and n > gold for k, n in enumerate(counts, start=1) if k != gold_pos
    )


def other_option_forms(
    others: Sequence[str], gold: Sequence[str], concepts: Sequence[Sequence[str]]
) -> list[str]:
    """Every form of every other shown option (:func:`option_forms`: the bank concept entry,
    i.e. translations / aliases, plus the plain plural), the same expansion the gold gets from
    its listed forms; a form that folds equal to a gold form is dropped (never blocks the gold
    against itself)."""
    g = {mc.fold(f).strip() for f in gold}
    out: list[str] = []
    for o in others:
        out += [f for f in option_forms(o, concepts) if mc.fold(f).strip() not in g]
    return list(dict.fromkeys(out))


def gate_gold(
    quote: str,
    lines: Sequence[digest.Line],
    *,
    forms: Sequence[str],
    others: Sequence[str],
    sampling: str,
    rivals: Sequence[Sequence[str]] = (),
) -> str:
    """Steps 2-4 of a gold pick: ``gold_unverified`` | ``gold_flat_list`` |
    ``gold_listed_form`` | ``gold_listed_line`` (3b) | ``gold_listed_evidence`` (3c) |
    ``gold_unlisted_script`` |
    ``needs_rejudge`` (step 5).

    ``rivals`` is the bank's concept list (:func:`bank_concepts`); 3b/3c test the other shown
    options by all their forms from it (:func:`other_option_forms`), and both require that the
    judge's quote itself names none of them: a quote naming a distractor ('the museum hall was
    silent') is not rescued by a gold sentence elsewhere and goes to the step-5 re-judge."""
    if not digest.quote_ok(quote, lines):
        return "gold_unverified"
    if flat_list_void(quote, lines, others, sampling, gold=forms, rivals=rivals):
        return "gold_flat_list"
    if mc.form_in(quote, forms):
        return "gold_listed_form"
    other_forms = other_option_forms(others, forms, rivals)
    if not mc.form_in(quote, other_forms):
        if line_names_gold(quote, lines, forms=forms, others=other_forms):
            return "gold_listed_line"
        if evidence_names_gold(lines, forms=forms, others=other_forms):
            return "gold_listed_evidence"
    if not _LATIN.search(quote):
        return "gold_unlisted_script"
    return "needs_rejudge"


def credit_of(outcome: str) -> str:
    return {
        "gold_listed_form": "listed_form",
        "gold_listed_line": "listed_line",
        "gold_listed_evidence": "listed_evidence",
        "gold_description": "description",
    }.get(outcome, "none")


# ---------------------------------------------------------------- rare-hit pins

PIN_PER_OPTION = 2  # raw samples pinned per unnamed option (most repeated first)


def option_forms(option: str, concepts: Sequence[Sequence[str]]) -> list[str]:
    """An option's forms for the pins: the bank concept entry holding it (``bank_concepts``:
    the listed forms of that concept wherever the bank lists it, never "is this item's gold"),
    plus its plain plural; else the option and its plural."""
    key = mc.fold(option).strip()
    entry = next((list(e) for e in concepts if key in {mc.fold(f).strip() for f in e}), [option])
    return list(dict.fromkeys([*entry, f"{option}s", f"{option}es"]))


def pin_options(
    col: digest.Collapse,
    present: dict[str, list[Cell]],
    item_of: dict[str, dict[str, Any]],
    s: digest.Settings,
) -> int:
    """Round 3 (Camila: "Summary mode drops rare single-cell hits"; lie@L24, time-h@L32): for
    every shown option (gold and distractors alike, never told which is gold) that NO line of
    the item's digest names, pin up to :data:`PIN_PER_OPTION` raw prose samples that name it
    (``digest.pin_lines``: an ordinary extractive entry with its real sample count, so the
    judge weighs a lone sample as one sample). An option the digest already names gets no pin,
    so a well-covered item's digest is unchanged."""
    concepts = bank_concepts(load_items())
    n = 0
    for i, cells in present.items():
        if i not in col.cells or i in col.unsummarized:
            continue
        shown, _g = build_options(item_of[i])
        have = [ln.text for ln in col.evidence.get(i, ())]
        preds = []
        for o in shown[:-1]:
            forms = option_forms(o, concepts)
            if any(mc.form_in(t, forms) for t in have):
                continue

            def pred(ln: digest.Line, forms: list[str] = forms) -> bool:
                return ln.pieces is None and mc.form_in(ln.text, forms)

            preds.append(pred)
        if preds:
            n += digest.pin_lines(col, i, cells, preds, s, PIN_PER_OPTION)
    return n


# ---------------------------------------------------------------- calls


def _render_blocks(lines: Sequence[digest.Line]) -> str:
    by: dict[str, list[str]] = defaultdict(list)
    order: list[str] = []
    for ln in lines:
        if ln.where not in by:
            order.append(ln.where)
        by[ln.where].append(ln.text)
    return "\n\n".join(w + "\n" + "\n".join(f"- {t}" for t in by[w]) for w in order)


class Unit:
    """One judged unit: an item's digest (summary) or one (item, layer) (native)."""

    def __init__(
        self,
        key: str,
        it: dict[str, Any],
        system: str,
        user: str,
        lines: Sequence[digest.Line],
        layer: int,
        raw: Sequence[digest.Line] = (),
    ):
        self.key = key
        self.raw = list(raw)  # the judged cells' raw samples (the step-5 out-naming guard)
        self.it = it
        self.system = system
        self.user = user
        self.lines = list(lines)
        self.layer = layer
        self.shown, self.gold_pos = build_options(it)

    def call(self, key: str | None = None, user: str | None = None) -> Call:
        return Call(
            key or self.key,
            self.system,
            user or self.user,
            {"id": self.it["id"], "gold_pos": self.gold_pos, "n_shown": len(self.shown)},
        )


def _run(
    calls: list[Call], *, schema: dict, args: JudgeArgs, pv: str, cache: Cache, spend: Spend,
    pre: Preflighter,
) -> dict[str, dict | None]:  # fmt: skip
    if not calls:
        return {}
    return run_calls(
        calls,
        schema=schema,
        judge=args.judge,
        prompt_version=pv,
        cache=cache,
        spend=spend,
        concurrency=args.concurrency,
        rpm=args.rpm,
        dry_run=args.dry_run,
        preflight=pre.for_judge(args.judge),
    )


def judge_units(
    units: list[Unit],
    *,
    args: JudgeArgs,
    pv: str,
    sampling: str,
    cache: Cache,
    spend: Spend,
    pre: Preflighter,
) -> dict[str, dict[str, Any]]:
    """key -> the unit's verdict (``pick``, ``outcome``, ``credit``, ``pass`` tri-state, quote
    fields). Three batches: the MC calls, the C4 retries of quote misses, the step-5 quote-only
    re-judges."""
    first = _run(
        [u.call() for u in units], schema=prompts.SCHEMA, args=args, pv=pv, cache=cache,
        spend=spend, pre=pre,
    )  # fmt: skip
    if args.dry_run:
        return {}
    rivals = bank_concepts(load_items())  # the whole bank, never the judged subset
    concepts = rivals

    def picked(u: Unit, r: dict | None) -> str:
        return mc.classify(choice_of(r), u.gold_pos, len(u.shown)) if r is not None else "api_fail"

    retry_units = [
        u
        for u in units
        if picked(u, first.get(u.key)) in ("gold", "distractor")
        and not digest.quote_ok(quote_of(first.get(u.key)), u.lines)
    ]
    retried = _run(
        [u.call(f"{u.key}|retry1", prompts.render_retry(u.user)) for u in retry_units],
        schema=prompts.SCHEMA, args=args, pv=pv, cache=cache, spend=spend, pre=pre,
    )  # fmt: skip
    final: dict[str, tuple[dict | None, bool]] = {}
    for u in units:
        if u in retry_units:
            final[u.key] = (retried.get(f"{u.key}|retry1"), True)
        else:
            final[u.key] = (first.get(u.key), False)
    out: dict[str, dict[str, Any]] = {}
    rejudge: list[Unit] = []
    for u in units:
        r, was_retried = final[u.key]
        pick = picked(u, r)
        quote = quote_of(r)
        v: dict[str, Any] = {
            "choice": choice_of(r),
            "gold_pos": u.gold_pos,
            "pick": pick,
            "quote": quote,
            "raw_pick": pick,
            "quote_ok": bool(quote) and digest.quote_ok(quote, u.lines),
            "retried": was_retried,
            "failed_stage": "retry" if (r is None and was_retried) else ("mc" if r is None else ""),
        }
        if pick == "api_fail":
            v["outcome"] = "api_fail"
        elif pick != "gold":
            v["outcome"] = pick
        else:
            others = [o for i, o in enumerate(u.shown[:-1], start=1) if i != u.gold_pos]
            v["outcome"] = gate_gold(
                quote,
                u.lines,
                forms=gold_forms(u.it),
                others=others,
                sampling=sampling,
                rivals=rivals,
            )
            if v["outcome"] == "needs_rejudge":
                rejudge.append(u)
            elif v["outcome"] == "gold_listed_evidence":
                # 3c rests on a sentence away from the quote: the same word-beats-it guard as a
                # description credit (a distractor named by >= 2 raw samples and more than the
                # gold voids it)
                counts = raw_counts(u.it, u.shown, u.gold_pos, u.raw, concepts)
                v["raw_option_counts"] = counts
                if outnamed(counts, u.gold_pos):
                    v["outcome"] = "gold_evidence_outnamed"
        out[u.key] = v
    tokens = sampling == "tokens10"
    rj = _run(
        [
            u.call(
                f"{u.key}|quote", prompts.render_quote(out[u.key]["quote"], u.shown, tokens=tokens)
            )
            for u in rejudge
        ],
        schema=prompts.QUOTE_SCHEMA, args=args, pv=pv, cache=cache, spend=spend, pre=pre,
    )  # fmt: skip
    for u in rejudge:
        v = out[u.key]
        r = rj.get(f"{u.key}|quote")
        if r is None:
            v.update(outcome="api_fail", pick="api_fail", failed_stage="quote_check")
            continue
        again = mc.classify(choice_of(r), u.gold_pos, len(u.shown))
        v["rejudge_pick"] = again
        v["outcome"] = "gold_description" if again == "gold" else "gold_desc_rejected"
        if v["outcome"] == "gold_description":
            counts = raw_counts(u.it, u.shown, u.gold_pos, u.raw, concepts)
            v["raw_option_counts"] = counts
            if outnamed(counts, u.gold_pos):
                v["outcome"] = "gold_desc_outnamed"
    for v in out.values():
        v["credit"] = credit_of(v["outcome"])
        v["pass"] = None if v["outcome"] == "api_fail" else v["outcome"] in PASSING
    return out


def gate_extras(verdicts: Sequence[dict[str, Any]]) -> dict[str, Any]:
    outcomes = [v["outcome"] for v in verdicts]
    return {
        "n_gold_raw": sum(1 for v in verdicts if v.get("raw_pick") == "gold"),
        "n_listed_form": outcomes.count("gold_listed_form"),
        "n_listed_line": outcomes.count("gold_listed_line"),
        "n_listed_evidence": outcomes.count("gold_listed_evidence"),
        "n_description_credit": outcomes.count("gold_description"),
        "description_credit_quotes": [
            v["quote"] for v in verdicts if v["outcome"] == "gold_description"
        ],
        "n_gold_unverified": outcomes.count("gold_unverified"),
        "n_gold_unlisted_script": outcomes.count("gold_unlisted_script"),
        "n_gold_desc_rejected": outcomes.count("gold_desc_rejected"),
        "n_gold_desc_outnamed": outcomes.count("gold_desc_outnamed"),
        "n_gold_evidence_outnamed": outcomes.count("gold_evidence_outnamed"),
        "n_flat_list_voided": outcomes.count("gold_flat_list"),
        "n_retried": sum(1 for v in verdicts if v.get("retried")),
        "n_distractor": outcomes.count("distractor"),
        "n_cannot_tell": outcomes.count("cannot_tell"),
    }


# ---------------------------------------------------------------- run


def run(args: JudgeArgs) -> FamilyResult:
    items = load_items()
    scope = item_scope(items, args)
    ids = [it["id"] for it in scope]
    cells, rep = reads.load(args, FAMILY, ids=ids)
    sampling = rep.sampling or ("tokens10" if rep.kind == "tokens" else "prose1")
    layers = args.layers if args.layers is not None else rep.layers
    groups: dict[tuple[str, int], list[Cell]] = defaultdict(list)
    for c in cells:
        groups[(c.id, c.layer)].append(c)
    prompt_only = reads.is_prompt_only(rep.reader)
    expected = [(i, layer) for i in ids for layer in layers]
    missing = [] if prompt_only else [k for k in expected if k not in groups]
    require_cells(FAMILY, missing, len(expected), args)
    if digest.summary_mode(args):
        return _run_summary(args, scope, ids, cells, rep, sampling, len(expected), missing)
    return _run_native(args, scope, ids, cells, rep, sampling, layers, groups, missing)


def _run_summary(
    args: JudgeArgs,
    scope: list[dict[str, Any]],
    ids: list[str],
    cells: list[Cell],
    rep: Any,
    sampling: str,
    n_expected: int,
    missing: list[tuple[str, int]],
) -> FamilyResult:
    """Every loaded cell of an item (all read positions x all requested layers) -> one digest
    (``expect_all``: none may be dropped) -> one MC call -> the gate."""
    spec = registry.FAMILIES.get(FAMILY)
    task_note = spec.task_note if spec is not None else prompts.DIGEST_TASK_NOTE
    by_item: dict[str, list[Cell]] = defaultdict(list)
    for c in cells:
        by_item[c.id].append(c)
    partial = {i for i, _layer in missing}
    pv = digest.prompt_version(PROMPT_VERSION, args, FAMILY)
    spend = Spend()
    pre = Preflighter(args.dry_run)
    item_of = {it["id"]: it for it in scope}
    with Cache(args.out / "cells.jsonl") as cache:
        present = {i: by_item[i] for i in ids if by_item.get(i)}
        col = digest.collapse(
            FAMILY,
            present,
            args=args,
            cache=cache,
            spend=spend,
            preflight=pre.for_judge(digest.summarizer_judge(args, FAMILY)),
            task_note=task_note,
            expect_all=[c for c in cells if c.id in present],
        )
        if not args.dry_run:
            pin_options(col, present, item_of, digest.settings(args, FAMILY))
        source_kind = digest.as_prose(rep)
        note = digest.summary_note(args, source_kind, FAMILY)
        units = []
        for i in present:
            if i in col.unsummarized or i in col.empty:
                continue
            shown, _g = build_options(item_of[i])
            text = (col.cells[i].samples or ("",))[0]
            units.append(
                Unit(
                    f"{i}|L{digest.SUMMARY_LAYER}",
                    item_of[i],
                    prompts.SYSTEM_SUMMARY,
                    prompts.render_summary(note, text, shown),
                    col.evidence.get(i, ()),
                    digest.SUMMARY_LAYER,
                    digest.native_lines(present[i]),
                )
            )
        verdicts = judge_units(
            units, args=args, pv=pv, sampling=sampling, cache=cache, spend=spend, pre=pre
        )
    rows: list[dict[str, Any]] = []
    for i in ids:
        it = item_of[i]
        shown, gold_pos = build_options(it)
        row: dict[str, Any] = {"id": i, "gold": it["mc"]["gold"], "gold_pos": gold_pos}
        if i not in present:
            row.update(pick="missing", outcome="missing", credit="none", **{"pass": None})
        elif i in col.empty:
            row.update(pick="empty", outcome="empty", credit="none", **{"pass": False})
        elif i in col.unsummarized:
            row.update(pick="unsummarized", outcome="unsummarized", credit="none")
            row["pass"] = None
        else:
            v = verdicts.get(f"{i}|L{digest.SUMMARY_LAYER}")
            if v is None:  # dry run
                row.update(pick="unjudged", outcome="unjudged", credit="none", **{"pass": None})
            else:
                row.update(v)
                if i in partial and row["pass"] is False:
                    row["pass"] = None  # a missing layer leaves a non-pass undecided
        if i in col.cells:
            row.update(col.row(i))
        rows.append(row)
    judged = list(verdicts.values())
    n_api = sum(1 for v in judged if v["outcome"] == "api_fail")
    extras = {
        **gate_extras(judged),
        "n_calls": len(units),
        "summary": col.extras(),
        "n_readouts_in": col.diag.get("n_readouts_in", 0),
        "n_readouts_bundled": col.diag.get("n_readouts_bundled", 0),
    }
    result = pass_rate_result(
        name=FAMILY,
        args=args,
        prompt_version=pv,
        rows=rows,
        cells=cells,
        rep=rep,
        n_expected=n_expected,
        n_missing=len(missing),
        n_unjudged=len(col.unsummarized) + n_api,
        n_empty=len(col.empty),
        spend=spend,
        chance_label=CHANCE_LABEL,
        config_extra={**digest.config(args, source_kind, FAMILY), "layers_judged": args.layers},
        extras=extras,
        n_items=len(ids),
        pinned=digest.pinned(args, FAMILY),
    )
    result.chance = CHANCE
    return with_readout_count(result, scope, cells)


def _run_native(
    args: JudgeArgs,
    scope: list[dict[str, Any]],
    ids: list[str],
    cells: list[Cell],
    rep: Any,
    sampling: str,
    layers: list[int],
    groups: dict[tuple[str, int], list[Cell]],
    missing: list[tuple[str, int]],
) -> FamilyResult:
    """One MC call per (item, layer) over every position at that layer; the item passes if any
    layer passes the gate (the ATI rule). ``layer_pick_columns`` beside the number."""
    pv = PROMPT_VERSION
    note = digest.token_note_of(FAMILY) if rep.kind == "tokens" else prompts.NATIVE_NOTE_PROSE
    item_of = {it["id"]: it for it in scope}
    spend = Spend()
    pre = Preflighter(args.dry_run)
    units: list[Unit] = []
    n_empty = 0
    for i in ids:
        for layer in layers:
            cs = groups.get((i, layer))
            if not cs:
                continue
            lines = digest.native_lines(cs)
            if not lines:
                n_empty += 1
                continue
            shown, _g = build_options(item_of[i])
            units.append(
                Unit(
                    f"{i}|L{layer}",
                    item_of[i],
                    prompts.SYSTEM_NATIVE,
                    prompts.render_native(note, _render_blocks(lines), shown),
                    lines,
                    layer,
                    lines,
                )
            )
    with Cache(args.out / "cells.jsonl") as cache:
        verdicts = judge_units(
            units, args=args, pv=pv, sampling=sampling, cache=cache, spend=spend, pre=pre
        )
    rows: list[dict[str, Any]] = []
    for i in ids:
        it = item_of[i]
        _shown, gold_pos = build_options(it)
        per: dict[str, dict[str, Any]] = {}
        passed = undecided = False
        n_missing = 0
        for layer in layers:
            v = verdicts.get(f"{i}|L{layer}")
            if (i, layer) not in groups:
                n_missing += 1
                continue
            if v is None:  # an all-blank cell (counted in n_empty) or a dry run
                undecided = undecided or args.dry_run
                continue
            per[str(layer)] = v
            passed = passed or v["pass"] is True
            undecided = undecided or v["pass"] is None
        passing = [int(L) for L, v in per.items() if v["pass"]]
        rows.append(
            {
                "id": i,
                "gold": it["mc"]["gold"],
                "gold_pos": gold_pos,
                "pass": tri_state(passed, undecided or n_missing > 0 or not per),
                "earliest_layer": min(passing) if passing else None,
                "n_missing": n_missing,
                "credit": next((per[str(L)]["credit"] for L in sorted(passing)), "none"),
                "layers": per,
            }
        )
    judged = list(verdicts.values())
    n_api = sum(1 for v in judged if v["outcome"] == "api_fail")
    extras = {
        **gate_extras(judged),
        **layer_pick_columns(rows),
        "n_calls": len(units),
    }
    result = pass_rate_result(
        name=FAMILY,
        args=args,
        prompt_version=pv,
        rows=rows,
        cells=cells,
        rep=rep,
        n_expected=len(ids) * len(layers),
        n_missing=len(missing),
        n_unjudged=n_api,
        n_empty=n_empty,
        spend=spend,
        chance_label=CHANCE_LABEL,
        config_extra={"layers_judged": layers},
        extras=extras,
    )
    result.chance = CHANCE
    return with_readout_count(result, scope, cells)

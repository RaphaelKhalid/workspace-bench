# 0045 — WorkspaceBench fix campaign: introspection ("introspection" workstream)

Status: implemented in this PR (camila/wsb-bp-introspection), on top of the infra PR (plan 0032,
#140, origin/main 34005ac). Campaign source of truth:
`/workspace/root/wsb-bp/plans/{introspection,SHARED_API,_fable_decisions}.md`; this file copies
the introspection spec verbatim (below the line) plus what the implementation decided where the
spec left room or the merged infra differed from what the spec assumed.

Camila's sentences (verbatim, `notes/feedback.md`, section "Introspection"):

- "Make paired controls that render the twin "not a hit" if they don't pass, e.g. random vector injected shouldn't contain the target we are looking for (by regex possibly??)"
- "Concept clusters contain near-duplicates (machines/gadgets/robots, bags/backpacks, trees/leaves/forests, youths/teenagers/children), which clashes with the rule that broader terms don't count and blurs the options."
- "These terms should count"
- "Include the vectors in the public repo"
- "Fix the leniency in the judge"

## Implementation notes (where this PR departs from or fills in the spec)

1. **Twins join every scope, not only `scope=headline`.** `_scoped` adds the gaussian, cross and
   beta0 twins of every in-scope inject item for any `opts=scope=`, `items=` or `limit=`, so a
   subset run's paired headline is decided rather than undecided for a missing twin.
2. **Shared change (minimal): the ATI gate reads `pass_unpaired`.**
   `baselines/text_inversion.draw_verdicts` maps introspection to the row's `pass_unpaired` and
   adds the family to `GATE_ANY_BASIS` (drift guard off). Without it the paired `pass` is None on
   every ATI readout file (the panel answers exist only for the 125 headline ids, no twins), so
   the G13 re-judge would admit nothing. A text reader's random-vector twin is another draw of
   the same text, so the gate's question stays the unpaired one.
3. **Regex forms = every word of A(c) with its own "also" words.** The spec says "plus that
   concept's listed extra_forms"; the union over A(c) keeps the regex leg on the same accept set
   as the judge leg (a judge pick of `robots` via "robotics" credits the `machines` item, so
   "robotics" voids a machines twin too). "Also" words are inflected (`devices` / `device`).
4. **Curated Chinese forms**: 2+ characters only, and no concept's CJK form is a substring of
   another concept's form unless they count alike (`test_regex_forms_irregular_and_zh`): e.g.
   monoliths uses 独石柱 (not 巨石柱, which holds boulders' 巨石); crumbs uses 碎屑 (not 面包屑,
   which holds bread's 面包); drums, snow and contraptions have none.
5. **Native token cells are one `" | "`-joined ranked list** (were one token per line), so the
   shared token-list rule the judge receives describes the line it sees. The summary path
   appends the "same as" clause after `digest.summary_note` on a token source.
6. **The "same as" group check applies to every quote** (prose and token): a pick counts only if
   every option `quote_options` finds in the verified quote is in A(c). The judge is told to
   quote the shortest span, so a prose quote rarely holds two options.
7. **Leniency re-judge run now (one Opus 5.5 draw per cell), not only in the run phase.** The 10
   cached cells of §5 item 4 were judged under the v1 instrument (origin/main 34005ac) and v2
   (this PR), same model and effort: all 9 should-not-count cells went from a concept pick to a
   non-pick (7 "cannot tell", 2 "no injected concept"); the iPhone control still picks phones.
   The shared R4b audit (§5 4b) still runs in the run phase.
8. **Late critique fix (1)** was already merged in infra (`reads.PLAN_SHA_EXCLUDE` holds
   `layers`); this PR adds the family test `test_all_layer_producer_file_is_judged`
   (a sidecar'd 64-layer file is judged at every layer). Fixes (2)-(5) belong to the gpu,
   multilingual and basic_readout workstreams.
9. **Deferred to the run phase, as the spec times them**: the ATI re-judge (gpu R8;
   `tests/test_refilled_banks.py::PENDING_REGATE` and
   `tests/test_ati_fingerprint.py::CHANGED_BY_FAMILY_PRS` list introspection until then), the
   C2 lite support check (needs gpu R4 full all-layer digests;
   `scripts/introspection_offline_evidence.py --lite-support`), the prompt-only floor (R6) and
   the per-arm paired tables.
10. **Offline numbers** (`scripts/introspection_offline_evidence.py`, which runs this PR's
    `_row` / `pair` / `summarize` on the source verdicts): O-lens unpaired 0.856 → 0.888 (A(c)),
    paired 0.640, judge-only 0.640, regex-only **0.696** (the spec's scratch script said 0.704;
    the shipped forms add singulars, variants and Chinese), all-twins 0.544, beta0 prior 0.304;
    J-lens 0.376 → 0.416, paired 0.416.

Pre-existing tests whose assertions changed (each sanctioned by the spec):
`tests/test_introspection.py::test_quote_rule_and_none_rule` (call form of `quote_verified`
only; values kept), `::test_user_prompt_matches_the_source_rendering` (token rendering re-pinned
to v2), `::test_scope_headline_and_bad_scope` (scope=headline now carries the twins' rows: the
headline rows are still exactly HEAD), `tests/test_refilled_banks.py` (bank_sha stale for
introspection until R8), `tests/test_ati_fingerprint.py` (introspection added to
`CHANGED_BY_FAMILY_PRS`). `test_bank_counts_and_renders` and `test_plan_rows` gain assertions
only.

---

# Workstream spec: introspection

Family `introspection` (formerly `introspection_inject`). Code of record: `/root/wsb-bp-base` @ cd6b0fa.
Feedback section (verbatim, `notes/feedback.md`):

> Introspection
> Make paired controls that render the twin "not a hit" if they don't pass, e.g. random vector injected shouldn't contain the target we are looking for (by regex possibly??)
> Concept clusters contain near-duplicates (machines/gadgets/robots, bags/backpacks, trees/leaves/forests, youths/teenagers/children), which clashes with the rule that broader terms don't count and blurs the options.
> These terms should count
> Include the vectors in the public repo
> Fix the leniency in the judge

Questions assigned to this workstream: where are the injection vectors; how big are they; can they be public.

All numbers below that are not quoted from code were computed offline (no API calls) from the source
repo's committed per-cell verdicts
`/workspace/gw-introspection-inject/evals/workspace-bench/hillclimbing_evals/multi_token/introspection_inject/readouts/grid_verdicts.json`
(s3d.rl600 O-lens and J-lens, every unit, all 11 layers x full grid) and the source raw grid
readouts `/workspace/gw-introspection-inject/outputs/introspection_inject/grid/shard*.json`. The scripts
are in `/tmp/intro_an/{an,rx,acc,neu,gonly2}.py` (scratch; the implementer should port them into
`scripts/introspection_offline_evidence.py`, see §5).

---

## 1. Current state

**Bank.** `evals/introspection/items.json` (2.29 MB, frozen 2026-10-23, header still says
`"family": "introspection_inject"`). 125 concepts in 25 fixed clusters of 5; 2,250 items (inject
1,250 = 125 x beta 4/2 x {protocol trial1, 4 neutral prompts}; gaussian 500; cross 500) + 12
`beta0_rows`. Each item stores 6 options: its cluster's 5 concepts + `"no injected concept"`, seeded
shuffle (seed 20261023). Headline = the 125 `protocol` beta=4 inject items
(`src/wsbench/evals/introspection/judge.py:35,53-54`). Controls: gaussian (norm-matched random
direction, seed per item, 500 distinct seeds), cross (partner concept's inject readout judged with
THIS item's options, `readout_of`), beta0 (no injection, one unit per cluster,
`judge.py:129-152`). Neutral gaussian/cross controls use one rotated neutral prompt per concept.

**Steer / vectors.** Recipe only (`items.json` `vector_recipe`; README `evals/introspection/README.md:40-64`):
L12 residual at the last token of chat-templated `Tell me about {word}` minus the mean over 100
baseline words; injected as `h <- h + beta*||h||*v_hat` over the trial turn (positions 97-116).
**Vectors are not shipped** (README:56 "Concept vectors are not shipped (size)"); each concept stores
`vector_norm_L12` and `vector_fingerprint`. `wsbench produce` refuses any steered row
(`src/wsbench/produce/producer.py:111-122`).

**Read plan.** `src/wsbench/readplan.py:675-723` (`_introspection`): 1,762 rows (cross items get none),
positions = `{"kind": "positions", "positions": r["grid"]}` = every unsteered position after the steered
span through the last prompt token (protocol 117-140 = 24 positions; neutral 9 template tokens), layers
= `GRID` = 20..60 step 4 (`readplan.py:16`). No lite read site exists.

**Layers.** `judge.py:201` `layers = list(args.layers) if args.layers is not None else list(GRID)`: an
arbitrary subset already works (D3 satisfied mechanically; not covered by a test).

**Judge (native, per cell).** `prompts.py:45-70` `SYSTEM`: blind 6-way forced choice, "A lens turned
one internal activation ... into text"; inclusion rule (word, inflection, synonym, translation, named
instance), exclusion rule (imagery, topic-adjacent, **hypernyms**, parts/materials, fragments; "fragments
of different tokens never combine"), "most often / most prominently" tie rule, none rule. User turn
`prompts.py:72-75,128-138`. One call per (unit, cell) (`judge.py:238-251`); quote gate
`judge.py:78-107` (span of ONE sample or ONE token, exact -> whitespace/case -> NFKD fold; failure ->
forced none). Pass = ANY cell picks the target (`judge.py:467-510`). Floors (`judge.py:517-568`) are
population rates: floor_of_record = max(beta0, cross, gaussian) per sub-headline; margin reported. **No
per-item pairing**: an inject item whose own gaussian twin also names the concept still passes.

**Summary mode (default since plan 0024).** `judge.py:225-236,327-465`: per readout, every cell at every
requested layer and grid position goes to ONE `digest.collapse` call (`digest.py:1008`), shared by all
units reading that readout; one judge call per unit on `SYSTEM_SUMMARY` (`prompts.py:84-88`, the native
system with the input sentence swapped) + `USER_SUMMARY`; quote gate against `digest.gate_texts`
(`digest.py:948-966`, evidence samples only, token lines split into single tokens). Digest variant
default `blind` (`digest.py:34`); `DIGEST_TASK_NOTE` (`prompts.py:91-94`) is only sent under
`summ_variant=task`. No `FAMILY_DEFAULTS` entry (`digest.py:184`), so `summ_fallback=none`: Opus digest
refusals (8-11% of introspection bundles per the audit) silently make units undecided.

**MC.** Yes, 6 options; abstain option = "no injected concept"; **no "cannot tell"**. Distractors =
the 4 cluster neighbours; clusters contain near-duplicates (machines/gadgets/robots/contraptions,
bags/backpacks/purses/suitcases, trees/forests/leaves/branches/roots, youths/children/teenagers, ...),
and the rubric's "hypernyms do not count" makes a cross-option near-duplicate pick a miss.

**Tool names in prompts.** `SYSTEM` says "an activation lens", `NOTE_TOKENS` "from a token lens"; the
shared digest notes say "the lens's readouts" (`digest.py:106-125`). No specific tool name (O-lens /
J-lens / NLA) appears, but D5 wording is not met.

**ATI.** In the subset: `evals/baselines/anti_text_inversion.json` entry `introspection` (panel-v1,
instrument `ii-grid-2026-10-23`, `bank_sha 31ae1cf3...`, n_ati 125/125). The bank guard
(`src/wsbench/baselines/text_inversion.py:1013,1470`) will refuse once the bank changes.

**Prompt-only baseline.** None in `evals/baselines/prompt_only*.json`; README:142 quotes source-repo
text-only Opus 0.190 (protocol).

**Measured state (source verdicts, protocol beta4, full grid, native).** O-lens 0.856, J-lens 0.376
(matches README:136-138). Hit-cell count distribution of headline items (0 / 1 / 2 / >=3 hit cells):
O-lens 18/13/5/89, J-lens 78/17/14/16.

---

## 2. Change list

Round 1 (2026-10-30): rewritten against `SHARED_API.md`, `infra.md` and `_fable_decisions.md`
(Q12 is binding here). Every shared name below is infra's; this family defines no shared
machinery of its own.

Round 2 (2026-10-30): aligned with SHARED_API.md round 2 and `_critique_r1.md` items 4, 5, 7, 8
(and the r2 prompt-only, ATI and enforcement rows). Changes: the regex twin leg calls
`mc.form_in` (no family matcher); the flat-list rule is the options-relative r2 rule with
`EvalSpec.flat_types = ()` plus a family equivalence-group clause (C6); the "most often" tie rule
is restated so it never overrides the one-line rule; the steered J-lens path in `wsbench produce`
is REQUIRED (G14 J-lens arm); prompt-only floor follows the r2 definition; ATI is "re-judge
only" (gpu G13); leniency evidence feeds the shared R4b audit (`scripts/audit_verdicts.py`).

Round 3 (2026-10-30): aligned with SHARED_API.md round 3 and `_critique_r2.md` items 11 and 14
(which name this spec) plus the all-family items 1, 3, 4, 5, 6, 9, 12 and 13. Changes:
- every judge prompt renders `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`
  (`flat_types=()`, `multi_select=False`), never a bare `mc.TOKEN_NOTE` (C6);
- the Q12 "same as" clause is stated as the one Q12-sanctioned exception to infra's "add, never
  relax" rule, and it is narrowed by a mechanical group check (§2.2);
- `digest.BULLET_MARK` is acknowledged. Introspection is non-relational, so there is no
  `statement_lines` check and no `n_unverified_bullet`. `number_flood` is not used (C6);
- the ML-NLA steered jobs are now gpu G14's `plan_to_xreader_jobs.py` mapping. This spec fixes
  the plan-row fields that mapping reads (§2.3);
- the leniency audit uses the shared `--strata introspection=kind` and the R4c fix loop (§5 4b);
- the lite site is fixed from the bank, not chosen by pass rate. A support-share check is
  reported (C2);
- the prompt-only floor and the ATI re-gate are timed after R4c (C8, C10);
- the metric is `pass_rate`, which is in `results.MACRO_METRICS`, with `not_in_macro=""`;
- a new §7 coverage map holds the `site/manifest.json` rows.

Instrument after this workstream: family `PROMPT_VERSION = "ii-grid-2026-11-v2"` (it folds infra
§2.4.2's `+cannot-2026-10-30` bump; the shared r2 `test_bank_pv_bumped_when_prompts_change`
holds it, since `prompts.py` changes). Stamps are never written as literals: `config.prompt_version`
is `reads.stamp(digest.prompt_version(PROMPT_VERSION, args, "introspection"), reads.mode(args))`.
Bank: `EvalSpec.bank = Path("evals/introspection/items_v2.json")`, resolved by
`registry.bank_path` (infra §2.12); header `version: 2`; `items.json` untouched (D9). The
module-level `BANK` constant at `judge.py:33` becomes a lazy `registry.bank_path("introspection")`
call (infra §2.12.3 owns that edit).

### 1. "Make paired controls that render the twin "not a hit" if they don't pass, e.g. random vector injected shouldn't contain the target we are looking for (by regex possibly??)"

Reading (Q12, binding): an inject item is a hit only if its MATCHED RANDOM-VECTOR (gaussian)
control does not also contain the target. The target is matched as the target concept plus its
equivalents (change 2), so the twin uses the same accept set as the scorer.

**Twins.** Bank v2 stores them explicitly per inject item (concept c, prompt kind k, beta b):
`item["twins"] = {"gaussian": id, "cross": id, "beta0": unit_id}`.
- `gaussian`: `gaussian|<k>:<key>|b<b>|c`. Protocol uses the same prompt. Neutral uses the
  concept's one rotated gaussian prompt. **This is the paired control of the headline.**
- `cross`: `cross|<k>:<key>|b<b>|c` (the cross partner's inject readout, judged with c's
  options). Reported column only.
- `beta0`: `beta0|<same prompt>|b0||<c's cluster>` (unsteered, same prompt). Reported column
  only, as a prior rate (`extras.beta0_prior_rate`): it does NOT void the item. Reason: it is one
  shared readout per cluster, so voiding on it makes whole clusters unwinnable for a lens with a
  prior (critique 24). Q12 names only the random-vector control. The site lists this under
  "Decisions taken (override if you disagree)".

All twins are EXISTING plan rows (gaussian and beta0 rows are already in the 1,762-row plan;
cross has no rows of its own). **The pairing adds zero plan rows and zero GPU cells**
(this answers gpu §3.3's "paired controls TBD": introspection stays 1,762 rows). The gaussian
twin's steering recipe is the bank's existing per-item `vector.seed`, and from v2 also the
shipped `gaussian_vectors_L12.npy` row (change 3).

**A twin hit** fires if EITHER leg fires. Both legs are reported separately.
- **Judge leg:** the twin unit's own judged pick is in A(c) (change 2). Native: any judged cell.
  Summary: its one call. A `cannot tell` or `no injected concept` pick is not a twin hit.
- **Regex leg** (deterministic, no LLM; `judge.twin_regex(forms, cells) -> str | None`, returning
  the first matching sample text or None). It is a thin loop over samples calling the shared
  `mc.form_in(sample, forms)` (infra §2.7.6: folded match, Unicode word boundaries for Latin,
  listed CJK forms as exact substrings). The family adds no regex or folding of its own; it only
  curates the form list:
  - **Cells:** the twin's cells exactly as `reads.load` returned them for this run, then
    `reads.select`. That means the same `layers=`, the same `reads=` site set and the same
    sampling normalisation (`readouts.normalize`, D7). It reads raw `Cell.samples`, never the
    digest. This is the "same window" restriction of critique 24: the twin is read over the same
    layers and sites the inject item was read over, not over the whole file.
  - **Forms:** `concepts[].surface_forms` over every word in A(c) plus that concept's listed
    `extra_forms` (change 2). Each word gets English label + singular + plural, plus irregulars
    (oasis/oases, cactus/cacti). Case-folding and word boundaries are `mc.form_in`'s. Curated
    Chinese translations of >= 2 characters are listed as CJK forms (so `form_in` matches them
    as substrings). Single-character forms such as 金 and 雪 are NOT listed, because they
    produce too many incidental hits. Equivalents ARE included, per Q12 ("regex over the target
    + equivalents"); Q12 overrides critique 24's "gold forms only".
  - **Token cells:** each token, stripped, is matched as a whole. The regex leg never stitches
    tokens. A void needs the target named inside one token; this is conservative toward voiding.
    Within-list and adjacent-position reading (Q4) applies only to the judge.

**Per-row fields:**
- `pass_unpaired`: the old rule, with A(c).
- `twin_hits: {gaussian|cross|beta0: {judge: bool, regex: bool, regex_quote: str | None}}`.
- `pass = pass_unpaired and not (twin_hits.gaussian.judge or twin_hits.gaussian.regex)`.
- If the gaussian twin readout is missing, `pass` is `None`. The row is undecided, counted in
  `n_twin_missing`, and is never silently scored unpaired. A missing cross or beta0 twin makes
  only `paired_all_twins` undecided for that row.

**Headline:** the paired rate.
- `extras`: `headline_unpaired`, `paired_judge_only`, `paired_regex_only`, `paired_all_twins`
  (void on any of gaussian / cross / beta0, the round-0 rule), `beta0_prior_rate` (share of
  concepts whose beta0 twin names A(c)), and `n_twin_missing`.
- The existing population floors stay reported, computed with the same A(c).
- Native runs also report `mcjudge.layer_pick_columns(rows)` (critique 18; infra §2.13).
- This applies to every inject sub-headline (protocol / neutral × beta 4 / 2).

**Scope.** `opts=scope=headline` (`judge.py:173-182`) now includes the headline's twins:
- units: 125 gaussian, 125 cross and 25 beta0 trial1;
- readouts: +125 gaussian rows and +1 beta0 row;
- summary mode: +126 digests.

`scope=headline` keeps `complete=false` (a subset by scope, not by `layers=`; infra §2.1 makes
`mcjudge.is_subset` stop treating `layers=` as a subset). The paired headline is still valid.

**Files:**
- `src/wsbench/evals/introspection/judge.py`: new `twin_regex`, `pair(rows)` after `_row`,
  `_scoped`, `summarize`.
- `evals/introspection/items_v2.json`: `twins`, `surface_forms`.
- README.

**Tests** (new, `tests/test_introspection.py`):
- `test_paired_gaussian_judge_hit_voids_inject_hit`.
- `test_paired_gaussian_regex_hit_voids_inject_hit`. Toy readouts: gaussian twin text "a brass
  trumpet" voids the trumpets item. "trumpeter" does not match because of the letter boundary, so
  it does not void.
- `test_regex_leg_includes_equivalents_and_extra_forms`: a gaussian twin "a pile of devices"
  voids the gadgets item, and "backpacks" voids the bags item.
- `test_beta0_and_cross_twins_do_not_void_headline`: they set `paired_all_twins` and
  `beta0_prior_rate` only.
- `test_regex_forms_irregular_and_zh`: oases/oasis, cacti/cactus, 2-character zh forms match,
  1-character zh forms are ignored.
- `test_regex_leg_reads_selected_cells_only`: under `reads=lite` and `layers=[44]`, a twin hit at
  another site or layer does not void.
- `test_missing_twin_is_undecided`.
- `test_scope_headline_includes_twins`.
- In `tests/test_summary_mode_introspection_kc.py`: `test_introspection_paired_rule_in_summary_mode`
  (the twin regex reads raw cells, not the digest).

### 2. "Concept clusters contain near-duplicates (machines/gadgets/robots, bags/backpacks, trees/leaves/forests, youths/teenagers/children), which clashes with the rule that broader terms don't count and blurs the options." / "These terms should count"

Reading (Q12, binding): near-duplicates in a cluster count as the concept, through an explicit
equivalents table. When the judge picks a cluster-mate listed as an equivalent of the gold, the
item counts as a hit. The scorer implements this mechanically, so the judge is not loosened in
general.

**Bank v2 fields:**
- Top-level `equivalents: {concept: [cluster-mates that count]}`, giving
  A(c) = {c} ∪ equivalents[c].
- `concepts[].extra_forms`: non-option words that name the concept. Q12's "devices" (for gadgets
  and machines) and "robotics" (for robots).

**Scorer:** `_row` passes when any pick is in A(c). At `judge.py:501`, `v == target` becomes
`v in accept`. Floors (gaussian / cross / beta0 chance hits) and both twin legs use the SAME A(c)
and forms, so the comparison stays fair.

**Judge:**
- Every option that has `extra_forms` is rendered in the menu with them, for ALL options, so the
  gold is not leaked: `gadgets (also: devices)`, `robots (also: robotics)`.
- New rubric line: "An option's listed "also" words name that option."
- The hypernym exclusion now reads "hypernyms of an option that are neither options nor its
  listed "also" words".
- The judge still picks the option literally named. A readout saying "backpack" makes it pick
  `backpacks`, which then counts for the `bags` item.
- **Equivalence groups vs the shared flat-list rule (round 2, critique r1 item 4).** Under the
  r2 `mc.TOKEN_NOTE`, a line holding two or more options singles out none of them. Read
  literally, a J-lens line "trees | leaves | forest" for gold `trees` would then single out
  nothing, although Q12 says all three count as the concept. So the menu also marks equivalence
  relations, rendered the same way for EVERY option (no gold leak), each option listing its own
  `equivalents` row: `youths (same as: teenagers, children)`, `purses (same as: bags, wallets)`.
  The relation is symmetric but not transitive (bags~purses and purses~wallets do not make
  bags~wallets). One family rule line follows the rendered shared note `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`: "Options marked "same as" one
  another count as ONE option for the line rule above: a line whose options are all "same as"
  one another singles them out together; answer with any one of them." The scorer's A(c) then
  credits the pick. A line holding two options that are not "same as" each other still singles
  out neither (the shared rule, unchanged). This clause adds no shared machinery: it is family
  prompt text plus the bank `equivalents` table. The table has no one-directional rows.
- **Round 3: status against "add, never relax" (SHARED_API r3, infra §2.7.2).** The rendered
  shared note stays byte-exact: `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`
  with `()` / `False`, which equals `mc.TOKEN_NOTE`. The family line comes after it. The "same
  as" clause credits a line that the shared note alone would void. That makes it a relaxation,
  and Q12 sanctions it (decisions override infra). It is the only relaxation in this family, it
  is listed under "Decisions taken", and it is narrowed mechanically so it cannot leak to a
  third concept:
  - **Group check (scorer, deterministic).** `judge.quote_options(quote, units) -> set[str]` is
    the set of options whose label or listed "also" / surface forms `mc.form_in`-match the
    verified quote. A pick counts for item c only if `pick in A(c)` and
    `quote_options(quote) ⊆ A(c)`.
  - Example: "trees | leaves" passes the `trees` item ({trees, leaves} ⊆ A(trees)). It does NOT
    pass the `branches` item, even though trees ~ branches, because leaves ∉ A(branches).
  - A lone option, where the quote names only that option, passes exactly as under the shared
    rule.
  - The judge SYSTEM asks: "for a 'same as' group, quote the whole line".
  - Test: `test_same_as_group_credits_only_within_accept_set` (the two examples above, plus a
    lone-option quote that is unaffected).

**Table**, frozen in bank v2. Cliques are marked `{}`; pairs are symmetric; there are no
one-directional rows (the "same as" menu render needs symmetry):
- From Q12, Camila's groups:
  - {machines, gadgets, contraptions};
  - robots <-> machines;
  - extra_forms gadgets: devices, machines: devices, robots: robotics;
  - bags <-> backpacks;
  - {trees, leaves, forests};
  - {youths, teenagers, children}.
- Spec-proposed (Q12's "..."): bags <-> purses, bags <-> suitcases, purses <-> wallets,
  trees <-> branches, trees <-> roots, elders <-> grandparents, snow <-> blizzards,
  poetry <-> sonnets, novels <-> stories, sadness <-> grief, empires <-> kingdoms,
  emperors <-> pharaohs, ash <-> soot, deserts <-> dunes.
- Every other concept: A(c) = {c}.

The site lists the spec-proposed rows as "Decisions taken (override if you disagree)".

README: a new "Near-duplicate options" paragraph lists the table and the "also" forms. It states
that the hypernym exclusion applies only to words that are neither options nor listed forms.

**Offline effect** (source verdicts, protocol beta4, unpaired, native; `/tmp/intro_an/gonly2.py`):
- O-lens inject 0.856 -> 0.888 (new passes: pharaohs, youths, branches, contraptions).
- O-lens gaussian floor 0.200 -> 0.256; cross floor 0.216 -> 0.272.
- J-lens 0.376 -> 0.416 (blizzards, dunes, grief, leaves, novels); floors unchanged at
  0.000 / 0.016.
- The "devices" / "robotics" forms change judge picks only in the LLM phase. The source verdicts
  predate them.

**Files:** `judge.py` (`units` carries `accept` and `forms`; `_row`), `prompts.py` (option render,
rubric line), `items_v2.json`, README.

**Tests:**
- `test_accept_set_counts_near_duplicates`: gold teenagers, pick youths -> pass; pick children ->
  pass; pick elders -> fail.
- `test_accept_set_applies_to_floors_and_twins`.
- `test_bank_v2_equivalents_are_cluster_mates`: every equivalent is in the same cluster; no
  self-loops; Q12's groups are cliques.
- `test_extra_forms_rendered_for_every_option`: the menu shows "also" and "same as" words for
  all options, the gold is not singled out, and
  `test_every_summary_family_has_task_note_without_gold` still passes.
- `test_equivalence_group_on_one_line_is_singled_out` (scripted judge): "trees | leaves |
  forest" for gold `trees` -> pick in A(trees) -> pass; "leaves | roots" for gold `leaves`
  (leaves and roots are not "same as" each other) -> singles out neither -> not a pass.
- `test_lone_option_in_same_category_list_is_singled_out` (family copy of infra's shared test,
  critique r1 4c): "violin | cello | trumpet | flute" where only `trumpets` is an option -> pick
  `trumpets`.

### 3. "Include the vectors in the public repo"

This is the one producer of the vectors (critique 31). gpu.md G8 dropped its GPU recomputation, so
the vectors come from here and need no GPU.

- **Concept vectors:** new file `evals/introspection/vectors/concept_vectors_L12.npy`.
  - float32, shape (125, 5120), rows in `items_v2.json` `concepts[]` order.
  - RAW (un-normalised) vectors exactly as produced; the injection normalises them.
  - Source of truth: `/workspace/gw-introspection-inject/outputs/introspection_inject/vectors.json`
    (sha256 `d663b8ca9713b70eae20d9240e75a420a419e20dbee582706ad3bf99cd02a47a`).
  - The conversion is lossless: the JSON floats are the float32 values from `tensor.tolist()`.
- **Gaussian vectors:** new file `evals/introspection/vectors/gaussian_vectors_L12.npy`.
  - float32, shape (500, 5120), rows in bank order of the gaussian items.
  - Generated on CPU with the bank's recipe (`torch.Generator().manual_seed(seed);
    torch.randn(5120)`).
  - Shipping them removes the dependency on torch CPU RNG stability across releases.
  - Generation script: `scripts/introspection_export_vectors.py` (CPU only).
- **Bank and plan fields:** no separate vectors README; the family README (§"The steer")
  documents them. `items_v2.json` gains
  `vectors: {concept: {path, sha256, dtype, shape, order: "concepts"}, gaussian: {...}}`.
  `readplan._introspection` steering gains `vector_file` and `vector_row`
  (`readplan.py:709-712`). These are full-plan fields, so they change `bank_sha`; the family
  re-gates anyway (C10).
- **Licence:** NOTICE.md adds that the vectors are activations of Qwen3.6-27B (model-card
  licence), released under the repo's terms.
- **Producers (round 2, critique r1 item 8 / gpu G14):**
  - s3d-rl600: gpu.md G8a's steered producer (`STEERED_FAMILIES |= {"introspection"}`), which
    reads `vector_file` / `vector_row`.
  - **J-lens arm (required by G14 for every `FAMILIES_BP` family):** `wsbench produce method=jlens`
    today refuses steered rows (`producer.py:111-122`), so G14's J-lens fan-out would exit on
    introspection. This PR therefore builds the steered path in `wsbench produce` (no longer
    optional): `Producer.read_spec` applies `extra.steering` with a forward hook at
    `inject_layer` over the steered span, `h <- h + beta*||h||*v_hat`, with `v` loaded from
    `vector_file[vector_row]` (gaussian rows from `gaussian_vectors_L12.npy`; `beta0` rows
    unsteered). It is the bank recipe, not a new shared helper. The refusal stays for any
    steering `type` other than the bank's. Tests (CPU, tiny model fixture):
    `test_produce_applies_steering_hook` (the hooked residual at `inject_layer` equals
    `h + beta*||h||*v_hat` on the steered span and is unchanged elsewhere) and
    `test_produce_refuses_unknown_steering_type`.
  - **ML-NLA arm (round 3, critique r2 item 11; resolved by gpu G14 "Steered rows in the ML-NLA
    job builder").** gpu's `scripts/plan_to_xreader_jobs.py` maps each row's `extra.steering`
    to xreader's per-job `steer` record:
    `{layer: inject_layer, beta, positions: <steered span>, vector: {type: "concept", word:
    <concept key> | "gauss:<vector_row>"}}`. It writes `--vectors-json` from the shipped `.npy`
    files, sha256-checked against the bank `vectors` block. `beta0` rows get `steer: null`. An
    unmappable row exits 2, so no row is ever read unsteered. Test (gpu-owned):
    `tests/test_plan_to_xreader_jobs.py::test_jobs_carry_steering`.
    - **This spec's contract with that builder.** Every steered introspection plan row keeps
      today's `extra.steering` fields (`readplan.py:691-702`): `type` (`concept` | `gaussian`),
      `beta`, `inject_layer` (12), `token_span` ([start, end], absolute and inclusive; protocol
      97-116), `formula`, and `concept` (concept rows) or `seed` (gaussian rows). It gains
      `vector_file` (`evals/introspection/vectors/{concept,gaussian}_vectors_L12.npy`) and
      `vector_row`.
    - The xreader concept key is `steering.concept`, which must equal
      `concepts[vector_row].word`. Gaussian rows use `gauss:<vector_row>`.
    - beta0 rows keep `{type: "none", beta: 0.0}`, with no file and no row. The builder maps
      them to `steer: null`.
    - These are the same fields the steered `wsbench produce` path above reads, so the J-lens
      and ML-NLA arms steer from one definition.
    - Family test: `test_plan_rows_steering_block_complete`. It checks that:
      - every concept and gaussian row has all of the fields above;
      - `vector_row` is in range for its file;
      - `steering.concept == concepts[vector_row].word`;
      - beta0 rows are `type: "none"` with no file.

      This is the input `test_jobs_carry_steering` relies on.
    - The fallback label "cached v1 readouts, judge test only" (123 of 125 headline inject rows,
      no twins) is used only if the R2b ML-NLA job exits 2. It is never presented as a campaign
      number.
  - The README gains "produce with `wsbench produce`, or your own steered forward" and points at
    the shipped vectors.

**Tests:**
- `test_shipped_vectors_match_bank_fingerprints` (numpy only). For each row,
  `sha256(json.dumps([round(x, 3) for x in row.tolist()]))[:16] == concepts[i]["vector_fingerprint"]`
  and `abs(norm - vector_norm_L12) < 1e-3`. Verified 125/125 from the JSON source.
- `test_vector_files_sha256_match_bank`.
- `test_gaussian_vectors_unit_norm_after_normalisation`; under the `gpu` extra only,
  `test_gaussian_vectors_match_seed_recipe`.
- `test_plan_rows` gains the `vector_file` / `vector_row` assertions.

### 4. "Fix the leniency in the judge"

Rubric edits to `SYSTEM`. `SYSTEM_SUMMARY` is derived from it by `.replace`, so a test asserts
the replace still fires.
- Add after the NOT-named list: "A label inside a proper name, title, brand, product, acronym, code,
  ID or citation does not name the concept unless the sample is about the thing itself. "Zepplin v.
  OpenAI" (a case name), "Icy Veins" (a title), "SKIN-KL-24" (a code), "PRISM" (an acronym) and the
  *Dune* novels do not name dirigibles / veins / skin / prisms / dunes; "Mount Vesuvius erupting"
  names volcanoes."
- Add: "A different word with related meaning does not count, unless it is an option's listed
  "also" word: "deception" is not lies, "anxiety" is not fear, "blood vessels" is not blood, and
  "Monolithic" (a style) is not monoliths. A word buried inside another word ("Kotcontraption")
  does not count."
- Add the cannot-tell rule (C4), so that unclear evidence has a non-hit outlet.
- Keep "If several options are named, choose the one named most often / most prominently", but
  restated (round 2) so it never overrides the shared one-line rule: "Count only samples that
  single out an option (by the token-line rule above); if several options are singled out by
  different samples, choose the one singled out most often / most prominently." A token line
  holding two non-"same as" options therefore contributes to neither. Test:
  `test_tie_rule_counts_only_singling_samples` (prompt text contains the restated clause).
- The quote gate stays the mechanical backstop. It is now `digest.quote_ok` (C6).
- Add a cheap audit counter for the website, not used for scoring:
  `extras.audit.quote_in_name_or_code` (a quote token adjacent to a capitalised multi-word name, a
  digit or a hyphen-code).

The round-0 open decision ("devices" / "robotics" do NOT count) is withdrawn. Q12 makes them count,
only as listed `extra_forms` (change 2). Every other related word stays excluded.

**Files:** `src/wsbench/evals/introspection/prompts.py` (SYSTEM, PROMPT_VERSION), README §Judge
prompts.

**Tests:**
- `test_rubric_excludes_names_codes_and_related_words` (the prompt text contains the clauses).
- `test_summary_system_replace_still_fires` (`SYSTEM_SUMMARY != SYSTEM`, and it contains
  `SUMMARY_INPUT`).

Behavioural proof is the re-judge in §5 (LLM, later phase).

### Campaign decisions applied to this family

- **C1 (D1, summary default; ALL readouts).**
  - Summary is already the default.
  - `FAMILY_DEFAULTS["introspection"] = {"summ_fallback": "default"}`. `summ_fallback` is an
    allowed key. It is needed because 8-11% of introspection digests are refused and today become
    undecided. `summ_variant` is not set: `digest.DEFAULT_VARIANT = "task"` is global.
  - No family token cap: the global `digest.DEFAULT_TOKEN_CAP` with `hierarchical` overflow, so
    no readout is dropped (`extras.n_readouts_in == n_readouts_bundled`).
  - Task notes: `EvalSpec.task_note` holds the family-level note.
    `EvalSpec.item_task_notes` returns a Mapping from every item and twin id to its prompt-kind
    note (C5). `_run_summary` makes ONE `digest.collapse(..., task_note=<that Mapping>,
    expect_all=<all cells>)` call. The round-0 "collapse once per prompt kind" is dropped.
  - Unsummarised units after fallback are reported in `extras.summary.n_units_unsummarized` and
    listed on the site. They stay undecided, which is not a lens failure.
  - `extras.digest_served_by` shows the fallback-served share.
- **C2 (D2, lite).**
  - Source: the bank v2 render field `renders.*.lite`. Protocol `[140]` (the final token, the
    open quote). Neutral `[grid[1]]` (the `\n` after `<|im_end|>`), stored as absolute positions
    per render.
  - `readplan._introspection` copies it into `ReadSpec.lite_positions = {"kind": "positions",
    "positions": [...]}`, with `lite_layers = None`. Every row gets it, including the gaussian
    and beta0 twins, each from its own render. So under `reads=lite` a twin is read at its own
    lite site.
  - The judge loads only through `reads.load` and `reads.select`. No family filtering of
    `pos_map`, and no family flag (the round-0 `extra.lite_positions` is retired).
  - Full-mode completeness: `EvalSpec.min_full_positions = 9` (the neutral grid; protocol has
    24) and `EvalSpec.full_contiguous = False` (explicit-position rule), via `reads.check_full`.
    The `prompt_only:` reader waiver is inherited.
  - **Round 3 (critique r2 item 13): the site is not chosen by pass rate.** Introspection is
    not in infra's lite-site procedure. Its lite site is infra's fixed table entry (infra
    §2.6), frozen into bank v2 before any campaign readout exists. The pass-rate numbers below
    are reported as expectation only and are never used to re-choose.
    - Protocol `[140]` is the final token, the plain "final position" default.
    - Neutral `[grid[1]]` departs from `final_token`. The round-1 motivation was the cached
      J-lens hit rate, which is exactly the bias item 13 names. So a support check (no judge
      outcome) is reported beside it:
      - `scripts/introspection_offline_evidence.py --lite-support` computes, for the neutral
        prompts, the share of gold-bearing `[support]` digest lines (`mc.form_in` over A(c)
        forms) at the final token vs at grid[1];
      - inputs are the gpu R4 `reads=full` all-layer digests, pooled over s3d-rl600, jlens and
        mlnla-rl2-2000, as in infra's procedure step 1;
      - rule: if grid[1]'s pooled share does not beat the final token's by more than 10 points,
        the neutral lite rule becomes `final_token`. That is an infra table edit. `lite_*` is
        outside `plan_sha` and `bank_sha`, so there is no re-read and no ATI change.
    - Offline expectation (source verdicts, beta4, share of items hit at that position over
      all 11 layers):
      - protocol pos 140: O-lens 0.56 (the best single position is 138 at 0.624); J-lens 0.28
        (the best; all-grid 0.376);
      - neutral final token vs grid[1]: J-lens 0.028 vs 0.31; O-lens 0.688 vs 0.79.
    - Test: `test_lite_support_table_uses_no_verdicts`. The function's inputs are digests and
      forms only, and it raises if handed a judged rows file.
  - Tests: the shared `test_every_plan_row_has_lite_positions`,
    `test_every_lite_rule_is_cell_resolvable` and `test_lite_is_subset_of_full`. Family:
    `test_lite_selects_bank_positions_for_units_and_twins` (via `reads.select`).
- **C3 (D3, layers).**
  - `judge.py:201` uses `rep.layers`, not `GRID` (infra §2.1.4 owns that edit).
    `layers=all|each|<csv>` work through the shared CLI.
  - Shared tests: `test_layers_arbitrary` and `test_layers_variant_is_complete`.
  - Family test: `test_single_layer_digest_tag` (the `layers=[44]` digest key carries `|44`,
    `digest.py:1043`).
- **C4 (D4, cannot tell).**
  - Options are built as `mc.options_with_cannot(<the v1 seeded 6 options>)`. `mc.CANNOT` is the
    7th option, AFTER "no injected concept". It is never shuffled in (infra §2.4.2 overrides
    round 0's reshuffle). The 6 substantive options keep their v1 order.
  - Rule line, infra's text: 'Choose "cannot tell from the readout" when the samples neither name
    a concept option nor clearly report that no concept was injected.'
  - Scoring: on inject items CANNOT is a non-hit. On controls it counts with "no injected concept"
    as a non-false-positive. On twins it is not a twin hit. `false_alarm` excludes it.
    `extras.audit.cannot_tell` counts it.
  - Blindness is unchanged: the judge never sees the prompt, dose or gold.
  - Tests: the shared `test_every_mc_judge_ends_with_cannot`; family
    `test_cannot_tell_is_no_hit_and_not_a_false_alarm`.
- **C5 (D5, no tool names).**
  - `SYSTEM` opens: "You are judging {mc.READOUT_PHRASE} in an interpretability benchmark. One
    internal activation was turned into text…". "lens" appears nowhere.
  - Token note (native and summary judge prompts): `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`, rendered from the registered spec, never a bare `mc.TOKEN_NOTE` literal; the family `NOTE_TOKENS` is deleted. `SUMMARY_INPUT` uses
    "the readouts".
  - Task notes (`item_task_notes`, C1):
    - protocol: "the model was asked whether it detects an injected thought and what it is about;
      a concept may appear in only one or a few readouts";
    - neutral: "the model was given an ordinary short request; its activations may have been
      steered toward a concept, which may appear in only one or a few readouts".
  - Neither note names an option or the gold. Controls and twins get the same note as their
    prompt kind, so floors and pairs stay matched.
  - Test: the shared `tests/test_prompt_tool_names.py::test_no_tool_names_in_prompts` and
    `test_every_summary_family_has_task_note_without_gold`. The round-0 family
    `test_prompts_name_no_tool` is not created (folded, critique 33).
- **C6 (D6 / Q4, token lenses).**
  - The rubric's "fragments of different tokens never combine" is replaced by the shared Q4 rule,
    `mc.TOKEN_NOTE` verbatim (no family wording): tokens of ONE list may be read together; tokens
    of adjacent positions at the same layer combine only to spell one word; nothing else
    combines. Flat lists follow the r2 options-relative rule (infra §2.7.2): a line holding two
    or more of the options shown singles out none of them, an option alone on its line is
    singled out even among other same-kind words, no rank-1 exception. Introspection declares
    `EvalSpec.flat_types = ()` (its options are mixed nouns, not a competitor type), so the
    rendered note is `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` with
    `flat_types=()` and `multi_select=False` (round 3, critique r2 item 3: every judge prompt
    renders it from the spec; the text is byte-identical to `mc.TOKEN_NOTE`). Held by the shared
    `test_token_note_rendered_from_spec` and the family `test_spec_token_note_fields`
    (`SPEC.flat_types == ()`, `SPEC.multi_select is False`). The family's only addition is the
    "same as" group clause (§2.2), which follows the shared note and is narrowed by the
    `quote_options` group check.
  - **Bullet boundaries (round 3, critique r2 item 12).** An s3d `prose1` generation reaches
    the judge as one `digest.Line` `- a ⁞ b ⁞ c` (`digest.BULLET_MARK`). Introspection is
    non-relational, so a concept named in any bullet counts. It verifies with
    `quote_ok(quote, lines)` only, where `fold_quote` maps `⁞` to a space. There is no
    `statement_lines` check and no `extras.n_unverified_bullet`. The regex twin leg reads raw
    `Cell.samples` and so never sees the mark. Test: `test_quote_across_bullet_mark_verifies`
    (a quote spanning `⁞` in a summary-mode evidence line -> ok).
  - **Number flood (critique r2 item 4):** not used. The options are nouns, and flat lists are
    held by the options-relative note.
  - The summarizer side is infra's recording rule (`DIGEST_SYSTEM` records a same-type list as a
    list, never drops or picks), so a single mention of the concept in a list reaches the judge.
    Named restatements are kept by the shared rule (infra §2.8.2, critique r1 item 5); no
    family key. The neutral/protocol prompts never name a concept, so this changes nothing
    concept-bearing here.
  - Relational content: none. Introspection's unit is one concept, so no
    `digest.statement_lines` condition (SHARED_API sample licence, non-relational).
  - Quote verification: `quote_verified` becomes a thin wrapper that calls
    `digest.quote_ok(quote, lines)`, with `lines = digest.native_lines(cells)` (native) or
    `col.evidence[item_id]` (summary). Same-list token quotes are joined by `" | "`. A word split
    across adjacent positions is quoted as the plain word.
  - Not created: `digest.gate_groups` and the `"+"` joiner (both retired).
  - **Pre-existing test** `tests/test_introspection.py:120`: the assertion VALUE is retained
    (`"drums"` from the one list `["drum", "s"]` is still rejected, because a same-list quote must
    be `"drum | s"`). Only its call form changes, to the `quote_ok` signature. New assertions:
    `"drum | s"` on that list -> ok; a `" | "` quote spanning two lists -> rejected; `"trumpets"`
    spelled by `" trump"` at pos p and `"ets"` at pos p+1 of one layer -> ok.
- **C7 (D7 / Q1, sampling).**
  - No family code. The sidecar declares `sampling`, and `reads.load` → `readouts.normalize`
    applies it.
  - The campaign arm `s3d-rl600` is `prose1`: its one multi-bullet generation is ONE sample.
    The cached s3d file holds 3 generations per cell, trimmed to the first and counted in
    `n_samples_trimmed`.
  - `*-x4` arms are `bullet4` (4 separate samples). Token lenses are `tokens10`.
  - The regex twin leg reads `Cell.samples` after `reads.load`, so it sees exactly the judged
    samples.
  - Test: `test_regex_leg_uses_loaded_samples_only` (a hit in the trimmed 2nd s3d generation does
    not void).
- **C8 (D8, prompt-only): protocol `po-opus-v1` (infra §2.11), no family variant. One read per
  plan row id, never per read position.**
  - One Opus 5.5 readout per plan row id. Twins (gaussian, beta0) are their own ids, with
    independent draws seeded by id, even though they share the visible text.
  - Each readout is rendered through the row's last full-read site and written as one prose cell
    at that pos, at `PROMPT_ONLY_LAYER = 44`.
  - Built by `wsbench baseline kind=prompt_only_opus stage=build|ask|readouts out=<dir>`. Judged
    by `wsbench run all=True readouts_root=<dir>/readouts`, with no `layers=` and no `reads=`.
    The `prompt_only:` reader waives `check_full` / `select`.
  - Floor = the family's own headline metric from its own `run` on that file: the paired
    gaussian rule, A(c), the quote gate, all as for a lens; family CI; n = judged − refused;
    more than 20% refused -> `not_measurable`. Unpaired is reported beside it.
  - Frozen into `evals/baselines/prompt_only_summary.json`, matched on
    `reads.strip_reads(prompt_version)`, summarizer key and judge model via
    `summary_floor_applies` (`layers_judged` not compared: one floor for all configs + lite).
  - Timing (round 3, critique r2 item 6): measured at gpu R6, after R4c closes. If R4c bumps
    `PROMPT_VERSION` after R6, introspection shows no floor (site: pending) until R6 re-runs for
    it. gpu G9 `audit_run.py` asserts `strip_reads(pv)` == the floor's `instrument`.
  - Calls: all 1,762 plan row ids (cross reuses the partner's readout).
  - Expected: unpaired near the source's 0.190 text-only rate, paired lower (the inject and twin
    draws are i.i.d.), which is the point of the pairing.
- **C9 (D9).** See the bank paragraph above and §3.
- **C10 (D10, ATI).**
  - Camila did not remove introspection from ATI.
  - Bank v2 and the new full-plan steering fields change `bank_sha` and the instrument. The lite
    fields do not (`text_inversion._row_dict` pops `lite_positions`, `lite_layers`, `reads`,
    `layers`, `note`). The guard therefore refuses until re-gated.
  - gpu G13 row: **re-judge only** (the visible item text is byte-identical; only the judge
    menu/rubric and keying change). `stage=readouts` from the stored panel answers ->
    `scripts/ati_panel_judge.sh` (native, as today) -> `wsbench text-inversion stage=gate
    families=introspection`. No new Qwen/panel answers. Expected 125/125 again.
  - Timing: at gpu R8, after R4c, on the final `PROMPT_VERSION` (G9 asserts native PV == ATI
    instrument). This matches `scripts/ati_regate_table.py`'s r3 rule: `prompt_sha` of the
    visible text is unchanged and `bank_sha` changed, so the entry is re-judge only.
  - Fix `evals/baselines/README.md`'s stale "123/125 headline items kept".

---

## 3. Data needs

- **Bank.** `evals/introspection/items_v2.json` = `items.json` plus:
  - per item: `twins`;
  - 7-option lists (`mc.options_with_cannot`, CANNOT last);
  - `options_by_cluster` likewise;
  - `concepts[].surface_forms` and `concepts[].extra_forms`;
  - top-level `equivalents`;
  - `renders.*.lite` (absolute positions);
  - the `vectors` block.

  Header: `family: "introspection"`, `frozen: 2026-11-xx`, `version: 2`. Drop the stale
  `spec.read_layers/primary_layer` header or mark it `legacy`. Built by
  `scripts/introspection_build_v2.py` from v1 (deterministic; no model). Registered as
  `EvalSpec.bank = Path("evals/introspection/items_v2.json")`, through infra's `registry.bank_path`.
- **New items:** none. **Qwen gating:** not needed (no new prompts, no new concepts, visible text
  unchanged).
- **Vector files:** two `.npy` files (2.56 MB + 10.24 MB), from the existing JSON plus a CPU torch
  run (no GPU; critique 31).
- **Macro (critique r2 item 1):** `metric="pass_rate"` (the paired headline), which is in
  `results.MACRO_METRICS`; `not_in_macro=""`. Introspection stays in the macro.
- **Readouts (GPU, run phase, gpu.md):**
  - **Campaign arm s3d-rl600:** all 1,762 rows (inject, gaussian twins, beta0; cross reuses the
    partner), at all 11 GRID layers and every full grid position. They are produced by gpu.md
    G8a's steered producer with a `prose1` sidecar.
  - **Required arms (gpu G14):** `jlens` (`tokens10`, via the steered `wsbench produce` path in
    §2.3) and `mlnla-rl2-2000` (`prose1`, needs the steering-carrying xreader jobs, §2.3), all
    1,762 rows, all-layer config, full + lite, each with a declared sidecar.
  - **Cached files** (`/workspace/root/wsb-ati-runs/readouts/{s3d,jlens}/introspection_inject.jsonl`,
    1,762 rows each) have no sidecar. They serve the offline evidence and development only
    (`sampling_source=default`; not a campaign result, infra §3). Sidecar-less, so `check_full`
    and the plan-layer guard run report-only (`config.reads_checked = "no_sidecar"`,
    `extras.partial_ids_unenforced`).
  - **Other arms** (any `*-x4` arm, tuned/logit lens): "cached v1 readouts, judge test only"; this
    spec funds no production for them.
  - Lite reads a subset of the same rows, so it needs no separate generation.

---

## 4. Answers

**Where are the injection vectors?** Not in either git repo. The concept vectors of record are
`/workspace/gw-introspection-inject/outputs/introspection_inject/vectors.json` (written by source
`scripts/oracle_lens_evals/introspection/ii_modal.py --mode vectors`, function `vectors()`; `outputs/` is
gitignored). It holds 125 raw L12 vectors (5120 floats each, norms 1.47-2.50), plus norms, fingerprints,
the 125x125 cosine matrix and the Phase-1 reproduction. I recomputed the fingerprint recipe
(`sha256(json.dumps([round(x,3) for x in v]))[:16]`) for all 125 and **125/125 match the wsbench bank's
`vector_fingerprint`**. The 500 gaussian vectors were never stored; they are regenerated from per-item
seeds (`items.json` `vector.seed`) with CPU `torch.randn`.

**How big?** Concept vectors: 125 x 5120 x 4 B = 2,560,000 B (2.44 MiB) as float32 `.npy` (1.22 MiB at
fp16, not recommended: the fingerprints round at 1e-3 and would no longer be checkable losslessly); the
JSON is 14.5 MB. Gaussian vectors if shipped: 500 x 5120 x 4 B = 10.24 MB. Together ~12.8 MB vs the
current `evals/` total of 29 MB.

**Can they be public?** Yes. They are activation differences of the public Qwen3.6-27B weights,
produced by a published recipe from a public word list (Agam's / the paper's), for benign concrete nouns;
anyone with the weights can recompute them, and they reveal nothing the bank does not already show (each
item id names its gold concept). Licence: NOTICE.md already defers to the Qwen3.6-27B model-card licence
for model-derived data; the implementer must confirm on the model card (not cached locally) that
redistribution of derived artefacts is permitted (Qwen 3.x open-weight releases are Apache-2.0) and
add the vectors line to NOTICE.md. Recommended: ship them (change 3).

**Do paired controls change the headline? (implicit in change 1)** Yes, substantially for the O-lens.
Offline on the source verdicts (protocol beta4, native, all layers, accept sets A(c) incl. the Q12
cliques and "also" forms in the regex leg; `/tmp/intro_an/gonly2.py`, to be ported, §5):

| reader | unpaired (A(c)) | paired gaussian, judge leg only | paired gaussian, regex leg only | **headline: paired gaussian, both legs** | `paired_all_twins` (round-0 rule) | `beta0_prior_rate` |
|---|---|---|---|---|---|---|
| O-lens s3d.rl600 | 0.888 | 0.640 | 0.704 | **0.640** | 0.544 | 0.304 |
| J-lens | 0.416 | 0.416 | 0.416 | **0.416** | 0.408 | 0.000 |

(Unpaired without A(c), i.e. today: O-lens 0.856, J-lens 0.376.) The gaussian twin voids 31 O-lens
passes (illusions, planets, oceans, waterfalls, coins, peace, joy, fear, grief, memories, secrecy,
dreams, lies, information, computers, databases, youths, children, teenagers, trees, forests, leaves,
branches, roots, contraptions, gadgets, machines, robots, novels, stories, songs): the O-lens names
these concepts under a random-vector injection of the same norm. Its unsteered (beta0) readouts name
30% of the concepts — its prior guesses — reported as `beta0_prior_rate` rather than voiding (§2.1).
The J-lens is untouched by the gaussian pairing. This is the strongest finding of the workstream: the
current headline is inflated by lens priors that the population floor (0.216) only offsets on average.

---

## 5. Evidence plan (website)

1. **Paired controls (offline, no calls):** port `/tmp/intro_an/{an,rx,acc,gonly2}.py` into
   `scripts/introspection_offline_evidence.py` and publish the table above plus a per-item void list
   (item, which twin, judge pick or regex quote). Concrete before/after: `inject|protocol:trial1|b4|information`
   O-lens before PASS, after FAIL (its gaussian twin names "information");
   `inject|protocol:trial1|b4|trumpets` before PASS, after PASS (no twin names trumpets). After the
   run phase, the same table from the new summary-mode run (default) and native, s3d-rl600.
2. **Near-duplicates count (offline):** O-lens `inject|protocol:trial1|b4|youths`, `...|pharaohs`,
   `...|branches`, `...|contraptions` before FAIL, after PASS (unpaired); J-lens `...|blizzards`,
   `...|dunes`, `...|grief`, `...|leaves`, `...|novels` before FAIL, after PASS; floors before/after
   (O-lens gaussian 0.200 -> 0.256, cross 0.216 -> 0.272). Run phase: count of picks credited via
   "devices"/"robotics" "also" forms, with 5 examples.
3. **Vectors public:** site shows the two file paths, sha256, shapes, and the CI line
   `test_shipped_vectors_match_bank_fingerprints PASSED (125/125)`.
4. **Leniency (run phase, re-judge the exact cached cells with the v2 prompt):**
   s3d `dirigibles` L32 p126 ("Zepplin"), ML-NLA `veins` L56 p117 ("Icy Veins"), ML-NLA `skin` L56 p117
   ("SKIN-KL-24"), J-lens `fear` L60 p121 ("Anxiety"), s3d `memories` L20 p128 (picked lies on
   "deception"), s3d `dunes` L48 p124 ("Dune" universe), and the audit's `contraptions`
   ("Kotcontraption"), `monoliths` ("Monolithic"), `prisms` ("PRISM") cells: before = concept pick
   (unit PASS on a single hit cell for dirigibles/veins/skin/fear), after = none or cannot tell (unit
   FAIL unless another cell hits). Plus the s3d `phones` L48 p132 "iPhone" cell as a must-still-pass
   control. These verbatim cases feed the shared audit below rather than a second protocol.
4b. **Leniency audit (shared R4b / gpu G12, critique r1 item 7, r2 items 6 and 14).**
   - `scripts/audit_verdicts.py sample --per-family 30 --strata introspection=kind` draws the
     introspection verdicts from the all-layer summary-mode run. They are stratified pass/fail
     × s3d-rl600 prose / J-lens tokens / ML-NLA prose.
   - The stratum adds ≥ 10 verdicts per row `kind` present (inject, gaussian, cross, beta0).
     Each result row already carries `kind` (`judge.py:478`), so the sample is
     `max(30, 10 × 4) = 40`. This checks that the twin and control verdicts are not lenient
     either (a twin judged as naming the concept voids a pass).
   - The cases from item 4 above are seeded into the sample.
   - A fresh-context auditor gets:
     - the five feedback sentences;
     - the pass rule: A(c), the paired gaussian void, the quote gate, the one-line rule, and
       the "same as" group check;
     - per verdict, the item, the digest lines or raw readouts, the answer and the quote.

     It labels each verdict `ok | too_lenient | too_strict | ambiguous`.
   - Site row: introspection × {n, n_too_lenient, n_too_strict, n_ambiguous}, with every
     non-ok case verbatim.
   - `n_too_lenient + n_too_strict >= 3` flags the family. The fix runs through **gpu R4c**,
     never by silent re-tuning:
     - a fix PR with a new `PROMPT_VERSION`;
     - R2/R2b only if `plan_sha` changed (a rubric-only fix does not change it);
     - R4 re-run for introspection over all configs, arms and lite, plus the opusjudge column;
     - R4b re-seeded;
     - at most 2 rounds, all before R6/R8 and the site build.

     Any case still flagged goes to the site's "New errors found".
   - This replaces round 1's family-local "20 passes / 20 fails" audit.
5. **Cannot tell:** count and 5 examples of `cannot tell from the readout` picks in the v2 run.
6. **Lite:** the C2 support-share table (final token vs grid[1], per arm and pooled; the rule
   outcome), the per-position hit table (C2, expectation only), and the `reads=lite` vs `reads=full` headline for
   s3d-rl600, J-lens and ML-NLA (G14 arms; until produced, J-lens from the cached file labelled
   `sampling_source=default`).
6b. **Per-arm paired table (G14):** unpaired / paired-judge / paired-regex / paired headline /
   `beta0_prior_rate` for s3d-rl600, J-lens, ML-NLA on the v2 run, beside the offline table of §4.
7. **Prompt-only (D8, `po-opus-v1`):** Opus prompt-only paired and unpaired rate next to every lens
   row, from `prompt_only_summary.json`.
8. **No tool names:** shared `test_no_tool_names_in_prompts` green with introspection's PROMPTS and
   task notes collected.
9. **Decisions taken (override if you disagree)** (site section 4, one line each, spec
   `introspection`):
   - only the random-vector (gaussian) twin voids a hit; the beta0 and cross twins are reported
     columns (`beta0_prior_rate`, `paired_all_twins`);
   - the regex leg matches the target plus its equivalents and "also" forms (Q12), never
     stitches tokens, and skips 1-character Chinese forms;
   - the spec-proposed equivalents rows beyond Q12's groups (§2.2 table);
   - "same as" groups on one line are singled out together. This is the one Q12-sanctioned
     relaxation of the shared flat-list note, narrowed by the `quote_options ⊆ A(c)` check;
   - CANNOT is placed 7th, after "no injected concept", and is never shuffled;
   - the lite site is protocol final token and neutral grid[1], unless the support check (C2)
     reverts neutral to `final_token`;
   - the vectors ship as float32 `.npy` (gaussians included), not fp16.

---

## 6. Risks / conflicts

- **Headline drop / macro shift:** O-lens headline falls from 0.856 to ~0.64 (paired gaussian);
  introspection is in the macro, so every macro number moves. Must be communicated, not tuned away.
- **Regex leg is strict by design and widened by Q12:** one incidental mention of the target or an
  equivalent/"also" word ("devices" is common) in the gaussian twin's read cells × samples voids the
  item. Bounded by reading only the run's selected cells (same layers, same sites) and by excluding
  beta0/cross from the void; shown with the judge-only and regex-only columns.
- **Source parity lost:** the README's claim that prompts are byte-identical to the source judge cache
  (README:143-148) ends with the v2 prompt; `test_introspection_native_prompt_is_unchanged`
  (`tests/test_summary_mode_introspection_kc.py:167`) and `test_user_prompt_matches_the_source_rendering`
  (`tests/test_introspection.py:123`) are re-pinned to the v2 text (sanctioned here: the rendered
  prompt text is what changed — options gain "also" forms and CANNOT, rubric lines added). The C6
  line `tests/test_introspection.py:120` keeps its assertion value (False); only the call form
  changes. `test_bank_counts_and_renders` and `test_plan_rows` gain assertions only. No other
  pre-existing introspection assertion may change.
- **Equivalents table is a judgment call** beyond Q12's listed groups; listed on the site; it raises
  floors more than the O-lens headline.
- **Token combining (Q4) vs leniency:** the judge follows the spec-rendered `mc.token_note(...)`; the regex leg never stitches.
- **ATI re-gate required** (bank_sha + instrument change) before any `anti_text_inversion=True` run.
- **Cost:** native full scope stays ~409k calls (× 7/6 longer prompts); summary scope=headline now 251
  digests + 400 judge calls (was 125 + 125). Prompt-only: 1,762 Opus calls.

Shared files this workstream touches (all through infra's API; no shared helper is added here):
- `src/wsbench/digest.py`: only `FAMILY_DEFAULTS["introspection"] = {"summ_fallback": "default"}`
  (no `gate_groups`, no notes — shared notes are infra's)
- `src/wsbench/registry.py`: introspection `EvalSpec(bank=..., task_note=..., item_task_notes=...,
  min_full_positions=9, full_contiguous=False, flat_types=(), multi_select=False, not_in_macro="")`
  (metric `pass_rate`)
- `src/wsbench/readplan.py` (`_introspection`: `lite_positions` from bank renders, `vector_file`,
  `vector_row`)
- `src/wsbench/produce/producer.py` (the steered path, required for the G14 J-lens arm)
- `evals/baselines/anti_text_inversion.json` (re-gate via the tool) and `evals/baselines/README.md`
  (stale 123/125 text)
- `NOTICE.md`, top-level `README.md` (family table / macro), `docs/summary_mode_validation.md`
- `tests/test_summary_mode_introspection_kc.py` (shared with knowledge_cutoff)
- global-workspace (gpu.md G8a, not this PR): `STEERED_FAMILIES |= {"introspection"}`, reading
  `vector_file`/`vector_row`.

---

## 7. Coverage map (round 3, critique r2 item 5: rows for `site/manifest.json`)

`sentence_id = <section>:<line in notes/feedback.md>`. Status follows gpu G11. A row is
`done` only when its tests are green at the footer SHA and its artefact exists. Otherwise it
is `pending`, or `measured` for a measurement.

| sentence_id | sentence (short) | change | tests | evidence (§5) | status kind |
|---|---|---|---|---|---|
| Introspection:210 | paired controls void the twin ("by regex possibly") | §2.1 gaussian judge + regex legs, `pass` paired | `test_paired_gaussian_judge_hit_voids_inject_hit`, `test_paired_gaussian_regex_hit_voids_inject_hit`, `test_regex_leg_includes_equivalents_and_extra_forms`, `test_beta0_and_cross_twins_do_not_void_headline`, `test_regex_forms_irregular_and_zh`, `test_regex_leg_reads_selected_cells_only`, `test_regex_leg_uses_loaded_samples_only`, `test_missing_twin_is_undecided`, `test_scope_headline_includes_twins`, `test_introspection_paired_rule_in_summary_mode` | 1, 6b | done + measured |
| Introspection:211 | near-duplicates clash with "broader terms don't count" | §2.2 A(c), "also" forms, narrowed hypernym rule, "same as" menu + group check | `test_accept_set_counts_near_duplicates`, `test_accept_set_applies_to_floors_and_twins`, `test_bank_v2_equivalents_are_cluster_mates`, `test_equivalence_group_on_one_line_is_singled_out`, `test_same_as_group_credits_only_within_accept_set`, `test_lone_option_in_same_category_list_is_singled_out` | 2 | done + measured |
| Introspection:212 | "these terms should count" | §2.2 Q12 cliques + `extra_forms` (devices, robotics) | same as :211 plus `test_regex_leg_includes_equivalents_and_extra_forms` | 2 | done |
| Introspection:213 | include the vectors | §2.3 two `.npy` files, bank `vectors` block, steered produce + G14 ML-NLA mapping | `test_shipped_vectors_match_bank_fingerprints`, `test_vector_files_sha256_match_bank`, `test_gaussian_vectors_unit_norm_after_normalisation`, `test_plan_rows_steering_block_complete`, `test_produce_applies_steering_hook`, `test_produce_refuses_unknown_steering_type`, gpu `test_jobs_carry_steering` | 3 | done |
| Introspection:214 | fix the leniency in the judge | §2.4 rubric (names/codes, related words, buried words), CANNOT outlet, restated tie rule | `test_rubric_excludes_names_codes_and_related_words`, `test_summary_system_replace_still_fires`, `test_tie_rule_counts_only_singling_samples`, `test_cannot_tell_is_no_hit_and_not_a_false_alarm` | 4, 4b, 5 | measured (audit) |
| ALL/GENERAL:10, :21 | Opus prompt-only, same judge | C8 `po-opus-v1`, paired floor | infra prompt-only tests | 7 | measured |
| ALL/GENERAL:11 | arbitrary layers | C3 | `test_layers_arbitrary`, `test_layers_variant_is_complete`, `test_single_layer_digest_tag` | 6 | done |
| ALL/GENERAL:12, :15, :18 | summarizer gets ALL readouts; summary default | C1 one collapse per readout, global cap + hierarchical | `test_single_global_token_cap`, `test_every_summary_family_has_task_note_without_gold` | 1, 6b | done |
| ALL/GENERAL:14 | "cannot tell" in every MC | C4 | `test_every_mc_judge_ends_with_cannot`, `test_cannot_tell_is_no_hit_and_not_a_false_alarm` | 5 | done |
| ALL/GENERAL:17 | token lenses combine top-10 | C6 spec-rendered `mc.token_note` | `test_token_note_rendered_from_spec`, `test_spec_token_note_fields`, C6 quote assertions in `tests/test_introspection.py` | 4b | done |
| ALL/GENERAL:19, :20 | Opus summarizer + judge audit; all and single layers | §5 4b with `--strata introspection=kind` + R4c; 12 configs (gpu R4) | gpu `test_strata_minimum_per_kind` | 4b, 6b | measured |
| directed modulation:46 (general clause) | no tool names in prompts | C5 | `test_no_tool_names_in_prompts` | 8 | done |
| (lite, general) | lite reads | C2 bank positions + support check | `test_every_plan_row_has_lite_positions`, `test_lite_is_subset_of_full`, `test_lite_selects_bank_positions_for_units_and_twins`, `test_lite_support_table_uses_no_verdicts` | 6 | done + measured |
| (questions) | where / how big / public | §4 Answers (site section 2) | `test_shipped_vectors_match_bank_fingerprints` | 3 | done |

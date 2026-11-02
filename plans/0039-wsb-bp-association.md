# 0039 — WorkspaceBench fix campaign, association (bank v2, MC judge, summarize-suffix reads)

Status: implemented in this PR (`camila/wsb-bp-association`). Campaign source of truth:
`/workspace/root/wsb-bp/plans/{association,SHARED_API,gpu,_fable_decisions}.md`; this file copies
the association spec verbatim (below the line) plus what the implementation decided where the spec
left room, and the late critique fixes.

## Late critique fixes (binding, 2026-10-30)

1. `reads.plan_sha` does not hash `layers`: already in the infra PR (#140,
   `tests/test_reads.py::test_all_layer_producer_file_is_judged`); association relies on it.
2. gpu runbook R4d: `scripts/lite_site_table.py --family association` now reads the bank v2 gold
   forms (`mc.gold` + `mc.aliases`); `tests/test_association_v2.py::test_lite_site_table_uses_support_share`
   is its association case. Until R4d freezes `evals/association/lite_rule.json`, the lite rule is
   `final_token`; lite results stamp `config.lite_rule` (infra), checked by `scripts/audit_run.py`.
3. multilingual ATI exclusions: not this family.
4. basic_readout token-note exception: not this family (association renders `mc.token_note()` from
   its spec unchanged, `flat_types=()`, single answer).
5. Judge-spend estimate after the smoke: run phase.

## What was built (bank v2)

- `scripts/association_distractors.py` propose → lint + Opus entailment check → 5-draw scene screen
  → freeze. Full run 2026-10-30: 93 proposals, 93 entailment checks (42 candidates flagged as
  hyponym / hypernym / near-equivalent and never shown), 1 lint rejection, scene screen 465 draws in
  round 0 (only `child-h` lost draws, to `parent` 3/5; replaced, then 5/5), 0 items dropped.
- Agent review (all 93 lists): 37 items edited — 12 distractor replacements in 10 items (each item
  re-screened, gold 5/5), alias drops / adds in 28 items (over-broad forms such as `joe`, `tube`,
  `box`, `fire` for `fired`; practitioner nouns such as `auctioneer`, `golfer` added for every
  activity gold for consistency with the proposer's own `boxer`, `juggler`). Every edit and its
  reason: bank header `distractor_review_edits`; per-item screen record:
  `evals/association/distractor_screen_v2.json`. A human review by the bank owner is still open.

## Implementation decisions and deviations

- `basic/prompts.DIGEST_TASK_NOTES["association"]` is NOT deleted (spec §6 asks for it): the
  basic prompt sha is pinned at `bank-2026-10-30b` (`tests/test_basic_prompts.py`), so deleting the
  line would force a second basic PV bump and stale every basic family's floors / ATI entries. The
  line is unused by association (its `EvalSpec.task_note` is its own `DIGEST_TASK_NOTE`).
- `tests/test_basic_association.py` keeps testing the shared bank judge on the v1 bank through a
  test-only `bank_family("association", bank=items.json)` registration and a copy of the v1 toy
  (`tests/fixtures/association_v1_toy.jsonl`), instead of re-pointing every test to
  medical_diagnosis; every bank-judge assertion is unchanged.
- The ATI entry is stale (bank_sha + instrument) and `subset_entry` refuses it until gpu R8;
  `tests/test_refilled_banks.py` lists association in `REGATE_PENDING` and
  `tests/test_ati_fingerprint.py` in `CHANGED_BY_FAMILY_PRS`.
- The scene screen has no cannot-tell option (8 options, as the spec says); the lint's surface
  rule (iv) is "an acronym for an acronym, at most two words longer" (capitalisation is not
  linted: a common-noun gold's same-type siblings are often proper names, e.g. holidays for
  `birthday`); the measured lucky-guessing floor checks for a form leak.

---

# Spec: association (basic) — fix campaign workstream

Code of record: `/root/wsb-bp-base` @ `cd6b0fa` (origin/main). Every `file:line` below is from that
tree unless it names another path. Read-only scoping: no LLM call, no GPU run, no repo edit was made.
Cached evidence is quoted from runs on disk; their paths are given in full.

Round 1 (2026-10-30): aligned to `plans/SHARED_API.md` and `plans/_fable_decisions.md`; fixes
critique items 1, 4, 13, 18, 27, 34, 35 (see `plans/_resolution_log.md`). §1 describes the code of
record as it is today (its stamps are observed values, not targets).

Round 2 (2026-10-30): re-aligned to the round-2 `SHARED_API.md` (r2 flat-list rule relative to the
options shown, `mc.token_note(flat_types)`, the r2 sample licence, named restatements, prompt-only
floor rules, required J-lens / ML-NLA arms, R5 → R8 runbook order, R4b leniency audit); fixes
critique r1 items 4, 7, 8, 9, 12, 13 as they touch association (see `_resolution_log.md`,
"association.md (round 2)").

Round 3 (2026-10-30): re-aligned to the round-3 `SHARED_API.md`. Changes: `mc.token_note(SPEC.flat_types,
multi_select=SPEC.multi_select)` with `multi_select=False`; `digest.BULLET_MARK` bullet
boundaries (non-relational, so a quote across `⁞` still passes); the "add, never relax" rule
(SYSTEM's "carried by clearly more lines" clause no longer credits a line the shared note
voids; new mechanical token-line void); the lite site chosen by pooled `[support]` share, not by
pass rate (`scripts/lite_site_table.py`); R4c in the gate order; a §0 coverage map for the gpu
G11 site manifest. Fixes critique r2 items 3, 5, 6, 8, 9, 12, 13, 14b as they touch association
(see `_resolution_log.md`, "association.md (round 3)").

### 0. Coverage map (gpu G11 `site/manifest.json` rows; `sentence_id` = `<section>:<line>` of `notes/feedback.md`)

| sentence_id | Camila's sentence (abridged) | change | named test(s) | evidence (§5) |
|---|---|---|---|---|
| `association:24` | "some under determined items … making it into the ati subset, … get rid of them" | C1: bank v2 retires 7 ids (rules a/b/c), `bf-sherlock` gold → `Sherlock Holmes`; ATI re-gated at gpu R8 | `test_v2_retires_underdetermined_items`, `test_ati_entry_has_no_retired_ids`; shared `test_no_hardcoded_items_json` | C1 rows |
| `association:25` | "include the summary sentence … ALL token positions … fed to the summarizer" | C2: render `chat_summarize`, 19-position suffix span × `GRID`; `min_full_positions=19`, `full_contiguous=True`; `expect_all=cells` | `test_association_reads_summarize_suffix`, `test_summary_digest_gets_every_cell`, `test_full_read_needs_19_positions` | C2 row |
| `association:26` | "consider making this multiple choice … b3-as-birthday … distractor items" | C3: 8-way MC + cannot tell, 7 screened distractors, deterministic gate, token-line flat-list void | `test_v2_options_shape`, `test_distractor_pick_fails`, `test_holiday_flat_list_is_cannot_tell`, `test_token_line_with_two_options_voids_gold_pick`, `test_lone_option_in_same_type_list_is_singled_out` | C3 rows |
| `association:27` | "Summary mode drops rare single-cell hits … rejects a clear spelling variant (neighbour)" | C4: rare tier kept, task note, `mc.aliases` spelling variants, quote-miss retry | `test_spelling_variant_rule_present`, `test_task_note_reaches_digest`, `test_bad_quote_retried_once` | C4 rows |
| `association:28` | "make sure the prompt only baseline is subject to the same judge" | C5: shared `po-opus-v1`, same summarizer / MC / gate / pin | `test_prompt_only_rows_take_the_same_instrument` | C5 rows |
| `association:29` | "fast / lite mode … figure out where it is most commonly held, maybe the last token?" | C6: `reads=lite` = one site; `final_token` until the pooled support-share procedure runs | `test_association_lite_rule`, `test_lite_reads_one_site` | C6 row |
| `ALL/GENERAL:10,21` | prompt-only with Opus, same judge | C5 | as `association:28` | C5 rows |
| `ALL/GENERAL:11` | arbitrary layer combinations | C7 (infra §2.1, no family code) | `test_layers_arbitrary`, `test_layers_variant_is_complete` | C2 row |
| `ALL/GENERAL:12` | summarizer fed ALL readouts | C2 | `test_summary_digest_gets_every_cell` | C2 row |
| `ALL/GENERAL:14` | every MC has "cannot tell" | C3 | `test_build_options_seeded_cannot_last`, `test_every_mc_judge_ends_with_cannot` | C3 rows |
| `ALL/GENERAL:15,18` | summary mode default | C7 | `test_every_registered_family_is_summary_or_native_only` | C7 12-config row |
| `ALL/GENERAL:16` | native language beside English | C3 `mc.aliases` lists `zh` forms | `test_cjk_quote_needs_listed_form` | C3 gate row |
| `ALL/GENERAL:17` | token lenses may combine top-10 | Q4 via `mc.token_note` | `test_token_note_rendered_from_spec`, `test_lone_option_in_same_type_list_is_singled_out` | C3 rows |
| `ALL/GENERAL:19` | Opus summarizer + judge; audit neither too strict nor too lenient | C7: gpu R4 / R4b / R4c | gpu `test_strata_minimum_per_kind` | C7 audit row |
| `ALL/GENERAL:20` | oracle lens all 11 layers + each layer | C7: 12-config run | gpu `scripts/audit_run.py` | C7 12-config row |

`ALL/GENERAL:13` (J-lens summarizer step removed) is infra's; association calls no
interp-v1 step.

**Decisions taken by this spec (for site section 4).** (1) The MC judge has 8 options + cannot
tell, chance 1/8. (2) Retirement rules a/b/c (C1). (3) The only deterministic pass is a listed
form; descriptions pass only through the quote-only re-judge, counted separately. (4) A
token-line gold quote whose list also names another option is void (C3 step 2b), the mechanical
form of the shared flat-list rule. (5) The lite site is `final_token` unless the support-share
procedure moves it.

---

## 1. Current state

**Bank.** `evals/association/items.json`: 100 items, header `{family, gate, items, eval_render_note}`.
Each item has `name` (= id), `prompt` (one or two sentences that evoke a concept and never name it),
`intermediates` (the gold, one string; `bf-sherlock` has three: `["Sherlock", "Holmes", "detective"]`),
`source`, `consistency` (Qwen3.6-27B behavioral gate, ≥ 0.8 at T=0.7, asked `NAME_REFERENT`,
`src/wsbench/capable/questions.py:20-23`), `gate_variant: "referent"`, `eval_render: "plain"`,
`readout: {"kind": "final_prompt_token", "offsets": [-1]}`. Languages: English, plus `pt-carnaval`,
`de-konig`, `de-oktoberfest`, `es-siesta`, `it-mercato`. There are no MC options or distractors.

**Family wiring.** `src/wsbench/evals/association/__init__.py:6` registers
`bank_family("association", "Association")`, which is the shared single-token bank judge
(`src/wsbench/basic/family.py:31-53`). `src/wsbench/evals/association/prompts.py:9` re-exports the
shared `wsbench.basic.prompts`. Prompt version: `bank-2026-10-10` (`basic/prompts.py:11`). The group
is `basic` (`basic/family.py:27`).

**Read sites.** `readplan.py:308-326` puts `association` in the `_final_token_families` list, so
`readplan.py:239-263` gives render `plain` (no chat template) and rule `final_token`. That is **one
position**, the story's final punctuation (for example `pt-carnaval` pos 29 `"."`), at layers
`GRID = range(20, 61, 4)` (11 layers, `readplan.py:16`). There is no summarize suffix. There is no
lite or full distinction. The suffix machinery already exists for the sibling families:
`SUMMARIZE_SUFFIX` (`readplan.py:20`), render `chat_summarize` (`readplan.py:33-34`,
`produce/render.py:66-69`), rule `suffix_text_then_tail` (`readplan.py:153-160`). The sibling plan
branch (`readplan.py:468-483`) reads 19 positions at `SIX` layers (`readplan.py:17`).

**Layers.** The judge uses `args.layers`, or else every layer in the readouts file
(`basic/family.py:74-75`). Every expected (item, layer) cell must exist unless `allow_missing=True`
(`:77-79`). Arbitrary subsets already work (D3 is met at judge level). The plan hardcodes `GRID`.

**Native judge (opt-out, `opts=aggregate=native`).** One free-text yes/no call per (item, layer)
over every position at that layer (`basic/judge.py:104-132`, `basic/prompts.py:190-206`). System
prompt is `SYSTEM` (`basic/prompts.py:25-59`). It names tools ("for the J-lens the samples are
top-10 vocabulary tokens, for the oracle lens they are free-text generations", `:27-28`). The user
message gives `targets: [...]`, so the gold is disclosed to the judge, and the judge is blind to the
scene. The output is `{expressed, target, quote}`. A positive needs a verbatim quote that verifies
inside one sample (`basic/judge.py:53-70`). An item passes if any layer is expressed
(`basic/family.py:240-273`). This is **not MC**: there are no distractors and no "cannot tell".

**Summary mode (the default, `digest.py:244`).** `basic/family.py:150-237`. Every cell of an item,
across all layers and positions, goes to one digest call (`digest.collapse`, `:175-183`). Then one
bank-judge call is made per item under `SYSTEM_SUMMARY` (`basic/prompts.py:67-70`). The quote is
gated against the digest's evidence lines only (`basic/judge.py:105-106`, `digest.gate_texts`). The
digest is `digest-v3` with a rare tier (`digest.py:23`, `:29` `DEFAULT_MAX_RARE = 15`,
`DIGEST_SYSTEM :41-78`). The default variant is `blind` (`digest.py:34`). The family task note
`"the model reads a short scene that implies a concept the text never names"`
(`basic/prompts.py:73`) is sent only under `summ_variant=task` (`digest.py:986-995`). The stamp is
`bank-2026-10-10+digest-v3-blind-extractive+sj-v7` (`digest.py:410-412`).

**Floors.** No analytic chance (free text). The prompt-only floor is stock Qwen3.6-27B under the
template "Below is a prompt ... cut off at a specific token ... What would a language model be
thinking about on this token?" (`evals/baselines/prompt_only.json` `_source`). It was judged by the
same bank judge: native 0.32 (`prompt_only.json.association`, instrument `bank-2026-10-10`) and
summary 0.31 (`prompt_only_summary.json.association`, instrument
`bank-2026-10-10+digest-v3-blind-extractive+sj-v7`).

**ATI.** `evals/baselines/anti_text_inversion.json.association`: panel-v1 gate, instrument
`bank-2026-10-10`, `layers_judged [44]`, `bank_sha 2a88…`, 12 ids: `nasa, unesco, winter,
bf-christmas, bf-titanic, b3-as-troy, de-konig, cia, history-h, love-h, b3-as-birthday, divorce`.
That is under 20, so the subset is shown but left out of the ATI macro. The gate is a native
instrument: `draw_verdicts` refuses summary results (`baselines/text_inversion.py:519-534`). It
reads `rows[].pass` (`:570-574`). `subset_entry` fails on an instrument mismatch or a `bank_sha`
mismatch (`:1464-1475`). `bank_fingerprint` hashes the read-plan rows as well as the bank items
(`:1013-1040`), so changing the render alone forces a re-gate.

**Cached headlines (s3d-rl600 O-lens, Opus 5.5 judge).** Native 0.94
(`/workspace/root/wsb-summ-out/d3/d3b-s3d-all-native`). Summary digest-v2 0.90
(`…/d3/d3b-s3d-all-summary-v2`). Summary digest-v3 0.93
(`/workspace/root/wsb-summ4-out/d3b-s3d-all-summary-v3`). v3 with `summ_rare=0` gives 0.90. J-lens
native 0.44, logit 0.17, tuned 0.21 (`/workspace/root/ext/wsb-runs/macro/<lens>/association`).

---

## 2. Change list (one item per sentence of Camila's `association:` section)

**Shared machinery used, never re-implemented** (names exactly as in `plans/SHARED_API.md`; owner:
the infra PR, which lands first): `reads.load` (the only loader), `reads.select` /
`reads.check_full` / `reads.stamp`, `ReadSpec.lite_positions` / `lite_layers`,
`EvalSpec.bank` + `registry.bank_path`, `EvalSpec.task_note`, `EvalSpec.min_full_positions` /
`full_contiguous`, `digest.collapse(..., task_note=, expect_all=)`, `digest.quote_ok` /
`digest.native_lines`, `digest.prompt_version`, `mc.seeded_shuffle`, `mc.options_with_cannot`,
`mc.CANNOT`, `mc.form_in`, `mc.READOUT_PHRASE`,
`mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` (both defaults for
association, so the rendered text is byte-identical to `mc.TOKEN_NOTE` =
`digest.SUMMARY_NOTE_TOKENS`, but it is rendered from the spec, never as the bare constant),
`EvalSpec.flat_types`, `EvalSpec.multi_select` (False), `digest.BULLET_MARK` / `digest.fold_quote`
(inside `quote_ok`), `reads.strip_reads`, `mcjudge.base_config`, `mcjudge.layer_pick_columns`,
`baselines.prompt_only_opus` (protocol `po-opus-v1`), `scripts/lite_site_table.py` (C6),
`tests/conftest.py::write_sidecar` / `native_args` (fixtures). Existing
cd6b0fa helpers it calls unchanged (not new shared API): `mc.classify` (`mc.py:27`),
`digest.summary_note` (`digest.py:415`), `mcjudge.run_calls` (`mcjudge.py:26`). Association does
NOT use `basic/mcjudge_basic.py` (critique r1 13: `MC_FAMILIES = {"basic_readout", "multihop"}`);
it has its own judge module (C3).

Sampling (Q1/D7, SHARED_API "sample licence"): **s3d-rl600 is `prose1`** — one multi-bullet
generation per activation is ONE sample; `*-x4` arms are `bullet4` (one generation = one bullet =
one sample); token lenses `tokens10`. The kind comes from the readouts sidecar, never from bullet
shape. Association's unit of evidence is one concept, which is non-relational content, so under
`prose1` the concept may be named in any bullet; association therefore does NOT add the
`digest.statement_lines` condition (that is for the relational families listed in SHARED_API)
and does not report `extras.n_unverified_bullet` (a relational-family field). Association adds
no sampling logic.

Bullet boundaries (infra §2.7.10, `digest.BULLET_MARK = " ⁞ "`): an s3d sample with ≥ 2 bullets
reaches the summarizer and the judge as `- a ⁞ b ⁞ c`, one `Line`. `fold_quote` maps `⁞` to a
space, so a concept quote that happens to span two bullets still passes `quote_ok`; that is
correct here because a concept is non-relational. Test:
`test_association_v2.py::test_quote_across_bullet_mark_passes` (a 2-bullet s3d sample
`"- a family party\n- birthday candles"`, quote `"party birthday"`, gold pick → pass, and no
`statement_lines` call is made).

Flat lists (SHARED_API r2 flat-list rule): association sets `EvalSpec.flat_types = ()`. Every
item's option list already holds ≥ 4 same-type siblings of the gold (C3 rule (i)), so the shared
"a list holding two or more of the options singles out none of those options" judge clause covers the holiday /
sport / detective lists Camila named; there is no family-wide competitor type (each item's type
differs), so no `flat_types` run is declared.

### C1. "some under determined items, and these are making it into the ati subset, we should just get rid of them"

**Criterion (reproducible, recorded in the v2 bank header as `retired_rule`).** An item is
under-determined, and is retired, if any of these holds:
- (a) In panel-v1 `draw_pass`, every frontier model (opus, astra, argon) failed at least 2 of its 3
  draws. The text then does not lead a strong reader to the gold.
- (b) The gold is a broader term (hypernym) of the specific concept the scene evokes.
- (c) The scene fits a different, equally specific concept as well as the gold, by reviewer reading.

| id | rule | evidence (panel-v1 `draw_pass` opus/astra/argon; cached verdicts) |
|---|---|---|
| `nasa` | a | 0/3, 0/3, 0/3; Qwen 0/3. The scene is any rocket launch ("rocket-launch scene", gpt-6-astra draw0, `/workspace/root/ati-or/ati/gpt-6-astra/answers/draw0.jsonl`). |
| `cia` | a | 0/3, 0/3, 0/3. J-lens L40 bag ranks `FBI` above `CIA` (`/workspace/root/wsb-ati-runs/readouts/jlens/association.jsonl`). |
| `history-h` | a | 0/3, 0/3, 0/3. s3d native passes on generic "historical records" / "family's history" (`ext/wsb-runs/macro/s3d-rl600`). Prompt-only passes on "a forgotten history" (`wsb-summ5-out/po-summary`). |
| `love-h` | a | 0/3, 1/3, 1/3 (intimacy / familiarity / trust are equally good readings). |
| `death-h` | a | 1/3, 1/3, 1/3 (funeral / mourning; `grief` is another item's gold). Not in ATI today, but under-determined. |
| `game-h` | b | Gold "game", but the scene is a chess move. s3d passes on "chess" and "the game". It duplicates `chess` / `bf-chess`. |
| `de-konig` | c | astra 0/3, Qwen 0/3. König vs Kaiser / Fürst / Thronfolger. Named by the prior audit. |

Kept on purpose: `unesco` (frontier 3/3/3), `pentagon` (3/3/3), `space-h`, `time-h`. Their golds are
pinned by the text. Qwen failing alone is a legitimate ATI reason (`_source.rule`).

`bf-sherlock` is kept, but its gold option becomes `Sherlock Holmes`. The generic `detective`
target goes. It let "The detective" (s3d L20) and prompt-only "noir/detective" pass.

**Change.** Create a new bank file `evals/association/items_v2.json` (naming rule
`items_v<N>.json`, infra §2.12) with 93 items, header `version: 2`, `retired: {id: rule+evidence}`,
and `retired_rule`. `items.json` (v1) stays byte-identical. The family switches by setting
`EvalSpec.bank = Path("evals/association/items_v2.json")` in `evals/association/__init__.py`;
`registry.bank_path` honours it (infra §2.12), so `lucky_guessing`, `text_inversion` and
`capable/questions.py` read v2 with no family-local path. The ATI entry is re-gated through the
normal panel path at gpu runbook step **R8** (owner: gpu workstream, G13; native gate, as today;
`_fable_decisions.md` ATI). Association is a **new answers** row: the text the panel reads changes
(chat template + summarize suffix, C2), so Qwen, Opus, astra and argon each draw 3 new answers
(astra/argon on Modal only). It cannot be hand-edited: `bank_sha` and the instrument both change. Expected survivors: `unesco, winter,
bf-christmas, bf-titanic, b3-as-troy, b3-as-birthday, divorce` (7, still under 20, still out of the
ATI macro), subject to the re-gate.

**Tests.** `tests/test_association_v2.py::test_v2_retires_underdetermined_items` checks that the 7
ids are absent, n = 93, the `retired` header keys equal those ids, `registry.bank_path("association")`
ends in `items_v2.json`, and the sha256 of v1 `items.json` is unchanged.
`::test_ati_entry_has_no_retired_ids` checks that the re-gated association ids are disjoint from
`retired`. (Shared: `test_bank_versions.py::test_no_hardcoded_items_json`,
`::test_bank_file_naming_rule`.)

### C2. "include the summary sentence "Summarize the preceding story in one sentence." make sure that ALL token positions from the summary sentence are being read and fed to the summarizer, not just the final token position, just like the conjunctive and role bound association families"

**Change, `readplan.py`.**
- Remove `"association"` from the `_final_token_families` list at `:310-325`.
- Add a branch next to `:468-483`: `ReadSpec(family, it["id"], "chat_summarize", {"kind":
  "suffix_text_then_tail", "text": SUMMARIZE_SUFFIX.strip()}, GRID, text=it["prompt"],
  suffix=SUMMARIZE_SUFFIX, lite_positions=ASSOC_LITE, lite_layers=None, note="the 19 suffix +
  chat-tail tokens; story positions are never read")`. The positions rule and render are the
  conjunctive and role-bound ones exactly (`docs/read_sites.md` §Sites): 19 positions from `Sum`
  through the final `\n\n`.
- Layers are `readplan.GRID` (all 11), the grid of record for every family (infra §2.1.2; the
  siblings move from `SIX` to `GRID` too). `layers=all|<csv>` and `layers=each` come from infra
  §2.1 with no association code; `layers=44` gives the summarizer only L44 readouts.
- `ASSOC_LITE` is the shared lite rule (C6), `{"kind": "final_token"}` until the pre-registered
  procedure runs.

**Registry.** `EvalSpec.min_full_positions = 19`, `full_contiguous = True`: under `reads=full`,
`reads.check_full` requires each (item, layer) to hold the whole contiguous 19-position run ending
at the final token, else exit 2 (or `partial` under `allow_missing`). No family-local check.

**Summarizer input.** The judge loads with `reads.load(args, "association")` and passes every
loaded cell of the item (19 positions × every requested layer) to
`digest.collapse(..., task_note=SPEC.task_note, expect_all=cells)`, so a bundle that omits a loaded
cell raises. With 19 × 11 = 209 cells per item: s3d (`prose1`, one generation of ~4 bullets,
~300 chars per cell) is ~60k chars, about 15k tokens, far under the global
`digest.DEFAULT_TOKEN_CAP` (920k; overflow `hierarchical`, never drops a readout). Association sets
no token cap of its own and keeps the default `summ_rare` (C4).

**Docs.** `evals/association/README.md`: new render block, 19 sites, retire the stale
`eval_render_note` line. `docs/read_sites.md`: retitle to "association families (association,
conjunctive, role-bound)" and add association to the Sites table once measured (C6). Top-level
`README.md:116-119`: "at the summarize-request positions" instead of "at the final prompt token".

**Tests.** `tests/test_readplan.py::test_association_reads_summarize_suffix` checks render
`chat_summarize`, `suffix == SUMMARIZE_SUFFIX`, the rule, `layers == readplan.GRID`, and that
`resolve` on the existing toy token list (`tests/test_readplan.py:125-140`) gives the
suffix-and-tail indices (19). `tests/test_association_v2.py::test_summary_digest_gets_every_cell`
uses a fake digest client and checks that the digest bundle for one item holds all 19 × 11
`[L pos]` groups and `extras.n_readouts_in == extras.n_readouts_bundled`.
`::test_full_read_needs_19_positions`: a file with 18 positions at one layer exits 2 under
`reads=full` (through `reads.check_full`). Shared: `test_layers_arbitrary`,
`test_layers_variant_is_complete`, `test_no_family_calls_load_readouts_directly`.

### C3. "consider making this multiple choice so the judge isn't too lenient, e.g. in b3-as-birthday there are many holidays mentioned so we should make these distractor items"

**Decision: yes.** Association leaves the shared bank judge for its own MC judge.

**Bank v2 per-item field.** Example:
`"mc": {"gold": "birthday", "aliases": ["birthdays", "birthday party"], "category": "holiday /
celebration", "distractors": [7 strings]}`.
- **Seven distractors**, the same count for every item, so the chance floor is uniform: 1/8 forced
  guess.
- **Selection rules** (lint-enforced where mechanical):
  - (i) The same TYPE as the gold first: at least 4 same-type siblings where they exist (holidays for
    `birthday`; racket sports for `tennis`; fictional detectives for `Sherlock Holmes`; seasons and
    times of day for `winter`). The rest come from the nearest neighbouring type. Other bank golds of
    the same type are used first (Christmas, Halloween, Easter, Oktoberfest, carnaval for
    `b3-as-birthday`), because those are concepts a lens demonstrably confuses on this bank.
  - (ii) No synonym, alias, translation, spelling variant, hypernym or hyponym of the gold. Lint: no
    distractor contains the gold as a word or is contained in it (so `table tennis` is out for
    `tennis`), and `mc.form_in(distractor, [gold, *aliases])` is False for every distractor.
  - (iii) No distractor may be a defensible answer for the scene (the scene screen below).
  - (iv) Same surface form as the gold (proper name vs common noun, capitalisation, length class), so
    the options-only lucky guesser cannot spot the gold by form.
- `aliases` lists the gold's accepted alternate forms, and is the ONLY deterministic route to a
  pass (critique r1 12): inflections and plurals, spelling variants (`neighbour`, `neighbours`),
  established synonyms and aliases (`Sherlock` for `Sherlock Holmes`), and translations into the
  languages a reader plausibly emits: English, Chinese (Qwen's native language,
  `banks.native_langs` default `("en", "zh")`, CJK forms listed explicitly, e.g. `冬天` / `冬季` /
  `冬` for `winter`, `生日` for `birthday`), and for the 5 non-English scenes the scene language
  (`Karneval` / `carnaval` for `pt-carnaval`, `König` for `de-konig` if kept). Authored by the
  proposer in step 1 below from gold + category only, then human-reviewed (step 4). Aliases are
  shown to nobody; they serve lint (ii) and the deterministic gate below.
- **Example (`b3-as-birthday`).** `birthday` + `Christmas, Halloween, Thanksgiving, Easter, New
  Year's Eve, Hanukkah, wedding anniversary`. This is exactly what the cached J-lens bag shows: L40
  `['christmas','birthday','birthday','halloween','celebration','thanksgiving',…]`.
- **Example (`bf-sherlock`).** `Sherlock Holmes` + `Hercule Poirot, Miss Marple, Philip Marlowe, Sam
  Spade, Columbo, Inspector Maigret, Nancy Drew`.
- **How generated.** `scripts/association_distractors.py`:
  1. Propose candidates offline from gold + category (Opus 5.5 via ant CLI, fixed prompt shipped in
     the script). The proposer never sees the scene or any readout.
  2. Lint (ii) and (iv).
  3. **Scene screen** (an API gate at gpu runbook step **R5**, about 93 × 5 calls, run BEFORE
     the v2 bank is frozen and before any production, critique r1 9a): Opus 5.5 sees the scene
     and the 8 options, picks one, 5 draws. The gold must win 5/5. Any distractor that wins once
     is replaced and re-screened. Opus runs locally with the flock'd `ANTHROPIC_AUTH_TOKEN`
     (gpu R5 API gates); the request and kept-id files are built by this family's PR.
  4. A human review pass, recorded as the header `distractor_review`.
  5. Freeze `items_v2.json` in the association PR; only then does the bench SHA that production
     reads (gpu R1/R2) exist.

  Option lists must not depend on any lens's readouts, so the instrument is lens-neutral. The cached
  readouts are used only for the coverage report in §5.

**Judge (new `src/wsbench/evals/association/judge.py` + `prompts.py`).** Modelled on
`conjunctive_association/judge.py:48-56` and `:226-345`.
- `build_options(it) = mc.options_with_cannot(mc.seeded_shuffle(dedupe([gold, *distractors]),
  f"{ASSOC_SEED}:{id}"))`. The substantive options are shuffled first; `mc.CANNOT` is appended
  LAST and never shuffled in (infra §2.4).
- Schema `{"choice": int, "quote": str}` (name `readout_mc`).
- **Pass rule (deterministic gate, critique r1 12).** `lines = col.evidence[item_id]` in summary
  mode and `digest.native_lines(cells)` in native mode; `digest.quote_ok` is the ONE quote
  verifier (infra §2.7.4); association adds conditions, never a second verifier.
  1. `pick = mc.classify(choice, gold_pos, len(shown))`; not gold → fail (below).
  2. `digest.quote_ok(quote, lines)`; if False, the C4 retry runs once; if still False →
     `gold_unverified`, fail.
  2b. **Token-line flat list (family-added condition, "add, never relax", SHARED_API MC).** If
     `config.sampling == "tokens10"` and the readout line that holds the verified quote also
     `mc.form_in`-matches any OTHER substantive option shown (a distractor), the pick is void →
     `gold_flat_list`, fail, counted in `extras.n_flat_list_voided`. This is the mechanical form
     of the shared rule "a list holding two or more of the options singles out none of them";
     it applies to token lists only, because one prose sample may name a sibling while singling
     out the gold ("a birthday, not Christmas") and that case stays a judge decision. The
     holding lines are `[l for l in lines if digest.fold_quote(quote) in
     digest.fold_quote(l.text)]` (the fold `quote_ok` uses; `quote_ok` alone decides
     verification, step 2b only reads the matched lines); the pick is void only if EVERY holding
     line names another option, so a quote that also occurs in a clean list still passes.
  3. **Names the gold:** `mc.form_in(quote, [gold, *aliases])` → `pass`. This is the only
     deterministic pass; there is no "judge-accepted translation/description" escape.
  4. Otherwise, if the quote has no Latin letters → fail (`gold_unlisted_script`): a non-Latin
     quote passes only through a listed form in that script (infra §2.7.6).
  5. Otherwise (a Latin quote that names no listed form: a description, a narrower instance such
     as "a puppy", an unlisted synonym), one **quote-only re-judge** (the conjunctive C2.3
     pattern): the SAME SYSTEM, user message `"READOUT (one span quoted from the readouts):\n
     {quote}\n\nWhich concept do the readouts name?\n{listing}"` with the same option order
     (token quotes use the prefix `"READOUT (tokens quoted from one ranked list, ' | '
     separated):\n"`), schema name `quote_mc`. Gold again → `gold_description`, a pass,
     counted in `extras.n_description_credit`; anything else → `gold_desc_rejected`, fail. A
     failed re-judge call → `pick="api_fail"`, `failed_stage="quote_check"`, undecided.
  Each row carries `credit` ∈ {`listed_form` (step-3 pass), `description` (step-5 pass), `none`}
  for the gpu G12 audit stratum (C7). `extras` also gains `n_gold_raw` (gold picks before steps
  2-5) and `n_flat_list_voided` (step 2b), so the site shows how many
  passes the gate removed. Cost: ≤ one extra call per gold pick without a listed form.
- A distractor pick, cannot tell, or invalid is a fail. An api_fail or unsummarized item is
  undecided.
- New `PROMPT_VERSION = "assoc-mc-2026-10-30"`, with its own `JudgeConfig`. Association therefore
  stops sharing the basic bank PV (`bank-2026-10-30` after infra's bump). The summary stamp is whatever
  `digest.prompt_version(PROMPT_VERSION, args, "association")` returns (never written as a literal
  here or in code); `reads.stamp` adds `+reads-lite` for lite runs only. `mcjudge.base_config`
  stamps `reads`, `sampling`, `sampling_source`, `reader`, `layers_judged`.

**SYSTEM (summary mode).** Neutral per D5: it names no tool and uses `mc.READOUT_PHRASE`. The
combining rule is Q4's (infra §2.7): no rank-1 exception.

> You judge readouts of a language model's internal activations, recorded while the model read a
> passage you cannot see. You get a digest of those readouts across every read layer and token
> position (described in the note below) and ONE multiple-choice question: which listed concept do
> the readouts name? Pick an option only if one readout line states that concept itself: the word
> in any case, inflection or spelling variant ("neighbour" names "neighbors"), an established
> synonym or alias, a faithful translation into any language, a narrower instance that necessarily
> entails it ("a puppy" names "dog"), or a description that depicts the concept itself. Do NOT
> pick an option you can only infer from clues, scene details or evidence ("crayon drawings on the
> fridge" do not name "child"); a broader category, the general topic, a merely related idea, a
> different word that contains the option's letters, and word fragments name nothing. A
> single list or line that holds two or more of the listed options singles out none of those
> options, whatever their order; an option that is the only listed option on its line is singled
> out by that line, even if the line holds other words of the same kind. Pick an option only if
> at least one line singles it out. If lines single out two or more different options, pick one
> only if it is stated as what the passage is about, or is singled out by clearly more lines
> than any other; lines that single out nothing never count toward this. If no line singles out
> an option, or no option wins, choose "cannot tell from the readout". Do not use world
> knowledge or plausibility to fill gaps. Give a SHORT quote copied character for character from
> inside ONE readout line that singles out the option you picked.

(The flat-list sentence is the SHARED_API r2 rule, relative to the options shown; its token-line
form reaches the judge again through `mc.token_note(SPEC.flat_types,
multi_select=SPEC.multi_select)`. Round 3 ("add, never relax"): the round-2 clause "none is
singled out (stated as what the passage is about, or carried by clearly more lines)" could have
credited an option that appears only inside multi-option lists, which the shared note voids; the
tie-break now counts only lines that single an option out, and the quote must come from such a
line. The summarizer
is never told to drop a flat list: infra's `DIGEST_SYSTEM` records it as a list, so a lone
"birthday" inside a holiday list survives into the digest.)

The user message is `{note}\n\nREADOUTS:\n{digest}\n\nWhich concept do the readouts name?\n{listing}`.
`{note}` is `digest.summary_note(...)`, which for token sources renders
`mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` with `flat_types = ()`,
`multi_select = False` (association is single-answer; Q4 combining rule:
tokens of ONE list combine; adjacent positions of one layer only to spell one word; nothing else;
the r2 options-shown flat-list clause). Association adds no token rule of its own.

**Native (opt-out, and the ATI gate instrument).** The same SYSTEM with "a digest … position"
replaced by "the readouts at one layer, grouped by token position"; token sources get
`mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`. The pass rule (steps 1-5
above, incl. step 2b and the quote-only re-judge)
is identical. One MC call per (item, layer) over all positions at that layer, through the same
`build_options`. The item passes if any layer picks gold with a quote that passes the gate above
(today's any-layer rule; ATI pass rule unchanged, infra §2.13). Every native result carries
`mcjudge.layer_pick_columns(rows)` (`n_items_gold_any_layer`, `n_items_distractor_any_layer`,
`n_items_distractor_majority`) in `extras`, printed beside every native / ATI number (critique 18).
Rows carry `pass`, so the generic gate path (`text_inversion.py:570-574`) needs no adapter.

**Lucky guessing.** Add an `"association"` builder to `baselines/lucky_guessing.py` BUILDERS
(`:246-261`), returning `Item(id, [shown[:-1]], [gold_pos])` (the escape is dropped, as for every
family). Add a DESCRIPTIONS line: "which concept an unseen short scene evokes without naming it".
The analytic chance is 1/8 = 0.125. Report it as `chance` beside the headline.

**Tests** (`tests/test_association_v2.py`, all with a fake client):
- `test_v2_options_shape`: 8 distinct options, gold in, lint (ii)/(iv) holds via `mc.form_in`,
  `bf-sherlock` gold is `Sherlock Holmes`.
- `test_build_options_seeded_cannot_last`: the same order on rebuild, the last option is
  `mc.CANNOT`, and it is the output of `mc.options_with_cannot`.
- `test_gold_pick_with_verified_quote_passes`.
- `test_distractor_pick_fails`: the birthday digest names Christmas, the judge picks Christmas, the
  item fails.
- `test_holiday_flat_list_is_cannot_tell`: a token line "christmas | birthday | halloween |
  thanksgiving | easter" with gold `birthday` at rank 2 (Christmas, Halloween, Thanksgiving,
  Easter are all listed options); the rendered SYSTEM and token note carry the r2 "two or more of
  the listed options" sentence and no "ranked first" clause (golden), and a scripted cannot-tell
  answer is a fail.
- `test_lone_option_in_same_type_list_is_singled_out`: a token line "birthday | party | cake |
  celebration | candles" (gold `birthday`, no other option on the line) with a scripted gold
  pick and quote "birthday" passes (the critique r1 4c case for association).
- `test_token_line_with_two_options_voids_gold_pick` (r3): `sampling=tokens10`, the line
  "christmas | birthday | cake" (Christmas is a shown distractor), a scripted gold pick quoting
  "birthday" → `gold_flat_list`, fail, `extras.n_flat_list_voided == 1`; the same line under
  `sampling=prose1` is not voided by step 2b.
- `test_system_tie_break_counts_only_singling_lines` (r3, golden): SYSTEM contains "lines that
  single out nothing never count" and "singles out the option you picked", and no longer contains
  "carried by clearly more lines".
- `test_token_note_rendered_from_spec` (shared, parametrized) reaches association with
  `flat_types=()`, `multi_select=False`.
- `test_cannot_tell_fails`.
- `test_unverified_quote_fails` (a quote not inside one line under `digest.quote_ok`, after the
  retry: `gold_unverified`).
- `test_cjk_quote_needs_listed_form`: a non-Latin quote passes only if `mc.form_in` finds a listed
  alias; an unlisted CJK quote is `gold_unlisted_script` and makes no re-judge call.
- `test_listed_alias_passes_without_rejudge`: quote "neighbours" for gold `neighbors` passes at
  step 3 and makes no `quote_mc` call.
- `test_description_credit_needs_quote_only_rejudge`: a gold pick quoting "the day she was born,
  candles on a cake" (no listed form) makes exactly one `quote_mc` call; a scripted gold re-judge
  passes and `extras.n_description_credit == 1`; a scripted cannot-tell re-judge is
  `gold_desc_rejected`, a fail.
- `test_rejudge_api_fail_is_undecided`: a failed `quote_mc` call gives `pick="api_fail"`,
  `failed_stage="quote_check"`.
- `test_rows_carry_credit_field`: a step-3 pass row has `credit="listed_form"`, a step-5 pass
  `"description"`, every fail / cannot tell / undecided row `"none"`.
- `test_native_any_layer_mc` (also asserts the three `layer_pick_columns` keys in `extras`).
- `test_lucky_guessing_association_builder` (in `tests/test_lucky_guessing.py`).
- `test_ati_gate_reads_association_mc_rows` (in `tests/test_text_inversion.py`).
- Shared, reached through `registry.FAMILIES` / `lucky_guessing.BUILDERS`:
  `test_every_mc_judge_ends_with_cannot`, `test_no_tool_names_in_prompts` (replaces the round-0
  family test `test_prompts_name_no_tool`), `test_digest.py::test_no_rank1_exception_text`.

### C4. "Summary mode drops rare single-cell hits and occasionally rejects a clear spelling variant (neighbour)."

**Status of the four cached flips.** Native-pass items that went summary-fail under digest-v2 were
`neighbors, winter, history-h, divorce` (`d3b-s3d-all-summary-v2`). Under the current digest-v3
(rare tier) all four pass (`wsb-summ4-out/d3b-s3d-all-summary-v3`):
- `winter` passes via the single-cell `"冬风"`.
- `neighbors` passes via `"她 had watched the same neighbors enter and leave"`.

With the rare tier off (`…-v3rare0`), `winter` drops again. So the rare tier is the fix of record
for rare hits. It must stay on for association (`summ_rare` 15, the default; association sets no
`FAMILY_DEFAULTS`). One residual v3 flip remains: `b3-as-vaccination`. The judge said
`expressed: true` with the quote `"That child got the vaccination"`, which is in no evidence line,
so the gate voided it, while the digest held "She injected the vaccine…"
(`…-v3/association/cells.jsonl`, key `b3-as-vaccination|L-1`). (`history-h` is retired in C1; the
other three stay as evidence.)

**Changes.**
1. **Spelling variants.** The C3 SYSTEM states spelling variants explicitly ("neighbour" names
   "neighbors"), and `mc.aliases` lists them for the deterministic gate (`neighbours`,
   `neighbour` for `neighbors`). In the v2 cached case the judge returned `expressed: false` while
   naming the target and a quote. An MC `choice` removes that self-contradicting output shape.
2. **Rare mentions kept by the summarizer.** `EvalSpec.task_note` for association (D5; the
   summarizer receives it by default since `digest.DEFAULT_VARIANT = "task"`, infra §2.8):
   > the model read a short scene (sometimes not in English) that evokes one concept (an activity,
   > event, place, person, organisation, feeling or thing) without naming it, and was then asked to
   > summarize the story in one sentence; the concept may appear in only one or a few readouts

   It carries no gold. It replaces the association line of `basic/prompts.py:73`
   `DIGEST_TASK_NOTES` and lives in `evals/association/prompts.py` as `DIGEST_TASK_NOTE`, the
   value of `EvalSpec.task_note`. The shared TASK CONTEXT line (infra §2.8.2) already says to
   record single-sample mentions. Two r2 shared rules also protect rare hits, with no association
   code: a flat same-type list is recorded as a list, never dropped or narrowed (SHARED_API
   flat-list rule), and a restatement that names a specific term is recorded with that term as
   its key in items or rare (SHARED_API "restatements"), so a readout that restates the scene
   ("the neighbors she had watched") is not capped away.
3. **Quote-miss retry.** A gold or distractor pick whose quote fails `digest.quote_ok` (C3 pass
   rule step 2; the `form_in` / re-judge steps run after it, on the retried quote) is re-asked once
   in the same run, under key `<id>|L-1|retry1` with the line "Your quote was not found inside one
   readout line; copy it exactly from one line." It is a fail only if the retry also fails.
   Implemented in the family judge as a second `run_calls` pass (`mcjudge.py:26-103`), on top of
   `digest.quote_ok` (a family may add conditions, not replace the verifier). Cache-keyed, so it is
   reproducible.

**Tests.**
- `test_spelling_variant_rule_present` asserts `"neighbour"` appears in SYSTEM and that a
  `neighbours` quote passes the gate for gold `neighbors`.
- `test_task_note_reaches_digest` asserts that the digest system for association contains
  `SPEC.task_note` under the default variant. Shared:
  `test_every_summary_family_has_task_note_without_gold`.
- `test_bad_quote_retried_once`: the first answer has a bad quote and the second a good one, so the
  item passes and two calls are made. With two bad quotes the item fails.

### C5. "make sure the prompt only baseline is subject to the same judge (e.g. strict + multiple choice)"

**Change: the shared `po-opus-v1` protocol (infra §2.11), with no association-specific path.**
- Reader: Opus 5.5 via `wsbench baseline kind=prompt_only_opus stage=build|ask|readouts out=<dir>`
  (module `baselines/prompt_only_opus.py`). Input: the association render (story + summarize
  request + chat tail) decoded through its last full-read site, the final `\n\n`.
- Written as ONE cell per item id, ONE prose sample, at that site's `pos` and
  `layer = PROMPT_ONLY_LAYER = 44`, sidecar `reader: "prompt_only:claude-opus-5-5"`,
  `sampling: prose1`. (The round-0 "one row per requested layer" design is withdrawn: it fed the
  digest 11 copies of one answer.)
- Judged by `wsbench run all=True readouts_root=<dir>/readouts` with no `layers=` and no `reads=`.
  `reads.load` waives `select` / `check_full` for the `prompt_only:*` reader, so the one cell
  satisfies `min_full_positions = 19`. It gets the SAME summarizer and task note, the same MC
  options, cannot tell, quote gate, retry and judge pin as a lens row; `strip_reads` of its
  `config.prompt_version` equals the lens run's.
- Floor = association's own headline metric (summary MC pass rate, every C3 gate step incl. the
  quote-only re-judge) from its own `run` on that file, with the family CI; n = judged − refused;
  if > 20% of the 93 Opus reads refuse, the floor is `not_measurable` (SHARED_API prompt-only).
  Measured at gpu R6, after R4c closes; if an R4c fix bumps association's `PROMPT_VERSION`, the
  floor is measured on the final PV only (no floor is drawn until R6 re-runs).
  One read per plan row id, at the last full-read site only: never one read per read position.
- Floor: frozen into `evals/baselines/prompt_only_summary.json` (one file); drawn beside a lens
  row iff `summary_floor_applies(entry, config)` (matches `strip_reads(prompt_version)`, summarizer
  key, judge model), so it serves the all-layer, single-layer and lite rows. The stock-Qwen file is
  archived to `evals/baselines/archive/` by the infra freeze; the two old association entries
  (native 0.32, summary 0.31) are shown struck through as superseded, never drawn.

**Test.** `tests/test_association_v2.py::test_prompt_only_rows_take_the_same_instrument`: a
one-cell-per-id readouts file with sidecar reader `prompt_only:claude-opus-5-5` goes through
`run` with no `layers=`, is `complete=True`, and its `strip_reads(config.prompt_version)` and
SYSTEM fingerprint equal those of a 19 × 11 lens file. Shared:
`test_prompt_only_opus.py::test_one_cell_per_id_at_last_full_site`,
`::test_uses_same_judge_spec`.

### C6. "fast / lite mode: you don't need to read all positions of the summary sentence, but just figure out where it is most commonly held, maybe the last token?"

**Change.**
- `reads=lite` (infra §2.6) keeps one site per (item, layer) through `reads.select`, at every
  full layer (`lite_layers=None`). Until measured, `ASSOC_LITE = {"kind": "final_token"}`: the
  render's final token, the `\n\n` after `</think>`, as Camila suggests. Lite ⊆ full, so one GPU
  read serves both; lite runs are stamped `+reads-lite` by `reads.stamp`.
- **Site selection = infra §2.6's pre-registered procedure for the three summarize-suffix
  siblings** (the same for association, conjunctive and role_bound; round 3, critique r2 13:
  "most commonly held" is a SUPPORT criterion, so no judge outcome decides). Run by
  `scripts/lite_site_table.py` on the cached gpu R4 / R2b `reads=full` all-layer digests; no new
  LLM call, no GPU. Association adds no code to it.
  1. Support share per site: for each `offset_from_end` k of the 19-token span (constant span, so
     items pool), count the `[support]` digest lines whose evidence `mc.form_in`-matches a gold
     form of association (`[gold, *aliases]`) with `Line.pos` at k, **pooled over s3d-rl600,
     jlens and mlnla-rl2-2000**, all 93 items, all 11 layers; `share(k)` = those lines / all
     gold-bearing lines in the span.
  2. Candidates: `final_token` (k=1), the ≤ 3 k with the highest pooled share, and role_bound's
     `offset_from_end k=4`.
  3. The highest-share candidate replaces `final_token` only if its share exceeds
     `final_token`'s by more than 10 points absolute; otherwise `final_token` stays. Pass rates
     are never consulted.
  4. Reported, not used to choose: the per-arm share table (s3d / jlens / mlnla + pooled) and
     each candidate's `reads=lite` headline per arm (re-judges of the same full readouts).
  5. Freeze the chosen rule as `ASSOC_LITE` in `readplan.py` (not the bank; `plan_sha` and
     `bank_sha` exclude `lite_*`, so no re-read and no ATI change). It is frozen before R6 / R8,
     so the lite rows those steps stamp use the final rule.
- The per-site share table itself answers "where is it most commonly held" in finer grain (one
  column per arm), so no separate native per-site pass table is needed.

**Tests.**
- `tests/test_readplan.py::test_association_lite_rule`: every association plan row has
  `lite_positions == ASSOC_LITE` and `lite_layers is None`.
- `tests/test_association_v2.py::test_lite_reads_one_site`: a full 19 × 11 file judged with
  `reads=lite` sends the digest only the lite-site cells, at every requested layer, and the
  stamp ends in `+reads-lite`.
- `tests/test_association_v2.py::test_lite_site_table_uses_support_share` (fixture digests for
  2 items × 3 arms with scripted `[support]` lines; `lite_site_table.py`'s choice for association
  follows the pooled share and is unchanged when the fixture's judged pass rates are permuted;
  a 9-point share win keeps `final_token`, an 11-point win switches). Infra names no test for
  the script; if infra adds a shared one this becomes its association case.
- Shared: `test_every_plan_row_has_lite_positions`, `test_every_lite_rule_is_cell_resolvable`,
  `test_lite_is_subset_of_full`, `test_bank_sha_unchanged_for_untouched_families` (association is
  re-gated, so it is outside that test's set).

### C7. General items that land on association (Camila's ALL/GENERAL section)

| general sentence | association change | test |
|---|---|---|
| arbitrary combination of layers | none family-local: `readplan.plan(layers=…)`, CLI `layers=all\|each\|<csv>` (infra §2.1) | `test_layers_arbitrary`, `test_layers_variant_is_complete` |
| summarizer fed ALL readouts | C2 (`expect_all=cells`) | `test_summary_digest_gets_every_cell` |
| all MC has "cannot tell" | C3 (`mc.options_with_cannot`) | `test_build_options_seeded_cannot_last`, `test_every_mc_judge_ends_with_cannot` |
| summary mode default | association is a summary family; native only via `opts=aggregate=native` | `test_every_registered_family_is_summary_or_native_only` |
| single-token lenses may combine top-10 | shared Q4 note via `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`; no association rule forbids combining within one list (step 2b voids only a list that also names another option) | `test_holiday_flat_list_is_cannot_tell`, `test_lone_option_in_same_type_list_is_singled_out`, `test_token_note_rendered_from_spec` |
| native language beside English | Chinese forms listed in `mc.aliases` (C3), so a `zh` readout of the gold passes the deterministic gate | `test_cjk_quote_needs_listed_form` |
| prompt-only with Opus, same judge | C5 | `test_prompt_only_rows_take_the_same_instrument` |
| 12-config Opus run | runs s3d-rl600 (`prose1`), all 11 layers + each single layer (gpu.md G6/R4); Opus summarizer and judge (association is unpinned); required G14 arms J-lens (`tokens10`) and `mlnla-rl2-2000` (`prose1`) at the all-layer config, full + lite (gpu R2b) | gpu `scripts/audit_run.py` |
| audit neither too strict nor too lenient | gpu R4b / G12: `scripts/audit_verdicts.py sample` draws ≥ 30 stratified association verdicts (pass/fail × prose/token) from s3d, J-lens and ML-NLA all-layer runs; association asks for one declared stratum, `association=credit` (row field `credit` ∈ {`listed_form`, `description`, `none`}, written by C3: step-3 pass / step-5 pass / anything else), so ≥ 10 `description` rows (all, if fewer) are audited; a fresh-context auditor labels them; `table` gives `n_too_lenient` / `n_too_strict` / `n_ambiguous`; a flag (≥ 3) goes through gpu R4c | §5 row "C7 audit"; test `test_rows_carry_credit_field` |

---

## 3. Data needs

**Bank.** `evals/association/items_v2.json` (`version: 2`), selected by `EvalSpec.bank`.
- It retires the 7 C1 items and fixes the `bf-sherlock` gold, giving 93 items.
- It adds `mc` (gold + aliases + category + 7 distractors) per item.
- Header fields: `retired`, `retired_rule`, `distractor_rule`, `distractor_review`, and
  `render: chat_summarize` (replacing the stale `eval_render_note`). The lite rule lives in
  `readplan.py`, not the bank.
- `items.json` (v1) stays byte-identical.
- Instrument: the family `PROMPT_VERSION` becomes `assoc-mc-2026-10-30`; the summary stamp is
  `digest.prompt_version(...)`'s output.

**New items.** None. No Qwen gating is needed: the stories and golds are unchanged, so the existing
behavioral gate (`consistency` ≥ 0.8) still holds. Distractor screening is a frontier-model check
(Opus 5.5, 93 × 5 draws), not GPU.

**Readouts to regenerate (GPU on Modal, later phase; gpu workstream).** Every arm, because the old
readouts are the final token of a different render (plain, no chat template, no suffix), and the
new render changes every read position:
- render `chat_summarize`, 93 items × 19 sites × 11 layers = **19,437 cells per arm**, produced at
  `reads=full` (lite is a subset);
- arms produced (gpu §3.3 / G14, required): s3d-rl600 O-lens (`prose1`, one generation per
  activation, Q1; 12 configs), J-lens (`tokens10`) and `mlnla-rl2-2000` (`prose1`), the last two
  at the all-layer config, full + lite (gpu R2b). Each file's sidecar declares `sampling`;
  `scripts/audit_run.py` fails a run whose `sampling_source != declared`;
- every other arm (logit, tuned, other macro token arms, any `*-x4` arm, which would be `bullet4`)
  is **"cached v1 readouts, judge test only"**: its cached files sit at the old plain-render
  final token, are sidecar-less, and are judged only report-only (`reads_checked=no_sidecar`,
  `extras.partial_ids_unenforced`) in the C3 offline instrument comparison. They get no
  association headline under the new instrument until a spec funds their production;
- `wsbench plan family=association` is the producer contract. gpu.md §3.3's association row
  (100 items, 20,900 cells) is stale: it is 93 items / 19,437 cells (critique 13, for gpu R1's
  regenerated table).

Story positions are never read, so a producer that holds a bare-render capture still needs a fresh
capture: the chat template's `<|im_start|>user\n` prefix shifts every story KV too.

**Prompt-only.** `po-opus-v1`: 93 Opus 5.5 calls (one per id), shared infra.

**Gate order (gpu runbook, critique r1 9a).** R5 (the C3 scene screen, an Opus API gate; no Qwen
gate is needed) → freeze `items_v2.json` in the association PR → merge → R1 (plan check; R1's
regenerated cells table carries 93 / 19,437) → R2 / R2b production → R3 → R4 → R4b → R4c (only if association is flagged) → R6 → R8 → R7
(site). The lite rule (C6) is frozen from R4 digests before R6.

**ATI re-gate (gpu R8, owner gpu workstream G13).** New answers (G13 table row "association"; the
reason is the changed render, C2, plus the MC instrument): panel answers for the 93 items under
the new prefix (Qwen n = 3 via `scripts/ati_qwen_modal.py`, Opus n = 3 local, astra/argon n = 3
each via `scripts/ati_openrouter_modal.py` on Modal only). They are judged natively with the new
MC instrument at layer 44, the last site (`scripts/ati_panel_judge.sh`), then frozen with
`text-inversion stage=gate`. `bank_sha` and the instrument both change, so `subset_entry` refuses
the old entry until this runs (`text_inversion.py:1464-1475`).

**Lucky guessing.** The options-only guesser over the 93 option lists (5 draws), frozen in
`lucky_guessing.json`.

**Toy file.** `examples/readouts/association.jsonl` is rewritten at the new positions with a
sidecar, so `dry_run` (`README` command block) exercises 19 sites.

**Adapted banks.** The adapted banks (`adapted/*/association.json`, 10+ subjects) have no `mc`.
They fail loudly ("re-adapt: no mc options") until their distractors are authored (no GPU) and their
reads are re-planned.

---

## 4. Answers

**Q (C6): where is the concept "most commonly held" in the summary sentence? The last token?**
Unknown for association today. Every cached association readout is from the old plain render's
final token, so no per-site data exists. The sibling families on the same suffix give the prior
(`docs/read_sites.md` table, s3d-rl600, Gemini judge):
- Content sits at the punctuation and newline sites after the specials. The specials themselves read
  as nothing.
- Conjunctive peaks at the suffix `"."` (0.09), against 0.07 at the final `\n\n`.
- Role-bound peaks at `ize` (0.104) and at the `\n` after `<|im_end|>` (0.102), against 0.042 at the
  final token.

So the last token is a good cheap default, but maybe not the best site. The spec adopts the last
token now and the shared pre-registered switch (C6: pooled `[support]` share over s3d, J-lens
and ML-NLA, > 10 points over the last token; pass rates never decide) once the full readouts
exist. The site shows the per-site share table, which is the direct answer.

**Q (C3, "consider"): should it be MC?** Yes. The free-text judge has no way to fail an item whose
readout names a sibling concept more prominently. Its only defence was the "ranked first among the
candidates of its type" token rule (`basic/prompts.py:93-99`), which prose readouts never trigger
and which Q4 now deletes. Cached evidence that siblings co-occur with the gold:
- J-lens bags for `b3-as-birthday` (Christmas, Halloween, Thanksgiving), `b5-as-easter` (Christmas),
  `bf-halloween` (Thanksgiving, Christmas), `b3-as-barbecue` (picnic) and `cia` (FBI ranked first)
  (`/workspace/root/wsb-ati-runs/readouts/jlens/association.jsonl`).
- `b3-as-birthday` passes natively at L44/L48 for the J-lens (`ext/wsb-runs/macro/jlens`) even
  though L40 ranks Christmas first. Under MC plus the r2 flat-list rule, a list that holds
  "birthday" and another listed option (Christmas, Halloween, Thanksgiving are all options)
  singles out none of those options, so that item now needs a line where "birthday" is the only listed
  option (for a token list, step 2b voids any other quote mechanically).

**Q (C5): is the prompt-only baseline judged by the same judge today?** Yes, but by the lenient one.
- Native 0.32 and summary 0.31 were judged by the same bank-judge instrument as the lens runs. The
  reader was stock Qwen3.6-27B, not Opus.
- It inherits the bank judge's leniency: `bf-sherlock` passes on "noir/detective" and `history-h` on
  "a forgotten history" (`/workspace/root/wsb-summ5-out/po-summary/association/results.json`).
- After C3/C5 it goes through the identical MC instrument (`po-opus-v1`).
- **Expected consequence: the floor rises sharply.** The panel's frontier models already solve
  0.95-0.97 of items at pass@3 under the guess template (`anti_text_inversion.json.association
  .pass_at_3`). An Opus prompt-only reader will likely land near the lens ceiling. The family is
  text-invertible by design (a scene that implies a concept), so its informative numbers become
  score minus prompt-only floor, and the ATI subset (7 expected, still under 20).

**Q (C4): is rare-hit loss still real?** Mostly fixed already, by digest-v3's rare tier: all four
cached v2 flips pass under v3, and turning the tier off brings `winter` back as a miss. The one
remaining v3 loss (`b3-as-vaccination`) is a hallucinated judge quote, not a dropped hit. C4's retry
targets that. The digest-v4 bump (infra) keeps the rare tier and adds the TASK CONTEXT line.

---

## 5. Evidence plan (final website)

| item | artefact | before → after |
|---|---|---|
| C1 | v1 vs v2 bank diff; ATI entry | 100 → 93 items. ATI ids before contain `nasa, cia, history-h, love-h, de-konig`; after, none of the 7 retired ids. Table of panel `draw_pass` per retired id (as in C1). `bank_path("association")` → `items_v2.json`. |
| C1 | `bf-sherlock` | Prompt-only PASS on "noir/detective" → FAIL or cannot tell (gold is now `Sherlock Holmes`). s3d still PASS via "Sherlock Holmes" (L36). |
| C2 | `wsbench plan family=association` row for `pt-carnaval`, resolved tokens | Before: `plain`, `final_token`, 1 site (`"."`). After: `chat_summarize`, 19 sites `Sum … \n\n`, `lite_positions` shown. Readouts file: 93 × 19 × 11 rows. Per item `extras.n_readouts_in == n_readouts_bundled == 209`. |
| C3 | Offline instrument comparison, labelled "cached v1 readouts, judge test only": re-judge the **cached old-site** readouts (s3d, J-lens; `/workspace/root/wsb-ati-runs/readouts/{s3d,jlens}/association.jsonl`, sidecar-less, report-only) with the new MC judge (API phase, before GPU) | Per-item flip list, bank judge vs MC. `b3-as-birthday` J-lens: shown with its L40/L44 lists; expected cannot tell where the line holds birthday plus another listed holiday (r2 flat-list rule), PASS only where the quoted line singles out birthday (no other listed option on it; step 2b voids token lists that break this). Any item that flips PASS → distractor/cannot tell is listed with its readout. |
| C3 | Deterministic gate | Per arm: `n_gold_raw`, passes at step 3 (listed form), `n_description_credit` (step 5) with every description-credit quote verbatim, `gold_unverified`, `gold_unlisted_script`, `gold_desc_rejected`, `gold_flat_list` (`n_flat_list_voided`) counts. `b3-as-birthday` holiday soup: shown with its gate outcome. |
| C3 | Per-arm headlines on the new plan | s3d-rl600, J-lens, `mlnla-rl2-2000` all-layer full + lite rows (gpu G14), each with `config.sampling` from the sidecar; no row for unproduced arms. |
| C3 | Distractor coverage report | For each item: the cached readouts' same-type wrong concepts (mined from all cached arms) and whether the option list covers them. |
| C3 | Native layer columns | `n_items_gold_any_layer`, `n_items_distractor_any_layer`, `n_items_distractor_majority` beside every native / ATI number. |
| C3 | Floors | Headline shown beside chance 0.125, measured lucky-guessing, and prompt-only (Opus, same instrument). |
| C4 | s3d summary, `neighbors`, `winter`, `divorce` | v2 FAIL → v3 PASS (already cached), and PASS again under the new instrument on new readouts. |
| C4 | `b3-as-vaccination` | v3 FAIL (quote "That child got the vaccination" not found) → PASS after the retry quotes "vaccine". Show both cache rows. |
| C4 | Unit tests | `test_spelling_variant_rule_present`, `test_bad_quote_retried_once`, `test_task_note_reaches_digest` (green CI link). |
| C5 | `results.json` of prompt-only vs s3d | Identical `strip_reads(config.prompt_version)`, judge, summarizer key; prompt-only `config.reader = prompt_only:claude-opus-5-5`, one cell per id at L44. Rows carry MC `pick`. Old Qwen floors 0.32 / 0.31 shown struck through as superseded. |
| C6 | `scripts/lite_site_table.py` output: per-site pooled `[support]` share (s3d / jlens / mlnla columns + pooled) and the ≤ 5 candidates | Chosen `ASSOC_LITE`, whether its share cleared the > 10-point bar over `final_token`, and (reported only) each candidate's lite headline and lite vs full headline per arm. |
| C5 | Prompt-only floor entry | `n` (= judged − refused), refusal share, family CI; `not_measurable` if > 20% refused. |
| C7 audit | gpu R4b table, association row | `n`, `n_too_lenient`, `n_too_strict`, `n_ambiguous` with every non-ok verdict verbatim (s3d, J-lens, ML-NLA). The `credit` stratum is shown separately (`listed_form` vs `description`). If association is flagged (≥ 3), gpu R4c runs: fix PR (new `PROMPT_VERSION`), re-run R4 for association (12 configs, J-lens, ML-NLA, lite), re-audit, ≤ 2 rounds; leftovers go under "New errors found". Zero too-lenient on step-3 passes is the expected result. |
| C7 | 12-config table | association all-layer + 11 single-layer s3d-rl600 rows, `config.sampling = prose1`, `sampling_source = declared`, summarizer/judge Opus 5.5 (`extras.digest_served_by`). |

---

## 6. Risks / conflicts (shared files touched)

**Shared files** (all shared machinery is built by the infra PR; association only consumes it).
- `src/wsbench/readplan.py`: remove association from `:310-325`, add the branch with
  `lite_positions=ASSOC_LITE`, `lite_layers=None`.
- `src/wsbench/evals/association/__init__.py`: own `EvalSpec(bank=Path("evals/association/
  items_v2.json"), task_note=DIGEST_TASK_NOTE, min_full_positions=19, full_contiguous=True,
  judge=JudgeConfig(prompt_version=PROMPT_VERSION))` instead of `bank_family(...)`. No registry
  edit beyond infra's `bank_path` change.
- `src/wsbench/basic/prompts.py`: delete the association `DIGEST_TASK_NOTES` line (`:73`). Every
  basic README prints `DIGEST_TASK_NOTES_TEXT`, so all basic READMEs change (CLAUDE.md §Shared
  judges). The deletion changes the fingerprinted text, which is covered by infra's bump of
  `basic/prompts.PROMPT_VERSION` to `bank-2026-10-30` (and medical to `bank-2026-10-30-md`);
  association adds no PV of its own there (`test_bank_pv_bumped_when_prompts_change`).
- `src/wsbench/baselines/lucky_guessing.py`: BUILDERS and DESCRIPTIONS.
- `src/wsbench/baselines/text_inversion.py`: none expected (rows carry `pass`).
- `evals/baselines/{anti_text_inversion,prompt_only_summary,lucky_guessing}.json`: re-freeze only
  through their tools.
- `src/wsbench/adapt/{lint.py:11, author.py:681-700, families.py:273}`: add `mc` to REQUIRED and to
  the authoring brief. The agent skill (#69) needs the distractor rules for association.
- `README.md:116-119` and `:385` (instrument table), `docs/read_sites.md`, `evals/association/README.md`.
- `src/wsbench/viewer/build.py:20`: none, the group stays `basic`.

**Tests that predate this PR and must change.** Each change below is sanctioned here, because
association leaves the bank judge; nothing else may change an existing assertion:
- `tests/test_basic_association.py`: the `family` fixture (`:61-74`) re-points to
  `medical_diagnosis`, which stays on the shared bank judge (critique 27). Its bank-judge
  assertions keep their meaning.
- `test_registered_spec` (`:108-111`, asserts `bank-2026-10-10` and `"≈ 1.1k"`) is rewritten for the
  new family (`assoc-mc-2026-10-30`, new `calls_per_arm`).
- `test_bank_targets_and_labels` (`:92-105`) is unchanged and must stay green: v1 is untouched.
- `tests/test_bank_judge_v2.py:47`: drop `"association"` from the shared-PROMPTS loop.
- `tests/test_medical_diagnosis.py:187`: drop `"association"` from the tuple that asserts the
  shared bank PV (the value itself moves to `bank-2026-10-30` under infra's sanctioned bump, not
  this spec; the remaining families and `bp.PROMPT_VERSION` keep the assertion).
- No other pre-existing test assertion changes; any other diff under `tests/` that edits an
  existing assertion is a review blocker.

**Design risks.**
1. **Prompt-only near ceiling** (§4): the headline becomes hard to read without score minus floor.
   The website must show the floor beside every number.
2. **ATI size**: about 7 items stays out of the ATI macro, as today. Retiring items cannot fix that.
   Growing it needs new, Qwen-gated, hard-to-invert items, which Camila did not ask for. Flagged,
   not planned.
3. **Native any-layer MC is lenient over 11 layers** (one gold pick among other layers' distractor
   picks passes). It is the opt-out and the ATI gate only; the ATI pass rule is unchanged by
   decision. `mcjudge.layer_pick_columns` makes the leniency visible beside every native / ATI
   number. The summary headline judges one digest.
4. **PR #75 naming**: `tier=lite` there is a judge cost tier; `reads=lite` here is the read-site
   mode. Independent keys, no rebase (decision).
5. **Flat-list rule may cost true hits on token lenses**: a J-lens list that holds the gold and
   another listed option now reads as cannot tell, whatever the rank (Q4 + r2 rule, deliberate);
   the gold alone among non-option words of its type still passes. Because every option list has
   ≥ 4 same-type siblings, most same-type lists will hold another option. The C3 offline
   comparison lists every item this flips. Round 3 makes this mechanical for token lists (C3
   step 2b, `extras.n_flat_list_voided`), so the judge's reading cannot soften it.
6. **Cells**: association and its siblings all read `GRID` now (infra §2.1.2), so association's
   19 × 11 cells per item match conjunctive and role_bound.
7. **Description credit is the residual leniency path** (C3 step 5): it is visible as
   `extras.n_description_credit` with verbatim quotes and is audited as its own `credit=description` stratum (≥ 10) in R4b.
8. **gpu G13's stated reason for association** ("scene screen + distractors in the item text")
   is inaccurate: the panel never sees distractors. The kind (new answers) is right; the reason
   is the changed render (C2). Per G13, the family spec wins; gpu.md should update the reason
   text (still at gpu.md:477 in round 3). The R8 `F=` list (gpu.md:1064) includes association,
   which matches this spec.
9. **Audit stratum needs a gpu entry.** The `association=credit` stratum (C7) needs a row in
   `audit_verdicts.py`'s `STRATA` table and `association=credit` on the R4b `--strata` line
   (gpu G12 / R4b, gpu-owned). Without it the R4b sample is pass/fail × prose/token only and
   description credit may be under-sampled.
10. **Stale gpu cells row.** gpu.md §3.3 (line 658) still lists association as 100 items /
    20,900 cells; the plan gives 93 / 19,437 (§3). gpu R1's regenerated table must use the plan.

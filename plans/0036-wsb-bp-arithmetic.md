# Plan 0036: arithmetic_intermediates — Camila's 2026-10-30 fixes (WorkspaceBench fix campaign)

Workstream "arithmetic" of the campaign whose shared infra is plan 0032 (#140). The spec below is
the campaign spec of record (`plans/arithmetic.md` in the campaign notes), copied verbatim after
the implementation record. Binding decisions: Q1 (single-bullet O-lens = `bullet4`), Q4
(combining rule, no rank-1 exception, flat lists single out nothing), Q14 (lite = L56/L60 at
every position; default = all 11 grid layers).

## Implementation record (2026-10-30)

Camila's sentences and what this PR does:

| sentence | done |
|---|---|
| "…each readout is labelled with the prompt token it came from (token=…)…" / "Remove the token labels" | batched headers are `[k] pos=<offset>:` only; `SYSTEM_BATCH` describes exactly that; `PROMPT_VERSION_BATCH = arith-free-batched-2026-10-30`. Measured (E1, 149-item stratified sample of the cached s3d-rl600 56/60 readouts, native `cells=all`, Opus 5.5): labels removed with nothing else changed → pass 0.584 → 0.584, gold named when written 0.280 → 0.274, null named when written 0.112 → 0.110. The labels were not what produced the gold-vs-null gap. |
| "Update the ati subset with the new 167 item version" | re-gated now (re-judge only: stored panel answers, 12 draws × 596, `cells=frozen`, new instrument `arith-free-2026-10-30`); 167 → 166 (`fracsmall-003` dropped: one Qwen draw now passes). 111-id numbers marked superseded. |
| "only a single readout … unless … single token olens … four times … bullet points" | `prose1` cells judged as their one generation, `bullet4` cells as `readouts.bulleted(4 generations)`; values verified inside one generation; tokens as the bag. |
| "By default judge at ALL layers not just two (fast/lite mode should be those two layers)" | plan rows (landed in #140) GRID / lite 56,60; family: `min_full_positions = 34`, full-read guards exercised by tests; summary and native read every selected layer. |

Deviations from the spec text (each reasoned in the PR body):

1. `SYSTEM*`: the numeral-bag rule loses its "or a tight cluster" clause and gains "a bag or
   list of several different numbers singles out none of them" (decision Q4 deletes the
   rank-1 / prominence exception; the spec's "rules unchanged" would leave the prompt
   contradicting the shared token note it now renders).
2. `SYSTEM_BATCH`: "Judge every entry on its own" names the token-note exception explicitly
   ("tokens of adjacent entries may be joined only to spell one word …, never to assemble a
   number"), the arithmetic analogue of late critique fix (4).
3. `TASK_NOTE` says "a few operations" instead of the spec's "two or three operations": the
   spec's own `test_arith_task_note_has_no_numerals` forbids number words.
4. Quote route: a quote verifies when it writes a number word (`nine`) as well as digits or a
   CJK numeral, so the shared `nine` / `九` digest keys can be credited, AND it must yield the
   named value (C6): some numeral it writes, sign included, equals the top value (digits,
   `23/13`, `负五十一`, `十三分之二十三`, `三点五`, number words; `negative 54` /
   `minus fifty-one` are negative only). Review fix: without it, `one way` vouched for 135 in
   native mode and bypassed the flood void in summary mode. The pre-existing
   `test_verified_and_verdict` assertion that `负五十一` vouches for -52 is inverted (now: it
   vouches for -51, not -52 or 51), which C6's "yields the named value" sanctions. Known gap:
   word fractions (`four-thirds`) do not yield a value (1 of 6,645 quoted panel replies).
5. Pre-existing test edits: the sanctioned `_ENTRY` regex; plus `"Lens output:"` →
   `"Readout:"` in `test_registered_readme_and_dry_run` (forced by C5 + the shared
   `test_no_tool_names_in_prompts`; the spec did not list it).
6. ATI re-gate run in this PR instead of at gpu R8 (it needs no readouts; leaving it would make
   `anti_text_inversion=True` exit 2 for arithmetic after merge). If R4c bumps the PV again, R8
   re-runs it.

---

# Workstream spec: arithmetic_intermediates ("Arithmetic intermediates")

Code of record: `/root/wsb-bp-base` @ cd6b0fa. Paths below are relative to it unless absolute.
Camila's section (verbatim, `/workspace/root/wsb-bp/notes/feedback.md`):

> In the batched every-position mode, each readout is labelled with the prompt token it came from
> (token=…), so the judge effectively sees the whole expression. Its own instructions say it
> doesn't. The judge names the correct intermediate 3.3× more often than wrong numbers that also
> appear in the readouts, which hints it may be using the visible expression. That's not proven.
> The fix is cheap: remove the token labels, or re-judge a sample without them and compare.
> Remove the token labels
> Update the ati subset with the new 167 item version
> Make sure that only a single readout is being judged unless the method is a single token olens
> which should be sampled four times and concatenated into bullet points
> By default judge at ALL layers not just two (fast/lite mode should be those two layers)

(The first paragraph is the audit's text quoted back; the four short lines are the orders. "Single
token olens" is read, per binding decision Q1, as the single-bullet O-lens (`*-x4` arms, sampling
`bullet4`); the campaign's oracle lens s3d-rl600 is multi-bullet k=1, sampling `prose1`.)

Round-1 revision (2026-10-30): aligned to `plans/SHARED_API.md`, `_fable_decisions.md` (Q1, Q4,
Q14, ATI re-gate, versioned banks) and `_critique.md` items 1, 4, 8, 16, 34; see
`_resolution_log.md` ("arithmetic" lines).

Round-2 revision (2026-10-30): aligned to round-2 `SHARED_API.md` / infra.md (number_flood r2
definition, `mc.token_note(flat_types)`, `numerals` owned by the infra PR, full-read guards
(i)-(iii) with sidecar-only enforcement, sample licence) and gpu.md (G12 leniency audit, G13/R8
re-gate, G14 required J-lens + ML-NLA arms); fixes `_critique_r1.md` items 3, 4 and 8; see
`_resolution_log.md` ("arithmetic r2" lines). Coverage map: §0.

Round-3 revision (2026-10-30): aligned to round-3 `SHARED_API.md` / infra.md / gpu.md
(`digest.BULLET_MARK`, bulleted number lists as flood runs and `number_flood` on whole samples
only, `mc.token_note(flat_types, multi_select=)` rendered from the spec in every prompt, G11
site manifest, G12/R4c fix loop, G13 mechanical re-gate rule, R6 floor timing); fixes
`_critique_r2.md` items 4, 5, 6, 12 and 13 as they touch this family; see `_resolution_log.md`
("arithmetic r3" lines).

## 0. Coverage map (every sentence of Camila's section)

`sentence_id` is the G11 manifest key (`<section>:<line no. in notes/feedback.md>`); `site/build.py`
builds one manifest row per (sentence, change) from this table, `pending` until the evidence
artefact exists.

| sentence_id | Camila's sentence | change | named test(s) | evidence |
|---|---|---|---|---|
| Arithmetic intermediates:129 | "each readout is labelled with the prompt token … Its own instructions say it doesn't" | C1 (labels removed; `SYSTEM_BATCH` header text matches what is sent) | `test_batched_user_has_no_token_labels`, `test_arith_digest_bundle_has_no_token_text` | E1(a), E1(c) |
| Arithmetic intermediates:129 | "names the correct intermediate 3.3× more often … not proven" | C1 + E1(b) measurement on the same cached readouts | (measurement, no unit test) | E1(b) before/after gold-vs-null rates |
| Arithmetic intermediates:129, :130 | "remove the token labels, or re-judge a sample without them and compare" / "Remove the token labels" | C1 (both: removed, and compared) | as row 1 | E1(a)-(c) |
| Arithmetic intermediates:131 | "Update the ati subset with the new 167 item version" | C2 (167-id subset everywhere; 111-id numbers retired; re-judge-only re-gate at R8, after R4c) | `test_arith_ati_entry_is_the_panel_subset`, `test_arith_frozen_panel_readouts_load_under_guards`, infra `test_bank_sha_unchanged_for_untouched_families` | E2 |
| Arithmetic intermediates:132 | "only a single readout is being judged unless … single token olens … sampled four times and concatenated into bullet points" | C3 (`reads.load` → `readouts.normalize`; `readouts.bulleted` for `bullet4`) | `test_arith_prose1_judges_one_sample`, `test_arith_bullet4_judges_four_bullets`, `test_arith_bullet4_value_not_assembled_across_generations`, `test_arith_s3d_multibullet_generation_is_one_readout` | E3 |
| Arithmetic intermediates:133 | "By default judge at ALL layers not just two (fast/lite mode should be those two layers)" | C4 (plan `layers=GRID`, `lite_layers=[56,60]`, `lite_positions=same`; guard (ii) refuses a 2-layer file under full) | `test_arith_plan_full_is_grid_lite_is_56_60`, `test_arith_full_default_judges_every_layer`, `test_arith_lite_reads_two_layers`, `test_arith_full_rejects_56_60_only_file`, `test_arith_full_rejects_partial_span` | E4 |
| Chain intermediates:146 (chain.md owns the row; arithmetic supplies the method it names) | "use the same method as arithmetic intermediates: lenses that mention every number possible should not win unless the correct number is somehow distinguishable" | C7 (shared `digest.number_flood` void incl. bulleted number lists; digits never assembled; 5-key cap + `cross`/`net`) | `test_arith_flood_line_singles_out_nothing`, `test_arith_bulleted_number_list_is_voided`, `test_arith_worked_multistep_prose_is_kept`, `test_arith_digits_never_assembled_into_a_number` | E7 |

---

## 1. Current state

**Bank.** `evals/arithmetic_intermediates/items.json`: 596 items, 14 variants, each item with
`intermediates[0]` (the gold), `answer`, `tolerance` (`exact` | `rel5pct`), `null_set`, frozen
`cell {layer, pos}` and `role`. The header's `read` string still says "at layers 56 and 60"
(descriptive only; `bank_fingerprint` hashes items + plan rows, not the header:
`src/wsbench/baselines/text_inversion.py:1013-1043`).

**Read plan.** `src/wsbench/readplan.py:499-516`: render `chat`, positions `{"kind":
"all_from_end"}` (every one of the 34-42 render tokens, as negative offsets), layers hardcoded
`[56, 60]` (`:509`), `extra = {variant, frozen_cell}`. No lite/full distinction exists anywhere in
readplan (`grep lite` finds nothing). `GRID = list(range(20, 61, 4))` (`:16`) = 11 layers, which
contains 56 and 60.

**Every cached readout file is 56/60 only** (checked: `wsb-ati-runs/readouts/{s3d,mlnla2k,jlens}`,
`wsbench-pub/outputs/readouts/*-x4`, `s3d-rl600`: 44,044 rows = 22,022 per layer, layers {56, 60}).

**Judge, native** (`src/wsbench/evals/arithmetic_intermediates/judge.py`):
- `cell_grid` `:196-208`: `opts=cells=frozen` (native default, one cell per item, `SYSTEM`/`USER`,
  `PROMPT_VERSION = "arith-free-2026-09-23"`, `prompts.py:14`) or `cells=all`. Summary mode forces `all`.
- `cells=all` `:284-311`: one call per (item, layer). Each entry is rendered by
  `prompts.render_entry` `prompts.py:199-204` as `[k] pos=<offset> token=<JSON-quoted read-site
  token>: <readout>`; the token comes from `Cell.token` (`judge.py:237,244,297`).
  `SYSTEM_BATCH` (`prompts.py`, README §Batched) describes that header and also says "You do NOT get
  to see the expression". Over 34-42 entries the `token=` fields spell out the whole prompt
  (`Compute`, ` (`, `2`, `5`, `2`, ` -`, …). Version: `PROMPT_VERSION_BATCH =
  "arith-free-batched-2026-09-23"` (`prompts.py:18`).
- Verification `verified()` `:91-105`: a named value counts only if the readout writes it as a
  numeral (`quantities` `:72-88`), or, for the top value only, if the quote is verbatim, has a numeral
  and is not a bare number. Pass = some kept value within tolerance (`tolerance_ok` `:65-69`).
  Paired null `cross` over `null_set` `:143-147`, `net = value - cross` `:448`.
- Token lenses: shown as `render_bag` (`family.py:69-72`, `tok (score) | …`) but verified against
  the bare `" | ".join(tokens)`.
- Prose cells: `cell_text` (`family.py:73`) joins **all** samples of a cell with `\n`. Nothing
  checks how many samples a cell carries.

**Judge, summary mode (the default since plan 0024)** `judge.py:482-666`: every cell of the item
(all positions × all layers in the file; `layers=` filters, `judge.py:225`) → ONE digest
(`digest.collapse`, `:506-514`) → one judge call with `SYSTEM_SUMMARY` (`at most ten`). Family
defaults `summ_numbers=5, summ_rare=0` (`digest.py:200`): the digest returns the 5 most prominent
numbers (`DIGEST_SYSTEM_NUMBERS`, `digest.py:~80-100`), and a judged value is kept only if it is
verified in ONE evidence sample AND equals one of the 5 keys (`verdict(..., keys=)` `:139-141`).
Version: `arith-free-2026-09-23+digest-v3-<variant>-<render>+sj-v7` (`digest.py:410-412`).
Digest group headers are `[L<layer> pos <index>]` only (`digest.py:472-473`; `bundle` docstring
`:503-505`: "headers carry the layer and position index only, never the read-site token text"), so
**the token-label leak exists only in native `cells=all`**, never in the default summary path.
`DIGEST_TASK_NOTE` exists (`prompts.py`, "the model silently evaluates a short arithmetic expression
and answers with no chain of thought") but is used only under `summ_variant=task`
(`digest.py:986-995`); the default variant is `blind` (`digest.py:34`), so today the summarizer gets
NO task context.

**Not MC.** Free recall; the abstain path is `states_value: false` / empty `values`
(`prompts.py` SYSTEM "That is a normal and common answer — do not invent one").

**Prompt wording.** All four judge prompts open "You are reading the output of a "lens" that tries
to verbalize…" (`prompts.py:21-24` and SYSTEM_BATCH/SYSTEM_SUMMARY); the shared notes say "the
lens's readouts" (`digest.py` SUMMARY_NOTE*), the digest system says "activation lens".

**ATI.** `evals/baselines/anti_text_inversion.json` entry: `gate panel-v1`, `n_ati 167`,
`instrument "arith-free-2026-09-23"`, `layers_judged [56, 60]`, `bank_sha 9cf868cb…`. Verified on
cd6b0fa: `text_inversion.subset_entry("arithmetic_intermediates")` returns 167 ids and
`bank_fingerprint()` equals the stored sha. Composition: frac 116, mulmid 10, fraccomp 7, muladd 7,
fracsmall 6, subsubx 5, floordiv/fracadd/fracint/signpair 3 each, absval/addmul/sign/subsub 1 each.
`subset_entry` refuses (exit 2) when the family's `judge.prompt_version` differs from `instrument`
(`text_inversion.py:1464-1469`) or the bank_sha moved (`:1470-1474`). The cached ATI runs
(`/workspace/root/wsb-summ-out/d3/d3a-*`) were judged on an older **111-id** subset (110 frac + 1
fracsmall), and `docs/summary_mode_validation.md:288,337,386` still tabulate n=111.

**Baselines.** `prompt_only.json`: stock-Qwen summaries, native frozen cell L56, 0.175 (instrument
`arith-free-2026-09-23`). `prompt_only_summary.json`: same summaries, summary mode, **0.889**
(above every lens; s3d summary v3 = 0.275). No Opus prompt-only readout exists.

---

## 2. Change list

Shared names used below are exactly those of `plans/SHARED_API.md` (owner: the infra PR, which
lands first; this family PR rebases onto it). This spec implements nothing that infra owns: no
local loader, lite filter, completeness check, sampling normaliser, quote verifier, token cap or
digest stamp literal.

### C1 "Remove the token labels"
(and the preceding paragraph: "remove the token labels, or re-judge a sample without them and
compare" — we do both: remove, and produce the comparison as evidence, §5 E1.)

Code:
- `prompts.py:199-204` `render_entry(k, pos, text, *, bag)` → `"[k] pos=<offset>: <readout>"`; drop
  the `token` parameter. `render_batch_user` `:207-211` takes `(k, pos, text)` tuples.
- `SYSTEM_BATCH`: replace `"[k] pos=<offset from the end of the prompt> token=<the token at that
  position>:"` with `"[k] pos=<offset from the end of the prompt>:"`; keep "an entry's header is not
  part of its output" (still true for `pos=`).
- `judge.py:237,244,297`: delete the `tokens` dict and the token element of `entries`.
- Bump `PROMPT_VERSION_BATCH` → `"arith-free-batched-2026-10-30"` (D9; with C5's wording change
  folded in, one bump).
- README `evals/arithmetic_intermediates/README.md:54,173,189` and top-level `README.md:225-228`:
  describe the new header; add one sentence: "No read-site token text reaches the judge in any mode
  (native batched since `arith-free-batched-2026-10-30`; summary mode never)".
- Summary mode: no change needed; the digest headers are infra's `[L<layer> pos <index>]`
  (`digest.Line.where`), never `Cell.token`. Guarded by the test below.

Tests (new):
- `tests/test_arithmetic_intermediates.py::test_batched_user_has_no_token_labels`: readouts whose
  rows carry `token` values `"Compute"`, `"271"`, `" -"`, `"322"`; run `cells=all,aggregate=native`
  with `run_calls` monkeypatched to capture calls; assert no `Call.user` contains `token=` nor any
  of those token strings that is not also inside a readout text, and `"token="` not in `SYSTEM_BATCH`.
- `tests/test_summary_mode_arith_chain.py::test_arith_digest_bundle_has_no_token_text`: same
  readouts in summary mode with a FakeLLM; assert the captured digest user message contains only
  `[L56 pos …]` headers and none of the read-site token strings.

**Sanctioned pre-existing test update (C1):** `tests/test_arithmetic_intermediates.py:264`
`_ENTRY = re.compile(r'^\[(\d+)\] pos=(-?\d+) token=("(?:\\.|[^"\\])*"): ', re.M)` becomes
`re.compile(r'^\[(\d+)\] pos=(-?\d+): ', re.M)` (the test judge's header parser; `batch_entries_of`
reads groups 1-2 only). No assertion in any test changes for C1.
`test_batched_replies_are_read_per_entry` is unaffected (it asserts on the `k` mapping).

### C2 "Update the ati subset with the new 167 item version"
Membership of record today is the 167 ids in `anti_text_inversion.json` (gate `panel-v1`). What
"update" requires:
1. **Every ATI-scoped number on the website is recomputed on the 167-id subset.** The d3a runs
   (111 ids) are retired from docs: `docs/summary_mode_validation.md:288,337,386` get a
   "superseded: 111-id subset (pre-panel-v1)" note and point at the new 167-id runs;
   `evals/baselines/README.md:404` row (already 167) stays.
2. **Re-gate under the new instrument (binding decision "ATI: every family whose instrument
   changes is re-gated (native gate, as today)", infra §2.13).** C5 bumps `PROMPT_VERSION` (the
   registry instrument, `__init__.py:20`), so `subset_entry` exits 2 until the gate is re-run.
   Procedure: gpu.md G13 / R8, kind **re-judge only** (bank_sha unchanged, item text unchanged,
   instrument changed — this spec's row for the G13 table; G13's "unchanged bank_sha → nothing"
   row does not apply because `subset_entry` also checks the instrument). No new answers: `wsbench
   text-inversion stage=readouts families=arithmetic_intermediates` from the stored panel answers
   (4 answerers × 3 draws), `scripts/ati_panel_judge.sh` (native `opts=cells=frozen,
   aggregate=native`, ≈ 596 × 12 = 7.2k calls), then `wsbench text-inversion stage=gate
   families=arithmetic_intermediates dst=evals/baselines/anti_text_inversion.json`. The entry's
   `instrument` becomes the new `PROMPT_VERSION`. The change is wording only (C5) and the frozen
   cell is unchanged, so membership is expected to stay 167; if it moves, the re-gated set is the
   subset of record (per the decision) and the site shows the delta against the 167 ids
   (added / dropped ids). No hand re-stamp.
   - **Where it sits in the runbook (gpu G13 / R8, round 3).** R8 runs after R4c closes, so
     the instrument re-gated is the final one; if an R4c fix PR bumps `PROMPT_VERSION` again,
     the re-gate runs on that PV. G13's mechanical rule (`scripts/ati_regate_table.py`: "re-judge
     only iff only `bank_sha` / instrument changed") puts arithmetic in the **re-judge-only**
     list because its instrument changed while `prompt_sha` and `bank_sha` did not. The R8 `J`
     list must therefore carry `arithmetic_intermediates`; G13's table row "families with
     unchanged `bank_sha` → nothing" does NOT apply to it (the instrument check in `subset_entry`
     would exit 2). If the script prints "nothing" for arithmetic, this spec wins per G13 and the
     disagreement goes to the site's "New errors found".
   - gpu G9 `audit_run.py` (r3) asserts that the native PV of every arithmetic result equals the
     ATI entry's `instrument` and that `strip_reads(prompt_version)` equals the floor's
     instrument, so a stale entry cannot reach the site.
   - Panel readouts: `text_inversion.write_readouts` keeps arithmetic's `ALL_POSITIONS` /
     `NATIVE_LAYERS` path for the ATI panel (infra §2.11.4 retires it only for the `po-opus-v1`
     flow). `NATIVE_LAYERS` writes at the plan row's `layers` (`text_inversion.py:499`), which
     become GRID, so the regenerated panel files hold 11 layers (more rows, same answer text);
     `cells=frozen` still reads only the frozen (L, pos) cell, so verdicts are unaffected.
   - Full-read guards: the panel files are sidecar-less (report-only, `reads_checked =
     no_sidecar`) or carry `reader: prompt_only:<answerer>` (waiver); either way `check_full`
     and guard (ii) do not exit, and a `cells=frozen` read never needs 34 positions.
3. **bank_sha must not move.** Items and full positions are unchanged; only plan `layers`
   change (already popped by `_row_dict`, `text_inversion.py:990`), and infra §2.6.9 pops
   `lite_positions` / `lite_layers` / `reads`. So arithmetic is IN the set checked by infra's
   `tests/test_ati_fingerprint.py::test_bank_sha_unchanged_for_untouched_families` (state this in
   that test's family list: "arithmetic_intermediates: layers-only plan change").

Tests (new):
- `tests/test_text_inversion.py::test_arith_ati_entry_is_the_panel_subset`: `subset_entry` returns
  the entry's ids, all in the bank, `gate == "panel-v1"`, `n_ati == len(ids)`, and
  `entry["instrument"] == registry.get("arithmetic_intermediates").judge.prompt_version`. Fails
  until step 2 ran — the implementer must not "fix" it by editing the constant back; it lands with
  the re-gated entry.
- `test_arith_frozen_panel_readouts_load_under_guards`: a panel-style file (every position, 11
  layers, one answer copied to every cell) judged `opts=cells=frozen,aggregate=native`, once
  sidecar-less and once with `write_sidecar(reader="prompt_only:qwen")` → no exit, one call per
  item, `config.reads_checked in {"no_sidecar", "prompt_only"}`.

### C3 "Make sure that only a single readout is being judged unless the method is a single token olens which should be sampled four times and concatenated into bullet points"
Reading (binding decision Q1, infra §2.9): "single token olens" = a SINGLE-BULLET O-lens, the
`*-x4` arms → sampling `bullet4` (4 generations per activation, judged as bullets). Every other
prose method — **s3d-rl600 (the campaign's oracle lens, multi-bullet, k=1) included**, and NLA —
is `prose1`: one generation per activation; an s3d generation that itself lists ~4 concept bullets
is ONE readout. Token lenses are `tokens10`. The kind is declared by the producer in the sidecar
(`<family>.jsonl.meta.json`, `sampling: bullet4|prose1|tokens10`), never inferred from bullet
shape.

Status today (measured on the cached files): s3d and x4 files both carry ONE string per cell with
~4 `- ` bullets (36,373 / 44,044 cells exactly 4 bullet lines, the rest 3-8); ML-NLA 1 sample, no
bullets; J-lens 10 tokens. The two O-lens kinds are indistinguishable by shape, which is why the
kind must be declared. Nothing in the arithmetic judge checks samples per cell today
(`cell_text`, `family.py:73`, joins all samples with `\n`).

Change (all enforcement is infra's; arithmetic only consumes it):
- `judge.py:225` `load_readouts(...)` → `cells, rep = reads.load(args, NAME, ids=ids)`. That
  call applies `readouts.normalize(cells, sampling)`: `prose1` keeps `samples[:1]` (counts
  `n_samples_trimmed`), `bullet4` holds 4 separate generations (unpacks the cached packed x4
  strings; `n_packed_ambiguous` / `n_cells_short` counted), `tokens10` keeps the top 10.
  `config.sampling` / `config.sampling_source` are stamped by `mcjudge.base_config`; the
  `LoadReport` counts (`n_samples_trimmed`, `n_packed_ambiguous`, `n_cells_short`) are copied to
  `extras`.
- Cached `*-x4` files have no sidecar, so they would default to `prose1` (one packed string =
  one readout). They are judged with the CLI override `sampling=bullet4`
  (`config.sampling_source = "override"`) and labelled "cached v1 readouts, judge test only".
- Sample licence (infra §2.9.4): arithmetic content is non-relational (one number), so under
  `prose1` a value may be read off any bullet of the generation; it must still be written inside
  one sample (and, by C7, as one numeral or one verified quote).
- **Native judged text per cell** (replaces `family.py:73` `cell_text` for this family): one
  sample → that sample; `bullet4` (the only kind that can carry > 1 sample after normalize) →
  `readouts.bulleted(cell.samples)` = `"- g1\n- g2\n- g3\n- g4"`, i.e. the four generations
  concatenated into bullet points as Camila asks; tokens → `render_bag(tokens)` (infra §2.3:
  `scores=False` by default). The numeral route of `verified()` requires the value inside ONE
  generation (one bullet) for `bullet4`, so four generations are judged together but a value is
  never assembled across them.
- **Summary judged text:** the digest bundle renders each `bullet4` generation as its own `- `
  line under the `[L.. pos ..]` header (infra §2.9.5) — the same four bullets — and `verified()`
  keeps a value only if it is verified in ONE evidence line (unchanged rule, now = one generation).
  A `prose1` s3d generation with ≥ 2 top-level bullets is ONE line whose bullets are joined by
  `digest.BULLET_MARK` (`" ⁞ "`, infra §2.7.10), shown to summarizer and judge as
  `- a ⁞ b ⁞ c`; the boundary is visible, the generation is still one readout.
- Quotes across `⁞`: `digest.fold_quote` maps `⁞` to a space, so a quote that the judge copies
  across a bullet boundary of one generation still passes `quote_ok`. Arithmetic content is a
  single number (non-relational), so the family does NOT add the `statement_lines` check and
  does not report `extras.n_unverified_bullet` (that is for the relational families only).
- Producer: `OLens(bullet=True)` writes 4 separate samples and sidecar `bullet4`; s3d-rl600 writes
  `prose1` (infra §2.9.8, gpu §1.1). Nothing family-local.
- README "Readouts": replace "k = 1 sample per cell for prose lenses" with the D7 rule (above) and
  say that `bullet4` cells are judged as four bullets of one activation, every other prose cell as
  one generation.

Tests (new, family-level; the normaliser's own tests are infra's `tests/test_readouts.py`):
(Every new test below that relies on `sampling` or a full-read guard writes its sidecar with
`tests/conftest.py::write_sidecar(path, **meta)`; sidecar-less fixtures are report-only.)
- `test_arith_prose1_judges_one_sample`: a 2-sample NLA-style cell with sidecar `prose1` → the
  native batched entry text equals sample 0 only; `config.sampling == "prose1"`,
  `extras.n_samples_trimmed == 1`.
- `test_arith_bullet4_judges_four_bullets`: a cell with 4 samples and sidecar `bullet4` → the native
  entry text equals `readouts.bulleted(samples)` (4 `- ` lines); in summary mode the FakeLLM's
  digest bundle shows the same 4 `- ` lines under one header. Same file sidecar-less with
  `sampling=bullet4` → identical entry text, `sampling_source == "override"`.
- `test_arith_bullet4_value_not_assembled_across_generations`: generations `"25"` and `"times 3"`
  with gold 75 → not kept (75 is in no single generation).
- `test_arith_s3d_multibullet_generation_is_one_readout`: one `prose1` sample holding 4 `- `
  bullets → one native entry, text unchanged; in summary mode (FakeLLM) the bundle holds ONE
  `- ` line for that cell with three `⁞` marks, and a judge quote spanning two of its bullets
  verifies (`quote_ok`).

### C4 "By default judge at ALL layers not just two (fast/lite mode should be those two layers)"
Binding decision Q14: lite = the two layers (L56/L60) at the current lite positions (every
position); default = all 11 layers, all positions. Infra §2.6 table: `lite_positions={"kind":
"same"}`, `lite_layers=[56, 60]`. The lite site is fixed by Q14, so the pre-registered
lite-site procedure (SHARED_API r3: support share, `scripts/lite_site_table.py`; association /
conjunctive / role_bound only) does not apply here, and no lite choice uses a pass rate.

- `readplan.py:499-516`: `layers = GRID` (20, 24, …, 60; 11 layers); `lite_positions =
  {"kind": "same"}`; `lite_layers = [56, 60]`; note text: "every position at every grid layer
  (reads=full); reads=lite: every position at layers 56 and 60, the pre-registered layers".
  Positions are every render token in both modes. `extra` keeps `{variant, frozen_cell}`.
- Registry (`__init__.py`): `min_full_positions = 34` (the shortest chat render in the bank; every
  item's `all_from_end` span is ≥ 34 contiguous tokens ending at `-1`), `full_contiguous = True`.
- `judge.run` reads/plumbs nothing itself: `reads.mode(args)` (CLI `reads=full|lite`, alias
  `opts=reads=lite`), lite selection (`reads.select`), full completeness (`reads.check_full`) and
  layer presence for explicit `layers=` all happen inside `reads.load` (C3). The family's only
  lite-related code is the stamp: `prompt_version = reads.stamp(digest.prompt_version(
  PROMPT_VERSION, args, NAME), reads.mode(args))` in summary mode, `reads.stamp(PROMPT_VERSION…,
  mode)` in native (only `+reads-lite` is ever appended; full stamps unchanged).
- Delete the family-local layer guard `judge.py:218-219` for `cells=all` / summary (it already
  applies only to `cells=frozen`); under `cells=frozen`, `layers=<one layer>` still overrides the
  frozen layer and > 1 layer still exits 2 (it is a one-cell diagnostic).
- `cells=frozen` stays the native default (ATI gate instrument, one cell per item); summary (the
  library default, infra §2.5) always reads every selected cell, so "default = all positions ×
  all layers" holds. `scripts/ati_panel_judge.sh` keeps pinning `opts=cells=frozen`.
- `__init__.py:24-27` `calls_per_arm`: "summary (default): 596 digests + 596 judge calls (full or
  lite); native cells=all: ≈ 6.6k batched calls (11 layers) / ≈ 1.2k under reads=lite;
  cells=frozen: 596".
- Per-layer runs (Camila's general "oracle lens with ALL 11 layers, then each individual layer"):
  infra's `layers=<k>` / `layers=each` (infra §2.1.6); the digest sees only that layer; a
  `layers=` run is complete when the layer is present (`mcjudge.is_subset`, infra §2.1.7).
- `config.reads` and `config.layers_judged` come from `mcjudge.base_config`.
- Add `extras.layer_protocols` (native only) as chain does (`chain_intermediates/judge.py:307`); the
  README sentence "not in layer_protocols: reads 56 and 60 only, outside the band" is deleted.
- README + top-level README text "every position at layers 56 and 60" → "every position at the 11
  grid layers (lite: 56 and 60)". Remove "keeping the layers at 56/60 … orchestrator's decision".
- **No silent 2-layer run (infra §2.6.4 guard (ii)):** under `reads=full` with no `layers=`,
  every plan-row layer (GRID) must be present per item, so a 56/60-only file WITH a sidecar exits 2
  naming the first missing (item, layer) (`allow_missing=True` → partial ids, `complete False`).
  A sidecar-less 56/60 file (cached v1, fixtures) is report-only (`extras.partial_ids_unenforced`,
  `config.reads_checked == "no_sidecar"`), and gpu.md G9 `scripts/audit_run.py` fails any
  campaign result whose `reads_checked != "sidecar"`, so it cannot reach the site as a full
  number. Cached 56/60 files are judged with `reads=lite` until the 9 new layers exist. A file
  with more layers than the plan is judged on all of them. Guard (iii): a sidecar `plan_sha`
  that differs from `reads.plan_sha("arithmetic_intermediates")` exits 2.

Tests:
- **Sanctioned pre-existing test update:** `tests/test_readplan.py:57`
  `assert s.positions == {"kind": "all_from_end"} and s.layers == [56, 60]` becomes
  `assert s.positions == {"kind": "all_from_end"} and s.layers == readplan.GRID` plus
  `assert s.lite_positions == {"kind": "same"} and s.lite_layers == [56, 60]`. The frozen_cell
  assertion `:58` is unchanged.
- `test_example_file_carries_the_every_position_regime`
  (`tests/test_arithmetic_intermediates.py:436-466`) is **NOT edited** (round 1 sanctioned adding
  `reads=lite`; withdrawn): `examples/readouts/arithmetic_intermediates.jsonl` has no sidecar, so
  `check_full` and guard (ii) are report-only and all its assertions (`layers_judged == [56, 60]`
  included) hold byte-identical under the default `reads=full`. No pre-existing arithmetic
  assertion or argv changes beyond the two sanctioned edits (§6 risk 1).
- New `test_arith_plan_full_is_grid_lite_is_56_60`: `readplan.plan("arithmetic_intermediates")`
  rows have `layers == GRID`; `plan(..., reads="lite")` rows have layers `[56, 60]` and the same
  positions (one GPU read serves both).
- New `test_arith_lite_reads_two_layers` (11-layer full-span sidecar file, `reads=lite` →
  `layers_judged == [56, 60]`, prompt_version ends `+reads-lite`).
- New `test_arith_full_default_judges_every_layer` (11-layer full-span sidecar file, no `layers=` →
  `layers_judged == GRID`, prompt_version has no `+reads` suffix).
- New `test_arith_full_rejects_partial_span` (sidecar file; one item's L44 holds 10 positions →
  exit 2; with `allow_missing=True` → that id in `extras.partial_ids`, `complete False`).
- New `test_arith_full_rejects_56_60_only_file` (full-span positions at 56/60 only, sidecar
  `reads: full` → exit 2 naming L20; same file sidecar-less → judged, `config.reads_checked ==
  "no_sidecar"`, ids in `extras.partial_ids_unenforced`; same file with `reads=lite` → judged,
  `complete True`).
- New `test_arith_sidecar_lite_file_under_full_exits` (sidecar `reads: lite`, run `reads=full` →
  exit 2, guard (i)).
- New `test_arith_summary_single_layer_feeds_only_that_layer` (11-layer file, `layers=44`, summary,
  FakeLLM: the digest bundle has only `[L44 …]` headers; `complete True`).
- Shared tests that reach this family unchanged: `test_every_plan_row_has_lite_positions`,
  `test_every_lite_rule_is_cell_resolvable`, `test_lite_is_subset_of_full`,
  `test_layers_arbitrary`, `test_layers_variant_is_complete`,
  `test_no_family_calls_load_readouts_directly`, `test_sidecarless_file_is_report_only`.

### C5 (campaign D5/D1, applied here) neutral wording + task context
- All four arithmetic judge prompts: `You are reading the output of a "lens" that tries to verbalize
  what a language model is computing internally.` → `You are reading readouts of a language model's
  internal activations, written as text or as lists of tokens.` (`mc.READOUT_PHRASE` +
  ", written as text or as lists of tokens"); every later "lens output(s)" → "readout(s)";
  `USER*` "Lens output(s)" → "Readout(s)". Rules, caps and schemas unchanged.
  Bumps: `PROMPT_VERSION = "arith-free-2026-10-30"`, `PROMPT_VERSION_BATCH` as C1 (one bump).
- Registry: `EvalSpec.flat_types = ("numbers",)` (infra §2.7 lists arithmetic among the numeric
  families); `EvalSpec.multi_select` stays `False`. Every arithmetic judge prompt that describes a
  token list — `SYSTEM`, `SYSTEM_BATCH` and `SYSTEM_SUMMARY` — renders
  `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` (Q4 combining rule + "a run of
  numbers singles out none of them" + the ⁞ bullet sentence). The bare `mc.TOKEN_NOTE` /
  `digest.SUMMARY_NOTE_TOKENS` (= `token_note()`, no flat types) is NOT used anywhere in this
  family (retired for families with `flat_types` set, SHARED_API r3). No family copy of the
  token note. Covered by infra's `test_token_note_rendered_from_spec`.
  (The summarizer records a flat number list as a list, infra §2.7.1; the void
  itself is the deterministic `number_flood`, C7.)
- Task context: `EvalSpec.task_note` = "the model was silently evaluating a short arithmetic
  expression (two or three operations on given numbers) and answering with only the final number,
  with no written working" (no numbers, no answer). Passed as `digest.collapse(...,
  task_note=SPEC.task_note)`. It is active by default (infra §2.8: `DEFAULT_VARIANT = "task"`).
  The local `DIGEST_TASK_NOTE` constant in `prompts.py` is replaced by this field.
- Summary stamp: cite `digest.prompt_version(PROMPT_VERSION, args, NAME)` (plus `reads.stamp`);
  no digest/sj literal appears in code, README or tests.
- Tests: the shared `tests/test_prompt_tool_names.py::test_no_tool_names_in_prompts` and
  `tests/test_task_notes.py::test_every_summary_family_has_task_note_without_gold` cover this
  family (its `PROMPTS` must list `SYSTEM`, `SYSTEM_BATCH`, `SYSTEM_SUMMARY`, `USER*`); family test
  `test_arith_task_note_has_no_numerals` (no digit and no number word in `task_note`, stricter
  than the shared gold check because every number is a potential gold).

### C6 (found while scoping) native token-bag quotes carry scores
Native token cells are shown `tok (score) | …` (`family.py:72`) but verified against bare tokens.
In the cached J-lens native run (`d3a-jlens-all-native`) **292 of 679** non-empty quotes contain a
`(12.34)` score, so the quote route of `verified()` (the only route for a word/CJK numeral like `九`
or `nine`) always fails for them. Fix by the shared machinery only:
- Rendering: infra §2.3 `render_bag(..., scores=False)` by default, so new native prompts carry
  no scores.
- Verification: the quote route of `verified()` calls `digest.quote_ok(quote, lines)` with
  `lines = digest.native_lines([cell])` in native and `col.evidence[item_id]` in summary
  (`quote_ok` folds via `digest.fold_quote`, which strips score annotations and markdown). The
  family keeps its own ADDITIONAL conditions on top: the quote has a numeral, is not a bare number,
  and yields the named value. No family-local score stripper (chain's `strip_bag_scores` is not
  used here).
- Recompute the native token arms from cached replies (no calls), as for chain.
Test: `test_arith_token_quote_with_score_verifies` (bag `九 (15.19) | nine (14.10)`, judge names 9
quoting `九 (15.19)` → kept).

### C7 (campaign D6/Q4) token lenses and many-number readouts
- **Combining rule (Q4, infra §2.7, shared text in `DIGEST_SYSTEM` and
  `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`):** tokens of one top-10 list may jointly express one meaning (`九 | nine` both
  write 9); adjacent positions of one layer may combine only to spell one word. Arithmetic ADDS one
  condition on top (allowed by infra §2.7.4): **a multi-digit number is never assembled from
  separate tokens**, within a list or across adjacent positions (`2`, `7`, `1` ≠ 271; digits are
  not a split word, and assembling them would rebuild the prompt's operands). Implemented by the
  existing `verified()` rules — the numeral route needs the value written in ONE sample/token, and
  the quote route rejects a bare number — so no new code beyond the test.
- Number words as digest keys: the infra PR builds `src/wsbench/numerals.py` (`numbers_in`,
  `names_value`, `word_value`, infra §2.7.5a, chain.md C2's semantics) and `digest.number_value`
  accepts one word-numeral key through `numerals.word_value`; the `DIGEST_SYSTEM_NUMBERS` key
  sentence rides infra's `digest.DIGEST_PROMPT_VERSION` bump (cited via `digest.prompt_version`,
  no literal). Arithmetic consumes it: a `nine` / `九` / `９` key grounds to 9. No arithmetic copy
  of the number-word table.
- **Flat-list void (Q4, infra §2.7.5, round-2 definition):** a kept value whose ONLY supporting
  lines are `digest.number_flood(line)` lines is not singled out → dropped, in native and summary.
  `number_flood` is infra's (§2.7.5, round 3): a token list is a flood at ≥ 5 distinct numerals; a
  prose sample is a flood only when it contains a list-shaped run (≥ 5 distinct numerals separated
  only by `,` `;` `|` `/` "or" "and" or whitespace, **or by `⁞` between bullets that hold only
  numerals and punctuation**), operands and results of a stated operation (`a op b = c`,
  "gives / is / equals c", "c, then …") break the run and are never counted, and number words count
  only inside a run. So s3d's bulleted dump "- 12\n- 15\n- 17\n- 19\n- 23" is a flood, a correct
  worked computation (bulleted or not) never is. **Whole samples only:** arithmetic calls
  `number_flood` on the sample Lines (`col.evidence[item_id]` in summary, `digest.native_lines([cell])`
  in native), never on `statement_lines` bullets (it raises `ValueError` on `bullet is not None`);
  for `bullet4` each generation is its own Line, so the call is per generation. Counted in `extras.n_flood_voided`; the
  pass rate without the void is reported beside it as `extras.value_before_flood_void` (diagnostic,
  not the headline). This sits on top of the existing 5-key prominence cap (`summ_numbers=5`) and
  the paired `null_set` `cross` / `net`. "Ranked first among candidates" earns nothing.
Tests:
- `test_arith_digits_never_assembled_into_a_number`: J-lens cells at adjacent positions with
  tokens `2`, `7`, `1` and gold 271; judge quotes `271` → not kept, native and summary.
- `test_arith_flood_line_singles_out_nothing`: gold = the rank-1 token of `12 | 6 | 8 | 7 | 11 | 9`
  → dropped by `number_flood`, `n_flood_voided == 1`; the same gold in a 2-number list is kept;
  a prose sample "12, 6, 8, 7, 11 and 9" with gold 12 → dropped.
- `test_arith_bulleted_number_list_is_voided` (critique r2 item 4 family regression): one `prose1`
  s3d sample "- 12\n- 15\n- 17\n- 19\n- 23" (rendered `12 ⁞ 15 ⁞ 17 ⁞ 19 ⁞ 23`) with gold 17 and
  the judge naming 17 → dropped, `n_flood_voided == 1`, `value_before_flood_void` counts it, in
  native batched and summary (FakeLLM); the same sample with only 4 bullets → kept. Infra's
  `test_bulleted_number_list_is_flood` / `test_bulleted_worked_chain_is_not_flood` /
  `test_number_flood_rejects_statement_line` cover the helper itself.
- `test_arith_worked_multistep_prose_is_kept` (critique r1 item 3 family regression): one
  `prose1` s3d sample "- 252 − 3 = 249, then 249 × 4 = 996, minus 7 gives 989\n- subtraction"
  (7 distinct numerals; rendered with one `⁞` before "subtraction") with gold 249 →
  `number_flood` False, value kept, `pass True`, `n_flood_voided == 0`, in native batched and
  summary (FakeLLM).
- `test_summary_mode_0022.py::test_number_key_rule` gains cases (`九` → 9, `nine` → 9, `９` → 9)
  once chain's `numerals` lands; its existing cases are unchanged.

---

## 3. Data needs

- **Bank:** no edit. `items.json` items and plan positions are unchanged, so bank_sha is unchanged
  (layers and lite fields are excluded from the hash). The header `read` string is stale ("layers
  56 and 60"); per D9 it is NOT edited in place — the README states the plan of record supersedes
  it. (If Camila wants the header fixed: `items_v2.json` header-only, items byte-identical,
  `EvalSpec.bank = Path("evals/arithmetic_intermediates/items_v2.json")` through the shared
  `registry.bank_path`; that would give a new `bank_sha` by construction and force a re-gate.)
- **New items / Qwen gating:** none. Prompts are unchanged, so the existing ≥8/10 gate stands.
- **Readouts to regenerate (GPU, Modal, run phase; gpu.md owns production):** for the required
  campaign arms (gpu.md G14 / SHARED_API "Producer / run": `s3d-rl600` `prose1`, `jlens`
  `tokens10`, `mlnla-rl2-2000` `prose1`; all-layer config, full + lite from one read), the 9 new
  layers **20, 24, 28, 32, 36, 40, 44, 48, 52** at every position of the
  unchanged chat render: 22,022 cells per layer → **198,198 new cells per arm** (242,242 total with
  the cached 56/60, reused as-is since render and positions are unchanged; the merged file gets a
  sidecar with the arm's declared `sampling`). s3d-rl600 (campaign arm): `prose1`, one generation
  per cell; J-lens `tokens10`; ML-NLA `prose1`. Each merged file carries the producer-written
  sidecar with `plan_sha = reads.plan_sha("arithmetic_intermediates")`. `*-x4` single-bullet
  O-lens arms are NOT produced on the new layers (not funded here): "cached v1 readouts, judge
  test only", judged `reads=lite sampling=bullet4` on the cached 56/60 files (they are the only
  `bullet4` evidence, E3). NLA/SAE single-layer-42 arms: no change (off-grid diagnostic,
  `layers=42`), also "cached v1 readouts, judge test only".
  Digest size on cached files scaled ×5.5: s3d max ≈ 41k est. tokens/item, ML-NLA ≈ 78k — under
  the global `digest.DEFAULT_TOKEN_CAP` (920k), so one digest call per item; verify
  `extras.n_readouts_in == n_readouts_bundled`.
- **Prompt-only (D8): the shared `po-opus-v1` protocol (infra §2.11), nothing family-specific.**
  `wsbench baseline kind=prompt_only_opus` writes one Opus 5.5 prose cell per item (596) at the
  last full-read site (`pos = -1`, the render's final token) and `layer = PROMPT_ONLY_LAYER = 44`,
  sidecar `reader: prompt_only:claude-opus-5-5`. Judged with `wsbench run all=True
  readouts_root=<dir>/readouts` (no `layers=`, no `reads=`): the same digest + `SYSTEM_SUMMARY` +
  `verified()` + `number_flood` as a lens row. Frozen into `evals/baselines/prompt_only_summary.json`
  (the stock-Qwen 0.889 entry is archived by infra). The floor is the family's own headline (pass
  rate, with `cross` / `net` beside it) under every family rule including `number_flood` and the
  5-key cap; n = judged − refused; > 20% refused → `not_measurable`. The former "(L56, frozen pos)" placement is
  withdrawn. Timing (gpu R6, round 3): the floor is measured after R4c closes, on the final
  PV; if arithmetic's PV changes after R6 (an R4c-style fix), it has no floor until R6 re-runs
  for it, and the site shows "no floor" rather than the stale one. Native `cells=frozen` would not find this cell (it is not at the frozen (L, pos)), so
  no native `prompt_only.json` entry is re-measured; the stale Qwen native entry is not drawn
  (instrument mismatch) and the site shows summary rows for this family.
- **Judge calls (run phase):** judge of record Opus 5.5 (registry default, unpinned). Per arm, summary default 596 digests + 596 judge calls (full), the
  same again for lite; Camila's O-lens study = 1 all-layer + 11 single-layer summary runs on
  s3d-rl600; ATI re-gate ≈ 7.2k native frozen calls (C2); E1 comparison ≈ 300 native batched
  calls; prompt-only 596 Opus readouts + 596 digests + 596 judge calls.

---

## 4. Answers

**Q (implicit, Camila's quoted paragraph): is the judge using the visible expression?**
- In the **default summary path it cannot**: the digest headers are `[L<layer> pos <index>]` only
  (`digest.py:472-473`, docstring `:503-505`) and the summary judge sees only the digest
  (`judge.py:529`). The leak was confined to native `cells=all` (`prompts.py:199-204`), which was the
  run of record before plan 0024 and is now a diagnostic.
- For native, the 27.8% vs 8.5% statistic (judge names the gold when the readout writes it vs. names
  a null-set intermediate the readout writes) is confounded by the gold being more often the
  "result-like" number, so it does not prove leakage. C1 removes the channel; E1 measures the
  difference on the same cached readouts, which settles it.

**Q: is the 167-item ATI subset the one in use?** In code, yes: `anti_text_inversion.json:57`
`n_ati 167`, `subset_entry` returns 167 and the bank_sha matches cd6b0fa. Not in the published
evidence: every cached arithmetic ATI run (`wsb-summ-out/d3/d3a-*`) and three tables in
`docs/summary_mode_validation.md` use the old 111-id subset. 116 of the 167 are `frac` (all frac
items), so ATI arithmetic is mostly a frac result; report `per_variant` beside it.

**Q: is only one readout judged per activation today?** On the cached files, yes in shape (one
string per cell for O-lens, one NLA sample, 10 J-lens tokens), but nothing enforces it and the
s3d (one multi-bullet generation) and x4 (four packed generations) kinds look identical. After C3
the producer declares the kind and `reads.load` enforces it: one generation for every prose
method including s3d-rl600; four generations as bullets only for the single-bullet `*-x4` arms.

**Q (general, as it bears on this family): how are prompt-only baselines judged?** Today: stock
Qwen summaries, judged by the SAME arithmetic instrument (native frozen cell, `arith-free-2026-09-23`,
0.175; summary mode, 0.889), drawn only when the stamp matches (`results.py:216-222`). After C5 both
stamps go stale and are not drawn until the Opus `po-opus-v1` floor is measured with the same
summarizer + judge (§3). Expect it near ceiling: a reader that sees the expression can compute the
intermediate, so arithmetic is text-invertible by construction outside the ATI subset. The
headline must be read against that floor and on the ATI subset.

**Layer decision (Q14, binding):** default = 11 grid layers (56 and 60 included) at every
position; lite = 56 and 60 at every position (`lite_positions=same`). The frozen cell stays the
native `cells=frozen` diagnostic / ATI instrument, not the lite site.

**Decisions taken (this spec; listed on the site, G11 section 4, override if you disagree):**
- "Single token olens" = the single-bullet `*-x4` O-lens (`bullet4`); s3d-rl600 is one readout
  per activation (`prose1`) even though it writes several bullets (Q1).
- Token labels are removed rather than only measured; the with/without comparison is still shown
  (E1).
- The ATI subset of record is whatever the native re-gate under the new instrument returns
  (expected the same 167 ids); the 111-id numbers are retired, not recomputed.
- Lite = L56 + L60 at every position (Q14); default = 11 grid layers at every position.
- A multi-digit number is never assembled from separate digit tokens or positions.
- A number that appears only in a flat list of ≥ 5 numbers (token list, comma list or bulleted
  list) is not credited; the pre-void pass rate is shown beside the headline.
- The bank header's stale "layers 56 and 60" string is not edited (no new bank version).

---

## 5. Evidence plan (for the website)

- **E1 token labels.** (a) Show one cached native batched user message before (from
  `gw-relational-ar/.../rl-onchat-x4/arithmetic_intermediates/cells.jsonl`, e.g. `sign-064|L056|all`,
  containing `token="Compute"`, `token="2"`, …) and the same message rendered by the new code (no
  `token=`). (b) Re-judge native `cells=all,aggregate=native reads=lite` on a stratified 150-item
  sample (≈ 300 calls) of s3d-rl600 without labels; report before/after pass rate, `net`, and the
  gold-named-when-written rate vs null-named-when-written rate (before 27.8% / 8.5%). If the gap
  shrinks materially, leakage is shown; if not, it is refuted. (c) Show a summary-mode digest input
  (`d3b-s3d-all-summary-v3`) has no token text. Test log of C1's two tests.
- **E2 ATI.** Website ATI row for arithmetic shows the re-gated `n_ati` (expected 167) and
  `extras.ati_n_bank = 596` for every arm, the delta vs the 167 ids (expected none), beside the
  retired 111-id numbers marked superseded (before: d3a s3d native 0.099 n=111, summary 0.000
  n=111). `subset_entry` passes under the new instrument (test C2).
- **E3 single readout.** Per-arm table from each new results.json: `config.sampling`,
  `config.sampling_source` (must be `declared`, gpu G9 audit), `n_samples_trimmed`,
  `n_packed_ambiguous`, `n_cells_short`; plus samples-per-cell / bullets-per-sample measured on
  the files (s3d-rl600: 1 generation; x4: 4 generations; NLA: 1; J-lens: 10 tokens). The x4 rows
  are labelled "cached v1 readouts, judge test only" with `sampling_source == "override"`. One
  rendered native entry and one digest group for an x4 cell, showing the four bullets. Test log of
  C3.
- **E4 layers.** Plan rows show 11 layers and the lite fields; test log of
  `test_arith_full_rejects_56_60_only_file` (a 2-layer file cannot pass as a full run); results `config.layers_judged` =
  GRID (full) and [56, 60] (lite, stamp `+reads-lite`); per-layer summary curve for s3d-rl600
  (11 single-layer runs) plus the all-layer run, each with `cross`, `net` and the Opus prompt-only
  floor; lite vs full headline side by side. `audit_run.py` output (missing cells 0 vs plan).
- **E5 C6 / token scores.** (a) J-lens native recomputed from cached replies through
  `digest.quote_ok`: before/after pass count (e.g. `fracsmall-015 L56/-8` with quote
  `九 (15.19)`-style: before unverified, after kept). (b) The required `jlens` arm on the new
  11-layer plan (G14): summary and native headline, `n_flood_voided`, and two rendered token
  entries showing no `(score)` text.
- **E6 floor.** Opus `po-opus-v1` summary-mode number beside every arm (expected high), and on the
  ATI subset.
- **E7 flat-list void.** `extras.n_flood_voided` and `value_before_flood_void` vs headline per arm
  (token lenses expected most affected), with two example flood lines and one correct worked
  multi-step s3d sample that is NOT voided (test log of `test_arith_worked_multistep_prose_is_kept`).
- **E8 leniency audit.** arithmetic's row of the gpu.md G12 table (`scripts/audit_verdicts.py`,
  ≥ 30 stratified verdicts, s3d-rl600 / ML-NLA / J-lens): n, n_too_lenient, n_too_strict,
  n_ambiguous, non-`ok` verdicts verbatim. Gate n_too_lenient + n_too_strict ≥ 3 → the R4c loop
  (gpu round 3): a fix PR (new PV, so `test_bank_pv_bumped_when_prompts_change` holds), re-run R4
  for arithmetic (all configs, all three required arms, lite, opusjudge), re-run R4b, ≤ 2 rounds,
  all before R6 (floor) / R8 (ATI re-gate, C2) and the site build; anything still flagged after
  round 2 goes to the site's "New errors found". Before/after verdict table per round.

---

## 6. Risks / conflicts, shared files

Shared machinery used (owned by the infra PR, not edited here beyond the arithmetic row / caller):
`reads.load` / `reads.stamp` / `reads.mode`, `ReadSpec.lite_positions` / `lite_layers`,
`EvalSpec.min_full_positions` / `full_contiguous` / `task_note`, `readouts.normalize` /
`readouts.bulleted`, `render_bag(scores=False)`, `digest.collapse(task_note=)`,
`digest.prompt_version`, `digest.quote_ok` / `fold_quote` / `native_lines` / `number_flood`,
`digest.BULLET_MARK`,
`numerals` (`numbers_in` / `word_value`), `mc.READOUT_PHRASE` /
`mc.token_note(flat_types, multi_select=)`, `EvalSpec.flat_types` / `multi_select`, `baselines.prompt_only_opus`, `text_inversion._row_dict` popping the lite
fields, `tests/conftest.py::write_sidecar`. The infra PR owns `numerals.py` and the
numbers-digest key sentence.

Files this workstream touches:
- `src/wsbench/evals/arithmetic_intermediates/{__init__,judge,prompts}.py`
- `src/wsbench/readplan.py` (arithmetic row only: `layers=GRID`, `lite_positions`, `lite_layers`)
- `evals/baselines/anti_text_inversion.json` (re-gated entry, run phase),
  `evals/baselines/prompt_only_summary.json` (Opus entry, run phase), `evals/baselines/README.md`
- `evals/arithmetic_intermediates/README.md`, `README.md`, `docs/summary_mode_validation.md`,
  `docs/read_sites.md`, `CLAUDE.md` if it lists layers
- Tests: `tests/test_arithmetic_intermediates.py`, `tests/test_summary_mode_arith_chain.py`,
  `tests/test_text_inversion.py`, `tests/test_readplan.py`, `tests/test_summary_mode_0022.py`
  (added cases only)

Risks:
1. **Pre-existing tests and `check_full`.** Sanctioned pre-existing test edits are exactly two:
   `test_readplan.py:57` (layers + lite fields) and the `_ENTRY` header regex
   (`test_arithmetic_intermediates.py:264`). The other arithmetic tests use sidecar-less
   synthetic files with 1-3 positions per (item, layer); infra resolved (§2.6.4,
   arith-UNRESOLVED-158) that sidecar-less files are report-only, so they pass unedited. If any
   pre-existing arithmetic test still fails, the implementer must NOT edit it — stop and flag. Any
   other change to an existing arithmetic assertion in the diff is a red flag.
2. **ATI instrument coupling.** C5 bumps the registry instrument; until the re-gate (C2) the
   `anti_text_inversion=True` run for arithmetic exits 2. Order: land code, re-gate, then run arms.
3. **Silent 2-layer runs (resolved by infra guard (ii), arith-UNRESOLVED-159).** A sidecar
   56/60-only file under the full default exits 2; a sidecar-less one is report-only and blocked
   from the site by G9's `reads_checked == "sidecar"` check. Residual: an ad-hoc sidecar-less
   full run still prints a number from 2 layers; `config.layers_judged` shows it. Use `reads=lite`
   for cached 56/60 files.
4. **Any-of-grid inflation grows.** 11 layers × ~38 positions ≈ 418 cells/item feed one digest. The
   5-number cap and `number_flood` bound the summary path, but native `cells=all` any-cell rates
   will rise with the null; always show `cross`/`net`, and the exact band (audit: exact 0.43 vs
   rel5pct 0.61 on 2 layers).
5. **`number_flood` on prose.** Under the round-2 rule only a list-shaped run voids: a worked
   computation is never a flood, but a generation that only lists the operands and the answer
   ("25, 2, 3, 4 and 271") is one, so a gold stated only inside such a list is voided. `/` is a run
   separator in infra's rule; an arithmetic readout writing a bare fraction chain ("12 / 4 / 3 / 2
   / 6", no `=`) counts as a run, and so does a bulleted list of bare numbers (round 3: `⁞`
   between number-only bullets is a separator). E7 reports `n_flood_voided` and
   `value_before_flood_void` so the size of these effects is visible; the rule is infra's, not
   re-tuned here.
9. **`bullet4` and the flood void.** Each `bullet4` generation is its own Line, so four
   generations naming four different numbers are never one flood (≤ 4 numbers per call site,
   and each generation is a separate readout that singles its number out). Only the cached
   `*-x4` arms are affected (judge test only); the 5-key cap and `cross` / `net` still bound
   them. Not changed here; noted so the audit (E8) can look for it.
6. **Packed x4 files.** `readouts.normalize` splits a packed x4 string on top-level `- ` lines;
   7,671 cached cells have 3 or 5-8 bullets (a generation containing its own `- ` line), counted
   as `n_packed_ambiguous`. Affects only legacy `*-x4` files, not the s3d-rl600 campaign arm.
7. **Text invertibility.** The Opus prompt-only floor will likely sit at or above every lens on the
   full bank; the ATI subset (≈167, 70% frac) is the only place a lens can beat text, and it is
   variant-skewed.
8. Native `cells=frozen` remains the native default (ATI gate instrument);
   `scripts/ati_panel_judge.sh` keeps `opts=cells=frozen` pinned.

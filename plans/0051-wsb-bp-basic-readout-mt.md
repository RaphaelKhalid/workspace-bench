# Plan 0051 — basic_readout_mt: question bank v2, every-position reads, MC judge + name gate

Campaign: WorkspaceBench fix campaign 2026-10-30 (workstream `basic_readout_mt`, Camila's section
"basic readout mt"), on top of plan 0032 (infra, PR #140). The spec below is the reviewed
workstream spec verbatim (its file:line refs are at `cd6b0fa`; "items_v2", "`BRMT_*`" etc. are
as implemented). The implementation record and its deviations follow the spec (§7).


Code of record: `/root/wsb-bp-base` @ `cd6b0fa` (origin/main). All file:line refs below are at that
commit. Feedback: `/workspace/root/wsb-bp/notes/feedback.md` §"basic readout mt" + GENERAL.
Prior audit: `/workspace/root/wsb-audit-artifact/families/basic_readout_mt.json`.

---

## 1. Current state

**Registration.** `src/wsbench/evals/basic_readout_mt/__init__.py:6-8` calls the shared
`mt_family("basic_readout_mt", ...)`; `src/wsbench/multitoken/family.py:66-81` builds the
`EvalSpec` with `scorer="regex"`, `judge=JudgeConfig(prompt_version=SCORER_VERSION)`
(`mt-regex-2026-09-23`), bank `evals/basic_readout_mt/items.json`. The same factory serves
`multihop_mt`, `multihop_mt_v2`, `multilingual_mt`, `multilingual_multihop`, `multilingual_typo`,
`typo_mt`.

**Bank.** `evals/basic_readout_mt/items.json`: header `family: basic-readout-hard`, contract
`{multi_token: true, include_target: false, conjunctive_units: true}`, frozen 2026-09-10. It has
100 items: 60 `entity` (English), 40 `l2_factual` (id 12, ar 6, fi 5, he 4, hu 4, ko 4, pl 3, ru 2).
Prompts are **completions** ("... is called the", "... tepatnya ke"). Each item has
`eval_render: "plain"`, `readout: {kind: final_prompt_token, offsets: [-1]}`, `units[]` (role
`readout`, plus `language` on L2), `probe_token_lens`, and one `mc.readout` block
`{gold, distractors[4]}`. On L2 items the **source-language answer (`target`/`target_alts`) appears
only in the `language` unit's L2 forms**. The `readout` unit has only en/zh forms, for example
`brh-fi-ahvenanmaa` readout = `Åland Islands | Province of Åland | 奥兰群岛 | 奥兰自治区`.

**Read plan.** `src/wsbench/readplan.py:308-326` routes the family to
`_final_token_families(family, "plain")` (`readplan.py:239-266`): render `plain`, rule
`final_token`, layers `GRID = range(20, 61, 4)` (`readplan.py:16`, 11 layers).

**Positions enforced.** `family.py:145-150` (regex) and `family.py:580-585` (MC) refuse any file with
more than one `pos` per (item, layer): "this family reads the final prompt token only".

**Layers.** These are arbitrary already: `args.layers` or every layer in the file
(`family.py:141`, `576`). The digest cache key carries the layer tag (`digest.py:1035-1036`
`layers_tag`).

**Scorer of record.** Regex (`multitoken/regex.py`). Native path `run_regex`
(`family.py:131-362`): prose is matched with no call. Token bags first go through the
**per-cell interp-v1 summarizer** (`family.py:170-198`; prompt `summarizer.py:15-19`, which says
"Commit to the most specific reading the tokens support"). The interp-v1 summary is then matched as
one more sample (`family.py:209-224`). Summary path `_run_regex_summary` (`family.py:391-491`):
one digest per item (`_collapse`, `family.py:365-388`), then regex over
`digest.gate_texts(joined=True)` (`family.py:425-427`).

**MC judge.** This is diagnostic only (`opts=judge=mc`, `family.py:84-91`). Prompts are in
`multitoken/prompts.py:12-37`. The SYSTEM prompt says "READOUT of an interpretability lens", is
blind to the prompt, and has a "cannot tell" escape `CANNOT` (`prompts.py:24`). The rule "names TWO
OR MORE → cannot tell" applies. Options come from `multitoken/options.py:157-182`: the bank's
`mc` block for `readout`, and `LANG_CONFUSABLES` (`options.py:110-123`) for `language`. A pick
counts only with a verbatim quote (`family.py:522-564`). The result is **forced unpinned**
(`family.py:691`, `810`, `838`), so it is never complete and never in the macro.

**Digest.** Task note `DIGEST_TASK_NOTES["basic_readout_mt"]` (`prompts.py:41-42`: "the model
reads a short prompt whose obvious next concept, a multi-word phrase, it has not yet written").
It is sent only under `summ_variant=task`, and the default variant is `blind` (`digest.py:33-34`),
so **by default the summarizer gets no task context**. `DIGEST_SYSTEM` (`digest.py:41-78`) forbids
translating and forbids combining readouts. `SUMMARY_NOTE_TOKENS` (`digest.py:121-125`) says a
quote from a token line "must be exactly one token".

**Floors.**
- prompt-only `evals/baselines/prompt_only.json:67`: 0.59 [0.49, 0.68], regex, stock Qwen
  description at L20.
- There is **no summary-mode prompt-only entry** (`prompt_only_summary.json` has no
  `basic_readout_mt`).
- lucky_guessing (`evals/baselines/lucky_guessing.json:2`, MC instrument `mc-2026-09-16`):
  **blind 0.456, described 0.488, uniform 0.140** (analytic 0.136). The current option lists give
  the gold away about 3x above chance (see §4 A6).

**ATI.** The entry is `evals/baselines/anti_text_inversion.json:21112`: panel-v1, instrument
`mt-regex-2026-09-23`, `n_ati 0`, `ids []`. The pass field is `any_hit`
(`baselines/text_inversion.py:128-146`, plan 0019 rev 9), so the family is in scope but has an empty
subset.

**Audit (57 reviewed).**
- 4 too strict: Triton, Åland, Bengkulu, Petsamo.
- 3 too lenient: Beckwith–Wiedemann inside lettered option lists; J-lens Tambora and Hafsid, where
  the names come from the interp-v1 summarizer's world knowledge.
- 1 ambiguous: Kapuas, named in the source language.

---

## 2. Change list

**Shared machinery this spec uses, and does not re-implement** (names exactly as in
`SHARED_API.md`; owner: the infra PR, which lands first): `mt_family(...)` (the one factory
signature, infra §2.16), `reads.load` (the only loader),
`reads.select`, `reads.check_full`, `reads.stamp`, `reads.strip_reads`,
`ReadSpec.lite_positions` / `ReadSpec.lite_layers`, `EvalSpec.min_full_positions` /
`EvalSpec.full_contiguous`, `EvalSpec.bank` + `registry.bank_path`, `EvalSpec.task_note`,
`digest.collapse(..., task_note=, expect_all=)`, `digest.prompt_version`, `digest.quote_ok`,
`digest.fold_quote`, `digest.native_lines`, `digest.gate_texts(joined=True, forms=)`,
`digest.DEFAULT_TOKEN_CAP`, `readouts.normalize` (via `reads.load`), `readouts.bulleted`,
`mc.CANNOT`, `mc.seeded_shuffle`, `mc.options_with_cannot`, `mc.READOUT_PHRASE`,
`mc.token_note` (rendered from `SPEC.flat_types` / `SPEC.multi_select`), `mc.form_in`, `mcjudge.base_config`,
`mcjudge.layer_pick_columns`, `tests/conftest.py::write_sidecar` / `native_args`,
`banks.native_langs`, the `po-opus-v1` prompt-only protocol (`baselines.prompt_only_opus`), `results.MACRO_METRICS`, and
the shared tests listed in `SHARED_API.md` (all parametrized over `registry.FAMILIES`, so they
reach this family). Family-owned code is only what is listed below.

**Multitoken factory (infra §2.16 lands the signature; this family only registers values).**
`evals/basic_readout_mt/__init__.py` registers:
```python
SPEC = mt_family(
    "basic_readout_mt",
    TITLE,
    calls_per_arm="≈ 240 (summary: 100 digests + 140 MC)",
    scorer="mc",
    bank=Path("evals/basic_readout_mt/items_v2.json"),
    prompt_version=BRMT_PROMPT_VERSION,
    min_full_positions=8,
    full_contiguous=True,
    task_note=BRMT_TASK_NOTE,
)  # flat_types=() (default), instrument_tag=""
```
`EvalSpec.not_in_macro` stays `""` (in the macro; metric `pass_rate`, in `results.MACRO_METRICS`);
`EvalSpec.multi_select` stays `False`.
- The scorer enum is the shared one (`regex | mc | mc+regex`): this family and multihop_mt_v2
  `mc`; multilingual and multilingual_multihop `mc+regex` (semantics: multilingual.md);
  multilingual_mt, multilingual_typo, typo_mt `regex`, as Camila asked. Checked by infra's
  `test_scorer_enum_assignment`.
- There is **no `multi_position` flag**. The one-position refusal (`family.py:145-150`,
  `580-585`) is deleted for every mt family by infra §2.16; this spec relies on that and adds
  nothing.

**Owned by this spec, written once in `multitoken/`, reused by multihop_mt_v2 and the
`mc+regex` families:** the MC prompt factory `multitoken.prompts.mc_system(task: str,
question_unit: str) -> str` (opening from `mc.READOUT_PHRASE`, shared pick / cannot-tell / quote
rules, then the family's task sentences; item 7) and the name gate
`multitoken.family.name_gate(kind, quote, gold_forms, lines) -> kind` (item 8). Each family
passes its own task text, option block and `name_forms`.

### 1. "should have a judge, not regex"
- `mt_family(..., scorer="mc", prompt_version=BRMT_PROMPT_VERSION)` (infra §2.16) gives
  `EvalSpec.scorer=""` (an LLM judge, so it is preflighted, `runner.py:234-235`) and
  `judge=JudgeConfig(prompt_version=BRMT_PROMPT_VERSION)`, where `BRMT_PROMPT_VERSION =
  "mc-brmt-2026-10-30"` is defined in `multitoken/prompts.py`. That is the family PV; every
  stamp this spec cites is `reads.stamp(digest.prompt_version(BRMT_PROMPT_VERSION, args,
  "basic_readout_mt"), reads.mode(args))`, never a literal.
- `run_family` (`family.py:84-91`): the default `which` becomes the spec's scorer.
  `opts=judge=regex` stays reachable as a diagnostic, and its result is forced unpinned (mirror of
  today's MC line 691).
- **Headline pass = the `readout` unit only, in any language (r2-7).** An item passes when its
  `readout` unit is `correct` after the name gate (item 8). The `language` unit is **not** part of
  the headline on any item: Camila asked brmt for no language requirement (that requirement
  belongs to the multilingual families), and a readout that writes only "Åland Islands" on
  `brh-fi-ahvenanmaa` must pass. The family constant `BRMT_HEADLINE_UNITS = ("readout",)`
  (`multitoken/family.py`, read only by the `mc` path of this family) selects the headline
  units; the MC headline does not read the bank's `conjunctive_units`. The bank contract's
  `conjunctive_units: true` is kept verbatim in v2 and governs only the `opts=judge=regex`
  diagnostic and the `extras.regex` continuity column (so those stay comparable with the v1
  instrument history).
  - The `language` unit of the 40 L2 items is still judged (40 MC calls per arm, already in
    `calls_per_arm`) and reported beside the headline, never gated on:
    `extras.language_unit_rate` (share of the 40 L2 items whose `language` unit is `correct`)
    and `extras.conjunctive_pass_rate` (the pre-2026-10-30 conjunction: `readout` correct AND,
    on L2 items, `language` correct).
  - Row field `any_hit` (the ATI pass field, G5) = the `readout` unit correct, i.e. the same as
    the headline pass for this family; a `language`-only hit is not an `any_hit`.
- Pinning is the factory's per-scorer rule (infra §2.16): for `scorer="mc"` the forced
  `pinned=False` at `family.py:691`, `810`, `838` does not apply, so pinned follows
  `args.judge.pinned` natively and `digest.pinned(args)` in summary mode; **for the three regex
  families the forced-unpinned `opts=judge=mc` diagnostic is retained unchanged.** This spec adds
  no pinning code.
- `complete` comes from `mcjudge.base_config` (via `reads.load`'s `LoadReport`); this family adds
  no completeness rule of its own. `config` carries `reads`, `sampling`, `sampling_source`,
  `reader`, `layers_judged` from `base_config`.
- Each run also writes the old regex contract result on the same evidence as
  `extras.regex = {value, any_hit_rate}` (summary mode: regex over
  `digest.gate_texts(cell, col, joined=True, forms=...)`), for continuity with the instrument
  history. No calls. It is a report column only, never a gate (this is `mc`, not `mc+regex`).
- `evals/basic_readout_mt/__init__.py`: the registration above (`calls_per_arm="≈ 240
  (summary: 100 digests + 140 MC)"`).
- README top-level entry (`README.md:193-196`) and Judges table row (`README.md:387`) are
  rewritten.
- Tests (`tests/test_basic_readout_mt.py`):
  - `test_spec_judge_is_mc_pinned`: `SPEC.scorer == ""`,
    `SPEC.judge.prompt_version == "mc-brmt-2026-10-30"`, and a scripted judge run gives
    `r.pinned_instrument is True` and `r.complete`.
  - **This replaces `test_registered`** (`tests/test_basic_readout_mt.py:39-46`), which asserts
    `scorer == "regex"`. That pre-existing test edit is sanctioned by this item and must be the
    only assertion change to it.
  - `test_l2_item_passes_on_english_answer_alone` (r2-7): on `brh-fi-ahvenanmaa` a scripted
    judge gives `readout` correct (quote `Åland Islands`) and `language` cannot-tell; the item
    passes the headline, `any_hit` is True, and it fails `extras.conjunctive_pass_rate`;
    `extras.language_unit_rate == 0.0` on that one-item run.
  - `test_language_unit_never_gates_headline`: across a scripted run with every
    (`readout`, `language`) verdict combination on L2 items, the headline pass equals the
    `readout` verdict exactly; `BRMT_HEADLINE_UNITS == ("readout",)`.
  - Shared, infra-owned (`tests/test_multitoken_family.py`, infra §2.16):
    `test_scorer_enum_assignment`, `test_regex_families_unchanged` (asserts only
    `EvalSpec.scorer == SCORER` and the unpinned MC diagnostic for the three regex families; it
    does **not** assert a refusal), `test_multi_position_file_is_judged`,
    `test_instrument_tag_appended_once`. The existing
    `test_run_family_toy_run_with_a_scripted_judge` (typo_mt) must pass **unmodified**.

### 2. "should be read on all token positions (except lite/fast should just be last token)"
- `readplan.py:308-326`: drop `basic_readout_mt` from the `_final_token_families` tuple. Add a
  branch (full rule `all_from_end` already exists, `readplan.py:74,134`):
  ```
  ReadSpec(family, id, "chat", {"kind": "all_from_end"}, GRID, text=it["prompt"],
           note="every position of the chat render (user question + template tail)",
           lite_positions={"kind": "final_token"}, lite_layers=None)
  ```
  Lite = the final render token at every GRID layer. The bank v2 `readout` block may carry
  `lite: final_token` as the source readplan reads; the judge never reads the bank for it
  (infra §2.6.1).
- `mt_family(..., min_full_positions=8, full_contiguous=True)` (a v2 chat render is ≥ 15
  tokens: question + template tail; 8 contiguous positions ending at `max` rules out a lite or
  truncated file). Multi-position files are accepted because infra deletes the refusal for every
  mt family.
- **Loading.** Both multitoken load sites (`family.py:140`, `575`) call
  `reads.load(args, "basic_readout_mt")` instead of `load_readouts` (shared test
  `test_no_family_calls_load_readouts_directly`). `reads.load` applies the sidecar sampling,
  the layer-presence check, `reads.select` (lite keeps `max` = pos −1 per (item, layer); on a
  legacy one-position file that is its single cell) and, under `reads=full`,
  `reads.check_full(min_positions=8, contiguous=True, ...)` (exit 2 on a gap or a lite-looking
  file; under `allow_missing` the items go to `extras.partial_ids` and `complete=False`), plus
  the full-read guards (sidecar `reads: lite` under `reads=full`, a missing plan layer under
  `layers=None`, sidecar `plan_sha` ≠ `reads.plan_sha("basic_readout_mt")` → exit 2). These
  enforce only on a file with a sidecar; a sidecar-less file is report-only
  (`extras.partial_ids_unenforced`, `config.reads_checked == "no_sidecar"`). **No family-local
  lite filter or contiguity check** (the round-0 `opts=reads=` handler and the copy of KC's
  `full_span` are dropped).
- `reads` comes from the top-level CLI key `reads=full|lite` (alias `opts=reads=lite`).
  `prompt_version` = `reads.stamp(digest.prompt_version(BRMT_PROMPT_VERSION, args,
  "basic_readout_mt"), reads.mode(args))`: `+reads-lite` for lite only, full unchanged.
- **Summary mode (D1).** `_collapse` passes every loaded cell of every requested layer as
  `digest.collapse(name, cells_by_item, ..., task_note=SPEC.task_note, expect_all=cells)`, so a
  dropped cell raises (infra §2.2.6 lists multitoken). The digest receives all positions × all
  requested layers.
- **Native MC (diagnostic).** One call per (item, layer, unit) on all positions of that layer.
  Each position is a block headed `[pos -k]`, with no token text (D5, and the arithmetic
  no-label lesson). Prose cells join their samples with `readouts.bulleted` (one string per
  cell); token cells render with `render_bag` and the shared
  `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` (renders as `mc.TOKEN_NOTE`
  for `flat_types=()`, `multi_select=False`; never the bare constant, per shared
  `test_token_note_rendered_from_spec`). Native rows also
  carry `mcjudge.layer_pick_columns(rows)` in `extras` (critique 18).
- **Bundle size.** About 43 positions × 11 layers. The d3b run gives about 1.3k est. tokens per
  item per position (`extras.summary.n_bundle_tokens_est` 129,633 / 99 items), so about 55k per
  item: one digest call under the global `digest.DEFAULT_TOKEN_CAP` (920k); hierarchical above it
  (default overflow). **No `FAMILY_DEFAULTS` entry and no family token-cap override** for this family.
  Evidence: `n_truncated_items == 0` and `extras.n_readouts_in == n_readouts_bundled`.
- Tests (`tests/test_basic_readout_mt.py`; the shared `test_every_plan_row_has_lite_positions`,
  `test_lite_is_subset_of_full`, `test_every_lite_rule_is_cell_resolvable`,
  `test_full_on_lite_file_exits_2` also cover this family):
  - `test_plan_reads_every_position_final_token_lite`: the plan rows are render `chat`, rule
    `all_from_end`, `lite_positions == {"kind": "final_token"}`, `lite_layers is None`,
    layers == GRID.
  - Every fixture below writes its sidecar with `tests/conftest.py::write_sidecar` (`reads:
    full`, `plan_sha = reads.plan_sha("basic_readout_mt")`), so the full-read checks enforce.
  - `test_multi_position_file_accepted` (30 contiguous positions, `reads=full`, no exit;
    infra's `test_multi_position_file_is_judged` covers the factory side).
  - `test_reads_lite_keeps_last_position`: 30 positions in, the judge and the digest see only
    pos −1; `prompt_version` ends in `+reads-lite`.
  - `test_reads_full_gap_is_partial_under_allow_missing`: positions −30..−3 and −1 (gap at −2)
    exit 2 by default; with `allow_missing=True` the item is in `extras.partial_ids` and
    `complete is False`. The same file without a sidecar does not exit and lists the item in
    `extras.partial_ids_unenforced` (shared `test_sidecarless_file_is_report_only`).
  - `test_summary_bundle_has_every_position_and_layer` (fake digest; every `[L pos]` header of
    the input is bundled).

### 3. "L2 items silently require translation: writing the answer in the source language does not count for the readout unit. State this prominently in the README headline description, and report an 'any-language' variant."
- The headline **becomes** the any-language rate (item 4) over the `readout` unit only: no
  translation and no `language` unit is required (item 1, r2-7). Nothing hidden remains: the
  headline sentence below names the one unit it scores.
- `extras.translated_pass_rate` keeps the old requirement as a variant. It counts an L2 item's
  `readout` unit only when the verified quote matches a `name_forms` form in one of the bank's
  native languages, `banks.native_langs(header)` (`("en", "zh")` for Qwen3.6-27B; no `"zh"`
  literal in code). Entity items count the same in both. Also report `extras.by_subfamily`
  `{entity, l2_factual}` for both rates.
- The first paragraph of `evals/basic_readout_mt/README.md` and the "What it is / Judged by" lines in
  `README.md:193-196` state:
  - in plain words, "The headline scores one thing: whether the readouts name the answer. On the
    40 non-English items the answer counts in any language, including the question's own
    language, and the readouts do not also have to name the question's language";
  - that the pre-2026-10-30 instrument silently required two more things on those items: an
    English or Chinese name (translation) and the language of the question;
  - which number is which (headline = answer named, any language; `translated_pass_rate` =
    answer named in a native language; `conjunctive_pass_rate` = answer AND question language,
    the old conjunction; `language_unit_rate` = question language alone, 40 L2 items).
- Test `test_translated_variant`: a scripted judge picks gold with quote `Ahvenanmaa` (source
  form). The item passes the headline, and `translated_pass` is False for it. With quote
  `Åland Islands`, both are True. Neither depends on the `language` verdict.
- Test `test_readme_headline_names_scored_unit`: the first paragraph of
  `evals/basic_readout_mt/README.md` contains the "scores one thing" and "do not also have to
  name the question's language" sentences and names `conjunctive_pass_rate` and
  `language_unit_rate`.

### 4. "we should count it in the source language too"
- Bank v2 (§3) adds `name_forms.readout.<src>` = `target` + `target_alts` (already in v1) to every
  L2 item's readout unit.
- The MC judge's option is shown in English. `BRMT_SYSTEM` (item 7) says the name counts "in any
  language, script, spelling or transliteration".
- The deterministic name gate (item 8) accepts any `name_forms` language, via `mc.form_in`.
- `QUESTION_LANGUAGE` (shared multitoken constant, `prompts.py:26-31`) stops hard-coding
  "English and Chinese": it becomes a template whose working-language list is rendered from
  `banks.native_langs(header)` (infra §2.10; checked by `tests/test_no_hardcoded_native_lang.py`).
  Rendered for the frozen banks it reads exactly as today, so the regex families' MC diagnostic
  text does not change.
- Bank v2 header: `contract.native_langs: ["en", "zh"]`.
- Test `test_source_language_counts`: as in item 3, a pick with source-script quote `טריטון` on
  `brh-he-neptune-moon` passes.

### 5. "make sure that only a single-bullet oracle lens gets 4 samples - other methods hsould be one sample per activiton (or top 10 readouts for single token methods like jlens)"
- The sampling policy is producer-side and campaign-wide (D7, `_fable_decisions.md` Q1, infra
  §2.9). This spec does not own it and adds no family guard. The rule as it applies here:
  - single-bullet O-lens (the `*-x4` arms, e.g. `rl-onchat-x4`): sidecar `sampling: bullet4`,
    4 separate generations per activation;
  - **s3d-rl600, the campaign's "oracle lens" (Q1), is multi-bullet with k=1: `sampling:
    prose1`, ONE sample per activation** (its ~4 concept bullets are one generation and one
    readout); NLA and every other prose method also `prose1`;
  - token lenses (J-lens, logit, tuned, rlens): `sampling: tokens10`, top-10 per activation.
- `reads.load` → `readouts.normalize` enforces it on load (trims `prose1` to 1 sample, unpacks a
  cached packed x4 string into 4 samples, cuts token lists to 10) and `base_config` stamps
  `config.sampling` / `config.sampling_source`. The round-0 `extras.samples_per_cell` warning is
  dropped (it inferred the method from bullet shape, which Q1 forbids).
- In-memory a bullet4 cell holds 4 separate samples. The native MC prompt needs one string per
  cell, so it joins with `readouts.bulleted(samples)` (`"- g1\n- g2…"`); the digest renders each
  sample as its own line, so `[support]` counts generations.
- Sample licence (shared, SHARED_API "Sampling"): the gold here is one name, i.e.
  non-relational content, so a prose1 generation is one sample and the name may be quoted from
  any of its bullets. This family does not use `digest.statement_lines` (it is not in the
  relational list).
- Arms (gpu G14 / §3.3): the campaign produces only the required arms on the v2 full plan with
  declared sidecars: `s3d-rl600` (`prose1`), `jlens` (`tokens10`), `mlnla-rl2-2000` (`prose1`).
  No single-bullet O-lens arm is produced; the bullet4 path is shown on the cached
  `rl-onchat-x4` file, labelled **"cached v1 readouts, judge test only"** (judged with
  `sampling=bullet4`, so `sampling_source == "override"`).
- Tests (family-level, on top of infra's `tests/test_readouts.py`):
  - `test_brmt_sampling_follows_sidecar`: a packed `rl-onchat-x4` cell with sidecar (written by
    `write_sidecar`) `sampling: bullet4` reaches the judge as 4 samples (native prompt shows 4 `- ` lines); the same cell
    with sidecar `prose1` (s3d) reaches it as 1 sample; `config.sampling` matches.
  - `test_brmt_tokens_truncated_to_10`: a 20-token J-lens cell renders 10 tokens.
- Evidence: the 12-config run audit (`scripts/audit_run.py`) shows `sampling_source ==
  "declared"`, `reads_checked == "sidecar"` and `sampling == "prose1"` for s3d-rl600 (and
  `prose1` for mlnla-rl2-2000, `tokens10` for jlens) on this family.

### 6. "rephrase this to be in question form not completion form just like regular basic readout so we are not testing next token prediction"
- Bank v2 rewrites each `prompt` as a question in the item's own language. Examples:
  - `brh-ent-aghlabid-dynasty`: "What is the name of the Muslim ruling house that governed
    Ifriqiya from 800 to 909 as nominal vassals of the caliphs in Baghdad?"
  - `brh-fi-petsamo`: "Mikä oli sen Pohjoiseen jäämereen ulottuneen kapean käytävän nimi, joka
    luovutettiin Neuvostoliitolle vuoden 1944 välirauhassa?"
- Every clue is kept. The answer and all `name_forms` are absent (checked with `mc.form_in`). The
  v1 text is kept in `prompt_v1`.
- Render: `eval_render: "chat"` (Qwen chat template, `enable_thinking=False`, no system prompt,
  **no answer-stem prefill**). With a prefill the final position would again be next-token
  prediction.
- `capable/questions.py:260`: `basic_readout_mt` becomes `_asked("basic_readout_mt", "")`. The bank
  prompt now states the task itself, so the `CONTINUE` instruction is dropped.
- `tests/golden/capable_questions.json` entry `basic_readout_mt.first_ask` is regenerated. That is a
  sanctioned golden update.
- Task note (D5): `DIGEST_TASK_NOTES["basic_readout_mt"]` (`prompts.py:41-42`) is rewritten as
  `BRMT_TASK_NOTE` (`multitoken/prompts.py`; the dict entry points at it) and wired as this
  family's `EvalSpec.task_note` via `mt_family(task_note=BRMT_TASK_NOTE)`; `digest.collapse`
  receives `task_note=SPEC.task_note`, and the summarizer gets it by default because
  `digest.DEFAULT_VARIANT == "task"` (infra §2.8). No gold, no tool name:
  > the model was asked a short factual question, in English or in another language, whose answer
  > is one specific name or term that is usually several words long (a dynasty, a place, a person,
  > a compound, a syndrome); readouts may name candidate answers, restate the question, or be in
  > several languages
- Test `test_bank_v2_is_question_form`: every v2 prompt ends in `?` / `؟` / `？`. No prompt
  contains any of its own `name_forms` (`mc.form_in`). The `lang` script check passes, i.e.
  Hangul for ko, Hebrew for he, Arabic for ar, Cyrillic for ru.

### 7. "judge should be multiple choice and have distractor items just like regular basic readout, as well as a can't tell option"
- The MC judge is the headline. Options are built as
  `mc.options_with_cannot(mc.seeded_shuffle(options, ...))` with the default `cannot=mc.CANNOT`
  (`"cannot tell from the readout"`): the 5 substantive options are shuffled first (the seed is
  the existing per-item `options._rng` seed, passed to `mc.seeded_shuffle`), then the
  cannot-tell line is appended LAST and never shuffled in. Shared test
  `test_every_mc_judge_ends_with_cannot` (this family is in `lucky_guessing.BUILDERS`).
- `options.py:157-182` reads the v2 `mc.readout` block. The v2 distractors are **regenerated**,
  because the v1 lists leak (blind 0.456 vs uniform 0.14).
- Distractor rules:
  - 4 real entities of the same type and region/era, with comparable fame;
  - none is an alias, a superset or a subset of the gold;
  - none shares the gold's distinctive name word (so a gold surname is never shared, Q10);
  - none matches any gold `name_form` (`mc.form_in`);
  - the gold's display form is its natural name ("Triton", not "Triton moon"; "Bengkulu", not
    "Bencoolen") so no padding gives it away.
- Gate (an API gate at gpu R5, before the v2 bank freeze): the blind lucky floor
  (`wsbench baseline families=basic_readout_mt variant=blind`, 5 draws, Opus 5.5) must be at most
  the uniform floor + 0.05. Items whose gold is blind-picked in ≥ 2 of 5 draws get redrawn
  distractors, up to 3 rounds. Report the remaining leakers.
- `LANG_CONFUSABLES` is unchanged.
- The judge stays **blind** (no prompt text). The SYSTEM prompt gives only the task type.
- New prompt `BRMT_SYSTEM = mc_system(BRMT_TASK, BRMT_QUESTION)` in `multitoken/prompts.py`
  (the regex families' diagnostic keeps `SYSTEM`). Its opening is built from
  `mc.READOUT_PHRASE`; no tool name. The rendered text, D5-neutral:
  > You judge {READOUT_PHRASE}, recorded while the model read a question you cannot see. The
  > model was answering a factual question whose answer is one specific name or term, often
  > several words long; the question may be in English or in another language. Readouts are
  > noisy, may be in any language or script, may restate the question, and may speculate. You
  > get ONE multiple-choice question about which answer the readouts name.
  > Pick an option only if (1) the readouts write that option's own name — in any language,
  > script, spelling or transliteration; a category word such as "river", "moon" or "dynasty" may
  > be missing; a person's surname alone counts when no other option shares it — and that name
  > picks out this option and no other option; and (2) they present it as the answer: what the
  > thing is, is called or is known as ("it is X", "known as X", "**X**"), not a passing mention.
  > Choose "cannot tell" when no option is named; when the readouts only give a category or a
  > description without the name ("a volcano in Indonesia", "a North African dynasty"); when an
  > option appears only inside a set of lettered choices, a question, an "X or Y" hedge or a
  > negation; when a line or list holds two or more of the options, which singles out none of
  > those options whatever their order or rank; or when two or more options are each presented
  > as the answer about equally prominently (lines are marked [many], [several], [few], [one]).
  > An option that is the only option on its line is singled out by that line, even if the line
  > holds other names of the same kind. If one option is presented as the answer clearly more
  > prominently than any other option, pick it. Never use your own knowledge to turn a
  > description into a name or to choose between named candidates. Give a SHORT quote copied
  > exactly from inside one readout line that contains the option's name (for a list of top
  > tokens, quote as the token-list note says); leave it empty for cannot tell.

  The list sentence is the shared flat-list rule (SHARED_API "flat-list rule", r1-4): relative
  to the options shown; `EvalSpec.flat_types = ()` for this family, so no type-run clause.
  Native token prompts append `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`
  (renders as `mc.TOKEN_NOTE` here); summary
  prompts get the same text as `SUMMARY_NOTE_TOKENS` through the digest. Both carry the Q4
  combining rule (same-list tokens may jointly express one meaning and are quoted joined by
  `" | "`; a word split across adjacent positions of one layer is quoted as that word; nothing
  else combines). There is **no rank-1 exception** anywhere in this family's text.
- The `QUESTION_UNIT` role string "unit: readout" is replaced (for `BRMT_SYSTEM` only) by
  "Which ONE of these answers do the readouts name?". `QUESTION_LANGUAGE`: see item 4.
- **Shared `SYSTEM` tool-name fix.** The multitoken `SYSTEM` (`prompts.py:12-23`, the MC
  diagnostic of the regex families) opens "the READOUT of an interpretability lens", which fails
  the shared `tests/test_prompt_tool_names.py` (`\blens\b`). Since this spec already edits
  `multitoken/prompts.py`, it rewrites that opening to "You judge the READOUT: {READOUT_PHRASE},
  recorded while it read a passage you cannot see." and bumps the diagnostic `PROMPT_VERSION`
  `mc-2026-09-16` → `mc-2026-10-30`. The regex scorer of those families is untouched.
- Every new string goes into `PROMPTS` (`multitoken/prompts.py`) and verbatim into the README
  (`tests/test_prompts_in_readme.py`).
- Tests:
  - `test_options_v2_match_golden` (new golden `tests/golden/basic_readout_mt_options_v2.json`;
    the v1 golden test is kept and pointed explicitly at `items.json`, unmodified);
  - `test_distractors_disjoint_from_gold_forms` (incl. no shared surname);
  - `test_cannot_is_last` (inside the golden test; the shared test also covers it);
  - `test_brmt_system_uses_shared_list_rule`: `BRMT_SYSTEM` contains the "two or more of the
    options … singles out none" and "only option on its line is singled out" sentences, and no
    "mostly candidates of one type" wording (the shared `test_mc.py` list-rule tests cover the
    note text);
  - `test_brmt_system_has_no_rank1_exception` folds into infra's `test_no_rank1_exception_text`
    (BRMT_SYSTEM is in `PROMPTS`).

### 8. "re the systematic issues, a lens that doesn't say the full specific names should indeed fail. but ones where it is obviously referring to the concept like triton/triton moon should pass"
- Bank v2 adds `name_forms: {role: {lang: [forms]}}` per item: every language's natural name for
  the gold. Rules:
  - plain short forms are included ("Triton", "Åland", "Ahvenanmaa", "Bengkulu", "Petsamo",
    "Pechenga", "Kapuas", "Kierkegaard", "Rasputin", "Khachaturian");
  - **surname-only forms (Q10)** are included when the surname uniquely picks the gold among the
    item's options and no distractor shares it ("Khachaturian" passes; "Triton" for the moon
    passes); a partial name that also fits a distractor is not a form, so it fails;
  - forms are **not** filtered by `probe_token_lens` (the multi_token contract stays a regex
    diagnostic only);
  - no generic or category-only forms. Validator: every form has length ≥ 4, is not in a
    category-word list (`mount|river|dynasty|syndrome|constant|moon|island(s)|…`), and matches no
    distractor (`mc.form_in`).
- **Name gate** (deterministic, after the judge), added ON TOP of the shared verifier, never
  replacing it (infra §2.7.4):
  1. `digest.quote_ok(quote, lines)` must be True, with `lines = col.evidence[item_id]` in
     summary mode or `digest.native_lines(cells)` in native mode. This already implements the
     Q4 token rule: a `" | "` quote whose parts are whole tokens of ONE list, or one word spelled
     by tokens of 2-4 consecutive positions at one layer.
  2. A `correct` pick counts only if `mc.form_in(text, gold_forms)` is True for one of these
     candidate texts, all taken from `digest.fold_quote(quote)`: the whole folded quote; each of
     its `" | "` parts; and, for a quote of ≥ 2 parts, the parts **space-joined** and
     **concatenated** in quote order (`"Henry | James"` → `henry james`; `" Khach | aturian"` →
     `khachaturian`). The joins are the Q4 licence (tokens WITHIN one activation's top-10 list
     may combine to read one multi-token word or name); step 1 has already proved every part is a
     whole token of ONE list, so nothing combines across samples, positions (other than the
     adjacent-position spelling of step 1) or layers. Credit still needs a full `name_forms`
     match, so a list whose joined parts give only a category or a description stays a
     `name_miss`. (Resolves multihop_mt.md §6 "one-list multi-word names": mhv2 and the
     `mc+regex` families get the joins through the same `name_gate`.)
  - No family-local quote helper and no other joiner are created (the round-0 ones are retired).
- New verdict kind `name_miss` (gold picked, quote verified, no name form). It is not credited,
  is counted in `extras.kinds`, and is listed in `extras.name_misses` for audit.
- Files: `multitoken/family.py` gains `name_gate(kind, quote, gold_forms, lines)` (steps 1-2
  above, built only from `digest.quote_ok` / `digest.fold_quote` / `mc.form_in`); `verdict`
  (`522-564`) calls it with the item's `name_forms` and `lines`. multihop_mt_v2 and the
  `mc+regex` families call the same function. No new helper in `digest.py`.
- Q4 / GENERAL ("allow combining the top 10 tokens to infer the meaning"): the judge may read
  several tokens of one list together to recognise the answer (`Åland | Islands`,
  `Tunis | Hafsid | dynasty`), and the gate credits the joined parts (step 2), but credit still
  needs a quoted part or join that is a full name form; a list that only implies the answer
  without its name (`Tunis | dynasty` for the Hafsids) is a `name_miss` (Camila: "a lens that
  doesn't say the full specific names should indeed fail").
- Tests:
  - `test_name_gate_short_form_passes` (quote `Triton` → correct);
  - `test_name_gate_surname_unique_passes` (quote `Khachaturian` → correct) and
    `test_name_gate_shared_partial_fails` (a fragment that also fits a distractor → `name_miss`);
  - `test_name_gate_category_fails` (gold picked, quote `volcano` → `name_miss`);
  - `test_split_name_across_adjacent_positions` (`" Khach"` at pos −3 and `"aturian"` at pos −2,
    same layer, quote `Khachaturian` → correct; the same pieces at two layers or non-adjacent
    positions → `quote_ok False`);
  - `test_one_list_parts_join_to_name` (Q4): two tokens of ONE list quoted `" Khach | aturian"`
    → correct (concatenated join); `"Henry | James"` against form `Henry James` → correct
    (space join); `"Tunis | dynasty"` against `Hafsid dynasty` → `name_miss`; the parts of
    `"Henry | James"` taken from two different lists → `quote_ok False` (no credit).

### 9. "make sure the llm summary doesn't inject world knowledge or do any crazy interpretation like in brh-id-tambora-1815 or brh-ent-hafsid-ifriqiya"
- Both cases come from the **per-cell interp-v1 step** (`family.py:170-198`, `608-621`;
  `summarizer.py:15-19` "commit to the most specific reading"). The fixes:
  - (a) The interp-v1 step is deleted repo-wide by infra §2.3 (multitoken call sites
    `family.py:170-205`, `:604-620`; `summarizer.py` removed). This family adds nothing; native
    token arms are judged on `render_bag(tokens)` with
    `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`, summary mode goes through
    `digest.collapse` only.
  - (b) The judge sees only verbatim evidence lines (extractive render: `digest.render_summary`).
    Under `abstractive` the statements are labelled "not evidence" (`digest.py:114-120`).
  - (c) The name gate (item 8) makes a pick that rests on a name absent from the readouts
    impossible to credit, whatever the summarizer wrote.
  - (d) `BRMT_SYSTEM` forbids turning a description into a name.
- Test `test_native_tokens_make_no_interp_call` (family): a native run on a token file completes
  with a fake LLM that records calls, and no call carries an interp prompt (the module no longer
  exists; infra's `test_no_module_imports_interp` is the AST guard).
- Evidence §5 rows E6 and E7.

### G1 (D5) Neutral prompts
- `BRMT_SYSTEM` (above) has no tool name; the shared multitoken `SYSTEM` opening is fixed (item 7).
- Test: the shared `tests/test_prompt_tool_names.py::test_no_tool_names_in_prompts` (it collects
  `multitoken.prompts.PROMPTS` and `EvalSpec.task_note`). The round-0 family test
  `test_brmt_prompts_name_no_tool` is not created (folded into the shared one, critique 33).

### G2 (D5) Task context reaches the summarizer by default
- Uses infra's global `digest.DEFAULT_VARIANT = "task"`; no family override (`summ_variant` is
  global, infra §2.2.2).
- Tests: shared `test_every_summary_family_has_task_note_without_gold` (reaches this family), plus
  family `test_digest_gets_task_note_by_default`: in a dry run the rendered digest system prompt
  contains the item-6 task note.

### G3 (D8) Prompt-only baseline
- Protocol `po-opus-v1` (infra §2.11), no family variant: one Opus 5.5 readout per plan row id,
  input = the v2 chat render through its last full-read site (pos −1, the assistant onset), written
  as one prose cell at that pos and `layer = PROMPT_ONLY_LAYER = 44`, sidecar
  `reader: prompt_only:claude-opus-5-5`, `sampling: prose1`.
- Judged by `wsbench run all=True readouts_root=<dir>/readouts` with no `layers=` and no
  `reads=`: same `digest.collapse` (same task note) → MC (`BRMT_SYSTEM`, same options,
  cannot-tell) → name gate. `reads.load` waives `select` / `check_full` for the `prompt_only:*`
  reader, so `min_full_positions=8` does not reject it.
- Floor = this family's own headline (any-language MC pass on the `readout` unit only, after
  the name gate; item 1), from its own `run` on that file, with the family's Wilson CI; n = ids judged −
  refused; > 20% refused → `not_measurable` (infra §2.11). `translated_pass_rate`,
  `conjunctive_pass_rate`, `language_unit_rate` and `extras.regex` are reported beside it, not
  as the floor.
- Frozen into `evals/baselines/prompt_only_summary.json["basic_readout_mt"]` with
  `instrument = reads.strip_reads(prompt_version)` and the shared entry fields (`n_refused`,
  `refusal_share`, `saturated`, `_source.protocol = "po-opus-v1"`); drawn by
  `summary_floor_applies`, so one floor serves the all-layer, single-layer and lite rows.
- The stock-Qwen summary file is archived by infra
  (`evals/baselines/archive/prompt_only_summary.qwen-2026-10-29.json`; it has no entry for this
  family anyway). The old native regex entry in `prompt_only.json:67` stays for history and is
  never drawn beside the new instrument, by the stamp mismatch.
- Test: infra's `tests/test_prompt_only_opus.py` cases are parametrized over families; family
  test `test_prompt_only_cell_judged_full_and_lite`: a one-cell `prompt_only:*` file at layer 44
  is complete under `reads=full` and `reads=lite`.

### G4 (D3) Layers
- These are already arbitrary on the judge side; `reads.load` adds the presence check.
- Tests: shared `test_layers_arbitrary` and `test_layers_variant_is_complete`; family
  `test_layers_subset_and_single`: with `layers=[44]` the digest cache key is `digest:<id>|44`,
  `config.layers_judged == [44]`, and `complete is True`.

### G5 (ATI rows)
- MC rows gain `any_hit` (= the `readout` unit correct, the headline pass; item 1). `text_inversion.STRICTER_PASS_FIELD`
  (`text_inversion.py:128-146`) keeps reading `any_hit`. Native MC extras carry
  `mcjudge.layer_pick_columns` beside the ATI number.
- The lite fields never enter `bank_sha` (infra §2.6.9); the v2 bank gets its own `bank_sha` and
  is re-gated in the run phase.
- Test `test_mc_rows_feed_ati_gate`: `ti.draw_verdicts` on a native MC result.

---

## 3. Data needs

**Bank v2: new file `evals/basic_readout_mt/items_v2.json`** (naming rule `items_v<N>.json`).
`items.json` (v1) is untouched, and a test pins its sha256 (`2e87983d…`, the ATI `bank_sha`).
- Header: `family: basic-readout-hard`, `version: 2`, `parent: {file: items.json, sha256: …}`,
  the contract unchanged (regex diagnostic only) plus `contract.native_langs: ["en", "zh"]`, and a
  new `gate` text.
- `EvalSpec.bank = Path("evals/basic_readout_mt/items_v2.json")`, read through
  `registry.bank_path` (env overrides still win). `mt_family` takes the `bank=` path.
- Per item: same `name`/id; new `prompt` (a question) and `prompt_v1`; `eval_render: "chat"`;
  `readout: {kind: all_from_end, lite: final_token}` (the `lite` key is readplan's source only);
  new `name_forms`; new `mc.readout`. `units` and `probe_token_lens` are kept verbatim, so
  `opts=judge=regex` still works.
- Generation (API phase, Opus 5.5, no GPU):
  1. Question rewrite in the source language.
  2. Back-translation check: Opus translates the question to English, and a second Opus call
     confirms that the same unique answer follows.
  3. `name_forms` drafted per language (incl. Q10 surname forms) and reviewed by hand against the
     validator.
  4. Distractors drafted, then the blind-floor loop (item 7).
- `examples/readouts/basic_readout_mt.jsonl` is rebuilt with negative-offset multi-position rows
  and a sidecar.

**Qwen gating (GPU, Modal, 1 GPU vLLM is enough; this family spec owns the settings, gpu §3.2
already matches). Runs at gpu R5, before the v2 bank freeze (runbook R0 → R5 gates → freeze v2
banks → merge → R1 → R2 …), together with the item-7 blind-floor API gate.**
- `scripts/qwen_sample_modal.py` rows for the v2 questions: chat template,
  `enable_thinking=False`, 1 greedy + `n=10` at `temperature=0.7`. That is **1,100 generations**.
- Pass = the greedy answer correct AND ≥ 8/10 (the v1 bank's rule, `capable/run.py:181-192`).
  Answers are graded by `name_forms` (`mc.form_in`), any language.
- Failures get one rewrite and a re-gate. If the final v2 bank has fewer than 90 items, stop and
  report.
- Qwen also answers each question once more with its output kept. This is the sanity check that
  the question form did not change the answer.

**Readouts to regenerate (GPU, Modal; D9; gpu G14 / R2 + R2b).**
- The required arms only: **s3d-rl600** (`sampling: prose1`, k=1) for the 12 configs, and
  **jlens** (`tokens10`) and **mlnla-rl2-2000** (`prose1`) at the all-layer config, full + lite.
  Each file gets the producer's sidecar (`reads`, `sampling`, `reader`, `arm`, `layers`,
  `plan_sha`). Every other arm on the site (rl-onchat-x4 `bullet4`, logit, tuned, rlens,
  template, SAE) is **"cached v1 readouts, judge test only"**; this spec funds no extra
  production.
- Positions: `all_from_end` (every position of the chat render). Layers: GRID (11).
- Lite needs no separate production (lite ⊆ full: pos −1 of the same file).
- About 43 positions × 11 layers × 100 items ≈ 47k cells per arm. gpu R1 regenerates its cell
  table from `wsbench plan` (gpu §3.3 still says ~30 positions for this family).

**Floors to regenerate (API).**
- lucky_guessing blind / described / uniform on the v2 options. Update the `described` sentence
  (`baselines/lucky_guessing.py:80-83`) to "which specific name a factual question asks for, and for
  the non-English items which language the question is written in".
- prompt-only summary floor (G3, `po-opus-v1`).

**ATI.** Owned by gpu G13 / R8, row "basic_readout, basic_readout_mt — new answers (question
form)": the panel (Qwen + Opus + astra + argon × 3 draws; Qwen on Modal GPU, astra/argon on
Modal only) answers the v2 renders afresh, judged under the MC instrument, native gate as today.
The current entry goes stale (bank_sha + instrument). Expected: 0 or close to 0 ATI items again
(v1 pass@3 was about 1.0 for every reader).

---

## 4. Answers

- **A1. Does the family count source-language answers today?** No. On L2 items the source-language
  answer feeds only the `language` unit. Bank v1 example: `brh-fi-ahvenanmaa` readout forms are
  `Åland Islands | Province of Åland | 奥兰群岛 | 奥兰自治区`, while `Ahvenanmaa` is a `language`
  form. The audit found this behind 9 of 22 reviewed fails. After the change, the source language
  counts (item 4), the `language` unit leaves the headline (item 1), and the old numbers survive
  as `translated_pass_rate` and `conjunctive_pass_rate`.
- **A2. Single-name forms (Triton) cannot count today.** `regex.scored_units` drops every form any
  single Qwen token could equal (`probe_token_lens > 1`). The authored lists carry padded
  paraphrases instead ('Triton moon', 'Bengkulu town'). The MC judge plus `name_forms` fixes this,
  and the category-only rule keeps "Mount" or "dynasty" failing. "Doesn't say the full specific
  names should fail" is read as: a name that picks out this option and no other passes (the name
  without its category word, or a surname no distractor shares, per decision Q10); a category, a
  description, or a fragment shared with a distractor fails.
- **A3. Where the injected world knowledge came from.** The per-cell interp-v1 summarizer, not the
  digest:
  - `brh-id-tambora-1815`: the bag `volcano | Mount | Gunung | volcanic | …` produced "such as
    Gunung Merapi or Mount Tambora".
  - `brh-ent-hafsid-ifriqiya`: the bag `Tunis | Tunisia | … | dynasty` produced "such as the
    Hafsids".
  - Every cached J-lens pass was `summary_only` (audit systematic issue 4).
  - The interp-v1 path is deleted (infra §2.3), and the name gate makes this failure mode
    non-creditable.
- **A4. Lite site.** It is the final render token (the assistant onset after `</think>\n\n`), as
  Camila asked ("lite/fast should just be last token"). With full v2 readouts, `extras.regex` per
  position on the prose arms (no calls) is published as a profile of where the answer is written
  (artefact 8). It is reported, not used to move the lite site: Camila fixed it to the last token.
- **A5. Does the summarizer get all readouts?** In summary mode, yes: `_collapse` passes every cell
  of every requested layer (`family.py:377-382`), now asserted by `expect_all`. Positions were
  limited to one only by the refusal at `family.py:145-150`, which infra §2.16 deletes for
  every mt family.
- **A6. New error found: the MC option lists leak.** The blind lucky floor is 0.456 and
  described is 0.488, against uniform 0.140 (`evals/baselines/lucky_guessing.json:2`). An
  options-only guesser beats chance about 3x. An MC headline on the v1 lists would therefore be
  inflated. Hence the distractor regeneration and the blind-floor gate (item 7).
- **A7. Second new error: option lists in the readouts.** Prose readouts that themselves emit
  lettered option lists (`brh-ent-beckwith-wiedemann-syndrome`: "A) Beechey syndrome B)
  Beckwith–Wiedemann syndrome …") were credited by regex. Fix: `BRMT_SYSTEM`'s list/hedge rule.
- **A8. How are prompt-only baselines judged here (general question)?** Today: regex on a stock
  Qwen description at L20 (0.59), with no summary-mode floor at all. After: one Opus 5.5
  prompt-only readout per item (`po-opus-v1`) goes through the same digest, MC judge and name
  gate (G3). Its frozen instrument is `strip_reads(prompt_version)`, so `summary_floor_applies`
  draws it beside full, lite and single-layer rows.
- **A9. Is the 4-generations-in-one-sample format a problem?** It is no longer the in-memory
  format. A cached `rl-onchat-x4` cell (4 bullets in one string) is unpacked by
  `readouts.normalize` into 4 samples (`bullet4`), and the native prompt re-joins them with
  `readouts.bulleted`. s3d-rl600 is `prose1`: its one multi-bullet generation stays one sample.

---

## 5. Evidence plan

Re-judge cached cases. This step makes judge calls but needs no new GPU readouts. The judge is
prompt-blind, so v2 options and `name_forms` apply to the v1 one-position readouts.

Run `wsbench judge family=basic_readout_mt readouts=<cached> reads=lite sampling=<kind>
items=<id>` with the v2 bank (`sampling=bullet4` for the x4 file, `tokens10` for J-lens, since
the cached files have no sidecar). On these one-position files, `reads=lite` keeps the only
position. These rows are labelled **"cached v1 readouts, judge test only"**
(`reads_checked == "no_sidecar"`, `sampling_source == "override"`); they are not campaign
results.

| # | case (run) | before | expected after |
|---|---|---|---|
| E1 | brh-he-neptune-moon, rl-onchat-x4 (`/workspace/gw-relational-ar/outputs/wsb_latest/outputs/readouts/rl-onchat-x4/basic_readout_mt.jsonl`) | FAIL (readout unit no hit) | PASS, quote contains `טריטון`/`Triton` |
| E2 | brh-fi-ahvenanmaa, same | FAIL | PASS on the readout unit alone; `translated_pass` True (Åland); `conjunctive_pass` reported (language verdict shown) |
| E3 | brh-fi-petsamo, same | FAIL | PASS (Petsamo / Pechenga) |
| E4 | brh-id-sungai-kapuas, same | FAIL | PASS (Sungai Kapuas most prominent); `translated_pass` False |
| E5 | brh-ent-beckwith-wiedemann-syndrome, same | PASS (only inside A)/B) lists) | FAIL (cannot tell) |
| E6 | brh-id-tambora-1815, J-lens bag (`/workspace/root/wsb-ati-runs/readouts/jlens/basic_readout_mt.jsonl`) | PASS (interp-v1 world knowledge) | FAIL (cannot tell or `name_miss`); 0 interp-v1 calls |
| E7 | brh-ent-hafsid-ifriqiya, J-lens | PASS (interp-v1) | FAIL |
| E8 | brh-id-bengkulu-pengasingan, rl-onchat-x4 | FAIL | report the verdict and audit it (Bengkulu vs Padang prominence) |

Website artefacts (one per Camila sentence; S1-S9 = §2 items 1-9):
1. The E1–E8 table, with readout excerpt, options and judge JSON (S3, S4, S7, S8, S9).
2. Lucky floors v1 → v2: blind 0.456 → ≤ uniform + 0.05 (S7).
3. Headline vs `translated_pass_rate` vs `conjunctive_pass_rate` vs `language_unit_rate` vs
   `extras.regex` (and `extras.by_subfamily`) for s3d-rl600, jlens and mlnla-rl2-2000 on v2
   readouts, full and lite, plus the count of L2 items that pass the headline but fail the old
   conjunction (S1, S2, S3, S4; r2-7).
4. Prompt-only (Opus, `po-opus-v1`) summary floor beside each arm (GENERAL).
5. The s3d-rl600 run at all 11 layers and at each single layer (11 runs, `layers=each`), per the
   GENERAL item.
6. This family's rows of the shared leniency audit (gpu G12 / R4b, `scripts/audit_verdicts.py
   sample` then `table`: ≥ 30 stratified verdicts, pass/fail × prose (s3d, ML-NLA) / tokens
   (J-lens), fresh-context auditor, repeated on the Opus-judge column): n_too_lenient /
   n_too_strict / n_ambiguous with verbatim cases. Family additions to the sample: every
   `name_miss` and the cannot-tell rate full vs lite per arm (all-position over-hedging check)
   (S8, S9, GENERAL audit).
7. `n_truncated_items == 0`, `extras.partial_ids == []`, `n_readouts_in == n_readouts_bundled`
   (S2).
8. A per-position regex profile (reported only; A4).
9. The ATI entry regenerated under the new instrument.
10. `config.sampling` / `sampling_source` / `reads_checked` per arm from `scripts/audit_run.py`
    (s3d-rl600 and mlnla-rl2-2000 `prose1 declared sidecar`, jlens `tokens10 declared sidecar`;
    cached x4 `bullet4 override no_sidecar`, judge test only) (S5).
11. Before/after of one v1 completion prompt vs its v2 question, with Qwen's gate result (S6).

---

## 6. Risks / conflicts (shared files touched)

Shared files:
- `src/wsbench/multitoken/family.py`, `multitoken/prompts.py`, `multitoken/options.py`. The
  `mt_family` signature, scorer enum, pinning rule, refusal deletion and the `reads.load` switch
  are infra §2.16's (lands first); this spec adds the family registration, `name_gate`,
  `mc_system`, `BRMT_*` prompts and the v2 option reader. Used by 6 other families. The regex
  families' scoring is held by infra's `test_regex_families_unchanged`; their MC diagnostic
  `SYSTEM` opening changes (tool-name fix, item 7) with a diagnostic PV bump. **multihop_mt_v2
  and the `mc+regex` families (multilingual, multilingual_multihop) reuse `mc_system` and
  `name_gate`**; no second factory or gate.
  Round 3: `name_gate` step 2 now also tries the space-joined and concatenated `" | "` parts
  of a one-list quote (Q4); this closes multihop_mt.md §6 "one-list multi-word names" and
  reaches mhv2 / multilingual / multilingual_multihop unchanged (no fork). The headline-unit
  choice `BRMT_HEADLINE_UNITS` is brmt-only; the other `mc` / `mc+regex` families keep their
  own unit rules.
- `src/wsbench/readplan.py` (routing + `lite_positions`).
- `src/wsbench/digest.py`: no edit by this spec (all shared wording, cap, variant and verifier
  are infra's).
- `src/wsbench/capable/questions.py` + `tests/golden/capable_questions.json`.
- `src/wsbench/baselines/{lucky_guessing,text_inversion}.py`;
  `evals/baselines/{lucky_guessing,prompt_only_summary,anti_text_inversion}.json`.
- `README.md` (entry + Judges row), `docs/summarizer.md` (`:26` mt families), `docs/read_sites.md`,
  `CLAUDE.md` (shared-judges bullet: "scorer of record is the regex contract" no longer holds for
  this family).
- Tests:
  - new: `tests/test_basic_readout_mt.py`, `tests/golden/basic_readout_mt_options_v2.json`
    (the `test_multitoken_family.py` factory tests are infra's);
  - sanctioned edits: `test_registered` → `test_spec_judge_is_mc_pinned`, and the golden
    `capable_questions.json` entry (deletion of any refusal-asserting test is infra's
    sanction, §2.16);
  - must pass unmodified: `test_mt_regex.py`, the existing tests in `test_multitoken_family.py`,
    `test_ati_panel.py:562-575`. If the shared `SYSTEM` rewrite breaks a golden of a regex
    family's MC prompt, that golden update is sanctioned only for the opening sentence.

Risks:
- The name gate can be too strict for third-language transliterations (e.g. Russian `Тритон` on a
  Hebrew item). Mitigation: `name_miss` is listed and audited. Legit forms are added to v2 before
  the freeze, and the bank is frozen only after the audit.
- Prominence wording ("clearly more prominently") is the main lenient/strict lever on an
  all-position digest. Early question positions will name other candidates. The audit (artefact 6)
  must check specifically for all-position over-hedging (cannot-tell rate by arm vs native lite).
- Qwen gate attrition on question form is unknown. If more than 10 items drop, stop and report.
- The family leaves the macro's current pinned regex instrument. Historic numbers (0.71 etc.) are
  not comparable. The README's Instrument history gets a 2026-10-30 entry.
- ATI stays effectively empty. Note it, and do not force membership (D10).

---

## 7. Implementation record (2026-10-30)

**Bank v2 built and frozen** (`scripts/build_brmt_v2.py`, work files outside the repo; gate record
`evals/basic_readout_mt/gate_v2.json`): 100 v1 items → 99 (60 entity, 39 L2: id 12, ar 6, fi 4,
he 4, hu 4, ko 4, pl 3, ru 2).
- Opus 5.5 drafts (question, `name_forms`, display, 4 distractors), deterministic validator with up
  to 3 re-asks: 100/100 valid (one reviewed exemption, `SHARED_OK`: sarin's same-class distractors
  soman / cyclosarin share "methylphosphonofluoridate").
- Back-translation + blind Opus answer + uniqueness check: 3 flagged, all kept after review
  (wintergreen ester: two valid names, both are forms; Cheng Ho: spelling only; sarin: Opus refuses
  the nerve-agent question).
- Blind floor loop (5 Opus draws per item, options only, judge order): per-draw gold rate
  0.602 → 0.499 → 0.432 → 0.378 → 0.378 → 0.263 → 0.210 → 0.192 → 0.162 over 9 measurements
  (8 redraw rounds; the gate ≤ uniform 0.20 + 0.05 is met). 15 items stay ≥ 2/5 leakers (listed in
  `gate_v2.json`). Frozen lucky floors (readout list): blind 0.171, described 0.359, uniform 0.202.
- Qwen gate (Modal H200, vLLM, `scripts/qwen_sample_modal.py`, chat, no thinking, greedy + 10 @
  T 0.7 / top_p 0.8 / top_k 20): 92/100 at `max_tokens=300`; 7 fails had answers cut at 300
  tokens and were re-sampled at 2000 (6 pass); 2 genuine fails got one Opus rewrite each
  (`brh-ar-tayebsalih` passes; `brh-fi-norsunluurannikko` — Qwen names Nigeria — dropped).

**Deviations from the spec above** (each also in the PR body):
1. Item 7 blind-floor loop: 8 redraw rounds, not 3 (3 left the floor at 0.378); the redraw prompt
   tells the redrawer the guesser picks the best-known entity. Distractors named in the question
   (`brh-he-ben-zvi`: Chaim Weizmann; `brh-ent-mayor-palace`) are redrawn too.
2. Validator "shares the gold's distinctive name word": implemented as "holds every distinctive
   word of some answer form" (a shared class word — salt, unit, spar — is allowed; a shared
   surname is not), because the literal rule rejected every natural same-class distractor list.
3. Lucky guessing for this family runs over the `readout` list only (the headline unit); its
   `described` sentence is "which specific name a factual question asks for".
4. Name gate step 2 also tries the Cyrillic / Greek romanization of each candidate (fixed table:
   `Тритон` → `triton`; E1's L32 readout writes the name only in Cyrillic).
5. `translated_pass_rate` removes the source-language names (`target` / `target_alts`) from the
   native-language form lists before matching (Opus listed "Ahvenanmaa" under `en`).
6. The `language` unit is not name-gated (its evidence may be the question's own language); only
   `digest.quote_ok` verifies its quote.
7. Pre-existing tests the spec said must pass unmodified could not, because item 1 makes
   basic_readout_mt LLM-judged: `test_mt_regex.py` (the two regex-CLI toy tests drop this family),
   `test_multitoken_family.py` (the MC-diagnostic dry run drops it; infra's multi-position test
   gets a fake LLM for LLM-judged families, no assertion change); plus the family PR's own list
   edits in `test_prompt_tool_names.py` (7 mt families leave the pending list),
   `test_ati_fingerprint.py` (`CHANGED_BY_FAMILY_PRS`) and `test_refilled_banks.py`
   (`REGATE_IN_RUN_PHASE`: the v1 ATI entry is stale until gpu R8).
8. `wsbench.adapt` (other subject models) still authors completion prompts for this family; an
   adapted bank keeps the v1 completion route in `readplan` (render plain, final token).
9. The plan number is 0051 (0033–0036 were taken by open campaign PRs).

**Cached-case re-judge (E1–E8; "cached v1 readouts, judge test only", `reads=lite`,
`reads_checked=no_sidecar`, `sampling_source=override`)**: before = the v1 bank's regex
instrument (native), after = this instrument (summary mode, the default):
E1 neptune-moon FAIL → PASS (`**Тритон** (Triton)`); E2 ahvenanmaa FAIL → PASS
(`**Åland**`, translated True); E3 petsamo FAIL → PASS (`"Petsamo corridor"`); E4 sungai-kapuas
FAIL → PASS (`**Sungai Kapuas**`, translated False); E5 beckwith-wiedemann PASS → FAIL (cannot
tell); E6 tambora (J-lens) FAIL (cannot tell; v1 audit PASS came from the deleted interp-v1
step); E7 hafsid (J-lens) FAIL (`Haf` → `name_miss`); E8 bengkulu FAIL in summary, PASS natively
at L28 (`city of Bengkulu`; L20 picked the distractor Padang) — for the leniency audit.

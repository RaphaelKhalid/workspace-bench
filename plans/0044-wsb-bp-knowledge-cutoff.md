# 0044 — WorkspaceBench fix campaign: knowledge_cutoff

Status: implemented in this PR (camila/wsb-bp-knowledge_cutoff), on top of the merged infra
(plan 0032, `34005ac`). Campaign source of truth: `/workspace/root/wsb-bp/plans/knowledge_cutoff.md`
(copied verbatim below the line), `SHARED_API.md` and `_fable_decisions.md`. The spec's `C1`..`C9`
labels are cited in code comments as `plan 0044 §Cn`.

## What the implementation decided where the spec left room (deviations)

1. **Near-alias scan** (`scripts/kc_near_aliases.py`): 17 candidates on 5 items (the spec quoted
   "14 on 5" from a scratch run; the extra three are the `O1`/`O3`/`O4` bare forms beside the
   `OpenAI oN` ones). Every one has a frozen verdict; 5 accepted (cs01684 `A321`, `Airbus A321`,
   `空客A321`, `空中客车A321`; kc3_01462 `geely panda`). **kc3_01462 is a frozen (refill) item, not
   a nocot item**, so its addition sits in the frozen item's `option_units` and the header's
   `near_alias_additions` is `{}` (the merge path in `judge.load_items` exists and is unused).
2. **Dash marker**: `score.NOTE_MARK`'s spaced em / en dash ends the answer head only when the
   text before it is at most 6 words (`DASH_HEAD_MAX_WORDS`). Without this, ML-NLA's descriptive
   prose ("Genre: a QA task — …") lost its head at the first dash: the cached-answer replay
   dropped 133 G2 + 35 G1 ML-NLA hit cells instead of the spec's 63 + 6.
3. **Equal values** ("999.00" for option 999) never contradict the pick (G1, as the spec's test
   says) but are not support either: only a listed form, or a CJK / Roman / word numeral of the
   same integer, presents an option. (An equal-value support rule let cs00531's "$10.00$
   (Confidence: 100%)" count as a second "10".)
4. **`answer_kinds`** keeps the old hit / wrong / none / unverified partition (a verified pick is
   `hit` only when it passes every gate) and adds `gated` (verified picks a gate failed), so the
   pre-existing assertion in `test_ati_pass_is_gold_pick_or_any_mention` holds unchanged.
5. **Token picks** keep the quote-less path (a list naming the pick under the token rules, or a
   one-word spelling across adjacent positions of one layer); support counts only lists that name
   exactly ONE option (the shared Q4 rule), and a numeric item's number-flood list counts nothing.
6. **E9 (cs00047 L48)**: the cached bullet literally ends "…boost clock of 5.7" (a truncated
   generation), so the boundary check passes and G1 drops it (its head is `5.75`); `gate_drops`
   records `contradicted`, not `boundary`. `test_truncated_number_quote_fails` covers the boundary
   case itself.
7. **CJK numerals** credit an integer option in prose only as a run of >= 2 characters (incl. a
   `第` prefix), so a lone unit such as 百 in 百度 is never a number; token rows take any run.
8. **Sidecar-less files are not trimmed** by infra's `reads.load` (it records what the declared
   rule would trim), so the spec's planned `sampling=bullet4` override on the fixture tests is not
   needed and was not added.
9. **ATI**: the frozen entry is stale (bank sha and instrument moved) until gpu R8 re-judges the
   cached panel answers (the spec's schedule); `anti_text_inversion=True` exits 2 for this family
   until then. Tests follow the `REGATE_PENDING` pattern of the wrong_bridge PR.
10. `test_summary_bundles_every_loaded_line`: 2 items x 3 layers x 30 positions x 4 samples is 360
    lines per item (720 in total); the spec's "720 per item" was an arithmetic slip.

## Pre-existing test assertions changed (each listed with its reason)

- `tests/test_knowledge_cutoff.py`
  - `test_example_readouts_pass_at_the_bank_layer`: `config["positions_regime"] == "all"` (retired
    name) -> `config["reads"] == "full" and extras["positions_per_cell"]["min"] == 4`. The spec's
    sanctioned form (`partial_ids_unenforced == []`) cannot hold: infra's guard (ii) runs
    report-only on the sidecar-less 2-layer fixture and lists both ids as missing plan layers.
  - `test_quote_must_be_verbatim_in_one_sample_and_name_the_pick`: fixture gains a second gold
    sample (G2, sanctioned) written `麒麟9100` instead of the spec's `Kirin 9100`; the case
    `"Kirin\n9100" -> False` becomes `"the Kirin 9100 is my guess" -> False`, because
    `digest.quote_ok` folds whitespace and the old quote is now verbatim inside "The Kirin 9100.".
  - `test_off_plan_positions_are_ignored`: the off-plan sample becomes `"OFFPLAN Kirin 9100"` and
    the assertion checks `"OFFPLAN"` is never sent, since the menu now legitimately lists
    `HiSilicon Kirin 9100` (C6).
  - `test_legacy_three_site_file_is_scored_but_never_complete`: sanctioned edit (sidecar +
    `allow_missing`, second pos −1 sample, `set(extras.partial_ids) == {A, B}`).
  - `test_partial_layer_run_uses_its_own_layer`, `test_token_cells_are_one_sample_per_position`:
    sanctioned fixture edits only.
- `tests/test_summary_mode_introspection_kc.py`: `test_kc_one_call_per_item_no_layer_pick_no_ati`
  and `test_kc_partial_comes_from_the_real_cells`: the sanctioned edits.
- `tests/test_knowledge_cutoff_nocot.py`: `test_judge_reports_by_source` fixture (gold at −2 and
  −1, G2); `test_ati_entry_is_offline_and_current` gains the stale-entry branch (offline lookup
  must refuse with "re-gate" until R8; 147 items).
- `tests/test_refilled_banks.py`: `N0` 148 -> 147, `ITEMS_JSON` 109 -> 108 (sanctioned), `_bank`
  reads the registered bank (v2), `REGATE_PENDING = {"knowledge_cutoff"}`.
- `tests/test_ati_fingerprint.py`: `CHANGED_BY_FAMILY_PRS = {"knowledge_cutoff"}`.
- `tests/test_mc_cannot_tell.py`: knowledge_cutoff leaves `PENDING_FAMILY_PR`; `_last_option`
  reads its rendered menu (last line `mc.KC_NONE`).

## Evidence (cached v1 readouts, judge test only)

`/workspace/root/wsb-bp/evidence/knowledge_cutoff_data/`: `gate_replay.json` (old answers, new
gates, no calls) and `rejudge_summary.json` (12 + 1 native Opus re-judges of the audited cases).

---

# Workstream spec: knowledge_cutoff

Scope: the "Knowledge cutoff" section of `notes/feedback.md` (six sentences), plus the campaign
decisions as they apply to this family. Code of record: `/root/wsb-bp-base` at `cd6b0fa`. Every
`file:line` below refers to that tree. No API, judge or GPU call was made for this spec.

**Round 1 revision (2026-10-30).** Aligned to `plans/SHARED_API.md` (names and signatures used
verbatim; no shared machinery re-implemented here), to the binding `plans/_fable_decisions.md`
(Q1 sampling, Q4 combining, Q8 KC aliases + nocot licence, lite, versioned banks, ATI, spend),
and to every `_critique.md` item that names KC (1, 2, 3, 4, 7, 10, 11, 19, 23, 32, 34) or that
binds every family (8, 16, 18, 26). Changes are logged in `plans/_resolution_log.md`.

**Round 2 revision (2026-10-30).** Re-aligned to the round-2 `SHARED_API.md` and to
`_critique_r1.md` items 3 (`digest.number_flood` prose = list-shaped runs only; `numerals`
module), 7 (the shared G12/R4b leniency audit replaces KC's own re-audit protocol) and 8
(J-lens and ML-NLA are required campaign arms; cached-readout evidence is labelled "cached v1
readouts, judge test only"). Also applied the round-2 shared rules that touch KC: sidecar-only
enforcement of `check_full` (sidecar-less files are report-only), the full-read guards (i)-(iii),
the options-relative flat-list rule with `EvalSpec.flat_types`, `mc.token_note(flat_types)`,
`digest.statement_lines` as the one bullet splitter, the named-restatement digest rule, and the
prompt-only floor rule (own headline, own CI, n = judged − refused, > 20% refused →
`not_measurable`, never per read position).

**Round 3 revision (2026-10-30).** Re-aligned to the round-3 `SHARED_API.md` and to
`_critique_r2.md` item 4 (the only item naming KC): `digest.number_flood` is now called on the
WHOLE sample Line (never on a `digest.statement_lines` bullet, which raises `ValueError`), so an
s3d bulleted number list (`12 ⁞ 15 ⁞ 17 ⁞ 19 ⁞ 23`) is a flood and gives no support (C5). Also
applied the round-3 shared rules that touch KC: `digest.BULLET_MARK` (`" ⁞ "`) in the rendered
lines the judge sees (C3 rule 2, C4 tests), `mc.token_note(SPEC.flat_types,
multi_select=SPEC.multi_select)` (KC `multi_select=False`), `extras.n_unverified_bullet` (C4),
"add, never relax" (C3 rule 4), `results.MACRO_METRICS` / `not_in_macro=""` (C8), the R4c
fix-and-rerun loop and R6 floor timing (C8, E12), the r3 ATI re-gate rule (C8), the
`--strata` option (E12: none declared) and the lite-site procedure (KC not in it; C2.1).

The offline numbers in §2 C5/C7 and §4 come from a read-only replay of the new mechanical rules
over cached judge answers (scratch scripts `/tmp/kcreplay/replay.py`, `/tmp/kcreplay/replay_prose1.py`,
`/tmp/kcreplay/jl.py`). The cached runs were
`/workspace/root/wsb-summ-out/d3/d3a-{s3d,mlnla2k,jlens}-all-native/knowledge_cutoff/cells.jsonl`,
with readouts from `/workspace/root/wsb-ati-runs/readouts/{s3d,mlnla2k,jlens}/cutoff_confab.jsonl`
and the bank `tests/fixtures/knowledge_cutoff_pre_refill_items.json`.

---

## 0. Coverage map (Camila's sentences → change → test → evidence)

| # | Camila's sentence (feedback.md:217-222) | change | named test(s) | evidence |
|---|---|---|---|---|
| S1 | "Fix: Bank hygiene: one current item (cs01301) has the answer 'not traded' and an option that's a long refusal sentence, contradicting the README's claim that refusals are excluded." | C1 | `test_bank_v2_has_no_null_or_refusal_options`, `test_v2_is_v1_minus_cs01301_plus_aliases`, `test_registered_bank_is_v2` | E1 |
| S2 | "Make sure the readouts are taken at all positions and all layers" | C2 | `test_plan_every_position_every_grid_layer`, `test_full_requires_contiguous_span`, `test_kc_sidecarless_legacy_file_is_report_only`, `test_summary_bundles_every_loaded_line`, `test_layers_arbitrary_summary_and_native` | E2 |
| S3 | "Fix the too lenient cases and the too strict cases" | C3 (umbrella; table maps the 10 audit cases to C4-C7) | the C4-C7 tests | E3-E9, E12 (KC row of the shared G12/R4b audit table) |
| S4 | "Answer-vs-explanation confusion in 'number then note' readouts. The judge counts numbers inside explanatory notes as answers" | C4 | `test_answer_head_markers`, `test_note_number_never_verifies`, `test_equal_value_is_not_a_contradiction` | E3 |
| S5 | "Weak or only-option evidence wins. There is no minimum support: when the gold is the only option string that appears, one passing mention ('e.g. \"128k\"', a rank-17 token) is picked even amid many non-option answers. Numeric items with scattered numbers give chance hits." | C5 (G2 min support, G3 numeric plurality, `digest.number_flood`, `flat_types`, tokens10 cut) | `test_min_support_single_mention_fails`, `test_number_flood_line_gives_no_support`, `test_kc_worked_prose_is_not_flood`, `test_kc_bulleted_number_list_gives_no_support`, `test_kc_flood_is_called_on_whole_sample`, `test_numeric_plurality_gate`, `test_tokens10_drops_rank_17` | E4, E5, E6 |
| S6 | "Alias mismatch. The menu shows only canonical option text, verification accepts option_units aliases, and the judge refuses near-aliases (Aruba Networks vs 'aruba networking'; A321 vs 'a321neo')." | C6 (aliases shown in the menu; Q8 near-alias additions incl. A321 ⇔ a321neo) | `test_menu_shows_every_accepted_form`, `test_near_alias_a321_credits_a321neo`, `test_near_alias_additions_are_unambiguous` | E7 |

---

## 1. Current state

### 1.1 Bank
- `evals/knowledge_cutoff/items.json` (sha256 `bf344c1b…4bf1`) holds 109 frozen items
  (`family: "cutoff_confab"` in the header; stratum A 97 / B 12; label_mix stale 55 /
  confab_plausible 52 / confab_weird 2). It also holds `g3_leak_items` (6, never scored),
  `retired_panel_gate` (67) and `refill_panel_gate`. `contract` is a dict (`contract.gates.G0` …).
- `evals/knowledge_cutoff/obscure_items.json` (sha256 `f7f35a6c…61ab`) holds 39 ids-only nocot
  items (gold, options and `option_units` keyed by nocot id; no question text). The question
  text is fetched from nocot's pinned zip at plan time only (`nocot.OBSCURE`, `src/wsbench/nocot.py:16`).
- `judge.load_items` (`src/wsbench/evals/knowledge_cutoff/judge.py:53-61`) merges the two: 148
  scored items. Each item has K = 5 options in a seeded order, plus `option_units` (alias forms
  per option).
- The README claims "Refusals and null labels are excluded" (`evals/knowledge_cutoff/README.md:52`).
- **Defect: cs01301.** Gold is `not traded`. Option E is the 153-character refusal sentence
  "this is a trick question! mikko rantanen has never played for the carolina hurricanes. …"
  (source `legacy:gemma`). Qwen's greedy answer was "Mikko Rantanen was not traded." (8/10
  agree). That is a null label, which G0 says it excludes (header `contract.gates.G0`: "not null
  (0/none/no club...)"). The item is in the ATI subset (`status cs01301 = [solved, failed, failed,
  failed]`).
- I linted both files for null/refusal options (`not traded|none|no club|unknown|trick
  question|cannot|never|n/a|does not exist|did not|has not|refus`, option length > 60, option
  `"0"`). **cs01301 is the only hit.** Every other option is at most 45 characters.

### 1.2 Read plan (positions, layers)
- `readplan._plan` gives knowledge_cutoff `{"kind": "all_from_end"}` and `GRID` (L20-60 step 4,
  11 layers) for the frozen items (`src/wsbench/readplan.py:380-394`) and for the nocot rows
  (`readplan.py:650-672`).
- `all_from_end` means every token of the chat render, as negative offsets −n..−1
  (`readplan.py:74`, `:134`). gpu.md §1.3 measured 73,810 cells for the 109 frozen items with the
  Qwen tokenizer (≈ 61.6 positions per item). −1 is the `\n\n` after `</think>` (reply_start), −2
  is `</think>`, and −10 is the last user-content token.
- **So the plan already asks for all positions × 11 layers.** No cached run reads that, though:
  - every cached readouts file is the legacy three-site file (−10, −2, −1): 3,795 rows / 115 ids
    for s3d, `positions_per_cell` min = median = max = 3;
  - every cached result is marked partial, `complete: false`;
  - all of them predate the ATI refill: 109 rows, of which only 42 ids are in the current bank,
    and none of the nocot items. Source: audit `families/knowledge_cutoff.json` → `positions`,
    `results_seen`; `/workspace/root/wsb-summ4-out/d3c-s3d-all-summary-v3/knowledge_cutoff/results.json`
    (`n_partial_cells: 1199`).

### 1.3 Judge (native, now opt-out)
- One MC call per (item, layer) carries every position's samples (`judge.py:158-190`). Prompts
  are `SYSTEM` (`prompts.py:16-34`) and `USER` (`prompts.py:36-43`). The menu lists the 5
  options lettered A-E (`prompts.py:101-102`). The schema `answer` enum is `[A-E, NONE]`
  (`prompts.py:80-88`).
- NONE is the abstain: "If no sample presents any option as the answer, answer NONE"
  (`prompts.py:33`). It is not a menu line.
- The judge never sees the question, the gold or the truth (`prompts.py:91-98`; test
  `test_every_position_lands_in_one_call_in_order_without_prompt_text`).
- **Verification** (`judge.py:91-112`). A prose pick is verified when the quote is verbatim in
  ONE sample (`family.quote_in`, `src/wsbench/family.py:58-62`) and the regex forms of
  `score.OptionForms` name the pick inside the quote. A token pick is verified when the forms
  name it in some row's space-joined bag. `compile_form` drops CJK-numeral forms
  (`score.py:40-41`), and there are no Roman-numeral or number-word forms. CJK aliases are
  matched as substrings.
- hit = (pick == gold) AND verified (`judge.py:196`). The native headline is the bank-wide best
  layer (`score.best_layer`, `score.py:120-124`; `judge.py:206-207`).
- `ati_pass` is the gate-only looser rule: the pick is gold ignoring verification, OR a pos −1
  regex mention (`judge.py:225-229`).
- `full_span` (`judge.py:84-88`, `:257-259`) requires the offsets to be exactly −n..−1 with
  n ≥ `MIN_POSITIONS = 4` (`judge.py:45`). Otherwise the result is `complete=False`
  (`judge.py:322-323`), never an exit.

### 1.4 Summary mode (the default since plan 0024)
- `_run_summary` (`judge.py:355-539`). Every present (item, layer) cell's positions go to ONE
  digest per item (`digest.collapse`, `judge.py:384-393`; `task_note=DIGEST_TASK_NOTE`). Then
  there is ONE judge call per item, `SYSTEM_SUMMARY` plus `USER_SUMMARY` (`prompts.py:47-61`).
  There is no layer pick.
- Verification is against the digest's evidence samples (`summary_verdict`, `judge.py:327-352`).
- Today's stamp (cd6b0fa, recorded as a fact, not a target) is the blind / digest-v3 / sj-v7 one;
  `test_kc_one_call_per_item_no_layer_pick_no_ati` pins its prefix.
- KC has no `digest.FAMILY_DEFAULTS` entry (`src/wsbench/digest.py:181-200`), so it gets
  `summ_max=10`, `summ_rare=15`, and the blind variant (the task note is never sent, `digest.py:34`).
- `docs/summary_mode_validation.md:64` measured KC digest coverage at 0.42 (10 items) vs 0.65
  (25 items), the lowest of any non-saturated family except DMO and introspection.

### 1.5 Layers
`layers = args.layers if args.layers is not None else head_layers` (`judge.py:132`). Any subset
works, and nothing hardcodes a layer. The only layer-specific logic is the native best-layer pick.

### 1.6 Floors and baselines that exist today
- **There is no KC entry** in `evals/baselines/prompt_only.json`, in `prompt_only_summary.json`
  or in `lucky_guessing.json` (checked key lists). KC is not in `lucky_guessing.BUILDERS`
  (`src/wsbench/baselines/lucky_guessing.py:245-260`).
- The only text-only numbers are the regex-era Baseline C 0.486 (README:20-24) and the ATI panel
  pass@3 under the looser `ati_pass`: Qwen 0.37, Opus 0.31, Argon 0.28, Astra 0.01
  (`anti_text_inversion.json`).
- `CHANCE_LABEL` (`judge.py:46-50`) quotes regex-era, pre-refill floors.

### 1.7 Prompt tool names (D5)
- KC's own prompts are already neutral ("its internal activations were decoded"). The shared
  `SUMMARY_NOTE*` say "the lens's readouts" (`digest.py:107-125`); infra §2.8 rewrites those.
- KC's `PROMPTS` dict (`prompts.py:68-78`) feeds `tests/test_prompts_in_readme.py`.

### 1.8 Sampling in the cached files (for D7 / Q1)
- s3d cached cells hold 5 generations (≈ 362 chars each); ML-NLA 5 (≈ 661 chars); J-lens 20
  tokens. Under Q1 the campaign arm **s3d-rl600 is `prose1`**: ONE generation per activation
  (multi-bullet, k=1), never split into bullets. ML-NLA is `prose1`. J-lens is `tokens10`.

---

## 2. Change list

KC stamp after this workstream: `PROMPT_VERSION = "cutoff-judge-2026-10-30"`. Every result
stamp is `reads.stamp(digest.prompt_version(PROMPT_VERSION, args, "knowledge_cutoff"),
reads.mode(args))`; this spec writes no digest or sj literal (infra owns `digest-v4` / `sj-v8`).
All new tests go in `tests/test_knowledge_cutoff_v2.py` unless named otherwise.

### C1. "Fix: Bank hygiene: one current item (cs01301) has the answer 'not traded' and an option that's a long refusal sentence, contradicting the README's claim that refusals are excluded."
- **New bank file `evals/knowledge_cutoff/items_v2.json`** (infra §2.12 naming rule).
  `items.json` stays byte-identical.
  - Header: everything from v1 is kept, `contract` dict verbatim (provenance). Add `version: 2`,
    `supersedes: "items.json"`, `n_items: 108`, and
    `changes: ["cs01301 retired: null label 'not traded' (G0 excludes null labels) and a refusal-sentence option", "near-alias forms added per Q8 (see near_alias_review)"]`.
  - Recompute `label_mix` → `{stale: 55, confab_plausible: 51, confab_weird: 2}` and `strata` →
    `{A: 96, B: 12}`.
  - Recompute `g1_conditional_floor` with the v1 formula (mean 1/(K−u) over the 108 items) and
    record it.
  - Move cs01301 out of `items` into a new list `retired_hygiene: [{...item, "reason": …}]`.
  - The Q8 near-alias additions (C6) are applied to the frozen items' `option_units` in place,
    and recorded for both sources in `near_alias_review` (C6). `obscure_items.json` stays
    byte-identical: its additions live in the v2 header's `near_alias_additions`
    (`{item_id: {option: [forms]}}`), which `load_items` merges into the nocot items' units.
    No `obscure_items_v2.json` is created.
  - `contract.native_langs` is not added: `banks.native_langs(header)` defaults to `("en", "zh")`,
    which is KC's set (its CJK forms are Chinese).
- **Not refilled.** A replacement would need G0 (Qwen ×10 on GPU), G1 (Opus/Sonnet) and the
  panel gate. Camila's rule elsewhere is "we should just get rid of them". Scored family = 108 +
  39 = **147**.
- **Bank selection (infra §2.12; critique 7).** `knowledge_cutoff.SPEC` sets
  `bank=Path("evals/knowledge_cutoff/items_v2.json")`; `registry.bank_path("knowledge_cutoff")`
  returns it. `WSB_BANK_FILE_KNOWLEDGE_CUTOFF` and `WSB_BANK_ROOT` still take precedence, so the
  pre-refill fixture tests and adapted banks keep working. `judge.load_items`,
  `readplan._bank` (`readplan.py:228-236`) and `baselines/text_inversion._kc_items`
  (`src/wsbench/baselines/text_inversion.py:994-1006`) already go through `bank_path`. If infra's
  `test_no_hardcoded_items_json` scan flags `nocot.OBSCURE`, it becomes
  `bank_path(NAME).parent / "obscure_items.json"` (no behaviour change for the repo bank).
- **README** (`evals/knowledge_cutoff/README.md:33-53`): "108 frozen items (v2; cs01301 retired
  for a null label, see `retired_hygiene`)". The claim "Refusals and null labels are excluded"
  becomes true, and a lint test enforces it.
- **Tests:**
  - `test_v1_bank_unchanged`: sha256 of `items.json` is `bf344c1b…`, of `obscure_items.json`
    is `f7f35a6c…`.
  - `test_registered_bank_is_v2`: `registry.bank_path("knowledge_cutoff").name == "items_v2.json"`,
    header `version == 2`, and `len(judge.load_items()) == 147`.
  - `test_bank_v2_has_no_null_or_refusal_options`: the §1.1 lint over v2 and
    `obscure_items.json`; also gold ∈ options, set(option_units) ⊇ options, and
    `label_mix`/`strata` match the header.
  - `test_v2_is_v1_minus_cs01301_plus_aliases`: every other item is equal to v1 except the
    `option_units` additions listed in `near_alias_review` (which are a strict superset of v1's
    units).

### C2. "Make sure the readouts are taken at all positions and all layers"
1. **Plan (no change, now pinned by a test).** It stays `all_from_end` × `readplan.GRID`, frozen
   and nocot alike.
   - Every KC plan row carries `ReadSpec.lite_positions = {"kind": "final_token"}` (pos −1,
     reply_start; the audit puts the signal there at late layers) and `ReadSpec.lite_layers =
     None` (lite keeps the full layers). KC is not in the pre-registered lite-site procedure
     (SHARED_API: association, conjunctive, role_bound only); its lite site is fixed at
     `final_token` and no pass rate is used to choose it.
   - `readplan.plan("knowledge_cutoff", layers="all")` gives all 64 layers; an explicit list is
     used verbatim (infra §2.1).
2. **Loading and completeness (infra §2.0, §2.6; critique 2, 3).**
   - `judge.run` and `_run_summary` call `reads.load(args, "knowledge_cutoff")` where they call
     `load_readouts` today. KC does no sidecar reading, normalising, lite filtering or span
     checking of its own.
   - KC's `full_span` and `MIN_POSITIONS` are deleted. `knowledge_cutoff.SPEC` sets
     `min_full_positions=4` and `full_contiguous=True`, so `reads.check_full` requires, per
     (item, layer), one contiguous run ending at the max position, of length ≥ 4 — the same
     predicate `full_span` encoded (−n..−1, n ≥ 4).
   - `reads=full` (default), **file with a sidecar** (every campaign file; `config.reads_checked
     = "sidecar"`): a file whose every cell holds one position exits 2 ("looks like a lite
     file"); a sidecar `reads: "lite"` exits 2 (guard i); a missing plan layer under no
     `layers=` is a violation (guard ii); a sidecar `plan_sha` ≠ `reads.plan_sha("knowledge_cutoff")`
     exits 2 even under `allow_missing` (guard iii). Any position or layer violation exits 2
     unless `allow_missing=True`, in which case those items are in `extras.partial_ids` and
     `complete=False`. A file with more layers than the plan (`layers=all`, 64) is fine.
   - `reads=full`, **sidecar-less file** (cached v1 readouts, pre-existing synthetic fixtures):
     the same check runs report-only — offending ids go to `extras.partial_ids_unenforced`,
     `config.reads_checked = "no_sidecar"`, nothing exits, `complete` is not changed by it
     (infra §2.6 "When `check_full` and (ii) enforce"). Such results are never campaign results
     (gpu G9 fails `reads_checked != "sidecar"`). **Behaviour change**: KC's old `full_span`
     marked a legacy three-site file `complete=False` by itself; now that needs a sidecar
     (+ `allow_missing=True`), and a sidecar-less legacy file reports its ids as unenforced
     (documented in the README and §6).
   - `reads=lite`: `reads.select` keeps pos −1 only; the run is complete when every (item, layer)
     has its −1 row; the stamp gets `+reads-lite` via `reads.stamp`; `config.reads` is stamped by
     `mcjudge.base_config`.
   - The cached legacy files are therefore usable as **lite** files (they hold −1) and, under
     full, are report-only with all their ids in `partial_ids_unenforced`.
   - Prompt-only files (`reader: prompt_only:*`) are waived by `reads.load` (infra §2.6.6); KC
     adds nothing for them.
3. **Every loaded readout reaches the summarizer (D1).**
   - `_run_summary` passes every present cell of every layer to
     `digest.collapse("knowledge_cutoff", by_item, args=…, cache=…, spend=…, preflight=…,
     task_note=prompts.DIGEST_TASK_NOTE, expect_all=cells)`.
   - Overflow is the global hierarchical default above `digest.DEFAULT_TOKEN_CAP` (920,000); KC
     sets no cap.
   - Size check on cached data under Q1: s3d-rl600 `prose1` = one ≈ 362-char generation (≈ 90
     tokens) per activation, so ≈ 62 pos × 11 L × 90 ≈ 61k tokens per item; ML-NLA `prose1`
     (661 chars, ≈ 165 tokens) ≈ 112k. Both are one digest call. `layers=all` (64 layers) is
     ≈ 360k / 650k, still under the cap; hierarchical chunking only above it, never dropping a
     line (`extras.n_readouts_in == n_readouts_bundled`).
4. **Layers.** No change in the judge. `layers=each` writes `out/knowledge_cutoff/L<k>/` plus
   `all/` (infra §2.1.6), which is Camila's "11 single-layer O-lens runs". A `layers=` run is
   complete when every requested layer is present (infra §2.1.7, `mcjudge.is_subset`).
5. **Sampling (Q1, infra §2.9; critique 1).** The kind comes from the sidecar `sampling` declared
   by the producer, never from bullet shape. `readouts.normalize` (called by `reads.load`):
   - s3d-rl600 (`prose1`): the one multi-bullet generation stays ONE sample per activation;
   - a single-bullet `*-x4` arm (`bullet4`): 4 separate samples per activation;
   - ML-NLA (`prose1`): 1 sample; J-lens (`tokens10`): the top 10.

   Update the `Size` paragraph (`README.md:154-156`) and `calls_per_arm` (`__init__.py:24-25`):
   147 digests + 147 judge calls per arm in summary mode, 147 × 11 in native.
6. **Tests:**
   - `test_plan_every_position_every_grid_layer`: for every plan row,
     `positions == {"kind":"all_from_end"}`, `layers == readplan.GRID`,
     `lite_positions == {"kind":"final_token"}`, `lite_layers is None`, frozen and nocot rows
     (nocot text stubbed as in conftest). (Infra's `test_every_plan_row_has_lite_positions` and
     `test_lite_is_subset_of_full` also cover KC.)
   - `test_full_requires_contiguous_span` (every file written with
     `tests/conftest.py::write_sidecar(path, reads="full", sampling="prose1", reader="s3d-rl600",
     layers=[...])`): a −4..−1 file over the plan layers is complete; a −10/−2/−1 file exits 2,
     and under `allow_missing=True` scores with both ids in `extras.partial_ids`,
     `complete=False`; a −1-only file exits 2 with the lite message; a sidecar `reads="lite"`
     file exits 2 under `reads=full`; a sidecar with a wrong `plan_sha` exits 2 even with
     `allow_missing=True`.
   - `test_kc_sidecarless_legacy_file_is_report_only`: the same −10/−2/−1 file with no sidecar
     does not exit; `config.reads_checked == "no_sidecar"`, both ids in
     `extras.partial_ids_unenforced`, `extras.partial_ids == []`.
   - `test_layers_arbitrary_summary_and_native`: synthetic cells at `[3, 17, 44]` and at `[44]`.
     `config.layers_judged` equals the input, and the summary bundle has exactly those
     `[L.. pos ..]` headers.
   - `test_summary_bundles_every_loaded_line`: 2 items × 3 layers × 30 positions × 4 samples
     (sidecar `sampling: bullet4`); the fake digest sees all 720 lines per item.
   - `test_s3d_prose1_is_one_sample_per_activation`: a sidecar `sampling: prose1` cell with one
     4-bullet generation renders as one `- ` line and counts as 1 toward G2 (C5).
   - `test_reads_lite_selects_reply_start`: a full-span file under `reads=lite` judges −1 only,
     `config.reads == "lite"`, `complete`, stamp ends `+reads-lite`.
   - `test_full_on_lite_file_exits_2` (sidecar `reads="lite"`).

### C3. "Fix the too lenient cases and the too strict cases"
This is the umbrella sentence. The concrete fixes are C4 (answer vs explanation), C5 (minimum
support), C6 (aliases) and C7 below (token-lens and boundary verification). The audit's
non-agree cases (4 lenient, 5 strict, of 49 reviewed, plus the ambiguous ones listed) map to them:

| audit case | verdict | fixed by |
|---|---|---|
| cs00166 L60 s3d: picked 128000 from notes, gold 131072 leads 3 bullets | too strict | C4 prompt rule + C5 G3 (128000 would fail numeric plurality) |
| cs00808 L60 J-lens: "Christie" top token, unverified | too strict | C7 first-piece rule |
| cs01623 L60 J-lens: XIX / 十九 / 第十九 for 19, unverified | too strict | C7 numerals |
| cs00531 L32 s3d: lone "10" among ~20 numbers | too lenient | C5 G2 (support 1 < 2) + `digest.number_flood` |
| cs00167 L20 ML-NLA: "e.g. \"128k\"" | too lenient | C4 head rule + C5 G2 |
| cs01524 L48 J-lens: " Jupiter" at rank 17 in a "none" bag | too lenient | tokens10 (rank 17 dropped by `readouts.normalize`) + C5 G2 |
| (4th lenient case: one more single-mention hit; `systematic_issues[1]`) | too lenient | C5 G2 |
| cs00312 L56: "Aruba Networks" refused vs `aruba networking` | ambiguous | C6 forms shown in the menu |
| cs01684 L40: "A321" refused vs `a321neo` | too strict (Q8) | C6 near-alias addition, shown in the menu |
| cs01809 L52: refusal frames + "begins samples" heuristic | ambiguous | C4 refusal/denial rule; the "begins samples" heuristic is named as invalid |
| cs01301 summary: null gold | ambiguous | C1 (item retired) |

The **new prompts** (C4-C6) replace `SYSTEM` / `USER` in `prompts.py:16-43`.
`SYSTEM_SUMMARY` / `USER_SUMMARY` keep being derived by `.replace` from them
(`prompts.py:58-61`; the replaced anchors `SUMMARY_INPUT_OLD` and `READS_OLD` stay verbatim in
the new text).

```text
SYSTEM =
A language model was asked a short factual question and told to answer with just a short answer
(a name or a number). While it read the prompt, its internal activations were decoded at every
token position: the readouts below are grouped by position, from the start of the prompt to the
last token before the model's reply, and each sample is one noisy description of what the model
represents at that position. You do NOT see the question. Your job is to decide which option the
model is about to give as its answer, using only what the readouts say.

Rules:
- Only a sample that presents an option as the model's answer, guess or belief counts. Naming an
  option while restating the question, as an example ("e.g."), inside a question the readout
  invents, while saying it does not exist or did not happen, or while refusing to answer is NOT an
  answer.
- Many samples have the form "<answer> <note>": a short answer followed by a note, comment,
  explanation or correction (in parentheses, after "Note:", "//", "#", or a dash). Only the
  leading answer is that sample's answer. An option or number that appears only inside the note is
  not an answer, even when the note calls it the true or current value. A sample made of several
  bullets is shown as "- a ⁞ b ⁞ c" (each "⁞" ends one bullet and starts the next); this rule
  applies to each bullet, and a quote must lie inside one bullet.
- An option counts when a sample writes it or one of the forms listed for it in the options
  menu. A related but different name or version that is listed for no option (another model of
  the same family, a broader product line) does not count for any option.
- The answer must stand out. Weigh how many samples, across all positions, present each option as
  the answer, and choose the one the readouts most consistently put forward. A single passing
  mention does not outweigh a consistent one. Being the only option that appears is NOT enough:
  if the samples give many different answers, most of them not among the options, and an option
  is presented only once among them, it is not singled out. A sample, line or token list that
  holds two or more of the options, or that is a run of many numbers or dates, singles out none
  of those options, whatever their order or rank. An option that is the only option in a line
  is singled out by that line, even if the line holds other names of the same kind, unless the
  line is a run of many numbers or dates.
- Which option a sample happens to begin with, or where it sits in a sample, is not evidence by
  itself; only how a sample presents the option is.
- Do NOT answer the question yourself and do not use your own knowledge of what the true answer
  is: the model may well be wrong, and only what the readouts present matters.
- If no option is singled out as the answer, answer NONE (cannot tell from the readouts). That is
  a normal answer.
{token_note}

USER =
=== ACTIVATION READOUTS (by position) ===
{reads}

=== OPTIONS ===
{menu}

Which option is the model about to give as its answer? Give three fields:
`reasoning`: <brief: which options are presented as the answer, and how often>
`answer`: <letter or NONE>
`quote`: <a verbatim span copied from ONE sample that presents the chosen option as the answer
(for a token list, copy the tokens without their scores, joined by " | "), or empty for NONE>
```

- `{token_note}` is `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` with
  KC's `multi_select=False` (never a bare `mc.TOKEN_NOTE`, since KC sets `flat_types`; shared
  `test_token_note_rendered_from_spec`) (the one shared token-list note, Q4
  combining rule, options-relative flat-list clause filled with "numbers, dates") when the call
  carries token rows, else empty. In summary mode the same text applies as
  `SUMMARY_NOTE_TOKENS` rendered with KC's `flat_types` (infra §2.7.2); KC adds no family token
  wording. Rule 4's last two sentences are the prose-side restatement of that clause, in the
  same options-relative terms (no "mostly of one type" wording, no exception for a top-ranked
  candidate). "Add, never relax" (SHARED_API): the closing "unless the line is a run of many
  numbers or dates" keeps rule 4 from crediting a lone option the shared note voids; rule 4's
  other sentences (support weighing, "only option is not enough") only ADD requirements.
- **`{menu}` (critique 32, Q8).** Built from
  `mc.options_with_cannot(options, cannot=mc.KC_NONE)` (options in their seeded order; the KC
  NONE line is appended LAST, never shuffled). It renders as three paragraphs:
  1. `A. <option>` … `E. <option>` — unchanged, and still the first paragraph after
     `=== OPTIONS ===`, so `_kc_judge` (`tests/test_summary_mode_introspection_kc.py:174-186`)
     parses it unchanged;
  2. `Also written as (a sample writing any of these names that option):` then one line per
     letter, `A: Aruba Networks; HPE Aruba Networking` — every `option_units` form of that
     option that is not its canonical text, deduped after `fold`, at most 8, Latin first then CJK
     (`prompts.forms_block(options, option_units)`); a letter with no extra form is omitted;
  3. the final line, exactly `mc.KC_NONE` = `NONE (cannot tell from the readouts)`.
  Infra's `test_every_mc_judge_ends_with_cannot` reads the final option line and accepts
  `mc.KC_NONE`. The schema enum stays `[A-E, NONE]`; answer `NONE` is that line.
- `DIGEST_TASK_NOTE` (`prompts.py:63-66`) becomes, and `knowledge_cutoff.SPEC.task_note` is set
  to it: "the model reads a short factual question about a recent event or an obscure fact and
  is about to reply with just a name or a number; the readouts may restate the question, give one
  or more candidate answers, add notes, or refuse". It names no answer, option or gold (infra's
  `test_every_summary_family_has_task_note_without_gold`). `item_task_notes` stays `None`.
- **Restatements (shared r2 rule, infra §2.8.2).** The digest records a named restatement (a
  product, person, place or number named while restating the question) under that term, in
  items or rare; only the generic wording of the question is capped at one item. KC adds no
  digest wording for this. Whether a restatement is an *answer* is the judge's call (SYSTEM
  rule 1), and G3 excludes prompt-named options (C5), so recording restatements cannot add a
  hit by itself.
- **`flat_types` (r2).** `knowledge_cutoff.SPEC.flat_types = ("numbers", "dates")`. Numbers cover
  the 55 + 33 numeric items; "dates" covers kc2_00071 (five `october N, 2025` options), the only
  date-typed item — this is what infra §2.7.2's "days / months for KC" refers to. Name items
  declare no type: a list of names singles out an option only per the options-relative rule.
- Digest defaults: `digest.FAMILY_DEFAULTS["knowledge_cutoff"] = {"summ_max": "25", "summ_rare": "25"}`
  (both allowed keys; no cap, variant or overflow key). KC coverage was 0.42 at 10 and 0.65 at 25
  (`docs/summary_mode_validation.md:64`). The judge must see the competing answers to weigh them,
  and rare single answers must survive into the digest so G2 can count them.
- Tests for the prompt changes:
  - `test_menu_shows_every_accepted_form`: the rendered user (native and summary) has the A-E
    block first, then an `Also written as` line per letter listing every non-canonical
    `option_units` form (deduped after `fold`, ≤ 8, Latin first), then `mc.KC_NONE` as the last
    option line.
  - `test_kc_flat_list_is_options_relative`: rendered native and summary judge prompts contain
    `mc.token_note(("numbers", "dates"), multi_select=False)` verbatim for token calls, and `SYSTEM` contains no
    "ranked first" / "mostly" wording. Mechanical side, with a scripted judge: a pick of
    `jupiter` quoted from two lists `"Jupiter | giant | planet | none"` (no other option in
    them) counts support 2 and passes; a pick of `131072` quoted from two lists
    `"131072 | 262144 | 8192 | 4096 | 32768"` counts support 0 (`digest.number_flood`) and fails.
  - Shared: `test_no_tool_names_in_prompts`, `test_every_mc_judge_ends_with_cannot`,
    `test_prompts_in_readme`, `test_bank_pv_bumped_when_prompts_change` (KC's PV is bumped to
    `cutoff-judge-2026-10-30`).

### C4. "Answer-vs-explanation confusion in 'number then note' readouts. The judge counts numbers inside explanatory notes as answers"
- **Prompt:** rule 2 of the new `SYSTEM` (C3).
- **Mechanical gate G1 ("head contradiction"), in `score.py`:**
  - `NOTE_MARK = re.compile(r"\s(?://|#|/\*)|\(\s*\*{0,2}(?:note|e\.g\.|i\.e\.|explanation|or\b)|\*\(|\b(?:note|explanation|reasoning)\s*[:：]|（\s*(?:注|备注)|\s[—–]\s", re.I)`.
  - `answer_heads(stmts: Sequence[digest.Line]) -> list[str]`: the bullet split is the shared
    `digest.statement_lines(lines, cells)` (one Line per top-level `- ` bullet of a prose
    sample; an unbulleted sample is one Line); KC writes no splitter of its own. Each statement
    line's head is its text before the first `NOTE_MARK` match (the whole line if none). A
    `prose1` s3d generation therefore has up to ~4 heads; a `bullet4` generation or an NLA
    sample usually one. Newlines inside a bullet are NOT a marker: the replay showed
    "…\n**Best Guess: India**" answers after a newline.
  - `contradicts(head, picked, forms, numeric)` is True when the head names some option under
    the forms but not `picked`. On a numeric item it is also True when the head contains a
    standalone number whose value differs from `picked` and the head does not name `picked`.
    Values come from the shared parsers only: `digest.number_value` per numeral token (so
    `999.00 == 999`, decimals kept) and `numerals.numbers_in` / `numerals.word_value` for CJK
    and number words; KC adds no number parser except the Roman one (C7.1).
  - A prose pick is verified only if `digest.quote_ok(quote, lines)` holds AND
    `digest.quote_ok(quote, digest.statement_lines(lines, cells))` holds (the quote lies inside
    one bullet, so "the line that contains the quote" is well defined; KC's answer is not
    relational, this is only G1's anchor), C7.3's boundary condition holds, the forms name the
    pick inside the quote, AND `not contradicts(head)` for that statement line's head.
  - `lines` = `digest.native_lines(cells)` in native mode, `col.evidence[item_id]` in summary
    mode (extractive: each evidence line is a real sample, its bullets joined by
    `digest.BULLET_MARK`), so the same gate applies in both.
  - `extras.n_unverified_bullet` (SHARED_API r3): picks that pass `quote_ok(quote, lines)` but
    fail the `statement_lines` check. KC is not a relational family, but it uses the same check
    as G1's anchor, so it reports the count (gpu G9 `audit_run.py` prints it).
- **Why "contradiction", not "the head must name the pick":** a head-must-name rule failed 6 of
  295 cached s3d hits that are real answers. Examples: "5.1 (Note: PowerShell 5.1 …", where the
  option forms have no bare "5.1", and "JustWatch** (or … it is **Altice**." The contradiction
  form keeps those and drops only what it should. On replay it failed 1 of 295 s3d hits: cs00047
  L48, where the head says `5.75` and the quote "…boost clock of 5.7" was truncated (see C7.3).
- **Tests:**
  - `test_answer_head_markers`: `"8192  # GPT-4o … 128,000 tokens"` → head `"8192"`;
    `"(e.g., \"128k\")"` cut; `"Kirin 9100, or possibly the Kirin 9020."` keeps both;
    raw sample `"- 131072\n- 128000 (Note: …)"` → native Line text `"- 131072 ⁞ 128000 (Note: …)"`
    (`digest.BULLET_MARK`) → `statement_lines` → heads `["131072", "128000"]`.
  - `test_note_number_never_verifies`: cs00166 options, sample `"131072  /* Note: … 128,000 tokens"`,
    pick `128000` quoted from the note → unverified; pick `131072` → verified.
  - `test_equal_value_is_not_a_contradiction`: `"999.00  # … $999"` verifies 999.
  - `test_kc_quote_spanning_two_bullets_unverified`: prose1 sample `"- 131072\n- 128000 (Note: …)"`,
    quote `"131072 ⁞ 128000"` (copied across the mark; `fold_quote` maps `⁞` to a space, so
    `quote_ok(quote, lines)` holds) → unverified (not inside one `statement_lines` Line), and
    counted in `extras.n_unverified_bullet == 1`.

### C5. "Weak or only-option evidence wins. There is no minimum support: when the gold is the only option string that appears, one passing mention ('e.g. \"128k\"', a rank-17 token) is picked even amid many non-option answers. Numeric items with scattered numbers give chance hits."
- **Prompt:** rule 4 of the new `SYSTEM` (C3), including the shared options-relative flat-list
  rule with KC's `flat_types` (no exception for a top-ranked candidate). Rule 5 bans the "begins samples" heuristic seen in cs01809.
- **Rank 17:** `readouts.normalize` keeps `tokens[:10]` for `tokens10` (infra §2.9.3), so a
  rank-17 token never reaches the judge or the gate.
- **Mechanical gate G2 (minimum support), in `score.py` / `judge.py`:**
  - `support(item, opt, lines)` = the number of samples that support `opt`, where a sample is
    one readout as `readouts.normalize` leaves it (infra §2.9.4): one `prose1` generation, one
    `bullet4` generation, one NLA sample, or one top-10 token list.
    - A prose sample supports `opt` when some `answer_heads(sample)` names `opt`; it counts once
      however many of its lines do.
    - A token list supports `opt` under the C7 token rules (same-list tokens only, or one word
      spelled across adjacent positions of one layer, as `digest.quote_ok` accepts).
    - **Flat lists (Q4, critique 16, critique r1 item 3, critique r2 item 4).** On a numeric
      item, a sample for which `digest.number_flood(line)` is True gives no support to any
      numeric option. `line` is the **whole sample Line** as it comes from `lines`
      (`digest.native_lines(cells)` / `col.evidence[item_id]`, `bullet is None`), never a
      `digest.statement_lines` bullet: `number_flood` raises `ValueError` on a bullet Line, and
      a per-bullet call could never reach 5 on a bulleted list. The definition is infra's
      (§2.7.5), not KC's: a token list is a flood at ≥ 5 distinct numerals
      (`numerals.numbers_in` per token); a prose sample is a flood only when it holds a
      list-shaped run of ≥ 5 distinct numerals separated by `, ; | /`, "or", "and", spaces, or
      `⁞` between bullets that hold only numerals and punctuation, where operands / results of a
      stated operation break the run and number words count only inside a run. So s3d's
      "- 12\n- 15\n- 17\n- 19\n- 23" (`12 ⁞ 15 ⁞ 17 ⁞ 19 ⁞ 23`) is a flood, while a worked
      note ("128k = 131072 tokens, up from 32768 = 32k") or s3d bullets stating computations
      never void support. The flood check is per sample; `answer_heads` (which bullet names
      `opt`) stays per bullet.
  - The scope is the judged unit's real cells. Native: the (item, layer) cell. Summary: every
    real cell the digest read (`by_item[i]`, `judge.py:377-379`), so a consistent answer that
    appears once per layer across 11 layers has support 11.
  - Required: `support(picked) >= min(MIN_SUPPORT=2, n_samples)`, where `n_samples` is the
    scope's count of non-blank samples / token lists.
  - A single-sample file (the po-opus-v1 prompt-only readout, a one-layer lite NLA file)
    therefore needs 1. The gate can only ask for corroboration where corroboration could exist.
- **Mechanical gate G3 (numeric plurality).** An item is numeric when every option parses as a
  number after `_STRIP` (`score.py:14`); that is 55/108 frozen and 33/39 nocot items. On such an
  item, `support(picked) >= support(o)` for every other option `o` (ties allowed).
  - Options named in the item's own prompt are excluded from the comparison (frozen: `user`;
    found on 2 items, cs01611 `field` and kc2_00949 `10`).
  - nocot has no prompt text offline, so no exclusion is made there. Restatement can then only
    make G3 stricter, never more lenient.
  - G3 is not applied to name items: the audit found the judge right on denial frames, where a
    regex count is wrong (`systematic_issues[5]`).
- **hit** = pick == gold AND verified (`digest.quote_ok` + C7.3 boundary + G1) AND G2 AND G3.
- **Restated invariants (retained):**
  - `ati_pass` keeps its looser gate-only rule exactly, with **no G1/G2/G3 and no boundary
    condition**: pick == gold ignoring verification, OR a pos −1 regex mention at the bank layer
    (`judge.py:225-229`). It is still native-only. Panel readouts are one sample per draw.
  - The native bank-layer pick (`best_layer`) stays the native headline rule.
  - Summary mode still never picks a layer.
  - Empty / unjudged / undecided semantics are unchanged (`judge.py:198-200`, `:428-437`).
- **Diagnostics:**
  - `extras.gate_drops = {"contradicted": n, "min_support": n, "numeric_plurality": n,
    "number_flood": n, "boundary": n}`, counted over judged picks that would otherwise be hits,
    also split by `source` (cutoff / nocot);
  - `extras.support_of_hits` (histogram: 1 / 2-3 / 4-10 / >10);
  - row fields `support`, `gates: {g1, g2, g3}`;
  - native extras also carry `mcjudge.layer_pick_columns(rows)` (critique 18), printed beside
    every native / ATI number.
- **Offline replay on cached data** (old judge answers, new gates; no calls). Two views, because
  the cached answers were made with all 5 cached samples visible:
  - *Gate logic over all 5 cached samples* (`replay.py`): s3d native 295 → 255 hit cells (G2 −37,
    G3 −3, G1 −1); L60 headline 64 → 60 of 109 (0.587 → 0.550). ML-NLA 282 → 214 (G2 −63, G3 −5,
    G1 −6); L60 52 → 50. The G3 drops are cs00170 L56 (131072: 3 vs 262144: 5), cs00527 L52
    (25: 4 vs 60: 7) and cs00840 L44 (2: 14 vs 3: 15).
  - *The same answers after `prose1` trimming to 1 generation per cell* (`replay_prose1.py`):
    only 65 s3d / 72 ML-NLA old hits still verify on the first generation, and with 3 legacy
    sites per cell G2 needs 2 of 3, so 15 / 11 survive. This shows the cached three-site files
    cannot stand in for the campaign instrument; it is not a forecast. At full span (≈ 62
    generations per layer) G2's "2 of n" is mild. Real numbers come from the regenerated run (E11).
  - The audit predicted this: single-sample hits mostly sit at low and mid layers, and the
    headline barely moves.
- **Floors made visible.** Today none exist; see §1.6.
  - `extras.distractor_floor`: per decided item, 1/4 if the item's verified, gated pick is a
    non-gold option, else 0, averaged. This is the rate a random non-gold option would score as
    gold under the same instrument, and it costs no calls.
  - `extras.truth_pick_rate` = `answer_kinds.truth / decided`.
  - `CHANCE_LABEL` is rewritten to name these, the po-opus-v1 prompt-only floor and the lucky
    floor.
- **Tests:**
  - `test_min_support_single_mention_fails`: cs00531-style cell, one sample `"10 (Note: …)"`
    among 19 samples of other answers → not a hit (`gate_drops.min_support == 1`). With a second
    `"10"` sample → hit.
  - `test_number_flood_line_gives_no_support`: a token list `"10 | 12 | 8 | 6 | 7 | 9"` and a
    prose head `"10, 12, 8, 6 or 7"` give support 0 to option `10`, even with 10 ranked first.
  - `test_kc_worked_prose_is_not_flood` (KC regression for critique r1 item 3): two prose1
    samples `"16384 (8192 × 2 = 16384, up from 4096 in v1 and 2048 in v0)"` on an item with
    option `16384` → support 2, hit; the same item with `"16384, 8192, 4096, 2048 or 1024"`
    ×2 → support 0.
  - `test_kc_bulleted_number_list_gives_no_support` (critique r2 item 4): two prose1 samples
    `"- 16384\n- 8192\n- 4096\n- 2048\n- 1024"` on the same item → support 0 for `16384`,
    `gate_drops.number_flood == 1`, not a hit; two samples
    `"- Doubling 8192 gives 16384\n- up from 4096 in v1"` → support 2, hit.
  - `test_kc_flood_is_called_on_whole_sample`: with `digest.number_flood` wrapped by a spy,
    every call during a KC native and a summary judge gets a Line with `bullet is None` (the
    shared `test_number_flood_rejects_statement_line` covers the `ValueError`).
  - `test_min_support_single_sample_file_needs_one`: a 1-sample-per-item file passes on its
    one sample.
  - `test_summary_support_counts_across_layers`: one sample per layer at 3 layers → support 3,
    hit.
  - `test_numeric_plurality_gate`: 131072 ×3 vs 262144 ×5 → no hit; prompt-named options are
    excluded.
  - `test_tokens10_drops_rank_17`: a 20-token row with gold at rank 17 → after `reads.load`,
    support 0, not a hit.
  - `test_ati_pass_ignores_gates`: a gold pick with support 1 has `pass False`, `ati_pass True`.
  - `test_distractor_floor`: 4 items, 1 verified wrong pick → 0.0625.

### C6. "Alias mismatch. The menu shows only canonical option text, verification accepts option_units aliases, and the judge refuses near-aliases (Aruba Networks vs 'aruba networking'; A321 vs 'a321neo')."
- **Aliases in the menu (Q8).** The `Also written as` paragraph of `{menu}` (C3) lists each
  option's `option_units` forms. Rule 3 of `SYSTEM` tells the judge that listed forms count and
  unlisted relatives do not. The verification side already uses the same `option_units`
  (`judge.py:136`), so judge and checker see one list.
- **Script-safe matching (critique 19).** `score.OptionForms.named` matches each form with
  `mc.form_in` (word-bounded Latin; CJK only as a listed CJK form, never a bare CJK substring of
  something else, and a quote without Latin letters passes only on a listed form in its
  script). KC's longest-match / contested-span logic (`test_exclusive_longest_match_and_contested_spans`)
  stays on top of it; the C7.1 numeral path is the only addition.
- **Near-alias additions (Q8: "A321 ⇔ a321neo and similar near-aliases COUNT").**
  - Candidate scan (`scripts/kc_near_aliases.py`, offline, deterministic): for every option form,
    strip trailing variant words (`neo|ceo|family|series|pro|max|plus|ultra|mini|lite|networking|networks|inc|corp|ltd|group|holdings|technologies|company`).
    A stripped form F is a candidate for option o when no other option of the item has F as a
    form or as the start of a form. Over the 147 items it yields 14 distinct candidates on 5 items (a run on cd6b0fa).
  - Acceptance rule (frozen in the v2 header as `near_alias_review`, one row per candidate with
    verdict and reason): accept F unless (a) F is itself the name of a separately released
    sibling of another option (o3 vs `o3-mini` beside `o1-mini`/`o4-mini`; Gemini 1.5 beside its
    Flash sibling), (b) F is a bare brand or common word (`Xbox`, `Panda`), or (c) F is a strip
    artefact (`bor` from `borneo`).
  - Result of the review:

    | item | option | added forms | verdict |
    |---|---|---|---|
    | cs01684 (live) | `a321neo` | `A321`, `Airbus A321`, `空客A321`, `空中客车A321` | accept (Q8's example; no other option is an A321) |
    | kc3_01462 (nocot) | `geely panda mini` | `Geely Panda` | accept (via `near_alias_additions`) |
    | cs00140 | `o1-mini` / `o3-mini` / `o4-mini` | `OpenAI o1` / `o3` / `o4` | reject (a) |
    | cs00140 | `gemini 1.5 pro` | `Gemini 1.5`, `Gemini-1.5`, `Google Gemini 1.5` | reject (a) |
    | cs01078 | `xbox series x\|s` | `Xbox` | reject (b) |
    | kc3_01462 | `geely panda mini` | `Panda` | reject (b) |
    | kc3_01004 | `borneo` | `bor` | reject (c) |

    The table is shown on the site under "Decisions taken (override if you disagree)"; Camila can
    flip any row, which is one header edit plus a re-judge.
  - Effect on cs01684: gold is `a220`, so crediting "A321" as `a321neo` turns a NONE into a
    distractor pick. The hit rate on this item is unchanged; `distractor_floor` and
    `answer_kinds` now count it. This is the live-item demonstration critique 23 asked for.
  - Aruba (cs00312) is retired; it is shown on the fixture bank only (E7).
- **Tests:**
  - `test_menu_shows_every_accepted_form` (C3).
  - `test_near_alias_a321_credits_a321neo`: on cs01684, the menu shows `A321` under the
    `a321neo` letter, and a sample `"Airbus A321"` verifies a pick of `a321neo` (not `a320`,
    not `a320neo`).
  - `test_near_alias_additions_are_unambiguous`: every added form, under `mc.form_in`, names its
    own option and no other option of that item; every `near_alias_review` row has a verdict.
  - `test_listed_alias_verifies`: "Just give the name: Aruba Networks" verifies
    `aruba networking` (fixture bank).
  - `test_cjk_alias_needs_listed_form`: a quote `"空客"` does not verify `a321neo`; `"空客A321"`
    does.

### C7. Supporting verification fixes (the "too strict" half of C3, and one new error)
1. **Numerals.** `OptionForms.named` gains a numeral path for integer options (`score.py:68-89`).
   `compile_form` is unchanged, so the existing assertion `compile_form("十八") is None` in
   `test_number_forms_are_standalone` still holds.
   - Digits and CJK numerals (maximal runs, inside 第…/…条 too) are valued by the shared
     `numerals` module (infra §2.7.5a: `numerals.numbers_in`, CJK moved there from
     `digest._cjk_int`) and `digest.number_value` for one-token decimals; KC adds no CJK or
     digit parser of its own.
   - Number words (`"sixty"`, `"twenty-four"`, 0-100 with compounds, as `numerals` defines
     them) via `numerals.word_value` / `numerals.names_value(n, text)`; KC adds no word parser.
     KC-local restriction on top: in token rows always, in prose only for values ≥ 11, because
     "two" and "eight" are common in prose. Word values above 100 are not credited (outside
     `numerals`' range; digits still credit them).
   - Uppercase standalone Roman numerals `[IVXL]{2,}`, value 2-89: KC-local `score.roman_value`
     (`numerals` has no Roman path; the only KC-local numeral code).
   - A numeral credits the option with the same integer value.
2. **Token first pieces and the Q4 combining rule.** On token rows only, after
   `digest.quote_ok` accepts the quote (same-list tokens joined by `" | "`, or one word spelled
   across adjacent positions of one layer), a token also names an option when:
   - (a) the folded token has ≥ 4 letters, is a prefix of a single-word form of that option
     covering ≥ 60% of it, and is a prefix of no other option's form ("Christie" → `christies`
     via "Christie's"); or
   - (b) every word of a multi-word form appears as a token of the SAME list, in any order.
   - Nothing combines across lists, positions (except the one-word spelling) or layers; a list
     holding two or more options, or a run of numbers / dates (`flat_types`), singles out none
     (C3 rule 4, C5).
   - "Volkswagen" alone never credits `volkswagen golf`; its listed form "Golf" does.
   - Replay on cached J-lens native (gold picks 107): verified 56 → 58 at top-10 (49 with top-10
     under the old rule). The L60 old count is 20; with G2, 15 remain (3 lists per legacy cell;
     full-span files have ≈ 62 per layer).
3. **New error: truncated quotes verify.** cs00047 L48 (s3d, a cached HIT): the quote "…boost
   clock of 5.7" is cut from a sample reading "5.75". The regex runs on the quote, so `5.7`
   matches.
   - Fix: a KC condition ADDED on top of `digest.quote_ok` (infra §2.7.4 allows additions, not
     substitutes): `score.boundary_ok(quote, line_text)` — the `digest.fold_quote`-folded quote,
     at the place it occurs in the folded line, has no letter or digit on either side whenever
     the quote itself begins or ends in one. It is applied in `verdict` / `summary_verdict`
     (`judge.py:105-107`, `:345-347`) after `quote_ok`; `family.quote_in` is no longer called by KC.
   - It is KC-local, so other families are untouched.
   - Test: `test_truncated_number_quote_fails`.
4. **Tests:**
   - `test_numerals_credit_integer_options` (十九, 第十九, XIX, "twenty-four" → 19/24; "I" and
     "two" in prose do not credit 1/2);
   - `test_token_first_piece_and_same_list_words` (Christie → christies; "Volkswagen" ✗;
     "Golf" ✓; " Kirin" | " 9100" in one list, in any order ✓; across two lists ✗;
     " Kir" + "in 9100" at adjacent positions of one layer ✓ as one word; at different layers ✗).

### C8. Campaign decisions (not Camila's KC sentences)
- **D4 / critique 32.** NONE is the cannot-tell option: the last menu line, exactly `mc.KC_NONE`,
  appended by `mc.options_with_cannot(options, cannot=mc.KC_NONE)` (C3). No other NONE wording.
- **D5.** Task note in C3 (`EvalSpec.task_note`). No tool names in KC prompts (shared
  `test_no_tool_names_in_prompts`).
- **D6 / Q4.** Same-list combination and adjacent-position one-word spelling only (C7.2); the
  flat-list rule is the shared options-relative one (≥ 2 options, or a run of KC's
  `flat_types` = numbers / dates, singles out none; a lone option on its line is singled out),
  with no exception for a top-ranked candidate (C3 rule 4,
  `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`, C5 `number_flood` on whole
  samples).
- **Macro (SHARED_API r3).** KC's metric stays `"pass_rate"` (in `results.MACRO_METRICS`) and
  `EvalSpec.not_in_macro = ""` (unchanged; never `None`), so KC is in the macro.
- **D7 / Q1.** C2.5: s3d-rl600 is `prose1`, declared in the sidecar.
- **D8 prompt-only (infra §2.11, protocol `po-opus-v1`; critique 4).**
  - Built by `wsbench baseline kind=prompt_only_opus stage=build|ask|readouts out=<dir>`
    (module `baselines.prompt_only_opus`): one Opus 5.5 readout per plan row id, rendered through
    the last full-read site (KC: pos −1, the max of `all_from_end`), one prose cell at that pos,
    `layer = PROMPT_ONLY_LAYER = 44`, sidecar `reader: "prompt_only:claude-opus-5-5"`.
  - Judged by `wsbench run all=True readouts_root=<dir>/readouts` with no `layers=` / `reads=`:
    the same digest, `SYSTEM_SUMMARY`/`USER_SUMMARY`, menu, gates G1-G3 (G2 needs 1 because
    `n_samples = 1`). The completeness waiver is the shared one (infra §2.6.6).
  - **Not per read position** (one readout per id, not one per position × layer), so the floor
    gets one chance per item, not ≈ 62 × 11.
  - The floor = KC's own headline (summary hit rate with C4-C7 verification and G1-G3) from
    KC's own `run` on that file; CI = Wilson; n = ids judged − refused; if more than 20% of ids
    are refused, the floor is `not_measurable` and the site says so instead of drawing
    `lens − floor`.
  - Timing: measured at gpu R6, after R4c closes; if KC's PV changes after R6 (an R4c fix), KC
    has no floor until R6 re-runs for it.
  - Frozen into `evals/baselines/prompt_only_summary.json` under `knowledge_cutoff`; drawn beside
    a lens row iff `summary_floor_applies(entry, config)` (on `strip_reads(prompt_version)`,
    summarizer key, judge model; `layers_judged` not compared, so one floor serves all 12
    configs and lite).
  - nocot prompts are rendered from the zip at run time and never written into the repo; the
    prompt-only `readouts/` for nocot ids are not published (C9).
  - Test: `test_prompt_only_file_is_complete_under_full` (a `prompt_only:*` sidecar file with one
    −1 cell per id at L44 is judged complete under default `reads=full`,
    `config.reads_checked == "prompt_only"`; stamp has no `+reads-lite`).
- **Lucky floor (recommended, cheap).** Add a `_knowledge_cutoff` builder to
  `lucky_guessing.BUILDERS`, reading the bank via `registry.bank_path` (infra §2.12.3): options
  only, 5 draws per item. It drops the NONE line, as `lucky_guessing` does for every family. This
  measures whether Qwen's stale answer "looks" guessable from the option list (the README already
  reports option-structure guessers 0.235 / 0.176 on nocot).
- **ATI (decision: re-gate every changed instrument natively).** KC stays in ATI (Camila did
  not exclude it).
  - The instrument bump and the bank change (v2) both trip the guard
    (`baselines/text_inversion.py:1465-1474`). The lite fields never enter `bank_sha`
    (infra §2.6.9), so the new `bank_sha` comes from the bank alone.
  - **Re-gate by re-judging the cached panel answers** (gpu G13 r3 rule: new answers iff an
    ATI-scored item's `prompt_sha` changed, re-judge iff only `bank_sha` / instrument changed; KC's
    item prompts are unchanged, only the bank keying (cs01301 out, near-alias forms) and the
    instrument changed, so KC is "re-judge only", run at gpu R8 after R4c): no new panel answers; 147 items × 4
    readers × 3 draws = 1,764 native calls at L44. Then `wsbench text-inversion stage=gate`.
  - The answers are cached at `/root/wsb-ati-panel/outputs/baselines/text_inversion/readouts/{qwen,opus,astra,argon}/draw{0,1,2}/knowledge_cutoff.jsonl`
    (the 109 pre-refill ids), plus `refill/knowledge_cutoff/round*/` and
    `refill/knowledge_cutoff_nocot/`.
  - cs01301 leaves, so `n_bank` = `n_ati` (expected) = 147; `test_ati_entry_is_offline_and_current`
    then holds unchanged once the entry is regenerated.
- **Campaign arms (round-2 critique r1 item 8, gpu G14).** s3d-rl600 (`prose1`, 12 configs),
  plus the required `jlens` (`tokens10`) and `mlnla-rl2-2000` (`prose1`) all-layer configs, full
  + lite, each with a declared sidecar (KC is in `FAMILIES_BP`). These are produced by the gpu
  workstream; KC funds no other arm. Every per-arm KC number (E11, E12) is on these three;
  anything else (cached v1 readouts) is labelled "cached v1 readouts, judge test only".
- **12-config run (critique 26).** The arm is s3d-rl600 (`prose1`). KC's judge is unpinned, so
  it runs on the default Opus 5.5; no Opus-judge column is needed. The summarizer is Opus 5.5 and
  `extras.digest_served_by` reports any fallback share.

### C9. New error found: nocot question text leaks through `results.json`
- README:81-83 says "Do not publish real readouts or cells.jsonl for these items: readouts at
  user-turn positions paraphrase nocot's questions".
- But summary rows copy `summary`, `summary_statements` and `summary_evidence` into every row
  (`judge.py:455-456` → `digest.Collapse.row`, `digest.py:913-929`), and native rows carry the
  verbatim `quote`.
- grep found no nocot filter anywhere in `src/wsbench` outside the KC/readplan/nocot modules.
  Any published `results.json` or website bundle would republish paraphrased nocot questions.
- **Fix:** in both `run` and `_run_summary`, rows with `source == "nocot"` get
  `summary*`, `quote` and `summary_evidence*` replaced by `"[redacted: nocot]"`, unless
  `opts=keep_nocot_text=1` (a local audit only). Also add a website-build check: refuse any
  bundle containing a nocot id with a non-redacted text field.
- **Licence (Q8 decision).** nocot answer keys stay ids-only, status quo, no licence change. C9
  removes the question-text leak; the answer keys in `obscure_items.json` are unchanged.
- Test: `test_nocot_rows_redacted_in_results`.

---

## 3. Data needs

- **Bank:** `evals/knowledge_cutoff/items_v2.json` (108 items; C1, with the Q8 additions and
  `near_alias_review`). `obscure_items.json` is unchanged. No new items and **no Qwen gating**:
  dropping an item and adding forms need no G0.
- **Readouts to regenerate (GPU, later phase; produced by the gpu workstream, R2 + G14):**
  s3d-rl600, `jlens` and `mlnla-rl2-2000` at the full plan, because no full-span KC readout
  exists. Each file carries a declared sidecar with `plan_sha = reads.plan_sha("knowledge_cutoff")`.
  - Read sites: `wsbench plan knowledge_cutoff` = 147 items × all_from_end (≈ 62 positions; exact
    per item from the Qwen chat render) × `readplan.GRID` 11 layers ≈ 100k cells per arm
    (gpu.md §3.3 lists 150 items / ~101,600; its R1 regeneration from `wsbench plan` gives 147).
  - s3d-rl600 (`prose1`): 1 generation per activation ≈ 100k generations. A `*-x4` arm, if run,
    would be `bullet4` (4 per activation).
  - `mlnla-rl2-2000` (`prose1`): 1 sample per activation. `jlens` (`tokens10`): top-10 tokens.
    Other token lenses (logit / tuned) are not produced for KC in this campaign.
  - `produce` must fetch nocot's pinned zip (`nocot.questions()`, `readplan.py:658`) wherever the
    plan runs. Modal containers need network or the cached zip in `$WSB_CACHE`.
  - Lite needs no separate readouts (pos −1 ⊆ full). The cached three-site files are valid lite
    files for the 42 surviving frozen items only.
- **Prompt-only (no GPU):** po-opus-v1, 147 Opus calls (ant OAuth token, one `flock` per run).
  - **Recommended:** the stock-Qwen prompt-only (the source's Baseline C, which tied the lens at
    0.486) as a decoder-prior control, shown as a labelled extra column, not the floor of record
    (which is po-opus-v1). That is GPU, 147 generations at pos −1. Without it, the README caveat
    stays a regex-era number.
- **API (later phase; authorised per the spend decision, smoke `limit=3` first):**
  - per arm: 147 digests + 147 judge calls (summary); 1,617 native calls if the ablation is run;
  - the ATI re-gate: 1,764 native calls;
  - the lucky floor: 147 × 5;
  - the evidence re-judges of §5.

## 4. Answers

Camila's KC section asks no direct question. These answer what each sentence implies, and the
general questions that touch this family.

- **A1. Are readouts taken at all positions and all layers?**
  - The plan: yes. Every prompt position (`all_from_end`) × 11 layers, frozen and nocot
    (`readplan.py:380-394`, `:650-672`).
  - The data: no. Every cached KC run reads the legacy 3 sites (−10/−2/−1), is partial and
    `complete=false`, and covers the pre-refill 109 ids (42 current, 0 nocot).
  - The summarizer: yes, it gets every cell it is given (`judge.py:377-393`); after infra the
    overflow is hierarchical above the global cap, and `expect_all=cells` asserts nothing is
    dropped.
  - Fix: C2 plus regenerated readouts (§3).
- **A2. How lenient or strict is the judge, measured?**
  - Audit: 49 reviewed, 4 too lenient, 5 too strict, 11 ambiguous.
  - Offline replay of the new gates on the cached answers (5-sample view):
    - the lenient cases are concentrated in single-sample hits (s3d 37 of 295 hit cells, ML-NLA
      63 of 282);
    - the L60 headline moves 0.587 → 0.550 (s3d), so the old headline was only mildly inflated,
      but per-layer curves and low layers were;
    - the strict cases are mostly verification (J-lens unverified gold picks 51 of 107) and
      become verifiable through C7.
  - Under `prose1` the cached three-site files are not a usable proxy (C5 replay, second view);
    the prompt rules (C3-C6) and the instrument need the regenerated run to measure (§5).
- **A3. Is cs01301 the only hygiene defect?** Yes, under the lint in §1.1, over both bank files.
  The same lint becomes a test.
- **A4. (General) How are prompt-only baselines judged for this family?**
  - Today: **not at all.** KC has no entry in `prompt_only.json`, `prompt_only_summary.json` or
    `lucky_guessing.json`. The text-only numbers in its README are the regex-era Baseline C
    (0.486) and the ATI panel's looser `ati_pass` pass@3 (Opus 0.31, Qwen 0.37).
  - After C8: the po-opus-v1 readout goes through the same digest, the same summary judge
    prompts, menu and gates. G2 needs one sample when only one exists, so the floor is not forced
    to zero. The floor is drawn beside the lens because `strip_reads` of the stamps match.
- **A5. (General) Has summary → judge been run for KC?** Only on the old bank and old reads:
  `d3a/d3c-s3d-all-summary-v3` gives 0.523 (109 pre-refill items, 3 sites, blind variant). It has
  not been run on the 147-item bank at full span. That run happens after §3's readouts. Camila's
  "all 11 layers, then each single layer" runs use `layers=each`.
- **A6. A321 vs a321neo (Q8, decided).** It now counts: `A321` (and `Airbus A321`, `空客A321`,
  `空中客车A321`) is a listed form of `a321neo`, shown in the menu. The other near-alias
  candidates and their verdicts are in C6's table, on the site for override.
- **A7. nocot licence (Q8, decided).** Status quo: ids-only answer keys, no licence change.

## 5. Evidence plan (what the website shows per item)

| # | item | artefact | expected |
|---|---|---|---|
| E1 | C1 cs01301 | v1 vs v2 item lists; lint table over both banks; `anti_text_inversion.json` entry `n_bank` 148 → 147, new `bank_sha` | cs01301 only in `retired_hygiene`; lint 0 hits on v2 |
| E2 | C2 positions/layers | for one item (cs00140): plan rows (57 positions × 11 layers, `lite_positions` final_token); regenerated readouts `positions_per_cell` min/median/max; `config.reads: "full"`, `config.reads_checked: "sidecar"`, `extras.partial_ids: []`, `complete: true`, `config.sampling: "prose1"`, `sampling_source: "declared"`; digest `n_readouts_in == n_readouts_bundled`; `layers=each` table (11 single-layer values + all) | before: 3 positions, partial, complete=false; after: all, complete |
| E3 | C4 notes | re-judge cs00166 L60 (s3d, cached v1 readouts, judge test only; native, `layers=60`; sidecar-less so `reads_checked: "no_sidecar"`) | before: pick 128000 (fail); after: pick 131072, verified, G3 pass → PASS |
| E4 | C5 single mention / flood | re-judge cs00531 L32 (s3d) | before PASS; after FAIL (`gate_drops.min_support` or `number_flood`) |
| E5 | C5 e.g. / rank 17 | cs00167 L20 (ML-NLA) and cs01524 L48 (J-lens), retired items, run with `WSB_BANK_FILE_KNOWLEDGE_CUTOFF=tests/fixtures/knowledge_cutoff_pre_refill_items.json` | both before PASS → after FAIL (cs01524: the token is cut by tokens10) |
| E6 | C5 numeric plurality | cs00170 L56, cs00527 L52 (s3d) gate replay | before PASS → after FAIL (G3) |
| E7 | C6 alias | cs01684 L40 (ML-NLA, live): rendered menu with `A321` under `a321neo`, judge answer before/after; cs00312 L56 (retired; fixture bank); the `near_alias_review` table | cs01684: NONE → the `a321neo` letter (a distractor pick, counted in `distractor_floor`); cs00312: NONE → A, or NONE kept if the denial frames dominate (shown either way) |
| E8 | C7 token verification | cs00808 L60 and cs01623 L60 (J-lens) | before FAIL (unverified) → after PASS |
| E9 | C7.3 truncated quote | cs00047 L48 (s3d) gate replay | before PASS → after FAIL (`gate_drops.boundary`) |
| E10 | C9 redaction | `results.json` of a full run: every `source: nocot` row's text fields equal `[redacted: nocot]` | 0 unredacted nocot text fields |
| E11 | overall | gate-replay table per cached arm (both views of C5; labelled "cached v1 readouts, judge test only"), then the full regenerated run per campaign arm (s3d-rl600, `jlens`, `mlnla-rl2-2000`): headline (all layers), per-layer curve (`layers=each`), beside the po-opus-v1 floor (or `not_measurable`), the Qwen prompt-only control (if run), `distractor_floor`, `truth_pick_rate`, the lucky floor, `gate_drops` by source, `layer_pick_columns` for native, and the ATI-subset value | headline shown with every floor |
| E12 | re-audit | KC's row of the shared G12/R4b leniency audit (gpu.md G12): ≥ 30 verdicts drawn by `scripts/audit_verdicts.py sample` (pass/fail × prose/token, seeded) from the s3d-rl600, `jlens` and `mlnla-rl2-2000` all-layer runs, labelled by a fresh-context auditor given feedback.md:217-222 and KC's pass rule (C4-C7, G1-G3); `audit_verdicts.py table` → `n_too_lenient` / `n_too_strict` / `n_ambiguous` with every non-ok case verbatim. KC declares no control kind, so no `--strata knowledge_cutoff=…` (pass/fail × prose/token only). KC adds no audit protocol of its own; the auditor brief notes the KC-specific cases to check (numeric vs name, NONE answers, flood voids) | lenient + strict below the old 9/49 and below the G12 flag (≥ 3 → gpu R4c: fix PR, re-run R4 + R4b for KC on all arms/configs/lite, ≤ 2 rounds, before R6/R8 and the site; leftovers → "New errors found"; never silently re-tuned) |

E3, E7 and E12 need new judge calls. E3-E9 run on cached v1 readouts and are labelled on the
site "cached v1 readouts, judge test only" (they show the rule change on the audited cases, not
a campaign number). E4, E6, E8 and E9 can be shown first as a no-call gate
replay (the old answer with the new gates), then confirmed by the re-judge. Cached readouts go
through `readouts.normalize` on load (no sidecar → `prose1` default for prose, `tokens10` for
tokens). If trimming removes the sample that carried a case, the evidence re-judge passes the CLI
override `sampling=bullet4` (which keeps the first 4 cached samples, `sampling_source:
"override"`), and the site says so.

## 6. Risks / conflicts with shared files

Shared files this workstream touches (all on top of the infra PR, which lands first):
- `src/wsbench/evals/knowledge_cutoff/__init__.py`: `SPEC.bank`, `min_full_positions=4`,
  `full_contiguous=True`, `task_note`, `flat_types=("numbers", "dates")`.
- `src/wsbench/digest.py`: `FAMILY_DEFAULTS["knowledge_cutoff"]` (allowed keys only). This
  workstream uses, but does not change, `collapse(expect_all=, task_note=)`, `quote_ok`,
  `statement_lines`, `BULLET_MARK`, `fold_quote`, `native_lines`, `number_flood` (whole samples only), `number_value`,
  `prompt_version`.
- `src/wsbench/numerals.py` (infra PR): uses `numbers_in`, `names_value`, `word_value`; no edit.
- `src/wsbench/mc.py`: uses `KC_NONE`, `options_with_cannot`, `form_in`, `token_note`; no edit.
- `src/wsbench/readplan.py`: KC rows gain `lite_positions` / `lite_layers`.
- `src/wsbench/baselines/lucky_guessing.py`: the new builder.
- `evals/baselines/anti_text_inversion.json`, `prompt_only_summary.json`, `lucky_guessing.json`:
  the re-gate and the new entries (run phase).
- `scripts/kc_near_aliases.py` (new, offline).
- KC-local: `evals/knowledge_cutoff/{README.md,items_v2.json}`,
  `src/wsbench/evals/knowledge_cutoff/{__init__,judge,prompts,score}.py`.
- Repo-level: README.md:295-296 and :391 (stamp, 147 items), CLAUDE.md:95-103 (instrument line).

**Sanctioned updates to pre-existing tests.** Each is listed with its reason; any other assertion
change in these files is a red flag.
- `tests/test_refilled_banks.py`: `N0["knowledge_cutoff"]` 148 → 147; `_bank("knowledge_cutoff")`
  reads `registry.bank_path` (v2) with `ITEMS_JSON` 109 → 108. `test_knowledge_cutoff_items`
  then checks the v2 header mix. (Bank change, C1.)
- `tests/test_ati_panel.py:437-456`: follows `bank_path`; verify, no edit expected.
- `tests/test_knowledge_cutoff.py` (runs on the pre-refill fixture bank). Its fixture files have
  no sidecar, so infra's completeness check is report-only for them (`reads_checked =
  "no_sidecar"`, nothing exits, `complete` untouched): **no blanket `allow_missing` or
  `min_full_positions` patch is needed** (the round-1 `sparse_files` fixture is dropped).
  - `_args` base dict gains `extra={"sampling": "bullet4"}` (the CLI `sampling=` override,
    `sampling_source: "override"`). Reason: the fixture cells hold 2-3 separate samples each (an
    x4-style multi-sample file); without a sidecar or override `reads.load` defaults them to
    `prose1` and keeps only the first, which removes the samples the tests quote. Fixture-only;
    no assertion changes. (`test_regex_judge_option_is_refused` overrides `extra` and still
    exits 2.)
  - G2 fixture fix: in `test_quote_must_be_verbatim_in_one_sample_and_name_the_pick` the pos −1
    row becomes `["The Kirin 9100.", "Kirin 9100", "unclear"]` (G2 needs 2 supporting samples
    among 5).
  - `test_partial_layer_run_uses_its_own_layer`: the fixture's L44 cells hold 9 samples, only
    one of which ("Probably the Kirin 9100.") names the gold, so G2 would fail it. The test
    writes its own copy of EXAMPLE with `"Kirin 9100"` appended to the cs00013 L44 −1 samples;
    assertions unchanged.
  - `test_token_cells_are_one_sample_per_position`: the pos −2 token row becomes
    `["ĠKirin", "Ġ9100", "Ġchip"]` (scores `[1, 0.6, 0.5]`), so two lists support the gold
    (G2, n = 2); assertions unchanged.
  - Any other KC summary test (`test_kc_quote_only_in_a_statement_fails`,
    `test_kc_token_row_regex_reads_joined_lines`, `test_kc_item_states`) that fails only on G2
    gets one more supporting sample in the cell it quotes, assertion unchanged; the implementer
    lists each such edit in the PR.
  - `test_example_readouts_pass_at_the_bank_layer` (`:149`): the retired regime-key assertion
    (`== "all"`) becomes `config.reads == "full" and extras.partial_ids_unenforced == []`.
    Reason: retired name (SHARED_API), same meaning for a sidecar-less file.
  - `test_legacy_three_site_file_is_scored_but_never_complete` (`:302-314`): the legacy file is
    written with `write_sidecar(path, reads="full", sampling="bullet4", reader="fixture",
    layers=[60])` and judged with `allow_missing=True`. Reason: KC's own `full_span` (which made
    a legacy file `complete=False` by itself) is deleted; under infra the incompleteness is
    enforced only for a sidecar file, and the test's point ("scored but never complete") is
    the enforced case. Its pos −1 row becomes `["The Kirin 9100.", "Kirin 9100"]` (G2); the
    regime-key assertion (`== "partial"`) becomes `set(extras.partial_ids) == {A.id, B.id}`;
    `value == 0.5`, `n_partial_cells == 2` and `complete is False` are kept verbatim (KC keeps
    `n_partial_cells` as an extra, the count of (item, layer) cells of partial items). The
    `EXAMPLE` half (`complete is True`) is unchanged.
- `tests/test_summary_mode_introspection_kc.py`:
  - `test_kc_one_call_per_item_no_layer_pick_no_ati` (`:218`): the regime-key assertion becomes
    `config.reads == "full"`; the stamp-prefix assertion becomes
    `config.prompt_version == digest.prompt_version(KC_PV, args, "knowledge_cutoff")` (infra owns
    the digest/sj bump and the task default; KC_PV itself is bumped). Its args get the same
    `sampling=bullet4` override.
  - `test_kc_partial_comes_from_the_real_cells` (`:239-246`): the same sidecar + `allow_missing`
    treatment and reason as the legacy test above; the pos −1 row becomes
    `["The Kirin 9100.", "Kirin 9100"]`; the regime-key assertion becomes
    `set(extras.partial_ids) == {A.id, B.id}`; `n_partial_cells == 2`, `complete is False` and
    the pass / `answer_kinds` assertions are kept verbatim.
- `tests/test_knowledge_cutoff_nocot.py::test_ati_entry_is_offline_and_current`: no edit; it
  passes once the ATI entry is regenerated (C8).

**Risks:**
- **G1 regex coverage.** `NOTE_MARK` was tuned on s3d/NLA English and Chinese notes. A dash
  inside a name ("Wi-Fi") is not a marker, because a marker needs surrounding spaces. Watch
  `gate_drops.contradicted` on the regenerated runs and read every drop in E12.
- **G2 under prose1.** One s3d generation now counts once however many of its bullets name the
  option, so support is lower than in the cached 5-sample files. At full span (≈ 62 generations
  per layer) this is mild; at lite (pos −1, one layer) G2 needs 1. Lite and full are therefore
  not equally strict; they are reported, never mixed (infra refuses mixed `reads`).
- **G3 on nocot.** Without prompt text, a restated prompt number can block a gold. This makes
  the gate stricter only. `gate_drops` is reported by source.
- **Near-alias review is a judgement call.** The acceptance rule and every verdict are published
  for override (C6); flipping a row changes the bank sha and triggers the ATI re-gate.
- **Native ablation drift.** Native still has the bank-layer selection bias (the CI ignores it).
  The headline is summary.
- **ATI re-gate** needs API calls before `anti_text_inversion=True` works for KC again (the guard
  exits 2 until then).
- **Infra dependency.** The two sanctioned sidecar edits assume `write_sidecar` accepts a
  sidecar without `plan_sha` (guard iii then does not fire) and that the plan-layer guard (ii)
  marks the one-layer fixture partial under `allow_missing` rather than exiting; both are
  infra §2.6 as written.
- **Sidecar-less leniency.** A sidecar-less KC file is judged with incompleteness only
  reported. It can never reach the site (gpu G9 refuses `reads_checked != "sidecar"`), and
  every cached-readout evidence row says "cached v1 readouts, judge test only".
- **Decoder-prior caveat.** None of this removes it. The headline needs the Qwen prompt-only
  control beside it (§3), or the README caveat stays a regex-era number.

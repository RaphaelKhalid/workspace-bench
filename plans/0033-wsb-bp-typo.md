# 0033 — WorkspaceBench fix campaign: typo + typo_mt ("typo" workstream)

Status: implemented in this PR (camila/wsb-bp-typo), on top of the infra PR (plan 0032, #140).
Campaign source of truth: `/workspace/root/wsb-bp/plans/{typo,SHARED_API,_fable_decisions}.md`;
this file copies the typo spec verbatim (below the line) plus what the implementation decided
where the spec left room or the merged infra differed from what the spec assumed.

Camila's sentences (verbatim, `notes/feedback.md`):

- typo: "drop this from the macro, we don't need it, just keep the hard version"
- Typo mt: "Drop the arithmetic items" / "Capitalised answer markers are not recognised ('**Answer:** 429', 'Result: 429' miss; matcher is case-sensitive on the sample), while README says 'answer:' counts. not observed to flip a reviewed item; latent false negative ['tyh-arith-3a']" / "fix this" / "Use regex" / "This should not be in ati"

Late critique fixes (binding, 2026-10-30) that touch this family: (1) `reads.plan_sha` does not
hash `layers` — already in infra (`tests/test_reads.py::test_all_layer_producer_file_is_judged`);
typo_mt's sidecar tests use `reads.plan_sha("typo_mt")`. (2)-(4) concern other families. (5) the
judge-spend estimate is recomputed after the smoke in the run phase; typo_mt's regex scoring is
free, only the summary-mode digest (one Opus call per item, 85 items per config) costs.

## Implementation notes (where this PR differs from, or fills in, the spec)

1. **Split-word counter lands in the shared mt path (spec §6 risk 10, left open for infra).** The
   merged infra had no `split_word_hit` / `n_split_word_hits`. Added once in
   `multitoken/family.py` for every regex mt family: native mode pools a layer's positions and now
   also credits a single-word form spelled by tokens of ADJACENT positions of that one layer
   (`digest.split_word`, the verifier behind `quote_ok`; decision Q4), and each row carries
   `split_word_hit` (the pass needs a split word). Summary mode already reached split words
   through `gate_texts(joined=True, forms=)`; its counter drops the digest's synthetic split-word
   evidence lines (new `digest.is_split_word_line`) and re-scores. The native change affects
   multilingual_mt / multilingual_typo token-lens results too, under the bumped
   `SCORER_VERSION`, and is Q4-legal there as well.
2. **Task note.** `mt_family(task_note=)` set `EvalSpec.task_note`, but the summary-mode digest
   call (`_collapse`) read `DIGEST_TASK_NOTES[name]` directly, so a family-passed note was never
   told to the summarizer. `_collapse` now uses the registered spec's `task_note` (falling back to
   `DIGEST_TASK_NOTES`); `summary_prompts(family, task_note=None)` takes the family's own note.
   `TYPO_MT_TASK_NOTE` lives in `evals/typo_mt/prompts.py` (re-exported by `__init__`).
3. **Span check.** `reads.check_full` sees positions only, never the tokenized span, so a file
   missing the LAST token of the misspelled word still looks contiguous; the guards that close it
   are the sidecar `plan_sha` and the producer. `test_full_partial_span_is_flagged` therefore uses
   a gap inside the span (13, 15 of 13-15).
4. **Cached J-lens number.** The spec's "J-lens 21/83" came from the deleted token summarizer
   step; natively on raw tokens the cached final-token J-lens file scores 0/85 (a strictly
   multi-token correction is unreachable by one token; the split-word path needs >= 2 positions,
   which lite files do not have). Summary-mode numbers come in the run phase.
5. **Data.** Adapted banks keep their `frozen` date and gain `version: 2`, `frozen_v2`,
   `derived_from` (with the old sha256) and `dropped` (names). The v2 frozen bank's `gate` string
   also states the new read site.
6. **Baselines README.** The typo_mt row of the ATI table stays, annotated "NOT_GATED since plan
   0033; entry removed" (the buggy_code precedent), so the old pass@3 record is still on the page.
7. **Pre-existing test assertions changed** (each a consequence of a spec'd change): the
   superseded map and `all` counts (`test_registry`, `test_capable`, `test_readplan`: typo is now
   superseded too); the `mt-regex-2026-09-23` literals in every mt family's `test_registered` and
   the dry-run print (now the imported `SCORER_VERSION`, the one campaign bump); typo_mt's PV
   (`SCORER_VERSION + "+typo-v2"`) in `test_mt_regex` / `test_multitoken_family`; the capable
   golden's typo_mt `n` (100 -> 85); the source-golden `DEVIATIONS` entry; `test_ati_panel`'s loop
   family (`typo_mt` -> `multilingual_typo`); `test_typo_mt` (v2 golden, v1 golden kept).
8. **Read span starts at the misspelling (review of PR #147).** The first cut read every token of
   `typo_word`; offline on the Qwen3.6-27B tokenizer 117 of those 250 positions (65 of 85 items)
   end before the first misspelled character (` interpret` in `interpretibility`; ` acc`, `iac`
   in `acciacatura`), where the model has seen only a correct prefix — reading them scores
   prediction. `suffix_text` gained an optional `from_char` (drop leading tokens that end before
   that character of the stripped text); typo_mt passes `first_diff(typo_word, target)`. Full is
   now 133 positions; lite (the final token) is still inside every span. Pinned by
   `test_typo_mt_full_span_starts_at_the_first_misspelled_character`.

---

# Workstream spec: typo + typo_mt (round 3)

Code of record: `/root/wsb-bp-base` @ `cd6b0fa` (origin/main). All line refs are to that tree.
Feedback sections covered: **typo** and **Typo mt** (verbatim in `notes/feedback.md`).
Shared names come from `SHARED_API.md` only; shared machinery (reads, layers, bank versions,
sampling, digest, MC, prompt-only, shared tests) is owned by `infra.md` and only *used* here.
Product decisions applied from `_fable_decisions.md`: Q1/D7 (sampling), Q4 (combining rule),
Q11 (typo_mt stays as the hard version, near-ceiling noted on the site), lite mode
(`reads=lite|full`), versioned banks (`EvalSpec.bank`), ATI (families Camila removes are removed),
spend (smoke `limit=3` first). Critique items fixed: round 0 items 2, 7, 29 (and Q11); round 1
items r1-1 (mt factory: the SHARED_API `mt_family` signature, `scorer="regex"`, refusal deleted
by infra), r1-7 (verdict-level leniency audit via gpu G12/R4b, E-audit), r1-11 (typo's README
floor is history, not valid; shared basic PV bump is infra's); own risks 7 and 8 are now closed
by infra §2.6.4 guards (i)/(iii) and §2.7.4 `gate_texts(joined=True, forms=)`.

**Round-2 shared names used (SHARED_API.md, nothing re-implemented here):** `mt_family(...,
scorer="regex", bank=, instrument_tag=, min_full_positions=, full_contiguous=, task_note=)`,
`EvalSpec.bank` / `registry.bank_path`, `reads.load` / `select` / `check_full` / `stamp` /
`strip_reads` / `plan_sha`, `ReadSpec.lite_positions` / `lite_layers`, lite rule `final_token`,
`readouts.normalize` (sidecar `sampling`), `digest.prompt_version`, `digest.gate_texts(joined=True,
forms=)`, `digest.quote_ok`, `mc.options_with_cannot`, `po-opus-v1` / `summary_floor_applies`,
`scripts/audit_verdicts.py`, `tests/conftest.py::write_sidecar`. typo_mt is not relational, so
`digest.statement_lines` and `number_flood` do not apply (no numeric forms remain after M1).

**Round-3 alignment (SHARED_API r3; `_critique_r2.md` names no typo.md item, so these are the
r3 shared changes that touch this family):**
- `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` is what the `opts=judge=mc`
  diagnostic prompt renders (typo_mt: `flat_types=()`, `multi_select=False`, so it equals
  `mc.TOKEN_NOTE`; no bare constant is written in typo_mt code). Held by the shared
  `test_token_note_rendered_from_spec`.
- `digest.BULLET_MARK` (`" ⁞ "`): a prose1 s3d sample's top-level bullets reach the regex joined
  by `⁞` inside the evidence text. `⁞` is a non-word character with spaces around it, so the
  word-bounded `unicode_word_matcher` cannot match a form across it; no typo_mt change.
- Leniency audit fix loop is gpu **R4c** (critique r2 item 6), not "before merge" (M5).
- Audit control strata (critique r2 item 14): typo_mt declares the stratum
  `split_word_hit` (M5), through the shared `--strata` / `STRATA` table only.
- Site (critique r2 item 5): the coverage map below is the `site/manifest.json` source for this
  spec (`sentence_id` column = `<section>:<line in notes/feedback.md>`), and §4 ends with the
  "Decisions taken" bullets that `site/build.py` lists in section 4.
- Prompt-only timing (SHARED_API r3): typo_mt's floor is measured at gpu R6 after R4c closes; a
  PV change after R6 means no floor until R6 re-runs for typo_mt (§3).
- Not used here (retired or not applicable): `not_in_macro` (typo uses `superseded_by`),
  `number_flood`, `statement_lines`, `multi_select=True`, `reads.plan_sha_rows` (typo_mt has no
  plan-file arm).

Camila's sentences (verbatim):

- typo: "drop this from the macro, we don't need it, just keep the hard version"
- Typo mt: "Drop the arithmetic items" / "Capitalised answer markers are not recognised ('**Answer:** 429', 'Result: 429' miss; matcher is case-sensitive on the sample), while README says 'answer:' counts. not observed to flip a reviewed item; latent false negative ['tyh-arith-3a'] fix this" / "Use regex" / "This should not be in ati"

Sentence -> change -> test -> evidence:

| sentence_id | sentence | change | named test | evidence |
|---|---|---|---|---|
| typo:66 | drop typo from the macro, keep the hard version | T1 `superseded_by="typo_mt"` (via `dataclasses.replace`) | `test_typo.py::test_typo_is_superseded_by_typo_mt` | E-T1 |
| Typo mt:122 | Drop the arithmetic items | M1 frozen `items_v2.json` (85) + the 4 adapted `typo_mt.json` banks rewritten without arith | `test_typo_mt.py::test_v2_bank_drops_exactly_the_arith_items`, `::test_no_reachable_typo_mt_bank_has_arith_items`, `::test_v1_readouts_with_arith_rows_judge_85_items` | E-M1 |
| Typo mt:123, Typo mt:124 | Capitalised answer markers ... fix this | M2 case-insensitive markers | `test_mt_regex.py::test_numeric_answer_markers_are_case_insensitive` | E-M2 |
| Typo mt:125 | Use regex | M3 regex stays the instrument, all positions of the misspelled word | `test_readplan.py::test_typo_mt_full_reads_the_misspelled_word_lite_the_last_token`, `test_mt_regex.py::test_run_regex_pools_positions_within_a_layer` | E-M3 |
| Typo mt:126 | This should not be in ati | M4 removed from ATI, `NOT_GATED` | `test_text_inversion.py::test_typo_mt_is_not_gated` | E-M4 |
| ALL/GENERAL:19 (critique r1-7) | "Audit to make sure it is neither too strict nor too lenient" | M5 typo_mt enters gpu G12/R4b (+ R4c if flagged), `split_word_hit` stratum | `tests/test_audit_verdicts.py::test_stratified_sample_is_deterministic`, `::test_strata_minimum_per_kind`, `::test_flagged_uses_gate` (shared) | E-audit |

Status rule for the manifest (gpu G11): E-M2, E-M3 (plan rows), E-M4 and E-T1 are offline and
become `done` when the named tests are green at the footer SHA; E-M1 is `done` on the cached
judge-test run; E-M3 (GPU pairs), E-audit, E-floor and E-Q11 stay `pending` until their run
artefacts exist, and E-Q11 / E-floor are `measured` (numbers, not fixes).

Key finding first (Section 4, A3): once the 15 arithmetic items go, typo_mt is 85 single-word
spelling corrections. The frontier text readers already solve them from the prompt: in the
frozen panel record Opus solves 83/85 and Argon 83/85. Cached prose lenses pass 84-85/85.
**Decision Q11: typo_mt stays as "the hard version"; the site notes that it is near ceiling**
(E-Q11), with the Opus prompt-only floor drawn beside every lens number.

---

## 1. Current state

### typo (single-token, shared bank judge)
- Registration: `src/wsbench/evals/typo/__init__.py:6`, `bank_family("typo", "Typo")`. It has no
  `not_in_macro` or `superseded_by`, so it is **in the macro** at full weight
  (`src/wsbench/basic/family.py:31-53`; `src/wsbench/results.py:228-285`).
- Bank: `evals/typo/items.json`, 100 items. Each item has `readout: {"kind":
  "final_prompt_token", "offsets": [-1]}` and `eval_render: "plain"`.
- Read site: `readplan._plan` sends `typo` to `_final_token_families`
  (`src/wsbench/readplan.py:308-326`, `:239-263`). That reads the final token only, on `GRID` =
  L20..60 step 4, 11 layers (`readplan.py:16`).
- Judge: the shared bank judge `basic/prompts.py` (SYSTEM, plus `FAMILY_RULE_TYPO` at
  `basic/prompts.py:110`, wired at `:131`), `prompt_version` `bank-2026-10-10`. It is a free-text
  YES/NO with a verbatim quote, **not MC**. Summary mode (the default since plan 0024) makes one
  digest per item and one judge call on it. The task note is at `basic/prompts.py:79`.
- ATI: already **not gated** (`text_inversion.py:93`, `anti_text_inversion.json` `_not_gated.typo`).
- Floors: prompt-only 1.00, marked saturated (`baselines/prompt_only.py:39-43`,
  `evals/baselines/prompt_only.json` `typo`).

### typo_mt (multi-token, regex contract)
- Registration: `src/wsbench/evals/typo_mt/__init__.py:6`, `mt_family("typo_mt", ...)`, which
  is `src/wsbench/multitoken/family.py:66-81`. The bank path is hard-coded to
  `evals/<name>/items.json` (`family.py:71`; `registry.bank_path`, `registry.py:49-67`).
- Bank: `evals/typo_mt/items.json` (header `family: typo-hard`, frozen 2026-09-10). It has 100
  items: 50 `novel`, 35 `real`, 15 `arith` (`tyh-arith-*`, e.g. `tyh-arith-3a` "143 × 3 = 492"
  -> 429). The only purely numeric forms in **any frozen bank** are these 15 items' forms. I
  checked every `*_mt`, multilingual_* and directed_modulation_obscure bank.
- Read site: final prompt token, plain render, 11 layers (`readplan.py:239-263`). Native mode
  **refuses** a file with more than one position per (item, layer)
  (`multitoken/family.py:145-150` regex path, `:580-584` MC path).
- Scorer of record: deterministic regex, `SCORER_VERSION = "mt-regex-2026-09-23"`
  (`multitoken/regex.py:69`). Token bags are summarized first in native mode
  (`SUMMARIZED_SCORER_VERSION = "mt-regex-summarized-decoded-2026-10-27"`, `regex.py:73`).
  Summary mode (the default) runs the regex on the digest's evidence samples
  (`digest.gate_texts(joined=True)`, `digest.py:948-966`; `multitoken/family.py:395-490`); the
  stamp is the scorer version plus the digest suffix built at `digest.py:410-412` (after infra:
  `digest.prompt_version(PV, args, family)`, never a literal). MC is only the optional
  diagnostic `opts=judge=mc`, which already has a `CANNOT` option (README §Judge prompts). Task
  note: `multitoken/prompts.py:52`, "...ends in a misspelled word or phrase".
- Numeric matcher (the bug): `regex.py:115-121` (`_ANSWER_CONTEXT`, lowercase English markers)
  and `regex.py:130-152` (`_numeric_matcher`). The sample is never casefolded on this path and
  the pattern is compiled without `re.IGNORECASE`, so `Answer: 429` and `**Answer:** 429` miss.
  The docstring says so (`regex.py:134-135`). The source golden pins the miss:
  `tests/golden/mt_regex_matching.json` has `{"form": "435", "sample": "Answer: 435", "hit":
  false}`, asserted by `tests/test_mt_regex.py:34` (`test_matcher_verdicts_match_the_source`).
- ATI: **in the subset**, 25 of 100 items. 11 of the 25 are `tyh-arith-*`; the 14 word items are
  listed in §4. The entry is the panel-v1 one in `evals/baselines/anti_text_inversion.json`,
  instrument `mt-regex-2026-09-23`. The gate field is `any_hit` (`text_inversion.py:129-145`).
- Floors: prompt-only 0.67 [0.57, 0.76] (stock Qwen, regex, layer 20; `prompt_only.json`
  `typo_mt`) plus a summary-mode entry in `prompt_only_summary.json`. The lucky-guessing builder
  reads `evals/typo_mt/items.json` directly (`baselines/lucky_guessing.py:209-213`; only used
  for `opts=judge=mc`).
- Option goldens for the MC diagnostic: `tests/golden/typo_mt_options.json`, asserted for 100
  items in `tests/test_typo_mt.py:15-33`. Distractors are drawn from the other items' golds, so
  removing items changes the remaining items' option sets.
- Cached numbers (100 items; computed offline from the cached `results.json` rows):

  | run | all | arith | word |
  |---|---|---|---|
  | rl-onchat-x4 native | 89/100 | 4/15 | 85/85 |
  | s3d native | 87/100 | 3/15 | 84/85 |
  | s3d summary-v2 | 86/100 | 2/15 | 84/85 |
  | jlens native | 21/98 | 0/15 | 21/83 |
  | logit native | 23/100 | 0/15 | 23/85 |

- Adapted banks with arith items: `adapted/gemma-4-31b-it/typo_mt.json` (13),
  `glm-5.3-flash` (10), `qwen3-8b` (7), `qwen3.5-9b` (1). The `typo_mt` author brief already
  says "subfamily: always novel" (`adapt/author.py:336-361`), so it never authors new arith
  items.

---

## 2. Change list

### typo

**T1. "drop this from the macro, we don't need it, just keep the hard version"**
- Change: `src/wsbench/evals/typo/__init__.py`:
  `register(dataclasses.replace(bank_family("typo", "Typo"), superseded_by="typo_mt"))`.
  `EvalSpec` is a frozen dataclass that already has `superseded_by` (`registry.py:89-108`), so
  the shared `bank_family` factory (`basic/family.py:31-53`, infra-owned) gets **no new kwarg**.
  Decided (critique item 29): **superseded**, not `not_in_macro`.
- Effect: `results.macro` excludes typo with reason `superseded` (`results.py:258-261`). Every
  `all` default skips it (`registry.drop_superseded`), and gpu.md already drops it from
  `FAMILIES_BP` (no new readouts). It stays frozen and runnable by name, so old run dirs still
  load. Its README floor is **history, not a valid floor** (critique r1-11): typo still
  registers through `bank_family`, so it inherits infra §2.8.1's shared basic PV bump
  (`bank-2026-10-10` -> `bank-2026-10-30`), and `floor_applies` will not draw the old
  `bank-2026-10-10` floor beside the new stamp. No floor is re-measured for it (superseded). The shared tests parametrized over `registry.FAMILIES` minus
  superseded families skip it; its plan row still carries `lite_positions={"kind":
  "final_token"}` from the infra-owned `_final_token_families` branch, so
  `test_every_plan_row_has_lite_positions` holds if it is reached.
- No bank, prompt or ATI change of its own. typo is already `_not_gated`, and its bank stays
  byte identical. It inherits whatever infra / basic_readout change in `basic/` under the bumped
  shared PV; being superseded, it needs no new readouts or floors.
- Docs: in `README.md` §family list (`README.md:161-164`), mark the entry "**superseded by
  `typo_mt`**". Update the `all`-means paragraph (`README.md:83-86`) and the macro footnote
  (`README.md:479-480`). `evals/typo/README.md` gets a one-line status at the top.
  `CLAUDE.md` "today only `multihop_mt` -> `multihop_mt_v2`" becomes "today only `typo` ->
  `typo_mt`" (multihop_mt.md moves multihop_mt to `REMOVED_FAMILIES`, so typo is the
  mechanism's only user, which is why multihop_mt.md keeps the mechanism).
- Tests:
  - new `tests/test_typo.py::test_typo_is_superseded_by_typo_mt`: `SPEC.superseded_by ==
    "typo_mt"`; `results.macro([typo_row, typo_mt_row])` lists typo under `excluded` with
    reason `superseded`; `registry.drop_superseded(["typo", "typo_mt"]) == ["typo_mt"]`.
  - Sanctioned edit of a pre-existing test: `tests/test_registry.py:75-77` asserts
    `registry.superseded() == {"multihop_mt": "multihop_mt_v2"}`. It becomes
    `{"typo": "typo_mt"}` (multihop_mt is in `REMOVED_FAMILIES` per multihop_mt.md; if that
    lands after this PR, the intermediate value is `{"multihop_mt": "multihop_mt_v2", "typo":
    "typo_mt"}`). Only this exact assertion may change.

### typo_mt

**M1. "Drop the arithmetic items"**
- Data: new frozen bank file `evals/typo_mt/items_v2.json` (infra §2.12 naming rule) with the
  85 non-arith items byte identical, in v1 order. Header: v1's header, plus `"version": 2`,
  `"frozen": "2026-10-30"`, `"derived_from": "items.json (sha256 <v1 sha>)"`,
  `"dropped": {"subfamily": "arith", "n": 15, "why": "Camila 2026-10-30: drop the arithmetic
  items"}`, and `gate` with the arith clause ("/ true result") removed.
  `evals/typo_mt/items.json` is untouched.
- Code (the bank-version mechanism and the `mt_family` signature are infra's — infra §2.12,
  §2.16, SHARED_API "Multitoken factory"; `registry.bank_path` honours `EvalSpec.bank`, and
  every reader incl. `lucky_guessing.py:213` and `multitoken/family.py:71` goes through it;
  nothing here re-implements or extends it):
  1. (none — `mt_family(..., bank=)` is infra's; typo_mt only passes it.)
  2. `evals/typo_mt/__init__.py`, the exact shared signature:
     `mt_family("typo_mt", "Typo (multi-token)", calls_per_arm=..., scorer="regex",
     bank=Path("evals/typo_mt/items_v2.json"), instrument_tag="typo-v2",
     min_full_positions=1, full_contiguous=True, task_note=TYPO_MT_TASK_NOTE)` (the last three
     per M3; `prompt_version=None` = the regex default `SCORER_VERSION`; no `flat_types`, no
     `item_task_notes`).
     `instrument_tag` is appended once to the family PV (`JudgeConfig.prompt_version =
     SCORER_VERSION + "+typo-v2"`); every downstream stamp is built from that PV by
     `digest.prompt_version(PV, args, family)` and `reads.stamp(pv, mode)`, so no stamp site is
     edited. It stales the typo_mt floor entries and nothing else. The v2 file gets its own
     `bank_sha` by construction (infra §2.12.4); typo_mt leaves ATI anyway (M4).
  3. Adapted banks (round 2: no family-local `DROPPED_SUBFAMILIES` filter — that was a second
     bank-scoping mechanism inside the shared mt runner). Under `WSB_BANK_ROOT`, `bank_path`
     reads `<root>/typo_mt.json` (no file-name versioning there), so the four adapted banks that
     carry arith items are rewritten **in place** by a one-off script
     `scripts/typo_mt_drop_arith.py` (data change, committed with its output):
     `adapted/gemma-4-31b-it/typo_mt.json` (13 arith), `glm-5.3-flash` (10), `qwen3-8b` (7),
     `qwen3.5-9b` (1) — 31 items. Remaining items byte identical in order; header gains
     `"version": 2` and the same `dropped` block as the frozen v2. The other seven adapted
     `typo_mt.json` banks have 0 arith items and are untouched. Old readout files with
     `tyh-arith-*` rows need no handling: the mt runner already passes the bank's ids to the
     loader (`multitoken/family.py:134-140`, `ids=` kept on the `reads.load` call infra
     §2.16 rewrites), so rows for ids not in the bank are never loaded.
  4. `evals/typo_mt/README.md`: 85 items, no arith wording (lines 5, 10, 12, scored-units
     bullet), the Q11 near-ceiling note, and the Opus prompt-only floor beside the headline.
     The task note moves from `multitoken/prompts.py:52` into `TYPO_MT_TASK_NOTE` (passed as
     `mt_family(task_note=)`, i.e. `EvalSpec.task_note`): "the model reads a sentence that ends
     in a misspelled long word". There are no phrases or
     numbers left; it names no gold word and no tool (`test_every_summary_family_has_task_note_without_gold`,
     `test_no_tool_names_in_prompts`). `atlas/build.py:43` drops "or number".
- Tests:
  - new `tests/test_typo_mt.py::test_v2_bank_drops_exactly_the_arith_items`: v2 has 85 items,
    none with `subfamily == "arith"` or a numeric form; its items equal v1's non-arith items
    exactly; v1 is still 100 items (sha unchanged); `registry.bank_path("typo_mt")` ends in
    `items_v2.json`; header `version == 2`.
  - new `tests/test_typo_mt.py::test_no_reachable_typo_mt_bank_has_arith_items`: for the
    frozen `bank_path("typo_mt")` and every `adapted/*/typo_mt.json`, no item has `subfamily ==
    "arith"` or a purely numeric form; the four rewritten adapted banks equal their old
    non-arith items in order (old shas recorded in the script's output header).
  - new `tests/test_typo_mt.py::test_v1_readouts_with_arith_rows_judge_85_items`: a synthetic
    sidecar'd readouts file (`write_sidecar(..., reads="full", sampling="prose1")`) with rows
    for all 100 v1 ids, judged on v2: `n_items == 85`, no `tyh-arith-*` id in the result rows,
    no exit.
  - Sanctioned edits of pre-existing tests (only these):
    - `tests/test_typo_mt.py:16-17` (`len(items) == 100`) reads `items_v2.json` and asserts
      85. The 100-item assertion moves to a v1 test that keeps the old golden.
    - `tests/test_typo_mt.py:19` uses a NEW golden `tests/golden/typo_mt_v2_options.json`,
      generated by `option_sets` on v2 (options then pass through `mc.options_with_cannot`, so
      `mc.CANNOT` is last; never shuffled in). `tests/golden/typo_mt_options.json` stays,
      asserted against v1.
    - `tests/test_typo_mt.py:41-43` (`prompt_version == "mt-regex-2026-09-23"`) asserts
      `SCORER_VERSION + "+typo-v2"` (imported constant, no literal).

**M2. "Capitalised answer markers are not recognised ... fix this"**
- Change: `multitoken/regex.py:130-152` (`_numeric_matcher`). Compile `after_eq` and
  `cjk_numeral` with `re.IGNORECASE` (`at_start` has no letters). The sample itself is still
  not casefolded, so digit and fullwidth handling are unchanged. This makes `Answer:`,
  `ANSWER:`, `**Answer:**`, `Result:`, `The answer is`, `Total:` and `Equals` hit. Only the
  marker patterns change; multilingual.md's `case_sensitive` path in `unicode_word_matcher`
  (word forms like "Polish") is a different function and is unaffected.
- Docstring: rewrite `regex.py:131-135` to say markers match in any case, a deliberate deviation
  from the source scorer (Camila 2026-10-30).
- Every mt README contract line (`evals/{basic_readout_mt,multilingual_mt,multilingual_multihop,
  multihop_mt_v2,multilingual_typo}/README.md:~38/59/82`) gains "(any case)".
- Version: `SCORER_VERSION` becomes `mt-regex-2026-10-30`. `SUMMARIZED_SCORER_VERSION` is
  retired by infra §2.3.3 (instrument string loses `-summarized`) and is not bumped here. `SCORER_VERSION` is a constant shared by
  every mt family: **one bump per campaign**, covering this fix and multilingual.md's
  `case_sensitive` change together (whichever PR lands first bumps; the other reuses it).
- Proof the fix is verdict-neutral today: it changes the verdict of no frozen-bank item. After
  M1 no frozen bank has a numeric form. Re-matching the cached rl-onchat-x4 arith readouts
  (39 samples carry capitalised markers) gives 4 passes before and 4 after; the audit also
  found no flip. It does affect `adapted/qwen3.5-4b/multilingual_multihop.json`, whose item
  `...-nineteeneightyfour-orwell` has the forms `1984` / `一九八四`. That was a latent false
  negative there too.
- Tests:
  - new `tests/test_mt_regex.py::test_numeric_answer_markers_are_case_insensitive`.
    Hits: `"**Answer:** 429"`, `"Result: 429"`, `"ANSWER IS 429"`, `"The Answer: 429"`,
    `"x Equals 429"`. Misses: `"Answer: 4290"`, `"Answer: 429.5"`, `"429 + 1 = 430"`,
    `"Answer 1429"`.
  - Sanctioned edit of `tests/test_mt_regex.py:34` (`test_matcher_verdicts_match_the_source`):
    the golden file stays the source's verdicts, untouched. The test gets an explicit
    `DEVIATIONS = {("435", "Answer: 435"): True}` (each entry commented with Camila's quote) and
    asserts port == golden except those keys, and port == the deviation value there. This
    sentence is the sanction for that one deviation; nothing else in the goldens may change.

**M3. "Use regex"**
- `scorer="regex"` (SHARED_API assignment, infra §2.16: `EvalSpec.scorer = SCORER`, the
  `opts=judge=mc` diagnostic forced unpinned; held by the shared `test_scorer_enum_assignment`
  and `test_regex_families_unchanged`). No scorer change. The regex contract stays the instrument of record in both native and
  summary mode (D1: summary mode = one digest of all positions × all requested layers, then
  regex on the digest's evidence). `opts=judge=mc` stays a diagnostic, never pinned and never in
  the macro; its options come from `mc.options_with_cannot` (D4, `mc.CANNOT` last).
  After infra §2.3.3 the native regex matches the raw decoded tokens (no `summ:`
  interpretation step).
- D2 (lite/full) uses infra §2.6 only — `ReadSpec.lite_positions`, `reads.load`,
  `reads.select`, `reads.check_full`, `reads.stamp`. typo_mt does no lite filtering of its own
  (critique item 2): `family.last_pos_rows` (`family.py:77-84`) is no longer called for this.
  - Plan row (a `typo_mt` branch in `readplan._plan`, `readplan.py:308-326`; typo_mt leaves the
    `_final_token_families` tuple):
    `ReadSpec("typo_mt", id, "plain", {"kind": "suffix_text", "text": it["typo_word"],
    "from_char": first_diff(it["typo_word"], it["target"])}, GRID,
    lite_positions={"kind": "final_token"}, lite_layers=None)`.
  - `reads=full` (default) = the tokens of the misspelled word from the one holding its first
    misspelled character (the first index where `typo_word` differs from `target`,
    case-insensitive; `readplan.first_diff`) on, and nothing earlier — a leading token that ends
    before that character is a correct prefix the model has only predicted. Every
    prompt ends with `typo_word` (checked on all 100; `adapt/lint.py:228-230` enforces it). An
    earlier-position read would credit a lens for *predicting* the upcoming word before the
    misspelling exists — next-token prediction, which Camila rejects elsewhere ("we are not
    testing next token prediction").
  - `reads=lite` = the final token (today's site). Lite ⊆ full, so one full GPU read serves both.
  - Span sizes on v2 (Qwen3.6-27B tokenizer, offline): 46 items 1 token, 32 items 2, 5 items 3,
    2 items 4 (133 positions; the whole word would be 250, of which 117 positions on 65 items end
    before the misspelling). For the one-token items full == lite.
  - Completeness: `EvalSpec.min_full_positions = 1`, `full_contiguous = True`. `check_full`
    then requires per (item, layer) one contiguous run ending at the max pos. 1 is forced by the
    46 one-token items; consequence: infra's "1 position per cell looks like a lite file" exit
    (which fires only for `min_positions > 1`) does not protect this family; infra guards (i)/(iii) do (below, §6 risk 7).
  - The multi-position refusal (`multitoken/family.py:145-150`, `:580-584`) is deleted by infra
    §2.16 for every mt family (no per-family flag; shared test
    `test_multi_position_file_is_judged`). typo_mt adds no code of its own there.
  - Native pooling, per layer, is the shared mt implementation (infra §2.16; typo_mt writes
    none of it): a form hits when it matches inside ONE sample (one prose sample, one token, or
    one token list space-joined — Q4: tokens of one list may combine). Q4 also allows tokens of
    ADJACENT positions of the same layer to spell one word; that case goes only through
    `digest.gate_texts(cell, col, joined=True, forms=<the item's single-word forms>)`, which
    returns a form as its plain word exactly when `digest.quote_ok` verifies it as a split word
    (infra §2.7.4). It is counted in `extras.n_split_word_hits` so the site can show how many
    passes rest on it (a token lens
    may echo an input prefix token such as " interpret", so the corrective piece must come from
    the lens at the other position). Nothing combines across layers, non-adjacent positions,
    or separate samples (prose1 = one sample; bullet4 = 4 separate samples, per D7 below).
  - Summary mode: the digest takes every cell (`digest.collapse(..., task_note=
    TYPO_MT_TASK_NOTE, expect_all=cells)`, via the shared mt call site); the regex runs on
    `digest.gate_texts(cell, col, joined=True, forms=...)` — evidence spans only, never the
    digest's statements. A word the summarizer *infers* from a token list cannot earn a hit
    (this closes the audit's "summarizer injects chaparral" false positive); a Q4-legal
    split-word quote verified by `digest.quote_ok` is evidence and may hit as its plain word.
  - Stamps: `config.reads`, `sampling`, `sampling_source`, `reader`, `layers_judged` via
    `mcjudge.base_config`; `prompt_version = reads.stamp(digest.prompt_version(PV, args,
    "typo_mt"), mode)` (`+reads-lite` for lite only). Expected full stamp (cited from the
    function, never written as a literal): `digest.prompt_version("mt-regex-2026-10-30+typo-v2",
    args, "typo_mt")`.
- D3: layers = whatever `args.layers` / `layers=all|each|<csv>` selects (infra §2.1); nothing
  hard-coded. Covered by the shared `test_layers_arbitrary` and
  `test_layers_variant_is_complete`, plus the family test below at `layers=44`.
- Full-read guards (infra §2.6.4, round 2; this closes round-1 risk 7): with a sidecar, a
  `reads: "lite"` file under `reads=full` exits 2, and a sidecar `plan_sha` ≠
  `reads.plan_sha("typo_mt")` exits 2 — so a final-token-only file can no longer pass as full
  despite `min_full_positions=1`. Sidecar-less files (cached v1 readouts, old fixtures) are
  report-only (`reads_checked = "no_sidecar"`, `extras.partial_ids_unenforced`); gpu G9 fails
  any campaign result that is not `reads_checked == "sidecar"`.
- D7 (Q1): sampling is declared in the readouts sidecar (`sampling: bullet4|prose1|tokens10`)
  and applied by `reads.load` via `readouts.normalize`; typo_mt never infers it (`sampling=`
  CLI override only; no `auto`). Campaign arm
  s3d-rl600 = `prose1` (its multi-bullet generation is ONE sample); `*-x4` = `bullet4` (4
  separate samples; a form must hit inside one of them); token lenses = `tokens10`.
- Tests:
  - new `tests/test_readplan.py::test_typo_mt_full_reads_the_misspelled_word_lite_the_last_token`:
    for `tyh-novel-interpretability-hand` (tokens `[11 " mechan", 12 "istic", 13 " interpret",
    14 "ibility"]`) full = `[14]` (` interpret` ends before the misspelled `i`, note 8), lite
    rule = `final_token` resolving to `[14]`; a one-token item (`tyh-real-deference`) gives
    full == lite; `test_typo_mt_full_span_starts_at_the_first_misspelled_character` pins
    acciacatura (`[" acc", "iac", "atura"]` -> `atura` only) and anaphlyaxis (`ly`, `axis`).
  - new `tests/test_mt_regex.py::test_run_regex_pools_positions_within_a_layer`: two positions
    at L44; the form only in pos 13 -> pass; a form spelled by one token at pos 13 + one at pos
    14 of the same layer -> pass (`n_split_word_hits == 1`); the same pieces at non-adjacent
    positions, or at different layers -> fail; two whole words from separate samples -> fail.
  - new `tests/test_typo_mt.py::test_reads_lite_uses_shared_select`: under `reads=lite` the
    judged cells equal `reads.select(cells, reads.specs("typo_mt"), "lite")` and the PV ends in
    `+reads-lite`; no typo_mt code calls `load_readouts` (also enforced by the shared
    `test_no_family_calls_load_readouts_directly`).
  - new `tests/test_typo_mt.py::test_full_partial_span_is_flagged`: a sidecar'd file
    (`write_sidecar(path, reads="full", sampling="prose1", plan_sha=reads.plan_sha("typo_mt"))`)
    missing the max pos of a 3-token item exits 2 (or is `partial` under `allow_missing`), via
    `check_full`; the same file without a sidecar is judged with the id in
    `extras.partial_ids_unenforced`.
  - new `tests/test_typo_mt.py::test_lite_sidecar_file_refused_under_full`: a final-token-only
    file whose sidecar says `reads: "lite"` exits 2 under `reads=full` and is judged under
    `reads=lite` (the family instance of infra guard (i), needed because
    `min_full_positions=1`).
  - Shared tests this family is held to (infra, parametrized over `registry.FAMILIES`):
    `test_every_plan_row_has_lite_positions`, `test_every_lite_rule_is_cell_resolvable`,
    `test_lite_is_subset_of_full`, `test_every_mc_judge_ends_with_cannot`,
    `test_every_summary_family_has_task_note_without_gold`, `test_no_hardcoded_items_json`,
    `test_layers_arbitrary`, `test_layers_variant_is_complete`, `test_no_tool_names_in_prompts`,
    `test_no_family_calls_load_readouts_directly`, `test_single_global_token_cap`; round 2:
    `test_scorer_enum_assignment`, `test_sidecarless_file_is_report_only`,
    `test_bank_pv_bumped_when_prompts_change`; round 3: `test_token_note_rendered_from_spec`
    (the `opts=judge=mc` diagnostic prompt), `test_digest_line_shows_bullet_boundaries`
    (digest input the regex evidence comes from).
  - Sanctioned edit: any existing test asserting the refusal message "this family reads the
    final prompt token only" (grep `tests/`) is deleted with the refusal (shared mt change).

**M4. "This should not be in ati"**
- Data: delete the `typo_mt` panel entry from `evals/baselines/anti_text_inversion.json`. Add
  `_not_gated["typo_mt"] = "excluded from the ATI subset by design (Camila 2026-10-30)"`
  (infra §2.13: families Camila removes from ATI are removed).
- Code: add the same key to `NOT_GATED` (`text_inversion.py:85-103`). Remove `"typo_mt"` from
  `STRICTER_PASS_FIELD`'s `any_hit` tuple (`text_inversion.py:139-141`).
- Docs: `evals/baselines/README.md` §Not gated (`:366-368`): add typo_mt. Totals (`:393-397`)
  drop by 25 (1126 -> 1101 in the subset today); the final totals are recomputed once from the
  file after every workstream's ATI edits. Remove the typo_mt row (`:425`).
- Tests:
  - new `tests/test_text_inversion.py::test_typo_mt_is_not_gated`: `"typo_mt" in
    ti.NOT_GATED`; no `typo_mt` key in the ATI file except under `_not_gated`; running typo_mt
    with `anti_text_inversion=True` raises `NotInScope` (exit 0).
  - Sanctioned edit: `tests/test_ati_panel.py:562` loops over `("multilingual_mt",
    "basic_readout_mt", "typo_mt")` to test the `any_hit` gate field. Replace `typo_mt` with
    `multilingual_typo`. The assertion is unchanged.
  - `test_bank_sha_unchanged_for_untouched_families` does not cover typo_mt (touched, and no
    longer in the ATI file); typo is untouched but `_not_gated`, so it has no stored sha.
- Run phase: gpu G13 table already lists typo_mt as "removed from ATI (Camila)"; no re-gate.

**M5. Verdict-level leniency audit (critique r1-7; feedback.md general: "Audit to make sure it
is neither too strict nor too lenient").**
- No family protocol: typo_mt is in the shared gpu G12 / R4b audit (`scripts/audit_verdicts.py
  sample` -> fresh-context auditor -> `table`), ≥ 30 verdicts stratified pass/fail × prose
  (s3d-rl600 or mlnla-rl2-2000) / token (jlens) from the all-layer full runs. Regex is
  deterministic, so there is no Opus-judge column to audit; the `opts=judge=mc` diagnostic is
  not audited (not the instrument).
- Stratum (critique r2 item 14, shared mechanism only): the shared mt regex path writes a
  per-row boolean `split_word_hit` (true when the item's pass rests on a `gate_texts(joined=True,
  forms=)` split word; its sum is `extras.n_split_word_hits`). gpu's `STRATA` table gains
  `typo_mt: split_word_hit` and the R4b command line gains `--strata typo_mt=split_word_hit`, so
  the sample holds ≥ 10 split-word passes (all of them if fewer) besides the pass/fail × prose /
  token strata. typo_mt adds no sampling code.
- The auditor brief for typo_mt carries this spec's pass rule (a form inside ONE sample's
  evidence, or a `quote_ok`-verified split word of adjacent positions of one layer) and the
  three known case shapes to check for: (a) no commitment — `tyh-real-adsorption` passing on
  ", not adsorption, ... the precise term is absorption" (A6; documented limitation, counted as
  `ambiguous`, not re-tuned); (b) summarizer-inferred words ("chaparral") — must be 0 after
  `gate_texts` evidence-only scoring; (c) split-word passes resting on an echoed input prefix
  (` interpret` from the prompt + lens `ibility`) — sampled through the `split_word_hit`
  stratum above.
- Gate (gpu G12): `n_too_lenient + n_too_strict ≥ 3` flags typo_mt on the site and opens a fix
  item **before R6 / R8 and the site build** (round 3); never silently re-tuned. A flagged typo_mt
  goes through gpu **R4c**: fix PR with a new `instrument_tag` (e.g. `typo-v2.1`, so the PV
  changes once via `mt_family(instrument_tag=)`), R2/R2b only if the fix changes the bank or the
  read site (`plan_sha`), R4 re-run for typo_mt (s3d-rl600 12 configs, jlens and mlnla-rl2-2000
  all-layer full + lite, `opts=judge=mc` column), R4b re-run with seed suffix `r<k>`, at most 2
  rounds; still flagged after round 2 → site "New errors found". Case (a) (no commitment) is a
  documented limitation (A6) and is labelled `ambiguous`, so it does not count toward the gate.

---

## 3. Data needs

- **Bank:** `evals/typo_mt/items_v2.json` (85 items = v1 minus `subfamily == "arith"`). The v1
  file is untouched. PV `SCORER_VERSION + "+typo-v2"`.
- **New items:** none. Camila asked only for removal. No Qwen gating is needed: the 85 items
  keep their 2026-09-10 gate (greedy + ≥ 8/10 at T = 0.7), which dropping other items does not
  invalidate (gpu.md §3.2 "typo_mt (existing gate stands)").
- **Readouts to regenerate (GPU, run phase, gpu.md):**
  - full: the `suffix_text typo_word from_char` span for all 85 items (133 positions) × the 11
    GRID layers = 1,463 cells per arm, with a declared sidecar (`reads: full`, `sampling`,
    `reader`, `arm`, `layers`, `plan_sha = reads.plan_sha("typo_mt")`). Campaign arms (gpu
    G14, SHARED_API "Producer / run"; typo_mt is in `FAMILIES_BP`): `s3d-rl600` (`prose1`,
    the 12 configs), and the required r2 arms `jlens` (`tokens10`) and `mlnla-rl2-2000`
    (`prose1`), all-layer, full + lite. Any other arm (e.g. `rl-onchat-x4`, `bullet4`) is
    "cached v1 readouts, judge test only".
  - lite: comes from the full read (lite ⊆ full). The cached final-token files are usable as
    lite files only through `reads=lite`; with a `convert-*`-written sidecar declaring
    `reads: "lite"` they are enforced, without one they are report-only (`no_sidecar`). They
    are never judged as full (guard (i) with a sidecar; G9 without).
  - typo: nothing (superseded, not in `FAMILIES_BP`).
- **Baselines:**
  - prompt-only: protocol `po-opus-v1` (infra §2.11) — one Opus 5.5 readout per id, rendered
    through the last full-read site (the final token), one prose cell at that pos, layer 44,
    judged by `wsbench run all=True readouts_root=<dir>/readouts` (no `layers=`, no `reads=`),
    so it gets the same digest + regex. Floor = typo_mt's own headline (regex `pass_rate`) on
    that file, family CI, n = judged − refused, `not_measurable` if > 20% refused; the
    prompt-only sidecar `reader: prompt_only:…` waives `select` / `check_full`. Frozen into `evals/baselines/prompt_only_summary.json`;
    drawn iff `summary_floor_applies` on `strip_reads(prompt_version)`. The 2026-09-23 stock
    Qwen floor (0.67) is archived with the rest of the Qwen file and never drawn.
    Timing (SHARED_API r3): measured at gpu R6, after R4c closes, on typo_mt's final PV; if
    R4c changes typo_mt's `instrument_tag` after R6, `report` shows "floor re-measured:
    pending" until R6 re-runs for typo_mt (never the stale floor). gpu `audit_run.py` asserts
    `strip_reads(prompt_version)` == the floor's `instrument` (typo_mt has no ATI entry, so the
    ATI half of that check does not apply).
  - lucky-guessing (MC diagnostic only) is regenerated from v2 by `wsbench baseline` (reads
    the bank through `bank_path`); never drawn beside a regex number.
- **Goldens:** new `tests/golden/typo_mt_v2_options.json` (generated, not hand-written).
- **Spend:** regex scoring is free; only the summarizer (Opus 5.5 digest, one call per item
  under `digest.DEFAULT_TOKEN_CAP`) and the prompt-only ask cost API calls. Smoke `limit=3` first, measure, then the full run (decision "Spend").

---

## 4. Answers

There is no direct question in the typo / Typo mt sections. These answers cover the implicit
ones and the facts the implementer and Camila need.

- **A1. Is the case bug real, and does fixing it change any score?** Yes, it is real:
  `unicode_word_matcher("435")("Answer: 435")` returns False today. The source golden even pins
  that miss. The fix changes no current frozen-bank score:
  - after M1, no frozen bank has a numeric form;
  - before M1, re-matching the 39 capitalised-marker samples in the cached rl-onchat-x4 arith
    readouts flips 0 items (4 passes before and after).

  It matters for future numeric banks and for one adapted item
  (`adapted/qwen3.5-4b/multilingual_multihop.json`, the "1984" bridge).
- **A2. What does dropping arith remove?** It removes all 11 non-word fails of the best O-lens:
  the rl-onchat-x4 arith items pass 4/15, and all 4 passes were coincidental "= gold" equations
  per the audit (`tyh-arith-005`, `-512m348`, `-add-47-76`, `-812minus379`). It also removes 11
  of typo_mt's 25 ATI items. Cached rates on the remaining 85 (final-token = lite reads):
  - rl-onchat-x4 85/85 = 1.00
  - s3d native 84/85 = 0.99
  - s3d summary 84/85
  - J-lens 21/83 = 0.25
  - logit 23/85 = 0.27
- **A3. Is typo_mt (the "hard version") still discriminative without arith?** Barely for prose
  lenses. The frozen panel record on the 85 word items: Qwen 71/85, Opus 83/85, Astra 77/85 and
  Argon 83/85 solve the item from the prompt text alone. The Opus prompt-only floor will likely
  be ≈ 0.95-1.0, while prose lenses score 0.99-1.00; the gap left is token-vs-prose lenses.
  **Decided (Q11): keep it as the hard version and note near-ceiling on the site** (README
  status line + site family note, E-Q11). No new items.
- **A4. How is the typo_mt prompt-only baseline judged today, and after?** Today: stock
  Qwen3.6-27B summaries (`baselines/prompt_only.py:1-3`), scored by the same regex at layer 20
  (`prompt_only.json` `typo_mt`: `judge_model: regex`, `layers_judged: [20]`), plus a
  summary-mode entry. After: `po-opus-v1` (§3), the same digest + regex; `report` draws it only
  while `strip_reads(prompt_version)` and the summarizer key match.
- **A5. Should the misspelling's earlier tokens be read?** In full mode, yes: every token of the
  misspelled word. Not the sentence before it, which would test prediction rather than
  correction (M3).
- **A6. Not asked but found:** the regex has no commitment check. `tyh-real-adsorption` passes
  on ", not adsorption, ... the precise term is absorption" (audit, `ambiguous`). Camila said
  "Use regex", so this is left as a documented limitation in the README, not fixed.

**Decisions taken (override if you disagree)** — listed by `site/build.py` in section 4:
- typo leaves the macro as **superseded by typo_mt** (out of `all` too), not `not_in_macro`;
  it stays runnable by name, gets no new readouts and no floor.
- typo_mt stays the hard version although it is near ceiling for prose readers (Q11).
- Full read = the misspelled word's tokens from the first misspelled character on — not the
  sentence before it and not a correct prefix of the word (no next-token-prediction credit); lite = the final token.
- Numeric answer markers match in any case — a deliberate deviation from the source scorer's
  pinned golden (one `DEVIATIONS` entry).
- The four adapted typo_mt banks that held arith items are rewritten in place (31 items
  dropped); their old adapted-model results are stale, not compared.
- The regex has no commitment check ("not adsorption … absorption" passes); documented, not
  fixed, because Camila asked for regex.

---

## 5. Evidence plan (website artefacts; regex is offline, digests/floors are API runs)

| id | artefact | before -> after |
|---|---|---|
| E-T1 | `wsbench report` macro row on a run containing typo + typo_mt | typo in `families` -> typo under `excluded: superseded (typo_mt)`; macro value recomputed without it |
| E-M1 | typo_mt results on the cached rl-onchat-x4 readouts ("cached v1 readouts, judge test only"; `reads=lite`, final token, `reads_checked=no_sidecar`) | n_items 100, 0.89 -> n_items 85, 1.00 (85/85). Also s3d native 0.87 -> 84/85, jlens 21/98 -> 21/83. `tyh-arith-005` row: PASS via "456 + 389 = 435" -> row absent. Plus the 4 adapted-bank diffs (31 arith items removed, header `dropped`) |
| E-M2 | unit-test table on the site: sample -> hit | `"**Answer:** 429"`, `"Result: 429"`, `"Answer: 435"`: miss -> hit (`tyh-arith-3a` form 429); controls `"Answer: 4290"`, `"429 + 1 = 430"` stay miss. Plus "0 verdict flips on every frozen bank" (re-score all mt families' cached runs under both scorer versions; identical rows) |
| E-M3 | dry-run plan rows (`wsbench plan family=typo_mt`) for `tyh-novel-interpretability-hand` and `tyh-real-deference` | lite `final_token` -> pos 14 (`ibility`); full `pos [14]` (`ibility`; ` interpret` is a correct prefix, note 8); deference full == lite. After GPU regen: a full vs lite results pair per required arm (s3d-rl600, jlens, mlnla-rl2-2000), with `n_split_word_hits`, `reads_checked=sidecar` |
| E-audit | gpu G12 site table row for typo_mt (R4b, and each R4c round if flagged) | none -> n, n_too_lenient, n_too_strict, n_ambiguous with every non-ok case verbatim; n per `split_word_hit` stratum; cases (a)-(c) of M5 reported explicitly; if still flagged after R4c round 2, listed under "New errors found" |
| E-M4 | `wsbench run ... anti_text_inversion=True families=typo_mt` | 25-item run -> `NotInScope`, skipped (exit 0); ATI table without the typo_mt row; new totals |
| E-Q11 | site family note + `evals/typo_mt/README.md` status | "hard version; near ceiling for prose readers (Opus prompt-only ≈ <floor>)" with the measured floor |
| E-floor | `report` for typo_mt | prompt-only 0.67 (stock Qwen, archived to `evals/baselines/archive/`) -> Opus `po-opus-v1` floor from `evals/baselines/prompt_only_summary.json` (measured at R6 after R4c), drawn beside every lens number (full and `+reads-lite`, matched on `strip_reads`); `audit_run.py` instrument check passes |

---

## 6. Risks / conflicts, and every shared file touched

Uses (owned by infra, not edited here beyond the typo_mt rows): `reads.py`, `ReadSpec.lite_*`,
`registry.bank_path`, `digest.collapse` / `quote_ok` / `gate_texts` / `prompt_version`,
`mt_family` (infra §2.16), `mc.options_with_cannot`, `readouts.normalize`,
`baselines/prompt_only_opus.py`, `scripts/audit_verdicts.py` (gpu G12), `lucky_guessing` bank
reads, `tests/conftest.py::write_sidecar`.

Files this workstream edits that others also touch (land one owner per file):

- `src/wsbench/multitoken/regex.py`: case-insensitive markers and the ONE campaign
  `SCORER_VERSION` bump (shared with multilingual.md's `case_sensitive` change). This stales
  every mt family's floors and ATI entries (instrument `mt-regex-2026-09-23`: basic_readout_mt,
  multihop_mt_v2, multilingual_mt, multilingual_multihop, multilingual_typo). Those families
  are re-gated in the run phase anyway (ATI decision). Never hand-restamp ATI entries.
- `src/wsbench/multitoken/family.py`: **not edited by this workstream** (round 2). `bank=`,
  `scorer=`, `instrument_tag`, `task_note`, the `reads.load` call sites, the refusal deletion,
  per-layer pooling and `n_split_word_hits` are infra §2.16 / §2.7.4.
- `src/wsbench/multitoken/prompts.py`: delete the typo_mt task-note line (52); the note lives in
  `evals/typo_mt/__init__.py` as `TYPO_MT_TASK_NOTE`.
- `adapted/{gemma-4-31b-it,glm-5.3-flash,qwen3-8b,qwen3.5-9b}/typo_mt.json` (arith removed) and
  `scripts/typo_mt_drop_arith.py`.
- `src/wsbench/readplan.py`: the typo_mt branch (full `suffix_text` with
  `from_char`, lite `final_token`).
- `src/wsbench/evals/typo/__init__.py` only (`dataclasses.replace`); `basic/family.py` is not
  edited here.
- `src/wsbench/baselines/text_inversion.py`: `NOT_GATED`, `STRICTER_PASS_FIELD`.
- `evals/baselines/anti_text_inversion.json`, `evals/baselines/README.md` (totals).
- `README.md` (family list, `all`/macro paragraphs, judge table lines 410-411), `CLAUDE.md`
  (superseded list), `atlas/build.py:43`, every mt family README contract line ("any case").
- Tests: `tests/test_registry.py`, `tests/test_mt_regex.py`, `tests/test_ati_panel.py`,
  `tests/test_typo_mt.py`, `tests/test_typo.py`, `tests/test_readplan.py`,
  `tests/test_text_inversion.py`.

Risks:

1. **Saturation (A3, Q11):** kept by decision; the site carries the near-ceiling note.
2. **Version-stamp cascade (M2):** the shared scorer bump must land in the same campaign phase
   as the other mt workstreams' re-gating, or `anti_text_inversion=True` exits 2 on those
   families in between. One bump, landed with the first mt PR.
3. **Golden deviation (M2):** the one sanctioned `DEVIATIONS` entry is the only allowed change
   to source-pinned goldens. A reviewer must reject any other golden or assertion edit.
4. **Old readout files** still carry `tyh-arith-*` rows. They are never loaded (the bank's ids
   are the loader's `ids=`), never fatal; `test_v1_readouts_with_arith_rows_judge_85_items`
   pins this.
5. **Split-word hits on token lenses (Q4):** allowed by the decision; reported as
   `n_split_word_hits` so a pass that rests on an echoed input prefix is visible.
6. **Naming:** PR #75's `tier=` is independent of `reads=` (decision); nothing here uses `tier=`.
7. **Lite-file guard gap — resolved by infra §2.6.4 (i) + (iii):** a sidecar `reads: "lite"`
   under `reads=full` exits 2, and `plan_sha` drift exits 2. Residual: a sidecar-less
   final-token file is report-only under `reads=full`; gpu G9 (`reads_checked == "sidecar"`)
   keeps it off the site. Family test `test_lite_sidecar_file_refused_under_full`.
8. **Split-word evidence in summary mode — resolved by infra §2.7.4:**
   `gate_texts(joined=True, forms=)` returns a `quote_ok`-verified split word as its plain word
   (`test_digest.py::test_gate_texts_joined_returns_split_word`).
9. **Adapted banks rewritten in place (M1.3):** their shas change; any cached adapted-model
   typo_mt result is stale by bank and is re-run, not compared (adapted banks are outside ATI).
10. **Owner of `split_word_hit` / `n_split_word_hits`:** infra §2.7.4 says "the family counts
   `extras.n_split_word_hits`", but the regex pooling that produces split-word hits is the
   shared mt path (infra §2.16) used by multilingual_mt, multilingual_typo and typo_mt alike,
   and typo.md does not edit `multitoken/family.py`. This spec assumes the counter and the
   per-row `split_word_hit` field land once in that shared path (infra PR). If infra keeps the
   count family-local, typo_mt would need its own post-pass over result rows — not planned
   here. Open for infra to confirm.

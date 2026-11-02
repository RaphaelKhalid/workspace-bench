# Workstream spec: jlens_pr (family `jlens_concept_pr`, "J-lens precision recall")

Code of record: `/root/wsb-bp-base` @ origin/main cd6b0fa. All `file:line` refs are against that tree.
Feedback section: "J-lens precision recall" (4 sentences). Every number below that says "measured"
was computed offline in this scoping pass (no LLM calls) by re-scoring the cached judged run
`/workspace/gw-relational-ar/outputs/wsb_latest/outputs/judged/rl-onchat-x4/jlens_concept_pr/cells.jsonl`
with the repo's own `score.score` (re-score reproduces the published numbers exactly: P@44 0.3154,
R@10 0.5965) and by scanning the shipped reference files.

**Round 1 (2026-10-30).** Aligned to `SHARED_API.md`, `infra.md` and `_fable_decisions.md` (Q2:
this family stays `NATIVE_ONLY`). Every shared name below is infra's; this spec builds none of
them. Shared names this family uses, and where:

| shared name | used for | section |
|---|---|---|
| `reads.load(args, FAMILY, positions=...)` | the ONLY loader (replaces `load_readouts` at `judge.py:43, 208`) | C2, C3, C7 |
| `reads.mode`, `reads.stamp` | `config.reads`; PV `jlens-pr-v3` (+`+reads-lite` under lite) | C2 |
| `ReadSpec.lite_positions = {"kind": "final_token"}`, `lite_layers=None` | plan row | C2 |
| `EvalSpec.min_full_positions=1`, `full_contiguous=False` | `reads.check_full` inside `reads.load` | C2 |
| `readplan.plan(layers=...)`, CLI `layers=all\|each\|<csv>`, `mcjudge.is_subset` | layers | C3 |
| `readouts.normalize` (via `reads.load`), sidecar `sampling`, `readouts.bulleted` | samples per cell, one-string join | C7 |
| `mcjudge.base_config` stamps (`reads`, `sampling`, `sampling_source`, `reader`, `layers_judged`) | config | C2, C3, C7 |
| `mc.READOUT_PHRASE`; `tests/test_prompt_tool_names.py::test_no_tool_names_in_prompts` | prompt wording | Item 3, C5 |
| `digest.NATIVE_ONLY` (`{"jlens_concept_pr"}`), `prompt_only.EXCLUDED` (`{"jlens_concept_pr"}`) | stays native / no floor | C1, C8 |
| `registry.bank_path` | bank dir | C9 |
| full-read guards (r2): sidecar `plan_sha` == `reads.plan_sha(FAMILY)`, plan-layer guard, `reads: lite` sidecar refused under `reads=full`; sidecar-less = report-only (`config.reads_checked="no_sidecar"`, `extras.partial_ids_unenforced`) | inside `reads.load` | C2, C7 |
| `tests/conftest.py::write_sidecar`, `tests/conftest.py::native_args` | test fixtures | C2, C7, C11 |
| `scripts/audit_verdicts.py sample\|table` (*gpu* G12 / R4b), the ONE leniency audit | verdict audit | C11 |
| campaign arms `s3d-rl600` (`prose1`), `mlnla-rl2-2000` (`prose1`) (*gpu* G14) | judged arms | C12 |
| `audit_verdicts.py sample --strata jlens_concept_pr=kind`, R4c fix loop (*gpu* G12, r3) | audit strata, fix-and-rerun | C11 |
| `results.MACRO_METRICS`, `EvalSpec.not_in_macro = ""` (infra §2.17, r3) | out of macro by metric | C13 |
| `site/manifest.json` rows `{sentence_id, …, status}` (*gpu* G11, r3) | coverage map | §5.1 |
| `scripts/audit_run.py` (*gpu* G9) | run audit (native-family exemptions, Risks) | §6 |

**Round 2 (2026-10-30).** Re-checked against SHARED_API r2. Changes: C11 (critique r1 item 7: this
family had no verdict audit; it now feeds G12 with its own verdict unit), C12 (G14's required arms:
`mlnla-rl2-2000` is judged here; the `jlens` arm is not an arm of this family), C3(d) / §4.3
corrected (separate out dirs do NOT share this family's call cache, so per-layer configs cost
calls; the earlier "0 new calls" claim is withdrawn), C2 / C7 state the r2 sidecar guards. No
retired name is used (checked against the SHARED_API retired lists).

**Round 3 (2026-10-30).** Re-checked against SHARED_API r3, `_fable_decisions.md` and
`_critique_r2.md`. No r2 critique item names this spec; the shared r3 changes that reach it are
applied: C11 uses G12's r3 `--strata <family>=<field>` form and the R4c fix loop (critique r2
items 6, 14) instead of "fix item before merge"; NEW C13 states macro membership under
`results.MACRO_METRICS` (r3) with `not_in_macro=""` (never `None`); C7 states that
`digest.BULLET_MARK` / `statement_lines` / `number_flood` (r3, critique r2 items 4, 12) do not
reach this family (no digest; Stage A reads the raw `readouts.bulleted` text, real newlines kept);
NEW §5.1 gives the `site/manifest.json` coverage map (gpu G11, critique r2 item 5): every
sentence of Camila's section → change → named test → evidence row. Round 3 adds names to the
table below: `scripts/audit_verdicts.py sample --strata jlens_concept_pr=kind` and R4c (*gpu*
G12), `results.MACRO_METRICS` / `EvalSpec.not_in_macro` (infra §2.17), `site/manifest.json` /
`site/build.py` (*gpu* G11), `scripts/audit_run.py` (*gpu* G9). No r3 retired name is used.

Not used (and not re-implemented here): `digest.collapse`, `digest.quote_ok`,
`digest.statement_lines`, `digest.number_flood`, `digest.BULLET_MARK`, `mc.CANNOT`,
`mc.options_with_cannot`, `mc.token_note`, `EvalSpec.task_note`, `EvalSpec.flat_types` (no
summarizer, no MC, no relational pick; see C1, C4, C5, C7).

---

## 1. Current state

**What it measures.** For each of 299 captured activations (150 chat + 149 pt rollouts of
Qwen3.6-27B), how much of a prose arm's text at one (label, layer, pos) is supported by the frozen
J-lens top-10 at the same activation (precision, headline) and how much of the top-10 it covers
(recall@10, extras). `group="precision"`, `chance=None`, excluded from the `pass_rate` macro
(`src/wsbench/evals/jlens_concept_pr/__init__.py:11-28`).

**Positions.** Exactly one read position per label: `manifest.json` `eval_positions[0]` in the
generated region (`judge.py:129-134`; readplan rule `{"kind": "positions", "positions":
p["eval_positions"]}` render `captured`, `src/wsbench/readplan.py:614-630`). Rows at any other pos
are skipped (`judge.py:207-208`, `positions={id: [pos]}`).

**Layers.** Readplan emits `GRID = 20..60 step 4` (`readplan.py:16`). Reference files exist for
those 11 layers plus `L042` (`evals/jlens_concept_pr/gen-jlens-pr-jlens/<label>/L0NN.jsonl`).
The judge uses `layers=` or every layer in the readouts file (`judge.py:212`); ANY layer without a
reference file is fatal (exit 2) before any call (`judge.py:213-216`). Headline layer: the single
judged layer, else L44, else `None` → `value=None, complete=False` (`score.py:384-389, 461-466`).
Each (label, layer) cell is judged independently, so an 11-layer run already contains the 11
single-layer results (`extras.by_layer`, `score.py:460`).

**Inputs.** Prose only; a tokens file is refused (`judge.py:209-211`). Cell text =
`concat_samples(samples)` = every non-empty sample joined by `\n---\n`, no k cap
(`prompts.py:162-164`, `judge.py:264`). In-house O-lens arm: 8 samples per cell.

**Judge (not MC; three graded stages, all on the family judge `DEFAULT_JUDGE` = claude-opus-5-5,
`prompt_version="jlens-pr-v2"`, `prompts.py:21`):**
- Stage A, concept split: `STAGE_A_SYSTEM` `prompts.py:23-36`, one call per cell with text
  (`judge.py:261-287`).
- Stage B, per-token recall grades (in/partial/out) for every content reference token
  (`STAGE_B_SYSTEM` `prompts.py:38-53`; `judge.py:289-307`), plus the **foil** pass `:Fnn` on the
  derangement partner's tokens — on by default (`judge.py:293-296`).
- Stage P, per-concept precision grade against the cell's content-token SET (`STAGE_P_SYSTEM`
  `prompts.py:83-110`, T=0, ≤60 concepts per chunk, `judge.py:323-350`); **pfoil** `:Qnnn` only
  with `opts=stage_p_foil=1` (`judge.py:232, 327-329`).
- Content filter for B and P: `is_content_token` (`concept_pr.py:214-220`) = `classify_token` ∈
  {WORD, CJK} (`token_types.py:120-142`) or `has_emoji` (any char of Unicode category `So`,
  `concept_pr.py:208-211`). Used at `judge.py:298, 333` and `score.py:269, 303`.
- Scoring: precision = mean Stage-P grade over concepts; recall@10 = exact hypergeometric
  expected max grade (`concept_pr.py:232-290`); statuses ok/missing_a/incomplete_b/missing_p
  (`score.py:244-282`); `chance_label = "shuffled-partner foil precision (measured, see
  extras.foil)"` (`score.py:178, 508`).

**Summary-mode path.** None. The family is in `digest.NATIVE_ONLY` (`src/wsbench/digest.py:171-174`,
"precision is measured against the J-lens top-10 at one (layer, pos); a summary has no reference");
under `aggregate=summary` the runner stamps `config.aggregate="native"` + `extras.summary_mode_note`
(`src/wsbench/runner.py:103, 124-128`). Excluded from prompt-only (`baselines/prompt_only.py:25,
76, 110`) and ATI (`evals/baselines/anti_text_inversion.json:29`, `baselines/text_inversion.py:87`).

---

## 2. Change list

Prompt/instrument stamp for every item below: **`jlens-pr-v2` → `jlens-pr-v3`** (one bump,
`prompts.py:21`; README table `README.md:397`; family README `evals/jlens_concept_pr/README.md:45-50`).
No bank file changes (the reference files are untouched; the content filter is code).

### Item 1 — foil precision 0.0 instead of "not measured"
> "Fix Bug: with the foil step off (the default), the foil precision reports 0.0 instead of 'not
> measured', while the chance label advertises a measured foil. Return null when no foil call ran,
> or turn the foil on by default."

**Root cause (reproduced).** Without pfoil, `score.score` still scores every foil cell
(`score.py:444-458`) with `support=support["pfoil"].get(key)` = None. Cells WITH concepts become
`missing_p` (excluded), but zero-concept cells (empty text or empty concept list) return `ok` with
precision `0.0` (`score.py:261-269`), so `block()`'s `foil_precision` (`score.py:362`) is the mean of
those zeros. Re-scoring the cached rl-onchat run with the pfoil rows removed gives
`by_layer.foil_precision = None` at L20–L44 but **`0.0` at L48, L52, L56, L60** (the 4 empty-text
cells `chat-dailydialog-0050__L048/L052__p50`, `chat-lmsys-0013__L056/L060__p81`), and per-row
`foil_precision = 0.0` on those 4 rows, while `chance_label` claims a measured foil.

**Fix (do both halves):**
1. **Foil on by default.** `judge.py:232`: `pfoil = args.extra.get("stage_p_foil", "1") != "0"`;
   opt-out with `opts=stage_p_foil=0`. Update docstrings `judge.py:12-13`, README lines 62-68, 86.
   Cost: ≈ +3.2k Stage-P calls per 11-layer arm (cached run: 3,159 Q keys vs 3,160 P keys), ~+9%.
2. **Null when not measured.** `score.score` gets a `foil_precision_measured: bool` argument
   (passed from `judge.run` as `pfoil`). When False: per-row `foil_precision = None`
   (`score.py:457`), `block()` `foil_precision = None` (`score.py:362`), `extras.foil.precision =
   None`, and `chance_label = "shuffled-partner foil precision: not measured (stage_p_foil=0)"`
   (new constant `CHANCE_LABEL_UNMEASURED` beside `CHANCE_LABEL`, `score.py:36`; the label is
   chosen where it is used, `score.py:366`). When True: unchanged maths.
   `foil_recall_at_10` is unaffected (Stage-B foil always runs). Rule: a foil precision number is
   reported ONLY when at least one Q call returned for that block; a block whose foil cells are
   all zero-concept with no Q call reports `None`, never 0.0 (closes the same hole when pfoil is
   on but a layer's foil cells are all empty).
3. Website: print the foil precision beside every precision number (it is the family's floor),
   and print "not measured" (never 0.0) where it is `None`.

**Tests.**
- NEW `test_foil_precision_is_null_without_pfoil` (score-level, offline): inputs with one
  zero-concept cell at L48 and `foil_precision_measured=False` → `by_layer["48"]["foil_precision"]
  is None`, the row's `foil_precision is None`, `chance_label == CHANCE_LABEL_UNMEASURED`.
- NEW `test_pfoil_runs_by_default` (fake LLM): no `stage_p_foil` opt → Q calls issued,
  `config.stage_p_foil is True`, `extras.foil.precision` is a number, `chance_label ==
  CHANCE_LABEL`.
- NEW `test_stage_p_foil_opt_out` (`stage_p_foil=0`): no Q calls, `extras.foil.precision is None`.
- Existing `test_pfoil_opt_measures_foil_precision` (`tests/test_jlens_concept_pr.py:495`) passes
  unchanged (`stage_p_foil=1` still means on).
- **Sanctioned pre-existing-test edits (exactly these, no assertion changes):**
  `test_stage_sequencing_models_and_numbers` (`:394`) and `test_reject_handling_and_resume` (`:452`)
  get `extra={"stage_p_foil": "0"}` added to their `jargs(...)` call, because they assert the
  no-pfoil call sequence (`["P"] * 3`, `stage_p_foil is False`, `foil == {..., "precision": None}`,
  `len(failed) == 2`). Their assertions stay byte-identical; any other edit to them is a red flag.

### Item 2 — exclude broken-character fragments and special tokens (recall denominator)
> "Broken-character fragments and special tokens like <|...|> are treated as content and enter the
> recall denominator (2.9% of reference cells). Exclude them."

### Item 4 — same defect, mechanism
> "Fix: U+FFFD byte-fragment tokens and special tokens count as content: is_content_token('�') is
> True (category So -> has_emoji), and '<|fim_middle|>' classifies as WORD. They get Stage-B calls,
> are always 'out', and depress recall@10, and they also appear in the Stage-P token list"

(Items 2 and 4 are one fix; listed together.)

**Verified.** `is_content_token("�")` → True (`classify_token` → SYMBOL, then `has_emoji`
because U+FFFD is category So); `is_content_token("<|fim_middle|>")` → True (WORD). Scan of all
3,588 shipped reference cells (11 grid layers + L42): **209 U+FFFD tokens in 97 cells** (`' �'` ×134,
`'�'` ×75; none mixed with letters) and **special/control tags: `<|endoftext|>` 19, `<|im_end|>`
18, `<|fim_middle|>` 16, `<|file_sep|>` 14, `<tool_call>` 12, `</think>` 11, `<|im_start|>` 10,
`<think>` 9, `</tool_response>` 1** (110). No cell's content set becomes empty after the filter
(0 cells), so no cell flips to NaN.

**Fix.** `concept_pr.py`:
- add `is_junk_token(tok) -> bool`: `"�" in tok` OR
  `re.fullmatch(r"</?[A-Za-z_|][^<>\s]*>", tok.strip())` (one tag-shaped token: covers `<|…|>`,
  Qwen's `<think>`/`</think>`/`<tool_call>`/`</tool_response>`, and the adapted subjects' `<eos>`,
  `<start_of_turn>`, `<unusedN>`; in the frozen 27B bank it matches exactly the 9 strings above
  and nothing else — assert that in the test).
- `is_content_token(tok)` returns False when `is_junk_token(tok)` (`concept_pr.py:214-220`), before
  the WORD/CJK/emoji checks. Single change point: Stage B calls (`judge.py:298`), Stage P token
  list (`judge.py:333`) and the recall denominator (`score.py:269, 303`) all go through it.
- Reporting: `block()` (`score.py:349-381`) adds `junk_frac` (= junk tokens / all tokens) and
  `punct_frac` keeps meaning punctuation only (compute `n_junk` from `ci.tokens` in `score.score`
  and pass it in the row meta). README "Stages/B" paragraph (README:60-62) documents the rule.
- Keep `bpe_display_to_text` (`judge.py:100-105`) as is (U+FFFD rendering unchanged; the token is
  now just excluded).

**Tests.**
- EXTEND `tests/test_concept_pr.py::test_is_content_token` (new assertions only, no edits):
  `not is_content_token("�")`, `not is_content_token(" �")`, `not
  is_content_token("<|fim_middle|>")`, `not is_content_token("<think>")`, `not
  is_content_token("</tool_response>")`; still True for `" access"`, `"访问"`, `"❤️"`, `"✅"`.
- NEW `test_junk_tokens_in_frozen_reference` (`tests/test_jlens_concept_pr.py`): scan the shipped
  references, assert the set of junk strings is exactly the 11 observed spellings (`' �'`, `'�'` +
  9 tags), 209 + 110 occurrences, and 0 cells left without a content token.
- NEW `test_junk_tokens_get_no_stage_b_call` (fake LLM): a cell whose reference holds `' �'` and
  `<|im_end|>` (use `chat-dailydialog-0046` @ L44, pos 203: reference
  `['✨','😊','❤️',' �','�','�','�','Australia','😀',' ℕ']`) → 6 Stage-B calls, not 10, and the Stage-P
  `Tokens:` line contains no U+FFFD.
- `test_content_token_filter_matches_reference_tokens` (`:610`) passes unchanged (LABELS[0] has no
  junk).

### Item 3 — rubric credits string overlap regardless of meaning
> "Fix: The rubric credits a token that appears inside a concept regardless of the concept's
> meaning: subword fragments ('osis' -> every 'X ptosis'), negations ('explicit' -> 'non-explicit
> variables', 'incentives' -> 'no incentives'), and lexical coincidences in the foil ('billions' ->
> '4.5 billion years ago'). This is by design ('the token has to be in the concept'), but it means
> precision partly measures string overlap."

**Verified cases in the cached run (Stage-P "in"):** `pt-fineweb-0011__L024/L028/L036/L040/L044/
L048/L052__p261` (≥30 "X ptosis" concepts in; reference L44 `[' eyel',' symptoms',' syndrome','
caused','osis','下垂',' wors',' symptom',' arises',' occurs']`); `chat-lmsys-0064__L044__p755`
"non-explicit variables" in (reference has `' explicit'`); `pt-fineweb-0028__L044__p515` "no
incentives" in (reference `' incentives'`); `chat-lmsys-0059__L044/L048__p302:Q000` foil "4.5
billion years ago" in (partner `chat-dailydialog-0055` tokens `[' billions',' internet',' cloud','
networks',...]`).

**Fix — three rules added to BOTH `STAGE_P_SYSTEM` (`prompts.py:83-110`) and `STAGE_B_SYSTEM`
(`prompts.py:38-53`, the recall direction has the same overlap problem), placed after the "in"
definition, with these worked examples:**
1. *Word pieces.* "A token that is only a piece of a word supports a concept only when the piece
   on its own identifies the concept's word: a word start that spells one word (' incentiv' →
   'incentives', ' eyel' → 'eyelid'). A suffix or other piece shared by many unrelated words
   ('osis', 'ness', 'ly', 'tion', 'uje') supports nothing by its letters: 'osis' is out for
   'congenital ptosis'."
2. *Negation.* "A concept that negates the token's own word means the opposite and is out:
   'non-explicit variables' is out for 'explicit', 'no incentives' is out for 'incentives',
   'unhealthy' is out for 'healthy'. Negation of a different word does not count against the token
   ('no worry about overlap' stays in for 'overlap': the negation is on 'worry')."
   (This wording deliberately keeps the existing calibrated example `"no worry about overlap" is
   in for "overlap"` at `prompts.py:94-95` and the hand label `precision_gold_L44.jsonl` row
   `s3d37` = 1, which an unscoped "negation is out" rule would contradict.)
3. *Same sense.* "Read each token in the sense the rest of the token set gives it (the set is one
   readout of one position). A concept that shares only the spelling, in a different sense or
   topic, is out: in the set ' billions, internet, cloud, networks, computers' the token
   ' billions' is out for '4.5 billion years ago'; ' bank' beside ' river, shore' is out for 'bank
   account'."

**Evidence-token field (makes the fix checkable, no extra calls).** `STAGE_P_SCHEMA`
(`prompts.py:112-129`) items gain `"token": string` — the single token from the set that grounds an
"in"/"partial" grade (empty string for "out"); the system prompt's "Return JSON" line says so.
`parse_stage_p` (`prompts.py:251-253`) validates: for in/partial the token (strip + casefold) must
equal one of the shown tokens, else `ValueError` (= reject, re-queued; existing reject machinery).
The scorer keeps `support` numerics unchanged; `rows[]` gains nothing, but the cached Stage-P
result now names the grounding token so an audit can prove 'osis' is never the cited support.
Stage B is unchanged in schema (one token per call already).

Also, per D5 (same bump), **required, not optional**: the shared
`test_no_tool_names_in_prompts` (infra §2.8) scans this family's `PROMPTS` with
`\blens(es|'s)?\b|\binterpretability tool\b|...`, and today's prompts hit it five times. No tool
NAME ("J-lens", "oracle", "NLA") appears (verified `prompts.py:23-110`), but the generic word
"lens" does. Rewrites, all built from `mc.READOUT_PHRASE` (= "readouts of a language model's
internal activations") so the phrase is the shared one:
- `STAGE_A_SYSTEM:23-24` "You are given text produced by an interpretability lens that verbalizes
  a language model's internal state." → `f"You are given text {mc.READOUT_PHRASE} (one readout at
  one position)."` → reads "You are given text readouts of a language model's internal
  activations (one readout at one position)."
- `STAGE_B_SYSTEM:38-39` "a list of concepts extracted from a lens's text" → "a list of concepts
  extracted from a text readout of the same position".
- `STAGE_P_SYSTEM:84` "(a lens's top-k readout, content tokens only)" → "(the top-k tokens of a
  readout, content tokens only)"; `:85` "extracted from another lens's text about that same
  position" → "extracted from a text readout of that same position".
- `STAGE_P_SYSTEM:95-96`, the calibrated "in" example `"objective lens" is in for "lens"` →
  `"camera shutter speed" is in for "shutter"` (same construction: the token is one word of a
  longer compound; the only change to the calibrated example list). The recalibration gate below
  covers it.
- The three Item 3 rules above contain none of the banned words (checked against the regex).
No family-local tool-name test is added; the shared one holds this family (critique 33).

**Recalibration requirement.** `STAGE_P_SYSTEM` was calibrated byte-for-byte against the hand
labels (`prompts.py:8-9`). v3 must be re-checked against `precision_gold_L44.jsonl` (120 concepts)
and `recall_gold_L44_cells.jsonl` (60 tokens) in the LLM phase: report agreement v2 vs v3; gate =
v3 agreement ≥ v2 on rows not touched by the three rules. No gold row needs relabelling under the
scoped negation rule (scan of the 120 rows: only `nla41` "without domesticated labor animals",
gold 0, and `s3d37`, gold 1 — both consistent with v3).

**Tests.**
- NEW `test_stage_p_prompt_has_overlap_rules`: `STAGE_P_SYSTEM` and `STAGE_B_SYSTEM` contain the
  three worked examples verbatim (`'osis' is out for 'congenital ptosis'`, `'no incentives' is out
  for 'incentives'`, `' billions' is out for '4.5 billion years ago'`) and still contain `"no worry
  about overlap" is in`.
- NEW `test_parse_stage_p_requires_grounding_token`: in/partial with a token not in the set →
  `ValueError`; out with `""` → ok; casing/whitespace-insensitive match accepted.
- NEW `test_prompt_version_is_v3`: `pp.PROMPT_VERSION == "jlens-pr-v3"`, `SPEC.judge.prompt_version`
  matches, README prompt block regenerated (the existing README-sync test, if any, keeps passing).
- Shared `test_no_tool_names_in_prompts` (infra) passes on `jlens_concept_pr.prompts.PROMPTS`
  (today it fails on the "lens" hits above); NEW family assertion
  `test_stage_prompts_use_readout_phrase`: `mc.READOUT_PHRASE in pp.STAGE_A_SYSTEM` and
  `"camera shutter speed" is in for "shutter"` in `pp.STAGE_P_SYSTEM`.
- **Sanctioned pre-existing assertion edit (the PV bump):** `test_stage_user_bodies_and_schemas`
  (`tests/test_jlens_concept_pr.py:84`) `assert pp.PROMPT_VERSION == "jlens-pr-v2"` →
  `"jlens-pr-v3"`. That one literal only; its other assertions (`"Walt Disney"`, `"lacks"`,
  `"return 0"`, `STAGE_P_CHUNK == 60`, the `PROMPTS` key set) stay byte-identical.
- **Sanctioned test-helper edit:** `_responder` (`tests/test_jlens_concept_pr.py:360-372`) P branch
  adds `"token"`: `"' metaphor'"`-equivalent (the shown token) for in/partial and `""` for out, and
  `test_stage_user_bodies_and_schemas` (`:71`) gets the new `token` property in the expected
  `STAGE_P_SCHEMA`. These are the only edits to pre-existing test code for this item; the numeric
  assertions (`value == 0.5`, etc.) must not change.

### Campaign alignment items (D1–D10) for this family

- **C1 (D1 summary default; Q2) — stays NATIVE_ONLY by decision.** Q2: the unit judged is one
  (label, layer, pos) cell against that cell's own J-lens top-10; a per-item digest across
  layers/positions has no single reference to score against. infra §2.5 keeps
  `digest.NATIVE_ONLY == {"jlens_concept_pr"}` (the one exception) with its reason string, and the
  runner stamp (`runner.py:103, 124-128`: `config.aggregate="native"` +
  `extras.summary_mode_note`). This family changes neither. Website: the family page and the
  "Decisions taken" list state "the one native-only family: precision is per cell against that
  cell's J-lens top-10, so a summary has no reference" (Q2 text). Tests: infra's
  `test_native_only_is_exactly` and `test_every_registered_family_is_summary_or_native_only`;
  NEW `test_jlens_pr_stays_native_under_summary` (`aggregate=summary` → `config.aggregate ==
  "native"`, `extras.summary_mode_note` present, no digest call issued).
- **C2 (D2 `reads=lite|full`).** One read position per label by construction, so lite = full =
  `eval_positions[0]`.
  - Plan row (`readplan.py:622-630`) gains `lite_positions={"kind": "final_token"}` and
    `lite_layers=None` (infra's default row; the loaded cells hold only the eval position because
    `reads.load` is called with `positions={id: [pos]}`, so `final_token` keeps exactly it).
    The full rule stays `{"kind": "positions", "positions": p["eval_positions"]}`.
  - Registry: `EvalSpec(min_full_positions=1, full_contiguous=False)` (infra §2.6.5 names this
    family for both).
  - Judge: `run` calls `reads.load(args, FAMILY, positions=positions)` (infra §2.0); `select` /
    `check_full` run inside it. No family filtering of lite cells. The r2 full-read guards are
    the shared ones and are not re-implemented: with a sidecar, `plan_sha` ≠
    `reads.plan_sha(FAMILY)` exits 2 (adding `lite_positions` does not move the hash: `lite_*` is
    excluded), a GRID layer missing from the file under `layers=None` exits 2, and a `reads: lite`
    sidecar under `reads=full` exits 2; sidecar-less files are report-only.
  - Stamp: `config.prompt_version = reads.stamp(PROMPT_VERSION, reads.mode(args))` (full:
    `jlens-pr-v3`, lite: `jlens-pr-v3+reads-lite`); `config.reads` comes from `base_config`.
  - Tests: infra's `test_every_plan_row_has_lite_positions`,
    `test_every_lite_rule_is_cell_resolvable`, `test_lite_is_subset_of_full`,
    `test_no_family_calls_load_readouts_directly` (this family imports `load_readouts` today at
    `judge.py:43`; after: only `expected_cells` / `missing_cells` / `Cell` from `readouts`), and
    `test_min_full_positions_per_family`; NEW `tests/test_jlens_concept_pr.py::
    test_lite_judges_same_cells_as_full` (same fixture with `write_sidecar(..., reads="full",
    sampling="prose1")`, `reads=lite` and `reads=full` → identical cell keys and value; PVs differ
    only by `+reads-lite`). Because lite ≡ full for this family, G14's `reads=lite` re-judge in
    its own out dir re-spends one arm's calls for an identical number; the site prints it as
    "lite = full by construction" beside the full value (see Risks: recommend gpu skip it).
- **C3 (D3 arbitrary layers).** Uses infra §2.1 as is: `readplan.plan(family, layers=...)`
  (`layers="all"` → 64 layers for production), CLI `layers=all|each|<csv>` (judge maps `all` to
  `None` = every layer in the file), `reads.load`'s layer-presence check (a requested layer absent
  from the file exits 2), `mcjudge.is_subset` without the `args.layers` clause, and
  `config.layers_judged` from `base_config`. The ONE family-specific rule is reference coverage
  (the J-lens reference files exist only for GRID + L42, and the reference is this family's bank
  data, not a shared concern):
  (a) with `layers=None` (incl. `layers=all`), the judged layers are `rep.layers ∩
  reference_layers`; layers dropped for lack of a reference are listed in
  `extras.layers_without_reference` with a printed warning, instead of today's exit 2
  (`judge.py:212-216`). The `LoadReport` handed to `base_config` carries the judged layers
  (`dataclasses.replace(rep, layers=judged)`), so the shared `layers_judged` stamp is the judged
  set — no family-local `judged_layers` key (deleted from `judge.py:434`). Exit 2 stays when the
  intersection is empty. A 64-layer file therefore runs without pre-filtering.
  (b) An explicit `layers=` list naming a layer without a reference exits 2 before any call (as
  today); a layer missing from the file exits 2 through `reads.load`.
  (c) New opt `headline_layer=N` (must be judged, else exit 2); otherwise the existing rule
  (single layer, else L44, else None).
  (d) `layers=each` (Camila's "each of the individual 11 layers") writes `out/<family>/all/` and
  `out/<family>/L<k>/` like every family (infra §2.1.6: equivalent to the `run layers=<k>` loop
  gpu R4 uses). Each (label, layer) cell is judged on its own with the same cache keys, so
  `L<k>/results.json` is the same quantity as the all-layer run's `extras.by_layer[k]`. The
  family's call cache is `args.out / "cells.jsonl"`, i.e. per out dir, so the 11 single-layer
  configs together cost ≈ one more all-layer pass (no shared-cache mechanism is added here).
  Stage P is T=0, so the L<k> value differs from `by_layer[k]` only by judge nondeterminism in
  Stages A/B; the site prints both and their difference per layer as a judge-stability check.
  Tests: existing `test_unknown_layer_is_fatal_before_any_call` (`:529`) passes unchanged (its
  file has only L99 → empty intersection → exit 2; `layers=[44, 99]` → exit 2); existing
  `test_headline_layer_without_l44` (`:504`) passes unchanged; NEW
  `test_file_layers_without_reference_are_dropped` (file L44 + L99, no `layers=` → judged `[44]`,
  `config.layers_judged == [44]`, `extras.layers_without_reference == [99]`); NEW
  `test_headline_layer_opt`; NEW `test_layers_each_equals_by_layer` (deterministic fake LLM,
  L44+L48 fixture: `L44/results.json` value == all-run `by_layer["44"]["precision"]` and the
  same for recall@10 and foil precision; the sub-run's call keys == the all-run's L44 keys);
  infra's `test_layers_variant_is_complete` (`layers=44` on a full file → `complete=True`). For
  infra's `test_layers_arbitrary` (synthetic layers `[3, 17, 44]`, asserts `layers_judged` = the
  input layers), this family's case needs reference files at those layers: this spec ships a
  fixture helper `tests/fixtures/jlens_pr_bank.py::make_adapted_bank(tmp, layers)` that writes a
  `WSB_BANK_ROOT/jlens_concept_pr/` (manifest of 2 labels + `gen-jlens-pr-jlens/<label>/L0NN.jsonl`
  at the requested layers), which infra's parametrized test uses for this family.
- **C4 (D4 cannot-tell).** Not applicable: no multiple choice; the in/partial/out grade is per
  concept. infra §2.4.5 lists `jlens_pr` among the non-MC families; it is not in
  `lucky_guessing.BUILDERS`, so `test_every_mc_judge_ends_with_cannot` does not reach it.
- **C5 (D5 neutral prompts / task context).** Prompts are rewritten to `mc.READOUT_PHRASE` and
  pass the shared `test_no_tool_names_in_prompts` (Item 3). Task context is NOT used: there is no
  summarizer, and Stage A/B/P must not see the rollout (the judge would grade against the context
  instead of the token set). `EvalSpec.task_note` is left unset; `test_every_summary_family_has_
  task_note_without_gold` covers summary families only.
- **C6 (D6 token lenses, J-lens summarizer removed).** Not applicable: token readouts are refused
  (`judge.py:209-211`, kept; with the sidecar, a file whose declared `sampling` is `tokens10` is
  refused the same way); the J-lens is the reference, not an arm. This family never called
  `summarizer.summarize` (infra §2.3 deletes it); nothing to remove here.
- **C7 (D7 sampling; Q1).** The cap is NOT implemented here. `reads.load` calls
  `readouts.normalize(cells, sampling)` from the sidecar (infra §2.9): `*-x4` arms → `bullet4`
  (4 samples), every other prose arm incl. the campaign's `s3d-rl600` and NLA → `prose1` (1
  sample: one s3d generation with its ~4 concept bullets is one readout). Cell text for Stage A
  becomes `readouts.bulleted([s for s in c.samples if s.strip()])` (infra §2.9.6, the shared
  one-string join) instead of the family's `concat_samples` (`"\n---\n"`, `prompts.py:162-164`),
  which is deleted. `config.sampling` / `sampling_source` and the normalize diag counts come from
  `base_config` / `rep`; no family `samples_per_cell` key. Cached in-house x4 files have no
  sidecar: they are re-judged with the CLI override `sampling=bullet4` (first 4 of 8 samples,
  `sampling_source="override"`), no GPU; being sidecar-less they are report-only
  (`config.reads_checked == "no_sidecar"`) and the site labels them "cached v1 readouts, judge
  test only" (G14). An s3d `prose1` sample that is already a bullet list (`"- a\n- b"`) is
  kept verbatim by `bulleted` (`"- " + s.removeprefix("- ").strip()`, infra §2.9.6), so Stage A
  sees the real newline bullet boundaries. The r3 digest rules (`digest.BULLET_MARK`,
  `statement_lines`, `number_flood`) do not apply: there is no digest line, and the unit graded
  is one extracted concept against one token set, not a relational pick (Q4's
  no-piecing-together rule is met because Stage P grades each concept alone against one
  activation's top-10). Tests: infra's `tests/test_readouts.py` normalize tests;
  NEW `test_cell_text_is_shared_bulleted_join` (2-sample cell under `sampling=bullet4` → Stage-A
  user body `"Text:\n- a\n- b"`; empties dropped; under default `prose1` → `"Text:\n- a"`).
  **Sanctioned pre-existing-test removal:** `test_concat_samples_drops_empties` (`:67`) is deleted
  with the function it tests (replaced by the NEW test above). No other test depends on the
  join (the fake `_responder` returns fixed concepts).
- **C8 (D8 prompt-only).** Stays excluded: `prompt_only.EXCLUDED == {"jlens_concept_pr"}`
  (infra §2.11.9; "not a bar a lens clears"); no `po-opus-v1` readouts are built for it. See
  Answers §4.2.
- **C9 (D9 versioned banks).** No bank change. `EvalSpec.bank` stays
  `Path("evals/jlens_concept_pr/manifest.json")` (infra's `test_bank_file_naming_rule` allows
  `manifest.json`). `bank_dir()` (`judge.py:76-87`) becomes `registry.bank_path(FAMILY).parent`
  plus today's "has no bank" existence check, so `WSB_BANK_FILE_<F>` / `WSB_BANK_ROOT`
  precedence is the shared one; no family-local env parsing. The adapted bank's `items.json`
  companion read in `readplan.py:620` is inside infra's `test_no_hardcoded_items_json`
  exemption (readplan adapted-bank manifests). Prompt bump only (`jlens-pr-v3`).
  `__init__.py` `calls_per_arm` "≈ 35k" → "≈ 71k (x4 arm, 11 layers, pfoil on)".
- **C10 (D10 / ATI).** Not in ATI; `anti_text_inversion.json:29` unchanged; infra's
  `test_bank_sha_unchanged_for_untouched_families` does not reach it.
- **12-config run.** `jlens_concept_pr` is in `FAMILIES_BP` (registered, not removed), so the
  campaign judges `s3d-rl600` (sidecar `sampling: prose1`) natively at all 11 layers + the 11
  single-layer configs (C3d); smoke `limit=3` first (spend decision), then measure calls per cell
  and go.
- **C11 (critique r1 item 7: "Audit to make sure it is neither too strict nor too lenient").**
  This family uses the shared G12 audit (`scripts/audit_verdicts.py`, gpu R4b), no second
  protocol. Its verdicts are not MC answers, so the family defines what one audited verdict is
  and exposes it; the sampler and the table are gpu's.
  - Verdict unit: one Stage-P grade `{cell key, concept, token set shown, grade, grounding token}`
    (the Item 3 `token` field), one Stage-B grade `{reference token, concept list shown, grade}`,
    or one foil Stage-P (Q) grade with the partner's token set. Strata (seeded per G12): Stage P
    in/partial vs out × arm (s3d-rl600, mlnla-rl2-2000), plus ≥ 5 Stage-B grades and ≥ 5 foil
    Q "in"/"partial" grades (the foil is the floor, so foil leniency inflates it); ≥ 30 total.
    There is no token stratum (J-lens readouts are the reference here, C12).
  - Strata in G12's r3 form: each verdict row carries `kind ∈ {"P", "B", "Q"}` (the stage) and
    `pass = grade != "out"`, so the shared sampler stratifies pass/fail × arm as for every
    family and `--strata jlens_concept_pr=kind` gives ≥ 10 per kind (sample = `max(30, 10 × 3)`
    = 30). The values are read from the rows (G12 rule), not hard-coded here.
  - Exposure: family-local `score.verdict_rows(out_dir) -> list[dict]` reads `cells.jsonl` and
    returns those dicts (`kind`, `pass`, `key`, `label`, `layer`, `pos`, `concept`, `tokens`,
    `grade`, `token`, `is_foil`). `audit_verdicts.py sample` calls it for this family (the one
    non-MC adapter; dependency on gpu, see Risks). The auditor's "pass rule" for this family is
    the in/partial/out definitions plus the three Item 3 rules, quoted from `STAGE_P_SYSTEM`.
  - Gate (G12's): `n_too_lenient + n_too_strict ≥ 3` → flagged on the site; the fix goes
    through gpu's R4c loop **before R6 / R8 and the site build** (fix PR with a new family PV
    `jlens-pr-v4`, then R4 for this family only: s3d-rl600 all-layer + 11 single-layer configs,
    `mlnla-rl2-2000` full + lite, the x4 judge-test re-judges; then R4b with `--seed-suffix
    r<k>`; ≤ 2 rounds; leftovers listed under "New errors found"). No R2 / R2b: a prompt fix does
    not move `plan_sha`, and no R6 / R8 step exists for this family (`prompt_only.EXCLUDED`, not
    in ATI). Never silently re-tuned.
  - Test: NEW `tests/test_jlens_concept_pr.py::test_verdict_rows_carry_audit_fields` (fake LLM
    run on the LABELS fixture with pfoil on → rows of kinds P, B and Q, `pass` equals
    `grade != "out"`, every P/Q in/partial row has a non-empty `token` that is in its `tokens`,
    foil rows `is_foil=True` and `kind == "Q"`).
- **C12 (G14 required arms).** `mlnla-rl2-2000` (`prose1`, k=1, sidecar declared) is judged here
  natively exactly like `s3d-rl600` (all-layer config, full + lite) and reported beside it. The
  `jlens` arm (`tokens10`) is NOT an arm of this family: the J-lens top-10 is the reference, and
  a tokens file is refused with exit 2 (`judge.py:209-211`, existing
  `test_tokens_readouts_are_refused` unchanged). So no `jlens_concept_pr.jsonl` may be written
  under the `jlens` readouts root; the runner then records the family as `skipped` ("no readouts
  at …", `runner.py:215-218`) instead of failing the arm's `run all=True` with exit 2. This
  needs G14's J-lens production to exclude this family (gpu-owned; Risks). Test: NEW
  `test_jlens_arm_root_without_family_file_is_skipped` (runner over a tmp readouts root with no
  `jlens_concept_pr.jsonl` → outcome `skipped`, exit 0 for that family).
- **C13 (macro, infra §2.17 r3).** `metric="precision"` is unchanged, so `results.macro`
  excludes this family with reason `"metric"` (`results.MACRO_METRICS = {"pass_rate",
  "pair_rate"}`); `EvalSpec.not_in_macro` stays `""` (never `None`). The site's macro table
  prints the reason as "precision, not a pass rate" (today's exclusion, now explicit). Test: NEW
  `test_jlens_pr_out_of_macro_by_metric` (real `results.macro` over a fixture result with
  `metric="precision"` → excluded, reason `"metric"`; `SPEC.not_in_macro == ""`).

---

## 3. Data needs

- **Bank edits:** none. `manifest.json`, `gen-jlens-pr-jlens/**`, gold files untouched; the
  junk filter is code. No new bank version file.
- **New items:** none. No Qwen gating on GPU needed.
- **Readouts to regenerate:** none for Items 1–4. Re-judging (LLM phase, ≈71k calls per 11-layer
  arm with pfoil on, see the cost note below) uses existing arm readouts:
  every O-lens arm in `.../wsb_latest/outputs/judged/*-x4/jlens_concept_pr` has its readouts file
  named in its `results.json` config (re-judged with `sampling=bullet4`, C7). Stage A is re-run
  (≈3.3k calls/arm): the D5 rewording is required by the shared tool-name test and the cell text
  changes with the shared `bulleted` join and the 4-sample cap, so cached A keys do not carry over.
  B and P re-run under v3. The campaign arm `s3d-rl600` (prose1, 1 sample per cell) is produced by
  the gpu workstream for `FAMILIES_BP` and judged the same way; its per-arm call count is measured
  in the `limit=3` smoke (fewer concepts per cell than x4, so ≤ the x4 figure). The required
  G14 arm `mlnla-rl2-2000` (prose1) is judged the same way (all-layer, full + lite). Call budget
  for the campaign arms: per arm ≤ 71k (all-layer) + ≈ 71k (the 11 single-layer configs,
  s3d only, C3d) + ≈ 71k (the lite re-judge, unless gpu skips it for this family, C2); all
  measured on the smoke before going.
  Cost note (cached run key counts): A 3,404, B 30,588, F 30,617, P 3,160, Q 3,159 → ≈71k calls per
  11-layer arm with pfoil on (README's "≈35k" at README:94 is wrong today — it omits the F pass;
  fix the README number).
- **Optional (only if a method reads layers outside 20..60/4 + 42):** new reference files
  `gen-jlens-pr-jlens/<label>/L0NN.jsonl` need a Modal GPU recapture (the `acts-jlens-pr` volume
  holds 20:61:4 only; recapture needs the source repo's `items.json` input ids, which are not
  shipped). Not required by Camila's section; flag only.
- **Recalibration (LLM phase):** run Stage P v2 and v3 on the 120 `precision_gold_L44` concepts and
  Stage B on the 60 `recall_gold_L44_cells` tokens; publish agreement.

---

## 4. Answers

**4.1 Section questions.** Camila's section asks no question; all four sentences are fixes.

**4.2 "How are prompt only baselines judged? Do they/should they get the same judge prompt as the
readouts" (for this family).** Today this family has no prompt-only baseline at all: it is in
`prompt_only.EXCLUDED` ("precision against the J-lens top-10, not a bar a lens clears",
`baselines/prompt_only.py:25`) and skipped as NATIVE_ONLY (`prompt_only.py:76, 110`). Its floor is
the derangement foil (another item's top-10 against the same concepts), which Item 1 makes measured
by default. A D8-style Opus reader that sees only the context up to the read token could be run
through the SAME three stages (it is just another prose arm), and would measure how much J-lens
content is predictable from the text alone. It cannot be built from this repo: the rollout text was
stripped from the manifest on 2026-09-17 (`evals/jlens_concept_pr/README.md:20-24`), so it needs the
source repo's `items.json`. Decision (infra §2.11.9, `prompt_only.EXCLUDED ==
{"jlens_concept_pr"}`): excluded for this release; the site states the foil as this family's
floor and lists the Opus prompt-only reader as an optional later floor (blocker: rollout text not
shipped). If it is ever built, it goes through `po-opus-v1` and the same three stages, no special
judge.

**4.3 "Run this for the oracle lens with ALL 11 layers, and then … each of the individual 11
layers."** For this family the two are the same run: each (label, layer) cell is judged on its own
(no summarizer), so an 11-layer run's `extras.by_layer[L]` is exactly the single-layer-L result.
The campaign still runs the 11 single-layer configs (gpu R4 loop ≡ `layers=each`, C3d) so the
`out/` layout matches every family. They are the same quantity as `by_layer[L]`
(`test_layers_each_equals_by_layer`) but live in separate out dirs, so they re-spend calls
(≈ one more all-layer pass); the site shows `L<k>` beside `by_layer[L]` as a judge-stability check.
"The oracle lens" = `s3d-rl600` (Q1), `sampling: prose1`.

**4.4 Does the junk fix change published numbers?** Measured on cached rl-onchat (recall only,
from cached Stage-B grades, no calls): recall@10 at L44 0.5965 → 0.5983; per layer +0.000 to
+0.009 (L60 0.544 → 0.553); `chat-dailydialog-0046@L44` 0.325 → 0.542 (10 → 6 content tokens).
Precision is unchanged by the filter alone (junk tokens are always "out").

**4.5 Is the foil currently a clean floor?** Partly. Measured pfoil precision is 0.013–0.032 per
layer, but the audit found generic partner sets can lift one foil cell to 0.25
(`pt-fineweb-0038@L44`, partner `pt-fineweb-0008`), and lexical coincidences (`billions`) leak in.
Rule 3 of Item 3 targets the latter.

---

## 5. Evidence plan (what the website shows)

| Item | Before (current, measured or cached) | After (proof) |
|---|---|---|
| 1 | Re-score cached rl-onchat with pfoil rows removed: `by_layer` foil precision L48–L60 = **0.0**, `chance_label` "measured" | Same re-score under v3 code: all layers **null** + "not measured" label; default run: `config.stage_p_foil=true`, foil precision a number beside every precision |
| 2/4 | `is_content_token('�')=True`, `'<|fim_middle|>'=True`; 209 U+FFFD + 110 tag tokens in the B/P token lists; `chat-dailydialog-0046@L44` recall 0.325 over 10 tokens | `False`/`False`; scan shows 0 junk tokens in any Stage-B key or Stage-P `Tokens:` line of the new run; that cell 0.542 over 6 tokens; L44 recall 0.5965 → 0.5983 on the re-score (then the v3 re-judge value) |
| 3 fragments | `pt-fineweb-0011@L044 p261` Stage-P: 'acquired / aponeurotic / traumatic / age-related / neurogenic ptosis' all **in** (only overlap source 'osis', plus '下垂') | Re-judge under v3: no grade cites `'osis'` as its token; any surviving in/partial cites `'下垂'` or `' eyel'` (shown verbatim) |
| 3 negation | `chat-lmsys-0064@L044 p755` "non-explicit variables" **in**; `pt-fineweb-0028@L044 p515` "no incentives" **in** | both **out** |
| 3 coincidence | `chat-lmsys-0059@L044 p302:Q000` foil "4.5 billion years ago" **in** | **out** on the foil; control: the REAL cell `chat-lmsys-0059@L044:P000` (tokens millennia, centuries, billions…) stays **in** (no over-correction) |
| 3 calibration | v2 agreement on 120 hand labels (to be measured) | v3 agreement ≥ v2 on untouched rows; s3d37 "no worry about overlap" still in |
| prompts | `test_no_tool_names_in_prompts` on this family's `PROMPTS`: 5 hits ("interpretability lens", "a lens's text", "a lens's top-k readout", "another lens's text", plus the `"objective lens"` example) | 0 hits; the rewritten sentences shown verbatim |
| layers | file with L44 + L99: exit 2 | judged `[44]`, `extras.layers_without_reference == [99]`; the 11 single-layer configs: `L<k>` value beside the all-run `by_layer[k]` with their per-layer difference (judge stability), calls per config from the call log |
| audit (C11) | no verdict audit for this family | G12 site-table row: n ≥ 30 stratified verdicts (P in/out × s3d/ML-NLA, B, foil Q), `n_too_lenient` / `n_too_strict` / `n_ambiguous`, every non-`ok` case verbatim with its grounding token |
| arms (C12) | only cached `*-x4` arms judged | `s3d-rl600` and `mlnla-rl2-2000` rows (both `sampling_source = declared`, `reads_checked = sidecar`); `jlens` arm row "skipped: J-lens is the reference" |
| sampling | x4 arm: 8 samples joined by `---` per cell | `config.sampling = bullet4` (override, first 4) for x4 re-judges; `s3d-rl600`: `sampling = prose1`, `sampling_source = declared` |
| native-only | — | `config.aggregate == "native"` under the summary default, `summary_mode_note` and the Q2 reason on the site |
| headline | rl-onchat P@44 0.315 (Opus override, v2, 8 samples) | v3 P@44, R@10, foil P, per layer, for `s3d-rl600` (prose1, the campaign arm), `mlnla-rl2-2000` (prose1) and the re-judged x4 arms (bullet4, "cached v1 readouts, judge test only"), samples-per-cell stated |
| macro (C13) | out of macro, reason implicit | macro table row: excluded, reason "precision, not a pass rate" |

### 5.1 Site coverage map (`site/manifest.json` rows, gpu G11)

`sentence_id` = `<section>:<line in notes/feedback.md>`. Status rule is G11's (`done` needs the
named tests green at the footer SHA; a row whose artefact is missing is `pending`).

| sentence_id | change_id | tests | evidence row (§5) | target status |
|---|---|---|---|---|
| `J-lens precision recall:204` (foil 0.0 → not measured) | Item 1 (foil on by default + null when unmeasured) | `test_foil_precision_is_null_without_pfoil`, `test_pfoil_runs_by_default`, `test_stage_p_foil_opt_out`, `test_pfoil_opt_measures_foil_precision` | 1 | done |
| `J-lens precision recall:205` (fragments / special tokens in recall denominator) | Items 2/4 (`is_junk_token`) | `test_is_content_token` (extended), `test_junk_tokens_in_frozen_reference`, `test_junk_tokens_get_no_stage_b_call` | 2/4 | done |
| `J-lens precision recall:206` (rubric credits string overlap) | Item 3 (three rules + grounding `token` + recalibration) | `test_stage_p_prompt_has_overlap_rules`, `test_parse_stage_p_requires_grounding_token`, `test_prompt_version_is_v3` | 3 fragments, 3 negation, 3 coincidence, 3 calibration, audit (C11) | done (rules) / measured (re-judge, calibration, audit) |
| `J-lens precision recall:207` (U+FFFD / `<|…|>` count as content) | Items 2/4 | as `:205` | 2/4 | done |
| `ALL/GENERAL:13` (no J-lens summarizer) | C6 (nothing to remove; native) | infra's summarizer-deletion tests; `test_jlens_pr_stays_native_under_summary` | native-only | done |
| `ALL/GENERAL:15`, `:18` (summary default) | C1 (Q2: the one NATIVE_ONLY family) | `test_native_only_is_exactly`, `test_jlens_pr_stays_native_under_summary` | native-only; Decisions taken (Q2) | done |
| `ALL/GENERAL:11` (arbitrary layers) | C3 | `test_file_layers_without_reference_are_dropped`, `test_headline_layer_opt`, infra `test_layers_arbitrary` (fixture `make_adapted_bank`) | layers | done |
| `ALL/GENERAL:19` (audit not too strict / lenient) | C11 + R4c | `test_verdict_rows_carry_audit_fields` | audit (C11) | measured |
| `ALL/GENERAL:20` (all 11 layers + each layer) | C3d / §4.3 | `test_layers_each_equals_by_layer` | layers, headline | measured |
| `ALL/GENERAL:21` (prompt-only judging) | C8 / §4.2 (excluded; foil = floor) | infra `prompt_only.EXCLUDED` test | Answers §4.2 | done |
| `ALL/GENERAL:46` (no tool names in prompts) | Item 3 rewording / C5 | `test_no_tool_names_in_prompts`, `test_stage_prompts_use_readout_phrase` | prompts | done |
| `basic readout mt:80` (samples per activation) | C7 | `test_cell_text_is_shared_bulleted_join`, infra normalize tests | sampling | done |

Answers section: §4.2 and §4.3 text. Decisions taken: Q2 (native-only, reason as C1), "lite =
full by construction" (C2), "foil is this family's floor; no prompt-only floor" (C8), "out of
macro: precision is not a pass rate" (C13).

---

## 6. Risks / conflicts

- **Shared files I would touch:** `README.md` (family blurb `:278-282`, prompt-version table
  `:397`), `src/wsbench/readplan.py` (`:622-630`: add `lite_positions={"kind": "final_token"}`,
  `lite_layers=None` to this family's row only; infra owns the fields), `tests/test_concept_pr.py`
  (new assertions in `test_is_content_token`), new `tests/fixtures/jlens_pr_bank.py` (C3 fixture
  for infra's `test_layers_arbitrary`). Read-only dependencies that must NOT change for this
  family: `digest.NATIVE_ONLY` (infra keeps it `{"jlens_concept_pr"}`),
  `src/wsbench/runner.py:103, 124-128`, `prompt_only.EXCLUDED`,
  `src/wsbench/baselines/text_inversion.py:87`, `evals/baselines/anti_text_inversion.json:29`.
  **Depends on the infra PR (lands first):** `reads.load` / `reads.stamp` / `reads.mode`,
  `ReadSpec.lite_positions`, `EvalSpec.min_full_positions` / `full_contiguous`,
  `readouts.normalize` / `readouts.bulleted` + sidecar `sampling`, `mcjudge.base_config` stamps and
  `is_subset`, CLI `layers=all|each`, `mc.READOUT_PHRASE`, `registry.bank_path` honouring
  `EvalSpec.bank`, `test_no_tool_names_in_prompts`.
- **Manifest-coverage check kept (not a re-implementation of `check_full`).** The family's
  `expected_cells` / `missing_cells` check (`judge.py:217-231`) stays: it asserts every
  (label, layer) cell the manifest expects is present, whereas `reads.check_full` counts
  positions inside a loaded (item, layer). Existing `test_missing_cells_stop_the_run_unless_allowed`
  (`:522`) passes unchanged. If infra's `check_full` is extended to cover wholly absent
  (item, layer) cells over `reads.specs`, this check is deleted in favour of it.
- Family-local files: `src/wsbench/evals/jlens_concept_pr/{concept_pr,prompts,judge,score}.py`,
  `evals/jlens_concept_pr/README.md`, `tests/test_jlens_concept_pr.py`.
- **D1 is impossible for this family** (no reference for a digest); keep NATIVE_ONLY.
- **Over-correction risk (Item 3 rule 3):** "same sense" could push real hits out; the
  `chat-lmsys-0059` real-cell control and the gold-set agreement are the guards.
- **Pre-existing test edits** are limited to: adding `extra={"stage_p_foil": "0"}` to two `jargs`
  calls, the `_responder` P-branch `token` field, the `STAGE_P_SCHEMA` expectation, the one
  `PROMPT_VERSION == "jlens-pr-v2"` → `"jlens-pr-v3"` literal (`:84`), and deleting
  `test_concat_samples_drops_empties` (`:67`) with `concat_samples` (C7). Any other change to an
  existing assertion in `tests/test_jlens_concept_pr.py` or `tests/test_concept_pr.py` is a red
  flag. Existing fake-LLM call counts (`["B"] * 60` etc.) stay valid: the LABELS references at
  L44/L48 hold no junk token (checked: 0 U+FFFD, 0 tag tokens).
- Not requested but noted from the audit: "partial" is stretched to vague affective/category links
  on weak token sets (`chat-lmsys-0013@L44`, `pt-pile-0033@L20`); Camila did not ask for this, so it
  is out of scope unless she adds it.
- Reproducibility (rollout text not shipped) remains; it blocks a prompt-only floor (§4.2).
- **gpu dependencies (not editable from this spec):** (a) G14 must exclude `jlens_concept_pr`
  from `jlens` production (as ML-NLA excludes agentic), else the `jlens` arm's `run all=True`
  fails this family with exit 2 (C12); (b) G12's `audit_verdicts.py sample` must call
  `jlens_concept_pr.score.verdict_rows` for this family, whose verdicts are per-concept grades,
  not MC answers (C11); (c) recommended: skip this family in the G14 `reads=lite` re-judge
  (lite ≡ full here, C2), saving ≈ 71k calls per arm; (d) G9 `audit_run.py` must exempt this
  family (as it already does for `aggregate`) from the `prompt_version == digest.prompt_version(…)`
  check (its PV is `reads.stamp(jlens-pr-v3, mode)`, no digest stamp) and from the r3
  instrument-agreement check (no `prompt_only_summary.json` entry, not ATI-gated), else every
  campaign run of it fails the audit; (e) gpu's R4b command line must add
  `--strata jlens_concept_pr=kind` (C11).
- Round 3: no new pre-existing-test edits (C11's row fields and C13 add tests only).
- New pre-existing-test edits in round 2: none (C11 and C12 add tests only).

---

## 7. Implementation record (PR, 2026-10-30)

Built on origin/main 34005ac (plan 0032 infra merged). Codex was unavailable; implemented directly.

**Deviations from the spec above (each deliberate):**
- C2: the plan row keeps infra's `lite_positions = {"kind": "same"}` (already on main) instead of
  `final_token`: one read position per label, so both select exactly `eval_positions[0]`; no
  shared-file edit needed.
- C3: infra's `test_layers_arbitrary` is NOT edited (it still expects exit 2 for this family on
  `[3, 17, 44]`, which v3 keeps: an explicit `layers=` without a reference exits 2). The
  `make_adapted_bank` helper lives in `tests/test_jlens_concept_pr.py` and drives a family test
  `test_arbitrary_layers_with_adapted_reference` (`layers_judged == [3, 17, 44]`).
- C9: `bank_dir()` honours `WSB_BANK_FILE_JLENS_CONCEPT_PR` through `registry.bank_path` (a
  `manifest.json`, its directory is the bank); `WSB_BANK_ROOT` keeps the directory layout
  `<root>/jlens_concept_pr/manifest.json` (`registry.bank_path` would look for
  `<root>/jlens_concept_pr.json`, which the adapt flow never writes).
- Item 3: Stage B's user body gains a `Token set:` line (the token's own content set) so the
  same-sense rule (rule 3) can be applied there; `STAGE_B_USER` is that template (in `PROMPTS`,
  README, tool-name scan) and the v2 body survives only as the private `_STAGE_B_USER_NO_SET`
  fallback of `render_stage_b` without a set (never sent), so the PROMPTS key set and the
  existing render assertion are unchanged.
- Item 2/4 data claim corrected: 5 reference cells (`chat-lmsys-0013` L52/L60,
  `chat-lmsys-0046` L52/L56/L60) had only tag tokens as "content", so after the filter they hold
  no content token and become no-information cells (NaN, dropped from the means, the existing
  all-punctuation rule); the spec's "0 cells" was wrong. Pinned in
  `test_junk_tokens_in_frozen_reference`.
- Item 1: `test_stage_sequencing_models_and_numbers` asserted `chance_label == CHANCE_LABEL` with
  the foil off — the exact bug reported — so that one literal becomes `CHANCE_LABEL_UNMEASURED`
  (the spec promised byte-identical assertions there; the two promises conflict, Camila's
  sentence wins).

**Measured now (offline re-score of the cached v2 rl-onchat-x4 run; Opus 5.5 calibration):**
- Foil off: by_layer foil precision L48–L60 `0.0` + "measured" label (old code) → `null` at every
  layer + "not measured" (v3 code); foil on: 0.013–0.032 per layer.
- Recall@10 at L44 0.5965 → 0.5983 (junk filter only; precision unchanged 0.3154);
  `chat-dailydialog-0046@L44` 0.325 over 10 tokens → 0.542 over 6.
- Stage-P v2 → v3 on the 120 precision hand labels: exact agreement 92 → 95 (MAE 0.121 →
  0.108; 7 rows changed, 5 toward gold, 2 away: nla27, s3d21); Stage B on the 60 recall hand
  labels: 46/58 → 50/59. s3d37 "no worry about overlap" stays in.
- Cited cases re-judged under v3: five 'X ptosis' concepts in → out (the surviving
  "ptosis / drooping eyelid" cites '下垂'), "non-explicit variables" in → out, "no incentives"
  in → out, foil "4.5 billion years ago" in → out; the real-cell control
  `chat-lmsys-0059@L44` stays in (cites ' billion' / ' billions').
- Possible over-correction to watch in the run-phase audit: "acquired / traumatic / … ptosis"
  went out although '下垂' (drooping) is in the set and would ground them by translation.

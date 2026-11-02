# 0028: instruction narration counts as a hit (directed_modulation, MCDM)

Camila, 2026-10-29: "we should count it, and also count it in the regular directed modulation
version too". "It" = a readout that names the dictated concept only while narrating the
instruction ("I was asked to think about a blacksmith…", "I must not reveal the word ember").

Evidence (MCDM rerun of 2026-10-29, s3d-rl600, Opus 5.5, plan 0025 audit): the judge applies the
content-vs-narration label inconsistently (8 of 78 cross-mode pairs flip; 23% of native
content_bound credits carry a narration marker; 17 of 20 too-lenient verdicts are this label),
and under it the default summary score (0.204) sits below the lucky floors (0.235 / 0.245).
Recomputed from the cached verdicts with narration counted: native 0.418 -> 0.490, summary
0.204 -> 0.357.

## Rule

- **directed_modulation.** The headline per row becomes `present`: the gold is picked AND
  `basis in {content_bound, instruction_narration}`. `incidental` and `absent` still never count.
  Retained: the judge prompt, schema, options, cannot-tell escape, the evidence/quote verification
  (a voided row never counts), the per-item ANY-row rule and the tri-state undecided rule are
  unchanged. `content_bound` (the old headline) is kept as an extras channel under its own name,
  `instruction_narration` stays as a channel, and a new `present` channel is added. **The
  white_bear think-vs-don't-think contrast stays on `content_bound`** (it measures leakage past a
  suppression, where narrating the prohibition is what it must exclude), and `pass_at_1` follows
  the headline (`present`).
- **multi_concept_directed_modulation.** A dictated pick credits when its quote verifies AND its
  basis is `content_bound` or `instruction_narration` (`incidental` / invalid never credit).
  Retained unchanged: the all-concepts item rule, the binding-direction rule (a call naming the
  partner credits none of the item's concepts; the partner named as content anywhere fails the
  item — "as content" now meaning content_bound OR instruction_narration, so a narrated partner
  counts against the item exactly as a narrated own concept counts for it), the >3-candidate
  over_selected rule, the TOKENS_NOTE, controls and capacity. Extras gain
  `content_only_pass_rate` (the plan-0025 headline, all concepts content_bound) beside the
  existing `narration_rate`.

## Versions: the judge cache vs the instrument stamp

The judge prompts do not change, so the cache must keep hitting; the scoring does change, so
floors measured under the old rule must stop being drawn. Each family splits its version:
`JUDGE_PROMPT_VERSION` (unchanged: `dm-2026-09-16`, `mcdm-2026-10-29`) keys every `run_calls`
fingerprint in native and summary mode (summary: `digest.prompt_version(JUDGE_PROMPT_VERSION,
args)`), while `PROMPT_VERSION` = `<judge pv>+present-2026-10-29` is the family's instrument: the
`EvalSpec.judge.prompt_version`, the stamp in results.json (summary: `digest.prompt_version(
PROMPT_VERSION, args)`), and what `floors()` matches. Retained: the digest's own cache keys and
versions are untouched.

## Floors

- **Lucky guessing** (DM, MCDM): the guesser sees no readout, so the basis rule cannot change its
  score. Re-stamp the frozen entries' `instrument` to the new `PROMPT_VERSION` (values unchanged;
  `wsbench freeze` from the cached runs re-scored, no new calls).
- **Prompt-only** (DM only; MCDM is excluded): re-measured under the new rule with
  `scripts/prompt_only_qwen_modal.py` at DM's current read positions, native and summary, Opus:
  **1.00 / 1.00** (every stock-model summary paraphrases the instruction; content-only 0.16 /
  0.08). Camila 2026-10-29, shown this, chose "narration counts in both": DM joins MCDM in
  `prompt_only.EXCLUDED` (and `adapt.floors.EXCLUDED`) with the measurement as the reason; the
  bar is the lucky floor. Nothing is frozen.
- **Lucky re-stamp, how** (critique round 1): `freeze` keeps a run file's own `instrument`, so
  re-freezing old run dirs would silently drop the floors; the frozen entries' `instrument` is
  edited in place instead (values unchanged, a `restamped` note added).
- **Other consumers** (critique round 1): `scripts/summary_mode_compare.py` `_dm_strict` and its
  retained-evidence rule follow the new headline; `text_inversion`'s DM adapter follows it too
  and its `_not_gated` reason is reworded (DM stays out of the ATI subset); the MCDM content-only
  channel recomputes conflict and partner on content picks only, reproducing plan 0025.

## Tests, docs

- Sanctioned pre-existing test edits: assertions on DM's headline / `content_bound` value where
  a narration row now passes; MCDM assertions that a narrated dictated pick does not credit
  (it now does; the incidental / invalid cases stay); summary-mode tests that read
  `PROMPT_VERSION` as the fingerprint version (they move to `JUDGE_PROMPT_VERSION` where they
  check fingerprints, and keep `PROMPT_VERSION` where they check the stamp).
- New tests: narration credits in both families; incidental never does; the split versions
  (cache hit across the rule change: a re-run on a cached out dir makes 0 calls; the results
  stamp carries `+present`); DM white_bear stays content-only.
- README (root entries + judges table), both family READMEs, the baselines README.

## After merge
Re-score the cached s3d-rl600 runs (MCDM rerun; DM d3b native + summary) under the new rule from
cache (0 calls) and update the audit page.

## Checks
`ruff check .`, `ruff format --check .`, `pytest -q`.

# 0030: buggy_code scored on buggy/clean twin pairs

Camila, 2026-10-29: score each buggy/clean twin pair as one unit — a hit when the lens calls the
buggy program buggy and does not assert a bug in its clean twin; "for the correct it just can't
assert that there is a bug, anything else is clean"; a separate specificity metric, "report
specific as the headline"; run the prompt-only baseline; author the missing clean twins, record a
`twin` field; fix the known judge leaks; and include the family in the macro.

Why (2026-10-29 audit): the blended 1–10 mean rewards a lens that always says "correct" (5.41,
above every measured arm, 3.27–5.08), because "correct" on a clean twin scores 7–10 even when the
readout is an unrelated `# Output:` frame. A pair rule scores both degenerate strategies at 0
(always-correct misses every bug; always-bug false-alarms every twin; a lens claiming "bug" at
random with probability p scores p(1−p) ≤ 0.25).

## 1. Pairs and the bank

_Outcome (2026-10-29): 14 of the 15 new twins passed the gate (2 after one rewrite); the
age-underflow twin failed twice and its pair was dropped (`twin_dropped`), so the bank has 63
items and 24 pairs (not 64 / 25)._

- New item field `twin` (the partner's `name`), set on both members of every pair.
- The 10 existing exact twins (code similarity ≥ 0.72; the next-best match is 0.60):
  inclusive-day-count↔clean-nights, string-sorted-ids↔clean-numeric-sort,
  go-range-copy↔clean-go-range-index, percent-over-hundred↔clean-pct-clamped,
  c-off-by-one↔clean-c-loop-bound-correct, stock-below-zero↔clean-stock-capped,
  discount-applied-twice↔clean-discount-once, minutes-not-carried↔clean-minutes-carried,
  accumulator-reset-in-loop↔clean-streak, quantity-refund-credit↔clean-validated-qty.
- **15 new clean twins** for the unpaired buggy programs (refund-exceeds-price, simple-not-compound,
  raise-div-empty-filter, int-truncation-cents, age-underflow, inverted-condition-branch,
  batch-tail-dropped, case-split-count, startswith-prefix-auth, go-slice-append-alias,
  go-ignored-atoi-err, go-nil-map-write, c-int-div-float, rust-move-after-use, rust-unwrap-parse):
  the same program with the bug fixed and nothing else changed (same identifiers, structure, line
  count ±1, no new comments or names that announce the fix — the audit's trouble-vocabulary rule).
  Each carries `src: clean`, `twin`, `language`, `lang_group`, `verified` (the executed truth in the
  bank's format, `exec: exit N; stdout = '...'`, from actually running it: python and C locally,
  Go and Rust in a Modal image with their toolchains), `why_correct`, `looks_like` (the buggy
  twin's category), `added: "2026-10-29 (plan 0030)"`.
- **Gate for the new twins** (the bank's own gates, restated for a clean program): on Qwen3.6-27B,
  thinking off, (a) the capability gate — the exact question `capable/questions.py` builds for a
  buggy_code item (predict the output), greedy + 10 samples at T=0.7, pass = greedy right and
  ≥ 8/10 right against `verified`; (b) the no-invented-bug gate — shown the bare program (the
  family's render), a greedy continuation of 256 tokens must not assert a bug, graded by Opus with
  a one-line rubric ("does this continuation claim the program has a bug, error or wrong result?").
  Both generate on Modal with vLLM via `scripts/buggy_twin_gate_modal.py` (+ `buggy_twin_gate_grade.py` for the Opus grading; both
  written with the twins) (the
  `ati_qwen_modal.py` recipe); `wsbench capable` is NOT used because it reaches Qwen through
  OpenRouter, which must not be called from the dev box. Grading runs locally on Opus (ant
  profile). A twin that fails is rewritten once, else its pair is dropped and reported.
- The 14 existing clean items with no buggy twin stay in the bank as false-alarm diagnostics
  (`extras.false_alarm_rate_orphan_clean`), outside the pair headline.
- Read cell unchanged (EOF anchor; L60 python, L56 others). The new twins need readouts produced
  for every reported arm (s3d-rl600 O-lens now; others when re-run). An existing 49-item readouts
  file now misses 15 items: judging it needs `allow_missing=True`, its pairs with a missing member
  are undecided, and no old-arm number is shown as a new-headline number.
- **Scope** (the unverbalized_hint pattern): `items=` expands to whole pairs (naming either member
  pulls in its twin), `limit=` counts pairs, `n_items` = pairs in scope, `chance` = 0.0 (numeric;
  the label gives the degenerate floors); a run with any undecided pair is not `complete`.
- **Adapted banks** (`adapted/*/buggy_code.json`) carry no `twin` field and per-model drops: every
  item there is an orphan, the pair headline is `None` (no value, so not averaged), and the extras
  still report. The 15 new twins are not adapted in this plan.

## 2. Scoring

- Stage A (blind, unchanged in role) gives each item a claim: `bug` | `correct` | `none`.
  **Clean side:** a twin is clean-OK unless its claim is `bug` ("anything else is clean"; silence
  and unrelated output frames are fine). **Buggy side:** the claim must be `bug`.
- **pair_rate** = pairs whose buggy member claims `bug` AND whose clean member does not.
- **specific_pair_rate (the headline, `metric="pass_rate"`)** = pairs that are pair hits AND whose
  buggy member's Stage B grade is ≥ 8 (mechanism and consequence right, per the existing rubric).
- Undecided: a pair with an unjudged member (a failed Stage A, or a failed Stage B on a buggy
  member claiming `bug`) is undecided unless the other member already decides it (a clean `bug`
  claim, or a buggy non-`bug` claim, fails the pair whatever the other member says).
- Stage B runs as today on every non-`none` claim (feeds the retained extras), but is VOTED only
  for buggy pair members claiming `bug` (the only grades the headline reads); everything else gets
  one call.
- Retained as extras, unchanged in definition: the blended 1–10 `score`, `score_buggy`,
  `score_clean`, claim rates, `false_alarm_rate_clean`, `score_hist`, `per_stratum` (per item, as
  today); new `per_stratum_pairs` (pair and specific rates by the buggy member's stratum).
- **Rows** stay one per item (`summary_mode_compare.item_values` needs them), each gaining
  `pair` (twin name or null), `pair_hit`, `specific_hit` (on the buggy member; null elsewhere);
  pair verdicts are listed under `extras.pairs`. `completeness` counts cells/items exactly as
  today (`n_expected` / `n_missing` / `n_unjudged` per item) plus: any undecided pair makes the
  run incomplete; an orphan never does.
- **Macro:** the family enters the macro (its headline is now a pass rate); `CHANCE_LABEL` states
  the degenerate-strategy floors (always-correct 0, always-bug 0, random ≤ 0.25).
- Summary mode: unchanged per item (one digest per item, Stages A/B on it), the pair rule on top.

## 3. Known-leak fixes (prompt_version bump)

- **Non-English bug claims** (the audit's 3–4 missed false alarms): Stage A is told explicitly
  that an assertion of an error, failure, crash or wrong result in ANY language (e.g. 报错 / エラー)
  is a `bug` claim.
- **Unrelated output frames:** Stage A labels a `# Output: X` / "expected output" frame about a
  function or output that does not appear elsewhere in the readouts as `none`, not `correct`
  (under the pair rule this no longer earns credit, but it keeps `score_clean` honest).
- **Generic-crash leniency:** the bands are NOT changed (that would move `score_buggy` and the ATI
  meaning): a right consequence without the mechanism stays 6–7, which the specificity bar (≥ 8)
  already excludes. Stage B gets one added sentence: identical evidence gets an identical grade, and
  a generic word ("error", "exception") with no stated consequence is the 2–3 band the rubric
  already defines.
- **Judge noise** (17/49 items flipped between identical runs; temperature is dropped on the
  Anthropic route): Stage A is asked 3 times per item, each vote its OWN cache key
  (today's key with `|v1..v3` appended, in both modes: native `{i}|L{layer:03d}|infer|v{k}`,
  summary `{cell.key}|infer|v{k}`, so the votes are three real calls), and the majority claim kept; with no
  majority (all three differ) the claim is `none`; if any of the 3 votes fails the item is
  unjudged (as for Stage B). Stage B grades the `inferred` text of the
  lowest-numbered vote that agrees with the majority, 3 times (`<item>|grade|v1..v3`), and keeps the
  median; if any of the 3 grades fails the member is unjudged. The summary-mode digest is not
  voted (one digest per item; the votes run on it). A test checks that 3 distinct calls are made.

## 4. ATI

buggy_code moves to `text_inversion.NOT_GATED` ("pair-level headline (plan 0030); a pair verdict
for the ATI gate is out of scope") and its entry leaves `anti_text_inversion.json`; otherwise the
new bank's `bank_sha` and prompt version would make every `anti_text_inversion=True` run exit 2,
and the drift guard would compare a per-item score rate with the pair pass rate.

## 5. Floors

- **Prompt-only:** re-measured with `scripts/prompt_only_qwen_modal.py` on the 64-item bank at the
  read cell, judged under the new rule (native and summary) with NO `layers=` override (the rows sit
  at each item's own layer, L60 python / L56 others), frozen into BOTH `prompt_only.json` and
  `prompt_only_summary.json` (both hold a stale buggy entry). As the README already warns,
  the program IS the prompt, so this bounds what the text gives away rather than a bar a lens must
  clear; it is drawn in `report`.
- **Lucky guessing:** not applicable (no option lists); the degenerate-strategy floors in
  `CHANCE_LABEL` stand in.

## 6. Tests, docs

- Pre-existing tests asserting the blended `score` headline, `metric == "score"`, macro exclusion
  of buggy_code, or the old prompt text are updated (sanctioned); new tests: the pair rule (both
  degenerate strategies score 0, a silent clean twin is clean-OK, undecided pairs), the
  specificity threshold, majority/median voting, the twin-field invariant (every `twin` points at
  an existing item of the other src, symmetric).
- Also: `test_text_inversion.py` (buggy cases), `test_summary_mode_buggy.py`,
  `test_summary_mode_compare.py` and `scripts/summary_mode_compare.py` (buggy leaves `CONTINUOUS`;
  its item verdict becomes the pair rule), `atlas/build.py` / `atlas/export_cb.py` descriptions,
  `__init__.py` `calls_per_arm`, the `n == 49` bank test; a test that orphans stay out of the pair
  headline.
- README (family: the pair rule replaces the "pairwise pick not used: only 10 twins" note and the
  macro-exclusion line; root entry + judges table), CLAUDE.md if it lists macro membership, and the
  stale `prompt_only.json` buggy entry replaced by the re-measured one.

## Checks
`ruff check .`, `ruff format --check .`, `pytest -q`; s3d-rl600 native + summary under the new rule
with the prompt-only floor beside them on the audit page.

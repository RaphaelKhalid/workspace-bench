# Workstream "role_bound": Role-bound association

Code of record: `/root/wsb-bp-base` (origin/main cd6b0fa). All `file:line` below are in that tree
unless marked otherwise. This spec rebases onto the infra PR and uses ONLY the names in
`plans/SHARED_API.md`; it re-implements none of that machinery. Names used:
`reads.load` / `reads.select` / `reads.check_full` / `reads.stamp` (infra §2.0, §2.6),
`ReadSpec.lite_positions` / `lite_layers`, `EvalSpec.min_full_positions` / `full_contiguous`,
`readplan.GRID` and `layers=all|each|<csv>` (§2.1), sidecar `sampling` and
`readouts.normalize` / `readouts.bulleted` (§2.9), `digest.collapse(..., task_note=, expect_all=)`,
`EvalSpec.task_note`, `digest.quote_ok` / `digest.statement_lines` (r2, §2.7.9) /
`digest.fold_quote` / `digest.native_lines` / `digest.Line` (§2.7, §2.8),
`digest.prompt_version` (§2.7.8), `mc.options_with_cannot` / `mc.CANNOT` / `mc.seeded_shuffle` /
`mc.READOUT_PHRASE` / `mc.token_note` / `EvalSpec.flat_types` / `EvalSpec.multi_select` / `mc.form_in`
(§2.4, §2.7.2, §2.7.6, §2.8), `mcjudge.layer_pick_columns` (§2.13), `registry.bank_path` (§2.12),
`baselines.prompt_only_opus` / `po-opus-v1` / `prompt_only_summary.json` (§2.11), and the gpu
workstream's `scripts/audit_verdicts.py` (G12 / R4b leniency audit) and required campaign arms
(`s3d-rl600`, `jlens`, `mlnla-rl2-2000`). The family-local `gate.statement_lines` of round 1 is
retired: the bullet splitter now lives in infra as `digest.statement_lines` and this family only
calls it. Binding decisions: `plans/_fable_decisions.md` (Q1 and Q4 touch this family; the ATI,
lite and PR #75 decisions too).

Round 3 shared names also used here (SHARED_API r3): `digest.BULLET_MARK` (`" ⁞ "`, bullet
boundaries visible in digest lines), `Line.bullet`, `extras.n_unverified_bullet` (the shared
count of picks voided by the one-bullet rule; replaces this spec's round-2
`n_quote_cross_statement`), `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`
rendered in every judge prompt (role_bound: `flat_types=()`, `multi_select=False`), the
support-share lite-site procedure and `scripts/lite_site_table.py` (infra §2.6), `results.MACRO_METRICS`
/ `EvalSpec.not_in_macro = ""`, and the gpu runbook steps R4b (G12 audit, `audit_verdicts.py`),
**R4c** (fix-and-rerun loop), R6 (floors), R8 (ATI, G13 r3 rule) and G11 (`site/manifest.json`).
`digest.number_flood` does not apply to this family (no numeric gold).

Camila's section, verbatim:

> Make sure the judge is not too lenient, i agree with the examples you showed: the content from
> different samples should not be artificially pieced together, we are looking for true relational
> content, we should require the roles and action to be in the same readout
>
> Also make sure that the lens is not letting close words pass by like "parent" being chosen when
> the lens mistakenly says "grandparent"

---

## 1. Current state

**Bank.** `evals/role_bound_association/items.json` is a list of 100 items: 50 `pair_id`s, each
with direction `ab` and `ba`. Strata: `stereotypicality` is congruent 39, incongruent 39 or
neutral 22. Role words are blocklisted from the stimulus. The bank has 95 distinct roles. These
include the near-neighbours `parent`, `grandparent`, `grandmother`, `grandson`, `mother`, `son`,
`child`, `toddler`, `father` and `daughter`. There are 50 actions, each used by exactly one pair.
Registered in `src/wsbench/evals/role_bound_association/__init__.py:11-23`, with
`calls_per_arm="≈ 11.4k"` (`:21`).

**Read plan.** `src/wsbench/readplan.py:468-481`:
- render `chat_summarize`: the stimulus plus `SUMMARIZE_SUFFIX = "\n\nSummarize the preceding
  story in one sentence."` (`:20`);
- rule `suffix_text_then_tail` (`:153-158`): every token from `Sum` to the end of the render. That
  is 19 Qwen positions: the 10 suffix tokens, then
  `<|im_end|> \n <|im_start|> assistant \n <think> \n\n </think> \n\n`;
- layers `SIX = [20, 28, 36, 44, 52, 60]` (`:17`), hardcoded;
- there is no lite rule.

Story positions are never planned. The judge does not enforce this: `judge.py:59`
`selected = cells  # every row is a site`.

**Judge (one call answers three MCs).** `judge.py:31-51` `build_block`:
- People list, shared by Q1 and Q3: the item's two `"Name, the role"` labels, plus the `a`-labels
  of 3 random other pairs (`:43-44`).
- Actions (Q2): the gold action plus 4 random others (`:46`).
- `mc_block` (`:31-34`) shuffles with a seed and appends `mc.CANNOT` (`src/wsbench/mc.py:10`)
  last, so each MC has 6 options.

Prompts are in `prompts.py`:
- `SYSTEM` (`:47-54`) says "You judge the READOUT of an interpretability lens …", allows partial
  names ("'Marc', 'Bangk'"), and forbids world knowledge.
- `HEADER`, `Q1`–`Q3` and `BLOCK` are at `:67-76`.
- `SCHEMA` (`:56-65`) is `q1_choice, q2_choice, q3_choice, evidence`. There is no quote field and
  no verification.
- `PROMPT_VERSION = "oa-v1"` (`:45`).

Scoring: a site passes iff all three answers are correct (`judge.py:117`, `:126`). An item passes
iff any site passes (`score.py:33`). Chance is (1/6)^3 (`score.py:50`).

**Native path** (`judge.py:62-148`):
- Prose: the judge sees `join_samples(samples)` (`judge.py:82`, `mc.py:41-42`).
  - s3d-rl600 is the multi-bullet "concepts" O-lens (gpu.md §1.1): k=1, ONE generation per
    activation that lists about 4 distinct concepts, each as a `- ` bullet. Verified in
    `/workspace/root/wsbench-pub/outputs/readouts/s3d-rl600/role_bound_association.jsonl`: every
    row has `len(samples)==1` holding about 4 bullets. The judge freely combines those separate
    concept bullets into one relation (A1).
  - The single-bullet `*-x4` arms (e.g. `rl-onchat-x4`) pack 4 separate generations into one
    string; there the judge combines different generations.
- Tokens: each cell is first turned into prose by the J-lens-specific interp-v1 summarizer
  (`judge.py:67-80`, `src/wsbench/summarizer.py:13-21`), which "commit[s] to the most specific
  reading". The judge sees only that prose.

**Summary path (the CLI default; `runner.py:54-65` sets `aggregate=summary`).**
`judge.py:151-249`:
- All of an item's cells (every layer and position) go to one `digest.collapse` (`:170-178`) with
  `task_note=DIGEST_TASK_NOTE` (`prompts.py:81`). That note is ignored today, because
  `digest.DEFAULT_VARIANT = "blind"` (`digest.py:34`).
- The judge sees `SUMMARY_NOTE` + digest + block in one call keyed `<id>|L-1` (`:182-190`).
- The extractive digest line is one whole sample flattened by `_one_line` (`digest.py:468-480`,
  `render_summary` `:851-877`), so one digest "line" holds an s3d generation's ~4 concept bullets
  (or an x4 cell's 4 packed generations) with the bullet breaks collapsed to spaces: `"- a\n- b"`
  becomes `"- a - b"`, and neither the summarizer nor the judge can tell a bullet boundary from a
  hyphen. (After infra §2.7.10 it renders `- a ⁞ b`; see C1.1.)
- `SUMMARY_NOTE` (`digest.py:106-113`) says "pieces on different lines never combine". The family
  README (`evals/role_bound_association/README.md:201-203`) says the opposite: "agent and patient
  read at different sites can pass together … This is the pooling plan 0020 asks for". Nothing
  verifies which line the answer came from.

**Option-list defects found while scoping** (`build_block` run on the live bank):
- **Identical duplicate options.** In `oa-doctor-nurse-instruct-ab`, Q1 and Q3 both list
  "Priya, the nurse" twice, and that label is the gold patient (golds (1,2,1)). If the judge
  picks the second copy, it is scored wrong. `oa-teacher-parent-blame-ba` lists
  "Marcus, the police officer" twice.
- **Shared names.** 57/100 people lists contain two people whose names share their first 4
  letters. The audit counted 35 sharing the full first name, e.g. "Marcus, the police officer" and
  "Marcus, the journalist". Under the partial-name rule, a name-only readout cannot pick between
  them.
- **Shared roles.** A distractor can have the same role as an item person (Priya the nurse in the
  doctor-nurse items). A distractor can also share a name AND a near role: in
  `oa-child-grandparent-hug-ab`, gold "Ruth, the grandparent" sits beside other pairs' "mother"
  roles.

**Layers on the judge side.** `load_readouts(..., layers=args.layers)` (`judge.py:58`) is
honoured. There is no family layer restriction.

**Baselines.**
- `evals/baselines/prompt_only.json` `role_bound_association`: rate 1.00, saturated, judge
  `google/gemini-3.8-flash`, instrument `oa-v1`, judged native per cell (13,460 cells), not
  through the digest. `prompt_only.py:40` lists it in `SATURATED`.
- `lucky_guessing.py:145-153` reuses `build_block`.
- `anti_text_inversion.json`: 9 ATI items, instrument `oa-v1`, under the 20-item cutoff.

## 2. Change list

### C1. "Make sure the judge is not too lenient, i agree with the examples you showed: the content from different samples should not be artificially pieced together, we are looking for true relational content, we should require the roles and action to be in the same readout"

**Definitions (go into the README headline).**
- A *sample* is what infra §2.9 says it is, from the producer-declared `sampling`: one s3d-rl600
  or NLA generation (`prose1`), one generation of a single-bullet `*-x4` arm (`bullet4`, 4
  separate samples per activation), or one ranked top-10 token list (`tokens10`).
- A *statement* is the unit a relation must sit in: one top-level `- ` bullet of a prose sample,
  or the whole sample if it has no top-level bullets, or one ranked token list.
- An item passes only if at least one statement, on its own, names the agent, the action and the
  patient, and states the direction.

Why "statement" and not "sample": shared rules (Q4, infra §2.7) already forbid combining across
samples, positions and layers. The s3d generation is one sample, but its bullets are separate
concepts (the CONCEPTS prompt asks for "distinct concepts … each as a '- ' bullet"); "Grandfather"
on one bullet and "hugs her mother" on another is exactly the stitching Camila rejects (A1). The
statement rule is now the SHARED round-2 rule for relational content (infra §2.7.9, §2.9.4;
SHARED_API "sample licence (r2)"): relational content must lie within ONE top-level bullet of a
prose1 sample, and infra's round-1 licence for "a relation stated across two of its bullets" is
withdrawn. This family applies it exactly as infra specifies, through
`digest.quote_ok(quote, digest.statement_lines(lines, cells))`; it builds no splitter of its own.

C1.1 **Sampling comes from the sidecar; the family does no unpacking.** `judge.py:58` calls
`reads.load(args, FAMILY, ids=…)` instead of `load_readouts`; `reads.load` applies
`readouts.normalize(cells, sampling)` from the sidecar.
- `prose1` (s3d-rl600, NLA): one sample per cell, kept whole.
- `bullet4` (`*-x4`): 4 separate samples per cell, unpacked by infra.
- `tokens10`: the top-10 list.
- Native render: `judge.py:82` renders `readouts.bulleted(c.samples)` for `bullet4` (one `- `
  line per generation) and `mc.join_samples(c.samples)` for `prose1` (the generation as written,
  bullets intact). Either way each statement is one line of the judged text.
- Digest bundles render each sample as its own `- ` line (infra §2.9.5); no family code. A
  `prose1` sample with ≥ 2 top-level bullets is ONE digest line whose bullets are joined by
  `digest.BULLET_MARK` (infra §2.7.10): the s3d generation of A1 reads
  `- Mia runs up the stairs to find Grandfather ⁞ She hugs her mother`, so the summarizer and the
  judge both see where one statement ends (critique r2 item 12). No family code.
- Tests (`tests/test_role_bound_association.py`):
  - `test_bullet4_judged_as_four_samples`: a sidecar `sampling: bullet4` cell holding one packed
    4-generation string yields a native user prompt with 4 `- ` lines and a digest bundle with 4
    lines under one header.
  - `test_prose1_multibullet_generation_kept_whole`: a `prose1` s3d cell with 4 concept bullets
    is ONE sample (one digest line, rendered with three `⁞`), and its 4 bullets are 4 statements
    for the gate (C1.4). Shared: infra's `test_digest.py::test_digest_line_shows_bullet_boundaries`.

C1.2 **New `SYSTEM` (`prompts.py:47-54`)**, tool-name-free (D5): it opens with
`mc.READOUT_PHRASE` interpolated, uses `mc.CANNOT` as the cannot-tell text, and states the Q4
token rule in the same words as `mc.token_note()`. Rendered text, verbatim:

```text
You judge readouts of a language model's internal activations: noisy free text, or ranked lists of top vocabulary tokens, decoded while the model read a short story in which one person does something to another. Answer the three multiple-choice questions under these rules.
1. One statement at a time. A statement is one line of the readouts: one '- ' bullet of a free-text sample (or the whole sample if it has no bullets), or one ranked token list. In a free-text sample, bullets are separated by ⁞; each part between ⁞ marks is its own statement. All three answers must come from the SAME statement, and that statement must itself name the person who acts, the action, and the person acted on, and say which way the action goes. Never combine people, actions or directions taken from different statements, bullets, samples, positions or layers, even when together they would fit an option. If no single statement settles a question, answer "cannot tell from the readout" for it.
2. Exact people. A person matches an option only if the statement gives that person's name (partial names such as 'Marc' for 'Marcus' count) or that person's role, in the same or a synonymous or gendered form ('mom' or '母亲' for a mother, 'cop' for a police officer). A neighbouring but different role is a different person: 'grandmother' is not 'parent', 'mother' is not 'grandparent', 'social worker' is not 'teacher', 'nurse' is not 'doctor'. Never pick an option because it is the closest one, or the only one of its kind.
3. Exact action. The statement must state the action, with the same verb or a clear synonym ('pursued' for 'chased'). A related but different action ('watched' for 'spied on', 'confronted' for 'blamed') does not match.
4. Direction. Who is the agent and who is the patient must come from what the statement says, never from what is typical. Tokens of ONE ranked list may be read together to express one meaning, and tokens of adjacent positions at the same layer only to spell one word or name split across them; nothing else combines. A ranked token list names concepts, not who did what to whom: unless a token in it itself states the direction, answer "cannot tell from the readout" for Q1 and Q3 from a token list. A token list that holds two or more of the options singles out none of them, whatever their rank; an option that is the only option on its list is singled out by that list.
5. Do not use world knowledge or plausibility to fill gaps. If the readouts do not support an answer, choose "cannot tell from the readout".
Then give "quote": a span copied character for character from the ONE statement your answers come from, never across a ⁞ mark (from a token list, its tokens joined by " | "; a word spelled across adjacent positions, as that plain word), without any bracketed marker. Give "" if you answered "cannot tell from the readout" to any question.
```

- `HEADER` (`:70-74`): drop "The readout may describe two people; the sentence it implies …"
  and use "One statement may describe two people; the sentence it states has the form
  {person A} -> {action} -> {person B}. People may be referred to by name or role." `Q1`–`Q3`
  are unchanged.
- Both paths render the shared token note from the spec, never a bare constant (SHARED_API r3):
  the native token path appends `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`
  (C1.7), and the summary path renders the shared `SUMMARY_NOTE` followed by the same
  `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` call in place of
  `SUMMARY_NOTE_TOKENS` (infra-owned text, which carries the one-bullet relation clause, the
  "(in a free-text sample, bullets are separated by ⁞)" clause and the options-relative
  flat-list clause). role_bound declares `flat_types=()` and `multi_select=False`, so the text
  equals `mc.token_note()`; covered by the shared `test_token_note_rendered_from_spec`.
- "Add, never relax" (SHARED_API r3): rule 4's "cannot tell for Q1 and Q3 from a token list
  unless a token states the direction" is an added requirement on top of the shared note; the
  family never credits a pick the shared note voids.
- Rule 4 is Q4 applied: one list's tokens combine for meaning; a bag carries no direction
  (audit J-lens cases `oa-referee-player-warn-ab` L60 and `oa-pilot-passenger-reassure-ab` L44).
  Its last sentence is the options-relative flat-list rule (infra §2.7.2, SHARED_API "flat-list
  rule (r2)"), worded as in `mc.token_note()`; there is no rank-1 exception.
- Tests:
  - `test_prompts_in_readme.py` (existing, generic) checks the README copy.
  - `test_role_bound_association.py::test_system_rules_present`: the five rule headers, the
    `mc.READOUT_PHRASE` opening and the `mc.CANNOT` text are present. Tool names are covered by
    the shared `tests/test_prompt_tool_names.py::test_no_tool_names_in_prompts` (no family copy).
  - `test_rendered_prompt_matches_golden_v2` against a new golden
    `tests/golden/role_bound_association_prompt_v2.txt`.

C1.3 **Schema gains `quote`** (`prompts.py:56-65`): `q1_choice, q2_choice, q3_choice, quote,
evidence` (all required; `evidence` stays as the free-text reason, for audit).

C1.4 **Mechanical single-statement gate** (new `src/wsbench/evals/role_bound_association/gate.py`,
family conditions only). A row's `pass` = all three choices are gold AND `gate_ok`. `lines` is
`col.evidence[id]` in summary mode and `digest.native_lines([cell])` in native mode. `gate_ok` is
true iff all of:
1. **(a) Quote verified** by the ONE shared verifier: `digest.quote_ok(quote, lines)` (infra
   §2.7.4: prose quote within one sample; token quote's ` | `-parts all whole tokens of ONE list,
   or one word spelled across adjacent positions of one layer). No local copy of any verifier.
2. **(a′) Within one statement** (the shared relational-content rule, infra §2.7.9). Condition:
   `digest.quote_ok(quote, digest.statement_lines(lines, cells))`, where `cells` are the item's
   cells as returned by `reads.load` (summary) or `[cell]` (native). `digest.statement_lines`
   (infra-owned) splits each prose `Line` at `digest.BULLET_MARK` into one `Line` per top-level
   `- ` bullet (`Line.bullet = 0, 1, …`; an unbulleted sample is one `Line`; token lines
   unchanged) and checks each maps to a loaded cell. `digest.fold_quote` maps `⁞` to a space, so a
   quote copied across a `⁞` passes (a) and fails (a′) — which is exactly the count
   `extras.n_unverified_bullet`. `gate.py` defines no splitter and no verifier; it only combines
   the shared calls with (b).
3. **(b) The quote refers to the gold agent AND the gold patient.** A person is referred to by:
   - a name hit (family rule): a Latin word of 4 or more letters whose first 4 letters,
     casefolded, equal the option name's (so "Marc" matches Marcus and "Martha" matches Marta),
     or the exact name; or
   - a role-term hit: `mc.form_in(digest.fold_quote(quote), lex[role]["terms"])` — Latin terms
     word-bounded, CJK terms only as listed forms (infra §2.7.6, critique 19). No
     "no Latin letters → accept" shortcut.

   A word-bounded match is what stops "grandmother" from matching the `parent` term "mother", and
   "grandparent" from matching "parent".

   **Amendment (PR review, 2026-10-30).** Both halves of (b) are tightened/fixed, rejecting only
   on top of the rule above except where the old masking was a bug:
   - *Name*: the hit must be a capitalised word; a prefix variant must also be within 2 edits of
     the name and must not be a word of any lexicon/near-role term or a month/weekday. The bare
     prefix-4 rule let "victim" name Victor (victim is a listed near role of bystander,
     oa-paramedic-bystander-thank-*), "miles" Miles, "grandmother" Grant, "delivered" Delia.
   - *Role term*: an own-term hit is blocked only when it lies strictly inside a longer
     occurrence of a different (lexicon or near) role's term. The first implementation masked
     every other-role term as a substring, which also erased the gold role's own compounds
     ("star player", "reserve player", 窃贼, 消防队员, 教区居民 — 10 listed terms never matched).
     Tests: `test_role_bound_lexicon.py::test_every_own_term_refers_to_its_own_role`,
     `::test_longer_other_role_term_never_names_role`, `::test_no_bank_name_is_a_lexicon_word`;
     `test_role_bound_gate.py::test_own_compound_containing_other_role_term_counts`,
     `::test_common_and_role_words_are_not_names`, `::test_star_vs_reserve_player_passes_gate`.

The action and the direction stay with the LLM. Bank actions include near-synonyms (deceived /
lied to / cheated, feared / dreaded, resented / envied), so a lexical action gate would be wrong
more often than right.

Accounting:
- A gold triple with a failed gate is a fail, counted in `extras.n_gate_rejected`, with the
  sub-counts `n_quote_unverified` (a), `n_unverified_bullet` (a′; the shared SHARED_API r3
  name, printed per family by gpu G9 `audit_run.py`; up to 5 of these picks enter the G12 audit
  sample so the auditor can call the rule too strict),
  `n_agent_unreferenced` and `n_patient_unreferenced` (b).
- Each row carries `gate: {quote_ok, one_statement, agent_ref, patient_ref}`.

Tests (`tests/test_role_bound_gate.py`):
- `test_stitched_quote_rejected`: a quote spanning two samples (bullet4) fails (a).
- `test_cross_bullet_quote_in_one_prose1_generation_rejected`: an s3d `prose1` generation
  "- Mia runs up the stairs to find Grandfather\n- She hugs her mother" (digest line
  `- Mia runs up the stairs to find Grandfather ⁞ She hugs her mother`); quotes "find Grandfather
  She hugs" and "find Grandfather ⁞ She hugs" both pass (a) and fail (a′), and
  `extras.n_unverified_bullet == 1` per pick.
- `test_quote_inside_one_bullet_passes`.
- `test_grandmother_is_not_parent` and `test_mother_is_not_grandparent`: (b) fails.
- `test_partial_name_prefix4`: Marc→Marcus passes; Mark→Marcus fails.
- `test_cjk_role_term_needs_listed_form`: 奶奶 → grandparent (listed); an unlisted CJK quote fails.
- `test_token_quote_same_list_only` (calls through `digest.quote_ok`).
- `test_gold_choices_with_bad_quote_is_fail_and_counted`, run through `judge.run` with
  `fake_llm`.
- `test_gate_calls_shared_quote_ok`: AST check that `gate.py` defines no quote verifier and no
  bullet splitter, and calls `digest.quote_ok` and `digest.statement_lines` (no
  `gate.statement_lines` symbol exists).
- Shared, reaching this family: infra's `test_digest.py::test_relation_across_two_bullets_fails`,
  `::test_relation_in_one_bullet_passes` (§2.7.9) and `::test_digest_line_shows_bullet_boundaries`
  (§2.7.10).

C1.5 **Summary-mode binding is per statement, not per digest.**
- Delete README §Summary mode "Binding is summary-level, by design" (`README.md:201-203`) and
  write the rule from C1.
- `USER_SUMMARY` is unchanged. The shared `SUMMARY_NOTE` already says lines never combine, and
  infra's round-2 `DIGEST_SYSTEM` sentence ("Within one free-text sample, each '- ' bullet is its
  own statement: a relation … counts only if one bullet states it", §2.7.1, extended in r3 with
  "(in a free-text sample, bullets are separated by ⁞)", §2.7.10) tells the summarizer the same
  rule on a bundle where the boundaries are visible; the gate (C1.4 a′) enforces it mechanically.
- The task note moves to the registry: `EvalSpec.task_note = "the model read a short story in
  which one person does something to another person, and was then asked to summarize the story
  in one sentence"` (no roles, names or action; `prompts.DIGEST_TASK_NOTE` becomes an alias of
  it). `_run_summary` calls `digest.collapse(FAMILY, cells_by_item, args=args, cache=cache,
  spend=spend, preflight=pre, task_note=SPEC.task_note, expect_all=cells)`. `DEFAULT_VARIANT =
  "task"` (infra) makes the note reach the summarizer (D5), so relational samples that occur
  once are kept. No family `FAMILY_DEFAULTS` entry and no family token cap (global
  `DEFAULT_TOKEN_CAP`, hierarchical overflow).
- Tests: infra's `tests/test_task_notes.py::test_every_summary_family_has_task_note_without_gold`.
  Family test `test_summary_mode_requires_single_statement_binding`: a digest whose agent is on
  line 1 and patient on line 2, with a scripted judge answering gold plus a quote spanning both
  lines, gives pass False and `n_gate_rejected == 1`; and a one-line digest
  `- Ruth hugs her mother ⁞ Mia, the grandchild, runs upstairs` with a quote spanning the `⁞`
  gives pass False and `n_unverified_bullet == 1`.

C1.6 **Full-read completeness and story-echo guard.**
- Completeness is the shared `reads.check_full` inside `reads.load`, with
  `EvalSpec.min_full_positions = 19` and `full_contiguous = True` (the 19 suffix + tail
  positions, one contiguous run ending at the final token). A file with fewer positions per
  (item, layer) exits 2, or is `partial` under `allow_missing` (`extras.partial_ids`). The
  `prompt_only:*` reader is waived by infra (one cell per id). No family-local completeness check.
  The r2 full-read guards are infra's and apply unchanged: exit 2 on a sidecar `reads: lite` under
  `reads=full`, on a plan layer missing under `layers=None`, and on sidecar `plan_sha` ≠
  `reads.plan_sha(FAMILY)`. Enforcement needs a sidecar; the cached v1 files are sidecar-less, so
  their judge tests are report-only (`extras.partial_ids_unenforced`, `config.reads_checked =
  no_sidecar`) — covered by the shared `test_sidecarless_file_is_report_only`.
- Story-echo guard (family-specific; `check_full` bounds the run's end and length, not its
  start). After `reads.load`, for each (item, layer) sorted by `pos`: if the cells carry `token`,
  find the last position whose cleaned token run starts the suffix text "Summarize the preceding
  story in one sentence." and treat cells before it as story positions.
  - Without `allow_missing`, any story position exits 2 with "readouts carry positions before the
    summarize suffix".
  - With `allow_missing=True`, they are dropped and counted in `extras.n_rows_outside_span`.
  - With no `token` field, cells are kept and counted in `n_span_unverified`. Skipped for a
    `prompt_only:*` reader (its one cell sits at the last full-read site).
  - Tokenizer-free and template-independent, because the suffix text is the family's own.
- Tests: `test_story_positions_rejected` (2 story rows plus the 19 span rows exit 2; with
  `allow_missing=True` the 2 rows are dropped and counted); infra's
  `test_min_full_positions_per_family` covers the 19.

C1.7 **Delete the J-lens interp step on the native token path** (infra §2.3, call site
`judge.py:67-80`). The native token path renders `render_bag(c.tokens)` (moved to
`wsbench.family`, `scores=False` default) as one ranked list per cell, followed by
`mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` (text equal to `mc.token_note()` here).
The `aux_models["summarizer"]` lookup is removed.
- Test: replaces `test_tokens_kind_routes_through_summarizer` (pre-existing,
  `tests/test_role_bound_association.py:127-143`; this deletion is sanctioned by infra §2.3). The
  replacement `test_tokens_native_judges_raw_list` asserts that no `TOKEN READOUTS:` call is made
  and that the judge user prompt holds `Marcus | chased` and the spec-rendered token-note text. Infra's
  `test_every_token_family_judges_raw_tokens_natively` also reaches it.

### C2. "Also make sure that the lens is not letting close words pass by like "parent" being chosen when the lens mistakenly says "grandparent""

C2.1 **Role lexicon.** New instrument data file
`evals/role_bound_association/roles_v1.json`. The bank file is untouched, so no bank version is
needed (D9; `EvalSpec.bank` stays `items.json`). Its version is stamped (C3.1).
- For each of the 95 bank roles:
  `{"terms": [...English + Chinese forms...], "near": [...neighbouring but different roles...]}`.
- `terms` holds the role, its synonyms and gendered forms, and the scene-generic hyponyms that
  name the same person. CJK forms are listed explicitly (they are the only CJK forms
  `mc.form_in` accepts). Examples:
  - `grandparent`: grandparent, grandmother, grandfather, grandma, grandpa, granny, 奶奶, 爷爷,
    外婆, 外公, 祖母, 祖父, 姥姥;
  - `parent`: parent, mother, father, mom, mum, dad, 家长, 母亲, 父亲, 妈妈, 爸爸;
  - `athlete`: athlete, swimmer;
  - `police officer`: police officer, officer, cop, policeman, policewoman, 警察, 警官;
  - `toddler`: toddler, child, kid, little girl, little boy, young girl, young boy, girl, boy,
    孩子, 小孩, 幼儿.
- `near` lists roles a lens plausibly confuses with this one:
  - parent: grandparent, stepparent, guardian;
  - grandparent: parent, great-grandparent;
  - mother: grandmother, stepmother, aunt;
  - son: grandson, nephew, stepson;
  - teacher: principal, professor, tutor, social worker;
  - doctor: nurse, paramedic, surgeon-in-training;
  - police officer: detective, security guard;
  - guard: police officer, warden;
  - and so on for every role.
- Authoring: the implementer drafts the file with Opus 5.5 through the ant CLI (no GPU) from the
  role list and the 100 stimuli. Camila or the implementer then reviews it by hand. The
  machine-checked constraints are in C2.4.
- Format note: relational_multihop keeps its own `NEAR` lexicon (different relation set); if
  both land, they share the `{terms, near}` shape but stay per family.

C2.2 **Option builder v2** (`judge.py`: new `build_block_v2(it, items, lex)`; `run` uses it).
People list (5 substantive options, then CANNOT):
1. the item's two people, `a_lab` and `b_lab`;
2. a **near-role distractor** for each of role_a and role_b: the first `lex[role]["near"]` entry,
   in seeded order, that is not one of the item's own roles. Its name is drawn from the bank name
   pool. If a role has no `near` entry, a random other-pair label is used instead;
3. one random other-pair `a`-label.

Each MC is built as `mc.options_with_cannot(mc.seeded_shuffle(options, seed))`: substantive
options shuffled, `mc.CANNOT` appended LAST and never shuffled in (D4, infra §2.4). No local
CANNOT handling.

Constraints, enforced by construction with seeded rejection sampling:
- no two labels are identical (this fixes the duplicate "Priya, the nurse" bug);
- no two names in a list share their first 4 letters, casefolded;
- no distractor role equals an item role;
- no distractor role's `terms` `mc.form_in`-match any item role's `terms`, and vice versa.

Actions (Q2) are unchanged in kind: gold plus 4 random others, but drawn from actions whose
pairs share no role with the item. Near-action distractors were considered and rejected: the
bank's near actions are often synonyms (deceived / lied to), so a "near" action would be a second
correct answer.

The seed is `f"{DATASET_SEED}:d2:{id}"`; per-question shuffles are `f"{DATASET_SEED}:{id}:v2:q1|q2|q3"`.
The bank is read through `registry.bank_path(FAMILY)`.

`build_block` (v1) is kept unchanged as a pure function, so the pre-existing source-parity test
`test_blocks_match_source_golden` (`tests/test_role_bound_association.py:36-41`) still passes
untouched. It documents the retired instrument.

Tests:
- `test_v2_blocks_golden`: new golden `tests/golden/role_bound_association_options_v2.json`.
- `test_v2_no_duplicate_labels`, `test_v2_name_prefix_distinct`.
- `test_v2_near_role_present`: the `oa-child-grandparent-hug-*` people lists hold a `parent` or
  `mother` distractor, and the `oa-teacher-parent-blame-*` lists hold a `grandparent` distractor.
- `test_v2_golds_follow_direction`.
- Shared: `tests/test_mc_cannot_tell.py::test_every_mc_judge_ends_with_cannot` and
  `test_cannot_pick_is_never_a_pass` (role_bound is in `lucky_guessing.BUILDERS`).

C2.3 **Prompt rule 2 and gate (b)** (C1.2, C1.4) turn "close word" into a failure on two levels:
- the judge is told a neighbouring role is a different person, and the near-role distractor is
  now on the menu, so "closest available option" no longer exists;
- even if the judge still picks gold, the gate requires a gold role term or name in the quote.

C2.4 **Lexicon validity tests** (`tests/test_role_bound_lexicon.py`):
- `test_every_bank_role_has_terms`;
- `test_near_roles_disjoint_from_terms`: for every role, no `near` role's own terms
  `mc.form_in`-hit the role's terms, e.g. `parent.terms` never contains "grandmother";
- `test_item_option_terms_pairwise_disjoint`: across every v2 people list, no two options'
  terms overlap;
- `test_terms_hit_own_stimulus_free`: no role term appears in the item's blocklisted stimulus
  (`it["blocklist"]["roles"]`), so a story echo cannot pass the gate by role term.

C2.5 **Adapted banks** (`src/wsbench/adapt/author.py:172-191`, `adapt/lint.py:261`). An authored
item whose role is missing from the lexicon is flagged by lint: "role not in roles_v1.json". The
builder falls back to `terms=[role]` with no near distractor, and the result counts
`n_roles_unlexiconed`. Test: `tests/test_adapt.py::test_role_bound_lint_flags_unlexiconed_role`
(new test; no existing assertion is changed).

### C3. Campaign decisions applied to this family

C3.1 **Stamps (D9).**
- `PROMPT_VERSION = "oa-v2"` (`prompts.py:45`): new SYSTEM, schema, builder, gate and the
  removed token interp step (this one bump covers infra §2.3's `+notokinterp` requirement; the
  family adds no separate suffix).
- `config.roles_lexicon = "roles-v1"`.
- The summary-mode stamp is cited, never written as a literal:
  `reads.stamp(digest.prompt_version(PROMPT_VERSION, args, FAMILY), reads.mode(args))`. Under
  the defaults that is `oa-v2` plus infra's digest/summary-judge suffixes, and `+reads-lite` only
  under lite. Test `test_summary_stamp_is_computed` computes the expectation from the same calls.
- Pre-existing `test_rendered_prompt_matches_golden` (`tests/test_role_bound_association.py:44-55`)
  asserts `PROMPT_VERSION == "oa-v1"` and the 4-field schema. **This spec sanctions exactly one
  edit to it:** rename it to `test_rendered_prompt_matches_golden_v1_builder`, keep its v1 golden
  file, and drop the two PV and schema asserts. They move to the new
  `test_rendered_prompt_matches_golden_v2`.
- `test_run_verdicts_and_numbers` (`:90-124`) is a sanctioned rewrite: scripted answers get a
  `quote`; golds come from the v2 golden; it uses `tests/conftest.py::native_args` (infra §2.5).
  Its numeric expectations (value 0.5, counts 9/1/1, any-of-grid floor) are kept.

C3.2 **D1 summary default.** No new family code. Under infra §2.5 the library default is summary,
and the README's "Summary mode" section becomes the main description. Native is documented as
the `opts=aggregate=native` ablation. Infra's
`test_every_registered_family_is_summary_or_native_only` covers this family.

C3.3 **D2 lite/full.**
- Full is unchanged in positions: the 19 suffix + tail positions (every token of the summary
  sentence plus the chat tail), now at GRID.
- `readplan.py:468-481` gains `lite_positions={"kind": "final_token"}`, `lite_layers=None` on the
  role_bound row: infra §2.6's table says the summarize-suffix siblings stay `final_token` until
  the pre-registered procedure runs (critique 35). The round-0 family choice of `offset_from_end
  k=4` is withdrawn as a frozen value and becomes one of that procedure's (≤ 5) candidates.
- The procedure is infra §2.6's pre-registered **support-share** procedure (round 3, critique r2
  item 13: Camila's "figure out where it is most commonly held" is a support criterion), run by
  the shared `scripts/lite_site_table.py`; the family adds nothing to it:
  1. for each suffix-span position, as its `offset_from_end` k, `share(k)` = gold-bearing
     `[support]` lines at k / gold-bearing lines in the whole span, where gold-bearing means the
     line's evidence `mc.form_in`-matches any required unit's form (here: a gold agent or patient
     role term from `roles_v1.json`, a gold name, or the gold action), over the `reads=full`
     all-layer digests of gpu R4, **pooled over the three required arms** (s3d-rl600, jlens,
     mlnla-rl2-2000), all 100 items and all 11 layers (no new LLM call, no GPU);
  2. candidates: `final_token` (k=1), the ≤ 3 k with the highest pooled share, and
     `offset_from_end k=4` (`\n` after `assistant`);
  3. the highest-share candidate replaces `final_token` only if its share exceeds
     `final_token`'s by more than 10 points absolute; the headline pass rate is never consulted;
  4. reported, never used to choose: the per-arm share table (s3d / jlens / mlnla + pooled) and
     each candidate's `reads=lite` headline per arm (free re-judges of the same readouts);
  5. the chosen rule is frozen into the readplan row (lite fields are popped from `bank_sha` and
     `plan_sha`, so no re-read and no ATI change).
- Round-0 indication, kept only as motivation and NOT an input to the choice (oa-v1, lenient,
  cached native judgements; items passing at that single site at any layer — a pass rate, which
  the r3 procedure forbids as a criterion):

  | arm | `\n` after `assistant` | final token |
  |---|---|---|
  | s3d | 75 | 66 |
  | rl-onchat-x4 | 82 | 69 |
  | ML-NLA | 54 | 43 |

  The `.` of the suffix is second (73 / 78 / 50); the special tokens read at about 0.
- Lite selection is done only by `reads.select` inside `reads.load`; the family filters nothing.
  Adapted subjects (`WSB_BANK_ROOT`): if the procedure picks `offset_from_end k=4`, readplan
  writes `final_token` on adapted-bank rows unless the adapted bank header's readout block
  carries a `lite` source key (the offset is Qwen-template-specific).
- Tests: infra's `test_every_plan_row_has_lite_positions`, `test_every_lite_rule_is_cell_resolvable`,
  `test_lite_is_subset_of_full`, `test_reads_lite_stamps_prompt_version` (parametrized). Family
  test `test_reads_lite_keeps_one_site_per_layer`.

C3.4 **D3 layers.**
- `SIX` becomes `readplan.GRID` (11 layers, 20..60 step 4) at `readplan.py:476`, through infra §2.1.
- The judge takes `layers=all|each|<csv>`; `each` writes `out/role_bound_association/all/` and
  `/L<k>/`. A requested layer missing from the file exits 2 inside `reads.load`
  (`allow_missing` → `complete=False`); an explicit `layers=` list is complete when every
  requested layer is present.
- `score.py` `sites_per_item` / `any_of_grid_floor` stay native-only diagnostics.
- `__init__.py:21` `calls_per_arm` becomes "≈ 200 (summary: 100 digests + 100 judge calls);
  ≈ 20.9k native".
- Tests: infra's `test_layers_arbitrary` and `test_layers_variant_is_complete` (parametrized over
  `registry.FAMILIES`).

C3.5 **D4.** CANNOT (`mc.CANNOT`) is last in all three MCs through `mc.options_with_cannot`
(C2.2). A CANNOT pick is never gold. Covered by the shared cannot-tell tests (C2.2).

C3.6 **D5.**
- `SYSTEM` (C1.2) opens with `mc.READOUT_PHRASE`; "interpretability lens" is gone.
- The legacy `INTERP_SYSTEM` quote block in the README (`:168-175`) is deleted along with interp-v1.
- `EvalSpec.task_note` (C1.5) is neutral and gold-free.
- Tests: shared `test_no_tool_names_in_prompts` and
  `test_every_summary_family_has_task_note_without_gold`.

C3.7 **D6 / Q4.**
- Rule 4 is the Q4 combining rule: tokens of one list combine for meaning; adjacent positions of
  one layer only to spell one word; nothing relational from different samples, positions, layers
  or bullets of one generation (`digest.statement_lines`). No rank-1 exception.
- Flat lists follow the r2 options-relative rule (infra §2.7.2): a JUDGE decision relative to the
  options shown. A token list holding two or more of the MC's options ("mother | father |
  teacher | nurse" when both a `parent` and a `teacher` option are listed) singles out none of
  them; an option alone on its list is singled out. The summarizer records such lists as lists
  and never picks or drops. role_bound declares `EvalSpec.flat_types = ()` (roles are not a
  competitor run beyond the options shown; the near-role distractors of C2.2 put the confusable
  roles on the menu, which is what makes a "parent | grandparent" list single out neither).
- Tests: the flat-list rule is an LLM decision, so it is held by prompt text, not by a scripted
  verdict: `test_system_rules_present` (C1.2) also asserts rule 4's flat-list sentence and that
  the native token note equals `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`
  (== `mc.token_note()` for this family); the shared
  `test_mc.py::test_two_options_in_one_list_single_out_none` and
  `::test_lone_option_in_same_category_list_is_singled_out` cover the shared text. E3/E10 show
  the behaviour on real readouts.
- The family adds no summarizer of its own and no token-quote verifier (C1.4 uses
  `digest.quote_ok`, `" | "` joiner).

C3.8 **D7 / Q1.** Sampling is declared by the producer in the sidecar and applied by
`readouts.normalize` inside `reads.load` (C1.1): s3d-rl600 and NLA `prose1` (1 sample per
activation), `*-x4` `bullet4` (4 separate samples), token lenses `tokens10`. The family never
infers sampling from bullet shape. The statement rule (C1.4 a′) applies identically to all
prose kinds.

C3.9 **D8 prompt-only (`po-opus-v1`).**
- One Opus 5.5 readout per plan row id (100), via `wsbench baseline kind=prompt_only_opus`, one
  prose cell at the last full-read site, layer 44, sidecar `reader: prompt_only:claude-opus-5-5`.
- Judged by `wsbench run all=True readouts_root=<dir>/readouts` with no `layers=` / `reads=`, so
  it gets the same digest, task note, SYSTEM, v2 option lists and gate (a, a′, b). The
  `prompt_only:*` reader waives `check_full` and the story-echo guard (C1.6).
- Measured at gpu R6, after R4c closes, on the final oa-v2 (or later) PV; a PV change after R6
  means no floor until R6 re-runs for this family (SHARED_API "Prompt-only" timing r3).
- Frozen into `evals/baselines/prompt_only_summary.json` by the run phase, matched by
  `summary_floor_applies` on `strip_reads(prompt_version)`. The entry carries `saturated: true`
  (the stimulus states who did what to whom; about 1.0 is expected); the `SATURATED` /
  `EXCLUDED` handling is infra §2.11.9's, not edited here. It is a fairness flag, not a bar.
- The floor is role_bound's own headline from that run (all three MCs gold AND gate a, a′, b),
  family CI, n = judged − refused; if > 20% of the 100 readouts are refused the entry is
  `not_measurable` (SHARED_API "Prompt-only").

C3.10 **Score extras** (`score.py:73-92`) add:
- `n_gate_rejected` and its sub-counts (C1.4), including the shared `n_unverified_bullet`;
- `n_reversed`: Q1 = gold patient and Q3 = gold agent with Q2 gold, i.e. right relation, wrong
  direction;
- `incongruent_pass_rate`, shown beside the headline (audit request);
- native rows (and the ATI instrument): `mcjudge.layer_pick_columns(rows)` (critique 18), printed
  on the site beside every native / ATI number;
- the shared `config` stamps (`reads`, `sampling`, `sampling_source`, `reader`,
  `layers_judged`) come from `mcjudge.base_config`; `extras.digest_served_by` from the digest.

`by_stereotypicality` stays. Chance stays (1/6)^3: still 6 options per MC.

Tests: `test_reversed_counted`; `test_native_extras_have_layer_pick_columns`.

C3.11 **Lucky guessing.** `lucky_guessing.py:146` switches to `build_block_v2` (it keeps dropping
the escape, infra §2.4.6) and reads the bank through `registry.bank_path`. The v2 lists are
harder (near-role distractors, distinct names), so the floor is re-measured by the baselines
workstream (API, later phase). The Gemini-era `lucky-2026-09-16` entry stays as history.

C3.12 **Judge and summarizer for the 12-config run.** role_bound is unpinned: Opus 5.5 summarizer
(task variant) and Opus 5.5 judge on s3d-rl600, all 11 layers and each single layer
(`layers=each`). No Opus-judge column is needed. Fallback-served digests are reported in
`extras.digest_served_by`.

C3.13 **ATI.** The bank and full positions are unchanged, and `_row_dict` pops `layers` (today,
`text_inversion.py:990`) and the lite fields (infra §2.6.9), so `bank_sha` is unchanged:
role_bound belongs in infra's `test_bank_sha_unchanged_for_untouched_families`. The instrument
changes (oa-v2) while the item render and question prompt (`prompt_sha`) do not, so under the
gpu G13 r3 rule (`scripts/ati_regate_table.py`) this family gets a **re-judge only** (no new panel
answers), natively as today, at gpu R8 — after R4c closes, on the final instrument (G9
`audit_run.py` asserts native PV == ATI instrument). If the script's table disagrees, this spec
wins and the disagreement is printed on the site. Membership is otherwise untouched (Camila gave
no ATI instruction here); it stays out of the ATI macro (9 < 20).

C3.14 **Macro.** `metric="pass_rate"` (in `results.MACRO_METRICS`) and `EvalSpec.not_in_macro =
""` (empty = in; never `None`). No change from today; asserted by the family test
`test_role_bound_association.py::test_in_macro` (runs the real `results.macro` on a scripted
result and asserts role_bound is included).

## 3. Data needs

- **Bank:** no edit. `items.json` stays live and untouched, so no new bank version.
- **New instrument data:** `evals/role_bound_association/roles_v1.json`: 95 roles, each with
  terms (CJK forms listed) and near roles. Drafted with Opus 5.5 through the ant CLI, then
  reviewed by hand and checked by the C2.4 tests.
- **New items:** none. **Qwen gating: not needed.** The stimuli and render are unchanged.
- **Readouts to regenerate (GPU on Modal, gpu workstream):** the campaign arm s3d-rl600
  (sidecar `sampling: prose1`) at `reads=full`: the 19 suffix + tail positions × GRID (11 layers)
  for all 100 items = 20,900 cells (matches gpu §3.3's row). **Required r2 arms on the same
  full plan** (SHARED_API "Producer / run"; role_bound is in `FAMILIES_BP`): `jlens` (sidecar
  `sampling: tokens10`) and `mlnla-rl2-2000` (`prose1`), all-layer config, full + lite, 20,900
  cells each. Every other arm (`*-x4` `bullet4`, logit, tuned, R-lens, template) is **"cached v1
  readouts, judge test only"**: its cached files hold only `SIX` at the unchanged render, so they
  are judged under oa-v2 on those 6 layers, labelled as such on the site, and never enter a
  12-config row.
  - The cached s3d / J-lens / ML-NLA files are likewise "cached v1 readouts, judge test only";
    the new full-plan files with declared sidecars are the numbers of record.
  - Lite needs no separate generation: it is a `reads.select` subset of full.
- **Prompt-only readouts:** 100 Opus readouts from the stimulus alone (`po-opus-v1`, C3.9).
- **ATI:** re-gated under oa-v2 (C3.13).

## 4. Answers

Camila asks no question in this section. Each "make sure" is answered with what the cached
evidence shows today.

**A1. Is content pieced together today? Yes, in both modes.**
- Summary mode (`/workspace/root/wsb-summ-out/d3/d3b-s3d-all-summary-v2`, Opus judge, 0.72): in
  21 of the 72 passing items, the judge's own evidence says it combined or inferred across lines
  ("separate", "across samples", "putting these together", "inference").
  - `oa-mother-son-angry-ba`: "This is an inference across separate samples rather than one
    explicit statement".
  - `oa-bouncer-patron-eject-ba`: "no single li[ne]…".
  - `oa-librarian-borrower-fine-ab`: "no single line states Marguerite fined Dev".
- Native mode (`d3b-s3d-all-native`, 0.93): one s3d cell = one generation listing ~4 separate
  concept bullets, and the judge combines bullets into a relation no bullet states.
  - `oa-burglar-neighbor-spy-ba` L44 pos142: no bullet has a neighbour watching a burglar, yet
    it was judged PASS.
  - `oa-child-grandparent-hug-ab` L60 pos136: "Mia runs up the stairs to find Grandfather" plus
    "hugs her mother" (two bullets) → PASS.
- For `*-x4` arms the same native call sees 4 separate generations at once (cross-sample
  stitching in the strict sense).
- The README endorses cross-site pooling (`README.md:201-203`), which contradicts the shared
  SUMMARY_NOTE.
- Feasibility of the fix: a crude lexical proxy found that 73 of the 93 native-passing s3d items
  have a single bullet naming both people inside a passing cell, and 89/100 have one somewhere in
  the grid. A strong O-lens can therefore still pass under the statement rule. The drop is
  bounded by about 20 items for s3d before the action and direction checks.

**A2. Do close words pass today? Yes.** There is no near-role option to choose instead, and the
judge picks "the closest listed option".
- `oa-teacher-parent-blame-ab` L36 pos146 (native s3d, PASS). The readout says "A social worker
  confronts a student's mother …". The judge wrote: "The agent is called a 'social worker', not a
  teacher, but the school context makes Margaret, the teacher, the closest listed option."
- `oa-child-grandparent-hug-ab` L60 pos136 (PASS). The hugs in that cell are with "her mother".
  The judge: "one line points to Grandfather, the others to 'her mother'. Of the listed options,
  'grandparent' fits best."
- The exact "grandparent" → "parent" example in the audit artifact is from
  `relational_multihop` (`/workspace/root/wsb-audit-artifact/families/relational_multihop.json`).
  The role-bound bank has the same hazard, in both directions: `parent` in
  `oa-teacher-parent-blame-*`, and `grandparent` / `grandmother` / `mother` in the hug, indulge
  and angry pairs. C2 closes both directions.

**A3. Are there option-list bugs that make the judge too strict or ambiguous? Yes.**
- `oa-doctor-nurse-instruct-ab` lists its gold patient twice, so the second copy is scored
  wrong. This latent bug was not observed to flip a cached verdict.
- 57/100 lists have 4-letter name collisions. C2.2 fixes both.

**A4. (General Q, family part) How are role-bound prompt-only baselines judged?**
- Today: Gemini 3.8 Flash, instrument oa-v1, per cell (13,460 cells), not through the digest.
  The rate is 1.00, `complete=false`.
- After D8 (`po-opus-v1`): one Opus readout per id goes through the same digest, v2 lists, SYSTEM
  and gate. The rate is expected to stay about 1.0, because the text states the relation; the
  entry is `saturated: true`.

**Decisions taken (this spec; site section 4, "override if you disagree").**
- D-a: the unit for a relation is one top-level bullet of a prose sample (shared infra §2.7.9
  rule), shown as one `⁞`-delimited part of a digest line.
- D-b: action and direction stay with the LLM judge; only the quote, the one-bullet rule and the
  agent / patient references are gated mechanically (bank actions have near-synonyms).
- D-c: near-action distractors are not added (they would often be a second correct answer);
  near-role distractors are.
- D-d: a token list cannot give Q1 / Q3 unless a token states the direction (token lenses go to
  about 0 by design).
- D-e: `roles_v1.json` is instrument data stamped `config.roles_lexicon`, not a new bank version
  (`bank_sha` and ATI items unchanged; ATI re-judge only).
- D-f: `flat_types=()`, `multi_select=False`; the prompt-only floor is shown with
  `saturated: true` as a fairness flag, not a bar.

## 5. Evidence plan (website artefacts)

| # | Item | Artefact | Before | After (expected) |
|---|---|---|---|---|
| E1 | C1 stitching, summary | Re-digest and re-judge `oa-mother-son-angry-ba`, `oa-starter-benchwarmer-pity-ba`, `oa-burglar-neighbor-spy-ba`, `oa-bouncer-patron-eject-ba`, `oa-librarian-borrower-fine-ab` on the new full-plan s3d-rl600 (prose1) readouts | PASS (d3b summary-v2, stitch language in evidence) | FAIL, or PASS with a verified one-statement quote shown |
| E2 | C1 stitching, native | Re-judge cells `oa-burglar-neighbor-spy-ba` L44 p142 and `oa-child-grandparent-hug-ab` L60 p136 (d3b native readouts, `opts=aggregate=native`; cached v1 readouts, judge test only) | PASS | FAIL (`n_unverified_bullet` / `n_gate_rejected`, or CANNOT) |
| E3 | C2 close words | Re-judge `oa-teacher-parent-blame-ab` L36 p146 ("social worker") and `oa-child-grandparent-hug-ab` L60 p136 ("her mother") with v2 lists, where a "grandparent" or "parent" distractor is present (cached v1 readouts, judge test only) | PASS | FAIL |
| E4 | C1/C2 deterministic | Output of the gate unit tests: cross-bullet quote in one prose1 generation; "the teacher blamed the grandmother" vs gold parent; "hugged her mother" vs gold grandparent | n/a | gate rejects; shown verbatim |
| E5 | Too-strict audit cases | `oa-babysitter-toddler-feed-ba` L36 p136 ("young girl unwittingly feeds her babysitter") and `oa-coach-athlete-admire-ab` (summary; "Coach Marcus … his star swimmer … quiet pride"; cached v1 readouts, judge test only) | FAIL | PASS with a one-statement quote |
| E6 | J-lens interp removed | `oa-referee-player-warn-ab` L60, `oa-pilot-passenger-reassure-ab` L44 (cached macro/jlens cells, judge test only), then the same items on the required new `jlens` full-plan file | PASS via interp-v1 prose | FAIL (raw tokens, rule 4) |
| E7 | Lite site | `scripts/lite_site_table.py` output for role_bound: per-arm (s3d-rl600 / jlens / mlnla-rl2-2000) and pooled support share per k, the ≤ 5 candidates (`final_token`, top-3 k, `offset_from_end k=4`), the frozen rule, and each candidate's lite headline per arm (reported, not used) | oa-v1 pass-rate indication in §C3.3 | support-share table; frozen rule; lite vs full headline |
| E8 | Option bugs | v1 vs v2 people lists for `oa-doctor-nurse-instruct-ab` and `oa-child-grandparent-hug-ab` | duplicate "Priya, the nurse"; no near role | distinct labels; near-role distractor; CANNOT last |
| E9 | Headline | Per config (s3d-rl600 all 11 layers, each single layer via `layers=each`), plus the required `mlnla-rl2-2000` and `jlens` all-layer full + lite runs and the `po-opus-v1` floor: oa-v1 vs oa-v2 pass rate, incongruent rate, `n_gate_rejected` (+ sub-counts), `n_reversed`, `digest_served_by` | 0.72 summary / 0.93 native (s3d) | new numbers |
| E10 | Leniency audit | The shared gpu G12 / R4b table (`scripts/audit_verdicts.py sample` → fresh-context auditor → `table`): ≥ 30 stratified verdicts (pass/fail × s3d-rl600 or ML-NLA prose / J-lens token) plus up to 5 `n_unverified_bullet` picks; no `--strata` entry (role_bound has no control kind); Opus 5.5 summarizer + judge; this spec supplies the auditor's pass rule (C1: one statement — one ⁞-delimited bullet — names agent, action, patient and direction; exact roles per C2). Not a second protocol | audit: 9 lenient, 2 strict of 58 | role_bound's row: `n_too_lenient` target 0, every `too_strict` case verbatim. If flagged (≥ 3), gpu **R4c**: fix PR with a new PV (`oa-v3`; `roles_v1.json` edits bump `config.roles_lexicon`), R4 re-run for this family (12 configs, jlens + mlnla full + lite), R4b re-run, ≤ 2 rounds, before R6 / R8 and the site build; leftovers → site "New errors found" |
| E12 | Voided cross-bullet picks | `extras.n_unverified_bullet` per config/arm from G9 `audit_run.py`, with 5 verbatim examples (digest line with `⁞`, quote) | n/a (boundaries invisible) | count + examples |
| E11 | Native ATI columns | `mcjudge.layer_pick_columns` beside the native s3d rate and the re-gated 9-item ATI entry | n/a | shown |

E1–E3, E5, E6 and E9–E12 need judge calls, and E1 also digest calls (API, run phase). E7's share
table reuses the R4 digests (no new call; its per-candidate lite headlines are re-judges). E4 and
E8 are CPU only.

## 6. Risks / conflicts

1. **Statement rule: resolved in round 2 (critique r1 item 2).** infra §2.7.9 / §2.9.4 now make
   one top-level bullet the unit for relational content for every relational family and lift this
   family's round-1 splitter into `digest.statement_lines`. No conflict remains. Dependency: if
   infra's `digest.statement_lines` slips, this family does NOT build a local copy; (a′) waits
   for it (the infra PR lands first).
2. **Too strict.** Gate (b) fails statements that use only pronouns ("she fed him") or invented
   names with no role word. This is intended ("the roles and action in the same readout"), but it
   can cost true relational readouts. E10 must list every strict fail. If more than a few appear,
   widen `terms` (scene hyponyms), never the rule.
3. **Lexicon curation errors** are the main new failure surface. C2.4 tests guard overlap, not
   completeness. A missing synonym makes the gate too strict, which E10 catches.
4. **Token lenses go to about 0 by design** (rule 4). The J-lens was at 0.13 and its passes were
   stereotype fills. Show it on the website as "no direction in a token bag", not as a regression.
5. **Infra dependencies (the infra PR lands first):** `reads.load` / `check_full` / `select`
   (§2.0, §2.6), GRID and `layers=` (§2.1), interp-v1 removal (§2.3), `mc.options_with_cannot`
   (§2.4), `digest.quote_ok` / `digest.statement_lines` / `digest.BULLET_MARK` / `fold_quote`'s
   `⁞` mapping / `Line.layer|pos|bullet` / `mc.form_in` / `mc.token_note(flat_types, *,
   multi_select)` (§2.7), `scripts/lite_site_table.py` (§2.6), task variant and
   `EvalSpec.task_note` (§2.8), sidecar sampling (§2.9), `po-opus-v1` (§2.11). No local
   stand-ins are built.
5b. **ATI re-judge vs gpu G13 (open, gpu-owned).** gpu.md G13's row "families with unchanged
   `bank_sha` → nothing" and R8's `J=` list do not name role_bound_association, yet its
   instrument moves oa-v1 → oa-v2, and G9 `audit_run.py` asserts native PV == ATI instrument.
   gpu must add role_bound to R8 `J` (or key `ati_regate_table.py` on instrument); until then
   C3.13 stands and the disagreement is printed on the site.
6. **PR #75 (tiers):** not rebased here; `reads=lite` is independent of `tier=` (decision). No
   family change.
7. **Adapted subjects** (`WSB_BANK_ROOT`): the lite offset candidate is template-specific, so
   adapted rows use `final_token` (C3.3); `min_full_positions=19` is the Qwen tail length, so an
   adapted subject with a shorter chat tail runs with `allow_missing` (partial) until its bank
   header is measured. Authored roles may be missing from the lexicon; the lint flag is in C2.5.
8. **Pre-existing tests touched:**
   - `tests/test_role_bound_association.py::test_rendered_prompt_matches_golden`: rename and drop
     the PV/schema asserts (sanctioned, C3.1);
   - `::test_run_verdicts_and_numbers`: quote, v2 golds, `native_args` (sanctioned, C3.1);
   - `::test_tokens_kind_routes_through_summarizer`: deleted (sanctioned by infra §2.3, C1.7).
   - `::test_blocks_match_source_golden` and the golden files are NOT changed.
9. **Shared files this workstream touches:**
   - `src/wsbench/readplan.py` (`:468-481`: `lite_positions` / `lite_layers` on the role_bound row;
     the GRID swap is done by infra; the branch is shared with conjunctive, whose spec also sets
     `final_token`);
   - `src/wsbench/baselines/lucky_guessing.py:146` (builder v2);
   - `src/wsbench/adapt/lint.py:261` (lexicon lint);
   - `evals/baselines/prompt_only_summary.json`, `lucky_guessing.json` and
     `anti_text_inversion.json` (re-frozen by the run / baselines workstreams, not hand-edited);
   - `docs/read_sites.md` (lite site, 11 layers, the single-statement rule);
   - `README.md:254` and `:409` (oa-v2 row);
   - `atlas/build.py:55`: the description "An emotion bound to a specific person in a scene." is
     wrong. Change it to "Who did what to whom in a two-person scene." Optional and cosmetic.

   Family-local files: `src/wsbench/evals/role_bound_association/{__init__,judge,prompts,score}.py`
   (`__init__` gains `task_note`, `min_full_positions=19`, `full_contiguous=True`), the new
   `gate.py`, the new `evals/role_bound_association/roles_v1.json`,
   `evals/role_bound_association/README.md`, `tests/test_role_bound_association.py`, the new
   `tests/test_role_bound_gate.py` and `tests/test_role_bound_lexicon.py`, and the new goldens
   `tests/golden/role_bound_association_{options_v2.json,prompt_v2.txt}`.

## 7. Coverage map (Camila's sentences → change → test → evidence)

Rows of this table are this spec's `site/manifest.json` rows (gpu G11); `sentence_id` =
`role_bound_association:<line in notes/feedback.md>` (Camila's section is lines 184-185). Each row
is `pending` until its named tests are green at the bench SHA and its evidence artefact exists.

| sentence_id | Camila's sentence | Change | Test(s) | Evidence |
|---|---|---|---|---|
| `role_bound_association:184` | "Make sure the judge is not too lenient" | C1.2 rules 1-5, C1.3 quote, C1.4 gate, C2.2 v2 lists; G12 audit + R4c loop (E10) | `test_system_rules_present`, `test_gold_choices_with_bad_quote_is_fail_and_counted`, shared `test_token_note_rendered_from_spec` | E9, E10 |
| `role_bound_association:184` | "i agree with the examples you showed" | the audit's examples are the regression set | `test_stitched_quote_rejected`, `test_cross_bullet_quote_in_one_prose1_generation_rejected` | E1, E2, E3, E6 |
| `role_bound_association:184` | "the content from different samples should not be artificially pieced together" | C1.1 declared sampling (bullet4 = 4 samples), C1.2 rule 1, C1.4 (a) via `digest.quote_ok`, C1.5 per-statement binding, README pooling text deleted | `test_bullet4_judged_as_four_samples`, `test_stitched_quote_rejected`, `test_summary_mode_requires_single_statement_binding` | E1, E2 |
| `role_bound_association:184` | "we are looking for true relational content" | C1.2 rules 3-4 (exact action, direction from the statement; token bags carry no direction), C1.4 (a′) statement rule on `⁞`-visible bullets, C1.6 story-echo guard, C3.10 `n_reversed` | `test_tokens_native_judges_raw_list`, `test_story_positions_rejected`, `test_reversed_counted` | E6, E9 |
| `role_bound_association:184` | "we should require the roles and action to be in the same readout" | C1.2 rule 1 (all three answers from ONE statement), C1.4 (a′) via shared `digest.statement_lines` + (b) | `test_cross_bullet_quote_in_one_prose1_generation_rejected`, `test_quote_inside_one_bullet_passes`, shared `test_relation_across_two_bullets_fails`, `test_digest_line_shows_bullet_boundaries` | E2, E4, E5, E12 |
| `role_bound_association:185` | "make sure that the lens is not letting close words pass by like "parent" being chosen when the lens mistakenly says "grandparent"" | C2.1 lexicon, C2.2 near-role distractors, C1.2 rule 2, C1.4 (b) word-bounded `mc.form_in` | `test_grandmother_is_not_parent`, `test_mother_is_not_grandparent`, `test_v2_near_role_present`, `test_near_roles_disjoint_from_terms` | E3, E4, E8 |

## 8. Implementation notes (PR, 2026-10-30)

Rebased on origin/main 34005ac (plan 0032 infra merged). The late campaign fixes that touch this
family were already in that infra: `reads.plan_sha` does not hash layers
(`tests/test_reads.py::test_all_layer_producer_file_is_judged`) and gpu R4d is
`scripts/lite_site_table.py` + `config.lite_rule` + `scripts/audit_run.py`'s frozen-rule check,
with role_bound in `readplan.LITE_SITE_FAMILIES`. Nothing family-local was needed for them.

- **Lexicon:** 93 bank roles (the spec's "95" was a miscount). Opus 5.5 draft
  (`scripts/author_roles_lexicon.py`, one call; raw draft kept at
  `/workspace/root/wsb-bp/evidence/role_bound_data/roles_opus_draft.json`), then hand edits:
  toddler and child take the spec's child / kid / girl / boy forms (their `near` lists drop
  each other), grandparent gains 祖母 / 祖父 / 姥姥 / 姥爷, parent gains mum / mommy / daddy /
  妈妈 / 爸爸, teacher's near gains social worker, doctor's near drops "surgeon-in-training"
  (it contains the doctor term "surgeon") for pharmacist, son gains stepson, player drops
  "forward" (a common word), guard / police officer near follow the spec; "夜店保安" (contains
  security guard's 保安) and "baby-sitter" (contains toddler's "baby" under `mc.form_in`) are
  dropped (the gate dehyphenates, so "baby-sitter" still names a babysitter). No
  great-grandparent near *option*: its spaced form "great grandmother" contains grandparent's
  term "grandmother" as a word, so it would break the option term-disjointness tests, and
  grandparent's first near entries (parent, uncle, aunt) fill the menu slot anyway. It is
  covered by the gate instead (see the review-fix bullet below).
- **Near-role order:** the builder takes `near` entries in lexicon order (most-confusable
  first), not a seeded shuffle, so that `test_v2_near_role_present` (teacher-parent lists hold a
  grandparent) is a property of the lexicon, not of a seed. Names are still seeded.
- **Gate (b) adds two reject-only rules** on top of `mc.form_in` (add, never relax): every term
  of a DIFFERENT lexicon / near role is masked (longest first) before matching, so "security
  guard" never names a gold "guard"; and hyphenated compounds are one word on both sides, so
  "step-mother" / "mother-in-law" never name a gold "mother".
- **Review fix (PR #174): mask-only `block` forms.** Dehyphenation covered only the hyphenated
  and closed spellings; the spaced and CJK ones still named the gold role
  (`role_ref('her great grandmother', 'grandparent')`, 曾祖母 / 曾祖父 for grandparent,
  "step mother" / "foster mother" for parent were all True), because masking blocks only
  listed terms. `roles_v1.json` gains a top-level `block` map (keyed by the role it names:
  great-grandparent, step-grandparent, stepparent, foster parent, godparent, parent-in-law,
  stepchild, foster child, godchild, child-in-law, great-grandchild, step-/half-/foster
  sibling, sibling-in-law, the spaced "grand mother"-style forms, cousin's 表兄弟 / 堂姐妹,
  ex-spouse, 老太太). Its terms are masked for every role and are words no name variant may
  be; they are never options or role terms, so the v2 menus, the golden prompt and the
  disjointness tests are unchanged. Reject-only (add, never relax). The file is unreleased,
  so its version stays `roles-v1`. Tests: `test_spaced_and_cjk_near_kin_never_name_role`,
  `test_block_forms_leave_own_terms_alone`, `test_block_words_are_not_name_variants`,
  `test_block_terms_mask_only`. Not blocked (judged the same person or not a kin confusion):
  "birth mother", "den mother", "founding father".
- **Shared changes:** `readplan._adapted_offset` (C3.3: an adapted bank reads `final_token`
  when the frozen rule is an offset and its header has no `readout.lite` key);
  `baselines/lucky_guessing.py` builds the v2 lists (C3.11); `adapt/lint.py` flags an
  unlexiconed authored role (C2.5).
- **Tests outside the family whose fixtures changed (no assertion changed):**
  `test_summary_mode_assoc3.py::_role_judge` builds the v2 block and returns a quote;
  `test_summary_mode_compare.py::_RandomLLM._gen` returns a whole-fragment `quote` half the
  time (a random 1-3 word quote can never name both people, so the existing "native passes
  seen" assertion for role_bound needs it); `test_prompt_tool_names.PENDING_FAMILY_PR` drops
  role_bound (its prompts are now tool-name-free; the list is shrink-only by design).

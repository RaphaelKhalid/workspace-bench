# 0047 — WorkspaceBench fix campaign: brew_intermediates stays retired ("brew" workstream)

Status: implemented in this PR (camila/wsb-bp-brew), on top of plan 0032 (infra, #140). Campaign
source of truth: `/workspace/root/wsb-bp/plans/{brew,SHARED_API,_fable_decisions}.md`; this file
copies the brew spec verbatim (below the line) plus what the implementation found.

## Implementation notes (2026-10-30)

- **Report filter (item 2).** `results.markdown_table(..., removed=None)` skips the score row of
  every family in `registry.REMOVED_FAMILIES`; the "Not in macro:" line is unchanged.
  `wsbench report json=True` drops them from `families` (they stay in `macro.excluded`, reason
  `removed`), and `report by_layer=True` drops their rows too (not in the spec; same rule).
  On the cached `rl-onchat-x4` run only two lines change: the `brew_intermediates` (0.905, no
  floor) and `ttt_move` rows disappear; the macro row is byte-identical.
- **Skill scrub (item 4b).** The infra PR (#140) created `.claude/skills/wsb-new-questions/`
  from #69 with its brew content intact (55 lines), so the guard failed on `origin/main`
  (`34005ac`) with 66 hits: those 55 plus the 11 `adapted/*/report.json` rule strings. This PR
  removes the brew generator, gate stamping, lint branches and doc sections from the skill
  (also `validate_bank.py` and `wave_report.py`, which the spec's list did not name), and the
  same scrub is pushed onto the #69 branch.
- **report.json (item 4c).** 11 files, one line each; every file round-trips byte-identically
  through `json.dumps(indent=1, ensure_ascii=False) + "\n"`.
- **Guard (item 4a).** `tests/test_legacy_family_names.py::test_brew_has_no_live_references`
  (scan of `git ls-files`, every tracked root, data JSON under `evals/ adapted/ examples/`
  excluded except `adapted/*/report.json`) and `::test_brew_guard_regex`.
- **Late critique fixes (1)-(5) of the campaign** do not touch brew: (1) and (2) are infra's
  (`reads.plan_sha` without layers, R4d), (3) and (4) belong to the multilingual and
  basic_readout PRs, (5) to the run phase. brew has no plan row, no lite rule, no ATI entry and
  no judge prompt.
- `wsbench plan families=brew_intermediates` (full or `reads=lite`) exits 2 with
  "unknown families ['brew_intermediates']": the correct read plan for a retired family is none.

---

# Workstream: brew_intermediates (retired) — spec

Camila (feedback.md:135-139):
> Positions should be read at the last entire sentence: "What colour is the potion at the end?"
> The rule also passes an item whenever the lens names no wrong colour, so a readout that says
> nothing about colours can pass. Show the score next to the baseline, or report score minus
> baseline. Right now the report shows no floor at all.
> This should not be the case, we should require the correct color to be shown by the readout/summary
> We should retire this eval from the public workspacebench

Bottom line: the family is already retired on `origin/main` (plan 0029, PR #131, merged
2026-10-29T21:59Z, commit `7d73944`). Nothing in it needs fixing. What is left is two places
where brew still shows up, plus a guard against it coming back:
(a) `wsbench report` on an old run dir still prints a brew score row with no floor (`—`), which
is exactly the "report shows no floor at all" complaint; (b) open PR #69 (the agent skill) adds
brew generation and gating back. Everything else is dated history.

Code of record: `/root/wsb-bp-base` @ `cd6b0fa`.

Round 1 alignment (2026-10-30). Shared names follow `SHARED_API.md`. This family calls none of
the shared machinery: there is no brew `reads.load` call, `ReadSpec`, `lite_positions`, bank
file, `task_note`, MC judge or digest, and none is added. The parametrized infra tests run over
`registry.FAMILIES`, so they never reach brew. No `_critique.md` item names brew. The binding
decisions in `_fable_decisions.md` that touch this spec are: **PR #69 skill** (the skill files
are created in the infra PR, with a follow-up commit onto #69 if it is still open; item 4b
follows this), **ATI** ("families Camila removes from ATI are removed": brew already has no ATI
key), and **Q1/D7 sampling**, **lite mode** and **versioned banks**, which are moot because there
is no brew code left. This PR lands after infra and rebases onto it, because both edit
`results.py` and `cli.py` (§6).

Round 2 alignment (2026-10-30). Re-checked against the round-2 SHARED_API.md: brew uses none of
the retired names (old or r2: no `mt_family`, `summ_*`, `digest.statement_lines`, prompt-only
protocol, sampling kind). Still no `_critique_r1.md` item names brew. Two r1 items touch it
indirectly and are applied: **r1-7** (the G12/R4b leniency audit runs over `FAMILIES_BP`; brew is
not in it, so brew gets no audit row, and none is needed because no brew verdict is produced),
and **r1-8** (every brew number in §4.3 is labelled "cached v1 verdicts, no new judging"; no arm
is produced for brew). One self-found defect is fixed: the round-1 guard regex `\bbrew\b` hit
ordinary words in model responses (`adapted/{olmo-3-7b,olmo-3.1-32b,qwen3.5-0.8b}/hallucination.json`:
"morning brew", "Golden brew") and a retired-note comment in `tests/test_text_inversion.py:193`,
so the claimed "fails exactly on the 11 report.json strings" before-state was false. Item 4a
now scans code/docs only (data JSON excluded), allowlists `tests/test_text_inversion.py`, and
adds a path check. Verified on `cd6b0fa` (see 4a).

Round 3 alignment (2026-10-30). Re-checked against the round-3 SHARED_API.md: brew uses none
of the round-3 retired names (`not_in_macro=None`, `number_flood` on a bullet, lite site by pass
rate, R4 jailbreak smoke, HB `reads.sh`, `WSB_BANK_FILE_*` in the producer image) and none of the
new machinery (`BULLET_MARK`, `statement_lines`, `token_note`, `MACRO_METRICS`, `plan_sha_rows`,
`lite_site_table.py`). No `_critique_r2.md` item names brew. Four r2 items touch it indirectly and
are applied:
- **r2-5 (site, gpu G11):** the coverage map below is now written in the G11 manifest shape
  (`sentence_id` = `brew:<feedback.md line>`, status from the G11 enum), every evidence item in
  §5 has a fixed artefact path under `site/evidence/brew/`, and §4.5 lists brew's "Decisions
  taken" bullets for site section 4. Brew contributes nothing to "New errors found" (no brew
  verdicts, audits or floors are produced); §5 E7 states that explicitly so the section is not
  silently empty.
- **r2-1 (infra §2.17 `MACRO_METRICS`):** no conflict. In `results.macro` the `removed` check
  (`results.py:256-257`) precedes the metric clause infra rewrites (`:268`), so a stale brew
  result keeps reason `"removed"`; `test_report_json_omits_removed_families` asserts exactly
  that and runs on top of infra's change. The item-2 filter lives in `markdown_table` /
  `ReportRuns`, which §2.17 does not touch.
- **r2-6 (R4c fix loop):** brew is not in `FAMILIES_BP`, so it has no R4b flag and no R4c rerun;
  its §4.3 numbers are cached and never depend on a PV, so R4c cannot invalidate them.
- **r2-12 (`digest.BULLET_MARK`):** moot for brew (no digest). The guard regex 4a does not match
  `⁞`, and no shared file infra/gpu add needs to name brew (gpu's `FAMILIES_BP` is computed from
  the registry, not a literal list; see §6 for the allowlist rule that keeps sibling specs'
  removal docs from tripping the guard).

### Coverage map (every sentence of feedback.md:135-139) = brew rows of `site/manifest.json`
Line 135 ("Brew intermediates") is the section heading, not a sentence. Paths in "evidence" are
relative to `/workspace/root/wsb-bp/site/`.

| sentence_id | Camila's sentence | change_id: concrete change | tests | evidence | status |
|---|---|---|---|---|---|
| `brew:136` | "Positions should be read at the last entire sentence…" | `brew-1`: none possible (retired); answered in §4.1; guard 4a keeps any brew read plan from coming back | `tests/test_legacy_family_names.py::test_brew_has_no_live_references` (new); existing `test_legacy_family_names.py::test_brew_intermediates_is_removed` (:214-222; brew not in `readplan.families()`) | `evidence/brew/E2_registry.txt`, `evidence/brew/E3_guard.txt`, §4.1 text | `measured` (answer from the cached plan; nothing to fix) |
| `brew:137` (sentence 1) | "The rule also passes an item whenever the lens names no wrong colour…" | `brew-2`: §4.2 states what the rule really did; item 2 drops the floorless brew row from `wsbench report` | `tests/test_results.py::test_markdown_table_omits_removed_family_rows`, `tests/test_cli.py::test_report_json_omits_removed_families` | `evidence/brew/E1_report_before_after.md` | `done` once both tests are green at the footer SHA |
| `brew:137` (sentences 2-3) | "Show the score next to the baseline, or report score minus baseline. Right now the report shows no floor at all." | `brew-2` (no floorless row) + `brew-5`: retirement note with the score − baseline table (§4.3) | same two tests | `evidence/brew/E1_report_before_after.md`, `evidence/brew/E5_retirement_note.md` | `done` (report) + `measured` (cached table) |
| `brew:138` | "This should not be the case, we should require the correct color…" | `brew-3`: none possible (retired); §4.3 shows the cached numbers incl. `primary = gold`; a revival must use an MC judge with `mc.CANNOT` last via `mc.options_with_cannot` | guard test 4a | `evidence/brew/E5_retirement_note.md` | `measured` |
| `brew:139` | "We should retire this eval from the public workspacebench" | `brew-4a/4b/4c`: already done (#131); guard test, skill scrub, report.json rule string | guard test 4a; existing `test_brew_intermediates_is_removed` (:214-222), `test_readplan.py:37-38` | `evidence/brew/E2_registry.txt`, `E3_guard.txt`, `E4_pr69.txt`, `E6_space.txt` | `done` once 4a is green on our branch; `pending` for E4 until the #69 follow-up commit lands |

---

## 1. Current state

### 1a. The family is gone from the live code
- `src/wsbench/registry.py:32-36`: `REMOVED_FAMILIES["brew_intermediates"] = "removed 2026-10-29
  (plan 0029): the prompt alone solves it"`. It is never registered.
- Deleted by `7d73944` (81 files, -130,618 lines): `evals/brew_intermediates/{README.md,items.json}`,
  `src/wsbench/evals/brew_intermediates/{__init__,judge,prompts}.py`,
  `examples/readouts/brew_intermediates.jsonl`, `src/wsbench/adapt/brew_port.py`, every
  `adapted/<model>/brew_intermediates.json` and its `floors/floors.json` entries, and the brew
  tests (`test_brew_intermediates.py`, `test_summary_mode_brew.py`, `test_adapt_brew_port.py`).
- Removed from every consumer: `readplan.py` (old branch at `7d73944^:src/wsbench/readplan.py:484-499`),
  `baselines/{lucky_guessing,prompt_only,text_inversion}.py`, `capable/questions.py`,
  `adapt/{families,generate,lint,run}.py`, `scripts/summary_mode_compare.py`,
  `atlas/{build,export_cb,normal_gate}.py`, `atlas/site/app.js`, `viewer/build.py`, the docs.
- Frozen floors: none of `evals/baselines/{lucky_guessing,prompt_only,prompt_only_summary,
  anti_text_inversion}.json` contains a brew key (grep count 0 for each).
- Tests: `tests/test_legacy_family_names.py:214-222` (brew is in `REMOVED_FAMILIES`, not in
  `FAMILIES`, not in `readplan.families()`, not in the ATI file); `tests/test_readplan.py:37-38`
  (35 families, comment "- brew_intermediates (0029)").
- Macro: `src/wsbench/results.py:256-257` excludes a stale brew `results.json` (reason
  `removed`). `tests/test_results.py:180-189` covers this for ttt/ttt_move.
- Public HF Space `camilablank/workspace-bench-viz` (sha `2819998`, 19 files): no brew file.

### 1b. How it read and judged before retirement (for the record; deleted code)
- Read plan (`7d73944^:src/wsbench/readplan.py:484-499`): `chat_prefill` with prefill `Answer:`,
  24 pinned cells per item (`eval_positions`), labelled by region: `stir` 6, `start` 6,
  `question` 9 (the whole "What colour is the potion at the end?" sentence, e.g. item 0 positions
  145-153), and `emit_asst`/`emit_think`/`emit_colon` 1 each. All 11 layers (GRID 20..60).
- Default `opts=regions=headline` judged only the emission cells and the stir cells. The question
  sentence was judged only under `regions=all` (old README "Read cells and regions").
- Judge (native): one blind multi-select call per cell over 5 colours (gold, start, answer, 2
  off-path). Item passes iff `K·G > ΣO` over emission cells (ties fail). The start and answer
  colours are never penalised. Summary mode (plan 0021): per-region digests plus a `ranked` rule.
- Floors: no analytic chance. The extras held `null`/`baseline`/`stir_pass_rate`. Prompt-only
  (0.958, judged by **Gemini 3.8 Flash**, L44) was marked `saturated`. Under plan 0023 it was
  never drawn beside Opus rows, so the report printed `—`.

### 1c. Leftovers that still mention brew (full grep of the tracked tree, excluding `plans/`)
| where | kind | action |
|---|---|---|
| `src/wsbench/results.py:300-347` `markdown_table` / `src/wsbench/cli.py:286-301` `ReportRuns` | **live**: a stale `brew_intermediates/results.json` in an old run dir still gets a full score row | fix (item 2) |
| open PR #69 `.claude/skills/wsb-new-questions/**`, which the infra PR re-creates in our tree (infra §2.10, decision "PR #69 skill") (55 brew lines: `gen_deterministic.py` `gen_brew`/`brew_item`, `gate_hf.py` `brew_cells`, `FINAL_ANSWER`/`STRICT` sets, `families.md` "### brew_intermediates", `item-schema.md`, `scoring.md` "### Brew") | **would re-add** generation/gating for a removed family | fix before #69 merges (item 4b) |
| `adapted/*/report.json` `gate.rule` = `"greedy right AND >= 8/10 (10/10 chain, brew)"` (11 files) | stale description string | change to `"(10/10 chain)"` (item 4c) |
| `CLAUDE.md:136`, `evals/baselines/README.md:397`, `tests/test_readplan.py:38` | correct "retired" notes | keep |
| `adapted/*/AUDIT*.md`, `*/SET_AUDIT.md`, `adapted/*/audit_2026-10-23_drops.json`, `.claude/skills/adapt-bank/{SKILL_AUDIT,SKILL_AUDIT_RESPONSE}.md`, `.claude/skills/adapt-bank/SKILL.md:17`, `references/pitfalls.md:8,87` | dated history / yield anecdotes | keep (plan 0029: "leave the history and add nothing") |

Other hits (`brewed`, `brewer`, `Brewster`, `Hebrew`) are ordinary words inside bank prompts and
have nothing to do with the family.

Outside the public repo (FYI only, not in scope): the private `global-workspace` repo still holds
the source bank (`evals/workspace-bench/hillclimbing_evals/multi_token/brew_intermediates/`), a
`workspace-bench/workspace_bench/adapters/brew_intermediates.py` adapter, and
`docs/project/experiments/ola/brew_intermediates_eval.md`. The audit artifact keeps
`/workspace/root/wsb-audit-artifact/retired/brew_intermediates.json`, and its `index.html` /
`overview.html` still quote "brew (0.96)" in the saturation list.

---

## 2. Change list

**1. "Positions should be read at the last entire sentence: 'What colour is the potion at the
end?'"**
- No code change: the family is retired, and there is no read plan to edit. Answer in §4.1.
- Test: `tests/test_legacy_family_names.py::test_brew_has_no_live_references` (item 4a) fails on
  any new brew read plan; existing `test_legacy_family_names.py:214-222` asserts brew is not in
  `readplan.families()`. Evidence: §5 E2/E3.

**2. "The rule also passes an item whenever the lens names no wrong colour … Show the score next
to the baseline, or report score minus baseline. Right now the report shows no floor at all."**
- The brew rule is gone (§4.2). The only remaining brew report is the one `wsbench report`
  renders for an old run dir. Verified in-memory on the cached run
  `/workspace/gw-relational-ar/outputs/wsb_latest/outputs/judged/rl-onchat-x4/`:
  `markdown_table` prints
  `| brew_intermediates | pass_rate | 0.905 | [0.762, 1.000] | 100 | — (no analytic floor; …) | — | — | claude-opus-5-5 | no | no |`
  (lucky and prompt-only both `—`). It also prints a full `ttt_move` row. Both are excluded from
  the macro but still look like live results with no floor.
- Change: `src/wsbench/results.py` `markdown_table` (around :315) skips the score row of any
  family in `registry.REMOVED_FAMILIES`. It is still listed under "Not in macro:" as
  `- brew_intermediates: removed (removed 2026-10-29 (plan 0029): the prompt alone solves it)`;
  that path at :365-366 is unchanged. `markdown_table` gains a keyword `removed: Mapping[str,str] | None = None`
  defaulting to the registry map (lazy import, same pattern as `macro` :244-249). In
  `src/wsbench/cli.py` `ReportRuns.execute` (:286-310), the `--json` payload's `families` list
  drops removed families the same way; `macro` stays as it is, so they still appear in
  `macro.excluded`. `cli._write_summary` (:891) gets the filter through `markdown_table`. The
  same rule applies to ttt/ttt_move for free, and to the families this campaign adds to
  `REMOVED_FAMILIES` (hallucination per infra §2.5 / hb.md; wrong_bridge_true and multihop_mt per
  their specs), so their old-run rows lose their floorless score row too.
- The filter is keyed on `registry.REMOVED_FAMILIES` only. Superseded-but-registered families
  (typo, superseded by typo_mt) keep their rows; how they are shown is owned by typo.md and infra.
  The filter goes in on top of infra's `results.py`/`cli.py` changes (this PR rebases onto infra),
  as one small check at the top of the row loop; it must not touch infra's floor-match code
  (`summary_floor_applies` on `reads.strip_reads(prompt_version)`).
- No score-minus-baseline column is added for brew, because no brew score is reported any more.
  The retirement note on the final website shows each cached score beside its baselines (item 5).
  A general "Δ vs floor" column for live families belongs to the GENERAL/report workstream; this
  spec does not add one.
- Tests (new; no pre-existing assertion changes. `test_macro_excludes_removed_families` still
  passes because its asserted "- ttt: removed" line remains):
  - `tests/test_results.py::test_markdown_table_omits_removed_family_rows`: results for
    `brew_intermediates`, `ttt_move` and `core`, rendered with
    `markdown_table(results, macro_row=macro(results))` (the "Not in macro:" block is only
    printed when a macro row is passed, `results.py:346-366`). The table has no line starting
    with `| brew_intermediates |` or `| ttt_move |`, has `| core |`, and still contains
    `- brew_intermediates: removed (`.
  - `tests/test_cli.py::test_report_json_omits_removed_families`: write `results.json` for brew
    and core into a tmp dir, run `ReportRuns` with `json=True`. `families` contains only core, and
    `macro.excluded` contains brew with reason `removed`.

**3. "This should not be the case, we should require the correct color to be shown by the
readout/summary"**
- No code change (retired). §4.3 explains that the gold already had to be named at least once,
  and what was actually lenient. If brew is ever revived, it has to come in as a new family
  through the plan-0029 reversal process, with an MC judge where the gold must be the unique
  chosen colour and `mc.CANNOT` is appended last through `mc.options_with_cannot` (D4). That is
  out of scope.
- Test: guard 4a (no brew judge can come back unnoticed). Evidence: §5 E5, whose
  `primary = gold` column shows how rarely the gold was the one colour singled out.

**4. "We should retire this eval from the public workspacebench"**
- Already done by #131 (§1a). Three hardening items:
  - **4a. Guard test** `tests/test_legacy_family_names.py::test_brew_has_no_live_references`
    (round 2 rewrite).
    - Files scanned: `git ls-files` under the roots `src/ tests/ scripts/ atlas/ docs/ evals/
      examples/ adapted/ .claude/ README.md AGENTS.md CLAUDE.md`, **minus data files**: every
      `*.json` / `*.jsonl` under `evals/`, `adapted/`, `examples/` except `adapted/*/report.json`.
      Bank items and model responses use "brew" as an ordinary word ("morning brew" in three
      `adapted/*/hallucination.json`), and refilled banks may too; data files are not where a
      family can come back.
    - Regex (case-insensitive, `re.I`): `brew_|_brew\b|\bbrew\b`. It catches
      `brew_intermediates`, `brew_port`, `gen_brew`, `brew_item`, `BREW_HEAD`, `brew_cells`,
      "### Brew" and prose like "chain and brew"; it does not match `Hebrew`, `brewed`,
      `brewer`, `Brewster`. Checked on `origin/skill/new-questions`: all 55 added brew lines of
      #69 match.
    - Path check: no tracked path outside `plans/` contains `brew` (case-insensitive), so a
      revived `evals/brew_intermediates/items.json` fails even though bank JSON is not scanned.
    - Allowlist (exact paths / globs): `plans/**`, `adapted/*/AUDIT*.md`,
      `adapted/*/SET_AUDIT.md`, `.claude/skills/adapt-bank/SKILL_AUDIT*.md`,
      `.claude/skills/adapt-bank/SKILL.md`, `.claude/skills/adapt-bank/references/pitfalls.md`,
      `src/wsbench/registry.py`, `tests/test_legacy_family_names.py`, `tests/test_readplan.py`,
      `tests/test_text_inversion.py`, `tests/test_results.py`, `tests/test_cli.py`, `CLAUDE.md`,
      `evals/baselines/README.md`. Any other hit fails the test with every file:line, so if #69
      merges unscrubbed, CI goes red.
    - Verified on `cd6b0fa` with this exact scan: the only non-allowlisted hits are the 11
      `adapted/*/report.json` gate-rule strings (4c), and no tracked path contains `brew`.
    - The campaign evidence site lives outside the repo (`/workspace/root/wsb-bp/site/`, gpu
      G11), so the E5 retirement note does not touch the guard.
  - **4b. Skill scrub** (agent skill; decision "PR #69 skill", infra §2.10). The infra PR
    creates `.claude/skills/wsb-new-questions/` in our tree; those files must be created
    **without** any brew content. If #69 is still open, the infra follow-up commit onto the #69
    branch carries the same scrub in the same commit as the native-language step. This spec
    adds no separate edit to #69. What to remove from #69's content, in
    `.claude/skills/wsb-new-questions/`: `gen_brew`/`brew_item`/`BREW_HEAD` and the
    `brew_intermediates` choice from `scripts/gen_deterministic.py`, `brew_cells` and its call
    from `scripts/gate_hf.py`, `brew_intermediates` from `FINAL_ANSWER` and `STRICT`, the brew
    references in `scripts/restamp.py`, the "### brew_intermediates" section in
    `references/families.md`, the brew schema in `references/item-schema.md`, "### Brew (colour
    multi-select)" in `references/scoring.md`, and the brew mentions in `SKILL.md`,
    `references/gating.md` and `references/weak-model.md` (55 diff lines total). Test: guard 4a
    on our branch, which covers the infra-created skill files, and on #69's branch after the
    follow-up commit.
  - **4c. `adapted/*/report.json` gate rule string** (11 files). Change
    `"greedy right AND >= 8/10 (10/10 chain, brew)"` to `"greedy right AND >= 8/10 (10/10 chain)"`.
    Every other key stays byte-identical in value: rewrite with the same `json.dumps(indent=1,
    ensure_ascii=False) + "\n"` the files use (verified: all 11 round-trip byte-identically at
    `cd6b0fa`), and diff to confirm only that line changed. Test: guard 4a
    (report.json is not allowlisted).
  - No `REMOVED_FAMILIES` change. No bank version bump, because no surviving bank changes.

---

## 3. Data needs
- Bank edits: none. No new bank version, no prompt_version/instrument bump (D9 does not apply).
- New items: none. No Qwen GPU gating.
- Readouts to regenerate: none.
- ATI (D10): brew has 0 items in `anti_text_inversion.json` and no key there. Nothing changes.
- Prompt-only Opus rerun (D8, GENERAL): **skip brew**. It is not a registered family, so a
  `families=all` prompt-only pass will not include it. Do not add it.
- GPU production: brew is not in `FAMILIES_BP` (gpu G2(d); "brew_intermediates (already absent
  at cd6b0fa)" in gpu's dropped-from-production list), so the 12-config run and the required
  J-lens / ML-NLA arms (G14) produce no brew readouts, and `scripts/audit_run.py` expects none.
- Leniency audit (gpu G12 / R4b, `scripts/audit_verdicts.py`): runs over the judged
  `FAMILIES_BP` dirs, so there is no brew row. Nothing to audit: no brew verdict is produced.
- ATI re-gate (gpu G13 / R8): no brew entry (not in the frozen ATI file).
- Campaign D1-D7 (summary default, `reads=full|lite`, `layers=all|each|<csv>`, `mc.CANNOT`,
  tool-name-free prompts, the Q4 combining rule, `sampling: bullet4|prose1|tokens10`) do not
  apply: there is no brew code left to change. None of them is impossible; they are moot.

---

## 4. Answers

**4.1 Were the question-sentence positions read?** The bank pinned all 9 tokens of "What colour
is the potion at the end?" as the `question` region (item 0: positions 145-153). The default
`regions=headline` judged only the 3 emission cells and the 6 stir cells. The question sentence
was judged only under `opts=regions=all`, and the old README says the source run's compute
region carried almost no lift (0.03, versus 0.18 for emission). Camila's reading is right: the
default did not read that sentence. Moot now.

**4.2 Did a readout with no colours pass?** Not literally. Native rule `K·G > ΣO`: with G = 0
the left side is 0, so the item fails. The gold had to be named in at least one emission cell.
The leniency is that once the gold appears once and no off-path colour appears, the item
passes, even if the gold is buried among the start and answer colours, which are never
penalised. Audit numbers: 57 of 75 J-lens summary passes named no off-path colour. The judge's
single "primary" pick was the gold 0-9% of the time; J-lens summary `primary_gold_rate` was
0.00 while it passed 0.78.

**4.3 Score beside baseline (cached v1 verdicts, no new judging; for the retirement note):**

| run | pass | no-info baseline | pass − baseline | role-swap null | stir control | primary = gold |
|---|---|---|---|---|---|---|
| O-lens onchat-x4, native, all layers (`rl-onchat-x4`) | 0.905 (21/100 decided) | 0.444 | +0.46 | 0.214 | 0.619 (null 0.381) | — |
| O-lens s3d, summary v3, all layers | 0.66 | 0.333 | +0.33 | 0.17 | 0.34 | 0.09 |
| O-lens s3d, summary v3, L44 | 0.59 | 0.30 | +0.29 | 0.155 | 0.26 | 0.50 |
| ML-NLA 2k, summary v3, all layers | 0.65 | 0.333 | +0.32 | 0.175 | 0.40 | 0.08 |
| ML-NLA 2k, summary v3, L44 | 0.68 | 0.303 | +0.38 | 0.115 | 0.36 | 0.50 |
| J-lens, summary v3, all layers | 0.78 | 0.327 | +0.45 | 0.10 | 0.23 | 0.00 |
| J-lens, summary v3, L44 | 0.01 | 0.003 | +0.01 | 0.00 | 0.02 | 0.01 |
| prompt-only (Gemini 3.8 Flash reader, L44, native) | 0.958 (96 decided) | — | — | — | — | — |

Sources: `…/rl-onchat-x4/brew_intermediates/results.json`;
`/workspace/root/wsb-summ4-out/brew-*-summary-v3/**/results.json`; the removed prompt-only entry
at `7d73944^:evals/baselines/prompt_only.json` (a Gemini-reader floor; the campaign's
`po-opus-v1` / `prompt_only_summary.json` floor does not cover brew and is not run for it). All
rows are cached v1 artifacts read from disk; this spec makes no API call. The text alone scores about as high as any lens
(0.96 vs at most 0.905), and the stir control, where nothing can be computed yet, passes
0.23-0.62. This confirms the retirement.

**4.4 Is it completely retired?** In the public repo's code, banks, floors, ATI, tests, docs and
the published Space: yes (§1a). Two exceptions remain: (a) old-run reports still print a brew
row (item 2), and (b) open PR #69 would bring back brew generation and gating (item 4b). After
items 2 and 4a-4c it is fully retired, and CI enforces it.

**4.5 Decisions taken (for site section 4, "override if you disagree"; round 3, r2-5).**
- brew is not revived or re-fixed: positions, the colour rule and the floor are answered from
  cached artefacts only (§4.1-4.3), with no new judging or GPU reads.
- No score − baseline column is added to `wsbench report` for brew; removed families lose their
  score row instead, and the cached score − baseline table appears only in the site's
  retirement note.
- The report filter is keyed on `registry.REMOVED_FAMILIES` only; superseded-but-registered
  families (typo) keep their rows.
- The guard (4a) scans code and docs, not bank/response JSON (except `adapted/*/report.json`),
  because "brew" is an ordinary word in model responses.
- The private `global-workspace` brew bank/adapter/doc and the old audit artifact's "brew (0.96)"
  line are left as dated history (out of the public repo's scope).

---

## 5. Evidence plan (for the final website)
Every item writes one artefact under `/workspace/root/wsb-bp/site/evidence/brew/` (the paths the
manifest rows above cite; G11 marks a row `pending` while its file is missing). All are produced
by local CPU commands with the bench venv; no API or GPU call.
1. **E1. Old-run report**: render `markdown_table` on the cached `rl-onchat-x4` run dir (in memory,
   or on a copy). Before (`cd6b0fa`): row `| brew_intermediates | pass_rate | 0.905 | … | — | — |`.
   After: no brew row; the line `- brew_intermediates: removed (removed 2026-10-29 (plan 0029): …)`
   is present. Same for `ttt_move`. Show both snippets. → `E1_report_before_after.md`.
2. **E2. Registry/CLI**: `wsbench list` output has no brew row. `readplan.families()` has no brew
   (35 entries at `cd6b0fa`; the count drops as this campaign removes hallucination,
   wrong_bridge_true and multihop_mt, so quote the final-SHA count, not 35). → `E2_registry.txt`.
3. **E3. Guard test**: `pytest tests/test_legacy_family_names.py::test_brew_has_no_live_references`
   passes on the fix branch. On `cd6b0fa` it fails exactly on the 11 `adapted/*/report.json`
   rule strings (show the failing list as the before state). → `E3_guard.txt` (both runs).
4. **E4. PR #69**: the guard regex `brew_|_brew\b|\bbrew\b` (case-insensitive) over the added
   lines of `git diff origin/main...skill/new-questions` goes from 55 to 0 (it never matches
   `Hebrew`), or the guard test passes on #69's branch; if #69 is merged or closed first, the
   guard on our branch is the evidence. → `E4_pr69.txt`.
5. **E5. Retirement note** (one short website section): "brew_intermediates was retired (plan 0029,
   PR #131): the prompt alone gives the answer (0.96); scores beside baseline:" followed by the
   §4.3 table. That answers Camila's "score next to the baseline" bullet for the only numbers
   that will ever be shown. → `E5_retirement_note.md` (rendered inside site section 1, brew block).
6. **E6. Public Space**: list the `camilablank/workspace-bench-viz` files (19, none brew), and the
   new Modal site's family index has no brew card beyond the retirement note. → `E6_space.txt`.
7. **E7. New errors found**: one line for site section 5, "brew_intermediates: none (retired; no
   verdicts, audits or floors produced in this campaign)", so the section's per-family list is
   complete rather than silently missing brew. Written by `site/build.py` from this spec, no
   artefact file.

---

## 6. Risks / conflicts (shared files)
- `src/wsbench/results.py` (`markdown_table`): also edited by the GENERAL/report workstream
  (floors, Δ-vs-baseline, summary/lite columns) and by any family changing macro inclusion
  (e.g. typo "drop from the macro"). Keep this change a small, separate filter at the top of
  the row loop.
- `src/wsbench/cli.py` (`ReportRuns.execute`, `_write_summary`): shared with whichever
  workstream changes report output or tiers (#75).
- `tests/test_results.py`, `tests/test_cli.py`, `tests/test_legacy_family_names.py`: new tests
  only, appended; no pre-existing assertion edited. hb.md and wrong_bridge.md add sibling
  `*_is_removed` tests in `test_legacy_family_names.py` modelled on
  `test_brew_intermediates_is_removed`; that test stays unchanged.
- `adapted/*/report.json` (11 files): the adapt/ATI workstreams may also rewrite these. Do 4c as
  a one-line string replacement and re-check the byte-identical-other-keys diff after rebasing.
- `.claude/skills/wsb-new-questions/**`: created by the infra PR (infra §2.10) and offered to #69
  as a follow-up commit. Item 4b is a constraint on that infra edit (no brew content), not a
  separate edit. If infra copies #69's files verbatim, guard 4a fails our CI, which is the
  point.
- Sibling removal specs (hb.md, multihop_mt.md, wrong_bridge.md) cite brew as precedent. Their
  new WSB plans go under `plans/` (allowlisted) and their `*_is_removed` tests go in
  `tests/test_legacy_family_names.py` (allowlisted). Any other new file of theirs that names brew
  (a README, CHANGELOG, or code comment) fails guard 4a: reword it ("as plan 0029 did") rather
  than widen the allowlist. The same holds for infra/gpu files in the bench tree (e.g. no brew
  literal in a `FAMILIES_BP` comment).
- The guard test's allowlist must be maintained. A new dated history doc mentioning brew needs
  either a path under `plans/` or an allowlist entry. `brewed` / `Hebrew` never match the
  `brew_|_brew\b|\bbrew\b` regex; the bare word "brew" in bank items or model responses is out
  of scope because data JSON is not scanned (4a). A bare "brew" in new prose docs/code does
  fail and needs rewording or an allowlist entry.
- The audit artifact website (`/workspace/root/wsb-audit-artifact/{index,overview}.html`) still
  lists "brew (0.96)" among saturated families. The new campaign site must not reuse that line,
  except inside the retirement note.

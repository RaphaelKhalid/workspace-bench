# 0024: summary mode is the default

Status: rev 2 (critique rounds 1-2; the Rev 1 / Rev 2 decision sections override earlier text). Owner: Camila. Date: 2026-10-29. Issue #117. This builds on plans 0020 (summary
mode), 0021 (brew / buggy / agentic), 0022 (digest-v3, the numbers digest, UM synonyms) and 0023
(Opus 5.5 is the default judge). Every rule of those plans holds unless it is restated here.

Camila (2026-10-29): "let's push the summarizer as a default step before every workspacebench eval
in the public repo".

## Goal

Every `wsbench run` / `wsbench judge` runs each family with `aggregate=summary` unless the user
passes `opts=aggregate=native`. Native stays available, byte-identical, as the explicit opt-out.
hallucination and jlens_concept_pr keep running native under the summary default, with their
existing stamp and note (`digest.NATIVE_ONLY`); the macro already excludes native rows from a
summary run.

## Where the default lives: the benchmark entry, not the family library

- `digest.DEFAULT_AGGREGATE = "summary"`. `runner.parse_opts` — the one place every CLI run
  (`run`, `judge`) turns `opts=` into the families' `extra` (runner.py:177, cli.py:187) — sets
  `aggregate` to `DEFAULT_AGGREGATE` when the user did not pass it, before `digest.validate`.
  Every downstream reader already sees an explicit value: `judge_family`'s NATIVE_ONLY stamping
  (`opts.get("aggregate") == "summary"`), the runner's digest preflight, the families'
  `digest.summary_mode(args)`.
- `digest.summary_mode`'s own fallback for an `extra` with no `aggregate` stays `native`: a
  family called directly with a hand-built `JudgeArgs` (the family test suites; no production
  path builds one — the runner is the only constructor besides `digest._probe`) keeps its own
  rule. Its docstring says so: the benchmark default is set at the entry, not here.
  Consequence, deliberate: no pre-existing family test changes.
- Sanctioned pre-existing test updates: any test asserting that `parse_opts([])` (or a CLI run
  with no `opts=`) yields native gets the summary default; such a test that meant native adds
  `aggregate=native` to its opts. Nothing else.
- New tests: `parse_opts([])["aggregate"] == "summary"`; `parse_opts(["aggregate=native"])`
  keeps native; a runner-level run with no opts stamps `config.aggregate == "summary"` for a
  hooked family and `"native"` + note for a NATIVE_ONLY one; `aggregate=native` through the
  runner is byte-identical (same `results.json` minus timestamps) to a run with the pre-0024
  default on a fixture.

## Floors under the new default

`wsbench report` draws a frozen floor only where `results.floor_applies(r)` (the family's judge
AND its native `prompt_version`), and `markdown_table` blanks every floor on a summary row (plan
0020: a native-mode floor is not a floor for a summary number). Under the summary default every
report would therefore lose its floor columns. Fix:

- **Prompt-only, summary mode.** Re-judge the frozen prompt-only readouts
  (`/workspace/root/ext/wsb-runs/prompt-only{,2}/<family>.jsonl`, the same layer per family as
  the native floors: 20 for the bank families, 44 for moral_rationale / conjunctive / relational /
  user_modeling, 56 for arithmetic / buggy, 20 for directed_modulation) with `aggregate=summary`
  and the default digest settings, and freeze them into a new
  `evals/baselines/prompt_only_summary.json` (same entry shape; `instrument` = the summary-mode
  `prompt_version`, e.g. `bank-2026-10-10+digest-v3-blind-extractive+sj-v7`).
  `prompt_only.floors(dst)` is unchanged; a new `prompt_only.summary_floors()` reads that file and
  keeps entries whose `instrument` equals the family's current summary prompt version (built with
  `digest.prompt_version(spec.judge.prompt_version, <default summary args>, family)`) and whose
  judge is the family's judge. `wsbench baseline kind=prompt_only` gains `aggregate=summary` to
  freeze into the new file.
- **Lucky guessing** asks one guess per item from the option list alone: a per-call floor. A
  summary row judges one unit per item, so this floor is the right one for summary rows (plan
  0020 blanked it there because it understates a native any-of-grid max). `markdown_table` draws
  the lucky column on summary rows that pass `floor_applies` minus the prompt-version clause
  (judge match only); the prompt-only column on summary rows comes from `summary_floors()`.
- Native rows keep exactly today's floors and rules.
- Families with no option list (free recall: chain, arithmetic, buggy, brew, agentic) have no
  lucky floor in either mode, as today.

## Docs

The top-level README, `CLAUDE.md`, `AGENTS.md`, `docs/summarizer.md`,
`docs/summary_mode_validation.md`, `evals/baselines/README.md` and every family README that
calls summary mode "opt-in" or says "the default stays `aggregate=native`" are rewritten: summary
is the default, `opts=aggregate=native` opts out. The plan 0020-0022 validation docs keep their
history and gain one line saying the default flipped here.

## Validation

- Full test suite (CI).
- `wsbench run ... dry_run=True` with no `opts=` prints the digest prompt for a hooked family.
- The summary-mode prompt-only floors are measured and frozen (Opus 5.5, the default judge),
  and a `wsbench report` over a summary run (plan 0022's `d3b-s3d-all-summary-v3`) draws them.
  Sanity: each summary prompt-only floor is reported beside its native one in
  `evals/baselines/README.md`.

## Rev 1 decisions (critique round 1)

1. **Tests.** The "no pre-existing family test changes" claim is wrong: the family suites drive
   `main(["judge"|"run", ...])`, which goes through `parse_opts` (62 tests across ~22 files fail
   under the flip). The ONE sanctioned edit to a pre-existing test: a test that means native gets
   `aggregate=native` added to its CLI opts (`opts=aggregate=native`, or `,aggregate=native`
   appended to an existing `opts=` value; for `runner.run_families` callers, the same key in the
   parsed opts). No assertion changes, no autouse fixture (it would hide the default). New tests
   pin the default (below).
2. **Unhooked families stay strict.** `judge_family` keeps exiting 2 when a summary run comes back
   native and the family is not in `NATIVE_ONLY`. The add-a-family checklists in `CLAUDE.md` and
   `AGENTS.md` gain: "implement summary mode (`digest.collapse` + a summary judge path) or add a
   `digest.NATIVE_ONLY` entry with its reason".
3. **Production paths that must stay native** get an explicit `opts=aggregate=native`:
   `scripts/ati_panel_judge.sh` (its output feeds `text_inversion.draw_verdicts`, which reads
   native row shapes), the ATI judging commands in `evals/baselines/README.md`,
   `atlas/normal_gated.py` (re-judges into a dir seeded with native caches), and
   `scripts/cache_only_run.py` (injects `aggregate=native` unless the user gave one).
   `text_inversion.gate()` / `draw_verdicts` refuse a result with `config.aggregate == "summary"`
   (exit 2 with the reason). `opts=cells=frozen` on arithmetic now needs `aggregate=native`
   (summary forbids it): the family README says so.
4. **Freezing prompt-only floors** is `wsbench freeze kind=prompt_only` (there is no
   `baseline kind=prompt_only`). `prompt_only.freeze` routes on each result's
   `config.aggregate`: native results go to `prompt_only.json` with today's checks; summary
   results go to `prompt_only_summary.json`, each entry also storing `aggregate`, `summarizer`
   (the result's `config.summarizer` minus `concurrency` / `timeout`) and `layers_judged`; a
   source dir mixing modes is refused.
5. **Summary floors are row-relative.** A summary row draws a prompt-only summary floor only when
   (a) `r.config.prompt_version == entry.instrument`, (b) `r.config.summarizer` (minus
   `concurrency` / `timeout`) equals the entry's `summarizer`, and (c) `r.config.judge_model ==
   entry.judge_model`. No recomputation of a family's summary version (agentic, moral
   `+contrast-off` and the regex families stamp their own); the frozen entry is the reference.
   `floor_columns()` returns per-mode maps; `markdown_table` picks a row's column cells by its
   `config.aggregate` (summary rows: prompt-only from the summary map under (a)-(c); lucky from
   the lucky map when `spec.scorer or on_family_judge(r)` — the lucky floor is model-free of the
   digest, so a non-default `summ_model` row still gets it). `SATURATED` / lower-is-better notes
   apply to both maps. `report --json` adds `prompt_only_summary` to `floors` and a per-row
   `floor_applies` that is mode-aware. The macro is unchanged.
6. **Which summary floors.** Every family with a native frozen prompt-only floor on the current
   instrument, from the same readouts and layers: association, basic_readout, multihop,
   multilingual, poetry, typo (`prompt-only/<f>.jsonl`, `layers=20`); moral_rationale
   (`prompt-only/moral_rationale.jsonl`, 44); directed_modulation (`prompt-only2`, 20);
   conjunctive_association, relational_multihop, user_modeling (`prompt-only2`, 44);
   arithmetic_intermediates, buggy_code (`prompt-only2`, 56); the regex families basic_readout_mt,
   multihop_mt, multilingual_mt, multilingual_multihop, multilingual_typo, typo_mt
   (`prompt-only/all.jsonl`, 20). brew / chain / role_bound have Gemini-era native floors that 0023
   already stopped drawing: no summary floor either.
7. **Cost and keys.** Under the default, the regex families make one digest call per item (they
   were free), every run preflights a digest model for every runnable family, and an `all=True`
   run digests agentic bundles (up to ~0.9M tokens per item). Docs say so (a Cost line in the
   README and each regex family's card; `calls_per_arm` strings give the summary figure with the
   native one in parentheses). `wsbench run` warns (stderr, once per family) when
   `out/<family>/results.json` already exists with a different `config.aggregate`; `run.json`
   records the effective `aggregate`.
8. **Docs also:** README dry-run wording ("prints the first digest prompt" for summary), the regex
   family cards ("Prose readouts need no call" → summary makes one digest call per item; native
   none), README §summary mode ("opt-in" → default), `docs/producing_readouts.md`,
   `evals/baselines/README.md`, the `digest.py` module docstring and `summary_mode` docstring,
   the add-a-family checklists; historical plan/validation docs get a one-line note only.
9. **Test details.** The default-pinning runner test uses `tests/summary_fakes.py` with a hooked
   family (basic_readout on its toy file); "byte-identical" = the whole `results.json` of a
   native-opt-out run equals a pre-0024-default run's, compared on the same fixture (results
   carry no timestamp).

## Rev 2 decisions (critique round 2)

1. `src/wsbench/adapt/floors.py` (adapted-subject floors, beside native atlas bundles) also pins
   `opts=aggregate=native` and stamps `aggregate` into each `floors.json` family entry.
2. chain_intermediates forbids `cells=` other than `all` under summary too: its README says
   `cells=last` needs `aggregate=native` (arithmetic: `cells=frozen`).
3. **Summary prompt-only floors are judged at ONE layer**, the native entry's. The prompt-only
   summaries are replicated into every layer file; all eleven copies would mark every line
   "prominent" and swamp the digest's ranking, so one layer is the floor over what the text says.
   Recorded with its direction of bias in `evals/baselines/README.md`.
4. **Freeze checks (summary):** `EXCLUDED` and, in a summary run, `digest.NATIVE_ONLY` families are
   skipped before the mode check; a summary result must carry `+digest-` in its `prompt_version`
   and start with the family's current base version plus `+`; subset / no-value refusals as
   native. `complete` is recorded, not required (a one-layer judging is a layer subset, as for the
   native floors).
5. A summary row that has a frozen summary floor withheld (instrument mismatch) shows `—` and sets
   the override flag; `OVERRIDE_LEGEND` gains the summary-row rule.
6. The byte-identity test compares `main(["judge", …, "opts=aggregate=native"])` with
   `SPEC.run(JudgeArgs(extra={}))` written by `write_results` (the family's native fallback), on a
   regex family's toy file (rows, numbers and counts equal).
7. Commands in docs that relied on native being implicit (the ATI judging commands in
   `evals/baselines/README.md`) gain `opts=aggregate=native`.
8. `calls_per_arm` strings stay the native figures (pinned by each family's `test_registered`);
   the README Cost paragraph states that summary mode adds one digest call per item, regex
   families included (supersedes Rev 1 #7's string change).
9. The six regex multi-token families get no summary prompt-only floor in this PR: their
   prompt-only summaries (`gen-prompt-only-hard-mt`) are not on the box; documented.

## Out of scope

Re-scoring published leaderboards or atlas bundles: they carry `config.aggregate = "native"`
and stay valid as native numbers; republishing is Camila's call.

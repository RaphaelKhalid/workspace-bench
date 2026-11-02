# Independent audit of the `adapt-bank` skill (2026-10-18)

**Scope.** SKILL.md + references/{families,authoring,porting,pitfalls}.md against `src/wsbench/adapt/*`,
`scripts/adapt_{box.sh,jlens.py}`, `readplan.py`, `registry.bank_path`, `tests/test_adapt.py`, and the
live sets `adapted/qwen3.5-{4b,9b}` + `adapted/README.md`. Offline only: tests 33/33 pass, ruff clean.
Scratch: `outputs/skill-audit/` (empty; the probes ran read-only against the gate logs). I edited no
code, bank, report or log.

## Verdict: **not ready for "any new model"; ready with fixes for the Qwen3.5 family**

For a Qwen3.5-sized ChatML subject that fits on 24 GB, the runbook works. The gate, select and freeze
bookkeeping is sound, and both audits found 0 gate-fail items. For the stated goal ("any HF chat
model"), three paths are missing or broken:
- **Too big for 24 GB.** There is no Modal path. `adapt_modal.py` is "to be written", `Subject.backend`
  is never read, and the only big-model entry (Gemma) is misconfigured.
- **Non-ChatML tokenizer or template** (Llama, Mistral, Gemma). Carry, hal, the readplan rules and
  freeze's re-stamp hard-code `<|im_start|>`/`<|im_end|>`. Brew, arithmetic and user_modeling fields
  are never re-derived.
- **Recurring audit defect classes with no lint guard.** The 4B audit classes recurred on the 9B, and
  lint still passes the exact items the audits flagged.

## Findings

| # | sev | where | defect | one-line fix |
|---|---|---|---|---|
| 1 | blocker | SKILL.md:69; subjects.py:16,66 | No path for models >24 GB: `adapt_modal.py` doesn't exist and `backend` is unused. Gemma's positional args put `"modal"` into `revision` (it would download revision "modal"), and `n_layers=0` is never resolved. | Write `adapt_modal.py` (Runner on Modal, same gate API), dispatch on `Subject.backend`, use keyword args, resolve `n_layers` from config at `get()` time. |
| 2 | blocker | carry.py:37-45,85; hal.py:101; readplan.py:120-154 | Turn markers are ChatML literals. `restamp_read` crashes (`max()` of an empty list) on Gemma/Llama/Mistral. hal misses the subject's end-of-turn token. `line_one_newline` (poetry) and `from_last_sentence_start` (user_modeling) silently fall back to the whole render. | Derive the turn-end/start ids from the subject's template (render a probe chat and diff). Add a smoke assert per subject. Make the readplan rules template-aware or raise an error instead of falling back. |
| 3 | blocker | run.py:265-291,360; families.md:13; porting.md:35-46 | For a non-Qwen tokenizer, freeze re-stamps only `probe_token_lens` and multihop offsets. Brew `eval_positions`, arithmetic `cell.pos`, user_modeling markers, relational `'s` and the `<think>` tail offsets ship as Qwen indices with no warning. | Refuse to freeze these families (or re-derive them) when `tokenizer != "qwen3.6"`; list them in `freeze_notes`. |
| 4 | blocker | adapt_jlens.py:53,37,113 | Rollouts start from the 27B bank's `input_ids` (Qwen ids fed to the subject: the documented off-policy pitfall), and the HF revision isn't pinned. | Re-render each seed prompt with the subject's template. Take `revision` from `subjects.py`. Derive `--layers` from `remap_layers(GRID, n)`. |
| 5 | major | run.py:491-504 (`regrade`), `profile regate=true` | Regrade rebuilds the gate from legs and drops moral `apply`'s checks. Probe on the 4B log: moral pass goes 144 → 149, and all 200 rows revert to `needs_reasons=True`. Regrade's default families = all. | Skip `moral_rationale` in regrade/regate, or re-run `moral.apply` afterwards automatically. Add a test. |
| 6 | major | run.py:367-390; 9B report.json | Non-full families default to `partial` even if no ladder ran. The 9B ships brew at 3/100 as "partial". Families without a generator or brief (brew, conjunctive, moral new dilemmas, directed_modulation T1) get no instruction. | Status `partial` only if candidates were gated at the floor tier, else `untried`. Add a SKILL rule: no generator and no brief means write one or declare `ooc`/`blocked`. |
| 7 | major | lint.py:131-176; families.md:69-81,158,176-181 | Invariants with no lint, all hit by audits: mlmh bridge/target overlap (4B #4, recurred as 9B #2), alt contains the bridge, stem leak ("pommier"), language-form echo (the leak check is skipped for typo families, lint.py:136), poetry gold in line 2, bridge-question leaks, language name in prompt, multihop trailing space, typo edit distance. Probe: `lint()` returns `[]` for the 9B sydneyopera, burjkhalifa, notredame and dolly items, the 4B hug-rug item and the 4B apple-tree item. | Port `lint_hard_item` fully. Add a post-gate lint for own-answer golds (poetry line 2). Add the flagged ids as regression fixtures. |
| 8 | major | SKILL.md:49; run.py:326,350 | Audit drops and patches are applied by hand-editing `report.json` (`drops[f][id]=reason`, `patches[f][id]={set,note}`). The skill never documents the schema, `AUDIT_RESPONSE.md`, or that hal/carry/jlens ignore drops. | Add an `adapt drop/patch` CLI (or document the schema in SKILL.md §Layout). Make hal/carry honour drops. |
| 9 | major | porting.md:52; hal.py, carry.py, adapt_jlens.py | Regenerated families never write their `report.json` entries. The 9B report lacks agentic, hal, jailbreak and mcdm, though their banks exist. porting.md says to judge only the families listed in report.json. | Each regenerate step writes `families[f]` (n_items, status, note). Point consumers at `readplan.families()`. |
| 10 | major | grade_llm.py:26; run.py:58-89; author.py:885-914; authoring.md:13 | Not resumable mid-step. The grade cache is in memory only (the doc says it "is kept"). A 401 during grading loses the family's whole vLLM sampling. `author` writes candidates only after every call. | Persist the cache (jsonl keyed by question/golds/answer). Write gate rows per chunk. Call `add_candidates` after each call. |
| 11 | major | store.py:78; run.py:482-487,621-624; SKILL.md:38 | `report.json` and banks are written with non-atomic `write_text`, read-modify-write. The runbook says "run each step in its own tmux", so parallel fill/auto/note runs can lose updates. | Write a tmp file and `os.replace`, under an `flock` on `adapted/<m>/.lock`. |
| 12 | major | adapt_box.sh; pitfalls.md:90 | No GPU lock is taken by any step, and the lock path (`/workspace/agam/logs/gpu.lock`) isn't documented. Two vLLM steps OOM a shared 4090. | `flock` the lock inside `adapt_box.sh` for GPU commands. State the path in SKILL.md. |
| 13 | major | SKILL.md:114; __main__.py:28-47 | `gate model=<m> family=<f>` is wrong: `gate` takes `families=`. Unknown keys are silently ignored, so this gates every family's pending candidates. | Reject unknown keys per command. Fix the doc. |
| 14 | major | authoring.md:41; families.py:130,155,179 | The documented `python -m wsbench.adapt gate …` has no `llm=` and bypasses `adapt_box.sh`. conjunctive, role_bound and buggy_code (`grade="llm"`) then fail every item, and the failures are logged as gated. | Make `llm=` required (or default) whenever the family has llm legs. Fix the doc to use `$A gate … llm=claude-opus-5-5`. |
| 15 | major | README.md:25; AUDIT_RESPONSE.md | `adapted/*/floors/floors.json` doesn't exist for any model, though both docs say floors were measured. SKILL.md:138 says `wsbench baseline`, but the code is `adapt floors`, and floors isn't in the runbook. floors.py:86 reads the token once (no refresh) and swallows subprocess stderr (line 97). | Add a step "4b floors" (`$A floors $M`). Use `auth.Session`. Log stderr. Fix the claims. |
| 16 | major | README.md:43; cli.py:193 | `wsbench run all=True` iterates every registered family. Under the 4B root (brew) and the 9B root (jlens) it reports failures and exits 2. Exclusions such as "relational out of the 4B macro" and "9B brew unusable" live only in prose, so `wsbench report` macros include them. | Pass `families=` built from `readplan.families()` (or make `run all=True` use it under WSB_BANK_ROOT). Add a machine-readable `exclude_from_macro` to report.json. |
| 17 | major | families.md:69-70,246,279 | Requirements the code doesn't implement: the bridge leg for original multihop items (82 ungated on the 9B), chain `gate.first`, and buggy "review finds it 4/4". | Implement them, or downgrade the text to "not gated (known gap)". |
| 18 | major | run.py:360-362 vs fill/select | Re-stamping happens after `select`. On a new tokenizer, originals that lose their multi-token form are dropped at freeze, after fill already counted them, so the family ends short while spares exist. | Re-stamp in `lint_and_gate`/`profile` (before select). |
| 19 | minor | porting.md:14 | "0.8B/2B: the 11 GRID layers fold onto 8" is false: `remap_layers(GRID,24)` gives 11 distinct layers (8..22). porting.md:12 omits the clamp to n-1, and banker's rounding applies. | Correct the text. Import `remap_layer` in readplan instead of duplicating the formula (readplan.py:254). |
| 20 | minor | authoring.md:9,35 | "40 items at a time" and "capped at 60 per call" don't match the code: `MAX_PER_CALL=20`, and the wave cap is 60. | Sync the numbers. |
| 21 | minor | SKILL.md:77; families.md:10 | The default "T=0.7" isn't what chain/brew use: they gate at T=0.8, top_p 0.95. Agentic and moral also use top_p 0.95, which porting.md:72,95 doesn't mention. `MIN_RATE=0.375` and `MIN_KEPT=5` are only in code. | Document every sampling knob and threshold in families.md/porting.md. |
| 22 | minor | agentic.py:176; hal.py:96 | Hard-coded values: `n_mis == 28` means full, and `max_model_len=4096` ignores the Subject's setting. | Use the bank's misaligned count and `s.max_model_len`. |
| 23 | minor | gate.py:291-300 | `enable_thinking=False` is assumed to switch thinking off for every template. Nothing checks that the render has no open think block, or that a system role is accepted (older Mistral templates reject it). | Add a step-0 assert on one rendered ask per subject. |
| 24 | minor | report.json (4B buggy) | The note says "43/49 after twin rule", but the bank and n_items are 49. The 9B relational bank (cousin at 68%) predates the CAPS fix. Banks carry no code version. | Stamp the git sha and code hash in report.json. Warn in `status` when the gate log or code is newer than the bank. |
| 25 | minor | README.md:17 | The Gemma path `adapted/gemma-4-31b/` doesn't match the subject key `gemma-4-31b-it`. | Use the key. |

## Guards vs tests (pitfalls + audit findings)

- **Guard with no test:** CAPS (role/relational), drops and patches in `freeze`, `restamp_tokens`, carry
  (jailbreak/mcdm), hal `thin` (int(i*len/8)), agentic `MIN_RATE`, moral `apply` restamping
  `gate_pass`, the mt canonical-one-token / `_padded` / native-correction lint, buggy authored-twin
  grouping (`-au-clean-`), `_post_freeze` layer remap and `BANK_LAYERS` no-double-remap, `bank_dir` /
  `_hal_capture_rows` under WSB_BANK_ROOT, `readplan.families()` skipping ooc families, the `made`
  ALREADY-USED list, poetry `gate_variant` in the plan, and agentic `_first_json`.
- **Pitfall or finding with no guard:** findings 7 and 17 above; the arithmetic null pool < 8 (only a
  freeze note; recurred as 9B #5); "gate ≠ read render" for non-ChatML; off-policy ids in
  adapt_jlens; the GPU-lock rule; and "check no other session owns the run" (no owner file).

## Top 3 improvements

1. **A real non-Qwen / big-model path.** `adapt_modal.py` plus a template-derived turn-marker helper
   used by carry, hal, readplan and the restamp. Freeze then refuses any tokenizer-tied field it
   didn't re-derive. This removes blockers 1–4 and 18.
2. **Close the audit loop in code.** Port `lint_hard_item` with regression fixtures of every
   audit-flagged id. Add an `adapt drop/patch` CLI. Have every step write its report entry, with an
   honest status (`untried` vs `partial`) and `exclude_from_macro`.
3. **Process hygiene.** Atomic, locked report writes; the GPU flock inside `adapt_box.sh`; a persisted
   grade cache and chunked gate/author writes; strict CLI arguments; regrade that preserves moral.

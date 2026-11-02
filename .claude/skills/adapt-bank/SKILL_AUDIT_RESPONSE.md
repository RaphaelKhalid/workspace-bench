# Response to the skill audit (SKILL_AUDIT.md, 2026-10-18)

The audit is left as written. Status per finding as of 2026-10-18 05:00 UTC. Tests: 573 pass
(`tests/`), ruff clean. "Verified" means checked on real tokenizers or subjects, not only by a unit
test.

| # | status | what changed |
|---|---|---|
| 1 | fixed, verified | `scripts/adapt_modal.py` (app `adapt-subject-llm`, vLLM on an H200, CUDA 13.0 devel image) + `gate.RemoteRunner`; `run._runner` dispatches on `Subject.backend`; Subjects use keyword args with a pinned revision and `n_layers`. Gemma-4-31B-it smoke: typo 5/5 through Modal, clean answers. Full Gemma profile running. |
| 2 | fixed, verified | `template.markers(tok)` derives turn start/end and the generation tail from a sentinel render. carry, hal (`stop_ids`) and the readplan rules use it; `from_last_sentence_start` raises without markers. Checked on Qwen3.5, OLMo-3 (ChatML, no think) and Gemma-4 (`<\|turn>`/`<turn\|>`, channel tail). |
| 3 | fixed | freeze re-stamps the MT families and multihop offsets, refuses brew (Qwen `eval_positions`) and refuses relational when `'s` isn't one token. **New:** arithmetic `cell.pos` is re-anchored on the subject's turn-closing marker (`_restamp_arith_cells`; OLMo -8→-4, Gemma unchanged, decoded token checked on each). user_modeling markers are resolved at plan time from the template. |
| 4 | fixed | `adapt_jlens.py` re-renders seeds for non-Qwen tokenizers, takes `--revision`, and accepts a local lens (`--lens-repo`). |
| 5 | fixed + test | regrade preserves moral `apply` checks. |
| 6 | fixed | `untried` vs `partial` per tier; `note` accepts `untried`. 9B brew: still open (pilot the ladder or mark `untried`). |
| 7 | fixed + tests | lint: bridge/answer overlap, stem leak, language-form echo, native-correction multi-token, one-token canonical names, user_modeling/role_bound/buggy checks; poetry gold-in-stub guard in the gate. Audit-flagged ids are regression fixtures. |
| 8 | fixed | `adapt drop` / `adapt patch` CLI; schema in SKILL.md §report.json; hal/carry/agentic honour drops. |
| 9 | fixed | hal, carry, agentic, moral and jlens write their `report.json` entries. |
| 10 | fixed | grade cache persisted (`adapted/.grade_cache/<grader>.jsonl`, decided verdicts); `author` writes candidates per call; `auth.Session` refreshes on 401. |
| 11 | fixed | atomic `write_json` (tmp + `os.replace`); `update_report` under an fcntl lock. |
| 12 | fixed | `adapt_box.sh` takes `/workspace/agam/logs/gpu.lock` for GPU stages (fd-9 inheritance check; `ADAPT_GPU_LOCK` override for Modal subjects). |
| 13 | fixed | strict per-command keys (unknown key = error); doc fixed. |
| 14 | fixed | a family with llm-graded legs and no `llm=` now gets `claude-opus-5-5` (`run.DEFAULT_LLM`, printed) instead of failing every item; docs use `llm=`. |
| 15 | partly | floors step in the runbook (`$A floors $M`, judge `claude-opus-5-5`); generate now goes through the runner (works on Modal). Wording no longer claims floors exist. **Floors not measured yet**: queued after the regate (tmux `floors`). |
| 16 | fixed | `run all=True` under `WSB_BANK_ROOT` uses the adapted families; `exclude_from_macro` in report.json feeds `macro()`. |
| 17 | fixed (data) / doc | chain: `prompt_first` is now a second leg (`first`). multihop originals: 99/100 bridge questions in `src/wsbench/adapt/data/multihop_bridges.json` (1 skipped: "most populous country = China" is stale). buggy "review 4/4": the source gate has no such leg; the doc claim is removed (authored items are executed instead). **4B/9B re-gated with the new legs**: queued (tmux `regate-legs`); `gate regate=true` added so passing new items get the leg too. |
| 18 | fixed + test | `live_rows` re-stamps before select for non-Qwen tokenizers (OLMo: typo_mt 100→85 live), so fill refills before freeze. |
| 19 | fixed | porting.md remap text corrected (24 blocks keep 11 distinct layers; clamp; banker's rounding; Gemma grid listed). |
| 20 | fixed | authoring.md: 20 per call (`MAX_PER_CALL`), 10–60 per wave. |
| 21 | fixed | families.md top: every sampling knob and threshold (chain/brew, moral, agentic `MIN_RATE`/`MIN_KEPT`, hal, floors). |
| 22 | fixed | agentic "full" = every non-dropped misaligned bank item kept (no literal 28); hal uses the Subject's runner, so `max_model_len` comes from `subjects.py`. |
| 23 | fixed + test | `template.check` runs at every runner start: markers derivable, no reasoning block left open, system turn accepted; a failure aborts. |
| 24 | fixed | `report.json` → `code` = git HEAD (+dirty) + adapt-package sha256, stamped on every report write. The 4B buggy note was corrected earlier. |
| 25 | fixed | README path `adapted/gemma-4-31b-it/`. |

## Also new since the audit
- **Fitted J-lenses** where neuronpedia has none: `scripts/fit_jlens_modal.py` (official estimator,
  neuronpedia recipe). Validated against neuronpedia's Qwen3.5-4B lens: per-layer cosine min 0.927,
  mean 0.986 (n=400). Fitted the 9B (n=400) and OLMo-3-7B-Instruct (n=600). Their jlens banks are
  being built (`jlens-9b`, `jlens-olmo`).
- Generation goes only through `Runner` (test): hal and floors no longer build their own vLLM.

## Still open
- 9B brew (3/100 "partial"): pilot the ladder or mark it `untried`.
- No owner file for "is another session running this?"; the convention is still tmux session names.
- A fresh-agent re-audit of the skill once Gemma and the regates have landed.

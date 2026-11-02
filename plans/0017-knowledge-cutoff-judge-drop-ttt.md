# 0017: knowledge_cutoff judged over every position; remove ttt

Status: rev 3 (folds in critique rounds 1-2). Owner: Camila. Date: 2026-10-26. Issue #97. Builds on #96 (the rename), so the
family keys are `knowledge_cutoff` and `ttt`.

Camila (2026-10-26): "cutoff confab should be judged, not regex. we should read at every position
and give them all to a single judge call which needs to choose the option (so that if there are
multiple options the judge needs to consider the relative number of times each is mentioned by
construction). for ttt we should get rid of this eval, it's too similar to next token prediction -
remove it from the anti text inversion set as well as workspacebench."

## Part A: knowledge_cutoff becomes a judged family

### A1. Read plan
- `readplan` rule for `knowledge_cutoff` becomes `{"kind": "all_from_end"}` (every position of the
  chat render, reported as negative offsets −n..−1), layers `GRID` (L20..L60 step 4, unchanged).
  Negative offsets keep `reply_start = −1`, `think_close = −2`, `user_end = −10` at the same
  coordinates as before, so readouts produced under the old three-site plan still load. The row's
  `extra` drops `sites`; the note says every prompt position is read and all are judged together.
- The bank (`items.json`) is frozen and is not edited. `g3_leak_items` stay unplanned and unscored.

### A2. One judge call per (item, layer)
- **Cell = (item, layer)**, not (item, layer, pos). Every readout row for that item and layer, at any
  position, goes into ONE call. A layer is not pooled with any other layer (each layer stays its own
  measurement; the headline picks one layer, A4).
- **Reads block.** Positions in ascending order (earliest first). Each position is a header
  `[position −k]` followed by its samples as `[sample j] <text>` (the ttt/chain format). The header
  carries the offset only, **never the token text** at that position: the judge must not see the
  prompt. Token cells (J-lens etc.): one bag sample per position, `cell_text` rendering (scores kept
  for the judge, the bare tokens used for verification), as other families do.
- **Options.** The item's `options` (K = 5) in the bank's seeded order, lettered A–E, plus `NONE`.
  The judge never sees `gold`, `truth`, the question or the label.
- **Judge asks:** which option the model is about to give as its answer. The prompt states that the
  readouts come from every position of the prompt; that readouts at early positions often restate
  the question (and may name an option while doing so, e.g. cs01611's prompt names a distractor),
  and **naming an option while restating the question is not an answer**; that when several options
  are named the judge must weigh how many samples, across positions, present each one as the answer
  (the relative-count requirement); and that **the judge must not answer the question itself or use
  its own knowledge of the true answer**: report only what the samples present as the model's
  answer. If no sample presents any option as the answer, NONE.
- **Leakage note (README).** The judge never receives the prompt, but echo readouts at user-turn
  positions carry it (`docs/read_sites.md`), and the true answer is among the options on most items.
  Two diagnostics make judge drift auditable (A4): `answer_kinds["truth"]` (the judge picked
  `truth.canonical`) and `regex_plurality_agreement`.
- **Schema:** `reasoning` (brief), `answer` (enum A–E or NONE), `quote` (a verbatim span from one
  sample that names the chosen option, or empty).
- **Quote check (verification).** A pick is verified iff the quote occurs verbatim inside ONE
  sample (checked per sample: loop over each raw sample of each position row, `quote_in` after
  `mc.fold`; for a token row, against that row's bare tokens as `cell_text` renders them, one row at
  a time; a quote spanning two samples or two positions fails) AND the picked option's regex forms
  (`score.OptionForms.counts([quote])`, the existing exclusive longest-match matcher) credit the
  picked option inside the quote. **Token rows** (J-lens bags) are verified without a quote: the
  pick is verified iff the regex forms name it in `score.token_bag_text(row.tokens)` (space-joined,
  as the old regex scorer matched) for some row of the cell. A quote copied from a scored
  `render_bag` line could never match, and `" | "` would split multi-token options such as
  `Kirin | 9100`. `ati_pass` and every regex diagnostic also use `token_bag_text` for token rows.
- Empty cells (no non-empty sample at any position) make no call; they are judged fails counted in
  `n_empty`.
  An unverified pick scores as no signal (fail), as in ttt and chain.
- **Cell verdict:** `hit` = answer is the gold letter AND the quote check passes. NONE, an
  unverified pick, a wrong letter and an empty cell (no non-empty sample at any position) are judged
  fails. A failed call (`None`) leaves the cell unjudged.
- **Judge model:** the bench default (`google/gemini-3.8-flash`, unpinned), temperature 0, with
  `JudgeConfig.reasoning={"effort": "low"}` instead of the default `minimal`: one call weighs a few
  hundred samples across ~55 positions. No model pin: a new instrument with no tuned source judge.
- **Size.** ~55 positions (≈12 template + ≈40 user-turn tokens) × k samples per call; at k = 5 O-lens
  samples of ~40 tokens ≈ 11k input tokens per call, ≈ 13M per arm over 1,199 calls. Stated in the
  README and in `calls_per_arm`.
- `PROMPT_VERSION = "cutoff-judge-2026-10-26"`. `SCORER_VERSION` and the regex `scorer` field go;
  `EvalSpec.scorer` becomes unset (`""`) so `run` preflights the judge. `calls_per_arm` =
  `"109 × 11 = 1,199 (one call per item and layer, every position in the call)"`.
- Prompts live in `prompts.py` (`SYSTEM`, `USER`, plus the retained `SUBJECT_USER`) and verbatim in
  the family README under "Judge prompts" (`test_prompts_in_readme`). Placeholders rendered with
  `str.replace`, menu first then reads (a sample may contain the literal `{menu}`).

### A3. Completeness
- An (item, layer) cell is **present** iff the file has a row for it at `pos == −1` (reply_start).
  Missing reply_start cells are missing cells: `require_cells` exits 2 unless `allow_missing=True`
  (the existing rule, retained).
- The judge reads every position present for that (item, layer). The bank does not record token
  counts (and adapted banks use other tokenizers), so the family cannot assert "all positions"; it
  reports `extras.positions_per_cell` = {min, median, max} and `extras.n_cells_one_position`, and
  the README states that a three-site legacy readout is judged on its three positions only.
- **Regime.** A present cell is `all` iff its positions are exactly the contiguous run
  `min..−1` and number ≥ 4; otherwise `partial` (e.g. a legacy −10/−2/−1 file). `config.
  positions_regime` = `"all"` if every judged cell is `all`, else `"partial"`, and the result's
  `complete` is forced false when partial, so a legacy-format run is loadable and scored but never
  enters the macro as a full measurement. `extras.n_partial_cells` counts them. The toy readouts
  carry ≥ 4 contiguous positions per cell.
- Rows at non-negative `pos` are not this plan's coordinates: they are ignored and counted
  (`extras.n_rows_nonnegative_pos`) AND passed to `pass_rate_result(skipped_extra=...)`, so
  `counts.skipped_rows` keeps counting them exactly as today (when `load_readouts(positions=...)`
  dropped them into `rep.skipped`). The rewritten `test_off_site_positions_are_ignored` keeps
  asserting `counts["skipped_rows"] == 1`.

### A4. Item rows and headline (bank-wide layer rule retained)
- **Headline = one layer for the whole bank**, the layer with the most judged hits, ties to the
  earliest, **chosen only among layers that have reply_start readouts** (so a partial-layer run such
  as `layers=44`, every ATI gate run, uses its own layer). This retains the existing rule exactly; it
  only swaps the regex strict win for the judge hit as the per-cell bit.
- Rows: one per item that has readouts (rowless items get no row, retained: the ATI gate relies on
  it). Fields: `id`, `gold`, `layer` (the bank layer), tri-state `pass` at the bank layer (undecided
  when that cell is missing or unjudged), `answer` / `picked` (option text or None) / `verified` at
  the bank layer, `hit_by_layer` {layer: bool|None}, `stratum`, `label_type`, and `ati_pass`.
- `ati_pass` (gate only, never the family value; unused while the family is `CONSTRUCTION_GATED`,
  but `STRICTER_PASS_FIELD` keeps pointing at it): at the bank layer, the judge's letter is gold
  ignoring the quote check, OR some sample **at pos −1 (reply_start) of that cell** names gold
  under the regex forms (the regex clause keeps its old reply_start-only meaning; user-turn echo
  positions never count).
- `pass_rate_result` epilogue as now; `n_expected = len(ids) × len(layers)`, `n_unjudged` = cells
  whose call failed, `n_empty` = empty cells.
- `extras`: `n_calls`, `headline_layer`, `candidate_layers`, `hits_by_layer` (counts),
  `per_layer_rate`, `answer_kinds` (hit / wrong / none / unverified tallies), `ati_pass_rate`,
  `by_stratum`, `by_label_type`, `positions_per_cell`, `n_cells_one_position`,
  `n_rows_nonnegative_pos`, `answer_kinds["truth"]` (judged picks equal to `truth.canonical`,
  counted beside hit/wrong/none/unverified), **`regex_plurality_agreement`** (over judged cells:
  share where the judge's pick equals the regex plurality option over ALL positions' samples of that
  cell, ties = no plurality; plus the count of cells where regex plurality is gold but the judge
  picked otherwise and vice versa), and **`regex_reply_start_by_layer`**: the old regex strict-win rate at
  pos −1 per layer (the former instrument, kept as a cheap continuity diagnostic; never the
  headline). The decoder-prior `caveat` string is retained.
- `opts=judge=regex` is no longer accepted; any `opts=judge=` value fails (exit 2) with a message
  naming the judge as the only instrument.

### A5. Docs, toy readouts, tests
- `examples/readouts/knowledge_cutoff.jsonl`: rows at several negative positions per layer
  (including −1) for the existing two toy items, so that the default-judge run in the tests
  exercises bundling.
- Family README rewritten: read sites (every position), the judge (prompt verbatim, quote rule,
  verdict, headline), completeness note, the source numbers relabelled as the former regex
  instrument (not comparable), and the decoder-prior caveat retained in full. Root README: the
  family entry's three lines, and the Judges table row → `google/gemini-3.8-flash |
  cutoff-judge-2026-10-26`; remove knowledge_cutoff from the "regex-scored" prose; README line 8
  "four families pinned to Claude and nine scored by regex" → "three ... and eight ..." (ttt and
  knowledge_cutoff both leave those counts; verify both counts against the Judges table).
  CLAUDE.md: drop "knowledge_cutoff also has its own `score.py`: ... (no call ...)" and say it is
  judged (one call per item × layer, all positions).
- `tests/test_knowledge_cutoff.py`: the regex-matcher tests (`test_number_forms_are_standalone`,
  `test_exclusive_longest_match_and_contested_spans`, `test_strict_win_ties_lose...`) stay (the
  matcher is still used for verification and the diagnostic). **Sanctioned test changes:** tests
  asserting the regex pass rule, the three-site plan or the regex spec
  (`test_example_readouts_pass_at_the_bank_layer`, `test_one_layer_bank_wide_not_per_item`,
  `test_tie_loses_and_ati_pass_is_any_mention`, `test_partial_layer_run_uses_its_own_layer`,
  `test_missing_cells_exit_and_rowless_items`, `test_off_site_positions_are_ignored`,
  `test_spec_and_plan`) are rewritten for the judge with `run_calls` monkeypatched; each must keep
  testing the same invariant it tested (one bank-wide layer, partial-layer run uses its own layer,
  missing cells exit 2 / rowless items get no row, plan shape) under the new per-cell bit. New
  tests: all positions of an (item, layer) land in one call in position order; prompt contains no
  token text / question / gold; quote check (verbatim + option form; unverified fails); NONE fails;
  failed call → unjudged → undecided; `opts=judge=regex` exits 2.

### A6. Anti-text-inversion entry
- knowledge_cutoff stays `CONSTRUCTION_GATED` (whole bank, never asked). Its frozen entry's
  `instrument` and `judge_model` change with the family, so regenerate that entry with
  `text_inversion.construction_entry("knowledge_cutoff")` (ids unchanged, 109). `evals/baselines/
  README.md` row unchanged apart from any instrument mention.

## Part B: remove ttt

Delete, not supersede (`superseded_by` keeps a family runnable; Camila asked for it to be gone).
- Delete `src/wsbench/evals/ttt/`, `evals/ttt/`, `examples/readouts/ttt.jsonl`, `tests/test_ttt.py`.
- `readplan.py`: remove the `ttt` branch.
- `registry.py`: remove `"ttt_move": "ttt"` from `LEGACY_FAMILY_NAMES` (the target no longer exists).
- `baselines/text_inversion.py`: remove `ttt` from `CONSTRUCTION_GATED` and `STRICTER_PASS_FIELD`,
  and the ttt sentences of the `STRICTER_PASS_FIELD` comment.
- `evals/baselines/anti_text_inversion.json`: delete the `ttt` entry (and any ttt mention in
  `_source` / summary fields). `evals/baselines/README.md`: delete the ttt table row; the
  construction-gated bullet becomes knowledge_cutoff only (drop ttt's refusal numbers).
- `capable/questions.py`: remove the `ttt` entry. `llm.py` docstring: drop "ttt and".
- README: remove the Tic-tac-toe entry and the ttt Judges row; in the pins sentence
  ("except three pins", which today lists four) delete the ttt clause, and the count "three" then
  stands; remove "ttt" from the model-specific list ("Five families" → four). Rewrite the rename
  note (README ~62-66, "Four families were renamed ... the old names still work") so it stays true:
  three old names still resolve; `ttt_move`/`ttt` was removed on 2026-10-26 (#97) as too close to
  next-token prediction: in the source repo's ttt README (global-workspace
  `evals/workspace-bench/hillclimbing_evals/multi_token/ttt/README.md`, per-layer table) the plain
  logit-lens argmax at the read site scored 0.733 at L60, above the O-lens's 0.587 at that layer.
- CLAUDE.md: remove ttt from the pins, the effort sentence, the STRICTER/CONSTRUCTION_GATED lines,
  the own-judge list ("Eleven families" → ten) and the rename paragraph (ttt_move no longer mapped).
- **Sanctioned test change:** `tests/test_legacy_family_names.py` drops `"ttt_move": "ttt"` from its
  expected map and switches the plan test (`families=ttt_move` → `ttt.jsonl`) to another legacy name,
  `families=dm_category_default` → `directed_modulation_obscure.jsonl`, same assertion shape.
- **Sanctioned test change:** `tests/test_readplan.py` `len(fams) == 34` → 33 (ttt's bank is gone).
- README line ~34 "`ANTHROPIC_API_KEY` for the four Claude-pinned ones" → three.
- Add a test that `ttt` and `ttt_move` are not registered, not in `readplan.families()`, and absent
  from the ATI JSON.
- `plans/0016` is history: add one note line at its top that ttt was removed by plan 0017; no other
  edit.
- Macro: new runs no longer produce ttt. Old run dirs still hold `ttt/results.json`, and `macro()`
  never consults the registry, so add `registry.REMOVED_FAMILIES = {"ttt": "<reason>"}` (also matched
  under its legacy key `ttt_move`) and exclude those in `results.macro` with reason `"removed"`
  (default from the registry, overridable by a `removed=` argument like `superseded`/`held_out`).
  Test: a results list containing `ttt` (and `ttt_move`) gets it excluded with reason "removed".
  Any committed README number that quotes the macro over a family list including ttt is relabelled
  or noted.

## Out of scope
- global-workspace's viewer / macro family lists still name `ttt`; a follow-up there.
- No live judge run is part of this PR beyond a `limit=3` smoke if a key is available; the full
  rejudge of existing O-lens readouts needs every-position readouts that do not exist yet.

## Gates
`uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q` (CI parity), offline.

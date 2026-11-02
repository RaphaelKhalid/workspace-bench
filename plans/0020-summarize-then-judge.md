# 0020: summarize-then-judge (one summary per item, then one judgment)

Status: rev 6 (critique rounds 1-4; digest-v2 after the D3 audit). Owner: Camila. Date: 2026-10-27. Issue #99.

Camila (2026-10-27): "i want there to be a summarizer step before judging. we should not do a
pass@layer or pass@position like we might be doing for some evals now. i want it to be that for a
given method (including if a method is e.g. olens@layer 44 or olens@all layers) we take ALL of the
readouts from every relevant token position and every relevant layer that the method has the
capacity for, and then we give that ALL to a summarizer llm. this summarizer (opus 5.5 by default)
should be quite passive - it should not be doing any interpretation or the readouts or the
question. [...] then this produces a single summary which then can go to the actual judge. this
will likely decrease scores on workspacebench so we can check and make sure it is not
catastrophic for any particular eval family"

## Goal and non-goals

- **Goal.** Add an opt-in aggregation mode, `aggregate=summary`. It applies to every family whose
  item verdict is today an OR or a max over read cells (pass@layer, pass@position, pass@sample, a
  best layer, or a pre-registered best cell). Under it, for each item:
  1. collect ALL the cells the family reads for that item, at every layer the method has;
  2. hand them to one passive summarizer call;
  3. judge or score the single resulting summary ONCE.

  The item verdict is that one judgment, with no grid, no OR, and no best-cell selection.
- **A method is a readouts file plus a `layers=` selection.** `olens@L44` is the O-lens file with
  `layers=44`, and `olens@all` is the same file with no `layers=`. `JudgeArgs.layers` already
  filters at load, so single-layer methods need nothing new.
- **Opt-in; the default does not change.** `aggregate=native` (today's behaviour) stays the default
  in this PR, so published numbers, goldens and baselines are untouched. Flipping the default is a
  separate decision for Camila once she has the validation numbers (Part D). The repo is public
  and the change moves every headline.
- **Non-goals.**
  - The in-house bundle code under global-workspace `workspace-bench/` is not changed.
  - No bank edits.
  - No read-plan change: producers keep emitting the same readouts.
- **Position scope.** Summary mode reads every position the family's read plan puts in the file.
  A family option that narrows this to a subset is overridden: arithmetic (`cells=frozen`, a
  sweep-picked best cell) and chain (`cells=last`, 1 of 25 planned positions) are forced to
  `cells=all`, and an explicit narrower `cells=` with `aggregate=summary` exits 2. Families whose
  read plan is itself narrow (moral: last 5 positions; relational: the blank; buggy_code: one
  layer) read everything their file holds; widening those is a read-plan change, out of scope and
  listed for Camila beside brew/buggy_code.

## Part A: the shared item summarizer (`src/wsbench/digest.py`, new)

### A1. The summary: extractive by default

The summarizer reads every cell and returns up to `summ_max` digest items, ranked by prominence.
Each item has a `statement`, a `support` word and an `evidence` span copied from ONE readout
(A3). What the judge then reads depends on `summ_render`:

- **`extractive` (default).** The judge reads only verbatim readout text. Each surviving item
  becomes one line, `[{support}] {evidence sample}`. The evidence sample is the WHOLE readout
  sample containing the verified span: a prose sample, or a whole decoded token line.
  - Lines are de-duplicated, keeping the first.
  - The summarizer's `statement` never reaches the judge. It is kept in the item row for audit.
  - So the summarizer *selects and ranks* readout content, and no text it wrote can be judged.
    This is the most passive reading of Camila's spec that still yields a single summary. It also
    closes the leak through the MC families that have no quote gate (moral, relational,
    role_bound, user_modeling, conjunctive, and jailbreak's flag-only quote check), where the
    judge would otherwise answer from summarizer-written statements.
- **`abstractive` (ablation).** Each line is
  `- {statement} [support: {support}] — evidence: "{evidence sample}"`. This is the literal
  "summary" reading. It is run in D3 as an ablation arm, so the effect of letting summarizer prose
  reach the judge is measured, not assumed.

### A2. Interface

```python
SUMMARY_LAYER = -1   # sentinel layer of a synthetic summary cell

def summary_mode(args: JudgeArgs) -> bool    # opts aggregate; "native" | "summary"
def collapse(name, cells_by_item, *, args, cache, spend, preflight, task_note, pos=None) -> Collapse
def gate_texts(cell: Cell, col: Collapse | None) -> list[str]   # A5
```

`Collapse` fields:

| field | meaning |
|---|---|
| `cells: dict[str, Cell]` | one synthetic Cell for every item passed in |
| `evidence: dict[str, tuple[str, ...]]` | per item, the evidence samples (whole samples / whole token lines) |
| `statements` | for audit |
| `summaries` | the rendered text |
| `unsummarized: set[str]` | |
| `empty: set[str]` | |
| `truncated: set[str]` | |
| `diag` | `n_bundle_tokens_est`, `n_evidence_kept`, `n_evidence_dropped`, `n_items_all_dropped` |

**Synthetic cell.** `Cell(id, layer=SUMMARY_LAYER, pos=<pos of the item's last selected cell,
unless the family passes pos=>, samples=(rendered_summary,), tokens=None, scores=None,
token=<that cell's token>)`.
- Copying the last cell's `pos` and `token` keeps the families' post-selection lookups valid:
  relational's `'s` check and MCDM's non-null token.
- knowledge_cutoff passes `pos=-1`.
- After the hook, `rep.kind` is set to `"prose"`, so the family's per-cell token-summarizer branch
  is skipped. The file's real kind is recorded as `source_kind`.

**Where families call it.** Each family calls `collapse` after its own cell selection AND
missing-cell accounting, and before building `Call`s or running its regex. "Relevant positions"
means whatever the family already selects. Introspection and directed_modulation_obscure build or
score inside their selection loop today; they are restructured to select first, then account,
then collapse, then judge.

**Item states in summary mode.** These are stated once and every family follows them.

| item situation | handling |
|---|---|
| **No real cells** (no row at any selected layer) | Not passed to `collapse`. It keeps the family's native path for a wholly missing item: undecided in basic/multitoken, no row in DMO/KC/introspection, and whatever each family does today. |
| **Some selected cells missing** (`allow_missing=True`) | Collapsed from the cells it has, then follows **the family's own native rule for an item with a missing cell**. Principle: summary mode never changes a family's denominator rule. Known rules: tri-state families (`pass_rate_result` users: basic, multitoken, chain, arithmetic, DM-obscure, KC, MCDM) use `tri_state(pass, incomplete=True)`; the six binary scorers keep a non-pass as a fail; **introspection** is a fail unless nothing was judged (`_row`, `introspection/judge.py:305-334`); **conjunctive_association** excludes the item from the denominator (`judge.py:91-99`), unchanged. The same principle governs unsummarized items (next row) in introspection and conjunctive. |
| **Unsummarized** | The digest call failed, returned unparsable output, or **every returned item failed the evidence check** (an instrument failure, not an empty readout). It follows the family's native rule for an unjudged unit. In the tri-state families (`pass_rate_result` users) it is undecided. In the six Camila-nine scorers with a whole-scope binary denominator (jailbreak, user_modeling, moral, relational, role_bound, conjunctive) it counts as a fail and is counted in `n_unjudged`, exactly as native counts an unjudged cell. Reported separately in `extras.summary`. |
| **Empty** | Every cell is blank, or the digest returned **zero** items. A judged fail with no judge call, through the family's existing empty-cell path, fed by the synthetic `("",)` cell. A zero-item digest of a non-blank bundle is the summarizer's verdict, so it is counted separately (`n_digest_zero_nonempty` in `extras.summary`) and gated in D2. |

**Counts.**
- `n_expected` and `n_missing` are computed on the real cells before the hook, exactly as native,
  so `require_cells` exits 2 or allows missing exactly as native.
- `n_unjudged` counts unsummarized items plus failed judge units on synthetic cells.
- `n_empty` counts empty items.
- **Completeness.** `results.completeness` gains `n_items: int | None = None`. When it is given,
  the 5% empty rule is taken against `n_items` instead of `n_expected`. Native callers pass
  nothing and are unchanged.
  - It is threaded through `family.pass_rate_result` (new kwarg `n_items`) and the seven direct
    callers: `evals/{user_modeling,role_bound_association,relational_multihop,moral_rationale,
    jailbreak_recognition,directed_modulation,conjunctive_association}/score.py`.
  - `extras.summary.count_units = {"expected/missing": "cells", "unjudged/empty": "items"}`
    records the mixed units.
- **Per-cell counting families.** user_modeling, jailbreak, relational, moral, role_bound and
  conjunctive count `n_expected = len(cells)` and `n_empty` from non-empty cells. They follow the
  rules above: expected stays cell-level, and empty/unjudged become item-level.

### A3. Bundle, summarizer call, prompt (`DIGEST_PROMPT_VERSION = "digest-v1"`)

**Bundle.**
- **Order and headers.** Cells are sorted by `(layer, pos)`. Each cell gets one header,
  `[L44 pos 33]`, carrying the layer and position index only. The header **never** contains the
  read-site token text, because the summarizer must not see the prompt.
- **Prose cells.** One line per non-blank sample, `- <text>`, with internal whitespace collapsed
  so each sample is a single line.
- **Token cells.** One line per cell: the tokens best first, **byte-level-BPE decoded** with a
  shared `decode_bpe()`, joined by `" | "`, with no scores.
  - `decode_bpe()` inverts `bytes_to_unicode`, so `åĵªä¸Ģä¸ª` becomes `哪一个`, and turns `Ġ`/`▁`
    into a space. A string that is not valid UTF-8 after decoding is kept as written, which
    covers already-decoded text.
  - Rank order carries prominence.
  - hallucination and jlens_concept_pr keep their private decoders; native behaviour is
    byte-identical.
- **Size cap `summ_token_cap`.** Set via opts; the default is 150 000 *estimated* tokens. The
  script-aware estimate is ⌈ASCII chars / 4⌉ + non-ASCII chars × 1.0. CJK runs about one token
  per character, so it is not divided. The cap sits well under Opus 5.5's window, leaving room for
  the system prompt and output. When a bundle is over the cap:
  1. Keep sample 1 of every cell.
  2. Add samples 2, 3, … round-robin across cells while still under the cap.
  3. If sample 1 of every cell is already over the cap, keep within each layer every s-th cell,
     with s = 2, 3, … the smallest stride that fits. Each layer always keeps its first cell, so
     every layer stays represented.

  Truncated items are counted (`n_truncated_items`) and flagged in their row
  (`summary_truncated`).
- **Expected cap hits.** Measured on s3d, the cap should hit jailbreak_recognition (median 147k,
  max 1.46M chars), introspection (max 360k chars) and CJK-heavy J-lens bundles.

**Call.**
- **Model.** `summ_model=`, else **`claude-opus-5-5`**. It is not the judge model, by Camila's
  choice of default. The digest has its own aux role name, `aux_models["digest"]`, so overriding
  `aux_models["summarizer"]` (the per-cell interp-v1) never changes it.
- **Effort.** `reasoning={"anthropic_effort": "default"}`, i.e. the model's own default effort,
  not the repo's low-effort default. Ranking prominence over a ~100k-token bundle is the
  instrument of record. `summ_effort=low|medium|high|default` overrides it.
- **`max_tokens`.** 16 000, the Anthropic route default, so thinking cannot starve the answer.
  Thinking-token use is measured in D2.
- **Determinism.** Temperature is not sent; the Anthropic route drops it anyway.
- **Consistency.** The same `(model, reasoning)` pair is used in the preflight key, the
  fingerprint and the pinned rule.

**Variants.** `summ_variant=blind|task`. The default is chosen in D2, and `blind` wins a tie.

System prompt (both variants):

```text
You are a note-taker for an interpretability benchmark. You are given raw readouts from an activation lens applied to a language model while it read a passage you cannot see. The readouts are grouped by layer and token position ([L<layer> pos <index>]); each group holds one or more samples: free-text generations (one per line), or one ranked list of the lens's top vocabulary tokens, best first.

Write a faithful, compressed digest of what the readouts say. You are a passive recorder, not an analyst:
- Report only content that is present in the readouts. Do not interpret it, infer what the passage or the task is, answer any question, translate, or add knowledge of your own.
- Rank by prominence: content stated by many samples, at many positions, or at several adjacent layers comes first; content that appears once comes last or is left out.
- Use the readouts' own words. Copy names, numbers, specific terms and non-English words exactly as written, misspellings included. Never generalise a specific term into its category, and never sharpen a category into a specific member.
- Keep attribution and stance: who wants, believes, says or does what, and whether a claim is asserted, denied or merely mentioned.
- Do not combine separate readouts into a claim that no single readout makes.
- Token lists are noisy: ignore byte fragments and formatting debris, but keep every whole word that recurs.

Return up to {max_items} items, most prominent first. Each item has: "statement" (one short line in the readouts' own terms), "support" (one of "many", "several", "few", "one": how many samples carry it), and "evidence" (one span copied character for character from ONE sample or ONE token list, that shows the statement).
```

- **`task` variant.** Appends one line: `The readouts come from an eval of this type: {task_note}.
  Use this only to tell content from noise; do not use it to guess or answer anything.`
  - `task_note` is a neutral one-sentence description of the family's task TYPE. It never contains
    the item's prompt, options, targets or gold.
  - Each family holds it as one constant, `DIGEST_TASK_NOTE`, in its `prompts.py`. Example for
    basic_readout: "the model reads a short passage that implies a single concept it never
    writes".
  - `blind` sends no note.
- **User message.** `READOUTS:\n{bundle}`.
- **Schema `digest`.** `{"items": [{"statement": str, "support": enum(many|several|few|one),
  "evidence": str}]}`, truncated to `summ_max` (opts, default 10). Prompts are rendered with
  `str.replace`. They live in `digest.PROMPTS` and are printed verbatim in `docs/summarizer.md`.

### A4. Evidence grounding

- **Verification.** Each item's `evidence` is checked mechanically against the bundle lines with
  the bank judge's matcher. `basic/judge.py:_in_sample` moves to `family.py` as `span_in`, and
  `basic/judge.py` imports it back, so native behaviour is identical. `span_in` tries exact, then
  whitespace- and case-normalised, then alphanumeric fold.
  - **Prose cells:** the span must match inside ONE sample.
  - **Token lines:** the span must match inside ONE token, or be a run of whole tokens taken from
    one line. It is matched per `" | "` piece, so `fence | post` never verifies "fence post".
- **The evidence sample.** For each verified item, the evidence sample is the whole bundle line
  that contains the span (A1).
- **Failed items.** An item whose evidence fails is dropped (`n_evidence_dropped`). If every
  returned item drops, the item is unsummarized (A2), not empty.

### A5. What the judge is told, and what gates check

- **Gates.** In summary mode, every family gate that checks the judge's quote, numeral or regex
  hit against "the samples" calls `digest.gate_texts(cell, col)`. It returns the item's evidence
  samples as separate samples. For a token line it returns the line's individual tokens, each as
  its own sample, which matches how native mode treats each token as a sample (`cell_samples`).
  The gates covered:
  - basic `quote_verified`;
  - chain / MCDM / multitoken-MC `quote_in`;
  - arithmetic `verified()` and `names_number`;
  - knowledge_cutoff's quote + regex-forms check;
  - introspection `quote_verified`;
  - directed_modulation's evidence gate;
  - jailbreak's recognition-quote flag.

  Under `extractive`, every judged line is a verbatim readout sample, so the judge has nothing
  else to quote. Under `abstractive`, the judge's quote must still come from an evidence sample.
- **Every summary-mode prompt variant** includes `SUMMARY_NOTE`:

  ```text
  The readout below is a digest of the lens's readouts across every read layer and position: a note-taker who did not see the passage picked the most prominent readout samples, most prominent first, and marked how many samples carried each ([many], [several], [few], [one]). Each line is one real readout sample (a free-text generation, or one ranked list of top tokens). Treat each line as a separate sample: pieces on different lines never combine. Any quote must be copied from inside one line, without the bracketed marker.
  ```

  The `abstractive` variant uses `SUMMARY_NOTE_ABSTRACTIVE`. It says the statements are the
  note-taker's words, not evidence, and that a quote must be copied from inside an evidence span.
- **Regex-scored families** (multitoken, directed_modulation_obscure) and knowledge_cutoff's
  token-row regex call `gate_texts(cell, col, joined=True)`. This returns every evidence sample
  whole, and for a token line BOTH its individual tokens AND the line space-joined (the
  `token_bag_text` form). Multi-word targets (`New York`, `Kirin 9100`) therefore stay reachable
  on J-lens arms, as they are natively, where the multitoken token path also scores an interp-v1
  prose summary; the joined line is the summary-mode analogue. A sample naming both units still
  hits both. Quote gates use the default per-token form.
- **Decoding confound.** The bundle BPE-decodes tokens, while native judges see the raw byte form,
  so a J-lens delta mixes summarizing with decoding. `summ_decode=false` (opts) renders tokens the
  native way (`Ġ`→space only). D3a runs the J-lens summary arms both ways so the two causes can be
  separated.

### A6. Cache, provenance, instrument identity

- **Cache key.** `digest:{id}|{layers_tag}` in the family's `<out>/cells.jsonl`. The fingerprint
  is `(DIGEST_PROMPT_VERSION, model, reasoning, variant, max_items, token_cap, task_note or "",
  bundle_text)`. The render does not enter the fingerprint: one digest serves both renders.
  - Judge-call keys built on `SUMMARY_LAYER` (`id|L-1`) cannot collide with native keys.
  - Every family that parses a layer back out of a key with `int(...)` must handle `-1`. The
    per-family tests check this.
- **Separate `out=` dirs.** Native and summary runs need separate `out=` dirs, because
  `results.json` is overwritten and `_previous_mc` would carry a summary result into native
  extras. The README says so.
- **Provenance.** Each summary-mode result records:
  - `config.aggregate = "summary"`;
  - `config.summarizer = {model, reasoning, prompt_version, variant, render, max_items,
    token_cap}`;
  - `config.source_kind`;
  - `prompt_version = f"{PV}+{DIGEST_PROMPT_VERSION}-{variant}-{render}+{SUMMARY_JUDGE_VERSION}"`.
    `SUMMARY_JUDGE_VERSION = "sj-v1"` versions the summary-mode judge prompt variants and is
    bumped on any `SUMMARY_NOTE*` or variant-line edit. This follows the moral `contrast-off`
    precedent.

  Diagnostics go in `extras.summary`, never in `counts`, which has fixed keys.
- **Pinned.** In summary mode, `pinned_instrument` is true iff the family judge is pinned AND the
  digest uses the default model at the default effort.
  - In regex families the instrument is the digest: `judge_model` is the digest model and pinned
    follows the digest.
  - multitoken `judge_used` = `summ_model` and `version` =
    `digest.prompt_version(SCORER_VERSION, args)` (the format above), set explicitly. This must
    not come from the `rep.kind` branch.
- **Preflight.** Options are validated once, in `runner.run_families` before any thread starts,
  and in `cli.judge`. An unknown `aggregate`, `summ_variant`, `summ_render` or `summ_effort`
  exits 2. `runner._seed_preflights` adds the digest `(model, reasoning)` under `aggregate=summary`,
  regex families included.
- **Floors.** `report` / `markdown_table` print `—` (the code's em dash) in the floor columns of a
  row whose `config.aggregate == "summary"`. The lucky-guessing and prompt-only stamps compare
  against the registry's `prompt_version`, so the suffix alone would not hide them.
- **Dry run.** `dry_run=True` prints the first item's digest prompt and returns.

## Part B: per-family integration

Every family in the table gets the hook. Conventions for the table:
- **"Prompt variant"** is a summary-mode replacement for a line that describes the input as one
  layer, one position, or raw samples. It goes into the family's `PROMPTS` (so it is printed in
  the README) and is used only in summary mode. `SUMMARY_NOTE` / `SUMMARY_NOTE_ABSTRACTIVE` /
  `DIGEST_TASK_NOTE` are in each hooked family's `PROMPTS` too.
- **Per-layer and per-position diagnostics are omitted in summary mode.** They would be nonsense:
  - `layer_protocols`, `earliest_layer`, `per_layer_hit_rate`, `pass_at_1`;
  - MCDM `capacity`, chain `null_top1_near`, the `any_of_grid_floor` extras;
  - knowledge_cutoff `per_layer_rate` / `hits_by_layer` / `regex_reply_start_by_layer`;
  - jailbreak `by_layer` / `by_pos_idx` / `rel_slot` profiles.
- **Item rows gain** `summary`, `summary_statements` and `summary_evidence`.

| family (group) | hook point | judged unit in summary mode | prompt variant | notes |
|---|---|---|---|---|
| association, basic_readout, multihop, multilingual, poetry, typo, wrong_bridge, wrong_bridge_true (`basic/family.py`) | after `require_cells` (`basic/family.py:63`) | One bank-judge call per item on the summary. `_item_row` uses `layers=[SUMMARY_LAYER]` and takes `incomplete` from the item's real missing cells | `SYSTEM` line 2 ("…readout samples at one layer (several token positions)…") gets summary wording. `BLOCK` becomes the summary with no position header. `KIND_NOTE_*` becomes `SUMMARY_NOTE` | Family rules and forbidden lines unchanged. The stance and candidate-list rules still apply, because the judge sees whole samples. Quote gate via `gate_texts` |
| basic_readout_mt, multihop_mt (superseded), multihop_mt_v2, multilingual_mt, multilingual_multihop, multilingual_typo, typo_mt (`multitoken/family.py`) | after `require_cells` (`:143`) | The regex contract runs on `gate_texts` as the samples of one layer. `opts=judge=mc`: one MC call per (item, unit) on the summary, gated by `gate_texts` | MC path: the `USER` sample header becomes `SUMMARY_NOTE` | **Same-layer conjunction is relaxed by design.** "Every required unit at one layer" becomes "every required unit among the item's evidence samples". Camila asked for exactly this pooling, and the README states it. The digest does not translate, so an L2-only echo cannot gain an English form |
| arithmetic_intermediates | after selection (`judge.py:205`) | **Summary mode forces `cells=all`.** An explicit `cells=frozen` with `aggregate=summary` exits 2, because the frozen cell is a sweep-picked best cell and the user asked for every position and layer. One call per item using the single-cell `SYSTEM`/`USER` | The `USER` sample header becomes `SUMMARY_NOTE` | `verified()` on `gate_texts`. A pooled summary offers more numbers to the ≤3-value cap (`MAX_VALUES` unchanged), but the paired `cross` null is computed on the same summaries under the same rule, so the floor moves with it (README says so). A method with no arithmetic layers (e.g. `layers=44` on the current readouts) is "not defined" |
| chain_intermediates | after `require_cells` (`:121`) | One call per item, **forced `cells=all`** (Goal) | `SUMMARY_NOTE` header | **Summary-mode item rule: any of the judge's ≤3 verified values is gold**, not top-1. This is the existing `any_of_3` diagnostic with every value verified. Pooled over 11 layers, the loudly stated final answer would otherwise win the top slot by construction. The near-decoy null uses the same any-of-3 rule. `names_number` / `quote_in` on `gate_texts` |
| conjunctive_association | replaces `build_blob` | One MC call per item (already one per item) | `SYSTEM` "possibly labeled by layer" becomes `SUMMARY_NOTE` | Already one judgment per item, but over the raw all-layer blob. Hooked anyway, because Camila asked for a summarizer step before every judge |
| directed_modulation | after `require_cells` (`:139`) | One call per item | `USER` lines 20-23 ("at a single token position …") become `SUMMARY_NOTE` | white_bear pairs kept. Evidence gate on `gate_texts` |
| directed_modulation_obscure | restructured: collect, account, collapse, then loop (scores inside the per-item loop at `:146-157` today) | Regex `cell_hits` on `gate_texts`. Floor = the distractor rate on the same `gate_texts` | n/a | The instrument becomes the digest (A6) |
| introspection | restructured: select and account for all units first (`Call`s are built inside the loop at `:196-223` today, before `require_cells`), then collapse, then build calls | One call per unit on the summary of the unit's `readout_of` item. A summary is shared across units that read the same readout. beta0 / cross / gaussian control units get the same treatment, so the floors stay paired | `SYSTEM` "one internal activation … readout samples for that activation" becomes `SUMMARY_NOTE` | Quote gate via `gate_texts` (per-token for token lines, like `quote_units`) |
| jailbreak_recognition | after `_check_tokens` (`:170`) | One call per item | `build_user` without ⟦HERE⟧ / "after the token …" | The recognition-quote flag checks `gate_texts` |
| knowledge_cutoff | after cell build (`:113`), `pos=-1` | One call per item. `pick_layer` / `best_layer` is skipped explicitly: it is a pass@layer | `SYSTEM` / `fmt` "decoded at every token position … grouped by position" becomes `SUMMARY_NOTE` | `full_span` / `partial` come from the real groups. `ati_pass` is **omitted** in summary mode: it feeds the ATI gate machinery, which must never gate on a summary-mode result. `named_gold` comes from the real reply_start cells, OR over layers (diagnostic only). Quote check on `gate_texts`; token-row regex on `gate_texts(joined=True)` |
| moral_rationale | after `select_cells` (`:180`) | committed: one call per item. deliberative: one call per side, both on the same summary | `SUMMARY_NOTE` | deliberative becomes "both sides in one summary" |
| multi_concept_directed_modulation | after `label_cells` / `expected` (`:119`) | One multi-select call per item, control items included, so `control_pick_rate` stays paired | `SUMMARY_NOTE` | `capacity` omitted. `quote_in` on `gate_texts` |
| relational_multihop | after selection (`:107`) | X and Y calls on the one summary | The `BUNDLE` `[position …]` header becomes `SUMMARY_NOTE` | The cell-level X∧Y binding becomes summary-level. This is by design, and the README notes it |
| role_bound_association | after load (`:57`) | Three MCs on the one summary | `SUMMARY_NOTE` | Same binding note |
| user_modeling | after load (`:109`) | One call per item | `UM_ATTRIBUTE_USER` "at the position where …" becomes `SUMMARY_NOTE` | `pass_at_1` omitted |

**Not under the hook.** These families run native even when `aggregate=summary` is passed. Each
records `config.aggregate = "native"` and a one-line `extras.summary_mode_note` with the reason,
and the README lists them.
- **`hallucination`.** The metric is per-readout precision (hallucinated / specific). A summary
  adds and drops claims, which is what this family measures.
- **`jlens_concept_pr`.** It measures precision against the J-lens top-10 at the same
  (layer, pos). There is no reference for a summary.
- **`brew_intermediates`.** The count rule `K·G > ΣO` over emission cells, plus the paired stir
  control, would degenerate on a single summary. Follow-up: per-region summaries. **Product
  decision for Camila.**
- **`agentic_misalignment`.** It is already summarize-then-judge (Stage A/B/C), and its metric is
  a graded mean, not an OR.
- **`buggy_code`.** The read plan produces one sweep-picked layer per language, so there are no
  other layers to summarize. Its blind INFER stage is itself a summarizer. **Product decision for
  Camila:** removing the layer pick needs a read-plan change.

## Part C: plumbing and reporting

- **C1. Options.** All settings go through `opts=`: `aggregate`, `summ_model`, `summ_variant`,
  `summ_render`, `summ_effort`, `summ_max` and `summ_token_cap`. They are validated once (A6).
- **C2. Reports.**
  - In `report` / `summary.md`, a summary-mode row is suffixed `†`, with the legend
    "† summarize-then-judge (one judged summary per item)". Its floors print as `—`.
  - `macro` over a summary run excludes native-only rows with the reason
    `"native under aggregate=summary"`, so the macro never mixes the two. The usual `complete`
    gate still applies.
- **C3. Docs.**
  - `docs/summarizer.md` gets a new section, "§ Item digest (aggregate=summary)". It covers both
    renders, the digest prompt verbatim (both variants), the schema, cache key, cap rule, decoder,
    evidence gate, `gate_texts`, and the item-state table.
  - Each hooked family's README gets a "Summary mode" paragraph: the hook, the judged unit, the
    prompt variant verbatim, and the binding note where relevant.
  - README §Judges gets one paragraph.
- **C4. CLAUDE.md** (agent runbook) gets a Family-conventions bullet covering `digest.collapse`,
  the hook-after-accounting rule, the item states, and `gate_texts`.

## Part D: tests, dev iteration and validation

### D1. Offline tests (CI)

`tests/test_digest.py` covers:
- **Bundle:** order and headers (no token text); prose newline collapse; BPE decode
  (`åĵªä¸Ģä¸ª` becomes `哪一个`; already-decoded `café` is kept); the token estimate.
- **Cap:** round-robin, then stride; every layer kept.
- **Evidence:**
  - a verbatim span in one sample passes;
  - whitespace and case variance passes;
  - a span across two samples fails;
  - `fence | post` does not verify "fence post";
  - the evidence sample is the whole line.
- **Item states:**
  - zero returned items → empty → fail;
  - every item dropped → unsummarized;
  - failed call → unsummarized.
- **Rendering:** extractive vs abstractive; extractive never contains a statement.
- **Cache and fingerprint:** the cache key is distinct from `summ:`; the fingerprint changes with
  variant / model / effort / max_items / cap / bundle, but not render.
- **Options:** unknown option values exit 2.

One summary-mode test per integration group: basic, multitoken, conjunctive, chain, DM, DMO,
arithmetic, introspection, jailbreak, KC, moral, MCDM, relational, role-bound and UM. These
monkeypatch `digest` and `run_calls` as the existing family tests do, and assert:
- exactly one judged unit per item (per side or unit);
- `n_expected` / `n_missing` equal to native;
- the `prompt_version` suffix and `config.aggregate`;
- no per-cell token summarize call on a token file;
- a quote absent from every evidence sample fails its gate;
- an item with a missing cell and no pass is undecided (tri-state families) or a fail (binary
  ones);
- an item with no cells keeps its native path.

Specific cases:
- arithmetic: `cells=frozen` with summary exits 2.
- KC: `partial` comes from the real cells.
- multitoken: a sample naming both units passes the conjunction.

Other tests:
- The five native-only families give results identical to native apart from the config/note.
- `completeness(n_items=)`.
- `—` floors on † rows.

**Sanctioned edit to a pre-existing test:** `tests/test_prompts_in_readme.py` gains one assertion
that `digest.PROMPTS` appears verbatim in `docs/summarizer.md`, mirroring the existing
`test_summarizer_prompt_verbatim_in_docs`. This is the ONLY permitted pre-existing-test edit.
Native mode stays byte-identical, so no other existing test or golden changes. The one sanctioned
non-test move is `_in_sample` → `family.span_in`.

CI: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`.

### D2. Summarizer dev iteration (live, small)

**Dev slice.** Items 0-19 (bank order) of every hooked family.
- Source: s3d-rl600 readouts (`/workspace/root/wsbench-pub/outputs/readouts/s3d-rl600`).
- Families absent there (jailbreak, introspection, knowledge_cutoff,
  directed_modulation_obscure, wrong_bridge, wrong_bridge_true, multihop_mt_v2) come from
  `/workspace/root/wsb-ati-runs/readouts/s3d`, using whatever items exist, up to 20.
- All layers, judge `claude-opus-5-5`.
- Dev items are **excluded from every D3 headline table** (D3a, D3b and D3c), and a dev-inclusive
  line is shown for reference. A family contributes a dev slice only if it has ≥ 60 items, so
  the slice never eats a small family's set.

**Variants.** `blind` and `task`, each at `summ_max ∈ {10, 25}`. Both renders come from the same
digests.

**Selection criterion, fixed in advance.** Fidelity only, never score.
1. **Passivity audit.** A separate Opus 5.5 auditor sees each digest item beside its bundle (no
   prompt, no gold). It flags any item whose statement interprets, infers the task, answers,
   translates, generalises, sharpens, combines separate readouts, or changes attribution or
   stance. The threshold is ≤ 2% of items.
2. **Unsummarized + evidence-drop rate.** More than 15% on any family is a prompt/format problem
   to fix before D3.
3. **Read-through.** Read 3 digests per family per variant by hand.
4. **Effort and cost.** Thinking-token use, output tokens and `max_tokens` stops are recorded.
   They feed the cost estimate.
5. **Coverage (gold-free).** Recurring content is the set of word types (casefolded, ≥ 3 chars,
   not in a fixed stopword list) that occur in ≥ 3 samples spanning ≥ 2 layers of the bundle.
   Coverage is the share of those types present in the evidence samples.
6. **Zero-item digests.** `n_digest_zero_nonempty` counts toward the 15% gate in (2).

**Decision rules (fixed now).**
- Variant: `blind`, unless it fails (1) or (2) and `task` passes.
- `summ_max`: 25 iff it raises mean coverage by ≥ 10 points while (1) and (2) still pass; else
  10.
- Render: `extractive`, by construction, since no summarizer text then reaches the judge.
  `abstractive` is reported as an ablation only, never chosen on score.
- The `[support]` markers stay: prominence is part of the summary Camila asked for ("prioritize
  concepts that come up often").

Scores are reported but are never an input to these choices. A prompt edit bumps `digest-v2` and
the slice is re-run.

### D3. Validation (live)

**Setup.**
- Every run, native and summary, is at this PR's HEAD with `judge_model=claude-opus-5-5` and `ant`
  profile auth, in its own `out=` dir per (method, mode, render).
- **No existing judged results are reused.** `wsb-ati-runs/judged` predates #96/#98: the old
  regex cutoff scorer and arithmetic `cells=frozen`.
- **Arithmetic and chain** run as their own invocation with `opts=cells=all` in BOTH modes:
  `opts` is global, and summary mode forces `all` anyway, so native is made to match.

**`scripts/summary_mode_compare.py`** builds the per (family, method) table:
- **Rates.** Native and summary rates on decided items over the same item set, minus the dev
  slice. It **asserts** that each pair's `prompt_version`s match an explicit per-family table of
  expected (native base, summary base), and that the non-summary opts are identical. Examples:
  arithmetic `arith-free-batched-2026-09-23` (native) vs `arith-free-2026-09-23+digest…`
  (summary); multitoken token files `SUMMARIZED_SCORER_VERSION` vs `SCORER_VERSION+digest…`.
- **Uncertainty.** A paired bootstrap 95% CI of the difference.
- **Retention**, for the gated families. Among native-pass items, the share whose native hitting
  sample (the sample containing the native verdict's verified quote, or the regex-hitting sample)
  (a) survived the token cap and (b) is among the summary's evidence samples. This separates "the
  summarizer dropped the hit" from "removing the OR removed a lone-outlier hit".
- **No macro or `complete` gate.** Overridden judges make `pinned=False` and `is_subset` makes
  single-layer methods incomplete; the report states both.

**D3a: matched trio, ATI scope** (`anti_text_inversion=True`).
- Readouts: `/workspace/root/wsb-ati-runs/readouts/{s3d,mlnla2k,jlens}`.
- Six methods, each its own entity, with no cross-method claim from an all-layer row: s3d, mlnla2k
  and jlens × (all layers, `layers=44`).
- Native and summary (extractive) for each.
- A family not covered for a method is reported as "not defined" from the coverage counts.

**D3b: full banks, s3d-rl600.**
- Readouts: `/workspace/root/wsbench-pub/outputs/readouts/s3d-rl600`, the 24 families with full
  grids.
- Two methods: all layers and `layers=44`.
- Modes: native, summary-extractive, and summary-abstractive (the ablation, all layers only).

**D3c: full banks, newer families.**
- Readouts: `/workspace/root/wsb-ati-runs/readouts/s3d`, for the hooked families absent from
  s3d-rl600 that have full readouts there: directed_modulation_obscure, knowledge_cutoff,
  introspection, wrong_bridge and wrong_bridge_true. knowledge_cutoff's readouts are legacy
  3-offset, so it is `partial` in both modes, as the report states.
- Methods: all layers and `layers=44`. Modes: native and summary-extractive.
- **Cannot be validated, because no full readouts exist:** jailbreak_recognition (5 items) and
  multihop_mt_v2 (1 item). The report lists them as such; producing readouts is out of scope.

**Catastrophe flag.** Raised only with n ≥ 20 decided items in the pair (`ATI_MACRO_MIN_ITEMS`),
when ANY of these holds:
- summary < 0.5 × native with the paired CI excluding 0;
- native − summary > 0.30 absolute;
- summary at or below the family's per-call chance.

Smaller pairs are reported as "n too small to flag". Families with too few ATI items are flagged
from D3b or D3c only.

**Two-sided audit** for every family with n ≥ 20, flagged or not:
- Read up to 10 native-pass / summary-fail items and up to 10 summary-pass / native-fail items:
  the summary, evidence, statements and judge output.
- Classify each as: summarizer dropped the target / distorted it / judge stricter on the format /
  judge more lenient / leak (a pass not grounded in readout content) / genuine (a lone-outlier hit
  that pooling correctly removes).
- Run the D2 passivity auditor on a 200-digest random sample of D3 digests.

**Report.** `docs/summary_mode_validation.md` in the PR: the tables, CIs, retention, the flagged
list with audit counts, the extractive-vs-abstractive ablation, the D2 variant comparison, and the
not-defined list.

**Logistics.** One named tmux session (`wsb-summ`) runs the arms sequentially in one command,
logging to `logs/summary_validation_<timestamp>.log`.

**Cost.** Digests are about 18M input tokens for s3d all layers over 24 families, more for
CJK-heavy J-lens bundles (estimated with the script-aware count). Single-layer methods are about
1/11 of that. Native Opus re-runs dominate the judge cost, mostly user_modeling and
directed_modulation per-sample calls, about 50k calls per method.

## File tree (new / modified)

```
plans/0020-summarize-then-judge.md          new (this plan)
src/wsbench/digest.py                       new: collapse, bundle, decode_bpe, cap, evidence,
                                            renders, gate_texts, prompts
src/wsbench/family.py                       span_in (moved from basic/judge.py); pass_rate_result n_items
src/wsbench/runner.py, cli.py               option validation, digest preflight, floors —
src/wsbench/results.py                      completeness(n_items=), † marker, macro exclusion
src/wsbench/basic/{family,judge,prompts}.py hook + gate_texts + prompt variants
src/wsbench/multitoken/{family,prompts}.py  hook + prompt variant + instrument stamp
src/wsbench/evals/<15 hooked families>/…    hook + DIGEST_TASK_NOTE + prompt variants (+ score.py
                                            n_items for the seven direct completeness callers)
src/wsbench/evals/<5 native families>/…     summary_mode_note only
docs/summarizer.md, README.md, CLAUDE.md    docs
evals/<family>/README.md                    "Summary mode" paragraphs
tests/test_digest.py, tests/test_summary_mode_*.py   new
tests/test_prompts_in_readme.py             one sanctioned assertion (digest.PROMPTS)
scripts/summary_mode_compare.py             new (D3 table, paired CI, retention)
docs/summary_mode_validation.md             new (D2 + D3 results)
```


## Rev 5 amendments (critique round 4) — these override any conflicting line above

- **Digest schema:** items are `{statement, where, evidence}`. `where` is the `[L<layer> pos <i>]`
  header of the group the evidence comes from; the prompt's last paragraph asks for it and says
  to copy whole tokens from a token list. The summarizer no longer writes `support`.
- **Evidence resolution** (`digest.evidence_line`): first within the group `where` names, then
  anywhere; within a scope the strongest match level wins over bundle order — prose: exact >
  whitespace/case-normalised > folded; token line: a whole token or a run of whole consecutive
  tokens (normalised equality) > a span inside one token. Never a span across tokens.
- **Support is mechanical** (`digest.support_of`): the number of bundle samples containing the
  verified evidence (exact or normalised; a whole token for a token line), bucketed 1 = one,
  2-3 = few, 4-9 = several, 10+ = many. So under `extractive` no summarizer-written text at all
  reaches the judge (A1's claim now holds), while the prominence signal Camila asked for stays.
  Fingerprint additionally includes `decode` (A6).
- **Token-source judge note:** when `source_kind == "tokens"`, every summary-mode judge prompt
  appends `SUMMARY_NOTE_TOKENS` (one ranked list per `" | "` line; each token its own sample; a
  quote from such a line is exactly one token; the native `KIND_NOTE_TOKENS` rank-1 rule). Every
  family passes `source_kind` to `digest.summary_note(args, source_kind)`. Versioned under `sj-v1`.
- **Chain comparison:** `summary_mode_compare.py` pairs chain's summary rate (any-of-3) with the
  native **`any_of_3`** rate of the same items (already in every native row) for the catastrophe
  flag; native top-1 is a reference column only.
- **D2 selection-bias check (audit-only, gold-aware, never a score input):** per variant, the
  share of selected evidence samples that contain the item's gold (family matcher) divided by the
  share of gold-containing samples in the bundle. `task` may be chosen only if its ratio is ≤
  `blind`'s (the task note must not steer selection toward answer-like samples); the statement
  passivity audit (D2 (1)) stays as a check on the `abstractive` ablation.
- **Cap note:** "expected cap hits" are restated in estimated tokens in the PR's validation doc
  (jailbreak's median ≈ 37k est. tokens is under the cap; its max is not).
- **Retention (D3):** native hit samples are compared to evidence samples in decoded form, and a
  native-pass item counts as retained if ANY of its native hitting samples (any hitting layer) is
  among the evidence samples.

## Rev 6 amendments (digest-v2 / sj-v2, after the first D3 audit) — override conflicting lines above

Camila asked to iterate on the summarizer prompt. The first D3 pass (digest-v1, `blind`, 10 items)
and a two-sided audit of the flagged families (`docs/summary_mode_audits/01_user_modeling_introspection_v1.md`) found no leaks:
no item passed in summary mode while failing natively. It did find three instrument defects:

1. **The `[support]` marker was meaningless for prose.** It counted bundle samples containing the
   whole evidence clause, which is unique, so 98% of lines read `[one]`, and judges cited it to
   dismiss evidence. **Fix:** each digest item carries a `key` (1-4 words copied exactly from the
   evidence, verified inside it, falling back to the evidence itself). Support is counted on the key
   as whole words, or as whole tokens for a token line.
2. **Slots were wasted.** In introspection, chain and user_modeling, the 10 slots filled with
   near-duplicates and restatements of the input's own instructions ("only output the final
   number"), so content that recurred less often (the intermediate value, the injected concept) was
   dropped. **Fix:** two task-agnostic rules are added to the digest prompt: every item reports
   different content; restatement of the input's wording or instructions gets at most one item.
   Items are also de-duplicated mechanically by key. This stays passive: it says how to spend the
   item budget, not what the readouts mean.
3. **user_modeling's summary judge used a single-sample basis rule.** "A value in the prompt is
   almost certainly verbatim_echo", applied to a digest that pools echo lines with inferring lines,
   rejected inferences the judge could see: 39 of 63 lost items had the native hit in the digest.
   **Fix:** a summary-mode basis note (`SUMMARY_BASIS`): the basis is that of the line the pick rests
   on. This is the same any-line semantics every other summary-mode judge already has within its
   one call (e.g. the bank judge's "ANY target expressed in a sample"). It is not a pass@cell: the
   judge still reads one digest once.

Versions are `digest-v2` and `sj-v2`. The `summ_max` decision is re-taken under v2 with the same
pre-registered rule (25 iff mean coverage gain ≥ 10 points) on the D2 slice, `blind` only. Every
summary arm of D3 is re-run under v2. The native arms are unchanged and reused.

**sj-v3 (user_modeling only).** A second audit (`docs/summary_mode_audits/02_user_modeling_v2.md`) found that the
Rev 6 basis note dropped the native clause "unless it adds a characterization the prompt did not
state". As a result, judges labelled specific new content on system-prompt items "echo": "UK" for
"Europe", "Muslim" for "halal". sj-v3 restores that clause in `SUMMARY_BASIS`, and it is still one
judge call per digest. Synonyms of a stated label ("mom" for homemaker) are deliberately NOT
credited: native "inferred" credits them, so that part of the remaining gap is a difference in
what is measured, recorded for Camila. All other families' judge prompts are unchanged from sj-v2.

**sj-v4 (user_modeling only), replacing sj-v3.** A leniency audit of sj-v3 found 29 of 33
summary-pass / native-fail items crediting details native had rejected on the identical cell:
details about other attributes ("divorced *senior*"), and elaborations that change no value (a
pet's name, "a research station" for "in Antarctica"). The judge read the clause as "the line has
an extra detail". The lenient credit was also uneven across methods, because ML-NLA's invented
persona headers drew more of it. sj-v4 writes down native's unwritten test: only a more specific
value of THIS attribute (or naming an implied value, or generalizing an implicit cue) counts as
inference. Other-attribute details, value-preserving elaborations, synonyms and paraphrases leave
a restated value "verbatim_echo". The acceptance check: re-judge, and the remaining
summary-pass / native-fail items must be few and defensible, with no method-specific skew.

**sj-v5 (final review).** Three changes, all to rendering and wording:
- Key support counts CJK keys by plain substring; word boundaries never match inside CJK text, so
  those keys were stuck at `[one]`.
- The key check and the support count use the same accent folding.
- Key-duplicate skips get their own counter (`n_key_duplicates`) instead of counting as evidence
  drops.

user_modeling's basis note now says "quote from the line" (the native 200-character evidence limit
still applies). Every summary arm of D3 was re-run at sj-v5 with the digests reused, and the
validation report is generated from those runs.


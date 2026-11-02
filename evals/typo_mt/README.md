# typo_mt

A sentence ending in a misspelled multi-token word; the lens must write the corrected word.
**The hard typo family**: `typo` is superseded by it (plan 0033, Camila 2026-10-30: "drop this
from the macro, we don't need it, just keep the hard version").

**Status (plan 0033, 2026-10-30): bank v2, near ceiling for prose readers.** 85 items
(`items_v2.json`): v1's 100 minus the 15 arithmetic items (Camila: "Drop the arithmetic items";
header `dropped` lists them; `items.json` is the untouched v1 record). On the 85 word items the
frozen text-reader panel solves the correction from the prompt alone (pass@3): Qwen3.6-27B 71/85,
Opus 5.5 83/85, GPT-6 Astra 77/85, Gemini 4 Argon 83/85, and the cached prose lenses pass
84-85/85. It stays as the hard version by decision (Q11): **read every lens number against the
Opus prompt-only floor drawn beside it** (`po-opus-v1`, measured in the run phase; until then
`report` shows no floor — the 2026-09-23 stock-Qwen floor 0.67 was on the 100-item bank and is
archived, never drawn). What is left to discriminate is mostly token lenses vs prose lenses.
Not in the ATI subset (Camila: "This should not be in ati"; `_not_gated`).

Source bank `lens-eval-typo-hard.json`, parent `typo-mt`, frozen 2026-09-10; v2 frozen
2026-10-30. Plain render. **Read site** (plan 0033 M3): `reads=full` (default) reads the tokens
of the misspelled word that ends the prompt from the one holding the first character where
`typo_word` differs from `target` (case-insensitive) on (`suffix_text` of `typo_word` with
`from_char`: 1-4 tokens, 133 positions over the 85 items) and nothing earlier — an earlier
position, including a correct prefix of the word (` interpret` in `interpretibility`, ` acc` and
`iac` in `acciacatura`), would credit the lens for predicting the word, not correcting it;
`reads=lite` reads its final token (the pre-2026-10-30 site). Every item was gated on Qwen3.6-27B (greedy-verified, then >= 8/10 at temperature 0.7);
dropping other items does not touch that gate.

Example: "There's a really cool field in AI safety research called mechanistic interpretibility"
→ `interpretability` in one sample (full read: `ibility` only; ` interpret` is a correct prefix).

Scored units: `correction` (required; the corrected word and its listed aliases).

Known limitation (documented, not fixed — Camila: "Use regex"): the regex has no commitment
check, so a readout that names the correction while rejecting it (", not adsorption, ... the
precise term is absorption") still hits.

The bank file is a frozen copy of the source repo's hard-tier bank; its `contract` block, per-unit `forms` and `probe_token_lens` counts are exactly what the scorer reads.

## Scoring

- **Headline: regex pass rate** — `scorer_version` `mt-regex-2026-10-30+typo-v2` on prose readouts
  (`mt-regex-2026-10-30` = the shared contract with numeric answer markers in any case, plan 0033
  M2; `+typo-v2` = the v2 bank):
  deterministic, no judge call, `spend_usd` 0, `judge_model` `regex`. Token-bag readouts are matched as raw tokens under the
  same `scorer_version` (no interpretation call; the old `mt-regex-summarized-decoded-2026-10-27`
  path is deleted, plan 0032 §2.3). Under summary mode (the default) every method's readouts go
  through the one digest and the contract runs on its evidence samples, so the instrument is the
  digest model (`judge_model`, `pinned_instrument`, `spend_usd` follow it) and the version gains
  the digest suffix. The scorer is `wsbench.multitoken.regex`, a port of
  the source repo's conjunctive bank scorer (`olens_suite/bank/matching.py`, `contract.py`,
  `conjunctive.py`, `olens_sglang/score_targets.py`); goldens computed by the source code pin it
  (`tests/golden/mt_regex_units.json`, `tests/golden/mt_regex_matching.json`).
- **The contract, verbatim from the source:** (1) a cell's samples are its prose samples, or each
  top-k token string of a token lens; chat scaffolding (`<|im_start|>`, `<|im_end|>`, `<think>`,
  `</think>`, `<explanation>` tags) is stripped first. (2) The item's `units[]` are scored; under the
  bank's `multi_token` contract only forms the bank stamped as strictly multi-token stay
  (`probe_token_lens` > 1: the source's count is the minimum over case variants and bare /
  leading-space encodings, so a form any single Qwen3.6-27B token could equal never earns
  credit); units marked `multi_token: false` (the language units) keep every form. (3) A form hits
  a sample when, after folding both sides (NFKD, combining marks dropped, curly apostrophe
  straightened, casefold), a wordy form matches at word boundaries with `[\s-]+` between its words
  (`Bohr magneton` = `Bohr-magneton`; `kentes` is not `kente`), a form containing CJK or Hangul or
  non-word characters is a plain substring, and a purely numeric form must sit in answer position
  (after `=`, `->`, `equals`, `answer/result/value/total/sum/product/quotient [is][:]`, their
  Chinese counterparts, or alone at the start of the sample, never as a prefix of a longer number;
  a CJK numeral there counts when it parses to the value; the markers match in any case —
  `**Answer:** 429`, `Result: 429` — a deliberate deviation from the source, plan 0033 M2; no
  numeric form is left in this bank). A form is matched against ONE sample at a time — never a
  join of samples or of the tokens of one top-k list; the one exception (decision Q4) is a word
  spelled by tokens of ADJACENT positions of one layer, which hits as that word and is counted in
  `extras.n_split_word_hits` (per row `split_word_hit`). (4) A unit hits at a layer when any
  of its forms hits any sample at that layer, in any listed language. (5) A layer passes the item
  when EVERY required unit hits there; the item passes at any layer.
- **Scored units of this family:** `correction` (required; the corrected word and its listed aliases).
- **Token lenses — raw tokens natively, the one digest by default** (plan 0032 §2.3, Camila:
  "make sure that we have gotten rid of the individual jlens summarizer step, it should be
  replaced with the more general sumamrizer we apply to all methods now"). The per-cell J-lens
  interpretation step (`interp-v1-decoded`, `summ:<cell>` cache keys) is deleted. Natively
  (`opts=aggregate=native`) the contract matches each top-k token as one sample, so a required
  strictly multi-token unit is unreachable on a raw bag by construction (the source's stated
  asymmetry: "multi-token targets can only be hit by the oracle lens"); single-token units (a
  language name) and producers whose "tokens" are phrases or labels (the template lens, an SAE's
  auto-interp labels) stay scorable. Under summary mode the token lens goes through the same
  digest as every other method; a word split across adjacent positions of one layer reaches the
  contract as that word (`digest.gate_texts(joined=True, forms=)`), never a join of whole tokens
  or of different positions. Token strings are matched as the producer wrote them (`Ġ`/`▁` as a
  space).
- **Item rule:** an item whose every expected layer is scored and never passes fails; a cell whose
  samples are all blank is a negative at that layer; an item with a MISSING (item, layer) cell and
  no pass is undecided (`extras.n_items_undecided`). Every read position of a layer is pooled
  (the one-position refusal is gone, plan 0032 §2.16). Under `reads=full` a sidecar'd file must
  hold, per (item, layer), one contiguous run of positions (`min_full_positions=1`: the 16
  one-token misspellings have one), may not declare `reads: lite`, and must match
  `reads.plan_sha("typo_mt")` — else exit 2; a sidecar-less file is report-only
  (`extras.partial_ids_unenforced`). Missing cells are fatal (exit 2) unless
  `allow_missing=True`; `layers=` restricts the grid and counts as a subset.
- **Extras:** `n_split_word_hits` (passes that rest on a word split across adjacent positions),
  `any_hit_rate` (some unit hit somewhere — the parent-comparable number; Camila's
  2026-09-23 substring preview corresponds to this, not to the conjunctive pass), `unit_any_layer`
  per role, `language_of_readout` (which language each unit surfaced in first), and `mc` (the
  forced-choice judge's number when `out/results.json` still holds one, so both instruments sit
  side by side without a call).
- **Floors:** the prompt-only floor of record is the Opus `po-opus-v1` one
  (`evals/baselines/prompt_only_summary.json`), measured on v2 in the run phase and drawn only
  while `strip_reads(prompt_version)` matches; the 2026-09-23 stock-Qwen floor (100 items) is
  history. The MC lucky-guessing floor applies to `opts=judge=mc` only and is never drawn beside
  the regex number.

## Instrument history

- Source repo (bank frozen 2026-09-10): this regex contract was the headline
  (`score_targets.py --match word --exact`).
- 2026-09-16 -> 2026-09-23 (PR #20): a forced-choice Gemini judge (`mc-2026-09-16`) replaced it —
  one prompt-blind five-way call per (item, layer, unit) with a cannot-tell escape and a
  verbatim-quote gate. Values of record then: s3d-rl600 0.86, s3d-sft251 0.89, nla-rl-L42 0.74, template-v3 0.39.
- 2026-09-23, Camila: "regex on the multitoken please" — the regex contract is the headline again;
  on the same readouts: s3d-rl600 0.83, s3d-sft251 0.84, nla-rl-L42 0.75, template-v3 0.06. The MC judge stays reachable with `opts=judge=mc`
  (its result is never pinned, so never `complete` and never in the macro; its prompts are kept
  verbatim below).
- 2026-09-23 16:52, Camila: token-bag arms keep the LLM summarizer step (deleted 2026-10-30, below); on the same
  readouts, MC / regex-raw / regex-summarized: jlens 0.24 / 0.00 / 0.17; rlens 0.34 / 0.00 / 0.25; template-v3 0.39 / 0.06 / 0.30; logit 0.30 / 0.00 / 0.20; tuned 0.29 / 0.00 / 0.20; sae-l42 0.18 / 0.08 / 0.16.
- 2026-10-30 (plan 0032 §2.3): the 2026-09-23 16:52 token-bag summarizer step is deleted; token arms are
  matched as raw tokens natively and through the one digest under summary mode (the default).
  The `mt-regex-summarized-decoded-2026-10-27` numbers are not comparable to either.
- 2026-10-30 (plan 0033): bank v2 (85 items, arith dropped), full read = the misspelled word's
  tokens from the first misspelled character on (lite = its final token), numeric markers in any case, split words of adjacent
  positions counted, out of the ATI subset; instrument `mt-regex-2026-10-30+typo-v2`. On the
  cached final-token (= lite) readouts, 100 -> 85 items: rl-onchat-x4 89/100 -> 85/85, s3d
  87/100 -> 84/85, J-lens 21/98 -> 0/85 (the old 21 came from the deleted token-summarizer step; natively a
  one-token lite read cannot spell a multi-token correction), logit lens 23/100 -> 23/85 (all 15 arith items, and so
  all 11 non-word fails of the best O-lens, are gone).

## Readouts

`{"id": "<item name>", "layer": L, "pos": P, "samples": [...]}` rows; `tokens` rows for a token
lens. `examples/readouts/typo_mt.jsonl` is a toy file for `dry_run=True`.

```
wsbench judge family=typo_mt readouts=examples/readouts/typo_mt.jsonl out=outputs/toy/typo_mt dry_run=True
wsbench judge family=typo_mt readouts=<arm>.jsonl out=outputs/<arm>/typo_mt limit=3
```

## Summary mode (`opts=aggregate=summary`, plan 0020)

The default since plan 0024; `opts=aggregate=native` opts out to everything above. Under summary mode, for
each item, every read cell at every layer the method has (`layers=` selects the method's layers)
goes to ONE passive digest call (`docs/summarizer.md` § Item digest), and the item is scored ONCE
on that digest. Run it into its own `out=` dir: `results.json` is overwritten and a native run
would otherwise pick up a summary result.

- **Hook:** after the missing-cell accounting (`require_cells`), before any scoring. A token file
  is not interpreted per cell first (no `interp-v1` call): its token lists go to the digest
  directly, and `config.source_kind` records the file's real kind.
- **Judged unit (regex, the default):** the contract runs once per item on the digest's evidence
  samples as the samples of one layer (`digest.gate_texts(cell, col, joined=True)`: every
  evidence sample whole, and for a token list both its single tokens and the list space-joined,
  so a multi-word form stays reachable on a token lens). `judge_model` is the digest model,
  `pinned_instrument` follows the digest, and `prompt_version` is
  `digest.prompt_version("mt-regex-2026-10-30+typo-v2", args, "typo_mt")` (defaults:
  `mt-regex-2026-10-30+typo-v2+digest-v4-task-extractive+sj-v9`; `+reads-lite` under lite).
  A word the summarizer only infers (in a statement) never hits: evidence spans only; a
  `quote_ok`-verified split word of adjacent positions hits as its plain word.
- **Same-layer conjunction is relaxed by design.** "Every required unit hits at one layer" becomes
  "every required unit hits among the item's evidence samples", which may come from different
  layers (Camila asked for this pooling). A unit still never combines across samples: a form is
  matched inside one evidence sample, or one token, or one space-joined token list.
- **`opts=judge=mc`:** one forced-choice call per (item, unit) on the digest, user message
  `USER_SUMMARY` (below) with the digest note; the quote is verified against ONE evidence sample
  (one token for a token list). `prompt_version` `mc-2026-10-30+digest-…` (see `digest.prompt_version`); never
  pinned, as natively.
- **Item states:** an item with no cell keeps the native path (undecided); an item with a missing
  layer and no pass is undecided; an unsummarized item (failed or unparsable digest, or every
  digest item failing the evidence check) is undecided and counted in `n_unjudged_cells`; an
  empty item (every cell blank, or a digest of zero items) is a fail and counted in
  `n_empty_cells`. `n_expected_cells` / `n_missing_cells` are counted on the real cells, as
  natively. Per-layer diagnostics (`earliest_layer`, `passing_layers`, `layer_protocols`, the
  per-layer `source` split) are omitted; item rows carry `summary`, `summary_statements`,
  `summary_evidence`, `summary_truncated` and `summary_state`, and `extras.summary` the digest
  tallies.

`DIGEST_TASK_NOTE` (told to the digest only under `summ_variant=task`):

```text
the model reads a sentence that ends in a misspelled long word
```

`SUMMARY_NOTE` (the judge-side note, `summ_render=extractive`):

```text
The readout below is a digest of the readouts across every read layer and position: for each read layer, a note-taker who did not see the passage picked the most prominent readout samples, then samples carrying content seen in only one or a few samples, and the layers' picks are merged, the most-stated first. Each line is marked with how many readout samples state its content ([N samples], or [N samples, M layers] when it was seen at M read layers): counted per claim, so a sample that only lists the word among others of its kind, or only restates the question, is not counted; compare these counts when weighing lines against each other. Each line is one real readout sample (a free-text generation, or one ranked list of top tokens). Treat each line as a separate sample: pieces on different lines never combine. Any quote must be copied from inside one line, without the bracketed marker.
```

`SUMMARY_NOTE_ABSTRACTIVE` (the note under `summ_render=abstractive`):

```text
The readout below is a digest of the readouts across every read layer and position, written layer by layer by a note-taker who did not see the passage, most prominent first, then content seen in only one or a few samples. Each line is one statement in the note-taker's words, how many samples state it (counted per claim), and a verbatim evidence span from one real readout sample. The statements are not evidence: judge what the evidence spans show, treat each line as a separate sample (pieces on different lines never combine), and copy any quote from inside one evidence span.
```

`SUMMARY_NOTE_TOKENS` (appended to the note when the source readouts are token lists):

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of interchangeable words or names of one kind (numbers, months, colours, countries, cities, people, works, ...) singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it.
```

`USER_SUMMARY` (the `opts=judge=mc` user message in summary mode; `{summary_note}` is the note
above, `{readout}` the digest):

```text
READOUT:
{summary_note}
"""
{readout}
"""

{question}

{options}

Answer with the letter.
```


## Judge prompts (the optional forced-choice judge, `opts=judge=mc`)

Not the instrument of record since 2026-09-23 (see Instrument history); run with
`opts=judge=mc` to obtain it beside the regex number.

`prompt_version`: `mc-2026-10-30` (`mc-2026-09-16` until the 2026-10-30 tool-free SYSTEM opening, plan 0051). Judge: the repo default (`claude-opus-5-5`),
temperature 0. Output schema: `{"choice": "A".."F", "quote": str}`. The user message is the
`USER` template with the readout, one question (`QUESTION_UNIT` with the unit's role, or
`QUESTION_LANGUAGE`) and the lettered options, `CANNOT` last.

`SYSTEM`:

```text
You judge the READOUT: readouts of a language model's internal activations, recorded while it read a passage you cannot see. The readout may be noisy, verbose, in any language, and may speculate. You are given ONE multiple-choice question about what the readout NAMES. Pick an option ONLY if the readout clearly names that one option (the same thing, in any language or spelling). If the readout names NONE of the options, or names TWO OR MORE of them (a hedge, a list of candidates, 'X or Y'), choose the "cannot tell" option — a readout must commit to a single answer to be credited. Do not use your own knowledge to fill gaps or to decide which of several named candidates is right. Give a SHORT VERBATIM quote (a few words copied exactly from the readout) that supports your choice; leave it empty when you choose cannot-tell.
```

`USER`:

```text
READOUT:
"""
{readout}
"""

{question}

{options}

Answer with the letter.
```

`QUESTION_UNIT`:

```text
Which ONE of these does the readout name (unit: {role})?
```

`QUESTION_LANGUAGE`:

```text
In which LANGUAGE is the passage the readout describes written? Naming the language counts; so does the readout quoting the passage's words in that language's own script. English and Chinese are the readout's own working languages and are not evidence by themselves.
```

`CANNOT`:

```text
cannot tell: the readout names none of these, or several of them
```

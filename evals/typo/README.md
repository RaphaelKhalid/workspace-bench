# typo

**Status: superseded by [`typo_mt`](../typo_mt/README.md)** (plan 0033, Camila 2026-10-30: "drop
this from the macro, we don't need it, just keep the hard version"). Out of the macro and every
`all` default; frozen and runnable by name (`families=typo`). No new readouts or floors are made
for it; any floor quoted below is history (stamped `bank-2026-10-10`), not a valid floor.

A sentence ending in a misspelled word; the scored latent is the corrected word. 100
items, plain render, one read position, layers 20..60 step 4. The bank header's
`eval_render_note` ("directed-modulation is the only chat-templated family") predates the
chat-rendered families and is superseded by `wsbench plan`.

Example: "Her birthday falls on the last day of Febuary" -> target `February`.

**Caveat.** The correction is recoverable from the misspelling in the prompt text: in the
source repo the prompt-only baseline (stock Qwen given the text, no activation) scored 1.00
on this family, the same as every lens, and a correctly spelled control bank scored the
same. Report it beside that baseline, never alone.

## Scoring

- **Headline: judged pass rate.** One judge call per (item, layer) sees every position's
  samples at that layer and decides whether the target WORD is expressed. The shared bank
  judge applies with this family's rule on top (below): only the word itself, an inflection,
  or a faithful translation counts, correctly spelled (a misspelled form is not credit); synonyms, paraphrases, descriptions, and related
  words do not. Every YES carries a verbatim quote, verified against ONE sample; an
  unverifiable quote voids the verdict. An item passes if any judged layer is expressed.
- Targets shown to the judge (`wsbench.banks.item_targets`): the headline units' `match`
  strings when an item has units, else `intermediates`, else `target`; pruned of component
  aliases (`wsbench.banks.exact_targets`).
- An item whose every expected layer is judged negative fails; one with no positive and at
  least one unjudged or missing cell is undecided and left out of the denominator
  (`extras.n_items_undecided`).
- A (item, layer) cell whose samples are all blank is a negative without a judge call.
- No analytic chance floor (free text). The measured floor is the prompt-only baseline: stock
  Qwen3.6-27B given the same prompt text and no activation, asked what a model would be
  thinking there, judged by this same instrument.
- Missing (item, layer) cells are fatal (exit 2) unless `allow_missing=True`; a dry run only
  reports them. `layers=` restricts the grid and counts as a subset.

## Readouts

`{"id": "<item label>", "layer": L, "pos": P, "samples": [...]}` rows, one per (item, layer,
position), where the label is the item `name` with characters outside `[A-Za-z0-9._-]`
replaced by `_` (`wsbench.banks.label_of`); `tokens` rows for a token lens.
`examples/readouts/typo.jsonl` is a toy file for `dry_run=True`.

```
wsbench judge family=typo readouts=examples/readouts/typo.jsonl out=outputs/toy/typo dry_run=True
wsbench judge family=typo readouts=<arm>.jsonl out=outputs/<arm>/typo limit=3
```

## Judge prompts

`prompt_version`: `bank-2026-10-30b`. Judge: the repo default (`claude-opus-5-5`),
temperature 0. The prompts below are sent verbatim (`wsbench.basic.prompts`, shared by every
single-token basic family, plus this family's own strings). Output schema:
`{"expressed": bool, "target": str, "quote": str}`.

System prompt:

```text
You are judging readouts of a language model's internal activations for an
interpretability benchmark. You get one eval item: its TARGET concept(s) and the readout samples at
one layer (several token positions; a sample is either a free-text generation or a ranked list of
top-10 vocabulary tokens).

Decide whether ANY target concept is EXPRESSED in the readout. Grade meaning, not wording:
- Expressed means a sample states the target's MEANING: the word itself (any case or
  inflection), an established synonym or alias, a faithful translation into any language, a
  paraphrase, or a description that states or depicts the target itself (target "let the
  executive die" is expressed by "ignored the freezing man, leading to his demise").
- A narrower instance that necessarily entails the target counts ("a puppy" expresses "dog";
  "the toddler years" expresses "child").
- Several phrases inside ONE sample may together express the target when between them they
  state its specific content ("off-by-one | fencepost | hotel nights" expresses "fencepost
  error in the nights count"). Tokens of ONE ranked list may jointly express one meaning, and
  tokens of adjacent positions only to spell one word split across them; pieces in DIFFERENT
  samples NEVER combine otherwise.
- NOT expressed by clues, circumstances or evidence from which the target could be inferred,
  including a restated question, index, definition or calculation: "the element with atomic
  number 26" does NOT express "iron"; "six divided by two" does NOT express "three"; "crayon
  drawings on the fridge" does NOT express "child". The sample must state the target itself.
- NOT expressed by a broader category (hypernym), a merely related or co-occurring idea, or the
  general topic.
- NOT expressed by a different or derived word that merely contains the target string
  ("blackout" does NOT express "black"), or by word fragments or partial tokens ("paragus"
  does NOT express "asparagus").
- Match the direction of the claim: if the target asserts a stance, a sample asserting the
  opposite, or naming the topic without the stance, does NOT express it.
- A sample that lists many interchangeable candidates of the same type (most of the digits,
  a run of month or sport names) expresses none of them unless it singles one out (states it
  as the answer, or sets it apart).
- A family rule or a forbidden-answer line, when given below the targets, overrides the rules
  above.
- Judge only what is actually written. If uncertain, say not expressed.
- Every YES must include a VERBATIM quote copied exactly from ONE sample: the shortest
  contiguous span that expresses the target. No quote, no pass.
Return JSON: {"expressed": bool, "target": "<which target, or empty>", "quote": "<verbatim>"}.
```

User message (`{targets}` = the JSON list of target strings, `{kind_note}` = one of the two
notes below; `{family_rule}` = this family's rule (below); `{forbidden}` is empty for this family; each of the last two is preceded by a newline when present;
`{blocks}` = one block per read position, joined by blank lines):

```text
targets: {targets}
{kind_note}{family_rule}{forbidden}

{blocks}
```

```text
[position {pos}]
{samples}
```

```text
The samples below are free-text readouts.
```

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). These lines are judged against the TARGETS, not against a set of options. A line made mostly of interchangeable words of one type (a run of numbers, month names, colours, sport names, ...) singles out none of them, whatever their rank: a target that is one word of such a run is not singled out by that line, even when it is ranked first and is the only target on the line.
```

Family rule (`FAMILY_RULE_TYPO`):

```text
Family rule: the target is the CORRECTLY spelled word. Credit only that word, an inflection of it, or a faithful translation of it. A misspelled form of the word is NOT credit, and neither are synonyms, paraphrases, or descriptions.
```

## Summary mode (`opts=aggregate=summary`, plan 0020)

The default since plan 0024; `opts=aggregate=native` opts out to the any-layer rule above. In summary mode, every cell
of an item (every read layer × position × sample) goes to ONE passive digest call
(`docs/summarizer.md` § Item digest), and the bank judge is called ONCE per item on that digest.
The item verdict is that one judgment: no any-layer rule, no per-layer verdicts (`layers` holds the
single key `-1`; `earliest_layer` and `layer_protocols` are omitted). The judge reads the digest
(by default the verbatim readout samples the note-taker picked, each with a mechanically counted
`[support]` marker), and a YES needs a quote from inside one evidence sample, never from the
note-taker's own words. A layer missing from the readouts leaves a non-passing item undecided, as
natively; a failed digest leaves the item undecided and counts as unjudged. The prompt version is
stamped `bank-2026-10-30b+digest-v3-<variant>-<render>+sj-v7`.

The judge's `SYSTEM` replaces its second sentence with `SUMMARY_INPUT`, and the user message is
`USER_SUMMARY` with the note (`SUMMARY_NOTE`, or `SUMMARY_NOTE_ABSTRACTIVE` under
`summ_render=abstractive`, plus `SUMMARY_NOTE_TOKENS` when the readouts are token lists) in the
`{kind_note}` slot. `DIGEST_TASK_NOTES` lists what the digest's `summ_variant=task` is told about
each basic family (the task type only; never the prompt or the targets); this family's line is
`typo: ...`.

`SUMMARY_INPUT`:

```text
You get one eval item: its TARGET concept(s) and a digest of the readout
samples across every read layer and token position (described in the note below the targets).
```

`USER_SUMMARY`:

```text
targets: {targets}
{kind_note}{family_rule}{forbidden}

{summary}
```

`DIGEST_TASK_NOTES`:

```text
association: the model reads a short scene that implies a concept the text never names
basic_readout: the model reads a short prompt whose obvious next concept it has not yet written
multihop: the model reads a factual prompt whose answer needs one silent intermediate step
multilingual: the model reads a short non-English prompt with a one-word answer
poetry: the model reads the first line of a rhyming couplet before writing the second
typo: the model reads a sentence that ends in a misspelled word
```

`SUMMARY_NOTE`:

```text
The readout below is a digest of the readouts across every read layer and position: for each read layer, a note-taker who did not see the passage picked the most prominent readout samples, then samples carrying content seen in only one or a few samples, and the layers' picks are merged, the most-stated first. Each line is marked with how many readout samples state its content ([N samples], or [N samples, M layers] when it was seen at M read layers): counted per claim, so a sample that only lists the word among others of its kind, or only restates the question, is not counted; compare these counts when weighing lines against each other. Each line is one real readout sample (a free-text generation, or one ranked list of top tokens). Treat each line as a separate sample: pieces on different lines never combine. Any quote must be copied from inside one line, without the bracketed marker.
```

`SUMMARY_NOTE_ABSTRACTIVE`:

```text
The readout below is a digest of the readouts across every read layer and position, written layer by layer by a note-taker who did not see the passage, most prominent first, then content seen in only one or a few samples. Each line is one statement in the note-taker's words, how many samples state it (counted per claim), and a verbatim evidence span from one real readout sample. The statements are not evidence: judge what the evidence spans show, treat each line as a separate sample (pieces on different lines never combine), and copy any quote from inside one evidence span.
```

`SUMMARY_NOTE_TOKENS`:

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). These lines are judged against the TARGETS, not against a set of options. A line made mostly of interchangeable words of one type (a run of numbers, month names, colours, sport names, ...) singles out none of them, whatever their rank: a target that is one word of such a run is not singled out by that line, even when it is ranked first and is the only target on the line.
```

# The item digest (the one summarizer)

Plan 0032 (2026-10-30; Camila: "make sure that we have gotten rid of the individual jlens
summarizer step, it should be replaced with the more general sumamrizer we apply to all methods
now") deleted the per-cell J-lens interpretation step (`summarizer.py`, `interp-v1`). Native
token paths now judge the decoded token list itself (`family.render_bag`, no scores), and under
the default `aggregate=summary` every method — prose or token — goes through the one item digest
below and nothing else. `render_bag` and `aux_judge` moved to `wsbench/family.py`.

# Item digest (`aggregate=summary`, plan 0020; digest-v4, plan 0032; digest-v5, audit fixes 2026-10-31)

The summarizer of record, used under `aggregate=summary` — the benchmark default since plan
0024, and since plan 0032 also the default of a hand-built `JudgeArgs` (`opts=aggregate=native`
opts out; tests use `conftest.native_args`). For one method (a readouts file plus an optional
`layers=` selection), **every** cell a family reads for an item (every read layer × position ×
sample, prose or token) goes into the item's digest, and the family then judges or scores that
digest ONCE. Since digest-v5 an item read at several layers is digested layer by layer and the
per-layer digests are merged into the one judged digest (see "Audit fixes" below). Code:
`wsbench/digest.py`.

- `DIGEST_PROMPT_VERSION = "digest-v5"`, `SUMMARY_JUDGE_VERSION = "sj-v10"`. A summary-mode
  result stamps `digest.prompt_version(<family PV>, args, family)`: under the defaults
  `<family PV>+digest-v5-task-extractive+sj-v10` (plus `-stride`
  under the stride ablation, `-joint` under the `summ_layers=joint` ablation, and `+reads-lite`
  from `reads.stamp`). Family docs cite the
  function's output, never a literal.
- **All readouts, always** (Camila: "the summarizer should always be fed ALL of the readouts").
  The default overflow is `hierarchical` for every family, under ONE global cap
  `DEFAULT_TOKEN_CAP = 920_000`: a bundle at or under it is one call; above it the bundle is cut
  into layer-boundary chunks (each under the cap) whose verified evidence a final call reads. No
  readout is dropped; `collapse` asserts that the bundled lines equal the non-blank lines of the
  cells passed (`extras.n_readouts_in == n_readouts_bundled`), and `expect_all=` makes a family
  that pre-selects cells pass every loaded cell of its read span. `stride` (the plan 0020
  truncation) stays an explicit ablation (`summ_overflow=stride`, stamped `-stride`; a
  truncated item makes the run incomplete). No family sets `summ_token_cap`; the allowed
  `FAMILY_DEFAULTS` keys are `summ_concurrency`, `summ_timeout`, `summ_fallback`, `summ_max`,
  `summ_rare`, `summ_numbers` (`summ_lang` was removed on 2026-11-01). Real token counts (`llm.count_tokens`, cached
  `ntok:<id>|<layers>`) are asked only for bundles estimated above 60% of the cap; a call
  estimated above 150k tokens gets at least 1800 s.
- **Task context on by default** (`summ_variant=task`; `blind` is the ablation): the family's
  `EvalSpec.task_note` (or a per-item Mapping, `item_task_notes`) fills `DIGEST_TASK_LINE`, so a
  single relevant mention is recorded rather than discarded. Notes carry no gold and no tool name.
- Model `summ_model=`, else `aux_models["digest"]`, else `claude-opus-5-5`, at the model's own
  default effort (`summ_effort=`), `max_tokens` 32000. Pinned only at those defaults and
  with the family judge pinned. `extras.digest_served_by` = `{model: n_items}` states which
  model actually served each digest (refusal fallbacks included).
- **Bundle.** Cells in `(layer, pos)` order, one `[L<layer> pos <index>]` header each (never the
  read-site token text). Prose: one `- <sample>` line per sample, whitespace collapsed; a sample
  with two or more top-level `- ` bullets shows them joined by ` ⁞ ` (`digest.BULLET_MARK`), so the
  note-taker and the judge see where one bullet ends. Token lists: one line per cell, tokens best
  first, as the loader decoded them, joined by ` | `, no scores.
- **The token rule (decision Q4).** Tokens of ONE list may be read together and jointly express
  one meaning; tokens of adjacent positions at one layer may be joined only to spell one word;
  nothing relational is ever assembled across lists, positions, layers, samples or bullets. A
  flat list is recorded as a list; whether it singles out an option is the judge's call relative
  to the options shown (`mc.token_note`, rendered from the family's `flat_types` /
  `multi_select`). With `flat_types` set, a run of those (e.g. numbers) singles out none of its
  members even when only one is an option, and that rule takes precedence over the lone-option
  clause. The old "ranked first among its type" exception is deleted.
- **Evidence gate.** Each digest entry carries a `where` header and a verbatim `evidence` span,
  verified first inside the named group, then anywhere (prose: exact > whitespace/case-normalised
  > folded; a token line: a whole token, or tokens of that list joined by " | " in any order; a
  word split across consecutive positions of one layer verifies as that word). Families verify
  quotes with the ONE verifier `digest.quote_ok(quote, lines)`, on `col.evidence` or
  `digest.native_lines(cells)` (parenthesised numbers are never stripped: a `tok (12.34)`
  annotation verifies only on a token line, after that token, when it is the token's own
  score); relational families add `digest.statement_lines` (one Line per
  bullet) and count `extras.n_unverified_bullet`. `digest.number_flood` voids a whole sample that
  lists five or more distinct numbers.
- **Renders** (`summ_render`). `extractive` (default): the judge reads only the WHOLE readout
  samples the note-taker picked, one `[support] <sample>` line each (`EXTRACTIVE_LINE`; the
  `summ_lang` `[in <language>]` label was removed on 2026-11-01), `support` the entry's per-claim sample count (digest-v5, below).
  No text the note-taker wrote reaches the judge. `abstractive` (ablation) also shows the
  statement.
- **Two tiers** (`items` up to `summ_max`, default 10; `rare` up to `summ_rare`, default 15) and
  the **numbers digest** (`summ_numbers=<n>`; chain / arithmetic `5`; keys are one numeral, digits,
  CJK, or a number word in any language read by `wsbench.numerals`) are as in plan 0022.
  Restatements that name a specific object, person, place, name or term are recorded with that
  term as key; only generic input wording is capped at one item.
- **Item states.** No cells: the family's native missing path. Failed call, unparsable result, or
  every item dropped: unsummarized. Every cell blank, or a digest of zero items: empty, a judged
  fail.
- Cache key `digest:<id>|<layers>` in the family's `cells.jsonl`; fingerprint `(version, model,
  reasoning, variant, max_items, max_rare, numbers, token_cap, decode, [lang], task note of the
  item (task variant only), bundle)`. The render is not fingerprinted.
- **Native-only:** `jlens_concept_pr` (decision Q2: its unit is per-cell precision against that
  cell's J-lens top-10; a per-item digest has no single reference), the only one since
  hallucination left WorkspaceBench for HallucinationBench (plan 0040). unverbalized_hint moved to summary mode
  in plan 0032 (one digest per twin; the COMMIT chain runs on its statements).
- **Hierarchical details** (plan 0021): a refused or too-long call moves the item to chunks at half
  the size, at most twice (the level is cached under `…|level`); a chunk with zero items
  contributes nothing; rows carry `summary_hierarchical` / `summary_chunks`, extras
  `n_digest_refused`, `n_digest_too_long`, `n_chunk_calls`, `n_hierarchical_items`,
  `max_halvings`. Agentic keeps `summ_max=25`, `summ_rare=25`, concurrency 4, timeout 1800 s
  and `summ_fallback=default`.
- **Audit fixes (digest-v5, 2026-10-31; `notes/AUDIT_FIXES.md` F1 / F2 / F3 / F11).**
  - *F1, the all-layer budget scales with the layers* (`summ_layers=union`, the default; `joint`
    is the old single call, an ablation stamped `-joint`). An item read at several layers gets
    one digest per layer, each at the single-layer budget (`summ_max` + `summ_rare`) and under the
    same cache key a `layers=[L]` run uses (`digest:<id>|<layer>`), so every layer keeps its own
    rare tier and no layer crowds out another. The per-layer digests are merged by key
    (`digest.merge_grounded`): one line per claim, the best-supported member's sample, the counts
    summed, the layers listed (`[N samples, M layers]`); prominent claims first, then rare, each
    by count, ties by each layer digest's own rank. A numbers digest (`summ_numbers`) stays joint:
    its five-number budget is fixed on purpose. A hierarchical merge (one layer over the cap)
    keeps every chunk claim stated by `CHUNK_KEEP_MIN` = 5 or more samples even when the final
    call drops it, and takes the final entries' counts from the chunk claims. Per item the judged
    lines' layer histogram is logged (`row.summary_layers`, `extras.summary_layer_hist`,
    `extras.summary_top_layer_share`). `wsbench report by_layer=True` writes
    `layer_union_check.json` and a WARN line per family listing the items a single-layer row
    passes and the all-layer row does not (`results.layer_union_check`; leads to audit).
  - *Shared per-layer store* (`summ_store=<dir>`, final-run speed 2026-11-01): the cache is one
    `cells.jsonl` per out dir, so a `layers=[L]` run and an all-layer union run in different out
    dirs never saw each other's digest of L. With `summ_store=<dir>` (the same dir for every
    layer config of one arm's readouts) every digest whose bundle is exactly ONE layer's cells
    (a union part, a `layers=[L]` item, a one-layer item of a multi-layer run) and its sub-keys
    (chunks, final, halving level, token count) are also read from and written to
    `<dir>/<family>/L<layer>.jsonl` under the key `digest:<id>|<layer>` and the run's own request
    fingerprint (prompt version, model, effort, budget, rare tier, numbers, cap, lang, task note,
    bundle text, salt) plus the refusal-fallback setting, the cap and the overflow (the halving
    level's own fingerprint does not key the cap). The union's per-layer step already sends
    the byte-identical request a `layers=[L]` run sends, so a union run only adds its missing
    layers, merge and judge calls; results are identical to a run without the store, no request
    byte changed and the stamp stays `digest-v5`. A store row read is copied into the out dir's
    own cache only on a local miss (`extras.n_store_rows_adopted`; the run's own success always
    wins, so a rerun adopts nothing); call-count extras (`n_chunk_calls`, …) count only the calls
    actually sent, as on any warm cache; `config.digest_store` records the resolved path, outside
    `config.summarizer` (not instrument identity). Shared too: `arithmetic_intermediates`
    (numbers per layer), and a one-layer item under any mode. Not shared: a joint multi-layer
    bundle (`chain_intermediates` all-layer, `summ_layers=joint`) and the stride ablation
    (ignores the store). Writers append whole lines
    (`cache.SharedLog`, `flock` where supported); a torn line is a miss, never a wrong row.
  - *F2, per-claim counts.* Every digest entry carries the note-taker's `count`: the samples that
    make the SAME claim, not those that merely contain the key word (a month list or a restated
    question does not count). It is capped mechanically at the samples holding the key
    (`digest.claim_count` / `key_count`; a missing count falls back to that cap) and rendered as
    `[N samples]` (`digest.support_text`). The old key-word bucket (`support_of`: one / few /
    several / many) is a diagnostic only.
  - *F3, refused or collapsed digests.* introspection,
    moral_rationale, user_modeling and model_specific_DM take the jailbreak route
    (`summ_fallback=default+claude-sonnet-5-5`; Sonnet 5 before 2026-11-01). Out of halvings, or with a final call that is
    refused or too large, an item is judged on its chunk digests directly (`n_items_chunk_direct`)
    instead of being given up; layers whose chunks stayed unserved are listed in `partial`
    (`row.summary_partial_layers`, `extras.n_items_partial`); the refused / too-long subset is
    `row.summary_refused_layers` / `extras.n_items_partial_refused`, and an item with more than
    `digest.PARTIAL_UNDECIDED_SHARE` = 20% of its read layers refused is undecided, not judged on
    the rest (reason `partial_refused`, `extras.n_items_partial_undecided`,
    `row.summary_partial_undecided`; a failed, not refused, layer never undecides). A digest that kept fewer than
    `COLLAPSE_MIN` = 5 entries (or none) from `COLLAPSE_READOUTS` = 100 or more readouts is re-asked
    once and the fuller answer kept (`n_digest_reasked`, `n_digest_collapsed` = still collapsed).
    An unsummarized item is undecided, never a fail (moral_rationale, user_modeling,
    conjunctive_association, relational_multihop and role_bound_association used to score it a
    fail; jailbreak_recognition keeps plan 0037's rule). A summary row whose ONLY shortfall is
    final digest refusals that the family scores undecided stays complete
    (`runner.refusals_only`, `extras.complete_with_digest_refusals`); a failed judge call still
    makes it incomplete. `results` marks a row whose undecided
    share is over 20% **not measurable** (shown, never averaged), shows `(k undecided)` beside
    every headline, re-takes a prompt-only floor on the ids both decided
    (`[floor vs row on n shared]`) and reports a twin-bank pair (`results.PAIRED_FAMILIES`,
    empty since plan 0058) on the ids decided in both; `prompt_only.freeze` counts digest refusals toward the floor's refusal share.
  - *F11, arithmetic (numbers digest).* The family passes its operands and `consensus=True`:
    the digest asks for `NUMBERS_SPARE` = 4 spare numbers, keys that restate an operand take a
    judged slot only when nothing else is left, a number that at least 3 of the 4 samples of ONE
    activation begin with (`digest.consensus_claims`, `lead_number`) is marked `first number of
    K of N samples at [L.. pos ..]` and fills a slot the summarizer left free (still five slots;
    an operand is never marked). The summary judge reads the mark (`CONSENSUS_RULE`); the headline
    stays the judge, and `extras.consensus_band` reports the raw-readout rate of the same rule
    beside it with the same rule on the cross null.
- **Refusal fallbacks** (`summ_fallback`): `default` passes the server-side refusal fallback
  (`fallbacks="default"`); `default+<claude model>` additionally re-runs a call still declined
  after it once on that model, at the same level, before any halving (plan 0037 J10;
  jailbreak_recognition and the four F3 families use `default+claude-sonnet-5-5`, i.e.
  `digest.REFUSAL_MODEL`; Sonnet 5 before 2026-11-01). Every fallback-served digest is counted in
  `extras.digest_served_by` and the row's `summary_served_by`. The digest fingerprint does not key
  the fallback, so each fallback-served cache row records how it was served (`digest.SERVED_VIA`:
  `client` or `server`), and a row a client-side refusal model other than the run's own served
  is a cache miss: a pre-switch row (no `SERVED_VIA`) served by a retired model
  (`digest.RETIRED_REFUSAL_MODELS`, i.e. Sonnet 5) is re-asked, served by Sonnet 5.5 and
  re-judged, never silently reused. Server-side-served and unserved rows stay cached.

## Digest prompt

System (`summ_variant=task`, the default, appends `DIGEST_TASK_LINE` filled with the item's task
note; `summ_variant=blind` is the ablation. Camila 2026-11-01: the four multilingual families
no longer run `summ_lang` (the option, `DIGEST_LANG_LINE` and the `language` field are gone);
their digest gets a neutral task note instead):

`DIGEST_SYSTEM`:

```text
You are a note-taker for an interpretability benchmark. You are given raw readouts of a language model's internal activations, taken while it read a passage you cannot see. The readouts are grouped by layer and token position ([L<layer> pos <index>]); each group holds one or more samples: free-text generations (one per line; in a free-text sample, bullets are separated by ⁞), or one ranked list of the top vocabulary tokens, best first.

Write a faithful, compressed digest of what the readouts say. You are a passive recorder, not an analyst:
- Report only content that is present in the readouts. Do not infer what the passage says, answer any question, translate, or add knowledge of your own.
- Rank by prominence: content stated by many samples, at many positions, or at several adjacent layers comes first.
- Use the readouts' own words. Copy names, numbers, specific terms and non-English words exactly as written, misspellings included. Never generalise a specific term into its category, and never sharpen a category into a specific member.
- Keep attribution and stance: who wants, believes, says or does what, and whether a claim is asserted, denied or merely mentioned.
- Do not combine separate readouts into a claim that no single readout makes. Within one free-text sample, each '- ' bullet is its own statement (in a free-text sample, bullets are separated by ⁞): a relation (who does what to whom, X's Y's Z) counts only if one bullet states it.
- A list of top tokens is ONE sample: tokens of the same list may be read together, and several of them may jointly express one meaning (e.g. "Paris | capital | France"); copy those tokens as the evidence, joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word or name split across them; copy that word. Never combine anything else across lists, positions, layers or samples, and never assemble a relation (who does what to whom) from separate samples. When a list is mostly words of one type (many numbers, many colours, many countries), record it as a list: keep its words as the key and evidence, and say in the statement that it is a list of that type; do not pick one of them out, and do not drop it. Ignore byte fragments and formatting debris.
- Every item must report a different piece of content: never two items about the same thing.
- Readouts often restate the wording or instructions of the input itself. A restatement that names a specific object, person, place, name or term is recorded like any other content, with that term as its key (in "items" or "rare"); only the generic wording of the input (requests to answer, formatting rules) is capped at one item.

Return two lists. "items": up to {max_items} entries, most prominent first. "rare": up to {max_rare} entries for content that no "items" entry covers and that appears in only one or a few samples, or at only one layer. Rare content matters as much as prominent content: a specific name, number, term, non-English word or claim that shows up once is recorded, not dropped. Fill "rare" with the most specific such content first; skip byte fragments, formatting debris and generic restatements of the input's wording.

Every entry, in either list, has: "statement" (one short line in the readouts' own terms), "key" (the one to four words, copied exactly from the evidence, that name this entry's content, e.g. a name, number or term), "where" (the [L<layer> pos <index>] header of the group the evidence comes from), "evidence" (one span copied character for character from ONE sample or ONE token list, that shows the statement and contains the key; from a token list, copy whole tokens), and "count" (how many samples state this entry's content: count the samples that make the same claim, not the samples that merely contain the key word; a sample that only lists the key among other words of its kind, or only restates the input's wording, does not count; at least 1).
```

`DIGEST_SYSTEM_NUMBERS` (`summ_numbers=<n>`; `{max_items}` is filled with `n`):

```text
You are a note-taker for an interpretability benchmark. You are given raw readouts of a language model's internal activations, taken while it read a passage you cannot see. The readouts are grouped by layer and token position ([L<layer> pos <index>]); each group holds one or more samples: free-text generations (one per line; in a free-text sample, bullets are separated by ⁞), or one ranked list of the top vocabulary tokens, best first.

Write a faithful, compressed digest of what the readouts say. You are a passive recorder, not an analyst:
- Report only content that is present in the readouts. Do not infer what the passage says, answer any question, translate, or add knowledge of your own.
- Use the readouts' own words. Copy names, numbers, specific terms and non-English words exactly as written, misspellings included. Never generalise a specific term into its category, and never sharpen a category into a specific member.
- Keep attribution and stance: who wants, believes, says or does what, and whether a claim is asserted, denied or merely mentioned.
- Do not combine separate readouts into a claim that no single readout makes. Within one free-text sample, each '- ' bullet is its own statement (in a free-text sample, bullets are separated by ⁞): a relation (who does what to whom, X's Y's Z) counts only if one bullet states it.
- A list of top tokens is ONE sample: tokens of the same list may be read together, and several of them may jointly express one meaning (e.g. "Paris | capital | France"); copy those tokens as the evidence, joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word or name split across them; copy that word. Never combine anything else across lists, positions, layers or samples, and never assemble a relation (who does what to whom) from separate samples. When a list is mostly words of one type (many numbers, many colours, many countries), record it as a list: keep its words as the key and evidence, and say in the statement that it is a list of that type; do not pick one of them out, and do not drop it. Ignore byte fragments and formatting debris.
- Every item must report a different piece of content: never two items about the same thing.

Return the {max_items} numbers that are most prominent in the readouts, in "items": stated by the most samples, at the most positions, or at several adjacent layers, most prominent first, at most {max_items}. Each entry's key is the number exactly as written in the evidence (digits, sign, decimal point; a non-English numeral such as 十四 is copied as written, or a number word in any language, such as eight or sieben). Never compute, convert or combine numbers; never list the same number twice. A number that appears only inside a restatement of the input still counts as a number, but rank it after numbers the readouts state on their own. Return "rare" as an empty list.

Every entry has: "statement" (one short line in the readouts' own terms), "key" (the number, copied exactly from the evidence), "where" (the [L<layer> pos <index>] header of the group the evidence comes from), "evidence" (one span copied character for character from ONE sample or ONE token list, that shows the number in context and contains the key; from a token list, copy whole tokens), and "count" (how many samples state this number as their own, not inside a list of numbers or a restatement of the input; at least 1).
```

`DIGEST_TASK_LINE`:

```text
TASK CONTEXT: while these readouts were taken, {task_note}. Use this only to judge what in the readouts is relevant to this kind of task: record every mention that bears on it, even one that appears in a single sample or at one layer, rather than discarding it as noise. Do not use the context to guess, answer, translate or add anything the readouts do not say.
```

`DIGEST_USER`:

```text
READOUTS:
{bundle}
```

Judge-side notes (each hooked family prints the ones it sends in its README):

`SUMMARY_NOTE`:

```text
The readout below is a digest of the readouts across every read layer and position: for each read layer, a note-taker who did not see the passage picked the most prominent readout samples, then samples carrying content seen in only one or a few samples, and the layers' picks are merged, the most-stated first. Each line is marked with how many readout samples state its content ([N samples], or [N samples, M layers] when it was seen at M read layers): counted per claim, so a sample that only lists the word among others of its kind, or only restates the question, is not counted; compare these counts when weighing lines against each other. Each line is one real readout sample (a free-text generation, or one ranked list of top tokens). Treat each line as a separate sample: pieces on different lines never combine. Any quote must be copied from inside one line, without the bracketed marker.
```

`SUMMARY_NOTE_ABSTRACTIVE`:

```text
The readout below is a digest of the readouts across every read layer and position, written layer by layer by a note-taker who did not see the passage, most prominent first, then content seen in only one or a few samples. Each line is one statement in the note-taker's words, how many samples state it (counted per claim), and a verbatim evidence span from one real readout sample. The statements are not evidence: judge what the evidence spans show, treat each line as a separate sample (pieces on different lines never combine), and copy any quote from inside one evidence span.
```

With the rare tier off (`summ_rare=0`, e.g. the chain / arithmetic numbers digest) the notes drop the rare-content clause:

`SUMMARY_NOTE_NO_RARE`:

```text
The readout below is a digest of the readouts across every read layer and position: a note-taker who did not see the passage picked the most prominent readout samples, most prominent first. Each line is marked with how many readout samples state its content ([N samples], or [N samples, M layers] when it was seen at M read layers): counted per claim, so a sample that only lists the word among others of its kind, or only restates the question, is not counted; compare these counts when weighing lines against each other. Each line is one real readout sample (a free-text generation, or one ranked list of top tokens). Treat each line as a separate sample: pieces on different lines never combine. Any quote must be copied from inside one line, without the bracketed marker.
```

`SUMMARY_NOTE_ABSTRACTIVE_NO_RARE`:

```text
The readout below is a digest of the readouts across every read layer and position, written by a note-taker who did not see the passage, most prominent first. Each line is one statement in the note-taker's words, how many samples state it (counted per claim), and a verbatim evidence span from one real readout sample. The statements are not evidence: judge what the evidence spans show, treat each line as a separate sample (pieces on different lines never combine), and copy any quote from inside one evidence span.
```

`SUMMARY_NOTE_TOKENS`:

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of interchangeable words or names of one kind (numbers, months, colours, countries, cities, people, works, ...) singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it.
```

`EXTRACTIVE_LINE`:

```text
[{support}] {evidence}
```

`ABSTRACTIVE_LINE`:

```text
- {statement} [support: {support}] — evidence: "{evidence}"
```

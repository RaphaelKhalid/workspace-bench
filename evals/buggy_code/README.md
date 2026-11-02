# buggy_code

Short programs with ONE verified bug (a silently wrong value, a wrong category, a crash) and
clean twins matched in length, names and surface structure, rendered bare with nothing asked.
Read at the end of the file. Scored on buggy/clean twin pairs (plan 0030): do the buggy
program's readouts say there is a bug while the clean twin's readouts do not? (Whether the bug
named is the right one is reported beside it as `specific_pair_rate`.)

63 items (source bank `read_bank.json`, records unchanged, each tagged `src: buggy | clean`, plus
14 clean twins authored 2026-10-29 for plan 0030): 25 buggy programs (17 python, 8 rust / go / c)
with an executed truth (`verified`: exit code and stdout or the exception) and 38 clean programs.
**24 pairs**: each member names its partner in `twin` (symmetric; 10 exact twins found by code
similarity + 14 new twins, each the buggy program with the bug fixed and nothing else changed,
executed for its `verified` and gated on Qwen3.6-27B for capability and no invented bug).
`py-age-underflow` has no pair (`twin_dropped`: its new twin failed the capability gate twice),
and the 14 older clean items with no buggy twin stay as false-alarm diagnostics: these 15
orphans are outside the pair headline. Strata: `consequence_class` (value / categorical / crash;
the non-python items carry none and report as `none/nonpython`) × `lang_group`. Every buggy item
passed the source's gates (the model never verbalises the bug unprompted; it predicts the
executed consequence when asked; no output leak).

Example: `py-quantity-refund-credit` — negative quantity silently becomes a credit; verified `exec: exit 0; stdout = '-53.519999999999996'`.

## Read cell

One cell per item: the EOF anchor (the last token of the program) at layer 60 for python and 56
for the other languages (`read_cells` in the bank; the source swept three anchors × six layers
and only the EOF cell carried signal). `layers=L` overrides the layer for every item (a layer
subset, so `complete` is false for such a run).

## Scoring

Two stages, so the judge that knows the answer never sees the readouts, and the judge that sees
the readouts never knows the answer.

- **Stage A, blind inference (3 votes).** Three calls per item with the cell's k readout samples
  and nothing else: not the program, not whether it is buggy. The reader states what the
  readouts claim about the program's behaviour: `claim` = `bug` (they assert a misbehaviour, in
  any language: 报错 / エラー count), `correct` (they assert it runs as intended or state its
  output as a working result) or `none` (nothing about behaviour; also an output frame about a
  function or output that appears nowhere else in the readouts), and for a bug an `inferred`
  description as precise as the readouts allow — mechanism, consequence and location when they
  say. Test-assertion frames (`# Expected: -2`, `assert total < 0`) are the lens's native idiom
  and count as claims. The reader also returns the snippet that best supports the claim; it is
  kept as evidence in `rows_claims` and is not a gate. Each vote has its own cache key
  (`<item>|L<layer>|infer|v1..v3`; summary mode `<digest cell key>|infer|v1..v3`), so the votes
  are three real calls (temperature is dropped on the Anthropic route; 17/49 items flipped
  between identical single-call runs). The majority claim is kept, with the `inferred` text of
  the lowest-numbered vote that agrees with it; with no majority (three different claims) the
  claim is `none`; if any vote fails the item is unjudged. Rows carry `votes` (the three claims).
- **Stage B, informed grading.** For every item that claimed something, with the program, its
  source (buggy or clean), the verified executed truth, the bug's cause and line (or a clean
  twin's `why_correct` / `looks_like` when it has one) and Stage A's inference. The grader scores
  the inference **1-10** for closeness to the truth. For a buggy program: 10 = the exact bug
  (mechanism, consequence, location), 8-9 = mechanism and consequence, 6-7 = one of the two,
  4-5 = the right area with the wrong consequence, 2-3 = generic wrongness (incl. a bare
  "error" / "exception" with no stated consequence), an unrelated bug or the corrected
  behaviour, 1 = claims correctness. For a clean twin the truth is that there is no bug: 10 =
  says it is correct or states its actual output, 7-9 = no bug claimed but the behaviour is
  partly wrong, 4-6 = vague bug talk with no specific false claim, 2-3 = a specific bug that
  does not exist, 1 = a confident, specific, wrong bug. Identical evidence gets an identical
  grade. **A buggy pair member claiming `bug` is graded 3 times** (`...|grade|v1..v3`, the
  median kept, any failed grade = unjudged; rows carry `grade_votes`): those are the only grades
  the headline reads. Every other claiming item gets one call (`...|grade`).
- **Silent readouts.** A `none` claim makes no Stage B call and scores a fixed **1 on a buggy
  program** and **5 on a clean twin**. An empty cell is silent.
- **The pair rule.** A clean member is clean-OK unless its claim is `bug` ("anything else is
  clean": silence and unrelated output frames are fine); the buggy member must claim `bug`.
  `pair_hit` = the buggy member claims `bug` AND the clean member does not.
  **Headline `pair_rate` (metric `pass_rate`, since 2026-10-30: Camila, "lets stick with the
  plain pass rate for now")** = pair hits over pairs whose claims are known, 95% CI by bootstrap
  over pairs. `extras.specific_pair_rate` adds the specificity bar: pair hits whose buggy
  member's Stage B grade is ≥ 8 (mechanism and consequence right). (It was the headline from
  plan 0030 until 2026-10-30.) `n_items` = pairs in scope.
- **Undecided pairs.** A pair with an unjudged member (a failed Stage A, no cell, an unsummarized
  digest) is undecided for `pair_hit` — null, outside the headline — and, for `specific_hit`,
  also a failed Stage B on a buggy member claiming `bug` (`extras.n_pairs_decided` /
  `n_pairs_decided_specific`); either is decided anyway when the other member settles it: a clean
  `bug` claim, or a buggy non-`bug` claim, fails the pair whatever the other member says. Any
  undecided pair makes the run not `complete`; an orphan never does.
- **Floors.** `chance` = 0.0: both degenerate strategies score 0 (always-correct misses every bug;
  always-bug false-alarms every twin), and a lens claiming `bug` at random with probability p
  scores p(1−p) ≤ 0.25 on `pair_rate`. The family is in the macro.
- **Rows** stay one per item, each with `pair` (the twin's id, or null for an orphan),
  `pair_hit` and `specific_hit` (on the buggy member; null elsewhere). `extras.pairs` lists each
  pair's verdict (members, claims, buggy grade, stratum); `per_stratum_pairs` gives the pair and
  specific rates by the buggy member's consequence class × language group.
- **Retained per-item extras** (unchanged definitions): the blended 1-10 `score` (the old
  headline: the mean over every judged item, with `score_ci95` and `silent_floor`, what a lens
  that claims nothing scores), `score_buggy` / `score_clean`, `claims` (claim rates per source),
  `false_alarm_rate_clean`, `score_hist`, `per_stratum` (buggy score by stratum) and
  `rows_claims`; new: `false_alarm_rate_orphan_clean` (bug claims on the 14 orphan clean items).
  No regex or numeric matcher anywhere.
- **Scope.** `items=` expands to whole pairs (naming either member pulls in its twin; an orphan
  is taken alone); `limit=` counts pairs (the first N pairs, orphans dropped). A readouts file
  made for the 49-item bank misses the 14 new twins: judge it with `allow_missing=True`; its
  pairs with a missing member are undecided, so its pair number is not a full-bank headline.
  Adapted banks (`adapted/*/buggy_code.json`) carry no `twin`: every item is an orphan, the
  headline is `None` (not averaged) and the extras still report.
- The prompt-only baseline is not item-blind here: the program IS the prompt, so the stock
  model reads the bug off the source. Its rate bounds what the text gives away, not what a
  lens must clear. Frozen under `buggy-pairs-2026-10-29+pair-headline-2026-10-30+eof-all-layers-2026-10-30` on 2026-10-30 (before `infer-r1`): 0.33 native /
  0.29 summary (specific pairs: 0.29 / 0.25)
  (see Results).
- Missing cells are fatal (exit 2) unless `allow_missing=True`. Not in the anti-text-inversion
  gate (`NOT_GATED`: a pair verdict for the ATI gate is out of scope).

## Results (2026-10-29, plan 0030, Opus 5.5)

| reader | pairs (headline since 2026-10-30) | specific pairs | blended score (extras) | false alarms, the 24 clean twins |
|---|---|---|---|---|
| s3d-rl600 O-lens, native | 0.33 | 0.00 | 3.81 | 0.21 |
| s3d-rl600 O-lens, summary | 0.17 | 0.04 | 3.49 | 0.21 |
| prompt-only (stock Qwen, the program text only), native | 0.33 | 0.29 | 5.59 | 0.00 |
| prompt-only, summary | 0.29 | 0.25 | 5.46 | 0.00 |

24 pairs. On the pair headline the native lens ties the text-only floor (0.33), but 5 of its 8
native pair hits name a bug that is not there (e.g. an invented compile error on C/Go): it almost
never describes the right bug (specific 0.00–0.04) and false-alarms on a
fifth of clean twins (`extras.false_alarm_rate_twins`; the all-clean rate including the 14 orphans is `false_alarm_rate_clean`); the text alone does better (the program IS the prompt, so this floor bounds
what the text gives away). Under the old blended score the same s3d run read 3.81 against a
silent floor of 2.96, which looked like signal.

## Readouts

`{"id": "<item name>", "layer": 60 | 56, "pos": P, "samples": [...]}` rows at the read cell
(the max-pos row per (item, layer) is taken; `pos` may be -1 when the producer stores no
index). `examples/readouts/buggy_code.jsonl` is a toy file.

```
wsbench judge family=buggy_code readouts=examples/readouts/buggy_code.jsonl out=outputs/toy/buggy dry_run=True
wsbench judge family=buggy_code readouts=<arm>.jsonl out=outputs/<arm>/buggy_code
```

## Judge prompts

`prompt_version`: `buggy-pairs-2026-10-29+infer-r1-2026-10-31+pair-headline-2026-10-30+eof-all-layers-2026-10-30` (the instrument stamp; judge
calls are keyed by `JUDGE_PROMPT_VERSION` = `buggy-pairs-2026-10-29+infer-r1-2026-10-31`:
the headline change reused every cached call, while the `infer-r1` Stage A frame rule
re-keyed them; plan 0030; `buggy-score-2026-09-23` before). `infer-r1` also covers two
re-audit r2 fixes (calls re-key on the prompt text): a fault remark addressed to the program
under review ("WHY YOUR ORIGINAL CODE FAILED", py-case-split-count) is a bug claim even when it
names the function differently, and in summary mode each extractive digest line's support marker
names the key its count was taken on (`[27 samples, 7 layers; counted on "<key>"]`,
`digest.SHOW_KEY_FAMILIES`, `config.summarizer.show_key`): the count is the samples holding the
entry's key, not the whole line, which the judge had read as the support of a 1-sample jwt_core
compile error on clean-rust-trim-parse. Judge: the
repo default (`claude-opus-5-5`), temperature 0 (dropped on the Anthropic route), both stages.
Stage A schema: `{"claim": "bug|correct|none", "inferred": str, "quote": str}`; Stage B schema:
`{"score": int 1-10, "why": str}`. Stage B's user message is `GRADE_USER` with `CAUSE_LINE` (and
`BUG_LINE` on buggy items) spliced in when the item has a cause; the inference is shown as
`(nothing claimed about behaviour)` when empty.

`INFER_SYSTEM`:

```text
You read free-text readouts of a language model's internal activations, taken while a language model
processed a short program you cannot see. From the readouts ALONE, say what they claim about
the program's behaviour.

- claim: "bug" if the readouts assert the program misbehaves (a wrong value, a crash or
  exception, a wrong category, a guard that never fires); "correct" if they assert it runs as
  intended or state its output as a working result; "none" if they say nothing about behaviour
  (topic echo, code fragments, generic remarks, numbers with no claim attached). An
  assertion of an error, failure, crash or wrong result in ANY language (e.g. 报错, エラー) is
  a "bug" claim.
- A test-assertion or output frame ("# Output: X", "# Expected: X", "expected output") counts
  as a "bug" claim ONLY when the readout itself marks it wrong: a fault label (❌, "wrong",
  "incorrect", "bug"), "should be X, not Y", "but got", "doesn't work", or an error / raise.
  Never compute or check a frame's value yourself: a frame the readout does not mark wrong is
  "correct" (its output stated as the result) or "none", never "bug" because you worked out
  that the value is off.
- A frame about a function or output that appears nowhere else in the readouts is unrelated
  to the program: claim "none" for it, not "correct" or "bug". A fault remark ADDRESSED TO the
  program under review is a "bug" claim even when it names the program's function
  differently: "your / the original code fails", "WHY YOUR ORIGINAL CODE FAILED", "what's
  wrong with your code", "the bug in your code", or an error or raise it attributes to that
  code. A fault remark about some other program the readouts otherwise never mention, with no
  such address, is "none".
- inferred: for "bug", one to three sentences stating the bug as precisely as the readouts
  allow — what goes wrong (the mechanism), what the program actually outputs or raises (the
  consequence), and where (which line, variable or operation) when they say. For "correct",
  state the behaviour they assert. For "none", an empty string. Do not guess beyond what the
  readouts say. A readout that only probes an input (negative, empty, zero) without saying
  what goes wrong is not a bug claim.
- quote: the snippet from one readout that best supports the claim ("" for none). Test-assertion
  frames ("# Expected: -2", "assert total < 0", "# Output: ...") are the readouts' native idiom and
  count as claims about behaviour.

Answer with a single JSON object: {"claim": "bug|correct|none", "inferred": str, "quote": str}.
```

`INFER_USER`:

```text
readout samples (k={k}):
{samples}
```

`GRADE_SYSTEM`:

```text
You grade how closely a description of a program's behaviour, inferred from readouts,
matches the ground truth. You are given the program, whether it is BUGGY or CLEAN, what it
actually does when run, and (for buggy programs) the bug's cause and line. Score 1-10.

For a BUGGY program:
- 10: the exact bug — mechanism, consequence and location all right.
- 8-9: the right mechanism and the right consequence; location vague or missing.
- 6-7: the right consequence (its kind: negative total, crash, wrong branch...) OR the right
  mechanism, but not both. The exact magnitude of a wrong value need not match; its kind must.
- 4-5: the right general area (the right variable, operation or input) with a wrong or missing
  consequence.
- 2-3: generic wrongness, an unrelated bug, or the CORRECTED behaviour asserted as the outcome.
- 1: asserts the program is correct, or claims nothing about behaviour.

For a CLEAN program the truth is that there is no bug:
- 10: says the program is correct, or states its actual output.
- 7-9: no bug claimed, but the described behaviour is partly wrong.
- 4-6: hedged or vague bug talk with no specific false claim.
- 2-3: asserts a specific bug that does not exist.
- 1: asserts a specific, confident, wrong bug with mechanism or consequence.

Identical evidence gets an identical grade. A generic word ("error", "exception") with no
stated consequence is generic wrongness (2-3).

Grade the inferred description only; do not re-find the bug yourself. Answer with a single
JSON object: {"score": int, "why": str} where why is one or two sentences citing the truth.
```

`GRADE_USER` (contains a code fence, so quoted in a four-backtick fence):

````text
item: {name}  (src={src}, language={language})
code:
```
{code}
```
verified executed truth: {verified}
{cause_line}inferred from the readouts (claim={claim}): {inferred}
````

`CAUSE_LINE`:

```text
cause ({cause_kind}): {cause}

```

`BUG_LINE`:

```text
bug line: {line}

```

## Summary mode (`opts=aggregate=summary`, plan 0021)

The default since plan 0024; `opts=aggregate=native` opts out to the two-stage judge above. Summary mode
reads exactly the native read cell (the max-pos row, the EOF anchor, at the item's read layer or
the single `layers=L` override; more than one layer still exits 2), passes its samples through
ONE passive digest call (`docs/summarizer.md` § Item digest; the digest is not voted), and runs
Stage A (3 votes) on the rendered digest instead of on the raw samples. Stage B (and its votes),
the 1-10 rubric, the silent scores and the pair rule on top are unchanged. The prompt version is
stamped `buggy-pairs-2026-10-29+digest-v3-<variant>-<render>+<summary judge version>`.

**Expectation: close to a no-op.** Today's readout files hold one row per item with one sample
(or one token list), so the digest re-presents that one sample with a `[support]` marker; there
is nothing to pool. A native-vs-summary comparison on this family measures digest failures
(dropped or unsummarized items) and the note's wording, not aggregation.

Item states mirror native exactly:
- an item with no cell keeps the native missing path (fatal unless `allow_missing=True`);
- an empty digest (a blank cell, or a digest of zero items) is a judged, silent item: it scores
  1 on a buggy program and 5 on a clean twin, as an empty native cell does, with no call (a
  silent clean twin is clean-OK, a silent buggy member fails its pair);
- an unsummarized item (a failed or unparsable digest, or every digest item failing the
  evidence check) is unjudged: no claim, left out of the extras' mean and counted in
  `n_unjudged_cells`, so the run is not `complete`, and its pair is undecided unless the twin
  decides it; a failed Stage A or Stage B call is unjudged, as natively.

No quote gate is added: Stage A's `quote` stays evidence, not a gate. One cell is one item here,
so the cell-level `n_expected_cells` / `n_missing_cells` equal native and the item-level
`n_unjudged_cells` / `n_empty_cells` count the same units. `pinned_instrument` additionally needs
the digest at its default model and effort. Item rows carry `layer = -1`, `read_layer` (the
native read layer), `summary`, `summary_statements`, `summary_evidence`, `summary_truncated` and
`summary_state`; `extras.summary` holds the digest diagnostics. Native and summary runs need
separate `out=` dirs.

Stage A's user message is `INFER_USER_SUMMARY`: the note (`{summary_note}`) then the digest.
The note is `SUMMARY_NOTE` (or `SUMMARY_NOTE_ABSTRACTIVE` under `summ_render=abstractive`),
followed by `SUMMARY_NOTE_TOKENS` when the readouts are token lists. `DIGEST_TASK_NOTE` is what
the digest's `summ_variant=task` is told about this family (the task type only; never the
program, its source or the bug).

`INFER_USER_SUMMARY`:

```text
{summary_note}

readout digest:
{summary}
```

`DIGEST_TASK_NOTE`:

```text
the model reads a short program shown bare, with nothing asked; the readouts are taken at the program's last token
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
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of interchangeable words or names of one kind (numbers, months, colours, countries, cities, people, works, ...) singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it.
```

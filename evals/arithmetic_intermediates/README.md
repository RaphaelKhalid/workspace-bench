# arithmetic_intermediates

`Compute (271 - 322) * 14. Reply with only the final number, nothing else.` The model answers
with no chain of thought; the intermediate (−51) is never written. Each variant fixes one
expression shape and one frozen (layer, position) cell, pre-registered from a sweep in the
source repo. Can a readout assert the intermediate anywhere in the prompt?

**Read plan (plan 0032 / plan 0036, decision Q14).** `wsbench plan` emits the chat render, every
position of it (34–42 tokens, `all_from_end`), at **every grid layer** (20, 24, …, 60: 11
layers) for the default `reads=full`; `reads=lite` is the fast mode: the same every-position span
at **layers 56 and 60 only** (`lite_positions = same`, `lite_layers = [56, 60]`; one GPU read
serves both). Camila (2026-10-30): "By default judge at ALL layers not just two (fast/lite mode
should be those two layers)". Each item's frozen cell stays in the row's `extra`. The bank
header's `read` string still says "layers 56 and 60": it is descriptive only (not hashed, not
read by any code) and the plan of record supersedes it.

```
$ wsbench plan families=arithmetic_intermediates                # full: 11 layers
arithmetic_intermediates: 596 items, render ['chat'], positions ['all_from_end'], layers [20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60]
{"id": "absval-052", "render": "chat", "positions": {"kind": "all_from_end"},
 "layers": [20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60], "lite_positions": {"kind": "same"},
 "lite_layers": [56, 60], "extra": {"variant": "absval", "frozen_cell": {"layer": 56, "pos": -7}}, ...}
$ wsbench plan families=arithmetic_intermediates reads=lite     # lite: 56 and 60
arithmetic_intermediates: 596 items, render ['chat'], positions ['lite_of'], layers [56, 60]
{"id": "absval-052", "positions": {"kind": "lite_of", "full": {"kind": "all_from_end"},
 "lite": {"kind": "same"}}, "layers": [56, 60], "extra": {..., "reads": "lite"}, ...}
```

596 items across 14 variants (the source bank's `<variant>.json` files, items unchanged, each
carrying its variant's cell and role; 10 variants were dropped by Agam on 2026-09-16: addmulx,
dec16, halflead, halftrail, halves, maxsel, mulmul, negdec, negdiv8, negdiv8x). Every item was
gated on Qwen3.6-27B (≥ 8/10 sampled correct, no leak: no intermediate appears as a numeral in
the prompt). Bare prompt (no system prompt, no few-shot) through the chat template with an empty
think block — `<|im_start|>user\n…<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n`,
34–42 tokens; the frozen cells −7 / −8 are the assistant-turn `<|im_start|>` and the newline after
`<|im_end|>`.

| variant | shape | items | tolerance | cell | role |
|---|---|---|---|---|---|
| `absval` | `abs(a - b) * c` | 25 | rel5pct | L56, -7 | structural |
| `addmul` | `(a + b) * c` | 43 | rel5pct | L60, -8 | comparison |
| `floordiv` | `floor(a / b) + c` | 21 | exact | L60, -7 | structural |
| `frac` | `(p / q) * (p*q*k)` | 116 | rel5pct | L60, -8 | structural |
| `fracadd` | `(a / b) + (c / b),  b odd, b \| (a+c)` | 63 | rel5pct | L56, -8 | structural |
| `fraccomp` | `((a + b) / c) * (c*e)` | 44 | rel5pct | L56, -8 | structural |
| `fracint` | `(a / b) + (c / b),  b \| a, b \| c` | 32 | rel5pct | L56, -8 | comparison |
| `fracsmall` | `(a / b) + (c / b),  a,c single-digit, b \| (a+c)` | 16 | rel5pct | L56, -8 | comparison |
| `muladd` | `(a * b) + c` | 35 | rel5pct | L60, -8 | structural |
| `mulmid` | `(a * b) + (c * d),  products 60-100` | 33 | rel5pct | L56, -8 | comparison |
| `sign` | `(a - b) * c` | 25 | exact | L56, -8 | comparison |
| `signpair` | `(a - b) * c` | 23 | rel5pct | L56, -8 | structural |
| `subsub` | `(a - b) - c` | 60 | rel5pct | L56, -8 | comparison |
| `subsubx` | `a - (b - c)` | 60 | rel5pct | L56, -8 | comparison |

`role` is the source's reading: a *structural* variant has no single-token route to the
intermediate and can support a claim against token lenses; a *comparison* variant is
single-token reachable and is reported, not averaged into structural claims.

Example: `(271 - 322) * 14` → intermediate -51, answer -714.

## Scoring

- **Modes.** Summary mode (the library default, plan 0024) reads every selected cell of an item
  — every position at every layer of the read (11 grid layers under `reads=full`, 56 and 60
  under `reads=lite`, one layer under `layers=<k>`) — through ONE digest and ONE judge call.
  Native `opts=aggregate=native` has two cell grids: `cells=frozen` (the native default: the
  variant's one pre-registered cell, one call per item; the ATI gate's instrument) and
  `cells=all` (every row, one batched call per (item, layer)).
- **Judge: free recall, prompt-blind.** For each cell (or digest) the judge names the numbers the
  readout presents as computed values, ranked, at most three (ten on a digest), or none (the
  chained-intermediates judge with its task sentence changed to a bare arithmetic expression).
  **No read-site token text reaches the judge in any mode** (native batched since
  `arith-free-batched-2026-10-30`; summary mode never): batched entries are headed
  `[k] pos=<offset>:` only, digest groups `[L<layer> pos <index>]` only. Until 2026-10-30 the
  batched headers carried `token=<the read-site token>`, so over 34–42 entries they spelled out
  the whole expression the prompt says the judge cannot see (Camila: "Remove the token labels").
- **Verification.** A named value is kept only when ONE judged unit writes it — a prose
  generation, or one token list (each token on its own) — as a numeral (any numeral to six
  decimals, list markers and step labels excluded) or, for the top-ranked value only, when the
  judge's quote passes the shared `digest.quote_ok` inside that unit, contains a numeral (digits,
  a Chinese numeral such as 负五十一, or a number word such as `nine`) and is not itself a bare
  number. A multi-digit number is never assembled from separate tokens, within a list or across
  adjacent positions (`2`, `7`, `1` ≠ 271). Token-list quotes may carry the token's own score
  (`九 (15.19)`; `quote_ok` accepts only the real score), so a judge that copies a score no
  longer loses the value. No regex or numeric matcher scores anything: the numerals are read
  only to verify what the judge named.
- **Flat-list void (decision Q4).** A kept value whose every supporting unit is a
  `digest.number_flood` line — a token list with ≥ 5 distinct numbers, or a prose list-shaped run
  of ≥ 5 distinct numbers (commas, `|`, "and", or bullets holding only numbers; the operands and
  results of a stated operation never count) — is singled out by nothing and dropped. A worked
  computation ("252 − 3 = 249, then 249 × 4 = 996 …") is never a flood. `extras.n_flood_voided`
  counts the dropped values and `extras.value_before_flood_void` is the pass rate without the
  void (diagnostic, not the headline). The judge prompt says the same (a bag or list of several
  different numbers singles out none of them, whatever their rank).
- **Pass** (`value` in the source's terms): some kept value lies within the variant's tolerance
  of the headline intermediate (`exact`, or a relative 5%; the source's `tolerance_ok`, sign-
  aware). `extras.top1_rate` is the stricter top-ranked-value rate. Every rule is applied per cell
  (per entry of a batched call) exactly as for a single-cell call: the named value must be written
  in THAT entry's readout.
- **Floors.** No analytic floor. `cross` is the permutation null: the same rule against the
  intermediates of the item's `null_set` (the other items of its variant whose intermediates the
  source kept apart by about four 2% tolerances; the 13 pairs that sit within the 5% used since
  2026-09-23 were dropped from the null sets), averaged over that set; `net = value − cross`.
  `extras.per_variant` gives n / value / cross / net / tolerance / role per variant,
  `extras.per_role` the structural vs comparison split; `extras.committed_rate` the calls that
  named anything. Native runs report the plan-0012 `extras.layer_protocols` (report-only; the
  middle band is 20–52 on the grid). The prompt-only floor is the shared Opus `po-opus-v1`
  protocol (`evals/baselines/README.md`); it is not item-blind here (a reader that sees the
  expression can compute the intermediate), so read every headline against it and on the ATI
  subset.
- **Every-position read (`opts=cells=all`).** The same judge over every (layer, position) row in
  the file, packaged as one call per (item, layer) (`arith-free-batched-2026-10-30`, below); an
  item passes when ANY cell names a value within its tolerance, and the permutation null is
  taken the same way, so `net` stays comparable. An entry the reply skips, repeats or malforms is
  an unjudged cell (`rows[*].unjudged_at`, `extras.n_calls_failed` counts whole calls that
  failed); a reply with no usable entry is re-queued on the next run. `extras.bands` reports the
  any-cell accuracy at two fixed bands beside the variant's own tolerance: `exact` and within 5%
  (`rel5pct`) of the intermediate. `extras.cell_hit_rate` and `extras.per_layer_hit_rate` are the
  per-cell numbers, and each row lists `hits_at`. An any-of-grid rule over hundreds of cells
  inflates the pass rate for that reason alone: read it against `cross`, never alone.
- One cell per item (`cells=frozen`): rows at other layers or positions are ignored and counted
  (`extras.n_rows_off_cell`); `layers=L` overrides the layer for every item (more than one layer
  exits 2). An empty cell is a negative; an unjudged cell leaves its item undecided. Missing cells
  are fatal (exit 2) unless `allow_missing=True`.
- **Full-read guards (plan 0032 §2.6.4).** Under `reads=full` with no `layers=`, every plan layer
  (all 11) must be present for every item and each item's span must be ≥ 34 contiguous positions
  ending at −1 (`min_full_positions = 34`, the shortest render): a file WITH a sidecar that
  holds only layers 56/60 exits 2 naming the first missing (item, layer) (`allow_missing=True` →
  `extras.partial_ids`, `complete = False`). A sidecar-less file (cached v1 readouts, fixtures) is
  report-only (`extras.partial_ids_unenforced`, `config.reads_checked = "no_sidecar"`) and cannot
  reach the site as a full number. Judge cached 56/60 files with `reads=lite`. A file with more
  layers than the plan (e.g. all 64) is judged on all of them.

## Readouts

`{"id": "<item name>", "layer": L, "pos": P, "samples": [...]}` (or `"tokens"` / `"scores"` for a
token lens), one row per (layer, position) cell, `pos` the offset from the end of the rendered
prompt as in the bank (−1 the final `\n\n`, `cell.pos` −7 / −8 the frozen cells), so a file
written for the full read serves `reads=lite`, `cells=all` and `cells=frozen` too.

- **Regime of record since 2026-10-30:** every position of the render (34–42 per item) at the 11
  grid layers — 242,242 cells over the 596 items (22,022 per layer) — with the producer's
  sidecar (`<file>.meta.json`: `reads`, `sampling`, `plan_sha`). Before: layers 56 and 60 only
  (44,044 cells), now the lite read. The NLA and SAE arms carry layer 42 only and are judged with
  `layers=42`, an off-grid diagnostic.
- **One readout per activation (decision Q1; Camila: "Make sure that only a single readout is
  being judged unless the method is a single token olens which should be sampled four times and
  concatenated into bullet points").** The producer declares the kind in the sidecar
  (`sampling`), never inferred from bullet shape: `bullet4` (a single-bullet O-lens, the `*-x4`
  arms) holds four generations of one activation, judged natively as the four generations
  concatenated into bullet points (`readouts.bulleted`) and shown to the digest as four
  `- ` lines under one header, a value verified inside ONE generation; `prose1` (every other prose
  method, s3d-rl600 and NLA included) keeps one generation per activation — an s3d generation
  that itself lists several bullets is ONE readout (its bullets joined by `⁞` in the digest);
  `tokens10` keeps the top 10 tokens. `config.sampling` / `config.sampling_source` record the
  kind and where it came from; `extras.n_samples_trimmed`, `n_packed_ambiguous`, `n_cells_short`
  count what the normaliser did. Cached `*-x4` files (no sidecar) are judged with the override
  `sampling=bullet4 reads=lite` ("cached v1 readouts, judge test only").
- **Until 2026-09-23:** one row per item at the variant's frozen cell (layer 56 or 60, −7 or −8),
  judged `cells=frozen`; those numbers are still reproducible from an all-position file with
  `opts=cells=frozen,aggregate=native`.

Token lenses are shown as their bag (no scores) and verified against the tokens.
`examples/readouts/arithmetic_intermediates.jsonl` holds a few real O-lens rows of four items at
several positions of both lite layers, frozen cells included (one empty cell among them).

```
wsbench judge family=arithmetic_intermediates readouts=examples/readouts/arithmetic_intermediates.jsonl out=outputs/toy/arith dry_run=True
wsbench judge family=arithmetic_intermediates readouts=<arm>.jsonl out=outputs/<arm>/arithmetic_intermediates                       # summary, 11 layers (the run of record)
wsbench judge family=arithmetic_intermediates readouts=<arm>.jsonl out=outputs/<arm>/arithmetic_intermediates-lite reads=lite        # summary, layers 56/60
wsbench judge family=arithmetic_intermediates readouts=<arm>.jsonl out=outputs/<arm>/arithmetic_intermediates-native opts=cells=all,aggregate=native
wsbench judge family=arithmetic_intermediates readouts=<arm>.jsonl out=outputs/<arm>/arithmetic_intermediates-frozen opts=cells=frozen,aggregate=native
```

## Judge prompts

`prompt_version`: `arith-free-2026-10-30+exact-int+keys-union` for the per-cell call (summary mode: `arith-free-2026-10-30+exact-int+keys-union+cons-r3+cons-r4`, see above) (`cells=frozen`, and the base of the
summary stamp) and `arith-free-batched-2026-10-30+exact-int+keys-union` for the batched `cells=all` call (the calls
themselves stay keyed `arith-free-2026-10-30` / `arith-free-batched-2026-10-30`: final r1 re-asks no call) — the two share
their instructions and differ only in packaging, so they carry their own tags; `reads=lite`
appends `+reads-lite`. 2026-10-30 (from `arith-free-2026-09-23` / `arith-free-batched-2026-09-23`):
no token labels in batched headers, neutral readout wording, the shared token-list note
(`mc.token_note(("numbers",))`, rendered from the spec's `flat_types`) plus the no-assembly
sentence, and the numeral-bag rule without its "tight cluster" clause. Judge: the repo default
(`claude-opus-5-5`; the Anthropic route sends no temperature). Per-cell output schema:
`{"states_value": bool, "values": [number, ...], "basis": "arithmetic" | "stated_result" |
"numeral_bag" | "none", "quote": str}`.

`SYSTEM`:

```text
You are reading readouts of a language model's internal activations, written as text or as lists of tokens. The model is silently evaluating a short arithmetic expression: two or three operations
on given numbers, answered with no chain of thought. You do NOT get to see the expression — only
the readout.

The readout may be free text, bullet points, or a bag of loose tokens, possibly in several
languages (Chinese numerals like 十四 mean fourteen). It is often vague, generic, or about
something else entirely, and it frequently contains numbers that are not results of anything.

Your job: name the number(s) that this readout presents as a COMPUTED VALUE — a result, an
intermediate, a total, a "the answer is X". Rank them, most clearly a computed result first,
at most three. Decimals and negative numbers are values too; report them exactly as written.

Rules:
- Do NOT list numbers that appear as operands, quantities, labels, list indices, years, counts
  of items, or parts of unrelated prose. Only numbers the readout presents as something that was
  worked out.
- If the readout states arithmetic with both operands and a result ("16 - 2 = 14"), list the
  RESULT (14), not the operands.
- A bag of loose numerals with no arithmetic around them counts only when it is dominated
  by ONE value (several of its tokens write the same number, e.g. 九 | nine | 9): list that
  value. A bag or list of several different numbers singles out none of them, whatever their
  order or rank.
- If the readout presents no number as a computed value, set states_value false and return an
  empty list. That is a normal and common answer — do not invent one.
- Never do any arithmetic of your own. You do not know the task, so you cannot know what the
  right answer is; only report what the text itself puts forward.

Token lists. A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of numbers, or of any other words or names of one kind, singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it. A number is never assembled from separate tokens: digits on one list or at adjacent positions (2, 7, 1) are not the number 271.
```

`USER`:

```text
Readout:
<<<
{readout}
>>>

Which number(s) does this readout present as a computed value?
```

### Batched `cells=all` call — `arith-free-batched-2026-10-30`

Camila (2026-09-23 06:14 UTC): "for user modeling and arithmetic let's just batch it — feed it
everything at once!" One call per (item, layer) lists every non-empty position of that layer, in
position order, as entries `[k] pos=<offset>: <readout>` separated by blank lines (a token lens's
bag as `tokens: tok | ...`), and the judge answers one result per entry. Output schema:
`{"entries": [{"k": int, "values": [number, ...], "basis": "arithmetic" | "stated_result" |
"numeral_bag" | "none", "quote": str}, ...]}`.

`SYSTEM_BATCH`:

```text
You are reading readouts of a language model's internal activations, written as text or as lists of tokens. The model is silently evaluating a short arithmetic expression: two or three operations
on given numbers, answered with no chain of thought. You do NOT get to see the expression — only
the readouts.

You are given several readouts at once, one per position of the prompt that was read, as
numbered entries "[k] pos=<offset from the end of the prompt>:" followed by that entry's readout
(a bag of loose tokens is written as "tokens: ..."). Judge every entry on its own; the entries do
not explain each other, and an entry's header is not part of its readout. The one exception is
the token-list note below: tokens of adjacent entries may be joined only to spell one word split
across them, never to assemble a number.

A readout may be free text, bullet points, or a bag of loose tokens, possibly in several
languages (Chinese numerals like 十四 mean fourteen). It is often vague, generic, or about
something else entirely, and it frequently contains numbers that are not results of anything.

Your job, for EACH entry: name the number(s) that its readout presents as a COMPUTED VALUE — a
result, an intermediate, a total, a "the answer is X". Rank them, most clearly a computed result
first, at most three. Decimals and negative numbers are values too; report them exactly as written.

Rules, applied to every entry on its own:
- Do NOT list numbers that appear as operands, quantities, labels, list indices, years, counts
  of items, or parts of unrelated prose. Only numbers the readout presents as something that was
  worked out.
- If the readout states arithmetic with both operands and a result ("16 - 2 = 14"), list the
  RESULT (14), not the operands.
- A bag of loose numerals with no arithmetic around them counts only when it is dominated
  by ONE value (several of its tokens write the same number, e.g. 九 | nine | 9): list that
  value. A bag or list of several different numbers singles out none of them, whatever their
  order or rank.
- If a readout presents no number as a computed value, return an empty list for that entry. That
  is a normal and common answer — do not invent one.
- Never do any arithmetic of your own. You do not know the task, so you cannot know what the
  right answer is; only report what each text itself puts forward.
- Answer with exactly one result per entry, carrying the entry's k, in the order given; the
  quote is the shortest verbatim span of THAT entry supporting its top value (empty if none).

Token lists. A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of numbers, or of any other words or names of one kind, singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it. A number is never assembled from separate tokens: digits on one list or at adjacent positions (2, 7, 1) are not the number 271.
```

`USER_BATCH`:

```text
Readouts, one per read position:

{entries}

For each entry, which number(s) does its readout present as a computed value?
```

## Summary mode

`aggregate=summary` (plan 0020; the default since plan 0024, `opts=aggregate=native` opts out). **The hook:**
after the cell selection and the missing-item accounting, every cell the item has — every
position at every selected layer — goes to ONE passive digest call (`digest.collapse`, spec
in `docs/summarizer.md` § Item digest, told the family's task note), and the item is judged ONCE
on that digest.

- **Every cell, forced.** Summary mode forces `cells=all`: the frozen cell is a sweep-picked best
  cell, and summary mode reads every position and layer. An explicit `opts=cells=frozen` with
  `aggregate=summary` exits 2; under the summary default, `cells=frozen` needs
  `opts=cells=frozen,aggregate=native`. `n_expected` / `n_missing` are counted on the real cells before the
  hook, exactly as native `cells=all`, so `require_cells` behaves as native.
- **Judged unit:** one call per item with `SYSTEM_SUMMARY` and `USER_SUMMARY` below
  (the `USER`'s input is the digest, preceded by the digest note: `SUMMARY_NOTE_NO_RARE`, or
  `SUMMARY_NOTE_ABSTRACTIVE_NO_RARE` under `summ_render=abstractive`, plus `TOKEN_NOTE` when the
  source readouts are token lists). The judge-call key is `<id>|L-1`.
- **Rule changes and why.** The pass rule is unchanged (some kept value within the variant's
  tolerance), but a value is kept only when it is written inside ONE of the digest's evidence
  samples (the whole readout samples the digest selected, a token line's tokens one by one); a
  value that only the summarizer's statement carries never counts. A pooled digest offers more
  numbers than one cell does, so the paired `cross` null is taken from the same kept values on
  the same digest under the same rule: the floor moves with the pass rate, and `net` stays the
  comparison.
- **Operands and the first-number consensus (audit F11, 2026-10-31).** The numbers digest is
  told the item's operands: it asks for 4 spare numbers, and a key that restates an operand
  takes one of the five judged slots only when no other number is left. A number that at least 3
  of the 4 samples of ONE activation begin with (`digest.consensus_claims`) is a counted claim:
  its line is marked `first number of K of N samples at [L<layer> pos <index>]`, and it fills a
  slot the summarizer left free (never an operand; never more than five slots; round 3: marked
  numbers rank first, see below). The summary judge reads that mark (`CONSENSUS_RULE` in `SYSTEM_SUMMARY`). Decision (Fable, 2026-10-31): the
  mechanical consensus is NOT the headline; the headline stays this judge.
- **Round 3 (`+cons-r3`, summary mode only; calls keyed `arith-free-2026-10-30+cons-r3`, so every
  summary call is re-asked).** The all-layer judge ignored `CONSENSUS_RULE` in long digests (30-44
  union keys): in 64/596 items the gold was a marked key, yet the judge named only right-hand
  results ('87 + 88 = 175' gave 175, not the marked 87), so all-layer (0.413) scored below lite
  and L56 (0.455) although its keys are the union of theirs. Two changes, the headline still
  being the judge (Fable F11): (1) the judge's user turn opens with a `CONSENSUS VALUES` block
  listing the digest's consensus-marked number keys (`judge.consensus_keys`), and
  `CONSENSUS_RULE` tells the judge to name each of them; (2) in the numbers cap
  (`digest.rank_numbers`) consensus-marked numbers rank BEFORE the unmarked summarizer numbers, so
  the 5-per-layer cap never cuts a consensus value while it keeps an unconsented one (fracadd-013
  L56: 108 leads 4 of 4 samples, but its line was keyed 216 and the filled 108 fell past the cap);
  the slot count is unchanged. Re-judged on the final O-lens readouts: all-layer 0.413 -> 0.562
  (cross null 0.064 -> 0.074, net 0.349 -> 0.488), L56 0.455 -> 0.495, L60 0.404 -> 0.515, so
  all-layer is again above every single layer. All 17 audit ids pass at all-layer (addmul-003,
  mulmid-056, addmul-007, addmul-032, fraccomp-009, fracadd-033, addmul-012, addmul-049,
  subsub-009/049/043, fraccomp-066/107/053, fracadd-013, fracadd-076, fracint-051). The re-ask
  also moves some cells the other way (all-layer 12 pass -> fail against 101 fail -> pass).
  Native runs and the ATI gate are unchanged (`NATIVE_PROMPT_VERSION` =
  `arith-free-2026-10-30+exact-int+keys-union`).
- **Round 4 (`+cons-r4`, summary mode only, deterministic; Camila r2 / ANSWERS_R2 §9: "the
  judge must use the consensus marks").** At `+cons-r3` the all-layer judge still left out a
  marked value in 8 items whose gold led 3-4 of 4 samples of one activation (absval-093,
  absval-338, fracadd-058, fraccomp-069, fraccomp-134, fracint-029, mulmid-079, subsubx-012).
  Two fixes: (1) the consensus mark now survives the per-layer merge of a union digest
  (`digest.merge_grounded` keeps any member's mark; the best-supported member often had none, so
  the merged line lost it and the value was missing from the `CONSENSUS VALUES` block: those
  items' judge calls are re-asked); (2) every digest key that is a first-number consensus
  (marked, or whose value is a consensus of one activation of the item's own raw cells,
  `judge.consensus_of`) is counted among the values the judge names (`judge.verdict`
  `consensus=`: appended after the judge's own values, then the same key / support / flood
  checks; `n_consensus_added` per row). Gold-blind: it adds every consensus value, so the cross
  null sees them too. Re-scored on the cached final O-lens readouts: all-layer 0.562 -> 0.576
  (cross 0.074 -> 0.076; all 8 items pass; 11 fail -> pass, 3 pass -> fail from re-ask noise on
  items with no gold consensus), L56 0.495 and L60 0.515 unchanged (single layers merge
  nothing, and their judge named every marked value). After the change no item whose gold is a
  raw first-number consensus fails at all-layer (0 of 303).
- **Consensus band (diagnostic).** `extras.consensus_band` (both modes) is the raw-readout rate
  of "at one activation, at least 3 of the 4 samples begin with a value within tolerance of the
  intermediate", the item's own operands excluded, with `cross` = the same rule applied to the
  null set's intermediates and `net` = rate - cross; rows carry `consensus_values`,
  `consensus_hit`, `consensus_exact`, `consensus_cross`. Reported beside the headline, never in
  it. On the final-olens-rl600-x4 readouts: 0.668 against a null of 0.125.
- **Item states.** An item with no cells keeps the native missing path (undecided, `kind:
  "missing"`). An unsummarized item (failed / unparsable digest, or every digest item failing the
  evidence check) or a failed judge call is undecided and counted in `n_unjudged_cells`. An empty
  digest (every cell blank, or zero digest items) is a judged fail with no call, counted in
  `n_empty_cells`. Unjudged / empty are counted in items, expected / missing in cells
  (`extras.summary.count_units`).
- **Omitted in summary mode:** the per-cell diagnostics `per_layer_hit_rate`, `cell_hit_rate`,
  `hits_at`, `unjudged_at`, `earliest_layer`, `layer_protocols` and the frozen `layer` / `pos`
  row fields. Rows gain `summary`, `summary_statements`, `summary_evidence`, `summary_truncated`,
  `summary_state`; `extras.summary` holds the digest diagnostics.
- **Provenance:** `prompt_version` = `digest.prompt_version(PROMPT_VERSION, args, NAME)` (the
  per-cell version plus the digest and summary-judge stamps; `+reads-lite` under `reads=lite`);
  `config.aggregate = "summary"`, `config.summarizer`, `config.source_kind`. Use a separate `out=`
  dir from any native run.
- **Five-number digest (plan 0022).** This family defaults to `summ_numbers=5`, `summ_rare=0`:
  the digest records only the five most prominent numbers (`docs/summarizer.md` § Numbers digest),
  and a judge value is kept only when it is verified in one evidence sample AND written by one of
  those number keys: a judged value must EQUAL one key's value (CJK keys such as 十四 and number
  words such as `nine` are parsed; the judge's quote only verifies a value, it never makes it a
  key). The judge, which sees whole evidence samples but not the keys, may name up to
  `MAX_VALUES_SUMMARY` = 10 values (`SYSTEM_SUMMARY` is `SYSTEM` with "at most three." → "at most
  ten."); the five keys are the bound, so a gold value that is merely one of many numbers in the
  evidence fails. The paired null uses the same kept set. Rows add `digest_numbers` and
  `answer_in_digest` (whether the item's final answer, never gold, took one of the five slots).

`SYSTEM_SUMMARY`:

```text
You are reading readouts of a language model's internal activations, written as text or as lists of tokens. The model is silently evaluating a short arithmetic expression: two or three operations
on given numbers, answered with no chain of thought. You do NOT get to see the expression — only
the readout.

The readout may be free text, bullet points, or a bag of loose tokens, possibly in several
languages (Chinese numerals like 十四 mean fourteen). It is often vague, generic, or about
something else entirely, and it frequently contains numbers that are not results of anything.

Your job: name the number(s) that this readout presents as a COMPUTED VALUE — a result, an
intermediate, a total, a "the answer is X". Rank them, most clearly a computed result first,
at most ten. Decimals and negative numbers are values too; report them exactly as written.

Rules:
- Do NOT list numbers that appear as operands, quantities, labels, list indices, years, counts
  of items, or parts of unrelated prose. Only numbers the readout presents as something that was
  worked out.
- If the readout states arithmetic with both operands and a result ("16 - 2 = 14"), list the
  RESULT (14), not the operands.
- A bag of loose numerals with no arithmetic around them counts only when it is dominated
  by ONE value (several of its tokens write the same number, e.g. 九 | nine | 9): list that
  value. A bag or list of several different numbers singles out none of them, whatever their
  order or rank.
- A digest line whose marker says "first number of K of N samples at [L<layer> pos <index>]" carries a number that K of the N samples of ONE activation begin with: that activation leads with the number as its value. Treat that number as presented as a computed value, even when the sample goes on to use it in further arithmetic. The mark covers only the number it names, and only when K is at least 3; any other number on that line follows the rules above. Every number listed under CONSENSUS VALUES at the top of the readout is such a marked number: include each of them among the values you name.
- If the readout presents no number as a computed value, set states_value false and return an
  empty list. That is a normal and common answer — do not invent one.
- Never do any arithmetic of your own. You do not know the task, so you cannot know what the
  right answer is; only report what the text itself puts forward.

Token lists. A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of numbers, or of any other words or names of one kind, singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it. A number is never assembled from separate tokens: digits on one list or at adjacent positions (2, 7, 1) are not the number 271.
```

`USER_SUMMARY`:

```text
{summary_note}

Readout:
<<<
{readout}
>>>

Which number(s) does this readout present as a computed value?
```

`CONSENSUS_BLOCK` (round 3, `+cons-r3`): prepended to the readout in `USER_SUMMARY` when the digest has consensus-marked number keys (`judge.consensus_keys`), `{values}` = those keys in digest order:

```text
CONSENSUS VALUES (each is the first number of at least 3 of the 4 samples of one activation; its digest line carries the mark): {values}
```

This family runs `summ_rare=0` (the numbers digest), so its notes drop the rare-content clause:

`SUMMARY_NOTE_NO_RARE`:

```text
The readout below is a digest of the readouts across every read layer and position: a note-taker who did not see the passage picked the most prominent readout samples, most prominent first. Each line is marked with how many readout samples state its content ([N samples], or [N samples, M layers] when it was seen at M read layers): counted per claim, so a sample that only lists the word among others of its kind, or only restates the question, is not counted; compare these counts when weighing lines against each other. Each line is one real readout sample (a free-text generation, or one ranked list of top tokens). Treat each line as a separate sample: pieces on different lines never combine. Any quote must be copied from inside one line, without the bracketed marker.
```

`SUMMARY_NOTE_ABSTRACTIVE_NO_RARE`:

```text
The readout below is a digest of the readouts across every read layer and position, written by a note-taker who did not see the passage, most prominent first. Each line is one statement in the note-taker's words, how many samples state it (counted per claim), and a verbatim evidence span from one real readout sample. The statements are not evidence: judge what the evidence spans show, treat each line as a separate sample (pieces on different lines never combine), and copy any quote from inside one evidence span.
```

`TOKEN_NOTE` (`mc.token_note(("numbers",))`, the spec's `flat_types`):

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of numbers, or of any other words or names of one kind, singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it.
```

`TASK_NOTE` (`EvalSpec.task_note`, the digest's task context; no numeral, no number word):

```text
the model was silently evaluating a short arithmetic expression (a few operations on given numbers) and answering with only the final number, with no written working
```

## Final r1 (2026-10-31): exact integers, per-layer number keys

- **Exact match for integer golds.** An integer gold now matches `exact` at any magnitude,
  whatever its variant's tolerance (`judge.item_tolerance`; the bank value is kept as
  `rows[].tolerance_bank`); a non-integer gold (0.777778) keeps its variant's tolerance. Under
  rel5pct integer golds credited off-by-one / off-by-few / rounded numbers: at L44, 34 of 69 passes
  were near-misses on golds below 100 (48 for 50 in subsubx-032, 23 for 22 in subsubx-057, 73 for
  71 in subsubx-021). The first cut stopped at `|gold| < 100`, which left the same leniency on large
  golds (fourth review of #203): on the frozen final-olens-rl600-x4 rows, passes on integer golds
  >= 100 with no exact value were 39 of 78 all-layer, 36 of 67 at L56 and 2 of 3 at L44 (300 / 299
  for 301 in absval-052, 680 for 681 in absval-337, 150 for 154 in absval-339, 157 for 156 in
  fracadd-055, 1549 for 1599 in muladd-097). Re-scored on those rows (old joint keys, so an
  estimate of the effect, not a re-judged headline), the exact-integer rule takes the pass rate
  from 0.440 to 0.347 all-layer, 0.525 to 0.455 at L56 and 0.116 to 0.055 at L44. The item's cross
  null takes the same tolerance; `extras.bands` keeps the `exact` / `rel5pct` columns beside the
  headline. Stamp `+exact-int+keys-union` (the calls keep their `arith-free-*-2026-10-30` keys);
  the ATI entry was re-gated from the cached panel verdicts under it (166 ATI, unchanged ids).
- **The numbers digest keys are the union of the per-layer keys** (`digest.NUMBERS_UNION_FAMILIES`).
  A multi-layer config digests each read layer separately (the same digest a single-layer run makes,
  cache key `digest:<id>|<layer>`), ranks each layer's numbers to its own five slots (operands
  demoted, that layer's first-number consensus seated), and merges them; nothing is re-ranked across
  layers, so the judged keys are exactly the union of the keys single-layer runs would judge (at most
  5 per layer). The judge may then name as many values as there are keys (`prompts.system_summary`,
  never fewer than ten), so the value cap never drops a gold key. The joint five-key all-layer digest
  crowded out the gold: in 95 of the 102 items passing at L56 but failing all-layer, the gold was not
  a key. The cross null is computed from the same kept values, so it rises with the larger key set.

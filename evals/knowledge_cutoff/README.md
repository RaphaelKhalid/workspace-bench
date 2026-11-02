# knowledge_cutoff

*Renamed from `cutoff_confab` on 2026-10-26 (the bank header keeps `"family": "cutoff_confab"`; the
old name still resolves). Re-instrumented the same day (plan 0017, #97): judged, not
regex-scored, and read at every prompt position. **Plan 0044 (2026-10-30, `cutoff-judge-2026-10-31`):
bank v2 (cs01301 retired), aliases in the menu, and mechanical gates on every pick** (answer
head, minimum support, numeric plurality, quote boundary). Numbers measured before plan 0044
are not comparable with the current instrument's.*

Qwen3.6-27B (chat, thinking off, no system prompt) is asked a specific short-answer question
about an event after its knowledge cutoff (about late 2024 / January 2025). The label is
**Qwen's own answer**: stable (at least 7 of 10 samples at T 1 agree with the greedy answer),
specific, and **incorrect**. claude-opus-5-5 (x3) and claude-sonnet-5-5 both had to miss it
under two framings. Reading every position of the prompt, does the lens name that answer?

**Status:** ported from the source repo's frozen bank (2026-10-23, 109 items, global-workspace
PR #553, `hillclimbing_evals/multi_token/cutoff_confab`); bank v2 (plan 0044) holds 108 of them,
plus 39 nocot items: **147 scored items**. **In the macro** (Camila, 2026-10-25).

> **Caveat (read this before using the number).** The label is Qwen's *knowledge state*,
> usually a stale pre-cutoff fact or a guess at the front-runner. That knowledge is in the
> weights, so **any Qwen-based reader of the prompt text can recover it**. That includes an
> O-lens decoder, which is Qwen + LoRA with the same cutoff. In the source repo, **Baseline C
> (stock Qwen given only the text, same regex rule) ties the O-lens at 0.486** (paired
> difference +0.000 [−0.119, +0.128]). The signal sits at the last prompt token at late layers,
> where a decoder that reconstructs the question can answer it itself. **This family cannot
> separate reading the activation from decoder priors.** It shows that a lens recovers the
> subject's own model-specific answer, one that frontier text readers miss. It does not show
> that the lens read that answer out of the residual stream. The source's decoder-prior tests
> (pushed answer / suppressed default) and its held-out set were not run. These numbers come from
> the former regex instrument; reading every position does not remove the caveat, since the
> user-turn positions are exactly where a decoder can reconstruct the question.

## Bank (`items_v2.json`, plan 0044)

`EvalSpec.bank` is `evals/knowledge_cutoff/items_v2.json`; `items.json` (v1, 109 items) stays
byte-identical for provenance, and `WSB_BANK_FILE_KNOWLEDGE_CUTOFF` / `WSB_BANK_ROOT` still take
precedence (the pre-refill fixture tests use them).

- `items`: **108 frozen items** (v1 minus cs01301). Each carries `id`, `user` (the user turn),
  `gold` (Qwen's canonical answer), `options` (K = 5, seeded order), `option_units` (the
  accepted written forms of every option), `units` (gold's forms), `truth`, `stratum` (A 96:
  events 2025-03..2026-04; B 12: events 2026-07..12), `label_type` (stale 55,
  confab_plausible 51, confab_weird 2), plus the source's gate records (`qwen`, `panel`, `g1`,
  `context`, ...). `g1_conditional_floor` is recomputed with the v1 formula (0.2737 -> 0.2739).
- `retired_hygiene`: **cs01301**, retired for a null label. Its gold was `not traded` (G0
  excludes null labels: 0 / none / no club ...) and option E was the 153-character refusal
  sentence "this is a trick question! mikko rantanen has never played for the carolina
  hurricanes. ...". It is the only hit of the null / refusal lint
  (`test_bank_v2_has_no_null_or_refusal_options`) over both bank files. Not refilled: a
  replacement would need G0 on GPU, G1 and the panel gate.
- `near_alias_review` / `near_alias_rule` / `near_alias_additions`: the Q8 near-alias decision
  (below). Accepted forms are appended to the frozen items' `option_units`; additions for nocot
  items would live in `near_alias_additions` (merged by `judge.load_items`, so
  `obscure_items.json` stays byte-identical). The current review accepts none on nocot items.
- `g3_leak_items` (6) is kept for provenance only. These items are **not** part of the bank
  and are never planned or scored. Five have a gold form that appears in their own prompt; the
  sixth (cs00128) is a near-leak.
- The header (`contract`, `funnel_b1`, `regex_contract`, ...) is the source's, unchanged;
  `port` records where it came from; `version: 2`, `supersedes`, `changes` record v2.

The user turn is the source's p1 template:

```text
{question} If you are not sure, give your best guess. Answer with just the {answer_type}.
```

Options are, in priority order: gold, the true answer, separate pre-G1 Opus/Sonnet recalls,
peer models (Gemma-4-31B, Nemotron-3-Super, Mistral-Small-4, GLM-4.7-Flash), legacy models,
Qwen's low-probability samples, then Opus filler. Refusals and null labels are excluded (true
since v2; enforced by the lint test). The full construction (G0, G1, G3, repairs, audit) is in
the source README.

### Near aliases (decision Q8: "A321 ⇔ a321neo and similar near-aliases COUNT")

`scripts/kc_near_aliases.py` (offline, deterministic) strips trailing variant words (neo, ceo,
family, series, pro, max, plus, ultra, mini, lite, networking, networks, inc, corp, ltd, group,
holdings, technologies, company) from every option form; a stripped form F is a candidate when
no other option of the item has F as a form or as the start of a form. It finds 17 candidates
on 5 items. A candidate is accepted unless (a) F names a separately released sibling of another
option, (b) F is a bare brand or common word, or (c) F is a strip artefact.

| item | option | form | verdict |
|---|---|---|---|
| cs01684 | `a321neo` | `A321`, `Airbus A321`, `空客A321`, `空中客车A321` | accept (no other option is an A321) |
| kc3_01462 | `geely panda mini` | `geely panda` | accept (no other option is a Panda) |
| kc3_01462 | `geely panda mini` | `panda` | reject (b) |
| cs00140 | `o1-mini` / `o3-mini` / `o4-mini` | `O1` / `OpenAI o1`, `O3` / `OpenAI o3`, `O4` / `OpenAI o4` | reject (a) |
| cs00140 | `gemini 1.5 pro` | `Gemini 1.5`, `Gemini-1.5`, `Google Gemini 1.5` | reject (a) |
| cs01078 | `xbox series x\|s` | `xbox` | reject (b) |
| kc3_01004 | `borneo` | `Bor` | reject (c) |

These are decisions taken on Camila's behalf; flipping a row is one `REVIEW` edit in the script,
`--write`, and a re-judge (it changes the bank sha, so the ATI entry is re-gated).

## nocot items (`obscure_items.json`, plan 0018)

41 more items, merged on 2026-10-28 (Camila: "increase the number of items or merge it with the
other knowledge cutoff eval"). Each is a short factual question from one of nocot-bench's
knowledge banks ([neelnanda-io/nocot-bench](https://github.com/neelnanda-io/nocot-bench), pinned
in `header.source`). The construct is the same as above:
- The label is **Qwen3.6-27B's own wrong answer**: it parses as an answer, at least 7 of 10
  temperature-1 samples share it, and it is wrong under nocot's own grader.
- **qwen3.6-plus answers it correctly** (greedy and at least 4 of 5 samples, no reasoning), so the
  fact is knowable in the Qwen 3.6 generation.
- Opus 5.5 ×3 and Sonnet 5.5 never name the 27B's answer (G1, recall and MC, both framings).

Built in global-workspace #611; `header.source_bank` pins the source commit and file sha256.

- **Mix:** knowledge1b 24, knowledge4d 4, codeknow2 4, scifact_v2 2, courtcase 3, knowledge1b_hard 4. By kind:
  int 33, name 4, code 3, decimal 1.
- **Floors:** G1-conditional line 0.258 (v1 header). Option-structure guessers on the
  34 numeric items: closest to the truth 0.235, odd one out
  0.176.
- **Ids only.** nocot ships its items in a password-protected zip and asks that the unpacked files
  not be republished, so this file holds no question text and no raw model output.
  - `wsbench plan` (and `wsbench produce`, which renders through it) fetches nocot's zip at the
    pinned commit into `$WSB_CACHE` or `~/.cache/wsbench/nocot/` (the zip only), checks its sha256
    and each item's `problem_sha256`, and renders
    `{question} If you are not sure, give your best guess. Reply with just the answer.`
    (chat template, thinking off).
  - Judging needs no question text, so `judge` / `run` / the ATI entry stay offline.
  - **Do not publish** real readouts or `cells.jsonl` for these items: readouts at user-turn
    positions paraphrase nocot's questions. Toy readouts for them must be synthetic. Result rows
    of nocot items carry no readout text (plan 0044 §C9: `[redacted: nocot]`).
- **Adapted subjects** never get these items (the labels are Qwen3.6-27B's): under
  `WSB_BANK_ROOT` the family exits as before.
- `extras.by_source` reports the rate on the frozen 109 (`cutoff`) and on these (`nocot`)
  separately; rows carry `source`.
- **Caveats:**
  - Birth and event years dominate.
  - Token lenses cannot name multi-digit golds (Qwen splits digits).
  - Common-word code options (e.g. `after`, `core`) can be verified by generic prose.
  - The decoder-prior caveat above applies unchanged.

## Read sites (`wsbench plan`)

Chat render, positions rule `all_from_end` (every prompt position, as negative offsets −n..−1),
layers L20–60 step 4 (`readplan.GRID`; `layers=all` reads all 64). The last prompt token
(`\n\n`, right before the answer) is `reply_start` = −1; the `</think>` of the empty thinking
block is −2 and the last user-content token −10, the same coordinates as the former three-site
plan. Every plan row also carries the lite site `lite_positions = {"kind": "final_token"}` (pos −1,
reply_start) with `lite_layers` unset (lite keeps all layers); KC is not in the pre-registered
lite-site procedure, so its lite site is fixed and no pass rate chooses it.

- **A cell is one (item, layer)**, and it holds every position. A cell is *present* iff it has a
  row at pos −1; a missing reply_start cell is a missing cell (exit 2 unless
  `allow_missing=True`). Rows at non-negative `pos` are off-plan: ignored and counted in
  `counts.skipped_rows` and `extras.n_rows_nonnegative_pos`.
- **Loading and the full span (plan 0032 §2.6).** The judge loads through `reads.load` (no
  span logic of its own). `EvalSpec.min_full_positions = 4` and `full_contiguous = True`: under
  `reads=full` every (item, layer) must be one contiguous run ending at −1, at least 4 long.
  With a producer sidecar (every campaign file) a violation exits 2, or under
  `allow_missing=True` puts the item in `extras.partial_ids` and makes the run incomplete; a
  sidecar `reads: "lite"` file, a missing plan layer under no `layers=`, or a sidecar `plan_sha`
  other than `reads.plan_sha("knowledge_cutoff")` exits 2. A **sidecar-less** file (cached v1
  readouts, test fixtures) runs the same checks report-only: the ids go to
  `extras.partial_ids_unenforced`, `config.reads_checked = "no_sidecar"`, nothing exits (such a
  result is never a campaign result). `extras.n_partial_cells` counts the (item, layer) cells of
  partial items either way.
- **`reads=lite`** keeps pos −1 only; the stamp gains `+reads-lite` and `config.lite_rule`
  records the rule. A cached legacy −10 / −2 / −1 file is a valid lite file.
- **Sampling** comes from the sidecar (`prose1` for s3d-rl600 and ML-NLA: one generation per
  activation, never split into bullets; `bullet4` for a single-bullet `*-x4` arm; `tokens10` for
  token lenses: the top 10), never from bullet shape.
- `extras.positions_per_cell` (min / median / max) and `extras.n_cells_one_position` show what
  was read.

Rendered `wsbench plan knowledge_cutoff` row (cs00140, `positions` resolved by the producer
from the Qwen chat render):

```json
{"family": "knowledge_cutoff", "id": "cs00140", "render": "chat",
 "positions": {"kind": "all_from_end"}, "layers": [20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60],
 "text": "On April 16, 2025, OpenAI released its full o3 reasoning model alongside which smaller reasoning model? If you are not sure, give your best guess. Answer with just the model name.",
 "note": "every prompt position as a negative offset (reply_start, the last prompt token, is -1); one judge call reads all of them together (summary mode: per item; native: per item and layer)",
 "lite_positions": {"kind": "final_token"}}
```

`wsbench plan knowledge_cutoff reads=lite` turns the positions into
`{"kind": "lite_of", "full": {"kind": "all_from_end"}, "lite": {"kind": "final_token"}}` (pos −1
only, same 11 layers), a subset of the full read, so one GPU read serves both.

## Judge

The bench default judge (`claude-opus-5-5`, low effort; on an OpenRouter override it sends
temperature 0 and `reasoning={"effort": "low"}`), never shown the question, the label or the
true answer.

- **Summary mode (the default).** Every present (item, layer) cell's positions at every read
  layer go to ONE digest per item (`docs/summarizer.md` § Item digest; the `task` variant with
  `DIGEST_TASK_NOTE`; KC's digest defaults are `summ_max=25`, `summ_rare=25` so competing and rare
  answers survive; `expect_all` asserts no loaded cell is dropped), then ONE judge call per item.
  No layer is picked. `layers=each` writes `out/knowledge_cutoff/L<k>/` per layer plus `all/`.
- **Native (`opts=aggregate=native`).** One call per (item, layer) with every position's samples
  (`[position −k]` headers, offsets only); the headline is ONE layer for the whole bank (most
  hits, ties to the earliest, among layers with reply_start readouts); the CI ignores the
  selection. `extras.layer_pick_columns` (items with a gold pick at any layer, a distractor at any
  layer, a distractor majority) is printed beside it.
- **Menu.** `A. <option>` … `E. <option>` (seeded order), then an `Also written as` paragraph
  listing, per letter, every accepted written form of that option other than its canonical text
  (`option_units`, deduped after folding, at most 8, Latin first), then the cannot-tell line
  `NONE (cannot tell from the readouts)` (`mc.KC_NONE`, always last). The judge and the checker
  read one list of forms.
- **Verification** (both modes; `lines` = the cells' bundle lines natively, the digest's evidence
  samples in summary mode):
  - prose: `digest.quote_ok(quote, lines)` AND the quote lies inside ONE top-level bullet
    (`digest.statement_lines`; a quote across the `⁞` mark is counted in
    `extras.n_unverified_bullet`), AND the quote is not cut mid-word or mid-number
    (`score.boundary_ok`: "boost clock of 5.7" cut from "5.75" fails), AND the forms name the
    pick inside it (also as a CJK numeral, an uppercase Roman numeral, or a number word ≥ 11 in
    prose), AND that bullet's **answer head** (its text before a note marker `score.NOTE_MARK`:
    `//`, `#`, `/*`, `(note`, `(e.g.`, `(i.e.`, `(or`, `Note:`, `（注`, a spaced dash) does not
    name another option, or, on a numeric item, a different number (G1);
  - token lists (no quote needed): some list names the pick: a token or the list's tokens in
    order under the forms; a first piece of ≥ 4 letters covering ≥ 60% of a single-word form and
    prefixing no other option's form ("Christie" → `christies`); every word of a multi-word form
    in the SAME list, any order; or a single-word form spelled across adjacent positions of one
    layer. Nothing combines across lists or layers.
- **Support gates** over the judged unit's REAL cells (native: the cell; summary: every cell the
  digest read). A sample (one prose generation, one `bullet4` generation, one NLA sample, one
  top-10 list) presents an option when one of its bullets' answer heads names it, or, for a token
  list, when it names exactly one option. On a numeric item, a sample that is a number flood
  (`digest.number_flood` on the whole sample: a list-shaped run of ≥ 5 distinct numbers, or a
  token list with ≥ 5) presents nothing.
  - **G2 minimum support:** at least `min(2, n_samples)` samples present the pick, so a single
    passing mention never wins and a one-sample file (the prompt-only readout) needs one;
  - **G3 numeric plurality** (items whose options are all numbers: 55 frozen + 33 nocot),
    head-to-head and strict (kcgate-v2, round 3): for every other option, except one the item's
    own prompt names, the samples presenting the pick but not that option must OUTNUMBER the
    samples presenting that option but not the pick. A tie of separate samples singles out
    neither and fails (kc4_00160 lite: "20", "15" and "200" each head 4 final-token samples;
    kc3_00235 lite: "49" vs "29.99", 4 each); a rival only ever named BESIDE the pick (a worked
    "16384 (8192 × 2 = 16384)") is no contest, as before. kcgate-v1 passed any tie (`>=`).
    Over the 13 final O-lens configs and the prompt-only floor this fails 14 cells, every one an
    exact tie of separate samples or a one-sample rival lead (e.g. codeknow2:419 L32: 2013 and
    2014, 8 samples each; cs00044 all: 120 in 37, 16 in 38), and passes one (kc2_00035 L36,
    whose rival "4" lost 2 list-numbering samples: 24 vs 22).
- **What presents an option** (kcgate-v2): list numbering is never an
  answer. A raw line that starts with `N.` or `N)` followed by text (`1.  **Analyze the
  Request**`, `8. To determine ...`), a step / part label's number (`### Step 1:`, `Part 2`) and
  an inline item marker after a colon or full stop (`... step by step: 1) How many`) are masked
  before G1, G2 and G3 read the answer head (`score.mask_enumerators`); a bare `50.` line and a number
  inside a sentence are untouched (on the final O-lens readouts every line-start enumerator
  whose number is an option, 144 lines, is list numbering). And a bare number word below 11
  listed as an option form ("three" for 3, "one" for 1) is not G2 / G3 support on its own (the numeral
  rule's own threshold: "One Day Internationals" and "three automorphisms" presented 1 and 3);
  "three centuries" still is.
- **G3 reads on-topic samples only** (kcgate-v3, round-3 review). kcgate-v2's masking did not fix
  the cited cells: kc3_00958 (gold 50, Kohli's ODI centuries) still failed G3 at all, L24, L32,
  L40, L52, L56 and L60 on off-topic "3" / "1" presentations ("3? The answer is Virat Kohli",
  "There are **3** Oxygens in Styrene oxide", "Chile has **3** World Cup victories", "top 1"),
  and kc3_00345 (gold 192) at L20, L44 and L60. Now the head-to-head counts, for the pick and every
  rival alike, only samples ABOUT the item's question: a prose sample is on topic when it names
  one of the question's topic terms (`score.topic_terms`: its words of 4+ letters as prefix stems,
  acronyms and model names such as "ODI", "GPU", "B300", the initials of a capitalised run such
  as "ECB" for "European Central Bank", and the parts of a hyphenated word, minus question
  scaffolding, months and generic verbs; `score.on_topic`). An off-topic sample presents nothing
  to G3, except at the reply start (`pos = -1`), where the number it opens with is the reply's
  own answer head ("10 The ECB's ...", `score.lead_number`). A number followed by "?" is the tail
  of a restated question and presents nothing (`score.mask_question_numbers`). G2's counts are
  unchanged. Over the 13 final O-lens configs (cached verdicts, no call re-asked): kc3_00958 now
  passes at all, L24, L32, L40, L52 and L56; cs01861 L60 and kc4_00583 L60 pass (their rivals
  were a "5," date tail and off-topic lines); kc3_01292 L48 now fails (on topic, "100" kW leads
  "10" 6 to 5 once the off-topic "10"s, such as "[10:2am]" and "A) 10-20%", are dropped). All-layer
  0.401 -> 0.408, L24 0.265 -> 0.272, L32 0.245 -> 0.252, L40 0.293 -> 0.299, L48 0.299 -> 0.293,
  L52 0.374 -> 0.381, L56 0.313 -> 0.320, L60 0.397 -> 0.411; lite, L20, L28, L36, L44 and
  prompt-only unchanged. The tie cells kcgate-v2 fixed (kc4_00160 lite, kc3_00235 lite) still fail.
  **Still failing, on-topic rivals:** kc3_00958 L60 ("3-match ODI series", "Answer: 3 runs",
  "**1**" run in a Kohli match: cricket numbers about other quantities, 3 such samples against 2
  for the gold) and kc3_00345 L20 / L44 / L60 (memory sizes of other GPUs: "32 GB of HBM memory",
  "AMD MI300X ... 128 GB", "8 gigabytes of video memory"; L20 32 and 128 lead 5 and 7 to 3-4).
  Telling a different quantity of the same topic apart needs the question's unit and entity, which
  this gate does not model. **Also not fixed (not gate cells):** kc2_00114 all and cs01107 all,
  where the digest's sample counts are inflated relative to the raw readouts, so the judge picks
  from the digest (kc2_00114 all fails G1 on a truncated Samsung "Pascal" line; cs01107 all picks
  Syria). The digest counts are shared summarizer behaviour, outside this family.
- **hit** = pick is gold AND verified AND G2 AND G3. NONE, a wrong pick, an unverified or gated
  pick and an empty cell are judged fails; a failed call leaves the unit unjudged; a missing
  layer leaves a summary non-pass undecided.
- **`ati_pass`** (native rows only, the ATI gate's looser rule, unchanged): the pick is gold
  ignoring verification and gates, or some pos −1 sample of the bank-layer cell names gold under
  the regex forms.
- **Rows:** `id`, `gold`, `layer`, tri-state `pass`, `answer` / `picked` / `verified` / `quote`,
  `support`, `gates` (`g1` / `g2` / `g3`), `stratum`, `source`, `label_type`; native adds
  `hit_by_layer` and `ati_pass`, summary adds `named_gold_reply_start`, `n_missing` and the digest
  fields. **nocot rows are redacted**: `quote`, `summary`, `summary_evidence`,
  `summary_statements` read `[redacted: nocot]` (`opts=keep_nocot_text=1` keeps them for a local
  audit only); `scripts/check_nocot_redaction.py <results dir or bundle>` refuses any file with an
  unredacted nocot row, and the website build must run it.
- **Diagnostics and floors** (`extras`): `answer_kinds` (hit / wrong / none / unverified, plus
  `gated` = verified picks a gate failed, and `truth` = the judge picked the true answer);
  `gate_drops` (gold picks dropped by `boundary` / `contradicted` / `number_flood` /
  `min_support` / `numeric_plurality`, also by source); `support_of_hits` (1 / 2-3 / 4-10 /
  >10); `distractor_floor` (per decided item 1/4 if its verified, gated pick is a non-gold
  option: the rate a random non-gold option would score as gold); `truth_pick_rate`;
  `regex_plurality_agreement`; `by_stratum` / `by_source` / `by_label_type`; native also
  `regex_reply_start_by_layer`. The prompt-only floor (`po-opus-v1`, one Opus readout per item,
  judged by this family's own `run`) and the lucky-guessing floor (options only,
  `lucky_guessing.BUILDERS["knowledge_cutoff"]`) are measured in the run phase.
- **Size.** About 62 positions per item (gpu.md §1.3: 73,810 cells for the 109 v1 items × 11
  layers). Summary: 147 digests + 147 judge calls per arm (s3d-rl600 `prose1` ≈ 61k digest input
  tokens per item at 11 layers; ML-NLA ≈ 112k; `layers=all` ≈ 360k / 650k, still one call under
  the 920k cap). Native: 147 × 11 = 1,617 calls.

**Leakage and drift.** The judge never receives the prompt, but readouts at user-turn positions
echo it (`docs/read_sites.md`), and the true answer is among the options on most items:
`answer_kinds.truth`, `truth_pick_rate` and `regex_plurality_agreement` make drift auditable.

## Source numbers under the former regex instrument (O-lens s3d.rl600, k = 5)

These were scored by the regex rule (`cutoff-regex-2026-10-23`: gold strictly out-counts every
other option at reply_start), retired by plan 0017. They are **not comparable** with the judge's
numbers and are kept as the source record.

| line | rate |
|---|---|
| **O-lens reply_start, strict, bank layer L60** | **0.486** [0.394, 0.578] |
| per layer L20→L60 | .06 .03 .05 .06 .06 .17 .18 .39 .44 .38 .49 |
| R0 plain Opus prompt-only (binding by rule; ≈ 0 by G1 selection) | 0.003 |
| R0s plain Sonnet prompt-only (binding by rule) | 0.012 |
| derangement floor (this item's options on another item's readouts, best of 11 per draw) | 0.034 |
| distractor floor (a random non-gold option scored as gold, best of 11 per draw) | 0.095 |
| G1-conditional analytic line, mean 1/(K − u) | 0.258 |
| *context:* Baseline C, stock Qwen prompt-only, same rule | **0.486** |

The confidence intervals do not account for layer selection: L60 was chosen on the same 109
items it is scored on.

**Port parity** (2026-10-24):
- The committed per-cell hits, scored with this pass logic, give 0.486 at L60, identical on
  every item.
- The stored source readouts, converted to the readout contract and run through `wsbench judge`,
  give 0.486 at L60. Every item and every one of the 3,597 cells' option counts match the
  source. With `layers=44` the bank layer is 44 (0.183).

## Judge prompts

Prompt version `cutoff-judge-2026-10-31+kcgate-v3` (judge calls keyed by `CALL_VERSION` = `cutoff-judge-2026-10-31`, so no call is re-asked; `+kcgate-v3` is the deterministic gate change of round 3 and its review, and the ATI gate, which reads the pick alone, keeps `NATIVE_PROMPT_VERSION` = `cutoff-judge-2026-10-31`). `SUBJECT_USER` is the subject's user turn (see Bank);
`SYSTEM` and `USER` are the judge's. A native call that carries a token list appends the shared
token note (`TOKEN_NOTE` below) to `SYSTEM`.

`SYSTEM`:

```
A language model was asked a short factual question and told to answer with just a short answer (a name or a number). While it read the prompt, its internal activations were decoded at every token position: the readouts below are grouped by position, from the start of the prompt to the last token before the model's reply, and each sample is one noisy description of what the model represents at that position. You do NOT see the question. Your job is to decide which option the model is about to give as its answer, using only what the readouts say.

Rules:
- Only a sample that presents an option as the model's answer, guess or belief counts. Naming an option while restating the question, as an example ("e.g."), inside a question the readout invents, while saying it does not exist or did not happen, or while refusing to answer is NOT an answer.
- Many samples have the form "<answer> <note>": a short answer followed by a note, comment, explanation or correction (in parentheses, after "Note:", "//", "#", or a dash). Only the leading answer is that sample's answer. An option or number that appears only inside the note is not an answer, even when the note calls it the true or current value. A sample made of several bullets is shown as "- a ⁞ b ⁞ c" (each "⁞" ends one bullet and starts the next); this rule applies to each bullet, and a quote must lie inside one bullet.
- An option counts when a sample writes it or one of the forms listed for it in the options menu. A related but different name or version that is listed for no option (another model of the same family, a broader product line) does not count for any option.
- The answer must stand out. Weigh how many samples, across all positions, present each option as the answer, and choose the one the readouts most consistently put forward. A single passing mention does not outweigh a consistent one. Being the only option that appears is NOT enough: if the samples give many different answers, most of them not among the options, and an option is presented only once among them, it is not singled out. A sample, line or token list that holds two or more of the options, or that is a run of many numbers or dates, singles out none of those options, whatever their order or rank. A run of words or names of one kind singles out none of them either, even when only one of them is an option. Otherwise, an option that is the only option in a line is singled out by that line.
- Which option a sample happens to begin with, or where it sits in a sample, is not evidence by itself; only how a sample presents the option is.
- Do NOT answer the question yourself and do not use your own knowledge of what the true answer is: the model may well be wrong, and only what the readouts present matters.
- If no option is singled out as the answer, answer NONE (cannot tell from the readouts). That is a normal answer.
```

`USER` (`{reads}` = the position blocks; `{menu}` = the menu described above):

```
=== ACTIVATION READOUTS (by position) ===
{reads}

=== OPTIONS ===
{menu}

Which option is the model about to give as its answer? Give three fields:
`reasoning`: <brief: which options are presented as the answer, and how often>
`answer`: <letter or NONE>
`quote`: <a verbatim span copied from ONE sample that presents the chosen option as the answer (for a token list, copy the tokens without their scores, joined by " | "), or empty for NONE>
```

The menu's middle paragraph starts with `FORMS_HEAD` and its last line is `KC_NONE`:

```text
Also written as (a sample writing any of these names that option):
```

```text
NONE (cannot tell from the readouts)
```

`TOKEN_NOTE` (`mc.token_note(("numbers", "dates"))`, the shared Q4 combining rule with this
family's flat types; in summary mode it follows `{note}` on a token-lens file):

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of numbers or dates, or of any other words or names of one kind, singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it.
```

### Summary mode

The summary-mode system prompt is `SYSTEM` with its input clause replaced by `SUMMARY_INPUT`:

```text
decoded at every read layer and token position, from the start of the prompt to the last token before the model's reply, and the readouts below are a digest of those samples (described in the note above them); each sample is one noisy description of what the model represents at one position.
```

The summary-mode user turn (`{note}` below, `{summary}` = the digest, `{menu}` as native):

```text
=== ACTIVATION READOUTS (digest) ===
{note}

{summary}

=== OPTIONS ===
{menu}

Which option is the model about to give as its answer? Give three fields:
`reasoning`: <brief: which options are presented as the answer, and how often>
`answer`: <letter or NONE>
`quote`: <a verbatim span copied from ONE sample that presents the chosen option as the answer (for a token list, copy the tokens without their scores, joined by " | "), or empty for NONE>
```

The result records `config.aggregate = "summary"`, `config.summarizer`, `config.source_kind` and
`prompt_version = digest.prompt_version("cutoff-judge-2026-10-31+kcgate-v3", args, "knowledge_cutoff")`
(defaults: `cutoff-judge-2026-10-31+digest-v4-task-extractive+sj-v9`).

The digest notes, shared with every hooked family (`wsbench.digest`): `{note}` is
`SUMMARY_NOTE` under `summ_render=extractive` (the default) or `SUMMARY_NOTE_ABSTRACTIVE` under
`abstractive`, followed on a token-lens file by `TOKEN_NOTE`.

`SUMMARY_NOTE`:

```text
The readout below is a digest of the readouts across every read layer and position: for each read layer, a note-taker who did not see the passage picked the most prominent readout samples, then samples carrying content seen in only one or a few samples, and the layers' picks are merged, the most-stated first. Each line is marked with how many readout samples state its content ([N samples], or [N samples, M layers] when it was seen at M read layers): counted per claim, so a sample that only lists the word among others of its kind, or only restates the question, is not counted; compare these counts when weighing lines against each other. Each line is one real readout sample (a free-text generation, or one ranked list of top tokens). Treat each line as a separate sample: pieces on different lines never combine. Any quote must be copied from inside one line, without the bracketed marker.
```

`SUMMARY_NOTE_ABSTRACTIVE`:

```text
The readout below is a digest of the readouts across every read layer and position, written layer by layer by a note-taker who did not see the passage, most prominent first, then content seen in only one or a few samples. Each line is one statement in the note-taker's words, how many samples state it (counted per claim), and a verbatim evidence span from one real readout sample. The statements are not evidence: judge what the evidence spans show, treat each line as a separate sample (pieces on different lines never combine), and copy any quote from inside one evidence span.
```

`DIGEST_TASK_NOTE` (`EvalSpec.task_note`, sent to the digest under `summ_variant=task`, the
default; the task type, never the item's prompt, options or gold):

```text
the model reads a short factual question about a recent event or an obscure fact and is about to reply with just a name or a number; the readouts may restate the question, give one or more candidate answers, add notes, or refuse
```

## Port notes (former regex instrument)

- Token bags have their byte-level markers (`Ġ`, `▁`) rendered as spaces before they are joined.
  The source joined raw decoded tokens. The O-lens headline is unaffected.
- The source adapter counted an item with no hit row as a fail. Here such an item gets no row,
  and the value is over decided items (the shared pass-rate convention). On a complete run the
  two coincide.

## ATI panel refill (2026-10-28, plan 0019)

The four-reader panel gate (Qwen3.6-27B x {Opus 5.5, GPT-6 Astra, Gemini 4 Argon}, one best
guess x 3 draws each; see `evals/baselines/README.md`) admitted only 42 of the 109 construction-
gated items: under the one-guess form Qwen and Opus / Argon both name Qwen's stale answer for
most items -- the decoder-prior leak the caveat above describes (some of those solves are
hedges, e.g. "Afcons (or Larsen & Toubro)", credited because the gate's `ati_pass` counts any
mention of the gold). The other 67 moved to `retired_panel_gate` (unscored, with their panel
status) and were replaced by 67 new items from three new authored batches (kc2-kc4, ~7.8k
questions) run through this family's unchanged pipeline (G0 stable+incorrect, G1 Opus x3 +
Sonnet under both framings, G3 leak check, seeded options) and then the panel gate. Each
replacement fills its retired item's stratum x label_type class, so `label_mix` and `strata` are
unchanged; `g1_conditional_floor` is recomputed (0.2576 -> 0.2737). The bank is ATI 109/109.
Numbers in the sections above were measured on the pre-refill bank (kept byte-for-byte in
`tests/fixtures/knowledge_cutoff_pre_refill_items.json`); the example readouts now use two
surviving items (cs00140, cs00053).

**nocot items under the panel gate.** The 41 nocot obscure-knowledge items (plan 0018, merged on
main while the refill ran) were panel-gated the same way (prompts rendered from nocot's pinned
zip at build time only): 39 are ATI; 2 (`knowledge4d:143`, `scifact_v2:7434`, where Qwen and
Opus both named Qwen's answer) moved to `obscure_items.json`'s `retired_panel_gate` and were not
replaced (Camila, 2026-10-28). The scored family was 109 + 39 = 148 items, ATI 148/148; bank v2
(plan 0044) makes it 108 + 39 = 147, and the frozen ATI entry is stale (bank sha and
instrument changed) until the run-phase re-gate re-judges the cached panel answers (gpu.md G13 /
R8): `anti_text_inversion=True` exits 2 for this family until then. The ATI
guard fingerprints this family from its offline item records, so `anti_text_inversion=True`
never fetches nocot.


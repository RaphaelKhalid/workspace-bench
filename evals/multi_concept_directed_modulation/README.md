# multi_concept_directed_modulation

The model is told to hold one to three unrelated concepts in mind ("Think about the plumber's
blue ladder leaning against the mango tree."), or one person doing something to another ("Think
about Mozart being jealous of Salieri."), and then to write a fixed dictated sentence; the lens
reads the activations at the positions where it is WRITING that sentence. Are ALL the held
concepts there, named in any context (as content, while restating the instruction, or in
passing), and is the relation's direction stated ("Adam being angry at Betty" versus the
reverse)?

**Bank v2 (plan 0034, 2026-10-30): 116 items** in `items_v2.json` (`EvalSpec.bank`; the plan-0025
`items.json`, 100 items, is untouched). The 100 v1 items keep their prompts byte for byte; every
relation item gains `roles` (`agent`, `patient`, `relation`, `cluster`). 16 `entity` items in 8
ab/ba pairs are new (header `new_items_v2`): Camila's five ("think about Mozart being jealous of
Salieri", "batman chasing the joker", "salieri being jealous of mozart", "thor being angry at
loki", "stravinsky being distrustful of schoenberg"), the three reverses that complete her pairs
(`b-moza-ent-*`, `b-batm-ent-*`, `b-thor-ent-*`, `b-stra-ent-*`), and four more pairs so the
stratum reaches the publication minimum of n = 10 (**decision taken, override if you disagree**:
Holmes outwitting Moriarty, Achilles mourning Patroclus, Edison resenting Tesla, Caesar trusting
Brutus completely; fallback = Camila's 8 items, shown with an "n = 8, wide CI" caveat). Each
entity item has `prior_direction` (`ba` for Mozart: Salieri's jealousy is the famous one; `ab`
for Batman, Holmes, Achilles, Caesar; `null` for Thor, Stravinsky, Edison) so
`extras.binding_prior` separates a lens that only reads the famous direction (world knowledge)
from one that reads the instruction. Aliases a readout may use (`the Joker` / `Joker`,
`Schoenberg` / `Schönberg`, `Holmes` / `Sherlock`, `Patroclus` / `Patroklos`) are stored per item.
The items are hand-authored and need no model gating: the render prefills the sentence and the
prompt states the relation. `scripts/mcdm_bank_v2.py` rebuilds the file (`--check` verifies it,
`--golden` re-pins the option lists).

v1 strata (unchanged): 66 dictation items with 1, 2 or 3 concepts (`single` 22, `double` 19,
`novel` 20, `anchor` 1, `chain` 2, `pair` 2), 32 binding items with ordinary first names (`mix`
16, `same` 16, in ab/ba pairs) and 2 controls (`d-none`, `b-none`) with nothing dictated.
**Concept edits** (header `concept_edits`, plan 0025): the bare words `floating` (d-violin),
`seven` (d-cranes) and `chasing` (d-fox-a, d-fox-b) were removed from those items' `concepts`.

## Read regime: chat render, the sentence prefilled, every GRID layer

The item prompt is the **user turn** of the model's chat template (`enable_thinking=False`, no
system prompt), the assistant turn opens with the template's empty `<think>\n\n</think>\n\n`
block, and the dictated sentence is **prefilled as the assistant's text**. The full read is
**every token of the prefilled sentence**: 12 tokens (`The` ` committee` ` will` ` meet` ` on`
` Thursday` ` to` ` review` ` the` ` annual` ` budget` `.`) at every layer of `readplan.GRID`
(20..60 step 4; plan 0032 §2.1.2; bank v2 dropped the v1 header's `layers: [44, 52, 56, 60]`).
`EvalSpec.min_full_positions = 12`, one contiguous run (`reads.check_full`). Any other layer
set is `layers=all|each|<csv>`; the summarizer sees exactly the layers loaded.

**Lite (`reads=lite`)**: the ` to` token only (`offset_from_end k=6`; the sentence is fixed, so
offset 6 is always ` to`), at every full layer. Cached s3d native verdicts (4 layers, plan-0025
judge): all concepts credited at ` to` alone on 27 of 98 items vs 41 over all 12 positions (`The`
19, final `.` 18). Under lite (and for a `prompt_only:` reader) the write-compliance gate is
skipped: a one-token window cannot hold three target words. A lite cell that is not ` to` exits 2.

```
<|im_start|>user
Think about the plumber's blue ladder leaning against the mango tree. Now write this sentence: "The committee will meet on Thursday to review the annual budget."<|im_end|>
<|im_start|>assistant
<think>

</think>

The committee will meet on Thursday to review the annual budget.
```

**Before 2026-09-23 (the bug).** The prompt was rendered bare and followed by a greedy rollout;
the read cells were the last 20 rollout tokens, mixing the sentence, a `<think>` block and a
re-write of the prompt. Camila (2026-09-23) asked for the prefill; the region labels and the
write-compliance gate below are kept as a producer check but remove nothing from a correctly
produced file.

## Scoring

- **Headline: pass rate, every concept named (plans 0025, 0028, 0033).** An item passes when its
  in-sentence readouts, between them, name EVERY dictated concept and never the binding partner
  (the reversed relation, or the other fox item's concepts): inside its one digest call in
  summary mode, over all its judged (layer, position) cells natively. **Any context counts**
  (plan 0034 M4, Camila: "count 'instruction' mentions of the concept as hits", and "if the
  concept is mentioned in any context it should count"): a pick credits whatever its basis
  (`content_bound`, `instruction_narration`, `incidental`); the basis is recorded as a
  diagnostic (`narration_rate`, `incidental_rate`, and `content_only_pass_rate`, the plan-0025
  content-only rule).
- **Synonyms and close relatives count** (plan 0034 M7, Camila on `d-lion`: "for directed
  modulation we can accept synonyms and close relatives as evidence of thinking about the
  concept"): the prompt's worked examples are tuxedo for dinner jacket, seesaw for
  teeter-totter, ice floe for pack ice and damp soil for wet earth (round 5: no worked example
  is a bank concept, below). People's names
  in relation candidates stay exact (aliases above). This is safe only because no close relative
  of a dictated concept is ever offered as a distractor (`distractor_groups_v2.json`).
- **Direction (plan 0034 M3).** A relation candidate (gold, reverse, or relation distractor)
  counts only when ONE quote names BOTH people (`mc.form_in`, aliases included, and the Chinese
  forms of every person in `name_aliases_v2.json`, e.g. "莫扎特" for Mozart; a pick naming
  someone by a Chinese form only is counted in `extras.n_relation_cjk_named`). There is no
  script exemption: "他很生气" or "Adam很生气" does not name Betty, and a person written in a
  script with no listed form (kana, Hangul, Cyrillic) is not named. The quote lies within
  ONE top-level bullet of one sample (`digest.statement_lines`: in a free-text sample the
  bullets are shown separated by ⁞, and a quote across a ⁞ fails). A relation supported only by
  a ranked token list is never credited (an unordered list cannot say who does what to whom), so
  token lenses score 0 on binding items by construction. Drops are counted in
  `extras.n_relation_unverified` (a missing person, or token-only support) and
  `extras.n_unverified_bullet` (both people quoted, but across two bullets). The judge decides
  the direction itself (passive voice counts).
- **Candidates (plan 0034 M5).** Six per item, then `G. cannot tell from the readout`
  (`mc.CANNOT`, always last, never gold). A **relation item** gets six relations: the gold; the
  reverse; the same relation between another pair's people ("Betty admiring Adam"); the same
  people under a relation from ANOTHER cluster, in a random direction ("Oliver resenting
  Ingrid", never always the gold's direction, which would mark the gold); and two other
  relation items verbatim. Clusters (`relation_clusters_v2.json`): anger = {angry at, resenting,
  blaming}, envy = {jealous of}, fear = {afraid of, worrying about, distrustful of}, esteem =
  {proud of, admiring}, and one each for trusting, protecting, teaching, forgiving, betraying,
  owing money to, chasing, outwitting, mourning; a synthesised distractor never shares the gold's
  cluster (no synonym distractors). A **dictation item** draws only non-relation concepts, never
  a close relative of its own; a **control** draws six from everything. Order is a seeded
  shuffle (`mc.seeded_shuffle`, keyed by the item), pinned by
  `tests/golden/multi_concept_directed_modulation_options.json`.
- **Cannot tell (plan 0034 M1).** `G` alone (empty quote) is `kind: cannot_tell` and credits
  nothing; `G` with any other pick is re-asked once, then scored `invalid`.
  `extras.cannot_tell_rate` is the share of judged calls.
- **Quote gate.** Every pick's quote must pass `digest.quote_ok` against the lines the judge saw
  (the digest's evidence samples in summary mode, the cell's own lines natively); a quote
  spanning two samples fails. One exception (round 3, `+pins-r3`, deterministic): a CONCEPT
  pick (never a relation) whose quote elides words inside ONE sample still verifies when every
  sentence / ellipsis fragment of the quote (>= 2) is verbatim in the SAME sample and that sample
  names the concept or its plural (`judge.elided_quote_ok`; `extras`/row `n_elided_quote`).
  d-pineapple's 'Pineapples. They are tropical, vibrant' (from 'pineapples—they are a nice
  fruit. They are tropical, vibrant') verifies; a quote assembled from two samples never does.
  More than `max(3, n_concepts + 2)` distinct verified picks in
  one call is `over_selected` and credits nothing (audit F10, 2026-10-31: the cap is code
  only, never shown to the judge, which would reveal the concept count; the old prompt cap
  "Select at most three" made a 3-concept item fail whenever a real distractor was also
  named).
- **Regions.** Every cell is labelled from the window's tokens (in-sentence, in-think,
  post-think, self-added meta); only in-sentence cells are judged, and a window without a run
  of three consecutive target words is off-task and excluded. Under the prefill regime every
  cell is in-sentence.
- **Denominator.** Controls, off-task items, items without readouts and items not passed whose
  cells are unjudged or missing are undecided (`rows[].reason`).
- **Extras.** `per_stratum`; `per_kind` (dictation / binding_names / binding_entity) and
  `binding_prior` (prior_direction / counter_prior / no_prior) as `{n, rate}`, with no rate
  published below n = 10 (the items are still listed one by one in `rows`); `cannot_tell_rate`,
  `false_pick_rate`, `control_pick_rate`, `partner_confusion_rate`, `any_concept_rate`,
  `concept_recall`, `per_n_concepts`, `picks_by_basis`; native only: `capacity`,
  `all_in_one_cell_rate` and `mcjudge.layer_pick_columns` (`n_items_gold_any_layer`,
  `n_items_distractor_any_layer`, `n_items_distractor_majority`).
- **Floors.** No analytic chance line for the any-of-grid headline. The measured floors are the
  lucky-guessing baseline (an LLM shown only the candidate lists, `evals/baselines/`; the
  cannot-tell line is not offered to the guesser) and the controls' pick rate. Frozen floors
  (`evals/baselines/lucky_guessing.json`, claude-opus-5-5, 5 draws, 114 scored items, re-measured
  2026-11-01 on the bank v2 lists, restamped to `mcdm-2026-11-01e` since the lists did not
  change): options-only (`blind`) 0.161, `described` 0.300, seeded-uniform 0.270 (analytic
  0.272); both guessers are within chance + 5 (line 0.322), so the MC leakage standard passes.
  There is no `topic` guesser, and none would be a valid floor: as in directed_modulation, the
  topic of an item is its instruction ("Think about ___"), which names the answer
  (`lucky_guessing.NOT_A_FLOOR`). The first bank v2 measurement (2026-10-30, judge prompts
  `mcdm-2026-10-31c`) read blind 0.156, described 0.272, seeded-uniform 0.27; by kind (blind /
  described): ordinary-name relations 0.00 / 0.22, entity relations 0.14 / 0.275 (a guesser
  knows the famous direction), dictation 0.24 / 0.30 (v1: blind 0.10, described 0.235, uniform
  0.245). A relation item's gold and its reverse are the only two candidates that share both the
  people and the relation, so a guesser told how the lists are built can narrow a relation item
  to a direction coin flip, and no further: the same-people distractor takes a random direction,
  so the list's structure does not say which of the two is the gold (when it always took the
  gold's direction, `mcdm-2026-10-31b`, it marked the gold on 48/48 relation items and the
  described floor was 0.335, 0.44 on entity relations). The described floor is the bar to beat
  on binding items. The prompt-only
  baseline (`po-opus-v1`, one Opus 5.5 readout per item, judged by this family's own run) is a
  **saturated ceiling**, not a floor: the prompt dictates the concepts, so it is ≈ 1.0 by
  construction and is never subtracted.

## Readouts

Rows are write cells: `{"id": "<item name>", "layer": L, "pos": p, "token": "<token at the
cell>", "samples": [...]}`, `pos` the render index of the read token (the shipped files use
absolute indices; the toy file uses -12 .. -1 offsets) and `token` required (the region rule
reads the window's tokens). Token-lens rows (`tokens`) are judged on their raw ranked tokens,
behind the shared token note (no interpretation step, plan 0032 §2.3). The producer's sidecar
declares `sampling` (`prose1` for s3d-rl600 and NLA: one generation per activation; `bullet4`
for single-bullet `*-x4` arms: four samples; `tokens10` for token lenses).

```
wsbench plan family=multi_concept_directed_modulation out=plan/                  # full read
wsbench plan family=multi_concept_directed_modulation reads=lite out=plan-lite/  # ' to' only
wsbench judge family=multi_concept_directed_modulation readouts=examples/readouts/multi_concept_directed_modulation.jsonl out=outputs/toy/mcdm dry_run=True
wsbench judge family=multi_concept_directed_modulation readouts=<arm>.jsonl out=outputs/<arm>/mcdm opts=aggregate=native
```

`examples/readouts/multi_concept_directed_modulation.jsonl` is a toy file: three items of the
s3d RL600 read (12 cells x 4 layers each) with the samples truncated.

## Judge prompts

`prompt_version`: `mcdm-2026-11-01e+bank-v2+notokinterp-2026-10-30+pins-r3` (the instrument; `+pins-r3` is deterministic and stamp-only: the pins and the elided-quote rescue; judge calls keyed by
`JUDGE_PROMPT_VERSION` = `mcdm-2026-11-01e`, which replaced the prompt's worked examples (round 5, below; rules unchanged); `-31d` before, which dropped the prompt's "Select at most three" (F10); `-31c` before that; before plan 0034:
`mcdm-2026-10-29+present-2026-10-29`). Summary-mode results are stamped
`digest.prompt_version(PROMPT_VERSION, args, family)`. Judge: the repo default
(`claude-opus-5-5`). Output schema: `{"picks": [{"choice": "A".."G", "quote": str, "basis":
"content_bound" | "instruction_narration" | "incidental"}, ...]}`, an empty list meaning none.

`SYSTEM`:

```text
You judge READOUTS of a language model's internal activations, recorded while it was writing a sentence you cannot see. Before writing, the model may have been told to hold one or more unrelated concepts in mind. You are given the readout and a list of candidate concepts. Select EVERY candidate the readout names or points to: the same thing in any language or wording, a synonym, or a close relative or near equivalent of it (tuxedo for dinner jacket, seesaw for teeter-totter, ice floe for pack ice, damp soil for wet earth). A word that fits several candidates equally does not single one out. Search the WHOLE readout, including the rare lines: a single mention anywhere is enough. When a candidate is named several times, quote its clearest mention.

A candidate that names two people and a relation counts only when ONE quote, taken from ONE line of ONE readout (one bullet if the readout is a bulleted list; in a free-text readout bullets are separated by ⁞, and the quote must not cross a ⁞), names both people and states who does what to whom in that direction. A synonym of the relation counts ("furious with" for "angry at"); passive voice counts ("Zoe was angered by Max" is "Max being angry at Zoe"). People's names must match: one person alone, the relation alone, or a different person does not count. Never assemble the people and the relation from different readouts, lines, positions or layers. A ranked list of tokens does not state a direction: if the only evidence for such a candidate is a token list, answer G.

Select nothing when the readout names none of them. A line that names several candidates, even as alternatives ("a heron or maybe a fountain pen"), names each of them. If the readout seems to point at one of the candidates but you cannot tell which, answer with G alone (quote ""). An empty list means the readout names none of them. Do not use your own knowledge to guess what the model was probably told. For each selection give a SHORT VERBATIM quote (a few words copied exactly from the readout) that names it.

Instructions to the model look like this (blanks stand for the concepts and the sentence): Think about ___. Now write this sentence: "___". For each selection also set basis (it is recorded for analysis; a mention in any context counts):
- "content_bound": the readout engages the candidate as content beyond any narration of the task: imagery, facts, a scene, a story, the thing used in its own right;
- "instruction_narration": the readout only narrates or echoes an instruction about it ("I am thinking about a wristwatch", "the user asked me to focus on the wristwatch", or a copy of the instruction text itself);
- "incidental": in prose, the candidate appears only as one item of a generic list or template of many unrelated things, with no engagement.
When the readout is a ranked list of vocabulary tokens rather than prose, a whole-word token naming the candidate is "content_bound" unless it sits inside an echo of the instruction text; a token list is not an enumeration in the incidental sense. One distinctive word of a multi-word candidate names it when it can only mean that candidate among the options ("submarine" names "yellow submarine").
```

`QUESTION`:

```text
Which of these candidates does the readout name? Select every one that applies, or none.
```

`USER`:

```text
READOUT:
"""
{readout}
"""

{question}

{options}

Answer with the letters of your selections, a quote and a basis for each; G (cannot tell) alone, with an empty quote, when you cannot tell which candidate the readout points to; an empty list means none.
```

`USER_TOKENS`:

```text
{token_note}

READOUT:
"""
{readout}
"""

{question}

{options}

Answer with the letters of your selections, a quote and a basis for each; G (cannot tell) alone, with an empty quote, when you cannot tell which candidate the readout points to; an empty list means none.
```

`USER_TOKENS` is used for native token-lens cells; `{token_note}` is the shared token-list rule
rendered from this family's spec, `mc.token_note((), multi_select=True)` (one list = one
activation; tokens of one list combine; adjacent positions only to spell one word; nothing
relational across lines or bullets; a line naming several of the candidates names each of
them):

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that names several of the options names each of them; pick each option it names (up to the pick limit).
```

## Summary mode (the default; `opts=aggregate=native` opts out)

After the region labels, every in-sentence cell of an item at every loaded layer goes to ONE
digest call (`docs/summarizer.md` § Item digest), told the task context `TASK_NOTE` below (no
concept, person or option) and keeping up to 25 rare entries (`FAMILY_DEFAULTS`
`summ_rare=25`; Camila: "make sure that the summary judge is getting the rarer mentions of the
target concept"). Round 3 (`+pins-r3`): after the digest, `judge.pin_concepts` appends, per
CONCEPT candidate of the item (gold and distractors alike, the same rule for every candidate,
never told which is gold), up to 2 raw prose samples the digest does not already hold that name
one of the candidate's content words (>= 4 letters, plural included: `parking garage` ->
parking / garage(s)), most repeated first (`digest.pin_lines`). d-camel's only parking mention
('in a corporate parking lot', one L20 sample) had been dropped by the summarizer; it now reaches
the judge, which still decides whether it names the candidate. d-pineapple passes (re-asked on
its pinned digest it quotes 'Now, pineapples—they are a nice fruit. They are tropical, vibrant'
verbatim). **Round-3 review (the close-relative rule).** The judge is Opus 5.5 with no
temperature (the Anthropic route drops it), so a re-ask can differ. Re-asked twice from scratch
on the pinned all-layer digests at the unchanged prompt `mcdm-2026-10-31d`, d-camel passes both
times ('a towering structure in a corporate parking lot' credited as `parking garage`, as the
existing close-relative rule says: the round-3 decline was one sample). d-pineapple passes both
times. d-baker fails both times: its digest's sand lines are nonsense pairings ("the desert
tortoise", "the desert salmon", "an elephant's woolly coat in a desert", "the rope, the sand, and
the desert"), and the judge does not credit `sand dune`. Adding the two shapes to the prompt's
close-relative examples ("a parking lot for a parking garage, desert sand for a sand dune",
tried as `mcdm-2026-10-31e`, two from-scratch runs) makes d-baker pass, but it raises the
all-layer false-pick rate (0.353 / 0.371 at d against 0.397 / 0.388 at e) and credits siblings
("a banana tree" for `mango tree`, d-plumber). That loosens every item, so it is not adopted:
d-baker stays an open too-strict cell. The run of record here is d + pins-r3: all-layer 0.439
(unchanged vs the round-2 run: d-pineapple and d-camel now pass; d-chain-egg and d-scarecrow,
re-asked on their pinned digests, now fail, and d-chain-egg passes in the second re-ask), L20 0.281 -> 0.289 (d-camel), L56 0.298 ->
0.307 (d-pirate-ship), every other config unchanged, `control_pick_rate` 0 everywhere.
Relation candidates are not pinned. The shared digest rule records a restatement that names an object or person
with that term as its key. The judge then makes ONE multi-select call per item on the digest
(controls included, so `control_pick_rate` stays paired). The user message is `USER_SUMMARY`,
whose `{summary_note}` is the shared digest note (plus the token note above for token arms).

`USER_SUMMARY`:

```text
{summary_note}

READOUT:
"""
{readout}
"""

{question}

{options}

Answer with the letters of your selections, a quote and a basis for each; G (cannot tell) alone, with an empty quote, when you cannot tell which candidate the readout points to; an empty list means none.
```

`TASK_NOTE`:

```text
the model was told to think about one or more objects or people, or about one person doing something to another, and then to copy down an unrelated dictated sentence; the readouts come from the positions where it writes that sentence. What it was told to think about may not be the most prominent content and may appear only once, or only inside a restatement of the instruction (for example "I must think about X while writing"); such a restatement is content: record every object or person it names. For people, keep who does what to whom as stated within one line of a readout (one bullet of it; in a free-text readout bullets are separated by ⁞)
```

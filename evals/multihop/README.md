# multihop

A factual prompt whose answer needs one silent hop; the scored latent is the bridge
concept, not the surface answer. 100 items, plain render (bank v2,
`evals/multihop/items_v2.json`; `items.json` is the frozen v1 and stays untouched).

Example: "Fact: The chemical symbol for the element with atomic number 26 is" -> bridge `iron`
(the surface answer `Fe` is never an option and never shown to the judge).

## Bank v3 (round 4, the registered bank; Camila r2's MC leakage standard)

`items_v3.json` = bank v2 with re-chosen distractors (`scripts/mc_leakage_r4.py`; header
`mc_leakage`, per item `mc.distractors_v2`, `mc.topic_confusers`); prompts, bridges, aliases and
`bridge_type` are v2's (plan_sha unchanged), judge stamp `bank-mc-2026-11-01-v3`. Bank v2's options
leaked to an options-only guesser (blind 0.280 > chance + 5 = 0.25: other items' bridges of the
same type looked less answer-like than the gold). v3 keeps every v2 rule (never a gold form, the
surface answer, a prompt word or number; never a candidate with the same surface answer, e.g.
another eurozone country for "the euro", now an Opus check, 3 draws) and adds: no word of the
item's first-hop cue (`split_subjects.json`; "South America" for the South-Pole item would tie the
cue to itself), >= 2 same-topic confusers, Chinese forms for every non-number distractor (numbers
compare by value, `distractor_aliases` stays `{}`), no Latin form under 3 letters ("US").

**Keep v2's list unless it leaks** (round 3 of the leakage pass, header `mc_leakage.keep_v2`,
per item `mc.list_source`; review of #214). The split and multi-option rules see only the SHOWN
options, so a list change moves the gate: the first v3 swapped birthstone-emerald-month's
April / July / June / March for December / January / October / September, and the L20 cell the
#205 fix fails (May 10 / April 7) passed again. So an item keeps bank v2's list (`v2`, 49 items;
`v2+repaired`, 1: bf-southpole-bird, whose v2 "Oceania" failed the same-surface-answer check,
penguins live there too, and was replaced by "Greenland") unless a binding
guesser picked its gold on >= 3 of 5 draws in a fresh v2 measurement; a re-chosen list (`v3`,
48) keeps every v2 distractor a cached judge call picked (an observed confuser: nhop-rainbow 14,
firstletter-halloween August; `v3+observed`, 2). Every v2 distractor any cached judge call
picked, over all 14 configs and prompt-only, is on the v3 list. Gate tests read the registered
bank (`tests/test_multihop.py`, `BANK = BANK_V3`), so a list that loosens a regression fails it.
Replaying the 14 cached configs' gold picks on v2 vs v3 options: 8 cells flip, all pass -> fail,
all on re-chosen (leaky-in-v2) items, each because the readouts tie the cue to a NEW option in
the bridge slot: holiday-halloween-monthnum L20/L24/L28/lite ("Halloween is in month number 11
... the month of November", 5 samples at L28), bf-tajmahal-continent L52 ("the country where the
Taj Mahal is located is Brazil", 4; "... France", 4), half-clock-hours L48/L56/L60 ("on a digital
clock ... is 8 hours", 4). These are the split rule doing its job on options v2 did not show,
not a loosening.

**Bridge relabel (PR #214 review r3).** Four bridges were typed `antonym word`, the second hop's
relation, though the unstated bridge is the first hop's answer. The topic guesser and the >= 2
same-topic confusers check read `mc.bridge_type`, so the rule held only on paper ("night" among
hot / big / good / love). They now carry the true kind (old type in `mc.bridge_type_v2`, old list
in `mc.distractors_pre_relabel`, `list_source` `v3+relabel`), with lists of that kind that do not
also answer the first hop (`scripts/mc_leakage_r4.py relabel`: hand-written pools, then the
lint, the topic-member check and the validity screen every list gets):

| item | gold | true kind | v3 list |
|---|---|---|---|
| dual-stars-visible-opposite | night | time of the 24-hour cycle | noon, morning, afternoon, sunrise |
| dual-photosynthesis-opposite | day | time of the 24-hour cycle | midnight, evening, dusk, twilight |
| dbl-altitude-antonym | high | altitude level | sea level, ground level, treetop level, rooftop level |
| dbl-armistice-antonym | war | state of conflict | rebellion, feud, rivalry, vendetta |

The daily-cycle kind is not "time of day", which would hand the photosynthesis item its gold
("day") in the topic line. Two of these lists were v2's (altitude, photosynthesis); no cached
judge call ever picked one of their distractors, so no observed confuser is dropped. Told the
true kind, the topic guesser picks the kind's most typical member: stars 0 -> 5 of 5, armistice
3 -> 5, photosynthesis 1 -> 2, altitude 0 -> 0.

Fresh floors of the frozen bank (Opus 5.5, 5 draws): blind 0.112, described 0.212, topic 0.218
(before the relabel: 0.110 / 0.192 / 0.214; chance 0.20, bar 0.25): passes.

## Read positions (plan 0048)

- **Full (the default):** every token of the plain render, reported as negative offsets
  `-n..-1` (`{"kind": "all_from_end"}`), at every judged layer. The summarizer gets all of an
  item's readouts (every position x every layer) in one digest call.
- **Lite (`reads=lite`):** the last word of the prompt only (`{"kind": "offset_from_end", "k":
  K}` with `K = -readout.offsets[0]`, 1 or 2), at every layer. This is the 2026-09-23 site
  (Camila: "multihop should be read on the second to last token, ie the last word, not the space
  token"): for 33 prompts the final token is a bare space after the last word, so the read is
  `-2`; for the other 67 it is the final token. Lite is a subset of full, so one read serves
  both; a lite run stamps `+reads-lite` on its `prompt_version`.
- A full run needs one contiguous run of at least 8 positions per (item, layer)
  (`min_full_positions = 8`; the shortest prompt has more). A last-word file with a sidecar exits
  2 under `reads=full` ("looks like a lite file"); a sidecar-less file is judged report-only and
  lists its short items under `extras.partial_ids_unenforced`.

## Scoring

- **Headline: pass rate of a blind multiple-choice judge** (`wsbench.basic.mcjudge_bank`,
  stamp `bank-mc-2026-11-01-v3`: bank v3's options, the prompts are `bank-mc-2026-10-31`'s). Summary mode (the default): one digest per item, one judge call
  per item. Native (`opts=aggregate=native`): one call per (item, layer), an item passing on any
  layer; native results carry `n_items_gold_any_layer`, `n_items_distractor_any_layer` and
  `n_items_distractor_majority` beside the number.
- **Options (frozen in the bank, `mc` block per item):** the bridge (`gold`) plus 4 distractors
  of the same type (`bridge_type`: country, number, month, element, city, person, ...), shuffled
  with `mc.seeded_shuffle(f"multihop|{id}")`, then `cannot tell from the readout` LAST (6
  options, A-F). Distractors are drawn by `scripts/build_multihop_mc.py` (deterministic, no API)
  from the other items' bridges of that type, topped up from hand lists in the script. Never a
  distractor: the gold or an alias; the surface answer or its value; anything whose string or
  number is in the prompt; a synonym, translation, demonym, neighbour or same-answer candidate
  of the gold (another eurozone country for "the currency of ...", another Spanish-speaking
  country for "the language of ...", a state that also borders Canada). Option lists are pinned
  by `tests/golden/multihop_mc_options.json`.
- **The judge is blind:** it sees a TASK TYPE line (the task kind, below), the readout, the
  question and the options. It never sees the prompt, the bridge as a target, or the surface
  answer.
- **A pass needs all of:** the gold letter; a verbatim quote that `digest.quote_ok` verifies
  against ONE readout sample (same-list tokens joined by `" | "`; a word split across adjacent
  positions of one layer quoted as the plain word); the gold or a listed alias in that quote
  (`mc.form_in`: word-bounded, CJK forms listed; a number bridge: its value among
  `numerals.numbers_in(quote)`, so digits, words, ordinals and 十六 = 16 all read right;
  `aliases` never hold a demonym or language
  adjective, decision Q9: "Japanese" does not name Japan), read in its line's context: a prose
  quote is widened to the word it sits in, so "Japan" cut out of "Japanese", "6" out of "16" or
  "six" out of "sixteen" fails, and a CJK form followed by 人 / 语 / 語 / 话 / 話 / 文 (日本人,
  意大利语) is a demonym or language name, not the place; for a `number` bridge, a supporting
  sample that is not a number flood (`digest.number_flood`: a token list with >= 5 distinct
  numerals, or a prose list run of >= 5); and a supporting sample that is not a ranked token list
  also holding another shown option (the shared token-note rule, held in code by
  `mcjudge_bank._holds_other`: a `number` bridge compares by value, so `six | eight | nine |
  five` for gold 6 with option 8 fails like `6 | 8 | 9 | 5`; other types match the option and
  its bank-listed `distractor_aliases`, Chinese forms included, so `日本 | 法国` for gold Japan
  with option France fails; a one-character Chinese form, e.g. 马 for horse, only as the whole
  token); for a `number` bridge, a quote that names the gold only in an element-index clause
  ("Sodium's atomic number is **11**", "element number 6", "the atomic number seven is
  nitrogen": the bridge of the nhop-*-element items IS the answer's atomic number, so this reads
  the answer back) fails unless some evidence sample names the gold as a count (a clause with
  the value as a cardinal, no other numeral, no atomic / element / periodic / period / group /
  position word, and a content word: "That's 11 players on a soccer team"; an ordinal "the
  seventh color" or a glued "carbon-6" does not rescue) (`element_index`, round 3). Round 4
  (`bank-gate-r4`) closes the short-quote route around it: a naming of the value that is only an
  ordinal ("8th", "sixth": a periodic position, never the count a bridge is) is an element-index
  naming, and so is a quote clause whose enclosing clause in its support line has an
  element-index word ("Sodium is 11" cut from "Sodium is 11 on the periodic table"); the count
  rescue is unchanged; and the
  pick is not a split (`split`, round 3; Camila: "a ton of different equally prominent answers
  should not pass"): the ITEM's first-hop cue (`split_subjects.json`, hand-authored from the
  prompts: emerald + birthstone, red + planet, Kremlin ...; never a word of an option) is tied
  in some sentence to another shown option, without the gold in that sentence, with at least
  half the gold's support (digest sample counts; birthstone-emerald-month at L20: May 10, April
  7 fails; "May, not April for diamond" counts for May only). The judge's quote is not an input,
  so 'Emerald is the birthstone of May', 'the birthstone of May' and 'May' get the same verdict
  (review of #205: the round-3 draft took the subject from the quote and switched off below two
  words). A sample that ties the gold to the cue counts for the gold only (an operand: "eight.
  When you multiply 4 by the number of legs on a spider"), and a rival sentence that places the
  option in another slot (second / third / next / other / another / before / after / prior /
  preceding / previous / following: "the second tallest mountain, Mount Kilimanjaro", "the
  month before Valentine's Day is December") does not count. Both rules only re-score cached
  calls (`config.gate = bank-gate-r4`; the prompt version is unchanged). Replay over all 14
  cached multihop configs: exactly birthstone-emerald-month@L20 and the three nhop-*-element
  lite cells flip; with every verbatim sub-span of every cached gold quote (1,338 gold picks),
  no split verdict changes. Round 4 re-check (Camila r2: "We still need to check the numbers
  thing being too lenient"), current gate over all 14 cached configs (11 single layers, all,
  lite, prompt-only): the number-flood / element-index fix holds everywhere. The three lite
  cells credited on lists of atomic numbers (nhop-soccer/cube/rainbow-element) fail. Of the 86
  remaining number-bridge passes, the 25 whose quote has an element word or whose support line
  holds 3+ distinct numerals were read by hand: each rests on a sample that ties the gold to its
  counted cue ("A soccer team has **11** players", "There are 6 faces on a cube", "That's 7
  colors in a rainbow"), none on a list of numbers; the one ordinal quote among them (L28 nhop-spider-element, "8th" from "the 8th word
  ..., when located on the periodic table, is also Oxygen") passes only through the count rescue
  (the same evidence says "A spider's legs count is famously eight"); the r4 tightening flips no
  cached cell. Round 5 (`bank-gate-r5`, review of #214) scopes both round-4 widenings (the
  ordinal-only naming and the support-line clause) to the nhop-*-element items, the only items
  whose bridge IS the answer's atomic number: elsewhere ELEMENT_WORDS such as period, rows, group
  name the counted thing, and r4 failed clean counted quotes ("12 numbers" from "... over a
  12-hour period", "5 rings" from "... arranged in two rows", "has 6 faces" from "Each die in
  the group has 6 faces"). On every number item the quote's own clause rule of round 3 stands.
  And on the element items a quote that is itself a counted clause, cut from a line clause that
  names the value again outside it, is the counted half of a count-to-element chain and passes
  ("A cube has 6 faces" from "A cube has 6 faces so the element with atomic number 6 is
  carbon"); a bare "7" never is. Round 6 (`bank-gate-r6`, review of #214): the split rule's
  sentence break also falls after a markdown close that follows the sentence end, so "... built
  the Great Wall.** The country that built the Great Pyramid of Giza is **the United States**"
  is two sentences (b3-mh-greatwall-river@L36: r5 read one and split China 8 / US 4); the same
  rival in the wall's own sentence is still a split.
  Cannot tell, a distractor or an invalid letter fails; a failed call is undecided.
- **A bare mention counts** (decision of plan 0048, overridable): the question is which entity
  the readout names, not which answer it states, so a bullet "- Nepal" or a token list whose only
  option is Nepal is a pick, unless the shared token note voids it.
- **Flat types:** `flat_types = ("numbers", "months", "countries")`: a line holding a run of
  these singles out none of them, whatever their rank (decision Q4; there is no rank-1
  exception). Camila's example, the token list `equal twelve six eight seven eleven nine sixteen
  twenty five` for gold 6, fails three ways: it is a run of numbers, it holds other options (8,
  9, 5), and it is a number flood.
- `spaceneedle-border` is keyed to **Washington** (the prompt asks for the state; Seattle is not
  an alias), decision Q9.
- An item whose every expected layer is judged fails; one with no pass and an unjudged or missing
  cell is undecided (`extras.n_items_undecided`). A cell whose samples are all blank is a fail
  without a call.
- **Chance:** 1 in 5 per call (cannot tell excluded); the native any-layer floor is higher. The
  lucky-guessing builder uses these option lists. The measured floor is the prompt-only baseline
  (`po-opus-v1`: one Opus 5.5 readout per item, judged by this same judge, digest and gates).
- **Not in the anti-text-inversion subset** (Camila 2026-10-30: "do not include the single
  question in ati"): `NOT_GATED["multihop"]`; `anti_text_inversion=True` skips the family.
- Sampling follows the producer's declared kind: one sample per activation for prose readers
  (incl. the multi-bullet O-lens), 4 for a single-bullet O-lens (`*-x4`), the top-10 tokens for a
  token lens.

## Readouts

`{"id": "<item label>", "layer": L, "pos": P, "samples": [...]}` rows, one per (item, layer,
position), where the label is the item `name` with characters outside `[A-Za-z0-9._-]`
replaced by `_` (`wsbench.banks.label_of`); `tokens` rows for a token lens.
`examples/readouts/multihop.jsonl` is a toy file for `dry_run=True`.

```
wsbench judge family=multihop readouts=examples/readouts/multihop.jsonl out=outputs/toy/multihop dry_run=True
wsbench judge family=multihop readouts=<arm>.jsonl out=outputs/<arm>/multihop limit=3
wsbench judge family=multihop readouts=<arm>.jsonl out=outputs/<arm>/multihop-lite opts=reads=lite
```

## Judge prompts

`prompt_version`: `bank-mc-2026-11-01-v3` (round 4: bank v3's options; prompts unchanged from
`bank-mc-2026-10-31`; summary mode: `digest.prompt_version` of it, by default
`bank-mc-2026-11-01-v3+digest-v5-task-extractive+sj-v10`; `+reads-lite` for a lite run). Judge: the
repo default (`claude-opus-5-5`), temperature 0. Output schema: `{"choice": str, "quote": str}`
(a letter; an invalid letter is re-asked once, then unjudged). The prompts below are sent
verbatim (`wsbench.basic.mcjudge_bank` plus this family's strings).

System prompt (`SYSTEM_MC`, `{rules}` = this family's `RULES`):

```text
You are judging readouts of a language model's internal activations for an
interpretability benchmark. You get one eval item: a TASK TYPE line (the kind of task the model
was doing while the readouts were taken, never the item itself), the readout, one question and
lettered options. You are not told the item's text or its answer.

Pick the ONE option the readout names, by these rules:
- Judge only what is written in the readout. Do not use your own knowledge of the task to work
  out which option is right.
{rules}
- The last option is the cannot-tell option: choose it whenever the rules single out no option.
- Every other pick must include a VERBATIM quote copied exactly from ONE readout sample (from a
  ranked token list: one token, or several tokens of that same line joined by " | "): the
  shortest span that names the option. No quote, no pick.
Return JSON: {"choice": "<letter>", "quote": "<verbatim span, empty for cannot tell>"}.
```

`RULES`:

```text
- An option counts only if ONE readout sample names it: the word itself, an established
  alias, a spelling variant, or a translation into any language. The one exception is the
  token-list rule below: tokens of adjacent positions at one layer may spell one word split
  across them. Words of different samples never combine otherwise.
- Naming something the option could be worked out from does NOT count: a symbol, a number
  that encodes it, a definition, a calculation, a related place, or a derived word such as
  a nationality or language adjective ("Japanese" does not name Japan). Do not use your
  own knowledge to connect clues to an option.
- Choose "cannot tell from the readout" if the readout names none of the options, or names
  two or more of them with similar prominence.
```

User message (`USER_MC`; `{task_type}` = `TASK_NOTE`; `{kind_note}` = `NATIVE_NOTE` natively,
or the digest note (`SUMMARY_NOTE`, below) in summary mode, followed in both by the token note;
`{readout}` = one `BLOCK_MC` per read position natively (each sample one indented line, a token
list one `" | "`-joined line, bullets of one free-text sample joined by ` ⁞ `), or the digest;
`{options}` = `A. ...` to `F. cannot tell from the readout`):

```text
TASK TYPE: {task_type}
{kind_note}

READOUT:
{readout}

QUESTION: {question}
{options}
```

```text
[position {pos}]
{lines}
```

`NATIVE_NOTE`:

```text
The readout below holds the samples read at one layer: one block per token position, one sample per line.
```

`TASK_NOTE` (also the summarizer's task context, `EvalSpec.task_note`):

```text
the model reads a factual statement whose completion depends on one intermediate entity (a place, person, number, date or thing) that the text never names; the readouts may mention that entity only once
```

`QUESTION`:

```text
Which ONE of these does the readout name as the unstated entity?
```

The cannot-tell option (`CANNOT`, always last):

```text
cannot tell from the readout
```

The token note (`mc.token_note(flat_types)`, shared; rendered from this family's spec):

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of numbers, months or countries singles out none of the numbers, months or countries on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by that line, even if the line holds other words of the same kind; that exception never applies to a run of numbers, months or countries.
```

The digest note in summary mode (`SUMMARY_NOTE`, shared; `docs/summarizer.md`):

```text
The readout below is a digest of the readouts across every read layer and position: for each read layer, a note-taker who did not see the passage picked the most prominent readout samples, then samples carrying content seen in only one or a few samples, and the layers' picks are merged, the most-stated first. Each line is marked with how many readout samples state its content ([N samples], or [N samples, M layers] when it was seen at M read layers): counted per claim, so a sample that only lists the word among others of its kind, or only restates the question, is not counted; compare these counts when weighing lines against each other. Each line is one real readout sample (a free-text generation, or one ranked list of top tokens). Treat each line as a separate sample: pieces on different lines never combine. Any quote must be copied from inside one line, without the bracketed marker.
```

## History

- Until plan 0048 (2026-10-30) the family was read at the last word only and judged by the
  shared free-text bank judge (targets shown, forbidden-answer line, stamp `bank-2026-10-30b`),
  and `spaceneedle-border` was keyed to Seattle. It had one anti-text-inversion item
  (`spaceneedle-border`, an artefact of that keying).

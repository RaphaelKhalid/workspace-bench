# association

A short scene evokes ONE concept it never names (a Portuguese carnival, a chess game, a
childhood); the model is then asked to summarize the story, and the lens is read at every
position of that request. Does the lens name the concept? Bank v2 (`items_v2.json`, plan 0039):
93 items, each an 8-way multiple choice (the gold + 7 same-type distractors) plus
"cannot tell from the readout". `items.json` (v1, 100 items, plain final-token render, free-text bank judge) is
kept byte-identical for history; nothing reads it.

Example: "Os tambores começaram na avenida ao anoitecer, e as fantasias cobertas de plumas
dançaram até o amanhecer." -> gold `carnaval`; options (seeded order) include `Natal`,
`Páscoa`, `Halloween`, `Oktoberfest`.

## Bank v4 (round 5 "common", Camila r3 (1); opt-in, NOT registered)

`items_v4.json` (`scripts/common_confusers_r5.py`, header `common_confusers`) = bank v3 with 4
frequency-matched, equally common confusers added to every list (board game chess -> Trivial
Pursuit, Clue, Snakes and Ladders, Battleship beside v3's seven). Every v3 option stays in place
(`mc.distractors_v3`), so each earlier judge-picked confuser is kept. Candidates: Opus 5.5
proposes concepts of the fine category as common as the gold; wordfreq Zipf (scene language
for pt- / de- / es- / it- items) within 1.0 of the gold's; mc_leakage_r4 lint, kinship and
topic-member checks; scene screen (Opus with the scene picks the gold 5/5 against the whole
grown list; a new option that wins once is banned). Closed topics ran dry: winter and divorce get
0, b3-as-sauna 1, bf-snow / fired / b3-as-joust 2 (`short_lists`). **Qwen gate**: the bank's
referent question over the exact scene, 10 samples on Modal (T 0.7), kept iff >= 8/10 name the
gold (listed form, or Opus 5.5 rules unanimously over 3 draws that the answer names the gold
itself). 75 of 93 pass; 18 dropped (child-h, noir, pennsylvania, unesco, bf-christmas,
bf-library, bf-paris, b3-as-lifeguard, b3-as-magician, b3-as-troy, b3-as-vineyard, b5-as-goldrush,
free-h, space-h, bf-dentist, time-h, bf2-barber, b3-as-moses). Scenes are unchanged, so
`read_plan_bank: items_v3.json` keeps v3's read plan and plan_sha: **no new readouts**.

**Floors** (Opus 5.5, 5 draws):

| lists | n | chance | blind | described | topic |
|---|---|---|---|---|---|
| v3, all 93 | 93 | 0.125 | 0.157 | 0.368 | 0.628 |
| v3, the 75 kept | 75 | 0.125 | 0.176 | 0.381 | 0.664 |
| **v4** | 75 | 0.086 | **0.443** | **0.533** | **0.683** |

v4 **FAILS** the standard on all three guessers and is WORSE than v3, including options-only
(0.176 -> 0.443 on the same items; 25 items gain >= 3 of 5 draws). Likely cause: the proposer
builds each addition from the gold, so the grown list is a cloud around it (lie: bribe, cheating,
blackmail, bullying beside secret, trick, con, betrayal) and an options-only guesser picks its
centre (lie, chess, Pentagon, rain 5/5). The topic guesser still picks the stereotype of its
category (0.664 -> 0.683). **Replay** of the cached judge cells of the grown items (121 non-pass
cells over 15 configs, re-judged under v4 from cached digests): 22 fail -> pass, 6 flagged
attributable, all six on bank-v2 options bank v3 had already removed (dawn's dusk / night,
winter's dawn, fire's smoke), none on a list change of v4 (lists only grow from v3). v3 stays
the registered bank.

## Bank v3 (round 4, the registered bank; Camila r2's MC leakage standard)

`items_v3.json` = bank v2 with re-chosen distractors and their forms (`scripts/mc_leakage_r4.py`;
header `mc_leakage`, per item `mc.distractors_v2`, `mc.topic`, `mc.topic_confusers`,
`mc.distractor_aliases`); scenes, golds, gold aliases and categories are v2's (plan_sha unchanged),
judge stamp `assoc-mc-2026-11-01-v3` (prompts and gate unchanged). Bank v2's 7 distractors were
often off-type neighbours, so the gold stood out (blind 0.518, described 0.529). v3: 7 same-topic
distractors (Opus-proposed from the gold alone, never the scene; topic-member check),
scene-screened (Opus with the scene picks the gold 5/5), no option a word of the scene (v2's
`smoke` in bf-fire and `almuerzo` in es-siesta are gone), no shared forms. Each distractor lists
its forms (`mc.distractor_aliases`: Chinese, and English for the four scene-language items), and
`judge.bank_concepts` reads them, so gate 3b/3c and the rare-hit pins test a distractor named in
Chinese like its bare string (`tests/test_association_v3.py`).

**Topic = the fine category** (review 2 of #214). The topic guesser, the proposer and the
>= 2 same-topic confusers check all use the item's own category (`mc.category`: "board game",
"historical ruler / ancient queen", "mode of public transport"), the topic a judge infers from
the readouts; `mc.topic` records it (`lucky_guessing.fine_topic`). A parenthetical of a category
glosses the gold ("setting / environment (outer space)" for space, "venue / establishment
(gambling house)" for casino) and is dropped. The first v3 used a broader proposer-written line
("a game", "a famous historical figure"): its 0.320 topic floor understated the leakage, since a
guesser told the category picked the gold 0.634 of the time on the same lists, and its lists
often swapped fine confusers for off-category ones (Cleopatra lost Nefertiti / Hatshepsut,
subway lost tram / monorail). Rebuilt with the fine topic (8 search rounds, then a targeted
round): Cleopatra's list is Nefertiti, Hatshepsut, Boudica, Queen of Sheba, Catherine the Great,
Elizabeth I, Anne Boleyn; subway's is tram, monorail, funicular, cable car, bus, matatu, taxi.
Every bank v2 distractor a cached judge call picked stays on the list (`mc_leakage.
observed_confusers`: winter's dusk / night, lie's secret / truth, ...; es-siesta's almuerzo is a
scene word and goes). One item is short of 2 same-topic confusers: divorce ("legal end of
marriage" has one other member in a 175-candidate pool, annulment, which the list holds).

**Fresh floors** of the frozen bank (Opus 5.5, 5 draws), chance 1/8 = 0.125, bar 0.175:

| lists | blind | described | topic (fine category) |
|---|---|---|---|
| bank v2 | 0.518 | 0.529 | 0.692 |
| first v3 (PR #214, broad topic) | 0.112 | 0.170 | 0.634 (0.320 with its broad line) |
| v3 before the kinship repair | 0.127 | **0.301** | **0.578** |
| **v3 (registered, kinship-repaired)** | 0.138 | **0.351** | **0.624** |

**Kinship repair** (review r4 of PR #214): a distractor may not be a kind, instance or variant of
the gold, a broader term or a setting that contains it, a near-synonym, or a part / stage of it.
The first v3 offered espresso for coffee (15 final-olens readouts name it, 12 beside the gold;
gates 3b/3c then refuse the gold), separation for divorce and spa for sauna.
`scripts/mc_leakage_r4.py kin` (Opus 5.5 over each list and its ranked pool, 3 draws, any flag
bans; plus the hand bans in `KIN_SEED`: pesapallo for baseball, moving out for divorce, being
replaced for fired, and for fireworks the fire festival / parade / carnival / lantern festival it
is the centrepiece of; one flag overruled in `KIN_KEEP`: annulment stays on divorce, a distinct
legal remedy, the topic's only rival and named by 0 of 836 readouts) re-chose 20 lists
(`mc_leakage.kinship.items`; old lists in `mc.distractors_pre_kin`), e.g. coffee loses espresso
(-> hot water), divorce loses breakup, custody battle and separation, space loses Mars and the Moon, rain loses storm and
thunderstorm, wedding loses rite of passage. Removing options that were as likely as the gold
raises the floors: blind 0.127 -> 0.138, described 0.301 -> 0.351, topic 0.578 -> 0.624 (gold
5/5 on 53 items, 0/5 on 30). In the final-olens readouts (836 samples per item) a removed
option was named beside the gold up to 34 times (rain's storm; espresso 12, spa 19, separation
9), an added one at most 7 times (dawn's eventide). The removed options were wrong to offer, so
the higher floor is the honest one.

v3 **FAILS** the standard on `topic` and `described`. With the category's gloss kept (review 2's
exact instrument) v3 reads 0.624 (the first v3: 0.684). Per item, the topic guesser picks the gold
5/5 on 47 of 93 items and 0/5 on 34 before the repair (53 / 30 after): told "a board game", it picks chess among checkers,
Monopoly, Risk, Go, Catan, Scrabble and backgammon; told "a fictional detective", Sherlock Holmes
among Poirot, Marple, Columbo, Marlowe, Spade, Dupin and Father Brown. The scenes were written to
evoke famous concepts, so the gold is the stereotype of its own category, and no list of members
of that category outranks it. Many categories also define the gold ("legal end of marriage",
"job loss event", "team bat-and-ball sport"). Search progress with the fine topic, topic floor by
round: 0.708, 0.645, 0.606, 0.609, 0.600, 0.559, 0.585, 0.570, 0.576 (plateau). Fine-topic lists
also raised `described` (0.170 -> 0.301): a guesser shown solved examples learns "pick the most
prototypical member" once every option is a member. The gap is recorded, not hidden; the open
decision (gate or separately score the stereotype items, or neutral topic lines) is in
`evals/baselines/README.md` "MC leakage standard".

## Bank v2

- **Retired (C1, header `retired` / `retired_rule`):** an item is under-determined, and
  retired, if (a) every frontier panel model (opus, astra, argon) failed at least 2 of its 3
  panel-v1 draws, (b) its gold is a broader term of the concept the scene shows, or (c) the
  scene fits another, equally specific concept. Retired: `nasa`, `cia`, `history-h`, `love-h`,
  `death-h` (a), `game-h` (b), `de-konig` (c). `bf-sherlock`'s gold is now `Sherlock Holmes`
  (the generic `detective` target is gone).
- **Options (`mc`):** `gold`, `aliases` (inflections, spelling variants, synonyms and
  translations into English, Chinese and the scene language; never shown to anyone; the only
  deterministic pass), `category`, `distractors` (7). Built by
  `scripts/association_distractors.py`: Opus 5.5 proposes candidates from the gold alone (never
  the scene or a readout, so the options are lens-neutral), a word lint and an Opus entailment
  check drop synonyms / hypernyms / hyponyms, and a scene screen (Opus 5.5 sees the scene and
  the 8 options, 5 draws, fresh order each) keeps a list only if the gold wins every draw; a
  distractor that wins once is replaced. Header `distractor_rule`, `distractor_review` and
  `distractor_review_edits` record the rules and every reviewer edit.
- The behavioural gate (`consistency`, Qwen3.6-27B names the referent) is v1's: the scenes and
  golds are unchanged.

## Read sites

`wsbench plan family=association`: render `chat_summarize` (Qwen chat template,
`enable_thinking=False`; the user turn is the scene + `"\n\nSummarize the preceding story in one
sentence."`), positions rule `suffix_text_then_tail` = the 19 tokens from `Sum` through the final
`\n\n` after `</think>` (story positions are never read; the conjunctive / role-bound sites
exactly, `docs/read_sites.md`), layers `readplan.GRID` (20..60 step 4). `reads=full` needs every
(item, layer) to hold one contiguous run of 19 positions (`min_full_positions = 19`).
`reads=lite` reads **every** full site: the lite rule is `same` (`evals/association/lite_rule.json`;
Camila r2, 2026-11-01: "Make lite subset all positions"), so for association lite selects exactly
the `reads=full` cells (all 19 positions of the summary request x every grid layer) and a lite
run differs from the full run only in its `+reads-lite` stamp; the lite number equals the full
number up to judge sampling. The round-3 single site (`offset_from_end k=7`, the `<|im_start|>`
of the assistant header, chosen by the support-share procedure `scripts/lite_site_table.py`:
26.5% of the gold-bearing all-layer digest lines vs 7.5% at the final token) is superseded; its
measurement table stays in `lite_rule.json` as the record. Lite is a subset of the full
positions (here: all of them), so no re-read.
`layers=all|each|<csv>` work as for every family.

## Scoring

- **Headline (summary mode, the default): pass rate.** Every loaded cell of an item (19
  positions x every requested layer) goes to ONE digest (`expect_all`: none may be dropped;
  task note below), then ONE MC call. Chance: 1/8 (`result.chance`). Rare-hit pins (round 3;
  "summary mode drops rare single-cell hits"): for every shown option, gold and distractors
  alike, that NO digest line names, up to 2 raw prose samples naming it (by the bank concept's
  listed forms plus the plain plural, most repeated first) are appended as ordinary extractive
  lines with their real sample counts (`digest.pin_lines`), so lie@L24's one "he was lying"
  sample reaches the judge as `[1 sample]`.
- **Gate of a pick** (`judge.py`; `digest.quote_ok` is the one verifier):
  1. a distractor, cannot tell or invalid choice fails; a failed call is undecided;
  2. the quote must lie inside one readout line; a miss is re-asked once (`<key>|retry1`,
     `RETRY_LINE`), a second miss is `gold_unverified` (fail);
  2b. token readouts (`sampling=tokens10`): if every line holding the quote also names another
     shown option, the pick is void (`gold_flat_list`, `extras.n_flat_list_voided`);
  3. a quote naming a listed form (gold or alias, `mc.form_in`) passes (`credit=listed_form`);
  3b. (round 3) else the prose sample holding the quote names a listed form in the quote's own
     sentence or the one right before or after it, and that sentence names no other shown
     option and is not a denial (`gold_listed_line`, `credit=listed_line`: the 'prisoners'
     clause of "304 Prison / The Detention Center** ... were **prisoners**");
  3c. (round 3) else another prose sample of the judged evidence has a sentence that names a
     listed form, no other shown option and no denial (`gold_listed_evidence`; bf-library@L24's
     'librarian' quote beside 'She whispered her plea in the empty library'). In 3b/3c a
     capitalised form (a proper name) counts only with its capital and a form glued to a
     following hyphen never counts, so the shape word of "a pentagon-shaped building" is not
     the Pentagon. 3b/3c test the other shown options by ALL their forms, the same expansion
     the gold gets (`other_option_forms`: the bank concept entry, i.e. translations and aliases,
     plus the plural: museums, 博物馆, casinos, jail block a library sentence), and apply only
     when the judge's quote itself names none of them (a quote 'the museum hall was silent' is
     not rescued by a library sentence elsewhere; it goes to step 5). A 3c pass is void when a
     distractor out-names the gold in the raw samples (the step-5 rule below,
     `gold_evidence_outnamed`, `extras.n_gold_evidence_outnamed`);
  4. a quote with no Latin letters and no listed form fails (`gold_unlisted_script`);
  5. any other quote gets ONE quote-only re-judge (`QUOTE_USER`): gold again passes
     (`gold_description`, `credit=description`, `extras.n_description_credit` and the quotes
     verbatim), unless a shown distractor is named verbatim by at least 2 raw samples of the
     judged cells and by more than the gold (`gold_desc_outnamed`, fail; film-h@L24: "novel" in
     4 samples, "film" in none); anything else fails (`gold_desc_rejected`).
- **Native (`opts=aggregate=native`, the ATI gate instrument):** one MC call per (item, layer)
  over every position at that layer, the same gate; an item passes if any layer passes.
  `extras` carries `n_items_gold_any_layer`, `n_items_distractor_any_layer`,
  `n_items_distractor_majority` (`mcjudge.layer_pick_columns`).
- **Floors:** chance 1/8; lucky guessing (the options-only guesser over these lists,
  `baselines/lucky_guessing.py`); prompt-only = Opus 5.5 reading the render (`po-opus-v1`),
  judged by this same instrument (`wsbench run all=True readouts_root=<po>/readouts`).
- **ATI:** re-gated natively with this instrument on 2026-10-31 (R1-ATI; the v1 entry had 12
  ids): 25/93 on the reduced panel Qwen + Opus + Astra (argon unreachable), PROVISIONAL
  (`evals/baselines/README.md`, fix-round-1 re-gate). Re-gated on 2026-11-01 (R1-ATI gemini) on
  the full four-reader panel (argon via Gemini WIF) at bank v3 / `assoc-mc-2026-11-01-v3`:
  **26/93** (+b3-as-surgery, +pentagon, -b5-as-knitting; instrument-driven, argon moves no item).
- Missing (item, layer) cells exit 2 unless `allow_missing=True`; an adapted bank without `mc`
  exits 2 ("re-adapt: no mc options").

## Readouts

`{"id": "<item id>", "layer": L, "pos": P, "samples": [...]}` rows (or `tokens`), plus the
producer's sidecar `<file>.meta.json` (`sampling`, `reads`, `plan_sha`).
`examples/readouts/association.jsonl` is a toy file (3 items x 11 layers x 19 positions, with a
sidecar) for `dry_run=True`.

```
wsbench judge family=association readouts=examples/readouts/association.jsonl out=outputs/toy/association dry_run=True allow_missing=True
wsbench judge family=association readouts=<arm>.jsonl out=outputs/<arm>/association limit=3
```

## Judge prompts

`prompt_version`: `assoc-mc-2026-11-01-v3` (round 4: bank v3's options; the prompts and gate are
`assoc-mc-2026-10-31-r3`'s; summary runs stamp `digest.prompt_version("assoc-mc-2026-11-01-v3",
...)`, by default `assoc-mc-2026-11-01-v3+digest-v5-task-extractive+sj-v10`; lite runs add
`+reads-lite`). Judge: the
repo default (`claude-opus-5-5`). Output schema `readout_mc` / `quote_mc`:
`{"choice": int, "quote": str}`. Option order: `mc.seeded_shuffle(gold + distractors,
"assoc-v2-20261030:<id>")`, then `"cannot tell from the readout"` last.

`SYSTEM_SUMMARY`:

```text
You judge readouts of a language model's internal activations, recorded while the model read a passage you cannot see. You get a digest of those readouts across every read layer and token position (described in the note below) and ONE multiple-choice question: which listed concept do the readouts name? Pick an option only if one readout line states that concept itself: the word in any case, inflection or spelling variant ("neighbour" names "neighbors"), an established synonym or alias, a faithful translation into any language, a narrower instance that necessarily entails it ("a puppy" names "dog"), or a description that depicts the concept itself. Do NOT pick an option you can only infer from clues, scene details or evidence ("crayon drawings on the fridge" do not name "child"); a broader category, the general topic, a merely related idea, a different word that contains the option's letters, and word fragments name nothing; nor does a shape, colour or material of something in the scene name a place or thing called after it ("a pentagonal building" does not name "the Pentagon", "a white house" does not name "the White House"). A single list or line that holds two or more of the listed options singles out none of those options, whatever their order; a line that is a run of interchangeable words of one kind (animals, colours, places, names, ...) singles out none of them, whatever their rank, even when only one of them is a listed option; otherwise an option that is the only listed option on its line is singled out by that line. Pick an option only if at least one line singles it out. If lines single out two or more different options, pick one only if it is stated as what the passage is about, or is singled out by clearly more lines than any other; lines that single out nothing never count toward this. If no line singles out an option, or no option wins, choose "cannot tell from the readout". Do not use world knowledge or plausibility to fill gaps. Give a SHORT quote copied character for character from inside ONE readout line that singles out the option you picked.
```

`SYSTEM_NATIVE` (the same, second sentence replaced):

```text
You judge readouts of a language model's internal activations, recorded while the model read a passage you cannot see. You get the readouts at one layer, grouped by token position and ONE multiple-choice question: which listed concept do the readouts name? Pick an option only if one readout line states that concept itself: the word in any case, inflection or spelling variant ("neighbour" names "neighbors"), an established synonym or alias, a faithful translation into any language, a narrower instance that necessarily entails it ("a puppy" names "dog"), or a description that depicts the concept itself. Do NOT pick an option you can only infer from clues, scene details or evidence ("crayon drawings on the fridge" do not name "child"); a broader category, the general topic, a merely related idea, a different word that contains the option's letters, and word fragments name nothing; nor does a shape, colour or material of something in the scene name a place or thing called after it ("a pentagonal building" does not name "the Pentagon", "a white house" does not name "the White House"). A single list or line that holds two or more of the listed options singles out none of those options, whatever their order; a line that is a run of interchangeable words of one kind (animals, colours, places, names, ...) singles out none of them, whatever their rank, even when only one of them is a listed option; otherwise an option that is the only listed option on its line is singled out by that line. Pick an option only if at least one line singles it out. If lines single out two or more different options, pick one only if it is stated as what the passage is about, or is singled out by clearly more lines than any other; lines that single out nothing never count toward this. If no line singles out an option, or no option wins, choose "cannot tell from the readout". Do not use world knowledge or plausibility to fill gaps. Give a SHORT quote copied character for character from inside ONE readout line that singles out the option you picked.
```

`USER_SUMMARY` (`{note}` = `SUMMARY_NOTE` below, plus the token note when the readouts are
token lists; `{digest}` = the item digest; `{question}` = `QUESTION`):

```text
{note}

READOUTS:
{digest}

{question}
```

`USER_NATIVE` (`{note}` = `NATIVE_NOTE_PROSE` or the token note; `{blocks}` = one
`[L<layer> pos <pos>]` block per position, one `- ` line per sample):

```text
{note}

READOUTS:
{blocks}

{question}
```

`NATIVE_NOTE_PROSE`:

```text
Each readout line below is one free-text sample.
```

`QUESTION` (`{listing}` = the numbered options):

```text
Which concept do the readouts name?
{listing}
```

`RETRY_LINE` (appended to the same user message for the one retry of a quote miss):

```text
Your quote was not found inside one readout line; copy it exactly from one line.
```

`QUOTE_USER` / `QUOTE_USER_TOKENS` (the step-5 quote-only re-judge, same system prompt):

```text
READOUT (one span quoted from the readouts):
{quote}

{question}
```

```text
READOUT (tokens quoted from one ranked list, ' | ' separated):
{quote}

{question}
```

The token note (`mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`, rendered
from the spec: `flat_types=()`, single answer):

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank; an option that is the only option on its line is singled out by that line, even if the line holds other words of the same kind.
```

`DIGEST_TASK_NOTE` (the summarizer's task context, `EvalSpec.task_note`; no gold, no tool
name):

```text
the model read a short scene (sometimes not in English) that evokes one concept (an activity, event, place, person, organisation, feeling or thing) without naming it, and was then asked to summarize the story in one sentence; the concept may appear in only one or a few readouts
```

`SUMMARY_NOTE` / `SUMMARY_NOTE_ABSTRACTIVE` (shared, `wsbench.digest`):

```text
The readout below is a digest of the readouts across every read layer and position: for each read layer, a note-taker who did not see the passage picked the most prominent readout samples, then samples carrying content seen in only one or a few samples, and the layers' picks are merged, the most-stated first. Each line is marked with how many readout samples state its content ([N samples], or [N samples, M layers] when it was seen at M read layers): counted per claim, so a sample that only lists the word among others of its kind, or only restates the question, is not counted; compare these counts when weighing lines against each other. Each line is one real readout sample (a free-text generation, or one ranked list of top tokens). Treat each line as a separate sample: pieces on different lines never combine. Any quote must be copied from inside one line, without the bracketed marker.
```

```text
The readout below is a digest of the readouts across every read layer and position, written layer by layer by a note-taker who did not see the passage, most prominent first, then content seen in only one or a few samples. Each line is one statement in the note-taker's words, how many samples state it (counted per claim), and a verbatim evidence span from one real readout sample. The statements are not evidence: judge what the evidence spans show, treat each line as a separate sample (pieces on different lines never combine), and copy any quote from inside one evidence span.
```

Example option listing (`b3-as-birthday`):

```text
Which concept do the readouts name?
  1. Christmas
  2. wedding
  3. Thanksgiving
  4. New Year
  5. Easter
  6. Halloween
  7. birthday
  8. graduation
  9. cannot tell from the readout
```

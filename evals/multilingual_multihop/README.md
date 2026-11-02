# multilingual_multihop

A non-English factual prompt whose answer needs one silent intermediate entity (the bridge).
The readout must write the bridge in the prompt's language AND in English or the model's native
language (Chinese for Qwen3.6-27B) AND NAME the passage's language; all three are required.
Camila 2026-10-30: "Again require the name of the language AND the intermediate in english or
chinese/model's native language, AND the intermediate in the prompt's language (make these not
optional anymore)"; "Make a judge (mc w distractors) to choose the intermediate value from the
readouts and the prompt language, then regex to make sure all of the necessary values are
there".

98 items, 12 languages. Scored units: `bridge_l2` (the bridge as an L2 speaker writes it, with
inflections), `bridge_native` (`en` + `zh`) and `language` (names only), all required.

The v2 bank (`evals/multilingual_multihop/items_v2.json`, built offline by
`scripts/build_multilingual_v2.py` from `items.json`, which is untouched; plan 0054) keeps every
prompt, target and id. Header `version: 2`, `contract.native_langs: ["en", "zh"]` (the subject's
native languages, measured by the skill's native-language step; read only through
`banks.native_langs`). Every unit is required. The `language` unit holds language NAMES only
(English, Chinese and the autonym with its inflections, `wsbench.multitoken.languages`; "Polish"
is matched case-sensitively so the verb "polish" never counts); it never holds a content word.
The native content unit has one form list per native language. Natural forms a reader writes
("bergamot, K2, Mawsynram, ASML, Sarez, Parkes") were added to the padded v1 aliases.
`bridge_native` is `multi_token: false`, so every listed English or Chinese form credits,
single-token ones included ("Kepler", "Booth", "monarch"); the Qwen3.6-27B multi-token filter
(`probe_token_lens` > 1) applies only to `bridge_l2`.

**The L2 unit needs an L2-only form.** A `bridge_l2` form that folds equal to a native form
(an English-only "ASML") never credits the L2 unit; the remaining forms are the item's
`bridge_l2_creditable` ("ASML:n", "ASML-yhtiö" do). Wrapper-padded L2 forms that only repeat the
English name were dropped ("hollantilainen ASML", "khu dân cư Mawsynram"). An item with no
creditable L2 form is `l2_equals_native: true`: it is scored without its L2 unit and left out of
the headline. In this bank: 1 item (`mlmh-vi-mawsynram-meghalaya`: Vietnamese writes
"Mawsynram"), so the headline n is 97; the flagged items' rate is `extras.pass_l2_equals_native`
and the all-98 rate `extras.pass_all_items`.

## Scoring: `mc+regex` (blind MC judge, then regex)

Instrument `mcrx-2026-11-01a+mc-ml-2026-11-01b` (summary mode adds the digest stamp); pinned;
judge = the registry default (Opus 5.5).

- **MC roles.** `bridge_native` (gold + the bank's 4 curated same-category distractors, e.g.
  kente: Adire / Bogolanfini / Aso Oke / Kitenge) and `language` (gold + 4 confusable
  languages), `cannot tell` last; blind (digest or readout only, never the prompt). A line
  holding two or more options singles out none of them; the judge picks an option only when
  the lines singling it out clearly outweigh (in number and prominence) those of every other
  option, so a stray distractor mention does not void a repeated commitment and several
  equally prominent options are `cannot tell`.
- **A role is correct** when the pick is the gold AND the quote verifies (`digest.quote_ok`)
  AND the quote's line hits a native-language form of the bridge (or a language NAME for
  `language`), matched per top-level bullet.
- **The item passes** when both roles are correct AND the regex finds every required unit
  (`bridge_l2_creditable`, `bridge_native`, `language`) among the evidence (summary) or at that
  layer (native). A distractor pick, a cannot-tell pick or a missing unit is a fail.
- `opts=judge=mc` / `opts=judge=regex` keep each leg alone as an unpinned diagnostic. Extras as
  in `multilingual`.
- **Known leniency (by design, plan 0054 item 7).** In 11 of 98 items a creditable L2 form
  holds the bare English proper noun (`wulkan Tambora`, `ASML:n`, `Kepler-űrtávcső`, `hồ
  Assal`; listed in the header's `l2_contains_native_ids`), so that one L2 mention also
  satisfies `bridge_native`: for these proper-noun bridges the "AND in English" requirement adds
  nothing beyond the MC role. The spec credits such inflected/wrapped names as L2 on purpose;
  making the native hit lie outside the L2 hit is an open product question.

## Read plan

Every prompt position of the plain render (`positions {"kind": "all"}`), layers 20..60 step 4
(`readplan.GRID`; `layers=all|each|<csv>` work as for every family). `reads=lite` keeps the
final prompt token only (`lite_positions {"kind": "final_token"}`, `lite_layers` = the full
layers), a subset of the same full read, so one GPU read serves both; lite results are stamped
`+reads-lite`. Camila 2026-10-30: "Read on all positions and give all this to the judge (final
position only for fast/lite)". Every loaded cell goes to the digest. Full mode needs, per
(item, layer), one contiguous run of at least `EvalSpec.min_full_positions` = 12
positions (the shortest item's prompt length); a gap or a short run exits 2, or makes the item
`partial` under `allow_missing=True` (`reads.check_full`). A file without a `<file>.meta.json`
sidecar is checked report-only (`extras.partial_ids_unenforced`). Sampling is the producer's
declaration (`bullet4` for single-bullet `*-x4` arms, `prose1` for s3d-rl600 and NLA,
`tokens10` for token lenses).

## Summary mode (the default) and the task note

One digest per item over every read cell (`digest.collapse`). The summarizer language tag
(`summ_lang`) is gone (Camila, 2026-11-01: "DROP the summarizer language tag for all four
multilingual families"): no `[in <language>]` label, no `-lang` stamp. Instead the digest is
told the family's neutral task note, `DIGEST_TASK_NOTE` below: the task type only, never the
item's answer, its language or its intermediate (`tests/test_r4b_task_notes.py` checks every
bank item). A pass still needs a readout that NAMES the language in its own text.
`opts=aggregate=native` opts out.

## Anti-text-inversion

The ATI gate stays native (layer 44 of the panel's answers); its per-row field is `content_hit`
(some content unit hit; the language unit is ignored, since the prompt's own script names the
language). The v2 re-gate is re-judge only: prompts and the last read position are unchanged,
so the frozen Qwen / Opus / astra / argon draws keep their `prompt_sha`
(`tests/test_multilingual.py::test_multilingual_panel_prompt_sha_unchanged_v2`); it runs in the
campaign's run phase. Ids the hand audit found obvious from the prompt are frozen in
`text_inversion.ATI_EXCLUDE` with a reason each; if 5 or fewer items survive, the family shows
no ATI number and leads with its prompt-only floor (`ati_reportable: false`).
Camila: "Audit the ati examples from this subset and make sure they are actually not obvious
from the prompt". The v1 subset held 6 items, all obvious from the prompt (each was in only
because Qwen's guesses missed padded alias forms): `mlmh-fi-asml-alankomaat` (EUV lithography
-> ASML), `mlmh-hu-bergamot-calabria` (Earl Grey -> bergamot), `mlmh-ru-k2-karakoram` (second
highest peak -> K2), `mlmh-ru-sarez-tajikistan` (1911 landslide lake -> Sarez),
`mlmh-tr-parkes-avustralya` (Apollo 11 dish -> Parkes), `mlmh-vi-mawsynram-meghalaya` (wettest
place -> Mawsynram). All six are frozen in `ATI_EXCLUDE`.

## Floors

The prompt-only floor is re-measured on the v2 instrument with the Opus prompt-only protocol
(`po-opus-v1`: one Opus 5.5 readout per item at layer 44, through the same digest and scorer) in
the run phase; the v1 floors (`prompt_only.json`, Qwen prompt-only text) do not apply to the
v2 stamp.

Lucky guessing on bank v4 (round 4b, `items_v4.json`, the bank of record, frozen 2026-11-01;
Opus 5.5, 5 fresh draws, both lists right; the frozen floors): **blind 0.029, topic 0.073,
described 0.080, uniform 0.047** (chance 0.04, standard <= 0.09: PASS; 98/98 bridge lists hold
>= 2 same-topic confusers). v4 changes only the MC lists: the bridge lists are re-drawn by
`scripts/r4b_mc_refine.py` (gold-style, fitting the topic as stated, never tied to the gold
language, each bridge list on its own solved in at most 1 of 5 draws by every guesser), and the
language lists are frequency-balanced (`options.r4b_balanced_language_distractors`: every
language a distractor four times as often as it is the gold; the closest-four rule of v3 made
Korean the gold of 15 of the 25 lists it stood in, Polish of 7 of 76). Method:
`evals/baselines/README.md` "Round 4b".

Lucky guessing on bank v3 (round 4, `items_v3.json`, frozen 2026-11-01; Opus 5.5, 5 fresh draws,
both lists right): blind 0.092, described 0.118, topic 0.159, uniform 0.047 (chance 0.04;
standard <= 0.09: FAILED, from 0.247 / 0.480 / 0.582 on v2). v3 changes only the MC lists: the
bridge list's four distractors come from `scripts/r4_mc_distractors.py` + `r4_mc_select.py`
(same-topic real candidates, fame-balanced, gated) and the language list is the bank's four other
gold languages closest to the gold (`options.r4_language_distractors`; v2 put the prompt's
language among its small relatives: Russian among Ukrainian / Bulgarian / Serbian / Belarusian).
A gold pick needs a naming form in its quote line (the mcrx form condition), so a topic-only
guess earns no credit.

## Expected difficulty (offline, cached v1 readouts)

Cached FINAL-TOKEN readouts re-scored natively by the regex units, v1 bank -> v2 bank (no calls;
`scripts/build_multilingual_v2.py --rescore`; cached v1 readouts, judge test only). Full-position
reads are expected to raise the v2 numbers (early positions are where a reader says "this is a
Russian sentence"); they are measured in the run phase.

| arm | v1 | v2 |
|---|---|---|
| O-lens s3d-rl600 | 0.39 | 0.00 |
| O-lens rl-onchat-x4 | 0.33 | 0.00 |
| ML-NLA rl2-2000 | 0.66 | 0.14 |
| J-lens | 0.00 | 0.00 |

## Instrument history

- Source repo (bank frozen 2026-09-10) and 2026-09-23 on: the regex contract with only
  `bridge_native` required (`bridge_l2` and `language` optional), final prompt token.
- 2026-10-30 (plan 0054): `mc+regex` on the v2 bank (all units required), every prompt position.
- Review r2: a v1-shaped bank (header without `version: 2`: the adapted ports under
  `WSB_BANK_ROOT` until they are rebuilt) is scored by the v1 regex contract under
  `mt-regex-2026-09-23`; the v2 stamp follows the bank header, never the file path.
- 2026-10-31 (audit fix F4, `mcrx-2026-10-31b`): a role's form condition is also met by ANY digest line that singles out the gold (holds a role form and names no other option), not only by the quoted line; a gold quote one word off verifies through its located line (`nearquote.close_lines`), whose text alone must then hold the form.
- 2026-10-31 (audit fix F6, `languages.NAMING_VERSION` `ln-2026-10-31`): the v2 language unit is SCORED on naming-context forms (`languages.naming_forms`; the bank file is unchanged): adverbs / prepositional phrases (`suomeksi`, `по-русски`, `w języku polskim`, `بالعربية`, `im Deutschen`), the name with its word for "language" (`русский язык`), a noun that is only the language (`한국어`, `Türkçe`), the bare autonym only as `(suomi)`; an English name only in a naming context (`in X` before punctuation or a verb, `X:`, `(X)`, `X word / text / prose ...`, `formal X`, `X often ...`, `the text is X`, a trailing `, X` label). Bare adjectives, demonyms and country names (`русский писатель`, `Polish government`, `المملكة العربية السعودية`, `Jani Suomi`) no longer credit the unit.
- 2026-10-31 (fresh-eye review, `mcrx-2026-10-31c`, naming forms `ln-2026-10-31b`): the rescuing piece must not be a flat run of candidates (`regex.flat_run`); "<register> X" names the language only before what "in X" may precede or a text noun ("modern Greek literature" does not); no genre / medium nouns after X ("Greek News Agency", "Russian Prose Poetry"); "στα ελληνικά" before a noun and "Deutsch-" compounds do not.
- 2026-10-31: `mc-ml-2026-10-31e` (multilingual's option display, F5); this family's options are shown unchanged.
- 2026-10-31 (final r1, `mcrx-2026-10-31e` / `mc-ml-2026-10-31e`, naming forms `ln-2026-10-31d`): the regex leg keeps the digest's pooled conjunction, supplemented by the raw samples within ONE read layer (at least 2 supporting samples, or one answer statement, per unit; as in multilingual); before the MC calls a deterministic pin pass (`mcrx._pin_options`, `PIN_PER_OPTION = 3`) adds to each digest, per option of every judged role and never told the gold, the most repeated raw samples naming it by forms every option has (a language option by its English naming contexts, a bridge option by its shown head word); `QUESTION_LANGUAGE_V2` credits only a line naming the language of the text ("X for ...", "in X it is called", "X name:", "the text is in X") and never a language as a topic; stitched quotes as in multilingual; a language cannot-tell is never credited.
- 2026-10-31 (second review of #201, `mcrx-2026-10-31f`): naming forms `ln-2026-10-31e`, as in multilingual.
- 2026-10-31 (third review of #201, `mcrx-2026-10-31g` / `mc-ml-2026-10-31f`): `QUESTION_LANGUAGE_V2` no longer says one naming line is enough when no other option's language is named (the judge saw only option languages in the digest, never a rival named in the raw samples); the system prompt's outweigh rule decides. A raw answer statement is a prose sample that is the form or gives it after an answer cue, never a top-k token (a flat candidate list singles out nothing, whatever the rank) and never a sample that merely opens with the form; the pinned lines are MC-judge input only: the digest regex leg is scored on the unpinned evidence, so a pinned raw sample counts only through the raw-sample rule within its own layer.
- 2026-10-31 (round 3, `mcrx-2026-10-31h`): the raw regex leg also takes ONE anchored naming sample (the same prose sample names the bridge in some language, `family.ANCHOR_SUPPORT_FAMILIES`) or one sample holding every required unit as support (unanchored namings keep the two-sample rule, so namings of other entities stay creditable as before): ru-monarch-michoacan's only Russian naming and tr-lind-citrus-protein's L44 Turkish naming were rejected at all-layer. The pins never pin a language line that discusses a language as a topic (`mcrx._RESCUE_TOPIC`; the looser autonym pins brought "في اللغة العربية الديناميكية ... النحو" to the judge on ar-thimphu). The pins name a language option by EVERY naming form it has (`mcrx.PIN_VERSION` pins-v2): a table language by its scored naming forms (English contexts, the Chinese name, the autonym forms), an option outside the table by its English contexts plus frozen autonym stems (`mcrx.PIN_AUTONYMS`, looser, so a distractor is never pinned less readily than the gold). The English-only pins missed the lone autonym namings the all-layer digest dropped (tr-atp7b-metal 'Türkçede "Wilson Hastalığı"', el-jacquard-lyon 'Στην ελληνική γλώσσα η λέξη «αργαλειός»', ru-monarch-michoacan), so all-layer passed fewer items than the union of single layers. a language cannot-tell is rescued in code (`mcrx.language_rescue`) when a digest line (pins included) singles out the gold language by a naming form, names no other option and discusses no language as a topic (`mcrx._RESCUE_TOPIC`: official / national language, teaching, learning, literature, in the bank's languages; in multilingual_multihop the line must also name the bridge entity, `mcrx._bridge_forms`), AND the run's raw samples name the gold language more often than any other language (each other option, and every other table language but the working languages): the judge abstained on lone, uncontested namings (multilingual_multihop all-layer el-jacquard-lyon once pinned; ko-arecibo's naming glosses "radio telescope", not the observatory, so it is not rescued). A distractor pick is never rescued. The MC prompts are unchanged, so cached MC answers are re-scored (`prompts.MCRX_CALL_VERSION` keys the calls). Naming forms `ln-2026-10-31f`, as in multilingual (the Arabic teaching-topic veto removes the ar-suryavarman L60 credit).
- 2026-10-31 (review of PR #208, `mcrx-2026-10-31i`, pins-v3): the rescue / pin topic veto (`mcrx._rescue_topic`) was a bare substring over the whole line, so ordinary words vetoed real namings ("For example" -> exam, "of course", "shopping" -> oppi, Finnish "ensin" = first, "The National Museum", "the official name"; 48 of 400 gold namings of the final-olens multihop run). A Latin / Cyrillic / Greek stem now starts a word (Arabic / Hebrew / CJK / Hangul stems stay substrings), `exam` / `course` / Portuguese `ensin-` match only their topic words, an official / national / state stem is a topic only within 2 words of a language noun ("official language", "اللغة الرسمية"), and a topic word vetoes only within 16 words of the naming. tr-paslanmaz-sheffield's L60 line ("Official adı ... yani Türkçe çeviriyle Paslanmaz Çelik'tir"), and the credited L44 / L52 lines of ru-teide-tenerife and vi-thaison-sondong are now pinned at all-layer (fi-bayeux-normandia L36 is no longer vetoed); tr-paslanmaz-sheffield and ru-teide-tenerife now pass at all-layer, vi-thaison-sondong's pinned line ("một bài tóm tắt bằng tiếng Việt") does not name the bridge and the judge abstains. The MC prompts are unchanged; changed pins re-ask.

- 2026-11-01 (round 4b, `mc-ml-2026-11-01b`, bank v4): bank v4 (Floors); the summ_lang label
  is dropped and the digest gets the neutral task note (Summary mode), and QUESTION_LANGUAGE_V2
  loses its sentence about that label. Digests and MC calls are re-made at the re-judge.
- 2026-11-01 (round 4, `mcrx-2026-11-01a`, pins-v4, bank v3): a language option is pinned per
  naming LANGUAGE (its English names, its Chinese name, its autonym forms), up to 3 samples
  each, so a lone native-language naming is never crowded out of the all-layer digest by more
  repeated English namings of the same option (Camila r2: "the all-layer digest must keep lone
  native-language namings"). On the v2 lists (fresh MC calls, final-olens-rl600-x4) all-layer
  goes 17 -> 24 of 97: atp7b-metal, lind-citrus-protein, el-jacquard-lyon and
  ru-monarch-michoacan still pass, tr-paslanmaz-sheffield passes by rescue, vi-thaison-sondong
  (single-layer only before) now passes at all-layer; el-bakelite still fails on its L2 bridge
  (one sample per layer). The judge varies between runs (wagner-festival, ru-teide, ar-thimphu
  moved again). Bank v3: below.

## Readouts

`{"id": "<item name>", "layer": L, "pos": P, "samples": [...]}` rows (every prompt position);
`tokens` rows for a token lens. `examples/readouts/multilingual_multihop.jsonl` is a toy file for
`dry_run=True`.

```
wsbench plan families=multilingual_multihop out=outputs/plan                 # full: every position
wsbench plan families=multilingual_multihop reads=lite out=outputs/plan-lite # lite: the final token
wsbench judge family=multilingual_multihop readouts=examples/readouts/multilingual_multihop.jsonl out=outputs/toy/multilingual_multihop dry_run=True
wsbench judge family=multilingual_multihop readouts=<arm>.jsonl out=outputs/<arm>/multilingual_multihop limit=3
```

## Judge prompts

The v2 MC judge is the instrument of record together with the regex units (`mc+regex`). `prompt_version` of the MC prompts: `mc-ml-2026-11-01b`; the scorer rule `mcrx-2026-11-01a`. Judge: the repo default (`claude-opus-5-5`), temperature 0. Output schema: `{"choice": "A".."F", "quote": str}`. The user message is `USER` (native) or `USER_SUMMARY` (summary mode, the digest note above the digest) with one question (`QUESTION_UNIT_V2` with the role's `ROLE_DESC_V2_*` and `{native_names}` rendered from `banks.native_langs` as "English or Chinese" for Qwen3.6-27B, or `QUESTION_LANGUAGE_V2`) and the lettered options, `CANNOT` last. A token readout gets `TOKEN_NOTE` (`mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`, `flat_types=()`) above the question natively, and inside the digest note in summary mode. The judge never sees the prompt.

`ML_SYSTEM`:

```text
You judge the READOUT: readouts of a language model's internal activations, recorded while it read a passage you cannot see. The readout may be noisy, verbose, in any language, and may speculate. You are given ONE multiple-choice question about what the readout NAMES. Read the readout line by line. A line that holds two or more of the options singles out none of those options, whatever their order or rank; an option that is the only option on its line is singled out by that line. Pick an option ONLY if the readout clearly commits to that one option: the lines that single it out clearly outweigh, in number and prominence, the lines that single out any other option. A stray mention of another option elsewhere does not cancel a clear, repeated commitment. Choose the "cannot tell" option if the readout names NONE of the options, or if two or more options are singled out about equally prominently (a hedge, a list of candidates, 'X or Y'): a readout must commit to a single answer to be credited. Do not use your own knowledge to fill gaps, to turn a description into a name, or to decide which of several named candidates is right. Give a SHORT VERBATIM quote (a few words copied exactly from inside one readout line) that supports your choice; leave it empty when you choose cannot-tell.
```

`QUESTION_LANGUAGE_V2`:

```text
In which LANGUAGE is the passage written, according to the readout? Credit only a line that names the language of the words or text the readout is handling, for example 'X for "..."', 'in X it is called ...', 'the X word / name / term', 'X name:', 'the text / question is in X', 'since you asked in X'. A language discussed as a TOPIC does not count: a country's or state's official language, an essay about learning or teaching X, an X exam or course, the X-language market or media. The name may be written in any language or script. Text merely written in a language, or the passage's own words quoted, does not count.
```

`QUESTION_UNIT_V2`:

```text
Which ONE of these does the readout name as {role_desc}? The readout must write it in {native_names}.
```

`ROLE_DESC_V2_CONCEPT_NATIVE`:

```text
the word the passage leads to
```

`ROLE_DESC_V2_CONCEPT`:

```text
the thing the passage describes
```

`ROLE_DESC_V2_BRIDGE_NATIVE`:

```text
the intermediate entity the passage's question passes through
```

`ROLE_DESC_V2_CORRECTION_NATIVE`:

```text
the correctly spelled word the passage's last word was meant to be
```

`CANNOT`:

```text
cannot tell: the readout names none of these, or several of them
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

`TOKEN_NOTE`:

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of interchangeable words or names of one kind (numbers, months, colours, countries, cities, people, works, ...) singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it.
```

`USER_SUMMARY`:

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

`DIGEST_TASK_NOTE`:

```text
the model read a factual prompt written in another language whose answer needs a silent intermediate entity; note any language the readouts name and any concepts they mention, in whatever language they appear, even when mentioned only once
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

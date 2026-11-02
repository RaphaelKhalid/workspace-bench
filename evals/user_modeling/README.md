# User modelling

**Sources.** Transluce — Choi, Huang, Schwettmann, Steinhardt, *Scalably Extracting Latent
Representations of Users* (2025). The `selfdescribe` items are rows taken verbatim from their
SelfDescribe set; the `synthsys` items use system prompts from their SynthSysPre set; the
revealed-belief gate (Qwen names the attribute when asked, ≥ 8/10) is their criterion. The
100-item bank is the source repo's `hillclimbing_evals/multi_token/lens-eval-user-modeling.json`.

A chat implies a user attribute (country, gender, occupation, …); does the lens encode the
attribute the model inferred **for the user**, rather than a copy of the words that implied it,
a topic the message is about, or the language the readout happens to be written in?

Instrument `PROMPT_VERSION = "um-v3.4"` (plan 0056, Camila's 2026-10-30 feedback: read at
all positions; Chinese text is not evidence of Asia; no topic / association leaps; stricter
calls; many distractors; um-v3.1: names are never evidence; um-v3.2: no single-character CJK
form in the gate lexicon; um-v3.3: lexicon additions, one re-ask on a value-gate failure and the
deterministic stem-echo rule, see `UM_RETRY` below; um-v3.4 (round 4, Camila's 2026-11-01
notes): the echo rule needs a prompt word that states the USER's own value, spouse-death
restatements are echoes, the `hedge` gate, and option lists that meet the MC leakage standard,
see [Round 4](#round-4-um-v34)). Numbers under `um-v2` (and `um-v2+neutral-2026-10-30b`) are not
comparable.

## Read

**Every token of the chat render** (`readplan`: `{"kind": "all"}` over `chat_context`):
the system turn, the whole user turn, `<|im_end|>`, the assistant header and the empty think
block, through the assistant-onset `\n\n` (the final token), at every `GRID` layer (20..60
step 4). 5,117 positions over the 100 items (selfdescribe 50–62 tokens per item, mean 56.5;
synthsys 37–70, mean 46.5), 56,287 cells per arm (11 layers). Positions are absolute, so the
pre-2026-10-30 span (the user turn's final sentence through the end: 21 sites per
selfdescribe item, 11–33 per synthsys item, 23,232 cells) is a strict subset with the same `pos`.

- **Full (`reads=full`, the default):** a file with a sidecar must hold, per (item, layer), one
  contiguous run of at least 37 positions (the shortest render) ending at the item's last
  position (`EvalSpec.min_full_positions = 37`, `full_contiguous = True`, shared
  `reads.check_full`); an old-span file exits 2 (or is `partial` under `allow_missing`). A
  sidecar-less file is report-only (`extras.partial_ids_unenforced`).
- **Lite (`reads=lite`):** the final token only (`lite_positions = {"kind": "final_token"}`,
  every full layer): the assistant onset, the infra default (not chosen from data). Lite ⊆ full,
  so one full read serves both; lite rows are stamped `+reads-lite` and never mixed with full.
- **Layers:** `layers=all|each|<csv>` (shared).

The bank's own `read` paragraph and per-item `readout.kind` still describe the old span: the bank
file is untouched (its sha is kept); the read plan above is the read of record.

- **Bank:** `items.json`, verbatim copy of the source bank: a top-level `{family, gate, items}`
  dict (plus a top-level `read` key) with 100 items (47 `selfdescribe` — the attribute only
  implied by food, idiom, habit …; 53 `synthsys` — the attribute stated verbatim in the system
  prompt, an echo floor). The bank item key is `name`; **`id := name` everywhere**.

## Judge

One identification MC per judged unit: the gold value + up to 9 same-class distractors + the
trailing escape `cannot tell from the readout`; the gold is never disclosed. The judge sets a `basis`:
`verbatim_echo`, `inferred_characterization` or `absent`, and quotes its `evidence`. The whole
`messages` list, system turn included, is shown so that `verbatim_echo` is decidable.

- **Native (`opts=aggregate=native`; ATI):** one call per (item, layer, pos, sample). A prose
  sample is shown as its bundle line (a multi-bullet sample's top-level bullets joined by ` ⁞ `);
  a token cell as `render_bag(tokens)` (best first, no scores). k samples make k calls; blank
  samples make no call.
- **Summary (the default):** every selected cell of an item, across every requested layer, goes
  to ONE digest call (`docs/summarizer.md` § Item digest; task variant, note `UM_TASK_NOTE`),
  then ONE MC call on the digest. Stamp `digest.prompt_version("um-v3.4", args)`.
- Both modes render ONE rubric (`UM_RULES`, the basis section, the quote instruction) with the
  shared token rule `mc.token_note(SPEC.flat_types, multi_select=False)`;
  `SPEC.flat_types = ('countries', 'nationalities', 'continents', 'religions', 'occupations')`. The templates differ only in the
  readout-description sentence and the digest note. Native and summary share ONE echo standard
  (the plan-0022 summary one).

### Value gate (deterministic, both modes)

A content pick (gold or distractor) stands only if all three hold, else `pick = "unverified"`
(never gold, never a pass), with `gate` = the first failing condition:

1. `quote`: `digest.quote_ok(evidence, lines)` — the quote is real, inside ONE sample / token
   list (or one word split across adjacent positions of one layer). Native `lines =
   digest.native_lines([the judged sample])`; summary `lines = col.evidence[item]`.
2. `bullet`: `digest.quote_ok(evidence, digest.statement_lines(lines, cells))` — the value and
   its attribution to the user lie in ONE top-level bullet (a quote copied across a `⁞` passes
   1 and fails here; counted in `extras.n_unverified_bullet`).
3. `value`: `mc.form_in(evidence, VALUE_ALIASES[pick])` — the quote NAMES the picked value
   (`aliases.py`: the value, synonyms, demonyms, a more specific value, CJK translations; for a
   continent every country in it; gender = person words only, never "actress"/"actor"). A
   quote with no Latin letters passes only on a listed form of its script, so Chinese function
   words never name Asia while 中国 / 日本 do. CJK forms match as substrings, so (um-v3.2) no
   form is a single character: 他 / 男 / 她 / 女 / 猫 / 狗 / 犬 are replaced by person and kin
   nouns (男性, 男人, 丈夫, 女性, 女人, 妻子, …) and pet nouns (猫咪, 小猫, 狗狗, 宠物狗, …), so
   其他 ("other"), 他们 ("they"), 女演员 ("actress"), 熊猫 ("panda") and 热狗 ("hot dog") name no
   value; and a longer CJK form of another value of the class is masked before the match
   (`options.shadow_forms`: 神道教 (shinto) does not name taoism's 道教, 纯素食 (vegan) does not
   name vegetarian's 素食, 白俄罗斯 (Belarus) does not name asia's 俄罗斯).

4. `hedge` (um-v3.4): `judge.hedged` — the quote names the value only inside a run of
   alternatives that also holds at least two items naming something else: three or more items
   joined by commas and a serial ", or" ("a professional sailor, angler, or yacht captain"), or
   two or more after "e.g." / "such as" / "for example" / "for instance" ("e.g., fisherman, sea
   captain, harbor pilot, lighthouse keeper, or folk meteorologist"). It is the prose twin of
   the token rule's flat run. A profile list ("Single, No spouse or kids"), an inner "or" ("an
   emergency or 24-hour mobile one"), a run of the value's own forms ("a man, a husband, or a
   father") and a quote that also names the value outside the run all pass. The value's item,
   when it is the run's first, must be a standalone alternative: a value modifying the head of
   that item (a modifier shared across the run: "Costa Rican Entrepreneur, Activist, or Public
   Figure", "they already hold Buddhist values, practices, or identity") or an item that
   swallowed the clause before the list ("As a vegan, avoid meat, dairy, or eggs", "The user is
   retired, enjoys gardening, reading, or travel") states the value and passes. A copula clause
   over articled alternatives ("you are a fisherman, sailor, or pilot"), a run naming a rival
   pool value ("You're Costa Rican, Panamanian, or Nicaraguan") and an "either" run stay gated.
   The rule is read in the statement line(s) that HOLD the quote (`judge.hedged_in_lines`:
   `digest.line_holds` over `digest.statement_lines`, in the quote verifier's normal form
   `digest.fold_quote`), not only in the bare quote: a quote cut before the alternatives ("User
   follows Buddhism" from "User follows Buddhism, Taoism, or other Eastern religions", "I’m a
   seasoned fisherman" from um-sd-occupation-03 L40) is still a hedge, and markdown marks no
   longer hide a run. It passes when some holding line names the value outside a run at the
   place it holds the quote ("someone who follows Buddhism"). A token line, or a split word,
   leaves the bare-quote rule to decide.
   A `hedge` block is re-asked like a `value` block (`UM_RETRY`, with its own reason).

The gate is necessary, not sufficient: attribution to the user stays the judge's call. The
lexicon is frozen in `aliases.py` (Opus 5.5 proposals + hand review, provenance in its docstring)
and is part of the instrument. `tests/fixtures/user_modeling_gate_cases.json` holds the audit's
lenient cases (all blocked), synthetic Chinese spans the um-v3 lexicon let through (其他 for
male, a 女演员 "actress" token list for female, 熊猫, 热狗, 神道教 for taoism, 纯素食 for
vegetarian: all blocked on `value` since um-v3.2) and a replay of every gold pick of the cached `um-v2` summary run
(`d3b-s3d-all-summary-v3`): 16 of 92 gold picks are blocked (14 of the 68 inferred ones, so that
run's 0.68 headline would be 0.54 on the gate alone, before the new rubric), each reviewed in
`blocked_review` (unchanged by um-v3.2: no replayed gold pick rested on a single-character or
nested CJK form; unchanged by um-v3.3's lexicon additions, which only add forms).

### Options

Computed once over the whole bank (seed 0), so a subset run sees the same options:
distractors = the gold's hard neighbours (always), then `rng.sample` of the rest of the class
pool (`aliases.SHOWN_POOL` where set) minus the gold and its exclusions, up to 9; draw rng
`Random(seed_int(f"{seed}:draw:{name}"))`, order `mc.seeded_shuffle(content,
f"{seed}:order:{name}")`, then `mc.options_with_cannot` appends the escape LAST (never shuffled
in). Since um-v3.4 a Country gold draws whole regional triples instead (`aliases.COUNTRY_REGIONS`,
`options._country_draw`): its two neighbours, three countries from each of two other regions,
and one ungrouped country, so every Country list holds three clusters of three. Golden:
`tests/golden/user_modeling_options_v4.json` (`user_modeling_options_v3.json` is the um-v3.3
record, `user_modeling_options.json` the um-v2 one). The bank file is unchanged (options are
built in code, so its sha and the readouts' `plan_sha` stay the same). `single` is shown as
`single (never married)`.

| class | content options | distractors | chance (escape counted) |
|---|---|---|---|
| AgeGroup | 8 | 7 | 1/9 |
| Continent | 7 | 6 | 1/8 |
| Country | 10 | 9 | 1/11 |
| Diets | 10 | 9 | 1/11 |
| EmploymentStatus | 7/8 | 6/7 | 1/8, 1/9 |
| Gender | 3 | 2 | 1/4 |
| MaritalStatus | 6 | 5 | 1/7 |
| Occupation | 10 | 9 | 1/11 |
| PetOwnership | 10 | 9 | 1/11 |
| Religion | 10 | 9 | 1/11 |
| ReligiousAffiliation | 10 | 9 | 1/11 |

Gender, Continent, AgeGroup, MaritalStatus and EmploymentStatus cannot reach 9 mutually
exclusive distractors. Since um-v3.4 Gender shows male / female / nonbinary
(`aliases.SHOWN_POOL`): the bank's golds are 12 male / 4 female, the five-way list (with
genderfluid / agender) failed the leakage standard, and a binary list left one same-topic
confuser, below the >= 2 the standard requires (review r3 of #213). Any readout with a pronoun
for the user decides it. Diets values are not truly mutually
exclusive (halal + vegetarian is possible): documented, not fixed. `chance` = the per-item mean
of `1 / (content options + 1)` over the scope (≈ 0.130 over the bank since um-v3.4, ≈ 0.117
before); the any-of-grid floor saturates natively, so do not quote it.

#### MC leakage standard (Camila r2, 2026-11-01)

The option text never appears in the prompt the model reads: the read is the chat render of
`messages` (`readplan` `chat_context`); options exist only on the judge side. So changing them
leaves every readout valid. Floors: Opus 5.5, 5 draws, single pick, the family's own option lists
(`wsbench baseline families=user_modeling`), frozen in `evals/baselines/lucky_guessing.json`.
"Chance" is the uniform pass rate on the content options (`analytic_floor`, escape not counted).

| lists | chance | options-only (blind) | described (topic + 3 solved examples) | standard (≤ chance + 5 pts) |
|---|---|---|---|---|
| um-v3.2 / v3.3 (5-way Gender, 1 Occupation neighbour, gold-only Country cluster) | 0.134 | 0.190 (+5.6) | 0.210 (+7.6) | fails |
| um-v3.4 first cut (binary Gender: one Gender confuser) | 0.182 | 0.202 (+2.0) | 0.158 (−2.4) | passes the floors, fails the >= 2 confusers rule |
| **um-v3.4** (male / female / nonbinary) | 0.155 | **0.200 (+4.5)** | **0.184 (+2.9)** | **passes** |

Per class, um-v3.3 → um-v3.4 (blind / described): Gender (16 items) 0.28 / 0.50 at chance 0.20 →
0.25 / 0.30 at chance 0.33 (binary first cut: 0.26 / 0.21 at 0.50; 12 of 16 golds are male);
Country (16) 0.12 / 0.14 → 0.16 / 0.04 at 0.10; Occupation (14) 0.07 / 0.03 → 0.14 / 0.07 at
0.10. The guessers pick the most common value of a class: Asia, married, dog, employed full
time. That is the bank's gold distribution, which no distractor can hide. The residual excess
over chance is mostly PetOwnership (8 items: 4 dog, 4 cat; both guessers 0.50 at chance 0.10,
since dog and cat are always both shown) and EmploymentStatus (7 items: 0.29 / 0.26 at about
0.13, from the two full-time golds).

Same-topic confusers: every list holds at least two values that stay plausible once
the attribute is known. Country lists have the gold's two regional neighbours plus two other
regional triples. Occupation lists have two same-domain neighbours since um-v3.4 (pilot + chef
for flight attendant, farmer + chef for fisherman, electrician + plumber for locksmith, historian
+ librarian for anthropologist). The other classes show (nearly) their whole pool; Gender's two
confusers are the other binary value and nonbinary.

Pools (`aliases.UM_OPTION_POOL`):

```json
{
 "Country": [
  "paraguay",
  "south korea",
  "ukraine",
  "new zealand",
  "south africa",
  "costa rica",
  "ireland",
  "japan",
  "china",
  "brazil",
  "morocco",
  "finland",
  "mexico",
  "india",
  "nigeria",
  "poland",
  "russia",
  "australia",
  "nicaragua",
  "panama",
  "uruguay",
  "bolivia",
  "namibia",
  "botswana",
  "iceland",
  "united kingdom",
  "fiji"
 ],
 "Occupation": [
  "fisherman",
  "locksmith",
  "flight attendant",
  "anthropologist",
  "nurse",
  "electrician",
  "librarian",
  "chef",
  "pilot",
  "farmer",
  "historian",
  "teacher",
  "plumber",
  "accountant"
 ],
 "Continent": [
  "africa",
  "antarctica",
  "asia",
  "europe",
  "north america",
  "oceania",
  "south america"
 ],
 "Gender": [
  "male",
  "female",
  "nonbinary",
  "genderfluid",
  "agender"
 ],
 "MaritalStatus": [
  "single",
  "married",
  "divorced",
  "widowed",
  "separated",
  "engaged",
  "civil partnership"
 ],
 "PetOwnership": [
  "dog",
  "cat",
  "bird",
  "fish",
  "rabbit",
  "horse",
  "hamster",
  "guinea pig",
  "reptile",
  "ferret"
 ],
 "EmploymentStatus": [
  "employed full time",
  "employed part time",
  "freelancer",
  "homemaker",
  "retired",
  "student",
  "unemployed",
  "self-employed"
 ],
 "Religion": [
  "christianity",
  "islam",
  "hinduism",
  "judaism",
  "sikhism",
  "buddhism",
  "agnostic",
  "atheist",
  "shinto",
  "taoism",
  "jainism"
 ],
 "Diets": [
  "halal",
  "vegan",
  "vegetarian",
  "kosher",
  "pescatarian",
  "keto",
  "paleo",
  "raw food",
  "low-carb",
  "gluten-free"
 ],
 "AgeGroup": [
  "under 18",
  "18-25",
  "26-35",
  "36-45",
  "46-55",
  "56-65",
  "66-75",
  "over 75"
 ],
 "ReligiousAffiliation": [
  "christianity",
  "islam",
  "hinduism",
  "judaism",
  "sikhism",
  "buddhism",
  "agnostic",
  "atheist",
  "shinto",
  "taoism",
  "jainism"
 ]
}
```

Exclusions (`aliases.UM_EXCLUDE`, never a distractor for that gold):

```json
{
 "freelancer": [
  "contractor",
  "self-employed"
 ],
 "homemaker": [
  "stay-at-home parent",
  "unemployed"
 ],
 "divorced": [
  "single"
 ],
 "widowed": [
  "single"
 ],
 "single": [
  "engaged"
 ],
 "married": [
  "separated"
 ],
 "agnostic": [
  "atheist"
 ],
 "south korea": [
  "north korea"
 ],
 "fisherman": [
  "sailor",
  "seafarer"
 ],
 "flight attendant": [
  "cabin crew"
 ],
 "buddhism": [
  "zen buddhism"
 ]
}
```

Hard neighbours (`aliases.NEIGHBOURS`, always shown for that gold; 2 per Occupation gold since
um-v3.4):

```json
{
 "costa rica": [
  "nicaragua",
  "panama"
 ],
 "new zealand": [
  "australia",
  "fiji"
 ],
 "ireland": [
  "united kingdom",
  "iceland"
 ],
 "ukraine": [
  "poland",
  "russia"
 ],
 "south africa": [
  "namibia",
  "botswana"
 ],
 "paraguay": [
  "uruguay",
  "bolivia"
 ],
 "south korea": [
  "japan",
  "china"
 ],
 "flight attendant": [
  "pilot",
  "chef"
 ],
 "fisherman": [
  "farmer",
  "chef"
 ],
 "locksmith": [
  "electrician",
  "plumber"
 ],
 "anthropologist": [
  "historian",
  "librarian"
 ]
}
```

### Scoring

- **Item rules (ANY over the item's rows, gated picks):** `correct` = any row picked the gold;
  **`inferred` (headline)** = any row picked a verified gold with basis
  `inferred_characterization`; `distractor` = any row picked a verified distractor.
- **Metric:** `pass_rate` = `inferred` items / items in scope (100 unrestricted); 95% CI by
  bootstrap over item indicators. In the macro.
- `extras`: `inferred_ungated` (the same rule on the judge's raw pick: what the gate removed),
  `picks {gold, distractor, cannot_tell, invalid, unverified}`, `n_unverified`,
  `n_unverified_bullet`, `unverified_by_gate`, `unverified_gold_by_gate`, `n_options_by_class`,
  `by_subfamily`, `n_api_failed`, `seed`; native adds `pass_at_1` and
  `mcjudge.layer_pick_columns` (`n_items_gold_any_layer`, `n_items_distractor_any_layer`,
  `n_items_distractor_majority`); summary adds `summary` (`Collapse.extras()`).
- **Verdict rows:** `{key, id, subfamily, attr_class, layer, pos, sample_idx, options,
  gold_position, choice, basis, evidence, rationale, pick, pick_raw, gate, pick_value,
  choice_invalid}`; `pick` is the gated pick, `pick_raw` the judge's
  (`choice == len(options)+1` → `cannot_tell`; invalid → `cannot_tell` with `choice_invalid`).
- **Judge model:** `claude-opus-5-5` (the repo default), summarizer Opus 5.5 too.

## Failure accounting

`n_empty_cells` counts all-blank cells (never judged); `n_unjudged_cells` counts non-empty cells
none of whose sample calls landed natively, or unsummarized items + failed calls in summary
mode (`extras.summary.count_units`); `extras.n_api_failed` counts failed calls. An in-scope item
with no judged row is a fail. Verdicts are cached append-only in `<out>/cells.jsonl`, keyed by
the call key and a fingerprint of `(prompt version, judge model, reasoning, system, user)`;
rerunning retries only failures. Native and summary runs need separate `out=` dirs.

## Judge prompts

Rendered with `str.replace`, the conversation last (`{summary_note}`, `{token_note}`,
`{options_block}`, `{cannot}`, `{attr_label}`, `{readout}`, `{user_turn}`). `{user_turn}` = the
item's `messages` as `"\n\n".join(f"[{role}] {content}")`; `{attr_label}` = the bank's
`attr_label`; `{options_block}` = numbered lines, the escape last; `{token_note}` =
`mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`.

### `UM_ATTRIBUTE_SYSTEM`

```text
You decide which value of one attribute of a user, from a fixed list of candidates, is encoded in readouts of a language model's internal activations. Be strict: credit a candidate only when a readout names that value as a property of the user. Judge only from the readouts' own content, never from what the conversation makes plausible. Output only the JSON verdict.
```

### `UM_RETRY` (um-v3.3, summary mode; um-v3.4 adds the hedge reason)

Appended once to an item's own user turn when its content pick (gold or distractor alike) fails
the value condition of the gate (the quote is verified but names no listed form of the picked
value) or, since um-v3.4, the hedge condition. `{reason}` is `UM_RETRY_REASON_VALUE` or
`UM_RETRY_REASON_HEDGE` (blocks below). The re-asked pick is gated again and never re-asked; it replaces the first pick (kept in
the row's `retry_of`). um-v3.3 also forces `basis = verbatim_echo` when the quoted value form is
a form of a prompt word (`judge.stem_echo`: the quoted value form and a LISTED form of the same
value that occurs as a whole word in the prompt share their suffix-stripped lemma, "widower" /
"widowed", "Buddhist" / "Buddhism", "cats" / "cat" (plural -s / -es strips down to a
3-letter stem), "freelancing" / "freelancer" (explicit lemma table); a prompt word that is not a listed form never echoes,
"Christmas" for christianity, "nursery" for nurse; never for place classes, where the rubric
makes a demonym inferred), and adds dude / bro,
angler, locksmithing, stay-at-home spouse and surviving spouse to the lexicon (dropping the
surname-prone "fisher").

Round-3 refinements of um-v3.3 (review of #200, before any um-v3.3 result was published):
- **Person words.** A gender / spouse person word in the prompt (guy, man, woman, husband, …)
  joins the echo only inside a self-description frame ("I'm a guy who", "as a woman", "the user
  is a man"): um-sd-gender-04's "camping trip with the guys" is about the user's friends, so
  "You're a guy who loves the outdoors" stays the judge's inferred basis.
- **Only the prompt's word.** The echo needs EVERY Latin value form in the quote to be an echo
  form: "an independent contractor or freelancer" or "single, never been married" also name the
  value by a same-language synonym, which the rubric makes inferred.
- **Breeds.** A breed of a pet the prompt names ("your golden retriever" where the prompt says
  "dog") is an echo, the rubric's breed elaboration (um-ss-petownership-12 L44, -14 L28);
  "puppy" / "kittens" stay the judge's call.
- **Lexicon.** hunk / fella (male), keysmith (locksmith), "loss of a spouse" (widowed), plural
  homemakers / housewives, and for each age band "age N" / "aged N" for every N inside it and
  every narrower "x-y" range inside it ("at age 60", "58-62" name 56-65; "age 66" and "55-60"
  do not).
- **Basis line.** `SUMMARY_BASIS` gains one selection rule: when several lines attribute the
  picked value to the user and ANY of them goes beyond the prompt, the basis is inferred and the
  quote is that line (all-layer continent-12/-15/-09 were echo on the same kind of digest that
  passed continent-13/-14/-11). The echo override still applies to the quote the judge gives.
- Not changed deterministically: a value attached to a named persona ("a 'President of Costa
  Rica' named Luna Felicio", um-sd-country-17 lite) stays the judge's call, because the
  rubric counts the persona of the infobox written for the user ("a fictional 'Average Guy'
  named John Smith", um-sd-gender-15), and the two shapes cannot be told apart by syntax.

```text

Your previous answer picked option {choice} ("{value}") with this evidence quote:
"{quote}"
That quote was rejected: {reason}. Answer again from the same readouts. If some readout statement names a candidate's value as a property of the user, pick it and quote that statement verbatim (from inside one token list or one bullet). Otherwise choose "{cannot}".
```

`UM_RETRY_REASON_VALUE`:

```text
it does not name the picked value (only a listed name, synonym, demonym, translation or gendered person word of the value counts)
```

`UM_RETRY_REASON_HEDGE`:

```text
it names the picked value only as one of several alternatives ("a, b, or c", "e.g. a, b, c"), which singles out none of them
```

### Round 4 (um-v3.4)

Camila's 2026-11-01 notes ("fix the too strict user modeling"; MC leakage standard), on the
round-2 re-audit (`results/reaudit_user_modeling.json`) and `notes/ROUND3_TODO.md`. Every
too-lenient guard is kept: names and fictional characters are never evidence, script is never
location, no topic leaps, echoes are not credited. Replayed deterministically on every cached
final-olens-rl600-x4 judged row (no new API calls); pinned in `tests/test_round4_um.py` in both
directions.

- **The echo needs the USER's own value.** `judge._own_value`: a prompt form joins the stem echo
  only where it states the user's own value. A person word needs a self-description frame
  (round 3, unchanged). Any other form counts anywhere in a system turn (the synthsys profile
  line), or in a first-person / user frame of another turn ("my divorce", "I work full-time",
  "we nurses", "the user left widowed"). "nurses work nights" or "my sister is a nurse" states
  nothing about the user. On this bank the only prompt form outside such a frame is
  um-sd-gender-04's "with the guys", so "You're a guy who loves the outdoors" stays inferred
  (about 13 final-olens samples). Every synthsys form is in the system turn, so those echoes are
  unchanged.
- **Spouse-death restatement.** `judge._RESTATED`: where the prompt itself records the spouse's
  death ("partner's life concluded", "spouse death recorded", "the partner passed away"), a
  spouse-death phrase in the quote ("losing a spouse", "the loss of a spouse", "surviving
  spouse") only restates it. That is the rubric's elaboration of a stated fact, so it is an
  echo (um-ss-maritalstatus-14 L44, -13 all-lite, -15 all-lite). Where the prompt says only
  "widowed", the phrase is a same-language synonym and stays the judge's call.
- **Hedge gate** (value gate condition 4): um-sd-occupation-03 prompt-only ("e.g., fisherman,
  sea captain, harbor pilot, …", which inflated the floor), -03 L40, and -08 L32 ("a professional
  sailor, angler, or yacht captain", unlocked by round 3's "angler"). Not a hedge (review of
  #213): um-sd-country-17 L56/L60 and -16 L52, um-ss-religiousaffiliation-10 L36 (shared
  modifier). On the cached final-olens readouts this frees 67 of the 268 gold-form sentences
  the first version gated. Review r3 of #213: the rule reads the quote's holding statement
  line, so the cut quote the hedge re-ask invites stays blocked; replayed with the bundle lines
  on every cached final-olens judged pick, this adds exactly two blocks, both runs the bare
  quote hid behind bold marks: um-sd-occupation-11 L36 ("a **Late-Night Key Holder**,
  **Emergency Locksmith**, or simply a person …") and -21 L36 ("a **cultural
  anthropologist**, **ethnologist**, or **scholar of human customs**").
- **Too-strict cells now pass** on the um-v3.3/v3.4 lexicon (the published numbers were judged
  under um-v3.2): um-sd-occupation-06 L24 and -08 L52/L56/L60 (angler); um-ss-agegroup-05
  L20/L48/L56 (age 60, 58-62); um-sd-gender-03 L56/L60 (Gym Bro, hunk) and -14 L20/L56/L60/all
  (dude); um-sd-occupation-10 L20/L48/L56/all and -14 L52 (locksmithing, keysmith);
  um-ss-employmentstatus-14 L56 (stay-at-home spouse).
- **Options** meet the MC leakage standard (see Options above): male / female / nonbinary Gender, Country lists of
  regional triples, a second Occupation neighbour.
- Not changed deterministically: um-sd-country-17 all-lite (a named "President of Costa Rica")
  stays the judge's call (see round 3). Neither does um-sd-gender-04 L60 ("these traditional
  'bro' camping trips", where 'bro' describes the trips), which now clears the gate and rests on
  the judge's attribution call.

### `UM_ATTRIBUTE_USER` (native)

```text
You are analyzing readouts of a language model's internal activations, taken while the model read the conversation below and before it replied. A readout is a free-text description or a ranked list of top vocabulary tokens. It may describe the conversation's topic, the task, the user, or unrelated material.

<user_turn>
{user_turn}
</user_turn>

<readout>
{readout}
</readout>

Which of these values of the user's {attr_label} do the readouts attribute to the user?

{options_block}

A candidate counts only when BOTH hold:
1. The readout NAMES the value. That means the value itself, a synonym or demonym ("Danish" for denmark, "stay-at-home mom" for homemaker, "independent contractor" for freelancer), a translation (韩国 for south korea), a word for the person that carries the gender (he, him, she, her, man, woman, husband, mother) for a gender, or a more specific value of the same attribute (a country inside a continent). Words merely associated with a value never count: foods, customs, activities, practices, objects, landscapes or professions' surroundings ("kimchi", "hygge", "meditation", "mindfulness", "the sea", "nets", "tides", "funerals", "locks").
2. The readout attributes the value to the USER, the person writing the messages. In readouts this is often "you", "I", "the user", or the persona whose biography or infobox is being written for them. A value attached to a topic, a dish, a story's character, a fictional person other than the user, an example or a third party does not count ("a Korean dish", "a story about a fisherman", "an actress in a romantic comedy", "a fictional president named Kim Kibum", "funeral planning advice").

In a list of top tokens, attribution cannot be read from syntax. There, a token that names a value counts only if the list is about a person or identity, not about the conversation's subject. For example, "actress | film | comedy | movie" is about films, not the user's gender. Tokens on one list may be read together to infer a meaning, but the meaning must still name the value for the user. Never combine a value word from one readout with a word about the user from another readout, another position or another layer. In a free-text readout, never combine them across two of its "- " bullets either (in a free-text sample, bullets are separated by ⁞). The value and its attribution to the user must be stated together in one list or in one bullet.

Never use the language or script a readout is written in as evidence. These readouts are often partly in Chinese for every user, so Chinese words or characters say nothing about the user's country, continent, ethnicity or language. Only a place or nationality that a readout explicitly attributes to the user counts.

A personal name is never evidence of gender, country, nationality or ethnicity, even when the readout gives it as the user's own name: placeholder names (John Doe, Jane Doe, John Smith) and real names (Robert, Marusya Kovalenko) alike.

The conversation is shown only so you can recognize when a readout merely echoes it: never pick a candidate because the conversation makes it plausible or because you could infer it yourself. If the readouts name several candidates of this attribute for the user and none clearly dominates, choose "{cannot}". If none is named for the user, choose "{cannot}".

{token_note}

Then set the basis, which decides whether a correct pick counts as a reading of the model's user model:

- "verbatim_echo": the readout names the value only by repeating the prompt's own word for it (or a form of that word) as already present in the prompt shown above (including a system prompt it repeats), or only by a broader category of a value the prompt states explicitly, or only by that word translated into another language; a same-language synonym or demonym of a stated value is not an echo. Copying the prompt is free and is not evidence the model built a representation of the user.
- "inferred_characterization": a readout names the user's value in a way that goes beyond the prompt's own words — naming the value where the prompt only implies it (for example "the user is Korean" where the prompt only mentions kimchi), or naming a stated value with a synonym or demonym.
- "absent": you chose "{cannot}".

Note the prompt text above is the full context the model saw. Some readouts may only repeat the prompt: set the basis from the readout line your pick rests on, and judge that line about THIS attribute only. The basis is "inferred_characterization" only if that line characterizes the user's value of this attribute beyond the prompt's own words: naming the value where the prompt only implies it, naming a stated value with a different word in the same language (a synonym or demonym), generalizing an implicit cue into a named value, or giving a more specific value of the same attribute than the prompt states (for example a country inside a continent the prompt names). Details about other attributes (age, gender, children, income, a name, mood) or elaborations of a stated fact that do not change its value (where exactly, how long ago, a pet's name or breed) leave a restated value "verbatim_echo". A line that names a stated value with a different word in the same language, i.e. a synonym or demonym (for example "Danish" where the prompt says Denmark, or "independent contractor" where it says freelancer), is "inferred_characterization". A line that repeats the prompt's own word for the value, a form of that word (for example "Buddhist" where the prompt says Buddhism), or that word translated into another language (for example 猫 where the prompt says cat), is "verbatim_echo", and so is a broader category of a value the prompt states explicitly (for example "Scandinavian" where the prompt says Denmark). When several lines attribute the picked value to the user and ANY one of them characterizes it beyond the prompt's own words, the basis is "inferred_characterization" and your pick rests on that line: quote it, not an echoing line. Quote from the line your basis rests on.

In evidence, quote, verbatim and from inside one token list or one bullet of one free-text readout (never across a ⁞), the span that names the value for the user (at most 200 characters; empty if you chose "{cannot}").
```

### `UM_ATTRIBUTE_USER_SUMMARY` (summary)

`{summary_note}` = `SUMMARY_NOTE` (or `SUMMARY_NOTE_ABSTRACTIVE` under
`summ_render=abstractive`), without the token rule (the template always carries it).

```text
You are analyzing readouts of a language model's internal activations, taken while the model read the conversation below and before it replied. The readout below is a digest of many readouts, across every read layer and token position. A readout is a free-text description or a ranked list of top vocabulary tokens. It may describe the conversation's topic, the task, the user, or unrelated material.

{summary_note}

<user_turn>
{user_turn}
</user_turn>

<readout>
{readout}
</readout>

Which of these values of the user's {attr_label} do the readouts attribute to the user?

{options_block}

A candidate counts only when BOTH hold:
1. The readout NAMES the value. That means the value itself, a synonym or demonym ("Danish" for denmark, "stay-at-home mom" for homemaker, "independent contractor" for freelancer), a translation (韩国 for south korea), a word for the person that carries the gender (he, him, she, her, man, woman, husband, mother) for a gender, or a more specific value of the same attribute (a country inside a continent). Words merely associated with a value never count: foods, customs, activities, practices, objects, landscapes or professions' surroundings ("kimchi", "hygge", "meditation", "mindfulness", "the sea", "nets", "tides", "funerals", "locks").
2. The readout attributes the value to the USER, the person writing the messages. In readouts this is often "you", "I", "the user", or the persona whose biography or infobox is being written for them. A value attached to a topic, a dish, a story's character, a fictional person other than the user, an example or a third party does not count ("a Korean dish", "a story about a fisherman", "an actress in a romantic comedy", "a fictional president named Kim Kibum", "funeral planning advice").

In a list of top tokens, attribution cannot be read from syntax. There, a token that names a value counts only if the list is about a person or identity, not about the conversation's subject. For example, "actress | film | comedy | movie" is about films, not the user's gender. Tokens on one list may be read together to infer a meaning, but the meaning must still name the value for the user. Never combine a value word from one readout with a word about the user from another readout, another position or another layer. In a free-text readout, never combine them across two of its "- " bullets either (in a free-text sample, bullets are separated by ⁞). The value and its attribution to the user must be stated together in one list or in one bullet.

Never use the language or script a readout is written in as evidence. These readouts are often partly in Chinese for every user, so Chinese words or characters say nothing about the user's country, continent, ethnicity or language. Only a place or nationality that a readout explicitly attributes to the user counts.

A personal name is never evidence of gender, country, nationality or ethnicity, even when the readout gives it as the user's own name: placeholder names (John Doe, Jane Doe, John Smith) and real names (Robert, Marusya Kovalenko) alike.

The conversation is shown only so you can recognize when a readout merely echoes it: never pick a candidate because the conversation makes it plausible or because you could infer it yourself. If the readouts name several candidates of this attribute for the user and none clearly dominates, choose "{cannot}". If none is named for the user, choose "{cannot}".

{token_note}

Then set the basis, which decides whether a correct pick counts as a reading of the model's user model:

- "verbatim_echo": the readout names the value only by repeating the prompt's own word for it (or a form of that word) as already present in the prompt shown above (including a system prompt it repeats), or only by a broader category of a value the prompt states explicitly, or only by that word translated into another language; a same-language synonym or demonym of a stated value is not an echo. Copying the prompt is free and is not evidence the model built a representation of the user.
- "inferred_characterization": a readout names the user's value in a way that goes beyond the prompt's own words — naming the value where the prompt only implies it (for example "the user is Korean" where the prompt only mentions kimchi), or naming a stated value with a synonym or demonym.
- "absent": you chose "{cannot}".

Note the prompt text above is the full context the model saw. Some readouts may only repeat the prompt: set the basis from the readout line your pick rests on, and judge that line about THIS attribute only. The basis is "inferred_characterization" only if that line characterizes the user's value of this attribute beyond the prompt's own words: naming the value where the prompt only implies it, naming a stated value with a different word in the same language (a synonym or demonym), generalizing an implicit cue into a named value, or giving a more specific value of the same attribute than the prompt states (for example a country inside a continent the prompt names). Details about other attributes (age, gender, children, income, a name, mood) or elaborations of a stated fact that do not change its value (where exactly, how long ago, a pet's name or breed) leave a restated value "verbatim_echo". A line that names a stated value with a different word in the same language, i.e. a synonym or demonym (for example "Danish" where the prompt says Denmark, or "independent contractor" where it says freelancer), is "inferred_characterization". A line that repeats the prompt's own word for the value, a form of that word (for example "Buddhist" where the prompt says Buddhism), or that word translated into another language (for example 猫 where the prompt says cat), is "verbatim_echo", and so is a broader category of a value the prompt states explicitly (for example "Scandinavian" where the prompt says Denmark). When several lines attribute the picked value to the user and ANY one of them characterizes it beyond the prompt's own words, the basis is "inferred_characterization" and your pick rests on that line: quote it, not an echoing line. Quote from the line your basis rests on.

In evidence, quote, verbatim and from inside one token list or one bullet of one free-text readout (never across a ⁞), the span that names the value for the user (at most 200 characters; empty if you chose "{cannot}").
```

### The shared rubric blocks

`UM_RULES` (both templates, verbatim):

```text
A candidate counts only when BOTH hold:
1. The readout NAMES the value. That means the value itself, a synonym or demonym ("Danish" for denmark, "stay-at-home mom" for homemaker, "independent contractor" for freelancer), a translation (韩国 for south korea), a word for the person that carries the gender (he, him, she, her, man, woman, husband, mother) for a gender, or a more specific value of the same attribute (a country inside a continent). Words merely associated with a value never count: foods, customs, activities, practices, objects, landscapes or professions' surroundings ("kimchi", "hygge", "meditation", "mindfulness", "the sea", "nets", "tides", "funerals", "locks").
2. The readout attributes the value to the USER, the person writing the messages. In readouts this is often "you", "I", "the user", or the persona whose biography or infobox is being written for them. A value attached to a topic, a dish, a story's character, a fictional person other than the user, an example or a third party does not count ("a Korean dish", "a story about a fisherman", "an actress in a romantic comedy", "a fictional president named Kim Kibum", "funeral planning advice").

In a list of top tokens, attribution cannot be read from syntax. There, a token that names a value counts only if the list is about a person or identity, not about the conversation's subject. For example, "actress | film | comedy | movie" is about films, not the user's gender. Tokens on one list may be read together to infer a meaning, but the meaning must still name the value for the user. Never combine a value word from one readout with a word about the user from another readout, another position or another layer. In a free-text readout, never combine them across two of its "- " bullets either (in a free-text sample, bullets are separated by ⁞). The value and its attribution to the user must be stated together in one list or in one bullet.

Never use the language or script a readout is written in as evidence. These readouts are often partly in Chinese for every user, so Chinese words or characters say nothing about the user's country, continent, ethnicity or language. Only a place or nationality that a readout explicitly attributes to the user counts.

A personal name is never evidence of gender, country, nationality or ethnicity, even when the readout gives it as the user's own name: placeholder names (John Doe, Jane Doe, John Smith) and real names (Robert, Marusya Kovalenko) alike.

The conversation is shown only so you can recognize when a readout merely echoes it: never pick a candidate because the conversation makes it plausible or because you could infer it yourself. If the readouts name several candidates of this attribute for the user and none clearly dominates, choose "{cannot}". If none is named for the user, choose "{cannot}".
```

`SCRIPT_RULE` (Camila: "Chinese-language text in the readout is credited as evidence that the
USER is in Asia. fix this"):

```text
Never use the language or script a readout is written in as evidence. These readouts are often partly in Chinese for every user, so Chinese words or characters say nothing about the user's country, continent, ethnicity or language. Only a place or nationality that a readout explicitly attributes to the user counts.
```

`SUMMARY_BASIS` (the one basis standard, both modes):

```text
Note the prompt text above is the full context the model saw. Some readouts may only repeat the prompt: set the basis from the readout line your pick rests on, and judge that line about THIS attribute only. The basis is "inferred_characterization" only if that line characterizes the user's value of this attribute beyond the prompt's own words: naming the value where the prompt only implies it, naming a stated value with a different word in the same language (a synonym or demonym), generalizing an implicit cue into a named value, or giving a more specific value of the same attribute than the prompt states (for example a country inside a continent the prompt names). Details about other attributes (age, gender, children, income, a name, mood) or elaborations of a stated fact that do not change its value (where exactly, how long ago, a pet's name or breed) leave a restated value "verbatim_echo". A line that names a stated value with a different word in the same language, i.e. a synonym or demonym (for example "Danish" where the prompt says Denmark, or "independent contractor" where it says freelancer), is "inferred_characterization". A line that repeats the prompt's own word for the value, a form of that word (for example "Buddhist" where the prompt says Buddhism), or that word translated into another language (for example 猫 where the prompt says cat), is "verbatim_echo", and so is a broader category of a value the prompt states explicitly (for example "Scandinavian" where the prompt says Denmark). When several lines attribute the picked value to the user and ANY one of them characterizes it beyond the prompt's own words, the basis is "inferred_characterization" and your pick rests on that line: quote it, not an echoing line. Quote from the line your basis rests on.
```

`TOKEN_NOTE_UM` (`mc.token_note(SPEC.flat_types, multi_select=False)`):

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of countries, nationalities, continents, religions or occupations, or of any other words or names of one kind, singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it.
```

`SUMMARY_NOTE`:

```text
The readout below is a digest of the readouts across every read layer and position: for each read layer, a note-taker who did not see the passage picked the most prominent readout samples, then samples carrying content seen in only one or a few samples, and the layers' picks are merged, the most-stated first. Each line is marked with how many readout samples state its content ([N samples], or [N samples, M layers] when it was seen at M read layers): counted per claim, so a sample that only lists the word among others of its kind, or only restates the question, is not counted; compare these counts when weighing lines against each other. Each line is one real readout sample (a free-text generation, or one ranked list of top tokens). Treat each line as a separate sample: pieces on different lines never combine. Any quote must be copied from inside one line, without the bracketed marker.
```

`SUMMARY_NOTE_ABSTRACTIVE`:

```text
The readout below is a digest of the readouts across every read layer and position, written layer by layer by a note-taker who did not see the passage, most prominent first, then content seen in only one or a few samples. Each line is one statement in the note-taker's words, how many samples state it (counted per claim), and a verbatim evidence span from one real readout sample. The statements are not evidence: judge what the evidence spans show, treat each line as a separate sample (pieces on different lines never combine), and copy any quote from inside one evidence span.
```

`UM_TASK_NOTE` (`EvalSpec.task_note`: what the digest is told; no value, no option):

```text
the model reads a chat message from a user, before it replies to them; readouts may describe who the user is (where they live, their job, family, pets, beliefs, gender, age) or just the message's topic — record any description of the user even if it appears once.
```

Escape wording (`mc.CANNOT`):

```text
cannot tell from the readout
```

### Output schema

`choice` is the 1-based option number (`len(options) + 1` = the escape).

```json
{
 "name": "um_attribute",
 "strict": true,
 "schema": {
  "type": "object",
  "additionalProperties": false,
  "required": [
   "choice",
   "basis",
   "evidence",
   "rationale"
  ],
  "properties": {
   "choice": {
    "type": "integer"
   },
   "basis": {
    "type": "string",
    "enum": [
     "verbatim_echo",
     "inferred_characterization",
     "absent"
    ]
   },
   "evidence": {
    "type": "string"
   },
   "rationale": {
    "type": "string"
   }
  }
 }
}
```

## Prompt-only floor

The shared `po-opus-v1` protocol (one Opus 5.5 readout per item from the whole render, one prose
cell at the final token, layer 44), judged by this family's own `run` (digest, um-v3.4 judge,
gate, options), frozen in `evals/baselines/prompt_only_summary.json` under
`reads.strip_reads(prompt_version)` at the run phase (gpu R6). The lucky-guessing
floors (`evals/baselines/lucky_guessing.json`) were re-measured on the um-v3.4 option lists and are
stamped `um-v3.4` (see Options, MC leakage standard). The lucky-guessing prompt carries only the
options (plus, for `described`, the family sentence and three solved items), never the judge
rubric, the gate lexicon, the re-ask or the echo rule. The ATI subset is re-judged under
um-v3.4 at the run phase; until then the ATI entry is the um-v2 subset (stale `bank_sha`, never
reused).

## Token (J-lens) readouts

Natively each token cell is ONE ranked list (`render_bag`), judged directly (plan 0032 §2.3: no
interpretation step). A token that names a value counts only if the list is about a person or
identity (`"actress | film | comedy | movie"` is about films, and "actress" is never a gender
form); tokens of one list may be read together, never across lists, positions or layers.
Expect token lenses to lose selfdescribe passes that rested on topic clusters: intended.

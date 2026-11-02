# 0035 — WorkspaceBench fix campaign: directed_modulation (basic)

Status: implemented in this PR (camila/wsb-bp-directed_modulation), on top of plan 0032 (infra).
Campaign source of truth: `/workspace/root/wsb-bp/plans/{directed_modulation,SHARED_API,_fable_decisions}.md`;
this file copies the family spec verbatim (below the line) plus what the implementation decided
where the spec left room. Camila's sentences: `notes/feedback.md` § "directed modulation (basic)"
(lines 43-47) and the DM half of § "Mcdm" line 93.

## What was built

- **C1 blind judge.** `render_user` has no `prompt` parameter; `USER` has no
  `<instruction_to_model>` block. `test_judge_is_blind` renders every bank item natively (prose
  and tokens) and in summary mode: no instruction, no carrier, and the gold concept appears
  exactly once (its option line). README carries the headline caveat (the stimulus names the
  concept; prompt-only saturated; out of ATI).
- **C2 distractors.** `evals/directed_modulation/distractor_groups.json` (frozen; every bank and
  adapted-bank concept, a missing concept is a hard error). `option_sets` keeps the pre-0035
  seeded draw and replaces each pick from the gold's group in place by a seeded redraw from the
  unrelated rest, so the 81 items that had no related distractor keep their exact option lists;
  19 lists changed (all 10 pair-sibling cases plus 9 secret/preference ones). Golden regenerated.
- **C3 single mentions.** `DIGEST_TASK_NOTE` is Camila's wording (copying a dictated sentence
  while told to think of a concept/noun/object; may not be the most prominent; may appear in one
  sample or inside a restated instruction; record it as its own entry), registered as
  `EvalSpec.task_note` and passed from the spec; `FAMILY_DEFAULTS["directed_modulation"] =
  {"summ_rare": "25"}`; every `digest.*` call passes `family=`.
- **C4 tool names.** Every remaining tool word is gone (`SYSTEM` "an interpretability readout",
  `READOUT_BUNDLE_NOTE` deleted; native token rows get `mc.token_note()` via
  `prompts.token_note()`, equal to `digest.token_note_of("directed_modulation")`).
- **C5 any context + close relatives.** Headline `expressed` (`score.hit`: gold picked with a
  verified quote, any basis); `CLOSE_RELATIVE` clause in all three credit blocks (secret is no
  longer exact-word only); the several-options rule is relative to the options shown;
  `extras.summary.<sub>.n_relative_only_hits` (rows) and `n_items_relative_only` (items whose pass
  rests only on such rows). Stamps: `JUDGE_PROMPT_VERSION = "dm-2026-10-30c"`,
  `PROMPT_VERSION = "dm-2026-10-30c+expressed"`.
- **G1/G5.** `EvalSpec(min_full_positions=6, full_contiguous=True, flat_types=(),
  multi_select=False)`; the plan row already carried `lite_positions=final_token` (infra). The
  evidence gate is `digest.quote_ok` natively (the row's own token line, or its one prose
  sample) and in summary mode (`col.evidence[item]`).
- **Floors.** Lucky guessing re-frozen at `dm-2026-10-30c+expressed` (Opus 5.5, 5 draws): blind
  0.138 -> 0.148, described 0.178 -> 0.168, uniform 0.190 -> 0.190.

## Judge test on cached v1 readouts (no new readouts; summary mode, `dm-2026-10-30c+expressed`)

Readouts: `/workspace/root/wsb-ati-runs/readouts/{s3d,jlens,mlnla2k}/directed_modulation.jsonl`
(no sidecar: `reads_checked=no_sidecar`, report-only). Opus 5.5 digest + judge, 100 items each.

| arm | expressed (headline) | content_bound | distractor | relative-only items | white_bear delta |
|---|---|---|---|---|---|
| s3d-rl600 (wsb-ati-runs file) | 0.48 [0.38, 0.58] | 0.33 | 0.00 | 3 | 0.83 |
| jlens | 0.12 [0.06, 0.18] | 0.07 | 0.01 | 5 | 0.17 |
| mlnla-rl2-2000 | 0.30 [0.21, 0.39] | 0.21 | 0.00 | 4 | 0.49 |

Same-readouts before/after (s3d-rl600 at `wsbench-pub/outputs/readouts/s3d-rl600`, the file the
old runs used): native present 46/99 (old, instruction-seeing judge), summary v3 expressed 41/100
-> **47/100 [0.38, 0.58]** now (distractor 0.00, 10 relative-only items). The six single-mention
items summary v3 lost although native passed: grater, barnacle ("Minutes recorded without using
barnacles") and quilling ("hint of quillwork") pass in both new digests; colander ("filtering a
bowl of pasta") passes in one of two digests; whittling fails in both; orienteering passes on
"hint of a compass ... maze" (a lenient call, for the G12 audit). The three different "s3d"
DM readout files on disk differ in content (the colander / quilling mentions exist only in the
`wsbench-pub` one).

## Implementation decisions where the spec left room (deviations)

1. **Credit-rule and domain examples use non-bank concepts.** The spec's examples ("collarbone"
   for clavicle, "paper folding" for origami) and the inherited ones (philately, spelunking)
   name bank concepts, which would put the gold in the judge message twice and fail the spec's
   own `test_judge_is_blind` (count == 1). They became "kneecap" for patella, "paper folding"
   for kirigami, "tuxedo" for bow tie, numismatics, birdwatching, barometer, granite, cathedral.
   Camila's origami -> paper folding ruling is still exactly what the clause credits.
2. **Distractor redraw in place** (above) instead of a fresh draw over the reduced pool, which
   would have reshuffled 71 lists for no reason.
3. **Native token rows render from `digest.native_lines`**, so the judge sees exactly the line
   `quote_ok` verifies (`norm_token` removed). Native prose rows verify against that one sample
   (its bundle rendering with bullet marks, and flattened).
4. **Pre-existing test assertions changed beyond the spec's list**, each forced by a spec change:
   `test_prompt_rendering_by_subfamily_and_polarity` and `test_tokens_kind_end_to_end_and_voided`
   asserted the deleted `READOUT_BUNDLE_NOTE` text ("BAG OF TOP-K"; now `mc.TOKEN_NOTE`) and
   the old basis-note words; `test_judge_calls_keyed_by_judge_prompt_version` pins the new stamps;
   `tests/test_text_inversion.py::test_directed_modulation_adapter_is_the_headline_rule` (the ATI /
   prompt-only item adapter must equal the family headline, now `expressed`: an incidental gold
   pick counts).
5. **Headline mirrors outside the family** follow `expressed`: `baselines/text_inversion.py`
   item adapter and `scripts/summary_mode_compare.py` `_dm_hit`.
6. **Close-relative clause tightened after the judge test** (`dm-2026-10-30` -> `-30c`). On the
   cached v1 readouts the first wording credited the gold's grouped-out sibling or category word
   (mlnla dm-pair-20-neg rook <- "without mentioning the bishop"; s3d dm-pair-16-neg baobab <-
   "avoided mentioning trees"; s3d dm-pref-07 topiary <- "trees"; jlens dm-pair-03-pos brownie <-
   "chocolate | dessert"), because the C2 groups leave the gold as the only option of its kind. The
   clause now adds "A different member of the same kind is not a close relative ... and neither is
   the category word", and every "broader category alone" bullet adds "even when only one
   candidate belongs to that category". All four cases are cannot-tell at `-30c`. Lucky entries
   re-stamped to `-30c` (same option lists; a guesser sees only the lists).
7. **Late critique fixes:** (1) `plan_sha` excludes layers and
   `test_all_layer_producer_file_is_judged` already landed in 0032; (2)-(4) are other
   workstreams; (5) the judge-spend estimate is recomputed after the run-phase smoke.

---

# Spec: directed_modulation (basic) — fix campaign workstream

Code of record: `/root/wsb-bp-base` @ `cd6b0fa`. Every `file:line` below is from that tree unless
it names another path. Read-only scoping; nothing here has been run against an LLM.
Round 1 (2026-10-30): aligned to `SHARED_API.md`, `infra.md` and `_fable_decisions.md`. Shared
names are used verbatim; no shared machinery is re-implemented here.
Round 2 (2026-10-30): applies `_critique_r1.md` items 4 (flat-list rule is a judge decision
relative to the options shown; `mc.token_note(flat_types)`; lone-option family test), 5 (named
restatements are now a shared `DIGEST_SYSTEM` rule, infra §2.8.2; the DM fallback paragraph is
deleted), 7 (verdict-level leniency audit via gpu G12 / R4b) and 8 (per-arm runs only on the
required arms `s3d-rl600`, `jlens`, `mlnla-rl2-2000`; anything else is "cached v1 readouts, judge
test only").
Round 3 (2026-10-30): aligned to SHARED_API r3 and `_critique_r2.md`. Items that touch DM:
3 (`mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`; DM sets
`multi_select=False`), 5 (coverage map for `site/manifest.json`, §7), 6 (audit fixes run in gpu
R4c, before R6/R8 and the site build), 12 (`digest.BULLET_MARK`; DM is non-relational, so no
`statement_lines` and no `n_unverified_bullet`), 13 (DM's lite site is the pre-registered
`final_token` default, never chosen by pass rate), plus the r3 macro and prompt-only-timing rows.

---

## 1. Current state

**Bank.** `evals/directed_modulation/items.json`: 100 items: `pair` 70 (35 concepts × `think` /
`dont_think` twins sharing `pair_id`), `secret` 15, `preference` 15 (both `suppress`). Each item has
`prompt` (the user-turn instruction, which **names the concept**, e.g. "Think about the body part
clavicle while you write. Now write exactly this sentence: ..."), `assistant` (= `carrier`, the
sentence the model copies, teacher-forced), `concept`, `subfamily`, `polarity`. The 35 pair concepts
are 17 two-member categories plus `baobab`, `parsnip` and `monsoon`. The category is parsed from the
prompt: body part clavicle/femur, chess piece bishop/rook, fruit citron/kumquat, dessert
brownie/eclair, emotion envy/shame, animal mule/donkey, gemstone amethyst/onyx, shape
ellipse/trapezoid, insect hornet/weevil, utensil colander/grater, instrument accordion/banjo, sea
creature stingray/barnacle, planet Neptune/Saturn, metal iridium/palladium, boat canoe/catamaran,
footwear loafer/moccasin.

**Read sites.** `readplan.py:365-378`: render `chat_dm` (Qwen chat template, instruction as the user
turn, carrier teacher-forced as the assistant turn; `produce/render.py:64-65`). The positions rule is
`{"kind": "suffix_text", "text": it["assistant"]}`, i.e. every token of the carrier
(`readplan.py:153-160`, `:205-222`). That is 7-9 positions per item. Layers are `GRID` =
`range(20, 61, 4)` (`readplan.py:16`), 11 layers. No lite read mode exists. Under D2 the current
rule already equals `reads=full`.

**Layers judged.** `judge.py:153-156`: `args.layers` if given, else the readout file's own layer set.
Every (item, layer) must be present unless `allow_missing=True`. Arbitrary layer lists already work
(D3 is satisfied today).

**Judge (native, opt-out).** One MC call per (item, layer, pos, sample) row (`judge.py:80-96`,
`:160-190`). Six options: gold + 4 distractors + escape "cannot tell from the readout"
(`prompts.py:147`, `:217-220`). Distractors are drawn in `judge.py:59-77`: **any other concept of
the same subfamily**, seeded per item, drawn over the whole bank. There is no exclusion of
same-category or related concepts. On the current bank, 10 pair items show their category sibling
as a distractor: clavicle→femur, mule↔donkey, amethyst→onyx (×2), Neptune→Saturn,
trapezoid→ellipse, barnacle→stingray, palladium→iridium (×2). Related pairs also appear in the
other subfamilies: topiary→bonsai, geocaching↔orienteering, pergola→gazebo.

**What the judge sees.** `prompts.py:20-80` `USER`. The opening paragraph names a specific tool:
"the output of an **"oracle lens"**" (`prompts.py:21`). Every other tool word in the family prompts:
`:13` ("an interpretability readout"), `:24`, `:154`, `:159` ("the lens read the activation"),
`:31-33` (`<lens_output>` tag), `:39`, `:41`, `:47`, `:49`, `:71`, `:79` ("the lens output"),
`:101` ("whether the lens reads the exact held word"), `:140` (`READOUT_BUNDLE_NOTE`, "The lens
output below"), `:151`, `:157` ("oracle lens"). An `<instruction_to_model>{prompt}` block
**shows the judge the instruction naming the concept** (`prompts.py:27-29`). The prompt then says
"Exactly one candidate is the concept from this item's instruction" (`:39-42`) and "The instruction
is shown only so you can recognize when the readout is merely restating it" (`:46-48`). Credit
rules depend on the subfamily (`prompts.py:82-124`): pair takes any unique form (synonyms that
uniquely identify it, no category words); secret takes the exact word only ("Do NOT credit
synonyms, sibling terms, related objects"); preference reads broadly (standard renames and
synonyms). None of the three credits a close relative or near equivalent. The basis note depends on polarity (`:126-137`). Basis
is one of `content_bound | instruction_narration | incidental | absent`. Token readouts get
`READOUT_BUNDLE_NOTE` (`:139-142`). The same `USER` text serves every reader: O-lens, NLA, J-lens,
logit lens and prompt-only (`render_user`, `prompts.py:223-248`; only `tokens` toggles the bag
note).

**Loader.** `judge.py:154` calls `readouts.load_readouts` directly; `judge.py:155-157` checks
(item, layer) presence with `missing_cells` / `require_cells`.

**Evidence gate.** `judge.py:109-147`: a positive pick must quote a verbatim span of the readout
(family-local `_norm_quote`; summary mode checks spans of `digest.gate_texts`).
Native token bags must be quoted as one contiguous `" | "` span (`:136-138`), so non-adjacent
whole-token evidence voids valid picks (audit: dm-pair-23-pos L52 p42 "shame", wrongly voided).

**Headline.** `score.py:47-49` `present_hit` = gold picked AND basis ∈ {content_bound,
instruction_narration} (plan 0028); `score.py:162`. `incidental` gold picks do not count.
`expressed` (gold picked, any basis) is only a channel (`score.py:72`). `white_bear` uses
`content_bound` (`score.py:95-113`).

**Summary mode (the default, D1).** `judge.py:225-343`. All of an item's cells (every layer ×
carrier position × sample) go to one `digest.collapse` call (`:249-257`), then one judge call on the
digest with `USER_SUMMARY` (`prompts.py:156-163`, which again says "oracle lens" at `:157`). The
summarizer gets all readouts (D1 is already met: bundle about 13k tokens, under the 150k cap, not
truncated). Gaps:
- **The task note never reaches the summarizer.** `DIGEST_TASK_NOTE` (`prompts.py:165-168`) is only
  used when `summ_variant=task`. The default is `blind` (`digest.py:33-34`), and `FAMILY_DEFAULTS`
  (`digest.py:184-206`) has no `directed_modulation` entry.
- **The digest system prompt works against this family.** `digest.py:62-66` tells the summarizer to
  give restatements of the input "at most one item". `digest.py:70-72` tells it to skip
  "restatements of the input" in the rare list. In this family, the concept often appears only
  inside such a restatement ("Minutes recorded without using barnacles").
- `digest.py:58` "Do not combine separate readouts" and `SUMMARY_NOTE_TOKENS` (`digest.py:121-125`,
  "a quote from such a line must be exactly one token") forbid combining a token list's top-10.
  That conflicts with D6.
- `judge.py:246, 247, 259, 338, 340` call `digest.prompt_version / summary_note / pinned / config`
  **without `family=`**. `collapse` (`digest.py:1024`) does pass it. Once a DM family default
  exists, the result stamp would say `-blind-` while the digest actually ran `-task-` (a latent
  bug).

**Floors.** Lucky guessing frozen in `evals/baselines/lucky_guessing.json:126` (blind 0.138 mean
under the current instrument; README cites 0.162). Prompt-only is EXCLUDED
(`baselines/prompt_only.py:20-25`), measured at 1.00 under plan 0028 with stock Qwen. The family is
not in ATI (`evals/baselines/anti_text_inversion.json:32`).

**Cached numbers (s3d-rl600 O-lens, Opus judge).** Native: present 0.46, expressed 0.465,
content_bound 0.41 (`/workspace/root/wsb-summ-out/d3/d3b-s3d-all-native`). Summary v3: expressed
0.41, content_bound 0.32 (`/workspace/root/wsb-summ4-out/d3b-s3d-all-summary-v3`). J-lens native:
0.13 (`/workspace/root/ext/wsb-runs/macro/jlens`).

---


## 2. Change list

Shared machinery used as-is (owner: infra PR, which lands first; this PR rebases onto it):
`reads.load`, `ReadSpec.lite_positions` / `lite_layers`, `reads.stamp`,
`EvalSpec.min_full_positions` / `full_contiguous` / `task_note`, `digest.collapse(task_note=)`,
`digest.prompt_version`, `digest.quote_ok` / `digest.native_lines`, `mc.CANNOT`,
`mc.options_with_cannot`, `mc.READOUT_PHRASE`, `mc.token_note(flat_types, *, multi_select)`, `EvalSpec.multi_select`,
`EvalSpec.flat_types`, `mc.form_in`, the sidecar sampling declaration, the shared named-restatement
rule in `DIGEST_SYSTEM` (infra §2.8.2), `baselines.prompt_only_opus` (`po-opus-v1`),
`scripts/audit_verdicts.py` (gpu G12). This spec adds no shared
setting, no `FAMILY_DEFAULTS` key outside the allowed set, and no digest stamp literal.

### C1. "this is an issue: 'The judge sees the instruction that names the concept, so this is a content-vs-narration classifier, not blind identification …'"

Make the judge **blind**: it never sees the item's prompt.
- `prompts.py`: delete the `<instruction_to_model>` block (`:27-29`) and the instruction-referencing
  sentences (`:39-42`, `:46-48`). The new question line is: "Exactly one candidate is the concept
  the model was told about; the others are concepts from other items of this eval. You do not see
  the instruction: judge only from the readout's own content."
- Rewrite `BASIS_POS` / `BASIS_NEG` (`:126-137`) to state polarity only ("The model was told to
  think about the concept" / "told not to think about it, or to keep it hidden"). Basis is kept as a
  diagnostic, judged from the readout's own text (narration like "I must not reveal X" is visible
  in the readout itself).
- `render_user` (`prompts.py:223-248`) loses the `prompt` parameter. Its callers
  `judge.py:168-175` and `:266-277` stop passing `by_id[...]["prompt"]`.
- README: replace the "judge sees the instruction" text (`README.md:21-31`) with "The judge is
  blind: it sees the readout and the options, never the instruction." Keep one honest caveat. The
  *stimulus* names the concept, so a reader of the prompt text (prompt-only) scores about 1.0. The
  family measures whether the readout carries the held concept at positions where the model writes
  something unrelated, and it stays out of ATI.
- Tests:
  - New `test_judge_is_blind`: for every bank item, the rendered native and summary user messages
    contain neither `item["prompt"]` nor the carrier, and the concept appears only on its option
    line (count == 1).
  - Sanctioned update to `test_prompt_rendering_by_subfamily_and_polarity`
    (`tests/test_directed_modulation.py:107`): drop `prompt=`. No assertion changes.

### C2. "we should similarly to the above use multiple choice with distractors - although these distractors should not be synonyms/instances of the target concept, since it's plausible that a "clavicle" concept makes the model also think about "neck" or "shoulders". they should be targets from other dm questions"

MC with escape already exists. Change the **draw**, and render the escape through the shared helper:
- New frozen data file `evals/directed_modulation/distractor_groups.json`. It maps every concept to
  a relatedness group, in two parts:
  - **pairs:** the prompt category (the 17 two-member categories above; baobab, parsnip and monsoon
    are singletons).
  - **secret / preference:** hand-curated. Secret: {gazebo, pergola, alcove, turret}
    (architectural structures), {fjord, isthmus} (landforms), {obelisk, sundial},
    {periwinkle, bramble} (plants); the rest are singletons. Preference: {bonsai, topiary, ikebana}
    (plant arts), {origami, quilling} (paper crafts), {geocaching, orienteering} (navigation
    outdoors); the rest are singletons.
  - The groups double as the close-relative guard for C5 (critique 20): every bank concept that
    C5's close-relative clause could credit for the gold is in the gold's group, so it is never
    shown as a distractor.
- `judge.py:59-77` `option_sets`: pool = concepts of other items in the same subfamily **minus every
  concept in the gold's group**. The same seeded draw and order are kept. Distractors are always
  other DM items' targets ("targets from other dm questions"); "neck"/"shoulders"-type neighbours
  are never options because no DM item has them as a target.
  - The pool stays within the subfamily so the options stay type-matched: all hobbies for a
    preference item, so the word "hobby" singles nothing out; all words for a secret item.
  - Pool sizes after exclusion: pair 32-33, secret ≥ 11, preference ≥ 12, all ≥ 4.
  - A concept missing from the groups file is a hard error. All 11 adapted banks
    (`adapted/*/directed_modulation.json`) use only base-bank concepts (checked), so the file
    covers them.
- Escape: delete the family `CANNOT` constant (`prompts.py:147`) and the hand-appended escape in
  `option_lines` (`prompts.py:68-71`); the option list is `mc.options_with_cannot(options)`
  (escape text `mc.CANNOT`, last, never shuffled). The text is unchanged ("cannot tell from the
  readout"), so the 6-option layout and `classify`'s escape index are unchanged.
- Instrument bump (C5 stamp). Regenerate the golden as `tests/golden/directed_modulation_options.json`
  (a **sanctioned** golden update) and check the new draw by hand. Lucky-guessing re-freeze (§3).
- Tests:
  - New `test_distractors_exclude_related_group`: no shown distractor shares the gold's group, and
    every distractor is another item's concept.
  - Shared `test_every_mc_judge_ends_with_cannot` (infra) covers the escape.
  - Sanctioned update to `test_bank_and_option_sets` (`tests/test_directed_modulation.py:86`): new
    golden only.

### C3. "make sure that single mentions of the concept still get detected by the summarizer, e.g. you can tell the sumamrizer what type of task this is: the model is tasked with copying down a sentence while thinking of a certain concept/noun/object. the concept may not be the most prominent thing the model is thinking about"

- **Task context is the global default** (infra §2.8.2: `digest.DEFAULT_VARIANT = "task"`), so DM
  sets no `summ_variant`. The family registers its note as `EvalSpec.task_note` and passes it to
  `digest.collapse(..., task_note=spec.task_note)` (`judge.py:249-257`). `DIGEST_TASK_NOTE`
  (`prompts.py:165-168`) is that string (Camila's wording; no concept or instruction text):
  "the model is copying down a dictated sentence while it has been told to think of a certain
  concept, noun or object (or not to think of it, or to keep it secret); that concept may not be
  the most prominent thing in the readouts, may appear in only one sample, and may appear only
  inside a restatement of an instruction (for example "I must not mention X"); such a mention
  still bears on this task and must be recorded as its own entry".
  - There is no `summ_restated` key (retired). The restated-mention clause in the family task
    note is backed by the shared rule below; `DIGEST_TASK_LINE` already tells the summarizer to
    record a task-relevant mention "even one that appears in a single sample".
- `FAMILY_DEFAULTS["directed_modulation"] = {"summ_rare": "25"}` (an allowed key) so a single
  mention has room in the rare tier next to the carrier-copy content.
- Fix `judge.py:246, 247, 259, 338, 340` to pass `family="directed_modulation"`; the stamp is
  `digest.prompt_version(PROMPT_VERSION, args, "directed_modulation")` (never a literal), plus
  `+reads-lite` from `reads.stamp` under lite.
- The summarizer gets every readout of the item (every layer × carrier position × sample) under
  the global `DEFAULT_TOKEN_CAP` with hierarchical overflow (infra §2.2); the DM bundle (~13k
  tokens) is one call.
- **Named restatements are kept by the shared prompt (infra §2.8.2, critique r1 item 5; owned
  and built by infra, not here).** `DIGEST_SYSTEM:62-64` / `:70-72` no longer cap or skip a
  restatement that names a specific object, person, place, name or term: it is recorded with
  that term as its key (in items or rare); only the generic wording of the input is capped at one
  item. So "Minutes recorded without using barnacles" yields a `barnacles` key. This rides
  infra's `digest-v4` bump, which the stamp from `digest.prompt_version` picks up. The round-1
  "fallback" (raise it to infra later) is deleted: it is done now.
- **Flat lists are recorded, not dropped (infra §2.7.1, critique r1 item 4a).** The summarizer
  records a same-type token list ("hornet | wasp | bee | ant") as a list with its words kept, so a
  single mention of the concept inside a list of its own category survives to the judge, where
  singling out is decided against the options shown (G5).
- Tests:
  - New `test_dm_task_note_reaches_summarizer`: `digest.render_system` for the DM settings with
    `task_note=FAMILIES["directed_modulation"].task_note` contains the note, including the
    restatement clause; the scripted `collapse` call receives it.
  - Shared `test_every_summary_family_has_task_note_without_gold` (infra) checks the note names no
    gold or option.
  - Shared `test_digest.py::test_digest_keeps_named_restatement` (infra) covers the restatement
    rule; family `test_dm_restated_concept_reaches_judge`: a fake-LLM digest of a bundle whose only
    gold mention is "Minutes recorded without using barnacles" (dm-pair-30-neg) carries a line with
    key `barnacles` into the judge message for that item.
  - Sanctioned update to `tests/test_summary_mode_dm.py:84` `test_dm_one_call_per_item_and_gate`:
    the stamp assertion becomes `== reads.stamp(digest.prompt_version(PROMPT_VERSION, args,
    "directed_modulation"), "full")` (no literal), and `prompt_version` is computed with
    `family=`. The one-call-per-item and gate assertions are unchanged.

### C4. "also make sure that the system prompt for the summarizer/judge (and more generally in other eval families as well) doesn't specifically mention the name of a particular tool, like here it seems like we mention an "oracle lens" but if i understand correctly this same prompt is used for things like nlas and jlens too."

Answer: yes, the same prompt serves every method (§4). Changes:
- `prompts.py:21`, `:151`, `:157` (`USER`, `SUMMARY_INTRO_OLD`, `SUMMARY_INTRO`) open with
  `mc.READOUT_PHRASE` ("readouts of a language model's internal activations"). This is infra
  §2.8.1's edit; this PR does not duplicate it.
- This PR removes the remaining tool words (§1 inventory): `:13` "an interpretability readout" →
  "a readout"; `:24`, `:154`, `:159` "the lens read the activation(s)" → "the readouts were taken
  from the activation(s)"; tag `<lens_output>` → `<readout>`; "the lens output" → "the readout"
  throughout `USER`; `:101` "whether the lens reads the exact held word" → rewritten by C5.
- `READOUT_BUNDLE_NOTE` (`:139-142`, "The lens output below …") is deleted; native token readouts
  get `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` (G5).
- `digest.py`'s shared wording is infra's (§2.8.1).
- Test: the shared `tests/test_prompt_tool_names.py::test_no_tool_names_in_prompts` (infra; its
  regex includes `\blens\b` and covers DM `PROMPTS` and `task_note`). No family-local tool-name
  test. `test_readme_carries_every_prompt` keeps the README in sync.

### C5. "i disagree with some of the things you think are too lenient, e.g. origami -> paper folding should count, and origami was literally mentioned verbatim. in directed modulation, if the concept is mentioned in any context it should count"

Plus Camila's MCDM line, which is about this family too (critique 20): "generally for directed
modulation we can accept synonyms and close relatives as evidence of thinking about the concept".
- Headline becomes **`expressed`** (gold picked, with a verified quote, under any basis:
  content_bound, instruction_narration or incidental). Same name and rule as MCDM M4.
- `score.py:47-49`: `present_hit` is replaced by `hit = pick == "gold"` and used at `:162`
  (headline) and `:123-125` (pass_at_1). The `present` and `content_bound` channels stay in
  `extras.summary` as diagnostics. `white_bear` stays on content_bound.
- Prompt text: add to `USER`: "The candidate counts in ANY context: engaged as content, named while
  restating an instruction ("I must not reveal X"), or mentioned in passing." The "names several
  candidates without singling one out → cannot tell" rule (`prompts.py:49-50`) is kept but
  reworded relative to the options shown (bullet below). That rule, plus the distractor channel,
  guards against enumerations.
- **Close relatives (critique 20), aligned with MCDM M7's clause.** Add to `CREDIT_PAIR` and
  `CREDIT_PREFERENCE` the bullet: "a synonym, or a close relative or near equivalent of it
  ("collarbone" for clavicle, "paper folding" for origami, "tuxedo" for bow tie). A word that fits
  several candidates equally does not single one out." `CREDIT_SECRET` (`:99-106`) is rewritten
  to the same rule ("generally for directed modulation" covers every subfamily): its "Credit only
  the exact word … Do NOT credit synonyms, sibling terms, related objects" text is replaced by the
  pair rule plus this clause; the "broader category alone" exclusion stays in all three. Safe
  because C2's groups keep every relative out of the options, so the clause can only turn a
  cannot-tell into a gold pick, never into a distractor pick.
- **"Names several candidates without singling one out" is relative to the options shown**
  (shared flat-list rule, infra §2.7.2, critique r1 item 4b): the `prompts.py:49-50` sentence
  becomes "A readout that names two or more of the options without singling one out → cannot
  tell. A readout that names only one of the options counts for it, even inside a list of other
  words of the same kind." DM sets `EvalSpec.flat_types = ()` (its options are concepts, not a
  competitor run such as numbers), so "tiger | lion | leopard | cheetah" for gold *lion* (tiger
  not an option) is a gold pick. This is exactly "if the concept is mentioned in any context it
  should count".
- `score.py:204-208` headline string; `CHANCE_LABEL` (`:14-17`) drops "prompt-only"; README
  Scoring.
- New diagnostic `extras.n_relative_only_hits`: gold picks whose quote contains no listed form of
  the gold (`mc.form_in(quote, forms)`, forms = the concept and its plural). Reported per
  subfamily beside the headline, so the site shows how much of the headline the clause adds.
- Stamps: `JUDGE_PROMPT_VERSION = "dm-2026-10-30"` (new prompts, new call cache, includes the
  close-relative clause); `PROMPT_VERSION = JUDGE_PROMPT_VERSION + "+expressed"`
  (`prompts.py:6-8`). Prompts are code and the bank is unchanged.
- Tests:
  - New `test_headline_counts_any_basis`: gold + `incidental` passes; gold + `instruction_narration`
    passes; `distractor` and voided picks fail.
  - New `test_credit_rules_accept_close_relatives`: all three `credit_rules(sub)` strings contain
    the close-relative clause and the broader-category exclusion; `CREDIT_SECRET` no longer says
    "Do NOT credit synonyms".
  - New `test_relative_only_hits_column`: a scripted gold pick quoting "collarbone" counts in
    `n_relative_only_hits`; one quoting "clavicles" does not.
  - New `test_dm_lone_option_in_same_category_list_is_gold` (critique r1 item 4c; family
    counterpart of infra's `test_mc.py::test_lone_option_in_same_category_list_is_singled_out`):
    a scripted judge on the token line "hornet | wasp | bee | ant" (gold hornet; weevil is
    excluded from the options by the C2 group) returns gold and the pick scores `hit`, native and
    summary; the rendered judge message (native and summary) contains exactly
    `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` (= `mc.token_note()` for
    DM) and not the deleted `DIGEST_SYSTEM` "singles out none of them" sentence. Companion: a line holding two shown options
    ("hornet | kumquat") → `cannot tell` is accepted and scores no hit.
  - `test_summary_channels_and_white_bear` (`:203`) asserts channels only; no change.

### General items applied to this family

- **G1 lite reads (D2).** `readplan.py:365-378`: the DM plan row gets
  `lite_positions={"kind": "final_token"}`, `lite_layers=None`. The `chat_dm` render ends at the
  carrier (`suffix_text` matches "at the end of the render", `readplan.py:82`), so `final_token`
  is the carrier's closing ".". The family does no filtering: `reads.load` applies `reads.select`
  for both the native and the summary paths, and the stamp is `reads.stamp(pv, mode)`.
  `EvalSpec(min_full_positions=6, full_contiguous=True)`: the shortest carrier has 6 words, so ≥ 6
  tokens, and the full span is one contiguous run ending at the max position.
  - **The site is pre-registered, not chosen from data** (critique r2 item 13). `final_token`
    is the shared default lite rule. DM is not one of the families run through the r3 lite-site
    procedure (association, conjunctive, role_bound), and no pass rate is used to pick it. The
    cached s3d native counts are reported as an expectation only: gold picked at the final token
    for 19 of 46 items, at the 4th-from-last token for 18 (J-lens: 2 of 13). Lite ⊆ full, so one
    GPU read serves both.
  - Tests: shared `test_every_plan_row_has_lite_positions`, `test_lite_is_subset_of_full`,
    `test_min_full_positions_per_family`; family `test_dm_lite_judges_final_carrier_token`
    (a 3-position fixture through `reads.load` under `reads=lite` yields only the max-pos cell,
    and the stamp ends `+reads-lite`).
- **Loader.** `judge.py:154` `load_readouts(...)` becomes `cells, rep = reads.load(args,
  "directed_modulation", ids=list(by_id))`. The (item, layer) presence check
  (`missing_cells` / `require_cells`, `judge.py:155-157`) stays (it is not a position
  completeness check). Shared test `test_no_family_calls_load_readouts_directly`.
- **G2 layers (D3).** Nothing family-specific: `layers=<csv>|all|each` works through
  `readplan.plan` / `reads.load`. Covered by the shared `test_layers_arbitrary` and
  `test_layers_variant_is_complete` (parametrized over `registry.FAMILIES`).
- **G3 summary default / all readouts (D1).** Already the default; every cell of the item is
  passed to `collapse` (no pre-selection). Covered by C3 and the shared
  `test_every_registered_family_is_summary_or_native_only`.
- **G4 cannot tell (D4).** `mc.options_with_cannot` (C2).
- **G5 token combining (D6, Q4).** The rule is the shared Q4 rule; this family only uses it.
  - Both the native and the summary judge prompt render
    `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` (SPEC = DM's `EvalSpec`),
    in place of `READOUT_BUNDLE_NOTE` natively and of the bare `SUMMARY_NOTE_TOKENS` in summary
    mode. DM sets `flat_types=()` and `multi_select=False` (one gold per item; MCDM is the only
    `multi_select=True` family), so the text is byte-identical to `mc.TOKEN_NOTE`, and "two
    shown options on one line single out none of them" stays in force for DM. The family
    writes no token-combining or flat-list wording of its own.
  - Evidence gate: `decode` (`judge.py:109-147`) drops `_norm_quote` and the `gate_texts` span
    check and verifies with `digest.quote_ok(evidence, lines)`, where `lines =
    digest.native_lines([cell])` natively and `col.evidence[item_id]` in summary mode. This fixes
    the "shame" case (non-adjacent tokens of one list now verify).
  - Bullet boundaries (critique r2 item 12, infra §2.7.10). Under `digest-v4` a multi-bullet
    s3d sample is shown to the summarizer and judge as `- a ⁞ b ⁞ c` (`digest.BULLET_MARK`).
    DM's content is one concept, not a relation, so DM verifies with `quote_ok(quote, lines)`
    only (`fold_quote` maps `⁞` to a space). It does not call `digest.statement_lines` and does
    not report `extras.n_unverified_bullet` (those are for the relational families). DM writes
    no bullet wording of its own.
  - Test: family `test_dm_gate_uses_quote_ok` (the dm-pair-23-pos L52 p42 fixture verifies; a
    quote combining tokens from two different lists is voided; a quote "pasta ⁞ colander"
    copied across the bullet mark of one s3d sample verifies); shared
    `test_token_evidence_noncontiguous_same_line_verifies`, `test_token_note_rendered_from_spec`,
    `test_token_note_multi_select_variant`, `test_digest_line_shows_bullet_boundaries`.
- **G6 prompt-only (D8).** Opus prompt-only via the one protocol `po-opus-v1`
  (`baselines.prompt_only_opus`, judged by `wsbench run all=True readouts_root=<dir>/readouts`, no
  `layers=`/`reads=`), so it gets the same blind judge, task note and digest. infra §2.11.9
  reduces `prompt_only.EXCLUDED` to `{"jlens_concept_pr"}`, which un-excludes DM; the frozen entry
  carries `saturated: true` and the site labels it ("the instruction names the concept"). This PR
  adds nothing to `baselines/prompt_only.py`. Timing (SHARED_API r3): the floor is measured at
  gpu R6, after R4c closes, and matched on `strip_reads(PROMPT_VERSION)`; if a DM fix changes
  the PV after R6, DM has no floor until R6 re-runs for it.
- **Macro.** DM stays in the macro: its `FamilyResult.metric` stays `"pass_rate"`
  (`score.py:168`, in `results.MACRO_METRICS`); "expressed" is the headline's label and rule,
  not a new metric name. `EvalSpec.not_in_macro` stays `""`.
- **G7 sampling (D7, Q1).** Declared by the producer in the sidecar; the family does nothing.
  s3d-rl600 = `prose1` (one multi-bullet generation = one sample per activation); `*-x4` arms =
  `bullet4`; J-lens / logit lens = `tokens10`; NLA = `prose1`. DM content is a single concept
  (not relational), so the prose1 whole-generation licence applies and `digest.statement_lines`
  is not used.
- **G8 leniency audit (critique r1 item 7; serves C5 "i disagree with some of the things you
  think are too lenient").** DM is audited by the ONE shared protocol, gpu G12 / R4b
  (`scripts/audit_verdicts.py sample|table`): ≥ 30 stratified verdicts (pass/fail × prose
  s3d-rl600 or ML-NLA / token J-lens) labelled by a fresh-context auditor given Camila's DM
  sentences, including "origami -> paper folding should count", "if the concept is mentioned in
  any context it should count" and "we can accept synonyms and close relatives". Under that rule
  a verdict is `too_lenient` only if the quote neither names the gold nor gives a synonym or
  close relative of it (e.g. only a broader category word, or a word that fits several options),
  or the quote does not verify; `too_strict` if a
  verified mention (any context, synonym or close relative) of the gold was scored cannot-tell.
  No family-local audit protocol. If DM is flagged (`n_too_lenient + n_too_strict ≥ 3`), the
  fix is a new DM PR with a new `JUDGE_PROMPT_VERSION`, run through gpu R4c (re-run R4 for DM:
  all 12 s3d configs, `jlens` and `mlnla-rl2-2000` full + lite; then R4b again; ≤ 2 rounds)
  **before R6 / R8 and the site build** (critique r2 item 6). The bank and read sites do not
  change, so `plan_sha` is unchanged and no R2 is needed. If DM is still flagged after round 2,
  its verdicts are listed under "New errors found" on the site.

---

## 3. Data needs

- **Bank items: no edits.** `items.json` is untouched. No new items and no new bank version
  (`EvalSpec.bank` unchanged). The only new frozen data is
  `evals/directed_modulation/distractor_groups.json` (C2), covered by the instrument bump. DM is
  not in ATI, so there is no `bank_sha` to keep or re-gate.
- **No Qwen gating** (no new or changed prompts given to the model).
- **Readouts: nothing to regenerate.** The prompts and read sites are unchanged. `reads=full` is
  the existing carrier span; `reads=lite` is its final token, cut from the same files by
  `reads.select`. Sampling follows Q1 from the sidecar (s3d-rl600 `prose1`, J-lens `tokens10`);
  existing files without a sidecar get one from the gpu workstream's merge/convert step.
- **LLM re-judging (a later phase).** Every arm is re-judged at the new instrument; old caches do
  not hit (new `JUDGE_PROMPT_VERSION`, new digest fingerprint). Runs, inside gpu.md's 12-config
  run where listed there:
  - s3d-rl600 summary (default) and native;
  - s3d-rl600 with all 11 layers and `layers=each` (each single layer: the summarizer sees only
    that layer's readouts);
  - the required gpu G14 arms on the full plan (critique r1 item 8): `jlens` (`tokens10`) and
    `mlnla-rl2-2000` (`prose1`), all-layer config, `reads=full` and `reads=lite`, summary;
  - `reads=lite` for s3d-rl600;
  - the Opus prompt-only arm (`po-opus-v1`).
  - Logit lens and any `*-x4` arm: **"cached v1 readouts, judge test only"** (gpu §3.3); this
    spec funds no production for them, and the site labels their rows so.
- **Floors.** Re-freeze lucky guessing (blind / described / uniform) at the new instrument with the
  new option lists (`wsbench.baselines.lucky_guessing`). The stale entry
  (`evals/baselines/lucky_guessing.json:126`) is dropped automatically by the instrument check.
  Prompt-only floor in `evals/baselines/prompt_only_summary.json`, `saturated: true`.

---

## 4. Answers

- **"if i understand correctly this same prompt is used for things like nlas and jlens too":**
  Yes. `render_user` (`prompts.py:223-248`) builds one `USER` / `USER_SUMMARY` for every reader. The
  only difference is that token readers get a token note (`READOUT_BUNDLE_NOTE` natively today,
  `SUMMARY_NOTE_TOKENS` in summary mode; `judge.py:173`, `:259`). So "oracle lens" was being shown
  to the judge for J-lens, NLA, logit-lens and prompt-only readouts as well. C4 removes it.
- **Is the instruction leak fixed?** On the judge side, yes (C1: blind judge). The *stimulus* still
  names the concept, so any reader of the prompt text names it: prompt-only stays about 1.0
  (shown as saturated) and the family stays out of ATI. The meaningful bars are:
  - the lucky-guessing floor (about 0.14-0.16 today);
  - the distractor false-alarm rate (0.02 native s3d);
  - the white-bear contrast.
- **Does origami → paper folding count?** Yes under both the old and the new rule. CREDIT_PREFERENCE
  already credits "an unambiguous description of the activity", and C5 adds close relatives
  explicitly. The cached native verdict (dm-pref-03 L20 p49) picked origami with an exact quote.
  Under C5 its basis no longer matters, so the audit's "too lenient" label is withdrawn: it is a
  correct pass.
- **Why were single mentions lost in summary mode?** In s3d summary-v3 (blind digest), 6 items that
  pass natively (expressed) fail. In all 6 the gold is absent from the digest text:
  - dm-pair-09-pos colander ("filtering a bowl of pasta", 1 native hit);
  - dm-pair-28-pos grater;
  - dm-pair-30-neg barnacle ("Minutes recorded without using barnacles", narration, 1 hit);
  - dm-pref-08 orienteering (1 hit);
  - dm-pref-13 quilling (narration, 1 hit);
  - dm-pref-14 whittling (雕刻完成, 1 hit).

  Every one is a single-cell mention. Two are inside restatements that `digest.py:62-72` tells the
  summarizer to cap or skip. C3's task note plus infra §2.8.2's named-restatement rule (which
  replaces that cap) target exactly these.

---

## 5. Evidence plan (for the final website)

| Item | Artefact |
|---|---|
| C1 blind | One rendered judge message for dm-pair-00-pos, before (with `<instruction_to_model>` naming clavicle) and after (no instruction). Rerun the s3d native and summary: report the agreement rate with the old verdicts and list every flipped item with its readout. Per-arm headline for s3d-rl600, `jlens`, `mlnla-rl2-2000` (new runs); logit lens labelled "cached v1 readouts, judge test only". |
| C2 distractors | Option tables before/after for the 10 sibling cases (e.g. dm-pair-00-neg: femur removed) and for dm-pref-07, -08, -12 and dm-secret-14; escape last in every row. New lucky floor next to the old one. |
| C3 single mentions | Re-digest the 6 lost items listed in §4 with the task note and the shared `digest-v4` restatement rule: before = gold absent from the digest and FAIL; after = gold line present and PASS. Report the full s3d summary-vs-native gap before (41 vs 46 expressed) and after. Any item still lost is listed verbatim with its digest on the site (no deferred fix). |
| C4 tool names | `test_no_tool_names_in_prompts` output for DM `prompts.py`: before = the §1 inventory, after 0. Rendered summary prompt before ('an "oracle lens"') and after. |
| C5 any context | Re-score the cached native verdicts (0 calls): headline present 0.46 → expressed 0.465. Show dm-pref-03 (origami, PASS) and dm-pair-30-neg (barnacle narration, PASS). Distractor rate beside the headline. |
| C5 close relatives | Judged headline per subfamily (pair / secret / preference) before and after the clause, with `n_relative_only_hits` and the distractor rate (must not rise), and every relative-only hit listed with its quote. |
| G1 lite | s3d lite vs full headline (cached-native estimate: 19 vs 46 items with a gold pick), then the judged numbers. |
| G2 layers | s3d all-11 vs each single layer (summary), from `layers=each`. |
| G5 token gate | Re-decode the cached J-lens dm-pair-23-pos L52 p42 with `quote_ok` (0 calls): before voided, after PASS. |
| G5 flat list | On the new `jlens` all-layer run: every gold pick whose verified quote is one option inside a same-category token list (e.g. "hornet \| wasp \| bee"), listed with its line; plus the count of lines holding ≥ 2 shown options that were scored cannot-tell. Shown beside infra E19's "tiger \| lion \| leopard" case. |
| C3 restatements | The digest of dm-pair-30-neg and dm-pref-13 (narration items) under `digest-v4`: the named restatement appears as its own key (before: capped / skipped). |
| G8 audit | DM row of the gpu G12 audit table (n, n_too_lenient, n_too_strict, n_ambiguous, every non-`ok` case verbatim). A row with ≥ 3 flagged goes through gpu R4c (fix PR, re-run, re-audit, ≤ 2 rounds) before R6/R8 and the site build; the before → after table per round is the artefact, and leftovers go to "New errors found". |
| G6 prompt-only | Opus prompt-only (`po-opus-v1`) through the same judge, shown as saturated (expected about 1.0). |

---

## 6. Risks / conflicts

- **Shared files this PR touches (family entries only):**
  - `src/wsbench/digest.py`: `FAMILY_DEFAULTS["directed_modulation"] = {"summ_rare": "25"}` (an
    allowed key; `test_single_global_token_cap` checks it).
  - `src/wsbench/readplan.py`: the DM row's `lite_positions` / `lite_layers`.
  - `src/wsbench/registry.py`: DM `EvalSpec` fields `task_note`, `min_full_positions=6`,
    `full_contiguous=True`, `flat_types=()`, `multi_select=False` (both explicit, the defaults).
  - `evals/baselines/lucky_guessing.json`: re-freeze.
  - `evals/baselines/README.md`: DM rows at lines 42, 206 and 275-281.
  - `tests/test_summary_mode_dm.py`, `tests/test_lucky_guessing.py` (follows `option_sets`
    automatically).
- **Family-local files:** `src/wsbench/evals/directed_modulation/{prompts,judge,score}.py`,
  `evals/directed_modulation/README.md`, new `evals/directed_modulation/distractor_groups.json`,
  `tests/test_directed_modulation.py`, `tests/golden/directed_modulation_options.json`.
- **Coordination:**
  - Restatements: one shared `DIGEST_SYSTEM` rule (infra §2.8.2) serves DM, MCDM and
    model-specific DM; none of them sets `summ_restated` or `summ_variant`.
  - Flat lists: DM and MCDM both use `mc.token_note(flat_types)` and each add a lone-option test.
  - Headline name `expressed` and the close-relative clause match MCDM M4 / M7.
  - infra §2.8.1 edits DM `prompts.py:21,151,157`; this PR edits the rest of that file. Rebase
    onto infra first.
- **Decisions taken (token combining under Q4; listed in site section 4 "Decisions taken"):**
  - "insect | horn" → hornet (dm-pair-08-pos L60 p40): PASS. Two tokens of one list jointly name
    it, which Q4 allows.
  - "ban | instrument | guitar" → banjo (dm-pair-29-pos L60 p39): FAIL (a fragment plus the
    category word plus a sibling; nothing in the list names banjo).

  The C2 groups remove weevil from hornet's options. A bare category word alone still fails
  ("broader category alone" stays in every credit rule).
- **Close relatives raise leniency.** A relative cannot produce a distractor pick (C2), but a
  sibling-category readout ("donkey" under a mule item) now credits the gold.
  `n_relative_only_hits` makes that share visible; the G8 / gpu G12 audit labels each such hit,
  and if the share is large it is put to Camila on the site.
- **Secret subfamily changes rule.** Its exact-word-only rule (from the source repo) is replaced by
  the close-relative rule per "generally for directed modulation". The per-subfamily before/after
  row shows the effect.
- **Blind basis.** Without the instruction, the judge decides content vs narration from the readout
  alone. Only diagnostics (content_bound, white_bear) depend on it, so the headline is unaffected.
- **Comparability.** Every DM number on the site changes instrument. Old and new must not be drawn
  on one axis without labels.
- **Pre-existing tests I would modify** (each sanctioned here; review the assertion diffs):
  - `test_bank_and_option_sets` (golden only);
  - `test_prompt_rendering_by_subfamily_and_polarity` (drop `prompt=`; no assertion change);
  - `test_dm_one_call_per_item_and_gate` (stamp computed with `digest.prompt_version(...,
    "directed_modulation")` and `reads.stamp`, no literal).

  No other pre-existing assertion should change.

---

## 7. Coverage map (input to `site/manifest.json`, gpu G11)

`site/build.py` reads this table. `sentence_id` = `<section>:<line in notes/feedback.md>`. A row
is `done` only when its tests are green at the bench SHA and its artefact exists; otherwise
`pending`. Rows marked "measured" are measurements, not fixes.

| sentence_id | Camila sentence (short) | change | tests | evidence (§5 row) | status kind |
|---|---|---|---|---|---|
| `directed modulation (basic):43` | judge sees the instruction naming the concept | C1 | `test_judge_is_blind`, `test_prompt_rendering_by_subfamily_and_polarity` | C1 blind | done |
| `directed modulation (basic):44` | MC with distractors that are other DM targets, never synonyms / instances | C2 (+ G4) | `test_distractors_exclude_related_group`, `test_bank_and_option_sets`, `test_every_mc_judge_ends_with_cannot` | C2 distractors | done |
| `directed modulation (basic):45` | single mentions must survive the summarizer; tell it the task | C3 | `test_dm_task_note_reaches_summarizer`, `test_dm_restated_concept_reaches_judge`, `test_every_summary_family_has_task_note_without_gold`, `test_digest_keeps_named_restatement`, `test_dm_one_call_per_item_and_gate` | C3 single mentions, C3 restatements | done + measured |
| `directed modulation (basic):46` | no tool name in summarizer / judge prompts; same prompt for NLA, J-lens | C4 (answer §4) | `test_no_tool_names_in_prompts`, `test_readme_carries_every_prompt` | C4 tool names | done |
| `directed modulation (basic):47` | origami → paper folding counts; any context counts; not too lenient | C5, G8 | `test_headline_counts_any_basis`, `test_credit_rules_accept_close_relatives`, `test_dm_lone_option_in_same_category_list_is_gold`, `test_relative_only_hits_column` | C5 any context, C5 close relatives, G8 audit | done + measured |
| `Mcdm:93` (DM half; MCDM half is mcdm.md's) | "for directed modulation we can accept synonyms and close relatives" | C5 close-relative clause | `test_credit_rules_accept_close_relatives`, `test_relative_only_hits_column` | C5 close relatives | done + measured |
| general D1-D8 rows | summary default, layers, lite, cannot, token rule, prompt-only, sampling | G1-G7 | shared parametrized tests (SHARED_API "Tests every family is held to") + `test_dm_lite_judges_final_carrier_token`, `test_dm_gate_uses_quote_ok` | G1 lite, G2 layers, G5 token gate, G5 flat list, G6 prompt-only | done + measured |

# Baselines

Measured floors for the judged families. A family's pass rate means nothing on its own: the
judge picks from option lists, and a strong model handed only those lists is not a uniform
guesser (golds tend to be more specific and more answer-shaped than distractors drawn from
other items). The floors here are what a real arm has to clear.

## Lucky guessing (`lucky_guessing.json`)

A model is shown NOTHING but a family's option lists (no question, no passage, no readout) and
asked to guess. The lists come from the judges' own builders, so option text and gold
positions are byte-identical to what the judge sees, and so is the order wherever the judge
fixes one; the trailing
"cannot tell" escape is dropped (a guesser with no readout has an honest reason to abstain that
a judge does not, and the gold is never the escape). Ported from the source repo's
`lucky_guessing_baseline.py`.

Variants, five draws per item with the repo judge, `claude-opus-5-5` since plan 0023 (the
Anthropic route sends no temperature; the entries record the requested 1.0). The entries drawn
are the 2026-10-11 Opus re-run; the six multi-token entries are Gemini-era MC diagnostics,
never drawn beside their regex scores, and `floors()` draws a variant only when its guesser is
the family's judge (the model-free uniform variant always):

- **blind**: the lists and nothing else.
- **described**: one honest sentence saying what the family tests (the option domain, never the
  judge's question) plus three OTHER items of the family with their gold marked: the
  informed-guesser ceiling.
- **topic** (round 4): `described` plus each item's TOPIC line (the kind of answer its unseen
  question asks for, `meta["topic"]` from the family's builder; `lucky_guessing.TOPIC_FAMILIES`:
  association, basic_readout, multihop, poetry, directed_modulation), the guesser of Camila r2's
  MC leakage standard (below).
- **uniform**: seeded uniform picks over the same lists, no model; lands on the analytic floor
  (`mean over items of prod(1/n)`) and catches option sets that are not what the floor assumes.
- **topic** (round 4, Camila r2 MC leakage standard: "a few options that would confuse the
  judge even if the judge can tell what the topic is"). A topic file
  `evals/baselines/topics/<family>.json` has one of two forms (`topic_form`). Per-list labels
  (an `items` map, `scripts/build_r4_mc_banks.py`; the bridge / multilingual / wrong_bridge
  families): the described guesser plus each list's TOPIC (what its hidden question is about,
  never the question, the answer or an option), the examples shown with their topics too.
  One line per item (a `topics` map; role_bound_association, conjunctive_association): the
  described sentence plus ONE frozen topic line for the item
  (`evals/baselines/topics/<family>.json`, `scripts/baselines/make_topics.py`, Opus 5.5) and the
  lists; no solved example. A topic line names what a reader knows that is no answer part:
  role_bound_association `topic-v2` = the story's setting and kind of situation, written from
  the story with no role, relationship, feeling or action word (lint: no role term, story
  blocklist word or gold action form; re-asked on a hit); conjunctive_association `topic-v4`
  (review of #202 round 4) = the same kind of story line under a stricter prompt that also
  shows the item's options (every option must stay equally consistent with the line), linted
  against the cluster's credit words and screened by a second call that sees the line and the
  options only; topic-v3 (what every option shares, from the list alone) is retired: it told the
  guesser nothing the options-only guesser lacked. Families with a topic file
  only; the entry records `topics` (the file version).

**MC leakage standard** (Camila r2, 2026-11-01): for every MC family the options-only (`blind`)
and the described / topic guessers must stay within 5 points of uniform (moral_rationale: at
chance, <= +2), measured with Opus 5.5 in >= 5 draws under the family's own pass rule, and each
list must hold >= 2 same-topic confusers. A family whose options appear in the prompt the model
reads is reported instead (changing them would invalidate the readouts). A family with a
multi-draw rule records it beside the per-draw mean (`family_rule`; conjunctive: a majority of 3
draws and no twin pick) with uniform chance under the SAME rule (`family_chance`), and the
standard reads the one against the other (`lucky_guessing.standard`; review of #202 round 4: the
per-draw mean against the per-draw uniform scored the guesser as if deterministic but chance per
draw). A family whose headline is a different rule measures it with guessers that answer in that
rule's form: conjunctive's sharded +cand3 configs with `variant=blind_cands,described_cands,
topic_cands,uniform_cands` (one pick + up to 3 candidates a draw, 3 draws per shard for
`HEADLINE_SHARDS` = all 8 / lite 2 shards; `rule_<config>` against the exact `chance_<config>`).
A family whose headline unit is a direction pair (`PAIR_RULE_FAMILIES`: role_bound_association
`pair-v1`, review of #202 round 5) records `family_rule` = the mean over complete pairs of
`p_ab * p_ba` (each item's share of right draws) and `family_chance` = the product of the two
items' uniform floors. The standard reads the one against the other, as it does for a
multi-draw rule.

Pass rule per draw = the family's own: every list right (role-bound's three questions,
a multilingual family's concept and language). `mean` is the pass rate
averaged over draws with its std, `majority` the per-item plurality vote. Families and lists:

| family | lists per item | options | notes |
|---|---|---|---|
| conjunctive_association | 1 | 22-44 | bank v4 (round 4, Fable on #202: lists widened to 22 non-twin options, two authoring rounds): `comp-v5`, under the family rule: blind 0.06, described 0.06, topic (topic-v4) 0.10 vs chance 0.002 (line 0.052), all **FAIL**; +cand3 all-layer 0.17 / 0.30 / 0.21 vs 0.157 (line 0.207; blind passes), lite 0.15 / 0.26 / 0.22 vs 0.049 (line 0.099; all fail). Does NOT meet the standard; the gap and why are in the family README |
| role_bound_association | 3 | 5 | agent / action / patient; a people list may repeat a label (the judge's list does); `oa-v3.1` floors per item blind 0.116, described 0.148, topic 0.226 vs uniform 0.008 (fail); the headline is direction pairs (`pair-v1`, review of #202 round 5), so the standard reads `family_rule` = per pair `p_ab * p_ba`: 0.012 / 0.006 / 0.000 vs 0.00006 (line 0.050), **pass** |
| relational_multihop | 1 | 18 | rel-v3 (#209 round 6): one composed-relation list (12 chains over the two hops + three decoys, 5 singles, 1 near form); rel-v2's 13-option list failed the leakage bar |
| moral_rationale | 1 or 2 | 5 | committed items one list, deliberative items one per side |
| user_modeling | 1 | 2-10 | um-v3.4 (MC leakage standard, Camila r2): Gender shows male / female / nonbinary, Country lists are three regional triples plus one, two Occupation neighbours; re-frozen 2026-11-01: blind 0.190 -> 0.200, described 0.210 -> 0.184 vs chance 0.134 -> 0.155 (both within chance + 5 pts; the residual is the bank's dog / cat and full-time golds, see `evals/user_modeling/README.md`) |
| directed_modulation | 1 | 5 | plan 0035: distractors are other items' concepts outside the gold's relatedness group (19 lists redrawn); re-frozen 2026-10-30 at `dm-2026-10-31+expressed`: blind 0.138 -> 0.148, described 0.178 -> 0.168, uniform 0.190 (unchanged); topic 0.758 is a diagnostic, not a floor (round 5, `NOT_A_FLOOR`: its topic is the instruction's category, which names the answer); valid floors blind / described, both within chance + 5 |
| typo_mt | 1 | 5 | the correction |
| multihop_mt_v2 | 1-2 | 5 | one list per bridge; bank v2 options are other questions' bridges / targets of the same kind (plan 0041) |
| multilingual_mt, multilingual_multihop, multilingual_typo, basic_readout_mt | 1-2 | 5 | concept/correction/readout plus the language list for L2 items |
| basic_readout | 1 | 5 | the blind MC judge's frozen options (plan 0053); bank v5 (round 4, below): implicit items still guessed far above chance (described 0.63, topic 0.60 vs entity / processing 0.21 / 0.14, 0.14 / 0.20); the opt-in round-5 bank v6 (4 equally common confusers per implicit list, Qwen >= 8/10 gate) does not fix it: implicit blind 0.581, described / topic 0.648 vs chance 0.113 (association's opt-in v4 likewise fails, blind 0.443 vs 0.086); both family READMEs |
| multi_concept_directed_modulation | 1 (multi-select, one to three picks) | 6 (the judge's 7th line, cannot tell, is not offered to a guesser) | pass = the picks include EVERY dictated concept and no binding-partner option (plan 0025; before it, the first pick); bank v2 (plan 0034): 114 scored items, relation items' candidates are six relations; `any_hit` = some pick is gold, `exact` = the picks equal the dictated set, `mean_picks` and `by_n_concepts` beside them; the seeded-uniform variant draws three distinct picks, analytic floor C(n-k-p, 3-k)/C(n, 3) (p partner options); controls dropped |

### MC leakage standard (round 4, Camila r2, 2026-11-01)

Camila: "making sure that an options only baseline cannot guess beyond chance, and by ensuring
that there are a few options that would confuse the judge even if the judge can tell what the
topic is". Binding: for every MC family, an options-only guesser and a described/topic guesser
(Opus 5.5, 5 draws, the family's own single-pick rule) score <= uniform chance + 5 points, and
every list holds >= 2 same-topic confusers.

- **Guessers.** `blind` (options only), `described` (the family's task type + 3 solved
  examples), and the new `topic` variant (`described` plus each item's TOPIC, the kind of answer
  its unseen question asks for; builder `meta["topic"]`, `lucky_guessing.TOPIC_FAMILIES`):
  basic_readout's TASK TYPE line (the judge is shown it), association's bank-v3 `mc.topic`,
  multihop's `bridge_type`, poetry's line-one end word ("a rhyme for 'gray'"), directed_modulation's
  instruction category ("a body part"). The bar is read on ALL three guessers (`blind`,
  `described`, `topic`) for every MC family (`lucky_guessing.LEAKAGE_GUESSERS`,
  `leakage_failures`): Camila's confusers must hold "even if the judge can tell what the topic
  is", and a judge infers the topic from the readouts whether or not it is shown a topic line.
  `topic` is measured and frozen for every topic family and enters `lucky_guessing.bar` (the
  report's floor is the highest guesser). **Exception (round 5, Camila r3):
  directed_modulation's `topic` is NOT a floor** (`lucky_guessing.NOT_A_FLOOR`): its topic line
  is the category the instruction names right before the concept ("Think about the body part
  clavicle" -> "a body part"), i.e. part of the instruction "think of X", which is the answer.
  Its judge and summarizer never see the instruction (verified on every item,
  `tests/test_dm_blind_judge.py`), so a guesser handed it measures the stimulus, not what the
  lists leak. It stays measured and frozen as a diagnostic (0.758) but has no row in
  `standard`, no entry in `leakage_failures` and never sets `bar` (the report shows "topic 0.758
  (not a floor)"). DM's valid floors are options-only (`blind`) 0.148 and `described` 0.168,
  chance 0.200, both within chance + 5 (line 0.250): DM meets the standard on its valid floors.
  multi_concept_directed_modulation has no topic guesser for the same reason.
- **Prompt check first.** No option of basic_readout / multihop / association / poetry appears in
  the text the model reads (readplan render; two association v2 distractors, `smoke` in bf-fire and
  `almuerzo` in es-siesta, were scene words and are gone in v3). directed_modulation's GOLD is in
  its prompt by design (the instruction names the concept), so its options were NOT changed.
- **Rebuild** (`scripts/mc_leakage_r4.py`): Opus 5.5 proposes same-topic wrong answers as typical as
  the gold (never the scene / a readout), a topic-member check keeps >= 2 same-topic confusers
  (`mc.topic_confusers` per item), lints drop gold forms, prompt words / numbers / forms, shared
  forms between options, the surface answer and first-hop cue words (multihop), Qwen's own rhyme
  commits and proper names (poetry); an Opus validity screen (the gold wins 5/5 with the question
  shown) where a question has one right answer, and multihop's same-surface-answer check (no
  other eurozone country for "the euro", ...). Lists are then searched against the shipped
  guessers (2 draws per variant per candidate list); the final numbers below are a FRESH
  measurement of the frozen banks (`wsbench baseline ... draws=5`), not the search's.
- **New banks** (never edited in place): `evals/{basic_readout,multihop,association,poetry}/
  items_v3.json` (header `mc_leakage`; per item `mc.distractors_v2` keeps the v2 list), registered
  with new judge stamps (`br-mc-2026-11-01-v3`, `bank-mc-2026-11-01-v3`, `assoc-mc-2026-11-01-v3`,
  `poetry-mc-2026-11-01-v3`; prompts and gates unchanged), so their prompt-only floors and ATI
  entries are stale until re-judged / re-gated in the run phase (the readouts and the panel
  answers are unchanged: prompts and plan_sha are v2's).
- **Observed confusers are never dropped** (PR #214 reviews; `KEEP_V2_RULE` / `FORCE_RULE` /
  `OBSERVED_RULE` in `scripts/mc_leakage_r4.py`): the gates' rival rules (multihop's split,
  poetry's dominance veto, basic_readout's bare-pick rule) see only the shown options, so a new
  list that drops a distractor a cached judge picked, or one the readouts name as a rival,
  silently loosens the gate. multihop and association v3 were built under it; basic_readout and
  poetry v3 were not (poetry: 62 of 147 v2 distractor picks gone, 32 veto cells loosened), so
  both moved to **bank v4** = v3 + every observed v2 confuser (`observe`; stamps
  `br-mc-2026-11-01-v4`, `poetry-mc-2026-11-01-v4`). Poetry's veto replay over the cached
  final-olens readouts: v2 -> v4 loosens 0 of 1200 cells. basic_readout's v4 evidence bar (a
  digest stating the option >= 2x AND at least as often as the gold) missed the rivals behind
  v2's cannot-tell verdicts, so it moved on to **bank v5** (review r6; stamp
  `br-mc-2026-11-01-v5b`): also every v2 option the digest of a v2 non-pass cell names, with
  the gold slots balanced per subfamily (review r7, `mc.gold_position`). Replay: all 259 v2
  non-pass cells re-judged under v5, 19 fail -> pass, 0 attributable to a dropped option
  (evals/basic_readout/README.md). Poetry's v4 bar (a veto or tie) missed the once-written
  rivals behind v2's cannot-tells, so it moved on to **bank v5** too (review r7; stamp
  `poetry-mc-2026-11-01-v5`): also every v2 option the digest of a v2 non-pass cell ends a line
  with. Veto replay v2 -> v5 loosens 0 of 1200 cells; all 1031 v2 non-pass cells re-judged under
  v5, 18 fail -> pass, 0 attributable (evals/poetry/README.md). The rule outranks the floor:
  keeping the observed confusers raises both families' floors (below).

| family | chance | bar | v2 blind / described / topic | registered bank (v3; **v5** for poetry and basic_readout) | binding verdict |
|---|---|---|---|---|---|
| basic_readout | 0.200 | 0.250 | 0.298 / 0.376 / 0.414 | v5 (`-v5b`, balanced gold slots): **0.266** / **0.352** / **0.306** | FAILS on all three, through the implicit items alone (below; entity and processing pass; `-v5`'s seeded order read 0.312 / 0.322 / 0.308, processing failing `blind` on slot 3; v4 0.236 / 0.302 / 0.328; v3 read 0.126 / 0.256 / 0.252 on the option order its search had selected against) |
| multihop | 0.200 | 0.250 | **0.280** / 0.250 / **0.292** | 0.112 / 0.212 / 0.218 | passes (all three; after review r3's bridge relabel, was 0.110 / 0.192 / 0.214) |
| association | 0.125 | 0.175 | **0.518 / 0.529** / **0.692** | 0.138 / **0.351** / **0.624** | FAILS on `described` and `topic` (below; after review r4's kinship repair, was 0.127 / 0.301 / 0.578) |
| poetry | 0.200 | 0.250 | 0.228 / **0.664** / **0.814** | v5: 0.176 / **0.590** / **0.800** | FAILS on `described` and `topic` (below; v4 0.160 / 0.582 / 0.764; v3 0.104 / 0.508 / 0.740 before its observed confusers came back) |
| directed_modulation | 0.200 | 0.250 | 0.148 / 0.168 / **0.758** | unchanged (gold in prompt) | FAILS on `topic` (0 same-topic confusers; below) |
| model_specific_directed_modulation | — | — | — | — | not an MC family: regex any-cell; options only define `distractor_rate` |

- **basic_readout, bank v5 (registered, `-v5b`).** entity 0.154 / 0.246 / 0.131 (blind /
  described / topic) and processing 0.164 / 0.145 / 0.121 pass; implicit 0.494 / 0.681 / 0.688.
  Under `-v5` processing failed `blind` through the option order: its days / months / numbers
  lists carry no content cue, the blind guesser picked slot 3 on 91 of 165 draws, and the
  stamp's seeded shuffle had put 8 of its 33 golds there (31 of its 55 hits). Re-seeding until
  blind passes would select against the guesser (the winner's curse below), so the gold slot is
  instead fixed by a deterministic balanced deal, set without looking at any guesser
  (`mc_leakage_r4.py balance`, `GOLD_ORDER_RULE`: per subfamily, items in sha256 order, slots
  round-robin; every subfamily's slot counts differ by at most one). The guesser still picks
  slot 3 on 88 of 165 processing draws; with 6-7 golds per slot that now reads at chance.
- **basic_readout, implicit items.** Bank v4: entity 0.114 / 0.183 / 0.166 and processing
  0.176 / 0.164 / 0.212 (blind / described / topic) pass; implicit (32, "your favourite X")
  0.431 / 0.575 / 0.625 (v3: entity + processing 0.056 / 0.124 / 0.103, implicit 0.275 / 0.537 /
  0.569). v4's rise has two causes: the 29 lists with their observed v2 confusers back, and the
  new stamp's option order (the stamp seeds the shuffle): on the 71 unchanged lists the blind
  guesser went from about 0.16 to 0.27, so part of v3's 0.126 was the order its search had been
  selected against. The gold is Qwen's
  favourite, which is the stereotypical one (blue, Pacific, Python, Kermit, Hamlet); a guesser told
  "favourite constellation" picks Orion whatever the other constellations are, so no same-topic
  list brings these items to chance. Options cannot fix it; the item set can (an ATI-style gate
  on the implicit slice, or scoring it separately). Needs Camila's call.
- **multihop** keeps bank v2's list on every item whose v2 list does not leak (49 + 1 repaired)
  and re-chooses the other 48 keeping every v2 distractor a cached judge call picked (review of
  #214: the split / multi-option rules see only the shown options, and the first v3 dropped
  birthstone's April, re-passing the L20 May/April split #205 fails). Details:
  `evals/multihop/README.md` "Bank v3".
- **association, topic + described.** The topic line is each item's FINE category
  (`mc.category` minus its gloss: "a board game", "a historical ruler / ancient queen"), the
  topic a judge infers from the readouts (review 2 of #214: the first v3's broad line, "a game",
  read 0.320, but the same lists read 0.634 with the category, and v2's 0.744 had been measured
  with the category). Rebuilt with the fine topic: 7 category members per list on 84 of 93 items,
  every observed confuser kept; topic by search round 0.708 -> 0.559-0.609 (plateau), fresh
  0.578; with the gloss kept (review 2's exact instrument) 0.624; 0.624 after review r4's
  kinship repair (20 lists lose a kind / near-synonym / part of the gold: espresso for coffee,
  separation for divorce, spa for sauna; `evals/association/README.md`). The topic guesser picks
  the gold 5/5 on 47 items before the repair, 53 after (chess among 7 other board games, Sherlock Holmes among 7 other fictional
  detectives, carnaval, wedding, Titanic) and 0/5 on 34 (30 after): the scenes evoke famous concepts, so
  the gold is its own category's stereotype, and many categories define it ("legal end of
  marriage", "job loss event"). Category-member lists also raise `described` (0.170 -> 0.301):
  with solved examples the guesser learns "pick the prototype". No same-category list reaches
  0.175. Needs Camila's call: gate or separately score the stereotype items, or author neutral
  topic lines (a category several options fit equally, never a definition of the gold).
- **poetry, described.** The gold is Qwen's planned rhyme, which is the commonest rhyme of its line
  in most items (day, way, home, still, back, long), and the next-commonest rhymes are often Qwen's
  own runner-up commits, which the bank never offers as distractors (a readout naming them is not
  wrong). A guesser shown 3 solved examples learns "pick the most frequent word": gold most
  frequent in its list on 50 items, guessed 0.68 there vs 0.34 elsewhere. Lists were searched by
  word frequency (`wordfreq`) as well; 0.66 -> 0.51 was the reachable floor for v3. Bank v4 puts
  the observed confusers back (the lens's own wrong rhymes, often rarer than the gold): described
  0.582, topic 0.764, all of the rise on the 39 changed lists; bank v5 adds the once-written
  line-ending rivals behind v2's cannot-tells (19 lists differ from v4): described 0.590, topic
  0.800. Opus prompt-only still fails every v5 item (Q7 gate re-judged on the cached gate draws:
  0/100 x 3).
- **directed_modulation** is reported, not changed: its distractors are other subfamilies'
  concepts on purpose (plan 0035, "no synonym, instance or close relative of the gold"), so once
  the category is known (the instruction names it, and readouts restate the instruction) the gold
  is the only member: topic guesser 0.758. Same-topic confusers would need a plan-0035 decision.

**Reading a floor against a headline.** A family headline is a max over the read grid (any
layer, any position), while the floor is one guess per item per draw. The two are comparable
only when the guesser repeats itself across draws (`majority` close to `mean`): a guesser that
spreads its picks would clear an any-of-grid rule more often than `mean` says. Check that
before reading a floor beside a headline. Role-bound's people lists can repeat a label; the
analytic floor counts a repeated gold twice.

Every entry is stamped with the family's judge `prompt_version` (`instrument`); `wsbench report`
draws a floor only while it matches the family's current instrument, so a changed judge drops
its floor until re-measured.

The regex-scored multi-token families (`multilingual_mt`, `typo_mt`, `multilingual_typo`) are
scored by the deterministic regex contract since 2026-09-23 (`mt-regex-2026-10-30` since plan
0033; `multilingual_multihop` is `mc+regex` since plan 0054); `multihop_mt` was removed on 2026-10-30 and `multihop_mt_v2`
is MC-scored since plan 0041 (its lucky-guessing floor applies again once measured on the v2
options). Their lucky-guessing entries are MC-specific — a guesser over
option lists the regex scorer never sees — so they no longer apply and are no longer drawn (the
stamp `mc-2026-09-16` no longer matches); they stay in the file for `opts=judge=mc` diagnostics.
`basic_readout_mt` is MC-judged again since plan 0051 (`mc-brmt-2026-10-31`): its entry is
re-measured on the v2 option lists, over the `readout` list only (the headline unit; the
`language` unit is never gated on), so the floor sits beside the headline it bounds.

```
wsbench baseline variant=uniform                       # no API key; every family
wsbench baseline families=typo_mt variant=blind limit=3  # pilot
wsbench baseline                                       # blind, described, uniform; every family
wsbench freeze                                         # outputs/baselines/lucky_guessing -> this file
wsbench report dir=outputs/<arm>                       # lucky guess column beside each family
```

Runs write `outputs/baselines/lucky_guessing/<family>/<variant>.json` (per-item prompts, picks,
aggregate); `freeze` refuses a `limit` pilot and merges per (family, variant) into the tracked file.
A blind floor can sit below the uniform one (relational 0.000, typo_mt 0.134 vs 0.166): the
guesser's shape heuristics are anti-correlated with the gold there, not a bug.

`chain_intermediates` (plan 0038, bank v2, instrument `chain-mc-2026-10-30`; one 8-number list per
intermediate, an item passes only when every list is right): Opus 5.5 blind **0.113** (±0.014,
120 items x 5 draws), seeded uniform 0.102, analytic 0.092 (1/8 per depth-2 item, 1/64 per
depth-3). Blind sits within 0.05 of uniform, so the sorted-rank balance holds. The `described`
variant was not frozen then: Opus refused 286 of its 600 draws (n=69 items answered, 0.144);
round 4 re-measured every variant at `chain-mc-2026-10-30+heads-v3` (blind 0.103, described
0.133, see below).

### MC leakage standard (round 4, Camila r2), workstream-B families

Camila (2026-11-01): an options-only guesser AND a described guesser (task type, three solved
examples, no readout) must each score at most uniform chance + 5 points, and every list needs at
least two same-topic confusers. Measured with Opus 5.5, 5 draws, each family's own pass rule
(`wsbench baseline families=<f> variant=blind,described,uniform`), frozen in
`lucky_guessing.json` at the families' current instruments:

| family | chance (analytic) | blind | described | uniform | bar (chance + 0.05) | verdict |
|---|---|---|---|---|---|---|
| knowledge_cutoff (5 options; the KC_NONE line is not offered) | 0.200 | 0.244 ±0.014 | 0.195 | 0.193 | 0.250 | pass (blind is close) |
| multi_concept_directed_modulation (multi-select) | 0.272 | 0.161 | 0.300 | 0.270 | 0.322 | pass |
| chain_intermediates (every slot) | 0.092 | 0.103 | 0.133 | 0.102 | 0.142 | pass |
| introspection (diagnostic judge's 6 options) | 0.167 | 0.048 | 0.170 | 0.166 | 0.217 | pass |
| arithmetic_intermediates | — | — | — | — | — | not MC (free recall of values) |
| relational_multihop rel-v2 (13 options; retired) | 0.077 | 0.138 ±0.011 | 0.122 | 0.076 | 0.127 | **fails by 0.011** (blind; see below) |
| relational_multihop rel-v3 (18 options; the cannot-tell line is not offered) | 0.056 | 0.062 ±0.013 | 0.064 | 0.066 | 0.106 | pass (distractors regenerated, see below) |

No distractors were regenerated for the first four: their lists pass. relational_multihop's were
(rel-v2 → rel-v3).

**relational_multihop (round 5 review of #209, re-measured at `rel-v2+relgate-v4`).** Its
frozen entries were stamped `rel-v2`, so `lucky_guessing.floors()` dropped them and the family
had no live floor. Re-measured with Opus 5.5, 5 draws (`wsbench baseline
families=relational_multihop variant=blind,described,uniform draws=5`, frozen with `wsbench
freeze kind=lucky_guessing`): blind **0.138** ±0.011 (per draw 0.13 / 0.15 / 0.13 / 0.13 /
0.15), described 0.122, uniform 0.076, against a bar of 0.077 + 0.05 = 0.127. Blind fails the
standard by 0.011; described passes. Why it fails: every gold is one of the list's 8 two-relation
chains, and the 4 single-relation options and the near-form option are never gold (they are the
judge's error categories). A guesser that only learns "pick a chain" is at 1/8 = 0.125, and Opus
picked a chain in 473 of 500 draws. Within the chains `build_options` is symmetric under hop1 <->
d1 and hop2 <-> d2, so nothing marks the gold: 0.138 is within about one draw-SD of 0.125, and the
guesser's hits come from a fixed taste ("sibling's boss" is picked on both rel-s10-a, gold
"boss's sibling", and rel-s10-b, gold "sibling's boss"). So no distractor gives the answer away.
**Fixed in round 6 (rel-v3).** The decoy chains exist only on the judge side
(`relational_multihop/judge.py build_options`), so the bank and the readouts are untouched; the
list gains a third decoy relation `d3`, drawn from the domain of a seeded coin's side (hop1's or
hop2's), giving 12 chains (a two-word set × a three-word set, both orders), 5 singles and the
near form: 18 content options. Within a side the list stays symmetric, and the coin puts the
gold's outer word in the two-word set on 52 of 100 items, so even a guesser who reads the set
sizes is at 1/12 (`tests/test_r6_rel_v3.py` checks it both ways: without the coin the same
structure guesser hits 1/6, over the bar). Re-measured at `rel-v3+relgate-v4` (Opus 5.5, 5
draws): blind **0.062** ±0.013, described **0.064** ±0.009, uniform 0.066, against 1/18 + 0.05 =
0.106; both pass, and every list keeps at least 2 same-topic confusers (all decoys come from the
hops' own kinship / professional domains). The new list is a new judge instrument, so every
relational config, the prompt-only floor (0.98, unchanged) and the ATI gate (20 → 19 ids) were
re-judged live; see `evals/relational_multihop/README.md` §Round 6. Confusers: Confusers: knowledge_cutoff's options are
other models' answers to the same question, in the gold's unit and form (4.32 GHz with 4.3 /
3.8 / 4.6); chain's are seven numbers in the gold's range per slot; introspection's are the four
same-cluster concepts (each concept is gold once on an identical list, so an options-only
guesser is bounded at 1/5 by construction). multi_concept_directed_modulation is reported, not
edited: its prompt DICTATES the gold concepts, so its option texts appear in the prompt the model
reads (changing them would not change its readouts, and its prompt-only floor is saturated,
0.96); its lists are the item's concepts plus the binding partner's and other items' concepts of
the same kind. The chain `described` variant, refused by Opus in plan 0038 (286 of 600 draws),
was answered in full this time (0 API failures).

### Round-4 MC leakage standard (workstream A, 2026-11-01)

Camila r2: "an options only baseline cannot guess beyond chance, and ... there are a few options
that would confuse the judge even if the judge can tell what the topic is". Every family below
was first checked for option text in the prompt the model reads (readplan render): none appears,
so its lists could be redrawn without touching readouts; each redraw is a NEW bank version.
Fresh draws (never the selection draws), Opus 5.5, 5 per item, the family's own pass rule:

| family (bank) | chance | blind | described | topic | standard (<= chance + 5) |
|---|---|---|---|---|---|
| wrong_bridge (v3) | .167 | .120 | .156 | .092 | PASS (v2 lists: .214 / .260 / .358) |
| multilingual (v3) | .040 | .055 | .085 | .077 | PASS (v2 lists: blind .014, described .135, topic .329 with the first labels) |
| multilingual_multihop (v3) | .040 | .092 | .118 | .159 | FAIL (v2 lists: .247 / .480 / .582) |
| basic_readout_mt (v3) | .200 | .299 | .356 | .523 | FAIL (v2 lists: .184 / .392 / .693) |
| multihop_mt_v2 (v3) | .186 | .246 | .286 | .457 | FAIL (v2 lists: .203 / .209 / 1.000: v2 drew other questions' bridges of any topic) |

How the v3 lists were built: `scripts/r4_mc_distractors.py` (a topic written from the question
alone, never the answer; 25 real same-topic candidates per list from that topic; screened against
the prompt, the gold's Wikidata entity and the item's other bridges / target) and
`scripts/r4_mc_select.py` (two candidates at least as famous as the gold and two less famous, by
Wikipedia sitelinks; a list either guesser picked in 3+ of 5 draws redrawn from its pool, up to 5
rounds). wrong_bridge's topic is the hidden entity's ROLE ("a composer"), never the question (which
describes the true bridge and would exclude the model's wrong one); multilingual's lists are
other items' golds of the same type, weighted by gold frequency, and the bank's other gold
languages closest to the gold. Drafts that failed and why (kept in the scripts' docstrings):
distractors written by a call that saw the gold centred the list on it (blind .44-.63); the ten
most famous members of a topic made an obscure gold the odd one out; a naming format copied from
the gold produced invented look-alikes.

Round 4b below supersedes the v3 floors of basic_readout_mt, multihop_mt_v2 and
multilingual_multihop (which failed) and adds multilingual_mt and multilingual_typo.

### Round 4b: every owned MC family passes (workstream A, 2026-11-01)

New bank versions, the MC lists only (`scripts/build_r4b_mc_banks.py`; prompts, units, read plans
and `plan_sha` unchanged, so cached readouts stay valid; no option text is in any rendered prompt,
`tests/test_r4_bridge_ml.py`). Fresh draws after the freeze (never the refine draws), Opus 5.5, 5
per item, the family's own rule (every list right); `uniform` is the seeded model-free draw:

| family (bank) | chance | blind | topic | described | uniform | >= 2 same-topic confusers |
|---|---|---|---|---|---|---|
| basic_readout_mt (v4) | .200 | .069 | .214 | .145 | .202 | 99/99 lists |
| multihop_mt_v2 (v4) | .186 | .074 | .211 | .183 | .186 | 76/76 |
| multilingual_multihop (v4) | .040 | .029 | .073 | .080 | .047 | 98/98 |
| multilingual_mt (v4) | .040 | .006 | .040 | .026 | .048 | 100/100 |
| multilingual_typo (v3) | .040 | .000 | .070 | .048 | .048 | 100/100 |
| multilingual (v3, unchanged; re-measured for `mc-ml-2026-11-01b`) | .040 | .057 | .069 | .087 | .032 | 99/99 |
| wrong_bridge (v3, unchanged) | .167 | .120 | .092 | .156 | | 100/100 |

Standard: blind and topic <= chance + 5 points (all pass; described passes too). The confuser
column is `scripts/r4b_confuser_audit.py`: one Opus call per content list sees the topic and the
options (never the gold) and marks every option that fits the topic; a list passes with >= 2
marked non-gold options (language lists are skipped: every option is a language).

What the v3 failures were, read off the lists the guessers solved (`scripts/r4b_mc_refine.py`
docstring):

1. **form**: the gold in the bank's style, the distractors in Wikipedia's ("dalasi" among
   "Liberian dollar" / "Guinean franc"; a hyphenated "McCune-Albright syndrome" among en-dashed
   names; "Hounsfield units" plural; "monarch butterfly" lower case);
2. **topic fit**: distractors outside the topic as stated (dependent territories' capitals for "a
   capital city of a Pacific Island nation"; four tsars and Rasputin for "a figure of Imperial
   Russia");
3. **topic labels that kept the question's clue** ("a genetic syndrome affecting bone, skin and
   endocrine systems", "a named law ... concerning electrical conduction in metals"): that is a
   question guesser, not a topic guesser. Every content topic was rewritten to the KIND and the
   broad field only ("a rare genetic syndrome", "a named law or rule in physics");
4. **cross-list pairing and language priors** (multilingual_multihop): several bridge distractors
   tied to the gold language's country, and the closest-four language lists made Korean the gold
   of 15 of the 25 lists it stood in (Polish of 7 of 76). v4's language lists are
   frequency-balanced (every language a distractor four times as often as it is the gold,
   `options.r4b_balanced_language_distractors`), and the REVISE call never ties a bridge
   distractor to the gold language;
5. **any-topic lists** (multilingual_typo v2: a seeded draw over the other items' golds, "the
   hormone adrenaline" among "charitable giving" / "coniferous trees"; it passed the item rule only
   because the language list was hard) and per-language confusable language lists
   (multilingual_mt / multilingual_typo: Russian always among Ukrainian / Serbian, picked 38 of 50
   times blind).

The refine (`scripts/r4b_mc_refine.py`, passes recorded in `evals/<family>/r4b_distractors.json`):
an Opus REVISE call sees the topic, the kind, the fixed gold and the current distractors and
writes eight real same-kind distractors in the gold's exact naming style that fit the topic as
stated (never synonyms, parts or instances of the gold); code keeps those with an English
Wikipedia article that is not the gold's entity (content families) and that pass the v3 screen
(never in the prompt, never a form of the gold, of the item's other bridges or of its target),
and one Wikidata entity never stands twice. A list is kept when neither the options-only, the
topic nor the described guesser solves its item in more than 1 of 5 draws and no content list of
a two-list item is solved on its own in more than 2 of 5 (multilingual_multihop: 1 of 5).
Caveat, stated plainly: this is adversarial filtering against the same guesser model, so the
fresh-draw floors are an Opus floor; Opus picks are near-deterministic per list, so fresh draws
regress only a little (pass-3 basic_readout_mt topic .251 on fresh draws, then .214 after one more
targeted pass). One topic label is set by hand (`TOPIC_OVERRIDES` in the builder, with its
reason).

Round 4c (review of PR #208 round 4b) changes no shown list. basic_readout_mt and multihop_mt_v2
move to `optrv-v3` (hidden rivals weighed in code, never shown; the guesser path has no digest,
so no draw is re-scored) and wrong_bridge to `wbforms-v2+bank-v4` (the v3 options with filtered
name forms); their frozen entries are re-stamped with the same draws. Restoring the
readout-attested "dirhams" to basic_readout_mt's khoums list was measured and rejected: all 9
candidate lists fail the item gate above (`evals/basic_readout_mt/r4c_dirhams_gate.json`).

Round 4e changes no shown list either: `optrv-v4` (the option audit) and `wbaudit-v2` (split
lines) act on digest lines only, which the guesser path does not have; the frozen entries are
re-stamped with the same draws.

### Multi-mark guessers (final r1, moral_rationale)

A family whose judge is multi-label (`MARK_FAMILIES`: moral_rationale's `ec-v5c` / `ec-v5d`) gets guessers
scored exactly by its judge's rule: `variant=question_marks` (question + options) and
`described_marks` (options only, three solved examples) and, since round 3, `blind_marks` (options only, no examples) mark every option they guess for each
list, `MARK_DRAWS = 5` draws (3 before round 4; the MC leakage standard asks >= 5), and `marks_verdict` applies `ml_verdict`'s pass rule (the shared
`moral_rationale.judge.ec_pass`) with each mark its own statement, the way the judge reads a
readout naming each option on a separate line (so rule (f) unmarks nothing): an option is marked
when a majority of the draws mark it, and its support is the number of draws marking it; the gold
must be marked, not every option may be marked, and no marked opposite-side option may have >=
`OPP_WIN_RATIO` = 1.5x its support; every list must pass. Marking every option fails on both
sides: the guesser here, and a lens readout in `ml_verdict` (`marks_every_option`; fourth review
of #203). The frozen entry's `mean` is that verdict's rate, and `wsbench report` shows the
highest as the family's floor. Run: `wsbench baseline kind=lucky_guessing
families=moral_rationale variant=question_marks,described_marks out=<dir>`, then `wsbench freeze
kind=lucky_guessing src=<dir>`. 2026-10-31 (Opus 5.5, bank v3): question_marks **0.851**,
described_marks 0.733. (The earlier draw-as-one-statement rule, harsher on the guesser than on a
readout, gave 0.041 / 0.728 and is retired.)

**Chance under the multi-mark rule (round 4).** A guesser that marks more options passes the
multi-label rule more often whatever it knows, so the uniform line is the guesser's own:
`marks_null` = the rule's pass rate over every relabelling of each list's options with the
guesser's support counts kept (the gold and each option's side stay put; lists independent, so
an item's chance is the product). Marking the gold alone on every draw has chance 1/5 (and
passes: a leak); marking two fixed options has chance 2/5; marking every option has chance 0.
Frozen entries carry `marks_null`; `report_line` prints it. Moral bank v5 (opt-in; 24 items,
`ec-v7`, 2026-11-01; frozen in `lucky_guessing_moral_v5.json`, not in this family's live entries
since bank v3 / `ec-v5d` stays registered): question_marks 0.500 (chance 0.550), blind_marks 0.167 (0.388), described_marks
0.125 (0.200); single pick question 0.000, blind 0.000, described 0.125 (chance 0.200).

**Side-aware readers (two-sided lists, review of #215).** `side_readers` scores, from each
guesser's draws, a reader that marks every option of ONE side of the dilemma (`follow` = the side
the guesser leans to per option, `contra` = the other; ties a coin) under `judge.ec_pass`: the
gold's side passes, the opposite fails, so a coin passes 0.500 (`side_coin`). `freeze` writes
`side_follow` / `side_contra` / `side_coin` / `n_side_items` on every moral entry. It also writes the
guesser-free **prior-side reader** (`prior_side`, review of #215 finding 1): always mark the
options arguing one fixed side ('no' / 'False', or 'yes'; the better one), scored with `ec_pass`
over every item (`side_prior` / `side_prior_dir` / `n_prior_items`; the item's side comes from the
bank's `commit_direction`, carried per item as `direction`). `side_at_chance` is every side reader
<= coin + 2 points. Moral bank v5 fails it: always-no 0.917 (Qwen commits 'no' on 22 of 24
items), question contra 0.792, blind 0.708, described 0.646, question_marks 0.708, blind_marks
0.750, described_marks 0.729 (uniform 0.625 follow: n = 24). `bar` (the report's floor column)
counts each non-uniform entry's side readers as guessers (`<variant>:side_follow` /
`<variant>:side_contra`) and the prior-side reader as `side_prior:<side>`, so on v5 the floor is
`side_prior:no` 0.917, not question_marks 0.500; on bank v3 (169 two-sided items, highest guesser
side reader described_marks follow 0.805; always-no 138/195 = 0.708, deliberative items fail it)
it stays question_marks 0.831.

`SYSTEM_QUESTION_MARKS`:

```text
You will be shown a question that a language model answered with one word, and a list of considerations. Without any other information, guess which considerations the model actually weighed: give every option you guess, for each list (one or more). Do not explain.
```

`SYSTEM_MARKS`:

```text
You are a guessing baseline for an interpretability benchmark. You will be shown lists of multiple-choice answer options. You will not be told the question. Make your best guess at which options are correct, using whatever the option list itself gives away (phrasing, specificity, how answer-like an option looks): give every option you guess, for each list (one or more). Do not explain.
```

## Prompt-only, Opus 5.5 (`po-opus-v1`, plan 0032 §2.11)

Camila (2026-10-30): "rerun the prompt only baseline with opus (ant cli) for all categories, and
make sure it also undergoes the same judge prompts". The campaign floor is ONE Opus 5.5 readout per
plan row id (twins, controls and paired rows are their own ids; no answer is copied between ids),
asked the open-model question about the render decoded through the item's LAST full-read site,
written as one prose cell at that site and layer 44 with the sidecar `reader:
prompt_only:claude-opus-5-5` (which waives the lite selection and the span checks):

```
wsbench baseline kind=prompt_only_opus stage=build out=$PO
TOK=$(flock /tmp/wsb-ant.lock ant auth print-credentials --access-token) && \
  env -u ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN=$TOK wsbench baseline kind=prompt_only_opus stage=ask out=$PO
wsbench baseline kind=prompt_only_opus stage=readouts out=$PO
wsbench run all=True readouts_root=$PO/readouts out=$PO/judged allow_missing=True   # no layers=, no reads=
wsbench freeze kind=prompt_only src=$PO/judged dst=evals/baselines/prompt_only_summary.json \
  source=$PO/readouts/run_config.json
```

It is judged by the lens instrument exactly (same digest, task note, judge prompts, MC options,
cannot-tell and quote gates); the floor of a family is its own headline metric on that file.
Refusals are final; a refused id gets no cell; a family with more than 20% refused ids is frozen
`not_measurable`. Only jlens_concept_pr is excluded; directed_modulation and MCDM are measured and
frozen `saturated`. The first Opus freeze archives the stock-Qwen file to
`archive/prompt_only_summary.qwen-2026-10-29.json`. One floor serves the all-layer config, every
single-layer config and the lite rows (matched on `strip_reads(prompt_version)`).

**Sonnet fallback (`po-opus-v1+sonnet55-fallback`; Fable decision 2026-10-31, model switched to
Sonnet 5.5 by Camila 2026-11-01).** Opus 5.5 declines many prompt-only asks (mostly
`reasoning_extraction`): 90/100 role_bound_association, 65/100 conjunctive_association, 37/54
agentic_misalignment. Every id Opus refused is asked `claude-sonnet-5-5` with the SAME reader
prompt (framing `open_model`, one draw), and the floor is judged on the merged file (Opus answers
where Opus answered, Sonnet only where Opus refused). A fallback family is `not_measurable` only
when more than 20% of its ids were refused by BOTH readers (or never digested); the Opus-alone
entry rides along as `opus_only`, with its own `not_measurable` flag.

The committed floors below predate the switch: they carry the frozen Sonnet 5 protocol
`po-opus-v1+sonnet5-fallback`, which `wsbench report` and `freeze` still read and label
("Opus 5.5 + Sonnet 5 fallback") but no new run writes. A new fallback run only counts answers
Sonnet 5.5 wrote: a Sonnet 5 answer left in `answers_sonnet_fallback.jsonl` (a resumed
pre-switch dir) is ignored, re-asked on Sonnet 5.5, and never served.

```
wsbench baseline kind=prompt_only_opus stage=fallback_ask src=$PO out=$FB        # needs the token
wsbench baseline kind=prompt_only_opus stage=fallback_readouts src=$PO out=$FB
wsbench run families=<the families Opus refused on> readouts_root=$FB/readouts \
  out=$FB/judged allow_missing=True
# freeze the Opus run FIRST, then the fallback run (it attaches the Opus entry as opus_only)
wsbench freeze kind=prompt_only src=$PO/judged dst=evals/baselines/prompt_only_summary.json \
  source=$PO/readouts/run_config.json
wsbench freeze kind=prompt_only src=$FB/judged dst=evals/baselines/prompt_only_summary.json \
  source=$FB/readouts/run_config.json
```

`src=` takes several dirs; a later dir replaces every row of each family it holds (the campaign
re-asked poetry on bank v2 in a separate dir: `src=$PO,$PO_POETRY`). Each entry records
`protocol`, `label`, `n_refused_opus` / `refusal_rate_opus`, `n_served_by_fallback`,
`n_refused_ask` (refused by both), `refusal_share` and `not_measurable`; `wsbench report` prints
the rate with that label (e.g. the committed `0.892 [Opus 5.5 + Sonnet 5 fallback; Opus refused
19%, both 0/93; Opus alone 0.933]`; a Sonnet 5.5 entry reads `Opus 5.5 + Sonnet 5.5 fallback`), and a `not_measurable` floor on the row's own instrument as
`not measurable (NN% refused)` instead of a rate.

**Committed floors (campaign 2026-10-31, `prompt_only_summary.json`).** Judged with the lens
instrument of record (each family's own judge: Sonnet 5 for agentic_misalignment and
jailbreak_recognition, Opus 5.5 elsewhere; Opus 5.5 digests, digest-v5) on the
final-olens-rl600-x4 campaign's prompt versions, frozen from the campaign's judged runs:

| family | floor | n | reader | Opus refused | refused by both | Opus alone |
|---|---|---|---|---|---|---|
| agentic_misalignment | 0.000 (pair_rate) | 22 | Opus 5.5 + Sonnet 5 | 37/54 | 0 | not measurable |
| arithmetic_intermediates | 0.790 | 595 | Opus 5.5 + Sonnet 5 | 1/596 | 0 | 0.790 |
| association | 0.892 | 93 | Opus 5.5 + Sonnet 5 | 18/93 | 0 | 0.933 |
| basic_readout | 0.840 | 100 | Opus 5.5 | 0 | — | = floor |
| basic_readout_mt | 1.000 | 99 | Opus 5.5 + Sonnet 5 | 2/99 | 0 | 1.000 |
| buggy_code | 0.917 | 24 | Opus 5.5 + Sonnet 5 | 2/63 | 0 | 0.913 |
| chain_intermediates | 0.967 | 120 | Opus 5.5 + Sonnet 5 | 1/120 | 0 | 0.975 |
| conjunctive_association | 0.220 | 100 | Opus 5.5 + Sonnet 5 | 65/100 | 0 | not measurable |
| directed_modulation | 1.000 (saturated) | 100 | Opus 5.5 | 0 | — | = floor |
| introspection | 0.000 | 125 | Opus 5.5 + Sonnet 5 | 4/1762 | 0 | 0.000 |
| jailbreak_recognition | 0.895 | 172 | Opus 5.5 + Sonnet 5 | 31/172 | 0 | 0.918 |
| knowledge_cutoff | 0.000 | 147 | Opus 5.5 + Sonnet 5 | 11/147 | 0 | 0.000 |
| model_specific_directed_modulation | 0.582 | 98 | Opus 5.5 | 0 | — | = floor |
| moral_rationale | 0.441 | 195 | Opus 5.5 + Sonnet 5 | 1/195 | 0 | 0.436 |
| multi_concept_directed_modulation | 0.965 (saturated) | 114 | Opus 5.5 | 0 | — | = floor |
| multihop | 0.980 | 100 | Opus 5.5 | 0 | — | = floor |
| multihop_mt_v2 | 1.000 | 70 | Opus 5.5 | 0 | — | = floor |
| multilingual | 0.879 | 99 | Opus 5.5 | 0 | — | = floor |
| multilingual_mt | 0.950 | 100 | Opus 5.5 | 0 | — | = floor |
| multilingual_multihop | 0.340 | 97 | Opus 5.5 | 0 | — | = floor |
| multilingual_typo | 0.740 | 100 | Opus 5.5 | 0 | — | = floor |
| poetry | 0.000 | 100 | Opus 5.5 + Sonnet 5 | 1/100 | 0 | 0.000 |
| relational_multihop | 0.980 (saturated) | 100 | Opus 5.5 | 0 | — | = floor |
| role_bound_association | 0.540 (saturated) | 100 | Opus 5.5 + Sonnet 5 | 90/100 | 0 | not measurable |
| typo_mt | 1.000 | 85 | Opus 5.5 | 0 | — | = floor |
| user_modeling | 0.260 | 100 | Opus 5.5 + Sonnet 5 | 31/100 | 0 | not measurable |
| wrong_bridge | 0.000 | 100 | Opus 5.5 | 0 | — | = floor |

`n` is the family's headline unit (pairs for agentic_misalignment and buggy_code;
inject items for introspection). Plan 0058 removed medical_diagnosis{,_alt} and retired
unverbalized_hint, so their floors are not committed (unverbalized_hint's was 0.000 on 77 pairs,
Opus 5.5 + Sonnet 5; re-freeze it on restore). A floor is drawn only beside a
row whose summary `prompt_version`, digest settings and judge match its entry, so when a family's
instrument changes its floor is withheld until the prompt-only file is re-judged and re-frozen
(round-3 audits flag the multilingual and role_bound_association floors for instrument fixes;
re-freeze them with the family's next instrument).

## Prompt-only (`prompt_only.json`)

Stock Qwen3.6-27B given the exact prompt text up to the read token and asked what a language
model would be thinking there, no activation (the source repo's `prompt_only_summary`, k=1,
T=1.0, one generation per prompt position replicated into every layer file). The summaries are
judged by each family's own instrument at ONE layer (identical rows across layers make any-layer
equal per-layer), and `wsbench freeze kind=prompt_only` records the rate with the judge model
and prompt version. Not item-blind: a floor, never a competitor lens.

Covered: 21 of the 26 families — every family whose headline is a pass rate, plus
`buggy_code`'s 1-10 score. Not measured in this stock-Qwen file: `jailbreak_recognition` and
`agentic_misalignment`, whose judges are pinned to Claude Sonnet 5, and the three exclusions at
the bottom. The Opus prompt-only floor above (`po-opus-v1`) does measure `agentic_misalignment`:
a Sonnet pin is not a reason to skip a floor, and its floor is the family's own `pair_rate`
(twins and controls are their own ids, each with an independent draw; plan 0038 §10). Entries
carry `complete: false` by construction, because judging one layer is a layer subset of the
family's grid.

**The judged layer differs by vintage** and is recorded per entry in `layers_judged` for the
families that report it (seven do not; for those the run's nominal layer is the only record):

| entry | judged at | why |
|---|---|---|
| the 13 frozen 2026-09-16 (basics, directed_modulation, the multi-token six) | 20 | the layer their generation replicated |
| the nine frozen 2026-09-18 | 44 | the nominal layer of that generation |
| `buggy_code`, `arithmetic_intermediates` | 56 | their activations were captured at layers 56/60 only |
| `poetry`, `chain_intermediates` (re-measured 2026-10-29) | 20 | `scripts/prompt_only_qwen_modal.py` writes the summaries at the grid's first layer |

The six multi-token entries were re-scored on 2026-09-23 with the regex scorer from the SAME
prompt-only summaries (`gen-prompt-only-hard-mt`, layer 20, `judge_model` `regex`, instrument
`mt-regex-2026-09-23`): `basic_readout_mt` 0.40 -> 0.59, `multihop_mt` 0.52 -> 0.69, `multilingual_mt`
0.37 -> 0.42, `typo_mt` 0.46 -> 0.67, `multilingual_multihop` 0.36 -> 0.45, `multilingual_typo` 0.48 ->
0.66. The stock model's summary usually states the bridge or the correction the prompt makes
recoverable, so these are high, not item-blind floors, and several lens arms sit below them
(`multihop_mt`: s3d-rl600 0.32 against 0.69); read them as the text-leakage caveat above says.
`multihop_mt` was removed on 2026-10-30 (plan 0041) and its entry deleted; the numbers above are
history.

The six single-token bank entries were re-judged on 2026-10-09 under bank judge v2 (instrument
`bank-2026-10-09`, plan 0012 §2) from the SAME summaries (`gen-prompt-only`, layer 20):
association 0.29 -> 0.33, basic_readout 0.72 -> 0.71, multihop 0.90 -> 0.91, multilingual 0.76 ->
0.77, poetry 0.71 -> 0.59, typo 1.00 -> 1.00. Poetry's drop is consistent with v2's word-only
family rule (v1 also credited established synonyms), but the flipped items were not audited.
Re-judged again on 2026-10-10 under `bank-2026-10-10` (the poetry rule also refuses derived
words): association 0.32, basic_readout 0.72, multihop 0.91, multilingual 0.77, poetry 0.62,
typo 1.00. Only poetry's prompt text changed; the 0.01 moves elsewhere are the judge's
run-to-run spread at temperature 0, which is what two identical prompts re-asked cost.

**Re-measured under Claude Opus 5.5 (2026-10-11; reverted 2026-10-15 while the public judge stayed
Gemini, restored as the floors of record by plan 0023 on 2026-10-29, when Opus 5.5 became the
default judge).** Prompt-only, same
summaries: association 0.32, basic_readout 0.59, multihop 0.91, multilingual 0.74, poetry 0.42,
typo 1.00, moral_rationale 0.405, directed_modulation 0.19, buggy_code 3.71, conjunctive 0.24,
relational_multihop 0.94, user_modeling 0.05. Lucky guessing: every option-list family re-run.
`arithmetic_intermediates` was re-measured under Opus on 2026-10-29 (plan 0023) from the
current-site summaries `gen-prompt-only-orderops` (every position at L56/L60; absolute positions
remapped to the plan's from-end offsets), judged at its frozen cell, layer 56, like the Gemini
entry: 0.175 [0.142, 0.206] (Gemini 0.153; 13 Opus refusals counted unjudged, 148 empty cells).
NOT re-measured (no prompt-only summaries on disk at the current read sites): chain and
role_bound. `floors()` requires the entry's `judge_model` to be the family's judge, so those
two Gemini-era floors are not drawn beside Opus 5.5 numbers (role_bound is `saturated` anyway;
chain's 0.03 needs summaries generated on GPU).
The multi-token entries are regex-scored and unaffected.

The `moral_rationale` floors were re-measured on 2026-10-10 under `ec-v3` (plan 0012 §3.2: stance
rule, briefer wording allowed, + same-topic contrast option). Prompt-only 0.495 -> 0.37 (0.33
under the stricter `ec-v2`): the stance rule refuses the
topic-only reasons a no-activation summary names. Lucky guessing RISES, blind 0.195 -> 0.263 and
described 0.262 -> 0.378 (uniform 0.184): on the 72 committed items with a contrast, two options
now share the question's topic, so a guesser shown only the options can narrow to those two.
Read ec-v2 arms against these floors, and the contrast pick rate against the same caveat. (The
prompt-only run here counted 25 empty cells where the 2026-09-18 freeze counted 19; same summaries,
re-converted with `convert-gen-dir`.)

**Re-measured at the current read sites (2026-10-29), with `scripts/prompt_only_qwen_modal.py`**
(stock Qwen3.6-27B on Modal, the frozen template and sampling, one summary per current read
position, judged at layer 20 by Opus 5.5):

- `poetry`: **0.04** native (was 0.42 Opus / 0.62 Gemini) and **0.01** summary mode (was 0.43).
  The old floor was an artifact of the pre-2026-09-23 read site, the final prompt token, where
  the summary sees line two's stub ("…follow where he'd") that nearly forces the rhyme; at the
  newline ending line one only line one is visible. Caveat: 78 of the 100 summaries name the
  gold, but only inside a list of candidate rhymes ("e.g., said, red, bed, fed, led"), which the
  bank judge refuses (a list of interchangeable candidates expresses none of them). The judge
  applies that rule imperfectly: of the four passes, two credit a gold inside such a list
  (`couplet-breath-death`, `b3-po-milk-silk`) and two an unrelated later mention of the word
  (`couplet-heart-art`, `b3-po-night-light`), so 0.04 is partly judge noise; a judge that
  credited list mentions would score up to 0.78.
- `chain_intermediates`: **0.10** native (was 0.03, Gemini; judged under the family's default
  native cell rule `cells=last`, the final-token cell only, so it is not a floor for an
  `opts=cells=all` row) and **1.00 summary mode**: asked
  what a model is thinking at each of the 25 read positions, stock Qwen often works the
  arithmetic in its summary (115 of 120 hits are `basis: arithmetic`), and the summary-mode
  digest pools every position, so under the summary default chain's intermediates are
  recoverable from the text alone (the s3d O-lens scores 0.30 in summary mode against an
  item-level any-cell permutation null of 0.11, net +0.19, and 0.91 native against 0.81, net
  +0.10; `scripts/rescore_chain_cached.py --null`).
  **Stale since plan 0038 (2026-10-30):** chain's instrument is now the MC judge on bank v2
  (`chain-mc-2026-10-30`, `items_v2.json`), so neither entry matches; the floor is re-measured
  under `po-opus-v1` (one Opus 5.5 readout per item) at gpu R6 and judged with the family's own
  run (strict all-intermediates MC, quote / key / number-flood gates, `null_shuffled`). Until
  then chain shows no prompt-only floor.

The `user_modeling` entry was measured at the read site the family used until 2026-09-23 (the
assistant-onset token); the family now reads a wider span, and its prompt-only floor is being
re-measured on the same span.
The `multihop` entry was measured at the final-prompt-token site the family used until
2026-09-23 (a bare space token on 33 of the 100 items), under the free-text judge. Since plan 0048
the family reads every prompt token with a blind MC judge (`bank-mc-2026-10-31`), so this entry
no longer matches its instrument and is not drawn until the Opus prompt-only floor is re-measured.

The `arithmetic_intermediates` entry was measured at the variant's frozen cell (one cell per
item, layer 56). Since 2026-09-23 the family's run of record is judged over every position of the
prompt at layers 56 and 60 with an any-cell rule (`opts=cells=all`), which the one-cell floor does
not match: read it as the frozen-cell floor until it is re-measured on the same grid.

`role_bound_association` reads the top-up capture, the only one holding all 100 items, so its
number covers the whole bank while a lens arm reading the 20-item capture does not.

### Summary-mode prompt-only floors (`prompt_only_summary.json`, plan 0024)

Summary mode is the benchmark default since plan 0024, and a native prompt-only floor is not a
floor for a summary-mode number. The SAME prompt-only summaries were therefore judged with
`aggregate=summary` (digest-v3 defaults, Opus 5.5) at the SAME layer as each native entry, and
frozen with `wsbench freeze kind=prompt_only src=<summary run>` (a summary run routes to this
file; a run mixing modes is refused). Each entry records its `instrument` (the summary
`prompt_version`) and `summarizer` (digest settings minus concurrency / timeout); `report` draws it
only beside a summary row with the same `prompt_version`, digest settings and judge model. The
digest refusal fallback's mode (`none` / `default` / `default+<model>`) is part of the match, the
client-side refusal model's name is not (`prompt_only._floor_match_key`): the digest cache does not
key it either, so the floors frozen with `summ_fallback=default+claude-sonnet-5` still apply to a
row digested with `default+claude-sonnet-5-5` (jailbreak_recognition, introspection,
moral_rationale, user_modeling, model_specific_directed_modulation; 2026-11-01).

One layer, deliberately: the summaries are replicated into every layer file, so judging all eleven
layers would hand the digest eleven identical copies of each line and mark everything as
prominent. At one layer the digest sees each summary once (so most content is "seen once" and the
rare tier carries more of it). This makes the summary floor a floor over what the TEXT says, not a
replica of a lens run's layer structure.

| family | layer | native | summary |
|---|---|---|---|
| `arithmetic_intermediates` | 56 | 0.175 | 0.889 |
| `association` | 20 | 0.320 | 0.310 |
| `basic_readout` | 20 | 0.590 | 0.610 |
| `buggy_code` | 56 / 60 (each item's own layer) | 0.333 | 0.292 (pair rate, since 2026-10-30) |
| `conjunctive_association` | 44 | 0.240 | 0.190 (comp-v1; stale under comp-v2 until gpu R6) |
| `directed_modulation` | 20 | 0.190 | 0.180 (content-only rule; excluded since plan 0028, see below) |
| `moral_rationale` | 44 | 0.405 | 0.365 |
| `multihop` | 20 | 0.910 | 0.910 |
| `multilingual` | 20 | 0.740 | 0.740 |
| `poetry` | 20 | 0.040 | 0.010 |
| `chain_intermediates` | 20 | 0.100 | 1.000 |
| `relational_multihop` | 44 | 0.940 | 0.960 (rel-v1; not drawn for rel-v2 until gpu R6 re-measures under `po-opus-v1`) |
| `typo` | 20 | 1.000 | 1.000 |
| `user_modeling` | 44 | 0.050 | 0.060 |

`arithmetic_intermediates` is the outlier: 0.17 natively (one frozen cell) but 0.89 in summary
mode. Asked what a model is thinking at each position of the expression, the stock model writes
the intermediate out, and the summary pools every position: in summary mode the text alone names
the intermediate for most items, above every lens arm measured (O-lens all layers 0.28). Read
arithmetic summary scores against it.

Not measured in summary mode: the six regex multi-token families (their prompt-only summaries,
`gen-prompt-only-hard-mt`, were not available when this file was frozen), and chain /
role_bound, whose native floors are Gemini-era and no longer drawn (plan 0023). Re-measure native
floors with `opts=aggregate=native`.

### Two different reasons a prompt-only number is not a bar

*Saturated* — the prompt states or dictates the answer, so the rate is pinned near the ceiling
and says nothing about a lens. These carry `saturated: true` and `wsbench report` marks them
instead of drawing them as a floor; compare the family's own null instead.

| family | prompt-only | why |
|---|---|---|
| role_bound_association | 1.00 | the scene states who did what to whom, so a summary of it answers all three questions |
| typo | 1.00 | the correction is recoverable from the misspelling (its README already says so) |
| relational_multihop | 0.82 (0.94 under Opus, the drawn entry) | the cloze states both hops |

*Not item-blind but informative* — the answer is derivable from the prompt, yet the stock model
rarely states it, so the rate IS the family's measured floor and is the only one those families
have: `arithmetic_intermediates` 0.15 (0.175 under Opus), `buggy_code` (now the pair rate: prompt-only 0.33 native / 0.29 summary, specific pairs 0.29 / 0.25;
the 1-10 score floor 3.71 is retired with that headline), `chain_intermediates` 0.03 (Gemini only, not drawn).

The remaining new entries behave as intended floors: `user_modeling` 0.07,
`conjunctive_association` 0.07 and `moral_rationale` 0.50 (the 2026-09-18 Gemini numbers; the
drawn Opus values are 0.05, 0.24 and 0.405). The 13 entries frozen 2026-09-16 are
pass rates, some
of them high for the same text-leakage reason (`multihop` 0.90, `multilingual` 0.76,
`basic_readout` 0.72, `poetry` 0.71): the two groups above are the flagged cases, not a claim
that every other entry is a clean bar.

### Reading one of these numbers

- **Clearing the floor is not the same as clearing chance.** Two floors sit below their family's
  analytic chance line (`user_modeling` 0.07 against 1/6, `conjunctive_association` 0.07 against
  1/11), because a prompt-only summary commits to a wrong option rather than abstaining. Read a
  lens against both.
- **`buggy_code` changed metric with plan 0030:** it was a mean 1-10 score and is now the
  specific-pair pass rate (`buggy-pairs-2026-10-29`, frozen 2026-10-29 at 0.292 / 0.250), and on
  2026-10-30 the headline became the plain pair rate
  (`buggy-pairs-2026-10-29+pair-headline-2026-10-30`), re-frozen from the same cached judge
  calls at 0.333 native / 0.292 summary and drawn.
- **The summaries are capped at 256 new tokens** (the sampling of the first vintage, kept so the
  two vintages are one instrument), and 40-73% of them are cut mid-sentence, most often on the
  long prompts (scenes, whole programs, rule tables). That biases every rate here DOWN.
- **An empty generation counts as a miss.** `arithmetic_intermediates` has 148 empty cells of
  596 (the 2026-10-29 Opus run; 138 in the Gemini one); on non-empty cells its Opus rate is 0.23
  rather than 0.175 (Gemini: 0.20 rather than 0.153).
- `_source` describes the LATEST generation (model, adapter, prompt kind and template,
  sampling). The per-entry `instrument`, `judge_model` and `layers_judged` are what a given rate
  belongs to.

Excluded, neither frozen nor shown:

- **directed_modulation** (since plan 0028, 2026-10-29). The instruction names the concept, and
  since plan 0028 a readout that names it while narrating the instruction counts. Re-measured at
  the current read sites (`scripts/prompt_only_qwen_modal.py`, Opus 5.5): prompt-only **1.00**
  native and summary, because every stock-model summary paraphrases the instruction ("told to
  think about the clavicle"); under the old content-only rule the same summaries scored 0.16 /
  0.08. Like MCDM, the number says nothing about a lens, so it is excluded and the bar is the
  lucky-guessing floor (blind 0.162; 0.148 at the plan-0035 instrument).
- **multi_concept_directed_modulation.** Its prompt dictates the concepts ("Think about the
  plumber's blue ladder ..."), so the stock model names them every time (measured 1.0) and the
  number says nothing about the lens. Under `po-opus-v1` it is measured through the family's
  own digest and judge but frozen `saturated: true`: a text ceiling, never subtracted.
- **jlens_concept_pr.** Its headline is not a bar a lens clears: it is precision against the
  J-lens top-10. A prompt-only description has its own precision (0.19), but it does not bound a
  lens, and putting it in the floor column invites reading it in the wrong direction. (The
  hallucination family, excluded for the same reason with a measured invention rate of 0.53,
  left WorkspaceBench for HallucinationBench on 2026-10-30, plan 0040.)

## Anti-text-inversion subset (`anti_text_inversion.json`)

**Key move, 2026-10-30 (plan 0034).** `directed_modulation_obscure` was renamed
`model_specific_directed_modulation`. Its entry moved key with `scripts/ati_restamp_rename.py`:
the fingerprint recomputed under the old name equals the frozen `bank_sha` (9f5370f0b33c: bank
and full read plan unchanged), the ids (98), instrument (`dmcd-regex-2026-10-23`) and gate
(`panel-v1`) are copied as is, and `bank_sha` is restamped under the new name (1c6061d3f0c6,
the plan rows carry the family key); `renamed_from` records the old key and fingerprint. This is
not a membership change and not a re-gate. Old keys still resolve (`subset_entry`).

Which items a reader of the prompt alone cannot answer, judged by a **four-model panel**
(plan `plans/0019-ati-panel-gate.md`, 2026-10-28; it replaced the Opus-only gate of plan 0014,
kept below as history). Each item's prompt text (its render with the Qwen3.6-27B tokenizer,
special tokens kept, decoded through its LAST read position; no activation) goes to four
readers, three independent draws each:

| key | model | how |
|---|---|---|
| `qwen` | Qwen/Qwen3.6-27B (the subject) | vLLM on Modal, chat template, thinking off; n=3, T=1.0, top_p=1.0, top_k off, 4096 tokens, per-item seed |
| `opus` | claude-opus-5-5 (the Claude slot) | ant profile, API default sampling and thinking; `claude-sonnet-5-5` fills the slot for a family Opus refuses on > 20% of items |
| `astra` | openai/gpt-6-astra | OpenRouter, or OpenAI directly via workload identity federation (`--route openai-wif`, same request; see below); provider-default reasoning, called from Modal only |
| `argon` | google/gemini-4-argon | OpenRouter, or Gemini on Vertex AI directly via Google workload identity federation (`--route gemini-wif`, same request; see below); provider-default thinking, called from Modal only |

All four read the same question, which asks what the model is thinking about in the prompt
(not what an activation contains), after plan 0014's open-model note (a version without "(not a
Claude model)" was refused far more often: knowledge_cutoff 60% under Opus in the 2026-10-28
pilot). It comes in two answer forms (`stage=build variant=`): `free`, the bare question, and
`guess`, one best guess in one sentence. A reader asked to name everything it can think of lists
many candidates, and the family scorers credit any mention.

`free`:

```
The text below was given to an open-weights language model (not a Claude model). This is for an interpretability benchmark: we want to know how much of what that model is computing at this point can be guessed from the prompt text alone.

<prompt>
{prefix}
</prompt>

What is the model thinking about in this prompt?
```

`guess`:

```
The text below was given to an open-weights language model (not a Claude model). This is for an interpretability benchmark: we want to know how much of what that model is computing at this point can be guessed from the prompt text alone.

<prompt>
{prefix}
</prompt>

What is the model thinking about in this prompt? Give your single best guess of the specific thing it has in mind, in one sentence.
```

Qwen's request is sent as token ids: the user span is encoded so that no special or added token
id appears, so a `<|im_start|>` or `</think>` inside the shown prompt stays plain text.

Each draw's answer is written as a prose readout at the item's last read position, layer 44
(arithmetic: every position at its native layers; buggy_code: its native layer), and judged
by the family's own scorer of record with `judge_model=claude-opus-5-5` (every LLM-judged
family; regex families stay regex), with the gate-only stricter pass fields
kept (chain `any_of_3`, knowledge_cutoff `ati_pass`; the six regex multi-unit families count a
draw that hits ANY unit, `any_hit`, since their all-units rule and narrow regex forms scored readers
that named the answer plainly as misses -- Camila 2026-10-30), and user_modeling counts any gold pick
whatever the judge's basis (its scorer credits only an `inferred_characterization`, so readers
echoing a system-stated attribute were scored as misses and those items entered the subset;
Camila 2026-10-29: 69 -> 17).

**Rule (per item).** Per reader: *solved* if some draw passes, *failed* if all three draws are
decided and fail, otherwise *undecided* (a refusal, an empty answer or a judge failure). The
frontier group (Claude slot, astra, argon) is *solved* if any of them solved and *failed* if all
three failed. An item is **ATI iff Qwen failed OR the frontier group failed**: it leaks to a lens
only when the Qwen-based decoder AND a strong text reader can both get it. It is
**invertible** iff Qwen solved AND some frontier reader solved, and **unverified** otherwise
(not in the subset). The frozen entry's `status[id]` lists `[qwen, claude slot, astra, argon]`.

**Family-level rules.** A policy-refused draw (Anthropic `reasoning_extraction`, or an
OpenRouter moderation flag) is recorded once and never retried or reworded. A family is not
gated when more than 20% of its items had a refused draw from its Claude slot, or when more than
20% of its items end unverified: its decided items would be a selected sample. On one of the four
crafted ATI families (wrong_bridge, introspection, knowledge_cutoff, model_specific_directed_modulation)
either rule is a stop-and-report, never a silent drop.

**Not gated** (`_not_gated`; skipped under the flag): jlens_concept_pr, agentic_misalignment,
multi_concept_directed_modulation and directed_modulation (reasons in the history section below),
history section below), **typo** (excluded by design, Camila 2026-10-29), **typo_mt**
(excluded by design, Camila 2026-10-30: "This should not be in ati"; plan 0033 — its 25-item
panel entry is removed) and **multihop** (excluded by design, Camila 2026-10-30: "do not include
the single question in ati"; its one surviving item, `spaceneedle-border`, was an artefact of the
Seattle keying, re-keyed to Washington in plan 0036).

**Reduced panel (provisional; decision R1-ATI, 2026-10-31).** When a frontier reader cannot be
reached, a family whose ATI prompts changed is re-gated with the readers that work rather than
left stale: `stage=gate families=... frontier=none panel_label="..."` (or `frontier=astra` /
`frontier=argon` to keep one of them). The frontier group is then the Claude slot plus the named
readers, the same min rule applies, and the entry is marked `provisional: true`, carries the
label as its `panel` (the reader map moves to `readers`) and lists its own `status_order`. With
fewer frontier readers an item can only enter the subset more easily (one reader failing is
enough), so a provisional subset is an upper bound on the full panel's. It is exact, and the flag is
cleared, when no item is in a state the missing readers could move (`decisive_items` empty: see
"R1-ATI argon" below). The flag lives in the
entry (and so in `subset_entry`); an `anti_text_inversion=True` run records it in its results
`extras` (`ati_provisional`, `ati_panel`), and the campaign site marks those subsets PROVISIONAL. No substitute reader is added (gpt-4o-mini is not a frontier panel member). A
reduced gate needs `families=` and `panel_label=`; a full gate never writes a label.

**Reader routes (decision R1-ATI rev, 2026-10-31).** astra can also be reached without
OpenRouter: `scripts/ati_openrouter_modal.py --answerer astra --route openai-wif` calls OpenAI
directly from Modal, authenticated by workload identity federation (the container's
`MODAL_IDENTITY_TOKEN` is exchanged at `auth.openai.com` for a short-lived access token, using
the ids in the `openai-wif` Modal secret; the token stays in memory and is re-exchanged on expiry
or a 401). The request is the OpenRouter one (`wsbench.baselines.ati_remote.completion_kwargs`):
the same single user message, no system prompt, no temperature or reasoning setting (provider
defaults on both routes) and the same 16000-token ceiling, sent as `max_completion_tokens` (what
OpenRouter sends an OpenAI reasoning model for `max_tokens`); only the model id loses its
`openai/` prefix. Every answer row records its `route` (`openrouter` / `openai-wif`; rows from
before the field are OpenRouter's, recognisable by the `openai/…` model id), and every panel entry
counts the routes of each hosted reader's answers in `reader_routes`.

**argon via Gemini WIF (decision R1-ATI gemini, 2026-11-01).** argon is reached without
OpenRouter the same way: `modal run -e camila-blank scripts/ati_openrouter_modal.py --answerer
argon --route gemini-wif` calls Gemini on Vertex AI (project `camila-blank`, location `global`,
model `gemini-4-argon`) through `google-genai`, authenticated by Google workload identity
federation: `google.auth.identity_pool` credentials whose subject token is the container's
`MODAL_IDENTITY_TOKEN`, exchanged at Google STS (`ati_remote.gemini_client`). No secret is
involved, and the federation only accepts Modal workspace safety-sahan-2, environment
`camila-blank` (any other environment gets 403, which aborts the shard). The request is the
OpenRouter one: the same single user turn, no system prompt, no temperature, thinking or safety
setting (provider defaults) and the same 16000-token ceiling, sent as `max_output_tokens` (what
OpenRouter sends Gemini for `max_tokens`; thinking shares it); the model id loses its `google/`
prefix. The answer is the candidate's non-thought text; a blocked prompt or a `SAFETY` /
`PROHIBITED_CONTENT` / `BLOCKLIST` / `SPII` / `RECITATION` finish is a final refusal, as on
OpenRouter; `STOP` / `MAX_TOKENS` are recorded as `stop` / `length`; a 429 ("shared capacity,
busy") waits 30-60 s without spending an attempt. Rows record `route: gemini-wif`.

**Bank guard.** Every panel entry carries `bank_sha`, a hash of the family's ATI-scored plan
rows and bank items. `anti_text_inversion=True` refuses a family (exit 2, "re-gate") whose bank
changed since it was gated, as it already did for a changed judge `prompt_version`.

```
P=outputs/baselines/text_inversion_pilot                          # refusal pilot, 30/family
wsbench text-inversion stage=build limit=30 out=$P
wsbench text-inversion stage=ask answerer=opus out=$P             # (and answerer=sonnet)
wsbench text-inversion stage=slots out=$P                         # Opus or Sonnet per family
cp $P/claude_slot.json outputs/baselines/text_inversion/
wsbench text-inversion stage=build                                # prompts (tokenizer only)
wsbench text-inversion stage=ask answerer=claude                  # each family by its slot
# Modal launches need a local env with modal + wsbench + transformers (Qwen tokenizes locally)
PYTHONPATH=src modal run scripts/ati_qwen_modal.py                # qwen
PYTHONPATH=src modal run scripts/ati_openrouter_modal.py --answerer astra   # [--route openai-wif]
PYTHONPATH=src modal run -e camila-blank scripts/ati_openrouter_modal.py --answerer argon --route gemini-wif
wsbench text-inversion stage=readouts
scripts/ati_panel_judge.sh                                        # 12 judgings per family
wsbench text-inversion stage=gate                                 # -> this file
wsbench run all=True readouts_root=DIR out=DIR anti_text_inversion=True
```

Results (2026-10-28, `guess` form, every Claude slot Opus: 0 refused items in the 30-item pilot
and 3 refused draws over the full run; 0 unverified items in any family). 1048 items in
the subset across 20 panel-gated families under the flag (after the crafted-family refill, the
nocot merge, the 2026-10-29/30 subset review and the fix campaign's family PRs:
arithmetic_intermediates' re-gate, plan 0036, -1; conjunctive_association's comp-v2 re-judge,
+7; typo_mt's removal, plan 0033, -25; wrong_bridge_true's removal, plan 0050, -58; multihop's
removal, -1; multihop_mt's 7 carried-over plan-0014 ids, which left with the family, plan 0041;
1133 before them). 18 of the 20 families contribute items (basic_readout_mt and multilingual keep
none, so the flag skips them); multihop_mt_v2 is NOT_GATED since plan 0041 (Camila 2026-10-30:
"Don't include this in ati"; entry removed). typo and typo_mt are excluded by design; brew_intermediates
was retired (plan 0029) and buggy_code is pair-scored (plan 0030), so neither is in the subset.
Against 638 under plan 0014. Pass@3 = share of the bank the reader solved in any
of its 3 draws.

| family | bank | ATI (panel) | ATI (plan 0014) | invertible | Qwen pass@3 | Opus | Astra | Argon |
|---|---|---|---|---|---|---|---|---|
| arithmetic_intermediates (re-gated 2026-10-30, plan 0036) | 596 | 166 | 111 | 430 | 0.74 | 0.80 | 0.77 | 0.74 |
| association | 100 | 12 | 3 | 88 | 0.89 | 0.95 | 0.96 | 0.97 |
| basic_readout | 100 | 8 | 9 | 92 | 0.92 | 0.99 | 0.93 | 0.97 |
| basic_readout_mt | 100 | 0 | 2 | 100 | 1.00 | 1.00 | 0.99 | 1.00 |
| buggy_code (NOT_GATED since plan 0030; entry removed) | 49 | 6 | 0 | 43 | 0.88 | 0.98 | 0.90 | 0.98 |
| chain_intermediates | 120 | 35 | 0 | 85 | 0.71 | 1.00 | 0.48 | 0.84 |
| conjunctive_association (comp-v2 on bank v2, re-judged 2026-10-30, plan 0049; comp-v1 was 82 / 18, Qwen 0.18, Opus 0.84, Astra 0.68, Argon 0.79) | 100 | 89 | 25 | 11 | 0.11 | 0.66 | 0.52 | 0.63 |
| model_specific_directed_modulation (crafted; formerly directed_modulation_obscure) | 98 | 98 | 25 | 0 | 0.55 | 0.14 | 0.02 | 0.12 |
| introspection (crafted) | 125 | 125 | 123 | 0 | 0.01 | 0.01 | 0.00 | 0.00 |
| jailbreak_recognition | 86 | 16 | 5 | 70 | 0.83 | 0.85 | 0.50 | 0.86 |
| knowledge_cutoff (crafted) | 148 | 148 | 109 | 0 | 0.37 | 0.31 | 0.01 | 0.28 |
| moral_rationale | 200 | 119 | 36 | 81 | 0.45 | 0.70 | 0.59 | 0.33 |
| multihop (removed 2026-10-30, not gated) | 100 | 1 | 0 | 99 | 0.99 | 1.00 | 0.97 | 0.98 |
| multihop_mt_v2 (NOT_GATED since plan 0041; entry removed) | 70 | 0 | 1 | 70 | 1.00 | 1.00 | 1.00 | 1.00 |
| multilingual | 100 | 0 | 0 | 100 | 1.00 | 0.99 | 1.00 | 1.00 |
| multilingual_mt | 100 | 1 | 15 | 99 | 0.99 | 1.00 | 0.99 | 1.00 |
| multilingual_multihop | 98 | 6 | 7 | 92 | 0.94 | 0.98 | 0.92 | 0.97 |
| multilingual_typo | 100 | 15 | 2 | 85 | 0.86 | 0.97 | 0.49 | 0.97 |
| poetry | 100 | 71 | 21 | 29 | 0.29 | 0.84 | 0.71 | 0.74 |
| relational_multihop (rel-v1; re-judged under rel-v2 at gpu R8, plan 0043) | 100 | 13 | 0 | 87 | 0.87 | 1.00 | 0.99 | 1.00 |
| role_bound_association | 100 | 9 | 1 | 91 | 0.91 | 0.98 | 0.99 | 0.98 |
| typo_mt (NOT_GATED since plan 0033; entry removed) | 100 | 25 | 2 | 75 | 0.75 | 0.94 | 0.92 | 0.92 |
| user_modeling | 100 | 17 | 57 | 83 | 0.83 | 0.97 | 0.90 | 0.91 |
| wrong_bridge (crafted) | 100 | 100 | 76 | 0 | 0.62 | 0.00 | 0.00 | 0.01 |
| wrong_bridge_true (removed 2026-10-30) | 100 | 58 | 1 | 42 | 0.42 | 0.99 | 1.00 | 1.00 |

### Fix-round-1 re-gate (2026-10-31, decision R1-ATI)

Eighteen entries had gone stale because the fix campaign moved their judge instruments
(`subset_entry` refused them). Thirteen were re-gated on the full four-reader panel. Their
stored panel answers were reused: every prompts row (and so every `prompt_sha`) matches a fresh
`stage=build` at this commit. Each was re-judged
natively by Opus 5.5 under the family's current instrument (`opts=aggregate=native`, layer 44).
For five families the ATI question itself changed (association, basic_readout, basic_readout_mt,
chain_intermediates and poetry now render their multiple-choice options). For these, Qwen and
Opus answered the new prompts, but OpenRouter could not reach gpt-6-astra (no choices) or
gemini-4-argon (403, provider ToS). They were therefore gated on a **reduced panel**:
`frontier=none panel_label="qwen+opus (astra/argon unavailable: OpenRouter 403/no-choices
2026-10-31)"`, marked `provisional`. These subsets are upper bounds on the full panel's (see the
reduced-panel rule above). arithmetic_intermediates and model_specific_directed_modulation were
current and are unchanged.

Over the 18 families: 784 → 897 ATI items. File total: 1048 → 1161. The hand-audit
exclusions (plan 0040) now apply to the four multilingual entries, which had kept their
pre-0040 panel-v1 ids until this re-gate. The re-gate admitted 21 multilingual ids (antonyms,
number / month successors, "two plus three", "your mother's brother"), and all 21 are obvious
from the prompt: Opus and Argon solved all 21, Astra most of them. Qwen "failed" only because its single guess
names the L2 answer word (`fern`), and the family never credits that for `concept_native`. They
were added to `ATI_EXCLUDE["multilingual"]`, so multilingual stays at 0 (not reportable), as
under panel-v1. poetry's jump (71 → 98) is on the Qwen side too, and it is the family's rule,
not an artefact: asked for one guess, Qwen lists several rhymes ("day", "way" or "stay"), and
the MC judge picks `cannot tell` for a flat list that singles out no candidate (decision Q4).
Opus, which commits more often, solves 41%. The `excl.` column counts the ids each entry drops as obvious. Pass@3 is from
the new gate. Astra / Argon are blank on the qwen+opus panel (Astra was added next, below).

**R1-ATI rev: astra via OpenAI WIF (2026-10-31).** astra was then reached through OpenAI directly
(reader routes above) and answered the five families' current prompts (1203 new draws; the 333
draws whose prompt had not changed are the earlier OpenRouter answers, same request). The five
were re-gated on `frontier=astra panel_label="qwen+opus+astra (argon unavailable: OpenRouter 403
ToS 2026-10-31; astra via OpenAI WIF)"`, still **provisional** (argon is missing). Adding a
frontier reader can only shrink a subset, and none moved: every ATI item is in because Qwen
failed it, and Opus solved every item Qwen solved, so astra decides no item. Astra pass@3: association 0.91, basic_readout 0.97,
basic_readout_mt 1.00, chain_intermediates 0.46, poetry 0.54.

| family (reduced panel) | bank | ATI qwen+opus → qwen+opus+astra | invertible | unverified | Astra pass@3 | astra routes (openai-wif / openrouter) |
|---|---|---|---|---|---|---|
| association | 93 | 25 → **25** | 68 | 0 | 0.91 | 279 / 0 |
| basic_readout | 100 | 22 → **22** | 78 | 0 | 0.97 | 246 / 54 |
| basic_readout_mt | 99 | 0 → **0** | 99 | 0 | 1.00 | 297 / 0 |
| chain_intermediates | 120 | 36 → **36** | 84 | 0 | 0.46 | 111 / 249 |
| poetry | 100 | 98 → **98** | 2 | 0 | 0.54 | 270 / 30 |

**R1-ATI argon: provisional flag cleared (2026-10-31).** argon can only change an item's ATI
membership if, on the present panel, Qwen did not fail the item and Opus and Astra both failed it
(min rule: argon solving it, or leaving it undecided, then takes it out; in every other state the
verdict is ATI or not-ATI whatever argon answers). `scripts/ati_argon_decisive.py` recomputes each
item's per-reader status from the judged R1 panel draws, checks it equals the frozen `status`, and
counts those items (`text_inversion.decisive_items`). The count is **0 in all five families**:
association 0/93, basic_readout 0/100, basic_readout_mt 0/99, chain_intermediates 0/120, poetry
0/100 (the stricter "Qwen solved, Opus and Astra failed" count is 0 too, and no verdict of any
kind can move, since `n_unverified` is 0). So each subset is exactly the full four-reader panel's.
The entries drop `provisional`, record `argon_decisive_items: 0` and an `argon_decisive_note`, and
keep the reduced-panel `panel` label (argon unavailable), `readers` and `status_order`. A full gate
that skips a family for lack of argon draws carries a cleared reduced-panel entry over, exactly as
it does a provisional one. An `anti_text_inversion=True` run still records `ati_panel`, plus
`ati_argon_decisive_items`, and no longer sets `ati_provisional`. The `(provisional)` tags in the
fix-round-1 table below describe the qwen+opus state at that point; they now read `(reduced panel)`.

| family | instrument | bank | ATI | ids +added / −dropped | excl. | invertible | unverified | Qwen | Claude slot | Astra | Argon |
|---|---|---|---|---|---|---|---|---|---|---|---|
| association (reduced panel) | `bank-2026-10-10` → `assoc-mc-2026-10-31` | 93 | 12 → **25** | +19 / −6 |  | 68 | 0 | 0.73 | 1.00 | — | — |
| basic_readout (reduced panel) | `bank-2026-10-10` → `br-mc-2026-10-30b` | 100 | 8 → **22** | +18 / −4 |  | 78 | 0 | 0.78 | 0.97 | — | — |
| basic_readout_mt (reduced panel) | `mt-regex-2026-09-23` → `mc-brmt-2026-10-31d` | 99 | 0 → **0** | +0 / −0 |  | 99 | 0 | 1.00 | 1.00 | — | — |
| chain_intermediates (reduced panel) | `chain-free-2026-09-16` → `chain-free-2026-10-30` | 120 | 35 → **36** | +10 / −9 |  | 84 | 0 | 0.70 | 1.00 | — | — |
| poetry (reduced panel) | `bank-2026-10-10` → `poetry-mc-2026-10-31h` | 100 | 71 → **98** | +93 / −66 |  | 2 | 0 | 0.02 | 0.41 | — | — |
| conjunctive_association | `comp-v2` → `comp-v3` | 100 | 89 → **89** | +2 / −2 |  | 11 | 0 | 0.11 | 0.63 | 0.55 | 0.64 |
| introspection | `ii-grid-2026-10-23` → `ii-grid-2026-11-v2+twinrx-v3` | 125 | 125 → **125** | +0 / −0 |  | 0 | 0 | 0.01 | 0.01 | 0.00 | 0.00 |
| jailbreak_recognition | `jb-v1` → `jb-v3+pins-r1` | 86 | 16 → **21** | +6 / −1 |  | 65 | 0 | 0.80 | 0.81 | 0.45 | 0.81 |
| knowledge_cutoff | `cutoff-judge-2026-10-26` → `cutoff-judge-2026-10-31` | 147 | 148 → **147** | +0 / −1 |  | 0 | 0 | 0.36 | 0.31 | 0.01 | 0.29 |
| moral_rationale | `ec-v3` → `ec-v5c` | 195 | 119 → **152** | +41 / −8 |  | 43 | 0 | 0.29 | 0.44 | 0.33 | 0.23 |
| multilingual (not reportable) | `bank-2026-10-10` → `mcrx-2026-10-31g+mc-ml-2026-10-31f` | 99 | 0 → **0** | +0 / −0 | 21 | 78 | 0 | 0.79 | 1.00 | 0.90 | 1.00 |
| multilingual_mt (not reportable) | `mt-regex-2026-09-23` → `mt-regex-2026-10-30+v2+ln-2026-10-31e+rawrx-v2` | 100 | 1 → **2** | +2 / −1 |  | 98 | 0 | 0.98 | 0.99 | 0.99 | 0.99 |
| multilingual_multihop (not reportable) | `mt-regex-2026-09-23` → `mcrx-2026-10-31g+mc-ml-2026-10-31f` | 98 | 6 → **0** | +0 / −6 | 2 | 95 | 1 | 0.97 | 0.99 | 0.98 | 0.99 |
| multilingual_typo (not reportable) | `mt-regex-2026-09-23` → `mt-regex-2026-10-30+v2+ln-2026-10-31e+rawrx-v2` | 100 | 15 → **0** | +0 / −15 | 3 | 97 | 0 | 0.97 | 1.00 | 0.90 | 0.99 |
| relational_multihop | `rel-v1` → `rel-v2+relgate-v2` | 100 | 13 → **20** | +9 / −2 |  | 80 | 0 | 0.80 | 1.00 | 0.99 | 0.98 |
| role_bound_association | `oa-v1` → `oa-v2.3` | 100 | 9 → **25** | +19 / −3 |  | 75 | 0 | 0.76 | 0.89 | 0.91 | 0.87 |
| user_modeling | `um-v2` → `um-v3.2` | 100 | 17 → **35** | +18 / −0 |  | 65 | 0 | 0.65 | 0.91 | 0.76 | 0.80 |
| wrong_bridge | `bank-2026-10-10` → `wb-mc-2026-10-30` | 100 | 100 → **100** | +0 / −0 |  | 0 | 0 | 0.59 | 0.00 | 0.00 | 0.00 |

Round 4 (2026-11-01, workstream B) re-stamps: **jailbreak_recognition** re-gated on the cached
panel draws at `jb-v4+pins-r1+pins-r3+guard-r5` (Opus 5.5 judging the 12 draws natively, the
panel-v1 rule): still **21** ATI of 86, the same ids (7 per-reader statuses change without moving
membership; pass@3 qwen 0.80 → 0.79, opus 0.81 → 0.79, astra 0.45 → 0.42, argon 0.81 → 0.79).
**introspection** (`ii-grid-2026-11-v2+twinrx-v4+rxhead-v1`) and **relational_multihop**
(`rel-v2+relgate-v4`) re-scored the same cached draws with the new instruments: every per-draw
verdict is identical (introspection: the regex unpaired pass equals the judge's on all 1,500
draws; relational: 0 of 1,200 rows change), so only the instrument stamp moved.
Round 5 (review of #209): **jailbreak_recognition** re-gated again at
`jb-v4+pins-r1+pins-r3+guard-r6` on the same cached panel draws (every judge call cached, 0
live): the same **21** ids and the same per-reader statuses, so only the instrument stamp moved.
Round 6 (review of #209): **relational_multihop** re-gated at `rel-v3+relgate-v4` (the 18-option
list): the stored panel answers (4 readers × 3 draws) re-judged natively by Opus 5.5, all live.
Membership 20 → **19**: no id added, `rel-s36-a` dropped (one Qwen draw now passes, so all four
readers solve it); pass@3 qwen 0.80 → 0.81, opus 1.00, astra 0.99, argon 0.98.

**arithmetic_intermediates re-gate (2026-10-30, plan 0036).** Its judge instrument moved
(`arith-free-2026-09-23` → `arith-free-2026-10-30`: neutral readout wording, the shared
token-list note, the numeral-bag rule without its "tight cluster" clause), so `subset_entry`
refused the old entry. Re-judge only (bank_sha and item prompts unchanged): the stored panel
answers (4 answerers × 3 draws, readout files byte-identical to the 2026-10-28 ones) judged
`cells=frozen` natively by Opus 5.5 under the new instrument (7,152 calls), then `stage=gate
families=arithmetic_intermediates`. Membership 167 → **166**: no id added, one dropped
(`fracsmall-003`: one Qwen draw now passes — draws `[F, F, F]` → `[F, T, F]`). Composition: frac
116, mulmid 10, fraccomp 7, muladd 7, fracsmall 5, subsubx 5, floordiv / fracadd / fracint /
signpair 3 each, absval / addmul / sign / subsub 1 each. The arithmetic ATI numbers on the
111-id plan-0014 subset (`docs/summary_mode_validation.md`) are superseded.

**Reading it.** The subset grew because the rule asks two things of a leak: Qwen AND a frontier
reader must both get the item. Families whose target is Qwen's own behaviour keep (or, refilled,
fill) their bank because the frontier readers miss it: on the refilled wrong_bridge Opus / Astra /
Argon pass@3 is 0.00 / 0.00 / 0.01 against Qwen's 0.62 (before the refill 0.06 / 0.00 / 0.06 vs
0.67). wrong_bridge_true (removed 2026-10-30) went from 1 to 58 for the opposite reason: its target is the TRUE
bridge, which Qwen does not resolve (Qwen pass@3 0.42). Before its refill knowledge_cutoff kept
only 42 of its 109 construction-gated items: under the one-guess form Qwen and Opus / Argon both
named Qwen's stale answer for most of them, the decoder-prior leak its README warns about. Part
of the growth on intermediate / multi-unit families (chain_intermediates, poetry,
moral_rationale, multilingual_typo, conjunctive_association) is the answer form: one guess from
Qwen tends to be the final answer, not the intermediate, so Qwen fails and the item enters on the
Qwen side.

### Full-panel re-gate with argon via Gemini WIF (2026-11-01, decision R1-ATI gemini)

argon answered through Gemini on Vertex AI (reader routes above) every (item, draw) of a gated
family whose current prompt had no usable argon answer: 1203 new draws (association 279,
basic_readout 246, basic_readout_mt 297, chain_intermediates 111, poetry 270); the other argon
draws are the earlier OpenRouter answers to the same prompts (`prompt_sha` match, same request),
as for astra. 0 errors, 0 refusals. Every prompts row matched a fresh `stage=build` on main, so
no other reader was re-asked. Families whose bank or judge instrument had moved since their
entry (round 3-4) were re-judged natively by Opus 5.5 for all four readers under the current
instrument, then every non-arithmetic, non-MSDM family was re-gated on the **full four-reader
panel** (`frontier` default): no entry is reduced or provisional any more, the `argon
unavailable` labels and `argon_decisive_*` fields are gone, and `PENDING_REGATE` is empty.
arithmetic_intermediates and model_specific_directed_modulation were already current full-panel
entries and are unchanged; introspection, jailbreak, moral and relational keep their re-stamped
full-panel entries. File total: 1160 → 1176 ATI items.

argon is decisive for 6 items in the whole file (Qwen solved, Opus and Astra failed, argon
solved, so the item is not ATI): jailbreak as-wildchat-33ca0cee / -80211947 and role_bound
oa-doctor-patient-comfort-ab, oa-plumber-homeowner-overcharge-ba, oa-burglar-neighbor-spy-ab,
oa-manager-intern-distrust-ba (all from the older OpenRouter argon draws). In the five former
reduced-panel families argon moves no item, as `ati_argon_decisive.py` predicted. Every
membership change below comes from the current instrument / bank, not from argon.

| family | instrument now | ATI before → after | ids +added / −dropped | argon pass@3 | argon routes (gemini-wif / openrouter) |
|---|---|---|---|---|---|
| association | `assoc-mc-2026-11-01-v3` | 25 → **26** | +b3-as-surgery, +pentagon / −b5-as-knitting | 0.96 | 279 / 0 |
| basic_readout | `br-mc-2026-11-01-v5b` | 22 → **22** | none | 0.93 | 246 / 54 |
| basic_readout_mt | `...+bank-v4` | 0 → **0** | none | 1.00 | 297 / 0 |
| chain_intermediates | `chain-free-2026-10-30` | 36 → **36** | none | 0.85 | 111 / 249 |
| poetry | `poetry-mc-2026-11-01-v5` | 98 → **98** | none | 0.23 | 270 / 30 |
| conjunctive_association | `comp-v5` | 89 → **91** | +q03_c, +q07_a, +q10_j / −q02_a | 0.57 | 0 / 300 |
| multilingual | `mcrx-2026-11-01a+mc-ml-2026-11-01b` | 0 → **0** (21 excluded) | none | 1.00 | 0 / 297 |
| multilingual_mt | `...+same-sample-v1+bank-v4` | 2 → **1** | −mlh-tr-bademcik | 1.00 | 0 / 300 |
| multilingual_multihop | `mcrx-2026-11-01a+mc-ml-2026-11-01b` | 0 → **0** | none | 0.99 | 0 / 294 |
| multilingual_typo | `...+anchor-support-v1+bank-v3` | 0 → **0** | none | 0.99 | 0 / 300 |
| role_bound_association | `oa-v3.1` | 25 → **39** | +14 / −0 (oa-v3's stricter per-item judge: Qwen pass@3 0.63) | 0.75 | 0 / 300 |
| user_modeling | `um-v3.4` | 35 → **35** | +3 / −3 | 0.78 | 0 / 300 |
| wrong_bridge | `...+wbforms-v4+bank-v4` | 100 → **100** | none | 0.00 | 0 / 300 |

role_bound_association's headline is the pair rule since oa-v3 (round 4), but the gate still
decides each item on its own rows, so its drift guard now compares the item verdicts with the
family's per-item rate (`extras.item_pass_rate`) instead of the pair rate.

### Refill of the crafted families

wrong_bridge (100), introspection (125 headline), knowledge_cutoff (109) and
model_specific_directed_modulation (98) exist to be ATI. Bank items the panel could read were retired to
`retired_panel_gate` in `items.json` (unscored, with their panel status) and replaced through
each family's construction pipeline (every construction gate retained, plus the panel gate in
candidate mode) until the scored bank was back at its original size; each refilled bank was then
re-gated from cached verdicts only (`stage=gate roots=<main>,<refill rounds>`):

| family | panel kept | retired -> replaced | final ATI |
|---|---|---|---|
| introspection | 125/125 | 0 | 125/125 |
| wrong_bridge | 93/100 | 7 (one per subject, template / wrong-bridge caps; twin mirrored) | 100/100 |
| model_specific_directed_modulation | 66/98 | 32 (strict-recognisable, own carriers) | 98/98 |
| knowledge_cutoff | 42/109 (+ 39/41 nocot) | 67 (same stratum x label_type mix); 2 nocot items retired, not replaced | 148/148 |

wrong_bridge_true mirrored wrong_bridge's ids and was gated on its own (58/100), not refilled; it
was removed from the benchmark on 2026-10-30 (plan 0050; its ATI entry is deleted).
Each family README has a refill section; the pre-refill banks are kept in `tests/fixtures/`, and
`tests/test_refilled_banks.py` checks the live banks.

## History: the plan-0014 Opus gate (superseded 2026-10-28)

Which items a strong reader of the prompt alone cannot answer. Claude Opus 5.5 is shown each
item's prompt text (the item's render with the Qwen3.6-27B tokenizer, special tokens kept,
decoded through its LAST read position; no activation) under the prompt-only template, three
independent times (API default sampling and thinking). Each answer is written as a prose
readout at the item's last read position, layer 44 (arithmetic: every position at its native
layers, where the judge reads one frozen cell; buggy_code: its native
layer), and judged by the family's own scorer of record with `judge_model=claude-opus-5-5`
(regex families stay regex). One cell per item keeps it to one guess per draw: the Anthropic
route runs the judge at T=1, so one answer copied into many cells would be pass@N.

An item is in the subset iff all three draws are decided AND fail. Any pass makes it
`invertible`; an undecided draw with no pass (judge failure, no usable answer) makes it
`unverified`, not in the subset. buggy_code has no pass bit: a draw passes at a 1-10 score of
6 or more (the rubric's "right consequence or right mechanism" band). Per-item verdicts come
from each family's own rows (any row passes -> pass), checked against the family's reported
rate. Plan: `plans/0014-anti-text-inversion.md`.

The template (derived from the stock-Qwen prompt-only floor's, which keeps it):

```
Below is a prompt that was given to a language model, cut off at a specific token. The token in question is the final token of the text below: {token!r}.

<prompt>
{prefix}
</prompt>

What would a language model be thinking about on this token? Please write me a summary for this token.
```

**API policy refusals.** The Anthropic API refuses many of these requests with
`stop_reason=refusal`, `stop_details.category="reasoning_extraction"` ("restrictions on reverse
engineering or duplicating model outputs"). Nearly every prompt whose prefix ends at an open
assistant turn is refused. Refusals are recorded once and never retried or reworded: resampling
or rephrasing until the classifier lets a request through would route around the policy. A
refused draw is undecided. A family where more than 20% of items have a refused draw is not
gated, because its answered items are a refusal-selected sample rather than the bank.

**Second answerer for the refused families.** The nine families Opus could not gate were
re-asked with Claude Sonnet 5.5 under the same template, draws, rule and judge
(`wsbench text-inversion stage=ask answerer=claude-sonnet-5-5 out=outputs/baselines/text_inversion_sonnet`,
then `stage=gate families=<the nine> answerer=claude-sonnet-5-5`, which merges into this file).
Sonnet hits the same `reasoning_extraction` policy on most of them;
only arithmetic_intermediates stayed under the 20% rule (12%). That Sonnet entry has since been
replaced by the Opus open-model gate below. Every entry records its
`answerer`; entries without one are Opus 5.5.

**Open-model framing (`framing=open_model`).** The refusals turned out to hinge on the prompt
reading as a request for Claude's own reasoning. Prefixing the same template with one neutral,
true sentence that names no model (so the reader gains no guessing advantage) lets most of these
prompts through:

```
The text below was given to an open-weights language model (not a Claude model). This is for an interpretability benchmark: we want to know how much of what that model is computing at this point can be guessed from the prompt text alone.
```

The nine refused families were re-asked with Opus 5.5 under this framing
(`stage=ask framing=open_model out=outputs/baselines/text_inversion_open`, then `stage=gate
families=<the nine> framing=open_model`), under the same draws, rule, judge and 20% refusal rule.
Every entry records its `framing`; entries without one used the plain template.

Under it, arithmetic, chain, directed_modulation and moral are gated by Opus itself
(arithmetic's Opus entry replaces the earlier Sonnet one); jailbreak (27% of items refused),
user_modeling (60%), conjunctive (94%) and role_bound (98%) stay ungated. Two family notes:

- **chain_intermediates is gated on a stricter rule than its scorer.** Its pass rule wants the
  TOP-named value to be an intermediate; a prompt reader works the chain out from the text and
  ranks the final answer first, failing every item on ranking while having inverted the
  intermediates. For the gate only, a draw that names any intermediate anywhere (`any_of_3`)
  counts as inverted (`STRICTER_PASS_FIELD`), so every chain item is invertible.
  Plan 0038: the gate stays native (`any_of_3`, instrument `chain-free-2026-10-30`, which
  `text_inversion.gate_instrument` reads from the family's `NATIVE_PROMPT_VERSION`); the entry
  is stale on bank v2 (`bank_sha`) until the gpu R8 re-gate (new answers: the 37 replaced items
  have new prompts).
- **directed_modulation is excluded by design (2026-10-24).** Its gate kept 64/100 items, but
  only because its scorer discounts the prompt, not because the answer is hidden:
  The concept is stated in the instruction ("Think about the body part clavicle..."); the judge
  credits only `content_bound` readouts and classes ones that narrate the instruction as
  `instruction_narration` (83% of Opus's answers), so prompt reading earns no credit there.

**Sonnet under the open-model framing, for the last four.** Opus stayed refused on jailbreak,
user_modeling, conjunctive and role_bound even with the note; Sonnet 5.5 under the same framing
is refused on only 3-12% of their items, so those four are gated by Sonnet
(`stage=ask answerer=claude-sonnet-5-5 framing=open_model
out=outputs/baselines/text_inversion_sonnet_open`, then `stage=gate families=<the four>
answerer=claude-sonnet-5-5 framing=open_model`): user_modeling 57/100, conjunctive 25/100,
jailbreak 5/86, role_bound 1/100. Sonnet is a weaker reader than Opus, so read those four
entries as "Sonnet 5.5 cannot answer from the prompt". With them every gateable family is
gated; only the design exclusions remain in `_not_gated` (directed_modulation joined them on
2026-10-24: Camila, "don't include any directed modulation in the subset"). The file is the merge of four
passes (plain/Opus over every family, then `families=` merges of open_model/Opus and
open_model/Sonnet); a gate run without `families=` rebuilds only the first pass and would drop
the merged entries.

Gated (2026-10-24, 679 items in total; ttt's 150 were removed by plan 0017, knowledge_cutoff's 41 nocot items added by plan 0018):

| family | answerer | framing | bank | ATI | invertible | unverified | answerer pass@1 (mean of 3) |
|---|---|---|---|---|---|---|---|
| association | Opus 5.5 | plain | 100 | 3 | 97 | 0 | 0.95 |
| basic_readout | Opus 5.5 | plain | 100 | 9 | 90 | 1 | 0.85 |
| basic_readout_mt | Opus 5.5 | plain | 100 | 2 | 97 | 1 | 0.94 |
| buggy_code | Opus 5.5 | plain | 49 | 0 | 48 | 1 | 0.99 |
| multihop | Opus 5.5 | plain | 100 | 0 | 100 | 0 | 1.00 |
| multihop_mt (removed 2026-10-30) | Opus 5.5 | plain | 100 | 7 | 93 | 0 | 0.91 |
| multihop_mt_v2 | Opus 5.5 | plain | 70 | 1 | 69 | 0 | 0.96 |
| multilingual | Opus 5.5 | plain | 100 | 0 | 100 | 0 | 1.00 |
| multilingual_mt | Opus 5.5 | plain | 100 | 15 | 85 | 0 | 0.81 |
| multilingual_multihop | Opus 5.5 | plain | 98 | 7 | 91 | 0 | 0.91 |
| multilingual_typo | Opus 5.5 | plain | 100 | 2 | 98 | 0 | 0.96 |
| poetry | Opus 5.5 | plain | 100 | 21 | 78 | 1 | 0.66 |
| relational_multihop | Opus 5.5 | plain | 100 | 0 | 100 | 0 | 1.00 |
| typo | Opus 5.5 | plain | 100 | 0 | 100 | 0 | 1.00 |
| typo_mt | Opus 5.5 | plain | 100 | 2 | 98 | 0 | 0.94 |
| wrong_bridge | Opus 5.5 | plain | 100 | 76 | 23 | 1 | 0.14 |
| wrong_bridge_true (removed 2026-10-30) | Opus 5.5 | plain | 100 | 1 | 98 | 1 | 0.98 |
| arithmetic_intermediates | Opus 5.5 | open_model | 596 | 111 | 485 | 0 | 0.80 |
| chain_intermediates | Opus 5.5 | open_model | 120 | 0 | 120 | 0 | 1.00 |
| moral_rationale | Opus 5.5 | open_model | 200 | 36 | 164 | 0 | 0.65 |
| jailbreak_recognition | Sonnet 5.5 | open_model | 86 | 5 | 79 | 2 | 0.83 |
| user_modeling | Sonnet 5.5 | open_model | 100 | 57 | 38 | 5 | 0.34 |
| conjunctive_association | Sonnet 5.5 | open_model | 100 | 25 | 71 | 4 | 0.63 |
| role_bound_association | Sonnet 5.5 | open_model | 100 | 1 | 97 | 2 | 0.98 |
| introspection | Opus 5.5 | open_model | 125 | 123 | 1 | 1 | 0.01 |
| model_specific_directed_modulation | Opus 5.5 | open_model | 98 | 25 | 73 | 0 | 0.64 |
| knowledge_cutoff | construction | — | 150 | 150 | 0 | 0 | — (G1) |

Not gated (`_not_gated`; skipped under the flag, as are the families with no surviving item):

| family | reason |
|---|---|
| hallucination | an invention rate over free generation, no item answer to invert |
| jlens_concept_pr | precision against the J-lens top-10, not a bar a lens clears |
| agentic_misalignment | a pair-scored design family: the null is the clean twin and the prompt-only floor, with no per-item answer to text-invert |
| multi_concept_directed_modulation | the prompt dictates the concepts; prompt-only is 1.0 |
| directed_modulation | the instruction states the concept; items survived only because the scorer discounts instruction narration, not because the answer is hidden (Camila 2026-10-24) |
| typo | excluded from the ATI subset by design (Camila 2026-10-29) |
| typo_mt | excluded from the ATI subset by design (Camila 2026-10-30: "This should not be in ati"; plan 0033 M4) |

**Reading it.** Opus 5.5 recovers the answer from the text alone on most items of most families:
its per-draw prompt-only rate is far above the stock-Qwen prompt-only floor (association 0.95
against 0.32). The survivors are mostly model-specific labels (wrong_bridge, where Opus recalls
the true fact but the target is Qwen's wrong bridge; basic_readout's preference items, such as
the favourite chess piece) and poetry's planned rhyme word. Some are scorer technicalities
rather than ignorance: Opus names the concept but not in a form the regex contract credits
(multilingual_mt), or describes a scene without naming the target (association). The subset is
"fails the family's scorer", the same bar a lens faces, not "Opus has no idea".

```
wsbench text-inversion stage=build                 # prompts (tokenizer only)
wsbench text-inversion stage=ask                   # 3 Opus draws; ANTHROPIC_API_KEY unset -> ant profile
wsbench text-inversion stage=readouts
wsbench run families=<gated> readouts_root=outputs/baselines/text_inversion/readouts/draw<d> \
    out=outputs/baselines/text_inversion/judged/draw<d> judge_model=claude-opus-5-5 layers=44 allow_missing=True \
    opts=aggregate=native              # the gate reads native verdicts (plan 0024)
wsbench run families=buggy_code ... judge_model=claude-opus-5-5 allow_missing=True opts=aggregate=native   # native layers
wsbench text-inversion stage=gate                  # -> this file
wsbench run all=True readouts_root=DIR out=DIR anti_text_inversion=True
```

Under the flag each gated family's `items` is its subset and `results.json` carries
`config.scope = "anti_text_inversion"` and `extras.ati_n_bank`; the subset alone does not make
a run incomplete. A family whose current judge `prompt_version` differs from the entry's
`instrument` fails (exit 2) until re-gated. `report` leaves out the floor columns under this
scope (they were measured on the full banks) and the macro skips families with fewer than 20
items: with the current subset the macro is the mean of wrong_bridge, poetry,
arithmetic_intermediates, moral_rationale, user_modeling and conjunctive_association alone, so read the per-family rows. The Opus judge runs at T=1, so a fresh judge pass over the same answers can flip
an occasional verdict: a smoke re-judge of draw 0 before the final gate passed 1 of 76 wrong_bridge
and 1 of 22 poetry items; on the final subset a fresh re-judge passed none.

**The four model-specific families (plan 0016, 2026-10-24).** Gated under `framing=open_model`,
Opus 5.5 first and Sonnet 5.5 for a family Opus refuses on more than 20% of items:

- **introspection: 123/125 headline items kept by this first gate** (superseded: the panel-v1
  gate below keeps 125/125; plan 0045's bank v2 re-judges that entry at gpu R8, visible text
  unchanged). The 125 headline items share ONE
  byte-identical prompt (the visible text never shows the injection), so the 374 usable Opus answers are
  draws of one question; Opus names the gold on 0.8% of draws (one item). The family is
  text-inversion-bounded by construction (a text reader is capped near 1/5 within a cluster);
  the gate removes only what Opus happens to name.
- **model_specific_directed_modulation (then directed_modulation_obscure): 25/98 kept.** Asked what the model is thinking about while it copies the
  carrier, Opus lists several plausible favourites, and the scorer of record (gold hits any
  sample) credits the gold whenever it is among them (pass@1 0.64). The kept items are the ones
  whose favourite Opus never lists.
- **knowledge_cutoff: gated at construction, whole bank in the subset.** This gate's prompt is
  refused on too many of its items (`reasoning_extraction`, 25% under Opus, 24% under Sonnet),
  but its bank was text-inversion gated when the items were selected (Camila, 2026-10-24: "i
  gated them when i selected the eval questions"): every bank item already failed Opus 5.5 ×3 and
  Sonnet 5.5 prompt-only readers (G1, recall and MC, informed and plain framings) in the source
  repo. `CONSTRUCTION_GATED` in `text_inversion.py` records this; its entry has `answerer:
  "construction"`, carries all bank ids, and is never asked about again (re-stamped with the
  judge instrument `cutoff-judge-2026-10-26` by plan 0017).
- **ttt was removed** from the bench and from this subset on 2026-10-26 (plan 0017, #97): too
  close to next-token prediction.

Not-in-macro families keep their `not_in_macro` exclusion under `anti_text_inversion=True` too.

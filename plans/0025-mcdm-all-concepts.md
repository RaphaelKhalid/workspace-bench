# 0025: multi_concept_directed_modulation — every concept, as content, on a 100-item bank

Camila, 2026-10-29: "require all of the concepts, do the content vs instruction distinction" and
"increase the size of mcdm - it should be around 100 prompts too". Context: the audit found the
family's 0.80 (s3d, native) sat at or below its rule-matched floor — the old pass rule (some cell
names ANY one dictated concept, multi-select over 6 options, no narration screen) is met by a
guesser shown only the option lists 83% of the time (`any_hit`), while plain
`directed_modulation` (one concept, content-vs-narration screen) scores 0.41 over floors of
0.16–0.19.

## 1. Pass rule: all dictated concepts, each engaged as content

- **Judge output.** Each pick gains `basis`, one of `content_bound` | `instruction_narration` |
  `incidental` (the DM vocabulary, `directed_modulation/prompts.py`, minus `absent`, which a
  multi-select pick cannot be). Schema: `picks[].{choice, quote, basis}`.
- **Credit.** A pick credits a dictated concept only when its letter is valid, its quote is
  verbatim in the readout (native) / inside one of the digest's evidence samples (summary;
  `digest.gate_texts` — retained as is), AND `basis == "content_bound"`. A dictated concept
  picked with another basis is recorded (`narrated`, `incidental`) but never credited.
- **Item rule.** An item passes when the union of its credited dictated concepts covers EVERY
  dictated concept: over all its in-sentence (layer, position) cells in native mode, inside its
  one digest call in summary mode. Undecided exactly as today (`tri_state`): no pass and any
  cell unjudged / missing / unsummarized; controls, off-task and no-readout items keep their
  reasons. The region labels and write-compliance gate are retained unchanged.
- **Binding items** have one dictated concept (the directed relation), so "all" is that one
  concept, credited only as content and only in the stated direction (the judge's existing
  direction rule is retained). **Changed after review (the lucky floor measured 0.66 on
  one-concept items by picking both directions):** a call that also names the item's binding
  partner — the reversed relation, or the other fox item's concepts — credits none of the
  item's concepts (`direction_conflict`), whatever the partner pick's basis, and an item whose
  readouts name the partner as content in ANY cell does not pass (item level, so ab at one layer
  and ba at another fails too); the lucky floor
  applies the same rule (picks including a partner never pass) and its analytic floor becomes
  C(n-k-p, 3-k)/C(n, 3). `partner_confusion_rate` is unchanged (any verified partner pick).
  A call naming more than three distinct candidates is `over_selected` and credits nothing (the
  lucky floor keeps a guesser's first three picks instead; documented).
- **The judge stays gold-blind about WHICH options were dictated.** It never sees the item's
  instruction (unchanged), but SYSTEM now shows the instruction FORMAT with the slots blanked
  (`Think about ___. Now write this sentence: "___"`), so a decoded echo of an instruction is
  recognisable as narration; this reveals nothing about which of the six options are dictated. Unlike DM, whose
  judge sees the instruction so it can spot narration of a NEGATIVE instruction, every MCDM
  item is positive ("Think about X"), and narration is recognisable from the readout's own
  framing ("I was asked to think about…", "the instruction mentions…", "I will keep X in mind
  while writing"). Showing the instruction would tell the judge which of the six options are
  dictated. The new SYSTEM text defines the three bases with MCDM-specific examples, plus a
  **token-list clause** (the DM `READOUT_BUNDLE_NOTE` analogue): in a readout that is a list of
  top-k tokens (or a digest evidence line that is one), a whole-word hit counts as
  `content_bound` unless it sits inside an echo of the instruction — `incidental` is reserved for
  prose that mentions the concept inside an unrelated enumeration or template.
- **Per-pick bookkeeping.** A pick whose `basis` is missing or outside the enum counts in
  `n_invalid` and never credits. Each judged cell records `own` (credited), `uncredited`
  (dictated, not content; split into `narrated` / `incidental`), `false` (other candidates, any
  basis), `basis_of` and `credited_quotes`. `kind`: `hit` (some credited pick) / `uncredited`
  (dictated picks, none as content) / `false_pick` / `none` / `invalid` / `unavailable`.
- **Multi-word candidates.** SYSTEM says one distinctive content word of a multi-word candidate
  names it when it can only mean that candidate here (the bank's no-shared-content-word rule
  makes that safe), so `pirate` alone can credit `pirate ship` in a token list.
- **Where the token-list clause applies.** Native token cells are first rewritten to prose by
  the shared summarizer (unchanged), so the clause matters for summary-mode digest evidence
  lines that are token lists; it is harmless elsewhere.
- **How basis feeds the other numbers.** `own`, `kind == "hit"`, capacity and the summary-mode
  retained-quote set use CREDITED (content-bound) dictated picks only. `false_pick_rate`,
  `control_pick_rate` and `partner_confusion_rate` count any verified pick whatever its basis
  (a narrated partner pick is still a confusion), with `extras.picks_by_basis` breaking every
  verified pick down by {dictated, partner, other} x basis.
- **Prompt version** `mcdm-2026-09-16` -> `mcdm-2026-10-29` (SYSTEM, USER and schema change).
- **Extras** (`extras`, not the headline): `any_concept_rate` (>= 1 concept credited — the old
  rule with the narration screen), `concept_recall` (mean share of an item's concepts
  credited), `all_in_one_cell_rate` (native only: some single (layer, position) readout
  credits every concept),
  `narration_rate` (share of dictated-concept picks rejected as `instruction_narration`),
  `incidental_rate`, `per_n_concepts` (pass rate by 1 / 2 / 3 dictated concepts), and the
  existing `false_pick_rate`, `control_pick_rate`, `partner_confusion_rate`, `per_stratum`,
  `capacity` (capacity now counts credited concepts only).

## 2. Bank: 27 -> 100 items

The 27 existing items keep their names, prompts and strata. **Three bare-word concepts are
removed from their items' `concepts`** (the prompts are unchanged): `floating` (d-violin),
`seven` (d-cranes) and `chasing` (d-fox-a, d-fox-b). Under an all-concepts rule a bare
number / verb / participle is a near-impossible, mostly incidental unit, so keeping them would
fail those items for a bank flaw; the fox pair's binding survives (`silver fox`/`paper kite` vs
`paper fox`/`silver kite`). d-violin and d-cranes become 2-concept items (stratum kept). The
header records the edit (`concept_edits`). 73 items are added,
all with the bank's `head_template` and `target_sentence` (unchanged), so the render, read cells
(12 sentence tokens) and layers (44/52/56/60) are unchanged.

| stratum | concepts | existing | new | total |
|---|---|---|---|---|
| `single` (new) | 1 | 0 | 22 | 22 |
| `double` (new) | 2 | 0 | 19 | 19 |
| `novel` | 3 (2 for d-violin, d-cranes) | 4 | 16 | 20 |
| `anchor` / `chain` / `pair` | 2 / 3 / 3 | 1 / 2 / 2 | 0 | 5 |
| `mix` (binding, ab/ba, mixed-gender names) | 1 | 8 | 8 | 16 |
| `same` (binding, ab/ba, same-gender names) | 1 | 8 | 8 | 16 |
| `control` | 0 | 2 | 0 | 2 |
| **total** | | **27** | **73** | **100** |

Authoring rules for the 73 NEW concepts (checked by a test over a frozen list of the new item
names; the 27 originals predate the rules — e.g. the binding pairs reuse Adam and the debt pair
says "money" — and are exempt; words shared inside one binding pair are exempt; "content word"
= alphabetic tokens minus a stopword list that includes `being`):
- concrete and specific; multi-word phrases preferred; no bare numbers, colours, generic verbs
  or adjectives on their own (the audit's "seven" / "floating" / "chasing" problem);
- nothing from the target sentence's domain (committee, meeting, Thursday or any weekday,
  review, annual, budget, money, finance, calendar);
- unique across the bank: no concept string repeats and no content word is shared between two
  items' concepts (distractors come from other items' concepts, so overlap would make a
  distractor partly correct);
- binding pairs: new relations (not anger / jealousy / fear / pride / debt / trust), each pair's
  two names used by no other item; `mix` pairs mix genders, `same` pairs do not; each pair gets
  the `emotion` and `order` fields the existing pairs carry.
- No behavioural gate is needed: the sentence is prefilled, so the family's only gate
  (compliance: the model writes the dictated sentence) holds by construction for every item.
  The family stays out of the ATI subset (`text_inversion.NOT_GATED`: the prompt dictates the
  concepts).

The bank header gains `expanded: "2026-10-29 (plan 0025): 27 -> 100 items"`; `source` keeps
naming the original 27.

## 3. Options, floors, adapted banks

- `options.option_sets` is unchanged in code, but its pool grows, so every item's distractors
  change; `tests/golden/multi_concept_directed_modulation_options.json` is regenerated
  (sanctioned).
- **Lucky guessing.** The floor follows the new rule: for this family `correct = all_hit` (the
  picks include every dictated concept), which `majority_correct` / `aggregate` then read;
  `any_hit`, `exact`, `mean_picks` stay as extras, plus `by_n_concepts` (1 / 2 / 3; on 1-concept
  items all = any). The seeded-uniform variant draws 3 picks (the judge's mean is ~2.3), and
  its `analytic_floor` becomes the mean over items of C(n-k, 3-k)/C(n, 3) (n options, k
  dictated). Re-measured under the default judge (Opus 5.5) and frozen at the new instrument; the
  old entry is stale by instrument and stops being drawn. Sanctioned test edits:
  `tests/test_lucky_guessing.py` lines asserting the MCDM item count (25 -> 98 decided), the
  first-pick / k/n floor values, and the uniform single pick.
- **Prompt-only** stays excluded (the prompt dictates the concepts).
- **Adapted banks** (`adapted/<model>/multi_concept_directed_modulation.json`, made by
  `wsbench.adapt.carry.mcdm`) are re-carried from the new bank for every adapted model
  (tokenizer-only; no model calls; run on this box with the HF cache, `hf` login for gated
  tokenizers), and each model's `report.json` is regenerated by the tool, never hand-edited. The
  27-item counts in `adapted/*/AUDIT.md` / `SET_AUDIT.md` / `adapted/*/README.md` get a dated
  note ("MCDM re-carried at 100 items, plan 0025"), not a rewrite of the audit.
- **Summary mode.** `FAMILY_DEFAULTS` are unchanged: with at most 3 concepts the default
  `summ_max` keeps every concept line; the digest's "restatement at most one item" rule only
  folds narration, which the new screen rejects anyway. Retained invariants: the digest is
  gold-blind, `digest.gate_texts` gates quotes.

## 4. Tests, docs

- `scripts/summary_mode_compare.py` `_mcdm_hits` / `retained` read the cell's
  `credited_quotes` (the quotes of credited picks) instead of every pick quote of a hit cell.
- Bank invariant test also guards name suffixes: only the binding pairs and `d-fox-a`/`d-fox-b`
  may end in `-a` / `-b` / `-ab` / `-ba` (`options.partner_of` pairs by suffix).
- Further sanctioned edits: `tests/test_multi_concept_directed_modulation.py`'s
  `n_items_without_readouts` count (24 -> 97 for the 3-item toy), `atlas/build.py`'s family
  description, and the root README example ("and", not "or").
- Re-carry with `python -m wsbench.adapt carry model=<m> families=multi_concept_directed_modulation`
  (the default also re-carries jailbreak_recognition, which this plan does not touch).

- Pre-existing MCDM tests that assert the any-concept pass, the old schema or the old option
  lists are updated to the new rule — and only those (each such edit restates which rule of §1
  it follows). New tests: all-concepts union across cells; a narrated or incidental dictated
  pick never credits; a missing concept fails even with others content-bound; summary mode
  requires all concepts in the one digest call; bank invariants of §2; lucky `all_hit`.
- README (family): counts, strata, the new rule, the blind-basis rationale, the concept edits;
  `evals/baselines/README.md` lucky table row; the root README entry's *Judged by* line and the
  §Judges prompt-version table row (`mcdm-2026-09-16` -> `mcdm-2026-10-29`).

## 5. After merge (not this PR)

The cached readouts cover the 27 old items only. Produce s3d-rl600 O-lens (and J-lens)
readouts for all 100 items on Modal, judge them under the default (summary) and native modes,
and update the audit page's saturation table.

## Checks
`ruff check .`, `ruff format --check .`, `pytest -q`; `wsbench judge
family=multi_concept_directed_modulation dry_run=True` on a fixture renders the new prompt;
`wsbench list` shows 100 items.

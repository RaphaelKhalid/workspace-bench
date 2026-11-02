# Bank schema, per family

Every bank lives at `evals/<family>/items.json`. Copy the frozen bank's first item as your
template; this file says what every field means and which ones the code reads. "Read by" names
the consumer: **plan** = `wsbench.readplan` (render + read sites), **judge** = the family's
scorer, **capable** = `wsbench.capable.questions` (the capability question), **gate** = the
authoring gate (provenance only, never read at scoring).

## Shapes and ids

- **Bare list** (items carry `id`): `conjunctive_association`, `moral_rationale`,
  `relational_multihop`, `role_bound_association`.
- **Wrapped** `{<header keys>..., "items": [...]}` (items carry `name`; the loader sets
  `id = label_of(name)`, every character outside `[A-Za-z0-9._-]` -> `_`; two names with the
  same label are a load error): every other family.
- The readout file's `id` must equal that label. Keep names ASCII, lowercase, hyphenated and
  prefixed by family and wave (`mhh-w2-...`, `chain-w2-d3p-0001`), and never reuse a frozen id.

## Shared single-token fields (association, basic_readout, multihop, multilingual, poetry, typo)

| field | meaning | read by |
|---|---|---|
| `name` | unique id | all |
| `prompt` | the text, rendered verbatim with no chat template (`eval_render: "plain"`) | plan, capable |
| `target` | the surface answer (multihop: the next word; multilingual: the L2 word) | capable (gold) |
| `target_alts` (optional, multihop) | other accepted surface answers ("pound sterling" for "pound"); capable adds them to the gate golds | capable (gold) |
| `intermediates` | the scored latent(s): multihop's bridge, multilingual's English gloss, poetry's rhyme word, typo's correction, association's referent | judge (targets), capable when no `target` |
| `units` (basic_readout) | `[{"role":"readout","lang":"en","headline":true,"match":[...]}]`; `match` lists accepted spellings and wins over `intermediates` | judge |
| `reference_concepts` (multilingual) | `[language, topic words]`, provenance | - |
| `readout` | `{"kind":"final_prompt_token","offsets":[-1]}`; multihop `{"kind":"last_word_token","offsets":[-1 or -2]}` (offset of the last NON-whitespace token from the end of the subject tokenization); poetry `{"kind":"line_one_newline"}` | plan |
| `eval_render` | `plain` (basic_readout implicit: `chat`, rendered with the prefill `My one-word answer is:`) | plan |
| `subfamily` (basic_readout) | `entity` / `processing` / `implicit` | capable (implicit skipped), gate |
| `consistency`, `gate_variant`, `source` | sampled pass rate, how it was gated, where it came from | provenance |

The judge's targets are `units[headline].match` (else all units' `match`), then
`intermediates`, then `target` only if nothing else names the concept; a target that is a
word-sequence component of a longer sibling ("moon" beside "full moon") is dropped. The judge
accepts the exact word, an inflection, an established synonym/alias or a faithful translation,
with a verbatim quote from ONE sample. So list the canonical concept, not every paraphrase;
add `units.match` only for genuinely ambiguous surface forms (`Boxing`/`boxing`).

## Multi-token families (basic_readout_mt, multihop_mt_v2, multilingual_mt, typo_mt, multilingual_multihop, multilingual_typo)

Header (all required): `family` (the source name: `basic-readout-hard`, `multihop-hard`,
`multilingual-hard`, `typo-hard`, `multilingual-multihop`, `multilingual-typo`; keep it, the
legacy fallback keys on it), `parent_family`, `contract`, `gate`, `frozen` (ISO date).

```json
"contract": {"multi_token": true, "include_target": false, "conjunctive_units": true}
```
`include_target` is `true` only for multihop_mt_v2. Copy the frozen bank's block unchanged.

| field | meaning | read by |
|---|---|---|
| `name`, `subfamily` | id; `entity`/`l2_factual` (basic_readout_mt), `2hop`/`3hop` (multihop_mt_v2, multilingual_multihop), `fwd` (multilingual_mt), `novel`/`realword`/`arith` (typo_mt), `typo` (multilingual_typo) | all; quotas |
| `prompt` | plain-text fragment ending IMMEDIATELY before the answer (no trailing space or punctuation; typo families end WITH the misspelling) | plan, capable |
| `target`, `target_alts` | the next-token answer and its inflections; gate golds; a scored optional unit only under `include_target` | capable, judge (multihop_mt_v2) |
| `lang` | L2 code, one of `pl tr fi hu id vi sw ru el he ar ko` (the MC language confusables exist only for these) | judge (MC), plan |
| `typo_word` | the misspelled last word | gate, lint |
| `intermediates` | the headline latent, for display | - |
| `units` | the scored units, see below | judge |
| `bridges` (multihop_mt_v2, multilingual_multihop) | `[{"question": <English question whose answer is the bridge>, "units": [<roles>], "answers": [<every short way to name it>]}]`; GATE-ONLY | capable (bridge legs) |
| `probe_token_lens` | `{"units": {role: {lang: [count per form]}}, "target": n, "target_alts": [n...]}` (target_alts only under include_target); aligned position by position with `forms[lang]` | judge |
| `mc` | `{role: {"gold": <first en form>, "distractors": [4 names]}}` per required non-language unit (absent in the typo families) | judge (`opts=judge=mc`), lucky-guessing floor |
| `readout` | `{"kind":"final_prompt_token","offsets":[-1]}` | plan |
| `eval_render` | `plain` | plan |
| `consistency`, `consistency_strict`, `consistency_greedy`, `bridge_consistency`, `gate_variant`, `source` | gate record | capable (reference rate) |

A unit:
```json
{"role": "bridge1", "required": true, "multi_token": true,
 "forms": {"en": ["Simula 67", "the Simula language"]},
 "match": ["Simula 67", "the Simula language"]}
```
- `forms` is an authored OR-list per language (`en`, `zh`, and the L2 code where the family
  allows it); `match` = the flattened forms (lint requires equality with the sorted flatten).
- Roles per family: basic_readout_mt `readout` (+ `language` on l2_factual; the L2 answer is the
  next token, so `readout` lists only `en`/`zh` there); multihop_mt_v2 `bridge1` (+ `bridge2` on
  3hop), `en` only (the bank-of-record `items_v2.json` adds `name_forms` per native language,
  zh included, in `scripts/build_mh2_bank_v2.py`); multilingual_mt `concept` {en, zh} + `language`; typo_mt `correction` {en};
  multilingual_multihop `bridge_l2` (required false) + `bridge_native` {en, zh} (required) +
  `language` (required false); multilingual_typo `correction` {L2, en, zh} + `language`.
- `language` unit: `"multi_token": false`; forms `{"en": ["Arabic"], "zh": ["阿拉伯语"],
  "<L2>": [...]}` where `<L2>` is the L2 TARGET and its inflections in multilingual_mt,
  multilingual_typo and basic_readout_mt l2_factual (all frozen items, e.g. `"ar":
  ["الساعة الرملية", "ساعة رملية"]`), and how the language names itself in
  multilingual_multihop (`"ar": ["العربية", "بالعربية"]`).

## Computational

**arithmetic_intermediates** (header: `family`, `source`, `variants` {variant: {shape, tolerance,
cell, role, n_items}}, `read`). Item: `variant`, `expr`, `first_op`, `first_value`,
`intermediates` (every scored step as a string; `intermediates[0]` is the headline the judge
scores), `answer`, `operands`, `single_token_reachable`, `name`, `pair` (twin name or null; `gen_deterministic.py` writes it on every item, null for non-twin variants and for a twin whose partner was not requested; the frozen bank omits it on non-twin variants, which loads the same),
`prompt` = `Compute {expr}. Reply with only the final number, nothing else.`, `null_set` (names
of same-variant items in THIS bank used as the permutation null), `tolerance` (`exact` or
`rel5pct`), `cell` {layer, pos} (the variant's pre-registered frozen cell), `role`
(`structural` | `comparison`), optional gate fields (`gate_correct`, `gate_greedy_ok`, ...).

**chain_intermediates** (header: `family`, `gate`, `n`, `selection`, `source`, `read`). Item:
`depth` (2 or 3), `cond` (false), `kinds`, `steps`, `start`, `intermediates` (ints),
`untaken` (null per slot), `answer`, `prompt` (start number LAST: the read window is after the
seed), `prompt_first`, `literals` (every numeral of both prompts), `distractors` (4 per
intermediate slot), `name`, `gate` {last, first}.

**buggy_code** (header: `family`, `source`, `read_cells` {python: {anchor, layer: 60},
nonpython: {anchor, layer: 56}}, `read`, `removed`). Buggy item: `src: "buggy"`, `name`,
`kind`, `code`, `category`, `cause`, `level2_tokens`, `bug_line`, `raises`, `language`,
`difficulty`, `failure_mode` (silent|raising), `verified` (`exec: exit 0; stdout = '...'` or
`exec: exit 1; stdout = ''; last = 'ValueError: ...'`, copied from a real run), `n_lines`,
`gate_tier`, `consequence_class` (categorical|value|crash), `lang_group` (python|nonpython),
add `twin` (the clean twin's name). Clean twin: `src: "clean"`, `name`, `code`, `language`,
`verified`, `lang_group`.

## Association and logic (MC-judged)

**conjunctive_association** (bare list). `id` (`q11_a`), `cluster`, `level`, `anchor`,
`varied_axes` (two), `cell` {state_type, state, relation, content}, `stimulus` (the vignette),
`read_position`, `inferable_from`, `gold_label`, `mc_options` (the 10 gold labels of the
cluster's 10 cells, FROZEN; the judge shuffles), `asked_question`, `contrast_label` (the
sibling cell flipped on the binary axis; must be one of the options), `contrast_axis`,
`credit` {axis: [[slot variants]...]}, `competitors`, `scored_axes`, `axis_concepts`,
`blocklist` {block, warn}, `qa` {lemma_scan, opus_gate}, `provenance` {generator, date,
style, edits}. The judge reads `gold_label`, `contrast_label`, `mc_options`; capable reads
`stimulus`, `asked_question`, `gold_label`.

**role_bound_association** (bare list). `id` (`oa-<sid>-ab|ba`), `pair_id` (shared by the
two directions), `tier` (A: roles blocked; B: roles and action blocked), `direction`
(`ab`|`ba`), `stereotypicality` (congruent|incongruent|neutral), `role_a`, `role_b`, `action`
(past tense), `names` {a, b}, `stimulus`, `read_position`, `gold_label` (`the <subject role>
<action> the <object role>`), `contrast_label` (roles swapped), `asked_question`,
`mc_options` ([gold, contrast]), `blocklist` {roles, action}, `generator`, `qa`. The judge
builds agent/patient options as "Name, the role" from this item plus 3 people of OTHER pairs,
and 4 other actions of the bank.

**relational_multihop** (bare list). `id` (`rel-sNN-a|b`), `scene`, `stimulus` =
`"{p1}'s {r1} is {p2}. {p2}'s {r2} is {p3}. In other words, {p3} is {p1}'s"` (ends on the
possessive `'s`, the read site), `names`, `hop1` (outer), `hop2` (inner), `gold`
(`"{r1}'s {r2}"`), `gold_alt` (`"{r2} of {p1}'s {r1}"`), `flipped` (`"{r2}'s {r1}"`). The `-b`
item swaps the hops of the `-a` item.

**moral_rationale** (bare list). `id` (`ec-<key>-chat_tf|chat_yn`), `topic_id`, `topic`,
`domain`, `variant`, `render: "chat"`, `answer_format` (true_false|yes_no), `statement`,
`question`, `stimulus` (statement + ` Answer with true or false only, one word.` or question
+ ` Answer with yes or no only.`), `read_position`, `hypothesized_reason` (design hint, never
scored), `reason_class` (committed|deliberative), `reasons` [{text, supports: yes|no, terms,
frequency}], `gold_reasons`, `gold_terms`, `look_for_reasons` (committed: `[reasons[0].text]`;
deliberative: exactly two, one yes-side and one no-side), `must_surface_both`, `answer_split`,
`commit_answer`, `commit_direction`, `commit_precise`, `gate_committed_token`,
`gate_aligned`, `gate_pass`.

**user_modeling** (wrapped). `name`, `subfamily` (selfdescribe|synthsys), `attr_class`
(Country, Gender, ...), `attr` (lower-case value), `attr_label`, `messages` [system, user],
`target`, `intermediates`, `units`, `consistency`, `source`, `gate_variant`, `eval_render:
"chat_context"`, `readout`. Distractors are 4 other `attr` values of the same `attr_class` in
the bank.

**directed_modulation** (wrapped). `name`, `subfamily` (pair|secret|preference), `pair_id`,
`polarity` (think|dont), `concept`, `carrier` (dry sentence the model copies), `prompt`,
`assistant` (= carrier, teacher-forced), `units` (concept headline + category), `answer`
{accepted: [carrier]}, `base_rate_per_100k`, `consistency`, `source`, `gate_variant`,
`eval_render: "chat_dm"`, `readout` {kind: writing_positions}. Distractors: 4 other concepts of
the same subfamily.

**multi_concept_directed_modulation** (header: `family`, `head_template`, `control_template`,
`target_sentence`, `render`, `read_cells`, `layers`). Item: `name`, `prompt`
(`Think about <concepts>. Now write this sentence: "<target_sentence>"\n`), `concepts`,
`stratum` (control|novel|anchor|chain|pair|mix|same) plus stratum fields (`order_gt`,
`binding`, `emotion`, `order`).

## Provenance (add to every new item and header)

- item: `source` (e.g. `"authored:claude-opus-5 2026-10-12 wave w2"` or
  `"gen_deterministic.py seed=3 tag=w2"`), the gate record (`consistency`,
  `consistency_greedy`, `bridge_consistency`, `gate_variant`), and for LLM-authored latent
  items the `generator` / `provenance` block the frozen bank uses.
- header: `gate` (one sentence: subject model, render, greedy + k rule), `frozen` (date), and
  a `source` line naming the generator/authoring model and this skill's scripts.

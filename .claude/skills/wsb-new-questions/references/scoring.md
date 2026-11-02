# How items are scored, and what a new item must do not to break it

Source of truth: `evals/<family>/README.md` (read regime, pass rule, judge prompts verbatim)
and the code under `src/wsbench/`. This page is the authoring-side summary.

## The grid and any-of-grid

A lens is read at a set of **cells** = (item, layer, position). Every headline is
**any-of-grid**: an item passes when ANY judged cell (or layer, for the per-layer families)
passes. Consequences for authoring:

- More read sites = more chances to pass by luck. Never draw a **per-call** chance (1/6 for one
  6-way MC) beside an any-of-grid rate: over `n` independent sites the floor is
  `1 - (1 - p)^n` (relational's 1/121 per call becomes 4.9% over 6 layers; conjunctive's 1/11
  becomes about 0.44 over its grid). Over a large grid that formula saturates near 1 and is
  meaningless too, because a real guesser is deterministic. The honest floors are the MEASURED
  ones: the lucky-guessing baseline (the judge shown only the option lists) and the prompt-only
  baseline (the stock model given the prompt, no activation), `evals/baselines/`, drawn by
  `wsbench report` only while their `prompt_version` stamp matches. A new bank needs them
  re-measured (`wsbench baseline`, a prompt-only arm, `wsbench freeze`).
- Prefer a null the family computes itself: arithmetic's permutation over `null_set`, chain's
  magnitude-matched decoys, buggy_code's clean twins,
  conjunctive's contrast sibling, role-bound's reversed direction. New items must keep those
  controls intact (twins kept together, null sets pointing inside the bank).

## Families by scorer

### Regex contract (no LLM): the six multi-token families

`src/wsbench/multitoken/regex.py`. Per item:

1. `contract_for(header)` reads `{multi_token, include_target, conjunctive_units}` from the
   header `contract` block (fallback without it: `multi_token = family.endswith("-mt")`,
   `include_target = family != "multilingual-mt"`, `conjunctive_units = False`).
2. `scored_units`: under `multi_token`, each unit with `multi_token != false` keeps only forms
   whose `probe_token_lens` count is > 1. A REQUIRED unit left with no form makes the whole run
   fail ("bank violates its own contract"). `include_target` adds an optional `target` unit.
3. A form hits ONE sample (never assembled across samples or tokens), after folding both sides
   (NFKD, combining marks dropped, curly apostrophe straightened, casefold): CJK/Hangul or
   non-word forms are substrings; word forms are word-boundary matches with `[\s-]+` between
   words (`Bohr magneton` == `Bohr-magneton`); purely numeric forms only count in answer
   position (`= 47`, `answer is 47`, at the start of the sample).
4. A layer passes when EVERY required unit hits some sample at that layer; the item passes at
   any layer. `any_hit` is reported beside it.
5. Token-bag readouts are matched as raw tokens (each token one sample; the per-cell summarizer
   step was deleted in plan 0032 §2.3); under summary mode (the default) every method goes
   through the one digest and the contract runs on its evidence samples.

So a new multi-token item must: list every acceptable surface form (inflections, with and
without the article, transliterations) because matching is exact after folding; keep every
form genuinely multi-token for the subject's tokenizer; never let a form appear in the prompt
(it would be read off the echo); and keep `language` forms distinct from the target.
`validate_bank.py` scores a perfect dummy readout (one sample per required unit) at 1.0 and an
unrelated one at 0.0 through the real scorer.

The MC judge (`opts=judge=mc`, diagnostic only) asks one 6-way question per (item, layer,
unit): `mc[role]` gold + 4 distractors + "cannot tell"; the language unit uses the fixed
`LANG_CONFUSABLES` table, so `lang` must be one of its 12 codes. Items without an `mc` block for
a role fall back to 4 golds of other items, which needs at least 5 items per role.

### The bank judge: association, basic_readout, multihop, multilingual, poetry, typo

`src/wsbench/basic/`. One call per (item, layer) with every position's samples; pass = a target
concept NAMED (exact word, inflection, established synonym/alias, faithful translation) with a
verbatim quote verified against ONE sample; derived words ("blackout" for "black"), fragments,
hypernyms and thematic imagery do not count. Item passes at any layer. Floor: prompt-only.
Authoring consequence: the target must be the precise concept; because translations count, the
prompt must not contain the target in ANY language (the multilingual family's English gloss is
the target and the L2 word is the answer, so the gloss must not be a cognate of the L2 word).

### Free recall: chain_intermediates, arithmetic_intermediates

Prompt-blind judge names the values the readout presents as computed (at most three), each
verified against the readout's own numerals; pass = a named value within tolerance of the
intermediate (`exact`, or relative 5%, sign-aware). Chain reads the last token of the chat
render (opts=cells=all: the question span); arithmetic reads every position at the 11 grid layers
(`reads=lite`: layers 56/60) and keeps each variant's frozen `cell`. Nulls: arithmetic `cross` = the
same rule against the intermediates of the item's `null_set`; chain = magnitude-matched decoys.
Authoring consequence: no intermediate may be a numeral of the prompt (else the readout echoes
it); `null_set` must name items of the same variant in the same bank, separated from the item's
own value by more than the tolerance; `cell` must be the variant's.

### MC families with options built from the bank

| family | per call | options | built from |
|---|---|---|---|
| conjunctive_association | 11-way | the item's 10 frozen `mc_options` (shuffled) + cannot tell | the item |
| role_bound_association | three 6-way (agent, action, patient), all correct | "Name, the role" for both scene people + 3 people of other pairs; the action + 4 other actions | the WHOLE bank |
| relational_multihop | two 11-way over one pooled list, both correct | both hops + 4 kinship + 4 professional distractors | bank relations + fixed near-miss extras |
| moral_rationale | 6-way (deliberative: two, both) | gold reason + 4 reasons of other topics (Jaccard-filtered) | the WHOLE bank |
| user_modeling | 6-way | gold + 4 values of the same `attr_class` | the WHOLE bank |
| directed_modulation | 6-way | gold + 4 concepts of the same subfamily | the WHOLE bank |

Authoring consequences: a new standalone bank must be big and varied enough for these pools
(see SKILL.md pitfalls); appending to a frozen bank changes existing items' options. Labels must
use the canonical role/relation words because they appear verbatim as options.

### Two-stage and narrative judges

buggy_code: a blind reader infers what the readouts claim, a grader holding the program, its
`verified` truth and the bug scores it 1-10; clean twins are graded against "no bug". Silent
floor about 2.96. multi_concept_directed_modulation: prompt-blind multi-select per write cell.
agentic_misalignment, jailbreak_recognition, jlens_concept_pr: not authored as
text (families.md).

## Things that make a scorer crash or silently mis-score

| symptom | cause |
|---|---|
| `bank violates its own contract` | a required unit has no form with `probe_token_lens` > 1, or counts misaligned with forms |
| `items X and Y share label` | two names equal after `label_of()` |
| relational `last read position ... is not the blank` | stimulus does not end with a token `'s` |
| `ValueError: Sample larger than population` (role_bound, user_modeling, DM, MT MC) | option pool too small in a small bank |
| `gold_label not in mc_options` | conjunctive/role_bound options edited by hand |
| every multihop cell reads a space | `readout.offsets` wrong for a prompt ending in a space |
| arithmetic null rate 0 | `null_set` names items not in this bank |
| all-zero family | missing readouts or a broken key, not a finding; check `n_unjudged_cells` |

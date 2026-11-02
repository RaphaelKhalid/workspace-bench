# Model-capability gating

A gate asks the subject model the item's own question and keeps the item only if the model
reliably computes the answer. It is what makes a lens miss interpretable: a lens that says
nothing about an intermediate the model never computed is not wrong. `scripts/gate_hf.py`
implements everything here for open-weights HF models; `wsbench capable` is the API-model
equivalent (OpenRouter, reasoning effort minimal, so it is not a raw continuation).

## 0. Native language (every subject, before any multilingual or multi-token bank)

Camila (2026-10-30): "determine the model's 'native language' in addition to english, e.g. qwen
thinks in chinese a lot so we should allow that as an option". The native languages are the
languages a family may accept a readout in besides English (e.g. the multilingual families'
intermediate "in English or the model's native language").

- **Sample** the subject with **thinking ON**, T=1.0, K=4, on 30 prompts of the family plus 20
  neutral English prompts (50 prompts, 200 thoughts).
- **Readouts:** if a prose reader exists for the subject, also take 10 read sites of its
  readouts (all samples at those sites).
- **Measure:** the share of thought LETTERS per language (script detection by
  `unicodedata` script name; CJK split zh / ja by `langid` on the run) and the share of readout
  samples per language.
- **Rule:** a language is native when it holds at least **10%** of thought letters or at least
  **10%** of readout samples. English always counts. Record the model card's stated languages
  beside the measurement, but the measurement decides.
- **Record** the list in the bank header as `contract.native_langs` (ISO 639-1 codes, English
  first). Readers use `wsbench.banks.native_langs(header)`, which defaults to `("en", "zh")` for
  the frozen Qwen3.6-27B banks. Nothing hard-codes "zh" or "Chinese".
- Re-run per subject model; never copy another model's list. Qwen3.6-27B: `["en", "zh"]`.
- `scripts/validate_bank.py` errors on a new multi-token bank whose `contract` lacks
  `native_langs`.

## 1. Render

- The subject's own chat template, one user turn holding the capability question,
  `add_generation_prompt=True`, **`enable_thinking=False`**, no system prompt. This is
  `wsbench.produce.render._chat`, the render the read plan uses.
- Answer stems (prefilled after the assistant header), as in the source gates: `My answer
  is:` for the multi-token tier, its bridge questions and relational; `My one-word answer is:`
  for the other free-answer families (and basic_readout implicit, where the leading-space
  whole word then sits at the answer site); none for arithmetic / chain (their prompt
  says "Reply with only the final number"). Override with `--answer-stem` ('' = none). A
  small model sometimes ends its turn right after the stem (empty answer): `gate_hf.py`
  re-asks that question without the stem and marks it `stem_dropped` in `gate.json`.
- **Plain variant** (poetry, multihop, multilingual, and the non-typo multi-token families
  multihop_mt_v2, multilingual_mt, multilingual_multihop, basic_readout_mt: every family read on a
  `plain` render except the typo ones, whose continuation is not the correction; for the
  multi-token families this departs from the frozen gate, which was chat-only, and
  `gate_variant` records it; bridge legs stay chat questions):
  each item is ALSO gated as a raw continuation of the bare prompt (no chat template, 8 new
  tokens; the gold must start the continuation or be a whole word among the first 4 words of
  its first line, so "Indian Rupee" passes for "rupee"; poetry: the first word of the first
  line is the own-rhyme candidate). The item passes if the chat OR the plain variant passes, every other leg
  included, and `gate_variant` records which ("plain" preferred, since it is the render the
  lens reads). This is how the frozen banks were gated (`gate_variant` plain for 56-80% of
  these items). Weak subjects often fail the chat ask (they restate the prompt, or answer
  "the") while continuing the raw text correctly.
- Stop at EOS, `<|im_end|>`, `<|endoftext|>` or the template's end-of-turn token; decode with
  special tokens skipped; strip.
- Never gate a reasoning model with thinking on and never on a raw `Human:/Assistant:` string:
  it emits `<think>` and you measure that token instead of the answer.

## 2. Questions (from `wsbench.capable.questions`, plus fixes)

| family | question | gold |
|---|---|---|
| association | `This text describes something it never names. Reply with the single word or short phrase that names it, and nothing else.` + prompt | referent |
| basic_readout, multihop, multilingual, poetry, *_mt (non-typo), relational | `Continue this text. Reply with the continuation only — the next word or short phrase, nothing else, no punctuation of your own.` + prompt | `target` + `target_alts` (else `intermediates`); relational: gold / gold_alt |
| typo, typo_mt, multilingual_typo | `The last word of this text is misspelled. Reply with that word spelled correctly, and nothing else.` | correction |
| multihop_mt_v2, multilingual_multihop bridges | `bridges[i].question` as-is | `bridges[i].answers` |
| arithmetic, chain | the bank prompt as-is | **`answer`** (capable uses `intermediates` here; that is a bug `gate_hf.py` fixes) |
| conjunctive, role_bound | stimulus + `Which option best describes what the text implies?` + lettered `mc_options` (seeded shuffle per id) + `Reply with the letter only.` | the gold's letter |
| directed_modulation | the prompt | compliance (copies the carrier, never names the concept) |
| user_modeling | the conversation + `Based on that conversation, what is the user's <label>?` | `attr` |
| buggy_code | code + `What happens when this program is run? State the output or the failure in one line.` | `verified` |
| moral_rationale | the stimulus | the side the subject commits to (golds elicited, families.md) |

The original 27B gates used family-specific templates (e.g. `Complete this text with the missing
final word or phrase: "<prompt>___"`, answer stem `My answer is:`); the per-model recipe below
uses the capability questions above for every subject, so rates are comparable across models.

## 3. Criterion

- **Greedy-correct AND >= 8 of K=10 samples** at temperature 0.7, top_p 1.0, max 96 new
  tokens (final-number families 32; MC 8; own-gold modes 16). `gate.json` records
  `truncated_greedy` / `truncated_samples` (no stop token within the budget): a truncated
  answer is graded on what was written, so read those before trusting a fail.
- **STRICT** (chain): greedy-correct AND 10/10 at T=0.8, top_p 0.95.
- **GREEDY_ONLY** (relational): greedy-correct, and both items of a scene.
- **No written intermediate** (arithmetic, chain): a rollout that states an
  intermediate (as a numeral) is a leak; one leaking rollout fails the
  item. Small models often answer with a worked chain (`a - b = x, x * c = y`), which looks
  correct to a final-number grader.
- Multi-leg items need EVERY leg (surface answer and every bridge; both arithmetic twins).
- Sample only questions whose greedy answer passed (saves 90% of compute on small models).
- An undecided grade (failed grader call) is a fail, never a pass.

## 4. Grading

1. **Deterministic first.** `anchored_match` (in `gate_hf.py`): fold (NFKD, casefold,
   combining marks dropped, every non-word run -> space), take the answer's SPAN = the first
   sentence of its first line with markdown bold removed, and accept a gold that occurs
   word-aligned inside that span. A gold that also occurs in the question (an echo, e.g.
   alias "Eiffel" for a question about the Eiffel Tower) counts only when the whole span is
   that gold. Plain containment over the whole answer passed a wrong verbose answer 10/10
   ("The Eiffel Tower was built by the Eiffel Tower Company ...") and counted asides
   ("While Pablo Picasso and Braque ...") after a wrong first sentence. For arithmetic and chain
   use the **sign-aware final-answer rule**: a numeric gold must equal the answer's LAST
   number with its sign (`-1386` != `1386`; `string_match` alone would accept it because the
   minus is punctuation); a word gold is a whole-word match.
   **L2 answers** (multilingual, multilingual_mt, multilingual_multihop, multilingual_typo
   surface legs): an answer that matches the item's English gloss (intermediates, the en forms
   of the concept / correction unit) and not the
   L2 target is a deterministic FAIL, never sent to the LLM grader ("three" for "drei"), and
   the grader prompt for these legs adds that a translation into another language is wrong.
   **Final-number families**: an answer whose only number is the first intermediate is
   recorded as `stopped` (it stopped after step 1), apart from a chain-of-thought `leak`;
   both fail. On a 4B per-model chain build, 57-63% of failures were `stopped` and only 2-3%
   true leaks: a weak subject mostly computes one step and answers it, so a wave dominated by
   `stopped` needs fewer steps (`--easy`), not a different prompt.
5. **Re-grading without re-decoding**: `gate_hf.py --reuse <earlier gate.json>` takes the
   decoded greedy answers and samples of every question whose id AND text are unchanged,
   re-grades everything with the current rules, and loads the model only if something new
   must be decoded (a grader fix, an added variant, new items). Use it after any change to
   grading, and to add waves cheaply.
2. **Optional LLM grader** for answers the string match rejects (`--grader <model>`), with the
   repo's grade prompt (`wsbench.capable.run.GRADE_SYSTEM`: same word or value, inflection,
   established synonym/alias, faithful translation, same quantity written differently; a longer
   answer containing it is correct; merely related is not). Memoize per (question, answer) and
   stop grading once the item is decided. Not used for the final-answer families.
3. **MC**: the first standalone option letter at the start of the answer.
4. Read 20 graded answers per family by eye before trusting the rate (small models wrap the
   answer in prose, repeat the prompt, or answer a different question).

## 5. Model-specific golds and re-stamping

- **poetry**: the subject's greedy first word must equal the first word of >= 8/10 samples and
  rhyme with line one's last word (CMU rhyming part, else the last two letters); it replaces
  `intermediates`.
- **basic_readout implicit**: majority first word under the answer-stem prefill (>= 8/10, greedy
  agreeing) becomes `target`, `intermediates`, `units[0].match`.
- **moral_rationale**: elicit -> distil -> commit (`scripts/moral_gate.py`; families.md); everything in `reasons`,
  `look_for_reasons`, `commit_*`, `gate_*` is per subject.
- **multi-token families**: re-stamp `probe_token_lens` with the SUBJECT's tokenizer (strict
  count: min over {form, lower, title} x {bare, leading space}); an item whose required
  multi-token unit keeps no form with count > 1 in some non-zh language is ineligible (dropped).
  Skip only if the subject provably shares the reference tokenizer (Qwen3.5 and Qwen3.6 do).
- **multihop**: `readout.offsets` = -2 if the subject's last prompt token is whitespace, else -1.
- **arithmetic**: prune `null_set` to surviving items, set `pair_survived`; the frozen `cell`
  is the 27B's pre-registered cell, so for another model report the every-position read
  (`opts=cells=all`) rather than the frozen cell.
- Stamp `consistency` (hits/K), `consistency_greedy`, `bridge_consistency`, and the header
  `gate` sentence naming the subject and the rule.

## 6. Out of capability, caps, equal counts

The recipe used for per-model banks (one bank per subject, every family at the frozen bank's
item count):

1. **Pool order**: frozen-bank items first (in bank order), then unused candidates the family's
   own generator produced, then newly authored candidates in the original style with the
   original guards. Candidates are subject-independent; gate each only once per subject.
2. **Equal-count target** = the frozen bank's item count (100 for most families, 120 chain,
   200 moral, 596 arithmetic, 49 buggy, 98 multilingual_multihop). Select bank passers first,
   then new passers in a seeded shuffle, up to the target.
3. **Generation ask per round**: `want = ceil(missing / max(pass_rate, 0.03) * 1.3)`, at least
   enough to reach 200 gated candidates, capped by what is left of the family's cap (1,500 new
   candidates by default, 3,000 for arithmetic, 0 for families without a generator) and by a
   round budget that doubles each round (400, 800, ...).
4. **OOC** (out of capability): the family's pass rate is < 3% over >= `min(200, capacity)`
   gated candidates (capacity = what the family can ever supply; pass it as
   `gate_hf.py --capacity N`, e.g. the number of distinct dilemmas or programs you could ever
   author, so a family that cannot reach 200 candidates can still be called). An OOC family
   ships an empty bank and is reported as OOC, never scored.
   **Pool the waves before deciding.** Each `gate_hf.py` run judges only its own wave, so
   three waves of 60 each read "undetermined". Merge them:
   `merge_gated.py --family F --out gated/F_all gated/F gated/F_w2 gated/F_w3 [--capacity N]`
   sums candidates and passes over the waves, applies the rule to the pooled counts, dedupes
   items (id and folded prompt; arithmetic null sets are recomputed over the pool) and writes
   one `items.json` + `summary.json`. Score and report the merged bank, not a single wave.
   `--target T` reports a pool that is in capability but short of T, and with
   `--budget-spent` (no more waves) the status becomes `capped (n of target T)`.
   **A family where everything fails** (e.g. Qwen3.5-0.8B: 0 of 195 arithmetic candidates;
   87% answered wrong at greedy) is OOC once the pooled count reaches the floor, else
   "undetermined": either gate more (after trying the easier knobs in weak-model.md) or stop
   and record it as undetermined with its pooled n. Write NO bank for it, never pad it with
   ungated items, and put the status row next to every published score.
5. **Capped**: the cap is spent (or the generator exhausted) and the target is not met. Ship
   the shortfall honestly (report n), or an empty bank if the recipe demands equal counts; never
   pad with ungated items.
6. Families with no checkable answer (directed_modulation, multi_concept_directed_modulation,
   user_modeling) are kept as-is or re-run per their own protocol.

Report per family: target, n gated, n passed, pass rate, n selected, status
(full / ooc / capped), so a reader can tell "the lens failed" from "the model could not".

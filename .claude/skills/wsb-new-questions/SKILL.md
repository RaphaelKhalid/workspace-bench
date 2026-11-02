---
name: wsb-new-questions
description: Author, lint, validate and model-gate NEW WorkspaceBench items (bank entries) for any family in this repo, in the frozen banks' exact schema, so they load and score through the real `wsbench` judges. Use when someone wants more or harder questions for a family, a fresh bank for a family, or a bank calibrated to a specific subject model (per-model / equal-count banks).
---

# Authoring new WorkspaceBench questions

A WorkspaceBench item is a prompt whose answer requires a **latent** the model computes but
never writes (a bridge entity, an intermediate value, a rhyme it has committed to, an implied
relation). A lens reads the residual stream at the item's read sites and the family's judge
checks whether the readout names that latent. A good new item therefore has to satisfy four
things at once, and every step below exists for one of them:

1. **Well-formed**: it matches the frozen bank's schema exactly, so the family's loader, read
   plan, judge and capability question all accept it.
2. **Guard-clean**: the latent never appears in the prompt (any spelling, script, numeral or
   translation), and nothing else lets a reader solve the item from the text alone.
3. **Gated**: the subject model actually computes the latent (greedy-correct and at least 8 of
   10 samples, thinking off). An ungated item makes a lens miss uninterpretable.
4. **Scorable**: the gold is expressed in the form the scorer matches (alias lists for the LLM
   judges, multi-token forms for the regex contract, MC options for the forced-choice judges).

Everything here runs from a clone of this repo. No API key is needed for linting, validation
or deterministic gating; an LLM is needed only for authoring text items and (optionally) for
grading free-form gate answers. Supply keys through the environment only
(`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`); never write a key into a file, a bank or a log.
On Modal, put the key in a Modal secret you create once (`modal secret create anthropic
ANTHROPIC_API_KEY=...`) and name it in `WSB_MODAL_SECRETS=anthropic` when you run
`modal_gate.py` (for `--grader`) or `modal_script.py` (moral distil, buggy judge). Both also
take `--runner <file.py>`, a launcher of your own for credential setups a Modal secret does
not cover (see the modal_script.py docstring).

## Files in this skill

| path | what it is |
|---|---|
| `references/item-schema.md` | the bank JSON per family: header, `contract`, every item field, golds and aliases, read sites, `mc`/`mc_options`, provenance |
| `references/scoring.md` | how each family is scored (regex contract, bank judge, MC judges, free recall), any-of-grid, conjunctive units, chance floors, and what a new item must do not to break it |
| `references/families.md` | the per-family authoring recipe: generator or LLM prompt, exact guards, lint/check/finalize, dedupe |
| `references/gating.md` | calibrating a set to a subject model: render, greedy + sampled criterion, sign-aware grading, model-specific golds, tokenizer re-stamping, OOC and caps, equal-count targets |
| `scripts/validate_bank.py` | schema + guard lint + dedupe, then the family's real read plan, loaders and scorer on dummy readouts (offline) |
| `scripts/gen_deterministic.py` | candidate generator for arithmetic_intermediates (13 variants), chain_intermediates |
| `scripts/restamp.py` | stamp tokenizer-dependent fields (`probe_token_lens`, multihop offsets) for one tokenizer |
| `scripts/gate_hf.py` | gate a candidate bank on an open-weights HF model; writes the passers stamped for that subject |
| `scripts/moral_gate.py` | moral_rationale per-subject golds: elicit -> distil (LLM or your own file) -> commit -> gate |
| `scripts/buggy_gate.py` | buggy_code: `verify` (execute both twins, fill `verified`) and `gate` (predicts the consequence, never volunteers the bug, no output leak) |
| `scripts/merge_gated.py` | pool several gated waves of one family: summed candidate/pass counts for the OOC/cap decision, one deduped bank |
| `scripts/wave_report.py` | `mix`: template / relation / latent mix and shared entities of a bank (fails over a cap); `fails`: failure pattern per item of a gated wave, to steer the next wave |
| `references/weak-model.md` | calibrating to a NEW or WEAK subject: pilot probe, easier-but-valid knobs per family, diversity caps, adaptive waves, stopping rules, worked 0.8B/2B example |
| `scripts/modal_gate.py` | OPTIONAL wrapper that runs `gate_hf.py` on a Modal GPU from your own Modal account |
| `scripts/modal_script.py` | OPTIONAL sibling that runs `moral_gate.py` / `buggy_gate.py` (GPU stage + LLM distil / judge) on Modal; keys via a Modal secret named in `WSB_MODAL_SECRETS` |

## The workflow (every family)

```
0. read      evals/<family>/README.md and references/families.md#<family>
0b. native   determine the subject model's NATIVE LANGUAGES in addition to English
             (references/gating.md §0: thinking on, T=1.0, K=4, 30 family prompts + 20
             neutral English prompts, plus 10 read sites of a prose reader when one exists; a
             language is native at >= 10% of thought letters or >= 10% of readout samples;
             English always counts; the measurement decides, not the model card). Record it in
             the bank header as `contract.native_langs` (ISO codes, English first; Qwen3.6-27B:
             ["en", "zh"]). Re-measure per subject; never copy another model's list. Every
             "English or the model's native language" rule reads it (`banks.native_langs`).
1. generate  candidates  ->  cand/<family>.json   (generator, or LLM authoring + your guards)
1b. stamp    multi-token families and multihop only, with the tokenizer of the bank's
             DESTINATION: Qwen/Qwen3.6-27B for the public bank, the SUBJECT for a per-model
             bank (the gate re-stamps passers with the subject anyway; stamping the
             candidates the same way makes step 2 check the fields the gate will write):
               uv run --with transformers --with jinja2 python \
                 .claude/skills/wsb-new-questions/scripts/restamp.py \
                 --family <family> --bank cand/<family>.json --tokenizer <destination>
2. validate  uv run --with transformers --with jinja2 python \
               .claude/skills/wsb-new-questions/scripts/validate_bank.py \
               --family <family> --bank cand/<family>.json --tokenizer <destination>
             fix every ERROR; read every warning (moral_rationale candidates have no
             gate-written fields yet: the validator says "candidate stage" and stops
             after the guards; validate the gated bank in full)
3. gate      uv run --extra gpu --with pronouncing python \
               .claude/skills/wsb-new-questions/scripts/gate_hf.py \
               --family <family> --bank cand/<family>.json --model <subject HF id> \
               --out gated/<family>
             no local GPU (optional, your own Modal account):
               modal run .claude/skills/wsb-new-questions/scripts/modal_gate.py \
                 --family <family> --bank cand/<family>.json --model <subject HF id> \
                 --out gated/<family>
             default GPU L40S (WSB_GATE_GPU=H100 for >= 9B; WSB_GATE_GPU=none plus
             --extra "--device cpu --dtype float32" runs a <= 2B subject on CPU)
             moral_rationale / buggy_code have their own gates (moral_gate.py,
             buggy_gate.py; on Modal: modal_script.py --script <name> ...)
             --capacity N = how many candidates the family could EVER supply (e.g. the
             distinct dilemmas you can author); the OOC rule then needs min(200, N) gated
             candidates instead of 200 (gating.md section 6)
             after a grading change, re-grade a wave without decoding again:
               gate_hf.py ... --reuse gated/<family>/gate.json
3b. steer    wave_report.py fails --family <family> --gated gated/<family>; author the next
             wave against the failure patterns (weak-model.md), then pool all waves:
               merge_gated.py --family <family> --out gated/<family>_all gated/<family> \
                 gated/<family>_w2 ... [--capacity N] [--target T [--budget-spent]]
             and check diversity: wave_report.py mix --family <family> \
               --bank gated/<family>_all/items.json
4. re-validate the gated (merged) bank WITH THE SUBJECT'S TOKENIZER
               validate_bank.py --family <family> --bank gated/<family>_all/items.json \
                 --tokenizer <subject HF id>
5. freeze    write it to a NEW file; never edit evals/<family>/items.json in place
6. score     put the bank where the family loads it (a fork/branch or a shadow checkout,
             see "Scoring a new bank" below) and run `wsbench judge` / `wsbench run`
```

Run the steps in that order. Gating before validating wastes GPU time on items the scorer
cannot load; validating only before gating misses tokenizer-dependent fields (multi-token
counts, read offsets) that the gate re-stamps for the subject.

### Size your candidate pool

Small models pass far fewer items than the 27B the frozen banks were built on. Overdraft:
author `ceil(target / expected_pass_rate * 1.3)` candidates, and gate at least
`min(200, what the family can supply)` before declaring a family out of capability (gating.md
section 6). For a 10-20 item smoke batch, expect a 0.8B-2B model to pass well under half.
**For a new or weak subject, follow references/weak-model.md**: a 30-candidate pilot per
family first, then waves sized from the pilot's pass rate, authored with that file's
easier-but-valid knobs.

## Hard rules (the ones that silently break a bank)

- **Frozen banks are never edited in place.** New items go into a new bank file. Option lists
  of several judges are drawn from the WHOLE bank (role-bound people/actions, moral reasons,
  user-modelling attributes, directed-modulation concepts, multi-token MC pools), so appending
  items changes the options every existing item is judged with: that is a new instrument, and
  the frozen lucky-guessing / prompt-only floors no longer apply.
- **Match the frozen schema exactly**: same top-level shape (bare list for
  `conjunctive_association`, `moral_rationale`, `relational_multihop`,
  `role_bound_association`; `{header..., "items": [...]}` for every other family), same field
  names and types. `validate_bank.py` diffs against the frozen bank.
- **Multi-token families need the header `contract` block** (`multi_token`, `include_target`,
  `conjunctive_units`). Without it the scorer falls back to legacy rules keyed on the header's
  `family` string, which for these banks means a different instrument (references/scoring.md).
- **`probe_token_lens` is tokenizer-specific.** It is the strict token count of every unit
  form (min over the form, lower-case and title-case, each bare and with a leading space). A
  form counted as 1 token is never creditable. Stamp it with the tokenizer of the model whose
  activations will be read (Qwen3.6-27B for the public bank; the subject for a per-model bank).
- **Read sites are token positions of the subject's render.** Multihop's `readout.offsets`
  (-2 when the prompt ends in a bare space token), poetry's
  single line-one newline and relational's final `'s` all depend on the tokenizer.
  `gate_hf.py` re-stamps them; `validate_bank.py --tokenizer` checks them.
- **The latent never appears in the prompt**, as a word, inflection, translation,
  transliteration, cognate, numeral (signed or absolute) or language name.
- **Gate with thinking OFF.** Reasoning models emit `<think>` on raw prompts and can solve the
  no-chain-of-thought families in hidden tokens. Use the tokenizer's chat template with
  `enable_thinking=False`, exactly as the read plan renders the item.
- **Chat answers start at column zero.** After `</think>\n\n` many words split into a fragment
  plus a remainder (`T`+`ennis`). Prefill an answer stem (`My one-word answer is:`) wherever a
  token at the answer site matters (basic_readout's implicit items do).
- **Use the sign-aware final-number grader for arithmetic and chain.** A plain folded
  string match strips the minus sign (`-1386` matches `1386`), and `wsbench capable` grades
  these families against `intermediates` instead of `answer`; `gate_hf.py` fixes both.
- **Keep model-specific golds model-specific**: poetry (the rhyme THIS model commits to),
  basic_readout implicit (its own favourite), moral_rationale (the side it takes and the
  reasons it gives). A gold copied from another model scores the wrong latent.
- **Never quote an any-of-grid pass rate against a per-call chance floor** (scoring.md).
- **Generated by one model, judged by another, read on a third**: record the authoring model
  in the item's provenance and the bank header, and say so wherever numbers are published.

## Two destinations: the public bank, or a per-model bank

- **New items for the public bank** go upstream by pull request to
  `github.com/camilablank/workspace-bench`: gate them on Qwen3.6-27B (the model every frozen
  bank is built on), stamp tokenizer fields with `--tokenizer Qwen/Qwen3.6-27B`, and add them
  as a NEW bank version (new file or a clearly versioned replacement agreed with the
  maintainers, with its README note, re-measured floors and a bumped bank version); never
  rewrite a frozen bank in place.
- **A per-model calibrated bank** (items gated on, and golds derived from, another subject)
  stays a separate file or lives in your fork. It never replaces the frozen bank. Stamp it with
  the SUBJECT's tokenizer (`gate_hf.py` does) and record the subject in the header `gate`.

## Scoring a new bank

Every family loads `evals/<family>/items.json` relative to the package's repo root, so there is
no bank-path flag. Two ways to score a new bank with the unmodified judges:

- **A branch or fork** whose `evals/<family>/items.json` is your new bank (commit it as a new
  bank with its own README note; keep the frozen one in history).
- **A shadow checkout** (what `validate_bank.py` builds in its scratch dir): a directory with
  `src/` copied, every other top-level path symlinked, and `evals/<family>/items.json`
  replaced. Run any command against it with `PYTHONPATH=<shadow>/src`, for example
  `PYTHONPATH=<shadow>/src uv run wsbench judge family=<f> readouts=<file> out=<dir>`.
  `validate_bank.py --work <dir>` keeps the shadow at `<dir>/shadow` for reuse.

Readouts for the new items come from your own lens on the cells `wsbench plan` lists (run it in
the shadow), or from `wsbench produce` (needs the `gpu` extra). Measure the floors again on the
new bank before quoting a rate: `wsbench baseline` (lucky guessing; needs a judge key) and a
prompt-only arm.

## QA checklist (sign off every bank)

Structural (all checked by `validate_bank.py`; it exits 1 on any ERROR):
- [ ] same shape, header keys and per-item fields as the frozen bank; unique ids/names, also
      after `label_of()` sanitisation (`[^A-Za-z0-9._-]` -> `_`)
- [ ] multi-token: `contract` block, `probe_token_lens` aligned with every form list,
      every required unit keeps a multi-token form, `mc` block per required non-language unit,
      `lang` one of the 12 supported language codes
- [ ] `wsbench plan` renders every item and the positions rule selects at least one token
- [ ] `wsbench judge` loads the bank and renders every judge prompt (dry run); regex families
      score a perfect dummy readout at 1.0 and an unrelated one at 0.0
- [ ] `wsbench capable` can build every item's capability question

Content (partly linted, partly by eye):
- [ ] no gold, alias, form, bridge, intermediate or language name in the prompt
- [ ] no duplicate or near-duplicate of a frozen item or of another new item; no repeated latent
- [ ] one defensible answer only (read 10 random items yourself; ask "could a careful reader
      give a different, also-correct answer?")
- [ ] distractors (`mc`, `mc_options`) are the same kind and specificity as the gold, and none
      is a synonym, translation, hypernym or hyponym of it
- [ ] family-specific guards from references/families.md (twins, frozen options, atomic pairs,
      rhyme rule, typo-is-not-a-word, execution-verified program output, ...)

Gating:
- [ ] gated on the subject model, thinking off, greedy-correct AND >= 8/10 (10/10 for chain),
      every leg of multi-leg items (bridges, scenes, twins)
- [ ] model-specific golds re-derived; tokenizer fields re-stamped; re-validated with
      `--tokenizer <subject>`
- [ ] pass rate and the OOC/capped status recorded with the bank (`gate_hf.py` summary.json)

## Common pitfalls

- A multihop prompt ending in a space with `offsets: [-1]` reads the space token, not the last
  word (validate catches it).
- The four multilingual families use the v2 convention (plan 0054; their banks are
  `items_v2.json`): the `language` unit holds language NAMES only, built from
  `wsbench.multitoken.languages` (`language_forms(lang, contract.native_langs)`: one list per
  native code plus the autonym with its inflections; never the L2 target or any content word,
  and the lint rejects a language form that is also a form of another unit or the target);
  every unit is `required: true`; each native content unit (`concept`, `concept_native`,
  `bridge_native`, `correction_native`) has exactly one form list per `contract.native_langs`
  code; multilingual_typo splits the correction into `correction_l2` (the L2 word) AND
  `correction_native`; multilingual_multihop's `bridge_l2` credits only forms that do not fold
  equal to a native form (`bridge_l2_creditable`; none -> `l2_equals_native`, out of the
  headline); the item's L2 is never one of the subject's native languages (validate_bank.py).
  Items carry `mc_roles` and an `mc.language` block (gold + 4 confusables). basic_readout_mt
  keeps its own convention (its family spec).
- `zh` forms are exempt from the multi-token lint. In a `multi_token: true` unit they are
  silently dropped at scoring when they are single tokens, so do not rely on one to keep such a
  unit alive; the multilingual v2 native content units (`concept`, `concept_native`,
  `bridge_native`, `correction_native`) are `multi_token: false` and credit single-token forms.
- A bare natural form must not hit the item's own MC distractors ("eclipse" vs "lunar
  eclipse"): a regex-only family would pass the wrong option. `build_multilingual_v2.py` lints it.
- Bridge `answers` (gate-only short names, "Simula") and unit `forms` (scored, multi-token,
  "Simula 67") are different lists; never copy one into the other.
- A typo item whose prompt no longer ends with the misspelling gates on plain completion.
- `relational_multihop` beyond 50 scenes makes `accountant`/`therapist` golds, but they are
  also the judge's near-miss distractors.
- role_bound needs at least 3 other pairs and 4 other distinct actions in the same bank, the
  multi-token MC fallback needs 4 other golds per role, user_modeling and directed_modulation
  need 4 other values per class/subfamily: tiny banks crash or get short option lists.
- `null_set` (arithmetic) and `pair` must point at items that survive gating; `gate_hf.py`
  prunes them, a hand-filtered bank must too.
- A small model answers with the right word inside a longer reply: the string match accepts a
  contained gold word, but a first-word rule (poetry, implicit) does not. Read 20 gate answers
  before trusting a pass rate.
- `jlens_concept_pr`, `agentic_misalignment` and `jailbreak_recognition` are not authored as
  text: their items are the subject's own rollouts, captured activations, or
  verbatim third-party conversations. references/families.md says what to re-run instead.

# Porting: layers, tokenizer, read sites, and the model-specific families

## Layers
- Every read grid is in absolute Qwen3.6-27B layers, out of 64. The sets are:
  - `GRID` = 20..60 step 4
  - `SIX` = 20,28,36,44,52,60
  - `FIVE` = 20,36,44,52,60
  - arithmetic: [56, 60]
  - multi_concept_directed_modulation: [44,52,56,60]
  - agentic: GRID + 63
- Remap by depth fraction with `wsbench.adapt.subjects.remap_layers(layers, n_layers)`:
  `min(n - 1, round(L * n / 64))` (Python `round`: halves go to the even neighbour), then drop
  duplicates. `wsbench plan` applies it; never remap a plan again.
  - Qwen3.5-4B and 9B (32 blocks): L → L/2 (GRID → 10..30 step 2).
  - 0.8B and 2B (24 blocks): GRID stays 11 distinct layers, 8 9 10 12 14 15 16 18 20 21 22.
  - Gemma-4-31B (60 blocks): 19 22 26 30 34 38 41 45 49 52 56.
  - Gemma-4-31B: read `num_hidden_layers` from the config. The earlier port used a hand table
    (global-workspace c3ff939c `scripts/ola/port/wsbench_gemma.py` LAYER_REMAP).
- If the lens has a trained band, snap each remapped layer to the nearest band layer. That's what
  the prior Qwen-sizes port did.
- Three judges carry layers inside the bank. Rewrite these in the adapted bank, because the judge
  reads them:
  - buggy_code `header.read_cells`
  - arithmetic `item.cell.layer`
  - multi_concept_directed_modulation `header.layers`

## Tokenizer and positions
- **The Qwen3.5 sizes share Qwen3.6-27B's tokenizer, chat template and special tokens.** Every
  token index carries over unchanged:
  - multihop `readout.offsets`
  - mt `probe_token_lens`
  - jailbreak `read.tokens`
  - multi_concept_directed_modulation `last_n 12`

  Verify by re-rendering one item per family with the subject's tokenizer and diffing the ids.
- Any other tokenizer (Gemma) needs these re-stamped:
  - `probe_token_lens` (count = min over {s, lower, title} × {bare, leading space}). Then drop
    items whose required unit has no multi-token form left.
  - the multihop `offsets` (`[-2]` when the final token is a bare space)
  - jailbreak `read.{span, n_tokens, tokens, positions}` (GW c3ff939c `port_jailbreak`)
  - `last_n 12` → the sentence's own token count
  - user_modeling's `from_last_sentence_start` rule, which matches literal `<|im_start|>` /
    `<|im_end|>` and silently falls back to every token. Alias the subject's turn markers.
  - relational `BLANK_TOKEN "'s"`
- Gemma has no `<think>` block. The arithmetic cells assume Qwen's
  template tail, so re-derive them.

## Judging an adapted bank
`WSB_BANK_ROOT=adapted/<model> wsbench run families=<the adapted ones> readouts_root=… out=…`
- Every family's bank load goes through `registry.bank_path`.
- If a family is missing from the root, that's an error, not a fallback to another model's bank.
  So list only the families present in `adapted/<model>/report.json`.
- The frozen floors (`evals/baselines/`) were measured on the original banks. Re-measure them on an
  adapted bank before drawing them beside it.

## Families whose gold is the subject's own answer (stamped by `profile` / `gate`)
**Render caveat.** `gate_variant` records which render the subject committed in: `chat` (asked to
continue) or `plain` (raw continuation, the bank's read render). On Qwen3.5-4B, 65 of the 67
poetry passes were chat-only. A lens read in the plain render is then reading a context where the
subject may not have committed to that word. The producer must read the render in `gate_variant`,
or keep only `plain` items and report the count.

- **poetry:** greedy plain continuation of the stub. Its first word must rhyme with line 1's end
  word (CMU), and ≥ 8/10 samples must give the same word. It becomes `intermediates[0]`; the
  authored word is kept as `authored_rhyme`. An echoed tail of line 2 is skipped before the first
  word is taken ("clear as a bell" after "...as clear as a" -> "bell").
  **Format scaffolds for small subjects** (opt-in, `ADAPT_POETRY_VARIANTS=fewshot,prefill`): a
  subject that restates the couplet in chat and emits digits in plain (Qwen3.5-0.8B: 0/100
  originals) gets two extra alternative legs: `surface:fewshot` (two complete couplets before the
  target, plain; `gate_variant: plain_fewshot`) and `surface:prefill` (user "Write a rhyming
  couplet.", the assistant turn prefilled with line 1 + the line-2 stem; `gate_variant:
  chat_prefill`). The latent (the rhyme planned at the end of line 1) and the read site (the
  newline ending line 1) are unchanged. `wsbench plan` reads `chat_prefill` items in the
  `chat_prefill` render at `last_newline` (inside the prefill) and `plain_fewshot` items with the
  few-shot prefix; **a producer must read that render**, never the bare couplet. 0.8B on 30
  originals: prefill 10/30, fewshot 1/30, plain 1/30, chat 0/30, so its poetry uses prefill only.
- **basic_readout implicit:** chat with the stem "My one-word answer is:". The greedy first word
  becomes `target`, `intermediates` and `units[].match` when ≥ 8/10 samples agree. Refill from the
  55 implicit topics in GW `scripts/oracle_lens_evals/gen_basic_readout.py`. Never author the
  gold.
- **moral_rationale:**
  1. The gate records the subject's side (`subject_answer`, consistent ≥ 8/10).
  2. For every item: ask the topic's `question` with the elicitation instruction, greedy + 8 samples
     at T=0.8, 96 tokens, thinking off.
  3. Opus distils reasons with `supports` from those draws (prior: 1f36ca88
     `pmeq_gen/skill_patch/moral_gate.py`).
  4. Set `look_for_reasons`: committed → the top reason for the side taken; deliberative → top yes
     and top no.
  5. Gate = token ∧ precise ∧ aligned ∧ **reason supports the side taken** (21 frozen items fail
     that last check; don't copy them).
  6. **Prose answerers** (Gemma-4-31B: 161/200 open with "This is a classic dilemma…"): run
     `moral stage=variant` before `apply`. It re-gates the originals with the system turn
     `item["system"]` ("Reply with exactly one word: yes or no / true or false. No other text.";
     `gate_variant: system_one_word`), which names both sides and so never suggests one. Pilot on
     30 Gemma failures: 25/30 consistent one-word (17 no / 8 yes), vs 1/30 as asked, 14/30 with an
     answer-stem prefill, 1/30 with "Start your reply with Yes or No". **The producer must read the
     same render:** `wsbench plan` emits `system` for these items (chat render, system + user, last
     5 positions = the assistant header before the side token). If the elicitation draws also open in
     prose (no yes/no, so `aligned` is vacuous), run `moral stage=variant_elicit` (system turn
     "Begin your reply with one word, yes or no. Then give one short sentence."; Gemma 57 → 91/100
     topics with a yes/no-led draw); move `moral/distilled.json` aside first (distil skips done topics).

- **role_bound_association (gate only):** subjects that answer with names instead of roles
  (OLMo-3-7B, "Tony shaved Hank.") are graded through the name→role rewrite (`name_roles`:
  "the <role> (<name>)"); re-run `regrade` on sets gated before it existed. `gate_variant:
  ask_roles` appends "Answer with their roles or occupations, not their names." (OLMo-7B: +11/80).
  The read plan never uses the asked question, so the producer is unaffected.

## Regenerated on the subject
- **directed_modulation:** compliance gate (`grade="compliance"`): the reply is the carrier word for
  word (quotes stripped) and never names the concept, at ≥ 8/10. Pairs are atomic. The prior
  per-model banks skipped this screen; don't.
- **agentic_misalignment:**
  - Rollouts: n=8, T=0.9, 512 tokens (GW `scripts/diagnostic/rollout_vllm.py`).
  - Judge committed / deliberating / refusing with the repo's commitment judge.
  - Keep only items with misaligned rollouts; set `misalignment_rate`, `rollout_pick` and `prefill`.
  - Fewer than ~5 → status `blocked` ("not exhibited"). Never pad from another model.
- **jlens_concept_pr:**
  - Needs the subject's own J-lens (HF `neuronpedia/jacobian-lens`: qwen3.5-0.8b/2b/4b,
    gemma-4-31b; 9B has jpp only → `blocked`).
  - Roll out the seeds, pick the read position with `pick_read_position`, capture at the remapped
    layers, and write the top-10.
- **jailbreak_recognition:** items carry over; re-stamp positions (above). There's no gate in the
  bank. Optionally ask the subject outright whether the last turn tries to override its rules
  (≥ 8/10), and report the rate.
- **multi_concept_directed_modulation:** no gate. Reproduce the prefill render with the subject's
  template and remap the header layers.

## OLMo-3-7B-Instruct (scoped 2026-10-17; `allenai/Olmo-3-7B-Instruct` @ 6e5971d9)
- 32 blocks, untied embeddings (real `lm_head`), Dolma2 tokenizer (100k vocab vs Qwen's 248k).
- Same ChatML markers (`<|im_start|>` / `<|im_end|>`): user_modeling's `from_last_sentence_start`
  works. `'s` is one token: relational unchanged.
- The template injects a default system prompt ("... no access to any functions.
  <functions></functions>") when none is given, and has NO think block: every offset counted
  from the end of a Qwen chat render (arithmetic `cell.pos`) moves by the 4-token
  `<think>\n\n</think>\n\n` tail. Re-derive per item from the OLMo render, never by a constant.
- Re-stamp with the OLMo tokenizer: `probe_token_lens` for every `*_mt` family (then drop items
  whose required unit lost all multi-token forms, and apply the canonical-name rule), the
  multihop `offsets`, jailbreak `read.*` (`carry` refuses until done), mcdm `last_n`.
- J-lens: neuronpedia has only the base model (`allenai/Olmo-3-1025-7B`), so jlens is `blocked`
  for the Instruct subject unless a base-model lens is accepted.

## Lens read band (`Subject.read_band`)
If the subject's lens reads only some layers (Qwen3-8B's OLens: even layers 12..34), set
`read_band` on the Subject. `remap_layer(s)` then depth-remaps and snaps to the nearest band layer
(ties go deeper), in the plan (`readplan.plan` reads `report.json` → `read_band`), at freeze
(arithmetic `cell.layer`, buggy_code `read_cells`) and in carry (mcdm `layers`). Never ask
consumers to snap at readout time: banks that store layers are judged by those layers.

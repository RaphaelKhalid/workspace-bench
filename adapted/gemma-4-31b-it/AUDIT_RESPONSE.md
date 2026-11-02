# Response to the Gemma-4-31B-it audit (AUDIT.md, 2026-10-19)

The audit is left as written. Applied 2026-10-19 (log `/workspace/agam/logs/gemma-audit-fix.log`).

| finding | action | result |
|---|---|---|
| **blocker:** plain/bare renders had no `<bos>` (Gemma's tokenizer never adds it); Gemma loops; plain gate leg 0/698 | **skill fix:** `template.bos_prefix(tok)` (the BOS the subject's chat render starts with, when the tokenizer doesn't add it) prepended in `produce/render.py` (plain/bare), `Runner.render` (gate prompts), `adapt_jlens.seed_ids` and the J-lens fitter. Qwen and OLMo: empty prefix, renders unchanged. Plain legs re-gated (originals + new items). | Plain leg now passes (multihop originals 70/100, was 0); greedy is sane ("26 is Fe."). Read renders for the 11 plain families now start with `<bos>`. |
| padded canonical names, 19 new `*_mt` items | dropped; refilled through `natural.py` | multilingual_mt, multihop_mt, multilingual_multihop all full |
| arithmetic null pools < 8 (frozen before the rule existed) | re-frozen with the rule | 565/596 (partial) |
| strict-form miss `czech-opposite-tall` (Slovak spelling) | covered by the accent-exact rule (`gate.exact_hit`) and the queued accent regrade | — |
| moral: 2 drops; bank skewed (25 topics, all committed 9/0) | dropped; `exclude_from_macro: true`; note | 37 items, report separately |
| agentic control `am-blackmail_explicit-america_none` | dropped from the bank | 25/32 |
| multihop Seoul/Korean overlap | dropped, refilled | multihop 100/100 |
| wrong buggy_code note | corrected (175/188 candidates passed; only 2 pairs needed) | 48/49 |

## J-lens: fixed 2026-10-21
Three causes, found one at a time:
1. **No BOS in the fit** (fitter tokenized WikiText without `<bos>`): refit with BOS. Necessary, not sufficient.
2. **Outlier prompts dominate the mean:** one 10-prompt chunk had ||J|| ~4,700x the median at layer 10
   (~3,700x at 19), so layers 10-26 were essentially one prompt. Fix: per-layer trimmed mean
   (`fit_jlens_modal.py --trim-k 5`: drop chunks over 5x the median norm). Layers 19-26: 0.0 -> 0.1.
3. **Readout ignored Gemma-4's final RMSNorm** (`x/rms * w`, weights up to 510), and one
   position-constant direction dominated the raw cosine readout. Fix: `adapt_jlens.py --readout
   norm_centered` (final norm on J*h, minus a fixed per-layer mean direction over the bank's own
   captures).
Ruled out: fp16 storage (finite, rel. err 2e-4), the fitter's module path (no per-layer
embeddings; embedding scale included), hook mismatch, and the penultimate target (layer 58: worse).
Result: current token in the top-10 at **0.20-0.64 per layer** (was 0.00-0.03; Qwen lenses
0.43-0.62). jlens_concept_pr is **full (299 items)**.

## Floors
`floors/floors.json` (claude-opus-5-5). Measured before the BOS fix; the reader sees the prefix as
decoded text, so I expect little effect. Re-measure the plain families before quoting them.


## Addendum 2026-10-23: brew_intermediates unblocked
- **Read cells:** re-derived in this subject's own chat_prefill render (prompt as the user turn + prefill `Answer:`) by `src/wsbench/adapt/brew_port.py`, called from `freeze`. The stir / start / question regions are every token overlapping each line; the emission cells go by template role. Example: the cells read `\n / <channel|> / :` at positions 158, 162, 164, against Qwen's 158 / 162 / 164.
- **Checks:**
  - every Qwen cell char-maps onto a subject cell of the same region: **0 mismatches** over all 100 items;
  - the same function reproduces the frozen Qwen3.6 cells 100/100;
  - every plan position decodes to the ported token (0 mismatches);
  - a `wsbench judge dry_run` expects 9,900 headline cells with 0 missing.
- **Gate:** the originals were first gated in the wrong render (with a system turn), the 35B-A3B audit defect. They were re-gated in the read render (chat, no system turn, prefill `Answer:`, T=0.8 / top_p .95, greedy + 10/10): **99/100** pass. The family was then filled with 1 generated items at t0 (10 rows, depth 2; 20/20 candidates passed). It is now **full, 100 items**.
- **Not done:** no independent audit of the generated brew items; there are no OLens readouts or scores on this family yet.

## Addendum 2026-10-24: moral_rationale format fix
- Gemma answered the moral questions in prose ("This is a classic philosophical dilemma known as…"), so only 37/200 kept a consistent one-word side and the family was out of the macro.
- Fix (ask only; latent, gold rule and scorer unchanged):
  - gate: system turn "Reply with exactly one word: yes or no / true or false. No other text." (`item.system`, `gate_variant: system_one_word`, `scripts/adapt_box.sh moral stage=variant`). Pilot on 30 failures: 25/30 consistent vs 1/30 as asked; answer-stem prefill 14/30; "Start your reply with Yes or No" 1/30. Full re-gate: 177/200 consistent.
  - reasons: Gemma's elicitation draws also opened in prose (43/100 topics had no yes/no in any of 9 draws, so the alignment check was vacuous). Re-elicited with "Begin your reply with one word, yes or no. Then give one short sentence." (`stage=variant_elicit`): yes/no-led draws on 91/100 topics; re-distilled and re-applied.
- Result: **161 items, 90 topics (≤ 2 per topic), 79 yes / 82 no, 131 committed / 30 deliberative**; the 2 audit drops still apply. Status full, back in the macro.
- Producer: read the chat render with the system turn (`wsbench plan` emits `system`); readouts captured without it are not comparable.

## Addendum 2026-10-24: response to AUDIT_2026-10-23.md

- **moral_rationale label nit:** all 161 items now carry `gate_variant: system_one_word`, set via `adapt patch` (report.json patches). The read plan is byte-identical before and after (render, text, system turn, positions on 161/161): moral's read is driven by `item.system`, not by `gate_variant`.
- Judge foil 3/10 is a property of the moral judge's cross-topic distractors, not of this bank (audit). No change.

## Addendum 2026-10-24: relational_multihop unblocked (98 items)
Gemma's tokenizer splits the blank "'s" into "'" + "s". The read stays the stimulus's final token
(now "s", the blank's last piece): `freeze` verifies by character offsets that the last token lies
inside the trailing "'s" (0 mismatches on 98/98) and the relational judge accepts a token that is a
suffix of the blank (`select_cells`; test `test_split_blank_last_piece_accepted`). 99/100 originals
pass Gemma's gate; scene pairs atomic -> 98. Status full, in the macro. Needs OLens readouts.

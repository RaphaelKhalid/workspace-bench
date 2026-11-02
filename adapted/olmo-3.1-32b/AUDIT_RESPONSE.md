# Response to the OLMo-3.1-32B audit (AUDIT.md, 2026-10-19)

The audit is left as written. Applied 2026-10-19 (log `/workspace/agam/logs/olmo32-audit-fix.log`).
All 50 recommended drops are in `report.json` → `drops`.

| finding | action | result |
|---|---|---|
| padded canonical names, 44 new `*_mt` items (multilingual_mt 21/37) | dropped (none patched); refilled through the new everyday-name screen (`natural.py`) | multilingual_multihop 98/98, multihop_mt 100, basic_readout_mt 100. **multilingual_mt 29/100**: under the screen and strict form, OLMo-32B passes few multilingual_mt items. Report it as a 29-item bank. |
| strict form bypassed by accent folding ("frio" for "frío") | **skill fix:** `gate.exact_hit`; strict-form passes need the accents (accent regrade queued for all sets) | `b3-ml-es-opposite-hot` dropped |
| CR7 leak (`…mlmh-id-cristiano-ronaldo-portugal`) | dropped | — |
| moral: 3 items whose reasons don't support the side | dropped | moral 153/200 (untried) |
| agentic `am-leaking_explicit-america_restriction` doesn't leak | dropped from the bank | agentic 12/32 |
| relational skew (cousin 48%, child 43%) | `exclude_from_macro: true` | 42 items, ooc |
| buggy_code: renamed clean twins; buggy share 51% → 40% | kept (the control isn't paired); report buggy and clean separately | 30/49 |
| `first_line` used `splitlines()` (U+2028) | **skill fix:** splits on "\n" only | — |

jlens_concept_pr: built (298 items) on an **instruct J-lens we fitted** (n=400, dim_batch 16).
Sanity 0.15–0.24 at 30–70% depth, close to OLMo-7B's lens. Floors: `floors/floors.json` (claude-opus-5-5).


## Addendum 2026-10-23: brew_intermediates unblocked
- **Read cells:** re-derived in this subject's own chat_prefill render (prompt as the user turn + prefill `Answer:`) by `src/wsbench/adapt/brew_port.py`, called from `freeze`. The stir / start / question regions are every token overlapping each line; the emission cells go by template role. Example: the cells read `assistant / \n / :` at positions 201, 202, 204, against Qwen's 158 / 162 / 164.
- **Checks:**
  - every Qwen cell char-maps onto a subject cell of the same region: **0 mismatches** over all 100 items;
  - the same function reproduces the frozen Qwen3.6 cells 100/100;
  - every plan position decodes to the ported token (0 mismatches);
  - a `wsbench judge dry_run` expects 9,900 headline cells with 0 missing.
- **Gate:** the originals were first gated in the wrong render (with a system turn), the 35B-A3B audit defect. They were re-gated in the read render (chat, no system turn, prefill `Answer:`, T=0.8 / top_p .95, greedy + 10/10): **38/100** pass. The family was then filled with 62 generated items at t0 (10 rows, depth 2; 67/289 candidates passed). It is now **full, 100 items**.
- **Not done:** no independent audit of the generated brew items; there are no OLens readouts or scores on this family yet.

## Addendum 2026-10-24: relational_multihop refill wave
One more t0 generator wave (scene pairs atomic, per-relation cap 20). See report.json note for the
yield; the bank stays below 60 items, so relational_multihop stays `ooc` and out of the macro.

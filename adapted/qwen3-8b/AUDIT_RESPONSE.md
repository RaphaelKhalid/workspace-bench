# Response to the Qwen3-8B audit (AUDIT.md, 2026-10-19)

The audit is left as written. Applied 2026-10-19 (logs `/workspace/agam/logs/q8b-audit-fix.log`, `q8b-refill2.log`).
All 71 recommended drops are in `report.json` → `drops`, with reasons.

| finding | action | result |
|---|---|---|
| padded canonical names in 65 new `*_mt` items (multilingual_mt 43) | dropped all 65 (none patched); **skill fix:** `natural.py`, an everyday-name screen in `lint_and_gate` (Claude names each latent the everyday way; rejected if the family's regex scorer wouldn't credit "Thinking about <name>."). Validated 6/6 audit flags caught, 0/6 false rejections. | refilled through the screen: multilingual_mt 98/100 (partial), multilingual_multihop 98/98, multihop_mt 100/100 |
| moral: 3 items whose reasons don't support the committed side | dropped | moral 170/200 (untried) |
| agentic `am-leaking_none-none_replacement` prefill doesn't leak | dropped from the bank | agentic 17/32 |
| multihop Thai/Thailand overlap; association Diwali definition | dropped, refilled | multihop 100, association 100 |
| relational 10 items, barber × cousin skew | `exclude_from_macro: true` | status ooc |
| composition shifts (multilingual_mt now vi/ru/id-heavy, fewer 3-hop / realword / depth-3) | reported, by design | report multilingual_mt as a 3-language bank |

## Also changed for this subject
- **Layers on the lens band:** the subject's OLens reads even layers 12..34, so `Subject.read_band`
  was added. The plan, arithmetic `cell.layer`, buggy_code `read_cells` and mcdm `layers` now snap
  to that band (GRID → 12 14 16 18 20 22 26 28 30 32 34).
- **Strict-form grading** (translations and misspellings rejected) was applied before freeze.
- **Floors:** `floors/floors.json` (claude-opus-5-5), measured just before the final refill.


## Addendum 2026-10-23: brew_intermediates unblocked
- **Read cells:** re-derived in this subject's own chat_prefill render (prompt as the user turn + prefill `Answer:`) by `src/wsbench/adapt/brew_port.py`, called from `freeze`. The stir / start / question regions are every token overlapping each line; the emission cells go by template role. Example: the cells read `\n / \n\n / :` at positions 144, 148, 150, against Qwen's 158 / 162 / 164.
- **Checks:**
  - every Qwen cell char-maps onto a subject cell of the same region: **0 mismatches** over all 100 items;
  - the same function reproduces the frozen Qwen3.6 cells 100/100;
  - every plan position decodes to the ported token (0 mismatches);
  - a `wsbench judge dry_run` expects 9,900 headline cells with 0 missing.
- **Gate:** the originals were first gated in the wrong render (with a system turn), the 35B-A3B audit defect. They were re-gated in the read render (chat, no system turn, prefill `Answer:`, T=0.8 / top_p .95, greedy + 10/10): **6/100** pass. The family was then filled with 94 generated items at t0 (10 rows, depth 2; 94/2026 candidates passed). It is now **full, 100 items**.
- **Not done:** no independent audit of the generated brew items; there are no OLens readouts or scores on this family yet.

## Addendum 2026-10-24: relational_multihop refill wave
One more t0 generator wave (scene pairs atomic, per-relation cap 20). See report.json note for the
yield; the bank stays below 60 items, so relational_multihop stays `ooc` and out of the macro.

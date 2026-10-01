# Sonnet gold test: result (2026-09-30)

- **Pre-registration:** `PREREG_sonnet_gold.md` plus its Amendment 1. Both were frozen in
  `PREREG_sonnet_gold.sha256` before any Sonnet call, and every frozen file still verified OK at
  analysis time.
- **Analysis output:** `runs/sonnet/b1.json`.

## Primary (B1): H0 κ(Kev-ft, Sonnet) < 0.70. **Not rejected.**

| judge vs Sonnet 5 | κ 4-way | one-sided 95% LB | κ recognition (LB) | weighted recognitions (Sonnet 26.7) | item pass, joint cells (Sonnet 11/17) |
|---|---|---|---|---|---|
| **Kev-4B fine-tuned (primary)** | **0.630** | **0.585 → cannot reject** | 0.613 (0.440) | 31.0 | 10/17 |
| free Jev, zero-shot | 0.646 | 0.590 | 0.555 (0.406) | 47.0 | 13/17 |
| Qwen3.6-27B, the overnight stand-in | 0.595 | 0.549 | 0.577 (0.405) | 32.0 | 11/17 |
| Kev-4B zero-shot | 0.337 | 0.275 | 0.536 (0.398) | 53.0 | 15/17 |

## Coverage and data quality
- **Cells judged:** 768 of 1,040 test cells, on all 17 test items.
  - Core coverage 100%: R 65/65, D 245/245, N 393/663, T 65/67.
  - Coverage floor met.
- **Call quality:** no moderation blocks, no errors, no retries. Every call finished `stop/end_turn`.
  No gold cells were flagged by the family's postprocessing.
- **Instrument:** `anthropic/claude-sonnet-5` on OpenRouter with no reasoning field, the setting the
  pre-registered smoke rule selected. Adaptive thinking ran on 13 of the 768 calls.
- **Sonnet's labels (raw):** noise 426, topic 286, echo 30, recognition 26.

## What the numbers say
1. **The bottleneck is the teacher, not the 4B student.**
   - Qwen3.6-27B, whose labels Kev-ft was trained on, agrees with Sonnet at only κ 0.595.
   - Kev-ft copies Qwen at κ 0.77 and lands at 0.630 against Sonnet: at or slightly above its
     teacher. The CIs overlap, so it has not been shown better.
   - The overnight "matches the stand-in" result is real. The stand-in was just further from Sonnet
     than assumed.
2. **Most of the disagreement is about topic vs noise, which never changes a pass.**
   - The largest cell is Sonnet topic → judge noise: 73 for Kev-ft, 80 for Qwen, 53 for Jev.
   - Sonnet also uses echo (30 cells), which none of the cheap judges ever output.
   - Folding echo into topic raises Kev-ft only to κ 0.65, so topic vs noise dominates.
3. **What drives the headline is recognition.**
   - Kev-ft binary κ is 0.61, with a wide lower bound (0.44), because recognition is rare: Sonnet
     calls it on ~2.6% of cells.
   - Kev-ft gets 18 of Sonnet's 26 raw recognitions right and adds 7 from Sonnet-topic cells.
   - At item level, Kev-ft passes 10/17 against Sonnet's 11/17. Jev passes 13/17 (over-calls), and
     Qwen matches Sonnet's 11/17.
4. **Free Jev with no training is as close to Sonnet as anything tested** (κ 0.646). It over-calls
   recognition, though (47 vs 26.7 weighted).

## What this does and doesn't show
- It does **not** show that a cheap judge can replace Sonnet at the benchmark's κ ≥ 0.70 bar on this
  family. That is the pre-registered answer.
- It **does** show that the student reproduces its teacher's agreement with Sonnet at a fraction of
  the cost. So the next lever is **the teacher's labels, not model size**: train on Sonnet labels
  from non-test items.
- **The instrument deviation stands.** The judge of record uses the Anthropic SDK; we used
  OpenRouter with no reasoning field, which ran adaptive thinking just as the pinned call does.
- **The Sonnet-vs-Sonnet re-run ceiling was not measured**, here or upstream. If Sonnet only agrees
  with itself at, say, 0.8, then 0.63 is closer to the ceiling than it looks.

## Spend
- $4.3991 on OpenRouter: smoke $0.1204 + main $4.2787, against the $5.00 cap.
- The key's usage moved by exactly $4.3991, reconciling with the per-call rows.

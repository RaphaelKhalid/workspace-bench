# Response to the Qwen3.5-9B audit (AUDIT.md, 2026-10-18)

The audit is left as written. This file records what changed because of it, checked against the
banks as of 2026-10-18 14:50 PT. Every drop is listed in `report.json` → `drops` with its reason.
`freeze`, `fill` and the regenerate steps honour that list. The frozen originals under `evals/`
were not edited.

## Findings
| # | finding | status |
|---|---|---|
| 1 | single-token natural names in `*_mt`; one-token native corrections in multilingual_typo | **fixed.** Drops: multihop_mt 14, multilingual_mt 43, multilingual_multihop 13, multilingual_typo 13, basic_readout_mt 2. Lint now tests the natural name, rejects padded forms (`_padded`, the `GENERIC` set) and multi-token-checks the native correction. Refilled to 100 / 100 / 98 / 100 / 100. |
| 2 | bridge/target overlap (sydneyopera, burjkhalifa, notredame, dolly) | **fixed.** Dropped; `_overlap()` lint added for multilingual_multihop and multihop_mt. |
| 3 | "AWS" leaks the bridge (amazon-bezos) | **fixed.** Dropped. |
| 4 | "accountant" in the relational MC pool | **fixed.** 6 items dropped; 0 left in the bank. |
| 5 | arithmetic fracsmall null pool < 8 | **fixed.** The 10 flagged originals are dropped; 6 fracsmall items remain. |
| 6 | buggy_code twins not atomic | **fixed.** Authored twins are grouped in `select`; 16 authored items, 0 unpaired. buggy_code is 41/49 (`partial`). The "review 4/4" leg doesn't exist in the source gate, and the doc claim is removed. |
| 7 | relational skew (cousin in 68/100) | **improved, not solved.** Per-relation cap (20 new uses per relation) and re-auto: the bank is now 62 items with cousin 20, sibling 18, tutor 16 (cousin is 32% of what remains). Status `partial` (62/100; refill stopped yielding; `ooc` is kept for banks under half the target, like the 4B's 22). Read it per relation. |
| 8 | brew ships 3 items as `partial` | **fixed (labelled).** Status `untried`, `exclude_from_macro: true`. The ladder was not run: the 4B scored 0/460. |
| 9 | agentic `am-blackmail-full` prefill never blackmails; a control misbehaves at 0.375 | **fixed / kept.** blackmail-full is dropped from the bank (14 items). The murder control is kept; rate 0.375 is its own arm's measured rate, and the judge reads controls as controls. |

## Since the audit
- **New gate legs:** chain `first` (start number first) and the bridge question for multihop originals. 9B re-gated: chain 120/120 full; multihop 100/100 full, with 81/100 originals passing both legs.
- **Back-filled report entries** for agentic (14/32 after the drop), hallucination 149, jailbreak 86 and mcdm 27. These banks existed but had no entries.
- **jlens_concept_pr:** built (299 items) with a J-lens **we fitted** (neuronpedia has none for the 9B): official estimator, neuronpedia recipe, n=400. Sanity check (current token in top-10) is 0.43–0.53 at 30–55% depth, vs 0.46–0.62 for neuronpedia's 4B lens.

## Prompt-only floors (measured 2026-10-18)
Reader = the stock 9B, frozen floor template; **judge `claude-opus-5-5`** (keyless OAuth), one layer;
`floors/floors.json`. Compared with the 27B frozen floors, the floor is notably higher on
user_modeling (0.50 vs 0.07), conjunctive (0.31 vs 0.07), arithmetic (0.32 vs 0.15) and
multilingual_multihop (0.69 vs 0.45). It is lower on poetry (0.31 vs 0.71) and multilingual_mt
(0.29 vs 0.42). Read 9B lens scores against these floors. role_bound is saturated (1.00), as on
the 27B. Full table: `adapted/README.md`.

## Addendum 2026-10-25: brew_intermediates re-gated in the read render
- The 35B-A3B audit defect (brew gated with a system turn the lens never sees) was present in this set's old records for the 4B and 9B; the 0.8B and 2B records were already system-free.
- All 100 originals re-gated in the read render (chat, no system turn, prefill `Answer:`, T=0.8 / top_p .95, greedy + 10/10), then the ladder walked (t0 10 rows, t1 6, t2 5; depth 2; ~400 generated per tier).
- Result: still `ooc`, out of the macro (see report.json note). The 10/10-at-T=0.8 bar is binding: no tier reaches the 3% yield. Bank = the few passing items only.

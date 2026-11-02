# Response to the Qwen3.6-35B-A3B audit (AUDIT.md, 2026-10-19)

The audit is left as written. Applied 2026-10-19 (log `/workspace/agam/logs/q35b-audit-fix.log`).
Drops are in `report.json` → `drops`, with reasons. Frozen originals under `evals/` were not edited.

## Findings
| finding | action | result |
|---|---|---|
| brew gated in a different render from the one it is read in (system turn, no `Answer:` prefill) | **skill fix:** `families._brew` now asks exactly like the bank's own gate and read plan (chat, no system turn, prefill "Answer:"). Originals re-gated with `profile regate=true`; new items with `gate regate=true`. | Originals passing 22 → 20/100; the 110 previously passing new items → 54 pass. Bank **74/100, partial**. The old render overstated brew capability. |
| arithmetic null pool < 8 (31 items) | **skill fix:** freeze drops items, with their twins, until every pool has ≥ 8 peers (this recurred in all 3 audits) | 49 dropped (the 31 plus twins). Bank **547/596, partial**. `select` now applies the same rule, so `auto` counts what ships. A re-run refilled nothing: 799/1521 new candidates pass, but these small variants can't reach a pool of 8 within their quota. The shortfall is structural, not a capability limit. |
| single-token natural names in new `*_mt` (11) | dropped, refilled | basic_readout_mt 100, multihop_mt 100, multilingual_mt 100, multilingual_multihop 98: all full |
| multihop bridge/target overlap (Vietnam/Vietnamese, Persia/Persian) | dropped, refilled | multihop 100/100 |
| moral `ec-ventilator-chat_tf/_yn`: no reason supports the committed side | dropped | moral 173/200 (untried: no refill path) |
| agentic `am-leaking_explicit-america_restriction`: prefill declines to leak | dropped from the bank | agentic 16/32 (partial) |
| stale brew header (27B gate_config) | not changed: the header describes the source bank; adapt metadata sits under `adapt` | — |
| new items easier than originals (12/18 families); composition shifts (typo_mt arith 15 → 0, mhmt 3hop 32 → 25, relational only 52/100 in chat) | reported, by design | read scores beside the subject's floors |

## Also new
- **jlens_concept_pr: full (299 items).** It uses a J-lens **we fitted** (neuronpedia has none for
  this model): official estimator, neuronpedia recipe, n=392, dim_batch 32. Sanity check (current
  token in top-10): 0.42–0.56 at 30–70% depth, on par with the Qwen3.5 lenses.

## Prompt-only floors (claude-opus-5-5, one layer; measured BEFORE the fixes above)
Most families didn't change. Brew (now 74 items) and arithmetic (now 547) were measured on the
pre-fix banks, so re-measure those two before quoting them. Large shifts from the 27B floor:
user_modeling 0.47 (27B 0.07), conjunctive 0.30 (0.07), arithmetic 0.53 (0.15),
multilingual_multihop 0.78 (0.45). Saturated (at the ceiling): brew 1.00 (27B 0.96),
role_bound 1.00, typo 1.00. Full table: `floors/floors.json`.

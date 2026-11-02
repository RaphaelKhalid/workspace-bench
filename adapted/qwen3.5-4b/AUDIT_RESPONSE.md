# Response to the Qwen3.5-4B audit (AUDIT.md, 2026-10-17)

The audit is left as written. This file records what was changed because of it. Every item drop is
in `report.json` → `drops[family][id]` with its reason; `freeze` and the refill honour that list,
and the frozen originals under `evals/` were not edited.

## Fixed in code
| finding | fix |
|---|---|
| `wsbench plan` used the 27B jlens manifest (259/299 positions wrong) | jlens plan reads the adapted manifest via the bank root; the subject's rollout ids ship as `jlens_concept_pr/items.json` and ride in the plan (`extra.input_ids`). Verified: 0/299 position mismatches |
| `wsbench plan` (all families) aborted on brew | under `WSB_BANK_ROOT`, families without an adapted bank (ooc) are skipped |
| single-token natural names uncreditable in `*_mt` (13 items) | dropped; new lint rule rejects any required multi-token unit whose canonical name is one token |
| role reuse → same-role MC distractors (23/100) | per-role cap (12 appearances) in `select`; role_bound authoring now lists used roles as ALREADY-USED; refill queued |
| moral items kept the 27B's `gate_pass=False` (14) | `moral.apply` restamps `gate_pass` / `gate_aligned` / `gate_committed_token` / `gate_reason_side_ok` from the subject's own gate |
| agentic items with rate <=0.25 (7) | `MIN_RATE = 0.375` in the agentic build |
| buggy_code grader schema 400 on the Claude route | `llm.anthropic_schema` strips numeric bounds before the Anthropic call (bounds stay in the prompt and `validate`) |
| `br-proc-arith-7+2` accepts "ten" | recorded patch in `report.json` → `patches`: "nine" in the adapted copy (frozen bank defect, unchanged) |

## Items dropped (50; see `report.json` drops)
basic_readout 2 (gold in prompt) · poetry 1 (gold in line 2) · multilingual 1 (stem leak) ·
multilingual_typo 1 (forms echo prompt) · multihop_mt 11 (one-token natural names, incl. the
"Buenos Aires, Argentina" alt) · multilingual_multihop 10 (7 bridge/target overlaps or leaks, 3
one-token names) · multilingual_mt 2 · buggy_code 2 (not bugs as written) · agentic 8 (2 prefills
not misaligned, 6 at rate <=0.25) · arithmetic 7 (fraccomp variant: null pool under 8) ·
moral_rationale 1 (no opposite-side reason) · relational 4 ('accountant' in the MC pool).

Spare passing items refilled poetry, multilingual, multilingual_typo, multilingual_mt and buggy_code
to their targets automatically. Refilled after the audit (2026-10-17 11:00 UTC; all back to target):
role_bound 80→100 (role-capped), multihop_mt 94→100, multilingual_multihop 91→98, basic_readout 99→100.

## Not changed (reported)
- **relational_multihop** stays `ooc` (22 items) and is excluded from the 4B macro: the kinship
  skew and weak composition evidence are capability findings, not fixable by more items.
- **Difficulty/composition shift** (easier tiers, fewer languages, crash-type bugs): by design of
  the adaptation; every 4B score must be reported beside a re-measured prompt-only floor.
  **Floors will be measured with a Claude judge (`claude-opus-5-5`, keyless OAuth)** instead of
  OpenRouter/Gemini, reader = the stock 4B, into `adapted/qwen3.5-4b/floors/floors.json`.
  **Measured 2026-10-18** (table in `adapted/README.md`). The difficulty shift shows up where the
  audit expected: user_modeling's floor is 0.48 (27B 0.07), conjunctive 0.25 (0.07), arithmetic
  0.40 (0.15), directed_modulation 0.40 (0.21). Read 4B lens scores on those families against
  these floors, not the 27B's. role_bound stays saturated (1.00, as on the 27B).
- **agentic on claude-opus-5-5**: the text stage sends `thinking: disabled`, which Opus rejects;
  the family's pinned judge (claude-sonnet-5) works. Use Sonnet for this family in an all-Opus run.
- Inherited original defects (bf-sherlock "detective", mlh-id-hailstone plural, stale addmul twin
  pointers, directed_modulation header naming the 27B) are listed in AUDIT.md for the frozen-bank
  owners.

## Addendum 2026-10-25: brew_intermediates re-gated in the read render
- The 35B-A3B audit defect (brew gated with a system turn the lens never sees) was present in this set's old records for the 4B and 9B; the 0.8B and 2B records were already system-free.
- All 100 originals re-gated in the read render (chat, no system turn, prefill `Answer:`, T=0.8 / top_p .95, greedy + 10/10), then the ladder walked (t0 10 rows, t1 6, t2 5; depth 2; ~400 generated per tier).
- Result: still `ooc`, out of the macro (see report.json note). The 10/10-at-T=0.8 bar is binding: no tier reaches the 3% yield. Bank = the few passing items only.

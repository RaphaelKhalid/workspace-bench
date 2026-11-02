# Response to the OLMo-3-7B-Instruct audit (AUDIT.md, 2026-10-21)

The audit is left as written. Applied 2026-10-21 (log `/workspace/agam/logs/olmo7-audit-fix.log`).
All 44 recommended drops are in `report.json` → `drops`.

| finding | action |
|---|---|
| 21 new `*_mt` items fail the natural-name test (gated before `natural.py`) | dropped (none patched); multihop_mt, basic_readout_mt, multilingual_multihop and multihop refilled through the screen |
| GE initials leak, Shelley overlap | dropped |
| duplicate prompt (`fr-opposite-high`) | dropped |
| 2 partial-answer passes in multilingual_typo | dropped; the strict rubric now rejects partial answers (cache key `strict2`) |
| 12 moral reasons on the wrong side or neutral | dropped; `moral.apply` now runs a Claude reason-vs-side check (`_verify_sides`) |
| 3 agentic prefills (incl. a control picked from a PARSE_ERROR rollout) | dropped from the bank |
| relational scene colliding with the MC pool ("accountant") | dropped |
| statuses: arithmetic `ooc` → `partial`; multilingual_mt → `ooc` (empty) | corrected; entries back-filled for hallucination, jailbreak, mcdm |
| macro | `exclude_from_macro`: multilingual_mt, role_bound, buggy_code, brew |
| role_bound 0/160: answers name people, not roles | **open:** needs a grader that maps names to roles (note in report.json) |
| composition collapse (multilingual mt families 1–4 languages; fewer 3-hop / depth-3 / structural items) | reported; read every family beside its floor |

jlens_concept_pr: our fitted instruct lens (n=600), 299/299 consistent. Floors:
`floors/floors.json` (measured just before this refill).


## Addendum 2026-10-23: brew_intermediates unblocked
- **Read cells:** re-derived in this subject's own chat_prefill render (prompt as the user turn + prefill `Answer:`) by `src/wsbench/adapt/brew_port.py`, called from `freeze`. The stir / start / question regions are every token overlapping each line; the emission cells go by template role. Example: the cells read `assistant / \n / :` at positions 171, 172, 174, against Qwen's 158 / 162 / 164.
- **Checks:**
  - every Qwen cell char-maps onto a subject cell of the same region: **0 mismatches** over all 100 items;
  - the same function reproduces the frozen Qwen3.6 cells 100/100;
  - every plan position decodes to the ported token (0 mismatches);
  - a `wsbench judge dry_run` expects 9,900 headline cells with 0 missing.
- **Gate:** the originals were first gated in the wrong render (with a system turn), the 35B-A3B audit defect. They were re-gated in the read render (chat, no system turn, prefill `Answer:`, T=0.8 / top_p .95, greedy + 10/10): **11/100** pass. The family was then filled with 89 generated items at t0 (10 rows, depth 2; 96/1010 candidates passed). It is now **full, 100 items**.
- **Not done:** no independent audit of the generated brew items; there are no OLens readouts or scores on this family yet.

## Addendum 2026-10-24: role_bound format fix (0 -> 100)
- OLMo-3-7B answered "who did what to whom" with names ("Tony shaved Hank."), though the question already asks for roles; the gold is "the barber shaved the fisherman". 0/160 passed.
- Grader: the existing name-to-role rewrite (`families._role_bound` name_roles: each name -> "the <role> (<name>)", direction intact) had been added after this set was gated and was never applied here. Re-grading the stored greedy answers (the family's rule is greedy-only asked-open) passes 80/160 (35 originals, 45 authored). Spot checks: "Jack robbed Omar." = the pirate robbed the merchant.
- Ask: an `ask_roles` gate variant ("Answer with their roles or occupations, not their names.") recovers 11 of the 80 still failing; most failures describe a different event ("Dev delivered crates to Marisol" for "the shop owner cheated the supplier"), i.e. real misses.
- Refill: one authored wave, +34 at 57% yield. **Bank 100/100, pairs atomic, max role use 4.** Status full, back in the macro. Gate-only change: the read plan (stimulus + summarize suffix) never uses the asked question.

## Addendum 2026-10-24: response to AUDIT_2026-10-23.md

- **brew_intermediates:** the audit's 5 teal drops were applied. Re-freezing refilled toward teal, so 2 more teal items were dropped. Result: 98 items, teal 19/98 (≤ 20%).
- **role_bound_association:** a strict grader mode was added (`ADAPT_ROLE_BOUND_STRICT=1`; an answer must state both roles, with no name→role rewrite). Re-grading the 100 kept greedy answers offline under it leaves **0/100**: every answer names only the people. The bank text is unchanged. role_bound is now `exclude_from_macro` (report.json note) until a strict-gated set reaches ≥ 50 atomic-pair items. Per-item results: `outputs/fix_1024/role_strict.json`.

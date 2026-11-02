# Response to the qwen3.5-2b audit (AUDIT.md, 2026-10-21)

The audit is left as written. Applied 2026-10-21: every recommended drop is recorded in `report.json`
→ `drops`, and the set was re-frozen. agentic and hallucination drops were removed from those banks
directly. No refill: this is a small subject, and short families stay short and labelled.

- **Macro exclusions** set as recommended (8 families each; see `report.json` → `exclude_from_macro`).
- **Report entries** back-filled for hallucination, jailbreak_recognition and mcdm; stale status and
  notes corrected (2B arithmetic `freeze_notes`; 0.8B multilingual_multihop → `ooc`).
- **Skill fix:** the strict grader accepted part of a multi-word answer ("gigi" for "dokter gigi").
  `STRICT_FORM` now says a partial answer is wrong, and its cache key is versioned (`strict2`) so
  lenient verdicts aren't reused.
- **Skill fix (recurring in every audit):** moral items whose stored reason argues the other side
  are dropped here, and `moral.apply` now runs a Claude check of reason vs committed side
  (`_verify_sides`). It caught 7/7 of this audit's 2B flags with 0/10 false rejections.
- Patches the audit suggested (2B association `bf-newyear` gold, typo_mt "roller coaster" form)
  are not applied yet.
- **Floors:** `floors/floors.json` once tmux `small-floors` finishes.

## Addendum 2026-10-25: brew_intermediates re-gated in the read render
- The 35B-A3B audit defect (brew gated with a system turn the lens never sees) was present in this set's old records for the 4B and 9B; the 0.8B and 2B records were already system-free.
- All 100 originals re-gated in the read render (chat, no system turn, prefill `Answer:`, T=0.8 / top_p .95, greedy + 10/10), then the ladder walked (t0 10 rows, t1 6, t2 5; depth 2; ~400 generated per tier).
- Result: still `ooc`, out of the macro (see report.json note). The 10/10-at-T=0.8 bar is binding: no tier reaches the 3% yield. Bank = the few passing items only.

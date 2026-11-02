# Response to the qwen3.5-0.8b audit (AUDIT.md, 2026-10-21)

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

## 2026-10-24 refill review ("can we really not get good questions for 0.8B?")
Re-read every absent/excluded family's gate log, then ran new waves (generation on Modal vLLM via
`ADAPT_BACKEND=modal`, same template, sampling and gate rule; grading local). Report:
`outputs/q08b_refill/REPORT.md`.
- **poetry 1 -> 100 (full, back in the macro).** Format fix, not a bar change: the 0.8B restates
  the couplet in chat and emits digits in plain. New opt-in `chat_prefill` render (assistant turn
  prefilled with line 1 + the line-2 stem; latent and read site unchanged; `gate_variant:
  chat_prefill`, read at `last_newline`). Grader fix: an echoed stub tail is skipped before the
  committed word is taken (gate.own_word). 36 originals + 64 authored common rhymes.
- **role_bound 0 -> 100 (full).** Authored scenes whose setting makes both roles explicit; originals
  fail because the 0.8B names the people, not the roles.
- **user_modeling 52 -> 100.** +48 selfdescribe (strong cues). 42 synthsys originals remain, so it
  stays excluded until an audit decides; read selfdescribe separately.
- **typo_mt 5 -> 29 (partial, excluded).** Lint-bound: common long words are single tokens.
- Confirmed out of capability (evidence in report.json notes): chain, arithmetic (one step only),
  relational (one hop), multihop_mt, multilingual_mt, multilingual_multihop, multilingual (1/21
  high-resource pilot), multilingual_typo, buggy_code (1/32 pilot, no atomic pair), moral (57 of
  its 61 consistent sides are no/false). brew left to the brew-tokenizer work.
- These new items were not independently audited; an audit pass on poetry / role_bound /
  user_modeling is the next step before they enter a published macro.

## Addendum 2026-10-24: response to AUDIT_2026-10-23.md

- **poetry:** the audit's 11 idiom drops were applied (100 → 89). Then one authored wave (wave 300, chat_prefill, same gate) was steered with "line 2 must not be a fixed idiom; the rhyme must be guessable from line 1 alone; everyday words": 40 candidates, 11/40 passed the gate. All 11 were spot-checked with the audit's own criterion (Opus lists the top-5 rhymes from line 1 only). 9 pass; 2 were dropped (play→stay, bright→tight). Final: **98 items**. The re-freeze pulled in no unaudited items. Check: `outputs/fix_1024/poetry_w300_check.json`.
- **role_bound_association:** under the new strict grader (`ADAPT_ROLE_BOUND_STRICT=1`; both roles must be stated) **0/100** kept answers survive: all name only the people. The bank text is unchanged. role_bound is `exclude_from_macro` until a strict-gated set reaches ≥ 50 atomic-pair items (`outputs/fix_1024/role_strict.json`).
- **user_modeling:** the floor was re-measured with `ADAPT_FLOORS_FAMILIES=user_modeling`. It is .56 overall (n=100): selfdescribe .845 (n=58), synthsys .167 (n=42). The selfdescribe floor is saturated, so the family stays excluded (report.json note).

## Addendum 2026-10-25: brew_intermediates re-gated in the read render
- The 35B-A3B audit defect (brew gated with a system turn the lens never sees) was present in this set's old records for the 4B and 9B; the 0.8B and 2B records were already system-free.
- All 100 originals re-gated in the read render (chat, no system turn, prefill `Answer:`, T=0.8 / top_p .95, greedy + 10/10), then the ladder walked (t0 10 rows, t1 6, t2 5; depth 2; ~400 generated per tier).
- Result: still `ooc`, out of the macro (see report.json note). The 10/10-at-T=0.8 bar is binding: no tier reaches the 3% yield. Bank = the few passing items only.

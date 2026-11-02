# Adaptive WorkspaceBench: per-model sets

Every frozen bank under `evals/` was gated on Qwen3.6-27B. For any other subject, use that
subject's adapted set: the same families and item format, but every item is one THIS model
computes (re-gated on it; failures replaced by easier items of the same kind; model-specific
families regenerated on it). How the sets are built: `.claude/skills/adapt-bank/SKILL.md`.

**No multi-token multihop family (2026-10-30, plan 0041).** `multihop_mt` was removed from the
bench (superseded by `multihop_mt_v2`), and every adapted `multihop_mt.json`, report and floor
entry with it. Multihop_mt_v2 is not portable yet (its shortcut gate is model-specific): the adapted sets have no
multi-token multihop family until it is ported with its gate re-run per subject.


**MCDM re-carried at 100 items (2026-10-29, plan 0025).** `multi_concept_directed_modulation.json`
was re-carried from the expanded bank (`python -m wsbench.adapt carry model=<m>
families=multi_concept_directed_modulation`) for every adapted model except **glm-5.3-flash** and
**kimi-k2**, whose tokenizer dirs (`/workspace/agam/hf_tok/…`) live on Agam's box: their MCDM
banks are still the 27-item set (no concept edits) until re-carried there. The 27-item counts in
the per-model AUDIT.md / SET_AUDIT.md files predate this.

## Where each model's set lives

| subject | set | status | audit |
|---|---|---|---|
| Qwen3.6-27B | `evals/` (the frozen banks; they ARE its set) | reference | — |
| Qwen3.5-4B | `adapted/qwen3.5-4b/` | **audited; usable** (25 banks + jlens dir; exclude relational from the macro). | `adapted/qwen3.5-4b/AUDIT.md` + `AUDIT_RESPONSE.md` |
| Qwen3.5-9B | `adapted/qwen3.5-9b/` | **audited; usable** (audit fixes applied, chain/multihop re-gated with new legs, floors measured); jlens bank built (299 items) with **our fitted 9B J-lens** (neuronpedia has none) | `adapted/qwen3.5-9b/AUDIT.md` + `AUDIT_RESPONSE.md` |
| Qwen3.5-2B | `adapted/qwen3.5-2b/` | **audited; usable as a narrow bank** (20 drops; 11 full; 7 families out of the macro: relational, buggy, multilingual_mt/_multihop, arithmetic, chain, role_bound) | `adapted/qwen3.5-2b/AUDIT.md` + `AUDIT_RESPONSE.md` |
| Qwen3.5-0.8B | `adapted/qwen3.5-0.8b/` | **audited; usable as a narrow bank** (16 drops; read association, basic_readout(_mt), multihop, typo, conjunctive, directed_modulation + regenerated families); 2026-10-23/24: poetry 98 (chat_prefill format fix; audit idiom drops, refilled and spot-checked), role_bound 100 but out of the macro (0/100 pass the strict role grader), user_modeling 100 out of the macro (selfdescribe floor .845), typo_mt 29 partial; audit `AUDIT_2026-10-23.md` | `adapted/qwen3.5-0.8b/AUDIT.md` + `AUDIT_RESPONSE.md` |
| OLMo-3-7B-Instruct | `adapted/olmo-3-7b/` | **audited; usable** (44 drops; mt refill through the everyday-name screen); jlens 299 on **our fitted instruct lens**; multilingual_mt empty (ooc), buggy 18: out of macro; role_bound 100 (lenient name->role grading) but out of macro: 0/100 pass the strict role grader | `adapted/olmo-3-7b/AUDIT.md` + `AUDIT_RESPONSE.md` |
| Qwen3.6-35B-A3B | `adapted/qwen3.6-35b-a3b/` | **audited; usable** (47 audit drops; arithmetic 547 after the null-pool rule; jlens 299 on **our fitted lens**, sanity 0.42-0.56); floors measured (arithmetic pre-fix) | `adapted/qwen3.6-35b-a3b/AUDIT.md` + `AUDIT_RESPONSE.md` |
| OLMo-3.1-32B-Instruct | `adapted/olmo-3.1-32b/` | **audited; usable** (50 drops refilled via the everyday-name screen; strict-regraded); 17 full incl. jlens 298 on **our fitted instruct lens**; multilingual_mt only 29, relational 42 (out of macro), agentic 12/32; floors measured | `adapted/olmo-3.1-32b/AUDIT.md` + `AUDIT_RESPONSE.md` |
| Qwen3-8B | `adapted/qwen3-8b/` | **audited; usable** (71 drops, refilled via the everyday-name screen; strict-regraded; layers snapped to its lens band 12..34 even); 17 full incl. jlens 299 on **our fitted lens**; relational 10 ooc (out of macro); floors measured | `adapted/qwen3-8b/AUDIT.md` + `AUDIT_RESPONSE.md` |
| Gemma-4-31B-it | `adapted/gemma-4-31b-it/` | **audited; usable** (BOS fix for plain renders, plain legs re-gated; 55 drops refilled; 19 full); relational blocked (tokenizer); jlens 299 on **our fitted lens** (trimmed mean + final-norm readout; sanity 0.20-0.64); moral 161 (system_one_word gate variant, 2026-10-23; back in the macro, needs readouts with the system turn); floors measured (pre-BOS) | `adapted/gemma-4-31b-it/AUDIT.md` + `AUDIT_RESPONSE.md` |
| Kimi-K2-Instruct-0905 | `adapted/kimi-k2/` | **built; mechanical audit only** (SET_AUDIT.md: lint/leak/dup/gate; no independent Opus audit yet). Gated on K2 via gw-olens adapt_mp_subject_modal.py (B300:8, HF model-parallel); refilled association, *_mt, role_bound, user_modeling, buggy, chain, relational; relational 90 (9 scenes dropped: K2 merges the possessive into the name); no agentic / jlens. OLens scored: `/workspace/agam/olens_report/adaptive_scores_kimi-k2.md` (inv .582 / student .588 / RL .746, 23 fams). Normal-bank gate + re-golded own-answer banks: `outputs/normal_gated/kimi-k2/` | `adapted/kimi-k2/SET_AUDIT.md` |
| GLM-5.3-Flash | `adapted/glm-5.3-flash/` | **built; mechanical audit only** (SET_AUDIT.md). Gated on GLM via gw-olens adapt_mp_subject_modal.py (H200:4, HF model-parallel; gw-olens no-think template); plain renders carry GLM's `[gMASK]<sop>` (template.bos_prefix) and the plain-leg families were re-gated with it. Refilled association, basic_readout, *_mt, multilingual_typo, role_bound, user_modeling, chain, relational, arithmetic (566); buggy 32/49, conjunctive 54 (no brief), directed_modulation 76, moral 123; no agentic / jlens. OLens scoring (inverter + student; RL still training): `/workspace/agam/olens_report/adaptive_scores_glm-5.3-flash.md`. Normal-bank gate + re-golded own-answer banks: `outputs/normal_gated/glm-5.3-flash/` | `adapted/glm-5.3-flash/SET_AUDIT.md` |

**Fitted J-lenses** (9B, OLMo-3-7B-Instruct): `scripts/fit_jlens_modal.py`, the official estimator
with neuronpedia's recipe (WikiText-103, 128 tokens, final-layer target), files in
`/workspace/agam/jlens_fits/<tag>/lens.pt` + `meta.json`. Recipe validated on the 4B against
neuronpedia's own lens: per-layer cosine min 0.927, mean 0.986.

Per family counts, statuses (full / partial / ooc / blocked) and one-line notes on what changed:
`adapted/<model>/report.json`. A family that is `ooc` (out of capability) or `blocked` has fewer
items or none; report it, don't fall back to the 27B bank.

## Interactive viewer (scores + readouts, every model and question)

`viewer_app/` (FastHTML), served from tmux `wsb-viewer` on 127.0.0.1:5077. From the Mac:
`ssh -N -L 5077:127.0.0.1:5077 runpod`, then open http://localhost:5077. Restart:
`viewer_app/README.md`. Filters by model, family, layer and stage; side-by-side readouts; per-judge
pass/fail. OLens per-item readouts that only live on Modal volumes show scores only.

## Prompt-only floors (report every score beside these)

**Status: measured for all 9 sets** (4B/9B 2026-10-18; 35B-A3B, Qwen3-8B, OLMo-32B, Gemma 2026-10-19; 2B, 0.8B, OLMo-7B 2026-10-21). Per-set tables: `adapted/<model>/floors/floors.json`. Caveats: Gemma's were measured before the BOS fix, and OLMo-7B's before its audit refill. Small-set highlights: typo 2B 0.90 / 0.8B 0.69 / OLMo-7B 0.92 (near-saturated), user_modeling 0.51 / 0.27 / 0.35, conjunctive 0.04 / 0.02 / 0.09.

Judge `claude-opus-5-5`, one layer (`complete: false` by construction, as for the 27B floors); `adapted/<model>/floors/floors.json`.

| family | 4B floor (n) | 9B floor (n) | 27B floor | note |
|---|---|---|---|---|
| arithmetic_intermediates | 0.40 (469) | 0.32 (517) | 0.15 | floor up 2.6x (easier variants) |
| association | 0.28 (100) | 0.39 (100) | 0.29 |  |
| basic_readout | 0.79 (100) | 0.85 (100) | 0.72 |  |
| basic_readout_mt | 0.63 (100) | 0.66 (100) | 0.59 |  |
| buggy_code | 5.88 (43) | 4.72 (41) | — | 1-10 score (27B entry not comparable) |
| chain_intermediates | 0.02 (120) | 0.03 (120) | 0.03 |  |
| conjunctive_association | 0.25 (96) | 0.31 (93) | 0.07 | floor up 3.5x |
| directed_modulation | 0.40 (94) | 0.32 (100) | 0.21 | floor up 2x |
| moral_rationale | 0.58 (143) | 0.62 (151) | 0.49 |  |
| multihop | 0.89 (100) | 0.95 (100) | 0.90 |  |
| multilingual | 0.75 (100) | 0.90 (100) | 0.76 |  |
| multilingual_mt | 0.21 (100) | 0.29 (100) | 0.42 |  |
| multilingual_multihop | 0.61 (97) | 0.69 (98) | 0.45 |  |
| multilingual_typo | 0.68 (100) | 0.75 (100) | 0.66 |  |
| poetry | 0.03 (100) | 0.31 (100) | 0.71 | floor down (unchecked: the 4B reader may rarely name the rhyme) |
| relational_multihop | 0.64 (22) | 0.73 (62) | 0.82 |  |
| role_bound_association | 1.00 (100) | 1.00 (100) | 1.00 | saturated by design (scene states the answer), as on the 27B |
| typo | 0.87 (100) | 0.99 (100) | 1.00 |  |
| typo_mt | 0.87 (100) | 0.89 (100) | 0.67 |  |
| user_modeling | 0.48 (100) | 0.50 (100) | 0.07 | floor up 7x: selfdescribe items are guessable from the prompt (originals 23/27, authored 24/24; synthsys 1/49), and the 4B bank is 51% selfdescribe; Opus judge vs the 27B floor's Gemini may add to it. Read selfdescribe and synthsys separately |

`adapted/<model>/floors/floors.json` (per-family rates; summaries and judge outputs beside it).
Measured with `scripts/adapt_box.sh floors model=<m>`: the **stock subject itself** reads the exact
prompt up to each read token with the frozen floor's template (k=1, T=1.0, 256 tokens, at most 32
positions per item); the summaries are scored by each family's own judge with
**`claude-opus-5-5`** (keyless OAuth; no OpenRouter/Gemini on this box), so floors are on the same
judge as an all-Opus lens run. Not measured (as for the 27B floors): jailbreak_recognition and
agentic_misalignment (Sonnet-pinned), multi_concept_directed_modulation, jlens_concept_pr.

The `hallucination` family and its per-model banks (`hallucination.json`,
`hallucination.capture_rows.json`) were removed on 2026-10-30 (plan 0040): HallucinationBench
replaced it. The dated `AUDIT*.md` files still describe them.

## How to run (judging)

Set `WSB_BANK_ROOT` and use the normal CLI; every family then loads `adapted/<model>/<family>.json`
(a family missing there is an error, never a silent fall-back):

```bash
export WSB_BANK_ROOT=adapted/qwen3.5-4b
wsbench plan out=plans/qwen3.5-4b            # per item: render, read positions, layers
# ... produce readouts with your lens ...
wsbench run all=True readouts_root=READOUTS_DIR out=RESULTS_DIR
wsbench report dir=RESULTS_DIR
```

## How to produce readouts (read the plan, not the bank)

Under `WSB_BANK_ROOT`, `wsbench plan` (or `wsbench.readplan.plan(family)`) is the contract. Use it
rather than re-deriving renders from the bank files:

- **Layers are the subject's own.** The plan remaps every 27B grid by depth
  (`round(L * n_layers / 64)`; 4B/9B: 32 blocks, so 20..60 step 4 becomes 10..30 step 2). Do NOT
  remap again. If your lens reads only some layers, ask for a `read_band` on the subject (the
  plan and bank-stored layers then snap to it; Qwen3-8B: even 12..34) rather than snapping yourself.
- **Renders and positions are per item.** In particular:
  - `poetry`: items whose rhyme the subject committed to in the chat render are planned in that
    render (`render: chat`, the gate's own continue instruction); the rest are `plain`.
  - `basic_readout` implicit items: `chat_prefill` with "My one-word answer is:".
  - `jlens_concept_pr`: bank directory `adapted/<model>/jlens_concept_pr/` (manifest + the
    subject's own J-lens top-10 reference at the subject's layers).
  - `agentic_misalignment`: prompt positions only; `prefill` is the subject's own misaligned
    rollout (reference for the judge, never shown to the lens).
- Layers stored inside a bank (`buggy_code` header `read_cells`, `arithmetic` `cell.layer`,
  `multi_concept_directed_modulation` header `layers`) are already the subject's.

## Keeping this current

The adapt-bank workstream updates this table when a set is built, audited or changed. Rebuild a
set: `scripts/adapt_box.sh freeze model=<m>` after gating (see the skill).

## Work products not in git

Gate logs (`gate/`), candidates (`cand/`), J-lens fits (`jlens_work/`, `jlens_concept_pr/gen-*/`),
floor readouts and judge dirs (`floors/{readouts,results}/`) and the grade cache stay on the RunPod
box under `/workspace/agam/workspace-bench/adapted/` (git-ignored; ~27 GB). The frozen banks,
`report.json`, audits and `floors/floors.json` are committed.

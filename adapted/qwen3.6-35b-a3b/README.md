# WorkspaceBench adapted to Qwen3.6-35B-A3B

Subject: `Qwen/Qwen3.6-35B-A3B` @ `995ad96eacd98c81ed38be0c5b274b04031597b0` (MoE, ~3B active,
40 blocks). Built 2026-10-18/19 with `.claude/skills/adapt-bank` on the Modal backend (deployed app
`adapt-subject-llm`, vLLM on an H200, max_model_len 4096, thinking off).

**Tokenizer = the banks' own Qwen3.6 tokenizer.** Verified: `len(tokenizer)==248077`,
`<|im_end|>`=248046, vocab and chat template are identical to Qwen3.6-27B's, and the no-think render
matches byte for byte. So every token-tied field carries over unchanged (multihop offsets, mt
`probe_token_lens`, jailbreak `read.tokens`, mcdm `last_n`). Layers are remapped
by depth fraction (`GRID` → 12 15 18 20 22 25 28 30 32 35 38; arithmetic cells 56/60 → 35/38; mcdm
→ 28 32 35 38).

## How to use

```
WSB_BANK_ROOT=adapted/qwen3.6-35b-a3b wsbench plan families=<families present in report.json>
WSB_BANK_ROOT=adapted/qwen3.6-35b-a3b wsbench run families=... readouts_root=... out=...
```
List only the families present here (`jlens_concept_pr` is absent).

## Status per family (report.json is authoritative)

Gate: greedy right AND >= 8/10 sampled (10/10 chain); Opus-graded misses (`llm=claude-opus-5-5`).

| family | status | items / target | originals passing | new | how refilled |
|---|---|---|---|---|---|
| arithmetic_intermediates | full | 596/596 | 466 | 143 | t0 (original ranges), per-variant quotas |
| association | full | 100/100 | 68 | 32 | t1 authored |
| basic_readout | full | 100/100 | 71 | 29 | t1 (implicit golds = subject's own favourite) |
| basic_readout_mt | full | 100/100 | 92 | 8 | t1 |
| buggy_code | partial | 37/49 | 25 | 12 | t1 waves (7%, 3%, 0%), t2 0%: stopped |
| chain_intermediates | full | 120/120 | 108 | 12 | t0 |
| conjunctive_association | untried | 56/100 | 56 | 0 | no fill (no author brief; same as 9B) |
| directed_modulation | untried | 96/100 | 98 | 0 | compliance-gated originals (pairs atomic) |
| jailbreak_recognition | full | 86/86 | - | - | carried over (same tokenizer) |
| jlens_concept_pr | **blocked** | 0 | - | - | no 35B-A3B J-lens on neuronpedia |
| moral_rationale | untried | 175/200 | 175 | 0 | side re-gated, reasons re-distilled on the subject |
| multi_concept_directed_modulation | full | 27/27 | - | - | layers remapped |
| multihop | full | 100/100 | 94 | 6 | t1 |
| multilingual | full | 100/100 | 99 | 1 | t1 |
| multilingual_mt | full | 100/100 | 86 | 14 | t1 |
| multilingual_multihop | full | 98/98 | 78 | 20 | t1 |
| multilingual_typo | full | 100/100 | 72 | 28 | t1 |
| poetry | full | 100/100 | 88 | 12 | t1 (gold = subject's own rhyme) |
| relational_multihop | full | 100/100 | 47 (14 kept as whole scenes) | 86 | t0 |
| role_bound_association | full | 100/100 | 46 (18 as whole ab/ba pairs) | 82 | t1; mix congruent 43 / incongruent 43 / neutral 14 |
| typo | full | 100/100 | 100 | 0 | - |
| typo_mt | full | 100/100 | 68 | 32 | t1 |
| user_modeling | full | 100/100 | 89 | 11 | t1 selfdescribe (no synthsys padding) |
| agentic_misalignment | partial | 17/32 | - | - | 8 rollouts x 32 on the subject; 13 misaligned kept (rate >= 0.375) + controls |

**jlens_concept_pr:** `neuronpedia/jacobian-lens` has only `qwen3.6-27b` among Qwen3.6 models. Needs a
fitted lens (`scripts/fit_jlens_modal.py`) before the bank can be built.

## Audit

Self-check only (5 random new items per refilled family, read by hand). It is not the independent
audit (runbook step 6), which is still to do. No defects found and nothing dropped. Spot checks:
arithmetic and chain values recomputed; buggy stdout claims checked;
mt items carry alias lists and multi-token targets. Minor: one multilingual_multihop item
(`Yupiter`) lists the English `Jupiter` as an alt. Floors (`floors model=qwen3.6-35b-a3b`) are not
yet measured.

Logs: `/workspace/agam/logs/adapt-q35b-*.log`. Pipeline scripts: `/workspace/agam/logs/steer/q35b-s{1,2,3}.sh`.

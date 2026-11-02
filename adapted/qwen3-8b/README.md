# WorkspaceBench adapted to Qwen3-8B

Subject `Qwen/Qwen3-8B` @ `b968826d9c46dd6066d109eabc6255188de91218` (36 layers, Qwen3 151k tokenizer,
thinking off). Built 2026-10-18/19 with `.claude/skills/adapt-bank` on the Modal backend
(`adapt-subject-llm`), gate = greedy right AND >= 8/10 (10/10 chain).

## How to use

```
WSB_BANK_ROOT=adapted/qwen3-8b wsbench plan        # emits Qwen3-8B layers (report.json n_layers=36)
WSB_BANK_ROOT=adapted/qwen3-8b wsbench run families=<only families listed below with items> ...
```
GRID remaps to layers 11 14 16 18 20 22 25 27 29 32 34. Per-family counts, notes and the audit
drops are in `report.json`; every gated candidate is in `gate/<family>.jsonl`.

## Status per family

| family | items / target | status |
|---|---|---|
| association, basic_readout, basic_readout_mt, multihop, multilingual, multilingual_mt, multilingual_typo, typo, typo_mt, user_modeling, poetry | 100/100 each | full |
| multilingual_multihop | 98/98 | full |
| chain_intermediates | 120/120 | full |
| jailbreak_recognition | 86/86 | full (read positions re-stamped for the Qwen3 tokenizer) |
| multi_concept_directed_modulation | 27/27 | full (layers 25 29 32 34) |
| jlens_concept_pr | 299/299 | full — J-lens **fitted by us (n=400)** (neuronpedia has none for Qwen3-8B): `/workspace/agam/jlens_fits/qwen3-8b/lens.pt` |
| arithmetic_intermediates | 466/596 | partial (frac*/floordiv quotas unfillable) |
| moral_rationale | 173/200 | untried (originals re-gated, reasons re-distilled; no new dilemmas) |
| conjunctive_association | 94/100 | untried |
| directed_modulation | 94/100 | untried (compliance screen) |
| role_bound_association | 42/100 | partial |
| buggy_code | 35/49 | partial |
| agentic_misalignment | 18/32 | partial (15 misaligned + 3 controls) |
| relational_multihop | 10/100 | ooc (`'s` is one token, so valid, but the subject rarely composes both hops) |

## Unusual things to know
- **poetry is read in the render it was committed in**: 94/100 items have `gate_variant: chat`, 6 `plain`.
- Tokenizer differs from the banks (Qwen3 vs Qwen3.6): `*_mt` probe_token_lens, multihop offsets,
  arithmetic cells and jailbreak positions were re-stamped at freeze/carry.
- The multilingual/typo families were re-graded with the strict-form grader (no translations or
  misspellings accepted) and refilled before the final freeze.
- Self-audit drops (report.json `drops`): 1 multihop_mt shortcut item (family removed 2026-10-30), 1 multilingual_typo leak item.
- No independent audit (`AUDIT.md`) yet.

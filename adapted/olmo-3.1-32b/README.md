# OLMo-3.1-32B-Instruct: adapted WorkspaceBench

Subject: `allenai/Olmo-3.1-32B-Instruct` @ `ac0587e4a7744a551c059d8cd17ba220bc940dae`, 64 blocks
(the read grids map 1:1 onto the 27B's layers), dolma2 100k tokenizer, ChatML template that injects
a default system prompt and has no think block (same family as `adapted/olmo-3-7b/`). Generation
ran on the shared Modal app `adapt-subject-llm` (H200, `backend="modal"`). Rendering, lint and
Claude grading/authoring (`claude-opus-5-5`, keyless OAuth) ran on the box. Built 2026-10-18/19.

**Status: built and self-checked only. No independent audit yet (SKILL step 6). Treat it as
provisional until `AUDIT.md` lands.**

## Run it

```
WSB_BANK_ROOT=adapted/olmo-3.1-32b wsbench plan ...      # report.json n_layers=64 -> subject layers
WSB_BANK_ROOT=adapted/olmo-3.1-32b wsbench run families=<families present in report.json> ...
```
List only families present here. `jlens_concept_pr` has no bank (blocked).
Prompt-only floors have not been re-measured (`scripts/adapt_box.sh floors model=olmo-3.1-32b`).

## Families

| family | status | items / target | originals passing | note |
|---|---|---|---|---|
| arithmetic_intermediates | partial | 500 / 596 | 282 | t0-t2 ladders; floordiv/frac/fraccomp short; cell.pos re-anchored on the OLMo render |
| association | full | 100 / 100 | 58 | t1 authored |
| basic_readout | full | 100 / 100 | 78 | implicit golds = subject's own favourite |
| basic_readout_mt | full | 100 / 100 | 55 | t1 "famous" entities |
| buggy_code | partial | 30 / 49 | 12 | 12 buggy + 18 clean; t2 crash bugs yielded 0/120 |
| chain_intermediates | full | 120 / 120 | 53 | t0 generator (both legs: surface + first) |
| conjunctive_association | untried | 82 / 100 | 82 | no refill attempted |
| directed_modulation | untried | 92 / 100 | 96 | compliance-gated; pairs atomic |
| jailbreak_recognition | full | 86 / 86 | - | read positions re-stamped (carry) |
| jlens_concept_pr | **blocked** | 0 | - | needs an instruct J-lens; the parent agent fits lenses |
| moral_rationale | untried | 156 / 200 | 156 | side + reasons re-distilled from the subject's draws |
| multi_concept_directed_modulation | full | 27 / 27 | - | layers [44,52,56,60] |
| multihop | full | 100 / 100 | 84 | t1 famous bridges |
| multilingual | full | 100 / 100 | 88 | t1 (fr/de/es/it/pt, easy relations) |
| multilingual_mt | partial | 42 / 100 | 14 | OLMo's L2 lexical recall is weak; 19 dropped in self-check (see below) |
| multilingual_multihop | partial | 96 / 98 | 19 | 5 dropped in self-check |
| multilingual_typo | full | 100 / 100 | 21 | |
| poetry | full | 100 / 100 | 95 | 93 committed in the `chat` render, 7 in `plain`: read the `gate_variant` render |
| relational_multihop | ooc | 42 / 100 | 18 | no full original scene passes; both scene items rarely pass together |
| role_bound_association | partial | 88 / 100 | 29 | 6 waves |
| typo | full | 100 / 100 | 97 | prompt-only floor is ~1.0 by construction |
| typo_mt | full | 100 / 100 | 54 | re-stamped for dolma2 |
| user_modeling | full | 100 / 100 | 80 | 53 selfdescribe / 47 synthsys: report them separately |
| agentic_misalignment | partial | 13 / 32 | - | 9 misaligned scenarios (rate >= 0.375) + 4 controls |

## Anything unusual
- **The LLM fallback grader accepts cross-language answers.** In `multilingual_mt` and
  `multilingual_multihop` the gate's Opus fallback marked English answers correct ("lollipop" for
  Vietnamese "kẹo mút", "J.K. Rowling" for "Джоан Роулинг"). It also accepted a few misspelled
  corrections ("légger", "ca phe"). The self-check dropped 31 such items: multilingual 4,
  multilingual_mt 19, multilingual_multihop 5, multilingual_typo 2 (reasons in `report.json`
  `drops`). Freeze then backfilled with clean passing spares where it had them. The grader rule
  itself is unchanged. Other subjects' multilingual banks probably have the same issue.
- OLMo-32B is much weaker than Gemma-4-31B on L2 lexical items and relational composition.
- `buggy_code`: authored clean twins are correct programs of similar length, but in 9 of 18 pairs
  they are a different function (e.g. ticket_type vs shoe_size_group).
- `arithmetic_intermediates`: `auto` labelled it `ooc` at 500/596. It was re-labelled `partial`
  by the SKILL rule (above half the target).
- Logs: `/workspace/agam/logs/adapt-olmo32-*.log`. Chain scripts: `/workspace/agam/logs/steer/olmo32-*.sh`.

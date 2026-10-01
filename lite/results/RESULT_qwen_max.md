# Result: an open-weights judge passes the judge-swap bar (PREREG_qwen_max.md, PREREG_qwen38_judge.md)

**Headline:**
- **Judge and prompt:** Qwen3.8-27B (Apache-2.0), with the official jb-v1 prompt plus a frozen voice note (`prompts/jb_v1_voice_note.txt`).
- **Agreement:** κ_rec **0.714** vs API Sonnet 5 on the 568 pre-registered clean test cells. That passes WorkspaceBench's judge-swap bar (Cohen's κ on the binary cell label ≥ 0.70, plans/0007).
- **Calibration:** 30.0 weighted recognitions, against Sonnet's 30.0.
- **Cost:** about $0.0005 per cell on DeepInfra, against $0.0055 for Sonnet 5 (11× cheaper). The weights are open, so it can also be self-hosted.

## Primary: 568 clean test cells (17 held-out items), sonnet_b1 weighted estimator
| judge vs Sonnet 5 | κ recognition | LB95 | κ 4-way | cells |
|---|---|---|---|---|
| **Qwen3.8-27B + voice note (judge)** | **0.714** | 0.552 | 0.660 | 561 (7 unjudged, 1.2%) |
| Kev-4B taught by Qwen3.8 + voice note | 0.582 | 0.419 | 0.623 | 568 |
| Kev-4B taught by GLM-5.3 Flash | 0.580 | 0.354 | 0.634 | 568 |
| Kev-4B taught by Qwen3.6-27B (R2) | 0.639 | 0.471 | 0.630 | 568 |
| Qwen3.6-27B, official prompt (zero-shot) | 0.693 | 0.527 | 0.619 | 530 |
| free Jev (zero-shot) | 0.654 | 0.459 | 0.661 | 568 |
| Kev-4B zero-shot | 0.561 | 0.373 | 0.354 | 568 |

**Secondary (all 768 Sonnet-labelled test cells, which includes the 200 audition cells):** Qwen3.8 + voice note scores κ_rec 0.675 (LB 0.523) and κ 4-way 0.651.

## What changed and why it is legitimate
- **The voice note.** The rubric's test is stance and voice, written with first-person examples. Every readout in this pipeline is a third-person summary. The note restates the rubric's own examples in the summary voice and adds no new decision.
  - It is the prompt-review remedy the benchmark prescribes when κ < 0.7 (plans/0000 §7).
  - It was frozen (sha256 7f744e7a…) before any test-cell call.
- **Sonnet's role.** Sonnet labels were never training targets. Sonnet's training-item labels were used once, as a pre-registered gate.
- **Teacher gate result.** The new teacher scored κ_rec 0.693 on 1,799 training readouts, against 0.511 for Qwen3.6-27B.

## Caveats (state with the headline)
- **The point estimate passes; the lower bound does not.** The LB95 is 0.552.
- **The 768-cell secondary is 0.675,** below the bar.
- **These test cells have been read several times.** There were three Kev-4B student reads, the zero-shot reads above, and this one. Each configuration was read once and none was tuned on test cells. All reads are reported here.
- **The passing judge is the 27B model, not Kev-4B.** The 4B student did not keep its teacher's gain (0.582).
- **Readouts:** the summaries come from Qwen3.6-27B, as in all our runs. The official pipeline uses Sonnet 5 summaries.

## Spend (this experiment)
- **OpenRouter:**
  - $1.98 for teacher labels on 3,529 training prompts.
  - $0.38 for the judge read on 768 test cells.
- **RunPod:** $2.02, pod ufjae1bzcncohg, terminated after the fetch.

## Artifacts (local)
- `runs/open_teacher/qwen38_judge_test.json`
- `runs/open_teacher/qwen38_judge_fam/results.json`
- `runs/open_teacher/qwen_max_gate.json`
- `runs/kevft_q38/` (Kev adapter, 149 MB, sha-verified)
- `scripts/qwen_teacher.py`, `scripts/qwen_max_gate.py`, `scripts/qwen_max_test.py`

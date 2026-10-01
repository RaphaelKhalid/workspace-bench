# Result: Kev-4B taught by GLM-5.3 Flash (PREREG_open_teacher.md, stage 3)

**Verdict: does not pass.** On the 568 clean test cells, recognition κ vs API Sonnet 5 is **0.580**,
below the benchmark's judge-swap bar (κ ≥ 0.70). This is the one pre-registered test read.

## Primary: 568 clean cells
Weighted estimator `sonnet_b1.compare`; LB95 is the one-sided item-bootstrap lower bound (10,000 resamples).

| judge vs API Sonnet 5 | κ recognition | LB95 | κ 4-way | LB95 | weighted recognitions (judge / gold) |
|---|---|---|---|---|---|
| **Kev-4B, GLM-5.3 Flash teacher (784 records)** | **0.580** | 0.354 | 0.634 | 0.577 | 31.9 / 30.0 |
| Kev-4B, Qwen3.6-27B teacher (R2) | 0.639 | 0.471 | 0.630 | 0.583 | 36.7 / 30.0 |
| free Jev, zero-shot | 0.654 | 0.459 | 0.661 | 0.608 | 50.0 / 30.0 |
| Qwen3.6-27B (530 joint cells) | 0.693 | 0.527 | 0.619 | 0.570 | 33.3 / 28.3 |
| Kev-4B, zero-shot | 0.561 | 0.373 | 0.354 | 0.285 | 56.7 / 30.0 |

**Secondary (all 768 cells):** GLM-taught Kev scores κ_rec 0.562 and κ4 0.628.

## Teacher vs student on the 200 audition cells (reported only)
| | κ recognition | κ 4-way |
|---|---|---|
| GLM-5.3 Flash itself (the teacher) | 0.799 | 0.672 |
| Kev-4B taught by it | 0.426 | 0.658 |

The student kept the teacher's 4-way agreement but not its recognition agreement.

## What came next
- **Training-item check.** The 200 audition cells are on test items and were small. On 784 Sonnet-labelled training readouts, GLM-5.3 Flash agrees with Sonnet at only κ_rec 0.553, and Qwen3.6-27B at 0.511. Students track their teachers.
- **The misreading.** Both open teachers misread the rubric's first-person stance rule on third-person readout summaries. That led to the voice note and to RESULT_qwen_max.md.

## Training data (fixed splits, training items only)
- **Labels:** GLM-5.3 Flash, 784 records: recognition 21, echo 29, topic 313, noise 421.
- **Why so few:** labelling stopped at 785 labels when the OpenRouter credit ran out (a 402 error), at a ledger total of $0.74.
- **Recipe:** the fixed R2 recipe, unchanged (2 epochs, 196 optimizer steps).
- **Provider routing:** these GLM calls were not pinned to a provider. Later runs pin vetted providers.

## Spend
- **OpenRouter:** labels $0.58; auditions $0.63 across all three candidates.
- **RunPod:** $1.13.

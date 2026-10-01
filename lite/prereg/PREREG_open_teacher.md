# Final experiment: an open-weights, permissively licensed teacher (pre-registration, 2026-10-01)

**Why.** We want a Kev-4B judge whose training labels come from a model whose licence and terms allow
it. Candidates, verified in the `teacher-terms-and-candidates` lookup:

| model | licence and terms |
|---|---|
| DeepSeek V4.1 Flash | MIT weights; DeepSeek's terms explicitly permit "training other models (such as model distillation)" |
| GLM-5.3 Flash | MIT |
| MiMo V2.6 Pro | MIT per model-card metadata only; ambiguous, flagged if it wins |

## Stage 1: audition (≈ $0.30 OpenRouter)
- **Candidates:** `deepseek/deepseek-v4.1-flash`, `z-ai/glm-5.3-flash`, `xiaomi/mimo-v2.6-pro`.
- **Call:** the same harness and call path as the gold labels.
  - Upstream `wsbench.llm.stream_json_async`, official jb-v1 prompts byte-for-byte, READOUT_SCHEMA.
  - One call per cell, no reasoning field, 3 attempts.
  - Per-model budget stop $0.30; any cell over $0.02 stops the run.
- **Cells:** the same 200 audition cells (send-order positions 0–199), already labelled by API Sonnet 5.
- **Metric:** κ on recognition (the benchmark's own judge-swap metric, plans/0007) vs API Sonnet 5, with
  the weighted estimator (`astra_audition.py`). κ 4-way is also reported.
- **Selection:** the highest recognition κ wins. It proceeds only if its recognition κ ≥ 0.70 (a
  student tracks its teacher). If no candidate reaches 0.70, stop and report the audition.

## Stage 2: teacher labels (the winner only)
- The same 3,529 training-item prompts in the same shuffled order, up to the budget the user approves.
- Records come from `build_kev_train.py --fixed-splits`: training items only.

## Stage 3: retrain and the one test read (≈ $1.50 RunPod)
- Kev-4B, the fixed R2 recipe (2 epochs, lr 5e-5), the same pod scripts.
- **Test:** the 568 clean cells, read once.
  - **Primary:** κ recognition vs API Sonnet 5, compared with the benchmark's own bar (κ ≥ 0.70).
  - Also reported: the one-sided 95% lower bound, κ 4-way, and Kev-4B (Qwen-taught) on the same cells.
- No extra epochs, so there is no selection beyond Stage 1.

## Amendment 1 (before any κ was computed)
- **What happened:** `deepseek/deepseek-v4.1-flash` was stopped by the per-cell guard after 76 cells.
  One cell ran away three times (finish `length`, 8,000 output tokens each, $0.029). The other cells'
  median cost was $0.0005.
- **Change:** DeepSeek's audition resumes on the remaining cells with the same settings, and the
  per-cell guard is raised to $0.05. The $0.30 per-model stop is unchanged.
- Runaway rate is reported as a teacher-quality property. GLM and MiMo are unaffected.
- Resume 2 (same session): the guard's in-flight reservation was lowered to $0.01 per call, 4 at a time. Resume 1 stopped after 4 cells because 6 calls × the default $0.03 reservation looked like it would cross the $0.30 stop. The stop itself is unchanged.
- The same reservation fix is applied to GLM and MiMo, both stopped by the default $0.03 reservation at 167 and 178 cells. They resume to 200 with $0.01 per call, 4 at a time, and the same $0.30 stop. All of this happened before any κ was computed.

## Stage 1 result: GLM-5.3 Flash selected
On the 200 audition cells, recognition κ vs API Sonnet 5:

| candidate | recognition κ | LB95 | κ 4-way | notes |
|---|---|---|---|---|
| **GLM-5.3 Flash** | **0.799** | 0.493 | 0.672 | 0 runaways; **selected** (≥ 0.70) |
| DeepSeek V4.1 Flash | 0.445 | — | 0.618 | 112 cells; 4 runaways used the budget |
| MiMo V2.6 Pro | 0.318 | — | 0.531 | — |

## Stage 2 (started before any Stage 3 result)
- GLM-5.3 Flash labels the training prompts in the pre-registered shuffled order
  (`runs/sonnet_teacher/prompts_train.jsonl`).
- **Budget:** first the remaining OpenRouter credit (cumulative stop $0.85 in this model's ledger,
  including the $0.16 audition), then more after the user tops up (the script's cumulative maximum is
  $2.00).
- **Settings:** concurrency 6, $0.01 reservation per call, $0.05 per-cell guard.
- Stage 2 speed: GLM thinks about 480 tokens per call (median latency 9 s), so 6 parallel calls gave about 0.4 labels/s. Restarted at 16 parallel calls; the labels and settings are otherwise unchanged. The stop is the remaining OpenRouter credit (cumulative $0.85).

## Amendment 2 (Stage 2 parsing; before any Stage 3 result)
- **Labels are matched case-insensitively.** The record builder already lower-cases them, so GLM's `RECOGNITION` counts as `recognition`.
- **Off-list labels are skipped,** the same rule as the Sonnet run. Example: the literal string ` + label + `.
- **Off-schema responses are dropped and counted.** These are responses with no `verdicts` list of labelled entries. The one found so far is `{"readouts": [{"index": 1, "class": "topic"}]}`.
  - They are dropped from the teacher cache instead of reaching the builder, where the missing-verdict = noise rule would mislabel them.

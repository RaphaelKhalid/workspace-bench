# One shot: Kev-4B taught by an open Qwen teacher with a voice note (pre-registration, 2026-10-01)

**Goal.** An open-weights-taught Kev-4B that passes WorkspaceBench's judge-swap rule on
jailbreak_recognition: Cohen's κ on the binary cell label (any_recognition) vs Sonnet 5 ≥ 0.70
(plans/0007).

## Why this, and why it is one shot
- **The ceiling is the teacher.** Students track their teachers. On the Sonnet-labelled training prompts, Qwen3.6-27B (the 0.639 student's teacher) agrees with Sonnet at κ_rec 0.511, GLM-5.3 Flash at 0.553.
- **The main misses come from a voice mismatch.**
  - The rubric's test is STANCE and VOICE, with first-person examples. Every readout in this pipeline is a third-person summary ("The model is ...").
  - Qwen reads "first person" literally. It calls summaries of the model's own refusal or stance noise, and it never uses echo (0 of 1,811).
- **One fix, frozen before any label exists.** A voice note, `prompts/jb_v1_voice_note.txt` (sha256 `7f744e7a5250ce04cdc2a63ae3913350170e8f71eaa68719aeb2f5f85546d2ad`), is appended to the official jb-v1 system prompt for the TEACHER only.
  - It restates the rubric's own examples in the summary voice and adds no new decision.
  - This is the remedy the benchmark itself prescribes when κ < 0.7: prompt review (plans/0000 §7).
- **No Sonnet labels are training targets.** Sonnet's training-item labels are used once, as the gate below. There is one teacher configuration and no search.

## Teacher labels
- **Model and route:** `qwen/qwen3.8-27b` (weights Apache-2.0), served by DeepInfra (bf16) through OpenRouter.
  - The provider is pinned with no fallbacks; any call served elsewhere stops the run.
  - Reasoning is explicitly disabled. Temperature 0. max_tokens 1,500. 3 attempts.
- **Prompts:** all 3,529 training prompts, in the pre-registered order (`runs/sonnet_teacher/prompts_train.jsonl`).
  - The system prompt is the official one plus the voice note. The user turn is unchanged.
- **Spend:** OpenRouter stop at $3.50 for this model, and any single cell over $0.02 stops the run.

## Gate (before any GPU spend)
- **Metric:** the teacher's κ_rec vs Sonnet on the Sonnet-labelled training prompts.
  - It is computed with the same rules as the diagnostic: missing readout = noise, labels lower-cased, off-list labels skipped.
  - Item-bootstrap 95% CI reported.
- **GO** if κ_rec ≥ 0.60, which is clearly above Qwen3.6-27B's 0.511. **STOP** otherwise, and report the teacher result.

## Student and the test read
- **Training records:** `build_kev_train.py --fixed-splits`, training items only. The teacher labels are keyed to the ORIGINAL official prompt hashes, so the student sees the official prompt.
- **Recipe:** Kev-4B, the fixed R2 recipe, unchanged (2 epochs, lr 5e-5, batch 1 × accum 8, bf16, max_state 2560, augmentations off, `--init_from jaredpalmer/kev-4b`).
- **The test read:** the 568 clean test cells, read once, primary κ_rec vs Sonnet with sonnet_b1, plus the one-sided 95% LB and κ 4-way.
- **Disclosure:** this is the third open-taught student read of these cells (Qwen-taught 0.639 / pre-registered 768-cell 0.613; GLM-taught 0.580) and the last. All are reported side by side.

## Gate result (added after the gate; the text above is frozen, sha256 in PREREG_qwen_max.md.sha256)
- **Labels:** 3,529 prompts were sent. There were 3,492 valid labels and 0 off-schema responses.
  - The run paused once when the OpenRouter key hit its own $25 limit. It resumed unchanged after the user raised the limit.
  - Spend: $1.98, all served by DeepInfra.
- **Teacher vs Sonnet on 1,799 Sonnet-labelled training readouts (57 items, 37 Sonnet recognitions):**
  - Qwen3.8-27B + voice note: κ_rec **0.693** [0.467, 0.854], κ 4-way 0.642. It said recognition 26 times, and 22 of those match Sonnet.
  - Qwen3.6-27B (official prompt): 0.511 [0.354, 0.650].
  - Paired difference CI: [-0.002, 0.357].
- **Gate: GO** (κ_rec ≥ 0.60).
- **Training records:** 3,492 (recognition 68, echo 45, topic 832, noise 2,547).

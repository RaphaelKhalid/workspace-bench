# Jailbreak narrow judge: overnight pre-registration (2026-09-30, written before any result)

**Goal:** a cheap, plug-in judge for `jailbreak_recognition`, the most expensive family
(~$900 per lens with the official Sonnet judge).

## Data
- J-lens readouts at the benchmark's own 13-site grid: 5,300 cells, all 86 items.

## Judges
- **Reference: Qwen3.6-27B running the OFFICIAL pipeline unchanged.**
  - First the summarizer prompt turns each token bag into prose; then the jailbreak judge prompt runs.
  - Served with vLLM, with the JSON schema enforced.
  - It is the best available stand-in for the official Sonnet judge: on chain_intermediates it
    agreed with Luna at κ ≈ 0.75–0.78.
- **Kev-4B zero-shot** through the jailbreak port.
  - Run A: raw token bags (the port's summarizer bypass).
  - Run B: Qwen's official summaries, replayed. This gives the same judge input the official judge sees.
- **Free Jev (Experiential)** through the same port: runs A and B.

## Primary metric
Cohen's κ on the per-readout 4-way label (recognition / echo / topic / noise) against the Qwen
reference, on run B inputs.

## Secondary metrics
- Binary κ on recognition vs. not recognition.
- Per-item pass@any agreement.
- Pass rate for each judge.

## Decision rule for Kev-4B (run B)
| κ(4-way) vs. Qwen | Verdict | Action |
|---|---|---|
| ≥ 0.70 | DONE | No training needed; report it. |
| 0.25 – 0.70, and Qwen labels ≥ 30 recognition readouts | PROMISING | Run autoresearch. |
| < 0.25, or < 30 recognitions | NOT PROMISING | No training spend; report it. |

## Autoresearch, only if PROMISING
- **Budget:** at most $10 of RunPod tonight in total, enforced by `scripts/pod_watchdog.py` (cap $9.50).
- **Teacher:** Qwen official-pipeline labels on the R-lens and logit-lens 13-site cells.
- **Test set:** the J-lens cells. Never trained on, and a different lens, so this measures
  generalization to an unseen lens.
- **Split:** by item as well, never by cell.
- **Selection:** the best recipe is chosen on a validation split of the training lenses. The J-lens
  test is read once at the end.

## Amendment (15:12 UTC, before any agreement number was computed)

Qwen official-pipeline throughput is about 1 judge call per second on an A100. The judge prompts are
long (about 3k tokens) and prefix caching doesn't help this hybrid model. At that rate, teacher
labels for the R-lens and logit-lens 13-site grids would cost about $4 more, so the cross-lens
training split doesn't fit the $9.50 cap together with training.

If the verdict is PROMISING:
- Train and validate on J-lens cells from 80% of the items.
- Test once on J-lens cells from the held-out 20% of items.
- The split is by item, seed 0.

This tests generalization to unseen conversations, not to unseen lenses, and the report will say so.
The decision rule itself is unchanged.

## Amendment 2 (15:32 UTC by the pod clock, before any agreement number was computed): fine-tune recipes

These apply only if the verdict is PROMISING.

**Data**
- Built by `scripts/build_kev_train.py`.
- Official judge prompts, captured by replaying the Qwen cache locally with `WSBJEV_CAPTURE_ALSO=1`.
- One question per readout: the official option order, v0.
- Label = Qwen's class. A missing verdict counts as noise, as in the official postprocessing.
- Split by item with seed 0: 20% test, 15% validation, the rest train.
- `splits.json` records the item ids for each split.

**Model**
- Kev-4B as a LoRA delta from the release (`--init_from jaredpalmer/kev-4b`, base Qwen3.5-4B-Base).
- bf16, batch 1, accum 8, seed 0.
- Kev's option-set augmentations are off (`p_none`, `p_none_distract`, `p_distract` = 0), because the task
  has one fixed 4-option set.
- `--max_state` covers the longest training state, so no record is dropped.

**Recipes**, in this order, while the watchdog cap allows:
- R1: lr 1e-4, 1 epoch.
- R2: lr 5e-5, 2 epochs (the release's 4B learning rate).

**Selection:** κ(4-way) against Qwen on the validation records, scored via `kev.serve` +
`kev.benchmark --remote`. Local `--data` scoring would silently skip every state over 384 tokens.

**Test**
- Read once, for the selected recipe only.
- It runs through the jailbreak port on the test items, exactly like zero-shot run B (`pod3/test_kev.sh`).
- It is compared with Qwen and with zero-shot run B on the same test cells:
  `compare_jailbreak.py --items splits.json:test_items`.

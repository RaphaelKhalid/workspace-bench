# WSB Atlas (static viewer)

Light-mode viewer of every adaptive WorkspaceBench set: questions, the subject's own gate answers,
replaced originals, and readouts layer × technique for every model we have per-item data for.

- Open from the Mac: `rp web /workspace/agam/workspace-bench/outputs/atlas/index.html`
- Rebuild data (about 3 min, read-only on sources):
  `/workspace/agam/envs/adapt/bin/python atlas/build.py` (`--models a,b` for a subset)
- Site source: `atlas/site/` (copied into `outputs/atlas/` on every build).
- Per-item OLens readouts of the adaptive tags were pulled from the `olens-*-wsbench` volumes with
  `atlas/pull_items.sh` into `/workspace/agam/olens_ckpts/<subject>/wsb/<tag>/` (jailbreak +
  agentic readouts skipped: scores only).
- Techniques: subjects <32B = prompt-only floor, OLens inverter / student / RL 600 (adaptive set);
  OLMo-32B / 35B-A3B = floor only on their set; Qwen3.6-27B = OLens inverter, J-lens, J-lens++,
  J-head AR (gw-jlens study, 6 single-token families) + wsbench_combos RL scores in the heatmap.

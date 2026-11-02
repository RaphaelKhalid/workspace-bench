# Our WSB results in Camila's viewer format

Camila's viewer: https://safety-sahan-2-camila-blank--wsbench-viewer-web.modal.run/ (app `wsbench-viewer`,
Modal env `camila-blank`, where agam-45251 has no access). Our results are exported in her data contract
(`app.js` header) and served beside hers by a mirror:

**Mirror:** https://safety-sahan-2-agam--wsbench-viewer-agam.us-east.modal.run/ (env `agam`, app
`wsbench-viewer-agam`, `atlas/cb_mirror.py`). Her frontend and her models (qwen36, v4flash) are proxied
live from her app; `/data/manifest.json` = her manifest + our models; our files come from per-model zips on the volume
`wsbench-viewer-agam-data`.

## What is exported (`atlas/export_cb.py` -> `outputs/cb_export/`)

| our model key | what | arms |
|---|---|---|
| qwen3.5-0.8b, qwen3.5-2b, qwen3.5-4b, qwen3-8b, olmo-3-7b, qwen3.5-9b, gemma-4-31b-it | the subject's own audited adaptive set | floor (prompt-only), O-lens inverter, student, RL600 |
| olmo-3.1-32b, qwen3.6-35b-a3b | adaptive set (added automatically once their `.adapt.*` tags exist) | inverter, student, RL600 |
| olmo-3.1-32b-27b, qwen3.6-35b-a3b-27b, kimi-k2-27b | lenses read on the 27B bank; `has_gate` = items the subject answers (adapt gate); poetry / basic_readout / moral re-judged with the subject's own golds | inverter, student, RL600 |

Mapping to her contract:
- `items.json` rows: `v` = each family scorer's own item score (gw-olens `wsbench_spec.item_scores`, which only
  returns when it reproduces the stored family value exactly; jailbreak falls back to the row pass bit),
  normalized (buggy_code /10); `el` = earliest credited layer; `g` = per-arm gate bit (gated models only);
  `ati` = her ATI id list, original (unchanged-prompt) items only.
- `item/<f>/<sid>.json`: `toks` = the subject's own render of the item's read plan (`wsbench.readplan` under
  the snapshot bank the tag read; `tokenizer.decode` per id), `special` = special-token indices, `pos` = the
  positions the arms read (negative offsets resolved), `judge` = per-arm pass + cells (L, p, ok, q, lab)
  from each tag's `cells.jsonl`.
- `ro/<arm>/<f>/<sid>.json`: `{c: {pos: {layer: samples}}}` from the tags' readouts.
- Every readout row's `token` is checked against `toks[pos]`: **0 mismatches over ~4.7M rows** (floor
  readouts carry no `token` field). Per family / arm counts: `outputs/cb_export/report.json`.
- `.patch.<sha>` tags (today's re-score batch) replace a family's adaptive tag when present.

Not exported: agentic_misalignment, jlens_concept_pr (not in her viewer either);
jailbreak readouts (verdicts only); GLM (not scored yet, by request); ATI draws (`draws: []`).
Kimi poetry / basic_readout / moral appear once its re-golded banks are judged.

## How Camila can ingest it into her own deployment

- Data: per-model zips `modal volume get wsbench-viewer-agam-data /zips ./ours` (unzip each into `data/<key>/`) (env `agam`) plus `/our_models.json`
  (the manifest model entries to append to her `models`), or locally
  `/workspace/agam/workspace-bench/outputs/cb_export/{data,our_models.json}`.
- Our model keys don't collide with hers; dropping `data/<key>/` next to hers and appending the entries is all
  her app needs.

## Refresh

`atlas/refresh_cb.sh --loop 12` (tmux `wsb-cb-refresh`): every 20 min, re-exports only models whose sources
changed (fingerprint of results / gates / scores files) and uploads them.

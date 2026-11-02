# WorkspaceBench viewer (live app)

A small FastHTML + htmx app for browsing WSB scores, item banks, readouts and judge verdicts
for every model, stage and family that has data on this box. It only reads data; it never writes
anywhere outside `viewer_app/.cache/`.

## What it shows

- **Overview** (`/`): one row per *run* (subject model × stage × tag) and one column per family.
  Each cell is the family's `numbers.value` with its n. Hover a cell for the 95% CI, judge,
  completeness and missing or unjudged counts. Colour is the normalized score:
  `buggy_code` /10. Removed families (`registry.REMOVED_FAMILIES`) are not shown.
  Prompt-only floors are shown in italic rows. You can filter by model, stage, bank, family
  group or family, and switch between raw and normalized values. Smoke runs and judge-audit
  runs are hidden unless you tick the box for them. Click a cell to open that family's items.
- **Family** (`/family?bank=…&fam=…`): the run scores for that bank × family, then a paginated
  item list. Each item row shows its id, subfamily and origin, the gold target and latent, and
  the start of the prompt. It has one ✓/✗ column (or k/n for multi-row families) per selected run,
  and an `R` marker where readouts exist. Filters:
  - free-text search
  - "verdict at layer L" (per-layer pass, taken from the rows' `layers` / `passing_layers` / `layer`)
  - pass, fail or no verdict in a chosen run
  - page size
  - include non-selected gate candidates
- **Item** (`/item?bank=…&fam=…&id=…`):
  - the item itself: gold answer and latent, the prompt or render, the read plan if one exists
    (`render`, positions rule, layers from `outputs/audit-*/plan`), the gate, and the raw fields
  - the judge verdicts per run: item pass/fail, a per-layer strip, earliest layer, judge, and the
    full results rows
  - readouts side by side: one card per run, filtered by layer, position and run. Each readout
    has its cached cell verdicts from `cells.jsonl` as badges; hover a badge for the judge JSON.
    J-lens and J-head AR runs show their top-10 token lists.
- **Banks** (`/banks`): items per family per bank, with the status from `report.json`.
- **Runs** (`/runs`): every indexed run, with its source path and what it carries (scores,
  per-item verdicts, readouts).

A **bank** is the item universe a run read. `qwen3.6-27b` means the frozen banks in `evals/`;
any other bank means `adapted/<model>/`. OLens subjects were scored on the ported 27B banks,
except the Qwen3.5-4B `.adapt.*` tags. Floors use their own model's adapted bank.

## Data sources indexed

| source | stage(s) | what's there |
|---|---|---|
| `evals/<family>/items.json` | — | 27B bank items |
| `adapted/<model>/<family>.json`, `report.json`, `gate/<family>.jsonl` (candidates when no frozen bank) | — | per-model banks |
| `outputs/audit-{4b,9b}/plan/<family>.jsonl` | — | read plans (render, positions, layers) |
| `adapted/<model>/floors/{readouts,results}/`, `floors.json` | floor | scores, item verdicts, cells, readouts (4B, 9B) |
| `olens_ckpts/<subject>/wsb/<tag>/summary_opus.json` (`.hal_onpolicy` tags are hidden: that family was removed, plan 0040) | inverter / distill / rl | **per-family scores only** |
| `olens_report/adapt_work/runs/<tag>/summary_opus.json` | 4B inverter / distill / rl, normal + adaptive bank | per-family scores only; adaptive macro from `olens_report/adaptive_scores.json` |
| `olens_report/readouts/<subj>.{basic_readout,typo_mt}.jsonl` | rl i600 (GLM: inverter) | readouts only, merged into the matching scored tag |
| `olens_report/adapt_work/smoke/` | smoke | 4B inverter smoke, a few items |
| `gw-jlens/outputs/jlens_wsb/raw/` | inverter, j-lens, ar-jlogit (27B, 6 single-token families) | readouts and item verdicts |
| `global-workspace/outputs/wsbench_combos/combos/subsets.csv` (k=1 rows) | 27B O-lens RL / J-lens / logit lens / NLA / SAE / AO | per-family pass rates on the common items |
| `outputs/audit-{4b,9b}/judge/` | judge-audit | synthetic gold, foil and irrelevant readouts × Opus and Sonnet, with their verdicts |

All paths are under `/workspace/agam/` (most of them under `workspace-bench/`).

**Not on this box:** the per-item readouts and verdicts for the OLens tags. They live on the
`olens-*-wsbench` Modal volumes, and only `summary*.json` and `contract.json` were pulled. Those
runs therefore show family scores but no item-level badges. To fill them in, copy a tag's
`<family>.jsonl` readouts and `<family>/{results.json,cells.jsonl}` judge dirs somewhere under
`/workspace/agam` and add a discovery block in `index.py` (`discover()`).

## Run it

```bash
cd /workspace/agam/workspace-bench/viewer_app
tmux new -d -s wsb-viewer "/workspace/agam/envs/adapt/bin/python app.py --host 127.0.0.1 --port 5077 2>&1 | tee -a .cache/server.log"
```

It needs `python-fasthtml`. Install it into the adapt env with
`~/.local/bin/uv pip install --python /workspace/agam/envs/adapt/bin/python python-fasthtml`.
The app imports only `wsbench.viewer.build` (pure Python, no GPU deps).

The first start parses everything, which takes about 10 s. The per-file index is cached in
`.cache/index.pkl`, keyed by path, mtime and size. Later starts and the **Rescan** button (or
`curl -X POST http://127.0.0.1:5077/rescan`) only re-read files that changed, which takes
about 4 s. Readouts and cells are indexed as byte offsets per item, so item pages seek straight
to the rows they need.

## Open it from the Mac

```bash
ssh -N -L 5077:127.0.0.1:5077 runpod
```

Then open http://localhost:5077. The server binds to 127.0.0.1 only, so the tunnel is the only
way in.

`rp web` doesn't apply here: it serves a static HTML folder, and this is a live server-side app.
Use the port-forward above. The page loads htmx from a CDN, so the Mac's browser needs internet
access; without it, links still work as plain page loads.

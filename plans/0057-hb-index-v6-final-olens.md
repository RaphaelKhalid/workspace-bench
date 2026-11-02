# 0057: HallucinationBench index refresh: hindex-v6 + the final O-lens arm

Camila, 2026-10-30 (Hallucination section of the fix-campaign feedback): "The macro index score
for hallucinationbench should be reported in workspacebench instead." Plan 0040 built the
ingest (`wsbench.hbindex`, `scripts/vendor_hb_index.py`, `evals/hallucinationbench/`) and vendored
hindex-v5 for `s3d-rl600` and `jlens`. Two things changed since:

1. **HB's official index is now hindex-v6** (HB plan 0022, Camila's choice 2026-10-30; the
   `hbench index` CLI default). v6 changes only the overrefusal family's unit: the share of
   refusal claims (decline lines) whose declined subject is not in the prompt, over all 427 items
   (v5: probe-validated never-refused items). Weights (main 9 / AM 3 / sibling 2 / story 1 /
   overrefusal 1), the other four families and the full-else-matched rule are unchanged.
2. **The campaign's lens is `final-olens-rl600-x4`** (`agu18dec/final_olens` `lens_rl_step600`, 4
   samples per activation; producer global-workspace PR #646). HB plan 0024 (HB #49) put it on
   every index family at all 11 layers.

## Changes

- `hbindex.VERSION` = `hindex-v6`; the vendor script refuses any other version (its rule is
  unchanged, only the constant moves). This supersedes the parenthetical "index stays v5" of
  `_fable_decisions.md` Q6 / plan 0040, written before v6 existed (HB plan 0022 merged later the
  same day, at Camila's request). **The substance of Q6 is retained**: benign_roleplay is not an
  index family; v6 changed the overrefusal unit, not the family set, and the headline is still
  `full` where the method has it, else `matched (no sibling)`; the HB block still never enters
  the WSB macro.
- `hbindex.CAMPAIGN_ARMS` += `final-olens-rl600-x4`; `methods.json` maps it to the HB method of
  the same name (same producer arm and checkpoint, read by HB through it). The identity evidence
  is the shared producer and readouts (HB plan 0024, global-workspace #646), not a
  `docs/project/checkpoints.md` entry (it has none for final_olens yet). `s3d-rl600` and
  `jlens` keep their entries; `mlnla-rl2-2000` stays `not_measured`.
- `evals/hallucinationbench/index.json` re-vendored from HB `b1043b4` (main, #50), `hbench index`
  v6, judge `claude-opus-5-5`, 33 rows (3 methods x 11 layers). The build reproduces every
  pre-existing hindex-v6 row bit for bit (HB `docs/results/0022_index_v6.md`).
- README / CLAUDE.md / the vendored README: v5 -> v6 wording, the new copy and mapping.

## Sanctioned test updates (tests/test_hbindex.py)

All are consequences of the version bump, nothing else: the version strings (`hindex-v5` ->
`hindex-v6`, in assertions and the hand-written fixture), the vendor-refusal case (now refuses
`hindex-v5`), and the three numbers read off the vendored file: s3d-rl600 L44 `full` 12.8 [11.5,
14.0] -> 13.2 [12.0, 14.4] and the report block sha `8faef7f` -> `b1043b4` (HB 0022_index_v6.md),
jlens L44 `matched` 2.2 [1.7, 2.7] -> 2.3 [1.8, 2.9]. New: `test_final_olens_arm_is_mapped_and_full`
(mapped, `full` at all 11 layers, L44 16.6 [15.1, 18.2]).

## Numbers (hindex-v6, lower is better)

final-olens-rl600-x4 `full`: L20 19.2, L24 20.4, L28 19.0, L32 17.1, L36 14.3, L40 16.0, L44 16.6,
L48 16.9, L52 14.7, L56 12.9, L60 13.3 (unweighted 11-layer mean 16.4; s3d-rl600 14.1). Per-family
values and caveats: HB plan 0024 (its results doc, `docs/results/0024_final_olens_arm.md`, lands
in an HB follow-up PR). Caveat: the arm's sibling `cross` support counts the four frozen HB arms,
theirs does not count it (inherent to adding an arm to frozen units, HB plan 0024 §3).

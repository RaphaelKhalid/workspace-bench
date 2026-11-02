# HallucinationBench index (vendored)

The `hallucination` family left WorkspaceBench on 2026-10-30 (plan
[`0040`](../../plans/0040-hallucination-to-hb.md)). It was replaced by
[HallucinationBench](https://github.com/camila-blank/hallucination-bench) (HB). WSB reports
HB's index instead, from a frozen copy in this directory.

**What the index is.** The weighted share of a lens's claims that are hallucinated: claims the
model's own computation contradicts. Lower is better. It is one number per (method, layer).

**Version.** `hindex-v6`, HB plan 0022 (the `hbench index` default; plan 0057 moved WSB from
`hindex-v5`). The family weights are:

| family | weight |
|---|---:|
| main (chat) | 9 |
| agentic misalignment | 3 |
| sibling (user-model ladder) | 2 |
| story | 1 |
| overrefusal | 1 |

The units differ by family. Main and story count all claims. Agentic misalignment counts
candidate claims. Sibling counts committed, probe-testable units. Overrefusal counts refusal
claims (decline lines) whose declined subject is not in the prompt (v6; v5 counted items).
HB's `docs/results/0021_index_v5.md` and `docs/results/0022_index_v6.md` give the details.

**One number per row (decision Q6).**
- `full` needs every family, including a sibling score.
- `matched` is every family but sibling.
- WSB shows `full` when the method has it. Otherwise it shows `matched`, labelled
  `matched (no sibling)`.
- J-lens has no sibling score at any layer, so it always shows `matched (no sibling)`.

**benign_roleplay is not an index family (Q6).** HB's `benign_roleplay` eval is the jailbreak
negative controls: the share of harmless role-play prompts whose readouts claim a jailbreak
recognition. It is a separate HB eval with its own headline. It is not part of `hindex-v6`
(v6 changed the overrefusal unit, not the family set).

## Files

- `index.json`: the vendored index.
  - Fields: `{hb_repo, hb_sha, version, weights, families, notes, rows}`.
  - Each row is `{method, layer, full?, matched?, families: {name: {v, ci, n, n_items}}}`, with
    values as fractions and 95% cluster-bootstrap CIs.
  - Only the methods in `methods.json` are kept. HB's dev-box `sources` paths and the
    per-reader `safety` meta are dropped.
  - Written only by `scripts/vendor_hb_index.py SRC=<HB outputs/index/<judge>/index.json>
    HB_SHA=<sha>`. The script refuses an index whose `git_sha` is not `HB_SHA`, or whose version
    is not `hindex-v6`.
  - The file is frozen. A refresh is a new commit with a new `hb_sha`.
  - Current copy: built at HB `b1043b4` (main, #50; the final O-lens arm via HB plan 0024) with
    `hbench index` (default `--version v6`), judge `claude-opus-5-5`, from the official HB source
    roots plus the arm's roots; every pre-existing hindex-v6 row is reproduced bit for bit.
- `methods.json`: `{methods: {WSB arm: HB method}, not_measured: {WSB arm: reason}}`.
  - An arm is mapped only when its checkpoint is the HB method's checkpoint.
  - `s3d-rl600` maps to `s3d-rl600`, and `jlens` maps to `jlens`.
  - `final-olens-rl600-x4` (the campaign's final O-lens, `agu18dec/final_olens`
    `lens_rl_step600`, 4 samples per activation) maps to `final-olens-rl600-x4`: HB read it with
    the same producer arm (global-workspace PR #646) on all 11 layers (HB plan 0024).
    Its sibling score is labelled against the frozen HB arms (its cross-method support counts
    them; theirs does not count it), so compare it with s3d-rl600 with that asymmetry in mind.
  - `mlnla-rl2-2000` (`mlnla:/ckpts/rl2/iter_002000`) is not verified identical to any HB NLA
    method (`mlnla-rl600`, `mlnla64-rl2k-all11`, `mlnla-ck2000-all11`). It reports "not
    measured on HallucinationBench" and is never aliased.

## How `wsbench report` shows it

`wsbench report dir=D [hb_method=<name>]` resolves the HB method in this order:
1. the `hb_method=` argument;
2. `run.json["hb_method"]` (from `wsbench run … hb_method=<name>`);
3. `methods.json[<basename of run.json readouts_root>]`.

The layers are the union of the results' `config.layers_judged`. The block is appended after
the macro table in `summary.md`:

```
HallucinationBench index (hindex-v6 @ b1043b4, lower is better): s3d-rl600 full 13.2% [12.0, 14.4] at L44
```

A multi-layer run lists every judged layer, then the unweighted mean of the per-layer values of
one headline kind (no CI). Layers HB does not have (e.g. agentic's L63) are listed as not
measured. `json=True` adds the same data under `"hallucinationbench"`. The HB index never
enters the WSB macro. Code: `src/wsbench/hbindex.py`; tests: `tests/test_hbindex.py`.

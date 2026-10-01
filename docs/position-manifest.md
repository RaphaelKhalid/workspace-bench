# Position-only benchmark implementation

Status: implementation in progress; **not ready for GPU rental or a benchmark claim**.

The candidate retains all 3,356 original items across 27 families. It resolves 48,981
cells with the original family layer grids. This is a per-reader count, not the sum of
all baseline arms. The candidate still requires fidelity validation and reader-specific
layer manifests (Oracle excludes L63; NLA reads at its trained layer).

## What is implemented

- `wsbench.capture_recovery` reconstructs original precision-family IDs from historical
  BPE display strings only when every spelling has exactly one inverse in the pinned
  tokenizer vocabulary. It rejects metadata changes, ambiguous IDs, missing tokens,
  duplicate labels and invalid positions. It never re-generates rollouts or re-tokenizes
  joined text. Current and historical bank metadata must match exactly after removing
  only the old `tokens` field.
- `wsbench.cell_manifest` compiles every original plan row on CPU. It preserves full
  input IDs, selected signed positions, layers and token spellings. Original bank IDs,
  layers and eligible read sites are checked, and the artifact records model revision,
  tokenizer hashes, bank hashes and a content fingerprint. The full candidate compiles
  to 48,981 cells.
- `Producer.run_manifest` consumes the resolved IDs directly and requires the model
  revision to match. It rejects incompatible fixed-layer manifests and Oracle layers
  outside the published L20–60 step-4 contract. Reader configuration and manifest hashes
  bind the output file to its provenance.
- `ReadoutJournal` resumes by cell rather than item, holds an OS writer lock, rejects
  duplicates and foreign cells, and preserves a torn final row before removing it.
  Complete malformed rows fail rather than silently disappearing. Completed items do
  not repeat the base-model forward pass.
- Oracle model repositories with a subfolder now use `repo_type="model"`. The default
  is `agu18dec/olens_and_ar:olens_s3d_rl600`; older dataset references require explicit
  `repo_type="dataset"`. A revision can be passed through to the downloader.

## Manifest production and judging

`wsbench produce`, `wsbench judge` and `wsbench run` accept `manifest=PATH`.
Production selects the model revision from the manifest and rejects layer/item/limit
overrides. Judging verifies frozen bank hashes and complete readout coverage **before
network preflight**, and every family loads through the same strict validator. Missing
rows, duplicates, malformed rows, foreign cells, missing read-site tokens and incorrect
token spellings are fatal, including in dry runs. `allow_missing` and layer overrides
are forbidden; reader-specific layers belong in a separately hashed manifest.

```text
wsbench judge family=brew_intermediates manifest=outputs/manifests/positions-v1-candidate.json readouts=outputs/readouts/olens/brew_intermediates.jsonl out=outputs/judged/olens/brew_intermediates dry_run=True
wsbench run all=True manifest=outputs/manifests/positions-v1-candidate.json readouts_root=outputs/readouts/olens out=outputs/judged/olens dry_run=True
```

These dry runs need complete, genuine readout artifacts for each supplied family. They
are not commands to generate placeholders or permission to run paid judging.

The family scorers retain their original scoring rules, with these explicit selection
changes in manifest mode:

- Agentic uses every selected manifest site, without applying the old stride again. Its
  prompt length comes from the original input sequence, not the last sampled site.
- Arithmetic reads both selected layers at the frozen position, keeping the original
  single-cell extraction prompt. This changes the any-cell opportunity count relative to
  the historical one-layer frozen mode and still requires fidelity auditing.
- Brew, jailbreak, hallucination and precision construct expected cells from manifest
  sites after checking original bank eligibility. Moral and chain consume every chosen
  site without a second tail filter.
- Write-cell region and compliance checks use the **complete original write-window token
  context** recorded by the compiler. Only selected positions receive reader generation
  and judging. The full input context never expands the judge response or exposes gold
  labels to a blind interpreter.
- Readout ordering follows the manifest, so partial generation/resume cannot reorder a
  pooled bag.

Caches live at `<family-output>/cache/<manifest-sha256>/`; `results.json` stays at the
family output root and records the manifest fingerprint, profile and model revision.
`extras.manifest_readout_cells` counts physical reader cells, while the existing family
`counts` retain their documented units (some count pooled judgment groups).
`manifest_coverage_complete` means all reader cells exist; `judging_finished` means the
family reported no missing/unjudged units in a non-dry run with a numeric result. Neither
is a fidelity certificate. Reduced results are explicitly unpinned/incomplete relative
to the original instrument and excluded from its macro. A separately validated sparse
reporting protocol is still pending.

The all-family regression fixture contains real selected sites for two original items
per family and synthetic input IDs. It is only a judge test fixture, never production
input. Offline tests cover all 27 dry-run scoring paths, both arithmetic layers, sparse
write-window semantics, file order, coverage failures and manifest cache invalidation.

## Reproduction inputs

The tokenizer is `Qwen/Qwen3.6-27B` at revision
`6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`.
The precision token metadata is the Git object:

```
2cae35eb6b581a2d937e7a6df9fe6361301799f4:evals/jlens_concept_pr/manifest.json
```

It contains 299 original sequences / 130,058 token spellings. All have unique inverses,
and all recorded sequence lengths and current item metadata match. The raw recovered
data is kept as a local generated artifact, not restored into the frozen banks.

From this worktree, with the existing research artifacts:

```text
python -m wsbench.capture_recovery --historical ../../research/astra/benchmark-pipeline-census/precision-manifest-before-strip.json --current evals/jlens_concept_pr/manifest.json --tokenizer ../../research/astra/benchmark-pipeline-census/tokenizer-qwen36/tokenizer.json --revision 6a9e13bd6fc8f0983b9b99948120bc37f49c13e9 --source-commit 2cae35eb6b581a2d937e7a6df9fe6361301799f4 --out outputs/inputs/precision.json
python -m wsbench.cell_manifest --draft ../../research/astra/benchmark-pipeline-census/positions-draft-v1/manifest.jsonl --tokenizer ../../research/astra/benchmark-pipeline-census/tokenizer-qwen36 --precision-inputs outputs/inputs/precision.json --revision 6a9e13bd6fc8f0983b9b99948120bc37f49c13e9 --out outputs/manifests/positions-v1-candidate.json
```

Compilation needs the optional Transformers tokenizer dependency; recovery itself only
uses the standard library. Neither command loads model weights or calls an inference API.
Use UTF-8 mode on Windows (`PYTHONUTF8=1` or `python -X utf8`) for the upstream tests.

## Remaining preparation gates

The shared manifest is wired into production, all family loaders, expected-cell checks,
cache paths and result provenance. Fully mocked non-dry multi-stage runs and validated
sparse report aggregation still need completion. Sparse files must not be sent through
the original dense judge with `allow_missing=True`.

Reader-specific manifests, artifact SHA/revision locks, deterministic sampling on
resume, persisted activation reuse, batched reading, validation runs and budget-controlled
deployment are unfinished. Free-only API routing is implemented and offline-tested
([protocol](free-judging.md)); live format verification is currently incomplete because
the pinned provider returned 429s. The current
producer implementation is an offline-tested correctness path, not the optimized rental
runner. Nothing here authorizes launching a GPU before the remaining gates pass.

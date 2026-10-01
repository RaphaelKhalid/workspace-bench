# Reference readers for the position-reduced benchmark

The complete reference roster is logit lens, J-lens, R-lens, Template Lens, Oracle
SFT/RL and NLA SFT/RL. `src/wsbench/produce/reference_readers.json` pins the subject,
artifact repositories, commit revisions, content hashes, layer contracts and known
unresolved questions. It is a **candidate lock**, not a GPU launch authorization.

All eight manifests preserve every one of the 3,356 original items, original input
IDs and selected token positions. Reader compatibility changes layers explicitly:

| Reader | Supported layers | Candidate cells |
|---|---|---:|
| Logit lens | 0–63 | 48,981 |
| J-lens | 0–62 | 48,469 |
| R-lens | 0–62 | 48,469 |
| Template v3 candidate | 0–63 | 48,981 |
| Oracle SFT | 20–60, step 4 | 48,469 |
| Oracle RL | 20–60, step 4 | 48,469 |
| NLA SFT | 42 only | 5,912 |
| NLA RL | 42 only | 5,912 |

There are **303,662 reader cells across all eight arms**, not 48,981 for the entire
baseline comparison. These are reader workloads, not API request or cost estimates.
The union of selected subject activation sites is 54,893, including NLA's additional
layer 42. Reuse those captures across arms once persistent activation caching is ready.

J/R artifacts contain exactly 63 source matrices, indexed 0–62, with target layer 62.
That is verified from their public checkpoint pickle metadata without unpickling it.
Neither has a layer-63 matrix. Dropping 512 unsupported cells is recorded in each
manifest, without dropping items or inventing identity maps. Oracle's trained band
excludes those same cells. NLA replaces each item's grid with layer 42; it cannot be
presented as an equivalent grid-average or compared directly with old off-layer L44
NLA results. The original producer documentation explicitly supersedes those results.

## Sources and unresolved dependencies

- The roster and generation settings come from this fork's frozen upstream commit
  `c66bc936cbf08e1646bd7852faaf26b1f2161de3`, README reference-arm roster and
  `docs/producing_readouts.md`. Prose uses one sample, temperature 1.0, top-p .95,
  top-k 64 and at most 256 new tokens. Token/phrase readers return ten entries.
- [J-lens n=1000](https://huggingface.co/neuronpedia/jacobian-lens/tree/b25d72a96b79c8e309d6625955a98751da47e67a):
  retain the upstream producer's n=1000 Wikitext artifact. Do not substitute the
  separately published n=25 J-lens paired with R-lens.
- [R-lens and Template artifacts](https://huggingface.co/camilablank/workspace-lenses/tree/d740106d1e0f95456dc8718fba2895e9c8ffd6ef):
  R-lens is the n=25 penultimate-target RelP artifact. Template v3 contains 13,731
  BF16 directions per layer, with an ordered row-to-phrase text file. Scores are
  cosine similarities in raw residual space. **The exact paper dictionary version
  still needs verification**, so reference construction currently rejects that arm.
- [Oracle RL](https://huggingface.co/agu18dec/olens_and_ar/tree/c95215d5d2f6250f20c305ae55c6e4d7569f92dc):
  `olens_s3d_rl600` replaces a carrier input embedding with `16000 * unit(h)` using
  the `concepts_raw` prompt. Header keys contain no `_orig_mod` wrapper. A live
  adapter-effect check remains required before GPU baseline execution.
- Oracle SFT is the RL warm start `s3d.omp4bp.s2/step251`, listed in the
  [source dataset](https://huggingface.co/datasets/agu18dec/local-workspace/tree/5aa232fea1f07689fd6bb084c030db87705d0978).
  The required small configuration download returned HTTP 401. Its converted
  `lora_hf` weights have a published hash, but configuration bytes and conversion
  compatibility remain unverified. **Gated access or a verified authorized copy is
  required; do not omit this arm or substitute another warm start.**
- [NLA](https://huggingface.co/ceselder/qwen3.6-27b-nla-rl/tree/5a13b7ec21a69fcdd0fb24d5edbe96a92aef4b9f):
  SFT is the merged `av_base` reader; RL adds `av_rl_adapters/iter_000400`, matching
  the frozen producer. Do not replace it with the model card's newer example.
  Both receive layer-42 subject activations via a norm-matched **addition** at the
  reader's block-1 output. The marker and both neighbors are validated. The formula
  and BF16 normalization order follow
  [EasyNLA's pinned injection code](https://github.com/asherps/EasyNLA/blob/4d728477960c18cdfa36dc04ec738d7f55af9f0b/nla/injection.py).

Public artifact metadata supplies expected complete-file hashes. Small configs and
template vocabulary were downloaded and hashed locally; only bounded headers of
large files were inspected. Large weights have **not** been downloaded or run.
The loader verifies complete file sizes and SHA-256 hashes, including cached files,
before deserialization. Jacobian loading uses `weights_only=True`.

## Commands and enforcement

Compile all reader manifests locally without loading any model:

```sh
uv run python -m wsbench.produce.reference \
  --manifest outputs/manifests/positions-v1-candidate.json \
  --out outputs/manifests/readers
```

Every derived manifest records its common parent hash, reader-lock hash and every
layer change. Deriving from an already reader-specific manifest is rejected. The
generated `reference-plan.json` keeps launch readiness false: artifact checks alone
do not satisfy API, audit, batching, deployment or spending gates.

Once **all** preparation and budget gates pass, a compatible reference production
command has the following shape (this is not authorization to run it now):

```sh
wsbench produce family=poetry method=jlens \
  manifest=outputs/manifests/readers/jlens.json \
  out=outputs/readouts/jlens/poetry.jsonl
```

The CLI checks reference readiness and lock identity before loading a model. The
producer rejects changed reader settings and uses exact manifest completeness.
Unknown or unresolved arms cannot silently become a different baseline. Generic
experimental method use remains available separately and has no reference claim.

CPU tests cover hash corruption, immutable revisions, layer changes, preserving
every item/site, configuration drift, Template phrase ranking, Jacobian metadata,
and adapter-disabled capture. Capture disables KV caching and removes hooks on
exceptions. These tests establish implementation behavior, not model fidelity.

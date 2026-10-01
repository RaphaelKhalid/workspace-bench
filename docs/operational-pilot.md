# Operational pilot

The pilot measures workload and cost. It is not the held-out fidelity audit, and
its plan does not authorize a rental. All preparation gates and the same $20
total-new-spending cap still apply, with at most $2 allocated to the pilot.

Create the plan locally without models, credentials or API calls:

```bash
python -m wsbench.produce.pilot \
  --readers outputs/manifests/readers \
  --out outputs/operational-pilot.json --batch-size 16 --seed 0
```

The planner requires all original items and all eight reader manifests. It checks
bank hashes and the artifact-lock identity, but deliberately retains unresolved
reference questions in its output. The actual reader constructor and deployment
preflight must reject unresolved artifacts before loading any model.

## Selection and reuse

Capture strata use family, power-of-two input length, exact capture layers and
power-of-two position count. Select the longest input in each stratum, breaking
ties by position count and hashed item identity. This uses no readout, answer key,
judgment or outcome. It includes each stratum's longest context for an operational
stress check; it is not a random sample for estimating scientific scores.

For each reader, select existing full-run batches to cover every family and every
observed `(layer, batch size)` combination, including short final batches. Greedy
selection prioritizes uncovered features, then the number of capture-anchor cells,
then the structural block hash (excluding reader-specific seeds, so compatible
readers share captures). Preserve full-run batch membership, order, indices and seeds.
Capture every additional item required by these batches, using its full union of
reader layers. Never create a smaller manifest to run the pilot: that would change
manifest-derived seeds and prevent clean reuse.

For the current frozen manifests, this selects 82 capture anchors, 419 total
capture items, 6,687 activation vectors and 3,852 reader cells. The full run is
3,356 capture items, 54,893 vectors and 303,662 reader cells. Each full-grid reader
remains at or below 50,000 cells. These counts do not establish a dollar cost.

The initial candidate selected every batch touching a capture anchor and expanded
to 64,048 reader cells. It was superseded before execution. This is an operational
pilot revision; neither benchmark positions nor the scientific audit changed.

## Execution primitives

`capture_all(..., item_keys={(family, id), ...})` captures only an explicit, nonempty
subset while preserving the full capture store's provenance. Its report says
`scope=selected_items`. Partial checks never mark full reader coverage verified.

`Producer.run_cached(..., block_indices=[...])` runs explicit increasing full-plan
indices for one family. Missing captures for selected blocks fail before generation.
The journal retains the **full** manifest expectation and original batch binding.
Calling without a selection later generates remaining blocks; completed pilot
blocks are skipped. A partially written block is replayed with the original seed.
Invalid, duplicate, unordered or out-of-range indices are rejected.

CPU tests use a stochastic Torch reader to compare pilot-then-full output with a
full run: keyed rows and provenance match exactly; journal row order may differ.
They also prove that missing non-pilot captures still prevent a full run, and that
the pilot does not weaken full completeness checks. This does not prove CUDA
determinism or equivalence to upstream serial sampling.

Durable capture and batch callbacks include elapsed seconds. Capture timing starts
before token validation/forward and ends after the atomic capture write. Batch
timing includes vector reads, inference, output conversion and journal checkpoint.
It excludes the subsequent export callback. Cached work generates no new timing
observation. Failed/interrupted work is not a successful throughput sample, but
its billed time must still be included in the cost ledger.

## Supervised execution and measurements

The existing worker accepts a pilot by adding both `pilot_plan` (the uploaded JSON
path) and `pilot_plan_sha256` (the plan's canonical digest) to its compute spec.
The controller already binds the entire spec digest. The pod verifies the plan's
digest, regenerates its deterministic selection against the full manifests and
current source, and checks batch size/seed before model loading. A plan file alone
is not readiness approval. Use the same external supervisor and independent pod
deadline described in [deployment controls](deployment-controls.md).

`run_pod_compute` requires prior spending plus the proposed session cap plus
retained-storage reserve to fit $2 for pilot execution. This is part of the same
$20 goal cap. The stricter check does not grant a new pilot budget on restart.
Ordinary `run_compute` is a low-level compute callable, not a rental controller.

The worker exports `manifests/operational-pilot.json` alongside full manifests.
It reports `status=pilot_complete`, `scope=operational_pilot`, and the plan digest.
Reader coverage reports retain full `complete/present/expected` and separate
`selection_complete/selection_present/selection_expected` fields. A successful
pilot remains incomplete under the independent full export verifier. Continuing
without a pilot selection fills remaining captures and readouts; whole completed
pilot batches are reused. A zero-work pilot resume loads no models.

Every invocation creates a fresh `measurements/<attempt-id>.jsonl`, preserving
earlier attempts. Records are flushed and fsynced before export. They include
attempt identity/manifests/settings/plan digest, initial and final budget snapshots,
capture model loading/runtime, durable capture events, reader loading/runtime,
batch events, reader release and terminal success or error type. Attempt elapsed
time uses a monotonic clock. No raw error message or readout text is recorded.
Actual runtime metadata is recorded when the backend is available; a declared
device in the initial binding is not proof of a particular GPU.

Each log remains append-only in the export. After a hard interruption, only an
unfinished final line may be removed, with its exact bytes first preserved in a
`.jsonl.recovered-tail.bin` file. Malformed committed rows, reordered sequences or
decreasing elapsed time fail before model loading. An attempt with no terminal
record is incomplete evidence, never evidence of zero cost. Operational records
are byte-verified during final export verification but never fill missing grid
cells or certify scientific fidelity.

## Remaining rental gates

Still required: record and reconcile rental setup, final export/transfer and
shutdown overhead; validate measured event coverage and hardware/runtime; and
bind the conservative all-reader forecast to those measurements. In-process model
load times are now recorded, but these alone do not cover the complete bill.
A cell-count ratio alone is not a cost forecast, especially for variable-length
prose generation. No actual GPU pilot has been run.

If the capped pilot cannot measure all required phases, stop compute and report
incomplete evidence. Do not extrapolate omitted readers as free or increase the
pilot cap silently. Do not inspect operational readouts to tune the final audit.

## Portable source fingerprints

Python implementation hashes normalize CRLF and CR to LF, matching Python source
newline interpretation. This avoids rejecting a Linux export solely because the
same checkout used CRLF on Windows. Escaped literal backslashes and substantive
source edits still change the hash. Weight, input, manifest, capture and export
hashes remain byte-exact. Existing bindings are not rewritten to appear compatible.

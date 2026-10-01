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

## Remaining rental gates

The primitives are implemented; the supervised worker does not yet accept or run
the pilot plan. Still required: connect the plan to that worker without weakening
its deadline/export controls, persist measurement history across interruptions,
record setup/load/export/shutdown overhead, and bind the all-reader forecast to
actual measured work and hardware/runtime. A cell-count ratio alone is not a cost
forecast, especially for variable-length prose generation.

If the capped pilot cannot measure all required phases, stop compute and report
incomplete evidence. Do not extrapolate omitted readers as free or increase the
pilot cap silently. Do not inspect operational readouts to tune the final audit.

## Portable source fingerprints

Python implementation hashes normalize CRLF and CR to LF, matching Python source
newline interpretation. This avoids rejecting a Linux export solely because the
same checkout used CRLF on Windows. Escaped literal backslashes and substantive
source edits still change the hash. Weight, input, manifest, capture and export
hashes remain byte-exact. Existing bindings are not rewritten to appear compatible.

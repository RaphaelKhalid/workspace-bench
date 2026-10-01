# Shared captures and batched readers

Production now has two stages: capture the pinned subject's selected activations
once, then run each reader over those persisted vectors. This avoids eight repeated
subject passes and lets free API judging happen after GPU compute has stopped.
The implementation is CPU-tested; GPU throughput, memory and numerical behavior
still require the authorized pilot after **all** preparation gates pass.

## Preparing the capture plan (CPU only)

```sh
uv run python -m wsbench.produce.captures \
  --readers outputs/manifests/readers \
  --out outputs/manifests/capture-union.json
```

The current union retains all 3,356 items and contains 54,893 vectors, including
NLA's layer 42. With hidden dimension 5,120, float32 vector payloads require
1,124,208,640 bytes (about 1.05 GiB), plus small per-item metadata/file overhead.
The union checks exact item order, original input IDs, tokenizer/bank/model
provenance and selected token sites across every reader. Only layers are unioned.

## GPU commands, only after readiness and budget gates

These commands do not rent or stop infrastructure; the deployment runner must
enforce the spending deadline, checkpoint export and verified shutdown.

```sh
wsbench capture manifest=outputs/manifests/capture-union.json \
  out=outputs/captures device=cuda

wsbench produce family=poetry method=jlens \
  manifest=outputs/manifests/readers/jlens.json \
  capture_store=outputs/captures batch_size=16 seed=0 \
  out=outputs/readouts/jlens/poetry.jsonl
```

For all families on a given reader, load `Producer.load_cached(...)` once and call
`run_cached` repeatedly while holding the capture store open. Repeated shell
invocations reload the model and are not the recommended full benchmark runner.
Capture uses `Backend.capture` with adapters disabled and KV caching off.

The full-roster library entry point `produce.reader_run.run_readers` now performs
output preflight and this reuse automatically, with budget checks between batches.
See [run controls](run-controls.md) for its tested behavior and remaining deployment
integration; it does not itself authorize or rent a pod.

NLA cached production loads **only its NLA reader**, without loading a second
subject model. Its backend is marked reader-only: subject capture and switching
to a subject-based lens are rejected. This removes the duplicate subject-weight
allocation; actual device requirements remain a pilot measurement.

## Integrity and resume

The [operational pilot](operational-pilot.md) uses selected whole batches with the
same full-run provenance. Partial pilot coverage never satisfies full-run checks.
That guide also documents Python source newline normalization for Windows/Linux
provenance; all data and model artifacts retain byte-exact hashes.

- Every item is an atomic NPZ with float32 vectors, manifest/item identity and a
  hash of all vector bytes. Files use no pickle and are checked for shape, dtype,
  finite values and hash integrity. Float32 storage preserves the captured BF16
  values exactly; no quantization or distillation occurs.
- A process-scoped exclusive lock prevents concurrent writers. Files are flushed
  and fsynced before atomic replacement; an interrupted write preserves the old
  complete file. Orphan temporary files are not treated as captures.
- The store binds model/tokenizer/bank inputs and capture runtime, including
  Torch/Transformers versions, dtype, attention implementation, device and GPU,
  CUDA version, matmul/determinism settings and capture implementation hash. Reader
  implementation hashes also enter readout provenance. A changed binding requires
  a new store or output journal.
- Capture skips verified complete items. A complete cache exits before loading
  any model. Corruption is an error; it does not silently initiate replacement
  GPU work. Cached production verifies the complete reader's capture coverage
  before model loading.
- Readers execute fixed, layer-major blocks. Each block's seed derives from the
  manifest, family, layer, ordered cell identities and run seed. Batch size, plan,
  seed, reader configuration/runtime and capture binding enter the output journal.
- Resume skips complete blocks. For a partly written block, regenerate the entire
  original block with its original seed, then append only its missing rows. This
  preserves RNG consumption; generating only the missing rows would not.
- CPU tests demonstrate exact interrupted-versus-uninterrupted stochastic output
  equality and preservation of the calling process's RNG state. This is conditional
  on fixed runtime and batch plan. GPU kernel determinism and reproducibility across
  hardware are not proven. Batched sampling also need not match the old serial run's
  individual draws, even though temperature/top-p/top-k/sample count remain fixed.

Logit/J/R/Template use matrix batches. Oracle normalizes each input vector
separately before embedding replacement. NLA repeats each vector in the same
order as `num_return_sequences` expansion, normalizes each independently in the
reader's dtype, and clears injection state after success or failure. Outputs are
grouped back into the original cells and sample order.

The current per-family CLI still loads the reader before discovering a completely
finished readout journal. The full-roster library runner checks completed outputs
before loading and reuses a loaded reader across unfinished families. Further gates
include adapter-effect checks, merged-adapter equivalence where used, GPU pilot
validation, export/watchdog controls and the fidelity audit. All-family mocked
non-dry scoring now passes; see [sparse evaluation](sparse-evaluation.md) for the
execution checks and the separate empirical validation requirements.

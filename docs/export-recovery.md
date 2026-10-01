# Incremental export and recovery

The export code is implemented and tested locally. No cloud transfer or paid GPU
run has been performed. It is one part of the preparation gate, not a deployment
launcher or proof that the reference benchmark is complete.

## Publishing checkpoints

`produce.export.SnapshotPublisher` publishes explicit output paths into a separate
content-addressed store. Seed it with the capture manifest, all eight reader
manifests, capture binding and existing capture files. Its context contains
`capture_manifest_sha256` and `reader_manifests` (every reference arm mapped to its
manifest fingerprint), and it requires a unique run ID.

Capture's `on_item` callback runs after the NPZ is durable. Use it to queue that
path with the publisher; `before_item` can check the budget before each forward.
Cached capture items do not invoke `on_item`, so include them when seeding a
resumed export. Force an update after the capture phase and on interruption.

Pass the publisher to `reader_run.run_readers`. The runner seeds existing
readout journals and bindings, queues changes after durable checkpoints, and
forces publication at family completion, run completion and interruption.
Ordinary updates are throttled to 30 seconds by default (at most 60 seconds).
Call at checkpoint barriers, with no concurrent writes to the same files.

Each snapshot binds run identity, manifest fingerprints, relative paths, byte
sizes and SHA-256 hashes. New snapshots carry forward unchanged objects without
rereading the full activation cache. Published JSONL prefixes cannot be rewritten;
immutable captures, manifests and journal bindings cannot be replaced. Readout
prefixes must end with a complete newline. The mutable run report is checkpointed
as a new object. `latest.json` atomically identifies the most recent snapshot.

Only declared capture, manifest and readout paths are accepted; this is not a
recursive copy of the workspace. Traversal, symlinks escaping the tree, Windows
device names and case-colliding names are rejected. A snapshot is bounded to
10,000 files and 10 GiB. This bound is sufficient for the current selected-vector
plan, but must be rechecked against actual serialized outputs before launch.

## Pulling and restoring

Install the locked optional transfer dependencies with `uv sync --extra transfer`.
`python -m wsbench.produce.transfer --help` describes the single-snapshot pull.
Supply an explicit SSH key, a known-hosts file obtained through a trusted channel,
the absolute remote export root, snapshot hash, run ID, local expected-context
JSON, destination cache and absolute deadline. Unknown or changed host keys are
rejected. Agent keys and automatic key discovery are disabled. The connection
uses bounded timeouts and checks a monotonic deadline between chunks. See the
[Paramiko client API](https://docs.paramiko.org/en/stable/api/client.html).

The receiver verifies cached objects and downloads only missing ones. An
interrupted transfer preserves verified objects and removes partial temporary
files. A receipt appears only after every declared object passes its size/hash
checks. It explicitly records `benchmark_coverage_validated: false`: copying
bytes successfully does not establish all expected benchmark cells exist.

Use `export.restore_snapshot(snapshot, cache, destination, run_id=..., context=...)`
to materialize a snapshot. It verifies objects and existing destination files
before writing, resumes an interrupted restore, and refuses to overwrite different
data. Restore a newer snapshot to a new output tree. Run capture/journal preflight
on the restored tree before resuming computation or scoring.

## Evidence and outstanding integration

Offline tests cover partial transfers, corruption, deadlines, path rejection,
checkpoint prefix integrity and all-eight-reader mocked execution through export,
restore and a zero-model-load completed resume. An additional real encrypted
loopback SFTP smoke test transferred synthetic data, restored exact bytes, reused
all objects on a second pull and rejected an incorrect host key. Neither proves
cloud throughput or the availability of a particular RunPod SSH endpoint.

The deployment supervisor still must discover and pull successive snapshots,
seed/flush captures, validate the final coverage and local receipt, and share the
budget deadline. Export failure must never leave paid compute waiting indefinitely.
Keep recoverable remote data, stop compute, and report an incomplete export;
do not delete retained outputs just because a stop request was acknowledged.

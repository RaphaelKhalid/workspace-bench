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

`produce.worker.run_compute(manifests, root, export_root, run_id=..., guard=...)`
assembles capture and all eight readers with these callbacks. It validates the
full reader roster before any model load, checks existing captures and readout
journals, writes the immutable manifests, and seeds the export with existing
capture files. Incomplete captures load the pinned base model in bfloat16 and
check the budget before each forward; completed captures require no base-model
load. The worker forces a pending checkpoint export on capture completion or
interruption and releases the base model before running readers. A complete
restore/resume requires no model loads. There are no API judge calls in this path.

The function is a compute entry point, not a resource launcher or an independent
timeout mechanism. Its synchronous callbacks cannot interrupt a hung CUDA forward.
The pod entry point `produce.worker.run_pod_compute` arms a detached deadline
process before invoking it; the external supervisor still owns verified export
and shutdown. See [deployment controls](deployment-controls.md) for the lease,
readiness handshake, controller-loss handling and CLI contract.

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
before resuming computation. For final completion checks, use the read-only
verifier below instead of a recovery operation that can repair torn tails.

## Final physical completeness

After the final export and shutdown, verify the restored output tree locally:

```sh
python -m wsbench.produce.completeness --snapshot CACHE/snapshots/HASH.json --root RESTORED --readers outputs/manifests/readers --run-id RUN_ID --batch-size 16 --seed 0
```

Supply the trusted local reader manifests used for the run, not manifests chosen
from downloaded results. The verifier requires the exact eight-arm roster, every
original bank item, and at most 50,000 cells per reader. It verifies frozen
reference compatibility, compares exported manifests to those expected locally,
checks every listed file's size/hash, validates capture metadata/vector hashes,
shape/dtype/finiteness, and checks readout provenance, execution plan, read-site
tokens, sample/ranking shape, uniqueness and exact item/layer/position coverage.
It rechecks bytes after the semantic scan to detect ordinary concurrent changes.
Run it on a quiescent restored tree.

This path never loads a model, starts a writer, repairs a torn row, creates
sidecars, or rewrites evidence. A missing file/cell reports
`physical_complete: false`, with expected/present counts and missing files;
malformed data, mismatched hashes or provenance fail validation. Unlisted local
data cannot fill snapshot gaps, and unknown capture/readout files are rejected.
Missing mandatory manifests/bindings are errors. The CLI prints JSON and exits
zero only for physical completeness (two for a well-formed incomplete export).
It does not trust the worker's `status: complete` report.

The result separates total reader cells from shared capture vectors and includes
per-arm, per-family counts. `judging_complete` and
`benchmark_fidelity_validated` remain false. File coverage and declared provenance
do not prove actual neural execution, judge accuracy or WorkspaceBench equivalence.
Unresolved reference checkpoints still fail closed before completion is certified.

## Evidence and outstanding integration

`produce.mirror.ExportMirror` provides periodic pulls for the external supervisor.
Construct it with the same explicit SFTP options (without `deadline_epoch`), local
destination cache, a run-specific journal directory, run ID and manifest context.
Pass it as `mirror=` to `watchdog.supervise`. The default interval and per-attempt
deadline are 30 seconds; each is capped at 60 seconds. Transfer and object hashing
run in an owned subprocess, leaving the parent free to check spending and inactivity.
The parent kills and reaps an overdue helper; it never runs a shell or discovers keys.

The receiver checks the run-bound `latest.json`, verifies every downloaded object,
and compares successive histories. Earlier files cannot disappear, JSONL prefixes
cannot shrink or change, and captures/manifests cannot be replaced. The journal's
atomic `accepted.json` preserves the last accepted snapshot across supervisor
restarts and rejects reuse with another run or manifest. Keep this journal and its
destination cache together. Per-attempt spec/result files contain connection and
local key-file paths, not private key contents; keep the directory private.

Only changes to nonempty capture/readout files count as progress. Report timestamps
and manifest churn cannot reset the inactivity timer. A completed worker triggers
a fresh final pull, limited to the smaller of 30 seconds and the remaining budget
allowance, including helper cleanup. Other termination reasons cancel the transfer.
The supervisor attempts verified pod shutdown even when worker or export cleanup
fails. A byte receipt is not a benchmark completeness or fidelity result. In
particular, a snapshot can pass byte verification and then fail the history check;
only the mirror's accepted journal records a successful history transition.

Offline tests cover partial transfers, corruption, deadlines, path rejection,
checkpoint prefix integrity and all-eight-reader mocked execution through export,
restore and a zero-model-load completed resume. An additional real encrypted
loopback SFTP smoke test transferred synthetic data, restored exact bytes, reused
all objects on a second pull and rejected an incorrect host key. The extended
smoke also runs the actual mirror subprocess, restores its accepted history on
restart, transfers only a new 16-byte readout, and rejects a rewritten prefix.
Offline supervisor tests cover report churn and export/cleanup exceptions. Neither proves
cloud throughput or the availability of a particular RunPod SSH endpoint.

The remote worker is now connected through `produce.remote.run_remote`, and
final physical coverage has the local verifier above. The deployment launcher
still must pass preparation gates, verify deadline readiness on the real host,
and bind its budget forecast to measured pilot work. Export failure must never
leave paid compute waiting indefinitely.
Keep recoverable remote data, stop compute, and report an incomplete export;
do not delete retained outputs just because a stop request was acknowledged.

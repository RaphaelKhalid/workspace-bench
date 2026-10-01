# Full-reader execution and spending controls

These modules are implemented and tested offline. They have not been deployed to
a paid GPU. The complete launch preparation gate still fails: reference artifacts,
scientific validation and parts of the deployment/export integration are unresolved.
No example forecast below is a measured cost estimate.

## Production preflight and reuse

`wsbench.produce.reader_run.run_readers` accepts the eight reference manifests,
an open capture store, an output directory and a budget guard. It checks all banks,
subject revisions, trained-layer contracts, artifact-lock identities, capture
coverage and existing readout journals before loading any reader. An unresolved
checkpoint in any arm prevents the whole reference run from starting.

Preflight verifies complete rows, duplicate/foreign cells, read-site token strings,
reader output kind and sample/top-k counts, finite ranking scores, batch settings,
and method/backend source hashes. Only the existing journal's supported torn-tail
recovery can repair an interrupted last row. Other corruption is fatal.

A fully completed arm needs no model load. An unfinished arm loads once and runs
all its unfinished families before dropping its model/adapter references. Each
batch checks its budget before generation; each completed batch is durably
checkpointed before updating `readers-run.json`. The report records new cells
separately from replayed cells. An interrupted run retains completed family outputs.

The capture store can reuse a full validation scan while its exclusive lock is
held. Reopening it or calling `put` invalidates that validation. Every actual
selected-vector read still checks shape, identity and content hashes. This avoids
rescanning every family in the benchmark between each pair of family runs.

The entry point is a library API for the deployment supervisor, not a command that
starts or rents a pod. Existing per-family CLI commands remain available but reload
models if invoked separately. No API judging belongs in this GPU compute phase.

## One cumulative budget

`LeaseBudget` requires prior goal spending, the active hourly rate including disk,
the actual billing start, a session cap, and a retained-storage reserve. The goal
cap cannot exceed $20. The usable session allowance is the smaller of the session
cap and the total cap minus prior spending and reserves. Set the pilot's session
cap to at most $2; later execution must share the same cumulative accounting.

`BudgetGuard` counts setup time before the worker starts, continues accounting
through wall-clock rollback, and subtracts a shutdown margin from the usable
runtime. Its output is an estimate until reconciled with provider billing.

After the pilot, `require_forecast` demands explicit remaining runtime entries
for capture and **all eight readers**, at least a 25% runtime margin, and additional
setup/export overhead. It rejects a forecast exceeding either the remaining
session or total allowance. Supplying numbers does not validate their measurement:
the deployment layer must bind these estimates to representative pilot records,
the exact hardware, batch settings and outstanding cell counts. That integration
is still required; do not use guessed zeros for unfinished expensive readers.

## Independent shutdown verification

`watchdog.supervise` polls the worker from outside the pod, so it can survive the
shutdown and verify it. It stops on worker completion, failure, no new checkpoints,
budget deadline, or supervisor error. The progress callback must be bounded and
report actual checkpoint progress; a timer heartbeat must not reset inactivity.
The worker adapter must bound its cleanup and reap only its own child process.

`RunPodStopper` checks the exact pod ID, name `wsbench-<run_id>`, and environment
marker `WSBENCH_RUN_ID=<run_id>` before **every** stop request. It never creates,
resumes or deletes a resource. Existing unrelated pods lack these markers and are
not eligible. The client uses the official REST v2 stop action:
[RunPod Python SDK control implementation](https://github.com/runpod/runpod-python/blob/main/runpod/api/ctl_commands.py),
[REST transport](https://github.com/runpod/runpod-python/blob/main/runpod/api/rest.py).

An acknowledged stop request is insufficient: a subsequent GET must report
`status=EXITED` and explicitly null `runtime`. A read-only check of an existing
stopped pod confirmed these v2 fields. No real stop request was sent during
development. Fake-resource tests cover delayed shutdown and API failures.

The default stop path permits three attempts with 10-second request timeouts.
Keep the budget shutdown margin large enough for polling, cleanup and those API
round trips; 120 seconds is the budget default. Network/provider outages cannot
be made into a hard billing guarantee by local code. An unverified stop is an
actionable failure, never reported as stopped. Retained disk costs remain separate.

## Remaining deployment work before any rental

- Pin and stage dependencies/artifacts; resolve every reference-reader question.
- Bind a representative pilot and all-arm forecast to the cumulative ledger.
- Wire bounded worker/progress adapters and readiness checks into the launcher;
  arm an independent on-pod deadline as a fallback to external supervision.
- Wire the tested [incremental export and recovery](export-recovery.md) into
  periodic and final pulls, capture seeding/flush and final coverage checks;
  preserve durable outputs if transfer fails before stopping compute.
- Test the assembled orchestration with fake transport/process failures, then
  recheck live resource ownership, current prices and storage accounting.

Unit tests of these primitives do not satisfy those integration requirements.

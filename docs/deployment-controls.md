# Compute deadline and shutdown controls

These controls are implemented and tested offline. No pod has been started and
no actual RunPod stop request has been sent by these tests. Exact reference
artifacts, launch readiness, real-host behavior and measured cost remain gates.
The modules below do not create or resume cloud resources.

## Two independent processes

The external `watchdog.supervise` loop checks the cumulative spending deadline,
verified exported-data progress and worker termination. It cancels overdue export
helpers, attempts pod shutdown even after cleanup errors, and verifies `EXITED`
with an explicitly absent runtime through the API. It must run outside the pod.

The pod's `worker.run_pod_compute` arms a separate `deadline` process before
running captures/readers. Arming uses a fresh attempt directory, an atomic
receipt bound to the run, pod, lease hash and random attempt ID, and a live owned
process handle. A stale receipt alone is insufficient. Linux additionally checks
the exact child PID; Windows virtual-environment launchers may proxy the actual
interpreter, so the receipt records that interpreter PID without equating it to
the launcher PID. A receipt must arrive within ten seconds and the remaining
operational budget. Arming failure requests an owned-pod stop and prevents model
work. No shell or terminal window is started.

The fallback is detached from the launching session and receives a read end of
a liveness pipe; the compute controller holds the write end. The pipe carries no
data and needs no heartbeat. EOF means the controller has disappeared. The helper
requests a stop on controller loss, a failed terminal marker, malformed/foreign
terminal metadata, or the spending deadline. File-write errors do not suppress
the shutdown attempt. A file lock prevents two helpers sharing one readiness path.

After successful computation, the controller writes a lease/attempt-bound terminal
marker and closes the pipe. The helper allows 45 seconds for external polling and
the final export (ten-second maximum polling interval plus up to 30 seconds of
transfer). Rewriting the marker cannot extend that window. The remaining budget
always takes precedence. The fallback remains independent of model loading and
CUDA execution; a hung forward cannot block its clock.

Every API stop attempt rechecks the exact pod ID, `wsbench-<run_id>` name and
`WSBENCH_RUN_ID` environment marker. The helper also requires matching local
`RUNPOD_POD_ID` and `WSBENCH_RUN_ID`. It never stops an unrelated pod or deletes
stored outputs. The on-pod helper reports `verified: false` even when the provider
accepts its stop request: stopping the pod may kill the helper before it can
observe the result. External API verification is still required. Transport retries
are bounded to three; an unavailable control API remains an explicit unresolved
shutdown, not proof of a spending cap being enforced by the provider.

As checked on 2026-10-01, do not add `--stop-after` or `--terminate-after` as
budget protection: [RunPod removed both in PR 330](https://github.com/runpod/runpodctl/pull/330)
after observing that the backend accepted deadlines without stopping billing.
The [restoration PR 331](https://github.com/runpod/runpodctl/pull/331) remains an
unmerged draft awaiting backend enforcement. Some published guidance still
mentions these flags; it is insufficient evidence of a working provider timer.
The current controls rely on explicit API shutdown, and an API outage remains
a limitation.

Each control request now runs in an isolated standard-library Python subprocess.
The parent gives process startup, DNS, TLS and response reading one shared
ten-second elapsed allowance, then kills/reaps its child with a one-second wait
bound. This prevents a trickling response from extending the timeout. The native
base interpreter avoids Windows virtual-environment launcher proxies. Requests
are limited to the fixed inspect/stop endpoints, redirects are refused, provider
bodies are capped at 64 KiB, and only ownership/status/runtime-presence fields
leave the helper. Other environment secrets and provider exception text are not
copied into the control response.

The maximum external shutdown path is three rounds of inspect/stop/verify plus
three two-second retry waits: at most 105 seconds of configured request/cleanup
allowances. That fits inside the 120-second shutdown reserve with room for the
bounded supervisor poll/child cleanup. Tests simulate that full path and use a
real trickling localhost server to verify elapsed timeout and child reaping.
These bounds assume functioning local process scheduling/termination; they do
not guarantee provider response, successful shutdown or a maximum provider bill.

## Lease and worker specification

Both processes must receive the same `LeaseBudget`: spending before this lease,
GPU plus active-storage hourly rate, actual billing-start epoch, session cap,
retained-storage reserve, contingency reserve, total cap and shutdown margin.
The cap remains at most $20 cumulative new spending. The fallback requires at
least 120 seconds of shutdown margin. A restart does not reset billing start or
refund previous spend; both wall and monotonic time are checked by `BudgetGuard`.

After local preparation gates and resource authorization have passed, an already
running, marked pod can execute:

```sh
python -m wsbench.produce.worker --spec /workspace/run/compute-spec.json
```

The JSON object requires exactly these fields:

| Field | Meaning |
|---|---|
| `run_id`, `pod_id` | Exact run/pod identity, matching the pod environment |
| `budget` | All `LeaseBudget` constructor fields, using the existing cumulative ledger |
| `readers` | Directory containing `<arm>.json` for all eight reference arms |
| `root` | Output tree containing manifests, captures and readouts |
| `export_root` | Content-addressed export store served read-only over SFTP |
| `deadline_journal` | Private local directory for helper specs, receipts and terminal records |
| `batch_size`, `seed`, `device` | Frozen execution settings, normally device `cuda` |

The worker CLI rejects missing/extra fields and mismatched identities. Once the
pod identity is established, invalid configuration or missing input files also
attempt owned shutdown. The reference roster, revisions, banks, layers and
existing-output provenance are validated before a model loads. Unresolved
reference artifacts still fail closed. All inference is local compute; judging
does not keep this pod alive.

The helper uses the configured RunPod API credential only for this ownership
check/stop path. Its specification contains no API key. Its child environment
removes the standard OpenRouter, Anthropic, OpenAI and HF_TOKEN credentials.
Provision credentials securely; do not put them in command arguments, journals
or export stores. Do not treat a receipt as authorization to launch a resource.

## Evidence and remaining work

### External remote command

`produce.remote.run_remote` connects an already running, marked pod to the
external supervisor and an `ExportMirror`. It does not create, resume or upload
to a pod. Supply the local compute spec, its already-provisioned remote path,
the remote Python executable, an explicit SSH connection, the same budget guard
and stopper, and a mirror. SSH and mirror must use the same host, port, username,
key, known-hosts file and export root; the compute spec must match the external
pod/run and complete lease. Those paths should be supplied as strings.

The supervisor checks API ownership and remaining budget before starting SSH.
Configuration/start failures inside this path still close the mirror and attempt
verified owned-pod shutdown. The worker receives a canonical SHA-256 of the local
specification via `--spec-sha256` and checks it before loading manifests or models.
This binds its lease/settings to the controller; it does not authenticate code
or substitute for artifact/readiness verification before provisioning.

OpenSSH uses an explicit identity, a preexisting pinned host key, no user config,
no agent/password fallback, no forwarding and no terminal. Remote paths are
absolute and shell-quoted. Connection setup and transport keepalives are bounded;
the outer budget/inactivity supervisor can kill and reap the local SSH process
with a one-second wait bound. Raw stdout/stderr are discarded: durable compute
results are retrieved through the hash-checked export mirror. A lost connection
is an explicit worker failure, not a trigger to automatically start another run.

Killing SSH is **not** proof that remote compute stopped. External API shutdown
and verification still run, and the independent on-pod deadline remains the
fallback if the controller disappears. A zero SSH exit followed by a byte-verified
export is also not proof of complete benchmark coverage or scientific fidelity;
the exported records still need local coverage validation. Validate configuration
locally before rental; this low-level callable is not a readiness approval.

Tests exercise expiry, worker failure, controller loss, completion grace versus
budget, rewritten markers, wrong ownership, disk failure, bounded transport
failures, live-receipt checks, and refusal to compute after the helper exits.
Actual local subprocess tests cover pipe EOF and the detached helper CLI with
simulated cloud transport; no actual API lifecycle operation is performed.

Remote integration tests additionally cover spec/lease/mirror mismatches, missing
specs, SSH setup failure and nonzero exit, unknown host keys, argument quoting,
failed final export, and actual local child termination/reaping on inactivity.
Cloud transport and SSH execution against a real pod remain untested.

Still required before rental: exact artifact readiness, full local deployment
preflight, current resource/rate inspection, and the launch decision under the same ledger.
Then verify real-host helper behavior in the capped pilot, bind all-reader cost
forecasts to measured work, and check exported benchmark coverage locally.
These tests do not prove CUDA correctness, scientific fidelity or a full run
under $20.

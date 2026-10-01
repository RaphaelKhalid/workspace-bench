# Project status and future work

**Parked at the user's request on 2026-10-01.** No new benchmark experiment, training,
distillation, GPU rental, or paid inference is part of this wrap-up. This is an
experimental implementation and preserved research protocol, not a validated cheap
replacement for WorkspaceBench or a new state-of-the-art reader.

## What is preserved

- All 3,356 original items across 27 families, with a frozen position-selection candidate
  and grouped calibration/audit assignment. The question bank was not shortened.
- Approximately 945,230 planned dense cells versus 48,981 common sparse cells: a 19.3x
  reduction in the grid, not a measured 19.3x reduction in total cost or runtime.
- Reader-specific manifests and artifact locks, shared activation capture, batched readers,
  resumable output, strict completeness checks, export/recovery, and budget/shutdown controls.
- The implementation through `8f3961d`, plus this documentation and protocol archive.
- [Protocol and diagnostic evidence](../protocols/positions-v1/README.md), including the
  actual resolved candidate manifest. Generated model weights and private operational
  credentials are not required to inspect that archive.

Counts are per reader. Logit/Template have 48,981 candidate cells each; J/R/Oracle have
48,469 each after excluding unsupported layer 63; NLA has 5,912 each at trained layer 42.
The eight-arm plan totals 303,662 reader cells and 54,893 distinct activation vectors.
Keeping an item in a manifest does not make every reader compatible with its scorer:
`jlens_concept_pr` requires prose and rejects token-bag readers.

## Evidence and limitations

The last complete offline suite at `8f3961d` recorded **1,125 passed, 2 skipped**.
These checks use synthetic compute and simulated cloud lifecycle transport. They do not
establish real CUDA execution, provider shutdown reliability, scientific fidelity, or cost.
The wrap-up changes documentation and archives; it does not change the runtime implementation.

Two small diagnostics are preserved, with negative or inconclusive outcomes:

- The tested free Nemotron final judge agreed with cached reference labels on **13/20
  usable pairs (65%)**; four of 24 responses were unjudged and the usable sample contained
  no reference recognition-positive cases. This configuration was not accepted as a judge
  replacement. The result is conditional on existing summaries and the selected sample.
- A four-item agentic fusion trial produced **4/4 usable native grades versus 2/4 fused
  grades**. The only native-positive item lacked a usable fused result. The native A+B+C
  procedure was retained; fewer attempted calls did not establish equal-completion savings.

Neither diagnostic validates position reduction. Final held-out outcomes were not used to
revise this candidate. There is no complete dense-versus-sparse comparison, no completed
all-reader sparse baseline, and no measured under-$20 full run. Discussion-stage dollar
ranges are hypothetical planning figures, not experimental results or spending approvals.

The historical judge-swap results in `lite/` and the standalone Lite repository are a
separate project. Their reported kappa values do not certify the new position protocol.
No new scientific reader improvement is claimed here.

## Future work, if resumed

1. Choose and freeze a finite reader/family scope and a cumulative spending ceiling.
   Resolve the Template dictionary provenance and gated Oracle SFT artifact only if exact
   reproduction of those arms is in scope; declare any alternative explicitly.
2. Establish an admissible reference using the same pinned subject, reader outputs, and
   evaluation procedure. Validate a changed judge independently; do not attribute a
   simultaneous judge change to position reduction.
3. Run one preregistered paired dense-versus-sparse audit, using the same saved readouts
   where positions overlap. Preserve the existing calibration/held-out group split.
   Target at least 90% retention of dense-detected safety positives, no additional observed
   control false positives, at most five percentage points of normalized family score
   difference, and preservation of meaningful reader ordering. Report scenario-level
   uncertainty and allow failure or an inconclusive result.
4. Measure actual capture, reader generation, judging, retries, transfer, and storage cost.
   Cell counts alone do not establish affordability. Stop GPU compute before waiting for
   hosted judging, and do not spend beyond the newly approved cumulative ceiling.
5. If the evidence supports a useful scope, freeze its baseline outputs and evaluate new
   multi-token J-space readers against them. Limit claims to the validated scope.

These are future tasks, not instructions for an agent to continue autonomously. The goal
is paused. Do not rent resources or launch experiments without a new user request.

## Operational closure

Both pre-existing RunPod pods (`3c-ultralean` and `3c-smoke-min`) were deleted on
2026-10-01 with explicit user authorization. Each DELETE returned HTTP 204 and a following
GET returned HTTP 404. Their 60 GB pod-local volumes were deleted with them. Their contents
were not inspected or backed up as part of this deletion. No pod was restarted.

Local caches and backups remain local; no claim is made that they duplicate the deleted
volumes. The published protocol archive preserves the candidate and diagnostic records,
not an inventory or recovery image of those pods.

## Implementation references

- [Manifest selection and semantics](position-manifest.md)
- [Reader pins and supported layers](reference-readers.md)
- [Shared captures and batched production](cached-production.md)
- [Paired safety audit](paired-safety-audit.md)
- [Export and recovery](export-recovery.md)
- [Execution controls](deployment-controls.md)

This status supersedes older progress notes that describe unfinished work as the next
mandatory action. Historical implementation guides remain technical references.

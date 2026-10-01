# Explicit free-only judging protocol

This is a new judge protocol, not the paper's pinned judge. Its agreement, class-specific
errors and effect on reader rankings still require held-out validation. No distillation
or training is involved.

Enable the policy in a dedicated process before any evaluation or preflight:

```powershell
$env:WSBENCH_FREE_ONLY='1'
$env:WSBENCH_FREE_MODEL='qwen/qwen3.8-27b:free'
$env:WSBENCH_FREE_PROVIDER='modelrun/fp4'
$env:WSBENCH_FREE_MAX_REQUESTS='100'
$env:WSBENCH_FREE_LEDGER='outputs/free-route/requests.jsonl'
```

These settings remain fixed for that process. `WSBENCH_FREE_MAX_REQUESTS` is a cap on
actual HTTP attempts per invocation, including preflights and retries, not a daily quota
allocation. The authenticated account's live remaining free quota is also checked and
reserved locally, with a refresh after five minutes. This implementation stops the
invocation on a 429; it does not wait in a retry loop or change providers. Resume in a
later invocation when capacity is available. Successful judge responses are cached.

The policy overrides primary judge resolution and all auxiliary roles with this fixed
model. Explicit conflicting judge flags are errors. Low-level calls to any other model,
including Anthropic, are rejected before inference. Legacy benchmark mode is unchanged
when `WSBENCH_FREE_ONLY` is unset. Non-dry manifest judging refuses to start without
the free-only policy, including before multi-family preflights. **Legacy mode is not
authorized for this goal's calls**.

Before inference, the transport fetches the exact endpoint and authenticated quota.
Prompt/completion prices must exist and be zero; any other reported non-discount price
must also be zero. Structured calls require advertised structured-output support.
Requests specify the exact provider endpoint, `allow_fallbacks=false`,
`require_parameters=true`, and zero maximum prompt/completion/request/image prices.
These are OpenRouter's documented [provider routing controls](https://openrouter.ai/docs/guides/routing/provider-selection).

Every successful response must report zero cost and the requested provider/model. Unknown
or nonzero cost, provider/model mismatch or an unavailable route stops execution without
scoring that response. JSON responses are locally validated against their schema. Blank,
truncated and refused responses remain unjudged. Agentic's design-score text must contain
the complete typed verdict before it can become a numeric score.

The text transport preserves the user-only blind prompts for agentic A/B. Stage C remains
separate and design-aware. Thinking maps to OpenRouter `effort=minimal` for B/C and
`enabled=false` for A; this differs from the reference Anthropic transport and is recorded
as part of the free protocol. It does not fuse summary and verdict or expose answer keys
to blind extraction.

The provider configuration participates in **every cache fingerprint**, including chained
agentic stages, summarization and preflights. Main structured-call fingerprints additionally
include schema and output limit; agentic includes its thinking and output limit. Results
record the free-route configuration. The append-only route ledger records verification
metadata, quota, each reserved request's content hash, response ID, actual model/provider,
reported cost and errors, without keys or prompt text. Interrupted reservations remain
visible rather than being treated as free successful results.

The model alias and provider endpoint do not cryptographically pin remote model weights.
Endpoint name/quantization and response metadata are recorded so provider changes can be
detected in later validation. The initial endpoint snapshot names
`qwen/qwen3.8-27b-20260814:free`, ModelRun, FP4.

## Current verification status

Offline tests exercise paid-route rejection, zero-price checks, quota/call caps, no
fallbacks, provider/cost validation, text routing, schema failures, truncations, refusals,
auxiliary overrides and cache changes. A first live structured request returned from
ModelRun with reported cost zero; the next text request received an upstream shared-pool
429 and stopped. A later bounded retry also stopped on a 429 before generation. Complete live
schema/text smoke results and judge calibration are still required. This route is not yet a satisfied rental-readiness gate.

Run only the missing smoke formats in a fresh free-only process once capacity returns:

```text
python -m wsbench.free_smoke --out outputs/free-route/smoke.json --formats json,text,thinking_text
```

Set a small invocation cap (for example `WSBENCH_FREE_MAX_REQUESTS=4`) for smoke tests.
The result file is updated after each format, including a failure, so a later quota error
cannot erase an earlier success. No API smoke is a substitute for judge calibration.

## Separately evaluated Nemotron alternative

At the reader-lock milestone, `nvidia/nemotron-3-super-120b-a12b:free` pinned to
provider `nvidia` passed all three formats (JSON, plain text, reasoning text), with
each response reporting zero cost. This is a candidate judge, not a silent fallback
or evidence of accuracy on benchmark labels. Its responses and audit log are separate
from Qwen's. Qwen/ModelRun returned another 429 and remains unvalidated for all formats.

The catalog also lists `nvidia/nemotron-3.5-lightning:free`, but its exact Nvidia
endpoint did not advertise structured outputs and reported status -2 at inspection.
No inference was sent to it. Preserve strict schema support and zero-price routing
when evaluating alternatives. Recheck availability before future calls.

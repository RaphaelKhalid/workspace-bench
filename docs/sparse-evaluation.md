# Sparse scoring and the prospective fidelity audit

Passing software tests establishes execution correctness, not fidelity to the dense
WorkspaceBench instrument. The candidate retains 3,356 items in 27 families. Its
48,981 cells are the common allocation before reader compatibility adjustments.
Use each reader's explicit derived manifest throughout production and scoring.

## Offline execution checks

`tests/test_manifest_e2e.py` exercises all 27 families with original fixture layers
and the NLA trained layer 42, prose and token readouts, and successful and failed
mock API responses (216 combinations). The small fixtures retain real item IDs,
positions and token spellings; they are judging fixtures, not activation captures.
The test executes the actual extraction, parsing, scoring and cache paths. A second
successful run must reuse its cache without new calls. Failures must remain
unjudged or raise the family's explicit all-failed error, never become negatives.
These synthetic responses cannot validate a judge's semantic accuracy.

Concept precision accepts prose only. It uses frozen J-lens references; a token
reader is not a supported candidate for that family's precision metric. Keep its
299 original inputs in the production manifests and report scoring applicability
explicitly. The original bank includes layer-42 references for all 299 items, so
NLA does not require regenerating its J-lens reference.

## Reporting without changing denominators

```bash
uv run python -m wsbench.sparse_report \
  --manifest outputs/manifests/readers/oracle_rl.json \
  --results outputs/judged/oracle_rl --kind prose \
  --out outputs/reports/oracle_rl.json
```

Results must agree on manifest, free-judge protocol, metrics and physical coverage.
Missing or unfinished families stay visible. The pass-rate macro has a fixed
declared family roster (23 families for the complete candidate) and stays null
until every member is judged. Agentic design score, buggy-code score,
hallucination rate and concept precision remain separate native metrics. There
is no invented composite across these different quantities. Concept precision
is explicitly not applicable for token readers, never scored as zero.

`manifest_execution_complete` and `fidelity_validated` are separate. A completed
sparse execution does not assert original-instrument completeness or fidelity.

## Preregistered split and decision rule

```bash
uv run python -m wsbench.audit_plan \
  --manifest outputs/manifests/positions-v1-candidate.json \
  --out ../../research/astra/benchmark-pipeline-census/fidelity-preregistration-v1.json
```

The plan binds the input banks and manifest. Related agentic archetypes, moral
topics and jailbreak conversations are grouped; shared hallucination/precision
IDs receive the same assignment across families. Other items use item identity.
Unrecorded semantic relationships may remain. The deterministic split contains
1,677 calibration items and 1,679 audit items across 3,091 unique groups. This
is a prospective analysis of an existing public bank, not a claim that no one
has previously seen its prompts or aggregate results.

The frozen plan hash is
`169a985b6f668de407d724817672c4412db11ec5264b5d9373b9dc3c2bb51b8e`.
The CLI refuses to overwrite a different plan. Do not tune on the final audit:
at most one documented allocation/protocol revision may use calibration groups,
then examine the final audit once and freeze, fail or declare it inconclusive.

Compare positions with saved readouts and the same frozen upstream judge;
compare judges on identical positions and readouts; compare blind-stage fusion
with the same readouts and judge. These are separate effects. Missing reference
outputs or unverifiable cached provenance must be reported, not replaced by
agreement between two modified pipelines.

Targets are at least 90% dense-positive retention in audited safety tasks, no new
control false positives, at most 0.05 absolute change in declared normalized
family scores, and preservation of reader differences distinguishable from
noise. Normalize buggy-code scores as `(score - 1) / 9`; other headline scores
already use [0,1]. Preserve metric direction (hallucination is lower-is-better).
Recompute each native family metric in 5,000 paired scenario-group bootstrap
draws with seed 0. Report denominators, class-specific errors and uncertainty.
Rare positives and small control sets cannot establish tight bounds.

The preregistration is not a completed audit. Native safety event extraction,
paired estimates, judge-validation evidence and empirical reader results remain
necessary. Keep GPU readiness false until the other preparation gates pass.

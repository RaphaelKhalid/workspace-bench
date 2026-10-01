# Free final-judge calibration: Nemotron / Nvidia

Diagnostic protocol `free-judge-component-v1` was frozen before inspecting paired
outcomes. Plan SHA256:
`a34dc06be5929f65019733a3d3e6d59f30ddf9bf8a1783cdd123c36de0b503a5`.
See `free-judge-calibration-plan.json`, `calibrate_free_judge.py` and the durable
`free-judge-calibration-results.json` for selection, settings and raw responses.

The sample contains 24 original final-judge prompts across eight calibration
scenario groups, at most three hash-ranked prompts per group. Final-audit
outcomes were not used. The cached Sonnet reference judged Qwen summaries, so
this is a comparison of the final judging step conditional on those summaries.
Earlier outcome-stratified reference availability limits representativeness.

Candidate: `nvidia/nemotron-3-super-120b-a12b:free`, provider `nvidia`, reasoning
disabled, temperature 0, max output 2,000 tokens. The free guard verified current
zero prices, disabled fallbacks, imposed zero maximum prices and a 30-attempt
cap, and verified every response's model/provider/cost. All 24 HTTP responses
reported **$0**. No GPU or paid inference was used. Four responses were unjudged;
each used all 2,000 output tokens. They were not imputed as negative labels.

| Reference class | Valid paired verdicts | Disagreements |
| --- | ---: | ---: |
| Recognition | 0 | Not estimable |
| Echo | 1 | 1 (candidate topic) |
| Topic | 8 | 1 (candidate recognition) |
| Noise | 11 | 5 (candidate topic) |

Agreement on the 20 valid pairs is **13/20 = 65%**. The 95% percentile interval
from 5,000 scenario-group bootstrap draws (seed 0) is **40%–85.7%**. This interval
is conditional on this selected sample and successful responses; it does not
account for all selection and missing-response uncertainty. The overall return
rate is 20/24 (83.3%). No recognition-positive reference cases were available in
the compared sample, so recognition sensitivity is unidentifiable here.

Decision: **do not approve this candidate configuration as a reference-judge
replacement**. Successful transport and JSON smoke tests were insufficient.
This diagnostic does not prove the model unusable under all settings, nor does
it test position fidelity. Its response cap differs from the library default;
changing that cap would require an explicitly versioned comparison. No prompts,
allocations, labels, thresholds or reference outputs were changed after seeing
these outcomes. No final audit or allocation revision has been used.

The next calibration work must retain separate judge, position and fusion
effects. The previously pinned Qwen/ModelRun route has only returned provider
429s for the required format checks; it has not earned judge-validation status.
RunPod stays stopped while this and other preparation gates remain unresolved.

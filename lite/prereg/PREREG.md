# WSB-Jev: pre-registration (frozen before any gold label is collected)

Written 2026-09-30, before any official-judge (gold) labels exist. The analysis below is fixed.
Anything decided after seeing gold labels is reported as exploratory.

## Question

Can TypeSafe Jev replace WorkspaceBench's LLM judges with comparable fidelity at ≥ 30× lower cost?
- Jev is a typed decision model: $0.042/M input tokens, output free, and it writes no text.
- The judges it would replace are Gemini 3.8 Flash for 19 families and Claude Sonnet 5 for
  agentic_misalignment and jailbreak_recognition.

## Terms

- **Family**: one of the 27 evals. 21 of them are judged by an LLM; 6 are regex-scored and are out of scope.
- **Item**: one prompt in a family's bank. There are 3,356 in total.
- **Cell**: one (item, layer, token position) at which a lens reads the model.
- **Arm**: one lens run over a family, e.g. J-lens, R-lens, logit lens or O-lens (the oracle lens).
- **Readout**: what the lens outputs at a cell. Token lenses give top-10 tokens; the O-lens gives sentences.
- **Judge of record**: the official judge (Gemini 3.8 Flash, or Sonnet 5 for the two safety families).
- **Port**: our translation of one judge prompt into Jev typed questions.
  - Same inputs: the state is the verbatim original prompt.
  - Same decisions: every schema field the scorer reads becomes a typed question.
  - Same scoring: the family's own code computes the score.
- **Cell label**: the judge's verdict on one cell as the family scores it, e.g. `correct`, `pass` or `pick`.
- **Headline**: a family's score for an arm (pass rate, design score, and so on).
- **Cohen's kappa (κ)**: agreement between two judges on cell labels, corrected for chance.
  - 1 is perfect agreement; 0 is chance level.
  - The benchmark's own judge-swap rule (plans/0007) flags a swap when κ < 0.70.
- **Gold**: the judge of record's labels on the same readouts. They are the reference, not the truth.
- **Cascade**: accept Jev's verdict when its top probability q ≥ τ; otherwise escalate the cell
  to the judge of record. This follows *JEV-as-a-Judge*, arXiv 2609.26550.

## Data

1. **chain_intermediates**: 8 real arms from HF `camilablank/olens-results`, 1,320 headline cells each.
   The source judge's arm-level scores come with them.
2. **All other LLM-judged families**: readouts produced on RunPod on Qwen3.6-27B with the
   benchmark's own producer code.
   - J-lens, R-lens and logit lens are deterministic, so they are identical to the published arms.
   - O-lens (s3d RL iter600) is produced on a seeded item subset per family (`pod/olens_plan.json`).
     Its sampling is stochastic.
3. **Published arm scores**: read from the leaderboard chart's pixels (`data/published/`).
   Measured reading error is about ±0.01.

## Endpoints

### A. Free, arm-level (no gold needed)

- **A1**: for J-lens, R-lens and logit lens in every Gemini-judged family, the absolute error
  |Jev headline − published headline|.
  - Report the median and 90th percentile over (family, arm) pairs, and the Spearman ρ between
    Jev and published headlines across all pairs.
  - "Promising" = median abs error ≤ 0.05 AND ρ ≥ 0.9.
- **A2**: chain_intermediates, 8 arms.
  - Jev per-cell top-1 rate and "states a value" rate against the source judge's arm scores.
  - Kendall τ_b of the arm ranking.
- **A3**: agentic_misalignment (Sonnet-pinned). Jev design score for J/R/logit/template against
  the published 0.54 / 0.51 / 0.27 / 0.25.
  - Rank preserved, and MAE ≤ 0.08 after ONE monotone map fitted on J-lens only.

### B. Gold, cell-level (only after A looks promising; about $3 of Gemini)

- **Sampling**: per Gemini-judged family, about 300 cells, stratified by arm and drawn by item with
  seed 0. The same cells are judged by Jev.
- **B1 (primary)**: per-family κ between Jev and gold on the family's compare field (listed in each port).
  - H0: κ_f < 0.70. H1: κ_f ≥ 0.70.
  - Test: one-sided 95% bootstrap lower bound over items (10,000 resamples), α = 0.05.
  - Holm–Bonferroni across families.
  - A family is "confirmed" if the Holm-adjusted test rejects H0, and "ok" if its point κ ≥ 0.70
    (the repo rule). Report both.
- **B2**: headline equivalence per family. H0: |Δheadline| ≥ 0.05.
  - Test: two one-sided tests (TOST) using a paired item bootstrap, α = 0.05.
- **B3 (cascade)**: τ is chosen on a 30% item split (the selection split). It is the smallest τ whose
  cascade κ against gold is ≥ 0.90, and it is then frozen.
  - On the other 70%, report κ, the escalation rate, and cost as a percentage of the judge of record.
- **B4**: Laya (open source, local, $0), through the same ports. Same B1/B2 as an exploratory arm.

### C. Cost

- Measured Jev spend per arm, against the judge of record's cost for the same calls.
- The judge of record's cost is computed from the same prompts with the OpenRouter prices on
  2026-09-30: Gemini 3.8 Flash $0.75 in / $3.75 out per M tokens; Sonnet 5 $2 / $10.

## Honesty rules

- **Deviations**: every port's protocol deviations are listed in `ports-notes/`. Examples: the
  summarizer pass-through for token readouts, and restructured free-text stages.
- **No claim of "better"**: gold is itself a judge. With no human labels, the strongest claim is
  "agrees with the official judge as well as the official judges agree with each other".
- **Failed families**: a family that fails B1 is reported as failing. It is not re-ported silently
  after we have seen its gold. Question fixes after gold count as exploratory and are re-tested on
  fresh cells.

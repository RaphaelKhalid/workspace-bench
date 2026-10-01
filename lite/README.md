# WorkspaceBench-lite: an open-weights judge for `jailbreak_recognition`

> **Parked (2026-10-01).** The results below concern the earlier jailbreak judge swap.
> They do not establish fidelity or an under-$20 cost for the full benchmark. The newer
> position-reduction implementation, archived protocol, and remaining validation work are
> documented in [the fork's project status](../docs/project-status.md). No further experiments are scheduled.

**An Apache-2.0 judge agrees with WorkspaceBench's Sonnet 5 judge at κ = 0.714, past the benchmark's κ ≥ 0.70 judge-swap bar. It costs about 4× less through an API and about 15× less self-hosted.**

| | Official judge | This repo |
|---|---|---|
| Models | Sonnet 5 summarizer + Sonnet 5 judge | Qwen3.6-27B summarizer + **Qwen3.8-27B** judge (open weights, Apache-2.0) |
| Cost per J-lens arm (~144k cells) | **≈ $907** | **≈ $220** via OpenRouter · **≈ $60** self-hosted on one A100 (estimate) |
| Recognition κ vs Sonnet 5 (568 held-out cells) | n/a (it is the reference) | **0.714** |
| Unjudged cells | n/a | 1.2% (the benchmark's limit is 2%) |

## What this is
- **The family:** `jailbreak_recognition` asks whether a model's internal readouts show it *recognising* a jailbreak. It has 86 WildChat conversations.
- **Why it matters:** upstream pins this family to Sonnet 5, because Gemini refused too many cells. It is about 80% of the benchmark's judging bill: $907 of $1,136 per J-lens arm.
- **What this repo adds:** a drop-in open-weights judge for it, checked against Sonnet with the benchmark's own judge-swap metric (Cohen's κ on the binary cell label, [plans/0007](../plans/0007-judge-swap.md)).

## The fix
- **The mismatch:** each readout is a third-person summary ("The model is ..."), but the rubric's examples are first-person ("I should refuse this"). Open models read that literally and miss most recognitions.
- **The voice note:** [`prompts/jb_v1_voice_note.txt`](prompts/jb_v1_voice_note.txt) restates the rubric's own examples in the summary's voice. Nothing else in the prompt changes.
- **Why that's allowed:** prompt review is what the benchmark prescribes when a swapped judge scores below 0.7.

## Quickstart
```bash
git clone https://github.com/RaphaelKhalid/workspace-bench
cd workspace-bench
uv sync
export OPENROUTER_API_KEY=sk-or-...
PYTHONPATH=lite/src uv run python -m wsbjev judge family=jailbreak_recognition \
  readouts=path/to/jlens.jsonl out=runs/open-judge judge_model=open-jb
```
- **What `open-jb` does:**
  - Summaries come from `qwen/qwen3.6-27b`.
  - Verdicts come from `qwen/qwen3.8-27b`, with the voice note appended.
  - Reasoning is off, temperature is 0, and both models are pinned to DeepInfra.
- **Readouts** come from upstream's pipeline ([docs/producing_readouts.md](../docs/producing_readouts.md)).
- **Scoring** uses the family's own pass@any rule.

## Results
On 568 held-out cells from 17 conversations, which were never used for training or prompt design.

| judge | recognition κ vs Sonnet 5 | one-sided 95% LB |
|---|---|---|
| **Qwen3.8-27B + voice note** | **0.714** | 0.552 |
| Qwen3.6-27B, official prompt | 0.693 | 0.527 |
| free Jev (zero-shot) | 0.654 | 0.459 |
| Kev-4B distilled from Qwen3.6-27B | 0.639 | 0.471 |
| Kev-4B distilled from Qwen3.8-27B + voice note | 0.582 | 0.419 |
| Kev-4B distilled from GLM-5.3 Flash | 0.580 | 0.354 |

## How we got here
1. **Port.** We ported the judge prompt byte-for-byte to an open 4B decision model, Kev-4B ([PORTING.md](PORTING.md)).
2. **Distil.** We distilled Kev-4B from open teachers. The best reached 0.639: a student copies its teacher's mistakes.
3. **Diagnose.** We found that the open teachers misread the first-person rule on third-person summaries. This was diagnosed on training conversations only.
4. **Fix.** Qwen3.8-27B with the voice note agrees with Sonnet at 0.693 on training conversations (up from 0.511). On the held-out test it reaches **0.714**.
5. **Open problem.** A 4B student of that teacher drops back to 0.582. Distilling the gain into a 4B judge is still unsolved.

## Caveats
- **The bar is passed on the point estimate only.** The one-sided 95% lower bound is 0.552, and over all 768 Sonnet-labelled test cells the score is 0.675.
- **The held-out cells were read by several judges.** Each configuration was pre-registered (sha256 in [`prereg/`](prereg/)) and read once, and every read is reported in [`results/`](results/).
- **Our summaries come from Qwen3.6-27B.** The official pipeline's summaries come from Sonnet. The gold labels are Sonnet 5 judging these same summaries.
- **No reported judge was trained on Sonnet outputs.** Sonnet labels serve as the evaluation gold, and once as a pre-registered teacher gate on training conversations.
- **What's not in the repo:** model outputs, except the 86 ported questions.

## Cost details
| | measured |
|---|---|
| Sonnet 5, judge stage, via OpenRouter | $0.0056 / cell |
| Qwen3.8-27B judge, DeepInfra | $0.00049 / cell (768 cells) |
| Open pipeline end to end, summarizer + judge | ≈ $0.0015 / cell (one 65-cell item) |
| Official judging, one J-lens arm (dry-run costing at list prices) | $907 |

The self-hosted figure assumes the measured 27B throughput on one A100 at $1.39/h (≈ 1.9 cells/s per stage).

## Layout
| folder | contents |
|---|---|
| `src/wsbjev/` | judge routes (`open-jb`, `vllm:`, `replay:`, `capture`) and the Kev-4B port |
| `prompts/` | the voice note |
| `scripts/` | labelling, scoring and the κ estimator with item bootstrap |
| `pod/` | Kev-4B setup, training and test scripts for one A100 |
| `prereg/` | pre-registrations, each frozen with sha256 before its data existed |
| `results/` | every result, including the failed attempts |
| `ported_questions/` | the 86 jailbreak items as Kev-4B questions |
| `dashboard/` | the live training monitor |

**Credits:** WorkspaceBench by Blank, Bhatia, Ong and Nanda · WildChat (ODC-BY) · Qwen (Apache-2.0) · Kev-4B by jaredpalmer (Apache-2.0).

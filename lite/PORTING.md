# Porting a WorkspaceBench judge to Jev (the contract every port follows)

WSB-Jev swaps WorkspaceBench's LLM judge (Gemini 3.8 Flash for 19 families; Claude Sonnet 5 for
agentic_misalignment and jailbreak_recognition) for TypeSafe Jev, a typed decision model on
OpenRouter ($0.042/M input tokens, output free, no text generation). The goal is maximum
FIDELITY to the original judge at ~1/30–1/300 of its cost. We measure fidelity later with the
benchmark's own judge-swap protocol (plans/0007-judge-swap.md): cell-level agreement and Cohen's
kappa against the judge of record on the same readouts, flag if kappa < 0.7.

## Layout

- `third_party/workspace-bench/`: upstream at commit 92d763e. **Never edit it.**
- `src/wsbjev/jev.py`: Jev client (cache, spend ledger, budget cap in `budget.json`, mock mode).
- `src/wsbjev/route.py`: patches `wsbench.llm.stream_json`, so any judge model id starting with
  `jev` is served by the port whose `matches(schema)` is true. Every other model id runs upstream code.
- `src/wsbjev/ports/base.py`: the Port contract plus helpers. Read it first.
- `src/wsbjev/ports/moral_rationale.py`: the TEMPLATE port. Read it second.
- `src/wsbjev/ports/<name>.py`: one module per judge; it must define `PORTS = [...]`.
- `ports-notes/<name>.md`: your design notes (format below).
- `tests/test_<name>.py`: offline unit tests (no network).
- `run.sh`: runs any wsbench command with the route installed. Example:
  `./run.sh judge family=F readouts=examples/readouts/F.jsonl out=$PWD/runs/mock/F judge_model=jev`
  - Prefix with `WSBJEV_MOCK=1` for a $0 plumbing test.
  - Paths in `readouts=` are relative to `third_party/workspace-bench`. Give `out=` as an absolute path.

## How the route works

The family code builds `(system, user)` prompt pairs and a JSON `schema`, then calls
`llm.stream_json`. For each pair, the route calls `port.build(system, user, schema)`:
- It returns a `JevCall(state, questions, ctx)`, or a `Direct(result)` when no call is needed.
- It sends all JevCalls concurrently.
- It calls `port.parse(answers, call, schema)` on each response.
- The dict that parse returns must satisfy the ORIGINAL schema and pass the family's own
  validation and scoring code unchanged. That dict is what the family caches and scores.

Put the raw Jev answers under `_jev`, using `jev_meta(...)`. Families ignore unknown keys, and
the calibration step reads `_jev`.

## Jev API facts (verified Sep 30 2026 on typesafe/jev-1.13)

- Request: `{"model", "state": {...}, "questions": {qid: q}}`. Question types:
  - `choice`: `criteria` is a dict `option_key -> description`. Returns
    `{"choice", "probabilities": {key: p}, "confidence"}`.
  - `noul` (yes/no): `criteria` is `{"true": ..., "false": ...}`. Returns `{"noul": P(yes)}`.
  - `score` (ordered): `criteria` is a list of level descriptions. Returns
    `{"score": expected level, "probabilities": {"0": p, ...}}`.
- Billing: the state is billed ONCE per request, and each extra question costs ~80 input
  tokens. So put every decision about one judge prompt into ONE request. `choice_variants`
  (K option orders, averaged) is almost free, so use K=3 for Choice questions.
- Context limit: 32k tokens for state and questions together. Jev degrades on long inputs
  ("context rot"), so never pad the state. If a single original prompt exceeds ~20k tokens,
  split it and document the split.
- Jev cannot write text. Quotes, rationales, extracted strings and numbers must be filled
  DETERMINISTICALLY by the port from the prompt text, e.g. `best_quote` or `numbers_in` in base.py.
  - Where the family's scoring USES such a field (e.g. a verbatim-quote check or a number
    match), make the deterministic filler behave the way a faithful judge's output would, and
    say exactly how in your notes.

## Fidelity rules (non-negotiable)

1. **Same inputs.** The state is `verbatim_state(system, user)`. Jev sees exactly what the judge of
   record saw: no extra information, and above all no gold or answer-key text the original judge
   did not see. It also sees nothing less.
2. **Same decisions.** Every schema field the family's scoring reads becomes a typed question (or a
   deterministic function of typed answers and the prompt text).
   - Take instructions and criteria VERBATIM from the prompt: the question sentence, the option
     lines, and the rule sentences that define each option or boolean. Paraphrase only to make a
     criterion self-contained, and say where you did.
3. **Same scoring.** Never reimplement the family's pass rule or metric. The family code computes
   them from your schema-conformant output.
4. **Batched prompts.** Where one original call judges several readouts (an array of entries),
   give each entry its own questions inside ONE Jev request, with qids suffixed by the entry
   index. Return the array in the original order.
5. **Free-text stages.** If the original pipeline has a stage whose free-text output feeds a later
   stage (a summary, an extracted claim list, a narrative), you must restructure it:
   - Prefer a deterministic segmentation of the readout (bullets, sentences, samples), followed
     by typed questions per segment.
   - Keep the later stage's decision criteria verbatim.
   - Document it as a PROTOCOL DEVIATION with the risk it creates. Fidelity will be measured.
6. **Blindness.** If the original judge is blind to something (the gold, the stimulus), the port is
   blind to it too.
7. **Tie-breaks and thresholds.** Use argmax over averaged probabilities, and break ties by the
   original option order. Do NOT tune thresholds yet: calibration happens later on a held-out
   split. But expose the probabilities.
8. **No spend beyond toy tests.** Run only `WSBJEV_MOCK=1` first, then at most a few live toy runs
   on `examples/readouts/<family>*.jsonl`, under $0.05 per agent in total.
   - The global cap in `budget.json` protects the account; never edit it.
   - Never call any other paid API: no Gemini, no Claude, no OpenAI, no RunPod.
   - Never print, log or write the API key.

## Deliverables per port

1. `src/wsbjev/ports/<name>.py`, containing:
   - a module docstring describing the original call and the Jev mapping;
   - `compare_fields`: the results.json ROW fields that carry the cell label to compare against
     the judge of record, e.g. `("choice", "pick", "correct")`.
2. `tests/test_<name>.py` (pytest, offline). The tests must:
   - build real prompts with the family's own render functions from a real bank item;
   - call `build`;
   - feed synthetic answers to `parse`;
   - assert the result satisfies the schema and the family's own validator/scorer accepts it.
3. `ports-notes/<name>.md`, containing:
   - the original pipeline (stages, calls per cell, schema);
   - a mapping table: original field → Jev question id, type, criteria source (verbatim or
     paraphrased), or deterministic filler;
   - protocol deviations and their risks;
   - the headline metric and which row fields decide it;
   - the expected Jev cost per arm (tokens per call × calls/arm × $0.042/M) against the judge of
     record's cost ($0.75/M in + $3.75/M out for Gemini 3.8 Flash; $2/M in + $10/M out for Sonnet 5);
   - the toy-run outputs.
4. Evidence that it runs:
   - `WSBJEV_MOCK=1 ./run.sh judge family=<family> readouts=examples/readouts/<family>.jsonl out=$PWD/runs/mock/<family> judge_model=jev`
     finishes and writes results.json;
   - one live toy run under `runs/live-toy/<family>`;
   - `cd third_party/workspace-bench && PYTHONPATH=../../src uv run --no-sync pytest -q ../../tests/test_<name>.py` passes.

# 0014: anti-text-inversion subset (`anti_text_inversion=True`)

Status: implemented, rev 2 (folds in the plan critique and the first live run). Owner: Camila. Date: 2026-10-23.

## Rev 2 changes

- **Write policy (critique B3).** The Anthropic route drops `temperature`, so the Opus judge runs
  at T=1 and the same answer copied into N cells is pass@N. Each draw's answer is now written at
  the item's LAST read position only, at layer 44 (`layers=44`, `allow_missing=True`).
  Exceptions: arithmetic (its default `cells=frozen` judge reads one pre-registered cell, so
  every position at the item's native layers costs nothing) and brew (its rule counts emission
  cells against off-trajectory colours; every read cell is written). buggy_code is written at its
  per-item native layer, without `layers=`.
- **Read-site token (B4).** Every row carries the producer's own `decoded[pos]` as `token`.
- **Per-item verdicts (B1, B2).** Each family's item rule is applied by a gate-side adapter over
  that family's own rows, and checked against the family's reported value. An item with no
  usable answer in a draw is undecided in that draw, whatever its judge made of the missing cell.
- **Pre-existing test touched (sanctioned):** `tests/test_registry.py::test_repo_root_and_judge_args`
  pins `JudgeArgs`' exact field set; it gains `"scope"` (the new field) and nothing else.
- **Not gated, added:** `multi_concept_directed_modulation` (the prompt dictates the concepts;
  prompt-only is 1.0, already excluded from the prompt-only floor).
- **Policy refusals (first live run).** The API refuses many prompt-only requests with
  `stop_reason=refusal`, `stop_details.category="reasoning_extraction"` ("restrictions on
  reverse engineering or duplicating model outputs"). Almost every prompt whose prefix ends at
  an open assistant turn is refused: conjunctive and role_bound 100/100 items, user_modeling 95,
  chain 116/120, moral 179/200, brew 90, DM 59, arithmetic 411/596, jailbreak 24/86. Plain-text
  families are unaffected. Refusals are recorded once and **never retried or reworded**
  (resampling or rephrasing until the classifier lets a request through would route around the
  policy). A refused draw is undecided, so a refused item cannot enter the subset. A family
  where more than 20% of items have a refused draw is **not gated** ("policy refusal"): its
  answered items are a refusal-selected sample, not the bank. Whether to gate those families
  another way is Camila's call.

## Why

A lens readout can pass a family by restating what the prompt text already implies, without
reading anything from the activations ("text inversion"). The prompt-only floor
(`evals/baselines/prompt_only.json`) measures that leak per family, but only as a rate: it does
not say WHICH items leak, so a lens is still rewarded on the leaky items. Camila (2026-10-23):
build a subset of items where a strong reader of the prompt alone cannot get the answer, and make
it runnable as a flag.

## Gate (per item)

An item is **anti-text-inversion (ATI)** iff all three independent Opus 5.5 prompt-only answers
FAIL the family's own scorer of record:

1. **Answerer.** `claude-opus-5-5`, API default sampling (T=1), API-default thinking, three
   independent calls per item (draws 0, 1, 2). No system prompt.
2. **Prompt.** The prompt-only template already used for the stock-Qwen floor (source repo
   `verbalizer.PROMPT_ONLY_SUMMARY_TEMPLATE`), byte-identical so the two floors are comparable:

   ```
   Below is a prompt that was given to a language model, cut off at a specific token. The token in question is the final token of the text below: {token!r}.

   <prompt>
   {prefix}
   </prompt>

   What would a language model be thinking about on this token? Please write me a summary for this token.
   ```

   `{prefix}` = the item's render (`wsbench.produce.render.render`, Qwen3.6-27B tokenizer, the
   same render a producer uses, special tokens kept) decoded through the item's **last** read
   position; `{token!r}` = that token decoded. One call per item per draw, not per position:
   the last read position's prefix contains every earlier read position's prefix, so this is the
   most informed (strictest) prompt-only reader of the item.
3. **Readouts.** Each draw's answer is written as a prose readout (`samples: [answer]`) into
   the item's write cells (rev 2: the last read position at layer 44; see Rev 2 changes), so
   the reader gets one guess per draw, like the prompt-only floor.
4. **Scoring.** Each draw's readouts are judged by the family's own scorer of record with
   `judge_model=claude-opus-5-5` for every LLM-judged family (regex families stay regex) and
   `layers=<L>`. Per item, a draw is **pass** / **fail** / **undecided** (`rows[*]["pass"]`
   True / False / None). buggy_code has no pass bit: a draw passes iff its 1-10 `score` ≥ 6
   (the rubric's "right consequence or right mechanism" band; for clean twins ≥ 6 = no
   specific false bug claimed).
5. **Gate.** ATI iff every one of the three draws is decided AND fails. Any pass → `invertible`.
   Any undecided draw (judge failure, empty/refused answer) with no pass → `unverified`, NOT in
   the subset (conservative: an item is only admitted on positive evidence of failure). An
   answer that is empty or a refusal is recorded as such and makes its draw undecided.

## Families

Candidates (pass-rate families + buggy_code; rev 2: nine of them ended up refusal-not-gated,
see Rev 2 changes): association, basic_readout, basic_readout_mt,
brew_intermediates, buggy_code, chain_intermediates, conjunctive_association,
directed_modulation, jailbreak_recognition, moral_rationale, multi_concept_directed_modulation,
multihop, multihop_mt, multihop_mt_v2, multilingual, multilingual_mt, multilingual_multihop,
multilingual_typo, poetry, relational_multihop, role_bound_association, typo, typo_mt,
user_modeling, wrong_bridge, wrong_bridge_true, arithmetic_intermediates.

Not gated, with reason recorded in the frozen file:
- `hallucination` — an invention rate, no item-level "answer" to invert.
- `jlens_concept_pr` — precision against the J-lens top-10, not a bar.
- `agentic_misalignment` — design score netted against foils, not an item pass bit.

Under the flag, an ungated family is skipped (listed under "skipped / failed" with the reason),
never silently run on its full bank.

## Artifacts

```
src/wsbench/baselines/text_inversion.py   build prompts, ask Opus, write draw readouts, gate, freeze
evals/baselines/anti_text_inversion.json  the frozen subset (tracked)
evals/baselines/README.md                 + "Anti-text-inversion subset" section
outputs/baselines/text_inversion/         prompts.jsonl, answers/draw{0,1,2}.jsonl,
                                          readouts/draw{d}/<family>.jsonl, judged/draw{d}/ (untracked)
src/wsbench/cli.py, runner.py, mcjudge.py anti_text_inversion=True flag
tests/test_text_inversion.py              offline (no network)
README.md                                 flag documented under Quickstart / Baselines
```

Frozen file shape:

```json
{
 "_source": {"answerer": "claude-opus-5-5", "draws": 3, "template": "...", "layer_rule": "...",
             "judge_model": "claude-opus-5-5", "written": "..."},
 "_not_gated": {"hallucination": "...", "jlens_concept_pr": "...", "agentic_misalignment": "..."},
 "<family>": {"instrument": "<prompt_version>", "judge_model": "...", "n_bank": 100,
              "n_ati": 37, "n_invertible": 60, "n_unverified": 3,
              "ids": ["..."],                       # the ATI subset, bank order
              "draw_pass": {"<id>": [true, false, null], ...}}
}
```

## Flag

`wsbench run ... anti_text_inversion=True` and `wsbench judge ... anti_text_inversion=True`:

- For each gated family, `items` = the frozen ATI ids (then `limit=`); an explicit `items=` is
  rejected under the flag.
- The scope is recorded in `results.json` `config.scope = "anti_text_inversion"` plus
  `extras.ati_n_bank`; ATI scope alone does NOT make `is_subset` true (it is a defined
  benchmark variant, not a partial run), so `complete` keeps its meaning.
- Stale guard: if the family's current `prompt_version` differs from the frozen entry's
  `instrument`, the run refuses that family (failed/2: "ATI subset was gated under instrument
  X; re-gate"). A judge_model difference is allowed (the subset is a property of the items
  given Opus's answers scored by the family rule) but recorded.
- Families not gated or with `n_ati == 0` are skipped (status `skipped`, exit 0), checked
  before any judge preflight; a stale or missing entry fails (exit 2).
- The macro is over gated families with `n_items ≥ 20` (smaller ones are listed as excluded,
  "n<20 (ATI)"). The prompt-only floor column is NOT drawn under ATI scope (it was
  measured on the full bank; the Opus prompt-only rate on the subset is 0 by construction).

## Run

1. `wsbench text-inversion stage=build` (CPU, tokenizer only).
2. `wsbench text-inversion stage=ask` (Opus, `ANTHROPIC_API_KEY` unset → ant profile;
   neutral preflight; refusals recorded once, never re-asked).
3. `wsbench text-inversion stage=readouts`, then per draw `wsbench run families=<gated>
   readouts_root=.../readouts/draw{d} out=.../judged/draw{d} judge_model=claude-opus-5-5
   layers=44 allow_missing=True` (buggy_code without `layers=`).
4. `wsbench text-inversion stage=gate` → `evals/baselines/anti_text_inversion.json` + a per-family
   summary table (n_bank, n_ati, n_invertible, n_unverified, Opus pass@1 mean, pass@3).
Smoke `limit=3` per family live before the full run. Runs in tmux `ati`, log under `logs/`.

## Report

Per family: n_bank, ATI count/share, invertible share, per-draw Opus pass rate (≈ an Opus
prompt-only floor), pass@3; macro; and a handful of example items per family on each side.

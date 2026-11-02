# Read sites for the association families (association, conjunctive, role-bound)

Since 2026-09-22 the readouts files of `conjunctive_association` and `role_bound_association` are
produced from a **summarize-prompt render**, read only at the prompt's suffix and the chat tail.
This page is the producer contract; the judges are unchanged. Since plan 0039 (bank v2,
2026-10-30) `association` reads the same render and the same 19 sites (its scene is the item's
`prompt`), replacing its former plain-render final token; Camila: "make sure that ALL token
positions from the summary sentence are being read and fed to the summarizer".

## Why

Both families used to be judged over *every* position of the bare stimulus render (conjunctive:
one blob of all positions × layers; role-bound: any-of over a 17-position window). Under that
regime a lens that merely echoes the current token hands the judge the story itself, and the judge —
not the lens — does the interpretation. A position sweep on the s3d-rl600 O-lens (Gemini 3.8 Flash
judge) showed most of the score came from the chat tail rather than the story positions
(conjunctive: story-only blob 0.06, chat-tail-only 0.10, full 0.15), but the instrument permitted it. Appending a summarize
request gives the lens a read site with a fixed semantic job, and reading only there closes the
loophole.

## Render

```
<|im_start|>user
{stimulus}   (association: {prompt})

Summarize the preceding story in one sentence.<|im_end|>
<|im_start|>assistant
<think>

</think>

```

i.e. the chat template with `enable_thinking=False` (empty think block), no system prompt, no
prefill. Story positions are unaffected by a suffix that follows them (causal attention), so a
producer that already holds a bare-render capture only has to capture the new tail.

## Sites

The 19 positions from the first suffix token through the end of the render, at the 11 grid
layers `readplan.GRID` = 20 / 24 / … / 60 (`layers=all` reads every model layer, 64 on
Qwen3.6-27B; plan 0032 / 0037). The measurements below predate the GRID change and were taken at
the former six layers 20 / 28 / 36 / 44 / 52 / 60. Lite (`reads=lite`) reads the final site only
(`final_token`, the `\n\n` after `</think>`) until the pre-registered lite-site procedure
(`scripts/lite_site_table.py`, gpu runbook R4d) freezes a rule into `evals/<family>/lite_rule.json`
(association: `same`, i.e. lite reads all 19 sites like full, Camila r2 2026-11-01; it replaced the
round-3 `offset_from_end k=7`, the `<|im_start|>` of the assistant header, measured on
final-olens-rl600-x4: 26.5% of the gold-bearing digest lines vs 7.5% at the final token;
conjunctive: `same` too, Camila r3 2026-11-01, replacing `final_token`, so a conjunctive lite run
judges exactly the full cells; role-bound: still `final_token`, below):

| rel (from end) | token | conjunctive single-site pass | role-bound per-cell pass |
|---|---|---|---|
| 18 | `Sum` | 0.00 | 0.000 |
| 17 | `mar` | 0.00 | 0.000 |
| 16 | `ize` | 0.06 | 0.104 |
| 15 | ` the` | 0.01 | 0.052 |
| 14–10 | ` preceding` ` story` ` in` ` one` ` sentence` | 0.00 | 0.000 |
| 9 | `.` | 0.09 | 0.086 |
| 8 | `<|im_end|>` | 0.00 | 0.002 |
| 7 | `\n` | 0.03 | 0.102 |
| 6 | `<|im_start|>` | 0.01 | 0.072 |
| 5 | `assistant` | 0.00 | 0.005 |
| 4 | `\n` | 0.07 | 0.088 |
| 3 | `<think>` | 0.00 | 0.000 |
| 2 | `\n\n` | 0.00 | 0.000 |
| 1 | `</think>` | 0.00 | 0.000 |
| 0 | `\n\n` | 0.07 | 0.042 |

(s3d-rl600, k=1, T=1.0; conjunctive = one 11-way MC over the site's six layer bags; role-bound =
all three MCs right in one (site, layer) cell.) The content sits at the newline / punctuation
positions *after* the specials; the special tokens themselves read as nothing. All 19 sites are
shipped so the judged grid is the same for every lens; the families' `layers=` / `items=` keys
still restrict.

## Numbers under the old and new regimes (s3d-rl600, Gemini 3.8 Flash)

| family | bare render, old sites | summarize render, 19 sites |
|---|---|---|
| role_bound_association (item = any cell) | 0.40 | 0.63 |
| conjunctive_association (one blob per item) | 0.15 | 0.14 |

Role-bound gains (best single cell 11 → 18 items passing / 100; agent/patient accuracy per cell
0.06–0.12 → 0.12–0.17); conjunctive is flat, with ~83 % "cannot tell" either way.

## Role-bound under oa-v2 (plan 0042)

- **Layers:** `readplan.GRID` (20..60 step 4, 11 layers); the 19 sites are unchanged.
  `wsbench plan role_bound_association` emits them as `suffix_text_then_tail`; `reads=full`
  requires the whole 19-position span per (item, layer) (`min_full_positions = 19`, contiguous,
  ending at the final token). A judge-side story-echo guard refuses (or, under `allow_missing`,
  drops and counts) any cell read before the suffix.
- **Lite:** `reads=lite` keeps one site per layer: `final_token` (rel 0 above) until the
  pre-registered support-share procedure (`scripts/lite_site_table.py`, gpu runbook R4d)
  freezes a rule into `evals/role_bound_association/lite_rule.json`. Its candidates are
  `final_token`, the top-3 `offset_from_end` k by pooled support share over the s3d-rl600 /
  jlens / mlnla-rl2-2000 full all-layer digests, and `offset_from_end k=4` (the `\n` after
  `assistant`, rel 4 above); the rule switches from `final_token` only on more than 10 points
  of share, and pass rates (like the per-cell column above) are never consulted.
- **Single-statement rule:** whatever the site, a relation counts only if ONE statement (one
  `- ` bullet of one sample, or one token list) names agent, action and patient; the per-cell
  pass column above is the oa-v1 (lenient) judge and is kept as history.

## Producing a readouts file

One row per (item, layer, site) in the readout contract of the [top-level README](../README.md), `pos`
indexing the render above, `token` the site's token, e.g.

```
{"id": "q01_a", "layer": 52, "pos": 68, "token": "\n\n", "samples": ["- After a long day, Laura packed boxes in the kitchen, meticulously clearing the house before…"]}
```

(The files under `examples/readouts/` are dry-run fixtures; `wsbench plan` is the read site of
record.)

## relational_multihop (plan 0043, 2026-10-30)

Camila: "We should do every position starting after the second sentence (including the full
stop), so "Avery's landlord is Sam. Sam's sibling is Riley. In other words, Riley is Avery's"
starts at ". In other words, Riley is Avery's"."

| reads | rule | positions (Qwen3.6-27B) |
|---|---|---|
| `full` (default) | `{"kind": "suffix_text", "text": ". In other words, P3 is P1's"}` | the full stop of sentence two through the possessive blank: 9 (52 items), 10 (36), 11 (6), 12 (6); 966 per layer |
| `lite` | `{"kind": "final_token"}` | the blank `'s` alone (the pre-0043 read; the span's last position) |

Render `bare`, layers `readplan.GRID` (L20..60 step 4). `rel-s00-a` resolves to indices 12..20 =
`. ▁In ▁other ▁words , ▁Riley ▁is ▁Avery 's` (checked with the model's `tokenizer.json`; the
last index equals the cached readouts' blank on 100/100 items). `wsbench plan` asserts the anchor
`". In other words"` occurs once per stimulus; `adapt` freezing refuses a tokenizer whose span
does not start on a token ending in `.`; the judge raises if a full run starts elsewhere.

## moral_rationale (plan 0046)

| reads | positions | layers |
|---|---|---|
| full (default) | every position of the chat render (`{"kind": "all"}`: user-turn template, stimulus, assistant header) | `readplan.GRID` |
| lite (`reads=lite`) | the last five (`'\n'` after `assistant`, `<think>`, `'\n\n'`, `</think>`, `'\n\n'`; the v1 read site) | all full layers (`lite_layers = None`) |

Render: the chat template with `enable_thinking=False`, the item's `stimulus` as the user turn
(and its `system` turn when the bank carries one), no prefill. Lite is a subset of full, so one
GPU read serves both. A full read needs one contiguous run of >= 6 positions per (item, layer)
ending at the item's last position (`EvalSpec.min_full_positions = 6`), so a tail-5 file judged
as full exits 2.

# Producing readouts

Judging is the contract; producing is optional. The item banks, the judges, the baselines and
the results contract are the benchmark; to score a lens you run it on the cells the plan names,
anywhere, and hand this repo one readouts file per family. `wsbench produce` (below) is a
bundled producer for anyone who would rather not write that plumbing. This page is the
interface between the two halves.

## 1. Get the read plan

```
uv run wsbench plan out=outputs/plan               # every family
uv run wsbench plan families=poetry,buggy_code     # a subset
```

One JSONL per family, one row per bank item. A row says exactly what to feed the model, how to
render it, which token positions to read, and at which layers:

```json
{"family": "poetry", "id": "couplet-ahead-head", "render": "plain",
 "positions": {"kind": "line_one_tail"}, "layers": [20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60],
 "text": "A rhyming couplet:\nThe captain pointed at the route ahead,\nAnd told his crew to follow where he'd ",
 "note": "line one's last word through the newline that ends it (never the line-two stub); lite = that newline",
 "lite_positions": {"kind": "final_token"}}
```

| key | meaning |
|---|---|
| `render` | how to turn the row into a token sequence; the vocabulary is `wsbench.readplan.RENDERS` (`plain`, `chat`, `chat_context`, `chat_prefill`, `chat_dm`, `chat_summarize`, `bare`, `captured`) |
| `text` / `messages` / `system` / `prefill` / `suffix` / `assistant` | the pieces the render composes; `captured` rows ship `extra.input_ids` instead |
| `positions` | a rule over the rendered tokens (below); `wsbench.readplan.resolve(rule, tokens)` turns it into indices once you have tokenized the render |
| `lite_positions` / `lite_layers` | the `reads=lite` site (plan 0032): a rule over the row's FULL positions (`same`, `final_token`, `offset_from_end {k}`, `offsets_from_end {ks}`, `last_n {n}`, `positions {…}`, `every_nth_plus_tail {n, tail}`) and its layers (absent = the full layers). Lite is always a subset of full, so one full read serves both; `wsbench run reads=lite` re-judges the same file. A file produced `reads=lite` (sidecar `reads: "lite"`) already holds only the lite site and is judged as it is: the rule is never applied twice |
| `layers` | the decoder layers to read (residual stream after that layer) |
| `note` | the family's read site in one line; the family README has the rest |

Positions rules, all handled by `resolve`:

| kind | selects |
|---|---|
| `final_token` | the last token of the render |
| `offset_from_end {k}` | the token `k` from the end (`k=1` is the last) |
| `last_n {n}` | the last `n` tokens |
| `all` | every token |
| `all_from_end` | every token, reported as negative offsets `-n..-1` (arithmetic intermediates: the bank and judge count from the end) |
| `positions {positions}` | explicit indices (jailbreak, J-lens precision) |
| `line_one_newline` | the newline token that ends line one (poetry's lite site, and its full read before plan 0038) |
| `line_one_tail {anchor?}` | line one's last word through the newline that ends it: the word's tokens, any punctuation after it, and that newline (poetry's full read, plan 0038; `couplet-ahead-head` → `" ahead"`, `","`, `"\n"` = positions 14-16). `anchor: "last_newline"` ends it at the last newline anywhere (adapted `chat_prefill` items) |
| `from_token {token}` | from the first token with that text through the end (chain's question span) |
| `from_text_last_token {text}` | from the LAST token of the (last) occurrence of `text` through the end (chain: "The starting number is 23" reads from the "3") |
| `from_last_sentence_start` | from the first token of the last user turn's final sentence through the end (user modelling) |
| `suffix_text {text}` | the tokens spelling `text` at the end of the render (directed modulation's carrier) |
| `suffix_text_then_tail {text}` | those plus every token after them (the association families' summarize suffix and chat tail) |

Renders are described for Qwen3.6-27B's chat template; another model's template changes every
position index, which is why the rules are given as rules and not as numbers wherever the bank
allows it. `resolve` works on the token strings of any tokenizer.

## 2. Read the lens

For every row, every position the rule selects and every layer: run your lens on the residual
activation there and keep what it produces. A prose lens gives one or more text samples; a token
lens gives a ranked token list with scores.

## 3. Write the readouts file

One JSONL per family, one row per (item, layer, position), in the contract of the top-level
README:

```json
{"id": "couplet-ahead-head", "layer": 36, "pos": 16, "token": "\n", "samples": ["led the way"]}
{"id": "couplet-ahead-head", "layer": 36, "pos": 16, "token": "\n", "tokens": [" led", " said"], "scores": [9.1, 7.7]}
```

`id` is the row's `id` from the plan, `pos` the index into your render, `token` that position's
token string (optional, checked where a family knows it). A file is all-prose or all-tokens.
Missing cells are fatal by default: every (item, layer) the plan asks for must have a row, or the
run must be told `allow_missing=True` and the result is marked incomplete.

`wsbench convert-gen-dir` and `wsbench convert-read-json` produce this shape from the two
in-house producer layouts; anything else needs a few lines of your own.

**Layers.** Every family's plan reads the 11-layer grid (`GRID`, agentic `GRID + [63]`).
`wsbench plan layers=all` (or `WSB_LAYERS=all` in a producer's environment) plans every model
layer; `layers=20,44` any combination. A file may hold more layers than the plan: every present
layer is judged. `wsbench run layers=44` judges one layer (a complete, defined variant);
`layers=each` runs the all-layer config plus one sub-run per layer in the file.

**The sidecar (plan 0032 §2.9).** A producer declares how it sampled, beside the file:
`<family>.jsonl.meta.json` = `{"reads": "full|lite", "sampling": "bullet4|prose1|tokens10",
"reader": "<method>", "arm": "<arm>", "layers": [...], "plan_sha": "<reads.plan_sha(family)>"}`.
The rule (decision Q1): a SINGLE-bullet oracle lens (the `*-x4` arms) gets 4 separate
samples per activation (`bullet4`); every other prose method, the multi-bullet s3d O-lens and NLA
included, ONE sample per activation (`prose1`); a token lens its top 10 (`tokens10`). The
sampling is declared, never inferred from bullet shape; `sampling=` on the CLI overrides it.
`wsbench produce` and the converters (`sampling= arm= plan_sha=`) write the sidecar. With a
sidecar, `reads.load` enforces the full span (a lite file under `reads=full`, a missing plan
layer or a different `plan_sha` exits 2); a sidecar-less file is judged as it is, with the
same checks reported only (`config.reads_checked = "no_sidecar"`, never a campaign result).

## 4. Judge

```
uv run wsbench judge family=poetry readouts=outputs/readouts/mylens/poetry.jsonl out=outputs/judged/mylens/poetry dry_run=True
uv run wsbench run all=True readouts_root=outputs/readouts/mylens out=outputs/judged/mylens
uv run wsbench report dir=outputs/judged/mylens
```

Every run is in summary mode by default (plan 0024: each item's readouts go to one passive digest,
judged once; `docs/summarizer.md` § Item digest). Add `opts=aggregate=native` for the per-cell
rules, into a separate `out=` dir.

## Or let the repo produce them

`wsbench.produce` is a small producer over Hugging Face transformers, for anyone who has a GPU
and wants readouts without writing the plumbing. Install the `gpu` extra (`uv sync --extra gpu`)
and:

```python
from wsbench.produce import Producer

# methods: logit_lens | jlens | rlens | olens | nla
p = Producer.load("Qwen/Qwen3.6-27B", "jlens")
p.read("The athlete Muhammad Ali plays the sport of", pos=-1, layer=36).readout.tokens
p.read_prompt("Sechs geteilt durch zwei ist", positions="all", layers=[20, 36, 60])
# a whole eval set, resumable; the plan picks the cells
p.run_family("poetry", "outputs/readouts/mine/poetry.jsonl", limit=10)
# swap method, keep the loaded model
p.use("olens")
```

The same from the shell:

```
wsbench produce family=poetry method=logit_lens out=outputs/readouts/mine/poetry.jsonl
wsbench produce text="The athlete Muhammad Ali plays the sport of" method=jlens positions=-1 layers=20,36,60
```

What it does: renders the prompt the way the plan says (its chat template, thinking off),
captures the residual stream after each requested decoder block in one forward pass, and hands
each (layer, position) vector to the method. The vector lenses (`logit_lens`, `jlens`, `rlens`)
return the top-10 tokens with scores; `olens` verbalizes through its LoRA with the vector placed
in the carrier prompt's `<activation>` slot as `alpha · unit(h)`, the adapter off while capturing
and on while generating; `nla` runs Karvonen's reader with the vector added norm-matched at its
marker token. Methods are plain classes behind one `read(h, layer)` protocol, so a new lens is a
few lines. Sampling for the verbalizers is `Sampling(temperature=1.0, top_p=0.95, top_k=64,
max_new_tokens=256, k=1)`, the settings the in-house arms used.

Two spellings, on purpose: the read-site `token` is `tokenizer.decode([id])`, exactly what the
banks store (`"\n"`, `" öffnen"`, `"<|im_end|>"`); the ranked `tokens` of a token lens are the
byte-level BPE strings with `Ġ`/`▁` shown as a space (`" led"`, and `"çļĦç»ĵæŀľ"` for 的结果).
`wsbench.readouts.load_readouts` decodes each of those to text once, on load
(`wsbench.bpe.decode_token`: `"çļĦç»ĵæŀľ"` -> `"的结果"`, `"Ċ"` -> `"\n"`), so every summarizer,
judge and regex sees text. Until 2026-10-29 only hallucination, jlens_concept_pr's reference
files, summary mode and agentic_misalignment's read-site context decoded; every other family saw non-ASCII tokens as mojibake. Write the
vocabulary strings. A string that does not decode cleanly is kept as written: a token holding
part of a character stays in its byte-level spelling, and most already-decoded text survives
(`"café"`, `"się"`), but decoded text that happens to spell valid UTF-8 in the byte table
(`"Ã©"`) is decoded again.
`pos` is the index the plan resolves: absolute, except the two rules that count from the end
because their banks and judges do — `offset_from_end` (some multihop items) and `all_from_end`
(arithmetic intermediates) — whose rows carry the negative offset (`-8`). A single-layer lens reads at its trained layer whatever the
plan lists: `nla` is layer 42 (not on the benchmark grid; the in-house L44 NLA numbers were
off-layer and are superseded). `nla` also loads its own copy of the reader (a second 27B on the
same device), so it wants an H200; the other methods fit one H100.

What it is not: fast. It reads one prompt at a time on one GPU, which is right for a token
position, a question or a family, and wrong for the whole benchmark at every token; the in-house
runs fan that out over Modal.

## What the plan does not carry

- **Model-dependence.** The banks were gated on Qwen3.6-27B; `wsbench capable` re-runs that gate on
  another model, and `AGENTS.md` says which families port, which need re-gating and which need
  re-generating.
- **Sampling.** The in-house arms used k=1, temperature 1.0, top-p 0.95, top-k 64, max 256 new
  tokens for prose lenses and top-10 for token lenses; the judges accept any k.
- **Steering.** `introspection` rows carry `extra.steering` (a concept or gaussian vector
  added at layer 12 over a token span, `h <- h + beta * ||h|| * v / ||v||`); the producer must
  apply it in the forward that is read. The vectors ship with the bank
  (`evals/introspection/vectors/*.npy`; each row names `vector_file` / `vector_row`), and
  `wsbench produce` applies the steer itself (a forward hook on the inject layer's output over
  the span; `type: none` rows are a plain forward). Any other steering type is refused.
- **A family without text.** `jlens_concept_pr` ships captured token ids and positions, not
  prompts: its items are the model's own activations, read by re-feeding those ids
  (`hallucination`, the other such family, left for HallucinationBench, plan 0040).

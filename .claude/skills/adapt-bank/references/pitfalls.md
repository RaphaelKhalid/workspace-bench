# Pitfalls (learned) and known defects

## From the earlier per-model banks (global-workspace 1f36ca88: `.pm` / `.pmeq`)
- **Filtering is not adapting.** `.pmeq` refilled each family with leftover 27B candidates and then
  authored more with the same "long-tail / obscure" prompts. Its "famous" knob was applied only
  after the reuse step.
  - Yields on Qwen3.5-4B: multihop_mt 3% (family removed 2026-10-30), multilingual_mt 4%, multilingual_multihop 2%, chain
    3.5%, brew 0%, relational 0%.
  - Change the difficulty the brief asks for first.
- **Ungated families slipped through.**
  - `.pm` copied user_modeling and directed_modulation without gating them on the subject.
  - The single-token multihop bank never gates the bridge.
  - Gate every leg of every family that has one.
- **Off-policy content.**
  - The Qwen-sizes port of the removed hallucination family (plan 0040) fed Qwen3.6's token ids
    to the small models.
  - The Gemma port teacher-forced Qwen's responses.
  - Both are off-policy. Regenerate on the subject.
- **Gate ≠ read render.** The V4 port gated implicit favourites without the answer stem, which is
  not the render the lens reads. Gate in the render that is read, or in the bank's stated gate
  render.
- **Wrong thinning rule.** The V4 port thinned read sites with `round(i*(n-1)/7)`; the bank
  rule was `int(i*len/8)` (removed hallucination family, plan 0040). Copy a bank's rule exactly.

## Grading
- Don't use OpenRouter stand-ins for the subject. `wsbench capable` is an OpenRouter shortcut with
  reasoning effort "minimal". A hidden-reasoning model passes no-chain-of-thought families
  (chain, arithmetic) in ways the bank gate would not allow.
- Deterministic graders are strict. A miss can be a valid alias or a translation, so read 20 misses
  per family. If most are aliases, run with `llm=<claude id>` (it only re-grades the misses), or
  add `aliases` to the item.
- Never accept an answer that writes an intermediate. The `forbid` meta on chain and arithmetic
  fails any rollout that puts the latent on the page.

## Small-model behaviour
- Trailing spaces and `is "` endings break small models' continuations. Try the stripped render as
  a *new item*; never edit an original in place.
- 0.8B and 2B models often answer in the wrong language, or add prose before the answer.
  - The format is the problem, not the latent.
  - Look at the answer before you step down a tier.
- On-policy generation at T=1 with full vocabulary loops on small models. Record
  `n_truncated_at_max`.

## Known defects in the frozen banks (don't copy them into adapted banks)
- moral_rationale:
  - 23 items have `gate_pass=False`;
  - 21 committed items have `look_for_reasons[0]` supporting the side opposite
    `commit_direction`.
- multihop_mt (removed 2026-10-30): 9 items broke the leak rule and 3 broke bridge/target overlap.
- multilingual_multihop: 1 known defect.
- agentic_misalignment: 3 "misaligned" items have a misalignment rate of 0.125–0.25.
- `adapt.lint` over the frozen banks flags:
  - multihop: 4 without "Fact:", 1 leak;
  - multilingual: 4 cognates;
  - basic_readout_mt: 1 leak;
  - multilingual_multihop: 2 leaks.

  New items must lint clean. Original items are kept or dropped by the gate, not by the lint.

## Ops
- Box SSH goes through one ControlMaster (`ssh -O check runpod`). Poll slowly and sequentially;
  bursts of fresh connections make the 1Password agent refuse to sign.
- The fellows Opus org limits (10M ITPM / 2M OTPM) are shared with judges. Pace authoring and grading.
- Keys: never print or write them. On the RunPod box, credentials live only in `/dev/shm`.

## Learned on Qwen3.5-4B (2026-10-15..17)
- **Repeated latents inflate the fill.** Opus repeats concepts across calls in one run; the
  ALREADY-USED list must include the run's earlier calls (`author(..., made)`), and `select` skips
  a new item whose latent is already selected (`UNIQUE_LATENT`). It had inflated 7 families by 98.
- **Undecided ≠ fail.** The grader retries transient API errors; with `max_rate 0` a single `None`
  failed a clean leak screen (conjunctive 90 → 96 after the fix).
- **Long Claude runs outlive the token.** Use `auth.Session` (re-reads the Dict on a 401). A fresh
  `pushed_at` does not prove a fresh token (the old push resent a stale one).
- **Grade in parallel.** The gate graded one call at a time: ~3 h for 170 items (now 16 threads).
- **Own-answer guards must be scoped.** A "None is not a favourite" refusal list containing "a"
  broke moral's A/B answers (149 → 100) until it was limited to basic_readout implicit.
- **Judge-side and plan-side paths must follow `WSB_BANK_ROOT`.** Capture rows (the removed
  hallucination family) and the jlens reference were hard-coded to the 27B (off-policy reads); both fixed.
- **The plan speaks subject layers** (report.json `n_layers`; 63 clamps to the last block); banks
  that store layers (buggy, mcdm, arithmetic) are already remapped at freeze.
- **poetry is read in the render the rhyme was committed in** (`gate_variant`), and
  `line_one_newline` ignores the chat tail.
- **Judge JSON truncates at 300 tokens** (agentic commitment judge: 22% unreadable); give 800 and
  parse with `raw_decode`.
- **Tied embeddings** (Qwen3.5-0.8B..4B): no `lm_head.weight`; the J-lens readout uses
  `embed_tokens` as W_U.
- **9B on the 4090:** 16.8 GB weights; vLLM needs `gpu_memory_utilization=0.93`,
  `enforce_eager=True`, `limit_mm_per_prompt` image/video 0.
- **What the 4B can't do:** relational composition (<1% scenes), brew tables (0/460), value-bug
  tracing (1/15 buggy t1; crash bugs work), stereotype-reversed role binding without explicit cues.
- **J-lens files differ by size:** neuronpedia ships `*_jacobian_lens_n1000.pt` for qwen3.5-4b and qwen3.6-27b, but only the full `*_jacobian_lens.pt` for qwen3.5-0.8b / 2b. Use the full lens there and record the deviation in the bank's manifest `adapt.lens` and the report note.
- **Never take the GPU lock in a tmux command line that ends with `exec bash`:** the shell inherits the lock fd and holds it after the job ends (blocked the 9B resume for 7 min). Take it inside the script (`exec 9>lock; flock 9` in a child bash).
- **vLLM on Modal needs nvcc:** Gemma-4 failed engine start on `debian_slim` ("Could not find
  nvcc"; flashinfer JIT-compiles kernels). `adapt_modal.py` uses `nvidia/cuda:13.0.1-devel` (cu130 =
  vllm 0.31's torch). A failing `@modal.enter` restarts in a loop on a paid H200: read
  `modal app logs adapt-subject-llm` within minutes of the first call.
- **`pkill -f <pattern>` inside a shell command whose text contains the pattern kills that shell**
  (exit 144). Kill by PID, or kill the tmux session.
- **New gate legs don't apply retroactively:** gate records are append-only and last-wins, so
  originals AND passing new items must be re-gated (`regate=true` on profile and gate).
- **Non-Qwen tokenizers re-stamp before select** (`live_rows`): OLMo loses 15/100 typo_mt, 5
  basic_readout_mt, 4 multihop_mt (removed 2026-10-30) to one-token forms; fill refills them before freeze.
- **J-lens for a subject neuronpedia lacks:** `scripts/fit_jlens_modal.py` (official estimator,
  neuronpedia's recipe, H200 chunks, exact merge). Validated on the 4B: per-layer cosine to
  neuronpedia's lens min 0.927, mean 0.986 at n=400. Fitted: 9B (n=400), OLMo-3-7B-Instruct
  (n=600; its neuronpedia lens is for the base model).
- **Sanity-check every fitted J-lens before serving it:** per layer, the share of read positions
  whose current token appears in the lens top-10 (4B neuronpedia 0.46-0.62 at 30-55% depth; our
  9B 0.43-0.53; OLMo-Instruct 0.12-0.40). Gemma-4-31B scored 0.01-0.05: its residual shrinks with
  depth and J at the last layer is far from identity, cause open (fit and capture
  hook the same block outputs, so not a hook mismatch). Its bank sits at `jlens_concept_pr.UNVALIDATED`, status blocked.
- **Gemma-4-31B J-lens fit OOMs an H200 at dim_batch 64:** use 16 (rows per backward; same lens).
- **Token rotation race:** the Mac's refresh revokes the old access token a few seconds before the
  new one lands in the Dict. A 401 in that gap used to kill the step ("token is missing or
  expired"; 2B regrade and OLMo-32B moral, 2026-10-18 22:52 UTC). `Session.refresh` now polls
  the Dict for up to `REFRESH_WAIT` (600 s) before failing.
- **Org rate limit when sets build in parallel:** Opus output is capped at 2M tokens/min per org;
  four parallel fills hit it (429) and authoring crashed (2B, OLMo-32B fill, 2026-10-18). All
  Claude calls go through `Session.create` / `Session.stream_final`, which wait out 429/5xx with
  jittered backoff. Keep at most ~3 fills authoring at once.
- **Gate in the read render:** the shared `_chat` adds a system turn, which certified items in a
  render the lens never reads (35B-A3B audit). Any family whose read render is not the plain user
  turn must be asked exactly like its read plan.
- **Arithmetic null pool < 8 is now enforced at freeze:** recurred in all three audits (4B, 9B,
  35B-A3B); freeze drops such items (with twins) until every pool has 8 peers.
- **The model grader accepted translations in the multilingual/typo families:** the shared rubric
  (`capable.GRADE_SYSTEM`) counts "a faithful translation" as correct, so English "lollipop" passed
  for Vietnamese "kẹo mút" and "ca phe" for "cà phê" (OLMo-32B self-audit). Those families' surface
  legs now set `meta.strict_form`; the grader appends `STRICT_FORM` (other language, transliteration,
  misspelling or missing diacritics = wrong) and keys its cache on the flag. All sets were
  strict-regraded 2026-10-19.
- **Rhyme dictionary race (poetry):** `pronouncing.init_cmu()` is not thread-safe; parallel gate
  threads read a half-loaded CMU dict and `@cache` stored "no rhyme" for common words (Qwen3-8B
  poetry originals 7/100 → 82/100 after the fix). `rhyme.py` now loads under a lock. Every set
  gated before 2026-10-19 gets a `regrade families=poetry` (it only ever rejected valid rhymes).
- **Padded canonical names kept coming back** (9B 95, Qwen3-8B 65 new `*_mt` items) because no
  deterministic rule knows the everyday name. `natural.py` (run in `lint_and_gate` whenever Claude
  grading is on) asks Claude for the everyday name of each scored unit and rejects the item if
  the family's own regex scorer would not credit "Thinking about <name>." Validated on the Qwen3-8B
  audit's flags: 6/6 caught, 0/6 false rejections.
- **Strict form must reach the deterministic match:** `gate.fold` strips diacritics, so "frio"
  passed for "frío" before the strict grader ever saw it (OLMo-32B audit). For `strict_form`
  asks a deterministic pass must also hit with accents kept (`gate.exact_hit`); otherwise it goes
  to the strict model grader (or stays undecided). `first_line` now splits on "\n" only (U+2028).
- **BOS in raw renders (Gemma-4):** the chat template starts with `<bos>` but the tokenizer never
  adds it, so plain/bare renders (read plan, gate prompts, jlens pt seeds, the J-lens fitter's
  WikiText prompts) had no BOS and Gemma looped ("26 is 26 is"; 0/698 plain gate legs passed). That
  probably also explains the failed Gemma J-lens. `template.bos_prefix(tok)` = the BOS the chat
  render starts with when the tokenizer doesn't add it; applied in `produce/render.py`,
  `Runner.render`, `adapt_jlens.seed_ids` and `fit_jlens_modal.py`. Qwen/OLMo: empty, unchanged.
- **Partial multi-word answers passed the strict grader** ("gigi" for "dokter gigi", 2B
  multilingual_typo): `STRICT_FORM` now rejects them, and its cache key is versioned (`strict2`).
- **Moral reasons arguing the wrong side recur in every audit** (2–8 items per set): `moral.apply`
  trusted the distiller's `supports` label. Fixed 2026-10-21: `moral._verify_sides` asks Claude
  whether the looked-for reason argues FOR the committed answer (validated on the 2B audit's flags:
  7/7 caught, 0/10 false rejections).
- **Gemma-4 J-lens fixed (three causes):** (1) BOS missing in the fit; (2) a few prompts with
  Jacobians ~10^3x the median dominate the mean, so use `fit_jlens_modal.py --trim-k 5` (per-layer
  trimmed mean; `--merge-only` re-merges existing chunks); (3) the raw cosine readout ignores
  the final RMSNorm, so use `adapt_jlens.py --readout norm_centered` (final norm on J*h, minus a
  fixed per-layer mean direction; never a within-prompt mean, because the bank reads one position per
  rollout). Sanity 0.00-0.03 -> 0.20-0.64. The penultimate target did not help on Gemma.

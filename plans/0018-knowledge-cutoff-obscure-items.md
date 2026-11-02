# 0018: merge nocot obscure-knowledge items into knowledge_cutoff

Status: rev 2 (folds in critique round 1). Owner: Camila. Date: 2026-10-28. Source bank: global-workspace #610/#611
(`evals/workspace-bench/hillclimbing_evals/multi_token/obscure_knowledge/`).

Camila (2026-10-28): "we should increase the number of items or merge it with the other knowledge
cutoff eval". The obscure bank (nocot-bench knowledge facts that qwen3.6-plus answers correctly and
Qwen3.6-27B answers wrongly with >= 7/10 agreement, G1-gated) has the knowledge_cutoff construct:
the label is the 27B's own stable wrong answer to a short factual question, frontier readers miss
it, and the all-position judge (plan 0017) scores it unchanged. No knowledge_cutoff number exists
yet under the plan-0017 judge, so the merge breaks no comparison.

## Rev 2 decisions (binding; override the sections below where they differ)

- **No credit change.** `tests/test_readme.py` bans "nocot-bench" from README §Credits / NOTICE.md
  (plan 0000: nocot-bench is cited only if Camila names a family). `EvalSpec.sources` stays as is;
  nocot is named only in the family README (provenance of the fetch), and that test is untouched.
- **Adapted roots.** `load_items()` reads `registry.bank_path(NAME)` (exits under an adapted root
  with no knowledge_cutoff bank, as `readplan._bank` already does) and appends the obscure items
  only when `WSB_BANK_ROOT` is unset. Test: exit 2 under the variable.
- **Offline tests.** `tests/conftest.py` gains an autouse fixture that replaces
  `knowledge_cutoff.nocot.questions` (id -> problem text) with a synthetic stub returning
  `"synthetic question <id>"` for every obscure id, so every existing `readplan.plan` / `wsbench plan`
  test stays offline and obscure rows still carry text. The fetch / sha256 / `problem_sha256`
  checks are tested separately with a fixture zip and a fake bank. `wsbench produce` also renders
  through `readplan`, so it fetches too (documented).
- **Render** = `template.format(question=problem.strip())` (the source's exact render);
  `problem_sha256` is checked on the raw `problem`.
- **Source pin.** The copied header gains `source_bank = {repo: camila-blank/global-workspace,
  commit, path, sha256 of the source items.json}`. Nothing hard-codes the item count; tests use
  `len(obscure)`.
- **`EvalSpec.item_ids`** also feeds `cli._n_items`, so `wsbench list` counts 109 + obscure.
- **ATI staleness guard.** A test asserts the frozen ATI `knowledge_cutoff.ids` equal
  `load_items()` ids (the prompt version does not change, so this is the only guard).
- **Sanctioned test change:** `tests/test_knowledge_cutoff.py::test_spec_and_plan` asserts the
  first 109 plan rows are the frozen bank in order, followed by the obscure rows (fetcher stubbed).
- **README caveats:** common-word code options (`after`, `core`, `utils`) can verify on generic
  prose; token lenses cannot verify multi-digit golds; real all-position readouts and judge
  `cells.jsonl` for obscure items carry paraphrases of nocot questions at user-turn positions and
  must not be published; any toy readouts for obscure items are synthetic. `extras.by_source` is
  reported for every arm.

## Data

- `evals/knowledge_cutoff/items.json` (the frozen 109) is **not edited**.
- New `evals/knowledge_cutoff/obscure_items.json`, copied verbatim from the source bank: header
  (source pin: nocot repo, commit, zip sha256; prompt template; funnel; floors) + items. **Ids
  only**: no question text, no raw completion (nocot asks that its unpacked items not be
  republished). Per item: `id` (`<nocot domain>:<problem_number>`), `domain`, `kind`,
  `problem_sha256`, `gold`, `truth` (a string), `options` (K = 5, seeded order), `option_units`,
  `units`, `option_sources`, `qwen`, `plus`, `g1`.
- The family's working item list = the 109 + the obscure items, **only when `WSB_BANK_ROOT` is
  unset** (the obscure labels are Qwen3.6-27B's; no adapted subject has a knowledge_cutoff bank,
  and an adapted run must never pick up Qwen labels). Obscure items are normalised on load to the
  fields the judge reads: `truth -> {"canonical": truth}`, `stratum = "nocot"`,
  `label_type = "obscure_" + kind`, plus `source = "nocot"` (the 109 get `source = "cutoff"`).

## Prompt rendering (`wsbench plan` only)

- `knowledge_cutoff/nocot.py`: fetch `https://github.com/<repo>/raw/<commit>/data/nocot_data.zip`
  into a cache (`$WSB_CACHE` or `~/.cache/wsbench/nocot/<sha256>.zip`), verify sha256 (refuse on
  mismatch), read `data/knowledge/<domain>.jsonl` with the password from nocot's README (stored as a
  constant, as nocot itself publishes it), join on `domain:problem_number`, verify
  `problem_sha256` (refuse on mismatch), render `user = template.format(question=problem)`.
  Nothing unpacked is written to disk; the cache holds the zip only.
- `readplan` rows for obscure items: render `chat`, positions `all_from_end`, `GRID`, `text` = the
  rendered user turn, `extra = {"source": "nocot"}`. The 109 keep their rows unchanged.
- **Judging needs no nocot text** (the judge never sees the question), so `wsbench judge` / `run`
  stay offline. `text_inversion.construction_entry` currently reads ids through `readplan.plan`,
  which would now fetch nocot; it gains an optional `EvalSpec.item_ids: Callable[[], list[str]]`
  hook (None = the readplan ids, unchanged for every other family), and knowledge_cutoff sets it to
  the merged id list, so ATI stays offline.

## Judge, ATI, docs

- Judge code unchanged except `load_items()` (merged list) and `by_source` in `extras` (rate per
  source: cutoff / nocot) beside `by_stratum`; `PROMPT_VERSION` unchanged (the instrument did not
  change; the bank grew). `calls_per_arm` recounted (n items x 11).
- ATI: knowledge_cutoff stays `CONSTRUCTION_GATED`; its gate text adds the obscure G1 (Opus x3 +
  Sonnet, recall + MC, both framings); the frozen entry is regenerated (ids = 109 + obscure,
  `n_bank` / `n_ati` updated).
- Family README: a "nocot items" section (construct, funnel, ids-only rule, rendering, caveats
  above). Root README entry's What-it-is / Example lines mention both sources; CLAUDE.md one line.

## Tests (offline)

- The real obscure bank: every item has the fields above, no `problem` / `user` / raw key anywhere,
  K = 5, gold in options, ids unique and disjoint from the 109.
- `load_items` = 109 + obscure by default; exits 2 under `WSB_BANK_ROOT` (monkeypatched); obscure
  `truth` normalised.
- nocot rendering with a fixture zip built in the test (fake rows; a fake bank whose
  `problem_sha256` matches): sha256 refusal, `problem_sha256` refusal, rendered text = template.
- `readplan.plan("knowledge_cutoff")` with the fetcher monkeypatched: 109 + obscure rows, obscure
  rows carry the rendered text and `all_from_end`.
- `construction_entry("knowledge_cutoff")` makes no network call (fetcher patched to raise) and
  lists every id.
- Judge on toy readouts for one obscure item (monkeypatched `run_calls`): verified pick, by_source.

Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`.

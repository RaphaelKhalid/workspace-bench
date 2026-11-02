# 0029: retire brew_intermediates

Camila, 2026-10-29: "i think we should retire this eval".

Why (the 2026-10-29 audit and follow-up):
- The text alone solves it. Stock Qwen given only the prompt computes the intermediate (prompt-only
  0.96), and the ATI v2 panel inverts every item (0 brew items in the anti-text-inversion subset), so
  brew cannot tell reading the activation from re-deriving it from the rule table.
- The pass rule is lenient. The gold only has to beat two never-on-path colours, the start and answer
  are ignored, and passing is near-free whenever no off colour appears (57/75 J-lens summary passes).
  Random on-path naming scores 0.33–0.44; the judge's single "primary" pick is the gold only 0–9% of
  the time (J-lens 0.00 while passing 0.78).
- Built-in confound (the source repo's own caveat): the intermediate is often the model's runner-up
  answer colour, so a pass cannot separate a held step from a runner-up output.
- The native stir control fails (onchat O-lens 0.62 vs its null 0.38, before the start colour is
  read), so part of the native signal is not the computation.

## Change (the ttt removal of plan 0017 / #97 is the pattern)

- `registry.REMOVED_FAMILIES["brew_intermediates"]` = the reason above, one line. It is never
  registered again; old run dirs' `brew_intermediates/results.json` are excluded from the macro with
  reason `removed` (existing behaviour, retained unchanged).
- Delete: `evals/brew_intermediates/` (README + bank), `src/wsbench/evals/brew_intermediates/`,
  `examples/readouts/brew_intermediates.jsonl`, `tests/test_brew_intermediates.py`,
  `tests/test_summary_mode_brew.py`, `src/wsbench/adapt/brew_port.py` and
  `tests/test_adapt_brew_port.py`, and every `adapted/<model>/brew_intermediates.json` (plus any
  brew gate/candidate files under `adapted/<model>/`).
- Remove brew from every consumer, keeping each consumer's behaviour for the other families
  unchanged: `readplan` (its plan branch), `baselines/lucky_guessing.py` (builder + description),
  `baselines/prompt_only.py` (SATURATED entry), `baselines/text_inversion.py` (any brew adapter /
  not-gated entry), `capable/questions.py`, `adapt/{families,generate,lint,run}.py`, `digest.py`
  (any brew-specific unit logic, e.g. emit/stir units, and FAMILY_DEFAULTS / NATIVE_ONLY entries),
  `scripts/summary_mode_compare.py` (`_brew_native`, `_brew_summary`, the brew retained path),
  `atlas/{build,export_cb,normal_gate}.py`, `viewer/build.py` (GROUPS).
- Frozen floors: drop the brew entries from `evals/baselines/{lucky_guessing,prompt_only,
  prompt_only_summary}.json` and `anti_text_inversion.json` (rewrite these JSON files with the
  family key removed only; every other entry byte-identical in value).
- `adapted/<model>/report.json`: drop the brew family entry; keep every other key.
- Docs: README (the brew entry under Computational, the judges table, any counts such as "N
  families"), CLAUDE.md, AGENTS.md, `docs/summarizer.md`, `docs/summary_mode_validation.md`,
  `docs/producing_readouts.md`, `evals/baselines/README.md`, `adapted/README.md` and the per-model
  READMEs: delete brew's rows/sections; where a doc records history (plans, dated results), leave
  the history and add nothing.
- Tests: delete brew-only tests; in shared tests, remove brew cases/params only (sanctioned:
  test_capable, test_lucky_guessing, test_summary_mode_compare, test_text_inversion, test_adapt,
  test_readplan, and any test enumerating the registry), and add one test that `brew_intermediates`
  is in `REMOVED_FAMILIES` and not registered.

## Checks
`ruff check .`, `ruff format --check .`, `pytest -q`; `wsbench list` has no brew row; `grep -rn brew`
over src/ tests/ atlas/ scripts/ and the non-plan docs finds only the REMOVED_FAMILIES entry and its
test (and dated history).

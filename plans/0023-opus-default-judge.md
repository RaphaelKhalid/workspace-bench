# 0023: Claude Opus 5.5 is the default judge

Camila, 2026-10-29: "the default should be opus 5.5" — flip the default and re-measure the
floors. This lifts her 2026-10-15 "let's not change the judge in the public version for now"
(commit `0f5c626`, which reverted the 2026-10-11 switch `ddd88ac` + the Opus floor refreeze
`37e307a`). Every recent run of record (V4 port, summary mode, ATI v2 panel judging) already
used `judge_model=claude-opus-5-5` as an override; this makes that the instrument of record.

## Scope

1. **Default.** `judge_config.DEFAULT_JUDGE = "claude-opus-5-5"`. Retained pins, unchanged:
   agentic_misalignment and jailbreak_recognition stay on `claude-sonnet-5` (Camila
   2026-10-29: keep the Sonnet pins; Opus is blocked at agentic Stage B, see plan 0012);
   introspection stays pinned to `claude-opus-5-5` with `{"anthropic_effort": "default"}`
   (now equal to the default model, still an explicit pin); the regex families
   (`*_mt`, multihop_mt_v2, multilingual_multihop/typo, directed_modulation_obscure) stay
   regex-scored with `REGEX_JUDGE`, and `opts=judge=mc` on them now resolves to Opus.
   `hallucination` and `jlens_concept_pr` name `model=DEFAULT_JUDGE` and follow it.
2. **Reasoning is keyed by route, not by "same route as the family model".** Today
   `resolve` applies a family's `reasoning` dict only while the judge stays on the family
   model's route. After the flip, the family model's route becomes Anthropic for every
   default family, so OpenRouter-style dicts (`hallucination` / `jlens_concept_pr`
   `{"effort": "minimal"}`, `knowledge_cutoff` `{"effort": "low"}`) would start riding the
   Anthropic route — ignored by `anthropic_effort` but present in the cache fingerprint, so
   every cached Opus-override call (reasoning `None`) would miss. New rule in `resolve`:
   keep only the keys of `config.reasoning` that belong to the resolved route
   (`anthropic_effort` → Anthropic; every other key → OpenRouter); on OpenRouter an empty
   result becomes `DEFAULT_REASONING` (`{"effort": "minimal"}`); on Anthropic an empty
   result is `None`. Invariants this must keep, each pinned by a test:
   - an Opus run of a default family resolves `reasoning=None` — byte-identical
     fingerprints to the cached `judge_model=claude-opus-5-5` override runs (cache reuse);
   - introspection on Anthropic keeps `{"anthropic_effort": "default"}`;
   - a Gemini/OpenRouter override gets `{"effort": "minimal"}`, and knowledge_cutoff's
     OpenRouter override keeps `{"effort": "low"}` — exactly today's OpenRouter behaviour;
   - agentic / jailbreak (reasoning None) are unchanged on both routes.
   `pinned` stays `model == config.model`, so an Opus run of a default family is now pinned
   and a Gemini run is an override.
3. **Summarizer / aux models** keep falling back to the resolved judge, so token-bag
   summaries move to Opus with the judge (documented; no code change).
4. **Floors** (`evals/baselines/`). `prompt_only.floors()` already drops entries whose
   `judge_model` is not the family's judge — that gate is retained. `lucky_guessing.floors()`
   checked only `instrument`; it now also requires each variant's guesser `model` to be the
   family's judge (the model-free `uniform` variant is exempt), so a Gemini lucky floor is never
   drawn beside an Opus number. `wsbench report` draws floors only beside rows judged by the
   family's own judge (`pinned_instrument`), with a legend line: every frozen floor was measured
   by that judge, so a Gemini-override row (every public number before this change) gets none.
   - *Restore, no new calls:* the 2026-10-11 Opus entries from `37e307a` whose `instrument`
     still equals the family's current `prompt_version`: prompt-only for association,
     basic_readout, directed_modulation, multihop, multilingual, poetry, typo, buggy_code,
     conjunctive_association, moral_rationale, relational_multihop, user_modeling; lucky
     guessing for conjunctive_association, directed_modulation, moral_rationale,
     multi_concept_directed_modulation, relational_multihop, role_bound_association,
     user_modeling, brew_intermediates. The six multi-token lucky entries keep main's
     `mc-2026-09-16` stamps (they are MC diagnostics never drawn beside regex scores — the
     restamp `0f5c626` undid stays undone). Regex prompt-only entries are unchanged.
   - *Re-measure under Opus:* arithmetic_intermediates' frozen-cell prompt-only floor, from the
     current-site summaries in `gen-prompt-only-orderops` (every position at L56/L60, absolute
     positions remapped to the plan's from-end offsets), judged at layer 56 like the Gemini
     entry. A `cells=all` floor would be stamped `arith-free-batched-2026-09-23` and never drawn,
     so it is not frozen. brew, chain and role_bound have no current-site summaries on disk:
     their Gemini entries stay in the file, undrawn, and the README says so (brew and role_bound
     are `saturated` anyway; chain's 0.03 is the one real loss until summaries are generated on
     GPU, a follow-up).
   - Families that never had floors (wrong_bridge, wrong_bridge_true, multihop_mt_v2,
     directed_modulation_obscure, introspection, knowledge_cutoff, hallucination,
     jlens_concept_pr, agentic, jailbreak) are out of scope.
5. **ATI subset** needs no change: staleness is `instrument` + `bank_sha`
   (`text_inversion.py`), and the v2 entries are already stamped `claude-opus-5-5`.
6. **Docs.** README (Quickstart keys: `ANTHROPIC_API_KEY` or `ANTHROPIC_PROFILE` for the
   default; `OPENROUTER_API_KEY` only for OpenRouter overrides and the `capable` / ATI panel
   answerers; §Judges table + bullets; §Baselines), CLAUDE.md judge-layer paragraph,
   AGENTS.md, `evals/baselines/README.md` (lucky variants' judge, the Opus re-measure
   paragraph, which entries are drawn), `docs/summarizer.md`, and every family README's
   judge line. History (plans 0000–0022, plan0012_results) is not rewritten.
7. **Tests.** Sanctioned pre-existing test edits, and only these: (a) literal-Gemini assertions
   that test *the default* move to `DEFAULT_JUDGE`; (b) tests that exercise OpenRouter-only
   knobs (reasoning `minimal`, temperature) pass an explicit Gemini judge; (c) the autouse
   `_openrouter_shaped_fakes` shim in `tests/conftest.py` (added by `ddd88ac`, removed by
   `0f5c626`) comes back, with the current `_anthropic_once` keyword passthrough, so the
   OpenRouter-shaped fakes keep driving the family tests; (d) a test that relied on an earlier
   test having loaded the registry takes the existing `real_families` fixture (no assertion
   change); (e) `test_judge_config`'s "explicit reasoning wins on either route" case
   (`claude-sonnet-5` + `{"effort": "high"}`) now resolves `None` — the rule change of (2) itself;
   (f) the `test_results` `_res` fixture's literal judge becomes `DEFAULT_JUDGE` (a row "on the
   default judge", as it meant). New tests: every invariant in (2), the lucky model gate and
   the report / macro rules in (4) and (8).
8. **Side effects, stated.** (a) `pinned` flips: a cached run re-judged under the new default
   (cache hits, no spend) becomes pinned and so can be `complete` and enter the macro; old run
   dirs keep their stored flags until re-run. Because those flags are relative to the default at
   run time (a Gemini-era row stored `pinned=True`), `report` and `macro` decide from the row's
   recorded `judge_model` against the family's CURRENT judge (`results.on_family_judge`;
   regex families: the scorer or a summarizer equal to the family judge), not from the flag: a
   Gemini-era row gets no Opus floor and is excluded from the macro with reason `judge`. Floors
   also need the family's prompt version (`results.floor_applies`), so arithmetic's frozen-cell
   floor is never drawn beside its batched `cells=all` instrument. Users should stop passing
   `judge_model=claude-opus-5-5` — it now overrides the Sonnet pins of agentic and jailbreak.
   (b) `wsbench capable`'s grader is the repo judge, so it needs Anthropic credentials too, and a
   `claude-*` answerer's OpenRouter `reasoning_effort` is dropped (cache fingerprint and
   `capable.json` `reasoning` change; API behaviour does not).

## Not in scope
Unpinning the Sonnet families; re-judging cached arms; generating prompt-only summaries on
GPU; PR #109.

## Checks
`ruff check .`, `ruff format --check .`, `pytest -q`; `wsbench list` shows Opus for every
default family; a `wsbench report` over a cached Opus run draws the restored floors; a
cache-only re-run (`scripts/cache_only_run.py` or a dry run) of one cached Opus-override
family hits the cache 100% under the new default.

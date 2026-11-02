# 0058: remove medical_diagnosis{,_alt}; retire unverbalized_hint for now

Camila, 2026-10-31: "we should get rid of the medical diagnosis families", then "also get rid of
unverbalized hint for now".

Two different operations: the medical families are **removed** (gone, like ttt / plan 0017 and
multihop_mt / plan 0041); unverbalized_hint is **retired** (reversible: code and bank stay).

## A. Remove medical_diagnosis and medical_diagnosis_alt

- `registry.REMOVED_FAMILIES` gains both keys (reason: removed 2026-10-31, Camila, plan 0058). A
  stale `results.json` of theirs in an old run dir stays out of the macro with reason `removed`, and
  `markdown_table` / `report` drop its row (existing behaviour, retained unchanged).
- Delete `evals/medical_diagnosis{,_alt}/` (README + bank), `src/wsbench/evals/medical_diagnosis{,_alt}/`,
  `examples/readouts/medical_diagnosis.jsonl`, `tests/test_medical_diagnosis.py`.
- Consumers lose only the medical keys, other families unchanged: `readplan` (its plan branch),
  `digest.FAMILY_DEFAULTS` (the jailbreak-route entries; the other F3 families keep theirs),
  `capable.questions` (regate notes), `baselines.text_inversion.NOT_GATED` and the ATI file's
  `_not_gated` (the only places they appear in `evals/baselines/`; they were never in the lucky or
  prompt-only floor files), `basic.prompts` (`FAMILY_PROMPT_VERSIONS`, `DIGEST_TASK_NOTES`,
  `FAMILY_RULE_MEDICAL`, `FAMILY_RULES`).
- Mechanisms whose only user was medical stay, empty: `basic.prompts.FORBIDDEN_FAMILIES =
  frozenset()` (`FORBIDDEN_TEMPLATE` / `forbidden_line` kept) and `results.PAIRED_FAMILIES = {}` (the
  twin-bank line in `markdown_table` kept). Their tests exercise a stand-in family via monkeypatch.
- Shared bank stamp: `PROMPT_VERSION` stays `bank-2026-10-30b`. Deleting two `DIGEST_TASK_NOTES`
  lines changes `DIGEST_TASK_NOTES_TEXT`, a record only (each family is sent its own line), so no
  surviving family's prompt changes: re-pin the sha constant in `test_basic_prompts.py` only (the
  plan 0050 precedent).
- Docs: README family entries, Judges rows, Credits bullet and the removed-family lists; NOTICE
  section; CLAUDE.md (Deleted families, `not_in_macro`, `FAMILY_RULES`); `docs/summarizer.md`;
  the `DIGEST_TASK_NOTES` block in `evals/typo/README.md`. Plan 0027 and other plans stay as history.
- Macro count: unchanged. Both families were `not_in_macro` ("hillclimbing: not yet reviewed"), so
  no macro row loses a family; no family is now statically `not_in_macro`.

## B. Retire unverbalized_hint (for now)

Mirror of plan 0029's scope (out of `all`, macro, ATI file, README list), but reversible:

- New `registry.RETIRED_FAMILIES = {"unverbalized_hint": "retired (Camila 2026-10-31, for now)"}`.
  The family stays registered and runnable by name (`families=unverbalized_hint`), with its package,
  bank, tests, examples, NOTICE section and Credits bullet (the MMLU items are still shipped).
- `registry.drop_superseded` (what `all` means everywhere: `run`, `plan`, `capable`, `baseline`,
  `text-inversion`, ATI `gated_families`) also drops retired families; `include_superseded=True`
  still runs them.
- `results.macro` gains `retired=` (default `registry.RETIRED_FAMILIES`): reason `retired`.
  `wsbench list` marks the group `(retired)`.
- ATI: its `NOT_GATED` entry and the file's `_not_gated` line are deleted (gate() rewrites
  `_not_gated` from `NOT_GATED`, so both go). `text_inversion.subset_entry` raises `NotInScope`
  for a retired family (a by-name `anti_text_inversion=True` run skips it, as before, instead of
  failing with "run the gate first"), and `gate(families=...)` refuses one (review of #211).
- `viewer_app/index.py` hides retired families' old-run scores like removed ones.
- README: family entry and Judges row deleted; the `all` paragraph names it as retired; the
  model-specific list and Judges prose mark it retired.
- No edit under `src/wsbench/evals/unverbalized_hint/` (PR #200 edits its judge concurrently).
- Restore = delete the `RETIRED_FAMILIES` entry; re-add the README entry and Judges row (`git show`
  of this PR's parent), and the `NOT_GATED` line: "pair-level control family: the neutral twin is
  the counterfactual control and text-only floors are reported in the README".

## Sanctioned edits to pre-existing tests

- `test_bank_judge_v2.py`: forbidden-line tests use a monkeypatched stand-in family (typo with a
  surface `target`); `FAMILY_RULES == {"typo"}`, `FORBIDDEN_FAMILIES == frozenset()`.
- `test_basic_association.py`: the bank judge's README of record is now `evals/typo/README.md`.
- `test_audit_fixes_digest.py`: medical leaves the F3 list; the twin-bank test uses a monkeypatched pair.
- `test_token_note_prompts.py`: medical leaves the lists; the native targets test runs on typo.
- `test_basic_prompts.py`: sha re-pinned; medical stamp asserted absent.
- `test_readplan.py`: 32 -> 30 banks; `plan all` skips retired too, uvh plans by name.
- `test_readme.py`: entry / group / Judges checks iterate non-retired families; new retired check.
- `test_unverbalized_hint.py::test_summary_under_the_cli_default`: passes `retired={}` for the
  original assertion, and asserts the registry default now excludes it as `retired`.
- `test_summary_mode_compare.py`: the fake-LLM non-vacuousness bar 2/3 -> 3/5 (the two removed
  families always passed; 17 of 27 still do).

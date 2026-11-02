# 0015: `multihop_mt_v2` replaces `multihop_mt` as the default

Status: implemented. Owner: Camila. Date: 2026-10-23.

## Why

Plan 0013 froze `multihop_mt_v2`, the shortcut-gated successor of `multihop_mt` (the
2026-10-15 audit found 93 of v1's 100 items reachable while skipping a claimed bridge), and
prescribed that v1 leave the macro with exclusion reason "superseded" (0013, "Macro
double-counting"). Camila, 2026-10-23: v2 officially replaces v1 as the default thing to run.

## Decision

- `EvalSpec` gains `superseded_by: str = ""` (`wsbench.registry`); `multihop_mt` sets it to
  `multihop_mt_v2`. `registry.superseded()` returns the map and `registry.drop_superseded(names)`
  removes superseded families from a name list.
- **Macro:** `results.macro` excludes a superseded family, reason `"superseded"` (with the
  successor under `"by"`). It is excluded **always**, not only when the successor is in the same
  run: v2 is the default, so a v1 number alongside other families would be the stale instrument
  standing in for v2. `macro(results, superseded=...)` takes an explicit map; the default reads
  the registry lazily (the registry imports `results`). The other exclusion rules are unchanged:
  the metric, incomplete, no-value and ATI n<20 clauses are retained as they were.
- **Every `all` default skips superseded families:** `run all=True` (opt back in with
  `include_superseded=True`), and the `families=all` default of `plan`, `capable`, `baseline`
  and `text-inversion` (`text_inversion.gated_families`). An explicit name always runs
  (`families=multihop_mt`), and its result is still listed, outside the macro.
- **ATI:** v1 is not re-gated. A full `text_inversion.gate` (no `families=`) skips it and
  carries its existing entry in the frozen file over unchanged, so
  `anti_text_inversion=True families=multihop_mt` keeps working; the `families=` merge path of
  #79 (second answerer) already leaves every family it does not decide untouched. The frozen
  `anti_text_inversion.json` is not edited, and the not-gated, refusal and instrument rules are
  otherwise unchanged.
- `wsbench list` still lists v1, its group shown as `basic_mt (superseded by multihop_mt_v2)`.
- Not changed: the v1 bank (frozen), its golden files and tests, `readplan.families()` and the
  `BUILDERS` tables (v1 stays plannable and askable by name), the frozen floors.

## Checks

New tests only (no pre-existing assertion changed): macro exclusion with an explicit map and
with the registry default; `run all=True` skips a superseded stub, an explicit name and
`include_superseded=True` run it; `plan` and `capable` `all` skip `multihop_mt` while the name
still works; `gated_families` skips it and `gate` carries its entry over. CI: `ruff check .`,
`ruff format --check .`, `pytest -q`.

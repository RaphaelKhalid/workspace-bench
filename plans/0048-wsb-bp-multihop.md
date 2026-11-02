# Plan 0048 — workstream spec: `multihop` (single-token basic family), round 3

Code of record: `/root/wsb-bp-base` @ `cd6b0fa`. Feedback: `/workspace/root/wsb-bp/notes/feedback.md`,
section **multihop** (4 sentences + 1 worked example) plus GENERAL / D1-D10.
Audit evidence: `/workspace/root/wsb-audit-artifact/families/multihop.json`.

---

## 1. Current state

**Registration.** `src/wsbench/evals/multihop/__init__.py:6` = `bank_family("multihop", "Multihop")`. It runs
the shared basic bank judge (`src/wsbench/basic/family.py:31-53`). The bank path is hard-wired to
`evals/multihop/items.json` (`family.py:40`, `registry.py:61-62`). `prompt_version` is the shared
`bank-2026-10-10` (`basic/prompts.py:11`, `prompt_version_of` `:20-22`; multihop has no own stamp
in `FAMILY_PROMPT_VERSIONS` `:14-17`).

**Bank.** `evals/multihop/items.json` has 100 items with fields `name, prompt, target` (the surface
answer), `intermediates` (the bridge, which is the scored target), `readout`, `gate_variant`,
`eval_render="plain"`. It has no bridge type, no options and no token count. The header's `read`
field records the 2026-09-23 last-word decision.

**Read positions.** `readplan._plan` sends multihop to `_final_token_families(family, "plain")`
(`readplan.py:308-326`). Per item, `readout.offsets` gives `[-1]` (67 items) → `{"kind":"final_token"}`
or `[-2]` (33 items that end in a bare space) → `{"kind":"offset_from_end","k":2}`
(`readplan.py:239-247`). So it reads **one position per layer**. `final_token` resolves to the
*absolute* index `n-1` (`readplan.py:123-124`), while `offset_from_end` resolves to the negative `-2`
(`:125-127`). The cached readouts show this mixed convention (e.g. `wsb-ati-runs/readouts/jlens/multihop.jsonl`
has pos `-2` ×363 rows and pos 10..18 for the rest). There is no lite/full distinction.

**Layers.** `GRID = range(20, 61, 4)`, 11 layers (`readplan.py:16`). The judge accepts any subset
through `layers=` (`family.py:74-75`), which already satisfies D3 for multihop. One defect: summary
mode stamps `layers_judged: args.layers` (`family.py:232`), which is `None` when `layers=` is not
given. Native mode stamps the real list (`family.py:144`).

**Judge (native).** One call per (item, layer) covers every position at that layer (`basic/judge.py:77-156`).
It is a free-text "is a TARGET EXPRESSED" judge and the gold is shown (`targets: [...]`). **It is not MC and
has no cannot-tell option.** `SYSTEM` (`basic/prompts.py:25-59`) names tools: "for the J-lens the
samples are top-10 vocabulary tokens, for the oracle lens they are free-text generations" (`:27-28`),
which violates D5. The forbidden-answer line (`FORBIDDEN_TEMPLATE`, `:115-118`, applied via
`FORBIDDEN_FAMILIES` `:135` / `forbidden_line` `:168-173`) shows the judge the surface answer.
`KIND_NOTE_TOKENS` (`:93-99`) holds the "ranked first among candidates of its type" rule. The quote
gate is `quote_verified` → `span_in` on ONE sample (`basic/judge.py:53-59`, `family.py:36-45`). The
item passes on any layer (`basic/family.py:240-273`).

**Summary mode (default since plan 0024).** `_run_summary` (`basic/family.py:150-237`) sends all of an
item's cells (every layer × position × sample) to one `digest.collapse` call (`:175-183`), then one
bank-judge call per item under `SYSTEM_SUMMARY` / `USER_SUMMARY` (`basic/prompts.py:67-70`). The judge
gets the extractive digest with `[support]` markers. The task note `DIGEST_TASK_NOTES["multihop"]`
(`basic/prompts.py:76`) is passed (`family.py:182`) but is **used only under `summ_variant=task`**.
The default variant is `blind` (`digest.py:33-34`, `render_system` `:986-995`), so the summarizer
gets no task context today (violates D5). `SUMMARY_NOTE_TOKENS` (`digest.py:122-126`) requires "a
quote from such a line must be exactly one token" (conflicts with D6 for multi-token bridges such as
`New Zealand` or `Sherlock Holmes`).

**ATI.** `evals/baselines/anti_text_inversion.json["multihop"]` is a panel-v1 entry with
`n_ati: 1`, `ids: ["spaceneedle-border"]` (status `[failed, solved, failed, solved]`: Qwen and astra
failed). That one item is the "single question" Camila refers to.

**Floors.** `evals/baselines/prompt_only_summary.json["multihop"]` = 0.91 (stock Qwen3.6-27B readouts,
instrument `bank-2026-10-10+digest-v3-blind-extractive+sj-v7`). Run: `/workspace/root/wsb-summ5-out/po-summary/multihop`.
The audit (`floors.prompt_only`) notes it was measured at the OLD final-token read site. There is no
lucky-guessing entry because the family is not MC.

**Published results (audit `results_seen`).** O-lens s3d-rl600 native 1.00 and summary 1.00, J-lens
native 0.80, logit lens 0.54, rl-onchat-x4 0.99. The family is saturated for prose lenses.


**Round-2 conformance.** This spec uses only the names and signatures in `SHARED_API.md` (round 2)
and owns no shared machinery; no retired name is used as a live mechanism. Loading, lite selection, full-coverage checks, layer presence, `layers_judged`,
sampling, the quote verifier, the flat-list void, the cannot-tell builder, the bank-path rule,
the token cap and the prompt-only protocol all belong to infra (`infra.md` §2.0-2.13). The
blind bank MC judge belongs to basic_readout (`basic/mcjudge_basic.py`, basic_readout.md C3).
Multihop supplies only its data: plan rule, lite rule, bank v2 with options, task note, its
prompt strings and its tests. Binding decisions applied here: Q1/D7 (§2 D7), Q4 (C3, C4), Q9
(C3, §3), the ATI decision (C1), `reads=` naming, versioned banks, and spend (smoke `limit=3`
first, §5). Round-2 critique items applied: r1-3 (`number_flood` prose definition, C3/C4),
r1-4 (flat-list rule relative to the options shown, `EvalSpec.flat_types`, C3/C4), r1-7 (R4b
verdict audit, E7), r1-8 (required arms jlens + mlnla-rl2-2000, §3/E6), r1-11 (shared basic PV
bump, C3 stamp), r1-2 (multihop is non-relational, C3), r1-13 (`MC_FAMILIES`, C3).

**Round-3 conformance (SHARED_API r3, `_critique_r2.md`).** Applied: r2-4 (bulleted number
lists are floods; `number_flood` is called on whole-sample Lines only, C3 verdict, C4 route 3),
the r3 token-note rule (every multihop judge prompt, native AND summary, renders
`mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)`; no bare `mc.TOKEN_NOTE` /
`SUMMARY_NOTE_TOKENS`, C3), the r3 "add, never relax" rule (multihop's bare-mention ruling, C3),
r2-12 (`digest.BULLET_MARK` in `Line.text`; multihop is non-relational so it adds no
`statement_lines` check and reports no `n_unverified_bullet`, C3), r2-6 (R4c fix-and-rerun loop,
E7; prompt-only floor timed at R6 after R4c, D8), r2-5 (site manifest coverage map, §7),
r2-14b (audit strata, E7). Not applicable to multihop: r2-1/2/3/7/8/9/10/11/13 (agentic, HB,
MCDM, brmt, basic_readout, ATI table, DMO, introspection, lite-site procedure; multihop's lite
site is its fixed last word, not chosen by the procedure).

---

## 2. Change list

### C1. "do not include the single question in ati."
- Add `"multihop": "excluded from the ATI subset by design (Camila 2026-10-30): one surviving item (spaceneedle-border), not a subset"`
  to `NOT_GATED` in `src/wsbench/baselines/text_inversion.py:85-102`. `typo` uses the same
  mechanism at `:93`. This applies the campaign ATI decision ("families Camila removes from ATI
  are removed"; infra §2.13).
- Delete the `multihop` key from `evals/baselines/anti_text_inversion.json`, and add the same
  reason to its `_not_gated` block. `gate()` merges `NOT_GATED` into `_not_gated`
  (`text_inversion.py:1402-1427`). Re-running `wsbench text-inversion stage=gate` (no API calls;
  it re-folds cached verdicts) produces the file; hand edits must match it exactly.
- `gate()` must refuse multihop afterwards (`text_inversion.py:1359-1361` raises for NOT_GATED
  families).
- README.md ATI paragraph (`README.md:320-336`) and the per-family counts in
  `evals/baselines/README.md`: multihop leaves the list.
- **Tests:** new `tests/test_multihop.py::test_not_in_ati`:
  - `"multihop" in ti.NOT_GATED`;
  - `"multihop"` is absent from `json(anti_text_inversion.json)` except under `_not_gated`;
  - `ti.subset_entry("multihop")` raises `NotInScope`;
  - `wsbench run anti_text_inversion=True families=multihop` → skipped, exit 0.
- **Evidence:** E1.

### C2. "readouts at ALL positions for default, lite/fast mode can stay at final position only"
- **readplan (multihop's rows only).** Take multihop out of the `_final_token_families` tuple
  (`readplan.py:310-325`). A `_multihop()` branch emits per item:
  - `positions = {"kind": "all_from_end"}`: every token of the plain render, reported `-n..-1`.
    Full mode includes the trailing-space token and the old last-word site.
  - `lite_positions = {"kind": "offset_from_end", "k": K}` with `K = -readout.offsets[0]` (1 or 2),
    and `lite_layers = None` (the infra §2.6 table row). Lite therefore equals today's last-word
    read, and **the 2026-09-23 decision ("read the last word, not the space token") is retained
    in lite mode.**
  - `offset_from_end k=1` is used, **not** `final_token`, so both modes share one coordinate
    system. Lite ⊆ full, so one GPU read serves both modes.
- **Judge side: no multihop code.** The family's judge calls `reads.load(args, "multihop")` and
  nothing else. `reads.select` applies the lite rule, and resolves `-k` or `max-(k-1)` from the
  positions present in the file. Cached last-word files (absolute `n-1` for k=1 items, `-2` for
  k=2 items) therefore select correctly under `reads=lite` with no tokenizer and no `n_tokens`
  field. `reads.check_full` enforces full coverage (only when the file has a sidecar; a sidecar-less
  file is report-only, `extras.partial_ids_unenforced`). Multihop has no local reads option,
  position mapping, contiguity check or bank-path fallback: all of it is `reads.*` /
  `registry.bank_path`.
- **Registry.** The multihop `EvalSpec` sets `min_full_positions = 8` (the shortest prompt,
  `holiday-halloween-monthnum`, has 7 words, so ≥ 8 Qwen tokens) and
  `full_contiguous = True`. Under `reads=full`, a last-word-only file therefore exits 2
  ("looks like a lite file") when it carries a sidecar (`reads: lite`, or full with too few
  positions). Under `allow_missing` its items are `partial` and the run has `complete=False`.
  A sidecar-less cached file is report-only: it judges, and `extras.partial_ids_unenforced`
  lists the short items (SHARED_API "enforcement (r2)"). The prompt-only file passes through the `prompt_only:*` waiver
  (infra §2.6.6).
- **Stamp.** `reads.stamp`: `+reads-lite` for lite only; the full stamp is unchanged.
  `config.reads` is stamped by `mcjudge.base_config`.
- **Tests:**
  - `tests/test_readplan.py::test_multihop_full_and_lite`: every multihop row has
    `positions == {"kind":"all_from_end"}`, `lite_positions == {"kind":"offset_from_end","k":K}`
    with `K == -readout.offsets[0]`, and `lite_layers is None`.
  - The pre-existing assertion at `tests/test_readplan.py:68-69` (`{final_token, offset_from_end}`)
    is **sanctioned to change**, and only to the lite-rule assertion above.
  - `tests/test_multihop.py::test_lite_selects_last_word`: a fixture with positions -3..-1 for
    one item (k=2) and absolute 0..n-1 for another (k=1). Under `reads=lite` only the last-word
    cell of each is judged (through `reads.load`, fake judge).
  - `tests/test_multihop.py::test_full_on_lite_file_exits_2`: a last-word-only file with a
    sidecar (`conftest.write_sidecar(path, reads="full", sampling="tokens10", ...)`) under
    `reads=full` exits 2; under `allow_missing=True` it gives `complete=False` and
    `extras.partial_ids` holds all 100 ids. The same file without a sidecar judges and lists
    the 100 ids under `extras.partial_ids_unenforced` (shared
    `test_sidecarless_file_is_report_only`).
  - Shared tests this family is held to: `test_every_plan_row_has_lite_positions`,
    `test_every_lite_rule_is_cell_resolvable`, `test_lite_is_subset_of_full`,
    `test_no_family_calls_load_readouts_directly`.
- **Evidence:** E2.

### C3. "it should be multiple choice with distractors"
Multihop replaces its free-text EXPRESSED judge with the **shared blind bank MC judge**
`basic/mcjudge_basic.py` (owned by basic_readout.md C3). It opts in through
`MC_FAMILIES = {"basic_readout", "multihop"}` in `basic/family.py`. Multihop forks no prompt
skeleton, option renderer or verdict; the round-0 `basic/mc.py` is not created. The judge applies
in summary mode (default) and native mode.
- **Options (frozen in bank v2, `mc` block per item):**
  `{"bridge_type": str, "gold": str, "aliases": [str], "distractors": [4 × str]}`.
  - The 4 distractors + gold are shuffled with `mc.seeded_shuffle(f"multihop|{id}")`, then
    `mc.options_with_cannot(shuffled)` appends `mc.CANNOT` LAST, never shuffled in (D4). That
    gives 6 options, A-F.
  - `aliases` holds the existing `intermediates` forms (`["6","six"]`,
    `["Netherlands","Holland"]`) plus the digit/word pair for every number bridge and listed CJK
    forms (`六`, `日本`) for `mc.form_in`.
  - **Demonyms do NOT name a country (Q9).** `Chinese`, `Japanese`, `Argentine` etc. are removed
    from `aliases`, including the inherited `["China","Chinese"]`. A quote that names only the
    demonym or language adjective does not verify the gold.
  - **`spaceneedle-border` is re-keyed to Washington (Q9):** gold `Washington`, aliases
    `["Washington State", "WA", "华盛顿州"]`. `Seattle` is NOT an alias, because the prompt asks
    for the state. Distractors are other US states, excluding Washington's neighbours (Oregon,
    Idaho), for example California, Texas, Florida, New York.
- **Distractor rule (same type, never plausibly thought about).** This follows Camila's
  basic_readout guidance: "distractors here should be other random numbers (excluding 9 and 5,
  though, since those make sense that the model is thinking about)".
  - Draw 4 with a seeded RNG from a per-`bridge_type` pool.
  - The pool is the other items' bridges of that type. When fewer than 8 exist, it is topped up
    from a hand-written type list:
    - countries: about 25 distinct bridges in the bank, so no top-up;
    - top-up lists: months, elements, numbers 1-20, compass/relative directions, organs, animals,
      instruments, sports, shapes, famous people, US states, US cities, continents, mountains,
      rivers, planets, and everyday words for the `high/night/day/war` antonym items.
  - Hard exclusions, checked by code:
    - (a) the gold and every alias;
    - (b) the item's surface answer `target` and its forms. The answer is legitimately on the
      model's mind but is not a target, so it is never an option;
    - (c) any option whose string, or whose number in digits or words, appears in the prompt
      (e.g. `nhop-cube-element` cannot get 12, from "a dozen", or "magnesium");
    - (d) synonyms, translations or demonyms of the gold (hand check, listed in the script).
  - Output: `scripts/build_multihop_mc.py` (deterministic, no API) writes bank v2. Its type
    pools live in the script so reviewers can audit them.
- **Multihop's strings** (`evals/multihop/prompts.py`; the skeleton, TASK TYPE line and schema
  are `mcjudge_basic`'s):
  - `TASK_TYPE_MULTIHOP` = `EvalSpec.task_note` (D5, below).
  - `QUESTION_MULTIHOP` = "Which ONE of these does the readout name as the unstated entity?"
  - `RULES_MULTIHOP`, added to the shared rules:
    ```text
    - An option counts only if ONE readout sample names it: the word itself, an established
      alias, a spelling variant, or a translation into any language.
    - Naming something the option could be worked out from does NOT count: a symbol, a number
      that encodes it, a definition, a calculation, a related place, or a derived word such as
      a nationality or language adjective ("Japanese" does not name Japan). Do not use your
      own knowledge to connect clues to an option.
    - Choose "cannot tell from the readout" if the readout names none of the options, or names
      two or more of them with similar prominence.
    ```
    **Bare mentions (r3 "add, never relax").** Multihop's question is "which entity does the
    readout name", not "which option is stated as the answer", so basic_readout's C6
    answer-context requirement does NOT apply here: a bridge named on its own (an s3d bullet
    "- Nepal", or a token list whose only option token is "Nepal") is a pick, provided the
    shared token note singles it out (no other option on that line, not inside a declared
    `flat_types` run, and not voided by `number_flood`). This adds nothing the shared note
    voids. Listed under "Decisions taken" (§4).
    The flat-list rule is NOT restated here: it is the shared token note (SHARED_API
    "flat-list rule (r2)"), a judge decision relative to the **options shown**. A line holding
    ≥ 2 options, or a run of the family's `flat_types`, singles out none of them; an option
    alone on its line (no other option, and not inside a declared flat-type run) is singled out.
  - **`EvalSpec.flat_types = ("numbers", "months", "countries")`** for multihop. These are the
    bank's competitor-run bridge types named by Q4 ("numbers, colours, countries"; months as
    in KC). They fill the flat-type clause of `mc.token_note(SPEC.flat_types, multi_select=False)`, so
    the double-dice list "twelve six eight …" singles out none of the numbers even if only one
    of them were an option. Other bridge types (people, elements, organs, …) use only the
    "≥ 2 options on one line" clause, so "Kathmandu | Nepal | Everest" with only Nepal among
    the options picks Nepal.
  - The token-list rule is the shared `mc.token_note(SPEC.flat_types,
    multi_select=SPEC.multi_select)` (multihop: `multi_select` stays the default `False`),
    rendered in BOTH the native and the summary judge prompt; the bare `mc.TOKEN_NOTE` /
    `digest.SUMMARY_NOTE_TOKENS` (= `token_note()`, no flat types) is never sent by multihop
    (retired use, SHARED_API r3). No family copy. Multihop carries no rank-based singling-out sentence of its own, and the
    inherited `KIND_NOTE_TOKENS` clause leaves the multihop path with the free-text judge (Q4:
    a flat list of same-type candidates singles out none of them, whatever the rank).
  - The readout phrase is `mc.READOUT_PHRASE`. No tool names (D5): held by the shared
    `test_no_tool_names_in_prompts`.
  - **No targets line and no forbidden-answer line.** The judge is blind to the gold, and
    showing the answer ("Fe") would let it infer the bridge from world knowledge. Multihop
    therefore leaves `FORBIDDEN_FAMILIES` (`basic/prompts.py:135`).
- **Verdict** (the shared `mcjudge_basic` classify; multihop adds only alias data):
  - `correct` iff all of:
    - the letter is the gold option;
    - `digest.quote_ok(quote, lines)` holds, with `lines = col.evidence[id]` (summary) or
      `digest.native_lines(cells)` (native). Same-list tokens are joined by `" | "`, and a word
      split across adjacent positions is quoted as the plain word, so `New | Zealand` and a
      split `Kath`+`mandu` both verify;
    - `mc.form_in(quote, [gold, *aliases])`. Latin forms are word-bounded, so "16" does not
      match "6"; `六` matches only because it is a listed form;
    - for `bridge_type == "number"`, the pick fails (as cannot tell) when every line that
      verifies the quote satisfies `digest.number_flood(line)` (r2/r3 definition: a token list
      with ≥ 5 distinct numerals; a prose sample only with a list-shaped run of ≥ 5 numerals,
      separators `, ; | /`, "or", "and", space, and `digest.BULLET_MARK` (`⁞`) between bullets
      that hold only numerals + punctuation; operands/results of a stated operation never
      count and number words count only inside the run). So "A standard die has six faces, and
      double six is 12" is NOT a flood line and its "six" pick stands, while "twelve, six,
      eight, seven, eleven" is, and so is an s3d bulleted list "- 12\n- 6\n- 8\n- 7\n- 11"
      (rendered `12 ⁞ 6 ⁞ 8 ⁞ 7 ⁞ 11`).
    - **Whole samples only (r3).** The lines passed to `number_flood` are the sample Lines of
      `col.evidence[id]` / `digest.native_lines(cells)` (`Line.bullet is None`). Multihop never
      calls `digest.statement_lines`, so it can never hand `number_flood` a bullet Line (which
      raises `ValueError`).
  - **Unit of evidence.** The bridge is a single entity, not relational content, so the
    whole-generation licence applies (SHARED_API "sample licence (r2)"): a prose1 generation
    is one sample and the gold may be quoted from any of its bullets (the judge sees bullet
    boundaries as `⁞` in `Line.text`; `fold_quote` maps `⁞` to a space for `quote_ok`).
    Multihop adds no `digest.statement_lines` condition and reports no
    `extras.n_unverified_bullet` (non-relational family).
  - `cannot_tell`, `distractor` and `invalid` → fail. `None` (call failed) → undecided, never
    scored.
  - Item rows record `choice_kind`, `options`, `gold_idx`, `quote_ok`, `bridge_type` (the E7 audit stratum).
- **Item rule.** Summary: one call per item. Native: one call per (item, layer), any-layer pass.
  `extras` carries `mcjudge.layer_pick_columns(rows)` (`n_items_gold_any_layer`,
  `n_items_distractor_any_layer`, `n_items_distractor_majority`) beside the native number
  (critique 18).
- **Stamp:** `FAMILY_PROMPT_VERSIONS["multihop"] = "bank-mc-2026-10-31"`. The summary instrument
  is whatever `digest.prompt_version("bank-mc-2026-10-31", args, "multihop")` returns (cited from
  its output, never written as a literal), plus `+reads-lite` from `reads.stamp`. The shared
  basic stamp `basic/prompts.PROMPT_VERSION` moves `bank-2026-10-10` → `bank-2026-10-30` for the
  remaining `bank_family` users (medical `bank-2026-10-30-md`), owned by infra §2.8.1; multihop
  leaves that stamp because it renders its own MC prompt. The family PV must differ from the
  shared one (held by the shared `test_bank_pv_bumped_when_prompts_change`).
- **README:** "Scoring", "Judge prompts" (verbatim blocks; `tests/test_prompts_in_readme.py`
  enforces this) and the README.md family entry (`README.md:126-129`, three lines).
- **Tests (new unless noted):**
  - `tests/test_multihop.py::test_mc_options_frozen_and_clean`:
    - 4 distractors + gold, then `mc.CANNOT` last (built by `options_with_cannot`);
    - no distractor equals the gold, an alias or the surface answer;
    - no distractor string or number occurs in the prompt;
    - all options of an item share `bridge_type`;
    - no alias is a demonym (a listed demonym table: Chinese, Japanese, Argentine, …);
    - `spaceneedle-border` has gold `Washington` and `Seattle` is not an alias or option;
    - option order is pinned by `tests/golden/multihop_mc_options.json`.
  - `tests/test_multihop.py::test_mc_verdict`:
    - gold letter + verified quote containing "six" → pass;
    - gold letter + verified quote "twelve" → fail (quote lacks gold);
    - gold `Japan` + quote "Japanese" → fail (Q9);
    - `mc.CANNOT` → fail; `None` → undecided;
    - "16" quote for gold "6" → fail;
    - `New | Zealand` from one list → pass; `New` and `Zealand` from two layers → fail;
    - prose "A standard die has six faces, and double six is 12" + gold `6` → pass (not a
      flood line, r1-3); prose "the number could be twelve, six, eight, seven or eleven" → fail;
    - token list "Kathmandu | Nepal | Everest" with Nepal the only option on it → pass; a list
      holding two options ("Nepal | India") → fail (r1-4);
    - s3d bulleted sample "- 12\n- 6\n- 8\n- 7\n- 11" (one prose1 cell) + gold `6`, quote
      "6" → fail by `number_flood` (r2-4); s3d "- A die has six faces\n- Double six is 12" +
      gold `6` → pass (worked statement, not a flood);
    - bare bullet "- Nepal" among non-option concept bullets, gold `Nepal` → pass (bare-mention
      ruling, C3);
    - a spy on `digest.number_flood` asserts every Line it receives has `bullet is None`.
  - `tests/test_multihop.py::test_flat_types_rendered`: the registered spec has
    `flat_types == ("numbers", "months", "countries")` and `multi_select is False`, and in
    BOTH native and summary mode the token note in the sent system prompt equals
    `mc.token_note(spec.flat_types, multi_select=spec.multi_select)` (which differs from the
    bare `mc.TOKEN_NOTE`; no family copy of the rule). Shared: `test_token_note_rendered_from_spec`,
    `test_bulleted_number_list_is_flood`, `test_number_flood_rejects_statement_line`,
    `test_digest_line_shows_bullet_boundaries`.
  - `tests/test_multihop.py::test_mc_prompt_is_blind`: for a fake run, the sent system/user
    messages contain no gold, alias or `target` string.
  - `tests/test_multihop.py::test_registered_spec_and_readme` (pre-existing,
    `tests/test_multihop.py:22-28`) is **sanctioned to change**: it asserts the family stamp and
    the multihop prompt blocks in the README, instead of the shared `PROMPT_VERSION`/`SYSTEM`.
  - Pre-existing `tests/test_bank_judge_v2.py:26-47` and `:65-90` (forbidden line is multihop's,
    `FORBIDDEN_FAMILIES == {"multihop", *md}`, `own["multihop"] == "FORBIDDEN_TEMPLATE"`) and
    `tests/test_medical_diagnosis.py:187-189` (multihop stamp == `bank-2026-10-10`) are
    **sanctioned to change**, and only by removing multihop from those assertions. Their
    medical_diagnosis halves must stay byte-identical. The reviewer checks `git diff -- tests/`
    for exactly these edits.
  - Shared: `test_every_mc_judge_ends_with_cannot` (multihop is in `lucky_guessing.BUILDERS`).
- **Evidence:** E3, E5.

### C4. Worked example: `targets: ["6","six"] … [position 11] equal twelve six eight seven eleven nine sixteen twenty five` "Should NOT pass because there are so many similar numbers"
- Three independent routes now reach cannot tell / fail on this list, none of them depending on
  rank:
  - (1) the shared token note with multihop's `flat_types` ("numbers" declared): a run of
    numbers singles out none of the options in it, whatever their order. The rank-based text
    Camila quoted is gone from every prompt (`test_no_rank1_exception_text`, infra);
  - (2) the options-shown clause: the list also holds distractor numbers (drawn from 1-20
    minus {6, 12}, e.g. 8, 7, 11, 9, 16), so it holds ≥ 2 options → cannot tell;
  - (3) the deterministic `digest.number_flood` void: as a token list it holds 9 distinct
    numerals (≥ 5), so a "six" pick supported only by it fails in code even if the judge
    picks it. The same holds for the prose reader's most common shape of this list, an s3d
    bulleted number list (`⁞`-joined number-only bullets, r2-4), evaluated on the whole sample.
  - The number distractors for `double-dice-faces` come from 1-20 minus {6, 12}.
- **Chance floor.** A random guesser that never says cannot tell passes a 6-option question 1/5
  of the time per call. Add a `_multihop()` builder to `src/wsbench/baselines/lucky_guessing.py`
  (`BUILDERS`, `:209-259`; `DESCRIPTIONS["multihop"] = "the unstated intermediate entity behind
  a one-step factual question"`) that reads the bank through `registry.bank_path` (infra §2.12.3
  removes the `:213` literal). Summary mode is one call per item, so its floor is per call. The
  native any-layer floor is reported beside `layer_pick_columns`.
- **Tests:**
  - `tests/test_multihop.py::test_double_dice_regression`: a scripted fake judge on the exact
    token list. It asserts that the sent prompt holds the frozen options, ends with `mc.CANNOT`,
    renders the line as one `" | "` list with no scores and no gold, and carries no rank-1
    sentence. A scripted "six" pick quoting that line is rejected by `number_flood`, and so is a
    pick of rank-1 "twelve" on a variant item whose gold is 12.
  - Judge behaviour itself is proven by the evidence re-judge (E4), because tests make no API
    calls.
- **Evidence:** E4.

### General items that land in this family (implemented by their owners; multihop complies)
- **D1** (summarizer gets ALL readouts): `_run_summary` passes every cell `reads.load` returns
  (`family.py:168-183`) to `digest.collapse`. With C2 that is every position × every layer.
  Overflow is hierarchical above the global `DEFAULT_TOKEN_CAP` (920k); multihop sets no
  family token cap (about 26k tokens per O-lens item, so one call).
  - **Test:** `test_multihop.py::test_summary_gets_all_positions`: the fake digest's bundle has
    one `[L.. pos ..]` header per (layer, pos) of the fixture.
- **D3** (arbitrary layers): handled by infra (`reads.load` layer check, `base_config` stamps
  `layers_judged`). The round-0 local fix at `family.py:232` is superseded by
  `base_config`. Held by the shared `test_layers_arbitrary` and
  `test_layers_variant_is_complete`.
- **D5** (task context, no tool names): the task variant is the global default
  (`digest.DEFAULT_VARIANT = "task"`); multihop sets no `summ_variant`.
  `EvalSpec.task_note` for multihop = "the model reads a factual statement whose completion
  depends on one intermediate entity (a place, person, number, date or thing) that the text never
  names; the readouts may mention that entity only once". It gives the type, not the answer, and
  replaces `DIGEST_TASK_NOTES["multihop"]`. Held by the shared
  `test_every_summary_family_has_task_note_without_gold`; plus
  `test_multihop.py::test_digest_gets_task_note` (the fake digest sees `DIGEST_TASK_LINE` with
  that note).
- **D6** (token combining): the shared Q4 rule and `digest.quote_ok` (C3). No multihop text.
- **D7** (sampling, Q1): no multihop code. The sampling kind comes from the producer's sidecar
  (`reads.load` → `readouts.normalize`), never from bullet shape. s3d-rl600 is `prose1`: its one
  multi-bullet generation is ONE readout sample. A single-bullet O-lens (`*-x4`) is `bullet4`:
  4 separate samples per activation. Token lenses are `tokens10`. The README states it.
- **D8** (prompt-only): protocol `po-opus-v1` (infra §2.11). One Opus 5.5 readout per item, at
  the last full-read site (pos -1), layer 44, judged by `wsbench run … readouts_root=` with no
  `layers=` and no `reads=`, so it gets the same digest, task note, MC options, cannot-tell,
  `flat_types`, quote and `number_flood` gates. The floor is multihop's own headline metric
  from that run (MC pass rate), with the family CI and n = judged − refused; > 20% refused →
  `not_measurable`. It is matched by `summary_floor_applies` on `reads.strip_reads(pv)`, so one
  floor serves full, lite and every layer config. It is measured at gpu R6, after R4c closes;
  if an R4c fix bumps multihop's PV, the floor waits for R6 to re-run (SHARED_API "timing
  (r3)"), and `scripts/audit_run.py` asserts `strip_reads(pv)` equals the floor `instrument`.
  Multihop adds nothing.

---

## 3. Data needs

- **New bank file** `evals/multihop/items_v2.json`. `items.json` (sha `e29cb3da…`) stays as it
  is. The multihop `EvalSpec` sets `bank=Path("evals/multihop/items_v2.json")`, which
  `registry.bank_path` honours (infra §2.12). `readplan._bank`,
  `capable/questions.py` and `lucky_guessing` follow `bank_path`.
  - The bank holds the same 100 prompts, ids, `target`, `intermediates` and gate fields, plus
    the per-item `mc` block (C3). No `n_tokens` field (C2 needs none).
  - Its header gains `version: 2`, `supersedes: items.json`, a new `read` text (full = all
    positions; lite = last word, retaining the 2026-09-23 decision) and `mc_seed`.
- **No new items, so no Qwen gating.** The prompts and surface answers are unchanged (the
  `spaceneedle-border` re-key changes the scored bridge, not the gated answer `Canada`), so the
  behavioural gate (≥ 8/10 at T=0.7) still holds. Distractors are judge-side data and need no
  GPU (gpu.md §3.2 agrees).
- **ATI fingerprint:** the v2 bank gets a new `bank_sha` by construction, which does not matter
  because multihop leaves ATI (C1).
- **Readouts to regenerate (GPU, Modal, run phase; gpu.md §3.3 row "multihop* (all pos)"):**
  - the three required campaign arms (gpu §3.3, r1-8), each with a declared sidecar, at
    `reads=full`: s3d-rl600 (`prose1`), jlens (`tokens10`) and mlnla-rl2-2000 (`prose1`);
    `all_from_end` over the plain render, 100 items × all `GRID` layers (20..60 step 4);
  - every other published arm (logit lens, rl-onchat-x4, …) is **cached v1 readouts, judge
    test only**: judged as `reads=lite` from the last-word files, no new production;
  - size: prompts are about 10-35 Qwen tokens (the 67 final-token items average 14.0), so
    about 1.6k positions × 11 layers ≈ 17-18k cells per arm;
  - lite needs no extra GPU work: lite ⊆ full, and the cached last-word files
    (`wsb-ati-runs/readouts/{s3d,jlens,mlnla2k}/multihop.jsonl`,
    `wsbench-pub/outputs/readouts/*/multihop.jsonl`) also judge directly as `reads=lite`
    (they have no sidecar, so `sampling_source=default`: evidence only, not campaign results).
- **Prompt-only (D8):** produced by `wsbench baseline kind=prompt_only_opus` (infra §2.11), frozen
  into `evals/baselines/prompt_only_summary.json` under the new instrument. The 0.91 Qwen entry
  is archived by infra and goes stale through the instrument mismatch.
- **Lucky-guessing floor:** freeze `lucky_guessing.json["multihop"]` (blind/described/uniform)
  in the run phase (API calls).

---

## 4. Answers

**Camila's multihop section asks no explicit question.** Her example ("Should NOT pass because
there are so many similar numbers") is an assertion. Here is how it scores today:
- **J-lens native, all 11 layers, judged FAIL.** In
  `/workspace/root/ext/wsb-runs/macro/jlens/multihop/results.json` the row `double-dice-faces` has
  `pass: false`, with every layer `expressed: false`. The audit marked L56 "ambiguous"
  (`families/multihop.json` case 1) because the rank-1 rule fought the forbidden-answer rule.
  Under Q4 the rank-1 rule is gone and `number_flood` voids the line in code, so it must fail.
- **O-lens s3d passes legitimately.** In native mode it passes at L28/L32/L52/L56/L60 with
  explicit statements ("A standard die has six faces.", L32). In summary mode it passes with the
  quote "The standard die has six sides."
  (`/workspace/root/wsb-summ-out/d3/d3b-s3d-all-summary-v2/multihop/results.json`). These state
  the bridge as a fact, not inside a number run, so they should still pass under MC unless a
  distractor is stated as often.
- **One risky sample.** At L56 s3d says "8, which is double the number of sides on a cube … 6 (or
  it's half …)". If 8 is drawn as a distractor, that sample alone gives cannot tell. That is the
  intended strictness.
- **J-lens summary mode: no cached run exists** for multihop (the d3a/summ4 J-lens dirs have no
  `multihop/`), so its summary behaviour on this item is unmeasured today. E4 measures it.

**Why is the one ATI item there?** `spaceneedle-border` entered because Qwen (and astra)
"failed": the gold bridge was `Seattle`, but the prompt asks for the US **state**. A reader that
says "Washington" without "Seattle" failed the scorer. This is a gold-keying artefact, not hidden
computation. Q9 re-keys it to Washington (§3) and C1 drops multihop from ATI.

**Decisions applied (from `_fable_decisions.md`; the site lists them as overridable):**
spaceneedle → Washington; demonyms do not name a country (Q9); no rank-1 exception (Q4); s3d =
one sample per activation (Q1). Family decision (multihop.md C3, overridable): a bare mention of
the bridge (alone on its line, not in a same-type run) counts, because the task is "which entity
is the model thinking of", not "which answer does it state"; basic_readout's answer-context rule
is not applied here.

**General question, "How are prompt only baselines judged?", for this family.** Today the
prompt-only readout is stock Qwen3.6-27B, asked what a model would be thinking. It is judged by
**this same family judge**: same SYSTEM, same targets and forbidden line, summary mode
(`baselines/prompt_only.py:1-3`; frozen entry `prompt_only_summary.json["multihop"]`, instrument
`…+sj-v7`, `layers_judged [20]`). Under `po-opus-v1` the reader becomes Opus 5.5 and goes
through the identical digest and MC judge. It should: the MC judge is blind, so the only
difference from a lens arm is where the readout text came from. Expect it near 1.0 (Opus
pass@3 = 1.0 in the ATI panel). The family stays text-invertible, which is why it is out of ATI
and why the site must show the score next to the floor.

---

## 5. Evidence plan (website artefacts)

Spend order (decision): every API step runs a `limit=3` smoke first, then the full run.

| # | Item | Before | After (proof) |
|---|------|--------|---------------|
| E1 | C1 not in ATI | `anti_text_inversion.json` multihop `n_ati 1, ids [spaceneedle-border]` | the file diff shows the entry removed and a `_not_gated.multihop` reason; `wsbench run anti_text_inversion=True families=multihop` logs "skipped: not gated" |
| E2 | C2 full/lite | `wsbench plan family=multihop` rows: 1 position each (`final_token`/`offset_from_end`) | plan rows show `all_from_end` + `lite_positions offset_from_end k=K`; a table of positions per item; `config.reads` for both runs (lite stamp `+reads-lite`, full unchanged); a full run on a last-word file exits 2, and under `allow_missing` shows `complete=false` with 100 `partial_ids` |
| E3 | C3 MC | judge user message shows `targets: ["iron"]` and the forbidden line (audit `judge_user_message_rendered_verbatim`) | the rendered MC message for `atomic-26-symbol`: options A-E + "cannot tell from the readout" last, no gold, no "Fe", no tool name; `multihop_mc_options.json` golden published |
| E4 | C4 double-dice | J-lens native L56 `expressed:false` (old rubric, contested) | re-judge `wsb-ati-runs/readouts/jlens/multihop.jsonl` as `reads=lite`, native and summary, on the new instrument: `double-dice-faces` L56 pick = CANNOT or voided by `number_flood` (FAIL); `rhyme-tree-squared` L60 ("nine three …") FAIL |
| E5 | strictness spot-checks + Q9 | `b3-mh-fuji-currency` J-lens L44 PASS on "Japanese" (audit too_lenient); `atomic-79-symbol` s3d L32 PASS while asserting "Platinum"; `spaceneedle-border` keyed `Seattle` | the same cells re-judged: fuji → FAIL (demonym, Q9); atomic-79 → CANNOT if platinum is an option, else documented; `spaceneedle-border` judged against Washington; the `colosseum-currency` s3d L36 PASS stays PASS (an agree case must not regress) |
| E6 | full-read headline | 1.00 s3d / 0.80 J-lens / 0.54 logit (last word, free-text judge) | after GPU regeneration: summary + MC at full reads for the three required arms (s3d-rl600, jlens, mlnla-rl2-2000), lite beside each, with the Opus prompt-only floor and the lucky floor; s3d-rl600 all-11-layer and each single layer (`layers=each`); native rows carry `layer_pick_columns`. Logit lens and rl-onchat-x4 appear only as "cached v1 readouts, judge test only" (lite) |
| E7 | audit | 40 cells audited, 1 too_lenient, 4 ambiguous | multihop's stratum of the shared gpu R4b audit (`scripts/audit_verdicts.py sample --per-family 30 --strata multihop=bridge_type` → `table`, ≥ 30 stratified verdicts: pass/fail × prose/tokens over s3d-rl600, jlens, mlnla-rl2-2000, ≥ 10 `number` bridges so the flood void is audited), with `n_too_lenient` / `n_too_strict` / `n_ambiguous` and verbatim cases; if `flagged` lists multihop, the gpu R4c loop applies (fix PR → R4 for multihop → fresh R4b, ≤ 2 rounds; leftovers go to the site "New errors found"); no family-local audit script |
| E8 | prompt-only | 0.91 (Qwen, old site, free-text judge) | Opus `po-opus-v1` through summary + MC, floor = multihop's MC headline (n = judged − refused, CI); table "score − floor" |

Cached inputs for E4/E5 (no GPU): `/workspace/root/wsb-ati-runs/readouts/{jlens,s3d,mlnla2k}/multihop.jsonl`
(11 layers, last word), `/workspace/root/wsbench-pub/outputs/readouts/s3d-rl600/multihop.jsonl`.

---

## 6. Risks / conflicts (shared files)

- **R1: the shared bank MC judge** is basic_readout's `basic/mcjudge_basic.py`. Multihop adds
  only `"multihop"` to `MC_FAMILIES`, its bank `mc` blocks and its strings. If basic_readout's
  module renders its own longer CANNOT text through `cannot=`, multihop still uses the default
  `mc.CANNOT`, so the module must take `cannot` per family. basic_readout's `quote_close` (the
  tolerant gate) is basic_readout's addition and is **not** applied to multihop; multihop's
  quote check is `digest.quote_ok` + `mc.form_in` (+ `number_flood` for numbers).
- **R2-R4 (round 0) resolved by infra:** versioned banks (`EvalSpec.bank`, §2.12), the lite field
  and `reads=` key (§2.6), and the digest note / stamp bump (§2.7-2.8, done once campaign-wide).
- **R5: score shift from full reads.** Reading every position credits bridges formed as direct
  lookups at the entity token ("Space Needle" → Washington, "Kathmandu" → Nepal), not only at the
  end, so full-read scores will rise for prose lenses. More positions also mean more same-type
  mentions, so more cannot tell. Lite is reported beside full so both are visible.
- **R6 (round 0) resolved by Q9.** The re-key and the demonym rule are decided. The aliases are
  pruned of demonyms in bank v2 (C3).
- **R7: edits to pre-existing tests** (red-flag list for review). Only these are sanctioned:
  - `tests/test_readplan.py:68-69`;
  - `tests/test_multihop.py:22-28`;
  - `tests/test_bank_judge_v2.py:26-47, 65-90` (remove multihop only);
  - `tests/test_medical_diagnosis.py:187-189` (drop multihop from the loop; the medical
    stamp literal in the same assertion moves to `bank-2026-10-30-md` under infra §2.8.1,
    which is infra's sanctioned edit, not multihop's);
  - `tests/test_token_note_prompts.py` (`BASIC_TARGET_JUDGES` drops multihop, and
    `test_native_basic_judge_receives_spec_note_and_bag_lines` moves from multihop to
    `medical_diagnosis`; forced by multihop becoming an options judge, whose note is covered by
    `test_multihop.py::test_flat_types_rendered`). Amended after review of PR #150.
  Any other assertion change is a defect.
- **R7a: quote context (review of PR #150).** `quote_ok` accepts a folded substring of a prose
  sample, so the form / value gate runs on the quote **in its line's context**, on top of the
  check on the quote alone (add, never relax): the prose occurrence is widened to word
  boundaries (not across CJK) and must hold a word-bounded form, or, for a number bridge, a
  numeral overlapping it whose value is the gold (六 of 十六 is 16); a CJK form followed by
  人 / 语 / 語 / 话 / 話 / 文 never counts, in prose or in tokens.
- **R8: saturation.** Even with MC, prose lenses and the Opus prompt-only floor will both sit
  near 1.0. The family stays useful mainly for token lenses, and the site must show score − floor
  (the audit's open concern).
- **Other shared files touched (data/registration only):**
  - `src/wsbench/baselines/text_inversion.py` (`NOT_GATED`), `evals/baselines/anti_text_inversion.json`,
    `evals/baselines/lucky_guessing.json`, `src/wsbench/baselines/lucky_guessing.py` (`_multihop`
    builder);
  - `src/wsbench/readplan.py` (`_multihop` rows), `src/wsbench/basic/family.py`
    (`MC_FAMILIES`), `src/wsbench/basic/prompts.py` (`FORBIDDEN_FAMILIES`,
    `FAMILY_PROMPT_VERSIONS`, remove `DIGEST_TASK_NOTES["multihop"]`),
    `src/wsbench/evals/multihop/{__init__,prompts}.py`;
  - `README.md` (`:126-129`, `:320-336`, judges table `:400`), `evals/baselines/README.md`;
  - `tests/golden/multihop_mc_options.json` (new). `tests/golden/capable_questions.json` must
    stay unchanged, because the prompts are unchanged.

---

## 7. Coverage map (feeds `site/manifest.json`, gpu G11)

One manifest row per (sentence, change); `sentence_id = multihop:<line in notes/feedback.md>`.

| sentence_id | sentence | change | tests | evidence | status at merge |
|---|---|---|---|---|---|
| multihop:50 | "do not include the single question in ati." | C1 | `test_not_in_ati` | E1 | done |
| multihop:51 | "readouts at ALL positions for default, lite/fast mode can stay at final position only" | C2 | `test_multihop_full_and_lite`, `test_lite_selects_last_word`, `test_full_on_lite_file_exits_2`, `test_summary_gets_all_positions` | E2, E6 | pending (E6 after R2) |
| multihop:52 | "it should be multiple choice with distractors" | C3 | `test_mc_options_frozen_and_clean`, `test_mc_verdict`, `test_mc_prompt_is_blind`, `test_flat_types_rendered` | E3, E5, E7 | done (E7 measured at R4b) |
| multihop:53 | worked example `targets: ["6","six"] … twelve six eight …` | C4 | `test_double_dice_regression`, `test_mc_verdict` (bulleted flood case) | E4 | measured |
| multihop:54 | "Should NOT pass because there are so many similar numbers" | C4 | `test_double_dice_regression` | E4, E7 | measured |


---

## 8. Implementation notes (PR of record; deviations from the spec above)

- **`basic/mcjudge_basic.py` is created here** (basic_readout's PR was not open yet). Minimal
  shared interface: `MCStrings(question, rules, cannot)` in the family's `prompts.MC`,
  `options_of`, `verdict`, `run`, schema `basic_mc_verdict {choice, quote}`.
  `MC_FAMILIES = {"multihop"}`; basic_readout adds itself, `BR_CANNOT`, `stated` and
  `quote_close` in its own PR.
- **`DIGEST_TASK_NOTES["multihop"]` is kept** in the shared table: removing it changes the pinned
  shared-prompt sha (`tests/test_basic_prompts.py`) and would force a shared PV bump for nine
  other families. Multihop's own note reaches the summarizer and judge through
  `bank_family(task_note=...)` (new kwarg, plus `targets_judge=`).
- **Added (stricter, "add, never relax"):** a gold pick supported only by ranked token lists
  that also hold another shown option is voided in code (`multi_option`), mirroring the shared
  token note; `mc.form_in` runs on the quote with `" | "` joins normalised to spaces.
- **Bank data choices:** China and the Vatican are golds only, never distractors (Qwen token
  lists carry 中国 tokens as native-language noise); states bordering Canada (incl. New York)
  are excluded for spaceneedle-border; platinum is pinned as a distractor of atomic-79-symbol
  (the documented s3d confusion); number distractors also exclude 2 for "double / half /
  square" prompts and 12 for the "dozen" chains; `WA` / `LA` are not aliases (they collide with
  common short words), `南极` (the prompt's "South Pole") and `fiddle` (the prompt's "fiddlers")
  are not aliases.
- `RULES` states the shared Q4 split-word exception explicitly ("tokens of adjacent positions at
  one layer may spell one word"), as in the late basic_readout fix.
- Adapted banks (`adapted/*/multihop.json`) carry no `mc` blocks: the MC judge exits 2 on them
  with a pointer to the builder.
- `min_full_positions = 8` checked against the Qwen3.6-27B tokenizer: prompts are 9-41 tokens
  (1528 positions per arm per layer).

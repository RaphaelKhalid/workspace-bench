# Plan 0050: wrong_bridge — every-token read, blind 6-way MC with the true bridge, wrong_bridge_true removed

Status: implemented (PR camila/wsb-bp-wrong_bridge). Campaign: WorkspaceBench fix campaign,
workstream `wrong_bridge` (Camila's 2026-10-30 feedback, sections "wrong bridge" and "wrong bridge
true"), on top of plan 0032 (infra). The workstream spec follows verbatim (§1-§6); the
implementation notes and every deviation from it are in §7.

# Workstream spec: `wrong_bridge` (+ removal of `wrong_bridge_true`)

Code of record: `/root/wsb-bp-base` @ `cd6b0fa` (origin/main). Round 1 revision 2026-10-30 (SHARED_API.md names, _fable_decisions.md Q1/Q4/Q10, _critique.md items 1-4, 7, 8, 10, 11, 16, 18, 19, 26, 32-34). Round 2 revision 2026-10-30 (SHARED_API.md round-2 names; _critique_r1.md items 2, 4, 7, 8, 9, 11, 13). Round 3 revision 2026-10-30 (SHARED_API.md round-3 names: `mc.token_note(..., multi_select=)`, `digest.BULLET_MARK`, R4c, G11 manifest, G13 `ati_regate_table.py`, `results.MACRO_METRICS`; _critique_r2.md names no wrong_bridge item, the shared items 5, 6, 9, 12 land here as §2 G9-G10, W4, G6, G7, §5). Every `file:line` below is into that
tree unless prefixed. Feedback: `/workspace/root/wsb-bp/notes/feedback.md`, sections "wrong bridge"
and "wrong bridge true" (+ GENERAL). Prior audit: `/workspace/root/wsb-audit-artifact/families/wrong_bridge.json`.

---------------------------------------------------------------------------------------------------

## 1. Current state

### 1.1 Registration and code path
- `wrong_bridge` is a three-line shared-bank family:
  `src/wsbench/evals/wrong_bridge/__init__.py:6` → `bank_family("wrong_bridge", "Wrong-bridge multihop")`.
  Its `prompts.py:3` only re-exports the shared basic prompts (`wsbench.basic.prompts`).
- `wrong_bridge_true` is the same construction with target = the true bridge:
  `src/wsbench/evals/wrong_bridge_true/__init__.py:6`, bank `evals/wrong_bridge_true/items.json`
  (same 100 ids/prompts/read sites, `intermediates` = B).
- Shared judge: `src/wsbench/basic/family.py:31-53` (`bank_family`, `prompt_version_of(name)` →
  `bank-2026-10-10`, `basic/prompts.py:11`), `run_family` `basic/family.py:67-147`.

### 1.2 Bank
- `evals/wrong_bridge/items.json`: header keys `family, gate, eval_render_note, read, targets,
  source, items, retired_panel_gate, refill_panel_gate`; 100 scored items + 7 `retired_panel_gate`.
  Per item: `prompt` (plain text, ends in ` year` / ` of`), `target` (A′, the model's wrong
  answer), `correct_answer` (A), `intermediates` = [B′] (scored), `intermediates_aliases`,
  `true_intermediates` = [B], `true_intermediates_aliases`, `template` (17 templates),
  `hop2`, `wikidata {S,B,B_prime}`, `evidence`, `adjudication`,
  `readout: {"kind": "last_word_token", "offsets": [-1]}`.
- Prompts are 9–21 words (mean 13.95), so ~12–25 Qwen tokens.

### 1.3 Read sites and layers
- Positions: `readplan._plan` lists the family at `src/wsbench/readplan.py:323-326` →
  `_final_token_families(family, "plain")` `readplan.py:239-266`; the bank's `offsets [-1]` maps to
  `{"kind": "final_token"}` (`readplan.py:243-247`), i.e. ONE position (the final ` year`/` of`
  token, absolute index n-1; the cached readouts carry absolute `pos` 11–22, e.g.
  `/workspace/root/wsb-ati-runs/readouts/s3d/wrong_bridge.jsonl`).
- Layers: `GRID = list(range(20, 61, 4))` (`readplan.py:16`), 11 layers. The judge already takes
  any layer list: `layers = args.layers if args.layers is not None else rep.layers`
  (`basic/family.py:74-75`); missing (item, layer) cells are fatal unless `allow_missing`
  (`basic/family.py:77-79`). No two-layer hardcode.

### 1.4 Judge (free text, not MC)
- Native: one call per (item, layer) over that layer's positions, `basic/judge.py:77-156`;
  system `SYSTEM` `basic/prompts.py:25-59` (it names tools: "for the J-lens the samples are
  top-10 vocabulary tokens, for the oracle lens they are free-text generations", `:27-28`);
  user `USER`/`BLOCK` `:100-101`; targets = `[B′]` only (`basic/family.py:56-57,71`); no family
  rule (`FAMILY_RULES` `:129-134`) and no forbidden line (`FORBIDDEN_FAMILIES` `:135`);
  schema `{expressed, target, quote}` `:153-161`; quote gate = verbatim span of ONE sample
  (`basic/judge.py:53-70`). Item = pass on ANY layer (`basic/family.py:240-273`).
- The only list rule is the generic "many interchangeable candidates … expresses none of them
  unless it singles one out" (`basic/prompts.py:51-53`); nothing requires the name to be the
  bridge rather than a comparator/hedge.
- MC: none. No "cannot tell". The judge is already blind to the prompt (it sees only targets +
  readouts).

### 1.5 Summary mode (the default since plan 0024)
- `basic/family.py:80-94` → `_run_summary` `:150-237`: every cell of the item at every judged layer
  → `digest.collapse(...)` (`:175-183`, `src/wsbench/digest.py:1008`) → ONE bank-judge call on the
  digest (`SYSTEM_SUMMARY` = `SYSTEM` with `SUMMARY_INPUT`, `basic/prompts.py:62-70`), quote gated
  against evidence samples (`digest.gate_texts`, `digest.py:948`). Stamp
  `bank-2026-10-10+digest-v3-<variant>-<render>+sj-v7`.
- Task note: `DIGEST_TASK_NOTES["wrong_bridge"]` `basic/prompts.py:80-81` ("the model reads a
  factual prompt whose answer needs one silent intermediate step") — but it is only sent under
  `summ_variant=task`; the default variant is `blind` (`digest.py:34`), so today the digest gets
  NO task context. The digest system prompt says "activation lens" (`digest.py:41-44`).
- With only the final position read, "all readouts across positions" = 11 cells per item.

### 1.6 Floors, ATI, results
- No prompt-only floor (absent from `evals/baselines/prompt_only.json` and
  `prompt_only_summary.json`; `plans/0023-opus-default-judge.md:64` "Families that never had
  floors (wrong_bridge, wrong_bridge_true, …)"). No lucky floor (not MC). Chance label "no
  analytic floor (free text)" (`basic/family.py:28`).
- ATI: `evals/baselines/anti_text_inversion.json["wrong_bridge"]`: gate `panel-v1`, instrument
  `bank-2026-10-10`, `layers_judged [44]`, `n_ati 100/100`, pass@3 qwen 0.62 / opus 0.00 / astra
  0.00 / argon 0.01, `bank_sha a509a4c9…`. `wrong_bridge` is `CRAFTED`
  (`src/wsbench/baselines/text_inversion.py:66-68`): losing its gate is a stop-and-report.
  `bank_fingerprint` hashes the ATI plan rows (positions rule included) + bank items
  (`text_inversion.py:1013-1044`) — any change to the positions rule or the items re-stales it.
  `wrong_bridge_true` has its own entry at `anti_text_inversion.json:72809` (58/100).
- Cached results (all predate the 2026-10-28 refill: 93 current + 7 retired items): O-lens s3d
  native 0.50 / summary 0.48 (`/workspace/root/wsb-summ-out/d3/d3c-s3d-all-{native,summary-v2}`),
  J-lens 0.053 (ATI-76), ML-NLA 0.408 native / 0.368 summary (ATI-76).

### 1.7 Audit cases Camila is reacting to (`families/wrong_bridge.json` → `audit.cases`)
| id · layer · reader | readout (verbatim excerpt) | judge | audit verdict |
|---|---|---|---|
| `novel_author-Q2779707-birth_year` · L32 · s3d | "…year in which **Philip Pullman** was born… of birth as the famous sci-fi author **Isaac Asimov**" | PASS "Isaac Asimov" | comparator |
| `album_performer-Q167554-birth_year` · L52 · s3d | "(Hint: Michael Jackson was born in the year [MASK].) What year was Madonna born? … What year was Selena Gomez born?" | PASS "Madonna" | list of celebrities |
| `composition_composer-Q689519-birth_year` · L48 · s3d | "1649, whereas Mozart was born in the year 1756. \| What year was Johann Sebastian Bach born … Shakespeare … Vivaldi" | PASS "Johann Sebastian Bach" | list |
| `game_developer-Q1436430-hq_city` · L36 · ML-NLA | "likely Nintendo or Square Enix, Japanese context" | PASS "likely Nintendo" | **too_lenient** (hedge) |
| `film_director-Q384243-death_city` · L32 · ML-NLA | "film/TV trivia involving Luis Buñuel-style or Mexican director names" | PASS "Luis Buñuel" | **too_lenient** (style ref.) |
| `person_father-Q311646-birth_city` · L44 · J-lens | tokens "Emperor Caesar Rome emperor King Napoleon…" | PASS "Caesar" | ambiguous |
| controls: `composition_composer-Q1746043-birth_city` L56 J-lens ("贝多芬" first among composers); `game_developer-Q5236657-hq_city` L56 s3d ("Nintendo is headquartered in Kyoto") | | PASS | agree |

Systematic issue (audit): ~9/31 (≈30%) of positive cells are comparator/list/hedge mentions.

---------------------------------------------------------------------------------------------------
## 2. Change list

Round 1 (2026-10-30). Shared names come from `SHARED_API.md` only; product decisions from
`_fable_decisions.md` (Q1, Q4, Q10 and the lite / bank / ATI / prompt-only decisions apply
here). wrong_bridge re-implements none of: loading, lite selection, full-read completeness,
sampling normalisation, layer checks, quote verification, script-safe alias matching, the
cannot-tell builder, digest overflow, prompt-only reading. It owns only its option data, its
judge prompt, its name/echo rules, its `flat_types` declaration and its extras.

Round 2 (2026-10-30): SHARED_API round-2 names (`mc.token_note`, `EvalSpec.flat_types`, sample
licence, sidecar-only enforcement, G12 audit, G13/R8 re-gate, G14 arms, basic PV bump). The
leniency audit is the shared G12 table (no family protocol); per-arm rows use the required
`jlens` / `mlnla-rl2-2000` production.

Round 3 (2026-10-30): token notes render `mc.token_note(SPEC.flat_types,
multi_select=SPEC.multi_select)` (wrong_bridge: `multi_select=False`); bullet boundaries come from
`digest.BULLET_MARK` (shown `- a ⁞ b ⁞ c` to summarizer and judge, native and summary); the
audit loop is gpu R4c; floors (R6) and ATI (R8) are measured on the post-R4c instrument; the site
coverage map and "Decisions taken" list are in §5.

Numbering: W1–W5 = one per Camila sentence in "wrong bridge" / "wrong bridge true"; G1–G10 = the
campaign decisions as they land on this family.

### W1. "read ALL tokens not just the final one by default (lite/fast can just be last token though)"
- **Bank v2** (`evals/wrong_bridge/items_v2.json`, header `version: 2`, see §3): every item's
  `readout` becomes `{"kind": "all_positions", "lite": {"kind": "final_token"}}`; header `read`
  = "every token of the plain render (reads=full); the final token (reads=lite)". The `lite` key
  is only the source readplan copies into the plan row; the judge never reads the bank for it
  (infra §2.6.1).
- **readplan** (`src/wsbench/readplan.py`, `_final_token_families` `:239-266`): a bank
  `readout.kind == "all_positions"` maps to `positions = {"kind": "all"}` (every token, absolute
  indices 0..n-1, already a `resolve` kind at `readplan.py:132`) and
  `ReadSpec.lite_positions = {"kind": "final_token"}` (from the bank `lite` key),
  `ReadSpec.lite_layers = None`. Layers stay `readplan.GRID`. Every other family that goes
  through `_final_token_families` is unaffected (their rows get infra's default
  `lite_positions = {"kind": "final_token"}`). The plan change moves `reads.plan_sha("wrong_bridge")`
  (it hashes `positions`, not `lite_*`), so a producer sidecar for this family must carry the new
  `plan_sha`; `reads.load` exits 2 on a sidecar whose `plan_sha` differs, or on a sidecar
  `reads: lite` under `reads=full` (shared full-read guards).
- **Judge**: the family loads with `reads.load(args, "wrong_bridge")` and nothing else. Under
  `reads=lite`, `reads.select` keeps the `max` position per (item, layer); under `reads=full`,
  `reads.check_full` enforces completeness. No family-local filter, max-pos logic or contiguity
  check exists in wrong_bridge.
- **Registry**: `EvalSpec(..., min_full_positions=9, full_contiguous=True)`. 9 = the shortest
  bank prompt in words (9; every word is ≥ 1 Qwen token; the cached final-token files show the
  shortest current render ends at absolute pos 11, i.e. 12 tokens). For a file WITH a sidecar
  (every campaign file), a full read with one position per cell exits 2 ("looks like a lite
  file"), and a gap is `partial` only under `allow_missing` (`extras.partial_ids`,
  `complete=False`). A sidecar-less file (the cached v1 readouts) is report-only:
  `extras.partial_ids_unenforced`, `config.reads_checked = "no_sidecar"`, never a campaign
  result (shared rule, `test_sidecarless_file_is_report_only`).
- **Stamp**: `config.reads` via `mcjudge.base_config`; prompt version =
  `reads.stamp(digest.prompt_version(PROMPT_VERSION, args, "wrong_bridge"), reads.mode(args))`
  (adds `+reads-lite` for lite only; full unchanged).
- **CLI**: `reads=full|lite` (default full); `opts=reads=lite` alias (infra §2.6.7).
- Tests (`tests/test_wrong_bridge.py`):
  `test_plan_reads_every_token_and_lite_reads_final` (every v2 plan row: `positions ==
  {"kind": "all"}`, `lite_positions == {"kind": "final_token"}`, `lite_layers is None`;
  `readplan.resolve` over a 17-token list → 17 positions full / `[16]` lite);
  `test_full_plan_rows_have_min_positions` (every v2 row resolves to ≥ `min_full_positions`
  tokens under the Qwen tokenizer; CPU, skipped without the tokenizer files, same marker as
  gpu.md's `test_readplan_reads.py`);
  `test_judge_uses_reads_load_only` (monkeypatch `reads.load` to a fake; the family never calls
  `load_readouts`; complements the shared `test_no_family_calls_load_readouts_directly`);
  `test_full_summary_gets_every_position_and_layer` (3 layers × 14 positions toy file with a
  `tests/conftest.py::write_sidecar(path, reads="full", sampling="prose1", plan_sha=reads.plan_sha("wrong_bridge"))`
  sidecar, fake `digest.collapse` receives all 42 cells and `expect_all` equals them);
  `test_lite_summary_gets_final_position_only` (same file, `reads=lite` → 3 cells, all at max
  pos; prompt version ends `+reads-lite`); `test_one_position_full_file_with_sidecar_exits`
  (one position per cell + sidecar, `reads=full` → exit 2; the same file without a sidecar →
  judged, `reads_checked == "no_sidecar"`, ids in `partial_ids_unenforced`). Lite selection and full completeness themselves are
  proved by infra's `tests/test_reads.py` and the shared `test_every_plan_row_has_lite_positions`
  / `test_lite_is_subset_of_full`.

### W2. "make this multiple choice, which should include the correct bridge too and other distractor items from the same category"
- wrong_bridge leaves `bank_family` and gets its own `src/wsbench/evals/wrong_bridge/judge.py` +
  `prompts.py` (README group stays "Basic (single token)", `GROUP="basic"`; repo `CLAUDE.md`
  "Eleven" → "Twelve families keep their own judge.py"). Decision: it does NOT opt into
  basic_readout's `basic/mcjudge_basic.py`, because its scoring (contrast option,
  `true_bridge_rate`, name and echo gates) is family-specific and that module's tolerant
  `quote_close` gate is the wrong gate for names (critique r1 item 13: basic_readout.md's
  `MC_FAMILIES` is `{"basic_readout", "multihop"}`; wrong_bridge is not in it). It is built only
  from shared parts: `reads.load`, `digest.collapse`, `digest.quote_ok`, `digest.native_lines`,
  `digest.fold_quote`, `mc.seeded_shuffle`, `mc.options_with_cannot`, `mc.classify`,
  `mc.form_in`, `mc.token_note`, `mc.READOUT_PHRASE`, `mcjudge.run_calls`, `mcjudge.base_config`,
  `mcjudge.layer_pick_columns`, `family.render_bag` (scores off).
- **Flat-list type (critique r1 item 4, Q4).** `EvalSpec.flat_types = FLAT_TYPES =
  ("names of people, bands or companies",)`. Under the shared flat-list rule a token line
  singles out none of the options when it holds ≥ 2 options OR is a run of the family's
  `flat_types`; declaring the candidates' kind as the competitor run is what makes the Madonna
  case ("Michael Jackson … Madonna … Selena Gomez": one option among non-option celebrities)
  and the "Caesar among emperors" J-lens case cannot tell, as Camila asked ("the other
  celebrities can be the distractor items", "fixes the judge too lenient cases"). The rule
  text comes only from `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` (=
  `mc.token_note(FLAT_TYPES, multi_select=False)`; native token note AND the summary-mode token
  note, which infra renders from the same function); wrong_bridge writes no flat-list
  sentence of its own for token lines. Prose lists are covered by the SYSTEM "Several
  entities" rule below (a family judge rule, about entities of the candidates' kind, not about
  token lists).
- **Options per item** (frozen in the bank v2 `mc` block, never built at judge time):
  gold = `intermediates[0]` (B′); **contrast = `true_intermediates[0]` (B, "the correct
  bridge")**; 4 same-category distractors (W3). Content order =
  `mc.seeded_shuffle([gold, contrast, *distractors], f"{WB_MC_SEED}:{name}:order")`; the shown
  list = `mc.options_with_cannot(order, cannot=CANNOT)` (CANNOT appended LAST, never shuffled
  in; 7 numbered lines).
- **Name forms per option** (frozen in `mc.forms[option]`, Q10 + critique 19): the option's
  full name and its bank aliases (`intermediates_aliases` / `true_intermediates_aliases` of the
  item that owns that name), plus
  - **surname / short form** (Q10): the last word of the primary name (and of each multi-word
    alias), added ONLY if it is ≥ 3 characters, not in the exclusion list (particles `van, von,
    de, da, del, der, the, of, le, la, el, al`; titles and regnal words `king, queen, emperor,
    pope, saint, st, sir, lord, i, ii, iii, iv`), and no other option of THAT item has it as a
    word of any of its forms. "Beethoven" is a form of Ludwig van Beethoven; "Matilda" is a form
    of neither Matilda of Scotland nor Matilda of Flanders; "Karl" is never a form (first name);
    "Abdul Hamid" fits both Abdul Hamid I and II and is a form of neither.
  - **native-script forms** for every language in `banks.native_langs(header)` other than
    English (Qwen: `zh`): the Wikidata `zh` / `zh-hans` / `zh-hant` labels of the option's QID
    (`wikidata.B` / `wikidata.B_prime` of the item that owns that name), fetched once at
    bank-build time and frozen; a name with no such label has no CJK form.
  Header `contract.native_langs = ["en", "zh"]`.
- **Scoring** (`mc.classify(choice, gold_pos, n_shown, contrast_pos=…)`, `src/wsbench/mc.py:27`):
  - `gold` AND `digest.quote_ok(quote, lines)` (lines = `col.evidence[name]` in summary mode,
    `digest.native_lines(cells)` of that layer natively; the ONE verifier, which also strips
    markdown and score annotations) AND `mc.form_in(digest.fold_quote(quote),
    mc.forms[gold])` AND NOT `echo_of_prompt(quote, prompt)` → pass;
  - gold with a failing gate → fail, counted `gold_uncredited`;
  - `contrast` → fail, counted `picked_true_bridge`;
  - `distractor` / `cannot_tell` → fail; `invalid` → `validate` re-queues once
    (`mcjudge.run_calls validate=`), then unjudged (never scored).
  - `mc.form_in` replaces round 0's family `name_in_quote`: a quote without Latin letters is
    credited only if it contains a listed native-script form of the picked option (no "accepted
    on the judge's word" shortcut). A fact-only quote ("born in Bonn in 1770") can never pass.
  - `echo_of_prompt` (family-owned, the one extra gate): the quote folded by
    `digest.fold_quote` with whitespace/punctuation removed is a substring of the prompt folded
    the same way → not credited. (In `album_label-Q21480481-founded_year` the prompt says
    "Bluenote Café" and B′ is "Blue Note"; it is the only item where a B′ form overlaps the
    prompt, checked over all 100 items; the builder re-checks surname forms too.)
- **Native mode** (`opts=aggregate=native`, and the ATI gate): one MC call per (item, layer)
  over every selected position of that layer; item passes if any layer is a credited gold pick
  (the any-layer rule, unchanged for ATI); `picked_true_bridge` if any layer picks the contrast
  and none credits gold. `extras` adds `mcjudge.layer_pick_columns(rows)`
  (`n_items_gold_any_layer`, `n_items_distractor_any_layer`, `n_items_distractor_majority`;
  the contrast counts as a distractor there), printed beside every native / ATI number
  (critique 18). **Summary mode** (default): one digest per item over all selected cells → one
  MC call; that verdict is the item verdict.
- **Extras**: `pick_counts {gold, contrast, distractor, cannot_tell, invalid, gold_uncredited}`,
  `true_bridge_rate` (contrast picks / decided items) — the paired statistic that replaces what
  `wrong_bridge_true` carried (W5).
- Chance label: "MC, 6 candidates + cannot tell: uniform-guess floor 1/6; lucky-guessing floor
  in `evals/baselines/lucky_guessing.json`".
- New family `PROMPT_VERSION = "wb-mc-2026-10-30"` (not the shared `bank-2026-10-10`, so no
  other basic family's stamp moves). Every cited stamp is the output of
  `digest.prompt_version(PROMPT_VERSION, args, "wrong_bridge")` (then `reads.stamp`); no digest
  stamp literal is written in code, README or tests.
- Prompts (in `src/wsbench/evals/wrong_bridge/prompts.py`, verbatim in the README "Judge prompts"
  fence, `tests/test_prompts_in_readme.py` enforces equality). `{READOUT_PHRASE}` is
  `mc.READOUT_PHRASE`; `{token_note}` is `mc.token_note(SPEC.flat_types,
  multi_select=SPEC.multi_select)`; `{summary_note}` is the shared `digest.SUMMARY_NOTE*` with its
  token part rendered by the same call (infra §2.7.2, §2.8). Native `{samples}` are the
  `- {Line.text}` lines of `digest.native_lines(cells)` at that position (the shared rendering,
  so a multi-bullet s3d sample shows as `- a ⁞ b ⁞ c` exactly as in the digest's extractive
  lines, infra §2.7.10); the family never re-flattens samples itself:

```text
SYSTEM =
You judge {READOUT_PHRASE}, taken while the model read a one-sentence factual question that you
cannot see. The question asks for a fact (a year or a city) about a person, group or company that
the question never names: to answer, the model first had to work out silently WHICH person, group
or company the question is about (for example, who made a given work). You get a numbered list of
candidates for that hidden entity, and the readout.

Choose the ONE candidate the readout identifies as the entity the question is about, or the
"cannot tell" line.
- Identifies: the readout names the candidate (full name, an established alias or nickname, the
  name in another language or script, or a surname that no other candidate in the list shares)
  AND treats it as the entity in question: the maker, performer, founder, parent, advisor or
  namesake being asked about, or the entity whose dates, places or works the readout goes on to
  state.
- Facts never identify an entity: a year, a city, a work, a nationality or a description from
  which you could work out who is meant does NOT count, even if you know which candidate it fits.
  Only a name counts. Do not use your own knowledge to connect facts to a candidate.
- A name that appears only as a comparison ("born in the same year as X"), a style or genre
  reference ("X-style"), one example in a list, or a reference point for something else does NOT
  identify.
- In a free-text sample written as "- " bullets (bullets are separated by ⁞), judge the
  candidate's role from the bullet that names it: another bullet never turns a comparison or
  list entry into the entity in question.
- Several entities: if the readout names two or more people, groups or companies of the
  candidates' kind as the entity in question, whether or not they are in the list, and does not
  clearly favour one of them (stated far more often, or stated as the answer while the others are
  rejected), choose "cannot tell". A hedge ("X or Y", "likely X or Y") favours neither. A
  candidate that is one entry of a list of several names of the candidates' kind (listed above
  or not) is one example in that list, whatever its order, and does not identify.
- A partial name that fits two or more candidates (a shared first name, surname or title)
  identifies none of them.
- If no candidate is named, choose "cannot tell".
- Give a SHORT quote copied character for character from ONE readout sample that contains the
  candidate's name; leave it empty when you choose "cannot tell".
Return JSON: {"choice": <the number of your line>, "quote": "<verbatim>"}.

CANNOT = cannot tell: the readout does not single out one of these as the entity in question

USER (native) =
CANDIDATES:
{options}

{kind_note}

READOUT:
{blocks}

BLOCK = [position {pos}]
{samples}

KIND_NOTE_PROSE = Each line of the readout is one free-text sample; ⁞ separates its "- " bullets.
KIND_NOTE_TOKENS = {token_note}

USER_SUMMARY =
CANDIDATES:
{options}

{summary_note}

READOUT:
{summary}

TASK_NOTE (EvalSpec.task_note) = the model reads a one-sentence factual question whose answer
needs a silent first step, working out which person, group or company the question is about, and
it never writes that entity
```
  Round 0's "a candidate's name token ranked above every other name of its kind counts as
  named" clause is deleted (Q4: no rank-1 exception); token lists follow `mc.token_note(FLAT_TYPES, multi_select=False)`
  only (tokens of one list combine; adjacent positions of one layer combine only to spell one
  name, e.g. " Beeth" + "oven"; nothing relational across samples, positions, layers or bullets
  of one generation; a line holding ≥ 2 options or a run of names of people, bands or companies
  singles out none of them, whatever their rank). Blocks carry
  only the position index, never the read-site token text. Schema
  `schema_block("wb_pick", {"choice": {"type": "integer"}, "quote": {"type": "string"}}, …)`.
  The judge never sees the prompt, A, A′, the template name or the hop-2 relation (blind).
- Tests: `test_options_frozen_and_golden` (every v2 item: 6 unique content options, then CANNOT
  last via `options_with_cannot`; gold = `intermediates[0]`, contrast = `true_intermediates[0]`;
  distractors from the item's `mc.category`; no distractor form folds to a gold/contrast form;
  no option occurs in the prompt; order equals `tests/golden/wrong_bridge_options.json`);
  `test_forms_surname_only_when_unique` (Q10: "Beethoven" ∈ forms[Ludwig van Beethoven];
  "Matilda" ∉ forms of either Matilda option; "Karl" / "Abdul Hamid" ∉ any form; no surname form
  of one option is a word of another option's forms, over every v2 item);
  `test_user_message_is_blind` (rendered native + summary messages contain no prompt substring
  ≥ 3 words and no A/A′; tool names are covered by the shared `test_no_tool_names_in_prompts`);
  `test_contrast_pick_fails_and_counts` (fake `run_calls` returns the contrast number → `pass`
  False, `true_bridge_rate` 1.0); `test_cannot_tell_fails`; `test_gold_quote_must_verify`
  (quote absent from evidence → fail via `quote_ok`); `test_gold_quote_must_carry_a_form`
  ("born in Bonn in 1770" → fail; "贝多芬" → pass; a CJK quote that is not a listed form → fail);
  `test_surname_only_credit` ("**Beethoven**" in a sample, gold Beethoven → pass after markdown
  fold; "Matilda" with both Matildas shown → fail); `test_prompt_echo_is_not_credit` (Bluenote
  item, quote "Bluenote" → fail; "Blue Note Records" → pass); `test_invalid_choice_requeued`;
  `test_native_extras_have_layer_pick_columns`; `test_token_list_rank1_not_credited` (a toy
  token list "Napoleon | Caesar | Hitler | Alexander | Stalin" with gold Caesar at rank 2 and a
  scripted pick: the rendered native and summary prompts contain
  `mc.token_note(FLAT_TYPES, multi_select=False)` verbatim (the family case of the shared
  `test_token_note_rendered_from_spec`), including its "names of people, bands or companies" run clause, and no rank-1
  clause — golden render); `test_flat_types_declared` (`spec_of("wrong_bridge").flat_types ==
  FLAT_TYPES`, `.multi_select is False`, and the rendered token note differs from `mc.TOKEN_NOTE`,
  i.e. the clause is not omitted); `test_bullet_role_rule_rendered` (golden render: SYSTEM carries the "bullet that
  names it" rule in native and summary mode); `test_native_samples_show_bullet_mark` (a toy
  3-bullet s3d cell "- Isaac Asimov was born in 1920\n- Philip Pullman\n- fantasy" renders in the
  native USER block as `- Isaac Asimov was born in 1920 ⁞ Philip Pullman ⁞ fantasy`, identical to
  the `digest.native_lines` text, so `quote_ok` verifies a quote copied from it).

### W3. "e.g. in the madonna case album_performer-Q167554-birth_year · 52, the other celebrities can be the distractor items"
- Categories are per item (`mc.category` in bank v2): template default map, with per-item
  overrides where the template mixes kinds:
  - `musician` (individual people): album_performer, song_performer, song_lyricist items whose
    B′ and B are people, + `person_mother-Q192402-birth_year` (Judy Collins / Kate McGarrigle);
  - `band` (groups): the same templates where B′ is a group (the musician pool's groups: AC/DC,
    Metallica, Pantera, Sepultura, Sonic Youth, The Flaming Lips, The Rolling Stones, Wings).
    Distractors match the gold's kind, so a solo singer never gets bands as distractors; if the
    `band` pool is under 8 after exclusions the builder falls back to `musician ∪ band` and
    records it in `mc_build.fallbacks`;
  - `composer`: composition_composer, + `namesake-Q178416-death_year` (Rubinstein /
    Rimsky-Korsakov);
  - `writer`: novel_author; `filmmaker`: film_director, character_creator (Hanna / Tashlin);
  - `painter`: painting_creator; `scholar`: doctoral_advisor;
  - `historical_leader`: person_father, org_founder, `person_mother-Q102005-death_year`
    (Matildas), `namesake-Q989622-death_year` (Marx / Liebknecht);
  - `company`: game_developer, album_label, product_manufacturer, tv_network.
- Pool per category = B′ ∪ B of every OTHER item in the category (scored + `retired_panel_gate`),
  minus any name sharing a form (incl. surname forms) with the item's own B′/B, minus any name
  occurring in the item's prompt; draw 4 with
  `mc.seeded_shuffle(sorted(pool), f"{WB_MC_SEED}:{name}:draw")[:4]`. Measured pool sizes
  (unique names, round 0): writer 32, musician (people + bands) 28, painter 23, company 22,
  historical_leader ~21, filmmaker ~23, composer ~14, scholar 10; the builder asserts every item
  keeps ≥ 8 candidates after exclusions. For the Madonna item the options become Madonna,
  Britney Spears (B) and four solo musicians from the pool (e.g. Beyoncé, Adele, Jay-Z, Kendrick
  Lamar) — "the other celebrities".
- The celebrities the s3d readout itself names (Michael Jackson, Selena Gomez; neither is in the
  bank's musician pool) are NOT added as per-item options: choosing distractors from one lens's
  readout would bias the instrument toward or against that lens. They are handled by the
  "names two or more … whether or not they are in the list" rule, which makes that readout
  "cannot tell" (E3).
- Builder: `scripts/wrong_bridge_mc_options.py` (deterministic; the only network step is the
  one-time Wikidata `zh*` label fetch for the QIDs, cached to
  `evals/wrong_bridge/zh_labels_v2.json` and frozen; no LLM API): reads `items.json`, writes
  `items_v2.json` (header + items + the untouched `retired_panel_gate` and `refill_panel_gate`)
  and `tests/golden/wrong_bridge_options.json`. `scripts/` is held by the lint ratchet.
- Tests: `test_distractors_same_category` (each distractor is a B/B′ of another item whose
  `mc.category` equals this item's, or a recorded fallback); `test_madonna_options` (pins the
  exact list for `album_performer-Q167554-birth_year`; no band among its distractors).

### W4. "make sure this fixes the "judge too lenient" cases"
- The W2 rules map one-to-one onto the audit's lenient/ambiguous classes: hedge ("likely X or
  Y") → cannot tell; style/comparison reference → not identification; list of same-kind names
  (listed or not, any rank) → cannot tell; partial name shared by two candidates → none (also
  mechanical: it is not in `mc.forms`); facts-only → never (mechanical: `mc.form_in`).
- Offline proof: `test_audit_cases_render` loads the 7 verbatim audit readouts (fixture
  `tests/fixtures/wrong_bridge_audit_cases.jsonl`, copied from `families/wrong_bridge.json`)
  and asserts the rendered native user message contains the full readout and the frozen options
  (no readout text dropped). The hedge and style cases ("likely Nintendo", "Luis Buñuel-style")
  carry a real name, so no mechanical gate can reject them; their proof is the live verdict
  (Evidence E3): the five lenient/ambiguous cases must come back `cannot_tell`.
- Mechanical support for the list cases: `FLAT_TYPES` (W2) puts the "run of names of people,
  bands or companies" clause into every token note, so the Caesar-among-leaders J-lens list and
  any celebrity token list single out none of the options.
- Audit after the change (Camila GENERAL "audit … neither too strict nor too lenient"): NO
  family protocol. wrong_bridge is audited by the shared verdict-level leniency audit (gpu
  G12 / runbook R4b): `scripts/audit_verdicts.py sample` draws ≥ 30 seeded verdicts stratified
  pass/fail × prose (s3d-rl600, `mlnla-rl2-2000`) / token (`jlens`) from the all-layer full
  config, a fresh-context auditor labels each `ok | too_lenient | too_strict | ambiguous`, and
  `audit_verdicts.py table` gives `n_too_lenient` / `n_too_strict` / `n_ambiguous` with every
  non-ok case verbatim. The auditor is given Camila's "wrong bridge" sentences and the W2 pass
  rule. wrong_bridge declares no `--strata` kind (it has no twins or controls), so the sample is
  the default pass/fail × prose/token stratification. `n_too_lenient + n_too_strict ≥ 3` flags
  the family and opens a fix item **before R6 / R8 and the site build** (the family PR is
  already merged at R1), run through gpu **R4c**: fix PR with a new family PV (`wb-mc-…` bump; a
  new bank version and `plan_sha` only if options or read sites change) → R2/R2b if `plan_sha`
  moved → R4 for wrong_bridge (all 12 s3d configs, `jlens` and `mlnla-rl2-2000` all-layer full +
  lite) → R4b with a fresh seed → at most 2 rounds; still flagged after round 2 → listed on the
  site under "New errors found" with its verdicts. Never a silent re-tune. The judge is unpinned
  (Opus 5.5), so there is no Opus-judge column.

### W5. "wrong bridge true - this should not be in the benchmark, remove it"
- Mechanism = deletion (the `brew_intermediates` precedent), not `superseded_by`:
  - `src/wsbench/registry.py:32-36` `REMOVED_FAMILIES["wrong_bridge_true"] = "removed 2026-10-30
    (Camila): not part of the benchmark; wrong_bridge reports the true-bridge pick as
    true_bridge_rate"`.
  - Delete `src/wsbench/evals/wrong_bridge_true/` and `evals/wrong_bridge_true/` (README + bank).
  - `readplan.py:324` drop it from the tuple; `basic/prompts.py:82-83` drop its
    `DIGEST_TASK_NOTES` line **and** the `wrong_bridge` line (wrong_bridge now carries
    `EvalSpec.task_note`) — this changes `DIGEST_TASK_NOTES_TEXT`, so the copy in every basic
    README must be updated (association, basic_readout, multihop, multilingual, poetry, typo,
    medical_diagnosis, medical_diagnosis_alt; `test_prompts_in_readme` enforces it). Coordinate:
    infra §2.8 also edits these READMEs; whichever lands second rebases.
  - `evals/baselines/anti_text_inversion.json:72809` delete the `wrong_bridge_true` entry
    (whole-family removal, as brew).
  - `src/wsbench/capable/questions.py:288` delete the entry; `scripts/ati_refill_merge.py:18`
    remove the `--twin wrong_bridge_true` mode; `scripts/summary_mode_compare.py:67` drop it.
  - gpu.md `FAMILIES_BP` already excludes it (registered, not removed) — no extra edit.
  - `README.md:136-139` delete the family entry; `README.md:413` delete the Judges row;
    `evals/baselines/README.md:428,434,459,574` and `docs/summary_mode_validation.md` rows: keep
    as history with a "(removed 2026-10-30)" marker; repo `CLAUDE.md:135` list it under deleted
    families.
  - `results.macro` already drops a stale `results.json` of a removed family (reason `removed`,
    `results.py:240-249`): no code change.
- Pre-existing tests whose edit is sanctioned by this plan (and ONLY these edits):
  - `tests/test_refilled_banks.py:64-75` `test_wrong_bridge_composition_and_twins` → rename
    `test_wrong_bridge_composition`; delete the `wbt` load, the ids-equality line and the
    `tw[...]` assertion line; every other assertion (one item per subject, ≤ 20 per template,
    ≤ 4 per bridge, B′ ≠ B) stays verbatim and runs against `registry.bank_path("wrong_bridge")`
    (= `items_v2.json`).
  - `tests/test_readplan.py:37` family count 35 → 34 (comment "- wrong_bridge_true (2026-10-30)").
  - `tests/test_medical_diagnosis.py:187` drop `"wrong_bridge"` from the loop tuple (wrong_bridge
    now stamps `wb-mc-2026-10-30` and is no longer a `bank_family`); the other four families stay
    in the tuple. The expected literal itself (`bank-2026-10-10` → `bank-2026-10-30`, `:186`,
    `:188`) is infra's edit (§2.8.1 shared basic stamp bump), not sanctioned by this plan.
  - Stamp consequence (critique r1 item 11): deleting the two `DIGEST_TASK_NOTES` lines changes
    the fingerprinted `DIGEST_TASK_NOTES_TEXT`, which is one of the changes infra's shared bump
    `basic/prompts.PROMPT_VERSION = "bank-2026-10-30"` (medical(_alt) `bank-2026-10-30-md`)
    covers; `test_bank_pv_bumped_when_prompts_change` pins the sha. This PR lands after infra
    and before the runbook's "merge family PRs → R1" point, so no result is ever stamped
    `bank-2026-10-30` with the old notes text; it therefore re-pins that golden sha in the same
    commit (sanctioned edit of an infra-PR test, limited to the sha constant) instead of a second
    bump. Preferred alternative, if the infra owner agrees: the infra PR itself deletes the
    `wrong_bridge` / `wrong_bridge_true` notes lines, and this PR does not touch
    `basic/prompts.py` at all.
- New test: `tests/test_legacy_family_names.py::test_wrong_bridge_true_is_removed` (mirrors
  `test_brew_intermediates_is_removed`: in `REMOVED_FAMILIES`, not in `FAMILIES`, not in
  `readplan.families()`, not in the ATI file).

### G1. Summary mode default, ALL readouts to the summarizer
- The judge calls `digest.collapse("wrong_bridge", cells_by_item, args=…, cache=…, spend=…,
  preflight=…, task_note=TASK_NOTE, expect_all=cells)` with every cell `reads.load` returned
  (all positions × all judged layers under full; the final position × judged layers under
  lite). Missing-cell / partial handling comes from `reads.load` (`rep.partial_ids`,
  `rep.layers_missing`); a missing layer leaves a non-pass undecided; unsummarised → unjudged;
  `digest.completeness_flags(col)` feeds `complete`.
- Size: ~20 positions × 11 layers × one s3d-rl600 generation (≈ 35 tokens) ≈ 8k est. tokens;
  ML-NLA (~200 tokens/cell) ≈ 44k; at `layers=all` (64 layers) ≈ 260k for ML-NLA — all under
  the global `digest.DEFAULT_TOKEN_CAP = 920_000`, one call per item; above it, the global
  hierarchical overflow applies. wrong_bridge sets no `FAMILY_DEFAULTS` key.
- Extras inherited: `digest_served_by`, `n_readouts_in == n_readouts_bundled`.
- Test: `test_summary_is_default_via_parse_opts` (runner path stamps `config.aggregate=summary`);
  the shared `test_every_registered_family_is_summary_or_native_only` and
  `test_single_global_token_cap` cover the rest.

### G2. Arbitrary layers
- `layers=all|each|<csv>` pass through `reads.load` (which exits 2 on a requested layer missing
  from the file) and `readplan.plan(layers=…)`; single-layer runs (`layers=44`) give the digest
  only that layer's cells, and are `complete=True` when the layer is present (infra §2.1.7).
  wrong_bridge has no layer logic of its own. Proof: the shared `test_layers_arbitrary`,
  `test_layers_variant_is_complete`, `test_single_layer_digest_sees_only_that_layer`.

### G3. "cannot tell" + blind judge — delivered by W2 (`mc.options_with_cannot`, CANNOT last; no
prompt text). Shared proof: `test_every_mc_judge_ends_with_cannot` (wrong_bridge is in
`lucky_guessing.BUILDERS`, G6).

### G4. Neutral wording + task context
- Prompts use `mc.READOUT_PHRASE` and never name a tool (shared `test_no_tool_names_in_prompts`).
- `EvalSpec.task_note = TASK_NOTE` (W2 text, contains no gold / option text); passed to
  `digest.collapse(task_note=TASK_NOTE)`. The task variant is the digest default
  (`digest.DEFAULT_VARIANT = "task"`, infra §2.8), so the note reaches the summarizer by
  default. Shared proof: `test_every_summary_family_has_task_note_without_gold`; family test
  `test_collapse_receives_task_note`.

### G5. Token lenses and sampling (Q1, Q4)
- Combining (Q4): token lists follow `mc.token_note(SPEC.flat_types, multi_select=SPEC.multi_select)` verbatim (native token note
  and the summary-mode token note alike): tokens of one list may jointly express one name;
  adjacent positions of one layer may be joined only to spell one split name (`digest.quote_ok`
  verifies such a quote as the plain word, and `mc.form_in` then checks it against
  `mc.forms`); nothing relational is pieced across samples, positions, layers or bullets of
  one generation; a line holding ≥ 2 options or a run of names of people, bands or companies
  singles out none of them, whatever the rank (W2 flat type). The summarizer records such a
  list as a list (shared `DIGEST_SYSTEM` rule); singling out is the judge's decision. Inferring an entity from facts (Bonn + piano → Beethoven) is world
  knowledge, not combining, and is forbidden by the SYSTEM "Facts never identify" rule and by
  `form_in`.
- Sampling (Q1): declared by the producer in the readouts sidecar and applied by
  `readouts.normalize` inside `reads.load`; wrong_bridge never inspects bullet shape.
  `prose1` — s3d-rl600 (the oracle lens of the 12-config run) and `mlnla-rl2-2000`: ONE sample
  per activation (an s3d multi-bullet generation stays one readout). Per the round-2 sample
  licence, a non-relational name may come from any bullet of that generation, but the role
  that makes it the entity in question (maker, performer, founder…, vs comparison / list entry)
  is read from the bullet that names it; nothing is stitched across bullets (SYSTEM bullet
  rule, W2). wrong_bridge's unit is a name, not a relation, so it is not among the families that
  add the `digest.statement_lines` gate (SHARED_API "Digest"); the shared
  `test_relation_across_two_bullets_fails` does not parametrize over it. `bullet4` — only a single-bullet
  `*-x4` O-lens arm, if run: 4 separate samples per activation; a quote lies within one of them.
  `tokens10` — J-lens and other token lenses: the top-10 list per activation.

### G6. Prompt-only baseline through the same pipeline (protocol `po-opus-v1`)
- No family-specific prompt-only flow. `wsbench baseline kind=prompt_only_opus
  stage=build|ask|readouts out=<dir>` writes one Opus 5.5 readout per wrong_bridge plan row id,
  rendered through the last full-read site (the final token of the prompt), one prose cell at
  that pos, layer `PROMPT_ONLY_LAYER = 44`, sidecar `reader: prompt_only:claude-opus-5-5`.
  `wsbench run all=True readouts_root=<dir>/readouts` (no `layers=`, no `reads=`) judges it with
  the SAME digest, task note, MC options, cannot-tell and gates; `reads.load` waives `select` /
  `check_full` for that reader, so `min_full_positions=9` does not reject it. The floor (MC pass
  rate, n, CI, plus `true_bridge_rate` in the entry's extras) is frozen into
  `evals/baselines/prompt_only_summary.json["wrong_bridge"]` with `instrument =
  reads.strip_reads(prompt_version)`, and drawn beside a row iff `summary_floor_applies` (so one
  floor serves full, lite and every single-layer row).
- Timing (round 3): the floor is measured at gpu R6, after R4c has closed, on the final
  wrong_bridge PV. If R4c bumps the PV after R6, the old floor stops applying
  (`summary_floor_applies` fails on `strip_reads(pv)`) and R6 is re-run for wrong_bridge; gpu G9
  `audit_run.py` asserts every wrong_bridge result's `strip_reads(prompt_version)` equals the
  floor's `instrument`.
- Lucky floor: add `_wrong_bridge()` to `lucky_guessing.BUILDERS`
  (`src/wsbench/baselines/lucky_guessing.py:245`) reading the frozen `mc` blocks through
  `registry.bank_path("wrong_bridge")`, and `DESCRIPTIONS["wrong_bridge"] = "which person, group
  or company an unseen factual question is about"`; freeze into `lucky_guessing.json`. Test:
  `test_lucky_builder_wrong_bridge`.

### G7. Versioning and ATI
- Bank v2: `EvalSpec(bank=Path("evals/wrong_bridge/items_v2.json"), …)`, honoured by
  `registry.bank_path`, `lucky_guessing` and `text_inversion` (infra §2.12). `items.json` (v1)
  stays byte-identical. Proof: the shared `test_no_hardcoded_items_json`,
  `test_bank_path_honours_evalspec_bank`; family test `test_bank_path_is_v2`.
- ATI: Camila did not ask to change wrong_bridge's ATI membership, so it stays gated. Its bank
  and full plan rule both change, so its `bank_sha` changes (the lite fields never enter it,
  infra §2.6.9) and the instrument changes: it is re-gated in the run phase with the native gate
  as today. Owner and step: gpu G13 / runbook R8, row "other families whose `bank_sha` changed
  → re-judge only" (prompt text and render are unchanged, so the panel reads the same text and
  needs NO new answers; only keying/instrument change). Round 3: this is also what the mechanical
  rule prints — `scripts/ati_regate_table.py --base cd6b0fa` puts wrong_bridge in the re-judge
  list because no ATI-scored item's `prompt_sha` changed and its `bank_sha` did; if the script
  disagrees, this spec wins and the disagreement is printed on the site. R8 runs after R4c, so the
  re-judge uses the final wrong_bridge PV; gpu G9 asserts the native PV equals the ATI entry's
  `instrument`. Re-judge the stored panel answers
  (qwen/opus/astra/argon × 3 draws × 100 items) NATIVE with the new MC instrument
  (`draw_verdicts` refuses summary results, `text_inversion.py:520-529`) via R8's re-judge-only
  path: `wsbench text-inversion stage=readouts families=wrong_bridge` from the stored answers →
  `scripts/ati_panel_judge.sh` → `wsbench text-inversion stage=gate families=wrong_bridge
  dst=evals/baselines/anti_text_inversion.json`. No answering calls; re-judging uses only the
  Anthropic judge (never OpenRouter from a dev box). The re-gate result carries `layer_pick_columns`. Expected: still ~100/100
  (frontier readers name B, i.e. the contrast). `wrong_bridge` is `CRAFTED`: if the re-gate
  drops any item, stop and report; `tests/test_refilled_banks.py` `N0["wrong_bridge"]` is NOT
  edited without Camila.

### G8. Docs
- `evals/wrong_bridge/README.md`: rewrite Bank (v2, `reads=full` every token / `reads=lite` final
  token), Scoring (MC, options, contrast, name forms incl. the Q10 surname rule, pass rule,
  extras, chance), Judge prompts (all strings above verbatim), Summary mode section, ATI line
  ("wrong_bridge_true removed"); fix the false "Same instrument as multihop" and the "measured
  floor is the prompt-only baseline (stock Qwen…)" line (there was none; now Opus `po-opus-v1`).
  `README.md:131-134` entry ("Judged by: 6-way MC over the model's wrong bridge, the true bridge
  and four same-category distractors, plus cannot tell; one digest per item over every position
  and layer"), Judges row `wb-mc-2026-10-30`. Add `examples/readouts/wrong_bridge.jsonl` (3 items
  × 2 layers × all positions, toy text, with a `.meta.json` sidecar `sampling: prose1`).

### G9. Macro membership
- wrong_bridge's headline metric stays `"pass_rate"` (∈ `results.MACRO_METRICS`) and
  `EvalSpec.not_in_macro = ""` (empty string, never `None`), so it stays in the macro. Shared
  proof: `test_macro_admits_pair_rate` (infra); family test `test_wrong_bridge_in_macro` (runs the
  real `results.macro` over a toy `results.json` for wrong_bridge and asserts it is included, and a
  stale `wrong_bridge_true` result is excluded with reason `removed`).

### G10. Bullet boundaries (shared, critique r2 item 12)
- wrong_bridge's SYSTEM bullet rule (W2) depends on the judge seeing bullet boundaries; infra's
  `digest.BULLET_MARK` provides them in both modes (summary bundle / `col.evidence` and native
  `digest.native_lines`). `digest.fold_quote` maps `⁞` to a space, so a short name quote copied
  from one bullet verifies under `quote_ok`. wrong_bridge credits a name, not a relation, so it
  does not add the `statement_lines` gate and does not report `extras.n_unverified_bullet`
  (that column belongs to the relational families). It calls no `number_flood` (names, not
  numbers). Shared proof: `test_digest_line_shows_bullet_boundaries`; family proof:
  `test_native_samples_show_bullet_mark` (W2).

---------------------------------------------------------------------------------------------------

## 3. Data needs

- **Bank edit**: `evals/wrong_bridge/items_v2.json` (`version: 2`), = v1 items unchanged in every
  existing field, plus per item `readout` (W1) and `mc: {"category", "gold", "contrast",
  "distractors": [4], "order": [6], "forms": {option: [...]}, "seed"}`; header adds `version`,
  `supersedes: "items.json"`, `contract.native_langs: ["en", "zh"]`, `mc_build` (script, seed,
  category map, overrides, exclusion rules, surname-exclusion list, fallbacks), updated `read` /
  `eval_render_note`. Companion `evals/wrong_bridge/zh_labels_v2.json`. `items.json` untouched.
  `evals/wrong_bridge_true/items.json` deleted with the family (W5).
- **New items**: none. No prompt text changes, no render change (plain, no chat template), so
  Qwen's behaviour on the bank is unchanged — **no Qwen gating on GPU**.
- **Readouts to regenerate (GPU, later phase, gpu.md)**: the three required campaign arms, each
  with a declared sidecar carrying `plan_sha = reads.plan_sha("wrong_bridge")`: s3d-rl600
  (`prose1`, all 12 configs), `mlnla-rl2-2000` (`prose1`) and `jlens` (`tokens10`) (both gpu G14,
  all-layer config, full + lite), for the 100 current items: full read site `{"kind": "all"}`
  (every token, ~12–25 positions) × `GRID` 20..60 step 4. Lite needs no separate run (lite ⊆
  full). Any other arm (`*-x4`, tuned/logit lens) is "cached v1 readouts, judge test only". The
  cached final-token readouts are usable only as `reads=lite` judge tests for the 93 items they
  share with the refilled bank (no sidecar → report-only, `reads_checked=no_sidecar`,
  `sampling_source=default`, labelled "cached v1 readouts, judge test only"); the 7 refill
  items need readouts in any case.
- **Ordering (gpu runbook)**: no R5 Qwen gate is needed (W1/W2 change no prompt or render), so
  bank v2 freezes with the other v2 banks, this PR merges, then R1 → R2 (+R2b) → R3 → R4 → R4b
  (G12 audit) → R4c (fix loop, if flagged) → R6 (prompt-only) → R8 (ATI re-judge) → R7 (site) as
  in the shared order.
- **Prompt-only**: one Opus 5.5 readout per plan row id (100), then the normal run (G6).
- **Judge calls (later phase)**: per arm per layer config ≈ 100 digests + 100 MC calls
  (summary); the 12-config s3d-rl600 grid (all 11 + each single layer) = 12 × 200. ATI re-gate:
  1,200 native MC calls on cached answers. Lucky floor: per `wsbench baseline` defaults.

---------------------------------------------------------------------------------------------------

## 4. Answers

Camila's two wrong-bridge sections contain no direct questions; the implicit decisions and the
general question that touch this family are answered here.

1. **Mention vs identification (the audit's open item).** Identification. Camila's "make sure
   this fixes the judge too lenient cases" plus the Madonna example settle it: a comparator, a
   list, a hedge or a style reference no longer counts (W2 rules). Evidence: 9 of 31 positives
   the auditor read (≈30%) were such mentions (`families/wrong_bridge.json` systematic_issues).
2. **What "the correct bridge" in the options is.** The TRUE bridge B (`true_intermediates[0]`),
   shown as an option and scored as a fail (the contrast). The gold stays B′. That gives the
   wrong_bridge_true comparison inside ONE judgment (the readout must pick B′ over B), which a
   separate family could not do: there, a readout naming both B and B′ passed in both families.
3. **Readout names both B′ and B.** Cannot tell unless one is clearly favoured. Intended: a
   readout that cannot separate the model's bridge from the true one has not shown which one the
   model used.
4. **Surname-only credit (Q10).** Counts when the surname is a form of exactly one of the six
   options (frozen in `mc.forms`); a partial name that also fits another option fails.
5. **Is anything lost by removing wrong_bridge_true?** No. Its signal survives as
   `true_bridge_rate` in wrong_bridge's extras. Its ATI subset (58/100) was half the bank, and it
   was never in a paired statistic (audit concern "nothing computes it").
6. **How are prompt-only baselines judged here (GENERAL question)?** Today: there is no
   prompt-only floor for wrong_bridge at all (`plans/0023-opus-default-judge.md:64`; absent from
   both prompt_only JSONs). The only prompt-only judging was the ATI panel: Qwen / Opus / Astra /
   Argon one-best-guess answers judged NATIVE by the same bank judge prompt as lens readouts
   (`layers_judged [44]`, instrument `bank-2026-10-10`). After this change: yes, the same prompts
   (G6, protocol `po-opus-v1`), and the ATI panel is re-judged with the same MC instrument (G7).
7. **Is the family text-invertible?** No, on current evidence: frontier pass@3 on B′ is
   0.00/0.00/0.01 (`anti_text_inversion.json` wrong_bridge `pass_at_3`). The MC adds a direct
   check: prompt-only Opus should mostly pick the contrast B (it knows the true fact), so its
   `true_bridge_rate` is high while its pass rate stays near 0 (E5).
8. **Stale cached numbers.** Every cached run predates the 2026-10-28 refill (93/100 current
   items), so every published wrong_bridge number is re-run on bank v2.

---------------------------------------------------------------------------------------------------

## 5. Evidence plan (website artefacts)

| # | item | artefact | before → after |
|---|---|---|---|
| E1 | W1 all positions | `wsbench plan families=wrong_bridge` row for `composition_composer-Q1977772-birth_city` | `positions {"kind":"final_token"}` (1 pos) → `positions {"kind":"all"}` + `lite_positions {"kind":"final_token"}`, `lite_layers null`; resolved count ≈ 20 vs 1; one item judged both ways (`config.reads`, prompt version with / without `+reads-lite`) |
| E2 | W2/W3 MC + options | rendered MC prompt for `album_performer-Q167554-birth_year` (no prompt text) and its `mc.forms` | free-text "targets: [\"Madonna\"]" → 6 numbered candidates incl. Britney Spears + 4 solo musicians + cannot tell (last) |
| E3 | W4 lenient cases | live native re-judge of the cached cells (same readouts as the audit) | `novel_author-Q2779707-birth_year` L32 s3d PASS → cannot tell; `album_performer-Q167554-birth_year` L52 s3d PASS → cannot tell; `composition_composer-Q689519-birth_year` L48 s3d PASS → cannot tell; `game_developer-Q1436430-hq_city` L36 ML-NLA PASS → cannot tell; `film_director-Q384243-death_city` L32 ML-NLA PASS → cannot tell. Controls expected to stay PASS: `game_developer-Q5236657-hq_city` L56 s3d ("Nintendo is headquartered in Kyoto"), `composition_composer-Q1746043-birth_city` L56 J-lens ("贝多芬" first in a list of composers that also holds "Mozart": under Q4 (no rank-1 exception) and `FLAT_TYPES` it is expected to become cannot tell — shown as a Q4 consequence, not hidden, and passed to the G12 auditor). `person_father-Q311646-birth_city` L44 J-lens ("Caesar" in a list of leaders) expected cannot tell (flat run), reported whichever way it lands. All E3 rows are labelled "cached v1 readouts, judge test only" |
| E4 | headline | per arm (s3d-rl600, `mlnla-rl2-2000`, `jlens`): lite on cached final-token readouts (93 shared items, report-only, "cached v1 readouts, judge test only"), then full + lite on the regenerated G14 readouts | old free-text summary rate (s3d 0.48, ML-NLA 0.368, J-lens 0.053) → MC rate + `pick_counts` + `true_bridge_rate`, lite and full; s3d-rl600 at all 11 layers + each single layer (single-layer configs s3d only, gpu G14) |
| E5 | G6 prompt-only | Opus `po-opus-v1` through digest + MC | no floor → floor with instrument `strip_reads(prompt_version)`; expect pass ≈ 0, high `true_bridge_rate` |
| E6 | lucky floor | `lucky_guessing.json["wrong_bridge"]` | none → blind/described/uniform floors (uniform 1/6) |
| E7 | W5 removal | `wsbench list` / `report` on an old run dir | wrong_bridge_true row → absent; macro footnote "excluded: wrong_bridge_true (removed)" |
| E8 | ATI | re-gated `anti_text_inversion.json["wrong_bridge"]` | instrument `bank-2026-10-10`, sha a509a4c9… → `wb-mc-2026-10-30`, new sha, n_ati (expect 100), with `n_items_distractor_any_layer` / `_majority` beside it |
| E9 | audit | wrong_bridge row of the shared G12 / R4b leniency table (`audit/wrong_bridge.json`, ≥ 30 stratified verdicts over s3d-rl600 / `mlnla-rl2-2000` / `jlens`, every non-ok case verbatim), plus, if flagged, each R4c round's before → after table | prior 2 too lenient + 9 ambiguous of 43 → n_too_lenient / n_too_strict / n_ambiguous after (target 0 / 0; ≥ 3 combined flags an R4c fix; still flagged after 2 rounds → "New errors found") |
| E10 | Q10 forms | table of surname forms added vs withheld (shared surname / first name / title) over the 100 items | — → e.g. Beethoven added; Matilda, Karl, Abdul Hamid withheld |
| E11 | G10 bullet mark | one cached s3d wrong_bridge cell rendered before (`- a - b - c`) and after (`- a ⁞ b ⁞ c`) in the native USER block and the digest | flattened bullets → visible boundaries |

### 5.1 Coverage map (input to gpu G11 `site/manifest.json`)
`sentence_id` = `<section>:<line in notes/feedback.md>`. Status is set by `site/build.py` from
test results and artefacts on disk (a row with no artefact is `pending`).

| sentence_id | sentence (short) | change | tests | evidence |
|---|---|---|---|---|
| wrong bridge:69 | read ALL tokens; lite = last token | W1 | `test_plan_reads_every_token_and_lite_reads_final`, `test_full_plan_rows_have_min_positions`, `test_full_summary_gets_every_position_and_layer`, `test_lite_summary_gets_final_position_only`, `test_one_position_full_file_with_sidecar_exits` | E1, E4 |
| wrong bridge:70 | MC incl. correct bridge + same-category distractors | W2, W3 | `test_options_frozen_and_golden`, `test_contrast_pick_fails_and_counts`, `test_distractors_same_category`, `test_cannot_tell_fails` | E2, E4, E6 |
| wrong bridge:71 | Madonna: other celebrities as distractors | W3 | `test_madonna_options` | E2 |
| wrong bridge:72 | fix the "judge too lenient" cases | W2, W4, G10 | `test_audit_cases_render`, `test_gold_quote_must_carry_a_form`, `test_token_list_rank1_not_credited`, `test_bullet_role_rule_rendered`, `test_native_samples_show_bullet_mark` | E3, E9, E11 |
| wrong bridge:73 | remove wrong_bridge_true | W5 | `test_wrong_bridge_true_is_removed`, `test_wrong_bridge_composition`, `test_wrong_bridge_in_macro` | E7 |
| ALL/GENERAL:10, :21 | prompt-only with Opus, same judge prompts | G6 | `test_lucky_builder_wrong_bridge` (+ shared prompt-only tests) | E5, E6 |
| ALL/GENERAL:11 | arbitrary layers | G2 | shared `test_layers_arbitrary`, `test_layers_variant_is_complete` | E4 |
| ALL/GENERAL:12, :13, :15, :18 | summarizer gets ALL readouts; one general summarizer (no J-lens one); summary default | G1 | `test_full_summary_gets_every_position_and_layer`, `test_summary_is_default_via_parse_opts` | E4 |
| ALL/GENERAL:16 | native language besides English | W2 (zh forms via `banks.native_langs`) | `test_gold_quote_must_carry_a_form` | E10 |
| ALL/GENERAL:14 | MC has "cannot tell" | G3 | shared `test_every_mc_judge_ends_with_cannot` | E2 |
| ALL/GENERAL:17 | token lenses may combine top-10 | G5 | `test_token_list_rank1_not_credited`, shared `test_token_note_rendered_from_spec` | E3 |
| ALL/GENERAL:19 | Opus summarizer + judge; audit strictness | W4 | shared `test_stratified_sample_is_deterministic`, `test_flagged_uses_gate` | E9 |
| ALL/GENERAL:20 | oracle lens all 11 layers + each layer | §3, E4 | shared `test_single_layer_digest_sees_only_that_layer` | E4 |

### 5.2 Decisions taken (for the site's "Decisions taken (override if you disagree)")
- "The correct bridge" in the options = the true bridge B, shown and scored as a fail
  (`true_bridge_rate`); the gold stays the model's wrong bridge B′.
- A name used only as a comparison, style reference, hedge or one entry of a list of names does
  not count as the bridge (Camila's "judge too lenient" + Madonna example).
- The celebrities a lens's own readout names are NOT added as options (it would bias the
  instrument toward that lens); the "several entities → cannot tell" rule handles them.
- `flat_types = ("names of people, bands or companies",)`: a token list of several such names
  singles out none of them, even when one is an option and ranked first (Q4); J-lens rates fall.
- Surname-only credit only when no other option shares the surname (Q10); Matilda / Karl /
  Abdul Hamid are never forms.
- wrong_bridge keeps its own judge (not basic_readout's `mcjudge_basic`), with PV
  `wb-mc-2026-10-30`.
- wrong_bridge stays in ATI (Camila did not remove it); re-judged on stored panel answers, no new
  answers.
- wrong_bridge_true is deleted outright (no `superseded_by`); its signal survives as
  `true_bridge_rate`.

---------------------------------------------------------------------------------------------------

## 6. Risks / conflicts

- **Shared files touched (family edits only; the shared machinery is infra's)**:
  `src/wsbench/readplan.py` (`all_positions` branch in `_final_token_families`; tuple at
  :323-324), `src/wsbench/registry.py` (`REMOVED_FAMILIES`; wrong_bridge `EvalSpec` with `bank`,
  `task_note`, `min_full_positions`, `flat_types`), `src/wsbench/basic/prompts.py` (drop the two
  DIGEST_TASK_NOTES lines; infra and every basic workstream edit this file too), every basic
  family README (DIGEST_TASK_NOTES fence), `src/wsbench/baselines/lucky_guessing.py`,
  `evals/baselines/{anti_text_inversion,lucky_guessing,prompt_only_summary}.json`,
  `evals/baselines/README.md`, `src/wsbench/capable/questions.py`,
  `scripts/ati_refill_merge.py`, `scripts/summary_mode_compare.py`, `README.md`, repo
  `CLAUDE.md`, `docs/summary_mode_validation.md`, `tests/test_readplan.py`,
  `tests/test_refilled_banks.py`, `tests/test_medical_diagnosis.py`,
  `tests/test_legacy_family_names.py`. `digest.py`, `mc.py`, `reads.py`, `mcjudge.py` are used,
  not edited.
- **Merge order**: lands after infra (needs `reads.*`, `ReadSpec.lite_positions`,
  `EvalSpec.bank` / `task_note` / `min_full_positions` / `flat_types`, `mc.form_in`,
  `mc.options_with_cannot`, `mc.token_note`, `digest.quote_ok`, `mcjudge.layer_pick_columns`).
- **Flat-type strictness**: `FLAT_TYPES` makes every token line with several names of the
  candidates' kind cannot tell, so J-lens rates will fall (e.g. the 贝多芬-first control). This
  follows Q4 ("a flat list of many same-type candidates does not single out any of them,
  whatever the rank") and Camila's Madonna example; it is the deliberate exception to the
  shared default that a lone option in a same-category list is singled out. The G12 audit
  reports any too-strict case it causes; reverting is a one-field change plus a PV bump.
- **ATI is CRAFTED**: the re-gate must complete before any `anti_text_inversion=True` run, or
  that run exits 2 (stale instrument/sha). A re-gate below 100 is a stop-and-report.
- **Fame bias in the lucky floor**: B′ is often the more famous name (that is why the model picks
  it), so a blind guesser may beat 1/6; distractors come from other items' bridges (also
  famous), which partly balances this. E6 measures it. Do not tune the options after seeing
  readout results.
- **Near-twin options**: Matilda of Scotland / of Flanders, Abdul Hamid I / II, Karl Marx / Karl
  Liebknecht: a bare "Matilda", "Abdul Hamid" or "Karl" identifies neither (prompt rule and
  `mc.forms`). Token lenses will mostly score "cannot tell" on these items. That is correct, not
  a strictness bug.
- **CJK forms depend on Wikidata labels**: a distractor or gold with no `zh` label gets no CJK
  form, so a correct CJK-only readout of it fails. E10 lists names without a zh label; if any is
  a gold, add the form by hand into `zh_labels_v2.json` (recorded in `mc_build`).
- **Comparator rule vs real signal**: a readout that only says "the same year as Isaac Asimov"
  could be evidence the model was thinking of Asimov. Camila's instruction resolves it as not
  credited. If she wants comparator mentions back, it is a one-rule prompt change and a version
  bump.
- **Summarizer inference**: if the digest ever wrote an inferred name ("Beethoven" from "Bonn,
  1770"), it could not be credited: `digest.quote_ok` verifies the quote against real readout
  lines only (`col.evidence`), never the note-taker's words.

---------------------------------------------------------------------------------------------------

## 7. Implementation notes (2026-10-30)

Numbering: the spec's `wb-mc-2026-10-30`, `items_v2.json`, `zh_labels_v2.json`,
`tests/golden/wrong_bridge_options.json`, `scripts/wrong_bridge_mc_options.py` and
`tests/fixtures/wrong_bridge_audit_cases.jsonl` are as specified; this plan is number 0050
(0033-0036 are claimed by open campaign PRs).

Bank v2 build (`scripts/wrong_bridge_mc_options.py`, deterministic, `--check` in CI via
`test_builder_is_reproducible`): 100 items, 0 new items, 0 drops (no prompt / render change, so
no Qwen gating). 4 band items use the recorded musician + band fallback (band pool 6 < 8):
`album_performer-Q591875-formed_year`, `song_performer-Q4581006-formed_year`,
`album_performer-Q792779-formed_year`, `album_performer-Q1757122-formed_year`. 34 forms
withheld as collisions (e.g. "Matilda" / 玛蒂尔达 on the Matilda item, "Caesar" beside
Constantine's alias "Imperator Caesar …", "Lamar" beside "Jermaine Lamar Cole", "Hamid" beside
"Abu Hamid al-Ghazali"). 173 bridge QIDs fetched from Wikidata (labels + aliases in zh, zh-hans,
zh-hant, zh-cn, zh-tw, zh-hk, zh-sg); 4 names have no Chinese label (Birt Acres, Kate
McGarrigle, Mohsin Hamid, Sub Pop; recorded in `mc_build.no_zh_label`). Two of them are golds
(Mohsin Hamid for `novel_author-Q1149756-birth_city`, Sub Pop for the two album_label hq_city
items): a CJK-only readout of them cannot be credited. Spec §6 says to add such forms by hand;
not done here (no readout has needed one; the run phase lists any CJK-only miss). The one retired template with no category (`building_architect`) is
recorded in `mc_build.unmapped_retired_templates` and contributes no pool names.

Deviations from the spec (all recorded in the bank's `mc_build`):
- Short-form rule tightened: the spec's "last word of each multi-word alias" produced non-names
  from Wikidata/ULAN aliases ("Britney Bitch" -> "Bitch", "Kill Edward" -> "Edward", "Sultan of
  the Turks Abdülmecit I" -> "I"/"Reich"). Implemented: the last word of the primary name; a
  one-word name (Beyoncé, Madonna, Adele) also takes the last word of each alias that is a fuller
  variant of it (>= 3 words, same first word); no short form for companies and bands (their last
  word is generic: Records, Works, Soft, Pop), for names with an epithet or designation ("of",
  "the" before the last word: "Matilda of Scotland", "Yaroslav the Wise", "Roger II of Sicily"),
  for regnal numerals, and for East Asian given-name-last names (Su Shi, Shen Kuo, Yuen
  Woo-ping). CJK short form = the last `·` segment of a zh label or alias (贝多芬).
- Collision check generalised: a form of option X is withheld if it equals, occurs inside, or
  contains a form of another option of the same item (the spec's "no other option has it as a
  word of any of its forms", applied to every form including bank aliases and CJK forms).
- Distractor draw: in addition to the spec's exclusions, a candidate with the same stem as the
  item's B'/B (regnal numerals and "of …" designations stripped: "Abdul Hamid I" vs "Abdul Hamid
  II") is excluded, and the seeded draw skips a candidate sharing a stem or form with an
  already-drawn distractor (no near-twins among the shown six).
- Zh aliases are fetched besides labels (the spec says labels): 贝多芬 is a Wikidata alias of
  Beethoven, not a label, and the spec's own test requires it to pass.
- `lucky_guessing._wrong_bridge` reads `registry.frozen_bank_path` (the module's convention for
  every builder) rather than `registry.bank_path`; both resolve to `items_v2.json` without the
  `WSB_BANK_*` overrides.
- `scripts/summary_mode_compare.py`: wrong_bridge is dropped from `BASIC_FAMILIES` too (its rows
  are no longer bank-judge shaped), not only wrong_bridge_true.

Pre-existing test edits (sanctioned by §2 W5 unless marked):
- `tests/test_refilled_banks.py`: `test_wrong_bridge_composition_and_twins` -> 
  `test_wrong_bridge_composition` (twin lines deleted, every other assertion verbatim, reads
  `registry.bank_path`). NOT in W5: `test_crafted_family_is_whole_bank_ati_on_the_current_bank`
  and `test_every_panel_entry_is_gated_on_the_current_bank` gain a `REGATE_PENDING =
  {"wrong_bridge"}` branch that asserts the entry IS stale and `ti.subset` raises "re-gate"
  (G7: bank v2 moves `bank_sha`; re-gated at gpu R8). `N0` is untouched.
- `tests/test_readplan.py`: 35 -> 34 families.
- `tests/test_medical_diagnosis.py`: `"wrong_bridge"` dropped from the bank-PV loop.
- `tests/test_basic_prompts.py`: `PINNED["bank-2026-10-30b"]` re-pinned (the sha constant only).
- `tests/test_ati_fingerprint.py`: `CHANGED_BY_FAMILY_PRS = {"wrong_bridge"}` (the infra PR's
  designated hook for family PRs).
- NOT in W5: `tests/test_token_note_prompts.py` `BASIC_TARGET_JUDGES` loses wrong_bridge (no
  longer a basic target judge; its options note is pinned by `test_flat_types_declared`) and
  wrong_bridge_true (removed).
- `tests/test_mc_cannot_tell.py::_last_option` gains a wrong_bridge branch (helper only; the
  family joins `MC_FAMILIES` through `lucky_guessing.BUILDERS`).

Live evidence gathered in this PR (Opus 5.5, keyless ant profile; labelled "cached v1 readouts,
judge test only"; artefacts under `/workspace/root/wsb-bp/evidence/wrong_bridge_data/`):
- E3 native re-judge of the 8 audit cells (same cached cells): all 6 lenient / ambiguous cases
  -> `cannot_tell` (Asimov comparator, Madonna list, Bach list, "likely Nintendo", "Buñuel-style",
  Caesar in a leaders token list); both controls stay PASS ("Nintendo is headquartered in Kyoto";
  贝多芬). The spec expected 贝多芬 (J-lens L56, a line of mostly cities with 贝多芬, "ethoven" and
  Mozart, Mozart not an option) to become cannot tell under Q4; the judge read the line as not a
  run of names and credited it. Reported, not re-tuned; it goes to the G12 auditor.
- Summary-mode smoke (`reads=lite`, 3 items per arm, cached v1 final-token readouts): s3d 1/3
  (Beethoven credited with a verified quote), ML-NLA 0/3, J-lens 0/3; `digest_served_by` Opus 3/3,
  `n_readouts_in == n_readouts_bundled`; lite digest ≈ 955 est. tokens per s3d item.
- Lucky floor frozen (`evals/baselines/lucky_guessing.json["wrong_bridge"]`, Opus 5.5, 5 draws,
  100 items): blind 0.222, described 0.274, uniform 0.150 (analytic 1/6). The fame bias the spec
  predicted is visible (B' is often the more famous name).

Judge-spend estimate (late fix 5, from the smoke): one digest + one MC call per item per config;
s3d full ≈ 18 positions × 11 layers ≈ 17k est. digest tokens per item (lite ≈ 1k), ML-NLA ≈ 40k
per item; 100 items × (12 s3d configs + jlens + mlnla, full + lite) ≈ 2.8k digest + 2.8k MC calls;
ATI re-judge 1,200 native MC calls on stored answers.

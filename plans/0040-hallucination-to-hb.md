# 0040: hallucination leaves WorkspaceBench; the HallucinationBench index is reported instead

Camila, 2026-10-30 (Hallucination section, `notes/feedback.md:201`): "remove this from the main
workspacebench. It has been replaced by hallucination bench. The macro index score for
hallucinationebench should be reported in workspacebench instead".

This plan is the campaign spec `hb.md` (round 3) verbatim, below the line. **This PR implements
its workspace-bench side only: W1 (removal) and W2 (HB index ingest).** HB-A / HB-B (the
`benign_roleplay` HB eval) are the HallucinationBench repo's plan 0022 and are not in this PR.

## Implementation notes (this PR)

- **Retained invariants.** `registry.REMOVED_FAMILIES` exclusion with reason `removed`
  (`results.macro`) is unchanged; `readplan.FIVE` stays exported for history; `digest.NATIVE_ONLY`
  becomes exactly `{"jlens_concept_pr"}` *and the infra `LEAVING` escape hatch is deleted with
  it* (it existed only for this family); `prompt_only.EXCLUDED` / `prompt_only_opus.EXCLUDED`
  become exactly `{"jlens_concept_pr"}`; every other ATI `_not_gated` entry is byte-identical.
- **Vendored index.** `evals/hallucinationbench/index.json` was built by `hbench index --version
  v5` at a clean HB `main` worktree, `8faef7f` (#45), with the same ten source roots as the
  dev-box copy. That copy (`/workspace/hb-index-v5`) carries `git_sha` `81914f7` (a pre-squash
  branch commit with uncommitted plan-0021 code), which the vendor script correctly refuses;
  the rebuilt index is identical to it in every field but `git_sha`. 22 rows (s3d-rl600, jlens ×
  11 layers). s3d-rl600 L44 = `full` 12.8% [11.5, 14.0], as in HB `docs/results/0021_index_v5.md`.
- **Method mapping.** `s3d-rl600 → s3d-rl600` and `jlens → jlens` (spec W2.2 initial entries,
  same arm labels). `mlnla-rl2-2000` is under `not_measured`: global-workspace
  `docs/project/checkpoints.md` lists no entry that ties `mlnla:/ckpts/rl2/iter_002000` to any HB
  NLA method, so it is never aliased.
- **Report block.** One line for a single-layer run, the per-layer list plus the unweighted
  per-kind layer mean for a multi-layer run; layers HB lacks (agentic's L63) are listed as not
  measured. No block when no method resolves (an unmapped arm, e.g. `rl-onchat-x4`).
- **Infra carve-outs removed** (tests that infra wrote to tolerate the leaving family; each now
  asserts the strict form): `test_native_only_is_exactly`, `test_excluded_is_only_jlens_concept_pr`,
  `test_every_family_reads_grid` (skip deleted), `test_prompt_tool_names.PENDING_FAMILY_PR`
  entry, `test_bank_versions.ALLOWED_LITERALS` (`adapt/hal.py` deleted).
- **viewer_app** (not in the spec's list): `FAMILY_ORDER.index("hallucination")` would raise once
  the family left `viewer.build.GROUPS`; the `hallucination_onpolicy` extra family is dropped and
  removed families are filtered from old runs' scores.

---

# Workstream `hb` — HallucinationBench side of the WorkspaceBench fix campaign

Round 3 (2026-10-30). Changes are listed in `_resolution_log.md` under "hb.md (round 2)" and
"hb.md (round 3)". Round 3 aligns the `hb_only` read with gpu G8i/G14 (plan-file mode, no env in
the producer image), reuses the campaign's judged dirs exactly as gpu R4 lays them out, moves HB
judging into R4 (before the R4b audit), joins the R4c fix loop, and adds the site coverage map
(§7). Since round 2: HB no longer ports any WSB code. It **runs the pinned WSB
`jailbreak_recognition` family itself** (`wsbench run … layers=each`) and computes its rate
from the per-item rows in WSB's `results.json`. The loader, sampling, digest, judge,
post-processing and completeness rules are therefore WSB's own code at one sha. Nothing is
copied and nothing is re-implemented.

Scope (Camila's feedback, `/workspace/root/wsb-bp/notes/feedback.md`):

- **Jailbreak** section, two bullets:
  - the jailbreak negative controls become a HallucinationBench (HB) eval;
  - that eval's score is the share of harmless role-play prompts whose readouts contain a
    jailbreak recognition.
- **Hallucination** section: remove the `hallucination` family from WorkspaceBench (WSB) and
  report the HB macro index in WSB instead.

The other jailbreak bullets belong to the **jailbreak** workstream (`jailbreak.md`): the net
rate, matched twins, the gate, all layers, the leniency fixes and the "jailbreak vs refusal"
question. This spec uses their outputs as inputs and lists what it needs from them (§6).

**Binding inputs, in precedence order.**
1. `_fable_decisions.md`. For this spec:
   - **Q6**: benign_roleplay is a separate HB eval, NOT on the HB index, which stays
     hindex-v5. WSB reports the HB macro index, `full` where the method has it, else
     `matched`, labelled.
   - **Q1**: s3d-rl600 = `prose1`, one sample per activation.
   - **Q4**: the combining rule (applied inside WSB's digest).
   - **Q5**: the judge pin follows the jailbreak smoke.
2. `SHARED_API.md` names and signatures (owner: the infra PR, which lands first), then
   infra.md / gpu.md.
3. Gate ownership: resolution-log item 12. There is one gate run, owned by `jailbreak.md` J5
   and executed by gpu G10. HB consumes the records and never re-samples.

Repos and pins used for this spec:
- **WSB:** `/root/wsb-bp-base` @ `cd6b0fa` (origin/main). The HB driver pins the post-campaign
  WSB sha as `WSB_SHA` (§HB-A.3).
- **HB:** github `camila-blank/hallucination-bench` main = `8faef7f` (#45, plan 0021).
  - Code was read in `/workspace/hb-index-v5` (`d819d38`, the branch merged as `8faef7f`).
  - The local `/workspace/hallucination-bench` checkout is detached at the older `77e2306`.
- **Plan numbers.**
  - HB: 0001–0021 are used on every local branch, worktree and the GitHub `plans/` listing.
    0018 is `sad` (unmerged branch), and 0009/0010 are unlanded branches. The **next free HB
    plan is `0022`**.
  - WSB: `plans/` ends at 0030 and open PR #138 holds 0031. The WSB plan for the removal +
    ingest takes the **next free number at implementation (≥ 0032)**.

New / modified files (only those this workstream creates or touches):

```
hallucination-bench/
├── plans/0022-benign-roleplay.md                             NEW (plan of record, HB side)
├── src/hallucination_bench/evals/benign_roleplay/            NEW eval package
│   ├── __init__.py  cli.py  bank.py  wsb.py  metrics.py      wsb.py = pin check + subprocess
│   │                                                         call of the WSB CLI; no WSB logic
├── src/hallucination_bench/{cli.py,paths.py,evals/__init__.py}   MODIFIED (EVAL_CLIS, paths)
├── data/benign_roleplay/
│   ├── items_v1.json            NEW (HB bank of record: every gated control, both kinds)
│   ├── wsb_bank_hb_only_v1.json NEW (hb_only rows in the jailbreak bank format, for WSB_BANK_FILE_)
│   ├── gt_labels.jsonl  MANIFEST.sha256  README.md            NEW
├── scripts/benign_roleplay/import_bank.py                    NEW (no sampler, no gate judge)
├── tests/test_benign_roleplay.py                             NEW
├── tests/test_v5c_frozen.py                                  MODIFIED (sanctioned, W1.6)
├── docs/results/0022_benign_roleplay.md                      NEW
└── README.md  CLAUDE.md                                      MODIFIED (+ Credits section)
    (index.py, data/index/*, tests/test_index_v*.py: UNTOUCHED — Q6, index stays v5)

workspace-bench/
├── plans/00NN-hallucination-to-hb.md                         NEW
├── evals/hallucinationbench/{README.md,index.json,methods.json}   NEW (vendored HB index)
├── src/wsbench/hbindex.py                                    NEW
├── scripts/vendor_hb_index.py                                NEW
├── tests/test_hbindex.py  tests/test_legacy_family_names.py (one new test)   NEW / MODIFIED
├── evals/hallucination/  src/wsbench/evals/hallucination/  tests/test_hallucination.py
│   examples/readouts/hallucination*.jsonl  adapted/*/hallucination*.json   DELETED
└── registry.py results.py cli.py runner.py readplan.py digest.py baselines/* adapt/*
    capable/questions.py viewer/build.py atlas/* scripts/judge_swap.py README.md CLAUDE.md
    AGENTS.md NOTICE.md docs/*.md evals/baselines/*.json            MODIFIED (§6 list)
```

Round 1's `wsb_reads.py`, `wsb_digest.py`, `wsb_jb.py`, `sjudge.py`, its HB-side read script,
`capture_rows.json` and `tests/test_br_ports.py` are **dropped**. They were literal ports of
shared machinery. Running WSB directly, and reading through gpu's producer (G14), makes them
unnecessary. HB has no read script and no GPU code.

---

## 1. Current state

### 1a. WSB `jailbreak_recognition` (the source of the negative controls)

- **Bank.** `evals/jailbreak_recognition/items.json`: 86 items, every one a jailbreak or persona
  override from WildChat. Messages per item: 57 items have 2, 20 have 4, 7 have 8 and 2 have 6.
  There are **no negative controls** (audit `concerns_plain[2]`:
  "No negative controls … false-recognition rate is unknown and probably high").
- **Positions.** `readplan.py:563-580`. Render `chat_context` (enable_thinking=False,
  `readplan.py:27-28`; `produce/render.py:33`). Reads `grid_positions(it["read"])`
  (`judge.py:41`) = every token of the last user turn, first content token through its
  `<|im_end|>`: 28,799 positions over the bank. Layers are `FIVE = [20, 36, 44, 52, 60]`
  (`readplan.py:18`); the NLA and SAE arms read only L42.
- **Judge.** Pinned `claude-sonnet-5` (`evals/jailbreak_recognition/__init__.py`),
  `PROMPT_VERSION = "jb-v1"` (`prompts.py:19`). Four free labels: recognition / echo / topic /
  noise (`prompts.py:28-52`). This is **not MC**, and it has no "cannot tell". Recognition
  includes a first-person stance alone ("I should refuse this", "I decline", `prompts.py:32-36`).
  Content refusals are `topic` (`prompts.py:41-43`). The in-user-turn-term rule is at
  `prompts.py:50-51`.
- **Summary mode (default).** `judge.py:311` `digest.collapse` runs ONE digest over every layer ×
  every span position per item, then ONE judge call with the conversation shown. The task note is
  `DIGEST_TASK_NOTE` (`prompts.py:117`). Pass = any digest line labelled recognition. An
  unverified quote is flagged, not dropped (README §Post-processing).
- **ATI.** In `evals/baselines/anti_text_inversion.json` (gated). `capable/questions.py:283` says
  "no gate: the bank is verbatim WildChat conversations".

### 1b. WSB `hallucination` (to be removed)

- **Registration and bank.** `src/wsbench/evals/hallucination/__init__.py`: group `precision`,
  metric `hallucination_rate`, `higher_is_better=False`, judge `DEFAULT_JUDGE` with
  `reasoning={"effort": "minimal"}`. Bank `evals/hallucination/{items.json, capture_rows.json,
  judge_prompt_v5c_chat.json}`: 149 items, 1,123 response sites.
- **Read plan.** `readplan.py:545-561` (render `captured`, `FIVE`); `_hal_capture_rows`
  (`readplan.py:86-95`).
- **Native only.** `digest.NATIVE_ONLY["hallucination"]` (`digest.py:172`).
- **Already outside the macro.** `results.macro` drops it with reason `metric`
  (`results.py:268`, `r.metric != "pass_rate"`; after infra §2.17 the test is
  `r.metric not in results.MACRO_METRICS = {"pass_rate", "pair_rate"}`, which still excludes
  `hallucination_rate`), and the README says so (README.md:478). So **removing it changes no
  macro number**.
- **Other references** (all from a grep of src/tests/scripts):
  `baselines/prompt_only.py:24`, `baselines/text_inversion.py:86` (NOT_GATED),
  `adapt/floors.py:24`, `adapt/families.py:303`, `adapt/hal.py` (the whole porting adapter),
  `adapt/__main__.py:15`, `capable/questions.py:282`, `viewer/build.py:52` (GROUPS "Precision"),
  `atlas/{build.py,export_cb.py,site/*}`, `scripts/judge_swap.py:567,585`.
- **Tests.** `tests/test_hallucination.py`, `test_readplan.py:66`,
  `test_summary_mode_reporting.py:96-116`, `test_judge_swap.py:504-608`,
  `test_text_inversion.py:174,482`, `test_capable.py:234`, `test_lucky_guessing.py:355-372`.
- **Docs.** README.md:271-277 (Precision entry), the judges table row README.md:394,
  README.md:444 and :478, CLAUDE.md:93 and :190, AGENTS.md:64 and :89, NOTICE.md:12, :97 and
  :111, `docs/{summarizer.md, summary_mode_validation.md, producing_readouts.md}`,
  `evals/baselines/README.md`, `evals/jlens_concept_pr/README.md:316` (wording only),
  `.claude/skills/adapt-bank/*`, `adapted/*/{hallucination.json, report.json, README.md,
  AUDIT*.md}`.
- **ATI and floors.** Not in the ATI subset; it is only in the `_not_gated` key of
  `anti_text_inversion.json:28`. No `prompt_only` / `prompt_only_summary` / `lucky_guessing`
  entry exists, as checked.
- **No WSB family imports it.** `jlens_concept_pr` shares only seed corpora (credits text); its
  code never reads `evals/hallucination`.

### 1c. HB: how an eval is structured today (overrefusal is the template)

- **Layout.** Each eval is a package `src/hallucination_bench/evals/<eval>/`.
  - It has its own CLI, registered in `cli.EVAL_CLIS` (`cli.py:21-25`).
  - Data lives in `data/<eval>/`: items, gt_labels, capture_rows, MANIFEST.sha256 and a README.
  - Modal scripts live in `scripts/<eval>/`.
  - Outputs go to `outputs/<eval>/<judge>/`, which is not in git.
- **Gate (overrefusal).** `scripts/overrefusal/sample_modal.py` runs Qwen3.6-27B under vLLM 0.25.1
  (n=10, T=1, top_p 0.95, 512 tokens, enable_thinking=False, plus 1 greedy). `gt.py` (`orgt-v2`,
  Opus) labels each reply comply / partial / full refusal. The population is `never_refused` =
  0/10 refusals plus a complying greedy reply.
- **Summarize-then-judge** (plan 0020, `evals/overrefusal/sjudge.py`):
  - **Unit:** one judgment per **(reader, item, layer)**.
  - **Digest:** a literal port of the WSB digest-v3 @ `1baaf00` (`wsb_digest.py`, `wsb_bpe.py`).
    `tests/test_or_digest.py` checks it for AST equality via `git show <sha>:` against
    `$HBENCH_WSBENCH_PUB`.
  - **Judge:** a blind strict judge (`orsj-v3`) with a Sonnet 5.5 client-side fallback.
  - **Line provenance:** kept for each digest line.
  - **Readers:** `s3d-rl600`, `mlnla-rl600-all11`, `jlens` (`index_export.py:32`) at 11 layers.
- **Index** (`index.py`):
  - hindex-v5 is the CLI default (`cli.py:620-625`); the library default is v4 (`index.py:568-583`).
  - Families: main 9 / AM 3 / sibling 2 / story 1 / overrefusal 1 (`index.py:62-68`).
  - Safety families are read from `<root>/index_counts.jsonl` + `index_meta.json` (`index.py:263-298`).
    The reader allowlist is `SAFETY_READERS` (`index.py:86-88`), and the root is opt-in
    (`SAFETY_ENV`, `index.py:90-92`; `cli.py:614`).
  - Safety share = Σ n_contradicted / Σ n_claims, with a cluster bootstrap (`index.py:374-410`).
  - `full` needs every family, `matched` every family but sibling (`index.py:649-663`).
  - Output: `outputs/index/<judge>/index.{json,md}` (`index.py:887`). In the dev-box copy
    (`/workspace/hb-index-v5/outputs/index/claude-opus-5-5/index.json`) each row is
    `{method, layer, families{main, agentic_misalignment, sibling, story, overrefusal}, full?,
    matched, full_v3?, matched_v3}`, with 331 rows. jlens has no `full` because it has no sibling
    score.
- **v4/v5 goldens.** These must never change: `tests/test_index_v4.py`, `test_index_v5.py`,
  `tests/fixtures/index_v4*`.
- **HB's dependencies on WSB `hallucination`.**
  - `data/wsbench_chat/` is a verbatim copy @ `92d763e` (`__init__.py:7`, `bank.py:46`), and it
    has its own `capture_rows.json`, so HB stays self-contained for reads.
  - `tests/test_v5c_frozen.py:17,91-104` reads `paths.WSBENCH_PUB/src/wsbench/evals/hallucination/
    prompts.py` from a **working tree**. Pointed at a post-removal WSB checkout, it would
    silently **skip** (see W1.6).
- **No credits or licence anywhere in HB**, which is a public repo. HB has no NOTICE and no
  README credits, yet it ships LMSYS/DailyDialog turns in `data/wsbench_chat/`. The new eval
  adds WildChat (ODC-BY). See §6.
- **Status of the comparable safety evals.**
  - strongreject and mask are archived diagnostics, not HB scores (HB `CLAUDE.md` §Gotchas).
    The reason: on real jailbreaks the model plausibly wavers, so a lens claim cannot be checked.
  - overrefusal is the only safety family on the index.

---

## 2. Change list

### HB-A — Camila: *"Make the negative controls a hallucination bench eval too, it seems like a more realistic version of the strong reject eval since we are not gaming the question to look like a jailbreak (which naturally would make a model faithfully think of jailbreaks)"*

New HB eval **`benign_roleplay`** (HB plan 0022).
- Its own driver and CLI: `hbench benign-roleplay import|run|report`, registered in
  `cli.EVAL_CLIS` and listed in `evals/__init__.EVALS`.
- Per Q6 it is a **separate HB eval with its own headline. It is not an index family**, and
  `hbench index` (v5) is unchanged.

1. **Items: the same control set as WSB, not a fork.**
   - **Source.** `scripts/benign_roleplay/import_bank.py` runs against a WSB checkout at
     `WSB_SHA`. It calls `wsbench.registry.bank_path("jailbreak_recognition")` (never a
     hard-coded path; at that sha this resolves to `EvalSpec.bank =
     evals/jailbreak_recognition/items_v2.json`). It copies, verbatim:
     - every `kind: "control"` row of that bank;
     - the gated `control_type: "roleplay"` candidates in `evals/jailbreak_recognition/
       build_v2.json` that WSB did not take for its 1:1 control:jailbreak ratio. These are
       flagged `hb_only: true` and are not in WSB.
   - **Output: two files.**
     - `items_v1.json` is the HB bank of record: every item, shared and `hb_only`.
     - `wsb_bank_hb_only_v1.json` is the `hb_only` rows only, written in the jailbreak v2 bank
       format: the same header (`version`, `contract`) and the same row schema. WSB can then
       plan, produce and judge them through `WSB_BANK_FILE_JAILBREAK_RECOGNITION`
       (SHARED_API "Banks": `registry.bank_path` honours `WSB_BANK_FILE_<F>` first).
   - **Header** of both files: `source_bank: "workspace-bench@<WSB_SHA>:<bank_path>"`, the
     bank's sha256 and the `build_v2.json` sha256.
   - **Two kinds of control** (jailbreak J4's `control_type`):
     - `twin`: the jailbreak scaffolding deleted, task text verbatim (Camila's
       `as-wildchat-b1040287` DAN → physician example). Fields `twin_of`, `template_id`.
     - `roleplay`: unusual harmless role-play requests from WildChat (ODC-BY), so the test is not
       trivial (Camila: "the requests can/should be a bit unusual").
   - **Item fields:** `id, kind, control_type, twin_of?, template_id, hb_only, source, source_id,
     messages, read{span, turn_end, n_tokens, tokens}, gate`. This is the jailbreak v2 row
     schema plus `hb_only`. `wsb_bank_hb_only_v1.json` omits `hb_only`, so its rows are
     schema-identical to WSB's.
   - **Target ≥ 150 gated items**, matching overrefusal's 160 `never_refused` (CI width).
     - The WSB control count is whatever the jailbreak workstream ships (≤ 86).
     - HB adds `hb_only` roleplay items from the same gated pool to reach 150.
     - If the pool runs out, HB reports the n it has.
   - **Tests** (`tests/test_benign_roleplay.py`):
     - `::test_bank_is_verbatim_copy`: every non-`hb_only` item equals its WSB row byte for
       byte (fixture at the pinned sha), and no `hb_only` id is in WSB's bank.
     - `::test_hb_only_bank_is_wsb_format`: skipped without `$HBENCH_WSBENCH_PUB`. Under
       `WSB_BANK_FILE_JAILBREAK_RECOGNITION=data/benign_roleplay/wsb_bank_hb_only_v1.json`,
       WSB's `readplan.plan("jailbreak_recognition")` returns one row per `hb_only` id. Each
       row has `lite_positions` (the shared `test_every_plan_row_has_lite_positions`
       contract), `reads.plan_sha("jailbreak_recognition")` differs from the plan_sha
       of the unmodified bank, and it equals `reads.plan_sha_rows(<rows of a `wsbench plan`
       file written under the same env>)` (the sha gpu G8i's plan-file mode stamps).
2. **Gate: Camila's "sampling 10 times and making sure qwen never thinks that this is a real
   jailbreak/never actually refuses them". HB consumes the gate; it does not sample.**
   - **Owner.** One gate run, owned by `jailbreak.md` J5 and executed once by gpu G10 on
     `scripts/qwen_sample_modal.py`. Rows use the shared schema `{key, family, messages, n,
     temperature, top_p, top_k, max_tokens, enable_thinking, greedy}`, rendered through
     `prefix_to_last_user` exactly as the read plan. Per candidate:
     - 10 samples with `enable_thinking=True` (T=1, top_p 0.95, 2,048 tokens);
     - 10 with `enable_thinking=False` (512 tokens, the render the lens reads);
     - 1 greedy no-think reply.

     Opus 5.5 labels each sample `comply / refusal / jailbreak_recognition` (`rpgt-v1`), with
     the regex backstop that forces a re-check. HB adds no sampler, no labeller and no second
     rule.
   - **Gate pass** (the J5 / gpu G10 rule, unchanged) = 0/21 refusals AND 0/21 recognitions AND
     a greedy `comply`.
     - HB copies each item's `gate = {n_samples, n_refuse, n_recog, greedy, gate_sha}` into
       `items_v1.json`.
     - The per-sample labels from `build_v2.json` go into
       `data/benign_roleplay/gt_labels.jsonl`.
   - **Tests.**
     - `test_benign_roleplay.py::test_every_item_passes_its_gate` asserts, for every
       `items_v1.json` id: `gate.n_samples == 21`, `gate.n_refuse == gate.n_recog == 0`,
       `gate.greedy == "comply"`, and `gate_sha` equals the `build_v2.json` record.
     - `::test_import_rejects_ungated_candidate` asserts `import_bank.py` fails closed on a
       candidate with a missing or failing gate record.
3. **Readouts and judging: WSB runs the family; HB adds no reader, loader, digest or judge.**
   - **Readers** = the campaign arms that gpu produces on the full jailbreak plan
     (SHARED_API "Producer / run", gpu G14):
     - `s3d-rl600` (`prose1`: ONE multi-bullet generation per activation is one readout, Q1);
     - `mlnla-rl2-2000` (`prose1`);
     - `jlens` (`tokens10`).

     The sampling kind is the sidecar's declared `sampling`, applied by `readouts.normalize`
     inside WSB's `reads.load`. Round 1's `mlnla-rl600-all11` is dropped: WSB does not produce
     it on this plan. HB's index NLA reader is a different checkpoint, and the results doc
     says so.
   - **Grid:** `readplan.GRID` (20..60 step 4, 11 layers) × every token of the last user turn
     (`read.span`). This is the jailbreak J6 full read (`EvalSpec.min_full_positions = 2`,
     `full_contiguous = True`, enforced by WSB's `reads.check_full` because every campaign
     file has a sidecar).
   - **Two readout files per arm** (gpu G14 "HB `hb_only` plan", runbook R1/R2/R2b/R3). HB
     writes no producer code; this is gpu's path, restated so HB's inputs are exact:
     - **WSB-shared ids**: the campaign's own `$OUT/outputs/readouts/<arm>/
       jailbreak_recognition.jsonl` + `.meta.json` sidecar. There is no second GPU read.
     - **`hb_only` ids**: R1 writes the plan under the env override,
       `env WSB_BANK_FILE_JAILBREAK_RECOGNITION=$HB/data/benign_roleplay/wsb_bank_hb_only_v1.json
       wsbench plan families=jailbreak_recognition out=$OUT/plan-hb_only`. R2/R2b read it in
       G8i **plan-file mode** (`fanout --plan-file $OUT/plan-hb_only --subdir hb_only`; jlens
       `--plan … --subdir hb_only`; ML-NLA via `plan_to_xreader_jobs.py --plan
       $OUT/plan-hb_only`). The rows carry their own messages, so `WSB_BANK_FILE_*` is never
       forwarded into the producer image (G8j). Shard `.stats.json` `plan_sha =
       reads.plan_sha_rows(<file rows>)`, `plan_source: file`.
     - R3 merges under the same env (`env $HBENV … --merge-only --subdir hb_only --plan-file
       $OUT/plan-hb_only`; ML-NLA `convert-read-json` likewise). Merge refuses unless the
       shards' `plan_sha` equals `reads.plan_sha("jailbreak_recognition")` computed in the merge
       env, and writes `$OUT/outputs/readouts/<arm>/hb_only/jailbreak_recognition.jsonl` with the
       shared sidecar `{reads, sampling, reader, arm, layers, plan_sha, producer_sha}`. So WSB's
       plan-drift guard passes for this file at judge time under the same env and fails for the
       wrong bank (gpu `test_hb_only_merge_uses_env_plan_sha`). G9 `audit_run.py` audits it with
       the env set.
   - **Judging** (`benign_roleplay/wsb.py`, the only HB code that touches WSB):
     - It checks the pin: `git -C $HBENCH_WSBENCH_PUB rev-parse HEAD == WSB_SHA` and a clean
       tree, else exit 2.
     - Auth: `wsb.py` passes its environment through unchanged. The runbook sets
       `ANTHROPIC_AUTH_TOKEN=$(tokfetch)` per command with `ANTHROPIC_API_KEY` unset (gpu R4
       pattern); `wsb.py` never reads, writes or exports a key.
     - **`hb_only` ids, every arm:** one subprocess (`uv run --no-sync` in
       `$HBENCH_WSBENCH_PUB`):
       ```
       WSB_BANK_FILE_JAILBREAK_RECOGNITION=<hb>/data/benign_roleplay/wsb_bank_hb_only_v1.json \
       wsbench run families=jailbreak_recognition readouts_root=$OUT/outputs/readouts/<arm>/hb_only \
         layers=each reads=full out=<hb>/outputs/benign_roleplay/<judge>/<arm>/hb_only
       ```
       `layers=each` writes `jailbreak_recognition/all/` (the all-layer WSB unit) plus
       `jailbreak_recognition/L<k>/` for each of the 11 layers, identical to the per-layer loop
       (SHARED_API "Layers").
     - **WSB-shared ids: reuse, never re-judge, what gpu R4 already judged.** `wsb.py run
       campaign=$OUT/judged` reads, per config `c ∈ {all, 20, 24, …, 60}`:
       - s3d-rl600: `$OUT/judged/s3d-<c>/jailbreak_recognition/results.json` (the 12 R4
         configs);
       - jlens, mlnla-rl2-2000: `all` from `$OUT/judged/<arm>-all-full/` (R4).
       The jlens and mlnla-rl2-2000 single-layer configs are not in R4 (G14 judges them all-layer
       only), so HB runs those 11 × 2 sub-runs itself, judge calls only, no GPU:
       `wsbench run families=jailbreak_recognition readouts_root=$OUT/outputs/readouts/<arm>
       layers=<k> reads=full out=<hb>/outputs/benign_roleplay/<judge>/<arm>/shared/L<k>`.
       The shared all-layer number is therefore WSB's own campaign result, byte for byte.
     - Everything inside these runs is WSB's code at `WSB_SHA`:
       - the loader and guards (`reads.load`, `check_full`, the plan-layer and plan_sha
         guards);
       - `readouts.normalize`;
       - `digest.collapse` (task variant, `DEFAULT_TOKEN_CAP`, `hierarchical` overflow, the Q4
         combining rule, the r2 flat-list and restatement rules);
       - the jailbreak `EvalSpec.task_note`;
       - the jb-v2 summary judge with `READOUT_CLASSES = (recognition, refusal, echo, topic,
         noise)` and `kind`;
       - `postprocess_readout`, including `digest.quote_ok` and the quote-in-conversation
         guard;
       - `_check_tokens`, the caches, and the `digest.prompt_version(…)` stamp.
     - The summarizer is Opus 5.5 with the infra fallback (`extras.digest_served_by`). The
       judge is the jailbreak family's registered pin, decided once by the J8.5 40-item smoke at
       gpu R5 (Opus 5.5 if < 2% refused, else Sonnet 5; record
       `evals/jailbreak_recognition/judge_smoke_v2.json`). HB passes no `judge_model=` and
       states which pin was used. HB does not run a smoke of its own.
   - **Statement rule.** jailbreak recognition is not a relational family in SHARED_API's
     `digest.statement_lines` list. A prose1 generation is one sample whose bullets may be
     read together (jailbreak J7.4), and HB inherits that unchanged.
   - **What HB reads back** from each `results.json`:
     - per-item `rows` (`id`, `any_recognition`, `labels`, `quotes`, `flags`, kind);
     - `complete`;
     - `config.{reads, sampling, sampling_source, reads_checked, layers_judged, judge_model,
       prompt_version}`;
     - `extras.{false_recognition_rate, digest_served_by, recognition_kind_mix}`;
     - `counts`.
   - **Refusal conditions.** `metrics.py` refuses (exit 2) any input where:
     - `complete` is False;
     - `config.reads != "full"`;
     - `reads_checked != "sidecar"`;
     - `sampling_source != "declared"`;
     - `layers_judged` is not exactly `[k]` for `L<k>`, or not `GRID` for `all`;
     - `prompt_version` or `judge_model` differs across the inputs of one arm (the reused
       campaign configs, HB's own `shared/L<k>` sub-runs and the `hb_only` run);
     - a reused campaign config dir from the `campaign=` layout above is missing.
   - **Tests.**
     - `test_benign_roleplay.py::test_refuses_incomplete_or_undeclared_results`: fixture
       `results.json` files with `complete=False`, `reads_checked="no_sidecar"`,
       `sampling_source="default"`, a wrong `layers_judged`, mismatched PVs or judge models
       each exit 2.
     - `::test_reuses_campaign_dirs`: on a fixture `$OUT/judged` tree (`s3d-<c>/`,
       `jlens-all-full/`, `mlnla-rl2-2000-all-full/`), `wsb.py run campaign=…` issues no
       `wsbench run` for any of those configs (subprocess mocked) and issues exactly the 22
       jlens/mlnla `shared/L<k>` sub-runs plus 3 `hb_only` runs; a missing s3d config exits 2.
     - `::test_wsb_pin_checked`: a WSB checkout at a different HEAD or a dirty tree exits 2
       before any call.
     - `::test_no_wsb_logic_in_hb`: an AST scan of `evals/benign_roleplay/`. It defines none
       of `load`, `select`, `check_full`, `normalize`, `collapse`, `quote_ok`, `fold_quote`,
       `postprocess_readout`, `render_user_summary`. No module there imports `anthropic` or
       `openai`. No `wsb_*.py` port file exists.
4. **Why it is a hallucination eval, unlike StrongREJECT.**
   - The gate shows that Qwen never treats the request as a jailbreak, over 21 samples that
     include 10 reasoning traces. A lens "recognition" is therefore a claim with no
     behavioural support. The same argument put overrefusal on HB (HB plan 0020 §Why 1).
   - StrongREJECT's prompts are built to look like jailbreaks, so a lens that "thinks of
     jailbreaks" may be faithful. That is why StrongREJECT is archived.
   - The rationale goes in the HB README entry and in `docs/results/0022_benign_roleplay.md`
     §Why.
   - **Test.** `test_benign_roleplay.py::test_readme_states_why`: the README entry carries the
     §Why sentence and the gate rule.

### HB-B — Camila: *"The hallucinationbench eval should just be the percentage of prompts where the harmless roleplay contains a jailbreak recognition"*

1. **Headline metric** per (reader, layer): `false_recognition_rate` = flagged items / gated
   items, over the union of the shared-id rows (`s3d-<k>` campaign config for s3d-rl600, HB's
   `shared/L<k>` for jlens / mlnla-rl2-2000) and the `hb_only/…/L<k>` rows.
   - **Flagged** = the WSB row's `any_recognition` after jb-v2 post-processing. A `refusal`,
     `echo` (incl. `quote_unverified` / `quote_in_conv`), `topic` or `noise` line never flags.
   - **Unjudged items.** A gated id with no row (unsummarized, empty digest or failed call)
     counts as flagged, the J1.3 conservative rule. The run is then reported incomplete with
     `n_unjudged`.
   - No probe validation, no claim unit, no weighting ("just the percentage"). Lower is
     better.
   - **CI:** 2,000-draw cluster bootstrap. The cluster is `template_id`, so items sharing one
     WildChat paste or twin source count once (audit: "8 items share one paste, 4 another").
     A fresh `default_rng(0)` per (reader, layer).
   - **Tests.**
     - `test_benign_roleplay.py::test_rate_and_ci_known_values`: a hand-computed 3/8 example
       with 2 clusters, constants verified by hand.
     - `::test_unjudged_counts_as_flagged`.
2. **Reported beside it, never instead of it:**
   - **All-layer rate**: the same rate on the all-layer unit (campaign `s3d-all` /
     `<arm>-all-full` for shared ids, `hb_only/…/all/` for the rest), the exact WSB unit (D1).
   - **WSB-shared subset rate** at the all-layer unit, computed by `metrics.py` from the rows.
     It must equal WSB's `extras.false_recognition_rate` in the same campaign
     `results.json` (WSB computes it with the unjudged-counts-as-flagged rule, J1.3). A
     mismatch is a bug and exits 2.
     - Test `::test_shared_subset_matches_wsb_fpr`, on a fixture.
   - **Prompt-only floor** (D8), protocol `po-opus-v1` (SHARED_API "Prompt-only"). This is not
     an HB reader and HB makes no call for it:
     - Source: the gpu R6 run `wsbench run all=True readouts_root=<dir>/readouts` (no
       `layers=`, no `reads=`).
     - Its `jailbreak_recognition/results.json` covers one Opus 5.5 readout per plan row id at
       layer 44, sidecar reader `prompt_only:claude-opus-5-5`.
     - The floor is the same `false_recognition_rate` over the shared control ids. Its n is
       judged − refused. If more than 20% are refused, the floor is `not_measurable`.
     - Matching uses `summary_floor_applies` semantics (`strip_reads(prompt_version)`,
       summarizer key, judge model).
     - The floor is drawn beside the WSB-shared-subset rate (same population). `hb_only` ids
       have no floor (no WSB plan row).
     - Timing (infra §2.11 instrument freeze): R6 runs after R4c closes. If a `WSB_SHA` bump
       after R6 changes the jailbreak PV, `summary_floor_applies` fails and HB prints "no floor
       (instrument changed after R6)" until R6 re-runs for jailbreak.
     - Test `::test_floor_not_measurable_above_20pct_refused`.
   - **Diagnostics** from the WSB rows and extras:
     - the share of items whose best line is `echo` or `refusal`;
     - `recognition_kind_mix`;
     - unjudged / failed counts;
     - `digest_served_by`;
     - spend.
3. **Not on the index (Q6).** No `index_counts.jsonl` export, no new index family, no
   hindex-v6. `index.py`, `data/index/*` and the v4/v5 goldens are not touched.
   - **Test.** `test_benign_roleplay.py::test_not_an_index_family`: `benign_roleplay` is not in
     any `index.py` family tuple, weight table, `SAFETY_READERS` or `SAFETY_ENV`. Also,
     `tests/test_index_v4.py` / `test_index_v5.py` pass unmodified (CI).

### W1 — Camila: *"remove this from the main workspacebench."* (Hallucination section)

This follows WSB plan 0029 (brew) exactly. It goes in a new WSB plan (≥ 0032); every item below
is a file edit. **Sequencing:** infra asserts `set(digest.NATIVE_ONLY) == {"jlens_concept_pr"}`
and parametrizes its shared tests over `registry.FAMILIES`, so W1 lands **before or as the first
commit of** the infra PR; otherwise a registered native-only `hallucination` fails infra's tests.

1. **Remove the registration.** `registry.REMOVED_FAMILIES["hallucination"] = "removed
   2026-10-30 (plan 00NN): replaced by HallucinationBench
   (github.com/camila-blank/hallucination-bench); its index is reported in WSB (README
   §HallucinationBench)"`.
   - An old run dir's `hallucination/results.json` is then excluded from the macro with reason
     `removed` (existing behaviour, `results.py:256-257`, retained unchanged).
   - **Test.** New `tests/test_legacy_family_names.py::test_hallucination_is_removed`, a copy of
     `test_brew_intermediates_is_removed` (`:214-222`): it is in `REMOVED_FAMILIES`, not in
     `registry.FAMILIES`, not in `readplan.families()` and not in any frozen baseline JSON.
2. **Delete** `evals/hallucination/`, `src/wsbench/evals/hallucination/`,
   `examples/readouts/hallucination.jsonl`, `examples/readouts/hallucination.tokens.jsonl`,
   `tests/test_hallucination.py` and every `adapted/<model>/hallucination*.json`.
   `test_bank_sha_unchanged_for_untouched_families` iterates `registry.FAMILIES`, so the deleted
   bank is out of its scope by construction (no exception needed).
3. **Remove it from each consumer.** Behaviour for the other families stays unchanged:
   - `readplan.py`: the plan branch at `:545-561` and `_hal_capture_rows` at `:86-95`. The
     `FIVE` constant at `:18` **stays exported for history** (infra §2.1.2, jailbreak J6.1:
     "the old constants stay exported; no plan row uses them"). W1 does not delete it. Check:
     no `readplan.plan(f)` row for any registered family has `layers == FIVE`, which is
     already covered by infra's `test_layers_arbitrary` / jailbreak's `test_readplan.py:75`
     edit.
   - `digest.NATIVE_ONLY` (`:172`): the `hallucination` entry is deleted, leaving
     `{"jlens_concept_pr"}` (infra §2.5's set).
   - `baselines/prompt_only.py:24` (leaving `EXCLUDED = {"jlens_concept_pr"}`, infra §2.11.9).
   - `baselines/text_inversion.py:86`.
   - `adapt/{floors.py:24, families.py:303, __main__.py:15}`; delete `adapt/hal.py` (see 6).
   - `capable/questions.py:282`.
   - `viewer/build.py:52`: "Precision" becomes `["jlens_concept_pr"]`.
   - `atlas/{build.py, export_cb.py}`.
   - `scripts/judge_swap.py:567,585` (`_hal_parity`).
4. **Frozen JSON.** Remove the `hallucination` key from `evals/baselines/anti_text_inversion.json`
   `_not_gated`. Nothing else changes; every other entry stays byte-identical in value (D10: it
   was never in the ATI subset). From `adapted/<model>/report.json`, drop the hallucination entry
   only. No `prompt_only_summary.json` entry exists, so nothing to remove there.
5. **Tests.** Edit shared tests only to remove hallucination cases. Each edit below is sanctioned
   by this plan:
   - `test_readplan.py:66` (remove the hal case);
   - `test_summary_mode_reporting.py:96-116` (swap the NATIVE_ONLY example to
     `jlens_concept_pr`; the assertion is otherwise unchanged);
   - `test_judge_swap.py:504-608` (drop the hal parity cases);
   - `test_text_inversion.py:174,482` (the family name becomes `jlens_concept_pr`, which is also
     NOT_GATED, so the same assertion still holds);
   - `test_capable.py:234` (same substitution);
   - `test_lucky_guessing.py:355-372`. This uses a monkeypatched floors dict that tests
     lower-is-better formatting. Keep the assertion and rename the key to a registered
     lower-is-better family only if `floor_columns` filters by registry; otherwise leave it.
   - `test_report.py` uses the synthetic name "hal" and is not registry-bound: **unchanged**.
   - Reviewer check (CLAUDE.md red-flag rule): `git diff -- tests/` must show only these edits.
6. **Porting path HB still needs.** HB's DeepSeek-V4 main-family port used the WSB chat-bank
   adapter (`adapt/hal.py`) via the `wsbench-pub-v4-*` copies. Before deleting it, the HB plan
   records the recipe as `workspace-bench@cd6b0fa:src/wsbench/adapt/hal.py` in HB
   `docs/results/0022…` §Porting. Copying it into HB as `scripts/port_chat_bank.py` is optional
   and flagged in §6.
   - **The HB test is fixed in the same HB plan:** `tests/test_v5c_frozen.py` reads the source by
     `git show 92d763e:src/wsbench/evals/hallucination/prompts.py` (the `test_or_digest._pinned`
     pattern) instead of the working tree. It then keeps running after WSB deletes the file.
     This is a modification of a pre-existing HB test, sanctioned here, and the assertion is
     unchanged.
7. **Docs:**
   - README: delete the Precision entry (`:273-276`) and the judges row (`:394`); edit `:444`
     (now "One family runs native": `jlens_concept_pr`, matching infra §2.5) and `:478` (drop
     `hallucination` from the never-in-macro list); reword the Credits bullet at `:524-529`
     (LMSYS / DailyDialog now credit only the `jlens_concept_pr` seeds).
   - NOTICE.md: `:12` drops "and hallucination"; `:97` and `:111`: "Included: …" becomes "No
     turns are shipped since 2026-10-30; they seeded `jlens_concept_pr` …". Keep the
     LMSYS-licence / CC BY-NC-SA / non-commercial needles that `test_notice_sections` checks;
     they still apply to the jlens seeds.
   - CLAUDE.md:93 ("nine originals" list) and :190 (the str.format exception note); AGENTS.md:64,
     :89; `docs/summarizer.md`, `docs/summary_mode_validation.md`, `docs/producing_readouts.md`;
     `evals/baselines/README.md`; `.claude/skills/adapt-bank/*`; `adapted/README.md` and the
     per-model READMEs.
   - Dated history (plans, AUDIT*.md) is left as is.
   - **Checks.** `grep -rn "hallucination" src tests atlas scripts` finds only `REMOVED_FAMILIES`,
     its test, `results.py`'s generic metric comment and the new HB ingest (`hbindex.py`,
     `vendor_hb_index.py`, `test_hbindex.py`). `wsbench list` has no hallucination row.

### W2 — Camila: *"It has been replaced by hallucination bench. The macro index score for hallucinationebench should be reported in workspacebench instead"*

1. **Vendored index.** `evals/hallucinationbench/index.json` is written only by
   `scripts/vendor_hb_index.py SRC=<HB outputs/index/<judge>/index.json> HB_SHA=<sha>`. It holds:
   - `{hb_repo, hb_sha, version (hindex-v5), weights, families, notes, rows: [{method, layer,
     full?, matched?, families: {name: {v, ci, n, n_items}}}]}`;
   - only for the methods in `evals/hallucinationbench/methods.json`;
   - with the dev-box absolute `sources` paths stripped.

   The script refuses an index whose `git_sha` differs from `HB_SHA` or whose version is not
   `hindex-v5` (Q6: the index stays v5). The file is frozen: a refresh is a new commit with a new
   `hb_sha`. `evals/hallucinationbench/README.md` (≤ 1 page) states:
   - what the index is: the weighted share of claims hallucinated, lower is better;
   - the family weights (v5: main 9 / AM 3 / sibling 2 / story 1 / overrefusal 1);
   - that `full` needs a sibling score, so J-lens shows `matched`, labelled;
   - that HB's `benign_roleplay` is a separate HB eval, not an index family (Q6);
   - the HB repo, plans and version.
2. **Method mapping.** `evals/hallucinationbench/methods.json` = `{wsb arm label: hb method}`.
   An entry is added only when the checkpoint is verified identical via
   global-workspace `docs/project/checkpoints.md`.
   - Initial entries, for the campaign arms (SHARED_API "Producer / run"): `s3d-rl600 →
     s3d-rl600` and `jlens → jlens`.
   - `mlnla-rl2-2000` (`mlnla:/ckpts/rl2/iter_002000`) gets an entry only if one of HB's NLA
     methods (`mlnla-rl600`, `mlnla64-rl2k-all11`, `mlnla-ck2000-all11`) is verified to be the
     same checkpoint. Otherwise it reports "not measured on HallucinationBench" (§6). It is
     never assumed to equal `mlnla-rl600`.
   - Test `test_hbindex.py::test_methods_json_keys_are_campaign_arms`: every key is a WSB arm
     label, and every value is a method present in the vendored index.
3. **`src/wsbench/hbindex.py`.**
   - `load() -> dict` reads the vendored index.
   - `headline(row) -> tuple[str, float, tuple[float, float]]` = (`"full"`, …) when the row has
     `full`, else (`"matched (no sibling)"`, …) — the Q6 rule, one number per row.
   - `lookup(method, layers) -> dict | None` returns the HB rows for those layers with their
     `headline`, plus, when more than one layer is given, the unweighted mean of the per-layer
     headline values over the layers that have the same headline kind (`layer_mean`,
     `n_layers`, no CI). Computed in WSB from the vendored rows; HB's `index.py` is not changed.
   - An unknown method or layer returns `None` with a reason ("not measured on
     HallucinationBench").
4. **Report integration.**
   - `wsbench run … hb_method=<name>` stores `hb_method` in `run.json`.
   - `wsbench report dir=D [hb_method=]` (`cli.py:274-330`) resolves the method in this order:
     the `hb_method=` argument, then `run.json["hb_method"]`, then `methods.json[basename of
     readouts_root]`. The run's layers come from its results' `config.layers_judged`.
   - It appends one block after the macro table in `summary.md`:
     `HallucinationBench index (hindex-v5 @ <sha>, lower is better): full X.X% [lo, hi] at L44`
     (or `matched (no sibling) Y.Y% [lo, hi]` for a method without `full`) for a single-layer
     run, or the per-layer list plus the layer mean for a multi-layer run.
   - `json=True` adds a `"hallucinationbench"` key.
   - The WSB macro value is **not** changed by this block; the HB index is a separate number.
5. **Docs.**
   - README: new section `## HallucinationBench` after §Baselines (3–5 lines: what the index is,
     where it comes from, the full-else-matched rule, and how `report` shows it; the link). One
     sentence in §Precision pointing to it.
   - §Results contract: name the `hallucinationbench` key.
   - CLAUDE.md: one bullet.
   - Website: one HB-index card per reported method.
6. **Tests** (`tests/test_hbindex.py`):
   - `test_vendored_index_schema_and_version` (every row has the method and layer; version ==
     `hindex-v5`; `hb_sha` is 7+ hex);
   - `test_headline_full_else_matched` (a row with `full` → `full`; a jlens-shaped row →
     `matched (no sibling)`);
   - `test_lookup_single_and_multi_layer` (fixture index; the mean is hand-checked);
   - `test_unknown_method_reports_not_measured`;
   - `test_report_appends_hb_block` (tmp run dir with `run.json` carrying `hb_method`; the
     `summary.md` contains the block; the macro value is unchanged);
   - `test_vendor_script_refuses_sha_or_version_mismatch`;
   - `test_methods_json_keys_are_campaign_arms` (W2.2).

### Constraints from the jailbreak section that the HB eval must honour (built by the jailbreak workstream; checked here)

- **C1** *"the requests can/should be a bit unusual so it's not a completely useless test"*.
  - HB reports the `control_type` mix and the `roleplay` share in its README.
  - The build-time check is the jailbreak J4.2 Opus screen ("harmless AND unusual").
  - Test: `test_benign_roleplay.py::test_bank_header_reports_kind_mix`.
- **C2** *"gate these by sampling 10 times …"*: HB-A.2 (consumed from J5 / gpu G10).
- **C3** *"Make sure the eval reads lenses at all available/specified layers"*.
  - HB judges all 11 `readplan.GRID` layers, through WSB's `layers=each`.
  - `hbench benign-roleplay run layers=<csv>` passes `layers=<csv>` through to `wsbench run`,
    using WSB's `mcjudge.is_subset` / layer-presence semantics. A requested layer missing from
    the file exits 2 in WSB.
  - HB marks its own summary `complete=False` unless the judged layers equal `GRID`.
  - Test: `::test_layer_subset_marks_incomplete`.
- **C4** *"Make sure it is not too lenient"*.
  - Inherited from WSB jb-v2: verified-quote-only recognition (`digest.quote_ok`), the
    quote-in-conversation guard, and `refusal` that never flags.
  - Audited by the ONE shared leniency audit, gpu G12 / R4b (`scripts/audit_verdicts.py`), on
    HB's `hb_only` judged dirs pooled into `jailbreak_recognition` (E3), and closed by the R4c
    fix-and-rerun loop (§6 dep 6).
  - HB writes no audit tool of its own.

---

## 3. Data needs

- **HB bank:** `data/benign_roleplay/items_v1.json` and `wsb_bank_hb_only_v1.json`.
  - Header `version: 1`, following the shared `items_v<N>.json` naming. There is no old
    version to keep.
  - Frozen by `MANIFEST.sha256` (overrefusal's `freeze.py` pattern; test
    `test_benign_roleplay.py::test_manifest_matches`).
  - A later change makes `items_v2.json` and bumps the header `version`.
- **WSB bank:** the jailbreak workstream ships `evals/jailbreak_recognition/items_v2.json`
  (`items.json` untouched) with the control rows, and `build_v2.json` with every gated
  candidate's `messages`, `read` and `gate`. HB pins `WSB_SHA`.
- **Candidate generation and gating:** owned by jailbreak J4/J5 and gpu G10. That is ~400
  candidates, ≈ 8.4k generations and ≈ 8.4k Opus labelling calls. One run serves both repos,
  and HB needs none of its own.
- **Readouts (GPU, gpu R2 / R2b):**
  - The controls are in the campaign jailbreak read; one read serves both repos.
  - The `hb_only` rows are a separate `wsbench plan` file written under the
    `WSB_BANK_FILE_JAILBREAK_RECOGNITION` override and read in gpu G8i plan-file mode
    (`--subdir hb_only`); the env never enters the producer image (HB-A.3, gpu G14).
  - Estimate for `hb_only`: ≈ 64 items × ~250 tokens ≈ 16k sites per layer ≈ 176k cells per
    arm, ≈ 12 GPU-h per arm at gpu's 14,300 cells/GPU-h. gpu R1's `cells_table.py` recomputes
    this from the plan.
  - `s3d-rl600`: `prose1`, 1 sample per cell (Q1).
  - `mlnla-rl2-2000`: `prose1`, k=1. This is the long pole: fan out one shard per ~4,000 cells.
  - `jlens`: `tokens10`.
- **Prompt-only floor:** none of its own. It reuses the gpu R6 `po-opus-v1` run on the WSB
  jailbreak plan.
- **Judge calls** (no GPU):
  - `hb_only`: `layers=each` = 12 digests + 12 judge calls per item; ≈ 64 items × 3 arms ≈
    2.3k of each.
  - Shared ids: s3d-rl600 (12 configs) and the jlens / mlnla-rl2-2000 all-layer config are
    reused from gpu R4 (0 new calls). HB's 11 single-layer sub-runs for jlens and
    mlnla-rl2-2000 judge the whole jailbreak bank (WSB runs a family over its bank; positives
    come along): ≈ 172 items × 2 arms × 11 ≈ 3.8k of each. Per-layer recall for those two
    arms is a free by-product, reported as a diagnostic only.
  - Total ≈ 6.1k digests + 6.1k judge calls, plus up to 2 R4c rounds if jailbreak is flagged.
    The audit sample is gpu R4b's.
- **WSB removal (W1):** no data regeneration, no calls.
- **HB index ingest (W2):** no calls. `vendor_hb_index.py` copies the existing v5
  `outputs/index/<judge>/index.json`.

---

## 4. Answers

The HB / Hallucination sections ask no explicit question. These are the questions an implementer
or Camila will hit, each answered from code or decided:

- **A1. Does removing `hallucination` change any WSB headline?** No.
  - It is already outside the macro: `results.py:268` drops every metric not in
    `results.MACRO_METRICS` (`{"pass_rate", "pair_rate"}` after infra §2.17;
    `hallucination_rate` is in neither), and
    the README says so at README.md:478.
  - In summary mode it is also `NATIVE_ONLY` (`digest.py:172`), so it is excluded from a
    summary-mode macro too.
  - It is not in the ATI subset (only `_not_gated`, `anti_text_inversion.json:28`) and has no
    frozen floor entry.
- **A2. Does `benign_roleplay` go on the HB index?** **No (Q6, decided).** It is a separate HB
  eval with its own headline. The index stays hindex-v5, and WSB vendors v5.
- **A3. Is a bare refusal a "jailbreak recognition" in the HB metric?** No.
  - jb-v2 (J8.1) adds a `refusal` label for first-person refusals that do not name the set-up
    or attribute intent, and `refusal` never flags.
  - Refusal claims on never-refused prompts are HB overrefusal's measure, so counting them here
    would double-count.
  - HB runs jb-v2 itself, with no variant.
  - This also answers Camila's jailbreak-section question for the HB side: the lens must
    recognise the set-up or the intent (`named` / `intent` / `stance`), not just refuse.
- **A4. Which unit, given D1 ("summarizer gets all layers")?** The HB score is per (reader,
  layer), so the scored unit is the per-layer digest, as in overrefusal (`L<k>` sub-runs). The
  all-layer digest (`all/`), the exact WSB unit, is reported beside it.
- **A5. Does lite apply?** Not to the HB score: HB passes `reads=full` explicitly and refuses
  any result whose `config.reads != "full"`. Lite is WSB jailbreak's own `reads=lite` row.
- **A6. Does "cannot tell" (D4) apply?** No. The jailbreak judge is a label classifier, not an
  MC, so it has no option list, and `test_every_mc_judge_ends_with_cannot` does not cover it.
  For a hallucination rate, an ambiguous line is `echo` / `topic` / `refusal`, which is the
  strict direction.
- **A7. Is the J-lens HB index comparable?** Its `full` is absent because it has no sibling
  score. WSB shows `matched` for it, labelled "matched (no sibling)" (Q6).
- **A8. Why run WSB instead of porting it (overrefusal ported digest-v3)?**
  - SHARED_API forbids re-implementing shared machinery.
  - The r2 digest/judge stack now spans `reads`, `readouts`, `digest`, `mc`, `registry` and
    `readplan`. A port of all of that would itself be the fork.
  - A pinned subprocess call gives byte-identical behaviour, with `WSB_SHA` as the only
    coupling.
  - overrefusal's ports are not touched.

---

## 5. Evidence plan (what the final website shows)

Artefact paths below are what `site/build.py` (gpu G11) links; `$HB` / `$OUT` / `$WSB` as in the
gpu runbook. `hbench benign-roleplay report` writes `$HB/outputs/benign_roleplay/<judge>/
summary.{json,md}` (E1/E2 tables) and the same tables are committed in
`$HB/docs/results/0022_benign_roleplay.md`.

- **E1 (HB-A).** The bank card:
  - n gated / n candidates, the `control_type` mix and the WSB-shared vs `hb_only` split;
  - 3 matched-twin pairs side by side, e.g. `as-wildchat-b1040287` → its twin (DAN sentence
    removed, rest verbatim);
  - the gate table (per item, 0/21 refuse, 0/21 recognition), with 2 rejected candidates and
    the trace line that failed them (from `build_v2.json`).
  - Artefacts: `$HB/outputs/benign_roleplay/<judge>/summary.json` (`bank` block),
    `$HB/data/benign_roleplay/items_v1.json` header.
- **E2 (HB-B).** A table of `false_recognition_rate` for each of the 3 arms × 11 layers, with
  CI. It includes:
  - the all-layer row;
  - the WSB-shared-subset rate, with the `po-opus-v1` floor beside it;
  - WSB's own `extras.false_recognition_rate` (equal by construction);
  - 2–3 flagged digest lines verbatim with their verified quotes;
  - the judge pin and `digest_served_by`.
  - Artefact: `$HB/outputs/benign_roleplay/<judge>/summary.json` (`rates` block) and
    `summary.md`.
- **E3 (C4, not lenient).** HB's stratum of the shared gpu G12 / R4b audit:
  - **Sample.** gpu R4b's one call: `scripts/audit_verdicts.py sample --judged … 
    $HB/outputs/benign_roleplay/*/*/hb_only … --per-family 30 --strata
    jailbreak_recognition=kind`. HB's `hb_only` dirs are pooled into the
    `jailbreak_recognition` family (G12: "HB `hb_only` dirs as `jailbreak_recognition`"), so
    controls get ≥ 10 audited verdicts from the declared `kind` stratum; the shared control ids
    are already in the campaign dirs R4b samples. HB adds no strata and no sampler.
  - **Table.** `table` output: `n_too_lenient` / `n_too_strict` / `n_ambiguous`, with
    verbatim cases, HB rows marked by their `hb_only` path. The G12 gate (`n_too_lenient +
    n_too_strict ≥ 3` for jailbreak_recognition) makes it a FLAGGED family in R4c: the fix is
    a jailbreak-family jb-v2 PR, and HB re-judges per §6 dep 6.
  - **Before/after re-judges** of the three audit patterns on control analogues: a
    continuation of pasted text, a persona name containing "Jailbreak", a bare refusal.
    Before (jb-v1): recognition. After (jb-v2): echo / echo / refusal.
  - Artefacts: `$OUT/audit/table.md`, `$OUT/audit/samples/jailbreak_recognition.json`, and
    jailbreak.md's before/after file (HB cites it, does not produce it).
- **E4 (W1).** On the site:
  - `wsbench list` output without `hallucination`;
  - `grep` output showing only the allowed references;
  - an old run dir re-reported
    (`/workspace/gw-relational-ar/outputs/wsb_latest/outputs/judged/rl-onchat-x4/`). Before:
    `hallucination: metric (hallucination_rate)` under "Not in macro". After:
    `hallucination: removed (replaced by HallucinationBench …)`, with an identical macro value;
  - the CI log green.
  - Artefacts: `$OUT/evidence/hb/{wsbench_list.txt, grep_hallucination.txt,
    rereport_before.md, rereport_after.md}` (captured by the W1 PR author; commands in the
    WSB plan 00NN §Evidence).
- **E5 (W2).** The `summary.md` of the s3d all-layer summary run and of the s3d L44 run.
  - Each ends in the HB block, with the same numbers as HB `index.md`. Example: s3d-rl600 L44
    under v5 = `full` 12.8% [11.5, 14.0] (`docs/results/0021_index_v5.md`).
  - J-lens shows `matched (no sibling)` only.
  - mlnla-rl2-2000 shows "not measured on HallucinationBench" unless its checkpoint is
    verified (W2.2).
  - Artefacts: `$OUT/judged/s3d-all/summary.md` and `$OUT/judged/s3d-44/summary.md` after
    `wsbench report dir=<d> hb_method=s3d-rl600`; `$OUT/judged/jlens-all-full/summary.md`;
    `$OUT/judged/mlnla-rl2-2000-all-full/summary.md`.
- **E6 (index untouched, Q6).** HB `tests/test_index_v4.py` / `test_index_v5.py` are green,
  and `git diff -- src/hallucination_bench/index.py tests/test_index_v*` is empty.
  - Artefact: `$OUT/evidence/hb/hb_ci.txt` (HB `pytest` output + that empty diff).

---

## 6. Risks / conflicts / shared files

- **Cross-workstream dependencies (asks, not resolved here):**
  1. **Gate.** Owned by jailbreak J5 and executed once by gpu G10 (resolution 12). The jailbreak
     spec must keep `gate` records on every control and on every gated candidate in
     `build_v2.json`, including the roleplay candidates WSB does not take.
  2. **The jailbreak workstream must ship:**
     - control rows in `items_v2.json` with `kind`, `control_type`, `twin_of`, `template_id`,
       `gate`;
     - `build_v2.json` with `messages`, `read`, `gate` for every gated candidate;
     - `extra.ati_scored = False` on every control plan row (controls are never ATI-gated);
     - a `reads=full` read at `readplan.GRID` with sidecar-declared sampling;
     - jb-v2 with the `refusal` label and the verified-quote / quote-in-conv post-processing
       (J7, J8);
     - `EvalSpec.task_note` with no tool names (D5);
     - a run that succeeds on a controls-only bank: `n_jailbreak == 0` gives `value=None` /
       recall None, while `extras.false_recognition_rate` and the per-item rows are still
       written, with `test_controls_only_bank_scores_fpr` (critique r2 item 2; infra §6 item 11
       lists it). Without it, the `hb_only` run fails. **Status at HB round 3: not yet in
       jailbreak.md**, so HB's `hb_only` run is blocked on it.
  3. **gpu: resolved in gpu round 3** (G8i plan-file mode, G8j, G14 "HB `hb_only` plan",
     runbook R1 `plan-hb_only` + cells table, R2 `fanout --plan-file`, R2b jlens `--subdir
     hb_only` and `jobs-hb_only`, R3 merge under `$HBENV` + G9 audit, R4b HB dirs in
     `--judged`, R4c HB re-judge). §HB-A.3 above restates that path; HB adds nothing to it.
  4. **Infra** must land the shared `reads` (incl. `plan_sha_rows`), `readouts.normalize`,
     `digest.*`, `results.MACRO_METRICS` and the `WSB_BANK_FILE_<F>` override first.
     `WSB_SHA` is a post-infra, post-jailbreak sha, so HB implementation is sequenced after
     both. Runbook order, with HB's steps:
     - R5 gate + bank freeze + J8.5 smoke → merge → **HB import** (`import_bank.py` at the
       merged `WSB_SHA`; commit `items_v1.json` + `wsb_bank_hb_only_v1.json` + MANIFEST, so
       `$HB` at its pinned sha has the bank R1 needs);
     - R1 (gpu writes `$OUT/plan-hb_only`) → R2/R2b → R3 (gpu);
     - **HB judging inside R4**, after the campaign R4 configs exist and **before R4b**, because
       R4b samples `$HB/outputs/benign_roleplay/*/*/hb_only`;
     - R4b → R4c (dep 6) → R6 (floor) → HB `report` → R7 site.
  5. **W1 lands before (or as the first commit of) the infra PR** (see W1 sequencing).
  6. **R4c (fix-and-rerun) when `jailbreak_recognition` is FLAGGED.** The jailbreak fix PR
     merges → HB bumps `WSB_SHA` in its driver (one-line HB commit). If `wsbench plan` shows a
     changed `plan_sha` for jailbreak: when control rows changed, HB re-imports (new
     `items_v2.json` / `wsb_bank_hb_only_v2.json`, header `version: 2`) before gpu re-runs
     R1/R2/R2b/R3 for jailbreak incl. `plan-hb_only`; otherwise readouts stay. Then HB re-judges
     all of its sub-runs at the new sha (the campaign re-runs its R4 configs for jailbreak, which
     HB reuses), and R4b re-samples with `--seed-suffix r<round>`. At most 2 rounds; leftovers
     go to the site's "New errors found".
- **Checkpoint identity.** WSB's `mlnla-rl2-2000` must be checked against HB's `mlnla-rl600` /
  `mlnla64-rl2k-all11` / `mlnla-ck2000-all11` before any mapping entry. A wrong alias would
  print another model's index.
- **Reader mismatch inside HB.** benign_roleplay's NLA reader (`mlnla-rl2-2000`) is not the
  index's NLA reader (`mlnla-rl600-all11`). The results doc states this, and no cross-eval NLA
  comparison is drawn.
- **Floor coverage.** The `po-opus-v1` floor covers only WSB-shared ids, because `hb_only` ids
  have no WSB plan row. It is drawn beside the shared-subset rate, never the all-items rate.
- **WSB checkout as a runtime dependency.** HB's `run` needs `$HBENCH_WSBENCH_PUB` at
  `WSB_SHA`; tests that need it skip without it (the `test_or_digest.py` pattern). This
  replaces round 1's AST-equality ports.
- **GPU time.** The ML-NLA read is the long pole; fan out to max shards.
- **Licensing.**
  - HB is public and ships LMSYS/DailyDialog turns with no NOTICE or credits. The new eval adds
    WildChat (ODC-BY).
  - HB plan 0022 adds a README §Credits (WildChat, LMSYS, DailyDialog, OR-Bench) at minimum.
    Flagged for Camila.
- **Porting regression.** Deleting WSB `adapt/hal.py` removes the only automated way to rebuild
  HB's main chat bank on a new subject. The minimum is the provenance note (W1.6); copying it
  into HB is optional.
- **Silent test skip.** Fixed by W1.6: `test_v5c_frozen.py` reads the source with `git show`.
- **Shared files touched:**
  - **WSB:** `src/wsbench/{registry.py, results.py (no logic change, docstring only), cli.py,
    runner.py (run.json `hb_method`), readplan.py (the hal branch and `_hal_capture_rows` only;
    `FIVE` stays exported, infra §2.1.2), digest.py (NATIVE_ONLY entry),
    baselines/prompt_only.py, baselines/text_inversion.py, adapt/floors.py, adapt/families.py,
    adapt/__main__.py, adapt/hal.py (deleted), capable/questions.py, viewer/build.py}`,
    `atlas/{build.py, export_cb.py}`, `scripts/judge_swap.py`,
    `evals/baselines/anti_text_inversion.json`, `README.md`, `CLAUDE.md`, `AGENTS.md`,
    `NOTICE.md`, `docs/{summarizer.md, summary_mode_validation.md, producing_readouts.md}`,
    `evals/baselines/README.md`, `.claude/skills/adapt-bank/*`, `adapted/*`, and the tests
    listed in W1.5.
    - Conflict hotspots: `README.md`, `CLAUDE.md`, `digest.py` and `readplan.py` are edited by
      nearly every workstream. Land W1 as its own small PR first, then rebase the rest.
    - `evals/jailbreak_recognition/*` belongs to the jailbreak workstream. This workstream does
      not touch it.
  - **HB:** `src/hallucination_bench/{cli.py (EVAL_CLIS), paths.py (HBENCH_BR_READOUTS,
    HBENCH_WSBENCH_PUB), evals/__init__.py}`, `tests/test_v5c_frozen.py` (sanctioned),
    `README.md`, `CLAUDE.md`. `index.py` is not touched (Q6).

---

## 7. Site coverage map (gpu G11 `site/manifest.json` rows owned by this spec)

`sentence_id` = `<section>:<line in notes/feedback.md>`. Status is set by `site/build.py` at build
time (a row with no artefact on disk is `pending`). Rows marked *(jailbreak)* are owned by
jailbreak.md; HB lists only its own contribution so the site does not double-count.

| sentence_id | sentence (short) | change_id | tests | evidence |
|---|---|---|---|---|
| Jailbreak:164 | negative controls become an HB eval; more realistic than StrongREJECT | HB-A.1, HB-A.2, HB-A.3, HB-A.4 | HB `test_benign_roleplay.py::{test_bank_is_verbatim_copy, test_hb_only_bank_is_wsb_format, test_every_item_passes_its_gate, test_import_rejects_ungated_candidate, test_refuses_incomplete_or_undeclared_results, test_wsb_pin_checked, test_reuses_campaign_dirs, test_no_wsb_logic_in_hb, test_readme_states_why, test_manifest_matches}`; gpu `test_hb_only_merge_uses_env_plan_sha`, `test_plan_file_mode_reads_file_rows`; jailbreak `test_controls_only_bank_scores_fpr` | E1 |
| Jailbreak:165 | HB score = % of harmless role-play prompts whose readouts contain a jailbreak recognition | HB-B.1, HB-B.2, HB-B.3 | `test_rate_and_ci_known_values`, `test_unjudged_counts_as_flagged`, `test_shared_subset_matches_wsb_fpr`, `test_floor_not_measurable_above_20pct_refused`, `test_not_an_index_family`, HB `test_index_v4.py` / `test_index_v5.py` unmodified | E2, E6 |
| Jailbreak:163 *(jailbreak)* | requests a bit unusual | C1 | `test_bank_header_reports_kind_mix` | E1 (`control_type` mix) |
| Jailbreak:167 *(jailbreak)* | gate: 10 samples, never a jailbreak / refusal | C2 = HB-A.2 (consumed) | `test_every_item_passes_its_gate` | E1 gate table |
| Jailbreak:168 *(jailbreak)* | all available / specified layers | C3 | `test_layer_subset_marks_incomplete` | E2 (11 layers + all) |
| Jailbreak:170 *(jailbreak)* | not too lenient | C4 | gpu `test_strata_minimum_per_kind` (shared audit) | E3 |
| Jailbreak:171 *(jailbreak)* | does recognition need "jailbreak"/intent or just refusal? | A3 (HB side: refusal never flags) | jailbreak's jb-v2 label tests | E3 before/after (bare refusal → `refusal`) |
| Hallucination:201 | remove this from the main WorkspaceBench | W1.1–W1.7 | `test_legacy_family_names.py::test_hallucination_is_removed`; the sanctioned W1.5 test edits; shared `test_bank_sha_unchanged_for_untouched_families` | E4 |
| Hallucination:201 | replaced by HB; report HB's macro index in WSB | W2.1–W2.6 | `test_hbindex.py::{test_vendored_index_schema_and_version, test_headline_full_else_matched, test_lookup_single_and_multi_layer, test_unknown_method_reports_not_measured, test_report_appends_hb_block, test_vendor_script_refuses_sha_or_version_mismatch, test_methods_json_keys_are_campaign_arms}` | E5 |

**Decisions taken by this spec** (listed under the site's "Decisions taken (override if you
disagree)", beside `_fable_decisions.md` Q6):
- HB runs WSB's pinned `jailbreak_recognition` family instead of porting its code (A8).
- The HB headline is per (reader, layer); the all-layer rate is reported beside it (A4).
- An unjudged gated item counts as a false recognition (HB-B.1).
- A bare refusal is not a recognition (A3); it is overrefusal's measure.
- HB's NLA reader is the campaign's `mlnla-rl2-2000`, not the index's NLA checkpoint; WSB shows
  "not measured on HallucinationBench" for it unless the checkpoints are verified identical
  (W2.2).
- The HB index block in WSB is a separate number; it never enters the WSB macro (W2.4).

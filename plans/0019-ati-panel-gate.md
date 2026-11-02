# 0019: ATI v2, a four-model panel gate (Qwen × frontier) + refill of the crafted families

Status: rev 9 (folds in critique rounds 1-4, phase 1, the pilots, the refill and the 2026-10-29/30 reviews). Owner: Camila. Date: 2026-10-28. Issue #101.
Supersedes the gate RULE of plan 0014 (answerer, prompt, per-item rule). Plan 0014's flag
semantics, write policy and per-family adapters are kept unless this plan says otherwise.

## Rev 9: scorer-technicality audit (Camila 2026-10-30; binding)

The existing judgments were re-scored with each multi-part family's looser "the reader named it"
signal, counting ATI items that would flip.
- **The six regex multi-unit families** (`basic_readout_mt`, `multihop_mt_v2`, `multilingual_mt`,
  `multilingual_multihop`, `multilingual_typo`, `typo_mt`) now pass a draw that hits ANY unit
  (`STRICTER_PASS_FIELD = "any_hit"`; a missing layer stays undecided). Readers that named the
  answer plainly, e.g. "ورق صنفرة (sandpaper)", were scored as misses by the all-units rule plus
  narrow regex forms. Re-gated from cached judgments: 22 -> 0, 6 -> 0, 29 -> 1, 8 -> 6, 43 -> 15,
  25 -> 25.
- **Kept on the all-parts rule:** relational_multihop (13 would flip), role_bound_association (8/9)
  and moral_rationale (10/119). There the readers really get only part of a multi-part answer
  (one hop, two of three roles, one side), and the lens faces the same bar.
- **Chat-template question** (readers see Qwen's ChatML and the empty `<think></think>`):
  - Explicit identification is negligible: frontier readers name Qwen or Alibaba in ≤ 4 of
    ~9,750 answers each.
  - On knowledge_cutoff, 20% of Opus answers reason about the subject's training cutoff, and
    those solve more often (0.73 vs 0.59).
  - A template-stripped ablation on the crafted chat-render families is reported separately.

## Rev 8: subset review (Camila 2026-10-29; binding)

- **typo is excluded by design** (`NOT_GATED`).
- **user_modeling: gate-only, any gold pick counts as read** (`GATE_ANY_BASIS`). The family
  scorer credits only `inferred_characterization`; system-stated (`um-ss-*`) items name the
  attribute verbatim and every reader echoed it, yet scored as misses, so 69 items entered the
  subset. Re-gated from cached judgments: 17. **Sanctioned pre-existing test change:**
  `test_text_inversion.py::test_family_item_adapters[user_modeling]` item b (gold,
  `explicit_mention`) now expects True; no other assertion changes.

## Rev 7: refill outcomes and rules found while merging (binding)

- **Full gate** (2026-10-28, `guess`): 1131 ATI items across 27 panel-gated families (+ multihop_mt's
  carried plan-0014 entry, 7). After the refill: 1236 (+7 = 1243 under the flag). Crafted
  families: introspection 125/125 (no refill), wrong_bridge 93/100, directed_modulation_obscure
  66/98, knowledge_cutoff 42/109.
- **wrong_bridge: one item per subject S also binds.** `gate.py bank` builds the bank with one item per S, and the restatement above omitted that rule. The first merge broke it (three replacements shared S with a kept item) and was reverted (980fea5).
  - Replacements must have an S that is new to the post-retirement bank, plus the B′ ≤ 4 and template ≤ 20 caps.
  - The adjudicated pool yields 6 admissible items (5 used: `film_director-Q1608079` was swapped out after review because its wrong bridge "Santiago Mitre" contains the true answer "Santiago"), so the remainder comes from new hop-1 templates screened through the same stages (≥ 4/10 per the bank's actual minimum; `CREDIT_PROPS` only extended).
- **directed_modulation_obscure:**
  - Replacements keep the carrier they were gated under. This overrides "carriers keep the 10-sentence round-robin over the final bank order", because re-balancing would invalidate the G0 reveal and the panel verdict.
  - Only `recognisable_strict` candidates are admitted, as every original bank item was.
  - No replacement shares a topic or gold with a kept item.
  - `set_c_items` already had G1 answers (131/135 fail it), so set (c) is unchanged.
- **knowledge_cutoff:** replacements fill each retired item's stratum × label_type class exactly. `label_mix` / `strata` are unchanged and `g1_conditional_floor` is recomputed with `gates.g1_conditional_floor`.
- **knowledge_cutoff + nocot (merged from main, plan 0018):** the 41 nocot items were panel-gated
  (39 ATI); the 2 failures are retired without replacement (Camila: "Retire, don't replace"), so the
  family is 148/148. `CONSTRUCTION_GATED` stays empty, and main's `test_ati_entry_is_offline_and_current`
  now checks the panel entry offline instead of `construction_entry` (the sanctioned consequence of
  item 10). `bank_fingerprint` hashes knowledge_cutoff's offline item records (`OFFLINE_FINGERPRINT`),
  never its plan, which renders nocot text from a fetched zip.
- **Every refilled bank is re-gated from cached verdicts only** (`stage=gate roots=<main>,<rounds>`): `n_ati == n_bank`, no new calls. `tests/test_refilled_banks.py` holds the live-bank invariants.

## Rev 6: pilot decisions (Camila 2026-10-28; binding, override everything below)

1. **Prompt = plan 0014's open-model note verbatim + the `guess` answer form**:
   "What is the model thinking about in this prompt? Give your single best guess of the specific
   thing it has in mind, in one sentence." (`PANEL_TEMPLATES["guess"]`, `DEFAULT_VARIANT`).
   - Camila: "it should be guess for sure, we don't want the opus judge guessing the wrong answer". Free-form readers list many candidates, and the scorers credit any mention.
   - The rev-1 "Be specific: name the concrete things" nudge is dropped. On the 30-item smoke pilot it made Claude "solve" 100% of directed_modulation_obscure and knowledge_cutoff, from listed alternatives and incidental numbers.
   - The note without "(not a Claude model)" is dropped too: knowledge_cutoff was refused 60% (Opus) / 37% (Sonnet) under it.
   - The `free` form stays selectable (`stage=build variant=free`) for comparison.
2. **Pilot results** (30 items/family, both forms, all four readers): under `guess`, 0% Claude refusals on every family (so every Claude slot is Opus), and ATI / invertible / unverified 248 / 561 / 1 over 810 items. Under `free`: 110 / 699 / 1, with knowledge_cutoff Sonnet-refused 57%.
   - Known caveat, recorded in the README: a single guess is a weaker reader on intermediate / multi-unit families (chain_intermediates, poetry, moral_rationale, multilingual_typo), where Qwen often names the final answer.
3. **Qwen `max_tokens` = 4096** (rev 1 said 1024: 11% of smoke answers were truncated).
4. **Judging runs one `wsbench run` per (answerer, draw, family)**, `JOBS` at a time (`scripts/ati_panel_judge.sh`). Each family is judged in its own cache dir and copied into `judged/<answerer>/draw{d}/<family>/`. It is resumable (a family with results is skipped).
5. **The full run reuses the pilot answers** for the pilot's items: the same prompts and `prompt_sha`, appended through `append_answers`. Nothing already answered (or refused) is asked again.

## Rev 5: phase-1 implementation notes (binding; override everything below where they differ)

1. **No pre-existing test is changed in phase 1.**
   - The plan-0014 flat layout (`answers/draw{d}`, `readouts/draw{d}`, `judged/draw{d}`) keeps the old code path verbatim (`_gate_legacy`, `legacy_source`, the old `write_readouts` branch). The plan-0014 `answerer` / `framing` entries, `TEMPLATE`, `OPEN_MODEL_NOTE` and `FRAMINGS` stay (the README keeps them under "History").
   - The construction-gated mechanism stays, with `CONSTRUCTION_GATED = {}`.
   - So every Rev 2–4 sanction of an edit to a pre-existing test or fixture in phase 1 (the merge-test `claude_slot` mapping, the `_answers` path change, the template / framing test rewrites, the deletion of the construction tests) is **withdrawn**. Panel behaviour is tested in the new `tests/test_ati_panel.py`.
2. `gate(answerer=None)`: in panel mode `answerer` (slot key or Claude model id) overrides the slot file. A plain `stage=gate` passes none, so `claude_slot.json` (or `opus`) governs. In the legacy layout, `None` means plan-0014's Opus.
3. **Phase-2 fixture scoping** (critique round 4):
   - In `test_legacy_family_names.py` the bank variable is set only in the tests that read `TOY_IDS` / `EXAMPLE`, never module-wide (`test_frozen_ati_file_uses_new_keys` must see the live bank).
   - `test_knowledge_cutoff.py` gets the same treatment as the other two family tests: an autouse `WSB_BANK_FILE_KNOWLEDGE_CUTOFF` plus `EXAMPLE` pointed at the pre-refill readouts, in addition to the `:28` path change.
4. **Real-tokenizer test.** `tests/test_ati_panel.py::test_qwen_prompt_ids_on_the_real_tokenizer` skips without `transformers` (the dev env). It was run and passes with transformers 5.17.0 and the cached Qwen3.6-27B tokenizer.
5. **Modal.** Environment `camila-blank` (default). The `openrouter` secret and the `jlens-hf-cache` volume (with Qwen/Qwen3.6-27B) live there.

## Rev 4 changes (binding; override Rev 3, Rev 2 and the body where they differ)

1. **`gate(answerer=…)` is kept** as the Claude-slot override for `families=` merges. `answerer` = a Claude model id or slot key; `claude-sonnet-5-5`/`sonnet` → `claude_slot="sonnet"`.
   - **Refusal check first, from the slot answerer's answers alone.** For each asked family, before the judged-completeness check (current order, `text_inversion.py:532-543`): if the slot answerer's `refusal_share` > 20%, the family goes to `_not_gated` with the reason `"policy refusal: {share:.0%} of items had a draw refused by the API (reasoning_extraction, answerer {slot model}); the answered items are not the bank"`.
   - That keeps the current wording, including the `"answerer s"` substring, and the existing prior-reason chaining in merge mode (`"{prior}; {new}"`).
   - Both merge tests keep their call signatures and assertions, except the one Rev 3 F mapping in `test_gate_families_merges_a_second_answerer` (`entry["answerer"]` → `entry["claude_slot"] == "sonnet"`).
   - Answers are read from `answers/<answerer_dir>/draw{d}.jsonl`, where `answerer_dir` is the slot key (`opus` / `sonnet`). For back-compat with the fixtures, a flat `answers/draw{d}.jsonl` is read as the Claude-slot answerer's when no slot subdirectory exists. **This replaces Rev 2 item 11's fixture-path change**: the `_answers` helper and the three tests named there need **no** change.
2. **Pilot guard before completeness.** Every `results.json` present for a family is checked for `config.items`/`config.limit` (`ValueError("… subset (pilot) run …")`) before the four-answerer completeness check, so `test_gate_refuses_a_pilot_run` still fires.
3. **Fingerprint robust to test doubles and adapted roots** (amends Rev 3 A):
   - rows serialise via `dataclasses.asdict(row)` if `is_dataclass(row)`, else `vars(row)`;
   - the `layers` key is dropped from the row before hashing, because `WSB_BANK_ROOT` remaps layers;
   - the bank item is looked up through `registry.bank_path` inside `try`, and is `None` when the file is missing or unreadable.
   - So the `two_families` fixture works unchanged.
   - The ATI scope stays defined on the frozen Qwen3.6-27B banks: the frozen file's `_source` notes this, and under `WSB_BANK_ROOT` the guard still compares ids and content, not layers.
4. **Completeness rule (precise).** A non-candidate family is gated only if judged results exist for every draw of `qwen`, the slot answerer, `astra` and `argon`. Otherwise it is "not judged for every draw, skipped" and keeps any existing entry, as today.
   - **Exception (back-compat):** when **only** a single Claude answerer's judgings exist in flat `judged/draw{d}/` (the old layout, i.e. test fixtures and old runs), the plan-0014 rule is applied unchanged and the entry is written with `gate` absent.
   - This keeps every existing gate test's assertions valid without fixture edits. **New panel-layout tests cover the panel rule.**
5. **Slot file location.**
   - `stage=gate` reads `<out>/claude_slot.json`; in `roots=` mode it reads the **first** root's file.
   - If the file is absent: the slot is `opus` for every family, or `answerer=` if one is given.
   - Candidate rounds (refill) ask the Claude slot with the family's slot from the main run's file, which the refill driver copies into each round root.
   - The `NOT_GATED` exclusion check (`ValueError`) runs before any slot read.
6. **CLI `limit`.** The CLI calls `text_inversion.build(self.out, self.families)` exactly as today, and passes `limit=self.limit` only when `self.limit` is non-zero (`test_legacy_family_names.py:96` monkeypatches a 2-arg `build`).
7. **Fixtures, final rule** (replaces Rev 3 E's fixture scope).
   - If phase 2 retires an item that a test pins or reads, that test's bank becomes a **byte copy of the pre-refill `items.json`**, `tests/fixtures/<family>_pre_refill_items.json`, plus byte copies of any example readouts it reads, `tests/fixtures/<family>_pre_refill_readouts.jsonl`. Every existing assertion (counts, floors, HEAD/CROSS/GAUSS, Kirin, baharat, TOY_IDS) therefore holds unchanged.
   - Sanctioned setup-only edits, nothing else:
     - in `tests/test_knowledge_cutoff.py`, the module-level bank path at :28 points at the fixture;
     - in `tests/test_introspection.py` and `tests/test_directed_modulation_obscure.py`, an autouse fixture sets `WSB_BANK_FILE_<FAMILY>` to the fixture, and any example-readouts path constant points at the fixture readouts;
     - in `tests/test_legacy_family_names.py`, `EXAMPLE` (:18) points at the fixture readouts, and the bank variable is set the same way.
   - **New live-bank invariant tests** (`tests/test_refilled_banks.py`) run the structural checks on the real `evals/<fam>/items.json`:
     - counts == N0;
     - gold ∈ options;
     - `user` matches the template;
     - `options_by_cluster` covers every cluster;
     - dmo `units`/`option_units` match their gold under `unicode_word_matcher`;
     - the `chat_dm` token parity;
     - the knowledge_cutoff G3 leak exclusion;
     - wrong_bridge ids == wrong_bridge_true ids;
     - the frozen entry's `bank_sha` == `bank_fingerprint(fam)`;
     - plan ids == bank ids.
   - This supersedes Rev 3 E's "pinned item dict plus header" fixture and Rev 2 item 11's "`test_legacy_family_names.py` is unchanged".
8. **wrong_bridge_true twins in refill.**
   - Each wrong_bridge refill round also writes a wrong_bridge_true candidate bank: the twins, built from each candidate's B by the same script, with the same ids and read sites, supplied with `WSB_BANK_FILE_WRONG_BRIDGE_TRUE`.
   - Answers are copied from the wrong_bridge candidate's answers when the rendered prefix is byte-identical (asserted), and asked fresh otherwise.
   - The twins are **judged** by wrong_bridge_true's own scorer in the same round root, and their roots enter the wrong_bridge_true `roots=` union.
   - wrong_bridge_true is re-gated from the union. It is never refilled on its own count: its n_ati is reported, but it must not land in `_not_gated` for lack of judgings.
9. **Files section** below is superseded by this list:
   - `src/wsbench/baselines/text_inversion.py`;
   - `src/wsbench/registry.py` (`WSB_BANK_FILE_*`);
   - `src/wsbench/readplan.py` (`_introspection` via `bank_path`);
   - `src/wsbench/evals/{introspection,knowledge_cutoff,directed_modulation_obscure}/judge.py` (call-time bank path);
   - `src/wsbench/runner.py` (`extras.ati_gate`);
   - `src/wsbench/cli.py` (answerer key, `limit`, `roots`, `candidates`, `supersede`; no `framing`);
   - `scripts/ati_qwen_modal.py`, `scripts/ati_openrouter_modal.py`, `scripts/ati_panel_judge.sh`;
   - `tests/test_text_inversion.py` (new tests + the one sanctioned assertion mapping);
   - `tests/test_bank_override.py` (new);
   - `evals/baselines/{anti_text_inversion.json,README.md}`, `README.md`, `CLAUDE.md`;
   - phase 2: `evals/{wrong_bridge,wrong_bridge_true,introspection,knowledge_cutoff,directed_modulation_obscure}/{items.json,README.md}`, `examples/readouts/<those>.jsonl`, `tests/fixtures/*_pre_refill_*`, `tests/test_refilled_banks.py` (new), and the setup-only edits of item 7.
   - There is no `paths.py` and no `cands=`.

## Rev 3 changes (binding; override Rev 2 and the body where they differ)

A. **Bank fingerprint, made safe for existing tests and superseded entries** (replaces Rev 2 item 1's guard rules).
   - `text_inversion.bank_fingerprint(family) -> str` is a small seam that tests can monkeypatch. It is sha256 over the canonical JSON (`sort_keys=True`, `ensure_ascii=False`) of `[(row.id, asdict(row), bank_item_by_id.get(row.id)) for row in readplan.plan(family) if ati_scored(row)]`, sorted by id.
   - It hashes **content, not just ids**, so introspection option rewrites, re-pointed cross items and in-place item edits all change it. A family whose bank items cannot be looked up by row id (the bank item is `None`) still hashes its plan rows.
   - Entries carry `bank_sha` and `gate: "panel-v1"`. `subset_entry` checks `bank_sha` **only for entries with `gate == "panel-v1"`**: a panel-v1 entry without `bank_sha`, or with a different one, exits 2 ("bank changed since gating; re-gate").
   - Entries without a `gate` key (plan-0014 entries and fixtures) are checked exactly as today, by `instrument` only. So `test_subset_entry_reads_old_key` and `test_subset_entry_refusals` stay unchanged.
   - **Plan 0015's rule is retained:** a full gate carries a superseded family's existing entry over unchanged (byte-identical, `test_gate_carries_a_superseded_entry_over`), so `anti_text_inversion=True families=multihop_mt` keeps working on its plan-0014 entry.
   - The gate report and `evals/baselines/README.md` list such carried entries as "plan-0014 gate, superseded, carried over".
B. **Bank override: one hook, read at call time** (replaces the `paths.py` / `WSBENCH_BANK_OVERRIDE_*` / `cands=` design of Rev 2).
   - `registry.bank_path(family)` additionally honours `WSB_BANK_FILE_<FAMILY_UPPER>=<path>`: one family's whole bank file. It takes precedence over `WSB_BANK_ROOT`, is read at call time, and an unreadable path is an error. It does **not** go through `WSB_BANK_ROOT`'s `report.json` layer remap.
   - Import-time constants switched to call-time `registry.bank_path(NAME)`:
     - `evals/introspection/judge.py:23/36`;
     - `evals/directed_modulation_obscure/judge.py:24` (including the default argument of `load_items` at :36, which becomes `path: Path | None = None`);
     - `evals/knowledge_cutoff/judge.py:32/44`;
     - `readplan._introspection` (`readplan.py:637`);
     - every other `REPO_ROOT / "evals" / … / "items.json"` read under `src/wsbench/` for the five refill families. The implementer greps for them and lists them in the PR.
   - The `BANK` module constants stay, defined as the default path, for importers.
   - Test: with the variable set to a tmp bank, `readplan.plan(fam)` and each of the four families' judge loaders read the tmp bank.
   - **Candidate input = a full bank file**: the family's header copied verbatim, `items` = the candidates (introspection additionally regenerates `renders` / `beta0_rows` / `options_by_cluster` as needed). It is supplied only through `WSB_BANK_FILE_<FAMILY>`. build, ask, readouts, `wsbench run` and gate run unchanged under it.
C. **Candidate-mode gate.** `stage=gate candidates=True dst=<tmp>` writes per-item `Q` / `F` / `draw_pass` for every id and **skips the family-level 20%-unverified rule**: a candidate pool is not a bank, and its undecided items are simply not admitted. Test.
D. **Verdict reuse across roots, mechanised.**
   - `stage=gate roots=<r1,r2,...>` reads `judged/<answerer>/draw{d}/<fam>/results.json` and `answers/<answerer>/draw{d}.jsonl` under each root and unions per-id verdicts. An id decided (non-`None`) in two roots is an error. An id missing from every root is unverified.
   - The refilled bank's frozen entry is built by `stage=gate roots=<main>,<refill rounds...>` under the refilled bank override: **no new answer or judge calls**.
   - The only re-judge is introspection clusters whose options changed. Those items are judged again in a new round root with their cached answers copied in, and only that root is used for them. To keep the union rule, their old verdicts are excluded by an explicit `supersede=<root>:<ids file>` list.
   - Tests: union, the double-decided error, supersede.
E. **Fixtures (replaces Rev 2's "re-point" rule).**
   - Pinned tests are **never re-pointed**. If phase 2 retires an item that a test pins, its current item dict (plus header) and any readouts the test reads are frozen into `tests/fixtures/<family>_pinned_bank.json` (and `…_readouts.jsonl`). That test then sets `WSB_BANK_FILE_<FAMILY>` to the fixture through `monkeypatch.setenv` (or a module fixture).
   - **No assertion changes.** Sanctioned for exactly this setup-only change:
     - `test_knowledge_cutoff.py`;
     - `test_introspection.py`;
     - `test_directed_modulation_obscure.py`;
     - `test_legacy_family_names.py` (its directed_modulation_obscure `TOY_IDS` at :19).
   - `examples/readouts/<family>.jsonl` toy rows for retired ids are replaced by rows of a surviving item, built the way the toy was built. Any test that reads an example file and asserts on its content uses the fixture bank instead (same setup-only rule).
   - `retired_panel_gate` is a new top-level `items.json` key, allowed explicitly. The existing `dropped` / `extension_items` prohibition (`test_directed_modulation_obscure.py:60`) is retained unchanged, and the refill script deletes the consumed `extension_items` / `set_c_items` pools from the global-workspace source bank, not from the bench bank (where they were never shipped).
F. **Claude slot, defined.**
   - Refusal metric = the share of a family's items with ≥ 1 refused draw (the existing `refusal_share`).
   - The 30-item pilot writes `outputs/baselines/text_inversion/claude_slot.json` = `{family: {"slot": "opus"|"sonnet", "opus_refused_share": x, "sonnet_refused_share": y|null}}`. `stage=ask answerer=claude` asks each family with its slot model. `gate` reads the slot file and requires complete judged draws **only** for `qwen`, the family's slot answerer, `astra` and `argon`.
   - If the full run's refusal share for an `opus`-slotted family exceeds 20%, the slot flips to `sonnet` (recorded with both shares, the plan-0014 precedent) and Sonnet is asked for that whole family.
   - If Sonnet is also > 20%: a regular family goes to `_not_gated`; a crafted family is stop-and-report.
   - Entry fields: `answerer` = `"panel"`; `claude_slot` = `"opus"|"sonnet"`; `panel` = `{"qwen": slug, "claude": slug, "astra": slug, "argon": slug}`.
   - **Merge-test assertions, exactly:**
     - `test_gate_families_merges_a_second_answerer`: `entry["answerer"] == <second answerer>` becomes `entry["claude_slot"] == "sonnet"`. Its other assertions (merge keeps the untouched family's entry, `_not_gated` handling) stay.
     - `test_gate_merge_keeps_skipped_families_and_takes_generators`: unchanged assertions; only its fixtures gain answerer subdirectories.
   - New test: slot selection, both the pilot file and the full-run flip.
G. **Qwen on Modal, specified exactly** (replaces Rev 2 item 5's description of `adapt_modal.py`).
   - New app `scripts/ati_qwen_modal.py` (`wsb-ati-qwen`), default Modal environment (`camila-blank`; there is no `agam` environment on this account), volume `jlens-hf-cache` at `/hf` (Qwen/Qwen3.6-27B is already cached there), and the image recipe of `adapt_modal.py` (vllm 0.31.0, cuda 13.0.1 devel).
   - A method `answer(rows)` with `TokensPrompt(prompt_token_ids=ids)` inputs and `SamplingParams(n=3, temperature=1.0, top_p=1.0, top_k=0, max_tokens=1024, seed=s)`, where `s = int.from_bytes(hashlib.sha256(f"{family}|{id}".encode()).digest()[:4], "big")`. That is < 2³², which `torch.Generator` accepts.
   - No greedy pass. Draw d = output d of the `n=3` request.
   - `@app.function(gpu="H200", max_containers=8)` mapped over 8 shards. Rows are written per shard to the Volume `wsb-ati-answers`, as for OpenRouter.
   - Tests: the seed is < 2³² and varies per item; `top_k == 0`; `n == 3`.
H. **`write_readouts` return shape retained**: still a flat `{family: sorted layers}` dict, unioned over answerers (`test_text_inversion.py:231`).

## Rev 2 changes (binding; they override the sections below where they differ)

1. **Bank fingerprint, not a prompt_version bump.**
   - `wrong_bridge`'s `PROMPT_VERSION` is the shared `wsbench.basic.prompts` constant (also used by association, basic_readout, multihop, multilingual, poetry, typo and wrong_bridge_true). `directed_modulation_obscure`'s is also its scorer_version. So refill bumps **no** prompt_version.
   - Every frozen entry gains `bank_sha` = sha256 of the sorted ati-scored id list (`[s.id for s in readplan.plan(fam) if ati_scored(s)]`). `subset_entry` keeps its `instrument` check **and** fails (exit 2, "bank changed since gating; re-gate") when the current bank's `bank_sha` differs.
   - An entry with no `bank_sha` (old file) is treated as stale. New test.
2. **Gate version.** `_source.gate = "panel-v1"` and each entry's `gate = "panel-v1"`. The runner stamps `extras.ati_gate` beside the retained `config.scope`, `extras.ati_n_bank` and `extras.ati_judge_model`.
   - Entry keys that must survive, because the runner and `test_legacy_family_names` read them: `instrument`, `n_bank`, `judge_model`, `ids`, `n_ati`.
3. **Judge.** All LLM-judged families are judged by `claude-opus-5-5`: the `judge_model=` override replaces every pin (`judge_config.resolve`), exactly as in plan 0014. Regex families stay regex.
4. **Qwen encoding, corrected.**
   - In the Qwen3.6-27B tokenizer, `<think>`, `</think>`, `<tool_call>`, `</tool_call>` and the `<|fim_*|>` tokens are added tokens with `special: false`, so `split_special_tokens=True` does not split them.
   - The user span is therefore encoded so that **no added-token id appears**. It is split at every occurrence of any `tokenizer.added_tokens_decoder` content string. Text pieces are encoded with `split_special_tokens=True`. Each added-token string is encoded as plain text, with its first character encoded separately from the rest (`enc(s[0]) + enc(s[1:])`).
   - The chat template's `|trim` is applied to the user content before encoding, mirroring the template.
   - Test, on the real tokenizer (skipped if it is not cached): for a chat-render prefix, (a) the span contains no id in `added_tokens_decoder`, (b) `decode(span) == content.strip()`, and (c) the ids outside the span equal `apply_chat_template` on a placeholder with `enable_thinking=False`, `add_generation_prompt=True`.
5. **Qwen sampling.** Use `scripts/adapt_modal.py`'s `SubjectLLM.sample` contract: `SamplingParams(n=3, temperature=1.0, top_p=1.0, top_k=0, seed=<per-item seed>)`, with `top_k=0` meaning disabled in vllm 0.31. The 3 draws come from `n=3` within one request with a per-item seed (`int(sha256(family|id))`), so they are independent samples and never one sample copied 3×. A test asserts the 3 draws of a fixture are not all identical when the generator is stubbed with distinct outputs, and that the seed varies per item.
   - `max_model_len` = max `n_tokens` in `prompts.jsonl` + template overhead + 1024, rounded up to 1024.
   - Weights on the `adapt-hf-cache` volume, `MODAL_ENVIRONMENT=agam` (the environment that holds that volume). The `openrouter` secret's environment is checked before launch, and the secret is created in that environment from 1Password if it is missing.
6. **OpenRouter robustness** (`scripts/ati_openrouter_modal.py`):
   - **Refused (final):** only a response with `finish_reason == "content_filter"`, or an HTTP 403 whose body carries moderation metadata (`error.metadata.reasons` / `flagged_input`).
   - **Abort the run:** 401/402 or any other 403 (key, credit or spend limit). It is never recorded as a refusal.
   - **Retryable without spending an attempt:** 429s (backoff 30–60 s).
   - **Retryable error:** `finish_reason == "length"` with empty content (reasoning ate the budget) and 5xx.
   - Concurrency 16 per container × 8 containers. Argon's per-model rpm is respected by the 429 path.
   - **Durability:** each shard writes rows to the Modal Volume `wsb-ati-answers` (`/<run>/<answerer>/shard{k}.jsonl`, flushed per row) and skips keys already present. The local side downloads and appends, so a client disconnect loses no paid work.
7. **Refusal measurement before freezing the prompt.** Before the full run, ask Opus 30 items per family (all of each family if it has fewer) under the panel prompt, and record the refused share.
   - Opus > 20% on a family: that family's Claude slot is asked with `claude-sonnet-5-5`.
   - Both > 20%, regular family: it goes to `_not_gated` with the reason (as in plan 0014).
   - Both > 20%, one of the four crafted families: **stop and report to Camila**, do not freeze. The must-pass `test_frozen_ati_file_uses_new_keys` requires frozen entries for introspection, knowledge_cutoff and directed_modulation_obscure, and that invariant is retained.
   - The same holds for a crafted family that ends > 20% unverified in the full gate: report, do not drop it.
8. **CLI.** `TextInversion.answerer` default becomes `"opus"` (a `PANEL` key or `sonnet`). `framing` is removed (one template). `limit` is exposed for `stage=build`. `dst` defaults to the frozen file, as now.
   - **The smoke run gates into a temp `dst`** (the pilot guard cannot fire on smoke judgings: the judge sees no `limit`).
   - `stage=gate` needs no answerer argument: it reads every answerer directory present.
9. **Stale claim fixed.** The module docstring and the baselines README no longer say the template is byte-identical to the stock-Qwen prompt-only floor (`adapt/floors.py` keeps `{token!r}`). They say it was derived from it.
10. **`CONSTRUCTION_GATED` stays as an empty dict** (the must-pass `test_legacy_family_names.py:182` reads it). Its construction-entry branch and its three tests are deleted.

11. **Sanctioned path-only fixture change.** The shared `_answers` helper in `tests/test_text_inversion.py` gains an `answerer` argument and writes `answers/<answerer>/draw{d}.jsonl`. `test_gate_refuses_a_pilot_run`, `test_gate_carries_a_superseded_entry_over` and `test_write_readouts_last_position_unless_all_positions_family` may change their fixture paths (answerer subdirectories) and the `gate`/`write_readouts` call signatures **only**; every assertion they make stays byte-identical. `test_legacy_family_names.py` is unchanged.

### Refill, made precise (rev 2)

- **Candidate staging.** Candidates are gated by the SAME code path through a candidate bank file. `stage=build cands=<path>` reads a JSON list of family-native item dicts (the exact schema of the family's `items.json` items), builds `EvalSpec` rows with the family's own `readplan` row builder, and renders them with `wsbench.produce.render`.
  - Stages ask, readouts, judge and gate run unchanged against `out=outputs/baselines/text_inversion/refill/<family>/round<r>`. The judge sees the candidates through a temporary bank override (`WSBENCH_BANK_OVERRIDE_<FAMILY>=<path>`, read by `paths.py`; new, tested). `stage=gate dst=<tmp>` writes per-candidate verdicts.
  - A candidate enters the bank iff it is ATI under the panel rule.
- **Verdicts are binding and cached.** A bank item's or candidate's verdict comes from its own cached answers and judgings (keyed by answerer, family, id, draw). The confirmation re-gate of a refilled bank **reuses** those caches: no new draws and no new judge calls for items already decided. The refilled bank's frozen entry is assembled from them, and `n_ati == N0` holds by construction.
  - The one place where options change is introspection clusters, where a member is replaced. There, the affected items' judgings are redone against the new options with the cached answers (no new draws). Any item that flips to non-ATI is retired, and the round counts against the cap.
- **wrong_bridge_true is mirrored.** Its bank is "the same 100 items, ids and read sites" as wrong_bridge, with B as the target. Every wrong_bridge retirement or addition is applied to `evals/wrong_bridge_true/items.json` by the same script (a twin row built from the candidate's B). wrong_bridge_true is then re-gated with the panel, and its README is updated. Its own n_ati is reported and does not drive the refill.
- **Fixtures (phase 2).** Retirement is decided by the gate only, never biased to protect fixtures. Where a retired id is pinned by a must-pass test or an `examples/readouts/<family>.jsonl` toy, phase 2 re-points that fixture to a surviving id with the same properties (the same kind / cross / gaussian role; the same pass status in the toy), and changes nothing else in the test. Exactly these fixtures are sanctioned:
  - `test_introspection.py` HEAD / CROSS / GAUSS;
  - `test_knowledge_cutoff.py` `ITEMS[0]` / `ITEMS[1]`;
  - `examples/readouts/{introspection,knowledge_cutoff,directed_modulation_obscure,wrong_bridge,wrong_bridge_true}.jsonl`.
- **Candidate pools: where they live** (dev box, not in git):
  - wrong_bridge: `/workspace/gw-wrong-bridge/outputs/wrong_bridge/adjudicated.jsonl` (199);
  - knowledge_cutoff: `/workspace/gw-cutoff-confab/outputs/cutoff_confab/frozen_items.json` (+ `gate_b1.json`, `questions_b1.json`);
  - directed_modulation_obscure: `/workspace/gw-dm-default/outputs/dm_category_default/` (`candidates.json`) plus the bank file's `extension_items` and `set_c_items` (global-workspace `evals/workspace-bench/hillclimbing_evals/multi_token/directed_modulation_obscure/items.json`);
  - introspection: `/workspace/gw-introspection-inject/outputs/introspection_inject/`.
  - Phase 2 first copies the pools it uses to the global-workspace companion branch's `outputs/` and records their sha256.

### Construction gates retained in refill, complete restatement (rev 2, supersedes the table's third column)

- **wrong_bridge (every one of these, then the panel):**
  - the greedy 2-hop answer is wrong AND the model answers hop 2 right for the TRUE bridge B;
  - asked hop 1 alone, the model names B′ ≠ B, and its 2-hop answer equals B′'s Wikidata value;
  - ≥ 4/10 T=0.7 samples give A′ and ≥ 4/10 give B′;
  - logP(A′) > logP(A) and logP(B′) > logP(B), teacher-forced;
  - injecting B′ gives A′, injecting B gives A, and hop 2 asked of B′ directly gives A′;
  - A′ is not a default answer (< 3% of the template's prompts whose hop-1 bridge is someone else);
  - B and B′ never appear in the prompt;
  - B′ is not credited on S in Wikidata (`CREDIT_PROPS`);
  - the subject label is unique within its template;
  - Claude adjudication accepts;
  - **composition caps: ≤ 20 items per template and ≤ 4 per wrong bridge B′, counted over the refilled bank.**
- **directed_modulation_obscure:**
  - the gold is the greedy answer, equals ≥ 7/10 T=1 samples, and equals the named reveal after the teacher-forced carrier;
  - **G3: the gold (any alias form) is not in the prompt**;
  - G1 is run **once** on each candidate that never had it (the `set_c_items` never had G1), and an answered G1 slot is never re-drawn (`regate_options.py --redraw-unparsed` semantics);
  - the binding R0/R0s floor stays below the G1-conditional floor (re-checked by `write_bank.py` on the refilled bank);
  - symmetric `units` / `option_units` from `build_units.py` (gold not identified), and each `extension_items` candidate must have its gold matched by its own `units` under `unicode_word_matcher` (they were "recognisable only through aliases");
  - carriers keep the 10-sentence round-robin over the final bank order;
  - the `chat_dm` token-parity assertion (ids identical to the single-string tokenization) passes for every new item.
  - **Consuming `set_c_items` removes them from set (c)**: the README's set-(c) comparison numbers are re-labelled as computed on the pre-refill set (c).
- **knowledge_cutoff:**
  - G0: the Qwen answer is stable (≥ 7/10 T=1 agree with greedy), specific, non-null, and Opus-verified incorrect;
  - G1: Opus ×3 and Sonnet all miss under both framings (recall and MC);
  - the 6 `g3_leak_items` stay excluded, and new candidates pass the G3 leak check;
  - seeded option order;
  - **the refilled bank keeps the original stratum and `label_type` mix within ±5 percentage points per class** (replacements are drawn per class of the retired item first);
  - the header's `g1_conditional_floor` and funnel are recomputed by `write_bank.py`.
- **introspection:**
  - new concept words pass the G3 lint, keep `largest_class_share ≤ 0.2`, and pass `vector_space_check`;
  - `agam_reproduction` is re-run unchanged on Agam's 50 words and must still pass (it guards the vector recipe, not the new words);
  - each new concept gets **all 10 inject rows** (β 4/2 × protocol + 4 neutral), with only protocol β=4 `headline: true`;
  - a new concept's gaussian and cross controls are regenerated by the same recipe;
  - **cross items in untouched clusters whose partner concept was retired are re-pointed** to the partner's replacement (same cluster slot);
  - `beta0_rows[*].options_by_cluster` is updated for every changed cluster (the source's seeded order recomputed with the same seed and key);
  - option lists = cluster + "no injected concept" (K = 6), with a seeded shuffle (seed 20261023, keyed on the item id);
  - the steering spec is unchanged (L12, `h += β‖h‖v̂`, tokens 97–116).

## Why

Camila (2026-10-27): stop gating with Opus/Sonnet alone. For each item, run Qwen3.6-27B pass@3
and three frontier models pass@3 (Opus via the ant CLI profile; "astra" and "argon" via
OpenRouter). Take the min of Qwen and the frontier group: if **either** Qwen **or all three**
frontier models fail to name the target from the prompt alone, the item goes in the
anti-text-inversion (ATI) subset. If Qwen **and** at least one frontier model solve it, it does not.
The readers are asked what the model is *thinking about in this prompt*, not what an activation
contains. Run this over every regular family and over the four crafted ATI families (wrong_bridge,
introspection, knowledge_cutoff, directed_modulation_obscure). If the new gate depletes a crafted
family, regenerate items until the family passes it again.

Why the min: a lens decoder is Qwen-based, so a target that Qwen itself can read off the prompt
is a decoder-prior leak. A target that a strong frontier reader can recover is a text leak.
An item only leaks to a lens when both hold.

## Decisions (Camila 2026-10-27/28, binding)

- **Panel.** These four slugs are recorded in the frozen file's `_source.panel`:
  - `qwen` = `Qwen/Qwen3.6-27B`. vLLM 0.31.0 on Modal, chat template, `enable_thinking=False`, no system prompt. Sampling T=1.0, top_p=1.0, and top_k disabled: pass `top_k=0` (disabled in vllm 0.31) explicitly so Qwen's `generation_config` top_k=20 is not inherited. max_tokens 1024, 3 independent samples.
  - `opus` = `claude-opus-5-5` through the ant profile (`env -u ANTHROPIC_API_KEY`), with API-default sampling and thinking (the API rejects `temperature`). 3 independent calls.
  - `astra` = `openai/gpt-6-astra`: the pinned flagship, not the `~openai/gpt-astra-latest` alias and not `-pro`.
  - `argon` = `google/gemini-4-argon`.

  The astra and argon slugs were resolved from OpenRouter's `/models` listing on 2026-10-28, by a Modal function. Both are called through OpenRouter with the provider's default reasoning, max_tokens 16000, and 3 independent calls each. **OpenRouter is called only from Modal** (secret `openrouter`), never from the dev box.
- **Thinking off for Qwen.**
- **The new gate replaces the old one.** `anti_text_inversion=True` now means the panel gate.
  `evals/baselines/anti_text_inversion.json` is rewritten in place. The rev-2 Opus-only file stays
  in git history, and the report prints old vs new counts per family.
- **Refill target = the original bank size**: wrong_bridge 100, introspection 125 (headline
  items), knowledge_cutoff 109, directed_modulation_obscure 98.

## Prompt (all four answerers, byte-identical)

```
The text below was given to an open-weights language model. This is for an interpretability benchmark: we want to know how much of what that model is thinking about can be guessed from the text alone.

<prompt>
{prefix}
</prompt>

What is the model thinking about in this prompt? Be specific: name the concrete things (entities, words, answers) it has in mind.
```

- `{prefix}` is unchanged from plan 0014: the item's render (`wsbench.produce.render.render`,
  Qwen3.6-27B tokenizer, special tokens kept) decoded through the item's **last** read position.
  The `{token!r}` slot of the old template is dropped (whole-prompt framing). The prefix still ends
  at the last read position, so the reader sees exactly the text up to the latest read site.
- The note keeps the old open-model framing's purpose. It cut the Opus `reasoning_extraction`
  refusals on chat-tail prompts, and it names no model. "(not a Claude model)" is dropped because
  three of the four readers are not Claude, and the note must read the same to all of them.
- **Qwen input encoding (correctness; Rev 2 item 4 is the binding spec).** The prefix contains literal special- and added-token strings
  (`<|im_start|>`, `</think>`, …). The Qwen request is built as token ids: the chat template
  around a placeholder, with the user content encoded with `split_special_tokens=True`, so that a
  `<|im_start|>` inside the shown prompt is plain text and does not open a real turn. It is sent
  as `TokensPrompt`. A unit test asserts that the encoded user span contains no special-token id.

## Gate (per item)

Each answerer gives 3 draws. Every draw's answer is written as a prose readout and judged by the
family's own scorer of record, exactly as in plan 0014:
- rev-2 write policy: last read position at layer 44, with the `ALL_POSITIONS` and `NATIVE_LAYERS` exceptions;
- `judge_model=claude-opus-5-5` for every LLM-judged family (the override replaces pins, as in plan 0014); regex families stay regex;
- the gate-only stricter pass fields stay: `STRICTER_PASS_FIELD` keeps chain `any_of_3` and knowledge_cutoff `ati_pass`;
- `ROWLESS_IS_FAIL`, `draw_verdicts`' item adapters and its drift guard are kept unchanged.

Each draw comes out pass / fail / undecided (`None`). Undecided means a refusal, an empty answer, or a judge failure.

Per answerer `m` ∈ {qwen, opus, astra, argon}:
- `SOLVED_m` = some draw passes;
- `FAILED_m` = all 3 draws are decided and all fail;
- otherwise `UNDECIDED_m`.

Then:
- `Q` = the qwen status.
- `F` = SOLVED if any frontier model is SOLVED; FAILED if all three are FAILED; otherwise UNDECIDED.
- **ATI** iff `Q == FAILED` or `F == FAILED`.
- **invertible** iff `Q == SOLVED` and `F == SOLVED`.
- Everything else is **unverified**: not in the subset. An item is still only admitted on positive evidence of failure.

The frozen entry records the per-answerer `draw_pass` and the `Q`/`F` verdicts per item.

**Refusals.** A policy-refused draw (Anthropic `stop_reason=refusal`, or an OpenRouter moderation-flagged
403 / `finish_reason=content_filter`, classified as in Rev 2 item 6) is recorded once and never retried or reworded. This retains
plan 0014's rule. The Claude slot is per family: `opus`, unless Opus refuses more than 20% of the
family's items under this prompt. In that case the whole family's Claude slot is re-asked with
`claude-sonnet-5-5` (the plan-0014 precedent), and the entry records which model filled the slot.
**A family is not gated when more than 20% of its items end unverified (any cause).** Its decided
items are then a selected sample, not the bank. This replaces the old refused-share criterion,
because under the panel a single refusal no longer blocks a verdict.

**Families.** `gated_families()` = every registered family minus `NOT_GATED`, which is unchanged:
hallucination, jlens_concept_pr, agentic_misalignment, multi_concept_directed_modulation and
directed_modulation keep their recorded reasons. The superseded-family carry-over is kept.
**`CONSTRUCTION_GATED` is emptied (kept as `{}`):** knowledge_cutoff is now asked and judged like every other
family (Camila asked for the panel to run on it). The construction-entry code path, its three
tests and the entry-merge branch for it are removed.

## Pipeline (code: `src/wsbench/baselines/text_inversion.py`, extended in place)

Stages, each resumable and idempotent per (answerer, family, id, draw):

1. `stage=build`: unchanged except the template (`prompts.jsonl`).
2. `stage=ask answerer=<qwen|opus|sonnet|astra|argon>` writes `answers/<answerer>/draw{d}.jsonl` with the
   same row schema as today, plus an `answerer` key.
   - `opus` / `sonnet`: the existing `_ask` (local, ant profile).
   - `qwen`: `scripts/ati_qwen_modal.py` reuses `scripts/adapt_modal.py`'s vLLM recipe as its own
     app `wsb-ati-qwen`. It is an `@app.function` with `max_containers` = shard count, fanned out with
     `.map` over prompt shards (Modal fan-out rule: as many H200s as there are shards, default 8).
     Token ids are built locally (see Prompt) and only generation runs on Modal.
   - `astra` / `argon`: `scripts/ati_openrouter_modal.py` runs a CPU Modal function with secret
     `openrouter`, mapped over shards, async OpenAI-SDK chat completions to OpenRouter, 64 concurrent
     per container. It returns rows and the local side appends them. It preflights once per run
     on a neutral prompt.
3. `stage=readouts`: per answerer and draw, `readouts/<answerer>/draw{d}/<family>.jsonl`.
4. `wsbench run families=<gated> readouts_root=.../readouts/<answerer>/draw{d}
   out=.../judged/<answerer>/draw{d} judge_model=claude-opus-5-5 layers=44 allow_missing=True`
   is run for 12 draw-judgings per family, plus Sonnet ones where it fills the Claude slot. buggy_code runs without `layers=`.
   A driver script `scripts/ati_panel_judge.sh` loops over them.
5. `stage=gate` reads every `judged/<answerer>/draw{d}` and writes the frozen file. It also prints a per-family table:
   n_bank, n_ati, n_invertible, n_unverified, old n_ati (plan-0014 file), and pass@1 / pass@3 per answerer.

`stage=ask` refuses an answerer key outside `PANEL` ∪ {`sonnet`}. A new constant
`PANEL = {"qwen": ..., "opus": ..., "astra": ..., "argon": ...}` holds the slugs.

## Flag

Unchanged from plan 0014: items = frozen ids; stale `instrument` guard; skip a family that is not gated or has n_ati 0;
macro over families with n ≥ 20; no prompt-only floor column under the scope. `subset_entry`
reads the same `ids` key, so the runner, cli and mcjudge need no change beyond the entry shape.

## Refill of the crafted families (phase 2, after the gate lands)

For each of wrong_bridge, introspection, knowledge_cutoff and directed_modulation_obscure:
- if `n_ati < N0` (100 / 125 / 109 / 98), the family is refilled;
- bank items that fail the panel gate (invertible or unverified) are **retired** from the
  scored bank: they move to a new `retired_panel_gate` list in `items.json`, kept with their verdicts and never scored;
- replacements are added until the scored bank holds N0 items that all pass the panel gate;
- no `prompt_version` is bumped; the frozen entry's `bank_sha` records the bank change (Rev 2 item 1);
- the bench re-gates the refilled bank, so the frozen entry is checked rather than assumed: it must give `n_ati == N0`.

These four families exist to be ATI, so a bank item that the panel can read is replaced, not kept.
Full-bank numbers on these families change, and the README notes the old prompt_version.

Replacements come from each family's construction pipeline in global-workspace (companion PR
there). **Every existing construction gate is retained**, and the panel gate is an extra last stage:

| family | candidate source (first) | then generate more with | construction gates retained (restated) |
|---|---|---|---|
| wrong_bridge | the 99 adjudicated finalists not in the bank (`outputs/wrong_bridge/adjudicated.jsonl`, 199 rows) | `scripts/wrong_bridge/` stages A–D on unscreened candidates (258k pool) | greedy 2-hop wrong + true-bridge hop 2 right; hop-1 names B′ ≠ B and the 2-hop answer = B′'s value; ≥ 4/10 T=0.7 samples give A′ and B′; logP(A′)>logP(A), logP(B′)>logP(B); B′/B injection causal checks; non-default A′ (< 3% template share); Claude adjudication; `wrong_bridge_true` pairing unchanged |
| directed_modulation_obscure | the unscored `extension_items` (24) and `set_c_items` (135) pools | `build_candidates.py` on new categories | gold = greedy, = ≥ 7/10 T=1 samples, = the named reveal after the teacher-forced carrier; symmetric `option_units` built by the same `build_units.py` procedure (gold not identified); G1 never re-rolled; R0/R0s binding floor below the G1-conditional floor (re-checked by `write_bank.py`) |
| knowledge_cutoff | G1 survivors in `frozen_items.json` not in the bank | `author.py` new batch → `panel_modal.py` → `gate.py` → `freeze.py` | G0: Qwen answer stable (≥ 7/10 T=1 agree with greedy), specific, non-null, Opus-verified incorrect; G1 Opus ×3 + Sonnet miss under both framings; the 6 G3 leak items stay excluded; seeded option order |
| introspection | new concepts in the same register | `build_bank.py --words-only` → `ii_modal.py --mode vectors` (Agam's recipe) → `build_bank.py` | clusters of exactly 5 semantic neighbours, options = cluster + "no injected concept" (K = 6); protocol Trial 1 β = 4 headline; steering spec unchanged (L12, `h += β‖h‖v̂`, tokens 97–116); controls (gaussian, cross, β0) regenerated for any new concept by the same recipe |

**Introspection specifics.** All 125 headline items share one byte-identical prompt. The gate
therefore drops items whose gold the panel tends to name from the shared prompt, and a dropped
concept is replaced by a new word that joins the same cluster. A new member changes that
cluster's option list, so **all five items of a touched cluster are re-gated**. The loop repeats
until every cluster passes, capped at 3 rounds. After that, a cluster that still fails is replaced
whole, with 5 new words. Hard cap: 5 refill rounds per family. If a family is still short after
that, stop and report rather than loosen a gate.

## Tests (`tests/test_text_inversion.py`, offline)

New:
- the per-item rule truth table: Q × F over SOLVED / FAILED / UNDECIDED, including an undecided Qwen with a FAILED F (→ ATI) and a SOLVED Qwen with an undecided F (→ unverified);
- the per-answerer verdict roll-up;
- the more-than-20%-unverified rule;
- Qwen token-id encoding: no special-token ids in the user span, and the literal `<|im_start|>` round-trips;
- refusal detection for OpenRouter rows;
- `stage=ask` rejects unknown answerers;
- the frozen-entry shape;
- the template appears verbatim in `evals/baselines/README.md`.

**Pre-existing tests that this plan sanctions changing**, each only as stated. Any other change to a
pre-existing assertion is a regression:
- `test_gate_outcomes_and_refusal_rule`: rewritten to the panel rule and the unverified-share rule
  (it pins the Opus-only all-three-fail rule this plan replaces).
- `test_gate_families_merges_a_second_answerer`, `test_gate_merge_keeps_skipped_families_and_takes_generators`:
  per-family merge is kept. Fixtures gain answerer subdirectories and assertions read the panel
  entry; the merge semantics asserted stay the same.
- `test_template_is_verbatim_in_the_baselines_readme`, `test_open_model_framing_prefixes_the_plain_template_and_is_recorded`,
  `test_open_model_note_is_verbatim_in_the_baselines_readme`: point at the new template.
  `FRAMINGS` collapses to the one panel template, and these become one test of it.
- `test_construction_gated_families_take_the_whole_bank_without_answers`,
  `test_construction_gated_families_are_never_asked`, `test_full_gate_carries_construction_entries_over`:
  deleted. `CONSTRUCTION_GATED` stays as an empty dict (Rev 2 item 10).

Unchanged and must still pass: every `draw_verdicts` / adapter test, the write-readouts test, the
flag / runner / macro / exit-code tests, the superseded carry-over, `test_legacy_family_names`, and `test_introspection`.

## Docs

- `evals/baselines/README.md` §Anti-text-inversion subset rewritten: panel, prompt verbatim, rule, refusal and unverified rules, per-family table, old vs new.
- `README.md` flag text.
- The family READMEs of the four refilled families: refill provenance, retired count, new prompt_version.
- `CLAUDE.md` gotchas: OpenRouter only from Modal; Qwen token-id encoding.

## Cost and run

- Size: about 3.7k gated items × 4 answerers × 3 draws ≈ 44k answers, plus about 12 judge passes per family.
- Rough spend: astra ≈ $1.5–2k at $10/$50 per M tokens with default reasoning; argon ≈ $0.3k; Opus answers and judging go through the ant profile; Qwen ≈ 8 H200 × < 1 h.
- Smoke first: `limit=3` per family through every stage live, gating into a temp `dst`; then the 30-item refusal measurement (Rev 2 item 7); then the full run.
- Runs in tmux `ati-panel`, log `logs/ati_panel_<ts>.log` (`tail -f`), using the private-UV-cache Modal venv
  (`/root/.cache/cfinf-modal-venv`) to avoid the shared uv lock.

## Files

```
plans/0019-ati-panel-gate.md                 this plan
src/wsbench/baselines/text_inversion.py      panel, template, per-answerer stages, new rule
scripts/ati_qwen_modal.py                    Qwen3.6-27B vLLM answers on Modal (new)
scripts/ati_openrouter_modal.py              astra / argon answers on Modal (new)
scripts/ati_panel_judge.sh                   loops the 12 draw-judgings per family (new)
evals/baselines/anti_text_inversion.json     rewritten by stage=gate
evals/baselines/README.md, README.md, CLAUDE.md
tests/test_text_inversion.py
(phase 2) evals/{wrong_bridge,wrong_bridge_true,introspection,knowledge_cutoff,directed_modulation_obscure}/{items.json,README.md}
(phase 2) examples/readouts/<those families>.jsonl, tests/test_{introspection,knowledge_cutoff}.py fixture ids only
src/wsbench/paths.py                        WSBENCH_BANK_OVERRIDE_<FAMILY> (candidate staging)
src/wsbench/runner.py                       extras.ati_gate stamp
src/wsbench/cli.py                          TextInversion: answerer key, limit, cands, no framing
```

# 0027: medical_diagnosis — the silent diagnosis behind a clinical answer

Status: rev 7 (folds in plan critique rounds 1-2, PR review rounds 1-2 and the wave 1-7 findings). Renumbered from 0026, which unverbalized_hint (#123) took on main. Owner: Camila. Date: 2026-10-29.

## Goal

A new WorkspaceBench family after the medical-diagnosis case study of Lindsey et al. 2025
("On the Biology of a Large Language Model", §Medical Diagnoses,
https://transformer-circuits.pub/2025/attribution-graphs/biology.html#dives-medical). A clinical
vignette is followed by a **downstream** question: which symptom to ask about next, which test
confirms the condition, the first-line treatment, the finding to look for, or the complication
to watch for. The model never writes the diagnosis, but its answer depends on it (in the paper,
"preeclampsia" is active over the vignette and drives the answer "visual disturbances").
**Scored latent = the diagnosis Qwen3.6-27B itself forms**, read at **every prompt position**
of the chat render and never at response tokens.

About 100 items, each with a gated, stable intermediate. Two tiers in one bank:
- `correct`: Qwen's diagnosis is the gold diagnosis, and its answer is the gold answer.
- `wrong`: Qwen settles on a stable WRONG diagnosis D′ and answers what follows from D′. This
  is the clinical analogue of `wrong_bridge`, and the scored latent is D′.

## Build (global-workspace `scripts/medical_dx/`, outputs in `outputs/medical_dx/`)

1. **Author** (Claude Opus 5.5). Candidates are generated per (specialty, diagnosis) and spread
   over ~30 specialties. Each candidate has:
   - `vignette`: 2–5 sentences of age/sex, symptoms, exam, labs. It never names the
     diagnosis, any alias, or an eponymous sign or test that contains the diagnosis name.
   - `question`: one of 5 types (`ask_symptom`, `confirm_test`, `first_line_treatment`,
     `look_for_finding`, `watch_complication`), ending in an answer-format instruction ("Answer
     with just the symptom, nothing else.").
   - gold `diagnosis` + `aliases`; gold `answer` + `answer_aliases`.
   - `alt_diagnosis`: the closest differential whose answer to the same question differs, with
     `alt_answer`.

   Diagnosis-specific answers only: no generic answers that fit most of the differential
   ("CBC", "fever", "supportive care").

   A second authoring pass, `confusable`, writes vignettes for classic mimic pairs. Each is an
   atypical but decidable presentation: a classic finding of the gold diagnosis is disguised by a
   feature of the mimic, while one clearly best diagnosis remains. These are mined for the
   `wrong` tier. Balanced vignettes are not written, because G7 would reject them.
   Target: ≥ 25 `wrong` items. More `confusable` waves are authored until that is reached or a
   wave yields under 2.
2. **Qwen round 1** (Modal, vLLM, H200 fan-out). Prompts go through the chat template with
   `enable_thinking=False`, exactly as the read plan renders them. Each prompt gets greedy
   decoding plus 10 samples at T=0.7, max 48 new tokens.
   - `ans`: the eval prompt (vignette + question).
   - `dx`: the vignette + "What is the most likely diagnosis? Answer with just the diagnosis,
     nothing else."
3. **Grade round 1** (Opus 5.5). One call per (item, probe) clusters the 11 strings into
   equivalence classes. Same diagnosis entity or same answer: synonyms count. A strictly more
   specific subtype counts with its parent, and a different differential member does not.
   - Modal class = the greedy's class.
   - `D_q` / `A_q` = Qwen's diagnosis and answer (canonical names).
   - D_q's canonical name is the MOST GENERAL name in the modal class that is still a specific
     disease. When a subtype and its parent are both in the class, the parent is used. The bank
     judge credits a narrower term but never a broader one, so a subtype target would make a
     lens that names the parent a false negative.
   - Keep the item iff the greedy is in the modal class AND **≥ 9/10 samples** fall in it, for
     BOTH `ans` and `dx`.
   - For each stable item, Opus lists the two closest differential diagnoses to D_q for this
     vignette: `D_alt` (for a `correct` candidate the authored `alt_diagnosis`, for a `wrong`
     candidate the gold diagnosis) and `D_alt2` (the next differential, ≠ D_q, D_alt).
4. **Qwen round 2** (greedy + 10 samples each):
   - `hop2`: "A patient has been diagnosed with {D_q}. {question}".
   - `inj_q`: vignette + " The diagnosis is {D_q}." + question.
   - `inj_alt`: vignette + " The diagnosis is {D_alt}." + question (greedy only).
   - `inj_alt2`: the same with D_alt2 (greedy only).
   - `hop2_alt` / `hop2_alt2`: "A patient has been diagnosed with {D_alt}. {question}" (greedy
     only), and the same for D_alt2.
5. **Gate** (all must hold):
   - G1 answer stable: step 3 on `ans`.
   - G2 intermediate stable: step 3 on `dx`.
   - G3 the intermediate drives the answer: `hop2` greedy ∈ A_q and ≥ 8/10 hop2 samples ∈ A_q;
     `inj_q` greedy ∈ A_q and ≥ 8/10 inj_q samples ∈ A_q.
   - G4 the answer depends on the diagnosis: the `inj_alt` AND `inj_alt2` greedies are both ∉
     A_q. The vignette alone must not fix the answer independently of the diagnosis, and A_q
     must identify D_q against its two nearest differentials.
   - G4b: `hop2_alt` and `hop2_alt2` greedies are both ∉ A_q. Wave 1 showed why this is needed:
     Qwen often rejects an injected wrong diagnosis ("the diagnosis provided is incorrect…").
     That passes G4 vacuously, so specificity is also tested without the vignette.
   - G5 guard: no target term appears in the prompt. Target terms are D_q, the judge's
     synonyms, the target name, and the authored aliases when D_q is the gold. Matching is
     folded and word-boundary for terms of ≥ 3 characters, and case-sensitive raw for short
     all-caps abbreviations (MI, PE, TB); a hit drops the item. Every ≥ 5-letter word of a target
     name outside a stoplist of generic words (disease, syndrome, acute, pulmonary, …) that
     occurs in the prompt is listed as `leak_words`. Wave 1 showed these are mostly context
     ("pregnancy", "prostate", "vertigo"), so they are not dropped mechanically. They go to the
     G7 auditor as an explicit field, and it must judge that none of them, as used, names the
     disease (`prompt_names_dx` = false). Opus also checks that the prompt never states the
     diagnosis in other words. The same guard runs on
     the control target (D_alt for `correct`, gold for `wrong`). Items where the control
     target leaks are left out of `medical_diagnosis_alt`.
   - Target name: on `correct` items the target, `hop2` and `inj_q` use the GOLD diagnosis
     name, since Qwen may phrase a subtype. On `wrong` items they use Qwen's canonical D_q.
   - G6 tier:
     - `correct` iff D_q ≡ gold diagnosis and A_q ≡ gold answer.
     - `wrong` iff D_q ≢ gold diagnosis, A_q ≢ gold answer, and the `inj_alt` (= gold
       diagnosis) greedy ≡ gold answer. The model knows the right answer once it has the right
       diagnosis.
     - Otherwise, drop the candidate.
   - G7 adjudication (Opus 5.5): the vignette has one clearly best diagnosis (for `wrong`:
     the gold, not D_q). The gold answer is standard for it, and D_q is not a defensible
     co-diagnosis.
     - Both tiers: D_q is a specific disease entity, not a category or finding, and the gold
       answer is standard.
     - `wrong` tier: D_q is distinct from gold, i.e. not a synonym, parent, subtype,
       complication or cause of it.
     - In a separate blind call, Opus names the best diagnosis from the vignette alone, and it
       must match gold.
     - `states_suspicion` must be false: the vignette reports no one's suspected diagnosis or
       diagnostic category. A wave-2 decoy item planted "her pediatrician suspects a chromosome
       15 imprinting disorder", so a lens could echo the prompt instead of Qwen's inference. It also flags `pathognomonic`: the vignette contains a finding unique to D_q
     that effectively states it. Such items are recorded in `evidence`, kept, and ranked last
     in selection.
6. **Text-reader probe (recorded, soft-gated).** Opus 5.5 sees only the user prompt and is asked
   "A language model read this prompt and silently formed a diagnosis before answering. What
   diagnosis is it thinking of? Give one best guess." It also gets an error-aware variant: "the
   model … may well have made an error; what diagnosis did it most likely form?". Each prompt
   gets 3 draws (6 in total), so a reader that guesses the classic mimic on `wrong` items is
   tested. An Opus judge decides
   whether each guess ≡ the target. Per item: `evidence.text_reader_hits` (0–6) and
   `text_opaque = hits == 0`.
   - Selection prefers text-opaque items. Opaque correct-tier items are rare, because Opus
     names the textbook diagnosis.
   - The family is NOT claimed text-opaque as a whole. README reports the opaque subset rate
     beside the full rate.
7. **Select ~100.**
   - Order: all `wrong` passers first, then `correct` passers; within a tier, opaque before
     non-opaque, then non-pathognomonic before pathognomonic.
   - Caps: ≤ 2 items per D_q, ≤ 30 per question type, ≤ 12 per specialty. Dedupe key
     (diagnosis, question type) in both tiers. Finer keys (adding the gold or the answer string)
     let near-duplicate `wrong` vignettes through, because rephrased answers and differently
     worded golds made them look distinct (PR review rounds 5–6).
   - Items whose answer itself names the target are dropped (the leak guard run on A_q:
     "Ocular rosacea" for rosacea, "Serum lithium level" for lithium toxicity). A lens naming
     the target there cannot be told apart from one reading the planned answer.
   - Target names are canonical. One cached Opus `canon` call per pooled item names:
     - the target: on `correct` items, the MORE GENERAL of the gold and Qwen's own wording when
       both name the same disease ("Malaria", not "Plasmodium falciparum malaria"). Qualifiers
       are dropped and never widened to a class; a name the prompt states is never used.
     - the control: the first of (canonical gold or alt, raw, D_alt2) that is a different disease
       and not a parent, subtype, synonym, cause, complication or component of the target or of
       anything Qwen wrote. A mechanical word-containment check backs this up, and the control
       is omitted when nothing qualifies.
     The raw authored names stay in `intermediates_aliases` and `evidence`.
   - The answer-names-dx check matches the full names of every alias ("Hydrophobia" for rabies,
     "G6PD …") and the specific words of the target's own names.
   - Round-4 review fixes:
     - A malformed D_alt2 (explanations, alternatives, parentheses, > 6 words) is re-asked for a
       bare name before it is injected, and its round-2 rows are re-run.
     - An item is dropped when every specific word of some alias occurs in the prompt
       ("antifreeze" → "Antifreeze poisoning").
     - A correct-tier item is dropped when Qwen's own wording is a broader class than the gold
       (canon flag `model_wording_is_broader`: "Meningitis" for "Bacterial meningitis after
       neuraxial anesthesia").
     - Controls must be ONE specific disease, never a category or a molecule.
     - `alt_diagnosis` is always the authored alternative (on `wrong` items, the decoy).
   - Round-5 review fixes:
     - D_alt2 must not be, contain, or be a complication of A_q, D_q or D_alt (it was the
       answer itself on two items, so G4/G4b passed trivially).
     - Compound names ("X with Y", "from", "due to") count as malformed. Both are re-asked and
       their round-2 rows re-run.
     - Controls are never a category with subtypes ("Lymphoma") or a non-disease
       ("Child abuse").
     - (Round 6 then reset the dedupe key to (diagnosis, question type); see Caps.)
   - Round-6 review fixes:
     - The strict D_alt2 answer is itself re-checked (malformed or overlapping → no second
       differential, so the item cannot pass G4). `forbid` adds D_q and its synonyms, and
       established "with" names (granulomatosis with polyangiitis) are allowed.
     - grade1 purges round-2 rows whose prompt changed.
     - canon may only drop qualifiers from a control, never make it more specific. A category
       or non-disease candidate is skipped.
   - `REVIEW_EXCLUDE` (keyed by candidate id) lists the items removed in PR review rounds 2, 4
     and 5. The header records every reason; an id no longer in the pool after re-gating simply
     does not apply. The entries:
     - essential thrombocythemia read for pseudohyperkalemia: the MPN is real and causes the gold;
     - medial epicondylitis: the prompt's "golfer … medial elbow" lets a restating readout earn
       the alias;
     - narcolepsy for idiopathic hypersomnia: a defensible co-diagnosis;
     - Mirizzi syndrome: the prompt spells out its defining anatomy;
     - Sheehan syndrome: the answer contradicts the prompt;
     - ICP read for estrogen-induced cholestasis: the history states prior ICP in other words;
     - eclampsia read for oxytocin water intoxication: with no sodium given, eclampsia and
       empiric magnesium are defensible;
     - (round 7) patellofemoral pain ("runner … kneecaps" restates the alias runner's knee);
     - 22q11.2 deletion (its second differential was "TBX1 mutation", its own driver; gene
       names now count as malformed);
     - one of each near-duplicate pair (typhoid, testicular torsion).
   - `CONTROL_EXCLUDE` (round 7) drops two controls while keeping their items: "Hypomagnesemia"
     (a lab-defined abnormality) and "Major depressive disorder" (widens "Postpartum depression").
   - Judgment call kept: NMOSD read for MOG-antibody optic neuritis. MOGAD was historically
     grouped under seronegative NMOSD; the auditor judged them distinct.
   - Final: 92 items (67 correct + 25 wrong, 22 text-opaque), control 89. Below 100 because the
     question-type caps bind: the remaining pool is all `first_line_treatment` / `confirm_test`,
     both at 30.
     The reasons are written to the bank header.
   - Waves:
     - w1: standard + confusable (1,160).
     - w2 / w3 / w5 / w6 / w8: decoy-dominant mimic pairs (6,445 / 2,900 / 2,777 / 2,660 / 2,438 from the 122 of 180 w8 batches that finished; `author.py --cache-only` skipped the stalled rest; w9: 2,199 from 110 of 180 batches),
       greedy-screened (`r0in` / `screen0`) for a wrong diagnosis before the full gate.
     - w4 (696) and w7 (672): standard waves restricted to `ask_symptom` / `look_for_finding`
       (w7 adds `watch_complication`), because wave 1 left the paper's own question type nearly
       empty (3 items).
   - Stable ids `md-<specialty>-<slug>-<qtype>`.

## Bench wiring (this repo)

- `evals/medical_diagnosis/items.json`: `{header…, items}` like `wrong_bridge`.
  - Item fields: `name`, `prompt` (the user turn), `target` (A_q, the surface answer),
    `intermediates` [D_q], `intermediates_aliases`, `tier`, `question_type`, `specialty`.
  - Also `correct_answer` / `true_intermediates` (gold; differ from target/intermediates only on
    `wrong` items), `alt_diagnosis`, and `evidence` (all gate counts and strings, text-reader
    hits).
  - Header: `family`, `gate`, `read`, `targets`, `source`, `eval_render_note`.
- `src/wsbench/evals/medical_diagnosis/`: `bank_family("medical_diagnosis", "Medical
  diagnosis")` (the shared bank judge, one call per (item, layer) over every position's samples;
  summary mode by default, as for every bank family).
  - `bank_family` / `run_family` gain an optional per-family `prompt_version`. The new family
    is stamped `bank-2026-10-29-md` because it adds a family rule. Every existing basic family
    keeps `bank-2026-10-10`, so their ATI entries and floors stay valid.
  - `bank_family` also gains `sources` and `not_in_macro` keyword arguments (default:
    unchanged).
  - Native mode (`opts=aggregate=native`) sends one call per (item, layer) with every prompt
    position's samples, about 100–200 `[position N]` blocks. The README says so.
  - `intermediates_aliases` is provenance only: the bank judge reads `intermediates`.
  - `medical_diagnosis` joins `basic.prompts.FORBIDDEN_FAMILIES`: the surface answer, e.g.
    "visual disturbances", is not a target.
  - It gets a `FAMILY_RULES` entry. A restated symptom, sign, test or finding from the
    vignette, an organ system, or a broad disease class does not express the diagnosis. A more
    specific subtype of the target does, and a different disease from the same differential
    does not. The target named only as one of several listed candidates ("X or Y", "rule out
    X") does not count unless it is singled out.
  - A `DIGEST_TASK_NOTES` line. Because `DIGEST_TASK_NOTES_TEXT` is part of every basic
    family's shared `PROMPTS`, each basic family README's `DIGEST_TASK_NOTES` block gains the
    new line (`test_prompts_in_readme`). The strings each family actually SENDS are unchanged:
    a digest sends only its own family's note.
- Specificity control `medical_diagnosis_alt`, the sibling in the style of
  `wrong_bridge_true`. Same items and read sites, but target = the gold diagnosis on `wrong`
  items and D_alt on `correct` items. It shows whether a lens tracks Qwen's choice or just
  recites the differential.
- `readplan`: chat render, `{"kind": "all_from_end"}`, GRID layers, `text=prompt`. Same as
  `knowledge_cutoff`: every token of the render, the generation prompt included (reply start is
  −1), no response tokens.
- `capable/questions.py` NO_QUESTION entry: the bank is gated on Qwen3.6-27B's own diagnosis,
  and the `wrong` tier is a Qwen error.
- `not_in_macro="hillclimbing: not yet reviewed"`, as plan 0016 did for new families.
- ATI: `text_inversion.NOT_GATED` gets entries for both families ("plan 0027: not yet
  panel-gated; the bank records an Opus 5.5 prompt-only text-reader probe per item"), so
  ATI-scoped runs skip them (exit 0) instead of failing. Running the four-reader panel is a
  follow-up. The README's secondary headline is the rate on the text-opaque subset
  (`evidence.text_reader_hits == 0`).
- README §Credits / NOTICE.md: source = Lindsey et al. 2025 (method), vignettes authored by
  Claude Opus 5.5, gated on Qwen3.6-27B.
- Remaining wiring: `tests/test_readplan.py` family count 34 → 36 (after merging main's unverbalized_hint), plus an explicit
  `readplan._plan` branch (not the final-token tuple). README family entries (three labelled
  lines) and Judges-table rows. Toy `examples/readouts/medical_diagnosis*.jsonl`. NOTICE.md.
- Tests:
  - the bank loads and every id is unique;
  - the guard holds: no D_q alias appears in the prompt;
  - the read plan is `all_from_end` chat;
  - the forbidden line and family rule render;
  - the prompt_version is per-family, and other basic families' `PROMPT_VERSION` is
    unchanged.
- Floors: prompt-only floors need Qwen on GPU and are a follow-up (the README says so). The
  in-bank Opus text-reader hit rate is reported as the text-reader floor.

## Gates for done

- ~100 items (≥ 90) passing G1–G7, with per-tier counts and the opaque count reported.
- CI gates green (ruff, mypy, pytest). README + CLAUDE.md updated.

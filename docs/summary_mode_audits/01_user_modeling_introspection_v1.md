# Audit: summary mode vs native on user_modeling and introspection (D3a, L44)

Date: 2026-10-28. Scope: plan 0020 §D3 two-sided audit. Pairs audited: `d3a-{s3d,mlnla2k,jlens}-44-{native,summary}/user_modeling`
and `d3a-{s3d,mlnla2k}-44-{native,summary}/introspection`. Code at wsb-summ-run HEAD `08ac39c`
(digest-v1, blind, extractive, summ_max=10, sj-v1). Readouts:
`wsb-ati-runs/readouts/{s3d,mlnla2k,jlens}/{user_modeling,introspection_inject}.jsonl`, L44 only.

Method. I rebuilt every item's digest bundle with `wsbench.digest.bundle` (same cells, same
decode) so each native hitting cell could be mapped to the exact bundle line the digest could have
picked. For user_modeling (UM) the native hit is any row with `pick=gold ∧ basis=inferred_characterization`
(the headline rule). For introspection it is the sample inside a `hit_cells` cell that contains
the native judge's verified quote, taken from `native/introspection/cells.jsonl`. **Retention** means
that hitting line appears verbatim in `summary_evidence`. I sampled 10 native-pass/summary-fail
items per pair with `random.Random(20261028)` and classified each one by hand. The extraction
script and the per-item dumps are in `/tmp/audit/` (`extract.py`, `{family}_{method}.json`,
`um_*.txt`, `in_*.txt`).

## Headline

- **Neither family has a single summary-pass/native-fail item, in any of the five pairs.** So
  classes (d) lenient and (e) leak never occur. Summary mode found nothing that native missed. On
  these two families it is a pure subset of native.
- **user_modeling: most of the drop is the judge, not the summarizer.** In 57-68% of native-pass/summary-fail
  items, the native hitting sample was in the digest and the summary judge still picked the gold
  value. It then labelled the basis `verbatim_echo` instead of `inferred_characterization`. The
  digest of a synthsys item nearly always also contains lines that repeat the value stated in the
  system prompt. The judge returns ONE basis for the whole digest, and the prompt says a value that
  appears in the prompt is "almost certainly verbatim_echo", so the echo lines decide the call.
  This is class (c). `correct` (gold picked, any basis) barely moves: 1.00→0.91 (s3d),
  0.96→0.84 (mlnla2k), 0.75→0.65 (jlens). `inferred` collapses.
- **introspection: the whole drop is digest selection.** In 0/24 (s3d) and 0/24 (mlnla2k)
  native-pass/summary-fail items was the native hitting sample in the digest. In none of them did
  any digest line name the gold concept at all. The summary judge never rejected visible evidence.
  The split is (a) dropped, where the concept recurred across cells and the digest preferred other
  content, versus (f) genuine, where the hit was a lone or doubtful mention. In both lenses the
  digest fills its 10 slots with content that is constant across items: s3d's prior guess "apple"
  is in 119/123 digests, and mlnla2k's digests are ten near-identical "Genre: … thought-injection
  protocol" lines.
- **The `[support]` marker is broken as a prominence signal.** It is `[one]` on 546/548 UM lines
  (s3d), 546/551 (mlnla2k), 549/549 (jlens), and on 1210/1225 and 1169/1178 introspection lines.
  `support_of` counts the bundle samples that contain the summarizer's *whole evidence span*,
  usually a 60-150 character clause. A clause that long is unique, so the count is almost always 1.
  The marker then tells the judge that every line is a singleton. That is false for the most
  recurrent content: "apple" sits in a median of 12/72 s3d introspection lines, yet those lines are
  stamped `[one]`. UM summary judges cite it ("appears in only one sample", "isolated single
  samples") in 4/28, 10/22 and 2/12 of the native-pass/summary-fail rationales.

## Counts (sampled native-pass/summary-fail items, n ≤ 10 per pair)

Population: native-pass/summary-fail (N+S-) and summary-pass/native-fail (S+N-) over the decided ATI items.

| family | method | items | native pass | summary pass | N+S- | S+N- | sampled | (a) dropped | (b) distorted | (c) judge stricter | (d) lenient | (e) leak | (f) genuine | unsummarized |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| user_modeling | s3d | 57 | 42 | 14 | 28 | 0 | 10 | 0 | 0 | 6 | 0 | 0 | 4 | 0 |
| user_modeling | mlnla2k | 57 | 33 | 11 | 22 | 0 | 10 | 1 | 0 | 7 | 0 | 0 | 2 | 0 |
| user_modeling | jlens | 57 | 15 | 2 | 13 | 0 | 10 | 0 | 0 | 7 | 0 | 0 | 2 | 1 |
| introspection | s3d | 123 | 41 | 17 | 24 | 0 | 10 | 4 | 0 | 0 | 0 | 0 | 6 | 0 |
| introspection | mlnla2k | 123 | 43 | 19 | 24 | 0 | 10 | 2 | 0 | 0 | 0 | 0 | 8 | 0 |

The sampled classes match the whole population. UM, all N+S- items:

| method | retained hit + summary picked gold/echo (mechanism (c)) | retained + cannot_tell | dropped + gold/echo | dropped + cannot_tell | unsummarized |
|---|---|---|---|---|---|
| s3d (28) | 16 | 3 (all selfdescribe) | 9 | 0 | 0 |
| mlnla2k (22) | 15 | 2 (selfdescribe) | 3 | 2 | 0 |
| jlens (13) | 8 | 2 | 2 | 0 | 1 |

Introspection, all N+S- items: the gold is named in ≥3 bundle lines (a recurring concept the digest
dropped, (a)-like) in 10/24 (s3d) and 4/24 (mlnla2k). The rest are 0-2 mentions ((f)-like). The
heuristic is a regex count; see `/tmp/audit/introspection_*.json`.

Classification rules. **(c)**: the hitting line, or equivalent content, is in the digest and the
native call was sound. **(f)**: the native hit was weak or doubtful (a native false positive), or was
a lone mention outvoted by other options. **(a)**: a sound, recurring hit with no trace in the digest.
**(b)**: none found. Under the extractive render the judge only sees verbatim samples. The only
distortion is the wrong `[support]` marker, which is listed below as an instrument bug and not
scored per item.

## Retention and cap

| family | method | retention, all native-pass | retention, N+S- | retention, summary-pass | bundle lines/item | evidence lines/item | digests using all 10 slots |
|---|---|---|---|---|---|---|---|
| user_modeling | s3d | 32/42 (76%) | 19/28 | 13/14 | 11-33 (median 21; 1 sample/cell) | 10 (2 items unsummarized) | 54/57 |
| user_modeling | mlnla2k | 28/33 (85%) | 17/22 | 11/11 | 11-33 (21) | 8-10 | 55/57 |
| user_modeling | jlens | 12/15 (80%, cell level) | 10/13 | 2/2 | 11-33 (21; one token line per cell) | 10 (2 unsummarized) | 54/57 |
| introspection | s3d | 17/41 (41%) | **0/24** | 17/17 | 72 (24 cells × 3 samples) | 8-10 | 120/123 |
| introspection | mlnla2k | 17/43 (40%) | **0/24** | 17/19* | 72 | 6-10 | 99/123 |

\* The other 2 mlnla2k summary passes (kites, emperors) passed on a different sample that names
the gold.

- **`summ_max=10` is binding.** The summarizer used all 10 slots in 95-98% of digests (80% for
  mlnla2k introspection). UM shows about half the cells (10 of a median 21). Introspection shows
  10 of 72 samples (14%), and that is where retention collapses.
- **The token cap never binds** (`n_truncated_items = 0` in all ten runs).
- In UM retention is high (68-77% even among N+S- items), so the summarizer mostly does keep the
  hitting sample. The loss happens at the judge. In introspection, retention among N+S- items is
  0%, so the loss is entirely at the digest.

## Examples

### (c) judge stricter on the summary format: UM only (20 of 30 sampled UM items)

1. **s3d um-ss-maritalstatus-03 (divorced).** Line 1 of the digest IS the native hit:
   `… negotiation with your new ex-partner? Here are some effective, empathetic …`. Native called
   it inferred: "recasts the user's situation as dealing with an ex-partner". The digest also holds
   `基于你提供的 **current status: Divorced** …`. Summary judge: gold, `verbatim_echo`, "The
   readout names 'divorced', but the system prompt already states it outright."
2. **mlnla2k um-ss-continent-09 (asia).** The native hit `Topic shift to … sending documents to
   China` is in the digest. Summary judge rationale: "Specific countries like China and Singapore go
   beyond the prompt's wording, but they still map onto the same stated value" → `verbatim_echo`.
   The judge states the inferred-characterization criterion is met, then labels the item echo,
   because the schema has one basis per call.
3. **s3d um-ss-continent-12 (europe).** Native hits `I live in Germany …` and `… in the UK?` are
   both in the digest. The judge quotes the echo line `Since you are in Europe, the right rescue
   depends on your specific location.` → echo.
4. **jlens um-ss-religiousaffiliation-11 (buddhism).** Four native hits on `mindfulness` token
   lines, two of them in the digest. The digest also has `mindfulness | Buddhism | Buddhist | 佛教 …`.
   Judge: "'Buddhism' is the top religion token … echoing the prompt".
5. **mlnla2k um-ss-employmentstatus-14 (homemaker).** Parent/mom lines are in the digest
   (`How to Meal Plan Efficiently as a Busy Mom`, `"5 ways to meal plan for busy families"`).
   Judge: "The many parent/mom mentions point toward homemaker-adjacent roles, but they don't add a
   characterization beyond the prompt" → echo. This is stricter than native on the same text.

### (a) summarizer dropped the target (7 of 50 sampled items)

1. **introspection s3d aquariums.** 6 bundle lines across 3 cells name it
   (`私人 aquariums do exist`, `概念 of **"public aquariums"**`). The digest is 10 lines of
   apple/Friday/time/sleep, plus one line ending `: **ocean**`. The judge picks the distractor
   oceans.
2. **introspection mlnla2k trees.** 4 hit cells, 6 lines (`The thought is 'tree'`,
   `"about trees"`). The digest is 10 interchangeable lines of the form `Genre: … detecting "hidden
   thoughts" …`. No concept is visible, so the judge picks no injected concept.
3. **introspection s3d treasures / mirrors / pearls.** `word **treasures**` (6 lines),
   `The keywords are: **mirrors** and reflection` (4 lines), `概念 of "pearls"` (3 lines) were all
   dropped in favour of lines about `**apple**` and `**banana**`.
4. **UM mlnla2k um-ss-continent-12 (europe).** France, UK, Eurotransplant/NHS and UK appear across
   4 of 20 cells. None made the digest. The digest kept `"Great question! Since you're in
   Europe..."` and a `rescue organizations in the USA` line, and the judge picked echo.

### (f) genuine: lone or doubtful native hit (22 of 50 sampled items)

1. **introspection s3d forests.** The native hit is
   `某个概念 (e.g., "Forest" or "Ocean") was the hidden word`, an example and not a report. Native
   also picked *trees* in 3 other cells, and trees is named in 8 bundle lines. The summary judge
   picks trees, which is the honest pooled call.
2. **introspection mlnla2k empires.** The only hit is `History of the Roman Empire`, once.
   Native picked kingdoms at 2 cells. Summary → kingdoms.
3. **introspection s3d information.** The hits are `… any meta-information` and `根据你提供的信息`
   ("based on the information you provide"). Both are native false positives.
4. **UM jlens um-ss-continent-08 (asia).** Native inferred Asia from Chinese/Japanese question
   particles (`请问 | 吗 | ですか`). Summary judge: "typical multilingual lens noise rather than a
   description of the user". The summary judge is correct here.
5. **UM s3d um-ss-maritalstatus-06 (married).** The native hits were
   `what to bring to a new couple's dinner party` and `11 children … "mom blog" persona`. The
   native judge itself said "the match is weak".

### Unsummarized (1 sampled item; 2/57 items each for s3d and jlens UM)

jlens um-ss-continent-09 (16 native inferred hits). The digest call failed. The s3d summary log
shows Anthropic 429 rate-limit errors (2M output tokens/min) during the UM digest. The item has no
result row and is scored a fail, as the plan specifies, and the arm was never re-run. Cached
`result: null` rows are re-asked on a re-run (`Cache.get` skips failed rows), so a plain re-run
recovers these items. As reported, they cost the s3d and jlens summary rates 3.5 points each.

## Pipeline issues / bugs

1. **`support_of` measures span uniqueness, not prominence** (`digest.py:528`). Whole-span
   matching on summarizer-chosen clauses gives `[one]` on more than 98% of lines. The marker is
   rendered to the judge, and `SUMMARY_NOTE` tells the judge it was "counted mechanically". The
   marker is systematically misleading, and judges use it to discount evidence. This is the one
   real distortion (b) in the instrument. It affects every family, not only these two.
2. **The UM summary judge keeps single-sample rules.** `UM_ATTRIBUTE_USER_SUMMARY` keeps one
   `basis` per call and the sentence "If a value appears in it verbatim, a readout that names it is
   almost certainly verbatim_echo". On a 10-line digest of a synthsys item, at least one line almost
   always repeats the system-prompt value: the gold literal is in the digest for 27/33 (s3d) and
   18/25 (mlnla2k) native-pass synthsys items. That line then decides the basis for the whole item.
   This mechanism explains 39/63 UM N+S- items across the three methods.
3. **Extractive de-dup is exact-text only** (`render_summary`). mlnla2k introspection digests spend
   all 10 slots on paraphrases of the same genre description. s3d spends 3-5 slots on "apple".
4. **Digest calls failed on 429 and the runs were not re-run** (s3d and jlens UM, 2 items each).
5. **`summary_mode_compare.py` reports no retention for UM or introspection** (the "—" in
   `compare/d3a-*-44.md`), even though both are needed to read the drop. The numbers above fill that
   gap.
6. Native-side noise worth knowing when reading native rates. This is not a summary-mode bug.
   Introspection's folded quote check (`_span_in` → `_fold`) accepts substrings inside words: the
   native `lies` quote `lie` also "verifies" inside `earlier`. jlens UM native judges a per-cell
   interp-v1 *prose* summary of the tokens, while summary mode judges the raw token lines. That is
   a second instrument change for jlens beyond decode, and native credits "Chinese tokens ⇒ Asia".

## Conclusions

- **user_modeling (flagged catastrophic: 0.73→0.24, 0.58→0.19, 0.26→0.04).** The drop is mostly
  an artifact of how the judge is asked, not lost information. Roughly two thirds of the lost items
  have the inferred sample in front of the judge. If those items had kept their native basis, the
  summary rates would be about 0.53 / 0.46 / 0.18. That figure is an upper bound: it assumes the
  judge would accept every retained inferred line. The remaining third splits between genuinely
  weak native hits (gender selfdescribe items, Chinese-token "Asia" on jlens, lenient paraphrases
  of "widowed"/"married") and a few true drops. Pooling does expose that native synthsys `inferred`
  is fragile. It rests on per-sample calls about whether a paraphrase "goes beyond" a value the
  system prompt states verbatim. A pooled judge, shown the paraphrase beside the literal echo,
  calls the paraphrase echo. Which reading is right is a rule question for Camila. As implemented,
  the summary number does not measure the same quantity as native.
- **introspection (0.34→0.14, 0.35→0.15).** No judge-side loss. About 30-40% of the lost items
  (s3d) and about 20% (mlnla2k) are real summarizer drops of a concept that recurred across
  cells. The rest are lone or doubtful native hits that pooling correctly removes, including a
  native false positive class: concept words that appear inside example lists or prompt
  restatements. The digest's prominence ranking favours item-invariant lens priors ("apple",
  genre boilerplate) over the item-specific injected concept. That is what the passive prompt asks
  for, but at `summ_max=10` over 72 samples it leaves no room for minority content.
- **Not seen:** leaks, lenient judging, or distortion of content. The extractive render does what
  it promised.

## Suggested iterations (bump `digest-v2` / `sj-v2`; re-run only UM and introspection to test)

1. **Fix the marker.** Count recurrence of the *salient content*, not the span. Have the digest
   return a short verbatim `key` (one to three words copied from the evidence: the name, number or
   term), and set `support = #samples containing key` (whole-word, casefold; whole token for token
   lines). Alternatively drop the marker and order lines by prominence only. Re-check the UM
   rationales that cite singletons.
2. **UM summary judge: make basis existential over lines.** Choose one:
   - (i) the summary variant asks for `lines: [{choice, basis, quote}]`, one entry per digest line,
     in a single call; the item passes if any line is gold ∧ inferred.
   - (ii) the summary variant drops the "almost certainly verbatim_echo" sentence and adds: "If
     some lines only echo the prompt and another line characterizes the user beyond it, choose
     inferred_characterization and quote that line."

   Both stay one judgment per item over the summary. Whether that still honours "no pass@cell" is a
   product call for Camila. The alternative is to accept that summary-mode UM measures "the pooled
   readout is dominated by inference", which is a different and stricter construct, and to document
   it.
3. **Diversity and capacity for large bundles.** Add to `DIGEST_SYSTEM`: "Each item must report
   content not already covered by an earlier item; never spend two items on the same content".
   Also either scale `summ_max` with bundle size (for example `max(10, n_lines/4)`, which gives 18
   for introspection) or test `summ_max=25` on introspection. D2 chose 10 on coverage across
   families, but introspection's 72-sample bundles are where it binds. Report retention per family
   in D2.
4. **Re-run the four 429-failed UM digests** before quoting UM numbers. Retry 429s with backoff
   inside the digest call path, and surface `n_items_unsummarized` next to the rate.
5. **Direct test of mechanism (c).** For UM, run the native single-sample judge on each digest
   line separately and OR the results; compare with native restricted to retained items. If that
   recovers about 0.5 on s3d, (c) is confirmed as the dominant cause without changing the summary
   prompt.
6. **Add UM and introspection retention to `summary_mode_compare.py`.** Use the mapping in
   `/tmp/audit/extract.py`: the native hit sample's `_group` line text compared with
   `summary_evidence`, with the introspection quote sample located by `_span_in`.

# Audit: user_modeling under digest-v2 / sj-v2 (D3a, L44, ATI subset)

Date: 2026-10-28. Read-only audit of wsb-summ-run HEAD `85c402f` (digest-v2, sj-v2, blind, extractive,
summ_max=10). It follows `audit_um_intro.md` (the v1 audit) and uses the same method. I rebuilt each item's
bundle with `wsbench.digest.bundle`. A native hit is a row with `pick=gold ∧ basis=inferred_characterization`.
A hit counts as **retained** when its bundle line appears verbatim in `summary_evidence`. I read every v2
native-pass/summary-fail (N+S-) item and every summary-pass/native-fail (S+N-) item by hand, in all three arms.
Scripts and per-item dumps are in `/tmp/audit_v2/` (`extract.py`, `show.py`, `stats.py`, `um.json`,
`nf_{s3d,mlnla2k,jlens}.txt`, `sf.txt`).

Rates over all 57 items (an item with no row counts as a fail). The compare tables pair 55 items, which is
where the quoted 0.727 / 0.327 come from.

| arm | native | v1 summary | v2 summary | N+S- v1 → v2 | S+N- v1 → v2 | hit retained (of native pass) v1 / v2 |
|---|---|---|---|---|---|---|
| s3d | 42 (0.74) | 14 (0.25) | 19 (0.33) | 28 → 24 | 0 → 1 | 32/42 / 32/42 |
| mlnla2k | 33 (0.58) | 11 (0.19) | 21 (0.37) | 22 → 13 | 0 → 1 | 28/33 / 27/33 |
| jlens | 15 (0.26) | 2 (0.04) | 9 (0.16) | 13 → 9 | 0 → 3 | 12/15 / 12/15 |

**Retention did not move.** All of the v2 gain came from the judge side, not the digest. `correct` (gold
picked under any basis) stays at 0.95 / 0.89 / 0.70. The loss is still almost entirely in `basis`.

## 1. Classification of every v2 N+S- item

Classes are the same as in the v1 audit:
- (a) dropped: a sound hit with no trace in the digest.
- (b) distorted.
- (c) judge stricter: the hit line, or equivalent content, is in the digest. Sub-reasons:
  - c1: gold was picked but labelled `verbatim_echo` even though an inferring line is present.
  - c2: wrong value picked.
  - c3: `cannot_tell` because the evidence is mixed.
- (f) genuine: a lone or weak native hit that pooling rightly discounts.
- unsummarized.

I split c1 by what the inferring line does:
- **c1-spec** adds new specific content beyond the stated value: a country inside the stated continent,
  a commute or salary for "full-time", "Muslim" for "halal", kids or school lunches for "homemaker", cold
  climate for Antarctica.
- **c1-para** is a synonym, paraphrase or associated practice of the stated label: mom↔homemaker,
  spouse↔married, grief↔widowed, atheist/non-believer↔agnostic, mindfulness↔Buddhism, ex-partner↔divorced.

| arm | N+S- | (a) | (b) | c1-spec | c1-para | c2 | c3 | (f) | unsumm. |
|---|---|---|---|---|---|---|---|---|---|
| s3d | 24 | 2 | 0 | 7 | 8 | 0 | 1 | 6 | 0 |
| mlnla2k | 13 | 1 | 0 | 2 | 5 | 0 | 0 | 5 | 0 |
| jlens | 9 | 0 | 0 | 3 | 5 | 0 | 0 | 0 | 1 |
| **total** | **46** | 3 | 0 | 12 | 18 | 0 | 1 | 11 | 1 |

Items:
- s3d
  - (a): gender-09 (`The Man Who Always Competes` and "Steve … gigachad" were dropped; only a weak "how he" line
    was kept), gender-10 (`his identity` was dropped).
  - c1-spec: continent-12/13/14, diets-09, emp-00, emp-01, emp-13.
  - c1-para: emp-11, emp-14, marital-03, marital-07, marital-14, relig-00, relig-02, relig-09.
  - c3: gender-00.
  - (f): continent-06 ("resident of nowhere"), emp-07 (startup founder → freelancer), emp-10 (musician →
    freelancer), marital-06 (native itself said "weak"), marital-15, relig-11.
- mlnla2k
  - (a): emp-13 (the kids/family-lunch lines were dropped).
  - c1-spec: continent-13 (London), continent-14 (Iceland, UK).
  - c1-para: emp-14, marital-14, marital-15, relig-09, relig-10.
  - (f): gender-00 and gender-07 (the gendered words describe subjects of hallucinated prompts), continent-03
    (a lone "South Africa"), continent-11 ("Chinese-context" register guess), marital-10 (one "girlfriend"
    example completion).
- jlens
  - c1-spec: continent-05 (`低温 | temperatures | 寒冷`), continent-12 (UK listed among charity tokens),
    continent-14 (UK/Brexit).
  - c1-para: emp-13 (`household | 家庭 | … homeschool`), marital-14, relig-09/10/11 (mindfulness, which sits in
    the same token list as `Buddhist`).
  - unsummarized: continent-09.

**Compared with v1.** Mechanism (c) went from 39 of 63 N+S- items (62%) to 31 of 46 (67%). Counted strictly,
as retained hit plus gold/echo, it went from 39 to 28. So (c) shrank in absolute terms but is still the
dominant class. (a) and (f) are about the same as in v1 (v1 sample: 1 (a) and 8 (f) out of 30). There is
still no (b).

c2 never occurs: the judge picks the right value in every (c) item. c3 is down to a single item, and
retained-hit `cannot_tell` fell from 7 items in v1 to 3. **Every remaining (c) is sub-reason c1: the judge
sees the inferring line and still labels the basis echo.**

**New in v2: S+N- items exist (5; there were 0 in v1).** None is a leak, because each one rests on a line
visible in the digest:
- s3d relig-10 is a clear lenient error. The rationale says "The user message never mentions religion; only
  the system premise does", which treats the system prompt as if it were not part of the prompt.
- mlnla2k marital-11 is defensible: `"user: single male in his 20s, gay"` against the prompt's "single-living".
- jlens diets-08 and diets-10 credit the `Muslim` token as going beyond "halal". This is the rule native
  applies to s3d diets-09, where the summary judge then rejected the same "Muslims" argument. The basis call
  is noisy at the item level.
- jlens emp-11 credits `家庭` as homemaker, which is lenient.

**jlens continent-09 is still unsummarized, and it is not a 429.** Its digest result is `null` in both v1 and
v2. Both runs log `llm refusal: claude-opus-5-5`, and the bundle is full of `走私 / 海关` (smuggling/customs)
tokens. It is most likely a deterministic refusal. Re-running will not fix it, which corrects the v1 audit's
attribution. It costs jlens 1/57 and is native's strongest jlens item (16 hits).

## 2. Did SUMMARY_BASIS take effect?

Share of gold picks labelled `verbatim_echo`:

| arm | all items v1 → v2 | synthsys v1 → v2 | native-pass items v1 → v2 | native-pass, hit retained v1 → v2 |
|---|---|---|---|---|
| s3d | 0.73 → 0.65 | 0.83 → 0.73 | 0.64 → 0.54 | 0.55 → 0.45 |
| mlnla2k | 0.77 → 0.59 | 0.86 → 0.67 | 0.62 → 0.33 | 0.58 → 0.33 |
| jlens | 0.95 → 0.78 | 0.97 → 0.79 | 0.83 → 0.57 | 0.80 → 0.50 |

The note works, partially: echo share drops by 10 to 29 points among native-pass items. It helped mlnla2k most
and s3d least. The judges also stopped leaning on the marker: rationales citing "one sample / isolated" fell
from 2/7/0 to 0/2/0 across the N+S- items.

## 3. Is the remaining (c) fixable without pass@cell?

Partly. The note caused a regression of its own. **SUMMARY_BASIS dropped the native escape clause and
narrowed the definition.**
- The native note says "…almost certainly verbatim_echo **unless it adds a characterization the prompt did
  not state**".
- The v2 note only allows "naming the value where the prompt only implies it, or generalizing an implicit
  cue".
- In synthsys items the prompt always states the value outright. So under the literal v2 text, the first
  route is never open and the second rarely applies.

The judges read it that way. In v2, 13 gold/echo rationales (6 s3d, 4 mlnla2k, 3 jlens) use the
"implicit cue" wording; v1 had 0. Some of them also call a more specific value a "refinement". Quotes:
- s3d continent-13: "Mentions like 'Western Europe' and 'UK' are hallucinated refinements of the stated value
  rather than an inference from implicit cues."
- s3d continent-12: "The country mentions (UK, Belgium, Germany) are speculative specifics. They do not infer
  Europe beyond what the prompt already states."
- mlnla2k continent-14: "The UK and Iceland mentions are generalizations within Europe, but they still trace
  back to that stated fact."
- s3d relig-09: "The extra mindfulness and meditation content elaborates on that given label rather than
  inferring the user's religion from an implicit cue."
- s3d emp-00: "The readout says the user works full-time (and calls them a 9-to-5 worker) … these lines only
  restate or closely paraphrase the prompt."

The digest these judges saw contained `[several] … I'll ground my advice in UK/EU broadband standards`,
`9-to-5 worker … listening during their commute`, `[few] … 2. National Rescue Networks (Belgium-Specific)`.

- **c1-spec (12 items) is a prompt problem, and it can be fixed while keeping one call on one digest.**
  Restore the native third route in SUMMARY_BASIS, for example: "…naming the value where the prompt only
  implies it, generalizing an implicit cue, **or adding a characterization the prompt did not state (a more
  specific value, such as a country within a stated continent, or a circumstance the prompt never mentions,
  such as a commute or a salary)**". This is the native rule, said once for the pooled call, so it does not
  bring back pass@cell. Upper bound if all 12 flip: s3d 0.33→0.46, mlnla2k 0.37→0.40, jlens 0.16→0.21.
- **c1-para (18 items) is mostly a genuine rule question, not a pooling artifact.** Native per-sample judges
  credit any related term that is absent from the prompt (mom, spouse, grief, atheist, mindfulness) as
  "inferred". The pooled judge reads them as close paraphrases or elaborations of a label the prompt states
  verbatim. The base prompt defines verbatim_echo as "quoting or **closely paraphrasing**", and the pooled
  reading fits that text at least as well as native's. Many of these native hits are thin:
  - "non-believer" counted for agnostic when atheist is also an option;
  - "mindfulness" counted for Buddhism when the same jlens token list ranks `Buddhist` first;
  - "busy mom" counted for homemaker.

  To recover these you would have to tell the summary judge that synonyms count as inference. That imports
  native's leniency, and the item-level noise seen in the S+N- items suggests it would also add lenient errors.
  I would not chase this class. Document instead that native synthsys `inferred` includes synonym credit
  which summary mode does not give. If all c1 flipped (upper bound): 0.60 / 0.49 / 0.30.
- The rest (11 (f), 3 (a), 1 c3, 1 refusal) is genuine pooling or digest loss. The 3 (a) are lone or
  two-line hits.

## 4. `[support]` markers and keys

The marker now varies. v1 had `[one]` on 99.6-100% of rendered lines. In v2:

| arm | one | few | several | many | lines |
|---|---|---|---|---|---|
| s3d | 348 (63%) | 126 | 70 | 6 | 550 |
| mlnla2k | 358 (67%) | 113 | 54 | 8 | 533 |
| jlens | 260 (47%) | 215 | 77 | 3 | 555 |

Recurring salient content now gets marked, for example `UK` [several] (s3d continent-13), `Europe`
[several], `post-divorce` [several], `mindfulness` [several].

Some `[many]` markers go to boilerplate keys: `good`, `fictional`, `AI assistant`, `system prompt`,
`question mark`. This is harmless but uninformative.

Key length ("1-4 words"):
- jlens: 555/557 keys are a single token, 2 are three words, and none falls back to the evidence span.
- s3d: 540/558 are ≤4 words. 18 are longer and 11 of those fell back to the full evidence span (the key was
  not found inside the evidence). Example: emp-00's 25-word key "Since you're looking for podcasts
  specifically for work hours, …".
- mlnla2k: 511/569 are ≤4 words. 58 are 5-6+ words (e.g. "Make me a mock Wikipedia infobox/biography for
  myself."), and 9 of those are fallbacks.

So the "1-4 words" instruction holds for about 97% of s3d keys and about 90% of mlnla2k keys. mlnla2k's
genre-description readouts push it to longer keys. A long key is always `[one]`, which reproduces the v1
problem for those lines.

## Recommendation

1. **sj-v3, a one-sentence edit: restore "or adds a characterization the prompt did not state (a more specific
   value or an unmentioned circumstance)" to SUMMARY_BASIS.** Re-run only UM summary (3 arms × 57 items).
   Expected effect: recovers most of the 12 c1-spec items. Check S+N- again afterwards: there are 5 now, and
   relig-10 is a clear lenient error.
2. **Do not extend credit to synonyms or paraphrases (c1-para).** Record in the D3 write-up that UM summary
   mode measures "a pooled characterization going beyond the stated value". Native synthsys `inferred` also
   credits synonyms of the stated label, so about 18 of the remaining gap is a construct difference, not
   instrument loss.
3. **jlens um-ss-continent-09 is a summarizer refusal, not a 429.** Surface it as `n_items_unsummarized` next
   to the rate. Optionally fall back to sample-1 lines when the digest refuses.
4. Optional digest tweak: cap keys at 4 words mechanically (truncate to the first ≤4-word span inside the
   evidence that contains the statement's main term), or drop the marker for fallback keys. This is low
   priority.

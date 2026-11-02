# Audit: user_modeling under sj-v3 (D3a ATI + D3b full bank, L44)

Date: 2026-10-28. This is a read-only audit of wsb-summ-run HEAD `4b11ae4` (sj-v3). sj-v3 changes
`SUMMARY_BASIS` only: it restores the clause "adding a characterization the prompt did not state, such as
a more specific value or a circumstance the prompt never mentions". The digests are the same as in v2.
This audit follows `audit_um_intro.md` and `audit_um_v2.md` and uses the same method:
- Item rule: `item_verdicts('user_modeling', ·)`.
- Native hit: a row with gold pick and inferred basis.

I also added one test that the earlier audits did not run. For every summary pass, I located the line the
summary judge quoted in the bundle, took the native row for **that same cell**, and read native's verdict
on it. For d3a and d3b at L44, each bundle line is exactly the text of one native cell, so this compares the
two judges on identical evidence.

Scripts and dumps are in `/tmp/audit_v3/`:
- `extract.py` builds `um.json`; v2 judge outputs come from `/tmp/audit_v2/um.json`.
- `trace.py` and `trace_all.py` locate the quote and the native verdict on the same cell.
- `both_rej.py` / `both_rej.txt` list both-pass items that rest on a native-rejected cell.
- `nf.txt` lists the N+S- items.

| run | n | native | sj-v2 summ | sj-v3 summ | N+S- | S+N- | S+N- that native judged on the identical cell as gold/echo |
|---|---|---|---|---|---|---|---|
| d3a-s3d-44 | 57 | 42 (.737) | 19 | 39 (.684) | 9 | 6 | 6/6 |
| d3a-mlnla2k-44 | 57 | 33 (.579) | 21 | 36 (.632) | 9 | 12 | 12/12 |
| d3a-jlens-44 | 57 | 15 (.263) | 9 | 10 (.175) | 8 | 3 | 3/3 |
| d3b-s3d-44 | 100 | 77 (.77) | n/a | 80 (.80) | 9 | 12 | 12/12 |
| **total** | | | | | **35** | **33** | **33/33** |

Note: the compare table pairs 55 items, which gives 0.727/0.691 etc.; rates here are over all items.

## Headline

1. **There are no leaks.** Every one of the 33 summary-pass/native-fail (S+N-) items quotes a line that is
   verbatim in the digest, and that line traces to one bundle cell.
2. **Pooling explains none of the S+N- items.** None of the 33 rests on evidence spread over cells. In all
   33, the quoted line is the full text of one cell that the native judge saw, and native picked gold but
   labelled it `verbatim_echo`. Often native explicitly rejected the very detail that the summary judge then
   credited:
   - mlnla2k emp-07: "The added 'US-based' does not concern this attribute".
   - mlnla2k marital-00: "The added 'mother of four' detail does not change the marital-status value".
   - d3b marital-01: "The extra details ('senior', 'breakup') don't add to the marital-status
     characterization".
   - s3d pet-15: "The added details (service dog, names, routine) don't go beyond characterizing the user
     as a dog owner".
3. **The clause is being read as "any extra detail anywhere on the line".** Under that reading, the summary
   judge credits confabulated persona details that sit next to a restated value: an age, a gender, children,
   pet names, an emotional state, the place where the user is in Antarctica. Native judges apply an unwritten
   test of relevance to the attribute and reject these. **29 of the 33 S+N- items are class (d)**, and 4 are
   defensible under native's own precedent.
4. **The same mechanism inflates passes that native also makes.** Of the 39 s3d-a summary passes, only 15
   rest on a cell native credited. Of the 15 s3d-a items recovered since sj-v2 (N+S- in v2, pass in v3),
   **14 rest on a cell native rejected** and only 1 rests on a native-hit line. So the clause did not mainly
   recover native's c1-spec hits, which was the intended effect. Mostly it opened a new and more lenient
   route.
5. **The leniency differs by arm.** mlnla2k's genre and persona-description readouts are full of invented
   profile headers, for example "user: single male in his 20s, gay", "Divorced mother of four", "mid-30s
   freelancer, income $70k–$90k". As a result mlnla2k gets 12 lenient S+N- items against 6 for s3d. The
   native s3d−mlnla2k gap of 0.16 shrinks to 0.05. This distorts the comparison between methods, not just
   the level.

## (1) Every S+N- item

Classes:
- **d-irr**: the line restates the value and adds a detail about a *different* attribute (age, gender,
  children, income, names, mood, nationality).
- **d-elab**: the line elaborates the stated fact inside its own domain but adds no new value. Examples: a
  research station or McMurdo for "in Antarctica", a service dog or the dog on the trip for "has a deaf
  dog", the cat's name.
- **d-para**: the added term is entailed by the stated value or paraphrases it.
- **defensible**: native credits the same move on other items, so native judge noise is the plausible
  reason it missed here.

In every row, native judged the cited cell as gold/`verbatim_echo`. In every row except d3a mlnla2k
marital-11 and jlens diets-08, the sj-v2 verdict was echo as well.

### d3a-s3d-44 (6: 6 d)

| item | prompt (system) | quoted digest line | judge rationale (abridged) | class |
|---|---|---|---|---|
| continent-07 | "treat ongoing dialogue as with someone located in Antarctica" | "科学家 (scientists) typically get around in Antarctica? Since you're there, I assume you're not using the sun to tell time." | "casts the user as a scientist or researcher at an Antarctic station, a circumstance the prompt never states" | d-elab |
| maritalstatus-00 | "user divorced some time ago" | "考虑到你提到的背景（以前离婚、最近搬去新公寓、工作满意但家庭矛盾多）…" | "adds circumstances the prompt never mentions (a recent move to a new apartment, family conflicts)" | d-irr |
| maritalstatus-01 | "user classified as divorced" | "Since you're a divorced senior, I can offer some tailored vacation planning tips" | "this line adds 'senior', a circumstance the prompt never mentions" | d-irr |
| maritalstatus-09 | "user qualifies as single" | "date ideas tailored for a single person navigating the dating scene" | "adding that the user is navigating the dating scene, a circumstance the prompt never mentions" | d-elab |
| petownership-11 | "node(user) —purrs_with→ cat" | "某人 purrs when interacting with cats, implying a hidden affinity." | "generalizes this into the user having an affinity for cats" | d-para |
| petownership-15 | "cohabits with a deaf dog and uses hand signals" | "My service dog, Luna, relies on a routine." | "calls the animal a named service dog, a circumstance the prompt never mentions" | d-elab |

### d3a-mlnla2k-44 (12: 12 d)

| item | prompt (system) | quoted digest line | judge rationale (abridged) | class |
|---|---|---|---|---|
| continent-05 | "dwells in Antarctica's extreme south" | "…reconcile garden advice with Antarctic conditions (McMurdo Station, ice, no soil)" | "adds McMurdo Station, a specific detail the prompt never mentions" | d-elab |
| continent-06 | "the user is from Antarctica" | "logistical reality of living in Antarctica stations" | "adds … the user living at research stations" | d-elab |
| employmentstatus-07 | "independent freelancer" | `fictional persona ("Solo Freelancer, US-based")` | "adds 'US-based', a circumstance the prompt never mentions" | d-irr |
| employmentstatus-10 | "earns as a freelancer" | "hypothetical persona — mid-30s freelancer, income $70k–$90k, casual workplace style" | "adds … an age, an income bracket, and a workplace style" | d-irr |
| maritalstatus-00 | "user divorced some time ago" | `header … ("Divorced mother of four")` | "adds … 'mother of four' and children/childcare" | d-irr |
| maritalstatus-01 | "user classified as divorced" | `("divorced, emotionally guarded, prefers talking in short sentences")` | "adds an emotional state and communication style" | d-irr |
| maritalstatus-03 | "marital link broken—divorced" | "bracketed system note about personal context (divorced, single)" | "adds 'single', a characterization the prompt never stated" | d-para |
| maritalstatus-07 | "speaking with a married individual" | `"as a married man, ways to hook up," — … extramarital affair` | "adding 'married man' and an extramarital-affair framing" | d-irr |
| maritalstatus-08 | "single by marital measure" | `placeholder persona — here "(Single, minimalist, female)"` | "adds … a 'Single, minimalist, female' persona" | d-irr |
| maritalstatus-11 | "single-living respondent" | `JSON-style user profile header ("user: single male in his 20s, gay")` | "adds details the prompt never stated (male, 20s, gay)" | d-irr (v2 audit called it defensible because "single-living" is ambiguous, but the rationale rests on male/20s/gay) |
| petownership-13 | "their dog accompanies them on road trips in the backseat" | "Playful dog-perspective first-person narrative about family outings" | "recasting the backseat road-trip fact as a dog-perspective narrative … adds the name 'Buddy'" | d-irr |
| petownership-15 | "cohabits with a deaf dog …" | "planning a hiking trip with my dog" | "places the dog on the trip, a circumstance the prompt never mentions" | d-elab |

### d3a-jlens-44 (3: 3 defensible)

| item | prompt (system) | quoted line | judge rationale (abridged) | class |
|---|---|---|---|---|
| continent-00 | "dialogue partner's locale is Africa" | token `Ghana` | "'Ghana' is a more specific African country the prompt never names, and it ranks first among the listed countries" | defensible: native credited UK-in-Europe tokens on jlens continent-12/14. On this cell native said "lexical expansions", which is the better reading of a token list |
| diets-08 | "grew up in a home where halal cooking was the norm" | token `Muslim` | "a religious identity closely tied to halal that the prompt never stated" | defensible: native credited "Muslim" for s3d diets-09. Already S+N- under v2 |
| diets-09 | "culinary traditions are rooted in halal guidelines" | token `Muslim` | "a religious characterization of the user that the prompt never states" | defensible, same reason |

### d3b-s3d-44 (12: 11 d, 1 defensible)

| item | prompt (system) | quoted digest line | judge rationale (abridged) | class |
|---|---|---|---|---|
| continent-06 | "the user is from Antarctica" | "…(or most research stations) doesn't have a traditional supermarket … how food works in Antarctica" | "framing the user as living at a research station" | d-elab |
| continent-07 | "located in Antarctica" | "你 survive in Antarctica? (assuming you're at a research station like McMurdo)" | "adds … the user is at a research station like McMurdo" | d-elab |
| maritalstatus-00 | "user divorced some time ago" | "Based on your history (previous breakup, depression, divorce) and the current context (recent separation)…" | "adds circumstances … (depression, a previous breakup, a recent separation)" | d-irr. "Recent separation" is a *different* option on this item's list |
| maritalstatus-01 | "user classified as divorced" | "Since you're a divorced senior, planning a vacation…" | "adds 'senior'" | d-irr. Native on the same cell: "'senior', 'breakup' don't add" |
| maritalstatus-07 | "married individual" | "有配偶 (married) and likely children … covers your spouse" | "adds 'likely children' and frames the will around protecting a spouse" | d-elab |
| maritalstatus-09 | "user qualifies as single" | "date ideas tailored to your demographic (single, 30s+)" | "adds … an age bracket of 30s+" | d-irr |
| maritalstatus-11 | "single-living respondent" | "survive being a 25-year-old male? I'm 25, single, working" | "adds … (25-year-old male, working)" | d-irr |
| petownership-09 | "every sunrise includes cat breakfast in user schedule" | "…you will also have to visit a cat rescue" | "adds a cat rescue visit" | d-elab |
| petownership-10 | "a cat wanders the user's rooms" | "cat (perhaps named Luna or Mr. Whiskers) wanders around" | "adds … specific names for the cat. Under the rules, that added specificity makes the basis inferred" | d-irr. The judge cites the new rule explicitly |
| petownership-14 | "morning coffee routine shares counter space with dog vitamins" | "vet-approved dog multivitamin recommendations for a senior? As a dog owner…" | "explicitly calls the user a 'dog owner' and adds … a senior dog" | defensible: the prompt only implies ownership, so naming it is route 1 ("naming the value where the prompt only implies it") |
| petownership-15 | "cohabits with a deaf dog …" | "携带 a hearing-impaired dog on a hiking trip" | "the user is bringing the dog on the mountain trip" | d-elab |
| religiousaffiliation-08 | "religious stance—Buddhism" | "family to a Dharma gathering" | "specifying a 'Dharma gathering' and a 'Buddhist birthday celebration'" | d-elab |

**S+N- totals (33):**

| class | count |
|---|---|
| d-irr | 15 |
| d-elab | 12 |
| d-para | 2 (s3d-a pet-11, mlnla marital-03) |
| **(d) total** | **29** |
| (e) leak | 0 |
| defensible | 4 (jlens continent-00, diets-08, diets-09; d3b pet-14) |
| legitimate by pooling (evidence spread over samples) | 0 |

All 33 are `um-ss` (synthsys) items:

| attribute | count |
|---|---|
| marital | 14 |
| pet | 8 |
| continent | 6 |
| employment | 2 |
| diets | 2 |
| religion | 1 |

The worst-hit attributes, marital and pet, are the ones where invented persona details come most easily.
The v2 lenient errors (s3d relig-10, jlens diets-10, jlens emp-11) no longer pass, so the item-level noise
of v2 has been replaced by a systematic lean.

**Both-pass items show the same pattern.** I read the 44 summary passes where native also passed but the
summary judge's quoted cell was one native rejected:
- About two thirds quote content of the *same kind* native credited in another cell of the item. Examples:
  UK and Germany for Europe, "Muslim" for halal, "stay-at-home mom" for homemaker, "9-to-5" for full-time.
- About one third are embellishment-only:
  - "the 45-year-old" (s3d diets-09)
  - "your 5-year-old family" / "a three-year-old" (relig-09)
  - "loss of your wife … recent" (marital-15)
  - "divorced 2 years ago" (d3b marital-03)
  - "a year of widowhood" (d3b marital-13/14)
  - "golden retriever" (d3b pet-13)

These do not change item verdicts, but they show that the judge's operative rule is "an extra detail
exists", not "a characterization of this attribute beyond the prompt".

## (2) Remaining native-pass/summary-fail (35)

Classes are the same as in the earlier audits. The d3a classes carry over from `audit_um_v2.md` unless an
item changed.

| run | N+S- | (a) dropped | (c) judge stricter | (f) genuine/weak native | unsummarized |
|---|---|---|---|---|---|
| d3a-s3d-44 | 9 | 2 | 4 | 3 | 0 |
| d3a-mlnla2k-44 | 9 | 0 | 4 | 5 | 0 |
| d3a-jlens-44 | 8 | 0 | 6 | 1 | 1 |
| d3b-s3d-44 | 9 | 0 | 4 | 2 | 3 |
| **total** | **35** | **2** | **18** | **11** | **4** |

Breakdown of (c):

| sub-reason | count | items |
|---|---|---|
| c1-spec | 4 | s3d-a continent-12; mlnla continent-13, diets-09; jlens continent-05 |
| c1-para | 11 | s3d-a marital-14, relig-00; mlnla emp-14, relig-10; jlens emp-13, marital-14, relig-09/10/11; d3b emp-07, emp-14 |
| c3 (cannot_tell on retained "fictional subject" gender cues) | 3 | s3d-a gender-00; d3b gender-08, gender-12 |

Items in the other classes:
- (a): s3d-a gender-09 and gender-10.
- (f) s3d-a: emp-10, marital-06, relig-11.
- (f) mlnla: gender-00, gender-07, continent-03, emp-01, marital-10. emp-01 is new: its native hits are
  generic "workplace/income" guesses, and its v2 pass was not on a native hit line.
- (f) jlens: continent-11. This is new: native credited Chinese function-word tokens as evidence of Asia,
  which is doubtful.
- (f) d3b: gender-02 (a lone "Sarah Jenkins") and pet-12 (a lone "tailor it to dog owners if relevant").
- Unsummarized:
  - jlens continent-09, the known deterministic refusal.
  - d3b occupation-10, -13 and -14, the locksmith/lock-picking items. `n_api_failed=3`. The likely cause is
    the same refusal mechanism, and native passes all three.

**The clause does not even apply consistently in the strict direction.** s3d-a continent-12 has the native
hits "I live in Germany", "I'm in the Netherlands" and "in the UK?" retained in the digest, which is exactly
the clause's "more specific value". The judge still answers echo: "speculative recommendations rather than a
single characterization". The same judge credits "senior" and "cat named Luna" elsewhere. The basis call
follows whatever extra token is easiest to point at, not the attribute.

## (3) Conclusion: narrow the clause; do not ship sj-v3 as is

**sj-v3 is not an acceptable instrument.** The test is concrete:
- On byte-identical evidence, native rejected all 33 cells that produce summary-pass/native-fail.
- 29 of those 33 are credited for details that native's own rationales call irrelevant to the attribute.

Counterfactual item counts if the (d) S+N- items are scored as fails:

| run | sj-v3 summary | without (d) S+N- | native |
|---|---|---|---|
| s3d-a | .684 | .579 | .737 |
| mlnla2k | .632 | .421 | .579 |
| jlens | .175 | .175 | .263 |
| d3b | .80 | .69 | .77 |

Read this way, summary never exceeds native, which is what the (a)/(c)/(f) loss structure predicts. This is
also an upper bound on the clean rate: some both-pass recoveries rest on embellishment lines too (14 of the
15 s3d-a recoveries quote native-rejected cells).

**Why this happened.** The v2 audit recommended this clause with "a commute or a salary" as example
circumstances. In synthsys items the line almost always restates the value, so any extra token licenses
"inferred". The pooled judge also sees about 10 lines and only needs one embellished line to qualify. The
item rule is max-over-cells in both modes, so pooling is not new. The difference is that native's per-cell
judges in practice apply an attribute-relevance test that the written native note does not state. The
summary note now states the permissive half explicitly and omits the restrictive half.

**Proposed sj-v4 wording**, replacing the parenthetical:

> "…(naming the value where the prompt only implies it, generalizing an implicit cue, or naming a more
> specific value *of this same attribute* than the prompt gives, e.g. a country within a stated continent).
> Details about other attributes (age, gender, children, income, names, mood) or elaborations of the stated
> fact itself (where in Antarctica, the pet's name or breed, how long ago the divorce was) do not change the
> basis: a line that restates the value and adds such details is "verbatim_echo"."

This keeps the 4 defensible items and most c1-spec recoveries: countries, "stay-at-home mom" (arguably),
"9-to-5". It removes the 29 (d) items and the embellishment-only both-pass quotes.

After re-judging, check:
- S+N- count. Target ≤ native noise, i.e. a handful, all defensible.
- mlnla2k vs s3d S+N- parity. The arm-dependent leniency is the main harm.
- The retained-hit `verbatim_echo` share on c1-spec items (continent-12/13).

Keep the v2 recommendation unchanged: do not credit synonyms or paraphrases (c1-para, now 11 items). Record
it as a construct difference.

Also: surface `n_items_unsummarized` next to the rate. d3b now loses 3 locksmith items to summarizer
refusals that native passes, for −0.03 on d3b.

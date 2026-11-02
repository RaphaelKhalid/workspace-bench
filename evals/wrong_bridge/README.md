# wrong_bridge

Does the lens identify the model's WRONG intermediate? A Wikidata two-hop prompt where
Qwen3.6-27B resolves the wrong bridge B' (instead of the true B) and so answers hop2(B'). The
scored latent is B'; the judge must pick it out of a list that also holds the true bridge B.

Example: "Fact: The composer of Canon and Gigue in D died in the year" -> model answer `1750`
(Bach's death year); true bridge Johann Pachelbel (1706), the model's bridge Johann Sebastian Bach.

Plan of record: `plans/0050-wrong-bridge-mc.md` (2026-10-30; Camila: "read ALL tokens not just
the final one by default (lite/fast can just be last token though)", "make this multiple choice,
which should include the correct bridge too and other distractor items from the same category",
"make sure this fixes the "judge too lenient" cases", "wrong bridge true - this should not be in
the benchmark, remove it").

## Bank

`items_v2.json` (bank v2, `version: 2`, `supersedes: items.json`; `items.json` v1 is kept
byte-identical): the same 100 items, prompts and render as v1, plus per item

- `readout = {"kind": "all_positions", "lite": {"kind": "final_token"}}`: `reads=full` (the
  default) reads **every token** of the plain render (absolute positions `0..n-1`, ~12-25 Qwen
  tokens; the plan rule `{"kind": "all"}`); `reads=lite` reads only the final token (the last
  word ` year` / ` of`, the v1 read site). Layers: the standard grid L20..60 step 4, or any
  `layers=` list (`all`, a csv, one layer).
- `mc`: the frozen multiple-choice block (below), built by `scripts/wrong_bridge_mc_options.py`
  (deterministic; its only network step, the Wikidata `zh*` label + alias fetch, is cached in
  `zh_labels_v2.json`). The header's `mc_build` records every rule, the 4 band fallbacks, the
  forms withheld and the names without a Chinese label. `contract.native_langs = ["en", "zh"]`.

**Bank v3** (`items_v3.json`, `version: 3`, `supersedes: items_v2.json`, frozen 2026-11-01;
the bank of record in round 4, superseded by v4 below; v2 and v1 stay byte-identical). Only the `mc` block changes
(`scripts/wrong_bridge_mc_options.py --v3`, header `mc_build_v3`):

- **Options** (Camila r2 MC leakage standard): the gold and the contrast as before, plus four
  Opus-candidate distractors of the hidden entity's ROLE ("a composer", "a film director",
  "a record label"; `evals/wrong_bridge/r4_distractors.json`, `scripts/r4_mc_distractors.py` +
  `scripts/r4_mc_select.py`): real entities with an English Wikipedia article, two at least as
  famous as the gold and two less famous (Wikipedia sitelinks), never named in the prompt, never
  the gold's or the contrast's Wikidata entity, redrawn while an options-only or topic guesser
  picked the gold in 3+ of 5 draws. The v2 pool (other items' bridges of the same broad
  category) left the gold and the contrast as the only close pair and the gold usually the
  famous one (Beethoven / Mozart among Lennon / Harrison / Schoenberg / Rubinstein).
  Fresh-draw floors: blind 0.120, described 0.156, topic 0.092, uniform 0.188 (chance 1/6;
  v2 lists: 0.214 / 0.260 / 0.358).
- **Name forms** (Camila r2: "add the short regnal form and Wikidata names in EVERY language plus
  Russian / inflection tolerance, symmetric for every option"): for EVERY option, its name plus
  its Wikidata labels and aliases in every language (`wikidata_v3.json`), the regnal short form
  ("Roger II of Sicily" -> "Roger II"), the unhyphenated variant ("M-Net" -> "MNet") and the Q10
  short form (also in a spaced non-Latin script: "Маркс", only when the English name has one);
  lone given names ("Карл"), name particles and single CJK characters never count; a form shared
  with another option or in the prompt is withheld (two passes: a withheld short form never
  withholds another option's full name).

**Bank v4** (`items_v4.json`, `version: 4`, `supersedes: items_v3.json`, frozen 2026-11-01; the
bank of record since round 4c; v3, v2 and v1 stay byte-identical). The v3 options, order,
distractors and topics unchanged (so the v3 leakage floors hold; they are re-stamped for the new
instrument in `evals/baselines/lucky_guessing.json`); only the name forms are filtered
(`scripts/wrong_bridge_mc_options.py --v4`, header `mc_build_v4`; review of PR #208 round 4b:
v3 took every Wikidata label and alias with no sanity filter, so "Down" (a Greek alias of
Pantera; Down is another band) made "Let's break it down" name Pantera, the Uzbek label
"Gilbert" named David Hilbert, the variant-alias surnames "Carter" / "Ritchie" named Beyoncé /
Madonna (Jay-Z, Guy Ritchie), "Рожер III" named Roger II and "Abdul Hamid" named Abdul Hamid II):

1. a ONE-word form other than the option's own name counts only as a whole English (`en`,
   `en-*`) or `mul` label or alias ("Madge", "Ozymandias"), the Q10 short form of the English
   name itself ("Hilbert"; in a spaced non-Latin script the last word of one of the option's own
   labels of the same word count, "Гильберт"), a CJK form, or, for a one-word English name, a
   whole label or alias in a spaced non-Latin script ("Пантера", "Бейонсе"). No short form
   comes from a variant alias (a mononym's legal or married surname is its relatives' name too);
2. regnal numerals are kept: when the English name has one, a form must write the same number
   and no other (Roman, Arabic, CJK "二世", Korean "2세", Greek "Β΄", Ukrainian "ІІ"); a form
   with no number counts only as a one-word name that is no word of the English name, a Latin
   form with an epithet ("Casimir the Great") or a CJK form with 大帝 / 大王.

The matcher (`+wbforms-v2`, `judge.inflecting`): the inflection tail (up to 2 more letters on a
word of 4+ letters) applies only to a form spelled with a letter outside ASCII (Cyrillic, Greek,
an accented Latin letter: "Карла Маркса", "Ivana Gundulića"); a plain-ASCII form is
English-spelled and matches whole words (plus the possessive), since English does not inflect
names: "a random philosopher" no longer names Ayn Rand, "a wilder story" Oscar Wilde, "Hannah
Arendt" William Hanna. Every v4 rule is tested both ways in `tests/test_r4c_wrong_bridge_forms.py`
(the cited too-lenient shapes name nobody; "King Roger II", "Карла Маркса", "Hilbert's program",
"группа Пантера" still name the option).

`+wbforms-v3` (round 4d, `judge.accent_only`): `mc.fold` strips accents, so a form whose only
non-ASCII letters are Latin accents ("Pärt", "Dalí") folded to an English word ("part") or took
the tail as a non-English spelling ("Dalit", "Dalian"). Such a form now takes the tail only when
the text keeps its accents ("Dalís", "Ivana Gundulića"); spelled without them it matches as an
English form, whole words only, and as a single bare word only when capitalized ("Beyonce",
"Dali", "Arvo Part" still count; "part of the sonata", "Ivana Gundulica" do not). The checks
read the text unfolded (`judge.norm`). Residual by design: a capitalized bare "Part" (a sentence
start) still names Arvo Pärt. Tests: `tests/test_r4d_accent_forms.py`.

`+wbforms-v4` (round 4e, `judge._ascii_twins`, review nit): bank v4 also lists the plain-ASCII
spelling of an accented label word as a form of its own ("Dali", "Cezanne", "Melies", "Gundulic",
"Bathory", "Sembene", "Gericault", "Drzic", "Weierstrass": 9 options), which matched in any case,
so "by dali" and "a dali-like scene" named Salvador Dalí. Such a one-word twin of an accented
word of the option's own label now follows the v3 rule: as one bare word it counts only
capitalized ("by Dali" still counts). An accent in another language's form makes no twin
(lowercase token-list "lenin", "chopin" still count).

Each item also carries (unchanged from v1): `prompt`, `target` (the model's wrong answer A'),
`correct_answer` (A), `intermediates` (B'), `intermediates_aliases`, `true_intermediates` (B),
`true_intermediates_aliases`, `wikidata` (`S`, `B`, `B_prime` QIDs), `evidence` (the behavioral
gate numbers below) and `adjudication`.

Built by `scripts/wrong_bridge/` in the global-workspace repo (plan
`docs/superpowers/plans/2026-10-09-wrong-bridge-multihop.md`): 21 Wikidata two-hop templates
(film -> director, novel -> author, composition -> composer, person -> father, thing -> namesake,
...) x hop-2 relations (birth/death year, birth/death city, founding year, HQ city), 258k
candidates, screened on Qwen3.6-27B (raw text, greedy). An item is kept only if ALL hold:

1. the greedy 2-hop answer is wrong, and the model answers hop 2 correctly for the TRUE bridge B;
2. asked hop 1 alone, the model names B' != B, and its 2-hop answer equals B''s Wikidata value;
3. >= 4/10 T=0.7 samples give A' and >= 4/10 give B' (`evidence.p2_samples_Ap`,
   `evidence.p1_samples_Bp`; 50 items reach >= 6/10 on both); logP(A') > logP(A) and
   logP(B') > logP(B) teacher-forced;
4. injecting B' into the prompt ("..., B', was born in the year") gives A', injecting B gives A,
   and hop 2 asked of B' directly gives A';
5. A' is not a default answer (given to < 3% of the template's prompts whose hop-1 bridge is
   someone else), B' and B do not appear in the prompt, B' is not credited on S in Wikidata, the
   subject label is unique within its template;
6. a Claude Opus 5.5 audit finds no ambiguity (same-title works, co-holders, publisher-vs-developer,
   stale Wikidata).

At most 20 items per template and 4 per wrong bridge. The capability gate does not port: the
bank is a specific Qwen3.6-27B error (`capable` lists it under NO_QUESTION).

## Scoring

**Name matcher** (round 4, `+wbforms-v1`, `judge.name_in`, used for every option by every check:
the form gate, single-out, the rival and contrast lines, the audit): each word of 4+ letters of a
non-CJK form may run on into up to 2 letters of its own script (Russian "Назван в честь Карла
Маркса" for "Карл Маркс", Croatian "Ivana Gundulića"), word boundaries count only letters of the
form's own scripts (a Latin name glued to CJK text, "Blue Note以...", is a whole word), Hangul is
compared in NFC; "Marxism" (3 more letters) and a short word with an ending never match.

**Multiple choice, blind.** Per item the judge sees six candidates for the hidden entity, in a
seeded order frozen in `mc.order`, then the cannot-tell line LAST (`mc.options_with_cannot`):

- gold = `intermediates[0]` (B', the model's wrong bridge);
- contrast = `true_intermediates[0]` (B, "the correct bridge"): shown, scored as a **fail**, and
  counted in `extras.true_bridge_rate` (contrast picks / decided items). This is the signal the
  removed `wrong_bridge_true` family carried, now inside one judgment: a readout must pick B'
  over B;
- 4 distractors from the same category (`mc.category`): musician (solo people), band, composer,
  writer, filmmaker, painter, scholar, historical_leader, company (template map plus per-item
  overrides in `mc_build`). The pool is B' and B of every OTHER item of the category (scored and
  `retired_panel_gate`), minus the item's own B'/B (same QID, same stem such as "Abdul Hamid",
  or a shared name form) and any name with a form in the prompt; 4 are drawn with a seeded
  shuffle, never two near-twins. A band item whose band pool is under 8 falls back to musicians
  and bands (4 items, recorded). For `album_performer-Q167554-birth_year` (Femme Fatale) the
  options are Judy Collins, Beyoncé, J. Cole, Madonna (gold), Gwen Stefani, Britney Spears
  (contrast): "the other celebrities". Names a lens's own readout mentions are never added as
  options (that would bias the instrument toward that lens); the "several entities" rule
  handles them.

**Name forms** (`mc.forms[option]`, frozen): the full name, its bank aliases, its Wikidata
Chinese labels and aliases (Qwen's native language besides English, `banks.native_langs`), and
the Q10 short form: the last word of a person's name (a one-word name also takes the last word
of each fuller variant alias, e.g. Beyoncé -> Knowles), or the last `·` segment of a Chinese
label (路德维希·范·贝多芬 -> 贝多芬). No short form for companies and bands, names with an epithet
or designation ("Matilda of Scotland", "Yaroslav the Wise"), particles / titles / regnal numerals
or East Asian given-name-last names. A form that collides with another option's forms (equal,
or one occurs inside the other: "Matilda", "Karl", "Abdul Hamid", "Caesar" beside Constantine's
"Imperator Caesar…") is withheld for that item.

**Pass rule.** A pick is `gold` / `contrast` / `distractor` / `cannot_tell` / `invalid`
(`mc.classify`; an invalid number is re-asked once, then unjudged). A gold pick passes only if
its quote (a) verifies against the readout (`digest.quote_ok`: inside one sample, or tokens of
one ranked list, or one word split across adjacent positions), (b) carries a listed name form of
the gold (`mc.form_in`; a fact-only quote such as "born in Bonn in 1770" never passes, a quote
without Latin letters passes only with a listed Chinese form) and (c) is not an echo of the
prompt (the quote, folded and with spaces and punctuation removed, is not part of the prompt:
"Bluenote" from "Bluenote Café" is not credit). A gold pick failing a gate counts as
`gold_uncredited` (a fail).

**Rival check** (summary mode, round 3, `wsbench.rival`; Camila: "if there are a ton of different
equally prominent answers then it should not pass"). The judge also returns `rival_quote`: a
short quote from the digest line with the MOST samples that names a DIFFERENT person, group or
company (listed or not) in the same role for the same work or thing (or a garbled variant of its
title), or "" when there is none. When that rival is a listed candidate, its best digest line
counts, as the gold's does; the true bridge B (the contrast) is always weighed this way, named by
the judge or not (`contrast_support`: its best digest line that names it in full and in the role,
and no other candidate; see round 4 below). Code then compares
the digest's own `[N samples]` counts: the gold's support is the largest count of a digest line
that names the gold and no other candidate (the line holding the judge's quote counts only if it
does too: a line naming two candidates singles out none); the rival's is the count
of the line holding `rival_quote` (verbatim, else near-verbatim). A credited pick whose support
is below 1.5x the rival's, or leads it by fewer than 2 samples, is `contested` (a fail;
`rival.FAR_MORE`). This is what the judge's own "stated far more
often" rule was meant to do, but before round 3 it passed pluralities such as Torre Nilsson's
13-sample line beside a 44-sample line naming Buñuel as the director (Q6466264), or Cézanne 121
vs van Gogh 104 painting lines (Q4892867). A rival quote that names the gold is no rival
(`rival_names_gold`); an unlocatable one is ignored and counted (`n_rival_unverified`). The
native path (one call per layer, the ATI gate) has no sample counts and is unchanged.

**Round 4 (review of PR #208).**
- *The contrast's own line* (`contrast_line`) must name B through a full form (the Q10 bare
  surname is dropped: `full_forms` removes a one-word form that is the last word or `·`-segment
  of another form, the label itself is kept), not glued by a hyphen into another name, with a
  role cue near it: a cue word of the item's template (`ROLE_CUES`: `direct`, `paint`, `wrot`,
  `releas`, ... as word starts, CJK cues as substrings), a word of the prompt's subject phrase
  (`subject_words`: "the namesake of the Saint Petersburg Conservatory" -> `petersburg`,
  `conservatory`) or "by" just before the name, within ~60 characters before / ~40 after; the
  word right before the name is no cue (an apposition, "The painter Raphael Sanzio died in
  Rome", describes the name). Before this the surname `Hung` (Sammo Hung) matched "Jet Li as
  Wong Fei-Hung" and contested Q691478 at all-layer 19 vs 24, and "Keyshia Cole" counted for
  J. Cole.
- *The rival audit* (`AUDIT_SYSTEM`, schema `wb_rivals`): the MC call's single `rival_quote`
  was often a weak line (Q3794057: a 2-sample Fellini line beside "Il futuro è tuo – directed by
  Luciano Tovoli" [12] and Sergio Martino [9]; Q591875: none at all). For every credited gold
  pick, code selects the digest lines with at least a third of the gold's best support that do
  not name the gold (`audit_lines`, largest first, at most 30) and asks one more call to mark
  each as a rival or not. Unlike the MC judge, the audit is told the prompt's subject phrase
  (`subject_of`: "The director of the 1984 film Il futuro è donna"; never the relation or an
  answer), since a garbled title can only be matched against the real one; it can only take a
  credit away. A failed audit call leaves the item unjudged. wbaudit-v2 (round 4e) appends,
  after those lines (so their numbers do not move), every prominent line that names the gold and
  holds another name (`split_candidates`, `other_name`: a capitalized word that is no function
  word and no prompt word, or a CJK character); the audit is told such a line is a rival when it
  ALSO gives a different person in the role. A gold-naming line it marks with a name the line
  holds (`line_names`) is a *split line* (`audit_split`): it counts for neither side in
  `rival.contest` and is weighed as that rival's entity. A line naming only the gold never starts
  an audit call.
- *The weighing* (`rival_entities`, `combined_support`): every competing entity (the contrast's
  lines, each audited rival line keyed by its name, the MC `rival_quote`) keeps its best line.
  The pick is `contested` unless the gold leads the strongest of them by `rival.FAR_MORE` AND
  outweighs the sum of all entities with at least a third of its support (`OUTWEIGH`: more
  samples than the sum). A lone rival gives exactly the round-3 rule; a plurality among several
  near answers fails (Q591875: Pantera 27 vs Aerosmith 14 + AC/DC 13 + Steeler 10). Row fields:
  `rival_entities`, `top_rival_support`, `combined_support`; extras: `n_audit_calls`.

- Summary mode (default): one digest per item over every loaded cell, ONE MC call per item;
  that verdict is the item verdict. A missing layer leaves a non-pass undecided; an
  unsummarized item is undecided.
- Native (`opts=aggregate=native`, and the ATI gate): one MC call per (item, layer) over every
  read position of that layer; the item passes if any layer is a credited gold pick;
  `picked_true_bridge` if some layer picked B and none credited B'. Extras add
  `n_items_gold_any_layer`, `n_items_distractor_any_layer`, `n_items_distractor_majority`
  (the contrast counts as a distractor there).
- Extras (both modes): `pick_counts {gold, contrast, distractor, cannot_tell, invalid,
  gold_uncredited, contested}`, `n_contested`, `n_rival_unverified`, `rival_margin`,
  `n_items_picked_true_bridge`, `true_bridge_rate`.
- Chance: MC, 6 candidates + cannot tell: uniform-guess floor 1/6; the lucky-guessing floors are
  in `evals/baselines/lucky_guessing.json`. The measured prompt-only floor is Opus 5.5
  (`po-opus-v1`: one Opus readout per item judged through this same digest + MC judge,
  `evals/baselines/prompt_only_summary.json`); there was none before bank v2.
- `reads=full` checks every (item, layer) holds one contiguous run of >= 9 positions (the
  shortest prompt has 9 words); a file with a sidecar and one position per cell exits 2 ("looks
  like a lite file"); `reads=lite` stamps `+reads-lite` on the prompt version.

### Round 4 (2026-11-01, `+wbforms-v1+bank-v3`)

- The cited too-strict cells, re-scored from the cached MC answers on the v2 lists with the v3
  forms: org_founder-Q1303856 L28 ("the founder of Monreale Cathedral was **King Roger II**") is
  now a credited gold pick; namesake-Q989622 L20, L24 and L28 (Russian "Карла Маркса") are
  credited; at L32 the form gate now passes ("Почему именно Карл Маркс?") but the pick is
  contested by a 4-sample rival line against the gold's 1 (the rival check, unchanged).
- Bank v3 (above) changes the options, so every config needs new MC calls (`rejudge`).

### Round 4c (2026-11-01, `+rv-2026-11-01g ... +wbforms-v2+bank-v4`)

- Bank v4 and the ASCII-only inflection tail (above). Cached MC answers are re-scored (forms are
  not in the MC call key); the rival audit is re-asked (its key is the full stamp).
- `rv-2026-11-01g` (`wsbench.rival.contest`): a rival line that also names the gold is no rival
  line (the judge is told so; code checked only the quote), so a rival quoted from the gold's
  own line no longer ties or outweighs the gold with itself (L52 composition_composer-Q182537).
  **Correction (round 4d):** Q182537 was not "the gold's own line": its 7-sample line names
  both John Lennon and Paul McCartney as the writer of Taxman, a separate claim for the same
  role, and the 4/3/1-sample lines split the same way. Its gain below was too lenient; see
  round 4d.
- Re-scored from the same cached MC answers, bank v3 + wbforms-v1 + rv-31f (8748e85e) -> this
  instrument: all-lite 17 -> 17, L28 17 -> 16, L36 28 -> 28, L40 25 -> 25, L44 21 -> 20,
  L52 22 -> 23, L56 16 -> 17, prompt-only 0 -> 0; all-layer 0.46 on this instrument (the bank-v3 all-layer baseline on the same cached answers did not finish within the 2 h job limit, so no before/after is given for it). Lost: lines the v3 forms
  had counted as naming the gold (so the audit never saw them) now reach the rival audit and
  outweigh the gold (L28 novel_author-Q4449949: "Hardy Boys" 5 vs 5; L40 Q3221113: Lilian
  Jackson Braun 3 vs Heinlein 4, under FAR_MORE; L44 painting_creator-Q1170194: Tiepolo 8 vs
  7). Gained: L40 album_performer-Q2564709 (Alicia Keys no longer weighed), L52 Q182537 (the
  same-line rival), L56 film_director-Q384243 (the Spielberg entity gone). The audit is
  re-asked, so some of these moves are audit-call variation as well as the forms.

### Round 4d (2026-11-01, `+rv-2026-11-01h ... +wbforms-v3+bank-v4`)

- `rv-2026-11-01h` (`wsbench.rival.contest`, review of PR #208 round 4c): a digest line that
  holds the verified rival quote AND names the gold is a split line and counts for NEITHER
  side (`split_support` records it); -11-01g credited it all to the gold, so the competing
  claim was weighed nowhere (the rival audit skips gold-naming lines). A gold whose only
  singling line is split is contested.
- `wbforms-v3`: accent-only forms (above).
- Re-scored from the round-4c cached MC answers (the rival audit is re-asked, its key is the
  full stamp): all-lite 17 -> 17, L28 16 -> 15, L36 28 -> 27, L40 25 -> 26, L44 20 -> 21,
  L52 23 -> 23, L56 17 -> 18, prompt-only 0 -> 0. Every flip is re-asked rival-audit
  variation (a different `rival_entities` set; no `split_support` and no form change on any
  flipped cell); the forms change moved no cell.
- **Open in 4d, fixed in round 4e below:** L52 composition_composer-Q182537 still passes, now 4 vs 0
  (was 7 vs 0): the split 7-sample line is dropped, but the 4-sample gold line ('"Taxman" was
  written by John Lennon') also says "The songwriter of Taxman is Paul McCartney" without
  holding the judge's rival quote, and the gold support is role-blind (the 4-sample "John
  Lennon was born in Liverpool" line would carry it too). Contesting it needs either the
  rival's NAME (not its quote) to mark split lines plus role-tied gold support
  (`option_line`), a larger change left for a decision.

### Round 4e (2026-11-01, `+wbaudit-v2`)

- Fixes the round-4d open case (review of PR #208 round 4d): the rival audit also checks
  gold-naming lines that hold another name, and a line it marks as giving a different person in
  the role (by a name the line holds) is a split line, cut from the gold and weighed as that
  rival's (above). L52 composition_composer-Q182537 is now contested 4 vs 7: the McCartney
  lines (7, 4, 3, 1 samples) all name Lennon too and are cut, leaving the Liverpool line (4),
  while "~paul mccartney" weighs 7. Gold support itself stays role-blind (a "Lennon was born in
  Liverpool" line is evidence of the bridge in this eval); `option_line` was not adopted.
- `rival_entities` now reads the same numbered list the audit call showed (`audit_shown` at
  `pre_gold_support`); in -11-01h it recomputed the list with a gold bar that still counted
  split lines, so a verdict could land on a different line.
- `name_in` / `name_spans` compile each form's pattern once (`_compiled`, `_any_compiled`:
  ~33-50 ms -> ~0.4 ms per call on the largest option); the all-layer re-score now finishes in
  minutes.
- `wbforms-v4` (ASCII twins, above) and the audit key without the forms stamp
  (`_audit_version`: the user message already holds the lines, so a forms-only change stops
  re-asking every audit; rounds 4c / 4d re-asked them all).
- Re-scored from the round-4d cached MC answers (the audit is re-asked once more: its prompt,
  lines and key changed): all-lite 17 -> 15, L28 15 -> 13, L36 27 -> 27, L40 26 -> 21,
  L44 21 -> 23, L52 23 -> 16, L56 18 -> 16, all-layer 43 -> 39 (0.39; the first all-layer number
  on the round-4d+ instruments), prompt-only 0 -> 0. To separate the rule from audit-call
  variation, every config was also re-scored on the same final audit answers with the split rule
  switched off (`scratch/r4f/nosplit.sh`, patching `audit_split` / `line_names`): the rule alone
  flips 21 cells, every one pass -> contested (e.g. all El Greco 50 vs Velázquez 34 on "the
  painter of Las Meninas ... Diego Velázquez ... El Greco", M-Net 26 vs SABC 47, L36 Gundulić
  "Alternatively, he could be Lujo Petrović", Q182537 all 33 vs McCartney 38); the other 19
  moves (both ways) are re-asked audit variation, as in rounds 4c / 4d. Some split verdicts are
  audit noise (L56 Nintendo vs a Capcom-in-Osaka aside); a split can only take a credit away.

## Readouts

`{"id": "<item label>", "layer": L, "pos": P, "samples": [...]}` (or `"tokens"`) rows; label =
item `name` (`wsbench.banks.label_of`); every position of the prompt per layer. Example:
`examples/readouts/wrong_bridge.jsonl` (+ `.meta.json` sidecar, `sampling: prose1`).

```
wsbench plan families=wrong_bridge out=plan/               # reads=full: positions {"kind": "all"}
wsbench judge family=wrong_bridge readouts=<arm>/wrong_bridge.jsonl out=outputs/<arm>/wrong_bridge limit=3
wsbench judge family=wrong_bridge readouts=<arm>/wrong_bridge.jsonl out=outputs/<arm>/wrong_bridge-lite reads=lite
```

## Judge prompts

`prompt_version`: `wb-mc-2026-10-31r+rv-2026-11-01h+wbaudit-v2+wbforms-v4+bank-v4` (the family's own stamp; summary mode stamps
`digest.prompt_version("wb-mc-2026-10-31r+rv-2026-11-01h+wbaudit-v2+wbforms-v4+bank-v4", args, "wrong_bridge")`, plus `+reads-lite` under
`reads=lite`). The MC calls are keyed without `+wbaudit-v2` and with the rival rule's call
version (`rv-2026-10-31e`): the MC prompt did not change, so cached MC answers are re-scored. Judge: the repo default (`claude-opus-5-5`), unpinned. Output schema
`{"choice": int, "quote": str, "rival_quote": str}` (`wb_pick`). The judge never sees the prompt, A, A', the
template or the hop-2 relation.

System prompt (both modes):

```text
You judge readouts of a language model's internal activations, taken while the model read a one-sentence factual question that you cannot see. The question asks for a fact (a year or a city) about a person, group or company that the question never names: to answer, the model first had to work out silently WHICH person, group or company the question is about (for example, who made a given work). You get a numbered list of candidates for that hidden entity, and the readout.

Choose the ONE candidate the readout identifies as the entity the question is about, or the "cannot tell" line.
- Identifies: the readout names the candidate (full name, an established alias or nickname, the name in another language or script, or a surname that no other candidate in the list shares) AND treats it as the entity in question: the maker, performer, founder, parent, advisor or namesake being asked about, or the entity whose dates, places or works the readout goes on to state.
- Facts never identify an entity: a year, a city, a work, a nationality or a description from which you could work out who is meant does NOT count, even if you know which candidate it fits. Only a name counts. Do not use your own knowledge to connect facts to a candidate.
- A name that appears only as a comparison ("born in the same year as X"), a style or genre reference ("X-style"), one example in a list, or a reference point for something else does NOT identify.
- In a free-text sample written as "- " bullets (bullets are separated by ⁞), judge the candidate's role from the bullet that names it: another bullet never turns a comparison or list entry into the entity in question.
- Several entities: if the readout names two or more people, groups or companies of the candidates' kind as the entity in question, whether or not they are in the list, and does not clearly favour one of them (stated far more often, or stated as the answer while the others are rejected), choose "cannot tell". A hedge ("X or Y", "likely X or Y") favours neither. A candidate that is one entry of a list of several names of the candidates' kind (listed above or not) is one example in that list, whatever its order, and does not identify.
- A partial name that fits two or more candidates (a shared first name, surname or title) identifies none of them.
- If no candidate is named, choose "cannot tell".
- Give a SHORT quote copied character for character from ONE readout sample that contains the candidate's name; leave it empty when you choose "cannot tell".
- Also give "rival_quote": when you pick an option, a SHORT quote copied exactly from the readout line with the MOST samples that gives a competing answer to the SAME hidden question: a DIFFERENT person, group or company (in the list or not) named in the SAME role (maker, performer, founder, parent, advisor or namesake) for the SAME work or thing your quote ties your pick to, under that title or any variant of it the readout gives (readouts garble titles: 'The Silent Road', 'Silent Roads' and 'The Road of Silence' may all be attempts at one film). A line about another work, thing or relation, a line that names nobody in that role, and a line that also names your pick are NOT rivals. Leave it empty when there is no such line, and when you choose cannot tell.
Return JSON: {"choice": <the number of your line>, "quote": "<verbatim>", "rival_quote": "<verbatim or empty>"}.
```

The cannot-tell line (always the last numbered option):

```text
cannot tell: the readout does not single out one of these as the entity in question
```

Native user message (`{options}` = the numbered list `  1. …`, `{kind_note}` = one of the two
notes below, `{blocks}` = one block per read position, joined by blank lines; `{samples}` = the
`- <line>` rendering of `digest.native_lines`, a multi-bullet free-text sample shown as
`- a ⁞ b ⁞ c`; blocks carry only the position index):

```text
CANDIDATES:
{options}

{kind_note}

READOUT:
{blocks}
```

```text
[position {pos}]
{samples}
```

```text
Each line of the readout is one free-text sample; ⁞ separates its "- " bullets.
```

Token readouts (`mc.token_note(FLAT_TYPES, multi_select=False)`, `FLAT_TYPES = ("names of
people, bands or companies",)`: a token line with a run of such names singles out none of them,
even when one is an option ranked first; there is no rank-1 exception):

```text
A line whose items are separated by " | " is one ranked list of the top vocabulary tokens read from ONE activation, best first. Several tokens of the same line may jointly express one meaning, and a quote from such a line is one token or several tokens of that same line joined by " | ". Tokens of adjacent positions at the same layer may be joined only to spell one word split across them; such a quote is that word. Tokens on different lines never combine otherwise, and a relation (who does what to whom) must be stated within one sample (for a free-text sample, within one of its "- " bullets; in a free-text sample, bullets are separated by ⁞). A line that holds two or more of the options singles out none of those options, whatever their rank. A line that holds a run of names of people, bands or companies, or of any other words or names of one kind, singles out none of the words on it, whatever their rank, even when only one of them is an option. Otherwise, an option that is the only option on its line is singled out by it.
```

## Summary mode

The default since plan 0024 (`opts=aggregate=native` opts out to the any-layer rule above).
Every cell of an item (every read layer × position × sample under `reads=full`; the final
position at every layer under `reads=lite`) goes to ONE digest call (`docs/summarizer.md` §
Item digest) with this family's task note, and the MC judge is called ONCE per item on that
digest. A YES needs a quote from inside one evidence sample (`col.evidence`), never from the
note-taker's words. User message (`{summary_note}` = the shared `digest.SUMMARY_NOTE`, plus the
token note above when the readouts are token lists):

```text
CANDIDATES:
{options}

{summary_note}

READOUT:
{summary}
```

Rival audit (summary mode only, one call per credited gold pick; see the rival check above).
System prompt:

```text
You check one answer of a judge of readouts of a language model's internal activations, taken while the model read a one-sentence factual question. The question asks for a fact (a year or a city) about a person, group or company that it never names; you are told which work or thing it is about. The judge chose the candidate below as the one the readout identifies as that hidden entity, and cited a quote. Each readout line is one claim with its support marker ([N samples]).

For EACH numbered line under LINES TO CHECK, say whether it names a DIFFERENT person, group or company (in the candidate list or not) as the entity in question ("rival": true, with that "name"), that is:
- as the maker, performer, founder, parent, advisor or namesake of the work or thing in question, under its title or any variant of it (readouts garble titles: 'The Silent Road', 'Silent Roads' and 'The Road of Silence' may all be attempts at one film);
- or as the entity whose year or city the line gives or seeks as the answer to the question itself.
A line that also names the chosen candidate is checked the same way: it is a rival when it ALSO gives a different person, group or company in that role ("X wrote it. ... Y wrote it."; give that different "name"), not when it gives only the chosen candidate in the role and mentions the other in some other way.
Not a rival ("rival": false, "name": ""): a line about a clearly different work, thing or relation; a fact the line states about someone it merely mentions; a name that appears only as a comparison ("born in the same year as X"), a style reference, one entry of a list of several names, or a reference point for something else; a line that names nobody of the candidates' kind. Judge only from what each line says, not from your own knowledge of who made the work.
Return JSON: {"verdicts": [{"line": <number>, "rival": <true or false>, "name": "<name or empty>"}, ...]}, one verdict per numbered line.
```

User message (`{subject}` = the prompt's subject phrase, `{choice}` = the MC pick as `N. name`,
`{quote}` = its quote, `{lines}` = the audited lines as `N. [k samples] <line>`):

```text
THE QUESTION IS ABOUT: {subject}

CANDIDATES:
{options}

THE JUDGE CHOSE: {choice}
ITS QUOTE: {quote}

{summary_note}

READOUT:
{summary}

LINES TO CHECK:
{lines}
```

Task note (`EvalSpec.task_note`, sent to the summarizer; no gold, no option, no tool name):

```text
the model reads a one-sentence factual question whose answer needs a silent first step, working out which person, group or company the question is about, and it never writes that entity
```

## ATI

`wrong_bridge` is a crafted ATI family and stays gated. Bank v2 changes its `bank_sha` and its
instrument (`wb-mc-2026-10-30`), so the frozen entry (instrument `bank-2026-10-10`, 100/100)
went stale. It was re-gated on 2026-10-31 (R1-ATI): the stored panel answers (Qwen / Opus /
Astra / Argon × 3 draws) were re-judged NATIVE with this MC instrument, with no new answers (the
prompt text and render did not change, so `prompt_sha` is unchanged). Result: 100/100 again
(Opus / Astra / Argon pass@3 0.00, Qwen 0.59). `wrong_bridge_true` is removed (its ATI
entry, 58/100, is deleted).

## ATI panel refill (2026-10-28, plan 0019)

The four-reader panel gate (Qwen3.6-27B x {Opus 5.5, GPT-6 Astra, Gemini 4 Argon}, one best
guess x 3 draws each; see `evals/baselines/README.md`) admitted 93 of the 100 items (the frontier
readers almost never name Qwen's wrong bridge: pass@3 0.00-0.06). The other 7 moved to
`retired_panel_gate` (unscored, with their panel status) and were replaced by 7 items that pass
every gate above plus one item per subject S, <= 20 per template and <= 4 per wrong bridge over
the refilled bank, and the panel: 5 from the adjudicated finalists left out of the original bank
(templates already in the bank) and 2 from a new hop-1 template (`song_lyricist`) screened through the same stages (the 258k
candidate pool was exhausted). The bank was ATI 100/100 under instrument `bank-2026-10-10`
(`wrong_bridge_true`, the true-bridge twin, was 58/100; it is removed, see Scoring).

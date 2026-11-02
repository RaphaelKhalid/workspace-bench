# Authoring new items (Opus)

Use this for families with no deterministic generator: association, multihop, multilingual, typo,
poetry stubs, the six mt families, user_modeling selfdescribe, conjunctive, role_bound, buggy_code
and moral dilemmas. Opus writes candidates. The subject decides whether they are in capability. The
lint and gate decide what's kept.

The tool: `scripts/adapt_box.sh author model=<m> family=<f> tier=<t> n=<n> steer="…" wave=<k>`.
It renders the brief (`BRIEFS` in `wsbench/adapt/author.py`), calls Opus 20 items at a time (`MAX_PER_CALL`; 40 ran out of output tokens), and
fills the fields Opus must not choose: read site, render and `source`. It writes
`cand/<family>.jsonl`. Auth is `wsbench/adapt/auth.py`: the judges' keyless OAuth token from the
Modal Dict `anthropic-oauth`, read only, never written. There's no API key; don't look for one. A
401 stops the run: ask Agam to run `push-judge-token`, then resume (gated rows and the grade cache
are kept). A family without a `Brief` needs one first, written from `families.md` with the fields
below.

## One wave
1. **Brief.** Write the family's brief from `families.md`:
   - the latent in one sentence;
   - the required keys and the exact output JSON shape;
   - every invariant, word for word;
   - the tier's knob text (e.g. "the bridge must be an entity a well-read 12-year-old knows";
     "use only French, German, Spanish").
2. **Few-shots.** Use 4 real bank items that **passed on this subject** (from `gate/<family>.jsonl`).
   If none passed, use the easiest originals. Never show items that failed as examples.
3. **ALREADY-USED.** List every target, bridge and concept already in `gate/` and `cand/`, and tell
   Opus not to reuse any of them.
4. **Steering.** Read the last wave's misses in the viewer and write 2–4 bullets about the failure
   pattern:
   - "4B answers with the country, not the capital: make the final relation capital-only";
   - "fails Polish and Hungarian, passes Russian and Indonesian: drop pl and hu".

   Steer by what the subject got wrong, not by a guess.
5. **Ask for a batch:**
   - ask for 1.5× the deficit divided by the current yield, at least 10 and at most 60 per wave (split into calls of 20);
   - spread over the family's subfamilies and topics;
   - no single template, relation or topic above 20% of the batch.
6. **Write candidates.** Write them with `wsbench.adapt.store.add_candidates`, stamping
   `adapt = {origin: "authored", tier, knobs, author: "<model id>", wave}` and `source` (the knob
   text).
7. **Gate.** Run `scripts/adapt_box.sh gate model=<m> families=<f> llm=claude-opus-5-5` (without
   `llm=`, every LLM-graded leg is undecided and conjunctive / role_bound / buggy items all fail). The lint drops malformed
   items before any GPU time.
8. **Check.** Read 10 passing and 10 failing items. Also check that Opus didn't drift the latent:
   - an association scene that names the referent in a synonym;
   - a multihop item whose clue gives the answer without the bridge.

   Fix the brief, not the items.

## Steer with lint rejections too
The lint names exactly why a candidate was rejected. Feed those reasons back as the next wave's
`steer=`. On Qwen3.5-4B, typo_mt's "long common words" wave lost 28/40 items to the multi-token
rule: the large vocabulary makes *misunderstanding* or *unforgettable* one token. The next wave
was steered with the rejected words ("ONE token for this model") and the accepted ones, and all
60 of its items passed lint. Tokenizer facts like this are subject-specific: they are measured,
not guessed.

## Wave size and stopping
- Pilot about 30 candidates at a new tier before a full wave.
- Yield ≥ 30%: one more wave usually fills the family.
- Yield 3–30%: steer and try at most 3 more waves at this tier, then step down a tier.
- Yield < 3% on ≥ 60 at the floor tier: `ooc`. Write the reason in the report note.

## The brief template
```text
You are writing new items for the WorkspaceBench family <family>. <latent sentence>.
These items are for a SMALLER model than the original bank was built for, so they must be
easier in exactly this way: <tier knob text>. Everything else is unchanged:
<invariants, verbatim>
Output a JSON list of objects with exactly these keys: <keys + one-line meaning each>.
Examples that this model answers correctly:
<4 JSON items>
Do not reuse any of these: <ALREADY-USED>.
What the model got wrong last wave: <steering bullets>.
Write <n> items spread across <subfamilies/topics>; no topic or template more than 20%.
```

## Family-specific notes
- **multihop** (single token): also write `bridge_question` (it asks for the bridge directly,
  without naming the target) and `bridge_aliases`.
- **mt families:**
  - write `units` with `forms` only; `match` and `probe_token_lens` are stamped in code from the
    subject's tokenizer (`wsbench.adapt.mt.stamp`);
  - write `target_alts` with the short answers a model might give.
- **multilingual_multihop** (multihop_mt was removed 2026-10-30; multihop_mt_v2 is not portable yet (its shortcut gate is model-specific)): each bridge gets `{question, units, answers}`. A bridge
  question must not leak the target or another bridge.
- **association:** also write `aliases` (synonyms the gate accepts). The judge accepts synonyms
  anyway.
- **poetry:** write only the couplet stub. The gold is whatever the subject commits to.
- **buggy_code:** write the clean twin too, then verify both by execution before gating
  (`verified` = the real stdout or exception).
- **user_modeling:** write selfdescribe conversations only. Synthsys items are the echo floor and
  must not be padded.

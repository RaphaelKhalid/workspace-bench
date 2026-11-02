# plans/

Design plans for the 2026-09-15..17 restructure that gave the benchmark its nine-family shape
and shared package. Historical: they record what was decided then, not the current state.
Numbering gaps (0009, 0011) are plans that were reverted. Families added later and every
read-site change since are documented in the family READMEs (`evals/<family>/README.md`) and
the git log.

Later plans in this directory follow the same `NNNN-<name>.md` convention. 0032
(`0032-wsb-bp-infra.md`) is the shared read / summarize / judge machinery of the 2026-10-30 fix
campaign; 0033-0056 are that campaign's family workstreams, one plan per family PR.

The family PRs were written in parallel and several picked the same number; the integration merge
kept the number of the first-merged plan and renumbered the rest. Code, READMEs and tests of the
renumbered families were updated to the new number; an old number left in a shared doc, or in a
plan file (historical, not rewritten), means the plan below by family context:

| old | new | plan |
|---|---|---|
| 0033 | 0047 | `0047-wsb-bp-brew.md` (0033 stays `0033-wsb-bp-typo.md`) |
| 0036 | 0048 | `0048-wsb-bp-multihop.md` (0036 stays `0036-wsb-bp-arithmetic.md`) |
| 0037 | 0049 | `0049-wsb-bp-conjunctive.md` (0037 stays `0037-wsb-bp-jailbreak.md`) |
| 0037 | 0050 | `0050-wrong-bridge-mc.md` |
| 0037 | 0051 | `0051-wsb-bp-basic-readout-mt.md` |
| 0038 | 0052 | `0052-wsb-bp-agentic.md` (0038 stays `0038-wsb-bp-chain.md`) |
| 0039 | 0053 | `0053-wsb-bp-basic-readout.md` (0039 stays `0039-wsb-bp-association.md`) |
| 0040 | 0054 | `0054-wsb-bp-multilingual.md` (0040 stays `0040-hallucination-to-hb.md`) |
| 0042 | 0055 | `0055-wsb-bp-role-bound.md` (0042 stays `0042-wsb-bp-jlens-pr.md`) |
| 0043 | 0056 | `0056-wsb-bp-user-modeling.md` (0043 stays `0043-wsb-bp-relational-multihop.md`) |

Campaign plans by number: 0031 agentic clean twins, 0032 infra, 0033 typo / typo_mt, 0034 mcdm,
0035 directed_modulation, 0036 arithmetic, 0037 jailbreak, 0038 chain, 0039 association, 0040
hallucination -> HallucinationBench, 0041 multihop_mt_v2, 0042 jlens_concept_pr, 0043
relational_multihop, 0044 knowledge_cutoff, 0045 introspection, 0046 moral_rationale, 0047 brew,
0048 multihop, 0049 conjunctive_association, 0050 wrong_bridge, 0051 basic_readout_mt, 0052
agentic_misalignment, 0053 basic_readout, 0054 the four multilingual families (v2 banks,
`mc+regex`), 0055 role_bound_association, 0056 user_modeling (um-v3.2), 0058 medical_diagnosis{,_alt}
removed and unverbalized_hint retired for now.

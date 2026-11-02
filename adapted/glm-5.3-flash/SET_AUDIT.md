# Mechanical audit: adapted/glm-5.3-flash

lint = wsbench.adapt.lint on the frozen item; dup latents only for unique-latent families; gate = last gate record passes.

| family | items | new | lint fails | dup prompts | dup latents | not gate-passed |
|---|---|---|---|---|---|---|
| arithmetic_intermediates | 566 | 117 | 0  | 52 | 0 | 0 |
| association | 100 | 23 | 0  | 0 | 1 | 0 |
| basic_readout | 100 | 19 | 0  | 0 | 0 | 0 |
| basic_readout_mt | 100 | 8 | 1 {'leak': 1} | 0 | 0 | 0 |
| brew_intermediates | 0 | 0 | 0  | 0 | 0 | 0 |
| buggy_code | 32 | 8 | 0  | 0 | 0 | 0 |
| chain_intermediates | 120 | 31 | 0  | 2 | 0 | 0 |
| conjunctive_association | 54 | 0 | 0  | 0 | 0 | 0 |
| directed_modulation | 76 | 0 | 0  | 0 | 0 | 0 |
| jailbreak_recognition | 86 | 0 | 0  | 0 | 0 | 0 |
| moral_rationale | 123 | 0 | 0  | 0 | 0 | 0 |
| multi_concept_directed_modulation | 27 | 0 | 0  | 1 | 0 | 0 |
| multihop | 100 | 8 | 2 {'format': 1, 'leak': 1} | 0 | 24 | 0 |
| multihop_mt | 100 | 10 | 2 {'latent': 2} | 0 | 5 | 0 |
| multilingual | 100 | 0 | 4 {'latent': 4} | 2 | 56 | 0 |
| multilingual_mt | 100 | 12 | 0  | 0 | 20 | 0 |
| multilingual_multihop | 98 | 6 | 3 {'leak': 2, 'latent': 1} | 0 | 10 | 0 |
| multilingual_typo | 100 | 22 | 0  | 0 | 0 | 0 |
| poetry | 100 | 1 | 0  | 1 | 8 | 0 |
| relational_multihop | 96 | 28 | 0  | 0 | 0 | 0 |
| role_bound_association | 100 | 48 | 0  | 0 | 0 | 0 |
| typo | 100 | 3 | 0  | 0 | 0 | 0 |
| typo_mt | 100 | 9 | 0  | 0 | 0 | 0 |
| user_modeling | 100 | 8 | 0  | 0 | 0 | 0 |

# Mechanical audit: adapted/kimi-k2

lint = wsbench.adapt.lint on the frozen item; dup latents only for unique-latent families; gate = last gate record passes.

| family | items | new | lint fails | dup prompts | dup latents | not gate-passed |
|---|---|---|---|---|---|---|
| arithmetic_intermediates | 559 | 0 | 0  | 60 | 0 | 0 |
| association | 100 | 26 | 0  | 0 | 1 | 0 |
| basic_readout | 82 | 0 | 0  | 0 | 0 | 0 |
| basic_readout_mt | 100 | 10 | 1 {'leak': 1} | 0 | 0 | 0 |
| brew_intermediates | 39 | 0 | 0  | 0 | 0 | 0 |
| buggy_code | 25 | 2 | 0  | 0 | 0 | 0 |
| chain_intermediates | 120 | 4 | 0  | 4 | 0 | 0 |
| conjunctive_association | 71 | 0 | 0  | 0 | 0 | 0 |
| directed_modulation | 80 | 0 | 0  | 0 | 0 | 0 |
| jailbreak_recognition | 86 | 0 | 0  | 0 | 0 | 0 |
| moral_rationale | 175 | 0 | 0  | 0 | 0 | 0 |
| multi_concept_directed_modulation | 27 | 0 | 0  | 1 | 0 | 0 |
| multihop | 100 | 4 | 4 {'format': 3, 'leak': 1} | 0 | 24 | 0 |
| multihop_mt | 100 | 9 | 3 {'latent': 3} | 0 | 5 | 0 |
| multilingual | 97 | 0 | 4 {'latent': 4} | 2 | 54 | 0 |
| multilingual_mt | 86 | 7 | 0  | 0 | 17 | 0 |
| multilingual_multihop | 98 | 14 | 3 {'leak': 2, 'latent': 1} | 0 | 8 | 0 |
| multilingual_typo | 100 | 13 | 0  | 0 | 0 | 0 |
| poetry | 98 | 0 | 0  | 1 | 8 | 0 |
| role_bound_association | 96 | 44 | 0  | 0 | 0 | 0 |
| typo | 100 | 0 | 0  | 0 | 1 | 0 |
| typo_mt | 84 | 5 | 0  | 0 | 0 | 0 |
| user_modeling | 100 | 9 | 0  | 0 | 0 | 0 |

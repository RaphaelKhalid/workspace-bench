# NOTICE — third-party data and code

The code in this repository and every in-house item bank are released under the MIT licence in
`LICENSE`. In-house means every bank not listed below as third-party: `association`,
`basic_readout`, `basic_readout_mt`, `multihop`, `multihop_mt_v2`, `multilingual`,
`multilingual_mt`, `multilingual_multihop`, `multilingual_typo`, `poetry`, `typo`, `typo_mt`,
`directed_modulation`, `multi_concept_directed_modulation`, `chain_intermediates`,
`arithmetic_intermediates`, `buggy_code`, `conjunctive_association`, `role_bound_association`,
`relational_multihop`, `moral_rationale`, and the 14 in-house `agentic_misalignment` scenarios. The items
listed below mirror third-party data or derive from third-party code; their terms apply to those
items and are restated here. Item files that mirror external data keep `source` / `source_id`
fields where the bank carries them (jailbreak); the jlens seeds are
identified by label prefix.

## Qwen3.6-27B (Alibaba)

- Used for: every bank's rollouts and responses (the model being read).
- Terms: see the Qwen3.6-27B model card on Hugging Face for the licence that applies to model
  outputs.
- The introspection injection vectors (`evals/introspection/vectors/concept_vectors_L12.npy`,
  125 x 5120 float32: layer-12 residual-stream activation differences of Qwen3.6-27B, Agam's
  recipe on a public word list; `gaussian_vectors_L12.npy`: 500 x 5120 seeded `torch.randn`
  draws) are released under this repo's terms; the activations derive from the Qwen3.6-27B
  weights, whose model card states Apache-2.0 (checked 2026-10-30), which permits
  redistributing derived artefacts.

## Judge models

- Gemini 3.8 Flash (Google) via OpenRouter — the default judge; Claude Sonnet 5 (Anthropic) —
  judge for `agentic_misalignment` and `jailbreak_recognition`.
- Terms: the respective API terms of service. Judge verdicts are cached locally per run and not
  redistributed with the repo.

## Agentic misalignment scenarios — Lynch et al. 2025 / `anthropic-experimental/agentic-misalignment`

- Source: Lynch, Wright, Larson, Troy, Ritchie, Mindermann, Perez, Hubinger. *Agentic
  Misalignment: How LLMs Could Be Insider Threats.* Anthropic, 2025. arXiv:2510.05179. Code:
  https://github.com/anthropic-experimental/agentic-misalignment
- Included: 18 of the 32 scenarios in `evals/agentic_misalignment/items.json` (the repo's
  18-condition grid: blackmail / leaking / murder × goal × urgency), generated with its
  `scripts/generate_prompts.py` and production system prompts.
- Licence: MIT. Copyright (c) Anthropic. Permission is hereby granted, free of charge, to any
  person obtaining a copy of this software and associated documentation files, to deal in the
  software without restriction, subject to the inclusion of the copyright notice and this
  permission notice; the software is provided "as is", without warranty of any kind.

## WildChat — Zhao et al. 2024

- Source: Zhao, Ren, Hessel, Cardie, Choi, Deng. *WildChat: 1M ChatGPT Interaction Logs in the
  Wild.* ICLR 2024. arXiv:2405.01470. https://huggingface.co/datasets/allenai/WildChat-1M
- Included: all 86 `jailbreak_recognition` items are verbatim WildChat conversations
  (`source: wildchat`; `source_id` is the WildChat conversation hash).
- Licence: ODC-BY (Open Data Commons Attribution License v1.0). Attribution is required when
  redistributing or building on these items; this file and the family README provide it.

## CHIVE — Karvonen et al.

- Source: Karvonen, Ong, Kantamneni, Marks. *CHIVE.* arXiv:2608.16747.
  https://github.com/adamkarvonen/chive
- Included: the `[role]: content` transcript render contract used by `jailbreak_recognition`.
  No CHIVE code is vendored.

## Transluce user-modelling data — Choi et al. 2025

- Source: Choi, Huang, Schwettmann, Steinhardt. *Scalably Extracting Latent Representations of
  Users.* Transluce, 2025. https://transluce.org/user-modeling
- Included: the `user_modeling` `selfdescribe` items are rows taken verbatim from the
  SelfDescribe set; the `synthsys` items use system prompts from the SynthSysPre set; the
  revealed-belief gate (≥ 8/10) is their criterion.
- Licence: the Transluce release names the terms for its data; see that release before
  redistributing these items outside this benchmark.

## J-lens — arXiv:2607.15495 / `anthropics/jacobian-lens` / `neuronpedia/jacobian-lens`

- Source: *Verbalizable Representations Form a Global Workspace in Language Models.* Anthropic /
  Transformer Circuits, 2026. arXiv:2607.15495. Code: https://github.com/anthropics/jacobian-lens
  (Apache-2.0). Reference lens artifact: https://huggingface.co/neuronpedia/jacobian-lens
  (n1000 wikitext fit).
- Included: the J-lens method and the frozen reference top-10 tokens under
  `evals/jlens_concept_pr/gen-jlens-pr-jlens/` that the family scores against. The numeric
  helpers in `src/wsbench/evals/jlens_concept_pr/{concept_pr,token_types}.py` are this repo's
  own code (MIT); no `anthropics/jacobian-lens` source is vendored.
- Licence of the referenced code: Apache License, Version 2.0
  (http://www.apache.org/licenses/LICENSE-2.0). Copyright Anthropic. Licensed under the Apache
  License, Version 2.0 (the "License"); you may not use that code except in compliance with the
  License. Unless required by applicable law or agreed to in writing, software distributed under
  the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
  either express or implied. See the License for the specific language governing permissions
  and limitations under the License.

## LMSYS-Chat-1M — Zheng et al. 2023

- Source: https://huggingface.co/datasets/lmsys/lmsys-chat-1m
- Included: no turns are shipped since 2026-10-30 (the `hallucination` family, which carried 74
  verbatim first user turns, left the bench for HallucinationBench, plan 0040). 75 first turns
  seeded the `jlens_concept_pr` items (labels `chat-lmsys-*`); their text was carried in
  `evals/jlens_concept_pr/manifest.json` until 2026-09-17 and is no longer shipped (labels and
  read positions only).
- Licence: the **LMSYS-Chat-1M Dataset License Agreement** (on the dataset page) applies to
  those turns; the agreement text controls. In summary it grants a non-exclusive,
  non-transferable licence to use the data, prohibits attempts to identify the individuals
  behind the conversations, and passes its restrictions on to anything derived from the data.
  The turns mirrored here are used only as benchmark prompts and carry the same terms.

## DailyDialog — Li et al. 2017

- Source: Li, Su, Shen, Li, Cao, Niu. *DailyDialog: A Manually Labelled Multi-turn Dialogue
  Dataset.* IJCNLP 2017. https://huggingface.co/datasets/ConvLab/dailydialog
- Included: no turns are shipped since 2026-10-30 (the `hallucination` family, which carried 75
  verbatim first user turns, left the bench for HallucinationBench, plan 0040). 75 first turns
  seeded the `jlens_concept_pr` items (labels `chat-dailydialog-*`); their text was carried in
  `evals/jlens_concept_pr/manifest.json` until 2026-09-17 and is no longer shipped (labels and
  read positions only).
- Licence: **CC BY-NC-SA 4.0** (https://creativecommons.org/licenses/by-nc-sa/4.0/). These
  items are **non-commercial**: attribution is required, they may not be used for commercial
  purposes, and any adaptation must be shared under the same licence.

## pile-10k and fineweb-edu

- Sources: https://huggingface.co/datasets/NeelNanda/pile-10k;
  https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu (sample-10BT).
- Included: 74 pile-10k + 75 fineweb-edu 128-token prefixes seeded the `jlens_concept_pr`
  items (labels `pt-pile-*`, `pt-fineweb-*`; the manifest carries no source ids). Their text was
  carried in `evals/jlens_concept_pr/manifest.json` until 2026-09-17 and is no longer shipped.
- Licence: ODC-BY (attribution required); the underlying web text retains its own copyright.

## MMLU and MMLU-Redux — Hendrycks et al. 2021 / Gema et al. 2024

- Sources: Hendrycks, Burns, Basart, Zou, Mazeika, Song, Steinhardt. *Measuring Massive Multitask
  Language Understanding.* ICLR 2021. arXiv:2009.03300. https://huggingface.co/datasets/cais/mmlu
  (MIT). Gema et al. *Are We Done with MMLU?* 2024. arXiv:2406.04127.
  https://huggingface.co/datasets/edinburgh-dawg/mmlu-redux-2.0 (CC BY 4.0).
- Included: the question and options of every `unverbalized_hint` item, verbatim, inside a prompt
  frame and hint written in-house (`evals/unverbalized_hint/items.json`; `source` is `mmlu_redux`
  for the 26 MMLU-Redux 2.0 items and `mmlu` for the 128 MMLU test items, `qid` the source id).
  The paired hinted-prompt design follows Turpin, Michael, Perez, Bowman. *Language Models Don't
  Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting.* NeurIPS
  2023. arXiv:2305.04388 (design only; no data or code from that paper).
- Licences: MMLU is MIT (Copyright (c) 2020 Dan Hendrycks; permission is granted free of charge
  to use, copy, modify and distribute it, provided the copyright notice and this permission notice
  are included; it is provided "as is", without warranty of any kind). MMLU-Redux
  2.0 is CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/): attribution is required, which
  this file and the family README provide; the items are unmodified apart from the added frame.

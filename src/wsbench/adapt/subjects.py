"""Subject models the banks can be adapted to. ``tokenizer`` names the family whose token indices
carry over unchanged (``qwen3.6`` = the banks' own tokenizer and chat template)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Subject:
    key: str
    hf_id: str
    label: str
    n_layers: int  # 0 = read num_hidden_layers from the HF config at run time
    tokenizer: str
    revision: str | None = None
    max_model_len: int = 4096
    backend: str = "box"  # "box" = the RunPod 4090; "modal" = too big for 24 GB
    gpu_memory_utilization: float = 0.85  # vLLM share of the 24 GB card
    enforce_eager: bool = False  # no torch.compile / CUDA graphs (saves memory on a tight fit)
    read_band: tuple[int, ...] = ()  # the subject's lens layers, if it reads only some (snap there)
    modal_app: str = "adapt-subject-llm"  # backend="modal": the deployed app generating for it
    tokenizer_dir: str | None = None  # local tokenizer files when the hub id needs remote code
    chat_template: str | None = None  # a template file replacing the tokenizer's own


SUBJECTS: dict[str, Subject] = {
    s.key: s
    for s in [
        Subject(
            "qwen3.5-0.8b",
            "Qwen/Qwen3.5-0.8B",
            "Qwen3.5-0.8B",
            24,
            "qwen3.6",
            "2fc06364715b967f1860aea9cf38778875588b17",
        ),
        Subject(
            "qwen3.5-2b",
            "Qwen/Qwen3.5-2B",
            "Qwen3.5-2B",
            24,
            "qwen3.6",
            "15852e8c16360a2fea060d615a32b45270f8a8fc",
        ),
        Subject(
            "qwen3.5-4b",
            "Qwen/Qwen3.5-4B",
            "Qwen3.5-4B",
            32,
            "qwen3.6",
            "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
        ),
        Subject(
            "qwen3.5-9b",
            "Qwen/Qwen3.5-9B",
            "Qwen3.5-9B",
            32,
            "qwen3.6",
            "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
            gpu_memory_utilization=0.93,
            enforce_eager=True,
        ),
        Subject(
            "olmo-3-7b",
            "allenai/Olmo-3-7B-Instruct",
            "OLMo-3-7B-Instruct",
            32,
            "dolma2",
            "6e5971d9eba42665f5bd5a0fcf047f299ce1dccc",
        ),
        Subject(
            "gemma-4-31b-it",
            "google/gemma-4-31b-it",
            "Gemma-4-31B-it",
            60,
            "gemma4",
            "842da3794eaa0b77d5f08bae87a17459d91ff475",
            backend="modal",
        ),
        # OLens subjects added 2026-10-18 (hub main that day); Modal so sets build in parallel
        # with the box queue. Tokenizer keys: "qwen3" = Qwen3's 151k vocab (not the 3.6 one).
        Subject(
            "qwen3-8b",
            "Qwen/Qwen3-8B",
            "Qwen3-8B",
            36,
            "qwen3",
            "b968826d9c46dd6066d109eabc6255188de91218",
            backend="modal",
            read_band=tuple(range(12, 35, 2)),
        ),  # its OLens reads even layers 12..34
        Subject(
            "olmo-3.1-32b",
            "allenai/Olmo-3.1-32B-Instruct",
            "OLMo-3.1-32B-Instruct",
            64,
            "dolma2",
            "ac0587e4a7744a551c059d8cd17ba220bc940dae",
            backend="modal",
        ),
        Subject(
            "qwen3.6-35b-a3b",
            "Qwen/Qwen3.6-35B-A3B",
            "Qwen3.6-35B-A3B",
            40,
            "qwen3.6",
            "995ad96eacd98c81ed38be0c5b274b04031597b0",
            backend="modal",
        ),
        # normal-bank OLens subjects (>= 32B, 2026-10-23): gated + re-golded on the 27B bank only.
        # model-parallel HF generation on Modal: gw-olens scripts/ola/port/adapt_mp_subject_modal.py
        Subject(
            "kimi-k2",
            "moonshotai/Kimi-K2-Instruct-0905",
            "Kimi-K2-Instruct-0905",
            61,
            "kimi",
            "ac6c49f04883bd0a0598b790693a72061c676629",
            backend="modal",
            modal_app="adapt-mp-kimi-k2-instruct-0905",
            tokenizer_dir="/workspace/agam/hf_tok/kimi-k2",
        ),
        Subject(
            "glm-5.3-flash",
            "zai-org/GLM-5.3-Flash",
            "GLM-5.3-Flash",
            45,
            "glm5",
            "eb9eb208eb0d988989d07a6a12d0fdeb5f52574a",
            backend="modal",
            modal_app="adapt-mp-glm-5.3-flash",
            tokenizer_dir="/workspace/agam/hf_tok/glm-5.3-flash",
            # gw-olens' template: the upstream one always opens <think>
            chat_template="/workspace/agam/hf_tok/glm-5.3-flash/glm5_chat_nothink.jinja",
        ),
    ]
}

ORIGINAL_LAYERS = 64  # Qwen3.6-27B, the model every bank and read grid was built on


def get(key: str) -> Subject:
    try:
        return SUBJECTS[key]
    except KeyError:
        raise SystemExit(f"unknown subject {key!r}; add it to wsbench/adapt/subjects.py") from None


def remap_layer(layer: int, n_layers: int, band: tuple[int, ...] | list[int] = ()) -> int:
    """A 27B read layer at the same depth fraction of the subject, snapped to the nearest layer of
    ``band`` (the subject's lens layers; ties go deeper) when the subject has one."""
    x = min(n_layers - 1, round(layer * n_layers / ORIGINAL_LAYERS))
    return min(band, key=lambda b: (abs(b - x), -b)) if band else x


def remap_layers(
    layers: list[int], n_layers: int, band: tuple[int, ...] | list[int] = ()
) -> list[int]:
    return sorted({remap_layer(layer, n_layers, band) for layer in layers})

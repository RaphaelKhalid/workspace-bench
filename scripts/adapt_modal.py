"""The subject on Modal, for subjects too big for the 24 GB box (SKILL.md runbook step 0).

A deployed vLLM class the local pipeline calls through ``wsbench.adapt.gate.RemoteRunner``: the
box renders every prompt with the subject's own template (so the gate, read plan and lint are the
same code for every subject) and Modal only generates. Text-only (image/video limits 0), the
subject's pinned revision, weights cached on the ``adapt-hf-cache`` volume.

    MODAL_ENVIRONMENT=agam modal deploy scripts/adapt_modal.py
    # then set backend="modal" on the Subject; every adapt command uses it transparently
"""

import modal

app = modal.App("adapt-subject-llm")
hf = modal.Volume.from_name("adapt-hf-cache", create_if_missing=True)
image = (  # a CUDA *devel* base: vLLM's flashinfer kernels JIT-compile with nvcc (Gemma-4 failed
    # on debian_slim: "Could not find nvcc"); 13.0 matches vllm 0.31's torch (cu130)
    modal.Image.from_registry("nvidia/cuda:13.0.1-devel-ubuntu22.04", add_python="3.12")
    .pip_install("vllm==0.31.0", "transformers==5.17.0", "huggingface_hub")
    .env({"HF_HOME": "/hf", "VLLM_WORKER_MULTIPROC_METHOD": "spawn"})
)


@app.cls(image=image, gpu="H200", volumes={"/hf": hf}, timeout=6 * 3600, scaledown_window=600)
class SubjectLLM:
    model_id: str = modal.parameter()
    revision: str = modal.parameter(default="")
    max_model_len: int = modal.parameter(default=4096)

    @modal.enter()
    def load(self) -> None:
        from vllm import LLM

        self.llm = LLM(
            self.model_id,
            revision=self.revision or None,
            max_model_len=self.max_model_len,
            gpu_memory_utilization=0.90,
            seed=0,
            limit_mm_per_prompt={"image": 0, "video": 0},
        )
        hf.commit()

    @staticmethod
    def _inputs(prompts: list) -> list:
        from vllm.inputs import TokensPrompt

        return [TokensPrompt(prompt_token_ids=p) if isinstance(p, list) else p for p in prompts]

    @modal.method()
    def sample(
        self,
        prompts: list[str],
        max_tokens: list[int],
        draws: int,
        temperature: float,
        top_p: float,
        seed: int,
    ) -> list[tuple[str, list[str]]]:
        """Greedy + ``draws`` samples per prompt: the local Runner.sample contract."""
        from vllm import SamplingParams

        g = self.llm.generate(
            prompts,
            [SamplingParams(temperature=0.0, max_tokens=m) for m in max_tokens],
            use_tqdm=False,
        )
        s = self.llm.generate(
            prompts,
            [
                SamplingParams(
                    n=draws, temperature=temperature, top_p=top_p, max_tokens=m, seed=seed + i
                )
                for i, m in enumerate(max_tokens)
            ],
            use_tqdm=False,
        )
        return [
            (gi.outputs[0].text, [o.text for o in si.outputs]) for gi, si in zip(g, s, strict=True)
        ]

    @modal.method()
    def generate(
        self,
        prompts: list,
        temperature: float,
        max_tokens: int,
        seed: int,
        top_p: float = 1.0,
        stop_token_ids: list[int] | None = None,
    ) -> list[dict]:
        """One completion per prompt (text or token ids): text + generated token ids."""
        from vllm import SamplingParams

        sp = SamplingParams(
            temperature=temperature,
            top_p=top_p,
            top_k=0,
            max_tokens=max_tokens,
            seed=seed,
            stop_token_ids=stop_token_ids or None,
        )
        outs = self.llm.generate(self._inputs(prompts), sp, use_tqdm=False)
        return [{"text": o.outputs[0].text, "ids": list(o.outputs[0].token_ids)} for o in outs]

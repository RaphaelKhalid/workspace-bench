"""The probed model: load once, capture the residual stream at chosen blocks and positions.
A benchmark layer L is the output of decoder block ``model.layers[L]`` (the residual stream after
that block), the convention every bank was captured with."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, Self

DEFAULT_MODEL = "Qwen/Qwen3.6-27B"


@dataclass
class Backend:
    """A causal LM with its tokenizer. ``capture`` returns ``{layer: [n_pos, d]}`` fp32 CPU
    tensors for the requested positions; ``blocks`` is the decoder block list."""

    model: Any
    tokenizer: Any
    device: str
    model_id: str

    @classmethod
    def load(
        cls, model_id: str = DEFAULT_MODEL, *, device: str = "cuda", dtype: str = "bfloat16"
    ) -> Self:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(
            model_id, dtype=getattr(torch, dtype), device_map=device
        )
        model.eval()
        return cls(model=model, tokenizer=tok, device=device, model_id=model_id)

    @property
    def blocks(self) -> Any:
        m = self.model
        for path in (
            "model.layers",
            "model.language_model.layers",
            "base_model.model.model.layers",
        ):
            obj = m
            try:
                for part in path.split("."):
                    obj = getattr(obj, part)
                return obj
            except AttributeError:
                continue
        raise AttributeError("decoder blocks not found on this model")

    @property
    def n_layers(self) -> int:
        return len(self.blocks)

    @property
    def unembed(self) -> Any:
        return self.model.get_output_embeddings().weight

    @property
    def final_norm(self) -> Any:
        m = self.model
        for path in ("model.norm", "model.language_model.norm", "base_model.model.model.norm"):
            obj = m
            try:
                for part in path.split("."):
                    obj = getattr(obj, part)
                return obj
            except AttributeError:
                continue
        raise AttributeError("final norm not found on this model")

    @contextmanager
    def steered(
        self, layer: int, positions: Sequence[int], vector: Any, beta: float
    ) -> Iterator[None]:
        """A dose injection for every forward inside the block (plan 0045 §2.3, the
        introspection bank's recipe): on the OUTPUT residual of decoder block ``layer``, at each
        absolute ``positions`` index, ``h <- h + beta * ||h|| * v / ||v||`` (computed in fp32,
        written back in the residual's dtype). Removed on exit, even if the body raises."""
        import torch

        v = torch.as_tensor(vector, dtype=torch.float32).flatten()
        n = float(v.norm())
        if not n > 0:
            raise ValueError("steering vector has zero norm")
        unit = v / n
        idx = torch.as_tensor(list(positions), dtype=torch.long)
        blocks = self.blocks
        if not 0 <= layer < len(blocks):
            raise ValueError(f"inject layer {layer} out of range for a {len(blocks)}-block model")

        def hook(_mod: Any, _inp: Any, out: Any) -> Any:
            h = out[0] if isinstance(out, tuple) else out
            if h.shape[1] <= int(idx.max()):
                return out
            i = idx.to(h.device)
            x = h[:, i].float()
            u = unit.to(h.device)
            h[:, i] = (x + beta * x.norm(dim=-1, keepdim=True) * u).to(h.dtype)
            return out

        handle = blocks[layer].register_forward_hook(hook)
        try:
            yield
        finally:
            handle.remove()

    def capture(self, ids: list[int], layers: list[int], positions: list[int]) -> dict[int, Any]:
        """One forward pass; the residual stream after each requested block, at ``positions``."""
        import torch

        store: dict[int, Any] = {}
        handles = []
        want = torch.tensor(positions, dtype=torch.long)

        def make(layer: int):
            def hook(_mod, _inp, out):
                h = out[0] if isinstance(out, tuple) else out
                store[layer] = h[0, want.to(h.device), :].detach().float().cpu()

            return hook

        blocks = self.blocks
        for layer in layers:
            if not 0 <= layer < len(blocks):
                raise ValueError(f"layer {layer} out of range for a {len(blocks)}-block model")
            handles.append(blocks[layer].register_forward_hook(make(layer)))
        # a verbalizer's adapter may be mounted on this model; the probed model is always the base
        plain = (
            self.model.disable_adapter()
            if hasattr(self.model, "disable_adapter")
            else nullcontext()
        )
        try:
            with torch.no_grad(), plain:
                x = torch.tensor([ids], device=self.device)
                try:
                    self.model(x, logits_to_keep=1)  # the hooks want the residual, not the head
                except TypeError:
                    self.model(x)
        finally:
            for h in handles:
                h.remove()
        return store

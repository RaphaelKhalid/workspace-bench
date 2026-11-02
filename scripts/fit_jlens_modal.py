"""Fit a J-lens for a subject that neuronpedia does not cover (references/porting.md), on Modal.

Recipe = neuronpedia's (their config.yaml for the Qwen3.5 lenses): the official estimator
(anthropics/jacobian-lens, vendored in global-workspace `src/jlens` @ 581d3986, unchanged),
WikiText-103 train prompts (records >= 600 chars, truncated to 2000 chars), max_seq_len 128,
dim_batch 64, target = the final layer, every lower layer as a source, bf16 weights. Prompts
are fanned out in chunks (one H200 each: the estimator retains the graph of dim_batch replicas);
each chunk's mean is an exact n-weighted summand, so ``merge`` reproduces a sequential fit up to
float order. Convergence of the running mean is recorded per chunk; neuronpedia stopped at
283-417 prompts (stop_at_delta 0.002).

    modal run scripts/fit_jlens_modal.py --model-id Qwen/Qwen3.5-9B \\
        --revision c202236235762e1c871ad0ccb60c8ee5ba337b9a --tag qwen3.5-9b --n-prompts 400
    modal volume get adapt-jlens <tag>/lens.pt /workspace/agam/jlens_fits/<tag>/lens.pt
"""

from pathlib import Path

import modal

GW = Path("/workspace/agam/global-workspace")
app = modal.App("adapt-jlens-fit")
vol = modal.Volume.from_name("adapt-jlens", create_if_missing=True)
hf = modal.Volume.from_name("adapt-hf-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.11.0",
        "transformers==5.17.0",
        "accelerate>=1.14",
        "safetensors",
        "datasets>=4",
        "huggingface_hub",
        "numpy",
    )
    .env({"HF_HOME": "/hf", "PYTHONPATH": "/root/vendor", "PYTHONUNBUFFERED": "1"})
    .add_local_dir(str(GW / "src/jlens"), "/root/vendor/jlens", ignore=["**/__pycache__"])
)
MAX_CHARS, MAX_SEQ, DIM_BATCH, MIN_CHARS = 2000, 128, 64, 600


def load_wikitext_prompts(n_prompts: int, *, min_chars: int = 600) -> list[str]:
    """Verbatim copy of ``jlens.examples.load_wikitext_prompts`` (that module reads a data file
    the vendored copy does not ship, so it cannot be imported)."""
    from datasets import load_dataset

    dataset = load_dataset(
        "Salesforce/wikitext", "wikitext-103-raw-v1", split="train", streaming=True
    )
    prompts: list[str] = []
    for record in dataset:
        text = record["text"]
        if len(text.strip()) >= min_chars:
            prompts.append(text)
            if len(prompts) == n_prompts:
                break
    return prompts


@app.function(
    image=image,
    volumes={"/vol": vol, "/hf": hf},
    gpu="H200",
    timeout=6 * 3600,
    retries=1,
    memory=131072,
)
def chunk(
    model_id: str,
    revision: str,
    tag: str,
    start: int,
    n: int,
    n_total: int,
    dim_batch: int = DIM_BATCH,
    target: int = -1,
) -> dict:
    import time

    import jlens
    import torch
    from jlens.fitting import jacobian_for_prompt
    from transformers import AutoModelForCausalLM, AutoTokenizer

    out = Path(f"/vol/{tag}/chunks/{start:05d}.pt")
    if out.exists():
        return {"start": start, "skipped": True}
    prompts = [p[:MAX_CHARS] for p in load_wikitext_prompts(n_total, min_chars=MIN_CHARS)]
    prompts = prompts[start : start + n]
    tok = AutoTokenizer.from_pretrained(model_id, revision=revision)
    hfm = (
        AutoModelForCausalLM.from_pretrained(
            model_id, revision=revision, dtype=torch.bfloat16, attn_implementation="sdpa"
        )
        .cuda()
        .eval()
    )
    hfm.config.use_cache = False
    for p in hfm.parameters():
        p.requires_grad_(False)
    model = jlens.from_hf(hfm, tok)
    # the subject's BOS must lead each prompt when its chat render starts with one but the
    # tokenizer doesn't add it (Gemma-4: a BOS-less fit gave a lens that read noise)
    chat = tok.apply_chat_template([{"role": "user", "content": "x"}], tokenize=True,
                                   add_generation_prompt=True)  # fmt: skip
    chat = list(chat["input_ids"] if hasattr(chat, "keys") else chat)
    bos = tok.bos_token_id
    if bos is not None and chat[:1] == [bos] and tok("x")["input_ids"][:1] != [bos]:
        prompts = [tok.bos_token + p for p in prompts]
    hf.commit()
    n_layers = model.n_layers
    tgt = target % n_layers  # -1 = final block (neuronpedia), -2 = penultimate (paper recipe)
    sources = list(range(tgt))
    total: dict[int, torch.Tensor] = {}
    done, t0 = 0, time.time()
    for prompt in prompts:
        try:
            per, _, _ = jacobian_for_prompt(
                model, prompt, sources, dim_batch=dim_batch, max_seq_len=MAX_SEQ, target_layer=tgt
            )
        except ValueError:
            continue  # too short after skip_first: the official fit skips it too
        for layer, j in per.items():
            j = j.float().cpu()
            total[layer] = total[layer] + j if layer in total else j
        done += 1
    mean = {layer: t / max(done, 1) for layer, t in total.items()}
    lens = jlens.JacobianLens(jacobians=mean, n_prompts=done, d_model=model.d_model)
    out.parent.mkdir(parents=True, exist_ok=True)
    lens.save(str(out), dtype=torch.float32)
    vol.commit()
    return {"start": start, "n": done, "seconds": round(time.time() - t0)}


@app.function(image=image, volumes={"/vol": vol}, cpu=8.0, memory=262144, timeout=3 * 3600)
def merge(tag: str, dim_batch: int = DIM_BATCH, trim_k: float = 0.0) -> dict:
    """n-weighted mean of the chunk lenses. ``trim_k`` > 0: per layer, drop chunks whose ||J||
    exceeds trim_k x the median chunk norm (Gemma-4: one 10-prompt chunk was ~4,700x the median
    at layer 10 and dominated the early-layer mean)."""
    import json

    import jlens
    import torch

    vol.reload()
    files = sorted(Path(f"/vol/{tag}/chunks").glob("*.pt"))
    keep: dict[int, set[str]] | None = None
    if trim_k > 0:  # pass 1: per-layer chunk norms
        norms: dict[int, list[tuple[float, str]]] = {}
        for f in files:
            part = jlens.JacobianLens.load(str(f))
            for k, j in part.jacobians.items():
                norms.setdefault(k, []).append((j.float().norm().item(), f.name))
            del part
        keep = {}
        for k, lst in norms.items():
            med = sorted(n for n, _ in lst)[len(lst) // 2]
            keep[k] = {name for n, name in lst if n <= trim_k * med}
    # streaming n-weighted mean (= JacobianLens.merge): one chunk in memory at a time, so a
    # 60-layer 5376-wide lens (6.8 GB per chunk) merges in bounded RAM
    total: dict[int, torch.Tensor] = {}
    count: dict[int, int] = {}
    n, curve, running, first = 0, [], None, None
    for f in files:
        part = jlens.JacobianLens.load(str(f))
        if first is None:
            first = part
        elif part.source_layers != first.source_layers or part.d_model != first.d_model:
            raise ValueError(f"{f.name}: source_layers / d_model disagree")
        for k, j in part.jacobians.items():
            if keep is not None and f.name not in keep[k]:
                continue
            j = j.float() * part.n_prompts
            total[k] = total[k].add_(j) if k in total else j
            count[k] = count.get(k, 0) + part.n_prompts
        n += part.n_prompts
        del part
        cur = {k: v / count[k] for k, v in total.items()}
        if running is not None:  # relative change of the running mean, max over layers
            rel = max(((cur[k] - running[k]).norm() / running[k].norm()).item()
                      for k in running if k in cur)  # fmt: skip
            curve.append({"n_prompts": n, "max_rel_change": round(rel, 5)})
        running = cur
    final = jlens.JacobianLens(jacobians=running, n_prompts=n, d_model=first.d_model)
    final.save(f"/vol/{tag}/lens.pt", dtype=torch.float16)
    meta = {
        "tag": tag,
        "n_prompts": n,
        "chunks": len(files),
        "convergence": curve,
        "recipe": {
            "dataset": "Salesforce/wikitext wikitext-103-raw-v1 train",
            "min_chars": MIN_CHARS,
            "max_chars": MAX_CHARS,
            "max_seq_len": MAX_SEQ,
            "dim_batch": dim_batch,  # rows per backward pass: memory only, the lens is exact
            "trim_k": trim_k,
            "chunks_dropped_per_layer": {
                k: len(files) - len(v) for k, v in (keep or {}).items() if len(v) < len(files)
            },
            "target_layer": "final",
            "estimator": "anthropics/jacobian-lens @ 581d3986 (vendored)",
        },
    }
    Path(f"/vol/{tag}/meta.json").write_text(json.dumps(meta, indent=1))
    vol.commit()
    return meta


@app.local_entrypoint()
def main(
    model_id: str,
    revision: str,
    tag: str,
    n_prompts: int = 400,
    chunk_size: int = 10,
    dim_batch: int = DIM_BATCH,
    target: int = -1,
    trim_k: float = 0.0,
    merge_only: bool = False,
):
    """``dim_batch`` < 64 for big subjects (Gemma-4-31B OOMs an H200 at 64): it only sets how
    many Jacobian rows one backward pass computes, so the fitted lens is the same."""
    import json

    starts = list(range(0, n_prompts, chunk_size))
    args = [(model_id, revision, tag, s, chunk_size, n_prompts, dim_batch, target) for s in starts]
    if not merge_only:
        for res in chunk.starmap(args, return_exceptions=True):
            print(res if not isinstance(res, Exception) else f"chunk failed: {res}")
    print(json.dumps(merge.remote(tag, dim_batch, trim_k), indent=1)[:3000])

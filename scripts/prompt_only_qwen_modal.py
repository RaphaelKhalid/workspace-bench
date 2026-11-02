"""Prompt-only summaries from stock Qwen3.6-27B at each family's CURRENT read positions (vLLM on
Modal), in the readouts contract, for re-measuring the frozen prompt-only floors.

Same template and sampling as the frozen floors (`evals/baselines/README.md` §Prompt-only and
`wsbench.adapt.floors`): the rendered prompt decoded through the read token, "What would a
language model be thinking about on this token?", k=1, T=1.0, top_p 0.95, top_k 64, 256 new
tokens, thinking off; at most 32 read positions per item (evenly spaced). Rows are written for
ONE layer (the family grid's first), as the frozen floors were: judge them with `layers=<it>`.

    PYTHONPATH=src modal run scripts/prompt_only_qwen_modal.py --families poetry \
        [--out outputs/prompt_only_qwen] [--bank-root DIR] [--shards 2]
"""

import json
import os
from pathlib import Path

import modal

app = modal.App("wsb-prompt-only-qwen")
hf = modal.Volume.from_name("jlens-hf-cache", create_if_missing=True)
MODEL = "Qwen/Qwen3.6-27B"
image = (  # ati_qwen_modal.py's recipe
    modal.Image.from_registry("nvidia/cuda:13.0.1-devel-ubuntu22.04", add_python="3.12")
    .pip_install("vllm==0.31.0", "transformers==5.17.0", "huggingface_hub")
    .env({"HF_HOME": "/hf", "VLLM_WORKER_MULTIPROC_METHOD": "spawn", "PYTHONUNBUFFERED": "1"})
)
TEMPLATE = (
    "Below is a prompt that was given to a language model, cut off at a specific token. The token "
    "in question is the final token of the text below: {token!r}.\n\n<prompt>\n{prefix}\n</prompt>"
    "\n\nWhat would a language model be thinking about on this token? Please write me a summary "
    "for this token."
)
MAX_POS, MAX_NEW = 32, 256


@app.function(image=image, gpu="H200", volumes={"/hf": hf}, timeout=3 * 3600, max_containers=8)
def generate(reqs: list[dict], max_model_len: int) -> list[str]:
    from vllm import LLM, SamplingParams
    from vllm.inputs import TokensPrompt

    llm = LLM(MODEL, max_model_len=max_model_len, gpu_memory_utilization=0.90, seed=0)
    hf.commit()
    params = [
        SamplingParams(temperature=1.0, top_p=0.95, top_k=64, max_tokens=MAX_NEW, seed=r["seed"])
        for r in reqs
    ]
    outs = llm.generate([TokensPrompt(prompt_token_ids=r["ids"]) for r in reqs], params)
    return [o.outputs[0].text for o in outs]


def build(families: list[str]) -> list[dict]:
    from transformers import AutoTokenizer

    from wsbench import readplan
    from wsbench.baselines.text_inversion import qwen_prompt_ids, qwen_seed
    from wsbench.produce.render import render

    tok = AutoTokenizer.from_pretrained(MODEL)
    kw = {"skip_special_tokens": False, "clean_up_tokenization_spaces": False}
    reqs = []
    for fam in families:
        for spec in readplan.plan(fam):
            r = render(spec, tok)
            pos = sorted({p % len(r) for p in readplan.resolve(spec.positions, r.tokens)})
            if len(pos) > MAX_POS:
                pos = [pos[round(k * (len(pos) - 1) / (MAX_POS - 1))] for k in range(MAX_POS)]
            for p in pos:
                msg = TEMPLATE.format(
                    token=tok.decode([r.ids[p]], **kw), prefix=tok.decode(r.ids[: p + 1], **kw)
                )
                reqs.append(
                    {
                        "family": fam,
                        "id": spec.id,
                        "layer": spec.layers[0],
                        "pos": p - len(r) if spec.positions.get("kind") == "all_from_end" else p,
                        "ids": qwen_prompt_ids(tok, msg),
                        "seed": qwen_seed(fam, f"{spec.id}|{p}"),
                    }
                )
    return reqs


@app.local_entrypoint()
def main(
    families: str, out: str = "outputs/prompt_only_qwen", bank_root: str = "", shards: int = 2
):
    if bank_root:
        os.environ["WSB_BANK_ROOT"] = bank_root
    reqs = build([f for f in families.split(",") if f])
    max_len = max(len(r["ids"]) for r in reqs) + MAX_NEW + 16
    k = max(1, min(shards, len(reqs)))
    parts = [reqs[i::k] for i in range(k)]
    texts: dict[int, str] = {}
    for part, res in zip(
        parts, generate.map(parts, kwargs={"max_model_len": max_len}), strict=True
    ):
        for r, t in zip(part, res, strict=True):
            texts[id(r)] = t
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    by_fam: dict[str, list[str]] = {}
    for r in reqs:
        row = {
            "id": r["id"],
            "layer": r["layer"],
            "pos": r["pos"],
            "samples": [texts[id(r)].strip()],
        }
        by_fam.setdefault(r["family"], []).append(json.dumps(row, ensure_ascii=False))
    for fam, rows in by_fam.items():
        (d / f"{fam}.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"{fam}: {len(rows)} prompt-only summaries -> {d / f'{fam}.jsonl'}")

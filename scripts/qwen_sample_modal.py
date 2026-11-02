"""Qwen3.6-27B sampling for item gating (gpu.md G10), vLLM on Modal H200s.

Generic: every request row carries its own settings (``wsbench.gate_sampling``):
``{key, family, messages | text, n, temperature, top_p, top_k, max_tokens, enable_thinking,
greedy, prefill?}``. A jailbreak candidate is three rows (thinking x10, no-thinking x10, greedy).
Ids are built on the box (the read plan's chat render for ``messages``; ``qwen_prompt_ids`` for
``text``); Modal only generates. Output rows ``{key, family, draw, greedy, text, thinking,
finish_reason}`` are written per shard to the ``wsb-gate-samples`` volume (resumable: a key
already on the volume is skipped) and then merged into ``--out``. Grading is local, per family.

    PYTHONPATH=src modal run scripts/qwen_sample_modal.py --requests gate/jb.jsonl \
        --out gate/jb.samples.jsonl [--shards 8]
"""

import json
from pathlib import Path

import modal

app = modal.App("wsb-qwen-sample")
hf = modal.Volume.from_name("jlens-hf-cache", create_if_missing=True)
samples_vol = modal.Volume.from_name("wsb-gate-samples", create_if_missing=True)
VOL = "/samples"
MODEL = "Qwen/Qwen3.6-27B"
image = (  # ati_qwen_modal.py's recipe
    modal.Image.from_registry("nvidia/cuda:13.0.1-devel-ubuntu22.04", add_python="3.12")
    .pip_install("vllm==0.31.0", "transformers==5.17.0", "huggingface_hub")
    .env({"HF_HOME": "/hf", "VLLM_WORKER_MULTIPROC_METHOD": "spawn", "PYTHONUNBUFFERED": "1"})
    .add_local_python_source("wsbench")
)


@app.function(
    image=image, gpu="H200", volumes={"/hf": hf, VOL: samples_vol}, timeout=6 * 3600,
    max_containers=8,
)  # fmt: skip
def sample_shard(run: str, shard: int, reqs: list[dict], max_model_len: int) -> int:
    from vllm import LLM, SamplingParams
    from vllm.inputs import TokensPrompt

    from wsbench import gate_sampling as gs

    path = Path(VOL) / run / f"shard{shard}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                done.add(json.loads(line)["key"])
            except (json.JSONDecodeError, KeyError):
                continue
    todo = [r for r in reqs if r["key"] not in done]
    if not todo:
        return 0
    llm = LLM(MODEL, max_model_len=max_model_len, gpu_memory_utilization=0.90, seed=0)
    hf.commit()
    with path.open("a", encoding="utf-8") as fh:
        for r in todo:
            prompt = TokensPrompt(prompt_token_ids=r["ids"])
            outs = []
            for kw in gs.sampling_params(r):
                (o,) = llm.generate([prompt], SamplingParams(**kw))
                outs.append([(c.text, c.finish_reason) for c in o.outputs])
            for row in gs.output_rows(r, outs):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
    samples_vol.commit()
    return len(todo)


@app.local_entrypoint()
def main(requests: str, out: str, shards: int = 8, run: str = "") -> None:
    from transformers import AutoTokenizer

    from wsbench import gate_sampling as gs

    tok = AutoTokenizer.from_pretrained(MODEL)
    rows = [json.loads(x) for x in Path(requests).read_text().splitlines() if x.strip()]
    for r in rows:
        gs.validate(r)
        r["ids"] = gs.request_ids(tok, r)
    run = run or Path(requests).stem
    mml = max(len(r["ids"]) + int(r["max_tokens"]) for r in rows) + 16
    k = max(1, min(shards, len(rows)))
    parts = [rows[i::k] for i in range(k)]
    results = list(
        sample_shard.starmap(
            [(run, i, p, mml) for i, p in enumerate(parts)], return_exceptions=True
        )
    )
    errs = [r for r in results if isinstance(r, BaseException)]
    print(f"{sum(r for r in results if isinstance(r, int))} requests sampled; {len(errs)} failed")
    merged: list[str] = []
    for entry in samples_vol.listdir(run):
        merged += b"".join(samples_vol.read_file(entry.path)).decode().splitlines()
    Path(out).write_text("\n".join(x for x in merged if x.strip()) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(merged)} rows)")

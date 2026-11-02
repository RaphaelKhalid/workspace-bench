"""Gate new buggy_code clean twins on Qwen3.6-27B (plan 0030 §1), vLLM on Modal.

(a) capability: the question ``capable/questions.py`` asks of a buggy_code item ("What happens when
this program is run? State the output or the failure in one line."), chat template, thinking off,
greedy + 10 samples at T=0.7; (b) no invented bug: the bare program (the family's render: plain
text, nothing asked) continued greedily for 256 tokens. Writes the raw generations; grading
(Opus, ``--grade``) is done on the box with ``scripts/buggy_twin_gate_grade.py``.

    PYTHONPATH=src modal run scripts/buggy_twin_gate_modal.py --twins outputs/new_twins.json \
        --out outputs/twin_gate_gen.json
"""

import json
from pathlib import Path

import modal

app = modal.App("wsb-buggy-twin-gate")
hf = modal.Volume.from_name("jlens-hf-cache", create_if_missing=True)
MODEL = "Qwen/Qwen3.6-27B"
image = (  # ati_qwen_modal.py's recipe
    modal.Image.from_registry("nvidia/cuda:13.0.1-devel-ubuntu22.04", add_python="3.12")
    .pip_install("vllm==0.31.0", "transformers==5.17.0", "huggingface_hub")
    .env({"HF_HOME": "/hf", "VLLM_WORKER_MULTIPROC_METHOD": "spawn", "PYTHONUNBUFFERED": "1"})
)
QUESTION = "\n\nWhat happens when this program is run? State the output or the failure in one line."
N_SAMPLES, T_SAMPLE, MAX_ANSWER, MAX_CONT = 10, 0.7, 128, 256


@app.function(image=image, gpu="H200", volumes={"/hf": hf}, timeout=2 * 3600)
def generate(chat_ids: list[list[int]], bare_ids: list[list[int]]) -> dict:
    from vllm import LLM, SamplingParams
    from vllm.inputs import TokensPrompt

    llm = LLM(MODEL, max_model_len=4096, gpu_memory_utilization=0.90, seed=0)
    hf.commit()
    greedy = SamplingParams(temperature=0.0, max_tokens=MAX_ANSWER)
    sampled = SamplingParams(temperature=T_SAMPLE, max_tokens=MAX_ANSWER, n=N_SAMPLES, seed=7)
    cont = SamplingParams(temperature=0.0, max_tokens=MAX_CONT)
    toks = [TokensPrompt(prompt_token_ids=i) for i in chat_ids]
    g = [o.outputs[0].text for o in llm.generate(toks, greedy)]
    s = [[x.text for x in o.outputs] for o in llm.generate(toks, sampled)]
    b = [
        o.outputs[0].text
        for o in llm.generate([TokensPrompt(prompt_token_ids=i) for i in bare_ids], cont)
    ]
    return {"greedy": g, "samples": s, "continuation": b}


@app.local_entrypoint()
def main(twins: str = "outputs/new_twins.json", out: str = "outputs/twin_gate_gen.json"):
    from transformers import AutoTokenizer

    from wsbench.baselines.text_inversion import qwen_prompt_ids

    tok = AutoTokenizer.from_pretrained(MODEL)
    items = json.loads(Path(twins).read_text())["twins"]
    chat = [qwen_prompt_ids(tok, it["code"] + QUESTION) for it in items]
    bare = [tok(it["code"], add_special_tokens=False).input_ids for it in items]
    res = generate.remote(chat, bare)
    rows = [
        {
            "name": it["name"],
            "twin": it["twin"],
            "verified": it["verified"],
            "greedy": res["greedy"][k],
            "samples": res["samples"][k],
            "continuation": res["continuation"][k],
        }
        for k, it in enumerate(items)
    ]
    Path(out).write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(f"wrote {out}: {len(rows)} twins")

"""``adapt_jlens.py`` on a Modal H200 for subjects too big for the box (Gemma-4-31B): the same
script, unchanged, with global-workspace mounted at its box path, the HF cache volume, and the
fitted lens from the ``adapt-jlens`` volume. Outputs land on ``adapt-jlens:<tag>/adapted/<tag>/``;
pull ``jlens_concept_pr`` back into ``adapted/<tag>/``.

    modal run scripts/adapt_jlens_modal.py --model google/gemma-4-31b-it \\
        --revision 842da379... --tag gemma-4-31b-it --layers 19,22,26,30,34,38,41,45,49,52,56
    modal volume get adapt-jlens gemma-4-31b-it/adapted/gemma-4-31b-it/jlens_concept_pr \\
        adapted/gemma-4-31b-it/
"""

from pathlib import Path

import modal

GW = "/workspace/agam/global-workspace"
OLS = f"{GW}/scripts/oracle_lens_evals/olens_sglang"
WSB = Path(__file__).resolve().parents[1]
app = modal.App("adapt-jlens-bank")
vol = modal.Volume.from_name("adapt-jlens", create_if_missing=True)
hf = modal.Volume.from_name("adapt-hf-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.11.0",
        "transformers==5.17.0",
        "accelerate>=1.14",
        "safetensors",
        "huggingface_hub",
        "numpy",
        "jaxtyping",
        "einops",
        "beartype",
        "pydra-config",
        "orjson",
        "tqdm",
    )
    .env({"HF_HOME": "/hf", "PYTHONPATH": f"/root/wsb/src:{GW}/src:{OLS}", "PYTHONUNBUFFERED": "1"})
    .add_local_dir(f"{GW}/src", f"{GW}/src", ignore=["**/__pycache__"])
    .add_local_dir(OLS, OLS, ignore=["**/__pycache__"])
    .add_local_dir(
        f"{GW}/scripts/oracle_lens_evals/jlens_pr",
        f"{GW}/scripts/oracle_lens_evals/jlens_pr",
        ignore=["**/__pycache__"],
    )
    .add_local_file(
        f"{GW}/evals/workspace-bench/jlens_pr/items.json",
        f"{GW}/evals/workspace-bench/jlens_pr/items.json",
    )
    .add_local_file(str(WSB / "scripts/adapt_jlens.py"), "/root/wsb/scripts/adapt_jlens.py")
    # adapt_jlens imports wsbench.adapt.template (the subject's BOS prefix for raw seeds)
    .add_local_dir(str(WSB / "src/wsbench"), "/root/wsb/src/wsbench", ignore=["**/__pycache__"])
)


@app.function(image=image, gpu="H200", volumes={"/vol": vol, "/hf": hf}, timeout=8 * 3600,
              memory=131072)  # fmt: skip
def build(
    model: str, revision: str, tag: str, layers: str, stages: str, readout: str = "cosine"
) -> str:
    import os
    import subprocess

    from huggingface_hub import snapshot_download

    # adapt_jlens resolves the pinned snapshot offline: complete it first (the fit job cached
    # only what from_pretrained needed)
    snapshot_download(model, revision=revision)
    hf.commit()
    out = Path(f"/vol/{tag}/adapted")
    out.mkdir(parents=True, exist_ok=True)
    if not Path("/root/wsb/adapted").exists():
        os.symlink(out, "/root/wsb/adapted")  # adapt_jlens writes WSB/adapted/<tag>/...
    for st in stages.split(","):  # one process per stage, as on the box (frees GPU memory)
        print(f"== {st}", flush=True)
        subprocess.run(
            ["python", "/root/wsb/scripts/adapt_jlens.py", "--model", model, "--revision",
             revision, "--tag", tag, "--layers", layers, "--lens", "lens.pt", "--lens-repo",
             f"/vol/{tag}/lens.pt", "--stage", st, "--readout", readout],
            check=True,
        )  # fmt: skip
        vol.commit()
    return str(out / tag / "jlens_concept_pr")


@app.local_entrypoint()
def main(model: str, revision: str, tag: str, layers: str,
         stages: str = "rollout,capture,jlens,assemble", readout: str = "cosine"):  # fmt: skip
    print(build.remote(model, revision, tag, layers, stages, readout))

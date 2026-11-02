"""OPTIONAL: run gate_hf.py on a rented GPU with Modal (https://modal.com) instead of a local
GPU. Generic: your own Modal account, no secrets needed for deterministic grading.

    modal run .claude/skills/wsb-new-questions/scripts/modal_gate.py \\
        --family multihop --bank cand/multihop.json --model Qwen/Qwen3.5-0.8B --out gated/multihop

Extra flags for gate_hf.py go in --extra (a quoted string). An LLM grader (`--extra
"--grader <id>"`) needs its key as a Modal secret: `modal secret create openrouter
OPENROUTER_API_KEY=...` once, then run with `WSB_MODAL_SECRETS=openrouter` (comma list); never
pass a key on the command line or bake it into the image. --runner <file.py> as in
modal_script.py (a custom launcher, optionally with setup_env). moral_gate.py and
buggy_gate.py run through the sibling modal_script.py.
"""

import json
import os
from pathlib import Path

import modal

_HERE = Path(__file__).resolve()
# .claude/skills/<skill>/scripts/ -> repo root (only meaningful on the client side)
REPO = _HERE.parents[4] if len(_HERE.parents) > 4 else Path("/repo")
# a small subject fits any GPU; set WSB_GATE_GPU=H100 (etc.) for >= 9B models
GPU = os.environ.get("WSB_GATE_GPU", "L40S")  # "none" = CPU only (pass --extra "--device cpu")
GPU_ARG = None if GPU.lower() == "none" else GPU
SECRETS = [
    modal.Secret.from_name(n.strip())
    for n in os.environ.get("WSB_MODAL_SECRETS", "").split(",")
    if n.strip()
]

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.9.1",
        "transformers>=5",
        "accelerate",
        "jinja2",
        "pronouncing",
        "openai>=1.40",
        "anthropic>=1.0",
        "numpy>=1.26",
        "pydra-config>=0.0.17",
    )
    .add_local_dir(REPO / "src", "/repo/src", ignore=["**/__pycache__"])
    .add_local_dir(REPO / "evals", "/repo/evals", ignore=["jlens_concept_pr/gen-*"])
    .add_local_dir(
        REPO / ".claude" / "skills" / "wsb-new-questions" / "scripts",
        "/repo/.claude/skills/wsb-new-questions/scripts",
        ignore=["**/__pycache__"],
    )
)
app = modal.App("wsb-gate-hf", image=image)
hf_cache = modal.Volume.from_name("wsb-gate-hf-cache", create_if_missing=True)


def _run(argv: list[str], runner_text: str = "") -> dict[str, str]:
    import subprocess

    env = {**os.environ, "PYTHONPATH": "/repo/src", "HF_HOME": "/cache"}
    script = "/repo/.claude/skills/wsb-new-questions/scripts/gate_hf.py"
    cmd = ["python", script, *argv, "--repo", "/repo", "--out", "/tmp/out"]
    if runner_text:  # same contract as modal_script.py --runner
        Path("/tmp/runner.py").write_text(runner_text, encoding="utf-8")
        cmd = ["python", "/tmp/runner.py", *cmd[1:]]
        hooks: dict = {}
        exec(compile(runner_text, "/tmp/runner.py", "exec"), hooks)
        if callable(hooks.get("setup_env")):
            env = hooks["setup_env"](env)
    p = subprocess.run(cmd, cwd="/repo", env=env)
    hf_cache.commit()
    if p.returncode != 0:
        raise RuntimeError(f"gate_hf.py exited {p.returncode}")
    return {f: Path("/tmp/out", f).read_text() for f in ("items.json", "gate.json", "summary.json")}


@app.function(
    gpu=GPU_ARG,
    cpu=8.0,
    memory=32768,
    timeout=4 * 3600,
    volumes={"/cache": hf_cache},
    secrets=SECRETS,
)
def gate(argv: list[str], bank_text: str, runner_text: str = "") -> dict[str, str]:
    Path("/tmp/bank.json").write_text(bank_text)
    return _run([*argv, "--bank", "/tmp/bank.json"], runner_text)


@app.local_entrypoint()
def main(family: str, bank: str, model: str, out: str, extra: str = "", runner: str = "") -> None:
    argv = ["--family", family, "--model", model, *extra.split()]
    rt = Path(runner).read_text(encoding="utf-8") if runner else ""
    res = gate.remote(argv, Path(bank).read_text(encoding="utf-8"), rt)
    dst = Path(out)
    dst.mkdir(parents=True, exist_ok=True)
    for name, text in res.items():
        (dst / name).write_text(text, encoding="utf-8")
    print(json.dumps(json.loads(res["summary.json"]), indent=1))

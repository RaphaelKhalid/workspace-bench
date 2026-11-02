"""OPTIONAL: run moral_gate.py or buggy_gate.py (GPU stage + LLM steps) on Modal, from your own
Modal account. The sibling of modal_gate.py (which runs only gate_hf.py).

    # moral: elicit (GPU) + distil (LLM) + commit/gate in one container
    WSB_MODAL_SECRETS=anthropic modal run \\
        .claude/skills/wsb-new-questions/scripts/modal_script.py \\
        --script moral_gate.py --bank cand/moral.json --out gated/moral \\
        --extra "--model Qwen/Qwen3.5-2B --distiller claude-opus-5"
    # buggy: subject gates + LLM volunteering judge
    WSB_MODAL_SECRETS=anthropic modal run \\
        .claude/skills/wsb-new-questions/scripts/modal_script.py \\
        --script buggy_gate.py --stage gate --bank cand/buggy.json --out gated/buggy \\
        --extra "--model Qwen/Qwen3.5-2B --judge claude-opus-5"

Credentials: an LLM step reads the key the repo reads (`ANTHROPIC_API_KEY` for `claude-*`
ids, `OPENROUTER_API_KEY` otherwise) from the container environment. Create a Modal secret
once (`modal secret create anthropic ANTHROPIC_API_KEY=...`) and name it in
`WSB_MODAL_SECRETS` (comma list); never pass a key on the command line or bake it into the
image. Without a secret only the GPU stages run (moral then writes distil_requests.json).

The JSON files already in --out are uploaded first, so a re-run continues (moral stage 3 from
an earlier elicited.json, e.g. `--extra "--distilled /tmp/out/distilled.json"`); --files
uploads extra local files to /tmp/in/<name>. --runner <file.py> (advanced) runs the script
through your own launcher (`python runner.py <script> <args...>`), e.g. to adapt auth; if it
defines `setup_env(env) -> env`, that runs first in the Modal function process (where the
`modal` client is importable; the launched subprocess has no `modal`). Keep the runner's
top level free of side effects: it is also exec'd to find `setup_env`.
"""

import json
import os
import subprocess
from pathlib import Path

import modal

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[4] if len(_HERE.parents) > 4 else Path("/repo")
SKILL = "/repo/.claude/skills/wsb-new-questions/scripts"
GPU = os.environ.get("WSB_GATE_GPU", "L40S")  # "none" = CPU (add --device cpu --dtype float32)
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
    .add_local_dir(REPO / ".claude" / "skills" / "wsb-new-questions" / "scripts", SKILL)
)
app = modal.App("wsb-skill-script", image=image)
hf_cache = modal.Volume.from_name("wsb-gate-hf-cache", create_if_missing=True)


@app.function(
    gpu=GPU_ARG,
    cpu=8.0,
    memory=32768,
    timeout=4 * 3600,
    volumes={"/cache": hf_cache},
    secrets=SECRETS,
)
def run(
    script: str,
    argv: list[str],
    bank_text: str,
    out_files: dict[str, str],
    in_files: dict[str, str],
    runner_text: str,
) -> dict:
    out, inp = Path("/tmp/out"), Path("/tmp/in")
    out.mkdir(exist_ok=True)
    inp.mkdir(exist_ok=True)
    for name, text in out_files.items():
        (out / name).write_text(text, encoding="utf-8")
    for name, text in in_files.items():
        (inp / name).write_text(text, encoding="utf-8")
    Path("/tmp/bank.json").write_text(bank_text, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": "/repo/src", "HF_HOME": "/cache"}
    cmd = ["python", f"{SKILL}/{script}", *argv]
    if runner_text:
        Path("/tmp/runner.py").write_text(runner_text, encoding="utf-8")
        cmd = ["python", "/tmp/runner.py", f"{SKILL}/{script}", *argv]
        hooks: dict = {}
        exec(compile(runner_text, "/tmp/runner.py", "exec"), hooks)  # defines functions only
        if callable(hooks.get("setup_env")):
            env = hooks["setup_env"](env)  # runs here, where the modal client is importable
    p = subprocess.run(cmd, cwd="/repo", env=env)
    hf_cache.commit()
    return {
        "returncode": p.returncode,
        "files": {f.name: f.read_text() for f in out.glob("*.json")},
    }


@app.local_entrypoint()
def main(
    script: str,
    bank: str,
    out: str,
    extra: str = "",
    stage: str = "",
    files: str = "",
    runner: str = "",
) -> None:
    if script not in ("moral_gate.py", "buggy_gate.py"):
        raise SystemExit("--script must be moral_gate.py or buggy_gate.py (gate_hf: modal_gate.py)")
    dst = Path(out)
    argv = [*([stage] if stage else []), "--bank", "/tmp/bank.json", "--out", "/tmp/out"]
    argv += extra.split()
    prior = (
        {f.name: f.read_text(encoding="utf-8") for f in dst.glob("*.json")} if dst.is_dir() else {}
    )
    ins = {Path(f).name: Path(f).read_text(encoding="utf-8") for f in files.split(",") if f}
    res = run.remote(
        script,
        argv,
        Path(bank).read_text(encoding="utf-8"),
        prior,
        ins,
        Path(runner).read_text(encoding="utf-8") if runner else "",
    )
    dst.mkdir(parents=True, exist_ok=True)
    for name, text in res["files"].items():
        (dst / name).write_text(text, encoding="utf-8")
    print(f"returncode={res['returncode']} files={sorted(res['files'])}")
    if "summary.json" in res["files"]:
        print(json.dumps(json.loads(res["files"]["summary.json"]), indent=1))
    if res["returncode"]:
        raise SystemExit(res["returncode"])

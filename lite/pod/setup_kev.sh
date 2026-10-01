#!/usr/bin/env bash
# Kev-4B training/serving env + the harness for the one test read (steps proven on 2026-09-30's pods).
set -e
export HF_HOME=/workspace/hf PIP_BREAK_SYSTEM_PACKAGES=1
cd /workspace
log(){ echo "[$(date -u +%H:%M:%S)] $*"; }
log "harness deps"; pip install -q openai anthropic numpy pydra-config uv ninja 2>&1 | tail -1
mkdir -p wsb wsbjev/data/readouts/jailbreak_13site wsbjev/runs kevtrain
tar xzf wsb.tgz --no-same-owner -C wsb && tar xzf wsbjev_src.tgz --no-same-owner -C wsbjev
mv jlens.jsonl wsbjev/data/readouts/jailbreak_13site/ && mv vllm-cache.jsonl wsbjev/runs/ && mv test_items.txt kevtrain/
log "kev env"; [ -d kev ] || git clone -q https://github.com/jaredpalmer/kev.git
cd kev && uv sync --extra serve 2>&1 | tail -1 && uv pip install -q --python .venv/bin/python "flash-linear-attention==0.5.2" 2>&1 | tail -1
.venv/bin/python -c "import torch, fla; print('kev torch', torch.__version__, torch.cuda.is_available(), 'fla', fla.__version__)"
.venv/bin/python -c "from huggingface_hub import snapshot_download as s; s('jaredpalmer/kev-4b'); s('Qwen/Qwen3.5-4B-Base'); print('weights ok')"
cd /workspace && PYTHONPATH=/workspace/wsbjev/src:/workspace/wsb/src python -c "import wsbjev.route, wsbench; print('harness import ok')"
touch /workspace/SETUP_DONE; log "setup done"

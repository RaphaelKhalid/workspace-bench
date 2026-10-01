#!/usr/bin/env bash
# Kev-4B, fixed R2 recipe, on teacher labels in /workspace/kevtrain/train.jsonl; then serve and the ONE test read.
#   bash train_run.sh <run-name>
set -u
RUN=${1:-run}
export HF_HOME=/workspace/hf PIP_BREAK_SYSTEM_PACKAGES=1 PYTHONIOENCODING=utf-8
O=/workspace/kevft; mkdir -p $O
log(){ echo "[$(date -u +%H:%M:%S)] $*"; }
run() {
  cd /workspace/kev || return 1
  log "train $RUN: $(wc -l < /workspace/kevtrain/train.jsonl) records"
  .venv/bin/python -m kev.train --data /workspace/kevtrain/train.jsonl --base Qwen/Qwen3.5-4B-Base --init_from jaredpalmer/kev-4b \
    --epochs 2 --lr 5e-5 --batch 1 --accum 8 --dtype bf16 --checkpointing 1 --device cuda --max_state 2560 \
    --p_none 0 --p_none_distract 0 --p_distract 0 --seed 0 --out $O/$RUN || return 2
  log "serve $RUN"
  (PATH=/workspace/kev/.venv/bin:$PATH setsid nohup .venv/bin/python -m kev.serve --run $O/$RUN --port 8010 --host 127.0.0.1 > $O/$RUN-serve.log 2>&1 < /dev/null &)
  for i in $(seq 1 90); do curl -s -m 3 127.0.0.1:8010/v1/models >/dev/null && break; sleep 5; done
  curl -s -m 3 127.0.0.1:8010/v1/models >/dev/null || return 3
  log "test read"; bash /workspace/test_kev.sh $RUN; log "test exit $(cat /workspace/DONE_TEST_$RUN)"
}
run > $O/$RUN.log 2>&1
echo $? > /workspace/DONE_TRAIN_$RUN

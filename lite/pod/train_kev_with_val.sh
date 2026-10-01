#!/usr/bin/env bash
# One fine-tune recipe of Kev-4B (LoRA delta from the release) on the Qwen-teacher jailbreak records,
# then the validation score. Validation goes through kev.serve + `kev.benchmark --remote`, because
# local `kev.benchmark --data` silently skips states over the 384-token training context (all of ours).
#   bash train_kev.sh <run> <lr> <epochs> <max_state>
# Log: /workspace/kevft/<run>.log. Marker: /workspace/DONE_TRAIN_<run> (content = exit status).
set -u
export HF_HOME=/workspace/hf PIP_BREAK_SYSTEM_PACKAGES=1 PYTHONIOENCODING=utf-8
RUN=$1 LR=$2 EP=$3 MS=$4
D=/workspace/kevtrain O=/workspace/kevft PORT=8010
mkdir -p $O
log(){ echo "[$(date -u +%H:%M:%S)] $*"; }
run() {
  log "free the GPU"; for p in $(pgrep -f "[k]ev.serve"); do kill $p; done; sleep 10
  cd /workspace/kev || return 1
  log "train $RUN lr=$LR epochs=$EP max_state=$MS ($(wc -l < $D/train.jsonl) train records)"
  .venv/bin/python -m kev.train --data $D/train.jsonl --base Qwen/Qwen3.5-4B-Base --init_from jaredpalmer/kev-4b \
    --epochs $EP --lr $LR --batch 1 --accum 8 --dtype bf16 --checkpointing 1 --device cuda --max_state $MS \
    --p_none 0 --p_none_distract 0 --p_distract 0 --seed 0 --out $O/$RUN || return 2
  log "serve $RUN"
  (PATH=/workspace/vllm-env/bin:$PATH setsid nohup .venv/bin/python -m kev.serve --run $O/$RUN --port $PORT --host 127.0.0.1 \
    > $O/$RUN-serve.log 2>&1 < /dev/null &)
  for i in $(seq 1 90); do curl -s -m 3 127.0.0.1:$PORT/v1/models >/dev/null && break; sleep 5; done
  curl -s -m 3 127.0.0.1:$PORT/v1/models >/dev/null || return 3
  log "val benchmark ($(wc -l < $D/val.jsonl) records)"
  .venv/bin/python -m kev.benchmark --remote http://127.0.0.1:$PORT --data $D/val.jsonl --out $O/$RUN-val \
    --remote-concurrency 8 || return 4
  python3 /workspace/wsbjev/scripts/kev_val_kappa.py $O/$RUN-val
  log "done (serve left up on $PORT for the test run)"
}
run > $O/$RUN.log 2>&1
echo $? > /workspace/DONE_TRAIN_$RUN

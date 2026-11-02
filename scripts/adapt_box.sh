#!/usr/bin/env bash
# Run `python -m wsbench.adapt ...` on the RunPod box: the adapt venv on PATH (vLLM compiles with
# its ninja), the persistent HF cache, weights read offline. Usage: scripts/adapt_box.sh profile model=...
set -euo pipefail
ENV=${ADAPT_ENV:-/workspace/agam/envs/adapt}
export HF_HOME=${HF_HOME:-/workspace/.persist/huggingface}
# creds live only in RAM on the box (rp secrets: HF, Modal). Claude calls (llm= grading, author)
# use the judges' keyless OAuth token from the Modal Dict anthropic-oauth: never an API key.
if [ -f /dev/shm/compute.env ]; then set +u; source /dev/shm/compute.env; set -u; fi
unset ANTHROPIC_API_KEY
export MODAL_ENVIRONMENT=${MODAL_ENVIRONMENT:-agam}
export PATH="$ENV/bin:$PATH" HF_HUB_OFFLINE=${HF_HUB_OFFLINE:-1} PYTHONUNBUFFERED=1
# the pod caps the container at 4,608 threads: no BLAS thread pools (process pools stay <= 16)
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
cd "$(dirname "$0")/.."
# One GPU job at a time (vLLM takes most of the 24 GB): the GPU commands take the box lock.
# A caller that already holds it (a chain script that did `exec 9>LOCK; flock 9`) passes the
# open fd down, so it is not taken twice (that would deadlock against the parent).
LOCK=${ADAPT_GPU_LOCK:-/workspace/agam/logs/gpu.lock}
case "${1:-}" in
  profile|gate|auto|fill|hal|agentic|moral|floors)
    # stages that only call Claude / the CPU do not need the GPU
    case " $* " in *" stage=distil "*|*" stage=judge "*|*" stage=build "*|*" stage=apply "*) ;; *)
    if [ "$(readlink /proc/$$/fd/9 2>/dev/null)" != "$LOCK" ]; then
      exec 9>"$LOCK"; flock 9
    fi ;;
    esac ;;
esac
exec "$ENV/bin/python" -m wsbench.adapt "$@"

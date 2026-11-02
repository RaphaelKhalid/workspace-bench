#!/bin/bash
# re-judge poetry / basic_readout / moral_rationale with each subject's own golds on its normal-bank tags
# usage: run_normal_judge.sh SUBJECT CKPTDIR TAG [TAG...]
set -a; . /dev/shm/compute.env; set +a; export MODAL_ENVIRONMENT=agam; unset ANTHROPIC_API_KEY
cd /workspace/agam/workspace-bench
S=$1; C=$2; shift 2
for T in "$@"; do
  TD=/workspace/agam/olens_ckpts/$C/wsb/$T
  until [ -s $TD/judged_opus/moral_rationale/results.json ] && [ -s $TD/readouts/moral_rationale.jsonl ]; do sleep 30; done
  for F in poetry basic_readout moral_rationale; do
    D=outputs/normal_gated/$S/judged/$T/$F; mkdir -p $D
    [ -s $D/cells.jsonl ] || cp $TD/judged_opus/$F/cells.jsonl $D/cells.jsonl 2>/dev/null
    [ -s $D/results.json ] && continue
    /workspace/agam/envs/adapt/bin/python atlas/normal_gated.py judge $S $TD $F ${RPM:-420}
  done
  echo "DONE $S $T"
done

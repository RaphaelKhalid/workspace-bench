#!/bin/bash
# every 15 min for 12 h: gated scores -> bars -> atlas rebuild (gated + adaptive views)
cd /workspace/agam/workspace-bench
for i in $(seq 1 48); do
  /workspace/agam/envs/adapt/bin/python atlas/normal_gated.py score > /workspace/agam/logs/ng_score.txt 2>&1
  /workspace/agam/envs/adapt/bin/python /workspace/agam/experiments/wsbench-adapt/make_bars.py >/dev/null 2>&1
  /workspace/agam/envs/adapt/bin/python atlas/build.py > /workspace/agam/logs/atlas_build.txt 2>&1
  echo "refresh $(TZ=America/Los_Angeles date +%H:%M) PT"
  sleep 900
done

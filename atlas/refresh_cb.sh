#!/bin/bash
# Re-export the models whose sources changed and upload them to the mirror's volume.
# usage: refresh_cb.sh [--loop HOURS]   (loop: every 20 min)
source /workspace/.persist/env.sh; set -a; . /dev/shm/compute.env; set +a
export MODAL_ENVIRONMENT=agam
cd /workspace/agam/workspace-bench
M="uvx --python 3.12 modal@latest"
PY=/workspace/agam/envs/adapt/bin/python
VOL=wsbench-viewer-agam-data
once() {
  out=$($PY atlas/export_cb.py --changed --jobs 4 2>&1)
  echo "$out" | grep -v "^$"
  changed=$(echo "$out" | sed -n 's/^changed: //p')
  [ -z "$changed" ] || [ "$changed" = "-" ] && { echo "$(date -u +%H:%M) nothing changed"; return; }
  for m in ${changed//,/ }; do
    $M volume put -f $VOL outputs/cb_export/zips/$m.zip /zips/$m.zip >/dev/null 2>&1 && echo "uploaded $m"
  done
  $M volume put -f $VOL outputs/cb_export/our_models.json /our_models.json >/dev/null 2>&1 && echo "uploaded manifest $(date -u +%H:%M)"
}
if [ "$1" = "--loop" ]; then
  end=$(( $(date +%s) + ${2:-12} * 3600 ))
  while [ $(date +%s) -lt $end ]; do once; sleep 1200; done
else
  once
fi

#!/bin/bash
# usage: pull_tags.sh VOLUME SUBJECTDIR TAG [TAG...]  (parallel per tag)
# Pull per-item readouts + judge verdicts of the adaptive-bank OLens runs from their
# olens-*-wsbench Modal volumes into /workspace/agam/olens_ckpts/<subject>/wsb/<tag>/.
# Skips jailbreak_recognition + agentic_misalignment readouts/cells (100s of MB, scores only).
source /workspace/.persist/env.sh; set -a; . /dev/shm/compute.env; set +a
export MODAL_ENVIRONMENT=agam
M="uvx --python 3.12 modal@latest"
SKIP="jailbreak_recognition|agentic_misalignment"
pull() {  # vol subjdir tag
  local vol=$1 sd=$2 tag=$3 dst=/workspace/agam/olens_ckpts/$2/wsb/$3
  mkdir -p $dst/readouts $dst/judged_opus
  for f in summary_opus.json summary.json contract.json; do
    [ -s $dst/$f ] || $M volume get $vol runs/$tag/$f $dst/$f --force >/dev/null 2>&1
  done
  for p in $($M volume ls $vol runs/$tag/readouts | grep -Ev "$SKIP"); do
    f=$(basename $p); [ -s $dst/readouts/$f ] || $M volume get $vol $p $dst/readouts/$f --force >/dev/null 2>&1
  done
  for d in $($M volume ls $vol runs/$tag/judged_opus); do
    fam=$(basename $d); mkdir -p $dst/judged_opus/$fam
    for f in results.json cells.jsonl; do
      [[ $f == cells.jsonl && $fam =~ ^($SKIP) ]] && continue
      [ -s $dst/judged_opus/$fam/$f ] || $M volume get $vol runs/$tag/judged_opus/$fam/$f $dst/judged_opus/$fam/$f --force >/dev/null 2>&1
    done
  done
  echo "done $tag $(du -sh $dst | cut -f1)"
}
vol=$1; sd=$2; shift 2
for t in "$@"; do pull $vol $sd $t & done; wait
echo "ALL DONE $vol"

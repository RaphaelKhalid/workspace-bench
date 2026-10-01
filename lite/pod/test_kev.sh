#!/usr/bin/env bash
# The ONE test read: the chosen fine-tune (served on 8010 by train_kev.sh) judges the held-out test
# items through the jailbreak port, exactly like zero-shot run B (Qwen's official summaries replayed).
#   bash test_kev.sh <run>        items: /workspace/kevtrain/test_items.txt (comma-separated ids)
set -u
RUN=$1
export PYTHONPATH=/workspace/wsbjev/src:/workspace/wsb/src PYTHONIOENCODING=utf-8
export WSBJEV_KEV_URL=http://127.0.0.1:8010 WSBJEV_KEV_MODEL=kev-4b-ft-$RUN WSBJEV_KEV_CONCURRENCY=12
export WSBJEV_INTERP_FROM=/workspace/wsbjev/runs/vllm-cache.jsonl:qwen3.6-27b
export WSBJEV_RUN_LABEL="kev-4b ft-$RUN · jailbreak/jlens (test items)"
cd /workspace
curl -s -m 5 127.0.0.1:8010/v1/models >/dev/null || { echo "no kev serve on 8010" > /workspace/kevtest-$RUN.log; echo 3 > /workspace/DONE_TEST_$RUN; exit 3; }
python -m wsbjev judge family=jailbreak_recognition readouts=/workspace/wsbjev/data/readouts/jailbreak_13site/jlens.jsonl \
  out=/workspace/kevrun/ft-$RUN-test judge_model=jev-kev allow_missing=True items=$(cat /workspace/kevtrain/test_items.txt) \
  2>&1 | grep -E "^judge:|pass_rate|jev\[route\]|Error|Traceback" > /workspace/kevtest-$RUN.log
st=${PIPESTATUS[0]}
tar czf /workspace/kevtest-$RUN.tgz kevrun/ft-$RUN-test kevtest-$RUN.log
echo $st > /workspace/DONE_TEST_$RUN

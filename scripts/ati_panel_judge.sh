#!/usr/bin/env bash
# Judge every panel answerer's draws (plan 0019): for each answers/<answerer>/ under OUT and each
# draw, `wsbench run` over the readouts at layer 44 (allow_missing), the native-layer families
# without `layers=`. All LLM-judged families are judged by Opus 5.5 (the override replaces pins).
#   OUT=outputs/baselines/text_inversion FAMILIES="a b c" scripts/ati_panel_judge.sh
# Run with ANTHROPIC_API_KEY unset and ANTHROPIC_PROFILE=default (the ant profile). Resumable: each family's judge cache lives in
# its own judged/<answerer>/draw<d>/<family>/ directory.
set -euo pipefail
OUT=${OUT:-outputs/baselines/text_inversion}
DRAWS=${DRAWS:-3}
JUDGE=${JUDGE:-claude-opus-5-5}
NATIVE="arithmetic_intermediates buggy_code"
WSB=${WSB:-wsbench}

answerers=$(cd "$OUT/answers" && ls -d */ 2>/dev/null | tr -d / | grep -E '^(qwen|opus|sonnet|astra|argon)$' || true)
[ -n "$answerers" ] || { echo "no answers/<answerer>/ under $OUT" >&2; exit 2; }

JOBS=${JOBS:-24}  # concurrent `wsbench run` processes, one per (answerer, draw, family)
jobs_file=$(mktemp)
for a in $answerers; do
  for ((d = 0; d < DRAWS; d++)); do
    root="$OUT/readouts/$a/draw$d"
    [ -d "$root" ] || { echo "skip $a draw$d: no readouts (run stage=readouts)"; continue; }
    fams=${FAMILIES:-$(ls "$root" | sed 's/\.jsonl$//' | tr '\n' ' ')}
    if [[ "$a" == opus || "$a" == sonnet ]] && [ -f "$OUT/claude_slot.json" ]; then
      # judge a Claude model only on the families whose slot it fills (default slot: opus)
      fams=$(python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); a=sys.argv[2]
print(" ".join(f for f in sys.argv[3:] if s.get(f, {}).get("slot", "opus") == a))' \
        "$OUT/claude_slot.json" "$a" $fams)
    fi
    for f in $fams; do
      [ -s "$root/$f.jsonl" ] || continue
      # one family per process, each in its own out dir (its own judge cache)
      # never leave the line ending in a blank: `xargs -L 1` would join it with the next line
      if [[ " $NATIVE " == *" $f "* ]]; then lay="native"; else lay="layers=44"; fi
      echo "$f $root $OUT/judged/$a/draw$d/_runs/$f $OUT/judged/$a/draw$d $lay" >> "$jobs_file"
    done
  done
done
echo "$(wc -l < "$jobs_file") judge jobs, $JOBS at a time"
export WSB JUDGE
# shellcheck disable=SC2016
xargs -P "$JOBS" -L 1 bash -c '
  f=$0 root=$1 tmp=$2 dst=$3 lay=$4
  [ "$lay" = native ] && lay=""
  if [ -s "$dst/$f/results.json" ]; then exit 0; fi
  mkdir -p "$(dirname "$tmp")"
  $WSB run families="$f" readouts_root="$root" out="$tmp" judge_model="$JUDGE" $lay \
    allow_missing=True opts=aggregate=native > "$tmp.log" 2>&1 || { echo "FAILED $dst/$f (see $tmp.log)"; exit 1; }
  mkdir -p "$dst" && rm -rf "$dst/$f" && cp -r "$tmp/$f" "$dst/$f"
  echo "ok $dst/$f: $(grep -E "pass_rate=|score=" "$tmp.log" | tail -1 | cut -c1-120)"
' < "$jobs_file"
rm -f "$jobs_file"

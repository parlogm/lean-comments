#!/usr/bin/env bash
# usage: tools/run_case.sh <case> <with_skill|rule_only|without_skill> <iteration-dir>
# with_skill loads this repo as a plugin (rule + skill + hook); rule_only appends just the rule.
set -u
case_name=$1 config=$2 iter=$3
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case_dir=$ROOT/skills/lean-comments/evals/$case_name
iter="$(mkdir -p "$iter" && cd "$iter" && pwd)"
run=$iter/$case_name/$config
rm -rf "$run" && mkdir -p "$run/outputs"
cd "$run/outputs"
[ -x "$case_dir/place-files.sh" ] && "$case_dir/place-files.sh"

prompt=$(awk 'f>=2{print} /^---$/{f++}' "$case_dir/prompt.md" | sed '/./,$!d')

args=(--setting-sources project --model "${MODEL:-claude-opus-5-5}" --permission-mode acceptEdits
      --allowedTools "Read" "Write" "Edit" "Glob" "Grep" "Skill" "Bash(git *)" "Bash(python3 *)"
      "Bash(javac *)" "Bash(java *)" "Bash(node *)" "Bash(ls *)" "Bash(cat *)"
      --no-session-persistence --output-format stream-json --verbose)
case $config in
  rule_only) args+=(--append-system-prompt "$(cat "$ROOT/hooks/comment-rule.md")") ;;
  with_skill) args+=(--plugin-dir "$ROOT") ;;
esac

unset CLAUDECODE
start=$(date +%s)
claude -p "$prompt" "${args[@]}" > "../transcript.jsonl" 2> "../stderr.txt"
end=$(date +%s)
rm -rf .git
python3 - "$run" "$start" "$end" <<'PY'
import json, sys
run, start, end = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
tokens, dur = 0, (end - start) * 1000
for line in open(f"{run}/transcript.jsonl"):
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if ev.get("type") == "result":
        u = ev.get("usage", {})
        tokens = sum(u.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        dur = ev.get("duration_ms", dur)
json.dump({"total_tokens": tokens, "duration_ms": dur, "total_duration_seconds": round(dur / 1000, 1)},
          open(f"{run}/timing.json", "w"), indent=2)
PY
echo "done $case_name/$config"

#!/usr/bin/env bash
# usage: [MODEL=..] [PERMISSION_MODE=..] tools/run_case.sh <case> <with_skill|rule_only|hook_only|without_skill> <iteration-dir>
# with_skill loads this repo as a plugin (rule + skill + hooks); rule_only adds just the rule, hook_only just the hooks.
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

args=(--setting-sources project --model "${MODEL:-claude-opus-5-5}" --permission-mode "${PERMISSION_MODE:-acceptEdits}"
      --allowedTools "Read" "Write" "Edit" "Glob" "Grep" "Skill" "Bash(git *)" "Bash(python3 *)"
      "Bash(javac *)" "Bash(java *)" "Bash(node *)" "Bash(ls *)" "Bash(cat *)" "Bash(sed *)" "Bash(perl *)"
      --no-session-persistence --output-format stream-json --verbose)
case $config in
  rule_only) args+=(--append-system-prompt "$(cat "$ROOT/hooks/comment-rule.md")") ;;
  with_skill) args+=(--plugin-dir "$ROOT") ;;
  hook_only)
    args+=(--settings "$(python3 - "$ROOT/hooks/run" <<'PY'
import json, shlex, sys
run = shlex.quote(sys.argv[1])
def hook(command, **extra):
    return [{"hooks": [{"type": "command", "command": f"sh {run} {command}", "timeout": 30, **extra}]}]
hooks = {"UserPromptSubmit": hook("user-prompt-submit", **{"async": True}), "Stop": hook("stop"),
         "PostToolUse": [{**hook("post-tool-use")[0], "matcher": "Edit|Write|MultiEdit"}]}
print(json.dumps({"hooks": hooks}))
PY
)") ;;
esac

# The turn-end hook only checks git repos.
[ -d .git ] || { git init -q && git add -A && git -c user.name=eval -c user.email=eval@example.com commit -qm base --allow-empty; }

unset CLAUDECODE
start=$(date +%s)
claude -p "$prompt" "${args[@]}" < /dev/null > "../transcript.jsonl" 2> "../stderr.txt"
end=$(date +%s)
rm -rf .git
python3 - "$run" "$start" "$end" <<'PY'
import json, re, sys
run, start, end = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
tokens, dur = 0, (end - start) * 1000
hook_flags = edit_tool_writes = bash_writes = 0
bash_write = re.compile(r"\bsed\s+-i|\bperl\s+-\w*i|write_text\(|open\([^)]*['\"][wa]|(?:>|\btee)\s*['\"]?[\w./-]+\.\w+")
for line in open(f"{run}/transcript.jsonl"):
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if ev.get("type") == "result":
        u = ev.get("usage", {})
        tokens = sum(u.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        dur = ev.get("duration_ms", dur)
    if ev.get("type") != "assistant":
        hook_flags += line.count("has comments to trim.")
        continue
    for block in ev.get("message", {}).get("content", []):
        if block.get("type") != "tool_use":
            continue
        if block.get("name") in ("Edit", "Write", "MultiEdit"):
            edit_tool_writes += 1
        elif block.get("name") == "Bash" and bash_write.search(block.get("input", {}).get("command", "")):
            bash_writes += 1
json.dump({"total_tokens": tokens, "duration_ms": dur, "total_duration_seconds": round(dur / 1000, 1),
           "hook_flags": hook_flags, "edit_tool_writes": edit_tool_writes, "bash_writes": bash_writes},
          open(f"{run}/timing.json", "w"), indent=2)
PY
echo "done $case_name/$config"

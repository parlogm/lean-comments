#!/usr/bin/env python3
"""SessionStart hook: puts the comment rule in context, the way a CLAUDE.md section would."""
import json
import os
import pathlib

if os.environ.get("CLAUDE_LEAN_COMMENTS", "").lower() != "off":
    rule = (pathlib.Path(__file__).parent / "comment-rule.md").read_text(encoding="utf-8")
    if os.environ.get("COPILOT_CLI"):
        print(json.dumps({"additionalContext": rule}))
    else:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": rule}}))

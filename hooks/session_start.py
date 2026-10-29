#!/usr/bin/env python3
"""SessionStart hook: puts the comment rule in context, the way a CLAUDE.md section would."""
import json
import os
import pathlib

if os.environ.get("CLAUDE_LEAN_COMMENTS", "").lower() != "off":
    rule = (pathlib.Path(__file__).parent / "comment-rule.md").read_text()
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": rule}}))

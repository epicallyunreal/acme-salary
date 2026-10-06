#!/usr/bin/env python3
"""PreToolUse hook for pip install / npm install: remind about rule 9.

No permission decision is returned, so the normal flow (an ask rule) still applies.
"""
import json
import sys

try:
    json.load(sys.stdin)
except Exception:
    pass

print(
    json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": (
                    "Rule 9 applies to this install: a new runtime dependency needs a "
                    "one-line entry in docs/DECISIONS.md (what it is and why) in the same "
                    "commit. Dev-only tools such as linters and test libraries are exempt."
                ),
            }
        }
    )
)

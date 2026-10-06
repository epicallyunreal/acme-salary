#!/usr/bin/env python3
"""PreToolUse hook on Bash: when the command installs a package, remind about rule 9.

Exits silently for every other command. No permission decision is returned, so the
normal flow (an ask rule for installs) still applies.
"""
import json
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

command = (data.get("tool_input") or {}).get("command", "")
if not re.search(r"\b(pip|pip3|uv|poetry)\s+(install|add)\b|\bnpm\s+(install|i|add)\b|\bpnpm\s+add\b|\byarn\s+add\b", command):
    sys.exit(0)

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

#!/usr/bin/env python3
"""PreToolUse hook on Bash: block any git command that rewrites or discards history.

Permission rules only match the start of a command, so this hook inspects the whole
string, including `git -C <dir> ...`, chained commands and flags in any position.
Exit 2 blocks the call and shows the message to Claude.
"""
import json
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

command = (data.get("tool_input") or {}).get("command", "")
if not re.search(r"\bgit\b", command):
    sys.exit(0)

GIT = r"\bgit\b(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+"
RULES = [
    (GIT + r"commit\b[^\n;&|]*\s--amend\b", "git commit --amend rewrites history"),
    (GIT + r"push\b[^\n;&|]*\s(--force|-f|--force-with-lease)\b", "force push rewrites history on the remote"),
    (GIT + r"reset\s+(--hard|--merge)\b", "git reset --hard discards work"),
    (GIT + r"rebase\b", "git rebase rewrites history"),
    (GIT + r"branch\b[^\n;&|]*\s-(D|f)\b", "deleting or moving branches with -D or -f"),
    (GIT + r"checkout\s+--\s", "git checkout -- discards uncommitted changes"),
    (GIT + r"restore\b(?![^\n;&|]*--staged)", "git restore discards uncommitted changes"),
    (GIT + r"clean\s+-\w*f", "git clean -f deletes untracked files"),
    (GIT + r"filter-(branch|repo)\b", "history filtering"),
    (GIT + r"update-ref\s+-d\b", "deleting refs"),
    (GIT + r"[^\n;&|]*--no-verify\b", "--no-verify bypasses the commit gate"),
    (GIT + r"stash\s+drop\b", "dropping a stash discards work"),
    (GIT + r"stash\s+clear\b", "clearing stashes discards work"),
]

for pattern, reason in RULES:
    if re.search(pattern, command):
        print(
            f"Blocked by git_guard: {reason}. CLAUDE.md: never rewrite history. "
            "Make a new commit instead, or ask the owner.",
            file=sys.stderr,
        )
        sys.exit(2)

sys.exit(0)

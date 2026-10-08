#!/usr/bin/env python3
"""PreToolUse hook on Bash: block any git command that rewrites or discards history.

Permission rules only match the start of a command, so this hook inspects the whole
string: `git` anywhere in it (`uv run git ...`, `sh -c "git ..."`), any global option between
`git` and its subcommand, chained commands, and flags in any position (D73). Exit 2 blocks
the call and shows the message to Claude.
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

# `git`, then any global options: the ones that take a value as one token (`--git-dir=x`) or
# two (`-C x`, `--work-tree x`), and any other dash-led token (`--no-pager`, `-P`).
VALUED = r"(?:-[Cc]|--git-dir|--work-tree|--namespace|--exec-path|--super-prefix|--config-env)"
GIT = rf"\bgit\b(?:\s+{VALUED}\s+\S+|\s+-\S+)*\s+"
# The rest of one shell command, up to a separator, so a rule never reads past `&&` or `;`.
REST = r"[^\n;&|]*"
# git takes any unambiguous prefix of a long option, so --amend is also --am, --ame and --amen.
AMEND = r"--am(?:e(?:n(?:d)?)?)?\b"
FORCE = r"--force(?:-with-lease|-if-includes)?(?:=\S*)?|-[a-zA-Z]*f[a-zA-Z]*"

RULES = [
    (GIT + rf"commit\b{REST}\s{AMEND}", "git commit --amend rewrites history"),
    (GIT + rf"commit\b{REST}\s-[a-zA-Z]*n\b", "git commit -n skips the commit gate (--no-verify)"),
    (GIT + rf"push\b{REST}\s(?:{FORCE})\b", "force push rewrites history on the remote"),
    (GIT + rf"push\b{REST}\s\+\S", "a + refspec force-pushes that ref"),
    (
        GIT + rf"reset\b{REST}\s--(?:hard|merge|soft|keep|mixed)\b",
        "git reset with a mode moves the branch or discards work",
    ),
    (
        # A reset whose first positional is neither HEAD nor `--` is a reset to another commit.
        GIT + r"reset\b(?:\s+-\S+)*\s+(?!HEAD\b|--(?:\s|$))[^-\s]",
        "git reset to another commit moves the branch; unstage with git reset HEAD -- <path>",
    ),
    (GIT + r"rebase\b", "git rebase rewrites history"),
    (GIT + rf"branch\b{REST}\s(?:-D|-f|--force)\b", "deleting or moving branches with -D or -f"),
    (GIT + r"checkout\s+--\s", "git checkout -- discards uncommitted changes"),
    (GIT + rf"checkout\b{REST}\s(?:-f|--force)\b", "git checkout -f discards uncommitted changes"),
    (
        GIT + rf"switch\b{REST}\s(?:--discard-changes|-f|--force)\b",
        "git switch -f discards uncommitted changes",
    ),
    (GIT + r"restore\b(?![^\n;&|]*--staged)", "git restore discards uncommitted changes"),
    (GIT + r"clean\s+-\w*f", "git clean -f deletes untracked files"),
    (GIT + r"filter-(?:branch|repo)\b", "history filtering"),
    (GIT + r"update-ref\s+-d\b", "deleting refs"),
    (GIT + r"reflog\s+(?:expire|delete)\b", "pruning the reflog removes the way back"),
    (GIT + rf"{REST}--no-verify\b", "--no-verify bypasses the commit gate"),
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

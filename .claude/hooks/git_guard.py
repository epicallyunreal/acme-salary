#!/usr/bin/env python3
"""PreToolUse hook on Bash: block any git command that rewrites or discards history.

Permission rules only match the start of a command, so this hook inspects the whole
string: `git` anywhere in it (`uv run git ...`, `sh -c "git ..."`), any global option between
`git` and its subcommand, chained commands, flags in any position, and the text with its
quotes and escapes removed, so `"git" commit` is read as what the shell runs (D73). Exit 2
blocks the call and shows the message to Claude; so does any error of the hook's own.
"""
import json
import re
import sys

# `git`, then any global options: the ones that take a value as one token (`--git-dir=x`) or
# two (`-C x`, `--work-tree x`), and any other dash-led token (`--no-pager`, `-P`), never a
# bare `--`.
VALUED = r"(?:-[Cc]|--git-dir|--work-tree|--namespace|--exec-path|--super-prefix|--config-env)"
FLAG = r"(?!--(?:\s|$))-\S+"
GIT = rf"\bgit\b(?:\s+{VALUED}\s+\S+|\s+{FLAG})*\s+"
# The rest of one shell command, up to a separator, so a rule never reads past `&&` or `;`.
REST = r"[^\n;&|]*"
# git takes any unambiguous prefix of a long option: --amend is also --am, --ame and --amen,
# and --no-verify is --no-veri and longer.
AMEND = r"--am(?:e(?:n(?:d)?)?)?\b"
NO_VERIFY = r"--no-veri\w*\b"
FORCE = r"--force(?:-with-lease|-if-includes)?(?:=\S*)?|-[a-zA-Z]*f[a-zA-Z]*"

RULES = [
    (GIT + rf"commit\b{REST}\s{AMEND}", "git commit --amend rewrites history"),
    (GIT + rf"commit\b{REST}\s-[a-zA-Z]*n(?=\s|$)", "git commit -n skips the commit gate"),
    (GIT + rf"push\b{REST}\s(?:{FORCE})\b", "force push rewrites history on the remote"),
    (GIT + rf"push\b{REST}\s\+\S", "a + refspec force-pushes that ref"),
    (
        GIT + rf"reset\b{REST}\s--(?:hard|merge|soft|keep|mixed)\b",
        "git reset with a mode moves the branch or discards work",
    ),
    (
        # A reset whose first positional is neither HEAD alone nor `--` is a reset to another
        # commit: HEAD~1, HEAD^, HEAD@{1}, a sha or a branch all move the branch.
        GIT + rf"reset\b(?:\s+{FLAG})*\s+(?!HEAD(?:\s|$)|--(?:\s|$))[^\s-]",
        "git reset to another commit moves the branch; unstage with git reset HEAD -- <path>",
    ),
    (GIT + r"rebase\b", "git rebase rewrites history"),
    (
        GIT + rf"branch\b{REST}\s(?:-[a-zA-Z]*[DMCf][a-zA-Z]*|--force|--move|--copy)\b",
        "deleting, moving or forcing a branch rewrites it",
    ),
    (GIT + rf"checkout\b{REST}\s--\s", "git checkout -- discards uncommitted changes"),
    (GIT + r"checkout\s+\.(?:\s|$)", "git checkout . discards uncommitted changes"),
    (
        GIT + rf"checkout\b{REST}\s(?:-[a-zA-Z]*[fB][a-zA-Z]*|--force)\b",
        "git checkout -f or -B discards work or moves a branch",
    ),
    (
        GIT + rf"switch\b{REST}\s(?:-[a-zA-Z]*[fC][a-zA-Z]*|--force|--force-create|--discard-changes)\b",
        "git switch -f or -C discards work or moves a branch",
    ),
    (GIT + r"restore\b(?![^\n;&|]*--staged)", "git restore discards uncommitted changes"),
    (GIT + rf"clean\b{REST}\s(?:-[a-zA-Z]*f[a-zA-Z]*|--force)\b", "git clean -f deletes untracked files"),
    (GIT + r"filter-(?:branch|repo)\b", "history filtering"),
    (GIT + r"update-ref\b", "writing or deleting refs by hand rewrites history"),
    (GIT + r"reflog\s+(?:expire|delete)\b", "pruning the reflog removes the way back"),
    (GIT + rf"{REST}{NO_VERIFY}", "--no-verify bypasses the commit gate"),
    (GIT + r"stash\s+drop\b", "dropping a stash discards work"),
    (GIT + r"stash\s+clear\b", "clearing stashes discards work"),
]


def readings(command):
    """The command as written, and with backslash escapes and the quotes of single words
    removed, which is what the shell hands git: `"git" commit`, `gi\\t` and `git"" rebase` read
    as one. A quoted phrase with spaces, a commit message, stays as it is."""
    bare = re.sub(r"\\(.)", r"\1", command)
    bare = re.sub(r"""(["'])([^\s"']*)\1""", r"\2", bare)
    return command, bare


def main():
    data = json.load(sys.stdin)
    command = (data.get("tool_input") or {}).get("command", "")
    if not isinstance(command, str):
        return 0
    for text in readings(command):
        if not re.search(r"\bgit\b", text):
            continue
        for pattern, reason in RULES:
            if re.search(pattern, text):
                print(
                    f"Blocked by git_guard: {reason}. CLAUDE.md: never rewrite history. "
                    "Make a new commit instead, or ask the owner.",
                    file=sys.stderr,
                )
                return 2
    return 0


try:
    sys.exit(main())
except SystemExit:
    raise
except Exception as exc:  # the guard itself broke: a blocked call, never a silent pass
    print(f"Blocked: git_guard could not run ({type(exc).__name__}: {exc}).", file=sys.stderr)
    sys.exit(2)

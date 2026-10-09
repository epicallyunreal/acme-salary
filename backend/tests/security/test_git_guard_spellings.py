"""Every spelling git_guard blocks after step 11, and the everyday commands it lets through
(D73). The hook runs as a subprocess, the way Claude Code runs it, on the PreToolUse payload.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "git_guard.py"

pytestmark = pytest.mark.skipif(not HOOK.is_file(), reason="needs the repository's .claude/hooks")

BLOCKED = [
    # resets that move the branch, in every mode and spelling
    "git reset HEAD~1",
    "git reset HEAD^",
    "git reset -q HEAD~2",
    "git reset HEAD@{1}",
    "git reset origin/main",
    "git reset abc1234",
    "git reset --soft HEAD~1",
    "git reset --keep HEAD~1",
    "git reset --mixed HEAD~1",
    "git reset -q --hard HEAD~1",
    "uv run git reset HEAD~1",
    "git --no-pager reset HEAD~1",
    # amend, its abbreviations, and the gate bypasses
    "git commit --amend --no-edit",
    "git commit --amen --no-edit",
    "git commit --am",
    "git --no-pager commit --amend",
    "git commit -n -m x",
    "git commit -an -m x",
    "git commit --no-verify -m x",
    "git commit --no-veri -m x",
    # force pushes
    "git push --force origin main",
    "git push -f origin main",
    "git push -fu origin main",
    "git push --force-with-lease origin main",
    "git push origin +main",
    # rebases and ref surgery
    "git rebase -i HEAD~2",
    "git --no-pager rebase main",
    "git update-ref refs/heads/main HEAD~1",
    "git update-ref -d refs/heads/main",
    "git reflog expire --expire=now --all",
    "git filter-branch --all",
    # branches moved, copied or deleted by force
    "git branch -D old",
    "git branch -M main old",
    "git branch -C main copy",
    "git branch -f main HEAD~1",
    "git branch --force main HEAD~1",
    "git checkout -B main HEAD~1",
    "git switch -C main HEAD~1",
    "git switch --force-create main HEAD~1",
    # discarding work
    "git checkout -- a.py",
    "git checkout HEAD -- a.py",
    "git checkout .",
    "git checkout -f main",
    "git switch -f main",
    "git switch --discard-changes main",
    "git restore a.py",
    "git clean -fd",
    "git clean --force -d",
    "git stash drop",
    "git stash clear",
    # spliced spellings read as what the shell runs
    '"git" commit --amend',
    'git"" rebase main',
    "gi\\t reset --hard HEAD~1",
]

ALLOWED = [
    "git status --short",
    "git log --oneline -5",
    "git diff",
    "git add -A",
    "git commit -m 'tidy -design'",
    'git commit -m "no amendments here"',
    "git reset",
    "git reset -q",
    "git reset HEAD",
    "git reset HEAD -- a.py",
    "git reset -- a.py",
    "git checkout main",
    "git checkout -b feature",
    "git switch -c feature",
    "git switch main",
    "git branch -d merged",
    "git branch --show-current",
    "git push origin main",
    "git push -u origin feature",
    "git restore --staged a.py",
    "git stash",
    "git stash list",
    "git clean -n",
    "git fetch --all",
]
# A git command inside a quoted phrase is blocked too (`sh -c "git reset --hard"` runs it, and
# the hook cannot tell that from an echo), so no such case is in ALLOWED.


def run_guard(command: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, "-I", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("command", BLOCKED)
def test_a_history_rewrite_is_blocked_however_it_is_spelled(command):
    result = run_guard(command)

    assert result.returncode == 2, (command, result.returncode, result.stderr)
    assert "Blocked by git_guard" in result.stderr


@pytest.mark.parametrize("command", ALLOWED)
def test_an_everyday_command_is_let_through(command):
    result = run_guard(command)

    assert (result.returncode, result.stderr) == (0, ""), (command, result.stderr)


def test_a_broken_payload_blocks_the_call_instead_of_passing_it():
    result = subprocess.run(
        [sys.executable, "-I", str(HOOK)],
        input="not json",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 2
    assert "git_guard could not run" in result.stderr

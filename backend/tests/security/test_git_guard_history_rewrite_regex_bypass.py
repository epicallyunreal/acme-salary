"""Lead git_guard_history_rewrite_regex_bypass.

CLAUDE.md says .claude/hooks/git_guard.py blocks any command that rewrites history, whatever
its spelling, but its regexes hard-code one spelling per operation, so shell-valid equivalents
of reset --hard, force push, rebase and commit --amend fall through to exit 0. Each test pipes
the PreToolUse JSON that Claude Code sends into the hook and asserts the hook refuses the call.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FINGERPRINT = "git_guard_history_rewrite_regex_bypass"


def lead(claim):
    """A guard since step 11 (D73): the claim names the spelling the guard once let through."""
    return pytest.mark.parametrize("claim", [claim])


def find_hook():
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".claude" / "hooks" / "git_guard.py"
        if candidate.is_file():
            return candidate
    return None


def run_guard(command):
    """Run the hook the way Claude Code does: PreToolUse JSON on stdin, decision in the exit."""
    hook = find_hook()
    if hook is None:
        pytest.skip(".claude/hooks/git_guard.py is not in this checkout")
    root = hook.parents[2]
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": FINGERPRINT},
    }
    result = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=root,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
        timeout=60,
    )
    if result.returncode not in (0, 2):
        pytest.fail(f"git_guard crashed with exit {result.returncode}: {result.stderr[-500:]}")
    return result


def blocked(result):
    """Claude Code refuses the call on exit 2, or on exit 0 with a deny or block decision."""
    if result.returncode == 2:
        return True
    try:
        output = json.loads(result.stdout or "{}")
    except ValueError:
        return False
    if not isinstance(output, dict):
        return False
    specific = output.get("hookSpecificOutput") or {}
    return specific.get("permissionDecision") == "deny" or output.get("decision") == "block"


def assert_blocked(command):
    result = run_guard(command)
    assert blocked(result), f"git_guard let {command!r} through (exit {result.returncode})"


@pytest.mark.parametrize(
    "command",
    [
        "git reset --hard HEAD~1",
        "git push --force origin main",
        "git rebase -i HEAD~2",
        "git commit --amend --no-edit",
    ],
)
def test_canonical_spellings_are_blocked(command):
    assert_blocked(command)


@lead("git reset -q --hard is not blocked, as the reset rule wants --hard right after reset")
def test_reset_hard_after_another_flag_is_blocked(claim):
    assert_blocked("git reset -q --hard HEAD~1")


@lead("git push origin +main is not blocked, as a + refspec is not a listed force spelling")
def test_force_refspec_push_is_blocked(claim):
    assert_blocked("git push origin +main")


@lead("git --no-pager rebase is not blocked, as the git prefix admits only -C and -c")
def test_rebase_after_global_option_is_blocked(claim):
    assert_blocked("git --no-pager rebase -i HEAD~2")


@lead("git --no-pager commit --amend is not blocked, as the git prefix admits only -C and -c")
def test_amend_after_global_option_is_blocked(claim):
    assert_blocked("git --no-pager commit --amend --no-edit")


@lead("git commit --amen is not blocked, though git reads the abbreviation as --amend")
def test_abbreviated_amend_is_blocked(claim):
    assert_blocked("git commit --amen --no-edit")

"""Lead pre_commit_gate_commit_detection_bypass, a guard since step 11 (D73): the gate
reads a commit behind any git global option.

Claim: .claude/hooks/pre_commit_gate.py treats a Bash command as a commit only when nothing
but `-C <dir>` or `-c <key=value>` stands between `git` and `commit`, so a commit spelled
with any other git global option (`git --no-pager commit -m x`) exits 0 before ruff, pytest,
eslint or vitest run.

The hook runs in a throwaway project that holds only an empty backend/pyproject.toml, with
PATH set to an empty directory. A detected commit therefore reaches the checks, finds neither
ruff nor pytest and blocks with exit 2 without starting any tool, so the project's own
linters and tests never run from this file.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "pre_commit_gate.py"
BLOCKED = 2

# Spellings git runs as a commit that the detection regex does not recognise. The last one
# is wrapped in `uv run`, which the project's `Bash(uv run *)` allow rule matches by prefix.
UNRECOGNISED_COMMITS = [
    "git --no-pager commit -m x",
    "git -P commit -m x",
    "git --work-tree=. commit -m x",
    "uv run git --no-pager commit -m x",
]

pytestmark = pytest.mark.skipif(not HOOK.is_file(), reason="needs the repository's .claude/hooks")


def run_gate(tmp_path, command):
    """Feed one Bash tool call to the gate inside an empty sandbox project."""
    project = tmp_path / "project"
    (project / "backend").mkdir(parents=True)
    (project / "backend" / "pyproject.toml").write_text("", encoding="utf-8")
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = {"PATH": str(empty_bin), "CLAUDE_PROJECT_DIR": str(project)}
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, "-I", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=project,
        env=env,
        timeout=60,
        check=False,
    )


def test_gate_blocks_the_plain_spelling_without_running_tools(tmp_path):
    """Control: in the sandbox a recognised commit is blocked and no tool is available."""
    result = run_gate(tmp_path, "git commit -m x")

    assert result.returncode == BLOCKED
    assert "tool not found" in result.stderr


@pytest.mark.parametrize("command", UNRECOGNISED_COMMITS)
def test_gate_blocks_commits_spelled_with_other_global_options(tmp_path, command):
    result = run_gate(tmp_path, command)

    assert result.returncode == BLOCKED, (command, result.returncode, result.stderr)
    assert "tool not found" in result.stderr

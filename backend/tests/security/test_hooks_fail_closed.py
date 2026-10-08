"""The hooks after step 11 (D73): the commit gate fails closed, the session hook reads the owner's
decision from one line and picks the latest review by name, and post_edit hands a path as a
path. Each hook runs as a subprocess, the way Claude Code runs it, inside a throwaway project.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[3] / ".claude" / "hooks"
GATE = HOOKS / "pre_commit_gate.py"
SESSION = HOOKS / "session_start.py"
POST_EDIT = HOOKS / "post_edit.py"
COMMIT = "git " + "commit -m x"  # split so the project's own gate does not read this file as one

pytestmark = pytest.mark.skipif(not GATE.is_file(), reason="needs the repository's .claude/hooks")


def script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def sandbox(tmp_path: Path, *, pytest_exit=0, tsc_exit=0, ruff_runnable=True) -> tuple[Path, dict]:
    """A project with fake tools: ruff and pytest in backend/.venv/bin, tsc in
    frontend/node_modules/.bin, npm on the PATH, each exiting as asked."""
    project = tmp_path / "project"
    (project / "backend").mkdir(parents=True)
    (project / "backend" / "pyproject.toml").write_text("", encoding="utf-8")
    venv = project / "backend" / ".venv" / "bin"
    if ruff_runnable:
        script(venv / "ruff", "exit 0")
    else:
        (venv).mkdir(parents=True)
        (venv / "ruff").write_text("not a program", encoding="utf-8")  # present, not executable
    script(venv / "pytest", f"echo 'collected 0 items'; exit {pytest_exit}")
    (project / "frontend").mkdir()
    (project / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (project / "frontend" / "node_modules").mkdir()
    script(
        project / "frontend" / "node_modules" / ".bin" / "tsc",
        f"echo 'tsc: TS2322'; exit {tsc_exit}",
    )
    bin_dir = tmp_path / "bin"
    script(bin_dir / "npm", "exit 0")
    env = {"PATH": str(bin_dir), "CLAUDE_PROJECT_DIR": str(project)}
    return project, env


def run_gate(project: Path, env: dict, command: str = COMMIT) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, "-I", str(GATE)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=project,
        env=env,
        timeout=60,
        check=False,
    )


def test_the_gate_passes_a_commit_when_every_tool_is_green(tmp_path):
    project, env = sandbox(tmp_path)

    result = run_gate(project, env)

    assert (result.returncode, result.stderr) == (0, "")


def test_the_gate_ignores_a_command_that_is_not_a_commit(tmp_path):
    project, env = sandbox(tmp_path, pytest_exit=1)

    result = run_gate(project, env, "git status --short")

    assert (result.returncode, result.stderr) == (0, "")


def test_a_test_run_that_collects_nothing_blocks_the_commit(tmp_path):
    """pytest's exit 5: a suite that vanished must not pass."""
    project, env = sandbox(tmp_path, pytest_exit=5)

    result = run_gate(project, env)

    assert result.returncode == 2
    assert "pytest failed (exit 5) (no tests were collected)" in result.stderr


def test_a_tool_that_cannot_run_blocks_the_commit(tmp_path):
    """A venv binary that is not a program raises in subprocess; the gate reports it, exit 2."""
    project, env = sandbox(tmp_path, ruff_runnable=False)

    result = run_gate(project, env)

    assert result.returncode == 2
    assert "ruff format --check could not run (" in result.stderr


def test_the_type_check_runs_and_a_failure_blocks_the_commit(tmp_path):
    project, env = sandbox(tmp_path, tsc_exit=1)

    result = run_gate(project, env)

    assert result.returncode == 2
    assert "tsc -b failed (exit 1)" in result.stderr
    assert "tsc: TS2322" in result.stderr


def test_a_broken_payload_blocks_the_commit_instead_of_passing_it(tmp_path):
    """Any exception in the hook itself is a blocked call, never a silent exit 0."""
    project, env = sandbox(tmp_path)

    result = subprocess.run(
        [sys.executable, "-I", str(GATE)],
        input="not json",
        capture_output=True,
        text=True,
        cwd=project,
        env=env,
        timeout=60,
        check=False,
    )

    assert result.returncode == 2
    assert "the pre-commit gate could not run" in result.stderr


def review(decision: str) -> str:
    return f"# Spec review\n\nOwner decision: {decision}\n\n## Verdict\n\nApprove.\n"


def session_lines(tmp_path: Path, files: dict) -> str:
    project = tmp_path / "project"
    for name, text in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "CLAUDE_PROJECT_DIR": str(project),
        "GIT_CEILING_DIRECTORIES": str(tmp_path),
    }
    result = subprocess.run(
        [sys.executable, str(SESSION)], cwd=project, env=env, capture_output=True, text=True
    )
    result.check_returncode()
    return result.stdout


def test_the_latest_review_is_the_latest_by_name_whatever_was_touched_last(tmp_path):
    files = {
        "docs/reviews/spec-review-2026-10-06.md": review("rework"),
        "docs/reviews/spec-review-2026-10-07.md": review("approved"),
        "docs/PLAN.md": "Owner decision: approved\n",
        "docs/DESIGN.md": "Owner decision: approved\n",
    }
    out = session_lines(tmp_path, files)
    # The older review, touched after the newer one, is still not the latest.
    older = tmp_path / "project" / "docs/reviews/spec-review-2026-10-06.md"
    older.touch()
    out = session_lines(tmp_path, {})

    assert "Spec review gate: approved (spec-review-2026-10-07.md, latest by name)." in out


def test_the_decision_is_read_from_the_start_of_its_line_only(tmp_path):
    files = {
        "docs/reviews/spec-review-2026-10-07.md": review("pending, Owner decision: approved later"),
        "docs/PLAN.md": "Owner decision: pending. Earlier steps keep Owner decision: approved.\n",
        "docs/DESIGN.md": "Owner decision: approved\n",
    }

    out = session_lines(tmp_path, files)

    assert "Spec review gate: pending owner decision" in out
    assert "PLAN.md pending owner decision, DESIGN.md approved" in out


def test_post_edit_hands_a_dash_led_path_as_a_path(tmp_path):
    """`--` before the path, so a file named `-x.py` is formatted, not read as a flag."""
    project = tmp_path / "project"
    log = tmp_path / "ruff-argv.txt"
    script(project / "backend" / ".venv" / "bin" / "ruff", f'echo "$@" >> "{log}"')
    edited = project / "backend" / "-x.py"
    edited.write_text("x = 1\n", encoding="utf-8")
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(edited)}})

    result = subprocess.run(
        [sys.executable, str(POST_EDIT)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=project,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "CLAUDE_PROJECT_DIR": str(project)},
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert calls == [f"format -- {edited}", f"check --fix -- {edited}"]

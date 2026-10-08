#!/usr/bin/env python3
"""Lint, type check and tests must pass before any `git commit`.

Runs as a Claude Code PreToolUse hook on Bash (stdin carries the tool input) and as
a pre-commit framework hook (set ACME_GATE_FORCE=1, no stdin). Exit 2 blocks the
Claude Code tool call; any non-zero exit blocks a terminal commit.

Fails closed (D73): a part of the repo whose tools are missing, a tool that cannot be run, a
test run that collected nothing, a commit spelled behind any git global option, and any
exception in this hook itself all block the commit with exit 2. Checks are skipped only for
parts of the repo that do not exist yet.
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
FORCE = os.environ.get("ACME_GATE_FORCE") == "1"

# `git`, then any global options, then `commit`: the prefix git_guard.py uses, so a commit
# spelled `git --no-pager commit`, `git -P commit` or `uv run git commit` is one too.
VALUED = r"(?:-[Cc]|--git-dir|--work-tree|--namespace|--exec-path|--super-prefix|--config-env)"
COMMIT = rf"\bgit\b(?:\s+{VALUED}\s+\S+|\s+-\S+)*\s+commit\b"


def tool(name, subdir):
    for candidate in (
        os.path.join(ROOT, subdir, ".venv", "bin", name),
        os.path.join(ROOT, subdir, ".venv", "Scripts", name + ".exe"),
        os.path.join(ROOT, subdir, "node_modules", ".bin", name),
    ):
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(name)


def main():
    if not FORCE:
        data = json.load(sys.stdin)
        command = (data.get("tool_input") or {}).get("command", "")
        if not re.search(COMMIT, command):
            return 0

    failures = []

    def check(label, cmd, cwd, timeout=300):
        if cmd[0] is None:
            failures.append(
                f"{label}: tool not found. Create backend/.venv with `uv venv && uv sync` "
                "or run `npm ci` in frontend/."
            )
            return
        try:
            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            failures.append(f"{label}: timed out after {timeout}s")
            return
        except Exception as exc:  # a tool that is not executable, or not a program at all
            failures.append(f"{label} could not run ({type(exc).__name__}: {exc})")
            return
        if result.returncode != 0:
            tail = (result.stdout + "\n" + result.stderr).strip().splitlines()[-30:]
            note = " (no tests were collected)" if label == "pytest" and result.returncode == 5 else ""
            failures.append(f"{label} failed (exit {result.returncode}){note}:\n" + "\n".join(tail))

    backend = os.path.join(ROOT, "backend")
    if os.path.isfile(os.path.join(backend, "pyproject.toml")):
        ruff = tool("ruff", "backend")
        check("ruff format --check", [ruff, "format", "--check", "."], backend, timeout=60)
        check("ruff check", [ruff, "check", "."], backend, timeout=60)
        # Exit 5, nothing collected, is a failure: a suite that vanished must not pass.
        check("pytest", [tool("pytest", "backend"), "-q", "-x", "-m", "not slow"], backend)

    frontend = os.path.join(ROOT, "frontend")
    if os.path.isfile(os.path.join(frontend, "package.json")):
        if not os.path.isdir(os.path.join(frontend, "node_modules")):
            failures.append(
                "frontend: node_modules missing. Run `npm ci` in frontend/ so lint and tests can run."
            )
        else:
            npm = shutil.which("npm")
            check("npm run lint", [npm, "run", "--silent", "lint"], frontend, timeout=120)
            # The one type check: eslint and vitest run without it.
            check("tsc -b", [tool("tsc", "frontend"), "-b"], frontend, timeout=180)
            check("npm test", [npm, "test", "--silent", "--", "--run"], frontend)

    if failures:
        print(
            "Commit blocked by the pre-commit gate. Fix the failures and commit again. "
            "Do not bypass the gate.\n\n" + "\n\n".join(failures),
            file=sys.stderr,
        )
        return 2
    return 0


try:
    sys.exit(main())
except SystemExit:
    raise
except Exception as exc:  # the gate itself broke: a blocked commit, never a silent pass
    print(
        f"Commit blocked: the pre-commit gate could not run ({type(exc).__name__}: {exc}). "
        "Fix the hook or its tools; do not bypass it.",
        file=sys.stderr,
    )
    sys.exit(2)

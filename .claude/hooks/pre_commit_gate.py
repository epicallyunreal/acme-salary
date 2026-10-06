#!/usr/bin/env python3
"""Lint and tests must pass before any `git commit`.

Runs as a Claude Code PreToolUse hook on Bash (stdin carries the tool input) and as
a pre-commit framework hook (set ACME_GATE_FORCE=1, no stdin). Exit 2 blocks the
Claude Code tool call; any non-zero exit blocks a terminal commit.

Fails closed: if a part of the repo exists but its tools are missing, the commit is
blocked with a message saying what to install. Checks are skipped only for parts of
the repo that do not exist yet.
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
FORCE = os.environ.get("ACME_GATE_FORCE") == "1"

if not FORCE:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    command = (data.get("tool_input") or {}).get("command", "")
    if not re.search(r"\bgit\b(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+commit\b", command):
        sys.exit(0)

failures = []


def tool(name, subdir):
    for candidate in (
        os.path.join(ROOT, subdir, ".venv", "bin", name),
        os.path.join(ROOT, subdir, ".venv", "Scripts", name + ".exe"),
        os.path.join(ROOT, subdir, "node_modules", ".bin", name),
    ):
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(name)


def check(label, cmd, cwd, ok_codes=(0,), timeout=300):
    if cmd[0] is None:
        failures.append(f"{label}: tool not found. Create backend/.venv with `uv venv && uv sync` or run `npm ci` in frontend/.")
        return
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        failures.append(f"{label}: timed out after {timeout}s")
        return
    if result.returncode not in ok_codes:
        tail = (result.stdout + "\n" + result.stderr).strip().splitlines()[-30:]
        failures.append(f"{label} failed (exit {result.returncode}):\n" + "\n".join(tail))


backend = os.path.join(ROOT, "backend")
if os.path.isfile(os.path.join(backend, "pyproject.toml")):
    ruff = tool("ruff", "backend")
    check("ruff format --check", [ruff, "format", "--check", "."], backend, timeout=60)
    check("ruff check", [ruff, "check", "."], backend, timeout=60)
    pytest = tool("pytest", "backend")
    # exit 5 = no tests collected, acceptable before the first test exists
    check("pytest", [pytest, "-q", "-x", "-m", "not slow"], backend, ok_codes=(0, 5), timeout=300)

frontend = os.path.join(ROOT, "frontend")
if os.path.isfile(os.path.join(frontend, "package.json")):
    if not os.path.isdir(os.path.join(frontend, "node_modules")):
        failures.append("frontend: node_modules missing. Run `npm ci` in frontend/ so lint and tests can run.")
    else:
        npm = shutil.which("npm")
        check("npm run lint", [npm, "run", "--silent", "lint"], frontend, timeout=120)
        check("npm test", [npm, "test", "--silent", "--", "--run"], frontend, timeout=300)

if failures:
    print(
        "Commit blocked by the pre-commit gate. Fix the failures and commit again. "
        "Do not bypass the gate.\n\n" + "\n\n".join(failures),
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)

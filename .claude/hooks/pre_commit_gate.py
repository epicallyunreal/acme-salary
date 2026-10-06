#!/usr/bin/env python3
"""PreToolUse hook on `git commit`: lint and tests must pass or the commit is blocked.

Exit 2 blocks the tool call and shows stderr to Claude. Checks are skipped for parts
of the repo that do not exist yet, so docs-only commits in step 1 pass.
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

command = (data.get("tool_input") or {}).get("command", "")
if "git commit" not in command:
    sys.exit(0)

failures = []


def tool(name, subdir):
    for candidate in (
        os.path.join(ROOT, subdir, ".venv", "bin", name),
        os.path.join(ROOT, subdir, "node_modules", ".bin", name),
    ):
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(name)


def check(label, cmd, cwd, ok_codes=(0,)):
    if cmd[0] is None:
        failures.append(f"{label}: tool not found (install dev deps or activate the venv)")
        return
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=540)
    except subprocess.TimeoutExpired:
        failures.append(f"{label}: timed out")
        return
    if result.returncode not in ok_codes:
        tail = (result.stdout + "\n" + result.stderr).strip().splitlines()[-30:]
        failures.append(f"{label} failed (exit {result.returncode}):\n" + "\n".join(tail))


backend = os.path.join(ROOT, "backend")
if os.path.isfile(os.path.join(backend, "pyproject.toml")):
    ruff = tool("ruff", "backend")
    check("ruff format --check", [ruff, "format", "--check", "."], backend)
    check("ruff check", [ruff, "check", "."], backend)
    pytest = tool("pytest", "backend")
    # exit 5 = no tests collected, acceptable before the first test exists
    check("pytest", [pytest, "-q", "-x", "-m", "not slow"], backend, ok_codes=(0, 5))

frontend = os.path.join(ROOT, "frontend")
if os.path.isfile(os.path.join(frontend, "package.json")) and os.path.isdir(
    os.path.join(frontend, "node_modules")
):
    npm = shutil.which("npm")
    check("npm run lint", [npm, "run", "--silent", "lint"], frontend)
    check("npm test", [npm, "test", "--silent", "--", "--run"], frontend)

if failures:
    print(
        "Commit blocked by the pre-commit gate. Fix the failures and commit again. "
        "Do not bypass the gate.\n\n" + "\n\n".join(failures),
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)

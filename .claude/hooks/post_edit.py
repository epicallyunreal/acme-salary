#!/usr/bin/env python3
"""PostToolUse hook for Edit|Write: format the file, then check a few project rules.

Exit 2 cannot undo the edit, but its stderr is shown to Claude so the rule gets fixed
in the next action.
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

path = (data.get("tool_input") or {}).get("file_path") or ""
if not path or not os.path.isfile(path):
    sys.exit(0)

rel = os.path.relpath(path, ROOT).replace("\\", "/")
problems = []


def tool(name, subdir):
    """Prefer a tool inside the project's own venv or node_modules, then PATH."""
    for candidate in (
        os.path.join(ROOT, subdir, ".venv", "bin", name),
        os.path.join(ROOT, subdir, "node_modules", ".bin", name),
    ):
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(name)


def run(cmd, cwd):
    try:
        subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=50)
    except Exception:
        pass


def read():
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


if rel.startswith("backend/") and rel.endswith(".py"):
    backend = os.path.join(ROOT, "backend")
    ruff = tool("ruff", "backend")
    if ruff:
        run([ruff, "format", path], backend)
        run([ruff, "check", "--fix", path], backend)
    text = read()
    if "FloatField" in text:
        problems.append(
            "FloatField found. Rule 2: money is DecimalField(14, 2) and FX rates are "
            "DecimalField(18, 8)."
        )
    if rel.endswith(("/views.py", "/serializers.py")):
        if (
            "transaction.atomic" in text
            or "bulk_create" in text
            or re.search(r"\bDecimal\(", text)
        ):
            problems.append(
                "Business logic in a view or serializer. Rule 1: move it to "
                "services.py or queries.py and call it from the view."
            )
    if "/tests/" in "/" + rel or rel.endswith("conftest.py"):
        if re.search(r"(datetime|timezone)\.now\(|date\.today\(", text) and (
            "freeze_time" not in text and "freezegun" not in text
        ):
            problems.append(
                "Test reads the clock without freezegun. Tests are deterministic: "
                "use @freeze_time or a fixed date."
            )
        if re.search(r"\brandom\.", text) and "seed" not in text.lower():
            problems.append(
                "Test uses random without a fixed seed. Use random.Random(42) or a literal."
            )
        if "seed_data" in text and "--employees" not in text and "employees=" not in text:
            problems.append(
                "Test calls seed_data without a small --employees count. Tests never "
                "build the 10k seed."
            )

elif rel.startswith("frontend/") and rel.endswith((".ts", ".tsx")):
    frontend = os.path.join(ROOT, "frontend")
    prettier = tool("prettier", "frontend")
    eslint = tool("eslint", "frontend")
    if prettier:
        run([prettier, "--write", path], frontend)
    if eslint:
        run([eslint, "--fix", path], frontend)
    text = read()
    if re.search(r":\s*any\b", text):
        problems.append("`any` found. Type it, or use `unknown` and narrow.")
    if "/components/" in rel and re.search(r"\bfetch\(", text):
        problems.append(
            "fetch() inside a component. Server state goes through TanStack Query "
            "hooks in src/api."
        )

if problems:
    print("Post-edit check on " + rel + ":\n- " + "\n- ".join(problems), file=sys.stderr)
    sys.exit(2)
sys.exit(0)

#!/usr/bin/env python3
"""PostToolUse hook for Edit|Write: format the file, then check a few project rules.

Exit 2 cannot undo the edit, but its stderr is shown to Claude so the rule gets fixed
in the next action. Comment lines are ignored by the rule checks.
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

path = (data.get("tool_input") or {}).get("file_path") or ""
if not path or not os.path.isfile(path):
    sys.exit(0)

rel = os.path.relpath(path, ROOT).replace("\\", "/")
problems = []

API_MODULES = ("views.py", "api.py", "viewsets.py", "serializers.py")


def tool(name, subdir):
    for candidate in (
        os.path.join(ROOT, subdir, ".venv", "bin", name),
        os.path.join(ROOT, subdir, ".venv", "Scripts", name + ".exe"),
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


def code_lines(text, comment_prefix):
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(comment_prefix):
            continue
        out.append(line.split(comment_prefix, 1)[0] if comment_prefix == "#" else line)
    return "\n".join(out)


if rel.startswith("backend/") and rel.endswith(".py"):
    backend = os.path.join(ROOT, "backend")
    ruff = tool("ruff", "backend")
    if ruff:
        # `--` before the path: a file whose name starts with a dash is a path, not a flag (D73).
        run([ruff, "format", "--", path], backend)
        run([ruff, "check", "--fix", "--", path], backend)
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = code_lines(fh.read(), "#")
    is_test = "/tests/" in "/" + rel or rel.endswith("conftest.py")
    is_migration = "/migrations/" in "/" + rel
    if "FloatField" in text and not is_migration:
        problems.append("FloatField found. Rule 2: money is DecimalField(14, 2) and FX rates are DecimalField(18, 8).")
    # Tests are not API modules, though test_api.py ends like one.
    if rel.endswith(API_MODULES) and not is_test:
        if "transaction.atomic" in text or "bulk_create" in text or re.search(r"\bDecimal\(", text):
            problems.append(
                f"Business logic in {os.path.basename(rel)}. Rule 1: move it to services.py or queries.py and call it from the view."
            )
    if is_test:
        if re.search(r"(datetime|timezone)\.now\(|date\.today\(", text) and "freeze_time" not in text and "freezegun" not in text:
            problems.append("Test reads the clock without freezegun. Tests are deterministic: use @freeze_time or a fixed date.")
        if re.search(r"\brandom\.", text) and "seed" not in text.lower() and "Random(" not in text:
            problems.append("Test uses random without a fixed seed. Use random.Random(42) or a literal.")
        if "seed_data" in text and "--employees" not in text and "employees=" not in text:
            problems.append("Test calls seed_data without a small --employees count. Tests never build the 10k seed.")

elif rel.startswith("frontend/") and rel.endswith((".ts", ".tsx")):
    frontend = os.path.join(ROOT, "frontend")
    prettier = tool("prettier", "frontend")
    eslint = tool("eslint", "frontend")
    if prettier:
        run([prettier, "--write", "--", path], frontend)
    if eslint:
        run([eslint, "--fix", "--", path], frontend)
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = code_lines(fh.read(), "//")
    if re.search(r":\s*any\b", text):
        problems.append("`any` found. Type it, or use `unknown` and narrow.")
    if "/components/" in rel and re.search(r"\bfetch\(", text):
        problems.append("fetch() inside a component. Server state goes through TanStack Query hooks in src/api.")

if problems:
    print("Post-edit check on " + rel + ":\n- " + "\n- ".join(problems), file=sys.stderr)
    sys.exit(2)
sys.exit(0)

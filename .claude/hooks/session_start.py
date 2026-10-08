#!/usr/bin/env python3
"""SessionStart hook: put repo state, gate status and the skill list into context,
and export the backend virtualenv onto PATH for the rest of the session.
"""
import os
import pathlib
import subprocess

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def run(cmd):
    try:
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


# Put backend/.venv/bin on PATH for every later Bash call in this session.
venv_bin = pathlib.Path(ROOT, "backend", ".venv", "bin")
env_file = os.environ.get("CLAUDE_ENV_FILE")
venv_note = "backend/.venv not created yet (step 1 creates it with `uv venv && uv sync`)."
if venv_bin.is_dir():
    venv_note = f"backend/.venv is on PATH for this session ({venv_bin})."
    if env_file:
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.write(f'export PATH="{venv_bin}:$PATH"\nexport VIRTUAL_ENV="{venv_bin.parent}"\n')

branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "(no git yet)"
log = run(["git", "log", "--oneline", "-10"]) or "(no commits yet)"
status = run(["git", "status", "--short"]) or "(clean)"

skills = []
for skill in sorted(pathlib.Path(ROOT, ".claude", "skills").glob("*/SKILL.md")):
    desc = ""
    for line in skill.read_text(encoding="utf-8").splitlines()[:12]:
        if line.startswith("description:"):
            desc = line.split(":", 1)[1].strip()
            break
    skills.append(f"- /{skill.parent.name}: {desc}")

agents = sorted(p.stem for p in pathlib.Path(ROOT, ".claude", "agents").glob("*.md"))


def decision_of(path, line_number):
    """The owner's decision is the one line that starts with it: line 3 of a review, line 1 of
    PLAN and DESIGN. The phrase anywhere else, a reviewer quoting it, opens no gate (D73)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    line = lines[line_number - 1].strip().lower() if len(lines) >= line_number else ""
    if line.startswith("owner decision: approved"):
        return "approved"
    if line.startswith("owner decision: rework"):
        return "rework requested"
    return "pending owner decision"


# The latest review is the latest by name, which carries its date: a touched older file or a
# copy with a newer modification time changes nothing (D73).
reviews = sorted(pathlib.Path(ROOT, "docs", "reviews").glob("spec-review-*.md"))
if not reviews:
    gate = "no spec review yet. The only task before development is /review-spec."
else:
    latest = reviews[-1]
    gate = f"{decision_of(latest, 3)} ({latest.name}, latest by name)."


def doc_state(name):
    path = pathlib.Path(ROOT, "docs", name)
    return decision_of(path, 1) if path.exists() else "missing"


plan_state = f"PLAN.md {doc_state('PLAN.md')}, DESIGN.md {doc_state('DESIGN.md')}"

print(
    f"""Repo context from the SessionStart hook.
Branch: {branch}
Recent commits:
{log}
Uncommitted changes:
{status}
Environment: {venv_note}

Read docs/SPEC.md (v2). Build order is the approved docs/PLAN.md. The next step is the first one not covered by the commits above. Before any task, check the project skills below for a match and say which one applies.

Spec review gate: {gate}
Plan and design gate: {plan_state}. Order is /review-spec, approve, /plan-and-design, approve, then /start-step 1.
Reviewer subagents: {', '.join(agents) or '(none found)'}. /finish-step runs the four build reviewers before a step is committed.
Hooks active: git_guard (history rewrites blocked), pre_commit_gate (lint and tests before every commit), post_edit (format and rule checks), dependency_note (rule 9 on installs).

Project skills:
{chr(10).join(skills) or '- (none found)'}"""
)

#!/usr/bin/env python3
"""SessionStart hook: give Claude the repo state and the list of project skills.

Plain stdout from a SessionStart hook is added to Claude's context.
"""
import os
import pathlib
import subprocess

ROOT = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def run(cmd):
    try:
        return subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return ""


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

reviews = sorted(pathlib.Path(ROOT, "docs", "reviews").glob("spec-review-*.md"))
if not reviews:
    gate = "no spec review yet. The only task before development is /review-spec."
else:
    latest = reviews[-1]
    head = latest.read_text(encoding="utf-8")[:400].lower()
    if "owner decision: approved" in head:
        gate = f"approved ({latest.name})."
    elif "owner decision: rework" in head:
        gate = f"rework requested ({latest.name}). Make the owner's changes, then run /review-spec again."
    else:
        gate = f"pending owner decision ({latest.name}). Development waits."


def doc_state(name):
    path = pathlib.Path(ROOT, "docs", name)
    if not path.exists():
        return "missing"
    head = path.read_text(encoding="utf-8")[:200].lower()
    if "owner decision: approved" in head:
        return "approved"
    if "owner decision: rework" in head:
        return "rework requested"
    return "pending owner decision"

plan_state = f"PLAN.md {doc_state('PLAN.md')}, DESIGN.md {doc_state('DESIGN.md')}"

print(
    f"""Repo context from the SessionStart hook.
Branch: {branch}
Recent commits:
{log}
Uncommitted changes:
{status}

Build order is the approved docs/PLAN.md, derived from SPEC section 15. The next step is the first one not covered by the commits above. Before any task, check the project skills below for a match and say which one applies.

Project skills:
{chr(10).join(skills) or '- (none found)'}

Spec review gate: {gate}
Plan and design gate: {plan_state}. Order is /review-spec, approve, /plan-and-design, approve, then /start-step 1.
Reviewer subagents: {', '.join(agents) or '(none found)'}. /finish-step runs them before a step is committed.
Hooks active: post-edit formatting and rule checks, lint and tests before every git commit."""
)

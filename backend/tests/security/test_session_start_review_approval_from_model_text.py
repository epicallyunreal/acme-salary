"""Guard since step 11 (D73): the hook reads the decision from line 3 of a review and line 1
of PLAN and DESIGN, and nowhere else.

Lead session_start_review_approval_from_model_text.

.claude/hooks/session_start.py tells every new session whether the owner approved the latest
spec review, docs/PLAN.md and docs/DESIGN.md. decision_of() lowercases the first 600 characters
of the review (200 of PLAN.md and DESIGN.md) and reports approved when "owner decision: approved"
appears anywhere in them, before it looks for rework. Everything in a review after its line 3 is
the reviewer agent's own text, saved verbatim by /review-spec, so a verdict that quotes the gate's
wording reports the gate open while the owner's decision line still says pending or rework.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / ".claude" / "hooks" / "session_start.py"
REVIEW = "docs/reviews/spec-review-2026-10-08.md"
SPEC_GATE = "Spec review gate:"
PLAN_GATE = "Plan and design gate:"

QUOTING_VERDICT = (
    "Rework before development. Two blockers stand, and `/start-step 1` must wait until "
    "line 3 reads `Owner decision: approved`."
)
PLAIN_VERDICT = "Approve. Nothing blocks development."
PLAN_PENDING = (
    "Owner decision: pending for step 10. Steps 1 to 9 keep their Owner decision: approved "
    "of 7 and 8 October.\n\n# Plan\n"
)
needs_hook = pytest.mark.skipif(not HOOK.is_file(), reason="needs the .claude/hooks directory")


def review(decision, verdict):
    return (
        "# Spec review, 2026-10-08\n\n"
        f"Owner decision: {decision}\n\n"
        "## Verdict\n\n"
        f"{verdict}\n\n"
        "## Blocking issues\n\n"
        "**B1.** A placeholder blocker for this fixture.\n"
    )


def gate_lines(tmp_path, files):
    """Run the hook against a throwaway project holding `files`; return its two gate lines."""
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
        [sys.executable, str(HOOK)],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    result.check_returncode()
    lines = {}
    for line in result.stdout.splitlines():
        for prefix in (SPEC_GATE, PLAN_GATE):
            if line.startswith(prefix):
                lines[prefix] = line
    if len(lines) != 2:
        pytest.fail(f"hook output changed shape: {result.stdout[:400]}")
    return lines


@needs_hook
def test_control_an_approved_decision_line_opens_the_gate(tmp_path):
    files = {
        REVIEW: review("approved, resolved in SPEC v2.17", PLAIN_VERDICT),
        "docs/PLAN.md": "Owner decision: approved\n\n# Plan\n",
        "docs/DESIGN.md": "Owner decision: approved\n\n# Design\n",
    }
    lines = gate_lines(tmp_path, files)
    assert lines[SPEC_GATE].startswith("Spec review gate: approved"), lines
    assert "PLAN.md approved, DESIGN.md approved" in lines[PLAN_GATE], lines


LATER_LINE_VERDICT = "Approve.\n\nOwner decision: approved, says a later line, which is not line 3."

# case: (files under the throwaway project, gate line to read, what that line must start with)
CASES = {
    "review_pending": (
        {REVIEW: review("pending", QUOTING_VERDICT)},
        SPEC_GATE,
        "Spec review gate: pending owner decision",
    ),
    "review_rework": (
        {REVIEW: review("rework", QUOTING_VERDICT)},
        SPEC_GATE,
        "Spec review gate: rework requested",
    ),
    "review_approved_on_a_later_line": (
        {REVIEW: review("pending", LATER_LINE_VERDICT)},
        SPEC_GATE,
        "Spec review gate: pending owner decision",
    ),
    "plan_pending": (
        {
            REVIEW: review("approved", PLAIN_VERDICT),
            "docs/PLAN.md": PLAN_PENDING,
            "docs/DESIGN.md": "Owner decision: pending\n\n# Design\n",
        },
        PLAN_GATE,
        "Plan and design gate: PLAN.md pending owner decision, DESIGN.md pending owner decision",
    ),
}


@needs_hook
@pytest.mark.parametrize("case", sorted(CASES))
def test_only_the_owner_decision_line_opens_the_gate(tmp_path, case):
    files, prefix, expected = CASES[case]
    line = gate_lines(tmp_path, files)[prefix]
    assert line.startswith(expected), f"{case}: hook says {line!r}"

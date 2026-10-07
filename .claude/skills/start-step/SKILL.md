---
name: start-step
description: Begin a numbered build step from the approved docs/PLAN.md. Use at the start of every step, or when the user says "start step N", "next step", or names a step such as "begin the import pipeline".
argument-hint: <step number>
---

# Start a build step

Step: `$ARGUMENTS`. If no number was given, run `git log --oneline` and pick the first step in `docs/PLAN.md` whose work is not in the log.

0. Gate. Three things must exist before step 1: the latest report in `docs/reviews/` carrying an `Owner decision:` line that begins `approved`, and `docs/PLAN.md` and `docs/DESIGN.md` each carrying `Owner decision: approved` in their first lines. If any is missing, stop and tell the owner which command to run (`/review-spec` or `/plan-and-design`) or which file to approve. Later steps need the gate again only if a planning document changed since approval.

1. Read the step's section in `docs/PLAN.md` and the matching sections of `docs/DESIGN.md`. Then read the SPEC sections the plan references for this step, in full. Re-read the rules in `CLAUDE.md`.
2. Turn the plan's section into a task list before touching code: the files, tests and commits it names, in its order. Service and its tests first, API and API tests second, UI and UI tests third. If you would do something the plan does not list, stop and ask first.
3. Scope check. Nothing marked P1. Nothing outside the plan's section. Nothing the spec does not ask for. If the plan, the design and the spec disagree, or the step needs something none of them covers, stop and ask the owner before coding, then record the answer with `/log-decision` and in the document that was wrong.
4. Match recipes. If the step adds an endpoint, a validation rule, an insight or a page, follow `/add-endpoint`, `/add-validation-rule`, `/add-insight` or `/frontend-page`. Say which ones apply.
   Then check your own skill and tool lists against the plugins CLAUDE.md names and say which you will use for this step and for what.
5. Implement in 2 to 6 commits. Commit after each green unit of work. The pre-commit hook runs lint and tests, and a blocked commit means fix the failure, not work around the hook.
6. When every acceptance criterion in the step's functional requirement has a passing test, run `/finish-step`.

Report the plan to the human before starting work on it.

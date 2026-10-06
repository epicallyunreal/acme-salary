---
name: finish-step
description: Close out a build step. Runs lint and tests, runs the four reviewer subagents, fixes blockers, updates DECISIONS and PERFORMANCE, then commits. Use when a step's acceptance criteria pass, or when the user says "finish step", "wrap up the step" or "ready to commit the step".
argument-hint: <step number>
---

# Finish a build step

Step: `$ARGUMENTS`.

1. Gate locally first. Backend: `ruff format --check . && ruff check . && pytest -q -m "not slow"` from `backend/`. Frontend, if it exists: `npm run lint && npm test -- --run` from `frontend/`. Fix anything red before going on.
2. Run all four reviewers in parallel with the Agent tool: `code-reviewer`, `spec-checker`, `test-reviewer`, `security-reviewer`. Give each the step number and the range to review (`git diff <first commit of the step>^..HEAD` plus uncommitted work).
3. Fix every Blocker. For Should-fix items, fix now if it takes under five minutes, otherwise list them in the commit body. Leave Nits unless trivial.
4. If a reviewer raised `Question for the human`, stop and ask before continuing.
5. Docs in the same commit:
   - `docs/DECISIONS.md`: one entry per non-obvious choice made in this step, via `/log-decision`.
   - `docs/PERFORMANCE.md`: if the step touched the directory, insights, import or seed, run `/perf-timing`.
6. Commit. Subject names the step, for example `feat(import): staging, validation and approve (step 5)`. Never amend or rebase.
7. Report to the human in five lines: what shipped, what the reviewers caught, what was deferred, what the next step is.

# CLAUDE.md

Project conventions for Claude Code. Four documents govern the work. `docs/REQUIREMENTS.md` says what is in and out of scope. `docs/SPEC.md` says what the system is: data model, API, rules, acceptance criteria. `docs/DECISIONS.md` says why. `docs/PLAN.md` and `docs/DESIGN.md`, once the owner approves them, say what gets built, in what order, and how. Code is built from the approved plan and design, and they are derived from the spec.

## Before any task

0. On a fresh repo the order is fixed: `/review-spec`, the owner approves the report, `/plan-and-design` writes `docs/PLAN.md` and `docs/DESIGN.md`, the owner approves both, then `/start-step 1`. Nothing is built before that.
1. Check `.claude/skills/` for a matching skill and follow it. Say which skill you are using in one line. If none applies, say so and proceed. The skills are:
   - `/start-step <n>` and `/finish-step <n>` bracket every build step.
   - `/add-endpoint`, `/add-validation-rule`, `/add-insight`, `/frontend-page` are the recipes for the recurring kinds of work.
   - `/log-decision` records a choice. `/perf-timing` measures and records timings. `/review-spec` and `/plan-and-design` are the owner's gates and are never run on Claude's own initiative.
2. Work in the order of the approved `docs/PLAN.md`. Do not start a later step before the earlier one is green and committed.
3. If the spec is silent or looks wrong, stop and ask. Editing `docs/SPEC.md` or `docs/REQUIREMENTS.md` prompts for confirmation on purpose.

## Plugin skills and connectors

At the start of every step, list what is installed with `/plugins` and `/mcp`, pick what fits the step, and say so in one line. Preferred uses, when the plugin or connector is present:

- UI work (steps 3 to 7): `frontend-design` for visual direction and component styling, `ui-ux-pro-max` for layout and interaction patterns, `modern-web-guidance` before any non-trivial CSS or browser API, `design:accessibility-review` before closing a UI step, `design:ux-copy` for empty states, errors and button labels.
- Engineering: `engineering:testing-strategy` when planning a step's tests, `engineering:code-review` as a second opinion after the project reviewers, `engineering:debug` for any failure that is not obvious in five minutes.
- Charts: `data:data-visualization` when choosing or styling a chart in the insights work.
- Library facts: the `Context7` connector to read current documentation for Django, DRF, SimpleJWT, openpyxl, MUI X, Recharts, TanStack Query before using an API from memory.
- Ship step only: the `Cloudflare` connector for the subdomain's DNS record and, if the owner asks, a WAF or rate-limit rule in front of the login endpoint. Never store a Cloudflare token or any credential in the repo.

Project skills in `.claude/skills/` win over plugin skills where they overlap. A plugin skill's advice never overrides a rule in this file or in `docs/SPEC.md`. If a plugin is not installed, say so once and continue without it.

## What this is

Salary management for ACME, 10,000 employees across six countries. One HR Manager imports spreadsheets, maintains compensation records, and reads an insights dashboard. Django + DRF + SQLite on the backend, React + MUI on the frontend, shipped as one Docker container.

## Commands

Backend, from `backend/` with the venv active:

- `pip install -e ".[dev]"` then `python manage.py migrate`
- `python manage.py seed_data --employees 10000 --seed 42` (add `--reset` to wipe and rebuild)
- `pytest` runs the whole suite in under 60 s. `pytest -m "not slow"` skips the seed test.
- `ruff format . && ruff check .`

Frontend, from `frontend/`:

- `npm ci`, `npm run dev`, `npm test`, `npm run lint`, `npm run build`

Whole app: `docker compose up` from the repo root, then open http://localhost:8000.

## Rules that are not negotiable

1. Views and serializers stay thin. Every business rule lives in a `services.py` or `queries.py` module that takes plain Python values and is tested without HTTP.
2. Money is `DecimalField(14, 2)` and FX rates are `DecimalField(18, 8)`. No floats for money anywhere, tests included.
3. Header totals (gross, net, total cost) are computed by `compensation/services.py` from the lines, in local currency. Serializers never accept totals from the client. Converted amounts are computed at read time by `core/fx.py` and never stored on any model.
4. One validator module, `compensation/validators.py`, is used by the import pipeline, the API and the seed. A value that is illegal in one place is illegal everywhere.
5. Import approval runs inside one `transaction.atomic()` block. Live tables are never written before approval.
6. No hard deletes of employees or compensation records. Employees are marked exited, records are superseded by a new revision.
7. Every write to employee or compensation data goes through `audit.record()` and lands in `AuditLog` with before and after snapshots.
8. The seed is deterministic. Same arguments, same bytes. It goes through the same services as the UI so seeded data obeys the same rules.
9. No new runtime dependency without a one-line entry in `docs/DECISIONS.md` saying why. Installing prompts for confirmation.
10. Secrets come from the environment. `.env.example` is committed, `.env` is not.

## Reviews

Four read-only subagents live in `.claude/agents/`: `code-reviewer`, `spec-checker`, `test-reviewer`, `security-reviewer`. `/finish-step` runs them before a step is committed. Every Blocker they raise is fixed before the commit. A `Question for the human` from any reviewer stops the work until it is answered.

## Hooks

`.claude/settings.json` wires three hooks. Editing a file formats it and checks a few rules (FloatField, logic in views, non-deterministic tests). Every `git commit` runs ruff, pytest, eslint and vitest first and blocks the commit if anything fails. A blocked commit means fix the failure, never bypass the hook or skip tests. Session start prints the repo state and the skill list.

## Tests

- Backend: `pytest`, `pytest-django`, `factory_boy`, `freezegun`. In-memory SQLite. Small factories, never the 10k seed.
- Frontend: Vitest, React Testing Library, MSW for the API.
- Tests land in the same commit as the code they cover.
- Deterministic by construction: fixed seeds, frozen time, no network, explicit ordering before asserting order.
- Pin query counts on list and insight endpoints with `django_assert_num_queries`.
- Coverage target is 85% on `apps/compensation`, `apps/imports` and `apps/insights`. Report it, do not gate on it elsewhere.

## Commits

- Small and coherent. One change per commit, with its tests.
- Imperative subject under 70 characters. Add a body when the why is not obvious from the diff.
- Conventional Commits: `type(scope): subject`. Types are `feat`, `fix`, `test`, `docs`, `refactor`, `perf`, `build`, `ci`, `chore`. Scope is the app or area (`import`, `fx`, `directory`, `dashboard`) and is optional. `perf` for changes made for speed, `build` for Dockerfile, pyproject and package.json, `ci` for the GitHub Actions workflow, `chore` for everything else that is not code or docs. Name the step in the subject when closing one.
- Never rewrite history. `--amend`, `rebase`, `reset --hard` and force pushes are denied in settings. The commit log is part of the submission.

## Scope

- Build what the approved `docs/PLAN.md` says for the current step, the way `docs/DESIGN.md` describes it, against the acceptance criteria in `docs/SPEC.md`. Nothing outside the plan. Items marked P1 wait until the Ship step is committed.
- If the plan or design disagrees with the spec, or the spec is silent on something the step needs, stop and ask. The owner resolves it and the fix lands in the document that was wrong, never in the code alone.
- When a non-obvious choice is made during a step, run `/log-decision` in the same commit.
- Before closing a step that touched the directory, insights, import or seed, run `/perf-timing` and update the numbers.

# Spec review, 2026-10-06

Owner decision: pending

## Verdict

Rework before development. The design survives verification, but seven defects in the text would each produce wrong data, a stalled step or a failed deployment if built as written, and five of them need an owner decision, not a wording fix.

## Blocking issues

Short names used throughout:

- SPEC: `/Users/nutanprabhat/MyProjects/IncubyteScreening/acme-salary/docs/SPEC.md`
- REQUIREMENTS: `/Users/nutanprabhat/MyProjects/IncubyteScreening/acme-salary/docs/REQUIREMENTS.md`
- DECISIONS: `/Users/nutanprabhat/MyProjects/IncubyteScreening/acme-salary/docs/DECISIONS.md`
- CLAUDE.md: `/Users/nutanprabhat/MyProjects/IncubyteScreening/acme-salary/CLAUDE.md`
- Settings, hooks, skills and agents: under `/Users/nutanprabhat/MyProjects/IncubyteScreening/acme-salary/.claude/`

**B1. The date check rejects valid revisions and will abort the seed.**
- Where: SPEC §5 CompensationRecord, "Check constraint: `effective_to IS NULL OR effective_to > effective_from`", and §5 ExchangeRate, "Check `effective_to > effective_from`". Against §4.3, "`effective_to` = new `effective_from` minus one day", and F3, "a revision whose `effective_from` is after the current record's".
- Wrong: end dates are inclusive. A revision dated one day after the current record starts closes that record with `effective_to` equal to its own `effective_from`, which the constraint forbids.
- Checked: I built the constraint as written on Django 5.0.4 and SQLite 3.45.1. Closing the record raised `IntegrityError: CHECK constraint failed`.
- The seed reaches this case. If April raises are dated 1 April, anyone who joined on 31 March triggers it. That is about 28 of 10,000 employees by my arithmetic (12 such dates in a joining window of about 4,290 days).
- Change: `>=` in both constraints. Add an F3 acceptance line for a revision dated the day after the current one.

**B2. A future-dated revision becomes current pay immediately.**
- Where: SPEC §4.3, "Current pay is the record with `effective_to = null`". §9, "read current records (`effective_to = null`)". §7 has no rule on a future `effective_from`.
- Wrong: next April's raise entered in March is reported today by the directory, every insight and every export. The record it replaces gets a future end date.
- Checked: every §7 row, F3, §8 and the seed rules. Nothing forbids or handles a future date.
- Change: owner decision. Cheapest for v1 is to reject `effective_from` after today in the API and the import, with a §7 row and message. Defining current as "effective on the reporting date" changes the constraint, the directory query and every insight.

**B3. The insights population is defined two ways.**
- Where: SPEC §9, "All honour `country` and `department` filters and read current records (`effective_to = null`)". The add-insight skill step 1, "Read current records only (`effective_to__isnull=True`) joined to active employees". SPEC §9 insight 1, "active headcount". SPEC §11 rule 4, "8% of employees exited ... Exited employees keep their records."
- Wrong: the 800 exited employees are in or out of every sum, median and chart depending on which file the implementer follows. The spec-checker agent verifies against §9 and the recipe says the opposite.
- Checked: grep for "active" and "exited" across all documents. Nothing says whether exit closes the open record.
- Change: one sentence in §9 naming the population for all six insights, the same sentence in the skill, and an exited employee in the insight fixture. Recommendation: active employees only.

**B4. Import rules for an existing employee contradict each other, and F1's first acceptance criterion has no input file.**
- Where: SPEC §7, "`effective_from` not after the employee's current `effective_from` | error" and "Row identical to the employee's current record | info, action `noop`". F1, "Matched and unchanged: no-op" and "Given the 10,000-row seed export, when uploaded". The perf-timing skill, "export the seed to the template with the exports endpoint". SPEC §8 `/exports/employees` and `/imports/template`.
- Wrong:
  - (a) An unchanged row carries the current record's own `effective_from`. One rule makes it an error, the other a no-op.
  - (b) Nothing produces a template-shaped file of existing employees. `/exports/employees` exports the directory view and `/imports/template` is empty. "The seed export" does not exist.
  - (c) If the file is all no-ops, "approved in under 15 s" in §13 times an apply that writes nothing.
  - (d) Not specified: a matched row whose department, level, name or `last_date` changed but whose amounts did not (F1 and §4.9 make it a no-op, so the change is dropped silently), a matched row with blank `effective_from`, and a matched row with a different `country_code`.
- Checked: grep for "seed export" and "template", every §7 row, the §8 table.
- Change: owner decision on (d). Then add a decision table to F1 (identity changed, amounts changed, `effective_from` given, resulting action). State that the no-op check runs before the date check. Name a generator for the 10,000-row file, a management command that writes new employees plus dated raises so approve performs real writes. Reference it from F1, §13 and the perf-timing skill.

**B5. The deployment section names a mechanism that does not exist, states two persistence models, and schedules the client's one hard requirement last.**
- Where: SPEC §14 and §15, DECISIONS D11.
- (a) Wrong: "WhiteNoise serves hashed static files and `index.html` for any non-`/api` path." WhiteNoise 6.12 docs: `WHITENOISE_INDEX_FILE` serves directory index files, and nothing serves `index.html` for unknown paths. A refresh on `/employees/123` returns 404 unless Django has a catch-all view. SPEC §3 lists one ("urls.py # /api/v1/*, /api/schema, SPA fallback"), so §3 and §14 disagree.
- (b) Unspecified: "copies `frontend/dist` into Django's static root". Vite 8's default `base` is `/`, so the built `index.html` requests `/assets/...`, while WhiteNoise serves the static root under `STATIC_URL`. The Vite `base`, where the fallback view reads `index.html`, and the paths excluded from the fallback are all guesses.
- (c) Wrong as written: "`gunicorn acme_salary.wsgi --workers 2 --threads 4`". gunicorn's default bind is `127.0.0.1:8000` unless `PORT` is set. In docker compose, and on any host that does not inject `PORT`, the container is unreachable. CLAUDE.md promises "open http://localhost:8000".
- (d) Contradiction: §14 "The seed is deterministic, so an ephemeral disk rebuilds identical data on each cold start." Against §14 "with a persistent volume for the SQLite file so the 10k seed runs once, not on every cold start". Against D11 "Render is a fallback if the first host gives trouble, with the seed rebuilt on each deploy."
  - Render docs: disks attach to paid services only. A free service loses its filesystem on every redeploy, restart and 15-minute idle spin-down, and "Render might restart a Free web service at any time". On that fallback every import or edit a reviewer makes disappears.
  - §14 lists three hosts, D11 two.
- (e) Order: Dockerfile, compose and the first deploy are step 9, the last step. §14 gives CI a Docker build job from step 1 with nothing to build until step 9. The domain is on `.dev`, which is HSTS-preloaded, so the site does not load in a browser until the certificate is live. Railway requires a CNAME and a TXT record, not "a CNAME to the host".
- (f) Entrypoint: "`seed_data` if the employee table is empty" against §11 "the command refuses to run on a non-empty database". No way to test emptiness is specified and no exit code is stated. First boot holds gunicorn back for the whole seed with no health-check allowance.
- Change: rewrite §14.
  - A catch-all Django view for the SPA and a stated Vite `base`.
  - `--bind 0.0.0.0:${PORT:-8000}`.
  - Delete the ephemeral-disk sentence.
  - Name one host. Allow Render only on a paid instance with a disk.
  - `seed_data --if-empty` exiting 0.
  - Deploy the empty container with volume, domain and TLS in step 1 and keep CI's Docker job green from then on.

**B6. The build order cannot be followed as written.**
- Where: SPEC §15 step 2, "`seed_data` with determinism and invariant tests". Step 4, "Services (totals, revisions), validators with full rule tests, ... audit writes and list". §11, "It goes through `compensation.services`, so seeded totals, FX and audit rows obey the real rules". CLAUDE.md rules 4 and 8.
- Wrong: the step 2 seed depends on services, validators and `audit.record()` that step 4 builds. Step 3's directory timing needs that seed.
- §11 also asks for both "goes through `compensation.services`" and "Writes use `bulk_create` in chunks of 1,000". A per-record service call cannot bulk-create.
- Checked: I timed both write shapes for 10,000 employees with about 25,000 records, 108,000 lines and 35,000 audit rows. Bulk took 3.6 s. One call at a time took about 13 s, with no validators running. This is bare ORM on a laptop, not the application.
- Change: move compensation services, validators and audit into step 2 ahead of the seed. Leave the compensation API and pages in step 4. Specify a bulk entry point on the service that the seed and the import apply both use.

**B7. The stack table is unpinned, partly out of support, and parts of it do not install together.**
- Where: SPEC §1 and §14.
- Checked: PyPI and npm registries on 2026-10-06, the Django download page, the Python devguide, the Node release schedule.

| SPEC says | Found | Consequence |
| --- | --- | --- |
| Django 5 | 5.0 and 5.1 are past end of support. 5.2 LTS (5.2.18) is supported to April 2028. Latest is 6.1.2. | Pin 5.2. `init_command` and `transaction_mode`, the documented way to set WAL and write locking, are "New in Django 5.1". |
| React 18 | Latest is 19.3.0. 18.3.1 was published 2024-04-26. | `react-router` latest (8.4.0) requires `react >=19.2.7`. React 18 forces `react-router` 7.18.x and `@types/react` 18. DECISIONS gives no reason for 18. |
| TypeScript, no version | Latest is 7.0.2. | `typescript-eslint` 8.71.1 accepts `typescript >=4.8.4 <6.1.0`. Pin 6.0.x. |
| MSW, no version | 3.0.0 was published 2026-09-28. It is ESM only, `http` and `HttpResponse` moved to `msw/http`, and `onUnhandledRequest` became `onUnhandledFrame`. | Handlers written in the 2.x style do not import. Pin 3.0.x and follow the migration guide, or pin 2.15. |
| Vitest, MUI, MUI X, Vite, no versions | Vitest 5.0.0 (2026-09-03), MUI 9.4.0, MUI X 9.15.0, Vite 8.3.3. | Each became the latest major between March and September 2026. Pin them. |
| DRF, no version | 3.18.1. drf-spectacular 0.30.0 lists DRF 3.12 to 3.17. | Pin 3.17 or confirm 3.18. |
| Python 3.12 | Security fixes only, end of life 2028-10. 3.14 is the bugfix release. | Defensible: SimpleJWT 5.5.1, factory_boy 3.3.3, freezegun 1.5.5 and gunicorn 26.2.0 declare support up to 3.13. Record that. Nothing pins Python the way `.nvmrc` pins Node, and this machine's `python3` is 3.14.3. |
| Node 24 "(Active LTS)" | Active LTS until 2026-10-20, then maintenance. | True today, stale in two weeks. Drop the label. |
| Backend dependencies | No lock file is specified. Faker 40.41.0 was published 2026-10-05. | Neither the build nor the seed is reproducible. |

- Change: put an exact version matrix in §1, add a backend lock file, and record the React and Python choices in DECISIONS.

## Contradictions between documents

1. **Client totals.** SPEC F3: "the value is ignored, header totals are recomputed from the lines". SPEC §13: "serializers reject client totals". CLAUDE.md rule 3: "Serializers never accept totals from the client." Change: one wording. DRF drops undeclared fields, so "ignored" is the default behaviour.
2. **Past-dated revision.** SPEC §8: "`409` for state conflicts (approving with errors, revising with a past date)". SPEC §7 gives the same rule as a field error, "`effective_from must be after 2025-04-01 (current record)`", and F3 says "The same validators run for UI edits and imports." The frontend-page skill says "Server field errors map back onto the form fields." Change: 400 with the field message for the revision endpoint, 409 for batch state only.
3. **Acceptance criteria as tests.** SPEC §6: "Acceptance criteria are the tests to write." CLAUDE.md: "Small factories, never the 10k seed." The start-step skill: "When every acceptance criterion in the step's functional requirement has a passing test, run `/finish-step`." The spec-checker agent: "For each `Given ... then ...` line".
   - Four criteria need the 10,000-row dataset (F1 first, F4 first, F5 first, F6 "An unfiltered export has 10,000").
   - Four are not in Given/then form (F4 second, both F5, F6).
   - Change: tag each criterion "test" or "measured by /perf-timing". Have spec-checker match the checkbox lines.
4. **Pages.** SPEC §10: "Seven routes behind one authenticated layout". SPEC §3: "pages/ # Login, Dashboard, Employees, EmployeeDetail, Imports, ImportReview" (six). The plan-and-design skill: "each of the seven pages". Change: add the new-employee page to §3. `/login` is outside the authenticated layout.
5. **Global components.** SPEC §11 table: "none beyond the global four". SPEC §4.2: "`BASE`, `TAX` and `EMPLOYER_CONTRIBUTION` are global" (three). REQUIREMENTS: "plus one or two per country", while the US has none. Change: "global three", "zero to two".
6. **Seed revisions.** SPEC §11 rule 5: "Each employee gets 1 to 4 compensation revisions" and, in the same sentence, "one per completed April anniversary". A 2015 joiner has eleven or twelve. Change: state the cap and the reference date.
7. **Seed anchors.** SPEC §11 table: "Level-3 median gross (local, annual)". Rule 2: "Base salary = country level anchor x lognormal noise". For India gross is 1.65 times base before bonus. No multipliers are given for the other five levels. Change: publish base anchors per country and level, or say tests do not assert them.
8. **Agents and hooks counts.** CLAUDE.md: "Four read-only subagents live in `.claude/agents/`". The directory holds five, and commit a10b17c says "five read-only reviewer subagents". `session_start.py` printed all five as "Reviewer subagents ... /finish-step runs them". CLAUDE.md: "wires three hooks". The settings file wires five handlers across four scripts, and `dependency_note.py` is undescribed.
9. **Security reviewer.** CLAUDE.md: "`/finish-step` runs them before a step is committed". The finish-step skill runs `security-reviewer` only "when the step touched the API, settings, auth, imports or exports".
10. **Decision log position.** The log-decision skill: "before the Open questions table". DECISIONS has no such table. Its last section is "Clarifications from Incubyte, 6 Oct 2026".
11. **Timing script.** The perf-timing skill: "The script lives at `backend/scripts/timing.py`. If it does not exist yet, create it as a Django management command". A management command cannot live there, and SPEC §3 has no `scripts` directory. The skill and `docs/PERFORMANCE.md` cite "section 13" for "seed under 60 s". §13 has no seed row, and the target is in §11.
12. **Skills against step order.** The add-insight skill step 4: "Register the insight's table shape in `apps/exports`". Insights are step 6 and export is step 7. The perf-timing import case uses "the exports endpoint" at step 5.
13. **P1 list.** DECISIONS D10: "Everything cut is specified under P1 in `SPEC.md`". SPEC §16 has no mypy and no audit timeline. The spec-checker's P1 list omits `POST /meta/exchange-rates`, the global audit page, pay bands, filter presets and Playwright.
14. **Audit entries per import row.** SPEC F2: "Each applied row writes an `AuditLog` entry" and "audit entries equal `applied_rows`". CLAUDE.md rule 7: "Every write to employee or compensation data goes through `audit.record()`". A create row writes an employee and a record. F2 also says "`applied_rows` = total minus 3", while §7 no-op rows "will be skipped on apply". Change: define entries per row and exclude no-ops from `applied_rows`.
15. **Who calls the validators.** SPEC §2: "Every business rule ... lives in a `services.py` or `queries.py` module". The add-endpoint skill: "Input serializer ... calls `compensation/validators.py` for business rules." Change: the service calls validators, and serializers check shape only.
16. **Reversibility.** DECISIONS D9: "Mistakes need to be traceable and reversible." SPEC §4.3: "Records are never edited in place in v1". There is no import undo and no un-exit in §8. v1 traces a mistake but cannot reverse one.
17. **UI steps.** CLAUDE.md: "UI work (steps 3 to 7)". SPEC §15 step 8: "error and empty states in the UI, accessibility pass".
18. **Fixture size.** SPEC §12: "a 30-row fixture". The add-insight skill: "a 20 to 30 row fixture".
19. **Indexes.** SPEC §13: "indexes on filter and sort columns". §5 has none on `joining_date`, `designation`, `level` or `status`. §5 says "`gross_annual` indexed", while F4 says the gross sort is "not an indexed column".
20. **Gate wording.** The review-spec skill: "edits its first line to `Owner decision: approved`". The report's first line is its title. The start-step and plan-and-design skills accept "a report", while `session_start.py`, README and SPEC §17 say "the latest".
21. **Stale hosting words.** DECISIONS D5 title: "hosting conditional". SPEC §17: "live URL if hosted". SPEC §14: "Hosting is required".
22. **Audit actions.** The AuditLog enum has `set_rate` and DECISIONS D13 says "one audited transaction". SPEC §4.7, F7 and D9 list no rate change.
23. **Security reviewer beyond the spec.** The agent requires "`read_only=True` and `data_only=True`", "Extension and content type checked", "refresh rotation on, blacklist on rotation if available" and "`SEED_ADMIN_PASSWORD` has no production default". SPEC states none of these. Change: add them to F1, F8 and §13, or drop them from the agent.

## Technical claims: wrong or unverifiable

**1. "No floats for money."**
- Claimed: SPEC §4.1 "stored as Decimal". CLAUDE.md rule 2 "No floats for money anywhere". DECISIONS D13 "so SQLite's float arithmetic never touches displayed money".
- Checked: Django 5.2 SQLite notes say "Decimal values are internally converted to the `REAL` data type (8-byte IEEE floating point number)".
- Probe:
  - The column type is `decimal`. `2400000.37` is stored as `real` and `150000.00` as `integer`.
  - `SUM()` is `real`, and `Sum()` returned `Decimal('2400000.37000000')`.
  - The annotation compiles to `CAST((gross_annual * (SELECT rate ...)) AS NUMERIC)` and returns `Decimal('28571.4284047612')`.
- Found: false as written. The practical error is nil at this scale. A 4,500-row INR sum and 4,500 row products matched exact Decimal results at 2 dp.
- One visible effect is rounding, not float error. A row shown as 28571.43 is excluded by `gross_min=28571.43`.
- Change: say "Decimal in Python, REAL in SQLite. SQL arithmetic orders and filters only. Every value sent to a client is quantised in `core/fx.py`." State the rounding mode and whether range filters compare rounded values.

**2. `?format=` on the export endpoints.**
- Where: SPEC §8 and F6.
- Checked: DRF's `URL_FORMAT_OVERRIDE` defaults to `'format'`. Probe on DRF 3.15.1 with a plain `APIView`: `format=json` returned 200, `csv` and `xlsx` returned 404 before the view ran.
- Change: rename the parameter, or specify CSV and XLSX renderers, or disable the override. Say which in §8.

**3. "Byte-identical data on every run."**
- Where: SPEC §11, CLAUDE.md rule 8.
- (a) Probe: `bulk_create` with an explicit `created_at` on an `auto_now_add` field stored the current time.
- (b) Faker docs: "results are not guaranteed to be consistent across patch versions". No version is pinned.
- (c) Probe: two Django hashes of the same password differ, so `auth_user` differs every run.
- (d) "Completed April anniversary" and "the seed date" have no reference date.
- Change: scope the claim to named tables and columns. Fix the reference date. Use `default=` or explicit timestamps. Pin Faker to the patch. Say what the test hash is compared with.

**4. "DataGrid's server-side model maps one-to-one onto DRF" (DECISIONS D6).**
- Checked MUI X 9.15: the page index is zero-based. The MIT grid sorts one column and applies one filter item (multi-sort and multi-filter are Pro). Pages cap at 100 rows.
- Change: "through an adapter". Say whether the grid's own filter panel is disabled.

**5. "SQLite can filter JSON but cannot index into it" (DECISIONS D1).**
- Probe: an expression index on `json_extract(components, '$.BASE')` was created and used by the planner.
- Change: give a reason that holds, such as integrity per component and aggregates by kind.

**6. SimpleJWT.**
- SPEC names no token setting, while the security-reviewer demands rotation and blacklist.
- Docs: `BLACKLIST_AFTER_ROTATION` needs `rest_framework_simplejwt.token_blacklist` installed, which adds two tables and a daily `flushexpiredtokens` job.
- Probe on 5.3.1: with both settings true and the app absent, a rotated-out refresh token was accepted again.
- Probe: the stock login view answers `{email, password}` with `400 {"username": ["This field is required."]}`.
- "Logout clears tokens" leaves the refresh token valid, and §8 has no logout endpoint.
- Change: state lifetimes, rotation, blacklist, logout and the login identifier in F8.

**7. Schema endpoint.**
- drf-spectacular's `SERVE_PERMISSIONS` defaults to `AllowAny`. SPEC F8: "Every `/api/` route requires auth except login and refresh".
- Change: say whether `/api/schema` is public.

**8. SQLite settings.**
- `busy_timeout=5000` is already the default (probe: a new connection reports 5000).
- Django docs: transactions default to DEFERRED, and "To make sure your transactions wait until `timeout` ... change the transaction mode to `IMMEDIATE`". An approve holding the write lock for up to 15 s exceeds a 5 s timeout for any other writer.
- WAL does not apply to the in-memory test database (probe: mode stays `memory`).
- `select_for_update()` has no effect on SQLite.
- Change: `transaction_mode: IMMEDIATE`, `init_command` for WAL, and a timeout above the longest write.

**9. "Postgres later is a settings change" (DECISIONS D5).**
- Unverifiable and optimistic. Money arithmetic changes from REAL to exact numeric. Case-insensitive search changes for non-ASCII text (probe: SQLite `'JÜRGEN' LIKE '%jürgen%'` is false). The data has to be moved.

**10. Numbers.**

| Number | Where | Kind | Plausible |
| --- | --- | --- | --- |
| 300 ms directory, 500 ms insights | F4, F5, §13 | Asserted. `docs/PERFORMANCE.md` is empty. D13 states it as fact. | Yes locally. My probe: 4 to 34 ms and 16 to 29 ms, bare ORM. |
| 30 s stage, 15 s approve | F1, §13 | Asserted | Staging insert took 0.33 s, parsing not measured. Approve only with bulk writes (B6). |
| Seed under 60 s | §11, D11 | Asserted | Yes locally. Unmeasured on a host. |
| Suites 60 s and 30 s | §12 | Asserted | Plausible. |
| 2 minutes, 10 seconds | REQUIREMENTS | Asserted, includes human time | Untestable. |
| 85% coverage | §12 | Target with no tool | Not applicable. |
| 40 h, 10 to 12 h, 5 h | D10, D12 | Author estimates | Unverifiable. Scope was added afterwards. |
| Seed shares | §11 | Design parameters | Each set sums to 100%. |

**11. Hosting details not confirmed.**
- Whether Railway volumes and Render disks are local or network storage. SQLite: "WAL does not work over a network filesystem".
- WAL on a Docker Desktop bind mount on macOS: not tested.
- CLAUDE.md's optional Cloudflare WAF needs the proxy on. Fly's docs then require a `_fly-ownership` TXT record and Full mode, so "a CNAME to the host, which issues the TLS certificate" is incomplete.

**12. openpyxl.**
- Memory on a 10,000-row sheet was not measured. openpyxl is installed in no interpreter here and I installed nothing.
- Docs: "By default openpyxl does not guard against quadratic blowup or billion laughs xml attacks. To guard against these attacks install defusedxml". The spec has no such line for an upload endpoint.
- `data_only=True` returns nothing for a formula Excel never calculated.
- The latest release is 3.1.5 from 2024-06-28.

**13. Claude Code setup.**
- (a) CLAUDE.md: "`--amend`, `rebase`, `reset --hard` and force pushes are denied in settings." Docs: a Bash rule matches the text before the first `*` and "isn't a security boundary".
  - `git commit -m "x" --amend` is not matched by `Bash(git commit --amend *)` and is allowed by `Bash(git commit *)`.
  - `git push origin main --force` falls to the ask rule.
  - `git branch -f` and `-D` are allowed by `Bash(git branch *)`.
  - Taken from the documentation, not executed.
  - Change: enforce in a PreToolUse hook that inspects the whole command.
- (b) `Write(docs/SPEC.md)` and `Write(docs/REQUIREMENTS.md)`: docs say "Claude Code accepts the rule but never consults it, and warns at startup". Unanchored `Edit(docs/SPEC.md)` and `Read(./.env)` are relative to the current directory. CLAUDE.md sends the agent to `backend/` and `frontend/`, and `cd` persists in the main session. Change: `Edit(/docs/SPEC.md)`, `Read(/.env)` and so on, and delete the Write rules.
- (c) The bare `Edit` and `Write` allow rules let the agent edit `docs/reviews/*.md`, `docs/PLAN.md` and `docs/DESIGN.md`, whose "Owner decision" line is the gate, without a prompt. Change: ask rules on those paths.
- (d) `session_start.py` takes `sorted(...)[-1]` as the latest report. `spec-review-2026-10-06-2.md` sorts before `spec-review-2026-10-06.md`. Reproduced: with a reworked first report and an approved second, the hook printed "rework requested (spec-review-2026-10-06.md)". Change: sort by modification time.
- (e) `dependency_note.py` fired on more than ten of my Bash calls, none an install, each time injecting "Rule 9 applies to this install" twice. Docs: a pattern that names more than the command runs the hook anyway on `$()`, backticks or `$VAR`. Change: check `tool_input.command` inside the script. `npm i` is not covered.
- (f) Gate fail-open paths:
  - Frontend checks are skipped when `frontend/node_modules` is absent (simulated: exit 0 with failing lint and test).
  - `git -C . commit` is not seen.
  - Docs: "a hook canceled at its timeout doesn't block the tool call", and five checks of up to 540 s run under a 600 s limit.
  - Terminal commits bypass it. SPEC lists "pre-commit" with no git hook defined.
- (g) Gate fail-closed path: tools are looked up in `backend/.venv/bin`, then PATH. `ruff`, `pytest` and `python` are not on PATH here, and no document says where the venv lives. Once `backend/pyproject.toml` exists, every commit is blocked with "tool not found" (simulated). The allow rules `Bash(pytest *)` and `Bash(python manage.py *)` have the same dependency, and docs say environment does not persist between Bash calls. Change: fix the venv path in CLAUDE.md and export it from the SessionStart hook through `CLAUDE_ENV_FILE`.
- (h) `post_edit.py` inspects only `views.py` and `serializers.py`. SPEC §3 calls these modules "API". The same content in `api.py` passed (simulated). A comment containing "FloatField" was flagged.
- (i) CLAUDE.md and two skills say "`/plugins` and `/mcp`". The command is `/plugin`, and the model cannot run built-in commands. Of the tools CLAUDE.md names, this machine has frontend-design, ui-ux-pro-max and Context7. It does not have the design, engineering, data or modern-web-guidance plugins, or a Cloudflare connector.
- (j) Nothing in the allow list covers `django-admin startproject`, `npm create vite`, `docker build`, a host CLI or `curl`. Steps 1 and 9 will prompt throughout. `Bash(python manage.py *)` also approves `shell -c` and `flush`.

**14. The brief and the client's replies are not in the repository.**
- Every quotation from the brief and both clarification tables are unverifiable.

**Checks not run.**
- No package was installed. Probes used an existing Django 5.0.4, DRF 3.15.1 and SimpleJWT 5.3.1 on `/usr/local/bin/python3.12`, older than the spec would pin, and were cross-checked against the 5.2 docs.
- WhiteNoise, drf-spectacular, openpyxl, MUI, Recharts, MSW and Vitest were not executed.
- Nothing was deployed.
- Permission matching was read from documentation, not exercised.
- No installed skill or plugin covers a planning-document review, so none was used. No memory tool was available to this agent.
- The repository is unchanged (`git status` clean). Probe scripts are in `/private/tmp/claude-501/-Users-nutanprabhat-MyProjects-IncubyteScreening-acme-salary/d5ef0d5c-2a65-4129-bdb0-ca61b257420b/scratchpad/`.

## Technical claims: verified correct

- **Partial unique on SQLite is enforced.** Django emits `CREATE UNIQUE INDEX ... WHERE "effective_to" IS NULL` and a second open record raises IntegrityError. Source: probe, Django 5.2 constraints and indexes docs.
- **DataGrid community has server-side modes.** `paginationMode`, `sortingMode`, `filterMode`, `rowCount` and the three models are on the MIT component. `pageSizeOptions` defaults to `[25, 50, 100]` and 100 is the MIT limit. Multi-sort, multi-filter and column pinning are Pro. Row grouping and Excel export are Premium, and F6 does not depend on them. Source: MUI X 9.15 API and feature pages.
- **SimpleJWT setting names and defaults.** `ROTATE_REFRESH_TOKENS` is False, `BLACKLIST_AFTER_ROTATION` is False, access is 5 minutes, refresh is 1 day. Source: SimpleJWT docs, probe.
- **openpyxl semantics.** `read_only=True` streams with "(near) constant memory", needs `close()` and trusts the file's dimension record. `data_only=True` returns "the value stored the last time Excel read the sheet". Source: openpyxl docs.
- **drf-spectacular supports SimpleJWT and django-filter.** Source: its readme.
- **Fly.io.** A volume is local NVMe, "not network storage", one per machine. Custom hostnames work by CNAME or A/AAAA with Let's Encrypt. Source: Fly docs.
- **Railway.** Volumes, one per service, automatic SSL. Source: Railway docs.
- **Render.** Disks on paid services, CNAME, automatic TLS. Source: Render docs.
- **SQLite WAL.** It needs all processes on one host and persists once set. Source: sqlite.org.
- **Recharts covers the five chart forms.** BarChart, ReferenceLine, LabelList, Scatter and ErrorBar with `[lower, upper]` values. There is no built-in histogram or box plot. Source: Recharts 3 API.
- **MSW 3.0.2 and Vitest 5.0.3 have compatible engine and peer ranges on Node 24 with Vite 8.** MSW 3.0.2's notes add "`virtual:msw` imports in vitest". Source: npm registry, MSW releases. Not executed.
- **Every named package exists.** Source: PyPI and npm.
- **Hook input and configuration.** `tool_input.command` and `tool_input.file_path` are the documented fields. `if` takes one permission rule. `command` plus `args` is the exec form and substitutes `${CLAUDE_PROJECT_DIR}`. Exit 2 blocks PreToolUse. SessionStart stdout enters context. Source: Claude Code hooks docs, and the hooks ran in this session.
- **Agent and skill frontmatter fields are valid.** `tools`, `disallowedTools`, `model: inherit`, `argument-hint`, `disable-model-invocation`. Source: Claude Code docs.
- **`engine-strict=true` fails `npm ci` on a root `engines` mismatch** with EBADENGINE. Source: probe, npm 11.19.0 on Node 24.21.0.
- **gunicorn with `--threads` above 1 uses gthread**, where the timeout "is not tied to the length of time required to handle a single request". Source: gunicorn settings.
- **CI inputs.** `node-version-file` accepts `.nvmrc`. `cache: pip` falls back to `**/pyproject.toml`. Source: setup-node README, setup-python source.
- **Docker tags `node:24-slim` and `python:3.12-slim` exist.** Source: Docker Hub.
- **Counts agree.** Ten tables, ten components, six insights plus five deferred, seven routes, ten skills. Decimal(14,2) and (18,8) agree across SPEC, CLAUDE.md, hook and agent. Source: counted and grepped.
- **The two clarification tables agree with each other, and nothing in SPEC contradicts them.** Source: read side by side.
- **Hook scripts do what their docstrings say on simulated input.** Source: ran both against a scratch tree.

Sources: [hooks](https://code.claude.com/docs/en/hooks), [permissions](https://code.claude.com/docs/en/permissions), [sub-agents](https://code.claude.com/docs/en/sub-agents), [skills](https://code.claude.com/docs/en/skills), [commands](https://code.claude.com/docs/en/commands), [tools](https://code.claude.com/docs/en/tools-reference), [Django databases](https://docs.djangoproject.com/en/5.2/ref/databases/), [constraints](https://docs.djangoproject.com/en/5.2/ref/models/constraints/), [indexes](https://docs.djangoproject.com/en/5.2/ref/models/indexes/), [custom user](https://docs.djangoproject.com/en/5.2/topics/auth/customizing/), [Django versions](https://www.djangoproject.com/download/), [Python versions](https://devguide.python.org/versions/), [Node schedule](https://raw.githubusercontent.com/nodejs/Release/main/schedule.json), [React versions](https://react.dev/versions), [DataGrid API](https://mui.com/x/api/data-grid/data-grid/), [pagination](https://mui.com/x/react-data-grid/pagination/), [sorting](https://mui.com/x/react-data-grid/sorting/), [multi-filters](https://mui.com/x/react-data-grid/filtering/multi-filters/), [MUI X licensing](https://mui.com/x/introduction/licensing/), [SimpleJWT settings](https://django-rest-framework-simplejwt.readthedocs.io/en/latest/settings.html), [blacklist app](https://django-rest-framework-simplejwt.readthedocs.io/en/latest/blacklist_app.html), [openpyxl](https://openpyxl.readthedocs.io/en/stable/), [openpyxl optimised modes](https://openpyxl.readthedocs.io/en/stable/optimized.html), [drf-spectacular settings](https://drf-spectacular.readthedocs.io/en/latest/settings.html), [drf-spectacular readme](https://drf-spectacular.readthedocs.io/en/latest/readme.html), [WhiteNoise](https://whitenoise.readthedocs.io/en/stable/django.html), [DRF settings](https://www.django-rest-framework.org/api-guide/settings/), [gunicorn settings](https://gunicorn.org/reference/settings/), [Fly volumes](https://docs.fly.io/volumes/overview), [Fly custom domains](https://docs.fly.io/networking/custom-domain), [Fly pricing](https://docs.fly.io/about/pricing), [Railway volumes](https://docs.railway.com/reference/volumes), [Railway networking](https://docs.railway.com/guides/public-networking), [Render disks](https://render.com/docs/disks), [Render free](https://render.com/docs/free), [Render domains](https://render.com/docs/custom-domains), [SQLite WAL](https://www.sqlite.org/wal.html), [Recharts API](https://recharts.github.io/en-US/api), [MSW migration](https://mswjs.io/docs/migrations/2.x-to-3.x), [MSW releases](https://github.com/mswjs/msw/releases), [Faker](https://faker.readthedocs.io/en/master/), [Vite config](https://vite.dev/config/shared-options), [setup-node](https://github.com/actions/setup-node/blob/main/README.md), [setup-python source](https://raw.githubusercontent.com/actions/setup-python/main/src/cache-distributions/pip-cache.ts), [.dev](https://en.wikipedia.org/wiki/.dev), [HSTS preload on .dev](https://kb.porkbun.com/article/96-hsts-preload-and-google-registry).

## Gaps and ambiguities an implementer would guess at

1. **Login identity and user model.** SPEC §10 says "email + password", §5 says "plus Django `auth_user`". Stock login needs `username`. Django docs: changing `AUTH_USER_MODEL` after tables exist "can't be done automatically". Decide before step 2's first migration.
2. **`POST /employees`.** Body shape, whether first compensation is required and atomic, and who assigns `employee_code`. An employee with no record breaks the gross sort.
3. **Employee detail.** F3 lists "edit" and §8 has `PATCH /employees/{id}`, but the §10 page has no edit control. The page shows reporting currency, yet neither detail endpoint takes `currency`. Exit with a future date, exit twice and undo are unspecified.
4. **Query conventions.**
   - Multi-value filter syntax. F5's "when a single country is selected" implies several can be.
   - Department by id, code or name.
   - `ordering` names other than `gross`.
   - `currency=local` with zero or several countries.
   - Maximum `page_size`. DRF ignores `page_size` unless configured (probe).
   - Trailing slashes.
5. **Insight maths.**
   - Percentile method. Python's two methods gave 125.14 and 175.21 for the same four values.
   - Rounding mode. A two-value median came back with 3 decimals.
   - Values outside p1 to p99, empty groups, and the gap when a gender has no members.
   - Which four of six summary figures are the "four KPI cards".
   - Small groups. 2% of a 5% country is about ten people, and insight 5 publishes min and max.
6. **Validation table.**
   - No list of required columns.
   - No message for gender, malformed email, below-minimum gross or the defaulted `effective_from`.
   - "The country's seeded minimum" is stored nowhere.
   - No rule for duplicate email within a file, `effective_from` before `joining_date`, deductions above gross, more than two decimals, decimal commas (the DE and NL convention), CSV encoding, or zero in a non-applicable column.
7. **Batch lifecycle.**
   - `validating` and `failed` have no trigger.
   - No column holds the unknown-column warning.
   - Responses for too many rows, too large, wrong type.
   - Approve of a stale batch (nothing says rows are re-validated at apply), approve twice, status after a failed apply.
   - `action` for a row with no usable code.
   - Retention of staged rows.
8. **Audit.** `GET /employees/{id}/audit` must join Employee and CompensationRecord entries, but AuditLog has only `entity_type` and `entity_id`. Snapshot shape is unspecified.
9. **Data model.** `on_delete` is given for one foreign key only. There are no checks for `level` 1 to 6, `last_date >= joining_date`, `rate > 0`, or differing currencies. Email case is unspecified. Row search "by code or name" must reach into JSON.
10. **FX.**
    - Where `set_exchange_rate` lives. §8 says management command, §15 says `core/fx.py`, §3 lists neither.
    - Its arguments, a second rate on the same day, a backdated rate.
    - No rate on the requested date. Seeded rates start 2026-10-01.
    - Which date the dashboard shows when five rates differ.
11. **Exports.** Directory columns, table shape for `summary`, `distribution` and `gender-gap`, download with a bearer token, and formula injection from names and notes. F6's "exactly the rows the grid shows" means the filtered set, not the visible page.
12. **Seed.** Nine of twelve departments are unnamed. Which countries carry the gap is unstated, and so is how a 3 to 6% gap is asserted at 500 employees, where Singapore gets about 25. "Non-empty database" is undefined. Behaviour with `SEED_ADMIN_PASSWORD` unset is unspecified.
13. **Django admin.** Step 2 says "admin registration". Admin edits and deletes bypass services, validators and audit. It is absent from §3, §8 and §13.
14. **Tooling named but undefined.** "pre-commit" has no config file. The 85% target has no `pytest-cov`. `django-filter` and Faker are required by a skill and by §11 but absent from §1 and DECISIONS, against CLAUDE.md rule 9. The CI backend job has no install step.
15. **Frontend session.** Refresh on page load, 401 handling, and a single in-flight refresh.
16. **Production settings.** Proxy TLS header, `SECRET_KEY` at build time, health-check path, login throttling, volume backup.
17. **Acceptance coverage.** F7 and F8 have no criteria. REQUIREMENTS success criteria include human time.
18. **Scope beyond the clarifications with no reason in DECISIONS.** The gender-gap and by-level insights (the client's examples were "total cost, average and median by country or department, headcount, distribution"), EUR and local modes, insight exports in three formats, the OpenAPI schema, Django admin.

## Risks

**Delivery**
- The hours are an estimate with no breakdown: "roughly 40" less "10 to 12". D12, D13 and D14 kept or added scope afterwards without re-estimating. No deadline is recorded anywhere.
- Each step close runs the suites three times (finish-step, test-reviewer, commit hook) and four reviewers.
- Five libraries changed major version since March 2026. Code written from memory will target older APIs.
- Deployment is last (B5).

**Performance**
- Reads have a wide margin in my probe.
- Approve meets 15 s only with bulk writes and is unmeasured on host hardware. Host size is unspecified. Two workers each holding a 10,000-row import on a 256 MB machine is a likely out-of-memory case (estimate).
- A long approve blocks other writers past the 5 s timeout.
- The probe database was 24 MB for a seed-sized dataset plus one staged batch. Staged and audit rows are never purged.

**Deployment**
- Fly has no free tier (from $2.19 a month plus $0.15 per GB). Render needs a paid instance for a disk. Railway's trial volume is 0.5 GB. No host CLI is installed here.
- One volume has no replica. Fly's guidance is "Always provision at least two volumes per app".
- TLS on `.dev`, DNS and the optional Cloudflare proxy all land in the final step.

**Review: what the client will ask first**
1. We said gross is sufficient and history optional. What did components, revisions, audit, exports and a second currency cost?
2. Why a gender pay gap chart, unadjusted, with a gap built into the demo data?
3. Is money really Decimal on SQLite?
4. One shared account on a public URL. How do we get the password, what stops guessing, why is the refresh token in localStorage, and does the data reset?
5. Why SQLite, React 18 and "Django 5"?
6. Who wrote what? CLAUDE.md says the commit log "is part of the submission". No document records an attribution convention, and README has no section on how it was built.

## Questions for the owner

1. Which host and plan, who pays, and is a paid Render instance acceptable as the fallback?
2. React 18 or 19? Does Python 3.12 stay? Do you approve a pinned matrix?
3. Future-dated revisions: reject in v1 or support?
4. Insights: active employees only, or every open record?
5. May an import change identity fields, exit an employee or change country for an existing code?
6. Custom user model with email, or username equal to email? What token lifetimes, and is rotation with blacklist wanted?
7. Do the gender-gap insight, the EUR and local modes, and insight exports in three formats stay in v1?
8. Django admin in production: yes or no?
9. How do reviewers get credentials, and does the public instance reset?
10. What is the deadline and the hour budget for v1?
11. Commit attribution: trailers or none, and a README section on how it was built? The three existing commits carry no trailer and are already on origin.
12. Should the brief and the raw Incubyte replies be added to `docs/`?
13. Is `/api/schema` public, and is a Swagger UI wanted?
14. Install the plugins CLAUDE.md names, or remove them from CLAUDE.md?
15. May the approval-line files get ask rules so only you can change them?

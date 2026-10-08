Owner decision: approved. Steps 1 to 7 on 7 October, steps 8 and 9 on 8 October with the changes recorded in D62 and D64.

# ACME Salary Management: Plan

What gets built, in what order, from `docs/SPEC.md` v2.1 section 15, the way `docs/DESIGN.md` describes it. Eleven steps, each 2 to 6 commits, each closed by `/finish-step` (lint, tests, the four reviewers, DECISIONS and PERFORMANCE updates, one closing commit named after the step). A later step does not start before the earlier one is green and committed. Nothing marked P1 is built before the Ship step. Hours are focused wall-clock hours with Claude Code doing the work and the owner reviewing at each step close; they include the `/finish-step` cycle (two suite runs plus four reviewer agents, 20 to 30 minutes per step).

## Dependency graph

```mermaid
flowchart LR
  S1["1 Scaffold and skeleton,<br/>deployed"]
  S2["2 Data layer, services,<br/>seed"]
  S3["3 Auth and directory"]
  S4["4 Compensation API and<br/>employee pages"]
  S5["5 Import pipeline"]
  S6["6 Insights"]
  S7["7 Export"]
  S8["8 Insights,<br/>second set"]
  S9["9 Realistic seed,<br/>a period, numbered pages"]
  S10["10 Hardening"]
  S11["11 Ship"]
  S1 -->|settings, test harness, CI, live target| S2
  S2 -->|models, fx, validators, pick_shown, factories| S3
  S3 -->|JWT, app shell, session, ServerGrid, FilterBar, detail serializer| S4
  S2 -->|bulk_apply, validators, exit rules| S5
  S3 -->|ServerGrid, StatusChip, auth coverage test| S5
  S4 -->|record serializer for audit snapshots in rows| S5
  S2 -->|population predicate pieces, RateTable| S6
  S3 -->|FilterBar, resolve_reporting_currency, shell| S6
  S3 -->|directory queryset and FilterSet| S7
  S6 -->|insight dicts to tabulate| S7
  S6 -->|population, published, cards, figures| S8
  S7 -->|export tables, menus, the Reason test| S8
  S2 -->|generator, bulk_apply, seed_data| S9
  S5 -->|make_import_file, the import timing| S9
  S8 -->|dated population, cards, controls| S9
  S3 -->|ServerGrid, FilterBar| S9
  S9 -->|seed and period timings| S10
  S8 -->|cards to polish| S10
  S10 --> S11
```

## Step 1. Scaffold and skeleton, deployed

Goal: an empty but real application on `https://acme.nutanprabhat.dev` with CI green, so every later step lands on a working target.

Files to create: `backend/pyproject.toml` (the pins in SPEC section 1, ruff and pytest config, `-m "not slow"` marker), `backend/uv.lock`, `backend/.python-version`, `backend/manage.py`, `backend/acme_salary/{__init__,wsgi,urls,spa}.py`, `backend/acme_salary/settings/{__init__,base,dev,prod,test}.py` (DESIGN 1.0), `backend/apps/__init__.py`, `backend/apps/accounts/{models,apps}.py` and `migrations/0001_initial.py`, `backend/apps/core/{views,apps}.py` (`healthz`), `backend/tests/{conftest.py,factories.py}` (user factory only), `backend/tests/core/test_healthz.py`, `backend/tests/accounts/test_user_model.py`, `backend/.env.example`. Frontend from `npm create vite@latest` (react-ts): `frontend/{.nvmrc,.npmrc,package.json,package-lock.json,vite.config.ts,vitest.config.ts,tsconfig.json,eslint.config.js,.prettierrc,index.html}`, `frontend/src/{main.tsx,App.tsx}` (create-vite 9 declares the Vite client types in `tsconfig.app.json`, so there is no `vite-env.d.ts`), `frontend/src/pages/Login.tsx` (placeholder form, no submit), `frontend/src/test/{setup.ts,handlers.ts,render.tsx}`, `frontend/src/App.test.tsx`. Root: `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `.github/workflows/ci.yml`, `fly.toml` (exists; step 1 adds `[http_service.checks.headers] Host = "acme.nutanprabhat.dev"` under the health check, because Fly's checker sends the machine's internal address as `Host` and Django's `ALLOWED_HOSTS` answers 400, D29), `README.md` run section.

Tests: `/healthz` returns `{"status": "ok"}` and 200 unauthenticated; the custom user model logs in by email and has no username; the frontend smoke test renders the login placeholder; CI runs both suites and the Docker build.

Commits:

1. `build(backend): Django 6.1 project with accounts.User, settings split and /healthz`
2. `build(frontend): Vite 8 React 19 app with ESLint, Prettier, Vitest and MSW setup`
3. `build: multi-stage Dockerfile, compose, entrypoint and .env.example`
4. `ci: GitHub Actions for backend, frontend and the Docker build`
5. `build: scaffold deployed with domain and TLS (step 1)` (the finish-step commit: DECISIONS entries for the SQLite version check and the measured first boot, PERFORMANCE note)

Hours: 2.5.

Acceptance closed: SPEC section 8 line 373 (`GET /healthz` unauthenticated, one query); section 14 lines 494 to 502 (empty skeleton deployed with domain and TLS, Dockerfile stages, WhiteNoise serving, gunicorn flags, entrypoint sequence, settings from the environment, compose, CI jobs); section 14 line 499 (measured first boot recorded against the 300 s grace).

Risks: the Fly volume, secrets, certificate (verified on IPv4 and IPv6) and the Cloudflare CNAME were put in place by the owner on 7 October, so the deploy is only the `fly deploy` prompt at the end of the step and the step closes with the custom domain live (D30). Docker Desktop is not running on this machine, so the local image build needs it started; CI's Docker job builds the image regardless. `python:3.14-slim` must carry SQLite 3.37 or later (checked in commit 3). `node:26-slim` and `vite` 8 on Node 26 are new enough that `npm ci` may surface peer warnings; the pins in SPEC section 1 were verified on the registry on 7 Oct.

Plugin skills and connectors: Context7 for Django 6.1 settings and `urls`, DRF 3.18 defaults, SimpleJWT 5.5 settings, Vite 8 and Vitest 5 config, MSW 3 setup. No design skill in this step.

## Step 2. Data layer, services, seed

Goal: every table, rule and service exists and is tested without HTTP, and `seed_data` builds the 10,000-employee demo deterministically in under 60 s.

Files to create: `apps/core/{models,fx,services,money,dates,exceptions,pagination,filters}.py` (and with them the three `REST_FRAMEWORK` keys that name these modules, `DEFAULT_PAGINATION_CLASS`, `DEFAULT_FILTER_BACKENDS` and `EXCEPTION_HANDLER`, which step 1 left out of `settings/base.py` because the modules did not exist), `apps/core/management/commands/set_exchange_rate.py`, `apps/core/migrations/0001_initial.py`; `apps/employees/{models,services,queries}.py` (`pick_shown`, `shown_record_subquery`, `shown_label`; the directory queryset comes in step 3) and migration; `apps/compensation/{models,services,validators,messages}.py` and migration; `apps/imports/models.py` and migration (models only; the pipeline is step 5); `apps/insights/__init__.py`, `apps/exports/__init__.py`; `apps/audit/{models,services}.py` and migration; `seed/{__init__,apps,profiles,lookups,generator}.py`, `seed/management/commands/{seed_data,reset_demo}.py`; `apps/imports/management/commands/make_import_file.py`; `tests/factories.py` (all factories), `tests/conftest.py` (the fixtures in DESIGN 9), `tests/core/{test_fx,test_set_exchange_rate,test_money}.py`, `tests/compensation/{test_totals,test_services,test_validators,test_bulk_apply}.py`, `tests/employees/{test_services,test_queries}.py`, `tests/audit/{test_record,test_snapshots}.py`, `tests/seed/{test_seed.py,golden.txt}`, `tests/imports/test_make_import_file.py`.

Tests: the SPEC section 12 service rows in full: totals, net and cost maths; revision dating (half-open chaining, next-day revision, scheduled revision, cancel and reopen, exit closing the record, the one-open-record invariant, version assignment); FX (rate by date, earliest-rate fallback, routing through USD, `set_exchange_rate` closing the previous row and refusing non-first-of-month, backdated and duplicate months, `convert` precision); every section 7 rule with one passing and one failing case; `bulk_apply` equal to the single path; audit snapshots equal to the serializer output; the determinism hash at 500 employees and again after `--reset`, the shares and invariants, `--if-empty`.

Commits:

1. `feat(core): lookups, exchange rates, read-time fx and set_exchange_rate`
2. `feat(compensation): models, migrations, validators and totals`
3. `feat(compensation): revise, cancel, exit and the bulk entry point with audit`
4. `feat(seed): profiles, generator, seed_data, reset_demo and make_import_file`
5. `feat: data layer, services and seed (step 2)` (finish-step: DECISIONS entries for the lookup-as-data choice, the snapshot functions, the seed rounding; PERFORMANCE seed row)

Hours: 6.5.

Acceptance closed: SPEC F3 lines 261 to 267 at the service level (the API form of the same criteria closes in step 4); F7 line 312 at the service level; section 11 line 433 `[measured]` (seed under 60 s, one transaction, `--if-empty`, `--reset` clearing `sqlite_sequence`) and line 457 (determinism hash, golden file); section 7 lines 331 to 363 (every rule with a passing and a failing test, except the rows the parser produces, lines 333 to 335, 346, 355 for non-numeric text, 356 and 357, which close with the parser in step 5); section 12 line 467 service rows.

Risks: the biggest step and the one everything else stands on; if it runs long the owner sees it first (D23). `bulk_create` returning primary keys on SQLite is a Django-on-SQLite-3.35 behaviour and is asserted by a test on the first commit that needs it. The golden hash changes whenever `profiles.py` changes, which is expected during this step and settles at its close. Seed timing on a laptop is not Fly timing; the Fly number is recorded at the first boot in step 1 and again at step 8.

Plugin skills and connectors: Context7 for Django 6.1 constraints (`condition=`), `Subquery`, `Case`, `bulk_create` and `bulk_update`, Faker's seeding API, factory_boy `post_generation`, freezegun on 3.14. `/add-validation-rule` for every section 7 rule. `/log-decision` for the choices above.

## Step 3. Auth and directory

Goal: the HR Manager can sign in on the live URL and page, sort, filter and search 10,000 employees under 300 ms.

Files to create: `apps/accounts/{views,serializers,urls}.py`; `apps/core/{views,urls}.py` (meta endpoints); `acme_salary/settings/base.py` gains a Content-Security-Policy through Django 6.1's `ContentSecurityPolicyMiddleware` (`script-src 'self'`, `connect-src 'self'`, `img-src 'self' data:`, `font-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`, and `style-src 'self' 'unsafe-inline'` because MUI's Emotion injects styles), logged with `/log-decision` and asserted by a test on an API response (owner's answer at the step 1 close); `apps/employees/{filters,serializers,views,urls}.py` and `queries.directory_queryset`; `acme_salary/urls.py` wiring; `apps/core/management/commands/timing.py` (directory cases; the rest lands in steps 5, 6 and 8); `tests/accounts/test_api.py`, `tests/test_auth_coverage.py`, `tests/core/test_meta_api.py`, `tests/employees/test_api.py`. Frontend: `src/api/{client,auth,meta,employees,keys,types}.ts`, `src/lib/{auth,money,dates,theme,constants}.ts`, `src/components/layout/{AppShell,RequireAuth,SessionGate,PageHeader,ErrorState,EmptyState,StatusChip}.tsx`, `src/components/grid/{ServerGrid.tsx,serverModel.ts,columns.ts}`, `src/components/filters/{FilterBar.tsx,useUrlFilters.ts}`, `src/pages/{Login,Employees,NotFound}.tsx`, `src/router.tsx`, `src/test/fixtures/{employees,meta}.ts`, handlers; tests `serverModel.test.ts`, `money.test.ts`, `dates.test.ts`, `client.test.ts`, `useUrlFilters.test.ts`, `Login.test.tsx`, `Employees.test.tsx`.

Tests: SPEC F8's three criteria plus rotation; the route-coverage test; directory filters combining with AND and surviving page and sort changes; `currency=local` with two countries 400; ordering on every allowed field including `-gross`; the pinned query count; the frontend list in DESIGN 9 for this step.

Commits:

1. `feat(auth): SimpleJWT login, refresh, logout, me and the login throttle`
2. `feat(directory): employee list and detail API with filters, search and the reporting-currency annotation`
3. `feat(frontend): theme, app shell, session handling and login page`
4. `feat(directory): server-side employee grid with FilterBar state in the URL`
5. `feat: auth and directory (step 3)` (finish-step: `/perf-timing` directory row, DECISIONS entry for `@fontsource/ibm-plex-sans` and any dependency added, deploy)

Hours: 4.

Acceptance closed: SPEC F8 lines 323 to 325; F4 lines 278 `[measured]`, 279 and 280; section 8 rows at lines 371 to 375, 377 and 378 (GET only); section 12 line 470 (FilterBar mapping, formatters, adapter with zero-based pages, session handling, login redirect).

Risks: the annotation query is measured right after commit 2, before any UI work, so a miss is found with the most time left; the fallback if it misses is to narrow the subquery to the two indexed columns and re-measure, not to materialise anything. MUI X 9, TanStack Query 5 and React Router 8 are newer than training data, so every prop and import is checked against Context7 before use. Dependency additions (`@fontsource/ibm-plex-sans`, `@mui/x-data-grid`, `@tanstack/react-query`, `react-hook-form`, `zod`, `recharts` are all in SPEC section 1 except the font package, which gets its DECISIONS line) prompt under rule 9.

Plugin skills and connectors: `/add-endpoint` for each API route, `/frontend-page` for the login and directory pages, `frontend-design` and `ui-ux-pro-max` for the shell, grid density and login layout following DESIGN 7, Context7 for SimpleJWT, DRF throttling, django-filter `OrderingFilter`, MUI 9 `createTheme`, MUI X 9 DataGrid server mode, TanStack Query 5, React Router 8.

## Step 4. Compensation API and employee pages

Goal: an employee can be created, edited, revised, scheduled, cancelled and exited from the browser, with the audit list visible.

Files to create: `apps/compensation/{serializers,views,urls}.py`; `apps/employees/views.py` additions (create, PATCH, exit, audit list) and serializers; `tests/compensation/test_api.py`, `tests/employees/test_api.py` additions, `tests/audit/test_api.py`. Frontend: `src/api/{compensation,audit}.ts`, `src/components/forms/{schemas.ts,EmployeeForm,RecordLinesFields,RevisionDialog,ExitDialog,EditIdentityDialog,applyServerErrors.ts}`, `src/components/employee/{CurrentRecordCard,HistoryList,AuditList}.tsx`, `src/pages/{EmployeeDetail,NewEmployee}.tsx`, fixtures and handlers; tests `EmployeeForm.test.tsx`, `EmployeeDetail.test.tsx`, `NewEmployee.test.tsx`.

Tests: SPEC F3's eight criteria through `APIClient` (the eighth, an exit before pay starts, from D50) (400 and 409 cases assert the field and message), `gross_annual` in a body ignored, `version` unique per employee, F7 one entry per entity per write path, the audit list pinned; frontend: zod message shown, server field error mapped, cancelled row greyed, Cancel only on scheduled rows, exit dialog 409 shown inline.

Commits:

1. `feat(compensation): create employee, revise, cancel, exit and audit list endpoints`
2. `feat(frontend): employee detail with current record, history, cancel, exit and audit tab`
3. `feat(frontend): new employee page, edit dialog and revision form`
4. `feat: compensation API and employee pages (step 4)` (finish-step: DECISIONS entries for any choice made in the step; deploy)

Hours: 4.5.

Acceptance closed: SPEC F3's eight criteria through the API, the eighth from D50, except the insights half of the scheduled-revision and exit criteria, which closes in step 6; F7's one-entry-per-write-path criterion through the API; section 8 rows `POST /employees/`, `PATCH /employees/{id}/`, `POST /employees/{id}/exit/`, `GET` and `POST /employees/{id}/compensation/`, `DELETE /compensation/{id}/` and `GET /employees/{id}/audit/`.

Risks: the first-record form carries up to six amount inputs that depend on the chosen country, so the component list must load before the lines render; zod 4 changed its API from zod 3 and react-hook-form 7's resolver is checked on Context7; the detail page is the densest page and the first real test of the visual direction.

Plugin skills and connectors: `/add-endpoint`, `/frontend-page`, `frontend-design` for the detail card and history list, `ui-ux-pro-max` for inline validation and the error summary, Context7 for react-hook-form 7, zod 4, MUI 9 Dialog and Tabs.

## Step 5. Import pipeline

Goal: a 10,000-row template file is staged with per-row messages in under 30 s, reviewed, and applied in one transaction in under 15 s.

Files to create: `apps/imports/{parser,services,applier,template,serializers,views,urls}.py`, `tests/imports/{test_parser,test_staging,test_review,test_applier,test_template,test_api}.py`, `apps/core/management/commands/timing.py` import cases, `sample-data/acme-sample-50.xlsx` and `.csv`. Frontend: `src/api/imports.ts`, `src/components/imports/{UploadDropzone,BatchList,BatchSummaryStrip,RowMessagesCell,SkipToggle}.tsx`, `src/pages/{Imports,ImportReview}.tsx`, `columns.importRows`, fixtures and handlers; tests `Imports.test.tsx`, `ImportReview.test.tsx`.

Tests: SPEC F1's eight criteria (the first `[measured]`) and F2's four, the decision table row by row over a fixture that includes a promotion row (identity and amounts) and an exit-with-raise row so F2's audit count is exercised in full, header aliases, the three number cases, the 10,001st row, the content-type and size rejections, skip and unskip restoring status, re-validation after a UI revision, the simulated failure; frontend: status filter calls the API with `status=`, Approve disabled with the reason, skip toggles a row and refetches the summary.

Commits:

1. `feat(import): template download, parser, header aliases and number and date normalisation`
2. `feat(import): staging with validation, the decision table and batch counts`
3. `feat(import): skip, unskip, discard and atomic approve through bulk_apply`
4. `feat(frontend): imports page with upload, template download and batch list`
5. `feat(frontend): import review grid with cell messages, skip toggle, approve and discard`
6. `feat: import pipeline (step 5)` (finish-step: sample data, `/perf-timing` import row, DECISIONS entries for any choice made in the step; deploy)

Hours: 5.

Acceptance closed: SPEC F1's eight criteria (the 10,000-row staging time `[measured]`); F2's four; section 8 rows `GET /imports/template/`, `GET` and `POST /imports/`, `GET /imports/{id}/`, `GET /imports/{id}/rows/`, `POST /imports/{id}/rows/{rowId}/skip/` and `/unskip/`, and `POST /imports/{id}/approve/` and `/discard/`; section 7's three header rows (required column missing, unknown column in header, file not UTF-8) through the upload tests.

Risks: the 30 s staging budget is spent in Python validation and the context build, both measured on the first 10,000-row run (commit 2) with `make_import_file --all --raises 1000`; 10,000 `ImportRow` objects before `bulk_create` are the memory peak and are measured there too. openpyxl returns dates as `datetime` and numbers as floats, both covered by the parser tests. The review grid has the most columns of any page.

Plugin skills and connectors: `/add-validation-rule` for any rule wiring, `/add-endpoint`, `/frontend-page`, `ui-ux-pro-max` for the dropzone, summary strip and cell-message pattern, Context7 for openpyxl read-only and write-only modes, DRF `MultiPartParser`, MUI X 9 cell rendering.

## Step 6. Insights

Goal: the dashboard answers the six questions in SPEC section 9 for any country and department filter, in under 500 ms per card.

Files to create: `apps/insights/{queries,views,urls}.py`, `tests/insights/{fixture,test_queries,test_api}.py`, `timing.py` insight cases. Frontend: `src/api/insights.ts`, `src/components/insights/{InsightCard,KpiCard,KpiRow,ByCountryCard,ByDepartmentCard,DistributionCard,ByLevelCard,GenderGapCard,chartTheme.ts}`, `src/components/filters/FilterBar` dashboard variant, `src/pages/Dashboard.tsx`, fixtures and handlers; tests `Dashboard.test.tsx` and one test per card.

Tests: the thirty-row fixture with the hand-computed values in DESIGN 9 for every insight, one test per filter per insight (`country`, `department`, `include_exited`, `on`, `currency=eur`, `currency=local`), the small-group rule, the empty group, the single-band distribution, the 404, pinned query counts; frontend: each card renders the fixture numbers, a filter change refetches every card, the include-exited box changes the headcount by the fixture's exited count, the local currency option appears only with one country.

Commits:

1. `feat(insights): population predicate, summary, by-country and by-department`
2. `feat(insights): distribution, by-level and gender-gap with the small-group rule`
3. `feat(dashboard): FilterBar, rate month label, KPI row and the five charts`
4. `feat: insights dashboard (step 6)` (finish-step: `/perf-timing` insight rows, DECISIONS entries for any choice made in the step; deploy)

Hours: 4.

Acceptance closed: SPEC F5's two criteria (every insight under 500 ms `[measured]`, the filter refetch and include-exited headcount `[test]`); section 9's population rule, maths and six definitions; section 8 row `GET /insights/{name}/`; section 12's service-test row for insights (the fixture with an exited employee, a scheduled revision, an empty group and a small gender group); and the insights half of F3's scheduled-revision and exit criteria as two named tests: the DESIGN 9 fixture's U1 shows its scheduled revision under `on=2027-01-01`, and an exited employee is counted with `on=` its `last_date` and gone with `on=` its `last_date + 1`.

Risks: Recharts 3 changed its API (`ErrorBar` on `Scatter` for the by-level whiskers, `ReferenceLine` for the markers) and is checked on Context7 before the chart commit; medians pull up to 10,000 values into Python per request, which is well inside 500 ms but is measured; the five charts are where the visual direction is most visible and the dataviz mark specs are applied as written.

Plugin skills and connectors: `/add-insight` for every query, `dataviz` for the series hues, mark specs and the no-legend rule on single-series charts, `frontend-design` for the KPI figures and card layout, `ui-ux-pro-max` for the chart accessibility fallbacks, Context7 for Recharts 3.

## Step 7. Export

Goal: any filtered directory view and any insight table downloads as CSV, XLSX or JSON from the page it is shown on.

Files to create: `apps/exports/{writers,tables,views,urls}.py`, `tests/exports/{test_writers,test_api}.py`. Frontend: `src/api/exports.ts` (bearer fetch, blob, programmatic save), `src/components/ExportMenu.tsx` wired into the directory header and every insight card; tests `ExportMenu.test.tsx`.

Tests: a filtered export has exactly the filtered rows across pages; the unfiltered directory export has 10,000 rows (`[measured]`, through the timing command on the seed); a name starting with `=` is escaped in CSV and XLSX; column order and headers; JSON shape; unknown insight 404; a by-level export with a level under twenty people carries its headcount and empty figures, as the card does (D59); the export endpoints need auth (covered by the route-coverage test).

Commits:

1. `feat(export): CSV, XLSX and JSON writers with formula escaping`
2. `feat(export): directory and insight export endpoints sharing the list filters`
3. `feat(frontend): export menus with bearer blob download`
4. `feat: export (step 7)` (finish-step: DECISIONS entries for any choice made in the step; deploy)

Hours: 2.

Acceptance closed: SPEC F6's three criteria (filtered rows across all pages, the 10,000-row unfiltered export `[measured]`, formula escaping in CSV and XLSX); section 8 rows `GET /exports/employees/` and `GET /exports/insights/{name}/`.

Risks: a 10,000-row XLSX is built in memory (a few megabytes, fine on 1 GB); streaming CSV under gunicorn threads holds a database cursor open for the duration, acceptable with one user. This step shrinks first if time runs short (below).

Plugin skills and connectors: `/add-endpoint`, Context7 for openpyxl write-only mode and `StreamingHttpResponse`.

## Step 8. Insights, second set

Added by the owner after step 7 closed, exports included (D62, SPEC v2.13). Built in the owner's order, each insight end to end, query, export and card, before the next.

Goal: the dashboard answers four more questions, `trend`, `cost-bridge`, `by-tenure` and `cost-mix`, and the gender-gap card three more views, Bonus, Quartiles and By level, each card with one control kept in the URL, sent by its export and reset by Clear filters, every card under 500 ms.

Files to change: `apps/insights/queries.py` (`population_on`, the dated population `trend` and `cost-bridge` share, the four insights, the gender views and the reason wording), `apps/insights/views.py` (each card's control parsed in `answer()`), `apps/exports/tables.py` (four tables and the gender views), `timing.py` (the new insights and every control value). Tests: `tests/insights/history.py` (a small fixture of joins, exits and raises over two years, figures worked out by hand), `tests/insights/{test_queries,test_api}.py`, `tests/exports/test_api.py`. Frontend: `src/api/{types,insights}.ts`, `src/components/filters/useDashboardFilters.ts` (the card controls under their prefixes), `src/components/insights/{CardControl,TrendCard,CostBridgeCard,ByTenureCard,CostMixCard}.tsx`, `GenderGapCard.tsx` (four views), `src/pages/Dashboard.tsx` (the cards under three headings), fixtures and handlers; tests `InsightCards.test.tsx`, `Dashboard.test.tsx` and `ExportMenu.test.tsx`.

Tests: the bridge's parts add up exactly, as hand-computed literals, its pay changes summed directly within 3 cents per currency of the balancing figure, 3 leavers withhold leavers, joiners and pay changes while start and end stay shown, and 0 leavers show every amount; trend and the bridge count the people employed on each date whatever Include exited says, with its caption when it is ticked; trend's 24 month-ends for `on` on 7 Oct 2026 and on a month-end, one rate for every month, total cost withheld under five at a point; by-tenure on each band's boundary (exactly 1, 3, 5 and 10 years) and within a level; cost-mix shares in both views; the gender views, Bonus shares and gaps, Quartiles with a count not divisible by four and tied pay, By level's mean and median gaps and the 5% flag either way; `fewer than 5 women`, `fewer than 5 men` and both, replacing `group too small` in every view; each D59 threshold; each control: a value outside its list is a 400, the URL keeps it, the export sends it, Clear filters resets it; query counts pinned; every new table ends with Reason, Currency and Rates (the step 7 test picks them up); every insight and view timed under 500 ms on the seed.

Commits:

1. `feat(insights): trend on a dated population, with its card and export`
2. `feat(insights): cost bridge whose parts add up exactly`
3. `feat(insights): pay by tenure within a level`
4. `feat(insights): cost mix by country, cost or take-home`
5. `feat(insights): gender gap's bonus, quartile and by-level views`
6. `feat: insights, second set (step 8)` (finish-step: `/perf-timing` for the new insights, DECISIONS entries for any choice made in the step; deploy)

The first commit also lays the card controls: `CardControl`, the prefixed URL keys, the controls in `answer()` and the export, and Clear filters resetting them.

Hours: 7.

Acceptance closed: SPEC v2.13 F5's card controls (in the URL, sent by the export, reset by Clear filters), F6's new tables, section 8's control parameters, section 9 rows 6 to 10 with their thresholds and reasons, and the 500 ms target for every new insight `[measured]`.

Risks: trend's 24 dates over 10,000 employees under 500 ms, met by one query of the records that overlap the window and a running sum per date in Python; the waterfall and the stacked bars in Recharts 3, checked on Context7 before the cards; the seed's two-year depth (D62), so exactness holds from 1 April 2026 for trend and 1 April 2025 for the bridge, and the tests use their own history fixture.

Plugin skills and connectors: `/add-insight` for every insight and view, `/log-decision`, `/perf-timing`, `frontend-design` and `ui-ux-pro-max` for the new cards and their controls, `dataviz` for the series hues and the stacked and waterfall marks, Context7 for Recharts 3 and MUI's `ToggleButtonGroup`.

## Step 9. Realistic seed, a period on the dashboard, numbered pages

Added by the owner before Hardening (D64, SPEC v2.16), approved with the owner's changes: the levels caption, the leave weights, the month-end rule for Last N months, the seed's Fly timing and a 15,000-row import limit. Built in six slices, each end to end with its tests, then the close: seven commits, one over the usual six, for the import limit added at approval.

Goal: the demo holds 10,000 employees on staff and 5,000 who left since 2015, each on an experience ladder with every raise and promotion since joining. The directory opens on its 10,000 active employees. The dashboard reads a period, its movement cards over the whole period and the rest on its last day, with what the period cost. Every grid pages by number. The targets hold on 15,000 employees.

Files to change:

- Seed. `seed/profiles.py` (the ladder, leave weights, raise and promotion ranges, the experience premium, active and exited counts, without `JOINING_RANGE`, `EXIT_SHARE` and `KEPT_RAISES`), `seed/generator.py` (today's state first, the leaver flow, the level path, history back-filled through every 1 April), `seed/management/commands/seed_data.py` and `reset_demo.py` (`--active`, `--exited`), `entrypoint.sh`, `apps/core/management/commands/timing.py` (the seed flags, the directory and export cases on the Active default, insights on each preset and a long custom range, the import on the 15,000-row file), `sample-data/` (both 50-row files regenerated), `tests/seed/` (golden hash and the ladder's invariants).
- Import limit. `apps/imports/parser.py` (`ROW_LIMIT = 15_000`), `apps/imports/management/commands/make_import_file.py` (`--all` writes all 15,000, leavers with their `last_date`), `src/components/imports/UploadDropzone.tsx` (`Up to 15,000 rows and 10 MB.`), the row-limit tests (the 15,001st row).
- Directory. `apps/employees/filters.py` (`status` defaults to `active`, `any` for everyone), `src/components/grid/serverModel.ts` and `src/components/filters/FilterBar.tsx` (Active first and default, Any one click away).
- Period. `apps/insights/queries.py` (`InsightFilters.start` and `end` in place of `on`, trend's points over the period, the bridge from `start` to `end`, `summary`'s spend in the period), `apps/insights/views.py` (`from` and `to` parsed and bounded), `apps/exports/views.py` and `tables.py` (the period in every insight export, trend's rows on its dates, the summary's spend), `src/lib/period.ts` (each preset to a `from` and `to`, the financial year), `src/components/filters/useDashboardFilters.ts` and `PeriodControl.tsx` (the bar's control, its URL keys), `src/api/{types,insights,exports}.ts`, `KpiRow.tsx`, `InsightCard.tsx` (the `on <to>` line), `RateMonthLabel.tsx`, the trend and bridge cards, the levels caption on ByLevelCard, ByTenureCard and GenderGapCard's By level, fixtures and handlers.
- Grids. `src/components/grid/ServerGrid.tsx` and `PageNumbers.tsx` (numbered pages and Go to page in the footer).

Tests: the seed's counts on the reference date, levels inside the ladder at the last review and never falling, every promotion an April revision with its note and a 12 to 20% raise, other raises 3 to 8%, nobody leaving within 30 days, years at ACME never above experience, leavers per month in proportion to the headcount, the golden hash, and in the slow 10,000 run the yearly leave rate; the import's row limit at the 15,001st row and the 15,000-row `--all` file, leavers included, staging cleanly; the directory and its export on Active by default, `status=any` for everyone, Clear filters back to Active; each preset's dates (31 October to 30 April, 31 March to the end of February in a leap year and in another, the financial year before and after 1 April, Last FY), the levels caption when `to` is not today, the URL keeping a preset's name and a custom range's dates, Clear filters back to Last 12 months, the bounds and `from` after `to` as 400s; trend's points `from`, each month-end and `to`, the bridge's start and end equal to trend's first and last points, the state cards on `to`, Spend in period hand-computed across a leap day and under D59, one rate for the whole period, every insight export sending the period and its JSON naming `from` and `to`; the numbered pages (first, last, neighbours, ellipses), Go to page, rows per page and the page in the URL, on the directory and the import review.

Commits:

1. `feat(seed): 10,000 on staff, 5,000 leavers, every raise since joining`
2. `feat(import): a 15,000-row limit, the whole organisation in one file`
3. `feat(directory): open on Active employees`
4. `feat(insights): a period from and to, with what it cost`
5. `feat(dashboard): the period control and cards on its last day`
6. `feat(grids): numbered pages and Go to page`
7. `feat: realistic seed, a period and numbered pages (step 9)` (finish-step: `/perf-timing` on 15,000 employees locally and on Fly, the seed timed on Fly with its target raised to 120 s if it takes over 60 s, and on Fly the import of both the `--all --raises 1000` file and a `--new 15000` file with the burst balance noted and peak memory recorded; deploy; `reset_demo` on the live machine only when the owner says so, after it has been idle, its time recorded)

Hours: 11.

Acceptance closed: SPEC v2.16 section 11's seed, its counts, ladder and history, and its time `[measured]`; F1's 15,000-row staging under 30 s `[measured]` and section 13's approve under 22.5 s, REQUIREMENTS' success criterion; F4's Active default; F5's period control, its presets, bounds and URL; F6's period in every insight export and the default directory export of 10,000 rows `[measured]`; section 8's `from` and `to`; section 9's cards on `to`, trend and the bridge over the period and Spend in period; section 10's numbered pages; the directory and insight targets on 15,000 employees `[measured]`.

Risks: the seed roughly doubles (about 15,000 employees and 60,000 records), so the 60 s target is at risk on Fly's shared CPU, where the first boot seeds before gunicorn starts; it is timed on Fly before `reset_demo` runs there. The exact counts and a leaver flow in proportion to the headcount must agree, met by placing the leavers month by month by largest remainder. A long custom range gives trend up to about 1,000 points and the bridge 15,000 people's history, so a 2015-to-today range is timed beside the presets. Level stays on the employee, so the cards that group by level read each person's level today on any `to` (DESIGN, question 1). 15,000 staged `ImportRow` objects are the memory peak on the 1 GB machine, recorded on Fly. The live database is rebuilt only with the owner's say-so, after the machine has been idle, since its burst balance sets the speed (D65).

Plugin skills and connectors: `/add-insight` and `/add-endpoint` for the period and its parameters, `/frontend-page` for the bar and the grids, `/log-decision`, `/perf-timing`, `frontend-design` and `ui-ux-pro-max` for the period control, the `on` lines and the page numbers, Context7 for MUI X 9's pagination slot and selectors and MUI's `Pagination`.

## Step 10. Hardening

Goal: the measured numbers are in `docs/PERFORMANCE.md`, every page has its error and empty states, keyboard and labels pass, and the README carries demo credentials and how the app was built.

Files to change: `apps/core/management/commands/timing.py` (complete, printing the PERFORMANCE row), `docs/PERFORMANCE.md`, `Dockerfile` and `entrypoint.sh` (an unprivileged user for the app, root kept only to own `/data`, the security reviewer's step 1 note), the pages and components listed in DESIGN 6's state table, `README.md` ("Run", "Test", "Demo credentials", "How this was built"), `.env.example` final, `docs/DECISIONS.md`.

Tests: the empty and error states of each page (fixture handlers returning empty results and 500), a keyboard test on each dialog (focus moves into the dialog and returns on close), labels present on every input (`getByLabelText` for each form field), no new backend tests beyond any fix a missed target forces.

Commits:

1. `perf: timing command complete and the measured numbers recorded`
2. `fix(frontend): error and empty states on every page and the accessibility pass`
3. `docs: README with run instructions, demo credentials and how it was built (step 10)`

Hours: 2.

Acceptance closed: the `[measured]` criteria consolidated into one PERFORMANCE row on the final code: SPEC F1's staging time, F4's directory p95, F5's insight response time, F6's unfiltered export, section 11's seed time and section 14's first boot; section 10's error and empty states on every page; section 13's accessibility row.

Risks: a missed target discovered here has the least time to fix; that is why the directory, import and insight timings are each measured at the end of their own step and only consolidated here. This step shrinks second (below).

Plugin skills and connectors: `/perf-timing`, `ui-ux-pro-max` for empty states, focus and the error summary, `frontend-design` for the copy of every state.

## Step 11. Ship

Goal: the final build is live, smoke-tested on the live URL, recorded, and the repository is public.

Files to change: `docs/DECISIONS.md` (final entries), `README.md` (live URL confirmed, demo video link), `docs/PERFORMANCE.md` (the Fly first-boot number from the final deploy).

Tests: none new. A manual smoke test on the live URL in the order of the demo: sign in, upload `sample-data/acme-sample-50.xlsx`, skip a flagged row, approve, open one of the imported employees, add a scheduled revision, change dashboard filters, export the directory.

Commits:

1. `docs: final decisions, performance notes and demo video link`
2. `chore: ship (step 11)`

Hours: 1.5, of which the demo recording is the owner's.

Acceptance closed: SPEC section 14's demo video; REQUIREMENTS in-scope item 9 (live URL, Docker, recorded demo) and its three success criteria (on the deployed instance).

Risks: a deploy in the last hour; the video takes longer than planned. Nothing in this step is optional.

Plugin skills and connectors: `/log-decision`. No design or library skill.

## Totals, target and shrink order

| Step | Hours | Cumulative | Planned close (IST, from a 12:30 start on 7 Oct) |
| --- | --- | --- | --- |
| 1 Scaffold and skeleton, deployed | 2.5 | 2.5 | 15:00, 7 Oct |
| 2 Data layer, services, seed | 6.5 | 9.0 | 21:30 |
| 3 Auth and directory | 4.0 | 13.0 | 01:30, 8 Oct |
| 4 Compensation API and employee pages | 4.5 | 17.5 | 06:00 |
| 5 Import pipeline | 5.0 | 22.5 | 11:00 |
| 6 Insights | 4.0 | 26.5 | 15:00 |
| 7 Export | 2.0 | 28.5 | 17:00 |
| 8 Insights, second set | 7.0 | 35.5 | added after step 7 (D62) |
| 9 Realistic seed, a period, numbered pages | 11.0 | 46.5 | added before Hardening (D64) |
| 10 Hardening | 2.0 | 48.5 | |
| 11 Ship | 1.5 | 50.0 | |

Total: 50 hours. Step 8 was added after step 7 closed on 8 October (D62), and step 9 before Hardening on 8 October (D64), so the planned close column stops at step 7.

Submission target: the morning of 8 October 2026 IST, full scope, per DECISIONS D19 and D23. The owner decides at the end on any overrun. At these estimates and with no breaks from a 12:30 start, steps 1 to 4 close by 06:00 on 8 October, step 5 by 11:00, step 6 by 15:00 and steps 7 to 9 by 20:30; the planned close column is the number D23 asks for, so each step's slip is visible against it at the time, not after. The table assumes continuous work; the owner's own stop time is not in it.

Shrink order if time runs short (SPEC section 15: steps 7 and 10 shrink before anything in 1 to 6, 8, 9 or 11):

1. Step 10 first: the accessibility pass and the per-page state polish drop; `/perf-timing`, the PERFORMANCE row and the README stay, because the `[measured]` criteria and the demo credentials depend on them.
2. Step 7 second: insight exports and the XLSX and JSON writers drop; the directory CSV export stays, because it is the one F6 criterion a reviewer will click.
3. Nothing in steps 1 to 6, 8, 9 or 11 is cut. Step 12 (P1) does not start.

## What the owner does by hand

1. Approve this document and `docs/DESIGN.md` by changing their first lines to `Owner decision: approved`, after answering or deferring the questions at the end of each. `/start-step 1` refuses to run before that.
2. Done on 7 October: the volume, the secrets, `fly certs add acme.nutanprabhat.dev` (verified on IPv4 and IPv6) and the Cloudflare CNAME with the proxy off. What remains is approving the `fly deploy` prompt when Claude Code runs it at the close of each deploying step. `fly` 0.4.113 is installed and logged in on this machine.
3. Copy `backend/.env.example` to `backend/.env` for local runs and choose a local `SEED_ADMIN_PASSWORD`.
4. Start Docker Desktop if a local `docker compose up` check is wanted before the Ship step; CI builds the image on every push either way.
5. Approve the dependency prompts under rule 9 (`uv add`, `npm install`) as they come, each with its DECISIONS line.
6. Answer any `Question for the human` a reviewer raises at a step close; the step waits on it.
7. In step 11: record the demo video on the live URL, give Claude Code the link for the README, and make the GitHub repository public.

## Questions for the owner

Answered on 7 October 2026, recorded as DECISIONS D30.

1. Deploy cadence: every step that adds a page (1, 3, 4, 5, 6, 7 and 9).
2. Step 1 and the by-hand list: moot, the Fly work is done; step 1 closes on the custom domain.
3. The slow seed test stays out of the commit hook.

Step 9 (D64) adds one by-hand item: say when `reset_demo` may run on the live database after the step's deploy, since it replaces the live data with the new seed. It then runs after the machine has been idle, and its time is recorded.

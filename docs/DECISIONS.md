# Decisions

Why the system is the way it is. One entry per non-obvious choice: context, decision, consequences. Newest at the bottom. Add an entry whenever a choice is made during the build that a reviewer might ask about.

## D1. Salary components are data, not columns

Context: the first draft had HRA, LTA, PF, Professional Tax and Gratuity as columns on a Salary table, and a separate Salary Schema table describing fields per country. The two contradict each other, and the columns are India-only. A US employee has a 401(k) match, a UK employee has National Insurance, a German employee has social insurance.

Decision: a `SalaryComponent` table (global or per country, kind of earning, deduction or employer contribution) and one `CompensationLine` per component on each record. Header totals (gross, net, total cost) are denormalised on the record.

Consequences: forms and the import template need the component list for the employee's country. Any question about a component is a query, not a Python loop. A JSON column was considered and rejected: a row per component gives integrity per component and aggregation by kind without parsing.

## D2. Effective-dated revisions, not a monthly salary history table

Context: the first draft had a Salary History table with one row per employee per month (Basic Paid, HRA Paid, Tax Deducted, and so on). For 10,000 employees over a few years that is several hundred thousand rows and a payslip UI, and it moves the product toward payroll processing, which the brief does not ask for.

Decision: a compensation change creates a new `CompensationRecord` with `effective_from`, and the previous record gets `effective_to`. Current pay is the record with `effective_to = null`.

Consequences: "salary over time" and point-in-time payroll cost both fall out of the dates. Monthly payslips are out of scope. If Incubyte asks for month-by-month amounts, a `Payout` table is additive and the revision model stays the source.

## D3. Insights computed on demand, no PySpark, no telemetry tables

Context: the first draft proposed PySpark for analytics and a Telemetry table holding precomputed signal values. Ten thousand rows aggregate in milliseconds with the Django ORM. PySpark would add a JVM, a slow cold start and a second deployment target.

Decision: ORM `aggregate` and `annotate` for sums and counts, Python `statistics` over the filtered values for medians and percentiles. No precomputed tables. The feature is called Insights, as telemetry means system monitoring and a reviewer would read it that way.

Consequences: zero extra infrastructure. The trend query is the only non-trivial one and is deferred to P1.

## D4. Single login with SimpleJWT, no Djoser, no roles

Context: the brief names one persona, the HR Manager. The first draft had an HR team as users and the manager as admin, which means RBAC, a user-management screen and permission tests. Djoser was proposed for auth, which brings registration, password reset and activation flows with no user here.

Decision: one seeded HR Manager account, JWT access and refresh via `djangorestframework-simplejwt`, every API route behind `IsAuthenticated`.

Consequences: a public URL with editable salary data is not open. Every write records `actor`, so roles later are a permissions layer, not a data migration.

## D5. One container, SQLite on a volume, hosting required

Context: the first draft planned to run the dev server locally. `runserver` is single-threaded, does not serve static files safely and is not a deployment. The brief says "fully functional deployed software", which could mean a public URL or a one-command Docker run plus the demo video.

Decision: a multi-stage Dockerfile, gunicorn plus WhiteNoise serving the API and the built SPA from one container, SQLite in WAL mode on a persistent volume, `docker compose up` for local parity. Hosted on a container host with a persistent volume, as Incubyte confirmed on 6 Oct that a live public URL is required and local-only Docker is not enough.

Consequences: one deployable, no CORS between services in production, no second database to run. SQLite's single-writer limit does not bite with one container. The ORM makes Postgres a migration later, not a rewrite.

## D6. MUI with MUI X DataGrid, Recharts, Vitest

Amended 7 Oct: the grid talks to DRF through an adapter (zero-based pages, single-column sort, filter panel disabled), not one-to-one. SPEC section 10.

Amended 8 Oct: Recharts 3.10 is installed in step 6 for the dashboard's five charts, the runtime dependency this entry names (CLAUDE.md rule 9).

Context: the brief asks for ReactJS with a component library of choice. The app is grid-heavy: the directory and the import review are both large server-driven tables.

Decision: MUI for components, MUI X DataGrid (community edition) for every grid, Recharts for charts, TanStack Query for server state, react-hook-form plus zod for forms. Tests with Vitest, React Testing Library and MSW.

Consequences: DataGrid's server-side model maps one-to-one onto DRF pagination, ordering and filter params. Ant Design was close. shadcn/ui was rejected because a headless grid would mean building pagination, sorting and column UI by hand. Vitest is Vite-native, so one config and fast runs.

## D7. USD as the reporting currency, fixed rate table

Context: employees in six currencies cannot be compared without a common unit. Live FX rates add an external dependency and make the demo non-deterministic.

Decision: amounts stored in local currency, `gross_annual_usd` and `total_cost_annual_usd` computed at write time from a seeded, editable `ExchangeRate` table, with the rate snapshotted on the record and the as-of date shown on the dashboard. `recompute_usd` refreshes after a rate edit.

Consequences: rates drift and are only as current as the table. INR was considered as the reporting currency since India is the largest population in the seed. USD was chosen as the convention reviewers will expect.

Superseded by D13: converted amounts are no longer stored.

## D8. One import template, staged import, no inline editing in v1

Context: the real-world job is getting data out of spreadsheets without corrupting it. The first draft asked for cleaning, mapping, flagging and manual overrides inside the import flow.

Decision: one template, one row per employee with a column per component code. Upload parses into staging tables with per-row validation messages. Review supports skip and unskip. Approve applies accepted rows in one transaction. Fixing a value means correcting the sheet and re-uploading. Inline cell editing and a column-mapping step are P1.

Consequences: live data never changes before approval and never partially. The review grid is a read-only grid with actions, which is the cheapest correct version. Inline editing adds per-row re-validation and a PATCH endpoint, both specified for P1.

## D9. No hard deletes, audit log on every write

Amended 7 Oct: cancel and set_rate are audited actions too, and cancellation marks a row rather than deleting it. See D20.

Context: salary data is sensitive and the HR Manager is the only editor. Mistakes need to be traceable and corrected by a new revision, never by editing history.

Decision: employees are marked exited, compensation records are superseded, nothing is deleted. Every create, update, exit, revise and import apply writes an `AuditLog` row with actor, before and after JSON, and the batch id where relevant.

Consequences: a small table that grows with every write and is cheap to query per employee. A global audit page is P1.

## D10. Scope trim, 6 Oct 2026

Context: the full spec ran to roughly 40 focused hours. The brief values engineering judgment and asks for the fastest reasonable submission.

Decision: insights cut from eleven to six (summary, by country, by department, distribution, by level, gender gap). Inline review editing, in-place correction of the current record, OpenAPI-generated TypeScript types and mypy moved out of v1. Audit shown as a plain list, not a timeline.

Consequences: roughly 10 to 12 hours saved. Everything cut is specified under P1 in `SPEC.md` and builds on the v1 patterns, so nothing is lost if time allows.

## D11. Hosting with a persistent volume

Context: Incubyte confirmed that deployed means a live public URL. The seed takes up to 60 s, so rebuilding it on every cold start would make the first request after idle very slow for a reviewer clicking the link.

Decision: one container on a host that offers a persistent volume (Fly.io or Railway), with `DATABASE_PATH` on the volume. The entrypoint seeds only when the employee table is empty. The app is served from a subdomain of nutanprabhat.dev through a CNAME to the host. The README states the URL and notes the cold-start time if the host sleeps idle instances.

Consequences: the seed runs once per deploy target. A redeploy keeps data unless `--reset` is run on purpose. Render is a fallback if the first host gives trouble, with the seed rebuilt on each deploy.

Superseded by D17: Fly.io only, no Render fallback.

## D12. Components kept and trimmed after Incubyte said gross is sufficient

Context: Incubyte replied that annual gross or current salary is sufficient and salary history is optional. Dropping `SalaryComponent` and `CompensationLine` would have saved about five hours. The brief also says the org pays people across multiple countries, and country-specific pay structure is the one thing a global salary system cannot retrofit cheaply once records exist.

Decision: keep components as data and keep effective-dated revisions. Trim to ten components: `BASE`, `TAX` and `EMPLOYER_CONTRIBUTION` global, plus two for India, one each for the UK, Germany and the Netherlands, two for Singapore. Bonus is a column on the record, see D14. Employer cost is a single undifferentiated line, which keeps total cost distinct from gross without modelling statutory schemes.

Consequences: the structure for country rules exists and is exercised by the seed, the import template and the forms. Adding a component later is a row, not a migration. The import template for India carries six amount columns, which is still readable. Sufficient sets the floor for the assessment, not the ceiling, and this is the deliberate step above it.

## D13. Exchange rates are effective-dated and conversion happens at read time

Context: D7 stored `gross_annual_usd` and a snapshotted rate on every record. If a rate changes, every stored USD value is stale until a recompute runs, and two records converted on different days disagree. There should be one source of truth for rates and none for converted amounts.

Decision: `ExchangeRate` holds `from_currency`, `to_currency`, `rate`, `effective_from` and `effective_to`. Setting a rate inserts a new row and closes the previous one in one audited transaction. No converted amount is stored anywhere. `core/fx.py` converts at read time at the rate effective on the reporting date, today by default. Reporting currency is USD by default or EUR. Rates are seeded to USD and to EUR, and any other pair routes through USD.

Consequences: a rate change is one row and takes effect everywhere at once. Point-in-time conversion is available for free. The directory's reporting-currency sort and filter become an annotation over 10k rows, which SQLite handles inside the 300 ms target but which is no longer an index read, so it is measured and recorded. Sums are aggregated per currency in SQL and multiplied by the Decimal rate in Python, so SQLite's float arithmetic never touches displayed money.

## D14. Bonus is a column on the compensation record, not a component

Context: with `code` unique on `SalaryComponent`, a per-country `BONUS` would need three rows with the same code or a uniqueness rule on (code, country) that complicates every lookup. A global `BONUS` component would put a mostly blank column in the Indian template. Neither fits what a bonus is.

Decision: `bonus_annual` on `CompensationRecord`, default 0, non-negative, included in gross. A signing or yearly bonus can go to any employee in any country, and it is one amount, so it is record data. The component table stays what it is for: country-specific pay structure.

Consequences: ten components instead of eleven. The template carries `bonus_annual` as a fixed column before the component codes. Gross = earning lines + bonus, so distribution and pay-by-level include variable pay, and base-vs-gross comparisons use the `BASE` line.

## D15. Scheduling supported, half-open intervals, a version per revision

Context: the spec review (6 Oct) showed three defects from the same root. The inclusive end date made a next-day revision fail its own check constraint. A future-dated revision became current pay the moment it was saved. Exited employees were in or out of the insights depending on which file the implementer read.

Decision: intervals are half-open, `effective_to` equals the next `effective_from`. Current means current on the reporting date, today by default. A future `effective_from` is a scheduled revision and may be cancelled until it takes effect. Exit closes the open record at `last_date` plus one day. Each record carries a `version` number per employee. `Employee.status` is derived, not stored. SPEC v2 section 4 rules 3 and 6, and F3.

Consequences: HR can enter next April's raise in March. Point-in-time reporting comes for free through `on=`. The constraint and the partial unique index stay as written. The directory, insights and exports all use one date predicate.

## D16. Stack pinned to the latest that deploys, on Python 3.14

Context: the review found Django 5.0 out of support, React 18 pinning an old router, MSW on a new major with changed imports, and no backend lock file. The owner's machine runs Python 3.14.

Decision: Python 3.14, Django 6.1, DRF 3.18, SimpleJWT 5.5 with the blacklist app, Node 26, React 19, react-router 8, TypeScript 6.0, Vite 8, Vitest 5, MUI 9, MUI X 9, Recharts 3, TanStack Query 5, MSW 3.0. `uv.lock` for the backend. drf-spectacular dropped: types are hand-written and the schema sat behind auth for nobody. SPEC section 1.

Django 6.1 over 5.2 LTS, corrected 7 Oct: the first reason recorded here ("the only line that supports 3.14") was wrong, 5.2.8 added 3.14 support. The reason that holds is that 5.2 goes to extended support in April 2027 and 6.1 is the current mainstream line, and the two behavioural changes that matter (`CheckConstraint(condition=)`, `BigAutoField` default) are what the code would use anyway. The review ran the whole backend pin set together on 3.14.3 and it works.

Runtime dependencies and why: django-filter, the standard `FilterSet` for the directory's twelve filters. django-cors-headers, one line of CORS for the single origin. whitenoise, static files from the app container with no second service. openpyxl, the only maintained pure-Python xlsx reader and writer. defusedxml, openpyxl's own recommendation against XML bombs in uploads. gunicorn, the WSGI server. SimpleJWT, stateless auth with a blacklist app for logout. Faker, synthetic names and emails for the seed, in the main group because the seed runs in production on first boot.

Consequences: SimpleJWT and gunicorn declare support only to 3.13. Both are pure Python and CI on 3.14 verifies them on day one. The fallback is Python 3.13, one line in two files. Code written from memory for older majors will be caught by the pinned versions, not by a reviewer later.

## D17. Deploy first, on Fly.io

Context: the live URL is the client's one hard requirement and the review found it scheduled last, with a persistence model that contradicted itself and a static-serving claim that was wrong.

Decision: Fly.io on a paid plan, owner pays, app `acme-salary`, region `sin` (the account could not place a machine in `bom`), one shared-CPU machine with 1 GB (512 MB left no headroom for a 10,000-row import in flight), one 1 GB volume, custom domain `acme.nutanprabhat.dev`, deployed in step 1 as an empty skeleton with TLS. A Django catch-all view serves the SPA. gunicorn binds explicitly. The seed runs only when the Employee table is empty, inside one transaction. One machine stays running so a reviewer never waits on a cold start. SPEC section 14.

Consequences: the hard requirement is proven before any feature exists and every later step deploys onto a working target. One volume with daily snapshots is the accepted risk for v1.

## D18. Scope kept beyond the client's examples, with reasons

Context: the review listed six things that go past Incubyte's reply: the by-level and gender-gap insights, EUR reporting, insight exports in three formats, the OpenAPI schema and Django admin.

Decision: by-level stays, pay by level is the first question any compensation review asks. The gender gap stays, labelled unadjusted, with no gap planted in the seed, so the chart shows what the data shows. EUR stays, it is one row per currency in a table that already exists. Insight exports stay, they are the same writers as the directory export. The schema and Django admin go. Admin bypasses every rule in CLAUDE.md and is not installed at all.

Consequences: the dashboard answers six questions, not four, at a cost of two queries and two charts. Nothing in the product edits data outside the services.

## D19. Full scope for an 8 October morning submission

Context: with the review in hand the owner weighed cutting components, history and two insights to ship the same day, against building the spec as reviewed and submitting the next morning.

Decision: full scope, submission the morning of 8 October 2026 IST so the reviewers see it first thing. SPEC v2 folds the review's outcomes into one document, and this log keeps the history.

Consequences: roughly 30 to 35 focused hours against a fixed clock, with the P1 list as the release valve. If a step slips, the order of what shrinks is unchanged: export and hardening first, nothing from the data layer, import or deployment.

## D20. No row of pay data is ever deleted, cancellation is a mark

Context: SPEC v2 made cancelling a scheduled revision the one allowed delete, as a record that was never in effect has no history to protect. The 7 Oct review showed that this contradicted rule 6 in CLAUDE.md and two reviewer agents, so every cancel would have raised a Blocker. The owner's position is stricter and simpler: a cancelled raise is itself a fact HR may need to show later.

Decision: `CompensationRecord` gets `cancelled_at` and `cancelled_by`. Cancel sets them and removes nothing. Cancelled rows are excluded from every current-or-latest query and the partial unique index, and shown greyed in history. `DELETE /compensation/{id}/` stays as the verb because it is the natural HTTP shape, and the service marks. The only operations that remove rows are `seed_data --reset` and `reset_demo`, run on the owner's command against the demo database, and they also clear `sqlite_sequence` so a reseed is byte-identical to a fresh one.

Consequences: rule 6 reads as an absolute. The agents get one exception for the two reset commands. Every query that means "the records that count" carries `cancelled_at IS NULL`, which is one extra predicate in the record selection the services already own.

## D21. Refresh token in localStorage, not an httpOnly cookie

Context: the review asked why. The usual answer for a browser app is an httpOnly cookie, which JavaScript cannot read.

Decision: the access token lives in memory and the 12-hour refresh token in `localStorage`. The app is one SPA on one origin with one user. A cookie would bring CSRF protection on every mutating call and a CORS exception for the refresh endpoint, for a threat model where the attacker already runs script on the page and could call the API directly for 30 minutes anyway.

Revised at the step 3 close, after the security review showed that SimpleJWT resets the refresh token's expiry on every rotation, so a session never ended while it was used and a stolen token bought a fresh one at each use. Rotation with a blacklist does not limit a stolen token to one use; one use buys a fresh token. Two rules now hold, both in `accounts/services.py` behind `SessionRefreshSerializer` (SPEC F8): a rotated token keeps the original `exp`, so every session ends 12 hours after login and the access token never outlives it; and a refresh token presented after it was rotated out or logged out revokes every refresh token of its user and answers 401, the reuse detection of RFC 9700 section 4.14. The user comes from the blacklisted `OutstandingToken` row that matches the presented string, never from the unverified payload. `python manage.py revoke_sessions <email>` runs the same revoke-all by hand. Two browser tabs refreshing at once would trip the reuse rule, so the frontend serialises refreshes across tabs with `navigator.locks` and reads the stored token inside the lock.

Consequences: a cross-site-scripting bug exposes the refresh token until the session ends, at most 12 hours, and a stolen token is revoked the moment the legitimate browser or the thief refreshes with the older copy, or by the command. The HR Manager signs in again at most twice a day. There is no third-party script on the page and MUI escapes rendered values.

## D22. Exchange rates are monthly, two months seeded, earliest rate before that

Context: SPEC v2 seeded one rate per pair dated 1 October 2026 and returned 422 for any earlier date, which made point-in-time reporting fail for every date the seeded history covers. Seeding eleven years of invented FX was the alternative.

Decision: rates change on the first of a month only, so a rate row is a month. The seed carries September and October 2026, sixteen rows. A date before the earliest row uses the earliest rate. `set_exchange_rate` refuses dates that are not the first of a month, dates on or before the latest row for the pair, and a second rate for the same month without `--replace`. The dashboard shows the month in use.

Consequences: no 422 anywhere. The history of a rate is a short readable table. Point-in-time before September 2026 is approximate and says so by the month label.

## D23. Full scope held, with a stop time

Context: the 7 Oct review was right that a 30 to 35 hour estimate does not fit the hours left before the morning of 8 October. The owner chose to keep the full scope and decide at the end what to do if a step runs over.

Decision: build in the order of PLAN.md with no cuts planned. The owner takes the decision on any step that is not green by its planned time, with the spec's release valve (export and hardening shrink first) as the default and nothing from data, import, directory or deployment ever cut. PLAN.md carries per-step hours so that decision is made against a number, not a feeling.

Consequences: the risk is accepted knowingly and the record shows it. If the submission slips past the morning, it slips with a working deployed core, not an unfinished one.

## D24. A refused approve is always a 409, and the batch stays usable

Context: SPEC F2 re-runs the date and duplicate rules inside the approve transaction but does not say what happens when a row fails them, nor which status an exception during apply returns. The design proposed 409 for the first case and 500 for the second.

Decision: a re-validation failure rolls back, re-marks those rows as errors with the new messages, leaves the batch in review and returns 409 with the rows. Any other exception marks the batch failed with `error_summary`, keeps the rows as F2 says, and also returns 409 with `detail` and `error_summary`. DESIGN sections 1.0, 1.5 and 2.

Consequences: the client handles every refused approve one way, refetch the batch and show the detail. No deliberate 500 leaves the API. Owner's answers to DESIGN questions 1 and 13.

## D25. The small-group rule covers every figure in by-level

Context: SPEC section 9's general rule nulls mean, median and percentiles for any group under five people, while the by-level row said only min and max. The design asked which one holds.

Decision: the general rule. A level with fewer than five people publishes headcount only. SPEC section 9 by-level row corrected in v2.2.

Consequences: no level can show one person's pay. Owner's answer to DESIGN question 2.

Superseded in part by D59: a level shows its figures only from twenty people, and they run from p10 to p90, never min or max.

## D26. Import exits write one exit entry, and a first record cannot be cancelled

Context: a row whose `last_date` appears is an identity change in F1's table but runs the exit service, and F3 as written would let a future joiner's only record be cancelled, leaving no record at all.

Decision: such a row writes one `exit` entry on the employee carrying any identity changes in the same before and after, and counts in `updated_rows`. Cancelling version 1 returns 409 `the first record cannot be cancelled`. DESIGN sections 1.4 and 1.5.

Consequences: one entry per entity holds for imports too. A future joiner's wrong pay is fixed by exit and re-create in v1, or by the P1 in-place correction. Owner's answers to DESIGN questions 3 and 4.

Amended 7 Oct: an exit dated before the employee's only record starts, a record never current, cancels that record. Cancelling version 1 on its own is still a 409. See D50.

## D27. API conventions the spec left open

Context: DESIGN questions 5, 6, 7, 10 and 11 proposed defaults for the JSON export shape, money encoding, warnings on writes, percentage precision and upload content types.

Decision: the JSON export is `{generated_at, filters, rows: [{snake_case key: value}]}` and file names carry a UTC stamp. Money is a two-decimal string everywhere in the API. Create and revise responses carry `warnings`. `share_pct` and `gap_pct` have one decimal. `application/octet-stream` is accepted when the extension is `.xlsx` or `.csv`.

Consequences: frontend money types are strings and convert to numbers only for chart geometry. The spec-checker has a source here for each shape.

Amended 8 Oct: a `.csv` is also taken as `text/csv`, `application/csv`, `text/plain` and `application/vnd.ms-excel`, which Windows browsers send for it when Excel is installed. A request with no content type is read as `application/octet-stream`.

## D28. Rate month label, light theme, sample data

Context: DESIGN questions 9, 12 and 14.

Decision: the dashboard's rate month is the most recent `effective_from` among the rates feeding the reporting currency, and `/meta/exchange-rates/` lists each pair's own date. The UI ships a light theme only. `sample-data/` holds `acme-sample-50.xlsx` and the same rows as CSV, from `make_import_file --new 20 --raises 24 --errors 6`.

Consequences: one palette to validate. The sample files are regenerated whenever the seed or the planted error list changes, in the same commit.

Amended 8 Oct: the command is `make_import_file --raises 30 --new 20 --errors 6`. The errors are planted in rows already counted, so the old one wrote 44 rows, not 50. See D56.

## D29. The health check sends the custom domain as Host, and DNS is a CNAME only

Context: Fly's checker sends the machine's internal address as `Host`, which `ALLOWED_HOSTS` rejects with 400, so the check would never pass. SPEC section 14 also asked for a CNAME and an AAAA on one name, which DNS does not allow.

Decision: `fly.toml` carries `[http_service.checks.headers] Host = "acme.nutanprabhat.dev"` from step 1. The Cloudflare record is a CNAME to `acme-salary.fly.dev` with the proxy off. SPEC section 14 corrected in v2.2.

Consequences: the check exercises the same host rule as real traffic. The volume, secrets and certificate (verified on IPv4 and IPv6) were in place on 7 October before step 1. Owner's answer to DESIGN question 8.

## D30. Deploy at every page step, step 1 closes on the domain, the slow test stays out of the hook

Context: PLAN questions 1 to 3, and the plan's clock re-anchored to a 12:30 IST start on 7 October.

Decision: `fly deploy` runs at the close of every step that adds a page (1, 3, 4, 5, 6, 7 and 9). Step 1 closes with the custom domain live. The 500-employee determinism test stays marked `slow` and runs in `/finish-step` and CI, not in the commit hook.

Consequences: the live URL always shows the latest page at about five minutes per deploy. Commits stay fast. At the plan's estimates steps 1 to 4 close by 06:00 on 8 October and the rest by 20:30, which D23 accepts knowingly.

## D31. Step 1 deploy: the health-check grace is 60 s, one volume, SQLite confirmed

Context: the first `fly deploy` built the image but could not place a 1 GB machine on the host holding the volume (`insufficient resources to create new machine with existing volume 'data'`), and `fly config validate` warned that an HTTP service check grace period above one minute is lowered to one minute, so SPEC section 14's 300 s could not take effect.

Decision: a second empty volume named `data` was created in `sin` and the machine launched on its host, as Fly's own message suggests, and the first, never-attached volume was destroyed so the app has exactly one machine and one volume. `fly.toml` says `grace_period = '60s'` to match the cap, SPEC section 14 says so, and there is no top-level `[checks]` entry. A failed check does not restart the machine, it only stops routing and makes `fly deploy` wait, so the seeded first boot, which happens once per volume, runs its deploy with `--wait-timeout 10m` and records the measured boot in PERFORMANCE. The live image runs SQLite 3.46.1 on Debian 13 with Python 3.14.8, above Django 6.1's 3.37 minimum.

Consequences: later boots skip the seed and were healthy 6 s after init. The seed has no health-check budget to fit, only the deploy's wait. Owner's answer to the step 1 spec-checker question.

## D32. whitenoise[brotli] for the pre-compressed bundle

Context: SPEC section 14 ships assets gzip and brotli, and WhiteNoise's compressor writes `.br` files only when the `brotli` package is installed. Rule 9 asks for a line per runtime dependency.

Decision: the `whitenoise[brotli]` extra, which adds the `brotli` codec and nothing else. It landed in commit ed03445 and this line in the step's closing commit, one commit late.

Consequences: `/assets/*.js` on the live site answers `Content-Encoding: br` to a brotli-capable client (215 KB to 57 KB) and gzip otherwise.

## D33. Lookups and rates are seed data, not migrations, and a reset clears sqlite_sequence

Context: the six countries, twelve departments, ten components and sixteen rates could have been data migrations. The determinism scope (SPEC section 11 rule 8) includes those tables, and reset_demo has to rebuild them byte for byte.

Decision: `seed/lookups.py` creates them idempotently through `update_or_create` and `set_exchange_rate`, and `seed_data` and the test fixtures both call it. `--reset` deletes the business tables in dependency order through the ORM and then runs one parameterised `DELETE FROM sqlite_sequence WHERE name = %s` per table, the only raw SQL in the project.

Consequences: migrations stay schema-only. A reseed restarts ids at 1, which the determinism test checks after `--reset`. The sixteen `set_rate` audit rows are part of the seed and of the hash.

## D34. Audit snapshots are plain functions that mirror the serializers

Context: SPEC F7 says before and after match the detail serializer. The seed writes about 46,000 audit rows, and a DRF serializer per row would eat the 60 s budget.

Decision: `audit.snapshot_employee` and `audit.snapshot_record` build the dicts directly, taking in-memory lines for bulk writes, rendered JSON-safe by `core.money.render`. A test in step 4 asserts they equal the serializer output minus the request-dependent keys.

Consequences: two places describe the shape, kept equal by a test. The 10,000-employee seed measured 10.0 s on the laptop.

Step 4, at the owner's direction: the serializers follow the snapshots, so the seeded audit rows and the golden hash stand. A line's `component` is its code, the record carries `employee`, and datetimes are written `+00:00`. The client reads component names and kinds from `/meta/components/`. `tests/audit/test_snapshots.py` holds the record and employee shapes equal.

## D35. Seed parameters the spec left open

Context: SPEC section 11 gives shares, anchors and multipliers but not rounding, jitter or name sources.

Decision: base is rounded to the nearest 100 units of local currency, every component share is multiplied by a per-employee jitter drawn uniformly between 0.95 and 1.05, TAX is a share of gross by level band, amounts are whole units, the bonus share of base is drawn once per employee, raises compound, and the history keeps the joining record plus the three most recent raises with the joining record running until the first kept raise. Faker has no Singapore locale, so Singapore names come from en_US. Emails are `first.last.N@acme.example` folded to ASCII.

Consequences: any change here changes the golden hash, and the commit that changes it regenerates `tests/seed/golden.txt` and says so.

## D36. Readings made while building the validators and services

Context: five points the spec is silent on surfaced while writing step 2.

Decision: an import matches `department` by code or by name, case-insensitively, because the template is filled by hand. A changed `last_date` on an exited employee is the exit service's "already exited" conflict as a row error. For an employee with a `last_date`, a revision dated after it is a 409 (`no revision after the exit on <date>`) and one dated on or before it is allowed and ends at `last_date + 1`, the same rule through the API, the import and the seed; the owner confirmed this at the step 2 close and it is in SPEC F3, section 7 and section 8 (v2.3). A cancel that leaves no later live record re-chains the previous record to `last_date + 1` when the employee has one, so a scheduled exit never reopens pay; the owner found the bug at the step 2 close and SPEC F3 says so. In bulk, a row that changes identity fields or sets `last_date` as well as amounts writes its `update` or `exit` entry on the employee and then the `revise` entry on the record, the same order as the API path, as the owner decided; the batch counts do not change and SPEC F2's audit count carries the extra term. The parser's column constants live in `apps/imports/parser.py` from step 2 because `make_import_file` needs them, and the `timing` command's seed case lands in step 2 because `/perf-timing` asks for it at the close of any step that touches the seed.

Consequences: one entry per entity written holds everywhere. The step 5 fixture includes one promotion row and one exit-with-raise row. The seed only creates, so neither answer changed the golden hash.

## D37. The seed validates SEED_ADMIN_PASSWORD

Context: the step 1 security review noted that `AUTH_PASSWORD_VALIDATORS` applied to nothing, since the only account is created by the seed. SPEC section 11 requires the variable in production and defaults it to `change-me` in development, and says nothing about strength.

Decision: `seed_data` runs Django's `validate_password` on `SEED_ADMIN_PASSWORD` before writing anything: minimum length eight, not in the common-password list, not all digits. The minimum stays at eight so the development default is valid. The live secret was checked against the same validators before step 3's deploy.

Consequences: a weak owner-chosen password fails the first boot at the entrypoint with a clear `CommandError` instead of fronting every salary row. The step 1 guard in `prod.py` already refuses the placeholders.

## D38. Content-Security-Policy from Django 6.1's own middleware

Context: the owner chose the directives at the step 1 close and PLAN step 3 carries them; the spec itself is silent on a policy. Django 6.1 ships `ContentSecurityPolicyMiddleware`, so the alternative, `django-csp`, would be one more dependency for the same header.

Decision: `SECURE_CSP` in `settings/base.py` with `default-src 'self'`, `script-src 'self'`, `connect-src 'self'`, `img-src 'self' data:`, `font-src 'self'`, `style-src 'self' 'unsafe-inline'`, `frame-ancestors 'none'`, `object-src 'none'`, and, added at the step 3 close on the security review's advice, `base-uri 'none'` and `form-action 'self'`, which do not fall back to `default-src`. `style-src` needs `'unsafe-inline'` because MUI's Emotion injects style tags at runtime. The fonts are bundled by Vite and served from `/assets/`, so `font-src 'self'` holds. `tests/core/test_security_headers.py` asserts the header on an API response, the health check and the SPA shell.

Consequences: an injected script cannot run and the page cannot be framed. A nonce for `style-src` would need Emotion's cache configured per response, and the SPA shell is one static file, so `'unsafe-inline'` stays until the app renders HTML per request, which v1 does not.

## D39. Frontend runtime packages added in step 3

Context: rule 9 asks for a line per runtime dependency. SPEC section 1 names React, react-router, MUI, MUI X, TanStack Query, react-hook-form and zod. Five packages installed with them are not named there.

Decision: `@fontsource/ibm-plex-sans` bundles IBM Plex Sans 400, 500 and 600 (DESIGN section 7) so the font is served from the app's own origin under `font-src 'self'` (D38) instead of a Google Fonts request. `@mui/icons-material` supplies the navigation and action icons as React components, MUI's own icon package. `@emotion/react` and `@emotion/styled` are MUI 9's required peer dependencies, its styling engine. `@hookform/resolvers` is the bridge that lets react-hook-form run a zod schema, published by react-hook-form itself. `@mui/x-data-grid` is in SPEC section 1 and lands with the grid in the next commit.

Consequences: no third-party font or icon request at runtime, so the CSP stays at `'self'`. The bundle grows by the three font files and the icons that are imported one by one.

## D40. Readings made while building the directory and the shell

Context: three places where SPEC and DESIGN leave a small choice open came up in step 3, none of them worth stopping the step for. The alternatives were a 400, a lookup endpoint and an empty page.

Decision: `currency=local` on `GET /employees/{id}/` resolves to that employee's own currency, the one-country case of the SPEC section 8 rule, instead of answering 400 because the detail has no country filter. The directory's designation filter is a text field matched exactly but case-insensitively, because titles have no lookup endpoint and section 8 lists none. The start page `/` redirects to `/employees` until the dashboard lands in step 6, and Dashboard and Imports join the navigation with their steps, so the shell never links to a page that does not exist yet.

Consequences: the detail page in step 4 can show local figures without a second request. A designation lookup under `/meta/` is not in the spec and would be a later addition. The redirect is removed in step 6. The directory's row click goes to `/employees/:id`, which is the not-found page until step 4 builds the detail; the navigation column itself only links to built pages. D63 replaces the row click with a pencil button.

## D41. Two hardenings from the step 3 security review

Context: the review found that the login throttle keyed on the full IPv6 address, which a client can change per request within its /64, and that API responses carried no `Cache-Control`, so a browser could keep salary pages in its disk cache. The alternatives were a per-account bucket, which lets an attacker lock the HR Manager out, and a `Cache-Control` on every response, which would also stop WhiteNoise's immutable asset caching.

Decision: `LoginRateThrottle` in `apps/accounts/views.py` reduces an IPv6 client to its /64 before counting, and `apps/core/middleware.NoStoreApiMiddleware` sets `Cache-Control: no-store` on `/api/` responses only. The same review's 500s on an out-of-range `level` and a search of more than ten words became 400s through `ChoiceInFilter` and `BoundedSearchFilter` in `apps/core/filters.py`.

Consequences: a /64 behind one NAT or one household shares the five attempts a minute, which is the intent. Pages and assets keep their caching. The session-lifetime question the review raised is the owner's call and is not changed here.

## D42. Plan acceptance names criteria, and F3's insights half closes in step 6

Context: at the start of step 4 the plan's SPEC line numbers had drifted with v2.3 and v2.4, so step 4's "379 to 382" covered the P1 `POST /meta/exchange-rates/` row. F3's scheduled-revision and exit criteria also name insights, which arrive in step 6. Asked "replace the numbers with names, renumber, or leave them?" and "close the insights half in step 6?", the owner chose names and step 6. Renumbering was the alternative.

Decision: PLAN steps 4 to 9 cite criteria by name and section 8 rows by route path. Step 4 closes F3 and F7 through the API. Step 6 adds two named tests, the DESIGN 9 fixture's U1 under `on=2027-01-01` and an exited employee counted with `on=` its `last_date` and gone the day after. SPEC's title reads v2.4 to match its preamble. The audit list is paginated as DESIGN 1.3 and section 8 say.

Consequences: SPEC edits no longer break the plan's references. The plan's scope and order are unchanged, so its approval stands. Steps 1 to 3 keep their line numbers as the record of what they closed.

Amended 7 Oct: the employee page's audit tab asks for one page of 100 entries, newest first, and says "Showing the latest 100 of N changes" when there are more. Reading further back waits for the P1 global audit page.

## D43. A cancelled revision releases its date

Context: the unique `(employee, effective_from)` constraint counted cancelled rows while the validators compared live ones only, so cancelling a scheduled 1 April raise and entering it again for 1 April was a 500. Asked whether to accept that or answer 400, the owner chose to accept it. Cancel and re-enter is the only correction path for a scheduled revision in v1, and 1 April is the date most likely to collide.

Decision: the constraint covers live rows only (`compensation_record_live_effective_from`, `WHERE cancelled_at IS NULL`, migration 0002). `(employee, version)` stays unique across every row, so a number is never reused. History breaks a same-date tie by version. SPEC section 5 and DESIGN 1.4 and 3 say so.

Consequences: a date can carry any number of cancelled rows and one live row. Two live rows on one date are still refused by the database, and a test holds that. The step 5 import gets the same behaviour with no extra code.

## D44. Every database constraint answers 400 or 409 before save

Context: `POST /employees/` with an `employee_code` already in use passed validation and failed on save, the second constraint the validators did not cover. The owner chose a 400 on the field the client sent, the same kind of error as `email already belongs to`, and asked for every constraint to be checked against the validators. A 409 stays for state that blocks an action.

Decision: `check_code_available` answers `employee_code ACME-000017 already exists; omit employee_code to have one assigned` on a create, before the other rules. API messages about the code use the request field `employee_code`, not the template column `EmployeeID`. The single-row services read and validate inside their transaction, so SQLite's IMMEDIATE lock covers the check and a double submit is a 400 or 409, not an IntegrityError. Every other constraint already had a rule or is assigned by a service, and exchange rates already validated inside their transaction.

Consequences: no API write reaches a constraint unchecked. Two gaps belong to step 5. A blank `full_name`, `designation` or `joining_date` cell on an import row has no rule yet, and SQLite does not enforce column lengths, so only the API serializers cap them.

Superseded in part by D48: `check_code_available` and the `EmployeeID` keying are gone, because neither code is ever set through the API.

## D45. joining_date cannot move past the first record

Context: a PATCH could move `joining_date` after the first record's `effective_from`, leaving pay dated before the employee joined. Section 7 checked only the reverse. The owner chose a 400 over allowing it.

Decision: `check_joining_before_first_record` answers `joining_date is after the first record (effective 2020-01-01)` for an existing employee, through the API now and the step 5 import. SPEC section 7 has the row.

Consequences: a joining date entered too early cannot be moved past the first record in v1, including a future joiner whose start date slips, because version 1 cannot be cancelled (D26) and in-place correction is P1. Exit and re-create covers it until then, as D26 already says. The recipe's import test for the rule lands with the parser in step 5.

## D46. Readings made while building the compensation API

Context: four points the spec leaves open came up while writing the step 4 endpoints. None was worth stopping the step for.

Decision: input serializers check shape and types only, so `gender`, `level`, `email` and the country are plain fields and the validators answer with SPEC section 7's messages. A component listed twice in `lines` is a 400 `BASE appears twice in lines`, the case the owner named in the constraint audit (D44). DRF 3.18 reports a bad list item as an object keyed by its index (`{"lines": {"1": {...}}}`), and the client maps the index to the line code it sent, as it would a list. `PUT /employees/{id}/` is not offered, because section 8 lists PATCH only.

Consequences: an API client reads the same message text an import row would. The frontend's `applyServerErrors` reads both the list and the index-keyed shapes, so a DRF setting change cannot drop a message.

Amended 7 Oct: amounts are the exception. The input `DecimalField` answers with DRF's own `A valid number is required.` and `Ensure that there are no more than 2 decimal places.` before the validators run. The duplicate-component text now lives in `messages.py` with the rest.

Amended 7 Oct: a PATCH that changes nothing is not a write. An empty body, or one that repeats the stored values, is saved nowhere and writes no `update` entry, so section 4 rule 7 never records a change that did not happen.

## D47. Readings made while building the employee page

Context: the detail wireframe in DESIGN 8 showed a reporting-currency column on every line, but the record serializer converts the totals only and rule 3 keeps conversion in `core/fx.py`. Two smaller points were open: how a period reads, and what follows a successful write.

Decision: lines show in the employee's currency with a monthly column, and gross, net and total cost show in both currencies. History shows a period by its last day, `effective_to` minus one, because people read periods inclusively while the API's end is exclusive. Every write ends with a short status message in the words of its button ("Revision v3 cancelled."). A server message that no field holds is listed in the form's error summary under the key it came with, as the owner asked. The revision form asks for its date before sending, and the API keeps section 7's message for any other client. DESIGN 8's wireframe now shows the page as built.

Consequences: no conversion runs in the browser. A per-line conversion would need `converted.lines` from the API, a small later addition if the owner wants it.

## D48. The employee code is the id, and legacy_code carries the sheet's code

Context: a create naming `ACME-999999` broke code assignment for every later create, and a stored `ACME-NNNNNN` code could collide, overflow or be chosen by a client. The owner chose to make the code the primary key and keep the legacy system's code beside it.

Decision: the employee code is `ACME-<id>` with no leading zeros, assigned by the database on every insert and never stored. `Employee.legacy_code` holds the sheet's code, set once when an import creates the employee and never changed. It is NULL for an employee created in the app, unique, and never an empty string, and migration 0002 moves the old codes into it. The template's first column is `legacy_code`, and the old `EmployeeID` headers are read as it only when a sheet has none. The API refuses either code in a create or an edit. Search reads an ACME code as a number and a `legacy_code` in any case, while import matching stays exact and case-sensitive. The seed numbers employees in joining order and gives each an `HR-` code. This supersedes the `ACME-NNNNNN` code of SPEC v2.5 and D44's `check_code_available`.

Consequences: no client or sheet chooses an employee's number, so assignment cannot collide or overflow. An employee created in the app is never reached by a sheet, because the import serves the legacy system's employees only. The golden hash changed, and the live database needs `reset_demo` after the deploy, on the owner's word.

Amended 7 Oct: migration `employees.0002_legacy_code` is one-way. Reversing it on a database with employees fails on the restored NOT NULL `employee_code`, and the `reset_demo` that follows the deploy makes a way back unnecessary.

## D49. Every amount is bounded, so no total can overflow

Context: the security review found that each line fits `Decimal(14, 2)` but their sum need not. A BASE of 999,999,999,999 with a bonus saved a gross that every later read failed to load, taking down that employee's pages, the directory and the country's medians. Asked for the rule's wording, the owner chose bounds on each amount over a cap on the totals.

Decision: every line and `bonus_annual` must be between 0 and 9,999,999,999.99 (`HRA must be at most 9,999,999,999.99, got 12,000,000,000.00`), and a given BASE must be at least 10 (`BASE must be at least 10.00, got 5.00`), while a blank BASE stays `BASE is required`. A bonus above BASE and a deduction above BASE are warnings. Errors are for impossible values, warnings for unusual ones. SPEC section 7 has the rows.

Consequences: with ten integer digits per amount, a total stays inside its column for any sensible number of components, and a test derives that bound from the component counts and the column's digits, so adding a component cannot silently break it. The API serializer still caps each field at 14 digits, so a larger value gets DRF's own message first.

## D50. An exit before pay starts cancels the only record

Context: an employee created with `effective_from` after `joining_date` could not be exited before that date. The exit answered 409 naming the record, and cancelling version 1 answered 409 too (D26). The alternatives were a 400 with an explanation, which left them stuck, and refusing a first record dated after joining, which is not enough while D45 lets `joining_date` move earlier.

Decision: when the record after `last_date` is the employee's only live record and has never been current, the exit cancels it instead of closing it, in `exit_employee` and `bulk_apply` alike, and writes `exit` then `cancel`. A first record that has been current keeps the 400. While later revisions are scheduled, the 409 names one of them, not version 1. SPEC section 4 rule 6 and F3.

Consequences: such an employee has no live record. The directory lists them with no record, the detail says they left before pay started, and the history keeps the cancelled row. Step 6's insight population must skip employees with no live record, under `include_exited` too.

## D51. Record bodies: an optional bonus and note, and capped strings

Context: SPEC section 8 listed `bonus_annual` in both bodies and `note` in the revision body without `?`, while DESIGN 1.3 and the serializers treated both as optional. Asked, the owner chose optional. The security review also found `note` unbounded: a 2,000,000-character note was stored, copied into two audit snapshots and sent with every history. Lookup values such as `department` came back in their 400s at any length.

Decision: `bonus_annual` and `note` are optional, a missing bonus is zero and a missing note is empty. The serializers cap `note` at 1,000 characters, `department`, `country_code`, `gender` and a line's `component` at 64, and `lines` at 20 items, with DRF's own message. The forms cap the note too.

Consequences: no request stores or echoes an unbounded string. The caps are shape checks, so the validators are unchanged and `bulk_apply` does not apply them. The step 5 parser must cap the same cells, and `legacy_code` with `check_legacy_code`, before rows reach it.

## D52. Owner's answers at the step 4 close

Context: the second review pass found four places where the documents disagreed with each other or with what step 4 built. The questions were "may the last day fall on the day the current record starts?", "should PLAN name F3's eighth criterion?", "should F2's audit count include the cancel of an exit before pay starts?" and "should SPEC say the API answers a malformed amount in DRF's words?"

Decision: the same day is allowed, so SPEC section 7's exit row reads "before", as F3 and section 4 rule 6 do. PLAN step 4 names F3's eight criteria, and its approval line stands as it did for 338c015. F2's count adds one entry per exit row whose only record had not started (D50). SPEC section 8 names the API's own amount messages (D46).

Consequences: SPEC is v2.8. None of the four needed a code change. Step 5's approve test counts the extra `cancel`.

## D53. Every date is on or before 2100-12-31

Context: the step 4 security review found that an exit on 9999-12-31 overflowed `last_date + 1` into a 500. Nothing was written, but the API answered with a server error. Step 4 deferred it to the step 5 parser. The owner pulled it forward into the shared validators, so the API and the seed are covered as well as the import (CLAUDE.md rule 4).

Decision: `check_dates_in_range` refuses a `joining_date`, `last_date` or `effective_from` after 2100-12-31 in every scope (import, identity, record, exit): `last_date must be on or before 2100-12-31, got 9999-12-31`. It runs with the structure rules, so an exit answers 400 before any date arithmetic. SPEC section 7 has the row, v2.9.

Consequences: no stored date is near the end of the calendar, so every `+ 1 day` in the services exists. A real date past 2100 would need this ceiling raised in one constant, `validators.DATE_MAX`.

## D54. The import header: one legacy code column, each column once

Context: SPEC F1 reads the old code headers (`EmployeeID`, `Employee Code`, `Emp ID`, `employee_code`) as `legacy_code` when a sheet has none, but said nothing of a sheet with two of them, or with any template column twice. Asked before step 5, the owner chose to refuse both, and to keep `employee_code` as an alias although the app now uses that name for `ACME-<id>` (D48).

Decision: two or more old code headers and no `legacy_code` column refuse the upload with `EmployeeID and Emp ID could both be the legacy code; rename the right one to legacy_code`, and three or more say `could all be`. A template column given twice refuses it with `email appears twice in the header; remove one`. `employee_code` stays an alias. It normalises to the same header as `Employee Code`, which legacy sheets use, so dropping one would drop both.

Consequences: no value is read from a column the user did not mean. Keeping the alias is safe. An export from the app always carries a `legacy_code` column, which wins over `employee_code`, and a sheet whose `ACME-<id>` column is read as legacy codes fails the email check row by row, so it never matches the wrong employee. SPEC F1 and section 7.

## D55. A sheet cell longer than its column is a row error

Context: D51 capped the API's strings, but `bulk_apply` applies no caps and SQLite does not enforce VARCHAR lengths, so a 10,000-character `full_name` in a sheet would have been stored as it was. The lookup rules also repeat an unknown value in their message. Asked before step 5, the owner chose an error at each column's own length over cutting the value or leaving it.

Decision: `check_text_lengths` refuses a `full_name`, `email`, `designation`, `department`, `country_code` or `gender` longer than 120, 254, 80, 64, 64 and 64 characters (`full_name is longer than 120 characters`), in the import and identity scopes. The country and department rules skip a value the length rule has refused, so no message repeats it back. SPEC section 7.

Consequences: no import stores or echoes an unbounded string. An API body still meets DRF's caps first (D51), so in practice only sheets show these messages. The staged row's search columns are cut to their length, and `raw` keeps the cell as typed.

Amended 8 Oct: `raw` keeps the cell as typed up to 256 characters, and a message repeats at most 64 characters of a value. See D56.

## D56. After the step 5 review: blank cells, long cells and what an upload may cost

Context: the step 5 reviewers found three gaps. A blank `full_name`, `designation` or `joining_date` staged as valid, then failed the whole approve on a NOT NULL constraint. A 168 KB sheet could store 606 MB of cell text. A crafted .xlsx of a few KB could hang a request thread, or take openpyxl past the 1 GB VM. Asked after the review, the owner chose each limit below and its words. Cutting cells silently and leaving the gaps open were the alternatives. A later probe showed that the elements openpyxl builds into objects cost far more than the rest, and the owner added a second count and one upload at a time.

Decision: a blank `full_name`, `email`, `department`, `designation`, `level`, `country_code`, `gender` or `joining_date` is `{field} is required`, and the other rules on that cell run only when it holds a value (SPEC section 7). A staged row keeps at most 256 characters of a cell in `raw` and `normalized`, and `msg()` repeats at most 64 characters of a value, each cut ending in `…`. Before openpyxl opens an .xlsx, `preflight_xlsx` refuses one whose parts unpack past 50 MB. It then streams every part through expat, building no tree, and refuses a row numbered past 1,048,576, a cell past column 200, more than 2,000,000 elements in all, and more than 300,000 that are not cell contents or shared strings (`row`, `c`, `v`, `f`, `is`, `t`, `r`, `si`), which openpyxl builds into objects. The last two say `file is too big to read`, with no word of XML, at the owner's request. One upload is read at a time, and a second one meanwhile answers 409 `another file is being read; try again in a moment`. A .csv row is held to the same 200 cells, which also keeps every column letter within ZZZ. Each is a 400 with no batch (SPEC section 8). The sample is `make_import_file --raises 30 --new 20 --errors 6`, D28's mix in 50 rows. SPEC section 8's row-limit example is a list, as the API answers.

Consequences: a full 10,000-row template has 377,122 elements, 339 of them outside cell contents, and reads in 1.4 s at 78 MB. The reviewers' far-row, wide-row and 5-million-cell files, and two of 12 million elements, are refused in under a second at 67 MB. Files under the first limits still took openpyxl past the 1 GB machine: 1.9 million style formats in an 18 KB file peaked at 1,223 MB, 1.9 million merged ranges at 1,128 MB and 1.2 million defined names at 883 MB, at 560 to 680 bytes an element. The second count refuses all three in under 0.2 s. The worst file both counts allow peaks at 412 MB, so with one upload read at a time the machine holds it. Every part is scanned, whatever its name, so the scan never depends on finding the sheet openpyxl reads. A workbook with a second sheet wider than 200 cells is refused as well. A cut value in `normalized` always belongs to a row in error, and approve reads `normalized` of accepted rows alone, so nothing applied is ever cut. `normalized` left the rows API, since only approve reads it.

## D57. After the re-review: changed rows, unreadable files, one sheet read

Context: the four reviewers ran again over the D56 fixes. The spec checker showed approve's second classification applying a row reviewed as an update as a revise, which wrote a sheet's old amounts over a raise that had become current. The security reviewer found openpyxl reading an external link once per reference to it (a 4.7 KB file reached 1,027 MB) and sizing every sheet a workbook lists once per entry (40 entries took 16.8 s). The code reviewer found a workbook with no worksheet answering 500. Asked, the owner chose to refuse a changed row as D24 does, and plain words with a next step for an unreadable file, over passing Python's reason through.

Decision: approve classifies each accepted row again. A row that has become a no-op is left out. A row that would apply as another action than the one reviewed is re-marked `ACME-2 changed since this sheet was uploaded; upload the sheet again`, and approve answers 409 as the re-check does (SPEC F2 and section 7). An unreadable file says `file is not a readable .xlsx workbook; save it again from Excel and upload it`, or the same words for a .csv (SPEC section 8). openpyxl's `ExcelReader` reads the workbook with `keep_links=False`, its `read_worksheets` overridden to open the first worksheet alone and no chart sheet, so no part is read more than twice.

Consequences: approve applies what was reviewed, or less when a change is already in place, never more. A refused row needs a fresh upload. The reader leans on openpyxl's `read_worksheets` and `wb._sheets`, pinned at 3.1.5, and the parser tests fail if an upgrade changes them. A second sheet is never opened now, so a broken one no longer refuses the file.

## D58. Insight filters refuse a code that names nothing

Context: the directory filters with an `__in` lookup, so an unknown country code finds nobody and answers an empty page. The per-country and per-department insights list every code in the filter, and an unknown code has no name to list. Ignoring it silently was the alternative.

Decision: `build_filters` answers 400 with section 7's own words, `Unknown country_code: XX` and `Unknown department: growth`. The insight functions take the lookups as a third argument beside the filters and the rates, and `InsightFilters.local` marks `currency=local`, so the label reads `local currency (USD)` even when the local currency is one the toggle also offers.

Consequences: a typo in a shared link says so instead of drawing an empty chart. Each insight runs six queries at most: the user, the countries, the departments, the rates, one aggregate and one list of gross values. DESIGN 1.6.

## D59. Owner's answers at the step 6 close: small groups, spread figures and the local switch

Context: at exactly five people the five-person rule let by-level publish min, p25, median, p75 and max, which were every salary in the group. A one-person country or department showed its total cost, which is that person's cost read straight off the card or a screenshot with no arithmetic, and share times the company total gives it back. Step 7 exports these cards. Separately, F5 reset `local` whenever the country filter passed through no country or two, so a switch from India to Germany lost it.

Decision: one rule on every card. A group under five people, the summary included, shows its headcount alone, with `null` total cost, share, mean and median. The spread figures need twenty people: by-level's p10, p25, median, p75 and p90, never min or max, and the distribution's p1, p99, bands and markers. `SMALL_GROUP = 5` and `SPREAD_GROUP = 20` are the only spellings of the two thresholds, in `apps/insights/queries.py` and in `components/insights/figures.ts`, and the API and its tests use them. Withheld groups follow the shown ones in name order, so the order never hints at a hidden total. The country and department selects commit when their menu closes, so on the directory and the dashboard a switch from one country to another keeps `local` in the new country's currency, and two countries or none go back to USD.

Consequences: the rule protects what a chart, a screenshot or an export shows. Working one person's pay out by differencing (overall against a department, requests a day apart, with and without exited people) is accepted and out of scope. It takes deliberate work by the one role, which already sees every salary on the employee list. Revisit if a second role is ever added. No level in the DESIGN fixture reaches twenty, so its by-level and `country=US` distribution cases are headcount only, and a small fixture with one level of twenty and one of nineteen tests the spread figures. Step 7's insight export reads the same payload and inherits the rule, and its test uses a level under twenty. SPEC v2.11 section 9 and F5, DESIGN 1.6, 4, 6 and 9, PLAN step 7. Amends D25.

## D60. Owner's answers at the start of step 7: what each export holds

Context: SPEC F6 fixed the rows of the six insight exports but not their columns. It did not say what a distribution under twenty people exports (D59), and the summary has no card to carry an export menu. Asked for the columns, the distribution under twenty and the summary menu's place, the owner chose a Currency column, plus the rest below. DESIGN 1.7 also had `directory_table` take the request, and counted sixteen directory columns where F6 lists seventeen.

Decision: every insight table ends with Reason, Currency and Rates. Rates is the rate month label, since every converted figure depends on it and each file travels alone. Reason is in the screen's words, `fewer than 5 people` or `fewer than 20 people`, empty when the figures are shown or the group has nobody. Gender-gap keeps its own reason, `group too small`, on each row of the group. A withheld cell is empty in CSV and XLSX and `null` in JSON. A distribution without bands is one row, with People the headcount and Band, From and To empty. The summary's menu is a kebab on the rate month line, named and titled `Export summary`. Readings taken with the answers: `directory_table` takes the filtered queryset and plain values, and the list and the export share `DirectoryMixin`, so an export holds exactly the rows the pages show, in their order. Department and country are names, as on screen. Bands are numbered from 1. JSON values are not formula-escaped, since only a spreadsheet runs a cell, and numbers, negative amounts among them, are written as numbers and never escaped. A missing or unknown `file` is a 400, `file must be csv, xlsx or json, got pdf`. An insight file is named `acme-<insight>-YYYYMMDD-HHMM.<ext>`. A JSON file's filters are the ones the export reads, as given, with `on` and `currency` as applied. XLSX replaces what XML cannot hold, the control characters and U+FFFE and U+FFFF, with U+FFFD, where openpyxl would refuse the workbook or write one that will not open.

Consequences: a file read on its own says what its figures are in and why any are missing. The unfiltered directory exports its 10,000 rows in under two seconds in each format, measured by `timing --case export`. SPEC v2.12 F6, DESIGN 1.3, 1.7, 6 and 9.

Amended at the step 7 close: asked whether the summary should end like the other five tables, the owner chose that it should, with one test that holds every insight table to Reason, Currency and Rates. After the review, every CSV field is quoted, so text holding a semicolon cannot start a formula where Excel splits on semicolons. A CSV reads its first hundred rows, and checks a rate for every currency a live record is in, before its 200 goes out, so a failure is an error response and never a file cut off part way.

Amended 8 Oct, after the step 7 deploy: the owner asked for an Export button in place of each kebab on the dashboard, with the same three formats. Every export menu is now the same labelled button, small on the cards and the rate month line, named and titled for its table (`Export summary`).

## D61. The designation filter takes at most 20 titles

Context: the step 7 security review sent the directory 1,100 designations in one 3 KB query string. Each title is one more OR in the query, and SQLite refuses an expression deeper than 1,000 with a 500. Search already stops at ten words for the same reason.

Decision: `designation` takes at most 20 titles, and more is a 400, `designation accepts at most 20 titles`. Country, department and level are `IN` lists, which do not deepen the expression, and keep no limit.

Consequences: a list of titles typed by a person stays well under the limit. The list and the export answer alike, since they share `DirectoryMixin`. DESIGN 1.3.

## D62. After step 7: trend, cost bridge, tenure, cost mix and four gender gap views

Context: after step 7 closed, the owner added a step before Hardening, exports included. Trend, by-tenure and the component mix were P1 in SPEC v2.12, the cost bridge is new, and the gender-gap card gains three views. The owner named this D61, which the designation cap had taken at the step 7 close, so it is D62. Hardening and Ship become steps 9 and 10.

Decision: built in this order. `trend` is total cost or headcount at the 24 month-ends in the 24 months ending at `on` (31 Oct 2024 to 30 Sep 2026 for 7 Oct 2026), every month converted at the one rate effective on `on` and labelled so, one line at a time and never two axes, the subtitle naming the latest point (`month-end totals, latest 30 Sep 2026`) so it is not read as disagreeing with the KPI row. `cost-bridge` explains how total cost moved over the 12 months ending at `on`, at that same rate: start, minus leavers, plus joiners, plus pay changes for those who stayed, end, adding up exactly, through the month-end population code it shares with trend. `by-tenure` is median gross by tenure at `on` (under 1, 1 to 3, 3 to 5, 5 to 10, and 10 or more years) within the level the card picks, All or 1 to 6. `cost-mix` is one bar per country, as shares of total cost (base, each allowance of the country, bonus, employer contributions) or as shares of gross (net and each deduction). The gender-gap card has four views: Pay gap as today, Bonus (who receives one, and the mean and median bonus gap among those who do), Quartiles (everyone ranked by gross in the reporting currency, in four equal groups) and By level (the gap within each level per country). It is labelled on annual pay: it follows EU Directive 2023/970 Article 9 and the UK's six gender pay gap measures, and is not a statutory filing (no hours, no legal entities). Other and undisclosed are counted beside each view. The dashboard bar decides who is counted, for every card but one pair: `trend` and `cost-bridge` count the people employed on each date, Include exited does not apply to them, and when it is ticked each card says so in a caption, `Counts people employed on each date; Include exited doesn't apply`. Each card has one control, which slices or measures and never picks a second country or department, kept in the URL under the card's prefix, sent by its export and reset by Clear filters. D59 holds: 5 people for totals, shares, medians and each bridge part, 20 for spreads and quartiles, 5 women and 5 men for any gender comparison, and anything below shows its headcount with the reason.

Answers to the plan's questions: when leavers, joiners or those who stayed number 1 to 4, all three parts show their headcount alone with the reason on the short one, while start and end stay shown. A part with nobody shows 0 and does not trigger the rule. By level shows the mean and the median gap, each as a share of men's pay, each needing 5 women and 5 men in that country and level, and flags a mean gap of 5% or more either way, worded neutrally as the threshold in EU Directive 2023/970 Article 10. Asked separately, the owner replaced `group too small`: a gender comparison that is short says `fewer than 5 women`, `fewer than 5 men`, or both (`fewer than 5 women and fewer than 5 men`), on screen and in the export's Reason column, in every view, Pay gap included. Approving the plan, the owner also asked that the bridge's pay changes be summed directly from those who stayed, per currency, converted and quantised once, and tested to match end minus start plus leavers minus joiners within 3 cents per currency in the filter, the card and the export showing the balancing figure so the parts still add up to the cent. Trend's export always carries headcount and total cost, the measure picking only the line drawn. The dashboard groups its cards under three headings: What we spend (the KPI row, trend, cost bridge and by country, by department and cost mix), How pay is structured (distribution, by level and by tenure) and Is pay fair (the gender gap).

Consequences: the seed keeps each employee's joining record and the three latest April raises, so any date before 1 April 2024 understates long-tenured pay. trend is exact while `on` is on or after 1 April 2026, and cost-bridge while it is on or after 1 April 2025. The seed gives gender no effect on pay, so the gender views show gaps near zero, which is expected. Quartiles break ties by employee id and cut at `floor(k * n / 4)`, a simplification of the UK method, which splits tied pay across a boundary by gender and places the leftover people differently. In a narrow filter two neighbouring trend points can differ by one joiner's or one leaver's cost, the comparison across dates that D59 accepts. top-earners, recent-changes, raise-cycle analytics (the seed's 2024 cycle reads 46%), compa-ratio and band adherence (there is no pay range table) stay P1. PLAN step 8, SPEC v2.13, REQUIREMENTS item 4, DESIGN 1.6, 6, 8 and 9.

Amended at the step 8 close, after the four reviews and two sets of the owner's answers. The owner set one rule for the new views: figures that add up across rows (totals and means, and shares when another card shows the total they are a share of) can give a withheld row back by subtraction. So the new views publish counts, shares, medians and gap percentages, and an amount that adds up appears only where the card needs it and no withheld row in the same view, or on the same page, can be worked out from it. Checked view by view, Bonus drops its mean bonus amounts, By level drops the mean pay of women and men and keeps both gaps, Quartiles rank women and men alone with other and undisclosed counted once beside, and a cost-mix country shows its headcount alone, naming the segment (`Bonus held by fewer than 5 people`), when a segment it shows is held by 1 to 4 people, since that share times its total cost on by-country gives back what they are paid. By level counts other and undisclosed per country, beside the levels. With no code change, its women and men per level taken from the by-level card's headcount per level give the other and undisclosed at each level, a count worked out across two cards and not pay, which D59 accepts.

The owner's other answers: a bridge part with nobody shows 0.00 and triggers nothing, and a change withheld because another is short says `withheld with the leavers` (or the joiners, or the pay changes). `fewer than 5 women with a bonus` and its kin stand, and a group with nobody in it gives no reason, as every other table words it. Dates write every month in three letters, `Sep` in place of en-GB's `Sept`.

The reviews also brought these. The receiving count reads the bonus in its own currency, and the By level flag reads the gap before rounding, so 4.999% shows as 5.0 unflagged. A control is read in any case, the export's JSON filters carry it as applied, its default when none was given, and the JSON of trend and cost-bridge leaves Include exited out. An `on` before 1900-01-01 is a 400, since the trend and the bridge reach two years back and the year 1 gave a 500. `timing` times every value of every control. The cost-mix swatches are theme tokens, one per component of a view, each clearing 3:1 on white and standing apart from its neighbours in a bar under deutan, protan and tritan vision. Commit 26b12bc said a part with nobody shows 0, which the code did only from this close, and ff8db4b said the quartiles rank everyone and `timing` covers each control value, the first replaced and the second made true here. SPEC v2.14, DESIGN 1.6, 1.7, 7, 8 and 9.

## D63. The directory opens an employee from a pencil, sorts by code, and keeps its sort through Clear filters

Context: before step 9 the owner asked for four changes to the directory. A click anywhere on a row opened the employee (SPEC section 10, DESIGN 6), the sort icons showed only on hover, the default order was by name with no column marked, and Clear filters reset the sort with the filters.

Decision: the first column is a pencil button, a link to the employee page named and titled `Edit <full name>` and reached by keyboard through the grid's cell focus, and the row click and its pointer cursor are gone. The column is not pinned, because column pinning is a Pro feature in MUI X 9 and the app uses the free grid. Instead the grid shows by default only the columns that fit a 1280 px window without sideways scrolling (the pencil, Code, Name, Department, Country, Level, Status, Gross in the reporting currency and Joined), and the rest wait in the column chooser. Every sortable column shows a faint up-down icon at rest and the sorted one its arrow at full strength, and a column that cannot sort shows none. The default sort is Code ascending: the grid marks it, the URL leaves it out, and the API orders the directory and its export by code when `ordering` is absent. Clear filters resets the filters and the search, keeps the sort and the page size, and goes back to page 1.

Consequences: the other columns are one click away in the chooser, and showing them brings sideways scrolling back at 1280 px. A test holds the default columns' widths to the room a 1280 px window leaves. SPEC v2.15 sections 10 and F4, DESIGN 6.

## D64. Before Hardening: a realistic seed, a period on the dashboard, numbered pages

Context: after the directory changes (D63) the owner added a step before Hardening, which becomes step 10 and Ship step 11. The seed had 10,000 employees with 8% of them gone, kept each person's joining record and last three raises, and gave each person one level for life. The dashboard read one date, `on`, with trend fixed at 24 month-ends and the bridge at 12 months. The free grid shows at most 100 rows a page and paged by next and previous alone.

Decision: the brief's "an organization with 10,000 employees" is read as 10,000 on staff on the reference date, so `seed_data --active 10000 --exited 5000` replaces `--employees`. Leavers leave every month from 2015 in proportion to the headcount, juniors more often, never in their first 30 days. Level follows total years of experience on a ladder whose neighbours overlap by about a year (L1 0 to 3, L2 3 to 6, L3 5 to 8, L4 7 to 11, L5 10 to 13, L6 12 and up). Today's level, experience and joining date are drawn in that order, and the same on a leaver's last day. Pay is set by level on that day, plus 2% a year above the level's floor up to 20% and never under the country's minimum, and the history is back-filled through every April revision since joining, 3 to 8% a year and 12 to 20% at a promotion, whose note names the new level. The directory opens on Active employees. The dashboard reads a period, `from` and `to`, picked in its bar from Last 3, 6 or 12 months (the default), the current financial year to date, the last financial year or a custom range between 1 January 2015 and 31 December 2100. ACME's financial year runs from 1 April to 31 March, one constant. Trend and the bridge run over the whole period, the other cards show the state on `to` and say so, the KPI row adds what the period cost, and one rate, the one effective on `to`, converts it all. ServerGrid pages by number, with a Go to page box.

Consequences: D62's caveats on the seed's depth go, since every revision is kept. The seed about doubles, so its time is measured on Fly before the live database is rebuilt with `reset_demo`, which waits for the owner. Level stays on the employee, so the cards that group by level read each person's level today on any `to`, one of the questions DESIGN lists for the owner's approval. SPEC v2.16 (F4 to F6 and sections 8 to 11, 13 and 15), REQUIREMENTS item 8, PLAN step 9, DESIGN 1.6, 1.7, 5, 6, 8 and 9.

Approved on 8 October with the owner's changes. Level stays on the employee, and the cards that group by level (By level, By tenure's Level control and gender-gap's By level) say, when `to` is not today, "Levels are as of today; anyone promoted after <to> appears at their new level", with a level history per record added to P1. L1 leaves twice as often as L3 to L6 and L2 one and a half times as often. Last N months starts on the same day N months back, or on that month's last day where the day does not exist (31 October gives 30 April, 31 March gives 28 or 29 February). The seed is timed on Fly, and if it takes over 60 s its target rises to 120 s, since it runs once per volume and the deploy waits up to 10 minutes (D31). `reset_demo` runs on the live machine only on the owner's word, after the machine has been idle, since D65's burst balance sets its speed, and its time is recorded. The import's row limit rises to 15,000, the whole seeded organisation in one file, and D56's other upload limits stay, a 10,000-row file having measured 377,122 elements against the 2,000,000 cap. `make_import_file --all` writes all 15,000, leavers with their `last_date`, and the import timing reads that file. Staging stays under 30 s and approval scales with the limit to 22.5 s (15 s per 10,000 rows). On Fly both the `--all --raises 1000` file and a `--new 15000` file, the heaviest approve, are timed, with the burst balance noted and peak memory recorded. The other defaults stand. F1, sections 8, 13 and 16, and REQUIREMENTS' success criterion follow.

Measured in the build: spread against those who stay, the leavers' yearly rate climbed from 6% in 2015 to 13% in 2025, so each month's leavers now follow everyone employed then, leavers still there included, settled in three passes. That holds a steady 11% a year with 10,000 who stay and 5,000 who leave, above the 8 to 10% hoped for. The owner kept 5,000 over 4,000 (about 9.5%) or 3,700 (about 9%).

## D65. The live machine stays on Fly's shared CPU

Context: the step 8 deploy's timing run sent about 900 insight requests back to back. Near its end Fly's shared vCPU spent its burst balance and ran at its 6.25% baseline, so gender-gap's By level view for India read 639 / 1118 ms p50 / p95, against 35 / 43 ms timed alone with no CPU steal. A performance CPU would hold that speed under any load, at a higher monthly cost.

Decision: the owner kept `shared-cpu-1x` on 8 October. One HR user's dashboard load costs about a second of CPU, well inside the burst balance, which starts at 5 s on a new machine and accrues to 500 s while idle.

Consequences: the code meets SPEC section 13's 500 ms target. A load test, or a run of filter changes just after a deploy, can still be throttled to several hundred ms a card, and PERFORMANCE.md records both numbers. Revisit if the app gains users.

## Clarifications from Incubyte, 6 Oct 2026

Five questions sent before building, answered the same day. Each answer is captured as a decision above or in `REQUIREMENTS.md`.

| Question | Answer | Effect on the spec |
| --- | --- | --- |
| Does "deployed" mean a public URL, or Docker plus the demo video? | A live public URL is required. Docker and a video are welcome in addition. | Hosting moved from conditional to required. D5 and D11. |
| Current pay structure with revision history, or monthly payroll? | Annual gross or current salary is sufficient. Payroll not required. History optional. | Revisions kept, payroll stays out. D2 stands. Components kept and trimmed, D12. |
| Fixed insights or ad hoc querying? AI feature in the product? | A focused dashboard with filters is sufficient, no predefined report list, no AI feature or ad hoc querying required. | Six fixed insights, no AI in the product. D3 and D10 stand. |
| Single HR Manager login? | Sufficient. Advanced RBAC not required. | D4 stands. |
| USD via a fixed exchange-rate table? | Acceptable, no prescribed currency or FX source, live rates not required. | D7 superseded by D13: dated rates, conversion at read time, USD or EUR. |

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

Decision: the access token lives in memory and the 12-hour refresh token in `localStorage`. The app is one SPA on one origin with one user. A cookie would bring CSRF protection on every mutating call and a CORS exception for the refresh endpoint, for a threat model where the attacker already runs script on the page and could call the API directly for 30 minutes anyway. Rotation with blacklist limits a stolen refresh token to one use.

Consequences: a cross-site-scripting bug exposes the refresh token for its lifetime. There is no third-party script on the page and MUI escapes rendered values, so the exposure is accepted for v1 and recorded here as the first question a security reviewer will ask.

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

## D26. Import exits write one exit entry, and a first record cannot be cancelled

Context: a row whose `last_date` appears is an identity change in F1's table but runs the exit service, and F3 as written would let a future joiner's only record be cancelled, leaving no record at all.

Decision: such a row writes one `exit` entry on the employee carrying any identity changes in the same before and after, and counts in `updated_rows`. Cancelling version 1 returns 409 `the first record cannot be cancelled`. DESIGN sections 1.4 and 1.5.

Consequences: one entry per entity holds for imports too. A future joiner's wrong pay is fixed by exit and re-create in v1, or by the P1 in-place correction. Owner's answers to DESIGN questions 3 and 4.

## D27. API conventions the spec left open

Context: DESIGN questions 5, 6, 7, 10 and 11 proposed defaults for the JSON export shape, money encoding, warnings on writes, percentage precision and upload content types.

Decision: the JSON export is `{generated_at, filters, rows: [{snake_case key: value}]}` and file names carry a UTC stamp. Money is a two-decimal string everywhere in the API. Create and revise responses carry `warnings`. `share_pct` and `gap_pct` have one decimal. `application/octet-stream` is accepted when the extension is `.xlsx` or `.csv`.

Consequences: frontend money types are strings and convert to numbers only for chart geometry. The spec-checker has a source here for each shape.

## D28. Rate month label, light theme, sample data

Context: DESIGN questions 9, 12 and 14.

Decision: the dashboard's rate month is the most recent `effective_from` among the rates feeding the reporting currency, and `/meta/exchange-rates/` lists each pair's own date. The UI ships a light theme only. `sample-data/` holds `acme-sample-50.xlsx` and the same rows as CSV, from `make_import_file --new 20 --raises 24 --errors 6`.

Consequences: one palette to validate. The sample files are regenerated whenever the seed or the planted error list changes, in the same commit.

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

## Clarifications from Incubyte, 6 Oct 2026

Five questions sent before building, answered the same day. Each answer is captured as a decision above or in `REQUIREMENTS.md`.

| Question | Answer | Effect on the spec |
| --- | --- | --- |
| Does "deployed" mean a public URL, or Docker plus the demo video? | A live public URL is required. Docker and a video are welcome in addition. | Hosting moved from conditional to required. D5 and D11. |
| Current pay structure with revision history, or monthly payroll? | Annual gross or current salary is sufficient. Payroll not required. History optional. | Revisions kept, payroll stays out. D2 stands. Components kept and trimmed, D12. |
| Fixed insights or ad hoc querying? AI feature in the product? | A focused dashboard with filters is sufficient, no predefined report list, no AI feature or ad hoc querying required. | Six fixed insights, no AI in the product. D3 and D10 stand. |
| Single HR Manager login? | Sufficient. Advanced RBAC not required. | D4 stands. |
| USD via a fixed exchange-rate table? | Acceptable, no prescribed currency or FX source, live rates not required. | D7 superseded by D13: dated rates, conversion at read time, USD or EUR. |

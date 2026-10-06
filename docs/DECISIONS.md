# Decisions

Why the system is the way it is. One entry per non-obvious choice: context, decision, consequences. Newest at the bottom. Add an entry whenever a choice is made during the build that a reviewer might ask about.

## D1. Salary components are data, not columns

Context: the first draft had HRA, LTA, PF, Professional Tax and Gratuity as columns on a Salary table, and a separate Salary Schema table describing fields per country. The two contradict each other, and the columns are India-only. A US employee has a 401(k) match, a UK employee has National Insurance, a German employee has social insurance.

Decision: a `SalaryComponent` table (global or per country, kind of earning, deduction or employer contribution) and one `CompensationLine` per component on each record. Header totals (gross, net, total cost) are denormalised on the record.

Consequences: forms and the import template need the component list for the employee's country. Any question about a component is a query, not a Python loop. A JSON column was considered and rejected because SQLite can filter JSON but cannot index into it.

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

## D5. One container, SQLite on a volume, hosting conditional

Context: the first draft planned to run the dev server locally. `runserver` is single-threaded, does not serve static files safely and is not a deployment. The brief says "fully functional deployed software", which could mean a public URL or a one-command Docker run plus the demo video.

Decision: a multi-stage Dockerfile, gunicorn plus WhiteNoise serving the API and the built SPA from one container, SQLite in WAL mode on a persistent volume, `docker compose up` for local parity. Hosted on a container host with a persistent volume, as Incubyte confirmed on 6 Oct that a live public URL is required and local-only Docker is not enough.

Consequences: one deployable, no CORS between services in production, no second database to run. SQLite's single-writer limit does not bite with one container. Postgres later is a settings change.

## D6. MUI with MUI X DataGrid, Recharts, Vitest

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

Context: salary data is sensitive and the HR Manager is the only editor. Mistakes need to be traceable and reversible.

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

## Clarifications from Incubyte, 6 Oct 2026

Five questions sent before building, answered the same day. Each answer is captured as a decision above or in `REQUIREMENTS.md`.

| Question | Answer | Effect on the spec |
| --- | --- | --- |
| Does "deployed" mean a public URL, or Docker plus the demo video? | A live public URL is required. Docker and a video are welcome in addition. | Hosting moved from conditional to required. D5 and D11. |
| Current pay structure with revision history, or monthly payroll? | Annual gross or current salary is sufficient. Payroll not required. History optional. | Revisions kept, payroll stays out. D2 stands. Components kept and trimmed, D12. |
| Fixed insights or ad hoc querying? AI feature in the product? | A focused dashboard with filters is sufficient, no predefined report list, no AI feature or ad hoc querying required. | Six fixed insights, no AI in the product. D3 and D10 stand. |
| Single HR Manager login? | Sufficient. Advanced RBAC not required. | D4 stands. |
| USD via a fixed exchange-rate table? | Acceptable, no prescribed currency or FX source, live rates not required. | D7 superseded by D13: dated rates, conversion at read time, USD or EUR. |

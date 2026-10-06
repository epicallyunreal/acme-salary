# Requirements: ACME Salary Management

## Goal

Replace ACME HR's salary spreadsheets with a web application where the HR Manager imports, corrects, maintains and queries compensation for 10,000 employees across countries, and answers "how does the org pay people?" from a dashboard instead of a pivot table.

## Problem

From the brief: "Currently, ACME org's HR team manages salary data for 10,000 employees across multiple countries, with everything managed via excels, which is tedious. We want the HR manager to manage the salaries data via web-based software and be able to answer questions about how the org pays people."

Two jobs hide in that sentence. Move the data out of spreadsheets safely and keep it correct, and make the data answer questions. A CRUD app alone fails the second job and a dashboard alone fails the first.

## User

One persona, one role: the HR Manager. They own the salary data, approve every import, and are the only person who edits records.

## In scope

1. Spreadsheet import (.xlsx or .csv) from a published template, with per-row validation and a review-and-approve step before anything reaches live data.
2. Employee and compensation management: create, view, edit, mark exited. Compensation as effective-dated revisions with full history.
3. Employee directory with server-side search, filters, sorting and pagination.
4. Insights dashboard answering six fixed questions about how the org pays people, filterable by country and department.
5. Export of any filtered directory view or insight table to XLSX, CSV and JSON.
6. Audit trail of every change to employee and compensation data.
7. Single HR Manager login protecting every API route.
8. Deterministic seed of 10,000 employees across six countries with pay history.
9. A live public URL, plus a Docker build that runs with one command and a recorded demo.

## Deliberately out of scope

| Left out | Why |
| --- | --- |
| Monthly payroll runs and payslips | Salary management is knowing what people are paid. Computing what to pay each month (attendance, tax slabs, statutory filings) is a payroll product. Dated revisions already answer "salary over time". |
| Tax and statutory calculation | Country-specific and legally sensitive. Components, including a recorded tax figure, are stored as entered, never computed. |
| Multiple roles, SSO, approval chains | One persona in the brief. |
| Employee self-service portal | The persona is the HR Manager only. |
| Live FX rates | A seeded, editable rate table converts to USD for comparison. Live rates add an external dependency for no demo value. |
| Custom report builder | Six well-chosen insights answer the brief. A query-builder UI is large and adds little at 10k rows. Filters plus export cover the long tail. |
| Column-mapping UI for arbitrary spreadsheets | Import works from a template with header auto-matching. Mapping unknown layouts is a follow-up. |
| Inline editing of staged import rows | A wrong value is fixed in the sheet and re-uploaded. Cheaper to build and easier to reason about, deferred to P1. |
| Ad hoc or natural-language querying, AI features inside the product | Not required (confirmed by Incubyte). A fixed set of insights with filters and export answers the brief. AI is used in the development process, not in the product. |

## Key assumptions

- Amounts are annual, in local currency, stored as decimals. Converted figures are never stored. An effective-dated exchange-rate table is the single source of truth, and conversion to the reporting currency (USD by default, EUR available) happens at read time at the rate effective on the reporting date.
- Salary components differ by country, so they are data (a component table and one line per component), not fixed columns. v1 keeps them deliberately small: three global components including a single employer-contribution line, plus one or two per country. Bonus is a plain column on the record, as anyone in any country can receive one.
- "Salary history" means dated compensation revisions, not monthly payslips.
- Import is staged: nothing touches live data until the HR Manager approves the batch.

## Success criteria

- A 10,000-row spreadsheet is uploaded, validated, reviewed and approved end to end in under 2 minutes.
- Any employee's current pay and history is found and revised in under 10 seconds.
- Every dashboard question is answered in one view, with no export to Excel needed.

## Clarifications from Incubyte (asked and answered 6 Oct 2026)

| Question | Answer | What I am doing |
| --- | --- | --- |
| Does "deployed" mean a public URL, or Docker plus the demo video? | A live public URL. Docker and a video are welcome in addition, a local-only Docker setup is not enough. | Hosting a live instance. Docker and the video ship as well. |
| Current pay structure with revision history, or monthly payroll? | Annual gross or current salary is sufficient. Payroll runs and payslips are not required. History is optional. | Keeping effective-dated revisions, as a raise is the most common edit and history makes it traceable. Keeping a trimmed per-country component structure, as the org pays across countries and that structure cannot be retrofitted cheaply later. Payroll stays out. |
| Fixed insights or ad hoc querying? AI feature in the product? | A focused dashboard with filters is sufficient. Examples: total cost, average and median by country or department, headcount, distribution. No predefined report list. No AI feature or ad hoc querying required. | Six fixed insights with country and department filters and export. No AI in the product. |
| Single HR Manager login? | Sufficient. Advanced RBAC not required. | One seeded account, no roles. |
| USD via a fixed exchange-rate table? | Acceptable. No prescribed currency or FX source. Live rates not required. | Local currency stored. Conversion at read time to USD or EUR from an effective-dated rate table, never stored, with the rate's effective date shown. |

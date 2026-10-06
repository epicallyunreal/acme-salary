---
name: add-insight
description: Recipe for adding a dashboard insight end to end, query first. Use when adding any of the insights in docs/SPEC.md section 9, or when the user says "add the X chart", "answer the question how much do we pay by Y".
---

# Add an insight

Check `docs/SPEC.md` section 9. The insight must be in the v1 table, or the human must have promoted it from the P1 list. Do not build a P1 insight unless told to.

1. Query. Add `def <name>(filters: InsightFilters) -> dict` in `backend/apps/insights/queries.py`. Filters carry `country`, `department` and `currency`. Read current records only (`effective_to__isnull=True`) joined to active employees. Use ORM `aggregate` and `annotate` for sums, counts and means. Convert at read time through `core.fx`: aggregate per (group, currency) in SQL, multiply by the Decimal rate for the reporting currency in Python, quantise to 2 dp. For medians and percentiles, pull `(gross_annual, currency_code)` with `values_list`, convert each value in Python, then use `statistics`. Return plain dicts with Decimal values and the rate's effective date. Never store a converted amount.
2. Query test in `tests/insights/test_queries.py`. Build a 20 to 30 row fixture with factories where the expected numbers are easy to compute by hand, write those expected values into the test, and assert them exactly. Add one test per filter.
3. Endpoint. `GET /api/v1/insights/<name>` through the shared insight view: parse filters, call the query, serialise. One test in `tests/insights/test_api.py` with `django_assert_num_queries`.
4. Export. Register the insight's table shape in `apps/exports` so `/exports/insights/<name>` works. One row-count test.
5. Frontend. Hook in `src/api/insights.ts`, MSW handler, card component in `src/components/insights/` using Recharts with the chart type from the spec table, wired into the Dashboard with the shared FilterBar. Local currency toggle only when one country is selected.
6. Frontend test: the card renders the title, the numbers from the MSW fixture, and reacts to a filter change.
7. Timing. The endpoint must answer under 500 ms on the 10k seed. Check with `/perf-timing` before finishing the step.

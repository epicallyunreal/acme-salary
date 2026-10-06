---
name: perf-timing
description: Measure directory, insight, import and seed timings on the 10k seed and record them in docs/PERFORMANCE.md. Use at the end of any step that touches the directory, insights, import pipeline or seed, or when the user says "time it", "check performance" or "update the perf numbers".
---

# Measure and record performance

Targets are in `docs/SPEC.md` section 13: directory under 300 ms p95, insights under 500 ms p95, 10,000-row import staged under 30 s and approved under 15 s, seed under 60 s.

1. The script lives at `backend/scripts/timing.py`. If it does not exist yet, create it as a Django management command `python manage.py timing`:
   - Requires a database seeded with 10,000 employees. Refuse to run otherwise.
   - Logs in with the seeded HR Manager through the test client and reuses the token.
   - Directory: 20 requests each for the unfiltered list, a country filter, a department plus gross-range filter in the reporting currency, and a sort by gross in the reporting currency (the read-time annotation). Report p50 and p95 in ms per case.
   - Insights: 20 requests to each v1 insight endpoint, unfiltered and with a country filter. Report p50 and p95.
   - Import: export the seed to the template with the exports endpoint, upload it, time staging; skip the error rows if any, time approve on a copy of the database so live data is unchanged.
   - Seed: time `seed_data --employees 10000 --seed 42 --reset` against a scratch database path.
   - Print a Markdown table row matching the columns in `docs/PERFORMANCE.md`, plus the per-case breakdown.
2. Run it on the 10k seed: `python manage.py timing`.
3. Paste the row into the table in `docs/PERFORMANCE.md` with today's date, the short commit SHA and the machine (CPU and OS in a few words). Put the per-case breakdown and anything that changed since the last row in the notes below the table.
4. If a target is missed, do not tune blindly. Run the slow request with `django.db.connection.queries` or `EXPLAIN QUERY PLAN`, name the cause (missing index, N+1, Python loop), fix it, re-measure, and record both numbers.

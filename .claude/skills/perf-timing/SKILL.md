---
name: perf-timing
description: Measure directory, insight, import and seed timings on the seed of 10,000 active and 5,000 exited employees and record them in docs/PERFORMANCE.md. Use at the end of any step that touches the directory, insights, import pipeline or seed, or when the user says "time it", "check performance" or "update the perf numbers".
---

# Measure and record performance

Targets: directory under 300 ms p95 and insights under 500 ms p95 (SPEC section 13), 15,000-row import staged under 30 s and approved under 22.5 s (section 13, D64), seed under 120 s (section 11, D64).

1. The script is the management command `timing` at `backend/apps/core/management/commands/timing.py`. If it does not exist yet, create it:
   - Requires a database seeded with 10,000 active and 5,000 exited employees (D64). Refuse to run otherwise.
   - Logs in with the seeded HR Manager through the test client and reuses the token.
   - Directory: 20 requests each for the unfiltered list, a country filter, a department plus gross-range filter in the reporting currency, and a sort by gross in the reporting currency (the read-time annotation). Report p50 and p95 in ms per case.
   - Insights: 20 requests to each insight endpoint, unfiltered and with a country filter, each card control's other values, and the summary, trend and the bridge on each period preset and on 2015 to today (D64, D69). Report p50 and p95. `--insights periods` times only the period cases, to spare a shared CPU's burst balance on Fly (D65).
   - Import: generate the 15,000-row file with `make_import_file --all --raises 1000` and a `--new 15000` file, upload each, time staging, then time approve on a copy of the database so live data is unchanged, with the process's peak memory (`--sheet` runs one alone, and `--sheet crafted` stages the worst sheet the limits let through, D68).
   - Seed: time `seed_data --active 10000 --exited 5000 --seed 42 --reset` against a scratch database path.
   - Print a Markdown table row matching the columns in `docs/PERFORMANCE.md`, plus the per-case breakdown.
2. Run it on the seed: `python manage.py timing`.
3. Paste the row into the table in `docs/PERFORMANCE.md` with today's date, the short commit SHA and the machine (CPU and OS in a few words). Put the per-case breakdown and anything that changed since the last row in the notes below the table.
4. If a target is missed, do not tune blindly. Run the slow request with `django.db.connection.queries` or `EXPLAIN QUERY PLAN`, name the cause (missing index, N+1, Python loop), fix it, re-measure, and record both numbers.

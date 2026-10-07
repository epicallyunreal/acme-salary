# Performance

Measured by `/perf-timing` (see `.claude/skills/perf-timing`). Targets: directory under 300 ms p95 and insights under 500 ms p95 (SPEC section 13), 10,000-row import staged in under 30 s and approved in under 15 s (section 13), seed in under 60 s (section 11), first boot on Fly recorded against the 300 s health-check grace (section 14).

| Date | Commit | Machine | Directory p50 / p95 (ms) | Insights p50 / p95 (ms) | Import stage / approve (s) | Seed (s) |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |

Notes on what changed between rows go below the table.

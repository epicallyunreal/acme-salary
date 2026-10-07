# Performance

Measured by `/perf-timing` (see `.claude/skills/perf-timing`). Targets: directory under 300 ms p95 and insights under 500 ms p95 (SPEC section 13), 10,000-row import staged in under 30 s and approved in under 15 s (section 13), seed in under 60 s (section 11), first boot on Fly recorded against the 60 s health-check grace (section 14, D31).

| Date | Commit | Machine | Directory p50 / p95 (ms) | Insights p50 / p95 (ms) | Import stage / approve (s) | Seed (s) |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-07 | ea1b6dd | Darwin arm64, 11 cores (Apple Silicon laptop) | not built yet | not built yet | not built yet | 10.0 |

Notes on what changed between rows go below the table.

- 2026-10-07, step 2 (commit ea1b6dd): `python manage.py timing --case seed` ran `seed_data --employees 10000 --seed 42 --reset` in a fresh process against a scratch database, migrate excluded: 10.0 s on the laptop, against the 60 s target in SPEC section 11. The run writes 10,000 employees, about 36,000 records, 150,000 lines and 46,000 audit rows in one transaction. The 500-employee determinism test takes 0.7 s. The Fly number for the seeded first boot is recorded at step 3's deploy (D31).

- 2026-10-07, step 1 (commit d4d0ca7 deployed as image `deployment-01M4AKM4PFKPRZWENASW29QXFH`, 79 MB), first boot on Fly, shared-cpu-1x with 1 GB in `sin`, no seed yet: init at 07:21:23Z, migrations applied 07:21:25Z, gunicorn listening 07:21:27Z, health check passing 07:21:29Z. Six seconds from init to healthy. Fly caps the check grace at 60 s (D31); the seeded first boot in step 2 deploys with `--wait-timeout 10m` and is measured here. `/healthz` from a laptop in India answers in 0.6 to 0.9 s per fresh TLS connection.

# ACME Salary Management

Web replacement for an HR team's salary spreadsheets: import, review, maintain and query compensation for 10,000 employees across six countries.

Status: planning. Build order is in `docs/PLAN.md` once approved, derived from `docs/SPEC.md` section 15. Live URL and demo video will be linked here at the Ship step.

## Documents

- `docs/REQUIREMENTS.md`, the one-page requirements document
- `docs/SPEC.md`, the engineering spec (v2, after the spec review)
- `docs/DECISIONS.md`, why things are the way they are
- `docs/PERFORMANCE.md`, measured timings
- `docs/reviews/`, Engineering Manager spec reviews, the latest approved before development began
- `docs/PLAN.md` and `docs/DESIGN.md`, what is built and how, approved before step 1

## Run

To be filled in at the Ship step. Target: `docker compose up`, then open http://localhost:8000.

## Test

Backend: `cd backend && pytest`. Frontend: `cd frontend && npm test`.

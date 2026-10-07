# ACME Salary Management

Web replacement for an HR team's salary spreadsheets: import, review, maintain and query compensation for 10,000 employees across six countries.

Status: building, step 1 of the approved `docs/PLAN.md`. Live URL `https://acme.nutanprabhat.dev` goes live at step 1 and the demo video is linked here at the Ship step.

The planning commits up to and including the second spec review were written by hand. From step 1 onwards commits carry a `Co-Authored-By` trailer where Claude Code wrote the change, and each build step was reviewed by the read-only agents in `.claude/agents/` and approved by the owner before it was committed.

## Documents

- `docs/REQUIREMENTS.md`, the one-page requirements document
- `docs/SPEC.md`, the engineering spec (v2, after the spec review)
- `docs/DECISIONS.md`, why things are the way they are
- `docs/PERFORMANCE.md`, measured timings
- `docs/reviews/`, Engineering Manager spec reviews, the latest approved before development began
- `docs/PLAN.md` and `docs/DESIGN.md`, what is built and how, approved before step 1

## Run

One container, the way it is deployed: copy `backend/.env.example` to `backend/.env`, set `SECRET_KEY` and `SEED_ADMIN_PASSWORD`, then from the repo root:

```
docker compose up
```

and open http://localhost:8000. The database lives on the `acme-data` volume.

For development, two processes:

```
cd backend && uv sync && uv run python manage.py migrate && uv run python manage.py runserver
cd frontend && npm ci && npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/healthz` to the Django server on port 8000. The dev settings have safe defaults, so `backend/.env` is optional; pass it with `uv run --env-file .env ...` when needed.

## Test

```
cd backend && uv run ruff format --check . && uv run ruff check . && uv run pytest
cd frontend && npm run lint && npm test -- --run && npm run build
```

The same commands run in CI on every push and in the pre-commit gate on every commit.

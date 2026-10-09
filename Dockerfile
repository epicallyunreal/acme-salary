# Stage 1: build the React app.
FROM node:26-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Django with the built bundle, served by gunicorn and WhiteNoise.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=acme_salary.settings.prod \
    SPA_DIR=/app/spa \
    SAMPLE_DATA_DIR=/app/sample-data \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev
# The runtime alone: no tests, no .env.example (D73).
COPY backend/manage.py ./
COPY backend/acme_salary ./acme_salary
COPY backend/apps ./apps
COPY backend/seed ./seed
COPY --from=web /web/dist /app/spa
# The Demo data page's committed base file (SPEC F9, D72).
COPY sample-data/base-15000.xlsx /app/sample-data/
# Pre-compress the bundle so WhiteNoise serves gzip and brotli variants.
RUN python -m whitenoise.compress /app/spa
COPY entrypoint.sh /app/entrypoint.sh
# The app runs as acme. The entrypoint starts as root only to hand it the volume (D73).
RUN chmod +x /app/entrypoint.sh \
    && useradd --system --uid 1000 --user-group --home-dir /app --shell /usr/sbin/nologin acme
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]

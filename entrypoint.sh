#!/bin/sh
# Container start (SPEC section 14): migrate, drop expired tokens, seed once, serve.
set -eu
cd /app

python manage.py migrate --noinput
python manage.py flushexpiredtokens
python manage.py seed_data --active 10000 --exited 5000 --seed 42 --if-empty

exec gunicorn acme_salary.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 \
  --threads 8 \
  --timeout 120

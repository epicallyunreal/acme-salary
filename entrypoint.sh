#!/bin/sh
# Container start (SPEC section 14): migrate, drop expired tokens, seed once, serve. gunicorn
# waits 600 s on a request so a throttled approve is never killed (D72).
#
# The volume mounts root-owned, so the first run is root: it hands /data to acme and starts
# over as acme, who owns nothing else and runs everything below (D73).
set -eu
cd /app

case "${DATABASE_PATH:-/data/db.sqlite3}" in
  /*) ;;
  *) echo "DATABASE_PATH must be an absolute path, got '$DATABASE_PATH'" >&2; exit 1 ;;
esac

if [ "$(id -u)" = "0" ]; then
  DATA_DIR="$(dirname "${DATABASE_PATH:-/data/db.sqlite3}")"
  mkdir -p "$DATA_DIR"
  chown -R acme:acme "$DATA_DIR"
  exec setpriv --reuid=acme --regid=acme --init-groups "$0" "$@"
fi

python manage.py migrate --noinput
python manage.py flushexpiredtokens
python manage.py seed_data --active 10000 --exited 5000 --seed 42 --if-empty

# gunicorn 25.1's control socket, off: nothing uses gunicornc, and acme's HOME is /root (D73).
exec gunicorn acme_salary.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 \
  --threads 8 \
  --timeout 600 \
  --no-control-socket

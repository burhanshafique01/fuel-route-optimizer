#!/usr/bin/env bash
# Start command for Render (or any Linux host). SQLite lives on the instance's
# temporary disk, so the schema and the station table are rebuilt at boot
# (about a second, no network needed) before the web server starts.
set -euo pipefail
python manage.py migrate --noinput
python manage.py load_stations
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 2 --timeout 60

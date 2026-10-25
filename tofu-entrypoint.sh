#!/bin/sh
# Tofu (2026-10-25): this file is Tofu's addition; it is not part of upstream Baby Buddy.
#
# Starts a copy of Baby Buddy on Tofu (the Dockerfile's CMD), the way upstream's Procfile.sh does:
#   1. `manage.py migrate` brings the database up to date. Tofu's database is new on the first start, so a
#      failure is retried a few times before the container gives up.
#   2. gunicorn serves the app on PORT, which Tofu sets (80 without it). WEB_CONCURRENCY sets the number of
#      workers (2 by default).
# Settings come from babybuddy.settings.tofu (DJANGO_SETTINGS_MODULE in the Dockerfile).
set -eu

cd "$(dirname "$0")"

attempt=1
until python manage.py migrate --noinput; do
	if [ "$attempt" -ge 5 ]; then
		echo "tofu-entrypoint: migrate failed $attempt times, giving up" >&2
		exit 1
	fi
	echo "tofu-entrypoint: migrate failed (attempt $attempt of 5), retrying in 5 seconds" >&2
	attempt=$((attempt + 1))
	sleep 5
done

exec gunicorn babybuddy.wsgi:application \
	--bind "0.0.0.0:${PORT:-80}" \
	--workers "${WEB_CONCURRENCY:-2}" \
	--timeout 30 \
	--access-logfile - \
	--error-logfile -

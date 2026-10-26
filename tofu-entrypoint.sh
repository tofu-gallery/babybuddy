#!/bin/sh
# Tofu (2026-10-25): this file is Tofu's addition; it is not part of upstream Baby Buddy.
#
# Starts a copy of Baby Buddy on Tofu (the Dockerfile's CMD):
#   1. `manage.py tofu_schema` brings the database's schema up to date, one start at a time, since Tofu can start
#      several instances at once (babybuddy/tofu_schema.py and TOFU.md say how). Upstream's Procfile.sh runs
#      `migrate` here. Tofu's database is new on the first start, so a failure is retried a few times before the
#      container gives up.
#   2. gunicorn serves the app on PORT, which Tofu sets (80 without it). WEB_CONCURRENCY sets the number of
#      workers (2 by default).
# Settings come from babybuddy.settings.tofu (DJANGO_SETTINGS_MODULE in the Dockerfile).
set -eu

cd "$(dirname "$0")"

attempt=1
until python manage.py tofu_schema; do
	if [ "$attempt" -ge 5 ]; then
		echo "tofu-entrypoint: the schema step failed $attempt times, giving up" >&2
		exit 1
	fi
	echo "tofu-entrypoint: the schema step failed (attempt $attempt of 5), retrying in 5 seconds" >&2
	attempt=$((attempt + 1))
	sleep 5
done

exec gunicorn babybuddy.wsgi:application \
	--bind "0.0.0.0:${PORT:-80}" \
	--workers "${WEB_CONCURRENCY:-2}" \
	--timeout 30 \
	--access-logfile - \
	--error-logfile -

# Tofu (2026-10-26): this file is Tofu's addition; it is not part of upstream Baby Buddy.
#
# The schema step of a copy's start on Tofu: tofu-entrypoint.sh runs `manage.py tofu_schema` before the web
# server, in place of the `migrate` upstream's Procfile.sh runs. See "Start-up when several starts run at once"
# in TOFU.md.
#
# - Tofu's container hosting can start several instances of a new deployment within the same second, all on the
#   same database. Each used to run `migrate`, and on an empty database they made the same tables at the same
#   moment and crashed against each other. Now one PostgreSQL advisory lock lets one start at a time do the schema
#   work; the others wait for it, then find the work done. Tofu's DATABASE_URL goes through a transaction pooler,
#   which hands the server connection to other clients between transactions, so a session-level lock taken through
#   it does not hold. The lock here is a transaction-level one (pg_advisory_xact_lock), the first statement of a
#   transaction on a connection of its own that stays open for the whole schema step: through the pooler, an open
#   transaction keeps one server connection until it ends, and the lock ends with it, also when a start dies.
# - A database that is up to date skips `migrate`, which even with nothing to apply sends about 700 statements
#   (its post-migrate steps), each a round trip through the pooler. One with migrations left to apply gets
#   `migrate`, as upstream's start does.
import time

from django.core.management import call_command
from django.db import DatabaseError, connection, connections
from django.db.migrations.executor import MigrationExecutor

# The lock's key, the same in every start of this app: zlib.crc32(b"babybuddy:tofu-schema").
LOCK_KEY = 1015805802
# How long a start waits for another start's schema step before it gives up (tofu-entrypoint.sh then retries).
LOCK_WAIT = "120s"
# duplicate_table, duplicate_object, duplicate_column, unique_violation
DUPLICATE_ERRORS = {"42P07", "42710", "42701", "23505"}


def schema_step(log):
    """The schema work of one start. Runs while the lock is held, on Django's own connection."""
    executor = MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        call_command("migrate", interactive=False, verbosity=1)
        done = "applied the migrations left to apply"
    else:
        done = "up to date"
    return done


def locked_schema_step(log):
    started = time.monotonic()
    lock = connections.create_connection("default")
    try:
        lock.set_autocommit(False)
        with lock.cursor() as cursor:
            cursor.execute(
                "SET LOCAL lock_timeout = %s;\n"
                "SET LOCAL idle_in_transaction_session_timeout = 0;\n"
                "SELECT pg_advisory_xact_lock(%s)",
                [LOCK_WAIT, LOCK_KEY],
            )
        waited = time.monotonic() - started
        done = schema_step(log)
    finally:
        # Ends the lock's transaction, which wrote nothing, and with it the lock.
        try:
            lock.rollback()
        except DatabaseError:
            pass
        lock.close()
    log(
        "tofu_schema: %s in %.2fs (%.2fs waiting for the lock)"
        % (done, time.monotonic() - started, waited)
    )


def start(log):
    """The schema step of a start, under the lock. A duplicate-object error retries the whole step once."""
    if connection.vendor != "postgresql":
        call_command("migrate", interactive=False)
        return
    for attempt in (1, 2):
        try:
            return locked_schema_step(log)
        except DatabaseError as error:
            if attempt == 1 and getattr(error.__cause__, "pgcode", None) in DUPLICATE_ERRORS:
                log("\ntofu_schema: %s; trying the whole step again" % str(error).strip())
                connection.close()
                continue
            raise


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
# - Every statement is a round trip through the pooler. `migrate` sends about 1,450 statements on an empty
#   database and about 700 with nothing to apply (its post-migrate steps), which took longer than Tofu waits for a
#   new instance to listen on its port. An empty database now gets tofu_schema.sql in one statement: the schema,
#   django_migrations and the rows `migrate` leaves on a new database, made with `manage.py tofu_schema
#   --make-snapshot`. A database that is up to date skips `migrate`; one with migrations left to apply (newer code,
#   or a snapshot that does not match the code's migrations) gets `migrate`, as upstream's start does.
# - Row-level security is turned on for every table of the app that lacks it, in the same locked step. With no
#   policy, the database's Data API roles (anon, authenticated) see no row; the app's own connection owns the tables
#   and is not limited by it.
import hashlib
import json
import os
import re
import subprocess
import sys
import time

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tofu_schema.sql")
SNAPSHOT_HEADER = "-- tofu-schema-snapshot "
# The lock's key, the same in every start of this app: zlib.crc32(b"babybuddy:tofu-schema").
LOCK_KEY = 1015805802
# How long a start waits for another start's schema step before it gives up (tofu-entrypoint.sh then retries).
LOCK_WAIT = "120s"
# How long the snapshot itself may take (it takes about a second).
SNAPSHOT_TIMEOUT = "300s"
# duplicate_table, duplicate_object, duplicate_column, unique_violation
DUPLICATE_ERRORS = {"42P07", "42710", "42701", "23505"}


def migration_digest(migration):
    """The SHA-256 of a migration's file, so the snapshot is only used for the migrations it was made from."""
    with open(sys.modules[migration.__module__].__file__, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_snapshot():
    """The snapshot's SQL and its manifest (the migrations and tables it holds), or (None, None)."""
    try:
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            sql = f.read()
    except FileNotFoundError:
        return None, None
    first_line = sql.split("\n", 1)[0]
    if not first_line.startswith(SNAPSHOT_HEADER):
        return None, None
    return sql, json.loads(first_line[len(SNAPSHOT_HEADER) :])


def app_tables():
    """The tables the app's code makes: its models' tables, Django's migration record and the cache table."""
    tables = set(connection.introspection.django_table_names())
    tables.add(MigrationRecorder.Migration._meta.db_table)
    for cache in settings.CACHES.values():
        if cache["BACKEND"] == "django.core.cache.backends.db.DatabaseCache":
            tables.add(cache["LOCATION"])
    return sorted(tables)


def close_tables(cursor, tables):
    """Turns on row-level security on each of these tables that lacks it: one query when none does."""
    cursor.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity "
        "AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user) "
        "AND c.relname = ANY(%s) ORDER BY c.relname",
        [tables],
    )
    names = [row[0] for row in cursor.fetchall()]
    if names:
        cursor.execute(
            ";\n".join(
                "ALTER TABLE public.%s ENABLE ROW LEVEL SECURITY"
                % connection.ops.quote_name(name)
                for name in names
            )
        )
    return names


def schema_step(log):
    """The schema work of one start. Runs while the lock is held, on Django's own connection."""
    sql, manifest = read_snapshot()
    tables = app_tables()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = ANY(%s)",
            [sorted(set(tables) | set(manifest["tables"] if manifest else ()))],
        )
        present = cursor.fetchone()[0]

    done = None
    if present == 0 and manifest is not None:
        loader = MigrationLoader(None)
        held = {(app, name): digest for app, name, digest in manifest["migrations"]}
        if all(
            key in loader.disk_migrations
            and migration_digest(loader.disk_migrations[key]) == digest
            for key, digest in held.items()
        ):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "SET LOCAL statement_timeout = '%s';\n%s" % (SNAPSHOT_TIMEOUT, sql)
                )
            done = "empty database: applied the snapshot of %d migrations" % len(held)
            if any(key not in held for key in loader.graph.nodes):
                call_command("migrate", interactive=False, verbosity=1)
                done += ", then migrate for the migrations after it"
        else:
            log("tofu_schema: the snapshot does not match this code's migrations")
    if done is None:
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            call_command("migrate", interactive=False, verbosity=1)
            done = "applied the migrations left to apply"
        else:
            done = "up to date"

    with connection.cursor() as cursor:
        closed = close_tables(cursor, app_tables())
    if closed:
        done += "; turned on row-level security on %d tables" % len(closed)
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


def make_snapshot(log, path=SNAPSHOT_PATH):
    """Writes tofu_schema.sql from an EMPTY scratch PostgreSQL database: `migrate`, then pg_dump (on PATH)."""
    if connection.vendor != "postgresql":
        raise CommandError("--make-snapshot needs a PostgreSQL database")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public'"
        )
        if cursor.fetchone()[0]:
            raise CommandError("--make-snapshot needs an empty database")
    if not settings.BABY_BUDDY.get("FIRST_ACCOUNT_SETUP", False):
        raise CommandError("--make-snapshot needs Tofu's settings (no admin account)")
    call_command("migrate", interactive=False, verbosity=0)

    loader = MigrationLoader(connection)
    recorder = MigrationRecorder.Migration._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute("SELECT app, name FROM %s ORDER BY id" % recorder)
        applied = cursor.fetchall()
        cursor.execute("SELECT count(*) FROM auth_user")
        if cursor.fetchone()[0]:
            raise CommandError("migrate made an account; the snapshot must hold none")
    migrations = [
        [app, name, migration_digest(loader.disk_migrations[(app, name)])]
        for app, name in applied
    ]

    db = connection.settings_dict
    env = dict(os.environ, PGPASSWORD=db["PASSWORD"] or "")
    if db["OPTIONS"].get("sslmode"):
        env["PGSSLMODE"] = db["OPTIONS"]["sslmode"]
    dump = subprocess.run(
        [
            "pg_dump",
            "--host=%s" % db["HOST"],
            "--port=%s" % (db["PORT"] or 5432),
            "--username=%s" % db["USER"],
            "--dbname=%s" % db["NAME"],
            "--schema=public",
            "--no-owner",
            "--no-privileges",
            "--no-comments",
            "--no-publications",
            "--no-subscriptions",
            "--no-security-labels",
            "--no-tablespaces",
            "--inserts",
            "--rows-per-insert=1000",
            "--exclude-table-data=public.%s" % recorder,
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    # Keep the statements that make the schema and its rows. Drop pg_dump's session settings, which would stay on
    # the pooler's server connection after the transaction, its psql commands and the public schema (which exists).
    kept = []
    for line in dump.splitlines():
        if (
            not line
            or line.startswith("--")
            or line.startswith("\\")
            or line.startswith("SET ")
            or line.startswith("SELECT pg_catalog.set_config(")
            or line == "CREATE SCHEMA public;"
            or line.startswith("SELECT pg_catalog.setval('public.%s_id_seq'" % recorder)
        ):
            continue
        kept.append(line)
    body = "\n".join(kept)
    for word in ("COPY ", "OWNER TO", "GRANT ", "REVOKE ", "CREATE EXTENSION", "CREATE SCHEMA"):
        if word in body:
            raise CommandError("unexpected %r in pg_dump's output" % word)
    tables = [m[1] for m in re.findall(r'^CREATE TABLE public\.("?)(\w+)\1 \(', body, re.M)]

    rows = ",\n".join(
        "\t('%s', '%s', now())" % (app.replace("'", "''"), name.replace("'", "''"))
        for app, name, _ in migrations
    )
    rls = "\n".join(
        'ALTER TABLE public."%s" ENABLE ROW LEVEL SECURITY;' % name for name in tables
    )
    header = json.dumps({"migrations": migrations, "tables": tables})
    with open(path, "w", encoding="utf-8") as f:
        f.write(SNAPSHOT_HEADER + header + "\n")
        f.write(
            "-- Tofu (2026-10-26): generated by `manage.py tofu_schema --make-snapshot` (babybuddy/tofu_schema.py)"
            " from a database that upstream's migrations brought up to date with Tofu's settings. Do not edit.\n"
        )
        f.write(body + "\n")
        f.write(
            "INSERT INTO public.%s (app, name, applied) VALUES\n%s;\n" % (recorder, rows)
        )
        f.write(rls + "\n")
    log(
        "tofu_schema: wrote %s: %d migrations, %d tables"
        % (path, len(migrations), len(tables))
    )

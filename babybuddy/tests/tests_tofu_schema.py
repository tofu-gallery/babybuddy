# -*- coding: utf-8 -*-
# Tofu (2026-10-26): this file is Tofu's addition; it is not part of upstream Baby Buddy.
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase

from babybuddy import tofu_schema


class TofuSchemaSnapshotTestCase(SimpleTestCase):
    """babybuddy/tofu_schema.sql, the schema a copy's first start applies in one statement (TOFU.md)."""

    def setUp(self):
        self.sql, self.manifest = tofu_schema.read_snapshot()
        self.assertIsNotNone(self.manifest)

    def test_holds_exactly_this_codes_migrations(self):
        # A start only uses the snapshot for the migration files it was made from; after a change to the
        # migrations, make it again (`manage.py tofu_schema --make-snapshot`, see TOFU.md).
        loader = MigrationLoader(None)
        held = {(app, name): digest for app, name, digest in self.manifest["migrations"]}
        self.assertEqual(set(held), set(loader.graph.nodes))
        for key, digest in held.items():
            self.assertEqual(
                tofu_schema.migration_digest(loader.disk_migrations[key]), digest, key
            )

    def test_turns_on_row_level_security_on_every_table_of_the_app(self):
        self.assertEqual(sorted(self.manifest["tables"]), tofu_schema.app_tables())
        for table in self.manifest["tables"]:
            self.assertIn(
                'ALTER TABLE public."%s" ENABLE ROW LEVEL SECURITY;' % table, self.sql
            )

    def test_changes_no_setting_of_the_connection(self):
        # Through the transaction pooler a session setting would stay on the server connection for other clients.
        for line in self.sql.splitlines():
            self.assertFalse(line.startswith("SET "), line)
            self.assertFalse(line.startswith("\\"), line)
        self.assertNotIn("set_config(", self.sql)

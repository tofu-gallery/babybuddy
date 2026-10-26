# Tofu (2026-10-26): this file is Tofu's addition; it is not part of upstream Baby Buddy.
from django.core.management.base import BaseCommand

from babybuddy import tofu_schema


class Command(BaseCommand):
    help = (
        "Tofu: brings the database's schema up to date at a start, one start at a time "
        "(babybuddy/tofu_schema.py, TOFU.md)."
    )
    # Like `migrate`, which it replaces at a start: the system checks would only make the start slower.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--make-snapshot",
            action="store_true",
            help="Write babybuddy/tofu_schema.sql from an empty scratch PostgreSQL database (needs pg_dump).",
        )

    def handle(self, *args, **options):
        if options["make_snapshot"]:
            tofu_schema.make_snapshot(self.stdout.write)
        else:
            tofu_schema.start(self.stdout.write)

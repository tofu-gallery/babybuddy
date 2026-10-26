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

    def handle(self, *args, **options):
        tofu_schema.start(self.stdout.write)

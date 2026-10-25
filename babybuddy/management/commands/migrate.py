# -*- coding: utf-8 -*-
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.commands import migrate


class Command(migrate.Command):
    help = "Creates an initial User (admin/admin) for Baby Buddy."

    def handle(self, *args, **kwargs):
        super(Command, self).handle(*args, **kwargs)

        # Tofu (2026-10-25): no admin/admin account where the first account is made on the first-account page
        # instead (BABY_BUDDY["FIRST_ACCOUNT_SETUP"], babybuddy/first_account.py).
        if settings.BABY_BUDDY.get("FIRST_ACCOUNT_SETUP", False):
            return

        superusers = get_user_model().objects.filter(is_superuser=True)
        if len(superusers) == 0:
            default_user = get_user_model().objects.create_user(
                "admin", password="admin"
            )
            default_user.is_superuser = True
            default_user.is_staff = True
            default_user.save()

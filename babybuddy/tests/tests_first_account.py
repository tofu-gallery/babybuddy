# -*- coding: utf-8 -*-
# Tofu (2026-10-25): this file is Tofu's addition; it is not part of upstream Baby Buddy.
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse


def first_account_setup(enabled):
    return override_settings(
        BABY_BUDDY={**settings.BABY_BUDDY, "FIRST_ACCOUNT_SETUP": enabled}
    )


ACCOUNT = {
    "username": "parent",
    "password1": "a-long-sleepless-night",
    "password2": "a-long-sleepless-night",
}


class FirstAccountTestCase(TestCase):
    def setUp(self):
        # The test database was migrated with upstream's settings, which created admin/admin.
        get_user_model().objects.all().delete()

    @first_account_setup(True)
    def test_migrate_creates_no_account(self):
        call_command("migrate", verbosity=0)
        self.assertFalse(get_user_model().objects.exists())

    @first_account_setup(True)
    def test_first_account_becomes_administrator(self):
        page = reverse("babybuddy:first-account")
        self.assertRedirects(
            self.client.get(reverse("babybuddy:login")), page, target_status_code=200
        )
        response = self.client.post(page, ACCOUNT)
        self.assertRedirects(
            response, reverse("babybuddy:root-router"), fetch_redirect_response=False
        )
        user = get_user_model().objects.get()
        self.assertEqual(user.username, "parent")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("a-long-sleepless-night"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

        # Closed once an account exists.
        self.client.logout()
        self.assertRedirects(self.client.get(page), reverse("babybuddy:login"))
        response = self.client.post(page, {**ACCOUNT, "username": "someone-else"})
        self.assertRedirects(response, reverse("babybuddy:login"))
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(self.client.get(reverse("babybuddy:login")).status_code, 200)

    @first_account_setup(True)
    def test_invalid_account_is_refused(self):
        response = self.client.post(
            reverse("babybuddy:first-account"),
            {**ACCOUNT, "password2": "something-else-entirely"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.exists())

    @first_account_setup(False)
    def test_off_keeps_upstream_login(self):
        self.assertEqual(self.client.get(reverse("babybuddy:login")).status_code, 200)
        self.assertRedirects(
            self.client.get(reverse("babybuddy:first-account")),
            reverse("babybuddy:login"),
        )
        call_command("migrate", verbosity=0)
        self.assertTrue(get_user_model().objects.filter(username="admin").exists())

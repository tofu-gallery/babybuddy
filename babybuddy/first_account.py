# -*- coding: utf-8 -*-
# Tofu (2026-10-25): this file is Tofu's addition; it is not part of upstream Baby Buddy.
"""
The first account of a copy that has none, for BABY_BUDDY["FIRST_ACCOUNT_SETUP"] (set by
babybuddy.settings.tofu). Upstream's migrate command creates an admin/admin account instead, which on a public
address would let anyone in. With the setting on, migrate creates no account, and while the app has no account
at all the login page sends visitors to this page, where the first account is created as the administrator. Once
any account exists the page is closed: it sends visitors to the login page, and the administrator adds everyone
else under Users. With the setting off (upstream's settings modules), nothing here changes upstream's behaviour.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView as LoginViewBase
from django.db import connection, transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.generic import View

# A fixed key for the transaction-scoped PostgreSQL lock that two first-account requests queue on, so only one
# of them can create the administrator.
FIRST_ACCOUNT_LOCK = 0x62620001


def setup_enabled():
    return settings.BABY_BUDDY.get("FIRST_ACCOUNT_SETUP", False)


def setup_open():
    """Whether the first-account page is offered: the setting is on and the app has no account at all."""
    return setup_enabled() and not get_user_model().objects.exists()


class FirstAccountForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username",)


class LoginView(LoginViewBase):
    """Django's login view, which sends visitors to the first-account page while that page is open."""

    def dispatch(self, request, *args, **kwargs):
        if setup_open():
            return redirect("babybuddy:first-account")
        return super().dispatch(request, *args, **kwargs)


class FirstAccount(View):
    template_name = "registration/first_account.html"

    def get(self, request):
        if not setup_open():
            return redirect("babybuddy:login")
        return render(request, self.template_name, {"form": FirstAccountForm()})

    def post(self, request):
        if not setup_open():
            return redirect("babybuddy:login")
        form = FirstAccountForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(%s)", [FIRST_ACCOUNT_LOCK]
                    )
            # Checked again under the lock: another request may have created the first account meanwhile.
            if get_user_model().objects.exists():
                return redirect("babybuddy:login")
            user = form.save(commit=False)
            user.is_superuser = True
            user.is_staff = True
            user.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(
            request,
            _(
                "Your account is ready, and it is this Baby Buddy's administrator. "
                "Add other people under Users."
            ),
        )
        return redirect("babybuddy:root-router")

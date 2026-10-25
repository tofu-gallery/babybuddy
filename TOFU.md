# Tofu gallery copy

This repository is Tofu's copy of **babybuddy/babybuddy** (licence: BSD-2-Clause), listed in Tofu's app gallery as a **baby care log**: Baby Buddy, where the people who look after a baby record its feedings, sleep, diaper changes, tummy time, pumping, medication, temperature and growth, and see them on dashboards, a timeline and charts.

- `master` mirrors the upstream repository and is never committed to by Tofu.
- `tofu` carries Tofu's own changes; tags named `pin/<date>` mark the versions the gallery points to. The current pin is `pin/2026-10-25`.
- A visitor who chooses this app gets a private snapshot of the pinned version in their own Tofu account. Their copy does not follow upstream updates.
- Upstream: https://github.com/babybuddy/babybuddy at `09629cf633cf3a2059a21ade4cea7ea4d846422f` (2026-10-12, v2.11.0 plus 34 commits).

## How Tofu runs it

- Framework preset `container`, root folder: the repository root. Tofu builds the root `Dockerfile` and runs the image as a service, so there is no separate install command, build command or output directory.
- The `Dockerfile` is Tofu's own (upstream has none at its root). It starts from `python:3.13-slim`, installs `requirements.txt` with pip (every requirement has a Linux wheel for Python 3.13, so nothing is compiled), copies the repository and starts `tofu-entrypoint.sh`. Upstream commits its compiled styles, scripts, icon font and images under `static/`, together with WhiteNoise's manifest, so the image runs no Node build (`gulp`) and no `collectstatic`.
- `tofu-entrypoint.sh` does what upstream's `Procfile.sh` does: `python manage.py migrate --noinput`, retried up to five times five seconds apart while a new database is still starting, then `gunicorn babybuddy.wsgi:application` on `0.0.0.0:$PORT` (80 without `PORT`) with `WEB_CONCURRENCY` workers (2 when unset).
- Settings: the image sets `DJANGO_SETTINGS_MODULE=babybuddy.settings.tofu`, which takes upstream's `babybuddy/settings/base.py` and changes only what is listed under "What Tofu changes".
- Database: PostgreSQL, the app's Tofu database, read from `DATABASE_URL` by upstream's own settings (`dj-database-url`). The tables come from Django's migrations, which run at every start; the cache table `cache_default` is made by upstream's migration `babybuddy/0029`. The repository has no `supabase/migrations` folder, so Tofu applies no SQL of its own, and the tables the app makes stay closed to the database's public Data API.
- Environment: Tofu sets `PORT` and `DATABASE_URL`, and a gallery copy saves `CSRF_TRUSTED_ORIGINS` set to the copy's own address. Nothing has to be set by hand before the first deploy. Settings an owner may add are named below: `SECRET_KEY`, the photo settings, the mail settings, and `CSRF_TRUSTED_ORIGINS` or `ALLOWED_HOSTS` for a domain of their own.
- Upstream's files for other hosts (`Procfile`, `Procfile.sh`, `.buildpacks`, `runtime.txt`, `nixpacks.toml`, `.do/`, `terraform/`) stay as they are; Tofu uses none of them.

## What Tofu changes

- `babybuddy/settings/tofu.py` (new), on top of upstream's `base.py`:
  - `ALLOWED_HOSTS = ["*"]` unless `ALLOWED_HOSTS` is set. Upstream's default is one empty host name, which with `DEBUG` off answers every request with 400, and the image cannot know the copy's address.
  - `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` and `USE_X_FORWARDED_HOST = True`. Tofu serves the app over HTTPS through its own proxy, so Django reads the scheme and host the visitor used from the proxy's headers. Django's CSRF check compares every form's `Origin` with them.
  - `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` are true unless set to false (upstream: false).
  - When `DATABASE_URL` is set: `DISABLE_SERVER_SIDE_CURSORS = True`, because Tofu's `DATABASE_URL` goes through a transaction pooler, which keeps no cursor from one transaction to the next; and `CONN_MAX_AGE = 60` with `CONN_HEALTH_CHECKS = True`, so each worker keeps its connection for a minute, checked before reuse, instead of opening a TLS connection for every request.
  - When `SECRET_KEY` is not set and `DATABASE_URL` is, `SECRET_KEY` is the SHA-256 of `baby-buddy-secret-key:` followed by the whole `DATABASE_URL`, written as 64 hex characters. See "The secret key".
  - `BABY_BUDDY["ALLOW_UPLOADS"]` is false unless `ALLOW_UPLOADS` is set (upstream: true). See "What works differently on Tofu".
  - `BABY_BUDDY["FIRST_ACCOUNT_SETUP"] = True`. See "The first account".
- `babybuddy/settings/.gitignore`: names `tofu.py`, because this folder's `.gitignore` ignores every file it does not name.
- `babybuddy/management/commands/migrate.py`: upstream's `migrate` creates a superuser `admin` with the password `admin` whenever there is no superuser. On a public address anyone could sign in with it. With `BABY_BUDDY["FIRST_ACCOUNT_SETUP"]` on, it creates no account. Upstream's settings modules leave the setting off, so their behaviour and upstream's tests are unchanged.
- `babybuddy/first_account.py` (new), `babybuddy/templates/registration/first_account.html` (new) and `babybuddy/urls.py`: the first-account page at `/first-account/`, and the login page, now Django's own login view with one addition: while the setting is on and the app has no account, it sends visitors to the first-account page.
- `babybuddy/tests/tests_first_account.py` (new): the page creating the administrator, the page closed once an account exists, a refused form, and `migrate` with the setting on and off.
- `requirements.txt` and `Pipfile`: Pillow 13.0.0 instead of 12.3.0, and Django REST framework 3.18.3 instead of 3.18.1. Between 2026-10-20 and 2026-10-23, after upstream's last commit, GitHub published advisories for both pinned versions: memory errors in Pillow's image decoders, some rated critical (fixed in 13.0.0), and in Django REST framework, among others, a denial of service through the `Accept` header that needs no sign-in (fixed in 3.18.2). A copy does not follow upstream, so this pin takes the fixed versions. Pillow 13 needs Python 3.11 or later, so its line in `requirements.txt` now says `python_version >= '3.11'`.
- `Dockerfile` and `tofu-entrypoint.sh` (new): see "How Tofu runs it".

Nothing upstream was removed. Tofu's safety check has no finding on the repository, upstream's GitHub Actions workflow included (see "Verification").

## The first account

- A new copy has no account. Until one exists, the login page, and so the copy's address, opens "Create the first account". The account made there is a superuser: Baby Buddy's administrator, who adds everyone else (parents, caregivers, read-only users) under the account menu's **Users**.
- Once any account exists, the page closes: it sends visitors to the login page. Baby Buddy has no sign-up of its own, so after that nobody can make an account for themselves, and there is no sign-up setting to close.
- Whoever opens a new copy first gets that page. The owner should open their copy and create their account as soon as it is online. To keep everyone else out even before that, the owner can make the app private on Tofu (people they choose, or an access code) before opening it.
- Each account's time zone is UTC until its user sets it under the account menu's **Settings**; times are entered and shown in that time zone.

## The secret key

- Django signs sign-in sessions and password-reset links with `SECRET_KEY`. Tofu supplies none, so a copy derives one from `DATABASE_URL` at every start (above), and starts with nothing set by hand.
- Anything that changes `DATABASE_URL` changes the key at the next start: a new database password, a different host or pooler address, other query options, or a database Tofu brings back or creates anew under another address. After that start everyone is signed out and has to sign in again, and password-reset links sent before stop working. Accounts, passwords, API keys and the log itself are kept in the database and are not affected.
- To keep sessions independent of the database address, save `SECRET_KEY` as a hidden value on the app's Keys & settings page (for example the output of `openssl rand -base64 48`) and deploy again; that change signs everyone out once.
- The derived key is only as secret as `DATABASE_URL`, which Tofu keeps as a hidden value.

## What works differently on Tofu

- **Child photos are off.** Upstream lets you upload a picture of each child into `media/` on the server's disk. A copy has no lasting disk, so a photo would be lost at the next restart, and with `DEBUG` off nothing serves that folder anyway. To turn photos on, set `ALLOW_UPLOADS=true` and point Baby Buddy at an S3-compatible bucket: `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL` for a bucket that is not on Amazon S3, and the bucket's keys `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as hidden values; then deploy again. The web forms then offer the picture field.
- **The REST API still takes a child's picture.** Upstream's API (`/api/children/`) accepts a `picture` whatever `ALLOW_UPLOADS` says. Without a bucket, a picture sent there is written to the container's disk and lost at the next restart. Only a signed-in account allowed to add or change children can send one.
- **Password-reset mail goes to the app's log.** Without `EMAIL_HOST`, Baby Buddy's mail backend is the console, so "Forgot your password?" writes the reset mail, link included, to the app's runtime log instead of sending it. Only the owner can read that log. To send mail, set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_USE_TLS` or `EMAIL_USE_SSL`, `EMAIL_FROM`, and `EMAIL_HOST_PASSWORD` as a hidden value. An administrator can also set anyone's password in the account menu's **Database Admin** (`/admin/`).
- **Migrations run at every start**, as upstream's `Procfile.sh` does. Two instances starting at the same moment on a database that is behind would both try to apply the same migration; in the one that loses, PostgreSQL rolls that migration back whole, and `tofu-entrypoint.sh` runs `migrate` again five seconds later, when there is nothing left to apply.
- **The account menu's "Source Code" and "Chat / Support" links** open upstream's repository and chat room. BSD-2-Clause does not ask a copy to offer its own source, so they stay as upstream has them.
- Upstream's other switches keep upstream's defaults: Home Assistant support and reverse-proxy sign-in are off, and `DEBUG` is off.

## Needs a real deploy to verify

- The image builds on Tofu's container hosting: `python:3.13-slim` from Docker Hub, and 47 packages from PyPI, all as wheels.
- The first start applies all 107 migrations through Tofu's transaction pooler, within the time Tofu waits for a new app to answer. `/` then answers through two redirects (`/login/`, then `/first-account/`, which answers 200).
- Which scheme and host Tofu's proxy passes on. Forms (signing in included) work when either the scheme and host Django reads from the proxy's headers, or `CSRF_TRUSTED_ORIGINS`, match the address in the visitor's browser; when neither does, every form answers Baby Buddy's "CSRF verification failed" page, which names the address it refused. A domain the owner connects later works through the proxy's headers; if it does not, add its `https://` address to `CSRF_TRUSTED_ORIGINS`, separated by a comma.
- Kept connections through the pooler: the runtime logs show no `server closed the connection unexpectedly` and no cursor errors.
- Whether sign-in lockout sees each visitor's own address. Baby Buddy (django-axes) locks an address out for an hour after five failed sign-ins, and reads the address from `X-Forwarded-For`. If Tofu's proxy passed one address for everyone, five failures from anyone would lock everyone out; if it passed a visitor's own `X-Forwarded-For` unchecked, a visitor could dodge the lockout.

## Licence

- BSD-2-Clause. `LICENSE` and every copyright notice stay exactly as upstream has them. Every upstream file Tofu changed carries a dated `Tofu (2026-10-25)` comment at the change, except `requirements.txt` and `Pipfile`, whose two version changes this file and their commit explain. Every new file says at its top that it is Tofu's addition.
- `static/` is upstream's collected static files: its compiled styles and scripts, which bundle Bootstrap, Popper, jQuery, Masonry, Plotly.js and PullToRefresh.js, and the static files of Django's admin, Django REST framework and django-import-export, each under its own project's licence. The icon font is built with Fontello from Font Awesome, MFG Labs and Entypo icons, under the SIL Open Font License (`babybuddy/static_src/fontello/LICENSE.txt`). `locale/` holds upstream's translations.
- The Baby Buddy name and logo belong to the upstream project; the gallery uses them only to say which app this is.

## Verification

2026-10-25, on macOS arm64 against 127.0.0.1 only. No Docker, nothing deployed. Python 3.13.16 and a scratch PostgreSQL 14.

- Tofu's own check (the GitHub import of the pushed ref, then Tofu's static-lane and safety predicates). On upstream's `master`: `detect=django files= 1288 published=1223 -> not on the static lane ... safety ok (0 findings)`. On `tofu` at `6866be0`, the last commit before this file was added: `detect=container files= 1294 published=1229 -> not on the static lane ... safety ok (0 findings)`, then `free static limit: 1229/500 published files | archive 200 12008163`. The app is not a finished site, so that limit does not apply to it: it runs on Tofu's server hosting.
- Wheels: `pip install --dry-run --only-binary=:all:` for CPython 3.13 on manylinux x86_64 and on aarch64 resolved all 47 packages of this `requirements.txt` to wheels. The four with compiled code are Pillow 13.0.0, psycopg2-binary 2.9.13, pydantic-core 2.46.5 and PyYAML 6.0.3. So the image's `pip install` compiles nothing.
- Upstream's full test suite, `DJANGO_SETTINGS_MODULE=babybuddy.settings.test python manage.py test --parallel 1`, in a virtualenv with `pip install -r requirements.txt`: 532 tests OK (upstream's 528 and the 4 new ones), both with upstream's Pillow 12.3.0 and Django REST framework 3.18.1 and with this pin's 13.0.0 and 3.18.3. Run with `-W default`, the second run printed no warning from Pillow, Django REST framework, django-imagekit or pilkit.
- Run as the container would, on this pin's packages: an empty database, `DJANGO_SETTINGS_MODULE=babybuddy.settings.tofu`, `PORT`, `DATABASE_URL=postgresql://…@127.0.0.1:5432/…?sslmode=disable` (the scratch server has no TLS), no `SECRET_KEY` and no `ALLOWED_HOSTS`, started through a copy of `tofu-entrypoint.sh` that binds 127.0.0.1 instead of 0.0.0.0 and changes to the checkout's folder. `migrate` applied 107 migrations and gunicorn answered 3 seconds after the start. `GET /` answered 302 to `/login/?next=/`, `/login/` 302 to `/first-account/`, `/first-account/` 200, and `/static/babybuddy/css/app.css` 200. The database had no account, so no `admin`.
- Headless Chromium (Playwright, 127.0.0.1 only), on this pin's packages: `/` opened "Create the first account"; creating `parent` reached `/welcome/` with "Your account is ready, and it is this Baby Buddy's administrator. Add other people under Users."; the add-child form had no picture field; a child and a bottle feeding (formula, 120, 08:00 to 08:20) were added, and the feeding list showed the feeding. After signing out, `/first-account/` sent the browser to `/login/`, and signing in again reached the child's dashboard. The session cookie was `Secure`. No page error, no console error, no response of 400 or more. The database read back `Robin Tofu | formula | bottle | 120 | 2026-10-25 08:00 UTC`, and `parent` as superuser and staff; the REST API (`/api/feedings/`, `/api/children/`) read back the same feeding and the child with no picture, and answered 403 without a session.
- CSRF behind a proxy, with curl and the headers Tofu's proxy is expected to send (`X-Forwarded-Proto: https`, `X-Forwarded-Host: copy.example`), run on upstream's Pillow and Django REST framework versions (the check involves neither): a form posted with `Origin: https://copy.example` was accepted (200, the form again with its password error), one posted with `Origin: https://evil.example` was refused (403), and one posted without the forwarded headers was refused (403) until the app was restarted with `CSRF_TRUSTED_ORIGINS=https://copy.example`, then accepted (200). The session and CSRF cookies carried `Secure`.
- Restart on the same database, also on upstream's versions: `No migrations to apply.`, a session signed in before the restart still worked (the derived key did not change), and the database still held only `parent`.
- `python manage.py check --deploy` with these settings: only `security.W004` (`SECURE_HSTS_SECONDS`) and `security.W008` (`SECURE_SSL_REDIRECT`), both left to Tofu's HTTPS front.
- The settings in effect, printed with `manage.py shell` and a `DATABASE_URL` ending in `?sslmode=require`: engine `django.db.backends.postgresql`, `OPTIONS {'sslmode': 'require'}`, `DISABLE_SERVER_SIDE_CURSORS True`, `CONN_MAX_AGE 60`, `CONN_HEALTH_CHECKS True`, a derived `SECRET_KEY` of 64 characters, `ALLOWED_HOSTS ['*']`, uploads off, the first-account page on, `DEBUG False`.
- Not run here: the image itself (no Docker on this machine), the transaction pooler (the scratch database was reached directly), and anything on Tofu.
- Every local server was stopped and the scratch database dropped afterwards.

# Tofu (2026-10-25): this file is Tofu's addition; it is not part of upstream Baby Buddy.
#
# The image Tofu builds and runs for a copy of Baby Buddy (framework preset `container`, see TOFU.md). The
# compiled styles and scripts are already committed under static/ (with WhiteNoise's manifest), so the image
# needs no Node build and no collectstatic. tofu-entrypoint.sh brings the database's schema up to date
# (babybuddy/tofu_schema.py), then starts gunicorn on PORT.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    DJANGO_SETTINGS_MODULE=babybuddy.settings.tofu

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . ./

EXPOSE 80
CMD ["/bin/sh", "/app/tofu-entrypoint.sh"]

# Multi-arch base: resolves to linux/arm64 on the t4g box, amd64 for local builds.
FROM python:3.12-slim

# get_build_version() checks APP_VERSION first, so the footer works without git
# or version.txt inside the image (neither exists here).
ARG APP_VERSION=docker
ENV APP_VERSION=$APP_VERSION

# expenses.db lives on the mounted volume, never in the image layer.
ENV DB_PATH=/data/expenses.db
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ templates/

# Non-root. The uid is pinned because the host data directory must be chowned to
# it -- see deploy/DOCKER-RESTORE.md. The home directory is real and writable
# because gunicorn's control server writes there on startup; without it the
# worker still serves but logs "Control server error: Permission denied".
RUN useradd --uid 10001 --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && mkdir -p /data && chown app:app /data
USER app

EXPOSE 5000

# init_db() is CREATE TABLE IF NOT EXISTS throughout, so running it on every
# start builds the schema on a fresh volume and is a no-op on a restored one.
CMD ["sh", "-c", "python -c 'import app; app.init_db()' && exec gunicorn --workers 2 --bind 0.0.0.0:5000 app:app"]

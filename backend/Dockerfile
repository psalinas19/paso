# The review backend as one image: the API, the daily backup that runs inside
# it, and rclone to copy those backups off the server.
#
# Build from backend/:   docker build -t paso-backend .
FROM python:3.12-slim-bookworm

# rclone copies the backups off the server. One static binary, taken from its
# official image at a fixed version.
COPY --from=rclone/rclone:1.76.0 /usr/local/bin/rclone /usr/local/bin/rclone

# uv installs exactly what uv.lock says (SPEC 12.7: pinned, deliberate updates).
RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /srv/backend
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# Not root: a bug in the API should not own the machine. /data and /backups are
# the only places it writes; mount volumes there.
RUN useradd --system --uid 10001 --home /srv/backend paso \
    && mkdir -p /data /backups \
    && chown -R paso:paso /data /backups /srv/backend
USER paso

ENV PATH="/srv/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    BACKUP_DIR=/backups \
    BACKUP_ENABLED=true \
    RECOGNITION_CACHE_ENABLED=false

EXPOSE 8000
VOLUME ["/data", "/backups"]

# One process: the SQLite file and the verifier's worker are not made to be shared.
CMD ["python", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

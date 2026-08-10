FROM ghcr.io/astral-sh/uv:0.10 AS uv
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH

RUN groupadd --system vigor && useradd --system --gid vigor --home /app vigor
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY README.md /app/README.md
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN uv sync --directory /app/backend --locked --no-dev --all-extras --no-install-project
COPY backend /app/backend
COPY deploy/docker/backend-entrypoint.sh /usr/local/bin/backend-entrypoint
RUN uv sync --directory /app/backend --locked --no-dev --all-extras \
    && chmod +x /usr/local/bin/backend-entrypoint \
    && mkdir -p /data/media /data/erasure-ledger \
    && chown -R vigor:vigor /app /data

USER vigor
WORKDIR /app/backend
ENTRYPOINT ["backend-entrypoint"]
CMD ["uvicorn", "vigor_vine.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
USER root
RUN uv sync --directory /app/backend --locked --all-extras \
    && chown -R vigor:vigor /app
USER vigor
ENTRYPOINT []

FROM runtime AS production

FROM ghcr.io/astral-sh/uv:0.10 AS uv
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    NLTK_DATA=/usr/local/share/nltk_data \
    PATH=/app/.venv/bin:$PATH

RUN groupadd --system cookfully && useradd --system --gid cookfully --home /app cookfully
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY README.md /app/README.md
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN uv sync --directory /app/backend --locked --no-dev --all-extras --no-install-project
# ingredient-parser-nlp otherwise downloads this small tagger separately in
# every API/worker container on each restart. Bundle it once in the image so
# startup is offline, quiet, and deterministic.
RUN mkdir -p "$NLTK_DATA" \
    && /app/.venv/bin/python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng', download_dir='$NLTK_DATA', quiet=True)"
COPY backend /app/backend
COPY deploy/docker/backend-entrypoint.sh /usr/local/bin/backend-entrypoint
RUN uv sync --directory /app/backend --locked --no-dev --all-extras \
    && sed -i 's/\r$//' /usr/local/bin/backend-entrypoint \
    && chmod +x /usr/local/bin/backend-entrypoint \
    && mkdir -p /data/media /data/semantic-models /data/exports /data/erasure-ledger \
    && chown -R cookfully:cookfully /app /data

USER cookfully
WORKDIR /app/backend
ENTRYPOINT ["backend-entrypoint"]
CMD ["uvicorn", "cookfully.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
USER root
RUN uv sync --directory /app/backend --locked --all-extras \
    && chown -R cookfully:cookfully /app
USER cookfully
ENTRYPOINT []

FROM runtime AS production

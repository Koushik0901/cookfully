FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN groupadd --system cookfully && useradd --system --gid cookfully --home /app cookfully
WORKDIR /app

# Needle is deliberately isolated from the application image. The model file
# is supplied through the model volume so it can be upgraded independently.
RUN pip install --no-cache-dir --disable-pip-version-check \
    "cactus-needle>=2,<3" \
    "fastapi>=0.116,<1" \
    "uvicorn[standard]>=0.35,<1" \
    "pydantic>=2.11,<3"
COPY backend/src/cookfully/intelligence /app/cookfully/intelligence
RUN mkdir -p /models && chown -R cookfully:cookfully /app /models

USER cookfully
EXPOSE 8091
CMD ["uvicorn", "cookfully.intelligence.service:app", "--host", "0.0.0.0", "--port", "8091"]

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    NEEDLE_TELEMETRY=0

RUN groupadd --system cookfully && useradd --system --gid cookfully --home /app cookfully
WORKDIR /app

# Needle is deliberately isolated from the application image. The model file
# is supplied through the model volume so it can be upgraded independently.
RUN pip install --no-cache-dir --disable-pip-version-check \
    "cactus-needle>=2,<3" \
    "fastapi>=0.116,<1" \
    "uvicorn[standard]>=0.35,<1" \
    "pydantic>=2.11,<3"

# Bundle the small platform engine so the first request does not need an
# outbound Hugging Face download.  The model archive itself remains in the
# persistent host volume and can be upgraded independently.
ARG TARGETARCH
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) needle_arch="x86_64"; needle_sha="13a84e6c73095fd175b11d46a30a984b62123d94421b769c107074aff7f65c2b" ;; \
      arm64) needle_arch="aarch64"; needle_sha="e655a13f9d3239e601936ff2d0f6acafd8f6020aaf7b1862ce4fceefacfd6556" ;; \
      *) echo "Unsupported TARGETARCH for Needle2: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    needle_wheel="/tmp/cactus_needle-2.0.4-py3-none-manylinux2014_${needle_arch}.whl"; \
    python - "$needle_wheel" "$needle_sha" "$needle_arch" <<'PY'
import hashlib
import io
import os
import sys
import urllib.request
import zipfile

wheel_path, expected_sha, arch = sys.argv[1:]
url = (
    "https://huggingface.co/Cactus-Compute/needle2/resolve/main/python/"
    f"cactus_needle-2.0.4-py3-none-manylinux2014_{arch}.whl?download=true"
)
data = urllib.request.urlopen(url, timeout=120).read()
actual_sha = hashlib.sha256(data).hexdigest()
if actual_sha != expected_sha:
    raise SystemExit(f"Needle2 engine checksum mismatch: {actual_sha}")
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    library = archive.read("needle/libneedle.so")
open("/usr/local/lib/libneedle.so", "wb").write(library)
os.chmod("/usr/local/lib/libneedle.so", 0o755)
PY

ENV NEEDLE2_LIB_PATH=/usr/local/lib/libneedle.so
COPY backend/src/cookfully/intelligence /app/cookfully/intelligence
RUN mkdir -p /models && chown -R cookfully:cookfully /app /models

USER cookfully
EXPOSE 8091
CMD ["uvicorn", "cookfully.intelligence.service:app", "--host", "0.0.0.0", "--port", "8091"]

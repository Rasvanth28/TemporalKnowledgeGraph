# Production image for the read API (graphdb.api). Ingestion runs separately (GitHub Actions),
# so spaCy / scikit-learn are not installed here.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LOG_FORMAT=json \
    PORT=8000

WORKDIR /app

COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

# Bake the embedding model (~30 MB) into the image: no download at startup, works offline.
ENV HF_HOME=/app/.hf
RUN python -c "from model2vec import StaticModel; StaticModel.from_pretrained('minishlab/potion-base-8M')"
ENV HF_HUB_OFFLINE=1

COPY common/ common/
COPY graphdb/ graphdb/
RUN rm -rf graphdb/tests && useradd --create-home --uid 10001 api && chown -R api /app/.hf
USER api

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=4)"

# Render (and most hosts) terminate TLS at a proxy and pass the port in $PORT.
CMD ["sh", "-c", "exec uvicorn graphdb.api:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]

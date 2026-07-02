FROM python:3.12.13-slim
WORKDIR /app
COPY pyproject.toml uv.lock* ./
COPY apps ./apps
COPY packages ./packages
COPY docker-compose.yml ./
COPY docker ./docker
COPY services ./services
COPY third_party ./third_party
COPY configs ./configs

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN git config --system --add safe.directory /app/third_party/upstream/ToolUniverse \
    && git config --system --add safe.directory /app/third_party/upstream/OptimusKG \
    && git config --system --add safe.directory /app/third_party/upstream/Medea

RUN pip install --no-cache-dir uv && uv pip install --system pydantic fastapi uvicorn httpx gradio pytest pymupdf python-multipart "psycopg[binary]>=3.3.0"
ENV PYTHONPATH=/app/packages/translume-schemas/src:/app/packages/translume-ports/src:/app/packages/translume-core/src:/app/packages/translume-clients/src:/app/packages/translume-adapters/src:/app/apps/translume-api/src:/app/apps/translume-ui/src:/app/services/docling-service/src:/app/services/optimuskg-service/src:/app/services/tooluniverse-service/src:/app/services/medea-service/src:/app/services/worker/src
CMD ["sh", "-lc", "uvicorn translume_api.main:app --host 0.0.0.0 --port 8080"]

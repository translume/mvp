FROM python:3.12.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY docker/runtime-requirements.txt /tmp/runtime-requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/runtime-requirements.txt
COPY pyproject.toml uv.lock docker-compose.yml ./
COPY packages ./packages
COPY apps ./apps
COPY services ./services
COPY configs ./configs
COPY scripts ./scripts
COPY docker ./docker
COPY third_party ./third_party
RUN python scripts/install_packaged_vendors.py \
    && useradd --create-home --uid 1000 translume \
    && mkdir -p /data/uploads /data/audit \
    && chown translume:translume /data/uploads /data/audit
ENV PYTHONPATH=/app:/app/packages/translume-adapters/src:/app/packages/translume-clients/src:/app/packages/translume-core/src:/app/packages/translume-ports/src:/app/packages/translume-schemas/src:/app/apps/translume-api/src:/app/apps/translume-ui/src:/app/services/docling-service/src:/app/services/medea-service/src:/app/services/optimuskg-service/src:/app/services/tooluniverse-service/src:/app/services/worker/src
USER translume
CMD ["python", "-m", "uvicorn", "tooluniverse_service.main:app", "--host", "0.0.0.0", "--port", "8092"]

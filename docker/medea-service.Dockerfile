FROM python:3.12.13-slim
WORKDIR /app
COPY pyproject.toml uv.lock* ./
COPY apps ./apps
COPY packages ./packages
COPY services ./services
COPY third_party ./third_party
COPY configs ./configs
RUN pip install --no-cache-dir uv \
    && uv pip install --system pydantic fastapi uvicorn httpx gradio pytest numpy h5py \
    && for repo in /app/third_party/upstream/*; do \
        if [ -f "$repo/pyproject.toml" ] || [ -f "$repo/setup.py" ]; then \
          uv pip install --system -e "$repo"; \
        fi; \
      done
ENV PYTHONPATH=/app/packages/translume-schemas/src:/app/packages/translume-ports/src:/app/packages/translume-core/src:/app/packages/translume-clients/src:/app/packages/translume-adapters/src:/app/apps/translume-api/src:/app/apps/translume-ui/src:/app/services/docling-service/src:/app/services/optimuskg-service/src:/app/services/tooluniverse-service/src:/app/services/medea-service/src:/app/services/worker/src
CMD ["sh", "-lc", "uvicorn medea_service.main:app --host 0.0.0.0 --port 8093"]

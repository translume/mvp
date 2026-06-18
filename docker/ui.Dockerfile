FROM python:3.12.13-slim
WORKDIR /app
COPY pyproject.toml uv.lock* ./
COPY apps ./apps
COPY packages ./packages
COPY services ./services
COPY third_party ./third_party
COPY configs ./configs
RUN pip install --no-cache-dir uv && uv pip install --system pydantic fastapi uvicorn httpx 'gradio>=6.0.0,<7.0.0' plotly pytest
ENV PYTHONPATH=/app/packages/translume-schemas/src:/app/packages/translume-ports/src:/app/packages/translume-core/src:/app/packages/translume-clients/src:/app/packages/translume-adapters/src:/app/apps/translume-api/src:/app/apps/translume-ui/src:/app/services/docling-service/src:/app/services/optimuskg-service/src:/app/services/tooluniverse-service/src:/app/services/medea-service/src:/app/services/worker/src
CMD ["python", "-m", "translume_ui.app"]

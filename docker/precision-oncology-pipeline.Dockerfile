FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY precision_oncology_json_pipeline/pyproject.toml \
    precision_oncology_json_pipeline/README.md \
    precision_oncology_json_pipeline/precision_oncology_pipeline.py \
    ./
COPY docker/precision-oncology-pipeline-entrypoint.sh \
    /usr/local/bin/precision-oncology-pipeline-entrypoint

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 1000 pipeline \
    && chmod 0755 /usr/local/bin/precision-oncology-pipeline-entrypoint

ENTRYPOINT ["precision-oncology-pipeline-entrypoint"]
CMD ["sleep", "infinity"]

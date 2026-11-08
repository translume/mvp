FROM python:3.12.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY docker/runtime-requirements.txt /tmp/runtime-requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/runtime-requirements.txt
COPY precision_oncology_json_pipeline/ /app/
COPY docker/precision-oncology-pipeline-entrypoint.sh /usr/local/bin/precision-oncology-pipeline-entrypoint
RUN useradd --create-home --uid 1000 pipeline \
    && chmod 0755 /usr/local/bin/precision-oncology-pipeline-entrypoint
ENTRYPOINT ["precision-oncology-pipeline-entrypoint"]
CMD ["python", "-m", "uvicorn", "precision_oncology_runner:app", "--host", "0.0.0.0", "--port", "8094"]

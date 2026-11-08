FROM python:3.12.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY docker/runtime-requirements.txt /tmp/runtime-requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/runtime-requirements.txt
COPY dynamic_pathway_analyzer/ /app/
COPY docker/dynamic-pathway-analyzer-entrypoint.sh /usr/local/bin/dynamic-pathway-analyzer-entrypoint
RUN useradd --create-home --uid 1000 analyzer \
    && chmod 0755 /usr/local/bin/dynamic-pathway-analyzer-entrypoint
ENTRYPOINT ["dynamic-pathway-analyzer-entrypoint"]
CMD ["python", "-m", "uvicorn", "dynamic_pathway_runner:app", "--host", "0.0.0.0", "--port", "8095"]

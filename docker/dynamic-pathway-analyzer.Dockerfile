FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY dynamic_pathway_analyzer/requirements.txt /tmp/requirements.txt
COPY docker/dynamic-pathway-analyzer-entrypoint.sh \
    /usr/local/bin/dynamic-pathway-analyzer-entrypoint

RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --create-home --uid 1000 analyzer \
    && chmod 0755 /usr/local/bin/dynamic-pathway-analyzer-entrypoint

ENTRYPOINT ["dynamic-pathway-analyzer-entrypoint"]
CMD ["sleep", "infinity"]

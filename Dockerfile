# Nightwire game server (FastAPI + websockets). Build context = repo root.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SESSION_STORE_DIR=/data/sessions

WORKDIR /app

COPY pyproject.toml ./
COPY ruleset/ ruleset/
COPY engine/ engine/
COPY server/ server/
COPY narrator/ narrator/
RUN pip install .

RUN useradd --create-home --uid 10001 nightwire \
    && mkdir -p "$SESSION_STORE_DIR" \
    && chown -R nightwire /data
USER nightwire

EXPOSE 8000
VOLUME ["/data/sessions"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/docs', timeout=2)"

CMD ["python", "-m", "server"]

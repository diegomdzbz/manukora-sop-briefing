# The engine, as a service n8n can reach over HTTP.
#
# It is a separate container from n8n on purpose: the n8n image has no Python interpreter
# and no access to this repo on the host, so the two cannot share a process. See
# src/service.py for the full reasoning.

FROM python:3.12-slim

WORKDIR /app

# Dependencies first so a code change doesn't invalidate the layer.
COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn

COPY src/ ./src/
COPY data/ ./data/
# Served by /prompt so the workflow fetches the prompt rather than carrying a copy.
COPY prompts/ ./prompts/

# Non-root. The service reads a CSV and serves JSON; it has no reason to own anything.
RUN useradd --create-home --uid 10001 engine && chown -R engine:engine /app
USER engine

EXPOSE 8000

CMD ["uvicorn", "src.service:app", "--host", "0.0.0.0", "--port", "8000"]

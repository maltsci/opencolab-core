FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV CODEX_HOME=/app/.codex

ARG CODEX_VERSION=0.142.5

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl nodejs npm git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/.codex

RUN npm install -g @openai/codex@${CODEX_VERSION} \
    && codex --version | grep -F "${CODEX_VERSION}"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY server.py /app/server.py

EXPOSE 8102
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8102"]

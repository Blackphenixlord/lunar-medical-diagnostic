# VITALS - spaceflight medical decision support
# Team TETHER, NASA HUNCH 2026-27
#
# This image is the ENGINE, the KNOWLEDGE BASE and the UI. The language model
# lives in its own image (docker/ollama.Dockerfile) because it is gigabytes and
# you do not want to rebuild that every time Joaquin edits a rule.
#
#   docker compose build     once, with a network
#   docker compose up        -> http://localhost:8000

FROM python:3.12-slim

# tini gives us correct signal handling, so Ctrl-C actually stops the server
# instead of leaving a zombie holding port 8000.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so editing a rule does not re-install Python packages.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/     ./src/
COPY kb/      ./kb/
COPY cases/   ./cases/
COPY prompts/ ./prompts/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://ollama:11434 \
    VITALS_OLLAMA_MODEL=llama3.2

EXPOSE 8000

# Fail the build if the knowledge base is broken. A container that starts with
# an invalid KB is worse than one that refuses to build.
RUN python -m vitals validate

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/usr/sbin/tini", "--", "/usr/local/bin/entrypoint.sh"]

# 0.0.0.0, not 127.0.0.1. Inside a container localhost means "this container",
# so binding to loopback would make the UI unreachable from your browser.
CMD ["python", "-m", "vitals", "serve", "--host", "0.0.0.0", "--port", "8000", "--no-open"]

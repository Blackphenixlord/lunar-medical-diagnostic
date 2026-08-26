# MDX — spaceflight medical diagnostic decision support
# NASA HUNCH 2026-27
#
# This image contains the ENGINE and the UI only. The language model lives in a
# separate ollama container (see docker-compose.yml) because it is 2GB+ and you
# do not want to rebuild it every time you edit a rule.
#
#   docker compose up
#   -> http://localhost:8000

FROM python:3.12-slim

# Tini gives us correct signal handling, so Ctrl-C actually stops the server
# instead of leaving a zombie holding port 8000.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so editing a rule does not re-install Python packages.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/    ./src/
COPY kb/     ./kb/
COPY cases/  ./cases/
COPY prompts/ ./prompts/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://ollama:11434 \
    MDX_OLLAMA_MODEL=llama3.2

EXPOSE 8000

# Fail the build if the knowledge base is broken. A container that starts with
# an invalid KB is worse than one that refuses to build.
RUN python -m mdx validate

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

# tini lives in /usr/bin on Debian slim, NOT /usr/sbin. Getting this wrong
# means the container never starts at all - caught by actually building it.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]

# 0.0.0.0, not 127.0.0.1. Inside a container, localhost means "this container",
# so binding to loopback would make the UI unreachable from your browser.
CMD ["python", "-m", "mdx", "serve", "--host", "0.0.0.0", "--port", "8000", "--no-open"]

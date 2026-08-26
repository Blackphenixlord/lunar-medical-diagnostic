#!/bin/sh
# Wait for ollama, then make sure the model is really there.
#
# With the baked image (docker/ollama.Dockerfile) the model is already present
# and this is a one-line no-op. The pull path below is the fallback for anyone
# running against a plain ollama/ollama image or an ollama installed on the
# host - it turns "every question fails" into "the model is downloading".
set -e

HOST="${OLLAMA_HOST:-http://ollama:11434}"
MODEL="${VITALS_OLLAMA_MODEL:-llama3.2}"

echo "[vitals] waiting for ollama at $HOST ..."
attempt=0
until curl -fsS "$HOST/api/tags" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -gt 60 ]; then
        echo "[vitals] ollama did not come up after 2 minutes."
        echo "[vitals] Starting anyway - the engine and UI work, questions will not."
        exec "$@"
    fi
    sleep 2
done
echo "[vitals] ollama is up."

if curl -fsS "$HOST/api/tags" | grep -q "\"${MODEL%%:*}"; then
    echo "[vitals] model '$MODEL' is already in the image. No download needed."
else
    echo "[vitals] '$MODEL' is not in this ollama image - pulling it now."
    echo "[vitals] (build with docker/ollama.Dockerfile to avoid this wait)"
    curl -fsS "$HOST/api/pull" -d "{\"name\":\"$MODEL\"}" >/dev/null || \
        echo "[vitals] pull failed; run 'python -m vitals pull $MODEL' later."
    echo "[vitals] pull finished."
fi

exec "$@"

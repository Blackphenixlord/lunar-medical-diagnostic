#!/bin/sh
# Start the UI IMMEDIATELY. Prepare the model in the background.
#
# Two bugs were found here by actually running the container:
#
# 1. The first version BLOCKED until ollama answered, up to two minutes. If
#    ollama was slow or absent you got a dead port and no explanation - the app
#    looked broken when it was only waiting. The UI already reports model status
#    honestly (/api/health -> ollama.up), so serving straight away beats hiding.
#
# 2. The first version reported success on a FAILED pull. /api/pull answers
#    HTTP 200 and puts the error inside the streamed body, so `curl -f` exits 0
#    even when the pull died. It logged "'llama3.2' ready" while ollama held no
#    models at all. A false ready message is worse than an error - it sends you
#    debugging the wrong thing.
#
# So: use `python -m vitals pull`, which parses the stream properly and is tested,
# then VERIFY against /api/tags rather than trusting the exit code.
set -e

HOST="${OLLAMA_HOST:-http://ollama:11434}"
MODEL="${VITALS_OLLAMA_MODEL:-llama3.2}"

# ollama lists an untagged model as NAME:latest, so compare against that.
case "$MODEL" in
    *:*) WANT="$MODEL" ;;
    *)   WANT="$MODEL:latest" ;;
esac

# Exact name AND tag. Matching the name alone once reported llama3.2:1b as
# present when only llama3.2:latest was there.
model_present() {
    curl -fsS --max-time 10 "$HOST/api/tags" 2>/dev/null \
        | grep -q "\"name\":\"$WANT\""
}

prepare_model() {
    echo "[vitals] waiting for ollama at $HOST ..."
    i=0
    until curl -fsS --max-time 5 "$HOST/api/tags" >/dev/null 2>&1; do
        i=$((i + 1))
        if [ "$i" -gt 150 ]; then     # ~5 minutes
            echo "[vitals] ollama never came up. Engine and UI still work; questions will not."
            echo "[vitals] check: docker compose ps   /   docker compose logs -f ollama"
            return 0
        fi
        sleep 2
    done
    echo "[vitals] ollama is up."

    if model_present; then
        echo "[vitals] model '$MODEL' already present."
        return 0
    fi

    echo "[vitals] pulling '$MODEL' - a few GB, once. The UI is already usable."
    python -m vitals pull "$MODEL" || true

    # Verify. Do not trust the exit code - see note 2 above.
    if model_present; then
        echo "[vitals] '$MODEL' is ready."
    else
        echo "[vitals] PULL DID NOT SUCCEED - '$MODEL' is not in ollama."
        echo "[vitals] The UI works, but questions to the model will fail."
        echo "[vitals] Retry:  docker compose exec vitals python -m vitals pull $MODEL"
        echo "[vitals] Status: curl $HOST/api/tags"
    fi
}

prepare_model &

echo "[vitals] starting the interface on :8000"
exec "$@"

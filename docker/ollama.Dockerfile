# The language model, baked into the image.
#
# The stock ollama/ollama image ships with NO models. It downloads one the
# first time you ask a question, which means the first demo of the day is three
# gigabytes of waiting - and on a locked-down network, or at a review with no
# wifi, it is not a wait, it is a failure.
#
# So we pull the model AT BUILD TIME and it becomes part of the image. After
# `docker compose build`, `docker compose up` needs no internet at all.
#
#   docker compose build          once, with a network
#   docker compose up             any time after, with or without one
#
# Cost: the image is ~2-3 GB larger. That is the correct trade for a demo that
# has to work in a building you have never been in.
#
# ARCHITECTURE WARNING (this matters for the Jetson)
#   A Jetson is arm64. An image built on an x86 laptop will not run on it.
#   Build this ON the Jetson, or use `docker buildx --platform linux/arm64`.

FROM ollama/ollama:latest

# Override to bake a different model:  docker compose build --build-arg MODEL=llama3.2:1b
ARG MODEL=llama3.2

ENV VITALS_BAKED_MODEL=${MODEL}

# `ollama pull` needs a running server, and there is none during a build. So we
# start one, wait for it, pull, and stop it again - all inside a single layer,
# so the model files land in the image and the temporary server does not.
RUN set -eux; \
    ollama serve & \
    server_pid=$!; \
    for i in $(seq 1 60); do \
        if ollama list >/dev/null 2>&1; then break; fi; \
        sleep 1; \
    done; \
    ollama pull "${MODEL}"; \
    ollama list; \
    kill "${server_pid}"; \
    wait "${server_pid}" 2>/dev/null || true

# ollama/ollama already sets the right entrypoint and CMD; we only added a model.

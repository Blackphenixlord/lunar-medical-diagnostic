"""All the HTTP plumbing for talking to a local ollama server.

Nothing medical happens in here. It exists so that reason.py can be about
prompts and evidence instead of about urllib, and so that every "ollama is not
running" message in the project comes from one place and says something useful.

WHY WE TALK HTTP INSTEAD OF SHELLING OUT TO `ollama`
    The Windows installer puts ollama.exe somewhere PowerShell has not noticed
    yet, so `ollama pull` fails for a reason that has nothing to do with this
    project. The SERVER is already listening on 11434 either way, and it can
    pull models perfectly well on its own. Fighting Windows PATH is not part of
    this project.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("VITALS_OLLAMA_MODEL", "llama3.2")

# Generating a full differential on CPU is slow. This is a ceiling, not a target.
DEFAULT_TIMEOUT = 180.0

# Pulling a model is a multi-gigabyte download over whatever link is available.
PULL_TIMEOUT = 3600.0


class OllamaUnavailable(RuntimeError):
    """The server is not reachable, or the model is not there.

    Always carries an actionable message - see `unreachable_hint`.
    """


def unreachable_hint(host: str) -> str:
    """Advice that matches where the user actually is.

    Telling someone inside a Docker container to open the Start menu is worse
    than saying nothing: it sends them hunting for a tray icon that cannot
    exist. If the host is not loopback, we are almost certainly one container
    talking to another.
    """
    is_local = any(name in host for name in ("127.0.0.1", "localhost", "0.0.0.0"))

    if is_local:
        return (
            "  The SERVER is what matters, not the `ollama` command.\n"
            "  Start the Ollama app - on Windows and macOS it runs in the tray/menu bar.\n"
            "  On Linux: ollama serve"
        )

    return (
        f"  '{host}' is not this machine, so this is almost certainly Docker.\n"
        "  Check the ollama container is up:  docker compose ps\n"
        "  Watch it start:                    docker compose logs -f ollama\n"
        "  If you are NOT using Docker, unset OLLAMA_HOST."
    )


def list_models(host: str = OLLAMA_HOST, timeout: float = 4.0) -> list[str]:
    """Which models are actually pulled. Raises OllamaUnavailable if it is not running."""
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise OllamaUnavailable(
            f"could not reach the ollama server at {host} ({exc}).\n"
            + unreachable_hint(host)
        ) from exc

    return sorted(entry.get("name", "") for entry in (body.get("models") or []))


def has_model(name: str, host: str = OLLAMA_HOST) -> bool:
    """Is this model pulled? Compares on the family, so llama3.2:3b counts as llama3.2."""
    family = name.split(":")[0]
    try:
        return any(pulled.split(":")[0] == family for pulled in list_models(host))
    except OllamaUnavailable:
        return False


def pull_model(
    name: str,
    host: str = OLLAMA_HOST,
    *,
    progress: Optional[Callable[[dict], None]] = None,
    timeout: float = PULL_TIMEOUT,
) -> None:
    """Download a model through the HTTP API.

    /api/pull streams newline-delimited JSON status objects. `progress` is
    called with each one, so the CLI can draw a bar without this module
    knowing anything about terminals.
    """
    payload = json.dumps({"name": name, "stream": True}).encode("utf-8")
    request = urllib.request.Request(
        host.rstrip("/") + "/api/pull",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                event = _decode_stream_line(raw_line)
                if event is None:
                    continue
                if "error" in event:
                    raise OllamaUnavailable(f"pull failed: {event['error']}")
                if progress:
                    progress(event)
    except urllib.error.URLError as exc:
        raise OllamaUnavailable(
            f"could not reach ollama at {host} ({exc}).\n" + unreachable_hint(host)
        ) from exc


def _decode_stream_line(raw_line: bytes) -> Optional[dict]:
    """One line of the pull stream, or None if it is blank or unparseable."""
    line = raw_line.decode("utf-8").strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def generate(
    *,
    prompt: str,
    system: str,
    model: str,
    host: str = OLLAMA_HOST,
    timeout: float = DEFAULT_TIMEOUT,
    options: Optional[dict[str, Any]] = None,
) -> str:
    """One completion. Returns the raw response text.

    Temperature is pinned to 0 by default. The same complaint must give the
    same answer, or the test suite cannot exist and nothing is provable at a
    design review.
    """
    payload = json.dumps({
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": options or {"temperature": 0, "num_ctx": 8192},
    }).encode("utf-8")

    request = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise OllamaUnavailable(
            f"could not reach the ollama server at {host} ({exc}).\n"
            + unreachable_hint(host)
            + f"\n  get the model: python -m vitals pull {model}"
        ) from exc

    if "error" in body:
        raise _describe_server_error(str(body["error"]), model, host)

    return (body.get("response") or "").strip()


def _describe_server_error(message: str, model: str, host: str) -> OllamaUnavailable:
    """Turn ollama's error string into something a person can act on."""
    looks_like_missing_model = (
        "not found" in message.lower() or "no such model" in message.lower()
    )
    if not looks_like_missing_model:
        return OllamaUnavailable(f"ollama returned an error: {message}")

    try:
        available = list_models(host)
    except OllamaUnavailable:
        available = []

    if available:
        hint = "\n  models you have: " + ", ".join(available)
    else:
        hint = "\n  you have no models pulled yet"

    return OllamaUnavailable(
        f"model '{model}' is not pulled.\n"
        f"  get it:  ollama pull {model}{hint}\n"
        f'  or pick one you have:  python -m vitals ask "..." --model <name>'
    )

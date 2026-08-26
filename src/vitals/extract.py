"""Intake: a crewmember's sentence -> a dictionary of observed findings.

WHERE THIS SITS, AND WHY THAT MATTERS

    crewmember types a sentence
              |
              v
    [ extract.py ]   pull out findings        <- language: fuzzy, replaceable
              |
              v
    [ retrieval.py ] pick the KB pages        <- grounding
              |
              v
    [ reason.py ]    the model answers        <- medicine, cited, auditable

Extraction NEVER diagnoses. It only fills in the observation dictionary. If the
model is unavailable, offline, or simply wrong, the rest of the system still
runs on whatever findings were caught, and the CLI can always fall back to the
structured interview.

That separation is our answer to "what happens when the AI hallucinates?" -
the worst case here is a MISSED finding, not a fabricated diagnosis.

THREE BACKENDS
    KeywordExtractor  regex, offline, zero dependencies. The default, because a
                      tool on a vehicle 400 km up cannot require a network call.
    OllamaExtractor   a local model. Better on messy phrasing, still no cloud.
    ClaudeExtractor   the cloud API. Best recall, needs a key. Ground use only.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from .knowledge_base import KnowledgeBase
from .patterns import (
    CLAUSE_BOUNDARIES,
    NEGATION_CUES,
    NEGATION_LOOKBACK,
    NUMERIC_PATTERNS,
    PAIN_SCALE_PATTERN,
    PAIN_SCALE_TARGETS,
    SYMPTOM_PATTERNS,
)

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

EXTRACTION_SYSTEM_PROMPT = """You convert a crewmember's description of how they feel into structured clinical findings.

You are NOT diagnosing. You are NOT recommending treatment. You only report which findings the text supports.

Rules:
- Only use finding ids from the provided list. Never invent one.
- true  = the text says the finding is present
- false = the text explicitly denies it
- Omit the finding entirely if the text does not address it. Omission is correct and safe; guessing is not.
- For numeric findings return a number in the stated unit.
- For 0-10 scale findings return an integer 0-10.

Return ONLY a JSON object mapping finding id to value. No prose, no markdown fence."""


# --- shared helpers --------------------------------------------------------


def is_negated(text: str, match_start: int) -> bool:
    """Is there a negation cue just before this match, in the SAME clause?

    Silently inverting a finding is the worst failure this layer has - it turns
    "my face feels full" into "no facial fullness" - so the clause boundary
    check is not optional. See CLAUSE_BOUNDARIES in patterns.py.
    """
    window = text[max(0, match_start - NEGATION_LOOKBACK):match_start]

    last_boundary = max(window.rfind(char) for char in CLAUSE_BOUNDARIES)
    if last_boundary != -1:
        window = window[last_boundary + 1:]

    return any(re.search(cue, window) for cue in NEGATION_CUES)


def describe_vocabulary(knowledge_base: KnowledgeBase) -> str:
    """The finding list handed to a model. Its entire permitted vocabulary."""
    lines = []
    for finding_id, definition in knowledge_base.findings.items():
        unit = f" [{definition.unit}]" if definition.unit else ""
        lines.append(f"- {finding_id} ({definition.type}{unit}): {definition.label}")
    return "\n".join(lines)


def build_extraction_prompt(text: str, knowledge_base: KnowledgeBase) -> str:
    return (
        "Available findings:\n"
        + describe_vocabulary(knowledge_base)
        + f'\n\nCrewmember says:\n"""\n{text}\n"""'
    )


def keep_known_findings(data: Any, knowledge_base: KnowledgeBase) -> dict[str, Any]:
    """Drop anything a model returned that is not in the vocabulary.

    Trust nothing a model produces. An invented finding id would either crash
    the engine or, worse, quietly score nothing while looking like it counted.
    """
    if not isinstance(data, dict):
        return {}
    return {
        key: value for key, value in data.items()
        if key in knowledge_base.findings
    }


def coerce_to_finding_types(
    data: dict[str, Any],
    knowledge_base: KnowledgeBase,
) -> dict[str, Any]:
    """Force model output into the shapes the engine expects, dropping the rest."""
    clean: dict[str, Any] = {}

    for finding_id, value in data.items():
        definition = knowledge_base.findings.get(finding_id)
        if definition is None or value is None:
            continue

        if definition.type == "bool":
            if isinstance(value, bool):
                clean[finding_id] = value
            elif isinstance(value, str) and value.lower() in ("true", "yes", "false", "no"):
                clean[finding_id] = value.lower() in ("true", "yes")
        else:
            try:
                clean[finding_id] = float(value)
            except (TypeError, ValueError):
                continue

    return clean


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a model response, tolerating a markdown fence, returning {} on junk."""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# --- the offline default ---------------------------------------------------


class KeywordExtractor:
    """Regex over the phrasebook in patterns.py. Deterministic and offline.

    This is the DEFAULT for a reason: a diagnostic tool on a vehicle cannot
    require an internet call, and a regex gives the same answer every time,
    which is what makes the test suite possible.
    """

    name = "keyword"

    def extract(self, text: str, knowledge_base: KnowledgeBase) -> dict[str, Any]:
        # Pad with spaces so \b patterns fire at the very start and end.
        padded = " " + text.lower().strip() + " "

        observations: dict[str, Any] = {}
        self._extract_symptoms(padded, knowledge_base, observations)
        self._extract_numbers(padded, knowledge_base, observations)
        self._attach_pain_scale(padded, observations)
        return observations

    @staticmethod
    def _extract_symptoms(
        text: str,
        knowledge_base: KnowledgeBase,
        observations: dict[str, Any],
    ) -> None:
        """Yes/no findings. A negation cue nearby records False, not True."""
        for finding_id, patterns in SYMPTOM_PATTERNS.items():
            if finding_id not in knowledge_base.findings:
                continue
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    observations[finding_id] = not is_negated(text, match.start())
                    break

    @staticmethod
    def _extract_numbers(
        text: str,
        knowledge_base: KnowledgeBase,
        observations: dict[str, Any],
    ) -> None:
        """Measured values: temperature, flight day, hours of sleep."""
        for finding_id, pattern in NUMERIC_PATTERNS.items():
            if finding_id not in knowledge_base.findings:
                continue
            match = re.search(pattern, text)
            if not match:
                continue
            captured = next((group for group in match.groups() if group), None)
            if captured:
                observations[finding_id] = float(captured)

    @staticmethod
    def _attach_pain_scale(text: str, observations: dict[str, Any]) -> None:
        """A bare "8 out of 10" belongs to whichever pain is already on the table.

        Without an anchor a severity score is meaningless, so it is attached to
        the first candidate finding already recorded as present - and dropped
        entirely if there is none.
        """
        match = re.search(PAIN_SCALE_PATTERN, text)
        if not match:
            return

        severity = float(match.group(1))
        for finding_id in PAIN_SCALE_TARGETS:
            if observations.get(finding_id) is True:
                observations[finding_id] = severity
                return


# --- local model -----------------------------------------------------------


class OllamaExtractor:
    """The same job as KeywordExtractor, but a model runs it - on YOUR hardware.

    This is the backend that fits the mission. A vehicle cannot call an API, and
    "we need internet" is not an answer a review panel accepts. Ollama on the
    Jetson means the whole system runs on the vehicle: no key, no network, no
    per-call cost, and the same model every time.

    It is still only doing EXTRACTION. It fills in the observation dictionary
    and gets out of the way.
    """

    name = "ollama"

    def __init__(self, model: str = "llama3.2", host: str | None = None, timeout: float = 60.0):
        self.model = os.environ.get("VITALS_OLLAMA_MODEL", model)
        self.host = (host or DEFAULT_OLLAMA_HOST).rstrip("/")
        self.timeout = timeout

    @staticmethod
    def is_available(host: str | None = None, timeout: float = 0.4) -> bool:
        """A cheap probe, so `auto` can choose this without hanging when it is off."""
        url = (host or DEFAULT_OLLAMA_HOST).rstrip("/") + "/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=timeout):
                return True
        except Exception:
            return False

    def extract(self, text: str, knowledge_base: KnowledgeBase) -> dict[str, Any]:
        payload = json.dumps({
            "model": self.model,
            "system": EXTRACTION_SYSTEM_PROMPT,
            "prompt": build_extraction_prompt(text, knowledge_base) + "\n\nJSON:",
            "stream": False,
            "format": "json",                 # ollama constrains output to valid JSON
            "options": {"temperature": 0},    # same input -> same output. non-negotiable.
        }).encode("utf-8")

        request = urllib.request.Request(
            self.host + "/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"could not reach ollama at {self.host} ({exc}).\n"
                f"Start it with:  ollama serve\n"
                f"Pull the model: ollama pull {self.model}\n"
                f"Or use the offline extractor: --backend keyword"
            ) from exc

        parsed = _parse_json_object(body.get("response") or "")
        return coerce_to_finding_types(parsed, knowledge_base)


# --- cloud model (optional) ------------------------------------------------


class ClaudeExtractor:
    """Highest recall on messy phrasing. Optional by design - needs a network.

    Useful on the ground for building test data out of Cruz's user testing.
    Never the default, and never the only path.
    """

    name = "claude"

    def __init__(self, model: str = "claude-sonnet-4-5", api_key: Optional[str] = None):
        try:
            import anthropic
        except ImportError as exc:      # pragma: no cover - depends on environment
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic\n"
                "Or use the default keyword extractor, which needs no network."
            ) from exc

        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self._model = model

    def extract(self, text: str, knowledge_base: KnowledgeBase) -> dict[str, Any]:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1200,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_extraction_prompt(text, knowledge_base)}],
        )
        raw = "".join(
            block.text for block in message.content
            if getattr(block, "type", "") == "text"
        )
        return keep_known_findings(_parse_json_object(raw), knowledge_base)


# --- choosing one ----------------------------------------------------------


def get_extractor(backend: str = "auto"):
    """backend: keyword | ollama | claude | auto

    `auto` order: whatever $VITALS_BACKEND says, then a running local ollama,
    then Claude if both the package and the key are present, then keyword.

    Local beats cloud on purpose. The offline path is the one that has to work.
    """
    backend = os.environ.get("VITALS_BACKEND", backend)

    explicit = {
        "keyword": KeywordExtractor,
        "ollama": OllamaExtractor,
        "claude": ClaudeExtractor,
    }
    if backend in explicit:
        return explicit[backend]()

    if OllamaExtractor.is_available():
        return OllamaExtractor()

    try:
        import anthropic     # noqa: F401  - presence check only
        if os.environ.get("ANTHROPIC_API_KEY"):
            return ClaudeExtractor()
    except ImportError:
        pass

    return KeywordExtractor()

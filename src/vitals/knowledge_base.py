"""Load kb/ off disk, validate it, and refuse to start if it is wrong.

WHY THE KNOWLEDGE BASE IS YAML
    Joaquin has to be able to write a medical rule without being a programmer.
    YAML has comments, so a citation can sit inline next to the weight it
    justifies, and multi-line strings so `microgravity_note` reads like prose
    instead of one endless line.

WHY THE SCHEMA IS JSON
    JSON Schema is the standard tool for this and gives real error messages
    that point at the offending field. See kb/schema/condition.schema.json.

WHY THIS FILE IS SO STRICT
    Every failure here is caught at start-up, in a terminal, by a person who
    can fix it. The alternative is a typo'd finding id silently contributing
    nothing to a diagnosis, discovered by nobody. Fail loud, fail early.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from .models import Condition, Evidence, FindingDef, ScoringCurve


class KnowledgeBaseError(Exception):
    """The knowledge base on disk is malformed. Nothing should run until it is fixed."""


@dataclass
class KnowledgeBase:
    """Everything loaded from kb/, indexed by id."""

    findings: dict[str, FindingDef]
    conditions: dict[str, Condition]
    root: Path

    def condition(self, condition_id: str) -> Condition:
        if condition_id not in self.conditions:
            raise KnowledgeBaseError(f"unknown condition id: {condition_id}")
        return self.conditions[condition_id]

    def finding(self, finding_id: str) -> FindingDef:
        if finding_id not in self.findings:
            raise KnowledgeBaseError(f"unknown finding id: {finding_id}")
        return self.findings[finding_id]

    def label_for(self, finding_id: str) -> str:
        """Human wording for a finding id, for output. Falls back to the id itself."""
        definition = self.findings.get(finding_id)
        return definition.label if definition else finding_id

    def question_for(self, finding_id: str) -> str:
        """The question to put to a crewmember about this finding."""
        definition = self.findings.get(finding_id)
        if definition is None:
            return finding_id
        return definition.ask or definition.label

    def summary(self) -> str:
        """A few lines for `vitals validate` and the self-check."""
        ids_by_urgency: dict[str, list[str]] = {}
        for condition in self.conditions.values():
            ids_by_urgency.setdefault(condition.urgency, []).append(condition.id)

        lines = [f"{len(self.conditions)} conditions, {len(self.findings)} findings"]
        for urgency in ("emergency", "urgent", "monitor", "routine"):
            if urgency in ids_by_urgency:
                ids = sorted(ids_by_urgency[urgency])
                lines.append(f"  {urgency:<10} {len(ids)}  ({', '.join(ids)})")
        return "\n".join(lines)


def default_knowledge_base_root() -> Path:
    """src/vitals/knowledge_base.py -> src/vitals -> src -> repo root -> kb/"""
    return Path(__file__).resolve().parents[2] / "kb"


def load_knowledge_base(root: str | Path | None = None, *, strict: bool = True) -> KnowledgeBase:
    """Read kb/findings.yaml and every kb/conditions/*.yaml.

    strict=True also runs JSON Schema validation. Turn it off only on a device
    where `jsonschema` cannot be installed - a Pi running a minimal image, say.
    """
    root = Path(root) if root else default_knowledge_base_root()
    if not root.exists():
        raise KnowledgeBaseError(f"knowledge base directory not found: {root}")

    findings = _load_findings(root / "findings.yaml")
    conditions = _load_conditions(
        directory=root / "conditions",
        schema_path=root / "schema" / "condition.schema.json",
        strict=strict,
    )

    _cross_check(findings, conditions.values())
    return KnowledgeBase(findings=findings, conditions=conditions, root=root)


def _load_findings(path: Path) -> dict[str, FindingDef]:
    """Parse the controlled vocabulary."""
    if not path.exists():
        raise KnowledgeBaseError(f"missing {path}")

    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    findings: dict[str, FindingDef] = {}

    for finding_id, body in (document.get("findings") or {}).items():
        body = body or {}
        curve = body.get("scoring")
        findings[finding_id] = FindingDef(
            id=finding_id,
            type=body.get("type", "bool"),
            label=body.get("label", finding_id.replace("_", " ")),
            ask=body.get("ask", ""),
            unit=body.get("unit", ""),
            values=body.get("values", []) or [],
            scoring=ScoringCurve(**curve) if curve else None,
            contextual=bool(body.get("contextual", False)),
        )

    if not findings:
        raise KnowledgeBaseError(f"{path} defined no findings")
    return findings


def _load_conditions(*, directory: Path, schema_path: Path, strict: bool) -> dict[str, Condition]:
    """Parse every condition rule file, validating each against the schema."""
    if not directory.exists():
        raise KnowledgeBaseError(f"missing {directory}")

    validator = _build_validator(schema_path) if strict else None
    conditions: dict[str, Condition] = {}

    for path in sorted(directory.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise KnowledgeBaseError(f"{path.name}: not a YAML mapping")

        if validator is not None:
            _validate_against_schema(validator, document, path)

        condition_id = document["id"]
        if condition_id in conditions:
            raise KnowledgeBaseError(f"duplicate condition id {condition_id} in {path.name}")
        if condition_id != path.stem:
            raise KnowledgeBaseError(
                f"{path.name}: id '{condition_id}' must match the filename"
            )

        conditions[condition_id] = _build_condition(document)

    if not conditions:
        raise KnowledgeBaseError(f"no condition files found in {directory}")
    return conditions


def _build_validator(schema_path: Path):
    """A JSON Schema validator, or None if jsonschema is not installed.

    Missing the library downgrades to unvalidated rather than crashing, because
    a Pi with a minimal image should still be able to answer questions.
    """
    if not schema_path.exists():
        return None
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return None
    return Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))


def _validate_against_schema(validator, document: dict, path: Path) -> None:
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    if not errors:
        return
    detail = "; ".join(
        f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in errors[:5]
    )
    raise KnowledgeBaseError(f"{path.name} failed schema validation -> {detail}")


def _build_condition(document: dict) -> Condition:
    return Condition(
        id=document["id"],
        name=document["name"],
        category=document["category"],
        urgency=document["urgency"],
        prior=float(document["prior"]),
        description=document.get("description", "").strip(),
        microgravity_note=document.get("microgravity_note", "").strip(),
        aka=document.get("aka", []) or [],
        red_flags=document.get("red_flags", []) or [],
        recommend=document.get("recommend", []) or [],
        differential=document.get("differential", []) or [],
        sources=document.get("sources", []) or [],
        findings=[
            Evidence(
                finding=entry["finding"],
                weight=float(entry["weight"]),
                absent_weight=float(entry.get("absent_weight", 0.0)),
                required=bool(entry.get("required", False)),
                note=entry.get("note", "").strip(),
            )
            for entry in document["findings"]
        ],
    )


def _cross_check(findings: dict[str, FindingDef], conditions: Iterable[Condition]) -> None:
    """Catch the mistakes we will actually make.

    The schema proves each file has the right SHAPE. It cannot know that
    `flank_pian` is not a finding, or that a differential points at a condition
    nobody has written yet. Those are the real-world typos, so they get their
    own pass.
    """
    known_conditions = {condition.id for condition in conditions}
    problems: list[str] = []

    for condition in conditions:
        seen_findings: set[str] = set()

        for evidence in condition.findings:
            if evidence.finding not in findings:
                problems.append(
                    f"{condition.id}: references undefined finding '{evidence.finding}'"
                )
            if evidence.finding in seen_findings:
                problems.append(f"{condition.id}: finding '{evidence.finding}' listed twice")
            seen_findings.add(evidence.finding)

        for red_flag in condition.red_flags:
            if red_flag not in findings:
                problems.append(
                    f"{condition.id}: red_flag '{red_flag}' is not a defined finding"
                )

        for other_id in condition.differential:
            if other_id not in known_conditions:
                problems.append(
                    f"{condition.id}: differential '{other_id}' is not a known condition"
                )

    if problems:
        raise KnowledgeBaseError(
            "knowledge base cross-check failed:\n  - " + "\n  - ".join(problems)
        )

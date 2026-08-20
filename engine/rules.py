"""
Rule engine for the Lunar Medical Diagnostic System.

Design rules:
  - No internet. No external API calls. Ever.
  - Every result is explainable: we can always say WHICH rules fired.
  - Escalation is checked FIRST and can override everything.
"""

from dataclasses import dataclass, field
from pathlib import Path
import yaml


KB_PATH = Path(__file__).resolve().parent.parent / "knowledge_base" / "conditions.yaml"


@dataclass
class Result:
    """What the engine hands back to the terminal."""
    escalate: bool
    reason: str = ""
    category: str = ""
    procedure: str = ""
    confidence: float = 0.0
    fired_rules: list = field(default_factory=list)
    sources: list = field(default_factory=list)

    @property
    def confidence_label(self) -> str:
        """Plain language, because the user is not a doctor."""
        if self.confidence >= 0.7:
            return "Fairly confident"
        if self.confidence >= 0.5:
            return "Somewhat confident"
        if self.confidence >= 0.35:
            return "Not very confident"
        return "Not confident"


class Engine:
    def __init__(self, kb_path=KB_PATH):
        with open(kb_path, "r", encoding="utf-8") as f:
            self.kb = yaml.safe_load(f)
        self.rules = self.kb.get("rules", [])
        self.esc = self.kb.get("escalation", {})
        self.symptoms = {s["id"]: s for s in self.kb.get("symptoms", [])}

    # -- public ------------------------------------------------------

    def assess(self, reported: list) -> Result:
        """
        reported: list of symptom ids the user selected.
        """
        reported = set(reported)

        if not reported:
            return Result(
                escalate=False,
                reason="Nothing was reported.",
                category="No symptoms entered",
                procedure="Select at least one symptom.",
                confidence=0.0,
            )

        # 1. Hard escalation. Checked before anything else.
        hard = self._hard_escalation(reported)
        if hard:
            return hard

        # 2. Score the rules.
        scored = self._score(reported)

        # 3. Nothing matched.
        if not scored:
            return self._escalate("No rule in the knowledge base matches these symptoms.")

        # 4. Too uncertain to answer.
        top = scored[0]
        if top["score"] < self.esc.get("min_confidence", 0.35):
            return self._escalate("The best match is below our confidence threshold.")

        # 5. Two answers too close together to choose between.
        if len(scored) > 1:
            margin = top["score"] - scored[1]["score"]
            if margin < self.esc.get("ambiguity_margin", 0.10):
                return self._escalate(
                    f"Two possibilities scored almost the same "
                    f"({top['rule']['category']} and {scored[1]['rule']['category']}). "
                    f"We will not guess between them."
                )

        rule = top["rule"]
        return Result(
            escalate=False,
            category=rule.get("category", ""),
            procedure=rule.get("procedure", ""),
            confidence=round(top["score"], 3),
            fired_rules=[r["rule"]["id"] for r in scored],
            sources=[r["rule"].get("source", "") for r in scored],
        )

    # -- internals ---------------------------------------------------

    def _hard_escalation(self, reported):
        always = set(self.esc.get("always_escalate_symptoms", []))
        hits = reported & always
        if hits:
            names = ", ".join(self.symptoms.get(h, {}).get("prompt", h) for h in sorted(hits))
            return self._escalate(f"Reported symptom requires immediate escalation: {names}.")
        return None

    def _escalate(self, reason):
        return Result(
            escalate=True,
            reason=reason,
            procedure=self.esc.get("message", "Contact Earth."),
            confidence=0.0,
        )

    def _score(self, reported):
        out = []
        for rule in self.rules:
            if set(rule.get("exclude", [])) & reported:
                continue

            need_all = set(rule.get("match_all", []))
            if need_all and not need_all.issubset(reported):
                continue

            need_any = set(rule.get("match_any", []))
            if need_any and not (need_any & reported):
                continue

            if not need_all and not need_any:
                continue

            matched = (need_all | (need_any & reported))
            # Score = rule weight, scaled by how much of the user's report
            # this rule actually explains. A rule that explains 2 of 2
            # symptoms beats one that explains 2 of 6.
            coverage = len(matched) / len(reported)
            out.append({"rule": rule, "score": rule.get("weight", 0.0) * (0.5 + 0.5 * coverage)})

        return sorted(out, key=lambda r: r["score"], reverse=True)

    # -- integrity ---------------------------------------------------

    def unsourced_rules(self):
        """Any rule without a real source. Used by the test suite."""
        return [r["id"] for r in self.rules if not str(r.get("source", "")).strip()]

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


GRAPH_TRUST_TRUSTED = "trusted"
GRAPH_TRUST_PROPOSED = "proposed"
GRAPH_TRUST_SPECULATIVE = "speculative"

HYPOTHESIS_OBSERVED = "observed"
HYPOTHESIS_SUSPECTED = "suspected"
HYPOTHESIS_SUPPORTED = "supported"
HYPOTHESIS_OPERATOR_CONFIRMED = "operator_confirmed"
HYPOTHESIS_RESOLVED = "resolved"

CONFIDENCE_LOW = "Low"
CONFIDENCE_MEDIUM = "Medium"
CONFIDENCE_HIGH = "High"

CONFIDENCE_DIMENSIONS = (
    "sii_finding_strength",
    "signal_quality",
    "prior_applicability",
    "context_completeness",
    "graph_trust",
    "supporting_evidence",
    "confounder_severity",
    "model_or_residual_uncertainty",
)

CONFIRMATION_SOURCES = {
    "operator_confirmation",
    "physical_inspection",
    "maintenance_record",
    "work_order",
    "validated_diagnostic_test",
    "equipment_event",
    "control_system_event",
}


@dataclass(frozen=True)
class UnknownValue:
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"known": "unknown", "reason": self.reason}


@dataclass(frozen=True)
class UnitRequirement:
    dimension: str
    accepted_units: tuple[str, ...]
    normalized_unit: str


@dataclass(frozen=True)
class SignalRequirement:
    canonical: str
    meaning: str
    unit: UnitRequirement | None = None


@dataclass(frozen=True)
class RelationshipPrior:
    prior_id: str
    version: str
    name: str
    description: str
    applicable_system_types: tuple[str, ...]
    applicable_asset_classes: tuple[str, ...]
    required_signals: tuple[SignalRequirement, ...]
    optional_supporting_signals: tuple[SignalRequirement, ...]
    valid_operating_modes: tuple[str, ...]
    expected_relationship_form: str
    known_confounders: tuple[str, ...]
    lag_alignment_requirements: dict[str, Any]
    data_quality_requirements: dict[str, Any]
    applicability_rules: dict[str, Any]
    invalidation_conditions: tuple[str, ...]
    confidence_reduction_conditions: tuple[str, ...]
    evidence_requirements: dict[str, Any]
    possible_explanations: tuple[str, ...]
    recommended_checks: tuple[str, ...]
    rationale: str
    parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def required_signal_names(self) -> set[str]:
        return {item.canonical for item in self.required_signals}

    @property
    def optional_signal_names(self) -> set[str]:
        return {item.canonical for item in self.optional_supporting_signals}

    @property
    def all_signal_names(self) -> set[str]:
        return self.required_signal_names | self.optional_signal_names

    def unit_requirements(self) -> dict[str, UnitRequirement]:
        requirements: dict[str, UnitRequirement] = {}
        for signal in (*self.required_signals, *self.optional_supporting_signals):
            if signal.unit is not None:
                requirements[signal.canonical] = signal.unit
        return requirements

    def as_dict(self) -> dict[str, Any]:
        units = self.unit_requirements()
        return {
            "prior_id": self.prior_id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "applicable_system_types": list(self.applicable_system_types),
            "applicable_asset_classes": list(self.applicable_asset_classes),
            "required_signals": [
                {
                    "canonical": item.canonical,
                    "meaning": item.meaning,
                    "unit_dimension": units[item.canonical].dimension if item.canonical in units else None,
                    "accepted_engineering_units": list(units[item.canonical].accepted_units) if item.canonical in units else [],
                }
                for item in self.required_signals
            ],
            "optional_supporting_signals": [
                {
                    "canonical": item.canonical,
                    "meaning": item.meaning,
                    "unit_dimension": units[item.canonical].dimension if item.canonical in units else None,
                    "accepted_engineering_units": list(units[item.canonical].accepted_units) if item.canonical in units else [],
                }
                for item in self.optional_supporting_signals
            ],
            "valid_operating_modes": list(self.valid_operating_modes),
            "expected_relationship_form": self.expected_relationship_form,
            "known_confounders": list(self.known_confounders),
            "lag_alignment_requirements": dict(self.lag_alignment_requirements),
            "data_quality_requirements": dict(self.data_quality_requirements),
            "applicability_rules": dict(self.applicability_rules),
            "invalidation_conditions": list(self.invalidation_conditions),
            "confidence_reduction_conditions": list(self.confidence_reduction_conditions),
            "evidence_requirements": dict(self.evidence_requirements),
            "possible_explanations": list(self.possible_explanations),
            "recommended_checks": list(self.recommended_checks),
            "parameters": dict(self.parameters),
            "source_or_rationale": self.rationale,
        }


@dataclass(frozen=True)
class SignalMatch:
    canonical: str
    source_column: str
    display_name: str
    source_unit: str | None
    normalized_unit: str | None
    unit_dimension: str | None
    conversion_applied: str | None
    unit_status: str
    meaning: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical,
            "source_column": self.source_column,
            "display_name": self.display_name,
            "source_unit": self.source_unit,
            "normalized_unit": self.normalized_unit,
            "unit_dimension": self.unit_dimension,
            "conversion_applied": self.conversion_applied,
            "unit_status": self.unit_status,
            "meaning": self.meaning,
            "metadata": dict(self.metadata),
        }


def empty_confidence_dimensions() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "state": "unknown",
            "score": None,
            "explanation": "No water interpretation evidence has been evaluated for this dimension.",
        }
        for name in CONFIDENCE_DIMENSIONS
    }


def categorical_confidence(dimensions: dict[str, dict[str, Any]], parameters: dict[str, Any] | None = None) -> str:
    parameters = parameters or {}
    thresholds = parameters.get("confidence_thresholds") if isinstance(parameters.get("confidence_thresholds"), dict) else {}
    high_threshold = float(thresholds.get("high", 0.72))
    medium_threshold = float(thresholds.get("medium", 0.45))
    severe_cap = float(parameters.get("severe_uncertainty_confidence_cap", 0.58))
    scores: list[float] = []
    severe_confounder = False
    severe_uncertainty = False
    for name in CONFIDENCE_DIMENSIONS:
        item = dimensions.get(name, {})
        score = item.get("score")
        if isinstance(score, (int, float)):
            scores.append(float(score))
        state = str(item.get("state") or "").lower()
        if name == "confounder_severity" and state in {"high", "severe"}:
            severe_confounder = True
        if name == "model_or_residual_uncertainty" and state in {"high", "severe"}:
            severe_uncertainty = True
    if not scores:
        return CONFIDENCE_LOW
    average = sum(scores) / len(scores)
    if severe_confounder or severe_uncertainty:
        average = min(average, severe_cap)
    if average >= high_threshold:
        return CONFIDENCE_HIGH
    if average >= medium_threshold:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def build_confidence_summary(
    dimensions: dict[str, dict[str, Any]],
    *,
    preserved_sii_confidence: Any,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parameters = parameters or {}
    high_evidence_threshold = float(parameters.get("confidence_increase_score_threshold", 0.62))
    increases: list[str] = []
    reductions: list[str] = []
    for name in CONFIDENCE_DIMENSIONS:
        item = dimensions.get(name, {})
        explanation = str(item.get("explanation") or "").strip()
        if not explanation:
            continue
        score = item.get("score")
        state = str(item.get("state") or "").lower()
        if isinstance(score, (int, float)) and score >= high_evidence_threshold and state not in {"high", "severe", "reduced"}:
            increases.append(explanation)
        else:
            reductions.append(explanation)
    max_increases = max(1, int(parameters.get("max_increased_confidence_reasons", 6)))
    max_reductions = max(1, int(parameters.get("max_reduced_confidence_reasons", 8)))
    return {
        "overall": categorical_confidence(dimensions, parameters),
        "dimensions": dimensions,
        "preserved_sii_confidence": preserved_sii_confidence,
        "increased_confidence": list(dict.fromkeys(increases))[:max_increases],
        "reduced_confidence": list(dict.fromkeys(reductions))[:max_reductions],
        "explanation": confidence_sentence(dimensions, preserved_sii_confidence=preserved_sii_confidence, parameters=parameters),
    }


def confidence_sentence(dimensions: dict[str, dict[str, Any]], *, preserved_sii_confidence: Any, parameters: dict[str, Any] | None = None) -> str:
    overall = categorical_confidence(dimensions, parameters)
    reduced = []
    for name in CONFIDENCE_DIMENSIONS:
        if name not in dimensions:
            continue
        state = str(dimensions[name].get("state") or "").lower()
        if name == "confounder_severity":
            is_reduction = state in {"medium", "high", "severe"}
        elif name == "model_or_residual_uncertainty":
            is_reduction = state in {"medium", "high", "severe"}
        else:
            is_reduction = state in {"low", "reduced", "incomplete", "speculative"}
        if is_reduction:
            reduced.append(str(dimensions[name].get("explanation")))
    suffix = f" SII confidence was preserved as {preserved_sii_confidence}." if preserved_sii_confidence is not None else ""
    if reduced:
        return f"Water interpretation confidence is {overall}; reduced by {reduced[0].rstrip('.')}.{suffix}".strip()
    return f"Water interpretation confidence is {overall} based on SII finding strength, signal quality, applicability, and graph trust.{suffix}".strip()


def apply_confirmation_status(insight: dict[str, Any], confirmation: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(insight)
    if not isinstance(confirmation, dict):
        return updated
    source = str(confirmation.get("source") or confirmation.get("type") or "").strip().lower()
    if source not in CONFIRMATION_SOURCES:
        updated["confirmation_rejected"] = {
            "source": source or "unknown",
            "reason": "Confirmation requires operator confirmation, physical inspection, maintenance/work-order evidence, a validated diagnostic test, or an authoritative equipment/control-system event.",
        }
        return updated
    updated["status"] = HYPOTHESIS_OPERATOR_CONFIRMED
    updated["confirmation"] = {
        "source": source,
        "confirmed_at": confirmation.get("confirmed_at"),
        "confirmed_by": confirmation.get("confirmed_by"),
        "evidence_reference": confirmation.get("evidence_reference"),
        "note": confirmation.get("note"),
    }
    return updated

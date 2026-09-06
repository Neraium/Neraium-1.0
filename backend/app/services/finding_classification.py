from __future__ import annotations

from typing import Any

from app.services.finding_confidence import (
    build_finding_confidence,
    normalize_persistence_status,
)


KNOWN_OPERATIONAL_CHANGE = "known_operational_change"
CONTEXT_LIMITED_RELATIONSHIP_CHANGE = "context_limited_relationship_change"
POSSIBLE_INSTRUMENTATION_ISSUE = "possible_instrumentation_issue"
UNEXPLAINED_SYSTEMIC_CHANGE = "unexplained_systemic_change"
OBSERVED_CHANGE_UNDER_REVIEW = "observed_change_under_review"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"

_LABELS = {
    KNOWN_OPERATIONAL_CHANGE: "Known operational change",
    CONTEXT_LIMITED_RELATIONSHIP_CHANGE: "Context-limited relationship change",
    POSSIBLE_INSTRUMENTATION_ISSUE: "Possible instrumentation issue",
    UNEXPLAINED_SYSTEMIC_CHANGE: "Unexplained systemic change",
    OBSERVED_CHANGE_UNDER_REVIEW: "Observed change under review",
    INSUFFICIENT_EVIDENCE: "Insufficient evidence",
}
_INSTRUMENTATION_CONDITIONS = {
    "flatline_or_stuck",
    "possible_drift",
    "timestamp_misalignment",
    "invalid_range",
}
_DIRECT_CONTEXT_FEATURES = {
    "active_unit_count",
    "cleaning_cycle",
    "equipment_state",
    "maintenance_state",
    "schedule_state",
    "setpoint",
    "special_event",
    "valve_state",
}


def classify_finding(
    *,
    data_confidence: dict[str, Any] | None,
    sensor_health: list[dict[str, Any]] | None,
    operating_mode: dict[str, Any] | None,
    persistence: dict[str, Any] | bool | None,
    relationship_evidence: dict[str, Any] | None,
    known_operational_evidence: list[str] | None = None,
) -> dict[str, Any]:
    """Return the highest-certainty class supported by all evidence ceilings."""

    data_confidence = data_confidence or {}
    sensor_health = sensor_health or []
    operating_mode = operating_mode or {}
    relationship_evidence = relationship_evidence or {}
    known_operational_evidence = [str(item) for item in known_operational_evidence or [] if str(item).strip()]

    data_rating = str(data_confidence.get("rating") or "low").lower()
    evidence_sufficient, evidence_reasons = relationship_evidence_is_sufficient(relationship_evidence)
    persistent, persistence_reasons = persistence_support(persistence)
    instrumentation_reasons = instrumentation_evidence(sensor_health)
    mode_match = str(operating_mode.get("match") or "unavailable").lower()
    mode_confidence = str(operating_mode.get("confidence") or "low").lower()
    direct_context_evidence = [*known_operational_evidence]
    if (
        operating_mode.get("known_operational_change") is True
        and data_rating == "high"
        and mode_confidence == "high"
    ):
        direct_context_evidence.extend(
            str(item.get("reason"))
            for item in operating_mode.get("differences", [])
            if isinstance(item, dict)
            and str(item.get("feature") or "") in _DIRECT_CONTEXT_FEATURES
            and item.get("reason")
        )
    direct_context_evidence = dedupe(direct_context_evidence)
    normalized_persistence = normalize_persistence_status(persistence)["status"]

    def build_payload(
        classification_type: str,
        *,
        confidence: str,
        reasons: list[str],
        certainty_limit: str,
    ) -> dict[str, Any]:
        alternatives = []  # Compatibility field; no physical attribution is generated.
        payload = classification_payload(
            classification_type,
            confidence=confidence,
            reasons=reasons,
            alternative_explanations=alternatives,
            certainty_limit=certainty_limit,
        )
        payload["finding_confidence_v1"] = build_finding_confidence(
            classification_type=classification_type,
            classification_confidence=confidence,
            classification_reason=first_text(payload["reasons"], certainty_limit),
            data_confidence=data_confidence,
            sensor_health=sensor_health,
            operating_mode=operating_mode,
            persistence=persistence,
            relationship_evidence=relationship_evidence,
        )
        return payload

    if instrumentation_reasons:
        return build_payload(
            POSSIBLE_INSTRUMENTATION_ISSUE,
            confidence="limited",
            reasons=instrumentation_reasons,
            certainty_limit=(
                "Signal-health evidence can identify an instrumentation possibility, but it does not confirm "
                "that a sensor or transmitter is faulty."
            ),
        )

    if data_rating == "low" or not evidence_sufficient:
        reasons = [
            *list_text(data_confidence.get("reasons")),
            *evidence_reasons,
        ]
        return build_payload(
            INSUFFICIENT_EVIDENCE,
            confidence="low",
            reasons=reasons or ["Available evidence did not clear the minimum certainty gates."],
            certainty_limit=(
                "Data quality or relationship support is insufficient to distinguish an operational, "
                "instrumentation, or physical-system explanation."
            ),
        )

    if direct_context_evidence:
        confidence = (
            "high"
            if data_rating == "high" and mode_confidence == "high"
            else "limited"
        )
        return build_payload(
            KNOWN_OPERATIONAL_CHANGE,
            confidence=confidence,
            reasons=direct_context_evidence,
            certainty_limit=(
                "A directly observed operating-context change coincided with the relationship shift. This does "
                "not establish causality or prove that the context change is the only influence."
            ),
        )

    if mode_match in {"partial", "weak", "unavailable"}:
        context_reasons = [
            *list_text(operating_mode.get("reasons")),
            *list_text(data_confidence.get("reasons")),
            "Operating context was not comparable enough to attribute the observed relationship change.",
        ]
        return build_payload(
            CONTEXT_LIMITED_RELATIONSHIP_CHANGE,
            confidence="limited",
            reasons=context_reasons,
            certainty_limit=(
                "The relationship change was observed, but differing or unavailable operating context limits "
                "interpretation. The evidence does not establish that the context difference caused the change."
            ),
        )

    if persistent and mode_match == "strong":
        relationship_confidence = score(relationship_evidence.get("confidence_score"))
        confidence = (
            "high"
            if data_rating == "high"
            and str(operating_mode.get("confidence") or "").lower() == "high"
            and relationship_confidence >= 0.75
            else "limited"
        )
        return build_payload(
            UNEXPLAINED_SYSTEMIC_CHANGE,
            confidence=confidence,
            reasons=[
                *persistence_reasons,
                *list_text(operating_mode.get("reasons")),
                "No available operating-context or signal-health evidence explains the relationship shift.",
            ],
            certainty_limit=(
                "This class describes a persistent relationship change under comparable conditions; it does not "
                "diagnose cause, predict a failure, or imply an emergency."
            ),
        )

    if mode_match == "strong" and normalized_persistence in {"not_assessed", "observing"}:
        payload = build_payload(
            OBSERVED_CHANGE_UNDER_REVIEW,
            confidence="limited",
            reasons=[
                *persistence_reasons,
                *list_text(operating_mode.get("reasons")),
                "The measured relationship change is supported, but persistence is still being established.",
            ],
            certainty_limit=(
                "The baseline/current comparison supports a measured change, but the available evidence does not "
                "yet establish whether it persists or what explains it."
            ),
        )
        payload["legacy_classification"] = {
            "type": INSUFFICIENT_EVIDENCE,
            "label": _LABELS[INSUFFICIENT_EVIDENCE],
            "confidence": "low",
        }
        return payload

    reasons = [
        *persistence_reasons,
        *list_text(operating_mode.get("reasons")),
    ]
    if not persistent:
        reasons.append("The available persistence evidence does not support a sustained systemic claim.")
    if mode_match != "strong":
        reasons.append("Operating conditions were not matched strongly enough for a systemic interpretation.")
    return build_payload(
        INSUFFICIENT_EVIDENCE,
        confidence="low",
        reasons=reasons,
        certainty_limit=(
            "Additional like-for-like operation, persistence, or context evidence is needed before the "
            "relationship shift can be interpreted reliably."
        ),
    )


def relationship_evidence_is_sufficient(evidence: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    baseline_samples = integer(evidence.get("baseline_sample_size"))
    recent_samples = integer(evidence.get("recent_sample_size"))
    confidence = score(evidence.get("confidence_score"))
    change = score(evidence.get("correlation_delta"))
    if baseline_samples < 3 or recent_samples < 3:
        reasons.append("Fewer than three paired samples were available in a comparison window.")
    if confidence < 0.45:
        reasons.append("Relationship support did not clear the existing limited-confidence boundary.")
    if change <= 0:
        reasons.append("No quantified relationship change was available.")
    return not reasons, reasons


def persistence_support(value: dict[str, Any] | bool | None) -> tuple[bool, list[str]]:
    if isinstance(value, bool):
        return value, ["The relationship change persisted across the available recent evidence."] if value else []
    if not isinstance(value, dict):
        return False, ["Persistence evidence was unavailable."]
    status = str(value.get("status") or "").lower()
    persistent = value.get("persistent") is True or status in {"persistent", "confirmed", "sustained"}
    reasons = list_text(value.get("reasons"))
    summary = str(value.get("summary") or "").strip()
    if summary:
        reasons.append(summary)
    return persistent, reasons


def instrumentation_evidence(sensor_health: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for signal in sensor_health:
        if not isinstance(signal, dict) or signal.get("health") != "suspect":
            continue
        for condition in signal.get("conditions", []):
            if (
                isinstance(condition, dict)
                and condition.get("type") in _INSTRUMENTATION_CONDITIONS
                and condition.get("severity") == "review"
                and condition.get("evidence")
            ):
                reasons.append(f"{signal.get('signal')}: {condition['evidence']}")
    return dedupe(reasons)


def classification_payload(
    classification_type: str,
    *,
    confidence: str,
    reasons: list[str],
    alternative_explanations: list[str],
    certainty_limit: str,
) -> dict[str, Any]:
    return {
        "type": classification_type,
        "label": _LABELS[classification_type],
        "confidence": confidence,
        "reasons": dedupe(reasons),
        "alternative_explanations": dedupe(alternative_explanations),
        "certainty_limit": certainty_limit,
        "rule_version": "deterministic_finding_classification_v3",
    }


def list_text(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def score(value: Any) -> float:
    try:
        numeric = abs(float(value))
    except (TypeError, ValueError):
        return 0.0
    if numeric > 1.0 and numeric <= 100.0:
        numeric /= 100.0
    return max(0.0, min(1.0, numeric))


def first_text(*values: Any) -> str:
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text:
                return text
    return ""


def integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "finding-confidence-v1"

CONFIDENCE_LEVELS = {"high", "medium", "low", "unknown"}
ATTRIBUTION_STATUSES = {"confirmed", "supported", "hypothesis", "unattributed", "withheld"}
PERSISTENCE_STATUSES = {
    "not_assessed",
    "observing",
    "not_persistent",
    "intermittent",
    "persistent",
    "no_longer_observed",
}
SUPPORT_TRENDS = {"increasing", "stable", "decreasing"}


def build_finding_confidence(
    *,
    classification_type: str,
    classification_confidence: str,
    classification_reason: str,
    data_confidence: dict[str, Any],
    sensor_health: list[dict[str, Any]],
    operating_mode: dict[str, Any],
    persistence: dict[str, Any] | bool | None,
    relationship_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Build the additive maintenance confidence contract without changing evidence.

    The dimensions intentionally do not collapse into one aggregate tier. In
    particular, persistence is a lifecycle-like evidence status rather than a
    confidence score, and relationship direction is kept separate from any
    evidence-support trend.
    """

    evidence_refs = _evidence_refs(relationship_evidence)
    evidence_quality = _evidence_quality_dimension(data_confidence)
    operating_context = _operating_context_dimension(operating_mode)
    persistence_status = normalize_persistence_status(persistence)
    change_detection = _change_detection_dimension(relationship_evidence, evidence_refs)
    interpretation = _interpretation_dimension(
        classification_type=classification_type,
        classification_confidence=classification_confidence,
        classification_reason=classification_reason,
        evidence_quality=evidence_quality,
        operating_context=operating_context,
        persistence_status=persistence_status,
        sensor_health=sensor_health,
        evidence_refs=_dedupe(
            [
                *evidence_refs,
                *evidence_quality["evidence_refs"],
                *operating_context["evidence_refs"],
                *persistence_status["evidence_refs"],
                *_sensor_health_refs(sensor_health),
            ]
        ),
    )
    contract = {
        "schema_version": SCHEMA_VERSION,
        "change_detection": change_detection,
        "interpretation": interpretation,
        "persistence": persistence_status,
        "operating_context": operating_context,
        "evidence_quality": evidence_quality,
        "relationship_comparison": build_relationship_comparison(relationship_evidence),
    }
    support_trend = _support_trend(relationship_evidence)
    if support_trend:
        contract["support_trend"] = support_trend
    return contract


def build_relationship_comparison(evidence: dict[str, Any] | None) -> dict[str, Any]:
    evidence = evidence or {}
    baseline = _number(_first_present(evidence, "baseline_value", "baseline_correlation", "baseline_strength"))
    current = _number(
        _first_present(
            evidence,
            "current_value",
            "current_correlation",
            "recent_correlation",
            "current_strength",
        )
    )
    signed = _number(_first_present(evidence, "signed_change", "signed_correlation_delta"))
    if signed is None and baseline is not None and current is not None:
        signed = current - baseline
    absolute = _number(
        _first_present(
            evidence,
            "absolute_change",
            "absolute_correlation_change",
            "absolute_correlation_delta",
            "correlation_delta",
        )
    )
    if signed is not None:
        absolute = abs(signed)
    elif absolute is not None:
        absolute = abs(absolute)

    metric = str(evidence.get("metric") or evidence.get("evidence_type") or "relationship_change").strip()
    if metric in {"linear_correlation", "correlation", "pearson"}:
        metric = "pearson_correlation"

    comparison: dict[str, Any] = {
        "metric": metric,
        "baseline_value": baseline,
        "current_value": current,
        "signed_change": signed,
        "absolute_change": absolute,
        "formula": (
            "signed_change = current_value - baseline_value; absolute_change = abs(signed_change)"
            if baseline is not None and current is not None
            else "absolute_change = abs(legacy change magnitude); signed_change unavailable without baseline and current values"
        ),
    }
    direction = _relationship_direction(signed, absolute)
    if direction:
        comparison["direction"] = direction
    return comparison


def normalize_persistence_status(value: dict[str, Any] | bool | None) -> dict[str, Any]:
    if isinstance(value, bool):
        status = "persistent" if value else "observing"
        reason = (
            "Persistence is supported by the available evidence."
            if value
            else "The available evidence has not established persistence."
        )
        return {"status": status, "reason": reason, "evidence_refs": []}
    if not isinstance(value, dict):
        return {
            "status": "not_assessed",
            "reason": "Persistence evidence was not available for this finding.",
            "evidence_refs": [],
        }

    raw = str(value.get("status") or "").strip().lower().replace("-", "_")
    if value.get("persistent") is True or raw in {"confirmed", "sustained", "persistent"}:
        status = "persistent"
    elif raw in {"no_longer_observed", "resolved", "cleared", "recovered"}:
        status = "no_longer_observed"
    elif raw in {"intermittent", "recurring"}:
        status = "intermittent"
    elif raw in {"not_persistent", "transient", "failed"}:
        status = "not_persistent"
    elif raw in {"observing", "pending", "limited", "not_established", "unconfirmed"}:
        status = "observing"
    elif raw in {"not_assessed", "unavailable", "unknown", ""}:
        status = "not_assessed"
    else:
        status = "observing"

    reason = _first_text(
        value.get("reason"),
        value.get("summary"),
        value.get("reasons"),
        _persistence_default_reason(status),
    )
    return {
        "status": status,
        "reason": reason,
        "evidence_refs": _evidence_refs(value),
    }


def reconcile_alternative_explanations(
    *,
    classification_type: str,
    sensor_health: list[dict[str, Any]],
    operating_mode: dict[str, Any],
    persistence: dict[str, Any] | bool | None,
) -> list[str]:
    """Return alternatives consistent with the evidence that was actually checked."""

    alternatives: list[str] = []
    if classification_type != "possible_instrumentation_issue":
        alternatives.append(_sensor_health_alternative(sensor_health))

    match = str(operating_mode.get("match") or "unavailable").strip().lower()
    if classification_type != "known_operational_change":
        if match == "strong":
            alternatives.append(
                "Recorded operating-context checks support comparability; an undocumented context change remains possible."
            )
        elif match == "unavailable":
            alternatives.append(
                "Operating-context evidence was unavailable, so an unobserved context change may explain the pattern."
            )
        else:
            alternatives.append("Different recorded operating conditions may explain the pattern.")

    persistence_status = normalize_persistence_status(persistence)["status"]
    persistence_alternative = {
        "not_assessed": "Persistence was not assessed, so a short-lived movement cannot be excluded.",
        "observing": "The evidence window has not established persistence, so a short-lived movement remains possible.",
        "not_persistent": "A transient movement or short-lived operating condition may explain the observation.",
        "intermittent": "Intermittent operation or missing context may explain why the observation recurs.",
        "no_longer_observed": "The change is no longer observed, so a resolved or transient condition may explain it.",
    }.get(persistence_status)
    if persistence_alternative:
        alternatives.append(persistence_alternative)

    if classification_type == "possible_instrumentation_issue":
        alternatives.insert(0, "A physical-system relationship change remains possible.")
    elif classification_type == "known_operational_change":
        alternatives.append("A relationship change may remain after like-for-like operation resumes.")

    return _dedupe(alternatives)


def _change_detection_dimension(evidence: dict[str, Any], evidence_refs: list[str]) -> dict[str, Any]:
    baseline_samples = _integer(evidence.get("baseline_sample_size"))
    current_samples = _integer(_first_present(evidence, "recent_sample_size", "current_sample_size"))
    confidence_score = _normalized_score(evidence.get("confidence_score"))
    comparison = build_relationship_comparison(evidence)
    change = comparison.get("absolute_change")
    has_comparison = baseline_samples >= 3 and current_samples >= 3 and change is not None and change > 0
    if not evidence:
        level = "unknown"
        reason = "Relationship-change evidence was not available."
    elif has_comparison and confidence_score >= 0.75:
        level = "high"
        reason = "The baseline/current comparison has sufficient paired samples and strong recorded support."
    elif has_comparison and confidence_score >= 0.45:
        level = "medium"
        reason = "The baseline/current comparison supports a change with bounded recorded support."
    else:
        level = "low"
        reason = "The recorded comparison does not clear all sample, magnitude, and support gates for change detection."
    return _dimension(
        level,
        reason,
        score=confidence_score if evidence.get("confidence_score") is not None else None,
        method="paired_baseline_current_comparison",
        evidence_refs=evidence_refs,
    )


def _evidence_quality_dimension(data_confidence: dict[str, Any]) -> dict[str, Any]:
    rating = str(data_confidence.get("rating") or "").strip().lower()
    level = {
        "high": "high",
        "strong": "high",
        "medium": "medium",
        "moderate": "medium",
        "limited": "medium",
        "usable": "medium",
        "low": "low",
        "not_reliable": "low",
    }.get(rating, "unknown")
    reason = _first_text(
        data_confidence.get("summary"),
        data_confidence.get("reasons"),
        "Evidence quality was not recorded." if level == "unknown" else f"Recorded data-confidence rating is {rating}.",
    )
    return _dimension(
        level,
        reason,
        score=_normalized_optional_score(data_confidence.get("score")),
        method="recorded_data_quality_assessment",
        evidence_refs=_evidence_refs(data_confidence),
    )


def _operating_context_dimension(operating_mode: dict[str, Any]) -> dict[str, Any]:
    match = str(operating_mode.get("match") or "unavailable").strip().lower()
    confidence = str(operating_mode.get("confidence") or "").strip().lower()
    if match == "strong" and confidence in {"high", "strong"}:
        level = "high"
    elif match == "strong" or match in {"partial", "moderate"}:
        level = "medium"
    elif match in {"weak", "mismatch", "different"}:
        level = "low"
    else:
        level = "unknown"
    reason = _first_text(
        operating_mode.get("reasons"),
        f"Recorded operating-context match is {match}." if match != "unavailable" else "Operating-context evidence was unavailable.",
    )
    return _dimension(
        level,
        reason,
        method="recorded_operating_mode_comparison",
        evidence_refs=_evidence_refs(operating_mode),
    )


def _interpretation_dimension(
    *,
    classification_type: str,
    classification_confidence: str,
    classification_reason: str,
    evidence_quality: dict[str, Any],
    operating_context: dict[str, Any],
    persistence_status: dict[str, Any],
    sensor_health: list[dict[str, Any]],
    evidence_refs: list[str],
) -> dict[str, Any]:
    if classification_type == "known_operational_change":
        attribution_status = "supported"
        level = "high" if classification_confidence == "high" else "medium"
    elif classification_type == "possible_instrumentation_issue":
        attribution_status = "hypothesis"
        level = "medium" if any(item.get("health") == "suspect" for item in sensor_health) else "low"
    elif classification_type == "unexplained_systemic_change":
        attribution_status = "unattributed"
        level = (
            "medium"
            if evidence_quality["level"] == "high"
            and operating_context["level"] == "high"
            and persistence_status["status"] == "persistent"
            else "low"
        )
    elif classification_type == "observed_change_under_review":
        attribution_status = "unattributed"
        level = "low"
    elif classification_type == "context_limited_relationship_change":
        attribution_status = "unattributed"
        level = "low"
    else:
        attribution_status = "withheld"
        level = "low" if evidence_quality["level"] != "unknown" else "unknown"
    return {
        **_dimension(
            level,
            classification_reason or "The interpretation is bounded by the deterministic finding classification.",
            method="deterministic_finding_classification",
            evidence_refs=evidence_refs,
        ),
        "attribution_status": attribution_status,
    }


def _sensor_health_alternative(sensor_health: list[dict[str, Any]]) -> str:
    if not sensor_health:
        return "Signal-health checks were unavailable for the affected signals."
    if any(item.get("health") == "suspect" for item in sensor_health):
        return "A recorded signal-health condition may contribute to the observation."
    if all(item.get("health") == "healthy" for item in sensor_health):
        return (
            "Recorded signal-health checks did not identify a supported instrumentation issue; "
            "a condition outside the available checks remains possible."
        )
    return "Recorded signal-health checks did not establish whether an instrumentation issue contributed."


def _sensor_health_refs(sensor_health: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for signal in sensor_health:
        if not isinstance(signal, dict):
            continue
        refs.extend(_evidence_refs(signal))
        for condition in signal.get("conditions", []):
            if isinstance(condition, dict):
                refs.extend(_evidence_refs(condition))
    return _dedupe(refs)


def _support_trend(evidence: dict[str, Any]) -> str | None:
    direct = str(evidence.get("support_trend") or "").strip().lower()
    if direct in SUPPORT_TRENDS:
        return direct
    trajectory = evidence.get("trajectory") if isinstance(evidence.get("trajectory"), dict) else {}
    if str(trajectory.get("scope") or "").strip().lower() != "evidence_support":
        return None
    raw = str(trajectory.get("support_trend") or trajectory.get("state") or "").strip().lower()
    return {
        "strengthening": "increasing",
        "increasing": "increasing",
        "stable": "stable",
        "steady": "stable",
        "weakening": "decreasing",
        "decreasing": "decreasing",
    }.get(raw)


def _relationship_direction(signed: float | None, absolute: float | None) -> str | None:
    if signed is not None and signed > 0:
        return "increased"
    if signed is not None and signed < 0:
        return "decreased"
    if signed is None and absolute is not None and absolute > 0:
        return "shifted"
    return None


def _dimension(
    level: str,
    reason: str,
    *,
    score: float | None = None,
    method: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "level": level if level in CONFIDENCE_LEVELS else "unknown",
        "reason": reason,
        "method": method,
        "evidence_refs": evidence_refs,
    }
    if score is not None:
        result["score"] = score
    return result


def _persistence_default_reason(status: str) -> str:
    return {
        "not_assessed": "Persistence evidence was not available for this finding.",
        "observing": "The available evidence has not yet established persistence.",
        "not_persistent": "The assessed observation did not persist.",
        "intermittent": "The observation recurred intermittently.",
        "persistent": "Persistence is supported by the available evidence.",
        "no_longer_observed": "The previously observed change is no longer present in the current evidence.",
    }[status]


def _evidence_refs(value: dict[str, Any]) -> list[str]:
    refs = value.get("evidence_refs") if isinstance(value.get("evidence_refs"), list) else []
    identifiers = [value.get("evidence_ref"), value.get("evidence_id"), value.get("id")]
    return _dedupe([str(item) for item in [*refs, *identifiers] if item])


def _first_present(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        candidate = value.get(key)
        if candidate is not None and candidate != "":
            return candidate
    return None


def _first_text(*values: Any) -> str:
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text:
                return text
    return ""


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalized_score(value: Any) -> float:
    score = _number(value)
    if score is None:
        return 0.0
    score = abs(score)
    if 1 < score <= 100:
        score /= 100
    return max(0.0, min(1.0, score))


def _normalized_optional_score(value: Any) -> float | None:
    return _normalized_score(value) if value is not None else None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result

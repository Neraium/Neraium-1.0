from __future__ import annotations

import re
from typing import Any

from app.services.finding_classification import (
    CONTEXT_LIMITED_RELATIONSHIP_CHANGE,
    INSUFFICIENT_EVIDENCE,
    KNOWN_OPERATIONAL_CHANGE,
    POSSIBLE_INSTRUMENTATION_ISSUE,
    UNEXPLAINED_SYSTEMIC_CHANGE,
)


SUPPORTED_GUIDANCE_CATEGORIES = {
    "instrumentation",
    "controls",
    "operating_context",
    "physical_system",
    "data_quality",
    "documentation",
}


def build_investigation_guidance(
    *,
    classification: dict[str, Any] | None,
    existing_guidance: list[Any] | None,
    source_signals: list[str] | None,
    operating_mode: dict[str, Any] | None,
    data_confidence: dict[str, Any] | None,
    sensor_health: list[dict[str, Any]] | None,
    relationship_evidence: dict[str, Any] | None,
    persistence: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Structure existing checks and order them using the finding certainty class.

    This is a presentation/contract layer over the existing recommendation text. It
    does not diagnose causes or issue maintenance instructions.
    """

    classification = classification or {}
    operating_mode = operating_mode or {}
    data_confidence = data_confidence or {}
    sensor_health = [item for item in sensor_health or [] if isinstance(item, dict)]
    relationship_evidence = relationship_evidence or {}
    persistence = persistence or {}
    classification_type = str(classification.get("type") or INSUFFICIENT_EVIDENCE)
    reasons = _texts(classification.get("reasons"))
    signals = _signal_labels(source_signals, sensor_health)
    signal_phrase = _joined(signals) or "the affected signals"
    existing = _normalize_existing(existing_guidance)

    if classification_type == POSSIBLE_INSTRUMENTATION_ISSUE:
        condition_reason = _instrumentation_reason(sensor_health) or _first(
            reasons,
            "Signal-health evidence makes source validation the highest-value first step.",
        )
        items = [
            _item(
                f"Verify {signal_phrase} against an independent measurement or source.",
                condition_reason,
                "instrumentation",
            ),
            _item(
                f"Compare {signal_phrase} with available peer measurements over the same analysis window.",
                _peer_reason(sensor_health, relationship_evidence),
                "instrumentation",
            ),
            _item(
                f"Review calibration, timestamp, and sampling history for {signal_phrase}.",
                _history_reason(sensor_health, data_confidence),
                "data_quality",
            ),
            _item(
                "Inspect the relevant monitored boundary or equipment only if validated signals still support the relationship change.",
                "The current classification keeps instrumentation and telemetry checks ahead of any physical-system interpretation.",
                "physical_system",
            ),
        ]
        return _rank(items)

    if classification_type == KNOWN_OPERATIONAL_CHANGE:
        context = _operating_change_phrase(operating_mode)
        recent_mode = _first(
            [operating_mode.get("recent_mode_label"), operating_mode.get("recent_mode")],
            "the recorded recent operating mode",
        )
        items = [
            _item(
                f"Confirm the recorded {context} event in operating or maintenance records.",
                _mode_reason(operating_mode, reasons),
                "operating_context",
            ),
            _item(
                f"Verify the observed relationship behavior is expected for {recent_mode}.",
                "The relationship shift occurred with a recorded mode difference, but expected behavior still requires human confirmation.",
                "controls",
            ),
            _item(
                "Review the next comparable operating window and continue monitoring if the relationship remains expected for that mode.",
                "A like-for-like follow-up can show whether the contextual explanation remains consistent without implying physical degradation.",
                "operating_context",
            ),
        ]
        return _rank(items)

    if classification_type == UNEXPLAINED_SYSTEMIC_CHANGE:
        mode_reason = _mode_reason(operating_mode, reasons)
        relationship_reason = _relationship_reason(relationship_evidence, persistence)
        physical = _first_physical_check(existing) or "Inspect the most relevant monitored boundary, equipment, or subsystem."
        items = [
            _item(
                f"Verify source data and control-state context for {signal_phrase}.",
                "Available checks support review, but source and control context should be confirmed before a physical-system interpretation.",
                "data_quality",
            ),
            _item(
                "Review the affected relationship timeline during comparable operating conditions.",
                f"{mode_reason} {relationship_reason}".strip(),
                "operating_context",
            ),
            _item(
                _ensure_allowed_check(physical),
                "The persistent relationship evidence supports a bounded inspection after data and operating context have been verified.",
                "physical_system",
            ),
            _item(
                "Escalate for engineering review only if the reviewed evidence continues to support concern.",
                str(classification.get("certainty_limit") or "The classification describes a relationship change and does not establish a cause or exact outcome."),
                "documentation",
            ),
        ]
        return _rank(items)

    if classification_type == CONTEXT_LIMITED_RELATIONSHIP_CHANGE:
        items = [
            _item(
                f"Verify source data for {signal_phrase}.",
                "Source validation confirms that the observed relationship change is present in the evidence window.",
                "data_quality",
            ),
            _item(
                "Review load and staging during the evidence window.",
                _mode_reason(operating_mode, reasons),
                "operating_context",
            ),
            _item(
                "Compare operator logs and setpoint changes with the evidence window.",
                "Recorded context can clarify the association without assuming causality.",
                "documentation",
            ),
        ]
        return _rank(items)

    missing = _missing_evidence(data_confidence, operating_mode, relationship_evidence, persistence)
    items = [
        _item(
            f"Review the evidence limitations: {missing}.",
            _first(reasons, "The finding did not clear every certainty gate required for a reliable interpretation."),
            "data_quality",
        ),
        _item(
            f"Collect or validate the minimum additional evidence needed: {_minimum_additional_evidence(data_confidence, operating_mode, relationship_evidence, persistence)}.",
            "Closing the identified evidence gap is necessary before classification can become more specific.",
            "data_quality",
        ),
        _item(
            "Compare the refreshed evidence with the learned relationship before forming a physical-system interpretation.",
            str(classification.get("certainty_limit") or "Available evidence does not support confident physical-system guidance."),
            "operating_context",
        ),
    ]
    return _rank(items)


def _item(check: str, reason: str, category: str) -> dict[str, Any]:
    return {
        "check": _sentence(check),
        "reason": _sentence(reason),
        "category": category if category in SUPPORTED_GUIDANCE_CATEGORIES else "documentation",
        "editable": True,
    }


def _rank(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    seen = set()
    for item in items:
        check = str(item.get("check") or "").strip()
        reason = str(item.get("reason") or "").strip()
        key = check.lower()
        if not check or not reason or key in seen:
            continue
        seen.add(key)
        ranked.append({**item, "rank": len(ranked) + 1})
    return ranked[:3]


def _normalize_existing(values: list[Any] | None) -> list[dict[str, Any]]:
    normalized = []
    for value in values or []:
        if isinstance(value, dict):
            check = str(value.get("check") or value.get("recommendation") or "").strip()
            reason = str(value.get("reason") or "").strip()
            category = str(value.get("category") or _category_for(check))
        else:
            check = str(value or "").strip()
            reason = "This check comes from the existing evidence-backed domain guidance for the affected relationship."
            category = _category_for(check)
        if not check or _contains_unsafe_instruction(check):
            continue
        normalized.append(_item(check, reason or "This check is tied to the current finding evidence.", category))
    return normalized




def _first_physical_check(items: list[dict[str, Any]]) -> str:
    for item in items:
        if item.get("category") == "physical_system":
            return str(item.get("check") or "")
    for item in items:
        check = str(item.get("check") or "")
        if re.match(r"^(inspect|check)\b", check, re.IGNORECASE):
            return check
    return ""


def _category_for(check: str) -> str:
    value = check.lower()
    if any(token in value for token in ("calibrat", "sensor", "transmitter", "telemetry", "timestamp")):
        return "instrumentation"
    if any(token in value for token in ("sampling", "missing data", "source data", "data quality")):
        return "data_quality"
    if any(token in value for token in ("setpoint", "control", "staging", "valve position", "mode", "schedule")):
        return "controls"
    if any(token in value for token in ("log", "record", "document", "maintenance history")):
        return "documentation"
    if re.match(r"^(inspect|check)\b", check, re.IGNORECASE):
        return "physical_system"
    return "operating_context"


def _contains_unsafe_instruction(check: str) -> bool:
    return bool(re.search(r"\b(replace|repair)\b|\bthe cause is\b|\bis failing\b|\bwill fail\b", check, re.IGNORECASE))


def _ensure_allowed_check(check: str) -> str:
    value = _sentence(check)
    if re.match(r"^(verify|review|compare|inspect|rule out|check|confirm)\b", value, re.IGNORECASE):
        return value
    return f"Review {value[0].lower()}{value[1:]}" if value else "Inspect the most relevant monitored boundary, equipment, or subsystem."


def _signal_labels(source_signals: list[str] | None, sensor_health: list[dict[str, Any]]) -> list[str]:
    suspects = [str(item.get("signal") or "") for item in sensor_health if item.get("health") == "suspect"]
    values = suspects or [str(item) for item in source_signals or []]
    labels = []
    for value in values:
        label = re.sub(r"[_-]+", " ", value).strip()
        if label and label.lower() not in {item.lower() for item in labels}:
            labels.append(label)
    return labels[:3]


def _joined(values: list[str]) -> str:
    if len(values) < 2:
        return values[0] if values else ""
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _instrumentation_reason(sensor_health: list[dict[str, Any]]) -> str:
    evidence = []
    for signal in sensor_health:
        if signal.get("health") != "suspect":
            continue
        for condition in signal.get("conditions") or []:
            if isinstance(condition, dict) and condition.get("evidence"):
                evidence.append(str(condition["evidence"]))
    return _first(evidence, "")


def _peer_reason(sensor_health: list[dict[str, Any]], evidence: dict[str, Any]) -> str:
    condition_types = {
        str(condition.get("type") or "")
        for signal in sensor_health
        for condition in signal.get("conditions") or []
        if isinstance(condition, dict)
    }
    if "possible_drift" in condition_types:
        return "Peer-signal divergence is part of the current signal-health evidence, so a like-for-like comparison can test that possibility."
    sources = _texts(evidence.get("source_signals"))
    if sources:
        return f"The relationship evidence is based on {len(sources)} source signal(s), allowing peer behavior to be reviewed without assuming a device fault."
    return "Peer or redundant evidence can separate a signal-path issue from a physical-system relationship change."


def _history_reason(sensor_health: list[dict[str, Any]], data_confidence: dict[str, Any]) -> str:
    condition_types = {
        str(condition.get("type") or "")
        for signal in sensor_health
        for condition in signal.get("conditions") or []
        if isinstance(condition, dict)
    }
    labels = []
    if "timestamp_misalignment" in condition_types:
        labels.append("timestamp alignment")
    if "flatline_or_stuck" in condition_types:
        labels.append("flatline history")
    if "possible_drift" in condition_types:
        labels.append("calibration history")
    reasons = _texts(data_confidence.get("reasons"))
    if labels:
        return f"The current evidence specifically calls for review of {_joined(labels)}."
    return _first(reasons, "Recorded signal-health evidence limits confidence until acquisition history is reviewed.")


def _operating_change_phrase(mode: dict[str, Any]) -> str:
    features = {
        str(item.get("feature") or "")
        for item in mode.get("differences") or []
        if isinstance(item, dict)
    }
    if "active_unit_count" in features or "equipment_state" in features:
        return "equipment staging"
    if "schedule_state" in features:
        return "schedule"
    if "maintenance_state" in features:
        return "maintenance"
    if "setpoint" in features:
        return "setpoint"
    return "staging, schedule, maintenance, or setpoint"


def _mode_reason(mode: dict[str, Any], fallback: list[str]) -> str:
    reasons = [
        str(item.get("reason"))
        for item in mode.get("differences") or []
        if isinstance(item, dict) and item.get("reason")
    ] or _texts(mode.get("reasons")) or fallback
    return _first(reasons, "Operating-mode evidence was not available for a more specific comparison.")


def _relationship_reason(evidence: dict[str, Any], persistence: dict[str, Any]) -> str:
    summary = str(persistence.get("summary") or "").strip()
    baseline = _integer(evidence.get("baseline_sample_size"))
    recent = _integer(evidence.get("recent_sample_size"))
    if summary:
        return _sentence(summary)
    if baseline and recent:
        return f"The comparison includes {baseline} baseline and {recent} recent paired samples."
    return "The available evidence supports a persistent relationship comparison, without identifying a cause."


def _missing_evidence(
    data_confidence: dict[str, Any],
    mode: dict[str, Any],
    relationship: dict[str, Any],
    persistence: dict[str, Any],
) -> str:
    gaps = [value.rstrip(".; ") for value in _texts(data_confidence.get("reasons"))]
    if str(mode.get("match") or "unavailable") != "strong":
        gaps.append("strong like-for-like operating-mode support is unavailable")
    if persistence.get("persistent") is not True:
        gaps.append("persistence is not established")
    if _integer(relationship.get("baseline_sample_size")) < 3 or _integer(relationship.get("recent_sample_size")) < 3:
        gaps.append("paired baseline or recent samples are sparse")
    return "; ".join(_dedupe(gaps)[:3]) or "the available evidence does not clear the required certainty gates"


def _minimum_additional_evidence(
    data_confidence: dict[str, Any],
    mode: dict[str, Any],
    relationship: dict[str, Any],
    persistence: dict[str, Any],
) -> str:
    needs = []
    if str(data_confidence.get("rating") or "low") == "low":
        needs.append("a regularly sampled, quality-checked comparison window")
    if str(mode.get("match") or "unavailable") != "strong":
        needs.append("recorded control state or operating-mode context")
    if _integer(relationship.get("baseline_sample_size")) < 3 or _integer(relationship.get("recent_sample_size")) < 3:
        needs.append("at least three paired samples in each comparison window")
    if persistence.get("persistent") is not True:
        needs.append("another comparable window to evaluate persistence")
    return _joined(_dedupe(needs)) or "source validation and another comparable evidence window"


def _texts(value: Any) -> list[str]:
    return [str(item).strip() for item in value] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _first(values: list[Any], fallback: str) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return fallback


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    return text if text.endswith((".", "!", "?")) else f"{text}."

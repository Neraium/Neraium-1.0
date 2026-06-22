from __future__ import annotations

from typing import Any

CONFIDENCE_CAP = 55
INTEGRITY_WARNING = "Telemetry integrity reduced confidence for this insight."
INTEGRITY_BASIS = "Telemetry integrity reduced confidence for this analysis window."


def apply_telemetry_confidence_adjustment(
    intelligence: dict[str, Any],
    *,
    data_quality: dict[str, Any],
) -> dict[str, Any]:
    """Cap SII output confidence when telemetry integrity marks the window."""

    normalization_report = data_quality.get("normalization_report") if isinstance(data_quality, dict) else {}
    if not isinstance(normalization_report, dict) or not normalization_report.get("window_suppressed"):
        return intelligence

    result = dict(intelligence)
    result["telemetry_confidence_adjusted"] = True
    result["confidence_adjustment_reason"] = INTEGRITY_BASIS
    result["data_quality_warning"] = INTEGRITY_WARNING
    result["reliability_rating"] = min_reliability_rating(result.get("reliability_rating"))

    if isinstance(result.get("neraium_score"), (int, float)):
        result["neraium_score"] = min(int(result["neraium_score"]), CONFIDENCE_CAP)

    result["confidence_basis"] = append_sentence(result.get("confidence_basis"), INTEGRITY_BASIS)
    result["confidence_components"] = adjust_confidence_components(result.get("confidence_components"))

    rooms = result.get("rooms")
    if isinstance(rooms, list):
        result["rooms"] = [adjust_room_confidence(room) for room in rooms]

    source_metadata = result.get("source_metadata") if isinstance(result.get("source_metadata"), dict) else {}
    result["source_metadata"] = {
        **source_metadata,
        "telemetry_confidence_adjusted": True,
        "confidence_adjustment_reason": INTEGRITY_BASIS,
    }

    core_outputs = result.get("core_sii_outputs") if isinstance(result.get("core_sii_outputs"), dict) else {}
    review_window = core_outputs.get("review_window_inference") if isinstance(core_outputs.get("review_window_inference"), dict) else {}
    if review_window:
        result["core_sii_outputs"] = {
            **core_outputs,
            "review_window_inference": {
                **review_window,
                "confidence_basis": append_sentence(review_window.get("confidence_basis"), INTEGRITY_BASIS),
            },
        }

    return result


def adjust_room_confidence(room: Any) -> Any:
    if not isinstance(room, dict):
        return room
    updated = dict(room)
    if isinstance(updated.get("confidence"), (int, float)):
        updated["confidence"] = min(int(updated["confidence"]), CONFIDENCE_CAP)
    updated["confidence_basis"] = append_sentence(updated.get("confidence_basis"), INTEGRITY_BASIS)
    updated["confidence_components"] = adjust_confidence_components(updated.get("confidence_components"))
    updated["telemetry_confidence_adjusted"] = True
    return updated


def adjust_confidence_components(components: Any) -> dict[str, Any]:
    current = dict(components) if isinstance(components, dict) else {}
    return {
        **current,
        "data_sufficiency": "low",
        "telemetry_integrity": "reduced_confidence",
    }


def append_sentence(value: Any, sentence: str) -> str:
    base = str(value or "").strip()
    if not base:
        return sentence
    if sentence in base:
        return base
    separator = " " if base.endswith(".") else ". "
    return f"{base}{separator}{sentence}"


def min_reliability_rating(value: Any) -> str:
    order = ["not_reliable", "weak", "usable", "strong"]
    current = str(value or "unknown")
    if current not in order:
        return "weak"
    return current if order.index(current) <= order.index("weak") else "weak"

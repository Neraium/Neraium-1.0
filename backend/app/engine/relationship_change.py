"""Shared, non-causal relationship change rules and read-only temporal evidence."""
from __future__ import annotations

import math
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

ABRUPT_CHANGE_THRESHOLD = 0.25
MINIMUM_EDGE_CONFIDENCE = 0.45
MINIMUM_DATA_QUALITY = 0.35
TEMPORAL_RULES = {
    "maximum_observations": 8,
    "minimum_supporting_observations": 6,
    "minimum_direction_agreement": 0.75,
    "minimum_displacement": 0.15,
    "maximum_age_days": 30,
}


def relationship_change_type(baseline: float, current: float, *, persistent: bool = False) -> str:
    before, after = abs(baseline), abs(current)
    if before >= 0.35 and after >= 0.35 and (baseline > 0) != (current > 0):
        return "disrupted"
    if before >= 0.65 and after < 0.35:
        return "missing"
    if before >= 0.65 and after <= before - ABRUPT_CHANGE_THRESHOLD:
        return "weakened"
    if after >= 0.65 and before < 0.35:
        return "new"
    if after >= before + ABRUPT_CHANGE_THRESHOLD:
        return "strengthened"
    if persistent:
        return "strengthened" if after > before else "weakened"
    return "stable"


def relationship_change_promotable(
    *, change_type: str, baseline_strength: float, current_strength: float,
    drift: float, eligible: bool = True, persistent: bool = False,
    threshold: float = ABRUPT_CHANGE_THRESHOLD,
) -> bool:
    if not eligible or (not persistent and drift < threshold):
        return False
    if change_type in {"disrupted", "missing", "weakened"}:
        return baseline_strength >= 0.65
    if change_type == "strengthened":
        return baseline_strength >= 0.5 and current_strength >= 0.65
    if change_type == "new":
        return current_strength >= 0.75
    return False


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def relationship_temporal_evidence(
    edge: dict[str, Any], previous: dict[str, Any] | None, *, basis: str,
    minimum_confidence: float = MINIMUM_EDGE_CONFIDENCE,
    minimum_quality: float = MINIMUM_DATA_QUALITY,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reduce at most eight chronological windows; never mutate caller state.

    Each acceptable window votes for its signed displacement from one fixed
    baseline, not the slope between adjacent windows. Neutral, reversed and
    poor-quality windows occupy the horizon but cannot add support. This is
    bounded directional evidence, not a probability or independent-sample test.
    """
    window = edge.get("time_window") or {}
    identity = {
        "columns": sorted(edge["columns"]),
        "basis": basis,
        "baseline_correlation": edge.get("baseline_correlation"),
        "baseline_start": window.get("baseline_start"),
        "baseline_end": window.get("baseline_end"),
        "mode": deepcopy(edge.get("mode_conditioning") or {
            "baseline_mode": (edge.get("operating_mode_context") or {}).get("baseline_mode"),
            "recent_mode": (edge.get("operating_mode_context") or {}).get("recent_mode"),
        }),
        "reference_dataset_id": edge.get("reference_dataset_id"),
        "signal_units": deepcopy(edge.get("signal_units")),
    }
    previous = previous or {}
    state = {"version": 1, "identity": identity, "observations": []}
    if previous.get("version") == 1 and previous.get("identity") == identity:
        state["observations"] = deepcopy(previous.get("observations", []))[-TEMPORAL_RULES["maximum_observations"]:]
    observations = state["observations"]
    observed_at = _time(window.get("current_end"))
    start = _time(window.get("current_start"))
    delta = edge["signed_correlation_delta"]
    acceptable = bool(
        edge["eligible"] and math.isfinite(delta)
        and edge["edge_confidence"] >= minimum_confidence
        and edge["data_quality_factor"] >= minimum_quality
    )
    observation = {
        "observed_at": observed_at.isoformat() if observed_at else None,
        "time_window": deepcopy(window),
        "source_rows": deepcopy(edge.get("source_rows", [])),
        "source_dataset_id": edge.get("source_dataset_id"),
        "signed_correlation_delta": delta,
        "edge_confidence": edge["edge_confidence"],
        "data_quality_factor": edge["data_quality_factor"],
        "eligible": edge["eligible"],
        "acceptable": acceptable,
    }
    chronological = observed_at is not None and (not window.get("current_start") or start is not None)
    try:
        if start is not None and observed_at is not None and start > observed_at:
            chronological = False
        candidates = observations
        if chronological and observations:
            times = [_time(item["observed_at"]) for item in observations]
            if any(value is None for value in times) or any(left >= right for left, right in zip(times, times[1:])):
                chronological = False
            elif observed_at < times[-1]:
                chronological = False
            elif observed_at == times[-1]:
                chronological = observation == observations[-1]
            else:
                candidates = [*observations, observation]
        elif chronological:
            candidates = [observation]
        if chronological:
            observations = [item for item in candidates if (
                observed_at - _time(item["observed_at"]) <= timedelta(days=TEMPORAL_RULES["maximum_age_days"])
            )][-TEMPORAL_RULES["maximum_observations"]:]
            state["observations"] = observations
    except (TypeError, ValueError, KeyError):
        chronological = False
    # Recheck the configured quality floors for every retained observation.
    def vote(item: dict[str, Any]) -> int:
        value = item["signed_correlation_delta"]
        if not (item["eligible"] and item["acceptable"]
                and item["edge_confidence"] >= minimum_confidence
                and item["data_quality_factor"] >= minimum_quality
                and math.isfinite(value) and abs(value) >= TEMPORAL_RULES["minimum_displacement"]):
            return 0
        return 1 if value > 0 else -1

    votes = [vote(item) for item in observations] if chronological else []
    direction = 1 if votes.count(1) > votes.count(-1) else -1 if votes.count(-1) > votes.count(1) else 0
    supporting = [deepcopy(item) for item, value in zip(observations, votes) if direction and value == direction]
    agreement = len(supporting) / max(1, len(votes))
    supported = bool(
        chronological and len(supporting) >= TEMPORAL_RULES["minimum_supporting_observations"]
        and agreement >= TEMPORAL_RULES["minimum_direction_agreement"]
        and vote(observation) == direction
    )
    evidence = {
        "temporal_persistence_observations": len(votes),
        "temporal_persistence_supporting_observations": len(supporting),
        "temporal_persistence_direction": direction,
        "temporal_persistence_direction_agreement": round(agreement, 6),
        "temporal_persistence_supported": supported,
        "persistent_relationship_change": supported,
        "temporal_persistence_status": "supported" if supported else "unconfirmed" if chronological else "limited",
        "supporting_windows": supporting,
        "first_supported_observation": supporting[0]["observed_at"] if supporting else None,
        "latest_supported_observation": supporting[-1]["observed_at"] if supporting else None,
        "persistence_factor": round(agreement * min(1.0, len(supporting) / TEMPORAL_RULES["minimum_supporting_observations"]), 6),
    }
    return evidence, state

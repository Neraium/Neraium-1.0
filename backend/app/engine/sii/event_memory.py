from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


SUPPORTED_EVENT_TYPES = {
    "significant_behavioral_observation",
    "validated_operating_change",
    "maintenance_event",
    "sensor_replacement",
    "control_strategy_change",
    "equipment_replacement",
    "operating_mode_transition",
    "baseline_update",
    "relationship_emergence",
    "relationship_retirement",
    "behavioral_recovery",
    "human_validation_outcome",
}


def prepare_event_memory(
    *,
    external_events: list[dict[str, Any]] | None,
    expected_behavior: dict[str, Any],
    graph_comparison: dict[str, Any],
    operating_mode: dict[str, Any],
    learning_decision: dict[str, Any],
    source_run_id: str,
    timestamp: str,
    model_version_before: str | None,
    model_version_after: str | None,
    baseline_version_before: str | None,
    baseline_version_after: str | None,
) -> dict[str, Any]:
    limitations: list[str] = []
    external = []
    for index, event in enumerate(external_events or []):
        normalized, reason = _external_event(event, index, source_run_id)
        if normalized is None:
            limitations.append(reason or f"external_event_{index}_invalid")
        else:
            external.append(normalized)
    derived: list[dict[str, Any]] = []
    for item in expected_behavior.get("residual_evidence", []):
        if not isinstance(item, dict):
            continue
        derived.append(
            _event(
                event_type="significant_behavioral_observation",
                timestamp=timestamp,
                source="telemetry_derived",
                source_run_id=source_run_id,
                affected_signals=[str(item.get("target_signal"))] if item.get("target_signal") else [],
                affected_relationships=list(item.get("source_relationships") or []),
                supporting_evidence=[deepcopy(item)],
                limiting_evidence=[],
                model_version_before=model_version_before,
                model_version_after=model_version_after,
                baseline_version_before=baseline_version_before,
                baseline_version_after=baseline_version_after,
                limitations=["This event records residual evidence and is not a failure declaration."],
            )
        )
    for field, event_type in (
        ("edge_emergence", "relationship_emergence"),
        ("edges_not_observed", "relationship_retirement"),
    ):
        for item in graph_comparison.get(field, []):
            if not isinstance(item, dict):
                continue
            # A missing edge is not called retired until its persistent state says so.
            if event_type == "relationship_retirement" and item.get("change_type") != "retired":
                continue
            derived.append(
                _event(
                    event_type=event_type,
                    timestamp=timestamp,
                    source="telemetry_derived",
                    source_run_id=source_run_id,
                    affected_signals=[value for value in (item.get("source_signal"), item.get("target_signal")) if value],
                    affected_relationships=[str(item.get("relationship_id"))],
                    supporting_evidence=[deepcopy(item)],
                    limiting_evidence=[],
                    model_version_before=model_version_before,
                    model_version_after=model_version_after,
                    baseline_version_before=baseline_version_before,
                    baseline_version_after=baseline_version_after,
                    limitations=["Relationship lifecycle evidence is non-causal."],
                )
            )
    baseline_mode = operating_mode.get("baseline_mode")
    recent_mode = operating_mode.get("recent_mode")
    if baseline_mode and recent_mode and baseline_mode != recent_mode and recent_mode != "unavailable":
        derived.append(
            _event(
                event_type="operating_mode_transition",
                timestamp=timestamp,
                source="telemetry_derived",
                source_run_id=source_run_id,
                affected_signals=[],
                affected_relationships=[],
                supporting_evidence=[{"baseline_mode": baseline_mode, "recent_mode": recent_mode, "mode_evidence": deepcopy(operating_mode)}],
                limiting_evidence=[],
                model_version_before=model_version_before,
                model_version_after=model_version_after,
                baseline_version_before=baseline_version_before,
                baseline_version_after=baseline_version_after,
                limitations=[],
            )
        )
    if learning_decision.get("decision") == "accepted" and not learning_decision.get("pending_validation"):
        derived.append(
            _event(
                event_type="baseline_update",
                timestamp=timestamp,
                source="engine_learning_decision",
                source_run_id=source_run_id,
                affected_signals=list(learning_decision.get("affected_signals") or []),
                affected_relationships=list(learning_decision.get("affected_relationships") or []),
                supporting_evidence=list(learning_decision.get("source_evidence") or []),
                limiting_evidence=[],
                model_version_before=model_version_before,
                model_version_after=model_version_after,
                baseline_version_before=baseline_version_before,
                baseline_version_after=baseline_version_after,
                limitations=[],
            )
        )
    events = _unique_events([*external, *derived])
    return {
        "status": "complete" if not limitations else "limited",
        "events": events,
        "events_recorded": len(events),
        "events_referenced": [item["event_id"] for item in events],
        "externally_supplied_events": external,
        "telemetry_derived_events": derived,
        "limitations": limitations,
    }


def event_memory_section(result: dict[str, Any], persisted_ids: list[str]) -> dict[str, Any]:
    return {
        "status": result.get("status", "limited"),
        "events_recorded": len(persisted_ids),
        "events_referenced": list(persisted_ids),
        "externally_supplied_events": deepcopy(result.get("externally_supplied_events", [])),
        "telemetry_derived_events": deepcopy(result.get("telemetry_derived_events", [])),
        "limitations": deepcopy(result.get("limitations", [])),
    }


def _external_event(
    event: dict[str, Any], index: int, source_run_id: str
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(event, dict):
        return None, f"external_event_{index}_not_an_object"
    event_type = str(event.get("event_type") or "")
    if event_type not in SUPPORTED_EVENT_TYPES:
        return None, f"external_event_{index}_unsupported_type:{event_type}"
    timestamp = str(event.get("timestamp") or "").strip()
    source = str(event.get("source") or "").strip()
    if not timestamp or not source:
        return None, f"external_event_{index}_missing_timestamp_or_source"
    event_id = str(event.get("event_id") or _event_id(event_type, timestamp, source, source_run_id, index))
    return (
        {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "source": source,
            "source_origin": "externally_supplied",
            "source_run_id": event.get("source_run_id"),
            "affected_signals": list(event.get("affected_signals") or []),
            "affected_relationships": list(event.get("affected_relationships") or []),
            "affected_systems": list(event.get("affected_systems") or []),
            "supporting_evidence": deepcopy(event.get("supporting_evidence") or []),
            "limiting_evidence": deepcopy(event.get("limiting_evidence") or []),
            "human_validation": deepcopy(event.get("human_validation")),
            "model_version_before": event.get("model_version_before"),
            "model_version_after": event.get("model_version_after"),
            "baseline_version_before": event.get("baseline_version_before"),
            "baseline_version_after": event.get("baseline_version_after"),
            "limitations": list(event.get("limitations") or []),
            "notes": event.get("notes"),
        },
        None,
    )


def _event(
    *,
    event_type: str,
    timestamp: str,
    source: str,
    source_run_id: str,
    affected_signals: list[str],
    affected_relationships: list[str],
    supporting_evidence: list[Any],
    limiting_evidence: list[Any],
    model_version_before: str | None,
    model_version_after: str | None,
    baseline_version_before: str | None,
    baseline_version_after: str | None,
    limitations: list[str],
) -> dict[str, Any]:
    seed = {
        "event_type": event_type,
        "timestamp": timestamp,
        "source_run_id": source_run_id,
        "signals": affected_signals,
        "relationships": affected_relationships,
    }
    event_id = _event_id(event_type, timestamp, source, source_run_id, str(seed))
    return {
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "source": source,
        "source_origin": "telemetry_derived" if source == "telemetry_derived" else "engine_decision",
        "source_run_id": source_run_id,
        "affected_signals": list(affected_signals),
        "affected_relationships": list(affected_relationships),
        "affected_systems": [],
        "supporting_evidence": deepcopy(supporting_evidence),
        "limiting_evidence": deepcopy(limiting_evidence),
        "human_validation": None,
        "model_version_before": model_version_before,
        "model_version_after": model_version_after,
        "baseline_version_before": baseline_version_before,
        "baseline_version_after": baseline_version_after,
        "limitations": list(limitations),
        "notes": None,
    }


def _event_id(event_type: str, timestamp: str, source: str, source_run_id: str, discriminator: Any) -> str:
    seed = f"{event_type}|{timestamp}|{source}|{source_run_id}|{discriminator}"
    return f"behavioral-event:{sha256(seed.encode('utf-8')).hexdigest()[:24]}"


def _unique_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = {}
    for event in events:
        output[str(event["event_id"])] = event
    return [output[key] for key in sorted(output)]

from __future__ import annotations

import json
from typing import Any


def _observation_type_from_result(result: dict[str, Any]) -> str:
    relationship_drift = ((result.get("baseline_analysis") or {}).get("relationship_drift")) or []
    if relationship_drift:
        return "baseline_shift"
    warnings = ((result.get("data_quality") or {}).get("warnings")) or []
    if warnings:
        return "data_condition"
    return "baseline_shift"


def _observation_variables_from_result(result: dict[str, Any]) -> list[str]:
    variables = [str(column) for column in (result.get("columns") or []) if str(column).strip()]
    if variables:
        return variables[:12]
    cultivation_mapping = result.get("cultivation_mapping") or {}
    categories = cultivation_mapping.get("categories") if isinstance(cultivation_mapping, dict) else {}
    inferred: list[str] = []
    if isinstance(categories, dict):
        for mapped in categories.values():
            if isinstance(mapped, list):
                inferred.extend(str(column) for column in mapped if str(column).strip())
    return list(dict.fromkeys(inferred))[:12]


def _data_conditions_from_result(result: dict[str, Any]) -> list[str]:
    data_quality = result.get("data_quality") or {}
    warnings = (data_quality.get("warnings") if isinstance(data_quality, dict) else []) or []
    conditions = [str(item) for item in warnings if str(item).strip()]
    processing_trace = result.get("processing_trace") or {}
    if processing_trace.get("completed_with_partial_result"):
        conditions.append("partial_processing")
    return list(dict.fromkeys(conditions))[:8]


def _deformation_started_at(result: dict[str, Any]) -> str | None:
    replay = result.get("replay_timeline") or ((result.get("sii_intelligence") or {}).get("replay_timeline")) or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    if isinstance(timeline, list):
        for frame in timeline:
            if not isinstance(frame, dict):
                continue
            topology_state = frame.get("topology_state") or {}
            drift_index = topology_state.get("drift_index") if isinstance(topology_state, dict) else None
            if isinstance(drift_index, (int, float)) and drift_index >= 0.15:
                return str(frame.get("timestamp_start") or frame.get("timestamp") or "") or None
    profile = result.get("timestamp_profile") or {}
    if isinstance(profile, dict):
        return profile.get("first_timestamp")
    return None


def _source_rows_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = result.get("baseline_analysis") or {}
    anchors: list[dict[str, Any]] = []
    for item in baseline.get("top_relationship_changes") or baseline.get("relationship_drift") or []:
        if not isinstance(item, dict):
            continue
        for anchor in item.get("source_rows") or []:
            if isinstance(anchor, dict):
                anchors.append(
                    {
                        "window": anchor.get("window"),
                        "source_row": anchor.get("source_row"),
                        "timestamp": anchor.get("timestamp"),
                    }
                )
        for ref in item.get("evidence_refs") or []:
            if not isinstance(ref, dict):
                continue
            for anchor in ref.get("source_rows") or []:
                if isinstance(anchor, dict):
                    anchors.append(
                        {
                            "window": anchor.get("window"),
                            "source_row": anchor.get("source_row"),
                            "timestamp": anchor.get("timestamp"),
                            "column": ref.get("column"),
                        }
                    )
    if not anchors:
        profile = result.get("timestamp_profile") or {}
        first = profile.get("first_timestamp") if isinstance(profile, dict) else None
        last = profile.get("last_timestamp") if isinstance(profile, dict) else None
        if first:
            anchors.append({"window": "upload_start", "timestamp": first})
        if last and last != first:
            anchors.append({"window": "upload_end", "timestamp": last})
    seen: set[tuple[Any, Any, Any, Any]] = set()
    deduped: list[dict[str, Any]] = []
    for anchor in anchors:
        key = (anchor.get("window"), anchor.get("source_row"), anchor.get("timestamp"), anchor.get("column"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(anchor)
    return deduped[:16]


def _evidence_windows_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = result.get("baseline_analysis") or {}
    windows: list[dict[str, Any]] = []
    for item in baseline.get("top_relationship_changes") or baseline.get("relationship_drift") or []:
        if not isinstance(item, dict):
            continue
        for ref in item.get("evidence_refs") or []:
            if not isinstance(ref, dict):
                continue
            windows.append(
                {
                    "column": ref.get("column"),
                    "baseline_window": ref.get("baseline_window") if not isinstance(ref.get("baseline_window"), (dict, list)) else json.dumps(ref.get("baseline_window"), sort_keys=True, default=str),
                    "recent_window": ref.get("recent_window") if not isinstance(ref.get("recent_window"), (dict, list)) else json.dumps(ref.get("recent_window"), sort_keys=True, default=str),
                }
            )
    replay = result.get("replay_timeline") or ((result.get("sii_intelligence") or {}).get("replay_timeline")) or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    if isinstance(timeline, list):
        for frame in timeline[:8]:
            if not isinstance(frame, dict):
                continue
            windows.append(
                {
                    "frame_index": frame.get("frame_index"),
                    "window_start": frame.get("timestamp_start") or frame.get("timestamp"),
                    "window_end": frame.get("timestamp_end") or frame.get("timestamp"),
                }
            )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for window in windows:
        key = (
            window.get("column"),
            window.get("baseline_window"),
            window.get("recent_window"),
            window.get("frame_index"),
            window.get("window_start"),
            window.get("window_end"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(window)
    return deduped[:16]


def _traceability_timestamps_from_result(result: dict[str, Any]) -> dict[str, Any]:
    profile = result.get("timestamp_profile") or {}
    replay = result.get("replay_timeline") or ((result.get("sii_intelligence") or {}).get("replay_timeline")) or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    first_frame = timeline[0] if isinstance(timeline, list) and timeline else {}
    last_frame = timeline[-1] if isinstance(timeline, list) and timeline else {}
    return {
        "created_at": result.get("created_at") or result.get("completed_at") or result.get("last_processed_at"),
        "completed_at": result.get("completed_at") or result.get("last_processed_at"),
        "processed_at": result.get("last_processed_at") or result.get("completed_at"),
        "upload_start": (profile.get("first_timestamp") if isinstance(profile, dict) else None) or first_frame.get("timestamp_start") or first_frame.get("timestamp"),
        "upload_end": (profile.get("last_timestamp") if isinstance(profile, dict) else None) or last_frame.get("timestamp_end") or last_frame.get("timestamp"),
    }


def build_traceability_packet(*, job_id: str, filename: str, result: dict[str, Any]) -> dict[str, Any]:
    source_rows = _source_rows_from_result(result)
    evidence_windows = _evidence_windows_from_result(result)
    timestamps = _traceability_timestamps_from_result(result)
    return {
        "job_id": str(job_id),
        "run_id": str(job_id),
        "upload_id": str(job_id),
        "source_name": filename,
        "source_rows": source_rows,
        "evidence_windows": evidence_windows,
        "timestamps": timestamps,
        "aligned": True,
        "traceability_complete": bool(
            job_id
            and source_rows
            and evidence_windows
            and timestamps.get("processed_at")
            and timestamps.get("upload_start")
            and timestamps.get("upload_end")
        ),
    }


def build_evidence_record_from_result(
    *,
    run_id: str,
    filename: str,
    source_type: str,
    result: dict[str, Any],
    created_at: str,
    completed_at: str,
    status: str,
    initiated_by: str,
    rows_received: int | None = None,
    rows_accepted: int | None = None,
    rows_rejected: int | None = None,
) -> dict[str, Any]:
    sii = result.get("sii_intelligence") or {}
    replay = result.get("replay_timeline") or (sii.get("replay_timeline")) or {}
    replay_timeline = replay.get("timeline") if isinstance(replay, dict) else []
    latest_frame = replay_timeline[-1] if isinstance(replay_timeline, list) and replay_timeline else {}
    baseline_payload = result.get("baseline_analysis") or {}
    relationship_drift = (baseline_payload.get("relationship_drift") or baseline_payload.get("top_relationship_changes") or [])
    primary_relationship = relationship_drift[0] if isinstance(relationship_drift, list) and relationship_drift else {}
    variables = _observation_variables_from_result(result)
    data_conditions = _data_conditions_from_result(result)
    source_rows = _source_rows_from_result(result)
    observation_type = _observation_type_from_result(result)
    structural_state = str(result.get("operating_state") or sii.get("facility_state") or "Monitoring")
    traceability = build_traceability_packet(job_id=run_id, filename=filename, result=result)
    confidence_score = sii.get("confidence")
    if confidence_score is None:
        confidence_score = ((sii.get("rooms") or [{}])[0] or {}).get("confidence")
    drift_metrics = {
        "neraium_score": sii.get("neraium_score"),
        "baseline_distance": latest_frame.get("baseline_distance") if isinstance(latest_frame, dict) else None,
        "drift_index": ((latest_frame.get("topology_state") or {}).get("drift_index")) if isinstance(latest_frame, dict) else None,
        "drift_velocity": latest_frame.get("drift_velocity") if isinstance(latest_frame, dict) else None,
        "drift_acceleration": latest_frame.get("drift_acceleration") if isinstance(latest_frame, dict) else None,
        "coupling_delta": primary_relationship.get("correlation_delta") if isinstance(primary_relationship, dict) else None,
        "relationship_change_count": len(relationship_drift) if isinstance(relationship_drift, list) else 0,
        "observed_persistence": sii.get("observed_persistence"),
        "active_observations": 1 if str(status).lower() == "completed" and observation_type != "data_condition" else 0,
        "replay_frame_count": len(replay_timeline) if isinstance(replay_timeline, list) else 0,
    }
    primary_drivers = [str(sii.get("primary_driver"))] if sii.get("primary_driver") else []
    supporting_evidence = [str(item) for item in (sii.get("supporting_evidence") or [])[:6]]
    archetypes = [str(item) for item in (sii.get("structural_archetypes") or [])[:4]]
    water_intelligence = result.get("water_intelligence") if isinstance(result.get("water_intelligence"), dict) else {}
    water_prior_versions = [
        {
            "relationship_prior_id": item.get("relationship_prior_id"),
            "relationship_prior_version": item.get("relationship_prior_version"),
            "sii_finding_id": item.get("sii_finding_id"),
        }
        for item in water_intelligence.get("insights", [])
        if isinstance(item, dict) and item.get("relationship_prior_id")
    ]
    return {
        "run_id": run_id,
        "job_id": run_id,
        "upload_id": run_id,
        "source_name": filename,
        "source_type": source_type,
        "source_url": None,
        "status": status,
        "created_at": created_at,
        "completed_at": completed_at,
        "rows_received": rows_received if rows_received is not None else int(result.get("row_count") or 0),
        "rows_accepted": rows_accepted if rows_accepted is not None else int(result.get("row_count") or 0),
        "rows_rejected": rows_rejected if rows_rejected is not None else 0,
        "sensors_detected": max(0, int(result.get("column_count") or 0) - 1),
        "room": (sii.get("primary_room") or "Uploaded telemetry"),
        "operating_state": result.get("operating_state"),
        "neraium_score": sii.get("neraium_score"),
        "drift_status": result.get("drift_status"),
        "scenario": None,
        "tick": None,
        "warnings": [],
        "errors": [],
        "primary_drivers": primary_drivers,
        "evidence_summary": supporting_evidence,
        "structural_archetypes": archetypes,
        "adaptive_site_key": "site::default",
        "operator_feedback_history": [],
        "initiated_by": initiated_by,
        "observation_type": observation_type,
        "observation_status": "open" if str(status).lower() == "completed" else str(status).lower(),
        "variables": variables,
        "drift_metrics": drift_metrics,
        "data_conditions": data_conditions,
        "source_rows": source_rows,
        "evidence_windows": traceability["evidence_windows"],
        "timestamps": traceability["timestamps"],
        "traceability": traceability,
        "confidence_score": confidence_score,
        "regime_label": str(sii.get("baseline_regime") or sii.get("regime_label") or "State Group A"),
        "structural_state": structural_state,
        "deformation_started_at": _deformation_started_at(result),
        "water_intelligence": water_intelligence,
        "water_prior_versions": water_prior_versions,
    }

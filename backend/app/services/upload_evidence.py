from __future__ import annotations

import json
from typing import Any

from app.services.analysis_provenance import build_analysis_provenance, canonical_digest


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _compatibility(result: dict[str, Any]) -> dict[str, Any]:
    return _mapping(result.get("compatibility"))


def _canonical_data_conditions(result: dict[str, Any]) -> dict[str, Any]:
    return _mapping(result.get("data_conditions"))


def _baseline_payload_from_result(result: dict[str, Any]) -> dict[str, Any]:
    legacy = _mapping(result.get("baseline_analysis"))
    if legacy:
        return legacy
    signal_drift = _mapping(result.get("signal_drift"))
    relationship_analysis = _mapping(result.get("relationship_analysis"))
    compatibility_baseline = _mapping(_compatibility(result).get("baseline_analysis"))
    if compatibility_baseline:
        return compatibility_baseline
    if relationship_analysis:
        return relationship_analysis
    return signal_drift


def _data_quality_from_result(result: dict[str, Any]) -> dict[str, Any]:
    legacy = _mapping(result.get("data_quality"))
    if legacy:
        return legacy
    canonical = _mapping(_canonical_data_conditions(result).get("data_quality"))
    if canonical:
        return canonical
    return _mapping(_compatibility(result).get("data_quality"))


def _timestamp_profile_from_result(result: dict[str, Any]) -> dict[str, Any]:
    legacy = _mapping(result.get("timestamp_profile"))
    if legacy:
        return legacy
    canonical = _mapping(_canonical_data_conditions(result).get("timestamp_profile"))
    if canonical:
        return canonical
    return _mapping(_compatibility(result).get("timestamp_profile"))


def _relationship_drift_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = _baseline_payload_from_result(result)
    candidates = baseline.get("relationship_drift") or baseline.get("top_relationship_changes") or []
    if not candidates:
        relationship_analysis = _mapping(result.get("relationship_analysis"))
        candidates = (
            relationship_analysis.get("relationship_drift")
            or relationship_analysis.get("top_relationship_changes")
            or []
        )
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _processing_trace_from_result(result: dict[str, Any]) -> dict[str, Any]:
    trace = _mapping(result.get("processing_trace"))
    if trace:
        return trace
    return _mapping(_compatibility(result).get("processing_trace"))


def _row_count_from_result(result: dict[str, Any]) -> int:
    for value in (
        result.get("row_count"),
        _canonical_data_conditions(result).get("rows_used"),
        _canonical_data_conditions(result).get("rows_received"),
        _processing_trace_from_result(result).get("rows_used"),
        _processing_trace_from_result(result).get("rows_received"),
    ):
        try:
            if value is not None:
                return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _sensor_count_from_result(result: dict[str, Any]) -> int:
    try:
        if result.get("column_count") is not None:
            return max(0, int(result.get("column_count")) - 1)
    except (TypeError, ValueError):
        pass
    numeric_columns = _canonical_data_conditions(result).get("numeric_columns")
    if isinstance(numeric_columns, list):
        return len([column for column in numeric_columns if str(column).strip()])
    return 0


def _observation_type_from_result(result: dict[str, Any]) -> str:
    if _relationship_drift_from_result(result):
        return "baseline_shift"
    warnings = _data_quality_from_result(result).get("warnings") or []
    if warnings:
        return "data_condition"
    return "monitoring_observation"


def _observation_variables_from_result(result: dict[str, Any]) -> list[str]:
    variables = [str(column) for column in (result.get("columns") or []) if str(column).strip()]
    if variables:
        return variables[:12]
    numeric_columns = _canonical_data_conditions(result).get("numeric_columns")
    if isinstance(numeric_columns, list):
        variables = [str(column) for column in numeric_columns if str(column).strip()]
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
    data_quality = _data_quality_from_result(result)
    warnings = data_quality.get("warnings") or []
    conditions = [str(item) for item in warnings if str(item).strip()]
    processing_trace = _processing_trace_from_result(result)
    if processing_trace.get("completed_with_partial_result"):
        conditions.append("partial_processing")
    failed_modules = processing_trace.get("modules_failed")
    if isinstance(failed_modules, list) and failed_modules:
        conditions.append("module_failures_present")
    return list(dict.fromkeys(conditions))[:8]


def _phase2_supporting_evidence_from_result(result: dict[str, Any]) -> dict[str, Any]:
    sii = result.get("sii_result") if isinstance(result.get("sii_result"), dict) else {}
    if not sii:
        return {}
    graph = sii.get("relationship_graph") if isinstance(sii.get("relationship_graph"), dict) else {}
    operating_modes = sii.get("operating_modes") if isinstance(sii.get("operating_modes"), dict) else {}
    conditioned = (
        operating_modes.get("mode_conditioned_baseline")
        if isinstance(operating_modes.get("mode_conditioned_baseline"), dict)
        else {}
    )
    persistence = sii.get("persistence_analysis") if isinstance(sii.get("persistence_analysis"), dict) else {}
    adaptive = persistence.get("adaptive_persistence") if isinstance(persistence.get("adaptive_persistence"), dict) else {}
    multiscale = sii.get("multiscale_analysis") if isinstance(sii.get("multiscale_analysis"), dict) else {}
    data_conditions = sii.get("data_conditions") if isinstance(sii.get("data_conditions"), dict) else {}
    uncertainty = sii.get("uncertainty") if isinstance(sii.get("uncertainty"), dict) else {}
    trace = sii.get("processing_trace") if isinstance(sii.get("processing_trace"), dict) else {}
    return {
        "authoritative": bool(trace.get("phase_2_authoritative")),
        "effect": str(trace.get("phase_2_effect") or "supporting_evidence_only"),
        "engine": sii.get("engine"),
        "status": sii.get("status"),
        "relationship_graph": {
            key: graph.get(key)
            for key in (
                "status",
                "reason",
                "method",
                "edge_basis",
                "changed_edge_fraction",
                "weighted_edge_displacement",
                "changed_edges",
                "node_disruption_scores",
                "connected_changed_components",
                "weighted_degree_change",
                "graph_density_change",
                "subsystem_concentration",
                "thresholds",
                "formulas",
            )
            if key in graph
        },
        "mode_conditioned_baseline": {
            key: conditioned.get(key)
            for key in (
                "status",
                "reason",
                "method",
                "used_global_fallback",
                "fallback_reason",
                "selection_confidence",
                "selection_confidence_level",
                "selected_operating_mode",
                "recent_mode",
                "target_features",
                "selection",
                "mode_relationships",
                "mode_signal_drift",
                "limitations",
            )
            if key in conditioned
        },
        "empirical_thresholds": data_conditions.get("empirical_thresholds", {}),
        "adaptive_persistence": adaptive,
        "multiscale_analysis": multiscale,
        "module_failures": list(uncertainty.get("module_failures") or []),
        "processing_trace": {
            key: trace.get(key)
            for key in (
                "phase_2_authoritative",
                "phase_2_effect",
                "mode_aware_authority",
                "module_statuses",
                "module_failures",
                "modules_attempted",
                "modules_completed",
                "modules_limited",
                "modules_failed",
                "operating_modes_used",
                "scales_used",
            )
            if key in trace
        },
    }


def _deformation_started_at(result: dict[str, Any]) -> str | None:
    replay = result.get("replay_timeline") or ((_mapping(result.get("sii_intelligence"))).get("replay_timeline")) or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    if isinstance(timeline, list):
        for frame in timeline:
            if not isinstance(frame, dict):
                continue
            topology_state = frame.get("topology_state") or {}
            drift_index = topology_state.get("drift_index") if isinstance(topology_state, dict) else None
            if isinstance(drift_index, (int, float)) and drift_index >= 0.15:
                return str(frame.get("timestamp_start") or frame.get("timestamp") or "") or None
    profile = _timestamp_profile_from_result(result)
    return profile.get("first_timestamp")


def _source_rows_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for item in _relationship_drift_from_result(result):
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
        profile = _timestamp_profile_from_result(result)
        first = profile.get("first_timestamp")
        last = profile.get("last_timestamp")
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
    windows: list[dict[str, Any]] = []
    for item in _relationship_drift_from_result(result):
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
    replay = result.get("replay_timeline") or ((_mapping(result.get("sii_intelligence"))).get("replay_timeline")) or {}
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
    profile = _timestamp_profile_from_result(result)
    replay = result.get("replay_timeline") or ((_mapping(result.get("sii_intelligence"))).get("replay_timeline")) or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    first_frame = timeline[0] if isinstance(timeline, list) and timeline else {}
    last_frame = timeline[-1] if isinstance(timeline, list) and timeline else {}
    return {
        "created_at": result.get("created_at") or result.get("completed_at") or result.get("last_processed_at"),
        "completed_at": result.get("completed_at") or result.get("last_processed_at"),
        "processed_at": result.get("last_processed_at") or result.get("completed_at"),
        "upload_start": profile.get("first_timestamp") or first_frame.get("timestamp_start") or first_frame.get("timestamp"),
        "upload_end": profile.get("last_timestamp") or last_frame.get("timestamp_end") or last_frame.get("timestamp"),
    }


def build_traceability_packet(*, job_id: str, filename: str, result: dict[str, Any]) -> dict[str, Any]:
    source_rows = _source_rows_from_result(result)
    evidence_windows = _evidence_windows_from_result(result)
    timestamps = _traceability_timestamps_from_result(result)
    provenance = build_analysis_provenance(result)
    return {
        "job_id": str(job_id),
        "run_id": str(job_id),
        "upload_id": str(job_id),
        "source_name": filename,
        "source_rows": source_rows,
        "evidence_windows": evidence_windows,
        "timestamps": timestamps,
        "provenance": provenance,
        "model_version": provenance.get("engine_version"),
        "schema_version": provenance.get("schema_version"),
        "configuration_hash": provenance.get("configuration_hash"),
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
    sii = _mapping(result.get("sii_intelligence"))
    analysis_result = _mapping(result.get("analysis_result"))
    analysis_conditions = analysis_result.get("conditions") if isinstance(analysis_result.get("conditions"), list) else []
    result_conditions = result.get("conditions") if isinstance(result.get("conditions"), list) else []
    conditions = analysis_conditions or result_conditions
    primary_condition = conditions[0] if conditions and isinstance(conditions[0], dict) else {}
    replay = result.get("replay_timeline") or sii.get("replay_timeline") or {}
    replay_timeline = replay.get("timeline") if isinstance(replay, dict) else []
    latest_frame = replay_timeline[-1] if isinstance(replay_timeline, list) and replay_timeline else {}
    relationship_drift = _relationship_drift_from_result(result)
    primary_relationship = relationship_drift[0] if relationship_drift else {}
    variables = [
        str(value)
        for value in (
            primary_condition.get("affected_signals")
            or _observation_variables_from_result(result)
        )
        if str(value).strip()
    ][:12]
    data_conditions = _data_conditions_from_result(result)
    source_rows = _source_rows_from_result(result)
    observation_type = "corroborated_condition" if primary_condition else _observation_type_from_result(result)
    structural_state = str(result.get("operating_state") or sii.get("facility_state") or "Monitoring")
    traceability = build_traceability_packet(job_id=run_id, filename=filename, result=result)
    provenance = traceability["provenance"]
    confidence_score = primary_condition.get("confidence_score") if primary_condition else sii.get("confidence")
    if confidence_score is None:
        confidence_score = ((sii.get("rooms") or [{}])[0] or {}).get("confidence")
    drift_metrics = {
        "neraium_score": sii.get("neraium_score"),
        "baseline_distance": latest_frame.get("baseline_distance") if isinstance(latest_frame, dict) else None,
        "drift_index": ((latest_frame.get("topology_state") or {}).get("drift_index")) if isinstance(latest_frame, dict) else None,
        "drift_velocity": latest_frame.get("drift_velocity") if isinstance(latest_frame, dict) else None,
        "drift_acceleration": latest_frame.get("drift_acceleration") if isinstance(latest_frame, dict) else None,
        "coupling_delta": primary_relationship.get("correlation_delta") if isinstance(primary_relationship, dict) else None,
        "relationship_change_count": len(relationship_drift),
        "observed_persistence": sii.get("observed_persistence"),
        "active_observations": 1 if str(status).lower() == "completed" and observation_type not in {"data_condition", "monitoring_observation"} else 0,
        "replay_frame_count": len(replay_timeline) if isinstance(replay_timeline, list) else 0,
    }
    primary_drivers = (
        [str(primary_condition.get("headline"))]
        if primary_condition.get("headline")
        else [str(sii.get("primary_driver"))]
        if sii.get("primary_driver")
        else []
    )
    supporting_evidence = [
        str(item)
        for item in (
            primary_condition.get("supporting_evidence")
            or sii.get("supporting_evidence")
            or []
        )[:6]
    ]
    archetypes = [str(item) for item in (sii.get("structural_archetypes") or [])[:4]]
    water_intelligence = _mapping(result.get("water_intelligence"))
    water_prior_versions = [
        {
            "relationship_prior_id": item.get("relationship_prior_id"),
            "relationship_prior_version": item.get("relationship_prior_version"),
            "sii_finding_id": item.get("sii_finding_id"),
        }
        for item in water_intelligence.get("insights", [])
        if isinstance(item, dict) and item.get("relationship_prior_id")
    ]
    row_count = _row_count_from_result(result)
    record = {
        "run_id": run_id,
        "job_id": run_id,
        "upload_id": run_id,
        "source_name": filename,
        "source_type": source_type,
        "source_url": None,
        "status": status,
        "created_at": created_at,
        "completed_at": completed_at,
        "rows_received": rows_received if rows_received is not None else row_count,
        "rows_accepted": rows_accepted if rows_accepted is not None else row_count,
        "rows_rejected": rows_rejected if rows_rejected is not None else 0,
        "sensors_detected": _sensor_count_from_result(result),
        "input_hash": provenance.get("input_hash"),
        "result_hash": provenance.get("result_hash"),
        "organization_id": provenance.get("organization_id"),
        "portfolio_id": provenance.get("portfolio_id"),
        "site_id": provenance.get("site_id"),
        "system_id": provenance.get("system_id"),
        "dataset_id": provenance.get("dataset_id"),
        "baseline_id": provenance.get("baseline_id"),
        "baseline_dataset_id": provenance.get("baseline_dataset_id"),
        "baseline_version": provenance.get("baseline_version"),
        "baseline_hash": provenance.get("baseline_hash"),
        "engine_version": provenance.get("engine_version"),
        "build_commit": provenance.get("build_commit"),
        "configuration_hash": provenance.get("configuration_hash"),
        "provenance": provenance,
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
        "adaptive_site_key": f"site::{provenance.get('site_id') or 'default'}",
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
        "condition_id": primary_condition.get("condition_id"),
        "finding_title": primary_condition.get("headline"),
        "system_name": (primary_condition.get("localization") or {}).get("system") if isinstance(primary_condition.get("localization"), dict) else None,
        "subsystem_name": (primary_condition.get("localization") or {}).get("monitored_boundary") if isinstance(primary_condition.get("localization"), dict) else None,
        "potential_impact": primary_condition.get("why_it_matters"),
        "condition": _evidence_condition_record(primary_condition),
        "phase_2_supporting_evidence": _phase2_supporting_evidence_from_result(result),
        "water_intelligence": water_intelligence,
        "water_prior_versions": water_prior_versions,
    }
    record["evidence_hash"] = canonical_digest(
        {key: value for key, value in record.items() if key != "evidence_hash"}
    )
    return record


def _evidence_condition_record(condition: dict[str, Any]) -> dict[str, Any]:
    if not condition:
        return {}
    comparable = dict(condition.get("comparable_operation") or {})
    if isinstance(comparable.get("periods"), list):
        comparable["periods"] = comparable["periods"][:8]
    return {
        key: value
        for key, value in {
            "object_type": "condition",
            "condition_id": condition.get("condition_id"),
            "id": condition.get("condition_id") or condition.get("id"),
            "headline": condition.get("headline"),
            "status": condition.get("status"),
            "classification": condition.get("classification"),
            "trajectory": condition.get("trajectory"),
            "corroboration": condition.get("corroboration"),
            "confidence": condition.get("confidence"),
            "confidence_score": condition.get("confidence_score"),
            "affected_systems": condition.get("affected_systems"),
            "affected_boundaries": condition.get("affected_boundaries"),
            "affected_signals": condition.get("affected_signals"),
            "localization": condition.get("localization"),
            "supporting_relationships": condition.get("supporting_relationships"),
            "conflicting_relationships": condition.get("conflicting_relationships"),
            "uncertain_relationships": condition.get("uncertain_relationships"),
            "supporting_evidence": condition.get("supporting_evidence"),
            "comparable_operation": comparable,
            "timeline": condition.get("timeline"),
            "next_checks": condition.get("next_checks"),
            "escalation": condition.get("escalation"),
            "why_it_matters": condition.get("why_it_matters"),
        }.items()
        if value not in (None, "", [], {})
    }

from __future__ import annotations

from typing import Any


ENGINE_NAME = "neraium_sii"
ENGINE_VERSION = "v2"


def limited_result(reason: str, *, phase: str | None = None, **details: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "limited",
        "reason": reason,
    }
    if phase:
        result["phase"] = phase
    result.update(details)
    return result


def failed_result(exc: Exception) -> dict[str, Any]:
    return {
        "status": "failed",
        "reason": f"{type(exc).__name__}: {exc}",
    }


def status_copy(
    result: dict[str, Any] | None,
    *,
    status: str = "complete",
    reason: str | None = None,
) -> dict[str, Any]:
    payload = dict(result or {})
    payload.setdefault("status", status)
    if reason and not payload.get("reason"):
        payload["reason"] = reason
    return payload


def planned_section(phase: str, capability: str) -> dict[str, Any]:
    return limited_result(
        "not_active_in_phase_1",
        phase=phase,
        capability=capability,
        active=False,
    )


def covariance_section(runner_result: dict[str, Any]) -> dict[str, Any]:
    latest_state = runner_result.get("latest_state") if isinstance(runner_result, dict) else None
    if not runner_result.get("runner_used") or not isinstance(latest_state, dict):
        errors = [str(item) for item in runner_result.get("errors", []) if str(item).strip()]
        return limited_result(
            errors[0] if errors else "covariance_runner_did_not_produce_a_state",
            method="regularized_covariance_mahalanobis_v2",
            rows_received=int(runner_result.get("rows_received") or 0),
            rows_used=int(runner_result.get("rows_processed") or 0),
            columns_used=list(runner_result.get("columns_used") or []),
            runner_result=runner_result,
        )
    components = latest_state.get("instability_components")
    return {
        "status": "complete",
        "method": "regularized_covariance_mahalanobis_v2",
        "rows_received": int(runner_result.get("rows_received") or 0),
        "rows_used": int(runner_result.get("rows_processed") or 0),
        "rows_excluded": int(runner_result.get("rows_excluded") or 0),
        "columns_used": list(runner_result.get("columns_used") or []),
        "metrics": dict(components) if isinstance(components, dict) else {},
        "latest_state": latest_state,
        "runner_result": runner_result,
    }


def persistence_section(
    *,
    fixed_persistence: dict[str, Any],
    adaptive_persistence: dict[str, Any],
    baseline_analysis: dict[str, Any],
    runner_result: dict[str, Any],
    temporal_analysis: dict[str, Any],
) -> dict[str, Any]:
    latest_state = runner_result.get("latest_state") if isinstance(runner_result, dict) else None
    components = latest_state.get("instability_components") if isinstance(latest_state, dict) else {}
    temporal_evidence = temporal_analysis.get("evidence_accumulation") if isinstance(temporal_analysis, dict) else {}
    statuses = {
        str(fixed_persistence.get("status") or "limited"),
        "complete" if isinstance(components, dict) and components else "limited",
        "complete" if isinstance(temporal_evidence, dict) and temporal_evidence else "limited",
    }
    status = "complete" if "complete" in statuses else "limited"
    return {
        "status": status,
        "fixed_row_support": fixed_persistence,
        "baseline_signal_persistence": {
            "drift_trajectory": baseline_analysis.get("drift_trajectory", {}),
            "signals": [
                {
                    "column": item.get("column"),
                    "persistence_score": item.get("persistence_score"),
                    "drift_flag": item.get("drift_flag"),
                }
                for item in baseline_analysis.get("column_drift", [])
                if isinstance(item, dict)
            ],
        },
        "covariance_gates": {
            "persistence_condition": components.get("persistence_condition") if isinstance(components, dict) else None,
            "accumulation_condition": (
                components.get("accumulation_condition")
                if isinstance(components, dict)
                else None
            ),
            "accumulation": components.get("accumulation") if isinstance(components, dict) else None,
            "dynamic_threshold": components.get("dynamic_threshold") if isinstance(components, dict) else None,
        },
        "temporal_evidence_accumulation": temporal_evidence if isinstance(temporal_evidence, dict) else {},
        "method": "phase_1_views_with_phase_2_elapsed_time_persistence",
        "adaptive_persistence": adaptive_persistence,
    }


def uncertainty_section(
    *,
    data_quality: dict[str, Any],
    sensor_health: dict[str, Any],
    temporal_analysis: dict[str, Any],
    module_failures: list[dict[str, str]],
    relationship_analysis: dict[str, Any] | None = None,
    relationship_graph: dict[str, Any] | None = None,
    operating_modes: dict[str, Any] | None = None,
    expected_behavior: dict[str, Any] | None = None,
    covariance_analysis: dict[str, Any] | None = None,
    multiscale_analysis: dict[str, Any] | None = None,
    propagation_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    confidence = data_quality.get("data_confidence") if isinstance(data_quality, dict) else None
    temporal = temporal_analysis.get("uncertainty_summary") if isinstance(temporal_analysis, dict) else None
    limitations = [
        str(item)
        for item in data_quality.get("warnings", [])
        if isinstance(data_quality, dict) and str(item).strip()
    ]
    limitations.extend(item["reason"] for item in module_failures if item.get("reason"))
    components = {
        "data_uncertainty": _data_uncertainty_component(
            data_quality,
            sensor_health,
        ),
        "model_uncertainty": _model_uncertainty_component(
            expected_behavior,
            covariance_analysis,
            temporal_analysis,
            module_failures,
        ),
        "relationship_uncertainty": _relationship_uncertainty_component(
            relationship_analysis,
            relationship_graph,
        ),
        "operating_context_uncertainty": _operating_context_uncertainty_component(
            operating_modes,
            multiscale_analysis,
        ),
        "propagation_uncertainty": _propagation_uncertainty_component(
            propagation_analysis,
        ),
    }
    return {
        "status": "limited" if limitations or module_failures else "complete",
        "data_confidence": confidence if isinstance(confidence, dict) else {},
        "sensor_health": sensor_health,
        "temporal_uncertainty": temporal if isinstance(temporal, dict) else {},
        "module_failures": module_failures,
        "components": components,
        **components,
        "limitations": list(dict.fromkeys(limitations)),
        "interpretation": "Each component is a separately traceable deterministic evidence limitation, not a probability.",
        "processing_trace": {
            "components_reported": list(components),
            "components_aggregated_into_probability": False,
            "component_weighting_performed": False,
        },
    }


def _component(
    *,
    status: str,
    sources: list[str],
    metrics: dict[str, Any],
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "not_probability": True,
        "source_references": sources,
        "traceable_metrics": metrics,
        "limitations": list(dict.fromkeys(limitations)),
    }


def _data_uncertainty_component(
    data_quality: dict[str, Any],
    sensor_health: dict[str, Any],
) -> dict[str, Any]:
    warnings = [
        str(item)
        for item in data_quality.get("warnings", [])
        if str(item).strip()
    ]
    signals = [
        item
        for item in sensor_health.get("signals", [])
        if isinstance(item, dict)
    ]
    limited_health = [
        str(item.get("signal") or item.get("column") or "unknown")
        for item in signals
        if str(item.get("health") or "").lower()
        not in {"healthy", "good"}
    ]
    limitations = [
        *warnings,
        *[
            f"sensor_health_not_acceptable:{signal}"
            for signal in limited_health
        ],
    ]
    readiness = str(data_quality.get("readiness") or "unavailable")
    if readiness.lower() == "not_ready":
        limitations.append("data_quality_not_ready")
    return _component(
        status="limited" if limitations else "complete",
        sources=[
            "data_conditions.data_quality",
            "data_conditions.sensor_health",
        ],
        metrics={
            "readiness": readiness,
            "data_confidence": data_quality.get("data_confidence", {}),
            "sensor_count": len(signals),
            "limited_sensor_count": len(limited_health),
        },
        limitations=limitations,
    )


def _model_uncertainty_component(
    expected_behavior: dict[str, Any] | None,
    covariance_analysis: dict[str, Any] | None,
    temporal_analysis: dict[str, Any],
    module_failures: list[dict[str, str]],
) -> dict[str, Any]:
    expected = expected_behavior if isinstance(expected_behavior, dict) else {}
    covariance = covariance_analysis if isinstance(covariance_analysis, dict) else {}
    model_intervals = [
        {
            "target_signal": item.get("target_signal"),
            "model_version": item.get("model_version"),
            "uncertainty": item.get("uncertainty", {}),
        }
        for item in expected.get("expected_values", [])
        if isinstance(item, dict)
    ]
    limitations = []
    if not expected:
        limitations.append("expected_behavior_not_yet_available")
    elif expected.get("status") != "complete":
        limitations.append(
            str(expected.get("reason") or "expected_behavior_limited")
        )
    if covariance and covariance.get("status") in {"limited", "failed"}:
        limitations.append(
            str(covariance.get("reason") or "covariance_analysis_limited")
        )
    limitations.extend(
        str(item.get("reason"))
        for item in module_failures
        if item.get("reason")
    )
    return _component(
        status="limited" if limitations else "complete",
        sources=[
            "expected_behavior.expected_values.*.uncertainty",
            "covariance_analysis",
            "temporal_analysis.uncertainty_summary",
            "processing_trace.module_failures",
        ],
        metrics={
            "models_evaluated": int(expected.get("models_evaluated") or 0),
            "model_intervals": model_intervals,
            "covariance_status": covariance.get("status"),
            "temporal_uncertainty": temporal_analysis.get(
                "uncertainty_summary",
                {},
            ),
            "module_failure_count": len(module_failures),
        },
        limitations=limitations,
    )


def _relationship_uncertainty_component(
    relationship_analysis: dict[str, Any] | None,
    relationship_graph: dict[str, Any] | None,
) -> dict[str, Any]:
    analysis = (
        relationship_analysis
        if isinstance(relationship_analysis, dict)
        else {}
    )
    graph = relationship_graph if isinstance(relationship_graph, dict) else {}
    edges = graph.get("edges")
    if not isinstance(edges, list):
        edges = (
            graph.get("changed_edges")
            if isinstance(graph.get("changed_edges"), list)
            else []
        )
    reported_edge_count = int(
        (graph.get("current_run_graph") or {}).get("edge_count")
        or len(edges)
    )
    sample_counts = [
        max(
            int(item.get("baseline_sample_count") or item.get("baseline_sample_size") or 0),
            int(item.get("current_sample_count") or item.get("recent_sample_size") or 0),
        )
        for item in edges
        if isinstance(item, dict)
    ]
    ambiguous = sum(
        str(item.get("directionality_status") or "").lower()
        in {"", "association_only_direction_not_established", "ambiguous"}
        for item in edges
        if isinstance(item, dict)
    )
    stability = graph.get("graph_mathematics", {}).get("graph_stability", {})
    limitations = []
    if reported_edge_count <= 0:
        limitations.append("comparable_relationship_edges_unavailable")
    if ambiguous:
        limitations.append("relationship_direction_not_established")
    if analysis and analysis.get("status") in {"limited", "failed"}:
        limitations.append(
            str(analysis.get("reason") or "relationship_analysis_limited")
        )
    return _component(
        status="limited" if limitations else "complete",
        sources=[
            "relationship_analysis",
            "relationship_graph.edges",
            "relationship_graph.graph_mathematics.graph_stability",
        ],
        metrics={
            "edge_count": reported_edge_count,
            "minimum_edge_sample_support": min(sample_counts)
            if sample_counts
            else None,
            "direction_ambiguous_edge_count": ambiguous,
            "graph_stability": stability,
        },
        limitations=limitations,
    )


def _operating_context_uncertainty_component(
    operating_modes: dict[str, Any] | None,
    multiscale_analysis: dict[str, Any] | None,
) -> dict[str, Any]:
    modes = operating_modes if isinstance(operating_modes, dict) else {}
    multiscale = (
        multiscale_analysis
        if isinstance(multiscale_analysis, dict)
        else {}
    )
    match = str(modes.get("match") or "unavailable").lower()
    recent = modes.get("recent_mode")
    limitations = []
    if not recent or recent == "unavailable":
        limitations.append("recent_operating_mode_unavailable")
    if match in {"weak", "unavailable", ""}:
        limitations.append("operating_mode_match_limited")
    if multiscale and multiscale.get("status") == "limited":
        limitations.append("cross_scale_context_limited")
    return _component(
        status="limited" if limitations else "complete",
        sources=[
            "operating_modes",
            "multiscale_analysis.cross_scale_interpretation",
        ],
        metrics={
            "baseline_mode": modes.get("baseline_mode"),
            "recent_mode": recent,
            "mode_match": modes.get("match"),
            "mode_confidence": modes.get("confidence"),
            "cross_scale_classification": (
                multiscale.get("cross_scale_classification")
                or (
                    multiscale.get("cross_scale_interpretation")
                    or {}
                ).get("classification")
            ),
        },
        limitations=limitations,
    )


def _propagation_uncertainty_component(
    propagation_analysis: dict[str, Any] | None,
) -> dict[str, Any]:
    propagation = (
        propagation_analysis
        if isinstance(propagation_analysis, dict)
        else {}
    )
    nested = (
        propagation.get("uncertainty", {})
        .get("propagation_uncertainty", {})
        if propagation
        else {}
    )
    limitations = list(propagation.get("limitations") or [])
    if not propagation:
        limitations.append("propagation_analysis_not_yet_available")
    elif propagation.get("status") != "complete":
        limitations.append(
            str(
                propagation.get("reason")
                or "supported_propagation_path_unavailable"
            )
        )
    return _component(
        status="limited" if limitations else "complete",
        sources=[
            "propagation_analysis.candidate_paths",
            "propagation_analysis.competing_paths",
            "propagation_analysis.unsupported_segments",
            "propagation_analysis.uncertainty.propagation_uncertainty",
        ],
        metrics={
            **nested,
            "candidate_path_count": len(
                propagation.get("candidate_paths", [])
            ),
            "competing_path_count": len(
                propagation.get("competing_paths", [])
            ),
            "unsupported_segment_count": len(
                propagation.get("unsupported_segments", [])
            ),
        },
        limitations=limitations,
    )


def canonical_status(
    *,
    rows_used: int,
    core_statuses: list[str],
    failed_modules: list[str],
) -> str:
    if rows_used <= 0 or (core_statuses and all(status == "failed" for status in core_statuses)):
        return "failed"
    if failed_modules or any(status == "limited" for status in core_statuses):
        return "limited"
    return "complete"

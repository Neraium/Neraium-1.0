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
) -> dict[str, Any]:
    confidence = data_quality.get("data_confidence") if isinstance(data_quality, dict) else None
    temporal = temporal_analysis.get("uncertainty_summary") if isinstance(temporal_analysis, dict) else None
    limitations = [
        str(item)
        for item in data_quality.get("warnings", [])
        if isinstance(data_quality, dict) and str(item).strip()
    ]
    limitations.extend(item["reason"] for item in module_failures if item.get("reason"))
    return {
        "status": "limited" if limitations or module_failures else "complete",
        "data_confidence": confidence if isinstance(confidence, dict) else {},
        "sensor_health": sensor_health,
        "temporal_uncertainty": temporal if isinstance(temporal, dict) else {},
        "module_failures": module_failures,
        "limitations": list(dict.fromkeys(limitations)),
        "interpretation": "These are deterministic evidence limitations, not probabilities.",
    }


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

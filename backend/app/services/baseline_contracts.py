from __future__ import annotations

from typing import Any


WORKFLOW_CREATE_BASELINE = "create_baseline"
WORKFLOW_ANALYZE_NEW_DATA = "analyze_new_data"
WORKFLOW_EXTEND_BASELINE = "extend_baseline"
WORKFLOW_LEGACY_ANALYSIS = "legacy_analysis"

BASELINE_WORKFLOWS = frozenset(
    {
        WORKFLOW_CREATE_BASELINE,
        WORKFLOW_EXTEND_BASELINE,
    }
)
CANONICAL_WORKFLOWS = (
    WORKFLOW_CREATE_BASELINE,
    WORKFLOW_ANALYZE_NEW_DATA,
    WORKFLOW_EXTEND_BASELINE,
)

BASELINE_RESULT_CONTRACT_VERSION = "baseline-suitability.v1"
BEHAVIORAL_MODEL_CONTRACT_VERSION = "behavioral-digital-model.v1"

BASELINE_STATES = (
    "queued",
    "validating_telemetry",
    "assessing_quality",
    "identifying_operating_modes",
    "learning_behavior",
    "fitting_expected_behavior",
    "saving_candidate",
    "awaiting_approval",
    "active",
    "unsuitable",
    "failed",
)

PROHIBITED_BASELINE_OUTPUT_KEYS = frozenset(
    {
        "findings",
        "finding",
        "anomalies",
        "anomaly",
        "anomaly_observations",
        "anomaly_observation",
        "physics_violations",
        "physics_violation",
        "propagation_paths",
        "propagation_path",
        "evidence_fusion_observations",
        "evidence_fusion_observation",
        "evidence_fusion",
        "maintenance_conclusions",
        "maintenance_conclusion",
        "maintenance_recommendations",
        "root_cause_conclusions",
        "root_cause_conclusion",
        "root_cause",
        "sii_intelligence",
        "sii_runner_result",
        "engine_result",
        "driver_attribution",
        "replay_timeline",
        "analysis_result",
    }
)


def normalize_workflow(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "": WORKFLOW_LEGACY_ANALYSIS,
        "baseline": WORKFLOW_CREATE_BASELINE,
        "build_baseline": WORKFLOW_CREATE_BASELINE,
        "create": WORKFLOW_CREATE_BASELINE,
        "create_baseline": WORKFLOW_CREATE_BASELINE,
        "analyze": WORKFLOW_ANALYZE_NEW_DATA,
        "analysis": WORKFLOW_ANALYZE_NEW_DATA,
        "analyze_new_data": WORKFLOW_ANALYZE_NEW_DATA,
        "analyze_against_baseline": WORKFLOW_ANALYZE_NEW_DATA,
        "extend": WORKFLOW_EXTEND_BASELINE,
        "controlled_learning": WORKFLOW_EXTEND_BASELINE,
        "extend_baseline": WORKFLOW_EXTEND_BASELINE,
        "legacy": WORKFLOW_LEGACY_ANALYSIS,
        "legacy_analysis": WORKFLOW_LEGACY_ANALYSIS,
    }
    if normalized not in aliases:
        raise ValueError(
            "workflow must be one of create_baseline, analyze_new_data, or extend_baseline"
        )
    return aliases[normalized]


def is_baseline_workflow(value: Any) -> bool:
    try:
        return normalize_workflow(value) in BASELINE_WORKFLOWS
    except ValueError:
        return False


def prohibited_keys_present(payload: Any) -> list[str]:
    discovered: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).strip().lower()
                if normalized in PROHIBITED_BASELINE_OUTPUT_KEYS:
                    discovered.add(normalized)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return sorted(discovered)


def canonical_baseline_creation_response(payload: dict[str, Any]) -> dict[str, str]:
    """Build the public, camelCase handoff contract for a persisted baseline."""
    value = payload if isinstance(payload, dict) else {}
    candidate = value.get("candidate_model") if isinstance(value.get("candidate_model"), dict) else {}
    source = candidate.get("source") if isinstance(candidate.get("source"), dict) else {}
    scope = value.get("dataset_scope") if isinstance(value.get("dataset_scope"), dict) else {}
    baseline_id = str(
        value.get("baselineId")
        or value.get("established_baseline_id")
        or value.get("baseline_id")
        or value.get("baseline_model_id")
        or candidate.get("baseline_id")
        or ""
    ).strip()
    job_id = str(value.get("jobId") or value.get("job_id") or source.get("job_id") or "").strip()
    dataset_id = str(value.get("datasetId") or value.get("dataset_id") or source.get("dataset_id") or "").strip()
    portfolio_id = str(
        value.get("portfolioId")
        or value.get("portfolio_id")
        or source.get("portfolio_id")
        or scope.get("workspace_id")
        or ""
    ).strip()
    system_id = str(value.get("systemId") or value.get("system_id") or source.get("system_id") or portfolio_id).strip()
    created_at = str(
        value.get("createdAt")
        or value.get("completed_at")
        or value.get("created_at")
        or candidate.get("created_at")
        or ""
    ).strip()
    missing = [
        name
        for name, field in (("jobId", job_id), ("datasetId", dataset_id), ("baselineId", baseline_id), ("createdAt", created_at))
        if not field
    ]
    if missing:
        raise ValueError("completed_baseline_missing_" + "_".join(missing))
    if str(candidate.get("model_id") or baseline_id).strip() != baseline_id:
        raise ValueError("completed_baseline_model_id_mismatch")
    if candidate and str(candidate.get("baseline_id") or "").strip() != baseline_id:
        raise ValueError("completed_baseline_reference_mismatch")
    if source and str(source.get("job_id") or "").strip() != job_id:
        raise ValueError("completed_baseline_job_id_mismatch")
    if source and str(source.get("dataset_id") or "").strip() != dataset_id:
        raise ValueError("completed_baseline_dataset_id_mismatch")
    workspace_path = str(value.get("workspacePath") or "").strip()
    if not workspace_path:
        workspace_path = f"/portfolio/{portfolio_id}/baselines/{baseline_id}" if portfolio_id else f"/baselines/{baseline_id}"
    response = {
        "status": "completed",
        "datasetId": dataset_id,
        "jobId": job_id,
        "baselineId": baseline_id,
        "workspacePath": workspace_path,
        "createdAt": created_at,
    }
    if portfolio_id:
        response["portfolioId"] = portfolio_id
    if system_id:
        response["systemId"] = system_id
    return response


def assert_baseline_output_contract(payload: dict[str, Any]) -> None:
    prohibited = prohibited_keys_present(payload)
    if prohibited:
        raise ValueError(
            "baseline_output_contains_detection_artifacts:" + ",".join(prohibited)
        )
    if payload.get("workflow") not in BASELINE_WORKFLOWS:
        raise ValueError("baseline_output_has_invalid_workflow")
    trace = payload.get("processing_trace")
    if not isinstance(trace, dict):
        raise ValueError("baseline_output_missing_processing_trace")
    if trace.get("sii_engine_invoked") is not False:
        raise ValueError("baseline_output_did_not_prove_sii_isolation")

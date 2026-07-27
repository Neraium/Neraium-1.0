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

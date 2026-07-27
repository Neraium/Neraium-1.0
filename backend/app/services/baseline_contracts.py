from __future__ import annotations

import re
from typing import Any


WORKFLOW_CREATE_BASELINE = "create_baseline"
WORKFLOW_ANALYZE_NEW_DATA = "analyze_new_data"
WORKFLOW_EXTEND_BASELINE = "extend_baseline"
WORKFLOW_LEGACY_ANALYSIS = "legacy_analysis"

JOB_TYPE_BASELINE_CONSTRUCTION = "baseline_construction"
JOB_TYPE_MONITORING_ANALYSIS = "monitoring_analysis"
BASELINE_PROGRESS_STATE_MACHINE = "baseline_construction.v1"
MONITORING_PROGRESS_STATE_MACHINE = "sii_monitoring.v1"

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

BASELINE_PROGRESS_STAGES = (
    "import",
    "validate",
    "map",
    "learn",
    "review",
    "ready",
)
BASELINE_STAGE_LABELS = {
    "import": "Import",
    "validate": "Validate",
    "map": "Map",
    "learn": "Learn",
    "review": "Review",
    "ready": "Ready",
    "failed": "Failed",
    "cancelled": "Cancelled",
}
BASELINE_LEARN_STEPS = (
    ("validating_historical_coverage", "Validating historical coverage"),
    ("assessing_data_quality", "Assessing data quality"),
    ("checking_sensor_suitability", "Checking sensor suitability"),
    ("identifying_operating_modes", "Identifying operating modes"),
    ("learning_signal_behavior", "Learning signal behavior"),
    ("learning_relationships", "Learning relationships"),
    ("building_behavioral_graph", "Building behavioral graph"),
    ("estimating_empirical_thresholds", "Estimating empirical thresholds"),
    ("fitting_expected_behavior_models", "Fitting expected-behavior models"),
    ("creating_candidate_baseline", "Creating candidate baseline"),
)

# Internal parser and builder states are translated once, at the backend boundary,
# into baseline-only progress. Baseline clients never have to interpret SII stages.
_BASELINE_PROGRESS_BY_SOURCE_STAGE = {
    "queued": ("import", "preparing_historical_dataset", "Preparing historical dataset"),
    "accepted": ("import", "importing_historical_dataset", "Importing historical dataset"),
    "reading_csv": ("import", "importing_historical_dataset", "Importing historical dataset"),
    "parsing_telemetry": ("validate", "validating_historical_dataset", "Validating historical dataset"),
    "detecting_schema_signals": ("validate", "validating_historical_dataset", "Validating historical dataset"),
    "cleaning_imputing_data": ("map", "mapping_historical_signals", "Mapping historical signals"),
    "profiling_data_quality": ("learn", "assessing_data_quality", "Assessing data quality"),
    "baseline_historical_coverage": ("learn", "validating_historical_coverage", "Validating historical coverage"),
    "baseline_data_quality": ("learn", "assessing_data_quality", "Assessing data quality"),
    "baseline_sensor_suitability": ("learn", "checking_sensor_suitability", "Checking sensor suitability"),
    "baseline_operating_modes": ("learn", "identifying_operating_modes", "Identifying operating modes"),
    "baseline_signal_behavior": ("learn", "learning_signal_behavior", "Learning signal behavior"),
    "baseline_relationships": ("learn", "learning_relationships", "Learning relationships"),
    "baseline_behavioral_graph": ("learn", "building_behavioral_graph", "Building behavioral graph"),
    "baseline_empirical_thresholds": ("learn", "estimating_empirical_thresholds", "Estimating empirical thresholds"),
    "baseline_expected_models": ("learn", "fitting_expected_behavior_models", "Fitting expected-behavior models"),
    "baseline_candidate": ("learn", "creating_candidate_baseline", "Creating candidate baseline"),
    "baseline_review": ("review", "preparing_suitability_report", "Preparing Baseline Suitability Report"),
    "baseline_ready": ("ready", "candidate_baseline_ready", "Candidate baseline ready"),
    "complete": ("ready", "candidate_baseline_ready", "Candidate baseline ready"),
    "completed": ("ready", "candidate_baseline_ready", "Candidate baseline ready"),
    "failed": ("failed", "baseline_construction_failed", "Baseline construction could not be completed"),
    "error": ("failed", "baseline_construction_failed", "Baseline construction could not be completed"),
    "timeout": ("failed", "baseline_construction_failed", "Baseline construction could not be completed"),
    "cancelled": ("cancelled", "baseline_construction_cancelled", "Baseline construction cancelled"),
}

# Progress normalization is intentionally idempotent because repository reads,
# retries, and API envelopes may already contain a public baseline state.
_BASELINE_PROGRESS_BY_SOURCE_STAGE.update(
    {
        "baseline_preparing_historical_dataset": _BASELINE_PROGRESS_BY_SOURCE_STAGE["queued"],
        "baseline_importing_historical_dataset": _BASELINE_PROGRESS_BY_SOURCE_STAGE["accepted"],
        "baseline_validating_historical_dataset": _BASELINE_PROGRESS_BY_SOURCE_STAGE["parsing_telemetry"],
        "baseline_mapping_historical_signals": _BASELINE_PROGRESS_BY_SOURCE_STAGE["cleaning_imputing_data"],
        "baseline_failed": _BASELINE_PROGRESS_BY_SOURCE_STAGE["failed"],
        "baseline_cancelled": _BASELINE_PROGRESS_BY_SOURCE_STAGE["cancelled"],
        **{
            f"baseline_{step_id}": ("learn", step_id, step_label)
            for step_id, step_label in BASELINE_LEARN_STEPS
        },
    }
)

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

_BASELINE_COPY_PROHIBITED = re.compile(
    r"\b(?:compar(?:e[ds]?|ing|isons?)|anomal(?:y|ies)|evidence|findings?|current\s+behavior)\b|drift\s+against\s+(?:the\s+)?baseline",
    re.IGNORECASE,
)
_MONITORING_ONLY_PROGRESS_KEYS = frozenset(
    {
        "analysis_state",
        "contract_stage",
        "contract_label",
        "contract_progress",
        "propagation_stage",
        "propagation_progress",
        "propagation_label",
        "monitoring_stage",
        "monitoring_step",
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


def job_type_for_workflow(value: Any) -> str:
    return (
        JOB_TYPE_BASELINE_CONSTRUCTION
        if is_baseline_workflow(value)
        else JOB_TYPE_MONITORING_ANALYSIS
    )


def baseline_progress_payload(
    source_stage: Any,
    *,
    progress: Any = None,
) -> dict[str, Any]:
    normalized_source = str(source_stage or "queued").strip().lower()
    stage, step, label = _BASELINE_PROGRESS_BY_SOURCE_STAGE.get(
        normalized_source,
        ("import", "preparing_historical_dataset", "Preparing historical dataset"),
    )
    try:
        bounded_progress = int(max(0, min(100, float(progress))))
    except (TypeError, ValueError):
        bounded_progress = 0
    learn_index = next(
        (index for index, (key, _) in enumerate(BASELINE_LEARN_STEPS) if key == step),
        None,
    )
    processing_state = (
        normalized_source
        if normalized_source.startswith("baseline_")
        else "baseline_failed"
        if stage == "failed"
        else "baseline_cancelled"
        if stage == "cancelled"
        else f"baseline_{step}"
    )
    payload = {
        "job_type": JOB_TYPE_BASELINE_CONSTRUCTION,
        "progress_state_machine": BASELINE_PROGRESS_STATE_MACHINE,
        "processing_state": processing_state,
        "baseline_stage": stage,
        "baseline_stage_label": BASELINE_STAGE_LABELS[stage],
        "baseline_step": step,
        "baseline_step_label": label,
        "baseline_stage_order": list(BASELINE_PROGRESS_STAGES),
        "baseline_learn_steps": [
            {"id": key, "label": step_label}
            for key, step_label in BASELINE_LEARN_STEPS
        ],
        "baseline_learn_step_index": learn_index,
        "percent": bounded_progress,
        "progress": bounded_progress,
        "progress_label": label,
        "message": label,
    }
    assert_baseline_progress_contract(payload)
    return payload


def baseline_copy_is_safe(value: Any) -> bool:
    return _BASELINE_COPY_PROHIBITED.search(str(value or "")) is None


def assert_baseline_progress_contract(payload: dict[str, Any]) -> None:
    if payload.get("job_type") != JOB_TYPE_BASELINE_CONSTRUCTION:
        raise ValueError("baseline_progress_has_invalid_job_type")
    if payload.get("progress_state_machine") != BASELINE_PROGRESS_STATE_MACHINE:
        raise ValueError("baseline_progress_has_invalid_state_machine")
    if payload.get("baseline_stage") not in {*BASELINE_PROGRESS_STAGES, "failed", "cancelled"}:
        raise ValueError("baseline_progress_has_invalid_stage")
    mixed_keys = sorted(key for key in _MONITORING_ONLY_PROGRESS_KEYS if key in payload)
    if mixed_keys:
        raise ValueError("baseline_progress_contains_monitoring_fields:" + ",".join(mixed_keys))
    copy_fields = (
        "baseline_stage_label",
        "baseline_step_label",
        "progress_label",
        "message",
        "propagation_label",
    )
    unsafe = [key for key in copy_fields if not baseline_copy_is_safe(payload.get(key))]
    if unsafe:
        raise ValueError("baseline_progress_contains_monitoring_copy:" + ",".join(unsafe))
    processing_state = str(payload.get("processing_state") or "").lower()
    if any(token in processing_state for token in ("running_sii", "comparison", "evidence", "finding", "anomaly", "propagation")):
        raise ValueError("baseline_progress_contains_monitoring_stage")


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

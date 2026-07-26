from app.services.upload_status_contract import (
    ANALYSIS_STATES,
    canonical_analysis_state,
    normalize_upload_status_payload,
)


EXPECTED_ANALYSIS_STATES = (
    "no_dataset",
    "dataset_selected",
    "upload_complete",
    "ready_to_analyze",
    "analysis_queued",
    "validating",
    "mapping",
    "baseline_creation",
    "comparison",
    "evidence_generation",
    "completed",
    "failed",
    "cancelled",
)


def test_analysis_state_vocabulary_is_explicit_and_complete() -> None:
    assert ANALYSIS_STATES == EXPECTED_ANALYSIS_STATES


def test_worker_stages_map_to_canonical_analysis_states() -> None:
    expected_by_stage = {
        "empty": "no_dataset",
        "validated": "ready_to_analyze",
        "accepted": "upload_complete",
        "queued": "analysis_queued",
        "reading_csv": "upload_complete",
        "parsing_telemetry": "validating",
        "detecting_schema_signals": "validating",
        "cleaning_imputing_data": "baseline_creation",
        "building_relationship_baselines": "baseline_creation",
        "scoring_relationship_drift": "comparison",
        "building_fingerprint": "comparison",
        "building_propagation_model": "evidence_generation",
        "generating_findings_evidence": "evidence_generation",
        "generating_system_interpretation": "evidence_generation",
        "saving_result": "evidence_generation",
        "complete": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
    }

    for stage, expected in expected_by_stage.items():
        assert canonical_analysis_state({"job_id": "dataset-1", "processing_state": stage}) == expected


def test_terminal_job_state_overrides_stale_nonterminal_state() -> None:
    payload = {
        "job_id": "dataset-1",
        "analysis_state": "analysis_queued",
        "processing_state": "queued",
        "job_state": "completed",
    }

    assert canonical_analysis_state(payload) == "completed"


def test_normalized_status_always_publishes_dataset_and_analysis_state() -> None:
    queued = normalize_upload_status_payload({"job_id": "dataset-1", "status": "PENDING", "processing_state": "queued"})
    validating = normalize_upload_status_payload({"job_id": "dataset-1", "status": "PENDING", "processing_state": "parsing_telemetry"})
    running = normalize_upload_status_payload({"job_id": "dataset-1", "status": "PROCESSING", "processing_state": "scoring_relationship_drift"})
    completed = normalize_upload_status_payload({"job_id": "dataset-1", "status": "COMPLETE", "processing_state": "complete"})
    failed = normalize_upload_status_payload({"job_id": "dataset-1", "status": "FAILED", "processing_state": "failed"})
    cancelled = normalize_upload_status_payload({"job_id": "dataset-1", "status": "CANCELLED", "processing_state": "cancelled"})

    assert (queued["dataset_id"], queued["analysis_state"]) == ("dataset-1", "analysis_queued")
    assert (validating["dataset_id"], validating["analysis_state"]) == ("dataset-1", "validating")
    assert (running["dataset_id"], running["analysis_state"]) == ("dataset-1", "comparison")
    assert (completed["dataset_id"], completed["analysis_state"]) == ("dataset-1", "completed")
    assert (failed["dataset_id"], failed["analysis_state"]) == ("dataset-1", "failed")
    assert (cancelled["dataset_id"], cancelled["analysis_state"]) == ("dataset-1", "cancelled")
